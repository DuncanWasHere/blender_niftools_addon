"""Main NIF -> Blender import script."""

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


import bpy
import io_scene_niftools.utils.logging
import nifgen.spells.nif.fix
from io_scene_niftools.file_io.nif import NifFile
from io_scene_niftools.modules.nif_import import scene
from io_scene_niftools.modules.nif_import.animation.object import ObjectAnimation
from io_scene_niftools.modules.nif_import.animation.transform import TransformAnimation
from io_scene_niftools.modules.nif_import.armature import Armature
from io_scene_niftools.modules.nif_import.collision.bound import Bound
from io_scene_niftools.modules.nif_import.collision.havok import BhkCollision
from io_scene_niftools.modules.nif_import.constraint import Constraint
from io_scene_niftools.modules.nif_import.geometry.vertex.groups import VertexGroup
from io_scene_niftools.modules.nif_import.object import Object
from io_scene_niftools.modules.nif_import.object.block_registry import block_store
from io_scene_niftools.modules.nif_import.object.types import NiTypes
from io_scene_niftools.modules.nif_import.property.object import ObjectProperty
from io_scene_niftools.nif_common import NifCommon
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, NifData
from nifgen.formats.nif import classes as NifClasses


class NifImport(NifCommon):

    def __init__(self, operator, context):
        NifCommon.__init__(self, operator, context)

    def execute(self):
        """Main NIF import function."""

        self.load_files()  # Needs to be first to provide version info

        # Helper systems
        self.armaturehelper = Armature()
        self.boundhelper = Bound()
        self.bhkhelper = BhkCollision()
        self.constrainthelper = Constraint()
        self.objecthelper = Object()
        self.object_anim = ObjectAnimation()
        self.transform_anim = TransformAnimation()

        # find and store this list now of selected objects as creating new objects adds them to the selection list
        self.SELECTED_OBJECTS = bpy.context.selected_objects[:]

        # catch nif import errors
        try:
            # check that one armature is selected in 'import geometry + parent
            # to armature' mode
            if NifOp.props.process == "GEOMETRY_ONLY":
                if len(self.SELECTED_OBJECTS) != 1 or self.SELECTED_OBJECTS[0].type != 'ARMATURE':
                    raise io_scene_niftools.utils.logging.NifError(
                        "You must select exactly one armature in 'Import Geometry Only' mode.")

            # Force the wireframe color type to object for collision
            for workspace in bpy.data.workspaces:
                for screen in workspace.screens:
                    for area in screen.areas:
                        if area.type == 'VIEW_3D':
                            for space in area.spaces:
                                if space.type == 'VIEW_3D':
                                    space.shading.wireframe_color_type = 'OBJECT'

            NifLog.info("Importing data")
            # calculate and set frames per second
            if NifOp.props.animation:
                self.transform_anim.set_frames_per_second(NifData.data.roots)

            # merge skeleton roots and transform geometry into the rest pose
            if NifOp.props.merge_skeleton_roots:
                nifgen.spells.nif.fix.SpellMergeSkeletonRoots(data=NifData.data).recurse()
            if NifOp.props.send_geoms_to_bind_pos:
                nifgen.spells.nif.fix.SpellSendGeometriesToBindPosition(data=NifData.data).recurse()
            if NifOp.props.send_detached_geoms_to_node_pos:
                nifgen.spells.nif.fix.SpellSendDetachedGeometriesToNodePosition(data=NifData.data).recurse()
            if NifOp.props.apply_skin_deformation:
                VertexGroup.apply_skin_deformation(NifData.data)

            # store scale correction
            bpy.context.scene.niftools_scene.scale_correction = NifOp.props.scale_correction
            self.apply_scale(NifData.data, NifOp.props.scale_correction)

            # import all root blocks
            for root in NifData.data.roots:
                # root hack for corrupt better bodies meshes and remove geometry from better bodies on skeleton import
                for b in (b for b in root.tree(block_type=NifClasses.NiGeometry) if b.is_skin()):
                    # check if root belongs to the children list of the skeleton root
                    if root in [c for c in b.skin_instance.skeleton_root.children]:
                        # fix parenting and update transform accordingly
                        b.skin_instance.data.set_transform(root.get_transform() * b.skin_instance.data.get_transform())
                        b.skin_instance.skeleton_root = root
                        # delete non-skeleton nodes if we're importing skeleton only
                        if NifOp.props.process == "SKELETON_ONLY":
                            nonbip_children = (child for child in root.children if child.name[:6] != 'Bip01 ')
                            for child in nonbip_children:
                                root.remove_child(child)

                # import this root block
                NifLog.debug(f"Root block: {root.get_global_display()}")
                self.import_root(root)

        except NifError:
            return {'CANCELLED'}

        NifLog.info("Finished")
        return {'FINISHED'}

    def load_files(self):
        NifData.init(NifFile.load_nif(NifOp.props.filepath))
        if NifOp.props.override_scene_info:
            scene.import_version_info(NifData.data)

    def import_root(self, n_root_node):
        """Main import function."""
        # check that this is not a kf file
        if isinstance(n_root_node, (NifClasses.NiSequence, NifClasses.NiSequenceStreamHelper)):
            raise io_scene_niftools.utils.logging.NifError("Use the KF import operator to load KF files.")

        # divinity 2: handle CStreamableAssetData
        if isinstance(n_root_node, NifClasses.CStreamableAssetData):
            n_root_node = n_root_node.root

        # mark armature nodes and bones
        self.armaturehelper.check_for_skin(n_root_node)

        # read the NIF tree
        if isinstance(n_root_node, NifClasses.NiNode) or self.objecthelper.has_geometry(n_root_node):
            b_obj = self.import_branch(n_root_node)
            ObjectProperty().import_object_properties(n_root_node, b_obj)
            ObjectProperty().import_root_extra_data(n_root_node, b_obj)

            # now all havok objects are imported, so we are ready to import the havok constraints
            self.constrainthelper.import_bhk_constraints()

            # parent selected meshes to imported skeleton
            if NifOp.props.process == "SKELETON_ONLY":
                for b_child in self.SELECTED_OBJECTS:
                    self.objecthelper.remove_armature_modifier(b_child)
                    self.objecthelper.append_armature_modifier(b_child, b_obj)

        elif isinstance(n_root_node, NifClasses.NiCamera):
            NifLog.warn('Skipped NiCamera root')

        elif isinstance(n_root_node, NifClasses.NiPhysXProp):
            NifLog.warn('Skipped NiPhysXProp root')

        else:
            NifLog.warn(f"Skipped unsupported root block type '{n_root_node.__class__}' (corrupted nif?).")

    def import_collision(self, n_node):
        """Imports a NiNode's collision_object, if present."""
        if n_node.collision_object:
            if isinstance(n_node.collision_object, NifClasses.BhkNiCollisionObject):
                return self.bhkhelper.import_bhk_shape(n_node.collision_object.body)
            elif isinstance(n_node.collision_object, NifClasses.NiCollisionData):
                return self.boundhelper.import_bounding_volume(n_node.collision_object.bounding_volume)
        return None

    def import_branch(self, n_block, b_armature=None):
        """
        Read the content of the current NIF tree branch to Blender recursively.

        :param n_block: The nif block to import.
        :param b_armature: The blender armature for the current branch.
        """
        if not n_block:
            return None

        NifLog.info(f"Importing data for block '{n_block.name}'")
        if self.objecthelper.has_geometry(n_block) and NifOp.props.process != "SKELETON_ONLY":
            return self.objecthelper.import_geometry_object(b_armature, n_block)

        elif isinstance(n_block, NifClasses.NiNode):
            # import object
            if self.armaturehelper.is_armature_root(n_block):
                # all bones in the tree are also imported by import_armature
                if NifOp.props.process != "GEOMETRY_ONLY":
                    b_obj = self.armaturehelper.import_armature(n_block)
                else:
                    n_name = block_store.import_name(n_block)
                    # get the armature from the blender scene
                    b_obj = math.get_armature()
                    NifLog.info(f"Merging nif tree '{n_name}' with armature '{b_obj.name}'")
                    if n_name != b_obj.name:
                        NifLog.warn(f"Using Nif block '{n_name}' as armature '{b_obj.name}' but names do not match")
                b_armature = b_obj

            elif self.armaturehelper.is_bone(n_block):
                # bones have already been imported during import_armature
                n_name = block_store.import_name(n_block)
                if n_name in b_armature.data.bones:
                    b_obj = b_armature.data.bones[n_name]
                else:
                    # this is a fallback for a weird bug, when a node is child of a NiLodNode in a skeletal nif
                    b_obj = self.objecthelper.create_b_obj(n_block, None, name=n_name)
            else:
                # import as an empty
                b_obj = NiTypes.import_empty(n_block)

            # find children
            b_children = []
            n_children = [child for child in n_block.children]
            for n_child in n_children:
                b_child = self.import_branch(n_child, b_armature=b_armature)
                if b_child and isinstance(b_child, bpy.types.Object):
                    b_children.append(b_child)

            # import collision objects & bounding box
            if NifOp.props.process != "SKELETON_ONLY":
                collision_obj = self.import_collision(n_block)
                if collision_obj:
                    b_children.append(collision_obj)
                b_children.extend(self.boundhelper.import_bounding_box(n_block))

            # set bind pose for children
            self.objecthelper.set_object_bind(b_obj, b_children, b_armature)

            # import extra node data, such as node type
            ObjectProperty().import_object_properties(n_block, b_obj)

            if not isinstance(b_obj, bpy.types.Bone):
                ObjectProperty().import_extra_data(n_block, b_obj)
                NiTypes.import_root_collision(n_block, b_obj)
                NiTypes.import_billboard(n_block, b_obj)
                NiTypes.import_range_lod_data(n_block, b_obj, b_children)

            if NifOp.props.animation:
                self.transform_anim.import_controller_manager(n_block, b_obj, b_armature)

            # set object transform, this must be done after all children objects have been parented to b_obj
            if isinstance(b_obj, bpy.types.Object):
                # note: bones and this object's children already have their matrix set
                b_obj.matrix_local = math.import_matrix(n_block)

                # import object level animations (non-skeletal)
                if NifOp.props.animation:
                    # TODO [anim]: Fetch the action if it exists
                    # self.transform_anim.import_text_keys(n_block, b_action)
                    self.transform_anim.import_transforms(n_block, b_obj)
                    self.object_anim.import_visibility(n_block, b_obj)

            return b_obj

        # all else is currently discarded
        return None
