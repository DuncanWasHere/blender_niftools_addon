"""This script contains classes to help import bhk animations."""

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


from io_scene_niftools.utils import consts

from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.collision.havok import BhkCollisionCommon


class BhkBlendCollision(BhkCollisionCommon):

    def export_bhk_blend_collision(self, b_obj):
        n_col_obj = block_store.create_block("bhkBlendCollisionObject", b_obj)
        n_col_obj.unknown_float_1 = 1.0
        n_col_obj.unknown_float_2 = 1.0
        return n_col_obj

    def export_bhk_blend_controller(self, b_obj, parent_block):
        # also add a controller for it
        n_blend_ctrl = block_store.create_block("bhkBlendController", b_obj)
        n_blend_ctrl.flags = 12
        n_blend_ctrl.frequency = 1.0
        n_blend_ctrl.phase = 0.0
        n_blend_ctrl.start_time = consts.FLOAT_MAX
        n_blend_ctrl.stop_time = consts.FLOAT_MIN
        parent_block.add_controller(n_blend_ctrl)

""" # Oblivion skeleton export: check that all bones have a transform controller and transform interpolator
if bpy.context.scene.niftools_scene.game == 'OBLIVION' and file_base.lower() in ('skeleton', 'skeletonbeast'):
self.transform_anim_helper.add_dummy_controllers()"""