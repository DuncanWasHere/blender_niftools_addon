"""Script to export havok collisions."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2013, NIF File Format Library and Tools contributors.
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
from io_scene_niftools.modules.nif_export.collision.animation import HavokAnimation

from nifgen.formats.nif import classes as NifClasses

import io_scene_niftools.utils.logging
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.collision import Collision
from io_scene_niftools.utils import math, consts
from io_scene_niftools.utils.singleton import NifOp, NifData
from io_scene_niftools.utils.logging import NifLog


class BhkCollision(Collision):

    def __init__(self):
        # To be filled during the export process:
        self.HAVOK_SCALE = None

    def export_collision_helper(self, b_col_obj, n_parent_node):
        """Helper function to add collision objects to a node. This function
        exports the rigid body, and calls the appropriate function to export
        the collision geometry in the desired format.

        @param b_col_obj: The object to export as collision.
        @param n_parent_node: The NiNode parent of the collision.
        """

        rigid_body = b_col_obj.rigid_body
        if not rigid_body:
            NifLog.warn(f"'{b_col_obj.name}' has no rigid body, skipping rigid body export")
            return

        # Is it packed?
        coll_ispacked = (rigid_body.collision_shape == 'MESH')

        # Is it a list?
        coll_islist = (rigid_body.collision_shape == 'COMPOUND')

        # Only use bhkRigidBodyT if there are transforms on a box or sphere shape
        add_rigid_body_t = not b_col_obj.matrix_world.is_identity and (b_col_obj.rigid_body.collision_shape == 'BOX' or b_col_obj.rigid_body.collision_shape == 'SPHERE')


        # Set Havok Scale ratio
        self.HAVOK_SCALE = NifData.data.havok_scale

        # Find physics properties/defaults
        # Get Havok material type from the material of the first material in the object
        hav_mat_type = type(NifClasses.HavokMaterial(NifData.data).material)
        n_havok_mat_list = []
        if b_col_obj.data.materials:
            for mat in b_col_obj.data.materials:
                try:
                    n_havok_mat_list.append(hav_mat_type[mat.name])
                except KeyError:
                    NifLog.warn(f"Unknown Havok material '{mat.name}', defaulting to 0")
                    n_havok_mat_list.append(hav_mat_type.from_value(0))
        else:
            n_havok_mat_list.append(hav_mat_type.from_value(0))

        # Determine if a single material or multiple materials are needed
        if coll_ispacked:
            n_havok_material = n_havok_mat_list
        else:
            n_havok_material = n_havok_mat_list[0]

        layer = int(b_col_obj.nifcollision.collision_layer)

        #self.export_bsx_upb_flags(b_col_obj, n_parent_node)

        # If no collisions have been exported yet to this parent_block
        # then create new collision tree on parent_block
        # bhkCollisionObject -> bhkRigidBody
        if not n_parent_node.collision_object:
            # Note: collision settings are taken from lowerclasschair01.nif
            if layer == NifClasses.OblivionLayer.OL_BIPED:
                # Special collision object for creatures
                n_col_obj = HavokAnimation.export_bhk_blend_collision(b_col_obj)

                # TODO [collsion][animation] add detection for this
                HavokAnimation.export_bhk_blend_controller(b_col_obj, n_parent_node)
            else:
                # Usual collision object
                n_col_obj = self.export_bhk_collison_object(b_col_obj)

            n_parent_node.collision_object = n_col_obj
            n_col_obj.target = n_parent_node


            n_bhkrigidbody = self.export_bhk_rigid_body(b_col_obj, n_col_obj, add_rigid_body_t)

            # we will use n_col_body to attach shapes to below
            n_col_body = n_bhkrigidbody

        else:
            n_col_body = n_parent_node.collision_object.body
            # Fix total mass

        if coll_ispacked:
            self.export_collision_packed(b_col_obj, n_col_body, layer, n_havok_material)
        else:
            if b_col_obj.rigid_body.collision_shape == 'COMPOUND':
                self.export_collision_list(b_col_obj, n_col_body, layer, n_havok_material)
            else:
                self.export_collision_single(b_col_obj, n_col_body, layer, n_havok_material)

        if b_col_obj.nifcollision.use_blender_properties:
            Collision.update_rigid_body(b_col_obj, n_col_body)

    def export_bhk_rigid_body(self, b_col_obj, n_bhk_collision_object, add_rigid_body_t):

        if add_rigid_body_t:
            n_bhk_rigid_body = block_store.create_block("bhkRigidBodyT", b_col_obj)
            translation = b_col_obj.matrix_world.to_translation()
            n_bhk_rigid_body.rigid_body_info.translation = NifClasses.Vector4.from_value([translation.x, translation.y, translation.z, 0.0])
            rotation = b_col_obj.matrix_world.to_quaternion()
            n_bhk_rigid_body.rigid_body_info.rotation.x = rotation.x
            n_bhk_rigid_body.rigid_body_info.rotation.y = rotation.y
            n_bhk_rigid_body.rigid_body_info.rotation.z = rotation.z
            n_bhk_rigid_body.rigid_body_info.rotation.w = rotation.w
            n_bhk_rigid_body.apply_scale(1 / self.HAVOK_SCALE)
        else:
            n_bhk_rigid_body = block_store.create_block("bhkRigidBody", b_col_obj)
        n_bhk_collision_object.body = n_bhk_rigid_body

        b_r_body = b_col_obj.rigid_body # Blender rigid body object
        n_r_info = n_bhk_rigid_body.rigid_body_info # bhkRigidBody Block

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

    def export_bhk_collison_object(self, b_obj):
        layer = int(b_obj.nifcollision.collision_layer)
        col_filter = b_obj.nifcollision.col_filter

        n_col_obj = block_store.create_block("bhkCollisionObject", b_obj)
        n_col_obj.flags._value = 0
        if layer == NifClasses.OblivionLayer.OL_ANIM_STATIC and col_filter != 128:
            # animated collision requires flags = 41
            # unless it is a constrained but not keyframed object
            n_col_obj.flags = 41
        else:
            # in all other cases this seems to be enough
            n_col_obj.flags = 1
        return n_col_obj

    def export_bhk_mopp_bv_tree_shape(self, b_obj, n_col_body):
        n_col_mopp = block_store.create_block("bhkMoppBvTreeShape", b_obj)
        n_col_body.shape = n_col_mopp
        return n_col_mopp

    def export_bhk_packed_nitristrip_shape(self, b_obj, n_col_mopp):
        # the mopp origin, scale, and data are written later
        n_col_shape = block_store.create_block("bhkPackedNiTriStripsShape", b_obj)
        # TODO [collision] radius has default of 0.1, but maybe let depend on margin
        scale = n_col_shape.scale
        scale.x = 1.0
        scale.y = 1.0
        scale.z = 1.0
        scale.w = 0
        n_col_shape.scale_copy = scale
        n_col_mopp.shape = n_col_shape
        return n_col_shape

    def export_bhk_convex_vertices_shape(self, b_obj, fdistlist, fnormlist, radius, vertlist, n_havok_mat):
        colhull = block_store.create_block("bhkConvexVerticesShape", b_obj)
        colhull.material.material = n_havok_mat
        colhull.radius = radius

        # Vertices
        colhull.num_vertices = len(vertlist)
        colhull.reset_field("vertices")
        for vhull, vert in zip(colhull.vertices, vertlist):
            vhull.x = vert[0] / self.HAVOK_SCALE
            vhull.y = vert[1] / self.HAVOK_SCALE
            vhull.z = vert[2] / self.HAVOK_SCALE
            # w component is 0

        # Normals
        colhull.num_normals = len(fnormlist)
        colhull.reset_field("normals")
        for nhull, norm, dist in zip(colhull.normals, fnormlist, fdistlist):
            nhull.x = norm[0]
            nhull.y = norm[1]
            nhull.z = norm[2]
            nhull.w = dist / self.HAVOK_SCALE

        return colhull

    def export_collision_object(self, b_obj, layer, n_havok_mat, add_transform_shape=False):
        """Export object obj as box, sphere, capsule, or convex hull.
        Note: polyhedron is handled by export_collision_packed."""

        # find bounding box data
        if not b_obj.data.vertices:
            NifLog.warn(f"Skipping collision object {b_obj} without vertices.")
            return None

        # Check if transforms are applied
        has_transform = not b_obj.matrix_world.is_identity

        box_extends = self.calculate_box_extents(b_obj)
        calc_bhkshape_radius = (box_extends[0][1] - box_extends[0][0] +
                                box_extends[1][1] - box_extends[1][0] +
                                box_extends[2][1] - box_extends[2][0]) / (6.0 * self.HAVOK_SCALE)

        b_r_body = b_obj.rigid_body
        if b_r_body.use_margin:
            margin = b_r_body.collision_margin
            if margin - calc_bhkshape_radius > NifOp.props.epsilon:
                radius = calc_bhkshape_radius
            else:
                radius = margin

        collision_shape = b_r_body.collision_shape
        if collision_shape in {'BOX', 'SPHERE'}:
            # Create bhkTransformShape if transforms are applied
            if has_transform and add_transform_shape:
                n_coltf = block_store.create_block("bhkTransformShape", b_obj)
                n_coltf.material.material = n_havok_mat
                n_coltf.radius = radius

                matrix = math.get_object_bind(b_obj)
                row0 = list(matrix[0])
                row1 = list(matrix[1])
                row2 = list(matrix[2])
                row3 = list(matrix[3])
                n_coltf.transform.set_rows(row0, row1, row2, row3)
                n_coltf.apply_scale(1.0 / self.HAVOK_SCALE)

                if collision_shape == 'BOX':
                    n_colbox = block_store.create_block("bhkBoxShape", b_obj)
                    n_coltf.shape = n_colbox
                    n_colbox.material.material = n_havok_mat
                    n_colbox.radius = radius

                    dims = n_colbox.dimensions
                    dims.x = (box_extends[0][1] - box_extends[0][0]) / (2.0 * self.HAVOK_SCALE)
                    dims.y = (box_extends[1][1] - box_extends[1][0]) / (2.0 * self.HAVOK_SCALE)
                    dims.z = (box_extends[2][1] - box_extends[2][0]) / (2.0 * self.HAVOK_SCALE)
                    n_colbox.minimum_size = min(dims.x, dims.y, dims.z)

                elif collision_shape == 'SPHERE':
                    n_colsphere = block_store.create_block("bhkSphereShape", b_obj)
                    n_coltf.shape = n_colsphere
                    n_colsphere.material.material = n_havok_mat
                    n_colsphere.radius = radius
                    matrix = math.get_object_bind(b_obj)
                    row0 = list(matrix[0])
                    row1 = list(matrix[1])
                    row2 = list(matrix[2])
                    row3 = list(matrix[3])
                    n_coltf.transform.set_rows(row0, row1, row2, row3)
                    n_coltf.apply_scale(1.0 / self.HAVOK_SCALE)

                return n_coltf

            # No transform shape needed
            else:
                if collision_shape == 'BOX':
                    n_colbox = block_store.create_block("bhkBoxShape", b_obj)
                    n_colbox.material.material = n_havok_mat
                    n_colbox.radius = radius

                    # Fix dimensions for Havok coordinate system
                    box_extends = self.calculate_box_extents(b_obj)
                    dims = n_colbox.dimensions
                    dims.x = (box_extends[0][1] - box_extends[0][0]) / (2.0 * self.HAVOK_SCALE)
                    dims.y = (box_extends[1][1] - box_extends[1][0]) / (2.0 * self.HAVOK_SCALE)
                    dims.z = (box_extends[2][1] - box_extends[2][0]) / (2.0 * self.HAVOK_SCALE)
                    n_colbox.minimum_size = min(dims.x, dims.y, dims.z)

                    return n_colbox

                elif collision_shape == 'SPHERE':
                    n_colsphere = block_store.create_block("bhkSphereShape", b_obj)
                    n_colsphere.material.material = n_havok_mat
                    # TODO [object][collision] find out what this is: fix for havok coordinate system (6 * 7 = 42)
                    # take average radius
                    n_colsphere.radius = radius

                    return n_colsphere

        elif collision_shape in {'CYLINDER', 'CAPSULE'}:
            length = b_obj.dimensions.z - b_obj.dimensions.x
            radius = b_obj.dimensions.x / 2
            matrix = math.get_object_bind(b_obj)

            length_half = length / 2
            # Calculate the direction unit vector
            v_dir = (mathutils.Vector((0, 0, 1)) @ matrix.to_3x3().inverted()).normalized()
            first_point = matrix.translation + v_dir * length_half
            second_point = matrix.translation - v_dir * length_half

            radius /= self.HAVOK_SCALE
            first_point /= self.HAVOK_SCALE
            second_point /= self.HAVOK_SCALE

            n_col_caps = block_store.create_block("bhkCapsuleShape", b_obj)
            n_col_caps.material.material = n_havok_mat

            cap_1 = n_col_caps.first_point
            cap_1.x = first_point.x
            cap_1.y = first_point.y
            cap_1.z = first_point.z

            cap_2 = n_col_caps.second_point
            cap_2.x = second_point.x
            cap_2.y = second_point.y
            cap_2.z = second_point.z

            n_col_caps.radius = radius
            n_col_caps.radius_1 = radius
            n_col_caps.radius_2 = radius

            return n_col_caps

        elif collision_shape == 'CONVEX_HULL':
            # Note: we apply transforms to convex shapes directly. No need for bhkConvexTransformShape or bhkRigidBodyT
            b_mesh = b_obj.data
            b_transform_mat = math.get_object_bind(b_obj)

            b_rot_quat = b_transform_mat.decompose()[1]
            b_scale_vec = b_transform_mat.decompose()[0]

            # Calculate vertices, normals, and distances
            vertlist = [b_transform_mat @ vert.co for vert in b_mesh.vertices]
            fnormlist = [b_rot_quat @ b_face.normal for b_face in b_mesh.polygons]
            fdistlist = [(b_transform_mat @ (-1 * b_mesh.vertices[b_mesh.polygons[b_face.index].vertices[0]].co)).dot(b_rot_quat.to_matrix() @ b_face.normal) for b_face in b_mesh.polygons]

            # Remove duplicates through dictionary
            vertdict = {}
            for i, vert in enumerate(vertlist):
                vertdict[(int(vert[0] * consts.VERTEX_RESOLUTION),
                          int(vert[1] * consts.VERTEX_RESOLUTION),
                          int(vert[2] * consts.VERTEX_RESOLUTION))] = i

            fdict = {}
            for i, (norm, dist) in enumerate(zip(fnormlist, fdistlist)):
                fdict[(int(norm[0] * consts.NORMAL_RESOLUTION),
                       int(norm[1] * consts.NORMAL_RESOLUTION),
                       int(norm[2] * consts.NORMAL_RESOLUTION),
                       int(dist * consts.VERTEX_RESOLUTION))] = i

            # Sort vertices and normals
            vertkeys = sorted(vertdict.keys())
            fkeys = sorted(fdict.keys())
            vertlist = [vertlist[vertdict[hsh]] for hsh in vertkeys]
            fnormlist = [fnormlist[fdict[hsh]] for hsh in fkeys]
            fdistlist = [fdistlist[fdict[hsh]] for hsh in fkeys]

            if len(fnormlist) > 65535 or len(vertlist) > 65535:
                raise io_scene_niftools.utils.logging.NifError("Mesh has too many polygons/vertices. Simply/split your mesh and try again.")

            return self.export_bhk_convex_vertices_shape(b_obj, fdistlist, fnormlist, radius, vertlist, n_havok_mat)

        else:
            raise io_scene_niftools.utils.logging.NifError(f'Cannot export collision type {collision_shape} to collision shape list')

    def export_collision_packed(self, b_obj, n_col_body, layer, n_havok_mat_list):
        """Add object ob as packed collision object to collision body
        n_col_body. If parent_block hasn't any collisions yet, a new
        packed list is created. If the current collision system is not
        a packed list of collisions (bhkPackedNiTriStripsShape), then
        a ValueError is raised.
        """

        b_mesh = b_obj.data
        transform = math.get_object_bind(b_obj)
        rotation = transform.decompose()[1]

        # Transform vertices
        transformed_vertices = [transform @ vert.co for vert in b_mesh.vertices]

        # Collect triangles and normals by material
        triangles_by_material = {}
        normals_by_material = {}

        for face in b_mesh.polygons:
            if len(face.vertices) < 3:
                continue  # Ignore degenerate polygons

            material_idx = face.material_index

            if material_idx not in triangles_by_material:
                triangles_by_material[material_idx] = []
                normals_by_material[material_idx] = []

            triangles_by_material[material_idx].append([face.vertices[i] for i in (0, 1, 2)])
            normals_by_material[material_idx].append(rotation @ face.normal)

            if len(face.vertices) == 4:
                triangles_by_material[material_idx].append([face.vertices[i] for i in (0, 2, 3)])
                normals_by_material[material_idx].append(rotation @ face.normal)

        # Sort materials and align geometry
        material_mapping = {
            old_idx: new_idx for new_idx, (old_idx, _) in enumerate(
                sorted(enumerate(n_havok_mat_list), key=lambda item: item[1].value)
            )
        }
        n_havok_mat_list.sort(key=lambda mat: mat.value)

        # Align geometry to sorted materials
        aligned_triangles_by_material = {}
        aligned_normals_by_material = {}

        for old_idx, triangles in triangles_by_material.items():
            new_idx = material_mapping[old_idx]
            aligned_triangles_by_material[new_idx] = triangles
            aligned_normals_by_material[new_idx] = normals_by_material[old_idx]

        # Replace old geometry with aligned geometry
        triangles_by_material = aligned_triangles_by_material
        normals_by_material = aligned_normals_by_material

        # Initialize collision body shape if needed
        if not n_col_body.shape:
            n_col_mopp = self.export_bhk_mopp_bv_tree_shape(b_obj, n_col_body)
            n_col_shape = self.export_bhk_packed_nitristrip_shape(b_obj, n_col_mopp)
        else:
            n_col_mopp = n_col_body.shape
            n_col_shape = n_col_mopp.shape

        # Export geometry for each material group
        for mat_idx in sorted(triangles_by_material.keys()):
            triangles = triangles_by_material[mat_idx]
            normals = normals_by_material[mat_idx]

            try:
                n_material = n_havok_mat_list[mat_idx]
            except IndexError:
                NifLog.warn(f"Material index {mat_idx} out of bounds, using default material")
                n_material = n_havok_mat_list[0]

            # Collect unique vertices used by this material's triangles
            used_vertex_indices = {idx for tri in triangles for idx in tri}
            subshape_vertices = [transformed_vertices[idx] for idx in used_vertex_indices]

            # Map old vertex indices to new indices
            vertex_map = {old_idx: new_idx for new_idx, old_idx in enumerate(used_vertex_indices)}
            remapped_triangles = [[vertex_map[idx] for idx in tri] for tri in triangles]

            n_col_shape.add_shape(remapped_triangles, normals, subshape_vertices, layer, n_material)
            n_col_shape.radius = b_obj.rigid_body.collision_margin
            n_col_shape.radius_copy = b_obj.rigid_body.collision_margin

    def export_collision_single(self, b_obj, n_col_body, layer, n_havok_mat):
        """Add collision object to n_col_body.
        If n_col_body already has a collision shape, throw ValueError."""
        if n_col_body.shape:
            raise ValueError('Collision body already has a shape')
        n_col_body.shape = self.export_collision_object(b_obj, layer, n_havok_mat)

    def export_collision_list(self, b_obj, n_col_body, layer, n_havok_mat):
        """
        Add collision object b_obj to the list of collision objects of n_col_body.
        If n_col_body has no collisions yet, a new list is created.
        If the current collision system is not a list of collisions
        (bhkListShape), then a ValueError is raised.
        """
        # Ensure the n_col_body has a bhkListShape attached
        if not n_col_body.shape:
            n_col_shape = block_store.create_block("bhkListShape")
            n_col_body.shape = n_col_shape
            n_col_shape.material.material = n_havok_mat
        else:
            n_col_shape = n_col_body.shape
            if not isinstance(n_col_shape, NifClasses.BhkListShape):
                raise ValueError('Not a list of collisions')

        # Iterate through the children of b_obj to export collision objects
        for child in b_obj.children:
            if child.type == 'MESH' and child.rigid_body:  # Only process mesh objects with rigid bodies
                subshape = self.export_collision_object(child, layer, n_havok_mat, True)
                if subshape:
                    n_col_shape.add_shape(subshape)