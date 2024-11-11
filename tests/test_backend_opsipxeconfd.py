# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing opsipxeconfd backend.
"""

import pytest
from OPSI.Backend.OpsiPXEConfd import OpsiPXEConfdBackend, getClientCacheFilePath
from OPSI.Object import (
	NetbootProduct,
	OpsiClient,
	OpsiDepotserver,
	ProductOnClient,
	ProductOnDepot,
	UnicodeConfig,
)

from .helpers import patchAddress


@pytest.fixture()
def client():
	return OpsiClient(id="foo.test.invalid")


@pytest.fixture()
def depot():
	return OpsiDepotserver(id="depotserver1.test.invalid")


def testGetClientCachePath():
	clientId = "foo.bar.baz"

	path = getClientCacheFilePath(clientId)

	assert clientId in path
	assert path.endswith(".json")


def testCacheDataCollectionWithPxeConfigTemplate(backendManager, client, depot):
	"""
	Collection of caching data with a product with pxeConfigTemplate.
	"""
	backendManager.host_createObjects([client, depot])

	backendManager.config_createObjects(
		[
			UnicodeConfig(
				id="opsi-linux-bootimage.append",
				possibleValues=[
					"acpi=off",
					"irqpoll",
					"noapic",
					"pci=nomsi",
					"vga=normal",
					"reboot=b",
					"mem=2G",
					"nomodeset",
					"ramdisk_size=2097152",
				],
				defaultValues=[""],
			),
			UnicodeConfig(
				id="clientconfig.configserver.url",
				description="URL(s) of opsi config service(s) to use",
				possibleValues=["https://%s:4447/rpc" % depot.id],
				defaultValues=["https://%s:4447/rpc" % depot.id],
			),
			UnicodeConfig(
				id="clientconfig.depot.id",
				description="Depotserver to use",
				possibleValues=[],
				defaultValues=[depot.id],
			),
		]
	)

	product = NetbootProduct(
		"mytest86",
		productVersion=1,
		packageVersion=1,
		pxeConfigTemplate="scaredOfNothing",
	)
	backendManager.product_insertObject(product)

	productOnDepot = ProductOnDepot(
		productId=product.getId(),
		productType=product.getType(),
		productVersion=product.getProductVersion(),
		packageVersion=product.getPackageVersion(),
		depotId=depot.id,
	)
	backendManager.productOnDepot_createObjects([productOnDepot])

	poc = ProductOnClient(
		product.id, product.getType(), client.id, actionRequest="setup"
	)
	backendManager.productOnClient_insertObject(poc)

	with patchAddress(fqdn=depot.id):
		backend = OpsiPXEConfdBackend(context=backendManager)

		data = backend._collectDataForUpdate(client.id, depot.id)
		assert data
		assert data["product"]["pxeConfigTemplate"] == product.pxeConfigTemplate


def testCacheDataCollectionWithChangingPxeConfigTemplate(backendManager, client, depot):
	"""
	Testing what happens if the pxe template of a product is changed.
	"""
	backendManager.host_createObjects([client, depot])

	backendManager.config_createObjects(
		[
			UnicodeConfig(
				id="opsi-linux-bootimage.append",
				possibleValues=[
					"acpi=off",
					"irqpoll",
					"noapic",
					"pci=nomsi",
					"vga=normal",
					"reboot=b",
					"mem=2G",
					"nomodeset",
					"ramdisk_size=2097152",
				],
				defaultValues=[""],
			),
			UnicodeConfig(
				id="clientconfig.configserver.url",
				description="URL(s) of opsi config service(s) to use",
				possibleValues=["https://%s:4447/rpc" % depot.id],
				defaultValues=["https://%s:4447/rpc" % depot.id],
			),
			UnicodeConfig(
				id="clientconfig.depot.id",
				description="Depotserver to use",
				possibleValues=[],
				defaultValues=[depot.id],
			),
		]
	)

	oldProduct = NetbootProduct(
		"mytest86", productVersion=1, packageVersion=1, pxeConfigTemplate="old"
	)
	backendManager.product_insertObject(oldProduct)
	newProduct = NetbootProduct(
		oldProduct.id,
		productVersion=oldProduct.productVersion,
		packageVersion=int(oldProduct.packageVersion) + 1,
		pxeConfigTemplate="new",
	)
	backendManager.product_insertObject(newProduct)

	productOnDepot = ProductOnDepot(
		productId=oldProduct.getId(),
		productType=oldProduct.getType(),
		productVersion=oldProduct.getProductVersion(),
		packageVersion=oldProduct.getPackageVersion(),
		depotId=depot.id,
	)
	backendManager.productOnDepot_createObjects([productOnDepot])

	# Prepare next productOnDepot
	productOnDepot2 = ProductOnDepot(
		productId=newProduct.getId(),
		productType=newProduct.getType(),
		productVersion=newProduct.getProductVersion(),
		packageVersion=newProduct.getPackageVersion(),
		depotId=depot.id,
	)

	poc = ProductOnClient(
		oldProduct.id, oldProduct.getType(), client.id, actionRequest="setup"
	)
	backendManager.productOnClient_insertObject(poc)

	with patchAddress(fqdn=depot.id):
		backend = OpsiPXEConfdBackend(context=backendManager)

		data = backend._collectDataForUpdate(client.id, depot.id)
		assert data["product"]["pxeConfigTemplate"] == oldProduct.pxeConfigTemplate

		# Switching to new version on depot
		backendManager.productOnDepot_createObjects([productOnDepot2])

		data = backend._collectDataForUpdate(client.id, depot.id)
		assert data["product"]["pxeConfigTemplate"] == newProduct.pxeConfigTemplate


def testCacheDataCollectionWithMultiplePxeConfigTemplates(
	backendManager, client, depot
):
	"""
	Testing what happens if each product version has a different pxe template.
	"""
	backendManager.host_createObjects([client, depot])

	backendManager.config_createObjects(
		[
			UnicodeConfig(
				id="opsi-linux-bootimage.append",
				possibleValues=[
					"acpi=off",
					"irqpoll",
					"noapic",
					"pci=nomsi",
					"vga=normal",
					"reboot=b",
					"mem=2G",
					"nomodeset",
					"ramdisk_size=2097152",
				],
				defaultValues=[""],
			),
			UnicodeConfig(
				id="clientconfig.configserver.url",
				description="URL(s) of opsi config service(s) to use",
				possibleValues=["https://%s:4447/rpc" % depot.id],
				defaultValues=["https://%s:4447/rpc" % depot.id],
			),
			UnicodeConfig(
				id="clientconfig.depot.id",
				description="Depotserver to use",
				possibleValues=[],
				defaultValues=[depot.id],
			),
		]
	)

	oldProduct = NetbootProduct(
		"mytest86", productVersion=1, packageVersion=1, pxeConfigTemplate="old"
	)
	backendManager.product_insertObject(oldProduct)
	newProduct = NetbootProduct(
		oldProduct.id,
		productVersion=oldProduct.productVersion,
		packageVersion=int(oldProduct.packageVersion) + 1,
		pxeConfigTemplate="new",
	)
	backendManager.product_insertObject(newProduct)

	# The following product exists but is not available on the depot.
	newerProduct = NetbootProduct(
		oldProduct.id,
		productVersion=oldProduct.productVersion,
		packageVersion=int(oldProduct.packageVersion) + 2,
		pxeConfigTemplate="new",
	)
	backendManager.product_insertObject(newerProduct)

	productOnDepot = ProductOnDepot(
		productId=newProduct.getId(),
		productType=newProduct.getType(),
		productVersion=newProduct.getProductVersion(),
		packageVersion=newProduct.getPackageVersion(),
		depotId=depot.id,
	)
	backendManager.productOnDepot_createObjects([productOnDepot])

	poc = ProductOnClient(
		oldProduct.id, oldProduct.getType(), client.id, actionRequest="setup"
	)
	backendManager.productOnClient_insertObject(poc)

	with patchAddress(fqdn=depot.id):
		backend = OpsiPXEConfdBackend(context=backendManager)

		data = backend._collectDataForUpdate(client.id, depot.id)

		assert data["product"]["pxeConfigTemplate"] == newProduct.pxeConfigTemplate
