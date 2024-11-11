# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing backend cleaning.
"""

from OPSI.Object import LocalbootProduct, ProductOnDepot
from OPSI.Util.Task.CleanupBackend import cleanupBackend, cleanUpProducts

from .test_backend_replicator import (
	checkIfBackendIsFilled,
	fillBackend,
	fillBackendWithHosts,
)


def testCleanupBackend(cleanableDataBackend):
	# TODO: we need checks to see what get's removed and what not.
	# TODO: we also should provide some senseless data that will be removed!
	fillBackend(cleanableDataBackend)

	cleanupBackend(cleanableDataBackend)
	checkIfBackendIsFilled(cleanableDataBackend)


def testCleaninUpProducts(cleanableDataBackend):
	productIdToClean = "dissection"

	prod1 = LocalbootProduct(productIdToClean, 1, 1)
	prod12 = LocalbootProduct(productIdToClean, 1, 2)
	prod13 = LocalbootProduct(productIdToClean, 1, 3)
	prod2 = LocalbootProduct(productIdToClean + "2", 2, 1)
	prod3 = LocalbootProduct("unhallowed", 3, 1)
	prod32 = LocalbootProduct("unhallowed", 3, 2)

	products = [prod1, prod12, prod13, prod2, prod3, prod32]
	for p in products:
		cleanableDataBackend.product_insertObject(p)

	configServer, depotServer, _ = fillBackendWithHosts(cleanableDataBackend)
	depot = depotServer[0]

	pod1 = ProductOnDepot(
		prod13.id,
		prod13.getType(),
		prod13.productVersion,
		prod13.packageVersion,
		configServer.id,
	)
	pod1d = ProductOnDepot(
		prod13.id,
		prod13.getType(),
		prod13.productVersion,
		prod13.packageVersion,
		depot.id,
	)
	pod2 = ProductOnDepot(
		prod2.id, prod2.getType(), prod2.productVersion, prod2.packageVersion, depot.id
	)
	pod3 = ProductOnDepot(
		prod3.id, prod3.getType(), prod3.productVersion, prod3.packageVersion, depot.id
	)

	for pod in [pod1, pod1d, pod2, pod3]:
		cleanableDataBackend.productOnDepot_insertObject(pod)

	cleanUpProducts(cleanableDataBackend)

	products = cleanableDataBackend.product_getObjects(id=productIdToClean)
	assert len(products) == 1

	product = products[0]
	assert product.id == productIdToClean

	allProducts = cleanableDataBackend.product_getObjects()
	assert len(allProducts) == 3  # prod13, prod2, prod3
