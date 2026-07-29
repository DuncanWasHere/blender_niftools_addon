""" Nif User Interface, custom nif properties for shaders"""

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
from bpy.props import (BoolProperty,
                       EnumProperty, FloatProperty, IntProperty,
                       )
from bpy.types import PropertyGroup
from ..utils.decorators import register_classes, unregister_classes
from ..utils.flags import prettify_prop_name
from nifgen.formats.nif import classes as NifClasses


# Every shader property block the addon can write, with the fixed value each keeps in the
# enum so that a value stored in a blend file keeps its meaning when the list is filtered.
# A block only exists in the games that shipped it: the Fallout 3 family got the BSShader
# blocks, and Skyrim replaced the lot with the lighting and effect shaders.
SHADER_TYPES = (
    ('None', 'None', "", 0),
    ('BSShaderProperty', 'BS Shader Property', "", 1),
    ('BSShaderPPLightingProperty', 'BS Shader PP Lighting Property', "", 2),
    ('BSLightingShaderProperty', 'BS Lighting Shader Property', "", 3),
    ('BSEffectShaderProperty', 'BS Effect Shader Property', "", 4),
    ('BSShaderNoLightingProperty', 'BS Shader No Lighting Property', "", 5),
    ('SkyShaderProperty', 'Sky Shader Property', "", 6),
    ('TallGrassShaderProperty', 'Tall Grass Shader Property', "", 7),
    ('TileShaderProperty', 'Tile Shader Property', "", 8),
    ('WaterShaderProperty', 'Water Shader Property', "", 9)
)

FALLOUT_ONLY_TYPES = ('BSShaderPPLightingProperty', 'BSShaderNoLightingProperty', 'SkyShaderProperty',
                      'TallGrassShaderProperty', 'TileShaderProperty', 'WaterShaderProperty')
SKYRIM_ONLY_TYPES = ('BSShaderProperty', 'BSLightingShaderProperty', 'BSEffectShaderProperty')

def game_specific_shader_type_items(self, context):
    """The shader property blocks the currently selected game actually has."""

    b_scene = (context or bpy.context).scene.niftools_scene
    if b_scene.is_skyrim():
        allowed = SKYRIM_ONLY_TYPES
    elif b_scene.is_fo3():
        allowed = FALLOUT_ONLY_TYPES
    else:
        # Oblivion and earlier shade through the material property, not a shader property
        allowed = ()

    return [item for item in SHADER_TYPES if item[0] == 'None' or item[0] in allowed]


# The shader flags that switch on an effect the node tree shows. Kept as a plain set here so
# that the property definitions do not have to import the node wrapper at registration time.
VISUAL_SHADER_FLAGS = frozenset((
    'environment_mapping', 'refraction', 'fire_refraction',
    'parallax_shader_index_15', 'parallax_occulsion',
    # BSShaderFlags2 bit 31, real time reflections on Fallout 3
    'unknown_10',
))


def find_material(b_shader_props, context):
    """The material a shader property group belongs to."""

    b_mat = getattr(context, "material", None)
    if b_mat is not None and b_mat.nif_shader == b_shader_props:
        return b_mat
    return next((mat for mat in bpy.data.materials if mat.nif_shader == b_shader_props), None)


def update_shader_flag_visuals(self, context):
    """Mirror a shader flag onto the node group so the viewport shows what it turns on."""

    # imported here to avoid a circular import while the addon is registering
    from ..modules.nif_import.property.node_wrapper import sync_shader_flag_visuals

    b_mat = find_material(self, context)
    if b_mat is not None:
        sync_shader_flag_visuals(b_mat)


def update_shader_type(self, context):
    """Swap the material's shader node group when the shader type changes."""

    # imported here to avoid a circular import while the addon is registering
    from ..modules.nif_import.property.node_wrapper import sync_shader_group

    b_mat = find_material(self, context)
    if b_mat is not None:
        sync_shader_group(b_mat, self.bs_shadertype)


class ShaderProperty(PropertyGroup):
    bs_shadertype: EnumProperty(
        name='Shader Type',
        description='Type of property used to display meshes',
        items=game_specific_shader_type_items,
        update=update_shader_type
    )

    bslsp_shaderobjtype: EnumProperty(
        name='BS Lighting Shader Object Type',
        description='Type of object linked to shader',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.BSLightingShaderType)],
    )

    sky_object_type: EnumProperty(
        name='Sky Object Type',
        description='Type of sky object linked to shader',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.SkyObjectType)],
    )

    lighting_effect_1: FloatProperty(
        name='Lighting Effect 1',
        description='Controls strength of envmap/backlight/rim/softlight lighting effect',
        default = 0
    )

    lighting_effect_2: FloatProperty(
        name='Lighting Effect 2',
        description='Controls strength of envmap/backlight/rim/softlight lighting effect',
        default = 0
    )

    # refraction and parallax live on the shader node group's sockets, where they can be seen as well as set
    # the falloff above is still here for the Skyrim effect shader,
    # which builds a principled tree rather than a group

    texture_clamp_mode: EnumProperty(
        name='Texture Clamp Mode',
        description='How the shader textures are wrapped or clamped',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.TexClampMode)],
        default='WRAP_S_WRAP_T'
    )

annotations_dict = ShaderProperty.__dict__.get('__annotations__', None)
if annotations_dict:
    for flag_field in (NifClasses.BSShaderFlags,
                       NifClasses.BSShaderFlags2,
                       NifClasses.SkyrimShaderPropertyFlags1,
                       NifClasses.SkyrimShaderPropertyFlags2):
        for property_name in flag_field.__members__:
            if property_name not in annotations_dict:
                # the handful of flags that switch on something the node tree can show get an
                # update, so the viewport follows the checkbox
                annotations_dict[property_name] = BoolProperty(
                    name=prettify_prop_name(property_name),
                    update=update_shader_flag_visuals if property_name in VISUAL_SHADER_FLAGS else None)

CLASSES = [
    ShaderProperty
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.Material.nif_shader = bpy.props.PointerProperty(type=ShaderProperty)


def unregister():
    del bpy.types.Material.nif_shader

    unregister_classes(CLASSES, __name__)
