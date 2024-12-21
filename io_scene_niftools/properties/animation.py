"""Nif User Interface, custom nif properties store for animation settings"""

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
from bpy.props import EnumProperty, FloatProperty
from bpy.types import PropertyGroup

from nifgen.formats.nif import classes as NifClasses

from io_scene_niftools.utils.decorators import register_classes, unregister_classes


class AnimationProperty(PropertyGroup):
    """Group of Havok related properties, which gets attached to objects through a property pointer."""


    weight: FloatProperty(
        name='Weight',
        description='How the NiControllerSequence blends with other sequences at the same priority',
        default=1.0,
        min=0,
        max=1.0,
    )

    cycle_type: EnumProperty(
        name='Cycle Type',
        description='Playback behavior of the NiControllerSequence',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.CycleType)],
        default = 'CYCLE_LOOP'
    )

    frequency: FloatProperty(
        name='Frequency',
        description='Playback speed of the NiControllerSequence',
        min=0,
        default=1.0,
    )


CLASSES = [
    AnimationProperty
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.Action.nifanimation = bpy.props.PointerProperty(type=AnimationProperty)


def unregister():
    del bpy.types.Action.nifanimation

    unregister_classes(CLASSES, __name__)