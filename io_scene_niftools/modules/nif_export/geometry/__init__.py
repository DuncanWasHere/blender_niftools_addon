"""Classes for exporting NIF geometry objects."""

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
from io_scene_niftools.modules.nif_export.animation.geometry import GeometryAnimation
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.geometry import skin_partition
from io_scene_niftools.modules.nif_export.geometry.data import GeometryData
from io_scene_niftools.modules.nif_export.geometry.skinned import SkinnedGeometry
from io_scene_niftools.modules.nif_export.property.object import ObjectProperty
from io_scene_niftools.modules.nif_export.property.texture.texture import NiTexturingProperty
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses


class Geometry:
    """
    Main interface class for exporting NIF geometry blocks
    (i.e., NiTriShape, NiTriStrips, BSTriShape, NiSkinInstance and subclasses,
    NiTriStripsData, NiTriShapeData, NiSkinData, NiSkinPartition).
    shader and texture properties are handled by helper classes.
    """

    def __init__(self):
        self.texture_property_helper = NiTexturingProperty.get()
        self.object_property_helper = ObjectProperty()
        self.geometry_animation_helper = GeometryAnimation()
        self.geometry_data_helper = GeometryData()
        self.skinned_geometry_helper = SkinnedGeometry()

        self.nif_scene = bpy.context.scene.niftools_scene
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_geometry(self, b_obj, n_parent_node, n_root_node):
        """
        Export a Blender mesh object as a NiGeometry block.
        It will be parented to the given parent node.
        For non-skinned meshes, a strips shape will be created if enabled in the operator settings.
        Property blocks (shader, texture, and material) and skin blocks will also be exported as appropriate.
        """

        NifLog.info(f"Exporting {b_obj.name}.")

        # Get mesh from the Blender object and evaluate it with modifiers applied
        b_mesh = b_obj.data
        b_eval_mesh = self.get_evaluated_mesh(b_obj)

        # Ensure evaluated mesh has vertices
        if not b_eval_mesh.vertices:
            NifLog.warn(f"Mesh object {b_obj} has no vertices. "
                        f"It will not be exported.")
            return

        b_materials = []

        # Get the mesh's materials if not a collision shape
        if not isinstance(n_parent_node, NifClasses.RootCollisionNode):
            b_materials = b_eval_mesh.materials

        # If mesh has no materials, all face material indices should be 0, so fake one material in the material list
        if not b_materials:
            b_materials = [None]

        # Get body part face group attributes
        b_face_groups, face_group_names = self.get_body_part_face_groups(b_eval_mesh)

        n_ni_geometry_blocks = []

        # Export geometry blocks for every active material in the mesh
        for b_mat_index, b_mat in enumerate(b_materials):
            n_ni_geometry = (self.export_ni_geometry(b_obj, b_mat, b_mat_index, n_parent_node))
            n_ni_geometry_blocks.append(n_ni_geometry)

            vertex_map, triangles, t_nif_to_blend = self.export_ni_geometry_data(b_obj, b_eval_mesh, b_mat,
                                                                                 b_mat_index, n_ni_geometry)

            self.skinned_geometry_helper.export_skinned_geometry(n_ni_geometry, n_root_node, b_obj, b_eval_mesh,
                                                                 triangles, vertex_map, t_nif_to_blend,
                                                                 b_face_groups, face_group_names)

            # Export EGM or NiGeomMorpherController animation
            # Shape keys are only present on the raw, unevaluated mesh
            self.geometry_animation_helper.export_geometry_animations(b_mesh, n_ni_geometry, vertex_map)

        return n_ni_geometry_blocks[0]

    def export_ni_geometry(self, b_obj, b_mat, b_mat_index, n_parent_node):
        """Export a NiGeometry block."""

        # Create a NiGeometry block
        n_ni_geometry = None
        if self.target_game in ("SKYRIM_SE",):
            n_ni_geometry = block_store.create_block("BSTriShape", b_obj)
        elif NifOp.props.stripify and not (b_obj.parent and b_obj.parent.type == 'ARMATURE'):
            n_ni_geometry = block_store.create_block("NiTriStrips", b_obj)
        else:
            n_ni_geometry = block_store.create_block("NiTriShape", b_obj)

        # Parent to node
        if n_parent_node:
            n_parent_node.add_child(n_ni_geometry)

            # Add texture effect block (must be added as parent of the geometry block)
            n_parent_node = self.export_texture_effect(n_parent_node, b_mat)

        # Fill in the block's non-trivial values
        if isinstance(n_parent_node, NifClasses.RootCollisionNode):
            n_ni_geometry.name = ""
        else:
            n_ni_geometry.name = b_obj.name

        # Suffix with material index if multiple materials are present
        if b_mat_index > 0:
            n_ni_geometry.name = f"{n_ni_geometry.name}: {b_mat_index}"
        else:
            n_ni_geometry.name = block_store.get_full_name(n_ni_geometry)

        # Extra shader for Sid Meier's Railroads
        if self.target_game == 'SID_MEIER_S_RAILROADS':
            n_ni_geometry.has_shader = True
            n_ni_geometry.shader_name = "RRT_NormalMap_Spec_Env_CubeLight"
            n_ni_geometry.unknown_integer = -1

        math.set_object_matrix(b_obj, n_ni_geometry)  # Add transforms
        self.object_property_helper.export_object_properties(b_obj, n_ni_geometry)  # Object properties

        return n_ni_geometry

    def export_ni_geometry_data(self, b_obj, b_eval_mesh, b_mat, b_mat_index, n_ni_geometry):
        """Export a NiGeometryData block."""

        # Create a NiGeometryData block
        n_ni_geometry_data = None
        if isinstance(n_ni_geometry, NifClasses.BSTriShape):
            n_ni_geometry_data = n_ni_geometry
        elif isinstance(n_ni_geometry, NifClasses.NiTriStrips):
            n_ni_geometry_data = block_store.create_block("NiTriStripsData", b_obj)
            n_ni_geometry.data = n_ni_geometry_data
        else:
            n_ni_geometry_data = block_store.create_block("NiTriShapeData", b_obj)
            n_ni_geometry.data = n_ni_geometry_data

        # Set consistency flags
        if isinstance(n_ni_geometry, NifClasses.NiTriBasedGeom):
            n_ni_geometry_data.consistency_flags = NifClasses.ConsistencyType[b_obj.niftools.consistency_flags]

        b_uv_layers = b_eval_mesh.uv_layers

        if b_eval_mesh.polygons:
            if b_uv_layers:
                # If there are UV coordinates then double check that there is UV data
                if not b_eval_mesh.uv_layer_stencil:
                    NifLog.warn(f"No UV map for texture associated with selected mesh '{b_eval_mesh.name}'.")

        if self.nif_scene.is_bs():
            if len(b_uv_layers) > 1:
                raise NifError(f"{self.target_game} does not support multiple UV layers.")

        # Should normals be exported?
        has_normals = False
        if b_mat is not None:
            has_normals = True
            if self.nif_scene.is_skyrim() and b_mat.niftools_shader.model_space_normals:
                has_normals = False

        # Should tangents be exported?
        use_tangents = False
        if b_uv_layers and has_normals:
            default_use_tangents = 'BULLY_SE'
            if self.target_game in default_use_tangents or self.nif_scene.is_bs() or (
                    self.target_game in self.texture_property_helper.USED_EXTRA_SHADER_TEXTURES):
                use_tangents = True

        # Should vertex colors be exported?
        has_vertex_colors = len(b_eval_mesh.vertex_colors) > 0 or len(b_eval_mesh.color_attributes) > 0

        (triangles, t_nif_to_blend,
         vertex_information, v_nif_to_blend) = self.geometry_data_helper.get_geom_data(b_mesh=b_eval_mesh,
                                                                                       color=has_vertex_colors,
                                                                                       normal=has_normals,
                                                                                       uv=len(b_uv_layers) > 0,
                                                                                       tangent=use_tangents,
                                                                                       b_mat_index=b_mat_index)

        if len(vertex_information['POSITION']) == 0:
            return  # Skip empty material indices
        if len(vertex_information['POSITION']) > 65535:
            raise NifError("Too many vertices! Decimate your mesh and try again.")
        if len(triangles) > 65535:
            raise NifError("Too many triangles! Decimate your mesh and try again.")

        if len(b_uv_layers) > 0:
            # Adjustment of UV coordinates because of imprecision at larger sizes
            uv_array = vertex_information['UV']
            for layer_idx in range(len(b_uv_layers)):
                for coord_idx in range(uv_array.shape[2]):
                    coord_min = np.min(uv_array[:, layer_idx, coord_idx])
                    coord_max = np.max(uv_array[:, layer_idx, coord_idx])
                    min_floor = np.floor(coord_min)
                    # UV coordinates must not be in the 0th UV square and must fit in one UV square
                    if min_floor != 0 and np.floor(coord_max) == min_floor:
                        uv_array[:, layer_idx, coord_idx] -= min_floor

        vertex_map = [None for _ in range(len(b_eval_mesh.vertices))]
        for i, vertex_index in enumerate(v_nif_to_blend):
            if vertex_map[vertex_index] is None:
                vertex_map[vertex_index] = [i]
            else:
                vertex_map[vertex_index].append(i)

        self.geometry_data_helper.set_geom_data(n_ni_geometry, triangles, vertex_information, b_uv_layers)

        return vertex_map, triangles, t_nif_to_blend

    def export_texture_effect(self, n_block, b_mat):
        """Export a texture effect."""

        # TODO [texture]: Detect effect
        ref_mtex = False
        if ref_mtex:
            # create a new parent block for this shape
            extra_node = block_store.create_block("NiNode", ref_mtex)
            n_block.add_child(extra_node)
            # set default values for this ninode
            extra_node.rotation.set_identity()
            extra_node.scale = 1.0
            extra_node.flags = 0x000C  # morrowind
            # create texture effect block and parent the texture effect and n_geom to it
            texeff = self.texture_property_helper.export_texture_effect(ref_mtex)
            extra_node.add_child(texeff)
            extra_node.add_effect(texeff)
            return extra_node
        return n_block

    def get_evaluated_mesh(self, b_obj):
        """Get a Blender mesh with all modifiers applied."""

        # Get the armature influencing this mesh, if it exists
        b_armature_obj = b_obj.find_armature()
        if b_armature_obj:
            old_position = b_armature_obj.data.pose_position
            b_armature_obj.data.pose_position = 'REST'

        # make a copy with all modifiers applied
        dg = bpy.context.evaluated_depsgraph_get()
        eval_obj = b_obj.evaluated_get(dg)
        eval_mesh = eval_obj.to_mesh(preserve_all_data_layers=True, depsgraph=dg)
        if b_armature_obj:
            b_armature_obj.data.pose_position = old_position
        return eval_mesh

    def get_body_part_face_groups(self, b_mesh):
        """
        Assigns BSDismemberBodyPartType enum values to valid body part attributes
        and returns a mapping of face indices to these values.

        Parameters:
            b_mesh: Blender mesh (the mesh data of the object).

        Returns:
            tuple: A tuple containing:
                - numpy.ndarray: An array where each element is the BSDismemberBodyPartType value
                  for the corresponding face, or -1 if the face does not belong to any body part.
                - dict: A dictionary mapping BSDismemberBodyPartType values to attribute names.
        """

        valid_body_part_names = {member.name for member in NifClasses.BSDismemberBodyPartType}

        face_group_names = {}
        name_to_enum = {}

        for body_part_name in valid_body_part_names:
            if body_part_name in b_mesh.attributes:
                attr = b_mesh.attributes[body_part_name]
                if attr.data_type == 'BOOLEAN' and attr.domain == 'FACE':
                    enum_value = NifClasses.BSDismemberBodyPartType[body_part_name]
                    face_group_names[enum_value] = body_part_name
                    name_to_enum[body_part_name] = enum_value

        face_count = len(b_mesh.polygons)
        b_face_groups = np.full(face_count, -1, dtype=int)  # Default to -1 for unassigned faces

        for body_part_name, enum_value in name_to_enum.items():
            attr = b_mesh.attributes[body_part_name]
            for face_idx, attr_data in enumerate(attr.data):
                if attr_data.value:
                    b_face_groups[face_idx] = enum_value

        return b_face_groups, face_group_names
