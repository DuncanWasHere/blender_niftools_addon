"""Classes for importing NIF particle blocks."""

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

import bmesh
import bpy
import mathutils

from ....modules.nif_import.object import Object
from ....modules.nif_import.object.block_registry import block_store
from ....modules.nif_import.property.material import MaterialProperty
from ....utils import math as nif_math
from ....utils import particles
from . import block_properties
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses

# Emitter object pointers, resolved once the whole nif tree has been imported.
# Holds (blender particle settings, referenced nif block) pairs.
PENDING_EMITTER_OBJECTS = []

# Mesh-particle render objects, resolved after the whole scene tree has been imported.
# Holds (Blender particle settings, referenced nif particle-mesh node) pairs.
PENDING_PARTICLE_MESHES = []

# Typed NIF block references, resolved once the complete scene exists.
# Holds (ParticleNifReferenceProperty, referenced nif block) pairs.
PENDING_NIF_REFERENCES = []

# Gravity modifiers are resolved after their linked gravity objects have been
# imported, because the modifier axis lives in that object's rotated space.
PENDING_GRAVITY_PREVIEWS = []

# Blender objects created for imported particle system blocks, keyed by nif block
DICT_PARTICLE_SYSTEMS = {}

# Controller-sequence entries keyed by their target particle-system name. The
# controller attached to the system usually contains only a blend interpolator.
# Its actual BirthRate and EmitterActive values live in these entries.
SEQUENCE_CONTROLLED_BLOCKS = {}

# Visible scene ranges contributed by particle controllers. Cyclic systems use
# pre-roll internally, but keep the user-facing range at the controller loop.
# One-shot systems extend the visible range until their final particles die.
PARTICLE_TIMELINE_RANGES = []

LAST_VIEW_ROTATION = None

# World rotation of the particle instances of each sprite preview object, keyed by
# object name. Only ever measured from the depsgraph outside a frame change handler.
INSTANCE_ROTATIONS = {}

# Cached (sprite previews, orientation helpers), rebuilt on the viewport timer
BILLBOARD_OBJECTS = None

# Set while the importer steps the timeline, so that priming a particle cache does
# not rebuild every sprite quad once per frame
SUSPEND_BILLBOARDS = False


def clear():
    """Reset the state kept between the blocks of a single import."""
    global LAST_VIEW_ROTATION, BILLBOARD_OBJECTS

    PENDING_EMITTER_OBJECTS.clear()
    PENDING_PARTICLE_MESHES.clear()
    PENDING_NIF_REFERENCES.clear()
    PENDING_GRAVITY_PREVIEWS.clear()
    DICT_PARTICLE_SYSTEMS.clear()
    SEQUENCE_CONTROLLED_BLOCKS.clear()
    PARTICLE_TIMELINE_RANGES.clear()
    INSTANCE_ROTATIONS.clear()
    LAST_VIEW_ROTATION = None
    BILLBOARD_OBJECTS = None


def collect_sequence_controllers(roots):
    """Index particle controller-sequence entries before scene import."""

    for root in roots:
        for sequence in root.tree(block_type=NifClasses.NiControllerSequence, unique=True):
            for controlled in sequence.controlled_blocks:
                controller_type = str(controlled.controller_type or "")
                if not controller_type and controlled.controller:
                    controller_type = type(controlled.controller).__name__
                if "PSys" not in controller_type:
                    continue
                target_name = str(controlled.target_name or "")
                if not target_name:
                    target_name = str(controlled.get_node_name() or "")
                if target_name:
                    SEQUENCE_CONTROLLED_BLOCKS.setdefault(target_name, []).append(
                        (sequence, controlled))


class Particle:
    """
    Main interface class for importing NIF particle blocks
    (i.e., NiParticleSystem and subclasses).

    A particle system becomes a Blender object carrying a particle system, whose emitter
    mesh is generated from the nif emitter volume so the system previews in the viewport.
    The values Blender can represent (count, lifetime, size, velocity, rotation) are
    mapped onto the Blender particle settings; values with no Blender equivalent are
    preserved as typed NIF block properties on the particle settings.
    """

    # Nif rotation axes mapped to the closest Blender particle rotation modes
    AXIS_ROTATION_MODES = (((1.0, 0.0, 0.0), 'OB_X'),
                           ((0.0, 1.0, 0.0), 'OB_Y'),
                           ((0.0, 0.0, 1.0), 'OB_Z'))

    def __init__(self):
        self.material_property_helper = MaterialProperty()
        self.object_helper = Object()
        self.fps = bpy.context.scene.render.fps

    @staticmethod
    def is_particle_system(n_block):
        """Whether a nif block should be imported as a particle system."""
        return isinstance(n_block, NifClasses.NiParticles)

    def import_particle_system(self, n_block):
        """Import a particle system block as a Blender object holding a particle system."""

        if not isinstance(n_block, NifClasses.NiParticleSystem):
            # the Morrowind era particle blocks are driven by a NiParticleSystemController
            # and a chain of NiParticleModifiers, which share almost nothing with the modern format
            NifLog.warn(f"Legacy particle block '{n_block.name}' ({type(n_block).__name__}) is not supported "
                        f"and will not be imported.")
            return None

        NifLog.info(f"Importing particle system '{n_block.name}'")

        n_modifiers = [n_modifier for n_modifier in n_block.modifiers if n_modifier]
        n_emitter = self.find_modifier(n_modifiers, NifClasses.NiPSysEmitter)

        b_obj = self.object_helper.create_mesh_object(n_block)
        b_obj.matrix_local = nif_math.import_matrix(n_block)
        # the emitter mesh is a helper standing in for the nif emitter volume, not geometry
        # Do not use the WIRE object display override here: Blender propagates
        # it to legacy object-instanced particles in Material Preview, leaving
        # only selection outlines. Hide just the emitter geometry with the
        # instancer visibility controls while keeping its particles textured.
        b_obj.display_type = 'TEXTURED'
        b_obj.show_instancer_for_viewport = False
        b_obj.show_instancer_for_render = False
        self.object_helper.import_object_flags(n_block, b_obj)

        b_psys = self.create_particle_system(b_obj, n_block)
        b_settings = b_psys.settings
        nif_ps = b_settings.nif_particle_system

        nif_ps.particle_system_type = self.get_system_type(n_block)
        nif_ps.world_space = bool(n_block.world_space)

        self.import_data(n_block.data, b_settings, nif_ps)
        self.import_emitter(n_emitter, b_settings, nif_ps)
        self.import_modifiers(n_modifiers, b_settings, nif_ps)
        self.import_controllers(n_block, n_emitter, b_settings, nif_ps)
        # Blender cannot simulate negative frames, so the cache simply covers the
        # emission window and the lifetime of the last particle born in it.
        b_psys.point_cache.frame_start = max(0, math.floor(b_settings.frame_start))
        b_psys.point_cache.frame_end = math.ceil(
            b_settings.frame_end + b_settings.lifetime)
        self.build_emitter_mesh(b_obj.data, b_settings, nif_ps)

        self.material_property_helper.import_material_properties(n_block, b_obj)
        self.configure_particle_render(n_block, b_obj, b_psys)

        PENDING_NIF_REFERENCES.extend(block_properties.store_particle_blocks(
            nif_ps, n_block, n_block.data, n_modifiers, list(self.iter_controllers(n_block))))

        DICT_PARTICLE_SYSTEMS[n_block] = b_obj
        return b_obj

    @staticmethod
    def get_system_type(n_block):
        """The particle system block type, as named by the particle settings enum."""
        block_type = type(n_block).__name__
        if block_type in particles.PARTICLE_SYSTEM_TYPES:
            return block_type
        # subclasses we do not model separately still export as the closest known type
        if isinstance(n_block, NifClasses.BSStripParticleSystem):
            return "BSStripParticleSystem"
        if isinstance(n_block, NifClasses.NiMeshParticleSystem):
            return "NiMeshParticleSystem"
        return "NiParticleSystem"

    @staticmethod
    def find_modifier(n_modifiers, modifier_type):
        """The first modifier of the given type in a particle system's modifier list."""
        for n_modifier in n_modifiers:
            if isinstance(n_modifier, modifier_type):
                return n_modifier
        return None

    @staticmethod
    def create_particle_system(b_obj, n_block):
        """Add a Blender particle system to the object and give it sensible nif defaults."""
        b_name = block_store.import_name(n_block)
        b_obj.modifiers.new(b_name, 'PARTICLE_SYSTEM')
        b_psys = b_obj.particle_systems[-1]
        b_psys.name = b_name

        b_settings = b_psys.settings
        b_settings.name = b_name
        b_settings.type = 'EMITTER'
        b_settings.physics_type = 'NEWTON'
        b_settings.distribution = 'RAND'
        b_settings.use_emit_random = True
        b_settings.display_method = 'RENDER'
        b_settings.display_percentage = 100
        b_settings.emit_from = 'VOLUME'
        b_settings.normal_factor = 0.0
        # nif particles are only affected by the force modifiers of their own system
        b_settings.effector_weights.gravity = 0.0
        if isinstance(n_block, NifClasses.BSStripParticleSystem):
            # strip particles trail behind their position, which is what a path render approximates
            b_settings.render_type = 'PATH'
        elif isinstance(n_block, NifClasses.NiMeshParticleSystem):
            b_settings.render_type = 'OBJECT'
        else:
            # A NIF sprite particle is a camera-facing textured quad. Blender no
            # longer has a billboard particle renderer, so a generated quad is
            # assigned after the NIF material has been imported.
            b_settings.render_type = 'OBJECT'
        return b_psys

    def import_data(self, n_data, b_settings, nif_ps):
        """Import the particle system data block."""
        if not n_data:
            NifLog.warn("Particle system has no data block, using defaults")
            return

        # the nif count is how many particles can be alive at once, while the Blender count is
        # how many are emitted in total, which comes from the birth rate of the emitter controller
        nif_ps.max_particles = self.get_max_particles(n_data)
        for field_name in (
                "has_vertices", "has_normals", "has_vertex_colors", "has_radii",
                "has_sizes", "has_rotations", "has_rotation_angles",
                "has_rotation_axes", "has_rotation_speeds", "has_texture_indices"):
            setattr(nif_ps, f"data_{field_name}", bool(getattr(n_data, field_name, False)))

        n_offsets = list(getattr(n_data, "subtexture_offsets", ()) or ())
        nif_ps.subtexture_columns, nif_ps.subtexture_rows = particles.subtexture_grid(n_offsets)

        if isinstance(n_data, NifClasses.BSStripPSysData):
            nif_ps.bs_strip_max_point_count = n_data.max_point_count
            nif_ps.bs_strip_start_cap_size = n_data.start_cap_size
            nif_ps.bs_strip_end_cap_size = n_data.end_cap_size
            nif_ps.bs_strip_do_z_prepass = bool(n_data.do_z_prepass)
        elif isinstance(n_data, NifClasses.NiMeshPSysData) and n_data.particle_meshes:
            PENDING_PARTICLE_MESHES.append((b_settings, n_data.particle_meshes))

    @staticmethod
    def get_max_particles(n_data):
        """The maximum particle count of a data block, whichever field the nif version stores it in."""
        for field_name in ("bs_max_vertices", "num_particles", "num_vertices"):
            value = getattr(n_data, field_name, None)
            if value:
                return value
        return 0

    def import_emitter(self, n_emitter, b_settings, nif_ps):
        """Import the emitter modifier onto the Blender particle settings."""
        if not n_emitter:
            NifLog.warn("Particle system has no emitter modifier, using defaults")
            return

        nif_ps.particle_emitter_type = self.get_emitter_type(n_emitter)

        # velocity: the nif stores the emission direction as angles around the emitter's Z axis
        speed = particles.nif_to_blender_units(n_emitter.speed)
        direction = particles.angles_to_direction(
            n_emitter.declination, n_emitter.planar_angle)
        nif_ps.emitter_speed = speed
        nif_ps.declination = n_emitter.declination
        nif_ps.planar_angle = n_emitter.planar_angle
        if self.emits_along_normals(n_emitter):
            # A mesh emitter using its surface normals has no fixed direction for
            # Blender's object-aligned velocity to hold, but Blender emits along
            # the emission element's normal with exactly the same meaning.
            b_settings.object_align_factor = (0.0, 0.0, 0.0)
            b_settings.normal_factor = speed
        else:
            b_settings.object_align_factor = direction * speed
            b_settings.normal_factor = 0.0
        speed_variation = particles.nif_to_blender_units(n_emitter.speed_variation)
        nif_ps.emitter_speed_variation = speed_variation
        # Blender exposes one random velocity vector rather than Gamebryo's
        # separate speed, declination and planar-angle ranges. Combine their
        # maximum directional deviations for a faithful visual spread while
        # keeping the original scalar speed variation for export.
        declination_spread = min(math.pi, abs(n_emitter.declination_variation))
        planar_spread = min(math.pi, abs(n_emitter.planar_angle_variation))
        declination_random = 2.0 * speed * math.sin(declination_spread * 0.5)
        planar_random = (
            2.0 * speed * abs(math.sin(n_emitter.declination))
            * math.sin(planar_spread * 0.5)
        )
        b_settings.factor_random = math.sqrt(
            speed_variation ** 2
            + declination_random ** 2
            + planar_random ** 2
        )
        b_settings["niftools_emitter_speed_variation"] = speed_variation
        b_settings["niftools_preview_factor_random"] = b_settings.factor_random
        b_settings["niftools_preview_normal_factor"] = b_settings.normal_factor
        b_settings["niftools_preview_align_factor"] = tuple(b_settings.object_align_factor)
        nif_ps.declination_variation = n_emitter.declination_variation
        nif_ps.planar_angle_variation = n_emitter.planar_angle_variation

        # The birth colour belongs to the emitter, not to the material Blender shows
        # on the emitter object, so it is kept here rather than guessed back out of a
        # shader on export.
        n_color = n_emitter.initial_color
        nif_ps.initial_color = (n_color.r, n_color.g, n_color.b, n_color.a)
        b_settings["niftools_preview_initial_color"] = tuple(nif_ps.initial_color)

        # Gamebryo varies lifetime on both sides of the base value. Blender's
        # lifetime_random only shortens a maximum lifetime, so use base+variation
        # as the Blender maximum and choose the random factor that reaches
        # base-variation at the other end.
        nif_ps.life_span = max(0.0, n_emitter.life_span)
        nif_ps.life_span_variation = max(0.0, n_emitter.life_span_variation)
        if n_emitter.life_span > 0:
            max_lifetime = n_emitter.life_span + max(0.0, n_emitter.life_span_variation)
            b_settings.lifetime = max(0.001, max_lifetime * self.fps)
        b_settings.lifetime_random = particles.lifetime_random_from_variation(n_emitter.life_span,
                                                                             n_emitter.life_span_variation)
        b_settings["niftools_preview_lifetime"] = b_settings.lifetime
        b_settings["niftools_preview_lifetime_random"] = b_settings.lifetime_random

        # particle size. As with the life span, the nif varies the radius on both
        # sides of its base value while Blender only shrinks a maximum.
        if n_emitter.initial_radius > 0:
            b_settings["niftools_grow_fade_preview"] = True
            nif_ps.initial_radius = particles.nif_to_blender_units(n_emitter.initial_radius)
            radius_variation = max(0.0, getattr(n_emitter, "radius_variation", 0.0))
            nif_ps.radius_variation = particles.nif_to_blender_units(radius_variation)
            b_settings.particle_size = nif_ps.initial_radius + nif_ps.radius_variation
            b_settings.size_random = particles.lifetime_random_from_variation(
                n_emitter.initial_radius, radius_variation)

        # emitter volume, kept in Blender units so the generated emitter mesh matches
        if isinstance(n_emitter, NifClasses.NiPSysSphereEmitter):
            nif_ps.emitter_radius = particles.nif_to_blender_units(n_emitter.radius)
        elif isinstance(n_emitter, NifClasses.NiPSysCylinderEmitter):
            nif_ps.emitter_radius = particles.nif_to_blender_units(n_emitter.radius)
            nif_ps.emitter_height = particles.nif_to_blender_units(n_emitter.height)
        elif isinstance(n_emitter, NifClasses.NiPSysBoxEmitter):
            nif_ps.emitter_width = particles.nif_to_blender_units(n_emitter.width)
            nif_ps.emitter_height = particles.nif_to_blender_units(n_emitter.height)
            nif_ps.emitter_depth = particles.nif_to_blender_units(n_emitter.depth)
        elif isinstance(n_emitter, NifClasses.NiPSysMeshEmitter):
            nif_ps.emitter_emission_type = n_emitter.emission_type.name
            nif_ps.emitter_velocity_type = n_emitter.initial_velocity_type.name
            b_settings.emit_from = 'FACE' if "FACE" in n_emitter.emission_type.name else 'VERT'

        # the object particles are emitted from can only be resolved once everything is imported
        n_emitter_object = getattr(n_emitter, "emitter_object", None)
        if n_emitter_object is not None:
            PENDING_EMITTER_OBJECTS.append((b_settings, nif_ps, n_emitter_object))
        n_emitter_meshes = [n_mesh for n_mesh in getattr(n_emitter, "emitter_meshes", ()) if n_mesh]
        if n_emitter_meshes:
            PENDING_EMITTER_OBJECTS.append((b_settings, nif_ps, n_emitter_meshes[0]))
            if len(n_emitter_meshes) > 1:
                NifLog.warn(f"Mesh emitter '{n_emitter.name}' emits from {len(n_emitter_meshes)} meshes, "
                            f"only the first one is used for Blender's viewport preview.")

    @staticmethod
    def emits_along_normals(n_emitter):
        """Whether an emitter sends its particles along the normals of its emitter mesh."""
        if not isinstance(n_emitter, NifClasses.NiPSysMeshEmitter):
            return False
        return n_emitter.initial_velocity_type == NifClasses.VelocityType.VELOCITY_USE_NORMALS

    @staticmethod
    def get_emitter_type(n_emitter):
        """The emitter block type, as named by the particle settings enum."""
        block_type = type(n_emitter).__name__
        if block_type in particles.PARTICLE_EMITTER_TYPES:
            return block_type
        if isinstance(n_emitter, NifClasses.BSPSysArrayEmitter):
            return "BSPSysArrayEmitter"
        if isinstance(n_emitter, NifClasses.NiPSysMeshEmitter):
            return "NiPSysMeshEmitter"
        if isinstance(n_emitter, NifClasses.NiPSysCylinderEmitter):
            return "NiPSysCylinderEmitter"
        if isinstance(n_emitter, NifClasses.NiPSysBoxEmitter):
            return "NiPSysBoxEmitter"
        return "NiPSysSphereEmitter"

    def import_modifiers(self, n_modifiers, b_settings, nif_ps):
        """Import the modifiers that map onto Blender particle settings or nif properties."""
        for n_modifier in n_modifiers:
            if isinstance(n_modifier, NifClasses.NiPSysAgeDeathModifier):
                nif_ps.spawn_on_death = bool(n_modifier.spawn_on_death)

            elif isinstance(n_modifier, NifClasses.NiPSysSpawnModifier):
                nif_ps.num_spawn_generations = n_modifier.num_spawn_generations
                nif_ps.percentage_spawned = max(0.0, min(1.0, n_modifier.percentage_spawned))
                nif_ps.min_num_to_spawn = n_modifier.min_num_to_spawn
                nif_ps.max_num_to_spawn = n_modifier.max_num_to_spawn
                # shipped nifs store negative spawn variations, so they are kept as is
                nif_ps.spawn_speed_variation = n_modifier.spawn_speed_variation
                nif_ps.spawn_dir_variation = n_modifier.spawn_dir_variation

            elif isinstance(n_modifier, NifClasses.NiPSysRotationModifier):
                self.import_rotation_modifier(n_modifier, b_settings, nif_ps)

            elif isinstance(n_modifier, NifClasses.NiPSysGrowFadeModifier):
                nif_ps.use_grow_fade = True
                nif_ps.grow_time = n_modifier.grow_time
                nif_ps.fade_time = n_modifier.fade_time
                nif_ps.grow_fade_base_scale = getattr(n_modifier, "base_scale", 1.0)
                nif_ps.grow_generation = getattr(n_modifier, "grow_generation", 0)
                nif_ps.fade_generation = getattr(n_modifier, "fade_generation", 0)

            elif isinstance(n_modifier, NifClasses.BSPSysSimpleColorModifier):
                self.import_simple_color_modifier(n_modifier, nif_ps)

            elif isinstance(n_modifier, NifClasses.BSPSysSubTexModifier):
                nif_ps.use_subtexture_animation = True
                nif_ps.subtexture_start_frame = n_modifier.start_frame
                nif_ps.subtexture_frame_count = n_modifier.frame_count

            elif isinstance(n_modifier, NifClasses.BSPSysLODModifier):
                nif_ps.use_bs_lod = True
                nif_ps.bs_lod_begin_distance = n_modifier.lod_begin_distance
                nif_ps.bs_lod_end_distance = n_modifier.lod_end_distance
                nif_ps.bs_lod_end_emit_scale = n_modifier.end_emit_scale
                nif_ps.bs_lod_end_size = n_modifier.end_size

            elif isinstance(n_modifier, NifClasses.BSParentVelocityModifier):
                b_settings.object_factor = n_modifier.damping

            elif isinstance(n_modifier, NifClasses.BSWindModifier):
                nif_ps.use_bs_wind = True
                nif_ps.bs_wind_strength = n_modifier.strength
                b_settings.effector_weights.wind = n_modifier.strength

            elif isinstance(n_modifier, (NifClasses.NiPSysGravityModifier,
                                         NifClasses.NiPSysGravityFieldModifier)):
                if isinstance(n_modifier, NifClasses.NiPSysGravityModifier):
                    PENDING_GRAVITY_PREVIEWS.append((b_settings, n_modifier))

    @staticmethod
    def import_gravity_preview(n_modifier, b_settings, b_gravity_object=None):
        """Map a linked planar gravity direction onto Blender's gravity weight.

        Blender has no per-system arbitrary gravity vector.  The common planar
        world-Z component is nevertheless an exact magnitude mapping. The NIF
        axis is rotated by its linked gravity node; ignoring that node turns
        downward splash gravity into upward lift.
        """

        if not isinstance(n_modifier, NifClasses.NiPSysGravityModifier):
            return
        force_type = int(getattr(n_modifier, "force_type", 0))
        axis = getattr(n_modifier, "gravity_axis", None)
        if force_type != 0 or axis is None:
            return
        direction = mathutils.Vector((axis.x, axis.y, axis.z))
        if b_gravity_object:
            direction = b_gravity_object.matrix_world.to_quaternion() @ direction
        if not direction.length:
            return
        direction.normalize()
        if abs(direction.z) < 1e-4:
            return
        scene_gravity = abs(bpy.context.scene.gravity.z)
        if scene_gravity <= 1e-6:
            return
        acceleration = particles.nif_to_blender_units(n_modifier.strength)
        # Blender's scene gravity points down (-Z), so upward NIF acceleration
        # requires a negative weight. Signed NIF strength is intentional.
        b_settings.effector_weights.gravity -= direction.z * acceleration / scene_gravity

    @staticmethod
    def import_rotation_modifier(n_modifier, b_settings, nif_ps):
        """Import a NiPSysRotationModifier as Blender particle rotation settings."""
        nif_ps.use_rotation_modifier = True
        nif_ps.rotation_speed = n_modifier.rotation_speed
        nif_ps.rotation_angle = n_modifier.rotation_angle
        nif_ps.rotation_angle_variation = n_modifier.rotation_angle_variation
        nif_ps.rotation_axis = (n_modifier.axis.x, n_modifier.axis.y, n_modifier.axis.z)
        b_settings.use_rotations = True
        b_settings.angular_velocity_factor = n_modifier.rotation_speed
        b_settings.phase_factor = max(-1.0, min(1.0, n_modifier.rotation_angle / math.pi))
        b_settings.phase_factor_random = max(0.0, min(2.0, n_modifier.rotation_angle_variation / math.pi))

        nif_ps.rotation_speed_variation = n_modifier.rotation_speed_variation
        nif_ps.random_rot_speed_sign = bool(n_modifier.random_rot_speed_sign)
        nif_ps.random_rot_axis = bool(n_modifier.random_axis)

        # the fixed rotation axis is stored as a Blender rotation mode, the closest equivalent
        axis = (n_modifier.axis.x, n_modifier.axis.y, n_modifier.axis.z)
        b_settings.rotation_mode = min(Particle.AXIS_ROTATION_MODES,
                                       key=lambda pair: sum((a - b) ** 2 for a, b in zip(pair[0], axis)))[1]
        b_settings.angular_velocity_mode = 'RAND' if n_modifier.random_axis else 'VELOCITY'

    @staticmethod
    def import_simple_color_modifier(n_modifier, nif_ps):
        """Import a BSPSysSimpleColorModifier as the nif color over lifetime properties."""
        nif_ps.use_simple_color = True
        nif_ps.simple_color_fade_in = max(0.0, min(1.0, n_modifier.fade_in_percent))
        nif_ps.simple_color_fade_out = max(0.0, min(1.0, n_modifier.fade_out_percent))
        nif_ps.simple_color_1_start = max(0.0, min(1.0, n_modifier.color_1_start_percent))
        nif_ps.simple_color_1_end = max(0.0, min(1.0, n_modifier.color_1_end_percent))
        nif_ps.simple_color_2_start = max(0.0, min(1.0, n_modifier.color_2_start_percent))
        nif_ps.simple_color_2_end = max(0.0, min(1.0, n_modifier.color_2_end_percent))
        for index, prop_name in enumerate(("simple_color_1", "simple_color_2", "simple_color_3")):
            n_color = n_modifier.colors[index]
            setattr(nif_ps, prop_name, (n_color.r, n_color.g, n_color.b, n_color.a))

    def import_controllers(self, n_block, n_emitter, b_settings, nif_ps):
        """Import controller timing and derive Blender's emission window and count."""

        emitter_controller = None
        n_modifier_active = []
        for n_controller in self.iter_controllers(n_block):
            if isinstance(n_controller, NifClasses.NiPSysEmitterCtlr) and emitter_controller is None:
                emitter_controller = n_controller
                nif_ps.emitter_controller_flags = int(n_controller.flags)
                nif_ps.emitter_controller_frequency = n_controller.frequency
                nif_ps.emitter_controller_phase = n_controller.phase
                nif_ps.emission_start_time = n_controller.start_time
                nif_ps.emission_stop_time = n_controller.stop_time
                n_visibility = getattr(n_controller, "visibility_interpolator", None)
                if isinstance(n_visibility, NifClasses.NiBoolInterpolator) and not n_visibility.data:
                    nif_ps.emitter_visibility_value = int(n_visibility.value)
            elif isinstance(n_controller, NifClasses.NiPSysUpdateCtlr):
                nif_ps.update_controller_flags = int(n_controller.flags)
                nif_ps.update_controller_frequency = n_controller.frequency
                nif_ps.update_controller_phase = n_controller.phase
                nif_ps.update_start_time = n_controller.start_time
                nif_ps.update_stop_time = n_controller.stop_time
            elif isinstance(n_controller, NifClasses.NiPSysModifierActiveCtlr):
                n_modifier_active.append(n_controller)

        if not emitter_controller:
            return

        self.apply_emission_profile(
            n_block, n_emitter, emitter_controller, n_modifier_active, b_settings, nif_ps)

    def apply_emission_profile(self, n_block, n_emitter, n_emitter_controller,
                               n_modifier_active, b_settings, nif_ps):
        """Reproduce the emission of a nif system with Blender's single emission window.

        A nif system emits with an animated birth rate that is gated on and off by
        boolean curves, all of which live in the controller sequence that plays the
        system rather than on the controller itself. Blender only has one window and
        one total count, so the nif curves are integrated over the window: the count
        then matches the number of particles the game actually births, which is what
        the raw birth rate on its own badly overstates.
        """

        window_start, window_stop, cyclic = self.get_emission_window(
            n_block, n_emitter_controller)
        rate_keys, rate_constant = self.get_birth_rate_curve(
            n_block, n_emitter_controller, nif_ps)
        intervals = self.get_active_intervals(
            n_block, n_emitter, n_emitter_controller, n_modifier_active,
            window_start, window_stop)

        if not intervals:
            NifLog.info(f"Particle system '{n_block.name}' never activates its emitter, "
                        f"so no particles are emitted in the preview.")
            nif_ps.birth_rate = 0.0
            b_settings.count = 1
            b_settings.frame_start = b_settings.frame_end = window_start * self.fps
        else:
            total = 0.0
            active = 0.0
            for interval_start, interval_stop in intervals:
                if rate_keys:
                    total += particles.integrate_linear(rate_keys, interval_start, interval_stop)
                elif rate_constant is not None:
                    total += rate_constant * (interval_stop - interval_start)
                active += interval_stop - interval_start
            # The rate the emitter starts at, which for a constant interpolator is
            # exactly the value the nif stores. Using the average over the window
            # instead would disagree with the value the controller channel of an
            # animated birth rate puts back on this property.
            if rate_keys:
                nif_ps.birth_rate = rate_keys[0][1]
            elif rate_constant is not None:
                nif_ps.birth_rate = max(0.0, rate_constant)

            if cyclic:
                # A looping emitter is switched on again on every cycle. Blender only
                # emits over one window, so spreading the cycle's particles over the
                # whole loop keeps the average rate instead of firing a single burst
                # and then leaving the system dead until the timeline restarts.
                emission_start, emission_stop = window_start, window_stop
            else:
                # A one-shot system is a burst whose timing matters, so it keeps the
                # window over which its emitter is actually switched on.
                emission_start, emission_stop = intervals[0][0], intervals[-1][1]
            total = self.cap_to_particle_pool(
                total, emission_stop - emission_start, nif_ps, n_emitter)

            b_settings.frame_start = emission_start * self.fps
            b_settings.frame_end = emission_stop * self.fps
            b_settings.count = max(1, min(100000, int(round(total))))

        # Particle lifetimes have nothing to do with the controller that births them,
        # so the visible range always runs one full life span past the emission it
        # covers. Blender restarts a particle simulation when the timeline wraps, and
        # ending the timeline at the controller loop instead would clear every
        # particle that is still alive there. Repeating the loop until the emitting
        # stretch is at least as long as that die-out tail keeps most of the timeline
        # emitting rather than draining.
        lifetime_frames = max(0.0, b_settings.lifetime)
        loop_frames = (window_stop - window_start) * self.fps
        repeats = (max(1, math.ceil(lifetime_frames / loop_frames))
                   if cyclic and loop_frames > 0 else 1)
        visible_start = window_start * self.fps
        PARTICLE_TIMELINE_RANGES.append(
            (visible_start, visible_start + loop_frames * repeats + lifetime_frames))

        b_settings["niftools_preview_frame_start"] = b_settings.frame_start
        b_settings["niftools_preview_frame_end"] = b_settings.frame_end
        b_settings["niftools_preview_count"] = b_settings.count
        b_settings["niftools_preview_birth_rate"] = nif_ps.birth_rate
        b_settings["niftools_particle_cyclic"] = cyclic

    def get_emission_window(self, n_block, n_emitter_controller):
        """The (start, stop, loops) window a particle system emits over, in seconds.

        A manager-controlled emitter controller carries no timing of its own: the
        controller sequence that plays it decides both the window and whether it
        loops. Reading the controller's own stale times instead is what leaves
        imported systems emitting long past the end of their animation.
        """

        for sequence, controlled in self.iter_sequence_entries(n_block):
            if str(controlled.controller_type or "") != "NiPSysEmitterCtlr":
                continue
            if sequence.stop_time > sequence.start_time:
                cyclic = sequence.cycle_type == NifClasses.CycleType.CYCLE_LOOP
                return sequence.start_time, sequence.stop_time, cyclic

        start_time = n_emitter_controller.start_time
        stop_time = n_emitter_controller.stop_time
        if stop_time <= start_time:
            # a controller with no window of its own runs for as long as it is played
            return 0.0, 0.0, int(n_emitter_controller.flags) & 6 == 0
        return start_time, stop_time, int(n_emitter_controller.flags) & 6 == 0

    def get_birth_rate_curve(self, n_block, n_emitter_controller, nif_ps):
        """The birth rate of a system as (keys, constant); only one of the two is set."""

        for _, controlled in self.iter_sequence_entries(n_block):
            if (str(controlled.controller_type or "") == "NiPSysEmitterCtlr"
                    and str(controlled.interpolator_id or "") == "BirthRate"):
                keys, constant = self.float_curve(controlled.interpolator)
                if keys or constant is not None:
                    return keys, constant

        keys, constant = self.float_curve(n_emitter_controller.interpolator)
        if keys or constant is not None:
            return keys, constant

        # Manager-controlled blend interpolators do not carry their active value in
        # the nif. Derive a stable preview rate from the particle pool instead.
        average_life = particles.mean_lifetime(nif_ps.life_span, nif_ps.life_span_variation)
        if nif_ps.max_particles and average_life > 0:
            return [], nif_ps.max_particles / average_life
        return [], None

    def get_active_intervals(self, n_block, n_emitter, n_emitter_controller,
                             n_modifier_active, window_start, window_stop):
        """The spans of the emission window over which the emitter is actually on."""

        intervals = [(window_start, window_stop)]

        active_curves = []
        for _, controlled in self.iter_sequence_entries(n_block):
            if (str(controlled.controller_type or "") == "NiPSysEmitterCtlr"
                    and str(controlled.interpolator_id or "") == "EmitterActive"):
                active_curves.append(controlled.interpolator)
            elif str(controlled.controller_type or "") == "NiPSysModifierActiveCtlr":
                if self.controls_emitter(controlled, n_emitter):
                    active_curves.append(controlled.interpolator)

        n_visibility = getattr(n_emitter_controller, "visibility_interpolator", None)
        if not active_curves and n_visibility is not None:
            active_curves.append(n_visibility)
        for n_controller in n_modifier_active:
            if self.controls_emitter(n_controller, n_emitter):
                active_curves.append(n_controller.interpolator)

        for n_interpolator in active_curves:
            keys, constant = self.bool_curve(n_interpolator)
            if keys:
                gate = particles.true_intervals(keys, window_start, window_stop)
            elif constant is not None:
                gate = [(window_start, window_stop)] if constant else []
            else:
                continue
            intervals = self.intersect_intervals(intervals, gate)

        return intervals

    @staticmethod
    def controls_emitter(n_controller, n_emitter):
        """Whether a modifier-active controller switches a system's emitter on and off."""
        if n_emitter is None:
            return False
        modifier_name = str(getattr(n_controller, "modifier_name", "")
                            or getattr(n_controller, "controller_id", "") or "")
        return modifier_name == str(n_emitter.name or "")

    @staticmethod
    def intersect_intervals(left_intervals, right_intervals):
        """The overlap of two sorted lists of (start, stop) spans."""
        overlap = []
        for left_start, left_stop in left_intervals:
            for right_start, right_stop in right_intervals:
                start = max(left_start, right_start)
                stop = min(left_stop, right_stop)
                if stop > start:
                    overlap.append((start, stop))
        return sorted(overlap)

    def cap_to_particle_pool(self, total, duration, nif_ps, n_emitter):
        """Limit a particle count to what the nif's fixed particle pool can hold.

        Gamebryo births into a pool of ``max_particles``; once it is full nothing
        else is born. Blender keeps every particle it is told to emit, so without
        this cap a system with a high birth rate becomes far denser than in game.
        """

        life_span = nif_ps.life_span
        variation = nif_ps.life_span_variation
        if not life_span and not variation and n_emitter is not None:
            life_span = max(0.0, n_emitter.life_span)
            variation = max(0.0, n_emitter.life_span_variation)
        average_life = particles.mean_lifetime(life_span, variation)
        capped = particles.max_alive_count(nif_ps.max_particles, average_life, duration)
        if capped is None or capped >= total:
            return total
        NifLog.debug(f"Birth rate capped by the {nif_ps.max_particles} particle pool: "
                     f"{total:.1f} -> {capped:.1f} particles.")
        return capped

    @staticmethod
    def iter_sequence_entries(n_block):
        """The controller sequence entries that drive a particle system."""
        return SEQUENCE_CONTROLLED_BLOCKS.get(str(n_block.name), ())

    @staticmethod
    def float_curve(n_interpolator):
        """(keys, constant) of a float interpolator; both empty when it holds no scalar."""
        if not isinstance(n_interpolator, NifClasses.NiFloatInterpolator):
            return [], None
        n_key_group = getattr(getattr(n_interpolator, "data", None), "data", None)
        keys = list(getattr(n_key_group, "keys", ()) or ())
        if keys:
            return [(float(key.time), max(0.0, float(key.value))) for key in keys], None
        value = float(n_interpolator.value)
        return [], value if 0 <= value < 1e30 else None

    @staticmethod
    def bool_curve(n_interpolator):
        """(keys, constant) of a boolean interpolator; both empty when it holds no value."""
        if not isinstance(n_interpolator, NifClasses.NiBoolInterpolator):
            return [], None
        n_key_group = getattr(getattr(n_interpolator, "data", None), "data", None)
        keys = list(getattr(n_key_group, "keys", ()) or ())
        if keys:
            return [(float(key.time), bool(key.value)) for key in keys], None
        # 2 is the nif's "unset" boolean, which leaves the emitter enabled
        return [], bool(n_interpolator.value) if int(n_interpolator.value) != 2 else True

    @staticmethod
    def iter_controllers(n_block):
        """Walk the controller list of a block."""
        n_controller = n_block.controller
        while n_controller:
            yield n_controller
            n_controller = n_controller.next_controller

    @staticmethod
    def build_emitter_mesh(b_mesh, b_settings, nif_ps):
        """Generate emitter geometry matching the nif emitter volume, so that the
        particle system previews in the viewport the way the nif describes it."""
        b_bmesh = bmesh.new()
        emitter_type = nif_ps.particle_emitter_type

        if emitter_type == "NiPSysSphereEmitter" and nif_ps.emitter_radius > 0:
            bmesh.ops.create_icosphere(b_bmesh, subdivisions=2, radius=nif_ps.emitter_radius)
        elif emitter_type == "NiPSysCylinderEmitter" and nif_ps.emitter_radius > 0:
            bmesh.ops.create_cone(b_bmesh, cap_ends=True, cap_tris=False, segments=16,
                                  radius1=nif_ps.emitter_radius, radius2=nif_ps.emitter_radius,
                                  depth=max(nif_ps.emitter_height, 1e-4))
        elif emitter_type == "NiPSysBoxEmitter" and max(nif_ps.emitter_width, nif_ps.emitter_depth,
                                                        nif_ps.emitter_height) > 0:
            bmesh.ops.create_cube(b_bmesh, size=1.0)
            bmesh.ops.scale(b_bmesh, vec=(max(nif_ps.emitter_width, 1e-4),
                                          max(nif_ps.emitter_depth, 1e-4),
                                          max(nif_ps.emitter_height, 1e-4)),
                            verts=b_bmesh.verts)
        else:
            # point emitters, and volumes with no size, emit from a single vertex at the origin
            b_bmesh.verts.new((0.0, 0.0, 0.0))
            if emitter_type not in particles.PARTICLE_OBJECT_EMITTERS:
                b_settings.emit_from = 'VERT'
            # an emitter that emits from another object keeps the emission mode the
            # nif asked for. Its real geometry arrives once that object is imported

        b_bmesh.to_mesh(b_mesh)
        b_bmesh.free()
        b_mesh.update()

    # Sprite preview.
    #
    # A NIF sprite particle is a camera facing textured quad whose size, rotation
    # and color all change over the life of the individual particle. Blender's
    # legacy particle system has no billboard renderer, and its Particle Info
    # shader node returns nothing in EEVEE, so the lifecycle is reproduced with the
    # mechanisms that do work per particle in every engine:
    #
    #  * size  - a particle texture mapped to 'Strand / Particle', which Blender
    #            evaluates against the true age of each particle every frame;
    #  * rotation - a collection of pre-rotated quads, one picked per particle;
    #  * color - a ramp over the Particle Info age, which is exact under Cycles,
    #            blended down to the lifetime average where that node is unavailable.

    # Upper bound on the quads generated for one system, shared between the
    # subtexture cells of its atlas and its rotation variants.
    MAX_SPRITE_VARIANTS = 48

    # Rotation spread, in radians, below which pre-rotated sprite variants would all
    # look the same and are not worth the extra objects
    MIN_SPRITE_ANGLE_SPREAD = 0.35

    # Half width of a sprite quad whose particle radius is one, given that the nif
    # radius is measured from the centre of the sprite to its corners
    SPRITE_RADIUS_TO_EXTENT = 0.7071067811865476

    def configure_particle_render(self, n_block, b_obj, b_psys):
        """Give sprite particles textured quads instead of Blender's gray halo preview."""

        if isinstance(n_block, (NifClasses.BSStripParticleSystem,
                                NifClasses.NiMeshParticleSystem)):
            return

        b_settings = b_psys.settings
        nif_ps = b_settings.nif_particle_system

        self.apply_grow_fade_texture(b_settings, nif_ps)

        n_offsets = list(getattr(n_block.data, "subtexture_offsets", ()) or ())
        if bool(getattr(n_block.data, "has_texture_indices", False)) and len(n_offsets) > 1:
            # the nif picks a subtexture index independently for every particle
            uv_cells = [self.subtexture_uv_bounds(n_offset) for n_offset in n_offsets]
        elif n_offsets:
            uv_cells = [self.subtexture_uv_bounds(n_offsets[0])]
        else:
            uv_cells = [(0.0, 1.0, 0.0, 1.0)]

        spins = self.sprite_spins(nif_ps, len(uv_cells))
        b_material = (
            self.create_sprite_preview_material(b_obj.active_material, b_settings, nif_ps)
            if b_obj.active_material else None
        )

        b_previews = []
        for cell_index, uv_bounds in enumerate(uv_cells):
            for spin_index, (angle, angular_speed) in enumerate(spins):
                suffix = ""
                if len(uv_cells) > 1:
                    suffix += f" {cell_index + 1}"
                if len(spins) > 1:
                    suffix += f".{spin_index + 1}"
                b_previews.append(self.create_sprite_preview(
                    b_settings, uv_bounds, suffix, b_material, angle, angular_speed))

        if len(b_previews) == 1:
            b_settings.render_type = 'OBJECT'
            b_settings.instance_object = b_previews[0]
        else:
            # A particle collection gives each instance its own atlas cell and
            # rotation without scene-visible helper cards or shader approximations.
            b_collection = bpy.data.collections.new(f"{b_settings.name} Particle Sprites")
            b_collection["niftools_particle_preview"] = True
            for b_preview in b_previews:
                b_collection.objects.link(b_preview)
            b_settings.render_type = 'COLLECTION'
            b_settings.instance_collection = b_collection
            b_settings.use_collection_pick_random = True
            b_settings.use_whole_collection = False

        # Blender applies particle rotation after the instance object's transform,
        # which would tilt the view-facing quad out of the image plane. The sprites
        # carry their own rotation instead. The exporter restores the exact NIF
        # rotation data from the typed properties.
        b_settings["niftools_billboard_preview"] = True
        b_settings.use_rotations = False
        b_settings.rotation_mode = 'NONE'
        b_settings.angular_velocity_mode = 'NONE'

    def apply_grow_fade_texture(self, b_settings, nif_ps):
        """Drive Blender's per particle size from the NiPSysGrowFadeModifier curve.

        A particle texture using the 'Strand / Particle' coordinate is sampled at the
        true normalized age of every particle, on every frame, so grow and fade land
        on the same lifecycle the physics uses. That also makes the sprites visibly
        born small, which a single averaged radius never does.
        """

        if not nif_ps.use_grow_fade:
            return
        grow_time = max(0.0, nif_ps.grow_time)
        fade_time = max(0.0, nif_ps.fade_time)
        base_scale = max(0.0, min(1.0, nif_ps.grow_fade_base_scale))
        if (grow_time <= 0 and fade_time <= 0) or base_scale >= 0.999999:
            return

        lifetime = max(1e-4, b_settings.lifetime / self.fps)
        positions = {0.0, 1.0}
        if grow_time > 0:
            positions.add(min(1.0, grow_time / lifetime))
        if fade_time > 0:
            positions.add(max(0.0, 1.0 - fade_time / lifetime))
        if grow_time > 0 and fade_time > 0:
            # the point at which the growing and fading ramps cross
            positions.add(max(0.0, min(1.0, grow_time / (grow_time + fade_time))))

        b_texture = bpy.data.textures.new(f"{b_settings.name} Grow Fade", 'BLEND')
        b_texture["niftools_particle_preview"] = True
        b_texture.use_color_ramp = True
        b_ramp = b_texture.color_ramp
        b_ramp.interpolation = 'LINEAR'
        while len(b_ramp.elements) > 1:
            b_ramp.elements.remove(b_ramp.elements[-1])

        for index, position in enumerate(sorted(positions)):
            b_element = (b_ramp.elements[0] if index == 0
                         else b_ramp.elements.new(position))
            b_element.position = position
            scale = self.grow_fade_scale(
                position * lifetime, lifetime, grow_time, fade_time, base_scale)
            b_element.color = (scale, scale, scale, 1.0)

        b_slot = b_settings.texture_slots.add()
        b_slot.texture = b_texture
        b_slot.texture_coords = 'STRAND'
        b_slot.blend_type = 'MULTIPLY'
        # A new slot maps several influences by default, and the emission time one in
        # particular would feed this curve back into when particles are born.
        for influence in dir(b_slot):
            if influence.startswith("use_map_"):
                setattr(b_slot, influence, False)
        b_slot.use_map_size = True
        b_slot.size_factor = 1.0
        b_settings["niftools_grow_fade_texture"] = True

    @staticmethod
    def grow_fade_scale(age, lifetime, grow_time, fade_time, base_scale):
        """The NiPSysGrowFadeModifier size multiplier of a particle at a given age."""
        scale = 1.0
        if grow_time > 0:
            scale = min(scale, base_scale + (1.0 - base_scale) * min(1.0, age / grow_time))
        if fade_time > 0:
            scale = min(scale, base_scale
                        + (1.0 - base_scale) * min(1.0, max(0.0, lifetime - age) / fade_time))
        return max(0.0, min(1.0, scale))

    @staticmethod
    def sprite_spins(nif_ps, cell_count):
        """(start angle, angular speed) pairs for the rotated sprite variants.

        The variants are spread evenly over the NIF rotation ranges rather than drawn
        randomly, so importing the same nif twice always produces the same sprites.
        """

        if not nif_ps.use_rotation_modifier:
            return [(0.0, 0.0)]
        angle = nif_ps.rotation_angle
        angle_variation = abs(nif_ps.rotation_angle_variation)
        speed = nif_ps.rotation_speed
        speed_variation = abs(nif_ps.rotation_speed_variation)
        spinning = max(abs(speed), speed_variation) > 1e-6
        if not spinning and angle_variation < Particle.MIN_SPRITE_ANGLE_SPREAD:
            # every particle would end up at the same angle anyway
            return [(angle, 0.0)]

        count = max(2, min(6, Particle.MAX_SPRITE_VARIANTS // max(1, cell_count)))
        spins = []
        for index in range(count):
            # sample the middle of each band rather than its edges, so that a full
            # circle of variation does not put the first and last variant on the
            # same visual angle
            spread = -1.0 + 2.0 * (index + 0.5) / count
            # a second, incommensurable sequence keeps the angle and the speed of a
            # variant from being correlated, which would look like a single fan
            offset = ((index * 0.6180339887498949) % 1.0) * 2.0 - 1.0
            variant_speed = speed + speed_variation * offset
            if nif_ps.random_rot_speed_sign and index % 2:
                variant_speed = -variant_speed
            spins.append((angle + angle_variation * spread, variant_speed))
        return spins

    @staticmethod
    def subtexture_uv_bounds(n_offset):
        """Convert a NIF (left, width, top, height) cell to Blender UV bounds."""

        u_min = max(0.0, min(1.0, n_offset.x))
        u_max = max(u_min, min(1.0, n_offset.x + n_offset.y))
        v_max = max(0.0, min(1.0, 1.0 - n_offset.z))
        v_min = max(0.0, min(v_max, v_max - n_offset.w))
        return u_min, u_max, v_min, v_max

    @staticmethod
    def create_sprite_preview(b_settings, uv_bounds, suffix, b_material,
                              angle=0.0, angular_speed=0.0):
        """Create an unlinked, UV-mapped quad used as a particle render object."""

        b_name = f"{b_settings.name} Particle Sprite{suffix}"
        b_mesh = bpy.data.meshes.new(b_name)
        # The nif particle radius is the distance from the centre of the sprite to
        # each of its corners, not to its edges, so the quad a radius of one produces
        # is only sqrt(2) units across. Treating the radius as a half width is what
        # made imported particles noticeably larger than the same effect in game.
        extent = Particle.SPRITE_RADIUS_TO_EXTENT
        b_mesh.from_pydata(
            [(-extent, -extent, 0.0), (extent, -extent, 0.0),
             (extent, extent, 0.0), (-extent, extent, 0.0)],
            [],
            [(0, 1, 2, 3)],
        )
        b_mesh.update()

        u_min, u_max, v_min, v_max = uv_bounds
        b_uv_layer = b_mesh.uv_layers.new(name="UVMap")
        b_uvs = (
            (u_min, v_min), (u_max, v_min), (u_max, v_max), (u_min, v_max),
        )
        for loop_index, uv in enumerate(b_uvs):
            b_uv_layer.data[loop_index].uv = uv

        # the billboard update reads these back to spin the quad in its own plane
        b_mesh["niftools_particle_sprite_angle"] = angle
        b_mesh["niftools_particle_sprite_speed"] = angular_speed

        b_preview = bpy.data.objects.new(b_name, b_mesh)
        b_preview["niftools_particle_preview"] = True
        b_preview.display_type = 'TEXTURED'

        # ParticleSettings keeps this object datablock alive and can instance it
        # without linking it to the scene. Keeping it unlinked removes the
        # otherwise useless standalone card and Outliner clutter while Material
        # Preview, EEVEE and Cycles continue to render the particle instances.

        if b_material:
            b_mesh.materials.append(b_material)
        return b_preview

    def create_sprite_preview_material(self, b_source_material, b_settings, nif_ps):
        """Build a Blender-native DDS material solely for viewport particle sprites.

        The full NIF shader remains on the particle emitter and is what the exporter
        reads. A plain Principled shader is used here because EEVEE Material Preview
        reliably recognizes its Alpha input, unlike transparent/additive custom shader
        groups whose emitted color and surface alpha can disagree.
        """

        b_material = bpy.data.materials.new(
            f"{b_settings.name} Particle Sprite Material")
        b_material["niftools_particle_preview"] = True
        b_material.use_nodes = True
        b_material.use_backface_culling = False
        try:
            # Match the NIF material's imported transparency. Forcing DITHERED
            # makes low-alpha smoke and additive sprites effectively disappear
            # in EEVEE Material Preview even though Cycles can still show them.
            b_material.surface_render_method = b_source_material.surface_render_method
        except AttributeError:
            b_material.blend_method = getattr(
                b_source_material, "blend_method", 'HASHED')
        try:
            b_material.use_transparency_overlap = True
        except AttributeError:
            pass

        b_nodes = b_material.node_tree.nodes
        b_links = b_material.node_tree.links
        b_nodes.clear()
        b_output = b_nodes.new('ShaderNodeOutputMaterial')
        b_principled = b_nodes.new('ShaderNodeBsdfPrincipled')
        b_principled.inputs['Roughness'].default_value = 1.0
        if b_principled.inputs.get('Emission Strength'):
            b_principled.inputs['Emission Strength'].default_value = 1.0

        b_source_image_node = next(
            (node for node in b_source_material.node_tree.nodes
             if node.type == 'TEX_IMAGE' and node.image),
            None,
        )
        if b_source_image_node:
            b_image = b_nodes.new('ShaderNodeTexImage')
            b_image.image = b_source_image_node.image
            b_image.interpolation = b_source_image_node.interpolation
            b_image.extension = b_source_image_node.extension
            color_output = b_image.outputs['Color']
            alpha_output = b_image.outputs['Alpha']
            if nif_ps.use_simple_color:
                color_output, alpha_output = self.create_particle_color_nodes(
                    b_material.node_tree, nif_ps, color_output, alpha_output)
            b_links.new(color_output, b_principled.inputs['Base Color'])
            b_emission = b_principled.inputs.get('Emission Color')
            if b_emission:
                b_links.new(color_output, b_emission)
            b_links.new(alpha_output, b_principled.inputs['Alpha'])

        b_links.new(b_principled.outputs[0], b_output.inputs['Surface'])
        return b_material

    def create_particle_color_nodes(self, b_tree, nif_ps, image_color, image_alpha):
        """Apply the BSPSysSimpleColorModifier color and alpha over particle age.

        Cycles resolves the age of every particle through the Particle Info node and
        gets the exact curve. EEVEE has no per particle age at all, and reports a
        lifetime of zero, which is what selects the lifetime-averaged color there.
        """

        b_nodes = b_tree.nodes
        b_links = b_tree.links
        stops = self.simple_color_stops(nif_ps)

        b_ramp = b_nodes.new('ShaderNodeValToRGB')
        b_ramp.color_ramp.interpolation = 'LINEAR'
        while len(b_ramp.color_ramp.elements) > 1:
            b_ramp.color_ramp.elements.remove(b_ramp.color_ramp.elements[-1])
        for index, (position, color) in enumerate(stops):
            b_element = (b_ramp.color_ramp.elements[0] if index == 0
                         else b_ramp.color_ramp.elements.new(position))
            b_element.position = position
            b_element.color = color

        b_particle_info = b_nodes.new('ShaderNodeParticleInfo')
        b_age = b_nodes.new('ShaderNodeMath')
        b_age.operation = 'DIVIDE'
        b_age.use_clamp = True
        b_links.new(b_particle_info.outputs['Age'], b_age.inputs[0])
        b_links.new(b_particle_info.outputs['Lifetime'], b_age.inputs[1])
        b_links.new(b_age.outputs[0], b_ramp.inputs['Fac'])

        # A real particle always has a lifetime of at least one frame, so a reported
        # lifetime of zero can only mean the engine does not support the node.
        b_supported = b_nodes.new('ShaderNodeMath')
        b_supported.operation = 'MINIMUM'
        b_supported.inputs[1].default_value = 1.0
        b_supported.use_clamp = True
        b_links.new(b_particle_info.outputs['Lifetime'], b_supported.inputs[0])

        average_color, average_alpha = self.average_stop_color(stops)

        b_color = b_nodes.new('ShaderNodeMix')
        b_color.data_type = 'RGBA'
        b_color.blend_type = 'MIX'
        b_color.inputs['A'].default_value = average_color
        b_links.new(b_supported.outputs[0], b_color.inputs['Factor'])
        b_links.new(b_ramp.outputs['Color'], b_color.inputs['B'])

        b_alpha = b_nodes.new('ShaderNodeMix')
        b_alpha.data_type = 'FLOAT'
        b_alpha.inputs['A'].default_value = average_alpha
        b_links.new(b_supported.outputs[0], b_alpha.inputs['Factor'])
        b_links.new(b_ramp.outputs['Alpha'], b_alpha.inputs['B'])

        b_tinted = b_nodes.new('ShaderNodeMix')
        b_tinted.data_type = 'RGBA'
        b_tinted.blend_type = 'MULTIPLY'
        b_tinted.inputs['Factor'].default_value = 1.0
        b_links.new(image_color, b_tinted.inputs['A'])
        b_links.new(b_color.outputs['Result'], b_tinted.inputs['B'])

        b_faded = b_nodes.new('ShaderNodeMath')
        b_faded.operation = 'MULTIPLY'
        b_links.new(image_alpha, b_faded.inputs[0])
        b_links.new(b_alpha.outputs['Result'], b_faded.inputs[1])

        return b_tinted.outputs['Result'], b_faded.outputs[0]

    @staticmethod
    def simple_color_stops(nif_ps):
        """The (position, RGBA) stops a BSPSysSimpleColorModifier describes.

        The three colors are held and cross-faded over the particle lifetime. Color 1
        holds until 'color 1 end', reaches color 2 at 'color 1 start', holds until
        'color 2 end' and reaches color 3 at 'color 2 start'. Alpha follows the same
        shape, but the fade in and fade out percentages override where its two
        cross-fades happen.
        """

        colors = [
            mathutils.Color(tuple(getattr(nif_ps, name))[:3]).from_srgb_to_scene_linear()
            for name in ("simple_color_1", "simple_color_2", "simple_color_3")
        ]
        alphas = [tuple(getattr(nif_ps, name))[3]
                  for name in ("simple_color_1", "simple_color_2", "simple_color_3")]
        # nifskope's field names are ordered end-before-start, and shipped nifs store
        # the four percentages in ascending order regardless of what they are called
        bounds = sorted(max(0.0, min(1.0, value)) for value in (
            nif_ps.simple_color_1_start, nif_ps.simple_color_1_end,
            nif_ps.simple_color_2_start, nif_ps.simple_color_2_end))
        fade_in = max(0.0, min(1.0, nif_ps.simple_color_fade_in))
        fade_out = max(fade_in, min(1.0, nif_ps.simple_color_fade_out))

        def blend(values, position, hold_1, reach_2, hold_2, reach_3):
            """Value at a position of the hold/cross-fade/hold/cross-fade curve."""
            if position <= hold_1:
                return values[0]
            if position < reach_2:
                return Particle.lerp(values[0], values[1],
                                     (position - hold_1) / max(1e-6, reach_2 - hold_1))
            if position <= hold_2:
                return values[1]
            if position < reach_3:
                return Particle.lerp(values[1], values[2],
                                     (position - hold_2) / max(1e-6, reach_3 - hold_2))
            return values[2]

        def color_at(position):
            if bounds[3] <= 0.0:
                # every percentage left at zero leaves only the middle color in use
                return colors[1]
            return blend(colors, position, *bounds)

        def alpha_at(position):
            if fade_in <= 0.0 and fade_out >= 1.0:
                return alphas[1]
            # alpha reaches color 2 at the fade in and leaves it at the fade out
            return blend(alphas, position, 0.0, fade_in, fade_out, 1.0)

        positions = {0.0, 1.0}
        positions.update(bound for bound in bounds if 0.0 < bound < 1.0)
        positions.update(bound for bound in (fade_in, fade_out) if 0.0 < bound < 1.0)
        return [(position, tuple(color_at(position)) + (alpha_at(position),))
                for position in sorted(positions)[:32]]

    @staticmethod
    def lerp(left, right, fraction):
        """Linear blend of two floats or two colors."""
        if isinstance(left, mathutils.Color):
            return mathutils.Color(tuple(
                channel + (other - channel) * fraction
                for channel, other in zip(left, right)))
        return left + (right - left) * fraction

    @staticmethod
    def average_stop_color(stops):
        """The lifetime average of a stop list, as (RGBA color, alpha)."""

        if len(stops) < 2:
            color = stops[0][1] if stops else (1.0, 1.0, 1.0, 1.0)
            return tuple(color[:3]) + (1.0,), color[3]

        totals = [0.0, 0.0, 0.0, 0.0]
        span = 0.0
        for (left_position, left_color), (right_position, right_color) in zip(stops, stops[1:]):
            width = right_position - left_position
            if width <= 0:
                continue
            span += width
            for index in range(4):
                totals[index] += (left_color[index] + right_color[index]) * 0.5 * width
        if span <= 0:
            color = stops[0][1]
            return tuple(color[:3]) + (1.0,), color[3]
        average = [total / span for total in totals]
        return (average[0], average[1], average[2], 1.0), average[3]

def import_emitter_objects():
    """Resolve particle object references and billboards after the NIF tree is available."""

    for b_settings, nif_ps, n_target_block in PENDING_EMITTER_OBJECTS:
        b_obj = find_imported_object(n_target_block)
        if b_obj:
            nif_ps.particle_emitter_object = b_obj
            particle_object = find_particle_object(b_settings)
            if particle_object:
                build_object_emitter_preview(particle_object, b_obj, nif_ps, b_settings)
        else:
            NifLog.warn(f"Could not find the imported object for emitter target "
                         f"'{getattr(n_target_block, 'name', n_target_block)}'")
    PENDING_EMITTER_OBJECTS.clear()

    for b_settings, n_modifier in PENDING_GRAVITY_PREVIEWS:
        n_gravity_object = getattr(n_modifier, "gravity_object", None)
        b_gravity_object = (
            find_imported_object(n_gravity_object)
            if n_gravity_object is not None else None
        )
        Particle.import_gravity_preview(
            n_modifier, b_settings, b_gravity_object)
        # The system was created before its linked gravity object could be
        # resolved. Explicitly invalidate Blender's initial zero-force cache so
        # the subsequent hidden pre-roll uses the resolved direction.
        b_particle_object = find_particle_object(b_settings)
        if b_particle_object:
            for b_psys in b_particle_object.particle_systems:
                if b_psys.settings != b_settings:
                    continue
                cache_start = b_psys.point_cache.frame_start
                b_psys.point_cache.frame_start = cache_start + 1
                b_psys.point_cache.frame_start = cache_start
                b_settings.update_tag()
                break
        if n_gravity_object is not None and b_gravity_object is None:
            NifLog.warn(
                f"Could not resolve gravity object "
                f"'{getattr(n_gravity_object, 'name', n_gravity_object)}' "
                f"for particle system '{b_settings.name}'; using its stored axis.")
    if PENDING_GRAVITY_PREVIEWS:
        bpy.context.view_layer.update()
    PENDING_GRAVITY_PREVIEWS.clear()

    for b_settings, n_particle_meshes in PENDING_PARTICLE_MESHES:
        b_render_obj = find_imported_mesh_object(n_particle_meshes)
        if b_render_obj:
            b_settings.render_type = 'OBJECT'
            b_settings.instance_object = b_render_obj
        else:
            NifLog.warn(
                f"Could not find an imported mesh for mesh particle system "
                f"'{b_settings.name}'. Set Render As > Instance Object manually; "
                f"the original reference remains stored for export."
            )
    PENDING_PARTICLE_MESHES.clear()

    for reference, n_target_block in PENDING_NIF_REFERENCES:
        b_obj = find_imported_object(n_target_block)
        if b_obj:
            reference.target_object = b_obj
    PENDING_NIF_REFERENCES.clear()


def extend_cyclic_emission():
    """Keep looping systems emitting for as much of the visible timeline as they can.

    A nif emitter is restarted by every cycle of the controller sequence that plays
    it, so a system whose loop is shorter than the scene keeps producing particles at
    the same average rate. Blender has a single emission window per system, which is
    therefore stretched, and its count scaled with it.

    Emission stops one life span before the end of the scene. Blender clears a
    particle simulation when the timeline wraps, so anything still alive at the last
    frame would pop out of existence; leaving that tail free of new particles lets
    every particle finish its natural life instead.
    """

    scene_end = bpy.context.scene.frame_end
    for b_obj in DICT_PARTICLE_SYSTEMS.values():
        if not b_obj:
            continue
        for b_psys in b_obj.particle_systems:
            b_settings = b_psys.settings
            if not b_settings.get("niftools_particle_cyclic"):
                continue
            loop_length = b_settings.frame_end - b_settings.frame_start
            emission_end = scene_end - max(0.0, b_settings.lifetime)
            if loop_length <= 0 or emission_end <= b_settings.frame_end:
                continue
            b_settings.count = max(1, min(100000, int(round(
                b_settings.count * (emission_end - b_settings.frame_start) / loop_length))))
            b_settings.frame_end = emission_end
            b_settings["niftools_preview_frame_end"] = b_settings.frame_end
            b_settings["niftools_preview_count"] = b_settings.count
            b_psys.point_cache.frame_end = math.ceil(
                b_settings.frame_end + b_settings.lifetime)


def prime_particle_caches(max_primed_frames=90):
    """Step the start of the timeline so particle systems are not empty on arrival.

    Blender only simulates particles while the timeline advances, so a freshly
    imported system shows nothing at all until the user scrubs. Walking a short lead
    in fills that gap; the rest of the range caches during playback, which is both
    what Blender does for any other simulation and far quicker than caching a whole
    effect at import time.
    """

    global SUSPEND_BILLBOARDS

    b_scene = bpy.context.scene
    if not any(b_obj and b_obj.particle_systems
               for b_obj in DICT_PARTICLE_SYSTEMS.values()):
        return

    first_frame = max(0, int(math.floor(b_scene.frame_start)))
    last_frame = min(int(math.ceil(b_scene.frame_end)), first_frame + max_primed_frames)
    if last_frame <= first_frame:
        return

    original_frame = b_scene.frame_current
    # Every frame step fires the billboard frame change handler, which would rebuild
    # every sprite quad in the scene once per primed frame for no visible gain.
    SUSPEND_BILLBOARDS = True
    try:
        for frame in range(first_frame, last_frame + 1):
            b_scene.frame_set(frame)
        b_scene.frame_set(max(b_scene.frame_start, min(original_frame, b_scene.frame_end)))
    finally:
        SUSPEND_BILLBOARDS = False
    update_viewport_billboards(force=True)

def find_imported_object(n_block):
    """Find the Blender object imported for a nif block, by the name it was imported under."""
    if n_block in DICT_PARTICLE_SYSTEMS:
        return DICT_PARTICLE_SYSTEMS[n_block]
    n_name = block_store.import_name(n_block)
    for b_obj in bpy.data.objects:
        # objects only carry their nif name separately when Blender had to rename them
        if b_obj.name == n_name or getattr(b_obj.nif_object, "longname", "") == n_name:
            return b_obj
    return None


def find_particle_object(b_settings):
    """Find the scene object owning a particle settings datablock."""

    for b_obj in bpy.data.objects:
        for b_psys in b_obj.particle_systems:
            if b_psys.settings == b_settings:
                return b_obj
    return None


def build_object_emitter_preview(b_particle_obj, b_emitter_obj, nif_ps, b_settings=None):
    """Build Blender emission geometry from a referenced NIF emitter object."""

    if nif_ps.particle_emitter_type == "BSPSysArrayEmitter":
        if b_settings:
            b_settings.emit_from = 'VERT'
        matrix_to_particle = b_particle_obj.matrix_world.inverted()
        points = []
        pending = [b_emitter_obj]
        while pending:
            b_obj = pending.pop()
            points.append(matrix_to_particle @ b_obj.matrix_world.translation)
            pending.extend(b_obj.children)
        b_particle_obj.data.clear_geometry()
        b_particle_obj.data.from_pydata(points or [(0.0, 0.0, 0.0)], [], [])
        b_particle_obj.data.update()
        return

    if nif_ps.particle_emitter_type != "NiPSysMeshEmitter" or b_emitter_obj.type != 'MESH':
        return

    source_mesh = b_emitter_obj.data
    transform = b_particle_obj.matrix_world.inverted() @ b_emitter_obj.matrix_world
    emission_type = nif_ps.emitter_emission_type
    vertices = []
    faces = []

    if emission_type == "EMIT_FROM_VERTICES":
        vertices = [transform @ vertex.co for vertex in source_mesh.vertices]
    elif emission_type == "EMIT_FROM_FACE_CENTER":
        vertices = [transform @ polygon.center for polygon in source_mesh.polygons]
    elif emission_type == "EMIT_FROM_EDGE_CENTER":
        for edge in source_mesh.edges:
            midpoint = (source_mesh.vertices[edge.vertices[0]].co
                        + source_mesh.vertices[edge.vertices[1]].co) * 0.5
            vertices.append(transform @ midpoint)
    elif emission_type == "EMIT_FROM_EDGE_SURFACE":
        # Blender cannot emit continuously from edges. Eight evenly-spaced
        # vertices per edge give a close, deterministic viewport approximation.
        for edge in source_mesh.edges:
            start = source_mesh.vertices[edge.vertices[0]].co
            end = source_mesh.vertices[edge.vertices[1]].co
            for step in range(8):
                vertices.append(transform @ start.lerp(end, (step + 0.5) / 8.0))
    else:  # EMIT_FROM_FACE_SURFACE
        vertices = [transform @ vertex.co for vertex in source_mesh.vertices]
        faces = [tuple(polygon.vertices) for polygon in source_mesh.polygons]

    if not vertices:
        vertices = [(0.0, 0.0, 0.0)]
    if b_settings:
        # every emission type other than the face surface is approximated by points,
        # and Blender only emits along surface normals when it emits from faces
        b_settings.emit_from = 'FACE' if faces else 'VERT'
    b_particle_obj.data.clear_geometry()
    b_particle_obj.data.from_pydata(vertices, [], faces)
    b_particle_obj.data.update()


def find_imported_mesh_object(n_block):
    """Find the first imported mesh in a referenced particle-mesh node tree."""

    b_obj = find_imported_object(n_block)
    if b_obj and b_obj.type == 'MESH':
        return b_obj
    for n_child in getattr(n_block, "children", ()):
        if not n_child:
            continue
        b_obj = find_imported_mesh_object(n_child)
        if b_obj:
            return b_obj
    return None


def billboard_objects(rescan):
    """The (sprite previews, orientation helpers) this scene contains.

    Scanning every object in the file for its custom properties costs more than the
    work the billboards actually need, so the lists are only rebuilt on the viewport
    timer and reused by the far more frequent frame change updates.
    """

    global BILLBOARD_OBJECTS

    if rescan or BILLBOARD_OBJECTS is None:
        b_previews = []
        b_helpers = []
        for b_obj in bpy.data.objects:
            if b_obj.get("niftools_particle_preview"):
                if b_obj.type == 'MESH':
                    b_previews.append(b_obj)
            elif b_obj.get("niftools_billboard_orientation_helper"):
                b_helpers.append(b_obj)
        BILLBOARD_OBJECTS = (b_previews, b_helpers)
    return BILLBOARD_OBJECTS


def update_viewport_billboards(force=False, refresh_corrections=True):
    """Face imported particle sprites and billboard nodes toward the 3D viewport."""

    global LAST_VIEW_ROTATION

    if SUSPEND_BILLBOARDS:
        return
    window_manager = getattr(bpy.context, "window_manager", None)
    if not window_manager:
        return
    view_spaces = []
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                view_spaces.append((area.width * area.height, area.spaces.active.region_3d))
    if not view_spaces:
        return

    region_3d = max(view_spaces, key=lambda item: item[0])[1]
    view_rotation = region_3d.view_matrix.inverted_safe().to_quaternion()
    current_view = tuple(round(value, 7) for value in view_rotation)
    _, b_helpers = billboard_objects(refresh_corrections)
    helper_needs_update = any(
        tuple(b_helper.get("niftools_billboard_rotation", ())) != current_view
        for b_helper in b_helpers
    )
    if (not force and not helper_needs_update and LAST_VIEW_ROTATION is not None
            and abs(LAST_VIEW_ROTATION.dot(view_rotation)) > 0.999999):
        return
    LAST_VIEW_ROTATION = view_rotation.copy()
    update_billboard_geometry(view_rotation, refresh_corrections)


def update_render_billboards(scene):
    """Face imported particle sprites and billboard nodes toward the render camera."""

    if not scene or not scene.camera:
        return
    update_billboard_geometry(scene.camera.matrix_world.to_quaternion())


def update_billboard_geometry(view_rotation, refresh_corrections=True):
    """Update ordinary billboard constraints and compensate particle instance transforms.

    Blender's legacy particle instancer ignores constraints and evaluated rotation on an
    instance source object. It does use the object's mesh data, so rotate the four source
    vertices by ``instance_rotation^-1 @ view_rotation``. The final world-space particle
    quad then matches the viewport even when its emitter object is rotated.

    Those instance transforms can only be read from the depsgraph, which must never be
    evaluated from a frame change handler: doing so re-enters an evaluation that is
    already running and crashes Blender. The corrections depend on object transforms
    rather than on the frame, so a frame change reuses the ones last measured.
    """

    if SUSPEND_BILLBOARDS:
        return

    current_view = tuple(round(value, 7) for value in view_rotation)
    b_previews, b_helpers = billboard_objects(refresh_corrections)
    for b_helper in b_helpers:
        previous = b_helper.get("niftools_billboard_rotation")
        if previous and tuple(previous) == current_view:
            continue
        b_helper.rotation_mode = 'QUATERNION'
        b_helper.rotation_quaternion = view_rotation
        b_helper["niftools_billboard_rotation"] = current_view

    if not b_previews:
        return

    if refresh_corrections:
        INSTANCE_ROTATIONS.clear()
        preview_names = {b_preview.name for b_preview in b_previews}
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for instance in depsgraph.object_instances:
            if not instance.is_instance:
                continue
            b_original = getattr(instance.object, "original", None)
            name = getattr(b_original, "name", None)
            if name not in preview_names or name in INSTANCE_ROTATIONS:
                continue
            INSTANCE_ROTATIONS[name] = instance.matrix_world.to_quaternion()

    corrections = {
        name: rotation.inverted() @ view_rotation
        for name, rotation in INSTANCE_ROTATIONS.items()
    }

    extent = Particle.SPRITE_RADIUS_TO_EXTENT
    base_vertices = (
        (-extent, -extent, 0.0),
        (extent, -extent, 0.0),
        (extent, extent, 0.0),
        (-extent, extent, 0.0),
    )
    base_vectors = tuple(mathutils.Vector(vertex) for vertex in base_vertices)
    b_scene = bpy.context.scene
    seconds = b_scene.frame_current / max(1, b_scene.render.fps)
    spin_axis = mathutils.Vector((0.0, 0.0, 1.0))
    for b_preview in b_previews:
        b_mesh = b_preview.data
        correction = corrections.get(b_preview.name, view_rotation)
        # The NiPSysRotationModifier spins a sprite in its own plane, which has to
        # happen before the quad is turned to face the view.
        angle = b_mesh.get("niftools_particle_sprite_angle", 0.0)
        angle += b_mesh.get("niftools_particle_sprite_speed", 0.0) * seconds
        current = tuple(round(value, 7) for value in correction) + (round(angle, 5),)
        previous = b_mesh.get("niftools_billboard_rotation")
        if previous is not None and tuple(previous) == current:
            continue
        rotation = correction @ mathutils.Quaternion(spin_axis, angle) if angle else correction
        for b_vertex, base_vector in zip(b_mesh.vertices, base_vectors):
            b_vertex.co = rotation @ base_vector
        b_mesh["niftools_billboard_rotation"] = current
        b_mesh.update()
