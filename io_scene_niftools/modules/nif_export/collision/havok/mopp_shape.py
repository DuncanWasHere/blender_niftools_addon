"""Module for exporting Havok MOPP collision blocks."""

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
from io_scene_niftools.modules.nif_export.collision.havok import BhkCollisionCommon
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifData


class BhkMOPPShape(BhkCollisionCommon):
    """
    Class for exporting Havok MOPP collision blocks."""

    def export_bhk_mopp_shape(self, b_col_obj, n_bhk_rigid_body, n_hav_mat_list, n_hav_layer):
        """
        Export a tree of MOPP collision shape blocks and parent them to the given bhkRigidBody block.
        For each Blender object passed to this function, a new bhkMoppBvTreeShape block is created.
        Then a bhkPackedNiTriStripsShape block is created from the rigid body properties.
        Finally, an hkPackedNiTriStripsData block is created from the mesh and rigid body properties.
        Transforms will be applied if present.
        """

        self.HAVOK_SCALE = NifData.data.havok_scale

        # Export the MOPP block
        n_bhk_mopp_bv_tree_shape = self.__export_bhk_mopp_bv_tree_shape(b_col_obj, n_bhk_rigid_body)

        # Export the shape block
        n_bhk_packed_ni_tri_strips_shape = self.__export_bhk_packed_ni_tri_strips_shape(b_col_obj,
                                                                                        n_bhk_mopp_bv_tree_shape)

        # Export the shape data block
        self.__export_hk_packed_ni_tri_strips_data(b_col_obj, n_bhk_packed_ni_tri_strips_shape,
                                                   n_hav_layer, n_hav_mat_list)

    def __export_bhk_mopp_bv_tree_shape(self, b_col_obj, n_bhk_rigid_body):
        """
        Export and return a bhkMoppBvTreeShape block.
        It will be parented to the given bhkRigidBody block.
        The MOPP data will be filled in later by the Mopper tool.
        """

        n_bhk_mopp_bv_tree_shape = block_store.create_block("bhkMoppBvTreeShape", b_col_obj)
        n_bhk_rigid_body.shape = n_bhk_mopp_bv_tree_shape

        return n_bhk_mopp_bv_tree_shape

    def __export_bhk_packed_ni_tri_strips_shape(self, b_col_obj, n_bhk_mopp_bv_tree_shape):
        """
        Export and return a bhkPackedNiTriStripsShape block.
        It will be parented to the given bhkMoppBvTreeShape block.
        Its radius is set by the Blender rigid body's collision margin
        (defaults to 0.1 if not enabled).
        """

        n_bhk_packed_ni_tri_strips_shape = block_store.create_block("bhkPackedNiTriStripsShape", b_col_obj)

        b_rigid_body = b_col_obj.rigid_body

        scale = n_bhk_packed_ni_tri_strips_shape.scale
        scale.x = 1.0
        scale.y = 1.0
        scale.z = 1.0
        scale.w = 0
        n_bhk_packed_ni_tri_strips_shape.scale_copy = scale

        if b_rigid_body.use_margin:
            n_bhk_packed_ni_tri_strips_shape.radius = b_col_obj.rigid_body.collision_margin
            n_bhk_packed_ni_tri_strips_shape.radius_copy = b_col_obj.rigid_body.collision_margin
        else:
            n_bhk_packed_ni_tri_strips_shape.radius = 0.1
            n_bhk_packed_ni_tri_strips_shape.radius_copy = 0.1

        n_bhk_mopp_bv_tree_shape.shape = n_bhk_packed_ni_tri_strips_shape

        return n_bhk_packed_ni_tri_strips_shape

    def __export_hk_packed_ni_tri_strips_data(self, b_col_obj, n_bhk_packed_ni_tri_strips_shape,
                                              layer, n_hav_mat_list):
        """
        Export an hkPackedNiTriStripsData block.
        It will be parented to the given bhkPackedNiTriStripsShape block.
        A sub-shape will be created for each material set in the mesh.
        Transforms will be applied if present.
        """

        b_mesh = b_col_obj.data
        transform = math.get_object_bind(b_col_obj)
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
                sorted(enumerate(n_hav_mat_list), key=lambda item: item[1].value)
            )
        }
        n_hav_mat_list.sort(key=lambda mat: mat.value)

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

        # Export geometry for each material group
        for mat_idx in sorted(triangles_by_material.keys()):
            triangles = triangles_by_material[mat_idx]
            normals = normals_by_material[mat_idx]

            try:
                n_material = n_hav_mat_list[mat_idx]
            except IndexError:
                NifLog.warn(f"Material index {mat_idx} out of bounds! "
                            f"Using default material")
                n_material = n_hav_mat_list[0]

            # Collect unique vertices used by this material's triangles
            used_vertex_indices = {idx for tri in triangles for idx in tri}
            subshape_vertices = [transformed_vertices[idx] for idx in used_vertex_indices]

            # Map old vertex indices to new indices
            vertex_map = {old_idx: new_idx for new_idx, old_idx in enumerate(used_vertex_indices)}
            remapped_triangles = [[vertex_map[idx] for idx in tri] for tri in triangles]

            n_bhk_packed_ni_tri_strips_shape.add_shape(remapped_triangles, normals, subshape_vertices,
                                                       layer, n_material)
