"""Main module for exporting material animation blocks."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2025 NIF File Format Library and Tools contributors.
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


from io_scene_niftools.modules.nif_export.animation.common import AnimationCommon
from io_scene_niftools.modules.nif_export.block_registry import block_store
from nifgen.formats.nif import classes as NifClasses


class MaterialAnimation(AnimationCommon):

    def __init__(self):
        super().__init__()

    def export_material_animations(self, b_material, n_mat_prop):
        """Export material animations for given geometry."""

        self.export_material_controllers(b_material, n_mat_prop)

    def export_material_controllers(self, b_material, n_mat_prop):
        """Export material animation data for given geometry."""

        if not n_mat_prop:
            raise ValueError("Bug!! must add material property before exporting alpha controller")
        colors = (("alpha", None),
                  ("niftools.ambient_color", NifClasses.MaterialColor.TC_AMBIENT),
                  ("diffuse_color", NifClasses.MaterialColor.TC_DIFFUSE),
                  ("specular_color", NifClasses.MaterialColor.TC_SPECULAR))
        # the actual export
        for b_dtype, n_dtype in colors:
            self.export_material_alpha_color_controller(b_material, n_mat_prop, b_dtype, n_dtype)

    def export_material_alpha_color_controller(self, b_material, n_mat_prop, b_dtype, n_dtype):
        """Export the material alpha or color controller data."""

        # get fcurves
        if not b_material.animation_data:
            return

        fcurves = [fcu for fcu in b_material.animation_data.action.fcurves if b_dtype in fcu.data_path]
        if not fcurves:
            return

        # just set the names of the nif data types, main difference between alpha and color
        if b_dtype == "alpha":
            keydata = "NiFloatData"
            interpolator = "NiFloatInterpolator"
            controller = "NiAlphaController"
        else:
            keydata = "NiPosData"
            interpolator = "NiPoint3Interpolator"
            controller = "NiMaterialColorController"

        # create the key data
        n_key_data = block_store.create_block(keydata, fcurves)
        n_key_data.data.num_keys = len(fcurves[0].keyframe_points)
        n_key_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_key_data.data.reset_field("keys")

        # assumption: all curves have same amount of keys and are sampled at the same time
        for i, n_key in enumerate(n_key_data.data.keys):
            frame = fcurves[0].keyframe_points[i].co[0]
            # add each point of the curves
            n_key.arg = n_key_data.data.interpolation
            n_key.time = frame / self.fps
            if b_dtype == "alpha":
                n_key.value = fcurves[0].keyframe_points[i].co[1]
            else:
                n_key.value.x, n_key.value.y, n_key.value.z = [fcu.keyframe_points[i].co[1] for fcu in fcurves]
        # if key data is present
        # then add the controller so it is exported
        if fcurves[0].keyframe_points:
            n_mat_ctrl = block_store.create_block(controller, fcurves)
            n_mat_ipol = block_store.create_block(interpolator, fcurves)
            n_mat_ctrl.interpolator = n_mat_ipol

            self.set_flags_and_timing(n_mat_ctrl, fcurves)
            # set target color only for color controller
            if n_dtype:
                n_mat_ctrl.set_target_color(n_dtype)
            n_mat_ctrl.data = n_key_data
            n_mat_ipol.data = n_key_data
            # attach block to material property
            n_mat_prop.add_controller(n_mat_ctrl)
