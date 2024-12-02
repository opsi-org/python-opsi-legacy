# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing OPSI.Util.File
"""

import os
import shutil
from contextlib import contextmanager

import pytest

from OPSI.Util.File import IniFile, InfFile, TxtSetupOemFile, ZsyncFile

from .helpers import createTemporaryTestfile


def testParsingIniFileDoesNotFail():
	iniTestData = r"""
#[section1]
# abc = def

[section2]
abc = def # comment

[section3]
key = value ;comment ; comment2

[section4]
key = value \; no comment \# comment2 ;# comment3

[section5]
key = \;\;\;\;\;\;\;\;\;\;\;\;
"""

	iniFile = IniFile("filename_is_irrelevant_for_this")
	iniFile.parse(iniTestData.split("\n"))


@pytest.fixture(
	params=[
		"inf_testdata_1.inf",
		"inf_testdata_2.inf",
		"inf_testdata_3.inf",
		"inf_testdata_4.inf",
		"inf_testdata_5.inf",
		"inf_testdata_6.inf",
		"inf_testdata_7.inf",
		"inf_testdata_8.inf",
	]
)
def infFile(request):
	yield InfFile(getAbsolutePathToTestData(request.param))


def testDeviceDataIsReadFromInfFile(infFile):
	infFile.parse()

	devices = infFile.getDevices()
	assert devices

	for dev in devices:
		assert dev["vendor"]
		assert dev["device"]


def testTxtSetupOemFileParseAndGenerateDoesNotFail(txtSetupOemFileInTempDirectory):
	txtSetupOemFileInTempDirectory.parse()

	txtSetupOemFileInTempDirectory.generate()


@pytest.fixture
def txtSetupOemFileInTempDirectory(txtSetupOemFilePath):
	with getTempTxtSetupOemFileFromPath(txtSetupOemFilePath) as setupFile:
		yield setupFile


@contextmanager
def getTempTxtSetupOemFileFromPath(filePath):
	with createTemporaryTestfile(filePath) as newPath:
		yield TxtSetupOemFile(newPath)


def txtSetupOemFileNames():
	yield "txtsetupoem_testdata_1.oem"
	yield "txtsetupoem_testdata_2.oem"
	yield "txtsetupoem_testdata_3.oem"
	yield "txtsetupoem_testdata_4.oem"
	yield "txtsetupoem_testdata_5.oem"
	yield "txtsetupoem_testdata_6.oem"
	yield "txtsetupoem_testdata_7.oem"


@pytest.fixture(params=[f for f in txtSetupOemFileNames()])
def txtSetupOemFilePath(request):
	yield getAbsolutePathToTestData(request.param)


def getAbsolutePathToTestData(filename):
	from .conftest import TEST_DATA_PATH

	return os.path.join(TEST_DATA_PATH, "util", "file", filename)


@pytest.fixture
def regeneratedtxtSetupOemFileWithWorkarounds(txtSetupOemFileInTempDirectory):
	txtSetupOemFile = txtSetupOemFileInTempDirectory
	txtSetupOemFile.parse()
	txtSetupOemFile.applyWorkarounds()
	txtSetupOemFile.generate()

	yield txtSetupOemFile


def testTxtSetupOemFileApplyingWorkaroundsRemovesComments(
	regeneratedtxtSetupOemFileWithWorkarounds,
):
	comment_chars = (";", "#")

	with open(regeneratedtxtSetupOemFileWithWorkarounds.getFilename()) as setupfile:
		for line in setupfile:
			assert not line.startswith(comment_chars)


def testTxtSetupOemFileApplyingWorkaroundsCreatesDisksSection(
	regeneratedtxtSetupOemFileWithWorkarounds,
):
	assert _sectionExists(
		regeneratedtxtSetupOemFileWithWorkarounds.getFilename(), "[Disks]"
	)


def _sectionExists(filepath, sectionName):
	with open(filepath) as setupfile:
		return any(sectionName in line for line in setupfile)


def testTxtSetupOemFileApplyingWorkaroundsCreatesDefaultsSection(
	regeneratedtxtSetupOemFileWithWorkarounds,
):
	assert _sectionExists(
		regeneratedtxtSetupOemFileWithWorkarounds.getFilename(), "[Defaults]"
	)


def testTxtSetupOemFileCommasAreFollowdBySpace(
	regeneratedtxtSetupOemFileWithWorkarounds,
):
	with open(regeneratedtxtSetupOemFileWithWorkarounds.getFilename()) as setupfile:
		for line in setupfile:
			if "," in line:
				commaIndex = line.index(",")
				assert " " == line[commaIndex + 1]


def testTxtSetupOemFileApplyingWorkaroundsChangesContents(
	txtSetupOemFileInTempDirectory,
):
	with open(txtSetupOemFileInTempDirectory.getFilename()) as setupfile:
		before = setupfile.readlines()

	txtSetupOemFileInTempDirectory.parse()
	txtSetupOemFileInTempDirectory.applyWorkarounds()
	txtSetupOemFileInTempDirectory.generate()

	with open(txtSetupOemFileInTempDirectory.getFilename()) as setupfile:
		after = setupfile.readlines()

	assert before != after


@pytest.mark.parametrize(
	"filename, vendorId, deviceId",
	[
		("txtsetupoem_testdata_1.oem", "10DE", "07F6"),
		("txtsetupoem_testdata_3.oem", "10DE", "07F6"),
		("txtsetupoem_testdata_4.oem", "1002", "4391"),
		("txtsetupoem_testdata_7.oem", "8086", "3B22"),
	],
)
def testReadingInExistingSpecialDevicesAndApplyingFixes(filename, vendorId, deviceId):
	absFile = getAbsolutePathToTestData(filename)

	with getTempTxtSetupOemFileFromPath(absFile) as setupFile:
		assert setupFile.isDeviceKnown(vendorId=vendorId, deviceId=deviceId)

		assert [] != setupFile.getFilesForDevice(
			vendorId=vendorId, deviceId=deviceId, fileTypes=[]
		)

		assert setupFile.getComponentOptionsForDevice(
			vendorId=vendorId, deviceId=deviceId
		)["description"]

		setupFile.applyWorkarounds()
		setupFile.generate()

		assert [] != setupFile.getFilesForDevice(
			vendorId=vendorId, deviceId=deviceId, fileTypes=[]
		)


@pytest.mark.parametrize(
	"filename, vendorId, deviceId",
	[
		("txtsetupoem_testdata_2.oem", "10DE", "07F6"),
		("txtsetupoem_testdata_5.oem", "10DE", "07F6"),
		("txtsetupoem_testdata_6.oem", "10DE", "07F6"),
	],
)
def testCheckingForMissingVendorAndDevices(filename, vendorId, deviceId):
	absFile = getAbsolutePathToTestData(filename)

	with getTempTxtSetupOemFileFromPath(absFile) as setupFile:
		assert not setupFile.isDeviceKnown(vendorId=vendorId, deviceId=deviceId)

		with pytest.raises(Exception):
			setupFile.getFilesForDevice(
				vendorId=vendorId, deviceId=deviceId, fileTypes=[]
			)

		with pytest.raises(Exception):
			setupFile.getComponentOptionsForDevice(vendorId=vendorId, deviceId=deviceId)

		setupFile.applyWorkarounds()
		setupFile.generate()

		with pytest.raises(Exception):
			setupFile.getFilesForDevice(
				vendorId=vendorId, deviceId=deviceId, fileTypes=[]
			)


@pytest.mark.parametrize(
	"filename",
	[
		"txtsetupoem_testdata_1.oem",
		"txtsetupoem_testdata_2.oem",
		"txtsetupoem_testdata_3.oem",
		"txtsetupoem_testdata_4.oem",
		"txtsetupoem_testdata_6.oem",
		"txtsetupoem_testdata_7.oem",
	],
)
def testDevicesInTxtSetupOemFileHaveVendorAndDeviceId(filename):
	absFile = getAbsolutePathToTestData(filename)

	with getTempTxtSetupOemFileFromPath(absFile) as setupFile:
		devices = setupFile.getDevices()

		assert devices

		for device in devices:
			assert device["vendor"]
			assert device["device"]


@pytest.mark.parametrize("filename", ["txtsetupoem_testdata_5.oem"])
def testReadingDevicesContents(filename):
	absFile = getAbsolutePathToTestData(filename)

	with getTempTxtSetupOemFileFromPath(absFile) as setupFile:
		for device in setupFile.getDevices():
			assert device["vendor"]
			assert "fttxr5_O" == device["serviceName"]


@pytest.mark.parametrize(
	"filename",
	[
		pytest.param("txtsetupoem_testdata_1.oem", marks=pytest.mark.xfail),
		"txtsetupoem_testdata_2.oem",
		pytest.param("txtsetupoem_testdata_3.oem", marks=pytest.mark.xfail),
		"txtsetupoem_testdata_4.oem",
		"txtsetupoem_testdata_5.oem",
		"txtsetupoem_testdata_6.oem",
		"txtsetupoem_testdata_7.oem",
	],
)
def testReadingDataFromTextfileOemSetup(filename):
	absFile = getAbsolutePathToTestData(filename)

	with getTempTxtSetupOemFileFromPath(absFile) as setupFile:
		assert not setupFile.isDeviceKnown(vendorId="10DE", deviceId="0AD4")

		with pytest.raises(Exception):
			setupFile.getFilesForDevice(vendorId="10DE", deviceId="0AD4", fileTypes=[])

		with pytest.raises(Exception):
			setupFile.getFilesForDevice(vendorId="10DE", deviceId="07F6", fileTypes=[])

		assert not setupFile.isDeviceKnown(vendorId="10DE", deviceId="0754")

		with pytest.raises(Exception):
			setupFile.getComponentOptionsForDevice(vendorId="10DE", deviceId="0AD4")


def testZsyncFile(tempDir, test_data_path):
	filename = "opsi-configed_4.0.7.1.3-2.opsi.zsync"
	expectedHeaders = {
		"Blocksize": "2048",
		"Filename": "opsi-configed_4.0.7.1.3-2.opsi",
		"Hash-Lengths": "2,2,5",
		"Length": "9574912",
		"SHA-1": "702afc14c311ce9e4083c893c9ac4f4390413ae9",
		"URL": "opsi-configed_4.0.7.1.3-2.opsi",
		"zsync": "0.6.2",
	}

	def checkZsyncFile(zf):
		assert zf._data
		assert zf._header

		for key, value in expectedHeaders.items():
			assert zf._header[key] == value

		assert "mtime" not in zf._header

	shutil.copy(os.path.join(test_data_path, "util", "file", filename), tempDir)

	testFile = os.path.join(tempDir, filename)

	zf = ZsyncFile(testFile)
	assert not zf._parsed
	zf.parse()
	checkZsyncFile(zf)

	zf._header["mtime"] = "should not be written"
	zf.generate()
	zf.close()
	del zf

	zf = ZsyncFile(testFile)
	zf.parse()
	checkZsyncFile(zf)
