# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
This writes the opsi configserver URL into the default.menu file
"""

import os
import re

from OPSI.Exceptions import BackendMissingDataError

__all__ = ("patchServiceUrlInDefaultConfigs",)


def patchServiceUrlInDefaultConfigs(backend):
	"""
	Patches the clientconfig.configserver.url into the default.menu/grub.cfg

	:param backend: The backend used to read the configuration
	:type backend: ConfigDataBackend
	"""
	try:
		configServer = backend.config_getObjects(
			attributes=["defaultValues"], id="clientconfig.configserver.url"
		)[0]
		configServer = configServer.defaultValues[0]
	except IndexError:
		raise BackendMissingDataError(
			"Unable to get clientconfig.configserver.url"
		) from IndexError

	if configServer:
		defaultMenu, grubMenu = getMenuFiles()
		patchMenuFile(defaultMenu, "append", configServer)
		patchMenuFile(grubMenu, "linux", configServer)


def getMenuFiles():
	"""
	Returns the paths for for the default.menu and grub.cfg files.

	:returns: A two-item-tuple with absolute paths to first the \
default.menu and second grub.cfg.
	:rtype: (str, str)
	"""
	if os.path.exists("/tftpboot/linux/pxelinux.cfg/default.menu"):
		defaultMenu = "/tftpboot/linux/pxelinux.cfg/default.menu"
		grubMenu = "/tftpboot/grub/grub.cfg"
	else:
		defaultMenu = "/var/lib/tftpboot/opsi/pxelinux.cfg/default.menu"
		grubMenu = "/var/lib/tftpboot/grub/grub.cfg"

	return defaultMenu, grubMenu


def patchMenuFile(menufile, searchString, configServer):
	"""
	Patch the address to the `configServer` into `menufile`.

	To find out where to patch we look for lines that starts with the
	given `searchString` (excluding preceding whitespace).

	:param menufile: Path to the file to patch
	:type menufile: str
	:param searchString: Patches only lines starting with this string.
	:type searchString: str
	:param configServer: The address of the OpsiConfigserver to patch \
into the file.
	:type configServer: str
	"""
	newlines = []
	with open(menufile, "r", encoding="utf-8") as readMenu:
		for line in readMenu:
			if line.strip().startswith(searchString):
				if "service=" in line:
					line = re.sub(r"service=\S+", "", line.rstrip())
				newlines.append("{} service={}\n".format(line.rstrip(), configServer))
				continue

			newlines.append(line)

	with open(menufile, "w", encoding="utf-8") as writeMenu:
		writeMenu.writelines(newlines)
