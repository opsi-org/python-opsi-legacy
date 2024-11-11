# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing opsi config module.
"""

from OPSI.Config import (
	DEFAULT_DEPOT_USER,
	FILE_ADMIN_GROUP,
	OPSI_ADMIN_GROUP,
	OPSI_GLOBAL_CONF,
	OPSICONFD_USER,
)

import pytest


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
