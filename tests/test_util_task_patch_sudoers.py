# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the patching of the sudoers file.
"""

import os
import pytest

from .helpers import mock, createTemporaryTestfile

from OPSI.System import which
from OPSI.Util.Task.Sudoers import (
	_NO_TTY_FOR_SERVICE_REQUIRED,
	_NO_TTY_REQUIRED_DEFAULT,
	FILE_ADMIN_GROUP,
	patchSudoersFileForOpsi,
	patchSudoersFileToAllowRestartingDHCPD,
)


@pytest.fixture
def temporarySudoersFile(test_data_path):
	with createTemporaryTestfile(
		os.path.join(
			test_data_path, "util", "task", "sudoers", "sudoers_without_entries"
		)
	) as fileName:
		yield fileName


def testDoNotAlterFileIfEntryAlreadyExisting(temporarySudoersFile):
	fileName = temporarySudoersFile
	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as first:
		contentAfterFirstPatch = first.readlines()

	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as second:
		contentAfterSecondPatch = second.readlines()

	assert contentAfterFirstPatch == contentAfterSecondPatch


def testAlterFileIfPartOfPreviousPatchWasMissing(temporarySudoersFile):
	fileName = temporarySudoersFile
	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as before:
		lines = before.readlines()

	lines = [line for line in lines if not line.startswith("opsiconfd")]
	with open(fileName, "w") as before:
		before.writelines(lines)

	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as after:
		assert any(line.startswith("opsiconfd") for line in after)


def testFileEndsWithNewline(temporarySudoersFile):
	patchSudoersFileForOpsi(sudoersFile=temporarySudoersFile)

	with open(temporarySudoersFile) as changedFile:
		for line in changedFile:
			lastLine = line

	assert "\n" == lastLine


def testBackupIsCreated(test_data_path, tempDir):
	def showFolderInfo():
		print("Files in {0}: {1}".format(tempDir, filesInTemporaryFolder))

	with createTemporaryTestfile(
		os.path.join(
			test_data_path, "util", "task", "sudoers", "sudoers_without_entries"
		),
		tempDir=tempDir,
	) as fileName:
		filesInTemporaryFolder = os.listdir(tempDir)

		showFolderInfo()
		assert 1 == len(filesInTemporaryFolder)

		patchSudoersFileForOpsi(sudoersFile=fileName)

		filesInTemporaryFolder = os.listdir(tempDir)
		showFolderInfo()
		assert 2 == len(filesInTemporaryFolder)


def testOpsiconfdDoesNotRequireTTY(temporarySudoersFile):
	fileName = temporarySudoersFile

	with open(fileName) as pre:
		for line in pre:
			if _NO_TTY_REQUIRED_DEFAULT in line:
				pytest.skip("Command already existing. Can't check.")

	with mock.patch(
		"OPSI.Util.Task.Sudoers.distributionRequiresNoTtyPatch", lambda: True
	):
		patchSudoersFileForOpsi(fileName)

	with open(fileName) as post:
		assert any(
			_NO_TTY_REQUIRED_DEFAULT in line for line in post
		), "Expected {0} in patched file.".format(_NO_TTY_REQUIRED_DEFAULT)


def testExecutingServiceDoesNotRequireTTY(temporarySudoersFile):
	fileName = temporarySudoersFile
	with open(fileName) as pre:
		for line in pre:
			if _NO_TTY_FOR_SERVICE_REQUIRED in line:
				pytest.skip("Command already existing. Can't check.")

	patchSudoersFileForOpsi(fileName)

	with open(fileName) as post:
		assert any(
			_NO_TTY_FOR_SERVICE_REQUIRED in line for line in post
		), "Expected {0} in patched file.".format(_NO_TTY_FOR_SERVICE_REQUIRED)


def testServiceLineHasRightPathToService():
	try:
		path = which("service")
		assert path in _NO_TTY_FOR_SERVICE_REQUIRED
	except Exception:
		pytest.skip("Cant't find 'service' in path.")


@pytest.mark.parametrize(
	"command",
	[
		"service dhcpd restart",
	],
)
def testPatchingToAllowRestartingDHCPD(temporarySudoersFile, command):
	fileName = temporarySudoersFile
	with open(fileName) as pre:
		for line in pre:
			if command in line:
				pytest.skip("Command {0!r} already existing.".format(command))

	patchSudoersFileToAllowRestartingDHCPD(command, fileName)

	with open(fileName) as post:
		assert any(command in line for line in post)


def testDoNotAddDuplicates(temporarySudoersFile):
	adminGroup = "%{group}".format(group=FILE_ADMIN_GROUP)

	fileName = temporarySudoersFile
	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as before:
		lines = before.readlines()

	lines = [line for line in lines if not line.startswith("opsiconfd")]
	assert 1 == len([line for line in lines if line.startswith(adminGroup)])

	with open(fileName, "w") as before:
		before.writelines(lines)

	patchSudoersFileForOpsi(sudoersFile=fileName)
	with open(fileName) as after:
		afterLines = after.readlines()

	assert 1 == len([line for line in afterLines if line.startswith(adminGroup)])
