# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Basic backend.

This holds the basic backend classes.
"""

import threading
from contextlib import contextmanager

from .Base import describeInterface, Backend
from .Base import ConfigDataBackend
from .Base import getArgAndCallString, ExtendedBackend, ExtendedConfigDataBackend
from .Base import ModificationTrackingBackend, BackendModificationListener

__all__ = (
	'describeInterface', 'getArgAndCallString', 'temporaryBackendOptions',
	'DeferredCall', 'Backend', 'ExtendedBackend', 'ConfigDataBackend',
	'ExtendedConfigDataBackend',
	'ModificationTrackingBackend', 'BackendModificationListener'
)


@contextmanager
def temporaryBackendOptions(backend, **options):
	oldOptions = backend.backend_getOptions()
	try:
		backend.backend_setOptions(options)
		yield
	finally:
		backend.backend_setOptions(oldOptions)


class DeferredCall:
	def __init__(self, callback=None):
		self.error = None
		self.result = None
		self.finished = threading.Event()
		self.callback = callback
		self.callbackArgs = []
		self.callbackKwargs = {}

	def waitForResult(self):
		self.finished.wait()
		if self.error:
			raise self.error  # pylint: disable=raising-bad-type
		return self.result

	def setCallback(self, callback, *args, **kwargs):
		self.callback = callback
		self.callbackArgs = args
		self.callbackKwargs = kwargs

	def _gotResult(self):
		self.finished.set()
		if self.callback:
			self.callback(self, *self.callbackArgs, **self.callbackKwargs)
