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


import bpy
from bpy.types import Operator

from io_scene_niftools import properties
from io_scene_niftools.utils.decorators import register_classes, unregister_classes


class BSFurnitureMarkerAdd(Operator):
    """Add BSFurnitureMarker."""

    bl_idname = "object.bs_furniture_marker_add"
    bl_label = "Add Furniture Marker"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bs_furniture_marker = context.object.nif_object.bs_furniture_marker
        bs_furniture_marker_item = bs_furniture_marker.add()
        bs_furniture_marker_item.name = "FRN"
        return {'FINISHED'}

class BSFurnitureMarkerRemove(bpy.types.Operator):
    """Remove BSFurnitureMarker."""

    bl_idname = "object.bs_furniture_marker_remove"
    bl_label = "Remove Furniture Marker"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bs_furniture_marker = context.object.nif_object.bs_furniture_marker
        item = len(bs_furniture_marker) - 1
        bs_furniture_marker.remove(item)
        return {'FINISHED'}

class FurniturePositionAdd(Operator):
    """Add furniture position."""

    bl_idname = "object.furniture_position_add"
    bl_label = "Add Furniture Position"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        b_obj = context.active_object

        for i, x in enumerate(b_obj.nif_object.bs_furniture_marker):
            b_obj.nif_object.bs_furniture_marker[i].positions.add()

        return {'FINISHED'}

class FurniturePositionRemove(Operator):
    """Remove furniture position."""

    bl_idname = "object.furniture_position_remove"
    bl_label = "Remove Furniture Position"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        b_obj = context.active_object

        for i, x in enumerate(b_obj.nif_object.bs_furniture_marker):
            item = b_obj.nif_object.bs_furniture_marker[i].position_index
            b_obj.nif_object.bs_furniture_marker[i].positions.remove(item)

        return {'FINISHED'}

classes = [
    BSFurnitureMarkerAdd,
    BSFurnitureMarkerRemove,
    FurniturePositionAdd,
    FurniturePositionRemove
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
