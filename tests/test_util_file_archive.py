# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing the work with archives.
"""

import pytest

from OPSI.Util.File.Archive import Archive, is_pigz_available

from .helpers import mock


def testArchiveFactoryRaisesExceptionOnUnknownFormat():
	with pytest.raises(Exception):
		Archive("no_filename", format="unknown")


@pytest.mark.parametrize("fileFormat", ["tar", "cpio"])
def testCreatingArchive(fileFormat):
	Archive("no_file", format=fileFormat)


def testRaisingExceptionIfFiletypeCanNotBeDetermined():
	with pytest.raises(Exception):
		Archive(__file__)


def testDisablingPigz():
	"""
	Disabling the usage of pigz by setting PIGZ_ENABLED to False.
	"""
	with mock.patch("OPSI.Util.File.Opsi.OpsiConfFile.isPigzEnabled", lambda x: False):
		assert is_pigz_available() is False
