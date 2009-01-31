"""Automated Sid Meier's Railroads tests for the blender nif scripts."""

# ***** BEGIN LICENSE BLOCK *****
# 
# BSD License
# 
# Copyright (c) 2005-2009, NIF File Format Library and Tools
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. The name of the NIF File Format Library and Tools project may not be
#    used to endorse or promote products derived from this software
#    without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****

import logging
from itertools import izip

import Blender
from nif_test import TestSuite
from PyFFI.Formats.NIF import NifFormat

# some tests to import and export nif files

class SMRailroadsTestSuite(TestSuite):
    def __init__(self, *args, **kwargs):
        TestSuite.__init__(self, *args, **kwargs)
        self.logger = logging.getLogger("niftools.blender.test")

    def hasNoSpecProp(self, block):
        self.logger.info("Has no specular property?")
        return all((not isinstance(prop, NifFormat.NiSpecularProperty))
                   for prop in block.properties)

    def hasVColProp(self, block):
        self.logger.info("Has vertex color property?")
        return any(isinstance(prop, NifFormat.NiVertexColorProperty)
                   for prop in block.properties)

    def hasZBufProp(self, block):
        self.logger.info("Has z-buffer property?")
        return any(isinstance(prop, NifFormat.NiZBufferProperty)
                   for prop in block.properties)

    def hasIntegerExtra(self, trishape, name, value):
        self.logger.info("Has %s with value %i?" % (name, value))
        for extra in trishape.getExtraDatas():
            if (isinstance(extra, NifFormat.NiIntegerExtraData)
                and extra.name == name):
                # success if value matches
                return (extra.integerData == value)
        # extra block not found: failure
        return False

    def hasShaderTexture(self, texprop, name, shaderindex):
        self.logger.info("Has shader texture %s at index %i?" % (name, shaderindex))
        shaderTexDesc = texprop.shaderTextures[shaderindex]
        return shaderTexDesc.textureData.source.fileName.lower() == name.lower()

    def checkSMRailRoads(self, root_block):
        # sanity check
        assert(isinstance(root_block, NifFormat.NiNode))

        # find geom
        geom = root_block.find(block_type=NifFormat.NiGeometry)

        # root block property test
        assert(self.hasVColProp(root_block))

        assert(self.hasZBufProp(root_block))

        # geometry property test
        assert(self.hasNoSpecProp(geom))

        # geometry extra data test
        assert(self.hasIntegerExtra(geom, "EnvironmentIntensityIndex", 3))
        assert(self.hasIntegerExtra(geom, "EnvironmentMapIndex", 0))
        assert(self.hasIntegerExtra(geom, "LightCubeMapIndex", 4))
        assert(self.hasIntegerExtra(geom, "NormalMapIndex", 1))
        assert(self.hasIntegerExtra(geom, "ShadowTextureIndex", 5))
        assert(self.hasIntegerExtra(geom, "SpecularIntensityIndex", 2))

        # find texturing property
        texprop = geom.find(block_type=NifFormat.NiTexturingProperty)

        self.logger.info("Checking base texture.")

        # geometry diffuse texture test
        self.logger.info("Checking base texture.")
        assert(texprop.hasBaseTexture)
        assert(texprop.baseTexture.source.fileName[-9:].lower() == "_diff.dds")
        texbasename = texprop.baseTexture.source.fileName[:-9]

        # geometry shader textures
        assert(self.hasShaderTexture(texprop, "RRT_Engine_Env_map.dds", 0))
        assert(self.hasShaderTexture(texprop, texbasename + "_NRML.dds", 1))
        assert(self.hasShaderTexture(texprop, texbasename + "_SPEC.dds", 2))
        assert(self.hasShaderTexture(texprop, texbasename + "_EMSK.dds", 3))
        assert(self.hasShaderTexture(texprop, "RRT_Cube_Light_map_128.dds", 4))
        # note: 5 is apparently never used, although it has an extra index

    def run(self):
        nif_import = self.test(
            filename = 'test/nif/smrailroads1.nif')
        root_block = nif_import.root_blocks[0]
        # this is a generic regression test of the test itself
        # the original nif MUST pass it (if not there is a bug in the
        # testing code)
        self.logger.info(
            "Checking original nif (for regression, MUST succeed).")
        self.checkSMRailRoads(root_block)

        # check that specularity was imported (these nifs do not have specular
        # properties)
        self.logger.info("Checking specular color import.")
        testgeom = root_block.find(block_type=NifFormat.NiGeometry,
                                   block_name="Test")
        nifspec = testgeom.find(block_type=NifFormat.NiMaterialProperty).specularColor
        blendermat = Blender.Object.Get("Test").data.materials[0]
        assert(abs(blendermat.getSpec() - 1.0) < 1e-5)
        blenderspec = blendermat.getSpecCol()
        assert(abs(nifspec.r - blenderspec[0]) < 1e-5)
        assert(abs(nifspec.g - blenderspec[1]) < 1e-5)
        assert(abs(nifspec.b - blenderspec[2]) < 1e-5)

        nif_export = self.test(
            filename = 'test/nif/_smrailroads1.nif',
            config = dict(EXPORT_VERSION = "Sid Meier's Railroads"),
            selection = ['Test'])
        root_block = nif_export.root_blocks[0]

        # check exported specularity
        self.logger.info("Checking specular color export.")
        testgeom_export = root_block.find(block_type=NifFormat.NiGeometry,
                                   block_name="Test")
        nifspec_export = testgeom.find(block_type=NifFormat.NiMaterialProperty).specularColor
        assert(abs(nifspec.r - nifspec_export.r) < 1e-5)
        assert(abs(nifspec.g - nifspec_export.g) < 1e-5)
        assert(abs(nifspec.b - nifspec_export.b) < 1e-5)

        # check that the re-exported file still passes the check
        self.logger.info("Checking exported nif...")
        self.checkSMRailRoads(root_block)

suite = SMRailroadsTestSuite("smrailroads")
suite.run()

