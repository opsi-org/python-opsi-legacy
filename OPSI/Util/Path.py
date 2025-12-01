# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Functionality to work with paths.
"""

import os
from contextlib import contextmanager


@contextmanager
def cd(path: str):
	"Change the current directory to `path` as long as the context exists."

	currentDir = os.getcwd()
	os.chdir(path)
	try:
		yield
	finally:
		os.chdir(currentDir)
