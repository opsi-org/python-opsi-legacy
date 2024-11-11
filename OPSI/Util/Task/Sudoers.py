# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Util - Task - Sudoers

Functionality to patch a sudoers file on a Linux system.

.. versionadded:: 4.0.4.3


.. versionchanged:: 4.0.6.3

	The path to service is received directly from the OS.


.. versionchanged:: 4.0.6.6

	Avoid duplicating settings.
"""

import codecs
import shutil
import time

from opsicommon.logging import get_logger

from OPSI.Config import FILE_ADMIN_GROUP
from OPSI.System.Posix import Distribution, which

SUDOERS_FILE = "/etc/sudoers"
_NO_TTY_REQUIRED_DEFAULT = "Defaults:opsiconfd !requiretty"

try:
	_NO_TTY_FOR_SERVICE_REQUIRED = f"Defaults!{which('service')} !requiretty"
except Exception:  # pylint: disable=broad-except
	_NO_TTY_FOR_SERVICE_REQUIRED = "Defaults!/sbin/service !requiretty"

logger = get_logger("opsi.general")


def patchSudoersFileForOpsi(sudoersFile=SUDOERS_FILE):
	"""
	Patches the sudoers file so opsiconfd and the OPSI file admins can \
call opsi-set-rights.

	:param sudoersFile: The path to the sudoers file.
	"""
	entries = [
		"opsiconfd ALL=NOPASSWD: /usr/bin/opsi-set-rights",
		f"%{FILE_ADMIN_GROUP} ALL=NOPASSWD: /usr/bin/opsi-set-rights",
	]

	_patchSudoersFileWithEntries(sudoersFile, entries)


def patchSudoersFileToAllowRestartingDHCPD(
	dhcpdRestartCommand, sudoersFile=SUDOERS_FILE
):
	"""
	Patches the sudoers file so opsiconfd can restart the DHCP daemon
	and execute the ``service`` command without an tty.

	:param dhcpdRestartCommand: The command used to restart the DHCP daemon
	:param sudoersFile: The path to the sudoers file.
	"""
	entries = [f"opsiconfd ALL=NOPASSWD: {dhcpdRestartCommand}\n"]

	_patchSudoersFileWithEntries(sudoersFile, entries)


def _patchSudoersFileWithEntries(sudoersFile, entries):
	"""
	Patches ``sudoersFile`` with ``entries`` if they are missing.

	.. versionadded:: 4.0.4.6


	.. versionchanged:: 4.0.5.15

		Do not require a TTY for running the service command.


	.. versionchanged:: 4.0.6.3

		Add single entry if missing.

	"""
	entries = [element.strip() for element in entries]
	lines = []
	ttyPatchRequired = True
	servicePatchRequired = True

	with codecs.open(sudoersFile, "r", "utf-8") as inputFile:
		for line in inputFile:
			if _NO_TTY_REQUIRED_DEFAULT in line:
				ttyPatchRequired = False
			elif _NO_TTY_FOR_SERVICE_REQUIRED in line:
				servicePatchRequired = False

			lines.append(line)

	# Stripping is important to avoid problems with newlines.
	entriesToAdd = set(entries) - set(line.strip() for line in lines)

	ttyPatchRequired = ttyPatchRequired and distributionRequiresNoTtyPatch()
	modifyFile = ttyPatchRequired or servicePatchRequired or entriesToAdd
	if modifyFile:
		logger.notice("   Adding sudoers entries for opsi")

	if entriesToAdd:
		for entry in entriesToAdd:
			lines.append(f"{entry}\n")

	if ttyPatchRequired:
		lines.append(f"{_NO_TTY_REQUIRED_DEFAULT}\n")

	if servicePatchRequired:
		lines.append(f"{_NO_TTY_FOR_SERVICE_REQUIRED}\n")

	if modifyFile:
		lines.append("\n")

		logger.notice("   Creating backup of %s", sudoersFile)
		shutil.copy(sudoersFile, f"{sudoersFile}.{time.strftime('%Y-%m-%d_%H:%M')}")

		logger.notice("   Writing new %s", sudoersFile)
		with codecs.open(sudoersFile, "w", "utf-8") as outputFile:
			outputFile.writelines(lines)


def distributionRequiresNoTtyPatch():
	"""
	Checks if the used Distribution requires a patch to use sudo without a tty.

	.. versionadded:: 4.0.4.3

	:rtype: bool
	"""
	distributor = Distribution().distributor.lower()

	return bool("redhat" in distributor or "centos" in distributor)
