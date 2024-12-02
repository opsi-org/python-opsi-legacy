# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Utilities for working with logs.
"""

from OPSI.Types import forceInt

__all__ = ("truncateLogData",)


def truncateLogData(data, maxSize):
	"""
	Truncating `data` to not be longer than `maxSize` chars.

	:param data: Text
	:type data: str
	:param maxSize: The maximum size that is allowed in chars.
	:type maxSize: int
	"""
	maxSize = forceInt(maxSize)
	dataLength = len(data)
	if dataLength > maxSize:
		start = data.find("\n", dataLength - maxSize)
		if start == -1:
			start = dataLength - maxSize
		return data[start:].lstrip()

	return data
