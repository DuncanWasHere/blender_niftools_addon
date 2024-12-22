"""Classes for exporting NIF animation blocks."""

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


import bpy
from io_scene_niftools.modules.nif_export.animation.geometry import GeometryAnimation
from io_scene_niftools.modules.nif_export.animation.material import MaterialAnimation
from io_scene_niftools.modules.nif_export.animation.object import ObjectAnimation
from io_scene_niftools.modules.nif_export.animation.particle import ParticleAnimation
from io_scene_niftools.modules.nif_export.animation.shader import ShaderAnimation
from io_scene_niftools.modules.nif_export.animation.texture import TextureAnimation
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


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
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_animations(self, b_objects, n_root_node):
        # TODO: Operator setting to toggle NiControllerManager export for NIFs

        NifLog.info(f"Exporting animations...")

        if not bpy.data.actions:
            return # No animation data in the scene

        # Group NLA strips, by track name, into lists of controller sequences
        # NLA track name = Dict key = Sequence name
        # NLA strip list = Dict value = Controlled blocks
        # (NLA strip, Blender object) = List item = One controlled block for each keying set

        # TODO: Support multiple strips per track?

        b_sequences = {}

        for b_obj in b_objects:

            if b_obj.animation_data:
                for b_nla_track in b_obj.animation_data.nla_tracks:
                    if b_nla_track.name not in b_sequences:
                        b_sequences[b_nla_track.name] = []

                    b_sequence_data = (b_nla_track.strips[0], b_obj)
                    b_sequences[b_nla_track.name].append(b_sequence_data)

            if b_obj.type == 'MESH':

                if b_obj.data.animation_data:
                    for b_nla_track in b_obj.data.animation_data.nla_tracks:
                        if b_nla_track.name not in b_sequences:
                            b_sequences[b_nla_track.name] = []

                        b_sequence_data = (b_nla_track.strips[0], b_obj)
                        b_sequences[b_nla_track.name].append(b_sequence_data)

                if b_obj.active_material and b_obj.active_material.node_tree:
                    if b_obj.active_material.node_tree.animation_data:
                        for b_nla_track in b_obj.active_material.node_tree.animation_data.nla_tracks:
                            if b_nla_track.name not in b_sequences:
                                b_sequences[b_nla_track.name] = []

                            b_sequence_data = (b_nla_track.strips[0], b_obj)
                            b_sequences[b_nla_track.name].append(b_sequence_data)

                if b_obj.particle_systems:
                    if b_obj.particle_systems[0].animation_data:
                        for b_nla_track in b_obj.particle_systems[0].animation_data.nla_tracks:
                            if b_nla_track.name not in b_sequences:
                                b_sequences[b_nla_track.name] = []

                            b_sequence_data = (b_nla_track.strips[0], b_obj)
                            b_sequences[b_nla_track.name].append(b_sequence_data)

        # Export the NiControllerManager
        self.export_ni_controller_manager(n_root_node, b_sequences)

    def export_ni_controller_manager(self, n_root_node, b_sequences):
        # Create a NiControllerManager and parent it to the root node
        n_ni_controller_manager = block_store.create_block("NiControllerManager")
        n_ni_controller_manager.target = n_root_node
        n_root_node.controller = n_ni_controller_manager

        # TODO: Move to object animation class
        n_ni_multi_target_transform_controller = None

        for n_sequence_name, b_controlled_blocks in b_sequences.items():
            # Create a NiControllerSequence for each Blender quasi sequence
            n_ni_controller_sequence = self.export_ni_controller_sequence(n_sequence_name, b_controlled_blocks,
                                                                          n_root_node.name, n_ni_controller_manager)
            # TODO: Move to object animation class
            for n_controlled_block in n_ni_controller_sequence.controlled_blocks:
                if n_controlled_block.controller_type == 'NiTransformController':
                    if not n_ni_multi_target_transform_controller:
                        n_ni_multi_target_transform_controller = block_store.create_block(
                            "NiMultiTargetTransformController")
                        n_ni_controller_manager.next_controller = n_ni_multi_target_transform_controller
                    n_controlled_block.controller = n_ni_multi_target_transform_controller

        n_ni_default_av_object_palette = block_store.create_block("NiDefaultAVObjectPalette")
        n_ni_controller_manager.object_palette = n_ni_default_av_object_palette
        n_ni_default_av_object_palette.scene = n_root_node

    def export_ni_controller_sequence(self, n_sequence_name, b_controlled_blocks, n_accum_root_name,
                                      n_ni_controller_manager = None):
        """
        Export a NiControllerSequence block.
        Controlled blocks must be a set of ordered pairs: (NLA strip, Blender object).
        If a controller manager is given, the sequence will be parented to it (for NIFs).
        """

        # Create a NiControllerSequence block and set its trivial properties
        n_ni_controller_sequence = block_store.create_block("NiControllerSequence")
        n_ni_controller_sequence.accum_root_name = n_accum_root_name
        n_ni_controller_sequence.name = n_sequence_name
        n_ni_controller_sequence.array_grow_by = 1

        # Parent it to a NiControllerManager block if given
        if n_ni_controller_manager:
            n_ni_controller_manager.add_controller_sequence(n_ni_controller_sequence)
            n_ni_controller_sequence.manager = n_ni_controller_manager

        # Set the non-trivial properties using the first strip as a template
        b_template_nla_strip = b_controlled_blocks[0][0]
        n_ni_controller_sequence.weight = b_template_nla_strip.influence
        n_ni_controller_sequence.frequency = b_template_nla_strip.scale

        if b_template_nla_strip.use_reverse:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_REVERSE']
        elif b_template_nla_strip.use_animated_time_cyclic:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_REVERSE']
        else:
            n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_CLAMP']

        n_ni_controller_sequence.start_time = min(b_controlled_blocks,
                                                  key=lambda b_controlled_block: b_controlled_block[0].frame_start)
        n_ni_controller_sequence.stop_time = max(b_controlled_blocks,
                                                 key=lambda b_controlled_block: b_controlled_block[0].frame_end)

        # Export the controlled blocks and text keys
        self.export_controlled_blocks(n_ni_controller_sequence, b_controlled_blocks)
        self.export_text_keys(n_ni_controller_sequence, b_controlled_blocks)

        return n_ni_controller_sequence

    def export_controlled_blocks(self, n_ni_controller_sequence, b_controlled_blocks):
        # Export a controlled block for each controller type in the action's keying set
        # self.geometry_animation_helper.export_geometry_animations(n_ni_controller_sequence, b_controlled_blocks)
        # self.material_animation_helper.export_material_animations(n_ni_controller_sequence, b_controlled_blocks)
        self.object_animation_helper.export_object_animations(n_ni_controller_sequence, b_controlled_blocks)
        self.particle_animation_helper.export_particle_animations(n_ni_controller_sequence, b_controlled_blocks)
        # self.shader_animation_helper.export_shader_animations(n_ni_controller_sequence, b_controlled_blocks)
        self.texture_animation_helper.export_texture_animations(b_controlled_blocks, n_ni_controller_sequence)

    def export_text_keys(self, n_ni_controller_sequence, b_controlled_blocks):
        return

'''
        if bpy.context.scene.niftools_scene.game == 'MORROWIND':
            # animations without keyframe animations crash the TESCS
            # if we are in that situation, add a trivial keyframe animation
            has_keyframecontrollers = False
            for block in block_store.block_to_obj:
                if isinstance(block, NifClasses.NiKeyframeController):
                    has_keyframecontrollers = True
                    break
            if (not has_keyframecontrollers) and (not NifOp.props.bs_animation_node):
                NifLog.info("Defining dummy keyframe controller")
                # add a trivial keyframe controller on the scene root
                self.transform_anim_helper.create_controller(n_root_node, n_root_node.name)

            if NifOp.props.bs_animation_node:
                for block in block_store.block_to_obj:
                    if isinstance(block, NifClasses.NiNode):
                        # if any of the shape children has a controller or if the ninode has a controller convert its type
                        if block.controller or any(child.controller for child in block.children if
                                                   isinstance(child, NifClasses.NiGeometry)):
                            new_block = NifClasses.NiBSAnimationNode(NifData.n_data).deepcopy(block)
                            # have to change flags to 42 to make it work
                            new_block.flags = 42
                            n_root_node.replace_global_node(block, new_block)
                            if n_root_node is block:
                                n_root_node = new_block

'''