"""Main module for exporting geometry data."""

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


import numpy as np

import bpy
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, NifData
from nifgen.formats.nif import classes as NifClasses


class GeometryData:

    def get_geom_data(self, b_mesh, color, normal, uv, tangent, b_mat_index):
        """
        Converts the blender information in b_mesh to a triangles, a dictionary with vertex information and a
        mapping of the blender vertices to nif vertices.

        :param b_mesh: Blender Mesh object
        :type b_mesh: class:`bpy.types.Mesh`
        :param color: Whether to consider vertex colors
        :type color: bool
        :param normal: Whether to consider vertex normals
        :type normal: bool
        :param uv: Whether to consider UV coordinates
        :type uv: bool
        :param tangent: Whether to consider tangents and bitangents
        :type tangent: bool
        :param b_mat_index: Material index to filter on. -1 means no filtering
        :type b_mat_index: int

        :return: the triangles, triangle to polygon array, dict of vertex information and nif vertex to blender vertex array
        :rtype: tuple(np.ndarray, np.ndarray, dict(str, np.ndarray), np.ndarray)
        The dictionary can contain the following information:
        POSITION: position
        COLOR: vertex colors
        NORMAL: normal vectors per vertex
        UV: list of  UV coordinates per vertex per layer. vertex_dict['UV'][0][1] gives UV coordinates for the first vertex, second layer
        TANGENT: tangent vector per vertex
        BITANGENT: bitangent per vertex, always present if TANGENT is present

        NIF has one uv vertex, one normal, one color etc per vertex
        NIF uses the normal table for lighting.
        Smooth faces should use Blender's vertex normals,
        solid faces should use Blender's face normals.

        Blender's uv vertices and normals are per face.
        Blender supports per face vertex coloring.
        Blender loops, on the other hand, are much like nif vertices, and refer to one vertex associated with a polygon

        The algorithm merges loops with the same information (as long as they have the same original vertex) and
        triangulates the mesh without needing a triangulation modifier.
        """

        n_loops = len(b_mesh.loops)
        n_verts = len(b_mesh.vertices)
        n_tris = len(b_mesh.loop_triangles)

        if b_mat_index >= 0:
            loop_mat_indices = np.ones(n_loops, dtype=int) * -1
            for poly in b_mesh.polygons:
                loop_mat_indices[poly.loop_indices] = poly.material_index
            matl_to_loop = np.arange(n_loops, dtype=int)[loop_mat_indices == b_mat_index]
            del loop_mat_indices
        else:
            matl_to_loop = np.arange(n_loops, dtype=int)
        # for the loops without matl equivalent, use len(matl_to_loop) to exceed the length of the matl array
        loop_to_matl = np.ones(n_loops, dtype=int) * len(matl_to_loop)
        loop_to_matl[matl_to_loop] = np.arange(len(matl_to_loop), dtype=int)

        loop_hashes = np.zeros((len(matl_to_loop), 0), dtype=float)

        loop_to_vert = np.zeros(n_loops, dtype=int)
        b_mesh.loops.foreach_get('vertex_index', loop_to_vert)
        matl_to_vert = loop_to_vert[matl_to_loop]
        loop_hashes = np.concatenate((loop_hashes, matl_to_vert.reshape((-1, 1))), axis=1)

        vert_positions = np.zeros((n_verts, 3), dtype=float)
        b_mesh.vertices.foreach_get('co', vert_positions.reshape((-1, 1)))
        loop_positions = vert_positions[matl_to_vert]
        del vert_positions
        loop_hashes = np.concatenate((loop_hashes, loop_positions), axis=1)

        if color:
            loop_colors = np.zeros((n_loops, 4), dtype=float)
            if b_mesh.vertex_colors:
                b_mesh.vertex_colors[0].data.foreach_get('color', loop_colors.reshape((-1, 1)))
            else:
                # vertex information of face corner (loop) information
                # byte or float color, but both will give float values
                color_attr = b_mesh.color_attributes[0]
                if color_attr.domain == 'CORNER':
                    color_attr.data.foreach_get('color', loop_colors.reshape((-1, 1)))
                else:
                    vert_colors = np.zeros((n_verts, 4), dtype=float)
                    color_attr.data.foreach_get('color', vert_colors.reshape((-1, 1)))
                    loop_colors[:] = vert_colors[loop_to_vert]
                    del vert_colors
            loop_colors = loop_colors[matl_to_loop]
            loop_hashes = np.concatenate((loop_hashes, loop_colors), axis=1)

        if normal:
            # calculate normals
            loop_normals = np.zeros((n_loops, 3), dtype=float)
            b_mesh.loops.foreach_get('normal', loop_normals.reshape((-1, 1)))
            # smooth = vertex normal, non-smooth = face normal)
            for poly in b_mesh.polygons:
                if not poly.use_smooth:
                    loop_normals[poly.loop_indices] = poly.normal
            loop_normals = loop_normals[matl_to_loop]
            loop_hashes = np.concatenate((loop_hashes, loop_normals), axis=1)

        if uv:
            uv_layers = []
            for layer in b_mesh.uv_layers:
                loop_uv = np.zeros((n_loops, 2), dtype=float)
                layer.data.foreach_get('uv', loop_uv.reshape((-1, 1)))
                loop_uv = loop_uv[matl_to_loop]
                uv_layers.append(loop_uv)
                loop_hashes = np.concatenate((loop_hashes, loop_uv), axis=1)
            loop_uvs = np.swapaxes(uv_layers, 0, 1)
            del uv_layers

        if tangent:
            b_mesh.calc_tangents(uvmap=b_mesh.uv_layers[0].name)
            loop_tangents = np.zeros((n_loops, 3), dtype=float)
            b_mesh.loops.foreach_get('tangent', loop_tangents.reshape((-1, 1)))
            loop_tangents = loop_tangents[matl_to_loop]
            if NifOp.props.sep_tangent_space:
                loop_hashes = np.concatenate((loop_hashes, loop_tangents), axis=1)

            bitangent_signs = np.zeros((n_loops, 1), dtype=float)
            b_mesh.loops.foreach_get('bitangent_sign', bitangent_signs)
            bitangent_signs = bitangent_signs[matl_to_loop]
            loop_bitangents = bitangent_signs * np.cross(loop_normals, loop_tangents)
            if NifOp.props.sep_tangent_space:
                loop_hashes = np.concatenate((loop_hashes, loop_bitangents), axis=1)
            del bitangent_signs

        # now remove duplicates
        # first exact (also sorts by blender vertex)
        loop_hashes, hash_to_matl, matl_to_hash = np.unique(loop_hashes, return_index=True, return_inverse=True, axis=0)
        hash_to_same_hash = np.arange(len(loop_hashes), dtype=int)
        hash_to_nif_vert = np.arange(len(loop_hashes), dtype=int)
        # then inexact (if epsilon is not 0)
        if NifOp.props.epsilon > 0:

            current_vert = -1
            max_nif_vert = -1
            for hash_index, loop_hash in enumerate(loop_hashes):
                if loop_hash[0] != current_vert:
                    current_vert = loop_hash[0]
                    current_hash_start = hash_index

                nif_vert_index = max_nif_vert + 1
                for comp_index in range(current_hash_start, hash_index):
                    comp_loop_hash = loop_hashes[comp_index]
                    if any(np.abs(comp_loop_hash - loop_hash) > NifOp.props.epsilon):
                        # this hash is different, but others may be the same
                        continue
                    else:
                        nif_vert_index = hash_to_nif_vert[comp_index]
                        hash_to_same_hash[hash_index] = comp_index
                        break
                hash_to_nif_vert[hash_index] = nif_vert_index
                max_nif_vert = max((nif_vert_index, max_nif_vert))

        # finally, use the mapping from blender to nif to create the triangles
        # first get the actual triangles in an array
        blend_triangles = np.zeros((n_tris, 3), dtype=int)
        b_mesh.loop_triangles.foreach_get('loops', blend_triangles.reshape((-1, 1)))
        tri_to_poly = np.zeros(n_tris, dtype=int)
        b_mesh.loop_triangles.foreach_get('polygon_index', tri_to_poly)
        # filter out the ones not in the specified material
        triangle_mats = np.zeros(n_tris, dtype=int)
        b_mesh.loop_triangles.foreach_get('material_index', triangle_mats)
        mattri_to_looptri = np.arange(n_tris, dtype=int)
        if b_mat_index >= 0:
            mattri_to_looptri = mattri_to_looptri[triangle_mats == b_mat_index]
        blend_triangles = blend_triangles[mattri_to_looptri]
        tri_to_poly = tri_to_poly[mattri_to_looptri]
        # go from loop indices to nif vertices
        # [TODO] Possibly optimize later
        for i in range(len(blend_triangles)):
            blend_triangles[i] = hash_to_nif_vert[matl_to_hash[loop_to_matl[blend_triangles[i]]]]
        # sort the triangles on polygon index to keep the original order
        tri_sort = np.argsort(tri_to_poly, axis=0)
        tri_to_poly = tri_to_poly[tri_sort]
        blend_triangles = blend_triangles[tri_sort]

        # make the vertex data from the hash map
        nif_to_hash = np.unique(hash_to_same_hash, return_index=True)[1]
        nif_to_matl = hash_to_matl[nif_to_hash]
        data_dict = {
            'POSITION': loop_positions[nif_to_matl]
        }

        if color:
            data_dict['COLOR'] = loop_colors[nif_to_matl]
        if normal:
            data_dict['NORMAL'] = loop_normals[nif_to_matl]
        if uv:
            data_dict['UV'] = loop_uvs[nif_to_matl]
        if tangent:
            data_dict['TANGENT'] = loop_tangents[nif_to_matl]
            data_dict['BITANGENT'] = loop_bitangents[nif_to_matl]

        return blend_triangles, tri_to_poly, data_dict, loop_to_vert[matl_to_loop[nif_to_matl]]

    def set_geom_data(self, n_geom, triangles, vertex_information, b_uv_layers):
        if isinstance(n_geom, NifClasses.BSTriShape):
            self.set_bs_geom_data(n_geom, triangles, vertex_information, b_uv_layers)
        else:
            self.set_ni_geom_data(n_geom, triangles, vertex_information, b_uv_layers)

    def set_bs_geom_data(self, n_geom, triangles, vertex_information, b_uv_layers):
        """Sets the geometry data (triangles and flat lists of per-vertex data) to a BSGeometry block."""
        vertex_flags = n_geom.vertex_desc.vertex_attributes
        vertex_flags.vertex = True
        vertex_flags.u_vs = 'UV' in vertex_information
        vertex_flags.normals = 'NORMAL' in vertex_information
        vertex_flags.tangents = 'TANGENT' in vertex_information
        vertex_flags.vertex_colors = 'COLOR' in vertex_information
        n_geom.vertex_desc.vertex_attributes = vertex_flags
        vert_size = 0
        if vertex_flags.vertex:
            vert_size += 3
            vert_size += 1  # either unused W or bitangent X
        if vertex_flags.u_vs:
            vert_size += 1
        if vertex_flags.normals:
            vert_size += 1
        if vertex_flags.tangents:
            vert_size += 1
        if vertex_flags.vertex_colors:
            vert_size += 1
        n_geom.vertex_desc.vertex_data_size = vert_size

        n_geom.num_triangles = len(triangles)
        n_geom.num_vertices = len(vertex_information['POSITION'])
        # TODO: Maybe in future add function to generated code to use the calc attribute. For now, a copy of the xml.
        n_geom.data_size = ((n_geom.vertex_desc & 0xF) * n_geom.num_vertices * 4) + (n_geom.num_triangles * 6)

        n_geom.reset_field('vertex_data')
        for n_v, b_v in zip([data.vertex for data in n_geom.vertex_data], vertex_information['POSITION']):
            n_v.x, n_v.y, n_v.z = b_v
        if vertex_flags.u_vs:
            for n_uv, b_uv in zip([data.uv for data in n_geom.vertex_data], vertex_information['UV']):
                # NIF flips the texture V-coordinate (OpenGL standard)
                n_uv.u = b_uv[0][0]
                n_uv.v = 1.0 - b_uv[0][1]
        if vertex_flags.normals:
            for n_n, b_n in zip([data.normal for data in n_geom.vertex_data], vertex_information['NORMAL']):
                n_n.x, n_n.y, n_n.z = b_n
        if vertex_flags.tangents:
            # Tangents and bitangents are (mostly) stored as normbyte and therefore must be limited to [-1.0, 1.0]
            # However, Blender can sometimes give a value outside the bound due to rounding.
            vertex_information['BITANGENT'] = NifClasses.Normbyte.from_function(
                NifClasses.Normbyte.to_function(vertex_information['BITANGENT'])
            )
            vertex_information['TANGENT'] = NifClasses.Normbyte.from_function(
                NifClasses.Normbyte.to_function(vertex_information['TANGENT'])
            )
            # B_tan: +d(B_u), B_bit: +d(B_v) and N_tan: +d(N_v), N_bit: +d(N_u)
            # moreover, N_v = 1 - B_v, so d(B_v) = - d(N_v), therefore N_tan = -B_bit and N_bit = B_tan
            for n_t, b_t in zip([data.tangent for data in n_geom.vertex_data], vertex_information['BITANGENT']):
                n_t.x, n_t.y, n_t.z = -b_t
            for n_vert, b_b in zip(n_geom.vertex_data, vertex_information['TANGENT']):
                n_vert.bitangent_x, n_vert.bitangent_y, n_vert.bitangent_z = b_b
        if vertex_flags.vertex_colors:
            vertex_information['COLOR'] = np.rint(vertex_information['COLOR'] * 255).astype(int)
            for n_c, b_c in zip([data.vertex_colors for data in n_geom.vertex_data], vertex_information['COLOR']):
                n_c.r, n_c.g, n_c.b, n_c.a = b_c

        n_geom.update_center_radius()

        n_geom.reset_field('triangles')
        for n_tri, b_tri in zip(n_geom.triangles, triangles):
            n_tri.v_1 = b_tri[0]
            n_tri.v_2 = b_tri[1]
            n_tri.v_3 = b_tri[2]

    def set_ni_geom_data(self, n_geom, triangles, vertex_information, b_uv_layers):
        """Sets the geometry data (triangles and flat lists of per-vertex data) to a BSGeometry block."""

        # coords
        n_geom.data.num_vertices = len(vertex_information['POSITION'])
        n_geom.data.has_vertices = True
        n_geom.data.reset_field("vertices")
        for n_v, b_v in zip(n_geom.data.vertices, vertex_information['POSITION']):
            n_v.x, n_v.y, n_v.z = b_v
        n_geom.data.update_center_radius()
        # normals
        n_geom.data.has_normals = 'NORMAL' in vertex_information
        if n_geom.data.has_normals:
            n_geom.data.reset_field("normals")
            for n_v, b_v in zip(n_geom.data.normals, vertex_information['NORMAL']):
                n_v.x, n_v.y, n_v.z = b_v
        # tangents
        if 'TANGENT' in vertex_information:
            tangents = vertex_information['TANGENT']
            bitangents = vertex_information['BITANGENT']
            # B_tan: +d(B_u), B_bit: +d(B_v) and N_tan: +d(N_v), N_bit: +d(N_u)
            # moreover, N_v = 1 - B_v, so d(B_v) = - d(N_v), therefore N_tan = -B_bit and N_bit = B_tan
            self.add_defined_tangents(n_geom,
                                      tangents=-bitangents,
                                      bitangents=tangents,
                                      as_extra_data=(
                                              bpy.context.scene.niftools_scene.game == 'OBLIVION'))  # as binary extra data only for Oblivion
        # vertex_colors
        n_geom.data.has_vertex_colors = 'COLOR' in vertex_information
        if n_geom.data.has_vertex_colors:
            n_geom.data.reset_field("vertex_colors")
            for n_v, b_v in zip(n_geom.data.vertex_colors, vertex_information['COLOR']):
                n_v.r, n_v.g, n_v.b, n_v.a = b_v
        # uv_sets
        if bpy.context.scene.niftools_scene.nif_version == 0x14020007 and bpy.context.scene.niftools_scene.user_version_2:
            data_flags = n_geom.data.bs_data_flags
            data_flags.has_uv = len(b_uv_layers) > 0
            if len(b_uv_layers) > 1:
                NifLog.warn(f"More than one UV layers for game that doesn't support it, only using first UV layer")
        else:
            data_flags = n_geom.data.data_flags
            data_flags.num_uv_sets = len(b_uv_layers)

        if data_flags.has_uv:
            n_geom.data.reset_field("uv_sets")
            uv_coords = vertex_information['UV']
            for j, n_uv_set in enumerate(n_geom.data.uv_sets):
                for i, n_uv in enumerate(n_uv_set):
                    if len(uv_coords[i]) == 0:
                        continue  # skip non-uv textures
                    n_uv.u = uv_coords[i][j][0]
                    # NIF flips the texture V-coordinate (OpenGL standard)
                    n_uv.v = 1.0 - uv_coords[i][j][1]  # opengl standard
        # set triangles stitch strips for civ4
        n_geom.data.set_triangles(triangles, stitchstrips=True)

    def add_defined_tangents(self, n_geom, tangents, bitangents, as_extra_data):
        # check if size of tangents and bitangents is equal to num_vertices
        if not (len(tangents) == len(bitangents) == n_geom.data.num_vertices):
            raise NifError(f'Number of tangents or bitangents does not agree with number of vertices in {n_geom.name}')

        if as_extra_data:
            # if tangent space extra data already exists, use it
            # find possible extra data block
            extra_name = 'Tangent space (binormal & tangent vectors)'
            for extra in n_geom.get_extra_datas():
                if isinstance(extra, NifClasses.NiBinaryExtraData):
                    if extra.name == extra_name:
                        break
            else:
                # create a new block and link it
                extra = NifClasses.NiBinaryExtraData(NifData.data)
                extra.name = extra_name
                n_geom.add_extra_data(extra)
            # write the data
            extra.binary_data = np.concatenate((tangents, bitangents), axis=0).astype('<f').tobytes()
        else:
            # set tangent space flag
            n_geom.data.bs_data_flags.has_tangents = True
            n_geom.data.data_flags.nbt_method |= 1
            # XXX used to be 61440
            # XXX from Sid Meier's Railroad
            n_geom.data.reset_field("tangents")
            for n_v, b_v in zip(n_geom.data.tangents, tangents):
                n_v.x, n_v.y, n_v.z = b_v
            n_geom.data.reset_field("bitangents")
            for n_v, b_v in zip(n_geom.data.bitangents, bitangents):
                n_v.x, n_v.y, n_v.z = b_v
