import bmesh
import bpy
from .face_layers_collection import checkFLayersCollExist


# face_layers Operator
class OBJECT_OT_face_data(bpy.types.Operator):
    """Mesh Data Operator"""
    bl_idname = "object.mesh_data"
    bl_label = "Mesh data"
    bl_options = {'UNDO', 'INTERNAL'}

    face_layers_collection_index: bpy.props.IntProperty(options={"HIDDEN"})

    action: bpy.props.EnumProperty(
        items=[

            ('CALC_FACE_DATA', 'calculate face data', 'calculate face data'),
            ('SELECT_TRIS_ALL', 'select tris all', 'select all triangles in mesh'),
            ('SELECT_TRIS_SELECTED', 'select tris selected', 'select all triangles in selection'),
            ('SELECT_TRIS_LAYER', 'select tris layer', 'select all triangles in layer'),
            ('SELECT_NGONS_ALL', 'select ngons all', 'select all ngons in mesh'),
            ('SELECT_NGONS_SELECTED', 'select ngons selected', 'select all ngons in selection'),
            ('SELECT_NGONS_LAYER', 'select ngons layer', 'select all ngons in layer'),

        ], options={"HIDDEN"}
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    @staticmethod
    def CalcFaceData(context):
        ob = context.active_object
        current_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='EDIT')

        ob.update_from_editmode()  # update data from edit mode to object

        # Get the active mesh
        mesh = ob.data

        # Create a BMesh representation
        bm = bmesh.from_edit_mesh(mesh)

        # # selected faces only
        # selected_faces = 0
        # selected_tris = 0
        # selected_ngons = 0

        # all faces data
        all_faces = 0
        all_tris = 0
        all_ngons = 0

        # calculate number of faces in layers
        dict = {}

        if "FaceLayerIndex" in bm.faces.layers.int.keys():

            layer = bm.faces.layers.int.get("FaceLayerIndex")

            if layer:
                if checkFLayersCollExist(ob=ob):
                    collection = ob.face_layers_collection

                    for index in reversed(range(0, len(collection))):
                        layers = [col for col in collection if col.index == index]
                        layerC = layers[0]

                        layerC.num_of_tris = 0
                        layerC.num_of_ngons = 0

                    for i in range(0, len(collection)):
                        dict[i] = 0

                    for face in bm.faces:
                        loop_total = len(face.loops)

                        value = face[layer]
                        if value != -1:
                            dict[value] += 1

                        # if face.select:
                        #     selected_faces += 1
                        #     if loop_total == 3:
                        #         selected_tris += 1
                        #     elif loop_total > 4:
                        #         selected_ngons += 1

                        all_faces += 1
                        if loop_total == 3:
                            all_tris += 1
                            if value != -1:
                                layers = [col for col in collection if col.index == value]
                                layerC = layers[0]
                                layerC.num_of_tris += 1

                        elif loop_total > 4:
                            all_ngons += 1
                            if value != -1:
                                layers = [col for col in collection if col.index == value]
                                layerC = layers[0]
                                layerC.num_of_ngons += 1

                    for index in range(0, len(collection)):
                        layers = [col for col in collection if col.index == index]
                        layerC = layers[0]
                        layerC.num_of_faces = dict[index]

        # ob.face_layers_globals.selected_faces = selected_faces
        # ob.face_layers_globals.selected_tris = selected_tris
        # ob.face_layers_globals.selected_ngons = selected_ngons

        ob.face_layers_globals.all_faces = all_faces
        ob.face_layers_globals.all_tris = all_tris
        ob.face_layers_globals.all_ngons = all_ngons

        bmesh.update_edit_mesh(mesh)
        bm.free()
        bpy.ops.object.mode_set(mode=current_mode)

    @staticmethod
    def SelectTris(self, context, enum_mode):
        """enum_mode: 'ALL' (to select all triangles),
                      'SELECTED' (to select only selected triangles),
                      'LAYER' (to select only triangles in layer)
        """
        ob = context.active_object
        # Get the active mesh
        mesh = ob.data

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='FACE')

        # Create a BMesh representation
        bm = bmesh.from_edit_mesh(mesh)

        if enum_mode == 'ALL':
            for face in bm.faces:
                loop_total = len(face.loops)
                if loop_total == 3:
                    face.select = True

        elif enum_mode == 'SELECTED':
            selected_triangles = [face for face in bm.faces if face.select is True and len(face.loops) == 3]
            for face in selected_triangles:
                face.select = True

        elif enum_mode == 'LAYER':
            layer = bm.faces.layers.int.get("FaceLayerIndex")
            index = self.face_layers_collection_index
            triangles_in_layer = [face for face in bm.faces if face[layer] == index and len(face.loops) == 3]
            for face in triangles_in_layer:
                face.select = True

        bmesh.update_edit_mesh(mesh)
        bm.free()

    @staticmethod
    def SelectNgons(self, context, enum_mode):
        """enum_mode: 'ALL' (to select all ngons),
                      'SELECTED' (to select only selected ngons),
                      'LAYER' (to select only ngons in layer)
        """
        ob = context.active_object
        # Get the active mesh
        mesh = ob.data

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='FACE')

        # Create a BMesh representation
        bm = bmesh.from_edit_mesh(mesh)

        if enum_mode == 'ALL':
            for face in bm.faces:
                loop_total = len(face.loops)
                if loop_total > 4:
                    face.select = True

        elif enum_mode == 'SELECTED':
            selected_ngons = [face for face in bm.faces if face.select is True and len(face.loops) > 4]
            for face in selected_ngons:
                face.select = True

        elif enum_mode == 'LAYER':
            layer = bm.faces.layers.int.get("FaceLayerIndex")
            index = self.face_layers_collection_index
            ngons_in_layer = [face for face in bm.faces if face[layer] == index and len(face.loops) > 4]
            for face in ngons_in_layer:
                face.select = True

        bmesh.update_edit_mesh(mesh)
        bm.free()

    def execute(self, context):

        # calculate face data
        if self.action == 'CALC_FACE_DATA':
            self.CalcFaceData(context=context)

        # select triangles
        elif self.action == 'SELECT_TRIS_ALL':
            self.SelectTris(self=self, context=context, enum_mode='ALL')
        elif self.action == 'SELECT_TRIS_SELECTED':
            self.SelectTris(self=self, context=context, enum_mode='SELECTED')
        elif self.action == 'SELECT_TRIS_LAYER':
            self.SelectTris(self=self, context=context, enum_mode='LAYER')

        # select ngons
        elif self.action == 'SELECT_NGONS_ALL':
            self.SelectNgons(self=self, context=context, enum_mode='ALL')
        elif self.action == 'SELECT_NGONS_SELECTED':
            self.SelectNgons(self=self, context=context, enum_mode='SELECTED')
        elif self.action == 'SELECT_NGONS_LAYER':
            self.SelectNgons(self=self, context=context, enum_mode='LAYER')

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_face_data)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_face_data)
