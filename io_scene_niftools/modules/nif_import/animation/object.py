"""This script contains classes to help import object animations."""

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

from ....modules.nif_import.animation import Animation
from ....utils import math
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses

# The visibility channel of a bone, on its armature rather than on the armature object
BONE_HIDE_PATH = re.compile(r'^bones\["(.+)"\]\.hide$')


def get_hide_target(b_target):
    """
    Resolve an animation target to the datablock and data path that hide it.

    A bone is hidden through its armature, an object through itself.
    """

    if isinstance(b_target, bpy.types.PoseBone):
        # a pose bone is the posed copy of a bone; the animatable flag is on the bone
        return b_target.id_data.data, f'bones["{b_target.name}"].hide'
    return b_target, "hide_viewport"


def hide_animated_bones(b_armature):
    """The bones of an armature whose visibility any of its actions animates."""

    b_anim_data = b_armature.animation_data
    if not b_anim_data:
        return frozenset()

    b_actions = [b_anim_data.action]
    b_actions.extend(b_strip.action for b_track in b_anim_data.nla_tracks
                     for b_strip in b_track.strips)

    b_bone_names = set()
    for b_action in b_actions:
        if b_action is None:
            continue
        for b_fcurve in Animation.get_fcurves_from_action(b_action):
            match = BONE_HIDE_PATH.match(b_fcurve.data_path)
            if match:
                b_bone_names.add(match.group(1))
    return b_bone_names


def update_bone_visibility():
    """
    Hide the objects attached to a bone along with the bone itself.

    A nif node that a visibility controller hides takes its geometry with it, but a
    Blender bone and the objects parented to it are hidden separately. Parenting is read
    fresh on every call, so relationship changes are reflected.
    """

    b_hidden_bones = {}
    for b_armature in bpy.data.armatures:
        b_bone_names = hide_animated_bones(b_armature)
        if b_bone_names:
            b_hidden_bones[b_armature] = b_bone_names

    if not b_hidden_bones:
        return

    for b_obj in bpy.data.objects:
        if b_obj.parent_type != 'BONE' or not b_obj.parent_bone:
            continue
        b_parent = b_obj.parent
        b_armature = b_parent.data if b_parent and b_parent.type == 'ARMATURE' else None
        if b_obj.parent_bone not in b_hidden_bones.get(b_armature, ()):
            continue

        b_bone = b_armature.bones.get(b_obj.parent_bone)
        if b_bone is not None and b_obj.hide_viewport != b_bone.hide:
            b_obj.hide_viewport = b_bone.hide


class ObjectAnimation(Animation):

    def import_sequence_controlled_block(self, n_controlled_block, sequence_name, b_target,
                                         n_target_name=""):
        """Import a sequence-driven visibility controller for an object."""

        n_controller = n_controlled_block.controller
        controller_type = str(n_controlled_block.controller_type or "")
        if n_controller is not None and not controller_type:
            controller_type = type(n_controller).__name__
        if controller_type != "NiVisController":
            return False

        if not isinstance(b_target, (bpy.types.Object, bpy.types.PoseBone)):
            n_target_name = n_target_name or getattr(b_target, "name", "")
            NifLog.warn(f"The visibility controller of sequence '{sequence_name}' has nothing "
                        f"in the scene named '{n_target_name}' to hide, so it is skipped")
            return True

        n_ctrl_data = self.get_interpolator_data(n_controlled_block.interpolator)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The sequence visibility controller of '{b_target.name}' holds no keys, "
                        f"so it is skipped")
            return True

        flags = n_controller.flags if n_controller is not None else 0
        self.import_visibility_keys(
            b_target, n_ctrl_data, flags, sequence_name=sequence_name)
        return True

    def import_visibility(self, n_node, b_target):
        """Import the vis controller attached to a node, for its object or bone."""

        n_vis_ctrl = math.find_controller(n_node, NifClasses.NiVisController)
        if not n_vis_ctrl:
            return
        NifLog.info("Importing vis controller")

        n_ctrl_data = self.get_controller_data(n_vis_ctrl)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The vis controller of '{b_target.name}' holds no keys, so it is skipped")
            return

        self.import_visibility_keys(b_target, n_ctrl_data, n_vis_ctrl.flags)

    def import_visibility_keys(self, b_target, n_ctrl_data, flags, sequence_name=None):
        """Insert visibility data, shared by attached and sequence controllers."""

        # A bone keeps its own visibility flag, so it is keyed like any other channel.
        # The geometry a nif hides along with the node follows the bone at runtime.
        b_owner, data_path = get_hide_target(b_target)

        action_name = (f"{sequence_name}_{b_target.name}" if sequence_name
                       else f"{b_target.name}-Anim")
        b_action = self.create_action(b_owner, action_name, sequence_name)
        times, keys = self.get_keys_values(n_ctrl_data.keys)
        # A NIF visibility value shows an object. Blender's channel hides it.
        self.add_keys(b_owner, b_action, data_path, (0,), flags,
                      times, [not value for value in keys], "CONSTANT")
        self.set_max_key_time()
