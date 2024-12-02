# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for the dynamically loaded legacy extensions.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/20_legacy.conf``.

The legacy extensions are to maintain backwards compatibility for scripts
that were written for opsi 3.
"""

import pytest

from OPSI.Object import (
	BoolProductProperty,
	LocalbootProduct,
	OpsiClient,
	OpsiDepotserver,
	ProductDependency,
	ProductOnDepot,
	ProductPropertyState,
	UnicodeProductProperty,
)
from OPSI.Exceptions import BackendMissingDataError
from .test_hosts import getClients, getConfigServer, getDepotServers


def testGetGeneralConfigValueFailsWithInvalidObjectId(backendManager):
	with pytest.raises(ValueError):
		backendManager.getGeneralConfig_hash("foo")


def testGetGeneralConfig(backendManager):
	"""
	Calling the function with some valid FQDN must not fail.
	"""
	values = backendManager.getGeneralConfig_hash("some.client.fqdn")
	assert not values


def testGetDomainShouldWork(backendManager):
	assert backendManager.getDomain()


@pytest.mark.parametrize("value", [None, ""])
def testGetGeneralConfigValueWithoutConfigReturnsNoValue(backendManager, value):
	assert backendManager.getGeneralConfigValue(value) is None


def testGetGeneralConfigIsEmptyAfterStart(backendManager):
	assert {} == backendManager.getGeneralConfig_hash()


def generateLargeConfig(numberOfConfigs):
	numberOfConfigs = 50  # len(config) will be double

	config = {}
	for value in range(numberOfConfigs):
		config["bool.{0}".format(value)] = str(value % 2 == 0)
		config["normal.{0}".format(value)] = "norm-{0}".format(value)

	assert numberOfConfigs * 2 == len(config)

	return config


def testDeleteProductDependency(backendManager):
	firstProduct = LocalbootProduct("prod", "1.0", "1.0")
	secondProduct = LocalbootProduct("dependency", "1.0", "1.0")
	backendManager.product_insertObject(firstProduct)
	backendManager.product_insertObject(secondProduct)

	prodDependency = ProductDependency(
		productId=firstProduct.id,
		productVersion=firstProduct.productVersion,
		packageVersion=firstProduct.packageVersion,
		productAction="setup",
		requiredProductId=secondProduct.id,
		requiredAction="setup",
		requirementType="after",
	)
	backendManager.productDependency_insertObject(prodDependency)

	depots = getDepotServers()
	depot = depots[0]
	backendManager.host_insertObject(depot)

	productOnDepot = ProductOnDepot(
		productId=firstProduct.getId(),
		productType=firstProduct.getType(),
		productVersion=firstProduct.getProductVersion(),
		packageVersion=firstProduct.getPackageVersion(),
		depotId=depot.id,
		locked=False,
	)
	backendManager.productOnDepot_createObjects([productOnDepot])

	assert backendManager.productDependency_getObjects()

	backendManager.deleteProductDependency(
		firstProduct.id,
		"",
		secondProduct.id,
		requiredProductClassId="unusedParam",
		requirementType="unused",
	)

	assert not backendManager.productDependency_getObjects()


@pytest.mark.parametrize("createDepotState", [True, False])
def testSetProductPropertyWithoutSideEffects(backendManager, createDepotState):
	product = LocalbootProduct("aboabo", "1.0", "2")
	backendManager.product_insertObject(product)

	testprop = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="changeMe",
		possibleValues=["True", "NO NO NO"],
		defaultValues=["NOT YOUR IMAGE"],
		editable=True,
		multiValue=False,
	)
	untouchable = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="ucanttouchthis",
		possibleValues=["Chocolate", "Starfish"],
		defaultValues=["Chocolate"],
		editable=True,
		multiValue=False,
	)
	backendManager.productProperty_insertObject(testprop)
	backendManager.productProperty_insertObject(untouchable)

	configserver = getConfigServer()
	depot = OpsiDepotserver("biscuit.some.test")
	backendManager.host_insertObject(configserver)
	backendManager.host_insertObject(depot)

	expectedStates = 0
	if createDepotState:
		depotProdState = ProductPropertyState(
			productId=product.id,
			propertyId=testprop.propertyId,
			objectId=depot.id,
			values=testprop.getDefaultValues(),
		)
		backendManager.productPropertyState_insertObject(depotProdState)
		expectedStates += 1

	backendManager.setProductProperty(product.id, testprop.propertyId, "Starfish")

	results = backendManager.productProperty_getObjects()
	assert len(results) == 2

	for result in results:
		print("Checking {0!r}".format(result))
		assert isinstance(result, UnicodeProductProperty)

		if result.propertyId == untouchable.propertyId:
			assert result.getDefaultValues() == untouchable.getDefaultValues()
			assert result.getPossibleValues() == untouchable.getPossibleValues()
		elif result.propertyId == testprop.propertyId:
			assert result.getDefaultValues() == testprop.getDefaultValues()
			assert result.getPossibleValues() == testprop.getPossibleValues()
		else:
			raise ValueError("Unexpected property: {0!r}".format(result))

	states = backendManager.productPropertyState_getObjects()
	assert len(states) == expectedStates

	if createDepotState:
		pps = states.pop()
		assert pps.productId == product.id
		assert pps.propertyId == testprop.propertyId
		assert pps.objectId == depot.id
		assert pps.values == ["Starfish"]


@pytest.mark.parametrize(
	"productExists", [True, False], ids=["product exists", "product missing"]
)
@pytest.mark.parametrize(
	"propertyExists", [True, False], ids=["property exists", "property missing"]
)
@pytest.mark.parametrize(
	"clientExists", [True, False], ids=["client exists", "client missing"]
)
def testSetProductPropertyHandlingMissingObjects(
	backendManager, productExists, propertyExists, clientExists
):
	expectedProperties = 0
	productId = "existence"

	if productExists:
		product = LocalbootProduct(productId, "1.0", "1")
		backendManager.product_insertObject(product)

		if propertyExists:
			testprop = UnicodeProductProperty(
				productId=product.id,
				productVersion=product.productVersion,
				packageVersion=product.packageVersion,
				propertyId="changer",
				possibleValues=["True", "False"],
				defaultValues=["False"],
				editable=True,
				multiValue=False,
			)
			backendManager.productProperty_insertObject(testprop)

			expectedProperties += 1

	with pytest.raises(BackendMissingDataError):
		backendManager.setProductProperty(productId, "nothere", False)

	assert len(backendManager.productProperty_getObjects()) == expectedProperties

	if clientExists:
		client = OpsiClient("testclient.domain.invalid")
		backendManager.host_insertObject(client)

	with pytest.raises(BackendMissingDataError):
		backendManager.setProductProperty(
			productId, "nothere", False, "testclient.domain.invalid"
		)

	assert len(backendManager.productProperty_getObjects()) == expectedProperties


def testSetProductPropertyHandlingBoolProductProperties(backendManager):
	product = LocalbootProduct("testproduct", "1.0", "2")
	backendManager.product_insertObject(product)

	testprop = BoolProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="changeMe",
		defaultValues=[False],
	)
	backendManager.productProperty_insertObject(testprop)

	client = OpsiClient("testclient.domain.invalid")
	backendManager.host_insertObject(client)

	backendManager.setProductProperty(product.id, testprop.propertyId, True, client.id)

	result = backendManager.productProperty_getObjects(propertyId=testprop.propertyId)
	assert len(result) == 1
	result = result[0]
	assert isinstance(result, BoolProductProperty)
	assert result.getPossibleValues() == [False, True]
	assert result.getDefaultValues() == [False]

	result = backendManager.productPropertyState_getObjects()
	assert len(result) == 1
	result = result[0]
	assert result.getObjectId() == client.id
	assert result.getValues() == [True]


def testSetProductPropertyNotConcatenatingStrings(backendManager):
	product = LocalbootProduct("testproduct", "1.0", "2")
	backendManager.product_insertObject(product)

	testprop = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="rebootflag",
		possibleValues=["0", "1", "2", "3"],
		defaultValues=["0"],
		editable=False,
		multiValue=False,
	)
	donotchange = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="upgradeproducts",
		possibleValues=["firefox", "opsi-vhd-control", "winscp"],
		defaultValues=["firefox", "opsi-vhd-control", "winscp"],
		editable=True,
		multiValue=True,
	)

	backendManager.productProperty_insertObject(testprop)
	backendManager.productProperty_insertObject(donotchange)

	client = OpsiClient("testclient.domain.invalid")
	backendManager.host_insertObject(client)

	sideeffectPropState = ProductPropertyState(
		productId=product.id,
		propertyId=donotchange.propertyId,
		objectId=client.id,
		values=donotchange.getDefaultValues(),
	)
	backendManager.productPropertyState_insertObject(sideeffectPropState)

	backendManager.setProductProperty(product.id, testprop.propertyId, "1", client.id)

	result = backendManager.productProperty_getObjects(
		propertyId=donotchange.propertyId
	)
	assert len(result) == 1
	result = result[0]
	assert isinstance(result, UnicodeProductProperty)
	assert result.getPossibleValues() == ["firefox", "opsi-vhd-control", "winscp"]
	assert result.getDefaultValues() == ["firefox", "opsi-vhd-control", "winscp"]

	result = backendManager.productProperty_getObjects(propertyId=testprop.propertyId)
	assert len(result) == 1
	result = result[0]
	assert isinstance(result, UnicodeProductProperty)
	assert result.getPossibleValues() == ["0", "1", "2", "3"]
	assert result.getDefaultValues() == ["0"]

	results = backendManager.productPropertyState_getObjects()
	assert len(results) == 2

	for result in results:
		assert result.getObjectId() == client.id
		print("Checking {0!r}".format(result))

		if result.propertyId == donotchange.propertyId:
			assert result.getValues() == donotchange.getPossibleValues()
		elif result.propertyId == testprop.propertyId:
			assert result.getValues() == ["1"]
		else:
			raise ValueError("Unexpected property state: {0!r}".format(result))


def testSetProductPropertyFailingIfMultivalueIsFalse(backendManager):
	product = LocalbootProduct("testproduct", "1.0", "2")
	backendManager.product_insertObject(product)

	testprop = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="rebootflag",
		possibleValues=["0", "1", "2", "3"],
		defaultValues=["0"],
		editable=False,
		multiValue=False,
	)
	backendManager.productProperty_insertObject(testprop)

	client = OpsiClient("testclient.domain.invalid")
	backendManager.host_insertObject(client)

	with pytest.raises(ValueError):
		backendManager.setProductProperty(
			product.id, testprop.propertyId, ["1", "2"], client.id
		)


def testGetDepotId(backendManager):
	clients = getClients()
	configServer = getConfigServer()
	depots = getDepotServers()

	backendManager.host_createObjects(clients)
	backendManager.host_createObjects(depots)
	backendManager.host_createObjects(configServer)

	backendManager.config_createObjects(
		[
			{
				"id": "clientconfig.depot.id",
				"type": "UnicodeConfig",
				"values": [configServer.id],
			}
		]
	)

	client = clients[0]
	depotId = depots[0].id
	backendManager.configState_create(
		"clientconfig.depot.id", client.id, values=depotId
	)

	assert depotId == backendManager.getDepotId(clientId=client.id)


def testSetProductPropertiesWithMultipleValues(backendManager):
	product = LocalbootProduct("testproduct", "1.0", "2")
	backendManager.product_insertObject(product)

	testprop = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="rebootflag",
		possibleValues=["0", "1", "2", "3"],
		defaultValues=["0"],
		editable=False,
		multiValue=True,
	)
	donotchange = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="upgradeproducts",
		possibleValues=["firefox", "opsi-vhd-control", "winscp"],
		defaultValues=["firefox", "opsi-vhd-control", "winscp"],
		editable=True,
		multiValue=True,
	)

	backendManager.productProperty_insertObject(testprop)
	backendManager.productProperty_insertObject(donotchange)

	client = OpsiClient("testclient.domain.invalid")
	backendManager.host_insertObject(client)

	depotIds = set()
	for depot in getDepotServers():
		depotIds.add(depot.id)
		backendManager.host_insertObject(depot)

	for depotId in depotIds:
		backendManager.setProductProperties(
			product.id, {testprop.propertyId: ["1", "2"]}, depotId
		)

	result = backendManager.productProperty_getObjects(
		propertyId=donotchange.propertyId
	)
	assert len(result) == 1
	result = result[0]
	assert isinstance(result, UnicodeProductProperty)
	assert result.getPossibleValues() == ["firefox", "opsi-vhd-control", "winscp"]
	assert result.getDefaultValues() == ["firefox", "opsi-vhd-control", "winscp"]

	result = backendManager.productProperty_getObjects(propertyId=testprop.propertyId)
	assert len(result) == 1
	result = result[0]
	assert isinstance(result, UnicodeProductProperty)
	assert result.getPossibleValues() == ["0", "1", "2", "3"]
	assert result.getDefaultValues() == ["0"]

	results = backendManager.productPropertyState_getObjects()
	assert len(results) == len(depotIds)

	for result in results:
		assert result.getObjectId() in depotIds
		print("Checking {0!r}".format(result))

		if result.propertyId == donotchange.propertyId:
			assert result.getValues() == donotchange.getPossibleValues()
		elif result.propertyId == testprop.propertyId:
			assert result.getValues() == ["1", "2"]
		else:
			raise ValueError("Unexpected property state: {0!r}".format(result))
