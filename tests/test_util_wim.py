# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing working with WIM files.
"""

import os.path
from contextlib import contextmanager

import pytest

from OPSI.Util.WIM import getImageInformation, parseWIM

from .helpers import workInTemporaryDirectory, mock


@contextmanager
def fakeWIMEnvironment(tempDir=None):
	from .conftest import TEST_DATA_PATH

	with workInTemporaryDirectory(tempDir) as temporaryDir:
		fakeWimPath = os.path.join(temporaryDir, "fake.wim")
		with open(fakeWimPath, "w"):
			pass

		exampleData = os.path.join(TEST_DATA_PATH, "wimlib.example")

		def fakeReturningOutput(_unused):
			with open(exampleData, "rt", encoding="utf-8") as f:
				content = f.read()
				return content.split("\n")

		with mock.patch("OPSI.Util.WIM.which", lambda x: "/usr/bin/echo"):
			with mock.patch("OPSI.Util.WIM.execute", fakeReturningOutput):
				yield fakeWimPath


@pytest.fixture
def fakeWimPath(dist_data_path):
	with fakeWIMEnvironment(dist_data_path) as fakeWimPath:
		yield fakeWimPath


def testParsingNonExistingWimFileFails():
	with pytest.raises(OSError):
		parseWIM("not_here.wim")


def testParsingWIMReturnNoInformationFails(fakeWimPath):
	with mock.patch("OPSI.Util.WIM.execute", lambda x: [""]):
		with pytest.raises(ValueError):
			parseWIM(fakeWimPath)


def testParsingWIM(fakeWimPath):
	imageData = {
		"Windows 7 STARTERN": (set(["de-DE"]), "de-DE"),
		"Windows 7 HOMEBASICN": (set(["de-DE"]), "de-DE"),
		"Windows 7 HOMEPREMIUMN": (set(["de-DE"]), "de-DE"),
		"Windows 7 PROFESSIONALN": (set(["de-DE"]), "de-DE"),
		"Windows 7 ULTIMATEN": (set(["de-DE"]), "de-DE"),
	}

	for image in parseWIM(fakeWimPath):
		assert image.name in imageData

		assert image.languages == imageData[image.name][0]
		assert image.default_language == imageData[image.name][1]

		del imageData[image.name]

	assert not imageData, "Missed reading info for {0}".format(imageData.keys())


def testReadingImageInformationFromWim(fakeWimPath):
	infos = getImageInformation(fakeWimPath)

	for index in range(5):
		print("Check #{}...".format(index))
		info = next(infos)
		assert info

	with pytest.raises(StopIteration):  # Only five infos in example.
		next(infos)
