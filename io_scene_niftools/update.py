"""NIF User Interface: custom preferences in the Blender add-ons UI for updating the plugin automatically."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2026 NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****


import os

import bpy

from .utils import resources
from .utils.decorators import register_classes, unregister_classes


class NifResourcePath(bpy.types.PropertyGroup):
    filepath: bpy.props.StringProperty(
        name="Resource",
        description="A folder searched recursively for loose assets, "
                    "or a BSA archive searched for packed assets",
        subtype='FILE_PATH'
    )

    group: bpy.props.StringProperty(
        name="Resource Group",
        description="The games this resource belongs to"
    )


class NifResourcePathAdd(bpy.types.Operator):
    """Add a folder or archive to search for assets"""
    bl_idname = "wm.nif_resource_path_add"
    bl_label = "Add Folder or Archive"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        item = prefs.resource_paths.add()
        item.group = prefs.resource_group
        resources.clear_cache()
        return {'FINISHED'}


class NifResourcePathRemove(bpy.types.Operator):
    """Remove this folder or archive from the asset search"""
    bl_idname = "wm.nif_resource_path_remove"
    bl_label = "Remove"

    index: bpy.props.IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.resource_paths.remove(self.index)
        resources.clear_cache()
        return {'FINISHED'}


class NifResourcePathMove(bpy.types.Operator):
    """Change the order this resource is searched in"""
    bl_idname = "wm.nif_resource_path_move"
    bl_label = "Move"

    index: bpy.props.IntProperty()
    offset: bpy.props.IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        target = self.index + self.offset
        if 0 <= target < len(prefs.resource_paths):
            prefs.resource_paths.move(self.index, target)
        return {'FINISHED'}


class NifResourceAutoDetect(bpy.types.Operator):
    """Find the installed game and add its data folder and archives"""
    bl_idname = "wm.nif_resource_auto_detect"
    bl_label = "Auto Detect Game Paths"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        group = prefs.resource_group

        detected = resources.detect_game_resources(group)
        if not detected:
            self.report({'WARNING'}, f"Could not find an installed game for "
                                     f"'{dict((i[0], i[1]) for i in resources.RESOURCE_GROUPS)[group]}'")
            return {'CANCELLED'}

        existing = {os.path.normcase(os.path.normpath(bpy.path.abspath(item.filepath)))
                    for item in prefs.resource_paths if item.group == group}
        added = 0
        for path in detected:
            if os.path.normcase(os.path.normpath(path)) in existing:
                continue
            item = prefs.resource_paths.add()
            item.group = group
            item.filepath = path
            added += 1

        resources.clear_cache()
        self.report({'INFO'}, f"Added {added} resource path(s) from {detected[0]}")
        return {'FINISHED'}


class NifResourceClearCache(bpy.types.Operator):
    """Re-read the resource folders and archives on the next import"""
    bl_idname = "wm.nif_resource_clear_cache"
    bl_label = "Refresh Resources"

    def execute(self, context):
        resources.clear_cache()
        self.report({'INFO'}, "Resource listings will be rebuilt on the next import")
        return {'FINISHED'}


class NifAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # Asset search preferences
    resource_paths: bpy.props.CollectionProperty(
        name="Resources",
        description="Folders and archives to search for assets when importing",
        type=NifResourcePath
    )

    resource_group: bpy.props.EnumProperty(
        name="Game",
        description="The game whose resources are shown",
        items=resources.RESOURCE_GROUPS,
        default='FALLOUT_3_NV'
    )

    def draw(self, context):
        layout = self.layout

        # Asset search settings
        box = layout.box()
        box.label(text="Resources", icon='FILE_FOLDER')
        box.label(text="Folders are searched recursively for loose assets and win over archives.")

        box.prop(self, "resource_group")

        indices = [i for i, item in enumerate(self.resource_paths) if item.group == self.resource_group]
        if not indices:
            box.label(text="No resources set for this game.", icon='INFO')
        for position, i in enumerate(indices):
            item = self.resource_paths[i]
            row = box.row(align=True)
            path = bpy.path.abspath(item.filepath)
            is_archive = path.lower().endswith((".bsa", ".ba2"))
            row.label(text="", icon='PACKAGE' if is_archive else 'FILE_FOLDER')
            row.prop(item, "filepath", text="")
            sub = row.row(align=True)
            sub.enabled = position > 0
            move_up = sub.operator(NifResourcePathMove.bl_idname, text="", icon='TRIA_UP')
            move_up.index = i
            move_up.offset = -1
            sub = row.row(align=True)
            sub.enabled = position < len(indices) - 1
            move_down = sub.operator(NifResourcePathMove.bl_idname, text="", icon='TRIA_DOWN')
            move_down.index = i
            move_down.offset = 1
            row.operator(NifResourcePathRemove.bl_idname, text="", icon='X').index = i

        row = box.row(align=True)
        row.operator(NifResourcePathAdd.bl_idname, icon='ADD')
        row.operator(NifResourceAutoDetect.bl_idname, icon='VIEWZOOM')
        row.operator(NifResourceClearCache.bl_idname, icon='FILE_REFRESH')


classes = [
    NifResourcePath,
    NifResourcePathAdd,
    NifResourcePathRemove,
    NifResourcePathMove,
    NifResourceAutoDetect,
    NifResourceClearCache,
    NifAddonPreferences
]

def register():
    register_classes(classes, __name__)

def unregister():
    unregister_classes(classes, __name__)
