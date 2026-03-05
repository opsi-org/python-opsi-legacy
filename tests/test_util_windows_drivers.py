# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing WindowsDrivers.
"""

import os

import pytest

from opsi_legacy.Object import AuditHardwareOnHost
from opsi_legacy.Util.WindowsDrivers import integrateAdditionalWindowsDrivers


def auditHardwareOnHostFactory(hardwareClass, hostId, vendor, model, sku=None):
	auditHardwareOnHost = AuditHardwareOnHost(hardwareClass, hostId)
	auditHardwareOnHost.vendor = vendor
	auditHardwareOnHost.model = model
	auditHardwareOnHost.sku = sku

	return auditHardwareOnHost


def _generateDirectories(folder, vendor, model):
	rulesDir = os.path.join(folder, "byAudit")
	if not os.path.exists(rulesDir):
		os.mkdir(rulesDir)
	vendorDir = os.path.join(rulesDir, vendor)
	modelDir = os.path.join(vendorDir, model)

	os.mkdir(vendorDir)
	os.mkdir(modelDir)


def _generateTestFiles(folder, vendor, model, filename):
	dstFilename = os.path.join(folder, "byAudit", vendor, model, filename)
	with open(dstFilename, "w"):
		pass


@pytest.fixture
def destinationDir(tempDir):
	yield os.path.join(tempDir, "destination")


@pytest.fixture(scope="session")
def hostId():
	yield "test.domain.local"


@pytest.fixture(scope="session")
def hardwareClass():
	yield "COMPUTER_SYSTEM"


def testByAudit(tempDir, destinationDir, hardwareClass, hostId):
	vendor = "Dell Inc."
	model = "Venue 11 Pro 7130 MS"

	testData1 = auditHardwareOnHostFactory(hardwareClass, hostId, vendor, model)
	_generateDirectories(tempDir, vendor, model)
	_generateTestFiles(tempDir, vendor, model, "test.inf")

	result = integrateAdditionalWindowsDrivers(tempDir, destinationDir, [], auditHardwareOnHosts=[testData1])

	expectedResult = [
		{
			"devices": [],
			"directory": "%s/1" % destinationDir,
			"driverNumber": 1,
			"infFile": "%s/1/test.inf" % destinationDir,
		}
	]

	assert expectedResult == result


def testByAuditWithUnderscoreAtTheEnd(tempDir, destinationDir, hardwareClass, hostId):
	vendor = "Dell Inc_"
	model = "Venue 11 Pro 7130 MS"

	testData1 = auditHardwareOnHostFactory(hardwareClass, hostId, "Dell Inc.", model)
	_generateDirectories(tempDir, vendor, model)
	_generateTestFiles(tempDir, vendor, model, "test.inf")

	result = integrateAdditionalWindowsDrivers(tempDir, destinationDir, [], auditHardwareOnHosts=[testData1])

	expectedResult = [
		{
			"devices": [],
			"directory": "%s/1" % destinationDir,
			"driverNumber": 1,
			"infFile": "%s/1/test.inf" % destinationDir,
		}
	]

	assert expectedResult == result


def testByAuditWithSKUFallback(tempDir, destinationDir, hardwareClass, hostId):
	vendor = "Dell Inc_"
	model = "Venue 11 Pro 7130 MS (ABC)"
	sku = "ABC"
	model_without_sku = "Venue 11 Pro 7130 MS"

	testData1 = auditHardwareOnHostFactory(hardwareClass, hostId, "Dell Inc.", model, sku)
	_generateDirectories(tempDir, vendor, model_without_sku)
	_generateTestFiles(tempDir, vendor, model_without_sku, "test.inf")

	result = integrateAdditionalWindowsDrivers(tempDir, destinationDir, [], auditHardwareOnHosts=[testData1])

	expectedResult = [
		{
			"devices": [],
			"directory": "%s/1" % destinationDir,
			"driverNumber": 1,
			"infFile": "%s/1/test.inf" % destinationDir,
		}
	]

	assert expectedResult == result
	assert expectedResult == result
