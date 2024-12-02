# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the backend configuration.
"""

import os

import pytest

import OPSI.Util.Task.ConfigureBackend as backendConfigUtils
import OPSI.Util.Task.ConfigureBackend.ConfigurationData as confData
from OPSI.Object import UnicodeConfig
from OPSI.System.Posix import CommandNotFoundException

from .helpers import createTemporaryTestfile, mock
from .test_hosts import getConfigServer


@pytest.fixture
def exampleMySQLBackendConfig(dist_data_path):
	templateFile = os.path.join(dist_data_path, "backends", "mysql.conf")

	with createTemporaryTestfile(templateFile) as fileName:
		yield fileName


def testReadingMySQLConfigFile(exampleMySQLBackendConfig):
	defaultMySQLConfig = {
		"address": "127.0.0.1",
		"database": "opsi",
		"username": "opsi",
		"password": "opsi",
	}

	config = backendConfigUtils.getBackendConfiguration(exampleMySQLBackendConfig)

	assert config == defaultMySQLConfig


def testUpdatingTestConfigFile(exampleMySQLBackendConfig):
	fileName = exampleMySQLBackendConfig
	config = backendConfigUtils.getBackendConfiguration(fileName)

	assert "notYourCurrentPassword" != config["password"]
	config["password"] = "notYourCurrentPassword"
	backendConfigUtils.updateConfigFile(fileName, config)
	assert "notYourCurrentPassword" == config["password"]

	del config["address"]
	del config["database"]
	del config["password"]

	backendConfigUtils.updateConfigFile(fileName, config)

	config = backendConfigUtils.getBackendConfiguration(fileName)

	for key in ("address", "database", "password"):
		assert key not in config, f"{key} should not be in {config}"

	for key in ("username",):
		assert key in config, f"{key} should be in {config}"


def testReadingWindowsDomainFromSambaConfig(test_data_path):
	testConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	domain = confData.readWindowsDomainFromSambaConfig(testConfig)

	assert "WWWORK" == domain


@pytest.mark.parametrize(
	"configId",
	[
		"clientconfig.depot.dynamic",
		"clientconfig.depot.drive",
		"clientconfig.depot.protocol",
		"clientconfig.windows.domain",
		"opsi-linux-bootimage.append",
		"license-management.use",
		"software-on-demand.active",
		"software-on-demand.product-group-ids",
		"clientconfig.dhcpd.filename",
		pytest.param("software-on-demand.show-details", marks=pytest.mark.xfail),
		"opsiclientd.event_user_login.active",
		"opsiclientd.event_user_login.action_processor_command",
	],
)
def testConfigureBackendAddsMissingEntries(
	test_data_path, extendedConfigDataBackend, configId
):
	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	configIdents = set(extendedConfigDataBackend.config_getIdents(returnType="unicode"))

	assert configId in configIdents


def testAddingDynamicClientConfigDepotDrive(test_data_path, extendedConfigDataBackend):
	"""
	'dynamic' should be a possible value in 'clientconfig.depot.drive'.

	This makes sure that old configs are updated aswell.
	"""
	extendedConfigDataBackend.config_delete(id=["clientconfig.depot.drive"])

	oldConfig = UnicodeConfig(
		id="clientconfig.depot.drive",
		description="Drive letter for depot share",
		possibleValues=[
			"c:",
			"d:",
			"e:",
			"f:",
			"g:",
			"h:",
			"i:",
			"j:",
			"k:",
			"l:",
			"m:",
			"n:",
			"o:",
			"p:",
			"q:",
			"r:",
			"s:",
			"t:",
			"u:",
			"v:",
			"w:",
			"x:",
			"y:",
			"z:",
		],
		defaultValues=["p:"],
		editable=False,
		multiValue=False,
	)
	extendedConfigDataBackend.config_createObjects([oldConfig])

	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	config = extendedConfigDataBackend.config_getObjects(id="clientconfig.depot.drive")[
		0
	]
	assert "dynamic" in config.possibleValues


def testAddingDynamicClientConfigDepotDriveKeepsOldDefault(
	test_data_path, extendedConfigDataBackend
):
	"""
	Adding the new property should keep the old defaults.
	"""
	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	extendedConfigDataBackend.config_delete(id=["clientconfig.depot.drive"])
	oldConfig = UnicodeConfig(
		id="clientconfig.depot.drive",
		description="Drive letter for depot share",
		possibleValues=[
			"c:",
			"d:",
			"e:",
			"f:",
			"g:",
			"h:",
			"i:",
			"j:",
			"k:",
			"l:",
			"m:",
			"n:",
			"o:",
			"p:",
			"q:",
			"r:",
			"s:",
			"t:",
			"u:",
			"v:",
			"w:",
			"x:",
			"y:",
			"z:",
		],
		defaultValues=["n:"],
		editable=False,
		multiValue=False,
	)
	extendedConfigDataBackend.config_createObjects([oldConfig])

	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	config = extendedConfigDataBackend.config_getObjects(id="clientconfig.depot.drive")[
		0
	]
	assert ["n:"] == config.defaultValues


def testAddingWANConfigs(extendedConfigDataBackend):
	requiredConfigIdents = [
		"opsiclientd.event_gui_startup.active",
		"opsiclientd.event_gui_startup{user_logged_in}.active",
		"opsiclientd.event_net_connection.active",
		"opsiclientd.event_timer.active",
	]

	confData.createWANconfigs(extendedConfigDataBackend)
	identsInBackend = set(extendedConfigDataBackend.config_getIdents())

	for ident in requiredConfigIdents:
		assert ident in identsInBackend, f"Missing config id {ident}"


def testAddingInstallByShutdownConfig(extendedConfigDataBackend):
	requiredConfigIdents = [
		"clientconfig.install_by_shutdown.active",
	]

	confData.createInstallByShutdownConfig(extendedConfigDataBackend)
	identsInBackend = set(extendedConfigDataBackend.config_getIdents())

	for ident in requiredConfigIdents:
		assert ident in identsInBackend, f"Missing config id {ident}"


@pytest.mark.parametrize("useSamba", [True, False])
def testAddingClientconfigDepotUser(
	test_data_path, extendedConfigDataBackend, useSamba
):
	sambaTestConfig = "/none"
	if useSamba:
		sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")

	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	configs = extendedConfigDataBackend.config_getHashes(id="clientconfig.depot.user")
	assert len(configs) == 1
	config = configs[0]

	assert len(config["defaultValues"]) == 1
	defaultValues = config["defaultValues"][0]
	if useSamba:
		assert "WWWORK\\pcpatch" in defaultValues
	else:
		assert "pcpatch" in defaultValues


def testAddingConfigsBasedOnConfigServer(test_data_path, extendedConfigDataBackend):
	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	configServer = getConfigServer()
	configServer.ipAddress = "12.34.56.78"

	confData.initializeConfigs(
		backend=extendedConfigDataBackend,
		pathToSMBConf=sambaTestConfig,
		configServer=configServer,
	)

	configIdents = set(extendedConfigDataBackend.config_getIdents(returnType="unicode"))
	expectedConfigIDs = ["clientconfig.configserver.url", "clientconfig.depot.id"]

	for cId in expectedConfigIDs:
		assert cId in configIdents

	urlConfig = extendedConfigDataBackend.config_getObjects(
		id="clientconfig.configserver.url"
	)[0]
	assert 1 == len(urlConfig.defaultValues)
	value = urlConfig.defaultValues[0]
	assert value.endswith("/rpc")
	assert value.startswith("https://")
	assert configServer.id in value
	assert urlConfig.editable

	depotConfig = extendedConfigDataBackend.config_getObjects(
		id="clientconfig.depot.id"
	)[0]
	assert 1 == len(depotConfig.defaultValues)
	assert configServer.id == depotConfig.defaultValues[0]
	assert configServer.id == depotConfig.possibleValues[0]
	assert not depotConfig.multiValue
	assert depotConfig.editable


def testConfigsAreOnlyAddedOnce(test_data_path, extendedConfigDataBackend):
	sambaTestConfig = os.path.join(test_data_path, "util", "task", "smb.conf")
	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)

	configIdentsFirst = extendedConfigDataBackend.config_getIdents(returnType="unicode")
	configIdentsFirst.sort()

	confData.initializeConfigs(
		backend=extendedConfigDataBackend, pathToSMBConf=sambaTestConfig
	)
	configIdentsSecond = extendedConfigDataBackend.config_getIdents(
		returnType="unicode"
	)
	configIdentsSecond.sort()

	assert configIdentsFirst == configIdentsSecond
	assert len(configIdentsSecond) == len(set(configIdentsSecond))


def testReadingDomainFromUCR():
	with mock.patch(
		"OPSI.Util.Task.ConfigureBackend.ConfigurationData.Posix.which",
		lambda x: "/no/real/path/ucr",
	):
		with mock.patch(
			"OPSI.Util.Task.ConfigureBackend.ConfigurationData.Posix.execute",
			lambda x: ["sharpdressed"],
		):
			assert "SHARPDRESSED" == confData.readWindowsDomainFromUCR()


def testReadingDomainFromUCRReturnEmptyStringOnProblem():
	failingWhich = mock.Mock(side_effect=CommandNotFoundException("Whoops."))
	with mock.patch(
		"OPSI.Util.Task.ConfigureBackend.ConfigurationData.Posix.which", failingWhich
	):
		assert "" == confData.readWindowsDomainFromUCR()
