"""This script contains helper methods to managing importing texture into specific slots."""

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


import bpy
from io_scene_niftools.modules.nif_import.property.texture.loader import TextureLoader
from io_scene_niftools.utils.consts import TEX_SLOTS, BS_TEX_SLOTS
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.nodes import nodes_iterate
from nifgen.formats.nif import classes as NifClasses

"""Names (ordered by default index) of shader texture slots for Sid Meier's Railroads and similar games."""
EXTRA_SHADER_TEXTURES = [
    "EnvironmentMapIndex",
    "NormalMapIndex",
    "SpecularIntensityIndex",
    "EnvironmentIntensityIndex",
    "LightCubeMapIndex",
    "ShadowTextureIndex"]


class NodeWrapper:
    __instance = None

    @staticmethod
    def get():
        """Static access method."""
        if NodeWrapper.__instance is None:
            NodeWrapper()
        return NodeWrapper.__instance

    def __init__(self):
        """Virtually private constructor."""

        if NodeWrapper.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            NodeWrapper.__instance = self

            self.texture_loader = TextureLoader()
            self.b_mat = None
            self.b_shader_tree = None

            # Shader Nodes
            self.b_mat_output = None # Material Output
            self.b_principled_bsdf = None # Principled BSDF
            self.b_glossy_bsdf = None # Glossy BSDF
            self.b_add_shader = None # Add Shader
            self.b_normal = None # Normal Map
            self.b_color_attribute = None # Color Attribute
            self.b_emissive_pass = None # Mix Color (for material emissive color)
            self.b_diffuse_pass = None # Mix Color (for color attribute)
            self.b_texture_coordinate = None # Texture Coordinate (for environment map)

            # Texture Nodes
            self.b_textures = [None] * 8

    @staticmethod
    def uv_node_name(uv_index):
        return f"TexCoordIndex_{uv_index}"

    def set_uv_map(self, b_texture_node, uv_index=0, reflective=False):
        """Attaches a vector node describing the desired coordinate transforms to the texture node's UV input."""
        if reflective:
            uv = self.b_shader_tree.nodes.new('ShaderNodeTexCoord')
            self.b_shader_tree.links.new(uv.outputs[6], b_texture_node.inputs[0])
        # use supplied UV maps for everything else, if present
        else:
            uv_name = self.uv_node_name(uv_index)
            existing_node = self.b_shader_tree.nodes.get(uv_name)
            if not existing_node:
                uv = self.b_shader_tree.nodes.new('ShaderNodeUVMap')
                uv.name = uv_name
                uv.uv_map = f"UV{uv_index}"
            else:
                uv = existing_node
            self.b_shader_tree.links.new(uv.outputs[0], b_texture_node.inputs[0])

    def global_uv_offset_scale(self, x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y):
        # get all uv nodes (by name, since we are importing they have the predefined name
        # and then we don't have to loop through every node
        uv_nodes = {}
        uv_index = 0
        while True:
            uv_name = self.uv_node_name(uv_index)
            uv_node = self.b_shader_tree.nodes.get(uv_name)
            if uv_node and isinstance(uv_node, bpy.types.ShaderNodeUVMap):
                uv_nodes[uv_index] = uv_node
                uv_index += 1
            else:
                break

        clip_texture = clamp_x and clamp_y

        for uv_index, uv_node in uv_nodes.items():
            # for each of those, create a new uv output node and relink
            split_node = self.b_shader_tree.nodes.new("ShaderNodeSeparateXYZ")
            split_node.name = f"Separate UV{uv_index}"
            split_node.label = split_node.name
            combine_node = self.b_shader_tree.nodes.new("ShaderNodeCombineXYZ")
            combine_node.name = f"Combine UV{uv_index}"
            combine_node.label = combine_node.name

            x_node = self.b_shader_tree.nodes.new("ShaderNodeMath")
            x_node.name = f"X offset and scale UV{uv_index}"
            x_node.label = x_node.name
            x_node.operation = 'MULTIPLY_ADD'
            # only clamp on the math node when we're not clamping on both directions
            # otherwise, the clip on the image texture node will take care of it
            x_node.use_clamp = clamp_x and not clip_texture
            x_node.inputs[1].default_value = x_scale
            x_node.inputs[2].default_value = x_offset
            self.b_shader_tree.links.new(split_node.outputs[0], x_node.inputs[0])
            self.b_shader_tree.links.new(x_node.outputs[0], combine_node.inputs[0])

            y_node = self.b_shader_tree.nodes.new("ShaderNodeMath")
            y_node.name = f"Y offset and scale UV{uv_index}"
            y_node.label = y_node.name
            y_node.operation = 'MULTIPLY_ADD'
            y_node.use_clamp = clamp_y and not clip_texture
            y_node.inputs[1].default_value = y_scale
            y_node.inputs[2].default_value = y_offset
            self.b_shader_tree.links.new(split_node.outputs[1], y_node.inputs[0])
            self.b_shader_tree.links.new(y_node.outputs[0], combine_node.inputs[1])

            # get all the texture nodes to which it is linked, and re-link them to the uv output node
            for link in uv_node.outputs[0].links:
                # get the target link/socket
                target_node = link.to_node
                if isinstance(link.to_node, bpy.types.ShaderNodeTexImage):
                    target_socket = link.to_socket
                    # delete the existing link
                    self.b_shader_tree.links.remove(link)
                    # make new ones
                    self.b_shader_tree.links.new(combine_node.outputs[0], target_socket)
                    # if we clamp in both directions, clip the images:
                    if clip_texture:
                        target_node.extension = 'CLIP'
            self.b_shader_tree.links.new(uv_node.outputs[0], split_node.inputs[0])
        pass

    def clear_nodes(self):
        """Clear existing shader nodes from the node tree and restart with minimal setup."""

        self.b_mat.use_nodes = True
        self.b_shader_tree = self.b_mat.node_tree

        # Remove existing shader nodes
        for node in self.b_shader_tree.nodes:
            self.b_shader_tree.nodes.remove(node)

        self.b_glossy_bsdf = None
        self.b_add_shader = None
        self.b_normal = None
        self.b_color_attribute = None
        self.b_emissive_pass = None
        self.b_diffuse_pass = None
        self.b_texture_coordinate = None

        self.b_textures = [None] * 8

        # Add basic shader nodes
        self.b_principled_bsdf = self.b_shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
        self.b_mat_output = self.b_shader_tree.nodes.new('ShaderNodeOutputMaterial')
        self.b_shader_tree.links.new(self.b_principled_bsdf.outputs[0], self.b_mat_output.inputs[0])

    def connect_to_pass(self, b_node_pass, b_texture_node, texture_type="Detail"):
        """Connect to an image premixing pass"""
        # connect if the pass has been established, ie. the base texture already exists
        if b_node_pass:
            rgb_mixer = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
            # these textures are overlaid onto the base
            if texture_type in ("Detail", "Reflect"):
                rgb_mixer.inputs[0].default_value = 1
                rgb_mixer.blend_type = "OVERLAY"
            # these textures are multiplied with the base texture (currently only vertex color)
            elif texture_type == "Vertex_Color":
                rgb_mixer.inputs[0].default_value = 1
                rgb_mixer.blend_type = "MULTIPLY"
            # these textures use their alpha channel as a mask over the input pass
            elif texture_type == "Decal":
                self.b_shader_tree.links.new(b_texture_node.outputs[1], rgb_mixer.inputs[0])
            self.b_shader_tree.links.new(b_node_pass.outputs[0], rgb_mixer.inputs[1])
            self.b_shader_tree.links.new(b_texture_node.outputs[0], rgb_mixer.inputs[2])
            return rgb_mixer
        return b_texture_node

    def connect_vertex_colors_to_pass(self, ):
        # if ob.data.vertex_colors:
        self.b_color_attribute = self.b_shader_tree.nodes.new('ShaderNodeVertexColor')
        self.b_color_attribute.layer_name = "RGBA"
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, self.b_color_attribute, texture_type="Vertex_Color")

    def connect_to_output(self, has_vcol=False):
        if has_vcol:
            self.connect_vertex_colors_to_pass()

        if self.b_diffuse_pass:
            self.b_shader_tree.links.new(self.b_diffuse_pass.outputs[0], self.b_principled_bsdf.inputs[0])

            if self.b_textures[0] and self.b_mat.nif_material.use_alpha and has_vcol and self.b_mat.nif_shader.vertex_alpha:
                mixAAA = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
                mixAAA.inputs[0].default_value = 1
                mixAAA.blend_type = "MULTIPLY"
                self.b_shader_tree.links.new(self.b_textures[0].outputs[1], mixAAA.inputs[1])
                self.b_shader_tree.links.new(self.b_color_attribute.outputs[1], mixAAA.inputs[2])
                self.b_shader_tree.links.new(mixAAA.outputs[0], self.b_principled_bsdf.inputs[4])
            elif self.b_textures[0] and self.b_mat.nif_material.use_alpha:
                self.b_shader_tree.links.new(self.b_textures[0].outputs[1], self.b_principled_bsdf.inputs[4])
            elif has_vcol and self.b_mat.nif_shader.vertex_alpha:
                self.b_shader_tree.links.new(self.b_color_attribute.outputs[1], self.b_principled_bsdf.inputs[4])

        nodes_iterate(self.b_shader_tree, self.b_mat_output)

    def create_and_link(self, slot_name, n_tex_info):

        slot_name_lower = slot_name.lower().replace(' ', '_')

        import_func_name = f"link_{slot_name_lower}_node"
        import_func = getattr(self, import_func_name, None)
        if not import_func:
            NifLog.debug(f"Could not find texture linking function {import_func_name}")
            return
        b_texture = self.create_texture_slot(n_tex_info)
        import_func(b_texture)

    def create_texture_slot(self, n_tex_desc):
        # todo [texture] refactor this to separate code paths?
        # when processing a NiTextureProperty
        if isinstance(n_tex_desc, NifClasses.TexDesc):
            b_image = self.texture_loader.import_texture_source(n_tex_desc.source)
            uv_layer_index = n_tex_desc.uv_set
        # when processing a BS shader property - n_tex_desc is a bare string
        else:
            b_image = self.texture_loader.import_texture_source(n_tex_desc)
            uv_layer_index = 0

        # create a texture node
        b_texture_node = self.b_mat.node_tree.nodes.new('ShaderNodeTexImage')
        b_texture_node.image = b_image
        b_texture_node.interpolation = "Smart"
        # todo [texture] pass info about reflective coordinates
        # UV mapping
        self.set_uv_map(b_texture_node, uv_index=uv_layer_index, reflective=False)

        # todo [texture] support clamping and interpolation settings
        return b_texture_node

    def link_base_node(self, b_texture_node):
        self.b_textures[0] = b_texture_node
        b_texture_node.label = TEX_SLOTS.BASE
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node)

        if bpy.context.scene.niftools_scene.game == 'OBLIVION':
            base_name, extension = b_texture_node.image.name.rsplit(".", 1)
            self.create_and_link("normal", f"{base_name}_n.{extension}")

    def link_bump_map_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.BUMP_MAP
        # # Influence mapping
        # b_texture_node.texture.use_normal_map = False  # causes artifacts otherwise.
        #
        # # Influence
        # # TODO [property][texture][flag][alpha] Figure out if this texture has alpha
        # # if self.nif_import.ni_alpha_prop:
        # #     b_texture_node.use_map_alpha = True
        #
        # b_texture_node.use_map_color_diffuse = False
        # b_texture_node.use_map_normal = True
        # b_texture_node.use_map_alpha = False

    def link_normal_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.NORMAL
        # Set to non-color data
        b_texture_node.image.colorspace_settings.name = 'Non-Color'

        # Create Y-invert node (because NIF normal maps are +X -Y +Z)
        nodes = self.b_shader_tree.nodes
        links = self.b_shader_tree.links
        group_name = "InvertY"

        if group_name in bpy.data.node_groups:
            node_group = bpy.data.node_groups[group_name]
        else:
            # The InvertY node group does not yet exist, create it
            node_group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")
            group_nodes = node_group.nodes

            # Add the input and output nodes
            input_node = group_nodes.new('NodeGroupInput')
            input_node.location = (-300, 0)
            group_output = group_nodes.new('NodeGroupOutput')
            group_output.location = (300, 0)

            # Define the inputs and outputs for the node group using the new API
            interface = node_group.interface
            input_socket = interface.new_socket(
                name="Input",
                socket_type='NodeSocketColor',
                in_out='INPUT',
                description="Input color for the group"
            )
            output_socket = interface.new_socket(
                name="Output",
                socket_type='NodeSocketColor',
                in_out='OUTPUT',
                description="Output color from the group"
            )

            # Set up the node group internals
            separate_node = group_nodes.new("ShaderNodeSeparateRGB")
            separate_node.location = (-150, 100)

            invert_node = group_nodes.new("ShaderNodeInvert")
            invert_node.location = (0, 100)

            combine_node = group_nodes.new("ShaderNodeCombineRGB")
            combine_node.location = (150, 100)

            # Link the nodes within the group
            group_links = node_group.links
            group_links.new(separate_node.outputs['R'], combine_node.inputs['R'])  # Red
            group_links.new(separate_node.outputs['G'], invert_node.inputs['Color'])  # Green (invert)
            group_links.new(invert_node.outputs['Color'], combine_node.inputs['G'])  # Green (inverted)
            group_links.new(separate_node.outputs['B'], combine_node.inputs['B'])  # Blue

            # Link the input and output nodes to the group sockets
            group_links.new(input_node.outputs[input_socket.name], separate_node.inputs['Image'])
            group_links.new(combine_node.outputs['Image'], group_output.inputs[output_socket.name])

        # Add the group node to the main node tree and link it
        group_node = nodes.new('ShaderNodeGroup')
        group_node.node_tree = node_group
        group_node.location = (-300, 300)

        links.new(group_node.inputs['Input'], b_texture_node.outputs['Color'])

        if self.b_mat.nif_shader.model_space_normals:
            links.new(self.b_principled_bsdf.inputs[5], group_node.outputs['Output'])
        else:
            # Create tangent normal map converter and link to it
            tangent_converter = nodes.new("ShaderNodeNormalMap")
            tangent_converter.location = (0, 300)
            links.new(tangent_converter.inputs['Color'], group_node.outputs['Output'])
            links.new(self.b_principled_bsdf.inputs[5], tangent_converter.outputs['Normal'])

    def link_glow_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.GLOW
        # # Influence mapping
        # b_texture_node.texture.use_alpha = False
        #
        # # Influence
        # # TODO [property][texture][flag][alpha] Figure out if this texture has alpha
        # # if self.nif_import.ni_alpha_prop:
        # #     b_texture_node.use_map_alpha = True
        #
        # b_texture_node.use_map_color_diffuse = False
        # b_texture_node.use_map_emit = True

    def link_gloss_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.GLOSS
        # # Influence mapping
        # b_texture_node.texture.use_alpha = False
        #
        # # Influence
        # # TODO [property][texture][flag][alpha] Figure out if this texture has alpha
        # # if self.nif_import.ni_alpha_prop:
        # #     b_texture_node.use_map_alpha = True
        #
        # b_texture_node.use_map_color_diffuse = False
        # b_texture_node.use_map_specular = True
        # b_texture_node.use_map_color_spec = True

    def link_decal_0_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.DECAL_0
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_decal_1_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.DECAL_1
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_decal_2_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.DECAL_2
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_detail_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.DETAIL
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Detail")

    def link_dark_node(self, b_texture_node):
        b_texture_node.label = TEX_SLOTS.DARK

    def link_reflection_node(self, b_texture_node):
        # Influence mapping

        # Influence
        # TODO [property][texture][flag][alpha] Figure out if this texture has alpha
        # if self.nif_import.ni_alpha_prop:
        #     b_texture_node.use_map_alpha = True

        # b_texture_node.use_map_color_diffuse = True
        # b_texture_node.use_map_emit = True
        # b_texture_node.use_map_mirror = True
        return

    def link_environment_node(self, b_texture_node):
        # Influence mapping

        # Influence
        # TODO [property][texture][flag][alpha] Figure out if this texture has alpha
        # if self.nif_import.ni_alpha_prop:
        #     b_texture_node.use_map_alpha = True

        # b_texture_node.use_map_color_diffuse = True
        # b_texture_node.blend_type = 'ADD'
        return

    def link_diffuse_map_node(self, b_texture_node):
        self.b_textures[0] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.DIFFUSE_MAP
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node)

    def link_normal_map_node(self, b_texture_node):
        self.b_textures[1] = b_texture_node
        self.link_normal_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.NORMAL_MAP

    def link_glow_map_node(self, b_texture_node):
        self.b_textures[2] = b_texture_node
        self.link_glow_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.GLOW_MAP

    def link_parallax_map_node(self, b_texture_node):
        self.b_textures[3] = b_texture_node
        self.link_detail_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.PARALLAX_MAP

    def link_environment_map_node(self, b_texture_node):
        self.b_textures[4] = b_texture_node
        self.link_reflection_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.ENVIRONMENT_MAP

    def link_environment_mask_node(self, b_texture_node):
        self.b_textures[5] = b_texture_node
        self.link_environment_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.ENVIRONMENT_MASK

    def link_subsurface_tint_map_node(self, b_texture_node):
        self.b_textures[6] = b_texture_node
        self.link_environment_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.SUBSURFACE_TINT_MAP

    def link_backlight_map_node(self, b_texture_node):
        self.b_textures[7] = b_texture_node
        self.link_environment_node(b_texture_node)
        b_texture_node.label = BS_TEX_SLOTS.BACKLIGHT_MAP

    @staticmethod
    def get_b_blend_type_from_n_apply_mode(n_apply_mode):
        # TODO [material] Check out n_apply_modes
        if n_apply_mode == NifClasses.ApplyMode.APPLY_MODULATE:
            return "MIX"
        elif n_apply_mode == NifClasses.ApplyMode.APPLY_REPLACE:
            return "COLOR"
        elif n_apply_mode == NifClasses.ApplyMode.APPLY_DECAL:
            return "OVERLAY"
        elif n_apply_mode == NifClasses.ApplyMode.APPLY_HILIGHT:
            return "LIGHTEN"
        elif n_apply_mode == NifClasses.ApplyMode.APPLY_HILIGHT2:  # used by Oblivion for parallax
            return "MULTIPLY"
        else:
            NifLog.warn(f"Unknown apply mode ({n_apply_mode}) in material, using blend type 'MIX'")
            return "MIX"
