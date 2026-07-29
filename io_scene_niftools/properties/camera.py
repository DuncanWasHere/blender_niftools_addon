"""Nif User Interface, custom nif properties for cameras"""

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
from bpy.props import FloatProperty, IntProperty
from bpy.types import PropertyGroup

from ..utils.decorators import register_classes, unregister_classes


class CameraProperties(PropertyGroup):
    """Group of NiCamera properties, attached to cameras through a property pointer.

    Only the fields Blender has no camera setting for live here. The frustum and the
    projection type are read off the Blender camera itself (lens angle, shift, clipping,
    orthographic scale), so that a camera set up the ordinary way exports correctly.
    """

    camera_flags: IntProperty(
        name='Camera Flags',
        description='Obsolete flags, present from 10.1.0.0 on. Nothing reads them',
        default=0,
        min=0,
        max=65535
    )

    lod_adjust: FloatProperty(
        name='LOD Adjust',
        description='Scales the distances at which NiLODNodes under this camera switch level',
        default=1.0
    )

    viewport_left: FloatProperty(
        name='Left',
        description='Left edge of the viewport rectangle this camera renders into',
        default=0.0
    )

    viewport_right: FloatProperty(
        name='Right',
        description='Right edge of the viewport rectangle this camera renders into',
        default=1.0
    )

    viewport_top: FloatProperty(
        name='Top',
        description='Top edge of the viewport rectangle this camera renders into',
        default=1.0
    )

    viewport_bottom: FloatProperty(
        name='Bottom',
        description='Bottom edge of the viewport rectangle this camera renders into',
        default=0.0
    )


CLASSES = [
    CameraProperties
]


def register():
    register_classes(CLASSES, __name__)

    bpy.types.Camera.nif_camera = bpy.props.PointerProperty(type=CameraProperties)


def unregister():
    del bpy.types.Camera.nif_camera

    unregister_classes(CLASSES, __name__)
