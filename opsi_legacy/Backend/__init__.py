# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Backends.
"""

import functools
from typing import Callable


def no_export(func: Callable) -> Callable:
	func.no_export = True
	return func


def deprecated(
	func: Callable = None, *, alternative_method: Callable = None
) -> Callable:
	if func is None:
		return functools.partial(deprecated, alternative_method=alternative_method)

	func.deprecated = True
	func.alternative_method = alternative_method
	return func

	# @functools.wraps(func)
	# def wrapper(*args, **kwargs):
	# 	logger.warning("Deprecated")
	# 	return func(*args, **kwargs)
	# return wrapper
