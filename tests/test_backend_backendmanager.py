# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing BackendManager.
"""

import os

import pytest

from OPSI.Backend.BackendManager import BackendManager
from OPSI.Backend.Base import ConfigDataBackend

from .Backends.File import getFileBackend
from .helpers import getLocalFQDN
from .test_configs import getConfigs
from .test_groups import fillBackendWithGroups
from .test_hosts import getClients, getConfigServer, getDepotServers
from .test_products import getProducts, getProductsOnDepot


def testBackendManagerDispatchesCallsToExtensionClass():
	"""
	Make sure that calls are dispatched to the extension class.
	These calls should not fail.
	"""

	class TestClass:
		def methodOnBackend(self, y):
			assert y == "yyyyyyyy"

		def checkIfOptionsExist(self):
			options = self.backend_getOptions()
			assert options

	cdb = ConfigDataBackend()
	bm = BackendManager(backend=cdb, extensionClass=TestClass)
	bm.methodOnBackend("yyyyyyyy")
	bm.checkIfOptionsExist()


def testBackendManagerMethods(backendManager):
	# TODO: split into multiple tests...
	bm = backendManager

	origClients = getClients()
	configServer = getConfigServer()
	depots = getDepotServers()
	origHosts = list(origClients) + list(depots) + [configServer]

	bm.host_createObjects(origClients)
	bm.host_createObjects(depots)
	bm.host_createObjects(configServer)

	hostIds = bm.host_getIdents()
	for host in origHosts:
		assert host.id in hostIds

	# No configs set - should be equal now
	client1 = origClients[0]
	assert bm.getGeneralConfig_hash() == bm.getGeneralConfig_hash(objectId=client1.id)

	origDepotserver1 = depots[0]
	origConfigs = getConfigs(origDepotserver1.id)
	for config in origConfigs:
		config.setDefaults()
	bm.config_createObjects(origConfigs)

	config1 = origConfigs[0]
	assert config1.defaultValues[0] == bm.getGeneralConfigValue(
		key=config1.id, objectId=None
	)

	generalConfig = {
		"test-key-1": "test-value-1",
		"test-key-2": "test-value-2",
		"opsiclientd.depot_server.depot_id": origDepotserver1.id,
	}
	for key, val in generalConfig.items():
		bm.config_create(id=key, defaultValues=[val])

	key = "test-key-1"
	value = bm.getGeneralConfigValue(key=key, objectId=client1.id)
	assert value == generalConfig[key]

	anotherKey = "test-key-2"
	bm.configState_create(configId=anotherKey, objectId=client1.id, values=[client1.id])
	bm.config_create(id=anotherKey, defaultValues=["changed"])
	assert "changed" == bm.getGeneralConfigValue(key=anotherKey, objectId=None)

	value = bm.getGeneralConfigValue(key=anotherKey, objectId=client1.id)
	assert value == client1.id

	bm.deleteGeneralConfig(client1.id)
	assert "changed" == bm.getGeneralConfigValue(key=anotherKey, objectId=client1.id)

	origGroups = fillBackendWithGroups(bm)

	groupIds = bm.getGroupIds_list()
	for group in origGroups:
		assert group.id in groupIds

	client2 = origClients[1]
	clients = [client1.id, client2.id]
	groupId = "a test group"
	bm.createGroup(
		groupId, members=clients, description="A test group", parentGroupId=""
	)

	assert 1 == len(bm.group_getObjects(id=groupId))

	objectToGroups = bm.objectToGroup_getObjects(groupId=groupId)
	assert 2 == len(objectToGroups)
	for objectToGroup in objectToGroups:
		assert objectToGroup.objectId in clients

	bm.group_delete(id=groupId)
	assert 0 == len(bm.group_getObjects(id=groupId))

	ipAddress = bm.getIpAddress(hostId=client1.id)
	assert ipAddress == client1.ipAddress

	_, domain = getLocalFQDN().split(".", 1)

	clientName = "test-client"
	clientId = bm.createClient(
		clientName=clientName,
		domain=domain,
		description="a description",
		notes="notes...",
		ipAddress="192.168.1.91",
		hardwareAddress="00:01:02:03:01:aa",
	)
	assert clientId == clientName + "." + domain

	clientIds = bm.host_getIdents(type="OpsiClient")
	assert clientId in clientIds

	bm.host_delete(id=clientId)
	assert clientId not in bm.host_getIdents(type="OpsiClient")

	description = "Updated description"
	notes = "Updated notes"
	opsiHostKey = "00000000001111111111222222222233"
	mac = "00:01:02:03:40:12"
	bm.setHostDescription(hostId=client1.id, description=description)
	bm.setHostNotes(hostId=client1.id, notes=notes)
	bm.setOpsiHostKey(hostId=client1.id, opsiHostKey=opsiHostKey)
	bm.setMacAddress(hostId=client1.id, mac=mac)

	host = bm.host_getObjects(id=client1.id)[0]

	assert description == host.description
	assert notes == host.notes
	assert opsiHostKey == host.opsiHostKey
	assert mac == host.hardwareAddress

	assert opsiHostKey == bm.getOpsiHostKey(hostId=client1.id)
	assert mac == bm.getMacAddress(hostId=client1.id)

	host = bm.getHost_hash(hostId=client1.id)
	serverIds = bm.getServerIds_list()
	assert isinstance(serverIds, list)
	assert serverIds
	serverId = bm.getServerId(clientId=client1.id)
	assert serverId.endswith(domain)

	depotName = origDepotserver1.id.split(".", 1)[0]
	depotRemoteUrl = "smb://{0}/xyz".format(depotName)
	depotId = bm.createDepot(
		depotName=depotName,
		domain=domain,
		depotLocalUrl="file:///xyz",
		depotRemoteUrl=depotRemoteUrl,
		repositoryLocalUrl="file:///abc",
		repositoryRemoteUrl="webdavs://{0}:4447/products".format(depotName),
		network="0.0.0.0/0",
		description="Some description",
		notes="Some notes",
		maxBandwidth=100000,
	)
	assert depotId == depotName + "." + domain

	depotIds = bm.getDepotIds_list()
	depot = bm.getDepot_hash(depotId)
	assert depot["depotRemoteUrl"] == depotRemoteUrl

	bm.host_delete(id=depotId)
	depotIds = bm.getDepotIds_list()
	assert depotId not in depotIds

	origProducts = getProducts()
	bm.product_createObjects(origProducts)

	depotserver1 = {
		"isMasterDepot": True,
		"type": "OpsiDepotserver",
		"id": origDepotserver1.id,
	}
	bm.host_createObjects(depotserver1)

	origProductOnDepots = getProductsOnDepot(origProducts, configServer, depots)
	bm.productOnDepot_createObjects(origProductOnDepots)

	origProduct1 = origProducts[0]
	bm.lockProduct(productId=origProduct1.id, depotIds=[origDepotserver1.id])
	productLocks = bm.getProductLocks_hash(depotIds=[])
	for prductId, depotIds in productLocks.items():
		assert prductId == origProduct1.id
		assert 1 == len(depotIds)
		assert depotIds[0] == origDepotserver1.id

	bm.unlockProduct(productId=origProduct1.id, depotIds=[])
	assert not bm.getProductLocks_hash(depotIds=[])

	productId1 = "test-localboot-1"
	bm.createLocalBootProduct(
		productId=productId1,
		name="Some localboot product",
		productVersion="1.0",
		packageVersion="1",
		licenseRequired=0,
		setupScript="",
		uninstallScript="",
		updateScript="",
		alwaysScript="",
		onceScript="",
		priority=0,
		description="",
		advice="",
		windowsSoftwareIds=[],
		depotIds=[],
	)

	productId2 = "test-netboot-1"
	bm.createNetBootProduct(
		productId=productId2,
		name="Some localboot product",
		productVersion="1.0",
		packageVersion="1",
		licenseRequired=0,
		setupScript="",
		uninstallScript="",
		updateScript="",
		alwaysScript="",
		onceScript="",
		priority=0,
		description="",
		advice="",
		pxeConfigTemplate="some_template",
		windowsSoftwareIds=[],
		depotIds=[],
	)

	productIdents = bm.product_getIdents(returnType="tuple")
	assert (productId1, "1.0", "1") in productIdents
	assert (productId2, "1.0", "1") in productIdents

	# TODO: insert assertions
	product = bm.getProduct_hash(productId=productId1, depotId=origDepotserver1.id)
	bm.getProducts_hash()
	bm.getProducts_listOfHashes()
	bm.getProducts_listOfHashes(depotId=origDepotserver1.id)

	for client in origClients:
		allProductIds = bm.getInstalledProductIds_list(objectId=client.id)

		productIds = bm.getInstalledLocalBootProductIds_list(objectId=client.id)
		for product in productIds:
			assert product in allProductIds

		productIds = bm.getInstalledNetBootProductIds_list(objectId=client.id)
		for product in productIds:
			assert product in allProductIds

	productIds = bm.getProvidedLocalBootProductIds_list(depotId=origDepotserver1.id)
	productIds = bm.getProvidedNetBootProductIds_list(depotId=origDepotserver1.id)

	for client in origClients:
		bm.getProductInstallationStatus_hash(
			productId=origProduct1.id, objectId=client.id
		)

	bm.config_createObjects(
		[
			{
				"id": "clientconfig.depot.id",
				"type": "UnicodeConfig",
			}
		]
	)
	bm.configState_create(
		"clientconfig.depot.id", client.id, values=[origDepotserver1.id]
	)

	bm.setProductState(
		productId=origProduct1.id,
		objectId=client.id,
		installationStatus="not_installed",
		actionRequest="setup",
	)
	bm.setProductInstallationStatus(
		productId=origProduct1.id, objectId=client.id, installationStatus="installed"
	)
	bm.setProductActionProgress(
		productId=origProduct1.id,
		hostId=client.id,
		productActionProgress="something 90%",
	)
	bm.setProductActionRequest(
		productId=origProduct1.id, clientId=client.id, actionRequest="uninstall"
	)

	for product in origProducts:
		bm.getPossibleProductActions_list(productId=product.id)

	bm.getPossibleProductActions_hash()
	depotId = bm.getDepotId(clientId=client.id)
	assert depotId == origDepotserver1.id

	clientId = bm.getClientIdByMac(mac=client2.hardwareAddress)
	assert clientId == client2.id

	productIds = bm.getInstallableProductIds_list(clientId=client.id)
	productIds = bm.getInstallableLocalBootProductIds_list(clientId=client.id)
	productIds = bm.getInstallableNetBootProductIds_list(clientId=client.id)
	# TODO: assertions!
	bm.getProductInstallationStatus_listOfHashes(objectId=client.id)
	bm.getProductActionRequests_listOfHashes(clientId=client.id)
	bm.getLocalBootProductStates_hash()


def testGettingBackendManagerWithDefaultConfig():
	requiredPaths = (
		"/etc/opsi/backendManager/dispatch.conf",
		"/etc/opsi/backends",
		"/etc/opsi/backendManager/extend.d",
		"/var/lib/opsi/config/depots",
	)

	for path in requiredPaths:
		if not os.path.exists(path):
			pytest.skip("Missing {0}".format(path))

	backend = BackendManager()
	assert backend.backend_info()


def testGettingBackendManagerWithCustomConfig(tempDir):
	backendsDir = os.path.join(tempDir, "backendsss")
	bmDir = os.path.join(tempDir, "bm")
	dispatchConfig = os.path.join(bmDir, "dispatch.conf")
	extensionDir = os.path.join(bmDir, "extension")

	os.mkdir(bmDir)
	os.mkdir(extensionDir)
	os.mkdir(backendsDir)

	with open(dispatchConfig, "w") as dpconf:
		dpconf.write("""
.* : file
""")

	kwargs = {
		"dispatchConfigFile": dispatchConfig,
		"backendConfigDir": backendsDir,
		"extensionConfigDir": extensionDir,
	}

	with getFileBackend(path=tempDir):
		# We need to make sure there is a file.conf for the backend.
		os.link(
			os.path.join(tempDir, "etc", "opsi", "backends", "file.conf"),
			os.path.join(backendsDir, "file.conf"),
		)

	backend = BackendManager(**kwargs)
	assert backend.backend_info()


def testBackendManagerCanAccessExtensions(backendManager):
	assert backendManager.backend_info()

	# This may be empty but the call must not fail.
	backendManager.getServerIds_list()


def testBackendManagerGettingOptionsReturnsCopy(backendManager):
	options = backendManager.backend_getOptions()
	options["foo"] = True

	newOptions = backendManager.backend_getOptions()
	assert newOptions
	assert "foo" not in newOptions
