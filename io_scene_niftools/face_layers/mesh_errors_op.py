import bpy


# mesh_errors Operator
class OBJECT_OT_mesh_errors(bpy.types.Operator):
    """Mesh Errors Operator"""
    bl_idname = "object.mesh_errors"
    bl_label = "Mesh errors"
    bl_options = {'UNDO', 'INTERNAL'}

    action: bpy.props.EnumProperty(
        items=[

            ('SELECT_LOOSE_FACES', 'select loose faces', 'select loose faces'),
            ('SELECT_LOOSE_EDGES', 'select loose edges', 'select loose edges'),
            ('SELECT_LOOSE_VERTS', 'select loose verts', 'select loose verts'),

            ('DELETE_LOOSE_FACES', 'delete loose faces', 'delete loose faces'),
            ('DELETE_LOOSE_EDGES', 'delete loose edges', 'delete loose edges'),
            ('DELETE_LOOSE_VERTS', 'delete loose verts', 'delete loose verts'),

            ('SELECT_ZERO_AREA_FACES', 'select zero area faces', 'select zero area faces'),
            ('DELETE_ZERO_AREA_FACES', 'delete zero area faces', 'delete zero area faces'),

            ('SCAN_MESH_ERRORS', 'scan mesh errors', 'scan mesh errors'),

        ], options={"HIDDEN"}
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    @staticmethod
    def ScanMeshErrors(context):

        ob = context.active_object
        mesh = ob.data

        ob.update_from_editmode()  # update data from edit mode to object
        current_selection = [vert.index for vert in ob.data.vertices if vert.select]
        current_mode = ob.mode
        current_mesh_select_mode = list(context.tool_settings.mesh_select_mode)

        ob.face_layers_globals.loose_faces = 0
        ob.face_layers_globals.loose_edges = 0
        ob.face_layers_globals.loose_verts = 0
        ob.face_layers_globals.zero_area_faces = 0
        ob.face_layers_globals.zero_length_edges = 0

        bpy.ops.object.mode_set(mode='EDIT')

        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_loose()
        ob.update_from_editmode()  # update data from edit mode to object
        for polygon in mesh.polygons:
            if polygon.select:
                ob.face_layers_globals.loose_faces += 1

        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_loose()
        ob.update_from_editmode()  # update data from edit mode to object
        for edge in mesh.edges:
            if edge.select:
                ob.face_layers_globals.loose_edges += 1

        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_loose()
        ob.update_from_editmode()  # update data from edit mode to object
        for vertex in mesh.vertices:
            if vertex.select:
                ob.face_layers_globals.loose_verts += 1

        bpy.ops.mesh.select_mode(type='FACE')
        for polygon in mesh.polygons:
            if polygon.area == 0:
                ob.face_layers_globals.zero_area_faces += 1

        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for index in current_selection:
            mesh.vertices[index].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        setMeshSelectMode(current_mesh_select_mode)
        bpy.ops.object.mode_set(mode=current_mode)

    @staticmethod
    def SelLooseFaces(context):
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_loose()

    @staticmethod
    def SelLooseEdges(context):
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_loose()

    @staticmethod
    def SelLooseVerts(context):
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_loose()

    @staticmethod
    def DelLooseFaces(context):
        ob = context.active_object
        current_mode = ob.mode
        bpy.ops.object.mode_set(mode='EDIT')
        current_mesh_select_mode = list(bpy.context.tool_settings.mesh_select_mode)

        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose(use_faces=True, use_edges=False, use_verts=False)
        bpy.ops.mesh.select_all(action='DESELECT')
        setMeshSelectMode(current_mesh_select_mode)
        bpy.ops.object.mode_set(mode=current_mode)
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)

    @staticmethod
    def DelLooseEdges(context):
        ob = context.active_object
        current_mode = ob.mode
        bpy.ops.object.mode_set(mode='EDIT')
        current_mesh_select_mode = list(bpy.context.tool_settings.mesh_select_mode)

        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose(use_faces=False, use_edges=True, use_verts=False)
        bpy.ops.mesh.select_all(action='DESELECT')
        setMeshSelectMode(current_mesh_select_mode)
        bpy.ops.object.mode_set(mode=current_mode)
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)

    @staticmethod
    def DelLooseVerts(context):
        ob = context.active_object
        current_mode = ob.mode
        bpy.ops.object.mode_set(mode='EDIT')
        current_mesh_select_mode = list(context.tool_settings.mesh_select_mode)

        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose(use_faces=False, use_edges=False, use_verts=True)
        bpy.ops.mesh.select_all(action='DESELECT')
        setMeshSelectMode(current_mesh_select_mode)
        bpy.ops.object.mode_set(mode=current_mode)
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)

    @staticmethod
    def SelZeroAreaFaces(context):
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)
        ob = context.active_object
        mesh = ob.data
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        zero_area_faces_list = [polygon.index for polygon in mesh.polygons if polygon.area == 0]
        for index in zero_area_faces_list:
            mesh.polygons[index].select = True
        bpy.ops.object.mode_set(mode='EDIT')

    @staticmethod
    def DelZeroAreaFaces(context):
        ob = context.active_object
        current_mode = ob.mode
        bpy.ops.object.mode_set(mode='EDIT')
        current_mesh_select_mode = list(bpy.context.tool_settings.mesh_select_mode)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.dissolve_degenerate()
        setMeshSelectMode(current_mesh_select_mode)
        bpy.ops.object.mode_set(mode=current_mode)
        OBJECT_OT_mesh_errors.ScanMeshErrors(context=context)

    def execute(self, context):

        # scan mesh for errors
        if self.action == 'SCAN_MESH_ERRORS':
            self.ScanMeshErrors(context=context)

        # select loose (faces, edges, verts)
        elif self.action == 'SELECT_LOOSE_FACES':
            self.SelLooseFaces(context=context)
        elif self.action == 'SELECT_LOOSE_EDGES':
            self.SelLooseEdges(context=context)
        elif self.action == 'SELECT_LOOSE_VERTS':
            self.SelLooseVerts(context=context)

        # delete loose (faces, edges, verts)
        elif self.action == 'DELETE_LOOSE_FACES':
            self.DelLooseFaces(context=context)
        elif self.action == 'DELETE_LOOSE_EDGES':
            self.DelLooseEdges(context=context)
        elif self.action == 'DELETE_LOOSE_VERTS':
            self.DelLooseVerts(context=context)

        # select zero area faces:
        elif self.action == 'SELECT_ZERO_AREA_FACES':
            self.SelZeroAreaFaces(context=context)

        # delete zero area faces:
        elif self.action == 'DELETE_ZERO_AREA_FACES':
            self.DelZeroAreaFaces(context=context)

        return {'FINISHED'}


# custom function
def setMeshSelectMode(current_mesh_select_mode):
    if current_mesh_select_mode[0]:
        type = 'VERT'
    elif current_mesh_select_mode[1]:
        type = 'EDGE'
    elif current_mesh_select_mode[2]:
        type = 'FACE'
    bpy.ops.mesh.select_mode(type=type)


def register():
    bpy.utils.register_class(OBJECT_OT_mesh_errors)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_mesh_errors)
