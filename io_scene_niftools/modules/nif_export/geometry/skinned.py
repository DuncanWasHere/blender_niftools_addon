"""Main module for exporting skinned geometry."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2025 NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****


import numpy as np

import bpy
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, NifData
from nifgen.formats.nif import classes as NifClasses


class SkinnedGeometry:

    def __init__(self):
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_skinned_geometry(self, n_ni_geometry, n_root_node, b_obj, b_eval_mesh, triangles, vertex_map,
                                t_nif_to_blend, b_face_groups, face_group_names):

        if not b_obj.parent or not b_obj.parent_type == 'ARMATURE':
            return

        n_face_groups = []
        ungrouped_faces = []

        # Add body part number
        if self.target_game not in ('FALLOUT_3', 'FALLOUT_NV', 'SKYRIM', 'SKYRIM_SE') or len(b_face_groups) == 0:
            n_face_groups = np.zeros(len(triangles), dtype=int)
        else:
            n_face_groups = b_face_groups[t_nif_to_blend]
            ungrouped_triangle_indices = np.arange(len(b_face_groups))[b_face_groups < 0]
            ungrouped_faces = [b_eval_mesh.polygons[i] for i in ungrouped_triangle_indices]

        # Check that there are no missing body part polygons
        if ungrouped_faces:
            self.select_ungrouped_triangles(b_eval_mesh, b_obj, ungrouped_faces)

        # TODO [mesh/object]: Use more sophisticated armature finding, also taking armature modifier into account
        # now export the vertex weights, if there are any
        if b_obj.parent and b_obj.parent.type == 'ARMATURE':
            b_obj_armature = b_obj.parent
            vertgroups = {vertex_group.name for vertex_group in b_obj.vertex_groups}
            bone_names = set(b_obj_armature.data.bones.keys())
            # the vertgroups that correspond to bone_names are bones that influence the mesh
            boneinfluences = vertgroups & bone_names
            if boneinfluences:  # yes we have skinning!
                # create new skinning instance block and link it
                n_ni_skin_instance, n_ni_skin_data = self.create_skin_inst_data(b_obj, b_obj_armature,
                                                                                b_face_groups)
                n_ni_geometry.skin_instance = n_ni_skin_instance

                # Vertex weights,  find weights and normalization factors
                vert_list = {}
                vert_norm = {}
                unweighted_vertices = []

                for bone_group in boneinfluences:
                    b_list_weight = []
                    b_vert_group = b_obj.vertex_groups[bone_group]

                    for b_vert in b_eval_mesh.vertices:
                        if len(b_vert.groups) == 0:  # check vert has weight_groups
                            unweighted_vertices.append(b_vert.index)
                            continue

                        for g in b_vert.groups:
                            if b_vert_group.name in boneinfluences:
                                if g.group == b_vert_group.index:
                                    b_list_weight.append((b_vert.index, g.weight))
                                    break

                    vert_list[bone_group] = b_list_weight

                    # create normalisation groupings
                    for v in vert_list[bone_group]:
                        if v[0] in vert_norm:
                            vert_norm[v[0]] += v[1]
                        else:
                            vert_norm[v[0]] = v[1]

                self.select_unweighted_vertices(b_obj, unweighted_vertices)

                # for each bone, get the vertex weights and add its n_node to the NiSkinData
                for b_bone_name in boneinfluences:
                    # find vertex weights
                    vert_weights = {}
                    for v in vert_list[b_bone_name]:
                        # v[0] is the original vertex index
                        # v[1] is the weight

                        # vertex_map[v[0]] is the set of vertices (indices) to which v[0] was mapped
                        # so we simply export the same weight as the original vertex for each new vertex

                        # write the weights
                        # extra check for multi material meshes
                        if vertex_map[v[0]] and vert_norm[v[0]]:
                            for vert_index in vertex_map[v[0]]:
                                vert_weights[vert_index] = v[1] / vert_norm[v[0]]
                    # add bone as influence, but only if there were actually any vertices influenced by the bone
                    if vert_weights:
                        # find bone in exported blocks
                        n_node = self.get_bone_block(b_obj_armature.data.bones[b_bone_name])
                        n_ni_geometry.add_bone(n_node, vert_weights)
                del vert_weights

                # update bind position skinning data
                # n_geom.update_bind_position()
                # override pyffi n_geom.update_bind_position with custom one that is relative to the nif root
                self.update_bind_position(n_ni_geometry, n_root_node, b_obj_armature)

                self.export_skin_partition(b_obj, n_face_groups, face_group_names, triangles, n_ni_geometry)

                # calculate center and radius for each skin bone data block
                n_ni_geometry.update_skin_center_radius()

    def export_skin_partition(self, b_obj, n_face_groups, face_group_names, triangles, n_ni_geometry):
        """
        Attaches a skin partition to n_geom if needed.

        Parameters:
            b_obj: The Blender object.
            n_face_groups: Array of integer indices mapping each triangle to a body part.
            face_group_names: Dictionary mapping integer indices to body part names (strings).
            triangles: List of triangle indices.
            n_ni_geometry: The NiGeometry object in the NIF file.
        """
        game = bpy.context.scene.niftools_scene.game
        if NifData.data.version >= 0x04020100 and NifOp.props.skin_partition:
            NifLog.info("Creating skin partition")

            # Warn on bad config settings
            if game == 'OBLIVION':
                if NifOp.props.pad_bones:
                    NifLog.warn(
                        "Using padbones on Oblivion export. Disable the pad bones option to get higher quality skin partitions."
                    )

            # Skyrim Special Edition has a limit of 80 bones per partition, but export is not yet supported
            bones_per_partition_lut = {"OBLIVION": 18, "FALLOUT_3": 18, 'FALLOUT_NV': 18, "SKYRIM": 24}
            rec_bones = bones_per_partition_lut.get(game, None)
            if rec_bones is not None:
                if NifOp.props.max_bones_per_partition < rec_bones:
                    NifLog.warn(
                        f"Using less than {rec_bones} bones per partition on {game} export."
                        f" Set it to {rec_bones} to get higher quality skin partitions."
                    )
                elif NifOp.props.max_bones_per_partition > rec_bones:
                    NifLog.warn(
                        f"Using more than {rec_bones} bones per partition on {game} export."
                        f" This may cause issues in-game."
                    )

            # Translate face group strings to enum members (unique values, maintaining order)
            part_order = [NifClasses.BSDismemberBodyPartType[body_part_name] for body_part_name in
                          face_group_names.keys() if body_part_name in NifClasses.BSDismemberBodyPartType.__members__]

            # Update skin partition
            lostweight = n_ni_geometry.update_skin_partition(
                maxbonesperpartition=NifOp.props.max_bones_per_partition,
                maxbonespervertex=NifOp.props.max_bones_per_vertex,
                stripify=NifOp.props.stripify,
                stitchstrips=True,
                padbones=NifOp.props.pad_bones,
                triangles=triangles,
                trianglepartmap=n_face_groups,
                maximize_bone_sharing=(game in ('FALLOUT_3', 'FALLOUT_NV', 'SKYRIM')),
                part_sort_order=part_order,
            )

            if lostweight > NifOp.props.epsilon:
                NifLog.warn(
                    f"Lost {lostweight:f} in vertex weights while creating a skin partition for Blender object '{b_obj.name}' (nif block '{n_ni_geometry.name}')"
                )

    def update_bind_position(self, n_geom, n_root, b_obj_armature):
        """
        Transfer the Blender bind position to the nif bind position.
        Sets the NiSkinData overall transform to the inverse of the geometry transform
        relative to the skeleton root, and sets the NiSkinData of each bone to
        the inverse of the transpose of the bone transform relative to the skeleton root, corrected
        for the overall transform.
        """

        if not n_geom.is_skin():
            return

        # validate skin and set up quick links
        n_geom._validate_skin()
        skininst = n_geom.skin_instance
        skindata = skininst.data
        skelroot = skininst.skeleton_root

        # calculate overall offset (including the skeleton root transform) and use its inverse
        geomtransform = (n_geom.get_transform(skelroot) * skelroot.get_transform()).get_inverse(fast=False)
        skindata.set_transform(geomtransform)

        # for some nifs, somehow n_root is not set properly?!
        if not n_root:
            NifLog.warn(f"n_root was not set, bug")
            n_root = skelroot

        old_position = b_obj_armature.data.pose_position
        b_obj_armature.data.pose_position = 'POSE'

        # calculate bone offsets
        for i, bone in enumerate(skininst.bones):
            bone_name = block_store.block_to_obj[bone].name
            pose_bone = b_obj_armature.pose.bones[bone_name]
            n_bind = math.mathutils_to_nifformat_matrix(math.blender_bind_to_nif_bind(pose_bone.matrix))
            # TODO [armature]: figure out the correct transform that works universally
            # inverse skin bind in nif armature space, relative to root / geom??
            skindata.bone_list[i].set_transform((n_bind * geomtransform).get_inverse(fast=False))
            # this seems to be correct for skyrim heads, but breaks stuff like ZT2 elephant
            # skindata.bone_list[i].set_transform(bone.get_transform(n_root).get_inverse())

        b_obj_armature.data.pose_position = old_position

    def get_bone_block(self, b_bone):
        """For a blender bone, return the corresponding nif node from the blocks that have already been exported"""

        for n_block, b_obj in block_store.block_to_obj.items():
            if isinstance(n_block, NifClasses.NiNode) and b_bone == b_obj:
                return n_block
        raise NifError(f"Bone '{b_bone.name}' not found.")

    def create_skin_inst_data(self, b_obj, b_obj_armature, body_part_face_groups):
        if bpy.context.scene.niftools_scene.game in ('FALLOUT_3', 'FALLOUT_NV', 'SKYRIM') and len(body_part_face_groups) > 0:
            skininst = block_store.create_block("BSDismemberSkinInstance", b_obj)
        else:
            skininst = block_store.create_block("NiSkinInstance", b_obj)

        # get skeleton root from custom property
        if b_obj.niftools.skeleton_root:
            n_root_name = b_obj.niftools.skeleton_root
        # or use the armature name
        else:
            n_root_name = block_store.get_full_name(b_obj_armature)
        # make sure that such a block exists, find it
        for block in block_store.block_to_obj:
            if isinstance(block, NifClasses.NiNode):
                if block.name == n_root_name:
                    skininst.skeleton_root = block
                    break
        else:
            raise NifError(f"Skeleton root '{n_root_name}' not found.")

        # create skinning data and link it
        skindata = block_store.create_block("NiSkinData", b_obj)
        skininst.data = skindata

        skindata.has_vertex_weights = True
        # fix geometry rest pose: transform relative to skeleton root
        skindata.set_transform(math.get_object_matrix(b_obj).get_inverse())
        return skininst, skindata

    # TODO [mesh]: Join code paths for those two?
    def select_unweighted_vertices(self, b_obj, unweighted_vertices):
        # Vertices must be assigned at least one vertex group
        # Let's be nice and display any unweighted vertices for the user

        if len(unweighted_vertices) > 0:
            for b_scene_obj in bpy.context.scene.objects:
                b_scene_obj.select_set(False)

            bpy.context.view_layer.objects.active = b_obj

            # switch to edit mode to deselect everything in the mesh (not missing vertices or edges)
            bpy.ops.object.mode_set(mode='EDIT', toggle=False)
            bpy.context.tool_settings.mesh_select_mode = (True, False, False)
            bpy.ops.mesh.select_all(action='DESELECT')

            # select unweighted vertices - switch back to object mode to make per-vertex selection
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
            for vert_index in unweighted_vertices:
                b_obj.data.vertices[vert_index].select = True

            # switch back to edit mode to make the selection visible and raise exception
            bpy.ops.object.mode_set(mode='EDIT', toggle=False)

            raise NifError("Cannot export mesh with unweighted vertices. "
                           "The unweighted vertices have been selected in the mesh "
                           "so they can easily be identified.")

    def select_ungrouped_triangles(self, b_mesh, b_obj, polygons_without_bodypart):
        """Select any faces which are not weighted to a vertex group."""

        ngon_mesh = b_obj.data
        # make vertex: poly map of the untriangulated mesh
        vert_poly_dict = {i: set() for i in range(len(ngon_mesh.vertices))}
        for face in ngon_mesh.polygons:
            for vertex in face.vertices:
                vert_poly_dict[vertex].add(face.index)

        # translate the tris of polygons_without_bodypart to polygons (assuming vertex order does not change)
        ngons_without_bodypart = []
        for face in polygons_without_bodypart:
            poly_set = vert_poly_dict[face.vertices[0]]
            for vertex in face.vertices[1:]:
                poly_set = poly_set.intersection(vert_poly_dict[vertex])
                if len(poly_set) == 0:
                    break
            else:
                for poly in poly_set:
                    ngons_without_bodypart.append(poly)

        # switch to object mode so (de)selecting faces works
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        # select mesh object
        for b_deselect_obj in bpy.context.scene.objects:
            b_deselect_obj.select_set(False)
        bpy.context.view_layer.objects.active = b_obj
        # switch to edit mode to deselect everything in the mesh (not missing vertices or edges)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.mesh.select_all(action='DESELECT')

        # switch back to object mode to make per-face selection
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        for poly in ngons_without_bodypart:
            ngon_mesh.polygons[poly].select = True

        # select bad polygons switch to edit mode to select polygons
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        # raise exception
        raise NifError(f"Some polygons of {b_obj.name} not assigned to any body part. "
                       f"The unassigned polygons have been selected in the mesh so they can easily be identified.")