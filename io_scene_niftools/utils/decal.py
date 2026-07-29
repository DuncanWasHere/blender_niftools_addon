"""Viewport helpers for BSDecalPlacementVectorExtraData."""

import bpy
import mathutils

from ..utils.particles import blender_to_nif_units, nif_to_blender_units


NORMAL_AXIS = mathutils.Vector((0.0, 0.0, 1.0))
NORMAL_EPSILON = 1.0e-8


def is_decal_helper(b_obj):
    """Whether an object is a viewport handle rather than an exportable nif node."""

    return bool(b_obj and getattr(b_obj, "nif_object", None)
                and b_obj.nif_object.is_decal_placement_helper)


def create_point_helper(b_root, point, normal, name=None):
    """Create and link an arrow empty for one root-local point/normal pair.

    Returns ``(helper, normal_length)``.  Normal length is kept separately because an
    empty's rotation represents direction only.
    """

    b_normal = mathutils.Vector(normal)
    normal_length = b_normal.length
    if normal_length <= NORMAL_EPSILON:
        b_normal = NORMAL_AXIS.copy()
        normal_length = 0.0
    else:
        b_normal.normalize()

    b_helper = bpy.data.objects.new(name or f"{b_root.name} Decal Point", None)
    b_helper.empty_display_type = 'SINGLE_ARROW'
    b_helper.empty_display_size = 0.25
    b_helper.show_in_front = True
    b_helper.rotation_mode = 'XYZ'
    b_helper.rotation_euler = NORMAL_AXIS.rotation_difference(b_normal).to_euler()
    b_helper.lock_scale = (True, True, True)
    b_helper.nif_object.is_decal_placement_helper = True
    b_helper.nif_object.decal_placement_root = b_root
    b_helper.parent = b_root
    b_helper.location = tuple(point)

    # Link beside the root so collection visibility controls the handles along with the nif.
    for b_collection in b_root.users_collection:
        b_collection.objects.link(b_helper)
    if not b_helper.users_collection:
        bpy.context.scene.collection.objects.link(b_helper)

    return b_helper, normal_length


def helper_point_and_normal(b_root, b_helper, normal_length):
    """Read a helper as root-local nif point/normal values."""

    # matrix_basis reflects transform edits immediately, even before Blender evaluates the
    # dependency graph.  Fall back through world space if a user has reparented the handle.
    # Scale is deliberately discarded from the normal.
    if b_helper.parent is b_root:
        b_matrix = b_helper.matrix_basis
    else:
        b_matrix = b_root.matrix_world.inverted_safe() @ b_helper.matrix_world
    b_point = b_matrix.to_translation()
    b_direction = b_matrix.to_quaternion() @ NORMAL_AXIS
    if b_direction.length > NORMAL_EPSILON:
        b_direction.normalize()
    else:
        b_direction = NORMAL_AXIS.copy()

    n_point = tuple(blender_to_nif_units(value) for value in b_point)
    n_normal = tuple(b_direction * normal_length)
    return n_point, n_normal


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
