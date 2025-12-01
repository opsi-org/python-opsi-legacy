# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing the opsi SQLite backend.
"""

import pytest


def testInitialisationOfSQLiteBackendWithoutParametersDoesNotFail():
	sqlModule = pytest.importorskip("OPSI.Backend.SQLite")
	SQLiteBackend = sqlModule.SQLiteBackend

	backend = SQLiteBackend()
	backend.backend_createBase()
