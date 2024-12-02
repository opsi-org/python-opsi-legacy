# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for the kiosk client method.
"""

import pytest

from OPSI.Object import (
	LocalbootProduct,
	ObjectToGroup,
	OpsiClient,
	OpsiDepotserver,
	ProductGroup,
	ProductOnDepot,
	ProductDependency,
	UnicodeConfig,
)
from OPSI.Exceptions import BackendMissingDataError


def testGettingInfoForNonExistingClient(backendManager):
	with pytest.raises(BackendMissingDataError):
		backendManager.getKioskProductInfosForClient("foo.bar.baz")


# TODO: set custom configState for the client with different products in group.
def testGettingEmptyInfo(backendManager, client, depot):
	backendManager.host_createObjects([client, depot])

	basicConfigs = [
		UnicodeConfig(
			id="software-on-demand.product-group-ids",
			defaultValues=["software-on-demand"],
			multiValue=True,
		),
		UnicodeConfig(
			id="clientconfig.depot.id",
			description="Depotserver to use",
			possibleValues=[],
			defaultValues=[depot.id],
		),
	]
	backendManager.config_createObjects(basicConfigs)

	assert [] == backendManager.getKioskProductInfosForClient(client.id)


@pytest.fixture()
def client():
	return OpsiClient(id="foo.test.invalid")


@pytest.fixture()
def depot():
	return OpsiDepotserver(id="depotserver1.test.invalid")


@pytest.fixture()
def anotherDepot():
	return OpsiDepotserver(id="depotserver2.some.test")


def createProducts(amount=2):
	for number in range(amount):
		yield LocalbootProduct(
			id="product{0}".format(number),
			name="Product {0}".format(number),
			productVersion="{0}".format(number + 1),
			packageVersion="1",
			setupScript="setup.opsiscript",
			uninstallScript="uninstall.opsiscript",
			updateScript="update.opsiscript",
			description="This is product {0}".format(number),
			advice="Advice for product {0}".format(number),
		)


def testDoNotDuplicateProducts(backendManager, client, depot):
	backendManager.host_createObjects([client, depot])

	products = list(createProducts(10))
	backendManager.product_createObjects(products)

	for product in products:
		pod = ProductOnDepot(
			productId=product.id,
			productType=product.getType(),
			productVersion=product.getProductVersion(),
			packageVersion=product.getPackageVersion(),
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

	productGroupIds = set()
	for step in range(1, 4):
		productGroup = ProductGroup(id="group {0}".format(step))
		backendManager.group_createObjects([productGroup])
		productGroupIds.add(productGroup.id)

		for product in products[::step]:
			groupAssignment = ObjectToGroup(
				groupType=productGroup.getType(),
				groupId=productGroup.id,
				objectId=product.id,
			)
			backendManager.objectToGroup_createObjects([groupAssignment])

	basicConfigs = [
		UnicodeConfig(
			id="software-on-demand.product-group-ids",
			defaultValues=list(productGroupIds),
			multiValue=True,
		),
		UnicodeConfig(
			id="clientconfig.depot.id",
			description="Depotserver to use",
			possibleValues=[],
			defaultValues=[depot.id],
		),
	]
	backendManager.config_createObjects(basicConfigs)

	result = backendManager.getKioskProductInfosForClient(client.id)
	assert isinstance(result, list)
	assert len(result) == len(products)


def testGettingKioskInfoFromDifferentDepot(backendManager, client, depot, anotherDepot):
	backendManager.host_createObjects([client, depot, anotherDepot])

	products = list(createProducts(10))
	backendManager.product_createObjects(products)

	expectedProducts = set()
	for index, product in enumerate(products):
		pod = ProductOnDepot(
			productId=product.id,
			productType=product.getType(),
			productVersion=product.getProductVersion(),
			packageVersion=product.getPackageVersion(),
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

		if index % 2 == 0:
			# Assign every second product to the second depot
			pod.depotId = anotherDepot.id
			backendManager.productOnDepot_createObjects([pod])
			expectedProducts.add(product.id)

	productGroup = ProductGroup(id="my product group")
	backendManager.group_createObjects([productGroup])

	for product in products:
		groupAssignment = ObjectToGroup(
			groupType=productGroup.getType(),
			groupId=productGroup.id,
			objectId=product.id,
		)
		backendManager.objectToGroup_createObjects([groupAssignment])

	basicConfigs = [
		UnicodeConfig(
			id="software-on-demand.product-group-ids",
			defaultValues=[productGroup.id],
			multiValue=True,
		),
		UnicodeConfig(
			id="clientconfig.depot.id",
			description="Depotserver to use",
			possibleValues=[],
			defaultValues=[depot.id],
		),
	]
	backendManager.config_createObjects(basicConfigs)

	# Assign client to second depot
	backendManager.configState_create(
		"clientconfig.depot.id", client.id, values=[anotherDepot.id]
	)
	assert backendManager.getDepotId(client.id) == anotherDepot.id

	results = backendManager.getKioskProductInfosForClient(client.id)
	assert isinstance(results, list)

	for result in results:
		assert result["productId"] in expectedProducts

	assert len(results) == 5


@pytest.mark.parametrize("addConfigs", [True, False])
def testGettingKioskInfoWithConfigStates(backendManager, client, depot, addConfigs):
	backendManager.host_createObjects([client, depot])

	products = list(createProducts(2))
	backendManager.product_createObjects(products)

	for product in products:
		pod = ProductOnDepot(
			productId=product.id,
			productType=product.getType(),
			productVersion=product.getProductVersion(),
			packageVersion=product.getPackageVersion(),
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

	productGroup = ProductGroup(id="my product group")
	backendManager.group_createObjects([productGroup])

	for product in products:
		groupAssignment = ObjectToGroup(
			groupType=productGroup.getType(),
			groupId=productGroup.id,
			objectId=product.id,
		)
		backendManager.objectToGroup_createObjects([groupAssignment])

	dependency = ProductDependency(
		productId=products[0].id,
		requiredProductId=products[1].id,
		productVersion="1",
		packageVersion="1",
		productAction="setup",
		requiredAction="setup",
	)
	backendManager.productDependency_createObjects([dependency])

	basicConfigs = [
		UnicodeConfig(
			id="software-on-demand.product-group-ids",
			defaultValues=[productGroup.id],
			multiValue=True,
		),
		UnicodeConfig(
			id="clientconfig.depot.id",
			description="Depotserver to use",
			possibleValues=[],
			defaultValues=[depot.id],
		),
	]
	backendManager.config_createObjects(basicConfigs)

	result = backendManager.getKioskProductInfosForClient(
		clientId=client.id, addConfigs=addConfigs
	)

	if addConfigs:
		assert isinstance(result, dict)
		assert len(result) == 2

		assert len(result["configStates"]) == 1
		assert len(result["products"]) == 2

		for item in result["products"]:
			if item["productId"] == products[0].id:
				assert len(item["requirements"]) == 1
				break
		else:
			raise RuntimeError("Did not find product with id {}".format(products[0].id))
	else:
		assert isinstance(result, list)
		assert len(result) == 2

		for item in result:
			assert isinstance(item, dict)
			if item["productId"] == products[0].id:
				assert len(item["requirements"]) == 1
				break
		else:
			raise RuntimeError("Did not find product with id {}".format(products[0].id))
