"""Classes for exporting NIF animation blocks."""

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

from ....modules.nif_export.animation.geometry import GeometryAnimation
from ....modules.nif_export.animation.material import MaterialAnimation
from ....modules.nif_export.animation.object import ObjectAnimation
from ....modules.nif_export.animation.particle import ParticleAnimation
from ....modules.nif_export.animation.shader import ShaderAnimation
from ....modules.nif_export.animation.texture import TextureAnimation

from ....modules.nif_export.animation.common import (AnimationExportMode, animation_data_of,
                                                     create_text_keys, export_text_keys)

from ....modules.nif_export.block_registry import block_store
from ....utils.logging import NifLog, NifError
from nifgen.formats.nif import classes as NifClasses

# Sequence roots that hold their controlled blocks as a flat list, by game
SEQUENCE_STREAM_HELPER_GAMES = ('MORROWIND', 'FREEDOM_FORCE')
CONTROLLER_SEQUENCE_GAMES = ('CIVILIZATION_IV', 'ZOO_TYCOON_2', 'FREEDOM_FORCE_VS_THE_3RD_REICH',
                             'SHIN_MEGAMI_TENSEI_IMAGINE', 'SID_MEIER_S_PIRATES')

# The bones a sequence accumulates root motion on, most specific first
ACCUM_ROOT_BONES = ("NPC Root [Root]", "Bip01", "Bip02")


class ActionStrip:
    """
    Stands in for an NLA strip, for actions that were never pushed into the NLA.

    An action carries the same sequence settings on its nifanimation property group, so
    the sequence exporter can treat both the same way.
    """

    def __init__(self, b_action, b_action_slot=None):
        b_settings = b_action.nifanimation

        self.action = b_action
        self.action_slot = b_action_slot
        self.name = b_action.name
        self.influence = b_settings.weight
        self.scale = b_settings.frequency
        self.frame_start, self.frame_end = b_action.frame_range
        self.use_reverse = b_settings.cycle_type == 'CYCLE_REVERSE'
        self.use_animated_time_cyclic = b_settings.cycle_type == 'CYCLE_LOOP'


def get_sequence_name(b_action, b_obj):
    """
    Work out which sequence an action belongs to.

    Imported sequences keep their identity on the shared slotted action. Actions built by
    hand may carry no metadata, so retain the older '<sequence>_<object>' fallback and then
    use the plain action name.
    """

    n_sequence_name = b_action.nifanimation.sequence_name
    if n_sequence_name:
        return n_sequence_name

    b_suffix = f"_{b_obj.name}"
    if b_action.name.endswith(b_suffix) and len(b_action.name) > len(b_suffix):
        return b_action.name[:-len(b_suffix)]

    return b_action.name


def sort_animation_data(b_objects):
    """
    Group the animation in the scene into sequences.

    Each sequence is a list of (strip, Blender object) pairs, one per animated action slot;
    every pair becomes a set of controlled blocks. NLA tracks group hand-built actions by
    track name, while imported shared actions retain their sequence metadata.
    """

    b_sequences = {}

    for b_obj in b_objects:
        # material animation lives on the node tree of each material rather than on the
        # object, so it has to be collected too or it is simply never seen
        for b_anim_data in animation_data_of(b_obj):
            collect_animation_data(b_sequences, b_anim_data, b_obj)

    return b_sequences


def collect_animation_data(b_sequences, b_anim_data, b_obj):
    """Sort one animation data block's strips and action into the sequences."""

    b_stripped_actions = set()
    nla_entries = []

    for b_nla_track in b_anim_data.nla_tracks:
        if not b_nla_track.strips:
            continue
        if len(b_nla_track.strips) > 1:
            NifLog.warn(f"NLA track '{b_nla_track.name}' of {b_obj.name} has more than one strip. "
                        f"Only the first one is exported; split the rest into their own tracks "
                        f"to export them as separate sequences.")

        b_nla_strip = b_nla_track.strips[0]
        if not b_nla_strip.action:
            continue

        # Imported tracks can acquire Blender's numeric suffix when the target already
        # had a track of that name. The action metadata remains the authoritative sequence
        # identity. Hand-built actions without it continue to group by track name.
        n_sequence_name = (b_nla_strip.action.nifanimation.sequence_name
                           or b_nla_track.name)
        nla_entries.append((n_sequence_name, b_nla_strip))
        b_stripped_actions.add(b_nla_strip.action)

    # Insert the active action before stashed sequences. Dict insertion order controls
    # controller sequence order on export, so this preserves the default sequence across
    # an import/export round trip.
    b_action = b_anim_data.action
    if b_action and not b_action.is_empty and b_action not in b_stripped_actions:
        n_sequence_name = get_sequence_name(b_action, b_obj)
        b_sequences.setdefault(n_sequence_name, []).append(
            (ActionStrip(b_action, b_anim_data.action_slot), b_obj))

    for n_sequence_name, b_nla_strip in nla_entries:
        b_sequences.setdefault(n_sequence_name, []).append((b_nla_strip, b_obj))

    return b_sequences


def get_accum_root_name(b_objects, default_name):
    """Find the node a sequence should accumulate root motion on."""

    for b_obj in b_objects:
        if b_obj.type != 'ARMATURE':
            continue
        for b_bone_name in ACCUM_ROOT_BONES:
            if b_bone_name in b_obj.data.bones:
                return block_store.get_bone_name_for_nif(b_bone_name)

    return default_name


class Animation:
    """Main interface class for exporting NIF animation blocks."""

    def __init__(self):

        self.geometry_animation_helper = GeometryAnimation()
        self.material_animation_helper = MaterialAnimation()
        self.object_animation_helper = ObjectAnimation()
        self.particle_animation_helper = ParticleAnimation()
        self.shader_animation_helper = ShaderAnimation()
        self.texture_animation_helper = TextureAnimation()

        self.fps = bpy.context.scene.render.fps
        self.niftools_scene = bpy.context.scene.niftools_scene
        self.target_game = self.niftools_scene.game

    def export_animations(self, b_objects, n_root_node):
        """
        Export the scene's animation into a NIF.

        Every sequence hangs off a single NiControllerManager on the root node, and the
        controllers themselves stay on the blocks they animate.
        """
        # TODO: Operator setting to toggle NiControllerManager export for NIFs

        NifLog.info(f"Exporting animations...")

        AnimationExportMode.init(kf=False)

        # Group NLA strips, by track name, into lists of controller sequences
        # NLA track name = Dict key = Sequence name
        # NLA strip list = Dict value = Controlled blocks
        # (NLA strip, Blender object) = List item = One controlled block for each keying set
        b_sequences = sort_animation_data(b_objects)

        if not b_sequences:
            return  # No animation data in the scene

        # Export the NiControllerManager
        self.export_ni_controller_manager(n_root_node, b_sequences, b_objects)

    def export_kf_roots(self, b_objects, default_accum_root_name="Scene Root"):
        """
        Export the scene's animation as the root blocks of a KF file.

        None of the animated blocks exist in a KF, so there is no controller manager and
        each sequence is a file root that addresses its targets by name.
        """

        NifLog.info(f"Exporting animations...")

        AnimationExportMode.init(kf=True)

        b_sequences = sort_animation_data(b_objects)

        if not b_sequences:
            raise NifError("No animation to export!\n"
                           "Assign an action to an object, or push one down into an NLA track.")

        accum_root_name = get_accum_root_name(b_objects, default_accum_root_name)

        return [self.export_kf_root(n_sequence_name, b_controlled_blocks, accum_root_name)
                for n_sequence_name, b_controlled_blocks in b_sequences.items()]

    def export_kf_root(self, n_sequence_name, b_controlled_blocks, accum_root_name):
        """Export one sequence as a KF root block of the type the target game expects."""

        game = self.target_game

        if game in SEQUENCE_STREAM_HELPER_GAMES:
            return self.export_ni_sequence_stream_helper(n_sequence_name, b_controlled_blocks,
                                                         accum_root_name)

        if self.niftools_scene.is_bs() or game in CONTROLLER_SEQUENCE_GAMES:
            return self.export_ni_controller_sequence(n_sequence_name, b_controlled_blocks,
                                                      accum_root_name)

        raise NifError(f"Keyframe export for '{game}' is not supported.")

    def export_ni_controller_manager(self, n_root_node, b_sequences, b_objects):
        # Create a NiControllerManager and parent it to the root node
        n_ni_controller_manager = block_store.create_block("NiControllerManager")
        n_ni_controller_manager.target = n_root_node
        n_root_node.controller = n_ni_controller_manager

        n_ni_default_av_object_palette = block_store.create_block("NiDefaultAVObjectPalette")
        n_ni_controller_manager.object_palette = n_ni_default_av_object_palette
        n_ni_default_av_object_palette.scene = n_root_node

        accum_root_name = get_accum_root_name(b_objects, n_root_node.name)

        n_ni_av_controlled_blocks = []

        for n_sequence_name, b_controlled_blocks in b_sequences.items():
            # Create a NiControllerSequence for each Blender quasi sequence
            n_ni_controller_sequence = self.export_ni_controller_sequence(n_sequence_name, b_controlled_blocks, accum_root_name, n_ni_controller_manager)

            for n_controlled_block in n_ni_controller_sequence.controlled_blocks:
                n_obj = next((block for block in block_store.block_to_obj
                              if isinstance(block, NifClasses.NiAVObject)
                              and block.name == n_controlled_block.node_name), None)

                if n_obj is not None and n_obj not in n_ni_av_controlled_blocks:
                    n_ni_av_controlled_blocks.append(n_obj)

        n_ni_default_av_object_palette.num_objs = len(n_ni_av_controlled_blocks)
        n_ni_default_av_object_palette.reset_field("objs")

        for n_palette_obj, n_obj in zip(n_ni_default_av_object_palette.objs, n_ni_av_controlled_blocks):
            n_palette_obj.av_object = n_obj
            n_palette_obj.name = n_obj.name

    def export_ni_sequence_stream_helper(self, n_sequence_name, b_controlled_blocks, accum_root_name):
        """
        Export a sequence as a NiSequenceStreamHelper block, for games predating
        NiControllerSequence. Its controllers form a flat chain down from the root,
        paired with the NiStringExtraData blocks that name their targets.
        """

        n_ni_sequence_stream_helper = block_store.create_block("NiSequenceStreamHelper")
        n_ni_sequence_stream_helper.name = n_sequence_name

        n_text_extra = create_text_keys(n_ni_sequence_stream_helper)

        self.export_controlled_blocks(n_ni_sequence_stream_helper, b_controlled_blocks)

        export_text_keys(self.fps, b_controlled_blocks[0][0].action, n_text_extra)

        return n_ni_sequence_stream_helper

    def export_ni_controller_sequence(self, n_sequence_name, b_controlled_blocks, accum_root_name,
                                      n_ni_controller_manager=None):
        """
        Export a NiControllerSequence block.
        Controlled blocks must be a set of ordered pairs: (NLA strip, Blender object).
        If a controller manager is given, the sequence will be parented to it (for NIFs).
        """

        # Create a NiControllerSequence block and set its trivial properties
        n_ni_controller_sequence = block_store.create_block("NiControllerSequence")
        n_ni_controller_sequence.accum_root_name = accum_root_name
        n_ni_controller_sequence.name = n_sequence_name
        n_ni_controller_sequence.array_grow_by = 1

        # Set the non-trivial properties using the first strip as a template
        b_template_nla_strip = b_controlled_blocks[0][0]
        n_ni_controller_sequence.weight = b_template_nla_strip.influence
        n_ni_controller_sequence.frequency = b_template_nla_strip.scale

        if b_template_nla_strip.use_reverse:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType.CYCLE_REVERSE
        elif b_template_nla_strip.use_animated_time_cyclic:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType.CYCLE_LOOP
        else:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType.CYCLE_CLAMP

        b_start_frames = [block[0].frame_start for block in b_controlled_blocks]
        b_end_frames = [block[0].frame_end for block in b_controlled_blocks]

        n_ni_controller_sequence.start_time = min(b_start_frames) / self.fps
        n_ni_controller_sequence.stop_time = max(b_end_frames) / self.fps

        # Parent it to a NiControllerManager block if given
        if n_ni_controller_manager:
            n_ni_controller_manager.add_controller_sequence(n_ni_controller_sequence)
            n_ni_controller_sequence.manager = n_ni_controller_manager

        # Export the controlled blocks and text keys
        self.export_controlled_blocks(n_ni_controller_sequence, b_controlled_blocks)

        n_text_extra = create_text_keys(n_ni_controller_sequence)
        export_text_keys(self.fps, b_template_nla_strip.action, n_text_extra)

        return n_ni_controller_sequence

    def export_controlled_blocks(self, n_ni_controller_sequence, b_controlled_blocks):
        # Export a controlled block for each controller type in the action's keying set
        # self.geometry_animation_helper.export_geometry_animations(n_ni_controller_sequence, b_controlled_blocks)
        self.material_animation_helper.export_material_animations(b_controlled_blocks, n_ni_controller_sequence)
        self.object_animation_helper.export_object_animations(b_controlled_blocks, n_ni_controller_sequence)
        self.particle_animation_helper.export_particle_animations(b_controlled_blocks, n_ni_controller_sequence)
        self.shader_animation_helper.export_shader_animations(b_controlled_blocks, n_ni_controller_sequence)
        self.texture_animation_helper.export_texture_animations(b_controlled_blocks, n_ni_controller_sequence)

    # TODO [anim] Morrowind needs a trivial keyframe controller on the scene root when
    #  nothing else is animated, or the TESCS crashes, and NiBSAnimationNode conversion
    #  for the bs_animation_node operator setting.
