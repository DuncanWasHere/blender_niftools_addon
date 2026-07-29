"""Export particle animation channels from slotted Blender actions."""

import mathutils
import re

from ....modules.nif_export.particle import modifier as ParticleModifier
from ....modules.nif_export.animation.common import (
    AnimationCommon,
    V_CONTROLLED_BLOCK_CONTROLLER,
    create_blend_interpolator,
    set_controlled_block_strings,
)
from ....modules.nif_export.block_registry import block_store
from ....utils.logging import NifError
from ....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class ParticleAnimation(AnimationCommon):
    """Export particle settings channels and legacy particle color animation."""

    BIRTH_RATE_PATH = "nif_particle_system.birth_rate"
    EMITTER_ACTIVE_PATH = "nif_particle_system.emitter_visibility_value"

    def __init__(self):
        super().__init__()
        self.modifier_helper = ParticleModifier.Modifier()

    @staticmethod
    def settings_using_action(b_obj, b_action, b_action_slot):
        """Find the ParticleSettings datablock owning this action slot."""

        for b_psys in b_obj.particle_systems:
            b_settings = b_psys.settings
            b_anim_data = b_settings.animation_data
            if not b_anim_data:
                continue
            if (b_anim_data.action == b_action
                    and (b_action_slot is None
                         or b_anim_data.action_slot == b_action_slot)):
                return b_settings
            if any(
                    strip.action == b_action
                    and (b_action_slot is None or strip.action_slot == b_action_slot)
                    for track in b_anim_data.nla_tracks for strip in track.strips):
                return b_settings
        return None

    @staticmethod
    def get_particle_target(b_obj):
        """Return the exported particle system represented by a Blender object."""

        return next((
            n_block for n_block, b_block_obj in block_store.block_to_obj.items()
            if b_block_obj is b_obj
            and isinstance(n_block, NifClasses.NiParticleSystem)
        ), None)

    def export_particle_animations(self, b_controlled_blocks,
                                   n_ni_controller_sequence=None):
        for b_strip, b_obj in b_controlled_blocks:
            if not b_obj.particle_systems:
                continue

            b_action = b_strip.action
            b_action_slot = b_strip.action_slot
            b_settings = self.settings_using_action(
                b_obj, b_action, b_action_slot)
            action_fcurves = self.get_fcurves_from_action(
                b_action, b_action_slot)

            n_particle_system = self.get_particle_target(b_obj)
            if (b_settings is not None
                    and n_particle_system is not None
                    and n_ni_controller_sequence is not None):
                self.export_controller_channels(
                    action_fcurves, b_settings, n_particle_system,
                    n_ni_controller_sequence)

            # Preserve the add-on's older particle color-action support without
            # mistaking an emission-only action for an incomplete RGBA action.
            color_data = [
                fcurve for fcurve in action_fcurves
                if "color" in fcurve.data_path.lower()
                or "inputs[0]" in fcurve.data_path.lower()
            ]
            alpha_data = [
                fcurve for fcurve in action_fcurves
                if "alpha" in fcurve.data_path.lower()
                or "inputs[4]" in fcurve.data_path.lower()
            ]
            if color_data or alpha_data:
                if len(color_data) + len(alpha_data) != 4:
                    raise NifError(
                        f"Incomplete particle color key set for action {b_action.name}. "
                        "Keyframe every RGBA channel.")
                color_curves = [
                    (frame, color.from_scene_linear_to_srgb())
                    for frame, color in self.iter_frame_key(
                        color_data, mathutils.Color)
                ]
                alpha_curves = [
                    (point.co[0], point.co[1])
                    for fcurve in alpha_data
                    for point in fcurve.keyframe_points
                ]
                if n_particle_system:
                    self.modifier_helper.export_color_modifier(
                        b_obj, (color_curves, alpha_curves),
                        n_particle_system)

    def export_controller_channels(self, fcurves, b_settings,
                                   n_particle_system, n_sequence):
        """Export all scalar particle controller-sequence channels."""

        n_emitter = next((
            modifier for modifier in n_particle_system.modifiers
            if isinstance(modifier, NifClasses.NiPSysEmitter)
        ), None)
        emitter_id = str(
            getattr(n_emitter, "name", "")
            or "")

        for fcurve in fcurves:
            match = re.fullmatch(
                r"nif_particle_system\.controller_channels\[(\d+)\]\."
                r"(float_value|bool_value)",
                fcurve.data_path,
            )
            if match:
                channel_index = int(match.group(1))
                channels = b_settings.nif_particle_system.controller_channels
                if channel_index >= len(channels):
                    continue
                channel = channels[channel_index]
                controller_type = channel.controller_type
                controller_id = channel.controller_id
                interpolator_id = channel.interpolator_id
                value_type = channel.value_type
            elif fcurve.data_path == self.BIRTH_RATE_PATH:
                # Compatibility with actions created by the first typed-particle
                # builds before controller channels became generic.
                controller_type = "NiPSysEmitterCtlr"
                controller_id = emitter_id
                interpolator_id = "BirthRate"
                value_type = "FLOAT"
            elif fcurve.data_path == self.EMITTER_ACTIVE_PATH:
                controller_type = "NiPSysEmitterCtlr"
                controller_id = emitter_id
                interpolator_id = "EmitterActive"
                value_type = "BOOL"
            else:
                continue

            n_controller = self.find_or_create_controller(
                n_particle_system, controller_type, controller_id, fcurve)
            if n_controller is None:
                continue
            if value_type == "BOOL":
                n_interpolator = self.bool_interpolator(fcurve)
                if hasattr(n_controller, "visibility_interpolator"):
                    n_controller.visibility_interpolator = create_blend_interpolator(
                        "NiBlendBoolInterpolator")
                elif hasattr(n_controller, "interpolator"):
                    n_controller.interpolator = create_blend_interpolator(
                        "NiBlendBoolInterpolator")
            else:
                n_interpolator = self.float_interpolator(fcurve)
                if hasattr(n_controller, "interpolator"):
                    n_controller.interpolator = create_blend_interpolator(
                        "NiBlendFloatInterpolator")
            self.add_controlled_block(
                n_sequence, n_controller, n_interpolator,
                n_particle_system.name, controller_type,
                controller_id, interpolator_id)

    def find_or_create_controller(self, n_particle_system, controller_type,
                                  controller_id, fcurve):
        n_controller = next((
            controller for controller in n_particle_system.get_controllers()
            if type(controller).__name__ == controller_type
            and (not controller_id
                 or str(getattr(controller, "modifier_name", "")) == controller_id)
        ), None)
        if n_controller is not None:
            return n_controller
        try:
            n_controller = block_store.create_block(controller_type)
        except Exception:
            return None
        n_controller.flags = 72
        n_controller.frequency = 1.0
        points = list(fcurve.keyframe_points)
        if points:
            n_controller.start_time = points[0].co[0] / self.fps
            n_controller.stop_time = points[-1].co[0] / self.fps
        if controller_id and hasattr(n_controller, "modifier_name"):
            n_controller.modifier_name = controller_id
        n_particle_system.add_controller(n_controller)
        return n_controller

    @staticmethod
    def add_controlled_block(n_sequence, n_controller, n_interpolator,
                             node_name, controller_type, controller_id,
                             interpolator_id):
        controlled = n_sequence.add_controlled_block()
        controlled.priority = 0
        controlled.interpolator = n_interpolator
        if NifData.data.version <= V_CONTROLLED_BLOCK_CONTROLLER:
            controlled.controller = n_controller
        set_controlled_block_strings(
            controlled, n_sequence,
            node_name=node_name,
            controller_type=controller_type,
            controller_id=controller_id,
            interpolator_id=interpolator_id,
        )

    def float_interpolator(self, fcurve):
        points = list(fcurve.keyframe_points)
        n_interpolator = block_store.create_block("NiFloatInterpolator")
        if points and all(
                abs(point.co[1] - points[0].co[1]) < 1e-7
                for point in points[1:]):
            n_interpolator.value = points[0].co[1]
            return n_interpolator

        n_data = block_store.create_block("NiFloatData")
        n_data.data.num_keys = len(points)
        interpolation = (
            self.get_n_interp_from_b_interp(points[0].interpolation)
            if points else NifClasses.KeyType.LINEAR_KEY)
        n_data.data.interpolation = interpolation
        n_data.data.reset_field("keys")
        for n_key, point in zip(n_data.data.keys, points):
            n_key.time = point.co[0] / self.fps
            n_key.value = point.co[1]
            if interpolation == NifClasses.KeyType.QUADRATIC_KEY:
                n_key.forward = 3.0 * (point.co[1] - point.handle_left[1])
                n_key.backward = 3.0 * (point.handle_right[1] - point.co[1])
        n_interpolator.data = n_data
        return n_interpolator

    def bool_interpolator(self, fcurve):
        points = list(fcurve.keyframe_points)
        n_interpolator = block_store.create_block("NiBoolInterpolator")
        values = [bool(round(point.co[1])) for point in points]
        if values and all(value == values[0] for value in values[1:]):
            n_interpolator.value = values[0]
            return n_interpolator

        n_data = block_store.create_block("NiBoolData")
        n_data.data.num_keys = len(points)
        n_data.data.interpolation = NifClasses.KeyType.CONST_KEY
        n_data.data.reset_field("keys")
        for n_key, point, value in zip(n_data.data.keys, points, values):
            n_key.time = point.co[0] / self.fps
            n_key.value = value
        n_interpolator.data = n_data
        return n_interpolator
