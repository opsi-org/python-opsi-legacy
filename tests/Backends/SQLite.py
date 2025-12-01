# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

from contextlib import contextmanager

import pytest

try:
	from .config import SQLiteconfiguration
except ImportError:
	SQLiteconfiguration = {}


@contextmanager
def getSQLiteBackend(**backendOptions):
	sqliteModule = pytest.importorskip("OPSI.Backend.SQLite")
	SQLiteBackend = sqliteModule.SQLiteBackend

	# Defaults and settings from the old fixture.
	# defaultOptions = {
	# 	'processProductPriorities':            True,
	# 	'processProductDependencies':          True,
	# 	'addProductOnClientDefaults':          True,
	# 	'addProductPropertyStateDefaults':     True,
	# 	'addConfigStateDefaults':              True,
	# 	'deleteConfigStateIfDefault':          True,
	# 	'returnObjectsOnUpdateAndCreate':      False
	# }
	# licenseManagement = True

	optionsForBackend = SQLiteconfiguration
	optionsForBackend.update(backendOptions)

	yield SQLiteBackend(**optionsForBackend)


@contextmanager
def getSQLiteModificationTracker():
	sqliteModule = pytest.importorskip("OPSI.Backend.SQLite")
	trackerClass = sqliteModule.SQLiteObjectBackendModificationTracker

	yield trackerClass(database=":memory:")
