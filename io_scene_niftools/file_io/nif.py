"""NIF file operations for import/export."""

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
import os.path as path

import bpy
import nifgen.formats.nif as NifFormat
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import EGMData


class NifFile:
    """Class for loading and saving NIF files."""

    @staticmethod
    def load_nif(file_path):
        """Load a NIF from the given file path."""

        NifLog.info(f"Importing {file_path}")

        file_ext = path.splitext(file_path)[1]

        # Open file for binary reading
        with open(file_path, "rb") as nif_stream:
            # Check if nif file is valid
            modification, (version, user_version, bs_version) = NifFormat.NifFile.inspect_version_only(nif_stream)
            if version >= 0:
                # It is valid, so read the file
                NifLog.info(f"NIF file version: {version:x}")
                NifLog.info(f"Reading {file_ext} file")
                data = NifFormat.NifFile.from_stream(nif_stream)
            elif version == -1:
                raise NifError("Unsupported NIF version.")
            else:
                raise NifError("Not a NIF file.")

        return data

    @staticmethod
    def write_nif(n_data, directory, file_base, file_ext):
        # export nif file:
        if bpy.context.scene.niftools_scene.game == 'EMPIRE_EARTH_II':
            file_ext = ".nifcache"
        NifLog.info(f"Writing {file_ext} file.")

        # Assemble full file path and add 'x' prefix for Morrowind
        prefix = "x" if bpy.context.scene.niftools_scene.game in ('MORROWIND',) else ""
        niffile = os.path.join(directory, prefix + file_base + file_ext)

        # todo [export] I believe this is redundant and setting modification only is the current way?
        n_data.neosteam = (bpy.context.scene.niftools_scene.game == 'NEOSTEAM')
        if bpy.context.scene.niftools_scene.game == 'NEOSTEAM':
            n_data.modification = "neosteam"
        elif bpy.context.scene.niftools_scene.game == 'ATLANTICA':
            n_data.modification = "ndoors"
        elif bpy.context.scene.niftools_scene.game == 'HOWLING_SWORD':
            n_data.modification = "jmihs1"

        NifLog.info(f"Validating.")
        n_data.validate()
        with open(niffile, "wb") as stream:
            n_data.write(stream)

        # export egm file:
        # -----------------
        if EGMData.data:
            ext = ".egm"
            NifLog.info(f"Writing {ext} file.")

            egmfile = os.path.join(directory, file_base + ext)
            with open(egmfile, "wb") as stream:
                EGMData.data.write(stream)
