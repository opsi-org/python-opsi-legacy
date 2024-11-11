# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing backend replication.
"""

import pytest

from OPSI.Backend.Replicator import BackendReplicator

from .Backends import getTestBackend
from .test_configs import getConfigs, getConfigStates
from .test_groups import getHostGroups, getObjectToGroups, getProductGroup
from .test_hosts import getClients, getConfigServer, getDepotServers
from .test_license_management import getLicenseContracts
from .test_products import (
	getLocalbootProducts,
	getNetbootProduct,
	getProductDepdencies,
	getProductProperties,
	getProductPropertyStates,
	getProductsOnClients,
	getProductsOnDepot,
)
from .test_software_and_hardware_audit import (
	getAuditHardwareOnHost,
	getAuditHardwares,
	getAuditSoftwareOnClient,
	getAuditSoftwares,
)


# TODO: there are some cases we should test
# * handling backends with / without license management
# * test with serverID, depotID, hostID given
@pytest.mark.parametrize(
	"checkAuditData", [True, False], ids=["with audit", "without audit"]
)
def testBackendReplication(replicationDestinationBackend, checkAuditData):
	# One important note regarding pytest:
	# With our current way of setting up backends we may end up in
	# reading from and writing to the same source!
	# This is the only reason why we still have getTestBackend present.
	with getTestBackend(extended=True) as readBackend:
		fillBackend(readBackend)
		checkIfBackendIsFilled(readBackend)

		writeBackend = replicationDestinationBackend
		replicator = BackendReplicator(readBackend, writeBackend)
		replicator.replicate(audit=checkAuditData)

		checkIfBackendIsFilled(writeBackend)
		checkBackendDataIsEqual(
			readBackend, writeBackend, checkAuditData=checkAuditData
		)

		if not checkAuditData:
			assert 0 == len(writeBackend.auditHardware_getObjects())
			assert 0 == len(writeBackend.auditSoftware_getObjects())
			assert 0 == len(writeBackend.auditHardwareOnHost_getObjects())
			assert 0 == len(writeBackend.auditSoftwareOnClient_getObjects())


def checkBackendDataIsEqual(first, second, checkAuditData=True):
	compareResultsFromBackendMethod(first, second, "host_getObjects")
	compareResultsFromBackendMethod(first, second, "product_getObjects")
	compareResultsFromBackendMethod(first, second, "config_getObjects")
	compareResultsFromBackendMethod(first, second, "group_getObjects")
	compareResultsFromBackendMethod(first, second, "licenseContract_getObjects")
	compareResultsFromBackendMethod(first, second, "licensePool_getObjects")
	compareResultsFromBackendMethod(first, second, "softwareLicense_getObjects")
	compareResultsFromBackendMethod(first, second, "productDependency_getObjects")
	compareResultsFromBackendMethod(first, second, "productProperty_getObjects")
	compareResultsFromBackendMethod(first, second, "productOnDepot_getObjects")
	compareResultsFromBackendMethod(first, second, "productOnClient_getObjects")
	compareResultsFromBackendMethod(first, second, "productPropertyState_getObjects")
	compareResultsFromBackendMethod(first, second, "configState_getObjects")
	compareResultsFromBackendMethod(first, second, "objectToGroup_getObjects")
	compareResultsFromBackendMethod(
		first, second, "softwareLicenseToLicensePool_getObjects"
	)
	compareResultsFromBackendMethod(first, second, "licenseOnClient_getObjects")
	compareResultsFromBackendMethod(
		first, second, "auditSoftwareToLicensePool_getObjects"
	)

	if checkAuditData:
		compareResultsFromBackendMethod(first, second, "auditHardware_getObjects")
		compareResultsFromBackendMethod(first, second, "auditSoftware_getObjects")
		compareResultsFromBackendMethod(first, second, "auditHardwareOnHost_getObjects")
		compareResultsFromBackendMethod(
			first, second, "auditSoftwareOnClient_getObjects"
		)


def compareResultsFromBackendMethod(firstBackend, secondBackend, methodname):
	firstMethod = getattr(firstBackend, methodname)
	secondMethod = getattr(secondBackend, methodname)

	checkContents(firstMethod(), secondMethod())


def checkContents(firstData, secondData):
	assert len(firstData) == len(secondData)

	for obj in firstData:
		assert obj in secondData


def fillBackend(backend, licenseManagementData=False):
	configServer, depotServer, clients = fillBackendWithHosts(backend)
	products = fillBackendWithProducts(backend)
	configs = fillBackendWithConfigs(backend)
	groups = fillBackendWithGroups(backend)

	if licenseManagementData:
		fillBackendWithLicenseContracts(backend)
		fillBackendWithLicensePools(backend)
		fillBackendWithSoftwareLicenses(backend)

	fillBackendWithProductDependencys(backend, products)
	productProperties = fillBackendWithProductPropertys(backend, products)
	fillBackendWithProductOnDepots(backend, products, configServer, depotServer)
	fillBackendWithProductOnClients(backend, products, clients)
	fillBackendWithProductPropertyStates(
		backend, productProperties, depotServer, clients
	)
	fillBackendWithConfigStates(backend, configs, clients, depotServer)
	fillBackendWithObjectToGroups(backend, groups, clients)
	auditSoftwares = fillBackendWithAuditSoftwares(backend)
	fillBackendWithAuditSoftwareOnClients(backend, auditSoftwares, clients)

	if existsHwAuditConfig(backend):
		auditHardwares = fillBackendWithAuditHardwares(backend)
		fillBackendWithAuditHardwareOnHosts(backend, auditHardwares, clients)

	if licenseManagementData:
		fillBackendWithSoftwareLicenseToLicensePools(backend)
		fillBackendWithLicenseOnClients(backend)
		fillBackendWithAuditSoftwareToLicensePools(backend)


def checkIfBackendIsFilled(backend, licenseManagementData=False, auditData=False):
	assert len(backend.host_getObjects()) > 2
	assert len(backend.product_getObjects()) > 2
	assert len(backend.config_getObjects()) > 0
	for config in backend.config_getObjects():
		print(type(config), config.toHash())
		assert type(config).__name__ in ("UnicodeConfig", "BoolConfig")
	assert len(backend.group_getObjects()) > 2
	for group in backend.group_getObjects():
		print(type(group), group.toHash())
		assert type(group).__name__ in ("HostGroup", "ProductGroup")

	if licenseManagementData:
		# TODO: check licenseManagementData
		assert len(backend.licenseContract_getObjects()) > 0
		# fillBackendWithLicensePools(backend)
		# fillBackendWithSoftwareLicenses(backend)

	assert len(backend.productDependency_getObjects()) > 0
	assert len(backend.productProperty_getObjects()) > 0
	for product_property in backend.productProperty_getObjects():
		print(type(product_property), product_property.toHash())
		assert type(product_property).__name__ in (
			"UnicodeProductProperty",
			"BoolProductProperty",
		)
	assert len(backend.productOnDepot_getObjects()) > 0
	assert len(backend.productOnClient_getObjects()) > 0
	assert len(backend.productPropertyState_getObjects()) > 0
	assert len(backend.objectToGroup_getObjects()) > 0
	assert len(backend.configState_getObjects()) > 0

	if auditData:
		assert len(backend.auditSoftware_getObjects()) > 0
		assert len(backend.auditSoftwareOnClient_getObjects()) > 0

		if existsHwAuditConfig(backend):
			assert len(backend.auditHardwareOnHost_getObjects()) > 0
			assert len(backend.auditHardware_getObjects()) > 0


def existsHwAuditConfig(backend):
	return bool(backend._auditHardwareConfig)


def fillBackendWithHosts(backend):
	configServer = getConfigServer()
	backend.host_insertObject(configServer)

	depots = getDepotServers()
	backend.host_createObjects(depots)

	clients = getClients()
	backend.host_createObjects(clients)

	return configServer, depots, clients


def fillBackendWithProducts(backend):
	netbootProduct = getNetbootProduct()
	backend.product_createObjects(netbootProduct)

	localbootProducts = getLocalbootProducts()
	backend.product_createObjects(localbootProducts)

	return [netbootProduct] + list(localbootProducts)


def fillBackendWithConfigs(backend):
	configs = getConfigs()
	backend.config_createObjects(configs)

	return configs


def fillBackendWithGroups(backend):
	groups = list(getHostGroups())
	groups.append(getProductGroup())

	backend.group_createObjects(groups)

	return groups


def fillBackendWithLicenseContracts(backend):
	licenseContracts = getLicenseContracts()
	backend.licenseContract_createObjects(licenseContracts)


def fillBackendWithLicensePools(backend):
	raise NotImplementedError("This is yet to be implemented.")


def fillBackendWithSoftwareLicenses(backend):
	raise NotImplementedError("This is yet to be implemented.")


def fillBackendWithAuditHardwares(backend):
	if not existsHwAuditConfig(backend):
		return []

	auditHardwares = getAuditHardwares()
	backend.auditHardware_createObjects(auditHardwares)

	return auditHardwares


def fillBackendWithAuditSoftwares(backend):
	auditSoftwares = getAuditSoftwares()
	backend.auditSoftware_createObjects(auditSoftwares)

	return auditSoftwares


def fillBackendWithProductDependencys(backend, products):
	dependencies = getProductDepdencies(products)
	backend.productDependency_createObjects(dependencies)


def fillBackendWithProductPropertys(backend, products):
	properties = getProductProperties(products)
	backend.productProperty_createObjects(properties)

	return properties


def fillBackendWithProductOnDepots(backend, products, configServer, depotServer):
	productsOnDepots = getProductsOnDepot(products, configServer, depotServer)
	backend.productOnDepot_createObjects(productsOnDepots)


def fillBackendWithProductOnClients(backend, products, clients):
	productsOnClients = getProductsOnClients(products, clients)
	backend.productOnClient_createObjects(productsOnClients)

	return productsOnClients


def fillBackendWithProductPropertyStates(
	backend, productProperties, depotServer, clients
):
	productPropertyStates = getProductPropertyStates(
		productProperties, depotServer, clients
	)
	backend.productPropertyState_createObjects(productPropertyStates)


def fillBackendWithConfigStates(backend, configs, clients, depotserver):
	configStates = getConfigStates(configs, clients, depotserver)
	backend.configState_createObjects(configStates)


def fillBackendWithObjectToGroups(backend, groups, clients):
	objectToGroups = getObjectToGroups(groups, clients)
	backend.objectToGroup_createObjects(objectToGroups)


def fillBackendWithAuditHardwareOnHosts(backend, auditHardwares, clients):
	if not auditHardwares:
		return

	ahoh = getAuditHardwareOnHost(auditHardwares, clients)
	backend.auditHardwareOnHost_createObjects(ahoh)


def fillBackendWithAuditSoftwareOnClients(backend, auditSoftwares, clients):
	asoc = getAuditSoftwareOnClient(auditSoftwares, clients)
	assert len(asoc) > 0
	backend.auditSoftwareOnClient_createObjects(asoc)
	assert len(backend.auditSoftwareOnClient_getObjects()) > 0


def fillBackendWithSoftwareLicenseToLicensePools(backend):
	raise NotImplementedError("This is yet to be implemented.")  # TODO: <--


def fillBackendWithLicenseOnClients(backend):
	raise NotImplementedError("This is yet to be implemented.")  # TODO: <--


def fillBackendWithAuditSoftwareToLicensePools(backend):
	raise NotImplementedError("This is yet to be implemented.")  # TODO: <--
