"""Classes for exporting NIF collision blocks."""

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

from io_scene_niftools.modules.nif_export.collision.bound import Bound, NiCollision
from io_scene_niftools.modules.nif_export.collision.havok import BhkCollision
from io_scene_niftools.modules.nif_export.collision.havok.animation import BhkBlendCollision
from io_scene_niftools.modules.nif_export.object import DICT_NAMES
from io_scene_niftools.utils.logging import NifLog

from nifgen.formats.nif import classes as NifClasses


class Collision:
    """Main interface class for exporting NIF collision blocks."""

    def __init__(self):
        self.bhk_collision_helper = BhkCollision()
        self.bhk_blend_collision_helper = BhkBlendCollision()
        self.bound_helper = Bound()
        self.ni_collision_helper = NiCollision()
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_collision(self, b_collision_objects):
        """Main function for handling collision export."""

        NifLog.info(f"Exporting collision...")

        if not b_collision_objects:
            return  # No collision data in the scene

        for b_col_obj in b_collision_objects:

            # Skip bhkListShape sub-shapes for now
            if b_col_obj.parent.rigid_body:
                continue

            # Get parent node from object dictionary
            if b_col_obj.parent:
                n_parent_node = DICT_NAMES[b_col_obj.parent.name]
            else:
                n_parent_node = DICT_NAMES[b_col_obj.name]

            if "bound" in b_col_obj.name.lower():
                # Export bounding boxes
                if self.target_game == 'MORROWIND':
                    # Export Morrowind NiNode bounding box
                    self.bound_helper.export_bounds(b_col_obj, n_parent_node, bsbound=False)
                else:
                    # Export BSBound
                    self.bound_helper.export_bounds(b_col_obj, n_parent_node, bsbound=True)
                continue

            if bpy.context.scene.niftools_scene.is_bs():
                # Export Bethesda/Havok collision objects
                layer = int(b_col_obj.nif_collision.collision_layer)

                if self.target_game in ('OBLIVION', 'OBLIVION_KF'):
                    if NifClasses.OblivionLayer.from_value(layer) == 'OL_BIPED':
                        self.bhk_blend_collision_helper.export_bhk_blend_collision(b_col_obj)
                elif self.target_game in ('FALLOUT_3', 'Fallout_NV'):
                    if NifClasses.Fallout3Layer.from_value(layer) == 'FOL_BIPED':
                        self.bhk_blend_collision_helper.export_bhk_blend_collision(b_col_obj)
                self.bhk_collision_helper.export_bhk_collision(b_col_obj, n_parent_node, layer)
            elif self.target_game in ('ZOO_TYCOON_2',):
                self.ni_collision_helper.export_nicollisiondata(b_col_obj, n_parent_node)
            else:
                NifLog.warn(f"Collision not supported for game '{self.target_game}', "
                            f"skipped collision object '{b_col_obj.name}'")
