"""This script contains helper methods to managing importing texture into specific slots."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2026 NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the following
#   disclaimer in the documentation and/or other materials provided
#   with the distribution.
#
# * Neither the name of the NIF File Format Library and Tools
#   project nor the names of its contributors may be used to endorse
#   or promote products derived from this software without specific
#   prior written permission.
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


import struct

import bpy
from .....modules.nif_import.property.texture.loader import TextureLoader
from .....utils.consts import (TEX_SLOTS, BS_TEX_SLOTS, FALLOUT_SHADER_TYPES,
                                            FALLOUT_UNLIT_TYPES, GAMEBRYO_SHADER, NIF_SHADER_GROUPS,
                                            UNLIT_GROUPS, FALLOFF_GROUPS)
from .....utils.logging import NifLog
from .....utils.nodes import nodes_iterate
from .....utils.singleton import NifOp
from nifgen.formats.nif import classes as NifClasses


"""Names (ordered by default index) of shader texture slots for Sid Meier's Railroads and similar games."""
EXTRA_SHADER_TEXTURES = [
    "EnvironmentMapIndex",
    "NormalMapIndex",
    "SpecularIntensityIndex",
    "EnvironmentIntensityIndex",
    "LightCubeMapIndex",
    "ShadowTextureIndex"]


# NiMaterialProperty fields that a shader type simply ignores. They are still in the
# block, but they change nothing, so there is no socket for them and nothing to preserve.
UNUSED_SHADER_VALUES = {shader_type: ("Glossiness",) for shader_type in FALLOUT_UNLIT_TYPES}

# Shader flags that switch on an effect the node tree can show, and the socket that mirrors
# each one. The flag stays the value that is written to the nif; the socket is only there so
# the viewport reflects it.
SHADER_FLAG_SOCKETS = {
    'environment_mapping': "Environment Mapping",
    'refraction': "Refraction",
    'fire_refraction': "Fire Refraction",
    'parallax_shader_index_15': "Parallax",
    'parallax_occulsion': "Parallax Occlusion",
    # BSShaderFlags2 bit 31, which nif.xml leaves unnamed but Fallout 3 uses for real time
    # reflections. Blender has an equivalent, so this one shows something real.
    'unknown_10': "Real Time Reflections",
}


def sync_shader_flag_visuals(b_mat):
    """Push the shader flags that have a visual effect onto the shader group's sockets."""

    b_group_node = get_shader_group_node(b_mat)
    if b_group_node is None:
        return

    for b_flag, socket_name in SHADER_FLAG_SOCKETS.items():
        if socket_name in b_group_node.inputs:
            b_group_node.inputs[socket_name].default_value = 1.0 if b_mat.nif_shader.get(b_flag) else 0.0


def get_or_rebuild_group(group_name, expected_sockets, variant=None):
    """Return an empty node group ready to be built, reusing the existing one by name.

    A blend file may already hold a group of this name that an older version of the
    addon built with different sockets, or one built for a different specular model.
    Values would then silently fail to apply and fall back to defaults, so such a group
    is emptied and rebuilt from scratch.
    """

    b_group = bpy.data.node_groups.get(group_name)
    if b_group is None:
        b_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
        if variant is not None:
            b_group["niftools_variant"] = variant
        return b_group

    current = [item.name for item in b_group.interface.items_tree
               if item.item_type == 'SOCKET' and item.in_out == 'INPUT']
    stored_variant = b_group.get("niftools_variant", b_group.get("specular_model"))
    if current == list(expected_sockets) and b_group.nodes \
            and (variant is None or stored_variant == variant):
        if variant is not None:
            b_group["niftools_variant"] = variant
        return b_group

    NifLog.info(f"Rebuilding the '{group_name}' node group, which was made by an older "
                f"version of the addon and no longer matches the NIF fields")
    b_group.nodes.clear()
    for item in list(b_group.interface.items_tree):
        b_group.interface.remove(item)
    if variant is not None:
        b_group["niftools_variant"] = variant
    return b_group


def get_shader_group_node(b_mat):
    """Return the shader property node group of a material, or None."""

    if not (b_mat and b_mat.use_nodes and b_mat.node_tree):
        return None
    for b_node in b_mat.node_tree.nodes:
        if (isinstance(b_node, bpy.types.ShaderNodeGroup) and b_node.node_tree
                and b_node.node_tree.name in NIF_SHADER_GROUPS):
            return b_node
    return None


def sync_shader_group(b_mat, shader_type):
    """
    Point the material's shader group node at the group for a shader type.

    Called when the shader type is changed by hand, so that the node tree follows the block
    the material claims to be. The sockets of the two groups do not line up one for one, so
    values that have no counterpart in the new group are left at its defaults rather than
    being carried across.
    """

    b_group_node = get_shader_group_node(b_mat)
    if b_group_node is None:
        # nothing to retarget: Skyrim's shaders and materials with no group build their own
        # node trees on import
        return

    if shader_type not in NIF_SHADER_GROUPS:
        return

    b_group_node.node_tree = create_shader_group(shader_type)
    NifLog.info(f"Switched the shader node group of '{b_mat.name}' to {shader_type}.")


ADDITIVE_NODE = "Additive Blending"


def apply_additive_blending(b_mat, b_group_node, additive):
    """Connect the NIF shader group without corrupting its texture alpha.

    Blender 5's EEVEE viewport has no material setting for arbitrary source and
    destination framebuffer blend factors. The previous approximation added a second
    Transparent BSDF to a group that already performs alpha transparency. That could
    yield a zero-alpha material in Material Preview while its emission remained visible
    in Rendered mode, and it made low-alpha atlas backgrounds accumulate as rectangles.

    Use ordinary alpha blending for the Blender preview. The exact NIF blend factors
    remain on ``nif_alpha`` and are exported unchanged.
    """

    b_tree = b_mat.node_tree
    b_output = next((n for n in b_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    b_add = b_tree.nodes.get(ADDITIVE_NODE)
    if b_output is None:
        return

    if b_add:
        b_tree.nodes.remove(b_add)
    b_transparent = b_tree.nodes.get(f"{ADDITIVE_NODE} Transparent")
    if b_transparent:
        b_tree.nodes.remove(b_transparent)
    b_tree.links.new(b_group_node.outputs[0], b_output.inputs['Surface'])


def apply_alpha_links(b_mat, b_group_node):
    """
    Link or unlink the alpha channels according to the use alpha toggle.

    The toggle decides whether the material gets a NiAlphaProperty at all, so with it off
    nothing about the texture's alpha channel should reach the surface. Doing this every
    time the settings change, rather than once while importing, is what makes the toggle
    work in both directions instead of only reflecting how the material was imported.

    The images themselves are read as channel packed, so their colour is the same either
    way and only the linking has to change.
    """

    b_tree = b_mat.node_tree
    use_alpha = b_mat.nif_alpha.use_alpha

    # (alpha socket, the socket whose source node carries that alpha, extra condition)
    for socket_name, source_name, wanted in (
            ("Diffuse Alpha", "Diffuse Map", True),
            ("Vertex Alpha", "Vertex Color", bool(b_mat.nif_shader.get("vertex_alpha")))):
        b_socket = b_group_node.inputs.get(socket_name)
        if b_socket is None:
            continue

        for b_link in list(b_socket.links):
            b_tree.links.remove(b_link)
        b_socket.default_value = 1.0

        if not (use_alpha and wanted):
            continue

        b_source = b_group_node.inputs.get(source_name)
        if b_source is None or not b_source.links:
            continue
        b_from_node = b_source.links[0].from_node
        if len(b_from_node.outputs) > 1:
            b_tree.links.new(b_from_node.outputs[1], b_socket)


def apply_alpha_property(b_mat, b_group_node=None):
    """Show the NiAlphaProperty settings of a material in the viewport.

    Called when a material is imported and whenever the alpha settings are edited,
    so what is seen in Blender follows the alpha property rather than only living
    in the panel.
    """

    if b_group_node is None:
        b_group_node = get_shader_group_node(b_mat)
    if b_group_node is None or "Alpha Test" not in b_group_node.inputs:
        return

    apply_alpha_links(b_mat, b_group_node)

    b_alpha = b_mat.nif_alpha
    alpha_property = bool(b_mat.nif_alpha.use_alpha)
    alpha_test = alpha_property and b_group_node.inputs["Alpha Test"].default_value > 0.0

    # The blend factors decide what the surface does to what is behind it.
    # ONE, ZERO writes the colour straight out, so the surface is opaque however
    # transparent its texture is; anything scaled by ONE on the destination adds to the
    # background instead of covering it.
    source, destination = b_alpha.source_blend_mode, b_alpha.destination_blend_mode
    blend_enabled = alpha_property and b_alpha.enable_blending
    blend_is_opaque = blend_enabled and source == 'ONE' and destination == 'ZERO'
    blend_is_additive = blend_enabled and destination == 'ONE'
    smooth_alpha = blend_enabled and not blend_is_opaque

    apply_additive_blending(b_mat, b_group_node, blend_is_additive)

    b_group_node.inputs["Alpha Enabled"].default_value = 1.0 if alpha_property else 0.0
    if "Alpha Blend" in b_group_node.inputs:
        b_group_node.inputs["Alpha Blend"].default_value = 1.0 if smooth_alpha else 0.0

    if alpha_test and b_alpha.alpha_test_function != 'TEST_GREATER':
        NifLog.warn(f"Alpha test function '{b_alpha.alpha_test_function}' cannot be shown in Blender, "
                    f"which always tests for greater than the threshold")

    # Alpha testing gives a hard cutout, so dithered costs nothing: the alpha is already
    # either 0 or 1 and there is nothing left to dither, while depth is written per
    # fragment so cutouts sort correctly against everything.
    # Real blending is the awkward case. Dithered would turn it into noise, so blended is
    # used for its smooth result, at the price of blended surfaces being sorted per object
    # rather than per fragment. Overlapping transparent surfaces can therefore draw in the
    # wrong order; switching such a material to Dithered in its settings resolves it.
    if smooth_alpha and not alpha_test:
        # additive surfaces have to stay blended, as they must let the background through
        render_method = 'BLENDED'
    else:
        render_method = 'DITHERED'
    try:
        b_mat.surface_render_method = render_method
    except AttributeError:
        # older blender versions use the blend method instead
        if not (smooth_alpha or alpha_test):
            b_mat.blend_method = 'OPAQUE'
        else:
            b_mat.blend_method = 'BLEND' if render_method == 'BLENDED' else 'HASHED'

    # Water sheets and other effects commonly fold over themselves. Rendering only the
    # nearest layer punches holes through those meshes, so keep self-overlap enabled.
    # Blender 5 renamed this setting; set the old alias too for earlier supported versions.
    try:
        b_mat.use_transparency_overlap = True
    except AttributeError:
        pass
    b_mat.show_transparent_back = True

    if blend_is_additive:
        NifLog.info(f"Material '{b_mat.name}' adds its light to the background "
                    f"({source} to {destination})")
    elif blend_is_opaque:
        NifLog.info(f"Material '{b_mat.name}' writes straight out ({source} to {destination}), "
                    f"so it is drawn opaque")


def create_cube_map_group():
    """Create (or return the existing) node group that samples a cube map.

    Blender has no cube map texture node and loads a DDS cube map as its six faces
    stacked into one vertical strip, in the DirectX order +X, -X, +Y, -Y, +Z, -Z.
    This group turns a direction vector into the strip coordinate of the face it hits.
    """

    b_group = get_or_rebuild_group(
        "Cube Map", ["Vector", "Face Size"], "directx-y-up-texel-inset-2")
    if b_group.nodes:
        # already built and up to date
        return b_group

    b_interface = b_group.interface
    b_interface.new_socket(name="Vector", socket_type='NodeSocketVector', in_out='INPUT')
    b_face_size = b_interface.new_socket(
        name="Face Size", socket_type='NodeSocketFloat', in_out='INPUT')
    b_face_size.default_value = 1.0
    b_face_size.min_value = 1.0
    b_interface.new_socket(name="Vector", socket_type='NodeSocketVector', in_out='OUTPUT')

    b_nodes = b_group.nodes
    b_links = b_group.links
    b_input = b_nodes.new('NodeGroupInput')
    b_output = b_nodes.new('NodeGroupOutput')

    def math(operation, in_1, in_2=None, in_3=None):
        node = b_nodes.new('ShaderNodeMath')
        node.operation = operation
        for socket, value in zip(node.inputs, (in_1, in_2, in_3)):
            if isinstance(value, bpy.types.NodeSocket):
                b_links.new(value, socket)
            elif value is not None:
                socket.default_value = value
        return node.outputs[0]

    b_separate = b_nodes.new('ShaderNodeSeparateXYZ')
    b_links.new(b_input.outputs["Vector"], b_separate.inputs[0])
    blender_x, blender_y, blender_z = (b_separate.outputs[i] for i in range(3))

    # Blender is Z-up, while DDS cube maps use DirectX's Y-up face convention.
    # Swapping Y and Z also changes from Blender's right-handed axes to the DirectX
    # convention expected by the face-orientation table below.
    x, y, z = blender_x, blender_z, blender_y
    abs_x, abs_y, abs_z = (math('ABSOLUTE', axis) for axis in (x, y, z))

    # which axis the direction points along decides the face, and the largest
    # component is the distance to that face
    x_major = math('GREATER_THAN', abs_x, math('MAXIMUM', abs_y, abs_z))
    y_major = math('MULTIPLY', math('GREATER_THAN', abs_y, abs_z),
                   math('SUBTRACT', 1.0, x_major))
    z_major = math('SUBTRACT', 1.0, math('ADD', x_major, y_major))

    x_positive = math('GREATER_THAN', x, 0.0)
    y_positive = math('GREATER_THAN', y, 0.0)
    z_positive = math('GREATER_THAN', z, 0.0)
    negate = lambda value: math('MULTIPLY', value, -1.0)
    invert = lambda value: math('SUBTRACT', 1.0, value)

    # exactly one of these is 1, selecting the face the direction points at
    selectors = {
        'X+': math('MULTIPLY', x_major, x_positive),
        'X-': math('MULTIPLY', x_major, invert(x_positive)),
        'Y+': math('MULTIPLY', y_major, y_positive),
        'Y-': math('MULTIPLY', y_major, invert(y_positive)),
        'Z+': math('MULTIPLY', z_major, z_positive),
        'Z-': math('MULTIPLY', z_major, invert(z_positive)),
    }

    def select(face_values):
        """Sum each face's value weighted by whether that face was selected."""
        total = None
        for face, value in face_values.items():
            term = math('MULTIPLY', selectors[face], value)
            total = term if total is None else math('ADD', total, term)
        return total

    # face local coordinates, following the DirectX cube map convention
    major = math('MAXIMUM', abs_x, math('MAXIMUM', abs_y, abs_z))
    safe_major = math('MAXIMUM', major, 1e-6)

    face_u = select({'X+': negate(z), 'X-': z, 'Y+': x, 'Y-': x, 'Z+': x, 'Z-': negate(x)})
    face_v = select({'X+': negate(y), 'X-': negate(y), 'Y+': z, 'Y-': negate(z),
                     'Z+': negate(y), 'Z-': negate(y)})

    u = math('MULTIPLY_ADD', math('DIVIDE', face_u, safe_major), 0.5, 0.5)
    v = math('MULTIPLY_ADD', math('DIVIDE', face_v, safe_major), 0.5, 0.5)

    # The six faces share one 2D atlas in Blender. Sampling exactly at 0 or 1 lets
    # bilinear filtering cross into the unrelated face above or below in the strip,
    # drawing a border around cube faces. Clamp the local coordinates to the centers
    # of their outer texels: [0.5 / size, 1 - 0.5 / size].
    safe_face_size = math('MAXIMUM', b_input.outputs["Face Size"], 1.0)
    inverse_face_size = math('DIVIDE', 1.0, safe_face_size)
    half_texel = math('MULTIPLY', inverse_face_size, 0.5)
    texel_span = math('SUBTRACT', 1.0, inverse_face_size)
    u = math('MULTIPLY_ADD', u, texel_span, half_texel)
    v = math('MULTIPLY_ADD', v, texel_span, half_texel)

    # face index in the strip: +X 0, -X 1, +Y 2, -Y 3, +Z 4, -Z 5
    face_index = select({'X+': 0.0, 'X-': 1.0, 'Y+': 2.0, 'Y-': 3.0, 'Z+': 4.0, 'Z-': 5.0})

    # the strip runs top to bottom, while blender's v axis runs bottom to top
    strip_v = math('DIVIDE', math('SUBTRACT', math('SUBTRACT', 6.0, face_index), v), 6.0)

    b_combine = b_nodes.new('ShaderNodeCombineXYZ')
    b_links.new(u, b_combine.inputs[0])
    b_links.new(strip_v, b_combine.inputs[1])
    b_links.new(b_combine.outputs[0], b_output.inputs["Vector"])

    nodes_iterate(b_group, b_output)
    return b_group


def create_shader_group(shader_type):
    """Create (or return the existing) node group reproducing the shading of a NIF shader
    property block. The group is named after the block it stands for, and its input sockets
    hold the values of that block, so what is seen in Blender is what the nif contains.

    Lit shaders use a traditional diffuse + specular glossy model rather than PBR, matching
    the fixed function shading these games actually use.
    """

    unlit = shader_type in UNLIT_GROUPS

    # what every one of them shares: a texture, vertex colours, an emissive term and the
    # NiAlphaProperty settings. Without an alpha property the mesh is drawn opaque whatever
    # its alpha holds, and the test turns the alpha into a hard cutout.
    sockets = [
        ("Diffuse Map", 'NodeSocketColor', (1, 1, 1, 1)),
        ("Diffuse Alpha", 'NodeSocketFloat', 1.0),
        ("Vertex Color", 'NodeSocketColor', (1, 1, 1, 1)),
        ("Vertex Alpha", 'NodeSocketFloat', 1.0),
        ("Glow Map", 'NodeSocketColor', (1, 1, 1, 1)),
        ("Emissive Color", 'NodeSocketColor', (0, 0, 0, 1)),
        ("Emissive Mult", 'NodeSocketFloat', 1.0),
        ("Alpha", 'NodeSocketFloat', 1.0),
        ("Alpha Enabled", 'NodeSocketFloat', 0.0),
        ("Alpha Blend", 'NodeSocketFloat', 0.0),
        ("Alpha Test", 'NodeSocketFloat', 0.0),
        ("Alpha Test Threshold", 'NodeSocketFloat', 0.5),
    ]

    lit_sockets = [
        ("Normal Map", 'NodeSocketColor', (0.5, 0.5, 1, 1)),
        # the normal map alpha channel is the gloss map: it scales the specular
        # highlight. Materials whose normal map has no alpha channel get no
        # specularity at all, hence the default of 0
        ("Gloss Map", 'NodeSocketFloat', 0.0),
        # NiMaterialProperty glossiness: the phong specular exponent, roughly 0 to 128
        ("Glossiness", 'NodeSocketFloat', 10.0),
    ]

    if shader_type == GAMEBRYO_SHADER:
        # the colours of the NiMaterialProperty, which is what actually shades these games
        sockets[4:4] = lit_sockets
        sockets += [
            ("Ambient Color", 'NodeSocketColor', (1, 1, 1, 1)),
            ("Diffuse Color", 'NodeSocketColor', (1, 1, 1, 1)),
            ("Specular Color", 'NodeSocketColor', (1, 1, 1, 1)),
        ]
    else:
        # every BSShaderProperty carries this field, even the ones that ignore it
        sockets += [("Environment Map Scale", 'NodeSocketFloat', 1.0)]
        if not unlit:
            sockets[4:4] = lit_sockets
            sockets[-1:-1] = [
                ("Environment Map", 'NodeSocketColor', (0, 0, 0, 1)),
                ("Environment Mask", 'NodeSocketColor', (1, 1, 1, 1)),
            ]

    if shader_type in FALLOFF_GROUPS:
        # the falloff fades the surface by viewing angle. The angles are cosines: 1 is
        # straight on, 0 is edge on, so the opacity is looked up between the two
        sockets += [
            ("Falloff Start Angle", 'NodeSocketFloat', 1.0),
            ("Falloff Stop Angle", 'NodeSocketFloat', 0.0),
            ("Falloff Start Opacity", 'NodeSocketFloat', 1.0),
            ("Falloff Stop Opacity", 'NodeSocketFloat', 0.0),
        ]

    if shader_type == 'BSShaderPPLightingProperty':
        sockets += [
            ("Parallax Map", 'NodeSocketFloat', 0.0),
            ("Refraction Strength", 'NodeSocketFloat', 0.0),
            ("Refraction Fire Period", 'NodeSocketFloat', 0.0),
            ("Parallax Max Passes", 'NodeSocketFloat', 4.0),
            ("Parallax Scale", 'NodeSocketFloat', 1.0),
        ]
        # Mirrors of the shader flags that switch these effects on. The flags themselves stay
        # the thing that is written to the nif; these only let the node tree show what they do,
        # and are pushed here whenever a flag changes.
        sockets += [(name, 'NodeSocketFloat', 0.0) for name in SHADER_FLAG_SOCKETS.values()]

    # the specular model changes the nodes but not the sockets, so it is recorded on the
    # group and any group built with the other model is rebuilt
    # read from the snapshot rather than NifOp.props, because this also runs from the shader
    # type update callback, long after the import operator that set those properties is gone
    phong = bool(NifOp.use_phong_specular)
    # Include an internal revision so blend files containing an older copy of this shared
    # group are rebuilt after its rendering math changes.
    variant = f"{'phong' if phong else 'glossy'}-2"
    b_group = get_or_rebuild_group(shader_type, [name for name, _type, _default in sockets], variant)
    if b_group.nodes:
        # already built and up to date
        return b_group
    b_group["specular_model"] = variant

    b_interface = b_group.interface
    for socket_name, socket_type, socket_default in sockets:
        b_socket = b_interface.new_socket(name=socket_name, socket_type=socket_type, in_out='INPUT')
        b_socket.default_value = socket_default
    b_interface.new_socket(name="Shader", socket_type='NodeSocketShader', in_out='OUTPUT')

    b_nodes = b_group.nodes
    b_links = b_group.links
    b_input = b_nodes.new('NodeGroupInput')
    b_output = b_nodes.new('NodeGroupOutput')

    def new_mix(blend_type, in_1, in_2, fac=1.0):
        b_mix = b_nodes.new('ShaderNodeMixRGB')
        b_mix.blend_type = blend_type
        for socket, value in ((b_mix.inputs[0], fac), (b_mix.inputs[1], in_1), (b_mix.inputs[2], in_2)):
            if isinstance(value, bpy.types.NodeSocket):
                b_links.new(value, socket)
            elif value is not None:
                socket.default_value = value
        return b_mix

    def new_math(operation, in_1, in_2=None, use_clamp=False):
        b_math = b_nodes.new('ShaderNodeMath')
        b_math.operation = operation
        b_math.use_clamp = use_clamp
        for socket, value in zip(b_math.inputs, (in_1, in_2)):
            if isinstance(value, bpy.types.NodeSocket):
                b_links.new(value, socket)
            elif value is not None:
                socket.default_value = value
        return b_math

    group_in = b_input.outputs

    # base color: diffuse texture * vertex color
    b_base_rgb = new_mix('MULTIPLY', group_in["Diffuse Map"], group_in["Vertex Color"])
    if "Diffuse Color" in group_in:
        # the games before the shader properties tint the texture by the material colour
        b_base_rgb = new_mix('MULTIPLY', b_base_rgb.outputs[0], group_in["Diffuse Color"])

    # combined opacity: texture alpha * vertex alpha * material alpha
    b_alpha_1 = new_math('MULTIPLY', group_in["Diffuse Alpha"], group_in["Vertex Alpha"])
    b_alpha_blended = new_math('MULTIPLY', b_alpha_1.outputs[0], group_in["Alpha"])

    if "Falloff Start Angle" in b_input.outputs:
        # How square on the surface is: the cosine of the angle between the way the surface
        # faces and the way we are looking at it, which is what the nif angles are given as.
        b_geometry = b_nodes.new('ShaderNodeNewGeometry')
        b_facing = b_nodes.new('ShaderNodeVectorMath')
        b_facing.operation = 'DOT_PRODUCT'
        b_links.new(b_geometry.outputs['Incoming'], b_facing.inputs[0])
        b_links.new(b_geometry.outputs['Normal'], b_facing.inputs[1])

        # look the opacity up between the two angles, clamped so that beyond either end it
        # holds at that end's opacity
        b_falloff = b_nodes.new('ShaderNodeMapRange')
        b_falloff.clamp = True
        b_links.new(b_facing.outputs['Value'], b_falloff.inputs['Value'])
        b_links.new(group_in["Falloff Stop Angle"], b_falloff.inputs['From Min'])
        b_links.new(group_in["Falloff Start Angle"], b_falloff.inputs['From Max'])
        b_links.new(group_in["Falloff Stop Opacity"], b_falloff.inputs['To Min'])
        b_links.new(group_in["Falloff Start Opacity"], b_falloff.inputs['To Max'])

        b_alpha_blended = new_math('MULTIPLY', b_alpha_blended.outputs[0], b_falloff.outputs[0])

    # Blending and testing are independent bits. With blending off, a passing fragment is
    # opaque. With both on, the test only rejects pixels below the threshold and must retain
    # the original fractional alpha for pixels that pass.
    b_blend_off = new_math('SUBTRACT', 1.0, group_in["Alpha Blend"])
    b_blend_on = new_math('MULTIPLY', b_alpha_blended.outputs[0], group_in["Alpha Blend"])
    b_alpha_after_blend = new_math('ADD', b_blend_off.outputs[0], b_blend_on.outputs[0])

    b_alpha_passes = new_math('GREATER_THAN', b_alpha_blended.outputs[0],
                              group_in["Alpha Test Threshold"])
    b_test_off_fac = new_math('SUBTRACT', 1.0, group_in["Alpha Test"])
    b_test_off = new_math('MULTIPLY', b_alpha_after_blend.outputs[0], b_test_off_fac.outputs[0])
    b_test_pass = new_math('MULTIPLY', b_alpha_after_blend.outputs[0], b_alpha_passes.outputs[0])
    b_test_on = new_math('MULTIPLY', b_test_pass.outputs[0], group_in["Alpha Test"])
    b_alpha_used = new_math('ADD', b_test_off.outputs[0], b_test_on.outputs[0])

    # Without an alpha property neither blending nor testing applies.
    b_alpha_off = new_math('SUBTRACT', 1.0, group_in["Alpha Enabled"])
    b_alpha_on = new_math('MULTIPLY', b_alpha_used.outputs[0], group_in["Alpha Enabled"])
    b_alpha_final = new_math('ADD', b_alpha_off.outputs[0], b_alpha_on.outputs[0])

    # emissive: the glow map tinted by the emissive colour and scaled by the multiplier.
    # the glow map socket defaults to white, so a material without one still emits its
    # emissive colour, exactly as the games do
    b_emissive_rgb = new_mix('MULTIPLY', group_in["Glow Map"], group_in["Emissive Color"])
    b_emission = b_nodes.new('ShaderNodeEmission')
    b_links.new(b_emissive_rgb.outputs[0], b_emission.inputs['Color'])
    b_links.new(group_in["Emissive Mult"], b_emission.inputs['Strength'])

    if unlit:
        # No lighting: the texture is shown as it is. The emissive multiplier scales it,
        # but the emissive colour is not added on top, which would double the brightness
        # of a shader that is already showing the texture at full strength.
        b_shaded = b_nodes.new('ShaderNodeEmission')
        b_links.new(b_base_rgb.outputs[0], b_shaded.inputs['Color'])
        b_links.new(group_in["Emissive Mult"], b_shaded.inputs['Strength'])
        b_nodes.remove(b_emission)
        b_nodes.remove(b_emissive_rgb)
    else:
        # directx normal map (+X -Y +Z), so invert green before the tangent space conversion
        b_separate = b_nodes.new('ShaderNodeSeparateColor')
        b_links.new(group_in["Normal Map"], b_separate.inputs[0])
        b_invert_g = new_math('SUBTRACT', 1.0, b_separate.outputs[1])
        b_combine = b_nodes.new('ShaderNodeCombineColor')
        b_links.new(b_separate.outputs[0], b_combine.inputs[0])
        b_links.new(b_invert_g.outputs[0], b_combine.inputs[1])
        b_links.new(b_separate.outputs[2], b_combine.inputs[2])
        b_normal_map = b_nodes.new('ShaderNodeNormalMap')
        b_links.new(b_combine.outputs[0], b_normal_map.inputs['Color'])
        b_shading_normal = b_normal_map.outputs[0]

        if "Parallax Map" in group_in:
            # The game offsets the texture lookup along the view ray by the height map, which
            # a node group cannot march. Bumping the shading normal by the same height gives
            # the surface relief that setting is there to produce, scaled the same way, so the
            # scale is worth something to look at rather than a number in a box.
            b_parallax_on = new_math('MAXIMUM', group_in["Parallax"], group_in["Parallax Occlusion"])
            b_parallax_distance = new_math('MULTIPLY', group_in["Parallax Scale"],
                                           b_parallax_on.outputs[0])
            b_bump = b_nodes.new('ShaderNodeBump')
            b_links.new(group_in["Parallax Map"], b_bump.inputs['Height'])
            b_links.new(b_parallax_distance.outputs[0], b_bump.inputs['Distance'])
            b_links.new(b_normal_map.outputs[0], b_bump.inputs['Normal'])
            b_shading_normal = b_bump.outputs[0]

        # diffuse lighting
        b_diffuse_bsdf = b_nodes.new('ShaderNodeBsdfDiffuse')
        b_links.new(b_base_rgb.outputs[0], b_diffuse_bsdf.inputs['Color'])
        b_links.new(b_shading_normal, b_diffuse_bsdf.inputs['Normal'])

        # the games use phong specular, spec = glossmap * pow(N.H, glossiness), where the
        # glossiness is an exponent that runs to about 128 rather than a 0 to 1 factor.
        # Convert that exponent to microfacet roughness with a = sqrt(2 / (n + 2)).
        b_gloss_clamped = new_math('MAXIMUM', group_in["Glossiness"], 0.0)
        b_gloss_add = new_math('ADD', b_gloss_clamped.outputs[0], 2.0)
        b_gloss_div = new_math('DIVIDE', 2.0, b_gloss_add.outputs[0])
        b_roughness = new_math('POWER', b_gloss_div.outputs[0], 0.5)

        if phong:
            # Phong specular against a light sitting at the camera, the way NifSkope
            # shows it. With the light direction equal to the view direction the half
            # vector is the view vector, so the highlight is pow(N.V, glossiness).
            # Being emission rather than a BSDF, it never mirrors the world, which is
            # what made the glossy version wash surfaces out.
            b_geometry = b_nodes.new('ShaderNodeNewGeometry')
            b_facing = b_nodes.new('ShaderNodeVectorMath')
            b_facing.operation = 'DOT_PRODUCT'
            b_links.new(b_shading_normal, b_facing.inputs[0])
            b_links.new(b_geometry.outputs['Incoming'], b_facing.inputs[1])

            b_facing_clamped = new_math('MAXIMUM', b_facing.outputs['Value'], 0.0)
            b_highlight = new_math('POWER', b_facing_clamped.outputs[0], group_in["Glossiness"])
            b_spec_strength = new_math('MULTIPLY', b_highlight.outputs[0], group_in["Gloss Map"])

            b_specular = b_nodes.new('ShaderNodeEmission')
            b_links.new(b_spec_strength.outputs[0], b_specular.inputs['Strength'])
            if "Specular Color" in group_in:
                b_links.new(group_in["Specular Color"], b_specular.inputs['Color'])
        else:
            # the gloss map scales the highlight, so a black gloss map means no specular
            b_spec_rgb = new_mix('MIX', (0, 0, 0, 1), (1, 1, 1, 1))
            b_links.new(group_in["Gloss Map"], b_spec_rgb.inputs[0])

            b_specular = b_nodes.new('ShaderNodeBsdfGlossy')
            b_links.new(b_spec_rgb.outputs[0], b_specular.inputs['Color'])
            b_links.new(b_roughness.outputs[0], b_specular.inputs['Roughness'])
            b_links.new(b_shading_normal, b_specular.inputs['Normal'])

        # the highlight is added on top of the full diffuse, as the game does; mixing
        # between them instead would take the diffuse away and leave the surface dark
        b_lit = b_nodes.new('ShaderNodeAddShader')
        b_links.new(b_diffuse_bsdf.outputs[0], b_lit.inputs[0])
        b_links.new(b_specular.outputs[0], b_lit.inputs[1])

        if "Ambient Color" in group_in:
            # the ambient term lifts the surface out of full darkness, the way the fixed
            # function pipeline these games use applies it
            b_ambient_rgb = new_mix('MULTIPLY', b_base_rgb.outputs[0], group_in["Ambient Color"])
            b_ambient = b_nodes.new('ShaderNodeEmission')
            b_links.new(b_ambient_rgb.outputs[0], b_ambient.inputs['Color'])
            b_ambient.inputs['Strength'].default_value = 0.1
            b_lit_ambient = b_nodes.new('ShaderNodeAddShader')
            b_links.new(b_lit.outputs[0], b_lit_ambient.inputs[0])
            b_links.new(b_ambient.outputs[0], b_lit_ambient.inputs[1])
            b_lit = b_lit_ambient

        b_shaded = b_nodes.new('ShaderNodeAddShader')
        b_links.new(b_lit.outputs[0], b_shaded.inputs[0])
        b_links.new(b_emission.outputs[0], b_shaded.inputs[1])

        if "Environment Map" in group_in:
            # The reflection is added over the lit surface rather than replacing it. The mask
            # and the scale set how much is added, so a material with a real diffuse and
            # normal map keeps them and only gains a reflection on the masked areas.
            b_env_mask = b_nodes.new('ShaderNodeRGBToBW')
            b_links.new(group_in["Environment Mask"], b_env_mask.inputs[0])
            if "Environment Mapping" in group_in:
                # the flag is what turns the reflection on, so an unflagged material shows none
                b_env_gate = new_math('MULTIPLY', group_in["Environment Map Scale"],
                                      group_in["Environment Mapping"])
                b_env_strength = new_math('MULTIPLY', b_env_mask.outputs[0],
                                          b_env_gate.outputs[0])
            else:
                b_env_strength = new_math('MULTIPLY', b_env_mask.outputs[0],
                                          group_in["Environment Map Scale"])
            b_env_emission = b_nodes.new('ShaderNodeEmission')
            b_env_emission.name = "Environment Map Shader"
            b_links.new(group_in["Environment Map"], b_env_emission.inputs['Color'])
            b_links.new(b_env_strength.outputs[0], b_env_emission.inputs['Strength'])

            b_add_env = b_nodes.new('ShaderNodeAddShader')
            b_add_env.name = "Environment Map Add"
            b_links.new(b_shaded.outputs[0], b_add_env.inputs[0])
            b_links.new(b_env_emission.outputs[0], b_add_env.inputs[1])
            b_shaded = b_add_env

        if "Real Time Reflections" in group_in:
            # The game reflects the scene around the object rather than a baked cube map,
            # which is what a glossy BSDF does: it picks up the world and whatever probes
            # the scene has. Its sharpness comes from the same glossiness as the highlight,
            # and the gloss map decides where the surface is reflective at all.
            b_reflection = b_nodes.new('ShaderNodeBsdfGlossy')
            b_links.new(b_roughness.outputs[0], b_reflection.inputs['Roughness'])
            b_links.new(b_shading_normal, b_reflection.inputs['Normal'])
            b_reflect_rgb = new_mix('MIX', (0, 0, 0, 1), (1, 1, 1, 1))
            b_links.new(group_in["Gloss Map"], b_reflect_rgb.inputs[0])
            b_links.new(b_reflect_rgb.outputs[0], b_reflection.inputs['Color'])

            # mixing rather than scaling the shader, so turning the flag off leaves exactly
            # the tree that was there before it was turned on
            b_with_reflection = b_nodes.new('ShaderNodeAddShader')
            b_links.new(b_shaded.outputs[0], b_with_reflection.inputs[0])
            b_links.new(b_reflection.outputs[0], b_with_reflection.inputs[1])

            b_reflect_mix = b_nodes.new('ShaderNodeMixShader')
            b_links.new(group_in["Real Time Reflections"], b_reflect_mix.inputs[0])
            b_links.new(b_shaded.outputs[0], b_reflect_mix.inputs[1])
            b_links.new(b_with_reflection.outputs[0], b_reflect_mix.inputs[2])
            b_shaded = b_reflect_mix

    if "Refraction Strength" in group_in:
        # The game bends what is behind the surface using the normal map, which is what a
        # refraction BSDF does, so the strength drives how much of it replaces the shading.
        # Either flag switches it on; the fire variant only differs by scrolling the map,
        # which a still node tree has nothing to show for.
        b_refraction = b_nodes.new('ShaderNodeBsdfRefraction')
        b_links.new(b_base_rgb.outputs[0], b_refraction.inputs['Color'])
        b_links.new(b_shading_normal, b_refraction.inputs['Normal'])

        b_refract_on = new_math('MAXIMUM', group_in["Refraction"], group_in["Fire Refraction"])
        b_refract_fac = new_math('MULTIPLY', b_refract_on.outputs[0], group_in["Refraction Strength"],
                                 use_clamp=True)

        b_refract_mix = b_nodes.new('ShaderNodeMixShader')
        b_links.new(b_refract_fac.outputs[0], b_refract_mix.inputs[0])
        b_links.new(b_shaded.outputs[0], b_refract_mix.inputs[1])
        b_links.new(b_refraction.outputs[0], b_refract_mix.inputs[2])
        b_shaded = b_refract_mix

    # opacity
    b_transparent = b_nodes.new('ShaderNodeBsdfTransparent')
    b_mix_shader = b_nodes.new('ShaderNodeMixShader')
    b_links.new(b_alpha_final.outputs[0], b_mix_shader.inputs[0])
    b_links.new(b_transparent.outputs[0], b_mix_shader.inputs[1])
    b_links.new(b_shaded.outputs[0], b_mix_shader.inputs[2])
    b_links.new(b_mix_shader.outputs[0], b_output.inputs["Shader"])

    nodes_iterate(b_group, b_output)
    return b_group


class NodeWrapper:
    __instance = None

    @staticmethod
    def get():
        """Static access method."""

        if NodeWrapper.__instance is None:
            NodeWrapper()
        return NodeWrapper.__instance

    def __init__(self):
        """Virtually private constructor."""

        if NodeWrapper.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            NodeWrapper.__instance = self

            self.texture_loader = TextureLoader()
            self.b_mat = None
            self.b_shader_tree = None

            self.emissive_color = (0.0, 0.0, 0.0, 1.0)

            # raw nif shader and material values, keyed by fallout shader group socket name
            self.shader_values = {}

            # Shader Nodes
            self.b_mat_output = None # Material Output
            self.b_principled_bsdf = None # Principled BSDF
            self.b_glossy_bsdf = None # Glossy BSDF
            self.b_normal_map = None # Normal Map
            self.b_color_attribute = None # Color Attribute
            self.b_diffuse_pass = None # Mix Color
            self.b_specular_pass = None # Float Curve
            self.b_gloss_pass = None # Mix Color
            self.b_emissive_pass = None # Mix Color
            self.b_normal_pass = None # Invert Y
            self.b_parallax_pass = None # Vector Displacement
            self.b_environment_pass = None # Texture Coordinate

            # Texture Nodes
            self.b_textures = [None] * 10

    @staticmethod
    def uv_node_name(uv_index):
        return f"TexCoordIndex_{uv_index}"

    def set_uv_map(self, b_texture_node, uv_index=0, reflective=False):
        """Attaches a vector node describing the desired coordinate transforms to the texture node's UV input."""

        if reflective:
            uv = self.b_shader_tree.nodes.new('ShaderNodeTexCoord')
            self.b_shader_tree.links.new(uv.outputs[6], b_texture_node.inputs[0])
        # use supplied UV maps for everything else, if present
        else:
            uv_name = self.uv_node_name(uv_index)
            existing_node = self.b_shader_tree.nodes.get(uv_name)
            if not existing_node:
                uv = self.b_shader_tree.nodes.new('ShaderNodeUVMap')
                uv.name = uv_name
            else:
                uv = existing_node
            self.b_shader_tree.links.new(uv.outputs[0], b_texture_node.inputs[0])

    def global_uv_offset_scale(self, x_scale, y_scale, x_offset, y_offset, clamp_x, clamp_y):
        # get all uv nodes (by name, since we are importing they have the predefined name
        # and then we don't have to loop through every node
        uv_nodes = {}
        uv_index = 0
        while True:
            uv_name = self.uv_node_name(uv_index)
            uv_node = self.b_shader_tree.nodes.get(uv_name)
            if uv_node and isinstance(uv_node, bpy.types.ShaderNodeUVMap):
                uv_nodes[uv_index] = uv_node
                uv_index += 1
            else:
                break

        clip_texture = clamp_x and clamp_y

        for uv_index, uv_node in uv_nodes.items():
            # for each of those, create a new uv output node and relink
            split_node = self.b_shader_tree.nodes.new('ShaderNodeSeparateXYZ')
            split_node.name = f"Separate UV{uv_index}"
            split_node.label = split_node.name
            combine_node = self.b_shader_tree.nodes.new('ShaderNodeCombineXYZ')
            combine_node.name = f"Combine UV{uv_index}"
            combine_node.label = combine_node.name

            x_node = self.b_shader_tree.nodes.new('ShaderNodeMath')
            x_node.name = f"X offset and scale UV{uv_index}"
            x_node.label = x_node.name
            x_node.operation = 'MULTIPLY_ADD'
            # only clamp on the math node when we're not clamping on both directions
            # otherwise, the clip on the image texture node will take care of it
            x_node.use_clamp = clamp_x and not clip_texture
            x_node.inputs[1].default_value = x_scale
            x_node.inputs[2].default_value = x_offset
            self.b_shader_tree.links.new(split_node.outputs[0], x_node.inputs[0])
            self.b_shader_tree.links.new(x_node.outputs[0], combine_node.inputs[0])

            y_node = self.b_shader_tree.nodes.new('ShaderNodeMath')
            y_node.name = f"Y offset and scale UV{uv_index}"
            y_node.label = y_node.name
            y_node.operation = 'MULTIPLY_ADD'
            y_node.use_clamp = clamp_y and not clip_texture
            y_node.inputs[1].default_value = y_scale
            y_node.inputs[2].default_value = y_offset
            self.b_shader_tree.links.new(split_node.outputs[1], y_node.inputs[0])
            self.b_shader_tree.links.new(y_node.outputs[0], combine_node.inputs[1])

            # get all the texture nodes to which it is linked, and re-link them to the uv output node
            for link in uv_node.outputs[0].links:
                # get the target link/socket
                target_node = link.to_node
                if isinstance(link.to_node, bpy.types.ShaderNodeTexImage):
                    target_socket = link.to_socket
                    # delete the existing link
                    self.b_shader_tree.links.remove(link)
                    # make new ones
                    self.b_shader_tree.links.new(combine_node.outputs[0], target_socket)
                    # if we clamp in both directions, clip the images:
                    if clip_texture:
                        target_node.extension = 'CLIP'
            self.b_shader_tree.links.new(uv_node.outputs[0], split_node.inputs[0])
        pass

    def clear_nodes(self):
        """Clear existing shader nodes from the node tree and restart with minimal setup."""
        
        self.b_shader_tree = self.b_mat.node_tree

        # Remove existing shader nodes
        for node in self.b_shader_tree.nodes:
            self.b_shader_tree.nodes.remove(node)

        self.b_glossy_bsdf = None
        self.b_add_shader = None
        self.b_normal_map = None
        self.b_color_attribute = None
        self.b_diffuse_pass = None
        self.b_specular_pass = None
        self.b_gloss_pass = None
        self.b_emissive_pass = None
        self.b_normal_pass = None
        self.b_parallax_pass = None
        self.b_environment_pass = None

        self.b_textures = [None] * 8
        self.shader_values = {}

        # Add basic shader nodes
        self.b_principled_bsdf = self.b_shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
        self.b_mat_output = self.b_shader_tree.nodes.new('ShaderNodeOutputMaterial')
        self.b_shader_tree.links.new(self.b_principled_bsdf.outputs[0], self.b_mat_output.inputs[0])

    def shader_group_name(self):
        """
        The node group this material is displayed with, or None for a Principled BSDF.

        Every shader that has a group of its own is shown through it, so what is on screen
        is the nif's own values rather than an approximation. The Skyrim lighting shader is
        the one left on the Principled BSDF.
        """

        if not self.b_mat:
            return None

        b_scene = bpy.context.scene.niftools_scene
        shader_type = self.b_mat.nif_shader.bs_shadertype

        if b_scene.is_fo3() and shader_type in FALLOUT_SHADER_TYPES:
            return shader_type
        if b_scene.is_skyrim() and shader_type == 'BSEffectShaderProperty':
            return shader_type
        if not (b_scene.is_fo3() or b_scene.is_skyrim()):
            # Oblivion and earlier shade from the material and texturing properties
            return GAMEBRYO_SHADER
        return None

    def fallout_mode(self):
        """True when the material is displayed with a node group instead of a Principled BSDF."""
        return self.shader_group_name() is not None

    def connect_to_pass(self, b_node_pass, b_texture_node, texture_type="Detail"):
        """Connect to an image premixing pass."""

        # connect if the pass has been established, ie. the base texture already exists
        if b_node_pass:
            rgb_mixer = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
            # these textures are overlaid onto the base
            if texture_type in ("Detail", "Reflect"):
                rgb_mixer.inputs[0].default_value = 1
                rgb_mixer.blend_type = "OVERLAY"
            # these textures are multiplied with the base texture (currently only vertex color)
            elif texture_type == "Vertex_Color":
                rgb_mixer.inputs[0].default_value = 1
                rgb_mixer.blend_type = "MULTIPLY"
            # these textures use their alpha channel as a mask over the input pass
            elif texture_type == "Decal":
                self.b_shader_tree.links.new(b_texture_node.outputs[1], rgb_mixer.inputs[0])
            self.b_shader_tree.links.new(b_node_pass.outputs[0], rgb_mixer.inputs[1])
            self.b_shader_tree.links.new(b_texture_node.outputs[0], rgb_mixer.inputs[2])
            return rgb_mixer
        return b_texture_node

    def connect_vertex_colors_to_pass(self, ):
        # if ob.data.vertex_colors:
        self.b_color_attribute = self.b_shader_tree.nodes.new('ShaderNodeVertexColor')
        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, self.b_color_attribute, texture_type="Vertex_Color")

    def connect_to_output(self, has_vcol=False):
        if self.fallout_mode():
            self.build_fallout_tree(has_vcol)
            return

        if has_vcol:
            self.connect_vertex_colors_to_pass()

        if self.b_diffuse_pass:
            self.b_shader_tree.links.new(self.b_diffuse_pass.outputs[0], self.b_principled_bsdf.inputs[0])

            if self.b_textures[0] and self.b_mat.nif_alpha.use_alpha and has_vcol and self.b_mat.nif_shader.vertex_alpha:
                mixAAA = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
                mixAAA.inputs[0].default_value = 1
                mixAAA.blend_type = "MULTIPLY"
                self.b_shader_tree.links.new(self.b_textures[0].outputs[1], mixAAA.inputs[1])
                self.b_shader_tree.links.new(self.b_color_attribute.outputs[1], mixAAA.inputs[2])
                self.b_shader_tree.links.new(mixAAA.outputs[0], self.b_principled_bsdf.inputs[4])
            elif self.b_textures[0] and self.b_mat.nif_alpha.use_alpha:
                self.b_shader_tree.links.new(self.b_textures[0].outputs[1], self.b_principled_bsdf.inputs[4])
            elif has_vcol and self.b_mat.nif_shader.vertex_alpha:
                self.b_shader_tree.links.new(self.b_color_attribute.outputs[1], self.b_principled_bsdf.inputs[4])

        nodes_iterate(self.b_shader_tree, self.b_mat_output)

    def build_fallout_tree(self, has_vcol=False):
        """Replace the default Principled BSDF tree with the fallout shader node group,
        linking the imported textures to its sockets and storing the raw nif values on it."""

        b_nodes = self.b_shader_tree.nodes
        b_links = self.b_shader_tree.links

        # only the texture and coordinate nodes survive
        for b_node in list(b_nodes):
            if not isinstance(b_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment,
                                       bpy.types.ShaderNodeUVMap, bpy.types.ShaderNodeTexCoord)):
                b_nodes.remove(b_node)
        self.b_principled_bsdf = None

        shader_type = self.shader_group_name()
        b_group_node = b_nodes.new('ShaderNodeGroup')
        b_group_node.node_tree = create_shader_group(shader_type)
        b_group_node.name = shader_type
        b_group_node.label = shader_type
        self.b_mat_output = b_nodes.new('ShaderNodeOutputMaterial')
        b_links.new(b_group_node.outputs[0], self.b_mat_output.inputs[0])

        # store the raw nif values on the group sockets
        for socket_name, value in self.shader_values.items():
            b_socket = b_group_node.inputs.get(socket_name)
            if b_socket:
                b_socket.default_value = value
            elif socket_name in UNUSED_SHADER_VALUES.get(shader_type, ()):
                # the block carries this field but the shader ignores it, so it is junk
                NifLog.debug(f"'{shader_type}' ignores '{socket_name}', so it is not shown")
            else:
                # a value read from the nif with nowhere to go would be silently lost
                NifLog.warn(f"The '{shader_type}' node group has no '{socket_name}' socket, "
                            f"so that value could not be applied (this is a bug in the addon)")

        # link the imported textures by their slot labels. The alpha channels are left to
        # apply_alpha_links, so the use alpha toggle is the one thing that decides them.
        for b_texture_node in [n for n in b_nodes if isinstance(n, (bpy.types.ShaderNodeTexImage,
                                                                    bpy.types.ShaderNodeTexEnvironment))]:
            label = b_texture_node.label
            if label in (BS_TEX_SLOTS.DIFFUSE_MAP, TEX_SLOTS.BASE):
                b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Diffuse Map"])
                if b_texture_node.image:
                    # Read the alpha channel as a channel of its own rather than as coverage
                    # of the colour. A transparent pixel then keeps the colour it holds, so
                    # the same texture is right whether the material uses its alpha or not,
                    # and nothing has to be changed when that is toggled.
                    b_texture_node.image.alpha_mode = 'CHANNEL_PACKED'
                # whether that alpha is linked is decided by apply_alpha_links below
            elif label in (BS_TEX_SLOTS.NORMAL_MAP, TEX_SLOTS.NORMAL) and "Normal Map" in b_group_node.inputs:
                b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Normal Map"])
                # the normal map alpha channel is the gloss map; a normal map whose
                # format has no alpha channel gets no specularity, unless environment
                # mapping is on, which forces specularity regardless of the format
                if self.image_has_alpha_channel(b_texture_node.image):
                    b_links.new(b_texture_node.outputs[1], b_group_node.inputs["Gloss Map"])
                elif self.b_mat.nif_shader.get("environment_mapping"):
                    b_group_node.inputs["Gloss Map"].default_value = 1.0
            elif label in (BS_TEX_SLOTS.GLOW_MAP, TEX_SLOTS.GLOW):
                b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Glow Map"])
            elif label == BS_TEX_SLOTS.ENVIRONMENT_MAP and "Environment Map" in b_group_node.inputs:
                self.link_environment_texture(b_texture_node, b_group_node)
            elif label == BS_TEX_SLOTS.ENVIRONMENT_MASK and "Environment Mask" in b_group_node.inputs:
                b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Environment Mask"])
            elif label == BS_TEX_SLOTS.PARALLAX_MAP and "Parallax Map" in b_group_node.inputs:
                # the height the parallax shading is bumped by, inside the group with
                # everything else the shader block holds
                b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Parallax Map"])

        if has_vcol:
            self.b_color_attribute = b_nodes.new('ShaderNodeVertexColor')
            b_links.new(self.b_color_attribute.outputs[0], b_group_node.inputs["Vertex Color"])

        self.apply_alpha_property(b_group_node)
        # import writes the flags straight as ID properties, which does not run their update,
        # so the sockets that mirror them are filled in once the group is wired up
        sync_shader_flag_visuals(self.b_mat)

        nodes_iterate(self.b_shader_tree, self.b_mat_output)

    def link_environment_texture(self, b_texture_node, b_group_node):
        """Link an environment map so it is sampled the way the game samples it.

        A DDS cube map is loaded by Blender as its six faces stacked into one vertical
        strip, which needs the reflection direction converted to a strip coordinate.
        Other environment maps are flat reflection textures and are sampled directly.
        """

        b_nodes = self.b_shader_tree.nodes
        b_links = self.b_shader_tree.links

        b_texture_coord = b_nodes.new('ShaderNodeTexCoord')
        b_image = b_texture_node.image
        is_cube_strip = b_image and b_image.size[0] and b_image.size[1] == b_image.size[0] * 6

        if is_cube_strip:
            b_cube = b_nodes.new('ShaderNodeGroup')
            b_cube.node_tree = create_cube_map_group()
            b_cube.name = b_cube.label = "Cube Map"
            b_cube.inputs["Face Size"].default_value = float(b_image.size[0])
            b_links.new(b_texture_coord.outputs['Reflection'], b_cube.inputs['Vector'])
            b_links.new(b_cube.outputs['Vector'], b_texture_node.inputs[0])
            # faces must not bleed into each other at their edges
            b_texture_node.extension = 'EXTEND'
        else:
            if b_image:
                NifLog.info(f"Environment map '{b_image.name}' is not a cube map "
                            f"({b_image.size[0]}x{b_image.size[1]}), sampling it as a reflection map")
            b_links.new(b_texture_coord.outputs['Reflection'], b_texture_node.inputs[0])

        b_links.new(b_texture_node.outputs[0], b_group_node.inputs["Environment Map"])

    def apply_alpha_property(self, b_group_node):
        """Apply the NiAlphaProperty settings of this material to its shader group."""

        apply_alpha_property(self.b_mat, b_group_node)

    def create_and_link(self, slot_name, n_texture):

        slot_name_lower = slot_name.lower().replace(' ', '_')

        # The shaders that name a texture directly usually sit beside a NiTexturingProperty
        # pointing at the same one, so whichever is read first fills the slot and the
        # second would only add a texture node that nothing uses.
        if slot_name_lower in ("base", "diffuse_map") and self.b_textures[0] is not None:
            NifLog.debug(f"The base texture is already loaded, so this copy is skipped")
            return

        import_func_name = f"link_{slot_name_lower}_node"
        import_func = getattr(self, import_func_name, None)
        if not import_func:
            NifLog.debug(f"Could not find texture linking function {import_func_name}.")
            return
        b_texture = self.create_texture_slot(slot_name_lower, n_texture)
        import_func(b_texture)

    def create_texture_slot(self, slot_name, n_texture):
        """Create an image texture node from a NIF source texture."""

        # TODO [texture]: Refactor this to separate code paths?
        if isinstance(n_texture, NifClasses.TexDesc):
            # When processing a NiTexturingProperty
            b_image = self.texture_loader.import_texture_source(n_texture.source)
            uv_layer_index = n_texture.uv_set
        else:
            # When processing a BSShaderProperty - n_texture is a bare string
            b_image = self.texture_loader.import_texture_source(n_texture)
            uv_layer_index = 0

        # create a texture node
        if slot_name == "environment_map" and not self.fallout_mode():
            # an equirectangular projection is only right for the old code path;
            # the shader groups sample the map themselves, see link_environment_texture
            b_texture_node = self.b_mat.node_tree.nodes.new('ShaderNodeTexEnvironment')
            self.set_uv_map(b_texture_node, uv_index=uv_layer_index, reflective=True)
        else:
            b_texture_node = self.b_mat.node_tree.nodes.new('ShaderNodeTexImage')
            self.set_uv_map(b_texture_node, uv_index=uv_layer_index)

        b_texture_node.image = b_image
        b_texture_node.interpolation = "Smart"

        # TODO [texture]: Support clamping and interpolation settings

        return b_texture_node

    def link_base_node(self, b_texture_node):
        """Link a base texture node to the shader tree."""

        self.b_textures[0] = b_texture_node
        b_texture_node.label = TEX_SLOTS.BASE

        if self.fallout_mode():
            # the fallout shader group links the textures when the tree is finalized
            return

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node)

        if bpy.context.scene.niftools_scene.game == 'OBLIVION':
            base_name, extension = b_texture_node.image.name.rsplit(".", 1)
            self.create_and_link("normal", f"{base_name}_n.{extension}")

    def link_dark_node(self, b_texture_node):
        """Link a dark texture node to the shader tree."""

        # TODO: Set this up

        self.b_textures[1] = b_texture_node
        b_texture_node.label = TEX_SLOTS.DARK

    def link_detail_node(self, b_texture_node):
        """Link a detail texture node to the shader tree."""

        self.b_textures[2] = b_texture_node
        b_texture_node.label = TEX_SLOTS.DETAIL

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Detail")

    def link_gloss_node(self, b_texture_node):
        """Link a gloss texture node to the shader tree."""

        self.b_textures[3] = b_texture_node
        b_texture_node.label = TEX_SLOTS.GLOSS

        self.create_specular_pass(b_texture_node)

        self.create_gloss_pass(b_texture_node)

    def link_glow_node(self, b_texture_node):
        """Link a glow texture node to the shader tree."""

        self.b_textures[4] = b_texture_node
        b_texture_node.label = TEX_SLOTS.GLOW

        self.create_emissive_pass(b_texture_node)

    def link_bump_map_node(self, b_texture_node):
        """Link a bump map texture node to the shader tree."""

        # TODO: Set this up

        self.b_textures[5] = b_texture_node
        b_texture_node.label = TEX_SLOTS.BUMP_MAP

    def link_normal_node(self, b_texture_node):
        """Link a normal texture node to the shader tree."""

        self.b_textures[6] = b_texture_node
        b_texture_node.label = TEX_SLOTS.NORMAL
        b_texture_node.image.colorspace_settings.name = 'Non-Color'

        self.create_normal_pass(b_texture_node)

        if bpy.context.scene.niftools_scene.game == 'OBLIVION' and self.image_has_alpha(b_texture_node):
            self.create_gloss_pass(b_texture_node)
        else:
            self.b_principled_bsdf.inputs['Roughness'].default_value = 1.0
            self.b_principled_bsdf.inputs['IOR'].default_value = 1.0

    def link_decal_0_node(self, b_texture_node):
        """Link a decal 0 texture node to the shader tree."""

        self.b_textures[7] = b_texture_node
        b_texture_node.label = TEX_SLOTS.DECAL_0

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_decal_1_node(self, b_texture_node):
        """Link a decal 1 texture node to the shader tree."""

        self.b_textures[8] = b_texture_node
        b_texture_node.label = TEX_SLOTS.DECAL_1

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_decal_2_node(self, b_texture_node):
        """Link a decal 2 texture node to the shader tree."""

        self.b_textures[9] = b_texture_node
        b_texture_node.label = TEX_SLOTS.DECAL_2

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node, texture_type="Decal")

    def link_diffuse_map_node(self, b_texture_node):
        """Link a Bethesda diffuse map texture node to the shader tree."""

        self.b_textures[0] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.DIFFUSE_MAP

        if self.fallout_mode():
            return

        self.b_diffuse_pass = self.connect_to_pass(self.b_diffuse_pass, b_texture_node)

    def link_normal_map_node(self, b_texture_node):
        """Link a Bethesda normal map texture node to the shader tree."""

        self.b_textures[1] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.NORMAL_MAP
        b_texture_node.image.colorspace_settings.name = "Non-Color"

        if self.fallout_mode():
            return

        self.create_normal_pass(b_texture_node)

        # Specularity is only enabled if normal map isn't fully opaque
        if self.image_has_alpha(b_texture_node.image):
            self.create_gloss_pass(b_texture_node)
        else:
            self.b_principled_bsdf.inputs['Roughness'].default_value = 1.0
            self.b_principled_bsdf.inputs['IOR'].default_value = 1.0

    def link_glow_map_node(self, b_texture_node):
        """Link a Bethesda glow map texture node to the shader tree."""

        self.b_textures[2] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.GLOW_MAP

        if self.fallout_mode():
            return

        self.create_emissive_pass(b_texture_node)

    def link_parallax_map_node(self, b_texture_node):
        """Link a Bethesda parallax map texture node to the shader tree."""

        self.b_textures[3] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.PARALLAX_MAP

        if self.fallout_mode():
            return

        self.create_parallax_pass(b_texture_node)

    def link_environment_map_node(self, b_texture_node):
        """Link a Bethesda environment map texture node to the shader tree."""

        self.b_textures[4] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.ENVIRONMENT_MAP

        if self.fallout_mode():
            return

        self.create_environment_pass(b_texture_node)

    def link_environment_mask_node(self, b_texture_node):
        """Link a Bethesda environment mask texture node to the shader tree."""

        self.b_textures[5] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.ENVIRONMENT_MASK

        if self.fallout_mode():
            return

        self.create_environment_mask_pass(b_texture_node)

    def link_subsurface_tint_map_node(self, b_texture_node):
        """Link a Bethesda subsurface map texture node to the shader tree."""

        # TODO: Set this up

        self.b_textures[6] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.SUBSURFACE_TINT_MAP

    def link_backlight_map_node(self, b_texture_node):
        """Link a Bethesda backlight map texture node to the shader tree."""

        # TODO: Set this up

        self.b_textures[7] = b_texture_node
        b_texture_node.label = BS_TEX_SLOTS.BACKLIGHT_MAP

    def create_specular_pass(self, b_texture_node):
        """
        Create a mix shader node to multiply specular map with
        NiMaterialProperty/BSShaderProperty specular color.
        """

        self.b_specular_pass = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
        self.b_specular_pass.inputs['Fac'].default_value = 1
        self.b_specular_pass.blend_type = "MULTIPLY"

        self.b_shader_tree.links.new(b_texture_node.outputs['Color'], self.b_specular_pass.inputs[1])
        self.b_shader_tree.links.new(self.b_specular_pass.outputs['Color'], self.b_principled_bsdf.inputs['Specular Color'])

    def create_gloss_pass(self, b_texture_node):
        """Create a float curve shader node to invert gloss maps into roughness."""

        # Create Float Curve node to invert the roughness values
        b_curve_node = self.b_shader_tree.nodes.new('ShaderNodeFloatCurve')
        b_curve_node.location = (-200, -200)

        curve = b_curve_node.mapping.curves[0]
        curve.points[0].location = (0.0, 1.0)  # Maps 0 -> 1 (low alpha → high roughness)
        curve.points[1].location = (1.0, 0.0)  # Maps 1 -> 0 (high alpha → low roughness)

        self.b_shader_tree.links.new(b_curve_node.inputs['Value'], b_texture_node.outputs['Alpha'])
        self.b_shader_tree.links.new(self.b_principled_bsdf.inputs['Roughness'], b_curve_node.outputs['Value'])

    def create_emissive_pass(self, b_texture_node):
        """
        Create a mix shader node to multiply glow map with
        NiMaterialProperty/BSShaderProperty emissive color.
        """

        self.b_emissive_pass = self.b_shader_tree.nodes.new('ShaderNodeMixRGB')
        self.b_emissive_pass.inputs['Fac'].default_value = 1
        self.b_emissive_pass.blend_type = "MULTIPLY"

        self.b_shader_tree.links.new(b_texture_node.outputs['Color'], self.b_emissive_pass.inputs[1])
        self.b_shader_tree.links.new(self.b_emissive_pass.outputs['Color'], self.b_principled_bsdf.inputs['Emission Color'])

        self.b_emissive_pass.inputs['Color2'].default_value = self.emissive_color

    def create_normal_pass(self, b_texture_node):
        """
        Create a custom Y-inversion shader node for normal maps
        (because NIF normal maps are +X -Y +Z).
        """

        b_nodes = self.b_shader_tree.nodes
        b_links = self.b_shader_tree.links
        group_name = "Invert Y"

        if group_name in bpy.data.node_groups:
            b_node_group = bpy.data.node_groups[group_name]
        else:
            # The InvertY node group does not yet exist, create it
            b_node_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
            b_group_nodes = b_node_group.nodes

            # Add the input and output nodes
            b_input_node = b_group_nodes.new('NodeGroupInput')
            b_input_node.location = (-300, 0)
            b_group_output = b_group_nodes.new('NodeGroupOutput')
            b_group_output.location = (300, 0)

            # Define the inputs and outputs for the node group using the new API
            b_interface = b_node_group.interface
            b_input_socket = b_interface.new_socket(
                name="Input",
                socket_type='NodeSocketColor',
                in_out='INPUT',
                description="Input color for the group"
            )
            b_output_socket = b_interface.new_socket(
                name="Output",
                socket_type='NodeSocketColor',
                in_out='OUTPUT',
                description="Output color from the group"
            )

            # Set up the node group internals
            b_separate_node = b_group_nodes.new('ShaderNodeSeparateColor')
            b_separate_node.location = (-150, 100)

            b_invert_node = b_group_nodes.new('ShaderNodeInvert')
            b_invert_node.location = (0, 100)

            b_combine_node = b_group_nodes.new('ShaderNodeCombineColor')
            b_combine_node.location = (150, 100)

            # Link the nodes within the group
            b_group_links = b_node_group.links
            b_group_links.new(b_separate_node.outputs['Red'], b_combine_node.inputs['Red'])  # Red
            b_group_links.new(b_separate_node.outputs['Green'], b_invert_node.inputs['Color'])  # Green (invert)
            b_group_links.new(b_invert_node.outputs['Color'], b_combine_node.inputs['Green'])  # Green (inverted)
            b_group_links.new(b_separate_node.outputs['Blue'], b_combine_node.inputs['Blue'])  # Blue

            # Link the input and output nodes to the group sockets
            b_group_links.new(b_input_node.outputs[b_input_socket.name], b_separate_node.inputs['Color'])
            b_group_links.new(b_combine_node.outputs['Color'], b_group_output.inputs[b_output_socket.name])

        # Add the group node to the main node tree and link it
        b_group_node = b_nodes.new('ShaderNodeGroup')
        b_group_node.node_tree = b_node_group
        b_group_node.location = (-300, 300)

        b_links.new(b_group_node.inputs['Input'], b_texture_node.outputs['Color'])

        if self.b_mat.nif_shader.model_space_normals:
            b_links.new(self.b_principled_bsdf.inputs[5], b_group_node.outputs['Output'])
        else:
            # Create tangent normal map converter and link to it
            b_tangent_converter = b_nodes.new('ShaderNodeNormalMap')
            b_tangent_converter.location = (0, 300)
            b_links.new(b_tangent_converter.inputs['Color'], b_group_node.outputs['Output'])
            b_links.new(self.b_principled_bsdf.inputs['Normal'], b_tangent_converter.outputs['Normal'])

    def create_parallax_pass(self, b_texture_node):
        """Create a vector displacement shader node for parallax maps."""

        self.b_parallax_pass = self.b_shader_tree.nodes.new('ShaderNodeVectorDisplacement')

        self.b_shader_tree.links.new(b_texture_node.outputs['Color'], self.b_parallax_pass.inputs['Vector'])
        self.b_shader_tree.links.new(self.b_parallax_pass.outputs['Displacement'], self.b_mat_output.inputs['Displacement'])

    def create_environment_pass(self, b_texture_node):
        """Create a glossy BSDF shader node for environment maps."""

        self.b_glossy_bsdf = self.b_shader_tree.nodes.new('ShaderNodeBsdfGlossy')
        self.b_environment_pass = self.b_shader_tree.nodes.new('ShaderNodeAddShader')

        self.b_shader_tree.links.new(b_texture_node.outputs['Color'], self.b_glossy_bsdf.inputs['Color'])

        self.b_shader_tree.links.new(self.b_principled_bsdf.outputs['BSDF'], self.b_environment_pass.inputs[0])
        self.b_shader_tree.links.new(self.b_glossy_bsdf.outputs['BSDF'], self.b_environment_pass.inputs[1])

        self.b_shader_tree.links.new(self.b_environment_pass.outputs[0], self.b_mat_output.inputs[0])

    def create_environment_mask_pass(self, b_texture_node):
        """Create a custom value mask shader node for environment masks."""

        b_nodes = self.b_shader_tree.nodes
        b_links = self.b_shader_tree.links
        group_name = "Value Mask"

        if group_name in bpy.data.node_groups:
            b_node_group = bpy.data.node_groups[group_name]
        else:
            # The Value Mask node group does not yet exist, create it
            b_node_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
            b_group_nodes = b_node_group.nodes

            # Add the input and output nodes
            b_input_node = b_group_nodes.new('NodeGroupInput')
            b_input_node.location = (-300, 0)
            b_group_output = b_group_nodes.new('NodeGroupOutput')
            b_group_output.location = (300, 0)

            # Define the inputs and outputs for the node group using the new API
            b_interface = b_node_group.interface
            b_input_socket = b_interface.new_socket(
                name="Input",
                socket_type='NodeSocketColor',
                in_out='INPUT',
                description="Input color for the group"
            )
            b_output_socket = b_interface.new_socket(
                name="Output",
                socket_type='NodeSocketFloat',
                in_out='OUTPUT',
                description="Output color from the group"
            )

            # Set up the node group internals
            b_invert_color = b_group_nodes.new('ShaderNodeInvert')
            b_invert_color.location = (0, 100)

            b_rgb_to_bw = b_group_nodes.new('ShaderNodeRGBToBW')
            b_rgb_to_bw.location = (150, 100)

            # Link the nodes within the group
            b_group_links = b_node_group.links
            b_group_links.new(b_invert_color.outputs['Color'], b_rgb_to_bw.inputs['Color'])

            # Link the input and output nodes to the group sockets
            b_group_links.new(b_input_node.outputs[b_input_socket.name], b_invert_color.inputs['Color'])
            b_group_links.new(b_rgb_to_bw.outputs['Val'], b_group_output.inputs[b_output_socket.name])

        # Add the group node to the main node tree and link it
        b_group_node = b_nodes.new('ShaderNodeGroup')
        b_group_node.node_tree = b_node_group
        b_group_node.location = (-300, 300)

        b_links.new(b_group_node.inputs['Input'], b_texture_node.outputs['Color'])
        b_links.new(self.b_glossy_bsdf.inputs['Roughness'], b_group_node.outputs['Output'])

    @staticmethod
    def image_has_alpha_channel(b_img):
        """Whether the image format carries an alpha channel.

        This is the check the games make: a texture whose format has no alpha simply
        has no gloss map, regardless of what the pixels happen to contain. Blender
        decompresses DDS files into RGBA and so always reports a depth of 32, which
        says nothing about the stored format, so the DDS header is read instead.
        """

        if not b_img:
            return False

        header = None
        if b_img.packed_file:
            header = b_img.packed_file.data[:128]
        else:
            try:
                with open(bpy.path.abspath(b_img.filepath), "rb") as stream:
                    header = stream.read(128)
            except OSError:
                header = None

        if not header or len(header) < 108 or header[:4] != b"DDS ":
            # not a DDS, so fall back to what blender reports
            return b_img.depth in (32, 64, 128)

        pixel_flags, four_cc = struct.unpack_from("<I4s", header, 80)
        alpha_bit_mask = struct.unpack_from("<I", header, 104)[0]

        DDPF_ALPHAPIXELS, DDPF_FOURCC = 0x1, 0x4
        if pixel_flags & DDPF_FOURCC:
            # DXT1 only stores a single bit of alpha and carries no gloss map
            return four_cc in (b"DXT2", b"DXT3", b"DXT4", b"DXT5", b"DX10")
        return bool(pixel_flags & DDPF_ALPHAPIXELS) and alpha_bit_mask != 0

    @staticmethod
    def image_has_alpha(b_img):
        """Whether any pixel of the image is not fully opaque."""

        # Load image pixels and check alpha values
        b_img.scale(b_img.size[0], b_img.size[1])  # Ensure image data is available
        pixels = list(b_img.pixels)  # Convert to a list (R, G, B, A sequence)

        return any(pixels[i + 3] < 1.0 for i in range(0, len(pixels), 4))
