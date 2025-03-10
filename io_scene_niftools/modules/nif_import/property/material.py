"""Classes for importing NIF property blocks into Blender materials."""

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

from functools import singledispatch

import bpy
from io_scene_niftools.modules.nif_import.property.node_wrapper import NodeWrapper
from io_scene_niftools.modules.nif_import.property.shader.bethesda import BSShaderProperty
from io_scene_niftools.utils.consts import TEX_SLOTS
from io_scene_niftools.utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


class MaterialProperty:
    """Main interface class for importing NIF property blocks into Blender materials."""

    def __init__(self):
        self.shader_property_helper = BSShaderProperty()
        self.node_wrapper = NodeWrapper.get()

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

        # Retrieve existing material with same name, or create a new one
        for n_ni_property in n_ni_property_list:
            if n_ni_property.name:
                mat_name = n_ni_property.name
                if mat_name in bpy.data.materials:
                    b_mat = bpy.data.materials[mat_name]
                    NifLog.debug(f"Retrieved already imported material {b_mat.name}.")
                else:
                    b_mat = bpy.data.materials.new(mat_name)
                    NifLog.debug(f"Created material {b_mat.name}.")
                break
        else:
            b_mat = bpy.data.materials.new("noname")
            NifLog.debug(f"Created material {b_mat.name}")

        b_obj.data.materials.append(b_mat)

        self.node_wrapper.b_mat = b_mat
        self.node_wrapper.clear_nodes()

        b_mat.use_backface_culling = True

        for n_ni_property in n_ni_property_list:
            self.import_material_property(n_ni_property, b_obj)

        self.node_wrapper.connect_to_output(b_obj.data.color_attributes)

    def __import_material_property(self, n_property_block, b_obj):
        """Base method for unsupported blocks."""

        NifLog.warn(f"Unknown property block found : {n_property_block.name:s}.")
        NifLog.warn(f"This type is not currently supported: {type(n_property_block)}.")

    def __import_ni_material_property(self, n_ni_material_property, b_obj):
        """Import a NiMaterialProperty block into a Blender material."""

        NifLog.debug("Importing NiMaterialProperty block.")

        b_mat = b_obj.active_material
        b_mat.nif_material.material_flags = n_ni_material_property.flags

        b_principled_bsdf = self.node_wrapper.b_principled_bsdf

        if not (bpy.context.scene.niftools_scene.is_skyrim or bpy.context.scene.niftools_scene.is_fo3):

            b_principled_bsdf.inputs[26].default_value = (n_ni_material_property.ambient_color.r, n_ni_material_property.ambient_color.g,
             n_ni_material_property.ambient_color.b, 1)

            b_principled_bsdf.inputs[22].default_value = (n_ni_material_property.diffuse_color.r, n_ni_material_property.diffuse_color.g,
             n_ni_material_property.diffuse_color.b, 1)

            b_principled_bsdf.inputs[14].default_value = (n_ni_material_property.specular_color.r, n_ni_material_property.specular_color.g,
             n_ni_material_property.specular_color.b, 1)

        b_principled_bsdf.inputs[27].default_value = (n_ni_material_property.emissive_color.r,
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

        b_mat.nif_material.use_alpha = True
        b_mat.nif_alpha.enable_blending = n_ni_alpha_property.flags.alpha_blend
        b_mat.nif_alpha.source_blend_mode = n_ni_alpha_property.flags.source_blend_mode.name
        b_mat.nif_alpha.destination_blend_mode = n_ni_alpha_property.flags.destination_blend_mode.name
        b_mat.nif_alpha.enable_testing = n_ni_alpha_property.flags.alpha_test
        b_mat.nif_alpha.alpha_test_function = n_ni_alpha_property.flags.test_func.name
        b_mat.nif_alpha.no_sorter = n_ni_alpha_property.flags.no_sorter
        b_mat.nif_alpha.alpha_test_threshold = n_ni_alpha_property.threshold

    def __import_ni_specular_property(self, n_ni_specular_property, b_obj):
        """Import a NiSpecularProperty block into a Blender material."""

        NifLog.debug("Importing NiSpecularProperty block.")

        b_mat = b_obj.active_material

        b_mat.nif_material.use_specular = n_ni_specular_property.flags.value

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
