# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Various important configuration values.

This module should be used to refer to often used values in a consistent
way instead of hardcoding the values.

If new values are added they must be added that the module stays
functional independen of the current underlying system.

These values are not intended to be changed on-the-fly!
Doing so might result in unforseen problems and is strongly discouraged!
"""

# Group used to identify members whits administrative rights in opsi
OPSI_ADMIN_GROUP = "opsiadmin"

# Default user when accessing the opsi depot
DEFAULT_DEPOT_USER = "pcpatch"


# Default home dir of depot user
DEFAULT_DEPOT_USER_HOME = "/var/lib/opsi"

# Path to global opsi configuration file
OPSI_GLOBAL_CONF = "/etc/opsi/global.conf"

try:
	from OPSI.Util.File.Opsi import OpsiConfFile

	OPSI_ADMIN_GROUP = OpsiConfFile().getOpsiAdminGroup()
	FILE_ADMIN_GROUP = OpsiConfFile().getOpsiFileAdminGroup()
except Exception:  # pylint: disable=broad-except
	# Use "pcpatch" if group exists otherwise use the new default "opsifileadmins"
	try:
		import grp

		grp.getgrnam("pcpatch")
		FILE_ADMIN_GROUP = "pcpatch"
	except (KeyError, ImportError):
		FILE_ADMIN_GROUP = "opsifileadmins"

# User that is running opsiconfd.
try:
	# pyright: reportMissingImports=false
	from opsiconfd.config import config  # pylint: disable=import-error

	OPSICONFD_USER = config.run_as_user
except Exception:  # pylint: disable=broad-except
	OPSICONFD_USER = "opsiconfd"
