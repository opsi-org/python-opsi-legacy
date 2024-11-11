# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Support for JSON-RPC.

Information about the JSON-RPC standard can be found at
http://www.jsonrpc.org/specification
"""

import sys
import time
import traceback

from opsicommon.exceptions import OpsiBadRpcError, OpsiRpcError
from opsicommon.logging import get_logger
from opsicommon.objects import deserialize
from opsicommon.types import forceUnicode

logger = get_logger("opsi.general")


class JsonRpc:  # pylint: disable=too-many-instance-attributes
	def __init__(self, instance, interface, rpc):
		self._instance = instance
		self._interface = interface
		self.started = None
		self.ended = None
		self.type = rpc.get("type")
		self.rpcVersion = rpc.get("jsonrpc", None)
		self.tid = rpc.get("tid", rpc.get("id"))
		self.action = rpc.get("action")
		self.method = rpc.get("method")
		self.params = rpc.get("params", rpc.get("data")) or []
		self.result = None
		self.exception = None
		self.traceback = None

		if not self.tid:
			raise OpsiBadRpcError("No transaction id ((t)id) found in rpc")

		if not self.method:
			raise OpsiBadRpcError("No method found in rpc")

	def isStarted(self):
		return bool(self.started)

	def hasEnded(self):
		return bool(self.ended)

	def getMethodName(self):
		if self.action:
			return f"{self.action}_{self.method}"

		return self.method

	def getDuration(self):
		if not self.started or not self.ended:
			return None

		return round(self.ended - self.started, 3)

	def execute(self, result=None):  # pylint: disable=unused-argument,too-many-locals,too-many-branches,too-many-statements
		self.result = None
		params = list(self.params)
		self.started = time.time()

		try:
			methodName = self.getMethodName()
			for method in self._interface:
				if methodName == method["name"]:
					methodInterface = method
					break
			else:
				methodInterface = None

			if not methodInterface:
				raise OpsiRpcError(f"Method '{methodName}' is not valid")

			keywords = {}
			if methodInterface["keywords"]:
				parameterCount = 0
				if methodInterface["args"]:
					parameterCount += len(methodInterface["args"])
				if methodInterface["varargs"]:
					parameterCount += len(methodInterface["varargs"])

				if len(params) >= parameterCount:
					kwargs = params.pop(-1)
					if not isinstance(kwargs, dict):
						raise TypeError(f"kwargs param is not a dict: {params[-1]}")

					for key, value in kwargs.items():
						keywords[str(key)] = deserialize(value)

				del parameterCount

			params = deserialize(params)

			pString = forceUnicode(params)[1:-1]
			if keywords:
				pString = f"{pString}, {keywords}"

			if len(pString) > 200:
				pString = f"{pString[:200]}..."

			logger.notice("-----> Executing: %s(%s)", methodName, pString)

			method = getattr(self._instance, methodName)
			if keywords:
				self.result = method(*params, **keywords)
			else:
				self.result = method(*params)

			logger.info("Got result for %s", methodName)
			logger.trace("RPC ID %s: %s", self.tid, self.result)
		except Exception as err:  # pylint: disable=broad-except
			logger.info(err, exc_info=True)
			logger.error("Execution error: %s", err)
			self.exception = err
			self.traceback = []
			try:
				for tbInfo in traceback.format_tb(sys.exc_info()[2]):
					self.traceback.append(tbInfo)
			except AttributeError as error:
				message = f"Failed to collect traceback: {error}"
				logger.warning(message)
				self.traceback.append(message)
		finally:
			self.ended = time.time()

	def getResponse(self):
		response = {}
		if self.type == "rpc":
			response["tid"] = self.tid
			response["action"] = self.action
			response["method"] = self.method
			if self.exception:
				response["type"] = "exception"
				response["message"] = {
					"class": self.exception.__class__.__name__,
					"message": forceUnicode(self.exception),
				}
				response["where"] = self.traceback
			else:
				response["type"] = "rpc"
				response["result"] = self.result
		else:
			response["id"] = self.tid
			if self.rpcVersion == "2.0":
				response["jsonrpc"] = "2.0"

			if self.exception:
				if self.rpcVersion == "2.0":
					try:
						code = int(getattr(self.exception, "errno"))
					except Exception:  # pylint: disable=broad-except
						code = 0

					response["error"] = {
						"code": code,
						"message": forceUnicode(self.exception),
						"data": {"class": self.exception.__class__.__name__},
					}
				else:
					response["error"] = {
						"class": self.exception.__class__.__name__,
						"message": forceUnicode(self.exception),
					}

				if self.rpcVersion != "2.0":
					response["result"] = None
			else:
				if self.rpcVersion != "2.0":
					response["error"] = None
				response["result"] = self.result

		return response

	def __getstate__(self):
		state = self.__dict__
		state["_instance"] = None
		state["_interface"] = None
		return state
