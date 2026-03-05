# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing the modification tracking.

Based on work of Christian Kampka.
"""

import pytest

from opsi_legacy.Backend.Backend import ModificationTrackingBackend
from opsi_legacy.Object import OpsiClient

from .Backends.MySQL import getMySQLBackend, getMySQLModificationTracker
from .Backends.SQLite import getSQLiteBackend, getSQLiteModificationTracker


@pytest.fixture(
	params=[
		(getSQLiteBackend, getSQLiteModificationTracker),
		(getMySQLBackend, getMySQLModificationTracker),
	],
	ids=["sqlite", "mysql"],
)
def backendAndTracker(request):
	backendFunc, trackerFunc = request.param
	with backendFunc() as basebackend:
		basebackend.backend_createBase()

		backend = ModificationTrackingBackend(basebackend)

		with trackerFunc() as tracker:
			backend.addBackendChangeListener(tracker)

			yield backend, tracker

			# When reusing a database there may be leftover modifications!
			tracker.clearModifications()

		backend.backend_deleteBase()


def testTrackingOfInsertObject(backendAndTracker):
	backend, tracker = backendAndTracker

	host = OpsiClient(id="client1.test.invalid")
	backend.host_insertObject(host)

	modifications = tracker.getModifications()
	assert 1 == len(modifications)
	mod = modifications[0]
	assert mod["objectClass"] == host.__class__.__name__
	assert mod["command"] == "insert"
	assert mod["ident"] == host.getIdent()


def testTrackingOfUpdatingObject(backendAndTracker):
	backend, tracker = backendAndTracker

	host = OpsiClient(id="client1.test.invalid")

	backend.host_insertObject(host)
	tracker.clearModifications()
	backend.host_updateObject(host)

	modifications = tracker.getModifications()
	assert 1 == len(modifications)
	mod = modifications[0]
	assert mod["objectClass"] == host.__class__.__name__
	assert mod["command"] == "update"
	assert mod["ident"] == host.getIdent()


@pytest.mark.requires_license_file
def testTrackingOfDeletingObject(backendAndTracker):
	backend, tracker = backendAndTracker

	host = OpsiClient(id="client1.test.invalid")

	backend.host_insertObject(host)
	tracker.clearModifications()
	backend.host_deleteObjects(host)

	modifications = tracker.getModifications()

	assert 1 == len(modifications)
	modification = modifications[0]

	assert modification["objectClass"] == host.__class__.__name__
	assert modification["command"] == "delete"
	assert modification["ident"] == host.getIdent()
