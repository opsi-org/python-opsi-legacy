# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing the task to backup opsi.
"""

import os
import shutil
import sys

from opsi_legacy.Util.Task.Backup import OpsiBackup
from opsi_legacy.Util.Task.ConfigureBackend import getBackendConfiguration, updateConfigFile

from .helpers import mock, workInTemporaryDirectory

try:
	from .Backends.MySQL import MySQLconfiguration
except ImportError:
	MySQLconfiguration = None


def testVerifySysConfigDoesNotFailBecauseWhitespaceAtEnd():
	backup = OpsiBackup()

	archive = {
		"distribution": "SUSE Linux Enterprise Server",
		"sysVersion": "(12, 0)",
	}
	system = {
		"distribution": "SUSE Linux Enterprise Server ",  # note the extra space
		"sysVersion": (12, 0),
	}

	assert {} == backup.getDifferencesInSysConfig(archive, sysInfo=system)


def testPatchingStdout():
	fake = "fake"
	backup = OpsiBackup(stdout=fake)
	assert fake == backup.stdout

	newBackup = OpsiBackup()
	assert sys.stdout == newBackup.stdout


def testGettingArchive(dist_data_path):
	fakeBackendDir = os.path.join(dist_data_path, "backends")
	fakeBackendDir = os.path.normpath(fakeBackendDir)

	with mock.patch("opsi_legacy.Util.Task.Backup.OpsiBackupArchive.BACKEND_CONF_DIR", fakeBackendDir):
		backup = OpsiBackup()
		archive = backup._getArchive("r")

		assert os.path.exists(archive.name), "No archive created."
		os.remove(archive.name)


def testCreatingArchive(dist_data_path):
	with workInTemporaryDirectory() as backendDir:
		with workInTemporaryDirectory() as tempDir:
			assert 0 == len(os.listdir(tempDir)), "Directory not empty"

			configDir = os.path.join(backendDir, "config")
			os.mkdir(configDir)

			sourceBackendDir = os.path.join(dist_data_path, "backends")
			sourceBackendDir = os.path.normpath(sourceBackendDir)
			fakeBackendDir = os.path.join(backendDir, "backends")

			shutil.copytree(sourceBackendDir, fakeBackendDir)

			for filename in os.listdir(fakeBackendDir):
				if not filename.endswith(".conf"):
					continue

				configPath = os.path.join(fakeBackendDir, filename)
				config = getBackendConfiguration(configPath)
				if "file" in filename:
					config["baseDir"] = configDir
				elif "mysql" in filename and MySQLconfiguration:
					config.update(MySQLconfiguration)
				else:
					continue  # no modifications here

				updateConfigFile(configPath, config)

			with mock.patch(
				"opsi_legacy.Util.Task.Backup.OpsiBackupArchive.CONF_DIR",
				os.path.dirname(__file__),
			):
				with mock.patch(
					"opsi_legacy.Util.Task.Backup.OpsiBackupArchive.BACKEND_CONF_DIR",
					fakeBackendDir,
				):
					backup = OpsiBackup()
					backup.create()

					dirListing = os.listdir(tempDir)
					try:
						dirListing.remove(".coverage")
					except ValueError:
						pass

					assert len(dirListing) == 1
