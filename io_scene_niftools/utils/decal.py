"""Viewport helpers for BSDecalPlacementVectorExtraData."""

import math
import re

import bpy
import mathutils

from ..utils.particles import blender_to_nif_units, nif_to_blender_units


NORMAL_AXIS = mathutils.Vector((0.0, 0.0, 1.0))
NORMAL_EPSILON = 1.0e-8

# vector numbers repeat across groups, so Blender adds a .001 suffix to the later ones
GROUP_NAME = re.compile(r"DecalPlacementVectorGroup(\d+)(\.\d+)?$")
VECTOR_NAME = re.compile(r"DecalPlacementVector(\d+)(\.\d+)?$")

# max distance in nif units between a reference node and the vector it is matched to
MATCH_DISTANCE = 0.5


def is_decal_helper(b_obj):
    """Whether an object is a decal vector handle."""

    return bool(b_obj and getattr(b_obj, "nif_object", None)
                and b_obj.nif_object.is_decal_placement_helper)


def normal_rotation(normal):
    """The rotation that aims local +Z along a normal."""

    b_normal = mathutils.Vector(normal)
    if b_normal.length <= NORMAL_EPSILON:
        return mathutils.Quaternion()
    b_normal.normalize()
    return NORMAL_AXIS.rotation_difference(b_normal)


def make_handle(b_helper, b_root):
    """Make an object into a decal handle, shown as an arrow."""

    b_helper.empty_display_type = 'SINGLE_ARROW'
    b_helper.empty_display_size = 0.25
    b_helper.show_in_front = True
    b_helper.lock_scale = (True, True, True)
    b_helper.nif_object.is_decal_placement_helper = True
    b_helper.nif_object.decal_placement_root = b_root
    return b_helper


def place_handle(b_root, b_helper, point, normal):
    """Put a handle at a root-local point, aimed along a root-local normal."""

    # set in world space, because an adopted node is parented to its group node
    b_matrix = mathutils.Matrix.LocRotScale(
        mathutils.Vector(point), normal_rotation(normal), None)
    if b_root is None:
        b_helper.matrix_world = b_matrix
    else:
        b_helper.matrix_world = b_root.matrix_world @ b_matrix
    return b_helper


def link_beside(b_root, b_object):
    """Link an object into the same collections as a root."""

    for b_collection in b_root.users_collection:
        b_collection.objects.link(b_object)
    if not b_object.users_collection:
        bpy.context.scene.collection.objects.link(b_object)
    return b_object


def create_point_helper(b_root, point, normal, name=None, b_parent=None):
    """Create and link an arrow empty for one root-local point/normal pair."""

    name = name or f"{b_root.name} Decal Point"
    b_helper = bpy.data.objects.new(name, None)
    b_helper.rotation_mode = 'XYZ'
    make_handle(b_helper, b_root)
    b_helper.parent = b_parent or b_root
    # vector names repeat per group, so Blender suffixes them and the nif needs the plain one
    b_helper.nif_object.longname = name
    link_beside(b_root, b_helper)
    place_handle(b_root, b_helper, point, normal)
    return b_helper


def find_vector_group(b_root, block_index):
    """The reference group node for one vector block, or None."""

    for b_child in b_root.children:
        match = GROUP_NAME.match(b_child.name)
        if match and int(match.group(1)) == block_index:
            # the group transform is not part of the vector positions
            b_child.matrix_world = b_root.matrix_world
            b_child.nif_object.is_decal_placement_helper = True
            b_child.nif_object.decal_placement_root = b_root
            # its children are read in world space, which is stale until the depsgraph runs
            bpy.context.view_layer.update()
            return b_child
    return None


def vector_group(b_root, block_index):
    """The reference group node for one vector block, created if the file had none."""

    b_group = find_vector_group(b_root, block_index)
    if b_group is not None:
        return b_group

    name = f"DecalPlacementVectorGroup{block_index}"
    b_group = bpy.data.objects.new(name, None)
    b_group.empty_display_type = 'PLAIN_AXES'
    b_group.empty_display_size = 0.5
    b_group.nif_object.longname = name
    b_group.nif_object.is_decal_placement_helper = True
    b_group.nif_object.decal_placement_root = b_root
    b_group.parent = b_root
    link_beside(b_root, b_group)
    b_group.matrix_world = b_root.matrix_world
    return b_group


def next_vector_name(b_group):
    """The next free DecalPlacementVector name under a group."""

    used = set()
    for b_child in b_group.children:
        match = VECTOR_NAME.match(b_child.name)
        if match:
            used.add(int(match.group(1)))
    index = 0
    while index in used:
        index += 1
    return f"DecalPlacementVector{index}"


def adoptable_handles(b_group):
    """The vector nodes under a group."""

    return [b_child for b_child in b_group.children
            if b_child.type == 'EMPTY' and VECTOR_NAME.match(b_child.name)]


def claim_handle(b_root, b_candidates, point):
    """Remove and return the node matching a point, or None if none match."""

    # node order and numbering do not follow the block, so match on position
    b_point = mathutils.Vector(point)
    tolerance = nif_to_blender_units(MATCH_DISTANCE)
    b_best = None
    for b_candidate in b_candidates:
        distance = (helper_matrix(b_root, b_candidate).to_translation() - b_point).length
        if distance <= tolerance and (b_best is None or distance < b_best[0]):
            b_best = (distance, b_candidate)
    if b_best is None:
        return None
    b_candidates.remove(b_best[1])
    return b_best[1]


def helper_matrix(b_root, b_helper):
    """The transform of a handle in the space of its decal root."""

    # matrix_basis is up to date before the depsgraph runs, so use it when it applies
    if b_root is None or b_helper.parent is b_root:
        return b_helper.matrix_basis
    return b_root.matrix_world.inverted_safe() @ b_helper.matrix_world


def helper_normal(b_root, b_helper):
    """The unit normal of a handle, in the space of its decal root."""

    b_direction = helper_matrix(b_root, b_helper).to_quaternion() @ NORMAL_AXIS
    if b_direction.length <= NORMAL_EPSILON:
        return NORMAL_AXIS.copy()
    b_direction.normalize()
    return b_direction


def helper_point_and_normal(b_root, b_helper):
    """The root-local nif point and normal of a handle."""

    b_point = helper_matrix(b_root, b_helper).to_translation()
    n_point = tuple(blender_to_nif_units(value) for value in b_point)
    return n_point, tuple(helper_normal(b_root, b_helper))


def imported_point(point):
    """Convert an unscaled decal point from nif units to Blender units."""

    return tuple(nif_to_blender_units(value) for value in point)


def select_helper(b_helper, context=None):
    """Select one decal handle and make it active."""

    if b_helper is None:
        return
    context = context or bpy.context
    for b_selected in context.selected_objects:
        b_selected.select_set(False)
    b_helper.hide_set(False)
    b_helper.select_set(True)
    context.view_layer.objects.active = b_helper


def highlight_helpers(b_helpers):
    """Select the given handles without taking the active object."""

    # the decal panel only draws while the root is the active object
    context = bpy.context
    if not getattr(context, "view_layer", None):
        return
    for b_selected in context.selected_objects:
        b_selected.select_set(False)
    b_active = context.view_layer.objects.active
    if b_active is not None:
        b_active.select_set(True)
    for b_helper in b_helpers:
        if b_helper is not None and b_helper.name in context.view_layer.objects:
            b_helper.select_set(True)


def mesh_axes(b_root, b_mesh):
    """The mesh's own axes in the root's space, longest first."""

    b_to_root = b_root.matrix_world.inverted_safe()
    b_points = [b_to_root @ (b_mesh.matrix_world @ b_vertex.co)
                for b_vertex in b_mesh.data.vertices]
    if not b_points:
        return None

    b_center = sum(b_points, mathutils.Vector()) / len(b_points)
    b_covariance = mathutils.Matrix(((0.0,) * 3,) * 3)
    for b_point in b_points:
        b_offset = b_point - b_center
        for row in range(3):
            for column in range(3):
                b_covariance[row][column] += b_offset[row] * b_offset[column]

    b_axes = []
    for _index in range(3):
        b_axis = mathutils.Vector((1.0, 1.0, 1.0))
        for _step in range(64):
            b_axis = b_covariance @ b_axis
            for b_found in b_axes:
                b_axis -= b_found * b_axis.dot(b_found)
            if b_axis.length <= NORMAL_EPSILON:
                b_axis = mathutils.Vector((1.0, 0.0, 0.0))
                break
            b_axis.normalize()
        b_axes.append(b_axis)

    radius = max((b_point - b_center).length for b_point in b_points)
    return b_center, b_axes, radius


def facing_triangles(b_root, b_mesh, b_direction):
    """Triangles of a mesh whose front faces a direction, in the root's space."""

    b_data = b_mesh.data
    b_data.calc_loop_triangles()
    b_to_root = b_root.matrix_world.inverted_safe() @ b_mesh.matrix_world
    b_normal_to_root = b_to_root.to_3x3()

    b_triangles = []
    for b_triangle in b_data.loop_triangles:
        if (b_normal_to_root @ b_triangle.normal).dot(b_direction) <= 0.0:
            continue
        b_corners = [b_to_root @ b_data.vertices[index].co for index in b_triangle.vertices]
        b_area = (b_corners[1] - b_corners[0]).cross(b_corners[2] - b_corners[0]).length * 0.5
        if b_area > NORMAL_EPSILON:
            b_triangles.append((b_area, b_corners))
    return b_triangles


def poisson_samples(b_triangles, count, candidates_each=32):
    """Poisson disc sample of a triangle set, returned in the space the triangles are in.

    Candidates are scattered over the surface by area and then thinned so that no two picks
    sit closer than a radius, which is relaxed until enough of them fit.
    """

    if not b_triangles or count <= 0:
        return []

    total_area = sum(b_area for b_area, _corners in b_triangles)
    if total_area <= NORMAL_EPSILON:
        return []

    # low discrepancy pairs, so the same mesh always scatters the same way
    b_candidates = []
    wanted = count * candidates_each
    for index in range(wanted):
        along = (index + 0.5) / wanted * total_area
        first = (index * 0.7548776662) % 1.0
        second = (index * 0.5698402909) % 1.0
        running = 0.0
        for b_area, b_corners in b_triangles:
            running += b_area
            if running >= along:
                if first + second > 1.0:
                    first, second = 1.0 - first, 1.0 - second
                b_candidates.append(b_corners[0]
                                    + (b_corners[1] - b_corners[0]) * first
                                    + (b_corners[2] - b_corners[0]) * second)
                break

    radius = math.sqrt(total_area / count) * 0.8
    for _attempt in range(12):
        b_picked = []
        for b_candidate in b_candidates:
            if all((b_candidate - b_point).length >= radius for b_point in b_picked):
                b_picked.append(b_candidate)
                if len(b_picked) == count:
                    return b_picked
        if len(b_picked) >= count:
            return b_picked[:count]
        radius *= 0.8
    return b_picked
