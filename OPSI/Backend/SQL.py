# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Basic SQL backend.

This backend is a general SQL implementation undependend from concrete
databases and their implementation.
"""

import json
import re
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, Tuple

from opsicommon.logging import get_logger

from OPSI.Backend.Base import Backend, BackendModificationListener, ConfigDataBackend
from OPSI.Exceptions import (
	BackendBadValueError,
	BackendConfigurationError,
	BackendMissingDataError,
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
	Entity,
	Group,
	Host,
	HostGroup,
	LicenseContract,
	LicenseOnClient,
	LicensePool,
	ObjectToGroup,
	Product,
	ProductDependency,
	ProductGroup,
	ProductOnClient,
	ProductOnDepot,
	ProductProperty,
	ProductPropertyState,
	Relationship,
	SoftwareLicense,
	SoftwareLicenseToLicensePool,
	getPossibleClassAttributes,
	mandatoryConstructorArgs,
)
from OPSI.Types import (
	forceBool,
	forceDict,
	forceList,
	forceObjectClassList,
	forceOpsiTimestamp,
	forceUnicodeList,
	forceUnicodeLower,
)
from OPSI.Util import timestamp

__all__ = (
	"timeQuery",
	"onlyAllowSelect",
	"SQL",
	"SQLBackend",
	"SQLBackendObjectModificationTracker",
)

DATABASE_SCHEMA_VERSION = 8

logger = get_logger("opsi.general")


@contextmanager
def timeQuery(query: str) -> Generator[None, None, None]:
	startingTime = datetime.now()
	logger.debug("start query %s", query)
	try:
		yield
	finally:
		logger.debug(
			"ended query (duration: %s) %s", query, datetime.now() - startingTime
		)


def onlyAllowSelect(query: str) -> None:
	if not forceUnicodeLower(query).strip().startswith(("select", "show", "pragma")):
		raise ValueError("Only queries to SELECT/SHOW/PRAGMA data are allowed.")


def createSchemaVersionTable(database: Any, session: Any) -> None:
	logger.debug("Creating 'OPSI_SCHEMA' table.")
	table = f"""CREATE TABLE IF NOT EXISTS `OPSI_SCHEMA` (
		`version` integer NOT NULL,
		`updateStarted` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		`updateEnded` TIMESTAMP NULL DEFAULT NULL,
		PRIMARY KEY (`version`)
	) {database.getTableCreationOptions('OPSI_SCHEMA')};
	"""
	logger.debug(table)
	database.execute(session, table)


class SQL:
	"""Class handling basic SQL functionality."""

	AUTOINCREMENT = "AUTO_INCREMENT"
	ALTER_TABLE_CHANGE_SUPPORTED = True
	ESCAPED_BACKSLASH = "\\\\"
	ESCAPED_APOSTROPHE = "\\'"
	ESCAPED_UNDERSCORE = "\\_"
	ESCAPED_PERCENT = "\\%"
	ESCAPED_ASTERISK = "\\*"
	ESCAPED_COLON = "\\:"

	def __init__(self, **kwargs) -> None:
		self.Session = lambda: None
		self.session_factory = None
		self.engine = None
		self.log_queries = False
		# Parse arguments
		for option, value in kwargs.items():
			option = option.lower()
			if option == "log_queries":
				self.log_queries = forceBool(value)

	@staticmethod
	def on_engine_connect(conn, branch) -> None:
		pass

	def init_connection(self) -> None:
		pass

	def disconnect(self) -> None:
		if self.engine:
			self.engine.dispose()

	@contextmanager
	def session(self, commit: bool = True) -> None:
		session = self.Session()
		try:
			yield session
			if commit:
				session.commit()
		except Exception:
			session.rollback()
			raise
		finally:
			self.Session.remove()

	def connect(self, cursorType: Any = None) -> None:
		logger.warning("Method 'connect' is deprecated")

	def close(self, conn: Any, cursor: Any) -> None:
		logger.warning("Method 'close' is deprecated")

	def execute(self, session: Any, query: str) -> None:
		session.execute(query)

	def getSet(self, session: Any, query: str) -> list[list[str, Any]]:
		"""
		Return a list of rows, every row is a dict of key / values pairs
		"""
		logger.trace("getSet: %s", query)
		onlyAllowSelect(query)
		result = session.execute(query).fetchall()
		if not result:
			return []
		return [dict(row) for row in result if row is not None]

	def getRows(self, session: Any, query: str) -> list[list[Any]]:
		"""
		Return a list of rows, every row is a list of values
		"""
		logger.trace("getRows: %s", query)
		onlyAllowSelect(query)
		result = session.execute(query).fetchall()
		if not result:
			return []
		return [list(row) for row in result if row is not None]

	def getRow(self, session: Any, query: str) -> list[Any]:
		"""
		Return one row as value list
		"""
		logger.trace("getRow: %s", query)
		onlyAllowSelect(query)
		result = session.execute(query).fetchone()
		if not result:
			return []
		return list(result)

	def insert(self, session: Any, table: str, valueHash: Any) -> int:
		if not valueHash:
			raise BackendBadValueError("No values given")

		col_names = [f"`{col_name}`" for col_name in list(valueHash)]
		bind_names = [f":{col_name}" for col_name in list(valueHash)]
		query = f"INSERT INTO `{table}` ({','.join(col_names)}) VALUES ({','.join(bind_names)})"
		logger.trace("insert: %s - %s", query, valueHash)
		result = session.execute(query, valueHash)
		return result.lastrowid

	def update(
		self,
		session: Any,
		table: str,
		where: str,
		valueHash: Any,
		updateWhereNone: bool = False,
	) -> int:
		if not valueHash:
			raise BackendBadValueError("No values given")

		updates = []
		for key, value in valueHash.items():
			if value is None and not updateWhereNone:
				continue
			updates.append(f"`{key}` = :{key}")

		query = f"UPDATE `{table}` SET {','.join(updates)} WHERE {where}"

		logger.trace("update: %s - %s", query, valueHash)
		result = session.execute(query, valueHash)
		return result.rowcount

	def delete(self, session: Any, table: str, where: str) -> int:
		query = f"DELETE FROM `{table}` WHERE {where}"
		logger.trace("delete: %s", query)
		result = session.execute(query)
		return result.rowcount

	def getTables(self, session: Any) -> Dict:
		return {}

	def getTableCreationOptions(self, table: str) -> str:
		return ""

	def escapeBackslash(self, string: str) -> str:
		return string.replace("\\", self.ESCAPED_BACKSLASH)

	def escapeApostrophe(self, string: str) -> str:
		return string.replace("'", self.ESCAPED_APOSTROPHE)

	def escapeUnderscore(self, string: str) -> str:
		return string.replace("_", self.ESCAPED_UNDERSCORE)

	def escapePercent(self, string: str) -> str:
		return string.replace("%", self.ESCAPED_PERCENT)

	def escapeAsterisk(self, string: str) -> str:
		return string.replace("*", self.ESCAPED_ASTERISK)

	def escapeColon(self, string: str) -> str:
		return string.replace(":", self.ESCAPED_COLON)


class SQLBackendObjectModificationTracker(BackendModificationListener):
	def __init__(self, **kwargs) -> None:
		BackendModificationListener.__init__(self)
		self._sql = None
		self._lastModificationOnly = False
		for option, value in kwargs.items():
			option = option.lower()
			if option == "lastmodificationonly":
				self._lastModificationOnly = forceBool(value)

	def _createTables(self) -> None:
		with self._sql.session() as session:
			tables = self._sql.getTables(session)
			if "OBJECT_MODIFICATION_TRACKER" not in tables:
				logger.debug("Creating table OBJECT_MODIFICATION_TRACKER")
				table = f"""CREATE TABLE `OBJECT_MODIFICATION_TRACKER` (
						`id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`command` varchar(6) NOT NULL,
						`objectClass` varchar(128) NOT NULL,
						`ident` varchar(1024) NOT NULL,
						`date` TIMESTAMP,
						PRIMARY KEY (`id`)
					) {self._sql.getTableCreationOptions('OBJECT_MODIFICATION_TRACKER')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `objectClass` on `OBJECT_MODIFICATION_TRACKER` (`objectClass`);",
				)
				self._sql.execute(
					session,
					"CREATE INDEX `ident` on `OBJECT_MODIFICATION_TRACKER` (`ident`);",
				)
				self._sql.execute(
					session,
					"CREATE INDEX `date` on `OBJECT_MODIFICATION_TRACKER` (`date`);",
				)

	def _trackModification(self, command: str, obj: Any) -> None:
		command = forceUnicodeLower(command)
		if command not in ("insert", "update", "delete"):
			raise ValueError(f"Unhandled command '{command}'")

		data = {
			"command": command,
			"objectClass": obj.__class__.__name__,
			"ident": obj.getIdent(),
			"date": timestamp(),
		}

		with self._sql.session() as session:
			if self._lastModificationOnly:
				objectClass = data["objectClass"]
				ident = self._sql.escapeApostrophe(
					self._sql.escapeBackslash(self._sql.escapeColon(data["ident"]))
				)
				self._sql.delete(
					session,
					"OBJECT_MODIFICATION_TRACKER",
					f"`objectClass` = '{objectClass}' AND `ident` = '{ident}'",
				)
			start = time.time()
			self._sql.insert(session, "OBJECT_MODIFICATION_TRACKER", data)
			logger.debug(
				"Took %0.2f seconds to track modification of objectClass %s, ident %s",
				time.time() - start,
				data["objectClass"],
				data["ident"],
			)

	def getModifications(self, sinceDate: str = None) -> Any:
		where = ""
		if sinceDate:
			where = f" WHERE `date` >= '{forceOpsiTimestamp(sinceDate)}'"
		with self._sql.session() as session:
			return self._sql.getSet(
				session, f"SELECT * FROM `OBJECT_MODIFICATION_TRACKER`{where}"
			)

	def clearModifications(
		self, objectClass: str = None, sinceDate: str = None
	) -> None:
		where = "1 = 1"
		if objectClass:
			where = f" AND `objectClass` = '{objectClass}'"
		if sinceDate:
			where += f" AND `date` >= '{forceOpsiTimestamp(sinceDate)}'"
		with self._sql.session() as session:
			self._sql.delete(session, "OBJECT_MODIFICATION_TRACKER", where=where)

	def objectInserted(self, backend: Backend, obj: Any) -> None:
		self._trackModification("insert", obj)

	def objectUpdated(self, backend: Backend, obj: Any) -> None:
		self._trackModification("update", obj)

	def objectsDeleted(self, backend: Backend, objs: list[Any]) -> None:
		for obj in forceList(objs):
			self._trackModification("delete", obj)


class SQLBackend(ConfigDataBackend):
	"""Backend holding information in MySQL form."""

	_OPERATOR_IN_CONDITION_PATTERN = re.compile(r"^\s*([>=<]+)\s*(\d\.?\d*)")

	def __init__(self, **kwargs) -> None:
		self._name = "sql"

		ConfigDataBackend.__init__(self, **kwargs)

		self._sql = None
		self._auditHardwareConfig = {}
		self.unique_hardware_addresses = True
		self._setAuditHardwareConfig(self.auditHardware_getConfig())
		# Parse arguments
		for option, value in kwargs.items():
			if option == "unique_hardware_addresses":
				self.unique_hardware_addresses = forceBool(value)

	def _setAuditHardwareConfig(self, config: dict[str, dict[str, Any]]) -> None:
		self._auditHardwareConfig = {}
		for conf in config:
			hwClass = conf["Class"]["Opsi"]
			self._auditHardwareConfig[hwClass] = {}
			for value in conf["Values"]:
				self._auditHardwareConfig[hwClass][value["Opsi"]] = {
					"Type": value["Type"],
					"Scope": value["Scope"],
				}

	def _filterToSql(self, filter: dict[str, Any] = None, table: str = None) -> str:
		"""
		Creates a SQL condition out of the given filter.
		"""
		filter = filter or {}

		def buildCondition() -> Generator[str, None, None]:
			for key, values in filter.items():
				if values is None:
					continue
				values = forceList(values)
				if not values:
					continue
				if len(values) > 10 and isinstance(values[0], str):
					if table:
						key = f"`{table}`.`{key}`"
					else:
						key = f"`{key}`"

					def escaped_string(value):
						return f"'{self._sql.escapeApostrophe(self._sql.escapeBackslash(self._sql.escapeColon(value)))}'"

					yield f"{key} in ({','.join([escaped_string(val) for val in values])})"
				else:
					yield " or ".join(processValues(key, values, table))

		def processValues(
			key: str, values: list[Any], table: str = None
		) -> Generator[str, None, None]:
			if table:
				key = f"`{table}`.`{key}`"
			else:
				key = f"`{key}`"
			for value in values:
				if isinstance(value, bool):
					if value:
						yield f"{key} = 1"
					else:
						yield f"{key} = 0"
				elif isinstance(value, (float, int)):
					yield f"{key} = {value}"
				elif value is None:
					yield f"{key} is NULL"
				else:
					value = value.replace(self._sql.ESCAPED_ASTERISK, "\uffff")
					value = self._sql.escapeApostrophe(
						self._sql.escapeBackslash(self._sql.escapeColon(value))
					)
					match = self._OPERATOR_IN_CONDITION_PATTERN.search(value)
					if match:
						operator = match.group(1)
						value = match.group(2)
						value = value.replace("\uffff", self._sql.ESCAPED_ASTERISK)
						yield f"{key} {operator} {value}"
					else:
						if "*" in value:
							operator = "LIKE"
							value = self._sql.escapeUnderscore(
								self._sql.escapePercent(value)
							).replace("*", "%")
						else:
							operator = "="

						value = value.replace("\uffff", self._sql.ESCAPED_ASTERISK)
						yield f"{key} {operator} '{value}'"

		def addParenthesis(conditions: list[str]) -> str:
			for condition in conditions:
				yield f"({condition})"

		return " and ".join(addParenthesis(buildCondition()))

	def _createQuery(
		self, table: str, attributes: list[str] = None, filter: dict[str, Any] = None
	) -> str:
		select = ",".join(f"`{attribute}`" for attribute in attributes or []) or "*"

		condition = self._filterToSql(filter or {})
		if condition:
			query = f"select {select} from `{table}` where {condition}"
		else:
			query = f"select {select} from `{table}`"
		logger.debug("Created query: %s", query)
		return query

	def _adjustAttributes(
		self, objectClass: str, attributes: list[str], filter: dict[str, Any]
	):
		possibleAttributes = getPossibleClassAttributes(objectClass)

		newAttributes = []
		if attributes:
			newAttributes = forceUnicodeList(attributes)
			for attr in newAttributes:
				if attr not in possibleAttributes:
					raise ValueError(f"Invalid attribute '{attr}'")

		newFilter = {}
		if filter:
			newFilter = forceDict(filter)
			for attr in filter:
				if attr not in possibleAttributes:
					raise ValueError(f"Invalid attribute '{attr}' in filter")

		objectId = self._objectAttributeToDatabaseAttribute(objectClass, "id")

		if "id" in newFilter:
			newFilter[objectId] = newFilter["id"]
			del newFilter["id"]

		if "id" in newAttributes:
			newAttributes.remove("id")
			newAttributes.append(objectId)

		if "type" in newFilter:
			for oc in forceList(newFilter["type"]):
				if objectClass.__name__ == oc:
					newFilter["type"] = forceList(newFilter["type"]).append(
						list(objectClass.subClasses.values())
					)
					break

		if newAttributes:
			if issubclass(objectClass, Entity) and "type" not in newAttributes:
				newAttributes.append("type")
			objectClasses = [objectClass]
			objectClasses.extend(list(objectClass.subClasses.values()))
			for oc in objectClasses:
				for arg in mandatoryConstructorArgs(oc):
					if arg == "id":
						arg = objectId

					if arg not in newAttributes:
						newAttributes.append(arg)

		return (newAttributes, newFilter)

	def _adjustResult(self, objectClass: str, result: dict[str, Any]) -> dict[str, Any]:
		idAttribute = self._objectAttributeToDatabaseAttribute(objectClass, "id")

		try:
			result["id"] = result[idAttribute]
			del result[idAttribute]
		except KeyError:
			pass

		return result

	def _objectToDatabaseHash(self, object: Any) -> dict[str, Any]:
		_hash = object.toHash()
		if object.getType() == "ProductOnClient":
			try:
				del _hash["actionSequence"]
			except KeyError:
				pass  # not there - can be

		if issubclass(object.__class__, Product):
			try:
				# Truncating a possibly too long changelog entry
				# This takes into account that unicode characters may be
				# composed of multiple bytes by encoding, stripping and
				# decoding them.
				changelog = _hash["changelog"]
				changelog = changelog.encode("utf-8")
				changelog = changelog[:65534]
				# Ignoring errors because truncation could have
				# currupted a multi-byte utf-8 char
				_hash["changelog"] = changelog.decode("utf-8", "ignore")
			except (KeyError, TypeError):
				pass  # Either not present in _hash or set to None
			except UnicodeError:
				# Encoding problem. We truncate anyway and remove some
				# buffer characters for possible unicode characters.
				# Since encoding is attempted after we have read the
				# has we can assume that the key is present.
				_hash["changelog"] = _hash["changelog"][:65000]

		if issubclass(object.__class__, Relationship):
			try:
				del _hash["type"]
			except KeyError:
				pass  # not there - can be

		for objectAttribute in list(_hash):
			dbAttribute = self._objectAttributeToDatabaseAttribute(
				object.__class__, objectAttribute
			)
			if objectAttribute != dbAttribute:
				_hash[dbAttribute] = _hash[objectAttribute]
				del _hash[objectAttribute]

		return _hash

	def _objectAttributeToDatabaseAttribute(
		self, objectClass: str, attribute: str
	) -> str:
		if attribute == "id":
			# A class is considered a subclass of itself
			if issubclass(objectClass, Product):
				return "productId"
			if issubclass(objectClass, Host):
				return "hostId"
			if issubclass(objectClass, Group):
				return "groupId"
			if issubclass(objectClass, Config):
				return "configId"
			if issubclass(objectClass, LicenseContract):
				return "licenseContractId"
			if issubclass(objectClass, SoftwareLicense):
				return "softwareLicenseId"
			if issubclass(objectClass, LicensePool):
				return "licensePoolId"
		return attribute

	def _uniqueCondition(self, object: Any) -> str:
		"""
		Creates an unique condition that can be used in the WHERE part
		of an SQL query to identify an object.
		To achieve this the constructor of the object is inspected.
		Objects must have an attribute named like the parameter.

		:param object: The object to create an condition for.
		"""

		def createCondition() -> Generator[str, None, None]:
			for argument in mandatoryConstructorArgs(object.__class__):
				value = getattr(object, argument)
				if value is None:
					continue

				arg = self._objectAttributeToDatabaseAttribute(
					object.__class__, argument
				)
				if isinstance(value, bool):
					if value:
						yield f"`{arg}` = 1"
					else:
						yield f"`{arg}` = 0"
				elif isinstance(value, (float, int)):
					yield f"`{arg}` = {value}"
				else:
					yield f"`{arg}` = '{self._sql.escapeApostrophe(self._sql.escapeBackslash(self._sql.escapeColon(value)))}'"

			if isinstance(object, (HostGroup, ProductGroup)):
				yield f"`type` = '{object.getType()}'"

		return " and ".join(createCondition())

	def backend_exit(self) -> None:
		logger.debug("%s backend_exit", self)
		if self._sql and self._sql.engine:
			logger.debug("%s dispose engine", self)
			self._sql.engine.dispose()

	def backend_deleteBase(self) -> None:
		ConfigDataBackend.backend_deleteBase(self)

		# Drop database
		with self._sql.session() as session:
			error_count = 0
			success = False
			while not success:
				success = True
				for table_name in self._sql.getTables(session).keys():
					drop_command = f"DROP TABLE `{table_name}`;"
					logger.debug(drop_command)
					try:
						self._sql.execute(session, drop_command)
					except Exception as err:
						logger.debug("Failed to drop table '%s': %s", table_name, err)
						success = False
						error_count += 1
						if error_count > 99:
							raise

	def backend_createBase(self) -> None:
		ConfigDataBackend.backend_createBase(self)

		with self._sql.session() as session:
			tables = self._sql.getTables(session)

			logger.notice("Creating opsi base")

			existingTables = set(tables.keys())
			# Host table
			if "HOST" not in existingTables:
				self._createTableHost()

			if "CONFIG" not in existingTables:
				logger.debug("Creating table CONFIG")
				table = f"""CREATE TABLE `CONFIG` (
						`configId` varchar(200) NOT NULL,
						`type` varchar(30) NOT NULL,
						`description` varchar(256),
						`multiValue` bool NOT NULL,
						`editable` bool NOT NULL,
						PRIMARY KEY (`configId`)
					) {self._sql.getTableCreationOptions('CONFIG')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session, "CREATE INDEX `index_config_type` on `CONFIG` (`type`);"
				)

			if "CONFIG_VALUE" not in existingTables:
				logger.debug("Creating table CONFIG_VALUE")
				table = f"""CREATE TABLE `CONFIG_VALUE` (
						`config_value_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`configId` varchar(200) NOT NULL,
						`value` TEXT,
						`isDefault` bool,
						PRIMARY KEY (`config_value_id`),
						FOREIGN KEY (`configId`) REFERENCES `CONFIG` (`configId`)
					) {self._sql.getTableCreationOptions('CONFIG_VALUE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			if "CONFIG_STATE" not in existingTables:
				logger.debug("Creating table CONFIG_STATE")
				table = f"""CREATE TABLE `CONFIG_STATE` (
						`config_state_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`configId` varchar(200) NOT NULL,
						`objectId` varchar(255) NOT NULL,
						`values` text,
						PRIMARY KEY (`config_state_id`)
					) {self._sql.getTableCreationOptions('CONFIG_STATE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_config_state_configId` on `CONFIG_STATE` (`configId`);",
				)
				self._sql.execute(
					session,
					"CREATE INDEX `index_config_state_objectId` on `CONFIG_STATE` (`objectId`);",
				)

			if "PRODUCT" not in existingTables:
				logger.debug("Creating table PRODUCT")
				table = f"""CREATE TABLE `PRODUCT` (
						`productId` varchar(255) NOT NULL,
						`productVersion` varchar(32) NOT NULL,
						`packageVersion` varchar(16) NOT NULL,
						`type` varchar(32) NOT NULL,
						`name` varchar(128) NOT NULL,
						`licenseRequired` varchar(50),
						`setupScript` varchar(50),
						`uninstallScript` varchar(50),
						`updateScript` varchar(50),
						`alwaysScript` varchar(50),
						`onceScript` varchar(50),
						`customScript` varchar(50),
						`userLoginScript` varchar(50),
						`priority` integer,
						`description` TEXT,
						`advice` TEXT,
						`pxeConfigTemplate` varchar(50),
						`changelog` TEXT,
						PRIMARY KEY (`productId`, `productVersion`, `packageVersion`)
					) {self._sql.getTableCreationOptions('PRODUCT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session, "CREATE INDEX `index_product_type` on `PRODUCT` (`type`);"
				)
				self._sql.execute(
					session,
					"CREATE INDEX `index_productId` on `PRODUCT` (`productId`);",
				)

			# FOREIGN KEY ( `productId` ) REFERENCES `PRODUCT` ( `productId` ),
			if "WINDOWS_SOFTWARE_ID_TO_PRODUCT" not in existingTables:
				logger.debug("Creating table WINDOWS_SOFTWARE_ID_TO_PRODUCT")
				table = f"""CREATE TABLE `WINDOWS_SOFTWARE_ID_TO_PRODUCT` (
						`windowsSoftwareId` VARCHAR(100) NOT NULL,
						`productId` varchar(255) NOT NULL,
						PRIMARY KEY (`windowsSoftwareId`, `productId`)
					) {self._sql.getTableCreationOptions('WINDOWS_SOFTWARE_ID_TO_PRODUCT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_windows_software_id_to_product_productId` on `WINDOWS_SOFTWARE_ID_TO_PRODUCT` (`productId`);",
				)

			if "PRODUCT_ON_DEPOT" not in existingTables:
				logger.debug("Creating table PRODUCT_ON_DEPOT")
				table = f"""CREATE TABLE `PRODUCT_ON_DEPOT` (
						`productId` varchar(255) NOT NULL,
						`productVersion` varchar(32) NOT NULL,
						`packageVersion` varchar(16) NOT NULL,
						`depotId` varchar(255) NOT NULL,
						`productType` varchar(16) NOT NULL,
						`locked` bool,
						PRIMARY KEY (`productId`, `depotId`),
						FOREIGN KEY (`productId`, `productVersion`, `packageVersion` ) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`),
						FOREIGN KEY (`depotId`) REFERENCES `HOST` (`hostId`)
					) {self._sql.getTableCreationOptions('PRODUCT_ON_DEPOT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_product_on_depot_productType` on `PRODUCT_ON_DEPOT` (`productType`);",
				)

			if "PRODUCT_PROPERTY" not in existingTables:
				logger.debug("Creating table PRODUCT_PROPERTY")
				table = f"""CREATE TABLE `PRODUCT_PROPERTY` (
						`productId` varchar(255) NOT NULL,
						`productVersion` varchar(32) NOT NULL,
						`packageVersion` varchar(16) NOT NULL,
						`propertyId` varchar(200) NOT NULL,
						`type` varchar(30) NOT NULL,
						`description` TEXT,
						`multiValue` bool NOT NULL,
						`editable` bool NOT NULL,
						PRIMARY KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`),
						FOREIGN KEY (`productId`, `productVersion`, `packageVersion`) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`)
					) {self._sql.getTableCreationOptions('PRODUCT_PROPERTY')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_product_property_type` on `PRODUCT_PROPERTY` (`type`);",
				)

			if "PRODUCT_PROPERTY_VALUE" not in existingTables:
				logger.debug("Creating table PRODUCT_PROPERTY_VALUE")
				table = f"""CREATE TABLE `PRODUCT_PROPERTY_VALUE` (
						`product_property_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`productId` varchar(255) NOT NULL,
						`productVersion` varchar(32) NOT NULL,
						`packageVersion` varchar(16) NOT NULL,
						`propertyId` varchar(200) NOT NULL,
						`value` text,
						`isDefault` bool,
						PRIMARY KEY (`product_property_id`),
						FOREIGN KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`)
							REFERENCES `PRODUCT_PROPERTY` (`productId`, `productVersion`, `packageVersion`, `propertyId`)
					) {self._sql.getTableCreationOptions('PRODUCT_PROPERTY_VALUE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_product_property_value` on "
					"`PRODUCT_PROPERTY_VALUE` (`productId`, `propertyId`, `productVersion`, `packageVersion`);",
				)

			if "PRODUCT_DEPENDENCY" not in existingTables:
				logger.debug("Creating table PRODUCT_DEPENDENCY")
				table = f"""CREATE TABLE `PRODUCT_DEPENDENCY` (
						`productId` varchar(255) NOT NULL,
						`productVersion` varchar(32) NOT NULL,
						`packageVersion` varchar(16) NOT NULL,
						`productAction` varchar(16) NOT NULL,
						`requiredProductId` varchar(255) NOT NULL,
						`requiredProductVersion` varchar(32),
						`requiredPackageVersion` varchar(16),
						`requiredAction` varchar(16),
						`requiredInstallationStatus` varchar(16),
						`requirementType` varchar(16),
						PRIMARY KEY (`productId`, `productVersion`, `packageVersion`, `productAction`, `requiredProductId`),
						FOREIGN KEY (`productId`, `productVersion`, `packageVersion`) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`)
					) {self._sql.getTableCreationOptions('PRODUCT_DEPENDENCY')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			# FOREIGN KEY ( `productId` ) REFERENCES PRODUCT( `productId` ),
			if "PRODUCT_ON_CLIENT" not in existingTables:
				logger.debug("Creating table PRODUCT_ON_CLIENT")
				table = f"""CREATE TABLE `PRODUCT_ON_CLIENT` (
						`productId` varchar(255) NOT NULL,
						`clientId` varchar(255) NOT NULL,
						`productType` varchar(16) NOT NULL,
						`targetConfiguration` varchar(16),
						`installationStatus` varchar(16),
						`actionRequest` varchar(16),
						`actionProgress` varchar(255),
						`actionResult` varchar(16),
						`lastAction` varchar(16),
						`productVersion` varchar(32),
						`packageVersion` varchar(16),
						`modificationTime` TIMESTAMP,
						PRIMARY KEY (`productId`, `clientId`),
						FOREIGN KEY (`clientId`) REFERENCES `HOST` (`hostId`)
					) {self._sql.getTableCreationOptions('PRODUCT_ON_CLIENT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			# FOREIGN KEY ( `productId` ) REFERENCES `PRODUCT` ( `productId` ),
			if "PRODUCT_PROPERTY_STATE" not in existingTables:
				logger.debug("Creating table PRODUCT_PROPERTY_STATE")
				table = f"""CREATE TABLE `PRODUCT_PROPERTY_STATE` (
						`product_property_state_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`productId` varchar(255) NOT NULL,
						`propertyId` varchar(200) NOT NULL,
						`objectId` varchar(255) NOT NULL,
						`values` text,
						PRIMARY KEY (`product_property_state_id`)
					) {self._sql.getTableCreationOptions('PRODUCT_PROPERTY_STATE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_product_property_state_objectId` on `PRODUCT_PROPERTY_STATE` (`objectId`);",
				)

			if "GROUP" not in existingTables:
				logger.debug("Creating table GROUP")
				table = f"""CREATE TABLE `GROUP` (
						`type` varchar(30) NOT NULL,
						`groupId` varchar(255) NOT NULL,
						`parentGroupId` varchar(255),
						`description` varchar(100),
						`notes` varchar(500),
						PRIMARY KEY (`type`, `groupId`)
					) {self._sql.getTableCreationOptions('GROUP')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_group_parentGroupId` on `GROUP` (`parentGroupId`);",
				)

			if "OBJECT_TO_GROUP" not in existingTables:
				logger.debug("Creating table OBJECT_TO_GROUP")
				table = f"""CREATE TABLE `OBJECT_TO_GROUP` (
						`object_to_group_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`groupType` varchar(30) NOT NULL,
						`groupId` varchar(255) NOT NULL,
						`objectId` varchar(255) NOT NULL,
						PRIMARY KEY (`object_to_group_id`),
						FOREIGN KEY (`groupType`, `groupId`) REFERENCES `GROUP` (`type`, `groupId`)
					) {self._sql.getTableCreationOptions('OBJECT_TO_GROUP')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_object_to_group_objectId` on `OBJECT_TO_GROUP` (`objectId`);",
				)

			if "LICENSE_CONTRACT" not in existingTables:
				logger.debug("Creating table LICENSE_CONTRACT")
				table = f"""CREATE TABLE `LICENSE_CONTRACT` (
						`licenseContractId` VARCHAR(100) NOT NULL,
						`type` varchar(30) NOT NULL,
						`description` varchar(100),
						`notes` varchar(1000),
						`partner` varchar(100),
						`conclusionDate` TIMESTAMP NULL DEFAULT NULL,
						`notificationDate` TIMESTAMP NULL DEFAULT NULL,
						`expirationDate` TIMESTAMP NULL DEFAULT NULL,
						PRIMARY KEY (`licenseContractId`)
					) {self._sql.getTableCreationOptions('LICENSE_CONTRACT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_license_contract_type` on `LICENSE_CONTRACT` (`type`);",
				)

			if "SOFTWARE_LICENSE" not in existingTables:
				logger.debug("Creating table SOFTWARE_LICENSE")
				table = f"""CREATE TABLE `SOFTWARE_LICENSE` (
						`softwareLicenseId` VARCHAR(100) NOT NULL,
						`licenseContractId` VARCHAR(100) NOT NULL,
						`type` varchar(30) NOT NULL,
						`boundToHost` varchar(255),
						`maxInstallations` integer,
						`expirationDate` TIMESTAMP NULL DEFAULT NULL,
						PRIMARY KEY (`softwareLicenseId`),
						FOREIGN KEY (`licenseContractId`) REFERENCES `LICENSE_CONTRACT` (`licenseContractId`)
					) {self._sql.getTableCreationOptions('SOFTWARE_LICENSE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_software_license_type` on `SOFTWARE_LICENSE` (`type`);",
				)
				self._sql.execute(
					session,
					"CREATE INDEX `index_software_license_boundToHost` on `SOFTWARE_LICENSE` (`boundToHost`);",
				)

			if "LICENSE_POOL" not in existingTables:
				logger.debug("Creating table LICENSE_POOL")
				table = f"""CREATE TABLE `LICENSE_POOL` (
						`licensePoolId` VARCHAR(100) NOT NULL,
						`type` varchar(30) NOT NULL,
						`description` varchar(200),
						PRIMARY KEY (`licensePoolId`)
					) {self._sql.getTableCreationOptions('LICENSE_POOL')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_license_pool_type` on `LICENSE_POOL` (`type`);",
				)

			if "AUDIT_SOFTWARE_TO_LICENSE_POOL" not in existingTables:
				logger.debug("Creating table AUDIT_SOFTWARE_TO_LICENSE_POOL")
				table = f"""CREATE TABLE `AUDIT_SOFTWARE_TO_LICENSE_POOL` (
						`licensePoolId` VARCHAR(100) NOT NULL,
						`name` varchar(100) NOT NULL,
						`version` varchar(100) NOT NULL,
						`subVersion` varchar(100) NOT NULL,
						`language` varchar(10) NOT NULL,
						`architecture` varchar(3) NOT NULL,
						PRIMARY KEY (`name`, `version`, `subVersion`, `language`, `architecture`),
						FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
					) {self._sql.getTableCreationOptions('AUDIT_SOFTWARE_TO_LICENSE_POOL')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			if "PRODUCT_ID_TO_LICENSE_POOL" not in existingTables:
				logger.debug("Creating table PRODUCT_ID_TO_LICENSE_POOL")
				table = f"""CREATE TABLE `PRODUCT_ID_TO_LICENSE_POOL` (
						`licensePoolId` VARCHAR(100) NOT NULL,
						`productId` VARCHAR(255) NOT NULL,
						PRIMARY KEY (`licensePoolId`, `productId`),
						FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
					) {self._sql.getTableCreationOptions('PRODUCT_ID_TO_LICENSE_POOL')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			if "SOFTWARE_LICENSE_TO_LICENSE_POOL" not in existingTables:
				logger.debug("Creating table SOFTWARE_LICENSE_TO_LICENSE_POOL")
				table = f"""CREATE TABLE `SOFTWARE_LICENSE_TO_LICENSE_POOL` (
						`softwareLicenseId` VARCHAR(100) NOT NULL,
						`licensePoolId` VARCHAR(100) NOT NULL,
						`licenseKey` VARCHAR(1024),
						PRIMARY KEY (`softwareLicenseId`, `licensePoolId`),
						FOREIGN KEY (`softwareLicenseId`) REFERENCES `SOFTWARE_LICENSE` (`softwareLicenseId`),
						FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
					) {self._sql.getTableCreationOptions('SOFTWARE_LICENSE_TO_LICENSE_POOL')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)

			if "LICENSE_ON_CLIENT" not in existingTables:
				logger.debug("Creating table LICENSE_ON_CLIENT")
				table = f"""CREATE TABLE `LICENSE_ON_CLIENT` (
						`license_on_client_id` integer NOT NULL {self._sql.AUTOINCREMENT},
						`softwareLicenseId` VARCHAR(100) NOT NULL,
						`licensePoolId` VARCHAR(100) NOT NULL,
						`clientId` varchar(255),
						`licenseKey` VARCHAR(1024),
						`notes` VARCHAR(1024),
						PRIMARY KEY (`license_on_client_id`),
						FOREIGN KEY (`softwareLicenseId`, `licensePoolId`) REFERENCES `SOFTWARE_LICENSE_TO_LICENSE_POOL` (`softwareLicenseId`, `licensePoolId`)
					) {self._sql.getTableCreationOptions('LICENSE_ON_CLIENT')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_license_on_client_clientId` on `LICENSE_ON_CLIENT` (`clientId`);",
				)

			# Software audit tables
			if "SOFTWARE" not in existingTables:
				logger.debug("Creating table SOFTWARE")
				table = f"""CREATE TABLE `SOFTWARE` (
						`name` varchar(100) NOT NULL,
						`version` varchar(100) NOT NULL,
						`subVersion` varchar(100) NOT NULL,
						`language` varchar(10) NOT NULL,
						`architecture` varchar(3) NOT NULL,
						`windowsSoftwareId` varchar(100),
						`windowsDisplayName` varchar(100),
						`windowsDisplayVersion` varchar(100),
						`type` varchar(30) NOT NULL,
						`installSize` BIGINT,
						PRIMARY KEY (`name`, `version`, `subVersion`, `language`, `architecture`)
					) {self._sql.getTableCreationOptions('SOFTWARE')};
					"""
				logger.debug(table)
				self._sql.execute(session, table)
				self._sql.execute(
					session,
					"CREATE INDEX `index_software_windowsSoftwareId` on `SOFTWARE` (`windowsSoftwareId`);",
				)
				self._sql.execute(
					session,
					"CREATE INDEX `index_software_type` on `SOFTWARE` (`type`);",
				)

			if "SOFTWARE_CONFIG" not in existingTables:
				self._createTableSoftwareConfig()

			self._createAuditHardwareTables()

			if "OPSI_SCHEMA" not in existingTables:
				createSchemaVersionTable(self._sql, session)

				query = f"""
					INSERT INTO OPSI_SCHEMA (`version`, `updateEnded`)
					VALUES({DATABASE_SCHEMA_VERSION}, CURRENT_TIMESTAMP);
				"""
				self._sql.execute(session, query)

	def _createTableHost(self) -> None:
		logger.debug("Creating table HOST")
		table = f"""CREATE TABLE `HOST` (
				`hostId` varchar(255) NOT NULL,
				`type` varchar(30),
				`description` varchar(100),
				`notes` varchar(500),
				`hardwareAddress` varchar(17),
				`ipAddress` varchar(15),
				`inventoryNumber` varchar(64),
				`created` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
				`lastSeen` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
				`opsiHostKey` varchar(32),
				`oneTimePassword` varchar(32),
				`maxBandwidth` integer,
				`depotLocalUrl` varchar(128),
				`depotRemoteUrl` varchar(255),
				`depotWebdavUrl` varchar(255),
				`repositoryLocalUrl` varchar(128),
				`repositoryRemoteUrl` varchar(255),
				`networkAddress` varchar(31),
				`isMasterDepot` bool,
				`masterDepotId` varchar(255),
				`workbenchLocalUrl` varchar(128),
				`workbenchRemoteUrl` varchar(255),
				PRIMARY KEY (`hostId`)
			) {self._sql.getTableCreationOptions('HOST')};
			"""

		logger.debug(table)
		with self._sql.session() as session:
			self._sql.execute(session, table)
			self._sql.execute(
				session, "CREATE INDEX `index_host_type` on `HOST` (`type`);"
			)

	def _createTableSoftwareConfig(self) -> None:
		logger.debug("Creating table SOFTWARE_CONFIG")
		table = f"""CREATE TABLE `SOFTWARE_CONFIG` (
				`config_id` integer NOT NULL {self._sql.AUTOINCREMENT},
				`clientId` varchar(255) NOT NULL,
				`name` varchar(100) NOT NULL,
				`version` varchar(100) NOT NULL,
				`subVersion` varchar(100) NOT NULL,
				`language` varchar(10) NOT NULL,
				`architecture` varchar(3) NOT NULL,
				`uninstallString` varchar(200),
				`binaryName` varchar(100),
				`firstseen` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
				`lastseen` TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00',
				`state` TINYINT NOT NULL,
				`usageFrequency` integer NOT NULL DEFAULT -1,
				`lastUsed` TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00',
				`licenseKey` VARCHAR(1024),
				PRIMARY KEY (`config_id`)
			) {self._sql.getTableCreationOptions('SOFTWARE_CONFIG')};
			"""

		logger.debug(table)
		with self._sql.session() as session:
			self._sql.execute(session, table)
			self._sql.execute(
				session,
				"CREATE INDEX `index_software_config_clientId` on `SOFTWARE_CONFIG` (`clientId`);",
			)
			self._sql.execute(
				session,
				"CREATE INDEX `index_software_config_nvsla` on "
				"`SOFTWARE_CONFIG` (`name`, `version`, `subVersion`, `language`, `architecture`);",
			)

	def _createAuditHardwareTables(self) -> None:
		with self._sql.session() as session:
			tables = self._sql.getTables(session)
			existingTables = set(tables.keys())

			for hwClass, values in self._auditHardwareConfig.items():
				logger.debug("Processing hardware class '%s'", hwClass)
				hardwareDeviceTableName = f"HARDWARE_DEVICE_{hwClass}"
				hardwareConfigTableName = f"HARDWARE_CONFIG_{hwClass}"

				hardwareDeviceTableExists = hardwareDeviceTableName in existingTables
				hardwareConfigTableExists = hardwareConfigTableName in existingTables

				if hardwareDeviceTableExists:
					hardwareDeviceTable = f"ALTER TABLE `{hardwareDeviceTableName}`\n"
				else:
					hardwareDeviceTable = (
						f"CREATE TABLE `{hardwareDeviceTableName}` (\n"
						f"`hardware_id` INTEGER NOT NULL {self._sql.AUTOINCREMENT},\n"
					)

				if hardwareConfigTableExists:
					hardwareConfigTable = f"ALTER TABLE `{hardwareConfigTableName}`\n"
				else:
					hardwareConfigTable = (
						f"CREATE TABLE `{hardwareConfigTableName}` (\n"
						f"`config_id` INTEGER NOT NULL {self._sql.AUTOINCREMENT},\n"
						"`hostId` varchar(255) NOT NULL,\n"
						"`hardware_id` INTEGER NOT NULL,\n"
						"`firstseen` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n"
						"`lastseen` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n"
						"`state` TINYINT NOT NULL,\n"
					)

				hardwareDeviceValuesProcessed = 0
				hardwareConfigValuesProcessed = 0
				for value, valueInfo in values.items():
					logger.debug("  Processing value '%s'", value)
					if valueInfo["Scope"] == "g":
						if hardwareDeviceTableExists:
							if value in tables[hardwareDeviceTableName]:
								# Column exists => change
								if not self._sql.ALTER_TABLE_CHANGE_SUPPORTED:
									continue
								hardwareDeviceTable += f"CHANGE `{value}` `{value}` {valueInfo['Type']} NULL,\n"
							else:
								# Column does not exist => add
								hardwareDeviceTable += (
									f'ADD `{value}` {valueInfo["Type"]} NULL,\n'
								)
						else:
							hardwareDeviceTable += (
								f'`{value}` {valueInfo["Type"]} NULL,\n'
							)
						hardwareDeviceValuesProcessed += 1
					elif valueInfo["Scope"] == "i":
						if hardwareConfigTableExists:
							if value in tables[hardwareConfigTableName]:
								# Column exists => change
								if not self._sql.ALTER_TABLE_CHANGE_SUPPORTED:
									continue
								hardwareConfigTable += f'CHANGE `{value}` `{value}` {valueInfo["Type"]} NULL,\n'
							else:
								# Column does not exist => add
								hardwareConfigTable += (
									f'ADD `{value}` {valueInfo["Type"]} NULL,\n'
								)
						else:
							hardwareConfigTable += (
								f'`{value}` {valueInfo["Type"]} NULL,\n'
							)
						hardwareConfigValuesProcessed += 1

				if not hardwareDeviceTableExists:
					hardwareDeviceTable += "PRIMARY KEY (`hardware_id`)\n"
				if not hardwareConfigTableExists:
					hardwareConfigTable += "PRIMARY KEY (`config_id`)\n"

				# Remove leading and trailing whitespace
				hardwareDeviceTable = hardwareDeviceTable.strip()
				hardwareConfigTable = hardwareConfigTable.strip()

				# Remove trailing comma
				if hardwareDeviceTable.endswith(","):
					hardwareDeviceTable = hardwareDeviceTable[:-1]
				if hardwareConfigTable.endswith(","):
					hardwareConfigTable = hardwareConfigTable[:-1]

				# Finish sql query
				if hardwareDeviceTableExists:
					hardwareDeviceTable += " ;\n"
				else:
					hardwareDeviceTable += f"\n) {self._sql.getTableCreationOptions(hardwareDeviceTableName)};\n"

				if hardwareConfigTableExists:
					hardwareConfigTable += " ;\n"
				else:
					hardwareConfigTable += f"\n) {self._sql.getTableCreationOptions(hardwareConfigTableName)};\n"

				# Execute sql query
				if hardwareDeviceValuesProcessed or not hardwareDeviceTableExists:
					logger.debug(hardwareDeviceTable)
					self._sql.execute(session, hardwareDeviceTable)
				if hardwareConfigValuesProcessed or not hardwareConfigTableExists:
					logger.debug(hardwareConfigTable)
					self._sql.execute(session, hardwareConfigTable)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _host_check_duplicates(self, host: Host, session: Any) -> None:
		if (
			self.unique_hardware_addresses
			and host.hardwareAddress
			and not host.hardwareAddress.startswith("00:00:00")
		):
			res = self._sql.getRow(
				session,
				f"""
					SELECT hostId FROM `HOST`
					WHERE hostId != '{host.id}' AND hardwareAddress = '{host.hardwareAddress}'
					LIMIT 1
				""",
			)
			if res:
				raise BackendBadValueError(
					f"Hardware address {host.hardwareAddress!r} is already used by host {res[0]!r}"
				)

	def host_insertObject(self, host: Host) -> None:
		ConfigDataBackend.host_insertObject(self, host)
		data = self._objectToDatabaseHash(host)
		data.pop("systemUUID", None)
		where = self._uniqueCondition(host)
		with self._sql.session() as session:
			self._host_check_duplicates(host, session)
			if self._sql.getRow(session, f"select * from `HOST` where {where}"):
				self._sql.update(session, "HOST", where, data, updateWhereNone=True)
			else:
				self._sql.insert(session, "HOST", data)

	def host_updateObject(self, host: Host) -> None:
		ConfigDataBackend.host_updateObject(self, host)
		data = self._objectToDatabaseHash(host)
		data.pop("systemUUID", None)
		where = self._uniqueCondition(host)
		with self._sql.session() as session:
			self._host_check_duplicates(host, session)
			self._sql.update(session, "HOST", where, data)

	def host_getObjects(self, attributes: list[str] = None, **filter) -> list[Host]:
		ConfigDataBackend.host_getObjects(self, attributes=[], **filter)
		logger.info("Getting hosts, filter: %s", filter)

		hostType = forceList(filter.get("type", []))
		if "OpsiDepotserver" in hostType and "OpsiConfigserver" not in hostType:
			hostType.append("OpsiConfigserver")
			filter["type"] = hostType

		hosts = []
		(attributes, filter) = self._adjustAttributes(Host, attributes or [], filter)
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("HOST", attributes, filter)
			):
				self._adjustResult(Host, res)
				hosts.append(Host.fromHash(res))

		return hosts

	def host_deleteObjects(self, hosts: list[Host]) -> None:
		ConfigDataBackend.host_deleteObjects(self, hosts)

		with self._sql.session() as session:
			for host in forceObjectClassList(hosts, Host):
				logger.info("Deleting host %s", host)
				where = self._uniqueCondition(host)
				self._sql.delete(session, "HOST", where)

				auditHardwareOnDeletedHost = self.auditHardwareOnHost_getObjects(
					objectId=host.id
				)
				if auditHardwareOnDeletedHost:
					self.auditHardwareOnHost_deleteObjects(auditHardwareOnDeletedHost)

				# TODO: Delete audit data!
				# https://redmine.uib.local/issues/869

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config: Config) -> None:
		ConfigDataBackend.config_insertObject(self, config)
		data = self._objectToDatabaseHash(config)
		possibleValues = data["possibleValues"]
		defaultValues = data["defaultValues"]
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data["possibleValues"]
		del data["defaultValues"]

		where = self._uniqueCondition(config)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `CONFIG` where {where}"):
				self._sql.update(session, "CONFIG", where, data, updateWhereNone=True)
			else:
				self._sql.insert(session, "CONFIG", data)

			self._sql.delete(session, "CONFIG_VALUE", where)
			for value in possibleValues:
				self._sql.insert(
					session,
					"CONFIG_VALUE",
					{
						"configId": data["configId"],
						"value": value,
						"isDefault": (value in defaultValues),
					},
				)

	def config_updateObject(self, config: Config) -> None:
		ConfigDataBackend.config_updateObject(self, config)
		data = self._objectToDatabaseHash(config)
		where = self._uniqueCondition(config)
		possibleValues = data["possibleValues"] or []
		defaultValues = data["defaultValues"] or []
		del data["possibleValues"]
		del data["defaultValues"]

		with self._sql.session() as session:
			if self._sql.update(session, "CONFIG", where, data) > 0:
				self._sql.delete(session, "CONFIG_VALUE", where)
				for value in possibleValues:
					self._sql.insert(
						session,
						"CONFIG_VALUE",
						{
							"configId": data["configId"],
							"value": value,
							"isDefault": (value in defaultValues),
						},
					)

	def config_getObjects(self, attributes: list[str] = None, **filter) -> list[Config]:
		ConfigDataBackend.config_getObjects(self, attributes=[], **filter)
		logger.info("Getting configs, filter: %s", filter)
		configs = []
		(attributes, filter) = self._adjustAttributes(Config, attributes or [], filter)

		with self._sql.session() as session:
			try:
				if filter["defaultValues"]:
					configIds = filter.get("configId")
					filter["configId"] = [
						res["configId"]
						for res in self._sql.getSet(
							session,
							self._createQuery(
								"CONFIG_VALUE",
								("configId",),
								{
									"configId": configIds,
									"value": filter["defaultValues"],
									"isDefault": True,
								},
							),
						)
					]

					if not filter["configId"]:
						return []

				del filter["defaultValues"]
			except KeyError:
				pass

			try:
				if filter["possibleValues"]:
					configIds = filter.get("configId")
					filter["configId"] = [
						res["configId"]
						for res in self._sql.getSet(
							session,
							self._createQuery(
								"CONFIG_VALUE",
								("configId",),
								{
									"configId": configIds,
									"value": filter["possibleValues"],
								},
							),
						)
					]

					if not filter["configId"]:
						return []

				del filter["possibleValues"]
			except KeyError:
				pass

			readValues = (
				not attributes
				or "possibleValues" in attributes
				or "defaultValues" in attributes
			)

			attrs = [
				attr
				for attr in attributes
				if attr not in ("defaultValues", "possibleValues")
			]
			for res in self._sql.getSet(
				session, self._createQuery("CONFIG", attrs, filter)
			):
				res["possibleValues"] = []
				res["defaultValues"] = []
				if readValues:
					for res2 in self._sql.getSet(
						session,
						f"select * from CONFIG_VALUE where `configId` = '{res['configId']}'",
					):
						res["possibleValues"].append(res2["value"])
						if res2["isDefault"]:
							res["defaultValues"].append(res2["value"])
				self._adjustResult(Config, res)
				configs.append(Config.fromHash(res))
			return configs

	def config_deleteObjects(self, configs: list[Config]) -> None:
		ConfigDataBackend.config_deleteObjects(self, configs)
		with self._sql.session() as session:
			for config in forceObjectClassList(configs, Config):
				logger.info("Deleting config %s", config)
				where = self._uniqueCondition(config)
				self._sql.delete(session, "CONFIG_VALUE", where)
				self._sql.delete(session, "CONFIG", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState: ConfigState) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.configState_insertObject(self, configState)
		data = self._objectToDatabaseHash(configState)
		data["values"] = json.dumps(data["values"])

		where = self._uniqueCondition(configState)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `CONFIG_STATE` where {where}"):
				self._sql.update(
					session, "CONFIG_STATE", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "CONFIG_STATE", data)

	def configState_updateObject(self, configState: ConfigState) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.configState_updateObject(self, configState)
		data = self._objectToDatabaseHash(configState)
		where = self._uniqueCondition(configState)
		data["values"] = json.dumps(data["values"])
		with self._sql.session() as session:
			self._sql.update(session, "CONFIG_STATE", where, data)

	def configState_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ConfigState]:
		ConfigDataBackend.configState_getObjects(self, attributes=[], **filter)
		logger.info("Getting configStates, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			ConfigState, attributes or [], filter
		)

		configStates = []
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("CONFIG_STATE", attributes, filter)
			):
				try:
					res["values"] = json.loads(res["values"])
				except KeyError:
					pass

				configStates.append(ConfigState.fromHash(res))
		return configStates

	def configState_deleteObjects(self, configStates: list[ConfigState]) -> None:
		ConfigDataBackend.configState_deleteObjects(self, configStates)
		with self._sql.session() as session:
			for configState in forceObjectClassList(configStates, ConfigState):
				logger.info("Deleting configState %s", configState)
				where = self._uniqueCondition(configState)
				self._sql.delete(session, "CONFIG_STATE", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product: Product) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.product_insertObject(self, product)
		data = self._objectToDatabaseHash(product)
		windowsSoftwareIds = data["windowsSoftwareIds"]
		del data["windowsSoftwareIds"]
		del data["productClassIds"]

		where = self._uniqueCondition(product)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `PRODUCT` where {where}"):
				self._sql.update(session, "PRODUCT", where, data, updateWhereNone=True)
			else:
				self._sql.insert(session, "PRODUCT", data)

			self._sql.delete(
				session,
				"WINDOWS_SOFTWARE_ID_TO_PRODUCT",
				f"`productId` = '{data['productId']}'",
			)

			for windowsSoftwareId in windowsSoftwareIds:
				mapping = {
					"windowsSoftwareId": windowsSoftwareId,
					"productId": data["productId"],
				}
				self._sql.insert(session, "WINDOWS_SOFTWARE_ID_TO_PRODUCT", mapping)

	def product_updateObject(self, product: Product) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.product_updateObject(self, product)
		data = self._objectToDatabaseHash(product)
		where = self._uniqueCondition(product)
		windowsSoftwareIds = data["windowsSoftwareIds"] or []
		del data["windowsSoftwareIds"]
		del data["productClassIds"]

		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT", where, data)
			self._sql.delete(
				session,
				"WINDOWS_SOFTWARE_ID_TO_PRODUCT",
				f"`productId` = '{data['productId']}'",
			)

			for windowsSoftwareId in windowsSoftwareIds:
				mapping = {
					"windowsSoftwareId": windowsSoftwareId,
					"productId": data["productId"],
				}
				self._sql.insert(session, "WINDOWS_SOFTWARE_ID_TO_PRODUCT", mapping)

	def product_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[Product]:
		ConfigDataBackend.product_getObjects(self, attributes=[], **filter)
		logger.info("Getting products, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(Product, attributes or [], filter)

		readWindowsSoftwareIDs = not attributes or "windowsSoftwareIds" in attributes
		products = []
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("PRODUCT", attributes, filter)
			):
				res["windowsSoftwareIds"] = []
				res["productClassIds"] = []
				if readWindowsSoftwareIDs:
					for res2 in self._sql.getSet(
						session,
						f"select * from WINDOWS_SOFTWARE_ID_TO_PRODUCT where `productId` = '{res['productId']}'",
					):
						res["windowsSoftwareIds"].append(res2["windowsSoftwareId"])

				if not attributes or "productClassIds" in attributes:
					# TODO: is this missing an query?
					pass

				self._adjustResult(Product, res)
				products.append(Product.fromHash(res))
		return products

	def product_deleteObjects(self, products: list[Product]) -> None:
		ConfigDataBackend.product_deleteObjects(self, products)
		with self._sql.session() as session:
			for product in forceObjectClassList(products, Product):
				logger.info("Deleting product %s", product)
				where = self._uniqueCondition(product)
				self._sql.delete(
					session,
					"WINDOWS_SOFTWARE_ID_TO_PRODUCT",
					f"`productId` = '{product.getId()}'",
				)
				self._sql.delete(session, "PRODUCT", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty: ProductProperty) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productProperty_insertObject(self, productProperty)
		data = self._objectToDatabaseHash(productProperty)
		possibleValues = data["possibleValues"]
		defaultValues = data["defaultValues"]
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data["possibleValues"]
		del data["defaultValues"]

		where = self._uniqueCondition(productProperty)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `PRODUCT_PROPERTY` where {where}"
			):
				self._sql.update(
					session, "PRODUCT_PROPERTY", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "PRODUCT_PROPERTY", data)

			self._sql.delete(session, "PRODUCT_PROPERTY_VALUE", where)
			for value in possibleValues:
				self._sql.insert(
					session,
					"PRODUCT_PROPERTY_VALUE",
					{
						"productId": data["productId"],
						"productVersion": data["productVersion"],
						"packageVersion": data["packageVersion"],
						"propertyId": data["propertyId"],
						"value": value,
						"isDefault": (value in defaultValues),
					},
				)

	def productProperty_updateObject(self, productProperty: ProductProperty) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productProperty_updateObject(self, productProperty)
		data = self._objectToDatabaseHash(productProperty)
		where = self._uniqueCondition(productProperty)
		possibleValues = data["possibleValues"]
		defaultValues = data["defaultValues"]
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data["possibleValues"]
		del data["defaultValues"]
		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT_PROPERTY", where, data)

			self._sql.delete(session, "PRODUCT_PROPERTY_VALUE", where)
			for value in possibleValues:
				self._sql.insert(
					session,
					"PRODUCT_PROPERTY_VALUE",
					{
						"productId": data["productId"],
						"productVersion": data["productVersion"],
						"packageVersion": data["packageVersion"],
						"propertyId": data["propertyId"],
						"value": value,
						"isDefault": (value in defaultValues),
					},
				)

	def productProperty_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductProperty]:
		ConfigDataBackend.productProperty_getObjects(self, attributes=[], **filter)
		logger.info("Getting product properties, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			ProductProperty, attributes or [], filter
		)

		readValues = (
			not attributes
			or "possibleValues" in attributes
			or "defaultValues" in attributes
		)

		query = self._createQuery("PRODUCT_PROPERTY", attributes, filter)
		productProperties = []
		with self._sql.session() as session:
			for productProperty in self._sql.getSet(session, query):
				productProperty["possibleValues"] = []
				productProperty["defaultValues"] = []
				if readValues:
					valueQuery = (
						"select value, isDefault "
						"from PRODUCT_PROPERTY_VALUE "
						f"where `propertyId` = '{productProperty['propertyId']}' "
						f"AND `productId` = '{productProperty['productId']}' "
						f"AND `productVersion` = '{productProperty['productVersion']}' "
						f"AND `packageVersion` = '{productProperty['packageVersion']}'"
					)
					for propertyValues in self._sql.getSet(session, valueQuery):
						productProperty["possibleValues"].append(
							propertyValues["value"]
						)
						if propertyValues["isDefault"]:
							productProperty["defaultValues"].append(
								propertyValues["value"]
							)

				productProperties.append(ProductProperty.fromHash(productProperty))

		return productProperties

	def productProperty_deleteObjects(
		self, productProperties: list[ProductProperty]
	) -> None:
		ConfigDataBackend.productProperty_deleteObjects(self, productProperties)
		with self._sql.session() as session:
			for productProperty in forceObjectClassList(
				productProperties, ProductProperty
			):
				logger.info("Deleting product property %s", productProperty)
				where = self._uniqueCondition(productProperty)
				self._sql.delete(session, "PRODUCT_PROPERTY_VALUE", where)
				self._sql.delete(session, "PRODUCT_PROPERTY", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(
		self, productDependency: ProductDependency
	) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productDependency_insertObject(self, productDependency)
		data = self._objectToDatabaseHash(productDependency)

		where = self._uniqueCondition(productDependency)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `PRODUCT_DEPENDENCY` where {where}"
			):
				self._sql.update(
					session, "PRODUCT_DEPENDENCY", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "PRODUCT_DEPENDENCY", data)

	def productDependency_updateObject(
		self, productDependency: ProductDependency
	) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productDependency_updateObject(self, productDependency)
		data = self._objectToDatabaseHash(productDependency)
		where = self._uniqueCondition(productDependency)
		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT_DEPENDENCY", where, data)

	def productDependency_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductDependency]:
		ConfigDataBackend.productDependency_getObjects(self, attributes=[], **filter)
		logger.info("Getting product dependencies, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			ProductDependency, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				ProductDependency.fromHash(res)
				for res in self._sql.getSet(
					session, self._createQuery("PRODUCT_DEPENDENCY", attributes, filter)
				)
			]

	def productDependency_deleteObjects(
		self, productDependencies: list[ProductDependency]
	) -> None:
		ConfigDataBackend.productDependency_deleteObjects(self, productDependencies)
		with self._sql.session() as session:
			for productDependency in forceObjectClassList(
				productDependencies, ProductDependency
			):
				logger.info("Deleting product dependency %s", productDependency)
				where = self._uniqueCondition(productDependency)
				self._sql.delete(session, "PRODUCT_DEPENDENCY", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot: ProductOnDepot) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productOnDepot_insertObject(self, productOnDepot)
		data = self._objectToDatabaseHash(productOnDepot)

		productOnDepotClone = productOnDepot.clone(identOnly=True)
		productOnDepotClone.productVersion = None
		productOnDepotClone.packageVersion = None
		productOnDepotClone.productType = None
		where = self._uniqueCondition(productOnDepotClone)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `PRODUCT_ON_DEPOT` where {where}"
			):
				self._sql.update(
					session, "PRODUCT_ON_DEPOT", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "PRODUCT_ON_DEPOT", data)

	def productOnDepot_updateObject(self, productOnDepot: ProductOnDepot) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productOnDepot_updateObject(self, productOnDepot)
		data = self._objectToDatabaseHash(productOnDepot)
		where = self._uniqueCondition(productOnDepot)
		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT_ON_DEPOT", where, data)

	def productOnDepot_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductOnDepot]:
		ConfigDataBackend.productOnDepot_getObjects(self, attributes=[], **filter)
		(attributes, filter) = self._adjustAttributes(
			ProductOnDepot, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				ProductOnDepot.fromHash(res)
				for res in self._sql.getSet(
					session, self._createQuery("PRODUCT_ON_DEPOT", attributes, filter)
				)
			]

	def productOnDepot_deleteObjects(
		self, productOnDepots: list[ProductOnDepot]
	) -> None:
		ConfigDataBackend.productOnDepot_deleteObjects(self, productOnDepots)
		with self._sql.session() as session:
			for productOnDepot in forceObjectClassList(productOnDepots, ProductOnDepot):
				logger.info("Deleting productOnDepot %s", productOnDepot)
				where = self._uniqueCondition(productOnDepot)
				self._sql.delete(session, "PRODUCT_ON_DEPOT", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient: ProductOnClient) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productOnClient_insertObject(self, productOnClient)
		data = self._objectToDatabaseHash(productOnClient)

		productOnClientClone = productOnClient.clone(identOnly=True)
		productOnClientClone.productVersion = None
		productOnClientClone.packageVersion = None
		productOnClientClone.productType = None
		where = self._uniqueCondition(productOnClientClone)

		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `PRODUCT_ON_CLIENT` where {where}"
			):
				self._sql.update(
					session, "PRODUCT_ON_CLIENT", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "PRODUCT_ON_CLIENT", data)

	def productOnClient_updateObject(self, productOnClient: ProductOnClient) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productOnClient_updateObject(self, productOnClient)
		data = self._objectToDatabaseHash(productOnClient)
		where = self._uniqueCondition(productOnClient)
		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT_ON_CLIENT", where, data)

	def productOnClient_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductOnClient]:
		ConfigDataBackend.productOnClient_getObjects(self, attributes=[], **filter)
		logger.info("Getting productOnClients, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			ProductOnClient, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				ProductOnClient.fromHash(res)
				for res in self._sql.getSet(
					session, self._createQuery("PRODUCT_ON_CLIENT", attributes, filter)
				)
			]

	def productOnClient_deleteObjects(
		self, productOnClients: list[ProductOnClient]
	) -> None:
		ConfigDataBackend.productOnClient_deleteObjects(self, productOnClients)
		with self._sql.session() as session:
			for productOnClient in forceObjectClassList(
				productOnClients, ProductOnClient
			):
				logger.info("Deleting productOnClient %s", productOnClient)
				where = self._uniqueCondition(productOnClient)
				self._sql.delete(session, "PRODUCT_ON_CLIENT", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(
		self, productPropertyState: ProductPropertyState
	) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productPropertyState_insertObject(self, productPropertyState)
		with self._sql.session() as session:
			if not self._sql.getSet(
				session,
				self._createQuery(
					"HOST", ["hostId"], {"hostId": productPropertyState.objectId}
				),
			):
				raise BackendReferentialIntegrityError(
					f"Object '{productPropertyState.objectId}' does not exist"
				)
			data = self._objectToDatabaseHash(productPropertyState)
			data["values"] = json.dumps(data["values"])

			where = self._uniqueCondition(productPropertyState)
			if self._sql.getRow(
				session, f"select * from `PRODUCT_PROPERTY_STATE` where {where}"
			):
				self._sql.update(
					session, "PRODUCT_PROPERTY_STATE", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "PRODUCT_PROPERTY_STATE", data)

	def productPropertyState_updateObject(
		self, productPropertyState: ProductPropertyState
	) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.productPropertyState_updateObject(self, productPropertyState)
		data = self._objectToDatabaseHash(productPropertyState)
		where = self._uniqueCondition(productPropertyState)
		data["values"] = json.dumps(data["values"])
		with self._sql.session() as session:
			self._sql.update(session, "PRODUCT_PROPERTY_STATE", where, data)

	def productPropertyState_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ProductPropertyState]:
		ConfigDataBackend.productPropertyState_getObjects(self, attributes=[], **filter)
		logger.info("Getting productPropertyStates, filter: %s", filter)
		productPropertyStates = []
		(attributes, filter) = self._adjustAttributes(
			ProductPropertyState, attributes or [], filter
		)
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("PRODUCT_PROPERTY_STATE", attributes, filter)
			):
				try:
					res["values"] = json.loads(res["values"])
				except KeyError:
					pass  # Could be non-existing and it would be okay.
				productPropertyStates.append(ProductPropertyState.fromHash(res))
		return productPropertyStates

	def productPropertyState_deleteObjects(
		self, productPropertyStates: list[ProductPropertyState]
	) -> None:
		ConfigDataBackend.productPropertyState_deleteObjects(
			self, productPropertyStates
		)
		with self._sql.session() as session:
			for productPropertyState in forceObjectClassList(
				productPropertyStates, ProductPropertyState
			):
				logger.info("Deleting productPropertyState %s", productPropertyState)
				where = self._uniqueCondition(productPropertyState)
				self._sql.delete(session, "PRODUCT_PROPERTY_STATE", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group: Group) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.group_insertObject(self, group)
		data = self._objectToDatabaseHash(group)

		where = self._uniqueCondition(group)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `GROUP` where {where}"):
				self._sql.update(session, "GROUP", where, data, updateWhereNone=True)
			else:
				self._sql.insert(session, "GROUP", data)

	def group_updateObject(self, group: Group) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.group_updateObject(self, group)
		data = self._objectToDatabaseHash(group)
		where = self._uniqueCondition(group)
		with self._sql.session() as session:
			self._sql.update(session, "GROUP", where, data)

	def group_getObjects(self, attributes: list[str] = None, **filter) -> list[Group]:
		ConfigDataBackend.group_getObjects(self, attributes=[], **filter)
		logger.info("Getting groups, filter: %s", filter)
		groups = []
		(attributes, filter) = self._adjustAttributes(Group, attributes or [], filter)
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("GROUP", attributes, filter)
			):
				self._adjustResult(Group, res)
				groups.append(Group.fromHash(res))
		return groups

	def group_deleteObjects(self, groups: list[Group]) -> None:
		ConfigDataBackend.group_deleteObjects(self, groups)
		with self._sql.session() as session:
			for group in forceObjectClassList(groups, Group):
				logger.info("Deleting group %s", group)
				where = self._uniqueCondition(group)
				self._sql.delete(session, "GROUP", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup: ObjectToGroup) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.objectToGroup_insertObject(self, objectToGroup)
		data = self._objectToDatabaseHash(objectToGroup)

		where = self._uniqueCondition(objectToGroup)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `OBJECT_TO_GROUP` where {where}"
			):
				self._sql.update(
					session, "OBJECT_TO_GROUP", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "OBJECT_TO_GROUP", data)

	def objectToGroup_updateObject(self, objectToGroup: ObjectToGroup) -> None:
		self._check_module("mysql_backend")
		ConfigDataBackend.objectToGroup_updateObject(self, objectToGroup)
		data = self._objectToDatabaseHash(objectToGroup)
		where = self._uniqueCondition(objectToGroup)
		with self._sql.session() as session:
			self._sql.update(session, "OBJECT_TO_GROUP", where, data)

	def objectToGroup_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[ObjectToGroup]:
		ConfigDataBackend.objectToGroup_getObjects(self, attributes=[], **filter)
		logger.info("Getting objectToGroups, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			ObjectToGroup, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				ObjectToGroup.fromHash(res)
				for res in self._sql.getSet(
					session, self._createQuery("OBJECT_TO_GROUP", attributes, filter)
				)
			]

	def objectToGroup_deleteObjects(self, objectToGroups: list[ObjectToGroup]) -> None:
		ConfigDataBackend.objectToGroup_deleteObjects(self, objectToGroups)
		with self._sql.session() as session:
			for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
				logger.info("Deleting objectToGroup %s", objectToGroup)
				where = self._uniqueCondition(objectToGroup)
				self._sql.delete(session, "OBJECT_TO_GROUP", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_insertObject(self, licenseContract: LicenseContract) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licenseContract_insertObject(self, licenseContract)
		data = self._objectToDatabaseHash(licenseContract)

		where = self._uniqueCondition(licenseContract)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `LICENSE_CONTRACT` where {where}"
			):
				self._sql.update(
					session, "LICENSE_CONTRACT", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "LICENSE_CONTRACT", data)

	def licenseContract_updateObject(self, licenseContract: LicenseContract) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licenseContract_updateObject(self, licenseContract)
		data = self._objectToDatabaseHash(licenseContract)
		where = self._uniqueCondition(licenseContract)
		with self._sql.session() as session:
			self._sql.update(session, "LICENSE_CONTRACT", where, data)

	def licenseContract_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[LicenseContract]:
		ConfigDataBackend.licenseContract_getObjects(self, attributes=[], **filter)
		logger.info("Getting licenseContracts, filter: %s", filter)
		licenseContracts = []
		(attributes, filter) = self._adjustAttributes(
			LicenseContract, attributes or [], filter
		)
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("LICENSE_CONTRACT", attributes, filter)
			):
				self._adjustResult(LicenseContract, res)
				licenseContracts.append(LicenseContract.fromHash(res))
		return licenseContracts

	def licenseContract_deleteObjects(
		self, licenseContracts: list[LicenseContract]
	) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licenseContract_deleteObjects(self, licenseContracts)
		with self._sql.session() as session:
			for licenseContract in forceObjectClassList(
				licenseContracts, LicenseContract
			):
				logger.info("Deleting licenseContract %s", licenseContract)
				where = self._uniqueCondition(licenseContract)
				self._sql.delete(session, "LICENSE_CONTRACT", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_insertObject(self, softwareLicense: SoftwareLicense) -> None:
		self._check_module("license_management")

		ConfigDataBackend.softwareLicense_insertObject(self, softwareLicense)
		data = self._objectToDatabaseHash(softwareLicense)

		where = self._uniqueCondition(softwareLicense)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `SOFTWARE_LICENSE` where {where}"
			):
				self._sql.update(
					session, "SOFTWARE_LICENSE", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "SOFTWARE_LICENSE", data)

	def softwareLicense_updateObject(self, softwareLicense: SoftwareLicense) -> None:
		self._check_module("license_management")

		ConfigDataBackend.softwareLicense_updateObject(self, softwareLicense)
		data = self._objectToDatabaseHash(softwareLicense)
		where = self._uniqueCondition(softwareLicense)
		with self._sql.session() as session:
			self._sql.update(session, "SOFTWARE_LICENSE", where, data)

	def softwareLicense_getObjects(
		self, attributes: list[str] = None, **filter
	) -> None:
		ConfigDataBackend.softwareLicense_getObjects(self, attributes=[], **filter)
		logger.info("Getting softwareLicenses, filter: %s", filter)
		softwareLicenses = []
		(attributes, filter) = self._adjustAttributes(
			SoftwareLicense, attributes or [], filter
		)
		with self._sql.session() as session:
			for res in self._sql.getSet(
				session, self._createQuery("SOFTWARE_LICENSE", attributes, filter)
			):
				self._adjustResult(SoftwareLicense, res)
				softwareLicenses.append(SoftwareLicense.fromHash(res))
		return softwareLicenses

	def softwareLicense_deleteObjects(
		self, softwareLicenses: list[SoftwareLicense]
	) -> None:
		ConfigDataBackend.softwareLicense_deleteObjects(self, softwareLicenses)
		with self._sql.session() as session:
			for softwareLicense in forceObjectClassList(
				softwareLicenses, SoftwareLicense
			):
				logger.info("Deleting softwareLicense %s", softwareLicense)
				where = self._uniqueCondition(softwareLicense)
				self._sql.delete(session, "SOFTWARE_LICENSE", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePools
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_insertObject(self, licensePool: LicensePool) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licensePool_insertObject(self, licensePool)
		data = self._objectToDatabaseHash(licensePool)
		productIds = data["productIds"]
		del data["productIds"]

		where = self._uniqueCondition(licensePool)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `LICENSE_POOL` where {where}"):
				self._sql.update(
					session, "LICENSE_POOL", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "LICENSE_POOL", data)

			self._sql.delete(
				session,
				"PRODUCT_ID_TO_LICENSE_POOL",
				f"`licensePoolId` = '{data['licensePoolId']}'",
			)

			for productId in productIds:
				mapping = {
					"productId": productId,
					"licensePoolId": data["licensePoolId"],
				}
				self._sql.insert(session, "PRODUCT_ID_TO_LICENSE_POOL", mapping)

	def licensePool_updateObject(self, licensePool: LicensePool) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licensePool_updateObject(self, licensePool)
		data = self._objectToDatabaseHash(licensePool)
		where = self._uniqueCondition(licensePool)
		productIds = data["productIds"]
		del data["productIds"]
		with self._sql.session() as session:
			self._sql.update(session, "LICENSE_POOL", where, data)
			self._sql.delete(
				session,
				"PRODUCT_ID_TO_LICENSE_POOL",
				f"`licensePoolId` = '{data['licensePoolId']}'",
			)

			for productId in productIds:
				mapping = {
					"productId": productId,
					"licensePoolId": data["licensePoolId"],
				}
				self._sql.insert(session, "PRODUCT_ID_TO_LICENSE_POOL", mapping)

	def licensePool_getObjects(self, attributes: list[str] = None, **filter) -> None:
		ConfigDataBackend.licensePool_getObjects(self, attributes=[], **filter)
		logger.info("Getting licensePools, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			LicensePool, attributes or [], filter
		)

		with self._sql.session() as session:
			try:
				if filter["productIds"]:
					licensePoolIds = filter.get("licensePoolId")
					query = self._createQuery(
						"PRODUCT_ID_TO_LICENSE_POOL",
						["licensePoolId"],
						{
							"licensePoolId": licensePoolIds,
							"productId": filter["productIds"],
						},
					)

					filter["licensePoolId"] = [
						res["licensePoolId"] for res in self._sql.getSet(session, query)
					]

					if not filter["licensePoolId"]:
						return []

				del filter["productIds"]
			except KeyError:
				pass

			readProductIds = not attributes or "productIds" in attributes

			licensePools = []
			attrs = [attr for attr in attributes if attr != "productIds"]
			for res in self._sql.getSet(
				session, self._createQuery("LICENSE_POOL", attrs, filter)
			):
				res["productIds"] = []
				if readProductIds:
					for res2 in self._sql.getSet(
						session,
						f"select * from PRODUCT_ID_TO_LICENSE_POOL where `licensePoolId` = '{res['licensePoolId']}'",
					):
						res["productIds"].append(res2["productId"])
				self._adjustResult(LicensePool, res)
				licensePools.append(LicensePool.fromHash(res))
			return licensePools

	def licensePool_deleteObjects(self, licensePools: list[LicensePool]) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licensePool_deleteObjects(self, licensePools)
		with self._sql.session() as session:
			for licensePool in forceObjectClassList(licensePools, LicensePool):
				logger.info("Deleting licensePool %s", licensePool)
				where = self._uniqueCondition(licensePool)
				self._sql.delete(
					session,
					"PRODUCT_ID_TO_LICENSE_POOL",
					f"`licensePoolId` = '{licensePool.id}'",
				)
				self._sql.delete(session, "LICENSE_POOL", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_insertObject(
		self, softwareLicenseToLicensePool: SoftwareLicenseToLicensePool
	) -> None:
		self._check_module("license_management")

		ConfigDataBackend.softwareLicenseToLicensePool_insertObject(
			self, softwareLicenseToLicensePool
		)
		data = self._objectToDatabaseHash(softwareLicenseToLicensePool)

		where = self._uniqueCondition(softwareLicenseToLicensePool)
		with self._sql.session() as session:
			if self._sql.getRow(
				session,
				f"select * from `SOFTWARE_LICENSE_TO_LICENSE_POOL` where {where}",
			):
				self._sql.update(
					session,
					"SOFTWARE_LICENSE_TO_LICENSE_POOL",
					where,
					data,
					updateWhereNone=True,
				)
			else:
				self._sql.insert(session, "SOFTWARE_LICENSE_TO_LICENSE_POOL", data)

	def softwareLicenseToLicensePool_updateObject(
		self, softwareLicenseToLicensePool: SoftwareLicenseToLicensePool
	) -> None:
		self._check_module("license_management")

		ConfigDataBackend.softwareLicenseToLicensePool_updateObject(
			self, softwareLicenseToLicensePool
		)
		data = self._objectToDatabaseHash(softwareLicenseToLicensePool)
		where = self._uniqueCondition(softwareLicenseToLicensePool)
		with self._sql.session() as session:
			self._sql.update(session, "SOFTWARE_LICENSE_TO_LICENSE_POOL", where, data)

	def softwareLicenseToLicensePool_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[SoftwareLicenseToLicensePool]:
		ConfigDataBackend.softwareLicenseToLicensePool_getObjects(
			self, attributes=[], **filter
		)
		logger.info("Getting softwareLicenseToLicensePool, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			SoftwareLicenseToLicensePool, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				SoftwareLicenseToLicensePool.fromHash(res)
				for res in self._sql.getSet(
					session,
					self._createQuery(
						"SOFTWARE_LICENSE_TO_LICENSE_POOL", attributes, filter
					),
				)
			]

	def softwareLicenseToLicensePool_deleteObjects(
		self, softwareLicenseToLicensePools: list[SoftwareLicenseToLicensePool]
	) -> None:
		self._check_module("license_management")

		ConfigDataBackend.softwareLicenseToLicensePool_deleteObjects(
			self, softwareLicenseToLicensePools
		)
		with self._sql.session() as session:
			for softwareLicenseToLicensePool in forceObjectClassList(
				softwareLicenseToLicensePools, SoftwareLicenseToLicensePool
			):
				logger.info(
					"Deleting softwareLicenseToLicensePool %s",
					softwareLicenseToLicensePool,
				)
				where = self._uniqueCondition(softwareLicenseToLicensePool)
				self._sql.delete(session, "SOFTWARE_LICENSE_TO_LICENSE_POOL", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_insertObject(self, licenseOnClient: LicenseOnClient) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licenseOnClient_insertObject(self, licenseOnClient)
		data = self._objectToDatabaseHash(licenseOnClient)

		where = self._uniqueCondition(licenseOnClient)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `LICENSE_ON_CLIENT` where {where}"
			):
				self._sql.update(
					session, "LICENSE_ON_CLIENT", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "LICENSE_ON_CLIENT", data)

	def licenseOnClient_updateObject(self, licenseOnClient: LicenseOnClient) -> None:
		self._check_module("license_management")

		ConfigDataBackend.licenseOnClient_updateObject(self, licenseOnClient)
		data = self._objectToDatabaseHash(licenseOnClient)
		where = self._uniqueCondition(licenseOnClient)
		with self._sql.session() as session:
			self._sql.update(session, "LICENSE_ON_CLIENT", where, data)

	def licenseOnClient_getObjects(
		self, attributes: list[str] = None, **filter
	) -> None:
		ConfigDataBackend.licenseOnClient_getObjects(self, attributes=[], **filter)
		logger.info("Getting licenseOnClient, filter: %s", filter)
		(attributes, filter) = self._adjustAttributes(
			LicenseOnClient, attributes or [], filter
		)
		with self._sql.session() as session:
			return [
				LicenseOnClient.fromHash(res)
				for res in self._sql.getSet(
					session, self._createQuery("LICENSE_ON_CLIENT", attributes, filter)
				)
			]

	def licenseOnClient_deleteObjects(
		self, licenseOnClients: list[LicenseOnClient]
	) -> None:
		ConfigDataBackend.licenseOnClient_deleteObjects(self, licenseOnClients)
		with self._sql.session() as session:
			for licenseOnClient in forceObjectClassList(
				licenseOnClients, LicenseOnClient
			):
				logger.info("Deleting licenseOnClient %s", licenseOnClient)
				where = self._uniqueCondition(licenseOnClient)
				self._sql.delete(session, "LICENSE_ON_CLIENT", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_insertObject(self, auditSoftware: AuditSoftware) -> None:
		ConfigDataBackend.auditSoftware_insertObject(self, auditSoftware)
		data = self._objectToDatabaseHash(auditSoftware)

		where = self._uniqueCondition(auditSoftware)
		with self._sql.session() as session:
			if self._sql.getRow(session, f"select * from `SOFTWARE` where {where}"):
				self._sql.update(session, "SOFTWARE", where, data, updateWhereNone=True)
			else:
				self._sql.insert(session, "SOFTWARE", data)

	def auditSoftware_updateObject(self, auditSoftware: AuditSoftware) -> None:
		ConfigDataBackend.auditSoftware_updateObject(self, auditSoftware)
		data = self._objectToDatabaseHash(auditSoftware)
		where = self._uniqueCondition(auditSoftware)
		with self._sql.session() as session:
			self._sql.update(session, "SOFTWARE", where, data)

	def auditSoftware_getHashes(
		self, attributes: list[str] = None, **filter
	) -> list[dict[str, Any]]:
		(attributes, filter) = self._adjustAttributes(
			AuditSoftware, attributes or [], filter
		)
		with self._sql.session() as session:
			return self._sql.getSet(
				session, self._createQuery("SOFTWARE", attributes, filter)
			)

	def auditSoftware_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditSoftware]:
		attributes = attributes or []
		ConfigDataBackend.auditSoftware_getObjects(self, attributes=[], **filter)
		logger.info("Getting auditSoftware, filter: %s", filter)
		return [
			AuditSoftware.fromHash(h)
			for h in self.auditSoftware_getHashes(attributes, **filter)
		]

	def auditSoftware_deleteObjects(self, auditSoftwares: list[AuditSoftware]) -> None:
		ConfigDataBackend.auditSoftware_deleteObjects(self, auditSoftwares)
		with self._sql.session() as session:
			for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware):
				logger.info("Deleting auditSoftware %s", auditSoftware)
				where = self._uniqueCondition(auditSoftware)
				self._sql.delete(session, "SOFTWARE", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_insertObject(
		self, auditSoftwareToLicensePool: AuditSoftwareToLicensePool
	) -> None:
		ConfigDataBackend.auditSoftwareToLicensePool_insertObject(
			self, auditSoftwareToLicensePool
		)
		data = self._objectToDatabaseHash(auditSoftwareToLicensePool)

		where = self._uniqueCondition(auditSoftwareToLicensePool)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `AUDIT_SOFTWARE_TO_LICENSE_POOL` where {where}"
			):
				self._sql.update(
					session,
					"AUDIT_SOFTWARE_TO_LICENSE_POOL",
					where,
					data,
					updateWhereNone=True,
				)
			else:
				self._sql.insert(session, "AUDIT_SOFTWARE_TO_LICENSE_POOL", data)

	def auditSoftwareToLicensePool_updateObject(
		self, auditSoftwareToLicensePool: AuditSoftwareToLicensePool
	) -> None:
		ConfigDataBackend.auditSoftwareToLicensePool_updateObject(
			self, auditSoftwareToLicensePool
		)
		data = self._objectToDatabaseHash(auditSoftwareToLicensePool)
		where = self._uniqueCondition(auditSoftwareToLicensePool)
		with self._sql.session() as session:
			self._sql.update(session, "AUDIT_SOFTWARE_TO_LICENSE_POOL", where, data)

	def auditSoftwareToLicensePool_getHashes(
		self, attributes: list[str] = None, **filter
	) -> list[dict[str, Any]]:
		(attributes, filter) = self._adjustAttributes(
			AuditSoftwareToLicensePool, attributes or [], filter
		)
		with self._sql.session() as session:
			return self._sql.getSet(
				session,
				self._createQuery("AUDIT_SOFTWARE_TO_LICENSE_POOL", attributes, filter),
			)

	def auditSoftwareToLicensePool_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditSoftwareToLicensePool]:
		attributes = attributes or []
		ConfigDataBackend.auditSoftwareToLicensePool_getObjects(
			self, attributes=[], **filter
		)
		logger.info("Getting auditSoftwareToLicensePool, filter: %s", filter)
		return [
			AuditSoftwareToLicensePool.fromHash(h)
			for h in self.auditSoftwareToLicensePool_getHashes(attributes, **filter)
		]

	def auditSoftwareToLicensePool_deleteObjects(
		self, auditSoftwareToLicensePools: list[AuditSoftwareToLicensePool]
	) -> None:
		ConfigDataBackend.auditSoftwareToLicensePool_deleteObjects(
			self, auditSoftwareToLicensePools
		)
		with self._sql.session() as session:
			for auditSoftwareToLicensePool in forceObjectClassList(
				auditSoftwareToLicensePools, AuditSoftwareToLicensePool
			):
				logger.info("Deleting auditSoftware %s", auditSoftwareToLicensePool)
				where = self._uniqueCondition(auditSoftwareToLicensePool)
				self._sql.delete(session, "AUDIT_SOFTWARE_TO_LICENSE_POOL", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_insertObject(
		self, auditSoftwareOnClient: AuditSoftwareOnClient
	) -> None:
		ConfigDataBackend.auditSoftwareOnClient_insertObject(
			self, auditSoftwareOnClient
		)
		data = self._objectToDatabaseHash(auditSoftwareOnClient)

		where = self._uniqueCondition(auditSoftwareOnClient)
		with self._sql.session() as session:
			if self._sql.getRow(
				session, f"select * from `SOFTWARE_CONFIG` where {where}"
			):
				self._sql.update(
					session, "SOFTWARE_CONFIG", where, data, updateWhereNone=True
				)
			else:
				self._sql.insert(session, "SOFTWARE_CONFIG", data)

	def auditSoftwareOnClient_updateObject(
		self, auditSoftwareOnClient: AuditSoftwareOnClient
	) -> None:
		ConfigDataBackend.auditSoftwareOnClient_updateObject(
			self, auditSoftwareOnClient
		)
		data = self._objectToDatabaseHash(auditSoftwareOnClient)
		where = self._uniqueCondition(auditSoftwareOnClient)
		with self._sql.session() as session:
			self._sql.update(session, "SOFTWARE_CONFIG", where, data)

	def auditSoftwareOnClient_getHashes(
		self, attributes: list[str] = None, **filter
	) -> list[dict[str, Any]]:
		(attributes, filter) = self._adjustAttributes(
			AuditSoftwareOnClient, attributes or [], filter
		)
		with self._sql.session() as session:
			return self._sql.getSet(
				session, self._createQuery("SOFTWARE_CONFIG", attributes, filter)
			)

	def auditSoftwareOnClient_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditSoftwareOnClient]:
		attributes = attributes or []
		ConfigDataBackend.auditSoftwareOnClient_getObjects(
			self, attributes=[], **filter
		)
		logger.info("Getting auditSoftwareOnClient, filter: %s", filter)
		return [
			AuditSoftwareOnClient.fromHash(h)
			for h in self.auditSoftwareOnClient_getHashes(attributes, **filter)
		]

	def auditSoftwareOnClient_deleteObjects(
		self, auditSoftwareOnClients: list[AuditSoftwareOnClient]
	) -> None:
		ConfigDataBackend.auditSoftwareOnClient_deleteObjects(
			self, auditSoftwareOnClients
		)
		with self._sql.session() as session:
			for auditSoftwareOnClient in forceObjectClassList(
				auditSoftwareOnClients, AuditSoftwareOnClient
			):
				logger.info("Deleting auditSoftwareOnClient %s", auditSoftwareOnClient)
				where = self._uniqueCondition(auditSoftwareOnClient)
				self._sql.delete(session, "SOFTWARE_CONFIG", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _uniqueAuditHardwareCondition(self, auditHardware: AuditHardware) -> str:
		try:
			auditHardware = auditHardware.toHash()
		except AttributeError:
			pass

		def createCondition():
			listWithNone = [None]

			for attribute, value in auditHardware.items():
				if attribute in ("hardwareClass", "type"):
					continue

				if value is None or value == listWithNone:
					yield f"`{attribute}` is NULL"
				elif isinstance(value, (float, int, bool)):
					yield f"`{attribute}` = {value}"
				else:
					yield f"`{attribute}` = '{self._sql.escapeApostrophe(self._sql.escapeBackslash(self._sql.escapeColon(value)))}'"

		return " and ".join(createCondition())

	def _getHardwareIds(self, auditHardware: AuditHardware) -> list[str]:
		try:
			auditHardware = auditHardware.toHash()
		except AttributeError:  # Method not present
			pass

		for attribute, value in auditHardware.items():
			if value is None:
				auditHardware[attribute] = [None]
			elif isinstance(value, str):
				auditHardware[attribute] = self._sql.escapeAsterisk(value)

		logger.debug("Getting hardware ids, filter %s", auditHardware)
		hardwareIds = self._auditHardware_search(
			returnHardwareIds=True, attributes=[], **auditHardware
		)
		logger.debug("Found hardware ids: %s", hardwareIds)
		return hardwareIds

	def auditHardware_insertObject(self, auditHardware: AuditHardware) -> None:
		ConfigDataBackend.auditHardware_insertObject(self, auditHardware)

		logger.info("Inserting auditHardware: %s", auditHardware)
		hardwareHash = auditHardware.toHash()
		filter = {}
		for attribute, value in hardwareHash.items():
			if value is None:
				filter[attribute] = [None]
			elif isinstance(value, str):
				filter[attribute] = self._sql.escapeAsterisk(value)
			else:
				filter[attribute] = value
		res = self.auditHardware_getObjects(**filter)
		if res:
			return

		table = "HARDWARE_DEVICE_" + hardwareHash["hardwareClass"]
		del hardwareHash["hardwareClass"]
		del hardwareHash["type"]

		with self._sql.session() as session:
			self._sql.insert(session, table, hardwareHash)

	def auditHardware_updateObject(self, auditHardware: AuditHardware) -> None:
		ConfigDataBackend.auditHardware_updateObject(self, auditHardware)

		logger.info("Updating auditHardware: %s", auditHardware)
		filter = {}
		for attribute, value in auditHardware.toHash().items():
			if value is None:
				filter[attribute] = [None]

		if not self.auditHardware_getObjects(**filter):
			raise BackendMissingDataError(
				f"AuditHardware '{auditHardware.getIdent()}' not found"
			)

	def auditHardware_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditHardware]:
		attributes = attributes or []
		ConfigDataBackend.auditHardware_getObjects(self, attributes=[], **filter)

		logger.info("Getting auditHardwares, filter: %s", filter)
		return [
			AuditHardware.fromHash(h)
			for h in self.auditHardware_getHashes(attributes, **filter)
		]

	def auditHardware_getHashes(
		self, attributes: list[str] = None, **filter
	) -> list[dict[str, Any]]:
		return self._auditHardware_search(
			returnHardwareIds=False, attributes=attributes or [], **filter
		)

	def _auditHardware_search(
		self, returnHardwareIds: bool = False, attributes: list[str] = None, **filter
	):
		attributes = attributes or []
		hardwareClasses = set()
		hardwareClass = filter.get("hardwareClass")
		if hardwareClass not in ([], None):
			for hwc in forceUnicodeList(hardwareClass):
				regex = re.compile(f"^{hwc.replace('*', '.*')}$")
				for key in self._auditHardwareConfig:
					if regex.search(key):
						hardwareClasses.add(key)

			if not hardwareClasses:
				return []

		if not hardwareClasses:
			hardwareClasses = set(self._auditHardwareConfig)

		for unwanted_key in ("hardwareClass", "type"):
			try:
				del filter[unwanted_key]
			except KeyError:
				pass  # not there - everything okay.

		try:
			attributes.remove("hardwareClass")
		except ValueError:
			pass

		for attribute in attributes:
			if attribute not in filter:
				filter[attribute] = None

		if returnHardwareIds and attributes and "hardware_id" not in attributes:
			attributes.append("hardware_id")

		results = []
		with self._sql.session() as session:
			for hardwareClass in hardwareClasses:
				classFilter = {}
				for attribute, value in filter.items():
					valueInfo = self._auditHardwareConfig[hardwareClass].get(attribute)
					if not valueInfo:
						logger.debug(
							"Skipping hardwareClass '%s', because of missing info for attribute '%s'",
							hardwareClass,
							attribute,
						)
						break

					try:
						if valueInfo["Scope"] != "g":
							continue
					except KeyError:
						pass

					if value is not None:
						value = forceList(value)
					classFilter[attribute] = value
				else:
					if not classFilter and filter:
						continue

					logger.debug(
						"Getting auditHardwares, hardwareClass '%s', filter: %s",
						hardwareClass,
						classFilter,
					)
					query = self._createQuery(
						"HARDWARE_DEVICE_" + hardwareClass, attributes, classFilter
					)
					for res in self._sql.getSet(session, query):
						if returnHardwareIds:
							results.append(res["hardware_id"])
							continue

						try:
							del res["hardware_id"]
						except KeyError:
							pass

						res["hardwareClass"] = hardwareClass
						for attribute, valueInfo in self._auditHardwareConfig[
							hardwareClass
						].items():
							try:
								if valueInfo["Scope"] == "i":
									continue
							except KeyError:
								pass

							if attribute not in res:
								res[attribute] = None

						results.append(res)

		return results

	def auditHardware_deleteObjects(self, auditHardwares: AuditHardware) -> None:
		ConfigDataBackend.auditHardware_deleteObjects(self, auditHardwares)
		with self._sql.session() as session:
			for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
				logger.info("Deleting auditHardware: %s", auditHardware)

				where = self._uniqueAuditHardwareCondition(auditHardware)
				hardwareClass = auditHardware.getHardwareClass()
				for hardwareId in self._getHardwareIds(auditHardware):
					self._sql.delete(
						session,
						f"HARDWARE_CONFIG_{hardwareClass}",
						f"`hardware_id` = {hardwareId}",
					)

				self._sql.delete(session, f"HARDWARE_DEVICE_{hardwareClass}", where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _extractAuditHardwareHash(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> Tuple[dict[str, Any], dict[str, Any]]:
		try:
			auditHardwareOnHost = auditHardwareOnHost.toHash()
		except AttributeError:
			pass

		hardwareClass = auditHardwareOnHost["hardwareClass"]

		auditHardware = {"type": "AuditHardware"}
		auditHardwareOnHostNew = {}
		for attribute, value in auditHardwareOnHost.items():
			if attribute == "type":
				continue

			if attribute in ("hostId", "state", "firstseen", "lastseen"):
				auditHardwareOnHostNew[attribute] = value
				continue

			if attribute == "hardwareClass":
				auditHardware[attribute] = value
				auditHardwareOnHostNew[attribute] = value
				continue

			valueInfo = self._auditHardwareConfig[hardwareClass].get(attribute)
			if valueInfo is None:
				raise BackendConfigurationError(
					f"Attribute '{attribute}' not found in config of hardware class '{hardwareClass}'"
				)

			if valueInfo.get("Scope", "") == "g":
				auditHardware[attribute] = value
				continue
			auditHardwareOnHostNew[attribute] = value

		return (auditHardware, auditHardwareOnHostNew)

	def _uniqueAuditHardwareOnHostCondition(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> str:
		(auditHardware, auditHardwareOnHost) = self._extractAuditHardwareHash(
			auditHardwareOnHost
		)

		del auditHardwareOnHost["hardwareClass"]

		hardwareFilter = {}
		for attribute, value in auditHardwareOnHost.items():
			if value is None:
				hardwareFilter[attribute] = [None]
			elif isinstance(value, str):
				hardwareFilter[attribute] = self._sql.escapeAsterisk(value)
			else:
				hardwareFilter[attribute] = value

		where = self._filterToSql(hardwareFilter)

		hwIdswhere = " or ".join(
			[
				f"`hardware_id` = {hardwareId}"
				for hardwareId in self._getHardwareIds(auditHardware)
			]
		)

		if not hwIdswhere:
			logger.error("Building unique AuditHardwareOnHost constraint impossible!")
			raise BackendReferentialIntegrityError(
				f"Hardware device '{auditHardware}' not found"
			)

		return " and ".join((where, hwIdswhere.join(("(", ")"))))

	def _auditHardwareOnHostObjectToDatabaseHash(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> dict[str, Any]:
		(auditHardware, auditHardwareOnHost) = self._extractAuditHardwareHash(
			auditHardwareOnHost
		)

		data = {
			attribute: value
			for attribute, value in auditHardwareOnHost.items()
			if attribute not in ("hardwareClass", "type")
		}

		for key, value in auditHardware.items():
			if value is None:
				auditHardware[key] = [None]
		hardwareIds = self._getHardwareIds(auditHardware)
		if not hardwareIds:
			raise BackendReferentialIntegrityError(
				f"Hardware device {auditHardware} not found"
			)
		data["hardware_id"] = hardwareIds[0]
		return data

	def auditHardwareOnHost_insertObject(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> None:
		ConfigDataBackend.auditHardwareOnHost_insertObject(self, auditHardwareOnHost)

		table = f"HARDWARE_CONFIG_{auditHardwareOnHost.getHardwareClass()}"

		where = self._uniqueAuditHardwareOnHostCondition(auditHardwareOnHost)
		with self._sql.session() as session:
			if not self._sql.getRow(session, f"select * from `{table}` where {where}"):
				data = self._auditHardwareOnHostObjectToDatabaseHash(
					auditHardwareOnHost
				)
				self._sql.insert(session, table, data)

	def auditHardwareOnHost_updateObject(
		self, auditHardwareOnHost: AuditHardwareOnHost
	) -> None:
		ConfigDataBackend.auditHardwareOnHost_updateObject(self, auditHardwareOnHost)

		logger.info("Updating auditHardwareOnHost: %s", auditHardwareOnHost)
		data = auditHardwareOnHost.toHash()
		update = {}
		toDelete = set()
		for attribute, value in data.items():
			if attribute in ("state", "lastseen", "firstseen"):
				if value is not None:
					update[attribute] = value
				toDelete.add(attribute)

		for key in toDelete:
			del data[key]

		if update:
			where = self._uniqueAuditHardwareOnHostCondition(data)
			with self._sql.session() as session:
				self._sql.update(
					session,
					f"HARDWARE_CONFIG_{auditHardwareOnHost.hardwareClass}",
					where,
					update,
				)

	def auditHardwareOnHost_getHashes(
		self, attributes: list[str] = None, **filter
	) -> list[dict[str, Any]]:
		attributes = attributes or []
		hardwareClasses = set()
		hardwareClass = filter.get("hardwareClass")
		if hardwareClass not in ([], None):
			for hwc in forceUnicodeList(hardwareClass):
				regex = re.compile(f"^{hwc.replace('*', '.*')}$")
				keys = (key for key in self._auditHardwareConfig if regex.search(key))
				for key in keys:
					hardwareClasses.add(key)

			if not hardwareClasses:
				return []

		if not hardwareClasses:
			hardwareClasses = set(self._auditHardwareConfig)

		for unwanted_key in ("hardwareClass", "type"):
			try:
				del filter[unwanted_key]
			except KeyError:
				pass  # not there - everything okay.

		for attribute in attributes:
			if attribute not in filter:
				filter[attribute] = None

		hashes = []
		with self._sql.session() as session:
			for hardwareClass in hardwareClasses:
				auditHardwareFilter = {}
				classFilter = {}
				skipHardwareClass = False
				for attribute, value in filter.items():
					valueInfo = None
					if attribute not in ("hostId", "state", "firstseen", "lastseen"):
						valueInfo = self._auditHardwareConfig[hardwareClass].get(
							attribute
						)
						if not valueInfo:
							logger.debug(
								"Skipping hardwareClass '%s', because of missing info for attribute '%s'",
								hardwareClass,
								attribute,
							)
							skipHardwareClass = True
							break

						scope = valueInfo.get("Scope", "")
						if scope == "g":
							auditHardwareFilter[attribute] = value
							continue
						if scope != "i":
							continue

					if value is not None:
						value = forceList(value)

					classFilter[attribute] = value

				if skipHardwareClass:
					continue

				hardwareIds = []
				if auditHardwareFilter:
					auditHardwareFilter["hardwareClass"] = hardwareClass
					hardwareIds = self._getHardwareIds(auditHardwareFilter)
					logger.trace("Filtered matching hardware ids: %s", hardwareIds)
					if not hardwareIds:
						continue
				classFilter["hardware_id"] = hardwareIds

				if attributes and "hardware_id" not in attributes:
					attributes.append("hardware_id")

				logger.debug(
					"Getting auditHardwareOnHosts, hardwareClass '%s', hardwareIds: %s, filter: %s",
					hardwareClass,
					hardwareIds,
					classFilter,
				)
				for res in self._sql.getSet(
					session,
					self._createQuery(
						f"HARDWARE_CONFIG_{hardwareClass}", attributes, classFilter
					),
				):
					data = self._sql.getSet(
						session,
						f"SELECT * from `HARDWARE_DEVICE_{hardwareClass}` where `hardware_id` = {res['hardware_id']}",
					)

					if not data:
						logger.error(
							"Hardware device of class '%s' with hardware_id '%s' not found",
							hardwareClass,
							res["hardware_id"],
						)
						continue

					data = data[0]
					data.update(res)
					data["hardwareClass"] = hardwareClass
					del data["hardware_id"]
					try:
						del data["config_id"]
					except KeyError:
						pass  # not there - everything okay

					for attribute in self._auditHardwareConfig[hardwareClass]:
						if attribute not in data:
							data[attribute] = None
					hashes.append(data)

		return hashes

	def auditHardwareOnHost_getObjects(
		self, attributes: list[str] = None, **filter
	) -> list[AuditHardwareOnHost]:
		ConfigDataBackend.auditHardwareOnHost_getObjects(self, attributes=[], **filter)
		attributes = attributes or []

		logger.info("Getting auditHardwareOnHosts, filter: %s", filter)
		return [
			AuditHardwareOnHost.fromHash(h)
			for h in self.auditHardwareOnHost_getHashes(attributes, **filter)
		]

	def auditHardwareOnHost_deleteObjects(
		self, auditHardwareOnHosts: list[AuditHardwareOnHost]
	) -> None:
		ConfigDataBackend.auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts)
		with self._sql.session() as session:
			for auditHardwareOnHost in forceObjectClassList(
				auditHardwareOnHosts, AuditHardwareOnHost
			):
				logger.info("Deleting auditHardwareOnHost: %s", auditHardwareOnHost)
				where = self._uniqueAuditHardwareOnHostCondition(auditHardwareOnHost)
				self._sql.delete(
					session,
					f"HARDWARE_CONFIG_{auditHardwareOnHost.getHardwareClass()}",
					where,
				)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Extension for direct connect to db
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def getData(self, query: str) -> Generator[Any, None, None]:
		onlyAllowSelect(query)

		with self._sql.session() as session:
			with timeQuery(query):
				for row in self._sql.getSet(session, query):
					for key, val in row.items():
						if isinstance(val, datetime):
							row[key] = val.strftime("%Y-%m-%d %H:%M:%S")
					yield row

	def getRawData(self, query: str) -> Generator[Any, None, None]:
		onlyAllowSelect(query)

		with self._sql.session() as session:
			with timeQuery(query):
				for row in self._sql.getRows(session, query):
					for idx, val in enumerate(row):
						if isinstance(val, datetime):
							row[idx] = val.strftime("%Y-%m-%d %H:%M:%S")
					yield row
