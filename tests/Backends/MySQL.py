# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
MySQL backend test helpers
"""

from contextlib import contextmanager

import pytest

from OPSI.Backend.MySQL import (
	MySQL,
	MySQLBackend,
	MySQLBackendObjectModificationTracker,
)
from OPSI.Util.Task.UpdateBackend.MySQL import disableForeignKeyChecks

try:
	from .config import MySQLconfiguration
except ImportError:
	MySQLconfiguration = None

UNKNOWN_TABLE_ERROR_CODE = 1051


@contextmanager
def getMySQLBackend(**backendOptions):
	if not MySQLconfiguration:
		pytest.skip("no MySQL backend configuration given.")

	optionsForBackend = MySQLconfiguration
	optionsForBackend.update(backendOptions)

	with cleanDatabase(MySQL(**optionsForBackend)):
		yield MySQLBackend(**optionsForBackend)


@contextmanager
def getMySQLModificationTracker():
	if not MySQLconfiguration:
		pytest.skip("no MySQL backend configuration given.")

	yield MySQLBackendObjectModificationTracker(**MySQLconfiguration)


@contextmanager
def cleanDatabase(database):
	def dropAllTables(database):
		with database.session() as session:
			with disableForeignKeyChecks(database, session):
				# Drop database
				error_count = 0
				success = False
				while not success:
					success = True
					for table_name in getTableNames(database, session):
						drop_command = f"DROP TABLE `{table_name}`"
						try:
							database.execute(session, drop_command)
						except Exception:
							success = False
							error_count += 1
							if error_count > 10:
								raise

	dropAllTables(database)
	try:
		yield database
	finally:
		dropAllTables(database)


def getTableNames(database, session):
	return set(tuple(i.values())[0] for i in database.getSet(session, "SHOW TABLES"))
