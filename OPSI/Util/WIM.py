# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Working with Windows Imaging Format (WIM) files.
"""

import os.path
from collections import namedtuple

from opsicommon.logging import get_logger

from OPSI.System import execute, which
from OPSI.Types import forceList, forceProductId
from OPSI.Util import getfqdn

__all__ = ("getImageInformation", "parseWIM", "writeImageInformation")

logger = get_logger("opsi.general")


def parseWIM(wimPath):
	"""
	Parses the WIM file at the given `path`.

	This requires `wimlib-imagex` to be installed on the server.

	:return: a list of images. These have attributes `name`, `languages` and `default_language`.
	"""
	Image = namedtuple("Image", "name languages default_language")

	logger.notice("Detected the following images:")
	images = []
	for image in getImageInformation(wimPath):
		logger.notice(image["name"])
		images.append(
			Image(
				image["name"],
				image.get("languages", tuple()),
				image.get("default language", None),
			)
		)

	if not images:
		raise ValueError("Could not find any images")

	return images


def getImageInformation(imagePath):
	"""
	Read information from a WIM file at `imagePath`.

	This method acts as a generator that yields information for each image
	in the file as a `dict`. The keys in the dict are all lowercase.
	Every dict has at least the key 'name'.
	"""
	if not os.path.exists(imagePath):
		raise OSError(f"File '{imagePath}' not found!")

	try:
		imagex = which("wimlib-imagex")
	except Exception as err:
		logger.debug(err, exc_info=True)
		logger.error(
			"Unable to find 'wimlib-imagex', please install 'wimtools': %s", err
		)
		raise RuntimeError(f"Unable to find 'wimlib-imagex': {err}") from err

	imageinfo = {}
	for line in execute(f"{imagex} info '{imagePath}'"):
		if line and ":" in line:
			key, value = line.split(":", 1)
			key = key.strip().lower()
			value = value.strip()

			if key == "languages":
				langs = value
				if " " in langs:
					langs = langs.split(" ")
				elif "," in langs:
					langs = langs.split(",")
				else:
					langs = [langs]

				languages = set()
				for lang in langs:
					if lang.strip():
						languages.add(lang.strip())

				value = languages

			imageinfo[key] = value
		elif not line and imageinfo:
			if "name" in imageinfo:  # Do not return file information.
				logger.debug("Collected information: %s", imageinfo)
				yield imageinfo

			imageinfo = {}


def writeImageInformation(
	backend, productId, imagenames, languages=None, defaultLanguage=None
):
	"""
	Writes information about the `imagenames` to the propert *imagename*
	of the product with the given `productId`.

	If `languages` are given these will be written to the property
	*system_language*. If an additional `defaultLanguage` is given this
	will be selected as the default.
	"""
	if hasattr(backend, "_get_backend_dispatcher"):
		# Use unprotected backend dispatcher if available
		backend_dispatcher = backend._get_backend_dispatcher()  # pylint: disable=protected-access
		if backend_dispatcher:
			backend = backend_dispatcher

	if not productId:
		raise ValueError(f"Not a valid productId: '{productId}'")
	productId = forceProductId(productId)

	productProperty = _getProductProperty(backend, productId, "imagename")
	productProperty.possibleValues = imagenames
	if productProperty.defaultValues:
		if productProperty.defaultValues[0] not in imagenames:
			logger.info(
				"Mismatching default value. Setting first imagename as default."
			)
			productProperty.defaultValues = [imagenames[0]]
	else:
		logger.info("No default values found. Setting first imagename as default.")
		productProperty.defaultValues = [imagenames[0]]

	backend.productProperty_updateObject(productProperty)
	logger.notice(
		"Wrote imagenames to property 'imagename' product on '%s'.", productId
	)

	if languages:
		logger.debug("Writing detected languages...")
		productPropertyList = [
			(
				_getProductProperty(backend, productId, "system_language"),
				"system_language",
			),
			(
				_getProductProperty(backend, productId, "winpe_uilanguage"),
				"winpe_uilanguage",
			),
			(
				_getProductProperty(backend, productId, "winpe_uilanguage_fallback"),
				"winpe_uilanguage_fallback",
			),
		]
		for _, productProperty in enumerate(productPropertyList):
			productProperty[0].possibleValues = forceList(languages)

			if defaultLanguage and defaultLanguage in languages:
				logger.debug("Setting language default to '%s'", defaultLanguage)
				productProperty[0].defaultValues = [defaultLanguage]

			logger.debug(
				"%s property is now: %s", productProperty[1], productProperty[0]
			)
			logger.debug(
				"%s possibleValues are: %s",
				productProperty[1],
				productProperty[0].possibleValues,
			)
			backend.productProperty_updateObject(productProperty[0])
			logger.notice(
				"Wrote languages to property '%s' product on %s.",
				productProperty[1],
				productId,
			)


def _getProductProperty(backend, productId, propertyId):
	productFilter = {"productId": productId, "propertyId": propertyId}
	properties = backend.productProperty_getObjects(**productFilter)
	logger.debug("Properties: %s", properties)

	if not properties:
		raise RuntimeError(
			f"No property '{propertyId}' for product '{productId}'' found!"
		)
	if len(properties) > 1:
		logger.debug("Found more than one property... trying to be more specific")

		serverId = getfqdn()
		prodOnDepot = backend.productOnDepot_getObjects(
			depotId=serverId, productId=productId
		)
		if not prodOnDepot:
			raise RuntimeError(
				f"Did not find product '{productId}' on depot '{serverId}'"
			)
		if len(prodOnDepot) > 1:
			raise RuntimeError(f"Too many products '{productId}' on depot {serverId}")

		prodOnDepot = prodOnDepot[0]
		productFilter["packageVersion"] = prodOnDepot.packageVersion
		productFilter["productVersion"] = prodOnDepot.productVersion
		logger.debug("New filter: %s", productFilter)
		properties = backend.productProperty_getObjects(**productFilter)
		logger.debug("Properties: %s", properties)

		if not properties:
			raise RuntimeError(
				f"Unable to find property '{propertyId}' for product '{productId}'!"
			)
		if len(properties) > 1:
			raise RuntimeError("Too many product properties found - aborting.")

	return properties[0]
