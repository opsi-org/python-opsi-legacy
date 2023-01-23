# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing opsi config module.
"""

from pathlib import Path

import pytest
from OPSI.Config import (
	DEFAULT_DEPOT_USER,
	FILE_ADMIN_GROUP,
	OPSI_ADMIN_GROUP,
	OPSI_GLOBAL_CONF,
	OPSICONFD_USER,
	OpsiConfFile,
)


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
def test_value_is_set(value: str) -> None:
	assert value is not None
	assert value


def test_opsi_conf(tmp_path: Path) -> None:
	configfile = tmp_path / "opsi.conf"
	configfile.write_text(
		"[ldap_auth]\nldap_url = ldaps://ldaphost:636/dc=opsi,dc=org\nbind_user = uid={username},dc=Users,{base}\ngroup_filter = (filter=val)",
		encoding="utf-8",
	)
	conf_file = OpsiConfFile(filename=str(configfile))  # type: ignore[no-untyped-call]
	ldap_auth = conf_file.get_ldap_auth_config()
	assert ldap_auth == {
		"ldap_url": "ldaps://ldaphost:636/dc=opsi,dc=org",
		"bind_user": "uid={username},dc=Users,{base}",
		"group_filter": "(filter=val)",
	}
	print(ldap_auth)
