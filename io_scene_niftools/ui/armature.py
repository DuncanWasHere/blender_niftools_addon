"""Nif User Interface, connect custom properties from properties.py into Blenders UI"""

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

from bpy.types import Panel, UIList

from ..properties.object import OBJECT_FLAG_BITS
from ..utils.decorators import register_classes, unregister_classes
from ..utils.flags import draw_bit_bools


class BonePanel(Panel):
    bl_idname = "NIFTOOLS_PT_BonePanel"
    bl_label = "NifTools Bone"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "bone"

    # noinspection PyUnusedLocal
    @classmethod
    def poll(cls, context):
        return context.bone is not None

    def draw(self, context):
        nif_bone_props = context.bone.nif_bone

        row = self.layout.column()

        row.prop(nif_bone_props, "priority")
        row.prop(nif_bone_props, "longname")


class BoneFlagsPanel(Panel):
    bl_idname = "NIFTOOLS_PT_BoneFlagsPanel"
    bl_label = "Object Flags"
    bl_parent_id = "NIFTOOLS_PT_BonePanel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "bone"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_bit_bools(self.layout, context.bone.nif_bone, OBJECT_FLAG_BITS)


class ArmaturePanel(Panel):
    bl_label = "NifTools Armature"
    bl_idname = "NIFTOOLS_PT_ArmaturePropsPanel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    # noinspection PyUnusedLocal
    @classmethod
    def poll(cls, context):
        return context.armature is not None

    def draw(self, context):
        nif_armature_props = context.armature.nif_armature

        layout = self.layout
        row = layout.column()

        row.prop(nif_armature_props, "axis_forward")
        row.prop(nif_armature_props, "axis_up")
        row.prop(nif_armature_props, "skeleton_id")


class BoneLODGroupList(UIList):
    """The LOD groups. A group's row number is its LOD level."""

    bl_idname = "NIFTOOLS_UL_BoneLODGroups"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=f"Level {index}", icon='GROUP_BONE')
        layout.label(text=f"{len(item.bones)} bones")


class BoneLODBoneList(UIList):
    """The bones of the selected LOD group."""

    bl_idname = "NIFTOOLS_UL_BoneLODBones"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop_search(item, "bone", context.armature, "bones", text="", icon='BONE_DATA')


class BoneLODPanel(Panel):
    bl_label = "Bone LOD Groups"
    bl_idname = "NIFTOOLS_PT_BoneLODPanel"
    bl_parent_id = "NIFTOOLS_PT_ArmaturePropsPanel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.armature is not None

    def draw(self, context):
        layout = self.layout
        nif_armature = context.armature.nif_armature

        row = layout.row()
        row.template_list(BoneLODGroupList.bl_idname, "", nif_armature, "bone_lod_groups",
                          nif_armature, "active_bone_lod_group_index", rows=4)
        col = row.column(align=True)
        col.operator("niftools.bone_lod_group_add", icon='ADD', text="")
        col.operator("niftools.bone_lod_group_remove", icon='REMOVE', text="")

        if not nif_armature.bone_lod_groups:
            return

        b_group = nif_armature.bone_lod_groups[nif_armature.active_bone_lod_group_index]
        row = layout.row()
        row.template_list(BoneLODBoneList.bl_idname, "", b_group, "bones",
                          b_group, "active_bone_index", rows=6)
        col = row.column(align=True)
        col.operator("niftools.bone_lod_bone_add", icon='ADD', text="")
        col.operator("niftools.bone_lod_bone_remove", icon='REMOVE', text="")


classes = [
    BonePanel,
    BoneFlagsPanel,
    ArmaturePanel,
    BoneLODGroupList,
    BoneLODBoneList,
    BoneLODPanel
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
