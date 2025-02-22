"""Helper functions for NIF import and export scripts."""

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

import bpy
import nifgen.formats.nif as NifFormat
from io_scene_niftools.utils import debugging
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifOp
from nifgen.spells.nif import NifToaster
from nifgen.spells.nif.fix import SpellScale


class NifCommon:
    """
    Abstract base class for NIF import and export operators.
    Contains common utility functions that are used in both.
    """

    def __init__(self, operator, context):
        """Common initialization functions for executing the import/export operators."""

        NifOp.init(operator, context)

        debugging.start_debug()

        # Print scripts info
        from io_scene_niftools import bl_info
        niftools_ver = (".".join(str(i) for i in bl_info["version"]))

        NifLog.info(f"Executing - NifTools : Blender NifTools Add-on v{niftools_ver}. "
                    f"(Running on Blender {bpy.app.version_string}, "
                    f"NIF XML version {NifFormat.__xml_version__}).")

    @staticmethod
    def apply_scale(data, scale):
        NifLog.info(f"Scale Correction set to {scale}.")
        toaster = NifToaster()
        toaster.scale = scale
        SpellScale(data=data, toaster=toaster).recurse()
