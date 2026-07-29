"""Main module for exporting Bethesda shader property blocks."""

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

from ......modules.nif_export.block_registry import block_store
from ......modules.nif_export.types import is_skinned
from ......modules.nif_export.property.texture.bethesda import BSShaderTextureSet
from ......modules.nif_export.property.texture.common import TextureCommon
from ......modules.nif_export.property.texture.texture import NiTexturingProperty

from ......utils.logging import NifLog, NifError
from ......utils.math import color_blender_to_nif

from nifgen.formats.nif import classes as NifClasses

# BSShaderProperty.shader_type only ever restates which block it is, so it is derived from
# the block rather than being a setting of its own. The generated class names are used as
# the keys, which is what type(block).__name__ gives.
SHADER_TYPE_BY_BLOCK = {
    'BSShaderPPLightingProperty': NifClasses.BSShaderType.SHADER_DEFAULT,
    'BSShaderNoLightingProperty': NifClasses.BSShaderType.SHADER_NOLIGHTING,
    'TallGrassShaderProperty': NifClasses.BSShaderType.SHADER_TALL_GRASS,
    'SkyShaderProperty': NifClasses.BSShaderType.SHADER_SKY,
    'TileShaderProperty': NifClasses.BSShaderType.SHADER_TILE,
    'WaterShaderProperty': NifClasses.BSShaderType.SHADER_WATER,
}


class BSShaderProperty:
    """Main interface class for exporting Bethesda shader property blocks."""

    def __init__(self):
        self.bs_shader_texture_set_helper = BSShaderTextureSet.get()
        self.ni_texturing_property_helper = NiTexturingProperty.get()

        # whether the geometry currently being exported has a skin instance, which decides
        # the one shader flag that does not come from the material
        self.b_is_skinned = False

    def export_bs_shader_property(self, n_ni_geometry, b_mat=None, b_obj=None):
        """Main function for handling Bethesda shader property export."""

        if b_mat.nif_shader.bs_shadertype == 'None':
            NifLog.warn(f"No shader applied to material '{b_mat}' for mesh "
                        f"'{n_ni_geometry.name}'. It will not be visible in game.")
            return

        self.b_is_skinned = is_skinned(b_obj)

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

    @staticmethod
    def get_fallout_group_value(b_mat, socket_name, default=None):
        """Read a raw nif value from the fallout shader group of the material, if present."""
        b_group_node = TextureCommon.get_fallout_group_node(b_mat)
        if b_group_node:
            b_socket = b_group_node.inputs.get(socket_name)
            if b_socket:
                return b_socket.default_value
        return default

    def export_fallout_shader_common(self, n_bs_shader_property, b_mat):
        """Export the fields shared by all fallout era shader property blocks."""

        n_bs_shader_property.shader_type = SHADER_TYPE_BY_BLOCK.get(type(n_bs_shader_property).__name__,
                                                                   NifClasses.BSShaderType.SHADER_DEFAULT)

        self.export_shader_flags(b_mat, n_bs_shader_property)

        env_map_scale = self.get_fallout_group_value(b_mat, "Environment Map Scale")
        if env_map_scale is not None:
            n_bs_shader_property.environment_map_scale = env_map_scale

        if hasattr(n_bs_shader_property, "texture_clamp_mode"):
            n_bs_shader_property.texture_clamp_mode = NifClasses.TexClampMode[b_mat.nif_shader.texture_clamp_mode]

    def export_bs_shader_pp_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderPPLightingProperty block."""

        n_bs_shader_pp_lighting_property = block_store.create_block("BSShaderPPLightingProperty")

        self.export_fallout_shader_common(n_bs_shader_pp_lighting_property, b_mat)

        n_bs_shader_pp_lighting_property.refraction_strength = self.get_fallout_group_value(
            b_mat, "Refraction Strength", n_bs_shader_pp_lighting_property.refraction_strength)
        n_bs_shader_pp_lighting_property.refraction_fire_period = round(self.get_fallout_group_value(
            b_mat, "Refraction Fire Period", n_bs_shader_pp_lighting_property.refraction_fire_period))
        n_bs_shader_pp_lighting_property.parallax_max_passes = self.get_fallout_group_value(
            b_mat, "Parallax Max Passes", n_bs_shader_pp_lighting_property.parallax_max_passes)
        n_bs_shader_pp_lighting_property.parallax_scale = self.get_fallout_group_value(
            b_mat, "Parallax Scale", n_bs_shader_pp_lighting_property.parallax_scale)

        self.bs_shader_texture_set_helper.export_bs_shader_pp_lighting_property_textures(n_bs_shader_pp_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_pp_lighting_property)

    def export_bs_shader_no_lighting_property(self, n_ni_geometry, b_mat):
        """Export a BSShaderNoLightingProperty block."""

        n_bs_shader_no_lighting_property = block_store.create_block("BSShaderNoLightingProperty")

        self.export_fallout_shader_common(n_bs_shader_no_lighting_property, b_mat)

        for n_field, socket_name in (("falloff_start_angle", "Falloff Start Angle"),
                                     ("falloff_stop_angle", "Falloff Stop Angle"),
                                     ("falloff_start_opacity", "Falloff Start Opacity"),
                                     ("falloff_stop_opacity", "Falloff Stop Opacity")):
            setattr(n_bs_shader_no_lighting_property, n_field,
                    self.get_fallout_group_value(b_mat, socket_name,
                                                 getattr(n_bs_shader_no_lighting_property, n_field)))

        # These shaders name their texture themselves and are also given a
        # NiTexturingProperty pointing at the same one, which is what any texture
        # transform animation is attached to.
        self.ni_texturing_property_helper.export_ni_texturing_property(
            b_mat, n_ni_geometry, n_bs_shader_no_lighting_property)

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_bs_shader_no_lighting_property)

        n_ni_geometry.add_property(n_bs_shader_no_lighting_property)

    def export_bs_lighting_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSLightingShaderProperty block."""

        n_bs_lighting_shader_property = block_store.create_block("BSLightingShaderProperty")

        n_bs_shader_type = NifClasses.BSLightingShaderType[b_mat.nif_shader.bslsp_shaderobjtype]
        n_bs_lighting_shader_property.skyrim_shader_type = NifClasses.BSLightingShaderType[n_bs_shader_type]

        self.bs_shader_texture_set_helper.export_bs_lighting_shader_property_textures(n_bs_lighting_shader_property)

        b_principled_bsdf = next((node for node in b_mat.node_tree.nodes if isinstance(node, bpy.types.ShaderNodeBsdfPrincipled)), None)

        if b_principled_bsdf is None:
            raise NifError(f"{b_mat.name} must have a Principled BSDF to export a BSLightingShaderProperty!")

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
                                b_principled_bsdf.inputs['Specular Tint'].default_value)

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

        self.export_shader_flags(b_mat, n_bs_lighting_shader_property)

        n_ni_geometry.shader_property = n_bs_lighting_shader_property

    def export_bs_effect_shader_property(self, n_ni_geometry, b_mat):
        """Export a BSEffectShaderProperty block."""

        n_bs_effect_shader_property = block_store.create_block("BSEffectShaderProperty")

        self.bs_shader_texture_set_helper.export_bs_effect_shader_property_textures(n_bs_effect_shader_property)

        # TODO [shader]: Add support for other BSEffectShaderProperty properties

        # read back from the effect shader's own node group
        b_group_node = TextureCommon.get_fallout_group_node(b_mat)
        if b_group_node is not None:
            n_emissive = n_bs_effect_shader_property.emissive_color
            n_emissive.r, n_emissive.g, n_emissive.b = b_group_node.inputs["Emissive Color"].default_value[:3]
            n_bs_effect_shader_property.emissive_multiple = b_group_node.inputs["Emissive Mult"].default_value
            n_bs_effect_shader_property.alpha = b_group_node.inputs["Alpha"].default_value

            for n_field, socket_name in (("falloff_start_angle", "Falloff Start Angle"),
                                         ("falloff_stop_angle", "Falloff Stop Angle"),
                                         ("falloff_start_opacity", "Falloff Start Opacity"),
                                         ("falloff_stop_opacity", "Falloff Stop Opacity")):
                setattr(n_bs_effect_shader_property, n_field,
                        b_group_node.inputs[socket_name].default_value)

        self.export_shader_flags(b_mat, n_bs_effect_shader_property)

        n_ni_geometry.shader_property = n_bs_effect_shader_property

    def export_sky_shader_property(self, n_ni_geometry, b_mat):
        """Export a SkyShaderProperty block."""

        n_sky_shader_property = block_store.create_block("SkyShaderProperty")

        self.export_fallout_shader_common(n_sky_shader_property, b_mat)

        n_sky_shader_property.sky_object_type = NifClasses.SkyObjectType[b_mat.nif_shader.sky_object_type]

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_sky_shader_property)

        n_ni_geometry.add_property(n_sky_shader_property)

    def export_tall_grass_shader_property(self, n_ni_geometry, b_mat):
        """Export a TallGrassShaderProperty block."""

        n_tall_grass_shader_property = block_store.create_block("TallGrassShaderProperty")

        self.export_fallout_shader_common(n_tall_grass_shader_property, b_mat)

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_tall_grass_shader_property)

        n_ni_geometry.add_property(n_tall_grass_shader_property)

    def export_tile_shader_property(self, n_ni_geometry, b_mat):
        """Export a TileShaderProperty block."""

        n_tile_shader_property = block_store.create_block("TileShaderProperty")

        self.export_fallout_shader_common(n_tile_shader_property, b_mat)

        self.bs_shader_texture_set_helper.export_misc_shader_property_textures(n_tile_shader_property)

        n_ni_geometry.add_property(n_tile_shader_property)

    def export_water_shader_property(self, n_ni_geometry, b_mat):
        """Export a WaterShaderProperty block."""

        n_water_shader_property = block_store.create_block("WaterShaderProperty")

        self.export_fallout_shader_common(n_water_shader_property, b_mat)

        n_ni_geometry.add_property(n_water_shader_property)
        
    def export_shader_flags(self, b_mat, n_bs_shader_property):
        """Export shader flags for a BSShaderProperty block."""

        if hasattr(n_bs_shader_property, 'shader_flags'):
            n_shader_flags = n_bs_shader_property.shader_flags
            BSShaderProperty.process_flags(b_mat, n_shader_flags)
            self.set_skinned_flag(n_shader_flags)

        if hasattr(n_bs_shader_property, 'shader_flags_1'):
            n_shader_flags_1 = n_bs_shader_property.shader_flags_1
            BSShaderProperty.process_flags(b_mat, n_shader_flags_1)
            self.set_skinned_flag(n_shader_flags_1)

        if hasattr(n_bs_shader_property, 'shader_flags_2'):
            n_shader_flags_2 = n_bs_shader_property.shader_flags_2
            BSShaderProperty.process_flags(b_mat, n_shader_flags_2)

        return n_bs_shader_property

    def set_skinned_flag(self, n_bs_shader_flags):
        """
        Turn the skinned flag on for geometry that is exported with a skin instance.

        This is the one shader flag that describes the mesh rather than the material, so it is
        the only one worth deriving; a skinned mesh whose shader does not claim to be skinned
        renders in its bind pose. Flags the material set are left alone, so the checkbox stays
        the authority for everything else.
        """

        # the bitfield members are descriptors that only resolve against an instance, so
        # asking the class for the attribute is not a way to find out whether it has one
        if self.b_is_skinned and 'skinned' in n_bs_shader_flags.__members__:
            n_bs_shader_flags.skinned = True

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
