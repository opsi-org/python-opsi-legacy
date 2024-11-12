# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Functionality to automatically configure the DHCPD-backend.

.. versionadded:: 4.0.6.40
"""

from __future__ import absolute_import

import grp
import os
import pwd
import shutil
import time

from opsicommon.logging import get_logger

from OPSI.Config import OPSI_ADMIN_GROUP as ADMIN_GROUP
from OPSI.Config import OPSICONFD_USER
from OPSI.System import execute
from OPSI.System.Posix import (
	getDHCPDRestartCommand,
	getNetworkConfiguration,
	isCentOS,
	isOpenSUSE,
	isRHEL,
	isSLES,
	locateDHCPDConfig,
)
from OPSI.Util.File import DHCPDConf_Block, DHCPDConf_Parameter, DHCPDConfFile

logger = get_logger("opsi.general")

DHCPD_CONF = locateDHCPDConfig(default="/etc/dhcp/dhcpd.conf")


def configureDHCPD(configFile=DHCPD_CONF):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
	"""
	Configure the configuration file for DHCPD.

	If any changes are made the original file will be backed up.
	The backup file has a timestamp appended to the filename.

	:param configFile: The configuration file for DHCP.
	"""
	if not os.path.exists(configFile):
		logger.warning("Can't find an dhcpd.conf. Aborting configuration.")
		return

	logger.notice("Configuring dhcpd")
	sysConfig = getNetworkConfiguration()
	if not sysConfig["ipAddress"]:
		raise ValueError("Failed to find local ip address")

	dhcpdConf = DHCPDConfFile(configFile)
	dhcpdConf.parse()

	confChanged = False
	if (
		dhcpdConf.getGlobalBlock()
		.getParameters_hash()
		.get("use-host-decl-names", False)
	):
		logger.info("  use-host-decl-names already enabled")
	else:
		confChanged = True
		logger.notice("  enabling use-host-decl-names")
		dhcpdConf.getGlobalBlock().addComponent(
			DHCPDConf_Parameter(
				startLine=-1,
				parentBlock=dhcpdConf.getGlobalBlock(),
				key="use-host-decl-names",
				value=True,
			)
		)

	subnets = dhcpdConf.getGlobalBlock().getBlocks("subnet", recursive=True)
	if not subnets:
		confChanged = True
		logger.notice("  No subnets found, adding subnet")
		dhcpdConf.getGlobalBlock().addComponent(
			DHCPDConf_Block(
				startLine=-1,
				parentBlock=dhcpdConf.getGlobalBlock(),
				type="subnet",
				settings=[
					"subnet",
					sysConfig["subnet"],
					"netmask",
					sysConfig["netmask"],
				],
			)
		)

	for subnet in dhcpdConf.getGlobalBlock().getBlocks("subnet", recursive=True):
		logger.info("  Found subnet %s/%s", subnet.settings[1], subnet.settings[3])
		groups = subnet.getBlocks("group")
		if not groups:
			confChanged = True
			logger.notice("    No groups found, adding group")
			subnet.addComponent(
				DHCPDConf_Block(
					startLine=-1, parentBlock=subnet, type="group", settings=["group"]
				)
			)

		for group in subnet.getBlocks("group"):
			logger.info("    Configuring group")
			params = group.getParameters_hash(inherit="global")

			if params.get("next-server"):
				logger.info("      next-server already set")
			else:
				confChanged = True
				group.addComponent(
					DHCPDConf_Parameter(
						startLine=-1,
						parentBlock=group,
						key="next-server",
						value=sysConfig["ipAddress"],
					)
				)
				logger.notice("      next-server set to %s", sysConfig["ipAddress"])

			if params.get("filename"):
				logger.info("      filename already set")
			else:
				confChanged = True
				filename = "linux/pxelinux.0"
				if isSLES() or isOpenSUSE():
					filename = "opsi/pxelinux.0"
				group.addComponent(
					DHCPDConf_Parameter(
						startLine=-1, parentBlock=group, key="filename", value=filename
					)
				)
				logger.notice("      filename set to %s", filename)

	restartCommand = getDHCPDRestartCommand(default="/etc/init.d/dhcp3-server restart")
	if confChanged:
		logger.notice("  Creating backup of %s", configFile)
		shutil.copy(configFile, configFile + "." + time.strftime("%Y-%m-%d_%H:%M"))

		logger.notice("  Writing new %s", configFile)
		dhcpdConf.generate()

		logger.notice("  Restarting dhcpd")
		try:
			execute(restartCommand)
		except Exception as err:  # pylint: disable=broad-except
			logger.warning(err)

	opsiconfdUid = pwd.getpwnam(OPSICONFD_USER)[2]
	adminGroupGid = grp.getgrnam(ADMIN_GROUP)[2]
	os.chown(configFile, opsiconfdUid, adminGroupGid)
	os.chmod(configFile, 0o664)

	if isRHEL() or isCentOS():
		dhcpDir = os.path.dirname(configFile)
		if dhcpDir == "/etc":
			return

		logger.notice(
			'Detected Red Hat-family system. Providing rights on "%s" to group "%s"',
			dhcpDir,
			ADMIN_GROUP,
		)
		os.chown(dhcpDir, -1, adminGroupGid)

	backendConfigFile = os.path.join("/etc", "opsi", "backends", "dhcpd.conf")
	logger.notice("Configuring backend file %s", backendConfigFile)
	insertDHCPDRestartCommand(backendConfigFile, restartCommand)


def insertDHCPDRestartCommand(dhcpBackendConfigFile, restartCommand):
	"""
	Searches for the 'reloadConfigCommand' in the given file and replaces
	the value of it with `restartCommand`.

	Since the dhcpd.conf usually contains information that is evaluated
	during runtime it is not possible to just read the config and then
	patch the value we want as this would result in destroying the
	dynamic.
	"""
	with open(dhcpBackendConfigFile, encoding="utf-8") as configFile:
		config = configFile.read()

	for line in config.split("\n"):
		if "reloadConfigCommand" in line and not line.startswith("#"):
			_, command = line.split(":", 1)

	command = command.strip()
	logger.debug("Found command: '%s'", command)

	command = command.lstrip("u").rstrip(",").strip('"')
	if command.startswith("sudo "):
		command = command[5:]
	logger.debug("Cleaned command: '%s'", command)

	with open(dhcpBackendConfigFile, "w", encoding="utf-8") as configFile:
		configFile.write(config.replace(command, restartCommand))
