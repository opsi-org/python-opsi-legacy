# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Service functionality.
"""

import os

from OpenSSL import SSL
from opsicommon.logging import get_logger

from OPSI.Service.Session import SessionHandler

logger = get_logger("opsi.general")


class SSLContext(object):
	def __init__(self, sslServerKeyFile, sslServerCertFile, acceptedCiphers=""):
		"""
		Create a context for the usage of SSL in twisted.

		:param sslServerCertFile: Path to the certificate file.
		:type sslServerCertFile: str
		:param sslServerKeyFile: Path to the key file.
		:type sslServerKeyFile: str
		:param acceptedCiphers: A string defining what ciphers should \
be accepted. Please refer to the OpenSSL documentation on how such a \
string should be composed. No limitation will be done if an empty value \
is set.
		:type acceptedCiphers: str
		"""
		self._sslServerKeyFile = sslServerKeyFile
		self._sslServerCertFile = sslServerCertFile
		self._acceptedCiphers = acceptedCiphers

	def getContext(self):
		"""
		Get an SSL context.

		:rtype: OpenSSL.SSL.Context
		"""

		# Test if server certificate and key file exist.
		if not os.path.isfile(self._sslServerKeyFile):
			raise OSError(f"Server key file '{self._sslServerKeyFile}' does not exist!")

		if not os.path.isfile(self._sslServerCertFile):
			raise OSError(
				f"Server certificate file '{self._sslServerCertFile}' does not exist!"
			)

		context = SSL.Context(SSL.SSLv23_METHOD)
		context.use_privatekey_file(self._sslServerKeyFile)
		context.use_certificate_file(self._sslServerCertFile)

		if self._acceptedCiphers:
			context.set_cipher_list(self._acceptedCiphers)

		return context


class OpsiService(object):
	def __init__(self):
		self._sessionHandler = None

	def _getSessionHandler(self):
		if self._sessionHandler is None:
			self._sessionHandler = SessionHandler()
		return self._sessionHandler

	def getInterface(self):
		return {}
