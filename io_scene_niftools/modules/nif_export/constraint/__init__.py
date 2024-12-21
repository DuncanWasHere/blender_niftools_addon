"""Classes for exporting NIF constraint blocks."""

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
from io_scene_niftools.modules.nif_export.constraint.havok import BhkConstraint

from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData


class Constraint:
    """Main class for exporting NIF constraint blocks."""

    def __init__(self):
        self.bhk_constraint_helper = BhkConstraint()
        self.target_game = None

    def export_constraints(self, b_constraint_objects, n_root_node, target_game):
        """Main function for handling constraint export."""

        if not b_constraint_objects:
            return

        self.target_game = target_game

        # Set Havok Scale ratio
        self.HAVOK_SCALE = NifData.data.havok_scale

        for b_constr_obj in b_constraint_objects:

            # Only export constraints for Bethesda games
            if not bpy.context.scene.niftools_scene.is_bs():
                NifLog.warn(f"Constraints not supported for game '{self.target_game}', "
                            f"skipped collision object '{b_constr_obj.name}'")

            NifLog.warn(f"Exporting constraint!")

            b_constr = b_constr_obj.rigid_body_constraint

            self.bhk_constraint_helper.export_bhk_constraint(b_constr, b_constr_obj)
