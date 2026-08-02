"""Main module for exporting NIF object property blocks."""

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


from math import pi

import bpy
from ....modules.nif_export.block_registry import block_store
from ....modules.nif_export.property.material import MaterialProperty
from ....modules.nif_export.property.texture import TextureProperty
from ....properties.object import BSX_FLAG_BITS
from ....modules.nif_export.animation.common import has_animation
from ....utils.consts import USED_EXTRA_SHADER_TEXTURES
from ....utils import decal
from ....utils.flags import bit_labels, bit_mask, to_unsigned_32
from ....utils.logging import NifLog
from ....utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses

# The BSX bits the export derives, resolved against the table the checkboxes are built from
BSX_ANIMATED = bit_mask(BSX_FLAG_BITS, 'animated')
BSX_HAVOK = bit_mask(BSX_FLAG_BITS, 'havok')
BSX_DYNAMIC = bit_mask(BSX_FLAG_BITS, 'dynamic')

# Motion systems that never move the body, so they do not make a nif dynamic
STATIC_MOTION_SYSTEMS = ('MO_SYS_INVALID', 'MO_SYS_FIXED', 'MO_SYS_KEYFRAMED')


class ObjectProperty:
    """
    Main interface class for exporting NIF object property blocks
    (i.e., NiMaterialProperty, NiAlphaProperty, BSLightingShaderProperty).
    """

    def __init__(self):
        self.material_property_helper = MaterialProperty()
        self.texture_property_helper = TextureProperty()

    def export_object_properties(self, b_obj, n_node, idx=0):
        """
        This is the main property processor that attaches
        all suitable properties gauged from b_obj and b_mat to n_block.
        """

        if not NifOp.is_type_enabled('MATERIAL'):
            return

        if b_obj.material_slots:
            b_mat = b_obj.material_slots[idx].material
        else:
            b_mat = None
            NifLog.warn(f"Mesh object {b_obj.name} has no material. "
                        f"No material, texture or shader properties will be exported for it.")

        if b_obj and b_mat:
            # export and add properties to n_block
            self.export_alpha_property(b_mat, n_node),
            self.export_wireframe_property(b_obj, n_node),
            self.export_stencil_property(b_mat, n_node),
            self.export_specular_property(b_mat, n_node),
            self.material_property_helper.export_ni_material_property(b_mat, n_node)
            self.texture_property_helper.export_texture_properties(b_mat, n_node, b_obj)

    def export_root_node_properties(self, n_root_node, b_root_objects, b_exportable_objects, b_collision_objects):
        """Wrapper for exporting properties that are commonly attached to the nif root"""

        NifLog.info(f"Exporting root node properties...")

        # Add vertex color and zbuffer properties for civ4 and railroads
        if bpy.context.scene.niftools_scene.game in (
                'CIVILIZATION_IV', 'SID_MEIER_S_RAILROADS', 'EMPIRE_EARTH_II', 'ZOO_TYCOON_2'):
            self.export_vertex_color_property(n_root_node)
            self.export_z_buffer_property(n_root_node)

        # Single-valued extra data can only come from one object. When a meta root was created
        # for several Blender roots, the first one stands in for the nif root
        b_root_obj = b_root_objects[0] if b_root_objects else None
        if b_root_obj:
            self.export_ni_string_extra_data_upb(n_root_node, b_root_obj)
            self.export_ni_string_extra_data_prn(n_root_node, b_root_obj)
            self.export_bs_inv_marker(n_root_node, b_root_obj)
            self.export_decal_placement(n_root_node, b_root_obj)
            self.export_skeleton_id(n_root_node, b_root_obj)

        self.export_bs_x_flags(n_root_node, b_root_objects, b_exportable_objects, b_collision_objects)

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
        if b_mat.nif_alpha.use_alpha:
            n_ni_alpha_property = block_store.create_block("NiAlphaProperty")
            n_node.add_property(n_ni_alpha_property)

            n_ni_alpha_property.flags.alpha_blend = b_mat.nif_alpha.enable_blending
            n_ni_alpha_property.flags.source_blend_mode = NifClasses.AlphaFunction[b_mat.nif_alpha.source_blend_mode]
            n_ni_alpha_property.flags.destination_blend_mode = NifClasses.AlphaFunction[b_mat.nif_alpha.destination_blend_mode]
            n_ni_alpha_property.flags.test_func = NifClasses.TestFunction[b_mat.nif_alpha.alpha_test_function]
            n_ni_alpha_property.flags.no_sorter = b_mat.nif_alpha.no_sorter

            # The shader sockets mirror these panel properties for the viewport;
            # export reads the same source of truth used by the blending fields.
            n_ni_alpha_property.flags.alpha_test = b_mat.nif_alpha.enable_testing
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
        """Write the object's UPB back out verbatim, if it has one."""

        if not b_obj.nif_object.upb:
            return

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

    def export_decal_placement(self, n_root_node, b_root_obj):
        """Export the root's viewport-edited decal point/normal arrays."""

        b_store = b_root_obj.nif_object.bs_decal_placement
        if not b_store:
            return

        niftools_scene = bpy.context.scene.niftools_scene
        if not (niftools_scene.is_fo3() or niftools_scene.is_skyrim()):
            NifLog.warn(
                f"'{b_root_obj.name}' has decal placement data, but "
                f"{niftools_scene.game} does not support BSDecalPlacementVectorExtraData; "
                f"the data was not exported.")
            return

        for data_index, b_data in enumerate(b_store):
            # Do not associate the extra block with b_root_obj in the block registry: that
            # object is already mapped to its NiNode, which later animation/constraint passes
            # still need to resolve.
            n_extra = block_store.create_block("BSDecalPlacementVectorExtraData")
            n_extra.name = b_data.name
            n_extra.float_data = b_data.float_data
            n_extra.num_vector_blocks = len(b_data.vector_blocks)
            n_extra.reset_field("vector_blocks")

            for block_index, (b_vector_block, n_vector_block) in enumerate(
                    zip(b_data.vector_blocks, n_extra.vector_blocks)):
                n_pairs = []
                for point_index, b_point in enumerate(b_vector_block.points):
                    if b_point.helper is None:
                        NifLog.warn(
                            f"Skipped missing viewport handle for decal point "
                            f"{data_index + 1}.{block_index + 1}.{point_index + 1} on "
                            f"'{b_root_obj.name}'.")
                        continue
                    n_pairs.append(decal.helper_point_and_normal(
                        b_root_obj, b_point.helper, b_point.normal_length))

                n_vector_block.num_vectors = len(n_pairs)
                n_vector_block.reset_field("points")
                n_vector_block.reset_field("normals")
                for pair_index, (n_point, n_normal) in enumerate(n_pairs):
                    n_vector_block.points[pair_index].x = n_point[0]
                    n_vector_block.points[pair_index].y = n_point[1]
                    n_vector_block.points[pair_index].z = n_point[2]
                    n_vector_block.normals[pair_index].x = n_normal[0]
                    n_vector_block.normals[pair_index].y = n_normal[1]
                    n_vector_block.normals[pair_index].z = n_normal[2]

            n_root_node.add_extra_data(n_extra)

    def export_skeleton_id(self, n_root_node, b_root_obj):
        """Attach the SkeletonID of an armature root, if it has one."""

        if b_root_obj.type != 'ARMATURE':
            return

        n_skeleton_id = b_root_obj.data.nif_armature.skeleton_id
        if not n_skeleton_id:
            # an armature that is only there to skin a mesh carries no id
            return

        n_ni_integer_extra_data = block_store.create_block("NiIntegerExtraData")
        n_ni_integer_extra_data.name = 'SkeletonID'
        n_ni_integer_extra_data.integer_data = n_skeleton_id
        n_root_node.add_extra_data(n_ni_integer_extra_data)

    def export_bs_x_flags(self, n_root_node, b_root_objects, b_exportable_objects, b_collision_objects):
        """
        Export the root BSXFlags, adding the bits that the exported content requires.

        The stored value is the authority: every bit that the user set, or that import read out
        of the source nif, is kept. Most of the bits describe things that cannot be seen in the
        Blender scene at all - a nif whose animation lives in a companion KF file still needs its
        animated bit, an addon or editor marker bit says nothing about the objects being exported -
        so clearing them would silently throw away the only place they are recorded. Only the bits
        that follow directly from what is being written are added on top.
        """

        if not bpy.context.scene.niftools_scene.is_bs():
            # BSXFlags is a Bethesda block, other games have no use for it
            return

        # Several Blender roots end up under one meta root, so the nif root carries all their flags
        bs_x_flags = 0
        for b_root_obj in b_root_objects:
            bs_x_flags |= to_unsigned_32(b_root_obj.nif_object.bsxflags)

        b_havok_objects = self.get_havok_collision_objects(b_collision_objects)

        n_derived_flags = 0
        if has_animation(b_exportable_objects):
            n_derived_flags |= BSX_ANIMATED
        if b_havok_objects:
            n_derived_flags |= BSX_HAVOK
        if self.has_dynamic_collision(b_havok_objects):
            n_derived_flags |= BSX_DYNAMIC

        n_added_flags = n_derived_flags & ~bs_x_flags
        if n_added_flags:
            NifLog.info(f"Enabling BSX flags required by the export: "
                        f"{', '.join(bit_labels(BSX_FLAG_BITS, n_added_flags))}")
        bs_x_flags |= n_derived_flags

        if not bs_x_flags:
            # nothing to say, so no reason to write the block
            return

        n_bs_x_flags = block_store.create_block("BSXFlags")
        n_bs_x_flags.name = 'BSX'
        n_bs_x_flags.integer_data = bs_x_flags
        n_root_node.add_extra_data(n_bs_x_flags)

        NifLog.debug(f"Exported BSXFlags {bs_x_flags}")

    def get_havok_collision_objects(self, b_collision_objects):
        """
        The collision objects that are exported as havok bodies of their own.

        Sub-shapes of a list shape are parented to the body that holds them and carry no
        bhkRigidBody, and objects named 'bound' become a bounding box rather than collision,
        so neither of them makes the nif a havok nif.
        """

        return [b_col_obj for b_col_obj in b_collision_objects
                if "bound" not in b_col_obj.name.lower()
                and not (b_col_obj.parent and b_col_obj.parent.rigid_body)]

    def has_dynamic_collision(self, b_havok_objects):
        """True if any exported havok body is simulated rather than held in place."""

        return any(b_col_obj.nif_collision.motion_system not in STATIC_MOTION_SYSTEMS
                   for b_col_obj in b_havok_objects)
