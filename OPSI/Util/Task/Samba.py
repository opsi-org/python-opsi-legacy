# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Configuration of Samba for the use with opsi.
"""

import codecs
import os
import shutil
import time

from OPSI.System import execute, which
from OPSI.System.Posix import getSambaServiceName
from opsicommon.logging import get_logger

__all__ = ("configureSamba", "isSamba4")

SMB_CONF = "/etc/samba/smb.conf"

logger = get_logger("opsi.general")


def configureSamba(config=SMB_CONF):
	"""
	Configure the Samba configuration to include the required shares.

	:param config: The path to the Samba configuration file.
	:type config: str
	"""
	logger.notice("Configuring samba")
	lines = _readConfig(config)
	newlines = _processConfig(lines)
	if lines != newlines:
		_writeConfig(newlines, config)
		_reloadSamba()
		logger.notice(
			"Samba configuration finished. You may want to restart your Samba daemon."
		)


def _readConfig(config):
	with codecs.open(config, "r", "utf-8") as readConf:
		return readConf.readlines()


def _processConfig(lines):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
	newlines = []
	optPcbinShareFound = False
	depotShareFound = False
	depotShareRWFound = False
	workbenchShareFound = False
	opsiImagesFound = False
	repositoryFound = False
	logsFound = False
	oplocksFound = False

	samba4 = isSamba4()

	for line in lines:
		currentLine = line.lower().strip()
		if currentLine == "[opt_pcbin]":
			optPcbinShareFound = True
		elif currentLine == "[opsi_depot]":
			depotShareFound = True
		elif currentLine == "[opsi_depot_rw]":
			depotShareRWFound = True
		elif currentLine == "[opsi_images]":
			opsiImagesFound = True
		elif currentLine == "[opsi_workbench]":
			workbenchShareFound = True
		elif currentLine == "[opsi_repository]":
			repositoryFound = True
		elif currentLine == "[opsi_logs]":
			logsFound = True
		elif "oplocks" in currentLine:
			oplocksFound = True
		newlines.append(line)

	if optPcbinShareFound:
		logger.warning(
			"Share opt_pcbin configuration found. You should use opsi_depot_rw instead, if you need a writeable depot-Share."
		)

	if not depotShareFound:
		logger.notice("   Adding share [opsi_depot]")
		newlines.append("[opsi_depot]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi depot share (ro)\n")
		newlines.append("   path = /var/lib/opsi/depot\n")
		newlines.append("   follow symlinks = yes\n")
		newlines.append("   writeable = no\n")
		newlines.append("   invalid users = root\n")
		if samba4:
			newlines.append("   acl allow execute always = true\n")
		newlines.append("\n")
	elif samba4:
		logger.notice(
			"   Share opsi_depot found and samba 4 is detected. Setting executable fix on opsi_depot share"
		)
		tmp_lines = []
		in_opsi_depot_section = False
		for i, line in enumerate(newlines):
			last_line_of_file = i + 1 == len(newlines)
			if line.lower().strip() == "[opsi_depot]":
				in_opsi_depot_section = True
			elif in_opsi_depot_section:
				if line.lower().strip().startswith("[") or last_line_of_file:
					# next section or last line of file
					logger.notice("   Adding 'acl allow execute always = true'")
					tmp_lines.append("   acl allow execute always = true\n")
					in_opsi_depot_section = False
				if not line.strip():
					# remove empty line
					continue
				if line.lower().find("admin users") != -1:
					logger.notice("   Removing old executable fix (%s)", line.strip())
					continue
				if line.lower().find("acl allow execute always") != -1:
					# remove, will be re-inserted add the end of the section
					logger.info("   Removing (%s)", line.strip())
					continue
			tmp_lines.append(line)
		newlines = tmp_lines

	if not depotShareRWFound:
		logger.notice("   Adding share [opsi_depot_rw]")
		newlines.append("[opsi_depot_rw]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi depot share (rw)\n")
		newlines.append("   path = /var/lib/opsi/depot\n")
		newlines.append("   follow symlinks = yes\n")
		newlines.append("   writeable = yes\n")
		newlines.append("   invalid users = root\n")
		newlines.append("\n")

	if not opsiImagesFound:
		logger.notice("   Adding share [opsi_images]")
		newlines.append("[opsi_images]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi ntfs images share (rw)\n")
		newlines.append("   path = /var/lib/opsi/ntfs-images\n")
		newlines.append("   writeable = yes\n")
		newlines.append("   invalid users = root\n")
		newlines.append("\n")
		if not os.path.exists("/var/lib/opsi/ntfs-images"):
			logger.debug("Path:  /var/lib/opsi/ntfs-images not found: creating.")
			os.mkdir("/var/lib/opsi/ntfs-images")

	if not workbenchShareFound:
		logger.notice("   Adding share [opsi_workbench]")
		newlines.append("[opsi_workbench]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi workbench\n")
		newlines.append("   path = /var/lib/opsi/workbench\n")
		newlines.append("   writeable = yes\n")
		newlines.append("   invalid users = root\n")
		newlines.append("   create mask = 0660\n")
		newlines.append("   directory mask = 0770\n")
		newlines.append("\n")

	if not repositoryFound:
		logger.notice("  Adding share [opsi_repository]")
		newlines.append("[opsi_repository]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi repository share (ro)\n")
		newlines.append("   path = /var/lib/opsi/repository\n")
		newlines.append("   follow symlinks = yes\n")
		newlines.append("   writeable = no\n")
		newlines.append("   invalid users = root\n")
		newlines.append("\n")

	if not logsFound:
		logger.notice("  Adding share [opsi_logs]")
		newlines.append("[opsi_logs]\n")
		newlines.append("   available = yes\n")
		newlines.append("   comment = opsi logs share (ro)\n")
		newlines.append("   path = /var/log/opsi\n")
		newlines.append("   follow symlinks = yes\n")
		newlines.append("   writeable = no\n")
		newlines.append("   invalid users = root\n")
		newlines.append("\n")

	if oplocksFound:
		logger.warning(
			"Detected oplocks in your samba configuration. "
			"It is not recommended to use them with opsi. "
			"Please see the opsi manual for further information."
		)

	return newlines


def isSamba4():
	"""
	Check if the current system uses samba 4.

	:return: True if running Samba 4. False otherwise.
	:rtype: bool
	"""
	samba4 = False

	try:
		smbd = which("smbd")
		result = execute(f"{smbd} -V 2>/dev/null")
		for line in result:
			if line.lower().startswith("version"):
				samba4 = line.split()[1].startswith("4")
	except Exception as err:  # pylint: disable=broad-except
		logger.debug("Getting Samba Version failed due to: %s", err)

	return samba4


def _writeConfig(newlines, config):
	logger.notice("   Creating backup of %s", config)
	shutil.copy(config, config + "." + time.strftime("%Y-%m-%d_%H:%M"))

	logger.notice("   Writing new smb.conf")
	with codecs.open(config, "w", "utf-8") as writeConf:
		writeConf.writelines(newlines)


def _reloadSamba():
	logger.notice("   Reloading samba")
	try:
		execute(f'service {getSambaServiceName(default="smbd")} reload')
	except Exception as err:  # pylint: disable=broad-except
		logger.warning(err)
