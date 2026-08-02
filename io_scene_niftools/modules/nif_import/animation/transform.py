"""This script contains classes to help import NIF controllers as blender bone or object level transform(ation) animations."""

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

from bisect import bisect_left
from functools import singledispatch

import bpy
import mathutils
from ....modules.nif_import.animation import Animation
from ....modules.nif_import.object import block_registry
from ....utils import math
from ....utils.consts import QUAT, EULER, LOC, SCALE
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


def as_b_quat(n_val):
    return mathutils.Quaternion([n_val.w, n_val.x, n_val.y, n_val.z])


def as_b_loc(n_val):
    return mathutils.Vector([n_val.x, n_val.y, n_val.z])


def as_b_scale(n_val):
    return n_val, n_val, n_val


def as_b_euler(n_val):
    return mathutils.Euler(n_val)


def correct_loc(key, n_bind_rot_inv, n_bind_trans):
    return math.import_keymat(n_bind_rot_inv, mathutils.Matrix.Translation(key - n_bind_trans)).to_translation()


def correct_loc_tangent(key, n_bind_rot_inv, n_bind_trans):
    """Rotate a translation tangent without applying the bind translation."""

    return math.import_keymat(
        n_bind_rot_inv,
        mathutils.Matrix.Translation(key),
    ).to_translation()


def correct_quat(key, n_bind_rot_inv, n_bind_trans):
    return math.import_keymat(n_bind_rot_inv, key.to_matrix().to_4x4()).to_quaternion()


def correct_euler(key, n_bind_rot_inv, n_bind_trans):
    return math.import_keymat(n_bind_rot_inv, key.to_matrix().to_4x4()).to_euler()


def correct_scale(key, n_bind_rot_inv, n_bind_trans):
    return key


key_lut = {
    QUAT: (as_b_quat, correct_quat, None, 4),
    EULER: (as_b_euler, correct_euler, None, 3),
    LOC: (as_b_loc, correct_loc, correct_loc_tangent, 3),
    SCALE: (as_b_scale, correct_scale, correct_scale, 3),
}


def interpolate(x_out, x_in, y_in):
    """
    sample (x_in I y_in) at x coordinates x_out
    """
    y_out = []
    intervals = zip(x_in, x_in[1:], y_in, y_in[1:])
    slopes = [(y2 - y1) / (x2 - x1) for x1, x2, y1, y2 in intervals]
    # if we had just one input, slope will be 0 for constant extrapolation
    if not slopes:
        slopes = [0, ]
    for x in x_out:
        i = bisect_left(x_in, x) - 1
        # clamp to valid range
        i = max(min(i, len(slopes) - 1), 0)
        y_out.append(y_in[i] + slopes[i] * (x - x_in[i]))
    return y_out


class TransformAnimation(Animation):

    def __init__(self):
        super().__init__()
        from ....modules.nif_import.animation.material import MaterialAnimation
        from ....modules.nif_import.animation.object import ObjectAnimation
        from ....modules.nif_import.animation.particle import ParticleAnimation
        self.material_anim = MaterialAnimation()
        self.object_anim = ObjectAnimation()
        self.particle_anim = ParticleAnimation()
        self.import_kf_root = singledispatch(self.import_kf_root)
        self.import_kf_root.register(NifClasses.NiControllerSequence, self.import_controller_sequence)
        self.import_kf_root.register(NifClasses.NiSequenceStreamHelper, self.import_sequence_stream_helper)
        self.import_kf_root.register(NifClasses.NiSequenceData, self.import_sequence_data)

    def get_bind_data(self, b_armature):
        """Get the required bind data of an armature. Used by standalone KF import and export. """
        self.bind_data = {}
        if b_armature:
            for b_bone in b_armature.data.bones:
                n_bind_scale, n_bind_rot, n_bind_trans = math.decompose_srt(math.get_object_bind(b_bone))
                self.bind_data[b_bone.name] = (n_bind_rot.inverted(), n_bind_trans)

    def get_target(self, b_armature_obj, n_name):
        """Gets a target for an anim controller"""
        b_name = block_registry.get_bone_name_for_blender(n_name)
        # if we have an armature, get the pose bone
        if b_armature_obj and b_name in b_armature_obj.pose.bones:
            return b_armature_obj.pose.bones[b_name]
        # a sequence of a skinned nif also drives plain objects, such as its meshes,
        # so fall back to the objects even when there is an armature
        if b_name in bpy.data.objects:
            return bpy.data.objects[b_name]
        # objects only carry their nif name separately when Blender had to rename them
        return next((b_obj for b_obj in bpy.data.objects
                     if getattr(b_obj.nif_object, "longname", "") == b_name), None)

    def import_kf_root(self, kf_root, b_armature_obj):
        """Base method to warn user that this root type is not supported"""
        NifLog.warn(f"Unknown KF root block found : {kf_root.name}")
        NifLog.warn(f"This type isn't currently supported: {type(kf_root)}")

    def import_generic_kf_root(self, kf_root):
        NifLog.debug(f'Importing {type(kf_root)}...')
        return kf_root.name

    def import_sequence_data(self, kf_root, b_armature_obj):
        b_action_name = self.import_generic_kf_root(kf_root)
        actions = set()
        for evaluator in kf_root.evaluators:
            b_target = self.get_target(b_armature_obj, evaluator.node_name)
            actions.add(self.import_keyframe_controller(
                evaluator, b_armature_obj, b_target, b_action_name,
                sequence_name=b_action_name))
        for b_action in actions:
            if b_action:
                self.import_text_keys(kf_root, b_action)
                if kf_root.cycle_type:
                    extend = self.get_extend_from_cycle_type(kf_root.cycle_type)
                    self.set_extrapolation(extend, self.get_fcurves_from_action(b_action))

    def import_sequence_stream_helper(self, kf_root, b_armature_obj):
        b_action_name = self.import_generic_kf_root(kf_root)
        actions = set()
        # import parallel trees of extra datas and keyframe controllers
        extra = kf_root.extra_data
        controller = kf_root.controller
        textkeys = None
        while extra and controller:
            # textkeys in the stack do not specify node names, import as markers
            while isinstance(extra, NifClasses.NiTextKeyExtraData):
                textkeys = extra
                extra = extra.next_extra_data

            # grabe the node name from string data
            if isinstance(extra, NifClasses.NiStringExtraData):
                b_target = self.get_target(b_armature_obj, extra.string_data)
                actions.add(self.import_keyframe_controller(
                    controller, b_armature_obj, b_target, b_action_name,
                    sequence_name=b_action_name))
            # grab next pair of extra and controller
            extra = extra.next_extra_data
            controller = controller.next_controller
        for b_action in actions:
            if b_action:
                self.import_text_key_extra_data(textkeys, b_action)

    def import_controller_sequence(self, kf_root, b_armature_obj):
        b_action_name = self.import_generic_kf_root(kf_root)
        actions = set()
        for controlledblock in kf_root.controlled_blocks:
            if self.particle_anim.import_sequence_controlled_block(controlledblock, kf_root):
                continue
            # material and texture animation is driven from the sequence too, as the
            # controllers on the targets only hold blend interpolators
            if self.material_anim.import_sequence_controlled_block(controlledblock, str(kf_root.name or "")):
                continue

            # get bone name
            # todo [pyffi] fixed get_node_name() is up, make release and clean up here
            # ZT2 - old way is not supported by pyffi's get_node_name()
            n_name = controlledblock.target_name
            # fallout (node_name) & Loki (StringPalette)
            if not n_name:
                n_name = controlledblock.get_node_name()
            b_target = self.get_target(b_armature_obj, n_name)
            if self.object_anim.import_sequence_controlled_block(
                    controlledblock, str(kf_root.name or ""), b_target, n_name):
                continue
            # todo - temporarily disabled! should become a custom property on both object and pose bone, ideally
            # import bone priority
            # b_target.niftools.priority = controlledblock.priority
            # fallout, Loki
            kfc = controlledblock.interpolator
            if not kfc:
                # ZT2
                kfc = controlledblock.controller
            if kfc:
                actions.add(self.import_keyframe_controller(
                    kfc, b_armature_obj, b_target, b_action_name,
                    sequence_name=b_action_name))
        # Material, texture, and visibility helpers create their slots through the same
        # shared sequence registry but return only a handled/not-handled flag above.
        # Recover the shared action so its text keys and cycle mode are imported too.
        actions.add(self.get_sequence_action(b_action_name))
        for b_action in actions:
            if b_action:
                self.import_text_keys(kf_root, b_action)
                # fallout: set global extrapolation mode here (older versions have extrapolation per controller)
                if kf_root.cycle_type:
                    extend = self.get_extend_from_cycle_type(kf_root.cycle_type)
                    self.set_extrapolation(extend, self.get_fcurves_from_action(b_action))

    def import_keyframe_controller(self, n_kfc, b_armature, b_target,
                                   b_action_name, sequence_name=None):
        """
        Imports a keyframe controller as fcurves in an action, which is created if necessary.
        n_kfc: some nif struct that has keyframe data, somewhere
        b_armature: either None or Object (blender armature)
        b_target: either Object or PoseBone
        b_action_name: display name used for a standalone action
        sequence_name: NIF sequence identity when this controller is one slot of
            a shared sequence action; None for an attached standalone controller
        """
        # the target may not exist in the scene, in which case it is None here
        if not b_target:
            return
        NifLog.debug(f'Importing keyframe controller for {b_target.name}')

        n_kfd = None
        # fallout, Loki - we set extrapolation according to the root NiControllerSequence.cycle_type
        flags = None
        n_bind_rot_inv = n_bind_trans = None

        # create or get the action
        if b_armature and isinstance(b_target, bpy.types.PoseBone):
            # action on armature, one per armature
            b_action = self.create_action(
                b_armature, b_action_name, sequence_name=sequence_name)
            if b_target.name in self.bind_data:
                n_bind_rot_inv, n_bind_trans = self.bind_data[b_target.name]
            bone_name = b_target.name
        else:
            action_name = (
                f"{b_action_name}_{b_target.name}"
                if sequence_name else b_action_name
            )
            b_action = self.create_action(
                b_target, action_name, sequence_name=sequence_name)
            bone_name = None

        b_anim_owner = b_armature if bone_name else b_target

        # A path interpolator drives translation from one curve and time/percentage
        # from another. It is not exposed through ``get_controller_data`` because
        # it has no generic ``data`` field.
        n_path = (
            n_kfc.interpolator
            if (hasattr(n_kfc, "interpolator")
                and isinstance(n_kfc.interpolator, NifClasses.NiPathInterpolator))
            else n_kfc
        )
        if isinstance(n_path, (NifClasses.NiPathInterpolator,
                               NifClasses.NiPathController)):
            self.import_path_translation(
                n_path, n_kfc, b_anim_owner, b_action, bone_name,
                n_bind_rot_inv, n_bind_trans)
            return b_action

        # B-spline curve import
        if isinstance(n_kfc, NifClasses.NiBSplineInterpolator):
            # Bsplines are Bezier curves
            interp = "BEZIER"
            if isinstance(n_kfc, NifClasses.NiBSplineCompFloatInterpolator):
                # used by WLP2 (tiger.kf), but only for non-LocRotScale data
                # eg. bone stretching - see controlledblock.get_variable_1()
                # do not support this for now, no good representation in Blender
                # pyffi lacks support for this, but the following gets float keys
                # keys = list(kfc._getCompKeys(kfc.offset, 1, kfc.bias, kfc.multiplier))
                return
            times = list(n_kfc.get_times())
            keys = [NifClasses.Vector3.from_value(tuple_key) for tuple_key in n_kfc.get_translations()]
            self.import_keys(LOC, b_anim_owner, b_action, bone_name, times, keys, flags, interp, n_bind_rot_inv, n_bind_trans)
            keys = [NifClasses.Quaternion.from_value(tuple_key) for tuple_key in n_kfc.get_rotations()]
            self.import_keys(QUAT, b_anim_owner, b_action, bone_name, times, keys, flags, interp, n_bind_rot_inv, n_bind_trans)
            keys = list(n_kfc.get_scales())
            self.import_keys(SCALE, b_anim_owner, b_action, bone_name, times, keys, flags, interp, n_bind_rot_inv, n_bind_trans)
            return b_action
        elif isinstance(n_kfc, NifClasses.NiMultiTargetTransformController):
            # not sure what this is used for
            return
        n_kfd = self.get_controller_data(n_kfc)
        if n_kfd is None:
            # a blend interpolator, whose animation comes from the controller sequences
            return
        # ZT2 - get extrapolation for every kfc
        if isinstance(n_kfc, NifClasses.NiKeyframeController):
            flags = n_kfc.flags
        if isinstance(n_kfd, NifClasses.NiKeyframeData):
            if n_kfd.rotation_type == 4:
                b_target.rotation_mode = "XYZ"
                # euler keys need not be sampled at the same time in KFs
                # but we need complete key sets to do the space conversion
                # so perform linear interpolation to import all keys properly

                # get all the times and keys for each coordinate
                times_keys = [self.get_keys_values(euler.keys) for euler in n_kfd.xyz_rotations]
                # the unique time stamps we have to sample all curves at
                times_all = sorted(set(times_keys[0][0] + times_keys[1][0] + times_keys[2][0]))
                # todo - this assumes that all three channels are keyframed, but it seems like this need not be the case
                # resample each coordinate for all times
                keys_res = [interpolate(times_all, times, keys) for times, keys in times_keys]
                # for eulers, the actual interpolation type is apparently stored per channel
                n_interpolation = n_kfd.xyz_rotations[0].interpolation
                interp = self.get_b_interp_from_n_interp(n_interpolation)
                tangents = None
                same_key_times = all(
                    channel_times == times_keys[0][0]
                    for channel_times, _ in times_keys[1:])
                if (same_key_times
                        and all(group.interpolation == NifClasses.KeyType.QUADRATIC_KEY
                                for group in n_kfd.xyz_rotations)):
                    axis_tangents = [
                        self.get_nif_tangents(
                            group.keys, group.interpolation)
                        for group in n_kfd.xyz_rotations
                    ]
                    tangents = (
                        list(zip(*(pair[0] for pair in axis_tangents))),
                        list(zip(*(pair[1] for pair in axis_tangents))),
                    )
                elif n_interpolation == NifClasses.KeyType.QUADRATIC_KEY:
                    # Differently timed Euler channels must be resampled for the
                    # space conversion, so their original Hermite tangents no longer
                    # line up. Linear interpolation avoids fabricating endpoint ease.
                    interp = "LINEAR"
                self.import_keys(
                    EULER, b_anim_owner, b_action, bone_name,
                    times_all, zip(*keys_res), flags, interp, n_bind_rot_inv,
                    n_bind_trans, tangents)
            else:
                b_target.rotation_mode = "QUATERNION"
                times, keys = self.get_keys_values(n_kfd.quaternion_keys)
                # Quaternion keys never store quadratic tangents. NifSkope uses
                # spherical interpolation regardless of the numeric rotation key
                # type. Linear component curves are Blender's closest native
                # representation and avoid invented Bézier endpoint easing.
                interp = "LINEAR"
                self.import_keys(QUAT, b_anim_owner, b_action, bone_name, times, keys, flags, interp, n_bind_rot_inv, n_bind_trans)
            times, keys = self.get_keys_values(n_kfd.scales.keys)
            interp = self.get_b_interp_from_n_interp(n_kfd.scales.interpolation)
            tangents = self.get_nif_tangents(
                n_kfd.scales.keys, n_kfd.scales.interpolation)
            self.import_keys(
                SCALE, b_anim_owner, b_action, bone_name, times,
                keys, flags, interp, n_bind_rot_inv, n_bind_trans, tangents)

            times, keys = self.get_keys_values(n_kfd.translations.keys)
            interp = self.get_b_interp_from_n_interp(n_kfd.translations.interpolation)
            tangents = self.get_nif_tangents(
                n_kfd.translations.keys, n_kfd.translations.interpolation)
            self.import_keys(
                LOC, b_anim_owner, b_action, bone_name, times,
                keys, flags, interp, n_bind_rot_inv, n_bind_trans, tangents)

        return b_action

    @staticmethod
    def _inverse_linear_percent(percent_keys, value):
        """Return the controller time at which a monotonic linear percent curve
        reaches ``value``."""

        if len(percent_keys) == 1:
            return float(percent_keys[0].time)
        for left, right in zip(percent_keys, percent_keys[1:]):
            left_value = float(left.value)
            right_value = float(right.value)
            if min(left_value, right_value) <= value <= max(left_value, right_value):
                if right_value == left_value:
                    return float(left.time)
                factor = (value - left_value) / (right_value - left_value)
                return float(left.time) + factor * (
                    float(right.time) - float(left.time))
        return float(min(
            percent_keys, key=lambda key: abs(float(key.value) - value)).time)

    @staticmethod
    def _evaluate_key_group(group, time):
        """Evaluate the linear/quadratic key groups used by path interpolators."""

        keys = list(group.keys)
        if not keys:
            return None
        if len(keys) == 1 or time <= float(keys[0].time):
            return keys[0].value
        if time >= float(keys[-1].time):
            return keys[-1].value

        for left, right in zip(keys, keys[1:]):
            left_time = float(left.time)
            right_time = float(right.time)
            if time > right_time:
                continue
            factor = (time - left_time) / (right_time - left_time)
            left_value = left.value
            right_value = right.value
            if hasattr(left_value, "x"):
                left_value = mathutils.Vector(
                    (left_value.x, left_value.y, left_value.z))
                right_value = mathutils.Vector(
                    (right_value.x, right_value.y, right_value.z))

            if group.interpolation == NifClasses.KeyType.QUADRATIC_KEY:
                outgoing = left.backward
                incoming = right.forward
                if hasattr(outgoing, "x"):
                    outgoing = mathutils.Vector(
                        (outgoing.x, outgoing.y, outgoing.z))
                    incoming = mathutils.Vector(
                        (incoming.x, incoming.y, incoming.z))
                factor_2 = factor * factor
                factor_3 = factor_2 * factor
                return (
                    (2 * factor_3 - 3 * factor_2 + 1) * left_value
                    + (factor_3 - 2 * factor_2 + factor) * outgoing
                    + (-2 * factor_3 + 3 * factor_2) * right_value
                    + (factor_3 - factor_2) * incoming
                )
            return left_value + (right_value - left_value) * factor
        return keys[-1].value

    def import_path_translation(self, n_path, n_controller, b_obj, b_action,
                                bone_name, n_bind_rot_inv, n_bind_trans):
        """Import a NiPathInterpolator/NiPathController as object translation.

        A monotonic linear percentage curve can be inverted at the original path
        keys, preserving the NIF Hermite handles exactly. More complex percentage
        curves are composed with the path at the scene frame rate.
        """

        n_path_data = getattr(n_path, "path_data", None)
        n_percent_data = getattr(n_path, "percent_data", None)
        path_group = getattr(n_path_data, "data", None)
        percent_group = getattr(n_percent_data, "data", None)
        path_keys = list(getattr(path_group, "keys", ()) or ())
        percent_keys = list(getattr(percent_group, "keys", ()) or ())
        if not path_keys or not percent_keys:
            NifLog.warn(
                f"Path controller for '{b_obj.name}' has no path or percentage keys.")
            return

        percent_values = [float(key.value) for key in percent_keys]
        increasing = all(
            right >= left
            for left, right in zip(percent_values, percent_values[1:]))
        decreasing = all(
            right <= left
            for left, right in zip(percent_values, percent_values[1:]))
        can_preserve_keys = (
            percent_group.interpolation == NifClasses.KeyType.LINEAR_KEY
            and (increasing or decreasing)
            and path_group.interpolation in (
                NifClasses.KeyType.LINEAR_KEY,
                NifClasses.KeyType.QUADRATIC_KEY)
        )
        flags = getattr(n_controller, "flags", None)
        # The generic NIF scale spell scales NiTransformData translations but
        # does not visit NiPathInterpolator.path_data. Apply the same scene
        # correction here so path-driven objects stay in the imported scene.
        scale_correction = bpy.context.scene.niftools_scene.scale_correction

        def scaled_vector(value):
            return NifClasses.Vector3.from_value((
                float(value.x) * scale_correction,
                float(value.y) * scale_correction,
                float(value.z) * scale_correction,
            ))

        if can_preserve_keys:
            times = [
                self._inverse_linear_percent(percent_keys, float(key.time))
                for key in path_keys
            ]
            # A flat/repeated percentage segment cannot represent distinct path
            # keys at distinct Blender frames, so use composed samples instead.
            if len({round(time * self.fps) for time in times}) == len(times):
                values = [scaled_vector(key.value) for key in path_keys]
                interpolation = self.get_b_interp_from_n_interp(
                    path_group.interpolation)
                tangents = self.get_nif_tangents(
                    path_keys, path_group.interpolation)
                if tangents:
                    tangents = tuple(
                        [scaled_vector(value) for value in values]
                        for values in tangents
                    )
                self.import_keys(
                    LOC, b_obj, b_action, bone_name, times, values, flags,
                    interpolation, n_bind_rot_inv, n_bind_trans, tangents)
                return

        start_time = float(percent_keys[0].time)
        stop_time = float(percent_keys[-1].time)
        controller_start = float(getattr(n_controller, "start_time", start_time))
        controller_stop = float(getattr(n_controller, "stop_time", stop_time))
        start_time = max(start_time, controller_start)
        stop_time = min(stop_time, controller_stop)
        sample_count = max(1, round((stop_time - start_time) * self.fps))
        times = [
            start_time + (stop_time - start_time) * index / sample_count
            for index in range(sample_count + 1)
        ]
        values = []
        for time in times:
            percent = self._evaluate_key_group(percent_group, time)
            value = self._evaluate_key_group(path_group, float(percent))
            if isinstance(value, mathutils.Vector):
                value = NifClasses.Vector3.from_value(tuple(value))
            value = scaled_vector(value)
            values.append(value)
        self.import_keys(
            LOC, b_obj, b_action, bone_name, times, values, flags, "LINEAR",
            n_bind_rot_inv, n_bind_trans)

    def import_keys(self, key_type, b_obj, b_action, bone_name, times, keys,
                    flags, interp, n_bind_rot_inv, n_bind_trans, tangents=None):
        """Imports key frames according to the specified key_type"""
        if not keys:
            return
        # look up conventions by key type
        key_func, key_corrector, tangent_corrector, key_dim = key_lut[key_type]
        NifLog.debug(f'{key_type} keys...')
        # convert nif keys to proper key type for blender
        keys = [key_func(val) for val in keys]
        if tangents:
            forward, backward = tangents
            tangents = (
                [key_func(value) for value in forward],
                [key_func(value) for value in backward],
            )
        # correct for bone space if target is an armature bone
        if bone_name:
            keys = [key_corrector(key, n_bind_rot_inv, n_bind_trans) for key in keys]
            if tangents and tangent_corrector:
                forward, backward = tangents
                tangents = (
                    [tangent_corrector(
                        value, n_bind_rot_inv, n_bind_trans)
                     for value in forward],
                    [tangent_corrector(
                        value, n_bind_rot_inv, n_bind_trans)
                     for value in backward],
                )
            elif tangents:
                tangents = None
                interp = "LINEAR"
        self.add_keys(
            b_obj, b_action, key_type, range(key_dim), flags, times, keys,
            interp, bone_name=bone_name, tangents=tangents)
        self.set_max_key_time()

    def import_transforms(self, n_block, b_obj, bone_name=None):
        """Loads an animation attached to a nif block."""
        # find keyframe controller
        n_kfc = math.find_controller(n_block, (NifClasses.NiKeyframeController, NifClasses.NiTransformController))
        if n_kfc:
            # skeletal animation
            if bone_name:
                p_bone = b_obj.pose.bones[bone_name]
                self.import_keyframe_controller(n_kfc, b_obj, p_bone, f"{b_obj.name}_Anim")
            # object-level animation
            else:
                self.import_keyframe_controller(n_kfc, None, b_obj, f"{b_obj.name}_Anim")

    def import_controller_manager(self, n_block, b_obj, b_armature):
        ctrlm = n_block.controller
        if ctrlm and isinstance(ctrlm, NifClasses.NiControllerManager):
            NifLog.debug(f'Importing NiControllerManager')
            if b_armature:
                self.get_bind_data(b_armature)
            for ctrl in ctrlm.controller_sequences:
                self.import_kf_root(ctrl, b_armature)
