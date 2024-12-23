"""Main Blender -> KF export script."""

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


import os

from bpy.types import Scene
from io_scene_niftools.modules.nif_export.animation.object import ObjectAnimation
from io_scene_niftools.modules.nif_export.scene import Scene
from io_scene_niftools.nif_common import NifCommon
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, NifData


class KfExport(NifCommon):

    def __init__(self, operator, context):
        NifCommon.__init__(self, operator, context)

        # Helper systems
        self.transform_anim = ObjectAnimation()
        self.scene_helper = Scene()

    def execute(self):
        """Main KF export function."""

        NifLog.info(f"Exporting {NifOp.props.filepath}")

        # extract directory, base name, extension
        directory = os.path.dirname(NifOp.props.filepath)
        filebase, fileext = os.path.splitext(os.path.basename(NifOp.props.filepath))

        game, self.version, data = self.scene_helper.get_version_data()

        if game == 'UNKNOWN':
            raise NifError("You have not selected a game. Please select a game in the scene tab.")

        prefix = "x" if game in ('MORROWIND',) else ""
        # todo[anim] - change to KfData, but create_controller() [and maybe more] has to be updated first
        NifData.init(data)

        b_armature = math.get_armature()
        # some scenes may not have an armature, so nothing to do here
        if b_armature:
            math.set_bone_orientation(b_armature.data.niftools.axis_forward, b_armature.data.niftools.axis_up)

        NifLog.info("Creating keyframe tree")
        kf_root = self.transform_anim.export_kf_root(b_armature)

        # write kf (and xkf if asked)
        ext = ".kf"
        NifLog.info(f"Writing {prefix}{ext} file")

        data.roots = [kf_root]
        data.neosteam = (game == 'NEOSTEAM')

        # scale correction for the skeleton
        self.apply_scale(data, 1 / NifOp.props.scale_correction)

        data.validate()

        kffile = os.path.join(directory, prefix + filebase + ext)
        with open(kffile, "wb") as stream:
            data.write(stream)

        NifLog.info("Finished successfully")
        return {'FINISHED'}

