# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
SQLite backend.
"""

import os
import sqlite3
import threading
from typing import Any, Generator

# Disable sqlalchemy 2.0 deprecation warnings
import sqlalchemy.util.deprecations
from opsicommon.logging import get_logger

sqlalchemy.util.deprecations.SILENCE_UBER_WARNING = True

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.event import listen  # noqa: E402
from sqlalchemy.orm import scoped_session, sessionmaker  # noqa: E402

from OPSI.Backend.SQL import (  # noqa: E402
	SQL,
	SQLBackend,
	SQLBackendObjectModificationTracker,
)
from OPSI.Types import forceFilename  # noqa: E402

__all__ = ("SQLite", "SQLiteBackend", "SQLiteObjectBackendModificationTracker")


logger = get_logger("opsi.general")


class SQLite(SQL):
	"""Class handling basic SQLite functionality."""

	AUTOINCREMENT = ""
	ALTER_TABLE_CHANGE_SUPPORTED = False
	ESCAPED_BACKSLASH = "\\"
	ESCAPED_APOSTROPHE = "''"
	ESCAPED_ASTERISK = "**"
	_WRITE_LOCK = threading.Lock()

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)

		self._database = ":memory:"
		self._databaseCharset = "utf8"

		for option, value in kwargs.items():
			option = option.lower()
			if option == "database":
				self._database = forceFilename(value)
			elif option == "databasecharset":
				self._databaseCharset = str(value)

		try:
			self.init_connection()
		except (sqlite3.DatabaseError, sqlite3.OperationalError) as dbError:
			logger.error(
				"SQLite database '%s' is defective: %s, recreating",
				self._database,
				dbError,
			)
			self.delete_db()
			self.init_connection()
		except Exception as err:  # pylint: disable=broad-except
			logger.error("Problem connecting to SQLite database: %s, recreating", err)
			self.delete_db()
			self.init_connection()

	@staticmethod
	def on_engine_connect(conn, branch) -> None:  # pylint: disable=unused-argument
		# conn.execute('PRAGMA synchronous=OFF')
		# conn.execute('PRAGMA temp_store=MEMORY')
		# conn.execute('PRAGMA cache_size=5000')
		# conn.execute('PRAGMA encoding="UTF-8"')
		pass

	def init_connection(self) -> None:
		uri = f"sqlite:///{self._database}"
		logger.info("Connecting to %s", uri)

		self.engine = create_engine(uri, encoding=self._databaseCharset)
		self.engine._should_log_info = lambda: self.log_queries  # pylint: disable=protected-access

		listen(self.engine, "engine_connect", self.on_engine_connect)

		self.session_factory = sessionmaker(
			bind=self.engine, autocommit=False, autoflush=False
		)
		self.Session = scoped_session(self.session_factory)  # pylint: disable=invalid-name
		# self.Session = self.session_factory  # pylint: disable=invalid-name

		# Test connection
		with self.session() as session:
			self.getTables(session)
		logger.debug("SQLite connected: %s", self)

	def __repr__(self) -> str:
		return f"<{self.__class__.__name__}(database={self._database})>"

	def delete_db(self) -> None:
		self.disconnect()
		if os.path.exists(self._database):
			os.remove(self._database)

	def getTables(self, session: scoped_session) -> dict[str, Any]:
		"""
		Get what tables are present in the database.

		Table names will always be uppercased.

		:returns: A dict with the tablename as key and the field names as value.
		:rtype: dict
		"""
		tables = {}
		logger.trace("Current tables:")
		for i in self.getSet(
			session, 'SELECT name FROM sqlite_master WHERE type = "table";'
		):
			tableName = tuple(i.values())[0].upper()
			logger.trace(" [ %s ]", tableName)
			fields = [
				j["name"]
				for j in self.getSet(session, f"PRAGMA table_info(`{tableName}`);")
			]
			tables[tableName] = fields
			logger.trace("Fields in %s: %s", tableName, fields)

		return tables

	def getTableCreationOptions(self, table: Any) -> str:
		return ""


class SQLiteBackend(SQLBackend):
	"""Backend holding information in SQLite form."""

	def __init__(self, **kwargs) -> None:
		self._name = "sqlite"

		SQLBackend.__init__(self, **kwargs)

		self._sql = SQLite(**kwargs)

		logger.debug("SQLiteBackend created: %s", self)

	def _check_module(self, module: str) -> None:
		return

	def backend_createBase(self) -> None:
		try:
			return SQLBackend.backend_createBase(self)
		except sqlite3.DatabaseError as dbError:
			logger.error(
				"SQLite database %s is defective: %s, recreating", self._sql, dbError
			)
			self._sql.delete_db()
			self._sql.connect()
			return SQLBackend.backend_createBase(self)

	def _createAuditHardwareTables(self) -> str:  # pylint: disable=too-many-statements
		"""
		Creating tables for hardware audit data.

		The speciatly for SQLite is that an ALTER TABLE may not list
		multiple columns to alter but instead has to alter one column
		after another.
		"""
		with self._sql.session() as session:
			tables = self._sql.getTables(session)
			existingTables = set(tables.keys())

			def removeTrailingComma(query: str) -> str:
				if query.endswith(","):
					return query[:-1]

				return query

			def finishSQLQuery(tableExists: bool, tableName: str) -> str:
				if tableExists:
					return " ;\n"
				return f"\n) {self._sql.getTableCreationOptions(tableName)};\n"

			def getSQLStatements() -> Generator[str, None, None]:  # pylint: disable=too-many-branches,too-many-statements
				for hwClass, values in self._auditHardwareConfig.items():  # pylint: disable=too-many-nested-blocks
					logger.debug("Processing hardware class '%s'", hwClass)
					hardwareDeviceTableName = f"HARDWARE_DEVICE_{hwClass}"
					hardwareConfigTableName = f"HARDWARE_CONFIG_{hwClass}"

					hardwareDeviceTableExists = (
						hardwareDeviceTableName in existingTables
					)
					hardwareConfigTableExists = (
						hardwareConfigTableName in existingTables
					)

					if hardwareDeviceTableExists:
						hardwareDeviceTable = (
							f"ALTER TABLE `{hardwareDeviceTableName}`\n"
						)
					else:
						hardwareDeviceTable = (
							f"CREATE TABLE `{hardwareDeviceTableName}` (\n"
							f"`hardware_id` INTEGER NOT NULL {self._sql.AUTOINCREMENT},\n"
						)

					avoid_process_further_hw_dev = False
					hardwareDeviceValuesProcessed = 0
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
									yield f"{hardwareDeviceTable} ADD COLUMN `{value}` {valueInfo['Type']} NULL;"
									avoid_process_further_hw_dev = True
							else:
								hardwareDeviceTable += (
									f"`{value}` {valueInfo['Type']} NULL,\n"
								)
							hardwareDeviceValuesProcessed += 1

					if hardwareConfigTableExists:
						hardwareConfigTable = (
							f"ALTER TABLE `{hardwareConfigTableName}`\n"
						)
					else:
						hardwareConfigTable = (
							f"CREATE TABLE `{hardwareConfigTableName}` (\n"
							f"`config_id` INTEGER NOT NULL {self._sql.AUTOINCREMENT},\n"
							"`hostId` varchar(255) NOT NULL,\n"
							"`hardware_id` INTEGER NOT NULL,\n"
							"`firstseen` TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:01',\n"
							"`lastseen` TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:01',\n"
							"`state` TINYINT NOT NULL,\n"
						)

					avoid_process_further_hw_cnf = False
					hardwareConfigValuesProcessed = 0
					for value, valueInfo in values.items():
						logger.debug("  Processing value '%s'", value)
						if valueInfo["Scope"] == "i":
							if hardwareConfigTableExists:
								if value in tables[hardwareConfigTableName]:
									# Column exists => change
									if not self._sql.ALTER_TABLE_CHANGE_SUPPORTED:
										continue

									hardwareConfigTable += f"CHANGE `{value}` `{value}` {valueInfo['Type']} NULL,\n"
								else:
									# Column does not exist => add
									yield f"{hardwareConfigTable} ADD COLUMN `{value}` {valueInfo['Type']} NULL;"
									avoid_process_further_hw_cnf = True
							else:
								hardwareConfigTable += (
									f"`{value}` {valueInfo['Type']} NULL,\n"
								)
							hardwareConfigValuesProcessed += 1

					if avoid_process_further_hw_cnf or avoid_process_further_hw_dev:
						continue

					if not hardwareDeviceTableExists:
						hardwareDeviceTable += "PRIMARY KEY (`hardware_id`)\n"
					if not hardwareConfigTableExists:
						hardwareConfigTable += "PRIMARY KEY (`config_id`)\n"

					# Remove leading and trailing whitespace
					hardwareDeviceTable = hardwareDeviceTable.strip()
					hardwareConfigTable = hardwareConfigTable.strip()

					hardwareDeviceTable = removeTrailingComma(hardwareDeviceTable)
					hardwareConfigTable = removeTrailingComma(hardwareConfigTable)

					hardwareDeviceTable += finishSQLQuery(
						hardwareDeviceTableExists, hardwareDeviceTableName
					)
					hardwareConfigTable += finishSQLQuery(
						hardwareConfigTableExists, hardwareConfigTableName
					)

					if hardwareDeviceValuesProcessed or not hardwareDeviceTableExists:
						yield hardwareDeviceTable

					if hardwareConfigValuesProcessed or not hardwareConfigTableExists:
						yield hardwareConfigTable

			for statement in getSQLStatements():
				logger.trace("Processing statement %s", statement)
				self._sql.execute(session, statement)
				logger.trace("Done with statement.")


class SQLiteObjectBackendModificationTracker(SQLBackendObjectModificationTracker):
	def __init__(self, **kwargs) -> None:
		SQLBackendObjectModificationTracker.__init__(self, **kwargs)
		self._sql = SQLite(**kwargs)
		self._createTables()
