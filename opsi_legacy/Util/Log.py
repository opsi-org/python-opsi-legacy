# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Utilities for working with logs.
"""

from opsi_legacy.Types import forceInt

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
