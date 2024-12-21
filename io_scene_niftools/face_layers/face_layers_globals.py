import bmesh
import bpy


# Face layers global data
class face_layers_globals(bpy.types.PropertyGroup):

    def SelectAll(self, context):
        ob = context.active_object
        collection = ob.face_layers_collection
        current_mode = context.active_object.mode
        if current_mode == 'OBJECT':
            current_mode = 'EDIT'

        self.select_affects_icon_only = True
        bpy.ops.object.mode_set(mode='EDIT')

        mesh = ob.data
        bm = bmesh.from_edit_mesh(mesh)

        if "FaceLayerIndex" in bm.faces.layers.int.keys():
            custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

            if custom_layer:
                lockedIndices = []

                if self.select_all:
                    for coll in collection:
                        if not coll.locked:
                            coll.select = True
                        else:
                            lockedIndices.append(coll.index)

                    for face in bm.faces:
                        if face[custom_layer] != -1:
                            if face[custom_layer] not in lockedIndices:
                                face.select = True

                else:
                    for coll in collection:
                        if not coll.locked:
                            coll.select = False
                        else:
                            lockedIndices.append(coll.index)

                    for face in bm.faces:
                        if face[custom_layer] != -1:
                            if face[custom_layer] not in lockedIndices:
                                face.select = False

        bmesh.update_edit_mesh(mesh)
        bm.free()

        self.select_affects_icon_only = False
        bpy.ops.object.mode_set(mode=current_mode)

    def HideAll(self, context):
        ob = context.active_object
        collection = ob.face_layers_collection
        current_mode = context.active_object.mode
        if current_mode == 'OBJECT':
            current_mode = 'EDIT'

        self.hide_affects_icon_only = True
        bpy.ops.object.mode_set(mode='EDIT')

        mesh = ob.data
        bm = bmesh.from_edit_mesh(mesh)

        if "FaceLayerIndex" in bm.faces.layers.int.keys():
            custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

            if custom_layer:
                lockedIndices = []

                if self.hide_all:
                    for coll in collection:
                        if not coll.locked:
                            coll.hide = True
                        else:
                            lockedIndices.append(coll.index)

                    for face in bm.faces:
                        if face[custom_layer] != -1:
                            if face[custom_layer] not in lockedIndices:
                                face.hide = True
                                for edge in face.edges:
                                    edge.hide = True
                                for vertex in face.verts:
                                    vertex.hide = True
                else:
                    for coll in collection:
                        if not coll.locked:
                            coll.hide = False
                        else:
                            lockedIndices.append(coll.index)

                    for face in bm.faces:
                        if face[custom_layer] != -1:
                            if face[custom_layer] not in lockedIndices:
                                face.hide = False
                                for edge in face.edges:
                                    edge.hide = False
                                for vertex in face.verts:
                                    vertex.hide = False

        bmesh.update_edit_mesh(mesh)
        bm.free()

        self.hide_affects_icon_only = False
        bpy.ops.object.mode_set(mode=current_mode)

    select_all: bpy.props.BoolProperty(description="Select all face layers", update=SelectAll, default=False, options={'HIDDEN'})
    select_affects_icon_only: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    active_affects_icon_only: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    hide_all: bpy.props.BoolProperty(description="Hide all face layers", update=HideAll, default=False, options={'HIDDEN'})
    hide_affects_icon_only: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    move_material_affects_ui_only: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    all_faces: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    all_tris: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    all_ngons: bpy.props.IntProperty(default=0, options={'HIDDEN'})

    # selected_faces: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    # selected_tris: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    # selected_ngons: bpy.props.IntProperty(default=0, options={'HIDDEN'})

    loose_faces: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    loose_edges: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    loose_verts: bpy.props.IntProperty(default=0, options={'HIDDEN'})

    zero_area_faces: bpy.props.IntProperty(default=0, options={'HIDDEN'})

    material_fill: bpy.props.PointerProperty(type=bpy.types.Material, options={'HIDDEN'})
    materials_box: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    palettes_box: bpy.props.BoolProperty(default=False, options={'HIDDEN'})


def register():
    bpy.utils.register_class(face_layers_globals)
    bpy.types.Object.face_layers_globals = bpy.props.PointerProperty(type=face_layers_globals)


def unregister():
    bpy.utils.unregister_class(face_layers_globals)
    del bpy.types.Object.face_layers_globals
