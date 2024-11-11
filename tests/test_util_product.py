# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the OPSI.Util.Product module.
"""

import os
import re
import tempfile

import pytest

import OPSI.Util.Product as Product

from .helpers import cd, mock


@pytest.mark.parametrize(
	"text",
	[
		".svn",
		pytest.param(".svnotmatching", marks=pytest.mark.xfail),
		".git",
		pytest.param(".gitignore", marks=pytest.mark.xfail),
	],
)
def testDirectoryExclusion(text):
	assert re.match(Product.EXCLUDE_DIRS_ON_PACK_REGEX, text) is not None


def testProductPackageFileRemovingFolderWithUnicodeFilenamesInsideFails(tempDir):
	"""
	As mentioned in http://bugs.python.org/issue3616 the attempt to
	remove a filename that contains unicode can fail.

	Sometimes products are created that feature files with filenames
	that do containt just that.
	We need to make shure that removing such fails does not fail and
	that we are able to remove them.
	"""
	tempPackageFilename = tempfile.NamedTemporaryFile(suffix=".opsi")

	ppf = Product.ProductPackageFile(tempPackageFilename.name)
	ppf.setClientDataDir(tempDir)

	fakeProduct = mock.Mock()
	fakeProduct.getId.return_value = "umlauts"
	fakePackageControlFile = mock.Mock()
	fakePackageControlFile.getProduct.return_value = fakeProduct

	# Setting up evil file
	targetDir = os.path.join(tempDir, "umlauts")
	os.makedirs(targetDir)

	with cd(targetDir):
		os.system(r"touch -- $(echo -e '--\0250--')")

	with mock.patch.object(ppf, "packageControlFile", fakePackageControlFile):
		ppf.deleteProductClientDataDir()

	assert not os.path.exists(
		targetDir
	), "Product directory in depot should be deleted."


def testSettigUpProductPackageFileWithNonExistingFileFails():
	with pytest.raises(Exception):
		Product.ProductPackageFile("nonexisting.opsi")


def testCreatingProductPackageSourceRequiresExistingSourceFolder(tempDir):
	targetDir = os.path.join(tempDir, "nope")

	with pytest.raises(Exception):
		Product.ProductPackageSource(targetDir)
