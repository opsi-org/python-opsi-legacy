# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Handling an .opsirc file.

An .opsirc file contains information about how to connect to an
opsi API.
By default the file is expected to be at `~/.opsi.org/opsirc`.

An example::

	address = https://opsimain.domain.local:4447/rpc
	username = myname
	password = topsecret


None of these settings are mandatory.

Instead of writing the password directly to the file it is possible
to reference a file with the secret as follows::

	password file = ~/.opsi.org/opsirc.secret


The files should be encoded as utf-8.
"""

import codecs
import os

from opsicommon.logging import get_logger, secret_filter

from OPSI.Types import forceUnicode, forceUrl

__all__ = ("getOpsircPath", "readOpsirc")

logger = get_logger("opsi.general")


def readOpsirc(filename=None):
	"""
	Read the configuration file and parse it for usable information.

	:param filename: The path of the file to read. Defaults to using \
the result from `getOpsircPath`.
	:type filename: str
	:returns: Settings read from the file. Possible keys are `username`,\
`password` and `address`.
	:rtype: {str: str}
	"""
	if filename is None:
		filename = getOpsircPath()

	if not os.path.exists(filename):
		logger.debug(".opsirc file %s does not exist.", filename)
		return {}

	return _parseConfig(filename)


def getOpsircPath():
	"""
	Return the path where an opsirc file is expected to be.

	:return: The path of an opsirc file.
	:rtype: str
	"""
	path = os.path.expanduser("~/.opsi.org/opsirc")
	return path


def _parseConfig(filename):
	config = {}
	with codecs.open(filename, mode="r", encoding="utf-8") as opsircfile:
		for line in opsircfile:
			line = line.strip()
			if line.startswith(("#", ";")) or not line:
				continue

			try:
				key, value = line.split("=", 1)
			except ValueError:
				logger.trace("Unable to split line %s", line)
				continue

			key = key.strip()
			value = value.strip()

			if not value:
				logger.warning(
					"There is no value for %s in opsirc file %s, skipping.",
					key,
					filename,
				)
				continue

			if key == "address":
				config[key] = forceUrl(value)
			elif key == "username":
				config[key] = forceUnicode(value)
			elif key == "password":
				value = forceUnicode(value)
				secret_filter.add_secrets(value)
				config[key] = value
			elif key == "password file":
				passwordFilePath = os.path.expanduser(value)
				value = _readPasswordFile(passwordFilePath)
				secret_filter.add_secrets(value)
				config["password"] = value
			else:
				logger.debug("Ignoring unknown key %s", key)

	logger.debug(
		"Found the following usable keys in %s: %s",
		filename,
		", ".join(list(config.keys())),
	)
	return config


def _readPasswordFile(filename):
	with codecs.open(filename, mode="r", encoding="utf-8") as pwfile:
		password = pwfile.read()

	return password.strip()
