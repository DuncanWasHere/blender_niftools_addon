"""Main module for exporting Havok collision blocks."""

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
from io_scene_niftools.modules.nif_export.collision.havok.common import BhkCollisionCommon
from io_scene_niftools.modules.nif_export.collision.havok.mopp_shape import BhkMOPPShape
from io_scene_niftools.modules.nif_export.collision.havok.shape import BhkShape
from io_scene_niftools.modules.nif_export.object import DICT_NAMES
from io_scene_niftools.utils.singleton import NifData
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

        # Export a bhkCollisionObject if a bhkBlendCollisionObject wasn't already exported
        if not n_col_obj:
            n_col_obj = self.__export_bhk_collision_object(b_col_obj, n_hav_layer)
            n_parent_node.collision_object = n_col_obj
            n_col_obj.target = n_parent_node

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
        if b_col_obj.nifcollision.use_blender_properties:
            self.update_rigid_body(b_col_obj, n_bhk_rigid_body)

        DICT_NAMES[b_col_obj.name] = n_bhk_rigid_body

    def __export_bhk_collision_object(self, b_obj, layer):
        """
        Export a bhkCollisionObject block.
        """

        col_filter = b_obj.nifcollision.col_filter

        n_col_obj = block_store.create_block("bhkCollisionObject", b_obj)
        n_col_obj.flags._value = 0

        # Animated collision requires flags = 41
        # Unless it is constrained, but not keyframed
        if self.is_oblivion:
            if layer == NifClasses.OblivionLayer.OL_ANIM_STATIC and col_filter != 128:
                n_col_obj.flags = 41
                return n_col_obj
        elif self.is_fallout:
            if layer == NifClasses.Fallout3Layer.FOL_ANIM_STATIC and col_filter != 128:
                n_col_obj.flags = 41
                return n_col_obj

        # In all other cases this seems to be enough
        n_col_obj.flags = 1
        return n_col_obj

    def __export_bhk_rigid_body(self, b_col_obj, n_bhk_collision_object, b_col_shape):
        """
        Export a bhkRigidBody block.
        A bhkRigidBodyT block will be created if needed.
        """

        # Export a bhkRigidBodyT only for primitives that need them
        if b_col_shape in ('BOX', 'SPHERE') and not b_col_obj.matrix_world.is_identity:
            n_bhk_rigid_body = block_store.create_block("bhkRigidBodyT", b_col_obj)
            translation = b_col_obj.matrix_world.to_translation()
            n_bhk_rigid_body.rigid_body_info.translation = NifClasses.Vector4.from_value(
                [translation.x, translation.y, translation.z, 0.0])
            rotation = b_col_obj.matrix_world.to_quaternion()
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

        n_bhk_rigid_body.havok_filter.layer = int(b_col_obj.nifcollision.collision_layer)
        n_bhk_rigid_body.havok_filter.flags = b_col_obj.nifcollision.col_filter
        # n_r_body.havok_filter.group = 0

        n_bhk_rigid_body.entity_info.collision_response = NifClasses.HkResponseType['RESPONSE_SIMPLE_CONTACT']
        n_r_info.collision_response = NifClasses.HkResponseType['RESPONSE_SIMPLE_CONTACT']

        n_r_info.havok_filter = n_bhk_rigid_body.havok_filter

        n_r_info.inertia_tensor.m_11, n_r_info.inertia_tensor.m_22, n_r_info.inertia_tensor.m_33 = b_col_obj.nifcollision.inertia_tensor
        n_r_info.center.x, n_r_info.center.y, n_r_info.center.z = b_col_obj.nifcollision.center
        n_r_info.mass = b_col_obj.nifcollision.mass
        n_r_info.linear_damping = b_r_body.linear_damping
        n_r_info.angular_damping = b_r_body.angular_damping
        n_r_info.friction = b_r_body.friction
        n_r_info.restitution = b_r_body.restitution
        n_r_info.max_linear_velocity = b_col_obj.nifcollision.max_linear_velocity
        n_r_info.max_angular_velocity = b_col_obj.nifcollision.max_angular_velocity
        n_r_info.penetration_depth = b_col_obj.nifcollision.penetration_depth

        n_r_info.motion_system = NifClasses.HkMotionType[b_col_obj.nifcollision.motion_system]
        n_r_info.deactivator_type = NifClasses.HkDeactivatorType[b_col_obj.nifcollision.deactivator_type]
        n_r_info.solver_deactivation = NifClasses.HkSolverDeactivation[b_col_obj.nifcollision.solver_deactivation]
        n_r_info.quality_type = NifClasses.HkQualityType[b_col_obj.nifcollision.quality_type]

        n_bhk_rigid_body.body_flags = b_col_obj.nifcollision.body_flags

        return n_bhk_rigid_body
