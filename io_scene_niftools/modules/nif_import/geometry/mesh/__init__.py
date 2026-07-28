"""This module contains helper methods to import mesh data."""

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

import numpy as np

import bpy
import bmesh
import mathutils

import io_scene_niftools.utils.logging
from io_scene_niftools.modules.nif_import.animation.morph import MorphAnimation
from io_scene_niftools.modules.nif_import.geometry.vertex import Vertex
from io_scene_niftools.modules.nif_import.geometry.vertex.groups import VertexGroup
from io_scene_niftools.modules.nif_import.property.material import MaterialProperty
from io_scene_niftools.utils.logging import NifLog
from io_scene_niftools.utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses
from nifgen.formats.nif.nimesh.structs.DisplayList import DisplayList


class Mesh:
    supported_mesh_types = (NifClasses.BSTriShape, NifClasses.NiMesh, NifClasses.NiTriBasedGeom)

    def __init__(self):
        self.material_property_helper = MaterialProperty()
        self.morph_anim = MorphAnimation()

    def import_mesh(self, n_block, b_obj):
        """Creates and returns a raw mesh, or appends geometry data to group_mesh.

        :param n_block: The nif block whose mesh data to import.
        :type n_block: C{NiTriBasedGeom}
        :param b_obj: The mesh to which to append the geometry data. If C{None}, a new mesh is created.
        :type b_obj: A Blender object that has mesh data.
        """

        node_name = n_block.name
        NifLog.info(f"Importing mesh data for geometry '{node_name}'")
        b_mesh = b_obj.data

        assert isinstance(n_block, self.supported_mesh_types)

        vertices = []
        triangles = []
        uvs = None
        vertex_colors = None
        normals = None

        if isinstance(n_block, NifClasses.BSTriShape):
            vertex_attributes = n_block.vertex_desc.vertex_attributes
            vertex_data = n_block.get_vertex_data()
            if isinstance(n_block, NifClasses.BSDynamicTriShape):
                # for BSDynamicTriShapes, the vertex data is stored in 4-component vertices
                vertices = [(vertex.x, vertex.y, vertex.z) for vertex in n_block.vertices]
            elif vertex_attributes.vertex:
                vertices = [vertex.vertex for vertex in vertex_data]
            triangles = n_block.get_triangles()
            if vertex_attributes.u_vs:
                uvs = [[vertex.uv for vertex in vertex_data]]
            if vertex_attributes.vertex_colors:
                vertex_colors = [NifClasses.Color4.from_value(tuple(c / 255.0 for c in vertex.vertex_colors)) for vertex
                                 in vertex_data]
            if vertex_attributes.normals:
                normals = [vertex.normal for vertex in vertex_data]
        elif isinstance(n_block, NifClasses.NiMesh):
            # if it has a displaylist then the vertex data is encoded differently
            displaylist_data = n_block.geomdata_by_name("DISPLAYLIST", False, False)
            if len(displaylist_data) > 0:
                displaylist = DisplayList(displaylist_data)
                vertices_info, triangles, weights = displaylist.extract_mesh_data(n_block)
                vertices = vertices_info[0]
                normals = vertices_info[1]
                vertex_colors = [NifClasses.Color4.from_value(color) for color in vertices_info[2]]
                uvs = vertices_info[3]
            else:
                # get the data from the associated nidatastreams based on the description in the component semantics
                vertices.extend(n_block.geomdata_by_name("POSITION", sep_datastreams=False))
                vertices.extend(n_block.geomdata_by_name("POSITION_BP", sep_datastreams=False))
                triangles = n_block.get_triangles()
                uvs = n_block.geomdata_by_name("TEXCOORD")
                vertex_colors = n_block.geomdata_by_name("COLOR", sep_datastreams=False)
                if len(vertex_colors) == 0:
                    vertex_colors = None
                else:
                    vertex_colors = [NifClasses.Color4.from_value(color) for color in vertex_colors]
                normals = n_block.geomdata_by_name("NORMAL", sep_datastreams=False)
                normals.extend(n_block.geomdata_by_name("NORMAL_BP", sep_datastreams=False))
            if len(uvs) == 0:
                uvs = None
            else:
                uvs = [[NifClasses.TexCoord.from_value(tex_coord) for tex_coord in uv_coords] for uv_coords in uvs]
            if len(normals) == 0:
                normals = None
        elif isinstance(n_block, NifClasses.NiTriBasedGeom):
            n_tri_data = n_block.data

            if not n_tri_data:
                raise io_scene_niftools.utils.logging.NifError(f"No shape data in {node_name}")

            vertices = n_tri_data.vertices
            triangles = n_block.get_triangles()
            uvs = n_tri_data.uv_sets
            
            if n_tri_data.has_vertex_colors:
                vertex_colors = n_tri_data.vertex_colors

            if n_tri_data.has_normals:
                normals = n_tri_data.normals

        # Create raw mesh from vertices and triangles
        b_mesh.from_pydata(vertices, [], triangles)
        b_mesh.update()

        # Must set faces to smooth before setting custom normals, or the normals bug out!
        is_smooth = True if (not (normals is None) or n_block.is_skin()) else False
        self.set_face_smooth(b_mesh, is_smooth)

        # Store additional data layers
        if uvs is not None:
            Vertex.map_uv_layer(b_mesh, uvs)

        if vertex_colors is not None:
            self.map_vertex_colors(b_mesh, vertex_colors)

        if normals is not None:
            # In some cases, normals can be four-component structs instead of 3; discard the 4th.
            Vertex.map_normals(b_mesh, np.array(normals)[:, :3])

        self.material_property_helper.import_material_properties(n_block, b_obj)

        # Import skinning info, for meshes affected by bones
        if n_block.is_skin():
            VertexGroup.import_skin(n_block, b_obj)

        # import morph controller
        if NifOp.props.animation:
            self.morph_anim.import_morph_controller(n_block, b_obj)

        self.weld_and_mark_sharp(b_mesh, b_obj)
        b_mesh.update()

    @staticmethod
    def set_face_smooth(b_mesh, smooth):
        """Set face smoothing and material"""

        for poly in b_mesh.polygons:
            poly.use_smooth = smooth
            poly.material_index = 0  # only one material

    @staticmethod
    def weld_and_mark_sharp(
        b_mesh,
        b_obj,
        epsilon=1e-6,
        normal_threshold=0.999,
        node_name="mesh",
    ):
        """
        This should weld all duplicate vertices and convert the mesh to use Blender's face normals and smooth shading.
        Custom normals only exist for smooth edges that are duplicated in the nif due to UV/vertex color seams.
        Open edges without custom normals are marked as sharp.
        All overlapping edges are merged except when their parent faces have opposite normals to preserve backface shells.
        Leftover open edges are then smoothed for clarity.
        Custom split normals are removed after the operation as they are no longer needed.
        """

        def _pos_key_from_vec(vec, decimals=6):
            return (round(vec.x, decimals), round(vec.y, decimals), round(vec.z, decimals))

        def _edge_key_from_positions(pos_a, pos_b):
            return (pos_a, pos_b) if pos_a <= pos_b else (pos_b, pos_a)

        def _norm_aligned(n1, n2):
            return n1.dot(n2) > normal_threshold

        if len(b_mesh.vertices) == 0 or len(b_mesh.polygons) == 0 or len(b_mesh.loops) == 0:
            NifLog.debug(f"Skipping merge/sharp/seam: empty/degenerate mesh '{node_name}'")
            return

        loop_normals = [ln.normal.copy() for ln in b_mesh.loops]

        corner_normal_by_poly_vert = {}
        for poly in b_mesh.polygons:
            for li in poly.loop_indices:
                v_idx = b_mesh.loops[li].vertex_index
                corner_normal_by_poly_vert[(poly.index, v_idx)] = loop_normals[li]

        vertices_co = [v.co.copy() for v in b_mesh.vertices]

        edge_incidence = {}
        for poly in b_mesh.polygons:
            v_indices = list(poly.vertices)
            if len(v_indices) < 2:
                continue
            for i in range(len(v_indices)):
                vA_idx = v_indices[i]
                vB_idx = v_indices[(i + 1) % len(v_indices)]

                posA = _pos_key_from_vec(vertices_co[vA_idx])
                posB = _pos_key_from_vec(vertices_co[vB_idx])
                ekey = _edge_key_from_positions(posA, posB)

                nA = corner_normal_by_poly_vert.get((poly.index, vA_idx))
                nB = corner_normal_by_poly_vert.get((poly.index, vB_idx))
                edge_incidence.setdefault(ekey, []).append((nA, nB))

        sharp_edge_keys = set()
        manifold_edges = 0
        nonmanifold_edges = 0
        boundary_geo_edges = 0

        for ekey, entries in edge_incidence.items():
            if len(entries) == 1:
                boundary_geo_edges += 1
                continue
            if len(entries) != 2:
                nonmanifold_edges += 1
                continue

            manifold_edges += 1
            nA0, nB0 = entries[0]
            nA1, nB1 = entries[1]
            if nA0 is None or nB0 is None or nA1 is None or nB1 is None:
                continue

            direct = _norm_aligned(nA0, nA1) and _norm_aligned(nB0, nB1)
            swapped = _norm_aligned(nA0, nB1) and _norm_aligned(nB0, nA1)
            if not (direct or swapped):
                sharp_edge_keys.add(ekey)

        NifLog.debug(
            f"Sharp inference for '{node_name}': manifold={manifold_edges}, boundary_geo={boundary_geo_edges}, "
            f"nonmanifold={nonmanifold_edges}, sharp_keys={len(sharp_edge_keys)}"
        )

        bm = bmesh.new()
        bm.from_mesh(b_mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        initial_vert_count = len(bm.verts)

        boundary_position_map = {}
        for v in bm.verts:
            if any(e.is_boundary for e in v.link_edges):
                boundary_position_map.setdefault(_pos_key_from_vec(v.co), []).append(v)

        merged_buckets = 0
        buckets_skipped_opposite = 0

        for _, verts in boundary_position_map.items():
            if len(verts) < 2:
                continue

            # Avoid collapsing double-sided coplanar shells.
            face_normals = [f.normal.copy() for v in verts for f in v.link_faces]
            skip_bucket = False
            for i in range(len(face_normals)):
                ni = face_normals[i]
                for j in range(i + 1, len(face_normals)):
                    if ni.dot(face_normals[j]) < -normal_threshold:
                        skip_bucket = True
                        break
                if skip_bucket:
                    break

            if skip_bucket:
                buckets_skipped_opposite += 1
                continue

            before_bucket = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=verts, dist=epsilon)
            if len(bm.verts) < before_bucket:
                merged_buckets += 1

        final_vert_count = len(bm.verts)

        NifLog.debug(
            f"Merging done for '{node_name}': merged_buckets={merged_buckets}, "
            f"skipped_buckets_opposite={buckets_skipped_opposite}, verts_before={initial_vert_count}, "
            f"verts_after={final_vert_count}, merged_verts={initial_vert_count - final_vert_count}"
        )

        bm.to_mesh(b_mesh)
        bm.free()
        b_mesh.update()

        bm2 = bmesh.new()
        bm2.from_mesh(b_mesh)
        bm2.verts.ensure_lookup_table()
        bm2.edges.ensure_lookup_table()

        sharp_applied_inferred = 0
        for e in bm2.edges:
            pos0 = _pos_key_from_vec(e.verts[0].co)
            pos1 = _pos_key_from_vec(e.verts[1].co)
            ekey = _edge_key_from_positions(pos0, pos1)

            if ekey in sharp_edge_keys:
                e.smooth = False
                sharp_applied_inferred += 1

        bm2.to_mesh(b_mesh)
        bm2.free()
        b_mesh.update()

        bm3 = bmesh.new()
        bm3.from_mesh(b_mesh)
        bm3.edges.ensure_lookup_table()

        boundary_cleared = 0
        for e in bm3.edges:
            if e.is_boundary and not e.smooth:
                e.smooth = True
                boundary_cleared += 1

        bm3.to_mesh(b_mesh)
        bm3.free()
        b_mesh.update()

        NifLog.debug(
            f"Sharps applied on '{node_name}': inferred={sharp_applied_inferred}, boundary_cleared={boundary_cleared}"
        )

        try:
            attr_name = "custom_normal"
            if hasattr(b_mesh, "attributes") and attr_name in b_mesh.attributes:
                b_mesh.attributes.remove(b_mesh.attributes[attr_name])
                NifLog.debug(f"Removed attribute '{attr_name}' from mesh for '{node_name}'")

            b_mesh.calc_normals()
            b_mesh.update()

        except Exception as ex:
            NifLog.debug(f"Failed to remove custom normals attribute for '{node_name}': {ex!r}")
