# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Fixtures for tests.

To use any of these fixtures use their name as a parameter when
creating a test function. No rurther imports are needed.

	def testSomething(fixtureName):
		pass


Backends with MySQL / SQLite sometimes require a modules file and may
be skipped if it does not exist.
"""

import os
import shutil
import warnings
from contextlib import contextmanager

import pytest
import urllib3
from _pytest.logging import LogCaptureHandler

from OPSI.Backend.Backend import ExtendedConfigDataBackend
from OPSI.Backend.BackendManager import BackendManager

from .Backends.File import getFileBackend
from .Backends.MySQL import getMySQLBackend
from .Backends.SQLite import getSQLiteBackend
from .helpers import createTemporaryTestfile, workInTemporaryDirectory

_LICENSE_FILE = os.path.exists(os.path.join("/etc", "opsi", "licenses", "test.opsilic"))

# Path to test data dir
TEST_DATA_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))
# Path to dist data dir (data/etc from opsi-server)
DIST_DATA_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))


@pytest.fixture
def test_data_path():
	return TEST_DATA_PATH


@pytest.fixture
def dist_data_path():
	return DIST_DATA_PATH


def emit(*args, **kwargs) -> None:
	pass


LogCaptureHandler.emit = emit


@pytest.hookimpl()
def pytest_configure(config):
	# https://pypi.org/project/pytest-asyncio
	# When the mode is auto, all discovered async tests are considered
	# asyncio-driven even if they have no @pytest.mark.asyncio marker.
	config.option.asyncio_mode = "auto"
	config.addinivalue_line(
		"markers", "obsolete: mark test that are obsolete for 4.2 development"
	)


@pytest.fixture(autouse=True)
def disable_insecure_request_warning():
	warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)


@pytest.fixture(
	params=[
		getFileBackend,
		pytest.param(getMySQLBackend, marks=pytest.mark.requires_license_file),
		pytest.param(getSQLiteBackend, marks=pytest.mark.requires_license_file),
	],
	ids=["file", "mysql", "sqlite"],
)
def configDataBackend(request):
	"""
	Returns an `OPSI.Backend.ConfigDataBackend` for testing.

	This will return multiple backends but some of these may lead to
	skips if required libraries are missing or conditions for the
	execution are not met.
	"""
	with request.param() as backend:
		with _backendBase(backend):
			yield backend


@contextmanager
def _backendBase(backend):
	"Creates the backend base before and deletes it after use."

	backend.backend_createBase()
	try:
		yield
	finally:
		backend.backend_deleteBase()


@pytest.fixture
def extendedConfigDataBackend(configDataBackend):
	"""
	Returns an `OPSI.Backend.ExtendedConfigDataBackend` for testing.

	This will return multiple backends but some of these may lead to
	skips if required libraries are missing or conditions for the
	execution are not met.
	"""
	yield ExtendedConfigDataBackend(configDataBackend)


@pytest.fixture
def cleanableDataBackend(_serverBackend):
	"""
	Returns an backend that can be cleaned.
	"""
	yield ExtendedConfigDataBackend(_serverBackend)


@pytest.fixture(
	params=[
		getFileBackend,
		pytest.param(getMySQLBackend, marks=pytest.mark.requires_license_file),
	],
	ids=["file", "mysql"],
)
def _serverBackend(request):
	"Shortcut to specify backends used on an opsi server."

	with request.param() as backend:
		with _backendBase(backend):
			yield backend


@pytest.fixture(
	params=[
		getFileBackend,
		pytest.param(getMySQLBackend, marks=pytest.mark.requires_license_file),
	],
	ids=["destination:file", "destination:mysql"],
)
def replicationDestinationBackend(request):
	# This is the same as _serverBackend, but has custom id's set.
	with request.param() as backend:
		with _backendBase(backend):
			yield backend


@pytest.fixture
def backendManager(_serverBackend, tempDir, dist_data_path):
	"""
	Returns an `OPSI.Backend.BackendManager.BackendManager` for testing.

	The returned instance is set up to have access to backend extensions.
	"""
	shutil.copytree(dist_data_path, os.path.join(tempDir, "etc", "opsi"))

	yield BackendManager(
		backend=_serverBackend,
		extensionconfigdir=os.path.join(
			tempDir, "etc", "opsi", "backendManager", "extend.d"
		),
	)


@pytest.fixture
def tempDir():
	"""
	Switch to a temporary directory.
	"""
	with workInTemporaryDirectory() as tDir:
		yield tDir


@pytest.fixture
def licenseManagementBackend(sqlBackendCreationContextManager):
	"""Returns a backend that can handle License Management."""
	with sqlBackendCreationContextManager() as backend:
		with _backendBase(backend):
			yield ExtendedConfigDataBackend(backend)


@pytest.fixture(
	params=[
		getMySQLBackend,
		pytest.param(getSQLiteBackend, marks=pytest.mark.requires_license_file),
	],
	ids=["mysql", "sqlite"],
)
def sqlBackendCreationContextManager(request):
	yield request.param


@pytest.fixture(params=[getMySQLBackend], ids=["mysql"])
def multithreadingBackend(request):
	with request.param() as backend:
		with _backendBase(backend):
			yield backend


@pytest.fixture(params=[getMySQLBackend, getSQLiteBackend], ids=["mysql", "sqlite"])
def hardwareAuditBackendWithHistory(request, hardwareAuditConfigPath):
	with request.param(auditHardwareConfigFile=hardwareAuditConfigPath) as backend:
		with _backendBase(backend):
			yield ExtendedConfigDataBackend(backend)


@pytest.fixture
def hardwareAuditConfigPath(dist_data_path):
	"""
	Copies the opsihwaudit.conf that is usually distributed for
	installation to a temporary folder and then returns the new absolute
	path of the config file.
	"""
	pathToOriginalConfig = os.path.join(dist_data_path, "hwaudit", "opsihwaudit.conf")

	with createTemporaryTestfile(pathToOriginalConfig) as fileCopy:
		yield fileCopy


@pytest.fixture(
	params=[getFileBackend, getMySQLBackend, getSQLiteBackend],
	ids=["file", "mysql", "sqlite"],
)
def auditDataBackend(request, hardwareAuditConfigPath):
	with request.param(auditHardwareConfigFile=hardwareAuditConfigPath) as backend:
		with _backendBase(backend):
			yield ExtendedConfigDataBackend(backend)


@pytest.fixture(
	params=[
		getMySQLBackend,
		pytest.param(getSQLiteBackend, marks=pytest.mark.requires_license_file),
	],
	ids=["mysql", "sqlite"],
)
def licenseManagentAndAuditBackend(request):
	with request.param() as backend:
		with _backendBase(backend):
			yield ExtendedConfigDataBackend(backend)


def pytest_runtest_setup(item):
	envmarker = item.get_closest_marker("requires_license_file")
	if envmarker is not None:
		if not _LICENSE_FILE:
			pytest.skip(f"{item.name} requires a license file!")

	envmarker = item.get_closest_marker("obsolete")
	if envmarker is not None:
		pytest.skip(f"{item.name} uses tech that will likely be obsolete in the future")
