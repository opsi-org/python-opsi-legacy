# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Basic backend.

This holds the basic backend classes.
"""

import threading
from contextlib import contextmanager
from typing import Any, Callable

from .Base import (
	Backend,
	BackendModificationListener,
	ConfigDataBackend,
	ExtendedBackend,
	ExtendedConfigDataBackend,
	ModificationTrackingBackend,
	describeInterface,
)

__all__ = (
	"describeInterface",
	"temporaryBackendOptions",
	"DeferredCall",
	"Backend",
	"ExtendedBackend",
	"ConfigDataBackend",
	"ExtendedConfigDataBackend",
	"ModificationTrackingBackend",
	"BackendModificationListener",
)


@contextmanager
def temporaryBackendOptions(backend: Backend, **options) -> None:
	oldOptions = backend.backend_getOptions()
	try:
		backend.backend_setOptions(options)
		yield
	finally:
		backend.backend_setOptions(oldOptions)


class DeferredCall:
	def __init__(self, callback: Callable = None) -> None:
		self.error = None
		self.result = None
		self.finished = threading.Event()
		self.callback = callback
		self.callbackArgs = []
		self.callbackKwargs = {}

	def waitForResult(self) -> Any:
		self.finished.wait()
		if self.error:
			raise self.error  # pylint: disable=raising-bad-type
		return self.result

	def setCallback(self, callback: Callable, *args, **kwargs) -> None:
		self.callback = callback
		self.callbackArgs = args
		self.callbackKwargs = kwargs

	def _gotResult(self) -> None:
		self.finished.set()
		if self.callback:
			self.callback(self, *self.callbackArgs, **self.callbackKwargs)
