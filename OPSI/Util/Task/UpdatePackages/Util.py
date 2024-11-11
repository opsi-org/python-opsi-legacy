# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Utility functions for package updates.
"""

from opsicommon.logging import get_logger

from OPSI.Util import compareVersions

from .Exceptions import NoActiveRepositoryError

__all__ = ("getUpdatablePackages",)

logger = get_logger("opsi.general")


def getUpdatablePackages(updater):
	"""
	Returns information about updatable packages from the given `updater`.


	:raises NoActiveRepositoryError: If not active repositories are found.
	:param updater: The update to use.
	:type updater: OpsiPackageUpdater
	:returns: A dict containing the productId as key and the value is \
another dict with the keys _productId_, _newVersion_, _oldVersion_ and \
_repository_.
	:rtype: {str: {}
	"""
	if not any(updater.getActiveRepositories()):
		raise NoActiveRepositoryError("No active repository configured.")

	updates = {}
	try:
		installedProducts = updater.getInstalledProducts()
		downloadablePackages = updater.getDownloadablePackages()
		downloadablePackages = updater.onlyNewestPackages(downloadablePackages)
		downloadablePackages = updater._filterProducts(downloadablePackages)  # pylint: disable=protected-access

		for availablePackage in downloadablePackages:
			productId = availablePackage["productId"]
			for product in installedProducts:
				if product["productId"] == productId:
					logger.debug("Product '%s' is installed", productId)
					logger.debug(
						"Available product version is '%s', installed product version is '%s-%s'",
						availablePackage["version"],
						product["productVersion"],
						product["packageVersion"],
					)
					updateAvailable = compareVersions(
						availablePackage["version"],
						">",
						f"{product['productVersion']}-{product['packageVersion']}",
					)

					if updateAvailable:
						updates[productId] = {
							"productId": productId,
							"newVersion": f"{availablePackage['version']}",
							"oldVersion": f"{product['productVersion']}-{product['packageVersion']}",
							"repository": availablePackage["repository"].name,
						}
					break
	except Exception as error:
		raise error

	return updates
