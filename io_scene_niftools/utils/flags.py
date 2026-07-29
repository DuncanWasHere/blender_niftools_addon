"""Helpers for NIF bitflags."""

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

from bpy.props import BoolProperty

# Blender integer properties are signed 32 bit, so a NIF uint with its top bit set has to be
# stored as the negative number with the same bit pattern and converted back on the way out
INT32_SIGN_BIT = 1 << 31
UINT32_MASK = 0xFFFFFFFF


def to_signed_32(n_value):
    n_value &= UINT32_MASK
    return n_value - (1 << 32) if n_value & INT32_SIGN_BIT else n_value


def to_unsigned_32(b_value):
    return b_value & UINT32_MASK


def prettify_prop_name(property_name):
    replacers = [('Hd', 'HD'), ('Lod', 'LOD'), ('Ik', 'IK')]
    prettified = ' '.join(word.capitalize() for word in property_name.split('_'))
    for original, replacement in replacers:
        prettified = prettified.replace(original, replacement)
    return prettified


def bits_of(n_bitfield_type, descriptions=None):
    """
    Build a bit table from a generated NIF bitfield class.
    Only single-bit members are taken.
    """

    descriptions = descriptions or {}
    bits = []
    for b_attr in n_bitfield_type.__members__:
        # the members are BitfieldMember descriptors carrying the position and mask
        # some bitfields also declare uppercase constants for them, but not all of them do
        n_member = n_bitfield_type.__dict__[b_attr]
        if n_member.mask != (1 << n_member.pos):
            continue
        bits.append((b_attr, n_member.pos, prettify_prop_name(b_attr), descriptions.get(b_attr, "")))
    return bits


def named_bits(names, descriptions=None):
    """
    Build a bit table from names listed in bit order, for a NIF field that is a bare uint.
    Used for bitflag fields that aren't typed/named in nifxml but are known from elsewhere.
    None = unknown flag.
    """

    descriptions = descriptions or {}
    bits = []
    for bit, name in enumerate(names):
        if name is None:
            continue
        if isinstance(name, tuple):
            b_attr, label = name
        else:
            b_attr, label = name, prettify_prop_name(name)
        bits.append((b_attr, bit, label, descriptions.get(b_attr, "")))
    return bits


def bit_mask(flag_bits, b_attr):
    for name, bit, _, _ in flag_bits:
        if name == b_attr:
            return 1 << bit
    raise KeyError(b_attr)


def bit_labels(flag_bits, n_value):
    """The labels of the bits set in a value, for logging."""

    return [label for _, bit, label, _ in flag_bits if n_value & (1 << bit)]


def inject_bit_bools(property_group, int_attr, flag_bits):
    """Add a BoolProperty for every named bit of int_attr to a PropertyGroup class."""

    annotations = property_group.__annotations__
    for b_attr, bit, label, description in flag_bits:
        annotations[b_attr] = BoolProperty(name=label,
                                           description=description,
                                           get=_bit_getter(int_attr, bit),
                                           set=_bit_setter(int_attr, bit))


def draw_bit_bools(layout, b_props, flag_bits, columns=2):
    """Draw a checkbox per named bit."""

    grid = layout.grid_flow(columns=columns, even_columns=True, align=True)
    for b_attr, _, _, _ in flag_bits:
        grid.prop(b_props, b_attr)


def packed_value_accessors(int_attr, mask, n_valid_values):
    """Getter and setter for a value packed into part of an integer property."""

    def get_value(b_self):
        n_value = getattr(b_self, int_attr) & mask
        return n_value if n_value in n_valid_values else 0

    def set_value(b_self, n_value):
        setattr(b_self, int_attr, (getattr(b_self, int_attr) & ~mask) | (n_value & mask))

    return get_value, set_value


def _bit_getter(int_attr, bit):
    def get_bit(b_self):
        return bool(getattr(b_self, int_attr) & (1 << bit))

    return get_bit


def _bit_setter(int_attr, bit):
    def set_bit(b_self, b_value):
        n_flags = to_unsigned_32(getattr(b_self, int_attr))
        if b_value:
            n_flags |= (1 << bit)
        else:
            n_flags &= ~(1 << bit)
        setattr(b_self, int_attr, to_signed_32(n_flags))

    return set_bit
