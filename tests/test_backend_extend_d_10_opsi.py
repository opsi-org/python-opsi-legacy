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


@pytest.mark.parametrize(
	"clientId",
	[
		"backend-test-1.vmnat.local",
		"BACKEND-test-1.VMNAT.local",
		"BACKEND-TEST-1.VMNAT.LOCAL",
	],
)
def testSetProductActionRequestWithDependenciesSetsProductsToSetup(
	prefilledBackendManager, clientId
):
	"""
	An product action request should set product that are dependencies to \
setup even if they are already installed on a client.
	"""
	prefilledBackendManager.setProductActionRequestWithDependencies(
		"to_install", clientId, "setup"
	)

	productsOnClient = prefilledBackendManager.productOnClient_getObjects()
	assert 2 == len(productsOnClient)

	for poc in productsOnClient:
		assert (
			"backend-test-1.vmnat.local" == poc.clientId
		), "Wrong client id. Expected it to be {0!r} but got: {1!r}".format(
			"backend-test-1.vmnat.local", poc.clientId
		)

		if poc.productId == "already_installed":
			productThatShouldBeReinstalled = poc
			break
	else:
		raise AssertionError(
			'Could not find a product "{0}" on the client.'.format("already_installed")
		)

	assert productThatShouldBeReinstalled.productId == "already_installed"
	assert productThatShouldBeReinstalled.actionRequest == "setup"


@pytest.mark.parametrize(
	"installationStatus", ["installed", "unknown", "not_installed", None]
)
@pytest.mark.parametrize("actionRequest", ["setup"])
def testSetProductActionRequestWithDependenciesWithDependencyRequestingAction(
	backendManager, installationStatus, actionRequest
):
	client, depot = createClientAndDepot(backendManager)

	jedit = LocalbootProduct("jedit", "1.0", "1.0")
	javavm = LocalbootProduct("javavm", "1.0", "1.0")
	backendManager.product_createObjects([jedit, javavm])

	prodDependency = ProductDependency(
		productId=jedit.id,
		productVersion=jedit.productVersion,
		packageVersion=jedit.packageVersion,
		productAction="setup",
		requiredProductId=javavm.id,
		requiredAction="setup",
	)
	backendManager.productDependency_createObjects([prodDependency])

	jeditOnDepot = ProductOnDepot(
		productId=jedit.id,
		productType=jedit.getType(),
		productVersion=jedit.productVersion,
		packageVersion=jedit.packageVersion,
		depotId=depot.id,
	)
	javavmOnDepot = ProductOnDepot(
		productId=javavm.id,
		productType=javavm.getType(),
		productVersion=javavm.productVersion,
		packageVersion=javavm.packageVersion,
		depotId=depot.id,
	)
	backendManager.productOnDepot_createObjects([jeditOnDepot, javavmOnDepot])

	if installationStatus:
		poc = ProductOnClient(
			clientId=client.id,
			productId=javavm.id,
			productType=javavm.getType(),
			productVersion=javavm.productVersion,
			packageVersion=javavm.packageVersion,
			installationStatus=installationStatus,
			actionResult="successful",
		)

		backendManager.productOnClient_createObjects([poc])

	backendManager.setProductActionRequestWithDependencies(
		"jedit", client.id, actionRequest
	)

	productsOnClient = backendManager.productOnClient_getObjects()
	assert 2 == len(productsOnClient)

	for poc in productsOnClient:
		if poc.productId == "javavm":
			productThatShouldBeSetup = poc
			break
	else:
		raise ValueError(
			'Could not find a product "{0}" on the client.'.format("already_installed")
		)

	assert productThatShouldBeSetup.productId == "javavm"
	assert productThatShouldBeSetup.actionRequest == actionRequest


@pytest.mark.parametrize(
	"installationStatus", ["installed", "unknown", "not_installed", None]
)
@pytest.mark.parametrize("actionRequest", ["setup"])
def testSetProductActionRequestWithDependenciesWithDependencyRequiredInstallationStatus(
	backendManager, installationStatus, actionRequest
):
	client, depot = createClientAndDepot(backendManager)

	jedit = LocalbootProduct("jedit", "1.0", "1.0")
	javavm = LocalbootProduct("javavm", "1.0", "1.0")
	backendManager.product_createObjects([jedit, javavm])

	prodDependency = ProductDependency(
		productId=jedit.id,
		productVersion=jedit.productVersion,
		packageVersion=jedit.packageVersion,
		productAction="setup",
		requiredProductId=javavm.id,
		requiredInstallationStatus="installed",
		requirementType="after",
	)
	backendManager.productDependency_createObjects([prodDependency])

	jeditOnDepot = ProductOnDepot(
		productId=jedit.id,
		productType=jedit.getType(),
		productVersion=jedit.productVersion,
		packageVersion=jedit.packageVersion,
		depotId=depot.id,
	)
	javavmOnDepot = ProductOnDepot(
		productId=javavm.id,
		productType=javavm.getType(),
		productVersion=javavm.productVersion,
		packageVersion=javavm.packageVersion,
		depotId=depot.id,
	)
	backendManager.productOnDepot_createObjects([jeditOnDepot, javavmOnDepot])

	if installationStatus:
		poc = ProductOnClient(
			clientId=client.id,
			productId=javavm.id,
			productType=javavm.getType(),
			productVersion=javavm.productVersion,
			packageVersion=javavm.packageVersion,
			installationStatus=installationStatus,
			actionRequest=None,
			actionResult="successful",
		)

		backendManager.productOnClient_createObjects([poc])

	backendManager.setProductActionRequestWithDependencies(
		"jedit", client.id, actionRequest
	)

	productsOnClient = backendManager.productOnClient_getObjects()
	assert 2 == len(productsOnClient)

	for poc in productsOnClient:
		if poc.productId == "javavm":
			productThatShouldBeInstalled = poc
			break
	else:
		raise ValueError(
			'Could not find a product "{0}" on the client.'.format("already_installed")
		)

	assert productThatShouldBeInstalled.productId == "javavm"
	if installationStatus == "installed":
		assert not productThatShouldBeInstalled.actionRequest == "setup"


def testSetProductActionRequestWithDependenciesWithOnce(backendManager):
	client, depot = createClientAndDepot(backendManager)

	masterProduct = LocalbootProduct("master", "3", "1.0")
	prodWithSetup = LocalbootProduct("reiter", "1.0", "1.0")
	prodWithOnce = LocalbootProduct("mania", "1.0", "1.0")
	backendManager.product_createObjects([masterProduct, prodWithOnce, prodWithSetup])

	prodOnceDependency = ProductDependency(
		productId=masterProduct.id,
		productVersion=masterProduct.productVersion,
		packageVersion=masterProduct.packageVersion,
		productAction="once",
		requiredProductId=prodWithOnce.id,
		requiredAction="once",
		requirementType="after",
	)
	prodSetupDependency = ProductDependency(
		productId=masterProduct.id,
		productVersion=masterProduct.productVersion,
		packageVersion=masterProduct.packageVersion,
		productAction="once",
		requiredProductId=prodWithSetup.id,
		requiredAction="setup",
		requirementType="after",
	)
	backendManager.productDependency_createObjects(
		[prodOnceDependency, prodSetupDependency]
	)

	for prod in (masterProduct, prodWithOnce, prodWithSetup):
		pod = ProductOnDepot(
			productId=prod.id,
			productType=prod.getType(),
			productVersion=prod.productVersion,
			packageVersion=prod.packageVersion,
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

	backendManager.setProductActionRequestWithDependencies(
		masterProduct.id, "backend-test-1.vmnat.local", "once"
	)

	productsOnClient = backendManager.productOnClient_getObjects()
	assert 3 == len(productsOnClient)

	depOnce = None
	depSetup = None

	for poc in productsOnClient:
		if poc.productId == prodWithOnce.id:
			depOnce = poc
		elif poc.productId == prodWithSetup.id:
			depSetup = poc

	if not depOnce:
		raise ValueError(
			"Could not find a product {0!r} on the client.".format(prodWithOnce.id)
		)
	if not depSetup:
		raise ValueError(
			"Could not find a product {0!r} on the client.".format(prodWithSetup.id)
		)

	assert depOnce.actionRequest == "once"
	assert depSetup.actionRequest == "setup"


def testSetProductActionRequestWithDependenciesUpdateOnlyNeededObjects(backendManager):
	client, depot = createClientAndDepot(backendManager)

	expectedModificationTime = "2017-02-07 08:50:21"

	masterProduct = LocalbootProduct("master", "3", "1.0")
	prodWithSetup = LocalbootProduct("reiter", "1.0", "1.0")
	prodWithNoDep = LocalbootProduct("nicht_anfassen", "1.0", "1.0")
	backendManager.product_createObjects([masterProduct, prodWithNoDep, prodWithSetup])

	prodSetupDependency = ProductDependency(
		productId=masterProduct.id,
		productVersion=masterProduct.productVersion,
		packageVersion=masterProduct.packageVersion,
		productAction="setup",
		requiredProductId=prodWithSetup.id,
		requiredAction="setup",
		requirementType="after",
	)
	backendManager.productDependency_createObjects([prodSetupDependency])

	for prod in (masterProduct, prodWithNoDep, prodWithSetup):
		pod = ProductOnDepot(
			productId=prod.id,
			productType=prod.getType(),
			productVersion=prod.productVersion,
			packageVersion=prod.packageVersion,
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

	poc = ProductOnClient(
		clientId=client.id,
		productId=prodWithNoDep.id,
		productType=prodWithNoDep.getType(),
		productVersion=prodWithNoDep.productVersion,
		packageVersion=prodWithNoDep.packageVersion,
		installationStatus="installed",
		actionRequest=None,
		modificationTime=expectedModificationTime,
		actionResult="successful",
	)

	backendManager.productOnClient_createObjects([poc])

	backendManager.setProductActionRequestWithDependencies(
		masterProduct.id, client.id, "setup"
	)

	productsOnClient = backendManager.productOnClient_getObjects()
	assert 3 == len(productsOnClient)

	for poc in productsOnClient:
		if poc.productId == "nicht_anfassen":
			assert poc.modificationTime != expectedModificationTime


def testSetProductActionRequestWithDependenciesHandlingMissingProductOnDepot(
	backendManager,
):
	"""
	setProductActionRequestWithDependencies should be able to handle
	cases where not all products are present on the depot.
	"""
	client, depot = createClientAndDepot(backendManager)

	masterProduct = LocalbootProduct("master", "3", "1.0")
	prodWithSetup = LocalbootProduct("reiter", "1.0", "1.0")
	backendManager.product_createObjects([masterProduct, prodWithSetup])

	prodSetupDependency = ProductDependency(
		productId=masterProduct.id,
		productVersion=masterProduct.productVersion,
		packageVersion=masterProduct.packageVersion,
		productAction="setup",
		requiredProductId=prodWithSetup.id,
		requiredAction="setup",
		requirementType="after",
	)
	brokenSetupDependency = ProductDependency(
		productId=masterProduct.id,
		productVersion=masterProduct.productVersion,
		packageVersion=masterProduct.packageVersion,
		productAction="setup",
		requiredProductId="missing_product",
		requiredAction="setup",
		requirementType="after",
	)

	backendManager.productDependency_createObjects(
		[prodSetupDependency, brokenSetupDependency]
	)

	for prod in (masterProduct, prodWithSetup):
		pod = ProductOnDepot(
			productId=prod.id,
			productType=prod.getType(),
			productVersion=prod.productVersion,
			packageVersion=prod.packageVersion,
			depotId=depot.id,
		)
		backendManager.productOnDepot_createObjects([pod])

	backendManager.setProductActionRequestWithDependencies(
		masterProduct.id, client.id, "setup"
	)

	productsOnClient = backendManager.productOnClient_getObjects()

	# Neither master nor dependencies are set to setup
	# product 'reiter' could be set to setup depending on the order in
	# which products are processed in the backend.
	# product 'master' will not be set to setup because it is set to
	# 'none' through OPSI.SharedAlgorithm.
	assert len(productsOnClient) <= 1

	for poc in productsOnClient:
		if poc.productId == "reiter":
			assert poc.actionRequest == "setup"
		else:
			raise RuntimeError("Unexpected product: %s" % poc)
