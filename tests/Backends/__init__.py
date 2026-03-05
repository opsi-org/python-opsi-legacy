# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Basics for backend tests.
"""

from contextlib import contextmanager

from opsi_legacy.Backend.Backend import ExtendedConfigDataBackend

__all__ = ("getTestBackend", "BackendMixin")


@contextmanager
def getTestBackend(extended=False):
	"""
	Get a backend for tests.

	Each call to this will return a different backend.

	If `extended` is True the returned backend will be an
	`ExtendedConfigDataBackend`.
	"""
	from .File import getFileBackend  # lazy import

	with getFileBackend() as backend:
		if extended:
			backend = ExtendedConfigDataBackend(backend)

		backend.backend_createBase()
		try:
			yield backend
		finally:
			backend.backend_deleteBase()


class BackendMixin:
	"""
    Base class for backend test mixins.

    :param CREATES_INVENTORY_HISTORY: Set to true if the backend keeps a \
history of the inventory. This will affects tests!
    :type CREATES_INVENTORY_HISTORY: bool
    """

	CREATES_INVENTORY_HISTORY = False

	def setUpBackend(self):
		pass

	def tearDownBackend(self):
		pass
