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



import math

import bpy
import mathutils
from bpy.types import Operator

from .. import properties
from ..utils.decorators import register_classes, unregister_classes
from ..utils import decal
from ..utils.particles import nif_to_blender_units


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
    return store[0] if store else None


def _active_vector_block(b_root):
    b_data = _active_decal_data(b_root)
    if b_data is None or not b_data.vector_blocks:
        return None
    index = min(b_data.vector_block_index, len(b_data.vector_blocks) - 1)
    return b_data.vector_blocks[index]


def _block_index(b_root, b_vector_block):
    b_data = _active_decal_data(b_root)
    for index, b_candidate in enumerate(b_data.vector_blocks):
        if b_candidate == b_vector_block:
            return index
    return 0


def _remove_point_helpers(b_points):
    for b_point in b_points:
        if b_point.helper is not None:
            bpy.data.objects.remove(b_point.helper, do_unlink=True)


def _center_line_frame(b_axis):
    """Two axes perpendicular to an axis."""

    b_across = b_axis.cross(mathutils.Vector((0.0, 0.0, 1.0)) if abs(b_axis.z) < 0.9
                            else mathutils.Vector((1.0, 0.0, 0.0)))
    b_across.normalize()
    return b_across, b_axis.cross(b_across)


def _aim_at_target(b_root, b_data, point):
    """The normal aiming a vector at the nearest point of the decal volume, or None."""

    if b_data is None or b_data.target is None:
        return None
    b_mesh = b_data.target
    b_to_local = b_mesh.matrix_world.inverted_safe() @ b_root.matrix_world
    hit, b_at, _normal, _index = b_mesh.closest_point_on_mesh(b_to_local @ mathutils.Vector(point))
    if not hit:
        return None
    b_normal = (b_root.matrix_world.inverted_safe()
                @ (b_mesh.matrix_world @ b_at)) - mathutils.Vector(point)
    return b_normal if b_normal.length > decal.NORMAL_EPSILON else None


def _add_decal_point(b_root, b_vector_block, point, normal, select=True, b_group=None):
    index = len(b_vector_block.points)
    if b_group is None:
        b_group = decal.vector_group(b_root, _block_index(b_root, b_vector_block))
    b_helper = decal.create_point_helper(
        b_root, point, normal, decal.next_vector_name(b_group), b_parent=b_group)
    b_vector_block.points.add().helper = b_helper
    b_vector_block.point_index = index
    if select:
        decal.select_helper(b_helper)
    return b_helper


class NifDecalPlacementAdd(Operator):
    """Add a BSDecalPlacementVectorExtraData block with one empty vector block."""

    bl_idname = "object.nif_decal_placement_add"
    bl_label = "Add Decal Placement Data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and not b_root.nif_object.bs_decal_placement

    def execute(self, context):
        b_root = _decal_root(context)
        b_data = b_root.nif_object.bs_decal_placement.add()
        b_data.vector_blocks.add()
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
        for b_vector_block in store[0].vector_blocks:
            _remove_point_helpers(b_vector_block.points)
        store.clear()
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
    """Add a decal vector at the 3D cursor, aimed at the decal volume."""

    bl_idname = "object.nif_decal_point_add"
    bl_label = "Add Vector at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        return b_root is not None and _active_vector_block(b_root) is not None

    def execute(self, context):
        b_root = _decal_root(context)
        b_data = _active_decal_data(b_root)
        b_point = b_root.matrix_world.inverted_safe() @ context.scene.cursor.location
        b_normal = _aim_at_target(b_root, b_data, b_point)
        if b_normal is None:
            self.report({'WARNING'}, "Set a decal volume mesh to aim the vector at")
            b_normal = mathutils.Vector((0.0, 0.0, 1.0))
        _add_decal_point(b_root, _active_vector_block(b_root), b_point, b_normal)
        return {'FINISHED'}


class NifDecalGenerate(Operator):
    """Build three groups of vectors covering the decal volume from three directions.

    Each vector is a hitscan. Its tail is where a decal is thrown from and its head is where
    that decal lands, so the landing points are scattered over the volume as a poisson disc
    to cover as much of the surface as the count allows.
    """

    bl_idname = "object.nif_decal_generate"
    bl_label = "Generate Vectors"
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(
        name="Vectors Per Group",
        description="How many vectors each group holds. Vanilla weapons use seven",
        default=7, min=1, max=64
    )

    distance: bpy.props.FloatProperty(
        name="Distance",
        description="How far the vectors sit from the decal volume, in nif units. Zero "
                    "picks a distance from the size of the volume",
        default=0.0, min=0.0
    )

    spread: bpy.props.FloatProperty(
        name="Spread",
        description="How wide a cone of directions each group covers",
        default=0.44, min=0.0, max=1.4, subtype='ANGLE'
    )

    @classmethod
    def poll(cls, context):
        b_root = _decal_root(context)
        b_data = _active_decal_data(b_root) if b_root else None
        return b_data is not None and b_data.target is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        b_root = _decal_root(context)
        b_data = _active_decal_data(b_root)
        b_axes = decal.mesh_axes(b_root, b_data.target)
        if b_axes is None:
            self.report({'ERROR'}, f"'{b_data.target.name}' has no geometry")
            return {'CANCELLED'}
        b_center, b_mesh_axes, radius = b_axes
        distance = (nif_to_blender_units(self.distance) if self.distance
                    else max(radius, decal.NORMAL_EPSILON))

        for b_vector_block in b_data.vector_blocks:
            _remove_point_helpers(b_vector_block.points)
        b_data.vector_blocks.clear()

        # the two sides of the weapon and its tip, which is where vanilla puts its groups
        b_directions = (b_mesh_axes[1], -b_mesh_axes[1], b_mesh_axes[0])
        placed = 0
        for index, b_direction in enumerate(b_directions):
            b_vector_block = b_data.vector_blocks.add()
            b_group = decal.vector_group(b_root, index)
            placed += self._fill(b_root, b_data, b_group, b_vector_block, b_direction, distance)

        b_data.vector_block_index = 0
        if not placed:
            self.report({'ERROR'}, f"No part of '{b_data.target.name}' could be reached")
            return {'CANCELLED'}
        decal.highlight_helpers([b_point.helper for b_block in b_data.vector_blocks
                                 for b_point in b_block.points])
        self.report({'INFO'}, f"Generated {placed} decal vectors in "
                              f"{len(b_data.vector_blocks)} groups")
        return {'FINISHED'}

    def _fill(self, b_root, b_data, b_group, b_vector_block, b_direction, distance):
        b_triangles = decal.facing_triangles(b_root, b_data.target, b_direction)
        b_samples = decal.poisson_samples(b_triangles, self.count)
        b_across, b_up = _center_line_frame(b_direction)

        for index, b_sample in enumerate(b_samples):
            b_point = b_sample + self._offset(index, b_direction, b_across, b_up) * distance
            _add_decal_point(b_root, b_vector_block, b_point, b_sample - b_point,
                             select=False, b_group=b_group)
        return len(b_samples)

    def _offset(self, index, b_direction, b_across, b_up):
        # golden angle, so the cone of directions fills in evenly as the count rises
        angle = index * 2.399963
        tilt = self.spread * math.sqrt(index / max(1, self.count - 1))
        return (b_direction * math.cos(tilt)
                + (b_across * math.cos(angle) + b_up * math.sin(angle)) * math.sin(tilt))


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
    NifDecalGenerate,
    NifDecalPointRemove,
    NifDecalPointSelect,
    NifDecalRootSelect
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
