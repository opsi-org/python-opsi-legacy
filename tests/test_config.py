# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Testing opsi config module.
"""

import pytest

from opsi_legacy.Config import DEFAULT_DEPOT_USER, FILE_ADMIN_GROUP, OPSI_ADMIN_GROUP, OPSI_GLOBAL_CONF, OPSICONFD_USER


@pytest.mark.parametrize(
	"value",
	[
		FILE_ADMIN_GROUP,
		OPSI_ADMIN_GROUP,
		DEFAULT_DEPOT_USER,
		OPSI_GLOBAL_CONF,
		OPSICONFD_USER,
	],
)
def testValueIsSet(value):
	assert value is not None
	assert value
