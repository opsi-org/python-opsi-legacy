# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
BackendManager.

If you want to work with an opsi backend in i.e. a script a
BackendManager instance should be your first choice.
A BackendManager instance does the heavy lifting for you so you don't
need to set up you backends, ACL, multiplexing etc. yourself.
"""

from .Manager._Manager import BackendManager, backendManagerFactory
from .Manager.AccessControl import BackendAccessControl
from .Manager.Dispatcher import BackendDispatcher
from .Manager.Extender import BackendExtender

__all__ = (
	"BackendManager",
	"BackendDispatcher",
	"BackendExtender",
	"BackendAccessControl",
	"backendManagerFactory",
)
