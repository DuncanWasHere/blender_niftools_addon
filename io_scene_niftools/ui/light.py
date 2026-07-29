""" Nif User Interface, connect the light properties into Blender's UI"""

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


from bpy.types import Panel

from ..utils.decorators import register_classes, unregister_classes

# Which nif block a Blender light becomes, for the label at the top of the panel
LIGHT_BLOCK_LABELS = {
    'POINT': "NiPointLight",
    'SPOT': "NiSpotLight",
    'AREA': "NiPointLight (area lights have no nif equivalent)",
}


class LightButtonsPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.light is not None


class LightPanel(LightButtonsPanel):
    bl_label = "NifTools Light"
    bl_idname = "NIFTOOLS_PT_LightPanel"

    def draw(self, context):
        b_light = context.light
        nif_light = b_light.nif_light

        layout = self.layout
        column = layout.column()

        if b_light.type == 'SUN':
            column.prop(nif_light, "sun_block_type")
        else:
            column.label(text=LIGHT_BLOCK_LABELS.get(b_light.type, "Unsupported"),
                         icon='LIGHT_DATA')

        column.prop(nif_light, "dimmer")
        column.prop(nif_light, "switch_state")

        column.separator()
        # the diffuse colour is the light's own colour, shown here only as a reminder that
        # the nif keeps three colours where Blender keeps one
        column.prop(b_light, "color", text="Diffuse Color")
        column.prop(nif_light, "ambient_color")
        column.prop(nif_light, "specular_color")


class LightAttenuationPanel(LightButtonsPanel):
    bl_label = "Attenuation"
    bl_idname = "NIFTOOLS_PT_LightAttenuationPanel"
    bl_parent_id = "NIFTOOLS_PT_LightPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # attenuation is a NiPointLight field, so it covers point and spot lights
        return context.light is not None and context.light.type in ('POINT', 'SPOT', 'AREA')

    def draw(self, context):
        nif_light = context.light.nif_light

        layout = self.layout
        layout.label(text="Blender lights always fall off quadratically", icon='INFO')

        column = layout.column(align=True)
        column.prop(nif_light, "constant_attenuation", text="Constant")
        column.prop(nif_light, "linear_attenuation", text="Linear")
        column.prop(nif_light, "quadratic_attenuation", text="Quadratic")


class LightSpotPanel(LightButtonsPanel):
    bl_label = "Spot"
    bl_idname = "NIFTOOLS_PT_LightSpotPanel"
    bl_parent_id = "NIFTOOLS_PT_LightPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.light is not None and context.light.type == 'SPOT'

    def draw(self, context):
        b_light = context.light

        layout = self.layout
        column = layout.column(align=True)
        # the cone itself is Blender's, and is what the spot angles are written from
        column.prop(b_light, "spot_size", text="Outer Angle")
        column.prop(b_light, "spot_blend", text="Blend")

        layout.prop(b_light.nif_light, "exponent")


classes = [
    LightPanel,
    LightAttenuationPanel,
    LightSpotPanel,
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
