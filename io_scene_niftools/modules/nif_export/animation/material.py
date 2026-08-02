"""Main module for exporting material animation blocks."""

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
import mathutils

from ....modules.nif_export.animation.common import (AnimationCommon, attach_controller,
                                                                   get_n_target, get_n_property_target)
from ....modules.nif_export.block_registry import block_store
from ....utils.logging import NifError, NifLog
from ....utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses


class MaterialAnimation(AnimationCommon):

    def __init__(self):
        super().__init__()

    def export_material_animations(self, b_controlled_blocks, n_ni_controller_sequence=None):
        """Export material animations for given geometry."""

        if not NifOp.is_type_enabled('MATERIAL'):
            return

        for b_controlled_block in b_controlled_blocks:
            b_strip, b_obj = b_controlled_block
            b_action = b_strip.action
            b_action_slot = b_strip.action_slot

            if b_obj.particle_systems or b_obj.type != 'MESH':
                continue

            n_ni_geometry, n_ni_geometry_name, n_mat_prop = get_n_property_target(
                b_obj, NifClasses.NiMaterialProperty)

            if n_ni_geometry:
                if not n_mat_prop:
                    NifLog.warn(
                        f"Object {b_obj.name} has no NiMaterialProperty! "
                        f"Material animation for {b_action.name} will not be exported "
                        f"(ensure that an unsupported shader property is not applied)."
                    )
                    continue

            self.export_material_alpha_color_controller(
                n_mat_prop, n_ni_geometry_name, b_action,
                n_ni_controller_sequence, b_action_slot)

    @staticmethod
    def resolve_geometry(n_block):
        """Return the geometry block that holds the properties.

        Exporting a mesh registers both the geometry and its data against the same
        Blender object, so the lookup can land on the data block, which has no properties.
        """

        if n_block is None or hasattr(n_block, "properties"):
            return n_block
        for n_candidate in block_store.block_to_obj:
            if isinstance(n_candidate, NifClasses.NiTriBasedGeom) and n_candidate.data is n_block:
                return n_candidate
        return None

    def get_socket_names(self, b_action, b_action_slot=None):
        """Map the data path of every node socket curve in an action to the socket's name.

        The path names the node and the socket index, so the owning node tree is needed
        to turn that index back into a name that does not shift when a group changes.
        """

        socket_names = {}
        b_tree = next((b_material.node_tree for b_material in bpy.data.materials
                       if b_material.node_tree and b_material.node_tree.animation_data
                       and MaterialAnimation.uses_action(
                           b_material.node_tree.animation_data, b_action, b_action_slot)),
                      None)
        if b_tree is None:
            return socket_names

        for b_fcurve in self.get_fcurves_from_action(b_action, b_action_slot):
            match = re.match(r'nodes\["(.+)"\]\.inputs\[(\d+)\]\.default_value$', b_fcurve.data_path)
            if not match:
                continue
            b_node = b_tree.nodes.get(match.group(1))
            index = int(match.group(2))
            if b_node and index < len(b_node.inputs):
                socket_names[b_fcurve.data_path] = b_node.inputs[index].name
        return socket_names

    @staticmethod
    def uses_action(b_anim_data, b_action, b_action_slot=None):
        """Whether an animation data block holds this action, active or in a strip."""

        if (b_anim_data.action == b_action
                and (b_action_slot is None or b_anim_data.action_slot == b_action_slot)):
            return True
        return any(strip.action == b_action
                   and (b_action_slot is None or strip.action_slot == b_action_slot)
                   for track in b_anim_data.nla_tracks for strip in track.strips)

    def export_material_alpha_color_controller(self, n_mat_prop, n_ni_geometry_name, b_action,
                                               n_ni_controller_sequence=None, b_action_slot=None):
        """Export the material alpha or color controller data."""

        action_fcurves = self.get_fcurves_from_action(b_action, b_action_slot)

        # Curves on a shader node group address a socket by index, and that index moves
        # whenever the group changes, so they are matched on the socket's name instead.
        socket_names = self.get_socket_names(b_action, b_action_slot)

        def curves_for(socket_name, *legacy_fragments):
            return [fcu for fcu in action_fcurves
                    if socket_names.get(fcu.data_path) == socket_name
                    or (socket_names.get(fcu.data_path) is None
                        and any(fragment in fcu.data_path for fragment in legacy_fragments))]

        ambient_color_fcurves = curves_for("Ambient Color", "ambient")
        diffuse_color_fcurves = curves_for("Material Diffuse Color", "diffuse")
        emission_color_fcurves = curves_for("Emissive Color", "emission_color", "inputs[27]")
        specular_color_fcurves = curves_for("Specular Color", "specular_tint", "inputs[14]")

        alpha_fcurves = curves_for("Alpha", "alpha", "inputs[4]")
        emission_strength_fcurves = curves_for("Emissive Mult", "emission_strength", "inputs[28]")

        for fcus, num_fcus in ((ambient_color_fcurves, 3), (diffuse_color_fcurves, 3), (emission_color_fcurves, 3), (specular_color_fcurves, 3)):
            if fcus and len(fcus) != num_fcus:
                raise NifError(
                    f"Incomplete color key set for action {b_action.name}."
                    f"Ensure that if a color is keyframed for a property, the alpha channel is not keyframed.")

        #TODO: enable export for ambient, diffuse, and specular animation

        ambient_curves = []
        diffuse_curves = []
        emission_color_curves = []
        specular_curves = []

        alpha_curves = []
        emission_strength_curves = []

        for frame, ambient in self.iter_frame_key(ambient_color_fcurves, mathutils.Color):
            ambient_curves.append((frame, ambient.from_scene_linear_to_srgb()))

        for frame, diffuse in self.iter_frame_key(diffuse_color_fcurves, mathutils.Color):
            diffuse_curves.append((frame, diffuse.from_scene_linear_to_srgb()))

        for frame, emission_color in self.iter_frame_key(emission_color_fcurves, mathutils.Color):
            emission_color_curves.append((frame, emission_color.from_scene_linear_to_srgb()))

        for frame, specular in self.iter_frame_key(specular_color_fcurves, mathutils.Color):
            specular_curves.append((frame, specular.from_scene_linear_to_srgb()))

        for fcurve in alpha_fcurves:
            for keyframe in fcurve.keyframe_points:
                alpha_curves.append((keyframe.co[0], keyframe.co[1]))

        for fcurve in emission_strength_fcurves:
            for keyframe in fcurve.keyframe_points:
                emission_strength_curves.append((keyframe.co[0], keyframe.co[1]))


        if emission_color_curves:
            self.export_emissive_color_controller(emission_color_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence)

        if alpha_curves:
            self.export_alpha_controller(alpha_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence)

        if emission_strength_curves:
            self.export_emissive_strength_controller(emission_strength_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence)

    def export_emissive_color_controller(self, emission_color_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence=None):
        # create the key data
        n_key_data = block_store.create_block("NiPosData")
        n_key_data.data.num_keys = len(emission_color_curves)
        n_key_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_key_data.data.reset_field("keys")

        for key, (frame, color) in zip(n_key_data.data.keys, emission_color_curves):
            key.time = frame / self.fps
            key.value.x = color.r
            key.value.y = color.g
            key.value.z = color.b

        n_mat_ctrl = block_store.create_block("NiMaterialColorController")
        n_mat_ipol = block_store.create_block("NiPoint3Interpolator")
        n_mat_ctrl.interpolator = n_mat_ipol

        self.set_flags_and_timing(n_mat_ctrl, action_fcurves, *b_action.frame_range)

        # set target color only for color controller
        n_mat_ctrl.set_target_color(NifClasses.MaterialColor.TC_SELF_ILLUM)
        n_mat_ipol.data = n_key_data

        attach_controller(n_mat_ctrl, n_mat_ipol, n_ni_geometry_name, "NiMaterialColorController",
                          n_ctrl_target=n_mat_prop, n_sequence=n_ni_controller_sequence,
                          property_type="NiMaterialProperty", controller_id="TC_SELF_ILLUM")

    def export_alpha_controller(self, alpha_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence=None):
        # create the key data
        n_key_data = block_store.create_block("NiFloatData")
        n_key_data.data.num_keys = len(alpha_curves)
        n_key_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_key_data.data.reset_field("keys")

        for key, (frame, strength) in zip(n_key_data.data.keys, alpha_curves):
            key.time = frame / self.fps
            key.value = strength

        n_mat_ctrl = block_store.create_block("NiAlphaController")
        n_mat_ipol = block_store.create_block("NiFloatInterpolator")
        n_mat_ctrl.interpolator = n_mat_ipol

        self.set_flags_and_timing(n_mat_ctrl, action_fcurves, *b_action.frame_range)

        n_mat_ipol.data = n_key_data

        attach_controller(n_mat_ctrl, n_mat_ipol, n_ni_geometry_name, "NiAlphaController",
                          n_ctrl_target=n_mat_prop, n_sequence=n_ni_controller_sequence,
                          property_type="NiMaterialProperty")

    def export_emissive_strength_controller(self, emission_strength_curves, action_fcurves, b_action, n_ni_geometry_name, n_mat_prop, n_ni_controller_sequence=None):
        # create the key data
        n_key_data = block_store.create_block("NiFloatData")
        n_key_data.data.num_keys = len(emission_strength_curves)
        n_key_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_key_data.data.reset_field("keys")

        for key, (frame, strength) in zip(n_key_data.data.keys, emission_strength_curves):
            key.time = frame / self.fps
            key.value = strength

        n_mat_ctrl = block_store.create_block("BSMaterialEmittanceMultController")
        n_mat_ipol = block_store.create_block("NiFloatInterpolator")
        n_mat_ctrl.interpolator = n_mat_ipol

        self.set_flags_and_timing(n_mat_ctrl, action_fcurves, *b_action.frame_range)

        n_mat_ipol.data = n_key_data

        attach_controller(n_mat_ctrl, n_mat_ipol, n_ni_geometry_name,
                          "BSMaterialEmittanceMultController",
                          n_ctrl_target=n_mat_prop, n_sequence=n_ni_controller_sequence,
                          property_type="NiMaterialProperty")
