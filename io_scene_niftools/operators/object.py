""" Nif User Interface, connect custom properties from properties.py into Blenders UI"""

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
import mathutils
from bpy_extras import view3d_utils
from bpy.types import Operator

from .. import properties
from ..utils.decorators import register_classes, unregister_classes
from ..utils import decal


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

class NifMultiBoundAdd(Operator):
    """Add a bound helper to this BSMultiBoundNode. Move and scale it to set the bound"""

    bl_idname = "object.nif_multi_bound_add"
    bl_label = "Add Bound"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_obj = context.object
        return b_obj is not None and b_obj.nif_object.nodetype == 'BSMultiBoundNode'

    def execute(self, context):
        b_obj = context.object

        b_helper = bpy.data.objects.new(f"{b_obj.name} MultiBound", None)
        b_helper.empty_display_type = 'CUBE'
        b_helper.empty_display_size = 1.0
        b_helper.nif_object.node_multi_bound.is_bound_helper = True
        b_helper.parent = b_obj

        # link next to the node itself, so it shows up wherever that one is visible
        for b_collection in b_obj.users_collection:
            b_collection.objects.link(b_helper)

        return {'FINISHED'}


class NifMultiBoundRemove(Operator):
    """Remove this BSMultiBoundNode's bound helper"""

    bl_idname = "object.nif_multi_bound_remove"
    bl_label = "Remove Bound"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_obj = context.object
        return b_obj is not None and any(b_child.nif_object.node_multi_bound.is_bound_helper
                                         for b_child in b_obj.children)

    def execute(self, context):
        for b_child in list(context.object.children):
            if b_child.nif_object.node_multi_bound.is_bound_helper:
                bpy.data.objects.remove(b_child, do_unlink=True)
        return {'FINISHED'}


def _decal_root(context):
    """Get the root whose decal data the current UI is editing."""

    b_obj = context.object
    if b_obj is None:
        return None
    if decal.is_decal_helper(b_obj):
        return b_obj.nif_object.decal_placement_root
    if b_obj.parent is None and b_obj.type in ('EMPTY', 'ARMATURE'):
        return b_obj
    return None


def _active_decal_data(b_root):
    store = b_root.nif_object.bs_decal_placement
    if not store:
        return None
    index = min(b_root.nif_object.decal_placement_index, len(store) - 1)
    return store[index]


def _active_vector_block(b_root):
    b_data = _active_decal_data(b_root)
    if b_data is None or not b_data.vector_blocks:
        return None
    index = min(b_data.vector_block_index, len(b_data.vector_blocks) - 1)
    return b_data.vector_blocks[index]


def _remove_point_helpers(b_points):
    for b_point in b_points:
        if b_point.helper is not None:
            bpy.data.objects.remove(b_point.helper, do_unlink=True)


def _add_decal_point(b_root, b_vector_block, point, normal):
    index = len(b_vector_block.points)
    b_helper, normal_length = decal.create_point_helper(
        b_root, point, normal, f"{b_root.name} Decal Point {index + 1}")
    b_point = b_vector_block.points.add()
    b_point.helper = b_helper
    b_point.normal_length = normal_length
    b_vector_block.point_index = index
    decal.select_helper(b_helper)
    return b_helper


class NifDecalPlacementAdd(Operator):
    """Add a BSDecalPlacementVectorExtraData block with one empty vector block."""

    bl_idname = "object.nif_decal_placement_add"
    bl_label = "Add Decal Placement Data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _decal_root(context) is not None

    def execute(self, context):
        b_root = _decal_root(context)
        store = b_root.nif_object.bs_decal_placement
        b_data = store.add()
        b_data.vector_blocks.add()
        b_root.nif_object.decal_placement_index = len(store) - 1
        return {'FINISHED'}


class NifDecalPlacementRemove(Operator):
    """Remove the active extra data block and all of its viewport handles."""

    bl_idname = "object.nif_decal_placement_remove"
    bl_label = "Remove Decal Placement Data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and bool(b_root.nif_object.bs_decal_placement)

    def execute(self, context):
        b_root = _decal_root(context)
        store = b_root.nif_object.bs_decal_placement
        index = min(b_root.nif_object.decal_placement_index, len(store) - 1)
        for b_vector_block in store[index].vector_blocks:
            _remove_point_helpers(b_vector_block.points)
        store.remove(index)
        b_root.nif_object.decal_placement_index = max(0, min(index, len(store) - 1))
        return {'FINISHED'}


class NifDecalVectorBlockAdd(Operator):
    """Add a vector block to the active decal extra data."""

    bl_idname = "object.nif_decal_vector_block_add"
    bl_label = "Add Decal Vector Block"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and _active_decal_data(b_root) is not None

    def execute(self, context):
        b_data = _active_decal_data(_decal_root(context))
        b_data.vector_blocks.add()
        b_data.vector_block_index = len(b_data.vector_blocks) - 1
        return {'FINISHED'}


class NifDecalVectorBlockRemove(Operator):
    """Remove the active vector block and its viewport handles."""

    bl_idname = "object.nif_decal_vector_block_remove"
    bl_label = "Remove Decal Vector Block"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        b_data = _active_decal_data(b_root) if b_root else None
        return b_data is not None and bool(b_data.vector_blocks)

    def execute(self, context):
        b_data = _active_decal_data(_decal_root(context))
        index = min(b_data.vector_block_index, len(b_data.vector_blocks) - 1)
        _remove_point_helpers(b_data.vector_blocks[index].points)
        b_data.vector_blocks.remove(index)
        b_data.vector_block_index = max(0, min(index, len(b_data.vector_blocks) - 1))
        return {'FINISHED'}


class NifDecalPointAdd(Operator):
    """Add a decal point at the 3D cursor with a +Z normal."""

    bl_idname = "object.nif_decal_point_add"
    bl_label = "Add Decal Point at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and _active_vector_block(b_root) is not None

    def execute(self, context):
        b_root = _decal_root(context)
        b_point = b_root.matrix_world.inverted_safe() @ context.scene.cursor.location
        _add_decal_point(b_root, _active_vector_block(b_root), b_point, (0.0, 0.0, 1.0))
        return {'FINISHED'}


class NifDecalPointPick(Operator):
    """Click a mesh surface to add a decal point aligned to its normal."""

    bl_idname = "object.nif_decal_point_pick"
    bl_label = "Pick Decal Point on Surface"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and _active_vector_block(b_root) is not None

    def invoke(self, context, event):
        self._root = _decal_root(context)
        self._data_index = self._root.nif_object.decal_placement_index
        self._block_index = _active_decal_data(self._root).vector_block_index
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('CROSSHAIR')
        context.workspace.status_text_set(
            "Decal placement: click a mesh surface to add a point, Esc or right-click to cancel")
        return {'RUNNING_MODAL'}

    @staticmethod
    def _view_region(context, event):
        for area in context.screen.areas:
            if not (area.x <= event.mouse_x < area.x + area.width
                    and area.y <= event.mouse_y < area.y + area.height):
                continue
            if area.type != 'VIEW_3D':
                return None, None, None
            region = next((item for item in area.regions
                           if item.type == 'WINDOW'
                           and item.x <= event.mouse_x < item.x + item.width
                           and item.y <= event.mouse_y < item.y + item.height), None)
            return area, region, area.spaces.active.region_3d if region else None
        return None, None, None

    def _finish(self, context, result):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        return result

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return self._finish(context, {'CANCELLED'})
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}

        area, region, region_3d = self._view_region(context, event)
        if region is None:
            self.report({'INFO'}, "Click inside a 3D View, or press Esc to cancel")
            return {'RUNNING_MODAL'}

        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
        ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)
        hit, location, normal, _face_index, _hit_obj, _matrix = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), ray_origin, ray_direction)
        if not hit:
            self.report({'INFO'}, "No mesh surface under the cursor")
            return {'RUNNING_MODAL'}

        b_local_point = self._root.matrix_world.inverted_safe() @ location
        b_local_normal = self._root.matrix_world.to_3x3().inverted_safe() @ normal
        if b_local_normal.length:
            b_local_normal.normalize()
        else:
            b_local_normal = mathutils.Vector((0.0, 0.0, 1.0))

        store = self._root.nif_object.bs_decal_placement
        if self._data_index >= len(store):
            return self._finish(context, {'CANCELLED'})
        b_data = store[self._data_index]
        if self._block_index >= len(b_data.vector_blocks):
            return self._finish(context, {'CANCELLED'})
        _add_decal_point(
            self._root, b_data.vector_blocks[self._block_index], b_local_point, b_local_normal)
        return self._finish(context, {'FINISHED'})


class NifDecalPointRemove(Operator):
    """Remove the active decal point and its viewport handle."""

    bl_idname = "object.nif_decal_point_remove"
    bl_label = "Remove Decal Point"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        b_vector_block = _active_vector_block(b_root) if b_root else None
        return b_vector_block is not None and bool(b_vector_block.points)

    def execute(self, context):
        b_vector_block = _active_vector_block(_decal_root(context))
        index = min(b_vector_block.point_index, len(b_vector_block.points) - 1)
        b_helper = b_vector_block.points[index].helper
        if b_helper is not None:
            bpy.data.objects.remove(b_helper, do_unlink=True)
        b_vector_block.points.remove(index)
        b_vector_block.point_index = max(0, min(index, len(b_vector_block.points) - 1))
        return {'FINISHED'}


class NifDecalPointSelect(Operator):
    """Select the active point's arrow handle in the 3D viewport."""

    bl_idname = "object.nif_decal_point_select"
    bl_label = "Select Decal Point"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        b_vector_block = _active_vector_block(b_root) if b_root else None
        if b_vector_block is None or not b_vector_block.points:
            return False
        index = min(b_vector_block.point_index, len(b_vector_block.points) - 1)
        return b_vector_block.points[index].helper is not None

    def execute(self, context):
        b_vector_block = _active_vector_block(_decal_root(context))
        index = min(b_vector_block.point_index, len(b_vector_block.points) - 1)
        decal.select_helper(b_vector_block.points[index].helper, context)
        return {'FINISHED'}


class NifDecalRootSelect(Operator):
    """Return from a point handle to the root that owns its decal data."""

    bl_idname = "object.nif_decal_root_select"
    bl_label = "Select Decal Root"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return decal.is_decal_helper(context.object) and _decal_root(context) is not None

    def execute(self, context):
        decal.select_helper(_decal_root(context), context)
        return {'FINISHED'}


classes = [
    BSFurnitureMarkerAdd,
    BSFurnitureMarkerRemove,
    FurniturePositionAdd,
    FurniturePositionRemove,
    NifMultiBoundAdd,
    NifMultiBoundRemove,
    NifDecalPlacementAdd,
    NifDecalPlacementRemove,
    NifDecalVectorBlockAdd,
    NifDecalVectorBlockRemove,
    NifDecalPointAdd,
    NifDecalPointPick,
    NifDecalPointRemove,
    NifDecalPointSelect,
    NifDecalRootSelect
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
