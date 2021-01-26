# -*- coding: utf-8 -*-

# This module is part of the desktop management solution opsi
# (open pc server integration) http://www.opsi.org

# Copyright (C) 2013-2018 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Backend that tracks modifications.

:copyright: uib GmbH <info@uib.de>
:license: GNU Affero General Public License version 3
"""

from OPSI.Logger import Logger
from .Extended import ExtendedBackend

__all__ = (
	'ModificationTrackingBackend', 'BackendModificationListener'
)

logger = Logger()


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
			except Exception as err:  # pylint: disable=broad-except
				logger.error(err)

	def _executeMethod(self, methodName, **kwargs):
		logger.debug(
			"ModificationTrackingBackend %s: executing %s on backend %s",
			self, methodName, self._backend
		)
		meth = getattr(self._backend, methodName)
		result = meth(**kwargs)
		action = None
		if '_' in methodName:
			action = methodName.split('_', 1)[1]

		if action in ('insertObject', 'updateObject', 'deleteObjects'):
			value = list(kwargs.values())[0]
			if action == 'insertObject':
				self._fireEvent('objectInserted', value)
			elif action == 'updateObject':
				self._fireEvent('objectUpdated', value)
			elif action == 'deleteObjects':
				self._fireEvent('objectsDeleted', value)
			self._fireEvent('backendModified')

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
