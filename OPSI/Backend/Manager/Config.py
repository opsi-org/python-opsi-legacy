# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
BackendManager configuration helper.
"""

import os
import socket
import sys
from functools import lru_cache

from OPSI.Exceptions import BackendConfigurationError


def loadBackendConfig(path):
	"""
	Load the backend configuration at `path`.
	:param path: Path to the configuration file to load.
	:type path: str
	:rtype: dict
	"""
	if not os.path.exists(path):
		raise BackendConfigurationError(f"Backend config file '{path}' not found")

	moduleGlobals = {
		"config": {},  # Will be filled after loading
		"module": "",  # Will be filled after loading
		"os": os,
		"socket": socket,
		"sys": sys,
	}

	exec(_readFile(path), moduleGlobals)

	return moduleGlobals


@lru_cache(maxsize=None)
def _readFile(path):
	with open(path, encoding="utf-8") as configFile:
		return configFile.read()
