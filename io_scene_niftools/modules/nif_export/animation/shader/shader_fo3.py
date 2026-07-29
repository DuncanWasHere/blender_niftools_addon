import bpy

from .....modules.nif_export.animation.common import AnimationCommon, attach_controller
from .....modules.nif_export.block_registry import block_store
from .....modules.nif_export.property.texture.common import TextureCommon

from nifgen.formats.nif import classes as NifClasses
from .....utils.logging import NifError, NifLog

def export_fo3_effect_shader_animation(n_ni_geometry_name, n_shader_prop, b_material, b_action,
                                       n_ni_controller_sequence=None, b_action_slot=None):
    action_fcurves = AnimationCommon.get_fcurves_from_action(
        None, b_action, b_action_slot)

    # the values live on the shader group's sockets, so an fcurve animating one addresses it
    # as nodes["<group>"].inputs[<index>].default_value
    b_group_node = TextureCommon.get_fallout_group_node(b_material)
    socket_paths = {}
    if b_group_node is not None:
        for socket_name, key in (("Refraction Strength", "strength"),
                                 ("Refraction Fire Period", "fire_period")):
            b_socket = b_group_node.inputs.get(socket_name)
            if b_socket is not None:
                index = list(b_group_node.inputs).index(b_socket)
                socket_paths[f'nodes["{b_group_node.name}"].inputs[{index}].default_value'] = key

    refraction_strength_data = []
    fire_period_data = []

    for fcurve in action_fcurves:
        key = socket_paths.get(fcurve.data_path)
        if key == "strength":
            refraction_strength_data.append(fcurve)
        elif key == "fire_period":
            fire_period_data.append(fcurve)

    refraction_strength_curves = []
    fire_period_curves = []

    for fcurve in refraction_strength_data:
        for keyframe in fcurve.keyframe_points:
            refraction_strength_curves.append((keyframe.co[0], keyframe.co[1]))

    for fcurve in fire_period_data:
        for keyframe in fcurve.keyframe_points:
            fire_period_curves.append((keyframe.co[0], keyframe.co[1]))

    if refraction_strength_curves:
        export_bs_refraction_controller("BSRefractionStrengthController", b_action, refraction_strength_curves,
                                        action_fcurves, b_material, n_ni_geometry_name, n_shader_prop,
                                        n_ni_controller_sequence)

    if fire_period_curves:
        export_bs_refraction_controller("BSRefractionFirePeriodController", b_action, fire_period_curves,
                                        action_fcurves, b_material, n_ni_geometry_name, n_shader_prop,
                                        n_ni_controller_sequence)

def export_bs_refraction_controller(controller_type, b_action, curves, action_fcurves, b_material,
                                    n_ni_geometry_name, n_shader_prop, n_ni_controller_sequence=None):
    """Export one of the float valued refraction controllers of a Fallout 3 shader property."""

    scene_fps = bpy.context.scene.render.fps

    n_key_data = block_store.create_block("NiFloatData")
    n_key_data.data.num_keys = len(curves)
    n_key_data.data.interpolation = NifClasses.KeyType.LINEAR_KEY
    n_key_data.data.reset_field("keys")

    for key, (frame, strength) in zip(n_key_data.data.keys, curves):
        key.time = frame / scene_fps
        key.value = strength

    n_refraction_controller = block_store.create_block(controller_type)
    n_float_interpolator = block_store.create_block("NiFloatInterpolator")

    frame_start, frame_end = b_action.frame_range

    n_refraction_controller.start_time = frame_start / scene_fps
    n_refraction_controller.stop_time = frame_end / scene_fps

    n_float_interpolator.data = n_key_data
    n_refraction_controller.interpolator = n_float_interpolator

    attach_controller(n_refraction_controller, n_float_interpolator, n_ni_geometry_name, controller_type,
                      n_ctrl_target=n_shader_prop, n_sequence=n_ni_controller_sequence,
                      property_type=b_material.nif_shader.bs_shadertype)
