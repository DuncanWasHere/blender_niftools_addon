"""Module for exporting Havok blend collision blocks."""

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


from .....modules.nif_export.block_registry import block_store
from .....modules.nif_export.collision.havok import BhkCollisionCommon
from .....utils import consts


class BhkBlendCollision(BhkCollisionCommon):
    """Class for exporting Havok blend collision blocks."""

    def export_bhk_blend_collision(self, b_col_obj, n_parent_node, n_hav_layer):
        """
        Export a bhkBlendCollisionObject and the bhkBlendController that goes with it.

        The two always come as a pair: every node in a vanilla Bethesda skeleton that has a
        blend collision object also has a blend controller, and neither is any use alone.
        """

        n_col_obj = block_store.create_block("bhkBlendCollisionObject", b_col_obj)
        n_col_obj.flags = self.get_collision_object_flags(b_col_obj, n_hav_layer)
        n_col_obj.heir_gain = b_col_obj.nif_collision.heir_gain
        n_col_obj.vel_gain = b_col_obj.nif_collision.vel_gain

        self.export_bhk_blend_controller(b_col_obj, n_parent_node)

        return n_col_obj

    def export_bhk_blend_controller(self, b_col_obj, n_parent_node):
        """Export the bhkBlendController that drives a blend collision object's node."""

        # registered without the object, whose obj_to_block entry belongs to the rigid body
        n_blend_ctrl = block_store.create_block("bhkBlendController")
        # the values every vanilla skeleton uses. The controller runs for no time at all
        n_blend_ctrl.flags = 0x4C
        n_blend_ctrl.frequency = 1.0
        n_blend_ctrl.phase = 0.0
        n_blend_ctrl.start_time = consts.FLOAT_MAX
        n_blend_ctrl.stop_time = consts.FLOAT_MIN
        n_blend_ctrl.keys = 0
        n_parent_node.add_controller(n_blend_ctrl)
        n_blend_ctrl.target = n_parent_node

        return n_blend_ctrl


""" # Oblivion skeleton export: check that all bones have a transform controller and transform interpolator
if bpy.context.scene.niftools_scene.game == 'OBLIVION' and file_base.lower() in ('skeleton', 'skeletonbeast'):
self.transform_anim_helper.add_dummy_controllers()"""
