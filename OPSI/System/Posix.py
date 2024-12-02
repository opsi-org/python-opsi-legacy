# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Posix

Functions and classes for the use with a POSIX operating system.
"""

import codecs
import copy as pycopy
import datetime
import fcntl
import getpass
import locale
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import warnings
from functools import lru_cache
from itertools import islice
from signal import SIGKILL

import psutil
from opsicommon.logging import LOG_NONE, get_logger, logging_config
from opsicommon.objects import *
from opsicommon.system.subprocess import (
	get_subprocess_environment as opsicommon_get_subprocess_environment,
)
from opsicommon.types import (
	forceBool,
	forceDomain,
	forceFilename,
	forceHardwareAddress,
	forceHardwareDeviceId,
	forceHardwareVendorId,
	forceHostId,
	forceHostname,
	forceInt,
	forceIpAddress,
	forceNetmask,
	forceUnicode,
	forceUnicodeLower,
)
from opsicommon.utils import frozen_lru_cache

from OPSI.Exceptions import CommandNotFoundException
from OPSI.Util import getfqdn, objectToBeautifiedText, removeUnit

distro_module = None
if platform.system() == "Linux":
	import distro as distro_module


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


# Constants
GEO_OVERWRITE_SO = "/usr/local/lib/geo_override.so"
BIN_WHICH = "/usr/bin/which"
DHCLIENT_LEASES_FILE = "/var/lib/dhcp/dhclient.leases"
_DHCP_SERVICE_NAME = None
_SAMBA_SERVICE_NAME = None
LD_LIBRARY_EXCLUDE_LIST = ["/usr/lib/opsiclientd"]

logger = get_logger("opsi.general")

hooks = []
x86_64 = False
try:
	if "64bit" in platform.architecture():
		x86_64 = True
except Exception:
	pass


class SystemSpecificHook:
	def __init__(self):
		pass

	def pre_reboot(self, wait):
		return wait

	def post_reboot(self, wait):
		return None

	def error_reboot(self, wait, exception):
		pass

	def pre_halt(self, wait):
		return wait

	def post_halt(self, wait):
		return None

	def error_halt(self, wait, exception):
		pass

	def pre_Harddisk_deletePartitionTable(self, harddisk):
		return None

	def post_Harddisk_deletePartitionTable(self, harddisk):
		return None

	def error_Harddisk_deletePartitionTable(self, harddisk, exception):
		pass

	def pre_Harddisk_writePartitionTable(self, harddisk):
		return None

	def post_Harddisk_writePartitionTable(self, harddisk):
		return None

	def error_Harddisk_writePartitionTable(self, harddisk, exception):
		pass

	def pre_Harddisk_readPartitionTable(self, harddisk):
		return None

	def post_Harddisk_readPartitionTable(self, harddisk):
		return None

	def error_Harddisk_readPartitionTable(self, harddisk, exception):
		pass

	def pre_Harddisk_setPartitionBootable(self, harddisk, partition, bootable):
		return (partition, bootable)

	def post_Harddisk_setPartitionBootable(self, harddisk, partition, bootable):
		return None

	def error_Harddisk_setPartitionBootable(
		self, harddisk, partition, bootable, exception
	):
		pass

	def pre_Harddisk_setPartitionId(self, harddisk, partition, id):
		return (partition, id)

	def post_Harddisk_setPartitionId(self, harddisk, partition, id):
		return None

	def error_Harddisk_setPartitionId(self, harddisk, partition, id, exception):
		pass

	def pre_Harddisk_readMasterBootRecord(self, harddisk):
		return None

	def post_Harddisk_readMasterBootRecord(self, harddisk, result):
		return result

	def error_Harddisk_readMasterBootRecord(self, harddisk, exception):
		pass

	def pre_Harddisk_writeMasterBootRecord(self, harddisk, system):
		return system

	def post_Harddisk_writeMasterBootRecord(self, harddisk, system):
		return None

	def error_Harddisk_writeMasterBootRecord(self, harddisk, system, exception):
		pass

	def pre_Harddisk_readPartitionBootRecord(self, harddisk, partition):
		return partition

	def post_Harddisk_readPartitionBootRecord(self, harddisk, partition, result):
		return result

	def error_Harddisk_readPartitionBootRecord(self, harddisk, partition, exception):
		pass

	def pre_Harddisk_writePartitionBootRecord(self, harddisk, partition, fsType):
		return (partition, fsType)

	def post_Harddisk_writePartitionBootRecord(self, harddisk, partition, fsType):
		return None

	def error_Harddisk_writePartitionBootRecord(
		self, harddisk, partition, fsType, exception
	):
		pass

	def pre_Harddisk_setNTFSPartitionStartSector(self, harddisk, partition, sector):
		return (partition, sector)

	def post_Harddisk_setNTFSPartitionStartSector(self, harddisk, partition, sector):
		return None

	def error_Harddisk_setNTFSPartitionStartSector(
		self, harddisk, partition, sector, exception
	):
		pass

	def pre_Harddisk_createPartition(self, harddisk, start, end, fs, type, boot, lba):
		return (start, end, fs, type, boot, lba)

	def post_Harddisk_createPartition(self, harddisk, start, end, fs, type, boot, lba):
		return None

	def error_Harddisk_createPartition(
		self, harddisk, start, end, fs, type, boot, lba, exception
	):
		pass

	def pre_Harddisk_deletePartition(self, harddisk, partition):
		return partition

	def post_Harddisk_deletePartition(self, harddisk, partition):
		return None

	def error_Harddisk_deletePartition(self, harddisk, partition, exception):
		pass

	def pre_Harddisk_mountPartition(self, harddisk, partition, mountpoint, **options):
		return (partition, mountpoint, options)

	def post_Harddisk_mountPartition(self, harddisk, partition, mountpoint, **options):
		return None

	def error_Harddisk_mountPartition(
		self, harddisk, partition, mountpoint, exception, **options
	):
		pass

	def pre_Harddisk_umountPartition(self, harddisk, partition):
		return partition

	def post_Harddisk_umountPartition(self, harddisk, partition):
		return None

	def error_Harddisk_umountPartition(self, harddisk, partition, exception):
		pass

	def pre_Harddisk_createFilesystem(self, harddisk, partition, fs):
		return (partition, fs)

	def post_Harddisk_createFilesystem(self, harddisk, partition, fs):
		return None

	def error_Harddisk_createFilesystem(self, harddisk, partition, fs, exception):
		pass

	def pre_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs):
		return (partition, size, fs)

	def post_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs):
		return None

	def error_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs, exception):
		pass

	def pre_Harddisk_shred(self, harddisk, partition, iterations, progressSubject):
		return (partition, iterations, progressSubject)

	def post_Harddisk_shred(self, harddisk, partition, iterations, progressSubject):
		return None

	def error_Harddisk_shred(
		self, harddisk, partition, iterations, progressSubject, exception
	):
		pass

	def pre_Harddisk_fill(self, harddisk, partition, infile, progressSubject):
		return (partition, infile, progressSubject)

	def post_Harddisk_fill(self, harddisk, partition, infile, progressSubject):
		return None

	def error_Harddisk_fill(
		self, harddisk, partition, infile, progressSubject, exception
	):
		pass

	def pre_Harddisk_saveImage(self, harddisk, partition, imageFile, progressSubject):
		return (partition, imageFile, progressSubject)

	def post_Harddisk_saveImage(self, harddisk, partition, imageFile, progressSubject):
		return None

	def error_Harddisk_saveImage(
		self, harddisk, partition, imageFile, progressSubject, exception
	):
		pass

	def pre_Harddisk_restoreImage(
		self, harddisk, partition, imageFile, progressSubject
	):
		return (partition, imageFile, progressSubject)

	def post_Harddisk_restoreImage(
		self, harddisk, partition, imageFile, progressSubject
	):
		return None

	def error_Harddisk_restoreImage(
		self, harddisk, partition, imageFile, progressSubject, exception
	):
		pass

	def pre_auditHardware(self, config, hostId, progressSubject):
		return (config, hostId, progressSubject)

	def post_auditHardware(self, config, hostId, result):
		return result

	def error_auditHardware(self, config, hostId, progressSubject, exception):
		pass


def addSystemHook(hook):
	if hook not in hooks:
		hooks.append(hook)


def removeSystemHook(hook):
	if hook in hooks:
		hooks.remove(hook)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                               INFO                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getHostname():
	return forceHostname(socket.gethostname())


def getFQDN():
	return forceUnicodeLower(socket.getfqdn())


def getKernelParams():
	"""
	Reads the kernel cmdline and returns a dict containing all key=value pairs.
	Keys are converted to lower case.

	:rtype: dict
	"""
	cmdline = ""
	try:
		logger.debug("Reading /proc/cmdline")
		with codecs.open("/proc/cmdline", "r", "utf-8") as file:
			cmdline = file.readline()

		cmdline = cmdline.strip()
	except IOError as err:
		raise IOError(f"Error reading '/proc/cmdline': {err}") from err

	params = {}
	for option in cmdline.split():
		keyValue = option.split("=")
		if len(keyValue) < 2:
			params[keyValue[0].strip().lower()] = ""
		else:
			params[keyValue[0].strip().lower()] = keyValue[1].strip()

	return params


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            NETWORK                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getEthernetDevices():
	"""
	Get the ethernet devices on the system.

	:return: For each device the name of the device.
	:rtype: [str]
	"""
	devices = []
	with open("/proc/net/dev", encoding="utf-8") as file:
		for line in file:
			line = line.strip()
			if not line or ":" not in line:
				continue

			device = line.split(":")[0].strip()
			if device.startswith(("eth", "ens", "eno", "tr", "br", "enp", "enx")):
				logger.info("Found ethernet device: '%s'", device)
				devices.append(device)

	return devices


def getNetworkInterfaces():
	"""
	Get information about the network interfaces on the system.

	:rtype: [{}]
	"""
	return [getNetworkDeviceConfig(device) for device in getEthernetDevices()]


def getNetworkDeviceConfig(device):
	if not device:
		raise ValueError("No device given")

	result = {
		"device": device,
		"hardwareAddress": None,
		"ipAddress": None,
		"broadcast": None,
		"netmask": None,
		"gateway": None,
		"vendorId": None,
		"deviceId": None,
	}

	try:
		for key, value in psutil.net_if_addrs().items():
			if key != device:
				continue
			for item in value:
				if item.family == socket.AF_INET:
					result["ipAddress"] = item.address
					result["broadcast"] = item.broadcast
					result["netmask"] = item.netmask
				elif item.family == psutil.AF_LINK:
					result["hardwareAddress"] = item.address
			# Skipping all others devices
			break
	except Exception:
		logger.warning("Failed to get address info for device %s", device)

	for line in execute(f"{which('ip')} route"):
		line = line.lower().strip()
		match = re.search(
			r"via\s(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\sdev\s(\S+)\s*", line
		)
		if match and match.group(2).lower() == device.lower():
			result["gateway"] = forceIpAddress(match.group(1))

	try:
		with open(f"/sys/class/net/{device}/device/vendor", encoding="utf-8") as file:
			val = int(file.read().strip(), 16)

		result["vendorId"] = forceHardwareVendorId(f"{val:>04x}")
		logger.notice(f'device {device} vendor ID is {result["vendorId"]}')
	except Exception:
		logger.debug(
			"Failed to get vendor id for network device %s, trying alternative", device
		)
		try:
			valList = execute(
				'udevadm info /sys/class/net/%s | grep VENDOR_ID | cut -d "=" -f 2'
				% device
			)
			result["vendorId"] = forceHardwareVendorId(f"{int(valList[0], 16):>04x}")
			logger.notice(f'device {device} vendor ID is {result["vendorId"]}')
		except Exception:
			logger.debug("Alternative failed, no vendor ID for device %s found", device)

	try:
		with open(f"/sys/class/net/{device}/device/device", encoding="utf-8") as file:
			val = int(file.read().strip(), 16)

		if result["vendorId"] == "1AF4":
			# FIXME: what is wrong with virtio devices?
			val += 0xFFF

		result["deviceId"] = forceHardwareDeviceId(f"{val:>04x}")
		logger.notice(f'device {device} device ID is {result["deviceId"]}')
	except Exception:
		logger.debug(
			"Failed to get device id for network device %s, trying alternative", device
		)
		try:
			valList = execute(
				f'udevadm info /sys/class/net/{device} | grep MODEL_ID | cut -d "=" -f 2'
			)
			val = int(valList[0], 16)

			if result["vendorId"] == "1AF4":
				val += 0xFFF

			result["deviceId"] = forceHardwareDeviceId(f"{val:>04x}")
			logger.notice(f'device {device} device ID is {result["deviceId"]}')
		except Exception:
			logger.debug("alternative failed, no vendor ID for device %s found", device)

	return result


def getDefaultNetworkInterfaceName():
	for interface in getNetworkInterfaces():
		if interface["gateway"]:
			logger.info("Default network interface found: %s", interface["device"])
			return interface["device"]
	logger.info("Default network interface not found")
	return None


class NetworkPerformanceCounter(threading.Thread):
	def __init__(self, interface):
		threading.Thread.__init__(self)
		if not interface:
			raise ValueError("No interface given")
		self.interface = interface
		self._lastBytesIn = 0
		self._lastBytesOut = 0
		self._lastTime = None
		self._bytesInPerSecond = 0
		self._bytesOutPerSecond = 0
		self._regex = re.compile(
			r"\s*(\S+):\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
			r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
		)
		self._running = False
		self._stopped = False
		self.start()

	def __del__(self):
		self.stop()

	def stop(self):
		self._stopped = True

	def run(self):
		self._running = True
		while not self._stopped:
			self._getStatistics()
			time.sleep(1)

	def _getStatistics(self):
		with open("/proc/net/dev", "r", encoding="utf-8") as file:
			for line in file:
				line = line.strip()
				match = self._regex.search(line)
				if match and match.group(1) == self.interface:
					#       |   Receive                                                |  Transmit
					# iface: bytes    packets errs drop fifo frame compressed multicast bytes    packets errs drop fifo colls carrier compressed
					now = time.time()
					bytesIn = int(match.group(2))
					bytesOut = int(match.group(10))
					timeDiff = 1
					if self._lastTime:
						timeDiff = now - self._lastTime
					if self._lastBytesIn:
						self._bytesInPerSecond = (
							bytesIn - self._lastBytesIn
						) / timeDiff
						self._bytesInPerSecond = max(self._bytesInPerSecond, 0)
					if self._lastBytesOut:
						self._bytesOutPerSecond = (
							bytesOut - self._lastBytesOut
						) / timeDiff
						self._bytesOutPerSecond = max(self._bytesOutPerSecond, 0)
					self._lastBytesIn = bytesIn
					self._lastBytesOut = bytesOut
					self._lastTime = now
					break

	def getBytesInPerSecond(self):
		return self._bytesInPerSecond

	def getBytesOutPerSecond(self):
		return self._bytesOutPerSecond


def getDHCPResult(device, leasesFile=None):
	"""
	Get the settings of the current DHCP lease.

	It first tries to read the value from leases files and then tries
	to read the values from pump.

	.. versionchanged:: 4.0.5.1
		Added parameter *leasesFile*.

	:param leasesFile: The file to read the leases from. If this is not \
given known places for this file will be tried.
	:type leasesFile: str
	:return: Settings of the lease. All keys are lowercase. Possible \
keys are: ``ip``, ``netmask``, ``bootserver``, ``nextserver``, \
``gateway``, ``bootfile``, ``hostname``, ``domain``.
	:rtype: dict
	"""
	if not device:
		raise ValueError("No device given")

	if not leasesFile:
		leasesFile = DHCLIENT_LEASES_FILE

	dhcpResult = {}
	if os.path.exists(leasesFile):
		with open(leasesFile, encoding="utf-8") as leasesFileHandler:
			try:
				currentInterface = None
				for line in leasesFileHandler:
					line = line.strip()
					if line.endswith(";"):
						line = line[:-1].strip()
					if line.startswith("interface "):
						currentInterface = line.split('"')[1]
					if device != currentInterface:
						continue

					if line.startswith("filename "):
						dhcpResult["bootfile"] = dhcpResult["filename"] = line.split(
							'"'
						)[1].strip()
					elif line.startswith("option domain-name "):
						dhcpResult["domain"] = dhcpResult["domain-name"] = line.split(
							'"'
						)[1].strip()
					elif line.startswith("option domain-name-servers "):
						dhcpResult["nameservers"] = dhcpResult[
							"domain-name-servers"
						] = line.split(" ", 2)[-1]
					elif line.startswith("fixed-address "):
						dhcpResult["ip"] = dhcpResult["fixed-address"] = line.split(
							" ", 1
						)[-1]
					elif line.startswith("option host-name "):
						dhcpResult["hostname"] = dhcpResult["host-name"] = line.split(
							'"'
						)[1].strip()
					elif line.startswith("option subnet-mask "):
						dhcpResult["netmask"] = dhcpResult["subnet-mask"] = line.split(
							" ", 2
						)[-1]
					elif line.startswith("option routers "):
						dhcpResult["gateways"] = dhcpResult["routers"] = line.split(
							" ", 2
						)[-1]
					elif line.startswith("option netbios-name-servers "):
						dhcpResult["netbios-name-servers"] = line.split(" ", 2)[-1]
					elif line.startswith("option dhcp-server-identifier "):
						dhcpResult["bootserver"] = dhcpResult[
							"dhcp-server-identifier"
						] = line.split(" ", 2)[-1]
					elif line.startswith("renew "):
						dhcpResult["renew"] = line.split(" ", 1)[-1]
					elif line.startswith("rebind "):
						dhcpResult["rebind"] = line.split(" ", 1)[-1]
					elif line.startswith("expire "):
						dhcpResult["expire"] = line.split(" ", 1)[-1]
			except Exception as error:
				logger.warning(error)
	else:
		logger.debug("Leases file %s does not exist.", leasesFile)
		logger.debug("Trying to use pump for getting dhclient info.")
		try:
			for line in execute(f"{which('pump')} -s -i {device}"):
				line = line.strip()
				keyValue = line.split(":")
				if len(keyValue) < 2:
					# No ":" in pump output after "boot server" and
					# "next server"
					if line.lstrip().startswith("Boot server"):
						keyValue[0] = "Boot server"
						keyValue.append(line.split()[2])
					elif line.lstrip().startswith("Next server"):
						keyValue[0] = "Next server"
						keyValue.append(line.split()[2])
					else:
						continue
				# Some DHCP-Servers are returning multiple domain names
				# seperated by whitespace, so we split all values at
				# whitespace and take the first element
				dhcpResult[keyValue[0].replace(" ", "").lower()] = (
					keyValue[1].strip().split()[0]
				)
		except Exception as error:
			logger.warning(error)
	return dhcpResult


def configureInterface(device, address, netmask=None):
	"""
	Configure the given device to use the given address.
	Optionally you can set a netmask aswell.

	:type device: str
	:type address: str
	:param netmask: Optionally set the netmask in format 12.34.56.78.
	:type netmask: str
	"""
	try:
		cmd = f"{which('ifconfig')} {device} {forceIpAddress(address)}"
		if netmask:
			cmd += f" netmask {forceNetmask(netmask)}"
		execute(cmd)
	except CommandNotFoundException:  # no ifconfig
		if netmask:
			preparedAddress = f"{forceIpAddress(address)}/{forceNetmask(netmask)}"
		else:
			preparedAddress = forceIpAddress(address)

		execute(f"{which('ip')} address add {preparedAddress} dev {device}")


def ifconfig(device, address, netmask=None):
	logger.warning("Method 'ifconfig' is deprecated. Use 'configureInterface' instead!")
	configureInterface(device, address, netmask)


def getLocalFqdn():
	fqdn = getfqdn()
	try:
		return forceHostId(fqdn)
	except ValueError as err:
		raise ValueError(
			f"Failed to get fully qualified domain name. Value '{fqdn}' is invalid."
		) from err


def getNetworkConfiguration(ipAddress=None):
	"""
	Get the network configuration for the local host.

	The returned dict will contain the keys 'ipAddress',
	'hardwareAddress', 'netmask', 'broadcast' and 'subnet'.

	:param ipAddress: Force the function to work with the given IP address.
	:type ipAddress: str
	:returns: Network configuration for the local host.
	:rtype: dict
	"""
	networkConfig = {
		"hardwareAddress": "",
		"ipAddress": "",
		"broadcast": "",
		"subnet": "",
	}

	if ipAddress:
		networkConfig["ipAddress"] = ipAddress
	else:
		fqdn = getLocalFqdn()
		try:
			networkConfig["ipAddress"] = socket.gethostbyname(fqdn)
		except socket.gaierror as err:
			logger.warning("Failed to get ip address: %s", err)
			return networkConfig

	if networkConfig["ipAddress"].split(".", 1)[0] in ("127", "169"):
		logger.info(
			"Not using IP %s because of restricted network block.",
			networkConfig["ipAddress"],
		)
		networkConfig["ipAddress"] = None

	for device in getEthernetDevices():
		devconf = getNetworkDeviceConfig(device)
		if devconf["ipAddress"] and devconf["ipAddress"].split(".")[0] not in (
			"127",
			"169",
		):
			if not networkConfig["ipAddress"]:
				networkConfig["ipAddress"] = devconf["ipAddress"]

			if networkConfig["ipAddress"] == devconf["ipAddress"]:
				networkConfig["netmask"] = devconf["netmask"]
				networkConfig["hardwareAddress"] = devconf["hardwareAddress"]
				break

	if not networkConfig["ipAddress"]:
		logger.warning("Failed to get a valid ip address for fqdn %r", fqdn)
		return networkConfig

	if not networkConfig.get("netmask"):
		networkConfig["netmask"] = "255.255.255.0"

	for i in range(4):
		if networkConfig["broadcast"]:
			networkConfig["broadcast"] += "."
		if networkConfig["subnet"]:
			networkConfig["subnet"] += "."

		networkConfig["subnet"] += "%d" % (
			int(networkConfig["ipAddress"].split(".")[i])
			& int(networkConfig["netmask"].split(".")[i])
		)
		networkConfig["broadcast"] += "%d" % (
			int(networkConfig["ipAddress"].split(".")[i])
			| int(networkConfig["netmask"].split(".")[i]) ^ 255
		)

	return networkConfig


def getSystemProxySetting():
	# TODO: Has to be implemented for posix machines
	logger.notice("Not Implemented yet")


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                   SESSION / DESKTOP HANDLING                                      -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def reboot(wait=10):
	for hook in hooks:
		wait = hook.pre_reboot(wait)

	try:
		wait = forceInt(wait)
		if wait > 0:
			execute(f"{which('sleep')} {wait}; {which('shutdown')} -r now", nowait=True)
		else:
			execute(f"{which('shutdown')} -r now", nowait=True)
	except Exception as err:
		for hook in hooks:
			hook.error_reboot(wait, err)
		raise

	for hook in hooks:
		hook.post_reboot(wait)


def halt(wait=10):
	for hook in hooks:
		wait = hook.pre_halt(wait)

	try:
		wait = forceInt(wait)
		if wait > 0:
			execute(f"{which('sleep')} {wait}; {which('shutdown')} -h now", nowait=True)
		else:
			execute(f"{which('shutdown')} -h now", nowait=True)
	except Exception as err:
		for hook in hooks:
			hook.error_halt(wait, err)
		raise

	for hook in hooks:
		hook.post_halt(wait)


shutdown = halt


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                        PROCESS HANDLING                                           -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
@frozen_lru_cache(100)
def which(cmd: str, env: dict = None) -> str:
	if env is not None:
		warnings.warn("Parameter env invalid", DeprecationWarning)
	path = shutil.which(cmd)
	if not path:
		raise CommandNotFoundException(f"Command '{cmd}' not found in PATH")
	return path


def get_subprocess_environment(
	env: dict = None, add_lc_all_C=False, add_path_sbin=False
):
	sp_env = opsicommon_get_subprocess_environment(env)

	if add_lc_all_C:
		sp_env["LC_ALL"] = "C"

	if add_path_sbin:
		path_parts = sp_env["PATH"].split(":")
		if "/usr/local/sbin" not in path_parts:
			path_parts.append("/usr/local/sbin")
		if "/usr/sbin" not in path_parts:
			path_parts.append("/usr/sbin")
		if "/sbin" not in path_parts:
			path_parts.append("/sbin")
		sp_env["PATH"] = ":".join(path_parts)

	return sp_env


def execute(
	cmd,
	nowait=False,
	getHandle=False,
	ignoreExitCode=[],
	exitOnStderr=False,
	captureStderr=True,
	encoding=None,
	timeout=0,
	shell=True,
	waitForEnding=None,
	env={},
	stdin_data=b"",
):
	"""
	Executes a command.

	:param nowait: If this is ``True`` the command will be executed and \
no waiting for it to finish will be done.
	:type nowait: bool
	:param getHandle: If this is ``True`` the handle the reference to \
the command output will be returned.
	:type getHandle: bool
	:param ignoreExitCode: Ignore exit codes of the program. This can \
be ``True`` to ignore all exit codes or a list of specific exit codes \
that should be ignored.
	:type ignoreExitCode: bool or list or tuple or set
	:param exitOnStderr: If this is ``True`` output on stderr will be \
interpreted as an failed execution and will throw an Exception.
	:type exitOnStderr: bool
	:param captureStderr: If this is ``True`` the output of *stderr* \
will be redirected to *stdout*.
	:type captureStderr: bool
	:param encoding: The encoding to be used to decode the output.
	:type encoding: str
	:param timeout: The time in seconds after that the execution will \
be aborted.
	:type timeout: int
	:param shell: Currently ignored. This is introduced to have the \
same keyword arguments as on Windows.
	:param waitForEnding: If this is set it will overwrite the setting \
for *nowait*. This is introduced to have the same keyword arguments as \
on Windows.
	:type waitForEnding: bool
	:param env: Additional environment variables to pass to subprocess.
	:type env: dict
	:return: If the command finishes and we wait for it to finish the \
output will be returned.
	:rtype: list
	"""
	if isinstance(cmd, list):
		if shell:
			logger.warning("Cmd as list should not be combined with shell=True")
	else:
		cmd = forceUnicode(cmd)
	nowait = forceBool(nowait)
	getHandle = forceBool(getHandle)
	exitOnStderr = forceBool(exitOnStderr)
	captureStderr = forceBool(captureStderr)
	timeout = forceInt(timeout)

	if waitForEnding is not None:
		logger.debug("Detected kwarg 'waitForEnding'. Overwriting nowait.")
		nowait = not forceBool(waitForEnding)

	sp_env = opsicommon_get_subprocess_environment()
	sp_env.update(env)

	exitCode = 0
	result = []
	startTime = time.time()
	try:
		logger.info("Executing: %s", cmd)

		if nowait:
			os.spawnve(os.P_NOWAIT, which("bash"), [which("bash"), "-c", cmd], sp_env)
			return []

		if getHandle:
			if captureStderr:
				return (
					subprocess.Popen(
						cmd,
						shell=shell,
						stdin=subprocess.PIPE,
						stdout=subprocess.PIPE,
						stderr=subprocess.STDOUT,
						env=sp_env,
					)
				).stdout
			return (
				subprocess.Popen(
					cmd,
					shell=shell,
					stdin=subprocess.PIPE,
					stdout=subprocess.PIPE,
					stderr=None,
					env=sp_env,
				)
			).stdout

		data = b""
		with subprocess.Popen(
			cmd,
			shell=shell,
			stdin=subprocess.PIPE if stdin_data else None,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE if captureStderr else subprocess.DEVNULL,
			env=sp_env,
		) as proc:
			if not encoding:
				encoding = locale.getpreferredencoding()
				if encoding == "ascii":
					encoding = "utf-8"
			logger.info("Using encoding '%s'", encoding)

			flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
			fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

			if captureStderr:
				flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
				fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)

			if stdin_data:
				proc.stdin.write(stdin_data)
				proc.stdin.flush()

			ret = None
			while ret is None:
				ret = proc.poll()
				try:
					chunk = proc.stdout.read()
					if chunk:
						data += chunk
				except IOError as err:
					if err.errno != 11:
						raise

				if captureStderr:
					try:
						chunk = proc.stderr.read()
						if chunk:
							if exitOnStderr:
								raise RuntimeError(f"Command '{cmd}' failed: {chunk}")
							data += chunk
					except IOError as err:
						if err.errno != 11:
							raise

				if time.time() - startTime >= timeout > 0:
					_terminateProcess(proc)
					raise RuntimeError(
						f"Command '{cmd}' timed out atfer {(time.time() - startTime)} seconds"
					)

				time.sleep(0.001)

		exitCode = ret
		if data:
			lines = data.split(b"\n")
			for _num, line in enumerate(lines):
				line = line.decode(encoding, "replace")
				logger.debug(">>> %s", line)
				result.append(line)

	except (os.error, IOError) as err:
		# Some error occurred during execution
		raise RuntimeError(f"Command '{cmd}' failed:\n{err}") from err

	logger.debug("Exit code: %s", exitCode)
	if exitCode:
		if isinstance(ignoreExitCode, bool) and ignoreExitCode:
			pass
		elif (
			isinstance(ignoreExitCode, (list, tuple, set))
			and exitCode in ignoreExitCode
		):
			pass
		else:
			result = "\n".join(result)
			raise RuntimeError(f"Command '{cmd}' failed ({exitCode}):\n{result}")
	return result


def _terminateProcess(process):
	"""
	Terminate a running process.

	:param process: The process to terminate.
	:type process: subprocess.Popen
	"""
	try:
		process.kill()
	except Exception as killException:
		logger.debug("Killing process %s failed: %s", process.pid, killException)

		try:
			os.kill(process.pid, SIGKILL)
		except Exception as sigKillException:
			logger.debug(
				"Sending SIGKILL to pid %s failed: %s", process.pid, sigKillException
			)


def terminateProcess(processHandle=None, processId=None):
	if not processId:
		raise ValueError("Process id must be given")

	processId = forceInt(processId)

	try:
		os.kill(processId, SIGKILL)
	except Exception as err:
		logger.warning("Sending SIGKILL to pid %s failed: %s", processId, err)
		raise


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            FILESYSTEMS                                            -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getHarddisks(data=None):
	"""
	Get the available harddisks from the machine.

	:param data: Data to parse through.
	:type data: [str, ]
	:return: The found harddisks.
	:rtype: [Harddisk, ]
	"""
	disks = []

	if data is None:
		# Get all available disks
		if os.path.exists("/dev/cciss"):
			result = []
			logger.notice(
				"HP Smart Array detected, trying to workarround scan problem."
			)
			listing = os.listdir("/dev/cciss")
			for entry in listing:
				if len(entry) < 5:
					dev = entry
					size = forceInt(
						execute(
							f"{which('sfdisk')} --no-reread -s /dev/cciss/{dev}",
							ignoreExitCode=[1],
						)[0]
					)
					logger.debug(
						"Found disk =>>> dev: '%s', size: %0.2f GB",
						dev,
						size / (1000 * 1000),
					)
					hd = Harddisk(f"/dev/cciss/{dev}")
					disks.append(hd)
			if len(disks) <= 0:
				raise RuntimeError("No harddisks found!")
			return disks
		result = execute(f"{which('sfdisk')} --no-reread -s ", ignoreExitCode=[1])
	else:
		result = data

	for line in result:
		if not line.lstrip().startswith("/dev"):
			continue

		(dev, size) = line.split(":")
		size = forceInt(size.strip())
		logger.debug(
			"Found disk =>>> dev: '%s', size: %0.2f GB", dev, size / (1000 * 1000)
		)
		hd = Harddisk(dev)
		disks.append(hd)

	if len(disks) <= 0:
		raise RuntimeError("No harddisks found!")

	return disks


def getDiskSpaceUsage(path):
	disk = os.statvfs(path)
	info = {
		"capacity": disk.f_bsize * disk.f_blocks,
		"available": disk.f_bsize * disk.f_bavail,
		"used": disk.f_bsize * (disk.f_blocks - disk.f_bavail),
		"usage": float(disk.f_blocks - disk.f_bavail) / float(disk.f_blocks),
	}
	logger.info("Disk space usage for path '%s': %s", path, info)
	return info


def is_mounted(devOrMountpoint):
	if platform.system() == "Linux":
		with codecs.open("/proc/mounts", "r", "utf-8") as file:
			for line in file.readlines():
				(dev, mountpoint) = line.split(" ", 2)[:2]
				if devOrMountpoint in (dev, mountpoint):
					return True
	return False


def mount(dev, mountpoint, **options):
	raise NotImplementedError(f"mount not implemented on {platform.system()}")


def umount(devOrMountpoint, max_attempts=10):
	if not is_mounted(devOrMountpoint):
		logger.info("'%s' not mounted, no need to umount", devOrMountpoint)
		return
	attempt = 0
	while True:
		attempt += 1
		try:
			execute(f"{which('umount')} {devOrMountpoint}")
			logger.info("'%s' umounted", devOrMountpoint)
			break
		except Exception as err:
			if attempt >= max_attempts:
				logger.error("Failed to umount '%s': %s", devOrMountpoint, err)
				raise RuntimeError(
					f"Failed to umount '{devOrMountpoint}': {err}"
				) from err

			logger.warning(
				"Failed to umount '%s' (attempt #%d): %s", devOrMountpoint, attempt, err
			)
			time.sleep(3)


def getBlockDeviceBusType(device):
	"""
	:return: 'IDE', 'SCSI', 'SATA', 'RAID' or None (not found)
	:rtype: str or None
	"""
	device = forceFilename(device)

	(devs, type) = ([], None)
	if os.path.islink(device):
		dev = os.readlink(device)
		if not dev.startswith("/"):
			dev = os.path.join(os.path.dirname(device), dev)
		device = dev

	for line in execute(f"{which('hwinfo')} --disk --cdrom"):
		if re.search(r"^\s+$", line):
			(devs, type) = ([], None)
			continue

		match = re.search(r"^\s+Device Files*:(.*)$", line)
		if match:
			if match.group(1).find(",") != -1:
				devs = match.group(1).split(",")
			elif match.group(1).find("(") != -1:
				devs = match.group(1).replace(")", " ").split("(")
			else:
				devs = [match.group(1)]

			devs = [currentDev.strip() for currentDev in devs]

		match = re.search(r"^\s+Attached to:\s+[^\(]+\((\S+)\s*", line)
		if match:
			type = match.group(1)

		if devs and device in devs and type:
			logger.info("Bus type of device '%s' is '%s'", device, type)
			return type
	return None


def getBlockDeviceContollerInfo(device, lshwoutput=None):
	device = forceFilename(device)
	if lshwoutput and isinstance(lshwoutput, list):
		lines = lshwoutput
	else:
		proc_env = get_subprocess_environment(add_lc_all_C=True, add_path_sbin=True)
		lines = execute("lshw -short -numeric", captureStderr=False, env=proc_env)
	# example:
	# ...
	# /0/100                      bridge     440FX - 82441FX PMC [Natoma] [8086:1237]
	# /0/100/1                    bridge     82371SB PIIX3 ISA [Natoma/Triton II] [8086:7000]
	# /0/100/1.1      scsi0       storage    82371SB PIIX3 IDE [Natoma/Triton II] [8086:7010]
	# /0/100/1.1/0    /dev/sda    disk       10GB QEMU HARDDISK
	# /0/100/1.1/0/1  /dev/sda1   volume     10236MiB Windows NTFS volume
	# /0/100/1.1/1    /dev/cdrom  disk       SCSI CD-ROM
	# ...
	storageControllers = {}

	for line in lines:
		match = re.search(
			r"^(/\S+)\s+(\S+)\s+storage\s+(\S+.*)\s\[([a-fA-F0-9]{1,4}):([a-fA-F0-9]{1,4})\]$",
			line,
		)
		if match:
			vendorId = match.group(4)
			while len(vendorId) < 4:
				vendorId = "0" + vendorId
			deviceId = match.group(5)
			while len(deviceId) < 4:
				deviceId = "0" + deviceId
			storageControllers[match.group(1)] = {
				"hwPath": forceUnicode(match.group(1)),
				"device": forceUnicode(match.group(2)),
				"description": forceUnicode(match.group(3)),
				"vendorId": forceHardwareVendorId(vendorId),
				"deviceId": forceHardwareDeviceId(deviceId),
			}
			continue

		parts = line.split(None, 3)
		if len(parts) < 4:
			continue

		if parts[1].lower() == device:
			for hwPath in storageControllers:
				if parts[0].startswith(hwPath + "/"):
					return storageControllers[hwPath]

	# emulated storage controller dirty-hack, for outputs like:
	# ...
	# /0/100/1f.2               storage        82801JD/DO (ICH10 Family) SATA AHCI Controller [8086:3A02]
	# /0/100/1f.3               bus            82801JD/DO (ICH10 Family) SMBus Controller [8086:3A60]
	# /0/1          scsi0       storage
	# /0/1/0.0.0    /dev/sda    disk           500GB ST3500418AS
	# /0/1/0.0.0/1  /dev/sda1   volume         465GiB Windows FAT volume
	# ...
	# In this case return the first AHCI controller, that will be found
	storageControllers = {}

	storagePattern = re.compile(
		r"^(/\S+)\s+storage\s+(\S+.*[Aa][Hh][Cc][Ii].*)\s\[([a-fA-F0-9]{1,4}):([a-fA-F0-9]{1,4})\]$"
	)
	for line in lines:
		match = storagePattern.search(line)
		if match:
			vendorId = match.group(3)
			while len(vendorId) < 4:
				vendorId = "0" + vendorId

			deviceId = match.group(4)
			while len(deviceId) < 4:
				deviceId = "0" + deviceId

			storageControllers[match.group(1)] = {
				"hwPath": forceUnicode(match.group(1)),
				"device": device,
				"description": forceUnicode(match.group(2)),
				"vendorId": forceHardwareVendorId(vendorId),
				"deviceId": forceHardwareDeviceId(deviceId),
			}

			for hwPath in storageControllers:
				return storageControllers[hwPath]
		else:
			# Quick Hack: for entry like this:
			# /0/100/1f.2              storage        82801 SATA Controller [RAID mode] [8086:2822]
			# This Quick hack is for Bios-Generations, that will only
			# have a choice for "RAID + AHCI", this devices will be shown as
			# RAID mode-Devices
			match = re.search(
				r"^(/\S+)\s+storage\s+(\S+.*[Rr][Aa][Ii][Dd].*)\s\[([a-fA-F0-9]{1,4}):([a-fA-F0-9]{1,4})\]$",
				line,
			)
			if match:
				vendorId = match.group(3)
				while len(vendorId) < 4:
					vendorId = "0" + vendorId

				deviceId = match.group(4)
				while len(deviceId) < 4:
					deviceId = "0" + deviceId

				storageControllers[match.group(1)] = {
					"hwPath": forceUnicode(match.group(1)),
					"device": device,
					"description": forceUnicode(match.group(2)),
					"vendorId": forceHardwareVendorId(vendorId),
					"deviceId": forceHardwareDeviceId(deviceId),
				}

				for hwPath in storageControllers:
					return storageControllers[hwPath]

	return None


class Harddisk:
	def __init__(self, device):
		self.device = forceFilename(device)
		self.model = ""
		self.signature = None
		self.biosDevice = None
		self.totalCylinders = 0
		self.totalSectors = 0
		self.cylinders = 0
		self.heads = 0
		self.sectors = 0
		self.bytesPerSector = 512
		self.bytesPerCylinder = 0
		self.label = None
		self.size = -1
		self.partitions = []
		self.ldPreload = None
		self.dosCompatibility = True
		self.blockAlignment = False
		self.rotational = True

		self.useBIOSGeometry()
		self.readPartitionTable()
		self.readRotational()

	def setDosCompatibility(self, comp=True):
		self.dosCompatibility = bool(comp)

	def setBlockAlignment(self, align=False):
		self.blockAlignment = bool(align)

	def getBusType(self):
		return getBlockDeviceBusType(self.device)

	def getControllerInfo(self):
		return getBlockDeviceContollerInfo(self.device)

	def useBIOSGeometry(self):
		# Make sure your kernel supports edd (CONFIG_EDD=y/m) and module is loaded if not compiled in
		try:
			execute("modprobe edd")
		except Exception as err:
			logger.debug(err)
			return

		# geo_override.so will affect all devices !
		if not x86_64:
			logger.info("Using geo_override.so for all disks.")
			self.ldPreload = GEO_OVERWRITE_SO
		else:
			logger.info("Don't load geo_override.so on 64bit architecture.")

	def readRotational(self):
		"""
		Checks if a disk is rotational.

		The result of the check is saved in the attribute *rotational*.

		.. versionadded:: 4.0.4.2
		"""
		try:
			deviceparts = self.device.split("/")
			if len(deviceparts) > 3:
				if deviceparts[2].lower() == "cciss":
					logger.info("Special device (cciss) detected")
					devicename = "!".join(deviceparts[1:])
					if not os.path.exists(f"/sys/block/{devicename}/queue/rotational"):
						raise IOError(
							f"rotational file '/sys/block/{devicename}/queue/rotational' not found!"
						)
				else:
					logger.error("Unknown device, fallback to default: rotational")
					return
			else:
				devicename = self.device.split("/")[2]

			for line in execute(f"cat /sys/block/{devicename}/queue/rotational"):
				try:
					self.rotational = forceBool(int(line.strip()))
					break
				except Exception:
					pass
		except Exception as err:
			logger.error(
				"Checking if the device %s is rotational failed: %s", self.device, err
			)

	def getSignature(self):
		hd = os.open(str(self.device), os.O_RDONLY)
		try:
			os.lseek(hd, 440, 0)
			dat = os.read(hd, 4)
		finally:
			os.close(hd)

		logger.debug(
			"Read signature from device '%s': %s,%s,%s,%s",
			self.device,
			ord(dat[0]),
			ord(dat[1]),
			ord(dat[2]),
			ord(dat[3]),
		)

		self.signature = 0
		self.signature += ord(dat[3]) << 24
		self.signature += ord(dat[2]) << 16
		self.signature += ord(dat[1]) << 8
		self.signature += ord(dat[0])
		logger.debug("Device Signature: '%s'", hex(self.signature))

	def setDiskLabelType(self, label):
		label = forceUnicodeLower(label)
		if label not in ("bsd", "gpt", "loop", "mac", "mips", "msdos", "pc98", "sun"):
			raise ValueError(f"Unknown disk label '{label}'")
		self.label = label

	def setPartitionId(self, partition, id):
		part_id = id
		for hook in hooks:
			(partition, part_id) = hook.pre_Harddisk_setPartitionId(
				self, partition, part_id
			)
		try:
			partition = forceInt(partition)
			part_id = forceUnicodeLower(part_id)

			if (partition < 1) or (partition > 4):
				raise ValueError("Partition has to be int value between 1 and 4")

			if not re.search(r"^[a-f0-9]{2}$", part_id):
				if part_id in (
					"linux",
					"ext2",
					"ext3",
					"ext4",
					"xfs",
					"reiserfs",
					"reiser4",
				):
					part_id = "83"
				elif part_id == "linux-swap":
					part_id = "82"
				elif part_id == "fat32":
					part_id = "0c"
				elif part_id == "ntfs":
					part_id = "07"
				else:
					raise ValueError(f"Partition type '{part_id}' not supported!")
			part_id = eval("0x" + part_id)
			offset = 0x1BE + (partition - 1) * 16 + 4
			with open(self.device, "rb+") as file:
				file.seek(offset)
				file.write(chr(part_id))
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_setPartitionId(self, partition, part_id, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_setPartitionId(self, partition, part_id)

	def setPartitionBootable(self, partition, bootable):
		for hook in hooks:
			(partition, bootable) = hook.pre_Harddisk_setPartitionBootable(
				self, partition, bootable
			)
		try:
			partition = forceInt(partition)
			bootable = forceBool(bootable)
			if (partition < 1) or (partition > 4):
				raise ValueError("Partition has to be int value between 1 and 4")

			offset = 0x1BE + (partition - 1) * 16 + 4
			with open(self.device, "rb+") as file:
				file.seek(offset)
				if bootable:
					file.write(chr(0x80))
				else:
					file.write(chr(0x00))
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_setPartitionBootable(self, partition, bootable, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_setPartitionBootable(self, partition, bootable)

	def readPartitionTable(self):
		for hook in hooks:
			hook.pre_Harddisk_readPartitionTable(self)

		try:
			self.partitions = []
			sp_env = {"LC_ALL": "C"}
			if self.ldPreload:  # We want this as a context manager!
				sp_env["LD_PRELOAD"] = self.ldPreload
			result = execute(
				f"{which('sfdisk')} --no-reread -s {self.device}",
				ignoreExitCode=[1],
				env=sp_env,
			)
			for line in result:
				try:
					self.size = int(line.strip()) * 1024
				except Exception:
					pass

			logger.info(
				"Size of disk '%s': %s Byte / %s MB",
				self.device,
				self.size,
				(self.size / (1000 * 1000)),
			)
			result = execute(
				f"{which('sfdisk')} --no-reread -l {self.device}",
				ignoreExitCode=[1],
				env=sp_env,
			)
			partTablefound = None
			for line in result:
				if line.startswith("/dev"):
					partTablefound = True
					break
			if not partTablefound:
				logger.notice(
					"unrecognized partition table type, writing empty partitiontable"
				)
				execute(
					f'{which("echo")} -e "0,0\n\n\n\n" | {which("sfdisk")} --no-reread {self.device}',
					ignoreExitCode=[1],
					env=sp_env,
				)
				result = execute(
					f"{which('sfdisk')} --no-reread -l {self.device}",
					ignoreExitCode=[1],
					env=sp_env,
				)

			self._parsePartitionTable(result)

			result = execute(
				f"{which('sfdisk')} --no-reread -uS -l {self.device}",
				ignoreExitCode=[1],
				env=sp_env,
			)
			self._parseSectorData(result)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_readPartitionTable(self, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_readPartitionTable(self)

	def _parsePartitionTable(self, sfdiskListingOutput):
		"""
		Parses the partition table and sets the corresponding attributes
		on this object.

		:param sfdiskListingOutput: The output from ``sfdisk -l /dev/foo``
		:type sfdiskListingOutput: [str, ]
		"""

		for line in sfdiskListingOutput:
			line = line.strip()

			if line.lower().startswith("disk"):
				geometryOutput = execute(f"{which('sfdisk')} -g {self.device}")
				for gline in geometryOutput:
					if gline:
						logger.notice("geometryLine : %s", gline)
						match = re.search(
							r"\s+(\d+)\s+cylinders,\s+(\d+)\s+heads,\s+(\d+)\s+sectors",
							gline,
						)
						if not match:
							raise RuntimeError(
								f"Unable to get geometry for disk '{self.device}'"
							)
						self.cylinders = forceInt(match.group(1))
						self.heads = forceInt(match.group(2))
						self.sectors = forceInt(match.group(3))
						self.totalCylinders = self.cylinders

			elif line.lower().startswith("units"):
				match = re.search(
					r"sectors\s+of\s+\d\s+.\s+\d+\s+.\s+(\d+)\s+bytes", line
				)
				if not match:
					raise RuntimeError(
						f"Unable to get bytes/cylinder for disk '{self.device}'"
					)
				self.bytesPerCylinder = forceInt(match.group(1))
				self.totalCylinders = int(self.size / self.bytesPerCylinder)
				logger.info(
					"Total cylinders of disk '%s': %d, %d bytes per cylinder",
					self.device,
					self.totalCylinders,
					self.bytesPerCylinder,
				)

			elif line.startswith(self.device):
				match = re.search(
					rf"({self.device}p*)(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\d+)[\+\-]*.?\d*\S+\s+(\S+)\s*(.*)",
					line,
				)
				if not match:
					raise RuntimeError(
						f"Unable to read partition table of disk '{self.device}'"
					)

				if match.group(5):
					boot = False
					if match.group(3) == "*":
						boot = True

					fs = "unknown"
					fsType = forceUnicodeLower(match.group(8))
					if fsType in ("w95", "b", "c", "e"):
						fs = "fat32"
					elif fsType in ("hpfs/ntfs/exfat", "hfps/ntfs", "7"):
						fs = "ntfs"

					deviceName = forceFilename(match.group(1) + match.group(2))
					try:
						logger.debug("Trying using Blkid")
						fsres = execute(
							f"{which('blkid')} -o value -s TYPE {deviceName}"
						)
						if fsres:
							for fsline in fsres:
								fsline = fsline.strip()
								if not fsline:
									continue
								logger.debug(
									"Found filesystem: %s with blkid tool, using now this filesystemtype.",
									fsline,
								)
								fs = fsline
					except Exception:
						pass

					partitionData = {
						"device": deviceName,
						"number": forceInt(match.group(2)),
						"cylStart": forceInt(match.group(4)),
						"cylEnd": forceInt(match.group(5)),
						"cylSize": forceInt(match.group(6)),
						"start": forceInt(match.group(4)) * self.bytesPerCylinder,
						"end": (forceInt(match.group(5)) + 1) * self.bytesPerCylinder,
						"size": forceInt(match.group(6)) * self.bytesPerCylinder,
						"type": fsType,
						"fs": fs,
						"boot": boot,
					}

					self.partitions.append(partitionData)

					logger.debug(
						"Partition found =>>> number: %s, "
						"start: %s MB (%s cyl), end: %s MB (%s cyl), "
						"size: %s MB (%s cyl), "
						"type: %s, fs: %s, boot: %s",
						partitionData["number"],
						partitionData["start"] / (1024 * 1024),
						partitionData["cylStart"],
						partitionData["end"] / (1024 * 1024),
						partitionData["cylEnd"],
						partitionData["size"] / (1024 * 1024),
						partitionData["cylSize"],
						match.group(8),
						fs,
						boot,
					)

					if partitionData["device"]:
						logger.debug(
							"Waiting for device '%s' to appear", partitionData["device"]
						)
						timeout = 15
						while timeout > 0:
							if os.path.exists(partitionData["device"]):
								break
							time.sleep(1)
							timeout -= 1
						if os.path.exists(partitionData["device"]):
							logger.debug("Device '%s' found", partitionData["device"])
						else:
							logger.warning(
								"Device '%s' not found", partitionData["device"]
							)

	def _parseSectorData(self, outputFromSfDiskListing):
		"""
		Parses the sector data of the disk and extends the existing
		partition data.

		:param outputFromSfDiskListing: Output of ``sfdisk -uS -l /dev/foo``
		:type outputFromSfDiskListing: [str, ]
		"""
		for line in outputFromSfDiskListing:
			line = line.strip()

			if line.startswith(self.device):
				match = re.match(
					rf"{self.device}p*(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\d+)[\+\-]*.?\d*\S+\s+(\S+)\s*(.*)",
					line,
				)
				if not match:
					raise RuntimeError(
						f"Unable to read partition table (sectors) of disk '{self.device}'"
					)

				if match.group(4):
					for pnum, partition in enumerate(self.partitions):
						if forceInt(partition["number"]) == forceInt(match.group(1)):
							partition["secStart"] = forceInt(match.group(3))
							partition["secEnd"] = forceInt(match.group(4))
							partition["secSize"] = forceInt(match.group(5))
							self.partitions[pnum] = partition
							logger.debug(
								"Partition sector values =>>> number: %s, start: %s sec, end: %s sec, size: %s sec ",
								partition["number"],
								partition["secStart"],
								partition["secEnd"],
								partition["secSize"],
							)
							break

			elif line.lower().startswith("units"):
				match = re.search(
					r"sectors\s+of\s+\d\s+.\s+\d+\s+.\s+(\d+)\s+bytes", line
				)

				if not match:
					raise RuntimeError(
						f"Unable to get bytes/sector for disk '{self.device}'"
					)
				self.bytesPerSector = forceInt(match.group(1))
				self.totalSectors = int(self.size / self.bytesPerSector)
				logger.info(
					"Total sectors of disk '%s': %d, %d bytes per cylinder",
					self.device,
					self.totalSectors,
					self.bytesPerSector,
				)

	def writePartitionTable(self):
		logger.debug("Writing partition table to disk %s", self.device)
		for hook in hooks:
			hook.pre_Harddisk_writePartitionTable(self)
		try:
			cmd = f'{which("echo")} -e "'
			for pnum in range(4):
				try:
					part = self.getPartition(pnum + 1)
					if self.blockAlignment:
						logger.debug(
							"   number: %s, start: %s MB (%s sec), "
							"end: %s MB (%s sec), size: %s MB (%s sec), "
							"type: %s, fs: %s, boot: %s",
							part["number"],
							(part["start"] / (1000 * 1000)),
							part["secStart"],
							(part["end"] / (1000 * 1000)),
							part["secEnd"],
							(part["size"] / (1000 * 1000)),
							part["secSize"],
							part["type"],
							part["fs"],
							part["boot"],
						)

						cmd += f"{part['secStart']},{part['secSize']},{part['type']}"
					else:
						logger.debug(
							"   number: %s, start: %s MB (%s cyl), "
							"end: %s MB (%s cyl), size: %s MB (%s cyl), "
							"type: %s, fs: %s, boot: %s",
							part["number"],
							(part["start"] / (1000 * 1000)),
							part["cylStart"],
							(part["end"] / (1000 * 1000)),
							part["cylEnd"],
							(part["size"] / (1000 * 1000)),
							part["cylSize"],
							part["type"],
							part["fs"],
							part["boot"],
						)

						cmd += f"{part['cylStart']},{part['cylSize']},{part['type']}"

					if part["boot"]:
						cmd += ",*"
				except Exception as err:
					logger.debug("Partition %d not found: %s", (pnum + 1), err)
					cmd += "0,0"

				cmd += "\n"

			if self.blockAlignment:
				cmd += f'" | {which("sfdisk")} -L --no-reread -uS -f {self.device}'
			else:
				cmd += f'" | {which("sfdisk")} -L --no-reread {self.device}'

			sp_env = {}
			if self.ldPreload:
				sp_env["LD_PRELOAD"] = self.ldPreload
			execute(cmd, ignoreExitCode=[1], env=sp_env)

			self._forceReReadPartionTable()
			time.sleep(2)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_writePartitionTable(self, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_writePartitionTable(self)

	def _forceReReadPartionTable(self):
		sp_env = {}
		if self.ldPreload:
			sp_env["LD_PRELOAD"] = self.ldPreload
		logger.info("Forcing kernel to reread partition table of '%s'.", self.device)
		try:
			execute(f"{which('partprobe')} {self.device}", env=sp_env)
		except Exception:
			logger.error(
				"Forcing kernel reread partion table failed, waiting 5 sec. and try again"
			)
			try:
				time.sleep(5)
				execute(f"{which('partprobe')} {self.device}", ignoreExitCode=[1])
			except Exception:
				logger.error("Reread Partiontabel failed the second time, given up.")
				raise

	def deletePartitionTable(self):
		logger.info("Deleting partition table on '%s'", self.device)
		for hook in hooks:
			hook.pre_Harddisk_deletePartitionTable(self)
		try:
			with open(self.device, "rb+") as file:
				file.write(bytes([0] * 512))

			self._forceReReadPartionTable()
			self.label = None
			self.partitions = []
			self.readPartitionTable()
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_deletePartitionTable(self, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_deletePartitionTable(self)

	def shred(self, partition=0, iterations=25, progressSubject=None):
		for hook in hooks:
			(partition, iterations, progressSubject) = hook.pre_Harddisk_shred(
				self, partition, iterations, progressSubject
			)

		try:
			partition = forceInt(partition)
			iterations = forceInt(iterations)

			dev = self.device
			if partition != 0:
				dev = self.getPartition(partition)["device"]

			cmd = f"{which('shred')} -v -n {iterations} {dev} 2>&1"

			lineRegex = re.compile(r"\s(\d+)\/(\d+)\s\(([^\)]+)\)\.\.\.(.*)$")
			posRegex = re.compile(r"([^\/]+)\/(\S+)\s+(\d+)%")
			handle = execute(cmd, getHandle=True)
			position = ""
			error = ""
			if progressSubject:
				progressSubject.setEnd(100)

			for line in iter(lambda: handle.readline().strip(), ""):
				logger.debug("From shred =>>> %s", line)
				# shred: /dev/xyz: Pass 1/25 (random)...232MiB/512MiB 45%
				match = re.search(lineRegex, line)
				if match:
					iteration = forceInt(match.group(1))
					dataType = match.group(3)
					logger.debug("Iteration: %d, data-type: %s", iteration, dataType)
					match = re.search(posRegex, match.group(4))
					if match:
						position = match.group(1) + "/" + match.group(2)
						percent = forceInt(match.group(3))
						logger.debug("Position: %s, percent: %d", position, percent)
						if progressSubject and (percent != progressSubject.getState()):
							progressSubject.setState(percent)
							progressSubject.setMessage(
								f"Pass {iteration}/{iterations} ({dataType}), position: {position}"
							)
				else:
					error = line

			ret = handle.close()
			logger.debug("Exit code: %s", ret)

			if ret:
				raise RuntimeError(f"Command '{cmd}' failed: {error}")

		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_shred(
					self, partition, iterations, progressSubject, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_shred(self, partition, iterations, progressSubject)

	def zeroFill(self, partition=0, progressSubject=None):
		self.fill(forceInt(partition), "/dev/zero", progressSubject)

	def randomFill(self, partition=0, progressSubject=None):
		self.fill(forceInt(partition), "/dev/urandom", progressSubject)

	def fill(self, partition=0, infile="", progressSubject=None):
		for hook in hooks:
			(partition, infile, progressSubject) = hook.pre_Harddisk_fill(
				self, partition, infile, progressSubject
			)

		try:
			partition = forceInt(partition)
			if not infile:
				raise ValueError("No input file given")
			infile = forceFilename(infile)

			xfermax = 0
			dev = self.device
			if partition != 0:
				dev = self.getPartition(partition)["device"]
				xfermax = int(round(float(self.getPartition(partition)["size"]) / 1024))
			else:
				xfermax = int(round(float(self.size) / 1024))

			if progressSubject:
				progressSubject.setEnd(100)

			cmd = f"{which('dd_rescue')} -m {xfermax}k {infile} {dev} 2>&1"

			handle = execute(cmd, getHandle=True)
			done = False

			skip = 0
			rate = 0
			position = 0
			timeout = 0
			while not done:
				inp = handle.read(1024)
				# dd_rescue: (info): ipos:    720896.0k, opos:    720896.0k, xferd:    720896.0k
				# 		   errs:      0, errxfer:         0.0k, succxfer:    720896.0k
				# 	     +curr.rate:    21843kB/s, avg.rate:    23526kB/s, avg.load: 17.4%
				if inp:
					timeout = 0
					skip += 1
					if "Summary" in inp:
						done = True

				elif timeout >= 10:
					raise RuntimeError("Failed (timed out)")

				else:
					timeout += 1
					continue

				if skip < 10:
					time.sleep(0.1)
					continue
				skip = 0

				if progressSubject:
					match = re.search(r"avg\.rate:\s+(\d+)kB/s", inp)
					if match:
						rate = match.group(1)
					match = re.search(r"ipos:\s+(\d+)\.\d+k", inp)
					if match:
						position = forceInt(match.group(1))
						percent = (position * 100) / xfermax
						logger.debug(
							"Position: %s, xfermax: %s, percent: %s",
							position,
							xfermax,
							percent,
						)
						if percent != progressSubject.getState():
							progressSubject.setState(percent)
							progressSubject.setMessage(
								f"Pos: {round((position) / 1024)} MB, average transfer rate: {rate} kB/s"
							)

			if progressSubject:
				progressSubject.setState(100)
			time.sleep(3)
			if handle:
				handle.close()
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_fill(self, partition, infile, progressSubject, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_fill(self, partition, infile, progressSubject)

	def readMasterBootRecord(self):
		for hook in hooks:
			hook.pre_Harddisk_readMasterBootRecord(self)
		mbr = None
		try:
			with open(self.device, "rb") as file:
				mbr = file.read(512)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_readMasterBootRecord(self, err)
			raise

		for hook in hooks:
			mbr = hook.post_Harddisk_readMasterBootRecord(self, mbr)
		return mbr

	def writeMasterBootRecord(self, system="auto"):
		for hook in hooks:
			system = hook.pre_Harddisk_writeMasterBootRecord(self, system)

		try:
			system = forceUnicodeLower(system)

			try:
				logger.debug("Try to determine ms-sys version")
				cmd = f"{which('ms-sys')} -v"
				res = execute(cmd)
				if res:
					ms_sys_version = res[0][14:].strip()
			except Exception:
				ms_sys_version = "2.1.3"

			mbrType = "-w"

			if system in ("win2000", "winxp", "win2003", "nt5"):
				mbrType = "--mbr"
			elif system in ("vista", "win7", "nt6"):
				if ms_sys_version != "2.1.3":
					if system == "vista":
						mbrType = "--mbrvista"
					else:
						mbrType = "--mbr7"
				else:
					mbrType = "--mbrnt60"
			elif system in ("win9x", "win95", "win98"):
				mbrType = "--mbr95b"
			elif system in ("dos", "winnt"):
				mbrType = "--mbrdos"

			logger.info(
				"Writing master boot record on '%s' (system: %s)", self.device, system
			)

			cmd = f"{which('ms-sys')} {mbrType} {self.device}"
			try:
				sp_env = {}
				if self.ldPreload:
					sp_env["LD_PRELOAD"] = self.ldPreload
				execute(cmd, env=sp_env)
			except Exception as err:
				logger.error("Failed to write mbr: %s", err)
				raise RuntimeError(f"Failed to write mbr: {err}") from err
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_writeMasterBootRecord(self, system, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_writeMasterBootRecord(self, system)

	def readPartitionBootRecord(self, partition=1):
		for hook in hooks:
			partition = hook.pre_Harddisk_readPartitionBootRecord(self, partition)
		pbr = None
		try:
			with open(self.getPartition(partition)["device"], "rb") as file:
				pbr = file.read(512)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_readPartitionBootRecord(self, partition, err)
			raise

		for hook in hooks:
			pbr = hook.post_Harddisk_readPartitionBootRecord(self, partition, pbr)
		return pbr

	def writePartitionBootRecord(self, partition=1, fsType="auto"):
		for hook in hooks:
			(partition, fsType) = hook.pre_Harddisk_writePartitionBootRecord(
				self, partition, fsType
			)

		try:
			partition = forceInt(partition)
			fsType = forceUnicodeLower(fsType)

			logger.info(
				"Writing partition boot record on '%s' (fs-type: %s)",
				self.getPartition(partition)["device"],
				fsType,
			)

			if fsType == "auto":
				fsType = "-w"
			else:
				fsType = f"--{fsType}"

			time.sleep(10)

			cmd = f"{which('ms-sys')} -p {fsType} {self.getPartition(partition)['device']}"
			try:
				sp_env = {}
				if self.ldPreload:
					sp_env["LD_PRELOAD"] = self.ldPreload
				result = execute(cmd, env=sp_env)
				if "successfully" not in result[0]:
					raise RuntimeError(result)
			except Exception as err:
				logger.error("Cannot write partition boot record: %s", err)
				raise RuntimeError(
					f"Cannot write partition boot record: {err}"
				) from err
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_writePartitionBootRecord(
					self, partition, fsType, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_writePartitionBootRecord(self, partition, fsType)

	def setNTFSPartitionStartSector(self, partition, sector=0):
		for hook in hooks:
			(partition, sector) = hook.pre_Harddisk_setNTFSPartitionStartSector(
				self, partition, sector
			)

		try:
			partition = forceInt(partition)
			sector = forceInt(sector)
			if not sector:
				sector = self.getPartition(partition)["secStart"]
				if not sector:
					err = f"Failed to get partition start sector of partition '{self.getPartition(partition)['device']}'"
					logger.error(err)
					raise RuntimeError(err)

			logger.info(
				"Setting Partition start sector to %s in NTFS boot record on partition '%s'",
				sector,
				self.getPartition(partition)["device"],
			)

			dat = [0, 0, 0, 0]
			dat[0] = int((sector & 0x000000FF))
			dat[1] = int((sector & 0x0000FF00) >> 8)
			dat[2] = int((sector & 0x00FF0000) >> 16)
			dat[3] = int((sector & 0xFFFFFFFF) >> 24)

			hd = os.open(self.getPartition(partition)["device"], os.O_RDONLY)
			try:
				os.lseek(hd, 0x1C, 0)
				start = os.read(hd, 4)
				logger.debug(
					"NTFS Boot Record currently using %s %s %s %s as partition start sector",
					hex(start[0]),
					hex(start[1]),
					hex(start[2]),
					hex(start[3]),
				)
			finally:
				os.close(hd)

			logger.debug("Manipulating NTFS Boot Record!")
			hd = os.open(self.getPartition(partition)["device"], os.O_WRONLY)
			logger.info(
				"Writing new value %s %s %s %s at 0x1c",
				hex(dat[0]),
				hex(dat[1]),
				hex(dat[2]),
				hex(dat[3]),
			)
			try:
				os.lseek(hd, 0x1C, 0)
				for i in dat:
					os.write(hd, str.encode(chr(i)))
			finally:
				os.close(hd)

			hd = os.open(self.getPartition(partition)["device"], os.O_RDONLY)
			try:
				os.lseek(hd, 0x1C, 0)
				start = os.read(hd, 4)
				logger.debug(
					"NTFS Boot Record now using %s %s %s %s as partition start sector",
					hex(start[0]),
					hex(start[1]),
					hex(start[2]),
					hex(start[3]),
				)
			finally:
				os.close(hd)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_setNTFSPartitionStartSector(
					self, partition, sector, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_setNTFSPartitionStartSector(self, partition, sector)

	def getPartitions(self):
		return self.partitions

	def getPartition(self, number):
		number = forceInt(number)
		for part in self.partitions:
			if part["number"] == number:
				return part
		raise ValueError(f"Partition {number} does not exist")

	def createPartition(
		self, start, end, fs, type="primary", boot=False, lba=False, number=None
	):
		for hook in hooks:
			(start, end, fs, type, boot, lba) = hook.pre_Harddisk_createPartition(
				self, start, end, fs, type, boot, lba
			)
		try:
			start = forceUnicodeLower(start)
			end = forceUnicodeLower(end)
			fs = forceUnicodeLower(fs)
			type = forceUnicodeLower(type)
			boot = forceBool(boot)
			lba = forceBool(lba)

			partId = "00"
			if re.search(r"^[a-f0-9]{2}$", fs):
				partId = fs
			else:
				if fs in (
					"ext2",
					"ext3",
					"ext4",
					"xfs",
					"reiserfs",
					"reiser4",
					"linux",
				):
					partId = "83"
				elif fs == "linux-swap":
					partId = "82"
				elif fs == "fat32":
					partId = "c"
				elif fs == "ntfs":
					partId = "7"
				else:
					raise ValueError(f"Filesystem '{fs}' not supported!")

			if type != "primary":
				raise ValueError(f"Type '{type}' not supported!")

			unit = "cyl"
			if self.blockAlignment:
				unit = "sec"
			start = start.replace(" ", "")
			end = end.replace(" ", "")

			if start.endswith(("m", "mb")):
				match = re.search(r"^(\d+)\D", start)
				if self.blockAlignment:
					start = int(
						round((int(match.group(1)) * 1024 * 1024) / self.bytesPerSector)
					)
				else:
					start = int(
						round(
							(int(match.group(1)) * 1024 * 1024) / self.bytesPerCylinder
						)
					)
			elif start.endswith(("g", "gb")):
				match = re.search(r"^(\d+)\D", start)
				if self.blockAlignment:
					start = int(
						round(
							(int(match.group(1)) * 1024 * 1024 * 1024)
							/ self.bytesPerSector
						)
					)
				else:
					start = int(
						round(
							(int(match.group(1)) * 1024 * 1024 * 1024)
							/ self.bytesPerCylinder
						)
					)
			elif start.lower().endswith("%"):
				match = re.search(r"^(\d+)\D", start)
				if self.blockAlignment:
					start = int(
						round((float(match.group(1)) / 100) * self.totalSectors)
					)
				else:
					start = int(
						round((float(match.group(1)) / 100) * self.totalCylinders)
					)
			elif start.lower().endswith("s"):
				match = re.search(r"^(\d+)\D", start)
				start = int(match.group(1))
				if not self.blockAlignment:
					start = int(
						round(
							(
								(float(start) * self.bytesPerSector)
								/ self.bytesPerCylinder
							)
						)
					)
			elif start.lower().endswith("c"):
				# Cylinder!
				start = int(start)
				if self.blockAlignment:
					start = int(
						round(
							(
								(float(start) * self.bytesPerCylinder)
								/ self.bytesPerSector
							)
						)
					)
			else:
				# Cylinder!
				start = int(start)
				if self.blockAlignment:
					start = int(
						round(
							(
								(float(start) * self.bytesPerCylinder)
								/ self.bytesPerSector
							)
						)
					)

			if end.endswith(("m", "mb")):
				match = re.search(r"^(\d+)\D", end)
				if self.blockAlignment:
					end = int(
						round((int(match.group(1)) * 1024 * 1024) / self.bytesPerSector)
					)
				else:
					end = int(
						round(
							(int(match.group(1)) * 1024 * 1024) / self.bytesPerCylinder
						)
					)
			elif end.endswith(("g", "gb")):
				match = re.search(r"^(\d+)\D", end)
				if self.blockAlignment:
					end = int(
						round(
							(int(match.group(1)) * 1024 * 1024 * 1024)
							/ self.bytesPerSector
						)
					)
				else:
					end = int(
						round(
							(int(match.group(1)) * 1024 * 1024 * 1024)
							/ self.bytesPerCylinder
						)
					)
			elif end.lower().endswith("%"):
				match = re.search(r"^(\d+)\D", end)
				if self.blockAlignment:
					end = int(round((float(match.group(1)) / 100) * self.totalSectors))
				else:
					end = int(
						round((float(match.group(1)) / 100) * self.totalCylinders)
					)
			elif end.lower().endswith("s"):
				match = re.search(r"^(\d+)\D", end)
				end = int(match.group(1))
				if not self.blockAlignment:
					end = int(
						round(
							((float(end) * self.bytesPerSector) / self.bytesPerCylinder)
						)
					)
			elif end.lower().endswith("c"):
				# Cylinder!
				end = int(end)
				if self.blockAlignment:
					end = int(
						round(
							((float(end) * self.bytesPerCylinder) / self.bytesPerSector)
						)
					)
			else:
				# Cylinder!
				end = int(end)
				if self.blockAlignment:
					end = int(
						round(
							((float(end) * self.bytesPerCylinder) / self.bytesPerSector)
						)
					)

			if unit == "cyl":
				# Lowest possible cylinder is 0
				start = max(start, 0)
				if end >= self.totalCylinders:
					# Highest possible cylinder is total cylinders - 1
					end = self.totalCylinders - 1
			else:
				modulo = start % 2048
				if modulo:
					start = start + 2048 - modulo

				modulo = end % 2048
				end = end + 2048 - (end % 2048) - 1
				start = max(start, 2048)

				if end >= self.totalSectors:
					# Highest possible sectors is total sectors - 1
					end = self.totalSectors - 1

			# if no number given - count
			if not number:
				number = len(self.partitions) + 1

			for part in self.partitions:
				if unit == "sec":
					partitionStart = part["secStart"]
				else:
					partitionStart = part["cylStart"]
				if end <= partitionStart:
					if part["number"] - 1 <= number:
						# Insert before
						number = part["number"] - 1

			try:
				prev = self.getPartition(number - 1)
				if unit == "sec":
					if start <= prev["secEnd"]:
						# Partitions overlap
						start = prev["secEnd"] + 1
				else:
					if start <= prev["cylEnd"]:
						# Partitions overlap
						start = prev["cylEnd"] + 1
			except Exception:
				pass

			try:
				next = self.getPartition(number + 1)
				nextstart = next["cylStart"]
				if unit == "sec":
					nextstart = next["secStart"]

				if end >= nextstart:
					# Partitions overlap
					end = nextstart - 1
			except Exception:
				pass

			start = max(start, 2048)

			if unit == "sec":
				logger.info(
					"Creating partition on '%s': number: %s, type '%s', filesystem '%s', start: %s sec, end: %s sec.",
					self.device,
					number,
					type,
					fs,
					start,
					end,
				)

				if number < 1 or number > 4:
					raise ValueError(f"Cannot create partition {number}")

				self.partitions.append(
					{
						"number": number,
						"secStart": start,
						"secEnd": end,
						"secSize": end - start + 1,
						"start": start * self.bytesPerSector,
						"end": end * self.bytesPerSector,
						"size": (end - start + 1) * self.bytesPerSector,
						"type": partId,
						"fs": fs,
						"boot": boot,
						"lba": lba,
					}
				)
			else:
				logger.info(
					"Creating partition on '%s': number: %s, type '%s', filesystem '%s', start: %s cyl, end: %s cyl.",
					self.device,
					number,
					type,
					fs,
					start,
					end,
				)

				if number < 1 or number > 4:
					raise ValueError(f"Cannot create partition {number}")

				self.partitions.append(
					{
						"number": number,
						"cylStart": start,
						"cylEnd": end,
						"cylSize": end - start + 1,
						"start": start * self.bytesPerCylinder,
						"end": end * self.bytesPerCylinder,
						"size": (end - start + 1) * self.bytesPerCylinder,
						"type": partId,
						"fs": fs,
						"boot": boot,
						"lba": lba,
					}
				)

			self.writePartitionTable()
			self.readPartitionTable()
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_createPartition(
					self, start, end, fs, type, boot, lba, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_createPartition(self, start, end, fs, type, boot, lba)

	def deletePartition(self, partition):
		for hook in hooks:
			partition = hook.pre_Harddisk_deletePartition(self, partition)
		try:
			partition = forceInt(partition)

			logger.info("Deleting partition '%s' on '%s'", partition, self.device)

			partitions = []
			exists = False
			deleteDev = None
			for part in self.partitions:
				if part.get("number") == partition:
					exists = True
					deleteDev = part.get("device")
				else:
					partitions.append(part)

			if not exists:
				logger.warning("Cannot delete non existing partition '%s'.", partition)
				return

			self.partitions = partitions

			self.writePartitionTable()
			self.readPartitionTable()
			if deleteDev:
				logger.debug("Waiting for device '%s' to disappear", deleteDev)
				timeout = 5
				while timeout > 0:
					if not os.path.exists(deleteDev):
						break
					time.sleep(1)
					timeout -= 1
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_deletePartition(self, partition, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_deletePartition(self, partition)

	def mountPartition(self, partition, mountpoint, **options):
		for hook in hooks:
			(partition, mountpoint, options) = hook.pre_Harddisk_mountPartition(
				self, partition, mountpoint, **options
			)
		try:
			partition = forceInt(partition)
			mountpoint = forceFilename(mountpoint)
			mount(self.getPartition(partition)["device"], mountpoint, **options)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_mountPartition(
					self, partition, mountpoint, err, **options
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_mountPartition(self, partition, mountpoint, **options)

	def umountPartition(self, partition):
		for hook in hooks:
			partition = hook.pre_Harddisk_umountPartition(self, partition)
		try:
			partition = forceInt(partition)
			umount(self.getPartition(partition)["device"])
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_umountPartition(self, partition, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_umountPartition(self, partition)

	def createFilesystem(self, partition, fs=None):
		for hook in hooks:
			(partition, fs) = hook.pre_Harddisk_createFilesystem(self, partition, fs)

		try:
			partition = forceInt(partition)
			if not fs:
				fs = self.getPartition(partition)["fs"]
			fs = forceUnicodeLower(fs)

			if fs not in (
				"fat32",
				"ntfs",
				"linux-swap",
				"ext2",
				"ext3",
				"ext4",
				"reiserfs",
				"reiser4",
				"xfs",
			):
				raise ValueError(f"Creation of filesystem '{fs}' not supported!")

			logger.info(
				"Creating filesystem '%s' on '%s'.",
				fs,
				self.getPartition(partition)["device"],
			)

			retries = 1
			while retries <= 6:
				if os.path.exists(self.getPartition(partition)["device"]):
					break
				retries += 1
				if retries == 3:
					logger.debug("Forcing kernel to reread the partitiontable again")
					self._forceReReadPartionTable()
				time.sleep(2)

			if fs == "fat32":
				cmd = f"mkfs.vfat -F 32 {self.getPartition(partition)['device']}"
			elif fs == "linux-swap":
				cmd = f"mkswap {self.getPartition(partition)['device']}"
			else:
				options = ""
				if fs in ("ext2", "ext3", "ext4", "ntfs"):
					options = "-F"
					if fs == "ntfs":
						# quick format
						options += " -Q"
				elif fs in ("xfs", "reiserfs", "reiser4"):
					options = "-f"
				cmd = f"mkfs.{fs} {options} {self.getPartition(partition)['device']}"

			sp_env = {}
			if self.ldPreload:
				sp_env["LD_PRELOAD"] = self.ldPreload
			execute(cmd, env=sp_env)
			self.readPartitionTable()
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_createFilesystem(self, partition, fs, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_createFilesystem(self, partition, fs)

	def resizeFilesystem(self, partition, size=0, fs=None):
		for hook in hooks:
			(partition, size, fs) = hook.pre_Harddisk_resizeFilesystem(
				self, partition, size, fs
			)
		try:
			partition = forceInt(partition)
			size = forceInt(size)
			bytesPerSector = forceInt(self.bytesPerSector)
			if not fs:
				fs = self.getPartition(partition)["fs"]
			fs = forceUnicodeLower(fs)
			if fs not in ("ntfs",):
				raise ValueError(f"Resizing of filesystem '{fs}' not supported!")

			if size <= 0:
				if bytesPerSector > 0 and self.blockAlignment:
					size = self.getPartition(partition)["secSize"] * bytesPerSector
				else:
					size = self.getPartition(partition)["size"] - 10 * 1024 * 1024

			if size <= 0:
				raise ValueError(
					f"New filesystem size of {(float(size) / (1024 * 1024)):.2f} MB is not possible!"
				)

			if fs.lower() == "ntfs":
				cmd = f"echo 'y' | {which('ntfsresize')} --force --size {size} {self.getPartition(partition)['device']}"
				sp_env = {}
				if self.ldPreload:
					sp_env["LD_PRELOAD"] = self.ldPreload
				execute(cmd, env=sp_env)
		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_resizeFilesystem(self, partition, size, fs, err)
			raise

		for hook in hooks:
			hook.post_Harddisk_resizeFilesystem(self, partition, size, fs)

	def saveImage(self, partition, imageFile, progressSubject=None):
		for hook in hooks:
			(partition, imageFile, progressSubject) = hook.pre_Harddisk_saveImage(
				self, partition, imageFile, progressSubject
			)

		saveImageResult = {"TotalTime": "n/a", "AveRate": "n/a", "AveUnit": "n/a"}

		try:
			partition = forceInt(partition)
			imageFile = forceUnicode(imageFile)

			part = self.getPartition(partition)
			if not part:
				raise ValueError(f"Partition {partition} does not exist")

			pipe = ""
			if imageFile.startswith("|"):
				pipe = imageFile
				imageFile = "-"

			logger.info(
				"Saving partition '%s' to partclone image '%s'",
				part["device"],
				imageFile,
			)

			# "-f" will write images of "dirty" volumes too
			# Better run chkdsk under windows before saving image!
			cmd = (
				f"{which('partclone.' + part['fs'])} --rescue --clone --force "
				f"--source {part['device']} --overwrite {imageFile} {pipe}"
			)

			if progressSubject:
				progressSubject.setEnd(100)

			sp_env = {}
			if self.ldPreload:
				sp_env["LD_PRELOAD"] = self.ldPreload
			handle = execute(cmd, getHandle=True, env=sp_env)
			done = False

			timeout = 0
			buf = [""]
			lastMsg = ""
			started = False
			while not done:
				inp = handle.read(128)

				if inp:
					inp = inp.decode("latin-1")
					timeout = 0

					dat = inp.splitlines()
					if inp.endswith(("\n", "\r")):
						dat.append("")

					buf = [buf[-1] + dat[0]] + dat[1:]

					for currentBuffer in islice(buf, len(buf) - 1):
						try:
							logger.debug(" -->>> %s", currentBuffer)
						except Exception:
							pass

						if "Partclone fail" in currentBuffer:
							raise RuntimeError("Failed: %s" % "\n".join(buf))
						if "Partclone successfully" in currentBuffer:
							done = True
						if "Total Time" in currentBuffer:
							match = re.search(
								r"Total\sTime:\s(\d+:\d+:\d+),\sAve.\sRate:\s*(\d*.\d*)([GgMm]B/min)",
								currentBuffer,
							)
							if match:
								rate = match.group(2)
								unit = match.group(3)
								if unit.startswith(("G", "g")):
									rate = float(rate) * 1024
									unit = "MB/min"
								saveImageResult = {
									"TotalTime": match.group(1),
									"AveRate": str(rate),
									"AveUnit": unit,
								}

						if not started:
							if "Calculating bitmap" in currentBuffer:
								logger.info("Save image: Scanning filesystem")
								if progressSubject:
									progressSubject.setMessage("Scanning filesystem")
							elif (
								currentBuffer.count(":") == 1
								and "http:" not in currentBuffer
							):
								(key, val) = currentBuffer.split(":")
								key = key.strip()
								val = val.strip()
								logger.info("Save image: %s: %s", key, val)
								if progressSubject:
									progressSubject.setMessage(f"{key}:{val}")
								if "used" in key.lower():
									if progressSubject:
										progressSubject.setMessage("Creating image")
									started = True
									continue
						else:
							match = re.search(r"Completed:\s*([\d\.]+)%", currentBuffer)
							if match:
								percent = int(round(float(match.group(1))))
								if (
									progressSubject
									and percent != progressSubject.getState()
								):
									logger.debug(" -->>> %s", currentBuffer)
									progressSubject.setState(percent)

					lastMsg = buf[-2]
					buf[:-1] = []
				elif timeout >= 100:
					raise RuntimeError(f"Failed: {lastMsg}")
				else:
					timeout += 1
					continue

			time.sleep(3)
			if handle:
				handle.close()

		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_saveImage(
					self, partition, imageFile, progressSubject, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_saveImage(self, partition, imageFile, progressSubject)

		return saveImageResult

	def restoreImage(self, partition, imageFile, progressSubject=None):
		for hook in hooks:
			(partition, imageFile, progressSubject) = hook.pre_Harddisk_restoreImage(
				self, partition, imageFile, progressSubject
			)

		try:
			partition = forceInt(partition)
			imageFile = forceUnicode(imageFile)

			imageType = None
			fs = None

			pipe = ""
			if imageFile.endswith("|"):
				pipe = imageFile
				imageFile = "-"

			head = ""
			if pipe:
				with subprocess.Popen(
					pipe[:-1] + " 2>/dev/null",
					shell=True,
					stdin=subprocess.PIPE,
					stdout=subprocess.PIPE,
					stderr=None,
				) as proc:
					pid = proc.pid

					head = proc.stdout.read(128)
					logger.debug(
						"Read 128 Bytes from pipe '%s': %s",
						pipe,
						head.decode("ascii", "replace"),
					)

					proc.stdout.close()
					proc.stdin.close()

					while proc.poll() is None:
						pids = os.listdir("/proc")
						for pid_ in pids:
							if not os.path.exists(
								os.path.join("/proc", pid_, "status")
							):
								continue
							with open(
								os.path.join("/proc", pid_, "status"), encoding="utf-8"
							) as file:
								for line in file:
									if line.startswith("PPid:"):
										ppid = line.split()[1].strip()
										if ppid == str(pid):
											logger.info("Killing process %s", pid_)
											os.kill(int(pid_), SIGKILL)

						logger.info("Killing process %s", pid)
						os.kill(pid, SIGKILL)
						time.sleep(1)
			else:
				with open(imageFile, "rb") as image:
					head = image.read(128)
					logger.debug(
						"Read 128 Bytes from file '%s': %s",
						imageFile,
						head.decode("ascii", "replace"),
					)

			if "ntfsclone-image" in head:
				logger.notice("Image type is ntfsclone")
				imageType = "ntfsclone"
			elif "partclone-image" in head:
				logger.notice("Image type is partclone")
				imageType = "partclone"

			if imageType not in ("ntfsclone", "partclone"):
				raise ValueError("Unknown image type.")

			sp_env = {}
			if self.ldPreload:
				sp_env["LD_PRELOAD"] = self.ldPreload

			if imageType == "partclone":
				logger.info(
					"Restoring partclone image '%s' to '%s'",
					imageFile,
					self.getPartition(partition)["device"],
				)

				cmd = (
					f"{pipe} {which('partclone.restore')} --source {imageFile} "
					f"--overwrite {self.getPartition(partition)['device']}"
				)

				if progressSubject:
					progressSubject.setEnd(100)
					progressSubject.setMessage("Scanning image")

				handle = execute(cmd, getHandle=True, env=sp_env)
				done = False

				timeout = 0
				buf = [""]
				lastMsg = ""
				started = False
				while not done:
					inp = handle.read(128)

					if inp:
						inp = inp.decode("latin-1")
						timeout = 0

						dat = inp.splitlines()
						if inp.endswith(("\n", "\r")):
							dat.append("")

						buf = [buf[-1] + dat[0]] + dat[1:]

						for currentBuffer in islice(buf, len(buf) - 1):
							try:
								logger.debug(" -->>> %s", currentBuffer)
							except Exception:
								pass

							if "Partclone fail" in currentBuffer:
								raise RuntimeError("Failed: %s" % "\n".join(buf))
							if "Partclone successfully" in currentBuffer:
								done = True
							if not started:
								if (
									currentBuffer.count(":") == 1
									and "http:" in currentBuffer
								):
									(key, val) = currentBuffer.split(":")
									key = key.strip()
									val = val.strip()
									logger.info("Save image: %s: %s", key, val)
									if progressSubject:
										progressSubject.setMessage(f"{key}: {val}")
									if "file system" in key.lower():
										fs = val.lower()
									elif "used" in key.lower():
										if progressSubject:
											progressSubject.setMessage(
												"Restoring image"
											)
										started = True
										continue
							else:
								match = re.search(
									r"Completed:\s*([\d\.]+)%", currentBuffer
								)
								if match:
									percent = int(round(float(match.group(1))))
									if (
										progressSubject
										and percent != progressSubject.getState()
									):
										logger.debug(" -->>> %s", currentBuffer)
										progressSubject.setState(percent)

						lastMsg = buf[-2]
						buf[:-1] = []

					elif timeout >= 100:
						if progressSubject:
							progressSubject.setMessage(f"Failed: {lastMsg}")
						raise RuntimeError(f"Failed: {lastMsg}")
					else:
						timeout += 1
						continue

				time.sleep(3)
				if handle:
					handle.close()
			else:
				fs = "ntfs"
				logger.info(
					"Restoring ntfsclone-image '%s' to '%s'",
					imageFile,
					self.getPartition(partition)["device"],
				)

				cmd = (
					f"{pipe} {which('ntfsclone')} --restore-image "
					f"--overwrite {self.getPartition(partition)['device']} {imageFile}"
				)

				if progressSubject:
					progressSubject.setEnd(100)
					progressSubject.setMessage("Restoring image")

				handle = execute(cmd, getHandle=True, env=sp_env)
				done = False

				timeout = 0
				buf = [""]
				lastMsg = ""
				while not done:
					inp = handle.read(128)

					if inp:
						inp = inp.decode("latin-1")
						timeout = 0

						dat = inp.splitlines()
						if inp.endswith(("\n", "\r")):
							dat.append("")

						buf = [buf[-1] + dat[0]] + dat[1:]

						for currentBuffer in islice(buf, len(buf) - 1):
							if "Syncing" in currentBuffer:
								logger.info("Restore image: Syncing")
								if progressSubject:
									progressSubject.setMessage("Syncing")
								done = True
							match = re.search(
								r"\s(\d+)[\.\,]\d\d\spercent", currentBuffer
							)
							if match:
								percent = int(match.group(1))
								if (
									progressSubject
									and percent != progressSubject.getState()
								):
									logger.debug(" -->>> %s", currentBuffer)
									progressSubject.setState(percent)
							else:
								logger.debug(" -->>> %s", currentBuffer)

						lastMsg = buf[-2]
						buf[:-1] = []
					elif timeout >= 100:
						if progressSubject:
							progressSubject.setMessage(f"Failed: {lastMsg}")
						raise RuntimeError(f"Failed: {lastMsg}")
					else:
						timeout += 1
						continue

				time.sleep(3)
				if handle:
					handle.close()

			if fs == "ntfs":
				self.setNTFSPartitionStartSector(partition)
				if progressSubject:
					progressSubject.setMessage("Resizing filesystem to partition size")
				self.resizeFilesystem(partition, fs="ntfs")

		except Exception as err:
			for hook in hooks:
				hook.error_Harddisk_restoreImage(
					self, partition, imageFile, progressSubject, err
				)
			raise

		for hook in hooks:
			hook.post_Harddisk_restoreImage(self, partition, imageFile, progressSubject)


def isCentOS():
	"""
	Returns `True` if this is running on CentOS.
	Returns `False` if otherwise.
	"""
	return (
		_checkForDistribution("CentOS")
		or _checkForDistribution("Rocky Linux")
		or _checkForDistribution("AlmaLinux")
	)


def isDebian():
	"""
	Returns `True` if this is running on Debian.
	Returns `False` if otherwise.
	"""
	return _checkForDistribution("Debian")


def isOpenSUSE():
	"""
	Returns `True` if this is running on openSUSE.
	Returns `False` if otherwise.
	"""
	if os.path.exists("/etc/os-release"):
		with open("/etc/os-release", "r", encoding="utf-8") as release:
			for line in release:
				if "opensuse" in line.lower():
					return True

	return False


def isRHEL():
	"""
	Returns `True` if this is running on Red Hat Enterprise Linux.
	Returns `False` if otherwise.
	"""
	return _checkForDistribution("Red Hat Enterprise Linux")


def isSLES():
	"""
	Returns `True` if this is running on Suse Linux Enterprise Server.
	Returns `False` if otherwise.
	"""
	if os.path.exists("/etc/os-release"):
		with open("/etc/os-release", "r", encoding="utf-8") as release:
			for line in release:
				if "suse linux enterprise server" in line.lower():
					return True

	return False


def isUbuntu():
	"""
	Returns `True` if this is running on Ubuntu.
	Returns `False` if otherwise.
	"""
	return _checkForDistribution("Ubuntu") or _checkForDistribution("Zorin OS")


def isUCS():
	"""
	Returns `True` if this is running on Univention Corporate Server.
	Returns `False` if otherwise.
	"""
	return (
		_checkForDistribution("Univention")
		or "univention" in Distribution().distributor.lower()
	)


def _checkForDistribution(name):
	try:
		sysinfo = SysInfo()
		return name.lower() in sysinfo.distribution.lower()
	except Exception as error:
		logger.debug("Failed to check for Distribution: %s", error)
		return False


class Distribution:
	def __init__(self, distribution_information=None):
		if distribution_information is None:
			distribution_information = (
				distro_module.name(),
				distro_module.version(),
				distro_module.codename(),
			)

		logger.debug("distribution information: %s", distribution_information)
		self.distribution, self._version, self.id = distribution_information
		self.distribution = self.distribution.strip()

		self.hostname = platform.node()
		self.kernel = platform.release()
		self.detailedVersion = platform.version()
		self.arch = platform.machine()

		self.distributor = self._getDistributor()

	@property
	def version(self):
		if "errata" in self._version:
			version = self._version.strip('"').split("-")[0]
			return tuple([int(x) for x in version.split(".")])
		return tuple([int(x) for x in self._version.split(".")])

	@staticmethod
	@lru_cache(None)
	def _getDistributor():
		"""
		Get information about the distributor.

		Returns an empty string if no information can be obtained.
		"""
		try:
			distributor = distro_module.distro_release_attr("distributor_id")
			if not distributor:
				raise ValueError("No distributor information found.")
		except (AttributeError, ValueError):
			try:
				lsbReleaseOutput = execute("lsb_release -i")
				distributor = lsbReleaseOutput[0].split(":")[1].strip()
			except Exception:
				distributor = ""

		return distributor

	def __str__(self):
		return f"{self.distribution} {self._version} {self.id}"

	def __repr__(self):
		return f"Distribution(distribution_information=('{self.distribution}', '{self._version}', '{self.id}'"


class SysInfo:
	def __init__(self):
		self.dist = Distribution()

	@property
	def hostname(self):
		return forceHostname(socket.gethostname().split(".")[0])

	@property
	def fqdn(self):
		return forceUnicodeLower(socket.getfqdn())

	@property
	def domainname(self):
		return forceDomain(".".join(self.fqdn.split(".")[1:]))

	@property
	def distribution(self):
		return self.dist.distribution

	@property
	def sysVersion(self):
		return self.dist.version

	@property
	def distributionId(self):
		return self.dist.id

	@property
	def ipAddress(self):
		return forceIpAddress(socket.gethostbyname(self.hostname))

	@property
	def hardwareAddress(self):
		for device in getEthernetDevices():
			devconf = getNetworkDeviceConfig(device)
			if devconf["ipAddress"] and not devconf["ipAddress"].startswith(
				("127", "169")
			):
				if self.ipAddress == devconf["ipAddress"]:
					return forceHardwareAddress(devconf["hardwareAddress"])
		return None

	@property
	def netmask(self):
		for device in getEthernetDevices():
			devconf = getNetworkDeviceConfig(device)
			if devconf["ipAddress"] and not devconf["ipAddress"].startswith(
				("127", "169")
			):
				if self.ipAddress == devconf["ipAddress"]:
					return forceNetmask(devconf["netmask"])
		return "255.255.255.0"

	@property
	def broadcast(self):
		return ".".join(
			"%d"
			% (
				int(self.ipAddress.split(".")[i])
				| int(self.netmask.split(".")[i]) ^ 255
			)
			for i in range(len(self.ipAddress.split(".")))
		)

	@property
	def subnet(self):
		return ".".join(
			"%d" % (int(self.ipAddress.split(".")[i]) & int(self.netmask.split(".")[i]))
			for i in range(len(self.ipAddress.split(".")))
		)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                       HARDWARE INVENTORY                                          -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def auditHardware(config, hostId, progressSubject=None):
	for hook in hooks:
		(config, hostId, progressSubject) = hook.pre_auditHardware(
			config, hostId, progressSubject
		)

	try:
		hostId = forceHostId(hostId)

		AuditHardwareOnHost.setHardwareConfig(config)
		auditHardwareOnHosts = []

		info = hardwareInventory(config)
		info = hardwareExtendedInventory(config, info)
		for hardwareClass, devices in info.items():
			if hardwareClass == "SCANPROPERTIES":
				continue
			for device in devices:
				data = {"hardwareClass": hardwareClass}
				for attribute, value in device.items():
					data[str(attribute)] = value
				data["hostId"] = hostId
				auditHardwareOnHosts.append(AuditHardwareOnHost.fromHash(data))
	except Exception as err:
		for hook in hooks:
			hook.error_auditHardware(config, hostId, progressSubject, err)
		raise

	for hook in hooks:
		auditHardwareOnHosts = hook.post_auditHardware(
			config, hostId, auditHardwareOnHosts
		)

	return auditHardwareOnHosts


def hardwareExtendedInventory(config, opsiValues={}, progressSubject=None):
	if not config:
		logger.error("hardwareInventory: no config given")
		return {}

	for hwClass in config:
		if not hwClass.get("Class") or not hwClass["Class"].get("Opsi"):
			continue

		opsiName = hwClass["Class"]["Opsi"]

		logger.debug("Processing class '%s'", opsiName)

		valuesregex = re.compile(r"(.*)#(.*)#")
		for item in hwClass["Values"]:
			pythonline = item.get("Python")
			if not pythonline:
				continue
			condition = item.get("Condition")
			if condition:
				val = condition.split("=")[0]
				reg = condition.split("=")[1]
				if val and reg:
					conditionregex = re.compile(reg)
					conditionmatch = None

					logger.info("Condition found, try to check the Condition")
					value = None
					for currentValue in opsiValues[opsiName]:
						value = currentValue.get(val, "")
						if value:
							conditionmatch = re.search(conditionregex, value)
							break

					if not value:
						logger.warning(
							"The Value of your condition '%s' doesn't exists, please check your opsihwaudit.conf.",
							condition,
						)

					if not conditionmatch:
						continue
				match = re.search(valuesregex, pythonline)
				if match:
					result = None
					srcfields = match.group(2)
					fieldsdict = eval(srcfields)
					attr = ""
					for key, value in fieldsdict.items():
						for i in range(len(opsiValues.get(key, []))):
							attr = opsiValues.get(key)[i].get(value, "")
						if attr:
							break
					if attr:
						pythonline = pythonline.replace(f"#{srcfields}#", f"'{attr}'")
						result = eval(pythonline)

					if opsiName not in opsiValues:
						opsiValues[opsiName].append({})
					for i in range(len(opsiValues[opsiName])):
						opsiValues[opsiName][i][item["Opsi"]] = result

	return opsiValues


def hardwareInventory(config, progressSubject=None):
	import xml.dom.minidom

	if not config:
		logger.error("hardwareInventory: no config given")
		return {}

	opsiValues = {}

	def getAttribute(dom, tagname, attrname):
		nodelist = dom.getElementsByTagName(tagname)
		if nodelist:
			return nodelist[0].getAttribute(attrname).strip()
		return ""

	def getElementsByAttributeValue(
		dom, tagName, attributeName, attributeValue, onlyHighest=False
	):
		if onlyHighest:
			return [
				[
					element
					for element in dom.getElementsByTagName(tagName)
					if re.search(attributeValue, element.getAttribute(attributeName))
				][0]
			]

		return [
			element
			for element in dom.getElementsByTagName(tagName)
			if re.search(attributeValue, element.getAttribute(attributeName))
		]

	# Read output from lshw
	proc_env = get_subprocess_environment(add_lc_all_C=True, add_path_sbin=True)
	xmlOut = "\n".join(execute("lshw -xml", env=proc_env, captureStderr=False))
	xmlOut = re.sub(
		"[%c%c%c%c%c%c%c%c%c%c%c%c%c]"
		% (
			0x00,
			0x01,
			0x02,
			0x03,
			0x04,
			0x05,
			0x06,
			0x07,
			0x08,
			0xBD,
			0xBF,
			0xEF,
			0xDD,
		),
		".",
		xmlOut,
	)
	dom = xml.dom.minidom.parseString(xmlOut.encode("utf-8"))

	# Read output from lspci
	lspci = {}
	busId = None
	devRegex = re.compile(
		r"([\d.:a-f]+)\s+([\da-f]+):\s+([\da-f]+):([\da-f]+)\s*(\(rev ([^\)]+)\)|)"
	)
	subRegex = re.compile(r"\s*Subsystem:\s+([\da-f]+):([\da-f]+)\s*")
	proc_env = get_subprocess_environment(add_path_sbin=True)
	for line in execute("lspci -vn", captureStderr=False, env=proc_env):
		if not line.strip():
			continue
		match = re.search(devRegex, line)
		if match:
			busId = match.group(1)
			lspci[busId] = {
				"vendorId": forceHardwareVendorId(match.group(3)),
				"deviceId": forceHardwareDeviceId(match.group(4)),
				"subsystemVendorId": "",
				"subsystemDeviceId": "",
				"revision": match.group(6) or "",
			}
			continue
		match = re.search(subRegex, line)
		if match:
			lspci[busId]["subsystemVendorId"] = forceHardwareVendorId(match.group(1))
			lspci[busId]["subsystemDeviceId"] = forceHardwareDeviceId(match.group(2))
	logger.trace("Parsed lspci info:")
	logger.trace(objectToBeautifiedText(lspci))

	# Read hdaudio information from alsa
	hdaudio = {}
	if os.path.exists("/proc/asound"):
		for card in os.listdir("/proc/asound"):
			if not re.search(r"^card\d$", card):
				continue
			logger.debug("Found hdaudio card '%s'", card)
			for codec in os.listdir("/proc/asound/" + card):
				if not re.search(r"^codec#\d$", codec):
					continue
				if not os.path.isfile("/proc/asound/" + card + "/" + codec):
					continue
				with open(f"/proc/asound/{card}/{codec}", encoding="utf-8") as file:
					logger.debug("   Found hdaudio codec '%s'", codec)
					hdaudioId = card + codec
					hdaudio[hdaudioId] = {}
					for line in file:
						if line.startswith("Codec:"):
							hdaudio[hdaudioId]["codec"] = line.split(":", 1)[1].strip()
						elif line.startswith("Address:"):
							hdaudio[hdaudioId]["address"] = line.split(":", 1)[
								1
							].strip()
						elif line.startswith("Vendor Id:"):
							vid = line.split("x", 1)[1].strip()
							hdaudio[hdaudioId]["vendorId"] = forceHardwareVendorId(
								vid[0:4]
							)
							hdaudio[hdaudioId]["deviceId"] = forceHardwareDeviceId(
								vid[4:8]
							)
						elif line.startswith("Subsystem Id:"):
							sid = line.split("x", 1)[1].strip()
							hdaudio[hdaudioId]["subsystemVendorId"] = (
								forceHardwareVendorId(sid[0:4])
							)
							hdaudio[hdaudioId]["subsystemDeviceId"] = (
								forceHardwareDeviceId(sid[4:8])
							)
						elif line.startswith("Revision Id:"):
							hdaudio[hdaudioId]["revision"] = line.split("x", 1)[
								1
							].strip()
				logger.debug("      Codec info: '%s'", hdaudio[hdaudioId])

	# Read output from lsusb
	lsusb = {}
	busId = None
	devId = None
	indent = -1
	currentKey = None
	status = False

	devRegex = re.compile(
		r"^Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([\da-fA-F]{4}):([\da-fA-F]{4})\s*(.*)$"
	)
	descriptorRegex = re.compile(r"^(\s*)(.*)\s+Descriptor:\s*$")
	deviceStatusRegex = re.compile(r"^(\s*)Device\s+Status:\s+(\S+)\s*$")
	deviceQualifierRegex = re.compile(r"^(\s*)Device\s+Qualifier\s+.*:\s*$")
	keyRegex = re.compile(r"^(\s*)([^\:]+):\s*$")
	keyValueRegex = re.compile(r"^(\s*)(\S+)\s+(.*)$")

	try:
		proc_env = get_subprocess_environment(add_path_sbin=True)
		for line in execute("lsusb -v", captureStderr=False, env=proc_env):
			if not line.strip() or (line.find("** UNAVAILABLE **") != -1):
				continue
			# line = line.decode('ISO-8859-15', 'replace').encode('utf-8', 'replace')
			match = re.search(devRegex, line)
			if match:
				busId = str(match.group(1))
				devId = str(match.group(2))
				descriptor = None
				indent = -1
				currentKey = None
				status = False
				logger.debug("Device: %s:%s", busId, devId)
				# TODO: better key building.
				lsusb[busId + ":" + devId] = {
					"device": {},
					"configuration": {},
					"interface": {},
					"endpoint": [],
					"hid device": {},
					"hub": {},
					"qualifier": {},
					"status": {},
				}
				continue

			if status:
				lsusb[busId + ":" + devId]["status"].append(line.strip())
				continue

			match = re.search(deviceStatusRegex, line)
			if match:
				status = True
				lsusb[busId + ":" + devId]["status"] = [match.group(2)]
				continue

			match = re.search(deviceQualifierRegex, line)
			if match:
				descriptor = "qualifier"
				logger.debug("Qualifier")
				currentKey = None
				indent = -1
				continue

			match = re.search(descriptorRegex, line)
			if match:
				descriptor = match.group(2).strip().lower()
				logger.debug("Descriptor: %s", descriptor)
				if isinstance(lsusb[busId + ":" + devId][descriptor], list):
					lsusb[busId + ":" + devId][descriptor].append({})
				currentKey = None
				indent = -1
				continue

			if not descriptor:
				logger.error("No descriptor")
				continue

			if descriptor not in lsusb[busId + ":" + devId]:
				logger.error("Unknown descriptor '%s'", descriptor)
				continue

			(key, value) = ("", "")
			match = re.search(keyRegex, line)
			if match:
				key = match.group(2)
				indent = len(match.group(1))
			else:
				match = re.search(keyValueRegex, line)
				if match:
					if len(match.group(1)) > indent >= 0:
						key = currentKey
						value = match.group(0).strip()
					else:
						(key, value) = (match.group(2), match.group(3).strip())
						indent = len(match.group(1))

			logger.debug("key: '%s', value: '%s'", key, value)

			if not key or not value:
				continue

			currentKey = key
			if isinstance(lsusb[busId + ":" + devId][descriptor], list):
				if key not in lsusb[busId + ":" + devId][descriptor][-1]:
					lsusb[busId + ":" + devId][descriptor][-1][key] = []
				lsusb[busId + ":" + devId][descriptor][-1][key].append(value)
			else:
				if key not in lsusb[busId + ":" + devId][descriptor]:
					lsusb[busId + ":" + devId][descriptor][key] = []
				lsusb[busId + ":" + devId][descriptor][key].append(value)

		logger.trace("Parsed lsusb info:")
		logger.trace(objectToBeautifiedText(lsusb))
	except Exception as err:
		logger.error(err)

	# Read output from dmidecode
	dmidecode = {}
	dmiType = None
	header = True
	option = None
	optRegex = re.compile(r"(\s+)([^:]+):(.*)")
	proc_env = get_subprocess_environment(add_path_sbin=True)
	for line in execute("dmidecode", captureStderr=False, env=proc_env):
		try:
			if not line.strip():
				continue
			if line.startswith("Handle"):
				dmiType = None
				header = False
				option = None
				continue
			if header:
				continue
			if not dmiType:
				dmiType = line.strip()
				if dmiType.lower() == "end of table":
					break
				if dmiType not in dmidecode:
					dmidecode[dmiType] = []
				dmidecode[dmiType].append({})
			else:
				match = re.search(optRegex, line)
				if match:
					option = match.group(2).strip()
					value = match.group(3).strip()
					dmidecode[dmiType][-1][option] = removeUnit(value)
				elif option:
					if not isinstance(dmidecode[dmiType][-1][option], list):
						if dmidecode[dmiType][-1][option]:
							dmidecode[dmiType][-1][option] = [
								dmidecode[dmiType][-1][option]
							]
						else:
							dmidecode[dmiType][-1][option] = []
					dmidecode[dmiType][-1][option].append(removeUnit(line.strip()))
		except Exception as err:
			logger.error(
				"Error while parsing dmidecode output '%s': %s", line.strip(), err
			)
	logger.trace("Parsed dmidecode info:")
	logger.trace(objectToBeautifiedText(dmidecode))

	# Build hw info structure
	for hwClass in config:
		if (
			not hwClass.get("Class")
			or not hwClass["Class"].get("Opsi")
			or not hwClass["Class"].get("Linux")
		):
			continue

		opsiClass = hwClass["Class"]["Opsi"]
		linuxClasses = sorted(hwClass["Class"]["Linux"].split(";"), reverse=True)
		for linuxClass in linuxClasses:
			logger.debug("Processing class '%s' : '%s'", opsiClass, linuxClass)

			if linuxClass.startswith("[lshw]"):
				# Get matching xml nodes
				devices = []
				for hwclass in linuxClass[6:].split("|"):
					hwid = ""
					filter = None
					if ":" in hwclass:
						(hwclass, hwid) = hwclass.split(":", 1)
						if ":" in hwid:
							(hwid, filter) = hwid.split(":", 1)

					logger.debug(
						"Class is '%s', id is '%s', filter is: %s",
						hwClass,
						hwid,
						filter,
					)

					if hwclass == "system":
						# system nodes can appear nested... only working with root system here
						devs = getElementsByAttributeValue(
							dom, "node", "class", hwclass, onlyHighest=True
						)
					else:
						devs = getElementsByAttributeValue(
							dom, "node", "class", hwclass
						)

					for dev in devs:
						if dev.hasChildNodes():
							for child in dev.childNodes:
								if child.nodeName == "businfo":
									busInfo = child.firstChild.data.strip()
									if busInfo.startswith("pci@"):
										logger.debug(
											"Getting pci bus info for '%s'", busInfo
										)
										pciBusId = busInfo.split("@")[1]
										if pciBusId.startswith("0000:"):
											pciBusId = pciBusId[5:]
										pciInfo = lspci.get(pciBusId, {})
										for key, value in pciInfo.items():
											elem = dom.createElement(key)
											elem.childNodes.append(
												dom.createTextNode(value)
											)
											dev.childNodes.append(elem)
									break
					if hwid:
						filtered = []
						for dev in devs:
							if re.search(hwid, dev.getAttribute("id")):
								if not filter:
									filtered.append(dev)
								else:
									(attr, method) = filter.split(".", 1)
									if dev.getAttribute(attr):
										if eval(f"dev.getAttribute(attr).{method}"):
											filtered.append(dev)
									elif dev.hasChildNodes():
										for child in dev.childNodes:
											if (
												child.nodeName == attr
											) and child.hasChildNodes():
												if eval(
													f"child.firstChild.data.strip().{method}"
												):
													filtered.append(dev)
													break
											try:
												if (
													child.hasAttributes()
													and child.getAttribute(attr)
												):
													if eval(
														f"child.getAttribute(attr).{method}"
													):
														filtered.append(dev)
														break
											except Exception:
												pass
							# Also consider nodes with matching class
							if (
								re.search(hwid, dev.getAttribute("class"))
								and not filter
							):
								filtered.append(dev)
						devs = filtered

					logger.trace("Found matching devices: %s", devs)
					devices.extend(devs)

				# Process matching xml nodes
				for i, device in enumerate(devices):
					if opsiClass not in opsiValues:
						opsiValues[opsiClass] = []
					opsiValues[opsiClass].append({})

					if not hwClass.get("Values"):
						break

					for attribute in hwClass["Values"]:
						elements = [device]
						if not attribute.get("Opsi") or not attribute.get("Linux"):
							continue

						logger.trace(
							"Processing attribute '%s' : '%s'",
							attribute["Linux"],
							attribute["Opsi"],
						)
						for attr in attribute["Linux"].split("||"):
							attr = attr.strip()
							method = None
							data = None
							for part in attr.split("/"):
								if "." in part:
									(part, method) = part.split(".", 1)
								nextElements = []
								for element in elements:
									for child in element.childNodes:
										try:
											if child.nodeName == part:
												nextElements.append(child)
											elif (
												child.hasAttributes()
												and child.getAttribute("id").split(":")[
													0
												]
												== part
											):
												nextElements.append(child)
										except Exception:
											pass
									# Prefer matching child.id over matching child.class
									if not nextElements:
										for child in element.childNodes:
											try:
												if (
													child.hasAttributes()
													and child.getAttribute("class")
													== part
												):
													nextElements.append(child)
											except Exception:
												pass
								if not nextElements:
									logger.warning(
										"Attribute part '%s' not found", part
									)
									break
								elements = nextElements

							if not data:
								if not elements:
									opsiValues[opsiClass][i][attribute["Opsi"]] = ""
									logger.warning(
										"No data found for attribute '%s' : '%s'",
										attribute["Linux"],
										attribute["Opsi"],
									)
									continue

								for element in elements:
									if element.getAttribute(attr):
										data = element.getAttribute(attr).strip()
									elif element.getAttribute("value"):
										data = element.getAttribute("value").strip()
									elif element.hasChildNodes():
										data = element.firstChild.data.strip()
							if method and data:
								try:
									logger.debug("Eval: %s.%s", data, method)
									data = eval(f"data.{method}")
								except Exception as err:
									logger.error(
										"Failed to excecute '%s.%s': %s",
										data,
										method,
										err,
									)
							logger.trace("Data: %s", data)
							opsiValues[opsiClass][i][attribute["Opsi"]] = data
							if data:
								break

			# Get hw info from dmidecode
			elif linuxClass.startswith("[dmidecode]"):
				if not opsiValues.get(opsiClass):
					opsiValues[opsiClass] = []
				for hwclass in linuxClass[11:].split("|"):
					(filterAttr, filterExp) = (None, None)
					if ":" in hwclass:
						(hwclass, filter) = hwclass.split(":", 1)
						if "." in filter:
							(filterAttr, filterExp) = filter.split(".", 1)

					for dev in dmidecode.get(hwclass, []):
						if (
							filterAttr
							and dev.get(filterAttr)
							and not eval(f"str(dev.get(filterAttr)).{filterExp}")
						):
							continue
						device = {}
						for attribute in hwClass["Values"]:
							if not attribute.get("Linux"):
								continue

							for aname in attribute["Linux"].split("||"):
								aname = aname.strip()
								method = None
								if "." in aname:
									(aname, method) = aname.split(".", 1)
								if method:
									try:
										logger.debug(
											"Eval: %s.%s", dev.get(aname, ""), method
										)
										device[attribute["Opsi"]] = eval(
											f"dev.get(aname, '').{method}"
										)
									except Exception as err:
										if not device.get(attribute["Opsi"]):
											device[attribute["Opsi"]] = ""
										logger.error(
											"Failed to excecute '%s.%s': %s",
											dev.get(aname, ""),
											method,
											err,
										)
								else:
									if not device.get(attribute["Opsi"]):
										device[attribute["Opsi"]] = dev.get(aname)
								# if len(devices) == 1 and len(opsiValues[hwClass["Class"]["Opsi"]]) == 1:
								# 	opsiValues[hwClass["Class"]["Opsi"]][0][attribute["Opsi"]] = dev.get(aname)
								if device[attribute["Opsi"]]:
									break

						if len(devices) == 1 and opsiValues[hwClass["Class"]["Opsi"]]:
							for attr in device.keys():
								if device[attr]:
									opsiValues[hwClass["Class"]["Opsi"]][0][attr] = (
										device[attr]
									)
						else:
							opsiValues[hwClass["Class"]["Opsi"]].append(device)

			# Get hw info from alsa hdaudio info
			elif linuxClass.startswith("[hdaudio]"):
				opsiValues[opsiClass] = []
				for hdaudioId, dev in hdaudio.items():
					device = {}
					for attribute in hwClass["Values"]:
						if not attribute.get("Linux") or attribute["Linux"] not in dev:
							continue

						try:
							device[attribute["Opsi"]] = dev[attribute["Linux"]]
						except Exception as err:
							logger.warning(err)
							device[attribute["Opsi"]] = ""
					opsiValues[opsiClass].append(device)

			# Get hw info from lsusb
			elif linuxClass.startswith("[lsusb]"):
				opsiValues[opsiClass] = []
				for busId, dev in lsusb.items():
					device = {}
					for attribute in hwClass["Values"]:
						if not attribute.get("Linux"):
							continue

						try:
							value = pycopy.deepcopy(dev)
							for key in attribute["Linux"].split("/"):
								method = None
								if "." in key:
									(key, method) = key.split(".", 1)
								if not isinstance(value, dict) or key not in value:
									logger.error("Key '%s' not found", key)
									value = ""
									break
								value = value[key]
								if isinstance(value, list):
									value = ", ".join(value)
								if method:
									value = eval(f"value.{method}")

							device[attribute["Opsi"]] = value
						except Exception as err:
							logger.warning(err)
							device[attribute["Opsi"]] = ""
					opsiValues[opsiClass].append(device)

	# rm duplicates from opsiValues
	for hwClass in config:
		opsiClass = hwClass["Class"]["Opsi"]
		if opsiValues.get(opsiClass):
			opsiValues[opsiClass] = [
				dict(value_tuple)
				for value_tuple in {
					tuple(value_dict.items()) for value_dict in opsiValues[opsiClass]
				}
			]

	opsiValues["SCANPROPERTIES"] = [{"scantime": time.strftime("%Y-%m-%d %H:%M:%S")}]
	logger.debug("Result of hardware inventory: %s", objectToBeautifiedText(opsiValues))
	return opsiValues


def daemonize():
	# Fork to allow the shell to return and to call setsid
	try:
		pid = os.fork()
		if pid > 0:
			# Parent exits
			sys.exit(0)
	except OSError as err:
		raise RuntimeError(f"First fork failed: {err}") from err

	# Do not hinder umounts
	os.chdir("/")
	# Create a new session
	os.setsid()

	# Fork a second time to not remain session leader
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except OSError as err:
		raise RuntimeError(f"Second fork failed: {err}") from err

	logging_config(stderr_level=LOG_NONE)

	# Close standard output and standard error.
	os.close(0)
	os.close(1)
	os.close(2)

	# Open standard input (0)
	if hasattr(os, "devnull"):
		os.open(os.devnull, os.O_RDWR)
	else:
		os.open("/dev/null", os.O_RDWR)

	# Duplicate standard input to standard output and standard error.
	os.dup2(0, 1)
	os.dup2(0, 2)
	sys.stdout = None
	sys.stderr = None


def locateDHCPDConfig(default=None):
	locations = (
		"/etc/dhcpd.conf",  # suse / redhat / centos
		"/etc/dhcp/dhcpd.conf",  # newer debian / ubuntu
		"/etc/dhcp3/dhcpd.conf",  # older debian / ubuntu
	)

	for filename in locations:
		if os.path.exists(filename):
			return filename

	if default is not None:
		return default

	raise RuntimeError("Could not locate dhcpd.conf.")


def locateDHCPDInit(default=None):
	"""
	Returns the init command for the DHCPD.

	It will try to get the init script from ``/etc/init.d``.
	If no init commands are found and `default` is given it will return
	the	default.
	If no default is given it will throw an :py:exc:`RuntimeError`.

	:param default: If no init script is found fall back to this \
instead of throwing an error.
	:rtype: str
	"""
	locations = (
		"/etc/init.d/dhcpd",  # suse / redhat / centos
		"/etc/init.d/isc-dhcp-server",  # newer debian / ubuntu
		"/etc/init.d/dhcp3-server",  # older debian / ubuntu
	)

	for filename in locations:
		if os.path.exists(filename):
			return filename

	if default is not None:
		return default

	raise RuntimeError("Could not locate dhcpd init file.")


def getDHCPDRestartCommand(default=None):
	"""
	Returns a command that can be used to restart the used DHCPD.

	The command will include the full path to tools used, i.e. service.

	If no command can be automatically determined and `default` is given
	this will be returned. If `default` is not given an ``RuntimeError``
	will be risen.
	"""
	serviceName = getDHCPServiceName()
	if serviceName:
		try:
			return f"{which('service')} {serviceName} restart"
		except Exception as err:
			logger.debug("Ooops, getting the path to service failed: %s", err)

	locations = (
		"/etc/init.d/dhcpd",  # suse / redhat / centos
		"/etc/init.d/isc-dhcp-server",  # newer debian / ubuntu
		"/etc/init.d/dhcp3-server",  # older debian / ubuntu
	)

	for filename in locations:
		if os.path.exists(filename):
			return f"{filename} restart"

	if default is not None:
		logger.debug(
			"Could not find dhcpd restart command but default is given. Making use of default: %s",
			default,
		)
		return default

	raise RuntimeError("Could not find DHCPD restart command.")


def getDHCPServiceName():
	"""
	Tries to read the name of the used dhcpd.
	Returns `None` if no known service was detected.
	"""
	global _DHCP_SERVICE_NAME
	if _DHCP_SERVICE_NAME is not None:
		return _DHCP_SERVICE_NAME

	knownServices = ("dhcpd", "univention-dhcp", "isc-dhcp-server", "dhcp3-server")

	try:
		for servicename in getServiceNames():
			if servicename in knownServices:
				_DHCP_SERVICE_NAME = servicename
				return servicename
	except Exception:
		pass
	return None


def getSambaServiceName(default=None, staticFallback=True):
	"""
	Get the name for the samba service.

	:param default: If not value was detected use this as default.
	:type default: str
	:param staticFallback: If this is ``True`` it will use a static \
lookup to determine what value needs to be returned in case no \
service name was detected by the automatic approach.
	:type staticFallback: bool
	"""
	global _SAMBA_SERVICE_NAME
	if _SAMBA_SERVICE_NAME is not None:
		return _SAMBA_SERVICE_NAME

	def getFixServiceName():
		distroName = distro.distribution.strip().lower()
		if distroName == "debian":
			if distro.version[0] == 6:
				return "samba"
			return "smbd"
		if distroName == "ubuntu":
			return "smbd"
		if distroName in ("opensuse", "centos", "red hat enterprise linux server"):
			return "smb"
		return None

	distro = Distribution()
	if distro.distribution.strip() == "SUSE Linux Enterprise Server":
		name = "smb"
		_SAMBA_SERVICE_NAME = name
		return name

	possibleNames = ("samba", "smb", "smbd")

	for servicename in getServiceNames():
		if servicename in possibleNames:
			_SAMBA_SERVICE_NAME = servicename
			return servicename

	if staticFallback:
		servicename = getFixServiceName()
		if servicename is not None:
			return servicename

	if default is not None:
		return default

	raise RuntimeError("Could not get samba service name.")


def getServiceNames(_serviceStatusOutput=None):
	"""
	Get the names of services on the system.

	This script tries to pull the information from ``systemctl``.

	:param _serviceStatusOutput: The output of `service --status-all`.\
Used for testing.
	:type _serviceStatusOutput: [str, ]
	:rtype: set

	.. versionadded:: 4.0.5.11

	.. versionchanged:: 4.1.1.6
		Only supporting systemd now.
	"""
	if not _serviceStatusOutput:
		_serviceStatusOutput = execute(f"{which('systemctl')} list-unit-files")

	pattern = re.compile(r"(?P<servicename>([\w-]|@)+)\.service")
	services = set()

	for line in _serviceStatusOutput:
		match = pattern.search(line.strip())
		if match:
			services.add(match.group("servicename").strip())

	logger.debug("Found the following services: %s", services)
	return services


def getActiveConsoleSessionId():
	"""
	Get the currently used console session id.

	.. warning::

		This is currently only faked to have the function available for
		the opsi-linux-client-agent!

	"""
	return getActiveSessionId()


def getActiveSessionIds(protocol=None, states=["active", "disconnected"]):
	"""
	Getting the IDs of the currently active sessions.

	.. versionadded:: 4.0.5


	:param data: Prefetched data to read information from.
	:type data: [str, ]
	:rtype: [int, ]
	"""
	return []


def getActiveSessionId():
	"""
	Returns the currently active session ID.

	.. versionadded:: 4.0.5
	:rtype: int

	"""
	sessions = getActiveSessionIds()
	if sessions:
		return sessions[0]
	return None


def getSessionInformation(sessionId):
	return {"SessionId": sessionId}


def getActiveSessionInformation():
	info = []
	for sessionId in getActiveSessionIds():
		info.append(getSessionInformation(sessionId))
	return info


def grant_session_access(username: str, session_id: str):
	return opsicommon_get_subprocess_environment()


def runCommandInSession(
	command,
	sessionId=None,
	desktop=None,
	duplicateFrom=None,
	waitForProcessEnding=True,
	timeoutSeconds=0,
	noWindow=False,
	shell=True,
):
	"""
	Run an command.

	The arguments `sessionId`, `desktop` and `duplicateFrom` currently
	do not have any effect and are only provided to have a method
	signature matching the one from the corresponding Windows module.

	.. versionadded:: 4.0.5.2


	:param waitForProcessEnding: If this is `False` the command will be \
started and we will not wait for it to finish.
	:type waitForProcessEnding: bool
	:param timeoutSeconds: If this is set we will wait this many seconds \
until the execution of the process is terminated.
	:rtype: (subprocess.Popen, None, int, None) if \
`waitForProcessEnding` is False, otherwise (None, None, None, None)
	"""
	sleepDuration = 0.1

	if not isinstance(command, list):
		command = forceUnicode(command)
	waitForProcessEnding = forceBool(waitForProcessEnding)
	timeoutSeconds = forceInt(timeoutSeconds)

	logger.notice("Executing: '%s'", command)

	sp_env = opsicommon_get_subprocess_environment()
	if sessionId is not None:
		try:
			sp_env = grant_session_access(getpass.getuser(), sessionId)
		except Exception as err:
			logger.error(
				"Failed to grant access to session %s to user %s: %s",
				sessionId,
				getpass.getuser(),
				err,
				exc_info=True,
			)
	process = subprocess.Popen(
		args=command,
		shell=shell,
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		env=sp_env,
	)

	fd = process.stdout.fileno()
	fl = fcntl.fcntl(fd, fcntl.F_GETFL)
	fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

	logger.info("Process started, pid: %s", process.pid)
	if not waitForProcessEnding:
		return (process, None, process.pid, None)

	logger.info(
		"Waiting for process ending: %s (timeout: %s seconds)",
		process.pid,
		timeoutSeconds,
	)
	timeRunning = 0.0
	out = b""
	while process.poll() is None:
		if timeoutSeconds:
			if timeRunning >= timeoutSeconds:
				_terminateProcess(process)
				raise RuntimeError(
					f"Timed out after {timeRunning} seconds while waiting for process {process.pid}"
				)

			timeRunning += sleepDuration
		time.sleep(sleepDuration)
		try:
			data = process.stdout.read()
			if data:
				out += data
		except IOError:
			pass
	out = out.decode("utf-8", "replace")
	log = logger.notice
	if process.returncode == 0:
		logger.info("Process output:\n%s", out)
	else:
		logger.warning("Process output:\n%s", out)
		log = logger.warning
	log("Process %s ended with exit code %s", process.pid, process.returncode)
	return (None, None, None, None)


def setLocalSystemTime(timestring):
	"""
	Method sets the local systemtime
	param timestring = "2014-07-15 13:20:24.085661"
	Die Typ SYSTEMTIME-Struktur ist wie folgt:

	WYear           Integer-The current year.
	WMonth          Integer-The current month. January is 1.
	WDayOfWeek      Integer-The current day of the week. Sunday is 0.
	WDay            Integer-The current day of the month.
	WHour           Integer-The current hour.
	wMinute         Integer-The current minute.
	wSecond         Integer-The current second.
	wMilliseconds   Integer-The current millisecond.


	win32api.SetSystemTime

	int = SetSystemTime(year, month , dayOfWeek , day , hour , minute , second , millseconds )

	http://docs.activestate.com/activepython/2.5/pywin32/win32api__SetSystemTime_meth.html
	"""
	if not timestring:
		raise ValueError(
			"Invalid timestring given. It should be in format like: '2014-07-15 13:20:24.085661'"
		)

	try:
		dt = datetime.datetime.strptime(timestring, "%Y-%m-%d %H:%M:%S.%f")
		logger.info("Setting Systemtime Time to %s", timestring)
		systemTime = f'date --set="{dt.year}-{dt.month}-{dt.day} {dt.hour}:{dt.minute}:{dt.second}.{dt.microsecond}"'
		subprocess.call([systemTime])
	except Exception as err:
		logger.error("Failed to set System Time: %s", err)
