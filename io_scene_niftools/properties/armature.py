"""Nif Format Properties, stores custom nif properties for armature settings"""

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
from bpy.props import (CollectionProperty,
                       IntProperty,
                       EnumProperty,
                       StringProperty
                       )
from bpy.types import PropertyGroup

from ..properties.object import OBJECT_FLAG_BITS
from ..utils.decorators import register_classes, unregister_classes
from ..utils.flags import inject_bit_bools


class BoneProperties(PropertyGroup):
    # a bone is exported as a NiNode, so it carries the same flags as an object does
    flags: IntProperty(
        name='Bone Flag',
        default=0,
        override={"LIBRARY_OVERRIDABLE"},
    )
    priority: IntProperty(
        name='Bone Priority',
        description='Priority to be set on the controlled block using this bone\'s animation data.',
        default=0,
        min=0,
        max=127,
        override={"LIBRARY_OVERRIDABLE"},
    )
    longname: StringProperty(
        name='Nif Long Name',
        description='Name that the bone\'s corresponding NiNode will have upon export.',
    )


inject_bit_bools(BoneProperties, 'flags', OBJECT_FLAG_BITS)


class BoneLODBone(PropertyGroup):
    """One bone reference inside a bone LOD group."""

    bone: StringProperty(
        name="Bone",
        description="Bone belonging to this LOD group",
        default='',
    )


class BoneLODGroup(PropertyGroup):
    """One LOD level of a NiBSBoneLODController. Its index in the list is its level."""

    bones: CollectionProperty(type=BoneLODBone)
    active_bone_index: IntProperty(default=0)


class ArmatureProperties(PropertyGroup):
    axis_forward: EnumProperty(
        name="Forward",
        items=(('X', "X Forward", ""),
               ('Y', "Y Forward", ""),
               ('Z', "Z Forward", ""),
               ('-X', "-X Forward", ""),
               ('-Y', "-Y Forward", ""),
               ('-Z', "-Z Forward", ""),
               ),
        default="X",
    )

    axis_up: EnumProperty(
        name="Up",
        items=(('X', "X Up", ""),
               ('Y', "Y Up", ""),
               ('Z', "Z Up", ""),
               ('-X', "-X Up", ""),
               ('-Y', "-Y Up", ""),
               ('-Z', "-Z Up", ""),
               ),
        default="Y",
    )

    skeleton_id: IntProperty(
        name="Skeleton ID",
        description="Value of the SkeletonID NiIntegerExtraData on the nif root. Block not exported if 0",
        default=0,
        min=0,
    )

    bone_lod_groups: CollectionProperty(
        name="Bone LOD Groups",
        description="The bone groups of the NiBSBoneLODController. Each group's position in "
                    "the list is its LOD level",
        type=BoneLODGroup,
    )

    active_bone_lod_group_index: IntProperty(default=0)


CLASSES = [
    BoneProperties,
    BoneLODBone,
    BoneLODGroup,
    ArmatureProperties
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.Armature.nif_armature = bpy.props.PointerProperty(type=ArmatureProperties)
    bpy.types.Bone.nif_bone = bpy.props.PointerProperty(type=BoneProperties)


def unregister():
    del bpy.types.Armature.nif_armature
    del bpy.types.Bone.nif_bone

    unregister_classes(CLASSES, __name__)
