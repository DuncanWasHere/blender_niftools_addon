"""Export and import meshes with wire materials."""

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

import bpy
import nose.tools

from integration import SingleNif
from integration.modules.scene import n_gen_header, b_gen_header
from integration.modules.geometry.trishape import b_gen_geometry, n_gen_geometry
from integration.modules.property.material import b_gen_material, n_gen_material
from integration.modules.property.wireframe import b_gen_wire, n_gen_wire


class TestWireframeProperty(SingleNif):
    """Test import/export of meshes with material based wireframe property."""

    g_path = "property/wireframe"
    g_name = "test_wire"
    b_name = "Cube"

    def b_create_header(self):
        b_gen_header.b_create_morrowind_info()

    def n_create_header(self):
        n_gen_header.n_create_header_morrowind(self.n_data)

    def b_create_data(self):
        b_obj = b_gen_geometry.b_create_base_geometry(self.b_name)
        b_mat = b_gen_material.b_create_material_block(b_obj)
        b_gen_material.b_create_set_default_material_property(b_mat)
        b_gen_wire.b_create_wireframe_property(b_mat)

    def b_check_data(self):
        b_obj = bpy.data.objects[self.b_name]
        b_gen_geometry.b_check_geom_obj(b_obj)
        b_mat = b_gen_material.b_check_material_block(b_obj)
        b_gen_wire.b_check_wire_property(b_mat)

    def n_create_data(self):
        n_gen_geometry.n_create_blocks(self.n_data)
        n_trishape = self.n_data.roots[0].children[0]
        n_gen_material.n_attach_material_prop(n_trishape)
        n_gen_wire.n_attach_wire_prop(n_trishape)  # add niwireframeprop
        return self.n_data
    
    def n_check_data(self):
        n_nitrishape = self.n_data.roots[0].children[0]
        n_gen_geometry.n_check_trishape(n_nitrishape)
        
        nose.tools.assert_equal(n_nitrishape.num_properties, 2)
        n_mat_prop = n_nitrishape.properties[1]    
        n_gen_material.n_check_material_block(n_mat_prop)
        
        n_wire_prop = n_nitrishape.properties[0]
        n_gen_wire.n_check_wire_property(n_wire_prop)
