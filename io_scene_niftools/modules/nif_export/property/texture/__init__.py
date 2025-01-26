"""Classes for exporting NIF texture property blocks."""

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
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.property.shader.bethesda import BSShaderProperty
from io_scene_niftools.modules.nif_export.property.texture.texture import NiTexturingProperty
from io_scene_niftools.utils.logging import NifLog, NifError


class TextureProperty:
    """Main interface class for exporting NIF texture property blocks."""

    def __init__(self):
        self.bs_shader_property_helper = BSShaderProperty()
        self.ni_texturing_property_helper = NiTexturingProperty.get()

    def export_texture_properties(self, b_mat, n_node):
        """Main function for handling texture property export."""

        if bpy.context.scene.niftools_scene.is_fo3() or bpy.context.scene.niftools_scene.is_skyrim():
            self.bs_shader_property_helper.export_bs_shader_property(n_node, b_mat)
        else:
            if bpy.context.scene.niftools_scene.game in self.ni_texturing_property_helper.USED_EXTRA_SHADER_TEXTURES:
                # Sid Meier's Railroads and Civ4: set shader slots in extra data
                self.ni_texturing_property_helper.add_shader_integer_extra_datas(n_node)

            n_ni_texturing_property = self.ni_texturing_property_helper.export_ni_texturing_property(b_mat,
                applymode=self.ni_texturing_property_helper.get_n_apply_mode_from_b_blend_type('MIX'))

            n_node.add_property(n_ni_texturing_property)
