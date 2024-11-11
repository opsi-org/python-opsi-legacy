# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Updating backend data.

This holds backend-independent migrations.
"""

from opsicommon.logging import get_logger

from OPSI.System.Posix import isOpenSUSE, isSLES

__all__ = ("updateBackendData",)

logger = get_logger("opsi.general")


def updateBackendData(backend):
	setDefaultWorkbenchLocation(backend)


def setDefaultWorkbenchLocation(backend):
	"""
	Set the possibly missing workbench location on the server.

	The value is regarded as missing if it is not set to None.
	`workbenchLocalUrl` will be set to `file:///var/lib/opsi/workbench`
	on SUSE system and to `file:///home/opsiproducts` on others.
	`workbenchRemoteUrl` will use the same value for the depot address
	that is set in `depotRemoteUrl` and then will point to the samba
	share _opsi_workbench_.
	"""
	servers = backend.host_getObjects(type=["OpsiDepotserver", "OpsiConfigserver"])

	if isSLES() or isOpenSUSE():
		# On Suse
		localWorkbenchPath = "file:///var/lib/opsi/workbench"
	else:
		# On non-SUSE systems the path was usually /home/opsiproducts
		localWorkbenchPath = "file:///home/opsiproducts"

	changedServers = set()
	for server in servers:
		if server.getWorkbenchLocalUrl() is None:
			logger.notice(
				"Setting missing value for workbenchLocalUrl on %s to %s",
				server.id,
				localWorkbenchPath,
			)
			server.setWorkbenchLocalUrl(localWorkbenchPath)
			changedServers.add(server)

		if server.getWorkbenchRemoteUrl() is None:
			depotAddress = getServerAddress(server.depotRemoteUrl)
			remoteWorkbenchPath = f"smb://{depotAddress}/opsi_workbench"
			logger.notice(
				"Setting missing value for workbenchRemoteUrl on %s to %s",
				server.id,
				remoteWorkbenchPath,
			)
			server.setWorkbenchRemoteUrl(remoteWorkbenchPath)
			changedServers.add(server)

	if changedServers:
		backend.host_updateObjects(changedServers)


def getServerAddress(depotRemoteUrl):
	"""
	Get the address of the server from the `depotRemoteUrl`.

	:param depotRemoteUrl: the depotRemoteUrl of an OpsiDepotserver
	:type depotRemoteUrl: str
	:rtype: str
	"""
	_, addressAndPath = depotRemoteUrl.split(":")
	return addressAndPath.split("/")[2]
