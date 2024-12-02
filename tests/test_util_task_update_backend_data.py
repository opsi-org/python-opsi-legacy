# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the update of configuration data.
"""

import pytest

from OPSI.Object import OpsiClient, OpsiDepotserver, OpsiConfigserver
from OPSI.Util.Task.UpdateBackend.ConfigurationData import updateBackendData

from .test_hosts import getLocalHostFqdn
from .helpers import mock


@pytest.mark.parametrize(
	"onSuse, expectedLocalPath",
	(
		(True, "file:///var/lib/opsi/workbench"),
		(False, "file:///home/opsiproducts"),
	),
)
def testUpdateBackendData(backendManager, onSuse, expectedLocalPath):
	def getDepotAddress(address):
		_, addressAndPath = address.split(":")
		return addressAndPath.split("/")[2]

	addServers(backendManager)
	with mock.patch(
		"OPSI.Util.Task.UpdateBackend.ConfigurationData.isOpenSUSE", lambda: onSuse
	):
		with mock.patch(
			"OPSI.Util.Task.UpdateBackend.ConfigurationData.isSLES", lambda: onSuse
		):
			updateBackendData(backendManager)

	servers = backendManager.host_getObjects(
		type=["OpsiDepotserver", "OpsiConfigserver"]
	)
	assert servers, "No servers found in backend."

	for server in servers:
		assert server.workbenchLocalUrl == expectedLocalPath

		depotAddress = getDepotAddress(server.depotRemoteUrl)
		expectedAddress = "smb://" + depotAddress + "/opsi_workbench"
		assert expectedAddress == server.workbenchRemoteUrl


def addServers(backend):
	localHostFqdn = getLocalHostFqdn()
	configServer = OpsiConfigserver(
		id=localHostFqdn, depotRemoteUrl="smb://192.168.123.1/opsi_depot"
	)
	backend.host_createObjects([configServer])

	_, domain = localHostFqdn.split(".", 1)

	def getDepotRemoteUrl(index):
		if index % 2 == 0:
			return "smb://192.168.123.{}/opsi_depot".format(index)
		else:
			return "smb://somename/opsi_depot"

	depots = [
		OpsiDepotserver(
			id="depot{n}.{domain}".format(n=index, domain=domain),
			depotRemoteUrl=getDepotRemoteUrl(index),
		)
		for index in range(10)
	]
	backend.host_createObjects(depots)

	clients = [
		OpsiClient(id="client{n}.{domain}".format(n=index, domain=domain))
		for index in range(10)
	]
	backend.host_createObjects(clients)
