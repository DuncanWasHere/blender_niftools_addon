"""Nif specific properties for Blender particle systems."""

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

from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty, StringProperty)
from bpy.types import PropertyGroup

from ..utils.decorators import register_classes, unregister_classes


def _update_birth_rate(self, context):
    b_settings = self.id_data
    reference_rate = b_settings.get("niftools_preview_birth_rate")
    reference_count = b_settings.get("niftools_preview_count")
    if reference_rate is not None and reference_count:
        # An imported count already accounts for the times the emitter is switched
        # off and for the nif's fixed particle pool, neither of which the raw birth
        # rate expresses. Re-applying the imported rate, as the controller channels
        # do while a nif loads, therefore has to leave that count alone.
        if reference_rate > 0 and abs(self.birth_rate - reference_rate) >= 1e-6:
            b_settings.count = max(1, min(100000, round(
                reference_count * self.birth_rate / reference_rate)))
        return
    fps = context.scene.render.fps
    duration = max((b_settings.frame_end - b_settings.frame_start) / fps, 1.0 / fps)
    b_settings.count = max(1, round(self.birth_rate * duration))


def _update_emission_start(self, context):
    self.id_data.frame_start = self.emission_start_time * context.scene.render.fps


def _update_emission_stop(self, context):
    self.id_data.frame_end = self.emission_stop_time * context.scene.render.fps


def _update_grow_fade_preview(self, _context):
    b_settings = self.id_data
    if not b_settings.get("niftools_grow_fade_preview"):
        return
    # Grow and fade are applied per particle by the imported size texture, so
    # Blender's geometric radius stays at the largest radius the NIF emitter can
    # produce and the random shrink covers the variation around it.
    _apply_radius(b_settings, self)


def _update_radius_variation(self, _context):
    _apply_radius(self.id_data, self)


def _apply_radius(b_settings, nif_ps):
    from ..utils import particles

    b_settings.particle_size = nif_ps.initial_radius + nif_ps.radius_variation
    b_settings.size_random = particles.random_factor_from_variation(
        nif_ps.initial_radius, nif_ps.radius_variation)


# Emitter block types that emit from a volume of their own, with the dimensions of that volume
VOLUME_EMITTERS = {
    "NiPSysSphereEmitter": ("emitter_radius",),
    "NiPSysBoxEmitter": ("emitter_width", "emitter_height", "emitter_depth"),
    "NiPSysCylinderEmitter": ("emitter_radius", "emitter_height"),
}

# Emitter block types that emit from another object in the scene
OBJECT_EMITTERS = ("NiPSysMeshEmitter", "BSPSysArrayEmitter")


class ParticleNifFieldProperty(PropertyGroup):
    """One typed leaf value from a NIF particle block.

    Unsupported NIF-only values live in real Blender properties instead of an
    opaque JSON string.  ``path`` identifies a member inside the block.
    """

    path: StringProperty(name="Field")
    value_type: EnumProperty(
        name="Type",
        items=[
            ("BOOL", "Boolean", ""),
            ("INT", "Integer", ""),
            ("FLOAT", "Float", ""),
            ("STRING", "String", ""),
        ],
        default="FLOAT",
    )
    bool_value: BoolProperty(name="Value")
    int_value: IntProperty(name="Value")
    float_value: FloatProperty(name="Value")
    string_value: StringProperty(name="Value")


class ParticleNifReferenceProperty(PropertyGroup):
    """A reference held by a NIF particle block."""

    path: StringProperty(name="Field")
    target_name: StringProperty(name="NIF Target")
    target_object: PointerProperty(name="Object", type=bpy.types.Object)


class ParticleNifBlockProperty(PropertyGroup):
    """Typed representation of one imported particle block."""

    role: EnumProperty(
        name="Role",
        items=[
            ("SYSTEM", "Particle System", ""),
            ("DATA", "Particle Data", ""),
            ("MODIFIER", "Modifier", ""),
            ("CONTROLLER", "Controller", ""),
            ("NESTED", "Nested Block", ""),
        ],
        default="MODIFIER",
    )
    block_type: StringProperty(name="Block Type")
    block_name: StringProperty(name="Name")
    parent_index: IntProperty(name="Parent Block", default=-1, min=-1)
    reference_name: StringProperty(name="Reference Field")
    fields: CollectionProperty(type=ParticleNifFieldProperty)
    references: CollectionProperty(type=ParticleNifReferenceProperty)


def _update_controller_channel(self, _context):
    """Apply controller channels that Blender can preview directly."""

    b_settings = self.id_data
    nif_ps = b_settings.nif_particle_system
    if (self.controller_type == "NiPSysEmitterCtlr"
            and self.interpolator_id == "BirthRate"):
        nif_ps.birth_rate = self.float_value
    elif (self.controller_type == "NiPSysEmitterCtlr"
          and self.interpolator_id == "EmitterActive"):
        nif_ps.emitter_visibility_value = int(self.bool_value)


class ParticleControllerChannelProperty(PropertyGroup):
    """One scalar particle channel supplied by a controller sequence."""

    sequence_name: StringProperty(name="Sequence")
    controller_type: StringProperty(name="Controller Type")
    controller_id: StringProperty(name="Controller ID")
    interpolator_id: StringProperty(name="Interpolator ID")
    value_type: EnumProperty(
        name="Value Type",
        items=[
            ("FLOAT", "Float", ""),
            ("BOOL", "Boolean", ""),
        ],
        default="FLOAT",
    )
    float_value: FloatProperty(name="Value", update=_update_controller_channel)
    bool_value: BoolProperty(name="Value", update=_update_controller_channel)


class ParticleSystemProperty(PropertyGroup):
    """Nif particle system settings, attached to Blender particle settings through a property pointer."""

    nif_blocks: CollectionProperty(
        name="NIF Particle Blocks",
        description="Typed NIF-only particle block values preserved for export",
        type=ParticleNifBlockProperty,
    )

    controller_channels: CollectionProperty(
        name="Particle Controller Channels",
        description="Typed scalar channels imported from NIF controller sequences",
        type=ParticleControllerChannelProperty,
    )

    particle_system_type: EnumProperty(
        name='Particle System Type',
        description='Particle system block to export',
        items=[("NiParticleSystem", "NiParticleSystem", "2D sprite-based particle system.", 0),
               ("BSStripParticleSystem", "BSStripParticleSystem",
                "Bethesda ribbon particle system, drawing each particle as a trailing strip.\n"
                "Fallout 3, Fallout New Vegas and Skyrim only.", 1),
               ("NiMeshParticleSystem", "NiMeshParticleSystem",
                "Particle system drawing a mesh for each particle.\n"
                "Not supported by the Bethesda games.", 2)],
        default='NiParticleSystem'
    )

    particle_emitter_type: EnumProperty(
        name='Particle Emitter Type',
        description='Particle emitter modifier to export',
        items=[("NiPSysSphereEmitter", "NiPSysSphereEmitter",
                "Randomly spawns particles within the radius of a sphere centered on a NiNode.", 0),
               ("NiPSysBoxEmitter", "NiPSysBoxEmitter",
                "Randomly spawns particles within a bounding box centered on a NiNode.", 1),
               ("NiPSysCylinderEmitter", "NiPSysCylinderEmitter",
                "Randomly spawns particles within the radius of a cylinder centered on a NiNode.", 2),
               ("NiPSysMeshEmitter", "NiPSysMeshEmitter",
                "Spawns particles from the vertices, edges or faces of one or more meshes.", 3),
               ("BSPSysArrayEmitter", "BSPSysArrayEmitter",
                "Evenly spawns particles across a NiNode and its children Nodes recursively.\n"
                "Randomizes the position, rotation, and scale of each NiNode when each particle is spawned.\n"
                "Fallout 3, Fallout New Vegas and Skyrim only.", 4)],
        default='NiPSysSphereEmitter'
    )

    max_particles: IntProperty(
        name='Max Particles',
        description='How many particles the system can keep alive at once, which is not the same as the '
                    'total number Blender emits over the emission window.\n'
                    'Zero derives it from the birth rate and the particle life span.\n'
                    'NiPSysData::BS Max Vertices',
        default=0,
        min=0,
        max=65535,
    )

    particle_emitter_object: PointerProperty(
        name='Particle Emitter Object',
        description='Object the particles are emitted from. '
                    'Used by mesh and array emitters; the parent node is used when this is empty',
        type=bpy.types.Object,
    )

    # Emitter volume, in Blender units. The generated emitter mesh is only a viewport aid.
    # These values are what gets exported.

    emitter_radius: FloatProperty(
        name='Emitter Radius',
        description='Radius of the sphere or cylinder particles spawn in.\n'
                    'NiPSysSphereEmitter/NiPSysCylinderEmitter::Radius',
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
    )

    emitter_width: FloatProperty(
        name='Emitter Width',
        description='Size of the emitter box along X.\nNiPSysBoxEmitter::Width',
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
    )

    emitter_height: FloatProperty(
        name='Emitter Height',
        description='Size of the emitter box or cylinder along Z.\n'
                    'NiPSysBoxEmitter/NiPSysCylinderEmitter::Height',
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
    )

    emitter_depth: FloatProperty(
        name='Emitter Depth',
        description='Size of the emitter box along Y.\nNiPSysBoxEmitter::Depth',
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
    )

    initial_radius: FloatProperty(
        name="NIF Initial Radius",
        description="Unscaled particle radius before grow/fade is applied.\nNiPSysEmitter::Initial Radius",
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
        update=_update_grow_fade_preview,
    )

    radius_variation: FloatProperty(
        name="NIF Radius Variation",
        description="Random variation of the unscaled particle radius.\nNiPSysEmitter::Radius Variation",
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
        update=_update_radius_variation,
    )

    # Life span. Gamebryo varies the life span symmetrically around a base value,
    # while Blender only shortens a maximum, so the nif pair is kept exactly.

    life_span: FloatProperty(
        name="NIF Life Span",
        description="Base particle lifetime in seconds.\nNiPSysEmitter::Life Span",
        default=0.0,
        min=0.0,
        subtype='TIME_ABSOLUTE',
    )

    life_span_variation: FloatProperty(
        name="NIF Life Span Variation",
        description="Symmetric random variation of the particle lifetime, in seconds.\n"
                    "NiPSysEmitter::Life Span Variation",
        default=0.0,
        min=0.0,
        subtype='TIME_ABSOLUTE',
    )

    # Emission direction. The direction itself comes from the Blender velocity
    # (particle settings -> velocity -> object aligned), only its randomness lives here.
    # The nif angles are kept as well, because a mesh emitter that emits along its
    # surface normals has no direction vector for Blender to store them in.

    emitter_speed: FloatProperty(
        name="NIF Speed",
        description="Initial particle speed.\nNiPSysEmitter::Speed",
        default=0.0,
        min=0.0,
    )

    emitter_speed_variation: FloatProperty(
        name="NIF Speed Variation",
        description="Random variation of the initial particle speed.\n"
                    "NiPSysEmitter::Speed Variation",
        default=0.0,
        min=0.0,
    )

    declination: FloatProperty(
        name='Declination',
        description='Angle between the emission direction and the emitter Z axis.\n'
                    'NiPSysEmitter::Declination',
        default=0.0,
        subtype='ANGLE',
    )

    planar_angle: FloatProperty(
        name='Planar Angle',
        description='Angle of the emission direction around the emitter Z axis.\n'
                    'NiPSysEmitter::Planar Angle',
        default=0.0,
        subtype='ANGLE',
    )

    initial_color: FloatVectorProperty(
        name='Initial Color',
        description='Color particles are given when they are born, which tints the\n'
                    'particle texture.\nNiPSysEmitter::Initial Color',
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    declination_variation: FloatProperty(
        name='Declination Variation',
        description='Random spread of the emission direction away from the emission axis.\n'
                    'NiPSysEmitter::Declination Variation',
        default=0.0,
        subtype='ANGLE',
    )

    planar_angle_variation: FloatProperty(
        name='Planar Angle Variation',
        description='Random spread of the emission direction around the emission axis.\n'
                    'NiPSysEmitter::Planar Angle Variation',
        default=0.0,
        subtype='ANGLE',
    )

    world_space: BoolProperty(
        name='World Space',
        description='Simulate particles in world space, so they are left behind when the system moves.\n'
                    'Turn off for particles that should follow their parent node.\n'
                    'NiParticleSystem::World Space',
        default=True,
    )

    # Emitter and update controllers. Times are seconds, matching the NIF.

    birth_rate: FloatProperty(
        name="Birth Rate",
        description="Particles born per second.\nNiPSysEmitterCtlr interpolator value",
        default=0.0,
        min=0.0,
        update=_update_birth_rate,
    )

    emission_start_time: FloatProperty(
        name="Start Time",
        description="Time at which emission starts.\nNiPSysEmitterCtlr::Start Time",
        default=0.0,
        subtype='TIME_ABSOLUTE',
        update=_update_emission_start,
    )

    emission_stop_time: FloatProperty(
        name="Stop Time",
        description="Time at which emission stops.\nNiPSysEmitterCtlr::Stop Time",
        default=0.0,
        subtype='TIME_ABSOLUTE',
        update=_update_emission_stop,
    )

    emitter_controller_flags: IntProperty(
        name="Emitter Controller Flags",
        description="NiPSysEmitterCtlr::Flags",
        default=72,
    )

    emitter_controller_frequency: FloatProperty(
        name="Emitter Frequency",
        description="NiPSysEmitterCtlr::Frequency",
        default=1.0,
    )

    emitter_controller_phase: FloatProperty(
        name="Emitter Phase",
        description="NiPSysEmitterCtlr::Phase",
        default=0.0,
    )

    emitter_visibility_value: IntProperty(
        name="Visibility Value",
        description="Raw NiBoolInterpolator value (0 false, 1 true, 2 invalid/manager controlled)",
        default=2,
        min=0,
        max=2,
    )

    update_controller_flags: IntProperty(
        name="Update Controller Flags",
        description="NiPSysUpdateCtlr::Flags",
        default=76,
    )

    update_controller_frequency: FloatProperty(
        name="Update Frequency",
        description="NiPSysUpdateCtlr::Frequency",
        default=1.0,
    )

    update_controller_phase: FloatProperty(
        name="Update Phase",
        description="NiPSysUpdateCtlr::Phase",
        default=0.0,
    )

    update_start_time: FloatProperty(
        name="Update Start Time",
        description="NiPSysUpdateCtlr::Start Time",
        default=0.0,
        subtype='TIME_ABSOLUTE',
    )

    update_stop_time: FloatProperty(
        name="Update Stop Time",
        description="NiPSysUpdateCtlr::Stop Time",
        default=0.0,
        subtype='TIME_ABSOLUTE',
    )

    # NiPSysData flags. These remain independent of Blender's preview choices.

    data_has_vertices: BoolProperty(name="Has Vertices", default=True)
    data_has_normals: BoolProperty(name="Has Normals", default=False)
    data_has_vertex_colors: BoolProperty(name="Has Vertex Colors", default=False)
    data_has_radii: BoolProperty(name="Has Radii", default=True)
    data_has_sizes: BoolProperty(name="Has Sizes", default=True)
    data_has_rotations: BoolProperty(name="Has Rotations", default=False)
    data_has_rotation_angles: BoolProperty(name="Has Rotation Angles", default=False)
    data_has_rotation_axes: BoolProperty(name="Has Rotation Axes", default=False)
    data_has_rotation_speeds: BoolProperty(name="Has Rotation Speeds", default=False)
    data_has_texture_indices: BoolProperty(name="Has Texture Indices", default=False)

    # Mesh emitter settings

    emitter_emission_type: EnumProperty(
        name='Emission Type',
        description='Part of the emitter mesh particles spawn from.\nNiPSysMeshEmitter::Emission Type',
        items=[("EMIT_FROM_VERTICES", "Vertices", "Spawn particles on the mesh vertices.", 0),
               ("EMIT_FROM_FACE_CENTER", "Face Centers", "Spawn particles at the center of each face.", 1),
               ("EMIT_FROM_EDGE_CENTER", "Edge Centers", "Spawn particles at the center of each edge.", 2),
               ("EMIT_FROM_FACE_SURFACE", "Face Surface", "Spawn particles anywhere on the faces.", 3),
               ("EMIT_FROM_EDGE_SURFACE", "Edge Surface", "Spawn particles anywhere along the edges.", 4)],
        default="EMIT_FROM_VERTICES",
    )

    emitter_velocity_type: EnumProperty(
        name='Initial Velocity Type',
        description='How the initial direction of a particle is derived from the emitter mesh.\n'
                    'NiPSysMeshEmitter::Initial Velocity Type',
        items=[("VELOCITY_USE_NORMALS", "Use Normals", "Emit along the surface normal.", 0),
               ("VELOCITY_USE_RANDOM", "Random", "Emit in a random direction.", 1),
               ("VELOCITY_USE_DIRECTION", "Use Direction", "Emit along the emission axis.", 2)],
        default="VELOCITY_USE_NORMALS",
    )

    # Age and spawn settings

    spawn_on_death: BoolProperty(
        name='Spawn On Death',
        description='Generate new particles when the old ones die.\nNiPSysAgeDeathModifier::Spawn On Death',
        default=False,
    )

    num_spawn_generations: IntProperty(
        name='Spawn Generations',
        description='How many times each particle may spawn new particles.\n'
                    'NiPSysSpawnModifier::Num Spawn Generations',
        default=0,
        min=0,
        max=65535,
    )

    percentage_spawned: FloatProperty(
        name='Spawn Chance',
        description='Fraction of the particles that actually spawn each generation.\n'
                    'NiPSysSpawnModifier::Percentage Spawned',
        default=1.0,
        min=0.0,
        max=1.0,
    )

    min_num_to_spawn: IntProperty(
        name='Minimum Spawn Count',
        description='The minimum number of particles that spawn each generation '
                    'if they pass the percentage check.\nNiPSysSpawnModifier::Min Num To Spawn',
        default=1,
        min=0,
        max=65535,
    )

    max_num_to_spawn: IntProperty(
        name='Maximum Spawn Count',
        description='The maximum number of particles that spawn each generation '
                    'if they pass the percentage check.\nNiPSysSpawnModifier::Max Num To Spawn',
        default=1,
        min=0,
        max=65535,
    )

    spawn_speed_variation: FloatProperty(
        name='Spawn Speed Variation',
        description='Random spread of the speed given to spawned particles.\n'
                    'NiPSysSpawnModifier::Spawn Speed Variation',
        default=0.0,
        soft_min=-1.0,
        soft_max=1.0,
    )

    spawn_dir_variation: FloatProperty(
        name='Spawn Direction Variation',
        description='Random spread of the direction given to spawned particles.\n'
                    'NiPSysSpawnModifier::Spawn Dir Variation',
        default=0.0,
        soft_min=-1.0,
        soft_max=1.0,
    )

    # Rotation

    random_rot_speed_sign: BoolProperty(
        name='Randomly Negate Angular Velocity',
        description='Randomly negate the initial speed of particle rotations upon spawning.\n'
                    'NiPSysRotationModifier::Random Rot Speed Sign',
        default=False,
    )

    rotation_speed_variation: FloatProperty(
        name='Angular Velocity Variation',
        description='Random spread of the particle angular velocity.\n'
                    'NiPSysRotationModifier::Rotation Speed Variation',
        default=0.0,
        subtype='ANGLE',
    )

    random_rot_axis: BoolProperty(
        name='Random Rotation Axis',
        description='Give each particle a random rotation axis instead of the fixed one.\n'
                    'NiPSysRotationModifier::Random Axis',
        default=True,
    )

    use_rotation_modifier: BoolProperty(
        name="Particle Rotation",
        description="Use a NiPSysRotationModifier",
        default=False,
    )

    rotation_speed: FloatProperty(
        name="Angular Velocity",
        description="NiPSysRotationModifier::Rotation Speed",
        default=0.0,
        subtype='ANGLE',
    )

    rotation_angle: FloatProperty(
        name="Initial Angle",
        description="NiPSysRotationModifier::Rotation Angle",
        default=0.0,
        subtype='ANGLE',
    )

    rotation_angle_variation: FloatProperty(
        name="Initial Angle Variation",
        description="NiPSysRotationModifier::Rotation Angle Variation",
        default=0.0,
        min=0.0,
        subtype='ANGLE',
    )

    rotation_axis: FloatVectorProperty(
        name="Rotation Axis",
        description="NiPSysRotationModifier::Axis",
        size=3,
        default=(1.0, 0.0, 0.0),
        subtype='DIRECTION',
    )

    # Grow and fade

    use_grow_fade: BoolProperty(
        name='Grow And Fade',
        description='Scale particles up when they are born and down before they die.\n'
                    'Exports a NiPSysGrowFadeModifier',
        default=False,
        update=_update_grow_fade_preview,
    )

    grow_time: FloatProperty(
        name='Grow Time',
        description='Seconds a particle takes to reach full size after being born.\n'
                    'NiPSysGrowFadeModifier::Grow Time',
        default=0.0,
        min=0.0,
        subtype='TIME_ABSOLUTE',
        update=_update_grow_fade_preview,
    )

    fade_time: FloatProperty(
        name='Fade Time',
        description='Seconds a particle takes to shrink away before it dies.\n'
                    'NiPSysGrowFadeModifier::Fade Time',
        default=0.0,
        min=0.0,
        subtype='TIME_ABSOLUTE',
        update=_update_grow_fade_preview,
    )

    grow_fade_base_scale: FloatProperty(
        name='Base Scale',
        description='Size multiplier applied to particles by the grow and fade modifier.\n'
                    'NiPSysGrowFadeModifier::Base Scale',
        default=1.0,
        min=0.0,
        update=_update_grow_fade_preview,
    )

    grow_generation: IntProperty(
        name="Grow Generation",
        description="NiPSysGrowFadeModifier::Grow Generation",
        default=0,
        min=0,
    )

    fade_generation: IntProperty(
        name="Fade Generation",
        description="NiPSysGrowFadeModifier::Fade Generation",
        default=0,
        min=0,
    )

    # Color over lifetime (Bethesda simple color modifier)

    use_simple_color: BoolProperty(
        name='Simple Color',
        description='Blend particle color through three colors over their lifetime.\n'
                    'Exports a BSPSysSimpleColorModifier. Fallout 3, Fallout New Vegas and Skyrim only',
        default=False,
    )

    simple_color_1: FloatVectorProperty(
        name='Color 1',
        description='First color of the simple color modifier.\nBSPSysSimpleColorModifier::Colors[0]',
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    simple_color_2: FloatVectorProperty(
        name='Color 2',
        description='Second color of the simple color modifier.\nBSPSysSimpleColorModifier::Colors[1]',
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    simple_color_3: FloatVectorProperty(
        name='Color 3',
        description='Third color of the simple color modifier.\nBSPSysSimpleColorModifier::Colors[2]',
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    simple_color_fade_in: FloatProperty(
        name='Fade In',
        description='Point in the particle lifetime at which the alpha of color 1 has fully faded into color 2.\n'
                    'BSPSysSimpleColorModifier::Fade In Percent',
        default=0.1,
        min=0.0,
        max=1.0,
    )

    simple_color_fade_out: FloatProperty(
        name='Fade Out',
        description='Point in the particle lifetime at which the alpha of color 2 starts fading into color 3.\n'
                    'BSPSysSimpleColorModifier::Fade Out Percent',
        default=0.9,
        min=0.0,
        max=1.0,
    )

    simple_color_1_start: FloatProperty(
        name='Color 1 Start',
        description='Point in the particle lifetime at which the second color reaches its full value.\n'
                    'BSPSysSimpleColorModifier::Color 1 Start Percent',
        default=0.0,
        min=0.0,
        max=1.0,
    )

    simple_color_1_end: FloatProperty(
        name='Color 1 End',
        description='Point in the particle lifetime at which the first color starts fading into the second.\n'
                    'BSPSysSimpleColorModifier::Color 1 End Percent',
        default=0.0,
        min=0.0,
        max=1.0,
    )

    simple_color_2_start: FloatProperty(
        name='Color 2 Start',
        description='Point in the particle lifetime at which the third color reaches its full value. Named Color 2 Start by nifskope.\n'
                    'BSPSysSimpleColorModifier::Color 2 Start Percent',
        default=0.0,
        min=0.0,
        max=1.0,
    )

    simple_color_2_end: FloatProperty(
        name='Color 2 End',
        description='Point in the particle lifetime at which the second color starts fading into the third.\n'
                    'BSPSysSimpleColorModifier::Color 2 End Percent',
        default=1.0,
        min=0.0,
        max=1.0,
    )

    # Subtextures (flipbook/spritesheet)

    subtexture_columns: IntProperty(
        name='Subtexture Columns',
        description='Number of subtexture columns in the particle texture.\n'
                    'One column means the whole texture is used.\nNiParticlesData::Subtexture Offsets',
        default=1,
        min=1,
        max=16,
    )

    subtexture_rows: IntProperty(
        name='Subtexture Rows',
        description='Number of subtexture rows in the particle texture.\n'
                    'One row means the whole texture is used.\nNiParticlesData::Subtexture Offsets',
        default=1,
        min=1,
        max=16,
    )

    use_subtexture_animation: BoolProperty(
        name='Animate Subtextures',
        description='Play the subtextures as an animation over each particle lifetime.\n'
                    'Exports a BSPSysSubTexModifier. Fallout 3, Fallout New Vegas and Skyrim only',
        default=False,
    )

    subtexture_start_frame: FloatProperty(
        name='Start Frame',
        description='First subtexture of the animation.\nBSPSysSubTexModifier::Start Frame',
        default=0.0,
        min=0.0,
    )

    subtexture_frame_count: FloatProperty(
        name='Frame Count',
        description='Number of subtextures played over the particle lifetime.\n'
                    'BSPSysSubTexModifier::Frame Count',
        default=0.0,
        min=0.0,
    )

    # Bethesda strip particles

    bs_strip_max_point_count: IntProperty(
        name='Max Point Count',
        description='Number of points each strip particle is defined with.\n'
                    'BSStripPSysData::Max Point Count',
        default=4,
        min=2,
        max=65535,
    )

    bs_strip_start_cap_size: FloatProperty(
        name='Start Cap Size',
        description='Width of the strip at its leading end.\nBSStripPSysData::Start Cap Size',
        default=0.0,
    )

    bs_strip_end_cap_size: FloatProperty(
        name='End Cap Size',
        description='Width of the strip at its trailing end.\nBSStripPSysData::End Cap Size',
        default=0.0,
    )

    bs_strip_do_z_prepass: BoolProperty(
        name='Do Z Prepass',
        description='Render the strips in a depth prepass.\nBSStripPSysData::Do Z Prepass',
        default=False,
    )

    use_bs_wind: BoolProperty(
        name='Game Wind',
        description='Push the particles around with the wind of the game world.\n'
                    'Exports a BSWindModifier. Fallout 3, Fallout New Vegas and Skyrim only',
        default=False,
    )

    bs_wind_strength: FloatProperty(
        name='Wind Strength',
        description='How strongly the game wind pushes the particles.\nBSWindModifier::Strength',
        default=1.0,
    )

    # Bethesda level of detail

    use_bs_lod: BoolProperty(
        name='Particle LOD',
        description='Reduce emission and particle size with distance from the camera.\n'
                    'Exports a BSPSysLODModifier. Fallout 3, Fallout New Vegas and Skyrim only',
        default=False,
    )

    bs_lod_begin_distance: FloatProperty(
        name='LOD Begin Distance',
        description='Distance at which the system starts to scale down.\n'
                    'BSPSysLODModifier::LOD Begin Distance',
        default=0.1,
    )

    bs_lod_end_distance: FloatProperty(
        name='LOD End Distance',
        description='Distance at which the system reaches its smallest size.\n'
                    'BSPSysLODModifier::LOD End Distance',
        default=0.7,
    )

    bs_lod_end_emit_scale: FloatProperty(
        name='LOD End Emit Scale',
        description='Emission rate multiplier at the end distance.\nBSPSysLODModifier::End Emit Scale',
        default=0.2,
    )

    bs_lod_end_size: FloatProperty(
        name='LOD End Size',
        description='Particle size multiplier at the end distance.\nBSPSysLODModifier::End Size',
        default=1.0,
    )


class MasterParticleSystemProperty(PropertyGroup):
    """Settings for objects exported as a BSMasterParticleSystem node."""

    max_emitter_objects: IntProperty(
        name='Max Emitter Objects',
        description='Maximum number of emitter objects the master particle system tracks.\n'
                    'BSMasterParticleSystem::Max Emitter Objects',
        default=20,
        min=0,
        max=65535,
    )


CLASSES = [
    ParticleNifFieldProperty,
    ParticleNifReferenceProperty,
    ParticleNifBlockProperty,
    ParticleControllerChannelProperty,
    ParticleSystemProperty,
    MasterParticleSystemProperty,
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.ParticleSettings.nif_particle_system = bpy.props.PointerProperty(type=ParticleSystemProperty)
    bpy.types.Object.nif_master_particle_system = bpy.props.PointerProperty(type=MasterParticleSystemProperty)


def unregister():
    del bpy.types.Object.nif_master_particle_system
    del bpy.types.ParticleSettings.nif_particle_system

    unregister_classes(CLASSES, __name__)
