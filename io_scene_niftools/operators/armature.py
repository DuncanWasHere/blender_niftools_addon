"""Operators for editing the bone LOD groups of a skeleton armature."""

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
from bpy.types import Operator

from ..utils.decorators import register_classes, unregister_classes


class BoneLODOperator(Operator):
    """Shared context for the bone LOD group operators."""

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.armature is not None

    @staticmethod
    def get_groups(context):
        return context.armature.nif_armature


class BoneLODGroupAdd(BoneLODOperator):
    """Add a bone LOD group. Its position in the list is its LOD level"""

    bl_idname = "niftools.bone_lod_group_add"
    bl_label = "Add Bone LOD Group"

    def execute(self, context):
        nif_armature = self.get_groups(context)
        nif_armature.bone_lod_groups.add()
        nif_armature.active_bone_lod_group_index = len(nif_armature.bone_lod_groups) - 1
        return {'FINISHED'}


class BoneLODGroupRemove(BoneLODOperator):
    """Remove the selected bone LOD group. Every group after it drops a level"""

    bl_idname = "niftools.bone_lod_group_remove"
    bl_label = "Remove Bone LOD Group"

    @classmethod
    def poll(cls, context):
        return context.armature is not None and len(context.armature.nif_armature.bone_lod_groups) > 0

    def execute(self, context):
        nif_armature = self.get_groups(context)
        nif_armature.bone_lod_groups.remove(nif_armature.active_bone_lod_group_index)
        nif_armature.active_bone_lod_group_index = min(nif_armature.active_bone_lod_group_index,
                                                       len(nif_armature.bone_lod_groups) - 1)
        return {'FINISHED'}


class BoneLODBoneAdd(BoneLODOperator):
    """Add a bone slot to the selected LOD group"""

    bl_idname = "niftools.bone_lod_bone_add"
    bl_label = "Add Bone"

    @classmethod
    def poll(cls, context):
        return context.armature is not None and len(context.armature.nif_armature.bone_lod_groups) > 0

    def execute(self, context):
        nif_armature = self.get_groups(context)
        b_group = nif_armature.bone_lod_groups[nif_armature.active_bone_lod_group_index]
        b_group.bones.add()
        b_group.active_bone_index = len(b_group.bones) - 1
        return {'FINISHED'}


class BoneLODBoneRemove(BoneLODOperator):
    """Remove the selected bone from its LOD group"""

    bl_idname = "niftools.bone_lod_bone_remove"
    bl_label = "Remove Bone"

    @classmethod
    def poll(cls, context):
        if context.armature is None:
            return False
        nif_armature = context.armature.nif_armature
        if not nif_armature.bone_lod_groups:
            return False
        return len(nif_armature.bone_lod_groups[nif_armature.active_bone_lod_group_index].bones) > 0

    def execute(self, context):
        nif_armature = self.get_groups(context)
        b_group = nif_armature.bone_lod_groups[nif_armature.active_bone_lod_group_index]
        b_group.bones.remove(b_group.active_bone_index)
        b_group.active_bone_index = min(b_group.active_bone_index, len(b_group.bones) - 1)
        return {'FINISHED'}


classes = [
    BoneLODGroupAdd,
    BoneLODGroupRemove,
    BoneLODBoneAdd,
    BoneLODBoneRemove,
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
