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


import bpy

import io_scene_niftools.utils.logging
import io_scene_niftools.utils.math

from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.property.texture.bethesda import BSShaderTextureSet
from io_scene_niftools.modules.nif_export.property.texture.texture import NiTexturingProperty
from io_scene_niftools.utils.math import color_blender_to_nif

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
        elif b_mat.nif_shader.bs_shadertype == 'BSShaderNoLightingProperty':
            self.export_bs_shader_no_lighting_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'BSLightingShaderProperty':
            self.export_bs_lighting_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'BSEffectShaderProperty':
            self.export_bs_effect_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'SkyShaderProperty':
            self.export_sky_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'TallGrassShaderProperty':
            self.export_tall_grass_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'TileShaderProperty':
            self.export_tile_shader_property(n_ni_geometry, b_mat)
        elif b_mat.nif_shader.bs_shadertype == 'WaterShaderProperty':
            self.export_water_shader_property(n_ni_geometry, b_mat)

    def export_bs_shader_pp_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderPPLightingProperty block."""

        n_bs_shader_pp_lighting_property = block_store.create_block("BSShaderPPLightingProperty")

        n_bs_shader_pp_lighting_property.shader_type = NifClasses.BSShaderType[
            b_mat.nif_shader.bsspplp_shaderobjtype]

        self.bs_shader_texture_set_helper.export_bs_shader_pp_lighting_property_textures(n_bs_shader_pp_lighting_property)

        BSShaderProperty.export_shader_flags(b_mat, n_bs_shader_pp_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_pp_lighting_property)

    def export_bs_shader_no_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderNoLightingProperty block."""

        n_bs_shader_no_lighting_property = block_store.create_block("BSShaderNoLightingProperty")

        n_bs_shader_no_lighting_property.shader_type = NifClasses.BSShaderType[b_mat.nif_shader.bsspplp_shaderobjtype]

        self.ni_texturing_property_helper.export_ni_texturing_property(b_mat, n_ni_geometry)

        BSShaderProperty.export_shader_flags(b_mat, n_bs_shader_no_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_no_lighting_property)

    def export_bs_lighting_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSLightingShaderProperty block."""

        n_bs_lighting_shader_property = block_store.create_block("BSLightingShaderProperty")

        n_bs_shader_type = NifClasses.BSLightingShaderType[b_mat.nif_shader.bslsp_shaderobjtype]
        n_bs_lighting_shader_property.skyrim_shader_type = NifClasses.BSLightingShaderType[n_bs_shader_type]

        self.bs_shader_texture_set_helper.export_bs_lighting_shader_property_textures(n_bs_lighting_shader_property)

        if b_mat.use_nodes:
            b_principled_bsdf = b_mat.node_tree.nodes["Principled BSDF"]

            if b_principled_bsdf.inputs['Emission Color'].is_linked:
                b_color_node = b_principled_bsdf.inputs['Emission Color'].links[0].from_node
                if isinstance(b_color_node, bpy.types.ShaderNodeMixRGB):
                    color_blender_to_nif(n_bs_lighting_shader_property.emissive_color, b_color_node)
            else:
                color_blender_to_nif(n_bs_lighting_shader_property.emissive_color,
                                     b_principled_bsdf.inputs['Emission Color'].default_value)

            n_bs_lighting_shader_property.emissive_multiple = b_principled_bsdf.inputs[
                'Emission Strength'].default_value

            # TODO [shader]: Set up math node for diffuse map alpha * shader alpha
            n_bs_lighting_shader_property.alpha = b_principled_bsdf.inputs['Alpha'].default_value

            # Map specular IOR level (0.0 - 1.0) to glossiness (0.0 - 999.0)
            n_bs_lighting_shader_property.glossiness = (1 - b_principled_bsdf.inputs[
                'Specular IOR Level'].default_value) * 999

            color_blender_to_nif(n_bs_lighting_shader_property.specular_color,
                                 b_principled_bsdf.inputs['Specular Color'].default_value)

            # TODO [shader]: Set up math node for normal map alpha * shader specular strength

            if n_bs_shader_type == NifClasses.BSLightingShaderType.SKIN_TINT:
                color_blender_to_nif(n_bs_lighting_shader_property.skin_tint_color,
                                     b_principled_bsdf.inputs['Coat Tint'].default_value)
            elif n_bs_shader_type == NifClasses.BSLightingShaderType.HAIR_TINT:
                color_blender_to_nif(n_bs_lighting_shader_property.hair_tint_color,
                                     b_principled_bsdf.inputs['Sheen Tint'].default_value)

            # TODO [shader]: Add support for other Skyrim shader type properties

        n_bs_lighting_shader_property.lighting_effect_1 = b_mat.nif_shader.lighting_effect_1
        n_bs_lighting_shader_property.lighting_effect_2 = b_mat.nif_shader.lighting_effect_2

        BSShaderProperty.export_shader_flags(b_mat, n_bs_lighting_shader_property)

        n_ni_geometry.shader_property = n_bs_lighting_shader_property

    def export_bs_effect_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSEffectShaderProperty block."""

        n_bs_effect_shader_property = block_store.create_block("BSEffectShaderProperty")

        self.bs_shader_texture_set_helper.export_bs_effect_shader_property_textures(n_bs_effect_shader_property)

        if b_mat.use_nodes:
            # TODO [shader]: Add support for other BSEffectShaderProperty properties

            b_principled_bsdf = b_mat.node_tree.nodes["Principled BSDF"]

            if b_principled_bsdf.inputs['Emission Color'].is_linked:
                b_color_node = b_principled_bsdf.inputs['Emission Color'].links[0].from_node
                if isinstance(b_color_node, bpy.types.ShaderNodeMixRGB):
                    color_blender_to_nif(n_bs_effect_shader_property.emissive_color, b_color_node)
            else:
                color_blender_to_nif(n_bs_effect_shader_property.emissive_color,
                                     b_principled_bsdf.inputs['Emission Color'].default_value)

            n_bs_effect_shader_property.emissive_multiple = b_principled_bsdf.inputs[
                'Emission Strength'].default_value

        BSShaderProperty.export_shader_flags(b_mat, n_bs_effect_shader_property)

        n_ni_geometry.shader_property = n_bs_effect_shader_property

    def export_sky_shader_property(self, n_ni_geometry, b_mat):
        """Export a SkyShaderProperty block."""

        n_sky_shader_property = block_store.create_block("SkyShaderProperty")

        n_sky_shader_property.shader_type = NifClasses.BSShaderType[b_mat.nif_shader.bsspplp_shaderobjtype]
        n_sky_shader_property.sky_object_type = NifClasses.SkyObjectType[b_mat.nif_shader.sky_object_type]

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_sky_shader_property)

        BSShaderProperty.export_shader_flags(b_mat, n_sky_shader_property)

        n_ni_geometry.add_property(n_sky_shader_property)

    def export_tall_grass_shader_property(self, n_ni_geometry, b_mat):
        """Export a TallGrassShaderProperty block."""

        n_tall_grass_shader_property = block_store.create_block("TallGrassShaderProperty")

        n_tall_grass_shader_property.shader_type = NifClasses.BSShaderType[b_mat.nif_shader.bsspplp_shaderobjtype]

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_tall_grass_shader_property)

        BSShaderProperty.export_shader_flags(b_mat, n_tall_grass_shader_property)

        n_ni_geometry.add_property(n_tall_grass_shader_property)

    def export_tile_shader_property(self, n_ni_geometry, b_mat):
        """Export a TileShaderProperty block."""

        n_tile_shader_property = block_store.create_block("TileShaderProperty")

        n_tile_shader_property.shader_type = NifClasses.BSShaderType[b_mat.nif_shader.bsspplp_shaderobjtype]

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_tile_shader_property)

        BSShaderProperty.export_shader_flags(b_mat, n_tile_shader_property)

        n_ni_geometry.add_property(n_tile_shader_property)
    
    def export_water_shader_property(self, n_ni_geometry, b_mat):
        """Export a WaterShaderProperty block."""

        n_water_shader_property = block_store.create_block("WaterShaderProperty")

        n_water_shader_property.shader_type = NifClasses.BSShaderType[b_mat.nif_shader.bsspplp_shaderobjtype]

        BSShaderProperty.export_shader_flags(b_mat, n_water_shader_property)

        n_ni_geometry.add_property(n_water_shader_property)
        
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
    def process_flags(b_mat, n_bs_shader_flags):
        """Set shader flags for a BSShaderProperty block from Blender properties."""

        b_flag_list = b_mat.nif_shader.bl_rna.properties.keys()
        for sf_flag in n_bs_shader_flags.__members__:
            if sf_flag in b_flag_list:
                b_flag = b_mat.nif_shader.get(sf_flag)
                if b_flag:
                    setattr(n_bs_shader_flags, sf_flag, True)
                else:
                    setattr(n_bs_shader_flags, sf_flag, False)
