# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
JSONRPC backend.

This backend executes the calls on a remote backend via JSONRPC.
"""

from __future__ import annotations

from threading import Event
from typing import Any
from urllib.parse import urlparse

from opsicommon.client.opsiservice import ServiceClient, ServiceConnectionListener
from opsicommon.logging import get_logger

from OPSI import __version__
from OPSI.Backend.Base import Backend

logger = get_logger("opsi.general")

__all__ = ("JSONRPCBackend",)


class JSONRPCBackend(Backend, ServiceConnectionListener):
	"""
	This Backend gives remote access to a Backend reachable via jsonrpc.
	"""

	def __init__(self, address: str, **kwargs: Any) -> None:
		"""
		Backend for JSON-RPC access to another opsi service.

		:param compression: Should requests be compressed?
		:type compression: bool
		"""

		self._name = "jsonrpc"
		self._connection_result_event = Event()
		self._connection_error: Exception | None = None

		Backend.__init__(self, **kwargs)  # type: ignore[misc]

		connect_on_init = True
		service_args = {
			"address": address,
			"user_agent": f"opsi-jsonrpc-backend/{__version__}",
			"verify": "accept_all",
			"jsonrpc_create_objects": True,
			"jsonrpc_create_methods": True,
		}
		for option, value in kwargs.items():
			option = option.lower().replace("_", "")
			if option == "username":
				service_args["username"] = str(value or "")
			elif option == "password":
				service_args["password"] = str(value or "")
			elif option == "cacertfile":
				if value not in (None, ""):
					service_args["ca_cert_file"] = str(value)
			elif option == "verifyservercert":
				if value:
					service_args["verify"] = ["opsi_ca", "uib_opsi_ca"]
				else:
					service_args["verify"] = "accept_all"
			elif option == "verify":
				service_args["verify"] = value
			elif option == "sessionid":
				if value:
					service_args["session_cookie"] = str(value)
			elif option == "sessionlifetime":
				if value:
					service_args["session_lifetime"] = int(value)
			elif option == "proxyurl":
				service_args["proxy_url"] = str(value) if value else None
			elif option == "application":
				service_args["user_agent"] = str(value)
			elif option == "connecttimeout":
				service_args["connect_timeout"] = int(value)
			elif option == "connectoninit":
				connect_on_init = bool(value)

		self.service = ServiceClient(**service_args)
		self.service.register_connection_listener(self)
		if connect_on_init:
			self.service.connect()
			self._connection_result_event.wait()
			if self._connection_error:
				raise self._connection_error

	@property
	def hostname(self) -> str:
		return urlparse(self.service.base_url).hostname

	def connection_established(self, service_client: ServiceClient) -> None:
		self.service.create_jsonrpc_methods(self)
		self._connection_error = None
		self._connection_result_event.set()

	def connection_failed(
		self, service_client: ServiceClient, exception: Exception
	) -> None:
		self._connection_error = exception
		self._connection_result_event.set()
