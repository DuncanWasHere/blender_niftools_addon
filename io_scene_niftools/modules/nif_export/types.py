"""This module contains helper methods to import/export object type data."""

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
from math import degrees, tan

import bpy

from ...modules.nif_export.block_registry import block_store
from ...utils import math
from ...utils.logging import NifLog, NifError
from ...utils.serialization import dict_to_block
from nifgen.formats.nif import classes as NifClasses

# Blender light types mapped to the nif block they are written as. A sun can be either of
# the nif's two undirected lights, so it reads the choice off the light's own properties.
LIGHT_BLOCK_TYPES = {
    'POINT': "NiPointLight",
    'SPOT': "NiSpotLight",
    'AREA': "NiPointLight",
}


def create_ninode(b_obj=None, n_node_type=None):
    """Essentially a wrapper around create_block() that creates nodes of the right type."""
    # when no b_obj is passed, use the passed n_node_type
    if not b_obj:
        if n_node_type is None:
            n_node_type = "NiNode"
    # get node type - some are stored as custom property of the b_obj
    else:
        # let n_node_type overwrite the detected node type
        if n_node_type is None:
            try:
                n_node_type = b_obj.nif_object.nodetype
            except AttributeError:
                n_node_type = "NiNode"

            # ...others by presence of constraints
            if has_track(b_obj):
                n_node_type = "NiBillboardNode"

    # now create the node
    n_node = block_store.create_block(n_node_type, b_obj)

    # customize the node data, depending on type
    if n_node_type == "BSMasterParticleSystem" and hasattr(b_obj, "nif_master_particle_system"):
        # the particle system list itself is filled in as the child systems are exported
        n_node.max_emitter_objects = b_obj.nif_master_particle_system.max_emitter_objects

    if b_obj is not None:
        export_node_subtype_data(b_obj, n_node)

    return n_node


def export_node_subtype_data(b_obj, n_node):
    """Export the fields a node subtype adds on top of NiNode.

    Each check is its own `if`, because these are independent inheritance branches - a
    NiLODNode is also a NiSwitchNode and has to write both sets of fields.
    """

    nif_object = getattr(b_obj, "nif_object", None)
    if nif_object is None:
        return

    if isinstance(n_node, NifClasses.BSRangeNode):
        n_node.min = nif_object.node_range.min
        n_node.max = nif_object.node_range.max
        n_node.current = nif_object.node_range.current

    if isinstance(n_node, NifClasses.BSValueNode):
        n_node.value = nif_object.node_value.value
        n_node.value_node_flags = NifClasses.BSValueNodeFlags.from_value(
            nif_object.node_value.value_node_flags)

    if isinstance(n_node, NifClasses.BSOrderedNode):
        n_node.alpha_sort_bound = NifClasses.Vector4.from_value(
            list(nif_object.node_ordered.alpha_sort_bound))
        n_node.static_bound = nif_object.node_ordered.static_bound

    if isinstance(n_node, NifClasses.NiSwitchNode):
        n_node.index = nif_object.node_switch.index
        # switch flags only exist from 10.1.0.0 on
        if hasattr(n_node, "switch_node_flags"):
            n_node.switch_node_flags = NifClasses.NiSwitchFlags.from_value(
                nif_object.node_switch.switch_node_flags)

    if isinstance(n_node, NifClasses.NiSortAdjustNode):
        n_node.sorting_mode = NifClasses.SortingMode[nif_object.node_sort_adjust.sorting_mode]

    if isinstance(n_node, NifClasses.BSMultiBoundNode):
        # culling mode was only added for Skyrim
        if hasattr(n_node, "culling_mode"):
            n_node.culling_mode = NifClasses.BSCPCullingType[nif_object.node_multi_bound.culling_mode]


def export_frustum(b_camera_data, n_camera):
    """Fill a NiCamera's frustum from a Blender camera; the inverse of import_frustum."""

    n_camera.use_orthographic_projection = (b_camera_data.type == 'ORTHO')
    n_camera.frustum_near = b_camera_data.clip_start
    n_camera.frustum_far = b_camera_data.clip_end

    render = bpy.context.scene.render
    aspect = ((render.resolution_x * render.pixel_aspect_x) /
              (render.resolution_y * render.pixel_aspect_y))

    if b_camera_data.type == 'ORTHO':
        largest = b_camera_data.ortho_scale
    else:
        largest = 2.0 * b_camera_data.clip_start * tan(b_camera_data.angle / 2.0)

    # sensor_fit decides which frustum dimension the angle and the shift refer to
    fit = b_camera_data.sensor_fit
    if fit == 'AUTO':
        fit = 'HORIZONTAL' if aspect >= 1.0 else 'VERTICAL'
    if fit == 'HORIZONTAL':
        width, height = largest, largest / aspect
    else:
        width, height = largest * aspect, largest

    shift_x = b_camera_data.shift_x * largest
    shift_y = b_camera_data.shift_y * largest
    n_camera.frustum_left = shift_x - width / 2.0
    n_camera.frustum_right = shift_x + width / 2.0
    n_camera.frustum_bottom = shift_y - height / 2.0
    n_camera.frustum_top = shift_y + height / 2.0


def export_spot_angles(b_light_data, n_spot_light):
    """Fill a NiSpotLight's angles from a Blender spot cone; the inverse of import_spot_angles."""

    outer = b_light_data.spot_size
    n_spot_light.outer_spot_angle = degrees(outer)
    if hasattr(n_spot_light, "inner_spot_angle"):
        n_spot_light.inner_spot_angle = degrees(outer * (1.0 - b_light_data.spot_blend))


def create_camera(b_obj):
    """Create a NiCamera block from a Blender camera object."""

    n_camera = block_store.create_block("NiCamera", b_obj)
    b_camera_data = b_obj.data

    # the frustum comes off the Blender camera itself, so an ordinary camera exports right
    export_frustum(b_camera_data, n_camera)

    nif_camera = b_camera_data.nif_camera
    # camera flags and the orthographic bool were only added in 10.1.0.0
    if hasattr(n_camera, "camera_flags"):
        n_camera.camera_flags = nif_camera.camera_flags
    n_camera.lod_adjust = nif_camera.lod_adjust
    n_camera.viewport_left = nif_camera.viewport_left
    n_camera.viewport_right = nif_camera.viewport_right
    n_camera.viewport_top = nif_camera.viewport_top
    n_camera.viewport_bottom = nif_camera.viewport_bottom

    return n_camera


def create_light(b_obj):
    """Create a NiLight subclass block from a Blender light object."""

    b_light_data = b_obj.data
    nif_light = b_light_data.nif_light

    if b_light_data.type == 'SUN':
        n_block_type = nif_light.sun_block_type
    else:
        n_block_type = LIGHT_BLOCK_TYPES.get(b_light_data.type)
        if n_block_type is None:
            NifLog.warn(f"Light '{b_obj.name}' is of unsupported type "
                        f"'{b_light_data.type}' and was skipped.")
            return None
        if b_light_data.type == 'AREA':
            NifLog.warn(f"The nif format has no area light, so '{b_obj.name}' was exported "
                        f"as a NiPointLight.")

    n_light = block_store.create_block(n_block_type, b_obj)

    n_light.dimmer = nif_light.dimmer
    math.color_blender_to_nif(n_light.diffuse_color, b_light_data.color)
    math.color_blender_to_nif(n_light.ambient_color, nif_light.ambient_color)
    math.color_blender_to_nif(n_light.specular_color, nif_light.specular_color)
    # switch_state runs from 10.1.0.106 up to Fallout 4 only
    if hasattr(n_light, "switch_state"):
        n_light.switch_state = nif_light.switch_state

    if isinstance(n_light, NifClasses.NiPointLight):
        n_light.constant_attenuation = nif_light.constant_attenuation
        n_light.linear_attenuation = nif_light.linear_attenuation
        n_light.quadratic_attenuation = nif_light.quadratic_attenuation

    if isinstance(n_light, NifClasses.NiSpotLight):
        export_spot_angles(b_light_data, n_light)
        n_light.exponent = nif_light.exponent

    return n_light


def is_skeleton(b_root_objects):
    """
    Whether this export is a standalone skeleton rather than an ordinary nif.

    Marked the same way the importer recognises one: a SkeletonID on an armature root. An
    armature on its own does not make a skeleton, since a skinned mesh carries a flat
    armature of the bones it uses and that is not a skeleton.
    """

    return any(b_obj.type == 'ARMATURE' and b_obj.data.nif_armature.skeleton_id
               for b_obj in b_root_objects)


def is_skinned(b_obj):
    """
    Determine whether this b_obj is exported with a skin instance.

    This is the same condition the skinned geometry exporter applies: the object hangs off an
    armature, and at least one of its vertex groups is named after a bone of that armature.
    """

    if not b_obj or not b_obj.parent or b_obj.parent.type != 'ARMATURE':
        return False

    b_vertex_groups = {b_vertex_group.name for b_vertex_group in b_obj.vertex_groups}
    return bool(b_vertex_groups & set(b_obj.parent.data.bones.keys()))


def has_track(b_obj):
    """Determine if this b_obj has a track_to constraint."""
    # bones do not have constraints
    if not isinstance(b_obj, bpy.types.Bone):
        for constr in b_obj.constraints:
            if constr.type == 'TRACK_TO':
                return True


def export_lod_data(n_node, b_obj, b_children):
    """
    Export a NiLODNode's switching data, once its children are known.

    b_children must be the children that were actually exported, in the order they were
    added to n_node, since a LOD level is matched to a child by position.
    """

    nif_object = getattr(b_obj, "nif_object", None)
    if nif_object is None:
        return

    if nif_object.node_lod.lod_type == 'NiScreenLODData':
        export_screen_lod_data(n_node, b_obj, nif_object)
        return

    export_range_lod_data(n_node, b_obj, b_children, nif_object)


def export_range_lod_data(n_node, b_obj, b_children, nif_object):
    """Export the per child distance ranges, as a NiRangeLODData block on n_node."""

    n_range_data = block_store.create_block("NiRangeLODData", b_obj)
    n_node.lod_level_data = n_range_data

    n_center = nif_object.node_lod.lod_center
    n_range_data.lod_center.x, n_range_data.lod_center.y, n_range_data.lod_center.z = n_center
    # up to 10.0.1.0 the node carries a centre of its own as well
    if hasattr(n_node, "lod_center"):
        n_node.lod_center.x, n_node.lod_center.y, n_node.lod_center.z = n_center

    # The levels live on the node up to 10.0.1.0 and on the data block after that. Both are
    # filled independently rather than in one zip, because the array the version does not
    # write stays zero length however large num_lod_levels is set, and zipping the two
    # together would then silently write nothing at all.
    b_extents = [(b_child.nif_object.lod_level.near_extent,
                  b_child.nif_object.lod_level.far_extent) for b_child in b_children]

    for n_levels_owner in (n_node, n_range_data):
        n_levels_owner.num_lod_levels = len(b_extents)
        n_levels_owner.reset_field("lod_levels")
        for n_lod_level, (b_near, b_far) in zip(n_levels_owner.lod_levels, b_extents):
            n_lod_level.near_extent = b_near
            n_lod_level.far_extent = b_far


def export_screen_lod_data(n_node, b_obj, nif_object):
    """Rebuild a NiScreenLODData block from the snapshot taken on import."""

    snapshot = nif_object.node_lod.screen_lod_data
    if not snapshot:
        NifLog.warn(f"'{b_obj.name}' is set to screen LOD but carries no screen LOD data, "
                    f"so it was exported without any.")
        return

    try:
        entry = json.loads(snapshot)
    except json.JSONDecodeError as exception:
        NifLog.warn(f"'{b_obj.name}' has unreadable screen LOD data ({exception}), "
                    f"so it was exported without any.")
        return

    n_node.lod_level_data = dict_to_block(entry, lambda n_type: block_store.create_block(n_type, b_obj))


def get_multi_bound_helper(b_obj):
    """The child object holding a BSMultiBoundNode's bound, if it has one."""

    return next((b_child for b_child in b_obj.children
                 if b_child.nif_object.node_multi_bound.is_bound_helper), None)


def export_multi_bound(b_obj, n_node):
    """
    Export a BSMultiBoundNode's bound from its helper child object.

    The helper's transform is the bound: its location is the centre, its scale the extent
    or radius, and for an oriented box its rotation is the box rotation.
    """

    if not isinstance(n_node, NifClasses.BSMultiBoundNode):
        return

    b_helper = get_multi_bound_helper(b_obj)
    if b_helper is None:
        return

    b_bound_type = b_helper.nif_object.node_multi_bound.bound_type
    n_multi_bound = block_store.create_block("BSMultiBound", b_obj)
    n_bound_data = block_store.create_block(b_bound_type, b_helper)
    n_multi_bound.data = n_bound_data
    n_node.multi_bound = n_multi_bound

    b_matrix = math.get_object_bind(b_helper)
    b_translation = b_matrix.to_translation()
    b_scale = b_matrix.to_scale()

    if b_bound_type == 'BSMultiBoundAABB':
        n_bound_data.position.x, n_bound_data.position.y, n_bound_data.position.z = b_translation
        n_bound_data.extent.x, n_bound_data.extent.y, n_bound_data.extent.z = b_scale

    elif b_bound_type == 'BSMultiBoundOBB':
        n_bound_data.center.x, n_bound_data.center.y, n_bound_data.center.z = b_translation
        n_bound_data.size.x, n_bound_data.size.y, n_bound_data.size.z = b_scale
        b_rotation = b_matrix.to_3x3().normalized()
        for row_index in range(3):
            for col_index in range(3):
                setattr(n_bound_data.rotation, f"m_{row_index + 1}{col_index + 1}",
                        b_rotation[row_index][col_index])

    else:
        n_bound_data.center.x, n_bound_data.center.y, n_bound_data.center.z = b_translation
        # a sphere has one radius, so a non-uniformly scaled helper has to lose something
        n_bound_data.radius = max(b_scale)
        if max(b_scale) - min(b_scale) > 1e-4:
            NifLog.warn(f"Multi bound '{b_helper.name}' is a sphere but is scaled unevenly, "
                        f"so its largest axis was used as the radius.")


def export_furniture_marker(n_root, filebase):
    # Oblivion and Fallout 3 furniture markers
    if bpy.context.scene.niftools_scene.is_bs() and filebase[:15].lower() == 'furnituremarker':
        # exporting a furniture marker for Oblivion/FO3
        try:
            furniturenumber = int(filebase[15:])
        except ValueError:
            raise NifError(f"Furniture marker has invalid number ({filebase[15:]}).\n"
                                                           f"Name your file 'furnituremarkerxx.nif' where xx is a number between 00 and 19.")

        # create furniture marker block
        furnmark = block_store.create_block("BSFurnitureMarker")
        furnmark.name = "FRN"
        furnmark.num_positions = 1
        furnmark.reset_field("positions")
        furnmark.positions[0].position_ref_1 = furniturenumber
        furnmark.positions[0].position_ref_2 = furniturenumber

        # add extra blocks
        n_root.add_extra_data(furnmark)
