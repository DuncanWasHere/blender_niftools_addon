"""Common functions shared between animation export classes."""

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


from abc import ABC

import bpy

from ....utils import consts

from ....modules.nif_export.block_registry import block_store
from ....utils.logging import NifLog, NifError
from ....utils.singleton import NifOp, NifData
from nifgen.formats.nif import classes as NifClasses

# First version with interpolators, and thus with controlled blocks that can stand
# on their own in a KF without the controller they were split off from
V_INTERPOLATORS = 0x0A01006A
# Version range in which controlled block strings are kept in a NiStringPalette
V_STRING_PALETTE = (0x0A020000, 0x14010000)
# Last version whose controlled blocks still carry a controller reference
V_CONTROLLED_BLOCK_CONTROLLER = 0x14030000

# The blend interpolator a manager controlled controller reads through, per interpolator type
BLEND_INTERPOLATORS = {
    "NiTransformInterpolator": "NiBlendTransformInterpolator",
    "NiBoolInterpolator": "NiBlendBoolInterpolator",
    "NiFloatInterpolator": "NiBlendFloatInterpolator",
    "NiPoint3Interpolator": "NiBlendPoint3Interpolator",
    "NiPathInterpolator": "NiBlendPoint3Interpolator",
}


class AnimationExportMode:
    """
    Which kind of file the animation blocks are currently being written into.

    A NIF keeps every controller on the block it animates and hangs its sequences off a
    single NiControllerManager. A KF contains none of those blocks, so its sequences are
    file roots that address their targets by name and reference only the interpolators.
    """

    kf = False

    @staticmethod
    def init(kf):
        AnimationExportMode.kf = kf


def get_n_target(b_target):
    """
    Resolve a Blender object or bone to the NIF block that represents it.

    Returns an (n_block, name) pair. n_block is None when exporting a KF, because none of
    the animated blocks are part of that file. only the name is available there.
    """

    if AnimationExportMode.kf:
        return None, block_store.get_full_name(b_target)

    n_block = block_store.obj_to_block.get(b_target)
    if n_block is None:
        NifLog.warn(f"No exported block found for {b_target.name}; "
                    f"its animation will be targeted by name only.")
        return None, block_store.get_full_name(b_target)

    # Exporting a mesh registers its geometry and then its geometry data against the same
    # object, so the lookup lands on the data block. Animation targets the geometry, which
    # is what holds the name and the properties.
    if isinstance(n_block, NifClasses.NiGeometryData):
        n_block = next((n_geometry for n_geometry in block_store.block_to_obj
                        if isinstance(n_geometry, NifClasses.NiTriBasedGeom)
                        and n_geometry.data is n_block), n_block)

    return n_block, n_block.name


def get_n_property_target(b_obj, property_type):
    """Resolve a Blender object to the geometry that carries a property of this type.

    An object exports one geometry block per material, so the object alone does not say
    which block a material animation belongs to. The property being animated does.

    Returns an (n_geometry, name, n_property) triple, with None entries when the block is
    not part of this file (KF export) or no such property was exported.
    """

    if AnimationExportMode.kf:
        return None, block_store.get_full_name(b_obj), None

    for n_block, b_block_obj in block_store.block_to_obj.items():
        if b_block_obj is not b_obj or not isinstance(n_block, NifClasses.NiTriBasedGeom):
            continue
        n_property = next((prop for prop in n_block.properties if isinstance(prop, property_type)), None)
        if n_property is not None:
            return n_block, n_block.name, n_property

    n_block, n_name = get_n_target(b_obj)
    return n_block, n_name, None


def create_blend_interpolator(blend_type):
    """Create the manager controlled blend interpolator that stands in for a real one."""

    n_blend_interpolator = block_store.create_block(blend_type)
    n_blend_interpolator.array_size = 2
    n_blend_interpolator.reset_field("interp_array_items")
    if hasattr(n_blend_interpolator.flags, "manager_controlled"):
        n_blend_interpolator.flags.manager_controlled = True
    else:
        n_blend_interpolator.manager_controlled = True
    return n_blend_interpolator


def set_controlled_block_strings(n_controlled_block, n_sequence, **strings):
    """
    Name the target of a controlled block.

    Up to 20.1.0.0 the strings live in a NiStringPalette shared by the whole sequence and
    the block only stores offsets into it. Later versions store them inline.
    """

    palette_min, palette_max = V_STRING_PALETTE
    use_palette = palette_min <= NifData.data.version <= palette_max

    if use_palette and n_sequence.string_palette is None:
        n_sequence.string_palette = block_store.create_block("NiStringPalette")

    for field, value in strings.items():
        if value is None:
            continue
        setattr(n_controlled_block, field, value)
        if use_palette:
            n_controlled_block.string_palette = n_sequence.string_palette
            offset = n_sequence.string_palette.palette.add_string(value)
            setattr(n_controlled_block, f"{field}_offset", offset)


def attach_controller(n_ctrl, n_interpolator, node_name, controller_type, n_ctrl_target=None,
                      n_sequence=None, property_type=None, controller_id=None,
                      interpolator_id=None, priority=0, blend_interpolator=True):
    """
    Hook a freshly built controller and its interpolator into the file being exported.

    n_ctrl_target is the block the controller hangs off in a NIF - the animated node
    itself, or the property for material, texture and shader controllers. It is unused
    for KF export, where the controller blocks are not written at all.
    node_name is always the name of the NiAVObject that ends up being animated.

    Returns the controlled block, or None if no sequence was given.
    """

    version = NifData.data.version
    is_kf = AnimationExportMode.kf

    if not is_kf and n_ctrl_target is not None:
        n_ctrl_target.add_controller(n_ctrl)

    if n_sequence is None:
        return None

    if isinstance(n_sequence, NifClasses.NiSequenceStreamHelper):
        # This root has no controlled blocks.
        # Its controllers hang off it in a flat chain,
        # each paired with the extra data block naming the node it belongs to.
        n_string_extra = block_store.create_block("NiStringExtraData")
        n_string_extra.bytes_remaining = len(node_name) + 4
        n_string_extra.string_data = node_name
        n_sequence.add_extra_data(n_string_extra)
        n_sequence.add_controller(n_ctrl)
        n_ctrl.target = None
        return None

    n_controlled_block = n_sequence.add_controlled_block()
    n_controlled_block.priority = priority

    if version >= V_INTERPOLATORS:
        n_controlled_block.interpolator = n_interpolator

    if is_kf:
        # Only the interpolator makes it into a modern KF. Versions predating
        # interpolators have to carry the controller itself instead.
        if version < V_INTERPOLATORS:
            n_ctrl.target = None
            n_controlled_block.controller = n_ctrl
            n_controlled_block.target_name = node_name
    else:
        if version <= V_CONTROLLED_BLOCK_CONTROLLER:
            n_controlled_block.controller = n_ctrl
        # The sequence owns the interpolator holding the keys, so the controller left on
        # the animated block reads its value through a blend interpolator instead.
        blend_type = BLEND_INTERPOLATORS.get(type(n_interpolator).__name__) if blend_interpolator else None
        if blend_type:
            n_ctrl.interpolator = create_blend_interpolator(blend_type)

    set_controlled_block_strings(n_controlled_block, n_sequence,
                                 node_name=node_name,
                                 property_type=property_type,
                                 controller_type=controller_type,
                                 controller_id=controller_id,
                                 interpolator_id=interpolator_id)

    return n_controlled_block


def add_dummy_markers(b_action):
    # a sequence without start and end text keys has no extent the game can play,
    # so stand in for any the action does not define itself

    added_markers = []
    b_marker_names = {marker.name for marker in b_action.pose_markers}

    for frame, text in zip(b_action.frame_range, ("start", "end")):
        if text in b_marker_names:
            continue

        NifLog.info(f"Defining '{text}' action pose marker.")
        marker = b_action.pose_markers.new(text)
        marker.frame = int(frame)

        added_markers.append(marker)

    return added_markers

def create_text_keys(kf_root):
    """Create the text keys before filling in the data so that the extra data hierarchy is correct"""
    # add a NiTextKeyExtraData block
    n_text_extra = block_store.create_block("NiTextKeyExtraData")
    if isinstance(kf_root, NifClasses.NiControllerSequence):
        kf_root.text_keys = n_text_extra
    elif isinstance(kf_root, NifClasses.NiSequenceStreamHelper):
        kf_root.add_extra_data(n_text_extra)
    return n_text_extra

def export_text_keys(fps, b_action, n_text_extra):
    """Process b_action's pose markers and populate the extra string data block."""
    NifLog.info("Exporting animation groups")
    added_markers = add_dummy_markers(b_action)
    f0, f1 = b_action.frame_range

    # sort pose markers by their active frame
    # fixes text keys exporting in the order they're added instead of order they appear
    sortedPoseMarkers = sorted(b_action.pose_markers, key=lambda timelineMarker: timelineMarker.frame)

    # create a text key for each frame descriptor
    n_text_extra.num_text_keys = len(b_action.pose_markers)
    n_text_extra.reset_field("text_keys")

    for key, marker in zip(n_text_extra.text_keys, sortedPoseMarkers):
        f = marker.frame
        if (f < f0) or (f > f1):
            NifLog.warn(f"Marker out of animated range ({f} not between [{f0}, {f1}])")
        key.time = f / fps
        key.value = marker.name.replace('/', '\r\n')

    for new_marker in added_markers:
        b_action.pose_markers.remove(new_marker)

# The bone that carries the accumulated root motion, and the one node of a skeleton whose
# transform controller comes before its blend controller and carries no interpolator
NON_ACCUM_BONE = "nonaccum"


def add_skeleton_controllers(b_armature):
    """
    Give a skeleton's bones the controller chain the game expects.

    A skeleton has no controller manager. Every bone from the non-accum bone down carries a
    NiTransformController of its own, and the order it sits in depends on what else is on the
    node, as the vanilla skeletons show:

      Bip01              NiBSBoneLODController -> NiTransformController[interpolator]
      Bip01 NonAccum     NiTransformController(no interpolator) -> bhkBlendController
      bone with blend    bhkBlendController -> NiTransformController[interpolator]
      plain bone         NiTransformController[interpolator]

    The root's siblings and the scene root get nothing. This runs after collision export, so
    the blend controllers the blend collision objects brought with them are already in place
    and only have to be ordered around.
    """

    b_bones = b_armature.data.bones
    b_non_accum = next((b_bone for b_bone in b_bones if NON_ACCUM_BONE in b_bone.name.lower()), None)

    # the root bone's own controller follows its bone LOD controller, if it has one
    for b_root_bone in (b_bone for b_bone in b_bones if not b_bone.parent):
        n_node = block_store.obj_to_block.get(b_root_bone)
        if n_node is not None and (b_non_accum is None or b_root_bone in b_non_accum.parent_recursive):
            add_transform_controller(n_node, with_interpolator=True)

    if b_non_accum is None:
        NifLog.warn(f"'{b_armature.name}' has no non-accum bone, so its bones were exported "
                    f"without the controllers a skeleton normally carries. Name the bone that "
                    f"holds the root motion something containing 'NonAccum'.")
        return

    n_non_accum_node = block_store.obj_to_block.get(b_non_accum)
    if n_non_accum_node is not None:
        # the only node whose transform controller leads the chain, and the only one without
        # an interpolator
        add_transform_controller(n_non_accum_node, with_interpolator=False, first=True)

    for b_bone in b_non_accum.children_recursive:
        n_node = block_store.obj_to_block.get(b_bone)
        if n_node is not None:
            add_transform_controller(n_node, with_interpolator=True)

    NifLog.info(f"Added skeleton controllers from '{b_non_accum.name}' down.")


def add_transform_controller(n_node, with_interpolator=True, first=False):
    """
    Attach a NiTransformController to a node, appended to whatever chain it already has.

    Pass first to put it at the head of the chain instead, which is what the non-accum bone
    needs so that its blend controller trails it.
    """

    n_transform_controller = block_store.create_block("NiTransformController")
    n_transform_controller.flags = 0x4C
    n_transform_controller.frequency = 1.0
    n_transform_controller.phase = 0.0
    n_transform_controller.start_time = consts.FLOAT_MAX
    n_transform_controller.stop_time = consts.FLOAT_MIN

    if with_interpolator:
        n_transform_controller.interpolator = create_dummy_interpolator(n_node)

    if first and n_node.controller:
        n_next_controller = n_node.controller
        n_node.controller = n_transform_controller
        n_transform_controller.target = n_node
        n_transform_controller.next_controller = n_next_controller
    else:
        n_node.add_controller(n_transform_controller)

    return n_transform_controller


def create_dummy_interpolator(n_node):
    """
    An interpolator holding the node's own transform and no keyframe data.

    The scale is the sentinel the vanilla skeletons use rather than 1.0, which is how a
    transform interpolator says it has no scale of its own.
    """

    n_interpolator = block_store.create_block("NiTransformInterpolator")
    n_scale, n_rotation, n_translation = n_node.get_transform().get_scale_quat_translation()

    n_interpolator.transform.translation.x = n_translation.x
    n_interpolator.transform.translation.y = n_translation.y
    n_interpolator.transform.translation.z = n_translation.z
    n_interpolator.transform.rotation.w = n_rotation.w
    n_interpolator.transform.rotation.x = n_rotation.x
    n_interpolator.transform.rotation.y = n_rotation.y
    n_interpolator.transform.rotation.z = n_rotation.z
    n_interpolator.transform.scale = consts.FLOAT_MIN

    return n_interpolator

def create_controller(parent_block, target_name, priority=0):
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

        if target_name == "Bip01 NonAccum" and not isinstance(parent_block, NifClasses.NiControllerSequence):
            bhkBlendController = block_store.create_block("bhkBlendController", None)
            bhkBlendController.target = parent_block
            n_kfc.next_controller = bhkBlendController
        else:
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
        raise NifError(f"Unsupported KeyframeController parent!")

    return n_kfc, n_kfi

class AnimationCommon(ABC):

    def __init__(self):
        self.fps = bpy.context.scene.render.fps
        self.target_game = bpy.context.scene.niftools_scene.game

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

                if b_action.is_empty == False:
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

    def get_fcurves_from_action(self, b_action, b_action_slot=None):
        """Return an action's curves, optionally restricted to one controlled slot."""

        new_fcurves = []

        for layer in b_action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    if b_action_slot is not None and channelbag.slot != b_action_slot:
                        continue
                    for fcurve in channelbag.fcurves:
                        new_fcurves.append(fcurve)

        return new_fcurves
    
    @staticmethod
    def iter_frame_key(fcurves, mathutilclass):
        """
        Iterator that yields a tuple of frame and key for all fcurves.
        Assumes the fcurves are sampled at the same time and all have the same amount of keys
        Return the key in the desired MathutilsClass
        """
        for point in zip(*[fcu.keyframe_points for fcu in fcurves]):
            frame = point[0].co[0]
            key = [k.co[1] for k in point]
            yield frame, mathutilclass(key)


def animation_data_of(b_obj):
    """Every animation data block that belongs to an object and its dependent data."""

    if b_obj.animation_data:
        yield b_obj.animation_data

    for b_particle_system in getattr(b_obj, "particle_systems", ()) or ():
        b_settings = b_particle_system.settings
        if b_settings and b_settings.animation_data:
            yield b_settings.animation_data

    b_data = getattr(b_obj, "data", None)
    # bone visibility is animated in the armature data
    if isinstance(b_data, bpy.types.Armature) and b_data.animation_data:
        yield b_data.animation_data

    for b_material in getattr(b_data, "materials", ()) or ():
        if not b_material:
            continue
        if b_material.animation_data:
            yield b_material.animation_data
        if b_material.node_tree and b_material.node_tree.animation_data:
            yield b_material.node_tree.animation_data


def has_animation(b_objects):
    """
    True if any of the objects carries animation that the exporter has something to write for.

    An object gets its animation data block as soon as anything touches it, so the block being
    there says nothing, only an action with keys in it, or an NLA strip holding one does.
    """

    for b_obj in b_objects:
        for b_anim_data in animation_data_of(b_obj):
            if any(b_track.strips and b_track.strips[0].action for b_track in b_anim_data.nla_tracks):
                return True
            if b_anim_data.action and not b_anim_data.action.is_empty:
                return True

    return False
