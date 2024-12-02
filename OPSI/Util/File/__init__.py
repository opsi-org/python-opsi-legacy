# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Working with files.

This includes classes not only useful for reading and writing but
parsing files for information.
"""

import builtins
import codecs
import functools
import locale
import os
import re
import threading
import time
from configparser import (
	ConfigParser,
	RawConfigParser,
)
from io import StringIO
from itertools import islice
from pathlib import Path

from opsicommon.logging import get_logger
from pyzsync import create_zsync_file

from OPSI.Exceptions import BackendBadValueError, BackendMissingDataError
from OPSI.System import execute, which  # noqa: F401
from OPSI.Types import (
	forceArchitecture,
	forceBool,
	forceDict,
	forceEmailAddress,
	forceFilename,
	forceHardwareAddress,
	forceHardwareDeviceId,
	forceHardwareVendorId,
	forceHostname,
	forceInt,
	forceIPAddress,
	forceList,
	forceOct,
	forceProductId,
	forceTime,
	forceUnicode,
	forceUnicodeList,
	forceUnicodeLower,
	forceUnicodeLowerList,
)
from OPSI.Util import ipAddressInNetwork

if os.name == "posix":
	import fcntl
	import grp
	import pwd

if os.name == "nt":
	# pyright: reportMissingImports=false
	import pywintypes
	import win32con
	import win32file

	pywintypeserror = pywintypes.error
else:
	win32con = None
	win32file = None
	pywintypes = None
	pywintypeserror = IOError

logger = get_logger("opsi.general")


def requiresParsing(function):
	"""
	Decorator that calls parse() on unparsed configs.
	"""

	@functools.wraps(function)
	def parsedFile(self, *args, **kwargs):
		if not self._parsed:
			self.parse()

		return function(self, *args, **kwargs)

	return parsedFile


class File:
	def __init__(self, filename):
		self._filename = forceFilename(filename)
		self._fileHandle = None
		self.fileState = None

	def getFilename(self):
		return self._filename

	def setFilename(self, filename):
		self._filename = forceFilename(filename)

	def exists(self):
		return os.path.exists(self._filename)

	def delete(self):
		if os.path.exists(self._filename):
			os.unlink(self._filename)

	def chown(self, user, group):
		if os.name == "nt":
			logger.warning("Not implemented on windows")
			return
		uid = -1
		if isinstance(user, int):
			if user > -1:
				uid = user
		elif user is not None:
			try:
				uid = pwd.getpwnam(user)[2]
			except KeyError as err:
				raise ValueError(f"Unknown user '{user}'") from err

		gid = -1
		if isinstance(group, int):
			if group > -1:
				gid = group
		elif group is not None:
			try:
				gid = grp.getgrnam(group)[2]
			except KeyError as err:
				raise ValueError(f"Unknown group '{group}'") from err

		os.chown(self._filename, uid, gid)

	def chmod(self, mode):
		mode = forceOct(mode)
		os.chmod(self._filename, mode)

	def create(self, user=None, group=None, mode=None):
		if not os.path.exists(self._filename):
			self.open("w")
			self.close()

		if user is not None or group is not None:
			self.chown(user, group)
		if mode is not None:
			self.chmod(mode)

	def open(self, mode="r"):
		self._fileHandle = builtins.open(self._filename, mode)
		return self._fileHandle

	def close(self):
		if not self._fileHandle:
			return
		self._fileHandle.close()
		self._fileHandle = None

	def __getattr__(self, attr):
		if attr in self.__dict__:
			return self.__dict__[attr]
		if self.__dict__["_fileHandle"]:
			return getattr(self.__dict__["_fileHandle"], attr)
		return None

	def __getstate__(self):
		state = self.__dict__.copy()
		file = self._fileHandle
		state["_fileHandle"] = None
		state["fileState"] = {}
		state["fileState"]["closed"] = file.closed
		state["fileState"]["encoding"] = file.encoding
		state["fileState"]["mode"] = file.mode
		state["fileState"]["name"] = file.name
		state["fileState"]["newlines"] = file.newlines
		state["fileState"]["softspace"] = file.softspace
		state["fileState"]["position"] = file.tell()
		return state

	def __setstate__(self, state):
		self.__dict__, self.fileState = state.copy(), None
		self.setFilename(state["fileState"]["name"])
		if not state["fileState"]["closed"]:
			self.open(state["fileState"]["mode"])
			self._fileHandle.encoding = state["fileState"]["encoding"]
			self._fileHandle.newlines = state["fileState"]["newlines"]
			self._fileHandle.softspace = state["fileState"]["softspace"]
			self.seek(state["fileState"]["position"])


class LockableFile(File):
	_fileLockLock = threading.Lock()

	def __init__(self, filename, lockFailTimeout=2000):
		File.__init__(self, filename)
		self._lockFailTimeout = forceInt(lockFailTimeout)

	def open(self, mode="r", encoding=None, errors="replace"):
		truncate = False
		if mode in ("w", "wb") and os.path.exists(self._filename):
			if mode == "w":
				mode = "r+"
				truncate = True
			elif mode == "wb":
				mode = "rb+"
				truncate = True
		if encoding:
			self._fileHandle = codecs.open(self._filename, mode, encoding, errors)
		else:
			self._fileHandle = builtins.open(self._filename, mode)
		self._lockFile(mode)
		if truncate:
			self._fileHandle.seek(0)
			self._fileHandle.truncate()
		return self._fileHandle

	def close(self):
		if not self._fileHandle:
			return
		self._fileHandle.flush()
		File.close(self)

	def _lockFile(self, mode="r"):
		timeout = 0
		while timeout < self._lockFailTimeout:
			# While not timed out and not locked
			logger.debug(
				"Trying to lock file '%s' (%s/%s)",
				self._filename,
				timeout,
				self._lockFailTimeout,
			)
			try:
				if os.name == "posix":
					# Flags for exclusive, non-blocking lock
					flags = fcntl.LOCK_EX | fcntl.LOCK_NB
					if mode in ("r", "rb"):
						# Flags for shared, non-blocking lock
						flags = fcntl.LOCK_SH | fcntl.LOCK_NB
					fcntl.flock(self._fileHandle.fileno(), flags)
				elif os.name == "nt":
					flags = (
						win32con.LOCKFILE_EXCLUSIVE_LOCK
						| win32con.LOCKFILE_FAIL_IMMEDIATELY
					)
					if mode in ("r", "rb"):
						flags = win32con.LOCKFILE_FAIL_IMMEDIATELY
					hfile = win32file._get_osfhandle(self._fileHandle.fileno())
					win32file.LockFileEx(
						hfile, flags, 0, 0x7FFF0000, pywintypes.OVERLAPPED()
					)
			except (IOError, pywintypeserror):
				# increase timeout counter, sleep 100 millis
				timeout += 100
				time.sleep(0.1)
				continue
			# File successfully locked
			logger.debug("File '%s' locked after %d millis", self._filename, timeout)
			return self._fileHandle

		File.close(self)
		# File lock failed => raise IOError
		raise IOError(
			f"Failed to lock file '{self._filename}' after {self._lockFailTimeout} millis"
		)

	def _unlockFile(self):
		if not self._fileHandle:
			return
		if os.name == "posix":
			fcntl.flock(self._fileHandle.fileno(), fcntl.LOCK_UN)
		elif os.name == "nt":
			hfile = win32file._get_osfhandle(self._fileHandle.fileno())
			win32file.UnlockFileEx(hfile, 0, 0x7FFF0000, pywintypes.OVERLAPPED())


class TextFile(LockableFile):
	def __init__(self, filename, lockFailTimeout=2000):
		LockableFile.__init__(self, filename, lockFailTimeout)
		self._lines = []
		self._lineSeperator = "\n"

	def open(self, mode="r", encoding="utf-8", errors="replace"):
		return LockableFile.open(self, mode, encoding, errors)

	def write(self, str):
		if not self._fileHandle:
			raise IOError("File not opened")
		str = forceUnicode(str)
		self._fileHandle.write(str)

	def readlines(self):
		self._lines = []
		if not self._fileHandle:
			for encoding in ("utf-8", "utf-16", "latin_1", "cp1252", "replace"):
				errors = "strict"
				if encoding == "replace":
					errors = "replace"
					encoding = "utf-8"

				self.open(encoding=encoding, errors=errors)
				try:
					self._lines = self._fileHandle.readlines()
					self.close()
					break
				except ValueError:
					self.close()
					continue
		return self._lines

	def getLines(self):
		return self._lines

	def writelines(self, sequence=[]):
		if not self._fileHandle:
			raise IOError("File not opened")
		if sequence:
			self._lines = forceUnicodeList(sequence)
		for index, current in enumerate(self._lines):
			self._lines[index] = current + self._lineSeperator
		self._fileHandle.writelines(self._lines)


class ChangelogFile(TextFile):
	"""
	Files containing changelogs.

	These follow the Debian style changelogs:

	package (version) distribution(s); urgency=urgency
		[optional blank line(s), stripped]
	  * change details
		 more change details
		  [blank line(s), included]
	  * even more change details
		  [optional blank line(s), stripped]
	[one space]-- maintainer name <email address>[two spaces]date
	"""

	releaseLineRegex = re.compile(
		r"^\s*(\S+)\s+\(([^\)]+)\)\s+([^;]+);\s+urgency=(\S+)\s*$"
	)

	def __init__(self, filename, lockFailTimeout=2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._entries = []

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		self._entries = []
		currentEntry = {}
		for lineNum, line in enumerate(self._lines):
			try:
				match = self.releaseLineRegex.search(line)
				if match:
					if currentEntry:
						self.addEntry(currentEntry)

					currentEntry = {
						"package": match.group(1),
						"version": match.group(2),
						"release": match.group(3),
						"urgency": match.group(4),
						"changelog": [],
						"maintainerName": "",
						"maintainerEmail": "",
						"date": None,
					}
					continue

				if line.startswith(" --"):
					if "  " not in line:
						raise ValueError(
							"maintainer must be separated from date using two spaces"
						)
					if not currentEntry or currentEntry["date"]:
						raise ValueError("found trailer out of release")

					(maintainer, date) = line[3:].strip().split("  ", 1)
					email = ""
					try:
						(maintainer, email) = maintainer.split("<", 1)
						maintainer = maintainer.strip()
						email = email.strip().replace("<", "").replace(">", "")
					except ValueError:
						pass

					currentEntry["maintainerName"] = maintainer
					currentEntry["maintainerEmail"] = email
					if "+" in date:
						date = date.split("+")[0]
					currentEntry["date"] = time.strptime(
						date.strip(), "%a, %d %b %Y %H:%M:%S"
					)
					changelog = []
					buf = []
					for cline in currentEntry["changelog"]:
						if not changelog and not cline.strip():
							continue
						if not cline.strip():
							buf.append(forceUnicode(cline))
						else:
							changelog.extend(buf)
							buf = []
							changelog.append(forceUnicode(cline))
					currentEntry["changelog"] = forceUnicodeList(changelog)

				else:
					if not currentEntry and line.strip():
						raise ValueError("text not in release")
					if currentEntry:
						currentEntry["changelog"].append(line.rstrip())
			except Exception as err:
				raise ValueError(f"Parse error in line {lineNum}: {err}") from err
		if currentEntry:
			self.addEntry(currentEntry)
		self._parsed = True
		return self._entries

	def generate(self):
		# get current locale
		loc = locale.getlocale()
		locale.setlocale(locale.LC_ALL, "C")
		try:
			if not self._entries:
				raise ValueError("No entries to write")
			self._lines = []
			for entry in self._entries:
				self._lines.append(
					f"{entry['package']} ({entry['version']}) {entry['release']}; urgency={entry['urgency']}"
				)
				self._lines.append("")
				for line in entry["changelog"]:
					self._lines.append(line)
				if self._lines[-1].strip():
					self._lines.append("")
				self._lines.append(
					f" -- {entry['maintainerName']} <{entry['maintainerEmail']}>  {time.strftime('%a, %d %b %Y %H:%M:%S +0000', entry['date'])}"
				)
				self._lines.append("")

			self.open("w")
			self.writelines()
			self.close()
		finally:
			if loc:
				try:
					locale.setlocale(locale.LC_ALL, loc)
				except Exception:
					pass

	@requiresParsing
	def getEntries(self):
		return self._entries

	def setEntries(self, entries):
		entries = forceList(entries)
		self._entries = []
		for entry in entries:
			self.addEntry(entry)

	def addEntry(self, entry):
		entry = forceDict(entry)
		for key in (
			"package",
			"version",
			"release",
			"urgency",
			"changelog",
			"maintainerName",
			"maintainerEmail",
			"date",
		):
			try:
				entry[key]
			except KeyError as err:
				raise KeyError(f"Missing key '{key}' in entry {entry}") from err

		entry["package"] = forceProductId(entry["package"])
		entry["version"] = forceUnicode(entry["version"])
		entry["release"] = forceUnicode(entry["release"])
		entry["urgency"] = forceUnicode(entry["urgency"])
		entry["changelog"] = forceUnicodeList(entry["changelog"])
		entry["maintainerName"] = forceUnicode(entry["maintainerName"])
		entry["maintainerEmail"] = forceEmailAddress(entry["maintainerEmail"])
		entry["date"] = forceTime(entry["date"])
		self._entries.append(entry)


class ConfigFile(TextFile):
	def __init__(
		self, filename, lockFailTimeout=2000, commentChars=[";", "#"], lstrip=True
	):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._commentChars = forceList(commentChars)
		self._lstrip = forceBool(lstrip)
		self._parsed = False

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		lines = []
		for line in self._lines:
			sline = line.strip()
			if not sline or sline[0] in self._commentChars:
				continue

			if self._lstrip:
				line = line.strip()
			else:
				line = line.rstrip()

			for cc in self._commentChars:
				if cc not in line:
					continue

				parts = line.split(cc)
				quote = 0
				doublequote = 0
				cut = -1
				for i, part in enumerate(islice(parts, len(parts) - 1)):
					quote += part.count("'")
					doublequote += part.count('"')
					if len(part) > 0 and part[-1] == "\\":
						# escaped comment
						continue

					if not quote % 2 and not doublequote % 2:
						cut = i
						break

				if cut > -1:
					line = cc.join(parts[: cut + 1])

			if not line:
				continue

			lines.append(line)
		self._parsed = True
		return lines


class IniFile(ConfigFile):
	optionMatch = re.compile(r"^([^:=]+)\s*([:=].*)$")

	def __init__(self, filename, lockFailTimeout=2000, ignoreCase=True, raw=True):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[";", "#"])
		self._ignoreCase = forceBool(ignoreCase)
		self._raw = forceBool(raw)
		self._configParser = None
		self._parsed = False
		self._sectionSequence = []
		self._keepOrdering = False

	def setSectionSequence(self, sectionSequence):
		self._sectionSequence = forceUnicodeList(sectionSequence)

	def setKeepOrdering(self, keepOrdering):
		self._keepOrdering = forceBool(keepOrdering)

	def parse(self, lines=None, returnComments=False):
		logger.debug("Parsing ini file '%s'", self._filename)
		start = time.time()
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False

		lines = []
		currentSection = None
		comments = {}
		currentComments = []
		for line in self._lines:
			line = line.strip()
			if not line:
				if returnComments:
					currentComments.append("")
				continue
			if line.startswith("["):
				currentSection = line.split("[", 1)[1].split("]", 1)[0].strip()
				if returnComments:
					comments[currentSection] = {"[]": currentComments}
					currentComments = []
				if self._ignoreCase:
					line = line.lower()
			if line[0] in self._commentChars and not returnComments:
				continue
			comment = None
			for cc in self._commentChars:
				if cc not in line:
					continue

				parts = line.split(cc)
				quote = 0
				doublequote = 0
				cut = -1
				for i, part in enumerate(islice(parts, len(parts) - 1)):
					quote += part.count("'")
					doublequote += part.count('"')
					if len(part) > 0 and part[-1] == "\\":
						# escaped comment
						continue
					if not quote % 2 and not doublequote % 2:
						cut = i
						break

				if cut > -1:
					line = cc.join(parts[: cut + 1])
					if returnComments:
						comment = cc + cc.join(parts[cut + 1 :])

			if self._ignoreCase or comment:
				match = self.optionMatch.search(line)
				if match:
					option = match.group(1)
					if self._ignoreCase:
						option = option.lower()
						line = option + match.group(2)
					if currentComments and currentSection:
						comments[currentSection][option.strip()] = currentComments
						currentComments = []
			if comment:
				currentComments.append(comment)
			if not line:
				continue
			lines.append(line)
		self._configParser = None
		if self._raw:
			self._configParser = RawConfigParser()
		else:
			self._configParser = ConfigParser()

		try:
			self._configParser.read_file(StringIO("\r\n".join(lines)))
		except Exception as err:
			raise RuntimeError(
				f"Failed to parse ini file '{self._filename}': {err}"
			) from err

		logger.debug("Finished reading file after %0.3f seconds", time.time() - start)

		self._parsed = True
		if returnComments:
			return (self._configParser, comments)
		return self._configParser

	def generate(self, configParser, comments={}):
		self._configParser = configParser

		if not self._configParser:
			raise ValueError("Got no data to write")

		sectionSequence = []
		optionSequence = {}
		if self._keepOrdering and os.path.exists(self._filename):
			for line in self.readlines():
				line = line.strip()
				if not line or line[0] in self._commentChars:
					continue
				if line.startswith("["):
					section = line.split("[", 1)[1].split("]", 1)[0].strip()
					sectionSequence.append(section)
				elif "=" in line:
					option = line.split("=")[0].strip()
					if sectionSequence[-1] not in optionSequence:
						optionSequence[sectionSequence[-1]] = []
					optionSequence[sectionSequence[-1]].append(option)
		else:
			sectionSequence = list(self._sectionSequence)

		sectionSequence.reverse()
		sections = self._configParser.sections()
		sections.sort()
		for section in sectionSequence:
			if section in sections:
				logger.trace("Moving section %s to top", section)
				sections.remove(section)
				sections.insert(0, section)
			logger.trace("Section sequence: %s", sections)

		self._lines = []
		for section in sections:
			section = forceUnicode(section)
			if comments:
				for cline in comments.get(section, {}).get("[]", []):
					self._lines.append(forceUnicode(cline))
			self._lines.append(f"[{section}]")
			options = self._configParser.options(section)
			options.sort()
			for num, option in enumerate(options):
				options[num] = forceUnicode(option)
			optseq = optionSequence.get(section, [])
			if optseq:
				optseq.reverse()
				for option in optseq:
					if option in options:
						options.remove(option)
						options.insert(0, option)
			for option in options:
				if comments:
					for cline in comments.get(section, {}).get(option, []):
						self._lines.append(forceUnicode(cline))
				self._lines.append(
					f"{option} = {self._configParser.get(section, option)}"
				)
			if not comments:
				self._lines.append("")
		self.open("w")
		self.writelines()
		self.close()


class InfFile(ConfigFile):
	sectionRegex = re.compile(r"\[\s*([^\]]+)\s*\]")
	pciDeviceRegex = re.compile(r"VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)", re.IGNORECASE)
	hdaudioDeviceRegex = re.compile(
		r"HDAUDIO\\.*VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)", re.IGNORECASE
	)
	usbDeviceRegex = re.compile(
		r"USB.*VID_([\da-fA-F]+)&PID_([\da-fA-F]+)", re.IGNORECASE
	)
	acpiDeviceRegex = re.compile(r"ACPI\\(\S+)_-_(\S+)", re.IGNORECASE)
	varRegex = re.compile(r"%([^%]+)%")
	classRegex = re.compile(r"class\s*=")

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[";", "#"])
		self._sourceDisksNames = []
		self._devices = []

	@requiresParsing
	def getDevices(self):
		return self._devices

	@requiresParsing
	def getSourceDisksNames(self):
		return self._sourceDisksNames

	def isDeviceKnown(self, vendorId, deviceId, deviceType=None):
		try:
			vendorId = forceHardwareVendorId(vendorId)
			deviceId = forceHardwareDeviceId(deviceId)
		except Exception as err:
			logger.error(err)
			return False
		if not self._parsed:
			self.parse()
		for dev in self._devices:
			if (
				(not deviceType or (dev.get("type") == deviceType))
				and (dev.get("vendor") == vendorId)
				and (not dev.get("device") or (dev["device"] == deviceId))
			):
				return True
		return False

	def parse(self, lines=None):
		logger.debug("Parsing inf file %s", self._filename)
		lines = ConfigFile.parse(self, lines)
		self._parsed = False
		self._devices = []

		path = os.path.dirname(self._filename)

		deviceClass = "???"
		deviceSections = []
		appendNext = False
		newLines = []
		for line in lines:
			if appendNext:
				newLines[-1] = lines[-1][:-1] + line
			else:
				newLines.append(line)

			appendNext = line.endswith("\\")
		lines = newLines

		# Get strings
		logger.trace("   - Getting strings")
		strings = {}
		section = ""
		for line in lines:
			match = re.search(self.sectionRegex, line)
			if match:
				if section.lower() == "strings":
					break
				section = match.group(1)
			else:
				if section.lower() == "strings":
					try:
						(var, string) = line.split("=", 1)
						string = string.strip()
						if string.startswith('"') and string.endswith('"'):
							string = string[1:-1]
						strings[var.strip().lower()] = string
					except Exception:
						pass
		logger.trace("        got strings: %s", strings)

		# Get source disks names
		self._sourceDisksNames = []
		sectionFound = False
		for line in lines:
			match = re.search(self.sectionRegex, line)
			if match:
				section = match.group(1)
				sectionFound = section.lower().startswith("sourcedisksnames")
				continue

			if sectionFound:
				if "=" not in line:
					continue
				name = line.split("=")[1].split(",")[0].strip()
				name = strings.get(name.replace("%", "").lower(), name)
				if name not in self._sourceDisksNames:
					self._sourceDisksNames.append(name)

		# Get devices
		logger.trace("   - Getting devices")
		section = ""
		for line in lines:
			match = re.search(self.sectionRegex, line)
			if match:
				if section.lower() == "manufacturer":
					break
				section = match.group(1)
			else:
				if section.lower() == "version":
					if line.lower().startswith("class"):
						if re.search(self.classRegex, line.lower()):
							deviceClass = line.split("=")[1].strip().lower()
							match = re.search(self.varRegex, deviceClass)
							if match:
								var = match.group(1).lower()
								if var in strings:
									deviceClass = deviceClass.replace(
										f"%{var}%", strings[var]
									)

				elif section.lower() == "manufacturer":
					if line and "=" in line:
						for dev in line.split("=")[1].split(","):
							deviceSections.append(dev.strip())

		devSections = set()
		for deviceSection in deviceSections:
			for i in deviceSection.split("."):
				devSections.add(i)
		deviceSections = devSections
		logger.trace("      - Device sections: %s", ", ".join(deviceSections))

		def isDeviceSection(section):
			if section in deviceSections:
				return True
			for sec in section.split("."):
				if sec not in deviceSections:
					return False
			return True

		regexAndType = (
			(self.hdaudioDeviceRegex, "HDAUDIO"),
			(self.pciDeviceRegex, "PCI"),
			(self.usbDeviceRegex, "USB"),
			(self.acpiDeviceRegex, "ACPI"),
		)
		found = set()
		section = ""
		sectionsParsed = []
		for line in lines:
			try:
				match = re.search(self.sectionRegex, line)
				if match:
					if section and isDeviceSection(section):
						sectionsParsed.append(section)
					section = match.group(1)
					if isDeviceSection(section):
						logger.trace("   - Parsing device section: %s", section)
				else:
					if isDeviceSection(section) and section not in sectionsParsed:
						try:
							if "=" not in line or "," not in line:
								continue

							devString = line.split("=")[1].split(",")[1].strip()
							logger.trace(
								"      - Processing device string: %s", devString
							)

							for regex, deviceType in regexAndType:
								match = regex.search(devString)
								if match:
									break
							else:  # No match found
								deviceType = ""  # reset the device type

							if match:
								logger.trace("         - Device type is %s", deviceType)
								if deviceType == "ACPI":
									vendor = match.group(1)
									device = match.group(2)
								else:
									vendor = forceHardwareVendorId(match.group(1))
									device = forceHardwareDeviceId(match.group(2))

								if f"{vendor}:{device}" not in found:
									logger.trace(
										"         - Found %s device: %s:%s",
										deviceType,
										vendor,
										device,
									)
									found.add(f"{deviceType}:{vendor}:{device}")
									self._devices.append(
										{
											"path": path,
											"class": deviceClass,
											"vendor": vendor,
											"device": device,
											"type": deviceType,
										}
									)
						except IndexError:
							logger.warning(
								"Skipping bad line '%s' in file %s",
								line,
								self._filename,
							)
			except Exception as err:
				logger.error(
					"Parse error in inf file '%s' line '%s': %s",
					self._filename,
					line,
					err,
				)
		self._parsed = True


class PciidsFile(ConfigFile):
	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(
			self, filename, lockFailTimeout, commentChars=[";", "#"], lstrip=False
		)
		self._devices = {}
		self._vendors = {}
		self._subDevices = {}

	@requiresParsing
	def getVendor(self, vendorId):
		vendorId = forceHardwareVendorId(vendorId)
		return self._vendors.get(vendorId, None)

	@requiresParsing
	def getDevice(self, vendorId, deviceId):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		return self._devices.get(vendorId, {}).get(deviceId, None)

	@requiresParsing
	def getSubDevice(self, vendorId, deviceId, subVendorId, subDeviceId):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		subVendorId = forceHardwareVendorId(subVendorId)
		subDeviceId = forceHardwareDeviceId(subDeviceId)
		return (
			self._subDevices.get(vendorId, {})
			.get(deviceId, {})
			.get(subVendorId + ":" + subDeviceId, None)
		)

	def parse(self, lines=None):
		logger.debug("Parsing ids file %s", self._filename)

		lines = ConfigFile.parse(self, lines)
		self._parsed = False

		self._devices = {}
		self._vendors = {}
		self._subDevices = {}

		currentVendorId = None
		currentDeviceId = None
		for line in lines:
			try:
				if line.startswith("C "):
					# Start of list of known device classes, subclasses and programming interfaces
					break

				if line.startswith("\t"):
					if not currentVendorId or currentVendorId not in self._devices:
						raise ValueError(
							f"Parse error in file '{self._filename}': {line}"
						)

					if line.startswith("\t\t"):
						if (
							not currentDeviceId
							or currentVendorId not in self._subDevices
							or currentDeviceId not in self._subDevices[currentVendorId]
						):
							raise ValueError(
								f"Parse error in file '{self._filename}': {line}"
							)
						(subVendorId, subDeviceId, subName) = line.lstrip().split(
							None, 2
						)
						subVendorId = forceHardwareVendorId(subVendorId)
						subDeviceId = forceHardwareDeviceId(subDeviceId)
						self._subDevices[currentVendorId][currentDeviceId][
							subVendorId + ":" + subDeviceId
						] = subName.strip()
					else:
						(deviceId, deviceName) = line.lstrip().split(None, 1)
						currentDeviceId = deviceId = forceHardwareDeviceId(deviceId)
						if deviceId not in self._subDevices[currentVendorId]:
							self._subDevices[currentVendorId][deviceId] = {}
						self._devices[currentVendorId][deviceId] = deviceName.strip()
				else:
					(vendorId, vendorName) = line.split(None, 1)
					currentVendorId = vendorId = forceHardwareVendorId(vendorId)
					try:
						self._devices[vendorId]
					except KeyError:
						self._devices[vendorId] = {}

					try:
						self._subDevices[vendorId]
					except KeyError:
						self._subDevices[vendorId] = {}

					self._vendors[vendorId] = vendorName.strip()
			except Exception as err:
				logger.error(err)
		self._parsed = True


UsbidsFile = PciidsFile


class TxtSetupOemFile(ConfigFile):
	sectionRegex = re.compile(r"\[\s*([^\]]+)\s*\]")
	pciDeviceRegex = re.compile(r"VEN_([\da-fA-F]+)(&DEV_([\da-fA-F]+))?(\S*)\s*$")
	usbDeviceRegex = re.compile(
		r"USB.*VID_([\da-fA-F]+)(&PID_([\da-fA-F]+))?(\S*)\s*$", re.IGNORECASE
	)
	filesRegex = re.compile(
		r"^files\.(computer|display|keyboard|mouse|scsi)\.(.+)$", re.IGNORECASE
	)
	configsRegex = re.compile(r"^config\.(.+)$", re.IGNORECASE)
	hardwareIdsRegex = re.compile(
		r"^hardwareids\.(computer|display|keyboard|mouse|scsi)\.(.+)$", re.IGNORECASE
	)
	dllEntryRegex = re.compile(r"^(dll\s*\=\s*)(\S+.*)$", re.IGNORECASE)

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[";", "#"])
		self._devices = []
		self._files = []
		self._componentNames = []
		self._componentOptions = []
		self._defaultComponentIds = []
		self._serviceNames = []
		self._driverDisks = []
		self._configs = []

	@requiresParsing
	def getDevices(self):
		return self._devices

	@requiresParsing
	def isDeviceKnown(self, vendorId, deviceId, deviceType=None):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		for dev in self._devices:
			if (
				(not deviceType or (dev.get("type") == deviceType))
				and (dev.get("vendor") == vendorId)
				and (not dev.get("device") or (dev["device"] == deviceId))
			):
				return True
		return False

	@requiresParsing
	def getDevice(self, vendorId, deviceId, deviceType=None, architecture="x86"):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		architecture = forceArchitecture(architecture)

		device = None
		for dev in self._devices:
			if (
				(not deviceType or (dev.get("type") == deviceType))
				and (dev.get("vendor") == vendorId)
				and (not dev.get("device") or dev["device"] == deviceId)
			):
				if architecture == "x86":
					if (
						"amd64" in dev["componentId"].lower()
						or "x64" in dev["componentId"].lower()
					):
						logger.debug(
							"Skipping device with component id '%s' which does not seem to match architecture '%s'",
							dev["componentId"],
							architecture,
						)
						continue
				elif architecture == "x64":
					if (
						"i386" in dev["componentId"].lower()
						or "x86" in dev["componentId"].lower()
					):
						logger.debug(
							"Skipping device with component id '%s' which does not seem to match architecture '%s'",
							dev["componentId"],
							architecture,
						)
						continue
				device = dev
				break
		if not device:
			raise ValueError(
				f"Device '{vendorId}:{deviceId}' not found in txtsetup.oem file '{self._filename}'"
			)
		return device

	def getFilesForDevice(
		self, vendorId, deviceId, deviceType=None, fileTypes=[], architecture="x86"
	):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		fileTypes = forceUnicodeLowerList(fileTypes)
		architecture = forceArchitecture(architecture)

		device = self.getDevice(
			vendorId=vendorId,
			deviceId=deviceId,
			deviceType=deviceType,
			architecture=architecture,
		)

		files = []
		diskDriverDirs = {}
		for dev in self._driverDisks:
			diskDriverDirs[dev["diskName"]] = dev["driverDir"]

		for file in self._files:
			if (
				file["componentName"] != device["componentName"]
				or file["componentId"] != device["componentId"]
			):
				continue
			if fileTypes and file["fileType"] not in fileTypes:
				continue
			if file["diskName"] not in diskDriverDirs:
				raise ValueError(
					f"Driver disk for file {file} not found in txtsetup.oem file '{self._filename}'"
				)
			files.append(
				os.path.join(diskDriverDirs[file["diskName"]], file["filename"])
			)
		return files

	def getComponentOptionsForDevice(
		self, vendorId, deviceId, deviceType=None, architecture="x86"
	):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)

		device = self.getDevice(
			vendorId=vendorId,
			deviceId=deviceId,
			deviceType=deviceType,
			architecture=architecture,
		)

		for componentOptions in self._componentOptions:
			if (
				componentOptions["componentName"] == device["componentName"]
				and componentOptions["componentId"] == device["componentId"]
			):
				return componentOptions
		for componentOptions in self._componentOptions:
			if (
				componentOptions["componentName"].lower()
				== device["componentName"].lower()
				and componentOptions["componentId"].lower()
				== device["componentId"].lower()
			):
				return componentOptions
		raise ValueError(
			f"Component options for device {device} not found in txtsetup.oem file '{self._filename}'"
		)

	@requiresParsing
	def applyWorkarounds(self):
		if not self._defaultComponentIds:
			# Missing default component will cause problems in windows textmode setup
			logger.info(
				"No default component ids found, using '%s' as default component id",
				self._componentOptions[0]["componentId"],
			)
			self._defaultComponentIds.append(
				{
					"componentName": self._componentOptions[0]["componentName"],
					"componentId": self._componentOptions[0]["componentId"],
				}
			)
		files = []
		for file in self._files:
			if file["fileType"] == "dll":
				# dll entries will cause problems in windows textmode setup
				continue
			files.append(file)
		self._files = files

	def parse(self, lines=None):
		logger.debug("Parsing txtsetup.oem file %s", self._filename)

		lines = ConfigFile.parse(self, lines)
		self._parsed = False

		self._devices = []
		self._files = []
		self._componentNames = []
		self._componentOptions = []
		self._defaultComponentIds = []
		self._serviceNames = []
		self._driverDisks = []
		self._configs = []

		sections = {}
		section = None
		for line in lines:
			logger.trace("txtsetup.oem: %s", line)
			match = re.search(self.sectionRegex, line)
			if match:
				section = match.group(1)
				sections[section] = []
			elif section:
				sections[section].append(line)

		# Search for component options
		logger.info("Searching for component names and options")
		for section, sec_lines in sections.items():
			if section.lower() not in (
				"computer",
				"display",
				"keyboard",
				"mouse",
				"scsi",
			):
				continue
			componentName = section
			for line in sec_lines:
				if "=" not in line:
					continue
				optionName = None
				(componentId, value) = line.split("=", 1)
				componentId = componentId.strip()
				try:
					(description, optionName) = value.split(",", 1)
					optionName = optionName.strip()
				except ValueError:
					description = value
				description = description.strip()
				if description.startswith('"') and description.endswith('"'):
					description = description[1:-1]
				if componentName not in self._componentNames:
					self._componentNames.append(componentName)
				self._componentOptions.append(
					{
						"componentName": componentName,
						"description": description,
						"componentId": componentId,
						"optionName": optionName,
					}
				)

		logger.info("Component names found: %s", self._componentNames)
		logger.info("Component options found: %s", self._componentOptions)

		# Search for default component ids
		logger.info("Searching for default component ids")
		for section, sec_lines in sections.items():
			if section.lower() != "defaults":
				continue

			for line in sec_lines:
				(componentName, componentId) = line.split("=", 1)
				self._defaultComponentIds.append(
					{
						"componentName": componentName.strip(),
						"componentId": componentId.strip(),
					}
				)

		if self._defaultComponentIds:
			logger.info("Found default component ids: %s", self._defaultComponentIds)

		# Search for hardware ids
		logger.info("Searching for devices")
		for section, sec_lines in sections.items():
			match = re.search(self.hardwareIdsRegex, section)
			if not match:
				continue
			componentName = match.group(1)
			componentId = match.group(2)
			logger.info(
				"Found hardwareIds section '%s', component name '%s', component id '%s'",
				section,
				componentName,
				componentId,
			)
			for line in sec_lines:
				if not re.search(r"[iI][dD]\s*=", line):
					continue
				(device, serviceName) = line.split("=", 1)[1].strip().split(",", 1)
				device = device.strip()
				if device.startswith('"') and device.endswith('"'):
					device = device[1:-1]
				serviceName = serviceName.strip()
				if serviceName.startswith('"') and serviceName.endswith('"'):
					serviceName = serviceName[1:-1]
				match = re.search(self.pciDeviceRegex, device)
				if not match:
					continue
				vendor = forceHardwareVendorId(match.group(1))
				device = None
				if match.group(3):
					device = forceHardwareDeviceId(match.group(3))
				extra = None
				if match.group(4):
					extra = forceUnicode(match.group(4))
				logger.debug(
					"   Found %s device: %s:%s, service name: %s",
					"PCI",
					vendor,
					device,
					serviceName,
				)
				self._devices.append(
					{
						"vendor": vendor,
						"device": device,
						"extra": extra,
						"type": "PCI",
						"serviceName": serviceName,
						"componentName": componentName,
						"componentId": componentId,
					}
				)
				if serviceName not in self._serviceNames:
					self._serviceNames.append(serviceName)

		if not self._devices:
			raise ValueError(f"No devices found in txtsetup file '{self._filename}'")

		logger.info("Found services: %s", self._serviceNames)
		logger.debug("Found devices: %s", self._devices)

		# Search for disks
		logger.info("Searching for disks")
		for section, sec_lines in sections.items():
			if section.lower() != "disks":
				continue

			for line in sec_lines:
				if "=" not in line:
					continue

				(diskName, value) = line.split("=", 1)
				diskName = diskName.strip()
				(desc, tf, dd) = value.split(",", 2)
				desc = desc.strip()
				if desc.startswith('"') and desc.endswith('"'):
					desc = desc[1:-1]
				tf = tf.strip()
				if tf.startswith("\\"):
					tf = tf[1:]
				dd = dd.strip()
				if dd.startswith("\\"):
					dd = dd[1:]

				self._driverDisks.append(
					{
						"diskName": diskName,
						"description": desc,
						"tagfile": tf,
						"driverDir": dd,
					}
				)
		if not self._driverDisks:
			raise ValueError(
				f"No driver disks found in txtsetup file '{self._filename}'"
			)
		logger.info("Found driver disks: %s", self._driverDisks)

		# Search for files
		logger.info("Searching for files")
		for section, sec_lines in sections.items():
			match = re.search(self.filesRegex, section)
			if not match:
				continue
			componentName = match.group(1)
			componentId = match.group(2)
			logger.info(
				"Found files section '%s', component name '%s', component id '%s'",
				section,
				componentName,
				componentId,
			)
			for line in sec_lines:
				(fileType, value) = line.split("=", 1)
				fileType = fileType.strip()
				parts = value.split(",")
				diskName = parts[0].strip()
				filename = parts[1].strip()
				optionName = None
				if len(parts) > 2:
					optionName = parts[2].strip()

				self._files.append(
					{
						"fileType": fileType,
						"diskName": diskName,
						"filename": filename,
						"componentName": componentName,
						"componentId": componentId,
						"optionName": optionName,
					}
				)
		logger.debug("Found files: %s", self._files)

		# Search for configs
		logger.info("Searching for configs")
		for section, sec_lines in sections.items():
			match = re.search(self.configsRegex, section)
			if not match:
				continue
			componentId = match.group(1)
			logger.info(
				"Found configs section '%s', component id '%s'", section, componentId
			)
			for line in sec_lines:
				value = line.split("=", 1)[1]
				(keyName, valueName, valueType, value) = value.split(",", 3)
				keyName = keyName.strip()
				valueName = valueName.strip()
				valueType = valueType.strip()
				value = value.strip()
				self._configs.append(
					{
						"keyName": keyName.strip(),
						"valueName": valueName.strip(),
						"valueType": valueType.strip(),
						"value": value.strip(),
						"componentId": componentId,
					}
				)
		logger.debug("Found configs: %s", self._configs)
		self._parsed = True

	def generate(self):
		lines = []
		lines.append("[Disks]\r\n")
		for disk in self._driverDisks:
			lines.append(
				f'{disk["diskName"]} = "{disk["description"]}", \\{disk["tagfile"]}, \\{disk["driverDir"]}\r\n'
			)
		lines.append("\r\n")
		lines.append("[Defaults]\r\n")
		for default in self._defaultComponentIds:
			lines.append(f'{default["componentName"]} = {default["componentId"]}\r\n')

		for name in self._componentNames:
			lines.append("\r\n")
			lines.append(f"[{name}]\r\n")
			for options in self._componentOptions:
				if options["componentName"] != name:
					continue
				line = f'{options["componentId"]} = "{options["description"]}"'
				if options["optionName"]:
					line = f'{line}, {options["optionName"]}'
				lines.append(line + "\r\n")

		for name in self._componentNames:
			for options in self._componentOptions:
				if options["componentName"] != name:
					continue
				lines.append("\r\n")
				lines.append(f'[Files.{name}.{options["componentId"]}]\r\n')
				for file in self._files:
					if (
						file["componentName"] != name
						or file["componentId"] != options["componentId"]
					):
						continue
					line = (
						f'{file["fileType"]} = {file["diskName"]}, {file["filename"]}'
					)
					if file["optionName"]:
						line = f'{line}, {file["optionName"]}'
					lines.append(line + "\r\n")

		for name in self._componentNames:
			for options in self._componentOptions:
				if options["componentName"] != name:
					continue
				lines.append("\r\n")
				lines.append(f'[HardwareIds.{name}.{options["componentId"]}]\r\n')
				for dev in self._devices:
					if (
						dev["componentName"] != name
						or dev["componentId"] != options["componentId"]
					):
						continue

					line = f'id = "{dev["type"]}\\VEN_{dev["vendor"]}'
					if dev["device"]:
						line += f'&DEV_{dev["device"]}'
					if dev["extra"]:
						line += dev["extra"]
					if dev["type"] == "USB":
						line = line.replace("VEN_", "VID_").replace("DEV_", "PID_")
					line += f'", "{dev["serviceName"]}"'
					lines.append(line + "\r\n")

		configComponents = {}
		for config in self._configs:
			if config["componentId"] not in configComponents:
				configComponents[config["componentId"]] = []
			configComponents[config["componentId"]].append(config)

		for componentId, configs in configComponents.items():
			lines.append("\r\n")
			lines.append(f"[Config.{componentId}]\r\n")
			for conf in configs:
				lines.append(
					f"value = {conf['keyName']}, {conf['valueName']}, {conf['valueType']}, {conf['value']}\r\n"
				)

		self._lines = lines
		self._fileHandle = codecs.open(self._filename, "w", "cp1250")
		self.writelines()
		self.close()


class ZsyncFile(LockableFile):
	def __init__(self, filename, lockFailTimeout=2000):
		LockableFile.__init__(self, filename, lockFailTimeout)
		self._header = {}
		self._data = ""
		self._parsed = False

	def parse(self, lines=None):
		logger.debug("Parsing zsync file %s", self._filename)

		self._parsed = False

		with open(self._filename, "rb") as file:
			for line in iter(lambda: file.readline().strip(), b""):
				strLine = line.decode()
				key, value = strLine.split(":", 1)
				self._header[key.strip()] = value.strip()

			# Header and data are divided by an empty line
			self._data = file.read()

		self._parsed = True

	def generate(self, dataFile=None):
		if dataFile:
			create_zsync_file(Path(dataFile), Path(self._filename))
			self.parse()

		with open(self._filename, "wb") as file:
			for key, value in self._header.items():
				if key.lower() == "mtime":
					continue
				headerData = f"{key}: {value}\n"
				file.write(headerData.encode())
			file.write("\n".encode())
			file.write(self._data)


class DHCPDConf_Component:
	def __init__(self, startLine, parentBlock):
		self.startLine = startLine
		self.endLine = startLine
		self.parentBlock = parentBlock

	def getShifting(self):
		shifting = ""
		if not self.parentBlock:
			return shifting
		parentBlock = self.parentBlock.parentBlock
		while parentBlock:
			shifting += "\t"
			parentBlock = parentBlock.parentBlock
		return shifting

	def asText(self):
		return self.getShifting()

	def __str__(self):
		return f"<{self.__class__.__name__}({self.startLine}, {self.endLine})>"

	def __repr__(self):
		return self.__str__()


class DHCPDConf_Parameter(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, key, value):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.key = key
		self.value = value
		if isinstance(self.value, str):
			if self.value.lower() in ("yes", "true", "on"):
				self.value = True
			elif self.value.lower() in ("no", "false", "off"):
				self.value = False

	def asText(self):
		value = self.value
		if isinstance(value, bool):
			if value:
				value = "on"
			else:
				value = "off"
		elif (
			self.key in ("filename", "ddns-domainname")
			or re.match(r".*['/\\].*", value)
			or re.match(r"^\w+\.\w+$", value)
			or self.key.endswith("-name")
		):
			value = f'"{value}"'
		return f"{self.getShifting()}{self.key} {value};"

	def asHash(self):
		return {self.key: self.value}


class DHCPDConf_Option(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, key, value):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.key = key
		self.value = value
		if not isinstance(self.value, list):
			self.value = [self.value]

	def asText(self):
		quotedOptions = (
			"-name",
			"-domain",
			"-identifier",
			"-search",
			"merit-dump",
			"nds-context",
			"netbios-scope",
			"nwip-domain",
			"nwip-suboptions",
			"nis-domain",
			"nisplus-domain",
			"root-path",
			"uap-servers",
			"user-class",
			"vendor-encapsulated-options",
			"circuit-id",
			"remote-id",
			"fqdn.fqdn",
			"ddns-rev-domainname",
		)

		text = []
		for value in self.value:
			if (
				re.match(r".*['/\\].*", value)
				or re.match(r"^\w+\.\w+$", value)
				or self.key.endswith(quotedOptions)
			):
				text.append(f'"{value}"')
			else:
				text.append(value)

		return f"{self.getShifting()}option {self.key} {', '.join(text)};"

	def asHash(self):
		return {self.key: self.value}


class DHCPDConf_Comment(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, data):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self._data = data

	def asText(self):
		return f"{self.getShifting()}#{self._data}"


class DHCPDConf_EmptyLine(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)


class DHCPDConf_Block(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, type, settings=[]):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.type = type
		self.settings = settings
		self.lineRefs = {}
		self.components = []

	def getComponents(self):
		return self.components

	def removeComponents(self):
		logger.debug("Removing components: %s", self.components)
		for comp in forceList(self.components):
			self.removeComponent(comp)

	def addComponent(self, component):
		self.components.append(component)
		if component.startLine not in self.lineRefs:
			self.lineRefs[component.startLine] = []
		self.lineRefs[component.startLine].append(component)

	def removeComponent(self, component):
		index = -1
		for i, currentComponent in enumerate(self.components):
			if currentComponent == component:
				index = i
				break

		if index < 0:
			raise BackendMissingDataError(f"Component '{component}' not found")

		del self.components[index]

		index = -1
		if component.startLine in self.lineRefs:
			for i, currentComponent in enumerate(self.lineRefs[component.startLine]):
				if currentComponent == component:
					index = i
					break
		if index >= 0:
			del self.lineRefs[component.startLine][index]

	def getOptions_hash(self, inherit=None):
		options = {}
		for component in self.components:
			if not isinstance(component, DHCPDConf_Option):
				continue
			options[component.key] = component.value

		if inherit and (self.type != inherit) and self.parentBlock:
			for key, value in self.parentBlock.getOptions_hash(inherit).items():
				if key not in options:
					options[key] = value

		return options

	def getOptions(self, inherit=None):
		options = []
		for component in self.components:
			if not isinstance(component, DHCPDConf_Option):
				continue
			options.append(component)

		if inherit and self.type != inherit and self.parentBlock:
			options.extend(self.parentBlock.getOptions(inherit))

		return options

	def getParameters_hash(self, inherit=None):
		parameters = {}
		for component in self.components:
			if not isinstance(component, DHCPDConf_Parameter):
				continue
			parameters[component.key] = component.value

		if inherit and self.type != inherit and self.parentBlock:
			for key, value in self.parentBlock.getParameters_hash(inherit).items():
				if key not in parameters:
					parameters[key] = value
		return parameters

	def getParameters(self, inherit=None):
		parameters = []

		if inherit and self.type != inherit and self.parentBlock:
			parameters.extend(self.parentBlock.getParameters(inherit))

		return parameters

	def getBlocks(self, type, recursive=False):
		blocks = []
		for component in self.components:
			if not isinstance(component, DHCPDConf_Block):
				continue
			if component.type == type:
				blocks.append(component)
			if recursive:
				blocks.extend(component.getBlocks(type, recursive))
		return blocks

	def asText(self):
		text = ""
		shifting = self.getShifting()
		if not isinstance(self, DHCPDConf_GlobalBlock):
			text += shifting + " ".join(self.settings) + " {\n"

		notWritten = self.components
		lineNumber = max(self.startLine, 1)

		while lineNumber <= self.endLine:
			if lineNumber not in self.lineRefs or not self.lineRefs[lineNumber]:
				lineNumber += 1
				continue

			for i, lineRef in enumerate(self.lineRefs[lineNumber]):
				compText = lineRef.asText()
				if i > 0 and isinstance(lineRef, DHCPDConf_Comment):
					compText = " " + compText.lstrip()
				text += compText
				# Mark component as written
				if lineRef in notWritten:
					notWritten.remove(lineRef)
			text += "\n"
			lineNumber += 1

		for component in notWritten:
			text += component.asText() + "\n"

		if not isinstance(self, DHCPDConf_GlobalBlock):
			# Write '}' to close block
			text += shifting + "}"

		return text


class DHCPDConf_GlobalBlock(DHCPDConf_Block):
	def __init__(self):
		DHCPDConf_Block.__init__(self, 1, None, "global")


class DHCPDConfFile(TextFile):
	def __init__(self, filename, lockFailTimeout=2000):
		TextFile.__init__(self, filename, lockFailTimeout)

		self._currentLine = 0
		self._currentToken = None
		self._currentIndex = -1
		self._data = ""
		self._currentBlock = None
		self._globalBlock = None
		self._parsed = False

		logger.debug("Parsing dhcpd conf file '%s'", self._filename)

	def getGlobalBlock(self):
		return self._globalBlock

	def parse(self, lines=None):
		self._currentLine = 0
		self._currentToken = None
		self._currentIndex = -1
		self._data = ""
		self._parsed = False

		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		self._currentBlock = self._globalBlock = DHCPDConf_GlobalBlock()
		self._globalBlock.endLine = len(self._lines)

		minIndex = 0
		while True:
			self._currentToken = None
			self._currentIndex = -1
			if not self._data.strip():
				if not self._getNewData():
					break
				if not self._data.strip():
					self._parse_emptyline()
				continue

			for token in ("#", ";", "}", "{"):
				index = self._data.find(token)
				if (
					(index != -1)
					and (index >= minIndex)
					and ((self._currentIndex == -1) or (index < self._currentIndex))
				):
					if (self._data[:index].count('"') % 2 == 1) or (
						self._data[:index].count("'") % 2 == 1
					):
						continue
					self._currentToken = token
					self._currentIndex = index
					break

			if not self._currentToken:
				minIndex = len(self._data)
				if not self._getNewData():
					break
				continue

			minIndex = 0
			if self._currentToken == "#":
				self._parse_comment()
			elif self._currentToken == ";":
				self._parse_semicolon()
			elif self._currentToken == "}":
				self._parse_rbracket()
			elif self._currentToken == "{":
				self._parse_lbracket()

		self._parsed = True

	def generate(self):
		if not self._globalBlock:
			raise ValueError("Got no data to write")

		self.open("w")
		self.write(self._globalBlock.asText())
		self.close()

	@requiresParsing
	def addHost(
		self, hostname, hardwareAddress, ipAddress, fixedAddress, parameters=None
	):
		if not parameters:
			parameters = {}

		hostname = forceHostname(hostname)
		hardwareAddress = forceHardwareAddress(hardwareAddress)
		ipAddress = forceIPAddress(ipAddress)
		fixedAddress = forceUnicodeLower(fixedAddress)
		parameters = forceDict(parameters)

		existingHost = None
		for block in self._globalBlock.getBlocks("host", recursive=True):
			if block.settings[1].lower() == hostname:
				existingHost = block
			else:
				for key, value in block.getParameters_hash().items():
					if key == "fixed-address" and value.lower() == fixedAddress:
						raise BackendBadValueError(
							f"Host '{block.settings[1]}' uses the same fixed address"
						)
					if (
						key == "hardware"
						and value.lower() == f"ethernet {hardwareAddress}"
					):
						raise BackendBadValueError(
							f"Host '{block.settings[1]}' uses the same hardware ethernet address"
						)

		if existingHost:
			logger.info(
				"Host '%s' already exists in config file '%s', deleting first",
				hostname,
				self._filename,
			)
			self.deleteHost(hostname)

		logger.notice(
			"Creating host '%s', hardwareAddress '%s', ipAddress '%s', fixedAddress '%s', parameters '%s' in dhcpd config file '%s'",
			hostname,
			hardwareAddress,
			ipAddress,
			fixedAddress,
			parameters,
			self._filename,
		)

		for key, value in parameters.items():
			parameters[key] = DHCPDConf_Parameter(-1, None, key, value).asHash()[key]

		# Default parent block is global
		parentBlock = self._globalBlock

		# Search the right subnet block
		for block in self._globalBlock.getBlocks("subnet", recursive=True):
			if ipAddressInNetwork(
				ipAddress, f"{block.settings[1]}/{block.settings[3]}"
			):
				logger.debug(
					"Choosing subnet %s/%s for host %s",
					block.settings[1],
					block.settings[3],
					hostname,
				)
				parentBlock = block

		# Search the right group for the host
		bestGroup = None
		bestMatchCount = 0
		for block in parentBlock.getBlocks("group"):
			matchCount = 0
			blockParameters = block.getParameters_hash(inherit="global")
			if blockParameters:
				# Block has parameters set, check if they match the hosts parameters
				for key, value in blockParameters.items():
					if key not in parameters:
						continue

					if parameters[key] == value:
						matchCount += 1
					else:
						matchCount -= 1

			if matchCount > bestMatchCount or matchCount >= 0 and not bestGroup:
				matchCount = bestMatchCount
				bestGroup = block

		if bestGroup:
			parentBlock = bestGroup

		# Remove parameters which are already defined in parents
		blockParameters = parentBlock.getParameters_hash(inherit="global")
		if blockParameters:
			for key, value in blockParameters.items():
				if key in parameters and parameters[key] == value:
					del parameters[key]

		hostBlock = DHCPDConf_Block(
			startLine=-1,
			parentBlock=parentBlock,
			type="host",
			settings=["host", hostname],
		)
		hostBlock.addComponent(
			DHCPDConf_Parameter(
				startLine=-1,
				parentBlock=hostBlock,
				key="fixed-address",
				value=fixedAddress,
			)
		)
		hostBlock.addComponent(
			DHCPDConf_Parameter(
				startLine=-1,
				parentBlock=hostBlock,
				key="hardware",
				value=f"ethernet {hardwareAddress}",
			)
		)
		for key, value in parameters.items():
			hostBlock.addComponent(
				DHCPDConf_Parameter(
					startLine=-1, parentBlock=hostBlock, key=key, value=value
				)
			)

		parentBlock.addComponent(hostBlock)

	@requiresParsing
	def getHost(self, hostname):
		hostname = forceHostname(hostname)

		for block in self._globalBlock.getBlocks("host", recursive=True):
			if block.settings[1] == hostname:
				return block.getParameters_hash()
		return None

	@requiresParsing
	def deleteHost(self, hostname):
		hostname = forceHostname(hostname)

		logger.notice(
			"Deleting host '%s' from dhcpd config file '%s'", hostname, self._filename
		)
		hostBlocks = []
		for block in self._globalBlock.getBlocks("host", recursive=True):
			if block.settings[1] == hostname:
				hostBlocks.append(block)
			else:
				for key, value in block.getParameters_hash().items():
					if key == "fixed-address" and value == hostname:
						hostBlocks.append(block)

		if not hostBlocks:
			logger.warning("Failed to remove host '%s': not found", hostname)
			return

		for block in hostBlocks:
			block.parentBlock.removeComponent(block)

	@requiresParsing
	def modifyHost(self, hostname, parameters):
		hostname = forceHostname(hostname)
		parameters = forceDict(parameters)

		logger.notice(
			"Modifying host '%s' in dhcpd config file '%s'", hostname, self.filename
		)

		hostBlocks = []
		for block in self._globalBlock.getBlocks("host", recursive=True):
			if block.settings[1] == hostname:
				hostBlocks.append(block)
			else:
				for key, value in block.getParameters_hash().items():
					if key == "fixed-address" and value == hostname:
						hostBlocks.append(block)
					elif key == "hardware" and value.lower() == parameters.get(
						"hardware"
					):
						raise BackendBadValueError(
							f"Host '{block.settings[1]}' uses the same hardware ethernet address"
						)

		if len(hostBlocks) != 1:
			raise BackendBadValueError(
				f"Host '{hostname}' found {len(hostBlocks)} times"
			)

		hostBlock = hostBlocks[0]
		hostBlock.removeComponents()

		for key, value in parameters.items():
			parameters[key] = DHCPDConf_Parameter(-1, None, key, value).asHash()[key]

		for key, value in hostBlock.parentBlock.getParameters_hash(
			inherit="global"
		).items():
			if key not in parameters:
				continue

			if parameters[key] == value:
				del parameters[key]

		for key, value in parameters.items():
			hostBlock.addComponent(
				DHCPDConf_Parameter(
					startLine=-1, parentBlock=hostBlock, key=key, value=value
				)
			)

	def _getNewData(self):
		if self._currentLine >= len(self._lines):
			return False
		self._data += self._lines[self._currentLine]
		self._currentLine += 1
		return True

	def _parse_emptyline(self):
		logger.trace("_parse_emptyline")
		self._currentBlock.addComponent(
			DHCPDConf_EmptyLine(
				startLine=self._currentLine, parentBlock=self._currentBlock
			)
		)
		self._data = self._data[: self._currentIndex]

	def _parse_comment(self):
		logger.trace("_parse_comment")
		self._currentBlock.addComponent(
			DHCPDConf_Comment(
				startLine=self._currentLine,
				parentBlock=self._currentBlock,
				data=self._data.strip()[1:],
			)
		)
		self._data = self._data[: self._currentIndex]

	def _parse_semicolon(self):
		logger.trace("_parse_semicolon")
		data = self._data[: self._currentIndex]
		self._data = self._data[self._currentIndex + 1 :]

		splittedData = data.split()
		key = splittedData[0]
		if key != "option":
			# Parameter
			value = " ".join(data.split()[1:]).strip()
			if len(value) > 1 and value.startswith('"') and value.endswith('"'):
				value = value[1:-1]

			self._currentBlock.addComponent(
				DHCPDConf_Parameter(
					startLine=self._currentLine,
					parentBlock=self._currentBlock,
					key=key,
					value=value,
				)
			)
			return

		# Option
		key = splittedData[1]
		value = " ".join(splittedData[2:]).strip()
		values = []
		quote = ""
		current = []
		for val in value:
			if val == '"':
				if quote == '"':
					quote = ""
				elif quote == "'":
					current.append(val)
				else:
					quote = '"'
			elif val == "'":
				if quote == "'":
					quote = ""
				elif quote == '"':
					current.append(val)
				else:
					quote = "'"
			elif re.search(r"\s", val):
				current.append(val)
			elif val == ",":
				if quote:
					current.append(val)
				else:
					values.append("".join(current).strip())
					current = []
			else:
				current.append(val)

		if current:
			values.append("".join(current).strip())

		self._currentBlock.addComponent(
			DHCPDConf_Option(
				startLine=self._currentLine,
				parentBlock=self._currentBlock,
				key=key,
				value=values,
			)
		)

	def _parse_lbracket(self):
		logger.trace("_parse_lbracket")
		# Start of a block
		data = self._data[: self._currentIndex]
		self._data = self._data[self._currentIndex + 1 :]
		# Split the block definition at whitespace
		# The first value is the block type
		# Example: subnet 194.31.185.0 netmask 255.255.255.0 => type is subnet
		splittedData = data.split()
		block = DHCPDConf_Block(
			startLine=self._currentLine,
			parentBlock=self._currentBlock,
			type=splittedData[0].strip(),
			settings=splittedData,
		)
		self._currentBlock.addComponent(block)
		self._currentBlock = block

	def _parse_rbracket(self):
		logger.trace("_parse_rbracket")
		# End of a block
		self._data = self._data[self._currentIndex + 1 :]

		self._currentBlock.endLine = self._currentLine
		self._currentBlock = self._currentBlock.parentBlock
