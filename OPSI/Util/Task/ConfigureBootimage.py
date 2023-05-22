# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
This writes the opsi configserver URL into the default.menu file
"""

import os
import passlib.hash
import re

from OPSI.Exceptions import BackendMissingDataError

__all__ = ("patchServiceUrlInDefaultConfigs",)

def encodedPassword(clearPassword):
	while True:
		pwhash = passlib.hash.sha512_crypt.using(rounds=5000).hash(clearPassword)
		if not pwhash or "." in pwhash:
			print("Invalid hash, retrying")
		else:
			return pwhash

def patchServiceUrlInDefaultConfigs(backend):
	"""
	Patches the clientconfig.configserver.url into the default.menu/grub.cfg

	:param backend: The backend used to read the configuration
	:type backend: ConfigDataBackend
	"""
	try:
		configServer = backend.config_getObjects(attributes=["defaultValues"], id="clientconfig.configserver.url")[0]
		configServer = configServer.defaultValues[0]
	except IndexError:
		raise BackendMissingDataError("Unable to get clientconfig.configserver.url") from IndexError

	if configServer:
		defaultMenu, grubMenu = getMenuFiles()
		patchMenuFile(defaultMenu, "append", configServer)
		patchMenuFile(grubMenu, "linux", configServer)

def patchRootPasswordInDefaultConfigs(backend):
	"""
	Patches the opsi-linux-bootimage.append password into the default.menu/grub.cfg

	:param backend: The backend used to read the configuration
	:type backend: ConfigDataBackend
	"""
	try:
		appendParameter = backend.config_getObjects(attributes=["defaultValues"], id="opsi-linux-bootimage.append")[0]
		appendParameter = appendParameter.defaultValues
	except IndexError:
		raise BackendMissingDataError("Unable to get opsi-linux-bootimage.append") from IndexError
	
	if appendParameter:
		for element in appendParameter:
			if "bootimageRootPassword" in element:
				clearRootPassword = element.split("=")[1]
				endcodedRootPassword = encodedPassword(clearRootPassword)
				pwhEntry = f"pwh={endcodedRootPassword}"
			if "pwh=" in element:
				pwhEntry = element
			if pwhEntry:
				defaultMenu, grubMenu = getMenuFiles()
				patchMenuFile(defaultMenu, "append", pwhEntry)
				patchMenuFile(grubMenu, "linux", pwhEntry)


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


def patchMenuFile(menufile, searchString, placement):
	"""
	Patch the address to the `placement` into `menufile`.

	To find out where to patch we look for lines that starts with the
	given `searchString` (excluding preceding whitespace).

	:param menufile: Path to the file to patch
	:type menufile: str
	:param searchString: Patches only lines starting with this string.
	:type searchString: str
	:param placement: The configServer address or password hash to patch \
into the file.
	:type placement: str
	"""
	newlines = []
	if "https" in placement:
		logger.notice("setting configserver URL to: %s", placement)
	if "pwh=" in placement:
		logger.debug("setting root password to: %s", placement)
	
	with open(menufile, "r", encoding="utf-8") as readMenu:
		for line in readMenu:
			if line.strip().startswith(searchString):
				if "service=" in line:
					line = re.sub(r"\s?service=\S+", "", line)
				if "pwh=" in line:
					line = re.sub(r"\s?pwh=\S+", "", line)
				logger.debug("patching line: %s", line)
				if placement.startswith("https"):
					logger.debug("line before adding configserver service address: %s", line)
					newlines.append(line.replace("console=ttyS0", "console=ttyS0 service=" + placement))
					logger.debug("line after adding configserver service address: %s", line)
				if placement.startswith("pwh="):
					logger.debug("line before adding root password: %s", line)
					newlines.append(line.replace("console=ttyS0", "console=ttyS0 " + placement))
					logger.debug("line after adding root password: %s", line)

				continue

			newlines.append(line)

	with open(menufile, "w", encoding="utf-8") as writeMenu:
		writeMenu.writelines(newlines)
