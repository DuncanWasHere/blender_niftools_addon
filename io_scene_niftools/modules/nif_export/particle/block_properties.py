"""Rebuild NIF particle blocks from the typed Blender properties.

The inverse of modules.nif_import.particle.block_properties, which is what wrote
these properties during import."""

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


from ....utils import serialization


def _field_value(field):
    if field.value_type == "BOOL":
        return field.bool_value
    if field.value_type == "INT":
        return field.int_value
    if field.value_type == "FLOAT":
        return field.float_value
    # Large integer fallback values are distinguishable by their syntax.
    value = field.string_value
    if value and value.lstrip("-").isdigit():
        try:
            return int(value)
        except ValueError:
            pass
    return value


def _insert_path(container, tokens, value):
    token = tokens[0]
    last = len(tokens) == 1
    if isinstance(container, list):
        index = int(token)
        while len(container) <= index:
            container.append(None)
        if last:
            container[index] = value
            return
        if container[index] is None:
            container[index] = [] if tokens[1].isdigit() else {}
        _insert_path(container[index], tokens[1:], value)
        return

    if last:
        container[token] = value
        return
    if token not in container:
        container[token] = [] if tokens[1].isdigit() else {}
    _insert_path(container[token], tokens[1:], value)


def fields_to_dict(block_property):
    fields = {}
    for field in block_property.fields:
        _insert_path(fields, field.path.split("/"), _field_value(field))
    return fields


def restore_particle_blocks(nif_ps, create_block, resolve_reference):
    """Recreate the imported block graph from typed Blender properties.

    Returns a dictionary mapping each role to a list of recreated blocks.
    """

    recreated = []
    roles = {"SYSTEM": [], "DATA": [], "MODIFIER": [], "CONTROLLER": [], "NESTED": []}
    for block_property in nif_ps.nif_blocks:
        n_block = create_block(block_property.block_type)
        serialization.dict_to_struct(n_block, fields_to_dict(block_property))
        recreated.append(n_block)
        roles[block_property.role].append(n_block)

    # Nested blocks are linked by collection index rather than by a fragile name.
    for index, block_property in enumerate(nif_ps.nif_blocks):
        if block_property.parent_index >= 0 and block_property.reference_name:
            parent = recreated[block_property.parent_index]
            setattr(parent, block_property.reference_name, recreated[index])

    by_name = {
        block_property.block_name: recreated[index]
        for index, block_property in enumerate(nif_ps.nif_blocks)
        if block_property.block_name
    }
    for index, block_property in enumerate(nif_ps.nif_blocks):
        n_block = recreated[index]
        for reference in block_property.references:
            target = None
            if reference.target_object:
                target = resolve_reference(reference.target_object)
            if not target:
                target = by_name.get(reference.target_name)
            if not target and reference.target_name:
                target = resolve_reference(reference.target_name)
            if target:
                _assign_reference(n_block, reference.path.split("/"), target)
    return roles


def _assign_reference(instance, tokens, target):
    field_name = tokens[0]
    if len(tokens) == 1:
        setattr(instance, field_name, target)
        return
    array = getattr(instance, field_name)
    index = int(tokens[1])
    if len(array) <= index:
        instance.reset_field(field_name)
        array = getattr(instance, field_name)
    if index < len(array):
        array[index] = target
