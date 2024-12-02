# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Utilites to backup configuration of an opsi system.
"""

import bz2
import gettext
import gzip
import os
import shutil
import sys

from opsicommon.logging import get_logger

from OPSI.Exceptions import (
	BackendConfigurationError,
	OpsiBackupBackendNotFound,
	OpsiBackupFileError,
	OpsiError,
)
from OPSI.Types import forceHostId, forceList, forceUnicode
from OPSI.Util.File.Opsi import OpsiBackupArchive
from OPSI.Util.Task.CleanupBackend import cleanupBackend

logger = get_logger("opsi.general")

try:
	sp = os.path.dirname(
		os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	)
	if os.path.exists(os.path.join(sp, "site-packages")):
		sp = os.path.join(sp, "site-packages")
	sp = os.path.join(sp, "python-opsi_data", "locale")
	translation = gettext.translation("python-opsi", sp)
	_ = translation.gettext
except Exception as lerr:
	logger.debug("Failed to load locale from %s: %s", sp, lerr)

	def _(string):
		"""Fallback function"""
		return string


WARNING_DIFF = _("""WARNING: Your system config is different from the one recorded with this backup.
This means the backup was probably taken for another machine and restoring it might leave this opsi installation unusable.
Do you wish to continue? [y/N] """)

WARNING_SYSCONFIG = _("""WARNING: A problem occurred while reading the sysconfig: %s
This means the backup was probably taken for another machine and restoring it might leave this opsi installation unusable.
Do you wish to continue? [y/N] """)


class OpsiBackup:
	SUPPORTED_BACKENDS = set(["auto", "all", "file", "mysql", "dhcp"])

	def __init__(self, stdout=None):
		if stdout is None:
			self.stdout = sys.stdout
		else:
			self.stdout = stdout

	def _getArchive(self, mode, file=None, compression=None):
		fileobj = None
		if file and os.path.exists(file):
			try:
				fileobj = gzip.GzipFile(file, mode)
				fileobj.read(1)
				fileobj.seek(0)
				compression = "gz"
			except IOError:
				fileobj = None

			try:
				fileobj = bz2.BZ2File(file, mode)
				fileobj.read(1)
				fileobj.seek(0)
				compression = "bz2"
			except IOError:
				fileobj = None

		if compression not in ("none", None):
			mode = ":".join((mode, compression))

		return OpsiBackupArchive(name=file, mode=mode, fileobj=fileobj)

	def create(
		self,
		destination=None,
		mode="raw",
		backends=["auto"],
		noConfiguration=False,
		compression="bz2",
		flushLogs=False,
		**kwargs,
	):
		if "all" in backends:
			backends = ["all"]

		if "auto" in backends:
			backends = ["auto"]

		if destination and os.path.exists(destination):
			file = None
		else:
			file = destination

		archive = self._getArchive(file=file, mode="w", compression=compression)

		try:
			if destination is None:
				name = archive.name.split(os.sep)[-1]
			else:
				name = archive.name
			logger.notice("Creating backup archive %s", name)

			if mode == "raw":
				for backend in backends:
					if backend in ("file", "all", "auto"):
						logger.debug("Backing up file backend.")
						archive.backupFileBackend(auto=("auto" in backends))
					if backend in ("mysql", "all", "auto"):
						logger.debug("Backing up mysql backend.")
						archive.backupMySQLBackend(
							flushLogs=flushLogs, auto=("auto" in backends)
						)
					if backend in ("dhcp", "all", "auto"):
						logger.debug("Backing up dhcp configuration.")
						archive.backupDHCPBackend(auto=("auto" in backends))

			if not noConfiguration:
				logger.debug("Backing up opsi configuration.")
				archive.backupConfiguration()

			archive.close()

			self.verify(archive.name)

			filename = archive.name.split(os.sep)[-1]
			if not destination:
				destination = os.getcwd()

			if os.path.isdir(destination):
				destination = os.path.join(destination, filename)

			shutil.move(archive.name, destination)

			logger.notice("Backup complete")
		except Exception as error:
			os.remove(archive.name)
			logger.debug(error, exc_info=True)
			raise error

	def list(self, files):
		"""
		List the contents of the backup.

		:param files: Path to files that should be processed.
		:type files: [str]
		"""
		for filename in forceList(files):
			with self._getArchive(file=filename, mode="r") as archive:
				archive.verify()

				data = {
					"configuration": archive.hasConfiguration(),
					"dhcp": archive.hasDHCPBackend(),
					"file": archive.hasFileBackend(),
					"mysql": archive.hasMySQLBackend(),
				}
				existingData = [btype for btype, exists in data.items() if exists]
				existingData.sort()

				logger.notice("%s contains: %s", archive.name, ", ".join(existingData))

	def verify(self, file, **kwargs):
		"""
		Verify a backup.

		:return: 0 if everything is okay, 1 if there was a failure.
		:rtype: int
		"""
		files = forceList(file)

		result = 0

		for fileName in files:
			with self._getArchive(mode="r", file=fileName) as archive:
				logger.info("Verifying archive %s", fileName)
				try:
					archive.verify()
					logger.notice("Archive %s is OK.", fileName)
				except OpsiBackupFileError as error:
					logger.error(error)
					result = 1

		return result

	def _verifySysconfig(self, archive):
		def ask(question=WARNING_DIFF):
			"""
			Ask for a yes or no.

			Returns ``True`` if the answer is ``Yes``, false otherwise.
			"""

			try:
				firstCharacter = input(question)
				return forceUnicode(firstCharacter) in ("y", "Y")
			except Exception as err:
				logger.error("Error while reading user input: %s", err)
			return False

		try:
			if self.getDifferencesInSysConfig(archive.sysinfo):
				return ask(WARNING_DIFF)
		except OpsiError as error:
			return ask(WARNING_SYSCONFIG % str(error))

		return True

	@staticmethod
	def getDifferencesInSysConfig(archiveSysInfo, sysInfo=None):
		"""
		Checks system informations for differences and returns the findings.

		:param archiveSysInfo: The information from the archive.
		:type archiveSysInfo: dict
		:param sysInfo: The information from the system. \
If this is `None` information will be read from the current system.
		:type sysInfo: dict
		"""
		if sysInfo is None:
			logger.debug("Reading system information...")
			sysInfo = OpsiBackupArchive.getSysInfo()

		differences = {}
		for key, value in archiveSysInfo.items():
			try:
				sysValue = str(sysInfo[key])
			except KeyError:
				logger.debug("Missing value for %s in system", key)
				differences[key] = value
				continue

			logger.debug(
				"Comparing '%s' (archive) with '%s (system)...", value, sysValue
			)
			if sysValue.strip() != value.strip():
				logger.debug(
					"Found difference (System != Archive) at %s: %s vs. %s",
					key,
					sysValue,
					value,
				)
				differences[key] = value

		return differences

	def restore(
		self,
		file,
		mode="raw",
		backends=[],
		configuration=True,
		force=False,
		new_server_id=None,
		**kwargs,
	):
		if new_server_id:
			new_server_id = forceHostId(new_server_id)

		if not backends:
			backends = []

		if "all" in backends:
			backends = ["all"]

		auto = "auto" in backends
		backends = [backend.lower() for backend in backends]

		logger.debug("Backends to restore: %s", backends)

		if not force:
			for backend in backends:
				if backend not in self.SUPPORTED_BACKENDS:
					raise ValueError(f"'{backend}' is not a valid backend.")

		configuredBackends = getConfiguredBackends()

		with self._getArchive(file=file[0], mode="r") as archive:
			self.verify(archive.name)

			if force or self._verifySysconfig(archive):
				logger.notice("Restoring data from backup archive %s.", archive.name)

				functions = []
				if configuration:
					if not archive.hasConfiguration() and not force:
						raise OpsiBackupFileError(
							"Backup file does not contain configuration data."
						)

					logger.debug("Adding restore of opsi configuration.")
					functions.append(lambda x: archive.restoreConfiguration())

				if mode == "raw":
					backendMapping = {
						"file": (archive.hasFileBackend, archive.restoreFileBackend),
						"mysql": (archive.hasMySQLBackend, archive.restoreMySQLBackend),
						"dhcp": (archive.hasDHCPBackend, archive.restoreDHCPBackend),
					}

					for backend in backends:
						for name, handlingFunctions in backendMapping.items():
							if backend in (name, "all", "auto"):
								dataExists, restoreData = handlingFunctions

								if not dataExists() and not force:
									if auto:
										logger.debug(
											"No backend data for %s - skipping.", name
										)
										continue  # Don't attempt to restore.
									raise OpsiBackupFileError(
										f"Backup file does not contain {name} backend data."
									)

								logger.debug("Adding restore of %s backend.", name)
								functions.append(restoreData)

								if (
									configuredBackends
									and (not configuration)
									and (
										backend not in configuredBackends
										and backend != "auto"
									)
								):
									logger.warning(
										"Backend %s is currently not in use!", backend
									)

				if not functions:
					raise RuntimeError(
						"Neither possible backend given nor configuration selected for restore."
					)

				try:
					for restoreFunction in functions:
						logger.trace(
							"Running restoration function '%s'", restoreFunction
						)
						restoreFunction(auto)
				except OpsiBackupBackendNotFound as err:
					logger.debug(err, exc_info=True)
					logger.debug("Restoring with '%s' failed: %s", restoreFunction, err)

					if not auto:
						raise err
				except Exception as err:
					logger.debug(err, exc_info=True)
					logger.error(
						"Failed to restore data from archive %s: %s. Aborting.",
						archive.name,
						err,
					)
					raise err

				logger.notice("Restoration complete")

				if new_server_id:
					logger.info("Cleanup backend...")
					cleanupBackend()
					logger.notice("Renaming config server to '%s'", new_server_id)
					try:
						from OPSI.Backend.BackendManager import (
							BackendManager,
						)

						managerConfig = {
							"depotBackend": False,
							"dispatchIgnoreModules": [
								"OpsiPXEConfd",
								"DHCPD",
								"HostControl",
							],
						}
						with BackendManager(**managerConfig) as backend:
							backend.backend_createBase()
							configserver = backend.host_getObjects(
								type="OpsiConfigserver"
							)
							if len(configserver) == 0:
								depotserver = backend.host_getObjects(
									type="OpsiDepotserver"
								)
								if len(depotserver) == 1:
									configserver = depotserver
							host = backend.host_getObjects(id=new_server_id)
							if not configserver:
								raise RuntimeError("No config server found in backend")
							if host and host != configserver:
								backend.host_deleteObjects(host)
							backend.host_renameOpsiDepotserver(
								oldId=configserver[0].id, newId=new_server_id
							)
					except Exception as err:
						raise RuntimeError(
							f"Failed to rename config server to '{new_server_id}': {err}"
						) from err


def getConfiguredBackends():
	"""
	Get what backends are currently confiugured.

	:returns: A set containing the names of the used backends. \
None if reading the configuration failed.
	:rtype: set or None
	"""
	try:
		from OPSI.Backend.BackendManager import (
			BackendDispatcher,
		)
	except ImportError as err:
		logger.debug("Import failed: %s", err)
		return None

	try:
		dispatcher = BackendDispatcher(
			dispatchConfigFile="/etc/opsi/backendManager/dispatch.conf",
			backendconfigdir="/etc/opsi/backends/",
		)
	except BackendConfigurationError as err:
		logger.debug("Unable to read backends: %s", err)
		return None

	names = [name.lower() for name in dispatcher.dispatcher_getBackendNames()]
	dispatcher.backend_exit()

	return set(names)
