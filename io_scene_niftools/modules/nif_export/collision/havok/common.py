"""Common functions shared between Havok collision export classes."""

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
from io_scene_niftools.modules.nif_export.collision.common import CollisionCommon
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BhkCollisionCommon(CollisionCommon):
    """Abstract base class containing functions and attributes shared between Havok collision export classes."""

    def __init__(self):
        super().__init__()

        self.HAVOK_SCALE = None
        self.HAVOK_MATERIALS = []
        self.is_oblivion = self.target_game in ('OBLIVION', 'OBLIVION_KF')
        self.is_fallout = self.target_game in ('FALLOUT_3', 'FALLOUT_NV')

    def get_havok_material_list(self, b_col_obj):
        """Get the Blender object's material list as Havok materials."""

        self.HAVOK_MATERIALS = type(NifClasses.HavokMaterial(NifData.data).material)
        n_hav_mat_list = []
        n_default_material = self.HAVOK_MATERIALS.from_value(0)

        if b_col_obj.data.materials:
            for b_mat in b_col_obj.data.materials:
                try:
                    n_hav_mat_list.append(self.HAVOK_MATERIALS[b_mat.name])
                except KeyError:
                    NifLog.warn(f"Unknown Havok material '{b_mat.name}' for object {b_col_obj.name}! "
                                f"Defaulting to '{n_default_material}'")
                    n_hav_mat_list.append(n_default_material)
        else:
            NifLog.warn(f"No material applied' for object {b_col_obj.name}! "
                        f"Defaulting to '{n_default_material}'")
            n_hav_mat_list.append(n_default_material)

        return n_hav_mat_list

    @staticmethod
    def update_rigid_body(b_col_obj, n_bhk_rigid_body):
        if bpy.context.scene.niftools_scene.is_bs():
            # Update rigid body center of mass and inertia
            # Mass value should be set manually as it is not necessarily physically accurate
            n_bhk_rigid_body.update_mass_center_inertia(mass=n_bhk_rigid_body.rigid_body_info.mass,
                                                        solid=b_col_obj.nif_collision.solid)
