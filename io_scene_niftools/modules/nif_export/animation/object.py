"""Main module for exporting object animation blocks."""

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

from ....modules.nif_export.animation import common as Common

from ....modules.nif_export.animation.common import V_INTERPOLATORS, attach_controller, get_n_target
from ....modules.nif_export.block_registry import block_store
from ....utils import math, consts
from ....utils.consts import QUAT, EULER, LOC, SCALE
from ....utils.logging import NifError, NifLog
from ....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses

# The visibility channel of a bone, on its armature rather than on the armature object
BONE_HIDE_PATH = re.compile(r'^bones\["(.+)"\]\.hide$')


class ObjectAnimation(Common.AnimationCommon):

    def __init__(self):
        super().__init__()

        self.niftools_scene = bpy.context.scene.niftools_scene

    def export_object_animations(self, b_controlled_blocks, n_ni_controller_sequence=None):
        for b_strip, b_obj in b_controlled_blocks:
            b_action = b_strip.action
            b_action_slot = b_strip.action_slot

            if not b_action_slot:
                continue

            if b_action_slot.target_id_type == 'ARMATURE':
                # the visibility of a bone is animated on the armature it belongs to
                self.export_ni_bone_vis_controllers(
                    b_obj, b_action, n_ni_controller_sequence, b_action_slot)
                continue

            if b_action_slot.target_id_type != 'OBJECT':
                continue

            if b_obj.type == 'MESH' and b_obj.parent_type == 'ARMATURE':
                # a skinned mesh is moved by its bones and has no transform of its own
                continue

            self.export_ni_object_controllers(
                b_obj, b_action, n_ni_controller_sequence, b_action_slot)

    def export_ni_bone_vis_controllers(self, b_obj, b_action, n_ni_controller_sequence=None,
                                       b_action_slot=None):
        """Export a visibility controller for every bone whose visibility is animated."""

        if b_obj.type != 'ARMATURE':
            return

        action_fcurves = self.get_fcurves_from_action(b_action, b_action_slot)

        for b_fcurve in action_fcurves:
            match = BONE_HIDE_PATH.match(b_fcurve.data_path)
            if not match:
                continue

            b_bone = b_obj.data.bones.get(match.group(1))
            if b_bone is None:
                continue

            hide_curve = [(point.co[0], point.co[1]) for point in b_fcurve.keyframe_points]
            if not hide_curve:
                continue

            n_node, n_node_name = get_n_target(b_bone)
            self.export_ni_vis_controller(hide_curve, b_action, action_fcurves,
                                          n_node, n_node_name, n_ni_controller_sequence)

    def export_ni_vis_controller(self, hide_curves, b_action, action_fcurves, n_node, n_node_name,
                                 n_ni_controller_sequence=None):
        """Export the visibility controller data."""

        n_bool_data = block_store.create_block("NiBoolData")

        n_bool_data.data.interpolation = NifClasses.KeyType.CONST_KEY
        n_bool_data.data.num_keys = len(hide_curves)
        n_bool_data.data.reset_field("keys")

        for key, (frame, b_hidden) in zip(n_bool_data.data.keys, hide_curves):
            key.time = frame / self.fps
            # blender hides an object, a nif shows it
            key.value = not b_hidden

        n_vis_ctrl = block_store.create_block("NiVisController")
        n_vis_ipol = block_store.create_block("NiBoolInterpolator")

        n_vis_ipol.data = n_bool_data
        n_vis_ctrl.interpolator = n_vis_ipol

        self.set_flags_and_timing(n_vis_ctrl, action_fcurves, *b_action.frame_range)

        attach_controller(n_vis_ctrl, n_vis_ipol, n_node_name, "NiVisController",
                          n_ctrl_target=n_node, n_sequence=n_ni_controller_sequence)

    def export_ni_object_controllers(self, b_obj, b_action, n_ni_controller_sequence=None,
                                     b_action_slot=None):
        action_fcurves = self.get_fcurves_from_action(b_action, b_action_slot)

        n_obj, n_obj_name = get_n_target(b_obj)

        if b_obj.type == 'ARMATURE':
            for b_bone in b_obj.data.bones:
                n_node, n_node_name = get_n_target(b_bone)

                quaternion_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith(f"{b_bone.name}\"].rotation_quaternion")]
                translation_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith(f"{b_bone.name}\"].location")]
                euler_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith(f"{b_bone.name}\"].rotation_euler")]
                scale_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith(f"{b_bone.name}\"].scale")]

                # ensure that those groups that are present have all their fcurves
                for fcus, num_fcus in ((quaternion_data, 4), (euler_data, 3), (translation_data, 3), (scale_data, 3)):
                    if fcus and len(fcus) != num_fcus:
                        NifLog.warn(f"{fcus, len(fcus), num_fcus}")
                        raise NifError(
                            f"Incomplete {b_bone.name} key set for action {b_action.name}.\nEnsure that if a bone is keyframed for a property, all channels are keyframed.")
                    
                bind_matrix = math.get_object_bind(b_bone)
                _, bind_rot, bind_trans = math.decompose_srt(bind_matrix)

                quat_curve = []
                euler_curve = []
                trans_curve = []
                scale_curve = []

                for frame, quat in self.iter_frame_key(quaternion_data, mathutils.Quaternion):
                    quat = math.export_keymat(bind_rot, quat.to_matrix().to_4x4(), b_bone).to_quaternion()
                    quat_curve.append((frame, quat))

                for frame, euler in self.iter_frame_key(euler_data, mathutils.Euler):
                    keymat = math.export_keymat(bind_rot, euler.to_matrix().to_4x4(), b_bone)
                    euler = keymat.to_euler("XYZ", euler)
                    euler_curve.append((frame, euler))

                for frame, trans in self.iter_frame_key(translation_data, mathutils.Vector):
                    keymat = math.export_keymat(bind_rot, mathutils.Matrix.Translation(trans), b_bone)
                    trans = keymat.to_translation() + bind_trans
                    trans_curve.append((frame, trans))

                for frame, scale in self.iter_frame_key(scale_data, mathutils.Vector):
                    # just use the first scale curve and assume even scale over all curves
                    scale_curve.append((frame, scale[0]))

                if max(len(c) for c in (quat_curve, euler_curve, trans_curve, scale_curve)) > 0:
                    # number of frames is > 0, so export transform data
                    self.export_ni_transform_controller(quat_curve, euler_curve, trans_curve, scale_curve, b_action, action_fcurves, n_node, n_node_name, bind_matrix, n_ni_controller_sequence, b_bone)
        else:
            quaternion_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith("quaternion")]
            translation_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith("location")]
            euler_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith("euler")]
            scale_data = [fcu for fcu in action_fcurves if fcu.data_path.endswith("scale")]

            # ensure that those groups that are present have all their fcurves
            for fcus, num_fcus in ((quaternion_data, 4), (euler_data, 3), (translation_data, 3), (scale_data, 3)):
                if fcus and len(fcus) != num_fcus:
                    NifLog.warn(f"{fcus, len(fcus), num_fcus}")
                    raise NifError(
                        f"Incomplete {b_obj.name} key set for action {b_action.name}.\nEnsure that if a bone is keyframed for a property, all channels are keyframed.")
                
            bind_matrix = b_obj.matrix_parent_inverse
            _, bind_rot, bind_trans = math.decompose_srt(bind_matrix)

            quat_curve = []
            euler_curve = []
            trans_curve = []
            scale_curve = []

            for frame, quat in self.iter_frame_key(quaternion_data, mathutils.Quaternion):
                quat = math.export_keymat(bind_rot, quat.to_matrix().to_4x4()).to_quaternion()
                quat_curve.append((frame, quat))

            for frame, euler in self.iter_frame_key(euler_data, mathutils.Euler):
                keymat = math.export_keymat(bind_rot, euler.to_matrix().to_4x4())
                euler = keymat.to_euler("XYZ", euler)
                euler_curve.append((frame, euler))

            for frame, trans in self.iter_frame_key(translation_data, mathutils.Vector):
                keymat = math.export_keymat(bind_rot, mathutils.Matrix.Translation(trans))
                trans = keymat.to_translation() + bind_trans
                trans_curve.append((frame, trans))

            for frame, scale in self.iter_frame_key(scale_data, mathutils.Vector):
                # just use the first scale curve and assume even scale over all curves
                scale_curve.append((frame, scale[0]))

            if max(len(c) for c in (quat_curve, euler_curve, trans_curve, scale_curve)) > 0:
                # number of frames is > 0, so export transform data
                self.export_ni_transform_controller(quat_curve, euler_curve, trans_curve, scale_curve, b_action, action_fcurves, n_obj, n_obj_name, math.get_object_bind(b_obj), n_ni_controller_sequence)

        hide_data = [fcu for fcu in action_fcurves if "hide" in fcu.data_path]

        hide_curve = []

        for fcurve in hide_data:
            for keyframe in fcurve.keyframe_points:
                hide_curve.append((keyframe.co[0], keyframe.co[1]))

        if hide_curve:
            self.export_ni_vis_controller(hide_curve, b_action, action_fcurves, n_obj, n_obj_name, n_ni_controller_sequence)

    def export_ni_transform_controller(self, quat_curves, euler_curves, trans_curves, scale_curves, b_action, action_fcurves, n_node, n_node_name, bind_matrix=None, n_ni_controller_sequence=None, b_bone=None):
        scene_fps = self.fps

        # before interpolators the controller held the keys itself, under its own block type
        use_interpolator = NifData.data.version >= V_INTERPOLATORS

        # In a NIF, a controller manager drives every animated node through a single shared
        # NiMultiTargetTransformController, so the nodes keep no transform controller of
        # their own. A KF has no nodes to keep one on in the first place.
        n_manager = getattr(n_ni_controller_sequence, "manager", None) if n_ni_controller_sequence else None
        n_multi_target_controller = self.get_multi_target_controller(n_manager, n_node)

        if n_multi_target_controller:
            n_kfc = n_multi_target_controller
        else:
            n_kfc = block_store.create_block("NiTransformController" if use_interpolator else "NiKeyframeController")
            self.set_flags_and_timing(n_kfc, action_fcurves, *b_action.frame_range)

        n_kfd = block_store.create_block("NiTransformData" if use_interpolator else "NiKeyframeData")

        if euler_curves:
            n_kfd.rotation_type = NifClasses.KeyType.XYZ_ROTATION_KEY
            n_kfd.num_rotation_keys = 1  # *NOT* len(frames) this crashes the engine!
            n_kfd.reset_field("xyz_rotations")
            for i, coord in enumerate(n_kfd.xyz_rotations):
                coord.num_keys = len(euler_curves)
                coord.interpolation = NifClasses.KeyType.LINEAR_KEY
                coord.reset_field("keys")
                for key, (frame, euler) in zip(coord.keys, euler_curves):
                    key.time = frame / scene_fps
                    key.value = euler[i]

        elif quat_curves:
            n_kfd.rotation_type = NifClasses.KeyType.QUADRATIC_KEY
            n_kfd.num_rotation_keys = len(quat_curves)
            n_kfd.reset_field("quaternion_keys")
            for key, (frame, quat) in zip(n_kfd.quaternion_keys, quat_curves):
                key.time = frame / scene_fps
                key.value.w = quat.w
                key.value.x = quat.x
                key.value.y = quat.y
                key.value.z = quat.z

        n_kfd.translations.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_kfd.translations.num_keys = len(trans_curves)
        n_kfd.translations.reset_field("keys")

        for key, (frame, trans) in zip(n_kfd.translations.keys, trans_curves):
            key.time = frame / scene_fps
            key.value.x, key.value.y, key.value.z = trans

        n_kfd.scales.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_kfd.scales.num_keys = len(scale_curves)
        n_kfd.scales.reset_field("keys")

        for key, (frame, scale) in zip(n_kfd.scales.keys, scale_curves):
            key.time = frame / scene_fps
            key.value = scale

        if use_interpolator:
            n_kfi = block_store.create_block("NiTransformInterpolator")
            n_kfi.data = n_kfd
            if bind_matrix is not None:
                # channels left unkeyed fall back to the interpolator's own transform
                n_scale, n_rot, n_trans = math.decompose_srt(bind_matrix)
                n_quat = n_rot.to_quaternion()
                n_kfi.transform.scale = n_scale
                n_kfi.transform.translation.x, n_kfi.transform.translation.y, n_kfi.transform.translation.z = n_trans
                n_kfi.transform.rotation.w, n_kfi.transform.rotation.x, n_kfi.transform.rotation.y, n_kfi.transform.rotation.z = n_quat
        else:
            n_kfi = None
            n_kfc.data = n_kfd

        if n_multi_target_controller:
            n_multi_target_controller.num_extra_targets += 1
            n_multi_target_controller.extra_targets.append(n_node)
        elif use_interpolator:
            n_kfc.interpolator = n_kfi

        attach_controller(n_kfc, n_kfi, n_node_name, "NiTransformController",
                          n_ctrl_target=None if n_multi_target_controller else n_node,
                          n_sequence=n_ni_controller_sequence,
                          priority=b_bone.nif_bone.priority if b_bone else 0,
                          blend_interpolator=not n_multi_target_controller)

    @staticmethod
    def get_multi_target_controller(n_manager, n_node):
        """
        Get the controller manager's NiMultiTargetTransformController, creating it on
        first use. Returns None when there is nothing for it to drive, as in a KF.
        """

        if n_manager is None or n_node is None:
            return None

        n_multi_target_controller = n_manager.next_controller

        if n_multi_target_controller is None:
            n_multi_target_controller = block_store.create_block("NiMultiTargetTransformController")
            n_multi_target_controller.target = n_manager.target
            n_manager.next_controller = n_multi_target_controller

        return n_multi_target_controller
