""" Nif User Interface, custom nif properties for materials"""

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

from bpy.props import (IntProperty, BoolProperty, EnumProperty, FloatVectorProperty)
from bpy.types import PropertyGroup

from ..utils.decorators import register_classes, unregister_classes

from nifgen.formats.nif import classes as NifClasses


def update_alpha_display(self, context):
    """Keep the viewport in step with the alpha property settings."""

    # imported here to avoid a circular import while the addon is registering
    from ..modules.nif_import.property.node_wrapper import apply_alpha_property

    b_mat = getattr(context, "material", None)
    if b_mat is None:
        b_mat = next((mat for mat in bpy.data.materials if mat.nif_alpha == self), None)
    if b_mat is not None:
        apply_alpha_property(b_mat)


class MaterialProperties(PropertyGroup):
    """Group of material related properties, which gets attached to materials through a property pointer."""

    texture_flags: IntProperty(
        name='Texture Flags',
        description='NiTexturingProperty flags. Only Oblivion and earlier make any use of '
                    'them; later games ignore the field but still carry it',
        default=4,
        min=0,
        max=65535
    )

    material_flags: IntProperty(
        name='Material Flags',
        description='NiMaterialProperty flags, used by Oblivion and earlier',
        default=0,
        min=0,
        max=65535
    )

    auto_named: BoolProperty(
        name='Automatically Named',
        description='The material was named after its texture on import, '
                    'so the name is not written to the NIF',
        default=0
    )


class AlphaProperties(PropertyGroup):
    """Group of alpha related properties, which gets attached to materials through a property pointer."""

    use_alpha: BoolProperty(
        name='Use Alpha',
        description='Give the material a NiAlphaProperty. Without one the surface is opaque '
                    'however transparent its texture is',
        default=0,
        update=update_alpha_display
    )

    enable_blending: BoolProperty(
        name='Enable Blending',
        default=0,
        update=update_alpha_display
    )

    source_blend_mode: EnumProperty(
        name='Source Blend Mode',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.AlphaFunction)],
        default='SRC_ALPHA',
        update=update_alpha_display
    )

    destination_blend_mode: EnumProperty(
        name='Destination Blend Mode',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.AlphaFunction)],
        default='INV_SRC_ALPHA',
        update=update_alpha_display
    )

    enable_testing: BoolProperty(
        name='Enable Testing',
        default=1,
        update=update_alpha_display
    )

    alpha_test_function: EnumProperty(
        name='Alpha Test Function',
        items=[(member.name, member.name, "", i) for i, member in enumerate(NifClasses.TestFunction)],
        default='TEST_GREATER',
        update=update_alpha_display
    )

    alpha_test_threshold: IntProperty(
        name='Alpha Test Threshold',
        default=128,
        min=0,
        max=255,
        update=update_alpha_display
    )

    no_sorter: BoolProperty(
        name='No Sorter',
        default=0,
        update=update_alpha_display
    )

CLASSES = [
    MaterialProperties,
    AlphaProperties
]

def register():
    register_classes(CLASSES, __name__)

    bpy.types.Material.nif_material = bpy.props.PointerProperty(type=MaterialProperties)
    bpy.types.Material.nif_alpha = bpy.props.PointerProperty(type=AlphaProperties)


def unregister():
    del bpy.types.Material.nif_material
    del bpy.types.Material.nif_alpha

    unregister_classes(CLASSES, __name__)
