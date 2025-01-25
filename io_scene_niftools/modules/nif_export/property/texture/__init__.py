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
from io_scene_niftools.modules.nif_export.property.shader.bethesda import BSShaderProperty

from io_scene_niftools.modules.nif_export.property.texture.common import TextureWriter
from io_scene_niftools.utils.consts import TEX_SLOTS
from io_scene_niftools.utils.logging import NifLog, NifError


class TextureProperty:
    # Maps shader node input sockets to image texture nodes and NIF texture slots
    TEX_SLOT_MAP = {
        TEX_SLOTS.BASE: {"shader_type": bpy.types.ShaderNodeBsdfPrincipled,
                         "socket_index": 0, "texture_type": bpy.types.ShaderNodeTexImage},  # Base Color
        TEX_SLOTS.NORMAL: {"shader_type": bpy.types.ShaderNodeBsdfPrincipled,
                           "socket_index": 5, "texture_type": bpy.types.ShaderNodeTexImage},  # Normal
        TEX_SLOTS.GLOW: {"shader_type": bpy.types.ShaderNodeBsdfPrincipled,
                         "socket_index": 27, "texture_type": bpy.types.ShaderNodeTexImage},  # Emissive Color
        TEX_SLOTS.DETAIL: {"shader_type": bpy.types.ShaderNodeOutputMaterial,
                           "socket_index": 2, "texture_type": bpy.types.ShaderNodeTexImage},  # Displacement
        TEX_SLOTS.ENV_MAP: {"shader_type": bpy.types.ShaderNodeBsdfAnisotropic,
                            "socket_index": 0, "texture_type": bpy.types.ShaderNodeTexEnvironment},  # Color
        TEX_SLOTS.ENV_MASK: {"shader_type": bpy.types.ShaderNodeBsdfAnisotropic,
                             "socket_index": 1, "texture_type": bpy.types.ShaderNodeTexImage}  # Roughness
    }

    def __init__(self):
        self.dict_mesh_uvlayers = []
        self.texture_writer = TextureWriter()
        self.bs_shader_property_helper = BSShaderProperty()

        self.b_mat = None

        self.slots = {}
        self._reset_fields()

    def export_textures(self, b_mat, n_node):
        if bpy.context.scene.niftools_scene.is_fo3() or bpy.context.scene.niftools_scene.is_skyrim():
            self.bs_shader_property_helper.export_bs_shader_property(n_node, b_mat)
        else:
            if bpy.context.scene.niftools_scene.game in self.ni_texturing_property_helper.USED_EXTRA_SHADER_TEXTURES:
                # sid meier's railroad and civ4: set shader slots in extra data
                self.ni_texturing_property_helper.add_shader_integer_extra_datas(n_node)

            n_nitextureprop = self.ni_texturing_property_helper.export_texturing_property(
                flags=0x0001,  # standard
                # TODO [object][texture][material] Move out and break dependency
                applymode=self.ni_texturing_property_helper.get_n_apply_mode_from_b_blend_type('MIX'),
                b_mat=b_mat)

            block_store.register_block(n_nitextureprop)
            n_node.add_property(n_nitextureprop)

    def _reset_fields(self):
        """Reset all slot assignments."""
        self.slots = {slot: None for slot in self.TEX_SLOT_MAP.keys()}

    def get_input_node_of_type(self, input_socket, node_types):
        # search back in the node tree for nodes of a certain type(s), depth-first
        links = input_socket.links
        if not links:
            # this socket has no inputs
            return None
        node = links[0].from_node
        if isinstance(node, node_types):
            # the input node is of the required type
            return node
        else:
            if len(node.inputs) > 0:
                for input in node.inputs:
                    # check every input if somewhere up that tree is a node of the required type
                    input_results = self.get_input_node_of_type(input, node_types)
                    if input_results:
                        return input_results
                # we found nothing
                return None
            else:
                # this has no inputs, and doesn't classify itself
                return None

    def determine_texture_types(self, b_mat):
        """Determine texture slots based on shader node connections."""
        self._reset_fields()

        shader_nodes = self._get_shader_nodes(b_mat)
        for shader_node in shader_nodes:
            for slot_name, mapping in self.TEX_SLOT_MAP.items():
                if isinstance(shader_node, mapping["shader_type"]):
                    input_socket = shader_node.inputs[mapping["socket_index"]]
                    if input_socket.is_linked:
                        texture_node = self.get_input_node_of_type(input_socket, mapping["texture_type"])
                        if texture_node:
                            self._assign_texture_to_slot(slot_name, texture_node, b_mat.name)

    def _get_shader_nodes(self, b_mat):
        """Retrieve all shader nodes in the material."""
        return [node for node in b_mat.node_tree.nodes if isinstance(node, bpy.types.ShaderNode)]

    def _assign_texture_to_slot(self, slot_name, texture_node, mat_name):
        """Assign a texture node to a slot, ensuring no duplicates."""
        if self.slots[slot_name]:
            raise NifError(f"Multiple textures assigned to slot '{slot_name}' in material '{mat_name}'.")
        self.slots[slot_name] = texture_node
        NifLog.info(f"Assigned texture node '{texture_node.name}' to slot '{slot_name}'")
