"""Main module for exporting Havok collision blocks."""

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


import mathutils

from .....modules.nif_export.block_registry import block_store
from .....modules.nif_export.collision.havok.common import BhkCollisionCommon
from .....modules.nif_export.collision.havok.mopp_shape import BhkMOPPShape
from .....modules.nif_export.collision.havok.shape import BhkShape
from .....utils import math
# from io_scene_niftools.modules.nif_export.object import DICT_NAMES
from .....utils.logging import NifLog
from .....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses


class BhkCollision(BhkCollisionCommon):
    """
    Main interface class for exporting Havok collision blocks
    (i.e., bhkCollisionObject, bhkRigidBody(T), bhkShape subclasses).
    For Bethesda games (except Morrowind) ONLY!
    Constraints are handled elsewhere.
    """

    def __init__(self):
        super().__init__()

        self.bhk_shape_helper = BhkShape()
        self.bhk_mopp_shape_helper = BhkMOPPShape()

    def export_bhk_collision(self, b_col_obj, n_parent_node, n_hav_layer):
        """
        Export a tree of Havok collision blocks and parent it to the given node.
        For each Blender object passed to this function, a new bhkCollisionObject is created if necessary.
        Then a bhkRigidBody(T) block is created from the rigid body properties.
        Finally, the collision shapes are created from the Blender mesh and rigid body properties.

        @param b_col_obj: The object to export as collision.
        @param n_parent_node: The parent node of the collision object.
        @param n_hav_layer: The collision layer of the rigid body.
        """

        # Load constants for this NIF version
        self.HAVOK_SCALE = NifData.data.havok_scale

        # Commonly referenced properties for this object
        b_rigid_body = b_col_obj.rigid_body
        b_col_shape = b_rigid_body.collision_shape
        n_hav_mat_list = self.get_havok_material_list(b_col_obj)
        n_col_obj = n_parent_node.collision_object

        # A phantom is a different collision object and body pair entirely, with no mass or
        # motion, so it takes a path of its own
        if b_col_obj.nif_collision.body_type != 'bhkRigidBody':
            self.export_bhk_phantom(b_col_obj, n_parent_node, n_hav_layer, n_hav_mat_list)
            return

        # Export a bhkCollisionObject if a bhkBlendCollisionObject wasn't already exported
        if not n_col_obj:
            n_col_obj = self.__export_bhk_collision_object(b_col_obj, n_hav_layer)
            n_parent_node.collision_object = n_col_obj
            n_col_obj.target = n_parent_node
        elif n_col_obj.body:
            NifLog.warn(f"Multiple collision objects target node '{n_parent_node.name}'. "
                        f"'{b_col_obj.name}' will replace the previously exported rigid body. "
                        f"Parent each collision object to its own node or bone")

        # Export a bhkRigidBody
        n_bhk_rigid_body = self.__export_bhk_rigid_body(b_col_obj, n_col_obj, b_col_shape)

        # Export the collision shape(s)
        if b_col_shape == 'MESH':
            # Export MOPP collision
            self.bhk_mopp_shape_helper.export_bhk_mopp_shape(b_col_obj, n_bhk_rigid_body, n_hav_mat_list, n_hav_layer)
        else:
            # Export normal collision
            self.bhk_shape_helper.export_bhk_shape(b_col_obj, n_bhk_rigid_body, n_hav_mat_list[0])

        # Recalculate inertia tensor and center of mass for bhkRigidBody(T)
        if b_col_obj.nif_collision.use_blender_properties:
            self.update_rigid_body(b_col_obj, n_bhk_rigid_body)

        # DICT_NAMES[b_col_obj.name] = n_bhk_rigid_body
        block_store.obj_to_block[b_col_obj] = n_bhk_rigid_body

        self.export_havok_actions(b_col_obj, n_bhk_rigid_body)

    def export_bhk_phantom(self, b_col_obj, n_parent_node, n_hav_layer, n_hav_mat_list):
        """
        Export a phantom body, which reports overlaps but has no physical response.

        A shape phantom carries its shape and its own transform and hangs off a
        bhkSPCollisionObject; an AABB phantom is only a box and hangs off a
        bhkPCollisionObject.
        """

        b_body_type = b_col_obj.nif_collision.body_type
        n_col_obj_type = ("bhkSPCollisionObject" if b_body_type == 'bhkSimpleShapePhantom'
                          else "bhkPCollisionObject")

        n_col_obj = block_store.create_block(n_col_obj_type, b_col_obj)
        n_col_obj.flags = self.get_collision_object_flags(b_col_obj, n_hav_layer)
        n_parent_node.collision_object = n_col_obj
        n_col_obj.target = n_parent_node

        n_phantom = block_store.create_block(b_body_type, b_col_obj)
        n_col_obj.body = n_phantom

        n_phantom.havok_filter.layer = n_hav_layer
        n_phantom.havok_filter.flags = b_col_obj.nif_collision.col_filter
        n_phantom.world_object_info.broad_phase_type = NifClasses.BroadPhaseType[
            b_col_obj.nif_collision.broad_phase_type]

        b_bind_matrix = math.get_object_bind(b_col_obj)

        if b_body_type == 'bhkSimpleShapePhantom':
            # Keep the phantom itself in its parent's space. A non-identity object bind
            # belongs on a bhkTransformShape around the primitive. Writing it on both
            # blocks would apply the transform twice.
            n_phantom.transform.set_identity()
            has_bind_transform = not all(
                abs(element - identity_element) < 1e-5
                for row, identity_row in zip(b_bind_matrix, mathutils.Matrix())
                for element, identity_element in zip(row, identity_row)
            )
            self.bhk_shape_helper.export_bhk_shape(
                b_col_obj,
                n_phantom,
                n_hav_mat_list[0],
                use_transform_shape=has_bind_transform,
            )
        else:
            self.__export_aabb(b_col_obj, b_bind_matrix, n_phantom)

        block_store.obj_to_block[b_col_obj] = n_phantom

    def __export_aabb(self, b_col_obj, b_bind_matrix, n_phantom):
        """Fill a bhkAabbPhantom's box from the object's bounding box."""

        b_corners = [b_bind_matrix @ mathutils.Vector(b_corner)
                     for b_corner in b_col_obj.bound_box]
        for axis_index, axis in enumerate('xyz'):
            b_values = [b_corner[axis_index] / self.HAVOK_SCALE for b_corner in b_corners]
            setattr(n_phantom.aabb.min, axis, min(b_values))
            setattr(n_phantom.aabb.max, axis, max(b_values))

    def export_havok_actions(self, b_col_obj, n_bhk_rigid_body):
        """
        Export the havok actions attached to a body.

        An action is held in the body's constraints list, which takes any bhkSerializable
        rather than only constraints proper, so this is the same list the bhkConstraint
        exporter appends to.
        """

        nif_action = getattr(b_col_obj, "nif_havok_action", None)
        if nif_action is None:
            return

        n_actions = []

        if nif_action.use_liquid_action:
            n_liquid = block_store.create_block("bhkLiquidAction", b_col_obj)
            n_liquid.initial_stick_force = nif_action.initial_stick_force
            n_liquid.stick_strength = nif_action.stick_strength
            n_liquid.neighbor_distance = nif_action.neighbor_distance
            n_liquid.neighbor_strength = nif_action.neighbor_strength
            n_actions.append(n_liquid)

        if nif_action.use_orient_hinged_body_action:
            n_orient = block_store.create_block("bhkOrientHingedBodyAction", b_col_obj)
            # this one does name its body, unlike the liquid action
            n_orient.entity = n_bhk_rigid_body
            n_orient.hinge_axis_ls = NifClasses.Vector4.from_value(
                list(nif_action.hinge_axis_ls) + [0.0])
            n_orient.forward_ls = NifClasses.Vector4.from_value(
                list(nif_action.forward_ls) + [0.0])
            n_orient.strength = nif_action.strength
            n_orient.damping = nif_action.damping
            n_actions.append(n_orient)

        for n_action in n_actions:
            n_bhk_rigid_body.num_constraints += 1
            n_bhk_rigid_body.constraints.append(n_action)

    def __export_bhk_collision_object(self, b_obj, layer):
        """
        Export a bhkCollisionObject block.
        """

        n_col_obj = block_store.create_block("bhkCollisionObject", b_obj)
        n_col_obj.flags = self.get_collision_object_flags(b_obj, layer)
        return n_col_obj

    def __export_bhk_rigid_body(self, b_col_obj, n_bhk_collision_object, b_col_shape):
        """
        Export a bhkRigidBody block.
        A bhkRigidBodyT block will be created if needed.
        """

        # The rigid body transform is relative to the node the collision object is attached to,
        # so only the object's transform relative to its parent matters, not the world transform
        b_bind_matrix = math.get_object_bind(b_col_obj)
        has_bind_transform = not all(abs(el - id_el) < 1e-5
                                     for row, id_row in zip(b_bind_matrix, mathutils.Matrix())
                                     for el, id_el in zip(row, id_row))
        # capsule shapes bake the bind into their shape data. The other shapes carry
        # no transform of their own, so a transform must be exported on the rigid body
        shape_needs_transform = has_bind_transform and b_col_shape not in ('CAPSULE', 'CYLINDER')

        # Export a bhkRigidBodyT only if needed
        if b_col_obj.nif_collision.force_bhk_rigid_body_t or shape_needs_transform:
            n_bhk_rigid_body = block_store.create_block("bhkRigidBodyT", b_col_obj)
            translation = b_bind_matrix.to_translation()
            n_bhk_rigid_body.rigid_body_info.translation = NifClasses.Vector4.from_value(
                [translation.x, translation.y, translation.z, 0.0])
            rotation = b_bind_matrix.to_quaternion()
            n_bhk_rigid_body.rigid_body_info.rotation.x = rotation.x
            n_bhk_rigid_body.rigid_body_info.rotation.y = rotation.y
            n_bhk_rigid_body.rigid_body_info.rotation.z = rotation.z
            n_bhk_rigid_body.rigid_body_info.rotation.w = rotation.w
            n_bhk_rigid_body.apply_scale(1 / self.HAVOK_SCALE)
        else:
            n_bhk_rigid_body = block_store.create_block("bhkRigidBody", b_col_obj)

        n_bhk_collision_object.body = n_bhk_rigid_body

        b_r_body = b_col_obj.rigid_body  # Blender rigid body object
        n_r_info = n_bhk_rigid_body.rigid_body_info  # bhkRigidBody block

        n_bhk_rigid_body.havok_filter.layer = int(b_col_obj.nif_collision.collision_layer)
        n_bhk_rigid_body.havok_filter.flags = b_col_obj.nif_collision.col_filter
        # n_r_body.havok_filter.group = 0

        n_bhk_rigid_body.entity_info.collision_response = NifClasses.HkResponseType['RESPONSE_SIMPLE_CONTACT']
        n_r_info.collision_response = NifClasses.HkResponseType['RESPONSE_SIMPLE_CONTACT']

        n_r_info.havok_filter = n_bhk_rigid_body.havok_filter

        n_r_info.inertia_tensor.m_11, n_r_info.inertia_tensor.m_22, n_r_info.inertia_tensor.m_33 = b_col_obj.nif_collision.inertia_tensor
        n_r_info.center.x, n_r_info.center.y, n_r_info.center.z = b_col_obj.nif_collision.center
        n_r_info.mass = b_col_obj.nif_collision.mass
        n_r_info.linear_damping = b_r_body.linear_damping
        n_r_info.angular_damping = b_r_body.angular_damping
        n_r_info.friction = b_r_body.friction
        n_r_info.restitution = b_r_body.restitution
        n_r_info.max_linear_velocity = b_col_obj.nif_collision.max_linear_velocity
        n_r_info.max_angular_velocity = b_col_obj.nif_collision.max_angular_velocity
        n_r_info.penetration_depth = b_col_obj.nif_collision.penetration_depth

        n_r_info.motion_system = NifClasses.HkMotionType[b_col_obj.nif_collision.motion_system]
        n_r_info.deactivator_type = NifClasses.HkDeactivatorType[b_col_obj.nif_collision.deactivator_type]
        n_r_info.solver_deactivation = NifClasses.HkSolverDeactivation[b_col_obj.nif_collision.solver_deactivation]
        n_r_info.quality_type = NifClasses.HkQualityType[b_col_obj.nif_collision.quality_type]

        n_bhk_rigid_body.world_object_info.broad_phase_type = NifClasses.BroadPhaseType[
            b_col_obj.nif_collision.broad_phase_type]

        n_bhk_rigid_body.body_flags = b_col_obj.nif_collision.body_flags

        return n_bhk_rigid_body
