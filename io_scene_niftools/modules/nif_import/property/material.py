"""Classes for importing NIF property blocks into Blender materials."""

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

import os.path
from functools import singledispatch

import bpy
from ....modules.nif_import.property.node_wrapper import NodeWrapper
from ....modules.nif_import.property.shader.bethesda import BSShaderProperty
from ....utils.consts import TEX_SLOTS, BS_TEX_SLOTS
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


# Blender materials created during this import, keyed by the set of NIF property blocks
# they were built from. Two meshes share a material only when they share those blocks.
DICT_MATERIALS = {}

# Materials by the name of the geometry they were imported for, so that the controller
# sequences, which refer to their targets by name, can find what to animate.
DICT_MATERIALS_BY_NODE = {}

# Materials by the NIF controller blocks referenced by their properties. A controller
# block may be shared by several distinct properties even when a controller sequence
# names only one geometry target. The game drives every owner of that shared block.
DICT_MATERIALS_BY_CONTROLLER = {}


def clear():
    """Forget the materials imported by the previous run."""
    DICT_MATERIALS.clear()
    DICT_MATERIALS_BY_NODE.clear()
    DICT_MATERIALS_BY_CONTROLLER.clear()


class MaterialProperty:
    """Main interface class for importing NIF property blocks into Blender materials."""

    def __init__(self):
        self.shader_property_helper = BSShaderProperty()
        self.node_wrapper = NodeWrapper.get()
        # imported here to avoid a circular import, as the animation module needs the shader tree
        from ....modules.nif_import.animation.material import MaterialAnimation
        self.material_animation_helper = MaterialAnimation()

        self.import_material_property = singledispatch(self.__import_material_property)
        self.import_material_property.register(NifClasses.NiMaterialProperty, self.__import_ni_material_property)
        self.import_material_property.register(NifClasses.NiAlphaProperty, self.__import_ni_alpha_property)
        self.import_material_property.register(NifClasses.NiSpecularProperty, self.__import_ni_specular_property)
        self.import_material_property.register(NifClasses.NiStencilProperty, self.__import_ni_stencil_property)
        self.import_material_property.register(NifClasses.NiVertexColorProperty, self.__import_ni_vertex_color_property)
        self.import_material_property.register(NifClasses.NiWireframeProperty, self.__import_ni_wireframe_property)
        self.import_material_property.register(NifClasses.NiTexturingProperty, self.__import_ni_texturing_property)
        self.import_material_property.register(NifClasses.BSShaderPPLightingProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.BSShaderNoLightingProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.BSLightingShaderProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.BSEffectShaderProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.SkyShaderProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.TallGrassShaderProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.TileShaderProperty, self.__import_bs_shader_property)
        self.import_material_property.register(NifClasses.WaterShaderProperty, self.__import_bs_shader_property)

    def import_material_properties(self, n_ni_geometry, b_obj):
        """Main function for handling material import."""

        n_ni_property_list = []

        if bpy.context.scene.niftools_scene.is_skyrim():
            # Skyrim's material properties are stored in the shader property
            # And there is a dedicated attribute for the linked alpha property
            if n_ni_geometry.shader_property:
                n_ni_property_list.append(n_ni_geometry.shader_property)
            if n_ni_geometry.alpha_property:
              n_ni_property_list.append(n_ni_geometry.alpha_property)

        else:
            n_ni_property_list = n_ni_geometry.properties

        if not n_ni_property_list:
            return

        # Two meshes share a material only when they reference the same property blocks.
        # Matching names mean nothing: a nif may hold several materials that share a name
        # (or have none at all) while differing in their properties, and merging those
        # would give every one of them the settings of whichever was imported last.
        material_key = tuple(n_ni_property_list)
        b_mat = DICT_MATERIALS.get(material_key)
        if b_mat is not None:
            NifLog.debug(f"Reusing material {b_mat.name}, which has the same property blocks.")
            b_obj.data.materials.append(b_mat)
            DICT_MATERIALS_BY_NODE.setdefault(str(n_ni_geometry.name), b_mat)
            return

        for n_ni_property in n_ni_property_list:
            if n_ni_property.name:
                # blender makes the name unique if another material already has it
                b_mat = bpy.data.materials.new(n_ni_property.name)
                NifLog.debug(f"Created material {b_mat.name}.")
                break
        else:
            # the nif has no material name. A name is derived from the texture further below
            b_mat = bpy.data.materials.new("noname")
            b_mat.nif_material.auto_named = True
            NifLog.debug(f"Created material {b_mat.name}")

        DICT_MATERIALS[material_key] = b_mat
        DICT_MATERIALS_BY_NODE.setdefault(str(n_ni_geometry.name), b_mat)
        for n_ni_property in n_ni_property_list:
            for n_controller in n_ni_property.get_controllers():
                b_materials = DICT_MATERIALS_BY_CONTROLLER.setdefault(n_controller, [])
                if b_mat not in b_materials:
                    b_materials.append(b_mat)
        b_obj.data.materials.append(b_mat)

        self.node_wrapper.b_mat = b_mat
        self.node_wrapper.clear_nodes()

        b_mat.use_backface_culling = True

        for n_ni_property in n_ni_property_list:
            self.import_material_property(n_ni_property, b_obj)

        self.node_wrapper.connect_to_output(b_obj.data.color_attributes)

        if b_mat.nif_material.auto_named:
            self.name_material_after_texture(b_mat)

        # the shader tree is complete, so the controllers have something to animate
        self.material_animation_helper.import_material_controllers(n_ni_geometry, b_mat)

    @staticmethod
    def name_material_after_texture(b_mat):
        """Name a material that the NIF left unnamed after its first texture, which is
        far more useful than 'noname' when working with several materials."""

        b_texture_nodes = [node for node in b_mat.node_tree.nodes
                           if isinstance(node, bpy.types.ShaderNodeTexImage) and node.image]
        if not b_texture_nodes:
            return

        # prefer the diffuse map, otherwise just take the first texture
        b_diffuse_nodes = [node for node in b_texture_nodes
                           if node.label in (BS_TEX_SLOTS.DIFFUSE_MAP, TEX_SLOTS.BASE)]
        b_texture_node = (b_diffuse_nodes or b_texture_nodes)[0]

        name = os.path.splitext(bpy.path.basename(b_texture_node.image.name))[0]
        if name:
            b_mat.name = name
            NifLog.debug(f"Named material after its texture: {b_mat.name}")

    def __import_material_property(self, n_property_block, b_obj):
        """Base method for unsupported blocks."""

        NifLog.warn(f"Unknown property block found : {n_property_block.name:s}.")
        NifLog.warn(f"This type is not currently supported: {type(n_property_block)}.")

    def __import_ni_material_property(self, n_ni_material_property, b_obj):
        """Import a NiMaterialProperty block into a Blender material."""

        NifLog.debug("Importing NiMaterialProperty block.")

        b_mat = b_obj.active_material
        b_mat.nif_material.material_flags = n_ni_material_property.flags

        # values the shading uses live on the shader node group, so what is seen matches the nif
        shader_values = self.node_wrapper.shader_values
        n_emissive = n_ni_material_property.emissive_color
        shader_values["Emissive Color"] = (n_emissive.r, n_emissive.g, n_emissive.b, 1)
        shader_values["Glossiness"] = n_ni_material_property.glossiness
        shader_values["Alpha"] = n_ni_material_property.alpha
        shader_values["Emissive Mult"] = getattr(n_ni_material_property, "emissive_mult", 1.0)

        # the colours only shade anything before Fallout 3, where the Gamebryo group holds
        # them. From Fallout 3 on a shader property takes over and they mean nothing, so
        # they are not read at all
        b_scene = bpy.context.scene.niftools_scene
        if not (b_scene.is_fo3() or b_scene.is_skyrim()):
            for socket_name, n_color in (("Ambient Color", n_ni_material_property.ambient_color),
                                         ("Diffuse Color", n_ni_material_property.diffuse_color),
                                         ("Specular Color", n_ni_material_property.specular_color)):
                shader_values[socket_name] = (n_color.r, n_color.g, n_color.b, 1)

        b_principled_bsdf = self.node_wrapper.b_principled_bsdf
        if b_principled_bsdf is not None:
            b_principled_bsdf.inputs['Emission Color'].default_value = (
                n_ni_material_property.emissive_color.r,
                n_ni_material_property.emissive_color.g,
                n_ni_material_property.emissive_color.b, 1)

        self.node_wrapper.emissive_color = (n_ni_material_property.emissive_color.r,
                                            n_ni_material_property.emissive_color.g,
                                            n_ni_material_property.emissive_color.b, 1)

        # Map glossiness (0.0 - 128.0) to specular IOR level (0.0 - 1.0)
        b_principled_bsdf.inputs['Specular IOR Level'].default_value = 1 - (n_ni_material_property.glossiness / 128)

        b_principled_bsdf.inputs['Alpha'].default_value = n_ni_material_property.alpha

        b_principled_bsdf.inputs['Emission Strength'].default_value = n_ni_material_property.emissive_mult



    def __import_ni_alpha_property(self, n_ni_alpha_property, b_obj):
        """Import a NiAlphaProperty block into a Blender material."""

        NifLog.debug("Importing NiAlphaProperty block.")

        b_mat = b_obj.active_material

        b_mat.nif_alpha.use_alpha = True
        b_mat.nif_alpha.enable_blending = n_ni_alpha_property.flags.alpha_blend
        b_mat.nif_alpha.source_blend_mode = n_ni_alpha_property.flags.source_blend_mode.name
        b_mat.nif_alpha.destination_blend_mode = n_ni_alpha_property.flags.destination_blend_mode.name
        b_mat.nif_alpha.enable_testing = n_ni_alpha_property.flags.alpha_test
        b_mat.nif_alpha.alpha_test_function = n_ni_alpha_property.flags.test_func.name
        b_mat.nif_alpha.alpha_test_threshold = n_ni_alpha_property.threshold
        b_mat.nif_alpha.no_sorter = n_ni_alpha_property.flags.no_sorter

        # the alpha test is shown in the shader tree, so it lives on the node group
        self.node_wrapper.shader_values["Alpha Test"] = 1.0 if n_ni_alpha_property.flags.alpha_test else 0.0
        self.node_wrapper.shader_values["Alpha Test Threshold"] = n_ni_alpha_property.threshold / 255.0

    def __import_ni_specular_property(self, n_ni_specular_property, b_obj):
        """Import a NiSpecularProperty block into a Blender material."""

        NifLog.debug("Importing NiSpecularProperty block.")

        b_mat = b_obj.active_material

        # specularity is driven by the normal map alpha channel, so there is nothing to store

    def __import_ni_stencil_property(self, n_ni_stencil_property, b_obj):
        """Import a NiStencilProperty block into a Blender material."""

        NifLog.debug("Importing NiStencilProperty block.")

        b_mat = b_obj.active_material

        b_mat.use_backface_culling = False

    def __import_ni_vertex_color_property(self, n_ni_vertex_color_property, b_obj):
        """Import a NiVertexColorProperty block into a Blender material."""

        # TODO: Implement with shader nodes
        NifLog.debug("Importing NiVertexColorProperty block.")

    def __import_ni_wireframe_property(self, n_ni_wireframe_property, b_obj):
        """Import a NiWireframeProperty block as a Blender modifier."""

        NifLog.debug("Importing NiWireframeProperty block.")

        b_mod = b_obj.modifiers.new("WIREFRAME", 'WIREFRAME')
        b_mod.use_relative_offset = True

    def __import_ni_texturing_property(self, n_ni_texturing_property, b_obj):
        """Import a NiTexturingProperty block into a Blender material."""

        NifLog.debug("Importing NiTexturingProperty block.")

        # only Oblivion and earlier read these, but carrying them through costs nothing
        b_obj.active_material.nif_material.texture_flags = int(n_ni_texturing_property.flags)

        for slot_name in vars(TEX_SLOTS).values():
            slot_lower = slot_name.lower().replace(' ', '_')
            field_name = f"{slot_lower}_texture"
            has_tex = getattr(n_ni_texturing_property, "has_" + field_name, None)
            if has_tex:
                NifLog.debug(f"Texdesc has active {slot_name}")
                n_tex = getattr(n_ni_texturing_property, field_name)
                self.node_wrapper.create_and_link(slot_name, n_tex)

    def __import_bs_shader_property(self, n_bs_shader_property, b_obj):
        """Import a BSShaderProperty block into a Blender material."""

        NifLog.debug("Importing BSShaderProperty block.")

        self.shader_property_helper.import_bs_shader_property(n_bs_shader_property, b_obj.active_material)
