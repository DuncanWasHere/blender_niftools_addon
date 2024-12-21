"""This script contains classes to help import animations."""

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
from abc import ABC

import bpy
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, NifData
from nifgen.formats.nif import classes as NifClasses


class NiControllerManager:

    def __init__(self):
        from io_scene_niftools.modules.nif_export.animation.material import MaterialAnimation
        from io_scene_niftools.modules.nif_export.animation.morph import MorphAnimation
        from io_scene_niftools.modules.nif_export.animation.shader import ShaderAnimation
        from io_scene_niftools.modules.nif_export.animation.texture import TextureAnimation
        from io_scene_niftools.modules.nif_export.animation.object import ObjectAnimation
        from io_scene_niftools.modules.nif_export.animation.transform import TransformAnimation

        self.fps = bpy.context.scene.render.fps
        self.transform_animation_helper = TransformAnimation()
        self.material_animation_helper = MaterialAnimation()
        self.texture_animation_helper = TextureAnimation()
        self.shader_animation_helper = ShaderAnimation()
        self.object_animation_helper = ObjectAnimation()
        self.morph_animation_helper = MorphAnimation()
        # self.particle_animation_helper =

    def export_nif_animations(self, n_root_node):

        NifLog.info(f"Exporting animations")

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


        # Collect NLA tracks by name
        # All NLA tracks with the same name = one NiControllerSequence
        # Sequence name = dict key
        b_sequences = {}

        if not bpy.data.actions:
            return # No animation data in the scene

        for b_obj in bpy.data.objects:
            if not b_obj.animation_data or not b_obj.animation_data.nla_tracks:
                continue

            for b_nla_track in b_obj.animation_data.nla_tracks:
                if b_nla_track.name not in b_sequences:
                    b_sequences[b_nla_track.name] = set()

                # TODO: Support multiple strips per track?
                b_sequence_data = (b_nla_track.strips[0], b_obj)
                b_sequences[b_nla_track.name].add(b_sequence_data)

        # Export the NiControllerManager
        self.export_ni_controller_manager(n_root_node, b_sequences)

    def export_ni_controller_manager(self, n_root_node, b_sequences):
        # Create a NiControllerManager and parent it to the root node
        n_ni_controller_manager = block_store.create_block("NiControllerManager")
        n_ni_controller_manager.target = n_root_node
        n_root_node.controller = n_ni_controller_manager

        n_ni_multi_target_transform_controller = None

        for n_sequence_name, b_sequence_data in b_sequences.items():
            # Create a NiControllerSequence for each Blender quasi sequence
            n_ni_controller_sequence = self.export_ni_controller_sequence(n_sequence_name, b_sequence_data, n_root_node.name)
            n_ni_controller_manager.add_controller_sequence(n_ni_controller_sequence)
            n_ni_controller_sequence.manager = n_ni_controller_manager

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

    def export_ni_controller_sequence(self, n_sequence_name, b_sequence_data, n_accum_root_name):
        # Create a NiControllerSequence and set its properties
        n_ni_controller_sequence = block_store.create_block("NiControllerSequence")
        n_ni_controller_sequence.accum_root_name = n_accum_root_name
        n_ni_controller_sequence.name = n_sequence_name
        n_ni_controller_sequence.array_grow_by = 1

        for b_sequence in b_sequence_data:
            b_nla_strip = b_sequence[0]

            n_ni_controller_sequence.start_time = b_nla_strip.frame_start / bpy.context.scene.render.fps
            n_ni_controller_sequence.stop_time = b_nla_strip.frame_end / bpy.context.scene.render.fps
            n_ni_controller_sequence.weight = b_nla_strip.influence
            n_ni_controller_sequence.frequency = b_nla_strip.scale

            if b_nla_strip.use_reverse:
                n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_REVERSE']
            elif b_nla_strip.use_animated_time_cyclic:
                n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_REVERSE']
            else:
                n_ni_controller_sequence.cycle_type = NifClasses.CycleType['CYCLE_CLAMP']

            # Export controlled blocks for all objects with strips on these tracks
            self.export_controlled_blocks(b_sequence[1],
                                          b_sequence[1].animation_data.action,
                                          n_ni_controller_sequence)

        self.export_text_keys()

        return n_ni_controller_sequence

    def export_controlled_blocks(self, b_obj, b_action, n_ni_controller_sequence):
        # Add a controlled block for each controller type in the action's keying set
        self.transform_animation_helper.export_transforms(n_ni_controller_sequence, b_obj, b_action)

    def export_text_keys(self):
        return

class Animation(ABC):

    def __init__(self):
        self.fps = bpy.context.scene.render.fps

    def set_flags_and_timing(self, kfc, exp_fcurves, start_frame=None, stop_frame=None):
        # fill in the non-trivial values
        kfc.flags._value = 8  # active
        kfc.flags |= self.get_flags_from_fcurves(exp_fcurves)
        if bpy.context.scene.niftools_scene.game == 'SID_MEIER_S_PIRATES':
            # Sid Meier's Pirates! want the manager_controlled flag set
            kfc.flags.manager_controlled = True
        kfc.frequency = 1.0
        kfc.phase = 0.0
        if not start_frame and not stop_frame:
            start_frame, stop_frame = exp_fcurves[0].range()
        # todo [anim] this is a hack, move to scene
        kfc.start_time = start_frame / self.fps
        kfc.stop_time = stop_frame / self.fps

    @staticmethod
    def get_flags_from_fcurves(fcurves):
        # see if there are cyclic extrapolation modifiers on exp_fcurves
        cyclic = False
        for fcu in fcurves:
            # sometimes fcurves can include empty fcurves - see uv controller export
            if fcu:
                for mod in fcu.modifiers:
                    if mod.type == "CYCLES":
                        cyclic = True
                        break
        if cyclic:
            return 0
        else:
            return 4  # 0b100

    @staticmethod
    def get_active_action(b_obj):
        # check if the blender object has a non-empty action assigned to it
        if b_obj:
            if b_obj.animation_data and b_obj.animation_data.action:
                b_action = b_obj.animation_data.action
                if b_action.fcurves:
                    return b_action

    @staticmethod
    def get_controllers(nodes):
        """find all nodes and relevant controllers"""
        node_kfctrls = {}
        for node in nodes:
            if not isinstance(node, NifClasses.NiAVObject):
                continue
            # get list of all controllers for this node
            ctrls = node.get_controllers()
            for ctrl in ctrls:
                if bpy.context.scene.niftools_scene.game == 'MORROWIND':
                    # morrowind: only keyframe controllers
                    if not isinstance(ctrl, NifClasses.NiKeyframeController):
                        continue
                if node not in node_kfctrls:
                    node_kfctrls[node] = []
                node_kfctrls[node].append(ctrl)
        return node_kfctrls

    def create_controller(self, parent_block, target_name, priority=0):
        # todo[anim] - make independent of global NifData.data.version, and move check for NifOp.props.animation outside
        n_kfi = None
        n_kfc = None

        try:
            if NifOp.props.animation == 'GEOM_NIF' and NifData.data.version < 0x0A020000:
                # keyframe controllers are not present in geometry only files
                # for more recent versions, the controller and interpolators are
                # present, only the data is not present (see further on)
                return n_kfc, n_kfi
        except AttributeError:
            # kf export has no animation mode
            pass

        # add a KeyframeController block, and refer to this block in the
        # parent's time controller
        if NifData.data.version < 0x0A020000:
            n_kfc = block_store.create_block("NiKeyframeController", None)
        else:
            n_kfc = block_store.create_block("NiTransformController", None)
            n_kfi = block_store.create_block("NiTransformInterpolator", None)
            # link interpolator from the controller
            n_kfc.interpolator = n_kfi
        # if parent is a node, attach controller to that node
        if isinstance(parent_block, NifClasses.NiNode):
            parent_block.add_controller(n_kfc)
            if n_kfi:
                # set interpolator default data
                n_kfi.scale, n_kfi.rotation, n_kfi.translation = parent_block.get_transform().get_scale_quat_translation()

        # else ControllerSequence, so create a link
        elif isinstance(parent_block, NifClasses.NiControllerSequence):
            controlled_block = parent_block.add_controlled_block()
            controlled_block.priority = priority
            # todo - pyffi adds the names to the NiStringPalette, but it creates one per controller link...
            # also the currently used pyffi version doesn't store target_name for ZT2 style KFs in
            # controlled_block.set_node_name(target_name)
            # the following code handles both issues and should probably be ported to pyffi
            if NifData.data.version < 0x0A020000:
                # older versions need the actual controller blocks
                controlled_block.target_name = target_name
                controlled_block.controller = n_kfc
                # erase reference to target node
                n_kfc.target = None
            else:
                # newer versions need the interpolator blocks
                controlled_block.interpolator = n_kfi
                controlled_block.node_name = target_name
                controlled_block.controller_type = "NiTransformController"
                # get the parent's string palette
                if not parent_block.string_palette:
                    parent_block.string_palette = NifClasses.NiStringPalette(NifData.data)
                # assign string palette to controller
                controlled_block.string_palette = parent_block.string_palette
                # add the strings and store their offsets
                palette = controlled_block.string_palette.palette
                controlled_block.node_name_offset = palette.add_string(controlled_block.node_name)
                controlled_block.controller_type_offset = palette.add_string(controlled_block.controller_type)
        # morrowind style
        elif isinstance(parent_block, NifClasses.NiSequenceStreamHelper):
            # create node reference by name
            nodename_extra = block_store.create_block("NiStringExtraData")
            nodename_extra.bytes_remaining = len(target_name) + 4
            nodename_extra.string_data = target_name
            # the controllers and extra datas form a chain down from the kf root
            parent_block.add_extra_data(nodename_extra)
            parent_block.add_controller(n_kfc)
        else:
            raise NifError("Unsupported KeyframeController parent!")
        
        return n_kfc, n_kfi

    # todo [anim] currently not used, maybe reimplement this
    @staticmethod
    def get_n_interp_from_b_interp(b_ipol):
        if b_ipol == "LINEAR":
            return NifClasses.KeyType.LINEAR_KEY
        elif b_ipol == "BEZIER":
            return NifClasses.KeyType.QUADRATIC_KEY
        elif b_ipol == "CONSTANT":
            return NifClasses.KeyType.CONST_KEY

        NifLog.warn(f"Unsupported interpolation mode ({b_ipol}) in blend, using quadratic/bezier.")
        return NifClasses.KeyType.QUADRATIC_KEY
    
    def add_dummy_markers(self, b_action):
        # if we exported animations, but no animation groups are defined,
        # define a default animation group
        NifLog.info("Checking action pose markers.")
        if not b_action.pose_markers:
            NifLog.info("Defining default action pose markers.")
            for frame, text in zip(b_action.frame_range, ("Idle: Start/Idle: Loop Start", "Idle: Loop Stop/Idle: Stop")):
                marker = b_action.pose_markers.new(text)
                marker.frame = int(frame)
