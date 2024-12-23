"""Classes for exporting basic NIF objects."""

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
from io_scene_niftools.modules.nif_export import types
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.geometry import Geometry
from io_scene_niftools.modules.nif_export.object.armature import Armature
from io_scene_niftools.modules.nif_export.property.object import ObjectDataProperty
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog

DICT_NAMES = {} # Dictionary to map Blender object names to NIF blocks

class Object:
    """
    Main interface class for exporting basic NIF blocks
    (i.e., NiNode and subclasses).
    Geometry is handled by a helper class.
    """

    export_types = ('EMPTY', 'MESH', 'ARMATURE')

    def __init__(self):
        self.armature_helper = Armature()
        self.mesh_helper = Geometry()
        self.object_property_helper = ObjectDataProperty()

        self.b_exportable_objects = []

        self.n_root_node = None
        self.target_game = None

    def export_objects(self, b_root_objects, target_game, file_base):
        """
        Export the root node and all valid child objects into the NIF.
        Use Blender root object if there is only one, otherwise create a meta root.
        """

        self.target_game = target_game
        self.n_root_node = None

        if len(b_root_objects) == 1:
            # There is only one root object, so use it as the root
            b_obj = b_root_objects[0]
            self.export_object_hierarchy(b_obj,None, n_node_type=b_obj.niftools.nodetype)
        else:
            # There is more than one root object, so create a meta root
            NifLog.info(f"Created meta root because Blender scene had {len(b_root_objects)} root objects.")
            self.n_root_node = types.create_ninode()
            self.n_root_node.name = "Scene Root"
            for b_obj in b_root_objects:
                self.export_object_hierarchy(b_obj, self.n_root_node)

        # Export extra data
        self.object_property_helper.export_bs_x_flags(self.n_root_node, b_root_objects)
        self.object_property_helper.export_inventory_marker(self.n_root_node, b_obj)
        self.object_property_helper.export_weapon_location(self.n_root_node, b_obj)
        types.export_furniture_marker(self.n_root_node, file_base)

        return self.n_root_node

    def export_object_hierarchy(self, b_obj, n_parent_node, n_node_type=None):
        """
        Export a mesh/armature/empty object as a child of the given parent node.
        Export also all children of the object.

        :param n_parent_node:
        :param b_obj:
        """

        # Can we export this object?
        if not b_obj or not b_obj in self.b_exportable_objects:
            return None

        if b_obj.type == 'MESH':
            # Export a geometry block

            # If this mesh has children or more than one material it gets wrapped in a purpose-made NiNode
            is_multi_material = len(set([f.material_index for f in b_obj.data.polygons])) > 1

            # Export a single NiGeometry block
            if not (b_obj.children or is_multi_material):
                n_ni_geometry = self.mesh_helper.export_geometry(b_obj, n_parent_node, self.n_root_node)
                if not self.n_root_node:
                    self.n_root_node = n_ni_geometry
                return n_ni_geometry

            # Mesh with armature parent should not have animation!
            if b_obj.parent and b_obj.parent.type == 'ARMATURE' and b_obj.animation_data.action:
                NifLog.warn(f"Mesh {b_obj.name} is skinned but also has object animation. "
                            f"The NIF format does not support this. Ignoring..")

        # Everything else (empty/armature) is a node
        n_node = types.create_ninode(b_obj, n_node_type=n_node_type)

        if not self.n_root_node:
            self.n_root_node = n_node

        # Make it a child of its parent in the NIF, if it has one
        if n_parent_node:
            n_parent_node.add_child(n_node)

        # And fill in this node's properties
        n_node.name = block_store.get_full_name(b_obj) # Name
        self.set_object_flags(b_obj, n_node) # Object Flags
        math.set_object_matrix(b_obj, n_node) # Transforms

        self.object_property_helper.export_upb(n_node, b_obj) # Extra Data

        if b_obj.type == 'MESH':
            # If b_obj is a multi-material mesh, export the geometries as children of this node
            n_ni_geometry = self.mesh_helper.export_geometry(b_obj, n_node, self.n_root_node)
        elif b_obj.type == 'ARMATURE':
            # If b_obj is an armature, export the bones as node children of this node
            self.armature_helper.export_bones(b_obj, n_node)
            # Special case: objects parented to armature bones
            for b_child in b_obj.children:
                # Find and attach to the right NiNode
                if b_child.parent_bone:
                    b_obj_bone = b_obj.data.bones[b_child.parent_bone]
                    # Find the correct n_node
                    # TODO [object]: This is essentially the same as Geometry.get_bone_block()
                    n_node = [k for k, v in block_store.block_to_obj.items() if v == b_obj_bone][0]
                    self.export_object_hierarchy(b_child, n_node)
                # Just child of the armature itself, so attach to armature root
                else:
                    self.export_object_hierarchy(b_child, n_node)
        else:
            # Export all children of this empty object as children of this node
            for b_child in b_obj.children:
                self.export_object_hierarchy(b_child, n_node)

        DICT_NAMES[b_obj.name] = n_node
        return n_node

    def get_export_objects(self):
        """
        Get all exportable objects.
        Separate into lists for root nodes, collision objects, constraints, and particle systems.
        """

        # Only export empties, meshes, and armatures
        self.b_exportable_objects = [b_obj for b_obj in bpy.context.scene.objects if b_obj.type in self.export_types]

        # Find all objects that do not have a parent
        b_root_objects = [b_obj for b_obj in self.b_exportable_objects if not b_obj.parent]

        # Split collision objects into separate list
        b_collision_objects = [b_obj for b_obj in self.b_exportable_objects if b_obj.rigid_body]
        for b_obj in b_collision_objects:
            if b_obj in self.b_exportable_objects:
                self.b_exportable_objects.remove(b_obj)
            if b_obj in b_root_objects:
                NifLog.warn(f"Collision object {b_obj} is a root node. "
                            f"It will be exported under a dummy parent node.")
                b_collision_objects.remove(b_obj)

        # Split constraints into separate list
        b_constraint_objects = [b_obj for b_obj in self.b_exportable_objects if b_obj.rigid_body_constraint]
        for b_obj in b_constraint_objects:
            if b_obj in self.b_exportable_objects:
                self.b_exportable_objects.remove(b_obj)
            if b_obj in b_root_objects:
                NifLog.warn(f"Constraint {b_obj} is a root node. "
                            f"It will be exported under a dummy parent node.")
                b_constraint_objects.remove(b_obj)
                
        # Split particle systems into separate list
        b_particle_objects = [b_obj for b_obj in self.b_exportable_objects if b_obj.particle_systems]
        for b_obj in b_particle_objects:
            if b_obj in self.b_exportable_objects:
                self.b_exportable_objects.remove(b_obj)
            if b_obj in b_root_objects:
                NifLog.warn(f"Particle system {b_obj} is a root node. "
                            f"It will be exported under a dummy parent node.")

        return (self.b_exportable_objects,
                b_root_objects,
                b_collision_objects,
                b_constraint_objects,
                b_particle_objects)

    def set_object_flags(self, b_obj, n_node):
        """Set node object flags if not already set in the properties panel."""

        # Default object flags
        if b_obj.niftools.flags != 0:
            n_node.flags = b_obj.niftools.flags
        else:
            if bpy.context.scene.niftools_scene.is_bs():
                n_node.flags = 0x000E
            elif self.target_game in ('SID_MEIER_S_RAILROADS', 'CIVILIZATION_IV'):
                n_node.flags = 0x0010
            elif self.target_game == 'EMPIRE_EARTH_II':
                n_node.flags = 0x0002
            elif self.target_game == 'DIVINITY_2':
                n_node.flags = 0x0310
            else:
                n_node.flags = 0x000C # Morrowind
