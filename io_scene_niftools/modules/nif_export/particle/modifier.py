"""Classes for exporting NIF particle modifier blocks."""

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

import math

import bpy

from ....modules.nif_export.block_registry import block_store
from ....utils import particles
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses

ORDER = NifClasses.NiPSysModifierOrder


def add_modifier(n_ni_particle_system, n_modifier):
    """Append a modifier to a particle system's modifier list."""
    n_ni_particle_system.modifiers.append(n_modifier)
    n_ni_particle_system.num_modifiers = len(n_ni_particle_system.modifiers)


def sort_modifiers(n_ni_particle_system):
    """Sort a particle system's modifiers by the order they must be evaluated in."""
    n_ni_particle_system.modifiers.sort(key=lambda n_modifier: int(n_modifier.order))


class Modifier:
    """
    Main interface class for exporting NIF particle modifier blocks
    (i.e., NiPSysModifier and subclasses).

    Every modifier that Blender can describe has an apply method, which writes the
    Blender values onto an existing block. The same methods are used whether the block
    was newly created or restored from the particle data stored on import, so both paths
    end up with the same values.
    """

    def __init__(self):
        self.nif_scene = bpy.context.scene.niftools_scene
        self.fps = bpy.context.scene.render.fps

    def create(self, b_obj, block_type, order=None):
        """Create a particle modifier block of the given type.
        The block is not registered against the Blender object, which the particle
        system block itself is registered against."""
        n_modifier = block_store.create_block(block_type)
        n_modifier.name = f"{b_obj.name}-{block_type}"
        n_modifier.active = True
        n_modifier.order = self.get_order(block_type) if order is None else order
        return n_modifier

    def get_order(self, block_type):
        """The evaluation order a modifier block type is expected to have."""
        if block_type == "BSPSysStripUpdateModifier":
            # Skyrim evaluates strip updates last, Fallout 3 and New Vegas right after spawning
            return ORDER.ORDER_FO3_BSSTRIPUPDATE if self.nif_scene.is_fo3() else ORDER.ORDER_SK_BSSTRIPUPDATE
        return {
            "NiPSysAgeDeathModifier": ORDER.ORDER_KILLOLDPARTICLES,
            "BSPSysLODModifier": ORDER.ORDER_BSLOD,
            "NiPSysSpawnModifier": ORDER.ORDER_SPAWN,
            "NiPSysPositionModifier": ORDER.ORDER_POS_UPDATE,
            "BSPSysRecycleBoundModifier": ORDER.ORDER_POSTPOS_UPDATE,
            "NiPSysBoundUpdateModifier": ORDER.ORDER_BOUND_UPDATE,
            "NiPSysAirFieldModifier": ORDER.ORDER_FORCE,
            "NiPSysDragFieldModifier": ORDER.ORDER_FORCE,
            "NiPSysGravityFieldModifier": ORDER.ORDER_FORCE,
            "NiPSysRadialFieldModifier": ORDER.ORDER_FORCE,
            "NiPSysTurbulenceFieldModifier": ORDER.ORDER_FORCE,
            "NiPSysVortexFieldModifier": ORDER.ORDER_FORCE,
            "BSWindModifier": ORDER.ORDER_FORCE,
            "NiPSysBombModifier": ORDER.ORDER_FORCE,
            "NiPSysDragModifier": ORDER.ORDER_FORCE,
            "NiPSysGravityModifier": ORDER.ORDER_FORCE,
        }.get(block_type, ORDER.ORDER_GENERAL)

    def apply(self, n_modifier, b_obj, b_psys, nif_ps):
        """Write the Blender values of a particle system onto one of its modifier blocks."""
        b_settings = b_psys.settings

        if isinstance(n_modifier, NifClasses.NiPSysAgeDeathModifier):
            n_modifier.spawn_on_death = nif_ps.spawn_on_death

        elif isinstance(n_modifier, NifClasses.NiPSysSpawnModifier):
            n_modifier.num_spawn_generations = nif_ps.num_spawn_generations
            n_modifier.percentage_spawned = nif_ps.percentage_spawned
            n_modifier.min_num_to_spawn = nif_ps.min_num_to_spawn
            n_modifier.max_num_to_spawn = nif_ps.max_num_to_spawn
            n_modifier.spawn_speed_variation = nif_ps.spawn_speed_variation
            n_modifier.spawn_dir_variation = nif_ps.spawn_dir_variation
            # A spawn modifier gives its children a life span of their own, which the
            # Blender particle settings cannot hold. A restored one therefore keeps
            # the value it was imported with unless the emitter lifetime was edited.
            if particles.lifetime_edited(b_settings) or not n_modifier.life_span:
                n_modifier.life_span, n_modifier.life_span_variation = particles.export_life_span(
                    b_settings, nif_ps, self.fps)

        elif isinstance(n_modifier, NifClasses.NiPSysRotationModifier):
            self.apply_rotation(n_modifier, b_settings, nif_ps)

        elif isinstance(n_modifier, NifClasses.NiPSysGrowFadeModifier):
            n_modifier.grow_time = nif_ps.grow_time
            n_modifier.fade_time = nif_ps.fade_time
            if hasattr(n_modifier, "grow_generation"):
                n_modifier.grow_generation = nif_ps.grow_generation
            if hasattr(n_modifier, "fade_generation"):
                n_modifier.fade_generation = nif_ps.fade_generation
            if hasattr(n_modifier, "base_scale"):
                n_modifier.base_scale = nif_ps.grow_fade_base_scale

        elif isinstance(n_modifier, NifClasses.BSPSysSimpleColorModifier):
            self.apply_simple_color(n_modifier, nif_ps)

        elif isinstance(n_modifier, NifClasses.BSPSysSubTexModifier):
            n_modifier.start_frame = nif_ps.subtexture_start_frame
            n_modifier.frame_count = nif_ps.subtexture_frame_count

        elif isinstance(n_modifier, NifClasses.BSPSysLODModifier):
            n_modifier.lod_begin_distance = nif_ps.bs_lod_begin_distance
            n_modifier.lod_end_distance = nif_ps.bs_lod_end_distance
            n_modifier.end_emit_scale = nif_ps.bs_lod_end_emit_scale
            n_modifier.end_size = nif_ps.bs_lod_end_size

        elif isinstance(n_modifier, NifClasses.BSParentVelocityModifier):
            n_modifier.damping = b_settings.object_factor

        elif isinstance(n_modifier, NifClasses.BSWindModifier):
            n_modifier.strength = nif_ps.bs_wind_strength

        elif isinstance(n_modifier, NifClasses.BSPSysStripUpdateModifier):
            if not n_modifier.update_delta_time:
                # a restored modifier keeps the update rate the nif was authored at,
                # which is not necessarily the frame rate of this Blender scene
                n_modifier.update_delta_time = 1 / self.fps

    @staticmethod
    def apply_rotation(n_modifier, b_settings, nif_ps):
        """Write the Blender rotation settings onto a NiPSysRotationModifier."""
        if b_settings.get("niftools_billboard_preview"):
            n_modifier.rotation_speed = nif_ps.rotation_speed
            n_modifier.rotation_angle = nif_ps.rotation_angle
            n_modifier.rotation_angle_variation = nif_ps.rotation_angle_variation
            n_modifier.axis.x, n_modifier.axis.y, n_modifier.axis.z = nif_ps.rotation_axis
        else:
            n_modifier.rotation_speed = b_settings.angular_velocity_factor
            n_modifier.rotation_angle = b_settings.phase_factor * math.pi
            n_modifier.rotation_angle_variation = b_settings.phase_factor_random * math.pi
            axis = {'OB_Y': (0.0, 1.0, 0.0), 'OB_Z': (0.0, 0.0, 1.0)}.get(
                b_settings.rotation_mode, (1.0, 0.0, 0.0))
            n_modifier.axis.x, n_modifier.axis.y, n_modifier.axis.z = axis
        n_modifier.rotation_speed_variation = nif_ps.rotation_speed_variation
        n_modifier.random_rot_speed_sign = nif_ps.random_rot_speed_sign
        n_modifier.random_axis = nif_ps.random_rot_axis

    @staticmethod
    def apply_simple_color(n_modifier, nif_ps):
        """Write the nif color over lifetime properties onto a BSPSysSimpleColorModifier."""
        n_modifier.fade_in_percent = nif_ps.simple_color_fade_in
        n_modifier.fade_out_percent = nif_ps.simple_color_fade_out
        n_modifier.color_1_start_percent = nif_ps.simple_color_1_start
        n_modifier.color_1_end_percent = nif_ps.simple_color_1_end
        n_modifier.color_2_start_percent = nif_ps.simple_color_2_start
        n_modifier.color_2_end_percent = nif_ps.simple_color_2_end
        for index, prop_name in enumerate(("simple_color_1", "simple_color_2", "simple_color_3")):
            b_color = getattr(nif_ps, prop_name)
            n_color = n_modifier.colors[index]
            n_color.r, n_color.g, n_color.b, n_color.a = b_color[0], b_color[1], b_color[2], b_color[3]

    def get_required_modifiers(self, b_psys, nif_ps, n_particle_system):
        """The modifier block types a particle system built from Blender values needs,
        in the order they are created. The emitter is added separately."""
        b_settings = b_psys.settings

        block_types = ["NiPSysAgeDeathModifier", "NiPSysSpawnModifier",
                       "NiPSysPositionModifier", "NiPSysBoundUpdateModifier"]

        if isinstance(n_particle_system, NifClasses.BSStripParticleSystem):
            block_types.append("BSPSysStripUpdateModifier")
        if b_settings.use_rotations or nif_ps.use_rotation_modifier:
            block_types.append("NiPSysRotationModifier")
        if nif_ps.use_grow_fade:
            block_types.append("NiPSysGrowFadeModifier")
        if nif_ps.use_simple_color:
            block_types.append("BSPSysSimpleColorModifier")
        if nif_ps.use_subtexture_animation:
            block_types.append("BSPSysSubTexModifier")
        if nif_ps.use_bs_lod:
            block_types.append("BSPSysLODModifier")
        if b_settings.object_factor != 0:
            block_types.append("BSParentVelocityModifier")
        if nif_ps.use_bs_wind:
            block_types.append("BSWindModifier")

        return block_types

    # Force fields, exported from the force field objects in the Blender scene

    def export_field_modifier(self, b_field_obj, b_psys, n_particle_system):
        """Export a Blender force field object as the matching particle field modifier."""
        b_field = b_field_obj.field
        block_type = {
            'FORCE': "NiPSysGravityFieldModifier",
            'WIND': "NiPSysAirFieldModifier",
            'VORTEX': "NiPSysVortexFieldModifier",
            'DRAG': "NiPSysDragFieldModifier",
            'TURBULENCE': "NiPSysTurbulenceFieldModifier",
        }.get(b_field.type)

        if not block_type:
            NifLog.warn(f"Force field {b_field_obj.name} is of type {b_field.type}, which has no nif "
                        f"equivalent. It will not affect {n_particle_system.name}.")
            return None

        n_modifier = self.create(b_field_obj, block_type)
        n_modifier.name = f"{b_field_obj.name}-{block_type}"
        n_modifier.magnitude = particles.blender_to_nif_units(b_field.strength)
        n_modifier.attenuation = b_field.falloff_power
        n_modifier.use_max_distance = b_field.use_max_distance
        n_modifier.max_distance = particles.blender_to_nif_units(b_field.distance_max)

        if isinstance(n_modifier, NifClasses.NiPSysGravityFieldModifier):
            # Blender force fields pull towards the object, the nif field pushes along an axis
            n_modifier.direction.x, n_modifier.direction.y, n_modifier.direction.z = (0.0, 0.0, -1.0)
        elif isinstance(n_modifier, NifClasses.NiPSysVortexFieldModifier):
            n_modifier.direction.x, n_modifier.direction.y, n_modifier.direction.z = (0.0, 0.0, 1.0)
        elif isinstance(n_modifier, NifClasses.NiPSysDragFieldModifier):
            n_modifier.use_direction = False
        elif isinstance(n_modifier, NifClasses.NiPSysTurbulenceFieldModifier):
            n_modifier.frequency = b_field.noise
        elif isinstance(n_modifier, NifClasses.NiPSysAirFieldModifier):
            self.apply_air_field(n_modifier, b_field)

        return n_modifier

    @staticmethod
    def apply_air_field(n_modifier, b_field):
        """Write a Blender wind force field onto a NiPSysAirFieldModifier."""
        n_modifier.direction.x, n_modifier.direction.y, n_modifier.direction.z = (0.0, 0.0, 1.0)
        n_modifier.inherit_velocity = max(0.0, min(1.0, b_field.flow))
        n_modifier.inherit_rotation = b_field.apply_to_rotation
        if b_field.use_radial_max:
            n_modifier.enable_spread = True
            n_modifier.spread = b_field.radial_max

    def export_color_modifier(self, b_obj, rgba_keys, n_particle_system):
        """Export animated particle color as a NiPSysColorModifier with a NiColorData block."""
        color_keys, alpha_keys = rgba_keys

        n_modifier = self.create(b_obj, "NiPSysColorModifier")
        n_modifier.target = n_particle_system

        n_color_data = block_store.create_block("NiColorData")
        n_modifier.data = n_color_data

        n_color_data.data.num_keys = len(color_keys)
        n_color_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
        n_color_data.data.reset_field("keys")

        for n_key, (frame, color), (_, alpha) in zip(n_color_data.data.keys, color_keys, alpha_keys):
            n_key.time = frame / self.fps
            n_key.value.r = color.r
            n_key.value.g = color.g
            n_key.value.b = color.b
            n_key.value.a = alpha

        add_modifier(n_particle_system, n_modifier)
        sort_modifiers(n_particle_system)

        return n_modifier
