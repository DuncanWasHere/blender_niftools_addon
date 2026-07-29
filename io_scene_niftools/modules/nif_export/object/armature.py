"""Main module for exporting skeleton related objects."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2026 NIF File Format Library and Tools contributors.
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

from ....modules.nif_export import types
from ....modules.nif_export.block_registry import block_store

from ....utils import consts, math
from ....utils.flags import to_unsigned_32
from ....utils.logging import NifLog

from ....utils.singleton import NifOp

BONE_LOD_ROOT = 'BSBoneLOD#BoneRoot#'
NEWLINE = '\r\n'


class Armature:
    """Main class for exporting skeleton related objects."""

    def __init__(self):
        self.b_action = None

    def export_bones(self, b_obj, n_root_node):
        """Export all bones of an armature."""

        assert (b_obj.type == 'ARMATURE')

        # self.b_action = self.transform_anim.get_active_action(b_obj)
        # the armature b_obj was already exported as a NiNode ("Scene Root") n_root_node
        # export the bones as NiNodes, starting from root bones
        old_position = b_obj.data.pose_position
        b_obj.data.pose_position = 'POSE'
        # start export with root bones
        for b_bone in b_obj.data.bones.values():
            if not b_bone.parent:
                self.export_bone(b_obj, b_bone, n_root_node, n_root_node)
        b_obj.data.pose_position = old_position

        self.export_bone_lod_controller(b_obj)
        # the per-bone controllers are added later, once collision export has put the blend
        # controllers on the nodes they have to be ordered against

    def export_bone(self, b_obj, b_bone, n_parent_node, n_root_node):
        """Exports a bone and all of its children."""
        # create a new nif block for this b_bone
        n_node = block_store.create_block("NiNode", b_bone)
        n_node.name = block_store.get_full_name(b_bone)
        # link to nif parent node
        n_parent_node.add_child(n_node)

        self.export_bone_flags(b_bone, n_node)
        self.export_bone_upb(b_obj, b_bone, n_node)
        # set the pose on the nodes
        p_mat = math.get_object_bind(b_obj.pose.bones[b_bone.name])
        math.set_b_matrix_to_n_block(p_mat, n_node)

        # per-bone animation
        # self.transform_anim.export_ni_transform_controller(n_node, b_obj, self.b_action, b_bone)
        # continue down the bone tree
        for b_child in b_bone.children:
            self.export_bone(b_obj, b_child, n_node, n_root_node)

    def export_bone_upb(self, b_obj, b_bone, n_node):
        """Build and attach the bone's UPB string."""

        lines = []
        if b_bone is self.get_bone_lod_root(b_obj):
            lines.append(BONE_LOD_ROOT)
        else:
            n_level = self.get_bone_lod_levels(b_obj).get(b_bone.name)
            if n_level is not None:
                lines.append(f'BSBoneLOD#Bone#{n_level}#')
        if b_bone.nif_bone.priority:
            lines.append(f'BSPriority#{b_bone.nif_bone.priority}#')

        if not lines:
            return
        b_upb = NEWLINE.join(lines) + NEWLINE

        n_ni_string_extra_data = block_store.create_block("NiStringExtraData")
        n_ni_string_extra_data.name = 'UPB'
        n_ni_string_extra_data.string_data = b_upb
        n_node.add_extra_data(n_ni_string_extra_data)

    @staticmethod
    def get_bone_lod_levels(b_obj):
        """Bone name to LOD level, from the armature's bone LOD groups."""

        b_levels = {}
        for n_level, b_group in enumerate(b_obj.data.nif_armature.bone_lod_groups):
            for b_group_bone in b_group.bones:
                if b_group_bone.bone:
                    b_levels[b_group_bone.bone] = n_level
        return b_levels

    @staticmethod
    def get_bone_lod_root(b_obj):
        """
        The bone the LOD controller hangs off, whose UPB says BoneRoot.

        Vanilla skeletons put it on the root bone that the non-accum bone descends from.
        """

        b_root_bones = [b_bone for b_bone in b_obj.data.bones.values() if not b_bone.parent]
        return b_root_bones[0] if b_root_bones else None

    def export_bone_lod_controller(self, b_obj):
        """Export the NiBSBoneLODController built from the armature's bone LOD groups."""

        b_levels = {}
        for b_bone in b_obj.data.bones.values():
            n_level = self.get_bone_lod_levels(b_obj).get(b_bone.name)
            if n_level is not None:
                b_levels.setdefault(n_level, []).append(b_bone)

        if not b_obj.data.nif_armature.bone_lod_groups:
            return

        n_target_node = self.get_bone_lod_target(b_obj)
        if n_target_node is None:
            NifLog.warn(f"'{b_obj.name}' has bone LOD groups, but no root bone was exported to "
                        f"attach the NiBSBoneLODController to. Skipped.")
            return

        # registered without the armature, which already owns its NiNode in obj_to_block
        n_bone_lod_controller = block_store.create_block("NiBSBoneLODController")
        n_bone_lod_controller.flags = 0x4C
        n_bone_lod_controller.frequency = 1.0
        n_bone_lod_controller.phase = 0.0
        n_bone_lod_controller.start_time = consts.FLOAT_MAX
        n_bone_lod_controller.stop_time = consts.FLOAT_MIN
        n_bone_lod_controller.lod = 0

        # the list defines the levels, so an empty group isn't dropped.
        # Vanilla skeletons have empty groups for some reason
        n_num_groups = len(b_obj.data.nif_armature.bone_lod_groups)
        n_bone_lod_controller.num_l_o_ds = n_num_groups
        n_bone_lod_controller.num_node_groups = n_num_groups
        n_bone_lod_controller.reset_field("node_groups")

        for n_level in range(n_num_groups):
            n_bone_nodes = [block_store.obj_to_block[b_bone] for b_bone in b_levels.get(n_level, [])
                            if b_bone in block_store.obj_to_block]
            n_group = n_bone_lod_controller.node_groups[n_level]
            n_group.num_nodes = len(n_bone_nodes)
            n_group.reset_field("nodes")
            for i, n_bone_node in enumerate(n_bone_nodes):
                n_group.nodes[i] = n_bone_node

        n_target_node.add_controller(n_bone_lod_controller)
        n_bone_lod_controller.target = n_target_node

        NifLog.info(f"Exported a NiBSBoneLODController with {n_num_groups} bone LOD groups.")

    def get_bone_lod_target(self, b_obj):
        """The node the bone LOD controller hangs off, which is the armature's root bone."""

        b_root_bone = self.get_bone_lod_root(b_obj)
        return block_store.obj_to_block.get(b_root_bone) if b_root_bone else None

    def export_bone_flags(self, b_bone, n_node):
        """
        Export bone flags according to the bone properties
        or the game version if none was set.
        """

        if b_bone.nif_bone.flags != 0:
            n_node.flags = to_unsigned_32(b_bone.nif_bone.flags)
        else:
            game = bpy.context.scene.niftools_scene.game
            if bpy.context.scene.niftools_scene.is_bs():
                # default for Oblivion bones
                # note: bodies have 0x000E, clothing has 0x000F
                n_node.flags = 0x000E
            elif game in ('CIVILIZATION_IV', 'EMPIRE_EARTH_II'):
                if b_bone.children:
                    # default for Civ IV/EE II bones with children
                    n_node.flags = 0x0006
                else:
                    # default for Civ IV/EE II final bones
                    n_node.flags = 0x0016
            elif game in ('DIVINITY_2',):
                if b_bone.children:
                    # default for Div 2 bones with children
                    n_node.flags = 0x0186
                elif b_bone.name.lower()[-9:] == 'footsteps':
                    n_node.flags = 0x0116
                else:
                    # default for Div 2 final bones
                    n_node.flags = 0x0196
            else:
                n_node.flags = 0x0002  # default for Morrowind bones
