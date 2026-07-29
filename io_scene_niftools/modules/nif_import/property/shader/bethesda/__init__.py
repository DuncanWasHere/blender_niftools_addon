"""This script contains helper methods to import BSShaderLightingProperty based properties."""

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


from functools import singledispatch

from ...... import NifLog
from ......modules.nif_import.property.node_wrapper import NodeWrapper
from ......modules.nif_import.property.texture.types.bsshadertextureset import BSShaderTextureSet
from nifgen.formats.nif import classes as NifClasses


class BSShaderProperty():
    """Main interface class for importing Bethesda shader property blocks."""

    __instance = None

    def __init__(self):
        self.node_wrapper = NodeWrapper.get()

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

    def import_shader_file_name(self, n_bs_shader_property):
        """Import the texture a shader names directly.

        These shaders usually sit next to a NiTexturingProperty that already points at
        the same texture, so importing it again would leave a second, unused texture node
        behind. Only load it when nothing has filled the base slot yet.
        """

        file_name = getattr(n_bs_shader_property, "file_name", None)
        if not file_name:
            return
        if self.node_wrapper.b_textures[0] is not None:
            NifLog.debug(f"'{file_name}' is already loaded by the texturing property, so the "
                         f"shader's own copy is skipped")
            return
        self.node_wrapper.create_and_link("base", file_name)

    def __import_fallout_shader_common(self, n_bs_shader_property, b_mat, shader_type):
        """Import the fields shared by all fallout era shader property blocks."""

        b_mat.nif_shader.bs_shadertype = shader_type

        # shader_type only restates which block this is, so it is derived again on export
        # rather than being stored

        self.import_shader_flags(b_mat, n_bs_shader_property.shader_flags)
        self.import_shader_flags(b_mat, n_bs_shader_property.shader_flags_2)

        if hasattr(n_bs_shader_property, "texture_clamp_mode"):
            b_mat.nif_shader.texture_clamp_mode = n_bs_shader_property.texture_clamp_mode.name

        # visually represented values live on the fallout shader group sockets
        self.node_wrapper.shader_values["Environment Map Scale"] = n_bs_shader_property.environment_map_scale

    def __import_bs_shader_pp_lighting_property(self, n_bs_shader_pp_lighting_property, b_mat):
        """Import a BSShaderPPLightingProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_bs_shader_pp_lighting_property, b_mat, 'BSShaderPPLightingProperty')

        # kept on the shader group sockets, alongside everything else the block holds
        shader_values = self.node_wrapper.shader_values
        shader_values["Refraction Strength"] = n_bs_shader_pp_lighting_property.refraction_strength
        shader_values["Refraction Fire Period"] = n_bs_shader_pp_lighting_property.refraction_fire_period
        shader_values["Parallax Max Passes"] = n_bs_shader_pp_lighting_property.parallax_max_passes
        shader_values["Parallax Scale"] = n_bs_shader_pp_lighting_property.parallax_scale

        self.texture_helper.import_bs_shader_texture_set(n_bs_shader_pp_lighting_property, b_mat)

    def __import_bs_shader_no_lighting_property(self, n_bs_shader_no_lighting_property, b_mat):
        """Import a BSShaderNoLightingProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_bs_shader_no_lighting_property, b_mat, 'BSShaderNoLightingProperty')

        # the falloff drives the alpha on the shader group, so it lives on its sockets
        shader_values = self.node_wrapper.shader_values
        shader_values["Falloff Start Angle"] = n_bs_shader_no_lighting_property.falloff_start_angle
        shader_values["Falloff Stop Angle"] = n_bs_shader_no_lighting_property.falloff_stop_angle
        shader_values["Falloff Start Opacity"] = n_bs_shader_no_lighting_property.falloff_start_opacity
        shader_values["Falloff Stop Opacity"] = n_bs_shader_no_lighting_property.falloff_stop_opacity

        self.import_shader_file_name(n_bs_shader_no_lighting_property)

    def __import_bs_lighting_shader_property(self, n_bs_lighting_shader_property, b_mat):

        b_mat.nif_shader.bs_shadertype = 'BSLightingShaderProperty'

        b_mat.nif_shader.bslsp_shaderobjtype = n_bs_lighting_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_lighting_shader_property.shader_flags_1)
        self.import_shader_flags(b_mat, n_bs_lighting_shader_property.shader_flags_2)

        self.texture_helper.import_bs_shader_texture_set(n_bs_lighting_shader_property, b_mat)

        x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y = self.__get_uv_transform(n_bs_lighting_shader_property)
        self.node_wrapper.global_uv_offset_scale(x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y)

        b_shader_node = b_mat.node_tree.nodes["Principled BSDF"]

        # By name, not index: the Principled BSDF reorders its sockets between Blender
        # versions. Hair and skin tint have no Principled equivalent, so they are parked
        # on the tint sockets the exporter reads them back from.
        for n_color, socket_name in ((n_bs_lighting_shader_property.specular_color, 'Specular Tint'),
                                     (n_bs_lighting_shader_property.hair_tint_color, 'Sheen Tint'),
                                     (n_bs_lighting_shader_property.skin_tint_color, 'Coat Tint')):
            b_socket = b_shader_node.inputs.get(socket_name)
            if b_socket is None:
                NifLog.warn(f"The Principled shader has no '{socket_name}' socket, so that "
                            f"colour of '{b_mat.name}' was not imported")
                continue
            b_socket.default_value = (n_color.r, n_color.g, n_color.b, 1)

        # Map glossiness (0.0 - 128.0) to specular IOR level (0.0 - 1.0)
        if not n_bs_lighting_shader_property.glossiness == 0:
            b_shader_node.inputs['Specular IOR Level'].default_value = (1 - (1 / (n_bs_lighting_shader_property.glossiness / 2))) ** 2
        else:
            b_shader_node.inputs['Specular IOR Level'].default_value = 0

        b_shader_node.inputs['Alpha'].default_value = n_bs_lighting_shader_property.alpha

        b_shader_node.inputs['Emission Strength'].default_value = n_bs_lighting_shader_property.emissive_multiple

        # TODO: Add color mult shader node for emissive color

        b_mat.nif_shader.lighting_effect_1 = n_bs_lighting_shader_property.lighting_effect_1
        b_mat.nif_shader.lighting_effect_2 = n_bs_lighting_shader_property.lighting_effect_2

    def __import_bs_effect_shader_property(self, n_bs_effect_shader_property, b_mat):

        b_mat.nif_shader.bs_shadertype = 'BSEffectShaderProperty'

        b_mat.nif_shader.bslsp_shaderobjtype = n_bs_effect_shader_property.shader_type.name

        self.import_shader_flags(b_mat, n_bs_effect_shader_property.shader_flags_1)
        self.import_shader_flags(b_mat, n_bs_effect_shader_property.shader_flags_2)

        self.texture_helper.import_bs_shader_texture_set(n_bs_effect_shader_property, b_mat)

        x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y = self.__get_uv_transform(n_bs_effect_shader_property)
        self.node_wrapper.global_uv_offset_scale(x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y)

        # the effect shader has a node group of its own, so its values go on those sockets
        n_emissive = n_bs_effect_shader_property.emissive_color
        shader_values = self.node_wrapper.shader_values
        shader_values["Emissive Color"] = (n_emissive.r, n_emissive.g, n_emissive.b, 1)
        shader_values["Emissive Mult"] = n_bs_effect_shader_property.emissive_multiple
        shader_values["Alpha"] = n_bs_effect_shader_property.alpha
        shader_values["Falloff Start Angle"] = n_bs_effect_shader_property.falloff_start_angle
        shader_values["Falloff Stop Angle"] = n_bs_effect_shader_property.falloff_stop_angle
        shader_values["Falloff Start Opacity"] = n_bs_effect_shader_property.falloff_start_opacity
        shader_values["Falloff Stop Opacity"] = n_bs_effect_shader_property.falloff_stop_opacity

        b_shader_node.inputs['Emission Strength'].default_value = n_bs_effect_shader_property.emissive_multiple

        # TODO: Add color mult shader node for emissive color

        b_mat.nif_shader.lighting_effect_1 = n_bs_effect_shader_property.lighting_effect_1
        b_mat.nif_shader.lighting_effect_2 = n_bs_effect_shader_property.lighting_effect_2

        # TODO: Add animation controller import

    def __import_sky_shader_property(self, n_sky_shader_property, b_mat):
        """Import a SkyShaderProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_sky_shader_property, b_mat, 'SkyShaderProperty')

        b_mat.nif_shader.sky_object_type = n_sky_shader_property.sky_object_type.name

        if n_sky_shader_property.file_name:
            self.node_wrapper.create_and_link("base", n_sky_shader_property.file_name)

    def __import_tall_grass_shader_property(self, n_tall_grass_shader_property, b_mat):
        """Import a TallGrassShaderProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_tall_grass_shader_property, b_mat, 'TallGrassShaderProperty')

        if n_tall_grass_shader_property.file_name:
            self.node_wrapper.create_and_link("base", n_tall_grass_shader_property.file_name)

    def __import_tile_shader_property(self, n_tile_shader_property, b_mat):
        """Import a TileShaderProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_tile_shader_property, b_mat, 'TileShaderProperty')

        if n_tile_shader_property.file_name:
            self.node_wrapper.create_and_link("base", n_tile_shader_property.file_name)

    def __import_water_shader_property(self, n_water_shader_property, b_mat):
        """Import a WaterShaderProperty block into a Blender shader tree."""

        self.__import_fallout_shader_common(n_water_shader_property, b_mat, 'WaterShaderProperty')

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

    # TODO [texture] Implement clamp on image wrapping
    @staticmethod
    def import_uv_offset(b_mat, shader_prop):
        for texture_slot in b_mat.texture_slots:
            if texture_slot:
                texture_slot.offset.x = shader_prop.uv_offset.u
                texture_slot.offset.y = shader_prop.uv_offset.v

    # TODO [texture] Implement clamp on image wrapping
    @staticmethod
    def import_uv_scale(b_mat, shader_prop):
        for texture_slot in b_mat.texture_slots:
            if texture_slot:
                texture_slot.scale.x = shader_prop.uv_scale.u
                texture_slot.scale.y = shader_prop.uv_scale.v

    # TODO [texture] Implement clamp on image wrapping
    @staticmethod
    def import_clamp(b_mat, shader_prop):
        clamp = shader_prop.texture_clamp_mode
        for texture_slot in b_mat.texture_slots:
            if texture_slot:
                if clamp == 3:
                    texture_slot.image.use_clamp_x = False
                    texture_slot.image.use_clamp_y = False
                if clamp == 2:
                    texture_slot.image.use_clamp_x = False
                    texture_slot.image.use_clamp_y = True
                if clamp == 1:
                    texture_slot.image.use_clamp_x = True
                    texture_slot.image.use_clamp_y = False
                if clamp == 0:
                    texture_slot.image.use_clamp_x = True
                    texture_slot.image.use_clamp_y = True

    # TODO [Shader] Alpha property
    @staticmethod
    def set_alpha_bsshader(b_mat, shader_property):
        NifLog.debug("Alpha prop detected")
        b_mat.use_transparency = True
        b_mat.alpha = (1 - shader_property.alpha)
        b_mat.transparency_method = 'Z_TRANSPARENCY'  # enable z-buffered transparency

    @staticmethod
    def import_shader_flags(b_mat, flags):
        for name in type(flags).__members__:
            if getattr(flags, name):
                b_mat.nif_shader[name] = True
