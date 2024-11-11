# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Util.HTTP
"""

import gzip
import zlib
from urllib.parse import urlparse


def urlsplit(url):
	_url = urlparse(url)
	if _url.hostname is None:
		return (None, _url.path, None, None, None, None)
	return (
		_url.scheme,
		_url.hostname,
		_url.port,
		_url.path,
		_url.username,
		_url.password,
	)


def deflateEncode(data, level=1):
	"""
	Compress data with deflate.

	:type data: str
	:type level: int
	:param level: Compression level
	:rtype: bytes
	"""
	if not isinstance(data, bytes):
		data = data.encode()
	return zlib.compress(data, level)


def deflateDecode(data):
	"""
	Decompress data with deflate.

	:type data: bytes
	:rtype: str
	"""
	return zlib.decompress(data)


def gzipEncode(data, level=1):
	"""
	Compress data with gzip.

	:type data: str
	:type level: int
	:param level: Compression level
	:rtype: bytes
	"""
	if not isinstance(data, bytes):
		data = data.encode()
	return gzip.compress(data, level)


def gzipDecode(data):
	"""
	Decompress data with gzip.

	:type data: bytes
	:rtype: str
	"""
	return gzip.decompress(data)
