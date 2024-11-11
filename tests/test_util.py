# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing functionality of OPSI.Util.
"""
# pylint: disable=too-many-lines

import os
import os.path
import random
import re
from collections import defaultdict
from contextlib import contextmanager

import pytest

from OPSI.Object import ConfigState, LocalbootProduct, OpsiClient
from OPSI.Util import (
	BlowfishError,
	blowfishDecrypt,
	blowfishEncrypt,
	chunk,
	compareVersions,
	findFilesGenerator,
	formatFileSize,
	fromJson,
	generateOpsiHostKey,
	ipAddressInNetwork,
	isRegularExpressionPattern,
	md5sum,
	objectToBash,
	objectToBeautifiedText,
	objectToHtml,
	randomString,
	removeUnit,
	toJson,
)
from OPSI.Util.Config import getGlobalConfig

from .helpers import (
	workInTemporaryDirectory,
)


@pytest.mark.parametrize(
	"ipa, network, result",
	[
		("10.10.1.1", "10.10.0.0/16", True),
		("10.10.1.1", "10.10.0.0/23", True),
		("10.10.1.1", "10.10.0.0/24", False),
		("10.10.1.1", "10.10.0.0/25", False),
	],
)
def testNetworkWithSlashInNotation(ipa, network, result):
	assert ipAddressInNetwork(ipa, network) == result


def testIpAddressInNetworkWithEmptyNetworkMask():
	assert ipAddressInNetwork("10.10.1.1", "0.0.0.0/0")


def testIpAddressInNetworkWithFullNetmask():
	assert ipAddressInNetwork("10.10.1.1", "10.10.0.0/255.255.0.0")


def generateLocalbootProducts(amount):
	"""
	Generates `amount` random LocalbootProducts.

	:rtype: LocalbootProduct
	"""

	productVersions = ("1.0", "2", "xxx", "3.1", "4")
	packageVersions = ("1", "2", "y", "3", "10", 11, 22)
	licenseRequirements = (None, True, False)
	setupScripts = ("setup.ins", None)
	updateScripts = ("update.ins", None)
	uninstallScripts = ("uninstall.ins", None)
	alwaysScripts = ("always.ins", None)
	onceScripts = ("once.ins", None)
	priorities = (-100, -90, -30, 0, 30, 40, 60, 99)
	descriptions = ["Test product", "Some product", "--------", "", None]
	advices = ("Nothing", "Be careful", "--------", "", None)

	for index in range(amount):
		yield LocalbootProduct(
			id=f"product{index}",
			productVersion=random.choice(productVersions),
			packageVersion=random.choice(packageVersions),
			name=f"Product {index}",
			licenseRequired=random.choice(licenseRequirements),
			setupScript=random.choice(setupScripts),
			uninstallScript=random.choice(uninstallScripts),
			updateScript=random.choice(updateScripts),
			alwaysScript=random.choice(alwaysScripts),
			onceScript=random.choice(onceScripts),
			priority=random.choice(priorities),
			description=random.choice(descriptions),
			advice=random.choice(advices),
			changelog=None,
			windowsSoftwareIds=None,
		)


@pytest.mark.parametrize("objectCount", [128, 1024])
def testObjectToHtmlProcessesGenerators(objectCount):
	text = objectToHtml(generateLocalbootProducts(objectCount))
	assert text.lstrip().startswith("[")
	assert text.rstrip().endswith("]")


def testObjectToHtmlOutputIsAsExpected():
	product = LocalbootProduct(
		id="htmltestproduct",
		productVersion="3.1",
		packageVersion="1",
		name="Product HTML Test",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		alwaysScript="always.ins",
		onceScript="once.ins",
		priority=0,
		description="asdf",
		advice="lolnope",
		changelog=None,
		windowsSoftwareIds=None,
	)

	result = objectToHtml(product)
	assert result.startswith('{<div style="padding-left: 3em;">')
	assert result.endswith("</div>}")
	assert result.count("\n") == 19
	assert result.count(",<br />") == 19

	assert '<font class="json_key">"onceScript"</font>: "once.ins"' in result
	assert '<font class="json_key">"windowsSoftwareIds"</font>: null' in result
	assert '<font class="json_key">"description"</font>: "asdf"' in result
	assert '<font class="json_key">"advice"</font>: "lolnope"' in result
	assert '<font class="json_key">"alwaysScript"</font>: "always.ins"' in result
	assert '<font class="json_key">"updateScript"</font>: "update.ins"' in result
	assert '<font class="json_key">"productClassIds"</font>: null' in result
	assert '<font class="json_key">"id"</font>: "htmltestproduct"' in result
	assert '<font class="json_key">"licenseRequired"</font>: false' in result
	assert '<font class="json_key">"ident"</font>: "htmltestproduct;3.1;1"' in result
	assert (
		'<font class="json_key">"name"</font>: "Product&nbsp;HTML&nbsp;Test"' in result
	)
	assert '<font class="json_key">"changelog"</font>: null' in result
	assert '<font class="json_key">"customScript"</font>: null' in result
	assert '<font class="json_key">"uninstallScript"</font>: "uninstall.ins"' in result
	assert '<font class="json_key">"userLoginScript"</font>: null' in result
	assert '<font class="json_key">"priority"</font>: 0' in result
	assert '<font class="json_key">"productVersion"</font>: "3.1"' in result
	assert '<font class="json_key">"packageVersion"</font>: "1"' in result
	assert '<font class="json_key">"type"</font>: "LocalbootProduct"' in result
	assert '<font class="json_key">"setupScript"</font>: "setup.ins"' in result


@pytest.mark.parametrize("objectCount", [1, 10240])
def testObjectToBeautifiedTextWorksWithGenerators(objectCount):
	generator = generateLocalbootProducts(objectCount)

	text = objectToBeautifiedText(generator)

	assert text.strip().startswith("[")
	assert text.strip().endswith("]")


@pytest.mark.parametrize("objectCount", [1, 10240])
def testObjectToBeautifiedTextGeneratesValidJSON(objectCount):
	objectsIn = list(generateLocalbootProducts(objectCount))
	text = objectToBeautifiedText(objectsIn)

	objects = fromJson(text)
	assert objectCount == len(objects)
	for obj in objects:
		assert isinstance(obj, LocalbootProduct)


def testObjectToBeautifiedText():
	product = LocalbootProduct(
		id="htmltestproduct",
		productVersion="3.1",
		packageVersion="1",
		name="Product HTML Test",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		alwaysScript="always.ins",
		onceScript="once.ins",
		priority=0,
		description="asdf",
		advice="lolnope",
		changelog=None,
		windowsSoftwareIds=None,
	)

	result = objectToBeautifiedText([product, product])
	assert result.startswith("[\n    {\n        ")
	assert result.endswith("\n    }\n]")
	assert result.count("\n") == 45

	for key, value in product.toHash().items():
		# print(f"Checking {key} ({value})")

		if value is None:
			fValue = "null"
		elif isinstance(value, bool):
			fValue = str(value).lower()
		elif isinstance(value, int):
			fValue = str(value)
		else:
			fValue = f'"{value}"'

		formattedStr = f'"{key}": {fValue}'
		assert formattedStr in result
		assert result.count(formattedStr) == 2  # We have two objects


@pytest.mark.parametrize(
	"value, expected",
	[
		([], "[]"),
		([[], []], "[\n    [],\n    []\n]"),
		({}, "{}"),
	],
)
def testObjectToBeautifiedTextEmptyObjects(expected, value):
	assert expected == objectToBeautifiedText(value)


def testObjectToBeautifiedTextFormattingDefaultDict():
	normalDict = {
		"lastStateChange": "",
		"actionRequest": "none",
		"productVersion": "",
		"productActionProgress": "",
		"packageVersion": "",
		"installationStatus": "not_installed",
		"productId": "thunderbird",
	}
	defaultDict = defaultdict(lambda x: "")

	for key, value in normalDict.items():
		defaultDict[key] = value

	normal = objectToBeautifiedText(normalDict)
	default = objectToBeautifiedText(defaultDict)

	expected = [
		("lastStateChange", ""),
		("actionRequest", "none"),
		("productVersion", ""),
		("productActionProgress", ""),
		("packageVersion", ""),
		("installationStatus", "not_installed"),
		("productId", "thunderbird"),
	]

	for _index, result in enumerate((normal, default)):
		# print(f"Check #{_index}: {result}")

		assert result.startswith("{")
		assert result.endswith("}")
		assert result.count(":") == len(expected)
		assert result.count(",") == len(expected) - 1
		assert result.count("\n") == len(expected) + 1

		for key, value in expected:
			assert f'"{key}": "{value}"' in result


def testObjectToBeautifiedTextWorkingWithSet():
	product = LocalbootProduct(
		id="htmltestproduct",
		productVersion="3.1",
		packageVersion="1",
		name="Product HTML Test",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		alwaysScript="always.ins",
		onceScript="once.ins",
		priority=0,
		description="asdf",
		advice="lolnope",
		changelog=None,
		windowsSoftwareIds=None,
	)

	# Exactly one product because set is unordered.
	obj = set([product])

	result = objectToBeautifiedText(obj)
	assert result.startswith("[\n    {\n        ")
	assert result.endswith("\n    }\n]")
	assert result.count(":") == 20
	assert result.count(",") == 19
	assert result.count("\n") == 23

	for key, value in product.toHash().items():
		# print(f"Checking {key} ({value})")

		if value is None:
			fValue = "null"
		elif isinstance(value, bool):
			fValue = str(value).lower()
		elif isinstance(value, int):
			fValue = str(value)
		else:
			fValue = f'"{value}"'

		formattedStr = f'"{key}": {fValue}'
		assert formattedStr in result


def testRandomStringBuildsStringOutOfGivenCharacters():
	assert 5 * "a" == randomString(5, characters="a")


@pytest.mark.parametrize("length", [10, 1, 0])
def testRandomStringHasExpectedLength(length):
	result = randomString(length)
	assert length == len(result)
	assert length == len(result.strip())


def testGeneratingOpsiHostKey():
	key = generateOpsiHostKey()
	assert 32 == len(key)
	assert isinstance(key, str)


@pytest.mark.parametrize(
	"sizeInBytes, base, expected",
	[
		(123, 2, "123B"),
		(1_234, 2, "1KiB"),
		(1_234_567, 2, "1MiB"),
		(314_572_800, 2, "300MiB"),
		(1_234_567_890, 2, "1GiB"),
		(1_234_567_890_000, 2, "1TiB"),
		(999, 10, "999B"),
		(10_001, 10, "10kB"),
		(90_100_100, 10, "90MB"),
		(300_000_000, 10, "300MB"),
		(1_123_123_123, 10, "1GB"),
		(1_000_999_999_999, 10, "1TB"),
	],
)
def testFormatFileSize(sizeInBytes, base, expected):
	assert formatFileSize(sizeInBytes, base) == expected


@pytest.mark.parametrize(
	"test_file, expected_hash",
	[
		("util/dhcpd/dhcpd_1.conf", "5f345ca76574c528903c1022b05acb4c"),
		("util/dhcpd/link_to_dhcpd1_1.conf", "5f345ca76574c528903c1022b05acb4c"),
	],
)
def testCreatingMd5sum(test_data_path, test_file, expected_hash):
	assert md5sum(os.path.join(test_data_path, test_file)) == expected_hash


def testChunkingList():
	base = list(range(10))

	chunks = chunk(base, size=3)
	assert (0, 1, 2) == next(chunks)
	assert (3, 4, 5) == next(chunks)
	assert (6, 7, 8) == next(chunks)
	assert (9,) == next(chunks)

	with pytest.raises(StopIteration):
		next(chunks)


def testChunkingGenerator():
	def gen():
		yield 0
		yield 1
		yield 2
		yield 3
		yield 4
		yield 5
		yield 6
		yield 7
		yield 8
		yield 9

	chunks = chunk(gen(), size=3)
	assert (0, 1, 2) == next(chunks)
	assert (3, 4, 5) == next(chunks)
	assert (6, 7, 8) == next(chunks)
	assert (9,) == next(chunks)
	with pytest.raises(StopIteration):
		next(chunks)


def testChunkingGeneratorWithDifferentSize():
	def gen():
		yield 0
		yield 1
		yield 2
		yield 3
		yield 4
		yield 5
		yield 6
		yield 7
		yield 8
		yield 9

	chunks = chunk(gen(), size=5)
	assert (0, 1, 2, 3, 4) == next(chunks)
	assert (5, 6, 7, 8, 9) == next(chunks)
	with pytest.raises(StopIteration):
		next(chunks)


@pytest.fixture
def globalConfigTestFile(test_data_path):
	return os.path.join(test_data_path, "util", "fake_global.conf")


def testGlobalConfigCommentsInFileAreIgnored(globalConfigTestFile):  # pylint: disable=redefined-outer-name
	assert "no" == getGlobalConfig("comment", globalConfigTestFile)


def testGlobalConfigLinesNeedAssignments(globalConfigTestFile):  # pylint: disable=redefined-outer-name
	assert getGlobalConfig("this", globalConfigTestFile) is None


def testGlobalConfigFileReadingValues(globalConfigTestFile):  # pylint: disable=redefined-outer-name
	assert "value" == getGlobalConfig("keyword", globalConfigTestFile)
	assert "this works too" == getGlobalConfig(
		"value with spaces", globalConfigTestFile
	)
	assert "we even can include a = and it works" == getGlobalConfig(
		"advanced value", globalConfigTestFile
	)


def testGetGlobalConfigExitsGracefullyIfFileIsMissing(globalConfigTestFile):  # pylint: disable=redefined-outer-name,unused-argument
	assert getGlobalConfig("dontCare", "nonexistingFile") is None


@pytest.mark.parametrize(
	"value, result",
	[
		(re.compile(r"ABC"), True),
		("no pattern", False),
		("SRE_Pattern", False),
	],
)
def testIfObjectIsRegExObject(value, result):
	assert isRegularExpressionPattern(value) == result


@pytest.mark.parametrize(
	"value, expected",
	[
		(2, 2),
		("2", 2),
	],
)
def testRemoveUnitDoesNotFailWithoutUnit(value, expected):
	assert expected == removeUnit(value)


@pytest.mark.parametrize(
	"value, expected",
	[
		("2MB", 2097152),  # 2048 * 1024
		("2.4MB", 2516582.4),  # (2048 * 1.2) * 1024),
		("3GB", 3221225472),
		("4Kb", 4096),
		("1Kb", 1024),
		("0.5Kb", 512),
	],
)
def testRemovingUnitFromValue(value, expected):
	assert expected == removeUnit(value)


def testSerialisingSet():
	inputSet = set(["opsi-client-agent", "mshotfix", "firefox"])
	output = toJson(inputSet)

	assert set(fromJson(output)) == inputSet


def testSerialisingList():
	inputValues = ["a", "b", "c", 4, 5]
	output = toJson(inputValues)

	assert inputValues == fromJson(output)
	assert '["a","b","c",4,5]' == output


def testSerialisingListWithFLoat():
	inputValues = ["a", "b", "c", 4, 5.6]
	output = toJson(inputValues)

	assert inputValues == fromJson(output)
	assert '["a","b","c",4,5.6]' == output


def testSerialisingListInList():
	inputValues = ["a", "b", "c", [4, 5, ["f"]]]
	assert '["a","b","c",[4,5,["f"]]]' == toJson(inputValues)


def testSerialisingListInListWithFloat():
	inputValues = ["a", "b", "c", [4, 5.6, ["f"]]]
	assert '["a","b","c",[4,5.6,["f"]]]' == toJson(inputValues)


def testSerialisingSetInList():
	inputValues = ["a", "b", set("c"), 4, 5]
	assert '["a","b",["c"],4,5]' == toJson(inputValues)


def testSerialisingSetInListWithFloat():
	inputValues = ["a", "b", set("c"), 4, 5.6]
	assert '["a","b",["c"],4,5.6]' == toJson(inputValues)


def testSerialisingDictsInList():
	inputValues = [
		{"a": "b", "c": 1},
		{"a": "b", "c": 1},
	]
	output = toJson(inputValues)

	assert output.startswith("[{")
	assert output.endswith("}]")
	assert output.count(":") == 4  # 2 dicts * 2 values
	assert output.count(",") == 3
	assert output.count('"c":1') == 2
	assert output.count('"a":"b"') == 2
	assert output.count("},{") == 1

	assert inputValues == fromJson(output)


def testSerialisingDictsInListWithFloat():
	inputValues = [
		{"a": "b", "c": 1, "e": 2.3},
		{"g": "h", "i": 4, "k": 5.6},
	]
	output = toJson(inputValues)

	assert output.startswith("[{")
	assert output.endswith("}]")
	assert output.count(":") == 6  # 2 dicts * 3 values
	assert output.count(",") == 5
	assert output.count("},{") == 1

	for value in inputValues:
		for key, val in value.items():
			if isinstance(val, str):
				assert f'"{key}":"{val}"' in output
			else:
				assert f'"{key}":{val}' in output

	assert inputValues == fromJson(output)


@pytest.mark.parametrize(
	"inputValues", [{"a": "b", "c": 1, "e": 2}, {"a": "b", "c": 1, "e": 2.3}]
)
def testSerialisingDict(inputValues):
	result = toJson(inputValues)

	assert result.startswith("{")
	assert result.endswith("}")
	assert result.count(":") == 3
	assert result.count(",") == 2
	for key, value in inputValues.items():
		if isinstance(value, str):
			assert f'"{key}":"{value}"' in result
		else:
			assert f'"{key}":{value}' in result

	assert inputValues == fromJson(result)


def testUnserialisableThingsFail():
	class Foo:  # pylint: disable=too-few-public-methods
		pass

	with pytest.raises(TypeError):
		toJson(Foo())


def testDeserialisationWithObjectCreation():
	json = """[
	{
	"ident" : "baert.niko.uib.local",
	"description" : "",
	"created" : "2014-08-29 10:41:27",
	"inventoryNumber" : "loel",
	"ipAddress" : null,
	"notes" : "",
	"oneTimePassword" : null,
	"lastSeen" : "2014-08-29 10:41:27",
	"hardwareAddress" : null,
	"opsiHostKey" : "7dc2b49c20d545bdbfad9a326380cea3",
	"type" : "OpsiClient",
	"id" : "baert.niko.uib.local"
	}
]"""

	result = fromJson(json, preventObjectCreation=False)

	assert isinstance(result, list)
	assert 1 == len(result)

	obj = result[0]
	assert isinstance(obj, OpsiClient)


def testDeserialisationWithObjectCreationFailure():
	json = """[
	{
	"ident" : "invalid",
	"description" : "",
	"created" : "2014-08-29 10:41:27",
	"inventoryNumber" : "loel",
	"ipAddress" : null,
	"notes" : "",
	"oneTimePassword" : null,
	"lastSeen" : "2014-08-29 10:41:27",
	"hardwareAddress" : null,
	"opsiHostKey" : "7dc2b49c20d545bdbfad9a326380cea3",
	"type" : "OpsiClient",
	"id" : "invalid"
	}
]"""

	with pytest.raises(ValueError):
		fromJson(json, preventObjectCreation=False)


def testDeserialisationWithoutObjectCreation():
	json = """[
	{
	"ident" : "baert.niko.uib.local",
	"description" : "",
	"created" : "2014-08-29 10:41:27",
	"inventoryNumber" : "loel",
	"ipAddress" : null,
	"notes" : "",
	"oneTimePassword" : null,
	"lastSeen" : "2014-08-29 10:41:27",
	"hardwareAddress" : null,
	"opsiHostKey" : "7dc2b49c20d545bdbfad9a326380cea3",
	"type" : "OpsiClient",
	"id" : "baert.niko.uib.local"
	}
]"""

	result = fromJson(json, preventObjectCreation=True)

	assert isinstance(result, list)
	assert 1 == len(result)

	obj = result[0]
	assert isinstance(obj, dict)
	assert "ident" in obj


def testDeserialisationWithExplicitTypeSetting():
	"It must be possible to set an type."

	json = """
	{
	"ident" : "baert.niko.uib.local",
	"description" : "",
	"created" : "2014-08-29 10:41:27",
	"inventoryNumber" : "loel",
	"ipAddress" : null,
	"notes" : "",
	"oneTimePassword" : null,
	"lastSeen" : "2014-08-29 10:41:27",
	"hardwareAddress" : null,
	"opsiHostKey" : "7dc2b49c20d545bdbfad9a326380cea3",
	"id" : "baert.niko.uib.local"
	}
"""

	obj = fromJson(json, objectType="OpsiClient", preventObjectCreation=False)

	assert isinstance(obj, OpsiClient)


def testDeserialisationWithExplicitTypeSettingWorksOnUnknown():
	"Setting invalid types must not fail but return the input instead."

	json = """
	{
	"ident" : "baert.niko.uib.local",
	"description" : "",
	"created" : "2014-08-29 10:41:27",
	"inventoryNumber" : "loel",
	"ipAddress" : null,
	"notes" : "",
	"oneTimePassword" : null,
	"lastSeen" : "2014-08-29 10:41:27",
	"hardwareAddress" : null,
	"opsiHostKey" : "7dc2b49c20d545bdbfad9a326380cea3",
	"id" : "baert.niko.uib.local"
	}
"""

	obj = fromJson(json, objectType="NotYourType", preventObjectCreation=False)

	assert isinstance(obj, dict)
	assert "baert.niko.uib.local" == obj["ident"]


def testSerialisingGeneratorFunction():
	def gen():
		yield 1
		yield 2
		yield 3
		yield "a"

	obj = toJson(gen())

	assert '[1,2,3,"a"]' == obj


def testSerialisingTuples():
	values = (1, 2, 3, 4)
	assert "[1,2,3,4]" == toJson(values)


def testFindFilesWithEmptyDirectory(tempDir):
	assert not list(findFilesGenerator(tempDir))


def testFindFilesFindsFolders():
	expectedFolders = ["top1", "top2", os.path.join("top1", "sub11")]

	with preparedDemoFolders() as demoFolder:
		folders = list(findFilesGenerator(demoFolder))
		for folder in expectedFolders:
			assert folder in folders


@contextmanager
def preparedDemoFolders():
	directories = ("top1", "top2", os.path.join("top1", "sub11"))

	with workInTemporaryDirectory() as tempDir:
		for dirname in directories:
			os.mkdir(os.path.join(tempDir, dirname))

		yield tempDir


@pytest.fixture(params=[1, 5, 91, 256, 337, 512, 829, 3333], scope="session")
def randomText(request):
	yield randomString(request.param)


@pytest.fixture(params=["575bf0d0b557dd9184ae41e7ff58ead0"])
def blowfishKey(request):
	return request.param


def test_blowfish_encryption():
	blowfishEncrypt(
		"575bf0d0b557dd9184ae41e7ff58ead0", "jksdfjklöasdfjkladfsjkasdfjlkö"
	)


def testBlowfishEncryption(randomText, blowfishKey):  # pylint: disable=redefined-outer-name
	encodedText = blowfishEncrypt(blowfishKey, randomText)
	assert encodedText != randomText

	decodedText = blowfishDecrypt(blowfishKey, encodedText)
	assert randomText == decodedText


def testBlowfishEncryptionFailures(randomText, blowfishKey):  # pylint: disable=redefined-outer-name
	encodedText = blowfishEncrypt(blowfishKey, randomText)

	with pytest.raises(BlowfishError):
		blowfishDecrypt(blowfishKey + "f00b4", encodedText)


def testBlowfishDecryptionFailsWithNoKey(randomText, blowfishKey):  # pylint: disable=redefined-outer-name
	encodedText = blowfishEncrypt(blowfishKey, randomText)

	with pytest.raises(BlowfishError):
		blowfishDecrypt(None, encodedText)


def testBlowfishEncryptionFailsWithNoKey(randomText, blowfishKey):  # pylint: disable=redefined-outer-name,unused-argument
	with pytest.raises(BlowfishError):
		blowfishEncrypt(None, randomText)


def testBlowfishWithFixedValues():
	"""
	Testing that blowfish encryption returns the desired values.

	This is important to assure that across different versions and
	platforms we always get the same values.
	"""
	key = "08e23bfada2293e0ecbd7612acf15275"

	encryptedPassword = blowfishEncrypt(key, "tanz1tanz2tanz3")
	assert encryptedPassword == "3b189043053c4e32befa7291c2f162c3"

	pcpatchPassword = blowfishDecrypt(key, encryptedPassword)
	assert pcpatchPassword == "tanz1tanz2tanz3"


@pytest.mark.parametrize("objectCount", [1, 10240])
def testObjectToBashWorksWithGenerators(objectCount):
	generator = generateLocalbootProducts(objectCount)
	result = objectToBash(generator)

	assert isinstance(result, dict)
	assert len(result) == objectCount + 1

	for index in range(1, objectCount + 1):  # to not start at 0
		resultVar = f"RESULT{index}"
		assert resultVar in result
		assert resultVar in result["RESULT"]

	for value in result.values():
		assert isinstance(value, str)


def testObjectToBashOutput():
	product = LocalbootProduct(
		id="htmltestproduct",
		productVersion="3.1",
		packageVersion="1",
		name="Product HTML Test",
		licenseRequired=False,
		setupScript="setup.ins",
		uninstallScript="uninstall.ins",
		updateScript="update.ins",
		alwaysScript="always.ins",
		onceScript="once.ins",
		priority=0,
		description="asdf",
		advice="lolnope",
		changelog=None,
		windowsSoftwareIds=None,
	)

	expected = {
		"RESULT": "(\nRESULT1=${RESULT1[*]}\nRESULT2=${RESULT2[*]}\n)",
		"RESULT1": '(\nonceScript="once.ins"\nwindowsSoftwareIds=""\ndescription="asdf"\nadvice="lolnope"\nalwaysScript="always.ins"\nupdateScript="update.ins"\nproductClassIds=""\nid="htmltestproduct"\nlicenseRequired="False"\nident="htmltestproduct;3.1;1"\nname="Product HTML Test"\nchangelog=""\ncustomScript=""\nuninstallScript="uninstall.ins"\nuserLoginScript=""\npriority="0"\nproductVersion="3.1"\npackageVersion="1"\ntype="LocalbootProduct"\nsetupScript="setup.ins"\n)',  # pylint: disable=line-too-long
		"RESULT2": '(\nonceScript="once.ins"\nwindowsSoftwareIds=""\ndescription="asdf"\nadvice="lolnope"\nalwaysScript="always.ins"\nupdateScript="update.ins"\nproductClassIds=""\nid="htmltestproduct"\nlicenseRequired="False"\nident="htmltestproduct;3.1;1"\nname="Product HTML Test"\nchangelog=""\ncustomScript=""\nuninstallScript="uninstall.ins"\nuserLoginScript=""\npriority="0"\nproductVersion="3.1"\npackageVersion="1"\ntype="LocalbootProduct"\nsetupScript="setup.ins"\n)',  # pylint: disable=line-too-long
	}

	result = objectToBash([product, product])

	assert set(result.keys()) == set(expected.keys())
	assert expected["RESULT"] == result["RESULT"]

	assert result["RESULT1"] == result["RESULT2"]

	singleResult = result["RESULT1"]
	assert singleResult.startswith("(\n")
	assert singleResult.endswith("\n)")
	assert singleResult.count("\n") == 21

	# The order may not necessarily be the same so we check every value
	assert 'onceScript="once.ins"\n' in singleResult
	assert 'windowsSoftwareIds=""\n' in singleResult
	assert 'description="asdf"\n' in singleResult
	assert 'advice="lolnope"\n' in singleResult
	assert 'alwaysScript="always.ins"\n' in singleResult
	assert 'updateScript="update.ins"\n' in singleResult
	assert 'productClassIds=""\n' in singleResult
	assert 'id="htmltestproduct"\n' in singleResult
	assert 'licenseRequired="False"\n' in singleResult
	assert 'ident="htmltestproduct;3.1;1"\n' in singleResult
	assert 'name="Product HTML Test"\n' in singleResult
	assert 'changelog=""\n' in singleResult
	assert 'customScript=""\n' in singleResult
	assert 'uninstallScript="uninstall.ins"\n' in singleResult
	assert 'userLoginScript=""\n' in singleResult
	assert 'priority="0"\n' in singleResult
	assert 'productVersion="3.1"\n' in singleResult
	assert 'packageVersion="1"\n' in singleResult
	assert 'type="LocalbootProduct"\n' in singleResult
	assert 'setupScript="setup.ins"\n' in singleResult


def testObjectToBashOnConfigStates():
	states = [
		ConfigState(
			configId="foo.bar.baz", objectId="client1.invalid.test", values=[""]
		),
		ConfigState(
			configId="drive.slow", objectId="client2.invalid.test", values=[False]
		),
	]

	result = objectToBash(states)

	# Why 2?
	# One for the general index.
	# Another one for the values of drive.slow.
	expectedLength = len(states) + 2

	assert len(result) == expectedLength

	for value in result.values():
		assert isinstance(value, str)

	for index in range(1, len(states) + 1):  # exclude ref to values of drive.slow
		resultVar = f"RESULT{index}"
		assert resultVar in result
		assert resultVar in result["RESULT"]


@pytest.mark.parametrize(
	"first, operator, second",
	[
		("1.0", "<", "2.0"),
		("2.0", ">", "1.0"),
		("1.0", "==", "1.0"),
		("1.2.3.5", "<=", "2.2.3.5"),
		("1.2.3.4-5~6", ">=", "1.2.3.4-5~1"),
	],
)
def testComparingVersionsOfSameSize(first, operator, second):
	assert compareVersions(first, operator, second)


@pytest.mark.parametrize(
	"ver1, operator, ver2",
	[
		("1.0", "", "1.0"),
	],
)
def testComparingWithoutGivingOperatorDefaultsToEqual(ver1, operator, ver2):
	assert compareVersions(ver1, operator, ver2)


def testComparingWithOnlyOneEqualitySign():
	assert compareVersions("1.0", "=", "1.0")


@pytest.mark.parametrize(
	"first, operator, second",
	[
		("1.0or2.0", "<", "1.0or2.1"),
		("1.0or2.0", "<", "1.1or2.0"),
		("1.0or2.1", "<", "1.1or2.0"),
	],
)
def testComparingOrVersions(first, operator, second):
	assert compareVersions(first, operator, second)


@pytest.mark.parametrize(
	"first, operator, second",
	[
		("20.09", "<", "21.h1"),
		("1.0.2s", "<", "1.0.2u"),
		("1.blubb.bla", "<", "1.foo"),
		("1.0.a", "<", "1.0.b"),
		("a.b", ">", "a.a"),
	],
)
def testComparingLetterVersions(first, operator, second):
	assert compareVersions(first, operator, second)


@pytest.mark.parametrize("operator", ["asdf", "+-", "<>", "!="])
def testUsingUnknownOperatorFails(operator):
	with pytest.raises(ValueError):
		compareVersions("1", operator, "2")


@pytest.mark.parametrize(
	"ver1, operator, ver2",
	[
		("1.0~20131212", "<", "2.0~20120101"),
		("1.0~20131212", "==", "1.0~20120101"),
	],
)
def testIgnoringVersionsWithWaveInThem(ver1, operator, ver2):
	assert compareVersions(ver1, operator, ver2)


@pytest.mark.parametrize(
	"ver1, operator, ver2",
	[("abc-1.2.3-4", "==", "1.2.3-4"), ("1.2.3-4", "==", "abc-1.2.3-4")],
)
def testUsingInvalidVersionStringsFails(ver1, operator, ver2):
	with pytest.raises(ValueError):
		compareVersions(ver1, operator, ver2)


@pytest.mark.parametrize(
	"ver1, operator, ver2",
	[
		("1.1.0.1", ">", "1.1"),
		("1.1", "<", "1.1.0.1"),
		("1.1", "==", "1.1.0.0"),
	],
)
def testComparisonsWithDifferntDepthsAreMadeTheSameDepth(ver1, operator, ver2):
	assert compareVersions(ver1, operator, ver2)


@pytest.mark.parametrize(
	"ver1, operator, ver2", [("1-2", "<", "1-3"), ("1-2.0", "<", "1-2.1")]
)
def testPackageVersionsAreComparedAswell(ver1, operator, ver2):
	assert compareVersions(ver1, operator, ver2)
