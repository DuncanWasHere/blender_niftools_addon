"""Main module for exporting Havok constraint blocks."""

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


from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.constraint.havok.common import ConstraintCommon
from io_scene_niftools.modules.nif_export.object import DICT_NAMES
from io_scene_niftools.utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


class BhkConstraint(ConstraintCommon):
    """
    Main interface class for exporting Havok constraint blocks
    (i.e., bhkConstraint subclasses).
    For Bethesda games (except Morrowind) ONLY!
    """

    def export_bhk_constraint(self, b_constr, b_constr_obj, ):

        # Ensure constraint target objects will be exported as valid collision objects
        if not b_constr.object1 and not b_constr.object2:
            NifLog.warn(f"Constraint {b_constr_obj.name} is missing one or both target objects. "
                        f"It will not be exported")
            return
        if not b_constr.object1.rigid_body and not b_constr.object2.rigid_body:
            NifLog.warn(f"Constraint {b_constr_obj.name} has target objects without rigid bodies. "
                        f"It will not be exported")
            return

        # Get target rigid bodies from object dictionary
        n_entity_a = DICT_NAMES[b_constr.object1.name]
        n_entity_b = DICT_NAMES[b_constr.object2.name]

        # Find constraint type and call export method
        n_bhk_constraint = None
        if b_constr.use_breaking:
            n_bhk_constraint = self.export_bhk_breakable_constraint(b_constr,
                                                                    b_constr_obj,
                                                                    n_entity_a,
                                                                    n_entity_b)
        elif b_constr.type == 'HINGE':
            if b_constr.use_limit_ang_z:
                n_bhk_constraint = self.export_bhk_limited_hinge_constraint(b_constr,
                                                                            b_constr_obj,
                                                                            n_entity_a,
                                                                            n_entity_b)
            else:
                n_bhk_constraint = self.export_bhk_hinge_constraint(b_constr,
                                                                    b_constr_obj,
                                                                    n_entity_a,
                                                                    n_entity_b)
        elif b_constr.type == 'SLIDER':
            n_bhk_constraint = self.export_bhk_prismatic_constraint(b_constr,
                                                                    b_constr_obj,
                                                                    n_entity_a,
                                                                    n_entity_b)
        elif b_constr.type == 'POINT':
            n_bhk_constraint = self.export_bhk_ball_and_socket_constraint(b_constr,
                                                                          b_constr_obj,
                                                                          n_entity_a,
                                                                          n_entity_b)
        elif b_constr.type == 'GENERIC_SPRING':
            n_bhk_constraint = self.export_bhk_stiff_spring_constraint(b_constr,
                                                                       b_constr_obj,
                                                                       n_entity_a,
                                                                       n_entity_b)
        elif b_constr.type == 'GENERIC':
            n_bhk_constraint = self.export_bhk_ragdoll_constraint(b_constr,
                                                                  b_constr_obj,
                                                                  n_entity_a,
                                                                  n_entity_b)
        else:
            NifLog.warn(f"Constraint {b_constr_obj.name} has an unsupported type ({b_constr.type})."
                        f"It will not be exported")
            return

    def export_bhk_ball_and_socket_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_ball_and_socket_constraint = block_store.create_block("bhkBallAndSocketConstraint")
        ConstraintCommon.attach_constraint(n_bhk_ball_and_socket_constraint, n_entity_a, n_entity_b)

        (n_bhk_ball_and_socket_constraint.constraint.pivot_a,
         n_bhk_ball_and_socket_constraint.constraint.pivot_b) = self.calculate_pivot(b_constr, b_constr_obj)

        return n_bhk_ball_and_socket_constraint

    def export_bhk_ragdoll_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_ragdoll_constraint = block_store.create_block("bhkRagdollConstraint")
        ConstraintCommon.attach_constraint(n_bhk_ragdoll_constraint, n_entity_a, n_entity_b)

        (n_bhk_ragdoll_constraint.constraint.twist_a,
         n_bhk_ragdoll_constraint.constraint.twist_b) = self.calculate_twist(b_constr, b_constr_obj,
                                                                             n_entity_a, n_entity_b)

        (n_bhk_ragdoll_constraint.constraint.plane_a,
         n_bhk_ragdoll_constraint.constraint.plane_b) = self.calculate_plane(b_constr, b_constr_obj,
                                                                             n_entity_a)

        (n_bhk_ragdoll_constraint.constraint.motor_a,
         n_bhk_ragdoll_constraint.constraint.motor_b) = self.calculate_motor(b_constr, b_constr_obj,
                                                                             n_entity_a)

        (n_bhk_ragdoll_constraint.constraint.pivot_a,
         n_bhk_ragdoll_constraint.constraint.pivot_b) = self.calculate_pivot(b_constr, b_constr_obj)

        (n_bhk_ragdoll_constraint.constraint.cone_max_angle) = self.calculate_cone_angle(b_constr, b_constr_obj,
                                                                                         n_entity_a)

        (n_bhk_ragdoll_constraint.constraint.plane_min_angle,
         n_bhk_ragdoll_constraint.constraint.plane_max_angle) = self.calculate_plane_angle(b_constr, b_constr_obj,
                                                                                           n_entity_a)

        (n_bhk_ragdoll_constraint.constraint.twist_min_angle,
         n_bhk_ragdoll_constraint.constraint.twist_max_angle) = self.calculate_twist_angle(b_constr, b_constr_obj,
                                                                                           n_entity_a)

        return n_bhk_ragdoll_constraint

    def export_bhk_hinge_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_hinge_constraint = block_store.create_block("bhkHingeConstraint")
        ConstraintCommon.attach_constraint(n_bhk_hinge_constraint, n_entity_a, n_entity_b)

        return n_bhk_hinge_constraint

    def export_bhk_limited_hinge_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_limited_hinge_constraint = block_store.create_block("bhkLimitedHingeConstraint")
        ConstraintCommon.attach_constraint(n_bhk_limited_hinge_constraint, n_entity_a, n_entity_b)

        return n_bhk_limited_hinge_constraint

    def export_bhk_prismatic_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_prismatic_constraint = block_store.create_block("bhkPrismaticConstraint")
        ConstraintCommon.attach_constraint(n_bhk_prismatic_constraint, n_entity_a, n_entity_b)

        return n_bhk_prismatic_constraint

    def export_bhk_stiff_spring_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_stiff_spring_constraint = block_store.create_block("bhkStiffSpringConstraint")
        ConstraintCommon.attach_constraint(n_bhk_stiff_spring_constraint, n_entity_a, n_entity_b)

        return n_bhk_stiff_spring_constraint

    def export_bhk_malleable_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_malleable_constraint = block_store.create_block("bhkMalleableConstraint")
        ConstraintCommon.attach_constraint(n_bhk_malleable_constraint, n_entity_a, n_entity_b)

        return n_bhk_malleable_constraint

    def export_bhk_breakable_constraint(self, b_constr, b_constr_obj, n_entity_a, n_entity_b):
        n_bhk_breakable_constraint = block_store.create_block("bhkBreakableConstraint")
        ConstraintCommon.attach_constraint(n_bhk_breakable_constraint, n_entity_a, n_entity_b)

        n_bhk_breakable_constraint.threshold = b_constr.threshold

        if b_constr.type == 'HINGE':
            if b_constr.use_limit_ang_z:
                n_constraint_type = NifClasses.HkConstraintType['HINGE']
                n_wrapped_constraint = self.export_bhk_limited_hinge_constraint(b_constr, b_constr_obj)

                n_bhk_breakable_constraint.constraint_data.hinge.axis_a = (
                    n_wrapped_constraint.constraint.axis_a)

                n_bhk_breakable_constraint.constraint_data.hinge.perp_axis_in_a_1 = (
                    n_wrapped_constraint.constraint.perp_axis_in_a_1)

                n_bhk_breakable_constraint.constraint_data.hinge.perp_axis_in_a_2 = (
                    n_wrapped_constraint.constraint.perp_axis_in_a_2)

                n_bhk_breakable_constraint.constraint_data.hinge.pivot_a = (
                    n_wrapped_constraint.constraint.pivot_a)

                n_bhk_breakable_constraint.constraint_data.hinge.axis_b = (
                    n_wrapped_constraint.constraint.axis_b)

                n_bhk_breakable_constraint.constraint_data.hinge.perp_axis_in_b_1 = (
                    n_wrapped_constraint.constraint.perp_axis_in_b_1)

                n_bhk_breakable_constraint.constraint_data.hinge.perp_axis_in_b_2 = (
                    n_wrapped_constraint.constraint.perp_axis_in_b_2)

                n_bhk_breakable_constraint.constraint_data.hinge.pivot_b = (
                    n_wrapped_constraint.constraint.pivot_b)

            else:
                n_constraint_type = NifClasses.HkConstraintType['LIMITED_HINGE']
                n_wrapped_constraint = self.export_bhk_hinge_constraint(b_constr, b_constr_obj)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.axis_a = (
                    n_wrapped_constraint.constraint.axis_a)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.perp_axis_in_a_1 = (
                    n_wrapped_constraint.constraint.perp_axis_in_a_1)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.perp_axis_in_a_2 = (
                    n_wrapped_constraint.constraint.perp_axis_in_a_2)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.pivot_a = (
                    n_wrapped_constraint.constraint.pivot_a)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.axis_b = (
                    n_wrapped_constraint.constraint.axis_b)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.perp_axis_in_b_1 = (
                    n_wrapped_constraint.constraint.perp_axis_in_b_1)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.perp_axis_in_b_2 = (
                    n_wrapped_constraint.constraint.perp_axis_in_b_2)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.pivot_b = (
                    n_wrapped_constraint.constraint.pivot_b)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.min_angle = (
                    n_wrapped_constraint.constraint.min_angle)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.max_angle = (
                    n_wrapped_constraint.constraint.max_angle)

                n_bhk_breakable_constraint.constraint_data.limited_hinge.max_friction = (
                    n_wrapped_constraint.constraint.max_friction)

        elif b_constr.type == 'SLIDER':
            n_constraint_type = NifClasses.HkConstraintType['PRISMATIC']
            n_wrapped_constraint = self.export_bhk_prismatic_constraint(b_constr, b_constr_obj)

            n_bhk_breakable_constraint.constraint_data.prismatic.sliding_a = (
                n_wrapped_constraint.constraint.sliding_a)

            n_bhk_breakable_constraint.constraint_data.prismatic.rotation_a = (
                n_wrapped_constraint.constraint.rotation_a)

            n_bhk_breakable_constraint.constraint_data.prismatic.plane_a = (
                n_wrapped_constraint.constraint.plane_a)

            n_bhk_breakable_constraint.constraint_data.prismatic.pivot_a = (
                n_wrapped_constraint.constraint.pivot_a)

            n_bhk_breakable_constraint.constraint_data.prismatic.sliding_b = (
                n_wrapped_constraint.constraint.sliding_b)

            n_bhk_breakable_constraint.constraint_data.prismatic.rotation_b = (
                n_wrapped_constraint.constraint.rotation_b)

            n_bhk_breakable_constraint.constraint_data.prismatic.plane_b = (
                n_wrapped_constraint.constraint.plane_b)

            n_bhk_breakable_constraint.constraint_data.prismatic.pivot_b = (
                n_wrapped_constraint.constraint.pivot_b)

            n_bhk_breakable_constraint.constraint_data.prismatic.min_distance = (
                n_wrapped_constraint.constraint.min_distance)

            n_bhk_breakable_constraint.constraint_data.prismatic.max_distance = (
                n_wrapped_constraint.constraint.max_distance)

            n_bhk_breakable_constraint.constraint_data.prismatic.friction = (
                n_wrapped_constraint.constraint.friction)

        elif b_constr.type == 'POINT':
            n_constraint_type = NifClasses.HkConstraintType['BALL_AND_SOCKET']
            n_wrapped_constraint = self.export_bhk_ball_and_socket_constraint(b_constr, b_constr_obj)

            n_bhk_breakable_constraint.constraint_data.ball_and_socket.pivot_a = (
                n_wrapped_constraint.constraint.pivot_a)

            n_bhk_breakable_constraint.constraint_data.ball_and_socket.pivot_b = (
                n_wrapped_constraint.constraint.pivot_b)

        elif b_constr.type == 'GENERIC_SPRING':
            n_constraint_type = NifClasses.HkConstraintType['STIFF_SPRING']
            n_wrapped_constraint = self.export_bhk_stiff_spring_constraint(b_constr, b_constr_obj)

            n_bhk_breakable_constraint.constraint_data.stiff_spring.pivot_a = (
                n_wrapped_constraint.constraint.pivot_a)

            n_bhk_breakable_constraint.constraint_data.stiff_spring.pivot_b = (
                n_wrapped_constraint.constraint.pivot_b)

            n_bhk_breakable_constraint.constraint_data.ball_and_socket.length = (
                n_wrapped_constraint.constraint.length)

        elif b_constr.type == 'GENERIC':
            n_constraint_type = NifClasses.HkConstraintType['RAGDOLL']
            n_wrapped_constraint = self.export_bhk_ragdoll_constraint(b_constr, b_constr_obj)

            n_bhk_breakable_constraint.constraint_data.ragdoll.twist_a = (
                n_wrapped_constraint.constraint.twist_a)

            n_bhk_breakable_constraint.constraint_data.ragdoll.plane_a = (
                n_wrapped_constraint.constraint.plane_a)

            n_bhk_breakable_constraint.constraint_data.ragdoll.pivot_a = (
                n_wrapped_constraint.constraint.pivot_a)

            n_bhk_breakable_constraint.constraint_data.ragdoll.motor_a = (
                n_wrapped_constraint.constraint.motor_a)

            n_bhk_breakable_constraint.constraint_data.ragdoll.twist_b = (
                n_wrapped_constraint.constraint.pivot_b)

            n_bhk_breakable_constraint.constraint_data.ragdoll.plane_b = (
                n_wrapped_constraint.constraint.plane_b)

            n_bhk_breakable_constraint.constraint_data.ragdoll.pivot_b = (
                n_wrapped_constraint.constraint.pivot_b)

            n_bhk_breakable_constraint.constraint_data.ragdoll.motor_b = (
                n_wrapped_constraint.constraint.motor_b)

            n_bhk_breakable_constraint.constraint_data.ragdoll.cone_max_angle = (
                n_wrapped_constraint.constraint.cone_max_angle)

            n_bhk_breakable_constraint.constraint_data.ragdoll.plane_min_angle = (
                n_wrapped_constraint.constraint.plane_min_angle)

            n_bhk_breakable_constraint.constraint_data.ragdoll.plane_max_angle = (
                n_wrapped_constraint.constraint.plane_max_angle)

            n_bhk_breakable_constraint.constraint_data.ragdoll.twist_min_angle = (
                n_wrapped_constraint.constraint.twist_min_angle)

            n_bhk_breakable_constraint.constraint_data.ragdoll.twist_max_angle = (
                n_wrapped_constraint.constraint.twist_max_angle)

            n_bhk_breakable_constraint.constraint_data.ragdoll.max_friction = (
                n_wrapped_constraint.constraint.max_friction)

        else:
            NifLog.warn(f"Constraint {b_constr_obj.name} has an unsupported type ({b_constr.type})."
                        f"It will not be exported")

        n_bhk_breakable_constraint.constraint_data.type = n_constraint_type

        return n_bhk_breakable_constraint