# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Configuration data holding backend.
"""

import codecs
import collections
import copy as pycopy
import glob
import json
import os
import re
import shutil
import time
from functools import lru_cache

from opsicommon.license import (
	OPSI_MODULE_IDS,
	OPSI_OBSOLETE_MODULE_IDS,
	get_default_opsi_license_pool,
)
from opsicommon.logging import get_logger, secret_filter

from OPSI.Config import OPSI_ADMIN_GROUP
from OPSI.Exceptions import (
	BackendBadValueError,
	BackendMissingDataError,
	BackendModuleDisabledError,
	BackendReferentialIntegrityError,
)
from OPSI.Object import (
	AuditHardware,
	AuditHardwareOnHost,
	AuditSoftware,
	AuditSoftwareOnClient,
	AuditSoftwareToLicensePool,
	Config,
	ConfigState,
	Group,
	Host,
	LicenseContract,
	LicenseOnClient,
	LicensePool,
	ObjectToGroup,
	OpsiClient,
	OpsiDepotserver,
	Product,
	ProductDependency,
	ProductOnClient,
	ProductOnDepot,
	ProductProperty,
	ProductPropertyState,
	SoftwareLicense,
	SoftwareLicenseToLicensePool,
	getPossibleClassAttributes,
)
from OPSI.Types import (
	forceBool,
	forceFilename,
	forceHostId,
	forceInt,
	forceLanguageCode,
	forceObjectClass,
	forceObjectClassList,
	forceObjectId,
	forceUnicode,
	forceUnicodeList,
	forceUnicodeLower,
)
from OPSI.Util import blowfishDecrypt, blowfishEncrypt, getfqdn
from OPSI.Util.File import ConfigFile
from OPSI.Util.Log import truncateLogData

from .Backend import Backend

__all__ = ("ConfigDataBackend",)

OPSI_PASSWD_FILE = "/etc/opsi/passwd"
LOG_DIR = "/var/log/opsi"
LOG_TYPES = {  # key = logtype, value = requires objectId for read
	"bootimage": True,
	"clientconnect": True,
	"instlog": True,
	"opsiconfd": False,
	"userlogin": True,
	"winpe": True,
}
_PASSWD_LINE_REGEX = re.compile(r"^\s*([^:]+)\s*:\s*(\S+)\s*$")
OPSI_HARDWARE_CLASSES = []

DEFAULT_MAX_LOG_SIZE = 5000000
DEFAULT_KEEP_ROTATED_LOGS = 0
LOG_SIZE_HARD_LIMIT = 10000000


logger = get_logger("opsi.general")


class ConfigDataBackend(Backend):
	"""
	Base class for backends holding data.

	These backends should keep data integrity intact but not alter the data.
	"""

	option_defaults = {
		**Backend.option_defaults,
		**{"additionalReferentialIntegrityChecks": True},
	}

	def __init__(self, **kwargs):
		"""
		Constructor.

		Keyword arguments can differ between implementation.
		:param audithardwareconfigfile: Location of the hardware audit \
configuration file.
		:param audihardwareconfiglocalesdir: Location of the directory \
containing the localisation of the hardware audit.
		:param opsipasswdfile: Location of opsis own passwd file.
		:param depotid: Id of the current depot.
		:param maxlogsize: Maximum size of a logfile.
		:param keeprotatedlogs: Maximum size of a logfile.
		"""
		Backend.__init__(self, **kwargs)
		self._auditHardwareConfigFile = "/etc/opsi/hwaudit/opsihwaudit.conf"
		self._auditHardwareConfigLocalesDir = "/etc/opsi/hwaudit/locales"
		self._opsiPasswdFile = OPSI_PASSWD_FILE
		self._max_log_size = DEFAULT_MAX_LOG_SIZE
		self._keep_rotated_logs = DEFAULT_KEEP_ROTATED_LOGS
		self._depotId = None

		for option, value in kwargs.items():
			option = option.lower().replace("_", "")
			if option == "audithardwareconfigfile":
				self._auditHardwareConfigFile = forceFilename(value)
			elif option == "audithardwareconfiglocalesdir":
				self._auditHardwareConfigLocalesDir = forceFilename(value)
			elif option == "opsipasswdfile":
				self._opsiPasswdFile = forceFilename(value)
			elif option in ("depotid", "serverid"):
				self._depotId = value
			elif option == "maxlogsize":
				self._max_log_size = forceInt(value)
			elif option == "keeprotatedlogs":
				self._keep_rotated_logs = forceInt(value)

		if not self._depotId:
			self._depotId = getfqdn()
		self._depotId = forceHostId(self._depotId)

	def _testFilterAndAttributes(self, Class, attributes, **filter):
		if not attributes:
			if not filter:
				return

			attributes = []

		possibleAttributes = getPossibleClassAttributes(Class)

		for attribute in forceUnicodeList(attributes):
			if attribute not in possibleAttributes:
				raise BackendBadValueError(
					f"Class {Class} has no attribute '{attribute}'"
				)

		for attribute in filter:
			if attribute not in possibleAttributes:
				raise BackendBadValueError(
					f"Class {Class} has no attribute '{attribute}'"
				)

	def backend_createBase(self):
		"""
		Setting up the base for the backend to store its data.

		This can be something like creating a directory structure to setting up a database.
		"""

	def backend_deleteBase(self):
		"""
		Deleting the base of the backend.

		This is the place to undo all the things that were created by \
*backend_createBase*.
		"""

	def backend_getSystemConfiguration(self):
		"""
		Returns current system configuration.

		This holds information about server-side settings that may be
		relevant for clients.

		Under the key `log` information about log settings will be
		returned in form of a dict.
		In it under `size_limit` you will find the amount of bytes
		currently allowed as maximum log size.
		Under `types` you will find a list with currently supported log
		types.

		:rtype: dict
		"""
		return {
			"log": {
				"size_limit": self._max_log_size,
				"keep_rotated": self._keep_rotated_logs,
				"types": list(LOG_TYPES),
			}
		}

	def getOpsiCACert(self) -> str:
		return None

	def _check_module(self, module: str):
		if module not in self.backend_getLicensingInfo()["available_modules"]:
			raise BackendModuleDisabledError(f"Module {module!r} not available")

	def _get_client_info(self):
		logger.info("%s fetching client info", self)
		_all = len(self.host_getObjects(attributes=["id"], type="OpsiClient"))
		macos = len(
			self.productOnClient_getObjects(
				attributes=["clientId"],
				installationStatus="installed",
				productId="opsi-mac-client-agent",
			)
		)
		linux = len(
			self.productOnClient_getObjects(
				attributes=["clientId"],
				installationStatus="installed",
				productId="opsi-linux-client-agent",
			)
		)
		return {"macos": macos, "linux": linux, "windows": _all - macos - linux}

	@lru_cache(maxsize=10)
	def _get_licensing_info(
		self,
		licenses: bool = False,
		legacy_modules: bool = False,
		dates: bool = False,
		ttl_hash: int = 0,
	):
		"""
		Returns opsi licensing information.
		"""
		del ttl_hash  # ttl_hash is only used to invalidate the cache after a ttl
		pool = get_default_opsi_license_pool(
			license_file_path=self._opsi_license_path,
			modules_file_path=self._opsiModulesFile,
			client_info=self._get_client_info,
		)

		for config in ("client_limit_warning_percent", "client_limit_warning_absolute"):
			try:
				setattr(
					pool,
					config,
					int(
						self._context.config_getObjects(id=f"licensing.{config}")[
							0
						].getDefaultValues()[0]
					),
				)
			except Exception as err:
				logger.debug(err)

		try:
			disable_warning_for_modules = [
				m
				for m in self._context.config_getObjects(
					id="licensing.disable_warning_for_modules"
				)[0].getDefaultValues()
				if m in OPSI_MODULE_IDS
			]
		except Exception as err:
			logger.debug(err)
			disable_warning_for_modules = []

		try:
			client_limit_warning_days = int(
				self._context.config_getObjects(
					id="licensing.client_limit_warning_days"
				)[0].getDefaultValues()[0]
			)
		except Exception as err:
			logger.debug(err)
			client_limit_warning_days = 30

		modules = pool.get_modules()
		info = {
			"client_numbers": pool.client_numbers,
			"known_modules": OPSI_MODULE_IDS,
			"obsolete_modules": OPSI_OBSOLETE_MODULE_IDS,
			"available_modules": [
				module_id for module_id, info in modules.items() if info["available"]
			],
			"modules": modules,
			"licenses_checksum": pool.get_licenses_checksum(),
			"config": {
				"client_limit_warning_percent": pool.client_limit_warning_percent,
				"client_limit_warning_absolute": pool.client_limit_warning_absolute,
				"client_limit_warning_days": client_limit_warning_days,
				"disable_warning_for_modules": disable_warning_for_modules,
			},
		}
		if licenses:
			licenses = pool.get_licenses()
			info["licenses"] = [
				lic.to_dict(serializable=True, with_state=True) for lic in licenses
			]
		if legacy_modules:
			info["legacy_modules"] = pool.get_legacy_modules()
		if dates:
			info["dates"] = {}
			for at_date in pool.get_relevant_dates():
				info["dates"][str(at_date)] = {
					"modules": pool.get_modules(at_date=at_date)
				}
		return info

	def backend_getLicensingInfo(
		self,
		licenses: bool = False,
		legacy_modules: bool = False,
		dates: bool = False,
		allow_cache: bool = True,
	):
		pool = get_default_opsi_license_pool(
			license_file_path=self._opsi_license_path,
			modules_file_path=self._opsiModulesFile,
			client_info=self._get_client_info,
		)
		if not allow_cache or pool.modified():
			self._get_licensing_info.cache_clear()
		if pool.modified():
			pool.load()

		def get_ttl_hash(seconds=3600):
			"""Return the same value withing `seconds` time period"""
			return round(time.time() / seconds)

		return self._get_licensing_info(
			licenses=licenses,
			legacy_modules=legacy_modules,
			dates=dates,
			ttl_hash=get_ttl_hash(),
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Logs                                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def log_write(self, logType, data, objectId=None, append=False):
		"""
		Write log data into the corresponding log file.

		:param logType: Type of log. \
Currently supported: *bootimage*, *clientconnect*, *instlog*, *opsiconfd* or *userlogin*.
		:param data: Log content
		:type data: Unicode
		:param objectId: Specialising of ``logType``
		:param append: Changes the behaviour to either append or \
overwrite the log.
		:type append: bool
		"""
		logType = forceUnicode(logType)
		if logType not in LOG_TYPES:
			raise BackendBadValueError(f"Unknown log type '{logType}'")

		if not objectId:
			raise BackendBadValueError(f"Writing {logType} log requires an objectId")
		objectId = forceObjectId(objectId)

		append = forceBool(append)

		data = data.encode("utf-8", "replace")
		if len(data) > LOG_SIZE_HARD_LIMIT:
			data = data[-1 * LOG_SIZE_HARD_LIMIT :]
			idx = data.find(b"\n")
			if idx > 0:
				data = data[idx + 1 :]

		log_file = os.path.join(LOG_DIR, logType, f"{objectId}.log")

		if not os.path.exists(os.path.dirname(log_file)):
			os.mkdir(os.path.dirname(log_file), 0o2770)

		try:
			if not append or (
				append
				and os.path.exists(log_file)
				and os.path.getsize(log_file) + len(data) > self._max_log_size
			):
				logger.info("Rotating file '%s'", log_file)
				if self._keep_rotated_logs <= 0:
					os.remove(log_file)
				else:
					for num in range(self._keep_rotated_logs, 0, -1):
						src_file_path = log_file
						if num > 1:
							src_file_path = f"{log_file}.{num-1}"
						if not os.path.exists(src_file_path):
							continue
						dst_file_path = f"{log_file}.{num}"
						os.rename(src_file_path, dst_file_path)
						try:
							shutil.chown(dst_file_path, -1, OPSI_ADMIN_GROUP)
							os.chmod(dst_file_path, 0o644)
						except Exception as err:
							logger.error(
								"Failed to set file permissions on '%s': %s",
								dst_file_path,
								err,
							)

			for filename in glob.glob(f"{log_file}.*"):
				try:
					if int(filename.split(".")[-1]) > self._keep_rotated_logs:
						os.remove(filename)
				except ValueError:
					os.remove(filename)
		except Exception as err:
			logger.error("Failed to rotate log files: %s", err)

		with open(log_file, mode="ab" if append else "wb") as file:
			file.write(data)

		try:
			shutil.chown(log_file, group=OPSI_ADMIN_GROUP)
			os.chmod(log_file, 0o640)
		except Exception as err:
			logger.error("Failed to set file permissions on '%s': %s", log_file, err)

	def log_read(self, logType, objectId=None, maxSize=0):
		"""
		Return the content of a log.

		:param logType: Type of log. \
Currently supported: *bootimage*, *clientconnect*, *instlog*, *opsiconfd* or *userlogin*.
		:type data: Unicode
		:param objectId: Specialising of ``logType``
		:param maxSize: Limit for the size of returned characters in bytes. \
Setting this to `0` disables limiting.
		"""
		logType = forceUnicode(logType)
		maxSize = int(maxSize)

		if logType not in LOG_TYPES:
			raise BackendBadValueError(f"Unknown log type '{logType}'")

		if objectId:
			objectId = forceObjectId(objectId)
			log_file = os.path.join(LOG_DIR, logType, f"{objectId}.log")
		else:
			if LOG_TYPES[logType]:
				raise BackendBadValueError(f"Log type '{logType}' requires objectId")
			log_file = os.path.join(LOG_DIR, logType, "opsiconfd.log")

		try:
			with codecs.open(log_file, "r", "utf-8", "replace") as log:
				data = log.read()
		except IOError as ioerr:
			if ioerr.errno == 2:  # This is "No such file or directory"
				return ""
			raise

		if len(data) > maxSize > 0:
			return truncateLogData(data, maxSize)

		return data

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Users                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def user_getCredentials(self, username="pcpatch", hostId=None):
		"""
		Get the credentials of an opsi user.
		The information is stored in ``/etc/opsi/passwd``.

		:param hostId: Optional value that should be the calling host.
		:return: Dict with the keys *password* and *rsaPrivateKey*. \
If this is called with an valid hostId the data will be encrypted with \
the opsi host key.
		:rtype: dict
		"""
		username = forceUnicodeLower(username)
		if hostId:
			hostId = forceHostId(hostId)

		result = {"password": "", "rsaPrivateKey": ""}

		cf = ConfigFile(filename=self._opsiPasswdFile)
		for line in cf.parse():
			match = _PASSWD_LINE_REGEX.search(line)
			if match is None:
				continue

			if match.group(1) == username:
				result["password"] = match.group(2)
				break

		if not result["password"]:
			raise BackendMissingDataError(
				f"Username '{username}' not found in '{self._opsiPasswdFile}'"
			)

		depot = self.host_getObjects(id=self._depotId)
		if not depot:
			raise BackendMissingDataError(
				f"Depot '{self._depotId}'' not found in backend"
			)
		depot = depot[0]
		if not depot.opsiHostKey:
			raise BackendMissingDataError(
				f"Host key for depot '{self._depotId}' not found"
			)

		result["password"] = blowfishDecrypt(depot.opsiHostKey, result["password"])

		if username == "pcpatch":
			try:
				import pwd

				idRsa = os.path.join(pwd.getpwnam(username)[5], ".ssh", "id_rsa")
				with open(idRsa, encoding="utf-8") as file:
					result["rsaPrivateKey"] = file.read()
			except Exception as err:
				logger.debug(err)

		if hostId:
			host = self._context.host_getObjects(id=hostId)
			try:
				host = host[0]
			except IndexError as err:
				raise BackendMissingDataError(
					f"Host '{hostId}' not found in backend"
				) from err

			result["password"] = blowfishEncrypt(host.opsiHostKey, result["password"])
			if result["rsaPrivateKey"]:
				result["rsaPrivateKey"] = blowfishEncrypt(
					host.opsiHostKey, result["rsaPrivateKey"]
				)

		return result

	def user_setCredentials(self, username, password):
		"""
		Set the password of an opsi user.
		The information is stored in ``/etc/opsi/passwd``.
		The password will be encrypted with the opsi host key of the \
depot where the method is.
		"""
		username = forceUnicodeLower(username)
		password = forceUnicode(password)
		secret_filter.add_secrets(password)

		if '"' in password:
			raise ValueError("Character '\"' not allowed in password")

		try:
			depot = self._context.host_getObjects(id=self._depotId)
			depot = depot[0]
		except IndexError as err:
			raise BackendMissingDataError(
				f"Depot {self._depotId} not found in backend {self._context}"
			) from err

		encodedPassword = blowfishEncrypt(depot.opsiHostKey, password)

		cf = ConfigFile(filename=self._opsiPasswdFile)
		lines = []
		try:
			for line in cf.readlines():
				match = _PASSWD_LINE_REGEX.search(line)
				if not match or match.group(1) != username:
					lines.append(line.rstrip())
		except FileNotFoundError:
			pass

		lines.append(f"{username}:{encodedPassword}")
		cf.open("w")
		cf.writelines(lines)
		cf.close()

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_insertObject(self, host):
		host = forceObjectClass(host, Host)
		host.setDefaults()

	def host_updateObject(self, host):
		host = forceObjectClass(host, Host)

	def host_getHashes(self, attributes=[], **filter):
		return [obj.toHash() for obj in self.host_getObjects(attributes, **filter)]

	def host_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(Host, attributes, **filter)
		return []

	def host_deleteObjects(self, hosts):
		for host in forceObjectClassList(hosts, Host):
			# Remove from groups
			self._context.objectToGroup_deleteObjects(
				self._context.objectToGroup_getObjects(
					groupType="HostGroup", objectId=host.id
				)
			)

			if isinstance(host, OpsiClient):
				# Remove product states
				self._context.productOnClient_deleteObjects(
					self._context.productOnClient_getObjects(clientId=host.id)
				)
			elif isinstance(host, OpsiDepotserver):
				# This is also true for OpsiConfigservers
				# Remove products
				self._context.productOnDepot_deleteObjects(
					self._context.productOnDepot_getObjects(depotId=host.id)
				)
			# Remove product property states
			self._context.productPropertyState_deleteObjects(
				self._context.productPropertyState_getObjects(objectId=host.id)
			)
			# Remove config states
			self._context.configState_deleteObjects(
				self._context.configState_getObjects(objectId=host.id)
			)

			if isinstance(host, OpsiClient):
				# Remove audit softwares
				self._context.auditSoftwareOnClient_deleteObjects(
					self._context.auditSoftwareOnClient_getObjects(clientId=host.id)
				)

			# Remove audit hardwares
			self._context.auditHardwareOnHost_deleteObjects(
				self._context.auditHardwareOnHost_getObjects(hostId=host.id)
			)

			if isinstance(host, OpsiClient):
				# Free software licenses
				self._context.licenseOnClient_deleteObjects(
					self._context.licenseOnClient_getObjects(clientId=host.id)
				)

				softwareLicenses = self._context.softwareLicense_getObjects(
					boundToHost=host.id
				)
				softwareLicenses = softwareLicenses or []
				for softwareLicense in softwareLicenses:
					softwareLicense.boundToHost = None
					self._context.softwareLicense_insertObject(softwareLicense)

	def host_getTLSCertificate(self, hostId: str) -> str:
		return None

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config):
		config = forceObjectClass(config, Config)
		config.setDefaults()

	def config_updateObject(self, config):
		config = forceObjectClass(config, Config)

	def config_getHashes(self, attributes=[], **filter):
		return [obj.toHash() for obj in self.config_getObjects(attributes, **filter)]

	def config_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(Config, attributes, **filter)
		return []

	def config_deleteObjects(self, configs):
		ids = [config.id for config in forceObjectClassList(configs, Config)]

		if ids:
			self._context.configState_deleteObjects(
				self._context.configState_getObjects(configId=ids, objectId=[])
			)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)
		configState.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			configIds = [
				config.id
				for config in self._context.config_getObjects(attributes=["id"])
			]

			if configState.configId not in configIds:
				raise BackendReferentialIntegrityError(
					f"Config with id '{configState.configId}' not found"
				)

	def configState_updateObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)

	def configState_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.configState_getObjects(attributes, **filter)
		]

	def configState_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ConfigState, attributes, **filter)
		return []

	def configState_deleteObjects(self, configStates):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product):
		product = forceObjectClass(product, Product)
		product.setDefaults()

	def product_updateObject(self, product):
		product = forceObjectClass(product, Product)

	def product_getHashes(self, attributes=[], **filter):
		return [obj.toHash() for obj in self.product_getObjects(attributes, **filter)]

	def product_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(Product, attributes, **filter)
		return []

	def product_deleteObjects(self, products):
		productByIdAndVersion = collections.defaultdict(
			lambda: collections.defaultdict(list)
		)
		for product in forceObjectClassList(products, Product):
			productByIdAndVersion[product.id][product.productVersion].append(
				product.packageVersion
			)

			self._context.productProperty_deleteObjects(
				self._context.productProperty_getObjects(
					productId=product.id,
					productVersion=product.productVersion,
					packageVersion=product.packageVersion,
				)
			)
			self._context.productDependency_deleteObjects(
				self._context.productDependency_getObjects(
					productId=product.id,
					productVersion=product.productVersion,
					packageVersion=product.packageVersion,
				)
			)
			self._context.productOnDepot_deleteObjects(
				self._context.productOnDepot_getObjects(
					productId=product.id,
					productVersion=product.productVersion,
					packageVersion=product.packageVersion,
				)
			)

		for productId, versions in productByIdAndVersion.items():
			allProductVersWillBeDeleted = True
			for product in self._context.product_getObjects(
				attributes=["id", "productVersion", "packageVersion"], id=productId
			):
				if product.packageVersion not in versions.get(
					product.productVersion, []
				):
					allProductVersWillBeDeleted = False
					break

			if not allProductVersWillBeDeleted:
				continue

			# Remove from groups, when allProductVerionsWillBeDelted
			self._context.objectToGroup_deleteObjects(
				self._context.objectToGroup_getObjects(
					groupType="ProductGroup", objectId=productId
				)
			)
			self._context.productOnClient_deleteObjects(
				self._context.productOnClient_getObjects(productId=productId)
			)
			self._context.productPropertyState_deleteObjects(
				self._context.productPropertyState_getObjects(productId=productId)
			)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)
		productProperty.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.product_getObjects(
				attributes=["id", "productVersion", "packageVersion"],
				id=productProperty.productId,
				productVersion=productProperty.productVersion,
				packageVersion=productProperty.packageVersion,
			):
				raise BackendReferentialIntegrityError(
					f"Product with id '{productProperty.productId}', "
					f"productVersion '{productProperty.productVersion}', "
					f"packageVersion '{productProperty.packageVersion}' not found"
				)

	def productProperty_updateObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)

	def productProperty_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.productProperty_getObjects(attributes, **filter)
		]

	def productProperty_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductProperty, attributes, **filter)
		return []

	def productProperty_deleteObjects(self, productProperties):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                       -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)
		productDependency.setDefaults()
		if (
			not productDependency.getRequiredAction()
			and not productDependency.getRequiredInstallationStatus()
		):
			raise BackendBadValueError(
				"Either a required action or a required installation status must be given"
			)
		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.product_getObjects(
				attributes=["id", "productVersion", "packageVersion"],
				id=productDependency.productId,
				productVersion=productDependency.productVersion,
				packageVersion=productDependency.packageVersion,
			):
				raise BackendReferentialIntegrityError(
					f"Product with id '{productDependency.productId}', "
					f"productVersion '{productDependency.productVersion}', "
					f"packageVersion '{productDependency.packageVersion}' not found"
				)

	def productDependency_updateObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)

	def productDependency_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.productDependency_getObjects(attributes, **filter)
		]

	def productDependency_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductDependency, attributes, **filter)
		return []

	def productDependency_deleteObjects(self, productDependencies):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		productOnDepot.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.product_getObjects(
				attributes=["id", "productVersion", "packageVersion"],
				id=productOnDepot.productId,
				productVersion=productOnDepot.productVersion,
				packageVersion=productOnDepot.packageVersion,
			):
				raise BackendReferentialIntegrityError(
					f"Product with id '{productOnDepot.productId}', "
					f"productVersion '{productOnDepot.productVersion}', "
					f"packageVersion '{productOnDepot.packageVersion}' not found"
				)

	def productOnDepot_updateObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.product_getObjects(
				attributes=["id", "productVersion", "packageVersion"],
				id=productOnDepot.productId,
				productVersion=productOnDepot.productVersion,
				packageVersion=productOnDepot.packageVersion,
			):
				raise BackendReferentialIntegrityError(
					f"Product with id '{productOnDepot.productId}', "
					f"productVersion '{productOnDepot.productVersion}', "
					f"packageVersion '{productOnDepot.packageVersion}' not found"
				)

	def productOnDepot_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.productOnDepot_getObjects(attributes, **filter)
		]

	def productOnDepot_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductOnDepot, attributes, **filter)
		return []

	def productOnDepot_deleteObjects(self, productOnDepots):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		productOnClient.setDefaults()

		if (productOnClient.installationStatus == "installed") and (
			not productOnClient.productVersion or not productOnClient.packageVersion
		):
			raise BackendReferentialIntegrityError(
				f"Cannot set installationStatus for product '{productOnClient.productId}'"
				f", client '{productOnClient.clientId}' to 'installed' without productVersion and packageVersion"
			)

		if productOnClient.installationStatus != "installed":
			productOnClient.productVersion = None
			productOnClient.packageVersion = None

	def productOnClient_updateObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)

	def productOnClient_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.productOnClient_getObjects(attributes, **filter)
		]

	def productOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductOnClient, attributes, **filter)
		return []

	def productOnClient_deleteObjects(self, productOnClients):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(self, productPropertyState):
		productPropertyState = forceObjectClass(
			productPropertyState, ProductPropertyState
		)
		productPropertyState.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.productProperty_getObjects(
				attributes=["productId", "propertyId"],
				productId=productPropertyState.productId,
				propertyId=productPropertyState.propertyId,
			):
				raise BackendReferentialIntegrityError(
					f"ProductProperty with id '{productPropertyState.propertyId}' "
					f"for product '{productPropertyState.productId}' not found"
				)

	def productPropertyState_updateObject(self, productPropertyState):
		productPropertyState = forceObjectClass(
			productPropertyState, ProductPropertyState
		)

	def productPropertyState_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.productPropertyState_getObjects(attributes, **filter)
		]

	def productPropertyState_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductPropertyState, attributes, **filter)
		return []

	def productPropertyState_deleteObjects(self, productPropertyStates):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group):
		group = forceObjectClass(group, Group)
		group.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			if group.parentGroupId and not self._context.group_getObjects(
				attributes=["id"], id=group.parentGroupId
			):
				raise BackendReferentialIntegrityError(
					f"Parent group '{group.parentGroupId}' of group '{group.id}' not found"
				)

	def group_updateObject(self, group):
		group = forceObjectClass(group, Group)

	def group_getHashes(self, attributes=[], **filter):
		return [obj.toHash() for obj in self.group_getObjects(attributes, **filter)]

	def group_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(Group, attributes, **filter)
		return []

	def group_deleteObjects(self, groups):
		for group in forceObjectClassList(groups, Group):
			matchingMappings = self._context.objectToGroup_getObjects(
				groupType=group.getType(), groupId=group.id
			)
			self._context.objectToGroup_deleteObjects(matchingMappings)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		objectToGroup.setDefaults()

	def objectToGroup_updateObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)

	def objectToGroup_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.objectToGroup_getObjects(attributes, **filter)
		]

	def objectToGroup_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ObjectToGroup, attributes, **filter)
		return []

	def objectToGroup_deleteObjects(self, objectToGroups):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_insertObject(self, licenseContract):
		licenseContract = forceObjectClass(licenseContract, LicenseContract)
		licenseContract.setDefaults()

	def licenseContract_updateObject(self, licenseContract):
		licenseContract = forceObjectClass(licenseContract, LicenseContract)

	def licenseContract_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.licenseContract_getObjects(attributes, **filter)
		]

	def licenseContract_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicenseContract, attributes, **filter)
		return []

	def licenseContract_deleteObjects(self, licenseContracts):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_insertObject(self, softwareLicense):
		softwareLicense = forceObjectClass(softwareLicense, SoftwareLicense)
		softwareLicense.setDefaults()
		if not softwareLicense.licenseContractId:
			raise BackendBadValueError("License contract missing")

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.licenseContract_getObjects(
				attributes=["id"], id=softwareLicense.licenseContractId
			):
				raise BackendReferentialIntegrityError(
					f"License contract with id '{softwareLicense.licenseContractId}' not found"
				)

	def softwareLicense_updateObject(self, softwareLicense):
		softwareLicense = forceObjectClass(softwareLicense, SoftwareLicense)

	def softwareLicense_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.softwareLicense_getObjects(attributes, **filter)
		]

	def softwareLicense_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(SoftwareLicense, attributes, **filter)
		return []

	def softwareLicense_deleteObjects(self, softwareLicenses):
		softwareLicenseIds = [
			softwareLicense.id
			for softwareLicense in forceObjectClassList(
				softwareLicenses, SoftwareLicense
			)
		]

		self._context.softwareLicenseToLicensePool_deleteObjects(
			self._context.softwareLicenseToLicensePool_getObjects(
				softwareLicenseId=softwareLicenseIds
			)
		)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePools                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_insertObject(self, licensePool):
		licensePool = forceObjectClass(licensePool, LicensePool)
		licensePool.setDefaults()

	def licensePool_updateObject(self, licensePool):
		licensePool = forceObjectClass(licensePool, LicensePool)

	def licensePool_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.licensePool_getObjects(attributes, **filter)
		]

	def licensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicensePool, attributes, **filter)
		return []

	def licensePool_deleteObjects(self, licensePools):
		licensePoolIds = [
			licensePool.id
			for licensePool in forceObjectClassList(licensePools, LicensePool)
		]

		if licensePoolIds:
			softwareLicenseToLicensePools = (
				self._context.softwareLicenseToLicensePool_getObjects(
					licensePoolId=licensePoolIds
				)
			)
			if softwareLicenseToLicensePools:
				raise BackendReferentialIntegrityError(
					f"Refusing to delete license pool(s) {licensePoolIds}, "
					f"one ore more licenses/keys refer to pool: {softwareLicenseToLicensePools}"
				)

			self._context.auditSoftwareToLicensePool_deleteObjects(
				self._context.auditSoftwareToLicensePool_getObjects(
					name=[],
					version=[],
					subVersion=[],
					language=[],
					architecture=[],
					licensePoolId=licensePoolIds,
				)
			)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_insertObject(self, softwareLicenseToLicensePool):
		softwareLicenseToLicensePool = forceObjectClass(
			softwareLicenseToLicensePool, SoftwareLicenseToLicensePool
		)
		softwareLicenseToLicensePool.setDefaults()

		if self._options["additionalReferentialIntegrityChecks"]:
			if not self._context.softwareLicense_getObjects(
				attributes=["id"], id=softwareLicenseToLicensePool.softwareLicenseId
			):
				raise BackendReferentialIntegrityError(
					f"Software license with id '{softwareLicenseToLicensePool.softwareLicenseId}' not found"
				)
			if not self._context.licensePool_getObjects(
				attributes=["id"], id=softwareLicenseToLicensePool.licensePoolId
			):
				raise BackendReferentialIntegrityError(
					f"License with id '{softwareLicenseToLicensePool.licensePoolId}' not found"
				)

	def softwareLicenseToLicensePool_updateObject(self, softwareLicenseToLicensePool):
		softwareLicenseToLicensePool = forceObjectClass(
			softwareLicenseToLicensePool, SoftwareLicenseToLicensePool
		)

	def softwareLicenseToLicensePool_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.softwareLicenseToLicensePool_getObjects(
				attributes, **filter
			)
		]

	def softwareLicenseToLicensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(
			SoftwareLicenseToLicensePool, attributes, **filter
		)
		return []

	def softwareLicenseToLicensePool_deleteObjects(self, softwareLicenseToLicensePools):
		softwareLicenseIds = [
			softwareLicenseToLicensePool.softwareLicenseId
			for softwareLicenseToLicensePool in forceObjectClassList(
				softwareLicenseToLicensePools, SoftwareLicenseToLicensePool
			)
		]

		if softwareLicenseIds:
			licenseOnClients = self._context.licenseOnClient_getObjects(
				softwareLicenseId=softwareLicenseIds
			)
			if licenseOnClients:
				raise BackendReferentialIntegrityError(
					f"Refusing to delete softwareLicenseToLicensePool(s), one ore more licenses in use: {licenseOnClients}"
				)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_insertObject(self, licenseOnClient):
		licenseOnClient = forceObjectClass(licenseOnClient, LicenseOnClient)
		licenseOnClient.setDefaults()

	def licenseOnClient_updateObject(self, licenseOnClient):
		licenseOnClient = forceObjectClass(licenseOnClient, LicenseOnClient)

	def licenseOnClient_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.licenseOnClient_getObjects(attributes, **filter)
		]

	def licenseOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicenseOnClient, attributes, **filter)
		return []

	def licenseOnClient_deleteObjects(self, licenseOnClients):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_insertObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		auditSoftware.setDefaults()

	def auditSoftware_updateObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)

	def auditSoftware_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.auditSoftware_getObjects(attributes, **filter)
		]

	def auditSoftware_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftware, attributes, **filter)
		return []

	def auditSoftware_deleteObjects(self, auditSoftwares):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_insertObject(self, auditSoftwareToLicensePool):
		auditSoftwareToLicensePool = forceObjectClass(
			auditSoftwareToLicensePool, AuditSoftwareToLicensePool
		)
		auditSoftwareToLicensePool.setDefaults()

	def auditSoftwareToLicensePool_updateObject(self, auditSoftwareToLicensePool):
		auditSoftwareToLicensePool = forceObjectClass(
			auditSoftwareToLicensePool, AuditSoftwareToLicensePool
		)

	def auditSoftwareToLicensePool_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.auditSoftwareToLicensePool_getObjects(attributes, **filter)
		]

	def auditSoftwareToLicensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftwareToLicensePool, attributes, **filter)
		return []

	def auditSoftwareToLicensePool_deleteObjects(self, auditSoftwareToLicensePools):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(
			auditSoftwareOnClient, AuditSoftwareOnClient
		)
		auditSoftwareOnClient.setDefaults()

	def auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(
			auditSoftwareOnClient, AuditSoftwareOnClient
		)

	def auditSoftwareOnClient_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.auditSoftwareOnClient_getObjects(attributes, **filter)
		]

	def auditSoftwareOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftwareOnClient, attributes, **filter)
		return []

	def auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _checkHardwareClass(self, auditHardwareOrauditHardwareOnHost):
		hardwareClass = auditHardwareOrauditHardwareOnHost.getHardwareClass()
		if not AuditHardware.hardware_attributes.get(hardwareClass):
			raise ValueError(
				f"Attributes for hardware class '{hardwareClass}' not found, please check hwaudit.conf"
			)

	def auditHardware_insertObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		auditHardware.setDefaults()
		self._checkHardwareClass(auditHardware)

	def auditHardware_updateObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		self._checkHardwareClass(auditHardware)

	def auditHardware_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash() for obj in self.auditHardware_getObjects(attributes, **filter)
		]

	def auditHardware_getObjects(self, attributes=[], **filter):
		return []

	def auditHardware_deleteObjects(self, auditHardwares):
		pass

	def auditHardware_getConfig(self, language=None):
		if self._auditHardwareConfigFile.endswith(".json"):
			try:
				with codecs.open(self._auditHardwareConfigFile, "r", "utf8") as file:
					return json.loads(file.read())
			except Exception as err:
				logger.warning(
					"Failed to read audit hardware configuration from file '%s': %s",
					self._auditHardwareConfigFile,
					err,
				)
				return []

		if not language:
			language = "en_US"
		language = forceLanguageCode(language).replace("-", "_")

		localeFile = os.path.join(self._auditHardwareConfigLocalesDir, language)
		if not os.path.exists(localeFile):
			logger.debug(
				"No translation file found for language %s, falling back to en_US",
				language,
			)
			language = "en_US"
			localeFile = os.path.join(self._auditHardwareConfigLocalesDir, language)

		locale = {}
		try:
			lf = ConfigFile(localeFile)
			for line in lf.parse():
				try:
					identifier, translation = line.split("=", 1)
					locale[identifier.strip()] = translation.strip()
				except ValueError as verr:
					logger.trace("Failed to read translation: %s", verr)
			del lf
		except Exception as err:
			logger.debug(
				"Failed to read translation file for language %s: %s", language, err
			)

		def __inheritFromSuperClasses(classes, _class, scname=None):
			if not scname:
				for _scname in _class["Class"].get("Super", []):
					__inheritFromSuperClasses(classes, _class, _scname)
			else:
				for cl in classes:
					if cl["Class"].get("Opsi") == scname:
						clcopy = pycopy.deepcopy(cl)
						__inheritFromSuperClasses(classes, clcopy)
						newValues = []
						for newValue in clcopy["Values"]:
							foundAt = -1
							for i, currentValue in enumerate(_class["Values"]):
								if currentValue["Opsi"] == newValue["Opsi"]:
									if not currentValue.get("UI"):
										_class["Values"][i]["UI"] = newValue.get(
											"UI", ""
										)
									foundAt = i
									break
							if foundAt > -1:
								newValue = _class["Values"][foundAt]
								del _class["Values"][foundAt]
							newValues.append(newValue)
						newValues.extend(_class["Values"])
						_class["Values"] = newValues
						break
				else:
					logger.error(
						"Super class '%s' of class '%s' not found",
						scname,
						_class["Class"].get("Opsi"),
					)

		classes = []
		try:
			with open(self._auditHardwareConfigFile, encoding="utf-8") as hwcFile:
				exec(hwcFile.read())

			for i, currentClassConfig in enumerate(OPSI_HARDWARE_CLASSES):
				opsiClass = currentClassConfig["Class"]["Opsi"]
				if currentClassConfig["Class"]["Type"] == "STRUCTURAL":
					if locale.get(opsiClass):
						OPSI_HARDWARE_CLASSES[i]["Class"]["UI"] = locale[opsiClass]
					else:
						logger.debug("No translation for class '%s' found", opsiClass)
						OPSI_HARDWARE_CLASSES[i]["Class"]["UI"] = opsiClass

				for j, currentValue in enumerate(currentClassConfig["Values"]):
					opsiProperty = currentValue["Opsi"]
					try:
						OPSI_HARDWARE_CLASSES[i]["Values"][j]["UI"] = locale[
							opsiClass + "." + opsiProperty
						]
					except KeyError:
						pass

			for owc in OPSI_HARDWARE_CLASSES:
				try:
					if owc["Class"].get("Type") == "STRUCTURAL":
						logger.debug(
							"Found STRUCTURAL hardware class '%s'",
							owc["Class"].get("Opsi"),
						)
						ccopy = pycopy.deepcopy(owc)
						if "Super" in ccopy["Class"]:
							__inheritFromSuperClasses(OPSI_HARDWARE_CLASSES, ccopy)
							del ccopy["Class"]["Super"]
						del ccopy["Class"]["Type"]

						# Fill up empty display names
						for j, currentValue in enumerate(ccopy.get("Values", [])):
							if not currentValue.get("UI"):
								logger.debug(
									"No translation found for hardware audit configuration property '%s.%s' in %s",
									ccopy["Class"]["Opsi"],
									currentValue["Opsi"],
									localeFile,
								)
								ccopy["Values"][j]["UI"] = currentValue["Opsi"]

						classes.append(ccopy)
				except Exception as err:
					logger.error(
						"Error in config file '%s': %s",
						self._auditHardwareConfigFile,
						err,
					)
		except Exception as err:
			logger.warning(
				"Failed to read audit hardware configuration from file '%s': %s",
				self._auditHardwareConfigFile,
				err,
			)

		return classes

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardwareOnHost_insertObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		auditHardwareOnHost.setDefaults()
		self._checkHardwareClass(auditHardwareOnHost)
		self._context.auditHardware_insertObject(
			AuditHardware.fromHash(auditHardwareOnHost.toHash())
		)

	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		self._checkHardwareClass(auditHardwareOnHost)

	def auditHardwareOnHost_getHashes(self, attributes=[], **filter):
		return [
			obj.toHash()
			for obj in self.auditHardwareOnHost_getObjects(attributes, **filter)
		]

	def auditHardwareOnHost_getObjects(self, attributes=[], **filter):
		return []

	def auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   direct access                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def getData(self, query):
		return query

	def getRawData(self, query):
		return query
