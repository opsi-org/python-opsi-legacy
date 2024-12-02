# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
DHCPD Backend.

This backend works edits the configuration of the DHCPD and restarts
the daemon afterwards.
"""

import fcntl
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Callable, Generator

from opsicommon.logging import get_logger, secret_filter

from OPSI import System
from OPSI.Backend.Base import ConfigDataBackend
from OPSI.Backend.Base.Backend import Backend
from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Exceptions import (
	BackendBadValueError,
	BackendIOError,
	BackendMissingDataError,
	BackendUnableToConnectError,
	BackendUnaccomplishableError,
)
from OPSI.Object import ConfigState, Host, OpsiClient
from OPSI.Types import forceBool, forceDict, forceHostId, forceObjectClass
from OPSI.Util import getfqdn
from OPSI.Util.File import DHCPDConfFile

__all__ = ("DHCPDBackend",)

WAIT_AFTER_RELOAD = 4.0

logger = get_logger("opsi.general")


@contextmanager
def dhcpd_lock(lock_type: str = "") -> Generator[None, None, None]:
	lock_file = "/var/lock/opsi-dhcpd-lock"
	with open(lock_file, "a+", encoding="utf8") as lock_fh:
		try:
			os.chmod(lock_file, 0o666)
		except PermissionError:
			pass
		attempt = 0
		while True:
			attempt += 1
			try:
				fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
				break
			except IOError:
				if attempt > 200:
					raise
				time.sleep(0.1)
		lock_fh.seek(0)
		lines = lock_fh.readlines()
		if len(lines) >= 100:
			lines = lines[-100:]
		lines.append(
			f"{time.time()};{os.path.basename(sys.argv[0])};{os.getpid()};{lock_type}\n"
		)
		lock_fh.seek(0)
		lock_fh.truncate()
		lock_fh.writelines(lines)
		lock_fh.flush()
		yield None
		if lock_type == "config_reload":
			time.sleep(WAIT_AFTER_RELOAD)
		fcntl.flock(lock_fh, fcntl.LOCK_UN)
	# os.remove(lock_file)


class DHCPDBackend(ConfigDataBackend):
	"""This Backend holds information for DHCP functionality"""

	def __init__(self, **kwargs) -> None:
		self._name = "dhcpd"

		ConfigDataBackend.__init__(self, **kwargs)
		self._dhcpdConfigFile = System.Posix.locateDHCPDConfig("/etc/dhcp3/dhcpd.conf")
		self._reloadConfigCommand = None
		self._fixedAddressFormat = "IP"
		next_server = None
		for addr in socket.gethostbyname_ex(getfqdn())[2]:
			next_server = addr
			if not addr.startswith("127"):
				break

		self._defaultClientParameters = {
			"next-server": next_server,
			"filename": "linux/pxelinux.0",
		}
		self._dhcpdOnDepot = False

		# Parse arguments
		for option, value in kwargs.items():
			option = option.lower()
			if option == "dhcpdconfigfile":
				self._dhcpdConfigFile = value
			elif option == "reloadconfigcommand":
				self._reloadConfigCommand = value
			elif option == "defaultclientparameters":
				self._defaultClientParameters = forceDict(value)
			elif option == "fixedaddressformat":
				if value not in ("IP", "FQDN"):
					raise BackendBadValueError(
						f"Bad value {value!r} for fixedAddressFormat, possible values are IP and FQDN"
					)
				self._fixedAddressFormat = value
			elif option == "dhcpdondepot":
				self._dhcpdOnDepot = forceBool(value)

		if self._defaultClientParameters.get(
			"next-server"
		) and self._defaultClientParameters["next-server"].startswith("127"):
			raise BackendBadValueError(
				f"Refusing to use ip address {self._defaultClientParameters['next-server']!r} as default next-server"
			)

		self._dhcpdConfFile = DHCPDConfFile(self._dhcpdConfigFile)
		self._reloadThread = None
		self._depotId = forceHostId(getfqdn())
		self._opsiHostKey = None
		self._depotConnections = {}

	def _get_opsi_host_key(self, backend: Backend = None) -> None:
		if backend is None:
			backend = self._context
		depots = backend.host_getObjects(id=self._depotId)
		if not depots or not depots[0].getOpsiHostKey():
			raise BackendMissingDataError(
				f"Failed to get opsi host key for depot '{self._depotId}'"
			)
		self._opsiHostKey = depots[0].getOpsiHostKey()
		secret_filter.add_secrets(self._opsiHostKey)

	def _init_backend(self, config_data_backend: Backend) -> None:
		try:
			self._get_opsi_host_key(config_data_backend)
		except Exception as err:
			# This can fail if backend is not yet initialized, continue!
			logger.info(err)

	def _startReloadThread(self) -> None:
		class ReloadThread(threading.Thread):
			"""This class implements a thread regularly reloading the dhcpd.conf file."""

			def __init__(self, reloadConfigCommand: Callable) -> None:
				threading.Thread.__init__(self)
				self._reloadConfigCommand = reloadConfigCommand
				self._reloadEvent = threading.Event()
				self._isReloading = False
				if not self._reloadConfigCommand:
					self._reloadConfigCommand = f"/usr/bin/sudo {System.Posix.getDHCPDRestartCommand(default='/etc/init.d/dhcp3-server restart')}"

			@property
			def isBusy(self) -> bool:
				return self._isReloading or self._reloadEvent.is_set()

			def triggerReload(self) -> None:
				"""Explicitely call a config file reload."""
				logger.debug("Reload triggered")
				if not self._reloadEvent.is_set():
					self._reloadEvent.set()

			def run(self) -> None:
				while True:
					if self._reloadEvent.wait(WAIT_AFTER_RELOAD):
						with dhcpd_lock("config_reload"):
							self._isReloading = True
							self._reloadEvent.clear()
							try:
								logger.notice(
									"Reloading dhcpd config using command: '%s'",
									self._reloadConfigCommand,
								)
								result = System.execute(self._reloadConfigCommand)
								for line in result:
									if "error" in line:
										raise RuntimeError("\n".join(result))
							except Exception as err:
								logger.critical(
									"Failed to reload dhcpd config: %s", err
								)
							self._isReloading = False

		self._reloadThread = ReloadThread(self._reloadConfigCommand)
		self._reloadThread.daemon = True
		self._reloadThread.start()

	def _triggerReload(self) -> None:
		if not self._reloadThread:
			self._startReloadThread()
		self._reloadThread.triggerReload()

	def _getDepotConnection(self, depotId: str) -> Backend:
		depotId = forceHostId(depotId)
		if depotId == self._depotId:
			return self

		if depotId not in self._depotConnections:
			try:
				if not self._opsiHostKey:
					self._get_opsi_host_key()
				self._depotConnections[depotId] = JSONRPCBackend(
					address=f"https://{depotId}:4447/rpc/backend/dhcpd",
					username=self._depotId,
					password=self._opsiHostKey,
				)
			except Exception as err:
				raise BackendUnableToConnectError(
					f"Failed to connect to depot '{depotId}': {err}"
				) from err
		return self._depotConnections[depotId]

	def _getResponsibleDepotId(self, clientId: str) -> str:
		"""This method returns the depot a client is assigned to."""
		configStates = self._context.configState_getObjects(
			configId="clientconfig.depot.id", objectId=clientId
		)
		try:
			depotId = configStates[0].values[0]
		except IndexError as err:
			configs = self._context.config_getObjects(id="clientconfig.depot.id")
			if not configs or not configs[0].defaultValues:
				raise BackendUnaccomplishableError(
					f"Failed to get depotserver for client '{clientId}', config 'clientconfig.depot.id' not set and no defaults found"
				) from err
			depotId = configs[0].defaultValues[0]

		return depotId

	def backend_exit(self) -> None:
		if self._reloadThread:
			logger.info("Waiting for reload thread")
			for _i in range(10):
				if self._reloadThread.isBusy:
					time.sleep(1)

	def _dhcpd_updateHost(self, host: Host) -> Any:
		host = forceObjectClass(host, Host)

		if self._dhcpdOnDepot:
			depotId = self._getResponsibleDepotId(host.id)
			if depotId != self._depotId:
				logger.info(
					"Not responsible for client '%s', forwarding request to depot '%s'",
					host.id,
					depotId,
				)
				return self._getDepotConnection(depotId).dhcpd_updateHost(host)
		return self.dhcpd_updateHost(host)

	def dhcpd_updateHost(self, host: Host) -> None:
		host = forceObjectClass(host, Host)

		if not host.hardwareAddress:
			logger.warning(
				"Cannot update dhcpd configuration for client %s: hardware address unknown",
				host,
			)
			return

		hostname = _getHostname(host.id)

		ipAddress = host.ipAddress
		if not ipAddress:
			try:
				logger.info(
					"Ip addess of client %s unknown, trying to get host by name", host
				)
				ipAddress = socket.gethostbyname(host.id)
				logger.info("Client fqdn resolved to %s", ipAddress)
			except Exception as err:
				logger.debug("Failed to get IP by hostname: %s", err)
				with dhcpd_lock("config_read"):
					self._dhcpdConfFile.parse()
					currentHostParams = self._dhcpdConfFile.getHost(hostname)

				if currentHostParams:
					logger.debug(
						"Trying to use address for %s from existing DHCP configuration.",
						hostname,
					)

					if currentHostParams.get("fixed-address"):
						ipAddress = currentHostParams["fixed-address"]
					else:
						raise BackendIOError(
							f"Cannot update dhcpd configuration for client {host.id}: "
							"ip address unknown and failed to get ip address from DHCP configuration file."
						) from err
				else:
					raise BackendIOError(
						f"Cannot update dhcpd configuration for client {host.id}: "
						"ip address unknown and failed to get host by name"
					) from err

		fixedAddress = ipAddress
		if self._fixedAddressFormat == "FQDN":
			fixedAddress = host.id

		parameters = forceDict(self._defaultClientParameters)
		if not self._dhcpdOnDepot:
			try:
				depot = self._context.host_getObjects(
					id=self._getResponsibleDepotId(host.id)
				)[0]
				if depot.ipAddress:
					parameters["next-server"] = depot.ipAddress
			except Exception as err:
				logger.error("Failed to get depot info: %s", err)

		with dhcpd_lock("config_update"):
			try:
				self._dhcpdConfFile.parse()
				currentHostParams = self._dhcpdConfFile.getHost(hostname)
				if (
					currentHostParams
					and (
						currentHostParams.get("hardware", " ").split(" ")[1]
						== host.hardwareAddress
					)
					and (currentHostParams.get("fixed-address") == fixedAddress)
					and (
						currentHostParams.get("next-server")
						== parameters.get("next-server")
					)
				):
					logger.debug(
						"DHCPD config of host '%s' unchanged, no need to update config file",
						host,
					)
					return

				self._dhcpdConfFile.addHost(
					hostname=hostname,
					hardwareAddress=host.hardwareAddress,
					ipAddress=ipAddress,
					fixedAddress=fixedAddress,
					parameters=parameters,
				)
				self._dhcpdConfFile.generate()
			except Exception as err:
				logger.error(err, exc_info=True)

		self._triggerReload()

	def _dhcpd_deleteHost(self, host: Host) -> None:
		host = forceObjectClass(host, Host)
		if self._dhcpdOnDepot:
			for depot in self._context.host_getObjects(id=self._depotId):
				if depot.id != self._depotId:
					self._getDepotConnection(depot.id).dhcpd_deleteHost(host)
		self.dhcpd_deleteHost(host)

	def dhcpd_deleteHost(self, host: Host) -> None:
		host = forceObjectClass(host, Host)

		with dhcpd_lock("config_update"):
			try:
				self._dhcpdConfFile.parse()
				hostname = _getHostname(host.id)
				if not self._dhcpdConfFile.getHost(hostname):
					return
				self._dhcpdConfFile.deleteHost(hostname)
				self._dhcpdConfFile.generate()
			except Exception as err:
				logger.error(err, exc_info=True)

		self._triggerReload()

	def host_insertObject(self, host: Host) -> None:
		if not isinstance(host, OpsiClient):
			return

		logger.debug("Inserting host: %s", host)
		self._dhcpd_updateHost(host)

	def host_updateObject(self, host: Host) -> None:
		if not isinstance(host, OpsiClient):
			return

		if not host.ipAddress and not host.hardwareAddress:
			# Not of interest
			return

		logger.debug("Updating host: %s", host)
		try:
			self._dhcpd_updateHost(host)
		except Exception as err:
			logger.error(err, exc_info=True)

	def host_deleteObjects(self, hosts: Host) -> None:
		logger.debug("Deleting host: %s", hosts)

		errors = []
		for host in hosts:
			if not isinstance(host, OpsiClient):
				continue

			try:
				self._dhcpd_deleteHost(host)
			except Exception as err:
				errors.append(str(err))

		if errors:
			raise RuntimeError(", ".join(errors))

	def configState_insertObject(self, configState: ConfigState) -> None:
		if configState.configId != "clientconfig.depot.id":
			return

		for host in self._context.host_getObjects(id=configState.objectId):
			self.host_updateObject(host)

	def configState_updateObject(self, configState: ConfigState) -> None:
		if configState.configId != "clientconfig.depot.id":
			return

		for host in self._context.host_getObjects(id=configState.objectId):
			self.host_updateObject(host)

	def configState_deleteObjects(self, configStates: list[ConfigState]) -> None:
		for configState in configStates:
			if configState.configId != "clientconfig.depot.id":
				continue

			for host in self._context.host_getObjects(id=configState.objectId):
				self.host_updateObject(host)


@lru_cache(maxsize=256)
def _getHostname(fqdn: str) -> str:
	"""
	Return only the hostname of an FQDN.

	:param fqdn: The FQDN to work with.
	:type fqdn: str
	:rtype: str
	"""
	return fqdn.split(".")[0]
