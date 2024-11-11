# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
First backend initialization.

This is the first-time setup of an opsi server instance.
To work propery an initial configuration needs to take place.

This holds backend-independent migrations.
"""

import os.path

from OPSI.Backend.Base.ConfigData import OPSI_PASSWD_FILE
from OPSI.Object import OpsiConfigserver
from OPSI.System.Posix import getLocalFqdn, getNetworkConfiguration
from OPSI.Types import forceList
from OPSI.Util.Task.ConfigureBackend.ConfigurationData import initializeConfigs
from OPSI.Util.Task.Rights import set_rights
from opsicommon.logging import get_logger

__all__ = ("initializeBackends",)

logger = get_logger("opsi.general")


def initializeBackends(ipAddress=None, backendManagerConfig=None):
	"""
	Initial backend setup based on the current configuration.

	This will create required folders aswell as set up the current
	backend for use with opsi.

	:param ipAddress: Force the function to work with the given IP address.
	:type ipAddress: str
	"""
	_setupPasswdFile()

	from OPSI.Backend.BackendManager import (
		BackendManager,  # pylint: disable=import-outside-toplevel
	)

	managerConfig = {"depotBackend": False}
	if backendManagerConfig:
		managerConfig.update(backendManagerConfig)

	with BackendManager(**managerConfig) as backend:
		backend.backend_createBase()  # pylint: disable=no-member

		networkConfig = getNetworkConfiguration(ipAddress)
		fqdn = getLocalFqdn()

		logger.info("Trying to find a Configserver...")
		configServer = backend.host_getObjects(type="OpsiConfigserver")  # pylint: disable=no-member
		if not configServer and not backend.host_getIdents(
			type="OpsiConfigserver", id=fqdn
		):  # pylint: disable=no-member
			depot = backend.host_getObjects(type="OpsiDepotserver", id=fqdn)  # pylint: disable=no-member
			if not depot:
				logger.notice("Creating config server '%s'", fqdn)
				serverConfig = _getServerConfig(fqdn, networkConfig)
				backend.host_createOpsiConfigserver(**serverConfig)  # pylint: disable=no-member
				configServer = backend.host_getObjects(type="OpsiConfigserver", id=fqdn)  # pylint: disable=no-member
			else:
				logger.notice("Converting depot server '%s' to config server", fqdn)
				configServer = OpsiConfigserver.fromHash(depot[0].toHash())
				backend.host_createObjects(configServer)  # pylint: disable=no-member

				# list expected in further processing
				configServer = [configServer]
		else:
			depot = backend.host_getObjects(type="OpsiDepotserver", id=fqdn)  # pylint: disable=no-member
			if not depot:
				logger.notice("Creating depot server '%s'", fqdn)
				serverConfig = _getServerConfig(fqdn, networkConfig)
				backend.host_createOpsiDepotserver(**serverConfig)  # pylint: disable=no-member

		if configServer:
			if configServer[0].id == fqdn:
				try:
					configServer = backend.host_getObjects(type="OpsiConfigserver")[0]  # pylint: disable=no-member
				except IndexError as err:
					raise RuntimeError(f"Config server '{fqdn}' not found") from err

				if networkConfig["ipAddress"]:
					configServer.setIpAddress(networkConfig["ipAddress"])
				if networkConfig["hardwareAddress"]:
					configServer.setHardwareAddress(networkConfig["hardwareAddress"])

				# make sure the config server is present in all backends or we get reference error later on
				backend.host_insertObject(configServer)  # pylint: disable=no-member

			# initializeConfigs does only handle a single object
			configServer = forceList(configServer)[0]

		initializeConfigs(backend=backend, configServer=configServer)

	_setupDepotDirectory()
	_setupWorkbenchDirectory()


def _setupPasswdFile():
	"""
	Set up the opsi passwd file and set the correct rights.
	"""
	if not os.path.exists(OPSI_PASSWD_FILE):
		with open(OPSI_PASSWD_FILE, mode="w", encoding="utf-8"):
			pass
		set_rights(OPSI_PASSWD_FILE)


def _getServerConfig(fqdn, networkConfig):
	"""
	Prepare the configuration of the local server.

	:param networkConfig: Network configuration for the local host.
	:type networkConfig: dict
	:rtype: dict
	"""
	config = dict(
		id=fqdn,
		opsiHostKey=None,
		depotLocalUrl="file:///var/lib/opsi/depot",
		depotRemoteUrl=f"smb://{fqdn}/opsi_depot",
		depotWebdavUrl=f"webdavs://{fqdn}:4447/depot",
		repositoryLocalUrl="file:///var/lib/opsi/repository",
		repositoryRemoteUrl=f"webdavs://{fqdn}:4447/repository",
		workbenchLocalUrl="file:///var/lib/opsi/workbench",
		workbenchRemoteUrl=f"smb://{fqdn}/opsi_workbench",
		description=None,
		notes=None,
		hardwareAddress=networkConfig["hardwareAddress"],
		ipAddress=networkConfig["ipAddress"],
		inventoryNumber=None,
		networkAddress=f"{networkConfig['subnet']}/{networkConfig['netmask']}",
		maxBandwidth=0,
		isMasterDepot=True,
		masterDepotId=None,
	)

	logger.debug("Server configuration is: %s", config)
	return config


def _setupDepotDirectory():
	"""
	Set up the directory for the depot.
	"""
	depotDir = "/var/lib/opsi/depot"
	try:
		os.mkdir(depotDir)
	except OSError as error:
		if error.errno != 17:  # 17 is File exists
			logger.warning("Failed to create depot directory '%s': %s", depotDir, error)


def _setupWorkbenchDirectory():
	"""
	Set up the directory for the workbench in case it is missing.

	The path is `/var/lib/opsi/workbench`.
	"""
	try:
		os.mkdir("/var/lib/opsi/workbench")
	except OSError as error:
		if error.errno != 17:  # 17 is File exists
			logger.warning("Failed to create workbench directory: %s", error)
