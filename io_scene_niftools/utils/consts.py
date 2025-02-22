"""Nif Utilities, stores common constants that are used across the codebase"""
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


B_R_POSTFIX = "].R"
B_L_POSTFIX = "].L"

B_R_SUFFIX = ".R"
B_L_SUFFIX = ".L"

BRACE_L = "[L"
BRACE_R = "[R"

OPEN_BRACKET = "["
CLOSE_BRACKET = "]"

NPC_SUFFIX = "NPC "
NPC_L = "NPC L "
NPC_R = "NPC R "

BIP_01 = "Bip01 "
BIP01_R = "Bip01 R "
BIP01_L = "Bip01 L "

UPB_DEFAULT = 'Mass = 0.000000\r\nEllasticity = 0.300000\r\nFriction = 0.300000\r\nUnyielding = 0\r\nSimulation_Geometry = 2\r\nProxy_Geometry = <None>\r\nUse_Display_Proxy = 0\r\nDisplay_Children = 1\r\nDisable_Collisions = 0\r\nInactive = 0\r\nDisplay_Proxy = <None>\r\n'

FLOAT_MIN = -3.4028234663852886e+38
FLOAT_MAX = +3.4028234663852886e+38

VERTEX_RESOLUTION = 1000
NORMAL_RESOLUTION = 100

LOGGER_PYFFI = "pyffi"
LOGGER_PLUGIN = "niftools"


class EmptyObject:
    pass

TEX_SLOTS = EmptyObject()
TEX_SLOTS.BASE = "base"
TEX_SLOTS.DARK = "dark"
TEX_SLOTS.DETAIL = "detail"
TEX_SLOTS.GLOSS = "gloss"
TEX_SLOTS.GLOW = "glow"
TEX_SLOTS.BUMP_MAP = "bump map"
TEX_SLOTS.DECAL_0 = "decal 0"
TEX_SLOTS.DECAL_1 = "decal 1"
TEX_SLOTS.DECAL_2 = "decal 2"
TEX_SLOTS.SPECULAR = "specular"
TEX_SLOTS.NORMAL = "normal"
TEX_SLOTS.ENV_MAP = "environment map"
TEX_SLOTS.ENV_MASK = "environment mask"

BS_TEX_SLOTS = EmptyObject()
BS_TEX_SLOTS.DIFFUSE_MAP = "Diffuse Map"
BS_TEX_SLOTS.NORMAL_MAP = "Normal Map"
BS_TEX_SLOTS.GLOW_MAP = "Glow Map"
BS_TEX_SLOTS.PARALLAX_MAP = "Parallax Map"
BS_TEX_SLOTS.ENVIRONMENT_MAP = "Environment Map"
BS_TEX_SLOTS.ENVIRONMENT_MASK = "Environment Mask"
BS_TEX_SLOTS.SUBSURFACE_TINT_MAP = "Subsurface Tint Map"
BS_TEX_SLOTS.BACKLIGHT_MAP = "Backlight Map"

# Default ordering of Extra data blocks for different games
USED_EXTRA_SHADER_TEXTURES = {
    'SID_MEIER_S_RAILROADS': (3, 0, 4, 1, 5, 2),
    'CIVILIZATION_IV': (3, 0, 1, 2)
}

# fcurve data types for blender
QUAT = "rotation_quaternion"
EULER = "rotation_euler"
LOC = "location"
SCALE = "scale"
