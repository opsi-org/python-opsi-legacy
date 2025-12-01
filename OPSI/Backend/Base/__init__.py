# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Backends.
"""

from __future__ import absolute_import

from .Backend import Backend, describeInterface
from .ConfigData import ConfigDataBackend
from .Extended import ExtendedBackend, ExtendedConfigDataBackend
from .ModificationTracking import (
	BackendModificationListener,
	ModificationTrackingBackend,
)

__all__ = (
	"describeInterface",
	"Backend",
	"ExtendedBackend",
	"ConfigDataBackend",
	"ExtendedConfigDataBackend",
	"ModificationTrackingBackend",
	"BackendModificationListener",
)
