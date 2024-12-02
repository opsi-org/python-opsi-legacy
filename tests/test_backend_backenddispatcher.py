# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing BackendDispatcher.
"""

import os

import pytest

from OPSI.Backend.BackendManager import BackendDispatcher
from OPSI.Exceptions import BackendConfigurationError

from .Backends.File import getFileBackend
from .conftest import _backendBase


@pytest.mark.parametrize(
	"kwargs",
	[
		{},
		{"dispatchConfigfile": ""},
		{"dispatchConfigfile": "nope"},
		{"dispatchConfig": ""},
		{"dispatchConfig": [(".*", ("file",))]},
	],
)
def testBackendCreationFailsIfConfigMissing(kwargs):
	with pytest.raises(BackendConfigurationError):
		BackendDispatcher(**kwargs)


@pytest.mark.parametrize(
	"create_folder", [True, False], ids=["existing folder", "nonexisting folder"]
)
def testLoadingDispatchConfigFailsIfBackendConfigWithoutConfigs(create_folder, tempDir):
	backendDir = os.path.join(tempDir, "backends")

	if create_folder:
		os.mkdir(backendDir)
		print("Created folder: {0}".format(backendDir))

	with pytest.raises(BackendConfigurationError):
		BackendDispatcher(
			dispatchConfig=[[".*", ["file"]]], backendConfigDir=backendDir
		)


def testDispatchingMethodAndReceivingResults(dispatcher):
	assert [] == dispatcher.host_getObjects()


def testLoadingDispatchConfig(dispatcher):
	assert "file" in dispatcher.dispatcher_getBackendNames()
	assert [(".*", ("file",))] == dispatcher.dispatcher_getConfig()


@pytest.fixture
def dispatcherBackend(tempDir):
	"A file backend for dispatching"
	with getFileBackend(tempDir) as backend:
		with _backendBase(backend):
			yield backend


@pytest.fixture
def dispatcher(dispatcherBackend, tempDir):
	"a BackendDispatcher running on a file backend."

	dispatchConfigPath = _patchDispatchConfigForFileBackend(tempDir)

	yield BackendDispatcher(
		dispatchConfigFile=dispatchConfigPath,
		backendConfigDir=os.path.join(tempDir, "etc", "opsi", "backends"),
	)


def _patchDispatchConfigForFileBackend(targetDirectory):
	configDir = os.path.join(targetDirectory, "etc", "opsi", "backendManager")
	dispatchConfigPath = os.path.join(configDir, "dispatch.conf")

	with open(dispatchConfigPath, "w") as dpconf:
		dpconf.write("""
.* : file
""")

	return dispatchConfigPath
