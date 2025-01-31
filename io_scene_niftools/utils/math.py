"""Common NIF math utilities used across the code base."""

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
import mathutils
from bpy_extras.io_utils import axis_conversion
from io_scene_niftools.utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses

THETA_THRESHOLD_NEGY = 1.0e-9
THETA_THRESHOLD_NEGY_CLOSE = 1.0e-5


def set_bone_orientation(from_forward, from_up):
    # if version in (0x14020007, ):
    #   skyrim
    #   from_forward = "Z"
    #   from_up = "Y"
    # else:
    #   ZT2 and other old ones
    #   from_forward = "X"
    #   from_up = "Y"
    global correction
    global correction_inv
    correction = axis_conversion(from_forward, from_up).to_4x4()
    correction_inv = correction.inverted()


# set these from outside using set_bone_correction_from_version once we have a version number
correction = None
correction_inv = None


def import_keymat(rest_rot_inv, key_matrix):
    """Handles space conversions for imported keys """
    return correction @ (rest_rot_inv @ key_matrix) @ correction_inv


def export_keymat(rest_rot, key_matrix, bone):
    """Handles space conversions for exported keys """
    if bone:
        return rest_rot @ (correction_inv @ key_matrix @ correction)
    else:
        return rest_rot @ key_matrix


def _get_bone_bind(bone):
    """Get a nif local-space matrix from a blender bone. """
    bind = bone.matrix_local @ correction
    # make relative to parent
    if bone.parent:
        p_bind_restored = bone.parent.matrix_local @ correction
        bind = p_bind_restored.inverted() @ bind
    return bind


def _get_bone_pose(bone):
    """Get a nif local-space matrix from a blender pose bone. """
    bind = bone.matrix @ correction
    # make relative to parent
    if bone.parent:
        p_bind_restored = bone.parent.matrix @ correction
        bind = p_bind_restored.inverted() @ bind
    return bind


def blender_bind_to_nif_bind(blender_armature_space_matrix):
    return blender_armature_space_matrix @ correction


def nif_bind_to_blender_bind(nif_armature_space_matrix):
    return nif_armature_space_matrix @ correction_inv


def import_matrix(n_block, relative_to=None):
    """Retrieves a n_block's transform matrix as a Mathutil.Matrix."""
    return nifformat_to_mathutils_matrix(n_block.get_transform(relative_to))


def decompose_srt(b_matrix):
    """Decompose Blender transform matrix as a scale, 4x4 rotation matrix, and translation vector."""

    # get matrix components
    trans_vec, rot_quat, scale_vec = b_matrix.decompose()
    rotmat = rot_quat.to_matrix()

    # todo [armature] negative scale is not generated on armature end
    #                 no need to run costly operations here for now
    # and fix the sign of scale
    # if b_matrix.determinant() < 0:
    #     scale_vec.negate()

    # only uniform scaling allow rather large error to accommodate some nifs
    if abs(scale_vec[0] - scale_vec[1]) + abs(scale_vec[1] - scale_vec[2]) > 0.02:
        NifLog.warn("Non-uniform scaling not supported. Workaround: apply size and rotation (CTRL-A).")
    return scale_vec[0], rotmat.to_4x4(), trans_vec


def get_armature():
    """Get an armature. If there is more than one armature in the scene and some armatures are selected, return the first of the selected armatures. """
    b_armatures = [ob for ob in bpy.data.objects if type(ob.data) == bpy.types.Armature]
    # do we have armatures?
    if b_armatures:
        # see if one of these is selected -> get only that one
        if len(b_armatures) > 1:
            b_sel_armatures = [ob for ob in b_armatures if ob.select_get()]
            if b_sel_armatures:
                return b_sel_armatures[0]
        return b_armatures[0]


def get_armatures():
    """Get all armatures in the scene."""
    b_armatures = [ob for ob in bpy.data.objects if type(ob.data) == bpy.types.Armature]
    return b_armatures


def get_object_bind(b_obj):
    """Get the bind matrix of a blender object.
    Returns the final NIF matrix for the given blender object.
    Blender space and axes order are corrected for the NIF for bones.
    Returns a 4x4 mathutils.Matrix()
    """

    if isinstance(b_obj, bpy.types.Bone):
        return _get_bone_bind(b_obj)
    elif isinstance(b_obj, bpy.types.PoseBone):
        return _get_bone_pose(b_obj)
    elif isinstance(b_obj, bpy.types.Object):
        # TODO [armature] Move to armaturehelper
        # if there is a bone parent then the object is parented then get the matrix relative to the bone parent head
        if b_obj.parent_bone:
            # get parent bone
            parent_bone = b_obj.parent.data.bones[b_obj.parent_bone]

            # undo what was done on import
            mpi = nif_bind_to_blender_bind(b_obj.matrix_parent_inverse).inverted()
            mpi.translation.y -= parent_bone.length
            return mpi.inverted() @ b_obj.matrix_basis
        # just get the local matrix
        else:
            return b_obj.matrix_local.copy()
    # Nonetype, maybe other weird stuff
    return mathutils.Matrix()


def find_property(n_block, property_type):
    """Find a property."""
    if hasattr(n_block, "properties"):
        for prop in n_block.properties:
            if isinstance(prop, property_type):
                return prop

    for prop_name in ("shader_property", "alpha_property"):
        if hasattr(n_block, prop_name):
            prop = getattr(n_block, prop_name)
            if isinstance(prop, property_type):
                return prop
    return None


def find_controller(n_block, controller_type):
    """Find a controller."""
    ctrl = n_block.controller
    while ctrl:
        if isinstance(ctrl, controller_type):
            if ctrl.data or ctrl.interpolator:
                return ctrl
        ctrl = ctrl.next_controller


def controllers_iter(n_block, controller_type):
    """Find a controller."""
    ctrl = n_block.controller
    while ctrl:
        if isinstance(ctrl, controller_type):
            if ctrl.data or ctrl.interpolator:
                yield ctrl
        ctrl = ctrl.next_controller


def find_extra(n_block, extratype):
    # TODO: 3.0 - Optimise

    """Find extra data."""
    # pre-10.x.x.x system: extra data chain
    extra = n_block.extra_data
    while extra:
        if isinstance(extra, extratype):
            break
        extra = extra.next_extra_data
    if extra:
        return extra

    # post-10.x.x.x system: extra data list
    for extra in n_block.extra_data_list:
        if isinstance(extra, extratype):
            return extra
    return None


def set_object_matrix(b_obj, block):
    """Set a blender object's transform matrix to a NIF object's transformation matrix in rest pose."""
    block.set_transform(get_object_matrix(b_obj))


def get_object_matrix(b_obj):
    """Get a blender object's matrix as NifFormat.Matrix44"""
    return mathutils_to_nifformat_matrix(get_object_bind(b_obj))


def set_b_matrix_to_n_block(b_matrix, block):
    """Set a blender matrix to a NIF object's transformation matrix in rest pose."""
    # TODO [object] maybe favor this over the above two methods for more flexibility and transparency?
    block.set_transform(mathutils_to_nifformat_matrix(b_matrix))


def mathutils_to_nifformat_matrix(b_matrix):
    """Convert a blender matrix to a NifFormat.Matrix44"""
    # transpose to swap columns for rows so we can use pyffi's set_rows() directly
    # instead of setting every single value manually
    n_matrix = NifClasses.Matrix44()
    n_matrix.set_rows(*b_matrix.transposed())
    return n_matrix


def nifformat_to_mathutils_matrix(n_matrix):
    """Convert a NifFormat.Matrix44 to a blender matrix"""
    return mathutils.Matrix(n_matrix.as_list()).transposed()
