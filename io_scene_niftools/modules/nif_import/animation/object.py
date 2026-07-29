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

import bpy

from ....modules.nif_import.animation import Animation
from ....utils import math
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


class ObjectAnimation(Animation):

    def import_sequence_controlled_block(self, n_controlled_block, sequence_name, b_target):
        """Import a sequence-driven visibility controller for an object."""

        n_controller = n_controlled_block.controller
        controller_type = str(n_controlled_block.controller_type or "")
        if n_controller is not None and not controller_type:
            controller_type = type(n_controller).__name__
        if controller_type != "NiVisController":
            return False

        if not isinstance(b_target, bpy.types.Object):
            NifLog.warn("A sequence visibility controller has no object target, so it is skipped")
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

    def import_visibility(self, n_node, b_obj):
        """Import vis controller for blender object."""

        n_vis_ctrl = math.find_controller(n_node, NifClasses.NiVisController)
        if not n_vis_ctrl:
            return
        NifLog.info("Importing vis controller")

        n_ctrl_data = self.get_controller_data(n_vis_ctrl)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The vis controller of '{b_obj.name}' holds no keys, so it is skipped")
            return

        self.import_visibility_keys(b_obj, n_ctrl_data, n_vis_ctrl.flags)

    def import_visibility_keys(self, b_obj, n_ctrl_data, flags, sequence_name=None):
        """Insert visibility data, shared by attached and sequence controllers."""

        action_name = (f"{sequence_name}_{b_obj.name}" if sequence_name
                       else f"{b_obj.name}-Anim")
        b_obj_action = self.create_action(b_obj, action_name, sequence_name)
        times, keys = self.get_keys_values(n_ctrl_data.keys)
        # A NIF visibility value shows an object. Blender's channel hides it.
        self.add_keys(b_obj, b_obj_action, "hide_viewport", (0,), flags,
                      times, [not value for value in keys], "CONSTANT")
        self.set_max_key_time()
