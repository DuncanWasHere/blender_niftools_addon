"""Nif User Interface, connect custom particle system properties from properties.particle_system"""

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
from bpy.types import Panel

from ..properties.particle_system import OBJECT_EMITTERS, VOLUME_EMITTERS
from ..utils.decorators import register_classes, unregister_classes


class ParticleSystemPanel(Panel):
    bl_idname = "NIFTOOLS_PT_ParticleSystemPanel"
    bl_label = "NifTools Particle System"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "particle"

    @classmethod
    def poll(cls, context):
        return context.particle_settings is not None

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        is_bethesda = context.scene.niftools_scene.is_fo3() or context.scene.niftools_scene.is_skyrim()

        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "particle_system_type")
        layout.prop(nif_ps, "world_space")
        layout.prop(nif_ps, "max_particles")
        if nif_ps.particle_system_type == "BSStripParticleSystem":
            layout.prop(nif_ps, "bs_strip_max_point_count")
            layout.prop(nif_ps, "bs_strip_start_cap_size")
            layout.prop(nif_ps, "bs_strip_end_cap_size")
            layout.prop(nif_ps, "bs_strip_do_z_prepass")


class ParticleSubPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "particle"
    bl_parent_id = ParticleSystemPanel.bl_idname

    @classmethod
    def poll(cls, context):
        return context.particle_settings is not None


class ParticleEmitterPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleEmitterPanel"
    bl_label = "Emission"

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "birth_rate")
        layout.prop(nif_ps, "emission_start_time")
        layout.prop(nif_ps, "emission_stop_time")
        layout.separator()
        layout.prop(nif_ps, "particle_emitter_type")
        for prop_name in VOLUME_EMITTERS.get(nif_ps.particle_emitter_type, ()):
            layout.prop(nif_ps, prop_name)
        if nif_ps.particle_emitter_type in OBJECT_EMITTERS:
            layout.prop(nif_ps, "particle_emitter_object")
        if nif_ps.particle_emitter_type == "NiPSysMeshEmitter":
            layout.prop(nif_ps, "emitter_emission_type")
            layout.prop(nif_ps, "emitter_velocity_type")
        layout.prop(nif_ps, "declination_variation")
        layout.prop(nif_ps, "planar_angle_variation")
        layout.prop(nif_ps, "initial_radius")
        layout.prop(nif_ps, "radius_variation")
        layout.prop(nif_ps, "initial_color")


class ParticleSpawnPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleSpawnPanel"
    bl_label = "Spawning"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "spawn_on_death")
        layout.prop(nif_ps, "num_spawn_generations")
        layout.prop(nif_ps, "percentage_spawned")
        layout.prop(nif_ps, "min_num_to_spawn")
        layout.prop(nif_ps, "max_num_to_spawn")
        layout.prop(nif_ps, "spawn_speed_variation")
        layout.prop(nif_ps, "spawn_dir_variation")


class ParticleRotationPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleRotationPanel"
    bl_label = "Rotation"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "use_rotation_modifier")
        column = layout.column()
        column.enabled = nif_ps.use_rotation_modifier
        column.prop(nif_ps, "rotation_speed")
        column.prop(nif_ps, "rotation_speed_variation")
        column.prop(nif_ps, "rotation_angle")
        column.prop(nif_ps, "rotation_angle_variation")
        column.prop(nif_ps, "random_rot_speed_sign")
        column.prop(nif_ps, "random_rot_axis")
        if not nif_ps.random_rot_axis:
            column.prop(nif_ps, "rotation_axis")


class ParticleGrowFadePanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleGrowFadePanel"
    bl_label = "Size Over Lifetime"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "use_grow_fade")
        column = layout.column()
        column.enabled = nif_ps.use_grow_fade
        column.prop(nif_ps, "grow_time")
        column.prop(nif_ps, "fade_time")
        column.prop(nif_ps, "grow_fade_base_scale")
        column.prop(nif_ps, "grow_generation")
        column.prop(nif_ps, "fade_generation")


class ParticleColorPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleColorPanel"
    bl_label = "Color Over Lifetime"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        is_bethesda = context.scene.niftools_scene.is_fo3() or context.scene.niftools_scene.is_skyrim()
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "use_simple_color")
        column = layout.column()
        column.enabled = nif_ps.use_simple_color
        if not is_bethesda:
            column.label(text="Fallout 3, New Vegas and Skyrim only.", icon='ERROR')
        column.prop(nif_ps, "simple_color_1")
        column.prop(nif_ps, "simple_color_2")
        column.prop(nif_ps, "simple_color_3")
        column.prop(nif_ps, "simple_color_fade_in")
        column.prop(nif_ps, "simple_color_fade_out")
        column.prop(nif_ps, "simple_color_1_start")
        column.prop(nif_ps, "simple_color_1_end")
        column.prop(nif_ps, "simple_color_2_start")
        column.prop(nif_ps, "simple_color_2_end")


class ParticleSubtexturePanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleSubtexturePanel"
    bl_label = "Subtextures"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "subtexture_columns")
        layout.prop(nif_ps, "subtexture_rows")
        layout.prop(nif_ps, "use_subtexture_animation")
        column = layout.column()
        column.enabled = nif_ps.use_subtexture_animation
        column.prop(nif_ps, "subtexture_start_frame")
        column.prop(nif_ps, "subtexture_frame_count")


class ParticleBethesdaPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleBethesdaPanel"
    bl_label = "Bethesda"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (super().poll(context)
                and (context.scene.niftools_scene.is_fo3()
                     or context.scene.niftools_scene.is_skyrim()))

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "use_bs_wind")
        column = layout.column()
        column.enabled = nif_ps.use_bs_wind
        column.prop(nif_ps, "bs_wind_strength")
        layout.separator()
        layout.prop(nif_ps, "use_bs_lod")
        column = layout.column()
        column.enabled = nif_ps.use_bs_lod
        column.prop(nif_ps, "bs_lod_begin_distance")
        column.prop(nif_ps, "bs_lod_end_distance")
        column.prop(nif_ps, "bs_lod_end_emit_scale")
        column.prop(nif_ps, "bs_lod_end_size")


class ParticleAdvancedPanel(ParticleSubPanel):
    bl_idname = "NIFTOOLS_PT_ParticleAdvancedPanel"
    bl_label = "NIF Data"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        nif_ps = context.particle_settings.nif_particle_system
        layout = self.layout
        layout.use_property_split = True
        layout.prop(nif_ps, "emitter_controller_flags")
        layout.prop(nif_ps, "emitter_controller_frequency")
        layout.prop(nif_ps, "emitter_controller_phase")
        layout.prop(nif_ps, "emitter_visibility_value")
        layout.separator()
        layout.prop(nif_ps, "update_controller_flags")
        layout.prop(nif_ps, "update_controller_frequency")
        layout.prop(nif_ps, "update_controller_phase")
        layout.prop(nif_ps, "update_start_time")
        layout.prop(nif_ps, "update_stop_time")
        layout.separator()
        grid = layout.grid_flow(columns=2, even_columns=True)
        for prop_name in (
                "data_has_vertices", "data_has_normals", "data_has_vertex_colors",
                "data_has_radii", "data_has_sizes", "data_has_rotations",
                "data_has_rotation_angles", "data_has_rotation_axes",
                "data_has_rotation_speeds", "data_has_texture_indices"):
            grid.prop(nif_ps, prop_name)
        if nif_ps.nif_blocks:
            layout.label(text=f"{len(nif_ps.nif_blocks)} typed imported NIF blocks")
        if nif_ps.controller_channels:
            layout.label(text=f"{len(nif_ps.controller_channels)} animated particle channels")


class MasterParticleSystemPanel(Panel):
    bl_idname = "NIFTOOLS_PT_MasterParticleSystemPanel"
    bl_label = "NifTools Master Particle System"

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return (context.object is not None
                and hasattr(context.object, "nif_object")
                and context.object.nif_object.nodetype == 'BSMasterParticleSystem')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(context.object.nif_master_particle_system, "max_emitter_objects")


classes = [
    ParticleSystemPanel,
    ParticleEmitterPanel,
    ParticleSpawnPanel,
    ParticleRotationPanel,
    ParticleGrowFadePanel,
    ParticleColorPanel,
    ParticleSubtexturePanel,
    ParticleBethesdaPanel,
    ParticleAdvancedPanel,
    MasterParticleSystemPanel,
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
