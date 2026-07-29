"""This script contains classes to import havok constraints."""

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


import json

import bpy
import mathutils
from ....modules.nif_import import collision
from ....modules.nif_import.object import Object
from ....utils import serialization
from ....utils.logging import NifLog
from ....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses  # type: ignore


class Constraint:

    # hkConstraintType member names mapped to the closest Blender rigid body constraint types
    KIND_BLENDER_TYPES = {
        "BALL_AND_SOCKET": 'POINT',
        "HINGE": 'HINGE',
        "LIMITED_HINGE": 'HINGE',
        "PRISMATIC": 'SLIDER',
        "RAGDOLL": 'GENERIC',
        "STIFF_SPRING": 'GENERIC_SPRING',
    }

    def __init__(self):
        self.HAVOK_SCALE = NifData.data.havok_scale

    def import_bhk_constraints(self):
        # make sure the world matrices of the freshly imported collision objects are up to date
        bpy.context.view_layer.update()
        for n_bhk_rigid_body in collision.DICT_HAVOK_OBJECTS:
            self.import_constraint(n_bhk_rigid_body)

    def import_constraint(self, n_bhk_rigid_body):
        """Imports the constraints of a bhkRigidBody as Blender rigid body constraint objects."""
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

            # the list also holds the body's havok actions, which are bhkSerializables
            # rather than constraints and have no entities of their own
            if isinstance(n_bhk_constraint, NifClasses.BhkAction):
                self.import_havok_action(n_bhk_constraint, b_col_obj)
                continue

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
            b_col_obj_b = collision.DICT_HAVOK_OBJECTS[n_c_info.entity_b]
            if not b_col_obj_b:
                NifLog.warn("Second constraint entity has no imported shape, skipped")
                continue

            self.import_bhk_constraint(n_bhk_constraint, b_col_obj, b_col_obj_b)

    @staticmethod
    def import_havok_action(n_bhk_action, b_col_obj):
        """Import a havok action held in a rigid body's constraints list."""

        nif_action = b_col_obj.nif_havok_action

        if isinstance(n_bhk_action, NifClasses.BhkLiquidAction):
            nif_action.use_liquid_action = True
            nif_action.initial_stick_force = n_bhk_action.initial_stick_force
            nif_action.stick_strength = n_bhk_action.stick_strength
            nif_action.neighbor_distance = n_bhk_action.neighbor_distance
            nif_action.neighbor_strength = n_bhk_action.neighbor_strength

        elif isinstance(n_bhk_action, NifClasses.BhkOrientHingedBodyAction):
            nif_action.use_orient_hinged_body_action = True
            n_hinge_axis = n_bhk_action.hinge_axis_ls
            nif_action.hinge_axis_ls = (n_hinge_axis.x, n_hinge_axis.y, n_hinge_axis.z)
            n_forward = n_bhk_action.forward_ls
            nif_action.forward_ls = (n_forward.x, n_forward.y, n_forward.z)
            nif_action.strength = n_bhk_action.strength
            nif_action.damping = n_bhk_action.damping

        else:
            NifLog.warn(f"Unsupported havok action type "
                        f"({type(n_bhk_action).__name__}) on '{b_col_obj.name}', skipped.")

    def import_bhk_constraint(self, n_bhk_constraint, b_col_obj_a, b_col_obj_b):
        """Imports a single bhkConstraint linking two imported collision objects as an empty
        with a Blender rigid body constraint, and stores the full havok constraint data on it."""

        kind, n_bhk_descriptor = serialization.get_constraint_descriptor(n_bhk_constraint)
        if kind is None:
            NifLog.warn(f"Unknown constraint type ({type(n_bhk_constraint).__name__}), skipped")
            return

        # create an empty to hold the constraint, parented to the first entity
        b_con_obj = Object.create_b_obj(None, None, f"constraint_{b_col_obj_a.name}")
        b_con_obj.empty_display_type = 'ARROWS'
        b_con_obj.empty_display_size = 0.5
        # create_b_obj makes the empty the active object, which the constraint operator works on
        if not bpy.context.scene.rigidbody_world:
            bpy.ops.rigidbody.world_add()
        bpy.ops.rigidbody.constraint_add()
        b_constr = b_con_obj.rigid_body_constraint

        b_constr.object1 = b_col_obj_a
        b_constr.object2 = b_col_obj_b
        b_constr.type = self.KIND_BLENDER_TYPES[kind]

        # position the empty at the constraint pivot, oriented along the constraint axes,
        # matching the axis conventions of the Blender constraint types
        # (hinges rotate around Z, sliders move along X)
        if kind == "RAGDOLL":
            axis_z = self.vector_from_field(n_bhk_descriptor.twist_a)
            axis_x = self.vector_from_field(n_bhk_descriptor.plane_a)
        elif kind in ("HINGE", "LIMITED_HINGE"):
            axis_z = self.vector_from_field(n_bhk_descriptor.axis_a)
            axis_x = self.vector_from_field(n_bhk_descriptor.perp_axis_in_a_1)
            if axis_z.length < 0.5:
                # oblivion layout has no explicit hinge axis, derive it from the perpendicular pair
                axis_z = self.vector_from_field(n_bhk_descriptor.perp_axis_in_a_1).cross(
                    self.vector_from_field(n_bhk_descriptor.perp_axis_in_a_2))
                axis_x = self.vector_from_field(n_bhk_descriptor.perp_axis_in_a_2)
        elif kind == "PRISMATIC":
            axis_x = self.vector_from_field(n_bhk_descriptor.sliding_a)
            axis_z = self.vector_from_field(n_bhk_descriptor.plane_a)
        else:
            # ball and socket / stiff spring constraints have no meaningful axes
            axis_z = mathutils.Vector((0, 0, 1))
            axis_x = mathutils.Vector((1, 0, 0))

        pivot = self.vector_from_field(n_bhk_descriptor.pivot_a) * self.HAVOK_SCALE
        b_con_obj.parent = b_col_obj_a
        b_con_obj.matrix_parent_inverse = b_col_obj_a.matrix_world.inverted()
        b_con_obj.matrix_basis = b_col_obj_a.matrix_world @ self.compose_matrix(pivot, axis_x, axis_z)

        # transfer the values blender constraints can represent
        if kind == "RAGDOLL":
            b_constr.use_limit_ang_x = True
            b_constr.limit_ang_x_lower = n_bhk_descriptor.plane_min_angle
            b_constr.limit_ang_x_upper = n_bhk_descriptor.plane_max_angle
            b_constr.use_limit_ang_y = True
            b_constr.limit_ang_y_lower = -n_bhk_descriptor.cone_max_angle
            b_constr.limit_ang_y_upper = n_bhk_descriptor.cone_max_angle
            b_constr.use_limit_ang_z = True
            b_constr.limit_ang_z_lower = n_bhk_descriptor.twist_min_angle
            b_constr.limit_ang_z_upper = n_bhk_descriptor.twist_max_angle
            b_con_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.max_friction
        elif kind == "LIMITED_HINGE":
            b_constr.use_limit_ang_z = True
            b_constr.limit_ang_z_lower = n_bhk_descriptor.min_angle
            b_constr.limit_ang_z_upper = n_bhk_descriptor.max_angle
            b_con_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.max_friction
        elif kind == "PRISMATIC":
            b_constr.use_limit_lin_x = True
            b_constr.limit_lin_x_lower = n_bhk_descriptor.min_distance * self.HAVOK_SCALE
            b_constr.limit_lin_x_upper = n_bhk_descriptor.max_distance * self.HAVOK_SCALE
            b_con_obj.niftools_constraint.LHMaxFriction = n_bhk_descriptor.friction

        # transfer wrapper block values
        if isinstance(n_bhk_constraint, NifClasses.BhkBreakableConstraint):
            b_constr.use_breaking = True
            b_constr.breaking_threshold = n_bhk_constraint.threshold
        elif isinstance(n_bhk_constraint, NifClasses.BhkMalleableConstraint):
            n_c_info = n_bhk_constraint.constraint
            # newer nif versions store strength instead of tau and damping
            malleable_fields = [name for name, *_ in type(n_c_info)._get_filtered_attribute_list(n_c_info)]
            if "tau" in malleable_fields:
                b_con_obj.niftools_constraint.tau = n_c_info.tau
                b_con_obj.niftools_constraint.damping = n_c_info.damping

        # store the full havok constraint data so it survives the round trip to blender
        b_con_obj.niftools_constraint.data = json.dumps({
            "block_type": type(n_bhk_constraint).__name__,
            "fields": serialization.struct_to_dict(n_bhk_constraint),
        })

    @staticmethod
    def vector_from_field(n_vector):
        return mathutils.Vector((n_vector.x, n_vector.y, n_vector.z))

    @staticmethod
    def compose_matrix(pivot, axis_x, axis_z):
        """Build a transform matrix from a pivot point and the x and z axes of the constraint."""
        if axis_z.length < 0.5 or axis_x.length < 0.5:
            NifLog.warn("Constraint axes are degenerate, using identity orientation")
            axis_z = mathutils.Vector((0, 0, 1))
            axis_x = mathutils.Vector((1, 0, 0))
        axis_z = axis_z.normalized()
        # make x orthogonal to z in case the descriptor axes aren't exactly orthogonal
        axis_x = (axis_x - axis_x.project(axis_z)).normalized()
        axis_y = axis_z.cross(axis_x)
        matrix = mathutils.Matrix.Identity(4)
        matrix.col[0].xyz = axis_x
        matrix.col[1].xyz = axis_y
        matrix.col[2].xyz = axis_z
        matrix.translation = pivot
        return matrix
