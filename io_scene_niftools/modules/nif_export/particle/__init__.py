"""Classes for exporting NIF particle blocks."""
import bpy
from io_scene_niftools import NifLog
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


from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.object import DICT_NAMES


class Particle:
    """Main interface class for exporting NIF particle blocks."""

    def __init__(self):
        self.target_game = bpy.context.scene.niftools_scene.game

    def export_particles(self, b_particle_objects, n_root_node):
        """Export particle blocks."""

        for b_p_obj in b_particle_objects:
            if not b_p_obj.parent:
                NifLog.warn(f"Particle object {b_p_obj.name} has no parent! "
                            f"It will not be exported.")
                continue

            n_parent_node = DICT_NAMES[b_p_obj.parent]

            n_ni_particle_system = self.export_ni_particle_system(b_p_obj, n_parent_node)
            self.export_ni_p_sys_data(b_p_obj, n_ni_particle_system)

    def export_ni_particle_system(self, b_p_obj, n_parent_node):
        n_ni_particle_system = block_store.create_block("NiParticleSystem", b_p_obj)
        n_parent_node.add_child(n_ni_particle_system)

        return n_ni_particle_system

    def export_ni_p_sys_data(self, b_p_obj, n_ni_particle_system):
        n_ni_p_sys_data = block_store.create_block("NiPSysData", b_p_obj)
        n_ni_particle_system.data = n_ni_p_sys_data

        return

    def export_ni_p_sys_emitter(self, b_p_obj, n_ni_particle_system):
        return
