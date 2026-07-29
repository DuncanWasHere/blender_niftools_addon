"""Classes for exporting NIF particle emitter blocks."""

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
import mathutils

from ....utils import particles
from ....utils.logging import NifLog
from ....utils.math import color_blender_to_nif
from nifgen.formats.nif import classes as NifClasses


class Emitter:
    """
    Main interface class for exporting NIF particle emitter blocks
    (i.e., NiPSysEmitter and subclasses).

    Everything the Blender particle settings can describe (speed, direction, life span,
    particle size and color) is written by apply, so that an emitter restored from the
    particle data stored on import ends up with the same values as a new one.
    """

    def __init__(self):
        self.fps = bpy.context.scene.render.fps

    def apply(self, n_emitter, b_obj, b_psys, nif_ps):
        """Write the Blender values of a particle system onto its emitter block."""
        b_settings = b_psys.settings

        # velocity: Blender holds a direction vector, the nif the angles of that direction
        velocity = mathutils.Vector(b_settings.object_align_factor)
        if (particles.preview_unchanged(b_settings, "niftools_preview_align_factor", tuple(velocity))
                and particles.preview_unchanged(b_settings, "niftools_preview_normal_factor",
                                                b_settings.normal_factor)):
            # a mesh emitter that emits along its surface normals has no direction
            # vector at all, so its angles only exist in the typed nif properties
            n_emitter.speed = particles.blender_to_nif_units(nif_ps.emitter_speed)
            n_emitter.declination = nif_ps.declination
            n_emitter.planar_angle = nif_ps.planar_angle
        else:
            declination, planar_angle = particles.direction_to_angles(velocity, nif_ps.planar_angle)
            n_emitter.speed = particles.blender_to_nif_units(
                velocity.length or b_settings.normal_factor)
            n_emitter.declination = declination
            n_emitter.planar_angle = planar_angle
        preview_random = b_settings.get("niftools_preview_factor_random")
        if (preview_random is not None
                and abs(b_settings.factor_random - preview_random) < 1e-5):
            speed_variation = b_settings.get(
                "niftools_emitter_speed_variation", b_settings.factor_random)
        else:
            speed_variation = b_settings.factor_random
        n_emitter.speed_variation = particles.blender_to_nif_units(speed_variation)
        n_emitter.declination_variation = nif_ps.declination_variation
        n_emitter.planar_angle_variation = nif_ps.planar_angle_variation

        # life span, in frames in Blender and in seconds in the nif
        n_emitter.life_span, n_emitter.life_span_variation = particles.export_life_span(
            b_settings, nif_ps, self.fps)

        # particle size
        if b_settings.get("niftools_grow_fade_preview") and nif_ps.initial_radius > 0:
            n_emitter.initial_radius = particles.blender_to_nif_units(nif_ps.initial_radius)
        else:
            n_emitter.initial_radius = particles.blender_to_nif_units(
                particles.base_from_random_factor(b_settings.particle_size, b_settings.size_random))
        if hasattr(n_emitter, "radius_variation"):
            if b_settings.get("niftools_grow_fade_preview"):
                n_emitter.radius_variation = particles.blender_to_nif_units(nif_ps.radius_variation)
            else:
                n_emitter.radius_variation = particles.blender_to_nif_units(
                    particles.variation_from_random_factor(
                        b_settings.particle_size, b_settings.size_random))

        self.apply_initial_color(n_emitter, b_obj, b_settings, nif_ps)
        self.apply_volume(n_emitter, nif_ps)

        if isinstance(n_emitter, NifClasses.NiPSysMeshEmitter):
            n_emitter.emission_type = NifClasses.EmitFrom[nif_ps.emitter_emission_type]
            n_emitter.initial_velocity_type = NifClasses.VelocityType[nif_ps.emitter_velocity_type]

    @staticmethod
    def apply_volume(n_emitter, nif_ps):
        """Write the emitter volume of a particle system onto its emitter block."""
        if isinstance(n_emitter, NifClasses.NiPSysSphereEmitter):
            n_emitter.radius = particles.blender_to_nif_units(nif_ps.emitter_radius)
        elif isinstance(n_emitter, NifClasses.NiPSysCylinderEmitter):
            n_emitter.radius = particles.blender_to_nif_units(nif_ps.emitter_radius)
            n_emitter.height = particles.blender_to_nif_units(nif_ps.emitter_height)
        elif isinstance(n_emitter, NifClasses.NiPSysBoxEmitter):
            n_emitter.width = particles.blender_to_nif_units(nif_ps.emitter_width)
            n_emitter.height = particles.blender_to_nif_units(nif_ps.emitter_height)
            n_emitter.depth = particles.blender_to_nif_units(nif_ps.emitter_depth)

    @staticmethod
    def apply_initial_color(n_emitter, b_obj, b_settings, nif_ps):
        """Write the color particles are born with onto the emitter block.

        This is a property of the emitter rather than of the material, so an imported
        system exports the value it came in with. Only a system authored in Blender,
        which has no such value, falls back to reading the particle material.
        """

        if particles.preview_unchanged(b_settings, "niftools_preview_initial_color",
                                       tuple(nif_ps.initial_color)):
            b_color = nif_ps.initial_color
            n_emitter.initial_color.r = b_color[0]
            n_emitter.initial_color.g = b_color[1]
            n_emitter.initial_color.b = b_color[2]
            n_emitter.initial_color.a = b_color[3]
            return

        b_material = b_obj.active_material
        if not b_material or not b_material.use_nodes:
            return

        b_principled = next((b_node for b_node in b_material.node_tree.nodes
                             if isinstance(b_node, bpy.types.ShaderNodeBsdfPrincipled)), None)
        if not b_principled:
            # A material built from the nif shader node groups has no Principled BSDF,
            # and does not need one: the birth color is taken from the particle
            # settings above unless the user has changed it there.
            NifLog.debug(f"Material {b_material.name} of particle system {b_obj.name} has no Principled "
                         f"BSDF, so the initial particle color comes from the particle settings.")
            b_color = nif_ps.initial_color
            n_emitter.initial_color.r = b_color[0]
            n_emitter.initial_color.g = b_color[1]
            n_emitter.initial_color.b = b_color[2]
            n_emitter.initial_color.a = b_color[3]
            return

        b_color = mathutils.Color(b_principled.inputs["Base Color"].default_value[0:3])
        b_alpha = b_principled.inputs["Alpha"].default_value
        b_color = b_color.from_scene_linear_to_srgb()
        color_blender_to_nif(n_emitter.initial_color, (b_color[0], b_color[1], b_color[2], b_alpha))

    @staticmethod
    def get_emitter_object(b_obj, nif_ps):
        """The Blender object a particle system emits from, falling back to its parent."""
        if nif_ps.particle_emitter_object:
            return nif_ps.particle_emitter_object
        return b_obj.parent
