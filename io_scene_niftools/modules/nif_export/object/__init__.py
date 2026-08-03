"""Classes for exporting basic NIF objects."""

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


import bpy

from ....modules.nif_export import types
from ....modules.nif_export.block_registry import block_store
from ....modules.nif_export.geometry import Geometry
from ....modules.nif_export.object.armature import Armature
from ....modules.nif_export.property.object import ObjectProperty
from ....utils import math
from ....utils.flags import to_unsigned_32
from ....utils.logging import NifLog

from nifgen.formats.nif import classes as NifClasses

DICT_NAMES = {}  # Dictionary to map Blender object names to NIF blocks


class Object:
    """
    Main interface class for exporting basic NIF blocks
    (i.e., NiNode and subclasses).
    Geometry is handled by a helper class.
    """

    def __init__(self):
        self.armature_helper = Armature()
        self.mesh_helper = Geometry()
        self.object_property_helper = ObjectProperty()

        self.b_exportable_objects = []

        self.n_root_node = None
        self.target_game = None

    def export_objects(self, b_root_objects, b_exportable_objects, b_collision_objects, target_game, file_base):
        """
        Export the root node and all valid child objects into the NIF.
        Use Blender root object if there is only one, otherwise create a meta root.
        """

        self.b_exportable_objects = b_exportable_objects
        self.target_game = target_game
        self.n_root_node = None

        if len(b_root_objects) == 1:
            # There is only one root object, so use it as the root
            b_obj = b_root_objects[0]
            self.export_object_hierarchy(b_obj, None, n_node_type=b_obj.nif_object.nodetype)
        else:
            # There is more than one root object, so create a meta root
            NifLog.info(f"Created meta root because Blender scene had {len(b_root_objects)} root objects.")
            self.n_root_node = types.create_ninode()
            self.n_root_node.name = "Scene Root"
            for b_obj in b_root_objects:
                self.export_object_hierarchy(b_obj, self.n_root_node)

        if not self.n_root_node:
            # every root object is of a kind that is not exported as a node of its own
            # (a particle system, for instance), so the nif still needs a root to hold them
            NifLog.info("Created meta root because no root object was exported as a node.")
            self.n_root_node = types.create_ninode()
            self.n_root_node.name = "Scene Root"

        # Export extra data
        self.object_property_helper.export_root_node_properties(self.n_root_node, b_root_objects,
                                                                b_exportable_objects, b_collision_objects)
        types.export_furniture_marker(self.n_root_node, file_base)

        return self.n_root_node

    def export_object_hierarchy(self, b_obj, n_parent_node, n_node_type=None):
        """
        Export a mesh/armature/empty object as a child of the given parent node.
        Export also all children of the object.

        :param n_parent_node:
        :param b_obj:
        :param n_node_type:
        """

        # Can we export this Blender object?
        if not b_obj or not b_obj in self.b_exportable_objects:
            return False

        with NifLog.context(f"exporting {b_obj.type.lower()} object '{b_obj.name}'"):
            return self._export_object_hierarchy(b_obj, n_parent_node, n_node_type)

    def _export_object_hierarchy(self, b_obj, n_parent_node, n_node_type=None):
        """
        Export a single object and its children; see export_object_hierarchy.

        Returns whether the object produced a block of its own, which is what tells a
        NiLODNode parent which of its children became LOD levels.
        """

        if b_obj.type == 'MESH':
            # Export a geometry block
            if b_obj.parent and b_obj.parent.type == 'ARMATURE' and b_obj.animation_data and b_obj.animation_data.action:
                NifLog.warn(f"Mesh {b_obj.name} is skinned but also has object animation! "
                            f"The NIF format does not support this. Ignoring...")

            if not self.n_root_node:
                self.n_root_node = block_store.create_block("NiNode")
                n_parent_node = self.n_root_node

            self.mesh_helper.export_geometry(b_obj, n_parent_node, self.n_root_node)

            return True

        if b_obj.type in ('CAMERA', 'LIGHT'):
            return self._export_aimed_object(b_obj, n_parent_node)

        # Everything else (empty/armature) is a node
        n_node = types.create_ninode(b_obj, n_node_type=n_node_type)
        DICT_NAMES[b_obj.name] = n_node

        if not self.n_root_node:
            self.n_root_node = n_node

        self.set_object_fields(b_obj, n_node, n_parent_node)
        n_node.name = block_store.get_full_name(b_obj)

        if b_obj.type == 'ARMATURE':
            # If b_obj is an armature, export the bones as node children of this node
            self.armature_helper.export_bones(b_obj, n_node)
            # Special case: objects parented to armature bones
            for b_child in b_obj.children:
                # Find and attach to the right NiNode
                if b_child.parent_bone:
                    b_obj_bone = b_obj.data.bones[b_child.parent_bone]
                    # Find the correct n_node
                    # TODO [object]: This is essentially the same as Geometry.get_bone_block()
                    n_bone_node = [k for k, v in block_store.block_to_obj.items() if v == b_obj_bone][0]
                    self.export_object_hierarchy(b_child, n_bone_node)
                # Just child of the armature itself, so attach to armature root
                else:
                    self.export_object_hierarchy(b_child, n_node)
        else:
            # Export all children of this empty object as children of this node
            b_exported_children = []
            for b_child in b_obj.children:
                if b_child.nif_object.node_multi_bound.is_bound_helper:
                    # the bound of a BSMultiBoundNode, not a node in its own right
                    continue
                if self.export_object_hierarchy(b_child, n_node):
                    b_exported_children.append(b_child)

            if isinstance(n_node, NifClasses.NiLODNode):
                # the levels are matched to children by position, so this has to wait until
                # the children that actually made it into the nif are known
                types.export_lod_data(n_node, b_obj, b_exported_children)

            types.export_multi_bound(b_obj, n_node)

        return True

    def _export_aimed_object(self, b_obj, n_parent_node):
        """
        Export a camera or light, whose block aims along the nif's forward axis rather than
        Blender's, and which cannot hold children because it is not a NiNode.
        """

        if b_obj.type == 'CAMERA':
            n_block = types.create_camera(b_obj)
        else:
            n_block = types.create_light(b_obj)
        if n_block is None:
            return False

        if n_parent_node:
            n_parent_node.add_child(n_block)
        if not self.n_root_node:
            self.n_root_node = n_block

        math.set_aimed_object_matrix(b_obj, n_block)
        self.set_object_flags(b_obj, n_block)
        n_block.name = block_store.get_full_name(b_obj)
        DICT_NAMES[b_obj.name] = n_block

        # a NiCamera or NiLight has no children list, so anything parented to it in Blender
        # is attached to the node above instead rather than being dropped
        for b_child in b_obj.children:
            if b_child in self.b_exportable_objects:
                NifLog.warn(f"'{b_child.name}' is parented to '{b_obj.name}', which exports as "
                            f"a {type(n_block).__name__} and cannot hold children. "
                            f"It was attached to the node above instead.")
                self.export_object_hierarchy(b_child, n_parent_node)

        return True

    def set_object_fields(self, b_obj, n_node, n_parent_node=None):
        if n_parent_node:
            n_parent_node.add_child(n_node)

        math.set_object_matrix(b_obj, n_node)
        self.set_object_flags(b_obj, n_node)

    def set_object_flags(self, b_obj, n_node):
        """Set node object flags if not already set in the properties panel."""

        # Default object flags
        if b_obj.nif_object.flags != 0:
            n_node.flags = to_unsigned_32(b_obj.nif_object.flags)
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
                n_node.flags = 0x000C  # Morrowind
