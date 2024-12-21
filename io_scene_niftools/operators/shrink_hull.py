import bmesh
import bpy
from bpy.types import Operator
from io_scene_niftools.utils.decorators import register_classes, unregister_classes


class OperatorShrinkHull(Operator):
    """Shrink Collision Hull"""
    bl_idname = "niftools.shrink_hull"
    bl_label = "Shrink Collision Hull"
    bl_description = "Shrink the collision hull inward by the shrink offset"

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.data:
            self.report({'WARNING'}, "No active object with mesh data found")
            return {'CANCELLED'}

        if obj.type != 'MESH':
            self.report({'WARNING'}, f"{obj.name} is not a mesh. Skipping")
            return {'CANCELLED'}

        # Enter edit mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)

        bm.normal_update()

        # Offset each vertex along its normal
        for vert in bm.verts:
            if vert.select:  # Process only selected vertices
                vert.co -= vert.normal * obj.nifcollision.shrink_offset

        # Update the mesh and return to object mode
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"Shrank collision hull by {obj.nifcollision.shrink_offset}")
        return {'FINISHED'}

classes = [
    OperatorShrinkHull
]


def register():
    register_classes(classes, __name__)


def unregister():
    unregister_classes(classes, __name__)
