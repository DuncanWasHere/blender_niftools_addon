"""Script to import constraints."""

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
from io_scene_niftools.modules.nif_import import collision
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses  # type: ignore


class Constraint:

    def __init__(self):
        self.HAVOK_SCALE = NifData.data.havok_scale

    def import_bhk_constraints(self):
        for n_bhk_rigid_body in collision.DICT_HAVOK_OBJECTS:
            self.import_constraint(n_bhk_rigid_body)

    def import_constraint(self, n_bhk_rigid_body):
        """Imports a bone havok constraint as Blender object constraint."""
        assert (isinstance(n_bhk_rigid_body, NifClasses.BhkRigidBody))

        # check for constraints
        if not n_bhk_rigid_body.constraints:
            return

        # find objects
        if not collision.DICT_HAVOK_OBJECTS[n_bhk_rigid_body]:
            NifLog.warn("Rigid body with no or multiple shapes, constraints skipped")
            return

        b_col_obj = collision.DICT_HAVOK_OBJECTS[n_bhk_rigid_body]

        NifLog.info(f"Importing constraints for {b_col_obj.name}")

        # now import all constraints
        for n_bhk_constraint in n_bhk_rigid_body.constraints:

            # check constraint 
            n_c_info = n_bhk_constraint.constraint_info
            if not n_c_info.num_entities == 2:
                NifLog.warn("Constraint with more than 2 entities, skipped")
                continue
            if not n_c_info.entity_a is n_bhk_rigid_body:
                NifLog.warn("First constraint entity not self, skipped")
                continue
            if not n_c_info.entity_b in collision.DICT_HAVOK_OBJECTS:
                NifLog.warn("Second constraint entity not imported, skipped")
                continue

            # get constraint descriptor
            n_bhk_descriptor = n_bhk_constraint.constraint
            if isinstance(n_bhk_descriptor, (NifClasses.BhkRagdollConstraintCInfo,
                                             NifClasses.BhkLimitedHingeConstraintCInfo,
                                             NifClasses.BhkHingeConstraintCInfo)):
                b_col_obj.rigid_body.enabled = True
            elif isinstance(n_bhk_descriptor, NifClasses.BhkMalleableConstraintCInfo):
                # TODO [constraint] add other types used by malleable constraint (for values 0, 1, 6 and 8)
                if n_bhk_descriptor.type == 2:
                    n_bhk_descriptor = n_bhk_descriptor.limited_hinge
                    b_col_obj.rigid_body.enabled = False
                elif n_bhk_descriptor.type == 7:
                    n_bhk_descriptor = n_bhk_descriptor.ragdoll
                    b_col_obj.rigid_body.enabled = False
                else:
                    NifLog.warn(f"Unknown malleable type ({n_bhk_constraint.type:s}), skipped")
            else:
                NifLog.warn(f"Unknown constraint type ({n_bhk_constraint.__class__.__name__}), skipped")
                continue

            # TODO: The following is no longer possible. Fix me!

            b_col_obj2 = collision.DICT_HAVOK_OBJECTS[n_bhk_constraint.constraint_info.entity_b]
            # add the constraint as a rigid body joint
            override = bpy.context.copy()
            override['active_object'] = b_col_obj
            override['selected_objects'] = b_col_obj2

            bpy.ops.rigidbody.connect(con_type='FIXED', pivot_type='CENTER', connection_pattern='SELECTED_TO_ACTIVE')

            continue

            b_constr = None
            for obj in bpy.context.scene.objects:  # Iterate over all objects
                if obj.rigid_body_constraint:  # Check for rigid body constraints
                    if obj.rigid_body_constraint.object1 == b_col_obj and obj.rigid_body_constraint.object2 == b_col_obj2:
                        b_constr = obj.rigid_body_constraint

            # note: rigidbodyjoint parameters (from Constraint.c)
            # CONSTR_RB_AXX 0.0
            # CONSTR_RB_AXY 0.0
            # CONSTR_RB_AXZ 0.0
            # CONSTR_RB_EXTRAFZ 0.0
            # CONSTR_RB_MAXLIMIT0 0.0
            # CONSTR_RB_MAXLIMIT1 0.0
            # CONSTR_RB_MAXLIMIT2 0.0
            # CONSTR_RB_MAXLIMIT3 0.0
            # CONSTR_RB_MAXLIMIT4 0.0
            # CONSTR_RB_MAXLIMIT5 0.0
            # CONSTR_RB_MINLIMIT0 0.0
            # CONSTR_RB_MINLIMIT1 0.0
            # CONSTR_RB_MINLIMIT2 0.0
            # CONSTR_RB_MINLIMIT3 0.0
            # CONSTR_RB_MINLIMIT4 0.0
            # CONSTR_RB_MINLIMIT5 0.0
            # CONSTR_RB_PIVX 0.0
            # CONSTR_RB_PIVY 0.0
            # CONSTR_RB_PIVZ 0.0
            # CONSTR_RB_TYPE 12
            # LIMIT 63
            # PARSIZEY 63
            # TARGET [Object "capsule.002"]

            # limit 3, 4, 5 correspond to angular limits along x, y and z
            # and are measured in degrees

            # pivx/y/z is the pivot point

            # set constraint target
            b_constr.object1 = collision.DICT_HAVOK_OBJECTS[n_bhk_constraint.constraint_info.entity_a]
            b_constr.object2 = collision.DICT_HAVOK_OBJECTS[n_bhk_constraint.constraint_info.entity_b]
            # set rigid body type (generic)
            b_constr.pivot_type = 'GENERIC_6_DOF'
            # limiting parameters (limit everything)
            b_constr.use_angular_limit_x = True
            b_constr.use_angular_limit_y = True
            b_constr.use_angular_limit_z = True

            # get pivot point
            pivot = mathutils.Vector((n_bhk_descriptor.pivot_b.x,
                                      n_bhk_descriptor.pivot_b.y,
                                      n_bhk_descriptor.pivot_b.z)) * self.HAVOK_SCALE

            # get z- and x-axes of the constraint
            # (also see export_nif.py NifImport.export_constraints)
            if isinstance(n_bhk_descriptor, NifClasses.BhkRagdollConstraintCInfo):
                b_constr.pivot_type = 'CONE_TWIST'
                # for ragdoll, take z to be the twist axis (central axis of the
                # cone, that is)
                axis_z = mathutils.Vector((n_bhk_descriptor.twist_a.x,
                                           n_bhk_descriptor.twist_a.y,
                                           n_bhk_descriptor.twist_a.z))
                # for ragdoll, let x be the plane vector
                axis_x = mathutils.Vector((n_bhk_descriptor.plane_a.x,
                                           n_bhk_descriptor.plane_a.y,
                                           n_bhk_descriptor.plane_a.z))
                # set the angle limits
                # (see http://niftools.sourceforge.net/wiki/Oblivion/Bhk_Objects/Ragdoll_Constraint
                # for a nice picture explaining this)
                b_constr.limit_angle_min_x = n_bhk_descriptor.plane_min_angle
                b_constr.limit_angle_max_x = n_bhk_descriptor.plane_max_angle

                b_constr.limit_angle_min_y = -n_bhk_descriptor.cone_max_angle
                b_constr.limit_angle_max_y = n_bhk_descriptor.cone_max_angle

                b_constr.limit_angle_min_z = n_bhk_descriptor.twist_min_angle
                b_constr.limit_angle_max_z = n_bhk_descriptor.twist_max_angle

                b_col_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.max_friction

            elif isinstance(n_bhk_descriptor, NifClasses.BhkLimitedHingeConstraintCInfo):
                # for hinge, y is the vector on the plane of rotation defining
                # the zero angle
                axis_y = mathutils.Vector((n_bhk_descriptor.perp_2_axle_in_a_1.x,
                                           n_bhk_descriptor.perp_2_axle_in_a_1.y,
                                           n_bhk_descriptor.perp_2_axle_in_a_1.z))
                # for hinge, take x to be the the axis of rotation
                # (this corresponds with Blender's convention for hinges)
                axis_x = mathutils.Vector((n_bhk_descriptor.axle_a.x,
                                           n_bhk_descriptor.axle_a.y,
                                           n_bhk_descriptor.axle_a.z))
                # for hinge, z is the vector on the plane of rotation defining
                # the positive direction of rotation
                axis_z = mathutils.Vector((n_bhk_descriptor.perp_2_axle_in_a_2.x,
                                           n_bhk_descriptor.perp_2_axle_in_a_2.y,
                                           n_bhk_descriptor.perp_2_axle_in_a_2.z))
                # they should form a orthogonal basis
                if (mathutils.Vector.cross(axis_x, axis_y) - axis_z).length > 0.01:
                    # either not orthogonal, or negative orientation
                    if (mathutils.Vector.cross(-axis_x, axis_y) - axis_z).length > 0.01:
                        NifLog.warn(
                            f"Axes are not orthogonal in {n_bhk_descriptor.__class__.__name__}; Arbitrary orientation has been chosen")
                        axis_z = mathutils.Vector.cross(axis_x, axis_y)
                    else:
                        # fix orientation
                        NifLog.warn(f"X axis flipped in {n_bhk_descriptor.__class__.__name__} to fix orientation")
                        axis_x = -axis_x
                # getting properties with no blender constraint equivalent and setting as obj properties
                b_constr.limit_angle_max_x = n_bhk_descriptor.max_angle
                b_constr.limit_angle_min_x = n_bhk_descriptor.min_angle
                b_col_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.max_friction

                if hasattr(n_bhk_constraint, "tau"):
                    b_col_obj.niftools_constraint.tau = n_bhk_constraint.tau
                    b_col_obj.niftools_constraint.damping = n_bhk_constraint.damping

            elif isinstance(n_bhk_descriptor, NifClasses.HingeDescriptor):
                # for hinge, y is the vector on the plane of rotation defining
                # the zero angle
                axis_y = mathutils.Vector((n_bhk_descriptor.perp_2_axle_in_a_1.x,
                                           n_bhk_descriptor.perp_2_axle_in_a_1.y,
                                           n_bhk_descriptor.perp_2_axle_in_a_1.z))
                # for hinge, z is the vector on the plane of rotation defining
                # the positive direction of rotation
                axis_z = mathutils.Vector((n_bhk_descriptor.perp_2_axle_in_a_2.x,
                                           n_bhk_descriptor.perp_2_axle_in_a_2.y,
                                           n_bhk_descriptor.perp_2_axle_in_a_2.z))
                # take x to be the the axis of rotation
                # (this corresponds with Blender's convention for hinges)
                axis_x = mathutils.Vector.cross(axis_y, axis_z)
                b_col_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.max_friction
            else:
                raise ValueError(f"Unknown descriptor {n_bhk_descriptor.__class__.__name__}")

            # transform pivot point and constraint matrix into object
            # coordinates
            # (also see export_nif.py NifImport.export_constraints)

            # the pivot point v is in hkbody coordinates
            # however blender expects it in object coordinates, v'
            # v * R * B = v' * O * T * B'
            # with R = rigid body transform (usually unit tf)
            # B = nif bone matrix
            # O = blender object transform
            # T = bone tail matrix (translation in Y direction)
            # B' = blender bone matrix
            # so we need to cancel out the object transformation by
            # v' = v * R * B * B'^{-1} * T^{-1} * O^{-1}

            # the local rotation L at the pivot point must be such that
            # (axis_z + v) * R * B = ([0 0 1] * L + v') * O * T * B'
            # so (taking the rotation parts of all matrices!!!)
            # [0 0 1] * L = axis_z * R * B * B'^{-1} * T^{-1} * O^{-1}
            # and similarly
            # [1 0 0] * L = axis_x * R * B * B'^{-1} * T^{-1} * O^{-1}
            # hence these give us the first and last row of L
            # which is exactly enough to provide the euler angles

            # multiply with rigid body transform
            if isinstance(n_bhk_rigid_body, NifClasses.BhkRigidBodyT):
                # set rotation
                transform = mathutils.Quaternion((n_bhk_rigid_body.rotation.w,
                                                  n_bhk_rigid_body.rotation.x,
                                                  n_bhk_rigid_body.rotation.y,
                                                  n_bhk_rigid_body.rotation.z)).to_matrix()
                transform.resize_4x4()
                # set translation
                transform[0][3] = n_bhk_rigid_body.translation.x * self.HAVOK_SCALE
                transform[1][3] = n_bhk_rigid_body.translation.y * self.HAVOK_SCALE
                transform[2][3] = n_bhk_rigid_body.translation.z * self.HAVOK_SCALE
                # apply transform
                # pivot = pivot * transform
                transform = transform.to_3x3()
                axis_z = axis_z * transform
                axis_x = axis_x * transform

            # TODO [armature] update this to use the new bone system
            # next, cancel out bone matrix correction
            # note that B' = X * B with X = self.nif_import.dict_bones_extra_matrix[B]
            # so multiply with the inverse of X
            # for niBone in self.nif_import.dict_bones_extra_matrix:
            # if niBone.collision_object \
            # and niBone.collision_object.body is hkbody:
            # transform = mathutils.Matrix(
            # self.nif_import.dict_bones_extra_matrix[niBone])
            # transform.invert()
            # pivot = pivot * transform
            # transform = transform.to_3x3()
            # axis_z = axis_z * transform
            # axis_x = axis_x * transform
            # break

            # # cancel out bone tail translation
            # if b_hkobj.parent_bone:
            #     pivot[1] -= b_hkobj.parent.data.bones[
            #         b_hkobj.parent_bone].length

            # cancel out object transform
            transform = mathutils.Matrix(b_col_obj.matrix_local)
            transform.invert()
            # pivot = pivot * transform
            transform = transform.to_3x3()
            axis_z = axis_z * transform
            axis_x = axis_x * transform

            # set pivot point
            b_constr.pivot_x = pivot[0]
            b_constr.pivot_y = pivot[1]
            b_constr.pivot_z = pivot[2]

            # set euler angles
            constr_matrix = mathutils.Matrix((axis_x,
                                              mathutils.Vector.cross(axis_z, axis_x),
                                              axis_z))
            constr_euler = constr_matrix.to_euler()
            b_constr.axis_x = constr_euler.x
            b_constr.axis_y = constr_euler.y
            b_constr.axis_z = constr_euler.z
            # DEBUG
            assert ((axis_x - mathutils.Vector((1, 0, 0)) * constr_matrix).length < 0.0001)
            assert ((axis_z - mathutils.Vector((0, 0, 1)) * constr_matrix).length < 0.0001)

            # the generic rigid body type is very buggy... so for simulation purposes let's transform it into ball and hinge
            if isinstance(n_bhk_descriptor, NifClasses.BhkRagdollConstraintCInfo):
                # cone_twist
                b_constr.pivot_type = 'CONE_TWIST'
            elif isinstance(n_bhk_descriptor, (NifClasses.BhkLimitedHingeConstraintCInfo, NifClasses.HingeDescriptor)):
                # (limited) hinge
                b_constr.pivot_type = 'HINGE'
            else:
                raise ValueError(f"Unknown descriptor {n_bhk_descriptor.__class__.__name__}")
