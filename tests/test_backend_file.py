# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the opsi file backend.
"""

import pytest

from OPSI.Backend.File import FileBackend
from OPSI.Exceptions import BackendConfigurationError

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
