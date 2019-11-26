"""This script contains classes to help export object animations."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2019, NIF File Format Library and Tools contributors.
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
from pyffi.formats.nif import NifFormat

from io_scene_nif.modules.animation import animation_export
from io_scene_nif.modules.obj.block_registry import block_store


class ObjectAnimation:

    def export_object_vis_controller(self, n_node, b_obj):
        """Export the visibility controller data."""

        if not b_obj.animation_data and not b_obj.animation_data.action:
            return

        # get the hide fcurve
        fcurves = [fcu for fcu in b_obj.animation_data.action.fcurves if "hide" in fcu.data_path]
        if not fcurves:
            return

        # TODO [animation] which sort of controller should be exported?
        #                  should this be driven by version number?
        #                  we probably don't want both at the same time
        # NiVisData = old style, NiBoolData = new style
        n_vis_data = block_store.create_block("NiVisData", fcurves)
        n_bool_data = block_store.create_block("NiBoolData", fcurves)

        # we just leave interpolation at constant
        n_bool_data.data.interpolation = NifFormat.KeyType.CONST_KEY
        n_vis_data.num_keys = len(fcurves[0].keyframe_points)
        n_vis_data.keys.update_size()
        n_bool_data.data.num_keys = len(fcurves[0].keyframe_points)
        n_bool_data.data.keys.update_size()
        for b_point, n_vis_key, n_bool_key in zip(fcurves[0].keyframe_points, n_vis_data.keys, n_bool_data.data.keys):
            # add each point of the curve
            b_frame, b_value = b_point.co
            n_vis_key.arg = n_bool_data.data.interpolation  # n_vis_data has no interpolation stored
            n_vis_key.time = b_frame / bpy.context.scene.render.fps
            n_vis_key.value = b_value
            n_bool_key.arg = n_bool_data.data.interpolation
            n_bool_key.time = n_vis_key.time
            n_bool_key.value = n_vis_key.value

        # if alpha data is present (check this by checking if times were added) then add the controller so it is exported
        if fcurves[0].keyframe_points:
            n_vis_ctrl = self.nif_export.objecthelper.create_block("NiVisController", fcurves)
            n_vis_ipol = self.nif_export.objecthelper.create_block("NiBoolInterpolator", fcurves)
            animation_export.set_flags_and_timing(n_vis_ctrl, fcurves)
            n_vis_ctrl.interpolator = n_vis_ipol
            n_vis_ctrl.data = n_vis_data
            n_vis_ipol.data = n_bool_data
            # attach block to node
            n_node.add_controller(n_vis_ctrl)
