"""Nif User Interface, connect custom properties from properties.py into Blenders UI"""

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


from bpy.types import Panel
from io_scene_niftools.utils.decorators import register_classes, unregister_classes
from nifgen.formats.nif import classes as NifClasses


class ShaderPanel(Panel):
    bl_idname = "NIFTOOLS_PT_ShaderPanel"
    bl_label = "NifTools Shader"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        if context.material:
            return True
        return False

    def draw(self, context):
        layout = self.layout

        col_setting = context.active_object.active_material.nif_shader

        box = layout.box()

        box.prop(col_setting, "bs_shadertype", text="Shader Type")

        if col_setting.bs_shadertype and not (col_setting.bs_shadertype in ('BSLightingShaderProperty', 'BSEffectShaderProperty')):
            box.prop(col_setting, "bsspplp_shaderobjtype", text="BS Shader PP Lighting Type")

            for property_name in sorted(NifClasses.BSShaderFlags.__members__):
                box.prop(col_setting, property_name)
            for property_name in sorted(NifClasses.BSShaderFlags2.__members__):
                box.prop(col_setting, property_name)

        elif col_setting.bs_shadertype in ('BSLightingShaderProperty', 'BSEffectShaderProperty'):
            box.prop(col_setting, "bslsp_shaderobjtype", text="BS Lighting Shader Type")

            box.prop(col_setting, "lighting_effect_1", text="Lighting Effect 1")
            box.prop(col_setting, "lighting_effect_2", text="Lighting Effect 2")

            for property_name in sorted(NifClasses.SkyrimShaderPropertyFlags1.__members__):
                box.prop(col_setting, property_name)
            for property_name in sorted(NifClasses.SkyrimShaderPropertyFlags2.__members__):
                box.prop(col_setting, property_name)

classes = [
    ShaderPanel
]

def register():
    register_classes(classes, __name__)

def unregister():
    unregister_classes(classes, __name__)
