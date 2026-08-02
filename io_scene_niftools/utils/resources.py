"""This script contains helper methods for locating game assets in loose folders and BSA archives."""

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
import struct
import zlib

import bpy
from ..utils.logging import NifLog

ADDON_PACKAGE = __package__.rpartition(".")[0]

RESOURCE_GROUPS = (
    ('MORROWIND', "Morrowind", "Morrowind resources"),
    ('OBLIVION', "Oblivion", "Oblivion resources"),
    ('FALLOUT_3_NV', "Fallout 3 / New Vegas", "Fallout 3 and Fallout New Vegas resources"),
    ('SKYRIM', "Skyrim", "Skyrim resources"),
    ('SKYRIM_SE', "Skyrim SE", "Skyrim Special Edition resources"),
    ('FALLOUT_4', "Fallout 4", "Fallout 4 resources"),
    ('OTHER', "Other Games", "Resources for any other game"),
)

# Scene game settings mapped to the resource group they use
GAME_RESOURCE_GROUPS = {
    'MORROWIND': 'MORROWIND',
    'OBLIVION': 'OBLIVION',
    'OBLIVION_KF': 'OBLIVION',
    'FALLOUT_3': 'FALLOUT_3_NV',
    'FALLOUT_NV': 'FALLOUT_3_NV',
    'SKYRIM': 'SKYRIM',
    'SKYRIM_SE': 'SKYRIM_SE',
    'FALLOUT_4': 'FALLOUT_4',
}

# Steam app ids and registry keys used to find installed games
GAME_INSTALL_HINTS = {
    'MORROWIND': (22320, "Morrowind"),
    'OBLIVION': (22330, "Oblivion"),
    'FALLOUT_3_NV': (22370, "FalloutNV"),
    'SKYRIM': (72850, "Skyrim"),
    'SKYRIM_SE': (489830, "Skyrim Special Edition"),
    'FALLOUT_4': (377160, "Fallout4"),
}

# Steam folder names of the games belonging to each group, in search order
GAME_STEAM_FOLDERS = {
    'MORROWIND': ("Morrowind",),
    'OBLIVION': ("Oblivion",),
    'FALLOUT_3_NV': ("Fallout New Vegas", "Fallout 3 goty", "Fallout 3"),
    'SKYRIM': ("Skyrim",),
    'SKYRIM_SE': ("Skyrim Special Edition",),
    'FALLOUT_4': ("Fallout 4",),
}

# Archive index cache, valid for the session:
# archive path -> dict mapping lower case backslashed file path -> (offset, size, compressed, embedded_name)
_archive_indices = {}

# Loose file listing cache, valid for the session: folder path -> dict of relative path -> full path
_folder_indices = {}


def clear_cache():
    """Forget the cached archive and folder listings, so changed resources are picked up."""
    _archive_indices.clear()
    _folder_indices.clear()


def get_addon_preferences():
    try:
        return bpy.context.preferences.addons[ADDON_PACKAGE].preferences
    except (AttributeError, KeyError):
        return None


def get_resource_group(game=None):
    """Return the resource group used by the given scene game setting."""
    if game is None:
        game = bpy.context.scene.niftools_scene.game
    return GAME_RESOURCE_GROUPS.get(game, 'OTHER')


def get_resource_paths(group=None):
    """Return the existing resource paths configured for a resource group, in search order."""
    prefs = get_addon_preferences()
    if prefs is None:
        return []
    if group is None:
        group = get_resource_group()

    paths = []
    for item in prefs.resource_paths:
        if item.group != group:
            continue
        path = bpy.path.abspath(item.filepath)
        if not path:
            continue
        path = os.path.normpath(path)
        if os.path.exists(path):
            paths.append(path)
        else:
            NifLog.warn(f"Configured resource path '{path}' does not exist")
    return paths


def _read_bstring(data, offset):
    """
    Read a length prefixed string.
    Returns the string and the offset past it.
     """

    length = data[offset]
    return data[offset + 1:offset + 1 + length].decode("windows-1252", errors="replace"), offset + 1 + length


def _read_zstring(data, offset):
    """
    Read a null terminated string.
    Returns the string and the offset past it.
    """
    
    end = data.index(b"\x00", offset)
    return data[offset:end].decode("windows-1252", errors="replace"), end + 1


def parse_bsa_index(archive_path):
    """Parse the file index of a BSA archive.

    Only the header and the folder/file records are read, so this stays fast even for
    archives of several gigabytes, and unlike a full parse it tolerates the trailing
    padding that several of the vanilla archives have.

    :return: dict mapping lower case backslashed file paths to
        (data offset, size, compressed, has embedded name) tuples
    """

    index = {}
    with open(archive_path, "rb") as stream:
        magic = stream.read(4)

        if magic == b"\x00\x01\x00\x00":
            # morrowind: file records, name offsets, names, then hashes, then the data
            hash_offset, file_count = struct.unpack("<II", stream.read(8))
            records = struct.unpack(f"<{file_count * 2}I", stream.read(8 * file_count))
            stream.read(4 * file_count)  # name offsets, the names follow in the same order
            names_size = hash_offset - 12 * file_count
            name_block = stream.read(names_size)
            data_start = 12 + hash_offset + 8 * file_count
            offset = 0
            for i in range(file_count):
                name, offset = _read_zstring(name_block, offset)
                size, data_offset = records[i * 2], records[i * 2 + 1]
                index[name.lower().replace("/", "\\")] = (data_start + data_offset, size, False, False)
            return index

        if magic != b"BSA\x00":
            raise ValueError(f"not a BSA archive (unexpected magic {magic!r})")

        (version, folders_offset, archive_flags, folder_count, file_count,
         total_folder_name_length, total_file_name_length, _file_flags) = struct.unpack("<8I", stream.read(32))

        if version not in (103, 104, 105):
            raise ValueError(f"unsupported BSA version {version}")

        has_folder_names = bool(archive_flags & 0x1)
        default_compressed = bool(archive_flags & 0x4)
        # embedded file names were only introduced with version 104
        embedded_names = version >= 104 and bool(archive_flags & 0x100)
        # skyrim se uses wider folder records
        folder_record_size = 24 if version == 105 else 16

        stream.seek(folders_offset)
        folder_records = stream.read(folder_record_size * folder_count)

        folder_counts = []
        for i in range(folder_count):
            record = folder_records[i * folder_record_size:(i + 1) * folder_record_size]
            folder_counts.append(struct.unpack_from("<I", record, 8)[0])

        # folder names and file records are interleaved, one block per folder
        block_size = total_folder_name_length + folder_count if has_folder_names else 0
        block_size += 16 * sum(folder_counts)
        block = stream.read(block_size)

        file_records = []
        offset = 0
        for i in range(folder_count):
            if has_folder_names:
                folder_name, offset = _read_bstring(block, offset)
                folder_name = folder_name.rstrip("\x00")
            else:
                folder_name = ""
            for _ in range(folder_counts[i]):
                _name_hash, size, data_offset = struct.unpack_from("<QII", block, offset)
                offset += 16
                file_records.append((folder_name, size, data_offset))

        # the file names follow as one block of null terminated strings, in record order
        name_block = stream.read(total_file_name_length)
        offset = 0
        for folder_name, size, data_offset in file_records:
            if offset < len(name_block):
                file_name, offset = _read_zstring(name_block, offset)
            else:
                file_name = ""
            # bit 30 of the size flips the archive's compression setting for this file
            compressed = bool(size & 0x40000000) != default_compressed
            size &= 0x3FFFFFFF
            path = f"{folder_name}\\{file_name}" if folder_name else file_name
            index[path.lower().replace("/", "\\")] = (data_offset, size, compressed, embedded_names)

    return index


def get_archive_index(archive_path):
    """Return the cached file index of an archive, parsing it on first use."""
    if archive_path not in _archive_indices:
        try:
            _archive_indices[archive_path] = parse_bsa_index(archive_path)
            NifLog.debug(f"Indexed {len(_archive_indices[archive_path])} files in {archive_path}")
        except (OSError, ValueError, struct.error, IndexError) as error:
            NifLog.warn(f"Could not read archive '{archive_path}': {error}")
            _archive_indices[archive_path] = {}
    return _archive_indices[archive_path]


def get_folder_index(folder_path):
    """Return the cached listing of a resource folder, walking it on first use.

    Paths are relative to the folder itself, so a folder can be either a game data
    folder or a folder holding the asset trees directly.
    """
    if folder_path not in _folder_indices:
        index = {}
        try:
            for root, _dirs, files in os.walk(folder_path):
                relative_root = os.path.relpath(root, folder_path)
                for file_name in files:
                    relative = os.path.join(relative_root, file_name) if relative_root != "." else file_name
                    index[relative.lower().replace("/", "\\")] = os.path.join(root, file_name)
        except OSError as error:
            NifLog.warn(f"Could not read resource folder '{folder_path}': {error}")
        _folder_indices[folder_path] = index
        NifLog.debug(f"Indexed {len(index)} files in {folder_path}")
    return _folder_indices[folder_path]


def read_archive_file(archive_path, entry):
    """Return the bytes of a file in an archive, described by an index entry."""
    offset, size, compressed, has_embedded_name = entry
    try:
        with open(archive_path, "rb") as stream:
            stream.seek(offset)
            blob = stream.read(size)
    except OSError as error:
        NifLog.warn(f"Could not read from archive '{archive_path}': {error}")
        return None
    if has_embedded_name and blob:
        # skip the length prefixed file name stored before the data
        blob = blob[1 + blob[0]:]
    if compressed:
        # a uint32 with the original size precedes the compressed data
        try:
            blob = zlib.decompress(blob[4:])
        except zlib.error:
            # skyrim se archives may use lz4, which python cannot decompress natively
            NifLog.warn(f"Could not decompress a file from '{archive_path}' "
                        f"(lz4 compressed archives are not supported)")
            return None
    return blob


def relative_search_paths(file_path, asset_folder="textures"):
    """Return the candidate paths of an asset relative to a game data folder."""
    relative = file_path.lower().replace("/", "\\").replace(os.sep, "\\").lstrip("\\")
    # some nifs erroneously store absolute paths, so cut them down to the part below the data folder
    prefix = asset_folder + "\\"
    index = relative.find(prefix)
    if index != -1:
        relative = relative[index:]
    candidates = [relative]
    if not relative.startswith(prefix):
        candidates.append(prefix + relative)
    return candidates


def find_asset(file_path, asset_folder="textures", group=None):
    """Look for an asset in the configured resource folders and archives.

    Loose files take precedence over archives, matching how the games load assets.

    :param file_path: the asset path as stored in the nif, e.g. 'textures\\armor\\metal.dds'
    :return: tuple of (path identifying the asset, its bytes), or None if it was not found
    """

    resource_paths = get_resource_paths(group)
    if not resource_paths:
        return None

    candidates = relative_search_paths(file_path, asset_folder)

    # loose files win over archives, so check every folder first
    for resource_path in resource_paths:
        if not os.path.isdir(resource_path):
            continue
        index = get_folder_index(resource_path)
        for candidate in candidates:
            found = index.get(candidate)
            if found:
                NifLog.debug(f"Found {candidate} in {resource_path}")
                try:
                    with open(found, "rb") as stream:
                        return found, stream.read()
                except OSError as error:
                    NifLog.warn(f"Could not read '{found}': {error}")

    for resource_path in resource_paths:
        if os.path.isdir(resource_path):
            continue
        index = get_archive_index(resource_path)
        for candidate in candidates:
            entry = index.get(candidate)
            if entry:
                NifLog.debug(f"Found {candidate} in {resource_path}")
                data = read_archive_file(resource_path, entry)
                if data is not None:
                    return os.path.join(resource_path, candidate.replace("\\", os.sep)), data
    return None


def find_texture(file_path):
    """Look for a texture in the configured resources; see find_asset."""
    return find_asset(file_path, asset_folder="textures")


def steam_library_folders():
    """Return the Steam library folders configured on this machine."""
    libraries = []
    steam_path = None
    try:
        import winreg
        for root, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(root, key) as handle:
                    steam_path = winreg.QueryValueEx(handle, "SteamPath")[0]
                    break
            except OSError:
                continue
    except ImportError:
        # not Windows, so there is no registry
        # Steam keeps its root in a couple of places
        for candidate in (os.path.expanduser("~/.steam/steam"),
                          os.path.expanduser("~/.local/share/Steam"),
                          os.path.expanduser("~/Library/Application Support/Steam")):
            if os.path.isdir(candidate):
                steam_path = candidate
                break

    if not steam_path:
        return libraries

    libraries.append(os.path.join(steam_path, "steamapps", "common"))
    # additional libraries are listed in libraryfolders.vdf as quoted paths
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf_path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                parts = line.split('"')
                if len(parts) >= 5 and parts[1] == "path":
                    libraries.append(os.path.join(parts[3].replace("\\\\", "\\"), "steamapps", "common"))
    except OSError:
        pass
    return libraries


def find_game_data_folder(group):
    """Try to locate the data folder of an installed game of the given resource group."""

    # the registry entries the games write on install are the most reliable source
    app_id, registry_name = GAME_INSTALL_HINTS.get(group, (None, None))
    if registry_name:
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for prefix in (r"SOFTWARE\WOW6432Node\Bethesda Softworks", r"SOFTWARE\Bethesda Softworks"):
                    try:
                        with winreg.OpenKey(root, f"{prefix}\\{registry_name}") as handle:
                            install_path = winreg.QueryValueEx(handle, "Installed Path")[0]
                            data_path = os.path.join(install_path, "Data")
                            if os.path.isdir(data_path):
                                return data_path
                    except OSError:
                        continue
        except ImportError:
            pass

    # otherwise look through the steam libraries
    for library in steam_library_folders():
        for folder_name in GAME_STEAM_FOLDERS.get(group, ()):
            data_path = os.path.join(library, folder_name, "Data")
            if os.path.isdir(data_path):
                return data_path
    return None


def detect_game_resources(group):
    """Return the resource paths of an installed game, its data folder and its archives."""
    data_folder = find_game_data_folder(group)
    if not data_folder:
        return []

    paths = [data_folder]
    try:
        for file_name in sorted(os.listdir(data_folder)):
            if file_name.lower().endswith((".bsa", ".ba2")):
                paths.append(os.path.join(data_folder, file_name))
    except OSError as error:
        NifLog.warn(f"Could not list '{data_folder}': {error}")
    return paths
