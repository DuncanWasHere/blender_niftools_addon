from math import pow
from random import random
from random import randrange

import bmesh
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from .face_layers_collection import checkFLayersCollExist

"""Face layers"""


# Face layers main Operator
class OBJECT_OT_face_layers(bpy.types.Operator):
    """Face Layers Operator"""
    bl_idname = "object.face_layers"
    bl_label = "Face Layers"
    bl_options = {'UNDO', 'INTERNAL'}

    index: bpy.props.IntProperty(options={"HIDDEN"})

    action: bpy.props.EnumProperty(
        items=[
            # layers
            ('UPDATE_FACE_LAYERS', 'update face layers', 'update face layers'),
            ('REFRESH_FACE_LAYERS', 'refresh face layers', 'refresh face layers'),
            ('ADD_FACE_LAYER', 'add face layer', 'add face layer'),
            ('ADD_SELECTION', 'add selection', 'add selection'),
            ('REMOVE_SELECTION', 'remove selection', 'remove selection'),
            ('MOVE_FACE_LAYER_DOWN', 'move face layer down', 'move face layer down'),
            ('MOVE_FACE_LAYER_UP', 'move face layer up', 'move face layer up'),
            ('SELECT_BY_PICKING', 'select face layer by picking', 'select face layer by picking'),
            ('HIDE_BY_PICKING', 'hide face layer by picking', 'hide face layer by picking'),
            ('LOCK_BY_PICKING', 'lock face layer by picking', 'lock face layer by picking'),

        ], options={"HIDDEN"}
    )

    def __init__(self):
        self.face_indices = {}
        self.handler = None
        self.LayerIndex = -2

        self.indices = {}
        self.vertices = {}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH')

    @staticmethod
    def AddLayer(context):
        ob = context.active_object
        current_mode = ob.mode
        if current_mode == 'OBJECT':
            current_mode == 'EDIT'

        bpy.ops.object.mode_set(mode='EDIT')

        newLayer = bpy.context.object.face_layers_collection.add()
        index = len(bpy.context.object.face_layers_collection) - 1

        newLayer.index = index
        newLayer.name = 'FaceLayer_{0}'.format(newLayer.index)
        newLayer.active = True

        # Get the active mesh
        mesh = ob.data

        # Create a BMesh representation
        bm = bmesh.from_edit_mesh(mesh)

        # Check if the layer already exists
        if "FaceLayerIndex" not in bm.faces.layers.int.keys():
            # Add a new integer layer to faces if it does not exist
            custom_layer = bm.faces.layers.int.new("FaceLayerIndex")
            for face in bm.faces:
                face[custom_layer] = -1

        # Update the mesh
        bmesh.update_edit_mesh(mesh)
        bm.free()

        bpy.ops.object.mode_set(mode=current_mode)

    @staticmethod
    def AddSelection(context, index):
        ob = context.active_object
        mesh = ob.data
        bm = bmesh.from_edit_mesh(mesh)
        custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

        for face in bm.faces:
            if face.select:
                face[custom_layer] = index

        # Update the mesh
        bmesh.update_edit_mesh(mesh)
        bm.free()

    @staticmethod
    def RemoveSelection(context, index):
        ob = context.active_object
        mesh = ob.data
        bm = bmesh.from_edit_mesh(mesh)
        custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

        for face in bm.faces:
            if face.select:
                face[custom_layer] = -1
                face.select = False

        # Update the mesh
        bmesh.update_edit_mesh(mesh)
        bm.free()

    @staticmethod
    def MoveFaceLayerUp(context):
        ob = context.active_object
        bpy.ops.object.mode_set(mode='EDIT')

        collection = ob.face_layers_collection
        index = None

        for col in collection:
            if col.active:
                index = col.index

        if index is not None:

            if checkFLayersCollExist(ob) and len(ob.face_layers_collection) > index + 1:

                layers = [col for col in collection if col.index == index]
                layer = layers[0]

                nextLayers = [col for col in collection if col.index == index + 1]
                nextLayer = nextLayers[0]

                # Get the active mesh
                mesh = ob.data

                # Create a BMesh representation
                bm = bmesh.from_edit_mesh(mesh)

                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == layer.index:
                                face[custom_layer] += 1
                            elif face[custom_layer] == nextLayer.index:
                                face[custom_layer] -= 1

                # Update the mesh
                bmesh.update_edit_mesh(mesh)
                bm.free()

                layer.index += 1
                nextLayer.index -= 1

        bpy.ops.object.mode_set(mode='OBJECT')

    @staticmethod
    def MoveFaceLayerDown(context):
        ob = context.active_object
        bpy.ops.object.mode_set(mode='EDIT')

        collection = ob.face_layers_collection
        index = None

        for col in collection:
            if col.active:
                index = col.index

        if index:

            if checkFLayersCollExist(ob):

                layers = [col for col in collection if col.index == index]
                layer = layers[0]

                prevLayers = [col for col in collection if col.index == index - 1]
                prevLayer = prevLayers[0]

                # Get the active mesh
                mesh = ob.data

                # Create a BMesh representation
                bm = bmesh.from_edit_mesh(mesh)

                # Check if the layer already exists
                if "FaceLayerIndex" in bm.faces.layers.int.keys():
                    custom_layer = bm.faces.layers.int.get("FaceLayerIndex")

                    if custom_layer:
                        for face in bm.faces:
                            if face[custom_layer] == layer.index:
                                face[custom_layer] -= 1
                            elif face[custom_layer] == prevLayer.index:
                                face[custom_layer] += 1

                # Update the mesh
                bmesh.update_edit_mesh(mesh)
                bm.free()

                layer.index -= 1
                prevLayer.index += 1

        bpy.ops.object.mode_set(mode='OBJECT')

    @staticmethod
    def modal(self, context, event):

        if self.action == 'SELECT_BY_PICKING':
            context.window.cursor_set('PAINT_CROSS')

            if event.type == 'MOUSEMOVE':
                # get the context arguments
                scene = context.scene
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                scene = context.scene
                deps = context.evaluated_depsgraph_get()

                # get the ray from the viewport and mouse
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                hit = rayresult[0]
                if hit:
                    object_hitted = rayresult[4]
                    if object_hitted.name == self.ob.name:
                        face_id = rayresult[3]
                        try:
                            mesh = self.data

                            if 'FaceLayerIndex' in mesh.attributes:
                                layer = mesh.attributes['FaceLayerIndex']
                                face_layer_index = layer.data[face_id].value

                                if face_layer_index == -1 and face_layer_index != self.LayerIndex:

                                    if not self.handler:
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    else:
                                        bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    self.LayerIndex = face_layer_index

                                elif face_layer_index != -1 and face_layer_index != self.LayerIndex:

                                    layers = [col for col in self.collection if col.index == face_layer_index]
                                    layer = layers[0]

                                    if not layer.locked:
                                        if not layer.select:
                                            if not self.handler:
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()

                                            else:
                                                bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()
                                        else:
                                            if not self.handler:
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "YELLOW"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()

                                            else:
                                                bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "YELLOW"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()
                                    else:
                                        if not self.handler:
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()

                                        else:
                                            bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()
                                    self.LayerIndex = face_layer_index

                        except Exception:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            self.cleanup()
                            return {'FINISHED'}

            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                # get the context arguments
                scene = context.scene
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                scene = context.scene
                deps = context.evaluated_depsgraph_get()

                # get the ray from the viewport and mouse
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                hit = rayresult[0]
                if hit:
                    object_hitted = rayresult[4]
                    if object_hitted.name == self.ob.name:
                        face_id = rayresult[3]
                        try:
                            mesh = self.data
                            if 'FaceLayerIndex' in mesh.attributes:
                                layer = mesh.attributes['FaceLayerIndex']

                                face_layer_index = layer.data[face_id].value

                                if face_layer_index != -1:
                                    layers = [col for col in self.collection if col.index == face_layer_index]
                                    layer = layers[0]

                                    if not layer.locked:
                                        layer.select = not layer.select

                        except Exception:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            self.cleanup()
                            return {'FINISHED'}

                        if not event.alt:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            self.cleanup()
                            return {'FINISHED'}

                bpy.ops.object.mode_set(mode='OBJECT')
                self.LayerIndex = -2

            if event.type in {'ESC', 'RIGHTMOUSE', 'RET'}:
                context.window.cursor_set('DEFAULT')
                bpy.ops.object.mode_set(mode=self.current_mode)
                self.cleanup()
                return {'FINISHED'}

            return {'RUNNING_MODAL'}

        if self.action == 'HIDE_BY_PICKING':
            context.window.cursor_set('PAINT_CROSS')

            if event.type == 'MOUSEMOVE':
                # get the context arguments
                scene = context.scene
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                scene = context.scene
                deps = context.evaluated_depsgraph_get()

                # get the ray from the viewport and mouse
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                hit = rayresult[0]
                if hit:
                    object_hitted = rayresult[4]
                    if object_hitted.name == self.ob.name:
                        face_id = rayresult[3]
                        try:
                            mesh = self.data

                            if 'FaceLayerIndex' in mesh.attributes:
                                layer = mesh.attributes['FaceLayerIndex']
                                face_layer_index = layer.data[face_id].value

                                if face_layer_index == -1 and face_layer_index != self.LayerIndex:

                                    if not self.handler:
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    else:
                                        bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    self.LayerIndex = face_layer_index

                                elif face_layer_index != -1 and face_layer_index != self.LayerIndex:

                                    layers = [col for col in self.collection if col.index == face_layer_index]
                                    layer = layers[0]

                                    if not layer.locked:
                                        if not layer.hide:
                                            if not self.handler:
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()

                                            else:
                                                bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()
                                        else:
                                            if not self.handler:
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "YELLOW"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()

                                            else:
                                                bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                                self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "YELLOW"), 'WINDOW', 'POST_VIEW')
                                                context.area.tag_redraw()
                                    else:
                                        if not self.handler:
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()

                                        else:
                                            bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()
                                    self.LayerIndex = face_layer_index

                        except Exception:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            self.cleanup()
                            return {'FINISHED'}

            if event.type in {'LEFTMOUSE'}:
                if event.value in {'PRESS'}:
                    # get the context arguments
                    scene = context.scene
                    region = context.region
                    rv3d = context.region_data
                    coord = event.mouse_region_x, event.mouse_region_y
                    scene = context.scene
                    deps = context.evaluated_depsgraph_get()

                    # get the ray from the viewport and mouse
                    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                    rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                    hit = rayresult[0]
                    if hit:
                        object_hitted = rayresult[4]
                        if object_hitted.name == self.ob.name:
                            face_id = rayresult[3]
                            try:
                                mesh = self.data
                                if 'FaceLayerIndex' in mesh.attributes:
                                    layer = mesh.attributes['FaceLayerIndex']

                                    face_layer_index = layer.data[face_id].value

                                    if face_layer_index != -1:
                                        layers = [col for col in self.collection if col.index == face_layer_index]
                                        layer = layers[0]

                                        if not layer.locked:
                                            layer.hide = not layer.hide

                            except Exception:
                                context.window.cursor_set('DEFAULT')
                                bpy.ops.object.mode_set(mode=self.current_mode)
                                self.cleanup()
                                return {'FINISHED'}

                            if not event.alt:
                                context.window.cursor_set('DEFAULT')
                                bpy.ops.object.mode_set(mode=self.current_mode)
                                self.cleanup()
                                return {'FINISHED'}

                bpy.ops.object.mode_set(mode='OBJECT')
                self.LayerIndex = -2

            if event.type in {'ESC', 'RIGHTMOUSE', 'RET'}:
                context.window.cursor_set('DEFAULT')
                bpy.ops.object.mode_set(mode=self.current_mode)
                self.cleanup()
                return {'FINISHED'}

            return {'RUNNING_MODAL'}

        if self.action == 'LOCK_BY_PICKING':
            context.window.cursor_set('PAINT_CROSS')

            if event.type == 'MOUSEMOVE':
                # get the context arguments
                scene = context.scene
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                scene = context.scene
                deps = context.evaluated_depsgraph_get()

                # get the ray from the viewport and mouse
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                hit = rayresult[0]
                if hit:
                    object_hitted = rayresult[4]
                    if object_hitted.name == self.ob.name:
                        face_id = rayresult[3]
                        try:
                            mesh = self.data

                            if 'FaceLayerIndex' in mesh.attributes:
                                layer = mesh.attributes['FaceLayerIndex']
                                face_layer_index = layer.data[face_id].value

                                if face_layer_index == -1 and face_layer_index != self.LayerIndex:

                                    if not self.handler:
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    else:
                                        bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "RED"), 'WINDOW', 'POST_VIEW')
                                        context.area.tag_redraw()

                                    self.LayerIndex = face_layer_index

                                elif face_layer_index != -1 and face_layer_index != self.LayerIndex:

                                    layers = [col for col in self.collection if col.index == face_layer_index]
                                    layer = layers[0]

                                    if not layer.locked:
                                        if not self.handler:
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()

                                        else:
                                            bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "GREEN"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()

                                    else:
                                        if not self.handler:
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()

                                        else:
                                            bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                                            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context, face_layer_index, "BLUE"), 'WINDOW', 'POST_VIEW')
                                            context.area.tag_redraw()
                                    self.LayerIndex = face_layer_index

                        except Exception:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            self.cleanup()
                            return {'FINISHED'}

            if event.type in {'LEFTMOUSE'}:
                if event.value in {'PRESS'}:
                    # get the context arguments
                    scene = context.scene
                    region = context.region
                    rv3d = context.region_data
                    coord = event.mouse_region_x, event.mouse_region_y
                    scene = context.scene
                    deps = context.evaluated_depsgraph_get()

                    # get the ray from the viewport and mouse
                    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                    rayresult = scene.ray_cast(deps, ray_origin, view_vector)
                    hit = rayresult[0]
                    if hit:
                        object_hitted = rayresult[4]
                        if object_hitted.name == self.ob.name:
                            face_id = rayresult[3]
                            try:
                                mesh = self.data
                                if 'FaceLayerIndex' in mesh.attributes:
                                    layer = mesh.attributes['FaceLayerIndex']

                                    face_layer_index = layer.data[face_id].value

                                    if face_layer_index != -1:
                                        layers = [col for col in self.collection if col.index == face_layer_index]
                                        layer = layers[0]

                                        layer.locked = not layer.locked
                                        context.area.tag_redraw()

                            except Exception:
                                context.window.cursor_set('DEFAULT')
                                bpy.ops.object.mode_set(mode=self.current_mode)
                                self.cleanup()
                                return {'FINISHED'}

                            if not event.alt:
                                context.window.cursor_set('DEFAULT')
                                bpy.ops.object.mode_set(mode=self.current_mode)
                                self.cleanup()
                                return {'FINISHED'}

                self.LayerIndex = -2

            if event.type in {'ESC', 'RIGHTMOUSE', 'RET'}:
                context.window.cursor_set('DEFAULT')
                bpy.ops.object.mode_set(mode=self.current_mode)
                self.cleanup()
                return {'FINISHED'}

            return {'RUNNING_MODAL'}

    def cleanup(self):
        if self.handler:
            bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
            self.handler = None
        bpy.context.area.tag_redraw()

    def draw_callback_3d(self, context, face_layer_index, color):
        if not self.face_indices:
            return

        # Determine the color to paint
        paintedColor = {
            "GREEN": (0.0, 1.0, 0.0, 0.0),
            "RED": (1.0, 0.0, 0.0, 0.0),
            "BLUE": (0.0, 0.0, 1.0, 0.0),
            "YELLOW": (1.0, 1.0, 0.0, 0.0)
        }.get(color, (0.0, 0.0, 0.0, 0.0))

        obj = context.active_object
        mesh = obj.data
        world_matrix = obj.matrix_world

        if self.vertices[face_layer_index] and self.indices[face_layer_index]:
            vertices = [tuple(v) for v in self.vertices[face_layer_index]]
            batch = batch_for_shader(gpu.shader.from_builtin('UNIFORM_COLOR'), 'TRIS', {"pos": vertices}, indices=self.indices[face_layer_index])
        else:
            vertices = []
            indices = []
            index_map = {}

            for face_idx in self.face_indices[face_layer_index]:
                face = mesh.polygons[face_idx]
                face_verts = []
                for vert_idx in face.vertices:
                    if vert_idx not in index_map:
                        index_map[vert_idx] = len(vertices)
                        world_vert = world_matrix @ mesh.vertices[vert_idx].co
                        vertices.append(world_vert)
                    face_verts.append(index_map[vert_idx])

                # Generate triangles for the face
                triangles = []
                for i in range(len(face_verts) - 2):
                    tri = [face_verts[0], face_verts[i + 1], face_verts[i + 2]]
                    triangles.append(tri)
                indices.extend(triangles)

            indices = [tuple(tri) for tri in indices]

            self.vertices[face_layer_index] = vertices
            self.indices[face_layer_index] = indices

            if vertices:
                vertices = [tuple(v) for v in vertices]
                batch = batch_for_shader(gpu.shader.from_builtin('UNIFORM_COLOR'), 'TRIS', {"pos": vertices}, indices=indices)

        # Bind the shader and draw the batch
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float("color", paintedColor)
        batch.draw(shader)

    def initializeSelfAttrbs(self):
        collLen = len(self.collection)
        for i in range(0, collLen):
            self.face_indices[i] = []
            self.indices[i] = []
            self.vertices[i] = []

        self.face_indices[-1] = []
        self.indices[-1] = []
        self.vertices[-1] = []

    def execute(self, context):
        # update face layers
        if self.action == 'UPDATE_FACE_LAYERS':
            self.UpdateFaceLayers(context=context)

        # add face layer
        elif self.action == 'ADD_FACE_LAYER':
            self.AddLayer(context=context)

        # add faces to face layer (face map)
        elif self.action == 'ADD_SELECTION':
            self.AddSelection(context=context, index=self.index)

        # remove faces from face layer (face map)
        elif self.action == 'REMOVE_SELECTION':
            self.RemoveSelection(context=context, index=self.index)

        # move face layer up (face map up)
        elif self.action == 'MOVE_FACE_LAYER_DOWN':
            self.MoveFaceLayerDown(context=context)

        # move face layer down (face map down)
        elif self.action == 'MOVE_FACE_LAYER_UP':
            self.MoveFaceLayerUp(context=context)

        # select by picking
        elif self.action == 'SELECT_BY_PICKING':
            context.window_manager.modal_handler_add(self)
            self.data = context.active_object.data
            self.ob = context.active_object
            self.current_mode = self.ob.mode
            self.collection = self.ob.face_layers_collection

            if self.current_mode == 'OBJECT':
                self.current_mode = 'EDIT'
            bpy.ops.object.mode_set(mode='OBJECT')

            self.initializeSelfAttrbs()

            mesh = self.data
            if 'FaceLayerIndex' in mesh.attributes:
                layer = mesh.attributes['FaceLayerIndex']

                for i in range(0, len(layer.data)):
                    self.face_indices[layer.data[i].value].append(i)

            return {'RUNNING_MODAL'}

        # hide by picking
        elif self.action == 'HIDE_BY_PICKING':
            context.window_manager.modal_handler_add(self)
            self.data = context.active_object.data
            self.ob = context.active_object
            self.current_mode = self.ob.mode
            self.collection = self.ob.face_layers_collection

            if self.current_mode == 'OBJECT':
                self.current_mode = 'EDIT'
            bpy.ops.object.mode_set(mode='OBJECT')

            self.initializeSelfAttrbs()

            mesh = self.data
            if 'FaceLayerIndex' in mesh.attributes:
                layer = mesh.attributes['FaceLayerIndex']

                for i in range(0, len(layer.data)):
                    self.face_indices[layer.data[i].value].append(i)

            return {'RUNNING_MODAL'}

        # Lock by picking
        elif self.action == 'LOCK_BY_PICKING':
            context.window_manager.modal_handler_add(self)
            self.data = context.active_object.data
            self.ob = context.active_object
            self.current_mode = self.ob.mode
            self.collection = self.ob.face_layers_collection

            bpy.ops.object.mode_set(mode='OBJECT')

            self.initializeSelfAttrbs()

            mesh = self.data
            if 'FaceLayerIndex' in mesh.attributes:
                layer = mesh.attributes['FaceLayerIndex']

                for i in range(0, len(layer.data)):
                    self.face_indices[layer.data[i].value].append(i)

            return {'RUNNING_MODAL'}

        return {'FINISHED'}


# Delete all face layers
class OBJECT_OT_face_layers_delete_all(bpy.types.Operator):
    """Delete all unlocked face layers"""
    bl_idname = "object.face_layers_delete_all"
    bl_label = "Delete all unlocked face layers"
    bl_options = {'UNDO', 'INTERNAL'}

    @staticmethod
    def DeleteAllFaceLayers(context):
        ob = context.active_object
        collection = ob.face_layers_collection
        current_mode = bpy.context.active_object.mode

        bpy.ops.object.mode_set(mode='EDIT')
        for col in reversed(collection):
            if not col.locked:
                index = col.index
                bpy.ops.object.face_layers_delete(face_layer_index=index)

        bpy.ops.object.mode_set(mode=current_mode)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        self.DeleteAllFaceLayers(context=context)
        return {'FINISHED'}


"""Material layers"""


# Assign material layer by picking
class OBJECT_OT_face_layers_materials_assign_by_picking(bpy.types.Operator):
    """Fill face layer with selected material by picking on the model"""
    bl_idname = "object.face_layers_materials_assign_by_picking"
    bl_label = "Assign Material By Picking"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return (ob and ob.type == 'MESH')

    @staticmethod
    def modal(self, context, event):
        material_fill = self.ob.face_layers_globals.material_fill
        context.window.cursor_set('PAINT_CROSS')
        if event.type in {'LEFTMOUSE'}:
            if event.value in {'PRESS'}:
                bpy.ops.object.mode_set(mode='OBJECT')
                # get the context arguments
                scene = context.scene
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                scene = context.scene
                deps = context.evaluated_depsgraph_get()

                # get the ray from the viewport and mouse
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                rayresult = scene.ray_cast(deps, ray_origin, view_vector)

                hit = rayresult[0]
                if hit:
                    object_hitted = rayresult[4]
                    if object_hitted.name == self.ob.name:
                        face_id = rayresult[3]
                        try:
                            mesh = self.data
                            if 'FaceLayerIndex' in mesh.attributes:
                                layer = mesh.attributes['FaceLayerIndex']

                                face_layer_index = layer.data[face_id].value

                                if face_layer_index != -1:
                                    collection = self.ob.face_layers_collection
                                    layers = [col for col in collection if col.index == face_layer_index]
                                    layer = layers[0]

                                if not layer.locked:
                                    if material_fill:
                                        layer.material = material_fill

                        except Exception:
                            context.window.cursor_set('DEFAULT')
                            return {'FINISHED'}

                        if not event.alt:
                            context.window.cursor_set('DEFAULT')
                            bpy.ops.object.mode_set(mode=self.current_mode)
                            return {'FINISHED'}

                bpy.ops.object.mode_set(mode=self.current_mode)

        if event.type in {'ESC', 'RIGHTMOUSE', 'RET'}:
            context.window.cursor_set('DEFAULT')
            bpy.ops.object.mode_set(mode=self.current_mode)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def execute(self, context):
        context.window_manager.modal_handler_add(self)
        self.data = context.active_object.data
        self.ob = context.active_object
        self.current_mode = self.ob.mode
        return {'RUNNING_MODAL'}


# Randomize material layers colors
class OBJECT_OT_face_layers_materials_randomize_colors(bpy.types.Operator):
    """Randomize materials colors from palette"""
    bl_idname = "object.face_layers_materials_randomize_colors"
    bl_label = "Randomize materials colors"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH')

    @staticmethod
    def RandomizeColors(context):
        ob = bpy.context.active_object
        mat_slots = []
        for coll in ob.face_layers_collection:
            if coll.material:
                if not coll.locked:
                    mat_slots.append(coll.material)

        active_palette = bpy.context.tool_settings.image_paint.palette
        if active_palette and (colors_len := len(colors := active_palette.colors)):
            for material in mat_slots:
                if node_tree := material.node_tree:
                    links = node_tree.links.values()
                    for link in links:
                        if link.to_node.type == 'OUTPUT_MATERIAL':
                            if link.to_socket.name == 'Surface':
                                node_name = link.from_node.name
                                # SRGB to linear
                                color = colors[randrange(0, colors_len)].color
                                linear_color = []
                                for channel in color:
                                    if channel <= 0.0404482362771082:
                                        linear_channel = channel / 12.92
                                    else:
                                        linear_channel = pow(((channel + 0.055) / 1.055), 2.4)
                                    linear_color.append(linear_channel)
                                try:
                                    material.node_tree.nodes[node_name].inputs[0].default_value = *linear_color, 1
                                except Exception:
                                    pass
        else:
            for material in mat_slots:
                if node_tree := material.node_tree:
                    links = node_tree.links.values()
                    for link in links:
                        if link.to_node.type == 'OUTPUT_MATERIAL':
                            if link.to_socket.name == 'Surface':
                                node_name = link.from_node.name
                                try:
                                    material.node_tree.nodes[node_name].inputs[0].default_value = (random(), random(), random(), 1)
                                except Exception:
                                    pass

    def execute(self, context):
        self.RandomizeColors(context=context)
        return {'FINISHED'}


# Paste and create palette from any text contains 6 hex color values
class OBJECT_OT_face_layers_paste_hex_colors(bpy.types.Operator):
    """Add colors from copied hex values"""
    bl_idname = "object.face_layers_paste_hex_colors"
    bl_label = "Paste hex colors"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH' and context.tool_settings.image_paint.palette)

    @staticmethod
    def PastehexColors(self, context):
        url = str(context.window_manager.clipboard)
        color = False
        color_text = []
        i = 0
        length = len(url) - 5
        while i < length:
            color_text = url[i: i + 6]
            color = True
            for char in color_text:
                if char not in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", 'a', 'A', 'b', 'B', 'c', 'C', 'd', 'D', 'e', 'E', 'f', 'F'):
                    color = False
                    i += 1
                    break
            if color:
                R = int(color_text[:2], base=16) / 255
                G = int(color_text[2:4], base=16) / 255
                B = int(color_text[4:6], base=16) / 255
                RGB_color = (R, G, B)
                bpy.context.tool_settings.image_paint.brush.color = RGB_color
                bpy.ops.palette.color_add()
                i += 6

    def execute(self, context):
        self.PastehexColors(self=self, context=context)
        return {'FINISHED'}


# Clear face layers materials
class OBJECT_OT_face_layers_materials_clear(bpy.types.Operator):
    """Clear face layers materials"""
    bl_idname = "object.face_layers_materials_clear"
    bl_label = "Clear Materials"
    bl_options = {'UNDO', 'INTERNAL'}

    action: bpy.props.EnumProperty(items=[
        ("CLEAR_MATERIALS", "Clear Materials", "Clear Materials"),
        ("DELETE_MATERIALS", "Delete Materials", "Delete Materials")
    ], default="CLEAR_MATERIALS", name="Action")

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH')

    @staticmethod
    def ClearMaterials(self, context):
        ob = context.active_object
        collection = ob.face_layers_collection

        if self.action == 'CLEAR_MATERIALS':
            for coll in collection:
                if coll.material:
                    coll.material = None

        elif self.action == 'DELETE_MATERIALS':
            current_mode = ob.mode
            bpy.ops.object.mode_set(mode='OBJECT')
            for coll in collection:
                if coll.material:
                    bpy.data.materials.remove(coll.material)
                for slot in ob.material_slots:
                    if not slot.material:
                        ob.active_material_index = slot.slot_index
                        bpy.ops.object.material_slot_remove()
            bpy.ops.object.mode_set(mode=current_mode)

    def invoke(self, context, event):
        return bpy.context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        self.ClearMaterials(self=self, context=context)
        return {'FINISHED'}


# Create a new material layer for each face layer
class OBJECT_OT_face_layers_materials_create(bpy.types.Operator):
    """Create a material for each face layer"""
    bl_idname = "object.face_layers_materials_create"
    bl_label = "Create Materials"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH')

    @staticmethod
    def CreateMaterialForEachFaceLayer(self, context):
        ob = context.active_object
        collection = ob.face_layers_collection
        mat_slots = ob.material_slots
        baseName = self.base_name

        current_mode = ob.mode
        bpy.ops.object.mode_set(mode='OBJECT')

        if mat_slots:
            for i in reversed(range(0, len(mat_slots))):
                ob.active_material_index = i
                bpy.ops.object.material_slot_remove()

        for i in range(0, len(collection)):
            if self.base_name == "<<FaceLayerIndex>>":
                baseName = collection[i].name
            name = "".join([self.Prefix, baseName, self.Suffix])
            material = bpy.data.materials.new(name=name)
            material.use_nodes = True
            nodeTree = material.node_tree
            principledBSDF_node = nodeTree.nodes['Principled BSDF']
            nodeTree.nodes.remove(principledBSDF_node)
            surface_node = nodeTree.nodes.new(type=self.surface_type)
            output_material = nodeTree.nodes['Material Output']
            nodeTree.links.new(surface_node.outputs[0], output_material.inputs[0])

            if self.Colors == 'RANDOM_COLORS':
                try:
                    node = nodeTree.links[0].from_node
                    node.inputs[0].default_value = (random(), random(), random(), 1)
                except Exception:
                    pass

            elif self.Colors == 'RANDOM_FROM_PALETTE':
                bpy.ops.object.face_layers_materials_randomize_colors()

            collection[i].material = material

        bpy.ops.object.mode_set(mode=current_mode)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        self.CreateMaterialForEachFaceLayer(self=self, context=context)
        return {'FINISHED'}

    surface_type: bpy.props.EnumProperty(items=[
                                            ('ShaderNodeBsdfPrincipled', 'Principled BSDF', 'Principled BSDF'),
                                            ('ShaderNodeBsdfDiffuse', 'Diffuse BSDF', 'Diffuse BSDF'),
                                            ('ShaderNodeBsdfGlossy', 'Glossy BSDF', 'Glossy BSDF'),
                                            ('ShaderNodeBsdfGlass', 'Glass BSDF', 'Glass BSDF'),
                                            ('ShaderNodeBsdfToon', 'Toon BSDF', 'Toon BSDF'),
                                            ('ShaderNodeEmission', 'Emission', 'Emission')
                                        ], name='Surface Type')

    Colors: bpy.props.EnumProperty(items=[
                                        ('DEFAULT', 'default', 'default'),
                                        ('RANDOM_COLORS', 'Random Colors', 'Random Colors'),
                                        ('RANDOM_FROM_PALETTE', 'Random From Palette', 'Random From Palette'),
                                    ])

    Prefix: bpy.props.StringProperty()
    base_name: bpy.props.StringProperty(name="Base Name", default="<<FaceLayerIndex>>")
    Suffix: bpy.props.StringProperty()


# Create a new material
class OBJECT_OT_face_layers_new_material(bpy.types.Operator):
    """Create a new material"""
    bl_idname = "object.face_layers_new_material"
    bl_label = "Create a new material"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'MESH')

    @staticmethod
    def CreateNewMaterial(context):
        globals = context.active_object.face_layers_globals

        mat = bpy.data.materials.new(name="M.001")
        mat.use_nodes = True
        globals.material_fill = mat

    def execute(self, context):
        self.CreateNewMaterial(context=context)
        return {'FINISHED'}


"""Register"""


def register():
    bpy.utils.register_class(OBJECT_OT_face_layers)
    bpy.utils.register_class(OBJECT_OT_face_layers_delete_all)

    bpy.utils.register_class(OBJECT_OT_face_layers_paste_hex_colors)
    bpy.utils.register_class(OBJECT_OT_face_layers_materials_create)
    bpy.utils.register_class(OBJECT_OT_face_layers_new_material)
    bpy.utils.register_class(OBJECT_OT_face_layers_materials_randomize_colors)
    bpy.utils.register_class(OBJECT_OT_face_layers_materials_clear)
    bpy.utils.register_class(OBJECT_OT_face_layers_materials_assign_by_picking)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_face_layers_delete_all)

    bpy.utils.unregister_class(OBJECT_OT_face_layers_materials_assign_by_picking)
    bpy.utils.unregister_class(OBJECT_OT_face_layers_materials_clear)
    bpy.utils.unregister_class(OBJECT_OT_face_layers_materials_randomize_colors)
    bpy.utils.unregister_class(OBJECT_OT_face_layers_new_material)
    bpy.utils.unregister_class(OBJECT_OT_face_layers_materials_create)
    bpy.utils.unregister_class(OBJECT_OT_face_layers_paste_hex_colors)

    bpy.utils.unregister_class(OBJECT_OT_face_layers)
