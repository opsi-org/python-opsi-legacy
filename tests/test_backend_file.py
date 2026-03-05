# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing the opsi file backend.
"""

import pytest

from opsi_legacy.Backend.File import FileBackend
from opsi_legacy.Exceptions import BackendConfigurationError

from .Backends.File import getFileBackend


def testGetRawDataFailsOnFileBackendBecauseMissingQuerySupport():
	with getFileBackend() as backend:
		with pytest.raises(BackendConfigurationError):
			backend.getRawData("SELECT * FROM BAR;")


def testGetDataFailsOnFileBackendBecauseMissingQuerySupport():
	with getFileBackend() as backend:
		with pytest.raises(BackendConfigurationError):
			backend.getData("SELECT * FROM BAR;")


@pytest.mark.parametrize(
	"filename",
	[
		"exampleexam_e.-ex_1234.12-1234.12.localboot",
	],
)
def testProductFilenamePattern(filename):
	assert FileBackend.PRODUCT_FILENAME_REGEX.search(filename) is not None
