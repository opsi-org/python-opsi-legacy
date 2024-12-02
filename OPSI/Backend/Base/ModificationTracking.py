# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend that tracks modifications.
"""

from opsicommon.logging import get_logger

from .Extended import ExtendedBackend

__all__ = ("ModificationTrackingBackend", "BackendModificationListener")


logger = get_logger("opsi.general")


class ModificationTrackingBackend(ExtendedBackend):
	def __init__(self, backend, overwrite=True):
		ExtendedBackend.__init__(self, backend, overwrite=overwrite)
		self._createInstanceMethods()
		self._backendChangeListeners = []

	def addBackendChangeListener(self, backendChangeListener):
		if backendChangeListener in self._backendChangeListeners:
			return
		self._backendChangeListeners.append(backendChangeListener)

	def removeBackendChangeListener(self, backendChangeListener):
		if backendChangeListener not in self._backendChangeListeners:
			return
		self._backendChangeListeners.remove(backendChangeListener)

	def _fireEvent(self, event, *args):
		for bcl in self._backendChangeListeners:
			try:
				meth = getattr(bcl, event)
				meth(self, *args)
			except Exception as err:
				logger.error(err)

	def _executeMethod(self, methodName, **kwargs):
		logger.debug(
			"ModificationTrackingBackend %s: executing %s on backend %s",
			self,
			methodName,
			self._backend,
		)
		meth = getattr(self._backend, methodName)
		result = meth(**kwargs)
		action = None
		if "_" in methodName:
			action = methodName.split("_", 1)[1]

		if action in ("insertObject", "updateObject", "deleteObjects"):
			value = list(kwargs.values())[0]
			if action == "insertObject":
				self._fireEvent("objectInserted", value)
			elif action == "updateObject":
				self._fireEvent("objectUpdated", value)
			elif action == "deleteObjects":
				self._fireEvent("objectsDeleted", value)
			self._fireEvent("backendModified")

		return result


class BackendModificationListener:
	def objectInserted(self, backend, obj):
		# Should return immediately!
		pass

	def objectUpdated(self, backend, obj):
		# Should return immediately!
		pass

	def objectsDeleted(self, backend, objs):
		# Should return immediately!
		pass

	def backendModified(self, backend):
		# Should return immediately!
		pass
