""" Nif User Interface, custom nif properties for objects"""

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
from bpy.props import (StringProperty,
                       IntProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty, FloatVectorProperty, CollectionProperty
                       )
from bpy.types import PropertyGroup
from ..utils import decal
from ..utils.decorators import register_classes, unregister_classes
from ..utils.flags import bits_of, inject_bit_bools, named_bits
from nifgen.formats.nif import classes as NifClasses

OBJECT_FLAG_BITS = named_bits((
    'app_culled',
    'selective_update',
    'selective_update_transforms',
    'selective_update_controller',
    'selective_update_rigid',
    'display_object',
    'disable_sorting',
    'selective_update_transforms_override',
    'unk_8',
    'trans_is_identity',
    'no_decals',
    'always_draw',
    'preprocessed_node',
    'fixed_bound',
    'faded_in',
    'ignore_fade',
    ('lod_fading_out', 'LOD Fading Out'),
    'has_moving_sound',
    'has_property_controller',
    'has_bound',
    'not_visible',
    'ignores_picking',
    'world_bound_change',
    'no_shadows',
    'high_detail',
    'unk_25',
    'unk_26',
    'player_bone',
    'imposter_loaded',
    'unk_29',
    'unk_30',
    'unk_31',
), {
    'app_culled': 'Permanently culls the object. No effect on a root node unless set through '
                  'SetNifBlockFlag',
    'selective_update': 'Allows selective updates. Managed by the engine',
    'selective_update_transforms': 'Allows transform controller update. Managed by the engine',
    'selective_update_controller': 'Allows controller update. Managed by the engine',
    'selective_update_rigid': 'Forces a more tightly controlled update method. Managed by the engine',
    'display_object': 'Used only by sky objects. Managed by the engine',
    'disable_sorting': 'Unused. The game does not use Gamebryo\'s geometry sorters',
    'selective_update_transforms_override': 'Forces transform updates even with no transform '
                                            'controllers. Managed by the engine',
    'unk_8': 'Unused',
    'trans_is_identity': 'Ignores local transforms on the geometry. Setting it on a root node or '
                         'a mesh turns it invisible',
    'no_decals': 'Disallows impact decals such as bullet holes. Root node only',
    'always_draw': 'Forces light inclusion and skips culling',
    'preprocessed_node': 'Marks actor nodes for actor culling. Managed by the engine',
    'fixed_bound': 'Prevents bound updates. Culling behaves erratically when on',
    'faded_in': 'BSFadeNode only. Marks the fade state. Managed by the engine',
    'ignore_fade': 'BSFadeNode only. Disables fading',
    'lod_fading_out': 'BSFadeNode only. Unused',
    'has_moving_sound': 'Marks a sound to reference connection. Managed by the engine',
    'has_property_controller': 'Marks the presence of a property controller. Managed by the engine',
    'has_bound': 'Marks the presence of a bound. Managed by the engine',
    'not_visible': 'Used for actor culling. Managed by the engine',
    'ignores_picking': 'Disables activation prompts. Removed at runtime, so only useful through '
                       'SetNifBlockFlag',
    'world_bound_change': 'Forces multibound reevaluation. Managed by the engine',
    'no_shadows': 'Managed by the engine',
    'high_detail': 'BSFadeNode only. Unused',
    'unk_25': 'Unused',
    'unk_26': 'Unused',
    'player_bone': 'Marks the player\'s bones. Managed by the engine',
    'imposter_loaded': 'BSFadeNode only. Overrides fading for the imposter state. Managed by the engine',
})

BSX_FLAG_BITS = named_bits((
    'animated',
    'havok',
    'ragdoll',
    'complex',
    'addon',
    'editor_marker',
    'dynamic',
    'articulated',
    'needs_transform_updates',
    'external_emit',
), {
    'animated': 'Tick if the NIF has embedded non-material animations',
    'havok': 'Tick if the NIF has collision',
    'ragdoll': 'Seemingly unused',
    'complex': 'Indicates if NIF has multiple dynamic collision objects. If set alongside Dynamic, game uses Actor\'s custom ragdoll data for initial bone positions when loaded, even if Actor is not dead or unconscious',
    'addon': 'Indicates if a NIF can have AddOnNodes attached',
    'editor_marker': 'Hides Nodes named EditorMarker and their children',
    'dynamic': 'For actors if set alongside Complex, game uses Actor\'s custom ragdoll data for initial bone positions when loaded, even if Actor is not dead or unconscious',
    'articulated': 'Applies velocity equally to all bones of a grabbed object. Makes objects like armor ground models move cleanly',
    'needs_transform_updates': 'Technically unused, meant for a broken grab IK system that lacks animations',
    'external_emit': 'Seemingly unused in FO3 and later, appears to be a holdover from Oblivion which lacked shader properties. Set the External_Emit flag on shader properties instead',
})


# NiSwitchNode.Switch Node Flags, inherited by NiLODNode
SWITCH_NODE_FLAG_BITS = bits_of(NifClasses.NiSwitchFlags, {
    'update_only_active_child': 'Only update the child the node currently switched to, '
                                'rather than every child',
    'update_controllers': 'Keep updating controllers on children that are not active',
})

# BSValueNode.Value Node Flags
VALUE_NODE_FLAG_BITS = bits_of(NifClasses.BSValueNodeFlags, {
    'billboard_world_z': 'Billboard the attached addon around the world Z axis',
    'use_player_adjust': 'Apply the player adjustment to the attached addon',
})


class NodeRangeProperty(PropertyGroup):
    """BSRangeNode fields, shared by the destruction nodes that derive from it.

    On BSBlastNode, BSDamageStage and BSDebrisNode these are the damage stage range over
    which the node's children are active.
    """

    min: IntProperty(
        name='Min',
        description='Lowest damage stage this node is active for',
        default=0,
        min=0,
        max=255
    )

    max: IntProperty(
        name='Max',
        description='Highest damage stage this node is active for',
        default=0,
        min=0,
        max=255
    )

    current: IntProperty(
        name='Current',
        description='Damage stage the node is currently at. The game sets this at runtime',
        default=0,
        min=0,
        max=255
    )


class NodeValueProperty(PropertyGroup):
    """BSValueNode fields, which attach an AddOnNode form to the nif."""

    value: IntProperty(
        name='Value',
        description='Index of the AddOnNode form attached at this node',
        default=0,
        min=0
    )

    # Storage behind the value node flag checkboxes
    value_node_flags: IntProperty(
        name='Value Node Flags',
        default=0,
        min=0,
        max=255
    )


class NodeOrderedProperty(PropertyGroup):
    """BSOrderedNode fields, which redefine the alpha bound of the subtree below the node."""

    alpha_sort_bound: FloatVectorProperty(
        name='Alpha Sort Bound',
        description='Bound used to sort the alpha blended children of this node',
        size=4,
        default=(0.0, 0.0, 0.0, 0.0)
    )

    static_bound: BoolProperty(
        name='Static Bound',
        description='Treat the alpha sort bound as fixed rather than recomputing it',
        default=True
    )


class NodeSwitchProperty(PropertyGroup):
    """NiSwitchNode fields, inherited by NiLODNode."""

    index: IntProperty(
        name='Active Child',
        description='Index of the child the node is currently switched to',
        default=0,
        min=0
    )

    # Storage behind the switch flag checkboxes
    switch_node_flags: IntProperty(
        name='Switch Node Flags',
        default=0,
        min=0,
        max=65535
    )


class NodeLODProperty(PropertyGroup):
    """NiLODNode fields, on top of the NiSwitchNode ones it inherits."""

    lod_type: EnumProperty(
        name='LOD Data',
        description='Which data block decides when the node switches level',
        items=(
            ('NiRangeLODData', 'Range', "Switch on distance from the camera", 0),
            ('NiScreenLODData', 'Screen', "Switch on the proportion of the screen filled", 1),
        ),
        default='NiRangeLODData'
    )

    lod_center: FloatVectorProperty(
        name='LOD Center',
        description='Point the switching distances are measured from, in node space',
        subtype='XYZ',
        size=3,
        default=(0.0, 0.0, 0.0)
    )

    # Screen LOD switches on bounding spheres and screen proportions rather than on a range
    # per child, so there is nothing on the children to edit and nothing worth a panel for a
    # block this rare. A snapshot keeps it round tripping
    screen_lod_data: StringProperty(
        name='Screen LOD Data',
        description='JSON snapshot of a NiScreenLODData block, written back out unchanged',
        default=''
    )


class NodeSortAdjustProperty(PropertyGroup):
    """NiSortAdjustNode fields, which change how the subtree below is sorted."""

    sorting_mode: EnumProperty(
        name='Sorting Mode',
        description='How this node changes the sorting of the subtree below it',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.SortingMode)],
        default='SORTING_INHERIT'
    )


class NodeLODLevelProperty(PropertyGroup):
    """The distance range over which a child of a NiLODNode is the visible level.

    This lives on the child rather than on the LOD node so that it follows the object when
    it is reordered or reparented; the LOD node's panel gathers its children to show them
    together.
    """

    near_extent: FloatProperty(
        name='Near',
        description='Closest distance at which this child is the visible level',
        default=0.0,
        min=0.0
    )

    far_extent: FloatProperty(
        name='Far',
        description='Furthest distance at which this child is the visible level',
        default=0.0,
        min=0.0
    )


class NodeMultiBoundProperty(PropertyGroup):
    """BSMultiBoundNode fields, and the marker for the helper object holding its bound.

    The bound itself is imported as a child empty rather than as numbers in a panel, so it
    can be seen and dragged in the viewport. Its shape comes straight off that empty's
    transform: location is the center, scale is the extent or radius, and for an oriented
    box the rotation is the box rotation.
    """

    culling_mode: EnumProperty(
        name='Culling Mode',
        description='How the multibound culls the subtree below it. Only written from '
                    'Skyrim on; the Fallout 3 era format has no such field',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.BSCPCullingType)],
        default='CULL_ALLPASS'
    )

    is_bound_helper: BoolProperty(
        name='Multi Bound Helper',
        description='This object is the bound of its parent BSMultiBoundNode rather than a '
                    'node of its own, so it is not exported as a child',
        default=False
    )

    bound_type: EnumProperty(
        name='Bound Type',
        description='Which BSMultiBoundData block this bound is written as',
        items=(
            ('BSMultiBoundAABB', 'AABB', "Axis aligned bounding box", 0),
            ('BSMultiBoundOBB', 'OBB', "Oriented bounding box", 1),
            ('BSMultiBoundSphere', 'Sphere', "Bounding sphere", 2),
        ),
        default='BSMultiBoundAABB'
    )


class FurniturePosition(PropertyGroup):

    offset_x: FloatProperty(
        name="X Offset",
        description="Offset of furniture marker along the X axis",
        default=0
    )

    offset_y: FloatProperty(
        name="Y Offset",
        description="Offset of furniture marker along the Y axis",
        default=0
    )

    offset_z: FloatProperty(
        name="Z Offset",
        description="Offset of furniture marker along the Z axis",
        default=0
    )

    orientation: IntProperty(
        name="Orientation",
        description="Orientation of furniture marker",
        default=0,
        min=0,
        max=65535
    )

    position_ref_1: IntProperty(
        name="Ref 1 Position",
        description="Refers to a furnituremarkerxx.nif file",
        default=0,
        min=0,
        max=255
    )

    position_ref_2: IntProperty(
        name="Ref 2 Position",
        description="Refers to a furnituremarkerxx.nif file",
        default=0,
        min=0,
        max=255
    )

class BSFurnitureMarker(PropertyGroup):
    name: StringProperty(
        name="",
        default='FRN'
    )

    position_index: IntProperty()

    positions: CollectionProperty(
        name="Positions",
        description="Furniture positions",
        type=FurniturePosition
    )

class BsInventoryMarker(PropertyGroup):
    name: StringProperty(
        name="",
        default='INV'
    )

    x: FloatProperty(
        name="X Rotation",
        description="Rotation of object in inventory around the x axis",
        default=0,
        subtype="ANGLE"
    )

    y: FloatProperty(
        name="Y Rotation",
        description="Rotation of object in inventory around the y axis",
        default=0,
        subtype="ANGLE"
    )

    z: FloatProperty(
        name="Z Rotation",
        description="Rotation of object in inventory around the z axis",
        default=0,
        subtype="ANGLE"
    )

    zoom: FloatProperty(
        name="Zoom",
        description="Inventory object Zoom level",
        default=1
    )


class DecalPlacementPoint(PropertyGroup):
    """One point/normal pair, edited through an arrow empty in the viewport."""

    helper: bpy.props.PointerProperty(
        name="Viewport Handle",
        description="Arrow empty whose origin is the point and whose local +Z axis is the normal",
        type=bpy.types.Object
    )


def highlight_active_point(self, context):
    """Select the handle of the point picked in the list."""

    if self.points:
        index = min(self.point_index, len(self.points) - 1)
        decal.highlight_helpers([self.points[index].helper])


def highlight_active_block(self, context):
    """Select the handles of every vector in the block picked in the list."""

    if self.vector_blocks:
        index = min(self.vector_block_index, len(self.vector_blocks) - 1)
        decal.highlight_helpers([b_point.helper
                                 for b_point in self.vector_blocks[index].points])


class DecalVectorBlock(PropertyGroup):
    """One vector block inside BSDecalPlacementVectorExtraData."""

    points: CollectionProperty(
        name="Points",
        description="Paired decal placement points and normals",
        type=DecalPlacementPoint
    )

    point_index: IntProperty(
        name="Active Point",
        default=0,
        min=0,
        update=highlight_active_point
    )


class BSDecalPlacement(PropertyGroup):
    """Editable contents of one BSDecalPlacementVectorExtraData block."""

    target: bpy.props.PointerProperty(
        name="Decal Volume",
        description="Mesh whose faces are the part of the weapon that takes decals. Every "
                    "generated vector lands on it, so leave out anything that should stay "
                    "clean such as the handle",
        type=bpy.types.Object,
        poll=lambda self, b_obj: b_obj.type == 'MESH'
    )

    vector_blocks: CollectionProperty(
        name="Vector Blocks",
        description="Groups of decal placement point/normal pairs",
        type=DecalVectorBlock
    )

    vector_block_index: IntProperty(
        name="Active Vector Block",
        default=0,
        min=0,
        update=highlight_active_block
    )


class ObjectProperty(PropertyGroup):
    nodetype: EnumProperty(
        name='Node Type',
        description='Type of node this empty represents',
        items=(
            ('NiNode', 'NiNode', "", 0),
            ('BSFadeNode', 'BSFadeNode', "", 1),
            ('NiLODNode', 'NiLODNode', "", 2),
            ('NiBillboardNode', 'NiBillboardNode', "", 3),
            ('BSBlastNode', 'BSBlastNode', "", 4),
            ('BSDamageStage', 'BSDamageStage', "", 5),
            ('BSDebrisNode', 'BSDebrisNode', "", 6),
            ('BSMultiBoundNode', 'BSMultiBoundNode', "", 7),
            ('BSOrderedNode', 'BSOrderedNode', "", 8),
            ('BSValueNode', 'BSValueNode', "", 9),
            ('BSMasterParticleSystem', 'BSMasterParticleSystem', "", 10),
            ('RootCollisionNode', 'RootCollisionNode', "", 11),
            ('NiSwitchNode', 'NiSwitchNode', "", 12),
            ('NiSortAdjustNode', 'NiSortAdjustNode', "", 13),
            ('BSRangeNode', 'BSRangeNode', "", 14),
            ('BSLeafAnimNode', 'BSLeafAnimNode', "", 15)),
        default='NiNode',
    )

    billboard_mode: EnumProperty(
        name='Billboard Mode',
        description='The behavior of the billboard node.',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.BillboardMode)],
        default='ALWAYS_FACE_CAMERA',
    )

    prn_location: StringProperty(
        name='PRN',
        description='Attachment point of weapon, armor, or body part. For FO3, Oblivion, and Skyrim'
    )

    consistency_flags: EnumProperty(
        name='Consistency Flag',
        description='Controls animation type',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.ConsistencyType)],
        default = 'CT_STATIC'
    )

    # Storage behind the flag checkboxes. Signed because Blender integers are, so bit 31 of
    # a nif uint lands on the sign bit
    flags: IntProperty(
        name='Object Flags',
        default=524302
    )

    bsxflags: IntProperty(
        name='BSX Flags',
        default=0
    )

    upb: StringProperty(
        name='UPB',
        description='Rarely used for backpacks and bone LOD (rest is optimizer junk)',
        default=''
    )

    skeleton_root: StringProperty(
        name='Skeleton Root',
        description="The bone that acts as the root of the SkinInstance",
    )

    bs_inv: bpy.props.CollectionProperty(type=BsInventoryMarker)

    bs_furniture_marker: bpy.props.CollectionProperty(type=BSFurnitureMarker)

    bs_decal_placement: bpy.props.CollectionProperty(type=BSDecalPlacement)

    # Decal point arrows are editor handles, not NiNodes.  Keeping the marker on the object
    # lets every export path reject them even when a user exports selected objects only.
    is_decal_placement_helper: BoolProperty(
        name="Decal Placement Helper",
        default=False,
        options={'HIDDEN'}
    )

    decal_placement_root: bpy.props.PointerProperty(
        name="Decal Placement Root",
        type=bpy.types.Object,
        options={'HIDDEN'}
    )


    # Per node-subtype fields, each only meaningful for the matching nodetype
    node_range: bpy.props.PointerProperty(type=NodeRangeProperty)

    node_value: bpy.props.PointerProperty(type=NodeValueProperty)

    node_ordered: bpy.props.PointerProperty(type=NodeOrderedProperty)

    node_switch: bpy.props.PointerProperty(type=NodeSwitchProperty)

    node_lod: bpy.props.PointerProperty(type=NodeLODProperty)

    node_sort_adjust: bpy.props.PointerProperty(type=NodeSortAdjustProperty)

    node_multi_bound: bpy.props.PointerProperty(type=NodeMultiBoundProperty)

    # This one belongs to a child of a NiLODNode rather than to the LOD node itself
    lod_level: bpy.props.PointerProperty(type=NodeLODLevelProperty)


inject_bit_bools(ObjectProperty, 'flags', OBJECT_FLAG_BITS)
inject_bit_bools(ObjectProperty, 'bsxflags', BSX_FLAG_BITS)
inject_bit_bools(NodeSwitchProperty, 'switch_node_flags', SWITCH_NODE_FLAG_BITS)
inject_bit_bools(NodeValueProperty, 'value_node_flags', VALUE_NODE_FLAG_BITS)

CLASSES = [
    NodeRangeProperty,
    NodeValueProperty,
    NodeOrderedProperty,
    NodeSwitchProperty,
    NodeLODProperty,
    NodeSortAdjustProperty,
    NodeLODLevelProperty,
    NodeMultiBoundProperty,
    FurniturePosition,
    BSFurnitureMarker,
    BsInventoryMarker,
    DecalPlacementPoint,
    DecalVectorBlock,
    BSDecalPlacement,
    ObjectProperty
]

def register():
    register_classes(CLASSES, __name__)

    bpy.types.Object.nif_object = bpy.props.PointerProperty(type=ObjectProperty)

def unregister():
    del bpy.types.Object.nif_object

    unregister_classes(CLASSES, __name__)
