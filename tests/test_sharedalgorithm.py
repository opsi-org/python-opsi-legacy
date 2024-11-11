# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing OPSI.SharedAlgorithm
"""

import pytest
from OPSI import SharedAlgorithm
from OPSI.Exceptions import OpsiProductOrderingError
from OPSI.Object import LocalbootProduct, ProductDependency
from OPSI.Types import forceUnicode


def testSortingWithoutConflicts():
	"""
	Test sorting products without conflicts.

	There are no conflicting products and no failures expected.
	"""
	dependencies, products = getDependencies()

	print("Products: {0}".format(products))
	print("Dependencies: {0}".format(dependencies))

	expectedResult = [
		"opsi-agent",
		"sysessential",
		"firefox",
		"javavm",
		"ultravnc",
		"flashplayer",
		"jedit",
	]

	assert expectedResult == SharedAlgorithm.generateProductSequence_algorithm1(
		products, dependencies
	)


def getDependencies():
	products = getAvailableProducts()

	flashplayer = _getProductWithId(products, "flashplayer")
	firefox = _getProductWithId(products, "firefox")
	javavm = _getProductWithId(products, "javavm")
	jedit = _getProductWithId(products, "jedit")
	ultravnc = _getProductWithId(products, "ultravnc")

	flashplayerDependency1 = ProductDependency(
		productId=flashplayer.id,
		productVersion=flashplayer.productVersion,
		packageVersion=flashplayer.packageVersion,
		productAction="setup",
		requiredProductId=firefox.id,
		requiredProductVersion=firefox.productVersion,
		requiredPackageVersion=firefox.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	javavmDependency1 = ProductDependency(
		productId=javavm.id,
		productVersion=javavm.productVersion,
		packageVersion=javavm.packageVersion,
		productAction="setup",
		requiredProductId=firefox.id,
		requiredProductVersion=firefox.productVersion,
		requiredPackageVersion=firefox.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	jeditDependency1 = ProductDependency(
		productId=jedit.id,
		productVersion=jedit.productVersion,
		packageVersion=jedit.packageVersion,
		productAction="setup",
		requiredProductId=javavm.id,
		requiredProductVersion=javavm.productVersion,
		requiredPackageVersion=javavm.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	ultravncDependency1 = ProductDependency(
		productId=ultravnc.id,
		productVersion=ultravnc.productVersion,
		packageVersion=ultravnc.packageVersion,
		productAction="setup",
		requiredProductId=javavm.id,
		requiredProductVersion=javavm.productVersion,
		requiredPackageVersion=javavm.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	dependencies = [
		flashplayerDependency1,
		javavmDependency1,
		jeditDependency1,
		ultravncDependency1,
	]

	return dependencies, products


def getAvailableProducts():
	opsiAgent = LocalbootProduct(
		id="opsi-agent",
		name="opsi client agent",
		productVersion="4.0",
		packageVersion="1",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=95,
	)

	ultravnc = LocalbootProduct(
		id="ultravnc",
		name="Ult@VNC",
		productVersion="1.0.8.2",
		packageVersion="1",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=0,
	)

	firefox = LocalbootProduct(
		id="firefox",
		name="Mozilla Firefox",
		productVersion="3.6",
		packageVersion="1",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		priority=0,
	)

	flashplayer = LocalbootProduct(
		id="flashplayer",
		name="Adobe Flashplayer",
		productVersion="10.0.45.2",
		packageVersion="2",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=0,
	)

	sysessential = LocalbootProduct(
		id="sysessential",
		name="Sys Essential",
		productVersion="1.10.0",
		packageVersion=2,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=55,
	)

	javavm = LocalbootProduct(
		id="javavm",
		name="Sun Java",
		productVersion="1.6.20",
		packageVersion=2,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=0,
	)

	jedit = LocalbootProduct(
		id="jedit",
		name="jEdit",
		productVersion="5.1.0",
		packageVersion=2,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		priority=0,
	)

	products = [opsiAgent, ultravnc, flashplayer, javavm, jedit, firefox, sysessential]

	return products


def _getProductWithId(products, productId):
	for product in products:
		if product.id == productId:
			return product
	else:
		raise ValueError("Missing product with ID {0!r}".format(productId))


def testCreatingOrderWithImpossibleDependenciesFails():
	products = [
		{
			"setupScript": "setup.ins",
			"name": "firefox-sequ",
			"priority": 0,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "firefox-sequ",
		},
		{
			"setupScript": "setup.ins",
			"uninstallScript": "unsetup.ins",
			"name": "flashplayer-sequ",
			"priority": 0,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "flashplayer-sequ",
		},
		{
			"setupScript": "setup.ins",
			"uninstallScript": "unsetup.ins",
			"name": "javavm-sequ",
			"priority": 0,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "javavm-sequ",
		},
		{
			"setupScript": "setup.ins",
			"name": "jedit-sequ",
			"priority": 0,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "jedit-sequ",
		},
		{
			"setupScript": "setup.ins",
			"uninstallScript": "unsetup.ins",
			"name": "sysessential-sequ",
			"priority": 55,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "sysessential-sequ",
		},
		{
			"setupScript": "setup.ins",
			"uninstallScript": "unsetup.ins",
			"name": "ultravnc-sequ",
			"priority": 0,
			"packageVersion": "1",
			"productVersion": "1.0",
			"id": "ultravnc-sequ",
		},
	]

	deps = [
		{
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "ultravnc-sequ",
			"packageVersion": "1",
			"productId": "firefox-sequ",
		},
		{
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "firefox-sequ",
			"packageVersion": "1",
			"productId": "flashplayer-sequ",
		},
		{
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "firefox-sequ",
			"packageVersion": "1",
			"productId": "javavm-sequ",
		},
		{
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "javavm-sequ",
			"packageVersion": "1",
			"productId": "jedit-sequ",
		},
		{
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "ultravnc-sequ",
			"packageVersion": "1",
			"productId": "sysessential-sequ",
		},
		{
			"ident": "ultravnc-sequ;1.0;1;setup;javavm-sequ",
			"productAction": "setup",
			"requirementType": "before",
			"requiredInstallationStatus": "installed",
			"productVersion": "1.0",
			"requiredProductId": "javavm-sequ",
			"packageVersion": "1",
			"productId": "ultravnc-sequ",
		},
	]

	products = [LocalbootProduct.fromHash(h) for h in products]
	deps = [ProductDependency.fromHash(h) for h in deps]

	with pytest.raises(OpsiProductOrderingError):
		try:
			SharedAlgorithm.generateProductSequence_algorithm1(products, deps)
		except OpsiProductOrderingError as error:
			errormessage = forceUnicode(error)
			raise error

	assert "firefox-sequ" in errormessage
	assert "javavm-sequ" in errormessage
	assert "ultravnc-sequ" in errormessage


def testCircularDependenciesRaiseException():
	"Creating a circular dependency raises an exception."

	dependencies, products = getCircularDepedencies()

	with pytest.raises(OpsiProductOrderingError):
		SharedAlgorithm.generateProductSequence_algorithm1(products, dependencies)


def testCircularDependenciesExceptionNamesConflictingProducts():
	"""
	A circular dependency exception should inform the user what \
products are currently conflicting.
	"""
	dependencies, products = getCircularDepedencies()

	try:
		SharedAlgorithm.generateProductSequence_algorithm1(products, dependencies)
		pytest.fail("Should not get here.")
	except OpsiProductOrderingError as error:
		assert "firefox" in forceUnicode(error)
		assert "javavm" in forceUnicode(error)
		assert "ultravnc" in forceUnicode(error)


def getCircularDepedencies():
	"""
	This creates a circular dependency.

	The testcase is that ultravnc depends on javavm, javavm on firefox
	and, now added, firefox on ultravnc.
	"""
	dependencies, products = getDependencies()
	firefox = _getProductWithId(products, "firefox")
	ultravnc = _getProductWithId(products, "ultravnc")

	dependencies.append(
		ProductDependency(
			productId=firefox.id,
			productVersion=firefox.productVersion,
			packageVersion=firefox.packageVersion,
			productAction="setup",
			requiredProductId=ultravnc.id,
			requiredProductVersion=ultravnc.productVersion,
			requiredPackageVersion=ultravnc.packageVersion,
			requiredAction=None,
			requiredInstallationStatus="installed",
			requirementType="before",
		)
	)

	return dependencies, products


def testSortingWithOverlappingDependencies():
	dependencies, products = getDependenciesWithCrossingPriority()
	print("Products: {0}".format(products))
	print("Deps: {0}".format(dependencies))

	sortedProductList = SharedAlgorithm.generateProductSequence_algorithm1(
		products, dependencies
	)
	assert sortedProductList == [
		"opsi-agent",
		"firefox",
		"javavm",
		"ultravnc",
		"sysessential",
		"flashplayer",
		"jedit",
	]


def getDependenciesWithCrossingPriority():
	"""
	The sysessential dependency tries to move the product ultravnc to \
front in contradiction to priority
	"""
	dependencies, products = getDependencies()

	sysessential = _getProductWithId(products, "sysessential")
	ultravnc = _getProductWithId(products, "ultravnc")
	sysessentialDependency1 = ProductDependency(
		productId=sysessential.id,
		productVersion=sysessential.productVersion,
		packageVersion=sysessential.packageVersion,
		productAction="setup",
		requiredProductId=ultravnc.id,
		requiredProductVersion=ultravnc.productVersion,
		requiredPackageVersion=ultravnc.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	dependencies.append(sysessentialDependency1)

	return dependencies, products


def testAlgorithm1SortingWithDifferentPriorities():
	msServicePack = LocalbootProduct.fromHash(
		{
			"priority": 0,
			"packageVersion": "5",
			"productVersion": "xpsp3",
			"id": "msservicepack",
		}
	)

	msHotFix = LocalbootProduct.fromHash(
		{
			"priority": 80,
			"packageVersion": "1",
			"productVersion": "201305",
			"id": "mshotfix",
		}
	)

	productDep = ProductDependency.fromHash(
		{
			"productAction": "setup",
			"requirementType": "after",
			"requiredInstallationStatus": "installed",
			"productVersion": "xpsp3",
			"requiredProductId": "mshotfix",
			"packageVersion": "5",
			"productId": "msservicepack",
		}
	)

	results = SharedAlgorithm.generateProductSequence_algorithm1(
		[msServicePack, msHotFix], [productDep]
	)

	first, second = results
	assert msServicePack.id == first
	assert msHotFix.id == second


def testAlgorithm1SortingWithAfterSetupDependency():
	renameClient = LocalbootProduct.fromHash(
		{
			"priority": 0,
			"packageVersion": "2",
			"productVersion": "1.0",
			"id": "renameopsiclient",
		}
	)

	winDomain = LocalbootProduct.fromHash(
		{
			"priority": 20,
			"packageVersion": "6",
			"productVersion": "1.0",
			"id": "windomain",
		}
	)

	productDep = ProductDependency.fromHash(
		{
			"productAction": "setup",
			"requirementType": "after",
			"productVersion": "1.0",
			"requiredProductId": "windomain",
			"requiredAction": "setup",
			"packageVersion": "6",
			"productId": "renameopsiclient",
		}
	)

	results = SharedAlgorithm.generateProductSequence_algorithm1(
		[winDomain, renameClient], [productDep]
	)

	first, second = results
	assert renameClient.id == first
	assert winDomain.id == second
