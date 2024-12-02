# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Configuration data for the backend.

.. versionadded:: 4.0.6.1
"""

import codecs
import os
import re
from collections import namedtuple
from typing import List

from opsicommon.logging import get_logger

import OPSI.Backend.BackendManager as bm
from OPSI.Object import BoolConfig, Config, OpsiConfigserver, UnicodeConfig
from OPSI.System import Posix

logger = get_logger("opsi.general")

SimpleBoolConfig = namedtuple("SimpleBoolConfig", ["id", "description", "value"])
SimpleUnicodeConfig = namedtuple("SimpleUnicodeConfig", ["id", "description", "values"])


def initializeConfigs(
	backend: bm.BackendManager = None,
	configServer: OpsiConfigserver = None,
	pathToSMBConf: str = None,
) -> None:
	"""
	Adding default configurations to the backend.

	:param backend: The backend to use. If this is ``None`` a backend \
will be created.
	:param configServer: The ConfigServer that should be used as \
default. Supply this if ``clientconfig.configserver.url`` or \
``clientconfig.depot.id`` are not yet set.
	:param pathToSMBConf: The path the samba configuration.


	.. versionchanged:: 4.0.6.1

		Adding ``dynamic`` as value for ``clientconfig.depot.drive`` if missing.


	.. versionchanged:: 4.0.6.3

		Adding WAN extension configurations if missing.


	.. versionchanged:: 4.0.7.24

		On UCR we try read the domain for ``clientconfig.depot.user``
		preferably from Univention config registry (UCR).
	"""
	backendProvided = True

	if backend is None:
		backendProvided = False
		backend = bm.BackendManager()
		backend.backend_createBase()

	logger.notice("Setting up default values.")
	create_default_configs(backend, configServer, pathToSMBConf)
	addDynamicDepotDriveSelection(backend)
	createWANconfigs(backend)
	createInstallByShutdownConfig(backend)
	createUserProfileManagementDefaults(backend)

	logger.notice("Finished setting up default values.")
	if not backendProvided:
		backend.backend_exit()


def create_default_configs(
	backend: bm.BackendManager,
	configServer: OpsiConfigserver = None,
	pathToSMBConf: str = None,
) -> None:
	configIdents = set(backend.config_getIdents(returnType="unicode"))
	configs = []
	config_states = []

	if "clientconfig.depot.user" not in configIdents:
		logger.debug("Missing clientconfig.depot.user - adding it.")

		depotuser = "pcpatch"
		depotdomain = None
		if Posix.isUCS():
			logger.info("Reading domain from UCR")
			depotdomain = readWindowsDomainFromUCR()
			if not depotdomain:
				logger.info("Reading domain from UCR returned no result")
		if not depotdomain:
			logger.info("Trying to read domain from samba config")
			depotdomain = readWindowsDomainFromSambaConfig(pathToSMBConf)

		if depotdomain:
			depotuser = "\\".join((depotdomain, depotuser))

		logger.debug("Using '%s' as clientconfig.depot.user", depotuser)

		configs.append(
			UnicodeConfig(
				id="clientconfig.depot.user",
				description="User for depot share",
				possibleValues=[],
				defaultValues=[depotuser],
				editable=True,
				multiValue=False,
			)
		)

	if configServer and "clientconfig.configserver.url" not in configIdents:
		logger.debug("Missing clientconfig.configserver.url - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.configserver.url",
				description="URL(s) of opsi config service(s) to use",
				possibleValues=[f"https://{configServer.getId()}:4447/rpc"],
				defaultValues=[f"https://{configServer.getId()}:4447/rpc"],
				editable=True,
				multiValue=True,
			)
		)

	if configServer and "clientconfig.depot.id" not in configIdents:
		logger.debug("Missing clientconfig.depot.id - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.depot.id",
				description="ID of the opsi depot to use",
				possibleValues=[configServer.getId()],
				defaultValues=[configServer.getId()],
				editable=True,
				multiValue=False,
			)
		)

	if "clientconfig.depot.dynamic" not in configIdents:
		logger.debug("Missing clientconfig.depot.dynamic - adding it.")
		configs.append(
			BoolConfig(
				id="clientconfig.depot.dynamic",
				description="Use dynamic depot selection",
				defaultValues=[False],
			)
		)

	if "clientconfig.depot.drive" not in configIdents:
		logger.debug("Missing clientconfig.depot.drive - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.depot.drive",
				description="Drive letter for depot share",
				possibleValues=[
					"a:",
					"b:",
					"c:",
					"d:",
					"e:",
					"f:",
					"g:",
					"h:",
					"i:",
					"j:",
					"k:",
					"l:",
					"m:",
					"n:",
					"o:",
					"p:",
					"q:",
					"r:",
					"s:",
					"t:",
					"u:",
					"v:",
					"w:",
					"x:",
					"y:",
					"z:",
					"dynamic",
				],
				defaultValues=["p:"],
				editable=False,
				multiValue=False,
			)
		)

	if "clientconfig.depot.protocol" not in configIdents:
		logger.debug("Missing clientconfig.depot.protocol - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.depot.protocol",
				description="Protocol to use when mounting an depot share on the client",
				possibleValues=["cifs", "webdav"],
				defaultValues=["cifs"],
				editable=False,
				multiValue=False,
			)
		)

	if "clientconfig.depot.protocol.netboot" not in configIdents:
		logger.debug("Missing clientconfig.depot.protocol.netboot - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.depot.protocol.netboot",
				description="Protocol to use when mounting an depot share in netboot environment",
				possibleValues=["cifs", "webdav"],
				defaultValues=["cifs"],
				editable=False,
				multiValue=False,
			)
		)

	if "clientconfig.windows.domain" not in configIdents:
		logger.debug("Missing clientconfig.windows.domain - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.windows.domain",
				description="Windows domain",
				possibleValues=[],
				defaultValues=[readWindowsDomainFromSambaConfig(pathToSMBConf)],
				editable=True,
				multiValue=False,
			)
		)

	if "opsiclientd.global.verify_server_cert" not in configIdents:
		logger.debug("Missing opsiclientd.global.verify_server_cert - adding it.")
		configs.append(
			BoolConfig(
				id="opsiclientd.global.verify_server_cert",
				description="Verify opsi server TLS certificates",
				defaultValues=[False],
			)
		)

	if "opsiclientd.global.install_opsi_ca_into_os_store" not in configIdents:
		logger.debug(
			"Missing opsiclientd.global.install_opsi_ca_into_os_store - adding it."
		)
		configs.append(
			BoolConfig(
				id="opsiclientd.global.install_opsi_ca_into_os_store",
				description="Automatically install opsi CA into operating systems certificate store",
				defaultValues=[False],
			)
		)

	if "opsi-linux-bootimage.append" not in configIdents:
		logger.debug("Missing opsi-linux-bootimage.append - adding it.")
		configs.append(
			UnicodeConfig(
				id="opsi-linux-bootimage.append",
				description="Extra options to append to kernel command line",
				possibleValues=[
					"acpi=off",
					"irqpoll",
					"noapic",
					"pci=nomsi",
					"vga=normal",
					"reboot=b",
					"mem=2G",
					"nomodeset",
					"ramdisk_size=2097152",
					"dhclienttimeout=N",
				],
				defaultValues=[""],
				editable=True,
				multiValue=True,
			)
		)

	if "license-management.use" not in configIdents:
		logger.debug("Missing license-management.use - adding it.")
		configs.append(
			BoolConfig(
				id="license-management.use",
				description="Activate license management",
				defaultValues=[False],
			)
		)

	if "software-on-demand.active" not in configIdents:
		logger.debug("Missing software-on-demand.active - adding it.")
		configs.append(
			BoolConfig(
				id="software-on-demand.active",
				description="Activate software-on-demand",
				defaultValues=[False],
			)
		)

	if "software-on-demand.product-group-ids" not in configIdents:
		logger.debug("Missing software-on-demand.product-group-ids - adding it.")
		configs.append(
			UnicodeConfig(
				id="software-on-demand.product-group-ids",
				description=(
					"Product group ids containing products which are "
					"allowed to be installed on demand"
				),
				possibleValues=["software-on-demand"],
				defaultValues=["software-on-demand"],
				editable=True,
				multiValue=True,
			)
		)

	if "clientconfig.dhcpd.filename" not in configIdents:
		logger.debug("Missing clientconfig.dhcpd.filename - adding it.")
		configs.append(
			UnicodeConfig(
				id="clientconfig.dhcpd.filename",
				description=(
					"The name of the file that will be presented to the "
					"client on an TFTP request. For an client that should "
					"boot via UEFI this must include the term 'elilo'."
				),
				possibleValues=["elilo"],
				defaultValues=[""],
				editable=True,
				multiValue=False,
			)
		)

	backend.config_createObjects(configs)
	if config_states:
		backend.configState_createObjects(config_states)


def readWindowsDomainFromSambaConfig(pathToConfig: str = None) -> str:
	"""
	Get the Windows domain (workgroup) from smb.conf.
	If no workgroup can be found this returns an empty string.

	:param pathToConfig: Path to the smb.conf
	:return: The Windows domain in uppercase letters.
	"""
	winDomain = ""
	if pathToConfig and os.path.exists(pathToConfig):
		pattern = re.compile(r"^\s*workgroup\s*=\s*(\S+)\s*$")
		with codecs.open(pathToConfig, "r", "utf-8") as sambaConfig:
			for line in sambaConfig:
				match = pattern.search(line)
				if match:
					winDomain = match.group(1).upper()
					break

	return winDomain


def readWindowsDomainFromUCR() -> str:
	"""
	Get the Windows domain from Univention Config registry.
	If no domain can be found this returns an empty string.

	:return: The Windows domain in uppercase letters.
	"""
	domain = ""
	try:
		readCommand = f"{Posix.which('ucr')} get windows/domain"
		for output in Posix.execute(readCommand):
			if output:
				domain = output.strip().upper()
				break
	except Posix.CommandNotFoundException as missingCommandError:
		logger.info("Could not find ucr: %s", missingCommandError)

	return domain


def addDynamicDepotDriveSelection(backend: bm.BackendManager):
	config = backend.config_getObjects(id="clientconfig.depot.drive")[0]

	if "dynamic" not in config.possibleValues:
		logger.debug(
			"Could not find possibility to select dynamic drive selection. Adding it to 'clientconfig.depot.drive'."
		)

		config.possibleValues.append("dynamic")
		backend.config_updateObject(config)


def createWANconfigs(backend: bm.BackendManager) -> None:
	"Create the configurations that are used by the WAN extension if missing."

	configs = [
		SimpleBoolConfig(
			"opsiclientd.event_gui_startup.active", "gui_startup active", True
		),
		SimpleBoolConfig(
			"opsiclientd.event_gui_startup{user_logged_in}.active",
			"gui_startup{user_logged_in} active",
			True,
		),
		SimpleBoolConfig(
			"opsiclientd.event_net_connection.active",
			"event_net_connection active",
			False,
		),
		SimpleBoolConfig("opsiclientd.event_timer.active", "event_timer active", False),
	]

	_createBooleanConfigsIfMissing(backend, configs)


def _createBooleanConfigsIfMissing(
	backend: bm.BackendManager, configs: List[Config]
) -> None:
	availableConfigs = set(backend.config_getIdents())
	for config in configs:
		if config.id not in availableConfigs:
			logger.debug("Adding missing config '%s", config.id)
			backend.config_createBool(config.id, config.description, config.value)


def createInstallByShutdownConfig(backend: bm.BackendManager) -> None:
	"Create the configurations that are used by the InstallByShutdown extension if missing."

	config = SimpleBoolConfig(
		"clientconfig.install_by_shutdown.active", "install_by_shutdown active", False
	)

	_createBooleanConfigsIfMissing(backend, [config])


def createUserProfileManagementDefaults(backend: bm.BackendManager) -> None:
	"Create the default configuration for the User Profile Management extension."

	eventActiveConfig = SimpleBoolConfig(
		"opsiclientd.event_user_login.active", "user_login active", False
	)
	_createBooleanConfigsIfMissing(backend, [eventActiveConfig])

	actionProcressorCommand = SimpleUnicodeConfig(
		"opsiclientd.event_user_login.action_processor_command",
		"user_login action_processor",
		["%action_processor.command% /sessionid service_session /loginscripts /silent"],
	)

	if actionProcressorCommand.id not in set(backend.config_getIdents()):
		logger.debug("Adding missing config '%s'", actionProcressorCommand.id)
		backend.config_createUnicode(
			actionProcressorCommand.id,
			actionProcressorCommand.description,
			possibleValues=actionProcressorCommand.values,
			defaultValues=actionProcressorCommand.values,
		)
