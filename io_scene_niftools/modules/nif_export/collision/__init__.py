"""Classes for exporting NIF collision blocks."""

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

from ....modules.nif_export.block_registry import block_store

from ....modules.nif_export.collision.bound import Bound, NiCollision
from ....modules.nif_export.collision.havok import BhkCollision
from ....modules.nif_export.collision.havok.animation import BhkBlendCollision
from ....utils.logging import NifLog, NifError

from nifgen.formats.nif import classes as NifClasses


class Collision:
    """Main interface class for exporting NIF collision blocks."""

    def __init__(self):
        self.bhk_collision_helper = BhkCollision()
        self.bhk_blend_collision_helper = BhkBlendCollision()
        self.bound_helper = Bound()
        self.ni_collision_helper = NiCollision()
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_collision(self, b_collision_objects):
        """Main function for handling collision export."""

        NifLog.info(f"Exporting collision...")

        if not b_collision_objects:
            return  # No collision data in the scene

        for b_col_obj in b_collision_objects:

            # Skip bhkListShape sub-shapes for now
            if b_col_obj.parent and b_col_obj.parent.rigid_body:
                continue

            with NifLog.context(f"exporting collision object '{b_col_obj.name}'"):
                self.export_collision_object(b_col_obj)

    def export_collision_object(self, b_col_obj):
        """Export a single collision object."""

        # Get parent node from object dictionary
        if b_col_obj.parent and b_col_obj.parent_type == 'BONE':
            # attach to the node of the bone this collision object is parented to
            b_parent_bone = b_col_obj.parent.data.bones[b_col_obj.parent_bone]
            n_parent_nodes = [k for k, v in block_store.block_to_obj.items() if v == b_parent_bone]
            if not n_parent_nodes:
                raise NifError(f"Collision object '{b_col_obj.name}' is parented to bone "
                               f"'{b_col_obj.parent_bone}', which was not exported. "
                               f"Make sure the armature '{b_col_obj.parent.name}' is included in the export.")
            n_parent_node = n_parent_nodes[0]
        elif b_col_obj.parent:
            #n_parent_node = DICT_NAMES[b_col_obj.parent.name]
            n_parent_node = block_store.obj_to_block.get(b_col_obj.parent)
            if n_parent_node is None:
                raise NifError(f"Collision object '{b_col_obj.name}' is parented to '{b_col_obj.parent.name}', "
                               f"which was not exported as a node. "
                               f"Make sure the parent object is included in the export.")
        else:
            n_parent_node = block_store.obj_to_block.get(b_col_obj)
            if n_parent_node is None:
                raise NifError(f"Collision object '{b_col_obj.name}' has no parent node to attach to. "
                               f"Parent it to the object or bone whose collision it represents.")

        if "bound" in b_col_obj.name.lower():
            # Export bounding boxes
            if self.target_game == 'MORROWIND':
                # Export Morrowind NiNode bounding box
                self.bound_helper.export_bounds(b_col_obj, n_parent_node, bsbound=False)
            else:
                # Export BSBound
                self.bound_helper.export_bounds(b_col_obj, n_parent_node, bsbound=True)
            return

        if bpy.context.scene.niftools_scene.is_bs():
            # Export Bethesda/Havok collision objects
            layer = int(b_col_obj.nif_collision.collision_layer)

            if b_col_obj.nif_collision.use_blend_collision:
                # attaching it here means the havok exporter fills in this block rather than
                # creating a plain bhkCollisionObject of its own
                n_col_obj = self.bhk_blend_collision_helper.export_bhk_blend_collision(
                    b_col_obj, n_parent_node, layer)
                n_parent_node.collision_object = n_col_obj
                n_col_obj.target = n_parent_node

            self.bhk_collision_helper.export_bhk_collision(b_col_obj, n_parent_node, layer)

        elif self.target_game in ('ZOO_TYCOON_2',):
            self.ni_collision_helper.export_nicollisiondata(b_col_obj, n_parent_node)

        else:
            NifLog.warn(f"Collision not supported for game '{self.target_game}', "
                        f"skipped collision object '{b_col_obj.name}'")
