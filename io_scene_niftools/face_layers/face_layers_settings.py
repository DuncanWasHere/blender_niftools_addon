import bpy


class face_layers_settings(bpy.types.PropertyGroup):

    empty_icon: bpy.props.BoolProperty()

    ui_face_layers_align: bpy.props.BoolProperty(default=True)
    ui_face_layers_name_width: bpy.props.FloatProperty(subtype='PERCENTAGE', min=0, max=100, default=40)
    ui_face_layers_material_width: bpy.props.FloatProperty(subtype='PERCENTAGE', min=0, max=100, default=85)
    ui_face_layers_move: bpy.props.BoolProperty(default=True)
    ui_face_layers_material: bpy.props.BoolProperty(default=True)
    ui_face_layers_add: bpy.props.BoolProperty(default=True)
    ui_face_layers_remove: bpy.props.BoolProperty(default=True)
    ui_face_layers_select: bpy.props.BoolProperty(default=True)
    ui_face_layers_hide: bpy.props.BoolProperty(default=True)
    ui_face_layers_delete: bpy.props.BoolProperty(default=True)

    ui_mesh_data_align: bpy.props.BoolProperty(default=True)
    ui_mesh_data_name_width: bpy.props.FloatProperty(subtype='PERCENTAGE', min=0, max=100, default=40)

    ui_mesh_errors_align: bpy.props.BoolProperty(default=True)


def register():
    bpy.utils.register_class(face_layers_settings)
    bpy.types.Scene.face_layers_settings = bpy.props.PointerProperty(type=face_layers_settings)


def unregister():
    bpy.utils.unregister_class(face_layers_settings)
    del bpy.types.Scene.face_layers_settings
