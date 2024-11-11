# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend-Replicator.

The replicator allows replication from one backend into another.
"""

from opsicommon.logging import get_logger

from OPSI.Backend.Base import Backend, ExtendedConfigDataBackend

# Wildcard import is necessary for eval-statement
from OPSI.Object import *  # pylint: disable=wildcard-import,unused-wildcard-import  # noqa: F401,F403
from OPSI.Types import forceBool, forceHostId, forceList
from OPSI.Util.Message import ProgressSubject

__all__ = ("BackendReplicator",)

logger = get_logger("opsi.general")


class BackendReplicator:  # pylint: disable=too-many-instance-attributes
	OBJECT_CLASSES = [
		"Host",
		"Product",
		"Config",
		"Group",
		"LicenseContract",
		"LicensePool",
		"SoftwareLicense",
		"AuditHardware",
		"AuditSoftware",
		"ProductDependency",
		"ProductProperty",
		"ProductOnDepot",
		"ProductOnClient",
		"ProductPropertyState",
		"ConfigState",
		"ObjectToGroup",
		"AuditHardwareOnHost",
		"AuditSoftwareOnClient",
		"SoftwareLicenseToLicensePool",
		"LicenseOnClient",
		"AuditSoftwareToLicensePool",
	]

	def __init__(  # pylint: disable=too-many-arguments
		self,
		readBackend: Backend,
		writeBackend: Backend,
		newServerId: str = None,
		oldServerId: str = None,
		cleanupFirst: bool = True,
	) -> None:
		self.__readBackend = readBackend
		self.__writeBackend = writeBackend

		self._extendedReadBackend = ExtendedConfigDataBackend(self.__readBackend)
		self._extendedWriteBackend = ExtendedConfigDataBackend(self.__writeBackend)

		self.__newServerId = None
		self.__oldServerId = None

		self.__cleanupFirst = forceBool(cleanupFirst)
		self.__strict = False
		self.__serverIds = []  # pylint: disable=unused-private-member
		self.__depotIds = []  # pylint: disable=unused-private-member
		self.__clientIds = []  # pylint: disable=unused-private-member
		self.__groupIds = []  # pylint: disable=unused-private-member
		self.__productIds = []  # pylint: disable=unused-private-member

		if newServerId:
			self.__newServerId = forceHostId(newServerId)
		if oldServerId:
			self.__oldServerId = forceHostId(oldServerId)

		self.__overallProgressSubject = ProgressSubject(
			id="overall_replication", title="Replicating", end=100, fireAlways=True
		)
		self.__currentProgressSubject = ProgressSubject(
			id="current_replication", fireAlways=True
		)

	def getCurrentProgressSubject(self) -> ProgressSubject:
		return self.__currentProgressSubject

	def getOverallProgressSubject(self) -> ProgressSubject:
		return self.__overallProgressSubject

	def replicate(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
		self,
		serverIds: list[str] = None,
		depotIds: list[str] = None,
		clientIds: list[str] = None,
		groupIds: list[str] = None,
		productIds: list[str] = None,
		productTypes: list[str] = None,
		audit: bool = True,
		licenses: bool = True,
	) -> None:
		"""
		Replicate (a part) of a opsi configuration database
		An empty list passed as a param means: replicate all known
		None as the only element of a list means: replicate none
		"""
		serverIds = forceList(serverIds or [])
		depotIds = forceList(depotIds or [])
		clientIds = forceList(clientIds or [])
		groupIds = forceList(serverIds or [])
		productIds = forceList(productIds or [])
		productTypes = forceList(productTypes or [])
		audit = forceBool(audit)
		licenses = forceBool(licenses)

		logger.info(
			"Replicating: serverIds=%s, depotIds=%s, clientIds=%s, groupIds=%s, productIds=%s, productTypes=%s, audit: %s, license: %s",
			serverIds,
			depotIds,
			clientIds,
			groupIds,
			productIds,
			productTypes,
			audit,
			licenses,
		)

		rb = self._extendedReadBackend
		wb = self.__writeBackend
		aric = wb.backend_getOptions().get("additionalReferentialIntegrityChecks", True)
		if self.__strict:
			wb = self._extendedWriteBackend
		else:
			wb.backend_setOptions({"additionalReferentialIntegrityChecks": False})

		try:
			if serverIds or depotIds or clientIds:
				if not serverIds:
					serverIds = rb.host_getIdents(
						type="OpsiConfigserver", returnType=list
					)
				if not depotIds:
					depotIds = rb.host_getIdents(
						type="OpsiDepotserver", returnType=list
					)
				if not clientIds:
					clientIds = rb.host_getIdents(type="OpsiClient", returnType=list)

			hostIds = set()
			for serverId in serverIds:
				hostIds.add(serverId)

			for depotId in depotIds:
				hostIds.add(depotId)

			for clientId in clientIds:
				hostIds.add(clientId)

			self.__overallProgressSubject.reset()
			end = self._getNumberOfObjectClassesToProcess(audit, licenses)
			if self.__cleanupFirst:
				end += 1
			if self.__newServerId:
				end += 1
			self.__overallProgressSubject.setEnd(end)

			if self.__cleanupFirst:
				wb.backend_deleteBase()
				self.__overallProgressSubject.addToState(1)

			wb.backend_createBase()

			productOnDepots = []
			if depotIds:
				productOnDepots = rb.productOnDepot_getObjects(
					depotId=depotIds, productId=productIds, productType=productTypes
				)  # pylint: disable=no-member
				productIdsOnDepot = set()
				for productOnDepot in productOnDepots:
					productIdsOnDepot.add(productOnDepot.productId)

				if productIdsOnDepot:
					if not productIds:
						productIds = list(productIdsOnDepot)
					else:
						newProductIds = []
						for productId in productIds:
							if productId in productIdsOnDepot:
								newProductIds.append(productId)
						productIds = newProductIds

			auditClasses = set(
				[
					"AuditHardware",
					"AuditSoftware",
					"AuditHardwareOnHost",
					"AuditSoftwareOnClient",
				]
			)
			licenseClasses = set(
				[
					"LicenseContract",
					"SoftwareLicense",
					"LicensePool",
					"SoftwareLicenseToLicensePool",
					"LicenseOnClient",
					"AuditSoftwareToLicensePool",
				]
			)

			configServer = None
			depotServers = []
			for objClass in self.OBJECT_CLASSES:
				if not audit and objClass in auditClasses:
					continue
				if not licenses and objClass in licenseClasses:
					continue

				subClasses = [None]
				if objClass == "Host":
					subClasses = ["OpsiConfigserver", "OpsiDepotserver", "OpsiClient"]

				eval(f"{objClass}.backendMethodPrefix")  # pylint: disable=eval-used,unused-variable

				self.__overallProgressSubject.setMessage(f"Replicating {objClass}")
				self.__currentProgressSubject.setTitle(f"Replicating {objClass}")
				for subClass in subClasses:
					filter = {}  # pylint: disable=redefined-builtin
					if subClass == "OpsiConfigserver":
						filter = {"type": subClass, "id": serverIds}
					elif subClass == "OpsiDepotserver":
						filter = {"type": subClass, "id": depotIds}
					elif subClass == "OpsiClient":
						filter = {"type": subClass, "id": clientIds}
					elif objClass == "Group":
						filter = {"type": subClass, "id": groupIds}
					elif objClass == "Product":
						filter = {"type": subClass, "id": productIds}
					elif objClass == "ProductOnClient":
						filter = {
							"productType": productTypes,
							"productId": productIds,
							"clientId": clientIds,
						}
					elif objClass == "ProductOnDepot":
						filter = {
							"productType": productTypes,
							"productId": productIds,
							"depotId": depotIds,
						}
					elif objClass == "ProductDependency":
						filter = {"productId": productIds}
					elif objClass == "ProductProperty":
						filter = {"productId": productIds}
					elif objClass == "ProductPropertyState":
						filter = {
							"productId": productIds,
							"objectId": forceList(hostIds),
						}
					elif objClass == "ConfigState":
						filter = {"objectId": forceList(hostIds)}
					elif objClass == "ObjectToGroup":
						if productIds and hostIds:
							objectIds = productIds + forceList(hostIds)
						else:
							objectIds = []

						filter = {"objectId": objectIds}
					elif objClass == "LicenseOnClient":
						filter = {"clientId": clientIds}

					logger.notice(
						"Replicating class '%s', filter: %s" % (objClass, filter)
					)
					if not subClass:
						subClass = objClass
					Class = eval(subClass)  # pylint: disable=eval-used

					self.__currentProgressSubject.reset()
					self.__currentProgressSubject.setMessage("Reading objects")
					self.__currentProgressSubject.setEnd(1)
					objs = []

					if objClass == "ProductOnDepot" and productOnDepots:
						objs = productOnDepots
					else:
						meth = "%s_getObjects" % Class.backendMethodPrefix
						meth = getattr(rb, meth)
						objs = meth(**filter)

					self.__currentProgressSubject.addToState(1)
					if objClass == "Group":
						# Sort groups
						sortedObjs = []
						groupIds = []
						while True:
							notAddedObjs = []
							for obj in objs:
								if (
									not obj.getParentGroupId()
									or obj.getParentGroupId() in groupIds
								):
									if not obj.getParentGroupId():
										logger.debug(
											"Adding group '%s' without parent group set",
											obj,
										)
									else:
										logger.debug(
											"Adding group '%s' with parent group '%s' already added",
											obj,
											obj.getParentGroupId(),
										)
									sortedObjs.append(obj)
									groupIds.append(obj.getId())
								else:
									logger.debug(
										"Cannot add group '%s' parent group '%s' not added yet",
										obj,
										obj.getParentGroupId(),
									)
									notAddedObjs.append(obj)
							if not notAddedObjs:
								break
							if len(notAddedObjs) == len(objs):
								for obj in notAddedObjs:
									logger.error("Failed to add group: %s", obj)
								break
							objs = notAddedObjs
						objs = sortedObjs

					self.__currentProgressSubject.reset()
					self.__currentProgressSubject.setMessage("Writing objects")
					if subClass == "OpsiConfigserver" and objs:
						configServer = objs[0]
						depotServers.extend(objs)
					if subClass == "OpsiDepotserver":
						depotServers.extend(objs)

					if self.__strict:
						self.__currentProgressSubject.setEnd(1)
						meth = "%s_createObjects" % Class.backendMethodPrefix
						meth = getattr(wb, meth)
						meth(objs)
						self.__currentProgressSubject.addToState(1)
					else:
						self.__currentProgressSubject.setEnd(len(objs))
						meth = "%s_insertObject" % Class.backendMethodPrefix
						meth = getattr(wb, meth)

						for obj in objs:
							try:
								meth(obj)
							except Exception as err:  # pylint: disable=broad-except
								logger.debug(err, exc_info=True)
								logger.error(
									"Failed to replicate object %s: %s", obj, err
								)
							self.__currentProgressSubject.addToState(1)
					self.__currentProgressSubject.setState(len(objs))

				self.__overallProgressSubject.addToState(1)

			if self.__newServerId:
				self.__currentProgressSubject.reset()
				self.__currentProgressSubject.setMessage("Renaming server")
				self.__currentProgressSubject.setTitle("Renaming server")
				self.__currentProgressSubject.setEnd(1)
				if not self.__oldServerId:
					if configServer:
						self.__oldServerId = configServer.id
					elif depotServers:
						self.__oldServerId = depotServers[0].id
					else:
						logger.error("No config/depot servers found")

				if self.__oldServerId and self.__oldServerId != self.__newServerId:
					logger.notice(
						"Renaming config server {0!r} to {1!r}".format(
							self.__oldServerId, self.__newServerId
						)
					)
					renamingBackend = wb
					try:
						renamingBackend.host_renameOpsiDepotserver()
					except TypeError:
						pass  # Missing arguments but method exists
					except AttributeError:
						# Missing the method - need to use extended backend
						renamingBackend = self._extendedWriteBackend

					renamingBackend.host_renameOpsiDepotserver(
						oldId=self.__oldServerId, newId=self.__newServerId
					)

					newDepots = []
					for depot in renamingBackend.host_getObjects(
						type="OpsiDepotserver"
					):
						_hash = depot.toHash()
						del _hash["type"]
						if depot.id == self.__newServerId:
							newDepots.append(OpsiConfigserver.fromHash(_hash))
						else:
							newDepots.append(OpsiDepotserver.fromHash(_hash))
					renamingBackend.host_createObjects(newDepots)

				self.__overallProgressSubject.addToState(1)
		finally:
			wb.backend_setOptions({"additionalReferentialIntegrityChecks": aric})

	@classmethod
	def _getNumberOfObjectClassesToProcess(
		cls, audit: bool = True, licenses: bool = True
	) -> int:
		auditClasses = set(
			[
				"AuditHardware",
				"AuditSoftware",
				"AuditHardwareOnHost",
				"AuditSoftwareOnClient",
			]
		)
		licenseManagementClasses = set(
			[
				"LicenseContract",
				"SoftwareLicense",
				"LicensePool",
				"SoftwareLicenseToLicensePool",
				"LicenseOnClient",
				"AuditSoftwareToLicensePool",
			]
		)

		classesToProgress = set(cls.OBJECT_CLASSES)
		if not audit:
			classesToProgress = classesToProgress - auditClasses
		if not licenses:
			classesToProgress = classesToProgress - licenseManagementClasses

		return len(classesToProgress)
