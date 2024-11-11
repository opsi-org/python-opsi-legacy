# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
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
