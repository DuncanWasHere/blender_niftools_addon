"""Main module for exporting texture animation blocks."""

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


import re

import bpy
from ....modules.nif_export.animation.common import (AnimationCommon, attach_controller,
                                                                   get_n_target, get_n_property_target)
from ....modules.nif_export.block_registry import block_store
from ....modules.nif_export.property.texture.common import TextureCommon
from ....utils.logging import NifLog
from ....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses



class TextureAnimation(AnimationCommon):
    """
    Main interface class for exporting texture animation blocks
    (i.e., NiTextureTransformController, NiFlipController, NiUVController) and keyframe data.
    Texture animations for Bethesda shader properties (only for Skyrim and above)
    are handled by the shader animation class.
    """

    # TODO: Test NiFlipController and NiUVController export methods

    def __init__(self):
        super().__init__()

    def export_texture_animations(self, b_controlled_blocks, n_ni_controller_sequence=None):
        """
        Export texture animations based on UV Warp modifier FCurves.
        """

        for b_controlled_block in b_controlled_blocks:
            b_strip, b_obj = b_controlled_block
            b_action = b_strip.action
            b_action_slot = b_strip.action_slot

            # The texture transform is animated on the mapping node of the material, which
            # is what the importer builds, so the curves are found by matching that node
            # rather than by looking for a UV warp modifier.
            uv_curves = self.get_mapping_curves(b_obj, b_action, b_action_slot)
            if not uv_curves:
                continue

            n_ni_geometry, n_ni_geometry_name, n_ni_texturing_property = get_n_property_target(
                b_obj, NifClasses.NiTexturingProperty)

            if n_ni_geometry:
                if not n_ni_texturing_property:
                    NifLog.warn(
                        f"Object {b_obj.name} has no NiTexturingProperty! "
                        f"Texture animation for {b_action.name} will not be exported "
                        f"(ensure that an unsupported shader property is not applied)."
                    )
                    continue

                n_tex_desc = n_ni_texturing_property.base_texture
                n_tex_desc.has_texture_transform = True
                n_tex_desc.translation.u, n_tex_desc.translation.v = (0, 0)
                n_tex_desc.scale.u, n_tex_desc.scale.v = (1, 1)
                n_tex_desc.rotation = 0.0
                n_tex_desc.transform_method = NifClasses.TransformMethod.MAX
                n_tex_desc.center.u, n_tex_desc.center.v = (0.5, 0.5)

            action_fcurves = self.get_fcurves_from_action(b_action, b_action_slot)

            for fcurve, operation, value_scale in uv_curves:
                self.export_ni_texture_transform_controller(
                    n_ni_texturing_property, n_ni_geometry_name, action_fcurves, fcurve, b_action,
                    operation, n_ni_controller_sequence, value_scale
                )

    # Mapping node inputs and the transform each channel represents. Translation
    # curves in Blender show the texture moving in-game rather than NifSkope's
    # opposite interpretation of the stored coordinate offset. U is therefore
    # negated on export. V's motion and coordinate-axis inversions cancel.
    MAPPING_OPERATIONS = {
        (1, 0): (NifClasses.TransformMember.TT_TRANSLATE_U, "TT_TRANSLATE_U", -1.0),
        (1, 1): (NifClasses.TransformMember.TT_TRANSLATE_V, "TT_TRANSLATE_V", 1.0),
        (3, 0): (NifClasses.TransformMember.TT_SCALE_U, "TT_SCALE_U", 1.0),
        (3, 1): (NifClasses.TransformMember.TT_SCALE_V, "TT_SCALE_V", 1.0),
    }

    def get_mapping_curves(self, b_obj, b_action, b_action_slot=None):
        """Find the curves that animate a material's mapping node.

        :return: list of (fcurve, (operation, name), value scale) for each animated channel
        """

        b_materials = [b_material for b_material in getattr(b_obj.data, "materials", ()) or ()
                       if b_material and b_material.node_tree
                       and b_material.node_tree.animation_data
                       and self.uses_action(
                           b_material.node_tree.animation_data, b_action, b_action_slot)]
        if not b_materials:
            return []

        b_mapping_names = {b_node.name for b_material in b_materials
                           for b_node in b_material.node_tree.nodes if b_node.type == 'MAPPING'}
        if not b_mapping_names:
            return []

        uv_curves = []
        for b_fcurve in self.get_fcurves_from_action(b_action, b_action_slot):
            match = re.match(r'nodes\["(.+)"\]\.inputs\[(\d+)\]\.default_value$', b_fcurve.data_path)
            if not match or match.group(1) not in b_mapping_names:
                continue
            operation = self.MAPPING_OPERATIONS.get((int(match.group(2)), b_fcurve.array_index))
            if operation:
                uv_curves.append((b_fcurve, operation[:2], operation[2]))
        return uv_curves

    @staticmethod
    def uses_action(b_anim_data, b_action, b_action_slot=None):
        """Whether an animation data block holds this action, active or in a strip."""

        if (b_anim_data.action == b_action
                and (b_action_slot is None or b_anim_data.action_slot == b_action_slot)):
            return True
        return any(strip.action == b_action
                   and (b_action_slot is None or strip.action_slot == b_action_slot)
                   for track in b_anim_data.nla_tracks for strip in track.strips)

    def export_ni_texture_transform_controller(self, n_ni_texturing_property, n_ni_geometry_name,
                                               action_fcurves, fcurve, b_action, operation,
                                               n_ni_controller_sequence=None, value_scale=1.0):
        """Export a NiTextureTransformController block."""

        n_ni_texture_transform_controller = block_store.create_block("NiTextureTransformController")

        self.set_flags_and_timing(n_ni_texture_transform_controller, action_fcurves, *b_action.frame_range)

        n_ni_texture_transform_controller.texture_slot = NifClasses.TexType.BASE_MAP
        n_ni_texture_transform_controller.operation = operation[0]

        # Create interpolators and data
        n_ni_float_interpolator = block_store.create_block("NiFloatInterpolator")
        n_ni_float_interpolator.data = self.export_fcurve_to_nif_keys(fcurve, value_scale)
        n_ni_texture_transform_controller.interpolator = n_ni_float_interpolator

        attach_controller(n_ni_texture_transform_controller, n_ni_float_interpolator,
                          n_ni_geometry_name, "NiTextureTransformController",
                          n_ctrl_target=n_ni_texturing_property,
                          n_sequence=n_ni_controller_sequence,
                          property_type="NiTexturingProperty",
                          controller_id=f"0-0-{operation[1]}")

        return n_ni_texture_transform_controller

    def get_operation_from_fcurve(self, fcurve):
        """Map a data path to a NIF transform operation."""

        transform_member = None
        transform_string = None

        data_path = fcurve.data_path
        
        if "offset" in data_path:
            transform_member = NifClasses.TransformMember.TT_TRANSLATE_U if fcurve.array_index == 0 else NifClasses.TransformMember.TT_TRANSLATE_V
            transform_string = "TT_TRANSLATE_U" if fcurve.array_index == 0 else "TT_TRANSLATE_V"

            return (transform_member, transform_string)
        elif "scale" in data_path:
            transform_member = NifClasses.TransformMember.TT_SCALE_U if fcurve.array_index == 0 else NifClasses.TransformMember.TT_SCALE_V
            transform_string = "TT_SCALE_U" if fcurve.array_index == 0 else "TT_SCALE_V"

            return (transform_member, transform_string)
        elif "rotation" in data_path:
            transform_member = NifClasses.TransformMember.TT_ROTATE
            transform_string = "TT_ROTATE"

            return (transform_member, transform_string)
        return None

    def export_fcurve_to_nif_keys(self, fcurve, value_scale=1.0):
        n_ni_float_data = block_store.create_block("NiFloatData")
        n_ni_float_data.data.num_keys = len(fcurve.keyframe_points)
        n_ni_float_data.data.reset_field("keys")

        for keyframe, n_key in zip(fcurve.keyframe_points, n_ni_float_data.data.keys):
            time = keyframe.co[0]
            value = keyframe.co[1] * value_scale

            # add each point of the curves
            n_key.interpolation = self.get_n_interp_from_b_interp(keyframe.interpolation)
            n_key.time = time / self.fps
            n_key.value = value

        n_ni_float_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY

        return n_ni_float_data

    def export_ni_uv_controller(self, n_ni_geometry, b_action):
        """Export a NiUVController block."""

        # Get F-curves - a bit more elaborate here so we can zip with the NiUVData later
        # nb. these are actually specific to the texture slot in blender
        # here we don't care and just take the first F-curve that matches
        b_f_curves = []
        for dp, ind in (("offset", 0), ("offset", 1), ("scale", 0), ("scale", 1)):
            for fcu in b_action.fcurves:
                if dp in fcu.data_path and fcu.array_index == ind:
                    b_f_curves.append(fcu)
                    break
            else:
                b_f_curves.append(None)

        # continue if at least one fcurve exists
        if not any(b_f_curves):
            return

        # get the uv curves and translate them into nif data
        n_uv_data = NifClasses.NiUVData(NifData.data)
        for fcu, n_uv_group in zip(b_f_curves, n_uv_data.uv_groups):
            if fcu:
                NifLog.debug(f"Exporting {fcu} as NiUVData")
                n_uv_group.num_keys = len(fcu.keyframe_points)
                n_uv_group.interpolation = NifClasses.KeyType.LINEAR_KEY
                n_uv_group.reset_field("keys")
                for b_point, n_key in zip(fcu.keyframe_points, n_uv_group.keys):
                    # add each point of the curve
                    b_frame, b_value = b_point.co
                    if "offset" in fcu.data_path and fcu.array_index == 0:
                        # U is stored opposite to the in-game texture motion shown
                        # by Blender. V's image-axis conversion cancels that inversion.
                        b_value = -b_value
                    n_key.arg = n_uv_group.interpolation
                    n_key.time = b_frame / self.fps
                    n_key.value = b_value

        # if uv data is present then add the controller so it is exported
        if b_f_curves[0].keyframe_points:
            n_ni_uv_controller = NifClasses.NiUVController(NifData.data)
            self.set_flags_and_timing(n_ni_uv_controller, b_f_curves, *b_action.frame_range)
            n_ni_uv_controller.data = n_uv_data
            # attach block to geometry
            n_ni_geometry.add_controller(n_ni_uv_controller)

    def export_ni_flip_controller(self, fliptxt, texture, target, target_tex):
        # TODO [animation] port code to use native Blender image strip system
        #                  despite its name a NiFlipController does not flip / mirror a texture
        #                  instead it swaps through a list of textures for a sprite animation
        #
        # fliptxt is a blender text object containing the n_flip definitions
        # texture is the texture object in blender ( texture is used to checked for pack and mipmap flags )
        # target is the NiTexturingProperty
        # target_tex is the texture to n_flip ( 0 = base texture, 4 = glow texture )
        #
        # returns exported NiFlipController

        tlist = fliptxt.asLines()

        # create a NiFlipController
        n_flip = block_store.create_block("NiFlipController", fliptxt)
        target.add_controller(n_flip)

        # fill in NiFlipController's values
        n_flip.flags = 8  # active
        n_flip.frequency = 1.0
        start = bpy.context.scene.frame_start

        n_flip.start_time = (start - 1) * self.fps
        n_flip.stop_time = (bpy.context.scene.frame_end - start) * self.fps
        n_flip.texture_slot = target_tex

        count = 0
        for t in tlist:
            if len(t) == 0:
                continue  # skip empty lines
            # create a NiSourceTexture for each n_flip
            tex = TextureCommon.export_source_texture(texture, t)
            n_flip.num_sources += 1
            n_flip.sources.append(tex)
            count += 1
        if count < 2:
            raise NifLog.warn(f"Error in Texture Flip buffer '{fliptxt.name}': must define at least two textures")
        n_flip.delta = (n_flip.stop_time - n_flip.start_time) / count
