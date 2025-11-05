"""Nif User Interface, connect custom collision properties from properties.py into Blenders UI"""

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


from bpy.types import Panel
from io_scene_niftools.operators.shrink_hull import OperatorShrinkHull

from io_scene_niftools.utils.decorators import register_classes, unregister_classes


class CollisionPanel(Panel):
    bl_idname = "NIFTOOLS_PT_CollisionPanel"
    bl_label = "NifTools Collision"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "physics"

    @classmethod
    def poll(cls, context):
        if context.active_object.rigid_body:
            return True
        return False

    def draw(self, context):
        layout = self.layout

        collision_setting = context.active_object.nif_collision

        box = layout.box()
        box.prop(collision_setting, "collision_layer", text='Collision Layer')
        box.prop(collision_setting, "col_filter", text='Col Filter')
        box.prop(collision_setting, "inertia_tensor", text='Inertia Tensor')
        box.prop(collision_setting, "center", text='Center')
        box.prop(collision_setting, "mass", text='Mass')
        box.prop(collision_setting, "max_linear_velocity", text='Max Linear Velocity')
        box.prop(collision_setting, "max_angular_velocity", text='Max Angular Velocity')
        box.prop(collision_setting, "penetration_depth", text='Penetration Depth')
        box.prop(collision_setting, "motion_system", text='Motion System')
        box.prop(collision_setting, "deactivator_type", text='Deactivator Type')
        box.prop(collision_setting, "solver_deactivation", text='Solver Deactivator')
        box.prop(collision_setting, "quality_type", text='Quality Type')
        box.prop(collision_setting, "body_flags", text='React to Wind')
        box.prop(collision_setting, "force_bhk_rigid_body_t", text='Force BhkRigidBodyT')
        box.prop(collision_setting, "use_blender_properties", text='Recalculate Inertia Tensor')
        box.prop(collision_setting, "solid", text='Solid')
        box.prop(collision_setting, "shrink_offset", text='Shrink Offset')
        box.operator("niftools.shrink_hull", text='Shrink Hull')


classes = [
    CollisionPanel,
    OperatorShrinkHull
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
