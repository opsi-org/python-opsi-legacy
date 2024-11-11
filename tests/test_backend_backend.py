# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing basic backend functionality.
"""

import os.path

import pytest

from OPSI.Backend.Backend import Backend, ExtendedBackend, temporaryBackendOptions
from OPSI.Exceptions import BackendMissingDataError
from OPSI.Object import BoolConfig, OpsiClient, UnicodeConfig
from OPSI.Util import BlowfishError, blowfishDecrypt, generateOpsiHostKey, randomString

from .test_hosts import getConfigServer


def testGettingBackendInfoWithoutBackend():
	backend = ExtendedBackend(None)
	backend.backend_info()


def testSettingAndGettingUserCredentials(fakeCredentialsBackend):
	backend = fakeCredentialsBackend

	with pytest.raises(BackendMissingDataError):
		backend.user_getCredentials("unknown")

	backend.user_setCredentials(username="hans", password="blablabla")

	credentials = backend.user_getCredentials(username="hans")
	assert "blablabla" == credentials["password"]


def testOverWritingOldCredentials(fakeCredentialsBackend):
	backend = fakeCredentialsBackend

	backend.user_setCredentials(username="hans", password="bla")
	backend.user_setCredentials(username="hans", password="itworks")

	credentials = backend.user_getCredentials(username="hans")
	assert "itworks" == credentials["password"]


@pytest.mark.parametrize("number", [128])
def testWorkingWithManyCredentials(fakeCredentialsBackend, number):
	backend = fakeCredentialsBackend

	for _ in range(number):
		backend.user_setCredentials(
			username=randomString(12), password=randomString(12)
		)

	backend.user_setCredentials(username="hans", password="bla")

	credentials = backend.user_getCredentials(username="hans")
	assert "bla" == credentials["password"]


def testSettingUserCredentialsWithoutDepot(fakeCredentialsBackend):
	backend = fakeCredentialsBackend
	backend.host_deleteObjects(backend.host_getObjects())

	try:
		backend.user_setCredentials("hans", "")
		assert False, "We expected an exception to be risen!"
	except BlowfishError:  # File backend
		pass
	except BackendMissingDataError:  # SQL based backend
		pass


def testGettingPcpatchCredentials(fakeCredentialsBackend):
	"""
	Test reading and decrypting the pcpatch password with per-client encryption.

	This is essentially what is done in the opsi-linux-bootimage.
	"""
	backend = fakeCredentialsBackend

	backend.user_setCredentials(username="pcpatch", password="somepassword")

	host = OpsiClient("someclient.opsi.test", opsiHostKey=generateOpsiHostKey())
	backend.host_insertObject(host)

	creds = backend.user_getCredentials("pcpatch", host.id)

	password = blowfishDecrypt(host.opsiHostKey, creds["password"])

	assert password == "somepassword"


@pytest.fixture
def fakeCredentialsBackend(configDataBackend, tempDir):
	backend = configDataBackend
	backend.host_insertObject(getConfigServer())  # Required for file backend.

	credFile = os.path.join(tempDir, "credentials")
	with open(credFile, "w"):
		pass

	originalFile = backend._opsiPasswdFile
	backend._opsiPasswdFile = credFile
	try:
		yield backend
	finally:
		backend._opsiPasswdFile = originalFile


def testBackend_info(configDataBackend):
	info = configDataBackend.backend_info()

	assert "opsiVersion" in info
	assert "modules" in info
	assert "realmodules" in info


def testBackendCanBeUsedAsContextManager():
	with Backend() as backend:
		assert backend.backend_info()


@pytest.mark.parametrize(
	"option",
	[
		"addProductOnClientDefaults",
		"addProductPropertyStateDefaults",
		"addConfigStateDefaults",
		"deleteConfigStateIfDefault",
		"returnObjectsOnUpdateAndCreate",
		"addDependentProductOnClients",
		"processProductOnClientSequence",
	],
)
def testSettingTemporaryBackendOptions(extendedConfigDataBackend, option):
	optionDefaults = {
		"addProductOnClientDefaults": False,
		"addProductPropertyStateDefaults": False,
		"addConfigStateDefaults": False,
		"deleteConfigStateIfDefault": False,
		"returnObjectsOnUpdateAndCreate": False,
		"addDependentProductOnClients": False,
		"processProductOnClientSequence": False,
	}

	tempOptions = {option: True}

	with temporaryBackendOptions(extendedConfigDataBackend, **tempOptions):
		currentOptions = extendedConfigDataBackend.backend_getOptions()
		assert currentOptions
		for key, _value in optionDefaults.items():
			if key == option:
				assert currentOptions[key] is True
				continue

			assert currentOptions[key] is False

	currentOptions = extendedConfigDataBackend.backend_getOptions()
	print("options after leaving context: %s" % currentOptions)

	for key, defaultValue in optionDefaults.items():
		# if key == 'additionalReferentialIntegrityChecks':
		print("Checking key %s (%s)" % (key, currentOptions[key]))
		assert currentOptions[key] == defaultValue


def testSettingMultipleTemporaryBackendOptions(extendedConfigDataBackend):
	tempOptions = {
		"addProductOnClientDefaults": True,
		"addProductPropertyStateDefaults": True,
		"addConfigStateDefaults": True,
	}

	preOptions = extendedConfigDataBackend.backend_getOptions()
	assert preOptions
	for key, value in preOptions.items():
		try:
			assert value != tempOptions[key]
		except KeyError:
			continue

	# this is the same as:
	# with temporaryBackendOptions(extendedConfigDataBackend,
	# addProductOnClientDefaults=True,
	# addProductPropertyStateDefaults=True,
	# addConfigStateDefaults=True):
	with temporaryBackendOptions(extendedConfigDataBackend, **tempOptions):
		currentOptions = extendedConfigDataBackend.backend_getOptions()
		assert currentOptions

		testedOptions = set()
		for key, value in currentOptions.items():
			try:
				assert value == tempOptions[key]
				testedOptions.add(key)
			except KeyError:
				continue

		assert set(tempOptions.keys()) == testedOptions

	postContextOptions = extendedConfigDataBackend.backend_getOptions()
	assert postContextOptions
	for key, value in postContextOptions.items():
		assert preOptions[key] == value


def testConfigStateCheckWorksWithInsertedDict(extendedConfigDataBackend):
	backend = extendedConfigDataBackend
	client = OpsiClient(id="client.test.invalid")
	backend.host_insertObject(client)
	config = BoolConfig("license-managment.use")
	backend.config_insertObject(config)
	configState = {
		"configId": config.id,
		"objectId": client.id,
		"values": "true",
		"type": "ConfigState",
	}
	backend.configState_insertObject(configState)


def testConfigStateCheckWorksWithUpdatedDict(extendedConfigDataBackend):
	backend = extendedConfigDataBackend
	client = OpsiClient("client.test.invalid")
	backend.host_insertObject(client)
	config = BoolConfig("license-managment.use")
	backend.config_insertObject(config)

	configState = {
		"configId": config.id,
		"objectId": client.id,
		"values": True,
		"type": "ConfigState",
	}
	backend.configState_insertObject(configState)

	configState["values"] = False
	backend.configState_updateObject(configState)


@pytest.mark.parametrize("configValue", ["nofqdn", None, "non.existing.depot"])
def testConfigStateCheckFailsOnInvalidDepotSettings(
	extendedConfigDataBackend, configValue
):
	backend = extendedConfigDataBackend
	client = OpsiClient(id="client.test.invalid")
	backend.host_insertObject(client)

	configServer = getConfigServer()
	backend.host_insertObject(configServer)

	config = UnicodeConfig(
		id="clientconfig.depot.id",
		description="ID of the opsi depot to use",
		possibleValues=[configServer.getId()],
		defaultValues=[configServer.getId()],
		editable=True,
		multiValue=False,
	)

	backend.config_insertObject(config)
	configState = {
		"configId": config.id,
		"objectId": client.id,
		"values": configValue,
		"type": "ConfigState",
	}
	with pytest.raises(ValueError):
		backend.configState_insertObject(configState)


@pytest.mark.parametrize("length", [32, 64, 128, 256])
def testNamesAndPasswordsCanBeVeryLong(fakeCredentialsBackend, length):
	backend = fakeCredentialsBackend
	backend.host_insertObject(getConfigServer())  # Required for file backend.

	user = randomString(length)
	password = randomString(length)

	backend.user_setCredentials(username=user, password=password)
	credentials = backend.user_getCredentials(username=user)
	assert password == credentials["password"]


@pytest.mark.parametrize(
	"user, password",
	[
		("user", randomString(32)),
		("user.domain", randomString(32)),
		("user.domain.tld", randomString(32)),
		("user.subdomain.domain.tld", randomString(32)),
		("user.subdomain.subdomain.domain.tld", randomString(32)),
		("user.subdomain1.subdomain2.anotherdomain.tld", randomString(32)),
	],
)
def testSettingUserCredentialsWithDomain(fakeCredentialsBackend, user, password):
	backend = fakeCredentialsBackend
	backend.host_insertObject(getConfigServer())  # Required for file backend.

	backend.user_setCredentials(username=user, password=password)
	credentials = backend.user_getCredentials(username=user)
	assert password == credentials["password"]
