bl_info = {
    "name": "Face Layers",
    "author": "Split Studios",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Face Layers",
    "description": "Face Layers Add-on",
    "doc_url": "https://www.splitcg.com",
    "tracker_url": "mailto:splitstudios.games@gmail.com",
    "category": "Face Layers",
}

import importlib
import sys

modulesNames = ["face_data_op", "face_layers_collection", "face_layers_globals", "face_layers_op", "face_layers_settings", "mesh_errors_op", "UI"]

modulesFullNames = {}

for moduleName in modulesNames:
    modulesFullNames[moduleName] = ('{}.{}'.format(__name__, moduleName))

for currentModuleFullName in modulesFullNames.values():
    if currentModuleFullName in sys.modules:
        importlib.reload(sys.modules[currentModuleFullName])
    else:
        globals()[currentModuleFullName] = importlib.import_module(currentModuleFullName)
        setattr(globals()[currentModuleFullName], 'modulesNames', modulesFullNames)


def register():
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'register'):
                sys.modules[currentModuleName].register()


def unregister():
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'unregister'):
                sys.modules[currentModuleName].unregister()


if __name__ == "__main__":
    register()
