# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
OPSI Exceptions.
Deprecated, use opsi.exception instead.
"""

from opsi.exception import *  # noqa: F403


class CommandNotFoundException(RuntimeError):
	pass


class RepositoryError(OpsiError):
	pass
