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
from bpy.types import Panel
from bpy.types import UIList

from ..properties.object import (BSX_FLAG_BITS, OBJECT_FLAG_BITS,
                                                 SWITCH_NODE_FLAG_BITS, VALUE_NODE_FLAG_BITS)
from ..utils.decorators import register_classes, unregister_classes
from ..utils import decal
from ..utils.flags import draw_bit_bools

# Node types built on BSRangeNode, which is where their damage stage range comes from
RANGE_NODE_TYPES = {'BSRangeNode', 'BSBlastNode', 'BSDamageStage', 'BSDebrisNode'}

# What each destruction node's damage stage range actually controls, for the panel
RANGE_NODE_DESCRIPTIONS = {
    'BSBlastNode': "Where the explosion is placed over this damage stage range",
    'BSDamageStage': "Children shown over this damage stage range",
    'BSDebrisNode': "Where debris spawns over this damage stage range",
}

# Node types that carry NiSwitchNode's fields, whether directly or by inheriting them
SWITCH_NODE_TYPES = {'NiSwitchNode', 'NiLODNode'}


def is_nif_node(b_obj):
    """Whether this object is exported as a node, and so has a node type to configure."""

    return b_obj.type in ('EMPTY', 'ARMATURE') and not decal.is_decal_helper(b_obj)


class ObjectButtonsPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    @staticmethod
    def is_root_object(b_obj):
        return b_obj.parent is None

class ObjectPanel(ObjectButtonsPanel):
    bl_label = "NifTools Object"
    bl_idname = "NIFTOOLS_PT_ObjectPanel"

    # noinspection PyUnusedLocal
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        b_obj = context.object
        nif_obj_props = b_obj.nif_object

        layout = self.layout
        row = layout.column()
        if is_nif_node(b_obj) and b_obj.type == "EMPTY":
            # the fields each node type adds are drawn by ObjectNodeTypePanel below
            row.prop(nif_obj_props, "nodetype")
            row.prop(nif_obj_props, "upb")
        if self.is_root_object(b_obj) and b_obj.type != "ARMATURE":
            # prn nistringextradata is only useful as replacement for rigging data
            row.prop(nif_obj_props, "prn_location")
        if b_obj.type == "MESH":
            # consistency flags only exist for NiGeometry
            row.prop(nif_obj_props, "consistency_flags")

        parent = b_obj.parent
        if parent and parent.type == 'ARMATURE':
            row.prop_search(nif_obj_props, "skeleton_root", parent.data, "bones")


class ObjectNodeTypePanel(ObjectButtonsPanel):
    """The fields the chosen node type adds on top of a plain NiNode."""

    bl_label = "Node Type"
    bl_idname = "NIFTOOLS_PT_ObjectNodeTypePanel"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"

    @classmethod
    def poll(cls, context):
        b_obj = context.object
        if not is_nif_node(b_obj):
            return False
        nodetype = b_obj.nif_object.nodetype
        return (nodetype in RANGE_NODE_TYPES or nodetype in SWITCH_NODE_TYPES
                or nodetype in ('BSValueNode', 'BSOrderedNode', 'NiSortAdjustNode',
                                'BSMultiBoundNode', 'NiBillboardNode'))

    def draw(self, context):
        nif_obj_props = context.object.nif_object
        nodetype = nif_obj_props.nodetype

        layout = self.layout

        if nodetype in RANGE_NODE_TYPES:
            description = RANGE_NODE_DESCRIPTIONS.get(nodetype)
            if description:
                layout.label(text=description, icon='INFO')
            column = layout.column(align=True)
            column.prop(nif_obj_props.node_range, "min")
            column.prop(nif_obj_props.node_range, "max")
            column.prop(nif_obj_props.node_range, "current")

        if nodetype == 'BSValueNode':
            layout.prop(nif_obj_props.node_value, "value")
            draw_bit_bools(layout, nif_obj_props.node_value, VALUE_NODE_FLAG_BITS, columns=1)

        if nodetype == 'BSOrderedNode':
            layout.prop(nif_obj_props.node_ordered, "alpha_sort_bound")
            layout.prop(nif_obj_props.node_ordered, "static_bound")

        if nodetype == 'NiSortAdjustNode':
            layout.prop(nif_obj_props.node_sort_adjust, "sorting_mode")

        if nodetype == 'BSMultiBoundNode':
            if bpy.context.scene.niftools_scene.is_skyrim():
                layout.prop(nif_obj_props.node_multi_bound, "culling_mode")
            self.draw_multi_bound(layout, context.object)

        if nodetype in SWITCH_NODE_TYPES:
            layout.prop(nif_obj_props.node_switch, "index")
            draw_bit_bools(layout, nif_obj_props.node_switch, SWITCH_NODE_FLAG_BITS, columns=1)

        if nodetype == 'NiBillboardNode':
            layout.prop(nif_obj_props, "billboard_mode")

    @staticmethod
    def draw_multi_bound(layout, b_obj):
        """Show the bound helper child, or offer to add one."""

        b_helper = next((b_child for b_child in b_obj.children
                         if b_child.nif_object.node_multi_bound.is_bound_helper), None)

        box = layout.box()
        if b_helper is None:
            box.label(text="No bound", icon='MESH_CUBE')
            box.operator("object.nif_multi_bound_add", icon='ADD')
            return

        row = box.row(align=True)
        row.label(text=b_helper.name, icon='MESH_CUBE')
        row.operator("object.nif_multi_bound_remove", icon='X', text="")
        box.prop(b_helper.nif_object.node_multi_bound, "bound_type")
        box.label(text="Move and scale the helper to set the bound")


class ObjectLODLevelsPanel(ObjectButtonsPanel):
    """The distance range each child of a NiLODNode is the visible level over."""

    bl_label = "LOD Levels"
    bl_idname = "NIFTOOLS_PT_ObjectLODLevelsPanel"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"

    @classmethod
    def poll(cls, context):
        return is_nif_node(context.object) and context.object.nif_object.nodetype == 'NiLODNode'

    def draw(self, context):
        b_obj = context.object
        node_lod = b_obj.nif_object.node_lod

        layout = self.layout
        layout.prop(node_lod, "lod_type")

        if node_lod.lod_type == 'NiScreenLODData':
            if node_lod.screen_lod_data:
                layout.label(text="Screen LOD data is written back unchanged", icon='INFO')
            else:
                layout.label(text="No screen LOD data on this node", icon='ERROR')
            return

        layout.prop(node_lod, "lod_center")

        b_children = [b_child for b_child in b_obj.children
                      if not b_child.nif_object.node_multi_bound.is_bound_helper]
        if not b_children:
            layout.label(text="Parent the levels to this node", icon='INFO')
            return

        layout.label(text="Levels are matched to children in order")
        for level_index, b_child in enumerate(b_children):
            box = layout.box()
            box.label(text=f"{level_index}: {b_child.name}", icon='OBJECT_DATA')
            row = box.row(align=True)
            row.prop(b_child.nif_object.lod_level, "near_extent")
            row.prop(b_child.nif_object.lod_level, "far_extent")


class ObjectFlagsPanel(ObjectButtonsPanel):
    bl_label = "Object Flags"
    bl_idname = "NIFTOOLS_PT_ObjectFlagsPanel"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_bit_bools(self.layout, context.object.nif_object, OBJECT_FLAG_BITS)


class ObjectBSXFlagsPanel(ObjectButtonsPanel):
    bl_label = "BSX Flags"
    bl_idname = "NIFTOOLS_PT_ObjectBSXFlagsPanel"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # BSXFlags is a Bethesda block, and only ever sits on the root
        return cls.is_root_object(context.object) and bpy.context.scene.niftools_scene.is_bs()

    def draw(self, context):
        draw_bit_bools(self.layout, context.object.nif_object, BSX_FLAG_BITS)


class ObjectBSFurnitureMarkerPanel(ObjectButtonsPanel):
    bl_label = "Furniture Marker"
    bl_idname = "NIFTOOLS_PT_ObjectBSFurnitureMarker"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # a furniture marker sits on the root of a piece of furniture, never on a skeleton
        return cls.is_root_object(context.object) and context.object.type != 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        row = layout.row()

        bs_furniture_marker = context.object.nif_object.bs_furniture_marker

        if not bs_furniture_marker:
            row.operator("object.bs_furniture_marker_add", icon='ADD', text="")
        else:
            row.operator("object.bs_furniture_marker_remove", icon='REMOVE', text="")

        col = row.column(align=True)

        for i, x in enumerate(bs_furniture_marker):
            col = layout.column()
            col.label(text="Positions")

            row = col.row()
            row.template_list(
                    "NIFTOOLS_UL_FurniturePositions",
                         "",
                               bs_furniture_marker[i],
                      "positions",
                                bs_furniture_marker[i],
                  "position_index")

            # Add/Remove operators
            col = row.column(align=True)
            col.operator("object.furniture_position_add", icon='ADD', text="")

            has_positions = len(bs_furniture_marker[i].positions) > 0

            if has_positions:
                col.operator("object.furniture_position_remove", icon='REMOVE', text="")

            if has_positions:
                layout.row()
                box = layout.box()
                selected_position = bs_furniture_marker[i].positions[bs_furniture_marker[i].position_index]

                box.prop(selected_position, "offset_x")
                box.prop(selected_position, "offset_y")
                box.prop(selected_position, "offset_z")
                box.prop(selected_position, "orientation")
                box.prop(selected_position, "position_ref_1")
                box.prop(selected_position, "position_ref_2")

class ObjectFurniturePositionsList(UIList):
    bl_label = "Positions"
    bl_idname = "NIFTOOLS_UL_FurniturePositions"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.2)
        split.label(text=str(index))
        split.prop(item, "data", text="", emboss=False, translate=False, icon='BORDERMOVE')

class ObjectBSInvMarkerPanel(ObjectButtonsPanel):
    bl_label = "Inventory Marker"
    bl_idname = "NIFTOOLS_PT_ObjectBSInvMarker"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # BSInvMarker only exists from Skyrim on, which is also the only case the exporter
        # writes one for
        return cls.is_root_object(context.object) and bpy.context.scene.niftools_scene.is_skyrim()

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        bs_inv = context.object.nif_object.bs_inv
        if not bs_inv:
            row.operator("object.bs_inv_marker_add", icon='ADD', text="")
        else:
            row.operator("object.bs_inv_marker_remove", icon='REMOVE', text="")
        col = row.column(align=True)
        for i, x in enumerate(bs_inv):
            col.prop(bs_inv[i], "x", index=i)
            col.prop(bs_inv[i], "y", index=i)
            col.prop(bs_inv[i], "z", index=i)
            col.prop(bs_inv[i], "zoom", index=i)


class ObjectDecalPlacementList(UIList):
    bl_idname = "NIFTOOLS_UL_DecalPlacement"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='EMPTY_AXIS')


class ObjectDecalVectorBlocksList(UIList):
    bl_idname = "NIFTOOLS_UL_DecalVectorBlocks"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=f"Vector Block {index + 1}  ({len(item.points)} points)",
                     icon='GROUP_VERTEX')


class ObjectDecalPointsList(UIList):
    bl_idname = "NIFTOOLS_UL_DecalPoints"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if item.helper is None:
            layout.label(text=f"Point {index + 1} (missing handle)", icon='ERROR')
        else:
            layout.prop(item.helper, "name", text="", emboss=False, icon='EMPTY_SINGLE_ARROW')


class ObjectDecalPlacementPanel(ObjectButtonsPanel):
    bl_label = "Decal Placement"
    bl_idname = "NIFTOOLS_PT_ObjectDecalPlacement"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        b_obj = context.object
        game = bpy.context.scene.niftools_scene
        return (b_obj is not None and b_obj.parent is None and is_nif_node(b_obj)
                and (game.is_fo3() or game.is_skyrim()))

    def draw(self, context):
        layout = self.layout
        b_root = context.object
        nif_object = b_root.nif_object
        store = nif_object.bs_decal_placement

        row = layout.row()
        row.template_list("NIFTOOLS_UL_DecalPlacement", "", nif_object,
                          "bs_decal_placement", nif_object, "decal_placement_index", rows=2)
        buttons = row.column(align=True)
        buttons.operator("object.nif_decal_placement_add", icon='ADD', text="")
        buttons.operator("object.nif_decal_placement_remove", icon='REMOVE', text="")

        if not store:
            layout.label(text="Add data, then pick points directly on a mesh surface.",
                         icon='INFO')
            return

        data_index = min(nif_object.decal_placement_index, len(store) - 1)
        b_data = store[data_index]
        box = layout.box()
        box.prop(b_data, "name")
        box.prop(b_data, "float_data")

        row = layout.row()
        row.template_list("NIFTOOLS_UL_DecalVectorBlocks", "", b_data,
                          "vector_blocks", b_data, "vector_block_index", rows=2)
        buttons = row.column(align=True)
        buttons.operator("object.nif_decal_vector_block_add", icon='ADD', text="")
        buttons.operator("object.nif_decal_vector_block_remove", icon='REMOVE', text="")

        if not b_data.vector_blocks:
            layout.label(text="Add a vector block before adding points.", icon='INFO')
            return

        block_index = min(b_data.vector_block_index, len(b_data.vector_blocks) - 1)
        b_vector_block = b_data.vector_blocks[block_index]
        row = layout.row()
        row.template_list("NIFTOOLS_UL_DecalPoints", "", b_vector_block,
                          "points", b_vector_block, "point_index", rows=4)
        buttons = row.column(align=True)
        buttons.operator("object.nif_decal_point_pick", icon='EYEDROPPER', text="")
        buttons.operator("object.nif_decal_point_add", icon='ADD', text="")
        buttons.operator("object.nif_decal_point_remove", icon='REMOVE', text="")
        buttons.separator()
        buttons.operator("object.nif_decal_point_select", icon='RESTRICT_SELECT_OFF', text="")

        layout.label(text="Eyedropper: click a mesh to place and align an arrow.",
                     icon='INFO')
        layout.label(text="Move the arrow origin for the point. Rotate its +Z axis for the normal.")

        if not b_vector_block.points:
            return
        point_index = min(b_vector_block.point_index, len(b_vector_block.points) - 1)
        b_point = b_vector_block.points[point_index]
        detail = layout.box()
        if b_point.helper is None:
            detail.label(text="This point's viewport handle was deleted.", icon='ERROR')
        else:
            detail.prop(b_point.helper, "location", text="Point")
            detail.prop(b_point.helper, "rotation_euler", text="Normal Rotation")
        detail.prop(b_point, "normal_length")


class ObjectDecalPointPanel(ObjectButtonsPanel):
    """A compact return path while the viewport arrow itself is selected."""

    bl_label = "Decal Point"
    bl_idname = "NIFTOOLS_PT_ObjectDecalPoint"
    bl_parent_id = "NIFTOOLS_PT_ObjectPanel"

    @classmethod
    def poll(cls, context):
        return decal.is_decal_helper(context.object)

    def draw(self, context):
        b_helper = context.object
        layout = self.layout
        layout.label(text="Origin = point, local +Z = normal", icon='EMPTY_SINGLE_ARROW')
        layout.prop(b_helper, "location", text="Point")
        layout.prop(b_helper, "rotation_euler", text="Normal Rotation")
        layout.prop(b_helper.nif_object, "decal_placement_root", text="Root")
        layout.operator("object.nif_decal_root_select", icon='FILE_PARENT')


classes = [
    ObjectPanel,
    ObjectNodeTypePanel,
    ObjectLODLevelsPanel,
    ObjectFlagsPanel,
    ObjectBSXFlagsPanel,
    ObjectFurniturePositionsList,
    ObjectBSFurnitureMarkerPanel,
    ObjectBSInvMarkerPanel,
    ObjectDecalPlacementList,
    ObjectDecalVectorBlocksList,
    ObjectDecalPointsList,
    ObjectDecalPlacementPanel,
    ObjectDecalPointPanel
]

def register():
    register_classes(classes, __name__)

def unregister():
    unregister_classes(classes, __name__)
