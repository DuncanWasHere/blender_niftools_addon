""" Nif User Interface, connect custom properties from properties.py into Blenders UI"""
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

from bpy.types import Panel

from io_scene_niftools.utils.decorators import register_classes, unregister_classes


class ObjectButtonsPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    @staticmethod
    def is_root_object(b_obj):
        return b_obj.parent is None

class ObjectPanel(ObjectButtonsPanel):
    bl_label = "Niftools Object Property"
    bl_idname = "NIFTOOLS_PT_ObjectPanel"

    # noinspection PyUnusedLocal
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        b_obj = context.object
        nif_obj_props = b_obj.niftools

        layout = self.layout
        row = layout.column()
        if b_obj.type == "EMPTY":
            row.prop(nif_obj_props, "nodetype")
            row.prop(nif_obj_props, "upb")
        if self.is_root_object(b_obj):
            if b_obj.type != "ARMATURE":
                # prn nistringextradata is only useful as replacement for rigging data
                row.prop(nif_obj_props, "prn_location")
            row.prop(nif_obj_props, "bsxflags")
        if b_obj.type == "MESH":
            # consistency flags only exist for NiGeometry
            row.prop(nif_obj_props, "consistency_flags")
        row.prop(nif_obj_props, "flags")

        parent = b_obj.parent
        if parent and parent.type == 'ARMATURE':
            row.prop_search(nif_obj_props, "skeleton_root", parent.data, "bones")

class ObjectBSInvMarkerPanel(ObjectButtonsPanel):
    bl_label = "Niftools BS Inv Marker"
    bl_idname = "NIFTOOLS_PT_ObjectBSInvMarker"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"

    # noinspection PyUnusedLocal
    @classmethod
    def poll(cls, context):
        return cls.is_root_object(context.object)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        bs_inv = context.object.niftools.bs_inv
        if not bs_inv:
            row.operator("object.bs_inv_marker_add", icon='ZOOM_IN', text="")
        else:
            row.operator("object.bs_inv_marker_remove", icon='ZOOM_OUT', text="")
        col = row.column(align=True)
        for i, x in enumerate(bs_inv):
            col.prop(bs_inv[i], "x", index=i)
            col.prop(bs_inv[i], "y", index=i)
            col.prop(bs_inv[i], "z", index=i)
            col.prop(bs_inv[i], "zoom", index=i)


classes = [
    ObjectPanel,
    ObjectBSInvMarkerPanel,
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
