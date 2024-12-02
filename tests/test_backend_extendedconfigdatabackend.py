# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing extended backends features
"""

import random

import pytest

from OPSI.Backend.Backend import temporaryBackendOptions
from OPSI.Exceptions import BackendError, BackendMissingDataError
from OPSI.Object import (
	BoolProductProperty,
	ConfigState,
	LocalbootProduct,
	OpsiClient,
	OpsiDepotserver,
	ProductOnClient,
	ProductOnDepot,
	ProductPropertyState,
	UnicodeConfig,
	UnicodeProductProperty,
)
from OPSI.Util.Task.ConfigureBackend.ConfigurationData import initializeConfigs

from .test_backend_replicator import fillBackend
from .test_configs import getConfigs, getConfigStates
from .test_hosts import getClients, getConfigServer, getDepotServers
from .test_products import (
	getLocalbootProducts,
	getNetbootProduct,
	getProductPropertyStates,
	getProductsOnClients,
	getProductsOnDepot,
)

# TODO: provide tests for these backend options:
# extendedConfigDataBackend.backend_setOptions({
# 'addProductPropertyStateDefaults':	 True,
# 'addConfigStateDefaults':			  True,
# 'deleteConfigStateIfDefault':		  True,
# 'returnObjectsOnUpdateAndCreate':	  False
# })


def test_configState_getClientToDepotserver(extendedConfigDataBackend):
	originalClients = getClients()
	depotservers = getDepotServers()
	depot1 = depotservers[0]
	extendedConfigDataBackend.host_createObjects(depotservers)
	extendedConfigDataBackend.host_createObjects(originalClients)

	clientConfigDepotId = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		possibleValues=[],
		defaultValues=[depot1.id],
	)
	extendedConfigDataBackend.config_createObjects(clientConfigDepotId)

	products = list(getLocalbootProducts()) + [getNetbootProduct()]
	extendedConfigDataBackend.product_createObjects(products)
	originalProductsOnDepots = getProductsOnDepot(products, depot1, depotservers)
	extendedConfigDataBackend.productOnDepot_createObjects(originalProductsOnDepots)

	clients = extendedConfigDataBackend.host_getObjects(type="OpsiClient")
	with temporaryBackendOptions(
		extendedConfigDataBackend, addConfigStateDefaults=True
	):
		clientToDepots = extendedConfigDataBackend.configState_getClientToDepotserver()

	assert len(clientToDepots) == len(clients)

	for depotserver in getDepotServers():
		productOnDepots = extendedConfigDataBackend.productOnDepot_getObjects(
			depotId=depotserver.id
		)
		expectedProducts = [
			x for x in originalProductsOnDepots if x.depotId == depotserver.id
		]
		for productOnDepot in productOnDepots:
			assert productOnDepot in expectedProducts

	depotServerIDs = set(ds.id for ds in depotservers)

	for clientToDepot in clientToDepots:
		assert clientToDepot["depotId"] in depotServerIDs


def test_createProductOnClient(extendedConfigDataBackend):
	client = OpsiClient(id="client.test.invalid")
	extendedConfigDataBackend.host_createObjects(client)

	originalPoc = ProductOnClient(
		productId="product6",
		productType="LocalbootProduct",
		clientId=client.id,
		installationStatus="not_installed",
		actionRequest="setup",
	)
	extendedConfigDataBackend.productOnClient_createObjects(originalPoc)

	productOnClients = [
		poc
		for poc in extendedConfigDataBackend.productOnClient_getObjects(
			clientId=client.id
		)
		if poc.actionRequest == "setup"
	]

	assert [originalPoc] == productOnClients


def test_selectProductOnClientWithDefault(extendedConfigDataBackend):
	client = OpsiClient(id="client.test.invalid")
	depot = OpsiDepotserver(id="depotserver1.test.invalid")
	extendedConfigDataBackend.host_createObjects([client, depot])

	poc = ProductOnClient(
		productId="product6",
		productType="LocalbootProduct",
		clientId=client.id,
		installationStatus="not_installed",
		actionRequest="setup",
	)
	extendedConfigDataBackend.productOnClient_createObjects(poc)

	prod6 = LocalbootProduct(
		id="product6",
		productVersion="1.0",
		packageVersion=1,
	)
	prod7 = LocalbootProduct(
		id="product7",
		name="Product 7",
		productVersion="1.0",
		packageVersion=1,
	)
	extendedConfigDataBackend.product_createObjects([prod6, prod7])

	installedProductOnDepot6 = ProductOnDepot(
		productId=prod6.id,
		productType=prod6.getType(),
		productVersion=prod6.productVersion,
		packageVersion=prod6.packageVersion,
		depotId=depot.getId(),
		locked=False,
	)
	installedProductOnDepot7 = ProductOnDepot(
		productId=prod7.id,
		productType=prod7.getType(),
		productVersion=prod7.productVersion,
		packageVersion=prod7.packageVersion,
		depotId=depot.getId(),
		locked=False,
	)
	extendedConfigDataBackend.productOnDepot_createObjects(
		[installedProductOnDepot6, installedProductOnDepot7]
	)

	clientConfigDepotId = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		possibleValues=[],
		defaultValues=[depot.id],
	)
	extendedConfigDataBackend.config_createObjects(clientConfigDepotId)

	with temporaryBackendOptions(
		extendedConfigDataBackend, addProductOnClientDefaults=True
	):
		productOnClients = [
			pocc.productId
			for pocc in extendedConfigDataBackend.productOnClient_getObjects(
				clientId=client.id, productId=["product6", "product7"]
			)
		]

	productOnClients.sort()
	assert productOnClients == ["product6", "product7"]


def test_backend_option_addProductOnClientDefaults(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	clients = getClients()
	backend.host_createObjects(clients)
	client = random.choice(clients)

	configServer = getConfigServer()
	backend.host_createObjects(configServer)

	depots = getDepotServers()
	backend.host_createObjects(depots)
	depot = random.choice(depots)

	products = list(getLocalbootProducts()) + [getNetbootProduct()]
	backend.product_createObjects(products)

	pods = getProductsOnDepot(products, configServer, depots)
	backend.productOnDepot_createObjects(pods)

	pocs = getProductsOnClients(products, clients)
	backend.productOnClient_createObjects(pocs)

	podsOnDepot = backend.productOnDepot_getObjects(depotId=depot.id)
	assert 0 < len(podsOnDepot)

	pocsOnClient = backend.productOnClient_getObjects(clientId=client.id)
	assert len(pocsOnClient) < len(products)
	assert len(podsOnDepot) > len(pocsOnClient)

	productsOnClientNotOnDepot = set(p.productId for p in pocsOnClient) - set(
		p.productId for p in podsOnDepot
	)

	clientConfigDepotId = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		defaultValues=[configServer.id],
	)
	backend.config_createObjects(clientConfigDepotId)

	clientDepotAssignment = ConfigState(
		configId=clientConfigDepotId.id, objectId=client.id, values=[depot.id]
	)
	backend.configState_createObjects(clientDepotAssignment)

	with temporaryBackendOptions(backend, addProductOnClientDefaults=True):
		productOnClients = [
			pocc.productId
			for pocc in backend.productOnClient_getObjects(clientId=client.id)
		]

	assert len(pocsOnClient) < len(productOnClients)
	assert len(productOnClients) - len(productsOnClientNotOnDepot) == len(podsOnDepot)


def test_selectProductOnClientsByWildcard(extendedConfigDataBackend):
	client = OpsiClient(id="client.test.invalid")
	extendedConfigDataBackend.host_createObjects(client)

	poc = ProductOnClient(
		productId="product6",
		productType="LocalbootProduct",
		clientId=client.id,
		installationStatus="not_installed",
		actionRequest="setup",
	)
	extendedConfigDataBackend.productOnClient_createObjects(poc)

	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		clientId=client.id, productId="*6*"
	)
	assert productOnClients == [poc]


def testHost_createDepotServer(extendedConfigDataBackend):
	extendedConfigDataBackend.host_createOpsiDepotserver(
		id="depot100.test.invalid",
		opsiHostKey="123456789012345678901234567890aa",
		depotLocalUrl="file:///opt/pcbin/install",
		depotRemoteUrl="smb://depot3.uib.local/opt_pcbin/install",
		repositoryLocalUrl="file:///var/lib/opsi/products",
		repositoryRemoteUrl="webdavs://depot3.uib.local:4447/products",
		description="A depot",
		notes="Depot 100",
		hardwareAddress=None,
		ipAddress=None,
		networkAddress="192.168.100.0/24",
		maxBandwidth=0,
	)

	hosts = extendedConfigDataBackend.host_getObjects(id="depot100.test.invalid")
	assert len(hosts) == 1

	depot = hosts[0]
	assert depot.id == "depot100.test.invalid"
	assert depot.opsiHostKey == "123456789012345678901234567890aa"
	assert depot.depotLocalUrl == "file:///opt/pcbin/install"
	assert depot.depotRemoteUrl == "smb://depot3.uib.local/opt_pcbin/install"
	assert depot.repositoryLocalUrl == "file:///var/lib/opsi/products"
	assert depot.repositoryRemoteUrl == "webdavs://depot3.uib.local:4447/products"
	assert depot.description == "A depot"
	assert depot.notes == "Depot 100"
	assert depot.hardwareAddress is None
	assert depot.ipAddress is None
	assert depot.networkAddress == "192.168.100.0/24"
	assert depot.maxBandwidth == 0


@pytest.mark.parametrize("lastSeen", [None, "2020-01-01 01:01:01"])
def testHost_createClient(extendedConfigDataBackend, lastSeen):
	extendedConfigDataBackend.host_createOpsiClient(
		id="client100.test.invalid",
		opsiHostKey=None,
		description="Client 100",
		notes="No notes",
		hardwareAddress="00:00:01:01:02:02",
		ipAddress="192.168.0.200",
		created=None,
		lastSeen=lastSeen,
	)

	hosts = extendedConfigDataBackend.host_getObjects(id="client100.test.invalid")
	assert len(hosts) == 1

	client = hosts[0]
	assert client.id == "client100.test.invalid"
	assert client.description == "Client 100"
	assert client.notes == "No notes"
	assert client.hardwareAddress == "00:00:01:01:02:02"
	assert client.ipAddress == "192.168.0.200"

	# Automatically filled atttributes
	assert client.opsiHostKey
	assert client.created
	assert client.lastSeen

	if lastSeen:
		assert client.lastSeen == lastSeen


def testConfigState_getIdents(extendedConfigDataBackend):
	extendedConfigDataBackend.host_createOpsiDepotserver(
		id="depot100.test.invalid",
		opsiHostKey="123456789012345678901234567890aa",
		depotLocalUrl="file:///opt/pcbin/install",
		depotRemoteUrl="smb://depot3.uib.local/opt_pcbin/install",
		repositoryLocalUrl="file:///var/lib/opsi/products",
		repositoryRemoteUrl="webdavs://depot3.uib.local:4447/products",
		description="A depot",
		notes="Depot 100",
		hardwareAddress=None,
		ipAddress=None,
		networkAddress="192.168.100.0/24",
		maxBandwidth=0,
	)
	extendedConfigDataBackend.host_createOpsiClient(
		id="client100.test.invalid",
		opsiHostKey=None,
		description="Client 100",
		notes="No notes",
		hardwareAddress="00:00:01:01:02:02",
		ipAddress="192.168.0.200",
		created=None,
		lastSeen=None,
	)
	clients = getClients()
	extendedConfigDataBackend.host_createObjects(clients)

	configs = getConfigs()
	extendedConfigDataBackend.config_createObjects(configs)

	depotServer = extendedConfigDataBackend.host_getObjects(id="depot100.test.invalid")[
		0
	]
	configStates = getConfigStates(configs, clients, [None, depotServer])
	extendedConfigDataBackend.configState_createObjects(configStates)
	expectedIdents = [
		configState.getIdent(returnType="dict") for configState in configStates
	]

	with temporaryBackendOptions(
		extendedConfigDataBackend, addConfigStateDefaults=False
	):
		ids = extendedConfigDataBackend.configState_getIdents()

	assert len(ids) == len(expectedIdents)
	for ident in ids:
		objectIdent = dict(zip(("configId", "objectId"), tuple(ident.split(";"))))
		assert objectIdent in expectedIdents

	expect = len(extendedConfigDataBackend.host_getObjects()) * len(configs)
	with temporaryBackendOptions(
		extendedConfigDataBackend, addConfigStateDefaults=True
	):
		ids = extendedConfigDataBackend.configState_getIdents()
	assert expect == len(ids)


@pytest.mark.parametrize(
	"returnType, klass",
	((None, object), ("tuple", tuple), ("list", list), ("dict", dict)),
)
@pytest.mark.parametrize(
	"objectType",
	(
		"config",
		"host",
		"group",
		"objectToGroup",
		"product",
		"productProperty",
		"productOnDepot",
		"productPropertyState",
	),
)
def testGettingIdentsDoesNotRaiseAnException(
	extendedConfigDataBackend, objectType, returnType, klass
):
	fillBackend(extendedConfigDataBackend)

	methodOptions = {}
	if returnType is not None:
		methodOptions["returnType"] = returnType

	getObjects = getattr(extendedConfigDataBackend, objectType + "_getObjects")
	objectCount = len(getObjects())

	methodName = objectType + "_getIdents"
	method = getattr(extendedConfigDataBackend, methodName)

	result = method(**methodOptions)
	assert result
	assert objectCount == len(result)

	for obj in result:
		assert isinstance(obj, klass)


def testGetIdentsWithWildcardFilter(extendedConfigDataBackend):
	extendedConfigDataBackend.host_createOpsiDepotserver(id="depot100.test.invalid")
	extendedConfigDataBackend.host_createOpsiClient(id="client100.test.invalid")
	clients = getClients()
	extendedConfigDataBackend.host_createObjects(clients)

	ids = extendedConfigDataBackend.host_getIdents(id="*100*")
	assert 2 == len(ids)
	assert "depot100.test.invalid" in ids
	assert "client100.test.invalid" in ids


@pytest.mark.parametrize(
	"methodSignature",
	(
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "backend_getLicensingInfo",
			"args": ["self", "licenses", "legacy_modules", "dates", "allow_cache"],
			"params": ["*licenses", "*legacy_modules", "*dates", "*allow_cache"],
			"defaults": (False, False, False, True),
			"varargs": None,
			"keywords": None,
			"annotations": {
				"allow_cache": "bool",
				"dates": "bool",
				"legacy_modules": "bool",
				"licenses": "bool",
			},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "backend_getInterface",
			"args": ["self"],
			"params": [],
			"defaults": None,
			"varargs": None,
			"keywords": None,
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "backend_getOptions",
			"args": ["self"],
			"params": [],
			"defaults": None,
			"varargs": None,
			"keywords": None,
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "backend_info",
			"args": ["self"],
			"params": [],
			"defaults": None,
			"varargs": None,
			"keywords": None,
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "configState_getObjects",
			"args": ["self", "attributes"],
			"params": ["*attributes", "**filter"],
			"defaults": ([],),
			"varargs": None,
			"keywords": "filter",
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "config_getIdents",
			"args": ["self", "returnType"],
			"params": ["*returnType", "**filter"],
			"defaults": ("unicode",),
			"varargs": None,
			"keywords": "filter",
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "host_getObjects",
			"args": ["self", "attributes"],
			"params": ["*attributes", "**filter"],
			"defaults": (None,),
			"varargs": None,
			"keywords": "filter",
			"annotations": {"attributes": "list[str]"},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "productOnClient_getObjects",
			"args": ["self", "attributes"],
			"params": ["*attributes", "**filter"],
			"defaults": ([],),
			"varargs": None,
			"keywords": "filter",
			"annotations": {},
		},
		{
			"deprecated": False,
			"alternative_method": None,
			"name": "productPropertyState_getObjects",
			"args": ["self", "attributes"],
			"params": ["*attributes", "**filter"],
			"defaults": ([],),
			"varargs": None,
			"keywords": "filter",
			"annotations": {},
		},
	),
)
def testBackend_getInterface(extendedConfigDataBackend, methodSignature):
	"""
	Testing the behaviour of backend_getInterface.

	The method descriptions in `expected` may vary and should be
	reduced if problems because of missing methods occur.
	"""
	print("Base backend {0!r}".format(extendedConfigDataBackend))
	try:
		print(
			"Checking with backend {0!r}".format(
				extendedConfigDataBackend._backend._backend
			)
		)
	except AttributeError:
		try:
			print(
				"Checking with backend {0!r}".format(extendedConfigDataBackend._backend)
			)
		except AttributeError:
			pass

	for result in extendedConfigDataBackend.backend_getInterface():
		if result["name"] == methodSignature["name"]:
			assert "doc" in result
			del result["doc"]
			assert result == methodSignature
			break
	else:
		pytest.fail("Expected method {0!r} not found".format(methodSignature["name"]))


@pytest.mark.parametrize("addressType", ["fqdn"])
def testRenamingDepotServer(
	extendedConfigDataBackend, addressType, newId="hello.world.test"
):
	backend = extendedConfigDataBackend
	configServer = getConfigServer()

	backend.host_createObjects(configServer)
	initializeConfigs(backend)

	# TODO: add test variant that uses the hostname or IP in the addresses
	# TODO: relevant for #3034?
	if addressType != "fqdn":
		raise RuntimeError("Unsupported address type")
	address = "toberenamed.domain.test"

	depots = list(getDepotServers())
	oldServer = OpsiDepotserver(
		id="toberenamed.domain.test",
		depotLocalUrl="file:///var/lib/opsi/depot",
		depotRemoteUrl="smb://{address}/opsi_depot".format(address=address),
		depotWebdavUrl="webdavs://{address}:4447/depot".format(address=address),
		repositoryLocalUrl="file:///var/lib/opsi/repository",
		repositoryRemoteUrl="webdavs://{address}:4447/repository".format(
			address=address
		),
		workbenchLocalUrl="file:///var/lib/opsi/workbench",
		workbenchRemoteUrl="smb://{address}/opsi_workbench".format(address=address),
	)
	depots.append(oldServer)
	backend.host_createObjects(depots)

	products = list(getLocalbootProducts()) + [getNetbootProduct()]
	backend.product_createObjects(products)
	originalProductsOnDepots = getProductsOnDepot(products, oldServer, depots)
	backend.productOnDepot_createObjects(originalProductsOnDepots)
	productsOnOldDepot = backend.productOnDepot_getObjects(depotId=oldServer.id)

	product1 = products[0]
	specialProperty = UnicodeProductProperty(
		productId=product1.id,
		productVersion=product1.productVersion,
		packageVersion=product1.packageVersion,
		propertyId="changeMe",
		possibleValues=["foo", oldServer.id, "baz"],
		defaultValues=["foo", oldServer.id],
		editable=False,
		multiValue=True,
	)
	properties = [
		UnicodeProductProperty(
			productId=product1.id,
			productVersion=product1.productVersion,
			packageVersion=product1.packageVersion,
			propertyId="overridden",
			possibleValues=["foo", "bar", "baz"],
			defaultValues=["foo"],
			editable=True,
			multiValue=True,
		),
		BoolProductProperty(
			productId=product1.id,
			productVersion=product1.productVersion,
			packageVersion=product1.packageVersion,
			propertyId="irrelevant2",
			defaultValues=True,
		),
		specialProperty,
	]
	backend.productProperty_createObjects(properties)
	oldProperties = backend.productProperty_getObjects()

	specialProdPropertyState = ProductPropertyState(
		productId=product1.id,
		propertyId=properties[0].propertyId,
		objectId=oldServer.id,
		values=[oldServer.id],
	)
	productPropertyStates = list(getProductPropertyStates(properties, depots, depots))
	productPropertyStates.append(specialProdPropertyState)
	backend.productPropertyState_createObjects(productPropertyStates)
	oldProductPropertyStates = backend.productPropertyState_getObjects()

	testConfig = UnicodeConfig(
		id="test.config.rename",
		description="Testing value rename",
		possibleValues=["random value", oldServer.id, "another value"],
		defaultValues=[oldServer.id],
		editable=True,
		multiValue=False,
	)
	configs = list(getConfigs())
	configs.append(testConfig)
	configs.append(
		UnicodeConfig(
			id="clientconfig.depot.id",  # get's special treatment
			description="ID of the opsi depot to use",
			possibleValues=[configServer.id, oldServer.id],
			defaultValues=[oldServer.id],
			editable=True,
			multiValue=False,
		)
	)
	configs.append(
		UnicodeConfig(
			id="clientconfig.configserver.url",  # get's special treatment
			description="URL(s) of opsi config service(s) to use",
			possibleValues=[
				"https://%s:4447/rpc" % server
				for server in (configServer.id, oldServer.id)
			],
			defaultValues=["https://%s:4447/rpc" % configServer.id],
			editable=True,
			multiValue=True,
		)
	)
	backend.config_createObjects(configs)
	oldConfigs = backend.config_getObjects()

	testConfigState = ConfigState(
		configId=testConfig.id,
		objectId=oldServer.id,
		values=["broken glass", oldServer.id, "red"],
	)
	manyDepots = depots * 4
	configStates = list(getConfigStates(configs, manyDepots[:7], [None, oldServer]))
	configStates.append(testConfigState)
	backend.configState_createObjects(configStates)
	oldConfigStates = backend.configState_getObjects()
	configStatesFromDifferentObjects = [
		cs for cs in oldConfigStates if not cs.objectId == oldServer.id
	]

	secondaryDepot = OpsiDepotserver(
		id="sub-{0}".format(oldServer.id),
		isMasterDepot=False,
		masterDepotId=oldServer.id,
	)
	backend.host_createObjects(secondaryDepot)

	backend.host_renameOpsiDepotserver(oldServer.id, newId)

	assert not backend.host_getObjects(id=oldServer.id)

	newServer = backend.host_getObjects(id=newId)[0]
	assert newServer.id == newId
	assert newServer.getType() == "OpsiDepotserver"
	assert newServer.depotLocalUrl == "file:///var/lib/opsi/depot"
	assert newServer.repositoryLocalUrl == "file:///var/lib/opsi/repository"
	assert newServer.workbenchLocalUrl == "file:///var/lib/opsi/workbench"
	assert newServer.depotRemoteUrl == "smb://%s/opsi_depot" % newId
	assert newServer.depotWebdavUrl == "webdavs://%s:4447/depot" % newId
	assert newServer.repositoryRemoteUrl == "webdavs://%s:4447/repository" % newId
	assert newServer.workbenchRemoteUrl == "smb://{}/opsi_workbench".format(newId)

	assert not backend.productOnDepot_getObjects(depotId=oldServer.id)
	productsOnNewDepot = backend.productOnDepot_getObjects(depotId=newId)
	assert len(productsOnOldDepot) == len(productsOnNewDepot)

	newProperties = backend.productProperty_getObjects()
	assert len(newProperties) == len(oldProperties)
	specialPropertyChecked = False
	for productProperty in newProperties:
		if productProperty.propertyId == specialProperty.propertyId:
			assert oldServer.id not in productProperty.possibleValues
			assert newId in productProperty.possibleValues

			assert oldServer.id not in productProperty.defaultValues
			assert newId in productProperty.defaultValues
			specialPropertyChecked = True

	assert specialPropertyChecked, "Missing property {0}".format(
		specialProperty.propertyId
	)

	newProductPropertyStates = backend.productPropertyState_getObjects()
	assert len(oldProductPropertyStates) == len(newProductPropertyStates)
	assert not any(pps.objectId == oldServer.id for pps in newProductPropertyStates)
	assert not any(oldServer.id in pps.values for pps in newProductPropertyStates)

	newConfigs = backend.config_getObjects()
	assert len(oldConfigs) == len(newConfigs)
	configsTested = 0
	for config in newConfigs:
		assert oldServer.id not in config.possibleValues
		assert oldServer.id not in config.defaultValues

		if config.id == testConfig.id:
			assert newId in config.possibleValues
			assert newId in config.defaultValues
			assert len(testConfig.possibleValues) == len(config.possibleValues)
			assert len(testConfig.defaultValues) == len(config.defaultValues)
			configsTested += 1
		elif config.id == "clientconfig.configserver.url":
			assert 1 == len(config.defaultValues)
			assert newId not in config.defaultValues[0]  # Default is config server
			assert 2 == len(config.possibleValues)

			# TODO: this could be relevant for #1571
			if addressType == "fqdn":
				assert any(newId in value for value in config.possibleValues)
			else:
				raise RuntimeError(
					"Missing check for address type {0!r}".format(addressType)
				)
			configsTested += 1
		elif config.id == "clientconfig.depot.id":
			assert newId in config.possibleValues
			assert oldServer.id not in config.possibleValues
			assert 2 == len(config.possibleValues)
			assert [newId] == config.defaultValues
			configsTested += 1

	assert 3 == configsTested

	newConfigStates = backend.configState_getObjects()
	assert len(oldConfigStates) == len(newConfigStates)
	newConfigStatesFromDifferentObjects = [
		cs for cs in newConfigStates if not cs.objectId == newId
	]
	assert len(configStatesFromDifferentObjects) == len(
		newConfigStatesFromDifferentObjects
	)

	configStateTested = False
	for configState in newConfigStates:
		assert oldServer.id not in configState.values
		assert configState.objectId != oldServer.id

		if configState.configId == testConfigState.configId:
			assert configState.objectId == newId
			configStateTested = True

	assert configStateTested, "Reference to ID not changed"

	newSecondaryDepot = backend.host_getObjects(id=secondaryDepot.id)[0]
	assert newSecondaryDepot.isMasterDepot is False
	assert newSecondaryDepot.masterDepotId == newId


def testRenamingDepotServerFailsIfOldServerMissing(
	extendedConfigDataBackend, newId="hello.world.test"
):
	with pytest.raises(BackendMissingDataError):
		extendedConfigDataBackend.host_renameOpsiDepotserver(
			"not.here.invalid", "foo.bar.baz"
		)


def testRenamingDepotServerFailsIfNewIdAlreadyExisting(
	extendedConfigDataBackend, newId="hello.world.test"
):
	backend = extendedConfigDataBackend
	depots = getDepotServers()
	backend.host_createObjects(depots)

	assert len(depots) >= 2, "Requiring at least two depots for this test."
	oldServer = random.choice(depots)
	newServer = random.choice(depots)
	while newServer == oldServer:
		newServer = random.choice(depots)

	with pytest.raises(BackendError):
		backend.host_renameOpsiDepotserver(oldServer.id, newServer.id)
