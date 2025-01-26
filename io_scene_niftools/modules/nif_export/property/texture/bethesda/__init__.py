"""Main module for exporting Bethesda shader textures."""

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


from io_scene_niftools.modules.nif_export.property.texture.common import TextureCommon
from io_scene_niftools.utils.consts import TEX_SLOTS
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BSShaderTextureSet(TextureCommon):
    __instance = None

    @staticmethod
    def get():
        """Static access method."""
        if BSShaderTextureSet.__instance is None:
            BSShaderTextureSet()
        return BSShaderTextureSet.__instance

    def __init__(self):
        """Virtually private constructor."""
        if BSShaderTextureSet.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            super().__init__()
            BSShaderTextureSet.__instance = self

    def export_bs_effect_shader_property_textures(self, n_bs_effect_shader_property):
        """Export a BSEffectShaderProperty block."""
        n_bs_effect_shader_property.texture_set = self.__export_bs_shader_texture_set()

        if self.slots[TEX_SLOTS.BASE]:
            n_bs_effect_shader_property.source_texture = TextureCommon.export_texture_filename(
                self.slots[TEX_SLOTS.BASE])
        if self.slots[TEX_SLOTS.GLOW]:
            n_bs_effect_shader_property.greyscale_texture = TextureCommon.export_texture_filename(
                self.slots[TEX_SLOTS.GLOW])

        # get the offset, scale and UV wrapping mode and set them
        self.export_uv_transform(n_bs_effect_shader_property)

    def export_bs_lighting_shader_property_textures(self, n_bs_lighting_shader_property):
        n_bs_shader_texture_set = self.__export_bs_shader_texture_set()
        n_bs_lighting_shader_property.texture_set = n_bs_shader_texture_set

        # Add in extra texture slots
        n_bs_shader_texture_set.num_textures = 9
        existing_textures = n_bs_shader_texture_set.textures[:]
        n_bs_shader_texture_set.reset_field("textures")
        n_bs_shader_texture_set.textures[:len(existing_textures)] = existing_textures

        if self.slots[TEX_SLOTS.DECAL_0]:
            n_bs_shader_texture_set.textures[6] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.DECAL_0])

        if self.slots[TEX_SLOTS.GLOSS]:
            n_bs_shader_texture_set.textures[7] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.GLOSS])

        # get the offset, scale and UV wrapping mode and set them
        self.export_uv_transform(n_bs_lighting_shader_property)

    def export_bs_shader_pp_lighting_property_textures(self, n_bs_shader_pp_lighting_property):
        n_bs_shader_pp_lighting_property.texture_set = self.__export_bs_shader_texture_set()

    def __export_bs_shader_texture_set(self):
        n_bs_shader_texture_set = NifClasses.BSShaderTextureSet(NifData.data)

        if self.slots[TEX_SLOTS.BASE]:
            n_bs_shader_texture_set.textures[0] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.BASE])

        if self.slots[TEX_SLOTS.NORMAL]:
            n_bs_shader_texture_set.textures[1] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.NORMAL])

        if self.slots[TEX_SLOTS.GLOW]:
            n_bs_shader_texture_set.textures[2] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.GLOW])

        if self.slots[TEX_SLOTS.DETAIL]:
            n_bs_shader_texture_set.textures[3] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.DETAIL])

        if self.slots[TEX_SLOTS.ENV_MAP]:
            n_bs_shader_texture_set.textures[4] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.ENV_MAP])

        if self.slots[TEX_SLOTS.ENV_MASK]:
            n_bs_shader_texture_set.textures[5] = TextureCommon.export_texture_filename(self.slots[TEX_SLOTS.ENV_MASK])

        return n_bs_shader_texture_set

    def export_uv_transform(self, shader):
        # get the offset, scale and UV wrapping mode and set them
        x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y = self.get_global_uv_transform_clip()
        # default values for if they haven't been defined:
        if x_scale is None:
            x_scale = 1
        if y_scale is None:
            y_scale = 1
        if x_offset is None:
            x_offset = 0
        if y_offset is None:
            y_offset = 0
        else:
            # need to translate blender offset to nif offset to get the same results
            y_offset = 1 - y_scale - y_offset
        if clamp_x is None:
            clamp_x = False
        if clamp_y is None:
            clamp_y = False

        if hasattr(shader, "uv_scale"):
            shader.uv_scale.u = x_scale
            shader.uv_scale.v = y_scale

        if hasattr(shader, 'uv_offset'):
            shader.uv_offset.u = x_offset
            shader.uv_offset.v = y_offset

        # Texture Clamping mode
        if hasattr(shader, 'texture_clamp_mode'):
            if self.slots[TEX_SLOTS.BASE] and (self.slots[TEX_SLOTS.BASE].extension == "CLIP"):
                # if the extension is clip, we know the wrap mode is clamp for both,
                shader.texture_clamp_mode = NifClasses.TexClampMode.CLAMP_S_CLAMP_T
            else:
                # otherwise, look at the given clip modes from the nodes
                if not clamp_x:
                    wrap_s = 2
                else:
                    wrap_s = 0
                if not clamp_y:
                    wrap_t = 1
                else:
                    wrap_t = 0
                shader.texture_clamp_mode = NifClasses.TexClampMode.from_value(wrap_s + wrap_t)

        return shader
