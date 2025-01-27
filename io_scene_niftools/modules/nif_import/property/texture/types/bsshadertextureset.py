"""This script contains helper methods to import textures."""
from io_scene_niftools.modules.nif_import.property.node_wrapper import NodeWrapper
from io_scene_niftools.utils.consts import TEX_SLOTS, BS_TEX_SLOTS
# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2025 NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the following
#   disclaimer in the documentation and/or other materials provided
#   with the distribution.
#
# * Neither the name of the NIF File Format Library and Tools
#   project nor the names of its contributors may be used to endorse
#   or promote products derived from this software without specific
#   prior written permission.
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
from io_scene_niftools.utils.logging import NifLog


class BSShaderTextureSet:
    __instance = None
    _nodes_wrapper = None

    def __init__(self):
        """ Virtually private constructor. """
        if BSShaderTextureSet.__instance:
            raise Exception("This class is a singleton!")
        else:
            super().__init__()
            BSShaderTextureSet.__instance = self
            self.node_wrapper = NodeWrapper.get()

    @staticmethod
    def get():
        """ Static access method. """
        if not BSShaderTextureSet.__instance:
            BSShaderTextureSet()
        return BSShaderTextureSet.__instance

    def import_bs_shader_texture_set(self, bs_shader_property, b_mat):

        textures = bs_shader_property.texture_set.textures

        slots = {
            BS_TEX_SLOTS.DIFFUSE_MAP: 0,
            BS_TEX_SLOTS.NORMAL_MAP: 1,
            BS_TEX_SLOTS.GLOW_MAP: 2,
            BS_TEX_SLOTS.PARALLAX_MAP: 3,
            BS_TEX_SLOTS.ENVIRONMENT_MAP: 4,
            BS_TEX_SLOTS.ENVIRONMENT_MASK: 5,
            BS_TEX_SLOTS.SUBSURFACE_TINT_MAP: 6,
            BS_TEX_SLOTS.BACKLIGHT_MAP: 7
        }

        for slot_name, slot_i in slots.items():
            # skip those whose index we don't know from old code
            if slot_i is not None and len(textures) > slot_i:
                tex_str = textures[slot_i]
                # see if it holds a texture
                if tex_str:
                    NifLog.debug(f"Shader has active {slot_name}")
                    self.node_wrapper.create_and_link(slot_name, tex_str)

    def import_bseffectshaderproperty_textures(self, bs_effect_shader_property, b_mat):

        base = bs_effect_shader_property.source_texture
        if base:
            self.node_wrapper.create_and_link(TEX_SLOTS.BASE, base)

        glow = bs_effect_shader_property.greyscale_texture
        if glow:
            self.node_wrapper.create_and_link(TEX_SLOTS.GLOW, glow)

        # self.import_texture_game_properties(b_mat, bs_effect_shader_property)
