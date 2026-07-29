"""This script contains helper methods for serializing nifgen structs to plain dicts and back."""

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

from nifgen.base_struct import BaseStruct
from nifgen.base_enum import BaseEnum
from nifgen.bitfield import BasicBitfield
from nifgen.formats.nif import classes as NifClasses

from ..utils.logging import NifLog

# sentinel for field values that cannot be stored as plain data
NO_VALUE = object()

# bhkConstraint block types mapped to their hkConstraintType member names
CONSTRAINT_KINDS = {
    "bhkBallAndSocketConstraint": "BALL_AND_SOCKET",
    "bhkHingeConstraint": "HINGE",
    "bhkLimitedHingeConstraint": "LIMITED_HINGE",
    "bhkPrismaticConstraint": "PRISMATIC",
    "bhkRagdollConstraint": "RAGDOLL",
    "bhkStiffSpringConstraint": "STIFF_SPRING",
}

# hkConstraintType member names mapped to the descriptor fields of wrapped constraint data
WRAPPED_KIND_FIELDS = {
    "BALL_AND_SOCKET": "ball_and_socket",
    "HINGE": "hinge",
    "LIMITED_HINGE": "limited_hinge",
    "PRISMATIC": "prismatic",
    "RAGDOLL": "ragdoll",
    "STIFF_SPRING": "stiff_spring",
}


def get_constraint_descriptor(n_bhk_constraint):
    """Return (kind, descriptor) for a bhkConstraint block, where kind is a hkConstraintType
    member name and descriptor is the corresponding constraint info struct.
    Malleable and breakable constraints are unwrapped to their innermost descriptor.
    Returns (None, None) for unsupported types."""
    block_type = type(n_bhk_constraint).__name__
    if block_type in CONSTRAINT_KINDS:
        return CONSTRAINT_KINDS[block_type], n_bhk_constraint.constraint
    if block_type == "bhkMalleableConstraint":
        wrapped = n_bhk_constraint.constraint
    elif block_type == "bhkBreakableConstraint":
        wrapped = n_bhk_constraint.constraint_data
    else:
        return None, None
    kind = NifClasses.HkConstraintType.from_value(wrapped.type).name
    # a breakable constraint can wrap a malleable one
    while kind == "MALLEABLE":
        wrapped = wrapped.malleable
        kind = NifClasses.HkConstraintType.from_value(wrapped.type).name
    if kind not in WRAPPED_KIND_FIELDS:
        return None, None
    return kind, getattr(wrapped, WRAPPED_KIND_FIELDS[kind])


def value_to_plain(value):
    """Convert a single nifgen field value to a plain JSON-storable value.
    Returns NO_VALUE for anything that cannot be stored (block references and their arrays)."""
    if isinstance(value, NifClasses.NiObject):
        # references to other blocks cannot be stored as plain values
        return NO_VALUE
    if isinstance(value, (BaseEnum, BasicBitfield)):
        # nifgen enums and bitfields expose their numeric value through int(),
        # but are not int subclasses. Without this branch controller flags such
        # as MANAGER_CONTROLLED disappear from particle snapshots.
        return int(value)
    if isinstance(value, BaseStruct):
        return struct_to_dict(value)
    if isinstance(value, np.ndarray):
        # numeric arrays are stored as (possibly nested) lists
        return value.tolist()
    if isinstance(value, (list, tuple)):
        # arrays of structs, or of plain values
        elements = [value_to_plain(element) for element in value]
        if any(element is NO_VALUE for element in elements):
            return NO_VALUE
        return elements
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return NO_VALUE


def struct_to_dict(instance, exclude=()):
    """Recursively convert a nifgen struct instance to a dict of plain values suitable for JSON storage.
    Fields referencing other blocks (e.g. constraint entities) are skipped, as are the fields named in exclude."""
    fields = {}
    for field_name, field_type, arguments, _ in type(instance)._get_filtered_attribute_list(instance):
        if field_name in exclude:
            continue
        value = value_to_plain(getattr(instance, field_name, None))
        if value is NO_VALUE:
            NifLog.debug(f"Skipping unserializable field {field_name} on {type(instance).__name__}")
            continue
        fields[field_name] = value
    return fields


def dict_to_struct(instance, fields, exclude=()):
    """Recursively fill a nifgen struct instance from a dict created by struct_to_dict.
    Fields not present in the dict, and those named in exclude, keep their current values."""
    # values are assigned while iterating, so that fields conditioned
    # on earlier fields (e.g. union types, array lengths) resolve correctly
    for field_name, field_type, arguments, _ in type(instance)._get_filtered_attribute_list(instance):
        if field_name in exclude or field_name not in fields:
            continue
        value = fields[field_name]
        if value is None:
            continue
        current = getattr(instance, field_name, None)
        if isinstance(current, BaseStruct):
            if isinstance(value, dict):
                dict_to_struct(current, value)
            else:
                NifLog.warn(f"Stored value for struct field {field_name} is not a dict, skipped")
        elif isinstance(current, (np.ndarray, list, tuple)):
            if isinstance(value, list):
                set_array_field(instance, field_name, value)
            else:
                NifLog.warn(f"Stored value for array field {field_name} is not a list, skipped")
        else:
            try:
                setattr(instance, field_name, field_type.from_value(value))
            except (AttributeError, TypeError, ValueError):
                setattr(instance, field_name, value)
    return instance


def set_array_field(instance, field_name, values):
    """Fill an array field of a nifgen struct from a list created by struct_to_dict.
    The array is resized first, which picks up any length field restored before it."""
    # reset_field re-evaluates the array arguments, so the length field must already be set
    instance.reset_field(field_name)
    array = getattr(instance, field_name)
    if isinstance(array, np.ndarray):
        if array.dtype.names:
            # structured arrays are built from tuples, but json restores them as lists
            values = [tuple(value) for value in values]
        stored = np.array(values, dtype=array.dtype)
        if stored.shape != array.shape:
            NifLog.warn(f"Stored array {field_name} has shape {stored.shape}, expected {array.shape}, skipped")
            return
        array[...] = stored
        return
    if len(array) != len(values):
        NifLog.warn(f"Stored array {field_name} has {len(values)} elements, expected {len(array)}, skipped")
        return
    for element, value in zip(array, values):
        if isinstance(element, BaseStruct):
            dict_to_struct(element, value)
        else:
            NifLog.warn(f"Array {field_name} holds unsupported elements ({type(element).__name__}), skipped")
            return


def block_refs(n_block):
    """Collect the names of the blocks a block points at.
    Pointers cannot be stored as plain data, but their targets can be looked up by name
    again once the blocks around them have been rebuilt."""
    refs = {}
    for field_name, *_ in type(n_block)._get_filtered_attribute_list(n_block):
        value = getattr(n_block, field_name, None)
        if isinstance(value, NifClasses.NiObject):
            name = getattr(value, "name", "")
            if name:
                refs[field_name] = name
        elif isinstance(value, (list, tuple)) and value:
            n_targets = [element for element in value if isinstance(element, NifClasses.NiObject)]
            if len(n_targets) != len(value):
                continue
            names = [getattr(n_target, "name", "") for n_target in n_targets]
            if any(names):
                refs[field_name] = names
    return refs


def block_to_dict(n_block, exclude=(), nested_refs=()):
    """Snapshot a nif block as a dict holding its type and plain field values.
    Ref fields named in nested_refs are snapshotted as nested blocks (e.g. a modifier's data block)."""
    entry = {
        "block_type": type(n_block).__name__,
        "fields": struct_to_dict(n_block, exclude),
    }
    refs = block_refs(n_block)
    if refs:
        entry["refs"] = refs
    for ref_name in nested_refs:
        n_ref_block = getattr(n_block, ref_name, None)
        if isinstance(n_ref_block, NifClasses.NiObject):
            entry[ref_name] = block_to_dict(n_ref_block, nested_refs=nested_refs)
    return entry


def dict_to_block(entry, create_block, exclude=(), nested_refs=()):
    """Rebuild a nif block from a dict created by block_to_dict.
    create_block is called with the block type name and must return a new block of that type."""
    n_block = create_block(entry["block_type"])
    dict_to_struct(n_block, entry["fields"], exclude)
    for ref_name in nested_refs:
        if ref_name in entry:
            setattr(n_block, ref_name, dict_to_block(entry[ref_name], create_block, nested_refs=nested_refs))
    return n_block
