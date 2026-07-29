"""Main module for exporting Havok constraint blocks."""

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

from .....modules.nif_export.block_registry import block_store
from .....utils import serialization
from .....utils.logging import NifLog
from .....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BhkConstraint:
    """
    Main interface class for exporting Havok constraint blocks
    (i.e., bhkConstraint subclasses).
    For Bethesda games (except Morrowind) ONLY!
    """

    # Blender rigid body constraint types mapped to hkConstraintType member names
    BLENDER_TYPE_KINDS = {
        'POINT': "BALL_AND_SOCKET",
        'HINGE': "HINGE",  # LIMITED_HINGE when its angular limit is enabled
        'SLIDER': "PRISMATIC",
        'GENERIC': "RAGDOLL",
        'GENERIC_SPRING': "STIFF_SPRING",
    }

    # hkConstraintType member names mapped to bhkConstraint block types
    KIND_BLOCK_TYPES = {
        "BALL_AND_SOCKET": "bhkBallAndSocketConstraint",
        "HINGE": "bhkHingeConstraint",
        "LIMITED_HINGE": "bhkLimitedHingeConstraint",
        "PRISMATIC": "bhkPrismaticConstraint",
        "RAGDOLL": "bhkRagdollConstraint",
        "STIFF_SPRING": "bhkStiffSpringConstraint",
    }

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
        # NifData is not initialized yet when the helper is constructed
        self.HAVOK_SCALE = None

    def export_bhk_constraint(self, b_constr, b_constr_obj, root_node):
        self.HAVOK_SCALE = NifData.data.havok_scale

        # Ensure constraint target objects will be exported as valid collision objects
        if not b_constr.object1 or not b_constr.object2:
            NifLog.warn(f"Constraint {b_constr_obj.name} is missing one or both target objects. "
                        f"It will not be exported")
            return
        if not (b_constr.object1.rigid_body and b_constr.object2.rigid_body):
            NifLog.warn(f"Constraint {b_constr_obj.name} has target objects without rigid bodies. "
                        f"It will not be exported")
            return

        # Get target rigid bodies from the block registry
        n_entity_a = block_store.obj_to_block.get(b_constr.object1)
        n_entity_b = block_store.obj_to_block.get(b_constr.object2)
        if not isinstance(n_entity_a, NifClasses.BhkRigidBody) or not isinstance(n_entity_b, NifClasses.BhkRigidBody):
            NifLog.warn(f"Constraint {b_constr_obj.name} targets objects that were not exported "
                        f"as rigid bodies. It will not be exported")
            return

        # Restore the stored havok data if the constraint was imported from a nif,
        # otherwise derive everything from the Blender constraint
        stored = b_constr_obj.niftools_constraint.data
        n_bhk_constraint = None
        if stored:
            try:
                n_bhk_constraint = self.export_stored_constraint(json.loads(stored), b_constr, b_constr_obj)
            except (KeyError, ValueError):
                NifLog.warn(f"Stored havok data on constraint {b_constr_obj.name} could not be read. "
                            f"Exporting from the Blender constraint values instead")
        if not n_bhk_constraint:
            n_bhk_constraint = self.export_blender_constraint(b_constr, b_constr_obj)
        if not n_bhk_constraint:
            return

        self.attach_constraint(n_bhk_constraint, n_entity_a, n_entity_b)
        return n_bhk_constraint

    def export_stored_constraint(self, stored, b_constr, b_constr_obj):
        """Rebuild a bhkConstraint block from the havok data stored on import."""
        n_bhk_constraint = block_store.create_block(stored["block_type"], b_constr_obj)
        serialization.dict_to_struct(n_bhk_constraint, stored["fields"])
        self.apply_blender_values(n_bhk_constraint, b_constr, b_constr_obj)
        return n_bhk_constraint

    def apply_blender_values(self, n_bhk_constraint, b_constr, b_constr_obj):
        """Write the constraint values that are editable in Blender back into the restored havok data."""
        if isinstance(n_bhk_constraint, NifClasses.BhkBreakableConstraint) and b_constr.use_breaking:
            n_bhk_constraint.threshold = b_constr.breaking_threshold
        if isinstance(n_bhk_constraint, NifClasses.BhkMalleableConstraint):
            n_c_info = n_bhk_constraint.constraint
            # newer nif versions store strength instead of tau and damping
            malleable_fields = [name for name, *_ in type(n_c_info)._get_filtered_attribute_list(n_c_info)]
            if "tau" in malleable_fields:
                n_c_info.tau = b_constr_obj.niftools_constraint.tau
                n_c_info.damping = b_constr_obj.niftools_constraint.damping

        kind, n_bhk_descriptor = serialization.get_constraint_descriptor(n_bhk_constraint)
        if kind is None:
            return
        # only transfer values if the blender constraint still has the type the data was imported as
        if b_constr.type != self.KIND_BLENDER_TYPES[kind]:
            NifLog.warn(f"Type of Blender constraint {b_constr_obj.name} does not match its stored "
                        f"havok data ({kind}). The stored data will be exported unchanged")
            return

        if kind == "RAGDOLL":
            if b_constr.use_limit_ang_x:
                n_bhk_descriptor.plane_min_angle = b_constr.limit_ang_x_lower
                n_bhk_descriptor.plane_max_angle = b_constr.limit_ang_x_upper
            if b_constr.use_limit_ang_y:
                n_bhk_descriptor.cone_max_angle = b_constr.limit_ang_y_upper
            if b_constr.use_limit_ang_z:
                n_bhk_descriptor.twist_min_angle = b_constr.limit_ang_z_lower
                n_bhk_descriptor.twist_max_angle = b_constr.limit_ang_z_upper
            n_bhk_descriptor.max_friction = b_constr_obj.niftools_constraint.LHMaxFriction
        elif kind == "LIMITED_HINGE":
            if b_constr.use_limit_ang_z:
                n_bhk_descriptor.min_angle = b_constr.limit_ang_z_lower
                n_bhk_descriptor.max_angle = b_constr.limit_ang_z_upper
            n_bhk_descriptor.max_friction = b_constr_obj.niftools_constraint.LHMaxFriction
        elif kind == "PRISMATIC":
            if b_constr.use_limit_lin_x:
                n_bhk_descriptor.min_distance = b_constr.limit_lin_x_lower / self.HAVOK_SCALE
                n_bhk_descriptor.max_distance = b_constr.limit_lin_x_upper / self.HAVOK_SCALE
            n_bhk_descriptor.friction = b_constr_obj.niftools_constraint.LHMaxFriction

    def export_blender_constraint(self, b_constr, b_constr_obj):
        """Export a bhkConstraint block purely from the Blender constraint values."""
        kind = self.BLENDER_TYPE_KINDS.get(b_constr.type)
        if kind is None:
            NifLog.warn(f"Constraint {b_constr_obj.name} has an unsupported type ({b_constr.type}). "
                        f"It will not be exported")
            return None
        if kind == "HINGE" and b_constr.use_limit_ang_z:
            kind = "LIMITED_HINGE"

        if b_constr.use_breaking:
            n_bhk_constraint = block_store.create_block("bhkBreakableConstraint", b_constr_obj)
            n_bhk_constraint.threshold = b_constr.breaking_threshold
            n_bhk_constraint.constraint_data.type = NifClasses.HkConstraintType[kind]
            n_bhk_descriptor = getattr(n_bhk_constraint.constraint_data, serialization.WRAPPED_KIND_FIELDS[kind])
        else:
            n_bhk_constraint = block_store.create_block(self.KIND_BLOCK_TYPES[kind], b_constr_obj)
            n_bhk_descriptor = n_bhk_constraint.constraint

        self.fill_descriptor(n_bhk_descriptor, kind, b_constr, b_constr_obj)
        return n_bhk_constraint

    def fill_descriptor(self, n_bhk_descriptor, kind, b_constr, b_constr_obj):
        """Fill a constraint descriptor from the transform and values of the Blender constraint."""

        # the constraint object's transform defines the pivot point and axes in world space,
        # matching the axis conventions of the Blender constraint types
        # (hinges rotate around Z, sliders move along X)
        m_constr = b_constr_obj.matrix_world
        pivot_world = m_constr.translation
        axes_world = [m_constr.col[i].xyz.normalized() for i in range(3)]

        # convert into the local space of either entity
        for suffix, b_target_obj in (("a", b_constr.object1), ("b", b_constr.object2)):
            m_inverse = b_target_obj.matrix_world.inverted()
            pivot = (m_inverse @ pivot_world) / self.HAVOK_SCALE
            axis_x, axis_y, axis_z = [(m_inverse.to_3x3() @ axis).normalized() for axis in axes_world]

            self.set_vector_field(n_bhk_descriptor, f"pivot_{suffix}", pivot)
            if kind == "RAGDOLL":
                self.set_vector_field(n_bhk_descriptor, f"twist_{suffix}", axis_z)
                self.set_vector_field(n_bhk_descriptor, f"plane_{suffix}", axis_x)
                self.set_vector_field(n_bhk_descriptor, f"motor_{suffix}", axis_y)
            elif kind in ("HINGE", "LIMITED_HINGE"):
                self.set_vector_field(n_bhk_descriptor, f"axis_{suffix}", axis_z)
                self.set_vector_field(n_bhk_descriptor, f"perp_axis_in_{suffix}_1", axis_x)
                self.set_vector_field(n_bhk_descriptor, f"perp_axis_in_{suffix}_2", axis_y)
            elif kind == "PRISMATIC":
                self.set_vector_field(n_bhk_descriptor, f"sliding_{suffix}", axis_x)
                self.set_vector_field(n_bhk_descriptor, f"rotation_{suffix}", axis_y)
                self.set_vector_field(n_bhk_descriptor, f"plane_{suffix}", axis_z)

        # scalar values
        if kind == "RAGDOLL":
            if b_constr.use_limit_ang_x:
                n_bhk_descriptor.plane_min_angle = b_constr.limit_ang_x_lower
                n_bhk_descriptor.plane_max_angle = b_constr.limit_ang_x_upper
            if b_constr.use_limit_ang_y:
                n_bhk_descriptor.cone_max_angle = b_constr.limit_ang_y_upper
            if b_constr.use_limit_ang_z:
                n_bhk_descriptor.twist_min_angle = b_constr.limit_ang_z_lower
                n_bhk_descriptor.twist_max_angle = b_constr.limit_ang_z_upper
            n_bhk_descriptor.max_friction = b_constr_obj.niftools_constraint.LHMaxFriction
        elif kind == "LIMITED_HINGE":
            n_bhk_descriptor.min_angle = b_constr.limit_ang_z_lower
            n_bhk_descriptor.max_angle = b_constr.limit_ang_z_upper
            n_bhk_descriptor.max_friction = b_constr_obj.niftools_constraint.LHMaxFriction
        elif kind == "PRISMATIC":
            if b_constr.use_limit_lin_x:
                n_bhk_descriptor.min_distance = b_constr.limit_lin_x_lower / self.HAVOK_SCALE
                n_bhk_descriptor.max_distance = b_constr.limit_lin_x_upper / self.HAVOK_SCALE
            n_bhk_descriptor.friction = b_constr_obj.niftools_constraint.LHMaxFriction
        elif kind == "STIFF_SPRING":
            distance = (b_constr.object1.matrix_world.translation -
                        b_constr.object2.matrix_world.translation).length
            n_bhk_descriptor.length = distance / self.HAVOK_SCALE

    @staticmethod
    def set_vector_field(n_bhk_descriptor, field_name, vector):
        n_vector = getattr(n_bhk_descriptor, field_name)
        n_vector.x = vector.x
        n_vector.y = vector.y
        n_vector.z = vector.z
        n_vector.w = 0.0

    @staticmethod
    def attach_constraint(n_bhk_constraint, n_entity_a, n_entity_b):
        """Link the constraint to its entities. The constraint block is attached to
        the constraint list of its first entity, matching how the games store them."""
        # malleable and breakable constraints repeat the constraint info in their wrapped data
        n_c_infos = [n_bhk_constraint.constraint_info]
        n_wrapped = getattr(n_bhk_constraint, "constraint", None)
        if hasattr(n_wrapped, "constraint_info"):
            n_c_infos.append(n_wrapped.constraint_info)
        n_wrapped = getattr(n_bhk_constraint, "constraint_data", None)
        if hasattr(n_wrapped, "constraint_info"):
            n_c_infos.append(n_wrapped.constraint_info)

        for n_c_info in n_c_infos:
            n_c_info.num_entities = 2
            n_c_info.entity_a = n_entity_a
            n_c_info.entity_b = n_entity_b

        n_entity_a.num_constraints += 1
        n_entity_a.constraints.append(n_bhk_constraint)
