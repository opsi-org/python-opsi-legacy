# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Products.
"""

import os
import re
import shutil

from opsicommon.logging import get_logger

from OPSI.Config import FILE_ADMIN_GROUP as DEFAULT_CLIENT_DATA_GROUP
from OPSI.Config import OPSICONFD_USER as DEFAULT_CLIENT_DATA_USER
from OPSI.System import execute
from OPSI.Types import forceBool, forceFilename, forcePackageCustomName, forceUnicode
from OPSI.Util import findFilesGenerator, randomString, removeDirectory
from OPSI.Util.File.Archive import Archive
from OPSI.Util.File.Opsi import PackageContentFile, PackageControlFile

if os.name == "posix":
	import grp
	import pwd

DEFAULT_TMP_DIR = "/tmp"
EXCLUDE_DIRS_ON_PACK_REGEX = re.compile(r"(^\.svn$)|(^\.git$)")
EXCLUDE_FILES_ON_PACK_REGEX = re.compile(
	r"(~$)|(^[Tt]humbs\.db$)|(^\.[Dd][Ss]_[Ss]tore$)"
)
PACKAGE_SCRIPT_TIMEOUT = 600

logger = get_logger("opsi.general")


def _(string):
	return string


class ProductPackageFile:
	def __init__(self, packageFile, tempDir=None):
		self.packageFile = os.path.abspath(forceFilename(packageFile))
		if not os.path.exists(self.packageFile):
			raise IOError(f"Package file '{self.packageFile}' not found")

		tempDir = tempDir or DEFAULT_TMP_DIR
		self.tempDir = os.path.abspath(forceFilename(tempDir))

		if not os.path.isdir(self.tempDir):
			raise IOError(f"Temporary directory '{self.tempDir}' not found")

		self.clientDataDir = None
		self.tmpUnpackDir = os.path.join(
			self.tempDir, f".opsi.unpack.{randomString(5)}"
		)
		self.packageControlFile = None
		self.clientDataFiles = []

	def cleanup(self):
		logger.info("Cleaning up")
		if os.path.isdir(self.tmpUnpackDir):
			shutil.rmtree(self.tmpUnpackDir)
		logger.debug("Finished cleaning up")

	def setClientDataDir(self, clientDataDir):
		self.clientDataDir = os.path.abspath(forceFilename(clientDataDir))
		logger.info("Client data dir set to '%s'", self.clientDataDir)

	def getProductClientDataDir(self):
		if not self.packageControlFile:
			raise ValueError("Metadata not present")

		if not self.clientDataDir:
			raise ValueError("Client data dir not set")

		productId = self.packageControlFile.getProduct().getId()
		return os.path.join(self.clientDataDir, productId)

	def uninstall(self):
		logger.info("Uninstalling package")
		self.deleteProductClientDataDir()
		logger.debug("Finished uninstalling package")

	def deleteProductClientDataDir(self):
		if not self.packageControlFile:
			raise ValueError("Metadata not present")

		if not self.clientDataDir:
			raise ValueError("Client data dir not set")

		productId = self.packageControlFile.getProduct().getId()
		for file in os.listdir(self.clientDataDir):
			if file.lower() == productId.lower():
				clientDataDir = os.path.join(self.clientDataDir, file)
				logger.info("Deleting client data dir '%s'", clientDataDir)
				removeDirectory(clientDataDir)

	def install(self, clientDataDir, suppressPackageContentFileGeneration=False):
		"""
		Install a package.

		This runs the preinst-script, extracts the data, creates a
		package content file, sets the rights on extracted files, runs
		the postinst and removes temporary files created during the
		installation.

		Setting `suppressPackageContentFileGeneration` to `True` will
		suppress the creation of the package content file.
		"""
		self.setClientDataDir(clientDataDir)
		self.getMetaData()
		self.runPreinst()
		self.extractData()
		if not suppressPackageContentFileGeneration:
			self.createPackageContentFile()
		self.setAccessRights()
		self.runPostinst()
		self.cleanup()

	def unpackSource(self, destinationDir=".", newProductId=None, progressSubject=None):
		logger.info("Extracting package source from '%s'", self.packageFile)
		if progressSubject:
			progressSubject.setMessage(
				_("Extracting package source from '%s'") % self.packageFile
			)

		try:
			destinationDir = forceFilename(destinationDir)
			if newProductId:
				newProductId = forceUnicode(newProductId)

			archive = Archive(
				filename=self.packageFile, progressSubject=progressSubject
			)

			logger.debug(
				"Extracting source from package '%s' to: '%s'",
				self.packageFile,
				destinationDir,
			)

			if progressSubject:
				progressSubject.setMessage(_("Extracting archives"))
			archive.extract(targetPath=self.tmpUnpackDir)

			for file in os.listdir(self.tmpUnpackDir):
				logger.info("Processing file '%s'", file)
				archiveName = ""
				if file.endswith(".cpio.gz"):
					archiveName = file[:-8]
				elif file.endswith(".cpio"):
					archiveName = file[:-5]
				elif file.endswith(".tar.gz"):
					archiveName = file[:-7]
				elif file.endswith(".tar"):
					archiveName = file[:-4]
				elif file.startswith("OPSI"):
					continue
				else:
					logger.warning("Unknown content in archive: %s", file)
					continue
				archive = Archive(
					filename=os.path.join(self.tmpUnpackDir, file),
					progressSubject=progressSubject,
				)
				if progressSubject:
					progressSubject.setMessage(_("Extracting archive %s") % archiveName)
				archive.extract(targetPath=os.path.join(destinationDir, archiveName))

			if newProductId:
				self.getMetaData()
				product = self.packageControlFile.getProduct()
				if self.packageControlFile._filename.endswith("control.toml"):
					control_filename = "control.toml"
				else:
					control_filename = "control"
				for scriptName in (
					"setupScript",
					"uninstallScript",
					"updateScript",
					"alwaysScript",
					"onceScript",
					"customScript",
				):
					script = getattr(product, scriptName)
					if not script:
						continue
					newScript = script.replace(product.id, newProductId)
					if not os.path.exists(
						os.path.join(destinationDir, "CLIENT_DATA", script)
					):
						logger.warning(
							"Script file '%s' not found",
							os.path.join(destinationDir, "CLIENT_DATA", script),
						)
						continue
					os.rename(
						os.path.join(destinationDir, "CLIENT_DATA", script),
						os.path.join(destinationDir, "CLIENT_DATA", newScript),
					)
					setattr(product, scriptName, newScript)
				product.setId(newProductId)
				self.packageControlFile.setProduct(product)
				self.packageControlFile.setFilename(
					os.path.join(destinationDir, "OPSI", control_filename)
				)
				self.packageControlFile.generate()
			logger.debug("Finished extracting package source")
		except Exception as err:
			logger.info(err, exc_info=True)
			self.cleanup()
			raise RuntimeError(
				f"Failed to extract package source from '{self.packageFile}': {err}"
			) from err

	def getMetaData(self, output_dir=None):
		if self.packageControlFile:
			# Already done
			return

		logger.info("Getting meta data from package '%s'", self.packageFile)

		try:
			if not os.path.exists(self.tmpUnpackDir):
				os.mkdir(self.tmpUnpackDir)
				os.chmod(self.tmpUnpackDir, 0o700)

			metaDataTmpDir = os.path.join(self.tmpUnpackDir, "OPSI")
			archive = Archive(self.packageFile)

			logger.debug(
				"Extracting meta data from package '%s' to: '%s'",
				self.packageFile,
				metaDataTmpDir,
			)
			archive.extract(targetPath=metaDataTmpDir, patterns=["OPSI*"])

			metadataArchives = []
			for file in os.listdir(metaDataTmpDir):
				if not file.endswith((".cpio.gz", ".tar.gz", ".cpio", ".tar")):
					logger.warning("Unknown content in archive: %s", file)
					continue
				logger.debug("Metadata archive found: %s", file)
				metadataArchives.append(file)
			if not metadataArchives:
				raise ValueError("No metadata archive found")
			if len(metadataArchives) > 2:
				raise ValueError("More than two metadata archives found")

			# Sorting to unpack custom version metadata at last
			metadataArchives.sort()

			for metadataArchive in metadataArchives:
				archive = Archive(os.path.join(metaDataTmpDir, metadataArchive))

				if output_dir is None:
					archive.extract(targetPath=metaDataTmpDir)
				else:
					archive.extract(targetPath=output_dir)
			if output_dir is not None:
				return  # to work on the whole extracted metadata directory

			packageControlFile = os.path.join(metaDataTmpDir, "control.toml")
			if not os.path.exists(packageControlFile):
				packageControlFile = os.path.join(metaDataTmpDir, "control")
			if not os.path.exists(packageControlFile):
				raise IOError("No control file found in package metadata archives")

			self.packageControlFile = PackageControlFile(packageControlFile)
			self.packageControlFile.parse()

		except Exception as err:
			logger.error(err, exc_info=True)
			self.cleanup()
			raise RuntimeError(
				f"Failed to get metadata from package '{self.packageFile}': {err}"
			) from err
		logger.debug("Got meta data from package '%s'", self.packageFile)
		return self.packageControlFile

	def extractData(self):
		logger.info("Extracting data from package '%s'", self.packageFile)

		try:
			if not self.packageControlFile:
				raise ValueError("Metadata not present")

			if not self.clientDataDir:
				raise ValueError("Client data dir not set")

			self.clientDataFiles = []

			archive = Archive(self.packageFile)

			logger.info(
				"Extracting data from package '%s' to: '%s'",
				self.packageFile,
				self.tmpUnpackDir,
			)
			archive.extract(
				targetPath=self.tmpUnpackDir, patterns=["CLIENT_DATA*", "SERVER_DATA*"]
			)

			clientDataArchives = []
			serverDataArchives = []
			for file in os.listdir(self.tmpUnpackDir):
				if file.startswith("OPSI"):
					continue

				if not file.endswith((".cpio.gz", ".tar.gz", ".cpio", ".tar")):
					logger.warning("Unknown content in archive: %s", file)
					continue

				if file.startswith("CLIENT_DATA"):
					logger.debug("Client-data archive found: %s", file)
					clientDataArchives.append(file)
				elif file.startswith("SERVER_DATA"):
					logger.debug("Server-data archive found: %s", file)
					serverDataArchives.append(file)

			if not clientDataArchives:
				logger.warning("No client-data archive found")
			if len(clientDataArchives) > 2:
				raise ValueError("More than two client-data archives found")
			if len(serverDataArchives) > 2:
				raise ValueError("More than two server-data archives found")

			# Sorting to unpack custom version data at last
			def psort(name):
				return re.sub(r"(\.tar|\.tar\.gz|\.cpio|\.cpio\.gz)$", "", name)

			clientDataArchives = sorted(clientDataArchives, key=psort)
			serverDataArchives = sorted(serverDataArchives, key=psort)

			for serverDataArchive in serverDataArchives:
				archiveFile = os.path.join(self.tmpUnpackDir, serverDataArchive)
				logger.info("Extracting server-data archive '%s' to '/'", archiveFile)
				archive = Archive(archiveFile)
				archive.extract(targetPath="/")

			productClientDataDir = self.getProductClientDataDir()
			if not os.path.exists(productClientDataDir):
				os.mkdir(productClientDataDir)
				os.chmod(productClientDataDir, 0o2770)

			for clientDataArchive in clientDataArchives:
				archiveFile = os.path.join(self.tmpUnpackDir, clientDataArchive)
				logger.info(
					"Extracting client-data archive '%s' to '%s'",
					archiveFile,
					productClientDataDir,
				)
				archive = Archive(archiveFile)
				archive.extract(targetPath=productClientDataDir)

			logger.debug("Finished extracting data from package")
		except Exception as err:
			self.cleanup()
			raise RuntimeError(
				f"Failed to extract data from package '{self.packageFile}': {err}"
			) from err

	def getClientDataFiles(self):
		if self.clientDataFiles:
			return self.clientDataFiles

		self.clientDataFiles = list(
			findFilesGenerator(
				directory=self.getProductClientDataDir(),
				followLinks=True,
				returnLinks=False,
			)
		)
		return self.clientDataFiles

	def setAccessRights(self):
		logger.info("Setting access rights of client-data files")

		if os.name != "posix":
			raise NotImplementedError("setAccessRights not implemented on windows")

		try:
			if not self.packageControlFile:
				raise ValueError("Metadata not present")

			if not self.clientDataDir:
				raise ValueError("Client data dir not set")

			productClientDataDir = self.getProductClientDataDir()

			uid = -1
			if os.geteuid() == 0:
				uid = pwd.getpwnam(DEFAULT_CLIENT_DATA_USER)[2]
			gid = grp.getgrnam(DEFAULT_CLIENT_DATA_GROUP)[2]

			os.chown(productClientDataDir, uid, gid)
			os.chmod(productClientDataDir, 0o2770)

			for filename in self.getClientDataFiles():
				path = os.path.join(productClientDataDir, filename)

				try:
					if os.path.islink(path):
						continue
					logger.debug("Setting owner of '%s' to '%s:%s'", path, uid, gid)
					os.chown(path, uid, gid)
				except Exception as err:
					raise RuntimeError(
						f"Failed to change owner of '{path}' to '{uid}:{gid}': {err}"
					) from err

				mode = None
				try:
					if os.path.islink(path):
						continue
					if os.path.isdir(path):
						logger.debug("Setting rights on directory '%s'", path)
						mode = 0o2770
					elif os.path.isfile(path):
						logger.debug("Setting rights on file '%s'", path)
						mode = (os.stat(path)[0] | 0o660) & 0o770

					if mode is not None:
						os.chmod(path, mode)
				except Exception as err:
					if mode is None:
						raise RuntimeError(
							f"Failed to set access rights of '{path}': {err}"
						) from err
					raise RuntimeError(
						f"Failed to set access rights of '{path}' to '{mode}': {err}"
					) from err
			logger.debug("Finished setting access rights of client-data files")
		except Exception as err:
			self.cleanup()
			raise RuntimeError(
				f"Failed to set access rights of client-data files of package '{self.packageFile}': {err}"
			) from err

	def createPackageContentFile(self):
		logger.info("Creating package content file")

		try:
			if not self.packageControlFile:
				raise ValueError("Metadata not present")

			if not self.clientDataDir:
				raise ValueError("Client data dir not set")

			productId = self.packageControlFile.getProduct().getId()
			productClientDataDir = self.getProductClientDataDir()
			packageContentFilename = productId + ".files"
			packageContentFile = os.path.join(
				productClientDataDir, packageContentFilename
			)

			packageContentFile = PackageContentFile(packageContentFile)
			packageContentFile.setProductClientDataDir(productClientDataDir)
			cdf = self.getClientDataFiles()
			try:
				# The package content file will be re-written and
				# then the hash will be different so we need to remove
				# this before the generation.
				cdf.remove(packageContentFilename)
			except ValueError:
				pass  # not in list
			packageContentFile.setClientDataFiles(cdf)
			packageContentFile.generate()

			cdf.append(packageContentFilename)
			self.clientDataFiles = cdf
			logger.debug("Finished creating package content file")
		except Exception as err:
			logger.error(err, exc_info=True)
			self.cleanup()
			raise RuntimeError(
				f"Failed to create package content file of package '{self.packageFile}': {err}"
			) from err

	def _runPackageScript(self, scriptName, env=None):
		env = env or {}
		logger.info("Attempt to run package script %s", scriptName)
		try:
			if not self.packageControlFile:
				raise ValueError("Metadata not present")

			if not self.clientDataDir:
				raise ValueError("Client data dir not set")

			clientDataDir = self.getProductClientDataDir()
			script = os.path.join(self.tmpUnpackDir, "OPSI", scriptName)
			if not os.path.exists(script):
				logger.info("Package script '%s' not found", scriptName)
				return []

			with open(script, "rb") as file:
				data = file.read()
			if data.startswith(b"#!"):
				new_data = re.sub(
					rb"(^|\s|/)python3?(\s+)", rb"\g<1>opsi-python\g<2>", data
				)
				if b"\r\n" in data:
					logger.info("Replacing dos line breaks in %s", script)
					new_data = new_data.replace(b"\r\n", b"\n")
				if data != new_data:
					with open(script, "wb") as file:
						file.write(new_data)

			logger.notice("Running package script '%s'", scriptName)
			os.chmod(script, 0o700)

			sp_env = {
				"PRODUCT_ID": self.packageControlFile.getProduct().getId(),
				"PRODUCT_TYPE": self.packageControlFile.getProduct().getType(),
				"PRODUCT_VERSION": self.packageControlFile.getProduct().getProductVersion(),
				"PACKAGE_VERSION": self.packageControlFile.getProduct().getPackageVersion(),
				"CLIENT_DATA_DIR": clientDataDir,
			}
			sp_env.update(env)
			logger.debug("Package script env: %s", sp_env)
			return execute(script, timeout=PACKAGE_SCRIPT_TIMEOUT, env=sp_env)
		except Exception as err:
			logger.error(err, exc_info=True)
			self.cleanup()
			raise RuntimeError(
				f"Failed to execute package script '{scriptName}' of package '{self.packageFile}': {err}"
			) from err
		finally:
			logger.debug("Finished running package script %s", scriptName)

	def runPreinst(self, env=None):
		return self._runPackageScript("preinst", env=env or {})

	def runPostinst(self, env=None):
		return self._runPackageScript("postinst", env=env or {})


class ProductPackageSource:
	def __init__(
		self,
		packageSourceDir,
		tempDir=None,
		customName=None,
		customOnly=False,
		packageFileDestDir=None,
		format="cpio",
		compression="gzip",
		dereference=False,
	):
		self.packageSourceDir = os.path.abspath(forceFilename(packageSourceDir))
		if not os.path.isdir(self.packageSourceDir):
			raise IOError(
				f"Package source directory '{self.packageSourceDir}' not found"
			)

		tempDir = tempDir or DEFAULT_TMP_DIR
		self.tempDir = os.path.abspath(forceFilename(tempDir))
		if not os.path.isdir(self.tempDir):
			raise IOError(f"Temporary directory '{self.tempDir}' not found")

		self.customName = None
		if customName:
			self.customName = forcePackageCustomName(customName)

		self.customOnly = forceBool(customOnly)

		if format:
			if format not in ("cpio", "tar"):
				raise ValueError(f"Format '{format}' not supported")
			self.format = format
		else:
			self.format = "cpio"

		if not compression:
			self.compression = None
		else:
			if compression not in ("gzip", "bzip2", "zstd"):
				raise ValueError(f"Compression '{compression}' not supported")
			self.compression = compression

		self.dereference = forceBool(dereference)

		if not packageFileDestDir:
			packageFileDestDir = self.packageSourceDir
		packageFileDestDir = os.path.abspath(forceFilename(packageFileDestDir))
		if not os.path.isdir(packageFileDestDir):
			raise IOError(
				f"Package destination directory '{packageFileDestDir}' not found"
			)

		if customName:
			packageControlFile = os.path.join(
				self.packageSourceDir, f"OPSI.{customName}", "control.toml"
			)
			if not os.path.exists(packageControlFile):
				packageControlFile = os.path.join(
					self.packageSourceDir, f"OPSI.{customName}", "control"
				)
		if not customName or not os.path.exists(packageControlFile):
			packageControlFile = os.path.join(
				self.packageSourceDir, "OPSI", "control.toml"
			)
			if not os.path.exists(packageControlFile):
				packageControlFile = os.path.join(
					self.packageSourceDir, "OPSI", "control"
				)
		if not os.path.exists(packageControlFile):
			raise OSError(f"Control file '{packageControlFile}' not found")

		self.packageControlFile = PackageControlFile(packageControlFile)
		self.packageControlFile.parse()

		customName = ""
		if self.customName:
			customName = f"~{self.customName}"
		self.packageFile = os.path.join(
			packageFileDestDir,
			f"{self.packageControlFile.getProduct().id}_{self.packageControlFile.getProduct().productVersion}-"
			f"{self.packageControlFile.getProduct().packageVersion}{customName}.opsi",
		)

		self.tmpPackDir = os.path.join(self.tempDir, f".opsi.pack.{randomString(5)}")

	def getPackageFile(self):
		return self.packageFile

	def cleanup(self):
		logger.info("Cleaning up")
		if os.path.isdir(self.tmpPackDir):
			shutil.rmtree(self.tmpPackDir)
		logger.debug("Finished cleaning up")

	def pack(self, progressSubject=None):
		# Create temporary directory
		if os.path.exists(self.tmpPackDir):
			shutil.rmtree(self.tmpPackDir)
		os.mkdir(self.tmpPackDir)

		archives = []
		diskusage = 0
		dirs = ["CLIENT_DATA", "SERVER_DATA", "OPSI"]

		try:
			if self.customName:
				found = False
				for i, currentDir in enumerate(dirs):
					customDir = f"{currentDir}.{self.customName}"
					if os.path.exists(os.path.join(self.packageSourceDir, customDir)):
						found = True
						if self.customOnly:
							dirs[i] = customDir
						else:
							dirs.append(customDir)
				if not found:
					raise RuntimeError(f"No custom dirs found for '{self.customName}'")

			# Try to define diskusage from Sourcedirectory to prevent a override from cpio sizelimit.
			for _dir in dirs:
				if (
					not os.path.exists(os.path.join(self.packageSourceDir, _dir))
					and _dir != "OPSI"
				):
					logger.info(
						"Directory '%s' does not exist",
						os.path.join(self.packageSourceDir, _dir),
					)
					continue
				for file in findFilesGenerator(
					os.path.join(self.packageSourceDir, _dir),
					excludeDir=EXCLUDE_DIRS_ON_PACK_REGEX,
					excludeFile=EXCLUDE_FILES_ON_PACK_REGEX,
					followLinks=self.dereference,
				):
					diskusage = diskusage + os.path.getsize(
						os.path.join(self.packageSourceDir, _dir, file)
					)

			if diskusage >= 2147483648:
				logger.info(
					"Switching to tar format, because sourcefiles overrides cpio sizelimit."
				)
				self.format = "tar"

			for _dir in dirs:
				if (
					not os.path.exists(os.path.join(self.packageSourceDir, _dir))
					and _dir != "OPSI"
				):
					logger.info(
						"Directory '%s' does not exist",
						os.path.join(self.packageSourceDir, _dir),
					)
					continue

				fileList = list(
					findFilesGenerator(
						os.path.join(self.packageSourceDir, _dir),
						excludeDir=EXCLUDE_DIRS_ON_PACK_REGEX,
						excludeFile=EXCLUDE_FILES_ON_PACK_REGEX,
						followLinks=self.dereference,
					)
				)

				if _dir.startswith("SERVER_DATA"):
					# Never change permissions of existing directories in /
					tmp = []
					for file in fileList:
						if file.find(os.sep) == -1:
							logger.info("Skipping dir '%s'", file)
							continue
						tmp.append(file)

					fileList = tmp

				if not fileList:
					logger.notice(
						"Skipping empty dir '%s'",
						os.path.join(self.packageSourceDir, _dir),
					)
					continue

				filename = os.path.join(self.tmpPackDir, f"{_dir}.{self.format}")
				if self.compression == "gzip":
					filename += ".gz"
				elif self.compression == "bzip2":
					filename += ".bz2"
				archive = Archive(
					filename,
					format=self.format,
					compression=self.compression,
					progressSubject=progressSubject,
				)
				if progressSubject:
					progressSubject.reset()
					progressSubject.setMessage(
						f"Creating archive {os.path.basename(archive.getFilename())}"
					)
				archive.create(
					fileList=fileList,
					baseDir=os.path.join(self.packageSourceDir, _dir),
					dereference=self.dereference,
				)
				archives.append(filename)

			archive = Archive(
				self.packageFile,
				format=self.format,
				compression=None,
				progressSubject=progressSubject,
			)
			if progressSubject:
				progressSubject.reset()
				progressSubject.setMessage(
					f"Creating archive {os.path.basename(archive.getFilename())}"
				)
			archive.create(fileList=archives, baseDir=self.tmpPackDir)
			return archive.getFilename()
		except Exception as err:
			self.cleanup()
			raise RuntimeError(
				f"Failed to create package '{self.packageFile}': {err}"
			) from err
