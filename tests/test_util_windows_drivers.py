# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2013-2016 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Testing WindowsDrivers.

:author: Erol Ueluekmen <e.ueluekmen@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import os

from OPSI.Util.WindowsDrivers import integrateAdditionalWindowsDrivers
from OPSI.Object import AuditHardwareOnHost

from .helpers import workInTemporaryDirectory


def _generateAuditHardwareOnHost(hardwareClass, hostId, vendor, model, sku=None):
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


def testByAudit(self):
	with workInTemporaryDirectory() as temporary_folder:
		destinationDir = os.path.join(temporary_folder, "destination")

		hardwareClass = "COMPUTER_SYSTEM"
		hostId = "test.domain.local"
		vendor = "Dell Inc."
		model = "Venue 11 Pro 7130 MS"

		testData1 = _generateAuditHardwareOnHost(hardwareClass, hostId, vendor, model)
		_generateDirectories(temporary_folder, vendor, model)
		_generateTestFiles(temporary_folder, vendor, model, "test.inf")

		result = integrateAdditionalWindowsDrivers(temporary_folder, destinationDir, [], auditHardwareOnHosts=[testData1])

		expectedResult = [{
			'devices': [],
			'directory': u'%s/1' % destinationDir,
			'driverNumber': 1,
			'infFile': u'%s/1/test.inf' % destinationDir
		}]

		assert expectedResult == result


def testByAuditWithUnderscoreAtTheEnd():
	with workInTemporaryDirectory() as temporary_folder:
		destinationDir = os.path.join(temporary_folder, "destination")

		hardwareClass = "COMPUTER_SYSTEM"
		hostId = "test.domain.local"
		vendor = "Dell Inc_"
		model = "Venue 11 Pro 7130 MS"

		testData1 = _generateAuditHardwareOnHost(hardwareClass, hostId, "Dell Inc.", model)
		_generateDirectories(temporary_folder, vendor, model)
		_generateTestFiles(temporary_folder, vendor, model, "test.inf")

		result = integrateAdditionalWindowsDrivers(temporary_folder, destinationDir, [], auditHardwareOnHosts=[testData1])

		expectedResult = [{
			'devices': [],
			'directory': u'%s/1' % destinationDir,
			'driverNumber': 1,
			'infFile': u'%s/1/test.inf' % destinationDir
		}]

		assert expectedResult == result


def testByAuditWithSKUFallback():
	with workInTemporaryDirectory() as temporary_folder:
		destinationDir = os.path.join(temporary_folder, "destination")

		hardwareClass = "COMPUTER_SYSTEM"
		hostId = "test.domain.local"
		vendor = "Dell Inc_"
		model = "Venue 11 Pro 7130 MS (ABC)"
		sku = "ABC"
		model_without_sku = "Venue 11 Pro 7130 MS"

		testData1 = _generateAuditHardwareOnHost(hardwareClass, hostId, "Dell Inc.", model, sku)
		_generateDirectories(temporary_folder, vendor, model_without_sku)
		_generateTestFiles(temporary_folder, vendor, model_without_sku, "test.inf")

		result = integrateAdditionalWindowsDrivers(temporary_folder, destinationDir, [], auditHardwareOnHosts=[testData1])

		expectedResult = [{
			'devices': [],
			'directory': u'%s/1' % destinationDir,
			'driverNumber': 1,
			'infFile': u'%s/1/test.inf' % destinationDir
		}]

		assert expectedResult == result
