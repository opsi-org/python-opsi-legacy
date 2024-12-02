# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the modification tracking.

Based on work of Christian Kampka.
"""

from OPSI.Backend.Backend import ModificationTrackingBackend
from OPSI.Object import OpsiClient

from .Backends.SQLite import getSQLiteBackend, getSQLiteModificationTracker
from .Backends.MySQL import getMySQLBackend, getMySQLModificationTracker

import pytest


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
