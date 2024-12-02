# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Helpers for testing opsi.
"""

import os
import shutil
import tempfile
from contextlib import contextmanager
from unittest import mock

from OPSI.Util.Path import cd


@contextmanager
def workInTemporaryDirectory(tempDir=None):
	"""
	Creates a temporary folder to work in. Deletes the folder afterwards.

	:param tempDir: use the given dir as temporary directory. Will not \
be deleted if given.
	"""
	temporary_folder = tempDir or tempfile.mkdtemp()
	with cd(temporary_folder):
		try:
			yield temporary_folder
		finally:
			if not tempDir:
				try:
					shutil.rmtree(temporary_folder)
				except OSError:
					pass


@contextmanager
def createTemporaryTestfile(original, tempDir=None):
	"""Copy `original` to a temporary directory and \
yield the path to the new file.

	The temporary directory can be specified overridden with `tempDir`."""

	with workInTemporaryDirectory(tempDir) as targetDir:
		shutil.copy(original, targetDir)

		filename = os.path.basename(original)

		yield os.path.join(targetDir, filename)


def getLocalFQDN():
	"Get the FQDN of the local machine."
	# Lazy imports to not hinder other tests.
	from OPSI.Types import forceHostId
	from OPSI.Util import getfqdn

	return forceHostId(getfqdn())


@contextmanager
def patchAddress(fqdn="opsi.test.invalid", address="172.16.0.1"):
	"""
	Modify the results of socket so that expected addresses are returned.

	:param fqdn: The FQDN to use. Everything before the first '.' will serve\
as hostname.
	:param address: The IP address to use.
	"""
	hostname = fqdn.split(".")[0]

	def getfqdn(*_):
		return fqdn

	def gethostbyaddr(*_):
		return (fqdn, [hostname], [address])

	with mock.patch("socket.getfqdn", getfqdn):
		with mock.patch("socket.gethostbyaddr", gethostbyaddr):
			yield


@contextmanager
def patchEnvironmentVariables(**environmentVariables):
	"""
	Patches to environment variables to be empty during the context.
	Anything supplied as keyword argument will be added to the environment.
	"""
	originalEnv = os.environ.copy()
	try:
		os.environ.clear()
		for key, value in environmentVariables.items():
			os.environ[key] = value

		yield
	finally:
		os.environ = originalEnv


@contextmanager
def fakeGlobalConf(fqdn="opsi.test.invalid", dir=None):
	"Fake a global.conf and return the path to the file."

	with workInTemporaryDirectory(dir) as tempDir:
		configPath = os.path.join(tempDir, "global.conf")

		with open(configPath, "w", encoding="utf-8") as conf:
			conf.write("[global]\n")
			conf.write(f"hostname = {fqdn}\n")
		yield configPath
