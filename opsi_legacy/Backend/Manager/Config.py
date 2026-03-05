# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
BackendManager configuration helper.
"""

import os
import socket
import sys
from functools import lru_cache

from opsi_legacy.Exceptions import BackendConfigurationError


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
