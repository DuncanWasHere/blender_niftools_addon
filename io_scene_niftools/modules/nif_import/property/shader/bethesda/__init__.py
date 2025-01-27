"""This script contains helper methods to import BSShaderLightingProperty based properties."""

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


from functools import singledispatch

from io_scene_niftools import NifLog
from io_scene_niftools.modules.nif_import.property.shader import BSShader
from io_scene_niftools.modules.nif_import.property.texture.types.bsshadertextureset import BSShaderTextureSet
from nifgen.formats.nif import classes as NifClasses


class BSShaderProperty(BSShader):
    """Main interface class for importing Bethesda shader property blocks."""

    __instance = None

    def __init__(self):
        super().__init__()

        self.texture_helper = BSShaderTextureSet.get()

        self.import_bs_shader_property = singledispatch(self.__import_bs_shader_property)
        self.import_bs_shader_property.register(NifClasses.BSShaderPPLightingProperty, self.__import_bs_shader_pp_lighting_property)
        self.import_bs_shader_property.register(NifClasses.BSShaderNoLightingProperty, self.__import_bs_shader_no_lighting_property)
        self.import_bs_shader_property.register(NifClasses.BSLightingShaderProperty, self.__import_bs_lighting_shader_property)
        self.import_bs_shader_property.register(NifClasses.BSEffectShaderProperty, self.__import_bs_effect_shader_property)
        self.import_bs_shader_property.register(NifClasses.SkyShaderProperty, self.__import_sky_shader_property)
        self.import_bs_shader_property.register(NifClasses.TallGrassShaderProperty, self.__import_tall_grass_shader_property)
        self.import_bs_shader_property.register(NifClasses.TileShaderProperty, self.__import_tile_shader_property)
        self.import_bs_shader_property.register(NifClasses.WaterShaderProperty, self.__import_water_shader_property)

    def __import_bs_shader_property(self, n_bs_shader_property, b_mat):
        """Base method for unsupported blocks."""

        NifLog.warn(f"Unknown Bethesda shader block found : {n_bs_shader_property.name:s}.")
        NifLog.warn(f"This type is not currently supported: {type(n_bs_shader_property)}.")

    def __import_bs_shader_pp_lighting_property(self, n_bs_shader_pp_lighting_property, b_mat):
        """Import a BSShaderPPLightingProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'BSShaderPPLightingProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_bs_shader_pp_lighting_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_shader_pp_lighting_property.shader_flags)
        self.import_shader_flags(b_mat, n_bs_shader_pp_lighting_property.shader_flags_2)

        self.texture_helper.import_bs_shader_texture_set(n_bs_shader_pp_lighting_property, b_mat)

    def __import_bs_shader_no_lighting_property(self, n_bs_shader_no_lighting_property, b_mat):
        """Import a BSShaderNoLightingProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'BSShaderNoLightingProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_bs_shader_no_lighting_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_shader_no_lighting_property.shader_flags)
        self.import_shader_flags(b_mat, n_bs_shader_no_lighting_property.shader_flags_2)

    def __import_bs_lighting_shader_property(self, n_bs_lighting_shader_property, b_mat):

        b_mat.nif_shader.bs_shadertype = 'BSLightingShaderProperty'

        b_mat.nif_shader.bslsp_shaderobjtype = n_bs_lighting_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_lighting_shader_property.shader_flags_1)
        self.import_shader_flags(b_mat, n_bs_lighting_shader_property.shader_flags_2)

        self.texture_helper.import_bs_shader_texture_set(n_bs_lighting_shader_property, b_mat)

        x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y = self.__get_uv_transform(n_bs_lighting_shader_property)
        self._nodes_wrapper.global_uv_offset_scale(x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y)

        b_shader_node = b_mat.node_tree.nodes["Principled BSDF"]

        b_shader_node.inputs[14].default_value = (n_bs_lighting_shader_property.specular_color.r,
                                                  n_bs_lighting_shader_property.specular_color.g,
                                                  n_bs_lighting_shader_property.specular_color.b, 1)

        b_shader_node.inputs[26].default_value = (n_bs_lighting_shader_property.hair_tint_color.r,
                                                  n_bs_lighting_shader_property.hair_tint_color.g,
                                                  n_bs_lighting_shader_property.hair_tint_color.b, 1)

        b_shader_node.inputs[22].default_value = (n_bs_lighting_shader_property.skin_tint_color.r,
                                                  n_bs_lighting_shader_property.skin_tint_color.g,
                                                  n_bs_lighting_shader_property.skin_tint_color.b, 1)

        # Map roughness [0,1] to glossiness (MW -> 0.0 - 128.0)
        if not n_bs_lighting_shader_property.glossiness == 0:
            b_shader_node.inputs[2].default_value = (1 - (1 / (n_bs_lighting_shader_property.glossiness / 2))) ** 2
        else:
            b_shader_node.inputs[2].default_value = 0

        b_shader_node.inputs[4].default_value = n_bs_lighting_shader_property.alpha

        b_shader_node.inputs[28].default_value = n_bs_lighting_shader_property.emissive_mult

        # TODO: Add color mult shader node for emissive color

        self._b_mat.nif_shader.lighting_effect_1 = n_bs_lighting_shader_property.lighting_effect_1
        self._b_mat.nif_shader.lighting_effect_2 = n_bs_lighting_shader_property.lighting_effect_2

    def __import_bs_effect_shader_property(self, n_bs_effect_shader_property, b_mat):

        b_mat.nif_shader.bs_shadertype = 'BSEffectShaderProperty'

        b_mat.nif_shader.bslsp_shaderobjtype = n_bs_effect_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_effect_shader_property.shader_flags_1)
        self.import_shader_flags(b_mat, n_bs_effect_shader_property.shader_flags_2)

        self.texture_helper.import_bs_shader_texture_set(n_bs_effect_shader_property, b_mat)

        x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y = self.__get_uv_transform(n_bs_effect_shader_property)
        self._nodes_wrapper.global_uv_offset_scale(x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y)

        b_shader_node = b_mat.node_tree.nodes["Principled BSDF"]

        b_shader_node.inputs[14].default_value = (n_bs_effect_shader_property.specular_color.r,
                                                  n_bs_effect_shader_property.specular_color.g,
                                                  n_bs_effect_shader_property.specular_color.b, 1)

        b_shader_node.inputs[26].default_value = (n_bs_effect_shader_property.hair_tint_color.r,
                                                  n_bs_effect_shader_property.hair_tint_color.g,
                                                  n_bs_effect_shader_property.hair_tint_color.b, 1)

        b_shader_node.inputs[22].default_value = (n_bs_effect_shader_property.skin_tint_color.r,
                                                  n_bs_effect_shader_property.skin_tint_color.g,
                                                  n_bs_effect_shader_property.skin_tint_color.b, 1)

        # Map roughness [0,1] to glossiness (MW -> 0.0 - 128.0)
        b_shader_node.inputs[2].default_value = min(1, n_bs_effect_shader_property.glossiness / 128)

        b_shader_node.inputs[4].default_value = n_bs_effect_shader_property.alpha

        b_shader_node.inputs[28].default_value = n_bs_effect_shader_property.emissive_mult

        # TODO: Add color mult shader node for emissive color

        self._b_mat.nif_shader.lighting_effect_1 = n_bs_effect_shader_property.lighting_effect_1
        self._b_mat.nif_shader.lighting_effect_2 = n_bs_effect_shader_property.lighting_effect_2

        # TODO: Add animation controller import

    def __import_sky_shader_property(self, n_sky_shader_property, b_mat):
        """Import a SkyShaderProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'SkyShaderProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_sky_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_sky_shader_property.shader_flags)
        self.import_shader_flags(b_mat, n_sky_shader_property.shader_flags_2)

    def __import_tall_grass_shader_property(self, n_tall_grass_shader_property, b_mat):
        """Import a TallGrassShaderProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'TallGrassShaderProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_tall_grass_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_tall_grass_shader_property.shader_flags)
        self.import_shader_flags(b_mat, n_tall_grass_shader_property.shader_flags_2)

    def __import_tile_shader_property(self, n_tile_shader_property, b_mat):
        """Import a TileShaderProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'TileShaderProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_tile_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_tile_shader_property.shader_flags)
        self.import_shader_flags(b_mat, n_tile_shader_property.shader_flags_2)

    def __import_water_shader_property(self, n_water_shader_property, b_mat):
        """Import a WaterShaderProperty block into a Blender shader tree."""

        b_mat.nif_shader.bs_shadertype = 'WaterShaderProperty'

        b_mat.nif_shader.bsspplp_shaderobjtype = n_water_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_water_shader_property.shader_flags)
        self.import_shader_flags(b_mat, n_water_shader_property.shader_flags_2)

    def __get_uv_transform(self, shader):
        # get the uv scale and offset from the shader (used by BSLightingShaderProperty, BSEffectShaderProperty,
        # BSWaterShaderProperty and BSSkyShaderProperty, according to nif.xml)
        if hasattr(shader, 'uv_offset'):
            x_offset = shader.uv_offset.u
            y_offset = shader.uv_offset.v
        else:
            x_offset = 0
            y_offset = 0

        if hasattr(shader, 'uv_scale'):
            x_scale = shader.uv_scale.u
            y_scale = shader.uv_scale.v
        else:
            x_scale = 1
            y_scale = 1

        # only the y offset needs conversion, xoffset is the same for the same result
        b_y_offset = 1 - y_offset - y_scale

        # get the clamp (x and y direction)
        if hasattr(shader, 'texture_clamp_mode'):
            clamp_mode = shader.texture_clamp_mode
            if clamp_mode == NifClasses.TexClampMode.WRAP_S_WRAP_T:
                clamp_x = False
                clamp_y = False
            elif clamp_mode == NifClasses.TexClampMode.WRAP_S_CLAMP_T:
                clamp_x = False
                clamp_y = True
            elif clamp_mode == NifClasses.TexClampMode.CLAMP_S_WRAP_T:
                clamp_x = True
                clamp_y = False
            elif clamp_mode == NifClasses.TexClampMode.CLAMP_S_CLAMP_T:
                clamp_x = True
                clamp_y = True
            else:
                clamp_x = False
                clamp_y = False
        else:
            clamp_x = False
            clamp_y = False

        return x_scale, y_scale, x_offset, b_y_offset, clamp_x, clamp_y