# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
OPSI Exceptions.
Deprecated, use opsicommon.exceptions instead.
"""

from opsicommon.exceptions import *  # noqa: F403


class CommandNotFoundException(RuntimeError):
	pass
