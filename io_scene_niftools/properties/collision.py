"""Nif User Interface, custom nif properties store for collisions settings"""

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
from bpy.props import (IntProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty, FloatVectorProperty,
                       )
from bpy.types import PropertyGroup
from ..utils.decorators import register_classes, unregister_classes
from ..utils.flags import bits_of, inject_bit_bools, packed_value_accessors
from nifgen.formats.nif import classes as NifClasses

# bhkNiCollisionObject.Flags, a real bitflags in the format, so the members come from there
COLLISION_OBJECT_FLAG_BITS = bits_of(NifClasses.BhkCOFlags, {
    'active': 'The collision object takes part in the simulation',
    'set_local': 'Needed together with Use Vel for animated collision on the older games',
    'use_vel': 'Drive the body from the node velocity, for animated collision',
    'sync_on_update': 'Keep the body in sync with the node, set on Fallout 3 and later',
    'blend_pos': 'bhkBlendCollisionObject only',
    'always_blend': 'bhkBlendCollisionObject only',
})

# The flags packed into HavokFilter alongside the collision layer. Its low five bits hold
# the biped part, which is a value rather than a set of flags, so bits_of leaves it out and
# it gets an enum of its own over the same integer.
HAVOK_FILTER_FLAG_BITS = bits_of(NifClasses.CollisionFilterFlags, {
    'mopp_scaled': 'The MOPP data is scaled',
    'no_collision': 'The body is present but does not collide',
    'linked_group': 'The body is part of a linked collision group',
})

BIPED_PART_MASK = NifClasses.CollisionFilterFlags.__dict__['biped_part'].mask
BIPED_PART_GET, BIPED_PART_SET = packed_value_accessors(
    'col_filter', BIPED_PART_MASK, {member.value for member in NifClasses.BipedPart})


def game_specific_col_layer_items(self, context):
    """Items for collision layers based on the currently selected game"""
    if context is None:
        current_game = bpy.context.scene.niftools_scene.game
    else:
        current_game = context.scene.niftools_scene.game
    col_layer_format = None
    if current_game in ("OBLIVION", "OBLIVION_KF"):
        col_layer_format = NifClasses.OblivionLayer
    elif current_game in ("FALLOUT_3", 'FALLOUT_NV'):
        col_layer_format = NifClasses.Fallout3Layer
    elif current_game in ("SKYRIM", "SKYRIM_SE", "FALLOUT_4"):
        col_layer_format = NifClasses.SkyrimLayer
    if col_layer_format is None:
        return []
    else:
        return [(str(member.value), member.name, "", member.value) for member in col_layer_format]


class HavokActionProperties(PropertyGroup):
    """The Bethesda havok actions that can be attached to a collision object.

    An action is referenced by nothing in the format: it exists only as an entry in the
    block list, sitting directly after the rigid body it acts on. The exporter reproduces
    that placement, because the game crashes on a misplaced bhkLiquidAction.
    """

    use_liquid_action: BoolProperty(
        name='Liquid Action',
        description='Make this body stick to static and terrain bodies it touches. Vanilla '
                    'uses it for the incinerator fireball and the Nuka-grenade explosion',
        default=False
    )

    initial_stick_force: FloatProperty(
        name='Initial Stick Force',
        description='Force holding the body in place when it first sticks',
        default=25.0
    )

    stick_strength: FloatProperty(
        name='Stick Strength',
        description='How strongly the body stays stuck',
        default=100.0
    )

    neighbor_distance: FloatProperty(
        name='Neighbor Distance',
        description='Range over which nearby bodies are pulled together',
        default=128.0
    )

    neighbor_strength: FloatProperty(
        name='Neighbor Strength',
        description='How strongly nearby bodies are pulled together',
        default=500.0
    )

    use_orient_hinged_body_action: BoolProperty(
        name='Orient Hinged Body Action',
        description='Keep this body facing a fixed direction, letting it turn and pitch but '
                    'not tilt. Required by the turret skeletons',
        default=False
    )

    hinge_axis_ls: FloatVectorProperty(
        name='Hinge Axis',
        description='Axis the body is allowed to rotate about, in body space',
        subtype='XYZ',
        size=3,
        default=(1.0, 0.0, 0.0)
    )

    forward_ls: FloatVectorProperty(
        name='Forward',
        description='Direction the body tries to keep facing, in body space',
        subtype='XYZ',
        size=3,
        default=(0.0, 1.0, 0.0)
    )

    strength: FloatProperty(
        name='Strength',
        description='How hard the body is pushed back towards the forward direction',
        default=1.0
    )

    damping: FloatProperty(
        name='Damping',
        description='Damping applied to the reorienting motion',
        default=0.1
    )


class CollisionProperties(PropertyGroup):
    """Group of Havok related properties, which gets attached to objects through a property pointer."""

    body_type: EnumProperty(
        name='Body Type',
        description='Which kind of havok body this collision object is. A phantom has no '
                    'physical response and only reports overlaps, which is how trigger '
                    'volumes and trap activation ranges are built',
        items=(
            ('bhkRigidBody', 'Rigid Body',
             "Ordinary collision, written as a bhkCollisionObject with a bhkRigidBody", 0),
            ('bhkSimpleShapePhantom', 'Simple Shape Phantom',
             "Overlap only volume with a real shape, written as a bhkSPCollisionObject", 1),
            ('bhkAabbPhantom', 'AABB Phantom',
             "Overlap only volume that is just a box, written as a bhkPCollisionObject", 2),
        ),
        default='bhkRigidBody'
    )

    collision_layer: EnumProperty(
        name='Collision layer',
        description='Collision layer string (game-specific)',
        items=game_specific_col_layer_items,
        default=1
    )

    # Storage behind the havok filter checkboxes and the biped part
    col_filter: IntProperty(
        name='Havok Filter Flags',
        default=0,
        min=0,
        max=255
    )

    biped_part: EnumProperty(
        name='Biped Part',
        description='Which part of a biped this collision body is, stored in the low bits of '
                    'the havok filter',
        items=[(member.name, member.name, "", member.value) for member in NifClasses.BipedPart],
        get=BIPED_PART_GET,
        set=BIPED_PART_SET
    )

    # Storage behind the collision object checkboxes
    collision_flags: IntProperty(
        name='Collision Object Flags',
        default=int(NifClasses.BhkCOFlags.ACTIVE),
        min=0,
        max=65535
    )

    use_blend_collision: BoolProperty(
        name='Blend Collision',
        description='Export a bhkBlendCollisionObject instead of a plain bhkCollisionObject, '
                    'together with the bhkBlendController that always accompanies it. This is '
                    'what the biped collision on a Bethesda skeleton uses',
        default=False,
    )

    heir_gain: FloatProperty(
        name='Heir Gain',
        description='Blend collision heir gain',
        default=1.0,
    )

    vel_gain: FloatProperty(
        name='Vel Gain',
        description='Blend collision velocity gain',
        default=1.0,
    )

    broad_phase_type: EnumProperty(
        name='Broad Phase Type',
        description='How the havok broad phase treats this body',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.BroadPhaseType)],
        default='BROAD_PHASE_ENTITY'
    )

    inertia_tensor: FloatVectorProperty(
        name='Inertia Tensor',
        description='Inertia tensor for bhkRigidBody(t)',
        default=(0, 0, 0)
    )

    center: FloatVectorProperty(
        name='Center of Mass',
        description='Center of mass for bhkRigidBody(t)',
        default=(0, 0, 0)
    )

    mass: FloatProperty(
        name='Mass',
        description='Mass for bhkRigidBody(t)',
        default=0
    )

    max_linear_velocity: FloatProperty(
        name='Max Linear Velocity',
        description='Linear velocity limit for bhkRigidBody(t)',
        default=1068.0
    )

    max_angular_velocity: FloatProperty(
        name='Max Angular Velocity',
        description='Angular velocity limit for bhkRigidBody(t)',
        default=31.57
    )

    penetration_depth: FloatProperty(
        name='Penetration Depth',
        description='The maximum allowed penetration for this object.',
        default=0.15
    )

    motion_system: EnumProperty(
        name='Motion System',
        description='Havok Motion System settings for bhkRigidBody(T)',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.HkMotionType)],
        default='MO_SYS_FIXED',
    )

    deactivator_type: EnumProperty(
        name='Deactivator Type',
        description='Motion deactivation setting',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.HkDeactivatorType)],
        default='DEACTIVATOR_NEVER',
    )

    solver_deactivation: EnumProperty(
        name='Solver Deactivation',
        description='Motion deactivation setting',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.HkSolverDeactivation)],
        default='SOLVER_DEACTIVATION_OFF',
    )

    quality_type: EnumProperty(
        name='Quality Type',
        description='Determines quality of motion',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.HkQualityType)],
        default='MO_QUAL_FIXED',
    )

    body_flags: BoolProperty(
        name='Body Flags',
        description='Whether or not to react to wind',
        default=False,
    )

    force_bhk_rigid_body_t: BoolProperty(
        name='Force bhkRigidBodyT',
        description='Force the export to use a bhkRigidBodyT for this shape even if there are no transforms (needed for constraints)',
        default=False,
    )

    use_blender_properties: BoolProperty(
        name='Recalculate Inertia Tensor',
        description='Whether or not to recalculate inertia tensor based on blender mass and mesh geometry',
        default=False,
    )

    solid: BoolProperty(
        name='Solid',
        description='Recalculate inertia tensor for a solid object',
        default=True,
    )

    shrink_offset: FloatProperty(
        name="Shrink Offset",
        description='Value to shrink the collision hull by',
        default=0.072,
        min=0
    )


inject_bit_bools(CollisionProperties, 'collision_flags', COLLISION_OBJECT_FLAG_BITS)
inject_bit_bools(CollisionProperties, 'col_filter', HAVOK_FILTER_FLAG_BITS)

CLASSES = [
    HavokActionProperties,
    CollisionProperties
]

def register():
    register_classes(CLASSES, __name__)

    bpy.types.Object.nif_collision = bpy.props.PointerProperty(type=CollisionProperties)
    bpy.types.Object.nif_havok_action = bpy.props.PointerProperty(type=HavokActionProperties)

def unregister():
    del bpy.types.Object.nif_collision
    del bpy.types.Object.nif_havok_action

    unregister_classes(CLASSES, __name__)
