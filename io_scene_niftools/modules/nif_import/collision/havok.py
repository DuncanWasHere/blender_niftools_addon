"""This script contains classes to import collision objects."""

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


import operator
from functools import reduce, singledispatch

import bpy
import mathutils
from io_scene_niftools.modules.nif_import import collision
from io_scene_niftools.modules.nif_import.collision import Collision
from io_scene_niftools.modules.nif_import.object import Object
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses
from nifgen.utils.quickhull import qhull3d


class BhkCollision(Collision):

    LAYER_WIREFRAME_COLOR_MAP = [(0, 255, 0, 1),
                                 (255, 0, 0, 1),
                                 (255, 0, 255, 1),
                                 (255, 255, 255, 1),
                                 (0, 0, 255, 1),
                                 (255, 255, 0, 1),
                                 (0, 255, 255, 1)
                                 ]

    def __init__(self):
        # Dictionary mapping bhkRigidBody objects to objects imported in Blender;
        # We use this dictionary to set the physics constraints (ragdoll, etc.)
        collision.DICT_HAVOK_OBJECTS = {}

        self.HAVOK_SCALE = NifData.data.havok_scale

        self.process_bhk = singledispatch(self.process_bhk)
        self.process_bhk.register(NifClasses.BhkTransformShape, self.import_bhktransform)
        self.process_bhk.register(NifClasses.BhkConvexTransformShape, self.import_bhk_convex_transform)
        self.process_bhk.register(NifClasses.BhkRigidBodyT, self.import_bhk_rigidbody_t)
        self.process_bhk.register(NifClasses.BhkRigidBody, self.import_bhk_rigid_body)
        self.process_bhk.register(NifClasses.BhkBoxShape, self.import_bhkbox_shape)
        self.process_bhk.register(NifClasses.BhkSphereShape, self.import_bhksphere_shape)
        self.process_bhk.register(NifClasses.BhkCapsuleShape, self.import_bhkcapsule_shape)
        self.process_bhk.register(NifClasses.BhkConvexVerticesShape, self.import_bhkconvex_vertices_shape)
        self.process_bhk.register(NifClasses.BhkPackedNiTriStripsShape, self.import_bhkpackednitristrips_shape)
        self.process_bhk.register(NifClasses.BhkNiTriStripsShape, self.import_bhk_nitristrips_shape)
        self.process_bhk.register(NifClasses.NiTriStripsData, self.import_nitristrips)
        self.process_bhk.register(NifClasses.BhkMoppBvTreeShape, self.import_bhk_mopp_bv_tree_shape)
        self.process_bhk.register(NifClasses.BhkListShape, self.import_bhk_list_shape)
        self.process_bhk.register(NifClasses.BhkSimpleShapePhantom, self.import_bhk_simple_shape_phantom)

    def process_bhk(self, n_bhk_shape):
        """Base method to warn user that this collision shape is not supported."""

        NifLog.warn(f"Unsupported bhk shape {n_bhk_shape.__class__.__name__}")
        NifLog.warn(f"This type isn't currently supported: {type(n_bhk_shape)}")
        return None

    def import_bhk_rigid_body(self, n_bhk_rigid_body):
        """Import a BhkRigidBody block and return the child collision shape as a Blender object."""
        NifLog.debug(f"Importing {n_bhk_rigid_body.__class__.__name__}")

        # Import collision shape as Blender object
        b_col_obj = self.import_bhk_shape(n_bhk_rigid_body.shape)

        # Attach rigid body to Blender object
        self._import_bhk_rigid_body(n_bhk_rigid_body, b_col_obj)

        # Return Blender object with the rigid body attached
        return b_col_obj

    def import_bhk_rigidbody_t(self, n_bhk_rigid_body_t):
        """Import a BhkRigidBodyT block and return the transformed child collision shape as a Blender object."""
        NifLog.debug(f"Importing {n_bhk_rigid_body_t.__class__.__name__}")

        # Import collision shape as Blender object
        b_col_obj = self.import_bhk_shape(n_bhk_rigid_body_t.shape)
        body_info = n_bhk_rigid_body_t.rigid_body_info

        # Set rotation
        b_rot = body_info.rotation

        # Get transformation matrix
        transform = mathutils.Quaternion([b_rot.w, b_rot.x, b_rot.y, b_rot.z]).to_matrix().to_4x4()

        # Set translation
        b_trans = body_info.translation
        transform.translation = mathutils.Vector((b_trans.x, b_trans.y, b_trans.z)) * self.HAVOK_SCALE

        # Apply transform
        b_col_obj.matrix_local = b_col_obj.matrix_local @ transform

        # Attach rigid body to Blender object
        self._import_bhk_rigid_body(n_bhk_rigid_body_t, b_col_obj)

        # Return Blender object with the rigid body attached
        return b_col_obj

    def _import_bhk_rigid_body(self, n_bhk_rigid_body, b_col_obj):
        """Import the bhkRigidBody block properties into the Blender object's rigid body."""

        n_rigid_body_info = n_bhk_rigid_body.rigid_body_info
        b_r_body = b_col_obj.rigid_body

        # Properties shared by Blender and NIFs
        if (isinstance(n_bhk_rigid_body.shape, NifClasses.BhkMoppBvTreeShape)
                and (isinstance(n_bhk_rigid_body.shape.shape, NifClasses.BhkPackedNiTriStripsShape)
                     or isinstance(n_bhk_rigid_body.shape.shape, NifClasses.BhkNiTriStripsShape))):
            b_r_body.collision_margin = n_bhk_rigid_body.shape.shape.radius
        else:
            b_r_body.collision_margin = 0.1

        b_r_body.friction = n_rigid_body_info.friction
        b_r_body.restitution = n_rigid_body_info.restitution
        b_r_body.linear_damping = n_rigid_body_info.linear_damping
        b_r_body.angular_damping = n_rigid_body_info.angular_damping

        # Extra properties for Blender not used in NIFs
        b_r_body.use_deactivation = True
        b_r_body.kinematic = True
        b_r_body.mass = n_rigid_body_info.mass
        vel = n_rigid_body_info.linear_velocity
        b_r_body.deactivate_linear_velocity = mathutils.Vector([vel.w, vel.x, vel.y, vel.z]).magnitude
        ang_vel = n_rigid_body_info.angular_velocity
        b_r_body.deactivate_angular_velocity = mathutils.Vector([ang_vel.w, ang_vel.x, ang_vel.y, ang_vel.z]).magnitude

        # Custom NIF properties
        b_col_obj.nif_collision.collision_layer = str(n_rigid_body_info.havok_filter.layer.value)

        b_col_obj.nif_collision.col_filter = n_bhk_rigid_body.havok_filter.flags

        b_col_obj.nif_collision.inertia_tensor = (n_rigid_body_info.inertia_tensor.m_11,
                                                  n_rigid_body_info.inertia_tensor.m_22,
                                                  n_rigid_body_info.inertia_tensor.m_33)

        b_col_obj.nif_collision.center = (n_rigid_body_info.center.x,
                                          n_rigid_body_info.center.y,
                                          n_rigid_body_info.center.z)

        b_col_obj.nif_collision.mass = n_rigid_body_info.mass
        b_col_obj.nif_collision.max_linear_velocity = n_rigid_body_info.max_linear_velocity
        b_col_obj.nif_collision.max_angular_velocity = n_rigid_body_info.max_angular_velocity
        b_col_obj.nif_collision.penetration_depth = n_rigid_body_info.penetration_depth

        b_col_obj.nif_collision.motion_system = n_rigid_body_info.motion_system.name
        b_col_obj.nif_collision.deactivator_type = n_rigid_body_info.deactivator_type.name
        b_col_obj.nif_collision.solver_deactivation = n_rigid_body_info.solver_deactivation.name
        b_col_obj.nif_collision.quality_type = n_rigid_body_info.quality_type.name

        b_col_obj.nif_collision.body_flags = n_bhk_rigid_body.body_flags

        # Apply NifSkope-like wireframe color
        b_col_obj.color = self.LAYER_WIREFRAME_COLOR_MAP[n_rigid_body_info.havok_filter.layer.value %
                                                         len(self.LAYER_WIREFRAME_COLOR_MAP)]
        b_col_obj.visible_camera = False

        # Import constraints
        # This is done once all objects are imported for now, store all imported havok shapes with object lists
        collision.DICT_HAVOK_OBJECTS[n_bhk_rigid_body] = b_col_obj

    def import_bhk_shape(self, n_bhk_shape):
        NifLog.debug(f"Importing {n_bhk_shape.__class__.__name__}")
        return self.process_bhk(n_bhk_shape)

    def import_bhk_mopp_bv_tree_shape(self, bhk_shape):
        NifLog.debug(f"Importing {bhk_shape.__class__.__name__}")
        return self.process_bhk(bhk_shape.shape)

    def import_bhk_list_shape(self, bhk_list_shape):
        """Imports a BhkListShape block as a compound parent collision object."""
        NifLog.debug(f"Importing {bhk_list_shape.__class__.__name__}")

        # Create the parent collision object
        name = "collision_list"
        b_me = bpy.data.meshes.new(name)
        b_col_obj = Object.create_b_obj(None, b_me, name)
        self.set_b_collider(b_col_obj, bounds_type="COMPOUND", radius=0, n_obj=bhk_list_shape)

        # Import all subshapes and parent them to the list shape
        for subshape in bhk_list_shape.sub_shapes:
            b_subshape_obj = self.import_bhk_shape(subshape)
            if b_subshape_obj:  # Only parent if the object exists
                b_subshape_obj.parent = b_col_obj

        return b_col_obj

    def import_bhk_simple_shape_phantom(self, n_bhk_simple_shape_phantom):
        """Imports a bhkSimpleShapePhantom block and applies the transform to the collision object"""

        # import shapes
        b_col_obj = self.import_bhk_shape(n_bhk_simple_shape_phantom.shape)
        NifLog.warn("Support for bhkSimpleShapePhantom is limited, transform is ignored")
        # todo [pyffi/collision] current nifskope shows a transform, our nif xml doesn't, so ignore it for now
        # # find transformation matrix
        # transform = mathutils.Matrix(bhkshape.transform.as_list())
        #
        # # fix scale
        # transform.translation = transform.translation * self.HAVOK_SCALE
        #
        # # apply transform
        # for b_col_obj in collision_objs:
        #     b_col_obj.matrix_local = b_col_obj.matrix_local @ transform
        # return a list of transformed collision shapes
        return b_col_obj

    def import_bhktransform(self, n_bhk_transform_shape):
        """Imports a BhkTransformShape block and applies the transform to the collision object."""

        return self._import_bhk_transform(n_bhk_transform_shape)

    def import_bhk_convex_transform(self, n_bhk_convex_transform_shape):
        """Imports a BhkConvexTransformShape block and applies the transform to the collision object."""

        return self._import_bhk_transform(n_bhk_convex_transform_shape)

    def _import_bhk_transform(self, n_bhk_transform_shape):
        # import shapes
        b_col_obj = self.import_bhk_shape(n_bhk_transform_shape.shape)
        # find transformation matrix
        transform = mathutils.Matrix(n_bhk_transform_shape.transform.as_list())

        # fix scale
        transform.translation = transform.translation * self.HAVOK_SCALE

        # apply transform
        b_col_obj.matrix_local = b_col_obj.matrix_local @ transform
        # return a list of transformed collision shapes
        return b_col_obj

    def import_bhkbox_shape(self, n_bhk_box_shape):
        """Import a BhkBox block as a simple Box collision object."""

        NifLog.debug(f"Importing {n_bhk_box_shape.__class__.__name__}")

        # create box
        r = n_bhk_box_shape.radius * self.HAVOK_SCALE
        dims = n_bhk_box_shape.dimensions
        minx = -dims.x * self.HAVOK_SCALE
        maxx = +dims.x * self.HAVOK_SCALE
        miny = -dims.y * self.HAVOK_SCALE
        maxy = +dims.y * self.HAVOK_SCALE
        minz = -dims.z * self.HAVOK_SCALE
        maxz = +dims.z * self.HAVOK_SCALE

        # create blender object
        b_col_obj = Object.box_from_extents("collision_box", minx, maxx, miny, maxy, minz, maxz)
        self.set_b_collider(b_col_obj, radius=r, n_obj=n_bhk_box_shape, display_type='BOX')
        return b_col_obj

    def import_bhksphere_shape(self, n_bhk_sphere_shape):
        """Import a BhkSphere block as a simple sphere collision object"""
        NifLog.debug(f"Importing {n_bhk_sphere_shape.__class__.__name__}")

        r = n_bhk_sphere_shape.radius * self.HAVOK_SCALE
        b_col_obj = Object.box_from_extents("collision_sphere", -r, r, -r, r, -r, r)
        self.set_b_collider(b_col_obj, display_type="SPHERE", bounds_type='SPHERE', radius=r, n_obj=n_bhk_sphere_shape)
        return b_col_obj

    def import_bhkcapsule_shape(self, n_bhk_capsule_shape):
        """Import a BhkCapsule block as a simple cylinder collision object."""

        NifLog.debug(f"Importing {n_bhk_capsule_shape.__class__.__name__}")

        radius = n_bhk_capsule_shape.radius * self.HAVOK_SCALE
        p_1 = n_bhk_capsule_shape.first_point
        p_2 = n_bhk_capsule_shape.second_point
        length = (p_1 - p_2).norm() * self.HAVOK_SCALE
        first_point = p_1 * self.HAVOK_SCALE
        second_point = p_2 * self.HAVOK_SCALE
        minx = miny = -radius
        maxx = maxy = +radius
        minz = -radius - length / 2
        maxz = length / 2 + radius

        # create blender object
        b_col_obj = Object.box_from_extents("collision_capsule", minx, maxx, miny, maxy, minz, maxz)
        # here, these are not encoded as a direction so we must first calculate the direction
        b_col_obj.matrix_local = self.center_origin_to_matrix((first_point + second_point) / 2,
                                                              first_point - second_point)
        self.set_b_collider(b_col_obj, bounds_type="CAPSULE", display_type="CAPSULE", radius=radius,
                            n_obj=n_bhk_capsule_shape)
        return b_col_obj

    def import_bhkconvex_vertices_shape(self, n_bhk_convex_vertices_shape):
        """Import a BhkConvexVertex block as a convex hull collision object."""

        NifLog.debug(f"Importing {n_bhk_convex_vertices_shape.__class__.__name__}")

        # find vertices (and fix scale)
        scaled_verts = [(self.HAVOK_SCALE * n_vert.x, self.HAVOK_SCALE * n_vert.y, self.HAVOK_SCALE * n_vert.z)
                        for n_vert in n_bhk_convex_vertices_shape.vertices]
        if scaled_verts:
            verts, faces = qhull3d(scaled_verts)
        else:
            verts = []
            faces = []

        b_col_obj = Object.mesh_from_data("collision_convexpoly", verts, faces)
        radius = n_bhk_convex_vertices_shape.radius * self.HAVOK_SCALE
        self.set_b_collider(b_col_obj, bounds_type="CONVEX_HULL", radius=radius, n_obj=n_bhk_convex_vertices_shape)
        return b_col_obj

    def import_bhkpackednitristrips_shape(self, n_bhk_packed_nitristrips_shape):
        """Import a BhkPackedNiTriStrips block as a Triangle-Mesh collision object."""

        NifLog.debug(f"Importing {n_bhk_packed_nitristrips_shape.__class__.__name__}")

        # Create mesh for each sub shape
        all_verts = []
        all_faces = []
        material_map = {}  # Map of material names to material indices
        material_indices = []
        vertex_offset = 0
        subshapes = n_bhk_packed_nitristrips_shape.sub_shapes

        if not subshapes:
            # Fallout 3 stores them in the data
            subshapes = n_bhk_packed_nitristrips_shape.data.sub_shapes

        for subshape_num, subshape in enumerate(subshapes):
            verts = []
            faces = []
            for vert_index in range(vertex_offset, vertex_offset + subshape.num_vertices):
                n_vert = n_bhk_packed_nitristrips_shape.data.vertices[vert_index]
                verts.append((n_vert.x * self.HAVOK_SCALE,
                              n_vert.y * self.HAVOK_SCALE,
                              n_vert.z * self.HAVOK_SCALE))

            for bhk_triangle in n_bhk_packed_nitristrips_shape.data.triangles:
                bhk_tri = bhk_triangle.triangle
                if vertex_offset <= bhk_tri.v_1 < vertex_offset + subshape.num_vertices:
                    faces.append((bhk_tri.v_1 - vertex_offset,
                                  bhk_tri.v_2 - vertex_offset,
                                  bhk_tri.v_3 - vertex_offset))
                    # Assign the material index for this face
                    havok_material = getattr(subshape, 'material', None)
                    if havok_material:
                        if hasattr(havok_material, "material"):
                            mat_enum = havok_material.material
                            mat_name = mat_enum.name
                            b_mat = collision.get_material(mat_name)
                            if b_mat not in material_map:
                                material_map[b_mat] = len(material_map)

                            material_indices.append(material_map[b_mat])

            # Extend global lists with this subshape's data
            all_verts.extend(verts)
            all_faces.extend([(v1 + vertex_offset, v2 + vertex_offset, v3 + vertex_offset) for v1, v2, v3 in faces])
            vertex_offset += subshape.num_vertices

        # Create a single mesh object with all vertices and faces
        b_col_obj = Object.mesh_from_data("collision_poly", all_verts, all_faces)
        b_me = b_col_obj.data

        for b_mapped_mat in material_map.keys():
            b_me.materials.append(b_mapped_mat)

        for poly, mat_index in zip(b_me.polygons, material_indices):
            poly.material_index = mat_index

        radius = min(vert.co.length for vert in b_me.vertices)
        self.set_b_collider(b_col_obj, radius, bounds_type="MESH")
        return b_col_obj

    def import_bhk_nitristrips_shape(self, n_bhk_nitristrips_shape):
        return reduce(operator.add, (self.import_bhk_shape(strips) for strips in n_bhk_nitristrips_shape.strips_data))

    def import_nitristrips(self, n_nitristrips):
        """Import a NiTriStrips block as a Triangle-Mesh collision object."""

        # No factor 7 correction!!!
        verts = [(v.x, v.y, v.z) for v in n_nitristrips.vertices]
        faces = list(n_nitristrips.get_triangles())
        b_col_obj = Object.mesh_from_data("collision_poly", verts, faces)
        # TODO [collision] self.havok_mat!
        self.set_b_collider(b_col_obj, n_nitristrips.bounding_sphere.radius, bounds_type="MESH")
        return b_col_obj
