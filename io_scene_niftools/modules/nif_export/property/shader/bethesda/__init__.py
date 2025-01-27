"""Main module for exporting Bethesda shader property blocks."""

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


import io_scene_niftools.utils.logging
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.property.texture.bethesda import BSShaderTextureSet
from io_scene_niftools.modules.nif_export.property.texture.texture import NiTexturingProperty
from io_scene_niftools.utils.consts import FLOAT_MAX
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BSShaderProperty:
    """Main interface class for exporting Bethesda shader property blocks."""

    def __init__(self):
        self.bs_shader_texture_set_helper = BSShaderTextureSet.get()
        self.ni_texturing_property_helper = NiTexturingProperty.get()

    def export_bs_shader_property(self, n_ni_geometry, b_mat=None):
        """Main function for handling Bethesda shader property export."""

        if b_mat.nif_shader.bs_shadertype == 'None':
            io_scene_niftools.NifLog.warn(f"No shader applied to material '{b_mat}' for mesh "
                                          f"'{n_ni_geometry.name}'. It will not be visible in game.")
            return

        self.bs_shader_texture_set_helper.determine_texture_types(b_mat)

        if b_mat.nif_shader.bs_shadertype == 'BSShaderPPLightingProperty':
            self.export_bs_shader_pp_lighting_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'BSLightingShaderProperty':
            self.export_bs_lighting_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'BSEffectShaderProperty':
            self.export_bs_effect_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'BSShaderNoLightingProperty':
            self.export_bs_shader_no_lighting_property(n_ni_geometry, b_mat)

    def export_bs_effect_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSEffectShaderProperty block."""

        n_bs_effect_shader_property = block_store.create_block("BSEffectShaderProperty")

        self.bs_shader_texture_set_helper.export_bs_effect_shader_property_textures(n_bs_effect_shader_property)

        # Emissive
        BSShaderProperty.set_color3_property(n_bs_effect_shader_property.base_color, b_mat.nif_material.emissive_alpha)
        n_bs_effect_shader_property.base_color.a = b_mat.nif_material.emissive_alpha.v
        # TODO [shader] Expose a emission multiplier value
        # bsshader.base_color_scale = b_mat.emit

        BSShaderProperty.export_shader_flags(b_mat, n_bs_effect_shader_property)

        n_ni_geometry.shader_property = n_bs_effect_shader_property

    def export_bs_lighting_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSLightingShaderProperty block."""

        n_bs_lighting_shader_property = block_store.create_block("BSLightingShaderProperty")

        b_s_type = NifClasses.BSLightingShaderType[b_mat.nif_shader.bslsp_shaderobjtype]
        n_bs_lighting_shader_property.skyrim_shader_type = NifClasses.BSLightingShaderType[
            b_mat.nif_shader.bslsp_shaderobjtype]

        self.bs_shader_texture_set_helper.export_bs_lighting_shader_property_textures(n_bs_lighting_shader_property)

        # Diffuse color
        b_diffuse_color = b_mat.diffuse_color

        if b_s_type == NifClasses.BSLightingShaderType.SKIN_TINT:
            BSShaderProperty.set_color3_property(n_bs_lighting_shader_property.skin_tint_color, b_diffuse_color)
        elif b_s_type == NifClasses.BSLightingShaderType.HAIR_TINT:
            BSShaderProperty.set_color3_property(n_bs_lighting_shader_property.hair_tint_color, b_diffuse_color)
        # TODO [shader]: Expose intensity value
        # b_mat.diffuse_intensity = 1.0

        n_bs_lighting_shader_property.lighting_effect_1 = b_mat.nif_material.lightingeffect1
        n_bs_lighting_shader_property.lighting_effect_2 = b_mat.nif_material.lightingeffect2

        # TODO [shader]: Get emissive properties from shader nodes
        #BSShaderProperty.set_color3_property(n_bs_lighting_shader_property.emissive_color,
        #                                     b_mat.nif_material.emissive_color)
        # bsshader.emissive_multiple = b_mat.emit

        # TODO [shader]: Get roughness properties from shader nodes
        #n_bs_lighting_shader_property.glossiness = 1 / b_mat.roughness - 1 if b_mat.roughness != 0 else FLOAT_MAX

        # TODO [shader]: Get specular properties from shader nodes
        #BSShaderProperty.set_color3_property(n_bs_lighting_shader_property.specular_color, b_mat.specular_color)
        #n_bs_lighting_shader_property.specular_strength = b_mat.specular_intensity

        # TODO [shader]: Get alpha properties from shader nodes
        # if b_mat.use_transparency:
        #     bsshader.alpha = (1 - b_mat.alpha)

        BSShaderProperty.export_shader_flags(b_mat, n_bs_lighting_shader_property)

        n_ni_geometry.shader_property = n_bs_lighting_shader_property

    def export_bs_shader_pp_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderPPLightingProperty block."""

        n_bs_shader_pp_lighting_property = block_store.create_block("BSShaderPPLightingProperty")

        n_bs_shader_pp_lighting_property.shader_type = NifClasses.BSShaderType[
            b_mat.nif_shader.bsspplp_shaderobjtype]

        self.bs_shader_texture_set_helper.export_bs_shader_pp_lighting_property_textures(
            n_bs_shader_pp_lighting_property)

        BSShaderProperty.export_shader_flags(b_mat, n_bs_shader_pp_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_pp_lighting_property)

    def export_bs_shader_no_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderNoLightingProperty block."""

        n_bs_shader_no_lighting_property = block_store.create_block("BSShaderNoLightingProperty")

        n_bs_shader_no_lighting_property.shader_type = NifClasses.BSShaderType[
            b_mat.nif_shader.bsspplp_shaderobjtype]

        n_ni_texturing_property = self.ni_texturing_property_helper.export_ni_texturing_property(b_mat, n_ni_geometry)

        BSShaderProperty.export_shader_flags(b_mat, n_bs_shader_no_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_no_lighting_property)

    def export_sky_shader_property(self, n_ni_geometry, b_mat):
        """Export a SkyShaderProperty block."""

        pass

    def export_tall_grass_shader_property(self, n_ni_geometry, b_mat):
        """Export a TallGrassShaderProperty block."""

        pass

    def export_tile_shader_property(self, n_ni_geometry, b_mat):
        """Export a TileShaderProperty block."""

        pass

    def export_water_shader_property(self, n_ni_geometry, b_mat):
        """Export a WaterShaderProperty block."""

        pass

    @staticmethod
    def export_shader_flags(b_mat, n_bs_shader_property):
        """Export shader flags for a BSShaderProperty block."""

        if hasattr(n_bs_shader_property, 'shader_flags'):
            n_shader_flags = n_bs_shader_property.shader_flags
            BSShaderProperty.process_flags(b_mat, n_shader_flags)

        if hasattr(n_bs_shader_property, 'shader_flags_1'):
            n_shader_flags_1 = n_bs_shader_property.shader_flags_1
            BSShaderProperty.process_flags(b_mat, n_shader_flags_1)

        if hasattr(n_bs_shader_property, 'shader_flags_2'):
            n_shader_flags_2 = n_bs_shader_property.shader_flags_2
            BSShaderProperty.process_flags(b_mat, n_shader_flags_2)

        return n_bs_shader_property

    @staticmethod
    def process_flags(b_mat, n_shader_flags):
        """Set shader flags for a BSShaderProperty block from Blender properties."""

        b_flag_list = b_mat.nif_shader.bl_rna.properties.keys()
        for sf_flag in n_shader_flags.__members__:
            if sf_flag in b_flag_list:
                b_flag = b_mat.nif_shader.get(sf_flag)
                if b_flag:
                    setattr(n_shader_flags, sf_flag, True)
                else:
                    setattr(n_shader_flags, sf_flag, False)

    @staticmethod
    def set_color3_property(n_property, b_color):
        """Export shader flags for a BSShaderProperty block."""

        n_property.r = b_color[0]
        n_property.g = b_color[1]
        n_property.b = b_color[2]
