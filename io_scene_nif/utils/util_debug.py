"""This script contains helper methods to enable debugging the plugin execution during runtime."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2012, NIF File Format Library and Tools contributors.
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
import sys

from io_scene_nif import NifLog

CLIENT_PORT = 5678
REMOTE_PORT = 1234


def start_debug(port=REMOTE_PORT):
    NifLog.debug("Setting up debugger")
    try:
        pydev_src = os.environ['PYDEVDEBUG']
        NifLog.debug(f"Found: {pydev_src}")
        if sys.path.count(pydev_src) < 1:
            sys.path.append(pydev_src)
    except KeyError:
        NifLog.info("Dev: Sys variable not set")
        return

    try:
        from pydevd_pycharm import settrace
    except ImportError:
        NifLog.debug("Dev: Import failed to find pydevd module.\nPython Remote Debugging Server not found")
        return

    try:
        settrace('localhost', port=port, stdoutToServer=True, stderrToServer=True, suspend=True)
    except Exception as e:
        NifLog.debug("Unable to connect to remote debugging server")
        NifLog.debug(e)
        return

    NifLog.debug("Debugger setup completed")
