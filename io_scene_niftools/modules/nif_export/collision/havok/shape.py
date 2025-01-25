"""Module for exporting Havok primitive, convex, and list shape blocks."""

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


import mathutils
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.collision.havok import BhkCollisionCommon
from io_scene_niftools.utils import math, consts
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifData


class BhkShape(BhkCollisionCommon):
    """Class for exporting Havok primitive, convex, and list shape blocks."""

    def export_bhk_shape(self, b_col_obj, n_bhk_rigid_body, n_hav_mat):
        """
        Export a tree of collision shape blocks and parent them to the given bhkRigidBody block.
        For each Blender object passed to this function, a new type of bhkShape block is created.
        If the block is a compound parent, it will be exported as a bhkListShape block.
        Transforms will be applied if the block has point/vertex data.
        Box and sphere primitives under list shapes will be parented to bhkTransformShape blocks.
        Otherwise, the rigid body will be exported as a bhkRigidBodyT (since transform shapes are buggy).
        """

        self.HAVOK_SCALE = NifData.data.havok_scale

        if b_col_obj.rigid_body.collision_shape == 'COMPOUND':
            self.__export_bhk_list_shape(b_col_obj, n_bhk_rigid_body, n_hav_mat)
        else:
            n_bhk_shape = self.__export_bhk_shape(b_col_obj, n_hav_mat)
            if n_bhk_shape:
                n_bhk_rigid_body.shape = n_bhk_shape

    def __export_bhk_list_shape(self, b_col_obj, n_bhk_rigid_body, n_hav_mat):
        """
        Export a bhkListShape block.
        """

        # Create the list shape block
        n_bhk_list_shape = block_store.create_block("bhkListShape")
        n_bhk_rigid_body.shape = n_bhk_list_shape

        n_bhk_list_shape.material.material = n_hav_mat

        # Export all children as collision objects and attach each to the bhkListShape
        for b_sub_col_obj in b_col_obj.children:
            if b_sub_col_obj.type == 'MESH' and b_sub_col_obj.rigid_body:
                n_sub_hav_mat = self.get_havok_material_list(b_sub_col_obj)[0]
                n_bhk_shape = self.__export_bhk_shape(b_sub_col_obj, n_sub_hav_mat)
                if n_bhk_shape:
                    n_bhk_list_shape.add_shape(n_bhk_shape)

    def __export_bhk_shape(self, b_col_obj, n_hav_mat):
        """
        Export a single bhkShape block.
        """

        # Ensure mesh geometry exists
        if not b_col_obj.data.vertices:
            NifLog.warn(f"Collision object {b_col_obj.name} has no vertices."
                        f"It will not be exported")
            return None

        b_rigid_body = b_col_obj.rigid_body
        b_col_shape = b_rigid_body.collision_shape

        box_extents = self.calculate_box_extents(b_col_obj)

        if b_col_shape == 'CONVEX_HULL':
            return self.__export_bhk_convex_vertices_shape(b_col_obj, n_hav_mat)
        if b_col_shape == 'BOX':
            return self.__export_bhk_box_shape(b_col_obj, n_hav_mat, box_extents)
        elif b_col_shape == 'SPHERE':
            return self.__export_bhk_sphere_shape(b_col_obj, n_hav_mat, box_extents)
        elif b_col_shape == 'CAPSULE':
            return self.__export_bhk_capsule_shape(b_col_obj, n_hav_mat)
        elif b_col_shape == 'CYLINDER':
            return self.__export_bhk_cylinder_shape(b_col_obj, n_hav_mat)
        else:
            raise NifError(f'Cannot export collision object {b_col_obj.name}!'
                           f'Collision shape {b_col_shape} is unsupported.')

    def __export_bhk_box_shape(self, b_col_obj, n_hav_mat, box_extents):
        """
        Export and return a bhkBoxShape.
        Create and return a parent bhkTransformShape if the object has transforms
        and is in a list shape.
        """

        n_bhk_box_shape = block_store.create_block("bhkBoxShape", b_col_obj)
        n_bhk_box_shape.material.material = n_hav_mat
        n_bhk_box_shape.radius = 0.1  # This is hardcoded in the engine

        # Fix dimensions for Havok coordinate system
        dims = n_bhk_box_shape.dimensions
        dims.x = (box_extents[0][1] - box_extents[0][0]) / (2.0 * self.HAVOK_SCALE)
        dims.y = (box_extents[1][1] - box_extents[1][0]) / (2.0 * self.HAVOK_SCALE)
        dims.z = (box_extents[2][1] - box_extents[2][0]) / (2.0 * self.HAVOK_SCALE)
        n_bhk_box_shape.minimum_size = min(dims.x, dims.y, dims.z)

        if (b_col_obj.parent and b_col_obj.parent.rigid_body and
                b_col_obj.parent.rigid_body.collision_shape == 'COMPOUND'):
            if not b_col_obj.matrix_world.is_identity:
                n_bhk_transform_shape = self.__export_bhk_convex_transform_shape(b_col_obj, n_hav_mat, 0.1)
                n_bhk_transform_shape.shape = n_bhk_box_shape
                return n_bhk_transform_shape

        return n_bhk_box_shape

    def __export_bhk_sphere_shape(self, b_col_obj, n_hav_mat, box_extents):
        """
        Export and return a bhkSphereShape.
        Create and return a parent bhkTransformShape if the object has transforms
        and is in a list shape.
        """

        n_bhk_sphere_shape = block_store.create_block("bhkSphereShape", b_col_obj)
        n_bhk_sphere_shape.material.material = n_hav_mat

        # TODO [object][collision]: Find out what this is - fix for havok coordinate system (6 * 7 = 42)
        radius = (box_extents[0][1] - box_extents[0][0] +
                  box_extents[1][1] - box_extents[1][0] +
                  box_extents[2][1] - box_extents[2][0]) / (6.0 * self.HAVOK_SCALE)

        n_bhk_sphere_shape.radius = radius

        if (b_col_obj.parent and b_col_obj.parent.rigid_body and
                b_col_obj.parent.rigid_body.collision_shape == 'COMPOUND'):
            if not b_col_obj.matrix_world.is_identity:
                n_bhk_transform_shape = self.__export_bhk_convex_transform_shape(b_col_obj, n_hav_mat, radius)
                n_bhk_transform_shape.shape = n_bhk_sphere_shape
                return n_bhk_transform_shape

        return n_bhk_sphere_shape

    def __export_bhk_capsule_shape(self, b_col_obj, n_hav_mat):
        """Export and return a bhkCapsuleShape."""

        n_bhk_capsule_shape = block_store.create_block("bhkCapsuleShape", b_col_obj)
        n_bhk_capsule_shape.material.material = n_hav_mat

        length = b_col_obj.dimensions.z - b_col_obj.dimensions.x
        radius = b_col_obj.dimensions.x / 2
        matrix = math.get_object_bind(b_col_obj)

        length_half = length / 2
        # Calculate the direction unit vector
        v_dir = (mathutils.Vector((0, 0, 1)) @ matrix.to_3x3().inverted()).normalized()
        first_point = matrix.translation + v_dir * length_half
        second_point = matrix.translation - v_dir * length_half

        radius /= self.HAVOK_SCALE
        first_point /= self.HAVOK_SCALE
        second_point /= self.HAVOK_SCALE

        cap_1 = n_bhk_capsule_shape.first_point
        cap_1.x = first_point.x
        cap_1.y = first_point.y
        cap_1.z = first_point.z

        cap_2 = n_bhk_capsule_shape.second_point
        cap_2.x = second_point.x
        cap_2.y = second_point.y
        cap_2.z = second_point.z

        n_bhk_capsule_shape.radius = radius
        n_bhk_capsule_shape.radius_1 = radius
        n_bhk_capsule_shape.radius_2 = radius

        return n_bhk_capsule_shape

    def __export_bhk_cylinder_shape(self, b_col_obj, n_hav_mat):
        """Export and return a bhkCylinderShape."""

        # TODO: Fill in this method (low priority because cylinder shapes aren't very useful)
        # n_bhk_cylinder_shape = block_store.create_block("bhkCylinderShape", b_col_obj)
        return self.__export_bhk_capsule_shape(b_col_obj, n_hav_mat)

    def __export_bhk_convex_vertices_shape(self, b_col_obj, n_hav_mat):
        """Export and return a bhkConvexVerticesShape."""

        n_bhk_convex_vertices_shape = block_store.create_block("bhkConvexVerticesShape", b_col_obj)
        n_bhk_convex_vertices_shape.material.material = n_hav_mat
        n_bhk_convex_vertices_shape.radius = 0.1  # This is hardcoded in the engine

        # Note: we apply transforms to convex shapes directly. No need for bhkConvexTransformShape or bhkRigidBodyT
        b_mesh = b_col_obj.data
        b_transform_mat = math.get_object_bind(b_col_obj)

        b_rot_quat = b_transform_mat.decompose()[1]
        b_scale_vec = b_transform_mat.decompose()[0]

        # Calculate vertices, normals, and distances
        vertex_list = [b_transform_mat @ vert.co for vert in b_mesh.vertices]
        face_normals_list = [b_rot_quat @ b_face.normal for b_face in b_mesh.polygons]
        face_distances_list = [
            (b_transform_mat @ (-1 * b_mesh.vertices[b_mesh.polygons[b_face.index].vertices[0]].co)).dot(
                b_rot_quat.to_matrix() @ b_face.normal) for b_face in b_mesh.polygons]

        # Remove duplicates through dictionary
        vertex_dict = {}
        for i, vert in enumerate(vertex_list):
            vertex_dict[(int(vert[0] * consts.VERTEX_RESOLUTION),
                         int(vert[1] * consts.VERTEX_RESOLUTION),
                         int(vert[2] * consts.VERTEX_RESOLUTION))] = i

        fdict = {}
        for i, (norm, dist) in enumerate(zip(face_normals_list, face_distances_list)):
            fdict[(int(norm[0] * consts.NORMAL_RESOLUTION),
                   int(norm[1] * consts.NORMAL_RESOLUTION),
                   int(norm[2] * consts.NORMAL_RESOLUTION),
                   int(dist * consts.VERTEX_RESOLUTION))] = i

        # Sort vertices and normals
        vertkeys = sorted(vertex_dict.keys())
        fkeys = sorted(fdict.keys())
        vertex_list = [vertex_list[vertex_dict[hsh]] for hsh in vertkeys]
        face_normals_list = [face_normals_list[fdict[hsh]] for hsh in fkeys]
        face_distances_list = [face_distances_list[fdict[hsh]] for hsh in fkeys]

        # Vertices
        n_bhk_convex_vertices_shape.num_vertices = len(vertex_list)
        n_bhk_convex_vertices_shape.reset_field("vertices")
        for vhull, vert in zip(n_bhk_convex_vertices_shape.vertices, vertex_list):
            vhull.x = vert[0] / self.HAVOK_SCALE
            vhull.y = vert[1] / self.HAVOK_SCALE
            vhull.z = vert[2] / self.HAVOK_SCALE
            # w component is 0

        # Normals
        n_bhk_convex_vertices_shape.num_normals = len(face_normals_list)
        n_bhk_convex_vertices_shape.reset_field("normals")
        for nhull, norm, dist in zip(n_bhk_convex_vertices_shape.normals, face_normals_list, face_distances_list):
            nhull.x = norm[0]
            nhull.y = norm[1]
            nhull.z = norm[2]
            nhull.w = dist / self.HAVOK_SCALE

        if self.is_oblivion:
            if (b_col_obj.parent and b_col_obj.parent.rigid_body and
                    b_col_obj.parent.rigid_body.collision_shape == 'COMPOUND'):
                # bhkConvexVerticesShape of children of bhkListShapes need an extra bhkConvexTransformShape (see issue #3308638, reported by Koniption)
                # note: block_store.block_to_obj changes during iteration, so need list copy
                # TODO: Not necessary for FNV and won't work in Skyrim. Is this even needed for Oblivion?
                n_bhk_convex_transform_shape = self.__export_bhk_convex_transform_shape(b_col_obj, n_hav_mat)
                n_bhk_convex_transform_shape.shape = n_bhk_convex_vertices_shape
                return n_bhk_convex_transform_shape

        return n_bhk_convex_vertices_shape

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

    def __export_bhk_convex_transform_shape(self, b_col_obj, n_hav_mat, radius=0.1):
        """
        Export and return a bhkConvexTransformShape.
        Note: should generally only be used for box and sphere sub-shapes of list shapes.
        """

        n_bhk_convex_transform_shape = block_store.create_block("bhkConvexTransformShape", b_col_obj)
        n_bhk_convex_transform_shape.material.material = n_hav_mat
        n_bhk_convex_transform_shape.radius = radius

        matrix = math.get_object_bind(b_col_obj)
        row0 = list(matrix[0])
        row1 = list(matrix[1])
        row2 = list(matrix[2])
        row3 = list(matrix[3])
        n_bhk_convex_transform_shape.transform.set_rows(row0, row1, row2, row3)
        n_bhk_convex_transform_shape.apply_scale(1.0 / self.HAVOK_SCALE)

        return n_bhk_convex_transform_shape
