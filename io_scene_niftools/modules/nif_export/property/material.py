"""Main module for exporting NIF material property blocks."""

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
from io_scene_niftools.modules.nif_export.animation.material import MaterialAnimation
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


EXPORT_OPTIMIZE_MATERIALS = True

class MaterialProperty:
    """
    Main interface class for exporting NIF material property blocks
    (i.e., NiMaterialProperty).
    """

    def __init__(self):
        self.material_anim = MaterialAnimation()

    def export_ni_material_property(self, b_mat, n_node):
        """Return existing material property with given settings, or create
        a new one if a material property with these settings is not found."""
        # don't export material properties for these games

        b_shader_node = b_mat.node_tree.nodes["Principled BSDF"]

        if bpy.context.scene.niftools_scene.is_skyrim():
            return

        name = block_store.get_full_name(b_mat)
        # create n_block
        n_ni_material_property = NifClasses.NiMaterialProperty(NifData.data)

        # list which determines whether the material name is relevant or not  only for particular names this holds,
        # such as EnvMap2 by default, the material name does not affect rendering
        specialnames = ("EnvMap2", "EnvMap", "skin", "Hair", "dynalpha", "HideSecret", "Lava")

        # hack to preserve EnvMap2, skinm, ... named blocks (even if they got renamed to EnvMap2.xxx or skin.xxx on import)
        if bpy.context.scene.niftools_scene.is_bs():
            for specialname in specialnames:
                if name.lower() == specialname.lower() or name.lower().startswith(specialname.lower() + "."):
                    if name != specialname:
                        NifLog.warn(f"Renaming material '{name}' to '{specialname}'")
                    name = specialname

        # Clear default material names
        if name.lower().startswith("noname") or name.lower().startswith("material"):
            NifLog.warn(f"Renaming material '{name}' to ''")
            name = ""

        n_ni_material_property.name = name

        n_ni_material_property.flags = b_mat.nif_material.material_flags

        if b_mat.use_nodes:
            (n_ni_material_property.ambient_color.r, n_ni_material_property.ambient_color.g,
             n_ni_material_property.ambient_color.b, _) = b_shader_node.inputs[26].default_value

            (n_ni_material_property.diffuse_color.r, n_ni_material_property.diffuse_color.g,
             n_ni_material_property.diffuse_color.b, _) = b_shader_node.inputs[22].default_value

            (n_ni_material_property.specular_color.r, n_ni_material_property.specular_color.g,
             n_ni_material_property.specular_color.b, _) = b_shader_node.inputs[14].default_value

            if b_shader_node.inputs[27].is_linked:
                b_color_node = b_shader_node.inputs[27].links[0].from_node
                if isinstance(b_color_node, bpy.types.ShaderNodeMix):
                    (n_ni_material_property.emissive_color.r, n_ni_material_property.emissive_color.g,
                     n_ni_material_property.emissive_color.b, _) = b_color_node.inputs[7].default_value
            else:
                (n_ni_material_property.emissive_color.r, n_ni_material_property.emissive_color.g,
                 n_ni_material_property.emissive_color.b, _) = b_shader_node.inputs[27].default_value

            # Map roughness [0,1] to glossiness (MW -> 0.0 - 128.0)
            if not b_shader_node.inputs[2].default_value == 0:
                n_ni_material_property.glossiness = min(1/b_shader_node.inputs[2].default_value - 1, 128)
            else:
                n_ni_material_property.glossiness = 128

            n_ni_material_property.alpha = b_shader_node.inputs[4].default_value

            n_ni_material_property.emissive_mult = b_shader_node.inputs[28].default_value

        # search for duplicate
        # (ignore the name string as sometimes import needs to create different materials even when NiMaterialProperty is the same)
        for n_block in block_store.block_to_obj:
            if not isinstance(n_block, NifClasses.NiMaterialProperty):
                continue

            # when optimization is enabled, ignore material name
            if EXPORT_OPTIMIZE_MATERIALS:
                ignore_strings = not (n_block.name in specialnames)
            else:
                ignore_strings = False

            # check hash
            first_index = 1 if ignore_strings else 0
            if n_block.get_hash()[first_index:] == n_ni_material_property.get_hash()[first_index:]:
                NifLog.warn(f"Merging materials '{n_ni_material_property.name}' and '{n_block.name}' (they are identical in nif)")
                n_ni_material_property = n_block
                break

        block_store.register_block(n_ni_material_property)
        # material animation
        self.material_anim.export_material_animations(b_mat, n_ni_material_property)
        # no material property with given settings found, so use and register the new one
        n_node.add_property(n_ni_material_property)
