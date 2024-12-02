# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
HostControl backend.

This backend can be used to control hosts.
"""

import ipaddress
import socket
import struct
import time
from contextlib import closing
from typing import Any, List

from opsicommon.client.opsiservice import ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import Host

from OPSI import __version__
from OPSI.Backend.Base import ExtendedBackend
from OPSI.Backend.Base.Backend import Backend
from OPSI.Exceptions import BackendMissingDataError, BackendUnaccomplishableError
from OPSI.Types import (
	forceBool,
	forceHostId,
	forceHostIdList,
	forceInt,
	forceIpAddress,
	forceList,
	forceUnicode,
)
from OPSI.Util.Thread import KillableThread

__all__ = ("RpcThread", "ConnectionThread", "HostControlBackend")

logger = get_logger("opsi.general")


class RpcThread(KillableThread):
	_USER_AGENT = f"opsi-RpcThread/{__version__}"

	def __init__(
		self,
		hostControlBackend: ExtendedBackend,
		hostId: str,
		address: str,
		username: str,
		password: str,
		method: str,
		params: List = None,
		hostPort: int = 0,
	) -> None:
		KillableThread.__init__(self)
		self.hostControlBackend = hostControlBackend
		self.hostId = forceHostId(hostId)
		self.method = forceUnicode(method)
		self.params = forceList(params or [])
		self.address = address
		self.error = None
		self.result = None
		self.started = 0
		self.ended = 0
		if hostPort:
			hostPort = forceInt(hostPort)
		else:
			hostPort = self.hostControlBackend._opsiclientdPort

		self.jsonrpc = ServiceClient(
			address=f"https://{self.address}:{hostPort}/opsiclientd",
			username=forceUnicode(username),
			password=forceUnicode(password),
			connect_timeout=max(self.hostControlBackend._hostRpcTimeout, 0),
			jsonrpc_create_objects=True,
			jsonrpc_create_methods=True,
		)

	def run(self) -> None:
		self.started = time.time()
		try:
			self.result = self.jsonrpc.execute_rpc(self.method, self.params)
		except Exception as err:
			self.error = str(err)
		finally:
			try:
				self.jsonrpc.disconnect()
			except Exception as err:
				logger.warning(
					"Failed to clean up jsonrpc connection: %s", err, exc_info=True
				)
			self.ended = time.time()


class ConnectionThread(KillableThread):
	def __init__(
		self, hostControlBackend: ExtendedBackend, hostId: str, address: str
	) -> None:
		KillableThread.__init__(self)
		self.hostControlBackend = hostControlBackend
		self.hostId = forceHostId(hostId)
		self.address = forceIpAddress(address)
		self.result = False
		self.started = 0
		self.ended = 0

	def run(self) -> None:
		self.started = time.time()
		timeout = max(self.hostControlBackend._hostReachableTimeout, 0)

		logger.info(
			"Trying connection to '%s:%d'",
			self.address,
			self.hostControlBackend._opsiclientdPort,
		)
		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(timeout)
			sock.connect((self.address, self.hostControlBackend._opsiclientdPort))
			self.result = True
			sock.shutdown(socket.SHUT_RDWR)
			sock.close()
		except Exception as err:
			logger.info(err, exc_info=True)
		self.ended = time.time()


class HostControlBackend(ExtendedBackend):
	def __init__(self, backend: Backend, **kwargs) -> None:
		self._name = "hostcontrol"

		ExtendedBackend.__init__(self, backend, **kwargs)

		self._opsiclientdPort = 4441
		self._hostRpcTimeout = 15
		self._hostReachableTimeout = 3
		self._resolveHostAddress = False
		self._maxConnections = 50
		self._broadcastAddresses = {}

		broadcastAddresses = {"0.0.0.0/0": {"255.255.255.255": [7, 9, 12287]}}

		for option, value in kwargs.items():
			option = option.lower()
			if option == "opsiclientdport":
				self._opsiclientdPort = forceInt(value)
			elif option == "hostrpctimeout":
				self._hostRpcTimeout = forceInt(value)
			elif option == "hostreachabletimeout":
				self._hostReachableTimeout = forceInt(value)
			elif option == "resolvehostaddress":
				self._resolveHostAddress = forceBool(value)
			elif option == "maxconnections":
				self._maxConnections = max(forceInt(value), 1)
			elif option == "broadcastaddresses" and value:
				broadcastAddresses = value

		self._set_broadcast_addresses(broadcastAddresses)

	def __repr__(self) -> str:
		try:
			return f"<{self.__class__.__name__}(resolveHostAddress={self._resolveHostAddress}, maxConnections={self._maxConnections})>"
		except AttributeError:
			# Can happen during initialisation
			return f"<{self.__class__.__name__}()>"

	def _set_broadcast_addresses(self, value: Any) -> None:
		self._broadcastAddresses = {}
		old_format = False
		if isinstance(value, list):
			old_format: True
			# Old format <list-broadcast-addresses>
			value = {"0.0.0.0/0": {addr: [7, 9, 12287] for addr in value}}

		elif not isinstance(list(value.values())[0], dict):
			old_format: True
			# Old format <broadcast-address>: <port-list>
			value = {"0.0.0.0/0": value}

		# New format <network-address>: <broadcast-address>: <port-list>
		for network_address, broadcast_addresses in value.items():
			net = ipaddress.ip_network(network_address)
			self._broadcastAddresses[net] = {}
			for broadcast_address, ports in broadcast_addresses.items():
				brd = ipaddress.ip_address(broadcast_address)
				self._broadcastAddresses[net][brd] = tuple(
					forceInt(port) for port in ports
				)

		if old_format:
			logger.warning(
				"Your hostcontrol backend configuration uses an old format for broadcast addresses. "
				"Please use the following new format:\n"
				'{ "<network-address>": { "<broadcast-address>": <port-list> } }\n'
				'Example: { "0.0.0.0/0": { "255.255.255.255": [7, 9, 12287] } }'
			)

	def _getHostAddress(self, host: str) -> str:
		address = None
		if self._resolveHostAddress:
			try:
				address = socket.gethostbyname(host.id)
			except socket.error as lookupError:
				logger.trace(
					"Failed to lookup ip address for %s: %s", host.id, lookupError
				)
		if not address:
			address = host.ipAddress
		if not address and not self._resolveHostAddress:
			try:
				address = socket.gethostbyname(host.id)
			except socket.error as err:
				raise BackendUnaccomplishableError(
					f"Failed to resolve ip address for host '{host.id}'"
				) from err
		if not address:
			raise BackendUnaccomplishableError(
				f"Failed to get ip address for host '{host.id}'"
			)
		return address

	def _opsiclientdRpc(
		self, hostIds: list[str], method: str, params: List = None, timeout: int = None
	):
		if not hostIds:
			raise BackendMissingDataError("No matching host ids found")
		hostIds = forceHostIdList(hostIds)
		method = forceUnicode(method)
		params = forceList(params or [])
		if not timeout:
			timeout = self._hostRpcTimeout
		timeout = forceInt(timeout)

		result = {}
		rpcts = []
		for host in self._context.host_getObjects(id=hostIds):
			try:
				port = None
				try:
					configState = self._context.configState_getObjects(
						configId="opsiclientd.control_server.port", objectId=host.id
					)
					port = int(configState[0].values[0])
					logger.info("Using port %s for opsiclientd at %s", port, host.id)
				except IndexError:
					pass  # No values found
				except Exception as err:
					logger.warning(
						"Failed to read custom opsiclientd port for %s: %s",
						host.id,
						err,
					)

				address = self._getHostAddress(host)
				if ":" in address:
					# IPv6
					address = f"[{address}]"
				logger.debug("Using address '%s' for host '%s'", address, host)
				rpcts.append(
					RpcThread(
						hostControlBackend=self,
						hostId=host.id,
						hostPort=port,
						address=address,
						username="",
						password=host.opsiHostKey,
						method=method,
						params=params,
					)
				)
			except Exception as err:
				result[host.id] = {"result": None, "error": str(err)}

		runningThreads = 0
		while rpcts:
			newRpcts = []
			for rpct in rpcts:
				if rpct.ended:
					if rpct.error:
						logger.info(
							"Rpc to host %s failed, error: %s", rpct.hostId, rpct.error
						)
						result[rpct.hostId] = {"result": None, "error": rpct.error}
					else:
						logger.info(
							"Rpc to host %s successful, result: %s",
							rpct.hostId,
							rpct.result,
						)
						result[rpct.hostId] = {"result": rpct.result, "error": None}
					runningThreads -= 1
					continue

				if not rpct.started:
					if runningThreads < self._maxConnections:
						logger.debug("Starting rpc to host %s", rpct.hostId)
						rpct.start()
						runningThreads += 1
				else:
					timeRunning = time.time() - rpct.started
					if timeRunning >= timeout + 5:
						# thread still alive 5 seconds after timeout => kill
						logger.info(
							"Rpc to host %s (address: %s) timed out after %0.2f seconds, terminating",
							rpct.hostId,
							rpct.address,
							timeRunning,
						)
						result[rpct.hostId] = {
							"result": None,
							"error": f"timed out after {timeRunning:0.2f} seconds",
						}
						if not rpct.ended:
							try:
								rpct.terminate()
							except Exception as err:
								logger.error("Failed to terminate rpc thread: %s", err)
						runningThreads -= 1
						continue
				newRpcts.append(rpct)
			rpcts = newRpcts
			time.sleep(0.1)

		return result

	def _get_broadcast_addresses_for_host(self, host: Host) -> Any:
		if not self._broadcastAddresses:
			return []

		networks = []
		if host.ipAddress:
			ip_address = ipaddress.ip_address(host.ipAddress)
			for ip_network in self._broadcastAddresses:
				if ip_address and ip_address in ip_network:
					networks.append(ip_network)

			if len(networks) > 1:
				# Take bets matching network by prefix length
				networks = [
					sorted(networks, key=lambda x: x.prefixlen, reverse=True)[0]
				]
			elif not networks:
				logger.debug(
					"No matching ip network found for host address '%s', using all broadcasts",
					ip_address.compressed,
				)
				networks = list(self._broadcastAddresses)
		else:
			networks = list(self._broadcastAddresses)

		for network in networks:
			for broadcast, ports in self._broadcastAddresses[network].items():
				yield (broadcast.compressed, ports)

	def hostControl_start(self, hostIds: list[str] = None) -> dict[str, Any]:
		"""Switches on remote computers using WOL."""
		hosts = self._context.host_getObjects(
			attributes=["hardwareAddress", "ipAddress"], id=hostIds or []
		)
		result = {}
		for host in hosts:
			try:
				if not host.hardwareAddress:
					raise BackendMissingDataError(
						f"Failed to get hardware address for host '{host.id}'"
					)

				mac = host.hardwareAddress.replace(":", "")
				data = b"".join(
					[b"FFFFFFFFFFFF", mac.encode("ascii") * 16]
				)  # Pad the synchronization stream.

				# Split up the hex values and pack.
				payload = b""
				for i in range(0, len(data), 2):
					payload = b"".join(
						[payload, struct.pack("B", int(data[i : i + 2], 16))]
					)

				for (
					broadcast_address,
					target_ports,
				) in self._get_broadcast_addresses_for_host(host):
					logger.debug(
						"Sending data to network broadcast %s %s [%s]",
						broadcast_address,
						target_ports,
						data,
					)

					for port in target_ports:
						logger.debug("Broadcasting to port %s", port)
						with closing(
							socket.socket(
								socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
							)
						) as sock:
							sock.setsockopt(
								socket.SOL_SOCKET, socket.SO_BROADCAST, True
							)
							sock.sendto(payload, (broadcast_address, port))

				result[host.id] = {"result": "sent", "error": None}
			except Exception as err:
				logger.debug(err, exc_info=True)
				result[host.id] = {"result": None, "error": str(err)}
		return result

	def hostControl_shutdown(self, hostIds: list[str] = None) -> dict[str, Any]:
		if not hostIds:
			raise BackendMissingDataError("No host ids given")
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(hostIds=hostIds, method="shutdown", params=[])

	def hostControl_reboot(self, hostIds: list[str] = None) -> dict[str, Any]:
		if not hostIds:
			raise BackendMissingDataError("No host ids given")
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(hostIds=hostIds, method="reboot", params=[])

	def hostControl_fireEvent(
		self, event: str, hostIds: list[str] = None
	) -> dict[str, Any]:
		event = forceUnicode(event)
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(hostIds=hostIds, method="fireEvent", params=[event])

	def hostControl_showPopup(
		self,
		message: str,
		hostIds: list[str] = None,
		mode: str = "prepend",
		addTimestamp: bool = True,
		displaySeconds: float = None,
	) -> dict[str, Any]:
		"""
		This rpc-call creates a popup-Window with a message on given clients.

		:param message: The message to be displayed.
		:param hostIds: A list of hosts to show the message on.
		:param mode: Where to put message in relation to previous messages (prepend or append).
		:param addTimestamp: Whether to add the current timestamp to the message.
		:param displaySeconds: Number of seconds to show the message for (default None = intinity or until manually closed).
		:return: Dictionary containing the result of the rpc-call
		"""
		message = forceUnicode(message)
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		params = [message, mode, addTimestamp]
		if displaySeconds is not None:
			params.append(forceInt(displaySeconds))
		return self._opsiclientdRpc(hostIds=hostIds, method="showPopup", params=params)

	def hostControl_uptime(self, hostIds: list[str] = None) -> dict[str, Any]:
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(hostIds=hostIds, method="uptime", params=[])

	def hostControl_getActiveSessions(
		self, hostIds: list[str] = None
	) -> dict[str, Any]:
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(
			hostIds=hostIds, method="getActiveSessions", params=[]
		)

	def hostControl_opsiclientdRpc(
		self,
		method: str,
		params: list[Any] = None,
		hostIds: list[str] = None,
		timeout: int = None,
	) -> dict[str, Any]:
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		return self._opsiclientdRpc(
			hostIds=hostIds, method=method, params=params or [], timeout=timeout
		)

	def hostControl_reachable(
		self, hostIds: list[str] = None, timeout: int = None
	) -> dict[str, Any]:
		hostIds = self._context.host_getIdents(id=hostIds or [], returnType="unicode")
		if not hostIds:
			raise BackendMissingDataError("No matching host ids found")
		hostIds = forceHostIdList(hostIds)

		if not timeout:
			timeout = self._hostReachableTimeout
		timeout = forceInt(timeout)

		result = {}
		threads = []
		for host in self._context.host_getObjects(id=hostIds):
			try:
				address = self._getHostAddress(host)
				threads.append(
					ConnectionThread(
						hostControlBackend=self, hostId=host.id, address=address
					)
				)
			except Exception as err:
				logger.debug("Problem found: '%s'", err)
				result[host.id] = False

		runningThreads = 0
		while threads:
			newThreads = []
			for thread in threads:
				if thread.ended:
					result[thread.hostId] = thread.result
					runningThreads -= 1
					continue

				if not thread.started:
					if runningThreads < self._maxConnections:
						logger.debug("Trying to check host reachable %s", thread.hostId)
						thread.start()
						runningThreads += 1
				else:
					timeRunning = time.time() - thread.started
					if timeRunning >= timeout + 5:
						# thread still alive 5 seconds after timeout => kill
						logger.error(
							"Reachable check to host %s address %s timed out after %0.2f seconds, terminating",
							thread.hostId,
							thread.address,
							timeRunning,
						)
						result[thread.hostId] = False
						if not thread.ended:
							try:
								thread.terminate()
							except Exception as err:
								logger.error(
									"Failed to terminate reachable thread: %s", err
								)
						runningThreads -= 1
						continue
				newThreads.append(thread)
			threads = newThreads
			time.sleep(0.1)
		return result

	def hostControl_execute(
		self,
		command: str,
		hostIds: list[str] = None,
		waitForEnding: bool = True,
		captureStderr: bool = True,
		encoding: str = None,
		timeout: int = 300,
	) -> dict[str, Any]:
		command = forceUnicode(command)
		hostIds = self._context.host_getIdents(id=hostIds, returnType="unicode")
		return self._opsiclientdRpc(
			hostIds=hostIds,
			method="execute",
			params=[command, waitForEnding, captureStderr, encoding, timeout],
		)
