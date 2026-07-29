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

from math import atan, radians

import bpy
import mathutils
from ....modules.nif_import.animation import Animation
from ....modules.nif_import.object import Object
from ....utils import math
from ....utils.flags import to_signed_32
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses

# Rotation channels that need the aim correction folding in, and how many curves each has
AIMED_ROTATION_CHANNELS = {'rotation_quaternion': 4, 'rotation_euler': 3}

# NiLight subclasses mapped to the Blender light they are imported as.
# Blender's ambient light is a world setting rather than an object so NiAmbientLight is imported as a weak sun
LIGHT_TYPES = {
    NifClasses.NiSpotLight: 'SPOT',
    NifClasses.NiPointLight: 'POINT',
    NifClasses.NiDirectionalLight: 'SUN',
    NifClasses.NiAmbientLight: 'SUN',
}


def get_light_type(n_block):
    """The Blender light type for a NiLight block, most derived class first."""

    for n_light_type, b_light_type in LIGHT_TYPES.items():
        if isinstance(n_block, n_light_type):
            return b_light_type
    return None


def import_frustum(n_camera, b_camera_data):
    """Set up a Blender camera from a NiCamera's frustum.

    Blender describes a frustum as a field of view plus a lens shift, always symmetric
    around the shifted axis, where the nif gives the four edges at the near plane. Every
    frustum that can be expressed one way can be expressed the other.
    """

    width = n_camera.frustum_right - n_camera.frustum_left
    height = n_camera.frustum_top - n_camera.frustum_bottom
    if width <= 0 or height <= 0:
        NifLog.warn(f"NiCamera '{n_camera.name}' has an empty frustum "
                    f"({width:g} x {height:g}), using Blender's defaults.")
        return

    b_camera_data.type = 'ORTHO' if n_camera.use_orthographic_projection else 'PERSP'
    b_camera_data.clip_start = n_camera.frustum_near
    b_camera_data.clip_end = n_camera.frustum_far

    if b_camera_data.type == 'ORTHO':
        # an orthographic frustum has no angle. Its size is the near plane rectangle itself
        b_camera_data.ortho_scale = max(width, height)
    else:
        b_camera_data.sensor_fit = 'HORIZONTAL' if width >= height else 'VERTICAL'
        b_camera_data.angle = 2.0 * atan(max(width, height) / (2.0 * n_camera.frustum_near))

    # shift is measured in units of the larger frustum dimension, matching sensor_fit
    largest = max(width, height)
    b_camera_data.shift_x = (n_camera.frustum_right + n_camera.frustum_left) / (2.0 * largest)
    b_camera_data.shift_y = (n_camera.frustum_top + n_camera.frustum_bottom) / (2.0 * largest)


def import_spot_angles(n_spot_light, b_light_data):
    """Set a Blender spot cone from a NiSpotLight's angles.

    The nif stores the outer angle as the full cone in degrees, which is what NifSkope
    shows and what Blender's spot_size means, so the only conversion is to radians. The
    inner angle only exists from 20.2.0.5 on and becomes the blend fraction.
    """

    outer = radians(n_spot_light.outer_spot_angle)
    b_light_data.spot_size = outer

    inner = radians(getattr(n_spot_light, "inner_spot_angle", 0.0))
    b_light_data.spot_blend = min(max((outer - inner) / outer, 0.0), 1.0) if outer else 0.0


class NiTypes:

    @staticmethod
    def import_root_collision(n_node, b_obj):
        """ Import a RootCollisionNode, which is usually attached to a root node and holds a NiTriShape"""
        if isinstance(n_node, NifClasses.RootCollisionNode):
            b_obj["type"] = "RootCollisionNode"
            b_obj.name = "RootCollisionNode"
            b_obj.nif_object.flags = to_signed_32(n_node.flags)
            for b_child in b_obj.children:
                b_child.display_type = 'WIRE'

    @staticmethod
    def import_range_lod_data(n_node, b_obj, b_children):
        """Import the distance range each child of a NiLODNode is the visible level over."""

        if not isinstance(n_node, NifClasses.NiLODNode):
            return

        # up to 10.0.1.0 the levels sit on the node itself, after that on a NiRangeLODData
        n_range_data = n_node
        if not n_range_data.lod_levels:
            n_range_data = n_node.lod_level_data
        if n_range_data is None or not getattr(n_range_data, "lod_levels", None):
            return

        if len(n_range_data.lod_levels) != len(b_children):
            NifLog.warn(f"LOD node '{n_node.name}' has {len(n_range_data.lod_levels)} levels "
                        f"but {len(b_children)} children were imported, so the ranges were "
                        f"matched only as far as they go.")

        # the children are taken in import order rather than from b_obj.children, whose
        # order does not match the nif's
        for n_lod_level, b_child in zip(n_range_data.lod_levels, b_children):
            b_child.nif_object.lod_level.near_extent = n_lod_level.near_extent
            b_child.nif_object.lod_level.far_extent = n_lod_level.far_extent

    @staticmethod
    def import_multi_bound(n_node):
        """Import a BSMultiBoundNode's bound as a helper empty, to be parented to the node.

        The bound becomes a transform rather than a set of numbers in a panel, so it can be
        seen and dragged in the viewport: location is the centre, scale the extent or radius,
        and rotation the box rotation of an oriented box.
        """

        if not isinstance(n_node, NifClasses.BSMultiBoundNode):
            return None

        n_multi_bound = n_node.multi_bound
        n_bound_data = n_multi_bound.data if n_multi_bound else None
        if n_bound_data is None:
            return None

        if isinstance(n_bound_data, NifClasses.BSMultiBoundAABB):
            b_location = mathutils.Vector(n_bound_data.position.as_list())
            b_scale = mathutils.Vector(n_bound_data.extent.as_list())
            b_rotation = mathutils.Quaternion()
            b_display = 'CUBE'
        elif isinstance(n_bound_data, NifClasses.BSMultiBoundOBB):
            b_location = mathutils.Vector(n_bound_data.center.as_list())
            b_scale = mathutils.Vector(n_bound_data.size.as_list())
            b_rotation = mathutils.Matrix(n_bound_data.rotation.as_list()).to_quaternion()
            b_display = 'CUBE'
        elif isinstance(n_bound_data, NifClasses.BSMultiBoundSphere):
            b_location = mathutils.Vector(n_bound_data.center.as_list())
            b_scale = mathutils.Vector((n_bound_data.radius,) * 3)
            b_rotation = mathutils.Quaternion()
            b_display = 'SPHERE'
        else:
            NifLog.warn(f"Unsupported multi bound type "
                        f"'{type(n_bound_data).__name__}' on '{n_node.name}', skipped.")
            return None

        b_obj = Object.create_b_obj(None, None, name=f"{n_node.name} MultiBound")
        b_obj.empty_display_type = b_display
        b_obj.empty_display_size = 1.0
        b_obj.matrix_local = mathutils.Matrix.LocRotScale(b_location, b_rotation, b_scale)

        nif_multi_bound = b_obj.nif_object.node_multi_bound
        nif_multi_bound.is_bound_helper = True
        nif_multi_bound.bound_type = type(n_bound_data).__name__

        return b_obj

    @staticmethod
    def get_billboard_orientation_helper():
        """Return the shared, non-scene object that carries the viewport orientation."""

        b_helper = next((
            obj for obj in bpy.data.objects
            if obj.get("niftools_billboard_orientation_helper")
        ), None)
        if b_helper is None:
            # COPY_ROTATION still evaluates an unlinked target. Keeping this helper out of
            # every collection avoids adding a dummy camera (or any visible helper object)
            # to the imported scene.
            b_helper = bpy.data.objects.new("NIF Viewport Billboard Orientation", None)
            b_helper["niftools_billboard_orientation_helper"] = True
            b_helper.rotation_mode = 'QUATERNION'
        return b_helper

    @staticmethod
    def add_billboard_constraint(b_obj):
        """Constrain an ordinary NiBillboardNode to the working viewport orientation."""

        b_helper = NiTypes.get_billboard_orientation_helper()
        constr = b_obj.constraints.new('COPY_ROTATION')
        constr.name = "NIF Billboard"
        constr.target = b_helper
        constr.owner_space = 'WORLD'
        constr.target_space = 'WORLD'
        constr.mix_mode = 'REPLACE'
        return constr

    @staticmethod
    def import_billboard(n_node, b_obj):
        """Import a NiBillboardNode."""

        if isinstance(n_node, NifClasses.NiBillboardNode) and not isinstance(b_obj, bpy.types.Bone):
            NiTypes.add_billboard_constraint(b_obj)

    @staticmethod
    def import_empty(n_block):
        """Creates and returns a grouping empty."""
        b_empty = Object.create_b_obj(n_block, None)
        return b_empty

    @staticmethod
    def correct_aimed_animation(b_obj):
        """Fold the aim correction into an aimed object's imported rotation keys.

        The rest transform gets the correction when the object is created, but keyframes are
        read straight out of the nif, so without this a camera or spot light snaps back to
        the nif's own forward axis the moment its animation plays.
        """

        b_action = getattr(b_obj.animation_data, "action", None)
        if not b_action:
            return

        correction = math.get_aim_correction().to_quaternion()

        channels = {}
        for b_fcurve in Animation.get_fcurves_from_action(b_action):
            if b_fcurve.data_path in AIMED_ROTATION_CHANNELS:
                channels.setdefault(b_fcurve.data_path, {})[b_fcurve.array_index] = b_fcurve

        for data_path, b_indexed_curves in channels.items():
            dimension = AIMED_ROTATION_CHANNELS[data_path]
            b_fcurves = [b_indexed_curves.get(index) for index in range(dimension)]
            if any(b_fcurve is None for b_fcurve in b_fcurves):
                NifLog.warn(f"'{b_obj.name}' has an incomplete {data_path} animation, so its "
                            f"orientation was left uncorrected.")
                continue

            key_counts = {len(b_fcurve.keyframe_points) for b_fcurve in b_fcurves}
            if len(key_counts) != 1:
                NifLog.warn(f"'{b_obj.name}' has mismatched {data_path} key counts, so its "
                            f"orientation was left uncorrected.")
                continue

            b_previous_euler = None
            for key_index in range(key_counts.pop()):
                values = [b_fcurve.keyframe_points[key_index].co[1] for b_fcurve in b_fcurves]
                if data_path == 'rotation_quaternion':
                    corrected = mathutils.Quaternion(values) @ correction
                else:
                    corrected = (mathutils.Euler(values).to_quaternion() @ correction).to_euler()
                    if b_previous_euler:
                        # keep the curve continuous rather than letting it flip by a turn
                        corrected.make_compatible(b_previous_euler)
                    b_previous_euler = corrected

                for b_fcurve, value in zip(b_fcurves, corrected):
                    b_keyframe = b_fcurve.keyframe_points[key_index]
                    # move the handles with the key so the interpolation shape is kept
                    offset = value - b_keyframe.co[1]
                    b_keyframe.co[1] = value
                    b_keyframe.handle_left[1] += offset
                    b_keyframe.handle_right[1] += offset

            for b_fcurve in b_fcurves:
                b_fcurve.update()

    @staticmethod
    def import_camera(n_block):
        """Import a NiCamera as a Blender camera object."""

        b_camera_data = bpy.data.cameras.new(n_block.name or "NiCamera")
        b_obj = Object.create_b_obj(n_block, b_camera_data)
        b_obj.matrix_local = math.import_aimed_matrix(n_block)

        import_frustum(n_block, b_camera_data)

        nif_camera = b_camera_data.nif_camera
        # camera flags and the orthographic bool only exist from 10.1.0.0 on
        nif_camera.camera_flags = getattr(n_block, "camera_flags", 0)
        nif_camera.lod_adjust = n_block.lod_adjust
        nif_camera.viewport_left = n_block.viewport_left
        nif_camera.viewport_right = n_block.viewport_right
        nif_camera.viewport_top = n_block.viewport_top
        nif_camera.viewport_bottom = n_block.viewport_bottom

        return b_obj

    @staticmethod
    def import_light(n_block):
        """Import a NiLight subclass as a Blender light object."""

        b_light_type = get_light_type(n_block)
        if b_light_type is None:
            return None

        b_light_data = bpy.data.lights.new(n_block.name or type(n_block).__name__, b_light_type)
        b_obj = Object.create_b_obj(n_block, b_light_data)
        # only aimed lights have a meaningful orientation, but applying the correction to a
        # point light too keeps its transform identical on the way back out
        b_obj.matrix_local = math.import_aimed_matrix(n_block)

        # the diffuse colour is the one Blender genuinely has, so it drives the light itself
        math.color_nif_to_blender(n_block.diffuse_color, b_light_data.color)

        nif_light = b_light_data.nif_light
        nif_light.ambient_color = (n_block.ambient_color.r,
                                   n_block.ambient_color.g,
                                   n_block.ambient_color.b)
        nif_light.specular_color = (n_block.specular_color.r,
                                    n_block.specular_color.g,
                                    n_block.specular_color.b)
        # switch_state only exists from 10.1.0.106 up to FO4
        nif_light.switch_state = bool(getattr(n_block, "switch_state", True))
        # assigning dimmer last drives the update that sets the Blender power
        nif_light.dimmer = n_block.dimmer

        if isinstance(n_block, NifClasses.NiPointLight):
            nif_light.constant_attenuation = n_block.constant_attenuation
            nif_light.linear_attenuation = n_block.linear_attenuation
            nif_light.quadratic_attenuation = n_block.quadratic_attenuation

        if isinstance(n_block, NifClasses.NiSpotLight):
            import_spot_angles(n_block, b_light_data)
            nif_light.exponent = n_block.exponent

        if b_light_type == 'SUN':
            nif_light.sun_block_type = type(n_block).__name__
            if isinstance(n_block, NifClasses.NiAmbientLight):
                NifLog.warn(f"Blender has no ambient light object, so '{n_block.name}' was "
                            f"imported as a sun. It still exports as a NiAmbientLight.")

        return b_obj
