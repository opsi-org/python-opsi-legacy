# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Configuration utility functions.
"""

import codecs
import os

from OPSI.Config import OPSI_GLOBAL_CONF
from OPSI.Types import forceUnicode

__all__ = ("getGlobalConfig", "setGlobalConfig")


def getGlobalConfig(name, configFile=OPSI_GLOBAL_CONF):
	"""
	Reads the value of ``name`` from the global configuration.

	:param configFile: The path of the config file.
	:type configFile: str
	"""
	name = forceUnicode(name)
	if os.path.exists(configFile):
		with codecs.open(configFile, "r", "utf8") as config:
			for line in config:
				line = line.strip()
				if line.startswith(("#", ";")):
					continue

				try:
					key, value = line.split("=", 1)
					if key.strip().lower() == name.lower():
						return value.strip()
				except ValueError:
					continue

	return None


def setGlobalConfig(name, value, configFile=OPSI_GLOBAL_CONF):
	"""
	Set ``name`` to ``value`` in the global configuration.

	:param configFile: The path of the config file.
	:type configFile: str
	"""
	name = forceUnicode(name)
	value = forceUnicode(value)

	lines = []
	new_line = f"{name} = {value}"
	if os.path.exists(configFile):
		with codecs.open(configFile, "r", "utf8") as config:
			for line in config:
				lines.append(line.rstrip())
				line = line.strip()
				if line.startswith(("#", ";")):
					continue

				key, value = line.split("=", 1)
				if key.strip().lower() == name.lower():
					lines[-1] = new_line
					new_line = None
	if new_line:
		lines.append(new_line)

	with codecs.open(configFile, "w", "utf8") as config:
		config.writelines(lines)

	from OPSI.Util.Task.Rights import setRights

	setRights(configFile)
