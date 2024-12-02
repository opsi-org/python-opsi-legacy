# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing OPSI.Util.File.Opsi
"""

import os
import random

import pytest

from OPSI.Util import findFilesGenerator, md5sum
from OPSI.Util.File.Opsi import (
	BackendDispatchConfigFile,
	FileInfo,
	HostKeyFile,
	OpsiConfFile,
	PackageContentFile,
	PackageControlFile,
	parseFilename,
)

from .helpers import createTemporaryTestfile, workInTemporaryDirectory


def testReadingAllUsedBackends():
	exampleConfig = """
backend_.*		 : file, mysql, opsipxeconfd, dhcpd
host_.*			: file, mysql, opsipxeconfd, dhcpd
productOnClient_.* : file, mysql, opsipxeconfd
configState_.*	 : file, mysql, opsipxeconfd
license.*		  : mysql
softwareLicense.*  : mysql
audit.*			: mysql
.*				 : mysql
"""

	dispatchConfig = BackendDispatchConfigFile("not_reading_file")

	assert set(
		("file", "mysql", "opsipxeconfd", "dhcpd")
	) == dispatchConfig.getUsedBackends(lines=exampleConfig.split("\n"))


def testParsingIgnoresCommentedLines():
	exampleConfig = """
;backend_.*.*  : fail
	#audit.*			: fail
		.*				 : yolofile
"""

	dispatchConfig = BackendDispatchConfigFile("not_reading_file")
	usedBackends = dispatchConfig.getUsedBackends(lines=exampleConfig.split("\n"))

	assert "fail" not in usedBackends
	assert set(("yolofile",)), usedBackends


def testBackendDispatchConfigFileNotFailingOnInvalidLines():
	"""
	Reading invalid lines in a config must not lead to an exception.
	"""
	exampleConfig = """
this does not work
"""

	dispatchConfig = BackendDispatchConfigFile("not_reading_file")
	dispatchConfig.parse(lines=exampleConfig.split("\n"))


def testBackendDispatchConfigFileBackendsCanBeEmpty():
	exampleConfig = """
no_backends_follow:\t
empty_backends:\t, ,
"""

	dispatchConfig = BackendDispatchConfigFile("not_reading_file")
	result = dispatchConfig.parse(lines=exampleConfig.split("\n"))

	assert 1 == len(result)
	regex, backends = result[0]
	assert "empty_backends" == regex
	assert tuple() == backends


@pytest.fixture
def opsiConfigFile(test_data_path):
	path = os.path.join(test_data_path, "util", "file", "opsi", "opsi.conf")
	return OpsiConfFile(filename=path)


def testReadingFileAdminGroupReturnsLowercaseName(opsiConfigFile):
	assert "mypcpatch" == opsiConfigFile.getOpsiFileAdminGroup()


def testReturningDefaultForFileAdminGroup(opsiConfigFile):
	opsiConfigFile.parse([""])
	assert "pcpatch" == opsiConfigFile.getOpsiFileAdminGroup()


def testReadingReadonlyGroups(opsiConfigFile):
	assert ["myopsireadonlys"] == opsiConfigFile.getOpsiGroups("readonly")


def testGettingDefaultForReadonlyGroups(opsiConfigFile):
	opsiConfigFile.parse([""])
	assert opsiConfigFile.getOpsiGroups("readonly") is None


def testReadingPigzStatus(opsiConfigFile):
	assert not opsiConfigFile.isPigzEnabled()


def testGettingDefaultPigzStatus(opsiConfigFile):
	opsiConfigFile.parse([""])
	assert opsiConfigFile.isPigzEnabled()


@pytest.fixture
def opsiControlFilePath(test_data_path):
	# The file is the one that was causing a problem in
	# https://forum.opsi.org/viewtopic.php?f=7&t=7907
	return os.path.join(
		test_data_path, "util", "file", "opsi", "control_with_german_umlauts"
	)


def testParsingControlFileWithGermanUmlautsInDescription(opsiControlFilePath):
	p = PackageControlFile(opsiControlFilePath)
	p.parse()

	product = p.getProduct()
	assert (
		"Startet die Druckerwarteschlange auf dem Client neu / oder überhaupt."
		== product.description
	)


def testProductControlFileWithoutVersionUsesDefaults(test_data_path):
	filename = os.path.join(
		test_data_path, "util", "file", "opsi", "control_without_versions"
	)

	pcf = PackageControlFile(filename)

	product = pcf.getProduct()

	assert "1" == product.packageVersion
	assert "1.0" == product.productVersion


@pytest.fixture
def controlFileWithEmptyValues(test_data_path):
	filePath = os.path.join(
		test_data_path, "util", "file", "opsi", "control_with_empty_property_values"
	)

	with createTemporaryTestfile(filePath) as newFilePath:
		yield newFilePath


def testParsingProductControlFileContainingPropertyWithEmptyValues(
	controlFileWithEmptyValues,
):
	pcf = PackageControlFile(controlFileWithEmptyValues)

	properties = pcf.getProductProperties()
	assert len(properties) == 1

	testProperty = properties[0]
	assert testProperty.propertyId == "important"
	assert testProperty.possibleValues == []
	assert testProperty.defaultValues == []
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.description == "Nothing is important."


def testGeneratingProductControlFileContainingPropertyWithEmptyValues(
	controlFileWithEmptyValues,
):
	pcf = PackageControlFile(controlFileWithEmptyValues)
	pcf.parse()
	pcf.generate()
	pcf.generate()  # should destroy nothing
	pcf.close()
	del pcf

	pcf = PackageControlFile(controlFileWithEmptyValues)
	properties = pcf.getProductProperties()
	assert len(properties) == 1

	testProperty = properties[0]
	assert testProperty.propertyId == "important"
	assert testProperty.possibleValues == []
	assert testProperty.defaultValues == []
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.description == "Nothing is important."


@pytest.fixture
def specialCharacterControlFile(test_data_path):
	filePath = os.path.join(
		test_data_path,
		"util",
		"file",
		"opsi",
		"control_with_special_characters_in_property",
	)

	with createTemporaryTestfile(filePath) as newFilePath:
		yield newFilePath


def testGeneratingProductControlFileContainingSpecialCharactersInProperty(
	specialCharacterControlFile,
):
	pcf = PackageControlFile(specialCharacterControlFile)
	pcf.parse()
	pcf.generate()
	pcf.generate()  # should destroy nothing
	pcf.close()
	del pcf

	pcf = PackageControlFile(specialCharacterControlFile)
	properties = pcf.getProductProperties()
	assert len(properties) == 2

	if properties[0].propertyId == "target_path":
		testProperty = properties.pop(0)
	else:
		testProperty = properties.pop()

	assert testProperty.propertyId == "target_path"
	assert testProperty.description == "The target path"
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.possibleValues == ["C:\\temp\\my_target"]
	assert testProperty.defaultValues == ["C:\\temp\\my_target"]

	testProperty = properties.pop()
	assert testProperty.propertyId == "adminaccounts"
	assert (
		testProperty.description == "Windows account(s) to provision as administrators."
	)
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.defaultValues == ["Administrator"]
	assert set(testProperty.possibleValues) == {
		"Administrator",
		"domain.local\\Administrator",
		"BUILTIN\\ADMINISTRATORS",
	}


@pytest.fixture
def tomlControlFile(test_data_path):
	filePath = os.path.join(test_data_path, "util", "file", "opsi", "control.toml")

	with createTemporaryTestfile(filePath) as newFilePath:
		yield newFilePath


def testGeneratingProductControlFileToml(tomlControlFile):
	pcf = PackageControlFile(tomlControlFile)
	pcf.parse()
	pcf.generate()
	pcf.close()
	del pcf

	pcf = PackageControlFile(tomlControlFile)
	properties = pcf.getProductProperties()
	assert len(properties) == 2

	if properties[0].propertyId == "target_path":
		testProperty = properties.pop(0)
	else:
		testProperty = properties.pop()

	assert testProperty.propertyId == "target_path"
	assert testProperty.description == "The target path"
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.possibleValues == ["C:\\temp\\my_target"]
	assert testProperty.defaultValues == ["C:\\temp\\my_target"]

	testProperty = properties.pop()
	assert testProperty.propertyId == "adminaccounts"
	assert (
		testProperty.description == "Windows account(s) to provision as administrators."
	)
	assert testProperty.multiValue is False
	assert testProperty.editable is True
	assert testProperty.defaultValues == ["Administrator"]
	assert set(testProperty.possibleValues) == {
		"Administrator",
		"domain.local\\Administrator",
		"BUILTIN\\ADMINISTRATORS",
	}

	testDependency = pcf.getProductDependencies().pop()
	assert testDependency.productAction == "setup"
	assert testDependency.requiredProductId == "l-system-update"
	assert testDependency.requiredAction == "setup"
	assert testDependency.requirementType == "before"


def testConvertingControlFile(tomlControlFile):
	pcf_orig = PackageControlFile(tomlControlFile)
	pcf_orig.parse()
	pcf_orig.generate_old()  # this generates control file in old format

	# with open(tomlControlFile, "r", encoding="utf-8") as infile:
	# 	print("".join(infile.readlines()))

	pcf_generated = PackageControlFile(tomlControlFile.removesuffix(".toml"))
	assert pcf_generated.getProduct() == pcf_orig.getProduct()
	assert pcf_generated.getProductProperties() == pcf_orig.getProductProperties()
	assert pcf_generated.getProductDependencies() == pcf_orig.getProductDependencies()
	pcf_orig.close()
	pcf_generated.generate_toml()  # this generates control file in toml format

	# with open(tomlControlFile.replace(".toml", ""), "r", encoding="utf-8") as infile:
	# 	print("".join(infile.readlines()))

	pcf_regenerated = PackageControlFile(tomlControlFile)
	assert pcf_regenerated.getProduct() == pcf_generated.getProduct()
	# Advice and Description may differ as old format cannot handle multiline properly
	assert (
		pcf_regenerated.getProductProperties() == pcf_generated.getProductProperties()
	)
	assert (
		pcf_regenerated.getProductDependencies()
		== pcf_generated.getProductDependencies()
	)
	pcf_generated.close()
	pcf_regenerated.close()


@pytest.fixture
def outsideFile():
	with workInTemporaryDirectory() as anotherDirectory:
		outsideFile = os.path.join(anotherDirectory, "joan")
		with open(outsideFile, "w") as externalFile:
			externalFile.write("Watson, are you here?")

		yield outsideFile


@pytest.fixture
def outsideDir():
	with workInTemporaryDirectory() as tmpDir:
		dirPath = os.path.join(tmpDir, "dirOutside")
		os.mkdir(dirPath)

		yield dirPath


def testPackageContentFileCreation(outsideFile, outsideDir):
	with workInTemporaryDirectory() as tempDir:
		content = fillDirectory(tempDir)

		outsideLink = "jlink"
		assert outsideLink not in content
		for filename in (f for f, t in content.items() if t == "f"):
			os.symlink(outsideFile, os.path.join(tempDir, outsideLink))
			content[outsideLink] = "f"
			break

		outsideDirLink = "dlink"
		assert outsideDirLink not in content
		for dirname in (f for f, t in content.items() if t == "d"):
			os.symlink(outsideDir, os.path.join(tempDir, outsideDirLink))
			content[outsideDirLink] = "d"
			break

		clientDataFiles = list(findFilesGenerator(tempDir))

		filename = os.path.join(tempDir, "test.files")
		contentFile = PackageContentFile(filename)
		contentFile.setProductClientDataDir(tempDir)
		contentFile.setClientDataFiles(clientDataFiles)
		contentFile.generate()

		assert os.path.exists(filename)
		assert os.path.getsize(filename) > 10, "Generated file is empty!"

		# Manual parsing of the file contents to ensure that the
		# format matches our requirements.
		with open(filename) as generatedFile:
			for line in generatedFile:
				try:
					entry, path, size = line.split(" ", 2)

					path = path.strip("'")
					content.pop(path)

					if path == outsideLink:
						assert entry == "f"
					elif path == outsideDirLink:
						assert entry == "d"

					if entry == "d":
						assert int(size.strip()) == 0
					elif entry == "f":
						size, hashSum = size.split(" ", 1)

						assert os.path.getsize(path) == int(size)

						assert not hashSum.startswith("'")
						assert not hashSum.endswith("'")
						hashSum = hashSum.strip()
						assert md5sum(path) == hashSum
					elif entry == "l":
						size, target = size.split(" ", 1)

						assert int(size) == 0

						target = target.strip()
						assert target.startswith("'")
						assert target.endswith("'")
						target = target.strip("'")
						assert target
					else:
						raise RuntimeError("Unexpected type {0!r}".format(entry))
				except Exception:
					print("Processing line {0!r} failed".format(line))
					raise

		assert not content, "Files not listed in content file: {0}".format(
			", ".join(content)
		)


def fillDirectory(directory):
	assert os.path.exists(directory)

	directories = [
		("subdir",),
		("subdir", "sub1"),
	]

	files = [
		(("simplefile",), "I am an very simple file\nFor real!"),
		(("subdir", "fileinsub1"), "Subby one"),
		(("subdir", "fileinsub2"), "Subby two"),
		(("subdir", "sub1", "simplefile2"), "Sub in a sub.\nThanks, no cheese!"),
	]

	links = [
		(("simplefile",), ("simplelink",)),
		(("subdir", "sub1", "simplefile2"), ("goingdown",)),
	]

	content = {}

	for dirPath in directories:
		os.mkdir(os.path.join(directory, *dirPath))
		content[os.path.join(*dirPath)] = "d"

	for filePath, text in files:
		with open(os.path.join(directory, *filePath), "w") as fileHandle:
			fileHandle.write(text)

		content[os.path.join(*filePath)] = "f"

	for source, name in links:
		os.symlink(os.path.join(directory, *source), os.path.join(directory, *name))
		content[os.path.join(*name)] = "l"

	return content


def testParsingPackageContentFile(outsideFile, outsideDir):
	with workInTemporaryDirectory() as tempDir:
		content = fillDirectory(tempDir)

		outsideLink = "jlink"
		assert outsideLink not in content
		for filename in (f for f, t in content.items() if t == "f"):
			os.symlink(outsideFile, os.path.join(tempDir, outsideLink))
			content[outsideLink] = "f"
			break

		outsideDirLink = "dlink"
		assert outsideDirLink not in content
		for dirname in (f for f, t in content.items() if t == "d"):
			os.symlink(outsideDir, os.path.join(tempDir, outsideDirLink))
			content[outsideDirLink] = "d"
			break

		filename = os.path.join(tempDir, "test.files")
		contentFile = PackageContentFile(filename)
		contentFile.setProductClientDataDir(tempDir)
		clientDataFiles = list(findFilesGenerator(tempDir))
		contentFile.setClientDataFiles(clientDataFiles)
		contentFile.generate()
		del contentFile

		# Checking the parsing feature of PackageContentFile
		readContentFile = PackageContentFile(filename)
		contents = readContentFile.parse()
		assert len(contents) == len(content)

		for filename, entry in contents.items():
			assert filename
			assert not filename.startswith("'")
			assert not filename.endswith("'")

			entryType = entry["type"]
			assert entryType == content[filename] or (
				entryType == "f" and content[filename] == "l"
			)

			if entryType == "d":
				assert entry["size"] == 0
				assert entry["md5sum"] == ""
				assert entry["target"] == ""
			elif entryType == "f":
				assert entry["size"] > 0
				hashSum = entry["md5sum"]
				assert hashSum
				assert not hashSum.startswith("'")
				assert not hashSum.endswith("'")
				assert entry["target"] == ""
			else:
				raise RuntimeError("Unexpected type in {0!r}".format(entry))


@pytest.fixture
def emptyFile():
	with workInTemporaryDirectory() as tempDir:
		path = os.path.join(tempDir, "empty")
		with open(path, "w"):
			pass

		yield path


def testHostKeyFileUsage(emptyFile):
	hkf = HostKeyFile(emptyFile)

	hostId = "client.domain.test"
	assert hkf.getOpsiHostKey(hostId) is None  # unknown entry

	password = "deadbeef1c0ff3300deadbeef1c0ff33"  # 32 chars
	hkf.setOpsiHostKey(hostId, password)
	assert hkf.getOpsiHostKey(hostId) == password


@pytest.fixture(params=[50, 500, 5000], scope="session")
def hostKeyEntries(request):
	def generatePassword(number):
		pw = "deadbeef1c0ff3300deadbeef1c0ff33{0}".format(number)
		return pw[-32:]  # We need to have 32 characters in length

	entries = [
		("client{0}.domain.test".format(i), generatePassword(i))
		for i in range(request.param)
	]
	random.shuffle(entries)

	return entries


def testHostKeyFileGeneration(emptyFile, hostKeyEntries):
	hkf = HostKeyFile(emptyFile)
	for hostId, password in hostKeyEntries:
		hkf.setOpsiHostKey(hostId, password)
	hkf.generate()

	hosts = dict(hostKeyEntries)

	foundKeys = 0
	with open(emptyFile) as f:
		for line in f:
			line = line.strip()
			hostId, pw = line.split(":")
			assert hostId
			assert pw
			assert hosts[hostId] == pw
			foundKeys += 1

	assert foundKeys == len(hostKeyEntries)


def testHostKeyFileParsing(emptyFile, hostKeyEntries):
	with open(emptyFile, "w") as f:
		for hostId, password in hostKeyEntries:
			f.write("%s:%s\n" % (hostId, password))

	hkf = HostKeyFile(emptyFile)
	for hostId, password in hostKeyEntries:
		assert hkf.getOpsiHostKey(hostId) == password


def testHostKeyFileParsingSkippingInvalidEntries(emptyFile, hostKeyEntries):
	with open(emptyFile, "w") as f:
		for hostId, password in hostKeyEntries:
			f.write("%s:%s\n" % (hostId, password))

		f.write("%s:%s\n" % (hostId, password))  # duplicate entry
		f.write("nohostid:%s\n" % password)  # Invalid password
		f.write("%s:nopw\n" % hostId)  # Invalid host Id
		f.write(":\n")  # no content

	hkf = HostKeyFile(emptyFile)
	hkf.parse()


@pytest.mark.parametrize(
	"filename, expected",
	[
		("sap_7.40.8-3.opsi", FileInfo("sap", "7.40.8-3")),
		("sap_7.40.8-3.opsi.md5", FileInfo("sap", "7.40.8-3")),
		("sap_7.40.8-3.opsi.zsync", FileInfo("sap", "7.40.8-3")),
		("sap_dev_bex_7.40.8-3.opsi", FileInfo("sap_dev_bex", "7.40.8-3")),
		(
			"firefox_52.3.0esror55.0-2~fra3264.opsi",
			FileInfo("firefox", "52.3.0esror55.0-2~fra3264"),
		),
		("README.txt", None),
		("some/relative/path/summer_2000-19.opsi", FileInfo("summer", "2000-19")),
		("/tmp/summer_2000-18.opsi", FileInfo("summer", "2000-18")),
	],
)
def testParsingFile(filename, expected):
	assert expected == parseFilename(filename)
