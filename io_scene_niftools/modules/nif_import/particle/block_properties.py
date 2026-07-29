"""Store imported NIF particle blocks as typed Blender properties.

The particle importer used to put an opaque JSON snapshot on ParticleSettings.
This keeps the same lossless intent while storing every leaf value and reference
in registered Blender PropertyGroups, so the data is inspectable, editable and
versionable by Blender.

The reader half lives in modules.nif_export.particle.block_properties."""

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


import numpy as np

from nifgen.base_enum import BaseEnum
from nifgen.base_struct import BaseStruct
from nifgen.bitfield import BasicBitfield
from nifgen.formats.nif import classes as NifClasses


SYSTEM_EXCLUDE = {
    "name", "translation", "rotation", "scale", "flags",
    "num_properties", "properties", "num_extra_data_list", "extra_data_list",
    "controller", "collision_object", "data", "num_modifiers", "modifiers",
    "num_children", "children", "num_effects", "effects",
}
MODIFIER_EXCLUDE = {"target"}
CONTROLLER_EXCLUDE = {"target", "next_controller"}
NESTED_REFERENCE_FIELDS = {
    "data", "interpolator", "visibility_interpolator",
    "collider", "next_collider",
}


def _plain_scalar(value):
    """Return (property kind, plain value), or (None, None) for a non-scalar."""

    if isinstance(value, (BaseEnum, BasicBitfield)):
        return "INT", int(value)
    if isinstance(value, (np.bool_, bool)):
        return "BOOL", bool(value)
    if isinstance(value, (np.integer, int)):
        return "INT", int(value)
    if isinstance(value, (np.floating, float)):
        return "FLOAT", float(value)
    if isinstance(value, str):
        return "STRING", value
    return None, None


def _store_value(block_property, path, value):
    """Flatten structs and numeric arrays into typed leaf properties."""

    if isinstance(value, NifClasses.NiObject):
        return
    if isinstance(value, BaseStruct):
        for field_name, *_ in type(value)._get_filtered_attribute_list(value):
            _store_value(block_property, f"{path}/{field_name}", getattr(value, field_name, None))
        return
    if isinstance(value, np.ndarray):
        for index, element in enumerate(value.tolist()):
            _store_value(block_property, f"{path}/{index}", element)
        return
    if isinstance(value, (list, tuple)):
        for index, element in enumerate(value):
            _store_value(block_property, f"{path}/{index}", element)
        return

    kind, plain = _plain_scalar(value)
    if not kind:
        return
    field = block_property.fields.add()
    field.path = path
    field.value_type = kind
    if kind == "BOOL":
        field.bool_value = plain
    elif kind == "INT":
        # Blender integer properties are signed 32-bit. Particle enums, counts and
        # flags fit that range. Keep a string fallback for pathological vendor data.
        if -(2 ** 31) <= plain < 2 ** 31:
            field.int_value = plain
        else:
            field.value_type = "STRING"
            field.string_value = str(plain)
    elif kind == "FLOAT":
        field.float_value = plain
    else:
        field.string_value = plain


def _store_reference(block_property, path, target, pending_references):
    reference = block_property.references.add()
    reference.path = path
    reference.target_name = str(getattr(target, "name", "") or "")
    if isinstance(target, NifClasses.NiAVObject):
        pending_references.append((reference, target))


def _store_block(nif_ps, n_block, role, pending_references, parent_index=-1,
                 reference_name="", exclude=()):
    block_property = nif_ps.nif_blocks.add()
    block_index = len(nif_ps.nif_blocks) - 1
    block_property.role = role
    block_property.block_type = type(n_block).__name__
    block_property.block_name = str(getattr(n_block, "name", "") or "")
    block_property.parent_index = parent_index
    block_property.reference_name = reference_name

    for field_name, *_ in type(n_block)._get_filtered_attribute_list(n_block):
        if field_name in exclude:
            continue
        value = getattr(n_block, field_name, None)
        if isinstance(value, NifClasses.NiObject):
            if field_name in NESTED_REFERENCE_FIELDS:
                _store_block(nif_ps, value, "NESTED", pending_references,
                             parent_index=block_index, reference_name=field_name)
            else:
                _store_reference(block_property, field_name, value, pending_references)
            continue
        if isinstance(value, (list, tuple, np.ndarray)):
            elements = list(value)
            if elements and all(isinstance(element, NifClasses.NiObject) for element in elements):
                for index, target in enumerate(elements):
                    _store_reference(block_property, f"{field_name}/{index}", target,
                                     pending_references)
                continue
        _store_value(block_property, field_name, value)
    return block_index


def store_particle_blocks(nif_ps, n_system, n_data, n_modifiers, n_controllers):
    """Replace the typed block collection with the imported particle block graph.

    Returns reference-property/NIF-object pairs whose Blender object pointers can
    be resolved after the complete scene tree has been imported.
    """

    nif_ps.nif_blocks.clear()
    pending_references = []
    _store_block(nif_ps, n_system, "SYSTEM", pending_references, exclude=SYSTEM_EXCLUDE)
    if n_data:
        _store_block(nif_ps, n_data, "DATA", pending_references)
    for n_modifier in n_modifiers:
        _store_block(nif_ps, n_modifier, "MODIFIER", pending_references,
                     exclude=MODIFIER_EXCLUDE)
    for n_controller in n_controllers:
        _store_block(nif_ps, n_controller, "CONTROLLER", pending_references,
                     exclude=CONTROLLER_EXCLUDE)
    return pending_references
