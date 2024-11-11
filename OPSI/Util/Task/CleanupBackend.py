# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Util - Task - Backend Cleanup

Functionality to clean up an OPSI Backend.

The aim of this module is to remove obsolete data from the backend to
ensure having clean data.

The everyday method for this job is :py:func:`cleanupBackend`.
For more specialised cleanup you should use the corresponding methods.

.. versionadded:: 4.0.4.2
"""

import re

from opsicommon.logging import get_logger

import OPSI.Util.Task.ConfigureBackend as backendUtil
from OPSI.Backend.BackendManager import BackendManager
from OPSI.Backend.MySQL import MySQL
from OPSI.Types import forceBool, forceUnicodeLower
from OPSI.Util import chunk
from OPSI.Util.File.Opsi import BackendDispatchConfigFile

_CHUNK_SIZE = 500

logger = get_logger("opsi.general")


def cleanupBackend(backend=None):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
	"""
	Clean up data from your backends.

	This method uses different cleanup methods to ensure that no
	obsolete data is present in your backend.

	:param backend: the backend to check. If ``None`` this will create a \
BackendManager from default paths.
	:type backend: OPSI.Backend.Backend
	"""

	def usesMysqlBackend():
		logger.notice("Parsing dispatch.conf")
		bdc = BackendDispatchConfigFile("/etc/opsi/backendManager/dispatch.conf")
		dispatchConfig = bdc.parse()
		for entry in dispatchConfig:
			(regex, backends) = entry
			if not re.search(regex, "backend_createBase"):
				continue

			if "mysql" in backends:
				return True

		return False

	logger.debug("Cleaning backend chunk size: %s", _CHUNK_SIZE)

	if backend is None:
		backend = BackendManager(
			dispatchConfigFile="/etc/opsi/backendManager/dispatch.conf",
			backendConfigDir="/etc/opsi/backends",
			extensionConfigDir="/etc/opsi/backendManager/extend.d",
			depotBackend=False,
			dispatchIgnoreModules=["OpsiPXEConfd", "DHCPD", "HostControl"],
		)

		try:
			if usesMysqlBackend():
				logger.notice(
					"Mysql-backend detected. Trying to cleanup mysql-backend first"
				)
				cleanUpMySQL()
		except Exception as err:  # pylint: disable=broad-except
			logger.warning(err)

	logger.notice("Cleaning up groups")
	cleanUpGroups(backend)

	logger.notice("Cleaning up products")
	cleanUpProducts(backend)

	logger.debug("Getting current depots...")
	depotIds = set(
		depot.id
		for depot in backend.host_getObjects(
			type=["OpsiConfigserver", "OpsiDepotserver"]
		)
	)  # pylint: disable=maybe-no-member
	logger.debug("Depots are: %s", depotIds)

	logger.debug("Getting current products...")
	productIdents = set(
		product.getIdent(returnType="unicode")
		for product in backend.product_getObjects()
	)
	logger.debug("Product idents are: %s", productIdents)

	logger.notice("Cleaning up product on depots")
	cleanUpProductOnDepots(backend, depotIds, productIdents)

	logger.notice("Cleaning up product on clients")
	cleanUpProductOnClients(backend)

	logger.notice("Cleaning up product properties")
	productPropertyIdents = set()
	deleteProductProperties = []
	productPropertiesToCleanup = {}
	for productProperty in backend.productProperty_getObjects():  # pylint: disable=maybe-no-member
		productIdent = f"{productProperty.productId};{productProperty.productVersion};{productProperty.packageVersion}"
		if not productProperty.editable and productProperty.possibleValues:
			productPropertyIdent = f"{productIdent};{productProperty.propertyId}"
			productPropertiesToCleanup[productPropertyIdent] = productProperty

		if productIdent not in productIdents:
			logger.info(
				"Marking productProperty %s of non existent product '%s' for deletion",
				productProperty,
				productIdent,
			)
			deleteProductProperties.append(productProperty)
		else:
			productPropertyIdent = (
				f"{productProperty.productId};{productProperty.propertyId}"
			)
			productPropertyIdents.add(productPropertyIdent)

	if deleteProductProperties:
		for productProperties in chunk(deleteProductProperties, _CHUNK_SIZE):
			logger.debug("Deleting product properties: '%s'", productProperties)
			backend.productProperty_deleteObjects(productProperties)  # pylint: disable=maybe-no-member

	logger.notice("Cleaning up product property states")
	deleteProductPropertyStates = []
	for productPropertyState in backend.productPropertyState_getObjects():  # pylint: disable=maybe-no-member
		productPropertyIdent = (
			f"{productPropertyState.productId};{productPropertyState.propertyId}"
		)
		if productPropertyIdent not in productPropertyIdents:
			logger.info(
				"Marking productPropertyState %s of non existent productProperty '%s' for deletion",
				productPropertyState,
				productPropertyIdent,
			)
			deleteProductPropertyStates.append(productPropertyState)

	if deleteProductPropertyStates:
		for productPropertyStates in chunk(deleteProductPropertyStates, _CHUNK_SIZE):
			logger.debug(
				"Deleting product property states: '%s'", productPropertyStates
			)
			backend.productPropertyState_deleteObjects(productPropertyStates)  # pylint: disable=maybe-no-member

	for depot in backend.host_getObjects(type="OpsiDepotserver"):  # pylint: disable=maybe-no-member,too-many-nested-blocks
		objectIds = set(
			ClientToDepot["clientId"]
			for ClientToDepot in backend.configState_getClientToDepotserver(
				depotIds=depot.id
			)
		)
		objectIds.add(depot.id)

		productOnDepotIdents = {}
		for productOnDepot in backend.productOnDepot_getObjects(depotId=depot.id):  # pylint: disable=maybe-no-member
			productIdent = f"{productOnDepot.productId};{productOnDepot.productVersion};{productOnDepot.packageVersion}"
			productOnDepotIdents[productOnDepot.productId] = productIdent

		if not productOnDepotIdents:
			continue

		deleteProductPropertyStates = []
		updateProductPropertyStates = []
		for productPropertyState in backend.productPropertyState_getObjects(  # pylint: disable=maybe-no-member
			objectId=objectIds, productId=list(productOnDepotIdents), propertyId=[]
		):
			productIdent = productOnDepotIdents.get(productPropertyState.productId)
			if not productIdent:
				continue
			productPropertyIdent = f"{productIdent};{productPropertyState.propertyId}"
			productProperty = productPropertiesToCleanup.get(productPropertyIdent)
			if not productProperty:
				continue
			changed = False
			newValues = []
			removeValues = []
			changedValues = []
			for value in productPropertyState.values:
				if value in productProperty.possibleValues:
					newValues.append(value)
					continue
				if (
					productProperty.getType() == "BoolProductProperty"
					and forceBool(value) in productProperty.possibleValues
				):
					newValues.append(forceBool(value))
					changedValues.append(value)
					changed = True
					continue
				if productProperty.getType() == "UnicodeProductProperty":
					newValue = None
					for possibleValue in productProperty.possibleValues:
						if forceUnicodeLower(possibleValue) == forceUnicodeLower(value):
							newValue = possibleValue
							break
					if newValue:
						newValues.append(newValue)
						changedValues.append(value)
						changed = True
						continue
				removeValues.append(value)
				changed = True
			if changed:
				if not newValues:
					logger.info(
						"Marking productPropertyState %s for deletion: no value in possible values (%s)",
						productPropertyState,
						removeValues,
					)
					deleteProductPropertyStates.append(productPropertyState)
				else:
					productPropertyState.setValues(newValues)
					logger.info(
						"Marking productPropertyState %s for update: values not in possible values: %s, values corrected: %s",
						productPropertyState,
						removeValues,
						changedValues,
					)
					updateProductPropertyStates.append(productPropertyState)

		if deleteProductPropertyStates:
			for productPropertyStates in chunk(
				deleteProductPropertyStates, _CHUNK_SIZE
			):
				logger.debug(
					"Deleting product property states: '%s'", productPropertyStates
				)
				backend.productPropertyState_deleteObjects(productPropertyStates)  # pylint: disable=maybe-no-member
			del deleteProductPropertyStates

		if updateProductPropertyStates:
			for productPropertyStates in chunk(
				updateProductPropertyStates, _CHUNK_SIZE
			):
				logger.debug(
					"Updating product property states: '%s'", productPropertyStates
				)
				backend.productPropertyState_updateObjects(productPropertyStates)  # pylint: disable=maybe-no-member
			del updateProductPropertyStates

	logger.notice("Cleaning up config states")
	cleanUpConfigStates(backend)

	logger.notice("Cleaning up audit softwares")
	cleanUpAuditSoftwares(backend)

	logger.notice("Cleaning up audit software on clients")
	cleanUpAuditSoftwareOnClients(backend)


def cleanUpMySQL(backendConfigFile="/etc/opsi/backends/mysql.conf"):
	"""
	Clean up an MySQL backend.

	**This does not work with any backend other than MySQL.**

	:param backendConfigFile: The configuration file of the currently \
used MySQL backend.
	:type backendConfigFile: str
	"""
	config = backendUtil.getBackendConfiguration(backendConfigFile)
	logger.info("Current mysql backend config: %s", config)

	logger.notice(
		"Connection to database '%s' on '%s' as user '%s'",
		config["database"],
		config["address"],
		config["username"],
	)
	mysql = MySQL(**config)
	with mysql.session() as session:
		logger.notice("Cleaning up defaultValues in productProperties")
		deleteIds = []
		found = []
		for res in mysql.getSet(
			session, "SELECT * FROM PRODUCT_PROPERTY_VALUE WHERE isDefault like '1'"
		):
			ident = ";".join(
				[
					res["propertyId"],
					res["productId"],
					res["productVersion"],
					res["productVersion"],
					res["value"],
				]
			)
			if ident not in found:
				found.append(ident)
			elif (
				res["value"] in ("0", "1")
				and res["product_property_id"] not in deleteIds
			):
				deleteIds.append(res["product_property_id"])

		for ID in deleteIds:
			logger.notice("Deleting PropertyValue id: %s", ID)
			mysql.execute(
				session,
				f"DELETE FROM `PRODUCT_PROPERTY_VALUE` where `product_property_id` = '{ID}'",
			)


def cleanUpGroups(backend):
	"""
	This checks if a group has a parent set that does not exist and
	removes non-existing parents.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""
	updatedGroups = []
	groups = backend.group_getObjects(type="HostGroup")
	groupIds = set(group.id for group in groups)

	for group in groups:
		if group.getParentGroupId() and group.getParentGroupId() not in groupIds:
			logger.info(
				"Removing parent group id '%s' from group '%s' because parent group does not exist",
				group.parentGroupId,
				group.id,
			)
			group.parentGroupId = None
			updatedGroups.append(group)

	if updatedGroups:
		for group in chunk(updatedGroups, _CHUNK_SIZE):
			logger.debug("Updating groups: %s", group)
			backend.group_createObjects(group)


def cleanUpProducts(backend):
	"""
	This will delete any unreferenced product from the backend.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""
	productIdents = set()
	for productOnDepot in backend.productOnDepot_getObjects():
		productIdent = ";".join(
			(
				productOnDepot.productId,
				productOnDepot.productVersion,
				productOnDepot.packageVersion,
			)
		)
		productIdents.add(productIdent)

	deleteProducts = []
	for product in backend.product_getObjects():
		if product.getIdent(returnType="unicode") not in productIdents:
			logger.info("Marking unreferenced product %s for deletion", product)
			deleteProducts.append(product)

	for products in chunk(deleteProducts, _CHUNK_SIZE):
		logger.debug("Deleting products: '%s'", products)
		backend.product_deleteObjects(products)


def cleanUpProductOnDepots(backend, depotIds, existingProductIdents):
	"""
	Deletes obsolete information that occurs if either a depot or a \
product is not existing anymore.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	:param depotIds: IDs of the existing depot.
	:type depotIds: [str, ]
	:param existingProductIdents: Idents of the existing products.
	:type existingProductIdents: [str, ]
	"""
	deleteProductOnDepots = []
	for productOnDepot in backend.productOnDepot_getObjects():
		productIdent = ";".join(
			[
				productOnDepot.productId,
				productOnDepot.productVersion,
				productOnDepot.packageVersion,
			]
		)
		if productOnDepot.depotId not in depotIds:
			logger.info(
				"Marking product on depot %s for deletion, because opsi depot Server '%s' not found",
				productOnDepot,
				productOnDepot.depotId,
			)
			deleteProductOnDepots.append(productOnDepot)
		elif productIdent not in existingProductIdents:
			logger.info(
				"Marking product on depot %s with missing product reference "
				"for deletion",
				productOnDepot,
			)
			deleteProductOnDepots.append(productOnDepot)

	if deleteProductOnDepots:
		for productOnDepots in chunk(deleteProductOnDepots, _CHUNK_SIZE):
			logger.debug("Deleting products on depots: %s", productOnDepots)
			backend.productOnDepot_deleteObjects(productOnDepots)


def cleanUpProductOnClients(backend):
	"""
	Delete :py:class:`ProductOnClient` if the client does not exist or \
is either *not_installed* without an action request set.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""
	deleteProductOnClients = []
	clientIds = set(
		client.id for client in backend.host_getObjects(type=["OpsiClient"])
	)

	for productOnClient in backend.productOnClient_getObjects():
		if productOnClient.clientId not in clientIds:
			logger.info(
				"Marking productOnClient %s for deletion, client doesn't exists",
				productOnClient,
			)
			deleteProductOnClients.append(productOnClient)
		elif (
			productOnClient.installationStatus == "not_installed"
			and productOnClient.actionRequest == "none"
		):
			logger.info("Marking productOnClient %s for deletion", productOnClient)
			deleteProductOnClients.append(productOnClient)

	if deleteProductOnClients:
		for productOnClients in chunk(deleteProductOnClients, _CHUNK_SIZE):
			logger.debug("Deleting products on clients: '%s'", productOnClients)
			backend.productOnClient_deleteObjects(productOnClients)

	deleteProductOnClients = []
	productIds = set(product.getId() for product in backend.product_getObjects())
	for productOnClient in backend.productOnClient_getObjects():
		if productOnClient.productId not in productIds:
			logger.info("Marking productOnClient %s for deletion", productOnClient)
			deleteProductOnClients.append(productOnClient)

	if deleteProductOnClients:
		for productOnClients in chunk(deleteProductOnClients, _CHUNK_SIZE):
			logger.debug("Deleting products on clients: '%s'", productOnClients)
			backend.productOnClient_deleteObjects(productOnClients)


def cleanUpConfigStates(backend):
	"""
	Deletes configStates if the corresponding config is nonexisting.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""
	deleteConfigStates = []
	configIds = set(backend.config_getIdents())

	for configState in backend.configState_getObjects():
		if configState.configId not in configIds:
			logger.info(
				"Marking configState %s of non existent config '%s' for deletion",
				configState,
				configState.configId,
			)
			deleteConfigStates.append(configState)

	if deleteConfigStates:
		for configStates in chunk(deleteConfigStates, _CHUNK_SIZE):
			logger.debug("Deleting config states: '%s'", configStates)
			backend.configState_deleteObjects(configStates)


def cleanUpAuditSoftwares(backend):
	"""
	Deletes unreferenced audit software.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""

	idents = set()
	for aso in backend.auditSoftwareOnClient_getHashes():
		idents.add(
			f"{aso['name']};{aso['version']};{aso['subVersion']};{aso['language']};{aso['architecture']}"
		)
	for aso in backend.auditSoftwareToLicensePool_getHashes():
		idents.add(
			f"{aso['name']};{aso['version']};{aso['subVersion']};{aso['language']};{aso['architecture']}"
		)

	for aso in backend.auditSoftware_getHashes():
		ident = f"{aso['name']};{aso['version']};{aso['subVersion']};{aso['language']};{aso['architecture']}"
		if ident not in idents:
			logger.info("Deleting unreferenced audit software %s", ident)
			backend.auditSoftware_delete(
				aso["name"],
				aso["version"],
				aso["subVersion"],
				aso["language"],
				aso["architecture"],
			)


def cleanUpAuditSoftwareOnClients(backend):
	"""
	Deletes unreferenced auditSoftwareOnClients.

	:param backend: The backend where the data should be cleaned.
	:type backend: OPSI.Backend.Backend
	"""
	idents = set(
		f"{aso['name']};{aso['version']};{aso['subVersion']};{aso['language']};{aso['architecture']}"
		for aso in backend.auditSoftware_getHashes()
	)

	for aso in backend.auditSoftwareOnClient_getHashes():
		ident = f"{aso['name']};{aso['version']};{aso['subVersion']};{aso['language']};{aso['architecture']}"
		if ident not in idents:
			logger.info("Deleting audit software on client '%s'", ident)
			backend.auditSoftwareOnClient_delete(
				aso["name"],
				aso["version"],
				aso["subVersion"],
				aso["language"],
				aso["architecture"],
				aso["clientId"],
			)
