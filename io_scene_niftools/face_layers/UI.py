import bpy
import os
import bpy.utils.previews
from .face_layers_collection import checkFLayersCollExist


# Face Layers UI
class DATA_PT_FaceLayers(bpy.types.Panel):
    bl_label = "Face Layers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Face Layers"

    def draw(self, context):
        # custom icons
        pcoll = preview_collections["main"]
        pick = pcoll["pick"]
        add_facelayer = pcoll["add_facelayer"]
        assign_materials = pcoll["assign_materials"]
        fill_materials = pcoll["fill"]

        if (ob := context.active_object) and ob.type == 'MESH':
            globals = ob.face_layers_globals
            collection = ob.face_layers_collection
            settings = context.scene.face_layers_settings

            align = settings.ui_face_layers_align
            layout = self.layout
            box = layout.box()
            main_col = box.column()

            row = main_col.row(align=True)
            row.scale_y = 1.5
            row.operator('object.face_layers', icon_value=add_facelayer.icon_id, text='Add Face Layer').action = 'ADD_FACE_LAYER'
            # row.operator('object.face_layers', icon='FILE_REFRESH', text='').action = 'REFRESH_FACE_LAYERS'

            sub_col = main_col.column()

            # select, hide, lock by picking
            col = sub_col.box().column()

            if settings.ui_face_layers_move:
                main_split = col.split()
                split = main_split.split(align=True)
            else:
                split = col.split(align=True)

            col1 = split.column(align=True)
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Select').action = 'SELECT_BY_PICKING'
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Hide').action = 'HIDE_BY_PICKING'
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Lock').action = 'LOCK_BY_PICKING'

            # select , hide , delete all
            col2 = split.column(align=True)
            col2.prop(globals, property="select_all", icon='RESTRICT_SELECT_OFF', text='Select All')
            if globals.hide_all is True:
                hide = "HIDE_ON"
            else:
                hide = "HIDE_OFF"
            col2.prop(globals, property="hide_all", icon=hide, text='Hide All')
            col2.operator('object.face_layers_delete_all', icon='X', text='Delete All')

            # =======================================================================================================

            # Layers collection
            if checkFLayersCollExist(ob=ob):
                col = sub_col.box().column()

                if settings.ui_face_layers_move:
                    # Move face layer up and down
                    moveRow = col.row(align=True)
                    moveRow.scale_y = 1.5
                    moveRow.operator('object.face_layers', icon='TRIA_UP', text='Layer Up', emboss=False).action = 'MOVE_FACE_LAYER_UP'
                    moveRow.operator('object.face_layers', icon='TRIA_DOWN', text='Layer Down', emboss=False).action = 'MOVE_FACE_LAYER_DOWN'

                for index in reversed(range(0, len(ob.face_layers_collection))):
                    row = col.row(align=True)
                    row2 = row.row(align=True)

                    layers = [col for col in collection if col.index == index]
                    layer = layers[0]

                    # lock
                    icon = "UNLOCKED"
                    if layer.locked:
                        icon = "LOCKED"
                    row2.prop(layer, property="locked", icon=icon, text="")

                    split = row.split(factor=settings.ui_face_layers_name_width / 100, align=True)
                    # disable when locked
                    split.enabled = not layer.locked
                    name_row = split.row(align=True)

                    if settings.ui_face_layers_move:

                        # move
                        icon = "RADIOBUT_OFF"
                        if layer.active:
                            icon = "RADIOBUT_ON"
                        name_row.prop(layer, property="active", icon=icon, text="", emboss=False)

                    split2 = split.split(factor=settings.ui_face_layers_material_width / 100, align=True)
                    if settings.ui_face_layers_material:
                        split2.prop(layer, property="material", text="")

                    name_row.prop(layer, property="name", text="")
                    # Color
                    try:
                        material = layer.material
                        if material:
                            if node_tree := material.node_tree:
                                links = node_tree.links.values()
                                for link in links:
                                    if link.to_node.type == 'OUTPUT_MATERIAL':
                                        if link.to_socket.name == 'Surface':
                                            node_name = link.from_node.name
                                            split2.prop(material.node_tree.nodes[node_name].inputs[0], property="default_value", text="")
                    except Exception:
                        pass

                    # disable when locked
                    row = row.row(align=align)
                    row.enabled = not layer.locked
                    # add, remove
                    if settings.ui_face_layers_add or settings.ui_face_layers_remove:
                        row2 = row.row(align=align)
                        row2.enabled = (bpy.context.object.mode == 'EDIT')
                        if settings.ui_face_layers_add:
                            op1 = row2.operator('object.face_layers', icon='ADD', text="")
                            op1.action = 'ADD_SELECTION'
                            op1.index = index
                        if settings.ui_face_layers_remove:
                            op2 = row2.operator('object.face_layers', icon='REMOVE', text="")
                            op2.action = 'REMOVE_SELECTION'
                            op2.index = index
                    # select
                    if settings.ui_face_layers_select:
                        row.prop(layer, property='select', text="", icon='RESTRICT_SELECT_OFF')
                    # hide
                    if settings.ui_face_layers_hide:
                        if layer.hide is True:
                            hide = "HIDE_ON"
                        else:
                            hide = "HIDE_OFF"
                        row.prop(layer, property='hide', text="", icon=hide)
                    # delete
                    if settings.ui_face_layers_delete:
                        row.operator("object.face_layers_delete", text="", icon='X').face_layer_index = index

            # Palettes box
            icon = 'TRIA_RIGHT'
            if globals.palettes_box:
                icon = 'TRIA_DOWN'

            palette_box = sub_col.box()
            row = palette_box.row(align=True)
            row.prop(globals, property='palettes_box', icon=icon, text="Palettes", emboss=False)

            if globals.palettes_box:

                col = palette_box.box().column()

                # Palette
                tool_settings = context.tool_settings.image_paint
                col.template_ID(tool_settings, "palette", new="palette.new")

                # color to add
                brush = context.tool_settings.image_paint.brush
                if not brush:
                    col.label(text="Switch to Texture Paint Mode", icon='ERROR')
                else:
                    if ob.mode != 'OBJECT' and ob.mode != 'TEXTURE_PAINT':
                        empty = col.column()
                        empty.label(text="")
                        empty.scale_y = 5.5
                        col.label(text="Not Available In Edit Mode", icon='ERROR')
                    elif brush.color_type == 'COLOR':
                        row = col.row(align=True)
                        row.template_color_picker(data=brush, property="color", value_slider=True)
                        row = col.row(align=True)
                        row.scale_y = 1.5
                        row.operator("object.face_layers_paste_hex_colors", icon='PASTEDOWN')
                        row.prop(brush, property="color", text="")
                # Palette colors
                if tool_settings.palette:
                    col.template_palette(tool_settings, "palette", color=True)
                row = col.row(align=True)
                row.scale_y = 1.5
                row.operator("object.face_layers_materials_randomize_colors", text="Randomize Materials Colors", icon='COLORSET_10_VEC')

            # Materials box
            icon = 'TRIA_RIGHT'
            if globals.materials_box:
                icon = 'TRIA_DOWN'

            material_box = sub_col.box()
            row = material_box.row(align=True)
            row.prop(globals, property='materials_box', icon=icon, text="Materials", emboss=False)

            if globals.materials_box:
                col = material_box.box().column(align=True)
                row = col.row(align=True)

                row.scale_y = 1.5
                row.operator("object.face_layers_new_material", text="New", icon='MATERIAL')
                row.operator("object.face_layers_materials_assign_by_picking", text="Fill", icon_value=fill_materials.icon_id)

                col.template_ID_preview(globals, property='material_fill', rows=5, cols=5, hide_buttons=True)
                row = col.row(align=True)

                row.scale_y = 1.5
                row.operator('object.face_layers_materials_create', text='Create Materials', icon_value=assign_materials.icon_id)
                row.operator('object.face_layers_materials_clear', text='Clear Materials', icon='X')

        else:
            layout = self.layout
            box = layout.box()
            row = box.row()
            row.scale_y = 1.5
            row.label(text='Select Mesh Object !')


# Mesh Data UI
class DATA_PT_MeshData(bpy.types.Panel):
    bl_label = "Mesh Data"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Face Layers"

    def draw(self, context):
        # custom icons
        pcoll = preview_collections["main"]
        data = pcoll["data"]

        if (ob := context.active_object) and ob.type == 'MESH':
            globals = ob.face_layers_globals
            if ob.face_layers_collection:
                settings = context.scene.face_layers_settings
                align = settings.ui_mesh_data_align

                layout = self.layout
                box = layout.box()
                row = box.row()
                row.scale_y = 1.5
                row.operator('object.mesh_data', icon_value=data.icon_id, text="Calculate Mesh Data").action = 'CALC_FACE_DATA'

                row = box.row()
                split = row.split(factor=settings.ui_mesh_data_name_width / 100, align=align)
                split.label(text="LAYER")
                split.label(text="FACES")
                split.label(text="TRIS")
                split.label(text="NGONS")

                if "face_layers_collection" in ob.keys():
                    collection = ob.face_layers_collection

                    for index in reversed(range(0, len(collection))):
                        layers = [col for col in collection if col.index == index]
                        layer = layers[0]

                        row = box.row()
                        split = row.split(factor=settings.ui_mesh_data_name_width / 100, align=align)
                        box_selected = split.row()
                        box_selected.scale_y = 0.5
                        box_selected.label(text=layer.name)
                        split.label(text="{0}".format(layer.num_of_faces))
                        select_tris = split.operator('object.mesh_data', text="{0}".format(layer.num_of_tris))
                        select_tris.action = 'SELECT_TRIS_LAYER'
                        select_tris.face_layers_collection_index = index
                        select_ngons = split.operator('object.mesh_data', text="{0}".format(layer.num_of_ngons))
                        select_ngons.action = 'SELECT_NGONS_LAYER'
                        select_ngons.face_layers_collection_index = index

                # row = box.row()
                # split = row.split(factor=settings.ui_mesh_data_name_width / 100, align=align)
                # box_selected = split.row()
                # box_selected.scale_y = 0.5
                # box_selected.alert = True
                # box_selected.label(text="Selected Faces")
                # split.label(text="{0}".format(globals.selected_faces))
                # split.operator('object.mesh_data', text="{0}".format(globals.selected_tris)).action = 'SELECT_TRIS_SELECTED'
                # split.operator('object.mesh_data', text="{0}".format(globals.selected_ngons)).action = 'SELECT_NGONS_SELECTED'

                row = box.row()
                split = row.split(factor=settings.ui_mesh_data_name_width / 100, align=align)
                box_all = split.row()
                box_all.scale_y = 0.5
                box_all.alert = True
                box_all.label(text="All Faces")
                split.label(text="{0}".format(globals.all_faces))
                split.operator('object.mesh_data', text="{0}".format(globals.all_tris)).action = 'SELECT_TRIS_ALL'
                split.operator('object.mesh_data', text="{0}".format(globals.all_ngons)).action = 'SELECT_NGONS_ALL'

            else:
                layout = self.layout
                box = layout.box()
                row = box.row()
                row.scale_y = 1.5
                row.label(text='There are no Face Layers !')

        else:
            layout = self.layout
            box = layout.box()
            row = box.row()
            row.scale_y = 1.5
            row.label(text='Select Mesh Object !')


# Mesh Errors UI
class DATA_PT_MeshErrors(bpy.types.Panel):
    bl_label = "Mesh Errors"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Face Layers"

    def draw(self, context):
        pcoll = preview_collections["main"]
        search = pcoll['search']

        if (ob := context.active_object) and ob.type == 'MESH':
            globals = ob.face_layers_globals
            align = context.scene.face_layers_settings.ui_mesh_errors_align

            layout = self.layout
            box = layout.box()
            row = box.row()
            row.scale_y = 1.5
            row.operator('object.mesh_errors', text="Scan Mesh for Errors", icon_value=search.icon_id).action = 'SCAN_MESH_ERRORS'

            row = box.row().box()
            split = row.split(factor=0.4, align=align)
            split.label(text="Loose Faces:")
            split.operator('object.mesh_errors', text="{0}".format(globals.loose_faces)).action = 'SELECT_LOOSE_FACES'
            split.operator('object.mesh_errors', text="Delete").action = 'DELETE_LOOSE_FACES'

            split = row.split(factor=0.4, align=align)
            split.label(text="Loose Edges:")
            split.operator('object.mesh_errors', text="{0}".format(globals.loose_edges)).action = 'SELECT_LOOSE_EDGES'
            split.operator('object.mesh_errors', text="Delete").action = 'DELETE_LOOSE_EDGES'

            split = row.split(factor=0.4, align=align)
            split.label(text="Loose Vertices:")
            split.operator('object.mesh_errors', text="{0}".format(globals.loose_verts)).action = 'SELECT_LOOSE_VERTS'
            split.operator('object.mesh_errors', text="Delete").action = 'DELETE_LOOSE_VERTS'

            row = box.row().box()
            split = row.split(factor=0.4, align=align)
            split.label(text="Zero Area Faces:")
            split.operator('object.mesh_errors', text="{0}".format(globals.zero_area_faces)).action = 'SELECT_ZERO_AREA_FACES'
            split.operator('object.mesh_errors', text="Delete").action = 'DELETE_ZERO_AREA_FACES'

        else:
            layout = self.layout
            box = layout.box()
            row = box.row()
            row.scale_y = 1.5
            row.label(text='Select Mesh Object !')


# Face Layers Settings UI
class SCENE_PT_face_layers_settings(bpy.types.Panel):
    bl_label = "Face Layers UI"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings = context.scene.face_layers_settings
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.label(text="Face Layers:")
        split = col.split(factor=0.5)
        split.label(text="")
        col = split.column()
        col.prop(settings, property='ui_face_layers_align', text="Align UI Buttons")
        col.prop(settings, property='ui_face_layers_name_width', text="Name")
        col.prop(settings, property='ui_face_layers_material_width', text="Material")
        col.prop(settings, property='ui_face_layers_move', text="Move Layers")
        col.prop(settings, property='ui_face_layers_material', text="Material")
        col.prop(settings, property='ui_face_layers_add', text="Add")
        col.prop(settings, property='ui_face_layers_remove', text="Remove")
        col.prop(settings, property='ui_face_layers_select', text="Select")
        col.prop(settings, property='ui_face_layers_hide', text="Hide")
        col.prop(settings, property='ui_face_layers_delete', text="Delete")

        box = layout.box()
        col = box.column()
        col.label(text="Mesh Data:")
        split = col.split(factor=0.5)
        split.label(text="")
        col = split.column()
        col.prop(settings, property='ui_mesh_data_align', text="Align UI Buttons")
        col.prop(settings, property='ui_mesh_data_name_width', text="Name Width")

        box = layout.box()
        col = box.column()
        col.label(text="Mesh Errors:")
        split = col.split(factor=0.5)
        split.label(text="")
        col = split.column()
        col.prop(settings, property='ui_mesh_errors_align', text="Align UI Buttons")


preview_collections = {}
# Keymap variable
FaceLayers_keymaps = []


class MyPieMenu(bpy.types.Menu):
    bl_label = "Face Layers"
    bl_idname = "OBJECT_MT_Face_Layers_pie_menu"

    # def draw(self, context):
    #     pcoll = preview_collections["main"]
    #     pick = pcoll["pick"]

    #     layout = self.layout
    #     pie = layout.menu_pie()    # Initialize pie menu

    #     # Add custom operators to the pie menu
    #     pie.operator("object.face_layers", text="Select", icon_value=pick.icon_id).action = 'SELECT_BY_PICKING'
    def draw(self, context):
        # custom icons
        pcoll = preview_collections["main"]
        pick = pcoll["pick"]

        if (ob := context.active_object) and ob.type == 'MESH':
            globals = ob.face_layers_globals
            collection = ob.face_layers_collection
            settings = context.scene.face_layers_settings

            align = settings.ui_face_layers_align
            layout = self.layout
            box = layout.box()
            main_col = box.column()

            row = main_col.row(align=True)
            row.scale_y = 1.5

            sub_col = main_col.column()

            # select, hide, lock by picking
            col = sub_col.box().column()

            if settings.ui_face_layers_move:
                main_split = col.split()
                split = main_split.split(align=True)
            else:
                split = col.split(align=True)

            col1 = split.column(align=True)
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Select').action = 'SELECT_BY_PICKING'
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Hide').action = 'HIDE_BY_PICKING'
            col1.operator('object.face_layers', icon_value=pick.icon_id, text='Lock').action = 'LOCK_BY_PICKING'

            # select , hide , delete all
            col2 = split.column(align=True)
            col2.prop(globals, property="select_all", icon='RESTRICT_SELECT_OFF', text='Select All')
            if globals.hide_all is True:
                hide = "HIDE_ON"
            else:
                hide = "HIDE_OFF"
            col2.prop(globals, property="hide_all", icon=hide, text='Hide All')
            col2.operator('object.face_layers_delete_all', icon='X', text='Delete All')

            # =======================================================================================================

            # Layers collection
            if checkFLayersCollExist(ob=ob):
                col = sub_col.box().column()

                for index in reversed(range(0, len(ob.face_layers_collection))):
                    row = col.row(align=True)
                    row2 = row.row(align=True)

                    layers = [col for col in collection if col.index == index]
                    layer = layers[0]

                    # lock
                    icon = "UNLOCKED"
                    if layer.locked:
                        icon = "LOCKED"
                    row2.prop(layer, property="locked", icon=icon, text="")

                    split = row.split(factor=settings.ui_face_layers_name_width / 100, align=True)
                    # disable when locked
                    split.enabled = not layer.locked
                    name_row = split.row(align=True)

                    split2 = split.split(factor=settings.ui_face_layers_material_width / 100, align=True)
                    if settings.ui_face_layers_material:
                        split2.prop(layer, property="material", text="")

                    name_row.prop(layer, property="name", text="")
                    # Color
                    try:
                        material = layer.material
                        if material:
                            if node_tree := material.node_tree:
                                links = node_tree.links.values()
                                for link in links:
                                    if link.to_node.type == 'OUTPUT_MATERIAL':
                                        if link.to_socket.name == 'Surface':
                                            node_name = link.from_node.name
                                            split2.prop(material.node_tree.nodes[node_name].inputs[0], property="default_value", text="")
                    except Exception:
                        pass

                    # disable when locked
                    row = row.row(align=align)
                    row.enabled = not layer.locked
                    # add, remove
                    if settings.ui_face_layers_add or settings.ui_face_layers_remove:
                        row2 = row.row(align=align)
                        row2.enabled = (bpy.context.object.mode == 'EDIT')
                        if settings.ui_face_layers_add:
                            op1 = row2.operator('object.face_layers', icon='ADD', text="")
                            op1.action = 'ADD_SELECTION'
                            op1.index = index
                        if settings.ui_face_layers_remove:
                            op2 = row2.operator('object.face_layers', icon='REMOVE', text="")
                            op2.action = 'REMOVE_SELECTION'
                            op2.index = index
                    # select
                    if settings.ui_face_layers_select:
                        row.prop(layer, property='select', text="", icon='RESTRICT_SELECT_OFF')
                    # hide
                    if settings.ui_face_layers_hide:
                        if layer.hide is True:
                            hide = "HIDE_ON"
                        else:
                            hide = "HIDE_OFF"
                        row.prop(layer, property='hide', text="", icon=hide)
                    # delete
                    if settings.ui_face_layers_delete:
                        row.operator("object.face_layers_delete", text="", icon='X').face_layer_index = index

        else:
            layout = self.layout
            box = layout.box()
            row = box.row()
            row.scale_y = 1.5
            row.label(text='Select Mesh Object !')


def register():

    pcoll = bpy.utils.previews.new()

    absolute_path = os.path.dirname(__file__)
    relative_path = "icons"
    path = os.path.join(absolute_path, relative_path)

    pcoll.load("pick", os.path.join(path, "pick.png"), 'IMAGE')
    pcoll.load("add_facelayer", os.path.join(path, "add_facelayer.png"), 'IMAGE')
    pcoll.load("data", os.path.join(path, "data.png"), 'IMAGE')
    pcoll.load("search", os.path.join(path, "search.png"), 'IMAGE')
    pcoll.load("fill", os.path.join(path, "fill.png"), 'IMAGE')
    pcoll.load("assign_materials", os.path.join(path, "assign_materials.png"), 'IMAGE')
    preview_collections["main"] = pcoll

    bpy.utils.register_class(DATA_PT_FaceLayers)
    bpy.utils.register_class(DATA_PT_MeshData)
    bpy.utils.register_class(DATA_PT_MeshErrors)
    bpy.utils.register_class(SCENE_PT_face_layers_settings)
    bpy.utils.register_class(MyPieMenu)

    # Create keymap entry for 3D View Global
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Create the keymap for the 3D View Global
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("wm.call_menu_pie", 'F', 'PRESS', ctrl=True, shift=True, alt=True)  # Ctrl + Shift + F
        kmi.properties.name = "OBJECT_MT_Face_Layers_pie_menu"
        FaceLayers_keymaps.append((km, kmi))


def unregister():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    for km, kmi in FaceLayers_keymaps:
        km.keymap_items.remove(kmi)
    FaceLayers_keymaps.clear()

    bpy.utils.unregister_class(SCENE_PT_face_layers_settings)
    bpy.utils.unregister_class(DATA_PT_MeshErrors)
    bpy.utils.unregister_class(DATA_PT_MeshData)
    bpy.utils.unregister_class(DATA_PT_FaceLayers)
    bpy.utils.unregister_class(MyPieMenu)
