"""This script contains helper methods to import objects."""

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
import json
import re
from math import pi

from .....modules.nif_import.object.block_registry import block_store
from .....utils import decal
from .....utils.flags import to_signed_32
from .....utils.logging import NifLog
from .....utils.serialization import block_to_dict
from nifgen.formats.nif import classes as NifClasses

# A bone states its animation priority in its UPB string as 'BSPriority#7#'. The LOD levels
# the string also carries come from the LOD controller's node groups instead.
BONE_PRIORITY = re.compile(r'BSPriority#(\d+)#')


def is_object_upb(b_upb):
    """Whether a UPB string contains supported bone data worth importing."""

    return 'BSBoneLOD' in b_upb or 'Bip' in b_upb


def get_bone_priority(b_upb):
    """The animation priority a UPB string declares, or None if it declares none."""

    if not b_upb:
        return None

    match = BONE_PRIORITY.search(b_upb)
    return int(match.group(1)) if match else None

# Nif node blocks paired with the nodetype they are stored as. Most derived first, so that a
# subclass is recognised before the base it inherits from.
NODE_TYPES = (
    (NifClasses.BSDamageStage, 'BSDamageStage'),
    (NifClasses.BSBlastNode, 'BSBlastNode'),
    (NifClasses.BSDebrisNode, 'BSDebrisNode'),
    (NifClasses.BSRangeNode, 'BSRangeNode'),
    (NifClasses.NiLODNode, 'NiLODNode'),
    (NifClasses.NiSwitchNode, 'NiSwitchNode'),
    (NifClasses.BSMultiBoundNode, 'BSMultiBoundNode'),
    (NifClasses.BSValueNode, 'BSValueNode'),
    (NifClasses.BSOrderedNode, 'BSOrderedNode'),
    (NifClasses.BSMasterParticleSystem, 'BSMasterParticleSystem'),
    (NifClasses.BSLeafAnimNode, 'BSLeafAnimNode'),
    (NifClasses.BSFadeNode, 'BSFadeNode'),
    (NifClasses.RootCollisionNode, 'RootCollisionNode'),
    (NifClasses.NiBillboardNode, 'NiBillboardNode'),
    (NifClasses.NiSortAdjustNode, 'NiSortAdjustNode'),
)


class ObjectProperty:

    # TODO [property] Add delegate processing
    def import_object_properties(self, n_block, b_obj):
        """Import object flags and node types."""

        # Store object flags
        if hasattr(b_obj, 'nif_object'):
            b_obj.nif_object.flags = to_signed_32(n_block.flags)
        elif hasattr(b_obj, 'nif_bone'):
            b_obj.nif_bone.flags = to_signed_32(n_block.flags)

        if not issubclass(type(n_block), NifClasses.NiNode):
            return

        # Store type of node
        for n_node_type, b_nodetype in NODE_TYPES:
            if isinstance(n_block, n_node_type):
                b_obj.nif_object.nodetype = b_nodetype
                break

        if isinstance(n_block, NifClasses.BSMasterParticleSystem):
            if hasattr(b_obj, 'nif_master_particle_system'):
                b_obj.nif_master_particle_system.max_emitter_objects = n_block.max_emitter_objects

        self.import_node_subtype_data(n_block, b_obj)

    @staticmethod
    def import_node_subtype_data(n_block, b_obj):
        """Import the fields a node subtype adds on top of NiNode.

        Every check is a separate `if` rather than a chain, because these are independent
        inheritance branches - a NiLODNode is also a NiSwitchNode and needs both.
        """

        nif_object = getattr(b_obj, 'nif_object', None)
        if nif_object is None:
            # bones carry nif_bone instead, and none of these blocks is ever a bone
            return

        if isinstance(n_block, NifClasses.BSRangeNode):
            nif_object.node_range.min = n_block.min
            nif_object.node_range.max = n_block.max
            nif_object.node_range.current = n_block.current

        if isinstance(n_block, NifClasses.BSValueNode):
            nif_object.node_value.value = n_block.value
            nif_object.node_value.value_node_flags = int(n_block.value_node_flags)

        if isinstance(n_block, NifClasses.BSOrderedNode):
            n_bound = n_block.alpha_sort_bound
            nif_object.node_ordered.alpha_sort_bound = (n_bound.x, n_bound.y, n_bound.z, n_bound.w)
            nif_object.node_ordered.static_bound = bool(n_block.static_bound)

        if isinstance(n_block, NifClasses.NiSwitchNode):
            nif_object.node_switch.index = n_block.index
            # switch flags only exist from 10.1.0.0 on
            nif_object.node_switch.switch_node_flags = int(getattr(n_block, "switch_node_flags", 0))

        if isinstance(n_block, NifClasses.NiLODNode):
            ObjectProperty.import_lod_data(n_block, nif_object)

        if isinstance(n_block, NifClasses.NiSortAdjustNode):
            nif_object.node_sort_adjust.sorting_mode = n_block.sorting_mode.name

        if isinstance(n_block, NifClasses.BSMultiBoundNode):
            # culling mode was only added for Skyrim. The Fallout 3 era has no such field
            if hasattr(n_block, "culling_mode"):
                nif_object.node_multi_bound.culling_mode = n_block.culling_mode.name

    @staticmethod
    def import_lod_data(n_block, nif_object):
        """Import a NiLODNode's LOD center and which kind of data drives its switching."""

        n_lod_data = getattr(n_block, "lod_level_data", None)

        if isinstance(n_lod_data, NifClasses.NiScreenLODData):
            # nothing here maps onto the children, so keep the block verbatim
            nif_object.node_lod.lod_type = 'NiScreenLODData'
            nif_object.node_lod.screen_lod_data = json.dumps(block_to_dict(n_lod_data))
            return

        nif_object.node_lod.lod_type = 'NiRangeLODData'
        nif_object.node_lod.screen_lod_data = ''

        # up to 10.0.1.0 the center sits on the node, after that on the NiRangeLODData
        n_center_source = n_lod_data if n_lod_data is not None else n_block
        n_center = getattr(n_center_source, "lod_center", None)
        if n_center is not None:
            nif_object.node_lod.lod_center = (n_center.x, n_center.y, n_center.z)

    def import_extra_data(self, n_node, b_obj):
        """Import extra data blocks for NiNode types."""
        for n_extra in n_node.get_extra_datas():
            if n_extra.name == "UPB" and is_object_upb(n_extra.string_data):
                b_obj.nif_object.upb = n_extra.string_data

    def import_bone_extra_data(self, n_node, b_bone):
        """
        Import what a bone's UPB string holds, and the bone LOD groups if it carries them.

        The LOD levels in the UPB and the controller's node groups say the same thing, so
        only the controller is read; the levels come back out of the groups on export.
        """

        for n_extra in n_node.get_extra_datas():
            if n_extra.name == "UPB":
                n_priority = get_bone_priority(n_extra.string_data)
                if n_priority is not None:
                    b_bone.nif_bone.priority = n_priority

        for n_controller in n_node.get_controllers():
            if isinstance(n_controller, NifClasses.NiBoneLODController):
                self.import_bone_lod_groups(n_controller, b_bone.id_data)

    @staticmethod
    def import_bone_lod_groups(n_bone_lod_controller, b_armature_data):
        """Fill the armature's bone LOD groups from the controller's node groups."""

        nif_armature = b_armature_data.nif_armature
        nif_armature.bone_lod_groups.clear()

        for n_group in n_bone_lod_controller.node_groups:
            b_group = nif_armature.bone_lod_groups.add()
            for n_node in n_group.nodes:
                if n_node is None:
                    continue
                b_bone_name = block_store.import_name(n_node)
                if b_bone_name not in b_armature_data.bones:
                    NifLog.warn(f"Bone LOD group names '{b_bone_name}', which is not a bone of "
                                f"'{b_armature_data.name}'. Skipped.")
                    continue
                b_group.bones.add().bone = b_bone_name

        NifLog.info(f"Imported {len(nif_armature.bone_lod_groups)} bone LOD groups.")

    def import_root_extra_data(self, n_root_node, b_obj):
        """Import extra data blocks for root node."""
        for n_extra in n_root_node.get_extra_datas():
            if isinstance(n_extra, NifClasses.BSDecalPlacementVectorExtraData):
                self.import_decal_placement(n_extra, b_obj)
            elif isinstance(n_extra, NifClasses.NiStringExtraData):
                # weapon location or attachment position
                if n_extra.name == "Prn":
                    b_obj.nif_object.prn_location = n_extra.string_data
                elif n_extra.name == "UPB" and is_object_upb(n_extra.string_data):
                    b_obj.nif_object.upb = n_extra.string_data
            elif isinstance(n_extra, NifClasses.BSXFlags):
                # checked before NiIntegerExtraData, which it inherits from
                b_obj.nif_object.bsxflags = to_signed_32(n_extra.integer_data)
            elif isinstance(n_extra, NifClasses.NiIntegerExtraData) and n_extra.name == "SkeletonID":
                # a skeleton is imported as an armature, so its id belongs on the armature data
                if getattr(b_obj, "type", None) == 'ARMATURE':
                    b_obj.data.nif_armature.skeleton_id = n_extra.integer_data
                else:
                    NifLog.warn(f"Found a SkeletonID of {n_extra.integer_data} but the root "
                                f"'{b_obj.name}' is not an armature, so it was not imported.")
            elif isinstance(n_extra, NifClasses.BSInvMarker):
                bs_inv_item = b_obj.nif_object.bs_inv.add()
                bs_inv_item.name = n_extra.name
                bs_inv_item.x = (-n_extra.rotation_x / 1000) % (2 * pi)
                bs_inv_item.y = (-n_extra.rotation_y / 1000) % (2 * pi)
                bs_inv_item.z = (-n_extra.rotation_z / 1000) % (2 * pi)
                bs_inv_item.zoom = n_extra.zoom

    @staticmethod
    def import_decal_placement(n_extra, b_root):
        """Import point/normal pairs as arrow empties parented to the Blender root."""

        b_store = b_root.nif_object.bs_decal_placement
        if b_store:
            NifLog.warn(f"'{b_root.name}' already has decal placement data, so the extra "
                        f"'{n_extra.name}' block was not imported. A nif holds one of these.")
            return
        b_data = b_store.add()

        if n_extra.name != "DVPG" or n_extra.float_data:
            NifLog.warn(f"Decal placement data on '{b_root.name}' is named '{n_extra.name}' with "
                        f"a float value of {n_extra.float_data}; it will be exported as 'DVPG' "
                        f"with a value of 0.")

        for block_index, n_vector_block in enumerate(n_extra.vector_blocks):
            b_vector_block = b_data.vector_blocks.add()
            n_count = min(len(n_vector_block.points), len(n_vector_block.normals))
            if n_count != n_vector_block.num_vectors:
                NifLog.warn(
                    f"Decal vector block {block_index + 1} on '{b_root.name}' declares "
                    f"{n_vector_block.num_vectors} vectors but contains "
                    f"{len(n_vector_block.points)} points and {len(n_vector_block.normals)} "
                    f"normals; imported the {n_count} complete pairs.")

            # the files repeat the vectors as reference nodes, so reuse those as handles
            b_group = decal.find_vector_group(b_root, block_index)
            b_candidates = decal.adoptable_handles(b_group) if b_group else []

            for n_point, n_normal in zip(n_vector_block.points, n_vector_block.normals):
                b_point = decal.imported_point((n_point.x, n_point.y, n_point.z))
                b_normal = (n_normal.x, n_normal.y, n_normal.z)
                b_helper = decal.claim_handle(b_root, b_candidates, b_point)
                if b_helper is None:
                    b_group = b_group or decal.vector_group(b_root, block_index)
                    b_helper = decal.create_point_helper(
                        b_root, b_point, b_normal, decal.next_vector_name(b_group),
                        b_parent=b_group)
                else:
                    # reference node rotations do not match the normals in the block
                    decal.make_handle(b_helper, b_root)
                    decal.place_handle(b_root, b_helper, b_point, b_normal)
                b_vector_block.points.add().helper = b_helper

            if b_candidates:
                NifLog.warn(f"{len(b_candidates)} node(s) under '{b_group.name}' did not match "
                            f"any vector of decal block {block_index + 1} and were left as "
                            f"ordinary nodes.")

        NifLog.info(
            f"Imported BSDecalPlacementVectorExtraData '{n_extra.name}' with "
            f"{len(b_data.vector_blocks)} vector blocks.")
