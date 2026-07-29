"""Classes for exporting NIF particle blocks."""

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
from ....modules.nif_export.object import DICT_NAMES
from ....modules.nif_export.particle.emitter import Emitter
from ....modules.nif_export.particle.modifier import Modifier, add_modifier, sort_modifiers
from ....modules.nif_export.property.object import ObjectProperty
from ....utils import math as nif_math
from ....utils import particles
from . import block_properties
from ....utils.flags import to_unsigned_32
from ....utils.logging import NifLog
from ....utils.singleton import NifData
from nifgen.formats.nif import classes as NifClasses

# Nif version that introduced the modern particle system blocks (10.2.0.0)
MIN_PARTICLE_SYSTEM_VERSION = 0x0A020000

# Bethesda version that introduced the BS particle blocks (Fallout 3)
MIN_BS_PARTICLE_VERSION = 34


class Particle:
    """
    Main interface class for exporting NIF particle blocks
    (i.e., NiParticleSystem and subclasses, their data, modifiers and controllers).

    Imported systems carry typed properties for their original blocks so Blender unsupported
    values survive the round trip.
    """

    # Modifier pointers to a node elsewhere in the nif
    SCENE_REFS = ("emitter_object", "field_object", "gravity_object", "bomb_object",
                  "drag_object", "inherit_object", "bound_object")

    # Modifier pointers to another modifier of the same particle system
    CHAIN_REFS = ("spawn_modifier", "modifier")

    # Modifier pointers to a list of geometry blocks
    MESH_LIST_REFS = ("emitter_meshes", "meshes")

    def __init__(self):
        self.nif_scene = bpy.context.scene.niftools_scene
        self.target_game = self.nif_scene.game
        self.fps = bpy.context.scene.render.fps

        self.object_property_helper = ObjectProperty()
        self.emitter_helper = Emitter()
        self.modifier_helper = Modifier()

    def export_particles(self, b_particle_objects, b_force_field_objects, n_root_node):
        """Export the particle systems of all Blender objects that carry one."""

        if not b_particle_objects:
            return

        if NifData.data.version < MIN_PARTICLE_SYSTEM_VERSION:
            NifLog.warn(f"{self.target_game} predates the modern particle system blocks. "
                        f"{len(b_particle_objects)} particle object(s) will not be exported.")
            return

        for b_obj in b_particle_objects:
            n_parent_node = self.get_parent_node(b_obj, n_root_node)
            for index, b_psys in enumerate(b_obj.particle_systems):
                self.export_particle_system(b_obj, b_psys, index, n_parent_node, b_force_field_objects)

    @staticmethod
    def get_parent_node(b_obj, n_root_node):
        """The node an object's particle systems are attached to."""
        if not b_obj.parent:
            return n_root_node
        n_parent_node = DICT_NAMES.get(b_obj.parent.name)
        if not n_parent_node:
            NifLog.warn(f"Parent {b_obj.parent.name} of particle object {b_obj.name} was not exported as a node. "
                        f"Its particle systems are attached to the root node instead.")
            return n_root_node
        return n_parent_node

    def export_particle_system(self, b_obj, b_psys, index, n_parent_node, b_force_field_objects):
        """Export a single Blender particle system as a particle system block."""

        nif_ps = b_psys.settings.nif_particle_system
        restored = self.restore_typed_blocks(nif_ps) if nif_ps.nif_blocks else None
        restored_system = restored["SYSTEM"][0] if restored and restored["SYSTEM"] else None

        block_type = type(restored_system).__name__ if restored_system else nif_ps.particle_system_type
        block_type = self.get_supported_type(block_type, "NiParticleSystem", b_obj.name)

        NifLog.info(f"Exporting particle system {b_psys.name} of {b_obj.name} as a {block_type} block.")

        if restored_system and type(restored_system).__name__ == block_type:
            n_particle_system = block_store.register_block(restored_system, b_obj)
        else:
            n_particle_system = block_store.create_block(block_type, b_obj)

        n_particle_system.name = block_store.get_full_name(b_obj)
        if index > 0:
            # an object can hold several particle systems, but a nif block only holds one
            n_particle_system.name = f"{n_particle_system.name}:{index}"
        nif_math.set_object_matrix(b_obj, n_particle_system)
        self.set_flags(b_obj, n_particle_system)
        n_particle_system.world_space = nif_ps.world_space

        n_parent_node.add_child(n_particle_system)
        if index == 0:
            DICT_NAMES[b_obj.name] = n_particle_system
        self.register_with_master(n_particle_system, n_parent_node)

        self.export_data(b_obj, b_psys, nif_ps, restored, n_particle_system)
        n_emitter = self.export_modifiers(
            b_obj, b_psys, nif_ps, restored, n_particle_system, b_force_field_objects)
        self.export_controllers(b_obj, b_psys, nif_ps, restored, n_particle_system, n_emitter)

        # Material, alpha, texture and shader properties, as for any other geometry
        # block. For a newly-authored object particle system, accept the instance
        # object's material when the emitter helper itself has none.
        b_property_obj = b_obj
        b_instance_obj = b_psys.settings.instance_object
        if (not b_obj.material_slots and b_instance_obj
                and b_instance_obj.material_slots):
            b_property_obj = b_instance_obj
        self.object_property_helper.export_object_properties(b_property_obj, n_particle_system)

        return n_particle_system

    def restore_typed_blocks(self, nif_ps):
        """Rebuild imported particle blocks from registered Blender properties."""

        return block_properties.restore_particle_blocks(
            nif_ps, block_store.create_block, self.resolve_typed_reference)

    def resolve_typed_reference(self, target):
        if isinstance(target, bpy.types.Object):
            return self.resolve_blender_object(target)
        return self.resolve_object(target)

    def set_flags(self, b_obj, n_block):
        """Set the object flags of a particle system block, as for any other node."""
        if b_obj.nif_object.flags != 0:
            n_block.flags = to_unsigned_32(b_obj.nif_object.flags)
        elif self.nif_scene.is_bs():
            n_block.flags = 0x000E
        else:
            n_block.flags = 0x000C

    def get_supported_type(self, block_type, fallback, object_name):
        """Replace a block type the target game does not support with the closest one it does.
        An empty fallback means the block is dropped."""
        unsupported = ""
        if block_type.startswith("BS") and NifData.data.bs_header.bs_version < MIN_BS_PARTICLE_VERSION:
            unsupported = f"{self.target_game} does not support {block_type}"
        elif block_type == "NiMeshParticleSystem" and self.nif_scene.is_bs():
            unsupported = f"The Bethesda games do not support {block_type}"

        if not unsupported:
            return block_type
        if fallback:
            NifLog.warn(f"{unsupported} (used by {object_name}), exporting a {fallback} instead.")
        else:
            NifLog.warn(f"{unsupported} (used by {object_name}), it will not be exported.")
        return fallback

    @staticmethod
    def register_with_master(n_particle_system, n_parent_node):
        """Add a particle system to the list of its parent master particle system, if it has one."""
        if not isinstance(n_parent_node, NifClasses.BSMasterParticleSystem):
            return
        n_parent_node.particle_systems.append(n_particle_system)
        n_parent_node.num_particle_systems = len(n_parent_node.particle_systems)

    # Particle system data

    def export_data(self, b_obj, b_psys, nif_ps, restored, n_particle_system):
        """Export the data block of a particle system."""

        restored_data = restored["DATA"][0] if restored and restored["DATA"] else None
        block_type = type(restored_data).__name__ if restored_data else self.get_data_type(n_particle_system)
        block_type = self.get_supported_type(block_type, "NiPSysData", b_obj.name)

        if restored_data and type(restored_data).__name__ == block_type:
            n_data = restored_data
        else:
            n_data = block_store.create_block(block_type)
        n_particle_system.data = n_data

        b_settings = b_psys.settings

        # the flags decide which per particle arrays the data block holds, so they come first
        for field_name in (
                "has_vertices", "has_normals", "has_vertex_colors", "has_radii",
                "has_sizes", "has_rotations", "has_rotation_angles",
                "has_rotation_axes", "has_rotation_speeds", "has_texture_indices"):
            if hasattr(n_data, field_name):
                setattr(n_data, field_name, getattr(nif_ps, f"data_{field_name}"))
        self.set_rotation_flags(n_data, b_settings, nif_ps)

        n_fields = self.get_field_names(n_data)
        self.set_max_particles(n_data, n_fields, self.get_max_particles(b_settings, nif_ps))
        self.set_subtexture_offsets(n_data, n_fields, nif_ps)

        if isinstance(n_data, NifClasses.BSStripPSysData):
            n_data.max_point_count = nif_ps.bs_strip_max_point_count
            n_data.start_cap_size = nif_ps.bs_strip_start_cap_size
            n_data.end_cap_size = nif_ps.bs_strip_end_cap_size
            n_data.do_z_prepass = nif_ps.bs_strip_do_z_prepass
        elif isinstance(n_data, NifClasses.NiMeshPSysData):
            self.set_particle_mesh_reference(b_obj, b_settings, n_data)

        return n_data

    def set_particle_mesh_reference(self, b_obj, b_settings, n_data):
        """Restore the node containing the geometry instanced by mesh particles."""

        n_particle_meshes = self.resolve_blender_object(b_settings.instance_object)
        if not n_particle_meshes:
            n_particle_meshes = n_data.particle_meshes

        if n_particle_meshes and not isinstance(n_particle_meshes, NifClasses.NiNode):
            # NiMeshPSysData requires a node even when Blender instances one mesh.
            n_wrapper = block_store.create_block("NiNode")
            n_wrapper.name = f"{b_obj.name} Particle Meshes"
            if isinstance(n_particle_meshes, NifClasses.NiAVObject):
                n_wrapper.add_child(n_particle_meshes)
                n_particle_meshes = n_wrapper
            else:
                n_particle_meshes = None

        n_data.particle_meshes = n_particle_meshes
        if not n_particle_meshes:
            NifLog.warn(
                f"Mesh particle system {b_settings.name} has no instance object "
                f"that was exported as NIF geometry."
            )

    @staticmethod
    def get_data_type(n_particle_system):
        """The data block type a particle system block needs."""
        if isinstance(n_particle_system, NifClasses.BSStripParticleSystem):
            return "BSStripPSysData"
        if isinstance(n_particle_system, NifClasses.NiMeshParticleSystem):
            return "NiMeshPSysData"
        return "NiPSysData"

    @staticmethod
    def get_field_names(n_block):
        """The fields a block actually holds at the nif version being exported."""
        return {field_name for field_name, *_ in type(n_block)._get_filtered_attribute_list(n_block)}

    def get_max_particles(self, b_settings, nif_ps):
        """How many particles the system can keep alive at once."""
        if nif_ps.max_particles:
            return nif_ps.max_particles
        maximum_life_span = b_settings.lifetime / self.fps
        variation = particles.variation_from_lifetime_random(
            maximum_life_span, b_settings.lifetime_random)
        life_span = particles.base_lifetime_from_blender(
            maximum_life_span, b_settings.lifetime_random)
        return particles.auto_max_particles(
            particles.birth_rate_from_count(b_settings, self.fps),
            life_span, variation)

    @staticmethod
    def set_max_particles(n_data, n_fields, count):
        """Set the maximum particle count, in whichever field the nif version stores it."""
        for field_name in ("bs_max_vertices", "num_particles", "num_vertices"):
            if field_name in n_fields:
                setattr(n_data, field_name, count)
                break
        else:
            NifLog.warn(f"Could not find a particle count field on {type(n_data).__name__}.")
            return

        # the per particle arrays are sized by the count, so they have to follow it
        for field_name in ("vertices", "normals", "tangents", "bitangents", "vertex_colors", "uv_sets",
                           "radii", "sizes", "rotations", "rotation_angles", "rotation_axes",
                           "rotation_speeds", "particle_info"):
            if field_name in n_fields:
                n_data.reset_field(field_name)

    @staticmethod
    def set_rotation_flags(n_data, b_settings, nif_ps):
        """Set the flags telling the engine which per particle rotation data to keep."""
        if b_settings.get("niftools_billboard_preview"):
            return
        n_data.has_rotations = nif_ps.data_has_rotations or b_settings.use_rotations
        n_data.has_rotation_angles = nif_ps.data_has_rotation_angles or b_settings.use_rotations
        n_data.has_rotation_speeds = (nif_ps.data_has_rotation_speeds
                                      or (b_settings.use_rotations
                                          and b_settings.angular_velocity_factor != 0))
        n_data.has_rotation_axes = (nif_ps.data_has_rotation_axes
                                    or (b_settings.use_rotations and not nif_ps.random_rot_axis))

    @staticmethod
    def set_subtexture_offsets(n_data, n_fields, nif_ps):
        """Split the particle texture into the subtexture grid set on the particle settings."""
        if "num_subtexture_offsets" not in n_fields:
            if nif_ps.subtexture_columns * nif_ps.subtexture_rows > 1:
                NifLog.warn(f"{bpy.context.scene.niftools_scene.game} does not support particle subtextures.")
            return

        b_offsets = particles.subtexture_offsets(nif_ps.subtexture_columns, nif_ps.subtexture_rows)
        if len(b_offsets) < 2:
            # a single section is the whole texture, which is what an empty offset list means
            b_offsets = []

        n_data.has_texture_indices = bool(b_offsets)
        n_data.num_subtexture_offsets = len(b_offsets)
        n_data.reset_field("subtexture_offsets")
        for n_offset, b_offset in zip(n_data.subtexture_offsets, b_offsets):
            n_offset.x, n_offset.y, n_offset.z, n_offset.w = b_offset

    # Modifiers

    def export_modifiers(self, b_obj, b_psys, nif_ps, restored, n_particle_system, b_force_field_objects):
        """Export the modifier chain of a particle system. Returns its emitter modifier."""

        restored_modifiers = restored["MODIFIER"] if restored else None
        if restored_modifiers:
            n_modifiers = [(n_modifier, {}) for n_modifier in restored_modifiers]
        else:
            n_modifiers = self.build_modifiers(b_obj, b_psys, nif_ps, n_particle_system, b_force_field_objects)
        was_restored = bool(restored_modifiers)

        for n_modifier, _ in n_modifiers:
            n_modifier.target = n_particle_system
            add_modifier(n_particle_system, n_modifier)

        n_emitter = None
        for n_modifier, _ in n_modifiers:
            if isinstance(n_modifier, NifClasses.NiPSysEmitter):
                if n_emitter is None:
                    n_emitter = n_modifier
                    self.emitter_helper.apply(n_modifier, b_obj, b_psys, nif_ps)
            else:
                self.modifier_helper.apply(n_modifier, b_obj, b_psys, nif_ps)

        self.relink_modifiers(n_modifiers, b_obj, nif_ps, n_particle_system, n_emitter, was_restored)
        sort_modifiers(n_particle_system)

        if not n_emitter:
            NifLog.warn(f"Particle system {b_psys.name} of {b_obj.name} has no emitter modifier, "
                        f"it will not emit anything in game.")
        return n_emitter

    def build_modifiers(self, b_obj, b_psys, nif_ps, n_particle_system, b_force_field_objects):
        """Build a modifier chain from the Blender particle system alone."""
        emitter_type = self.get_supported_type(nif_ps.particle_emitter_type, "NiPSysSphereEmitter", b_obj.name)
        n_modifiers = [(self.modifier_helper.create(b_obj, emitter_type), {})]

        for block_type in self.modifier_helper.get_required_modifiers(b_psys, nif_ps, n_particle_system):
            block_type = self.get_supported_type(block_type, "", b_obj.name)
            if block_type:
                n_modifiers.append((self.modifier_helper.create(b_obj, block_type), {}))

        for b_field_obj in b_force_field_objects:
            n_field_modifier = self.modifier_helper.export_field_modifier(b_field_obj, b_psys, n_particle_system)
            if n_field_modifier:
                n_modifiers.append((n_field_modifier, {"field_object": b_field_obj.name}))

        return n_modifiers

    def relink_modifiers(self, n_modifiers, b_obj, nif_ps, n_particle_system, n_emitter,
                         was_restored=False):
        """Restore the pointers of the modifier chain, which cannot be stored as plain data."""

        n_by_name = {n_modifier.name: n_modifier for n_modifier, _ in n_modifiers}

        for n_modifier, refs in n_modifiers:
            for field_name in self.SCENE_REFS:
                if field_name in refs and hasattr(n_modifier, field_name):
                    n_target = self.resolve_object(refs[field_name])
                    if n_target:
                        setattr(n_modifier, field_name, n_target)
            for field_name in self.CHAIN_REFS:
                if field_name in refs and hasattr(n_modifier, field_name):
                    n_target = n_by_name.get(refs[field_name])
                    if n_target:
                        setattr(n_modifier, field_name, n_target)
            for field_name in self.MESH_LIST_REFS:
                if field_name in refs and hasattr(n_modifier, field_name):
                    self.set_mesh_list(n_modifier, field_name, [self.resolve_object(name)
                                                                for name in refs[field_name]])

        # Fill in the pointers that were not restored from stored references. An
        # emitter restored from an import keeps an empty emitter object, because
        # some shipped nifs deliberately leave one unset.
        if n_emitter and not was_restored and not getattr(n_emitter, "emitter_object", True):
            n_emitter.emitter_object = self.get_emitter_node(b_obj, nif_ps, n_particle_system)
        if isinstance(n_emitter, NifClasses.NiPSysMeshEmitter) and not n_emitter.emitter_meshes:
            n_emitter_mesh = self.resolve_blender_object(nif_ps.particle_emitter_object)
            if n_emitter_mesh:
                self.set_mesh_list(n_emitter, "emitter_meshes", [n_emitter_mesh])
            else:
                NifLog.warn(f"Mesh emitter of {b_obj.name} has no emitter object that was exported as geometry, "
                            f"it will not emit anything in game.")

        for n_modifier, _ in n_modifiers:
            if isinstance(n_modifier, NifClasses.NiPSysAgeDeathModifier) and not n_modifier.spawn_modifier:
                n_modifier.spawn_modifier = next((n_spawn for n_spawn, _ in n_modifiers
                                                  if isinstance(n_spawn, NifClasses.NiPSysSpawnModifier)), None)
            elif isinstance(n_modifier, NifClasses.NiPSysFieldModifier) and not n_modifier.field_object:
                n_modifier.field_object = n_particle_system

    def get_emitter_node(self, b_obj, nif_ps, n_particle_system):
        """The node a particle system emits from: the object set on the particle settings,
        its parent node, or the particle system itself."""
        n_emitter_node = self.resolve_blender_object(nif_ps.particle_emitter_object)
        if n_emitter_node:
            return n_emitter_node
        if b_obj.parent:
            n_emitter_node = DICT_NAMES.get(b_obj.parent.name)
            if n_emitter_node:
                return n_emitter_node
        return n_particle_system

    @staticmethod
    def set_mesh_list(n_modifier, field_name, n_blocks):
        """Fill one of the block reference arrays of a modifier."""
        n_blocks = [n_block for n_block in n_blocks if n_block]
        count_name = "num_meshes" if field_name == "meshes" else f"num_{field_name}"
        setattr(n_modifier, count_name, len(n_blocks))
        n_modifier.reset_field(field_name)
        n_array = getattr(n_modifier, field_name)
        for array_index, n_block in enumerate(n_blocks):
            n_array[array_index] = n_block

    @staticmethod
    def resolve_blender_object(b_obj):
        """The block a Blender object was exported as."""
        if not b_obj:
            return None
        n_block = block_store.obj_to_block.get(b_obj)
        if isinstance(n_block, NifClasses.NiAVObject):
            return n_block
        # Geometry export registers both its NiGeometry and its data block against
        # the same Blender object, leaving obj_to_block pointing at the data block.
        # Particle pointers require the scene object, never NiGeometryData.
        for n_candidate, b_candidate in block_store.block_to_obj.items():
            if b_candidate == b_obj and isinstance(n_candidate, NifClasses.NiAVObject):
                return n_candidate
        n_block = DICT_NAMES.get(b_obj.name)
        return n_block if isinstance(n_block, NifClasses.NiAVObject) else None

    @staticmethod
    def resolve_object(n_name):
        """Find a block by the name it had in the nif it was imported from."""
        if not n_name:
            return None
        for b_obj, n_block in block_store.obj_to_block.items():
            if isinstance(n_block, NifClasses.NiAVObject) and block_store.get_full_name(b_obj) == n_name:
                return n_block
        return DICT_NAMES.get(n_name)

    # Controllers

    def export_controllers(self, b_obj, b_psys, nif_ps, restored, n_particle_system, n_emitter):
        """Export the controllers that run a particle system, and set its birth rate."""

        restored_controllers = restored["CONTROLLER"] if restored else None
        if restored_controllers:
            for n_controller in restored_controllers:
                n_particle_system.add_controller(n_controller)
        else:
            n_particle_system.add_controller(self.create_emitter_controller(nif_ps))
            n_update_controller = block_store.create_block("NiPSysUpdateCtlr")
            n_update_controller.flags = nif_ps.update_controller_flags
            n_update_controller.frequency = nif_ps.update_controller_frequency
            n_update_controller.phase = nif_ps.update_controller_phase
            n_update_controller.start_time = nif_ps.update_start_time
            n_update_controller.stop_time = nif_ps.update_stop_time
            n_particle_system.add_controller(n_update_controller)

        self.apply_controllers(b_psys, nif_ps, n_particle_system, n_emitter)

    @staticmethod
    def create_emitter_controller(nif_ps):
        """Create the controller that births particles."""
        n_controller = block_store.create_block("NiPSysEmitterCtlr")
        n_controller.flags = nif_ps.emitter_controller_flags
        n_controller.frequency = nif_ps.emitter_controller_frequency
        n_controller.phase = nif_ps.emitter_controller_phase
        n_controller.start_time = nif_ps.emission_start_time
        n_controller.stop_time = nif_ps.emission_stop_time
        n_controller.interpolator = block_store.create_block("NiFloatInterpolator")
        n_controller.visibility_interpolator = block_store.create_block("NiBoolInterpolator")
        n_controller.visibility_interpolator.value = nif_ps.emitter_visibility_value
        return n_controller

    def apply_controllers(self, b_psys, nif_ps, n_particle_system, n_emitter):
        """Write live Blender emission timing/count onto the NIF controllers."""
        b_settings = b_psys.settings
        preview_unchanged = (
            "niftools_preview_frame_start" in b_settings
            and abs(b_settings.frame_start
                    - b_settings["niftools_preview_frame_start"]) < 1e-4
            and abs(b_settings.frame_end
                    - b_settings["niftools_preview_frame_end"]) < 1e-4
            and int(b_settings.count)
                    == int(b_settings.get("niftools_preview_count", -1))
        )
        for n_controller in n_particle_system.get_controllers():
            if isinstance(n_controller, NifClasses.NiPSysEmitterCtlr):
                n_controller.flags = nif_ps.emitter_controller_flags
                n_controller.frequency = nif_ps.emitter_controller_frequency
                n_controller.phase = nif_ps.emitter_controller_phase
                if preview_unchanged:
                    n_controller.start_time = nif_ps.emission_start_time
                    n_controller.stop_time = nif_ps.emission_stop_time
                else:
                    n_controller.start_time = b_settings.frame_start / self.fps
                    n_controller.stop_time = b_settings.frame_end / self.fps
                if n_emitter:
                    n_controller.modifier_name = n_emitter.name
                n_interpolator = n_controller.interpolator
                if isinstance(n_interpolator, NifClasses.NiFloatInterpolator) and not n_interpolator.data:
                    n_interpolator.value = (
                        nif_ps.birth_rate if preview_unchanged
                        else particles.birth_rate_from_count(b_settings, self.fps)
                    )
                n_visibility = getattr(n_controller, "visibility_interpolator", None)
                if isinstance(n_visibility, NifClasses.NiBoolInterpolator) and not n_visibility.data:
                    n_visibility.value = nif_ps.emitter_visibility_value
            elif isinstance(n_controller, NifClasses.NiPSysUpdateCtlr):
                n_controller.flags = nif_ps.update_controller_flags
                n_controller.frequency = nif_ps.update_controller_frequency
                n_controller.phase = nif_ps.update_controller_phase
                n_controller.start_time = nif_ps.update_start_time
                n_controller.stop_time = nif_ps.update_stop_time
