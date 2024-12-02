# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the update of the MySQL backend from an older version.
"""

import json
import os.path

import pytest

from OPSI.Util.Task.UpdateBackend.File import (
	FileBackendUpdateError,
	getVersionFilePath,
	readBackendVersion,
	_readVersionFile,
	updateBackendVersion,
	updateFileBackend,
)

from .Backends.File import getFileBackend


@pytest.fixture
def fileBackend(tempDir):
	with getFileBackend(path=tempDir) as backend:
		yield backend


def testUpdatingFileBackend(fileBackend, tempDir):
	config = os.path.join(tempDir, "etc", "opsi", "backends", "file.conf")

	updateFileBackend(config)


def testReadingSchemaVersionFromMissingFile(tempDir):
	assert readBackendVersion(os.path.join(tempDir, "missingbasedir")) is None


@pytest.fixture
def baseDirectory(tempDir):
	newDir = os.path.join(tempDir, "config")
	os.makedirs(newDir)
	yield newDir


@pytest.fixture
def writtenConfig(baseDirectory):
	configFile = getVersionFilePath(baseDirectory)
	config = {
		0: {
			"start": 1495529319.022833,
			"end": 1495529341.870662,
		},
		1: {"start": 1495539432.271123, "end": 1495539478.045244},
	}
	with open(configFile, "w") as f:
		json.dump(config, f)

	yield config


def testReadingSchemaVersionLowLevel(baseDirectory, writtenConfig):
	assert writtenConfig == _readVersionFile(baseDirectory)


def testReadingSchemaVersion(baseDirectory, writtenConfig):
	version = readBackendVersion(baseDirectory)
	assert version is not None
	assert version == max(writtenConfig.keys())
	assert version > 0


@pytest.mark.parametrize(
	"config",
	[
		{0: {"start": 1495529319.022833}},  # missing end
		{0: {}},  # missing start
	],
)
def testRaisingExceptionOnUnfinishedUpdate(baseDirectory, config):
	configFile = getVersionFilePath(baseDirectory)

	with open(configFile, "w") as f:
		json.dump(config, f)

	with pytest.raises(FileBackendUpdateError):
		readBackendVersion(baseDirectory)


def testApplyingTheSameUpdateMultipleTimesFails(baseDirectory):
	with updateBackendVersion(baseDirectory, 1):
		pass

	with pytest.raises(FileBackendUpdateError):
		with updateBackendVersion(baseDirectory, 1):
			pass
