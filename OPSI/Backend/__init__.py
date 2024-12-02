# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
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
