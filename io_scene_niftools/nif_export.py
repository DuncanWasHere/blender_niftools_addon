"""Main Blender -> NIF export script."""

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


import os.path

import bpy
from io_scene_niftools.file_io import File
from io_scene_niftools.modules.nif_export.animation import Animation
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.collision import Collision
from io_scene_niftools.modules.nif_export.constraint import Constraint
from io_scene_niftools.modules.nif_export.object import Object
from io_scene_niftools.modules.nif_export.particle import Particle
from io_scene_niftools.modules.nif_export.scene import Scene
from io_scene_niftools.nif_common import NifCommon
from io_scene_niftools.utils import math
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.utils.singleton import NifOp, EGMData, NifData
from nifgen.formats.nif import classes as NifClasses


class NifExport(NifCommon):
    """Main NIF export function."""

    def __init__(self, operator, context):
        NifCommon.__init__(self, operator, context)

        # Helper systems
        self.scene_helper = Scene() # Exports header version data
        self.object_helper = Object() # Exports nodes and geometry blocks
        self.collision_helper = Collision() # Exports collision blocks
        self.constraint_helper = Constraint() # Exports constraint blocks
        self.particle_helper = Particle() # Exports particle blocks
        self.animation_helper = Animation() # Exports animation blocks

        # Blender objects to be exported
        self.b_exportable_objects = []
        self.b_root_objects = []
        self.b_collision_objects = []
        self.b_constraint_objects = []
        self.b_particle_objects = []

        # Common export properties
        self.target_game = None
        self.version = None

        # Used in testing
        self.root_blocks = []

    def execute(self):
        """Main NIF export function."""

        # Force Blender context to object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

        NifLog.info(f"Preparing to write file at {NifOp.props.filepath}")

        # Extract directory, base name, extension
        directory = os.path.dirname(NifOp.props.filepath)
        file_base, file_ext = os.path.splitext(os.path.basename(NifOp.props.filepath))

        block_store.block_to_obj = {}  # Clear out previous iteration

        # Catch export errors
        try:
            n_data = self.validate_nif_version() # Validate version info and initialize NIF file
            self.validate_scene_objects() # Get scene objects and validate
            self.validate_object_data() # Validate scene object transforms and vertex weights

            self.fix_bone_orientations()

            NifLog.info("Exporting...")

            # Export the actual root node and its children as nodes and geometry blocks
            # Root node is exported as a meta root if multiple root objects are present
            # The name is fixed later to avoid confusing the exporter with duplicate names
            # Specialized objects not in b_exportable_objects are skipped for now
            n_root_node = self.object_helper.export_objects(self.b_root_objects, self.target_game, file_base)

            # Export remaining block type categories
            # TODO: Rewrite the following modules to fully encapsulate each block type
            self.collision_helper.export_collision(self.b_collision_objects, self.target_game)
            # self.constraint_helper.export_constraints(self.b_constraint_objects, n_root_node, self.target_game)
            self.particle_helper.export_particles(self.b_particle_objects, n_root_node, self.target_game)
            self.animation_helper.export_animations(self.b_exportable_objects, n_root_node)

            self.correct_scale(n_data, n_root_node) # Correct scale for NIF units
            self.generate_mopp_data() # Generate MOPP data

            n_data.roots = [n_root_node]

            File.write_file(n_data, directory, file_base, file_ext) # Write NIF file

            # Save exported file (this is used by the test suite)
            self.root_blocks = [n_root_node]

        except NifError:
            return {'CANCELLED'}

        NifLog.info("Finished.")
        return {'FINISHED'}

    def validate_nif_version(self):
        """
        Initialize NIF file with version n_data from the scene.
        Prevent export if no game was selected.
        Return NIF n_data.
        """

        self.target_game, self.version, n_data = self.scene_helper.get_version_data()


        if self.target_game == 'UNKNOWN':
            raise NifError("You have not selected a game. Please select a game and"
                           " nif version in the scene tab.")

        NifData.init(n_data)
        return n_data

    def validate_scene_objects(self):
        """
        Get all Blender objects in the scene.
        Store all objects without parents as root objects.
        Separate collision objects, constraints,
        and particle systems into their own lists
        to be fed to their respective export scripts.
        Also prevent export if scene is empty.
        """

        (self.b_exportable_objects,
         self.b_root_objects,
         self.b_collision_objects,
         self.b_constraint_objects,
         self.b_particle_objects) = self.object_helper.get_export_objects()

        if not self.b_exportable_objects:
            NifLog.warn("No objects to export!")
            return {'FINISHED'}

    def validate_object_data(self):
        """
        Protect against exporting skinned meshes with enveloped weights
        and objects with non-uniform scale transforms
        (both are currently unsupported).
        """

        for b_obj in self.b_exportable_objects:
            if b_obj.type == 'MESH':
                if b_obj.parent and b_obj.parent.type == 'ARMATURE':
                    for b_mod in b_obj.modifiers:
                        if b_mod.type == 'ARMATURE' and b_mod.use_bone_envelopes:
                            raise NifError(
                                f"'{b_obj.name}': Envelope weights for skinned objects are currently unsupported."
                                f" If you have vertex groups, turn off envelopes.\n"
                                f"If you don't have vertex groups, select each bone one-by-one and press 'W' to "
                                f"convert their envelopes to vertex weights, then turn off envelopes.")

            # Protect against non-uniform scale transforms
            b_scale = b_obj.scale
            if abs(b_scale.x - b_scale.y) > NifOp.props.epsilon or abs(b_scale.y - b_scale.z) > NifOp.props.epsilon:
                NifLog.warn(f"Non-uniform scaling is currently not supported.\n"
                            f"Workaround: apply size and rotation (CTRL-A) on '{b_obj.name}.'")

    def fix_bone_orientations(self):
        """Correct bone orientations if the scene has an armature."""

        b_armatures = math.get_armatures()
        if b_armatures:
            for b_armature in b_armatures:
                math.set_bone_orientation(b_armature.data.niftools.axis_forward,
                                          b_armature.data.niftools.axis_up)

    def flatten_skin(self):
        """
        Export a flattened hierarchy of NiNodes for each bone in the armature affecting a skinned mesh.
        Needs to be fixed.
        """

        # FIXME:
        """
        if self.EXPORT_FLATTENSKIN:
            # (warning: trouble if armatures parent other armatures or
            # if bones parent geometries, or if object is animated)
            # flatten skins
            skelroots = set()
            affectedbones = []
            for block in block_store.block_to_obj:
                if isinstance(block, NifFormat.NiGeometry) and block.is_skin():
                    NifLog.info("Flattening skin on geometry {0}".format(block.name))
                    affectedbones.extend(block.flatten_skin())
                    skelroots.add(block.skin_instance.skeleton_root)
            # remove NiNodes that do not affect skin
            for skelroot in skelroots:
                NifLog.info("Removing unused NiNodes in '{0}'".format(skelroot.name))
                skelrootchildren = [child for child in skelroot.children
                                    if ((not isinstance(child,
                                                        NifFormat.NiNode))
                                        or (child in affectedbones))]
                skelroot.num_children = len(skelrootchildren)
                skelroot.children.update_size()
                for i, child in enumerate(skelrootchildren):
                    skelroot.children[i] = child
        """

    def correct_scale(self, n_data, n_root_node):
        """Apply scale to convert Blender units to NIF units."""

        n_data.roots = [n_root_node]
        scale_correction = bpy.context.scene.niftools_scene.scale_correction
        if abs(1 - scale_correction) > NifOp.props.epsilon:
            self.apply_scale(n_data, 1 / scale_correction)
            # Also scale EGM
            if EGMData.data:
                EGMData.data.apply_scale(1 / scale_correction)

    def generate_mopp_data(self):
        """Generate MOPP data (must be done after applying scale)!"""

        if bpy.context.scene.niftools_scene.is_bs():
            for block in block_store.block_to_obj:
                if isinstance(block, NifClasses.BhkMoppBvTreeShape):
                    NifLog.info("Generating mopp...")
                    block.update_mopp()
                    # NifLog.debug(f"=== DEBUG: MOPP TREE ===")
                    # block.parse_mopp(verbose = True)
                    # NifLog.debug(f"=== END OF MOPP TREE ===")
                    # Warn about MOPP on non-static objects
                    if any(sub_shape.layer != 1 for sub_shape in block.shape.sub_shapes):
                        NifLog.warn(
                            "MOPP for non-static objects may not function correctly in-game. "
                            "You may wish to use list shapes for collision.")