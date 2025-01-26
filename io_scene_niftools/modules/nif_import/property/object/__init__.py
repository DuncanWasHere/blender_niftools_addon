"""This script contains helper methods to import objects."""

from math import pi

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2025 NIF File Format Library and Tools contributors.
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
from nifgen.formats.nif import classes as NifClasses


class ObjectProperty:

    # TODO [property] Add delegate processing
    def import_object_properties(self, n_block, b_obj):
        """Import object flags and node types."""

        # Store object flags
        b_obj.nif_object.flags = n_block.flags

        if not issubclass(type(n_block), NifClasses.NiNode):
            return

        # Store type of node
        if isinstance(n_block, NifClasses.BSFadeNode):
            b_obj.nif_object.nodetype = 'BSFadeNode'
        elif isinstance(n_block, NifClasses.NiLODNode):
            b_obj.nif_object.nodetype = 'NiLODNode'
        elif isinstance(n_block, NifClasses.NiBillboardNode):
            b_obj.nif_object.nodetype = 'NiBillboardNode'
        elif isinstance(n_block, NifClasses.BSBlastNode):
            b_obj.nif_object.nodetype = 'BSBlastNode'
        elif isinstance(n_block, NifClasses.BSDamageStage):
            b_obj.nif_object.nodetype = 'BSDamageStage'
        elif isinstance(n_block, NifClasses.BSDebrisNode):
            b_obj.nif_object.nodetype = 'BSDebrisNode'
        elif isinstance(n_block, NifClasses.BSMultiBoundNode):
            b_obj.nif_object.nodetype = 'BSMultiBoundNode'
        elif isinstance(n_block, NifClasses.BSOrderedNode):
            b_obj.nif_object.nodetype = 'BSOrderedNode'
        elif isinstance(n_block, NifClasses.BSValueNode):
            b_obj.nif_object.nodetype = 'BSValueNode'

    def import_extra_data(self, n_node, b_obj):
        """Import extra data blocks for NiNode types."""
        for n_extra in n_node.get_extra_datas():
            if n_extra.name == "UPB":
                if 'BSBoneLOD' in n_extra.string_data or 'Bip' in n_extra.string_data:
                    b_obj.nif_object.upb = n_extra.string_data

    def import_root_extra_data(self, n_root_node, b_obj):
        """Import extra data blocks for root node."""
        for n_extra in n_root_node.get_extra_datas():
            if isinstance(n_extra, NifClasses.NiStringExtraData):
                # weapon location or attachment position
                if n_extra.name == "Prn":
                    b_obj.nif_object.prn_location = n_extra.string_data
                elif n_extra.name == "UPB":
                    if 'BSBoneLOD' in n_extra.string_data or 'Bip' in n_extra.string_data:
                        b_obj.nif_object.upb = n_extra.string_data
            elif isinstance(n_extra, NifClasses.BSXFlags):
                b_obj.nif_object.bsxflags = n_extra.integer_data
            elif isinstance(n_extra, NifClasses.BSInvMarker):
                bs_inv_item = b_obj.nif_object.bs_inv.add()
                bs_inv_item.name = n_extra.name
                bs_inv_item.x = (-n_extra.rotation_x / 1000) % (2 * pi)
                bs_inv_item.y = (-n_extra.rotation_y / 1000) % (2 * pi)
                bs_inv_item.z = (-n_extra.rotation_z / 1000) % (2 * pi)
                bs_inv_item.zoom = n_extra.zoom
