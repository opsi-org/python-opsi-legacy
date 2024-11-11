# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
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
