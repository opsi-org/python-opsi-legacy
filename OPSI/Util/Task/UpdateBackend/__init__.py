# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Functionality to update OPSI backends.

.. versionadded:: 4.0.6.1
"""


class BackendUpdateError(RuntimeError):
	"This error indicates a problem during a backend update."
