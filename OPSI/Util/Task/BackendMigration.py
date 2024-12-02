# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend migration tasks
"""

import time
from datetime import datetime

from opsicommon.logging import logger

from OPSI.Backend.BackendManager import BackendManager
from OPSI.Backend.Replicator import BackendReplicator
from OPSI.Exceptions import BackendConfigurationError, BackendModuleDisabledError
from OPSI.System import execute
from OPSI.Util.Task.Backup import OpsiBackup
from OPSI.Util.Task.Rights import set_rights
from OPSI.Util.Task.UpdateBackend.MySQL import updateMySQLBackend


def patch_dispatch_conf():
	logger.notice("Patch dispatch.conf to use MySQL backend")
	lines = []
	with open("/etc/opsi/backendManager/dispatch.conf", encoding="utf-8") as file:
		for line in file:
			if line.strip() and not line.strip().startswith("#"):
				match, backends = line.split(":", 1)
				match = match.strip()
				if match == ".*":
					lines.append(f"{match} : mysql\n")
					continue
				backends = list(
					{
						"mysql" if b.strip() == "file" else b.strip()
						for b in backends.split(",")
					}
				)
				if "mysql" in backends:
					if len(backends) == 1:
						continue
					backends.remove("mysql")
					backends.insert(0, "mysql")
				line = f"{match} : {', '.join(backends)}\n"
			lines.append(line)
	with open(
		"/etc/opsi/backendManager/dispatch.conf", mode="w", encoding="utf-8"
	) as file:
		file.writelines(lines)


def migrate_file_to_mysql(
	create_backup: bool = True, restart_services: bool = True
) -> bool:
	bm_config = {
		"dispatchConfigFile": "/etc/opsi/backendManager/dispatch.conf",
		"backendConfigDir": "/etc/opsi/backends",
		"extensionConfigDir": "/etc/opsi/backendManager/extend.d",
		"depotBackend": False,
		"dispatchIgnoreModules": ["OpsiPXEConfd", "DHCPD", "HostControl"],
		"unique_hardware_addresses": False,
	}
	backend_manager = backend = BackendManager(**bm_config)
	backends = None
	while getattr(backend, "_backend", None):
		backend = backend._backend
		if backend.__class__.__name__ == "BackendDispatcher":
			backends = backend._backends

	if not backends:
		raise BackendConfigurationError("Failed to get backends from dispatcher")

	if "file" not in backends:
		logger.info("File backend not active, nothing to do")
		return False

	licensing_info = backend_manager.backend_getLicensingInfo()
	mysql_module = licensing_info["modules"].get("mysql_backend")
	clients = licensing_info["client_numbers"]["all"]
	logger.info("Licensing info: clients=%d, MySQL module=%s", clients, mysql_module)
	if not mysql_module or not mysql_module["available"]:
		raise BackendModuleDisabledError("No license for MySQL backend available")

	if mysql_module["client_number"] < clients:
		raise BackendModuleDisabledError(
			f"MySQL backend license not sufficient: {mysql_module['client_number']} clients licensed but {clients} in backend"
		)

	if create_backup:
		backup_file = f"/var/lib/opsi/config/file-to-mysql-backup-{datetime.now().strftime('%Y%m%d%H%M%S')}.tar.bz2"
		OpsiBackup().create(backup_file)
		set_rights(backup_file)

	service_running = {}
	if restart_services:
		for service in ("opsipxeconfd", "opsiconfd"):
			try:
				execute(["systemctl", "is-active", "--quiet", service], shell=False)
				service_running[service] = True
			except RuntimeError as err:
				logger.debug(err)
				service_running[service] = False

			logger.info(
				"Service %r is %s",
				service,
				"running" if service_running[service] else "not running",
			)

			if service_running[service]:
				try:
					logger.notice("Stopping service %r", service)
					execute(["systemctl", "stop", service], shell=False)
				except RuntimeError as err:
					logger.warning("Failed to stop service %r: %s", service, err)
				else:
					stopped = False
					for _ in range(10):
						try:
							logger.debug("Checking if service %r is running", service)
							execute(
								["systemctl", "is-active", "--quiet", service],
								shell=False,
							)
							time.sleep(2)
						except RuntimeError:
							logger.info("Service %r stopped", service)
							stopped = True
							break
					if not stopped:
						try:
							logger.debug("Killing service %r", service)
							execute(["killall", "-9", service], shell=False)
						except RuntimeError:
							pass

	updateMySQLBackend()

	read_backend = backend_manager._loadBackend("file")
	read_backend.backend_createBase()

	write_backend = backend_manager._loadBackend("mysql")
	write_backend.unique_hardware_addresses = False
	write_backend.backend_createBase()

	backend_replicator = BackendReplicator(
		readBackend=read_backend, writeBackend=write_backend, cleanupFirst=True
	)
	backend_replicator.replicate(audit=False)

	patch_dispatch_conf()

	for service, state in service_running.items():
		if state:
			try:
				logger.notice("Starting service %r", service)
				execute(["systemctl", "start", service], shell=False)
			except RuntimeError as err:
				logger.warning("Failed to start service %r: %s", service, err)

	return True
