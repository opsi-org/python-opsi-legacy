#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for easy configuration of WAN clients.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/70_wan.conf``.

.. versionadded:: 4.0.6.3
"""

from __future__ import print_function

import pytest

from OPSI.Object import OpsiClient
from OPSI.Util.Task.ConfigureBackend.ConfigurationData import createWANconfigs


@pytest.fixture
def backendWithWANConfigs(backendManager):
	createWANconfigs(backendManager)
	yield backendManager


def clientHasWANEnabled(backend, clientId):
	configsToCheck = set(
		[
			"opsiclientd.event_gui_startup.active",
			"opsiclientd.event_gui_startup{user_logged_in}.active",
			"opsiclientd.event_net_connection.active",
			"opsiclientd.event_timer.active",
		]
	)

	for configState in backend.configState_getObjects(objectId=clientId):
		if configState.configId == "opsiclientd.event_gui_startup.active":
			if configState.values[0]:
				return False
			configsToCheck.remove("opsiclientd.event_gui_startup.active")
		elif (
			configState.configId
			== "opsiclientd.event_gui_startup{user_logged_in}.active"
		):
			if configState.values[0]:
				return False
			configsToCheck.remove(
				"opsiclientd.event_gui_startup{user_logged_in}.active"
			)
		elif configState.configId == "opsiclientd.event_net_connection.active":
			if not configState.values[0]:
				return False
			configsToCheck.remove("opsiclientd.event_net_connection.active")
		elif configState.configId == "opsiclientd.event_timer.active":
			if not configState.values[0]:
				return False
			configsToCheck.remove("opsiclientd.event_timer.active")

	if configsToCheck:
		print("The following configs were not set: {0}".format(configsToCheck))
		return False

	return True


def testEnablingSettingForOneHost(backendWithWANConfigs):
	backend = backendWithWANConfigs
	clientId = "testclient.test.invalid"
	backend.host_createObjects(OpsiClient(id=clientId))

	backend.changeWANConfig(True, clientId)
	assert clientHasWANEnabled(backend, clientId)

	backend.changeWANConfig(False, clientId)
	assert not clientHasWANEnabled(backend, clientId)


def testEnablingSettingForMultipleHosts(backendWithWANConfigs):
	backend = backendWithWANConfigs

	clientIds = ["testclient{0}.test.invalid".format(num) for num in range(10)]
	backend.host_createObjects([OpsiClient(id=clientId) for clientId in clientIds])

	backend.changeWANConfig(True, clientIds)

	for clientId in clientIds:
		assert clientHasWANEnabled(backend, clientId)


def testNotFailingOnEmptyList(backendWithWANConfigs):
	backendWithWANConfigs.changeWANConfig(True, [])


def testNotChangingUnreferencedClient(backendWithWANConfigs):
	backend = backendWithWANConfigs

	clientIds = ["testclient{0}.test.invalid".format(num) for num in range(10)]
	singleClient = "testclient99.test.invalid"
	backend.host_createObjects([OpsiClient(id=clientId) for clientId in clientIds])
	backend.host_createObjects([OpsiClient(id=singleClient)])

	backend.changeWANConfig(True, clientIds)
	backend.changeWANConfig(True, [])

	for clientId in clientIds:
		assert clientHasWANEnabled(backend, clientId)

	assert not clientHasWANEnabled(backend, singleClient)


@pytest.mark.parametrize(
	"value, expected",
	[
		("on", True),
		("1", True),
		("true", True),
		("off", False),
		("false", False),
		("0", False),
	],
)
def testUsingNonBooleanParameters(backendWithWANConfigs, value, expected):
	backend = backendWithWANConfigs

	client = OpsiClient(id="testclient101.test.invalid")
	backend.host_createObjects([client])

	backend.changeWANConfig(value, client.id)
	assert clientHasWANEnabled(backend, client.id) == expected
