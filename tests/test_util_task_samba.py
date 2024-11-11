# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing functionality of OPSI.Util.Task.Samba
"""

import os.path

import OPSI.Util.Task.Samba as Samba
import pytest

from .helpers import mock


@pytest.fixture(params=[True, False], ids=["Samba-4", "Samba-3"])
def isSamba4(request):
	with mock.patch("OPSI.Util.Task.Samba.isSamba4", lambda: request.param):
		yield request.param


@pytest.fixture
def pathToSmbConf(tempDir):
	"""
	Path to an empty file serving as possible smb.conf.
	"""
	pathToSmbConf = os.path.join(tempDir, "SMB_CONF")
	with open(pathToSmbConf, "w"):
		pass

	return pathToSmbConf


@pytest.fixture
def disableDirCreation():
	def printMessage(path, *_unused):
		print("Would create {0!r}".format(path))

	with mock.patch("OPSI.Util.Task.Samba.os.mkdir", printMessage):
		yield


@pytest.mark.parametrize("emptyoutput", [None, []])
def testCheckForSambaVersionWithoutSMBD(emptyoutput):
	with mock.patch("OPSI.Util.Task.Samba.execute", lambda cmd: emptyoutput):
		with mock.patch("OPSI.Util.Task.Samba.which", lambda cmd: None):
			assert not Samba.isSamba4()


@pytest.mark.parametrize(
	"versionString, expectedSamba4", [("version 4.0.3", True), ("version 3.1", False)]
)
def testCheckForSamba4DependsOnVersion(versionString, expectedSamba4):
	with mock.patch("OPSI.Util.Task.Samba.execute", lambda cmd: [versionString]):
		with mock.patch("OPSI.Util.Task.Samba.which", lambda cmd: cmd):
			assert Samba.isSamba4() == expectedSamba4


def testReadingEmptySambaConfig(pathToSmbConf):
	assert [] == Samba._readConfig(pathToSmbConf)


def testReadingSambaConfig(pathToSmbConf):
	config = [
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_repository]\n",
		"[opsi_logs]\n",
	]

	with open(pathToSmbConf, "w") as fakeSambaConfig:
		for line in config:
			fakeSambaConfig.write(line)

	assert config == Samba._readConfig(pathToSmbConf)


def testSambaConfigureSamba4Share(isSamba4, disableDirCreation):
	config = [
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_repository]\n",
		"[opsi_logs]\n",
	]
	result = Samba._processConfig(config)

	assert any(line.strip() for line in result)


def testAdminUsersAreRemovedExistingOpsiDepotShare(isSamba4, disableDirCreation):
	config = [
		"[opsi_depot]\n",
		"   available = yes\n",
		"   comment = opsi depot share (ro)\n",
		"   path = /var/lib/opsi/depot\n",
		"   oplocks = no\n",
		"   follow symlinks = yes\n",
		"   level2 oplocks = no\n",
		"   writeable = no\n",
		"   invalid users = root\n",
		"   admin users = pcpatch\n",  # old fix
	]

	if not isSamba4:
		pytest.skip("Requires Samba 4.")

	result = Samba._processConfig(config)

	assert not any(
		"admin users" in line for line in result
	), "admin users left in share opsi_depot"


def testCorrectOpsiDepotShareWithoutFixForSamba4(isSamba4, disableDirCreation):
	config = [
		"[opsi_depot]\n",
		"   available = yes\n",
		"   comment = opsi depot share (ro)\n",
		"   path = /var/lib/opsi/depot\n",
		"   oplocks = no\n",
		"   follow symlinks = yes\n",
		"   level2 oplocks = no\n",
		"   writeable = no\n",
		"   invalid users = root\n",
		"   # acl allow execute always = true\n",
	]

	if not isSamba4:
		pytest.skip("Requires Samba 4.")

	in_opsi_depot_section = False
	for line in Samba._processConfig(config):
		if line.lower().strip() == "[opsi_depot]":
			in_opsi_depot_section = True
		elif in_opsi_depot_section and line.lower().strip().startswith("["):
			in_opsi_depot_section = False

		if in_opsi_depot_section and line.strip() == "acl allow execute always = true":
			return

	raise RuntimeError(
		'Did not find "acl allow execute always = true" in opsi_depot share'
	)


def testCorrectOpsiDepotShareWithSamba4Fix(isSamba4, disableDirCreation):
	config = [
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"   available = yes\n",
		"   comment = opsi depot share (ro)\n",
		"   path = /var/lib/opsi/depot\n",
		"   oplocks = no\n",
		"   follow symlinks = yes\n",
		"   level2 oplocks = no\n",
		"   writeable = no\n",
		"   invalid users = root\n",
		"   acl allow execute always = true\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_repository]\n",
		"[opsi_logs]\n",
	]

	if not isSamba4:
		pytest.skip("Requires Samba 4.")

	print("".join(config))
	print("".join(Samba._processConfig(config)))

	assert config == Samba._processConfig(config)


def testProcessConfigDoesNotRemoveComment(isSamba4, disableDirCreation):
	config = [
		"; load opsi shares\n",
		"include = /etc/samba/share.conf\n",
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_repository]\n",
		"[opsi_logs]\n",
	]

	result = Samba._processConfig(config)

	assert any("; load opsi shares" in line for line in result)


def testProcessConfigAddsMissingRepositoryShare(isSamba4, disableDirCreation):
	config = [
		"; load opsi shares\n",
		"include = /etc/samba/share.conf\n",
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_logs]\n",
	]

	result = Samba._processConfig(config)

	repository = False
	pathFound = False
	for line in result:
		if "[opsi_repository]" in line:
			repository = True
		elif repository:
			if line.strip().startswith("["):
				# next section
				break
			elif line.strip().startswith("path"):
				assert "/var/lib/opsi/repository" in line
				pathFound = True
				break

	assert repository, "Missing entry 'opsi_repository'"
	assert pathFound, "Missing 'path' in 'opsi_repository'"


def testWritingEmptySambaConfig(pathToSmbConf):
	Samba._writeConfig([], pathToSmbConf)

	with open(pathToSmbConf, "r") as readConfig:
		assert [] == readConfig.readlines()


def testWritingSambaConfig(pathToSmbConf):
	config = [
		"[opt_pcbin]\n",
		"[opsi_depot]\n",
		"[opsi_depot_rw]\n",
		"[opsi_images]\n",
		"[opsi_workbench]\n",
		"[opsi_repository]\n",
		"[opsi_logs]\n",
	]

	Samba._writeConfig(config, pathToSmbConf)

	with open(pathToSmbConf, "r") as readConfig:
		assert config == readConfig.readlines()
