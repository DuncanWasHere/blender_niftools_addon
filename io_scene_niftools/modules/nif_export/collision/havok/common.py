"""Common functions shared between Havok collision export classes."""

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
from .....modules.nif_export.collision.common import CollisionCommon
from .....utils.logging import NifLog
from .....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BhkCollisionCommon(CollisionCommon):
    """Abstract base class containing functions and attributes shared between Havok collision export classes."""

    def __init__(self):
        super().__init__()

        self.HAVOK_SCALE = None
        self.HAVOK_MATERIALS = []
        self.is_oblivion = self.target_game in ('OBLIVION', 'OBLIVION_KF')
        self.is_fallout = self.target_game in ('FALLOUT_3', 'FALLOUT_NV')

    def get_collision_object_flags(self, b_col_obj, n_hav_layer):
        """
        The flags of a bhkNiCollisionObject, whichever kind is being written.

        Whatever the user set, or import read out of the source nif, is the starting point;
        the bits below are the ones the format documents as required for animated collision,
        so they are added on top rather than replacing the stored value.
        """

        n_flags = b_col_obj.nif_collision.collision_flags

        n_anim_static = None
        if self.is_oblivion:
            n_anim_static = NifClasses.OblivionLayer.OL_ANIM_STATIC
        elif self.is_fallout:
            n_anim_static = NifClasses.Fallout3Layer.FOL_ANIM_STATIC

        # unless it is constrained but not keyframed
        if n_anim_static is not None and n_hav_layer == n_anim_static \
                and b_col_obj.nif_collision.col_filter != 128:
            n_flags |= NifClasses.BhkCOFlags.SET_LOCAL | NifClasses.BhkCOFlags.USE_VEL

        return n_flags

    def get_havok_material_list(self, b_col_obj):
        """Get the Blender object's material list as Havok materials."""

        self.HAVOK_MATERIALS = type(NifClasses.HavokMaterial(NifData.data).material)
        n_hav_mat_list = []
        n_default_material = self.HAVOK_MATERIALS.from_value(0)

        if b_col_obj.data.materials:
            for b_mat in b_col_obj.data.materials:
                try:
                    n_hav_mat_list.append(self.HAVOK_MATERIALS[b_mat.name.upper()])
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

    def __export_bhk_transform_shape(self, b_col_obj, n_hav_mat, radius=0.1):
        """
        Export and return a bhkTransformShape.
        Note: should generally never be used. Function will remain here for completeness.
        """

        n_bhk_transform_shape = block_store.create_block("bhkTransformShape", b_col_obj)
        n_bhk_transform_shape.material.material = n_hav_mat
        n_bhk_transform_shape.radius = radius

        matrix = math.get_object_bind(b_col_obj)
        row0 = list(matrix[0])
        row1 = list(matrix[1])
        row2 = list(matrix[2])
        row3 = list(matrix[3])
        n_bhk_transform_shape.transform.set_rows(row0, row1, row2, row3)
        n_bhk_transform_shape.apply_scale(1.0 / self.HAVOK_SCALE)

        return n_bhk_transform_shape