"""This script contains classes to help import animations."""

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
import bpy
import math as python_math
from ....utils.consts import QUAT, EULER, LOC, SCALE
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


_ACTIONS = {}
_ACTION_OWNERS = {}
_ACTION_SLOTS = {}
_FPS = 30
_MAX_KEY_TIME = 0
_DEFAULT_SEQUENCE = None


def clear():
    """Reset animation state shared by all controller import helpers for one NIF."""

    global _FPS, _MAX_KEY_TIME, _DEFAULT_SEQUENCE
    _ACTIONS.clear()
    _ACTION_OWNERS.clear()
    _ACTION_SLOTS.clear()
    _FPS = 30
    _MAX_KEY_TIME = 0
    _DEFAULT_SEQUENCE = None


class Animation:

    def __init__(self):
        self.show_pose_markers()
        # All specialized animation helpers share these per-import registries.
        # we need to be able to map their owner and sequence to blender actions
        # to prevent overwriting existing animations from older imports
        # and still be able to access existing actions from this run
        self.actions = _ACTIONS
        self.action_owners = _ACTION_OWNERS
        self.action_slots = _ACTION_SLOTS

    @property
    def fps(self):
        return _FPS

    @fps.setter
    def fps(self, value):
        global _FPS
        _FPS = value

    @property
    def max_key_time(self):
        return _MAX_KEY_TIME

    @max_key_time.setter
    def max_key_time(self, value):
        global _MAX_KEY_TIME
        _MAX_KEY_TIME = value

    @staticmethod
    def get_controller_data(ctrl):
        """Return the key data of a controller, from its interpolator on newer games or
        directly from the controller itself, or None when it holds no keys of its own.
        """

        if hasattr(ctrl, 'interpolator') and ctrl.interpolator:
            return Animation.get_interpolator_data(ctrl.interpolator)

        data = getattr(ctrl, "data", None)
        if data is None:
            return None
        # these have their data set as a KeyGroup on data
        if isinstance(data, (NifClasses.NiBoolData, NifClasses.NiFloatData, NifClasses.NiPosData)):
            return data.data
        return data

    @staticmethod
    def get_interpolator_data(n_interpolator):
        """Return the key data an interpolator reads from, or None when it has none."""

        if not n_interpolator:
            return None
        if isinstance(n_interpolator, NifClasses.NiBlendInterpolator):
            NifLog.debug(f"{type(n_interpolator).__name__} holds no keys of its own; "
                         f"its animation comes from the controller sequences")
            return None
        data = getattr(n_interpolator, "data", None)
        if data is None:
            return None
        # these have their data set as a KeyGroup on data
        if isinstance(data, (NifClasses.NiBoolData, NifClasses.NiFloatData, NifClasses.NiPosData)):
            return data.data
        return data

    @staticmethod
    def get_keys_values(items):
        """Returns list of times and keys for an array 'items' with key elements having 'time' and 'value' attributes"""
        return [key.time for key in items], [key.value for key in items]

    @staticmethod
    def get_nif_tangents(items, interpolation):
        """Return the stored NIF tangents for quadratic keys.

        NIF's naming follows the key rather than the side of the curve: NifSkope
        evaluates a segment with the current key's ``backward`` tangent and the
        next key's ``forward`` tangent. Other interpolation types do not carry
        compatible tangent values.
        """

        if interpolation != NifClasses.KeyType.QUADRATIC_KEY:
            return None
        return (
            [key.forward for key in items],
            [key.backward for key in items],
        )

    @staticmethod
    def scale_key_data(values, tangents, factor):
        """Apply the same linear conversion to values and optional tangents."""

        values = [value * factor for value in values]
        if tangents is None:
            return values, None
        forward, backward = tangents
        return values, (
            [value * factor for value in forward],
            [value * factor for value in backward],
        )

    @staticmethod
    def get_fcurves_from_action(b_action):
        """
        Return every fcurve in an action.

        Actions have been slotted since Blender 4.4, so their curves live in channelbags
        under a strip in a layer rather than on the action itself.
        """

        return [fcurve
                for layer in b_action.layers
                for strip in layer.strips
                for channelbag in strip.channelbags
                for fcurve in channelbag.fcurves]

    @staticmethod
    def show_pose_markers():
        """Helper function to ensure that pose markers are shown"""
        for screen in bpy.data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == 'DOPESHEET_EDITOR':
                        space.show_pose_markers = True

    @staticmethod
    def get_b_interp_from_n_interp(n_ipol):
        if n_ipol in (NifClasses.KeyType.LINEAR_KEY, NifClasses.KeyType.XYZ_ROTATION_KEY):
            return "LINEAR"
        elif n_ipol == NifClasses.KeyType.QUADRATIC_KEY:
            return "BEZIER"
        elif n_ipol == 0:
            # guessing, not documented in nif.xml
            return "CONSTANT"
        # NifLog.warn(f"Unsupported interpolation mode ({n_ipol}) in nif, using quadratic/bezier.")
        return "BEZIER"

    def create_action(self, b_obj, action_name, sequence_name=None):
        """Create or retrieve an action and slot for this datablock.

        A NIF sequence maps directly to one Blender action. Every datablock controlled
        by it gets its own action slot. Standalone controllers still get an action of
        their own because they have no sequence identity by which to group them.
        """
        global _DEFAULT_SEQUENCE

        if sequence_name and _DEFAULT_SEQUENCE is None:
            _DEFAULT_SEQUENCE = sequence_name

        owner_pointer = b_obj.as_pointer()
        action_key = (("SEQUENCE", sequence_name) if sequence_name
                      else ("DATABLOCK", owner_pointer))
        if action_key in self.actions:
            b_action = self.actions[action_key]
        else:
            b_action = bpy.data.actions.new(sequence_name or action_name)
            b_action.use_fake_user = True
            self.actions[action_key] = b_action

        if sequence_name:
            b_action.nifanimation.sequence_name = sequence_name

        self.action_owners[owner_pointer] = b_obj
        slot_key = (b_action.as_pointer(), owner_pointer)
        if slot_key not in self.action_slots:
            self.action_slots[slot_key] = b_action.slots.new(
                id_type=b_obj.id_type, name=b_obj.name)
        b_slot = self.action_slots[slot_key]

        if not b_obj.animation_data:
            b_obj.animation_data_create()

        # Keep the first controller sequence active through this datablock's slot.
        # Later actions are assigned temporarily while their curves are created, then
        # stashed into muted NLA tracks during finalization.
        if sequence_name == _DEFAULT_SEQUENCE or (
                not sequence_name and b_obj.animation_data.action is None):
            b_obj.animation_data.action = b_action
            b_obj.animation_data.action_slot = b_slot
        return b_action

    def get_sequence_action(self, sequence_name):
        """Return the shared action already created for a named sequence."""

        return self.actions.get(("SEQUENCE", sequence_name))

    @staticmethod
    def _action_range(b_action):
        """Return an action's key range, or None for an empty action."""

        if b_action is None or b_action.is_empty:
            return None
        return tuple(b_action.frame_range)

    def update_active_action_range(self):
        """Set the scene range to encompass the imported actions currently active."""

        # Imported particle systems also contribute a visible range. Their
        # internal cyclic pre-roll deliberately remains outside this range.
        from ....modules.nif_import import particle

        ranges = list(particle.PARTICLE_TIMELINE_RANGES)
        seen_owners = set()
        for b_owner in self.action_owners.values():
            owner_pointer = b_owner.as_pointer()
            if owner_pointer in seen_owners:
                continue
            seen_owners.add(owner_pointer)
            b_anim_data = b_owner.animation_data
            if b_anim_data:
                action_range = self._action_range(b_anim_data.action)
                if action_range is not None:
                    ranges.append(action_range)

        if not ranges:
            return

        bpy.context.scene.frame_start = python_math.floor(
            min(frame_start for frame_start, _ in ranges))
        bpy.context.scene.frame_end = python_math.ceil(
            max(frame_end for _, frame_end in ranges))

    def stash_inactive_sequences(self):
        """Put every non-default sequence action in a muted NLA track."""

        for (action_pointer, owner_pointer), b_slot in self.action_slots.items():
            b_action = next(
                (action for action in self.actions.values()
                 if action.as_pointer() == action_pointer),
                None,
            )
            if b_action is None or b_action.is_empty:
                continue
            sequence_name = b_action.nifanimation.sequence_name
            if not sequence_name or sequence_name == _DEFAULT_SEQUENCE:
                continue

            b_owner = self.action_owners.get(owner_pointer)
            if b_owner is None:
                continue
            if not b_owner.animation_data:
                b_owner.animation_data_create()
            b_anim_data = b_owner.animation_data

            # Finalization can safely be called more than once without adding another
            # strip for the same action.
            if any(strip.action == b_action and strip.action_slot == b_slot
                   for track in b_anim_data.nla_tracks for strip in track.strips):
                continue

            frame_start, frame_end = b_action.frame_range
            b_track = b_anim_data.nla_tracks.new()
            b_track.name = sequence_name
            b_strip = b_track.strips.new(
                b_action.name, python_math.floor(frame_start), b_action)
            b_strip.action_slot = b_slot
            b_strip.action_frame_start = frame_start
            b_strip.action_frame_end = frame_end
            b_track.mute = True

    def finalize(self):
        """Finish sequence storage and choose the default preview range."""

        self.stash_inactive_sequences()
        self.update_active_action_range()

    def create_fcurves(self, obj, action, dtype, drange, flags, bone_name, key_name):
        """ Create fcurves in action for desired conditions. """
        slot_key = (action.as_pointer(), obj.as_pointer())
        action_slot = self.action_slots.get(slot_key)
        if action_slot is None:
            raise RuntimeError(
                f"Action '{action.name}' has no slot for '{obj.name}'")

        # armature pose bone animation
        if bone_name:
            data_path = f'pose.bones["{bone_name}"].{dtype}'
            action_group = bone_name
        elif key_name:
            data_path = f'key_blocks["{key_name}"].{dtype}'
            action_group = ""
        else:
            # Object animation (non-skeletal) is lumped into the "LocRotScale" action_group
            if dtype in (QUAT, EULER, LOC, SCALE):
                action_group = "LocRotScale"
            # Non-transformaing animations (eg. visibility or material anims) use no action groups
            else:
                action_group = ""
            data_path = dtype

        # Blender 4.4+ stores all of these in slotted action channelbags. Keep the API
        # interaction here so every controller type follows the same creation path.
        # Blender's convenience API requires the action to be assigned while it creates
        # curves. Preserve the user's/default active action while filling another
        # sequence's slot.
        b_anim_data = obj.animation_data
        previous_action = b_anim_data.action
        previous_slot = b_anim_data.action_slot
        try:
            b_anim_data.action = action
            b_anim_data.action_slot = action_slot
            fcurves = [
                action.fcurve_ensure_for_datablock(
                    datablock=obj,
                    data_path=data_path,
                    index=index,
                    group_name=action_group,
                )
                for index in drange
            ]
        finally:
            b_anim_data.action = previous_action
            if previous_action is not None and previous_slot is not None:
                b_anim_data.action_slot = previous_slot

        if flags:
            self.set_extrapolation(self.get_extend_from_flags(flags), fcurves)
        return fcurves

    @staticmethod
    def get_extend_from_flags(flags):
        if flags & 6 == 4:  # 0b100
            return "CONSTANT"
        elif flags & 6 == 0:  # 0b000
            return "CYCLIC"

        NifLog.warn("Unsupported cycle mode in nif, using clamped.")
        return "CONSTANT"

    @staticmethod
    def get_extend_from_cycle_type(cycle_type):
        return ("CYCLIC", "REVERSE", "CONSTANT")[cycle_type]

    @staticmethod
    def set_extrapolation(extend_type, fcurves):
        if extend_type == "CONSTANT":
            for fcurve in fcurves:
                fcurve.extrapolation = 'CONSTANT'
        elif extend_type == "CYCLIC":
            for fcurve in fcurves:
                if not any(modifier.type == 'CYCLES' for modifier in fcurve.modifiers):
                    fcurve.modifiers.new('CYCLES')
        # don't support reverse for now, not sure if it is even possible in blender
        else:
            NifLog.warn("Unsupported extrapolation mode, using clamped.")
            for fcurve in fcurves:
                fcurve.extrapolation = 'CONSTANT'

    def add_keys(self, b_obj, b_action, key_type, key_range, flags, times, keys,
                 interp, bone_name=None, key_name=None, tangents=None):
        """
        Create needed fcurves and add a list of keys to an action.

        ``tangents`` is a pair of forward/backward value arrays from quadratic
        NIF keys. They are converted to explicit Bézier handles so Blender
        evaluates the same Hermite spline as NifSkope instead of inventing
        auto-clamped endpoint easing.
        """
        samples = [round(t * self.fps) for t in times]
        assert len(samples) == len(keys)
        # import the keys
        try:
            fcurves = self.create_fcurves(b_obj, b_action, key_type, key_range, flags, bone_name, key_name)
            if len(key_range) == 1:
                # flat key - make it zippable
                key_per_fcurve = [keys]
                tangent_per_fcurve = [tangents] if tangents else [None]
            else:
                key_per_fcurve = zip(*keys)
                if tangents:
                    forward, backward = tangents
                    tangent_per_fcurve = zip(zip(*forward), zip(*backward))
                else:
                    tangent_per_fcurve = [None] * len(fcurves)
            for fcurve, fcu_keys, fcu_tangents in zip(
                    fcurves, key_per_fcurve, tangent_per_fcurve):
                fcu_keys = list(fcu_keys)
                points_by_frame = {point.co[0]: point for point in fcurve.keyframe_points}
                new_keys = []
                for sample, value in zip(samples, fcu_keys):
                    point = points_by_frame.get(sample)
                    if point is None:
                        new_keys.append((sample, value))
                    else:
                        # A reused action may legitimately encounter the same channel again.
                        # Replace that frame instead of appending a duplicate key.
                        point.co = (sample, value)
                        point.interpolation = interp

                first_new_index = len(fcurve.keyframe_points)
                fcurve.keyframe_points.add(count=len(new_keys))
                for index, (sample, value) in enumerate(new_keys, first_new_index):
                    point = fcurve.keyframe_points[index]
                    point.co = (sample, value)
                    point.interpolation = interp
                # update
                fcurve.update()
                if fcu_tangents:
                    forward, backward = (list(values) for values in fcu_tangents)
                    points_by_frame = {
                        point.co[0]: point for point in fcurve.keyframe_points}
                    for key_index, (sample, value) in enumerate(zip(samples, fcu_keys)):
                        point = points_by_frame[sample]
                        point.handle_left_type = "FREE"
                        point.handle_right_type = "FREE"

                        previous_sample = (
                            samples[key_index - 1] if key_index else sample)
                        next_sample = (
                            samples[key_index + 1]
                            if key_index + 1 < len(samples) else sample)

                        # NifSkope's quadratic evaluator uses:
                        #   current.backward as the outgoing Hermite tangent
                        #   next.forward as the incoming Hermite tangent.
                        # Hermite-to-Bézier conversion divides both by three.
                        point.handle_left = (
                            sample - (sample - previous_sample) / 3,
                            value - forward[key_index] / 3,
                        )
                        point.handle_right = (
                            sample + (next_sample - sample) / 3,
                            value + backward[key_index] / 3,
                        )
                    fcurve.update()
                # Update max_key_time
                self.max_key_time = max(self.max_key_time, max(times))
        except RuntimeError as error:
            NifLog.warn(f"Could not add fcurve '{key_type}' to '{b_action.name}': {error}")

    # import animation groups
    def import_text_keys(self, n_block, b_action):
        """Gets and imports a NiTextKeyExtraData"""
        if isinstance(n_block, NifClasses.NiControllerSequence):
            txk = n_block.text_keys
        else:
            txk = n_block.find(block_type=NifClasses.NiTextKeyExtraData)
        self.import_text_key_extra_data(txk, b_action)

    def import_text_key_extra_data(self, txk, b_action):
        """Stores the text keys as pose markers in a blender action."""
        if txk and b_action:
            for key in txk.text_keys:
                newkey = key.value.replace('\r\n', '/').rstrip('/')
                frame = round(key.time * self.fps)
                marker = b_action.pose_markers.new(newkey)
                marker.frame = frame

    def set_frames_per_second(self, roots):
        """Scan all blocks and set a reasonable number for fps to this class and the scene."""
        # find all key times
        key_times = []
        for root in roots:
            for kfd in root.tree(block_type=NifClasses.NiKeyframeData):
                key_times.extend(key.time for key in kfd.translations.keys)
                key_times.extend(key.time for key in kfd.scales.keys)
                key_times.extend(key.time for key in kfd.quaternion_keys)
                for dimension in kfd.xyz_rotations:
                    key_times.extend(key.time for key in dimension.keys)

            for kfi in root.tree(block_type=NifClasses.NiBSplineInterpolator):
                if not kfi.basis_data:
                    # skip bsplines without basis data (eg bowidle.kf in Oblivion)
                    continue
                key_times.extend(
                    point * (kfi.stop_time - kfi.start_time)
                    / (kfi.basis_data.num_control_points - 2)
                    for point in range(kfi.basis_data.num_control_points - 2))

            for uv_data in root.tree(block_type=NifClasses.NiUVData):
                for uv_group in uv_data.uv_groups:
                    key_times.extend(key.time for key in uv_group.keys)

        # not animated, return a reasonable default
        if not key_times:
            return

        # calculate fps
        key_times = sorted(set(key_times))
        fps = self.fps
        lowest_diff = sum(abs(int(time * fps + 0.5) - (time * fps)) for time in key_times)

        # for test_fps in range(1,120): #disabled, used for testing
        for test_fps in [20, 24, 25, 30, 35]:
            diff = sum(abs(int(time * test_fps + 0.5) - (time * test_fps)) for time in key_times)
            if diff < lowest_diff:
                lowest_diff = diff
                fps = test_fps
        NifLog.info(f"Animation estimated at {fps} frames per second.")
        self.fps = fps
        bpy.context.scene.render.fps = fps
        bpy.context.scene.frame_set(0)

    def set_max_key_time(self):
        # Preview only the first/default sequence, not the longest action in any sequence.
        self.update_active_action_range()
        NifLog.info(
            f"Active animation range set to {bpy.context.scene.frame_start}-"
            f"{bpy.context.scene.frame_end} frames.")
