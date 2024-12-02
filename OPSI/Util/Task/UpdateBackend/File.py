# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Functionality to update a file-based backend.

This module handles the database migrations for opsi.
Usually the function :py:func:updateFileBackend: is called from opsi-setup
"""

from __future__ import absolute_import

import json
import os.path
import time
from contextlib import contextmanager

from opsicommon.logging import get_logger

from OPSI.Util.Task.ConfigureBackend import getBackendConfiguration

from . import BackendUpdateError

__all__ = ("FileBackendUpdateError", "updateFileBackend")

logger = get_logger("opsi.general")


class FileBackendUpdateError(BackendUpdateError):
	"""
	Something went wrong during the update of the file-based backend.
	"""


def updateFileBackend(
	backendConfigFile="/etc/opsi/backends/file.conf",
	additionalBackendConfiguration=None,
):
	"""
	Applies migrations to the file-based backend.

	:param backendConfigFile: Path to the file where the backend \
configuration is read from.
	:type backendConfigFile: str
	:param additionalBackendConfiguration: Additional / different \
settings for the backend that will extend / override the configuration \
read from `backendConfigFile`.
	:type additionalBackendConfiguration: dict
	"""

	additionalBackendConfiguration = additionalBackendConfiguration or {}
	config = getBackendConfiguration(backendConfigFile)
	config.update(additionalBackendConfiguration)
	logger.info("Current file backend config: %s", config)

	baseDirectory = config["baseDir"]
	schemaVersion = readBackendVersion(baseDirectory)

	if schemaVersion is None:
		logger.notice("Missing information about file backend version. Creating...")
		with updateBackendVersion(baseDirectory, 0):
			logger.info("Creating...")
		logger.notice("Created information about file backend version.")

		schemaVersion = readBackendVersion(baseDirectory)
		assert schemaVersion == 0

	# Placeholder to see the usage for the first update :)
	# if schemaVersion < 1:
	#     print("Update goes here")


def readBackendVersion(baseDirectory):
	"""
	Read the backend version from `baseDirectory`.

	:param baseDirectory: The base directory of the backend.
	:type baseDirectory: str
	:raises FileBackendUpdateError: In case a migration was \
started but never ended.
	:returns: The version of the schema. `None` if no info is found.
	:rtype: int or None
	"""
	schemaConfig = _readVersionFile(baseDirectory)
	if not schemaConfig:
		# We got an empty version -> no version read.
		return None

	for version, info in schemaConfig.items():
		if "start" not in info:
			raise FileBackendUpdateError(
				f"Update {version} gone wrong: start time missing."
			)

		if "end" not in info:
			raise FileBackendUpdateError(
				f"Update {version} gone wrong: end time missing."
			)

	maximumVersion = max(schemaConfig)

	return maximumVersion


@contextmanager
def updateBackendVersion(baseDirectory, version):
	"""
	Update the backend version to the given `version`

	This is to be used as a context manager and will mark the start
	time of the update aswell as the end time.
	If during the operation something happens there will be no
	information about the end time written to the database.
	:param baseDirectory: The base directory of the backend.
	:type baseDirectory: str
	:param version: The version to update to.
	:type version: int
	"""
	versionInfo = _readVersionFile(baseDirectory)

	if version in versionInfo:
		raise FileBackendUpdateError(f"Update for {version} already applied!.")

	versionInfo[version] = {"start": time.time()}
	_writeVersionFile(baseDirectory, versionInfo)
	yield
	versionInfo[version]["end"] = time.time()
	_writeVersionFile(baseDirectory, versionInfo)


def _readVersionFile(baseDirectory):
	"""
		Read the version information from the file in `baseDirectory`.

		:param baseDirectory: The base directory of the backend.
		:type baseDirectory: str
		:return: The complete backend information. The key is the version,
	the value is a dict with two keys: `start` holds information about the
	time the update was started and `end` about the time the update finished.
		:rtype: {int: {str: float}}
	"""
	schemaConfigFile = getVersionFilePath(baseDirectory)

	try:
		with open(schemaConfigFile, encoding="utf-8") as source:
			versionInfo = json.load(source)
	except IOError:
		return {}

	newVersionInfo = {}
	for key, value in versionInfo.items():
		newVersionInfo[int(key)] = value

	return newVersionInfo


def getVersionFilePath(baseDirectory):
	"""
	Returns the path to the file containing version information.

	:param baseDirectory: The base directory of the backend.
	:type baseDirectory: str
	:rtype: str
	"""
	return os.path.join(os.path.dirname(baseDirectory), "config", "schema.json")


def _writeVersionFile(baseDirectory, versionInfo):
	"""
	Write the version information to the file in `baseDirectory`.

	:param baseDirectory: The base directory of the backend.
	:type baseDirectory: str
	:param versionInfo: Versioning information.
	:type versionInfo: {int: {str: float}}
	"""
	schemaConfigFile = getVersionFilePath(baseDirectory)

	with open(schemaConfigFile, "w", encoding="utf-8") as destination:
		json.dump(versionInfo, destination)
