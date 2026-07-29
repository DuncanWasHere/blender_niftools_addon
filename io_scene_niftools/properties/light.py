"""Nif User Interface, custom nif properties for lights"""

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
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty
from bpy.types import PropertyGroup

from ..utils.decorators import register_classes, unregister_classes

# A nif dimmer of 1.0 shown as this much Blender light power. Gamebryo simply multiplies the
# light colour by the dimmer, while Blender wants radiometric watts, so there is no correct
# conversion - this is only picked so that an imported light is visible at nif scale.
DIMMER_WATTS = 100.0


def update_light_display(self, context):
    """Keep the Blender light in step with the nif-only light properties.

    Dimmer has no Blender counterpart (it scales every colour component in the engine), so
    it is stored here and pushed onto the light's power purely so the viewport shows
    something proportional to what the game would draw.
    """

    b_light = getattr(context, "light", None)
    if b_light is None:
        b_light = next((light for light in bpy.data.lights if light.nif_light == self), None)
    if b_light is None:
        return

    if b_light.type == 'SUN':
        # a sun's strength is an irradiance, not a power, so watts would be absurd
        b_light.energy = self.dimmer
    else:
        b_light.energy = self.dimmer * DIMMER_WATTS


class LightProperties(PropertyGroup):
    """Group of NiLight properties, attached to lights through a property pointer."""

    # A Blender POINT is always a NiPointLight and a SPOT always a NiSpotLight, so the block
    # type only needs storing for suns, which stand in for both of the nif's undirected and
    # directional lights.
    sun_block_type: EnumProperty(
        name='Sun Block Type',
        description='Which NiLight block a Blender sun corresponds to',
        items=(
            ('NiDirectionalLight', 'NiDirectionalLight', "Parallel light with a direction", 0),
            ('NiAmbientLight', 'NiAmbientLight', "Undirected fill light", 1),
        ),
        default='NiDirectionalLight'
    )

    dimmer: FloatProperty(
        name='Dimmer',
        description='Scales the overall brightness of all light components. The viewport '
                    'power is derived from this',
        default=1.0,
        min=0.0,
        update=update_light_display
    )

    ambient_color: FloatVectorProperty(
        name='Ambient Color',
        description='Ambient contribution of the light. Usually black on Bethesda nifs',
        subtype='COLOR',
        default=(0.0, 0.0, 0.0),
        min=0.0,
        max=1.0
    )

    specular_color: FloatVectorProperty(
        name='Specular Color',
        description='Specular contribution of the light. Won\'t have a visual effect in Blender',
        subtype='COLOR',
        default=(0.0, 0.0, 0.0),
        min=0.0,
        max=1.0
    )

    switch_state: BoolProperty(
        name='Switch State',
        description='NiDynamicEffect switch state. When off the effect is not applied to the '
                    'affected nodes during rendering',
        default=True
    )

    constant_attenuation: FloatProperty(
        name='Constant Attenuation',
        description='Constant term of the point light falloff. Blender lights are physically '
                    'based and always fall off quadratically, so this is stored, not shown',
        default=0.0
    )

    linear_attenuation: FloatProperty(
        name='Linear Attenuation',
        description='Linear term of the point light falloff',
        default=1.0
    )

    quadratic_attenuation: FloatProperty(
        name='Quadratic Attenuation',
        description='Quadratic term of the point light falloff',
        default=0.0
    )

    exponent: FloatProperty(
        name='Exponent',
        description='NiSpotLight exponent, describing the distribution of light within the '
                    'cone. Blender uses a linear spot blend instead',
        default=1.0
    )


CLASSES = [
    LightProperties
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.Light.nif_light = bpy.props.PointerProperty(type=LightProperties)


def unregister():
    del bpy.types.Light.nif_light

    unregister_classes(CLASSES, __name__)
