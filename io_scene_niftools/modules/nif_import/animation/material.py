"""This script contains classes to help import material animations."""

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

from ....modules.nif_import.animation import Animation
from ....modules.nif_import.property.node_wrapper import get_shader_group_node
from ....utils import math
from ....utils.logging import NifLog
from ....utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses

# indices for blender ShaderNodeMapping node
LOC_DP = 1
SCALE_DP = 3
MAPPING = "ShaderNodeMapping"


class MaterialAnimation(Animation):

    def import_material_controllers(self, n_geom, b_material):
        """Import material animation data for given geometry."""
        if not NifOp.props.animation:
            return
        n_material = math.find_property(n_geom, NifClasses.NiMaterialProperty)
        if n_material:
            self.import_material_alpha_controller(b_material, n_material)
            self.import_emissive_mult_controller(b_material, n_material)
            for b_channel, n_target_color in (("niftools.ambient_color", NifClasses.MaterialColor.TC_AMBIENT),
                                              ("diffuse_color", NifClasses.MaterialColor.TC_DIFFUSE),
                                              ("specular_color", NifClasses.MaterialColor.TC_SPECULAR),
                                              ("emissive_color", NifClasses.MaterialColor.TC_SELF_ILLUM)):
                self.import_material_color_controller(b_material, n_material, b_channel, n_target_color)

        self.import_uv_controller(b_material, n_geom)
        self.import_tex_transform_controller(b_material, n_geom)
        self.import_shader_float_controllers(b_material, n_geom)

    # controllers that animate a single float on the shader node group
    FLOAT_CONTROLLER_SOCKETS = {
        "NiAlphaController": ("Alpha", "alpha controller"),
        "BSMaterialEmittanceMultController": ("Emissive Mult", "emissive mult controller"),
        "BSRefractionStrengthController": ("Refraction Strength", "refraction strength controller"),
        "BSRefractionFirePeriodController": (
            "Refraction Fire Period", "refraction fire period controller"),
    }

    def import_sequence_controlled_block(self, n_controlled_block, sequence_name):
        """Import one controlled block of a NiControllerSequence that animates a material.

        In a sequence the keys live on the block's own interpolator, while the controller
        on the target only holds a blend interpolator that mixes the running sequences,
        which is why these animations cannot be read from the target alone.

        :return: True when the block was handled here.
        """

        from ....modules.nif_import.property.material import (
            DICT_MATERIALS_BY_CONTROLLER,
            DICT_MATERIALS_BY_NODE,
        )

        n_controller = n_controlled_block.controller
        controller_type = str(n_controlled_block.controller_type or "")
        if n_controller is not None and not controller_type:
            controller_type = type(n_controller).__name__
        if controller_type not in self.FLOAT_CONTROLLER_SOCKETS and \
                controller_type not in ("NiTextureTransformController", "NiMaterialColorController"):
            return False

        node_name = str(n_controlled_block.node_name or n_controlled_block.target_name or "")
        b_materials = []
        b_named_material = DICT_MATERIALS_BY_NODE.get(node_name)
        if b_named_material is not None:
            b_materials.append(b_named_material)
        if n_controller is not None:
            for b_material in DICT_MATERIALS_BY_CONTROLLER.get(n_controller, ()):
                if b_material not in b_materials:
                    b_materials.append(b_material)

        if not b_materials:
            NifLog.warn(f"The sequence animates '{controller_type}' on '{node_name}', "
                        f"which has no imported material, so it is skipped")
            return True
        if len(b_materials) > 1:
            NifLog.info(
                f"The sequence's shared {controller_type} drives {len(b_materials)} materials")

        n_ctrl_data = self.get_interpolator_data(n_controlled_block.interpolator)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The '{controller_type}' of '{node_name}' holds no keys, so it is skipped")
            return True

        interp = self.get_b_interp_from_n_interp(n_ctrl_data.interpolation)
        times, keys = self.get_keys_values(n_ctrl_data.keys)
        tangents = self.get_nif_tangents(
            n_ctrl_data.keys, n_ctrl_data.interpolation)
        flags = n_controller.flags if n_controller is not None else 0

        for b_material in b_materials:
            if controller_type in self.FLOAT_CONTROLLER_SOCKETS:
                socket_name, description = self.FLOAT_CONTROLLER_SOCKETS[controller_type]
                data_path = self.get_shader_socket_path(b_material, socket_name)
                if data_path is None:
                    NifLog.warn(f"Cannot import the {description} of '{b_material.name}': "
                                f"its material has no '{socket_name}' shader input")
                    continue
                NifLog.info(f"Importing sequence {description} for '{b_material.name}'")
                b_action = self.create_action(b_material.node_tree,
                                              f"{b_material.name}-MaterialNodesAction",
                                              sequence_name)
                self.add_keys(
                    b_material.node_tree, b_action, data_path, (0,), flags,
                    times, keys, interp, tangents=tangents)

            elif controller_type == "NiMaterialColorController":
                data_path = self.get_shader_socket_path(b_material, "Emissive Color")
                if data_path is None:
                    continue
                NifLog.info(f"Importing sequence material colour controller for '{b_material.name}'")
                b_action = self.create_action(b_material.node_tree,
                                              f"{b_material.name}-MaterialNodesAction",
                                              sequence_name)
                self.add_keys(
                    b_material.node_tree, b_action, data_path, range(3), flags,
                    times, keys, interp, tangents=tangents)

            else:
                self.import_texture_transform_keys(
                    b_material, n_controller, times, keys, interp, flags,
                    sequence_name, tangents)

        self.set_max_key_time()
        return True

    def import_texture_transform_keys(self, b_material, n_controller, times, keys,
                                      interp, flags, sequence_name, tangents=None):
        """Insert texture transform keys onto the material's mapping node."""

        operation = getattr(n_controller, "operation", None)
        data_path, array_ind = self.get_texture_transform_target(operation, keys)
        if data_path is None:
            return
        # NIF translation values move texture coordinates, while the game presents
        # them as texture motion in the opposite direction. Blender's Mapping node
        # also transforms coordinates, so negate U to preview the in-game motion.
        # V already changes sign when converting from NIF's image coordinates to
        # Blender's, and the two inversions cancel.
        if operation in (NifClasses.TransformMember.TT_TRANSLATE_U,):
            keys, tangents = self.scale_key_data(keys, tangents, -1)

        NifLog.info(f"Importing sequence texture transform for '{b_material.name}'")
        b_action, transform = self.insert_mapping_node(b_material, sequence_name)
        self.add_keys(b_material.node_tree, b_action,
                      f'nodes["{transform.name}"].inputs[{data_path}].default_value',
                      (array_ind,), flags, times, keys, interp,
                      tangents=tangents)

    @staticmethod
    def get_texture_transform_target(operation, keys):
        """Map a texture transform operation to a mapping node input and index."""

        if operation == NifClasses.TransformMember.TT_TRANSLATE_U:
            return LOC_DP, 0
        if operation == NifClasses.TransformMember.TT_TRANSLATE_V:
            return LOC_DP, 1
        if operation == NifClasses.TransformMember.TT_SCALE_U:
            return SCALE_DP, 0
        if operation == NifClasses.TransformMember.TT_SCALE_V:
            return SCALE_DP, 1
        if operation == NifClasses.TransformMember.TT_ROTATE:
            NifLog.warn("Rotation in Texture Transform is not supported")
            return None, None
        NifLog.warn(f"Unsupported texture transform operation {operation}")
        return None, None

    @staticmethod
    def get_shader_socket_path(b_material, socket_name):
        """Return the data path of a shader node group socket, so animation drives what
        is actually rendered. Returns None when the material has no shader group."""

        b_group_node = get_shader_group_node(b_material)
        if b_group_node is None:
            return None
        b_socket = b_group_node.inputs.get(socket_name)
        if b_socket is None:
            return None
        index = list(b_group_node.inputs).index(b_socket)
        return f'nodes["{b_group_node.name}"].inputs[{index}].default_value'

    def import_float_controller(self, b_material, n_ctrl, socket_name, description):
        """Import a controller that animates a single float on the shader node group."""

        n_ctrl_data = self.get_controller_data(n_ctrl)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The {description} of '{b_material.name}' holds no keys, so it is skipped")
            return

        data_path = self.get_shader_socket_path(b_material, socket_name)
        if data_path is None:
            NifLog.warn(f"Cannot import the {description} of '{b_material.name}': "
                        f"its material has no '{socket_name}' shader input")
            return

        NifLog.info(f"Importing {description}")
        b_mat_action = self.create_action(b_material.node_tree, f"{b_material.name}-MaterialNodesAction")
        interp = self.get_b_interp_from_n_interp(n_ctrl_data.interpolation)
        times, keys = self.get_keys_values(n_ctrl_data.keys)
        tangents = self.get_nif_tangents(
            n_ctrl_data.keys, n_ctrl_data.interpolation)
        self.add_keys(
            b_material.node_tree, b_mat_action, data_path, (0,), n_ctrl.flags,
            times, keys, interp, tangents=tangents)
        self.set_max_key_time()

    def import_material_alpha_controller(self, b_material, n_material):
        # find alpha controller
        n_ctrl = math.find_controller(n_material, NifClasses.NiAlphaController)
        if not n_ctrl:
            return
        self.import_float_controller(b_material, n_ctrl, "Alpha", "alpha controller")

    def import_emissive_mult_controller(self, b_material, n_material):
        """Import a BSMaterialEmittanceMultController, which makes things glow brighter
        or dimmer over time."""

        n_ctrl = math.find_controller(n_material, NifClasses.BSMaterialEmittanceMultController)
        if not n_ctrl:
            return
        self.import_float_controller(b_material, n_ctrl, "Emissive Mult", "emissive mult controller")

    def import_shader_float_controllers(self, b_material, n_geom):
        """Import float controllers attached to a Bethesda shader property."""

        n_shader = math.find_property(n_geom, NifClasses.BSShaderPPLightingProperty)
        if n_shader is None:
            return

        for controller_type in (
                "BSRefractionStrengthController",
                "BSRefractionFirePeriodController",
        ):
            n_controller_class = getattr(NifClasses, controller_type)
            n_controller = math.find_controller(n_shader, n_controller_class)
            if n_controller is None:
                continue
            socket_name, description = self.FLOAT_CONTROLLER_SOCKETS[controller_type]
            self.import_float_controller(
                b_material, n_controller, socket_name, description)

    def import_material_color_controller(self, b_material, n_material, b_channel, n_target_color):
        # find material color controller with matching target color
        for n_ctrl in n_material.get_controllers():
            if isinstance(n_ctrl, NifClasses.NiMaterialColorController):
                if n_ctrl.get_target_color() == n_target_color:
                    break
        else:
            return

        n_ctrl_data = self.get_controller_data(n_ctrl)
        if not (n_ctrl_data and getattr(n_ctrl_data, "keys", None)):
            NifLog.info(f"The material color controller of '{b_material.name}' holds no keys, so it is skipped")
            return

        times, keys = self.get_keys_values(n_ctrl_data.keys)
        interp = self.get_b_interp_from_n_interp(n_ctrl_data.interpolation)
        tangents = self.get_nif_tangents(
            n_ctrl_data.keys, n_ctrl_data.interpolation)

        # the emissive colour is what the shader actually renders, so animate the node
        # group socket. The others only exist on the material property
        if n_target_color == NifClasses.MaterialColor.TC_SELF_ILLUM:
            data_path = self.get_shader_socket_path(b_material, "Emissive Color")
            if data_path is not None:
                NifLog.info("Importing material colour controller for the emissive colour")
                b_action = self.create_action(b_material.node_tree, f"{b_material.name}-MaterialNodesAction")
                self.add_keys(
                    b_material.node_tree, b_action, data_path, range(3),
                    n_ctrl.flags, times, keys, interp, tangents=tangents)
                self.set_max_key_time()
                return

        NifLog.info(
            f"Importing material color controller for target color {n_target_color} into blender channel {b_channel}")
        b_mat_action = self.create_action(b_material, "MaterialAction")
        self.add_keys(
            b_material, b_mat_action, b_channel, range(3), n_ctrl.flags,
            times, keys, interp, tangents=tangents)

    def import_uv_controller(self, b_material, n_geom):
        """Import UV controller data as a mapping node with animated values."""
        # search for the block
        n_ctrl = math.find_controller(n_geom, NifClasses.NiUVController)
        if not n_ctrl:
            return
        NifLog.info("Importing UV controller")

        n_ctrl_data = self.get_controller_data(n_ctrl)
        if not (n_ctrl_data and getattr(n_ctrl_data, "uv_groups", None)):
            NifLog.info(f"The UV controller of '{b_material.name}' holds no keys, so it is skipped")
            return
        if not any(n_uvgroup.keys for n_uvgroup in n_ctrl_data.uv_groups):
            return

        b_mat_action, transform = self.insert_mapping_node(b_material)

        # loc U, loc V, scale U, scale V
        dtypes = (LOC_DP, 0), (LOC_DP, 1), (SCALE_DP, 0), (SCALE_DP, 1)
        for n_uvgroup, (data_path, array_ind) in zip(n_ctrl.data.uv_groups, dtypes):
            if n_uvgroup.keys:
                interp = self.get_b_interp_from_n_interp(n_uvgroup.interpolation)
                times, keys = self.get_keys_values(n_uvgroup.keys)
                tangents = self.get_nif_tangents(
                    n_uvgroup.keys, n_uvgroup.interpolation)
                # Show the texture moving as it does in-game. U needs the motion
                # inversion. For V it cancels Blender's coordinate-axis inversion.
                if data_path == LOC_DP and array_ind == 0:
                    keys, tangents = self.scale_key_data(
                        keys, tangents, -1)
                self.add_keys(b_material.node_tree, b_mat_action,
                              f'nodes["{transform.name}"].inputs[{data_path}].default_value',
                              (array_ind,), n_ctrl.flags, times, keys, interp,
                              tangents=tangents)
                self.set_max_key_time()

    def import_tex_transform_controller(self, b_material, n_geom):
        """Import UV controller data as a mapping node with animated values."""
        # search for the block
        n_tex_prop = math.find_property(n_geom, NifClasses.NiTexturingProperty)
        if not n_tex_prop:
            return
        for n_ctrl in math.controllers_iter(n_tex_prop, NifClasses.NiTextureTransformController):
            if isinstance(n_ctrl.interpolator, NifClasses.NiBlendInterpolator):
                # its keys live in the controller sequences, which are imported separately
                NifLog.debug("Texture transform controller is driven by the controller sequences")
                continue

            NifLog.info("Importing Texture Transform controller")

            n_ctrl_data = self.get_controller_data(n_ctrl)
            if not n_ctrl_data or not hasattr(n_ctrl_data, "keys") or not n_ctrl_data.keys:
                NifLog.warn(f"Texture Transform Controller has no valid key data: {n_ctrl}. Skipping...")
                continue

            tex_slot = n_ctrl.texture_slot
            times, keys = self.get_keys_values(n_ctrl_data.keys)
            tangents = self.get_nif_tangents(
                n_ctrl_data.keys, n_ctrl_data.interpolation)
            operation = n_ctrl.operation
            if operation == NifClasses.TransformMember.TT_TRANSLATE_U:
                data_path = LOC_DP
                array_ind = 0
                keys, tangents = self.scale_key_data(
                    keys, tangents, -1)
            elif operation == NifClasses.TransformMember.TT_TRANSLATE_V:
                data_path = LOC_DP
                array_ind = 1
            elif operation == NifClasses.TransformMember.TT_ROTATE:
                NifLog.warn("Rotation in Texture Transform is not supported")
                continue
            elif operation == NifClasses.TransformMember.TT_SCALE_U:
                data_path = SCALE_DP
                array_ind = 0
            elif operation == NifClasses.TransformMember.TT_SCALE_V:
                data_path = SCALE_DP
                array_ind = 1

            b_mat_action, transform = self.insert_mapping_node(b_material)
            interp = self.get_b_interp_from_n_interp(n_ctrl_data.interpolation)
            self.add_keys(
                b_material.node_tree,
                b_mat_action,
                f'nodes["{transform.name}"].inputs[{data_path}].default_value',
                (array_ind,),
                n_ctrl.flags,
                times,
                keys,
                interp,
                tangents=tangents,
            )

    def insert_mapping_node(self, b_material, sequence_name=None):
        b_mat_action = self.create_action(
            b_material.node_tree,
            f"{b_material.name}-MaterialNodesAction",
            sequence_name,
        )
        tree = b_material.node_tree
        # reuse mapping node if one had been added before
        for node in tree.nodes:
            if node.type == "MAPPING":
                return b_mat_action, node
        transform = tree.nodes.new(MAPPING)
        # get previous links
        used_links = []
        for link in tree.links:
            # get uv nodes
            if link.from_node.type == "UVMAP":
                used_links.append(link)
        # link the node between previous uv node and texture node
        for link in used_links:
            from_socket = link.from_socket
            to_socket = link.to_socket
            tree.links.remove(link)
            tree.links.new(from_socket, transform.inputs[0])
            tree.links.new(transform.outputs[0], to_socket)
        return b_mat_action, transform
