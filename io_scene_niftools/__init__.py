"""Blender NifTools Addon for importing and exporting NetImmerse/Gamebryo files."""

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
import tomllib

import bpy

from . import handlers
from .utils import logging
from .utils.decorators import register_modules, unregister_modules
from .utils.logging import NifLog


def get_version():
    """Read the add-on version from the extension manifest."""

    manifest = os.path.join(os.path.dirname(__file__), "blender_manifest.toml")
    with open(manifest, "rb") as f:
        return tomllib.load(f)["version"]


def log_dependencies():
    """Report the versions of the add-on and the generated NIF format library.

    Both nifgen and PyFFI are declared as wheels in blender_manifest.toml, so
    Blender installs them outside the extension directory and puts them on the
    path itself.
    """

    NifLog.info(f"Loading: Blender NifTools Add-on: {get_version()}")

    import nifgen.formats.nif as NifFormat

    # TODO [generated]: Update this and library to have actual versioning
    NifLog.info(f"Loading: NIF Format: {NifFormat.__xml_version__}")


log_dependencies()
logging.init_loggers()

def get_ordered_submodules():
    """Get submodules and return them in the order by which they are to be registered."""

    from . import properties, operators, ui, update
    return [update, properties, operators, ui]

MODS = get_ordered_submodules()


def register():
    """Register the add-on's modules and application handlers."""

    NifLog.debug("Starting registration")

    register_modules(MODS, __name__)
    handlers.register()

def unregister():
    """Unregister the add-on's modules and application handlers."""

    handlers.unregister()
    unregister_modules(MODS, __name__)
