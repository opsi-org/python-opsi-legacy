# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Resource
"""

from opsicommon.logging import get_logger
from twisted.internet import defer
from twisted.web import resource, server

from OPSI.Service.Worker import WorkerOpsi, WorkerOpsiJsonInterface, WorkerOpsiJsonRpc

logger = get_logger("opsi.general")


class ResourceOpsi(resource.Resource):
	WorkerClass = WorkerOpsi
	isLeaf = True

	def __init__(self, service):
		resource.Resource.__init__(self)
		self._service = service

	def checkPrivileges(
		self, request, privileges, recurse=False, principal=None, inherited_aces=None
	):  # pylint: disable=unused-argument
		deferred = defer.Deferred()
		deferred.callback(None)
		return deferred

	def isCollection(self):
		return not self.isLeaf

	def hasProperty(self, property, request):  # pylint: disable=unused-argument,redefined-builtin
		deferred = defer.Deferred()
		deferred.callback(None)
		return deferred

	def render(self, request):
		"""Process request."""
		try:
			logger.trace("%s.render()", self.__class__.__name__)
			if not self.WorkerClass:
				raise RuntimeError(
					f"No worker class defined in resource {self.__class__.__name__}"
				)
			worker = self.WorkerClass(self._service, request, self)
			worker.process()
			return server.NOT_DONE_YET
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)


class ResourceOpsiJsonRpc(ResourceOpsi):
	WorkerClass = WorkerOpsiJsonRpc
	isLeaf = False

	def __init__(self, service):
		ResourceOpsi.__init__(self, service)

	def locateChild(self, request, segments):  # pylint: disable=unused-argument
		return self, server.StopTraversal  # pylint: disable=no-member


class ResourceOpsiJsonInterface(ResourceOpsiJsonRpc):
	WorkerClass = WorkerOpsiJsonInterface

	def __init__(self, service):  # pylint: disable=super-init-not-called
		ResourceOpsi.__init__(self, service)  # pylint: disable=non-parent-init-called
		self._interface = service.getInterface()
