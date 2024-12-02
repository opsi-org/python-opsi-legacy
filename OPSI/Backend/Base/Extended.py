# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Extended backends.

They provide extended functionality.
"""

from __future__ import absolute_import

import collections
import copy
import inspect
import random
import typing  # This is needed for dynamic loading  # noqa: F401
import warnings
from types import MethodType
from typing import (  # This is needed for dynamic loading  # noqa: F401
	Any,
	Generator,
	List,
)

import opsicommon  # This is needed for dynamic loading  # noqa: F401
from opsicommon.logging import get_logger

from OPSI.Exceptions import *  # This is needed for dynamic loading  # noqa: F403
from OPSI.Object import *  # This is needed for dynamic loading  # noqa: F403
from OPSI.Types import *  # This is needed for dynamic loading  # noqa: F403
from OPSI.Util import timestamp

from .Backend import Backend

logger = get_logger("opsi.general")


__all__ = (
	"ExtendedBackend",
	"ExtendedConfigDataBackend",
)


def get_function_signature_and_args(function):
	"""
	Inspects `function` and returns the function signature and arguments.

	:type method: func
	:rtype: (str, str)
	"""
	sig = (
		str(inspect.signature(function)).replace("(self, ", "(").replace("(self)", "()")
	)
	sig = sig.replace("NoneType", "None")
	spec = inspect.getfullargspec(function)
	args_ = [f"{arg}={arg}" for arg in spec.args if arg != "self"]
	if spec.varargs:
		args_.append(f"*{spec.varargs}")
	if spec.varkw:
		args_.append(f"**{spec.varkw}")
	return sig, ", ".join(args_)


class ExtendedBackend(Backend):
	"""
	Extending an backend with additional functionality.
	"""

	def __init__(self, backend, overwrite=True, **kwargs):
		"""
		Constructor.

		:param backend: Instance of the backend to extend.
		:param overwrite: Overwriting the public methods of the backend.
		"""
		Backend.__init__(self, **kwargs)
		self._backend = backend
		if self._context is self:
			logger.info("Setting context to backend %s", self._context)
			self._context = self._backend
		self._overwrite = forceBool(overwrite)  # noqa: F405
		self._createInstanceMethods()

	def _createInstanceMethods(self):
		logger.debug("%s is creating instance methods", self.__class__.__name__)
		for _, functionRef in inspect.getmembers(self._backend, inspect.ismethod):
			methodName = functionRef.__name__
			if getattr(functionRef, "no_export", False):
				continue
			if methodName.startswith("_"):
				# Not a public method
				continue

			logger.trace(
				"Found public %s method %s",
				self._backend.__class__.__name__,
				methodName,
			)
			if hasattr(self, methodName):
				if self._overwrite:
					logger.debug(
						"%s: overwriting method %s of backend instance %s",
						self.__class__.__name__,
						methodName,
						self._backend,
					)
					continue
				logger.debug(
					"%s: not overwriting method %s of backend instance %s",
					self.__class__.__name__,
					methodName,
					self._backend,
				)

			sig, arg = get_function_signature_and_args(functionRef)
			sig = "(self)" if sig == "()" else f"(self, {sig[1:]}"

			exec_locals: dict[str, object] = {}
			with warnings.catch_warnings():
				exec(
					f'def {methodName}{sig}: return self._executeMethod("{methodName}", {arg})',
					None,
					locals,
				)

			new_function = exec_locals[methodName]
			if getattr(functionRef, "deprecated", False):
				new_function.deprecated = functionRef.deprecated
			if getattr(functionRef, "alternative_method", None):
				new_function.alternative_method = functionRef.alternative_method
			if functionRef.__doc__:
				new_function.__doc__ = functionRef.__doc__
			setattr(self, methodName, MethodType(new_function, self))

	def _executeMethod(self, methodName, **kwargs):
		logger.debug(
			"ExtendedBackend %s: executing %s on backend %s",
			self,
			methodName,
			self._backend,
		)
		meth = getattr(self._backend, methodName)
		return meth(**kwargs)

	def _get_backend_dispatcher(self):
		from OPSI.Backend.Manager.Dispatcher import (
			BackendDispatcher,
		)

		backend = self
		while backend:
			if isinstance(backend, BackendDispatcher):
				return backend
			backend = getattr(backend, "_backend", None)
		return None

	def backend_info(self):
		if self._backend:
			return self._backend.backend_info()
		return Backend.backend_info(self)

	def backend_setOptions(self, options):
		"""
		Set options on ``self`` and the extended backend.

		:type options: dict
		"""
		Backend.backend_setOptions(self, options)
		if self._backend:
			self._backend.backend_setOptions(options)

	def backend_getOptions(self):
		"""
		Get options from the current and the extended backend.

		:rtype: dict
		"""
		options = Backend.backend_getOptions(self)
		if self._backend:
			options.update(self._backend.backend_getOptions())
		return options

	def backend_exit(self):
		if self._backend:
			logger.debug("Calling backend_exit() on backend %s", self._backend)
			self._backend.backend_exit()


class ExtendedConfigDataBackend(ExtendedBackend):
	option_defaults = {
		**Backend.option_defaults,
		**{
			"addProductOnClientDefaults": False,
			"addProductPropertyStateDefaults": False,
			"addConfigStateDefaults": False,
			"deleteConfigStateIfDefault": False,
			"returnObjectsOnUpdateAndCreate": False,
			"addDependentProductOnClients": False,
			"processProductOnClientSequence": False,
		},
	}

	def __init__(self, configDataBackend, overwrite=True, **kwargs):
		ExtendedBackend.__init__(self, configDataBackend, overwrite=overwrite, **kwargs)
		self._auditHardwareConfig = {}

		if hasattr(self._backend, "auditHardware_getConfig"):
			ahwconf = self._backend.auditHardware_getConfig()
			AuditHardware.setHardwareConfig(ahwconf)  # noqa: F405
			AuditHardwareOnHost.setHardwareConfig(ahwconf)  # noqa: F405
			for config in ahwconf:
				hwClass = config["Class"]["Opsi"]
				self._auditHardwareConfig[hwClass] = {}
				for value in config["Values"]:
					self._auditHardwareConfig[hwClass][value["Opsi"]] = {
						"Type": value["Type"],
						"Scope": value["Scope"],
					}

	def __repr__(self):
		return f"<{self.__class__.__name__}(configDataBackend={self._backend})>"

	def host_getIdents(self, returnType="unicode", **filter):
		return [
			host.getIdent(returnType)
			for host in self.host_getObjects(attributes=["id"], **filter)
		]

	def config_getIdents(self, returnType="unicode", **filter):
		return [
			config.getIdent(returnType)
			for config in self.config_getObjects(attributes=["id"], **filter)
		]

	def configState_getIdents(self, returnType="unicode", **filter):
		return [
			configState.getIdent(returnType)
			for configState in self.configState_getObjects(
				attributes=["configId", "objectId"], **filter
			)
		]

	def product_getIdents(self, returnType="unicode", **filter):
		return [
			product.getIdent(returnType)
			for product in self.product_getObjects(attributes=["id"], **filter)
		]

	def productProperty_getIdents(self, returnType="unicode", **filter):
		return [
			productProperty.getIdent(returnType)
			for productProperty in self.productProperty_getObjects(
				attributes=[
					"productId",
					"productVersion",
					"packageVersion",
					"propertyId",
				],
				**filter,
			)
		]

	def productDependency_getIdents(self, returnType="unicode", **filter):
		return [
			productDependency.getIdent(returnType)
			for productDependency in self.productDependency_getObjects(
				attributes=[
					"productId",
					"productVersion",
					"packageVersion",
					"productAction",
					"requiredProductId",
				],
				**filter,
			)
		]

	def productOnDepot_getIdents(self, returnType="unicode", **filter):
		return [
			productOnDepot.getIdent(returnType)
			for productOnDepot in self.productOnDepot_getObjects(
				attributes=["productId", "productType", "depotId"], **filter
			)
		]

	def productOnClient_getIdents(self, returnType="unicode", **filter):
		return [
			productOnClient.getIdent(returnType)
			for productOnClient in self.productOnClient_getObjects(
				attributes=["productId", "productType", "clientId"], **filter
			)
		]

	def productPropertyState_getIdents(self, returnType="unicode", **filter):
		return [
			productPropertyState.getIdent(returnType)
			for productPropertyState in self.productPropertyState_getObjects(
				attributes=["productId", "propertyId", "objectId"], **filter
			)
		]

	def group_getIdents(self, returnType="unicode", **filter):
		return [
			group.getIdent(returnType)
			for group in self.group_getObjects(attributes=["id"], **filter)
		]

	def objectToGroup_getIdents(self, returnType="unicode", **filter):
		return [
			objectToGroup.getIdent(returnType)
			for objectToGroup in self.objectToGroup_getObjects(
				attributes=["groupType", "groupId", "objectId"], **filter
			)
		]

	def licenseContract_getIdents(self, returnType="unicode", **filter):
		return [
			licenseContract.getIdent(returnType)
			for licenseContract in self.licenseContract_getObjects(
				attributes=["id"], **filter
			)
		]

	def softwareLicense_getIdents(self, returnType="unicode", **filter):
		return [
			softwareLicense.getIdent(returnType)
			for softwareLicense in self.softwareLicense_getObjects(
				attributes=["id", "licenseContractId"], **filter
			)
		]

	def licensePool_getIdents(self, returnType="unicode", **filter):
		return [
			licensePool.getIdent(returnType)
			for licensePool in self.licensePool_getObjects(attributes=["id"], **filter)
		]

	def softwareLicenseToLicensePool_getIdents(self, returnType="unicode", **filter):
		return [
			softwareLicenseToLicensePool.getIdent(returnType)
			for softwareLicenseToLicensePool in self.softwareLicenseToLicensePool_getObjects(
				attributes=["softwareLicenseId", "licensePoolId"], **filter
			)
		]

	def licenseOnClient_getIdents(self, returnType="unicode", **filter):
		return [
			licenseOnClient.getIdent(returnType)
			for licenseOnClient in self.licenseOnClient_getObjects(
				attributes=["softwareLicenseId", "licensePoolId", "clientId"], **filter
			)
		]

	def auditSoftware_getIdents(self, returnType="unicode", **filter):
		return [
			auditSoftware.getIdent(returnType)
			for auditSoftware in self.auditSoftware_getObjects(
				attributes=[
					"name",
					"version",
					"subVersion",
					"language",
					"architecture",
				],
				**filter,
			)
		]

	def auditSoftwareToLicensePool_getIdents(self, returnType="unicode", **filter):
		return [
			auditSoftwareToLicensePool.getIdent(returnType)
			for auditSoftwareToLicensePool in self.auditSoftwareToLicensePool_getObjects(
				attributes=[
					"name",
					"version",
					"subVersion",
					"language",
					"architecture",
					"licensePoolId",
				],
				**filter,
			)
		]

	def auditSoftwareOnClient_getIdents(self, returnType="unicode", **filter):
		return [
			auditSoftwareOnClient.getIdent(returnType)
			for auditSoftwareOnClient in self.auditSoftwareOnClient_getObjects(
				attributes=[
					"name",
					"version",
					"subVersion",
					"language",
					"architecture",
					"clientId",
				],
				**filter,
			)
		]

	def auditHardware_getIdents(self, returnType="unicode", **filter):
		return [
			auditHardware.getIdent(returnType)
			for auditHardware in self.auditHardware_getObjects(**filter)
		]

	def auditHardwareOnHost_getIdents(self, returnType="unicode", **filter):
		return [
			auditHardwareOnHost.getIdent(returnType)
			for auditHardwareOnHost in self.auditHardwareOnHost_getObjects(**filter)
		]

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_createObjects(self, hosts):
		forcedHosts = forceObjectClassList(hosts, Host)  # noqa: F405
		for host in forcedHosts:
			logger.info("Creating host '%s'", host)
			self._backend.host_insertObject(host)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.host_getObjects(id=[host.id for host in forcedHosts])
		return []

	def host_updateObjects(self, hosts):
		def updateOrInsert(host):
			logger.info("Updating host '%s'", host)
			if self.host_getIdents(id=host.id):
				self._backend.host_updateObject(host)
			else:
				logger.info("Host %s does not exist, creating", host)
				self._backend.host_insertObject(host)

		hostList = forceObjectClassList(hosts, Host)  # noqa: F405
		for host in hostList:
			updateOrInsert(host)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.host_getObjects(id=[host.id for host in hostList])
		return []

	def host_renameOpsiClient(self, id, newId):
		id = forceHostId(id)
		newId = forceHostId(newId)  # noqa: F405

		logger.info("Renaming client %s to %s...", id, newId)

		clients = self._backend.host_getObjects(type="OpsiClient", id=id)
		try:
			client = clients[0]
		except IndexError as err:
			raise BackendMissingDataError(  # noqa: F405
				f"Cannot rename: client '{id}' not found"
			) from err

		if self._backend.host_getObjects(id=newId):
			raise BackendError(f"Cannot rename: host '{newId}' already exists")  # noqa: F405

		logger.info("Processing group mappings...")
		objectToGroups = []
		for objectToGroup in self._backend.objectToGroup_getObjects(
			groupType="HostGroup", objectId=client.id
		):
			objectToGroup.setObjectId(newId)
			objectToGroups.append(objectToGroup)

		logger.info("Processing products on client...")
		productOnClients = []
		for productOnClient in self._backend.productOnClient_getObjects(
			clientId=client.id
		):
			productOnClient.setClientId(newId)
			productOnClients.append(productOnClient)

		logger.info("Processing product property states...")
		productPropertyStates = []
		for productPropertyState in self._backend.productPropertyState_getObjects(
			objectId=client.id
		):
			productPropertyState.setObjectId(newId)
			productPropertyStates.append(productPropertyState)

		logger.info("Processing config states...")
		configStates = []
		for configState in self._backend.configState_getObjects(objectId=client.id):
			configState.setObjectId(newId)
			configStates.append(configState)

		logger.info("Processing software audit data...")
		auditSoftwareOnClients = []
		for auditSoftwareOnClient in self._backend.auditSoftwareOnClient_getObjects(
			clientId=client.id
		):
			auditSoftwareOnClient.setClientId(newId)
			auditSoftwareOnClients.append(auditSoftwareOnClient)

		logger.info("Processing hardware audit data...")
		auditHardwareOnHosts = []
		for auditHardwareOnHost in self._backend.auditHardwareOnHost_getObjects(
			hostId=client.id
		):
			auditHardwareOnHost.setHostId(newId)
			auditHardwareOnHosts.append(auditHardwareOnHost)

		logger.info("Processing license data...")
		licenseOnClients = []
		for licenseOnClient in self._backend.licenseOnClient_getObjects(
			clientId=client.id
		):
			licenseOnClient.setClientId(newId)
			licenseOnClients.append(licenseOnClient)

		logger.info("Processing software licenses...")
		softwareLicenses = []
		for softwareLicense in self._backend.softwareLicense_getObjects(
			boundToHost=client.id
		):
			softwareLicense.setBoundToHost(newId)
			softwareLicenses.append(softwareLicense)

		logger.debug("Deleting client %s", client)
		self._backend.host_deleteObjects([client])

		logger.info("Updating client %s...", client.id)
		client.setId(newId)
		self.host_createObjects([client])

		if objectToGroups:
			logger.info("Updating group mappings...")
			self.objectToGroup_createObjects(objectToGroups)
		if productOnClients:
			logger.info("Updating products on client...")
			self.productOnClient_createObjects(productOnClients)
		if productPropertyStates:
			logger.info("Updating product property states...")
			self.productPropertyState_createObjects(productPropertyStates)
		if configStates:
			logger.info("Updating config states...")
			self.configState_createObjects(configStates)
		if auditSoftwareOnClients:
			logger.info("Updating software audit data...")
			self.auditSoftwareOnClient_createObjects(auditSoftwareOnClients)
		if auditHardwareOnHosts:
			logger.info("Updating hardware audit data...")
			self.auditHardwareOnHost_createObjects(auditHardwareOnHosts)
		if licenseOnClients:
			logger.info("Updating license data...")
			self.licenseOnClient_createObjects(licenseOnClients)
		if softwareLicenses:
			logger.info("Updating software licenses...")
			self.softwareLicense_createObjects(softwareLicenses)

	def host_renameOpsiDepotserver(self, oldId, newId):
		"""
		Rename OpsiDepotserver with id `oldId` to `newId`.

		References to the old id will be changed aswell.

		:raises BackendMissingDataError: If no depot `oldId` is found.
		:raises BackendError: If depot `newId` already exists.
		:param oldId: ID of the server to change.
		:type oldId: str
		:param oldId: New ID.
		:type newId: str
		"""
		oldId = forceHostId(oldId)
		newId = forceHostId(newId)
		oldHostname = oldId.split(".")[0]
		newHostname = newId.split(".")[0]

		depots = self._backend.host_getObjects(type="OpsiDepotserver", id=oldId)
		try:
			depot = depots[0]
		except IndexError as err:
			raise BackendMissingDataError(
				f"Cannot rename: depot '{oldId}' not found"
			) from err

		if self._backend.host_getObjects(id=newId):
			raise BackendError(f"Cannot rename: host '{newId}' already exists")

		logger.info("Renaming depot %s to %s", oldId, newId)

		logger.info("Processing ProductOnDepots...")
		productOnDepots = []
		for productOnDepot in self._backend.productOnDepot_getObjects(depotId=oldId):
			productOnDepot.setDepotId(newId)
			productOnDepots.append(productOnDepot)

		def replaceServerId(someList):
			"""
			Replaces occurrences of `oldId` with `newId` in `someList`.

			If someList is the wrong type or no change was made `False`
			will be returned.

			:type someList: list
			:returns: `True` if a change was made.
			:rtype: bool
			"""
			try:
				someList.remove(oldId)
				someList.append(newId)
				return True
			except (ValueError, AttributeError):
				return False

		logger.info("Processing ProductProperties...")
		modifiedProductProperties = []
		for productProperty in self._backend.productProperty_getObjects():
			changed = replaceServerId(productProperty.possibleValues)
			changed = replaceServerId(productProperty.defaultValues) or changed

			if changed:
				modifiedProductProperties.append(productProperty)

		if modifiedProductProperties:
			logger.info("Updating ProductProperties...")
			self.productProperty_updateObjects(modifiedProductProperties)

		logger.info("Processing ProductPropertyStates...")
		productPropertyStates = []
		for productPropertyState in self._backend.productPropertyState_getObjects(
			objectId=oldId
		):
			productPropertyState.setObjectId(newId)
			replaceServerId(productPropertyState.values)
			productPropertyStates.append(productPropertyState)

		logger.info("Processing Configs...")
		modifiedConfigs = []
		for config in self._backend.config_getObjects():
			changed = replaceServerId(config.possibleValues)
			changed = replaceServerId(config.defaultValues) or changed

			if changed:
				modifiedConfigs.append(config)

		if modifiedConfigs:
			logger.info("Updating Configs...")
			self.config_updateObjects(modifiedConfigs)

		logger.info("Processing ConfigStates...")
		configStates = []
		for configState in self._backend.configState_getObjects(objectId=oldId):
			configState.setObjectId(newId)
			replaceServerId(configState.values)
			configStates.append(configState)

		def changeAddress(value):
			newValue = value.replace(oldId, newId)
			newValue = newValue.replace(oldHostname, newHostname)
			logger.debug("Changed %s to %s", value, newValue)
			return newValue

		old_depot = copy.deepcopy(depot)
		if old_depot.hardwareAddress:
			# Hardware address needs to be unique
			old_depot.hardwareAddress = None
			self.host_createObjects([old_depot])

		logger.info("Updating depot and it's urls...")
		depot.setId(newId)
		if depot.repositoryRemoteUrl:
			depot.setRepositoryRemoteUrl(changeAddress(depot.repositoryRemoteUrl))
		if depot.depotRemoteUrl:
			depot.setDepotRemoteUrl(changeAddress(depot.depotRemoteUrl))
		if depot.depotWebdavUrl:
			depot.setDepotWebdavUrl(changeAddress(depot.depotWebdavUrl))
		if depot.workbenchRemoteUrl:
			depot.setWorkbenchRemoteUrl(changeAddress(depot.workbenchRemoteUrl))
		self.host_createObjects([depot])

		if productOnDepots:
			logger.info("Updating ProductOnDepots...")
			self.productOnDepot_createObjects(productOnDepots)
		if productPropertyStates:
			logger.info("Updating ProductPropertyStates...")
			self.productPropertyState_createObjects(productPropertyStates)
		if configStates:
			logger.info("Updating ConfigStates...")
			self.configState_createObjects(configStates)

		logger.info("Deleting old depot %s", old_depot)
		self._backend.host_deleteObjects([old_depot])

		def replaceOldAddress(values):
			"""
			Searches for old address in elements of `values` and
			replaces it with the new address.

			:type values: list
			:returns: `True` if an item was changed, `False` otherwise.
			:rtype: bool
			"""
			changed = False
			try:
				for i, value in enumerate(values):
					if oldId in value:
						values[i] = value.replace(oldId, newId)
						changed = True
			except TypeError:  # values probably None
				pass

			return changed

		logger.info("Processing depot assignment configs...")
		updateConfigs = []
		for config in self._backend.config_getObjects(
			id=["clientconfig.configserver.url", "clientconfig.depot.id"]
		):
			changed = replaceOldAddress(config.defaultValues)
			changed = replaceOldAddress(config.possibleValues) or changed

			if changed:
				updateConfigs.append(config)

		if updateConfigs:
			logger.info("Processing depot assignment configs...")
			self.config_updateObjects(updateConfigs)

		logger.info("Processing depot assignment config states...")
		updateConfigStates = []
		for configState in self._backend.configState_getObjects(
			configId=["clientconfig.configserver.url", "clientconfig.depot.id"]
		):
			if replaceOldAddress(configState.values):
				updateConfigStates.append(configState)

		if updateConfigStates:
			logger.info("Updating depot assignment config states...")
			self.configState_updateObjects(updateConfigStates)

		logger.info("Processing depots...")
		modifiedDepots = []
		for depot in self._backend.host_getObjects(type="OpsiDepotserver"):
			if depot.masterDepotId and depot.masterDepotId == oldId:
				depot.masterDepotId = newId
				modifiedDepots.append(depot)

		if modifiedDepots:
			logger.info("Updating depots...")
			self.host_updateObjects(modifiedDepots)

	def host_createOpsiClient(
		self,
		id,
		opsiHostKey=None,
		description=None,
		notes=None,
		hardwareAddress=None,
		ipAddress=None,
		inventoryNumber=None,
		oneTimePassword=None,
		created=None,
		lastSeen=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.host_createObjects(OpsiClient.fromHash(_hash))

	def host_createOpsiDepotserver(
		self,
		id,
		opsiHostKey=None,
		depotLocalUrl=None,
		depotRemoteUrl=None,
		depotWebdavUrl=None,
		repositoryLocalUrl=None,
		repositoryRemoteUrl=None,
		description=None,
		notes=None,
		hardwareAddress=None,
		ipAddress=None,
		inventoryNumber=None,
		networkAddress=None,
		maxBandwidth=None,
		isMasterDepot=None,
		masterDepotId=None,
		workbenchLocalUrl=None,
		workbenchRemoteUrl=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.host_createObjects(OpsiDepotserver.fromHash(_hash))

	def host_createOpsiConfigserver(
		self,
		id,
		opsiHostKey=None,
		depotLocalUrl=None,
		depotRemoteUrl=None,
		depotWebdavUrl=None,
		repositoryLocalUrl=None,
		repositoryRemoteUrl=None,
		description=None,
		notes=None,
		hardwareAddress=None,
		ipAddress=None,
		inventoryNumber=None,
		networkAddress=None,
		maxBandwidth=None,
		isMasterDepot=None,
		masterDepotId=None,
		workbenchLocalUrl=None,
		workbenchRemoteUrl=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.host_createObjects(OpsiConfigserver.fromHash(_hash))

	def host_delete(self, id):
		if id is None:
			id = []
		return self._backend.host_deleteObjects(self._backend.host_getObjects(id=id))

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_createObjects(self, configs):
		forcedConfigs = forceObjectClassList(configs, Config)
		for config in forcedConfigs:
			logger.info("Creating config '%s'", config)
			self._backend.config_insertObject(config)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.config_getObjects(
				id=[config.id for config in forcedConfigs]
			)
		return []

	def config_updateObjects(self, configs):
		forcedConfigs = forceObjectClassList(configs, Config)
		for config in forcedConfigs:
			logger.info("Updating config %s", config)
			if self.config_getIdents(id=config.id):
				self._backend.config_updateObject(config)
			else:
				logger.info("Config %s does not exist, creating", config)
				self._backend.config_insertObject(config)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.config_getObjects(
				id=[config.id for config in forcedConfigs]
			)
		return []

	def config_create(
		self,
		id,
		description=None,
		possibleValues=None,
		defaultValues=None,
		editable=None,
		multiValue=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.config_createObjects(Config.fromHash(_hash))

	def config_createUnicode(
		self,
		id,
		description=None,
		possibleValues=None,
		defaultValues=None,
		editable=None,
		multiValue=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.config_createObjects(UnicodeConfig.fromHash(_hash))

	def config_createBool(
		self,
		id,
		description=None,
		defaultValues=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.config_createObjects(BoolConfig.fromHash(_hash))

	def config_delete(self, id):
		if id is None:
			id = []
		return self._backend.config_deleteObjects(self.config_getObjects(id=id))

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_getObjects(self, attributes=[], **filter):
		"""
		Add default objects to result for objects which do not exist in backend
		"""
		# objectIds can only be client ids

		# Get config states from backend
		configStates = self._backend.configState_getObjects(attributes, **filter)

		if not self._options["addConfigStateDefaults"]:
			return configStates

		# Create data structure for config states to find missing ones
		css = {}
		for cs in self._backend.configState_getObjects(
			attributes=["objectId", "configId"],
			objectId=filter.get("objectId", []),
			configId=filter.get("configId", []),
		):
			try:
				css[cs.objectId].append(cs.configId)
			except KeyError:
				css[cs.objectId] = [cs.configId]

		clientIds = self.host_getIdents(id=filter.get("objectId"), returnType="unicode")
		# Create missing config states
		for config in self._backend.config_getObjects(id=filter.get("configId")):
			logger.debug("Default values for %s: %s", config.id, config.defaultValues)
			for clientId in clientIds:
				if config.id not in css.get(clientId, []):
					# Config state does not exist for client => create default
					cf = ConfigState(
						configId=config.id,
						objectId=clientId,
						values=config.defaultValues,
					)
					cf.setGeneratedDefault(True)
					configStates.append(cf)

		return configStates

	def _configStateMatchesDefault(self, configState):
		isDefault = False
		configs = self._backend.config_getObjects(
			attributes=["defaultValues"], id=configState.configId
		)
		if (
			configs
			and not configs[0].defaultValues
			and (len(configs[0].defaultValues) == len(configState.values))
		):
			isDefault = True
			for val in configState.values:
				if val not in configs[0].defaultValues:
					isDefault = False
					break
		return isDefault

	def _configState_checkValid(self, configState):
		if configState.configId == "clientconfig.depot.id":
			if not configState.values or not configState.values[0]:
				raise ValueError("No valid depot id given")
			depotId = forceHostId(configState.values[0])
			if not self.host_getIdents(
				type="OpsiDepotserver", id=depotId, isMasterDepot=True
			):
				raise ValueError(
					f"Depot '{depotId}' does not exist or is not a master depot"
				)

	def configState_insertObject(self, configState):
		if self._options[
			"deleteConfigStateIfDefault"
		] and self._configStateMatchesDefault(configState):
			# Do not insert configStates which match the default
			logger.debug(
				"Not inserting configState %s, because it does not differ from defaults",
				configState,
			)
			return

		configState = forceObjectClass(configState, ConfigState)
		self._configState_checkValid(configState)
		self._backend.configState_insertObject(configState)

	def configState_updateObject(self, configState):
		if self._options[
			"deleteConfigStateIfDefault"
		] and self._configStateMatchesDefault(configState):
			# Do not update configStates which match the default
			logger.debug(
				"Deleting configState %s, because it does not differ from defaults",
				configState,
			)
			return self._backend.configState_deleteObjects(configState)

		configState = forceObjectClass(configState, ConfigState)
		self._configState_checkValid(configState)
		return self._backend.configState_updateObject(configState)

	def configState_createObjects(self, configStates):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for configState in forceObjectClassList(configStates, ConfigState):
			logger.info("Creating configState '%s'", configState)
			self.configState_insertObject(configState)
			if returnObjects:
				result.extend(
					self._backend.configState_getObjects(
						configId=configState.configId, objectId=configState.objectId
					)
				)

		return result

	def configState_updateObjects(self, configStates):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for configState in forceObjectClassList(configStates, ConfigState):
			logger.info("Updating configState %s", configState)
			if self.configState_getIdents(
				configId=configState.configId, objectId=configState.objectId
			):
				self.configState_updateObject(configState)
			else:
				logger.info("ConfigState %s does not exist, creating", configState)
				self.configState_insertObject(configState)

			if returnObjects:
				result.extend(
					self._backend.configState_getObjects(
						configId=configState.configId, objectId=configState.objectId
					)
				)

		return result

	def configState_create(self, configId, objectId, values=None):
		_hash = locals()
		del _hash["self"]
		return self.configState_createObjects(ConfigState.fromHash(_hash))

	def configState_delete(self, configId, objectId):
		if configId is None:
			configId = []
		if objectId is None:
			objectId = []

		return self._backend.configState_deleteObjects(
			self._backend.configState_getObjects(configId=configId, objectId=objectId)
		)

	def configState_getClientToDepotserver(
		self, depotIds=[], clientIds=[], masterOnly=True, productIds=[]
	):
		"""
		Get a mapping of client and depots.

		:param depotIds: Limit the search to the specified depot ids. \
If nothing is given all depots are taken into account.
		:type depotIds: [str, ]
		:param clientIds: Limit the search to the specified client ids. \
If nothing is given all depots are taken into account.
		:type clientIds: [str, ]
		:param masterOnly: If this is set to `True` only master depots \
are taken into account.
		:type masterOnly: bool
		:param productIds: Limit the data to the specified products if \
alternative depots are to be taken into account.
		:type productIds: [str,]
		:return: A list of dicts containing the keys `depotId` and \
`clientId` that belong to each other. If alternative depots are taken \
into the IDs of these depots are to be found in the list behind \
`alternativeDepotIds`. The key does always exist but may be empty.
		:rtype: [{"depotId": str, "alternativeDepotIds": [str, ], "clientId": str},]
		"""
		depotIds = forceHostIdList(depotIds)
		productIds = forceProductIdList(productIds)

		depotIds = self.host_getIdents(type="OpsiDepotserver", id=depotIds)
		if not depotIds:
			return []
		depotIds = set(depotIds)

		clientIds = forceHostIdList(clientIds)
		clientIds = self.host_getIdents(type="OpsiClient", id=clientIds)
		if not clientIds:
			return []

		usedDepotIds = set()
		result = []
		addConfigStateDefaults = self.backend_getOptions().get(
			"addConfigStateDefaults", False
		)
		try:
			logger.debug("Calling backend_setOptions on %s", self)
			self.backend_setOptions({"addConfigStateDefaults": True})
			for configState in self.configState_getObjects(
				configId="clientconfig.depot.id", objectId=clientIds
			):
				try:
					depotId = configState.values[0]
					if not depotId:
						raise IndexError("Missing value")
				except IndexError:
					logger.error(
						"No depot server configured for client %s", configState.objectId
					)
					continue

				if depotId not in depotIds:
					continue
				usedDepotIds.add(depotId)

				result.append(
					{
						"depotId": depotId,
						"clientId": configState.objectId,
						"alternativeDepotIds": [],
					}
				)
		finally:
			self.backend_setOptions({"addConfigStateDefaults": addConfigStateDefaults})

		if forceBool(masterOnly):
			return result

		poDepotsByDepotIdAndProductId = {}
		for pod in self.productOnDepot_getObjects(productId=productIds):
			try:
				poDepotsByDepotIdAndProductId[pod.depotId][pod.productId] = pod
			except KeyError:
				poDepotsByDepotIdAndProductId[pod.depotId] = {pod.productId: pod}

		pHash = {}
		for (
			depotId,
			productOnDepotsByProductId,
		) in poDepotsByDepotIdAndProductId.items():
			productString = [
				f"|{productId};{productOnDepotsByProductId[productId].productVersion};{productOnDepotsByProductId[productId].packageVersion}"
				for productId in sorted(productOnDepotsByProductId.keys())
			]

			pHash[depotId] = "".join(productString)

		for usedDepotId in usedDepotIds:
			pString = pHash.get(usedDepotId, "")
			alternativeDepotIds = [
				depotId
				for (depotId, ps) in pHash.items()
				if depotId != usedDepotId and pString == ps
			]

			for i, element in enumerate(result):
				if element["depotId"] == usedDepotId:
					result[i]["alternativeDepotIds"] = alternativeDepotIds

		return result

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_createObjects(self, products):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for product in forceObjectClassList(products, Product):
			logger.info("Creating product %s", product)
			self._backend.product_insertObject(product)
			if returnObjects:
				result.extend(
					self._backend.product_getObjects(
						id=product.id,
						productVersion=product.productVersion,
						packageVersion=product.packageVersion,
					)
				)

		return result

	def product_updateObjects(self, products):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for product in forceObjectClassList(products, Product):
			logger.info("Updating product %s", product)
			if self.product_getIdents(
				id=product.id,
				productVersion=product.productVersion,
				packageVersion=product.packageVersion,
			):
				self._backend.product_updateObject(product)
			else:
				logger.info("Product %s does not exist, creating", product)
				self._backend.product_insertObject(product)

			if returnObjects:
				result.extend(
					self._backend.product_getObjects(
						id=product.id,
						productVersion=product.productVersion,
						packageVersion=product.packageVersion,
					)
				)

		return result

	def product_createLocalboot(
		self,
		id,
		productVersion,
		packageVersion,
		name=None,
		licenseRequired=None,
		setupScript=None,
		uninstallScript=None,
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=None,
		description=None,
		advice=None,
		changelog=None,
		productClassIds=None,
		windowsSoftwareIds=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.product_createObjects(LocalbootProduct.fromHash(_hash))

	def product_createNetboot(
		self,
		id,
		productVersion,
		packageVersion,
		name=None,
		licenseRequired=None,
		setupScript=None,
		uninstallScript=None,
		updateScript=None,
		alwaysScript=None,
		onceScript=None,
		priority=None,
		description=None,
		advice=None,
		changelog=None,
		productClassIds=None,
		windowsSoftwareIds=None,
		pxeConfigTemplate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.product_createObjects(NetbootProduct.fromHash(_hash))

	def product_delete(self, productId, productVersion, packageVersion):
		if productId is None:
			productId = []
		if productVersion is None:
			productVersion = []
		if packageVersion is None:
			packageVersion = []

		return self._backend.product_deleteObjects(
			self._backend.product_getObjects(
				id=productId,
				productVersion=productVersion,
				packageVersion=packageVersion,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _adjustProductPropertyStates(self, productProperty):
		"""
		A productProperty was created or updated
		check if the current productPropertyStates are valid
		"""
		if productProperty.editable or not productProperty.possibleValues:
			return

		# Check if productPropertyStates are possible
		depotIds = {
			productOnDepot.depotId
			for productOnDepot in self.productOnDepot_getObjects(
				productId=productProperty.productId,
				productVersion=productProperty.productVersion,
				packageVersion=productProperty.packageVersion,
			)
		}

		if not depotIds:
			return

		# Get depot to client assignment
		objectIds = depotIds.union(
			{
				clientToDepot["clientId"]
				for clientToDepot in self.configState_getClientToDepotserver(
					depotIds=depotIds
				)
			}
		)

		deleteProductPropertyStates = []
		updateProductPropertyStates = []
		for productPropertyState in self.productPropertyState_getObjects(
			objectId=objectIds,
			productId=productProperty.productId,
			propertyId=productProperty.propertyId,
		):
			changed = False
			newValues = []
			for val in productPropertyState.values:
				if val in productProperty.possibleValues:
					newValues.append(val)
					continue

				if (
					productProperty.getType() == "BoolProductProperty"
					and forceBool(val) in productProperty.possibleValues
				):
					newValues.append(forceBool(val))
					changed = True
					continue

				if productProperty.getType() == "UnicodeProductProperty":
					newValue = None
					for pv in productProperty.possibleValues:
						if forceUnicodeLower(pv) == forceUnicodeLower(val):
							newValue = pv
							break

					if newValue:
						newValues.append(newValue)
						changed = True
						continue

				changed = True

			if changed:
				if not newValues:
					logger.debug(
						"Properties changed: marking productPropertyState %s for deletion",
						productPropertyState,
					)
					deleteProductPropertyStates.append(productPropertyState)
				else:
					productPropertyState.setValues(newValues)
					logger.debug(
						"Properties changed: marking productPropertyState %s for update",
						productPropertyState,
					)
					updateProductPropertyStates.append(productPropertyState)

		if deleteProductPropertyStates:
			self.productPropertyState_deleteObjects(deleteProductPropertyStates)
		if updateProductPropertyStates:
			self.productPropertyState_updateObjects(updateProductPropertyStates)

	def productProperty_createObjects(self, productProperties):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			logger.info("Creating productProperty %s", productProperty)
			self._backend.productProperty_insertObject(productProperty)

			if returnObjects:
				result.extend(
					self._backend.productProperty_getObjects(
						productId=productProperty.productId,
						productVersion=productProperty.productVersion,
						packageVersion=productProperty.packageVersion,
						propertyId=productProperty.propertyId,
					)
				)

		return result

	def productProperty_updateObjects(self, productProperties):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			logger.info("Creating productProperty %s", productProperty)
			if self.productProperty_getIdents(
				productId=productProperty.productId,
				productVersion=productProperty.productVersion,
				packageVersion=productProperty.packageVersion,
				propertyId=productProperty.propertyId,
			):
				self._backend.productProperty_updateObject(productProperty)
			else:
				logger.info(
					"ProductProperty %s does not exist, creating", productProperty
				)
				self._backend.productProperty_insertObject(productProperty)

			if returnObjects:
				result.extend(
					self._backend.productProperty_getObjects(
						productId=productProperty.productId,
						productVersion=productProperty.productVersion,
						packageVersion=productProperty.packageVersion,
						propertyId=productProperty.propertyId,
					)
				)

		return result

	def productProperty_create(
		self,
		productId,
		productVersion,
		packageVersion,
		propertyId,
		description=None,
		possibleValues=None,
		defaultValues=None,
		editable=None,
		multiValue=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productProperty_createObjects(ProductProperty.fromHash(_hash))

	def productProperty_createUnicode(
		self,
		productId,
		productVersion,
		packageVersion,
		propertyId,
		description=None,
		possibleValues=None,
		defaultValues=None,
		editable=None,
		multiValue=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productProperty_createObjects(
			UnicodeProductProperty.fromHash(_hash)
		)

	def productProperty_createBool(
		self,
		productId,
		productVersion,
		packageVersion,
		propertyId,
		description=None,
		defaultValues=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productProperty_createObjects(BoolProductProperty.fromHash(_hash))

	def productProperty_delete(
		self, productId, productVersion, packageVersion, propertyId
	):
		if productId is None:
			productId = []
		if productVersion is None:
			productVersion = []
		if packageVersion is None:
			packageVersion = []
		if propertyId is None:
			propertyId = []

		return self._backend.productProperty_deleteObjects(
			self._backend.productProperty_getObjects(
				productId=productId,
				productVersion=productVersion,
				packageVersion=packageVersion,
				propertyId=propertyId,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                       -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_createObjects(self, productDependencies):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for productDependency in forceObjectClassList(
			productDependencies, ProductDependency
		):
			logger.info("Creating productDependency %s", productDependency)
			self._backend.productDependency_insertObject(productDependency)

			if returnObjects:
				result.extend(
					self._backend.productDependency_getObjects(
						productId=productDependency.productId,
						productVersion=productDependency.productVersion,
						packageVersion=productDependency.packageVersion,
						productAction=productDependency.productAction,
						requiredProductId=productDependency.requiredProductId,
					)
				)

		return result

	def productDependency_updateObjects(self, productDependencies):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for productDependency in forceObjectClassList(
			productDependencies, ProductDependency
		):
			logger.info("Updating productDependency %s", productDependency)
			if self.productDependency_getIdents(
				productId=productDependency.productId,
				productVersion=productDependency.productVersion,
				packageVersion=productDependency.packageVersion,
				productAction=productDependency.productAction,
				requiredProductId=productDependency.requiredProductId,
			):
				self._backend.productDependency_updateObject(productDependency)
			else:
				logger.info(
					"ProductDependency %s does not exist, creating", productDependency
				)
				self._backend.productDependency_insertObject(productDependency)

			if returnObjects:
				result.extend(
					self._backend.productDependency_getObjects(
						productId=productDependency.productId,
						productVersion=productDependency.productVersion,
						packageVersion=productDependency.packageVersion,
						productAction=productDependency.productAction,
						requiredProductId=productDependency.requiredProductId,
					)
				)

		return result

	def productDependency_create(
		self,
		productId,
		productVersion,
		packageVersion,
		productAction,
		requiredProductId,
		requiredProductVersion=None,
		requiredPackageVersion=None,
		requiredAction=None,
		requiredInstallationStatus=None,
		requirementType=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productDependency_createObjects(ProductDependency.fromHash(_hash))

	def productDependency_delete(
		self,
		productId,
		productVersion,
		packageVersion,
		productAction,
		requiredProductId,
	):
		if productId is None:
			productId = []
		if productVersion is None:
			productVersion = []
		if packageVersion is None:
			packageVersion = []
		if productAction is None:
			productAction = []
		if requiredProductId is None:
			requiredProductId = []

		return self._backend.productDependency_deleteObjects(
			self._backend.productDependency_getObjects(
				productId=productId,
				productVersion=productVersion,
				packageVersion=packageVersion,
				productAction=productAction,
				requiredProductId=requiredProductId,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		"""
		If productOnDepot exits (same productId, same depotId, different version)
		then update existing productOnDepot instead of creating a new one
		"""
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		currentProductOnDepots = self._backend.productOnDepot_getObjects(
			productId=productOnDepot.productId, depotId=productOnDepot.depotId
		)

		if currentProductOnDepots:
			currentProductOnDepot = currentProductOnDepots[0]
			logger.info(
				"Updating productOnDepot %s instead of creating a new one",
				currentProductOnDepot,
			)
			currentProductOnDepot.update(productOnDepot)
			self._backend.productOnDepot_insertObject(currentProductOnDepot)
		else:
			self._backend.productOnDepot_insertObject(productOnDepot)

	def productOnDepot_createObjects(self, productOnDepots):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for productOnDepot in forceObjectClassList(productOnDepots, ProductOnDepot):
			logger.info("Creating productOnDepot %s", productOnDepot.toHash())
			self.productOnDepot_insertObject(productOnDepot)

			if returnObjects:
				result.extend(
					self._backend.productOnDepot_getObjects(
						productId=productOnDepot.productId,
						depotId=productOnDepot.depotId,
					)
				)

		return result

	def productOnDepot_updateObjects(self, productOnDepots):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		productOnDepots = forceObjectClassList(productOnDepots, ProductOnDepot)
		for productOnDepot in productOnDepots:
			logger.info("Updating productOnDepot '%s'", productOnDepot)
			if self.productOnDepot_getIdents(
				productId=productOnDepot.productId,
				productType=productOnDepot.productType,
				productVersion=productOnDepot.productVersion,
				packageVersion=productOnDepot.packageVersion,
				depotId=productOnDepot.depotId,
			):
				self._backend.productOnDepot_updateObject(productOnDepot)
			else:
				logger.info(
					"ProductOnDepot %s does not exist, creating", productOnDepot
				)
				self.productOnDepot_insertObject(productOnDepot)

			if returnObjects:
				result.extend(
					self._backend.productOnDepot_getObjects(
						productId=productOnDepot.productId,
						depotId=productOnDepot.depotId,
					)
				)

		return result

	def productOnDepot_create(
		self,
		productId,
		productType,
		productVersion,
		packageVersion,
		depotId,
		locked=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productOnDepot_createObjects(ProductOnDepot.fromHash(_hash))

	def productOnDepot_deleteObjects(self, productOnDepots):
		productOnDepots = forceObjectClassList(productOnDepots, ProductOnDepot)
		products = {}
		for productOnDepot in productOnDepots:
			if productOnDepot.productId not in products:
				products[productOnDepot.productId] = {}
			if productOnDepot.productVersion not in products[productOnDepot.productId]:
				products[productOnDepot.productId][productOnDepot.productVersion] = []
			if (
				productOnDepot.packageVersion
				not in products[productOnDepot.productId][productOnDepot.productVersion]
			):
				products[productOnDepot.productId][
					productOnDepot.productVersion
				].append(productOnDepot.packageVersion)

		ret = self._backend.productOnDepot_deleteObjects(productOnDepots)

		if products:
			for productId, versions in products.items():
				for productVersion, packageVersions in versions.items():
					for packageVersion in packageVersions:
						if not self.productOnDepot_getIdents(
							productId=productId,
							productVersion=productVersion,
							packageVersion=packageVersion,
						):
							# Product not found on any depot
							self._backend.product_deleteObjects(
								self._backend.product_getObjects(
									id=[productId],
									productVersion=[productVersion],
									packageVersion=[packageVersion],
								)
							)

		return ret

	def productOnDepot_delete(
		self, productId, depotId, productVersion=None, packageVersion=None
	):
		if productId is None:
			productId = []
		if productVersion is None:
			productVersion = []
		if packageVersion is None:
			packageVersion = []
		if depotId is None:
			depotId = []
		return self._backend.productOnDepot_deleteObjects(
			self._backend.productOnDepot_getObjects(
				productId=productId,
				productVersion=productVersion,
				packageVersion=packageVersion,
				depotId=depotId,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _productOnClient_processWithFunction(self, productOnClients, function):
		productOnClientsByClient = {}
		productIds = set()
		for poc in productOnClients:
			try:
				productOnClientsByClient[poc.getClientId()].append(poc)
			except KeyError:
				productOnClientsByClient[poc.getClientId()] = [poc]

			productIds.add(poc.productId)

		depotToClients = {}
		for clientToDepot in self.configState_getClientToDepotserver(
			clientIds=(clientId for clientId in productOnClientsByClient)
		):
			try:
				depotToClients[clientToDepot["depotId"]].append(
					clientToDepot["clientId"]
				)
			except KeyError:
				depotToClients[clientToDepot["depotId"]] = [clientToDepot["clientId"]]

		productByProductIdAndVersion = collections.defaultdict(
			lambda: collections.defaultdict(dict)
		)
		for product in self._backend.product_getObjects(id=productIds):
			productByProductIdAndVersion[product.id][product.productVersion][
				product.packageVersion
			] = product

		additionalProductIds = []
		pDepsByProductIdAndVersion = collections.defaultdict(
			lambda: collections.defaultdict(lambda: collections.defaultdict(list))
		)

		def collectDependencies(
			additionalProductIds, productDependency, pDepsByProductIdAndVersion
		):
			pDepsByProductIdAndVersion[productDependency.productId][
				productDependency.productVersion
			][productDependency.packageVersion].append(productDependency)

			if (
				productDependency.requiredProductId not in productIds
				and productDependency.requiredProductId not in additionalProductIds
			):
				additionalProductIds.append(productDependency.requiredProductId)
				for productDependency2 in self._backend.productDependency_getObjects(
					productId=productDependency.requiredProductId
				):
					collectDependencies(
						additionalProductIds,
						productDependency2,
						pDepsByProductIdAndVersion,
					)

		for productDependency in self._backend.productDependency_getObjects(
			productId=productIds
		):
			collectDependencies(
				additionalProductIds, productDependency, pDepsByProductIdAndVersion
			)

		if additionalProductIds:
			for product in self._backend.product_getObjects(id=additionalProductIds):
				productByProductIdAndVersion[product.id][product.productVersion][
					product.packageVersion
				] = product

			productIds = productIds.union(additionalProductIds)

		def addDependencies(
			product,
			products,
			productDependencies,
			productByProductIdAndVersion,
			pDepsByProductIdAndVersion,
		):
			dependencies = pDepsByProductIdAndVersion[product.id][
				product.productVersion
			][product.packageVersion]
			for dep in dependencies:
				product = productByProductIdAndVersion[dep.productId][
					dep.productVersion
				][dep.packageVersion]
				if product:
					products.add(product)

					if dep not in productDependencies:
						productDependencies.add(dep)
						addDependencies(
							product,
							products,
							productDependencies,
							productByProductIdAndVersion,
							pDepsByProductIdAndVersion,
						)

		productOnClients = []
		for depotId, clientIds in depotToClients.items():
			products = set()
			productDependencies = set()

			for productOnDepot in self._backend.productOnDepot_getObjects(
				depotId=depotId, productId=productIds
			):
				product = productByProductIdAndVersion[productOnDepot.productId][
					productOnDepot.productVersion
				][productOnDepot.packageVersion]
				if product is None:
					raise BackendMissingDataError(
						f"Product '{productOnDepot.productId}', "
						f"productVersion '{productOnDepot.productVersion}', "
						f"packageVersion '{productOnDepot.packageVersion}' not found"
					)
				products.add(product)

				addDependencies(
					product,
					products,
					productDependencies,
					productByProductIdAndVersion,
					pDepsByProductIdAndVersion,
				)

			for clientId in clientIds:
				try:
					productOnClientsByClient[clientId]
				except KeyError:
					continue

				productOnClients.extend(
					function(
						productOnClients=productOnClientsByClient[clientId],
						availableProducts=products,
						productDependencies=productDependencies,
					)
				)

		return productOnClients

	def productOnClient_generateSequence(self, productOnClients):
		return productOnClients

	def productOnClient_addDependencies(self, productOnClients):
		return productOnClients

	def productOnClient_getObjects(self, attributes=[], **filter):
		"""
		possible attributes/filter-keys of ProductOnClient are:
			productId
			productType
			clientId
			targetState
			installationStatus
			actionRequest
			lastAction
			actionProgress
			actionResult
			productVersion
			packageVersion
			modificationTime

		missing ProductOnClients will be created with the following defaults:
			installationStatus = 'not_installed'
			actionRequest      = 'none'
			productVersion     = None
			packageVersion     = None
			modificationTime   = None
			targetState        = None
			lastAction         = None
			actionProgress     = None
			actionResult       = None
		"""

		pocAttributes = attributes
		pocFilter = dict(filter)

		defaultMatchesFilter = (
			(
				not filter.get("installationStatus")
				or "not_installed" in forceList(filter["installationStatus"])
			)
			and (
				not filter.get("actionRequest")
				or "none" in forceList(filter["actionRequest"])
			)
			and (
				not filter.get("productVersion")
				or None in forceList(filter["productVersion"])
			)
			and (
				not filter.get("packageVersion")
				or None in forceList(filter["packageVersion"])
			)
			and (
				not filter.get("modificationTime")
				or None in forceList(filter["modificationTime"])
			)
			and (
				not filter.get("targetState")
				or None in forceList(filter["targetState"])
			)
			and (
				not filter.get("lastAction") or None in forceList(filter["lastAction"])
			)
			and (
				not filter.get("actionProgress")
				or None in forceList(filter["actionProgress"])
			)
			and (
				not filter.get("actionResult")
				or None in forceList(filter["actionResult"])
			)
		)

		if (
			self._options["addProductOnClientDefaults"] and defaultMatchesFilter
		) or self._options["processProductOnClientSequence"]:
			# Do not filter out ProductOnClients on the basis of these attributes in this case
			# If filter is kept unchanged we cannot distinguish between "missing" and "filtered" ProductOnClients
			# We also need to know installationStatus and actionRequest of every product to create sequence
			unwantedKeys = set(
				(
					"installationStatus",
					"actionRequest",
					"productVersion",
					"packageVersion",
					"modificationTime",
					"targetState",
					"lastAction",
					"actionProgress",
					"actionResult",
				)
			)
			pocFilter = {
				key: value for (key, value) in filter.items() if key not in unwantedKeys
			}

		if (
			self._options["addProductOnClientDefaults"]
			or self._options["processProductOnClientSequence"]
		) and attributes:
			# In this case we definetly need to add the following attributes
			if "installationStatus" not in pocAttributes:
				pocAttributes.append("installationStatus")
			if "actionRequest" not in pocAttributes:
				pocAttributes.append("actionRequest")
			if "productVersion" not in pocAttributes:
				pocAttributes.append("productVersion")
			if "packageVersion" not in pocAttributes:
				pocAttributes.append("packageVersion")

		# Get product states from backend
		productOnClients = self._backend.productOnClient_getObjects(
			pocAttributes, **pocFilter
		)
		logger.debug("Got productOnClients")

		if (
			not (self._options["addProductOnClientDefaults"] and defaultMatchesFilter)
			and not self._options["processProductOnClientSequence"]
		):
			# No adjustment needed => done!
			return productOnClients

		logger.debug("Need to adjust productOnClients")

		# Create missing product states if addProductOnClientDefaults is set
		if self._options["addProductOnClientDefaults"]:
			# Get all client ids which match the filter
			clientIds = self.host_getIdents(
				id=pocFilter.get("clientId"), returnType="unicode"
			)
			logger.debug("   * got clientIds")

			# Get depot to client assignment
			depotToClients = {}
			for clientToDepot in self.configState_getClientToDepotserver(
				clientIds=clientIds
			):
				if clientToDepot["depotId"] not in depotToClients:
					depotToClients[clientToDepot["depotId"]] = []
				depotToClients[clientToDepot["depotId"]].append(
					clientToDepot["clientId"]
				)
			logger.debug("   * got depotToClients")

			productOnDepots = {}
			# Get product on depots which match the filter
			for depotId in depotToClients:
				productOnDepots[depotId] = self._backend.productOnDepot_getObjects(
					depotId=depotId,
					productId=pocFilter.get("productId"),
					productType=pocFilter.get("productType"),
					productVersion=pocFilter.get("productVersion"),
					packageVersion=pocFilter.get("packageVersion"),
				)

			logger.debug("   * got productOnDepots")

			# Create data structure for product states to find missing ones
			pocByClientIdAndProductId = {}
			for clientId in clientIds:
				pocByClientIdAndProductId[clientId] = {}
			for poc in productOnClients:
				pocByClientIdAndProductId[poc.clientId][poc.productId] = poc

			logger.debug("   * created pocByClientIdAndProductId")
			# for (clientId, pocs) in pocByClientIdAndProductId.items():
			#   for (productId, poc) in pocs.items():
			#       logger.trace("      [%s] %s: %s", clientId, productId, poc.toHash())

			for depotId, depotClientIds in depotToClients.items():
				for clientId in depotClientIds:
					for pod in productOnDepots[depotId]:
						if pod.productId not in pocByClientIdAndProductId[clientId]:
							logger.debug(
								"      - creating default productOnClient for clientId '%s', productId '%s'",
								clientId,
								pod.productId,
							)
							poc = ProductOnClient(
								productId=pod.productId,
								productType=pod.productType,
								clientId=clientId,
								installationStatus="not_installed",
								actionRequest="none",
							)
							poc.setGeneratedDefault(True)
							productOnClients.append(poc)

			logger.debug("   * created productOnClient defaults")
			# for (clientId, pocs) in pocByClientIdAndProductId.items():
			#   for (productId, poc) in pocs.items():
			#       logger.trace("      [%s] %s: %s", clientId, productId, poc.toHash())

		if (
			not self._options["addProductOnClientDefaults"]
			and not self._options["processProductOnClientSequence"]
		):
			return productOnClients

		if self._options["processProductOnClientSequence"]:
			logger.debug("   * generating productOnClient sequence")
			productOnClients = self.productOnClient_generateSequence(productOnClients)

		return [
			productOnClient
			for productOnClient in productOnClients
			if self._objectHashMatches(productOnClient.toHash(), **filter)
		]

	def _productOnClientUpdateOrCreate(self, productOnClient, update=False):
		nextProductOnClient = None
		currentProductOnClients = self._backend.productOnClient_getObjects(
			productId=productOnClient.productId, clientId=productOnClient.clientId
		)
		if currentProductOnClients:
			# If productOnClient exists
			# (same productId, same clientId, different version)
			# then update the existing instead of creating a new one
			nextProductOnClient = currentProductOnClients[0].clone()
			if update:
				nextProductOnClient.update(productOnClient, updateWithNoneValues=False)
			else:
				logger.info(
					"Updating productOnClient %s instead of creating a new one",
					nextProductOnClient,
				)
				nextProductOnClient.update(productOnClient, updateWithNoneValues=True)
		else:
			nextProductOnClient = productOnClient.clone()

		if nextProductOnClient.installationStatus:
			if nextProductOnClient.installationStatus == "installed":
				# TODO: Check if product exists?
				if (
					not nextProductOnClient.productVersion
					or not nextProductOnClient.packageVersion
				):
					clientToDepots = self.configState_getClientToDepotserver(
						clientIds=[nextProductOnClient.clientId]
					)
					if not clientToDepots:
						raise BackendError(
							f"Cannot set productInstallationStatus 'installed' for product '{nextProductOnClient.productId}'"
							f" on client '{nextProductOnClient.clientId}': product/package version not set and depot for client not found"
						)

					productOnDepots = self._backend.productOnDepot_getObjects(
						depotId=clientToDepots[0]["depotId"],
						productId=nextProductOnClient.productId,
					)
					if not productOnDepots:
						raise BackendError(
							f"Cannot set productInstallationStatus 'installed' for product '{nextProductOnClient.productId}' "
							f"on client '{nextProductOnClient.clientId}': "
							f"product/package version not set and product not found on depot '{clientToDepots[0]['depotId']}'"
						)
					nextProductOnClient.setProductVersion(
						productOnDepots[0].productVersion
					)
					nextProductOnClient.setPackageVersion(
						productOnDepots[0].packageVersion
					)
			else:
				nextProductOnClient.productVersion = None
				nextProductOnClient.packageVersion = None

		nextProductOnClient.setModificationTime(timestamp())

		return self._backend.productOnClient_insertObject(nextProductOnClient)

	def productOnClient_insertObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		return self._productOnClientUpdateOrCreate(productOnClient, update=False)

	def productOnClient_updateObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		return self._productOnClientUpdateOrCreate(productOnClient, update=True)

	def productOnClient_createObjects(self, productOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]
		result = []

		productOnClients = forceObjectClassList(productOnClients, ProductOnClient)
		if self._options["addDependentProductOnClients"]:
			productOnClients = self.productOnClient_addDependencies(productOnClients)

		for productOnClient in productOnClients:
			logger.info("Creating productOnClient %s", productOnClient)
			self.productOnClient_insertObject(productOnClient)

			if returnObjects:
				result.extend(
					self._backend.productOnClient_getObjects(
						productId=productOnClient.productId,
						clientId=productOnClient.clientId,
					)
				)

		return result

	def productOnClient_updateObjects(self, productOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]
		result = []

		productOnClients = forceObjectClassList(productOnClients, ProductOnClient)
		if self._options["addDependentProductOnClients"]:
			productOnClients = self.productOnClient_addDependencies(productOnClients)

		for productOnClient in productOnClients:
			logger.info("Updating productOnClient %s", productOnClient)
			if self.productOnClient_getIdents(
				productId=productOnClient.productId,
				productType=productOnClient.productType,
				clientId=productOnClient.clientId,
			):
				logger.info("ProductOnClient %s exists, updating", productOnClient)
				self.productOnClient_updateObject(productOnClient)
			else:
				logger.info(
					"ProductOnClient %s does not exist, creating", productOnClient
				)
				self.productOnClient_insertObject(productOnClient)

			if returnObjects:
				result.extend(
					self._backend.productOnClient_getObjects(
						productId=productOnClient.productId,
						clientId=productOnClient.clientId,
					)
				)

		return result

	def productOnClient_create(
		self,
		productId,
		productType,
		clientId,
		installationStatus=None,
		actionRequest=None,
		lastAction=None,
		actionProgress=None,
		actionResult=None,
		productVersion=None,
		packageVersion=None,
		modificationTime=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.productOnClient_createObjects(ProductOnClient.fromHash(_hash))

	def productOnClient_delete(self, productId, clientId):
		if productId is None:
			productId = []
		if clientId is None:
			clientId = []

		return self._backend.productOnClient_deleteObjects(
			self._backend.productOnClient_getObjects(
				productId=productId, clientId=clientId
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_getObjects(self, attributes=[], **filter):
		"""
		Add default objects to result for objects which do not exist in backend
		"""
		# objectIds can be depot ids or client ids

		# Get product property states
		productPropertyStates = self._backend.productPropertyState_getObjects(
			attributes, **filter
		)

		if not self._options["addProductPropertyStateDefaults"]:
			return productPropertyStates

		# Get depot to client assignment
		depotToClients = collections.defaultdict(list)
		for clientToDepot in self.configState_getClientToDepotserver(
			clientIds=filter.get("objectId", [])
		):
			depotToClients[clientToDepot["depotId"]].append(clientToDepot["clientId"])

		# Create data structure for product property states to find missing ones
		ppss = collections.defaultdict(lambda: collections.defaultdict(list))
		for pps in self._backend.productPropertyState_getObjects(
			attributes=["objectId", "productId", "propertyId"],
			objectId=filter.get("objectId", []),
			productId=filter.get("productId", []),
			propertyId=filter.get("propertyId", []),
		):
			ppss[pps.objectId][pps.productId].append(pps.propertyId)

		# Create missing product property states
		for depotId, clientIds in depotToClients.items():
			depotFilter = dict(filter)
			depotFilter["objectId"] = depotId
			for pps in self._backend.productPropertyState_getObjects(
				attributes, **depotFilter
			):
				for clientId in clientIds:
					if pps.propertyId not in ppss.get(clientId, {}).get(
						pps.productId, []
					):
						# Product property for client does not exist => add default (values of depot)
						productPropertyStates.append(
							ProductPropertyState(
								productId=pps.productId,
								propertyId=pps.propertyId,
								objectId=clientId,
								values=pps.values,
							)
						)
		return productPropertyStates

	def productPropertyState_createObjects(self, productPropertyStates):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]
		result = []
		for productPropertyState in forceObjectClassList(
			productPropertyStates, ProductPropertyState
		):
			logger.info("Updating productPropertyState %s", productPropertyState)
			self._backend.productPropertyState_insertObject(productPropertyState)

			if returnObjects:
				result.extend(
					self._backend.productPropertyState_getObjects(
						productId=productPropertyState.productId,
						objectId=productPropertyState.objectId,
						propertyId=productPropertyState.propertyId,
					)
				)

		return result

	def productPropertyState_updateObjects(self, productPropertyStates):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]
		result = []
		productPropertyStates = forceObjectClassList(
			productPropertyStates, ProductPropertyState
		)
		for productPropertyState in productPropertyStates:
			logger.info("Updating productPropertyState '%s'", productPropertyState)
			if self.productPropertyState_getIdents(
				productId=productPropertyState.productId,
				objectId=productPropertyState.objectId,
				propertyId=productPropertyState.propertyId,
			):
				self._backend.productPropertyState_updateObject(productPropertyState)
			else:
				logger.info(
					"ProductPropertyState %s does not exist, creating",
					productPropertyState,
				)
				self._backend.productPropertyState_insertObject(productPropertyState)

			if returnObjects:
				result.extend(
					self._backend.productPropertyState_getObjects(
						productId=productPropertyState.productId,
						objectId=productPropertyState.objectId,
						propertyId=productPropertyState.propertyId,
					)
				)

		return result

	def productPropertyState_create(self, productId, propertyId, objectId, values=None):
		_hash = locals()
		del _hash["self"]
		return self.productPropertyState_createObjects(
			ProductPropertyState.fromHash(_hash)
		)

	def productPropertyState_delete(self, productId, propertyId, objectId):
		if productId is None:
			productId = []
		if propertyId is None:
			propertyId = []
		if objectId is None:
			objectId = []

		return self._backend.productPropertyState_deleteObjects(
			self._backend.productPropertyState_getObjects(
				productId=productId, propertyId=propertyId, objectId=objectId
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_createObjects(self, groups):
		groups = forceObjectClassList(groups, Group)
		for group in groups:
			logger.info("Creating group '%s'", group)
			self._backend.group_insertObject(group)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.group_getObjects(id=[group.id for group in groups])
		return []

	def group_updateObjects(self, groups):
		groups = forceObjectClassList(groups, Group)
		for group in groups:
			logger.info("Updating group '%s'", group)
			if self.group_getIdents(id=group.id):
				self._backend.group_updateObject(group)
			else:
				logger.info("Group '%s' does not exist, creating", group)
				self._backend.group_insertObject(group)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.group_getObjects(id=[group.id for group in groups])
		return []

	def group_createHostGroup(
		self,
		id,
		description=None,
		notes=None,
		parentGroupId=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.group_createObjects(HostGroup.fromHash(_hash))

	def group_createProductGroup(
		self,
		id,
		description=None,
		notes=None,
		parentGroupId=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.group_createObjects(ProductGroup.fromHash(_hash))

	def group_delete(self, id):
		if id is None:
			id = []

		return self._backend.group_deleteObjects(self._backend.group_getObjects(id=id))

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_createObjects(self, objectToGroups):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
			logger.info("Creating objectToGroup %s", objectToGroup)
			self._backend.objectToGroup_insertObject(objectToGroup)

			if returnObjects:
				result.extend(
					self._backend.objectToGroup_getObjects(
						groupType=objectToGroup.groupType,
						groupId=objectToGroup.groupId,
						objectId=objectToGroup.objectId,
					)
				)
		return result

	def objectToGroup_updateObjects(self, objectToGroups):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]
		result = []
		objectToGroups = forceObjectClassList(objectToGroups, ObjectToGroup)
		for objectToGroup in objectToGroups:
			logger.info("Updating objectToGroup %s", objectToGroup)
			if self.objectToGroup_getIdents(
				groupType=objectToGroup.groupType,
				groupId=objectToGroup.groupId,
				objectId=objectToGroup.objectId,
			):
				self._backend.objectToGroup_updateObject(objectToGroup)
			else:
				logger.info("ObjectToGroup %s does not exist, creating", objectToGroup)
				self._backend.objectToGroup_insertObject(objectToGroup)

			if returnObjects:
				result.extend(
					self._backend.objectToGroup_getObjects(
						groupType=objectToGroup.groupType,
						groupId=objectToGroup.groupId,
						objectId=objectToGroup.objectId,
					)
				)

		return result

	def objectToGroup_create(self, groupType, groupId, objectId):
		_hash = locals()
		del _hash["self"]
		return self.objectToGroup_createObjects(ObjectToGroup.fromHash(_hash))

	def objectToGroup_delete(self, groupType, groupId, objectId):
		if not groupType:
			groupType = []
		if not groupId:
			groupId = []
		if not objectId:
			objectId = []

		return self._backend.objectToGroup_deleteObjects(
			self._backend.objectToGroup_getObjects(
				groupType=groupType, groupId=groupId, objectId=objectId
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_createObjects(self, licenseContracts):
		licenseContracts = forceObjectClassList(licenseContracts, LicenseContract)
		for licenseContract in licenseContracts:
			logger.info("Creating licenseContract %s", licenseContract)
			self._backend.licenseContract_insertObject(licenseContract)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.licenseContract_getObjects(
				id=[licenseContract.id for licenseContract in licenseContracts]
			)
		return []

	def licenseContract_updateObjects(self, licenseContracts):
		licenseContracts = forceObjectClassList(licenseContracts, LicenseContract)
		for licenseContract in licenseContracts:
			logger.info("Updating licenseContract '%s'", licenseContract)
			if self.licenseContract_getIdents(id=licenseContract.id):
				self._backend.licenseContract_updateObject(licenseContract)
			else:
				logger.info(
					"LicenseContract %s does not exist, creating", licenseContract
				)
				self._backend.licenseContract_insertObject(licenseContract)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.licenseContract_getObjects(
				id=[licenseContract.id for licenseContract in licenseContracts]
			)
		return []

	def licenseContract_create(
		self,
		id,
		description=None,
		notes=None,
		partner=None,
		conclusionDate=None,
		notificationDate=None,
		expirationDate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.licenseContract_createObjects(LicenseContract.fromHash(_hash))

	def licenseContract_delete(self, id):
		if id is None:
			id = []

		return self._backend.licenseContract_deleteObjects(
			self._backend.licenseContract_getObjects(id=id)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_createObjects(self, softwareLicenses):
		softwareLicenses = forceObjectClassList(softwareLicenses, SoftwareLicense)
		for softwareLicense in softwareLicenses:
			logger.info("Creating softwareLicense '%s'", softwareLicense)
			self._backend.softwareLicense_insertObject(softwareLicense)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.softwareLicense_getObjects(
				id=[softwareLicense.id for softwareLicense in softwareLicenses]
			)
		return []

	def softwareLicense_updateObjects(self, softwareLicenses):
		softwareLicenses = forceObjectClassList(softwareLicenses, SoftwareLicense)
		for softwareLicense in softwareLicenses:
			logger.info("Updating softwareLicense '%s'", softwareLicense)
			if self.softwareLicense_getIdents(id=softwareLicense.id):
				self._backend.softwareLicense_updateObject(softwareLicense)
			else:
				logger.info(
					"ProducSoftwareLicenset %s does not exist, creating",
					softwareLicense,
				)
				self._backend.softwareLicense_insertObject(softwareLicense)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.softwareLicense_getObjects(
				id=[softwareLicense.id for softwareLicense in softwareLicenses]
			)
		return []

	def softwareLicense_createRetail(
		self,
		id,
		licenseContractId,
		maxInstallations=None,
		boundToHost=None,
		expirationDate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.softwareLicense_createObjects(RetailSoftwareLicense.fromHash(_hash))

	def softwareLicense_createOEM(
		self,
		id,
		licenseContractId,
		maxInstallations=None,
		boundToHost=None,
		expirationDate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.softwareLicense_createObjects(OEMSoftwareLicense.fromHash(_hash))

	def softwareLicense_createVolume(
		self,
		id,
		licenseContractId,
		maxInstallations=None,
		boundToHost=None,
		expirationDate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.softwareLicense_createObjects(VolumeSoftwareLicense.fromHash(_hash))

	def softwareLicense_createConcurrent(
		self,
		id,
		licenseContractId,
		maxInstallations=None,
		boundToHost=None,
		expirationDate=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.softwareLicense_createObjects(
			ConcurrentSoftwareLicense.fromHash(_hash)
		)

	def softwareLicense_delete(self, id):
		if id is None:
			id = []

		return self._backend.softwareLicense_deleteObjects(
			self._backend.softwareLicense_getObjects(id=id)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePool                                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_createObjects(self, licensePools):
		licensePools = forceObjectClassList(licensePools, LicensePool)
		for licensePool in licensePools:
			logger.info("Creating licensePool '%s'", licensePool)
			self._backend.licensePool_insertObject(licensePool)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.licensePool_getObjects(
				id=[licensePool.id for licensePool in licensePools]
			)
		return []

	def licensePool_updateObjects(self, licensePools):
		licensePools = forceObjectClassList(licensePools, LicensePool)
		for licensePool in licensePools:
			logger.info("Updating licensePool '%s'", licensePool)
			if self.licensePool_getIdents(id=licensePool.id):
				self._backend.licensePool_updateObject(licensePool)
			else:
				logger.info("LicensePool %s does not exist, creating", licensePool)
				self._backend.licensePool_insertObject(licensePool)

		if self._options["returnObjectsOnUpdateAndCreate"]:
			return self._backend.licensePool_getObjects(
				id=[licensePool.id for licensePool in licensePools]
			)
		return []

	def licensePool_create(self, id, description=None, productIds=None):
		_hash = locals()
		del _hash["self"]
		return self.licensePool_createObjects(LicensePool.fromHash(_hash))

	def licensePool_delete(self, id):
		if id is None:
			id = []

		return self._backend.licensePool_deleteObjects(
			self._backend.licensePool_getObjects(id=id)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_createObjects(self, softwareLicenseToLicensePools):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for softwareLicenseToLicensePool in forceObjectClassList(
			softwareLicenseToLicensePools, SoftwareLicenseToLicensePool
		):
			logger.info(
				"Creating softwareLicenseToLicensePool %s", softwareLicenseToLicensePool
			)
			self._backend.softwareLicenseToLicensePool_insertObject(
				softwareLicenseToLicensePool
			)

			if returnObjects:
				result.extend(
					self._backend.softwareLicenseToLicensePool_getObjects(
						softwareLicenseId=softwareLicenseToLicensePool.softwareLicenseId,
						licensePoolId=softwareLicenseToLicensePool.licensePoolId,
					)
				)

		return result

	def softwareLicenseToLicensePool_updateObjects(self, softwareLicenseToLicensePools):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		softwareLicenseToLicensePools = forceObjectClassList(
			softwareLicenseToLicensePools, SoftwareLicenseToLicensePool
		)
		for softwareLicenseToLicensePool in softwareLicenseToLicensePools:
			logger.info("Updating %s", softwareLicenseToLicensePool)
			if self.softwareLicenseToLicensePool_getIdents(
				softwareLicenseId=softwareLicenseToLicensePool.softwareLicenseId,
				licensePoolId=softwareLicenseToLicensePool.licensePoolId,
			):
				self._backend.softwareLicenseToLicensePool_updateObject(
					softwareLicenseToLicensePool
				)
			else:
				logger.info(
					"SoftwareLicenseToLicensePool %s does not exist, creating",
					softwareLicenseToLicensePool,
				)
				self._backend.softwareLicenseToLicensePool_insertObject(
					softwareLicenseToLicensePool
				)

			if returnObjects:
				result.extend(
					self._backend.softwareLicenseToLicensePool_getObjects(
						softwareLicenseId=softwareLicenseToLicensePool.softwareLicenseId,
						licensePoolId=softwareLicenseToLicensePool.licensePoolId,
					)
				)

		return result

	def softwareLicenseToLicensePool_create(
		self, softwareLicenseId, licensePoolId, licenseKey=None
	):
		_hash = locals()
		del _hash["self"]
		return self.softwareLicenseToLicensePool_createObjects(
			SoftwareLicenseToLicensePool.fromHash(_hash)
		)

	def softwareLicenseToLicensePool_delete(self, softwareLicenseId, licensePoolId):
		if not softwareLicenseId:
			softwareLicenseId = []
		if not licensePoolId:
			licensePoolId = []

		return self._backend.softwareLicenseToLicensePool_deleteObjects(
			self._backend.softwareLicenseToLicensePool_getObjects(
				softwareLicenseId=softwareLicenseId, licensePoolId=licensePoolId
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_createObjects(self, licenseOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for licenseOnClient in forceObjectClassList(licenseOnClients, LicenseOnClient):
			logger.info("Creating licenseOnClient %s", licenseOnClient)
			self._backend.licenseOnClient_insertObject(licenseOnClient)

			if returnObjects:
				result.extend(
					self._backend.licenseOnClient_getObjects(
						softwareLicenseId=licenseOnClient.softwareLicenseId,
						licensePoolId=licenseOnClient.licensePoolId,
						clientId=licenseOnClient.clientId,
					)
				)

		return result

	def licenseOnClient_updateObjects(self, licenseOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		licenseOnClients = forceObjectClassList(licenseOnClients, LicenseOnClient)
		for licenseOnClient in licenseOnClients:
			logger.info("Updating licenseOnClient %s", licenseOnClient)
			if self.licenseOnClient_getIdents(
				softwareLicenseId=licenseOnClient.softwareLicenseId,
				licensePoolId=licenseOnClient.licensePoolId,
				clientId=licenseOnClient.clientId,
			):
				self._backend.licenseOnClient_updateObject(licenseOnClient)
			else:
				logger.info(
					"LicenseOnClient %s does not exist, creating", licenseOnClient
				)
				self._backend.licenseOnClient_insertObject(licenseOnClient)

			if returnObjects:
				result.extend(
					self._backend.licenseOnClient_getObjects(
						softwareLicenseId=licenseOnClient.softwareLicenseId,
						licensePoolId=licenseOnClient.licensePoolId,
						clientId=licenseOnClient.clientId,
					)
				)

		return result

	def licenseOnClient_create(
		self,
		softwareLicenseId,
		licensePoolId,
		clientId,
		licenseKey=None,
		notes=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.licenseOnClient_createObjects(LicenseOnClient.fromHash(_hash))

	def licenseOnClient_delete(self, softwareLicenseId, licensePoolId, clientId):
		if softwareLicenseId is None:
			softwareLicenseId = []
		if licensePoolId is None:
			licensePoolId = []
		if clientId is None:
			clientId = []

		return self._backend.licenseOnClient_deleteObjects(
			self._backend.licenseOnClient_getObjects(
				softwareLicenseId=softwareLicenseId,
				licensePoolId=licensePoolId,
				clientId=clientId,
			)
		)

	def licenseOnClient_getOrCreateObject(
		self, clientId, licensePoolId=None, productId=None, windowsSoftwareId=None
	):
		clientId = forceHostId(clientId)
		if licensePoolId:
			licensePoolId = forceLicensePoolId(licensePoolId)
		elif productId or windowsSoftwareId:
			licensePoolIds = []
			if productId:
				productId = forceProductId(productId)
				licensePoolIds = self.licensePool_getIdents(
					productIds=productId, returnType="unicode"
				)
			elif windowsSoftwareId:
				licensePoolIds = []
				windowsSoftwareId = forceUnicode(windowsSoftwareId)

				auditSoftwares = self.auditSoftware_getObjects(
					windowsSoftwareId=windowsSoftwareId
				)
				for auditSoftware in auditSoftwares:
					auditSoftwareToLicensePools = (
						self.auditSoftwareToLicensePool_getObjects(
							name=auditSoftware.name,
							version=auditSoftware.version,
							subVersion=auditSoftware.subVersion,
							language=auditSoftware.language,
							architecture=auditSoftware.architecture,
						)
					)
					if auditSoftwareToLicensePools:
						licensePoolIds.append(
							auditSoftwareToLicensePools[0].licensePoolId
						)

			if len(licensePoolIds) < 1:
				raise LicenseConfigurationError(
					f"No license pool for product id '{productId}', windowsSoftwareId '{windowsSoftwareId}' found"
				)
			if len(licensePoolIds) > 1:
				raise LicenseConfigurationError(
					f"Multiple license pools for product id '{productId}', windowsSoftwareId '{windowsSoftwareId}' found: {licensePoolIds}"
				)
			licensePoolId = licensePoolIds[0]
		else:
			raise ValueError(
				"You have to specify one of: licensePoolId, productId, windowsSoftwareId"
			)

		if not self.licensePool_getIdents(id=licensePoolId):
			raise LicenseConfigurationError(f"License pool '{licensePoolId}' not found")

		# Test if a license is already used by the host
		licenseOnClient = None
		licenseOnClients = self._backend.licenseOnClient_getObjects(
			licensePoolId=licensePoolId, clientId=clientId
		)
		if licenseOnClients:
			logger.info(
				"Using already assigned license '%s' for client '%s', license pool '%s'",
				licenseOnClients[0].getSoftwareLicenseId(),
				clientId,
				licensePoolId,
			)
			licenseOnClient = licenseOnClients[0]
		else:
			(softwareLicenseId, licenseKey) = self._getUsableSoftwareLicense(
				clientId, licensePoolId
			)
			if not licenseKey:
				logger.info("License available but no license key found")

			logger.info(
				"Using software license id '%s', license key '%s' for host '%s' and license pool '%s'",
				softwareLicenseId,
				licenseKey,
				clientId,
				licensePoolId,
			)

			licenseOnClient = LicenseOnClient(
				softwareLicenseId=softwareLicenseId,
				licensePoolId=licensePoolId,
				clientId=clientId,
				licenseKey=licenseKey,
				notes=None,
			)
			self.licenseOnClient_createObjects(licenseOnClient)
		return licenseOnClient

	def _getUsableSoftwareLicense(self, clientId, licensePoolId):
		softwareLicenseId = ""
		licenseKey = ""

		licenseOnClients = self._backend.licenseOnClient_getObjects(
			licensePoolId=licensePoolId, clientId=clientId
		)
		if licenseOnClients:
			# Already registered
			return (
				licenseOnClients[0].getSoftwareLicenseId(),
				licenseOnClients[0].getLicenseKey(),
			)

		softwareLicenseToLicensePools = (
			self._backend.softwareLicenseToLicensePool_getObjects(
				licensePoolId=licensePoolId
			)
		)
		if not softwareLicenseToLicensePools:
			raise LicenseMissingError(f"No licenses in pool '{licensePoolId}'")

		softwareLicenseIds = [
			softwareLicenseToLicensePool.softwareLicenseId
			for softwareLicenseToLicensePool in softwareLicenseToLicensePools
		]

		softwareLicensesBoundToHost = self._backend.softwareLicense_getObjects(
			id=softwareLicenseIds, boundToHost=clientId
		)
		if softwareLicensesBoundToHost:
			logger.info(
				"Using license bound to host: %s", softwareLicensesBoundToHost[0]
			)
			softwareLicenseId = softwareLicensesBoundToHost[0].getId()
		else:
			# Search an available license
			for softwareLicense in self._backend.softwareLicense_getObjects(
				id=softwareLicenseIds, boundToHost=[None, ""]
			):
				logger.debug(
					"Checking license '%s', maxInstallations %d",
					softwareLicense.getId(),
					softwareLicense.getMaxInstallations(),
				)
				if softwareLicense.getMaxInstallations() == 0:
					# 0 = infinite
					softwareLicenseId = softwareLicense.getId()
					break
				installations = len(
					self.licenseOnClient_getIdents(
						softwareLicenseId=softwareLicense.getId()
					)
				)
				logger.debug("Installations registered: %d", installations)
				if installations < softwareLicense.getMaxInstallations():
					softwareLicenseId = softwareLicense.getId()
					break

			if softwareLicenseId:
				logger.info(
					"Found available license for pool '%s' and client '%s': %s",
					licensePoolId,
					clientId,
					softwareLicenseId,
				)

		if not softwareLicenseId:
			raise LicenseMissingError(
				f"No license available for pool '{licensePoolId}' and client '{clientId}', or all remaining licenses are bound to a different host."
			)

		licenseKeys = []
		for softwareLicenseToLicensePool in softwareLicenseToLicensePools:
			if softwareLicenseToLicensePool.getLicenseKey():
				if (
					softwareLicenseToLicensePool.getSoftwareLicenseId()
					== softwareLicenseId
				):
					licenseKey = softwareLicenseToLicensePool.getLicenseKey()
					break
				logger.debug("Found license key: %s", licenseKey)
				licenseKeys.append(softwareLicenseToLicensePool.getLicenseKey())

		if not licenseKey and licenseKeys:
			licenseKey = random.choice(licenseKeys)
			logger.info("Randomly choosing license key")

		logger.debug(
			"Using license '%s', license key: %s", softwareLicenseId, licenseKey
		)
		return (softwareLicenseId, licenseKey)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_createObjects(self, auditSoftwares):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware):
			logger.info("Creating auditSoftware %s", auditSoftware)
			self._backend.auditSoftware_insertObject(auditSoftware)

			if returnObjects:
				result.extend(
					self._backend.auditSoftware_getObjects(
						name=auditSoftware.name,
						version=auditSoftware.version,
						subVersion=auditSoftware.subVersion,
						language=auditSoftware.language,
						architecture=auditSoftware.architecture,
					)
				)

		return result

	def auditSoftware_updateObjects(self, auditSoftwares):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		auditSoftwares = forceObjectClassList(auditSoftwares, AuditSoftware)
		for auditSoftware in auditSoftwares:
			logger.info("Updating %s", auditSoftware)
			if self.auditSoftware_getIdents(
				name=auditSoftware.name,
				version=auditSoftware.version,
				subVersion=auditSoftware.subVersion,
				language=auditSoftware.language,
				architecture=auditSoftware.architecture,
			):
				self._backend.auditSoftware_updateObject(auditSoftware)
			else:
				logger.info("AuditSoftware %s does not exist, creating", auditSoftware)
				self._backend.auditSoftware_insertObject(auditSoftware)

			if returnObjects:
				result.extend(
					self._backend.auditSoftware_getObjects(
						name=auditSoftware.name,
						version=auditSoftware.version,
						subVersion=auditSoftware.subVersion,
						language=auditSoftware.language,
						architecture=auditSoftware.architecture,
					)
				)

		return result

	def auditSoftware_create(
		self,
		name,
		version,
		subVersion,
		language,
		architecture,
		windowsSoftwareId=None,
		windowsDisplayName=None,
		windowsDisplayVersion=None,
		installSize=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.auditSoftware_createObjects(AuditSoftware.fromHash(_hash))

	def auditSoftware_delete(self, name, version, subVersion, language, architecture):
		if name is None:
			name = []
		if version is None:
			version = []
		if subVersion is None:
			subVersion = []
		if language is None:
			language = []
		if architecture is None:
			architecture = []

		return self._backend.auditSoftware_deleteObjects(
			self._backend.auditSoftware_getObjects(
				name=name,
				version=version,
				subVersion=subVersion,
				language=language,
				architecture=architecture,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_createObjects(self, auditSoftwareToLicensePools):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for auditSoftwareToLicensePool in forceObjectClassList(
			auditSoftwareToLicensePools, AuditSoftwareToLicensePool
		):
			logger.info("Creating %s", auditSoftwareToLicensePool)
			self._backend.auditSoftwareToLicensePool_insertObject(
				auditSoftwareToLicensePool
			)

			if returnObjects:
				result.extend(
					self._backend.auditSoftwareToLicensePool_getObjects(
						name=auditSoftwareToLicensePool.name,
						version=auditSoftwareToLicensePool.version,
						subVersion=auditSoftwareToLicensePool.subVersion,
						language=auditSoftwareToLicensePool.language,
						architecture=auditSoftwareToLicensePool.architecture,
					)
				)

		return result

	def auditSoftwareToLicensePool_updateObjects(self, auditSoftwareToLicensePools):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		auditSoftwareToLicensePools = forceObjectClassList(
			auditSoftwareToLicensePools, AuditSoftwareToLicensePool
		)
		for auditSoftwareToLicensePool in auditSoftwareToLicensePools:
			logger.info("Creating %s", auditSoftwareToLicensePool)
			if self.auditSoftwareToLicensePool_getIdents(
				name=auditSoftwareToLicensePool.name,
				version=auditSoftwareToLicensePool.version,
				subVersion=auditSoftwareToLicensePool.subVersion,
				language=auditSoftwareToLicensePool.language,
				architecture=auditSoftwareToLicensePool.architecture,
			):
				self._backend.auditSoftwareToLicensePool_updateObject(
					auditSoftwareToLicensePool
				)
			else:
				logger.info(
					"AuditSoftwareToLicensePool %s does not exist, creating",
					auditSoftwareToLicensePool,
				)
				self._backend.auditSoftwareToLicensePool_insertObject(
					auditSoftwareToLicensePool
				)

			if returnObjects:
				result.extend(
					self._backend.auditSoftwareToLicensePool_getObjects(
						name=auditSoftwareToLicensePool.name,
						version=auditSoftwareToLicensePool.version,
						subVersion=auditSoftwareToLicensePool.subVersion,
						language=auditSoftwareToLicensePool.language,
						architecture=auditSoftwareToLicensePool.architecture,
					)
				)

		return result

	def auditSoftwareToLicensePool_create(
		self,
		name,
		version,
		subVersion,
		language,
		architecture,
		licensePoolId,
	):
		_hash = locals()
		del _hash["self"]
		return self.auditSoftwareToLicensePool_createObjects(
			AuditSoftwareToLicensePool.fromHash(_hash)
		)

	def auditSoftwareToLicensePool_delete(
		self, name, version, subVersion, language, architecture, licensePoolId
	):
		if name is None:
			name = []
		if version is None:
			version = []
		if subVersion is None:
			subVersion = []
		if language is None:
			language = []
		if architecture is None:
			architecture = []
		if licensePoolId is None:
			licensePoolId = []

		return self._backend.auditSoftwareToLicensePool_deleteObjects(
			self._backend.auditSoftwareToLicensePool_getObjects(
				name=name,
				version=version,
				subVersion=subVersion,
				language=language,
				architecture=architecture,
				licensePoolId=licensePoolId,
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_createObjects(self, auditSoftwareOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		for auditSoftwareOnClient in forceObjectClassList(
			auditSoftwareOnClients, AuditSoftwareOnClient
		):
			logger.info("Creating auditSoftwareOnClient %s", auditSoftwareOnClient)
			self._backend.auditSoftwareOnClient_insertObject(auditSoftwareOnClient)

			if returnObjects:
				result.extend(
					self._backend.auditSoftwareOnClient_getObjects(
						name=auditSoftwareOnClient.name,
						version=auditSoftwareOnClient.version,
						subVersion=auditSoftwareOnClient.subVersion,
						language=auditSoftwareOnClient.language,
						architecture=auditSoftwareOnClient.architecture,
						clientId=auditSoftwareOnClient.clientId,
					)
				)

		return result

	def auditSoftwareOnClient_updateObjects(self, auditSoftwareOnClients):
		returnObjects = self._options["returnObjectsOnUpdateAndCreate"]

		result = []
		auditSoftwareOnClients = forceObjectClassList(
			auditSoftwareOnClients, AuditSoftwareOnClient
		)
		for auditSoftwareOnClient in auditSoftwareOnClients:
			logger.info("Updating auditSoftwareOnClient %s", auditSoftwareOnClient)
			if self.auditSoftwareOnClient_getIdents(
				name=auditSoftwareOnClient.name,
				version=auditSoftwareOnClient.version,
				subVersion=auditSoftwareOnClient.subVersion,
				language=auditSoftwareOnClient.language,
				architecture=auditSoftwareOnClient.architecture,
				clientId=auditSoftwareOnClient.clientId,
			):
				self._backend.auditSoftwareOnClient_updateObject(auditSoftwareOnClient)
			else:
				logger.info(
					"AuditSoftwareOnClient %s does not exist, creating",
					auditSoftwareOnClient,
				)
				self._backend.auditSoftwareOnClient_insertObject(auditSoftwareOnClient)

			if returnObjects:
				result.extend(
					self._backend.auditSoftwareOnClient_getObjects(
						name=auditSoftwareOnClient.name,
						version=auditSoftwareOnClient.version,
						subVersion=auditSoftwareOnClient.subVersion,
						language=auditSoftwareOnClient.language,
						architecture=auditSoftwareOnClient.architecture,
						clientId=auditSoftwareOnClient.clientId,
					)
				)

		return result

	def auditSoftwareOnClient_create(
		self,
		name,
		version,
		subVersion,
		language,
		architecture,
		clientId,
		uninstallString=None,
		binaryName=None,
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=None,
		lastUsed=None,
		licenseKey=None,
	):
		_hash = locals()
		del _hash["self"]
		return self.auditSoftwareOnClient_createObjects(
			AuditSoftwareOnClient.fromHash(_hash)
		)

	def auditSoftwareOnClient_delete(
		self, name, version, subVersion, language, architecture, clientId
	):
		if name is None:
			name = []
		if version is None:
			version = []
		if subVersion is None:
			subVersion = []
		if language is None:
			language = []
		if architecture is None:
			architecture = []
		if clientId is None:
			clientId = []

		return self._backend.auditSoftwareOnClient_deleteObjects(
			self._backend.auditSoftwareOnClient_getObjects(
				name=name,
				version=version,
				subVersion=subVersion,
				language=language,
				architecture=architecture,
				clientId=clientId,
			)
		)

	def auditSoftwareOnClient_setObsolete(self, clientId):
		if hasattr(self._backend, "auditSoftwareOnClient_setObsolete"):
			# Using optimized version
			return self._backend.auditSoftwareOnClient_setObsolete(clientId)
		if clientId is None:
			clientId = []
		clientId = forceHostIdList(clientId)
		self._backend.auditSoftwareOnClient_deleteObjects(
			self._backend.auditSoftwareOnClient_getObjects(clientId=clientId)
		)
		return None

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardware_createObjects(self, auditHardwares):
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			logger.info("Creating auditHardware %s", auditHardware)
			self.auditHardware_insertObject(auditHardware)
		return []

	def auditHardware_updateObjects(self, auditHardwares):
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			logger.info("Updating auditHardware %s", auditHardware)
			# You can't update auditHardwares, because the ident contains all attributes
			self.auditHardware_insertObject(auditHardware)
		return []

	def auditHardware_create(self, hardwareClass, **kwargs):
		_hash = locals()
		del _hash["self"]
		return self.auditHardware_createObjects(AuditHardware.fromHash(_hash))

	def auditHardware_delete(self, hardwareClass, **kwargs):
		if hardwareClass is None:
			hardwareClass = []

		for key in list(kwargs):
			if kwargs[key] is None:
				kwargs[key] = []

		return self._backend.auditHardware_deleteObjects(
			self._backend.auditHardware_getObjects(
				hardwareClass=hardwareClass, **kwargs
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		"""
		Update an auditHardwareOnHost object.

		This will update the attributes `state` and `lastseen` on the object.
		"""
		auditHardwareOnHost.setLastseen(timestamp())
		auditHardwareOnHost.setState(1)
		self._backend.auditHardwareOnHost_updateObject(auditHardwareOnHost)

	def auditHardwareOnHost_createObjects(self, auditHardwareOnHosts):
		for auditHardwareOnHost in forceObjectClassList(
			auditHardwareOnHosts, AuditHardwareOnHost
		):
			logger.info("Creating auditHardwareOnHost %s", auditHardwareOnHost)
			self._backend.auditHardwareOnHost_insertObject(auditHardwareOnHost)

		return []

	def auditHardwareOnHost_updateObjects(self, auditHardwareOnHosts):
		def getNoneAsListOrValue(value):
			if value is None:
				return [None]
			return value

		for auditHardwareOnHost in forceObjectClassList(
			auditHardwareOnHosts, AuditHardwareOnHost
		):
			_filter = {
				attribute: getNoneAsListOrValue(value)
				for (attribute, value) in auditHardwareOnHost.toHash().items()
				if attribute not in ("firstseen", "lastseen", "state")
			}

			if self.auditHardwareOnHost_getObjects(attributes=["hostId"], **_filter):
				logger.trace(
					"Updating existing AuditHardwareOnHost %s", auditHardwareOnHost
				)
				self.auditHardwareOnHost_updateObject(auditHardwareOnHost)
			else:
				logger.info(
					"AuditHardwareOnHost %s does not exist, creating",
					auditHardwareOnHost,
				)
				self._backend.auditHardwareOnHost_insertObject(auditHardwareOnHost)

		return []

	def auditHardwareOnHost_create(
		self,
		hostId,
		hardwareClass,
		firstseen=None,
		lastseen=None,
		state=None,
		**kwargs,
	):
		_hash = locals()
		del _hash["self"]
		return self.auditHardwareOnHost_createObjects(
			AuditHardwareOnHost.fromHash(_hash)
		)

	def auditHardwareOnHost_delete(
		self, hostId, hardwareClass, firstseen=None, lastseen=None, state=None, **kwargs
	):
		if hostId is None:
			hostId = []
		if hardwareClass is None:
			hardwareClass = []
		if firstseen is None:
			firstseen = []
		if lastseen is None:
			lastseen = []
		if state is None:
			state = []

		for key in list(kwargs):
			if kwargs[key] is None:
				kwargs[key] = []

		return self._backend.auditHardwareOnHost_deleteObjects(
			self._backend.auditHardwareOnHost_getObjects(
				hostId=hostId,
				hardwareClass=hardwareClass,
				firstseen=firstseen,
				lastseen=lastseen,
				state=state,
				**kwargs,
			)
		)

	def auditHardwareOnHost_setObsolete(self, hostId):
		if hasattr(self._backend, "auditHardwareOnHost_setObsolete"):
			# Using optimized version
			return self._backend.auditHardwareOnHost_setObsolete(hostId)
		if hostId is None:
			hostId = []
		hostId = forceHostIdList(hostId)
		for ahoh in self.auditHardwareOnHost_getObjects(hostId=hostId, state=1):
			ahoh.setState(0)
			self._backend.auditHardwareOnHost_updateObject(ahoh)
		return None
