# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the functionality of working with products.
"""

from itertools import product as iterproduct

import pytest

from OPSI.Backend.Backend import temporaryBackendOptions
from OPSI.Exceptions import BackendBadValueError
from OPSI.Object import (
	BoolProductProperty,
	LocalbootProduct,
	NetbootProduct,
	OpsiClient,
	OpsiDepotserver,
	Product,
	ProductDependency,
	ProductOnClient,
	ProductOnDepot,
	ProductPropertyState,
	UnicodeConfig,
	UnicodeProductProperty,
)
from OPSI.Types import forceHostId
from OPSI.Util import getfqdn

from .test_hosts import getClients, getConfigServer, getDepotServers


def getProducts():
	return [getNetbootProduct()] + list(getLocalbootProducts())


def getNetbootProduct():
	netbootProduct = NetbootProduct(
		id="product1",
		name="Product 1",
		productVersion="1.0",
		packageVersion=1,
		licenseRequired=True,
		setupScript="setup.py",
		uninstallScript=None,
		updateScript="update.py",
		alwaysScript=None,
		onceScript=None,
		priority="100",
		description="Nothing",
		advice="No advice",
		productClassIds=[],
		windowsSoftwareIds=["{be21bd07-eb19-44e4-893a-fa4e44e5f806}", "product1"],
		pxeConfigTemplate="special",
	)

	return netbootProduct


def getLocalbootProducts():
	product2 = LocalbootProduct(
		id="product2",
		name="Product 2",
		productVersion="2.0",
		packageVersion="test",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		alwaysScript=None,
		onceScript=None,
		priority=0,
		description=None,
		advice="",
		productClassIds=[],
		windowsSoftwareIds=["{98723-7898adf2-287aab}", "xxxxxxxx"],
	)

	product3 = LocalbootProduct(
		id="product3",
		name="Product 3",
		productVersion=3,
		packageVersion=1,
		licenseRequired=True,
		setupScript="setup.ins",
		uninstallScript=None,
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=100,
		description="---",
		advice="---",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product4 = LocalbootProduct(
		id="product4",
		name="Product 4",
		productVersion="3.0",
		packageVersion=24,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product5 = LocalbootProduct(
		id="product4",
		name="Product 4",
		productVersion="3.0",
		packageVersion=25,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product6 = LocalbootProduct(
		id="product6",
		name="Product 6",
		productVersion="1.0",
		packageVersion=1,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product7 = LocalbootProduct(
		id="product7",
		name="Product 7",
		productVersion="1.0",
		packageVersion=1,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product8 = LocalbootProduct(
		id="product8",
		name="Product 8",
		productVersion="1.0",
		packageVersion=2,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		customScript="custom.ins",
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	product9 = LocalbootProduct(
		id="product9",
		name=(
			"This is a very long name with 128 characters to test the "
			"creation of long product names that should work now but "
			"were limited b4"
		),
		productVersion="1.0",
		packageVersion=2,
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		customScript="custom.ins",
		priority=0,
		description="",
		advice="",
		productClassIds=[],
		windowsSoftwareIds=[],
	)

	return (
		product2,
		product3,
		product4,
		product5,
		product6,
		product7,
		product8,
		product9,
	)


def getProductDepdencies(products):
	product2, product3, product4, _, product6, product7, _, product9 = products[1:9]
	productDependency1 = ProductDependency(
		productId=product2.id,
		productVersion=product2.productVersion,
		packageVersion=product2.packageVersion,
		productAction="setup",
		requiredProductId=product3.id,
		requiredProductVersion=product3.productVersion,
		requiredPackageVersion=product3.packageVersion,
		requiredAction="setup",
		requiredInstallationStatus=None,
		requirementType="before",
	)

	productDependency2 = ProductDependency(
		productId=product2.id,
		productVersion=product2.productVersion,
		packageVersion=product2.packageVersion,
		productAction="setup",
		requiredProductId=product4.id,
		requiredProductVersion=None,
		requiredPackageVersion=None,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="after",
	)

	productDependency3 = ProductDependency(
		productId=product6.id,
		productVersion=product6.productVersion,
		packageVersion=product6.packageVersion,
		productAction="setup",
		requiredProductId=product7.id,
		requiredProductVersion=product7.productVersion,
		requiredPackageVersion=product7.packageVersion,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="after",
	)

	productDependency4 = ProductDependency(
		productId=product7.id,
		productVersion=product7.productVersion,
		packageVersion=product7.packageVersion,
		productAction="setup",
		requiredProductId=product9.id,
		requiredProductVersion=None,
		requiredPackageVersion=None,
		requiredAction=None,
		requiredInstallationStatus="installed",
		requirementType="after",
	)

	return (
		productDependency1,
		productDependency2,
		productDependency3,
		productDependency4,
	)


def getProductProperties(products):
	product1, _, product3 = products[:3]

	productProperty1 = UnicodeProductProperty(
		productId=product1.id,
		productVersion=product1.productVersion,
		packageVersion=product1.packageVersion,
		propertyId="productProperty1",
		description="Test product property (unicode)",
		possibleValues=["unicode1", "unicode2", "unicode3"],
		defaultValues=["unicode1", "unicode3"],
		editable=True,
		multiValue=True,
	)

	productProperty2 = BoolProductProperty(
		productId=product1.id,
		productVersion=product1.productVersion,
		packageVersion=product1.packageVersion,
		propertyId="productProperty2",
		description="Test product property 2 (bool)",
		defaultValues=True,
	)

	productProperty3 = BoolProductProperty(
		productId=product3.id,
		productVersion=product3.productVersion,
		packageVersion=product3.packageVersion,
		propertyId="productProperty3",
		description="Test product property 3 (bool)",
		defaultValues=False,
	)

	productProperty4 = UnicodeProductProperty(
		productId=product1.id,
		productVersion=product1.productVersion,
		packageVersion=product1.packageVersion,
		propertyId="i386_dir",
		description="i386 dir to use as installation source",
		possibleValues=["i386"],
		defaultValues=["i386"],
		editable=True,
		multiValue=False,
	)

	return productProperty1, productProperty2, productProperty3, productProperty4


def getProductsOnDepot(products, configServer, depotServer):
	(
		product1,
		product2,
		product3,
		_,
		product5,
		product6,
		product7,
		product8,
		product9,
	) = products[:9]
	depotserver1, depotserver2 = depotServer[:2]

	productOnDepot1 = ProductOnDepot(
		productId=product1.getId(),
		productType=product1.getType(),
		productVersion=product1.getProductVersion(),
		packageVersion=product1.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot2 = ProductOnDepot(
		productId=product2.getId(),
		productType=product2.getType(),
		productVersion=product2.getProductVersion(),
		packageVersion=product2.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot3 = ProductOnDepot(
		productId=product3.getId(),
		productType=product3.getType(),
		productVersion=product3.getProductVersion(),
		packageVersion=product3.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot4 = ProductOnDepot(
		productId=product3.getId(),
		productType=product3.getType(),
		productVersion=product3.getProductVersion(),
		packageVersion=product3.getPackageVersion(),
		depotId=configServer.getId(),
		locked=False,
	)

	productOnDepot5 = ProductOnDepot(
		productId=product5.getId(),
		productType=product5.getType(),
		productVersion=product5.getProductVersion(),
		packageVersion=product5.getPackageVersion(),
		depotId=configServer.getId(),
		locked=False,
	)

	productOnDepot6 = ProductOnDepot(
		productId=product6.getId(),
		productType=product6.getType(),
		productVersion=product6.getProductVersion(),
		packageVersion=product6.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot7 = ProductOnDepot(
		productId=product6.getId(),
		productType=product6.getType(),
		productVersion=product6.getProductVersion(),
		packageVersion=product6.getPackageVersion(),
		depotId=depotserver2.getId(),
		locked=False,
	)

	productOnDepot8 = ProductOnDepot(
		productId=product7.getId(),
		productType=product7.getType(),
		productVersion=product7.getProductVersion(),
		packageVersion=product7.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot9 = ProductOnDepot(
		productId=product8.getId(),
		productType=product8.getType(),
		productVersion=product8.getProductVersion(),
		packageVersion=product8.getPackageVersion(),
		depotId=depotserver2.getId(),
		locked=False,
	)

	productOnDepot10 = ProductOnDepot(
		productId=product9.getId(),
		productType=product9.getType(),
		productVersion=product9.getProductVersion(),
		packageVersion=product9.getPackageVersion(),
		depotId=depotserver1.getId(),
		locked=False,
	)

	productOnDepot11 = ProductOnDepot(
		productId=product9.getId(),
		productType=product9.getType(),
		productVersion=product9.getProductVersion(),
		packageVersion=product9.getPackageVersion(),
		depotId=depotserver2.getId(),
		locked=False,
	)

	return (
		productOnDepot1,
		productOnDepot2,
		productOnDepot3,
		productOnDepot4,
		productOnDepot5,
		productOnDepot6,
		productOnDepot7,
		productOnDepot8,
		productOnDepot9,
		productOnDepot10,
		productOnDepot11,
	)


def getProductsOnClients(products, clients):
	product1, product2 = products[:2]
	client1, _, client3 = clients[:3]

	productOnClient1 = ProductOnClient(
		productId=product1.getId(),
		productType=product1.getType(),
		clientId=client1.getId(),
		installationStatus="installed",
		actionRequest="setup",
		actionProgress="",
		productVersion=product1.getProductVersion(),
		packageVersion=product1.getPackageVersion(),
		modificationTime="2009-07-01 12:00:00",
	)

	productOnClient2 = ProductOnClient(
		productId=product2.getId(),
		productType=product2.getType(),
		clientId=client1.getId(),
		installationStatus="installed",
		actionRequest="uninstall",
		actionProgress="",
		productVersion=product2.getProductVersion(),
		packageVersion=product2.getPackageVersion(),
	)

	productOnClient3 = ProductOnClient(
		productId=product2.getId(),
		productType=product2.getType(),
		clientId=client3.getId(),
		installationStatus="installed",
		actionRequest="setup",
		actionProgress="running",
		productVersion=product2.getProductVersion(),
		packageVersion=product2.getPackageVersion(),
	)

	productOnClient4 = ProductOnClient(
		productId=product1.getId(),
		productType=product1.getType(),
		clientId=client3.getId(),
		targetConfiguration="installed",
		installationStatus="installed",
		actionRequest="none",
		lastAction="setup",
		actionProgress="",
		actionResult="successful",
		productVersion=product1.getProductVersion(),
		packageVersion=product1.getPackageVersion(),
	)

	return productOnClient1, productOnClient2, productOnClient3, productOnClient4


def getProductPropertyStates(productProperties, depotServer, clients):
	productProperty1, productProperty2 = productProperties[:2]
	depotserver1, depotserver2 = depotServer[:2]
	client1, client2 = clients[:2]

	productPropertyState1 = ProductPropertyState(
		productId=productProperty1.getProductId(),
		propertyId=productProperty1.getPropertyId(),
		objectId=depotserver1.getId(),
		values="unicode-depot-default",
	)

	productPropertyState2 = ProductPropertyState(
		productId=productProperty2.getProductId(),
		propertyId=productProperty2.getPropertyId(),
		objectId=depotserver1.getId(),
		values=[True],
	)

	productPropertyState3 = ProductPropertyState(
		productId=productProperty2.getProductId(),
		propertyId=productProperty2.getPropertyId(),
		objectId=depotserver2.getId(),
		values=False,
	)

	productPropertyState4 = ProductPropertyState(
		productId=productProperty1.getProductId(),
		propertyId=productProperty1.getPropertyId(),
		objectId=client1.getId(),
		values="unicode1",
	)

	productPropertyState5 = ProductPropertyState(
		productId=productProperty2.getProductId(),
		propertyId=productProperty2.getPropertyId(),
		objectId=client1.getId(),
		values=[False],
	)

	productPropertyState6 = ProductPropertyState(
		productId=productProperty2.getProductId(),
		propertyId=productProperty2.getPropertyId(),
		objectId=client2.getId(),
		values=True,
	)

	return (
		productPropertyState1,
		productPropertyState2,
		productPropertyState3,
		productPropertyState4,
		productPropertyState5,
		productPropertyState6,
	)


@pytest.mark.parametrize(
	"prodFilter, prodClass",
	(
		(None, object),
		("Product", Product),
		("LocalbootProduct", LocalbootProduct),
		("NetbootProduct", NetbootProduct),
	),
)
def testGetProductsByType(extendedConfigDataBackend, prodFilter, prodClass):
	origProds = getProducts()
	extendedConfigDataBackend.product_createObjects(origProds)

	expectedProducts = [p for p in origProds if isinstance(p, prodClass)]

	pFilter = {}
	if prodFilter:
		pFilter["type"] = prodFilter

	products = extendedConfigDataBackend.product_getObjects(**pFilter)
	assert len(products) == len(expectedProducts)

	for product in products:
		assert product in expectedProducts

		for p in expectedProducts:
			if (
				(product.id == p.id)
				and (product.productVersion == p.productVersion)
				and (product.packageVersion == p.packageVersion)
			):
				assert product == p


def test_verifyProducts(extendedConfigDataBackend):
	localProducts = getLocalbootProducts()
	netbootProducts = getNetbootProduct()
	origProds = [netbootProducts] + list(localProducts)
	extendedConfigDataBackend.product_createObjects(origProds)

	products = extendedConfigDataBackend.product_getObjects(
		type=localProducts[0].getType()
	)
	assert len(products) == len(localProducts)

	productIds = set(product.getId() for product in products)
	for product in localProducts:
		assert product.id in productIds

	for product in products:
		for p in origProds:
			if (
				product.id == p.id
				and product.productVersion == p.productVersion
				and product.packageVersion == p.packageVersion
			):
				product = product.toHash()
				p = p.toHash()
				for attribute, value in p.items():
					if attribute == "productClassIds":
						continue

					if value is not None:
						if type(value) is list:
							for v in value:
								assert v in product[attribute]
						else:
							assert value == product[attribute]
				break  # Stop iterating origProds


def testUpdatingProduct(extendedConfigDataBackend):
	origProds = getProducts()
	extendedConfigDataBackend.product_createObjects(origProds)

	product2 = origProds[1]
	product2.setName("Product 2 updated")
	product2.setPriority(60)

	products = extendedConfigDataBackend.product_updateObject(product2)
	products = extendedConfigDataBackend.product_getObjects(
		attributes=["name", "priority"], id=product2.id
	)
	assert len(products) == 1
	assert products[0].getName() == "Product 2 updated"
	assert products[0].getPriority() == 60


def testLongProductName(extendedConfigDataBackend):
	"""
	Can the backend handle product names of 128 characters length?
	"""
	product = LocalbootProduct(
		id="new_prod", name="New Product for Tests", productVersion=1, packageVersion=1
	)

	newName = (
		"This is a very long name with 128 characters to test the "
		"creation of long product names that should work now but "
		"were limited b4"
	)
	assert len(newName) == 128

	product.setName(newName)

	extendedConfigDataBackend.product_createObjects(product)
	backendProduct = extendedConfigDataBackend.product_getObjects(id=product.id)

	assert 1 == len(backendProduct)

	backendProduct = backendProduct[0]
	assert newName == backendProduct.name


@pytest.fixture(scope="session", params=[False, True], ids=["ascii", "unicode"])
def changelog(request):
	if request.param:
		# unicode
		changelog = """opsi-winst/opsi-script (4.11.5.13) stable; urgency=low

* do not try to run non existing external sub sections
* Jetzt ausf\xfchren oder sp\xe4ter

-- Detlef Oertel <d.oertel@uib.de>  Thu,  21 Aug 2015:15:00:00 +0200

"""
	else:
		# ASCII
		changelog = """opsi-winst/opsi-script (4.11.5.13) stable; urgency=low

* do not try to run non existing external sub sections

-- Detlef Oertel <d.oertel@uib.de>  Thu,  21 Aug 2015:15:00:00 +0200

"""

	changelog = changelog * 555

	assert len(changelog.strip()) > 65535  # Limit for `TEXT` in MySQL / MariaDB

	return changelog


def testLongChangelogOnProductCanBeHandled(extendedConfigDataBackend, changelog):
	product = LocalbootProduct(id="freiheit", productVersion=1, packageVersion=1)
	product.setChangelog(changelog)
	assert product.getChangelog() == changelog

	extendedConfigDataBackend.product_createObjects(product)

	productFromBackend = extendedConfigDataBackend.product_getObjects(id=product.id)[0]
	changelogFromBackend = productFromBackend.getChangelog()

	assert len(changelogFromBackend) > 1
	assert len(changelogFromBackend) > 63000  # Leaving some room...

	assert changelog[:2048] == changelogFromBackend[:2048]


def testGettingProductProperties(extendedConfigDataBackend):
	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	extendedConfigDataBackend.product_createObjects(prods)
	extendedConfigDataBackend.productProperty_createObjects(prodPropertiesOrig)

	productProperties = extendedConfigDataBackend.productProperty_getObjects()
	assert len(productProperties) == len(prodPropertiesOrig)

	matching = 0
	for productProperty, originalProperty in iterproduct(
		productProperties, prodPropertiesOrig
	):
		if (
			productProperty.productId == originalProperty.productId
			and productProperty.propertyId == originalProperty.propertyId
			and productProperty.productVersion == originalProperty.productVersion
			and productProperty.packageVersion == originalProperty.packageVersion
		):
			productProperty = productProperty.toHash()
			originalProperty = originalProperty.toHash()
			for attribute, value in originalProperty.items():
				if value is not None:
					if isinstance(value, list):
						for v in value:
							assert v in productProperty[attribute]
					else:
						assert value == productProperty[attribute]

			matching += 1

	assert matching == len(prodPropertiesOrig)


def testUpdatingProductProperty(extendedConfigDataBackend):
	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	extendedConfigDataBackend.product_createObjects(prods)
	extendedConfigDataBackend.productProperty_createObjects(prodPropertiesOrig)

	productProperty2 = prodPropertiesOrig[1]
	productProperty2.setDescription("updatedfortest")
	extendedConfigDataBackend.productProperty_updateObject(productProperty2)
	productProperties = extendedConfigDataBackend.productProperty_getObjects(
		attributes=[], description="updatedfortest"
	)

	assert len(productProperties) == 1
	assert productProperties[0].getDescription() == "updatedfortest"


def testDeletingProductProperty(extendedConfigDataBackend):
	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	extendedConfigDataBackend.product_createObjects(prods)
	extendedConfigDataBackend.productProperty_createObjects(prodPropertiesOrig)

	productProperty2 = prodPropertiesOrig[1]
	extendedConfigDataBackend.productProperty_deleteObjects(productProperty2)
	productProperties = extendedConfigDataBackend.productProperty_getObjects()
	assert len(productProperties) == len(prodPropertiesOrig) - 1
	assert productProperty2 not in productProperties


def testCreateDuplicateProductProperies(extendedConfigDataBackend):
	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	extendedConfigDataBackend.product_createObjects(prods)
	extendedConfigDataBackend.productProperty_createObjects(prodPropertiesOrig)

	productProperty1 = prodPropertiesOrig[0]
	productProperty4 = prodPropertiesOrig[3]
	extendedConfigDataBackend.productProperty_createObjects(
		[
			productProperty1,
			productProperty4,
			productProperty4,
			productProperty4,
			productProperty4,
		]
	)
	productProperties = extendedConfigDataBackend.productProperty_getObjects()
	assert len(productProperties) == len(prodPropertiesOrig)


def testGettingErrorMessageWhenAttributeInFilterIsNotAtObject(
	extendedConfigDataBackend,
):
	try:
		extendedConfigDataBackend.productPropertyState_getObjects(
			unknownAttribute="foobar"
		)
		assert False, "We should not get here."
	except BackendBadValueError as bbve:
		assert "has no attribute" in str(bbve)
		assert "unknownAttribute" in str(bbve)


def testProductAndPropertyWithSameName(extendedConfigDataBackend):
	"""
	Product and property may have the same name.
	"""
	product1 = LocalbootProduct(
		id="cbk",
		name="Comeback Kid",
		productVersion="1.0",
		packageVersion="2",
	)

	productProperty1 = BoolProductProperty(
		productId="cbk",
		productVersion=product1.productVersion,
		packageVersion=product1.packageVersion,
		propertyId="dep",
		defaultValues=True,
	)

	extendedConfigDataBackend.product_createObjects([product1])
	extendedConfigDataBackend.productProperty_createObjects([productProperty1])

	product2 = LocalbootProduct(
		id="dep",
		name="The Dillinger Escape Plan",
		productVersion="11.1",
		packageVersion=2,
	)

	productProperty2 = BoolProductProperty(
		productId=product2.id,
		productVersion=product2.productVersion,
		packageVersion=product2.packageVersion,
		propertyId="cbk",
		defaultValues=True,
	)

	extendedConfigDataBackend.product_createObjects([product2])
	extendedConfigDataBackend.productProperty_createObjects([productProperty2])

	properties = extendedConfigDataBackend.productProperty_getObjects(productId="cbk")

	assert 1 == len(properties)
	prop = properties[0]

	assert "dep" == prop.propertyId
	assert "cbk" == prop.productId
	assert "1.0" == prop.productVersion
	assert "2" == prop.packageVersion
	assert [True] == prop.defaultValues


def testProductPropertyStatesMustReferValidObjectId(extendedConfigDataBackend):
	product = LocalbootProduct("p1", productVersion=1, packageVersion=1)
	productProp = BoolProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="testtest",
		defaultValues=True,
	)

	extendedConfigDataBackend.product_createObjects(product)
	extendedConfigDataBackend.productProperty_createObjects(productProp)

	pps0 = ProductPropertyState(
		productId=productProp.getProductId(),
		propertyId=productProp.getPropertyId(),
		objectId="kaputtesdepot.dom.local",
	)

	with pytest.raises(Exception):
		extendedConfigDataBackend.productPropertyState_insertObject(pps0)


def testFixing1554(extendedConfigDataBackend):
	"""
	The backend must not ignore product property states of a product when \
the name of the product equals the name of a product property.

	The setup here is that there is a product with properties.
	One of these properties has the same ID as the name of a different
	product. For this product all properties must be shown.
	"""
	serverFqdn = forceHostId(getfqdn())  # using local FQDN
	depotserver1 = {
		"isMasterDepot": True,
		"type": "OpsiConfigserver",
		"id": serverFqdn,
	}

	product1 = {
		"name": "Windows Customizing",
		"packageVersion": "1",
		"productVersion": "4.0.1",
		"type": "LocalbootProduct",
		"id": "config-win-base",
	}

	product2 = {
		"name": "Software fuer Windows-Clients",
		"packageVersion": "3",
		"productVersion": "2.0",
		"type": "LocalbootProduct",
		"id": "clientprodukte",
	}

	productProperty1 = {
		"description": "Masterflag: Do Explorer Settings",
		"possibleValues": ["0", "1"],
		"defaultValues": ["1"],
		"productVersion": "4.0.1",
		"packageVersion": "1",
		"type": "UnicodeProductProperty",
		"propertyId": "flag_explorer",
		"productId": "config-win-base",
	}

	productProperty2 = {
		"description": "config-win-base installieren (empfohlen)",
		"possibleValues": ["ja", "nein"],
		"defaultValues": ["ja"],
		"productVersion": "2.0",
		"packageVersion": "3",
		"type": "UnicodeProductProperty",
		"propertyId": "config-win-base",
		"productId": "clientprodukte",
	}

	pps1 = {
		"objectId": serverFqdn,
		"values": ["1"],
		"type": "ProductPropertyState",
		"propertyId": "flag_explorer",
		"productId": "config-win-base",
	}

	pps2 = {
		"objectId": serverFqdn,
		"values": ["ja"],
		"type": "ProductPropertyState",
		"propertyId": "config-win-base",
		"productId": "clientprodukte",
	}

	extendedConfigDataBackend.product_createObjects([product1, product2])
	extendedConfigDataBackend.productProperty_createObjects(
		[productProperty1, productProperty2]
	)
	extendedConfigDataBackend.host_createObjects(depotserver1)
	extendedConfigDataBackend.productPropertyState_createObjects([pps1])

	product1Properties = extendedConfigDataBackend.productProperty_getObjects(
		productId=product1["id"]
	)
	assert product1Properties
	product2Properties = extendedConfigDataBackend.productProperty_getObjects(
		productId=product2["id"]
	)
	assert product2Properties

	# Only one productPropertyState
	property1States = extendedConfigDataBackend.productPropertyState_getObjects(
		productId=product1["id"]
	)
	assert property1States

	# Upping the game by inserting another productPropertyState
	extendedConfigDataBackend.productPropertyState_createObjects([pps2])

	property1States = extendedConfigDataBackend.productPropertyState_getObjects(
		productId=product1["id"]
	)
	assert property1States
	assert len(property1States) == 1
	property2States = extendedConfigDataBackend.productPropertyState_getObjects(
		productId=product2["id"]
	)
	assert property2States
	assert len(property2States) == 1
	propertyStatesForServer = extendedConfigDataBackend.productPropertyState_getObjects(
		objectId=depotserver1["id"], productId=product1["id"]
	)
	assert propertyStatesForServer
	assert len(property2States) == 1
	propertyStatesForServer = extendedConfigDataBackend.productPropertyState_getObjects(
		objectId=depotserver1["id"], productId=product2["id"]
	)
	assert propertyStatesForServer
	assert len(property2States) == 1
	propertyStatesForServer = extendedConfigDataBackend.productPropertyState_getObjects(
		objectId=depotserver1["id"]
	)
	assert propertyStatesForServer
	assert len(propertyStatesForServer) == 2


def testGetProductPropertyStatesFromBackend(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	depotServer = getDepotServers()
	properties = getProductProperties(products)
	pps = getProductPropertyStates(properties, depotServer, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depotServer)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productProperty_createObjects(properties)
	extendedConfigDataBackend.productPropertyState_createObjects(pps)

	productPropertyStates = extendedConfigDataBackend.productPropertyState_getObjects()
	assert len(pps) == len(productPropertyStates)

	for state in pps:
		assert state in productPropertyStates


def testDeletingProductPropertyStateFromBackend(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	depotServer = getDepotServers()
	properties = getProductProperties(products)
	pps = getProductPropertyStates(properties, depotServer, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depotServer)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productProperty_createObjects(properties)
	extendedConfigDataBackend.productPropertyState_createObjects(pps)

	productPropertyState2 = pps[1]
	extendedConfigDataBackend.productPropertyState_deleteObjects(productPropertyState2)
	productPropertyStates = extendedConfigDataBackend.productPropertyState_getObjects()
	assert productPropertyState2 not in productPropertyStates


def testInsertProductPropertyState(extendedConfigDataBackend):
	client = OpsiClient(id="someclient.test.invalid")
	product = LocalbootProduct("p1", productVersion=1, packageVersion=1)
	productProp = BoolProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="testtest",
		defaultValues=True,
	)
	pps = ProductPropertyState(
		productId=productProp.getProductId(),
		propertyId=productProp.getPropertyId(),
		objectId=client.id,
	)

	extendedConfigDataBackend.host_createObjects(client)
	extendedConfigDataBackend.product_createObjects(product)
	extendedConfigDataBackend.productProperty_createObjects(productProp)
	extendedConfigDataBackend.productPropertyState_insertObject(pps)

	productPropertyStates = extendedConfigDataBackend.productPropertyState_getObjects()
	assert 1 == len(productPropertyStates)
	assert pps in productPropertyStates


def test_getProductDependenciesFromBackendSmallExample(extendedConfigDataBackend):
	prod1 = LocalbootProduct("bla", 1, 1)
	prod2 = LocalbootProduct("foo", 2, 2)
	prod3 = LocalbootProduct("zulu", 3, 3)

	dep1 = ProductDependency(
		productId=prod1.id,
		productVersion=prod1.productVersion,
		packageVersion=prod1.packageVersion,
		productAction="setup",
		requiredProductId=prod2.id,
		requiredProductVersion=prod2.productVersion,
		requiredPackageVersion=prod2.packageVersion,
		requiredAction="setup",
		requiredInstallationStatus=None,
		requirementType="before",
	)
	dep2 = ProductDependency(
		productId=prod1.id,
		productVersion=prod1.productVersion,
		packageVersion=prod1.packageVersion,
		productAction="setup",
		requiredProductId=prod3.id,
		requiredProductVersion=prod3.productVersion,
		requiredPackageVersion=prod3.packageVersion,
		requiredAction="setup",
		requiredInstallationStatus=None,
		requirementType="before",
	)

	extendedConfigDataBackend.product_createObjects([prod1, prod2, prod3])
	assert 0 == len(extendedConfigDataBackend.productDependency_getObjects())

	extendedConfigDataBackend.productDependency_createObjects([dep1, dep2])

	productDependencies = extendedConfigDataBackend.productDependency_getObjects()
	assert 2 == len(productDependencies)


def testGetProductDependenciesFromBackend(extendedConfigDataBackend):
	products = getProducts()
	productDependenciesOrig = list(getProductDepdencies(products))

	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productDependency_createObjects(productDependenciesOrig)

	productDependencies = extendedConfigDataBackend.productDependency_getObjects()
	assert len(productDependencies) == len(productDependenciesOrig)


def testUpdateProductDependencies(extendedConfigDataBackend):
	products = getProducts()
	productDependenciesOrig = getProductDepdencies(products)

	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productDependency_createObjects(productDependenciesOrig)

	productDependency2 = productDependenciesOrig[1]

	assert productDependency2.requiredProductVersion != "2.0"
	productDependency2.requiredProductVersion = "2.0"
	assert productDependency2.requirementType is not None
	productDependency2.requirementType = None

	extendedConfigDataBackend.productDependency_updateObject(productDependency2)
	productDependencies = extendedConfigDataBackend.productDependency_getObjects()

	assert len(productDependencies) == len(productDependenciesOrig)
	for productDependency in productDependencies:
		if productDependency.getIdent() == productDependency2.getIdent():
			assert productDependency.getRequiredProductVersion() == "2.0"
			assert productDependency.getRequirementType() == "after"


def testDeletingProductDependency(extendedConfigDataBackend):
	products = getProducts()
	productDependenciesOrig = getProductDepdencies(products)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productDependency_createObjects(productDependenciesOrig)

	productDependency2 = productDependenciesOrig[1]

	extendedConfigDataBackend.productDependency_deleteObjects(productDependency2)
	productDependencies = extendedConfigDataBackend.productDependency_getObjects()
	assert len(productDependencies) == len(productDependenciesOrig) - 1


def testNotCreatingDuplicateProductDependency(extendedConfigDataBackend):
	products = getProducts()
	productDependenciesOrig = getProductDepdencies(products)
	extendedConfigDataBackend.product_createObjects(products)

	extendedConfigDataBackend.productDependency_createObjects(productDependenciesOrig)
	extendedConfigDataBackend.productDependency_createObjects(productDependenciesOrig)
	productDependencies = extendedConfigDataBackend.productDependency_getObjects()

	assert len(productDependenciesOrig) == len(productDependencies)


def testLockingProducts(extendedConfigDataBackend):
	prod = LocalbootProduct("Ruhe", 1, 1)
	depotserver = getConfigServer()  # A configserver always is also a depot.
	pod = ProductOnDepot(
		productId=prod.id,
		productType=prod.getType(),
		productVersion=prod.productVersion,
		packageVersion=prod.packageVersion,
		depotId=depotserver.id,
		locked=False,
	)

	extendedConfigDataBackend.host_createObjects(depotserver)
	extendedConfigDataBackend.product_createObjects(prod)
	extendedConfigDataBackend.productOnDepot_createObjects(pod)

	podFromBackend = extendedConfigDataBackend.productOnDepot_getObjects(
		productId=prod.id
	)[0]
	assert not podFromBackend.locked

	podFromBackend.locked = True
	extendedConfigDataBackend.productOnDepot_updateObjects(podFromBackend)

	podFromBackend = extendedConfigDataBackend.productOnDepot_getObjects(
		productId=prod.id
	)[0]
	assert podFromBackend.locked


def testGettingProductOnDepotsFromBackend(extendedConfigDataBackend):
	products = getProducts()
	configServer = getConfigServer()
	depots = getDepotServers()
	productsOnDepotOrig = getProductsOnDepot(products, configServer, depots)
	extendedConfigDataBackend.host_createObjects(configServer)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnDepot_createObjects(productsOnDepotOrig)

	productOnDepots = extendedConfigDataBackend.productOnDepot_getObjects(
		attributes=["productId"]
	)
	assert len(productOnDepots) == len(productsOnDepotOrig)


def testDeletingProductOnDepot(extendedConfigDataBackend):
	products = getProducts()
	configServer = getConfigServer()
	depots = getDepotServers()
	productsOnDepotOrig = getProductsOnDepot(products, configServer, depots)
	extendedConfigDataBackend.host_createObjects(configServer)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnDepot_createObjects(productsOnDepotOrig)

	productOnDepot1 = productsOnDepotOrig[0]
	extendedConfigDataBackend.productOnDepot_deleteObjects(productOnDepot1)
	productOnDepots = extendedConfigDataBackend.productOnDepot_getObjects()
	assert len(productOnDepots) == len(productsOnDepotOrig) - 1


def testCreatingDuplicateProductsOnDepots(extendedConfigDataBackend):
	products = getProducts()
	configServer = getConfigServer()
	depots = getDepotServers()
	productsOnDepotOrig = getProductsOnDepot(products, configServer, depots)
	extendedConfigDataBackend.host_createObjects(configServer)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.product_createObjects(products)

	extendedConfigDataBackend.productOnDepot_createObjects(productsOnDepotOrig)
	extendedConfigDataBackend.productOnDepot_createObjects(productsOnDepotOrig)

	productOnDepots = extendedConfigDataBackend.productOnDepot_getObjects()
	assert len(productOnDepots) == len(productsOnDepotOrig)


def testNotManuallyUpdatingModificationTimeOnProductOnClient(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	clients = getClients()
	products = getLocalbootProducts()
	pocs = getProductsOnClients(products, clients)

	backend.host_createObjects(clients)
	backend.product_createObjects(products)
	backend.productOnClient_createObjects(pocs)

	productOnClient2 = pocs[1]

	modTime = "2010-01-01 05:55:55"
	productOnClient2.setModificationTime(modTime)
	backend.productOnClient_updateObject(productOnClient2)
	productOnClients = backend.productOnClient_getObjects(
		modificationTime="2010-01-01 05:55:55"
	)
	assert not productOnClients
	productOnClients = backend.productOnClient_getObjects(modificationTime="2010-*")
	assert not productOnClients


def testGettingProductsOnClients(extendedConfigDataBackend):
	clients = getClients()
	products = getLocalbootProducts()
	pocs = getProductsOnClients(products, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnClient_createObjects(pocs)

	productOnClients = extendedConfigDataBackend.productOnClient_getObjects()
	assert len(productOnClients) == len(pocs)

	for poc in pocs:
		assert poc in productOnClients


def testGettingProductOnClientWithFilter(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	pocs = getProductsOnClients(products, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnClient_createObjects(pocs)

	client1 = clients[0]
	client1ProductOnClients = [
		productOnClient
		for productOnClient in pocs
		if productOnClient.getClientId() == client1.id
	]

	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		clientId=client1.getId()
	)
	for productOnClient in productOnClients:
		assert productOnClient.getClientId() == client1.getId()

	assert client1ProductOnClients == productOnClients


def testGettingProductOnClientByClientAndProduct(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	pocs = getProductsOnClients(products, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnClient_createObjects(pocs)

	client1 = clients[0]
	product2 = products[1]

	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		clientId=client1.getId(), productId=product2.getId()
	)
	assert 1 == len(productOnClients)
	poc = productOnClients[0]
	assert poc.getProductId() == product2.getId()
	assert poc.getClientId() == client1.getId()


def testGettingProductOnClientByClientAndProductType(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	clients = getClients()
	products = getLocalbootProducts()
	pocs = getProductsOnClients(products, clients)

	backend.host_createObjects(clients)
	backend.product_createObjects(products)
	backend.productOnClient_createObjects(pocs)

	productOnClient2 = pocs[1]

	productOnClients = backend.productOnClient_getObjects(
		productType=productOnClient2.productType, clientId=productOnClient2.clientId
	)
	assert len(productOnClients) >= 1
	assert productOnClient2 in productOnClients


def testUpdatingProductsOnClients(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	pocs = getProductsOnClients(products, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnClient_createObjects(pocs)

	productOnClient2 = pocs[1]
	productOnClient2.setTargetConfiguration("forbidden")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		targetConfiguration="forbidden"
	)
	assert productOnClient2 in productOnClients

	productOnClient2.setInstallationStatus("unknown")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		installationStatus="unknown"
	)
	assert len(productOnClients) == 1

	productOnClient2.setActionRequest("custom")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		actionRequest="custom"
	)
	assert len(productOnClients) == 1
	assert productOnClients[0] == productOnClient2

	productOnClient2.setLastAction("once")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		lastAction="once"
	)
	assert len(productOnClients) == 1
	assert productOnClients[0].clientId == productOnClient2.clientId

	productOnClient2.setActionProgress("aUniqueProgress")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		actionProgress="aUniqueProgress"
	)
	assert len(productOnClients) == 1
	assert productOnClients[0].clientId == productOnClient2.clientId

	productOnClient2.setActionResult("failed")
	extendedConfigDataBackend.productOnClient_updateObject(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects(
		actionResult="failed"
	)
	assert len(productOnClients) == 1
	assert productOnClients[0].clientId == productOnClient2.clientId


def testDeletingProductOnClient(extendedConfigDataBackend):
	products = getProducts()
	clients = getClients()
	pocs = getProductsOnClients(products, clients)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.product_createObjects(products)
	extendedConfigDataBackend.productOnClient_createObjects(pocs)

	productOnClient2 = pocs[1]
	extendedConfigDataBackend.productOnClient_deleteObjects(productOnClient2)
	productOnClients = extendedConfigDataBackend.productOnClient_getObjects()

	assert len(pocs) - 1 == len(productOnClients)
	assert productOnClient2 not in productOnClients


def testProductOnClientDependencies(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	clients = getClients()
	products = getLocalbootProducts()
	pocs = getProductsOnClients(products, clients)

	backend.host_createObjects(clients)
	backend.product_createObjects(products)
	backend.productOnClient_createObjects(pocs)

	# TODO

	# depotserver1: client1, client2, client3, client4
	# depotserver2: client5, client6, client7

	# depotserver1: product6_1.0-1, product7_1.0-1, product9_1.0-1
	# depotserver2: product6_1.0-1, product7_1.0-2, product9_1.0-1

	# product6_1.0-1: setup requires product7_1.0-1
	# product7_1.0-1: setup requires product9

	backend.productOnClient_create(
		productId="product6",
		productType="LocalbootProduct",
		clientId="client1.test.invalid",
		installationStatus="not_installed",
		actionRequest="setup",
	)

	backend.productOnClient_delete(
		productId="product7", clientId="client1.test.invalid"
	)

	backend.productOnClient_delete(
		productId="product9", clientId="client1.test.invalid"
	)

	productOnClients = backend.productOnClient_getObjects(
		clientId="client1.test.invalid"
	)
	setup = [
		productOnClient.productId
		for productOnClient in productOnClients
		if productOnClient.actionRequest == "setup"
	]
	assert "product6" in setup
	assert "product7" not in setup
	assert "product9" not in setup

	productOnClients = backend.productOnClient_getObjects(
		clientId="client1.test.invalid", productId=["product6", "product7"]
	)
	for productOnClient in productOnClients:
		print("Got productOnClient: %s" % productOnClient)
		assert productOnClient.productId in ("product6", "product7")

	productOnClients = backend.productOnClient_getObjects(
		clientId="client1.test.invalid", productId=["*6*"]
	)
	for productOnClient in productOnClients:
		print("Got productOnClient: %s" % productOnClient)
		assert productOnClient.productId == "product6"

	backend.productOnClient_create(
		productId="product6",
		productType="LocalbootProduct",
		clientId="client5.test.invalid",
		installationStatus="not_installed",
		actionRequest="setup",
	)

	backend.productOnClient_delete(
		productId="product7", clientId="client5.test.invalid"
	)

	backend.productOnClient_delete(
		productId="product9", clientId="client5.test.invalid"
	)

	productOnClients = backend.productOnClient_getObjects(
		clientId="client5.test.invalid"
	)
	setup = [
		productOnClient.productId
		for productOnClient in productOnClients
		if productOnClient.actionRequest == "setup"
	]
	assert "product7" not in setup
	assert "product9" not in setup


def test_processProductOnClientSequence(extendedConfigDataBackend):
	"""
	Checking that the backend is able to compute the sequences of clients.

	The basic constraints of products is the following:
	* setup of product2 requires product3 setup before
	* setup of product2 requires product4 installed before
	* setup of product4 requires product5 installed before

	This should result into the following sequence:
	* product3 (setup)
	* product5 (setup)
	* product4 (setup)
	* product2 (setup)
	"""
	backend = extendedConfigDataBackend

	clients = getClients()
	client1 = clients[0]

	depot = OpsiDepotserver(id="depotserver1.some.test")

	backend.host_createObjects([client1, depot])

	clientConfigDepotId = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		possibleValues=[],
		defaultValues=[depot.id],
	)
	backend.config_createObjects(clientConfigDepotId)

	product2 = LocalbootProduct("two", 2, 2)
	product3 = LocalbootProduct("three", 3, 3)
	product4 = LocalbootProduct("four", 4, 4)
	product5 = LocalbootProduct("five", 5, 5)
	prods = [product2, product3, product4, product5]
	backend.product_createObjects(prods)

	for prod in prods:
		pod = ProductOnDepot(
			productId=prod.id,
			productType=prod.getType(),
			productVersion=prod.productVersion,
			packageVersion=prod.packageVersion,
			depotId=depot.getId(),
			locked=False,
		)
		backend.productOnDepot_createObjects(pod)

	prodDependency1 = ProductDependency(
		productId=product2.id,
		productVersion=product2.productVersion,
		packageVersion=product2.packageVersion,
		productAction="setup",
		requiredProductId=product3.id,
		requiredAction="setup",
		requirementType="before",
	)

	prodDependency2 = ProductDependency(
		productId=product2.id,
		productVersion=product2.productVersion,
		packageVersion=product2.packageVersion,
		productAction="setup",
		requiredProductId=product4.id,
		requiredInstallationStatus="installed",
		requirementType="before",
	)

	prodDependency3 = ProductDependency(
		productId=product4.id,
		productVersion=product4.productVersion,
		packageVersion=product4.packageVersion,
		productAction="setup",
		requiredProductId=product5.id,
		requiredAction="setup",
		requiredInstallationStatus="installed",
		requirementType="before",
	)
	backend.productDependency_createObjects(
		[prodDependency1, prodDependency2, prodDependency3]
	)

	productOnClient1 = ProductOnClient(
		productId=product2.getId(),
		productType=product2.getType(),
		clientId=client1.getId(),
		installationStatus="not_installed",
		actionRequest="setup",
	)

	with temporaryBackendOptions(
		backend, processProductOnClientSequence=True, addDependentProductOnClients=True
	):
		backend.productOnClient_createObjects([productOnClient1])
		productOnClients = backend.productOnClient_getObjects(clientId=client1.id)

	undefined = -1
	posProduct2 = posProduct3 = posProduct4 = posProduct5 = undefined
	for productOnClient in productOnClients:
		if productOnClient.productId == product2.getId():
			posProduct2 = productOnClient.actionSequence
		elif productOnClient.productId == product3.getId():
			posProduct3 = productOnClient.actionSequence
		elif productOnClient.productId == product4.getId():
			posProduct4 = productOnClient.actionSequence
		elif productOnClient.productId == product5.getId():
			posProduct5 = productOnClient.actionSequence

	if any(
		pos == undefined for pos in (posProduct2, posProduct3, posProduct4, posProduct5)
	):
		print("Positions are: ")
		for poc in productOnClients:
			print("{0}: {1}".format(poc.productId, poc.actionSequence))

		raise Exception("Processing of product on client sequence failed")

	assert posProduct2 > posProduct3, "Wrong sequence: product3 not before product2"
	assert posProduct2 > posProduct4, "Wrong sequence: product4 not before product2"
	assert posProduct2 > posProduct5, "Wrong sequence: product5 not before product2"
	assert posProduct4 > posProduct5, "Wrong sequence: product5 not before product4"


def testGettingPxeConfigTemplate(backendManager):
	"""
	Test getting a NetbootProduct and limiting the attributes to pxeConfigTemplate.
	"""
	product = NetbootProduct(
		id="product1",
		productVersion="1.0",
		packageVersion=1,
		pxeConfigTemplate="special",
	)

	backendManager.product_insertObject(product)

	prodFromBackend = backendManager.product_getObjects(
		attributes=["id", "pxeConfigTemplate"], id=product.id
	)
	assert len(prodFromBackend) == 1
	prodFromBackend = prodFromBackend[0]

	assert product.id == prodFromBackend.id
	assert product.productVersion == prodFromBackend.productVersion
	assert product.packageVersion == prodFromBackend.packageVersion
	assert product.pxeConfigTemplate == prodFromBackend.pxeConfigTemplate


def testGettingUserloginScript(backendManager):
	"""
	Test getting a LocalbootProduct and limiting the attributes to userLoginScript.
	"""
	product = LocalbootProduct(
		id="product1",
		productVersion="1.0",
		packageVersion=1,
		userLoginScript="iloveyou",
	)

	backendManager.product_insertObject(product)

	prodFromBackend = backendManager.product_getObjects(
		attributes=["id", "userLoginScript"], id=product.id
	)
	assert len(prodFromBackend) == 1
	prodFromBackend = prodFromBackend[0]

	assert product.id == prodFromBackend.id
	assert product.productVersion == prodFromBackend.productVersion
	assert product.packageVersion == prodFromBackend.packageVersion
	assert product.userLoginScript == prodFromBackend.userLoginScript


def testVersionOnProduct():
	for product in getProducts():
		version = "{}-{}".format(product.productVersion, product.packageVersion)
		assert version == product.version


def testVersionOnProductOnClients():
	clients = getClients()
	products = getLocalbootProducts()

	for poc in getProductsOnClients(products, clients):
		version = "{}-{}".format(poc.productVersion, poc.packageVersion)
		assert version == poc.version


def testVersionOnProductOnDepots():
	products = getProducts()
	configServer = getConfigServer()
	depots = getDepotServers()

	for pod in getProductsOnDepot(products, configServer, depots):
		version = "{}-{}".format(pod.productVersion, pod.packageVersion)
		assert version == pod.version


def testUpdatingProductPropertyHashes(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	backend.product_createObjects(prods)
	backend.productProperty_createObjects(prodPropertiesOrig)

	ppFromBackend = backend.productProperty_getObjects()
	assert ppFromBackend
	ppFromBackend = [pp.toHash() for pp in ppFromBackend]
	for pp in ppFromBackend:
		pp["description"] = "Das ist auch dein Zuhause!"

	backend.productProperty_updateObjects(ppFromBackend)

	for pp in backend.productProperty_getObjects():
		assert pp.getDescription() == "Das ist auch dein Zuhause!"


def testUpdatingMultipleProductProperties(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	prods = getProducts()
	prodPropertiesOrig = getProductProperties(prods)
	backend.product_createObjects(prods)
	backend.productProperty_createObjects(prodPropertiesOrig)

	properties = backend.productProperty_getObjects()
	assert len(prodPropertiesOrig) == len(properties)
	assert len(properties) > 1, "Want more properties for tests"

	for index, changedProperty in enumerate(properties):
		if isinstance(changedProperty, UnicodeProductProperty):
			# We can not change the status of editable on a
			# BoolProductProperty and therefore need to use a
			# UnicodeProductProperty for this test.
			break
	else:
		raise RuntimeError("No UnicodeProductProperty found!")

	newText = "Eat my shorts!"
	changedProperty.setDescription(newText)
	changedProperty.setEditable(not changedProperty.getEditable())
	properties[index] == changedProperty
	backend.productProperty_updateObjects(properties)

	props = backend.productProperty_getObjects(
		productId=changedProperty.productId,
		productVersion=changedProperty.productVersion,
		packageVersion=changedProperty.packageVersion,
		propertyId=changedProperty.propertyId,
	)
	assert len(props) == 1
	updatedProp = props[0]

	assert updatedProp.getDescription() == newText
	assert updatedProp.getEditable() == changedProperty.getEditable()
