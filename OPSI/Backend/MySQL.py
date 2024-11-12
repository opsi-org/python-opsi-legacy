# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
MySQL-Backend
"""

import re
import time
from typing import Any, Callable, List
from urllib.parse import quote, urlencode

# Disable sqlalchemy 2.0 deprecation warnings
import sqlalchemy.util.deprecations
from opsicommon.logging import get_logger, secret_filter

sqlalchemy.util.deprecations.SILENCE_UBER_WARNING = True
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.event import listen  # noqa: E402
from sqlalchemy.orm import scoped_session, sessionmaker  # noqa: E402

from OPSI.Backend.Base import ConfigDataBackend  # noqa: E402
from OPSI.Backend.SQL import (  # noqa: E402
	SQL,
	SQLBackend,
	SQLBackendObjectModificationTracker,
)
from OPSI.Object import Product, ProductProperty  # noqa: E402
from OPSI.Types import forceHostIdList, forceInt, forceUnicode  # noqa: E402
from OPSI.Util import compareVersions  # noqa: E402

__all__ = ("MySQL", "MySQLBackend", "MySQLBackendObjectModificationTracker")

logger = get_logger("opsi.general")


def retry_on_deadlock(func: Callable) -> Callable:
	def wrapper(*args, **kwargs):
		trynum = 0
		while True:
			trynum += 1
			try:
				return func(*args, **kwargs)
			except Exception as err:  # pylint: disable=broad-except
				if trynum >= 10 or "deadlock" not in str(err).lower():
					raise
				time.sleep(0.1)

	return wrapper


class MySQL(SQL):  # pylint: disable=too-many-instance-attributes
	"""Class handling basic MySQL functionality."""

	AUTOINCREMENT = "AUTO_INCREMENT"
	ALTER_TABLE_CHANGE_SUPPORTED = True
	ESCAPED_BACKSLASH = "\\\\"
	ESCAPED_APOSTROPHE = "\\'"
	ESCAPED_ASTERISK = "\\*"

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self._address = "localhost"
		self._username = "opsi"
		self._password = "opsi"
		self._database = "opsi"
		self._databaseCharset = "utf8"
		self._connectionPoolSize = 20
		self._connectionPoolMaxOverflow = 10
		self._connectionPoolTimeout = 30
		self._connectionPoolRecyclingSeconds = -1

		# Parse arguments
		for option, value in kwargs.items():
			option = option.lower()
			if option == "address":
				self._address = forceUnicode(value)
				if self._address == "::1":
					self._address = "[::1]"
			elif option == "username":
				self._username = forceUnicode(value)
			elif option == "password":
				self._password = forceUnicode(value)
			elif option == "database":
				self._database = forceUnicode(value)
			elif option == "databasecharset":
				self._databaseCharset = str(value)
			elif option == "connectionpoolsize":
				self._connectionPoolSize = forceInt(value)
			elif option == "connectionpoolmaxoverflow":
				self._connectionPoolMaxOverflow = forceInt(value)
			# elif option == 'connectionpooltimeout':
			# self._connectionPoolTimeout = forceInt(value)
			elif option == "connectionpoolrecycling":
				self._connectionPoolRecyclingSeconds = forceInt(value)

		secret_filter.add_secrets(self._password)

		try:
			self.init_connection()
		except Exception as err:  # pylint: disable=broad-except
			if self._address != "localhost":
				raise
			logger.info("Failed to connect to socket (%s), retrying with tcp/ip", err)
			self._address = "127.0.0.1"
			self.init_connection()

	@staticmethod
	def on_engine_connect(conn, branch) -> None:  # pylint: disable=unused-argument
		conn.execute("""
			SET SESSION sql_mode=(SELECT
				REPLACE(
					REPLACE(
						REPLACE(@@sql_mode,
							'ONLY_FULL_GROUP_BY', ''
						),
						'NO_ZERO_IN_DATE', ''
					),
					'NO_ZERO_DATE', ''
				)
			);
			SET SESSION group_concat_max_len = 1000000;
			SET SESSION lock_wait_timeout = 60;
		""")
		conn.execute("SET SESSION group_concat_max_len = 1000000;")
		# conn.execute("SHOW VARIABLES LIKE 'sql_mode';").fetchone()

	def init_connection(self) -> None:
		password = quote(self._password)
		secret_filter.add_secrets(password)

		properties = {}
		if self._databaseCharset == "utf8":
			properties["charset"] = "utf8mb4"

		address = self._address
		if address.startswith("/"):
			properties["unix_socket"] = address
			address = "localhost"

		if properties:
			properties = f"?{urlencode(properties)}"
		else:
			properties = ""

		uri = f"mysql://{quote(self._username)}:{password}@{address}/{self._database}{properties}"
		logger.info("Connecting to %s", uri)

		self.engine = create_engine(
			uri,
			pool_pre_ping=True,  # auto reconnect
			encoding=self._databaseCharset,
			pool_size=self._connectionPoolSize,
			max_overflow=self._connectionPoolMaxOverflow,
			pool_recycle=self._connectionPoolRecyclingSeconds,
		)
		self.engine._should_log_info = lambda: self.log_queries  # pylint: disable=protected-access

		listen(self.engine, "engine_connect", self.on_engine_connect)

		self.session_factory = sessionmaker(
			bind=self.engine, autocommit=False, autoflush=False
		)
		self.Session = scoped_session(self.session_factory)  # pylint: disable=invalid-name

		# Test connection
		with self.session() as session:
			version_string = self.getRow(session, "SELECT @@VERSION")[0]
			logger.info("Connected to server version: %s", version_string)
			server_type = "MariaDB" if "maria" in version_string.lower() else "MySQL"
			match = re.search(r"^([\d\.]+)", version_string)
			if match:
				min_version = "5.6.5"
				if server_type == "MariaDB":
					min_version = "10.1"
				if compareVersions(match.group(1), "<", min_version):
					error = (
						f"{server_type} server version '{version_string}' to old."
						" Supported versions are MariaDB >= 10.1 and MySQL >= 5.6.5"
					)
					logger.error(error)
					raise RuntimeError(error)

	def __repr__(self) -> str:
		return f"<{self.__class__.__name__}(address={self._address})>"

	@retry_on_deadlock
	def insert(self, session: scoped_session, table: str, valueHash: Any) -> Any:
		return super().insert(session, table, valueHash)

	@retry_on_deadlock
	def update(
		self,
		session: scoped_session,
		table: str,
		where: str,
		valueHash: Any,
		updateWhereNone: bool = False,
	) -> Any:  # pylint: disable=too-many-arguments
		return super().update(session, table, where, valueHash, updateWhereNone)

	@retry_on_deadlock
	def delete(self, session: scoped_session, table: str, where: str) -> Any:
		return super().delete(session, table, where)

	def getTables(self, session: scoped_session) -> dict[str, Any]:
		"""
		Get what tables are present in the database (do not return views).

		Table names will always be uppercased.

		:returns: A dict with the table_name as key and the field names as value.
		:rtype: dict
		"""
		tables = {}
		logger.trace("Current tables:")
		for i in self.getSet(
			session,
			f"SELECT table_name from information_schema.tables WHERE table_type != 'VIEW' AND table_schema = '{self._database}';",
		):
			for table_name in i.values():
				table_name = table_name.upper()
				logger.trace(" [ %s ]", table_name)
				fields = [
					j["Field"]
					for j in self.getSet(session, f"SHOW COLUMNS FROM `{table_name}`")
				]
				tables[table_name] = fields
				logger.trace("Fields in %s: %s", table_name, fields)

		return tables

	def getTableCreationOptions(self, table: str) -> str:
		if table in ("SOFTWARE", "SOFTWARE_CONFIG") or table.startswith(
			("HARDWARE_DEVICE_", "HARDWARE_CONFIG_")
		):
			return "ENGINE=MyISAM DEFAULT CHARSET utf8 COLLATE utf8_general_ci;"
		return "ENGINE=InnoDB DEFAULT CHARSET utf8 COLLATE utf8_general_ci"


class MySQLBackend(SQLBackend):
	"""Backend holding information in MySQL form."""

	def __init__(self, **kwargs) -> None:
		self._name = "mysql"

		SQLBackend.__init__(self, **kwargs)

		self._sql = MySQL(**kwargs)

		logger.debug("MySQLBackend created: %s", self)

	def _createTableHost(self) -> None:
		logger.debug("Creating table HOST")
		# MySQL uses some defaults for a row that specifies TIMESTAMP as
		# type without giving DEFAULT or ON UPDATE constraints that
		# result in hosts always having the current time in created and
		# lastSeen. We do not want this behaviour, so we need to specify
		# our DEFAULT.
		# More information about the defaults can be found in the MySQL
		# handbook:
		#   https://dev.mysql.com/doc/refman/5.1/de/timestamp-4-1.html
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
			) {self._sql.getTableCreationOptions("HOST")};"""
		logger.debug(table)
		with self._sql.session() as session:
			self._sql.execute(session, table)
			self._sql.execute(
				session, "CREATE INDEX `index_host_type` on `HOST` (`type`);"
			)

	def _createTableSoftwareConfig(self) -> None:
		logger.debug("Creating table SOFTWARE_CONFIG")
		# We want the primary key config_id to be of a bigint as
		# regular int has been proven to be too small on some
		# installations.
		table = f"""CREATE TABLE `SOFTWARE_CONFIG` (
				`config_id` bigint NOT NULL {self._sql.AUTOINCREMENT},
				`clientId` varchar(255) NOT NULL,
				`name` varchar(100) NOT NULL,
				`version` varchar(100) NOT NULL,
				`subVersion` varchar(100) NOT NULL,
				`language` varchar(10) NOT NULL,
				`architecture` varchar(3) NOT NULL,
				`uninstallString` varchar(200),
				`binaryName` varchar(100),
				`firstseen` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
				`lastseen` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
				`state` TINYINT NOT NULL,
				`usageFrequency` integer NOT NULL DEFAULT -1,
				`lastUsed` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
				`licenseKey` VARCHAR(1024),
				PRIMARY KEY (`config_id`)
			) {self._sql.getTableCreationOptions("SOFTWARE_CONFIG")};
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
				"CREATE INDEX `index_software_config_nvsla` on `SOFTWARE_CONFIG` (`name`, `version`, `subVersion`, `language`, `architecture`);",
			)

	# Overwriting product_getObjects to use JOIN for speedup
	def product_getObjects(self, attributes: List = None, **filter) -> list[Product]:  # pylint: disable=redefined-builtin,dangerous-default-value
		attributes = attributes or []
		ConfigDataBackend.product_getObjects(self, attributes=[], **filter)
		logger.info("Getting products, filter: %s", filter)

		(attributes, filter) = self._adjustAttributes(Product, attributes, filter)
		readWindowsSoftwareIDs = not attributes or "windowsSoftwareIds" in attributes

		select = ",".join(f"p.`{attribute}`" for attribute in attributes) or "p.*"
		where = self._filterToSql(filter, table="p") or "1=1"
		query = f"""
			SELECT
				{select},
				GROUP_CONCAT(wp.windowsSoftwareId SEPARATOR "\n") AS windowsSoftwareIds
			FROM
				PRODUCT AS p
			LEFT JOIN
				WINDOWS_SOFTWARE_ID_TO_PRODUCT AS wp ON p.productId = wp.productId
			WHERE
				{where}
			GROUP BY
				p.productId,
				p.productVersion,
				p.packageVersion
		"""

		products = []
		with self._sql.session() as session:
			for product in self._sql.getSet(session, query):
				product["productClassIds"] = []
				if readWindowsSoftwareIDs and product["windowsSoftwareIds"]:
					product["windowsSoftwareIds"] = product["windowsSoftwareIds"].split(
						"\n"
					)
				else:
					product["windowsSoftwareIds"] = []

				if not attributes or "productClassIds" in attributes:
					pass

				self._adjustResult(Product, product)
				products.append(Product.fromHash(product))
		return products

	# Overwriting productProperty_getObjects to use JOIN for speedup
	def productProperty_getObjects(
		self, attributes: List = None, **filter
	) -> list[ProductProperty]:  # pylint: disable=redefined-builtin
		attributes = attributes or []
		ConfigDataBackend.productProperty_getObjects(self, attributes=[], **filter)
		logger.info("Getting product properties, filter: %s", filter)

		(attributes, filter) = self._adjustAttributes(
			ProductProperty, attributes, filter
		)
		readValues = (
			not attributes
			or "possibleValues" in attributes
			or "defaultValues" in attributes
		)

		select = ",".join(f"pp.`{attribute}`" for attribute in attributes) or "pp.*"
		where = self._filterToSql(filter, table="pp") or "1=1"
		query = f"""
			SELECT
				{select},
				-- JSON_ARRAYAGG(ppv.value) AS possibleValues,
				-- JSON_ARRAYAGG(IF(ppv.isDefault, ppv.value, NULL)) AS defaultValues,
				GROUP_CONCAT(ppv.value SEPARATOR "\n") AS possibleValues,
				GROUP_CONCAT(IF(ppv.isDefault, ppv.value, NULL) SEPARATOR "\n") AS defaultValues
			FROM
				PRODUCT_PROPERTY AS pp
			LEFT JOIN
				PRODUCT_PROPERTY_VALUE AS ppv ON
					ppv.productId = pp.productId AND
					ppv.productVersion = pp.productVersion AND
					ppv.packageVersion = pp.packageVersion AND
					ppv.propertyId = pp.propertyId
			WHERE
				{where}
			GROUP BY
				pp.productId,
				pp.productVersion,
				pp.packageVersion,
				pp.propertyId
		"""
		productProperties = []
		with self._sql.session() as session:
			for productProperty in self._sql.getSet(session, query):
				if readValues and productProperty["possibleValues"]:
					productProperty["possibleValues"] = productProperty[
						"possibleValues"
					].split("\n")
				else:
					productProperty["possibleValues"] = []

				if readValues and productProperty["defaultValues"]:
					productProperty["defaultValues"] = productProperty[
						"defaultValues"
					].split("\n")
				else:
					productProperty["defaultValues"] = []
				productProperties.append(ProductProperty.fromHash(productProperty))
		return productProperties

	def auditSoftwareOnClient_setObsolete(self, clientId: str) -> None:
		if not clientId:
			return
		clientId = forceHostIdList(clientId)
		with self._sql.session() as session:
			logger.info("Deleting auditSoftware of clients %s", clientId)
			session.execute(
				"DELETE FROM SOFTWARE_CONFIG WHERE clientId IN :clientIds",
				params={"clientIds": clientId},
			)

	def auditHardwareOnHost_setObsolete(self, hostId: str) -> None:
		if not hostId:
			return
		hostId = forceHostIdList(hostId)
		with self._sql.session() as session:
			for hw_class in self._auditHardwareConfig:
				session.execute(
					f"DELETE FROM HARDWARE_CONFIG_{hw_class} WHERE hostId IN :hostIds",
					params={"hostIds": hostId},
				)


class MySQLBackendObjectModificationTracker(SQLBackendObjectModificationTracker):
	def __init__(self, **kwargs) -> None:
		SQLBackendObjectModificationTracker.__init__(self, **kwargs)
		self._sql = MySQL(**kwargs)
		self._createTables()
