# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for the dynamically loaded OPSI 3.x legacy methods.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/10_opsi.conf``.
"""

from OPSI.Object import (
	OpsiClient,
	LocalbootProduct,
	ProductOnClient,
	ProductDependency,
	OpsiDepotserver,
	ProductOnDepot,
	UnicodeConfig,
	ConfigState,
)

import pytest


@pytest.fixture
def prefilledBackendManager(backendManager):
	fillBackend(backendManager)
	yield backendManager


def fillBackend(backend):
	client, depot = createClientAndDepot(backend)

	firstProduct = LocalbootProduct("to_install", "1.0", "1.0")
	secondProduct = LocalbootProduct("already_installed", "1.0", "1.0")

	prodDependency = ProductDependency(
		productId=firstProduct.id,
		productVersion=firstProduct.productVersion,
		packageVersion=firstProduct.packageVersion,
		productAction="setup",
		requiredProductId=secondProduct.id,
		# requiredProductVersion=secondProduct.productVersion,
		# requiredPackageVersion=secondProduct.packageVersion,
		requiredAction="setup",
		requiredInstallationStatus="installed",
		requirementType="after",
	)

	backend.product_createObjects([firstProduct, secondProduct])
	backend.productDependency_createObjects([prodDependency])

	poc = ProductOnClient(
		clientId=client.id,
		productId=firstProduct.id,
		productType=firstProduct.getType(),
		productVersion=firstProduct.productVersion,
		packageVersion=firstProduct.packageVersion,
		installationStatus="installed",
		actionResult="successful",
	)

	backend.productOnClient_createObjects([poc])

	firstProductOnDepot = ProductOnDepot(
		productId=firstProduct.id,
		productType=firstProduct.getType(),
		productVersion=firstProduct.productVersion,
		packageVersion=firstProduct.packageVersion,
		depotId=depot.getId(),
		locked=False,
	)

	secondProductOnDepot = ProductOnDepot(
		productId=secondProduct.id,
		productType=secondProduct.getType(),
		productVersion=secondProduct.productVersion,
		packageVersion=secondProduct.packageVersion,
		depotId=depot.getId(),
		locked=False,
	)

	backend.productOnDepot_createObjects([firstProductOnDepot, secondProductOnDepot])


def createClientAndDepot(backend):
	client = OpsiClient(
		id="backend-test-1.vmnat.local", description="Unittest Test client."
	)

	depot = OpsiDepotserver(
		id="depotserver1.some.test",
		description="Test Depot",
	)

	backend.host_createObjects([client, depot])

	clientConfigDepotId = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		possibleValues=[],
		defaultValues=[depot.id],
	)

	backend.config_createObjects(clientConfigDepotId)

	clientDepotMappingConfigState = ConfigState(
		configId=clientConfigDepotId.getId(),
		objectId=client.getId(),
		values=depot.getId(),
	)

	backend.configState_createObjects(clientDepotMappingConfigState)

	return client, depot


def testBackendDoesNotCreateProductsOnClientsOnItsOwn(prefilledBackendManager):
	pocs = prefilledBackendManager.productOnClient_getObjects()
	assert 1 == len(
		pocs
	), "Expected to have only one ProductOnClient but got {n} instead: {0}".format(
		pocs, n=len(pocs)
	)
