"""This script contains classes to help import morph animations as shape keys."""

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
import mathutils
from ....modules.nif_import.animation import Animation
from ....utils import math
from ....utils.logging import NifLog
from ....utils.singleton import EGMData
from nifgen.formats.nif import classes as NifClasses


class MorphAnimation(Animation):

    def __init__(self):
        super().__init__()

    def import_morph_controller(self, n_node, b_obj):
        """Import NiGeomMorpherController as shape keys for blender object."""

        n_morph_ctrl = math.find_controller(n_node, NifClasses.NiGeomMorpherController)
        if n_morph_ctrl:
            NifLog.debug("NiGeomMorpherController processed")
            b_mesh = b_obj.data
            morph_data = n_morph_ctrl.data
            if morph_data.num_morphs:
                # get name for base key
                morph = morph_data.morphs[0]
                key_name = morph.frame_name
                if not key_name:
                    key_name = 'Base'

                # insert base key, using relative keys
                sk_basis = b_obj.shape_key_add(name=key_name)

                # get base vectors and import all morphs
                base_verts = morph.vectors

                # created on the first morph that actually has keys, so that unanimated
                # morphs do not leave an empty action behind on the shape keys
                shape_action = None

                for morph_i in range(1, morph_data.num_morphs):
                    morph = morph_data.morphs[morph_i]
                    # get name for key
                    key_name = morph.frame_name
                    if not key_name:
                        key_name = f'Key {morph_i}'
                    NifLog.info(f"Inserting key '{key_name}'")
                    # get vectors
                    morph_verts = morph.vectors
                    self.morph_mesh(b_mesh, base_verts, morph_verts)
                    shape_key = b_obj.shape_key_add(name=key_name, from_mix=False)

                    # find the keys
                    # older versions store keys in the morph_data
                    # newer versions store keys in the controller
                    if not morph.keys:
                        n_interpolator = None
                        if n_morph_ctrl.interpolators:
                            n_interpolator = n_morph_ctrl.interpolators[morph_i]
                        elif n_morph_ctrl.interpolator_weights:
                            n_interpolator = n_morph_ctrl.interpolator_weights[morph_i].interpolator

                        if not isinstance(n_interpolator, NifClasses.NiFloatInterpolator):
                            # a morph need not be animated at all, and interpolators other
                            # than float ones have no weight curve to import
                            NifLog.info(f"Morph '{key_name}' has no float interpolator "
                                        f"(found {type(n_interpolator).__name__}); "
                                        f"importing its shape without keys.")
                            continue

                        if not n_interpolator.data:
                            NifLog.info(f"Morph '{key_name}' has an interpolator but no data; "
                                        f"importing its shape without keys.")
                            continue

                        morph = n_interpolator.data.data

                    if not morph.keys:
                        continue

                    if shape_action is None:
                        shape_action = self.create_action(b_obj.data.shape_keys, f"{b_obj.name}-Morphs")

                    # get the interpolation mode
                    interp = self.get_b_interp_from_n_interp(morph.interpolation)
                    times, keys = self.get_keys_values(morph.keys)
                    tangents = self.get_nif_tangents(
                        morph.keys, morph.interpolation)
                    self.add_keys(b_obj.data.shape_keys, shape_action, "value", (0,),
                                  n_morph_ctrl.flags, times, keys, interp,
                                  key_name=shape_key.name, tangents=tangents)
                    self.set_max_key_time()

    def import_egm_morphs(self, b_obj):
        """Import all EGM morphs as shape keys for blender object."""
        b_mesh = b_obj.data
        sym_morphs = [list(morph.get_relative_vertices()) for morph in EGMData.data.sym_morphs]
        asym_morphs = [list(morph.get_relative_vertices()) for morph in EGMData.data.asym_morphs]

        # insert base key at frame 1, using absolute keys
        sk_basis = b_obj.shape_key_add(name="Basis")
        b_mesh.shape_keys.use_relative = False

        morphs = ([(morph, f"EGM SYM {i}") for i, morph in enumerate(sym_morphs)] +
                  [(morph, f"EGM ASYM {i}") for i, morph in enumerate(asym_morphs)])

        base_verts = [v.co for v in b_mesh.vertices]
        for morph_verts, key_name in morphs:
            # convert tuples into vector here so we can simply add in morph_mesh()
            for b_v_index, (bv, mv) in enumerate(zip(base_verts, morph_verts)):
                b_mesh.vertices[b_v_index].co = bv + mathutils.Vector(mv)
            b_obj.shape_key_add(name=key_name, from_mix=False)

    def morph_mesh(self, b_mesh, baseverts, morphverts):
        """Transform a mesh to be in the shape given by morphverts."""
        # for each vertex calculate the key position from base
        # pos + delta offset
        # length check disabled
        # as sometimes, oddly, the morph has more vertices...
        # assert(len(baseverts) == len(morphverts))
        for b_v_index, (bv, mv) in enumerate(zip(baseverts, morphverts)):
            # pyffi vector3
            v = bv + mv
            # if applytransform:
            # v *= transform
            b_mesh.vertices[b_v_index].co = v.as_tuple()
