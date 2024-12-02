# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
File-Backend.

This backend stores all it's data in plaintext files.
"""

import grp
import os
import pwd
import re
import shutil
from typing import Union

from opsicommon.logging import get_logger

from OPSI.Backend.Base import ConfigDataBackend
from OPSI.Config import FILE_ADMIN_GROUP, OPSICONFD_USER
from OPSI.Exceptions import (
	BackendBadValueError,
	BackendConfigurationError,
	BackendError,
	BackendIOError,
	BackendMissingDataError,
	BackendUnaccomplishableError,
)
from OPSI.Object import *  # needed for calls to "eval"  # noqa: F403
from OPSI.Types import (
	forceBool,
	forceFilename,
	forceHostId,
	forceList,
	forceObjectClass,
	forceObjectClassList,
	forceProductId,
	forceUnicode,
	forceUnicodeList,
)
from OPSI.Util import fromJson, getfqdn, toJson
from OPSI.Util.File import IniFile, LockableFile
from OPSI.Util.File.Opsi import HostKeyFile, PackageControlFile

__all__ = ("FileBackend",)


logger = get_logger("opsi.general")


class FileBackend(ConfigDataBackend):
	"""Backend holding information in Plain textfile form."""

	PRODUCT_FILENAME_REGEX = re.compile(
		r"^([a-zA-Z0-9_.-]+)_([\w.]+)-([\w.]+)\.(local|net)boot$"
	)
	PLACEHOLDER_REGEX = re.compile(r"^(.*)<([^>]+)>(.*)$")

	def __init__(self, **kwargs) -> None:
		self._name = "file"

		ConfigDataBackend.__init__(self, **kwargs)

		self.__baseDir = "/var/lib/opsi/config"
		self.__hostKeyFile = "/etc/opsi/pckeys"

		self.__fileUser = OPSICONFD_USER
		self.__fileGroup = FILE_ADMIN_GROUP
		self.__fileMode = 0o660
		self.__dirGroup = FILE_ADMIN_GROUP
		self.__dirUser = OPSICONFD_USER
		self.__dirMode = 0o770

		# Parse arguments
		logger.trace("kwargs are: {0}".format(kwargs))
		for option, value in kwargs.items():
			option = option.lower()
			if option == "basedir":
				logger.trace('Setting __basedir to "{0}"'.format(value))
				self.__baseDir = forceFilename(value)
			elif option == "hostkeyfile":
				logger.trace('Setting __hostKeyFile to "{0}"'.format(value))
				self.__hostKeyFile = forceFilename(value)
			elif option in ("filegroupname",):
				logger.trace('Setting __fileGroup to "{0}"'.format(value))
				self.__fileGroup = forceUnicode(value)
				logger.trace('Setting __dirGroup to "{0}"'.format(value))
				self.__dirGroup = forceUnicode(value)
			elif option in ("fileusername",):
				logger.trace('Setting __fileUser to "{0}"'.format(value))
				self.__fileUser = forceUnicode(value)
				logger.trace('Setting __dirUser to "{0}"'.format(value))
				self.__dirUser = forceUnicode(value)

		self.__fileUid = pwd.getpwnam(self.__fileUser)[2]
		self.__fileGid = grp.getgrnam(self.__fileGroup)[2]
		self.__dirUid = pwd.getpwnam(self.__dirUser)[2]
		self.__dirGid = grp.getgrnam(self.__dirGroup)[2]

		self.__clientConfigDir = os.path.join(self.__baseDir, "clients")
		self.__depotConfigDir = os.path.join(self.__baseDir, "depots")
		self.__productDir = os.path.join(self.__baseDir, "products")
		self.__auditDir = os.path.join(self.__baseDir, "audit")
		self.__configFile = os.path.join(self.__baseDir, "config.ini")
		self.__clientGroupsFile = os.path.join(self.__baseDir, "clientgroups.ini")
		self.__productGroupsFile = os.path.join(self.__baseDir, "productgroups.ini")
		self.__clientTemplateDir = os.path.join(self.__baseDir, "templates")

		self.__defaultClientTemplateName = "pcproto"
		self.__defaultClientTemplatePath = os.path.join(
			self.__clientTemplateDir, "{0}.ini".format(self.__defaultClientTemplateName)
		)

		self.__serverId = forceHostId(getfqdn())

		self._mappings = {
			"Config": [
				{
					"fileType": "ini",
					"attribute": "type",
					"section": "<id>",
					"option": "type",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "description",
					"section": "<id>",
					"option": "description",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "editable",
					"section": "<id>",
					"option": "editable",
					"json": True,
				},
				{
					"fileType": "ini",
					"attribute": "multiValue",
					"section": "<id>",
					"option": "multivalue",
					"json": True,
				},
				{
					"fileType": "ini",
					"attribute": "possibleValues",
					"section": "<id>",
					"option": "possiblevalues",
					"json": True,
				},
				{
					"fileType": "ini",
					"attribute": "defaultValues",
					"section": "<id>",
					"option": "defaultvalues",
					"json": True,
				},
			],
			"OpsiClient": [
				{"fileType": "key", "attribute": "opsiHostKey"},
				{
					"fileType": "ini",
					"attribute": "oneTimePassword",
					"section": "info",
					"option": "onetimepassword",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "description",
					"section": "info",
					"option": "description",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "notes",
					"section": "info",
					"option": "notes",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "hardwareAddress",
					"section": "info",
					"option": "hardwareaddress",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "ipAddress",
					"section": "info",
					"option": "ipaddress",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "inventoryNumber",
					"section": "info",
					"option": "inventorynumber",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "created",
					"section": "info",
					"option": "created",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "lastSeen",
					"section": "info",
					"option": "lastseen",
					"json": False,
				},
			],
			"OpsiDepotserver": [
				{"fileType": "key", "attribute": "opsiHostKey"},
				{
					"fileType": "ini",
					"attribute": "description",
					"section": "depotserver",
					"option": "description",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "notes",
					"section": "depotserver",
					"option": "notes",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "hardwareAddress",
					"section": "depotserver",
					"option": "hardwareaddress",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "ipAddress",
					"section": "depotserver",
					"option": "ipaddress",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "inventoryNumber",
					"section": "depotserver",
					"option": "inventorynumber",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "networkAddress",
					"section": "depotserver",
					"option": "network",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "isMasterDepot",
					"section": "depotserver",
					"option": "ismasterdepot",
					"json": True,
				},
				{
					"fileType": "ini",
					"attribute": "masterDepotId",
					"section": "depotserver",
					"option": "masterdepotid",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "depotRemoteUrl",
					"section": "depotshare",
					"option": "remoteurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "depotWebdavUrl",
					"section": "depotshare",
					"option": "webdavurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "depotLocalUrl",
					"section": "depotshare",
					"option": "localurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "repositoryRemoteUrl",
					"section": "repository",
					"option": "remoteurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "repositoryLocalUrl",
					"section": "repository",
					"option": "localurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "maxBandwidth",
					"section": "repository",
					"option": "maxbandwidth",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "workbenchLocalUrl",
					"section": "workbench",
					"option": "localurl",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "workbenchRemoteUrl",
					"section": "workbench",
					"option": "remoteurl",
					"json": False,
				},
			],
			"ConfigState": [
				{
					"fileType": "ini",
					"attribute": "values",
					"section": "generalconfig",
					"option": "<configId>",
					"json": True,
				}
			],
			"Product": [
				{"fileType": "pro", "attribute": "name", "object": "product"},
				{
					"fileType": "pro",
					"attribute": "licenseRequired",
					"object": "product",
				},
				{"fileType": "pro", "attribute": "setupScript", "object": "product"},
				{
					"fileType": "pro",
					"attribute": "uninstallScript",
					"object": "product",
				},
				{"fileType": "pro", "attribute": "updateScript", "object": "product"},
				{"fileType": "pro", "attribute": "alwaysScript", "object": "product"},
				{"fileType": "pro", "attribute": "onceScript", "object": "product"},
				{"fileType": "pro", "attribute": "customScript", "object": "product"},
				{"fileType": "pro", "attribute": "priority", "object": "product"},
				{"fileType": "pro", "attribute": "description", "object": "product"},
				{"fileType": "pro", "attribute": "advice", "object": "product"},
				{"fileType": "pro", "attribute": "changelog", "object": "product"},
				{
					"fileType": "pro",
					"attribute": "productClassNames",
					"object": "product",
				},
				{
					"fileType": "pro",
					"attribute": "windowsSoftwareIds",
					"object": "product",
				},
			],
			"LocalbootProduct": [
				{"fileType": "pro", "attribute": "userLoginScript", "object": "product"}
			],
			"NetbootProduct": [
				{
					"fileType": "pro",
					"attribute": "pxeConfigTemplate",
					"object": "product",
				}
			],
			"ProductProperty": [{"fileType": "pro", "attribute": "*"}],
			"ProductDependency": [{"fileType": "pro", "attribute": "*"}],
			"ProductOnDepot": [
				{
					"fileType": "ini",
					"attribute": "productType",
					"section": "<productId>-state",
					"option": "producttype",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "productVersion",
					"section": "<productId>-state",
					"option": "productversion",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "packageVersion",
					"section": "<productId>-state",
					"option": "packageversion",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "locked",
					"section": "<productId>-state",
					"option": "locked",
					"json": False,
				},
			],
			"ProductOnClient": [
				{
					"fileType": "ini",
					"attribute": "productType",
					"section": "<productId>-state",
					"option": "producttype",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "actionProgress",
					"section": "<productId>-state",
					"option": "actionprogress",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "productVersion",
					"section": "<productId>-state",
					"option": "productversion",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "packageVersion",
					"section": "<productId>-state",
					"option": "packageversion",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "modificationTime",
					"section": "<productId>-state",
					"option": "modificationtime",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "lastAction",
					"section": "<productId>-state",
					"option": "lastaction",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "actionResult",
					"section": "<productId>-state",
					"option": "actionresult",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "targetConfiguration",
					"section": "<productId>-state",
					"option": "targetconfiguration",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "installationStatus",
					"section": "<productType>_product_states",
					"option": "<productId>",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "actionRequest",
					"section": "<productType>_product_states",
					"option": "<productId>",
					"json": False,
				},
			],
			"ProductPropertyState": [
				{
					"fileType": "ini",
					"attribute": "values",
					"section": "<productId>-install",
					"option": "<propertyId>",
					"json": True,
				}
			],
			"Group": [
				{
					"fileType": "ini",
					"attribute": "description",
					"section": "<id>",
					"option": "description",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "parentGroupId",
					"section": "<id>",
					"option": "parentgroupid",
					"json": False,
				},
				{
					"fileType": "ini",
					"attribute": "notes",
					"section": "<id>",
					"option": "notes",
					"json": False,
				},
			],
			"ObjectToGroup": [
				{
					"fileType": "ini",
					"attribute": "*",
					"section": "<groupId>",
					"option": "<objectId>",
					"json": False,
				}
			],
		}

		self._mappings["UnicodeConfig"] = self._mappings["Config"]
		self._mappings["BoolConfig"] = self._mappings["Config"]
		self._mappings["OpsiConfigserver"] = self._mappings["OpsiDepotserver"]
		self._mappings["UnicodeProductProperty"] = self._mappings["ProductProperty"]
		self._mappings["BoolProductProperty"] = self._mappings["ProductProperty"]
		self._mappings["HostGroup"] = self._mappings["Group"]
		self._mappings["ProductGroup"] = self._mappings["Group"]

		# Extending the settings with the attributes from the base class
		self._mappings["LocalbootProduct"].extend(self._mappings["Product"])
		self._mappings["NetbootProduct"].extend(self._mappings["Product"])

	def backend_exit(self) -> None:
		pass

	def backend_createBase(self) -> None:
		logger.notice("Creating base path: '%s'" % (self.__baseDir))
		for dirname in (
			self.__baseDir,
			self.__clientConfigDir,
			self.__depotConfigDir,
			self.__productDir,
			self.__auditDir,
			self.__clientTemplateDir,
		):
			if not os.path.isdir(dirname):
				self._mkdir(dirname)
			self._setRights(dirname)

		defaultTemplate = os.path.join(
			self.__clientTemplateDir, self.__defaultClientTemplateName + ".ini"
		)
		for filename in (
			defaultTemplate,
			self.__configFile,
			self.__hostKeyFile,
			self.__clientGroupsFile,
			self.__productGroupsFile,
		):
			if not os.path.isfile(filename):
				self._touch(filename)
			self._setRights(filename)

	def backend_deleteBase(self) -> None:
		logger.notice("Deleting base path: '%s'" % (self.__baseDir))
		if os.path.exists(self.__baseDir):
			shutil.rmtree(self.__baseDir)
		if os.path.exists(self.__clientConfigDir):
			shutil.rmtree(self.__clientConfigDir)
		if os.path.exists(self.__depotConfigDir):
			shutil.rmtree(self.__depotConfigDir)
		if os.path.exists(self.__productDir):
			shutil.rmtree(self.__productDir)
		if os.path.exists(self.__auditDir):
			shutil.rmtree(self.__auditDir)
		if os.path.exists(self.__configFile):
			os.unlink(self.__configFile)
		if os.path.exists(self.__hostKeyFile):
			os.unlink(self.__hostKeyFile)
		if os.path.exists(self.__clientGroupsFile):
			os.unlink(self.__clientGroupsFile)
		if os.path.exists(self.__productGroupsFile):
			os.unlink(self.__productGroupsFile)

	def _setRights(self, path: str) -> None:
		logger.debug("Setting rights for path '%s'", path)
		try:
			if os.path.isfile(path):
				logger.debug("Setting rights on file '%s'", path)
				os.chmod(path, self.__fileMode)
				if os.geteuid() == 0:
					os.chown(path, self.__fileUid, self.__fileGid)
				else:
					os.chown(path, -1, self.__fileGid)
			elif os.path.isdir(path):
				logger.debug("Setting rights on directory '%s'", path)
				os.chmod(path, self.__dirMode)
				if os.geteuid() == 0:
					os.chown(path, self.__dirUid, self.__dirGid)
				else:
					os.chown(path, -1, self.__dirGid)
		except Exception as err:
			logger.warning("Failed to set rights for path '%s': %s", path, err)

	def _mkdir(self, path: str) -> None:
		logger.debug("Creating path: '%s'", path)
		os.mkdir(path)
		self._setRights(path)

	def _touch(self, filename: str) -> None:
		logger.debug("Creating file: '%s'", filename)
		if not os.path.exists(filename):
			file = LockableFile(filename)
			file.create()
		else:
			logger.debug("Cannot create existing file, only setting rights.")
		self._setRights(filename)

	@staticmethod
	def __escape(string: str) -> str:
		string = forceUnicode(string)
		logger.trace("Escaping string: '%s'" % (string))
		return (
			string.replace("\n", "\\n")
			.replace(";", "\\;")
			.replace("#", "\\#")
			.replace("%", "%%")
		)

	@staticmethod
	def __unescape(string: str) -> str:
		string = forceUnicode(string)
		logger.trace("Unescaping string: '%s'" % (string))
		return (
			string.replace("\\n", "\n")
			.replace("\\;", ";")
			.replace("\\#", "#")
			.replace("%%", "%")
		)

	def _getConfigFile(self, objType: str, ident: dict[str, Any], fileType: str) -> str:
		logger.debug(
			"Getting config file for '%s', '%s', '%s'", objType, ident, fileType
		)
		filename = None

		if fileType == "key":
			filename = self.__hostKeyFile

		elif fileType == "ini":
			if objType in ("Config", "UnicodeConfig", "BoolConfig"):
				filename = self.__configFile
			elif objType == "OpsiClient":
				filename = os.path.join(self.__clientConfigDir, ident["id"] + ".ini")
			elif objType in ("OpsiDepotserver", "OpsiConfigserver"):
				filename = os.path.join(self.__depotConfigDir, ident["id"] + ".ini")
			elif objType == "ConfigState":
				if os.path.isfile(
					os.path.join(
						os.path.join(self.__depotConfigDir, ident["objectId"] + ".ini")
					)
				):
					filename = os.path.join(
						self.__depotConfigDir, ident["objectId"] + ".ini"
					)
				else:
					filename = os.path.join(
						self.__clientConfigDir, ident["objectId"] + ".ini"
					)
			elif objType == "ProductOnDepot":
				filename = os.path.join(
					self.__depotConfigDir, ident["depotId"] + ".ini"
				)
			elif objType == "ProductOnClient":
				filename = os.path.join(
					self.__clientConfigDir, ident["clientId"] + ".ini"
				)
			elif objType == "ProductPropertyState":
				if os.path.isfile(
					os.path.join(
						os.path.join(self.__depotConfigDir, ident["objectId"] + ".ini")
					)
				):
					filename = os.path.join(
						self.__depotConfigDir, ident["objectId"] + ".ini"
					)
				else:
					filename = os.path.join(
						self.__clientConfigDir, ident["objectId"] + ".ini"
					)
			elif objType in ("Group", "HostGroup", "ProductGroup"):
				if objType == "ProductGroup" or (
					objType == "Group" and ident.get("type", "") == "ProductGroup"
				):
					filename = os.path.join(self.__productGroupsFile)
				elif objType == "HostGroup" or (
					objType == "Group" and ident.get("type", "") == "HostGroup"
				):
					filename = os.path.join(self.__clientGroupsFile)
				else:
					raise BackendUnaccomplishableError(
						"Unable to determine config file for object type '%s' and ident %s"
						% (objType, ident)
					)
			elif objType == "ObjectToGroup":
				if ident.get("groupType") in ("ProductGroup",):
					filename = os.path.join(self.__productGroupsFile)
				elif ident.get("groupType") in ("HostGroup",):
					filename = os.path.join(self.__clientGroupsFile)
				else:
					raise BackendUnaccomplishableError(
						"Unable to determine config file for object type '%s' and ident %s"
						% (objType, ident)
					)

		elif fileType == "pro":
			pVer = "_" + ident["productVersion"] + "-" + ident["packageVersion"]

			if objType == "LocalbootProduct":
				filename = os.path.join(
					self.__productDir, ident["id"] + pVer + ".localboot"
				)
			elif objType == "NetbootProduct":
				filename = os.path.join(
					self.__productDir, ident["id"] + pVer + ".netboot"
				)
			elif objType in (
				"Product",
				"ProductProperty",
				"UnicodeProductProperty",
				"BoolProductProperty",
				"ProductDependency",
			):
				pId = None
				if objType == "Product":
					pId = ident["id"]
				else:
					pId = ident["productId"]
				# instead of searching the whole dir, let's check the only possible files
				if os.path.isfile(
					os.path.join(self.__productDir, pId + pVer + ".localboot")
				):
					filename = os.path.join(
						self.__productDir, pId + pVer + ".localboot"
					)
				elif os.path.isfile(
					os.path.join(self.__productDir, pId + pVer + ".netboot")
				):
					filename = os.path.join(self.__productDir, pId + pVer + ".netboot")

		elif fileType == "sw":
			if objType == "AuditSoftware":
				filename = os.path.join(self.__auditDir, "global.sw")
			elif objType == "AuditSoftwareOnClient":
				filename = os.path.join(self.__auditDir, ident["clientId"] + ".sw")

		elif fileType == "hw":
			if objType == "AuditHardware":
				filename = os.path.join(self.__auditDir, "global.hw")
			elif objType == "AuditHardwareOnHost":
				filename = os.path.join(self.__auditDir, ident["hostId"] + ".hw")

		if filename is None:
			raise BackendError(
				f"No config-file returned! objType '{objType}', ident '{ident}', fileType '{fileType}'"
			)

		if objType in (
			"ConfigState",
			"ProductOnDepot",
			"ProductOnClient",
			"ProductPropertyState",
		):
			if os.path.isfile(filename):
				return filename
			raise BackendIOError(
				f"{objType} needs existing file '{filename}' ident '{ident}', fileType '{fileType}'"
			)

		logger.trace("Returning config file '%s'", filename)
		return filename

	def _getIdents(self, objType: str, **filter) -> list[dict[str, Any]]:
		logger.debug("Getting idents for '%s' with filter '%s'", objType, filter)
		objIdents = []

		if objType in ("Config", "UnicodeConfig", "BoolConfig"):
			filename = self._getConfigFile(objType, {}, "ini")
			if os.path.isfile(filename):
				iniFile = IniFile(filename=filename, ignoreCase=False)
				cp = iniFile.parse()
				for section in cp.sections():
					objIdents.append({"id": section})

		elif objType in ("OpsiClient", "ProductOnClient"):
			if objType == "OpsiClient" and filter.get("id"):
				idFilter = {"id": filter["id"]}
			elif objType == "ProductOnClient" and filter.get("clientId"):
				idFilter = {"id": filter["clientId"]}
			else:
				idFilter = {}

			for entry in os.listdir(self.__clientConfigDir):
				if not entry.lower().endswith(".ini"):
					logger.trace("Ignoring invalid client file '%s'", entry)
					continue

				try:
					hostId = forceHostId(entry[:-4])
				except Exception:
					logger.warning("Ignoring invalid client file '%s'", entry)
					continue

				if idFilter and not self._objectHashMatches({"id": hostId}, **idFilter):
					continue

				if objType == "ProductOnClient":
					filename = self._getConfigFile(objType, {"clientId": hostId}, "ini")
					iniFile = IniFile(filename=filename, ignoreCase=False)
					cp = iniFile.parse()

					for section in cp.sections():
						if section.endswith("-state"):
							objIdents.append(
								{
									"productId": section[:-6],
									"productType": cp.get(section, "productType"),
									"clientId": hostId,
								}
							)
				else:
					objIdents.append({"id": hostId})

		elif objType in ("OpsiDepotserver", "OpsiConfigserver", "ProductOnDepot"):
			if objType in ("OpsiDepotserver", "OpsiConfigserver") and filter.get("id"):
				idFilter = {"id": filter["id"]}
			elif objType == "ProductOnDepot" and filter.get("depotId"):
				idFilter = {"id": filter["depotId"]}
			else:
				idFilter = {}

			if not os.path.isdir(self.__depotConfigDir):
				raise BackendMissingDataError(
					f"Directory {self.__depotConfigDir} does not exist"
				)

			for entry in os.listdir(self.__depotConfigDir):
				if not entry.lower().endswith(".ini"):
					logger.trace("Ignoring invalid depot file '%s'", entry)
					continue

				try:
					hostId = forceHostId(entry[:-4])
				except Exception:
					logger.warning("Ignoring invalid depot file '%s'", entry)
					continue

				if idFilter and not self._objectHashMatches({"id": hostId}, **idFilter):
					continue

				if objType == "OpsiConfigserver" and hostId != self.__serverId:
					continue

				if objType == "ProductOnDepot":
					filename = self._getConfigFile(objType, {"depotId": hostId}, "ini")
					iniFile = IniFile(filename=filename, ignoreCase=False)
					cp = iniFile.parse()

					for section in cp.sections():
						if section.endswith("-state"):
							objIdents.append(
								{
									"productId": section[:-6],
									"productType": cp.get(section, "producttype"),
									"productVersion": cp.get(section, "productversion"),
									"packageVersion": cp.get(section, "packageversion"),
									"depotId": hostId,
								}
							)
				else:
					objIdents.append({"id": hostId})

		elif objType in (
			"Product",
			"LocalbootProduct",
			"NetbootProduct",
			"ProductProperty",
			"UnicodeProductProperty",
			"BoolProductProperty",
			"ProductDependency",
		):
			if objType in (
				"Product",
				"LocalbootProduct",
				"NetbootProduct",
			) and filter.get("id"):
				idFilter = {"id": filter["id"]}
			elif objType in (
				"ProductProperty",
				"UnicodeProductProperty",
				"BoolProductProperty",
				"ProductDependency",
			) and filter.get("productId"):
				idFilter = {"id": filter["productId"]}
			else:
				idFilter = {}

			for entry in os.listdir(self.__productDir):
				match = None

				if entry.endswith(".localboot"):
					if objType == "NetbootProduct":
						continue
				elif entry.endswith(".netboot"):
					if objType == "LocalbootProduct":
						continue
				else:
					logger.trace("Ignoring invalid product file '%s'", entry)
					continue

				match = self.PRODUCT_FILENAME_REGEX.search(entry)
				if not match:
					logger.warning("Ignoring invalid product file '%s'", entry)
					continue

				if idFilter and not self._objectHashMatches(
					{"id": match.group(1)}, **idFilter
				):
					continue

				logger.trace(
					"Found match: id='%s', productVersion='%s', packageVersion='%s'"
					% (match.group(1), match.group(2), match.group(3))
				)

				if objType in ("Product", "LocalbootProduct", "NetbootProduct"):
					objIdents.append(
						{
							"id": match.group(1),
							"productVersion": match.group(2),
							"packageVersion": match.group(3),
						}
					)

				elif objType in (
					"ProductProperty",
					"UnicodeProductProperty",
					"BoolProductProperty",
					"ProductDependency",
				):
					filename = os.path.join(self.__productDir, entry)
					packageControlFile = PackageControlFile(filename=filename)
					if objType == "ProductDependency":
						for (
							productDependency
						) in packageControlFile.getProductDependencies():
							objIdents.append(
								productDependency.getIdent(returnType="dict")
							)
					else:
						for (
							productProperty
						) in packageControlFile.getProductProperties():
							objIdents.append(
								productProperty.getIdent(returnType="dict")
							)

		elif objType in ("ConfigState", "ProductPropertyState"):
			for path in (self.__depotConfigDir, self.__clientConfigDir):
				for entry in os.listdir(path):
					filename = os.path.join(path, entry)

					if not entry.lower().endswith(".ini"):
						logger.trace("Ignoring invalid file '%s'", filename)
						continue

					try:
						objectId = forceHostId(entry[:-4])
					except Exception as err:
						logger.warning("Ignoring invalid file '%s': %s", filename, err)
						continue

					if not self._objectHashMatches({"objectId": objectId}, **filter):
						continue

					iniFile = IniFile(filename=filename, ignoreCase=False)
					cp = iniFile.parse()

					if objType == "ConfigState" and cp.has_section("generalconfig"):
						for option in cp.options("generalconfig"):
							objIdents.append({"configId": option, "objectId": objectId})
					elif objType == "ProductPropertyState":
						for section in cp.sections():
							if not section.endswith("-install"):
								continue

							for option in cp.options(section):
								objIdents.append(
									{
										"productId": section[:-8],
										"propertyId": option,
										"objectId": objectId,
									}
								)

		elif objType in ("Group", "HostGroup", "ProductGroup", "ObjectToGroup"):
			if objType == "ObjectToGroup":
				if filter.get("groupType"):
					passes = [
						{
							"filename": self._getConfigFile(
								objType, {"groupType": filter["groupType"]}, "ini"
							),
							"groupType": filter["groupType"],
						}
					]
				else:
					passes = [
						{
							"filename": self._getConfigFile(
								objType, {"groupType": "ProductGroup"}, "ini"
							),
							"groupType": "ProductGroup",
						},
						{
							"filename": self._getConfigFile(
								objType, {"groupType": "HostGroup"}, "ini"
							),
							"groupType": "HostGroup",
						},
					]
			else:
				if objType in ("HostGroup", "ProductGroup"):
					passes = [
						{
							"filename": self._getConfigFile(objType, {}, "ini"),
							"groupType": objType,
						}
					]
				elif filter.get("type"):
					passes = [
						{
							"filename": self._getConfigFile(
								objType, {"type": filter["type"]}, "ini"
							),
							"groupType": filter["type"],
						}
					]
				else:
					passes = [
						{
							"filename": self._getConfigFile(
								objType, {"type": "ProductGroup"}, "ini"
							),
							"groupType": "ProductGroup",
						},
						{
							"filename": self._getConfigFile(
								objType, {"type": "HostGroup"}, "ini"
							),
							"groupType": "HostGroup",
						},
					]

			for _pass in passes:
				groupType = _pass["groupType"]
				iniFile = IniFile(filename=_pass["filename"], ignoreCase=False)
				cp = iniFile.parse()

				for section in cp.sections():
					if objType == "ObjectToGroup":
						for option in cp.options(section):
							if option in ("description", "notes", "parentgroupid"):
								continue

							try:
								value = cp.get(section, option)
								if not forceBool(value):
									logger.debug(
										"Skipping '%s' in section '%s' with False-value '%s'",
										option,
										section,
										value,
									)
									continue
								if groupType == "HostGroup":
									option = forceHostId(option)
								elif groupType == "ProductGroup":
									option = forceProductId(option)

								objIdents.append(
									{
										"groupType": groupType,
										"groupId": section,
										"objectId": option,
									}
								)
							except Exception as err:
								logger.error(
									"Found invalid option '%s' in section '%s' in file '%s': %s",
									option,
									section,
									_pass["filename"],
									err,
								)
					else:
						objIdents.append({"id": section, "type": groupType})

		elif objType in (
			"AuditSoftware",
			"AuditSoftwareOnClient",
			"AuditHardware",
			"AuditHardwareOnHost",
		):
			if objType in ("AuditHardware", "AuditHardwareOnHost"):
				fileType = "hw"
			else:
				fileType = "sw"

			filenames = []
			if objType in ("AuditSoftware", "AuditHardware"):
				filename = self._getConfigFile(objType, {}, fileType)
				if os.path.isfile(filename):
					filenames.append(filename)
			else:
				idFilter = {}
				if objType == "AuditSoftwareOnClient" and filter.get("clientId"):
					idFilter = {"id": filter["clientId"]}
				elif objType == "AuditHardwareOnHost" and filter.get("hostId"):
					idFilter = {"id": filter["hostId"]}

				for entry in os.listdir(self.__auditDir):
					entry = entry.lower()
					filename = None

					if entry in ("global.sw", "global.hw"):
						continue

					if not entry.endswith(".%s" % fileType):
						logger.trace("Ignoring invalid file '%s'" % (entry))

					try:
						if idFilter and not self._objectHashMatches(
							{"id": forceHostId(entry[:-3])}, **idFilter
						):
							continue
					except Exception:
						logger.warning("Ignoring invalid file '%s'", entry)
						continue

					filenames.append(os.path.join(self.__auditDir, entry))

			for filename in filenames:
				iniFile = IniFile(filename=filename)
				cp = iniFile.parse()

				for section in cp.sections():
					if objType in ("AuditSoftware", "AuditSoftwareOnClient"):
						objIdent = {
							"name": None,
							"version": None,
							"subVersion": None,
							"language": None,
							"architecture": None,
						}

						for key in list(objIdent):
							option = key.lower()
							if cp.has_option(section, option):
								objIdent[key] = self.__unescape(cp.get(section, option))

						if objType == "AuditSoftwareOnClient":
							objIdent["clientId"] = os.path.basename(filename)[:-3]
					else:
						objIdent = {}

						for key, value in cp.items(section):
							objIdent[str(key)] = self.__unescape(value)

						if objType == "AuditHardwareOnHost":
							objIdent["hostId"] = os.path.basename(filename)[:-3]

					objIdents.append(objIdent)

		else:
			logger.warning("Unhandled objType '%s'", objType)

		if not objIdents:
			logger.trace("Could not retrieve any idents, returning empty list.")
			return []

		needFilter = False
		for attribute in objIdents[0].keys():
			if filter.get(attribute):
				needFilter = True
				break

		if not needFilter:
			logger.trace("Returning idents without filter.")
			return objIdents

		return [
			ident for ident in objIdents if self._objectHashMatches(ident, **filter)
		]

	@staticmethod
	def _adaptObjectHashAttributes(
		objHash: dict[str, Any], ident: dict[str, Any], attributes: list[str]
	) -> dict[str, Any]:
		logger.trace(
			"Adapting objectHash with '%s', '%s', '%s'", objHash, ident, attributes
		)
		if not attributes:
			return objHash

		toDelete = set()
		for attribute in objHash.keys():
			if attribute not in attributes and attribute not in ident:
				toDelete.add(attribute)

		for attribute in toDelete:
			del objHash[attribute]

		return objHash

	def _read(self, objType: str, attributes: list[str], **filter) -> list[Any]:
		if filter.get("type"):
			match = False
			for objectType in forceList(filter["type"]):
				if objectType == objType:
					match = True
					break
				Class = eval(objectType)
				for subClass in Class.subClasses:
					if subClass == objType:
						match = True
						break
				Class = eval(objType)
				for subClass in Class.subClasses:
					if subClass == objectType:
						match = True
						break
				if match:
					break

			if not match:
				logger.debug(
					"Object type '%s' does not match filter %s", objType, filter
				)
				return []

		if objType not in self._mappings:
			raise BackendUnaccomplishableError(
				"Mapping not found for object type '%s'" % objType
			)

		logger.trace("Now reading '%s' with:" % (objType))
		logger.trace("   Attributes: '%s'" % (attributes))
		logger.trace("   Filter: '%s'" % (filter))

		mappings = {}
		for mapping in self._mappings[objType]:
			if (not attributes or mapping["attribute"] in attributes) or mapping[
				"attribute"
			] in filter:
				if mapping["fileType"] not in mappings:
					mappings[mapping["fileType"]] = []

				mappings[mapping["fileType"]].append(mapping)

		logger.trace("Using mappings %s" % mappings)

		packageControlFileCache = {}
		iniFileCache = {}
		hostKeys = None

		objects = []
		for ident in self._getIdents(objType, **filter):
			objHash = dict(ident)

			for fileType, mapping in mappings.items():
				filename = self._getConfigFile(objType, ident, fileType)

				if not os.path.exists(os.path.dirname(filename)):
					raise BackendIOError(
						"Directory '%s' not found" % os.path.dirname(filename)
					)

				if fileType == "key":
					if not hostKeys:
						hostKeys = HostKeyFile(filename=filename)
						hostKeys.parse()

					for _mapping in mapping:
						objHash[_mapping["attribute"]] = hostKeys.getOpsiHostKey(
							ident["id"]
						)

				elif fileType == "ini":
					try:
						cp = iniFileCache[filename]
					except KeyError:
						iniFile = IniFile(filename=filename, ignoreCase=False)
						cp = iniFileCache[filename] = iniFile.parse()

					if cp.has_section(
						"LocalbootProduct_product_states"
					) or cp.has_section("NetbootProduct_product_states"):
						if cp.has_section("LocalbootProduct_product_states"):
							if not cp.has_section("localboot_product_states"):
								cp.add_section("localboot_product_states")

							for key, val in cp.items("LocalbootProduct_product_states"):
								cp.set("localboot_product_states", key, val)

							cp.remove_section("LocalbootProduct_product_states")
						if cp.has_section("NetbootProduct_product_states"):
							if not cp.has_section("netboot_product_states"):
								cp.add_section("netboot_product_states")

							for key, val in cp.items("NetbootProduct_product_states"):
								cp.set("netboot_product_states", key, val)

							cp.remove_section("NetbootProduct_product_states")
						IniFile(filename=filename, ignoreCase=False).generate(cp)

					for _mapping in mapping:
						attribute = _mapping["attribute"]
						section = _mapping["section"]
						option = _mapping["option"]

						match = self.PLACEHOLDER_REGEX.search(section)
						if match:
							section = "%s%s%s" % (
								match.group(1),
								objHash[match.group(2)],
								match.group(3),
							)
							if (
								objType == "ProductOnClient"
							):  # <productType>_product_states
								section = section.replace(
									"LocalbootProduct", "localboot"
								).replace("NetbootProduct", "netboot")

						match = self.PLACEHOLDER_REGEX.search(option)
						if match:
							option = "%s%s%s" % (
								match.group(1),
								objHash[match.group(2)],
								match.group(3),
							)

						if cp.has_option(section, option):
							value = cp.get(section, option)
							if _mapping.get("json"):
								value = fromJson(value)
							elif isinstance(value, str):
								value = self.__unescape(value)

							# Invalid values will throw exceptions later
							if objType == "ProductOnClient" and section.endswith(
								"_product_states"
							):
								index = value.find(":")
								if index == -1:
									raise BackendBadValueError(
										f"No ':' found in section '{section}' in option '{option}' in '{filename}'"
									)

								if attribute == "installationStatus":
									value = value[:index]
								elif attribute == "actionRequest":
									value = value[index + 1 :]

							objHash[attribute] = value
						elif (
							objType == "ProductOnClient"
							and attribute.lower() == "installationstatus"
						):
							objHash[attribute] = "not_installed"
						elif (
							objType == "ProductOnClient"
							and attribute.lower() == "actionrequest"
						):
							objHash[attribute] = "none"

					logger.trace("Got object hash from ini file: %s" % objHash)

				elif fileType == "pro":
					try:
						packageControlFile = packageControlFileCache[filename]
					except KeyError:
						packageControlFileCache[filename] = PackageControlFile(
							filename=filename
						)
						packageControlFileCache[filename].parse()
						packageControlFile = packageControlFileCache[filename]

					if objType in ("Product", "LocalbootProduct", "NetbootProduct"):
						objHash = packageControlFile.getProduct().toHash()

					elif objType in (
						"ProductProperty",
						"UnicodeProductProperty",
						"BoolProductProperty",
						"ProductDependency",
					):
						if objType == "ProductDependency":
							knownObjects = packageControlFile.getProductDependencies()
						else:
							knownObjects = packageControlFile.getProductProperties()

						for obj in knownObjects:
							objIdent = obj.getIdent(returnType="dict")
							matches = True
							for key, value in ident.items():
								if objIdent[key] != value:
									matches = False
									break

							if matches:
								objHash = obj.toHash()
								break

			Class = eval(objType)
			if self._objectHashMatches(Class.fromHash(objHash).toHash(), **filter):
				if (
					Class is Config
					and "possibleValues" in objHash
					and objHash["possibleValues"]
				):
					if (
						len(objHash["possibleValues"]) == 2
						and True in objHash["possibleValues"]
						and False in objHash["possibleValues"]
						and not objHash["editable"]
						and not objHash["multiValue"]
					):
						Class = BoolConfig
					else:
						Class = UnicodeConfig

				if (
					Class is ProductProperty
					and "possibleValues" in objHash
					and objHash["possibleValues"]
				):
					if (
						len(objHash["possibleValues"]) == 2
						and True in objHash["possibleValues"]
						and False in objHash["possibleValues"]
						and not objHash["editable"]
						and not objHash["multiValue"]
					):
						Class = BoolProductProperty
					else:
						Class = UnicodeProductProperty

				if Class is Group:
					filename = self._getConfigFile(objType, ident, "ini")
					if "clientgroups" in filename:
						Class = HostGroup
					else:
						Class = ProductGroup
				objHash = self._adaptObjectHashAttributes(objHash, ident, attributes)
				objects.append(Class.fromHash(objHash))

		for obj in objects:
			logger.trace("Returning object: %s" % obj.getIdent())

		return objects

	def _write(self, obj: Any, mode: str = "create") -> None:
		objType = obj.getType()

		if objType == "OpsiConfigserver":
			if self.__serverId != obj.getId():
				raise BackendUnaccomplishableError(
					f"Filebackend can only handle this config server '{self.__serverId}', not '{obj.getId()}'"
				)

		if objType not in self._mappings:
			raise BackendUnaccomplishableError(
				"Mapping not found for object type '%s'" % objType
			)

		mappings = {}
		for mapping in self._mappings[objType]:
			if mapping["fileType"] not in mappings:
				mappings[mapping["fileType"]] = {}
			mappings[mapping["fileType"]][mapping["attribute"]] = mapping

		for fileType, mapping in mappings.items():
			filename = self._getConfigFile(
				objType, obj.getIdent(returnType="dict"), fileType
			)

			if fileType == "key":
				if mode == "create" or (mode == "update" and obj.getOpsiHostKey()):
					if not os.path.exists(filename):
						self._touch(filename)

					hostKeys = HostKeyFile(filename=filename)
					hostKeys.setOpsiHostKey(obj.getId(), obj.getOpsiHostKey())
					hostKeys.generate()

			elif fileType == "ini":
				iniFile = IniFile(filename=filename, ignoreCase=False)
				if mode == "create":
					if objType == "OpsiClient" and not iniFile.exists():
						proto = os.path.join(
							self.__clientTemplateDir, os.path.basename(filename)
						)
						if not os.path.isfile(proto):
							proto = self.__defaultClientTemplatePath
						shutil.copyfile(proto, filename)

					self._touch(filename)

				cp = iniFile.parse()

				if mode == "create":
					removeSections = []
					removeOptions = {}
					if objType in ("OpsiClient", "OpsiDepotserver", "OpsiConfigserver"):
						removeSections = [
							"info",
							"depotserver",
							"depotshare",
							"repository",
						]
					elif objType in ("Config", "UnicodeConfig", "BoolConfig"):
						removeSections = [obj.getId()]
					elif objType in ("Group", "HostGroup", "ProductGroup"):
						removeOptions[obj.getId()] = []
						for _mapping in mapping.values():
							removeOptions[obj.getId()].append(_mapping["option"])
					elif objType in ("ProductOnDepot", "ProductOnClient"):
						removeSections = [obj.getProductId() + "-state"]

					for section in removeSections:
						if cp.has_section(section):
							cp.remove_section(section)

					for section, options in removeOptions.items():
						if cp.has_section(section):
							for option in options:
								if cp.has_option(section, option):
									cp.remove_option(section, option)

				objHash = obj.toHash()

				for attribute, value in objHash.items():
					if value is None and mode == "update":
						continue

					attributeMapping = mapping.get(attribute, mapping.get("*"))

					if attributeMapping is not None:
						section = attributeMapping["section"]
						option = attributeMapping["option"]

						match = self.PLACEHOLDER_REGEX.search(section)
						if match:
							section = "%s%s%s" % (
								match.group(1),
								objHash[match.group(2)],
								match.group(3),
							)
							if objType == "ProductOnClient":
								section = section.replace(
									"LocalbootProduct", "localboot"
								).replace("NetbootProduct", "netboot")

						match = self.PLACEHOLDER_REGEX.search(option)
						if match:
							option = "%s%s%s" % (
								match.group(1),
								objHash[match.group(2)],
								match.group(3),
							)

						if not cp.has_section(section):
							cp.add_section(section)

						if objType == "ProductOnClient":
							if attribute in ("installationStatus", "actionRequest"):
								(installationStatus, actionRequest) = (
									"not_installed",
									"none",
								)

								if cp.has_option(section, option):
									combined = cp.get(section, option)
								else:
									combined = ""

								if ":" in combined:
									(installationStatus, actionRequest) = (
										combined.split(":", 1)
									)
								elif combined:
									installationStatus = combined

								if value is not None:
									if attribute == "installationStatus":
										installationStatus = value
									elif attribute == "actionRequest":
										actionRequest = value
								value = installationStatus + ":" + actionRequest
						elif objType == "ObjectToGroup":
							value = 1

						if value is not None:
							if attributeMapping.get("json"):
								value = toJson(value)
							elif isinstance(value, str):
								value = self.__escape(value)

							cp.set(section, option, value)

				iniFile.setSectionSequence(
					[
						"info",
						"generalconfig",
						"localboot_product_states",
						"netboot_product_states",
					]
				)
				iniFile.generate(cp)

			elif fileType == "pro":
				if not os.path.exists(filename):
					self._touch(filename)
				packageControlFile = PackageControlFile(filename=filename)

				if objType in ("Product", "LocalbootProduct", "NetbootProduct"):
					if mode == "create":
						packageControlFile.setProduct(obj)
					else:
						productHash = packageControlFile.getProduct().toHash()
						for attribute, value in obj.toHash().items():
							if value is None:
								continue
							productHash[attribute] = value
						packageControlFile.setProduct(Product.fromHash(productHash))
				elif objType in (
					"ProductProperty",
					"UnicodeProductProperty",
					"BoolProductProperty",
					"ProductDependency",
				):
					if objType == "ProductDependency":
						currentObjects = packageControlFile.getProductDependencies()
					else:
						currentObjects = packageControlFile.getProductProperties()

					found = False
					for i, currentObj in enumerate(currentObjects):
						if currentObj.getIdent(returnType="unicode") == obj.getIdent(
							returnType="unicode"
						):
							if mode == "create":
								currentObjects[i] = obj
							else:
								newHash = currentObj.toHash()
								for attribute, value in obj.toHash().items():
									if value is not None:
										newHash[attribute] = value

								Class = eval(objType)
								currentObjects[i] = Class.fromHash(newHash)
							found = True
							break

					if not found:
						currentObjects.append(obj)

					if objType == "ProductDependency":
						packageControlFile.setProductDependencies(currentObjects)
					else:
						packageControlFile.setProductProperties(currentObjects)

				packageControlFile.generate()

	def _delete(self, objList: list[Any]) -> None:
		if not objList:
			return

		# objType is not always correct, but _getConfigFile() is
		# within ifs obj.getType() from obj in objList should be used
		objType = objList[0].getType()

		if objType in ("OpsiClient", "OpsiConfigserver", "OpsiDepotserver"):
			hostKeyFile = HostKeyFile(self._getConfigFile("", {}, "key"))
			for obj in objList:
				if obj.getId() == self.__serverId:
					logger.warning(
						"Cannot delete %s '%s', ignored.", obj.getType(), obj.getId()
					)
					continue

				logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
				hostKeyFile.deleteOpsiHostKey(obj.getId())

				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "ini"
				)
				if os.path.isfile(filename):
					os.unlink(filename)
			hostKeyFile.generate()

		elif objType in ("Config", "UnicodeConfig", "BoolConfig"):
			filename = self._getConfigFile(objType, {}, "ini")
			iniFile = IniFile(filename=filename, ignoreCase=False)
			cp = iniFile.parse()
			for obj in objList:
				logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
				if cp.has_section(obj.getId()):
					cp.remove_section(obj.getId())
					logger.trace("Removed section '%s'" % obj.getId())
			iniFile.generate(cp)

		elif objType == "ConfigState":
			filenames = set(
				self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "ini"
				)
				for obj in objList
			)

			for filename in filenames:
				iniFile = IniFile(filename=filename, ignoreCase=False)
				cp = iniFile.parse()
				for obj in objList:
					if obj.getObjectId() != os.path.basename(filename)[:-4]:
						continue

					logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
					if cp.has_option("generalconfig", obj.getConfigId()):
						cp.remove_option("generalconfig", obj.getConfigId())
						logger.trace(
							"Removed option in generalconfig '%s'" % obj.getConfigId()
						)

				iniFile.generate(cp)

		elif objType in ("Product", "LocalbootProduct", "NetbootProduct"):
			for obj in objList:
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "pro"
				)
				logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
				if os.path.isfile(filename):
					os.unlink(filename)
					logger.trace("Removed file '%s'" % filename)

		elif objType in (
			"ProductProperty",
			"UnicodeProductProperty",
			"BoolProductProperty",
			"ProductDependency",
		):
			filenames = set(
				self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "pro"
				)
				for obj in objList
			)

			for filename in filenames:
				packageControlFile = PackageControlFile(filename=filename)

				if objType == "ProductDependency":
					oldList = packageControlFile.getProductDependencies()
				else:
					oldList = packageControlFile.getProductProperties()

				newList = []
				for oldItem in oldList:
					delete = False
					obj = None
					for obj in objList:
						if oldItem.getIdent(returnType="unicode") == obj.getIdent(
							returnType="unicode"
						):
							delete = True
							break
					if delete:
						logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
					else:
						newList.append(oldItem)

				if objType == "ProductDependency":
					packageControlFile.setProductDependencies(newList)
				else:
					packageControlFile.setProductProperties(newList)

				packageControlFile.generate()

		elif objType in ("ProductOnDepot", "ProductOnClient"):
			filenames = set(
				self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "ini"
				)
				for obj in objList
			)

			for filename in filenames:
				iniFile = IniFile(filename=filename, ignoreCase=False)
				cp = iniFile.parse()

				for obj in objList:
					logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
					if cp.has_section(obj.getProductId() + "-state"):
						cp.remove_section(obj.getProductId() + "-state")
						logger.trace(
							"Removed section '%s'" % obj.getProductId() + "-state"
						)

				iniFile.generate(cp)

		elif objType == "ProductPropertyState":
			for obj in objList:
				logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType="dict"), "ini"
				)
				iniFile = IniFile(filename=filename, ignoreCase=False)
				cp = iniFile.parse()

				section = obj.getProductId() + "-install"
				option = obj.getPropertyId()

				if cp.has_option(section, option):
					cp.remove_option(section, option)
					logger.trace(
						"Removed option '%s' in section '%s'" % (option, section)
					)

				if cp.has_section(section) and len(cp.options(section)) == 0:
					cp.remove_section(section)
					logger.trace("Removed empty section '%s'" % section)

				iniFile.generate(cp)

		elif objType in ("Group", "HostGroup", "ProductGroup", "ObjectToGroup"):
			passes = [
				{
					"filename": self._getConfigFile(
						"Group", {"type": "ProductGroup"}, "ini"
					),
					"groupType": "ProductGroup",
				},
				{
					"filename": self._getConfigFile(
						"Group", {"type": "HostGroup"}, "ini"
					),
					"groupType": "HostGroup",
				},
			]
			for _pass in passes:
				groupType = _pass["groupType"]
				iniFile = IniFile(filename=_pass["filename"], ignoreCase=False)
				cp = iniFile.parse()

				for obj in objList:
					section = None
					if obj.getType() == "ObjectToGroup":
						if obj.groupType not in ("HostGroup", "ProductGroup"):
							raise BackendBadValueError(
								"Unhandled group type '%s'" % obj.groupType
							)
						if not groupType == obj.groupType:
							continue
						section = obj.getGroupId()
					else:
						if not groupType == obj.getType():
							continue
						section = obj.getId()

					logger.debug("Deleting %s: '%s'", obj.getType(), obj.getIdent())
					if obj.getType() == "ObjectToGroup":
						if cp.has_option(section, obj.getObjectId()):
							cp.remove_option(section, obj.getObjectId())
							logger.trace(
								"Removed option '%s' in section '%s'"
								% (obj.getObjectId(), section)
							)
					else:
						if cp.has_section(section):
							cp.remove_section(section)
							logger.trace("Removed section '%s'" % section)

				iniFile.generate(cp)
		else:
			logger.warning(
				"_delete(): unhandled objType: '%s' object: %s", objType, objlist[0]
			)

	def getData(self, query: str) -> Any:
		raise BackendConfigurationError(
			"You have tried to execute a method, that will not work with filebackend."
		)

	def getRawData(self, query: str) -> Any:
		raise BackendConfigurationError(
			"You have tried to execute a method, that will not work with filebackend."
		)

	# Hosts
	def host_insertObject(self, host: Host) -> None:
		host = forceObjectClass(host, Host)
		ConfigDataBackend.host_insertObject(self, host)

		logger.debug("Inserting host: '%s'", host.getIdent())
		self._write(host, mode="create")

	def host_updateObject(self, host: Host) -> None:
		host = forceObjectClass(host, Host)
		ConfigDataBackend.host_updateObject(self, host)

		logger.debug("Updating host: '%s'", host.getIdent())
		self._write(host, mode="update")

	def host_getObjects(self, attributes: list[str] = None, **filter) -> list[Host]:
		attributes = attributes or []
		ConfigDataBackend.host_getObjects(self, attributes, **filter)

		logger.debug("Getting hosts ...")
		result = self._read("OpsiDepotserver", attributes, **filter)
		opsiConfigServers = self._read("OpsiConfigserver", attributes, **filter)

		if opsiConfigServers:
			contained = False
			for i, currentResult in enumerate(result):
				if currentResult.getId() == opsiConfigServers[0].getId():
					result[i] = opsiConfigServers[0]
					contained = True
					break

			if not contained:
				result.append(opsiConfigServers[0])
		result.extend(self._read("OpsiClient", attributes, **filter))

		return result

	def host_deleteObjects(self, hosts: list[Host]) -> None:
		ConfigDataBackend.host_deleteObjects(self, hosts)

		logger.debug("Deleting hosts ...")
		self._delete(forceObjectClassList(hosts, Host))

	# Configs
	def config_insertObject(self, config: Config) -> None:
		config = forceObjectClass(config, Config)
		ConfigDataBackend.config_insertObject(self, config)

		logger.debug("Inserting config: '%s'", config.getIdent())
		self._write(config, mode="create")

	def config_updateObject(self, config: Config) -> None:
		config = forceObjectClass(config, Config)
		ConfigDataBackend.config_updateObject(self, config)

		logger.debug("Updating config: '%s'", config.getIdent())
		self._write(config, mode="update")

	def config_getObjects(self, attributes: list[str] = None, **filter):
		attributes = attributes or []
		ConfigDataBackend.config_getObjects(self, attributes, **filter)

		logger.debug("Getting configs ...")
		return self._read("Config", attributes, **filter)

	def config_deleteObjects(self, configs: list[Config]) -> None:
		ConfigDataBackend.config_deleteObjects(self, configs)

		logger.debug("Deleting configs ...")
		self._delete(forceObjectClassList(configs, Config))

	# ConfigStates
	def configState_insertObject(self, configState: ConfigState) -> None:
		configState = forceObjectClass(configState, ConfigState)
		ConfigDataBackend.configState_insertObject(self, configState)

		logger.debug("Inserting configState: '%s'", configState.getIdent())
		self._write(configState, mode="create")

	def configState_updateObject(self, configState: ConfigState) -> None:
		configState = forceObjectClass(configState, ConfigState)
		ConfigDataBackend.configState_updateObject(self, configState)

		logger.debug("Updating configState: '%s'", configState.getIdent())
		self._write(configState, mode="update")

	def configState_getObjects(self, attributes: list[str] = None, **filter):
		attributes = attributes or []
		ConfigDataBackend.configState_getObjects(self, attributes, **filter)

		logger.debug("Getting configStates ...")
		return self._read("ConfigState", attributes, **filter)

	def configState_deleteObjects(self, configStates: list[ConfigState]) -> None:
		ConfigDataBackend.configState_deleteObjects(self, configStates)

		logger.debug("Deleting configStates ...")
		self._delete(forceObjectClassList(configStates, ConfigState))

	# Products
	def product_insertObject(self, product: Product) -> None:
		product = forceObjectClass(product, Product)
		ConfigDataBackend.product_insertObject(self, product)

		logger.debug("Inserting product: '%s'", product.getIdent())
		self._write(product, mode="create")

	def product_updateObject(self, product: Product) -> None:
		product = forceObjectClass(product, Product)
		ConfigDataBackend.product_updateObject(self, product)

		logger.debug("Updating product: '%s'", product.getIdent())
		self._write(product, mode="update")

	def product_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[Product]:
		attributes = attributes or []
		ConfigDataBackend.product_getObjects(self, attributes, **filter)

		logger.debug("Getting products ...")
		result = self._read("LocalbootProduct", attributes, **filter)
		result.extend(self._read("NetbootProduct", attributes, **filter))

		return result

	def product_deleteObjects(self, products: list[Product]) -> None:
		ConfigDataBackend.product_deleteObjects(self, products)

		logger.debug("Deleting products ...")
		self._delete(forceObjectClassList(products, Product))

	# ProductProperties
	def productProperty_insertObject(self, productProperty: ProductProperty) -> None:
		productProperty = forceObjectClass(productProperty, ProductProperty)
		ConfigDataBackend.productProperty_insertObject(self, productProperty)

		logger.debug("Inserting productProperty: '%s'", productProperty.getIdent())
		self._write(productProperty, mode="create")

	def productProperty_updateObject(self, productProperty: ProductProperty) -> None:
		productProperty = forceObjectClass(productProperty, ProductProperty)
		ConfigDataBackend.productProperty_updateObject(self, productProperty)

		logger.debug("Updating productProperty: '%s'", productProperty.getIdent())
		self._write(productProperty, mode="update")

	def productProperty_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductProperty]:
		attributes = attributes or []
		ConfigDataBackend.productProperty_getObjects(self, attributes, **filter)

		logger.debug("Getting productProperties ...")
		return self._read("ProductProperty", attributes, **filter)

	def productProperty_deleteObjects(
		self, productProperties: list[ProductProperty]
	) -> None:
		ConfigDataBackend.productProperty_deleteObjects(self, productProperties)

		logger.debug("Deleting productProperties ...")
		self._delete(forceObjectClassList(productProperties, ProductProperty))

	# ProductDependencies
	def productDependency_insertObject(
		self, productDependency: ProductDependency
	) -> None:
		productDependency = forceObjectClass(productDependency, ProductDependency)
		ConfigDataBackend.productDependency_insertObject(self, productDependency)

		logger.debug("Inserting productDependency: '%s'", productDependency.getIdent())
		self._write(productDependency, mode="create")

	def productDependency_updateObject(
		self, productDependency: ProductDependency
	) -> None:
		productDependency = forceObjectClass(productDependency, ProductDependency)
		ConfigDataBackend.productDependency_updateObject(self, productDependency)

		logger.debug("Updating productDependency: '%s'", productDependency.getIdent())
		self._write(productDependency, mode="update")

	def productDependency_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductDependency]:
		attributes = attributes or []
		ConfigDataBackend.productDependency_getObjects(self, attributes=[], **filter)

		logger.debug("Getting productDependencies ...")
		return self._read("ProductDependency", attributes, **filter)

	def productDependency_deleteObjects(
		self, productDependencies: list[ProductDependency]
	) -> None:
		ConfigDataBackend.productDependency_deleteObjects(self, productDependencies)

		logger.debug("Deleting productDependencies ...")
		self._delete(forceObjectClassList(productDependencies, ProductDependency))

	# ProductOnDepots
	def productOnDepot_insertObject(self, productOnDepot: ProductOnDepot) -> None:
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		ConfigDataBackend.productOnDepot_insertObject(self, productOnDepot)

		logger.debug("Inserting productOnDepot: '%s'", productOnDepot.getIdent())
		self._write(productOnDepot, mode="create")

	def productOnDepot_updateObject(self, productOnDepot: ProductOnDepot) -> None:
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		ConfigDataBackend.productOnDepot_updateObject(self, productOnDepot)

		logger.debug("Updating productOnDepot: '%s'", productOnDepot.getIdent())
		self._write(productOnDepot, mode="update")

	def productOnDepot_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductOnDepot]:
		attributes = attributes or []
		ConfigDataBackend.productOnDepot_getObjects(self, attributes=[], **filter)

		logger.debug("Getting productOnDepots ...")
		return self._read("ProductOnDepot", attributes, **filter)

	def productOnDepot_deleteObjects(
		self, productOnDepots: list[ProductOnDepot]
	) -> None:
		ConfigDataBackend.productOnDepot_deleteObjects(self, productOnDepots)

		logger.debug("Deleting productOnDepots ...")
		self._delete(forceObjectClassList(productOnDepots, ProductOnDepot))

	# ProductOnClients
	def productOnClient_insertObject(self, productOnClient: ProductOnClient) -> None:
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		ConfigDataBackend.productOnClient_insertObject(self, productOnClient)

		logger.debug("Inserting productOnClient: '%s'", productOnClient.getIdent())
		self._write(productOnClient, mode="create")

	def productOnClient_updateObject(self, productOnClient: ProductOnClient) -> None:
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		ConfigDataBackend.productOnClient_updateObject(self, productOnClient)

		logger.debug("Updating productOnClient: '%s'", productOnClient.getIdent())
		self._write(productOnClient, mode="update")

	def productOnClient_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductOnClient]:
		attributes = attributes or []
		ConfigDataBackend.productOnClient_getObjects(self, attributes=[], **filter)

		logger.debug("Getting productOnClient ...")
		return self._read("ProductOnClient", attributes, **filter)

	def productOnClient_deleteObjects(self, productOnClients: ProductOnClient) -> None:
		ConfigDataBackend.productOnClient_deleteObjects(self, productOnClients)

		logger.debug("Deleting productOnClients ...")
		self._delete(forceObjectClassList(productOnClients, ProductOnClient))

	# ProductPropertyStates
	def productPropertyState_insertObject(
		self, productPropertyState: ProductPropertyState
	) -> None:
		productPropertyState = forceObjectClass(
			productPropertyState, ProductPropertyState
		)
		ConfigDataBackend.productPropertyState_insertObject(self, productPropertyState)

		logger.debug(
			"Inserting productPropertyState: '%s'", productPropertyState.getIdent()
		)
		self._write(productPropertyState, mode="create")

	def productPropertyState_updateObject(
		self, productPropertyState: ProductPropertyState
	) -> None:
		productPropertyState = forceObjectClass(
			productPropertyState, ProductPropertyState
		)
		ConfigDataBackend.productPropertyState_updateObject(self, productPropertyState)

		logger.debug(
			"Updating productPropertyState: '%s'", productPropertyState.getIdent()
		)
		self._write(productPropertyState, mode="update")

	def productPropertyState_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductPropertyState]:
		attributes = attributes or []
		ConfigDataBackend.productPropertyState_getObjects(self, attributes=[], **filter)

		logger.debug("Getting productPropertyStates ...")
		return self._read("ProductPropertyState", attributes, **filter)

	def productPropertyState_deleteObjects(
		self, productPropertyStates: list[ProductPropertyState]
	) -> None:
		ConfigDataBackend.productPropertyState_deleteObjects(
			self, productPropertyStates
		)

		logger.debug("Deleting productPropertyStates ...")
		self._delete(forceObjectClassList(productPropertyStates, ProductPropertyState))

	# Groups
	def group_insertObject(self, group: Group) -> None:
		group = forceObjectClass(group, Group)
		ConfigDataBackend.group_insertObject(self, group)

		logger.debug("Inserting group: '%s'", group.getIdent())
		self._write(group, mode="create")

	def group_updateObject(self, group: Group) -> None:
		group = forceObjectClass(group, Group)
		ConfigDataBackend.group_updateObject(self, group)

		logger.debug("Updating group: '%s'", group.getIdent())
		self._write(group, mode="update")

	def group_getObjects(self, attributes: list[str] = None, **filter):
		attributes = attributes or []
		ConfigDataBackend.group_getObjects(self, attributes=[], **filter)

		logger.debug("Getting groups ...")
		return self._read("Group", attributes, **filter)

	def group_deleteObjects(self, groups: list[Group]) -> None:
		ConfigDataBackend.group_deleteObjects(self, groups)

		logger.debug("Deleting groups ...")
		self._delete(forceObjectClassList(groups, Group))

	# ObjectToGroups
	def objectToGroup_insertObject(self, objectToGroup: ObjectToGroup) -> None:
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		ConfigDataBackend.objectToGroup_insertObject(self, objectToGroup)

		logger.debug("Inserting objectToGroup: '%s'", objectToGroup.getIdent())
		self._write(objectToGroup, mode="create")

	def objectToGroup_updateObject(self, objectToGroup: ObjectToGroup) -> None:
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		ConfigDataBackend.objectToGroup_updateObject(self, objectToGroup)

		logger.debug("Updating objectToGroup: '%s'", objectToGroup.getIdent())
		self._write(objectToGroup, mode="update")

	def objectToGroup_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ObjectToGroup]:
		attributes = attributes or []
		ConfigDataBackend.objectToGroup_getObjects(self, attributes=[], **filter)

		logger.debug("Getting objectToGroups ...")
		return self._read("ObjectToGroup", attributes, **filter)

	def objectToGroup_deleteObjects(self, objectToGroups: list[ObjectToGroup]) -> None:
		ConfigDataBackend.objectToGroup_deleteObjects(self, objectToGroups)

		logger.debug("Deleting objectToGroups ...")
		self._delete(forceObjectClassList(objectToGroups, ObjectToGroup))

	# AuditSoftwares
	def auditSoftware_insertObject(self, auditSoftware: AuditSoftware) -> None:
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		ConfigDataBackend.auditSoftware_insertObject(self, auditSoftware)

		logger.debug("Inserting auditSoftware: '%s'", auditSoftware.getIdent())
		filename = self._getConfigFile("AuditSoftware", {}, "sw")

		if not os.path.exists(filename):
			self._touch(filename)

		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()

		auditSoftware = auditSoftware.toHash()
		for attribute in auditSoftware.keys():
			if (auditSoftware[attribute] is None) or (attribute == "type"):
				continue
			auditSoftware[attribute] = self.__escape(auditSoftware[attribute])

		newNum = 0
		removeSection = None
		for section in ini.sections():
			num = int(section.split("_")[-1])
			if num >= newNum:
				newNum = num + 1

			matches = True
			for attribute in (
				"name",
				"version",
				"subVersion",
				"language",
				"architecture",
			):
				if not ini.has_option(section, attribute):
					if auditSoftware[attribute] is not None:
						matches = False
						break
				elif ini.get(section, attribute) != auditSoftware[attribute]:
					matches = False
					break

			if matches:
				removeSection = section
				newNum = num
				logger.debug(
					"Found auditSoftware section '%s' to replace", removeSection
				)
				break

		section = "software_%d" % newNum
		if removeSection:
			ini.remove_section(removeSection)
		else:
			logger.debug("Inserting new auditSoftware section '%s'", section)

		ini.add_section(section)
		for attribute, value in auditSoftware.items():
			if value is None or attribute == "type":
				continue
			ini.set(section, attribute, value)
		iniFile.generate(ini)

	def auditSoftware_updateObject(self, auditSoftware: AuditSoftware) -> None:
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		ConfigDataBackend.auditSoftware_updateObject(self, auditSoftware)

		logger.debug("Updating auditSoftware: '%s'", auditSoftware.getIdent())
		filename = self._getConfigFile("AuditSoftware", {}, "sw")
		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()
		ident = auditSoftware.getIdent(returnType="dict")

		for section in ini.sections():
			found = True
			for key, value in ident.items():
				if self.__unescape(ini.get(section, key.lower())) != value:
					found = False
					break

			if found:
				for key, value in auditSoftware.toHash().items():
					if value is None:
						continue
					ini.set(section, key, self.__escape(value))
				iniFile.generate(ini)
				return

		raise BackendMissingDataError("AuditSoftware %s not found" % auditSoftware)

	def auditSoftware_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditSoftware]:
		attributes = attributes or []
		ConfigDataBackend.auditSoftware_getObjects(self, attributes=[], **filter)

		logger.debug("Getting auditSoftwares ...")
		filename = self._getConfigFile("AuditSoftware", {}, "sw")
		if not os.path.exists(filename):
			return []

		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()
		fastFilter = {}

		if filter:
			for attribute, value in filter.items():
				if (
					attribute
					in ("name", "version", "subVersion", "language", "architecture")
					and value
				):
					value = forceUnicodeList(value)
					if len(value) == 1 and value[0].find("*") == -1:
						fastFilter[attribute] = value[0]

		result = []
		for section in ini.sections():
			objHash = {
				"name": None,
				"version": None,
				"subVersion": None,
				"language": None,
				"architecture": None,
				"windowsSoftwareId": None,
				"windowsDisplayName": None,
				"windowsDisplayVersion": None,
				"installSize": None,
			}
			fastFiltered = False
			for key, value in objHash.items():
				try:
					value = self.__unescape(ini.get(section, key.lower()))
					if (
						fastFilter
						and value
						and key in fastFilter
						and (fastFilter[key] != value)
					):
						fastFiltered = True
						break
					objHash[key] = value
				except Exception:
					pass
			if not fastFiltered and self._objectHashMatches(objHash, **filter):
				# TODO: adaptObjHash?
				result.append(AuditSoftware.fromHash(objHash))

		return result

	def auditSoftware_deleteObjects(self, auditSoftwares: list[AuditSoftware]) -> None:
		ConfigDataBackend.auditSoftware_deleteObjects(self, auditSoftwares)

		logger.debug("Deleting auditSoftwares ...")
		filename = self._getConfigFile("AuditSoftware", {}, "sw")
		if not os.path.exists(filename):
			return
		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()
		idents = [
			auditSoftware.getIdent(returnType="dict")
			for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware)
		]

		removeSections = []
		for section in ini.sections():
			for ident in idents:
				found = True
				for key, value in ident.items():
					if self.__unescape(ini.get(section, key.lower())) != value:
						found = False
						break

				if found and section not in removeSections:
					removeSections.append(section)

		if removeSections:
			for section in removeSections:
				ini.remove_section(section)
			iniFile.generate(ini)

	# AuditSoftwareOnClients
	def auditSoftwareOnClient_insertObject(
		self, auditSoftwareOnClient: AuditSoftwareOnClient
	) -> None:
		auditSoftwareOnClient = forceObjectClass(
			auditSoftwareOnClient, AuditSoftwareOnClient
		)
		ConfigDataBackend.auditSoftwareOnClient_insertObject(
			self, auditSoftwareOnClient
		)

		logger.debug(
			"Inserting auditSoftwareOnClient: '%s'", auditSoftwareOnClient.getIdent()
		)
		filename = self._getConfigFile(
			"AuditSoftwareOnClient", {"clientId": auditSoftwareOnClient.clientId}, "sw"
		)

		if not os.path.exists(filename):
			self._touch(filename)

		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()

		auditSoftwareOnClient = auditSoftwareOnClient.toHash()
		for attribute in auditSoftwareOnClient.keys():
			if auditSoftwareOnClient[attribute] is None:
				continue
			auditSoftwareOnClient[attribute] = self.__escape(
				auditSoftwareOnClient[attribute]
			)
		newNum = 0
		removeSection = None
		for section in ini.sections():
			num = int(section.split("_")[-1])
			if num >= newNum:
				newNum = num + 1

			matches = True
			for attribute in (
				"name",
				"version",
				"subVersion",
				"language",
				"architecture",
			):
				if not ini.has_option(section, attribute):
					if auditSoftwareOnClient[attribute] is not None:
						matches = False
						break
				elif ini.get(section, attribute) != auditSoftwareOnClient[attribute]:
					matches = False
					break

			if matches:
				removeSection = section
				newNum = num
				logger.debug(
					"Found auditSoftwareOnClient section '%s' to replace", removeSection
				)
				break

		section = "software_%d" % newNum
		if removeSection:
			ini.remove_section(removeSection)
		else:
			logger.debug("Inserting new auditSoftwareOnClient section '%s'", section)

		ini.add_section(section)
		for attribute, value in auditSoftwareOnClient.items():
			if value is None:
				continue
			ini.set(section, attribute, value)
		iniFile.generate(ini)

	def auditSoftwareOnClient_updateObject(
		self, auditSoftwareOnClient: AuditSoftwareOnClient
	) -> None:
		auditSoftwareOnClient = forceObjectClass(
			auditSoftwareOnClient, AuditSoftwareOnClient
		)
		ConfigDataBackend.auditSoftwareOnClient_updateObject(
			self, auditSoftwareOnClient
		)

		logger.debug(
			"Updating auditSoftwareOnClient: '%s'", auditSoftwareOnClient.getIdent()
		)
		filename = self._getConfigFile(
			"AuditSoftwareOnClient", {"clientId": auditSoftwareOnClient.clientId}, "sw"
		)
		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()
		ident = auditSoftwareOnClient.getIdent(returnType="dict")

		for section in ini.sections():
			found = True
			for key, value in ident.items():
				if self.__unescape(ini.get(section, key.lower())) != value:
					found = False
					break

			if found:
				for key, value in auditSoftwareOnClient.toHash().items():
					if value is None:
						continue
					ini.set(section, key, self.__escape(value))
				iniFile.generate(ini)
				return

		raise BackendMissingDataError(
			"auditSoftwareOnClient %s not found" % auditSoftwareOnClient
		)

	def auditSoftwareOnClient_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditSoftwareOnClient]:
		attributes = attributes or []
		ConfigDataBackend.auditSoftwareOnClient_getObjects(
			self, attributes=[], **filter
		)

		logger.debug("Getting auditSoftwareOnClients ...")
		filenames = {}
		for ident in self._getIdents("AuditSoftwareOnClient", **filter):
			if ident["clientId"] not in filenames:
				filenames[ident["clientId"]] = self._getConfigFile(
					"AuditSoftwareOnClient", ident, "sw"
				)

		result = []
		for _clientId, filename in filenames.items():
			if not os.path.exists(filename):
				continue
			iniFile = IniFile(filename=filename)
			ini = iniFile.parse()
			for section in ini.sections():
				objHash = {
					"name": None,
					"version": None,
					"subVersion": None,
					"language": None,
					"architecture": None,
					"clientId": None,
					"uninstallString": None,
					"binaryName": None,
					"firstseen": None,
					"lastseen": None,
					"state": None,
					"usageFrequency": None,
					"lastUsed": None,
					"licenseKey": None,
				}
				for key in list(objHash):
					try:
						objHash[key] = self.__unescape(ini.get(section, key.lower()))
					except Exception:
						pass

				if self._objectHashMatches(objHash, **filter):
					result.append(AuditSoftwareOnClient.fromHash(objHash))

		return result

	def auditSoftwareOnClient_deleteObjects(
		self, auditSoftwareOnClients: list[AuditSoftwareOnClient]
	) -> None:
		ConfigDataBackend.auditSoftwareOnClient_deleteObjects(
			self, auditSoftwareOnClients
		)

		logger.debug("Deleting auditSoftwareOnClients ...")
		filenames = {}
		idents = {}
		for auditSoftwareOnClient in forceObjectClassList(
			auditSoftwareOnClients, AuditSoftwareOnClient
		):
			ident = auditSoftwareOnClient.getIdent(returnType="dict")
			try:
				idents[ident["clientId"]].append(ident)
			except KeyError:
				idents[ident["clientId"]] = [ident]

			if ident["clientId"] not in filenames:
				filenames[ident["clientId"]] = self._getConfigFile(
					"AuditSoftwareOnClient", ident, "sw"
				)

		for clientId, filename in filenames.items():
			iniFile = IniFile(filename=filename)
			ini = iniFile.parse()
			removeSections = []
			for section in ini.sections():
				for ident in idents[clientId]:
					found = True
					for key, value in ident.items():
						if self.__unescape(ini.get(section, key.lower())) != value:
							found = False
							break
					if found and section not in removeSections:
						removeSections.append(section)

			if removeSections:
				for section in removeSections:
					ini.remove_section(section)
				iniFile.generate(ini)

	# AuditHardwares
	def auditHardware_insertObject(self, auditHardware: AuditHardware) -> None:
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		ConfigDataBackend.auditHardware_insertObject(self, auditHardware)

		logger.debug("Inserting auditHardware: '%s'", auditHardware.getIdent())
		self.__doAuditHardwareObj(auditHardware, mode="insert")

	def auditHardware_updateObject(self, auditHardware: AuditHardware) -> None:
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		ConfigDataBackend.auditHardware_updateObject(self, auditHardware)

		logger.debug("Updating auditHardware: '%s'", auditHardware.getIdent())
		self.__doAuditHardwareObj(auditHardware, mode="update")

	def auditHardware_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditHardware]:
		attributes = attributes or []
		ConfigDataBackend.auditHardware_getObjects(self, attributes=[], **filter)

		logger.debug("Getting auditHardwares ...")
		filename = self._getConfigFile("AuditHardware", {}, "hw")
		if not os.path.exists(filename):
			return []

		result = []
		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()
		for section in ini.sections():
			objHash = {}
			for option in ini.options(section):
				if option.lower() == "hardwareclass":
					objHash["hardwareClass"] = self.__unescape(ini.get(section, option))
				else:
					objHash[str(option)] = self.__unescape(ini.get(section, option))

			auditHardware = AuditHardware.fromHash(objHash)
			if self._objectHashMatches(auditHardware.toHash(), **filter):
				result.append(auditHardware)

		return result

	def auditHardware_deleteObjects(self, auditHardwares: list[AuditHardware]) -> None:
		ConfigDataBackend.auditHardware_deleteObjects(self, auditHardwares)

		logger.debug("Deleting auditHardwares ...")
		# TODO: forceObjectClassList necessary?
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			self.__doAuditHardwareObj(auditHardware, mode="delete")

	# AuditHardwareOnHosts
	def auditHardwareOnHost_insertObject(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> None:
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		ConfigDataBackend.auditHardwareOnHost_insertObject(self, auditHardwareOnHost)

		logger.debug(
			"Inserting auditHardwareOnHost: '%s'", auditHardwareOnHost.getIdent()
		)
		self.__doAuditHardwareObj(auditHardwareOnHost, mode="insert")

	def auditHardwareOnHost_updateObject(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> None:
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		ConfigDataBackend.auditHardwareOnHost_updateObject(self, auditHardwareOnHost)

		logger.debug(
			"Updating auditHardwareOnHost: '%s'", auditHardwareOnHost.getIdent()
		)
		self.__doAuditHardwareObj(auditHardwareOnHost, mode="update")

	def auditHardwareOnHost_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditHardwareOnHost]:
		attributes = attributes or []
		ConfigDataBackend.auditHardwareOnHost_getObjects(self, attributes=[], **filter)

		logger.debug("Getting auditHardwareOnHosts ...")
		filenames = {}
		for ident in self._getIdents("AuditHardwareOnHost", **filter):
			if ident["hostId"] not in filenames:
				filenames[ident["hostId"]] = self._getConfigFile(
					"AuditHardwareOnHost", ident, "hw"
				)

		result = []
		for hostId, filename in filenames.items():
			if not os.path.exists(filename):
				continue

			iniFile = IniFile(filename=filename)
			ini = iniFile.parse()
			for section in ini.sections():
				objHash = {"hostId": hostId}
				for option in ini.options(section):
					if option.lower() == "hardwareclass":
						objHash["hardwareClass"] = self.__unescape(
							ini.get(section, option)
						)
					else:
						objHash[str(option)] = self.__unescape(ini.get(section, option))

				auditHardwareOnHost = AuditHardwareOnHost.fromHash(objHash)
				if self._objectHashMatches(auditHardwareOnHost.toHash(), **filter):
					result.append(auditHardwareOnHost)

		return result

	def auditHardwareOnHost_deleteObjects(
		self, auditHardwareOnHosts: list[AuditHardwareOnHost]
	) -> None:
		ConfigDataBackend.auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts)

		logger.debug("Deleting auditHardwareOnHosts ...")

		for auditHardwareOnHost in forceObjectClassList(
			auditHardwareOnHosts, AuditHardwareOnHost
		):
			self.__doAuditHardwareObj(auditHardwareOnHost, mode="delete")

	def __doAuditHardwareObj(
		self, auditHardwareObj: Union[AuditHardware, AuditHardwareOnHost], mode: str
	) -> None:
		if mode not in ("insert", "update", "delete"):
			raise ValueError("Unknown mode: %s" % mode)

		objType = auditHardwareObj.getType()
		if objType not in ("AuditHardware", "AuditHardwareOnHost"):
			raise TypeError("Unknown type: %s" % objType)

		filename = self._getConfigFile(
			objType, auditHardwareObj.getIdent(returnType="dict"), "hw"
		)
		self._touch(filename)
		iniFile = IniFile(filename=filename)
		ini = iniFile.parse()

		objHash = {}
		for attribute, value in auditHardwareObj.toHash().items():
			if attribute.lower() in ("hostid", "type"):
				continue

			if value is None:
				objHash[attribute.lower()] = ""
			else:
				objHash[attribute.lower()] = forceUnicode(value)

		sectionFound = None
		for section in ini.sections():
			matches = True
			for attribute, value in objHash.items():
				if attribute in ("firstseen", "lastseen", "state"):
					continue

				if ini.has_option(section, attribute):
					if self.__unescape(ini.get(section, attribute)) != value:
						matches = False
						break
				else:
					matches = False
					break
			if matches:
				logger.debug(
					"Found matching section '%s' in audit file '%s' for object %s",
					section,
					filename,
					objHash,
				)
				sectionFound = section
				break

		if mode == "delete":
			if sectionFound:
				ini.remove_section(sectionFound)
		elif mode == "update":
			if sectionFound:
				for attribute, value in objHash.items():
					if attribute in ("firstseen", "lastseen", "state") and not value:
						continue
					ini.set(sectionFound, attribute, self.__escape(value))
			else:
				mode = "insert"

		if mode == "insert":
			if sectionFound:
				ini.remove_section(sectionFound)
			else:
				nums = [
					int(section[section.rfind("_") + 1 :]) for section in ini.sections()
				]

				num = 0
				while num in nums:
					num += 1
				sectionFound = "hardware_%d" % num
			ini.add_section(sectionFound)
			for attribute, value in objHash.items():
				ini.set(sectionFound, attribute, self.__escape(value))

		iniFile.generate(ini)
