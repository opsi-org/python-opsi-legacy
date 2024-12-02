# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Darwin

Functions and classes for the use with a DARWIN operating system.
"""

import os
import re
import subprocess
import time
from typing import Any, Dict, List

import pexpect
from opsicommon.logging import get_logger

from OPSI.System import Posix
from OPSI.System.Posix import (
	CommandNotFoundException,
	Distribution,
	Harddisk,
	NetworkPerformanceCounter,
	SysInfo,
	SystemSpecificHook,
	addSystemHook,
	auditHardware,
	configureInterface,
	daemonize,
	execute,
	get_subprocess_environment,
	getActiveConsoleSessionId,
	getActiveSessionId,
	getActiveSessionInformation,
	getBlockDeviceBusType,
	getBlockDeviceContollerInfo,
	getDefaultNetworkInterfaceName,
	getDHCPDRestartCommand,
	getDHCPResult,
	getDHCPServiceName,
	getDiskSpaceUsage,
	getEthernetDevices,
	getFQDN,
	getHarddisks,
	getHostname,
	getKernelParams,
	getNetworkDeviceConfig,
	getNetworkInterfaces,
	getSambaServiceName,
	getServiceNames,
	getSessionInformation,
	getSystemProxySetting,
	halt,
	hardwareExtendedInventory,
	hooks,
	ifconfig,
	isCentOS,
	isDebian,
	isOpenSUSE,
	isRHEL,
	isSLES,
	isUbuntu,
	isUCS,
	locateDHCPDConfig,
	locateDHCPDInit,
	reboot,
	removeSystemHook,
	runCommandInSession,
	setLocalSystemTime,
	shutdown,
	terminateProcess,
	umount,
	which,
)
from OPSI.Types import forceFilename, forceUnicode
from OPSI.Util import objectToBeautifiedText, removeUnit

HIERARCHY_SEPARATOR = "//"

__all__ = (
	"CommandNotFoundException",
	"Distribution",
	"Harddisk",
	"NetworkPerformanceCounter",
	"SysInfo",
	"SystemSpecificHook",
	"addSystemHook",
	"auditHardware",
	"configureInterface",
	"daemonize",
	"execute",
	"get_subprocess_environment",
	"getActiveConsoleSessionId",
	"getActiveSessionId",
	"getActiveSessionIds",
	"getActiveSessionInformation",
	"getSessionInformation",
	"getBlockDeviceBusType",
	"getBlockDeviceContollerInfo",
	"getDHCPDRestartCommand",
	"getDHCPResult",
	"getDHCPServiceName",
	"getDefaultNetworkInterfaceName",
	"getDiskSpaceUsage",
	"getEthernetDevices",
	"getFQDN",
	"getHarddisks",
	"getHostname",
	"getKernelParams",
	"getNetworkDeviceConfig",
	"getNetworkInterfaces",
	"getSambaServiceName",
	"getServiceNames",
	"getSystemProxySetting",
	"halt",
	"hardwareExtendedInventory",
	"hardwareInventory",
	"hooks",
	"ifconfig",
	"isCentOS",
	"isDebian",
	"isOpenSUSE",
	"isRHEL",
	"isSLES",
	"isUCS",
	"isUbuntu",
	"locateDHCPDConfig",
	"locateDHCPDInit",
	"mount",
	"reboot",
	"removeSystemHook",
	"runCommandInSession",
	"setLocalSystemTime",
	"shutdown",
	"terminateProcess",
	"umount",
	"which",
)

logger = get_logger("opsi.general")


def set_tree_value(mydict: Dict, key_list: List, last_key: str, value: str) -> None:
	"""
	Assigns value to dict tree leaf.

	This method expects a dictionary and a series of keys.
	It traverses the series of keys downwards in the dictionary, creating
	subdicts if necessary. The given value is inserted as a new leaf under
	given key.

	:param mydict: Dictionary to insert into.
	:type mydict: Dict
	:param key_list: List of keys defining desired value location.
	:type key_list: List
	:param last_key: Key corresponding to the value to insert.
	:type last_key: str
	:param value: Value to insert into the dictionary.
	:type value: str
	"""
	subdict = mydict
	for key in key_list:
		sub = subdict.get(key)
		if sub is None:
			subdict[key] = {}
			subdict = subdict.get(key)
		else:
			subdict = sub
	subdict[last_key] = value


def get_tree_value(mydict: Dict, key_string: str) -> Any:
	"""
	Obtain certain dictionary value.

	This method obtains a value from a given dictionary by
	traversing it using a list of keys obtained from a string.

	:param mydict: Dictionary to search.
	:type mydict: Dict
	:param key_string: string representing a list of keys.
	:type key_strin: str

	:returns: Value corresponding to the list of keys.
	:rtype: Any
	"""
	key_list = key_string.split(HIERARCHY_SEPARATOR)
	subdict = mydict
	for key in key_list:
		sub = subdict.get(key)
		if sub is None:
			return None
		subdict = sub
	return subdict


def parse_profiler_output(lines: List) -> Dict:
	"""
	Parses the output of system_profiler.

	This method processes system_profiler output line
	by line and fills a dictionary with the derived
	information.

	:param lines: List of output lines.
	:type lines: List

	:returns: Dictionary containing the derived data.
	:rtype: Dict
	"""
	hwdata = {}
	key_list = []
	indent_list = [-1]
	for line in lines:
		indent = len(line) - len(line.lstrip())
		parts = [x.strip() for x in line.split(":", 1)]
		if len(parts) < 2:
			continue

		while indent <= indent_list[-1]:  # walk up tree
			indent_list.pop()
			key_list.pop()
		if parts[1] == "":  # branch new subtree ...
			indent_list.append(indent)
			key_list.append(parts[0])
		else:  # ... or fill in leaf
			value = parts[1].strip(",")
			value = removeUnit(value)
			set_tree_value(hwdata, key_list, parts[0], value)
	return hwdata


def parse_sysctl_output(lines: List) -> Dict:
	"""
	Parses the output of sysctl -a.

	This method processes sysctl -a output line
	by line and fills a dictionary with the derived
	information.

	:param lines: List of output lines.
	:type lines: List

	:returns: Dictionary containing the derived data.
	:rtype: Dict
	"""
	hwdata = {}
	for line in lines:
		key_string, value = line.split(":", 1)
		key_list = key_string.split(".")
		set_tree_value(hwdata, key_list[:-1], key_list[-1], value.strip())
	return hwdata


def parse_ioreg_output(lines: List) -> Dict:
	"""
	Parses the output of ioreg -l.

	This method processes ioreg -l output line
	by line and fills a dictionary with the derived
	information.

	:param lines: List of output lines.
	:type lines: List

	:returns: Dictionary containing the derived data.
	:rtype: Dict
	"""
	hwdata = {}
	key_list = []
	indent_list = [-1]
	for line in lines:
		line = line.strip()
		if line.endswith("{") or line.endswith("}"):
			continue
		indent = line.find("+-o ")
		parts = [x.strip() for x in line.split("=", 1)]

		if indent == -1:  # fill in leafs
			if len(parts) == 2:
				value = removeUnit(parts[1])
				set_tree_value(hwdata, key_list, parts[0], value)
			continue

		while indent <= indent_list[-1]:  # walk up tree
			indent_list.pop()
			key_list.pop()
		indent_list.append(indent)  # branch new subtree
		key = parts[0][indent + 3 :].split("<")[0]
		key_list.append(key.strip())
	return hwdata


def hardwareInventory(config, progressSubject=None):
	"""
	Collect hardware information on OSX.

	This method utilizes multiple os-specific commands
	to obtain hardware information and compiles it following
	a configuration list specifying keys and their attributes.

	:param config: Configuration for the audit, e.g. fetched from opsi backend.
	:type config: List

	:returns: Dictionary containing the result of the audit.
	:rtype: Dict
	"""
	if not config:
		logger.error("hardwareInventory: no config given")
		return {}
	opsiValues = {}

	hardwareList = []
	# Read output from system_profiler
	logger.debug("calling system_profiler command")
	getHardwareCommand = (
		"system_profiler SPParallelATADataType SPAudioDataType SPBluetoothDataType SPCameraDataType \
			SPCardReaderDataType SPEthernetDataType SPDiscBurningDataType SPFibreChannelDataType SPFireWireDataType \
			SPDisplaysDataType SPHardwareDataType SPHardwareRAIDDataType SPMemoryDataType SPNVMeDataType \
			SPNetworkDataType SPParallelSCSIDataType SPPowerDataType SPSASDataType SPSerialATADataType \
			SPStorageDataType SPThunderboltDataType SPUSBDataType SPSoftwareDataType"
	)
	cmd = "{}".format(getHardwareCommand)
	with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE) as proc:
		logger.debug("reading stdout stream from system_profiler")
		while True:
			line = proc.stdout.readline()
			if not line:
				break
			hardwareList.append(forceUnicode(line))
	profiler = parse_profiler_output(hardwareList)
	logger.debug("Parsed system_profiler info:")
	logger.debug(objectToBeautifiedText(profiler))

	hardwareList = []
	# Read output from systcl
	logger.debug("calling sysctl command")
	getHardwareCommand = "sysctl -a"
	cmd = "{}".format(getHardwareCommand)
	with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE) as proc:
		logger.debug("reading stdout stream from sysctl")
		while True:
			line = proc.stdout.readline()
			if not line:
				break
			hardwareList.append(forceUnicode(line))
	systcl = parse_sysctl_output(hardwareList)
	logger.debug("Parsed sysctl info:")
	logger.debug(objectToBeautifiedText(systcl))

	hardwareList = []
	# Read output from ioreg
	logger.debug("calling ioreg command")
	getHardwareCommand = "ioreg -l"
	cmd = "{}".format(getHardwareCommand)
	with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE) as proc:
		logger.debug("reading stdout stream from sysctl")
		while True:
			line = proc.stdout.readline()
			if not line:
				break
			hardwareList.append(forceUnicode(line))
	ioreg = parse_ioreg_output(hardwareList)
	logger.debug("Parsed ioreg info:")
	logger.debug(objectToBeautifiedText(ioreg))

	# Build hw info structure
	for hwClass in config:
		if not hwClass.get("Class"):
			continue
		opsiClass = hwClass["Class"].get("Opsi")
		osxClass = hwClass["Class"].get("OSX")

		if osxClass is None or opsiClass is None:
			continue

		logger.info("Processing class '%s' : '%s'", opsiClass, osxClass)
		opsiValues[opsiClass] = []

		command, section = osxClass.split("]", 1)
		command = command[1:]
		for singleclass in section.split("|"):
			(filterAttr, filterExp) = (None, None)
			if ":" in singleclass:
				(singleclass, filter_string) = singleclass.split(":", 1)
				if "." in filter_string:
					(filterAttr, filterExp) = filter_string.split(".", 1)

			singleclassdata = None
			if command == "profiler":
				# produce dictionary from key singleclass - traversed for all devices
				singleclassdata = get_tree_value(profiler, singleclass)
			elif command == "sysctl":
				# produce dictionary with only contents from key singleclass
				singleclassdata = {singleclass: get_tree_value(systcl, singleclass)}
			elif command == "ioreg":
				# produce dictionary with only contents from key singleclass
				singleclassdata = get_tree_value(ioreg, singleclass)
			if not singleclassdata:
				continue
			for key, dev in singleclassdata.items():
				if not isinstance(dev, dict):
					continue
				logger.debug("found device %s for singleclass %s", key, singleclass)
				if (
					filterAttr
					and dev.get(filterAttr)
					and not eval(f"str(dev.get(filterAttr)).{filterExp}")
				):
					continue
				device = {}
				for attribute in hwClass["Values"]:
					if not attribute.get("OSX"):
						continue
					for aname in attribute["OSX"].split("||"):
						aname = aname.strip()
						method = None
						if "." in aname:
							(aname, method) = aname.split(".", 1)
						value = get_tree_value(dev, aname)

						if method:
							try:
								logger.debug("Eval: %s.%s", value, method)
								device[attribute["Opsi"]] = eval(f"value.{method}")
							except Exception as err:
								device[attribute["Opsi"]] = ""
								logger.warning(
									"Class %s: Failed to excecute '%s.%s': %s",
									opsiClass,
									value,
									method,
									err,
								)
						else:
							device[attribute["Opsi"]] = value
						if device[attribute["Opsi"]]:
							break
				device["state"] = "1"
				device["type"] = "AuditHardwareOnHost"
				opsiValues[hwClass["Class"]["Opsi"]].append(device)

	opsiValues["SCANPROPERTIES"] = [{"scantime": time.strftime("%Y-%m-%d %H:%M:%S")}]
	logger.debug("Result of hardware inventory:")
	logger.debug(objectToBeautifiedText(opsiValues))
	return opsiValues


Posix.hardwareInventory = hardwareInventory


def getActiveSessionIds():
	"""
	Getting the IDs of the currently active sessions.

	.. versionadded:: 4.0.5


	:param data: Prefetched data to read information from.
	:type data: [str, ]
	:rtype: [int, ]
	"""
	return [1]


Posix.getActiveSessionIds = getActiveSessionIds


def is_mounted(devOrMountpoint):
	for line in execute("mount"):
		line = line.strip().lower()
		match = re.search(r"^(.*)\s+on\s+(.*)\s\(.*$", line)
		if match and devOrMountpoint.lower() in (match.group(1), match.group(2)):
			return True
	return False


Posix.is_mounted = is_mounted


def mount(dev, mountpoint, **options):
	dev = forceUnicode(dev)
	mountpoint = forceFilename(mountpoint)
	if not os.path.isdir(mountpoint):
		os.makedirs(mountpoint)

	if is_mounted(mountpoint):
		logger.debug(
			"Mountpoint '%s' already mounted, umounting before mount", mountpoint
		)
		umount(mountpoint)

	for key, value in options.items():
		options[key] = forceUnicode(value)

	if dev.lower().startswith(
		("smb://", "cifs://", "webdav://", "webdavs://", "http://", "https://")
	):
		match = re.search(
			r"^(smb|cifs|webdav|webdavs|http|https)://([^/]+)/([^/].*)$",
			dev,
			re.IGNORECASE,
		)
		if match:
			scheme = match.group(1).lower().replace("webdav", "http")
			server = match.group(2)
			share = match.group(3)
		else:
			raise ValueError(f"Bad {match.group(1)} uri '{dev}'")

		username = re.sub(r"\\+", r"\\", options.get("username", "guest")).replace(
			"\\", ";"
		)
		password = options.get("password", "")  # no urlencode needed for stdin
		command = f"mount_smbfs '//{username}@{server}/{share}' '{mountpoint}'"
		if scheme in ("http", "https"):
			command = f"mount_webdav -i '{scheme}://{server}/{share}' '{mountpoint}'"

		try:
			# Mount on macos only reads password from stdin -> expect script
			logger.info("Executing: %s", command)
			process = pexpect.spawn(command)
			if scheme in ("http", "https"):
				process.expect("Username.*: ")
				process.sendline(username)
			index = process.expect(["Password.*: ", pexpect.EOF])
			if index == 0:
				# It is possible that mount_smbfs caches a password and does not prompt for it again.
				process.sendline(password)
				process.expect(pexpect.EOF)
			output = process.before.decode("utf-8", "replace")
			process.close()
			exit_code = process.exitstatus
			logger.debug("Command exit code is %s, output: %s", exit_code, output)
			if exit_code != 0:
				raise RuntimeError(
					f"Command {command!r} failed with exit code {exit_code}: {output}"
				)
			# If expect hits timeout it throws a TIMEOUT exception
		except Exception as err:
			# Exit code 19 on mount_webdav means ssl cert not accepted
			logger.error("Failed to mount '%s': %s", dev, err)
			raise RuntimeError(f"Failed to mount '{dev}': {err}") from err
	else:
		raise ValueError(f"Cannot mount unknown fs type '{dev}'")


Posix.mount = mount
