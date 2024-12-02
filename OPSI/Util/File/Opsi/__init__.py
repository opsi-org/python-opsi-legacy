# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Utilites to handle files specific to opsi.
"""

import bz2
import codecs
import collections
import datetime
import gzip
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
from collections import namedtuple
from contextlib import closing
from hashlib import sha1
from io import BytesIO, StringIO
from operator import itemgetter

import tomlkit
from opsicommon.logging import get_logger

import OPSI.System
from OPSI import __version__ as LIBRARY_VERSION
from OPSI.Exceptions import (
	OpsiBackupBackendNotFound,
	OpsiBackupFileError,
	OpsiBackupFileNotFound,
)
from OPSI.Object import (
	BoolProductProperty,
	LocalbootProduct,
	NetbootProduct,
	Product,
	ProductDependency,
	ProductProperty,
	UnicodeProductProperty,
)
from OPSI.System import get_subprocess_environment
from OPSI.Types import (
	forceActionRequest,
	forceBool,
	forceDictList,
	forceFilename,
	forceHostId,
	forceInstallationStatus,
	forceList,
	forceObjectClass,
	forceObjectClassList,
	forceOpsiHostKey,
	forcePackageVersion,
	forceProductId,
	forceProductPriority,
	forceProductPropertyType,
	forceProductType,
	forceProductVersion,
	forceRequirementType,
	forceUnicode,
	forceUnicodeList,
	forceUnicodeLower,
	forceUniqueList,
)
from OPSI.Util import fromJson, md5sum, toJson
from OPSI.Util.File import ConfigFile, IniFile, TextFile, requiresParsing

if os.name == "posix":
	import fcntl
	import grp
	import pwd

	from OPSI.System.Posix import SysInfo


logger = get_logger("opsi.general")
FileInfo = namedtuple("FileInfo", "productId version")


def multiline_string(value: str) -> tomlkit.items.String:
	return tomlkit.items.String(
		tomlkit.items.StringType.MLB, value, value, tomlkit.items.Trivia()
	)


def parseFilename(filename):
	"""
	Parse the filename of a '.opsi' file for meta information.

	:returns: Information about the file based on the filename. \
If no information can be extracted returns None.
	:rtype: namedtuple with attributes `productId`, `version`.
	"""
	filename = os.path.basename(filename)
	parts = filename.rsplit(".opsi", 1)[0]
	parts = parts.split("_")

	productId = "_".join(parts[:-1])
	version = "_".join(parts[-1:])

	if not (productId and version):
		return None

	return FileInfo(productId, version)


class HostKeyFile(ConfigFile):
	lineRegex = re.compile(r"^\s*([^:]+)\s*:\s*([0-9a-fA-F]{32})\s*$")

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(
			self, filename, lockFailTimeout, commentChars=[";", "/", "#"]
		)
		self._opsiHostKeys = {}

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		self._parsed = False
		for line in ConfigFile.parse(self):
			match = self.lineRegex.search(line)
			if not match:
				logger.error(
					"Found bad formatted line '%s' in pckey file '%s'",
					line,
					self._filename,
				)
				continue

			try:
				hostId = forceHostId(match.group(1))
				opsiHostKey = forceOpsiHostKey(match.group(2))
				if hostId in self._opsiHostKeys:
					logger.error(
						"Found duplicate host '%s' in pckey file '%s'",
						hostId,
						self._filename,
					)
				self._opsiHostKeys[hostId] = opsiHostKey
			except ValueError as error:
				logger.error(
					"Found bad formatted line '%s' in pckey file '%s': %s",
					line,
					self._filename,
					error,
				)

		self._parsed = True
		return self._opsiHostKeys

	def generate(self):
		self._lines = [
			f"{hostId}:{hostkey}"
			for hostId, hostkey in sorted(self._opsiHostKeys.items(), key=itemgetter(1))
		]

		self.open("w")
		self.writelines()
		self.close()

	@requiresParsing
	def getOpsiHostKey(self, hostId):
		hostId = forceHostId(hostId)
		if hostId not in self._opsiHostKeys:
			return None
		return self._opsiHostKeys[hostId]

	@requiresParsing
	def setOpsiHostKey(self, hostId, opsiHostKey):
		hostId = forceHostId(hostId)
		opsiHostKey = forceOpsiHostKey(opsiHostKey)
		self._opsiHostKeys[hostId] = opsiHostKey

	@requiresParsing
	def deleteOpsiHostKey(self, hostId):
		hostId = forceHostId(hostId)
		if hostId in self._opsiHostKeys:
			del self._opsiHostKeys[hostId]


class BackendACLFile(ConfigFile):
	aclEntryRegex = re.compile(r"^([^:]+)+\s*:\s*(\S.*)$")

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=["#"])

	def parse(self, lines=None):
		from OPSI.Config import (
			FILE_ADMIN_GROUP,
			OPSI_ADMIN_GROUP,
		)

		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		# acl example:
		#    <method>: <aclType>[(aclTypeParam[(aclTypeParamValue,...)];...)]
		#    xyz_.*:   opsi_depotserver(attributes(id,name))
		#    abc:      self(attributes(!opsiHostKey));sys_group(admin, group 2, attributes(!opsiHostKey))

		acl = []
		for line in ConfigFile.parse(self):
			match = re.search(self.aclEntryRegex, line)
			if not match:
				raise ValueError(
					f"Found bad formatted line '{line}' in acl file '{self._filename}'"
				)
			method = match.group(1).strip()
			acl.append([method, []])
			for entry in match.group(2).split(";"):
				entry = entry.strip()
				aclType = entry
				aclTypeParams = ""
				if entry.find("(") != -1:
					(aclType, aclTypeParams) = entry.split("(", 1)
					if aclTypeParams[-1] != ")":
						raise ValueError(
							f"Bad formatted acl entry '{entry}': trailing ')' missing"
						)
					aclType = aclType.strip()
					aclTypeParams = aclTypeParams[:-1]

				if aclType not in (
					"all",
					"self",
					"opsi_depotserver",
					"opsi_client",
					"sys_group",
					"sys_user",
				):
					raise ValueError(f"Unhandled acl type: '{aclType}'")
				entry = {
					"type": aclType,
					"allowAttributes": [],
					"denyAttributes": [],
					"ids": [],
				}
				if not aclTypeParams:
					if aclType in ("sys_group", "sys_user"):
						raise ValueError(
							f"Bad formatted acl type '{aclType}': no params given"
						)
				else:
					aclTypeParam = ""
					aclTypeParamValues = [""]
					inAclTypeParamValues = False
					for idx, char in enumerate(aclTypeParams):
						if char == "(":
							if inAclTypeParamValues:
								raise ValueError(
									f"Bad formatted acl type params '{aclTypeParams}'"
								)
							inAclTypeParamValues = True
						elif char == ")":
							if not inAclTypeParamValues or not aclTypeParam:
								raise ValueError(
									f"Bad formatted acl type params '{aclTypeParams}'"
								)
							inAclTypeParamValues = False
						elif char != "," or idx == len(aclTypeParams) - 1:
							if inAclTypeParamValues:
								aclTypeParamValues[-1] += char
							else:
								aclTypeParam += char

						if char == "," or idx == len(aclTypeParams) - 1:
							if inAclTypeParamValues:
								if idx == len(aclTypeParams) - 1:
									raise ValueError(
										f"Bad formatted acl type params '{aclTypeParams}'"
									)
								aclTypeParamValues.append("")
							else:
								aclTypeParam = aclTypeParam.strip()
								aclTypeParamValues = [
									t.strip() for t in aclTypeParamValues if t.strip()
								]
								if aclTypeParam == "attributes":
									for val in aclTypeParamValues:
										if not val:
											continue
										if val.startswith("!"):
											entry["denyAttributes"].append(
												val[1:].strip()
											)
										else:
											entry["allowAttributes"].append(val)
								elif aclType in (
									"sys_group",
									"sys_user",
									"opsi_depotserver",
									"opsi_client",
								):
									val = aclTypeParam.strip()
									if aclType == "sys_group":
										val = val.replace(
											"{admingroup}", OPSI_ADMIN_GROUP
										)
										val = val.replace(
											"{fileadmingroup}", FILE_ADMIN_GROUP
										)
									entry["ids"].append(val)
								else:
									raise ValueError(
										f"Unhandled acl type param '{aclTypeParam}' for acl type '{aclType}'"
									)
								aclTypeParam = ""
								aclTypeParamValues = [""]

				acl[-1][1].append(entry)
		self._parsed = True
		return acl


class BackendDispatchConfigFile(ConfigFile):
	DISPATCH_ENTRY_REGEX = re.compile(r"^([^:]+)+\s*:\s*(\S.*)$")

	def parse(self, lines=None):
		"""
		Returns the dispatch config entries with RegEx and corresponding backends.

		:rtype: [('regex', ('backend1', 'backend2', ...)),]
		"""
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		self._parsed = False

		dispatch = []
		used_backends = set()
		for line in ConfigFile.parse(self, lines):
			match = self.DISPATCH_ENTRY_REGEX.search(line)
			if not match:
				logger.error(
					"Found bad formatted line '%s' in dispatch config file '%s'",
					line,
					self._filename,
				)
				continue

			method = match.group(1).strip()
			backends = (entry.strip() for entry in match.group(2).strip(",").split(","))
			backends = tuple(backend for backend in backends if backend)
			used_backends.update(backends)
			dispatch.append((method, backends))

		for num, entry in enumerate(dispatch):
			if entry[0].startswith("backend_"):
				new_backends = list(entry[1])
				for used_backend in used_backends:
					if used_backend not in entry[1]:
						logger.warning(
							"Adding missing backend '%s' in dispatch entry '%s'",
							used_backend,
							entry[0],
						)
						new_backends.insert(0, used_backend)
				dispatch[num] = (entry[0], tuple(new_backends))

		self._parsed = True
		return dispatch

	def getUsedBackends(self, lines=None):
		"""
		Returns the backends used by the dispatch configuration.
		This will not include any information on where it is used.

		:rtype: set(['backend1', 'backend2'])
		"""
		collectedBackends = set()

		dispatchConfig = self.parse(lines=lines)
		for _, backends in dispatchConfig:
			collectedBackends.update(backends)

		return collectedBackends


class PackageContentFile(TextFile):
	"""
	This files holds information about contents of a package.

	Clients using the WAN extension will rely on this file and the
	information it provides as part of the file caching mechanism.

	The generated file lists for each file, folder or link in the
	package the type, the path to the element and its size.
	Directories will be represented with type `d`, the path to the
	directory in singlq quotes and size `0`.
	Files will be represented with type `f`, relative path to the file
	in single quotes, the filesize in bytes and in addition the md5 hash
	of the file.
	Links will be represented with type `l`, relative path to the link
	in single quotes, size `0` and in addition the path to the
	destination in single quotes.
	If the link destination is outside of `productClientDataDir` the
	element	will be treated like a regular file or directory - whatever
	the destination is.
	"""

	def __init__(self, filename, lockFailTimeout=2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._productClientDataDir = "/"
		self._clientDataFiles = []
		self._productServerDataDir = "/"
		self._serverDataFiles = []

	def getClientDataFiles(self):
		return self._clientDataFiles

	def setClientDataFiles(self, clientDataFiles):
		self._clientDataFiles = forceUnicodeList(clientDataFiles)

	def getServerDataFiles(self):
		return self._serverDataFiles

	def setServerDataFiles(self, serverDataFiles):
		self._serverDataFiles = forceUnicodeList(serverDataFiles)

	def setProductClientDataDir(self, productClientDataDir):
		self._productClientDataDir = forceFilename(productClientDataDir)

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		fileInfo = {}
		for line in self._lines:
			(entryType, tmp) = line.strip().split(None, 1)

			filename = ""
			idx = 0
			for idx, currentElement in enumerate(tmp):
				if currentElement == "'":
					if idx > 0:
						if tmp[idx - 1] == "\\":
							filename = filename[:-1] + "'"
							continue
						break
					continue
				filename += currentElement

			size = 0
			target = ""
			md5 = ""

			tmp = tmp[idx + 2 :]
			if " " in tmp:
				parts = tmp.split(None, 1)
				tmp = ""
				size = parts[0]
				if len(parts) > 1:
					tmp = parts[1]

			if entryType == "f":
				md5 = tmp
			elif entryType == "l":
				target = tmp[1:-1].replace("\\'", "'")

			fileInfo[filename] = {
				"type": entryType,
				"size": int(size),
				"md5sum": md5,
				"target": target,
			}

		self._parsed = True
		return fileInfo

	def generate(self):
		def maskQuoteChars(string):
			"Prefixes single quotes in string with a single backslash."
			return string.replace("'", "\\'")

		def handleDirectory(path):
			logger.trace("Processing '%s' as directory", path)
			return "d", 0, ""

		def handleFile(path):
			logger.trace("Processing '%s' as file", path)
			return "f", os.path.getsize(path), md5sum(path)

		self._lines = []
		for filename in self._clientDataFiles:
			try:
				path = os.path.join(self._productClientDataDir, filename)
				if os.path.isdir(path):
					entryType, size, additional = handleDirectory(path)
				else:
					entryType, size, additional = handleFile(path)

				self._lines.append(
					f"{entryType} '{maskQuoteChars(filename)}' {size} {additional}"
				)
			except Exception as err:
				logger.error(err, exc_info=True)

		self.open("w")
		self.writelines()
		self.close()


class PackageControlFile(TextFile):
	sectionRegex = re.compile(r"^\s*\[([^\]]+)\]\s*$")
	valueContinuationRegex = re.compile(r"^\s(.*)$")
	optionRegex = re.compile(r"^([^\:]+)\s*\:\s*(.*)$")

	def __init__(self, filename, lockFailTimeout=2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._sections = {}
		self._product = None
		self._productDependencies = []
		self._productProperties = []
		self._packageDependencies = []

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		if self._filename.endswith(".toml"):
			self.parse_toml()
			self._parsed = True
			return self._sections

		self._parsed = False
		self._sections = {}
		self._product = None
		self._productDependencies = []
		self._productProperties = []
		self._packageDependencies = []

		productAttributes = set(
			[
				"id",
				"type",
				"name",
				"description",
				"advice",
				"version",
				"packageversion",
				"priority",
				"licenserequired",
				"productclasses",
				"pxeconfigtemplate",
				"setupscript",
				"uninstallscript",
				"updatescript",
				"alwaysscript",
				"oncescript",
				"customscript",
				"userloginscript",
			]
		)
		dependencyAttributes = set(
			[
				"action",
				"requiredproduct",
				"requiredproductversion",
				"requiredpackageversion",
				"requiredclass",
				"requiredstatus",
				"requiredaction",
				"requirementtype",
			]
		)
		propertyAttributes = set(
			[
				"type",
				"name",
				"default",
				"values",
				"description",
				"editable",
				"multivalue",
			]
		)

		sectionType = None
		option = None
		for lineNum, line in enumerate(self._lines, start=1):
			if line and line.startswith((";", "#")):
				# Comment
				continue

			line = line.replace("\r", "")

			match = self.sectionRegex.search(line)
			if match:
				sectionType = match.group(1).strip().lower()
				if sectionType not in (
					"package",
					"product",
					"windows",
					"productdependency",
					"productproperty",
					"changelog",
				):
					raise ValueError(
						f"Parse error in line {lineNum}: unknown section '{sectionType}'"
					)
				if sectionType == "changelog":
					self._sections[sectionType] = ""
				else:
					if sectionType in self._sections:
						self._sections[sectionType].append({})
					else:
						self._sections[sectionType] = [{}]
				continue

			if not sectionType and line:
				raise ValueError(f"Parse error in line {lineNum}: not in a section")

			if sectionType == "changelog":
				if self._sections[sectionType]:
					self._sections[sectionType] += "\n"
				self._sections[sectionType] += line.rstrip()
				continue

			key = None
			value = None
			match = self.valueContinuationRegex.search(line)
			if match:
				value = match.group(1)
			else:
				match = self.optionRegex.search(line)
				if match:
					key = match.group(1).lower()
					value = match.group(2).strip()

			if sectionType == "package":
				option = key
				if key == "version":
					value = forceUnicodeLower(value)
				elif key == "depends":
					value = forceUnicodeLower(value)
				else:  # Unsupported key
					continue

			elif sectionType == "product" and key in productAttributes:
				option = key
				if key == "id":
					value = forceProductId(value)
				elif key == "type":
					value = forceProductType(value)
				elif key == "name":
					value = forceUnicode(value)
				elif key == "description":
					value = forceUnicode(value)
				elif key == "advice":
					value = forceUnicode(value)
				elif key == "version":
					value = forceProductVersion(value)
				elif key == "packageversion":
					value = forcePackageVersion(value)
				elif key == "priority":
					value = forceProductPriority(value)
				elif key == "licenserequired":
					value = forceBool(value)
				elif key == "productclasses":
					value = forceUnicodeLower(value)
				elif key == "pxeconfigtemplate":
					value = forceFilename(value)
				elif key == "setupscript":
					value = forceFilename(value)
				elif key == "uninstallscript":
					value = forceFilename(value)
				elif key == "updatescript":
					value = forceFilename(value)
				elif key == "alwaysscript":
					value = forceFilename(value)
				elif key == "oncescript":
					value = forceFilename(value)
				elif key == "customscript":
					value = forceFilename(value)
				elif key == "userloginscript":
					value = forceFilename(value)

			elif sectionType == "windows" and key in ("softwareids",):
				option = key
				value = forceUnicodeLower(value)

			elif sectionType == "productdependency" and key in dependencyAttributes:
				option = key
				if key == "action":
					value = forceActionRequest(value)
				elif key == "requiredproduct":
					value = forceProductId(value)
				elif key == "requiredproductversion":
					value = forceProductVersion(value)
				elif key == "requiredpackageversion":
					value = forcePackageVersion(value)
				elif key == "requiredclass":
					value = forceUnicodeLower(value)
				elif key == "requiredstatus":
					value = forceInstallationStatus(value)
				elif key == "requiredaction":
					value = forceActionRequest(value)
				elif key == "requirementtype":
					value = forceRequirementType(value)

			elif sectionType == "productproperty" and key in propertyAttributes:
				option = key
				if key == "type":
					value = forceProductPropertyType(value)
				elif key == "name":
					value = forceUnicodeLower(value)
				elif key == "default":
					value = forceUnicode(value)
				elif key == "values":
					value = forceUnicode(value)
				elif key == "description":
					value = forceUnicode(value)
				elif key == "editable":
					value = forceBool(value)
				elif key == "multivalue":
					value = forceBool(value)

			else:
				value = forceUnicode(line)

			if not option:
				raise ValueError(
					f"Parse error in line '{lineNum}': no option / bad option defined"
				)

			if option not in self._sections[sectionType][-1]:
				self._sections[sectionType][-1][option] = value
			else:
				if isinstance(self._sections[sectionType][-1][option], str):
					if not self._sections[sectionType][-1][option].endswith("\n"):
						self._sections[sectionType][-1][option] += "\n"
					self._sections[sectionType][-1][option] += value.lstrip()

		for sectionType, secs in self._sections.items():
			if sectionType == "changelog":
				continue

			for i, currentSection in enumerate(secs):
				for option, value in currentSection.items():
					if (
						(sectionType == "product" and option == "productclasses")
						or (sectionType == "package" and option == "depends")
						or (
							sectionType == "productproperty"
							and option in ("default", "values")
						)
						or (sectionType == "windows" and option == "softwareids")
					):
						try:
							if not value.strip().startswith(("{", "[")):
								raise ValueError(
									"Not trying to read json string because value does not start with { or ["
								)
							value = fromJson(value.strip())
							# Remove duplicates
							value = forceUniqueList(value)
						except Exception as err:
							logger.trace(
								"Failed to read json string '%s': %s",
								value.strip(),
								err,
							)
							value = value.replace("\n", "")
							value = value.replace("\t", "")
							if not (
								sectionType == "productproperty" and option == "default"
							):
								value = [v.strip() for v in value.split(",")]

							# Remove duplicates
							value = [v for v in forceList(value) if v not in ("", None)]
							value = forceUniqueList(value)

					if isinstance(value, str):
						value = value.rstrip()

					self._sections[sectionType][i][option] = value

		if not self._sections.get("product"):
			raise ValueError(
				f"Error in control file '{self._filename}': 'product' section not found"
			)

		# Get package info
		for option, value in self._sections.get("package", [{}])[0].items():
			if option == "depends":
				for dep in value:
					match = re.search(r"^\s*([^\(]+)\s*\(*\s*([^\)]*)\s*\)*", dep)
					if not match.group(1):
						raise ValueError(
							f"Bad package dependency '{dep}' in control file"
						)

					package = match.group(1).strip()
					version = match.group(2)
					condition = None
					if version:
						match = re.search(
							r"^\s*([<>]?=?)\s*([\w\.]+-*[\w\.]*)\s*$", version
						)
						if not match:
							raise ValueError(
								f"Bad version string '{version}' in package dependency"
							)

						condition = match.group(1)
						if not condition:
							condition = "="
						if condition not in ("=", "<", "<=", ">", ">="):
							raise ValueError(
								f"Bad condition string '{condition}' in package dependency"
							)
						version = match.group(2)
					else:
						version = None
					self._packageDependencies.append(
						{"package": package, "condition": condition, "version": version}
					)

		# Create Product object
		product = self._sections["product"][0]
		Class = None
		if product.get("type") == "NetbootProduct":
			Class = NetbootProduct
		elif product.get("type") == "LocalbootProduct":
			Class = LocalbootProduct
		else:
			raise ValueError(
				f"Error in control file '{self._filename}': unknown product type '{product.get('type')}'"
			)

		productVersion = product.get("version")
		if not productVersion:
			logger.warning("No product version given! Assuming 1.0.")
			productVersion = 1.0
		packageVersion = self._sections.get("package", [{}])[0].get(
			"version"
		) or product.get("packageversion")
		if not packageVersion:
			logger.warning("No package version given! Assuming 1.")
			packageVersion = 1

		self._product = Class(
			id=product.get("id"),
			name=product.get("name"),
			productVersion=productVersion,
			packageVersion=packageVersion,
			licenseRequired=product.get("licenserequired"),
			setupScript=product.get("setupscript"),
			uninstallScript=product.get("uninstallscript"),
			updateScript=product.get("updatescript"),
			alwaysScript=product.get("alwaysscript"),
			onceScript=product.get("oncescript"),
			customScript=product.get("customscript"),
			priority=product.get("priority"),
			description=product.get("description"),
			advice=product.get("advice"),
			productClassIds=product.get("productclasses"),
			windowsSoftwareIds=self._sections.get("windows", [{}])[0].get(
				"softwareids", []
			),
			changelog=self._sections.get("changelog"),
		)
		if (
			isinstance(self._product, NetbootProduct)
			and product.get("pxeconfigtemplate") is not None
		):
			self._product.setPxeConfigTemplate(product.get("pxeconfigtemplate"))

		if (
			isinstance(self._product, LocalbootProduct)
			and product.get("userloginscript") is not None
		):
			self._product.setUserLoginScript(product.get("userloginscript"))
		self._product.setDefaults()

		# Create ProductDependency objects
		for productDependency in self._sections.get("productdependency", []):
			self._productDependencies.append(
				ProductDependency(
					productId=self._product.getId(),
					productVersion=self._product.getProductVersion(),
					packageVersion=self._product.getPackageVersion(),
					productAction=productDependency.get("action"),
					requiredProductId=productDependency.get("requiredproduct"),
					requiredProductVersion=productDependency.get(
						"requiredproductversion"
					),
					requiredPackageVersion=productDependency.get(
						"requiredpackageversion"
					),
					requiredAction=productDependency.get("requiredaction"),
					requiredInstallationStatus=productDependency.get("requiredstatus"),
					requirementType=productDependency.get("requirementtype"),
				)
			)
			self._productDependencies[-1].setDefaults()

		# Create ProductProperty objects
		for productProperty in self._sections.get("productproperty", []):
			self.parse_product_property(productProperty)

		self._parsed = True
		return self._sections

	def parse_toml(self):
		data_dict = tomlkit.loads("".join(self._lines)).unwrap()

		# kept _section stuff for compatibility
		self._sections["product"] = [data_dict["Product"].get("id")]
		self._sections["productproperty"] = []
		self._sections["productdependency"] = []

		product = None
		# changelog key in changelog section... better idea?
		changelog = data_dict.get("changelog", {}).get("changelog")
		if changelog is None:
			path = os.path.join(os.path.dirname(self._filename), "changelog.txt")
			if os.path.exists(path):
				with codecs.open(path, "r", encoding="utf-8") as file:
					changelog = file.read()
			else:
				changelog = ""
		self._sections["changelog"] = changelog

		windows_section = data_dict.get("windows")
		if windows_section:
			softwareids = windows_section.get("softwareids", [])
		else:
			softwareids = data_dict["Product"].get("windowsSoftwareIds", [])

		emptystring_entries = (
			"advice",
			"description",
			"setupScript",
			"uninstallScript",
			"updateScript",
			"updateScript",
			"alwaysScript",
			"onceScript",
			"customScript",
			"userLoginScript",
		)
		product_dict = data_dict["Product"]
		for key in emptystring_entries:
			if not product_dict.get(key):
				data_dict["Product"][key] = ""

		if product_dict["type"] in ("netboot", "NetbootProduct"):
			product = NetbootProduct(
				forceProductId(product_dict["id"]),
				forceProductVersion(product_dict["version"]),
				forcePackageVersion(data_dict["Package"]["version"]),
				name=forceUnicode(product_dict["name"]),
				licenseRequired=forceBool(product_dict.get("licenseRequired")),
				setupScript=forceFilename(product_dict.get("setupScript")),
				uninstallScript=forceFilename(product_dict.get("uninstallScript")),
				updateScript=forceFilename(product_dict.get("updateScript")),
				alwaysScript=forceFilename(product_dict.get("alwaysScript")),
				onceScript=forceFilename(product_dict.get("onceScript")),
				customScript=forceFilename(product_dict.get("customScript")),
				# userLoginScript=forceFilename(product_dict.get("userLoginScript")),
				priority=forceProductPriority(product_dict.get("priority")),
				description=forceUnicode(product_dict.get("description")),
				advice=forceUnicode(product_dict.get("advice")),
				changelog=changelog,
				productClassIds=forceUnicodeList(product_dict.get("productClasses")),
				windowsSoftwareIds=softwareids,
				pxeConfigTemplate=forceFilename(product_dict.get("pxeConfigTemplate")),
			)
		elif product_dict["type"] in ("localboot", "LocalbootProduct"):
			product = LocalbootProduct(
				forceProductId(product_dict["id"]),
				forceProductVersion(product_dict["version"]),
				forcePackageVersion(data_dict["Package"]["version"]),
				name=forceUnicode(product_dict["name"]),
				licenseRequired=forceBool(product_dict.get("licenseRequired")),
				setupScript=forceFilename(product_dict.get("setupScript")),
				uninstallScript=forceFilename(product_dict.get("uninstallScript")),
				updateScript=forceFilename(product_dict.get("updateScript")),
				alwaysScript=forceFilename(product_dict.get("alwaysScript")),
				onceScript=forceFilename(product_dict.get("onceScript")),
				customScript=forceFilename(product_dict.get("customScript")),
				userLoginScript=forceFilename(product_dict.get("userLoginScript")),
				priority=forceProductPriority(product_dict.get("priority")),
				description=forceUnicode(product_dict.get("description")),
				advice=forceUnicode(product_dict.get("advice")),
				changelog=changelog,
				productClassIds=forceUnicodeList(product_dict.get("productClasses")),
				windowsSoftwareIds=softwareids,
				# pxeConfigTemplate=forceFilename(product_dict.get("pxeConfigTemplate"))
			)
		self.setProduct(product)

		self.setPackageDependencies(data_dict["Package"].get("depends"))

		dep_list = []
		for dep in data_dict.get("ProductDependency", []):
			req_prod_vers = (
				forceProductVersion(dep.get("required_product_version"))
				if dep.get("required_product_version")
				else None
			)
			req_pack_vers = (
				forcePackageVersion(dep.get("required_package_version"))
				if dep.get("required_package_version")
				else None
			)
			req_act = forceActionRequest(dep.get("required_action", "setup"))
			req_inst_stat = forceInstallationStatus(
				dep.get("required_status", "installed")
			)
			req_type = forceRequirementType(dep.get("requirement_type", "before"))
			dependency = ProductDependency(
				forceProductId(product_dict["id"]),
				forceProductVersion(product_dict["version"]),
				forcePackageVersion(data_dict["Package"]["version"]),
				forceActionRequest(dep.get("action")),
				forceProductId(dep.get("requiredProduct")),
				requiredProductVersion=req_prod_vers,
				requiredPackageVersion=req_pack_vers,
				requiredAction=req_act,
				requiredInstallationStatus=req_inst_stat,
				requirementType=req_type,
			)
			dep_list.append(dependency)
			self._sections["productdependency"].append(
				dep.get("product_id")
			)  # kept for compatibility
		self.setProductDependencies(dep_list)

		for prop in data_dict.get("ProductProperty", []):
			self._sections["productproperty"].append(
				prop.get("name")
			)  # kept for compatibility
			self.parse_product_property(prop)

	def parse_product_property(self, productProperty):
		Class = UnicodeProductProperty

		if productProperty.get("type", "").lower() in (
			"unicodeproductproperty",
			"unicode",
			"",
		):
			Class = UnicodeProductProperty
		elif productProperty.get("type", "").lower() in ("boolproductproperty", "bool"):
			Class = BoolProductProperty
		else:
			raise ValueError(
				f"Error in control file '{self._filename}': unknown product property type '{productProperty.get('type')}'"
			)
		self._productProperties.append(
			Class(
				productId=self._product.getId(),
				productVersion=self._product.getProductVersion(),
				packageVersion=self._product.getPackageVersion(),
				propertyId=productProperty.get("name", ""),
				description=productProperty.get("description", ""),
				defaultValues=productProperty.get("default", []),
			)
		)
		if isinstance(self._productProperties[-1], UnicodeProductProperty):
			if productProperty.get("values") is not None:
				self._productProperties[-1].setPossibleValues(
					productProperty.get("values")
				)
			else:
				self._productProperties[-1].possibleValues = []

			if productProperty.get("editable") is not None:
				self._productProperties[-1].setEditable(productProperty["editable"])
			else:
				if productProperty.get("values") not in (None, []):
					self._productProperties[-1].setEditable(False)
				else:
					self._productProperties[-1].setEditable(True)

			if productProperty.get("multivalue") is not None:
				self._productProperties[-1].setMultiValue(productProperty["multivalue"])

		self._productProperties[-1].setDefaults()

	@requiresParsing
	def getProduct(self):
		return self._product

	def setProduct(self, product):
		self._product = forceObjectClass(product, Product)

	@requiresParsing
	def getProductDependencies(self):
		return self._productDependencies

	def setProductDependencies(self, productDependencies):
		self._productDependencies = forceObjectClassList(
			productDependencies, ProductDependency
		)

	@requiresParsing
	def getProductProperties(self):
		return self._productProperties

	def setProductProperties(self, productProperties):
		self._productProperties = forceObjectClassList(
			productProperties, ProductProperty
		)

	@requiresParsing
	def getPackageDependencies(self):
		return self._packageDependencies

	def setPackageDependencies(self, packageDependencies):
		self._packageDependencies = []
		if not packageDependencies:
			return
		for packageDependency in forceDictList(packageDependencies):
			if not packageDependency.get("package"):
				raise ValueError(f"No package given: {packageDependency}")

			if not packageDependency.get("version"):
				packageDependency["version"] = None
				packageDependency["condition"] = None
			else:
				if not packageDependency.get("condition"):
					packageDependency["condition"] = "="
				if packageDependency["condition"] not in ("=", "<", "<=", ">", ">="):
					raise ValueError(
						f"Bad condition string '{packageDependency['condition']}' in package dependency"
					)

			self._packageDependencies.append(packageDependency)

	def generate(self):
		if not self._product:
			raise ValueError("Got no data to write")

		logger.info("Writing opsi package control file '%s'", self._filename)
		if self._filename.endswith(".toml"):
			self.generate_toml()
		else:
			self.generate_old()

	def generate_old(self):
		self._lines = ["[Package]"]
		self._lines.append(f"version: {self._product.getPackageVersion()}")
		depends = ""
		for packageDependency in self._packageDependencies:
			if depends:
				depends += ", "

			depends += packageDependency["package"]
			if packageDependency["version"]:
				depends += f" ({packageDependency['condition']} {packageDependency['version']})"

		self._lines.append(f"depends: {depends}")
		self._lines.append("")

		self._lines.append("[Product]")
		productType = self._product.getType()
		if productType == "LocalbootProduct":
			productType = "localboot"
		elif productType == "NetbootProduct":
			productType = "netboot"
		else:
			raise ValueError(f"Unhandled product type '{productType}'")

		self._lines.append(f"type: {productType}")
		self._lines.append(f"id: {self._product.getId()}")
		self._lines.append(f"name: {self._product.getName()}")
		self._lines.append("description: ")
		descLines = self._product.getDescription().split("\n")
		if len(descLines) > 0:
			self._lines[-1] += descLines[0]
			if len(descLines) > 1:
				for line in descLines[1:]:
					self._lines.append(f" {line}")
		self._lines.append(f"advice: {self._product.getAdvice()}")
		self._lines.append(f"version: {self._product.getProductVersion()}")
		self._lines.append(f"priority: {self._product.getPriority()}")
		self._lines.append(f"licenseRequired: {self._product.getLicenseRequired()}")
		if self._product.getProductClassIds() is not None:
			self._lines.append(
				f'productClasses: {", ".join(self._product.getProductClassIds())}'
			)
		self._lines.append(f"setupScript: {self._product.getSetupScript()}")
		self._lines.append(f"uninstallScript: {self._product.getUninstallScript()}")
		self._lines.append(f"updateScript: {self._product.getUpdateScript()}")
		self._lines.append(f"alwaysScript: {self._product.getAlwaysScript()}")
		self._lines.append(f"onceScript: {self._product.getOnceScript()}")
		self._lines.append(f"customScript: {self._product.getCustomScript()}")
		if isinstance(self._product, LocalbootProduct):
			self._lines.append(f"userLoginScript: {self._product.getUserLoginScript()}")
		if isinstance(self._product, NetbootProduct):
			pxeConfigTemplate = self._product.getPxeConfigTemplate()
			if not pxeConfigTemplate:
				pxeConfigTemplate = ""
			self._lines.append(f"pxeConfigTemplate: {pxeConfigTemplate}")
		self._lines.append("")

		if self._product.getWindowsSoftwareIds():
			self._lines.append("[Windows]")
			self._lines.append(
				f'softwareIds: {", ".join(self._product.getWindowsSoftwareIds())}'
			)
			self._lines.append("")

		for dependency in self._productDependencies:
			self._lines.append("[ProductDependency]")
			self._lines.append(f"action: {dependency.getProductAction()}")
			if dependency.getRequiredProductId():
				self._lines.append(
					f"requiredProduct: {dependency.getRequiredProductId()}"
				)
			if dependency.getRequiredProductVersion():
				self._lines.append(
					f"requiredProductVersion: {dependency.getRequiredProductVersion()}"
				)
			if dependency.getRequiredPackageVersion():
				self._lines.append(
					f"requiredPackageVersion: {dependency.getRequiredPackageVersion()}"
				)
			if dependency.getRequiredAction():
				self._lines.append(f"requiredAction: {dependency.getRequiredAction()}")
			if dependency.getRequiredInstallationStatus():
				self._lines.append(
					f"requiredStatus: {dependency.getRequiredInstallationStatus()}"
				)
			if dependency.getRequirementType():
				self._lines.append(
					f"requirementType: {dependency.getRequirementType()}"
				)
			self._lines.append("")

		for productProperty in self._productProperties:
			self._lines.append("[ProductProperty]")
			productPropertyType = "unicode"
			if isinstance(productProperty, BoolProductProperty):
				productPropertyType = "bool"
			self._lines.append(f"type: {productPropertyType}")
			self._lines.append(f"name: {productProperty.getPropertyId()}")
			if not isinstance(productProperty, BoolProductProperty):
				self._lines.append(f"multivalue: {productProperty.getMultiValue()}")
				self._lines.append(f"editable: {productProperty.getEditable()}")
			if productProperty.getDescription():
				self._lines.append("description: ")
				descLines = productProperty.getDescription().split("\n")
				if len(descLines) > 0:
					self._lines[-1] += descLines[0]
					if len(descLines) > 1:
						for line in descLines[1:]:
							self._lines.append(f" {line}")

			if (
				not isinstance(productProperty, BoolProductProperty)
				and productProperty.getPossibleValues() is not None
			):
				self._lines.append(
					f"values: {toJson(productProperty.getPossibleValues())}"
				)
			if productProperty.getDefaultValues() is not None:
				if isinstance(productProperty, BoolProductProperty):
					self._lines.append(
						f"default: {productProperty.getDefaultValues()[0]}"
					)
				else:
					self._lines.append(
						f"default: {toJson(productProperty.getDefaultValues())}"
					)
			self._lines.append("")

		if self._product.getChangelog():
			self._lines.append("[Changelog]")
			self._lines.extend(self._product.getChangelog().split("\n"))

		old_path = self._filename
		try:
			if self._filename.endswith(".toml"):
				self._filename = self._filename.removesuffix(".toml")
			self.open("w")
			self.writelines()
		finally:
			self.close()
			self._filename = old_path

	def generate_toml(self):
		data_dict = tomlkit.document()
		data_dict["Package"] = {
			"version": self._product.getPackageVersion(),
			"depends": self._packageDependencies,  # Do not use getPackageDependencies() as it requires parsing
		}
		product_dict = {
			"type": self._product.getType(),
			"id": self._product.getId(),
			"name": self._product.getName(),
			"description": multiline_string(self._product.getDescription()) or None,
			"advice": multiline_string(self._product.getAdvice()) or None,
			"version": self._product.getProductVersion(),
			"priority": self._product.getPriority(),
			"licenseRequired": self._product.getLicenseRequired(),
			"productClasses": self._product.getProductClassIds(),
			"setupScript": self._product.getSetupScript() or None,
			"uninstallScript": self._product.getUninstallScript() or None,
			"updateScript": self._product.getUpdateScript() or None,
			"alwaysScript": self._product.getAlwaysScript() or None,
			"onceScript": self._product.getOnceScript() or None,
			"customScript": self._product.getCustomScript() or None,
			"userLoginScript": self._product.getUserLoginScript() or None,
			"windowsSoftwareIds": self._product.getWindowsSoftwareIds(),
		}
		if product_dict["type"] == "netboot":
			product_dict["pxeConfigTemplate"] = self._product.getPxeConfigTemplate()
		data_dict["Product"] = {
			key: value for key, value in product_dict.items() if value is not None
		}

		properties_list = []
		for prop in (
			self._productProperties
		):  # Do not use getPackageDependencies() as it requires parsing
			property_dict = {
				"type": prop.getType(),
				"name": prop.getPropertyId(),
				"multivalue": prop.getMultiValue(),
				"editable": prop.getEditable(),
				"description": prop.getDescription(),
				"values": prop.getPossibleValues(),
				"default": prop.getDefaultValues(),
			}
			properties_list.append(
				{
					key: value
					for key, value in property_dict.items()
					if value is not None
				}
			)
		if properties_list:
			data_dict["ProductProperty"] = properties_list

		dependencies_list = []
		for dep in (
			self._productDependencies
		):  # Do not use getPackageDependencies() as it requires parsing
			dependency_dict = {
				"requiredProduct": dep.getRequiredProductId(),
				"requiredProductVersion": dep.getRequiredProductVersion(),
				"requiredPackageVersion": dep.getRequiredPackageVersion(),
				"action": dep.getProductAction(),
				"requirementType": dep.getRequirementType(),
				"requiredAction": dep.getRequiredAction(),
				"requiredStatus": dep.getRequiredInstallationStatus(),
			}
			dependencies_list.append(
				{
					key: value
					for key, value in dependency_dict.items()
					if value is not None
				}
			)
		if dependencies_list:
			data_dict["ProductDependency"] = dependencies_list

		changelog = self._product.getChangelog().strip()
		if changelog is not None:
			path = os.path.dirname(self._filename)
			with codecs.open(
				os.path.join(path, "changelog.txt"), "w", encoding="utf-8"
			) as file:
				file.write(changelog)

		old_path = self._filename
		try:
			if not self._filename.endswith(".toml"):
				self._filename = self._filename + ".toml"
			self.open("w")
			self.write(tomlkit.dumps(data_dict))
		finally:
			self.close()
			self._filename = old_path


class OpsiConfFile(IniFile):
	sectionRegex = re.compile(r"^\s*\[([^\]]+)\]\s*$")
	optionRegex = re.compile(r"^([^\:]+)\s*\=\s*(.*)$")

	def __init__(self, filename="/etc/opsi/opsi.conf", lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[";", "#"])
		self._parsed = False
		self._sections = {}
		self._opsiGroups = {}
		self.parsed = False
		self._opsiConfig = {}

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self.parsed = False
		self._sections = {}
		self._opsiConfig = {}

		sectionType = None

		for lineNum, line in enumerate(self._lines, start=1):
			line = line.strip()
			if line and line.startswith((";", "#")):
				# This is a comment
				continue

			line = line.replace("\r", "")

			match = self.sectionRegex.search(line)
			if match:
				sectionType = match.group(1).strip().lower()
				if sectionType not in ("groups", "packages", "ldap_auth"):
					raise ValueError(
						f"Parse error in line {lineNum}: unknown section '{sectionType}'"
					)
			elif not sectionType and line:
				raise ValueError(f"Parse error in line {lineNum}: not in a section")

			key = None
			value = None

			match = self.optionRegex.search(line)
			if match:
				key = match.group(1).strip().lower()
				value = match.group(2).strip()

			if sectionType == "groups":
				if key == "admingroup":
					value = forceUnicodeLower(value)
				elif key == "fileadmingroup":
					value = forceUnicodeLower(value)
				elif value:
					value = forceUnicodeList(
						[part.strip().lower() for part in value.split(",")]
					)

				if "groups" not in self._opsiConfig:
					self._opsiConfig["groups"] = {}

				if key and value:
					self._opsiConfig["groups"][key] = value
			elif sectionType == "packages":
				if "packages" not in self._opsiConfig:
					self._opsiConfig["packages"] = {}

				if key == "use_pigz":
					self._opsiConfig["packages"][key] = forceBool(value)

			elif sectionType == "ldap_auth":
				if "ldap_auth" not in self._opsiConfig:
					self._opsiConfig["ldap_auth"] = {}
				if key in ("ldap_url", "bind_user", "group_filter") and value:
					self._opsiConfig["ldap_auth"][key] = value

		self._parsed = True
		return self._opsiConfig

	@requiresParsing
	def getOpsiFileAdminGroup(self):
		if not self._opsiConfig.get("groups", {}).get("fileadmingroup", ""):
			return "pcpatch"
		return self._opsiConfig["groups"]["fileadmingroup"]

	@requiresParsing
	def getOpsiAdminGroup(self):
		if not self._opsiConfig.get("groups", {}).get("admingroup", ""):
			return "opsiadmin"
		return self._opsiConfig["groups"]["admingroup"]

	@requiresParsing
	def getOpsiGroups(self, groupType):
		if not self._opsiConfig.get("groups", {}).get(groupType, ""):
			return None
		return self._opsiConfig["groups"][groupType]

	@requiresParsing
	def isPigzEnabled(self):
		"""
		Check if the usage of pigz is enabled.

		:return: False if the usage of pigz is disabled, True otherwise.
		:rtype: bool
		"""
		if (
			"packages" in self._opsiConfig
			and "use_pigz" in self._opsiConfig["packages"]
		):
			return self._opsiConfig["packages"]["use_pigz"]
		return True

	@requiresParsing
	def get_ldap_auth_config(self) -> dict:
		conf = self._opsiConfig.get("ldap_auth", {})
		if conf and conf.get("ldap_url"):
			if "username" in conf:
				# Option was renamed
				conf["bind_user"] = conf["username"]
				del conf["username"]
			return conf
		return None


class OpsiBackupArchive(tarfile.TarFile):
	CONTENT_DIR = "CONTENT"
	CONTROL_DIR = "CONTROL"

	CONF_DIR = "/etc/opsi"
	BACKEND_CONF_DIR = os.path.join(CONF_DIR, "backends")
	DISPATCH_CONF = os.path.join(CONF_DIR, "backendManager", "dispatch.conf")

	def __init__(
		self,
		name=None,
		mode=None,
		tempdir=tempfile.gettempdir(),
		fileobj=None,
		**kwargs,
	):
		self.tempdir = tempdir
		self.mode = mode
		self.sysinfo = None
		compression = None

		if mode and ":" in mode:
			self.mode, compression = mode.split(":")
			assert compression in ("gz", "bz2")

		if name is None:
			self.sysinfo = self.getSysInfo()
			name = self._generateNewArchive(suffix=compression)
			self.mode = "w"
		elif not os.path.exists(name):
			if self.mode and not self.mode.startswith("w"):
				raise OpsiBackupFileNotFound("Cannot read from nonexisting file.")
		else:
			if self.mode and self.mode.startswith("w"):
				raise OpsiBackupFileError("Backup files are immutable.")

		if compression and not fileobj:
			if compression == "gz":
				fileobj = gzip.GzipFile(name, self.mode)
			if compression == "bz2":
				fileobj = bz2.BZ2File(name, self.mode)

		self._filemap = {}

		assert self.mode and str(self.mode)[0] in ("r", "w")
		tarfile.TarFile.__init__(self, name, self.mode, fileobj=fileobj, **kwargs)

		if self.mode.startswith("w"):
			if not self.sysinfo:
				self.sysinfo = self.getSysInfo()
		else:
			self.sysinfo = self._readSysInfo()
			self._filemap = self._readChecksumFile()

		try:
			self._backends = self._readBackendConfiguration()
		except OpsiBackupFileError as error:
			if self.mode.startswith("w"):
				raise error
			self._backends = None

	def _readBackendConfiguration(self):
		if os.path.exists(self.CONF_DIR) and os.path.exists(self.DISPATCH_CONF):
			try:
				dispatchedBackends = BackendDispatchConfigFile(
					self.DISPATCH_CONF
				).getUsedBackends()
			except Exception as err:
				logger.warning("Could not read dispatch configuration: %s", err)
				dispatchedBackends = []

		if not os.path.exists(self.BACKEND_CONF_DIR):
			raise OpsiBackupFileError(
				f'Could not read backend configuration: Missing directory "{self.BACKEND_CONF_DIR}"'
			)

		backends = {}
		for entry in os.listdir(self.BACKEND_CONF_DIR):
			if entry.endswith(".conf"):
				name = entry.split(".")[0].lower()
				if name in backends:
					raise OpsiBackupFileError(
						"Multiple backends with the same name are not supported."
					)

				backendGlobals = {"config": {}, "module": "", "socket": socket}
				backendFile = os.path.join(self.BACKEND_CONF_DIR, entry)
				try:
					with open(backendFile, encoding="utf-8") as confFile:
						exec(confFile.read(), backendGlobals)

					backends[name] = {
						"name": name,
						"config": backendGlobals["config"],
						"module": backendGlobals["module"],
						"dispatch": (name in dispatchedBackends),
					}
				except Exception as err:
					logger.warning('Failed to read backend config "%s": %s', entry, err)

		return backends

	def _getBackends(self, type=None):
		if not self._backends:
			self._backends = self._readBackendConfiguration()

		for backend in self._backends.values():
			if type is None or backend["module"].lower() == type:
				yield backend

	def _generateNewArchive(self, suffix=None):
		return os.path.join(self.tempdir, self._generateArchiveName(suffix=suffix))

	def _generateArchiveName(self, suffix=None):
		currentTime = datetime.datetime.now()
		timestamp = str(currentTime).replace(" ", "_").replace(":", "-")
		name = (
			f"{self.sysinfo['hostname']}_{self.sysinfo['opsiVersion']}_{timestamp}.tar"
		)
		if suffix:
			name += f".{suffix}"
		return name

	@staticmethod
	def getSysInfo():
		"""
		Get the current system information as a dict.

		System information is hostname, domainname, FQDN, distribution,
		system version, distribution ID and the version of opsi in use.

		:rtype: dict
		"""
		sysinfo = SysInfo()

		return {
			"hostname": sysinfo.hostname,
			"fqdn": sysinfo.fqdn,
			"domainname": sysinfo.domainname,
			"distribution": sysinfo.distribution,
			"sysVersion": sysinfo.sysVersion,
			"distributionId": sysinfo.distributionId,
			"opsiVersion": LIBRARY_VERSION,
		}

	def _readSysInfo(self):
		sysInfo = {}
		with closing(self.extractfile(f"{self.CONTROL_DIR}/sysinfo")) as fp:
			for line in fp:
				key, value = line.decode().split(":")
				sysInfo[key.strip()] = value.strip()

		return sysInfo

	def _readChecksumFile(self):
		checksums = {}
		with closing(self.extractfile(f"{self.CONTROL_DIR}/checksums")) as fp:
			for line in fp:
				key, value = line.decode().split(" ", 1)
				checksums[value.strip()] = key.strip()

		return checksums

	def _addContent(self, path, sub=None):
		"""
		Add content to an backup.

		Content can be a file or directory.
		In case of a directory it will be added with all of its content.

		:param path: Path to the content to add.
		:type path: str
		:param sub: If given `path` will be alterd so that the first \
element of the tuple is replace with the second element.
		:type sub: tuple(str, str) or None
		"""
		dest = path
		if sub:
			dest = dest.replace(sub[0], sub[1])
		dest = os.path.join(self.CONTENT_DIR, dest)

		if os.path.isdir(path):
			self.add(path, dest, recursive=False)
			for entry in os.listdir(path):
				self._addContent(os.path.join(path, entry), sub=sub)
		else:
			if not os.path.exists(path):
				logger.info("'%s' does not exist. Skipping.", path)
				return

			checksum = sha1()
			with open(path, "rb") as file:
				for chunk in file:
					checksum.update(chunk)

			self._filemap[dest] = checksum.hexdigest()

			self.add(path, dest)

	def _addChecksumFile(self):
		string = StringIO()
		size = 0
		for path, checksum in self._filemap.items():
			size += string.write(f"{checksum} {path}\n")
		string.seek(0)

		info = tarfile.TarInfo(name=f"{self.CONTROL_DIR}/checksums")
		info.size = size

		self.addfile(info, BytesIO(string.getvalue().encode()))

	def _addSysInfoFile(self):
		string = StringIO()
		size = 0
		for key, value in self.sysinfo.items():
			size += string.write(f"{key}: {value}\n")
		string.seek(0)

		info = tarfile.TarInfo(name=f"{self.CONTROL_DIR}/sysinfo")
		info.size = size

		self.addfile(info, BytesIO(string.getvalue().encode()))

	def verify(self):
		if self.mode.startswith("w"):
			raise OpsiBackupFileError("Backup archive is not finalized.")

		for member in self.getmembers():
			if member.isfile() and member.name.startswith(self.CONTENT_DIR):
				checksum = self._filemap[member.name]
				filesum = sha1()

				count = 0
				with closing(self.extractfile(member)) as fp:
					for chunk in fp:
						count += len(chunk)
						filesum.update(chunk)

				if checksum != filesum.hexdigest():
					logger.trace(
						"Read %s bytes from file %s, resulting in checksum %s",
						count,
						member.name,
						filesum.hexdigest(),
					)
					raise OpsiBackupFileError(
						f"Backup Archive is not valid: File {member.name} is corrupted"
					)

		return True

	def close(self):
		if self.mode.startswith("w"):
			self._addChecksumFile()
			self._addSysInfoFile()
		tarfile.TarFile.close(self)
		if self.fileobj and self._extfileobj:
			self.fileobj.close()

	def _extractFile(self, member, dest):
		tf, path = tempfile.mkstemp(dir=self.tempdir)

		try:
			checksum = self._filemap[member.name]
			filesum = sha1()

			with closing(self.extractfile(member.name)) as fp:
				for chunk in fp:
					filesum.update(chunk)
					os.write(tf, chunk)

			if filesum.hexdigest() != checksum:
				raise OpsiBackupFileError(
					f"Error restoring file {member}: checksum missmatch."
				)

			shutil.copyfile(path, dest)
			os.utime(dest, (member.mtime, member.mtime))
			try:
				os.chmod(dest, member.mode)
				os.chown(
					dest, pwd.getpwnam(member.uname)[2], grp.getgrnam(member.gname)[2]
				)
			except Exception as err:
				logger.warning(
					"Failed to restore file permissions on %s: %s", dest, err
				)
		finally:
			os.close(tf)
			os.remove(path)

	def backupConfiguration(self):
		self._addContent(self.CONF_DIR, sub=(self.CONF_DIR, "CONF"))

	def hasConfiguration(self):
		for member in self.getmembers():
			if member.name.startswith(os.path.join(self.CONTENT_DIR, "CONF")):
				return True
		return False

	def restoreConfiguration(self):
		first = True

		for member in self.getmembers():
			if member.name.startswith(os.path.join(self.CONTENT_DIR, "CONF")):
				if first:
					shutil.rmtree(self.CONF_DIR, ignore_errors=True)
					os.makedirs(self.CONF_DIR)
					first = False
				dest = member.name.replace(
					os.path.join(self.CONTENT_DIR, "CONF"), self.CONF_DIR
				)

				if member.issym():
					os.symlink(member.linkname, dest)
				elif member.isdir():
					if not os.path.exists(dest):
						os.makedirs(dest, mode=member.mode)
						os.chown(
							dest,
							pwd.getpwnam(member.uname)[2],
							grp.getgrnam(member.gname)[2],
						)
				else:
					self._extractFile(member, dest)

	def _hasBackend(self, backend, name=None):
		if name:
			backend = os.path.join(backend, name)

		for member in self.getmembers():
			if member.name.startswith(
				os.path.join(self.CONTENT_DIR, os.path.join("BACKENDS", backend))
			):
				return True
		return False

	def hasFileBackend(self, name=None):
		return self._hasBackend("FILE", name=name)

	def backupFileBackend(self, auto=False):
		for backend in self._getBackends("file"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning(
						"Backing up backend %s although it's currently not in use.",
						backend["name"],
					)
				baseDir = backend["config"]["baseDir"]
				self._addContent(
					baseDir, sub=(baseDir, f"BACKENDS/FILE/{backend['name']}")
				)

				hostKeyFile = backend["config"]["hostKeyFile"]
				if baseDir not in os.path.dirname(hostKeyFile):
					# File resides outside of baseDir
					self._addContent(
						hostKeyFile,
						sub=(
							os.path.dirname(hostKeyFile),
							f"BACKENDS/FILE_HOSTKEYS/{backend['name']}",
						),
					)

	def restoreFileBackend(self, auto=False):
		if not self.hasFileBackend():
			raise OpsiBackupBackendNotFound("No File Backend found in backup archive")

		for backend in self._getBackends("file"):
			if not auto or backend["dispatch"]:
				backendBackupPath = os.path.join(
					self.CONTENT_DIR, f"BACKENDS/FILE/{backend['name']}"
				)
				hostKeyBackupPath = os.path.join(
					self.CONTENT_DIR, f"BACKENDS/FILE_HOSTKEYS/{backend['name']}"
				)
				baseDir = backend["config"]["baseDir"]

				members = self.getmembers()
				for member in members:
					if member.name.startswith(backendBackupPath):
						dest = member.name.replace(backendBackupPath, baseDir)

						if member.isfile():
							self._extractFile(member, dest)
						else:
							if not os.path.exists(dest):
								os.makedirs(dest, mode=member.mode)
								os.chown(
									dest,
									pwd.getpwnam(member.uname)[2],
									grp.getgrnam(member.gname)[2],
								)
					elif member.name.startswith(hostKeyBackupPath):
						assert member.isfile(), "No directory expected."
						hostKeyFile = backend["config"]["hostKeyFile"]
						self._extractFile(member, hostKeyFile)

	def backupDHCPBackend(self, auto=False):
		for backend in self._getBackends("dhcpd"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning(
						"Backing up backend %s although it's currently not in use.",
						backend["name"],
					)

				dhcpdConfigFile = backend["config"].get("dhcpdConfigFile")
				if dhcpdConfigFile:
					self._addContent(
						dhcpdConfigFile,
						sub=(
							os.path.dirname(dhcpdConfigFile),
							f"BACKENDS/DHCP/{backend['name']}",
						),
					)

	def hasDHCPBackend(self, name=None):
		return self._hasBackend("DHCP", name=name)

	def restoreDHCPBackend(self, auto=False):
		if not self.hasDHCPBackend():
			raise OpsiBackupBackendNotFound("No DHCPD Backend found in backup archive")

		for backend in self._getBackends("dhcpd"):
			if not auto or backend["dispatch"]:
				members = self.getmembers()

				file = backend["config"]["dhcpdConfigFile"]
				if os.path.exists(file):
					os.remove(file)

				for member in members:
					if member.name.startswith(
						os.path.join(
							self.CONTENT_DIR, f"BACKENDS/DHCP/{backend['name']}"
						)
					):
						self._extractFile(member, backend["config"]["dhcpdConfigFile"])

	def hasMySQLBackend(self, name=None):
		return self._hasBackend("MYSQL", name=name)

	def backupMySQLBackend(self, flushLogs=False, auto=False):
		for backend in self._getBackends("mysql"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning(
						"Backing up backend %s although it's currently not in use.",
						backend["name"],
					)

				# Early check for available command to not leak
				# credentials if mysqldump is missing
				mysqldumpCmd = OPSI.System.which("mysqldump")

				defaultsFile = createMySQLDefaultsFile(
					"mysqldump",
					backend["config"]["username"],
					backend["config"]["password"],
				)

				address = backend["config"]["address"]
				if address.startswith("/"):
					address = f"--socket={address}"
				else:
					address = f"--host={address}"

				cmd = [
					mysqldumpCmd,
					# --defaults-file has to be the first argument
					f"--defaults-file={defaultsFile}",
					address,
					"--lock-tables",
					"--add-drop-table",
				]
				if flushLogs:
					logger.debug("Flushing mysql table logs.")
					cmd.append("--flush-log")
				cmd.append(backend["config"]["database"])
				logger.trace("Prepared mysqldump command: '%s'", cmd)

				fd, name = tempfile.mkstemp(dir=self.tempdir)
				try:
					with subprocess.Popen(
						cmd,
						stdout=subprocess.PIPE,
						stderr=subprocess.PIPE,
						env=get_subprocess_environment(),
					) as proc:
						flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
						fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)

						out = proc.stdout.readline()

						try:
							collectedErrors = [
								proc.stderr.readline().decode("utf-8", "replace")
							]
						except Exception:
							collectedErrors = []
						lastErrors = collections.deque(collectedErrors, maxlen=10)

						while not proc.poll() and out:
							os.write(fd, out)
							out = proc.stdout.readline()

							try:
								currentError = (
									proc.stderr.readline()
									.decode("utf-8", "replace")
									.strip()
								)
								if currentError:
									lastErrors.append(currentError)
									collectedErrors.append(currentError)
							except Exception:
								continue

							if lastErrors.maxlen == len(lastErrors):
								only_one_err_on_last_errors = True
								firstError = lastErrors[0]
								for err in list(lastErrors)[1:]:
									if firstError != err:
										only_one_err_on_last_errors = False
										break

								if only_one_err_on_last_errors:
									logger.debug(
										"Aborting: Only one message in stderr: '%s'",
										firstError,
									)
									break

						if proc.returncode not in (0, None):
							raise OpsiBackupFileError(
								f"MySQL dump failed for backend {backend['name']}: {''.join(collectedErrors)}"
							)

						self._addContent(
							name,
							(name, f"BACKENDS/MYSQL/{backend['name']}/database.sql"),
						)
				finally:
					os.close(fd)
					os.remove(name)
					os.remove(defaultsFile)

	def restoreMySQLBackend(self, auto=False):
		if not self.hasMySQLBackend():
			raise OpsiBackupBackendNotFound("No MySQL Backend found in backup archive")

		for backend in self._getBackends("mysql"):
			if not auto or backend["dispatch"]:
				fd, name = tempfile.mkstemp(dir=self.tempdir)
				defaultsFile = None
				try:
					os.chmod(name, 0o770)
					for member in self.getmembers():
						if member.name == os.path.join(
							self.CONTENT_DIR,
							f"BACKENDS/MYSQL/{backend['name']}/database.sql",
						):
							self._extractFile(member, name)

					# Early check for available command to not leak
					# credentials if mysqldump is missing
					mysqlCmd = OPSI.System.which("mysql")
					defaultsFile = createMySQLDefaultsFile(
						"mysql",
						backend["config"]["username"],
						backend["config"]["password"],
					)

					address = backend["config"]["address"]
					if address.startswith("/"):
						address = f"--socket={address}"
					else:
						address = f"--host={address}"

					cmd = [
						mysqlCmd,
						# --defaults-file has to be the first argument
						f"--defaults-file={defaultsFile}",
						address,
					]
					logger.trace("Running command: '%s'", cmd)
					with subprocess.Popen(
						cmd,
						stdin=subprocess.PIPE,
						stdout=subprocess.PIPE,
						stderr=subprocess.STDOUT,
						env=get_subprocess_environment(),
					) as proc:
						proc.stdin.write(
							f"DROP DATABASE IF EXISTS {backend['config']['database']}; CREATE DATABASE {backend['config']['database']};".encode()
						)
						proc.stdin.close()

						out = proc.stdout.readline()
						while proc.poll() is None:
							line = proc.stdout.readline()
							if line:
								out += line
							else:
								time.sleep(0.01)

						if proc.returncode not in (0, None):
							raise OpsiBackupFileError(
								f"Failed to restore MySQL Backend: {out.decode()}"
							)

					cmd.append(backend["config"]["database"])
					logger.trace("Running command: '%s'", cmd)
					with subprocess.Popen(
						cmd,
						stdin=fd,
						stdout=subprocess.PIPE,
						stderr=subprocess.STDOUT,
						env=get_subprocess_environment(),
					) as proc:
						out = proc.stdout.readline()
						while proc.poll() is None:
							line = proc.stdout.readline()
							if line:
								out += line
							else:
								time.sleep(0.01)

						if proc.returncode not in (0, None):
							raise OpsiBackupFileError(
								f"Failed to restore MySQL Backend: {out.decode()}"
							)
				finally:
					os.close(fd)
					os.remove(name)
					if defaultsFile:
						os.remove(defaultsFile)


def createMySQLDefaultsFile(program, username, password):
	"""
	Create a secure file with mysql defaults.
	This can usually be passed as --defaults-file to most mysql commands.
	Returns the path to the file.

	The caller has to make sure that the file will be deleted afterwards!

	:param program: Name of the section in the config file
	:type program: str
	:param username: Username to use
	:type username: str
	:param password: Password to use
	:type password: str
	:returns: Path to the created file
	:rtype: str
	"""
	if '"' in username:
		raise ValueError("Double quotation marks not allowed in username")
	if '"' in password:
		raise ValueError("Double quotation marks not allowed in password")

	# password enclosed in double quotes (not allowed in MySQL passwords) to avoid special character interpretation
	with tempfile.NamedTemporaryFile(mode="wt", delete=False) as cFile:
		cFile.write(
			(f"[{program}]\n" f'user = "{username}"\n' f'password = "{password}"\n')
		)
		return cFile.name
