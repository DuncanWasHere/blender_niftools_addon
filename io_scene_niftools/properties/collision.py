"""Nif User Interface, custom nif properties store for collisions settings"""

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
from bpy.props import (IntProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty, FloatVectorProperty,
                       )
from bpy.types import PropertyGroup
from io_scene_niftools.utils.decorators import register_classes, unregister_classes
from nifgen.formats.nif import classes as NifClasses


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


class CollisionProperties(PropertyGroup):
    """Group of Havok related properties, which gets attached to objects through a property pointer."""

    collision_layer: EnumProperty(
        name='Collision layer',
        description='Collision layer string (game-specific)',
        items=game_specific_col_layer_items
    )

    col_filter: IntProperty(
        name='Col Filter',
        description='Flags for bhkRigidBody(t)',
        default=0
    )

    inertia_tensor: FloatVectorProperty(
        name='Inertia Tensor',
        description='Inertia tensor for bhkRigidBody(t)',
        default=(0, 0, 0)
    )

    center: FloatVectorProperty(
        name='Center',
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
        description='Havok Motion System settings for bhkRigidBody(t)',
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

    use_blender_properties: BoolProperty(
        name='Use Blender Properties',
        description='Whether or not to export collision settings via blender properties',
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

CLASSES = [
    CollisionProperties
]

def register():
    register_classes(CLASSES, __name__)

    bpy.types.Object.nif_collision = bpy.props.PointerProperty(type=CollisionProperties)

def unregister():
    del bpy.types.Object.nif_collision

    unregister_classes(CLASSES, __name__)
