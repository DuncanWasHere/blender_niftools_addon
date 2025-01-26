"""Helper methods for exporting texture sources."""

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


import os.path

import bpy
import io_scene_niftools
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.utils.consts import TEX_SLOTS
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData
from io_scene_niftools.utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses


class TextureCommon:
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
        self.slots = {}
        self._reset_fields()

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

    @staticmethod
    def export_source_texture(n_texture=None, filename=None):
        """Export a NiSourceTexture.

        :param n_texture: The n_texture object in blender to be exported.
        :param filename: The full or relative path to the n_texture file
            (this argument is used when exporting NiFlipControllers
            and when exporting default shader slots that have no use in
            being imported into Blender).
        :return: The exported NiSourceTexture block.
        """

        # create NiSourceTexture
        srctex = NifClasses.NiSourceTexture(NifData.data)
        srctex.use_external = True
        if filename is not None:
            # preset filename
            srctex.file_name = filename
        elif n_texture is not None:
            srctex.file_name = TextureCommon.export_texture_filename(n_texture)
        else:
            # this probably should not happen
            NifLog.warn("Exporting source texture without texture or filename (bug?).")

        # fill in default values (TODO: can we use 6 for everything?)
        if bpy.context.scene.niftools_scene.nif_version >= 0x0A000100:
            srctex.pixel_layout = 6
        else:
            srctex.pixel_layout = 5
        srctex.use_mipmaps = 1
        srctex.alpha_format = 3
        srctex.unknown_byte = 1

        # search for duplicate
        for block in block_store.block_to_obj:
            if isinstance(block, NifClasses.NiSourceTexture) and block.get_hash() == srctex.get_hash():
                return block

        # no identical source texture found, so use and register the new one
        return block_store.register_block(srctex, n_texture)

    def export_tex_desc(self, texdesc=None, uv_set=0, b_texture_node=None):
        """Helper function for export_texturing_property to export each texture slot."""
        texdesc.uv_set = uv_set
        texdesc.source = TextureCommon.export_source_texture(b_texture_node)

    @staticmethod
    def export_texture_filename(b_texture_node):
        """Returns image file name from b_texture_node.

        @param b_texture_node: The b_texture_node object in blender.
        @return: The file name of the image used in the b_texture_node.
        """

        if not (isinstance(b_texture_node, bpy.types.ShaderNodeTexImage) or
                isinstance(b_texture_node, bpy.types.ShaderNodeTexEnvironment)):
            raise io_scene_niftools.utils.logging.NifError(
                f"Expected a Shader node texture, got {type(b_texture_node)}")
        # get filename from image

        # TODO [b_texture_node] still needed? can b_texture_node.image be None in current blender?
        # check that image is loaded
        if b_texture_node.image is None:
            raise io_scene_niftools.utils.logging.NifError(
                f"Image type texture has no file loaded ('{b_texture_node.name}')")

        filename = b_texture_node.image.filepath

        # warn if packed flag is enabled
        if b_texture_node.image.packed_file:
            NifLog.warn(f"Packed image in texture '{b_texture_node.name}' ignored, exporting as '{filename}' instead.")

        # try and find a DDS alternative, force it if required
        ddsfilename = f"{(filename[:-4])}.dds"
        if os.path.exists(bpy.path.abspath(ddsfilename)) or NifOp.props.force_dds:
            filename = ddsfilename

        # sanitize file path
        nif_scene = bpy.context.scene.niftools_scene
        if not (nif_scene.is_bs() or nif_scene.game in ('MORROWIND',)):
            # strip b_texture_node file path
            filename = os.path.basename(filename)

        else:
            # strip the data files prefix from the b_texture_node's file name
            filename = filename.lower()
            idx = filename.find("textures")
            if idx >= 0:
                filename = filename[idx:]
            elif not os.path.exists(bpy.path.abspath(filename)):
                pass
            else:
                NifLog.warn(
                    f"{filename} does not reside in a 'Textures' folder; texture path will be stripped and textures may not display in-game")
                filename = os.path.basename(filename)
        # for linux export: fix path separators
        return filename.replace('/', '\\')
