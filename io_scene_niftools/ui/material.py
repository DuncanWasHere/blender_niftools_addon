"""Nif User Interface, connect custom properties from properties.py into Blenders UI"""

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

from ..utils.decorators import register_classes, unregister_classes


class MaterialPanel(Panel):
    bl_idname = "NIFTOOLS_PT_MaterialPanel"
    bl_label = "NifTools Material"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        # everything in here belongs to the games that shade with the material and texturing
        # properties.
        # From Fallout 3 and beyond Bethesda's custom shaders are used and the panel would be
        # empty, so it is not shown at all
        b_scene = bpy.context.scene.niftools_scene
        return context.material is not None and not (b_scene.is_fo3() or b_scene.is_skyrim())

    def draw(self, context):
        layout = self.layout

        col_setting = context.active_object.active_material.nif_material

        box = layout.box()
        box.prop(col_setting, "material_flags", text='Material Flags')
        box.prop(col_setting, "texture_flags", text='Texture Flags')

class AlphaPanel(Panel):
    bl_idname = "NIFTOOLS_PT_AlphaPanel"
    bl_label = "NifTools Alpha"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout

        b_mat = context.active_object.active_material
        material_setting = b_mat.nif_alpha

        box = layout.box()

        # the toggle decides whether a NiAlphaProperty is written at all, so everything else
        # in here only means something once it is on. It is always drawn, or there would be
        # no way to turn alpha back on once it is off.
        box.prop(material_setting, "use_alpha", text='Use Alpha')

        if not material_setting.use_alpha:
            return

        box.prop(material_setting, "enable_blending", text='Enable Blending')
        box.prop(material_setting, "source_blend_mode", text='Source Blend Mode')
        box.prop(material_setting, "destination_blend_mode", text='Destination Blend Mode')
        box.prop(material_setting, "enable_testing", text='Enable Testing')
        box.prop(material_setting, "alpha_test_function", text='Alpha Test Function')
        box.prop(material_setting, "alpha_test_threshold", text='Alpha Test Threshold')
        box.prop(material_setting, "no_sorter", text='No Sorter')

classes = [
    MaterialPanel,
    AlphaPanel
]

def register():
    register_classes(classes, __name__)

def unregister():
    unregister_classes(classes, __name__)
