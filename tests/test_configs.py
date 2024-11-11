# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing configuration objects on a backend.
"""

from OPSI.Object import BoolConfig, ConfigState, OpsiClient, UnicodeConfig

from .test_hosts import getClients, getDepotServers


def getConfigs(depotServerId=None):
	config1 = UnicodeConfig(
		id="opsi-linux-bootimage.cmdline.reboot",
		description=("Some string üöä?").encode("latin-1"),
		possibleValues=["w", "c", "b", "h", "b,c"],
		defaultValues=["b,c"],
	)

	config2 = BoolConfig(
		id="opsi-linux-bootimage.cmdline.bool", description="Bool?", defaultValues="on"
	)

	config3 = UnicodeConfig(
		id="some.products",
		description="Install this products",
		possibleValues=["product1", "product2", "product3", "product4"],
		defaultValues=["product1", "product3"],
	)

	config4 = UnicodeConfig(
		id="clientconfig.depot.id",
		description="Depotserver to use",
		possibleValues=[],
		defaultValues=[depotServerId or "depot3000.domain.invalid"],
	)

	config5 = UnicodeConfig(
		id="some.other.products",
		description="Some other product ids",
		possibleValues=["product3", "product4", "product5"],
		defaultValues=["product3"],
	)

	config6 = UnicodeConfig(
		id="%username%",
		description="username",
		possibleValues=None,
		defaultValues=["opsi"],
	)

	return (config1, config2, config3, config4, config5, config6)


def getConfigStates(configs, clients, depotserver):
	config1, config2, _, config4, _, config6 = configs[:6]
	client1, client2, _, _, client5, client6, client7 = clients[:7]
	depotserver2 = depotserver[1]

	configState1 = ConfigState(
		configId=config1.getId(), objectId=client1.getId(), values=["w"]
	)

	configState2 = ConfigState(
		configId=config2.getId(), objectId=client1.getId(), values=[False]
	)

	configState3 = ConfigState(
		configId=config2.getId(), objectId=client2.getId(), values=[False]
	)

	configState4 = ConfigState(
		configId=config6.getId(),
		objectId=client2.getId(),
		values=["-------- test --------\n4: %4\n1: %1\n2: %2\n5: %5"],
	)

	configState5 = ConfigState(
		configId=config4.getId(), objectId=client5.getId(), values=depotserver2.id
	)

	configState6 = ConfigState(
		configId=config4.getId(), objectId=client6.getId(), values=depotserver2.id
	)

	configState7 = ConfigState(
		configId=config4.getId(), objectId=client7.getId(), values=depotserver2.id
	)

	return (
		configState1,
		configState2,
		configState3,
		configState4,
		configState5,
		configState6,
		configState7,
	)


def testConfigMethods(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	configs = extendedConfigDataBackend.config_getObjects()
	assert len(configs) == len(configsOrig)
	ids = []
	for config in configs:
		ids.append(config.id)
	for config in configsOrig:
		assert config.id in ids

	for config in configs:
		for c in configsOrig:
			if config.id == c.id:
				assert config == c

	config2 = configsOrig[1]
	configs = extendedConfigDataBackend.config_getObjects(
		defaultValues=config2.defaultValues
	)
	assert len(configs) == 1
	assert configs[0].getId() == config2.getId()

	configs = extendedConfigDataBackend.config_getObjects(possibleValues=[])
	assert len(configs) == len(configs)

	config1 = configsOrig[0]
	configs = extendedConfigDataBackend.config_getObjects(
		possibleValues=config1.possibleValues, defaultValues=config1.defaultValues
	)
	assert len(configs) == 1
	assert configs[0].getId() == config1.getId()

	config3 = configsOrig[2]
	config5 = configsOrig[4]
	configs = extendedConfigDataBackend.config_getObjects(
		possibleValues=config5.possibleValues, defaultValues=config5.defaultValues
	)
	assert len(configs) == 2
	for config in configs:
		assert config.getId() in (config3.id, config5.id)

	multiValueConfigNames = []
	for config in configsOrig:
		if config.getMultiValue():
			multiValueConfigNames.append(config.id)
	configs = extendedConfigDataBackend.config_getObjects(
		attributes=[], multiValue=True
	)
	assert len(configs) == len(multiValueConfigNames)
	for config in configs:
		assert config.id in multiValueConfigNames

	extendedConfigDataBackend.config_deleteObjects(config1)
	configs = extendedConfigDataBackend.config_getObjects()
	assert len(configs) == len(configsOrig) - 1

	extendedConfigDataBackend.config_createObjects(config1)

	config3.setDescription("Updated")
	config3.setPossibleValues(["1", "2", "3"])
	config3.setDefaultValues(["1", "2"])
	extendedConfigDataBackend.config_updateObject(config3)

	configs = extendedConfigDataBackend.config_getObjects(description="Updated")
	assert len(configs) == 1
	assert len(configs[0].getPossibleValues()) == 3

	for i in ["1", "2", "3"]:
		assert i in configs[0].getPossibleValues()

	assert len(configs[0].getDefaultValues()) == 2
	for i in ["1", "2"]:
		assert i in configs[0].getDefaultValues()


def test_getConfigFromBackend(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	configs = extendedConfigDataBackend.config_getObjects()
	assert len(configs) == len(configsOrig)


def test_verifyConfigs(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	configs = extendedConfigDataBackend.config_getObjects()
	assert configs

	ids = [config.id for config in configs]
	for config in configsOrig:
		assert config.id in ids

	for config in configs:
		for c in configsOrig:
			if config.id == c.id:
				assert config == c


def test_getConfigByDefaultValues(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	config2 = configsOrig[1]

	configs = extendedConfigDataBackend.config_getObjects(
		defaultValues=config2.defaultValues
	)
	assert len(configs) == 1
	assert configs[0].getId() == config2.getId()


def test_getConfigByPossibleValues(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	configs = extendedConfigDataBackend.config_getObjects(possibleValues=[])
	assert len(configs) == len(configsOrig)

	config1 = configsOrig[0]
	configs = extendedConfigDataBackend.config_getObjects(
		possibleValues=config1.possibleValues, defaultValues=config1.defaultValues
	)
	assert len(configs) == 1
	assert configs[0].getId() == config1.getId()

	config5 = configsOrig[4]
	configs = extendedConfigDataBackend.config_getObjects(
		possibleValues=config5.possibleValues, defaultValues=config5.defaultValues
	)
	assert len(configs) == 2

	config3 = configsOrig[2]
	for config in configs:
		assert config.getId(), config3.id in config5.id


def test_getMultiValueConfigs(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	multiValueConfigNames = [
		config.id for config in configsOrig if config.getMultiValue()
	]
	assert multiValueConfigNames

	configs = extendedConfigDataBackend.config_getObjects(
		attributes=[], multiValue=True
	)
	assert len(configs) == len(multiValueConfigNames)
	for config in configs:
		assert config.id in multiValueConfigNames


def test_deleteConfigFromBackend(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	config1 = configsOrig[0]
	extendedConfigDataBackend.config_deleteObjects(config1)
	configs = extendedConfigDataBackend.config_getObjects()
	assert len(configs) == len(configsOrig) - 1


def test_updateConfig(extendedConfigDataBackend):
	configsOrig = getConfigs()
	extendedConfigDataBackend.config_createObjects(configsOrig)

	config3 = configsOrig[2]

	config3.setDescription("Updated")
	config3.setPossibleValues(["1", "2", "3"])
	config3.setDefaultValues(["1", "2"])
	extendedConfigDataBackend.config_updateObject(config3)

	configs = extendedConfigDataBackend.config_getObjects(description="Updated")
	assert len(configs) == 1
	config = configs[0]
	assert len(config.getPossibleValues()) == 3
	for i in ["1", "2", "3"]:
		assert i in config.getPossibleValues()
	assert len(config.getDefaultValues()) == 2
	for i in ["1", "2"]:
		assert i in config.getDefaultValues()


def testConfigStateMethods(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	configStates = extendedConfigDataBackend.configState_getObjects()
	assert len(configStates) == len(configStatesOrig)

	client1 = clients[0]
	client1ConfigStates = []
	for configState in configStatesOrig:
		if configState.getObjectId() == client1.getId():
			client1ConfigStates.append(configState)

	configStates = extendedConfigDataBackend.configState_getObjects(
		attributes=[], objectId=client1.getId()
	)
	assert len(configStates) == len(client1ConfigStates)
	for configState in configStates:
		assert configState.objectId == client1.getId()

	configState2 = configStatesOrig[1]
	extendedConfigDataBackend.configState_deleteObjects(configState2)
	configStates = extendedConfigDataBackend.configState_getObjects()
	assert len(configStates) == len(configStatesOrig) - 1
	for configState in configStates:
		assert not (
			configState.objectId == configState2.objectId
			and configState.configId == configState2.configId
		)

	configState3 = configStatesOrig[2]
	configState3.setValues([True])
	extendedConfigDataBackend.configState_updateObject(configState3)
	configStates = extendedConfigDataBackend.configState_getObjects(
		objectId=configState3.getObjectId(), configId=configState3.getConfigId()
	)
	assert len(configStates) == 1
	assert configStates[0].getValues() == [True]

	configState4 = configStatesOrig[3]
	configStates = extendedConfigDataBackend.configState_getObjects(
		objectId=configState4.getObjectId(), configId=configState4.getConfigId()
	)
	assert len(configStates) == 1
	assert configStates[0].getValues()[0] == configState4.getValues()[0]


def test_getConfigStatesFromBackend(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	configStates = extendedConfigDataBackend.configState_getObjects()
	assert configStates

	for state in configStatesOrig:
		assert state in configStates


def test_getConfigStateByClientID(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	client1 = clients[0]
	client1ConfigStates = [
		configState
		for configState in configStatesOrig
		if configState.getObjectId() == client1.getId()
	]

	configStates = extendedConfigDataBackend.configState_getObjects(
		attributes=[], objectId=client1.getId()
	)
	assert configStates
	assert len(configStates) == len(client1ConfigStates)
	for configState in configStates:
		assert configState.objectId == client1.getId()


def test_deleteConfigStateFromBackend(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	configState2 = configStatesOrig[1]

	extendedConfigDataBackend.configState_deleteObjects(configState2)
	configStates = extendedConfigDataBackend.configState_getObjects()
	assert len(configStates) == len(configStatesOrig) - 1
	assert configState2 not in configStates


def test_updateConfigState(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	configState3 = configStatesOrig[2]
	configState3.setValues([True])
	extendedConfigDataBackend.configState_updateObject(configState3)
	configStates = extendedConfigDataBackend.configState_getObjects(
		objectId=configState3.getObjectId(), configId=configState3.getConfigId()
	)
	assert len(configStates) == 1
	assert configStates[0].getValues() == [True]


def test_selectConfigStateFromBackend(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	configState4 = configStatesOrig[3]

	configStates = extendedConfigDataBackend.configState_getObjects(
		objectId=configState4.getObjectId(), configId=configState4.getConfigId()
	)
	assert len(configStates) == 1
	assert configStates[0].getValues()[0] == configState4.getValues()[0]


def testGettingConfigIdents(extendedConfigDataBackend):
	depots = getDepotServers()
	origConfigs = getConfigs(depots[0].id)

	selfIdents = [config.getIdent(returnType="dict") for config in origConfigs]

	for config in origConfigs:
		config.setDefaults()
	extendedConfigDataBackend.config_createObjects(origConfigs)

	ids = extendedConfigDataBackend.config_getIdents()
	assert len(ids) == len(selfIdents)

	for ident in ids:
		assert any(ident == selfIdent["id"] for selfIdent in selfIdents), (
			"'%s' not in '%s'" % (ident, selfIdents)
		)


def testGetConfigStateIdents(extendedConfigDataBackend):
	configs = getConfigs()
	clients = getClients()
	depots = getDepotServers()
	configStatesOrig = getConfigStates(configs, clients, depots)

	extendedConfigDataBackend.host_createObjects(clients)
	extendedConfigDataBackend.host_createObjects(depots)
	extendedConfigDataBackend.config_createObjects(configs)
	extendedConfigDataBackend.configState_createObjects(configStatesOrig)

	selfIdents = [
		configState.getIdent(returnType="dict") for configState in configStatesOrig
	]

	ids = extendedConfigDataBackend.configState_getIdents()
	assert len(ids) == len(selfIdents)

	for ident in ids:
		i = ident.split(";")

		assert any(
			((i[0] == selfIdent["configId"]) and (i[1] == selfIdent["objectId"]))
			for selfIdent in selfIdents
		), "'%s' not in '%s'" % (ident, selfIdents)


def testConfigStateGetObjectsIncludesDefaultValues(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	config = UnicodeConfig(
		id="democonfig",
		editable=False,
		multiValue=False,
		possibleValues=[0, 5],
		defaultValues=[5],
	)
	backend.config_insertObject(config)

	client = OpsiClient(id="mytest.client.id")
	backend.host_insertObject(client)

	csOrig = ConfigState(config.id, client.id, [0])
	backend.configState_insertObject(csOrig)

	configStates = backend.configState_getObjects()
	assert len(configStates) == 1

	cs = configStates[0]
	assert cs.objectId == client.id
	assert cs.configId == config.id
	assert cs.values == csOrig.values
	assert cs.values == [0]
