"""Conversions shared by the particle system importer and exporter."""

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
import mathutils

# Nif particle system block types, in the order of the enum in the particle settings
PARTICLE_SYSTEM_TYPES = ("NiParticleSystem", "BSStripParticleSystem", "NiMeshParticleSystem")

# Nif particle emitter block types, in the order of the enum in the particle settings
PARTICLE_EMITTER_TYPES = ("NiPSysSphereEmitter", "NiPSysBoxEmitter", "NiPSysCylinderEmitter",
                          "NiPSysMeshEmitter", "BSPSysArrayEmitter")

# Emitter block types whose emission geometry lives on another node in the nif
PARTICLE_OBJECT_EMITTERS = ("NiPSysMeshEmitter", "BSPSysArrayEmitter")


def get_scale_correction():
    """Blender units per nif unit, as used by the import and export operators."""
    return bpy.context.scene.niftools_scene.scale_correction


def nif_to_blender_units(value):
    """Convert a nif length (radius, speed, extent) to Blender units.
    Object transforms and geometry are scaled by the import spell, these fields are not."""
    return value * get_scale_correction()


def blender_to_nif_units(value):
    """Convert a Blender length (radius, speed, extent) to nif units."""
    scale_correction = get_scale_correction()
    if not scale_correction:
        return value
    return value / scale_correction


def angles_to_direction(declination, planar_angle):
    """Convert a nif emission direction, given as spherical angles around the emitter's Z axis,
    to a unit direction vector. A declination of zero emits straight up the Z axis."""
    return mathutils.Vector((math.sin(declination) * math.cos(planar_angle),
                             math.sin(declination) * math.sin(planar_angle),
                             math.cos(declination)))


def direction_to_angles(direction, fallback_planar_angle=0.0):
    """Convert a direction vector to the nif emission angles (declination, planar angle).
    The planar angle is undefined for directions along the Z axis, where the fallback is used."""
    direction = mathutils.Vector(direction)
    if not direction.length:
        return 0.0, fallback_planar_angle
    direction = direction.normalized()
    declination = math.acos(max(-1.0, min(1.0, direction.z)))
    if abs(direction.x) < 1e-6 and abs(direction.y) < 1e-6:
        return declination, fallback_planar_angle
    return declination, math.atan2(direction.y, direction.x)


def emission_duration(b_settings, fps):
    """Length of a particle system's emission window, in seconds."""
    duration = (b_settings.frame_end - b_settings.frame_start) / fps
    # a system that emits on a single frame still has to birth its particles somewhere
    return duration if duration > 0 else 1.0 / fps


def sample_linear(keys, time):
    """Value of a linearly interpolated (time, value) key list at a time.
    The first and last keys are held outside the key range, as the engine does."""
    if not keys:
        return 0.0
    if time <= keys[0][0]:
        return keys[0][1]
    if time >= keys[-1][0]:
        return keys[-1][1]
    for (left_time, left_value), (right_time, right_value) in zip(keys, keys[1:]):
        if time <= right_time:
            if right_time <= left_time:
                return right_value
            fraction = (time - left_time) / (right_time - left_time)
            return left_value + (right_value - left_value) * fraction
    return keys[-1][1]


def integrate_linear(keys, start, stop):
    """Area under a linearly interpolated (time, value) key list over [start, stop].

    This is the number of particles a birth rate curve births over an interval,
    which is what Blender's total particle count has to reproduce.
    """
    if stop <= start or not keys:
        return 0.0
    if len(keys) == 1:
        return keys[0][1] * (stop - start)

    area = 0.0
    # the curve is held constant before the first and after the last key
    if start < keys[0][0]:
        area += keys[0][1] * (min(stop, keys[0][0]) - start)
    if stop > keys[-1][0]:
        area += keys[-1][1] * (stop - max(start, keys[-1][0]))
    for (left_time, left_value), (right_time, right_value) in zip(keys, keys[1:]):
        segment_start = max(start, left_time)
        segment_stop = min(stop, right_time)
        if segment_stop <= segment_start or right_time <= left_time:
            continue
        value_start = sample_linear(keys, segment_start)
        value_stop = sample_linear(keys, segment_stop)
        area += (value_start + value_stop) * 0.5 * (segment_stop - segment_start)
    return area


def true_intervals(keys, start, stop, default=True):
    """The [start, stop] spans over which a stepped boolean key list is true.

    Boolean nif keys hold their value until the next key, and the first key's value
    also applies to everything before it.
    """
    if stop < start:
        return []
    if not keys:
        return [(start, stop)] if default else []

    intervals = []
    span_start = None
    # the value in force at the window start is the last key at or before it
    value = bool(keys[0][1])
    for key_time, key_value in keys:
        if key_time <= start:
            value = bool(key_value)
    if value:
        span_start = start

    for key_time, key_value in keys:
        if key_time <= start or key_time > stop:
            continue
        key_value = bool(key_value)
        if key_value and span_start is None:
            span_start = key_time
        elif not key_value and span_start is not None:
            intervals.append((span_start, key_time))
            span_start = None
    if span_start is not None:
        intervals.append((span_start, stop))
    return [span for span in intervals if span[1] > span[0]]


def mean_lifetime(life_span, life_span_variation):
    """Average particle lifetime of a nif emitter, in the same unit as its inputs.

    Gamebryo varies the life span symmetrically and drops particles whose lifetime
    would be negative, so the mean is not simply the base life span.
    """
    variation = abs(life_span_variation)
    if variation <= 0:
        return max(0.0, life_span)
    low = life_span - variation
    high = life_span + variation
    if low >= 0:
        return life_span
    if high <= 0:
        return 0.0
    # only the positive part of the interval produces particles that live at all
    return high * high / (4.0 * variation)


def max_alive_count(max_particles, average_lifetime, duration):
    """How many particles a capped nif system can birth over a window.

    A nif system owns a fixed particle pool, so however high its birth rate is, it
    cannot keep more than ``max_particles`` alive. Blender has no such pool, and
    reproducing the raw rate is what makes imported systems far denser than the game.

    A burst shorter than the particle lifetime simply fills the pool once, while a
    window longer than the lifetime refills it every ``average_lifetime`` seconds.
    """
    if max_particles <= 0 or average_lifetime <= 0 or duration <= 0:
        return None
    return max_particles * duration / min(duration, average_lifetime)


def birth_rate_from_count(b_settings, fps):
    """Particles born per second, as the nif emitter controller stores it."""
    return b_settings.count / emission_duration(b_settings, fps)


def count_from_birth_rate(birth_rate, b_settings, fps):
    """Total particle count over the emission window, as Blender stores it."""
    return max(1, round(birth_rate * emission_duration(b_settings, fps)))


def auto_max_particles(birth_rate, life_span, life_span_variation):
    """How many particles a system can have alive at once, from how fast it births them
    and how long they live. Used when the particle settings do not state a count of their own."""
    return max(1, min(65535, math.ceil(birth_rate * (life_span + life_span_variation))))


def random_factor_from_variation(base, variation):
    """Convert a symmetric NIF variation to Blender's maximum-relative randomness.

    The caller stores ``base + variation`` as the Blender maximum. Blender then
    shortens that maximum by up to this factor, reproducing the NIF interval
    ``base - variation`` through ``base + variation``.
    """
    maximum = base + max(0.0, variation)
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, 2.0 * variation / maximum))


def lifetime_random_from_variation(life_span, life_span_variation):
    """Convert symmetric NIF lifetime variation to Blender's maximum-relative randomness."""
    return random_factor_from_variation(life_span, life_span_variation)


def variation_from_random_factor(maximum, random_factor):
    """Recover a symmetric NIF variation from a Blender maximum and randomness."""
    return maximum * max(0.0, min(1.0, random_factor)) * 0.5


def base_from_random_factor(maximum, random_factor):
    """Recover the NIF base value from a Blender maximum and randomness."""
    return maximum - variation_from_random_factor(maximum, random_factor)


def variation_from_lifetime_random(maximum_life_span, lifetime_random):
    """Recover symmetric NIF variation from Blender's maximum lifetime."""
    return variation_from_random_factor(maximum_life_span, lifetime_random)


def base_lifetime_from_blender(maximum_life_span, lifetime_random):
    """Recover the NIF base lifetime from Blender's maximum and randomness."""
    return base_from_random_factor(maximum_life_span, lifetime_random)


def preview_unchanged(b_settings, key, value, tolerance=1e-5):
    """Whether a Blender value still matches what the importer derived it from.

    The nif carries values Blender cannot hold exactly, such as a life span that
    varies further down than its base or an emission direction that only exists as
    surface normals. Those survive the round trip as long as the user has not edited
    the Blender value the importer wrote alongside them.
    """
    stored = b_settings.get(key)
    if stored is None:
        return False
    if hasattr(value, "__len__"):
        return (len(stored) == len(value)
                and all(abs(left - right) < tolerance
                        for left, right in zip(stored, value)))
    return abs(stored - value) < tolerance


def lifetime_edited(b_settings):
    """Whether the Blender lifetime differs from the one the importer derived."""
    return not (
        preview_unchanged(b_settings, "niftools_preview_lifetime", b_settings.lifetime, 1e-3)
        and preview_unchanged(b_settings, "niftools_preview_lifetime_random",
                              b_settings.lifetime_random))


def export_life_span(b_settings, nif_ps, fps):
    """The (life span, variation) pair a particle system exports, in seconds."""
    if not lifetime_edited(b_settings):
        return nif_ps.life_span, nif_ps.life_span_variation
    maximum_life_span = b_settings.lifetime / fps
    return (base_lifetime_from_blender(maximum_life_span, b_settings.lifetime_random),
            variation_from_lifetime_random(maximum_life_span, b_settings.lifetime_random))


def subtexture_offsets(columns, rows):
    """Build the nif subtexture offset vectors for a columns x rows sprite sheet.

    Sections start from the upper-left corner of the texture. Despite some older
    documentation describing Y/W in the opposite order, shipped Bethesda NIFs
    consistently store ``(u, width, v, height)``. For example, a 4x2 atlas stores
    X positions 0/.25/.5/.75 with Y=.25, and Z positions 0/.5 with W=.5.
    """
    section_width = 1.0 / columns
    section_height = 1.0 / rows
    return [(column * section_width, section_width, row * section_height, section_height)
            for row in range(rows) for column in range(columns)]


def subtexture_grid(n_offsets):
    """Recover the (columns, rows) of a sprite sheet from its nif subtexture offsets.
    Counting the distinct positions avoids having to guess which component holds the width."""
    if not n_offsets:
        return 1, 1
    columns = len({round(n_offset.x, 4) for n_offset in n_offsets})
    rows = len({round(n_offset.z, 4) for n_offset in n_offsets})
    return max(1, columns), max(1, rows)
