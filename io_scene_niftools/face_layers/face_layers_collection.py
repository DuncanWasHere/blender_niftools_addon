import bpy
import bmesh


# Face layers collection data
class face_layers_collection(bpy.types.PropertyGroup):

    def SelectFaceLayer(self, context):
        ob = context.active_object
        globals = ob.face_layers_globals

        if not globals.select_affects_icon_only:

            current_mode = bpy.context.object.mode
            bpy.ops.object.mode_set(mode='EDIT')

            # Get the active mesh
            mesh = ob.data

            # Create a BMesh representation
            bm = bmesh.from_edit_mesh(mesh)

            if self.select:
                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == self.index:
                                face.select = True

            else:
                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == self.index:
                                face.select = False

            # Update the mesh
            bmesh.update_edit_mesh(mesh)
            bm.free()

            if current_mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                bpy.ops.object.mode_set(mode=current_mode)

        else:
            if globals.select_all:
                self.select = True
            else:
                self.select = False

    def HideFaceLayer(self, context):
        ob = context.active_object
        globals = ob.face_layers_globals

        if not globals.hide_affects_icon_only:

            current_mode = bpy.context.object.mode
            bpy.ops.object.mode_set(mode='EDIT')

            # Get the active mesh
            mesh = ob.data

            # Create a BMesh representation
            bm = bmesh.from_edit_mesh(mesh)

            if self.hide:
                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == self.index:
                                face.hide = True

                                # Hide all edges of the face
                                for edge in face.edges:
                                    edge.hide = True
                                for vertex in face.verts:
                                    vertex.hide = True

                    # Update the mesh
                    bmesh.update_edit_mesh(mesh)

            else:
                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == self.index:
                                face.hide = False

                                # Hide all edges of the face
                                for edge in face.edges:
                                    edge.hide = False
                                for vertex in face.verts:
                                    vertex.hide = False

            # Update the mesh
            bmesh.update_edit_mesh(mesh)
            bm.free()

            if current_mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                bpy.ops.object.mode_set(mode=current_mode)

        else:
            if globals.hide_all:
                self.hide = True
            else:
                self.hide = False

    def UpdateSingleMaterial(self, context):
        ob = context.active_object
        globals = ob.face_layers_globals
        material = self.material
        material_slots = ob.material_slots
        current_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')

        if not globals.move_material_affects_ui_only:
            if material:
                if material_slots:
                    # Check if material slot already exist
                    material_slot_index = material_slots.find(material.name)
                    if material_slot_index > -1:
                        ob.active_material_index = material_slot_index
                    else:
                        bpy.ops.object.material_slot_add()
                        material_slots[ob.active_material_index].material = self.material
                else:
                    bpy.ops.object.material_slot_add()
                    material_slots[ob.active_material_index].material = self.material

                # Save current selection
                polygons = ob.data.polygons
                selected = [poly.index for poly in polygons if poly.select]

                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='DESELECT')

                mesh = ob.data
                # Create a BMesh representation
                bm = bmesh.from_edit_mesh(mesh)

                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == self.index:
                                face.select = True

                    # Update the mesh
                    bmesh.update_edit_mesh(mesh)

                bpy.ops.object.material_slot_assign()
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')

                # Reselect polygons
                for i in selected:
                    polygons[i].select = True

            # Delete unused slots
            assigned_materials = []
            faceLayers = ob.face_layers_collection
            for layer in faceLayers:
                if material := layer.material:
                    assigned_materials.append(material.name)

            if num_of_slots := len(material_slots):
                for i in reversed(range(0, num_of_slots)):
                    if material_slots[i].name not in assigned_materials:
                        ob.active_material_index = i
                        bpy.ops.object.material_slot_remove()

            bpy.ops.object.mode_set(mode=current_mode)

    def updateActive(self, context):
        ob = context.active_object
        globals = ob.face_layers_globals

        if not globals.active_affects_icon_only:

            globals.active_affects_icon_only = True
            collection = ob.face_layers_collection
            for col in collection:
                col.active = False

            self.active = True
            globals.active_affects_icon_only = False

    index: bpy.props.IntProperty(options={'HIDDEN'})
    name: bpy.props.StringProperty(options={'HIDDEN'})
    active: bpy.props.BoolProperty(options={'HIDDEN'}, update=updateActive)
    locked: bpy.props.BoolProperty(description="Lock face layer", options={'HIDDEN'})
    num_of_faces: bpy.props.IntProperty(description="Number of faces in face layer", default=0, options={'HIDDEN'})
    num_of_tris: bpy.props.IntProperty(description="Number of triangles in face layer", default=0, options={'HIDDEN'})
    num_of_ngons: bpy.props.IntProperty(description="Number of ngons in face layer", default=0, options={'HIDDEN'})
    material: bpy.props.PointerProperty(type=bpy.types.Material, update=UpdateSingleMaterial, options={'HIDDEN'})
    select: bpy.props.BoolProperty(description="Select face layer", update=SelectFaceLayer, default=False, options={'HIDDEN'})
    hide: bpy.props.BoolProperty(description="Hide face layer", update=HideFaceLayer, default=False, options={'HIDDEN'})


# custom function
def checkFLayersCollExist(ob):
    """Check if there are face layers data exist"""
    return "face_layers_collection" in ob.keys() and len(ob.face_layers_collection)


# Delete face layer
class OBJECT_OT_face_layers_delete(bpy.types.Operator):
    """Delete face layer"""
    bl_idname = "object.face_layers_delete"
    bl_label = "Delete face layer"
    bl_options = {'UNDO', 'INTERNAL'}

    face_layer_index: bpy.props.IntProperty()

    @staticmethod
    def DeleteFaceLayer(self, context):

        ob = context.active_object
        collection = ob.face_layers_collection
        index = self.face_layer_index
        item = None

        for col in collection:
            if col.index == index:
                item = col

        itemIndex = -1
        if item:
            for i, prop in enumerate(collection):
                if prop == item:
                    itemIndex = i
                    break

        if itemIndex != -1:
            collection.remove(itemIndex)

        # Get the active mesh
        mesh = ob.data

        current_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='EDIT')

        # Create a BMesh representation
        bm = bmesh.from_edit_mesh(mesh)

        if len(collection):
            for col in collection:
                if col.index > index:
                    col.index -= 1

            # Check if the layer already exists
            if "FaceLayerIndex" in bm.faces.layers.int.keys():
                custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                if custom_layer:
                    for face in bm.faces:
                        if face[custom_layer] == index:
                            face[custom_layer] = -1

                        elif face[custom_layer] > index:
                            face[custom_layer] -= 1

        else:
            layer_name = "FaceLayerIndex"
            if layer_name in bm.faces.layers.int.keys():
                # Get the custom layer
                custom_layer = bm.faces.layers.int[layer_name]

                # Remove the layer
                bm.faces.layers.int.remove(custom_layer)

        # Update the mesh
        bmesh.update_edit_mesh(mesh)
        bm.free()

        bpy.ops.object.mode_set(mode=current_mode)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        self.DeleteFaceLayer(self=self, context=context)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(face_layers_collection)
    bpy.utils.register_class(OBJECT_OT_face_layers_delete)
    bpy.types.Object.face_layers_collection = bpy.props.CollectionProperty(type=face_layers_collection)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_face_layers_delete)
    bpy.utils.unregister_class(face_layers_collection)
    del bpy.types.Object.face_layers_collection
