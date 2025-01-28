"""Main module for exporting NIF object property blocks."""

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


from math import pi

import bpy

from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.property.material import MaterialProperty
from io_scene_niftools.modules.nif_export.property.texture import TextureProperty
from io_scene_niftools.utils.consts import USED_EXTRA_SHADER_TEXTURES
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses


class ObjectProperty:
    """
    Main interface class for exporting NIF object property blocks
    (i.e., NiMaterialProperty, NiAlphaProperty, BSLightingShaderProperty).
    """

    def __init__(self):
        self.material_property_helper = MaterialProperty()
        self.texture_property_helper = TextureProperty()

    def export_object_properties(self, b_obj, n_node):
        """
        This is the main property processor that attaches
        all suitable properties gauged from b_obj and b_mat to n_block.
        """

        b_mat = b_obj.active_material

        if b_obj and b_mat:
            # export and add properties to n_block
            self.export_alpha_property(b_mat, n_node),
            self.export_wireframe_property(b_obj, n_node),
            self.export_stencil_property(b_mat, n_node),
            self.export_specular_property(b_mat, n_node),
            self.material_property_helper.export_ni_material_property(b_mat, n_node)
            self.texture_property_helper.export_texture_properties(b_mat, n_node)

    def export_root_node_properties(self, n_root_node, b_root_obj):
        """Wrapper for exporting properties that are commonly attached to the nif root"""

        NifLog.info(f"Exporting root node properties...")

        # Add vertex color and zbuffer properties for civ4 and railroads
        if bpy.context.scene.niftools_scene.game in (
                'CIVILIZATION_IV', 'SID_MEIER_S_RAILROADS', 'EMPIRE_EARTH_II', 'ZOO_TYCOON_2'):
            self.export_vertex_color_property(n_root_node)
            self.export_z_buffer_property(n_root_node)

        self.export_ni_string_extra_data_upb(n_root_node, b_root_obj)
        self.export_ni_string_extra_data_prn(n_root_node, b_root_obj)
        self.export_bs_inv_marker(n_root_node, b_root_obj)
        self.export_bs_x_flags(n_root_node, b_root_obj)

    def get_matching_block(self, block_type, **kwargs):
        """Try to find a block matching block_type. Keyword arguments are a dict of parameters and required attributes of the block"""
        # go over all blocks of block_type

        NifLog.debug(f"Looking for {block_type} block. Kwargs: {kwargs}")
        for block in block_store.block_to_obj:
            # if isinstance(block, block_type):
            if block_type in str(type(block)):
                # skip blocks that don't match additional conditions
                for param, attribute in kwargs.items():
                    # now skip this block if any of the conditions does not match
                    if attribute is not None:
                        ret_attr = getattr(block, param, None)
                        if ret_attr != attribute:
                            NifLog.debug(f"break, {param} != {attribute}, returns {ret_attr}")
                            break
                else:
                    # we did not break out of the loop, so all checks went through, so we can use this block
                    NifLog.debug(f"Found existing {block_type} block matching all criteria!")
                    return block
        # we are still here, so we must create a block of this type and set all attributes accordingly
        NifLog.debug(f"Created new {block_type} block because none matched the required criteria!")
        block = block_store.create_block(block_type)
        for param, attribute in kwargs.items():
            if attribute is not None:
                setattr(block, param, attribute)
        return block

    def export_vertex_color_property(self, n_node, flags=1, vertex_mode=0, lighting_mode=1):
        """Return existing vertex color property with given flags, or create new one
        if an alpha property with required flags is not found."""
        n_node.add_property(self.get_matching_block("NiVertexColorProperty", flags=flags, vertex_mode=vertex_mode,
                                       lighting_mode=lighting_mode))

    def export_z_buffer_property(self, n_node, flags=15, function=3):
        """Return existing z-buffer property with given flags, or create new one
        if an alpha property with required flags is not found."""
        if bpy.context.scene.niftools_scene.game in ('EMPIRE_EARTH_II',):
            function = 1
        n_node.add_property(self.get_matching_block("NiZBufferProperty", flags=flags, function=function))

    def export_alpha_property(self, b_mat, n_node):
        """Return existing alpha property with given flags, or create new one
        if an alpha property with required flags is not found."""
        # don't export an alpha property if mat is opaque in blender
        if b_mat.nif_material.use_alpha:
            n_ni_alpha_property = block_store.create_block("NiAlphaProperty")
            n_node.add_property(n_ni_alpha_property)

            n_ni_alpha_property.flags.alpha_blend = b_mat.nif_alpha.enable_blending
            n_ni_alpha_property.flags.source_blend_mode = NifClasses.AlphaFunction[b_mat.nif_alpha.source_blend_mode]
            n_ni_alpha_property.flags.destination_blend_mode = NifClasses.AlphaFunction[b_mat.nif_alpha.destination_blend_mode]
            n_ni_alpha_property.flags.alpha_test = b_mat.nif_alpha.enable_testing
            n_ni_alpha_property.flags.test_func = NifClasses.TestFunction[b_mat.nif_alpha.alpha_test_function]
            n_ni_alpha_property.flags.no_sorter = b_mat.nif_alpha.no_sorter
            n_ni_alpha_property.threshold = b_mat.nif_alpha.alpha_test_threshold

    def export_specular_property(self, b_mat, n_node, flags=0x0001):
        """Return existing specular property with given flags, or create new one
        if a specular property with required flags is not found."""
        # search for duplicate
        if b_mat and not (
                bpy.context.scene.niftools_scene.is_skyrim()) and "FALLOUT" not in bpy.context.scene.niftools_scene.game:
            # add NiTriShape's specular property
            # but NOT for sid meier's railroads and other extra shader
            # games (they use specularity even without this property)
            if bpy.context.scene.niftools_scene.game in USED_EXTRA_SHADER_TEXTURES:
                return
            eps = NifOp.props.epsilon
            if (b_mat.specular_color.r > eps) or (b_mat.specular_color.g > eps) or (b_mat.specular_color.b > eps):
                n_node.add_property(self.get_matching_block("NiSpecularProperty", flags=flags))

    def export_wireframe_property(self, b_obj, n_node, flags=0x0001):
        """Return existing wire property with given flags, or create new one
        if an wire property with required flags is not found."""
        for b_mod in b_obj.modifiers:
            if b_mod.type == "WIREFRAME":
                n_node.add_property(self.get_matching_block("NiWireframeProperty", flags=flags))

    def export_stencil_property(self, b_mat, n_node, flags=None):
        """Return existing stencil property with given flags, or create new one
        if an identical stencil property."""
        # no stencil property
        if b_mat.use_backface_culling:
            return
        if bpy.context.scene.niftools_scene.is_fo3():
            flags = 19840
        # search for duplicate
        n_node.add_property(self.get_matching_block("NiStencilProperty", flags=flags))

    def export_ni_string_extra_data_upb(self, n_node, b_obj):
        """Export UPB NiStringExtraData if not optimizer junk."""

        if b_obj.nif_object.upb:
            if 'BSBoneLOD' in b_obj.nif_object.upb or 'Bip' in b_obj.nif_object.upb:
                n_ni_string_extra_data = block_store.create_block("NiStringExtraData")
                n_ni_string_extra_data.name = 'UPB'
                n_ni_string_extra_data.string_data = b_obj.nif_object.upb
                n_node.add_extra_data(n_ni_string_extra_data)

    def export_ni_string_extra_data_prn(self, n_root_node, b_root_obj):
        """Export weapon location."""

        if bpy.context.scene.niftools_scene.is_bs():
            loc = b_root_obj.nif_object.prn_location
            if loc:
                n_ni_string_extra_data = block_store.create_block("NiStringExtraData")
                n_ni_string_extra_data.name = 'Prn'
                n_ni_string_extra_data.string_data = loc
                n_root_node.add_extra_data(n_ni_string_extra_data)

    def export_bs_inv_marker(self, n_root_node, b_root_obj):
        """Attaches a BSInvMarker to n_root if desired and fill in its values"""
        niftools_scene = bpy.context.scene.niftools_scene
        bs_inv_store = b_root_obj.nif_object.bs_inv
        if niftools_scene.is_skyrim() and bs_inv_store:
            bs_inv = bs_inv_store[0]
            n_bs_inv_marker = NifClasses.BSInvMarker(n_root_node.context)
            n_bs_inv_marker.name = bs_inv.name
            n_bs_inv_marker.rotation_x = round((-bs_inv.x % (2 * pi)) * 1000)
            n_bs_inv_marker.rotation_y = round((-bs_inv.y % (2 * pi)) * 1000)
            n_bs_inv_marker.rotation_z = round((-bs_inv.z % (2 * pi)) * 1000)
            n_bs_inv_marker.zoom = bs_inv.zoom
            n_root_node.add_extra_data(n_bs_inv_marker)

    def export_bs_x_flags(self, n_root_node, b_root_obj):
        """Export BSXFlags and update to enable collision and animation if needed."""

        if bpy.context.scene.niftools_scene.is_bs():
            n_bs_x_flags = block_store.create_block("BSXFlags")
            n_bs_x_flags.name = 'BSX'
            n_root_node.add_extra_data(n_bs_x_flags)

            # Export root object's BSXFlags property
            n_bs_x_flags.integer_data = b_root_obj.nif_object.bsxflags

            # Set or clear animated bit
            if self.has_animation():
                n_bs_x_flags.integer_data |= 0x1
            else:
                n_bs_x_flags.integer_data &= ~0x1

            # Set or clear Havok bit
            if self.has_collision():
                n_bs_x_flags.integer_data |= 0x2
            else:
                n_bs_x_flags.integer_data &= ~0x2

            # Set or clear complex bit
            if self.has_dynamic_collision() and len(self.has_collision()) > 1:
                n_bs_x_flags.integer_data |= 0x4
            else:
                n_bs_x_flags.integer_data &= ~0x4

            # Set or clear dynamic bit
            if self.has_dynamic_collision():
                n_bs_x_flags.integer_data |= 0x20
            else:
                n_bs_x_flags.integer_data &= ~0x20

    def has_collision(self):
        """Helper function that determines if a blend file contains a collider."""
        b_objs = []
        for b_obj in bpy.data.objects:
            if b_obj.rigid_body and not b_obj.parent.rigid_body:
                b_objs.append(b_obj)

        return b_objs

    def has_dynamic_collision(self):
        """Helper function that determines if a blend file contains a collider with dynamic motion system."""
        b_objs = []
        for b_obj in bpy.data.objects:
            if b_obj.rigid_body:
                if not 'INVALID' in b_obj.nif_collision.motion_system and not 'FIXED' in b_obj.nif_collision.motion_system:
                    b_objs.append(b_obj)

        return b_objs

    def has_animation(self):
        """Helper function that determines if a blend file contains a collider with dynamic motion system."""
        for b_obj in bpy.data.objects:
            if b_obj.animation_data:
                return True
