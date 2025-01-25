"""Common functions shared between constraint export classes."""


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

class ConstraintCommon:
    """Abstract base class containing functions and attributes shared between constraint export classes."""

    def __init__(self):
        self.n_root_node = None
        self.HAVOK_SCALE = None

    @staticmethod
    def attach_constraint(n_bhk_constraint, n_entity_a, n_entity_b):
        n_bhk_constraint.constraint_info.entity_a = n_entity_a
        n_bhk_constraint.constraint_info.entity_b = n_entity_b
        n_entity_a.num_constraints += 1
        n_entity_a.constraints.append(n_bhk_constraint)
        n_entity_b.num_constraints += 1
        n_entity_b.constraints.append(n_bhk_constraint)

    def calculate_pivot(self, b_constr, b_constr_obj):
        return

    def calculate_plane(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_plane_a, n_plane_b)

    def calculate_twist(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_twist_a, n_twist_b)

    def calculate_motor(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_motor_a, n_motor_b)

    def calculate_cone_angle(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_cone_angle_a, n_cone_angle_b)

    def calculate_plane_angle(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_plane_angle_a, n_plane_angle_b)

    def calculate_twist_angle(self, b_constr, b_constr_obj, n_bhk_constraint):
        return (n_twist_angle_a, n_twist_angle_b)


'''
# defaults and getting object properties for user settings (should use constraint properties,
# but blender does not have those...)
if b_constr.limit_angle_max_x != 0:
    max_angle = b_constr.limit_angle_max_x
else:
    max_angle = 1.5
if b_constr.limit_angle_min_x != 0:
    min_angle = b_constr.limit_angle_min_x
else:
    min_angle = 0.0

# extra malleable constraint settings
if isinstance(n_bhkconstraint, NifClasses.BhkMalleableConstraint):
# unknowns
    n_bhkconstraint.unknown_int_2 = 2
n_bhkconstraint.unknown_int_3 = 1
# force required to keep bodies together
n_bhkconstraint.tau = b_constr_obj.niftools_constraint.tau
n_bhkconstraint.damping = b_constr_obj.niftools_constraint.damping

# calculate pivot point and constraint matrix
pivot = mathutils.Vector([b_constr.pivot_x,
                          b_constr.pivot_y,
                          b_constr.pivot_z]) / self.HAVOK_SCALE
constr_matrix = mathutils.Euler((b_constr.axis_x,
                                 b_constr.axis_y,
                                 b_constr.axis_z))
constr_matrix = constr_matrix.to_matrix()

# transform pivot point and constraint matrix into bhkRigidBody
# coordinates (also see import_nif.py, the
# NifImport.import_bhk_constraints method)

# the pivot point v' is in object coordinates
# however nif expects it in hkbody coordinates, v
# v * R * B = v' * O * T * B'
# with R = rigid body transform (usually unit tf)
# B = nif bone matrix
# O = blender object transform
# T = bone tail matrix (translation in Y direction)
# B' = blender bone matrix
# so we need to cancel out the object transformation by
# v = v' * O * T * B' * B^{-1} * R^{-1}

# for the rotation matrix, we transform in the same way
# but ignore all translation parts

# assume R is unit transform...

# apply object transform relative to the bone head
# (this is O * T * B' * B^{-1} at once)
transform = mathutils.Matrix(b_constr_obj.matrix_local)
# pivot = pivot * transform
constr_matrix = constr_matrix * transform.to_3x3()

# export n_bhkdescriptor pivot point
# n_bhkdescriptor.pivot_a.x = pivot[0]
# n_bhkdescriptor.pivot_a.y = pivot[1]
# n_bhkdescriptor.pivot_a.z = pivot[2]
# export n_bhkdescriptor axes and other parameters
# (also see import_nif.py NifImport.import_bhk_constraints)
axis_x = mathutils.Vector([1, 0, 0]) * constr_matrix
axis_y = mathutils.Vector([0, 1, 0]) * constr_matrix
axis_z = mathutils.Vector([0, 0, 1]) * constr_matrix

if isinstance(n_bhkdescriptor, NifClasses.BhkRagdollConstraintCInfo):
# z axis is the twist vector
    n_bhkdescriptor.twist_a.x = axis_z[0]
n_bhkdescriptor.twist_a.y = axis_z[1]
n_bhkdescriptor.twist_a.z = axis_z[2]
# x axis is the plane vector
n_bhkdescriptor.plane_a.x = axis_x[0]
n_bhkdescriptor.plane_a.y = axis_x[1]
n_bhkdescriptor.plane_a.z = axis_x[2]
# angle limits
# take them twist and plane to be 45 deg (3.14 / 4 = 0.8)

n_bhkdescriptor.plane_min_angle = b_constr.limit_angle_min_x
n_bhkdescriptor.plane_max_angle = b_constr.limit_angle_max_x

n_bhkdescriptor.cone_max_angle = b_constr.limit_angle_max_y

n_bhkdescriptor.twist_min_angle = b_constr.limit_angle_min_z
n_bhkdescriptor.twist_max_angle = b_constr.limit_angle_max_z

# same for maximum cone angle
n_bhkdescriptor.max_friction = max_friction

elif isinstance(n_bhkdescriptor, NifClasses.BhkLimitedHingeConstraintCInfo):
# y axis is the zero angle vector on the plane of rotation
n_bhkdescriptor.perp_2_axle_in_a_1.x = axis_y[0]
n_bhkdescriptor.perp_2_axle_in_a_1.y = axis_y[1]
n_bhkdescriptor.perp_2_axle_in_a_1.z = axis_y[2]
# x axis is the axis of rotation
n_bhkdescriptor.axle_a.x = axis_x[0]
n_bhkdescriptor.axle_a.y = axis_x[1]
n_bhkdescriptor.axle_a.z = axis_x[2]
# z is the remaining axis determining the positive direction of rotation
n_bhkdescriptor.perp_2_axle_in_a_2.x = axis_z[0]
n_bhkdescriptor.perp_2_axle_in_a_2.y = axis_z[1]
n_bhkdescriptor.perp_2_axle_in_a_2.z = axis_z[2]
# angle limits typically, the constraint on one side is defined by the z axis
n_bhkdescriptor.min_angle = min_angle
# the maximum axis is typically about 90 degrees
# 3.14 / 2 = 1.5
n_bhkdescriptor.max_angle = max_angle
# friction
n_bhkdescriptor.max_friction = max_friction
else:
raise ValueError(f"unknown descriptor {n_bhkdescriptor.__class__.__name__}")

# do AB
n_bhkconstraint.update_a_b(root_block)
n_bhkdescriptor.pivot_b.x = pivot[0]
n_bhkdescriptor.pivot_b.y = pivot[1]
n_bhkdescriptor.pivot_b.z = pivot[2]
'''
