# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
This tests what usually is found under
``/etc/opsi/backendManager/extend.de/10_wim.conf``.
"""

import os

import pytest

from OPSI.Object import NetbootProduct, ProductOnDepot, UnicodeProductProperty

from .helpers import getLocalFQDN, mock, patchAddress, patchEnvironmentVariables
from .test_hosts import getConfigServer
from .test_util_wim import (
	fakeWimPath,  # required fixture  # noqa: F401
)


def test_update_wim(backendManager, fakeWimPath):  # noqa: F811
	backend = backendManager
	localFqdn = getLocalFQDN()
	if "[mysql]" in os.environ["PYTEST_CURRENT_TEST"]:
		pytest.skip(
			"MySQL backend license check will not work with mocked os.path.exists"
		)

	with patchAddress(fqdn=localFqdn):
		with patchEnvironmentVariables(OPSI_HOSTNAME=localFqdn):
			fill_backend(backend)

			with mock.patch("OPSI.Util.WIM.os.path.exists", lambda path: True):
				backend.updateWIMConfig("testwindows")

			imagename = backend.productProperty_getObjects(
				propertyId="imagename", productId="testwindows"
			)
			imagename = imagename[0]

			possibleImageNames = set(
				[
					"Windows 7 HOMEBASICN",
					"Windows 7 HOMEPREMIUMN",
					"Windows 7 PROFESSIONALN",
					"Windows 7 STARTERN",
					"Windows 7 ULTIMATEN",
				]
			)
			assert possibleImageNames == set(imagename.possibleValues)
			assert imagename.defaultValues[0] in imagename.possibleValues

			language = backend.productProperty_getObjects(
				propertyId="system_language", productId="testwindows"
			)
			language = language[0]
			assert ["de-DE"] == language.defaultValues
			assert ["de-DE"] == language.possibleValues


@pytest.mark.parametrize("objectId", ["", None])
def test_updating_wim_fails_with_invalid_object_id(backendManager, objectId):
	with pytest.raises(ValueError):
		backendManager.updateWIMConfig(objectId)


def test_updating_wim_fails_with_invalid_product_id(backendManager):
	with pytest.raises(OSError):
		backendManager.updateWIMConfigFromPath("", "")


def fill_backend(backend):
	configServer = getConfigServer()
	backend.host_insertObject(configServer)

	product = NetbootProduct(id="testWindows", productVersion=1, packageVersion=1)
	backend.product_insertObject(product)

	productOnDepot = ProductOnDepot(
		productId=product.id,
		productType=product.getType(),
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		depotId=configServer.id,
		locked=False,
	)
	backend.productOnDepot_insertObject(productOnDepot)

	imagenameProductProperty = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="imagename",
		possibleValues=["NOT YOUR IMAGE", "NO NO NO"],
		defaultValues=["NOT YOUR IMAGE"],
		editable=True,
		multiValue=False,
	)
	systemLanguageProductProperty = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="system_language",
		possibleValues=["lol_NOPE"],
		defaultValues=["lol_NOPE", "rofl_MAO"],
		editable=True,
		multiValue=False,
	)
	winpeUilanguageProductProperty = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="winpe_uilanguage",
		possibleValues=["lel"],
		defaultValues=["lel", "topkek"],
		editable=True,
		multiValue=False,
	)
	winpeUilanguageFallbackProductProperty = UnicodeProductProperty(
		productId=product.id,
		productVersion=product.productVersion,
		packageVersion=product.packageVersion,
		propertyId="winpe_uilanguage_fallback",
		possibleValues=["lachkadse"],
		defaultValues=["lachkadse", "freuvieh"],
		editable=True,
		multiValue=False,
	)
	backend.productProperty_insertObject(imagenameProductProperty)
	backend.productProperty_insertObject(systemLanguageProductProperty)
	backend.productProperty_insertObject(winpeUilanguageProductProperty)
	backend.productProperty_insertObject(winpeUilanguageFallbackProductProperty)
