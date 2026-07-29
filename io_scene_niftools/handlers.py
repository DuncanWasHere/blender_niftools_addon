"""Blender application handlers owned by the add-on."""

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

# How often the viewport billboard update runs, in seconds. Returned from the
# timer to schedule the next call, so it doubles as the re-arm interval.
BILLBOARD_INTERVAL = 0.05


def particle_billboard_timer():
    """Keep imported particle sprites and billboard nodes parallel to the 3D viewport."""

    try:
        from .modules.nif_import.particle import update_viewport_billboards
        update_viewport_billboards()
    except (ReferenceError, RuntimeError):
        # Blender may be replacing screens or scenes during file load/quit.
        pass
    return BILLBOARD_INTERVAL


def particle_billboard_render_pre(scene, _depsgraph=None):
    """Point particle sprites and billboard nodes at the camera for an actual render."""

    from .modules.nif_import.particle import update_render_billboards
    update_render_billboards(scene)


def particle_billboard_frame_change(_scene, _depsgraph=None):
    """Refresh billboard orientation and sprite spin after the frame changes.

    Evaluating the depsgraph from here would re-enter the evaluation Blender is
    already running and crash it, so the particle instance transforms measured by the
    viewport timer are reused rather than re-read.
    """

    from .modules.nif_import.particle import update_viewport_billboards
    try:
        update_viewport_billboards(force=True, refresh_corrections=False)
    except (ReferenceError, RuntimeError):
        # the cached object list can outlive the objects when a file is loaded
        pass


def register():
    """Attach handlers, if they are not attached already."""

    if not bpy.app.timers.is_registered(particle_billboard_timer):
        bpy.app.timers.register(particle_billboard_timer,
                                first_interval=BILLBOARD_INTERVAL, persistent=True)
    if particle_billboard_render_pre not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(particle_billboard_render_pre)
    if particle_billboard_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(particle_billboard_frame_change)


def unregister():
    """Detach handlers."""

    if bpy.app.timers.is_registered(particle_billboard_timer):
        bpy.app.timers.unregister(particle_billboard_timer)
    if particle_billboard_render_pre in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(particle_billboard_render_pre)
    if particle_billboard_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(particle_billboard_frame_change)
