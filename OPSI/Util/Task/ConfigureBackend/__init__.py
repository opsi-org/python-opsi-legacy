# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Functionality to automatically configure an OPSI backend.

.. versionadded:: 4.0.4.6
"""

import codecs
import os
import re
import socket
import sys

from opsicommon.logging import get_logger

from OPSI.System.Posix import getLocalFqdn, getNetworkConfiguration
from OPSI.Util import objectToBeautifiedText

__all__ = ("getBackendConfiguration", "updateConfigFile")

logger = get_logger("opsi.general")


def getBackendConfiguration(backendConfigFile, customGlobals=None):
	"""
	Reads the backend configuration from the given file.

	:param backendConfigFile: Path to the backend configuration file.
	:param customGlobals: If special locals are needed for the config file \
please pass them here. If this is None defaults will be used.
	:type customGlobals: dict
	"""
	if customGlobals is None:
		customGlobals = {
			"config": {},  # Will be filled after loading
			"module": "",  # Will be filled after loading
			"os": os,
			"socket": socket,
			"sys": sys,
		}

	logger.info("Loading backend config '%s'", backendConfigFile)
	with open(backendConfigFile, encoding="utf-8") as configFile:
		exec(configFile.read(), customGlobals)

	config = customGlobals["config"]
	logger.debug("Current backend config: %s", config)

	return config


def updateConfigFile(backendConfigFile, newConfig, notificationFunction=None):
	"""
	Updates a config file with the corresponding new configuration.

	:param backendConfigFile: path to the backend configuration
	:param newConfig: the new configuration.
	:param notificationFunction: A function that log messages will be passed \
on to. Defaults to logger.notice
	:type notificationFunction: func
	"""

	def correctBooleans(text):
		"""
		Creating correct JSON booleans - they are all lowercase.
		"""
		return text.replace("true", "True").replace("false", "False")

	if notificationFunction is None:
		notificationFunction = logger.notice

	notificationFunction(f"Updating backend config '{backendConfigFile}'")

	lines = []
	with codecs.open(backendConfigFile, "r", "utf-8") as backendFile:
		for line in backendFile.readlines():
			if re.search(r"^\s*config\s*\=", line):
				break
			lines.append(line)

	with codecs.open(backendConfigFile, "w", "utf-8") as backendFile:
		backendFile.writelines(lines)
		backendConfigData = correctBooleans(objectToBeautifiedText(newConfig))
		backendFile.write(f"config = {backendConfigData}\n")

	notificationFunction(f"Backend config '{backendConfigFile}' updated")


def _getSysConfig():
	"""
	Skinned down version of getSysConfig from ``opsi-setup``.

	Should be used as **fallback only**!
	"""
	logger.notice("Getting current system config")
	fqdn = getLocalFqdn()
	sysConfig = {"fqdn": fqdn, "hostname": fqdn.split(".")[0]}

	sysConfig.update(getNetworkConfiguration())

	logger.notice("System information:")
	logger.notice("   ip address   : %s", sysConfig["ipAddress"])
	logger.notice("   netmask      : %s", sysConfig["netmask"])
	logger.notice("   subnet       : %s", sysConfig["subnet"])
	logger.notice("   broadcast    : %s", sysConfig["broadcast"])
	logger.notice("   fqdn         : %s", sysConfig["fqdn"])
	logger.notice("   hostname     : %s", sysConfig["hostname"])

	return sysConfig
