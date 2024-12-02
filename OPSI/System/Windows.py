# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Windows
"""

import difflib
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import winreg
from ctypes import (
	POINTER,
	Structure,
	byref,
	c_char,
	c_ubyte,
	c_uint,
	c_ulong,
	c_wchar,
	sizeof,
	windll,
)
from datetime import datetime
from functools import lru_cache

# Win32 imports
# pyright: reportMissingImports=false
from typing import Literal

import ntsecuritycon
import pefile
import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32gui
import win32net
import win32netcon
import win32pdh
import win32pdhutil
import win32process
import win32profile
import win32security
import win32service
import win32ts
import win32wnet
from opsicommon.logging import get_logger, secret_filter
from opsicommon.system.subprocess import (
	get_subprocess_environment as opsicommon_get_subprocess_environment,
)
from opsicommon.types import (
	forceBool,
	forceFilename,
	forceInt,
	forceUnicode,
	forceUnicodeList,
	forceUnicodeLower,
)

from OPSI.Exceptions import CommandNotFoundException

__all__ = (
	"HKEY_CURRENT_USER",
	"HKEY_LOCAL_MACHINE",
	"hooks",
	"SystemSpecificHook",
	"addSystemHook",
	"removeSystemHook",
	"get_subprocess_environment",
	"getArchitecture",
	"getOpsiHotfixName",
	"getHostname",
	"getFQDN",
	"getFileVersionInfo",
	"getProgramFilesDir",
	"getSystemDrive",
	"getNetworkInterfaces",
	"getDefaultNetworkInterfaceName",
	"getSystemProxySetting",
	"NetworkPerformanceCounter",
	"NetworkPerformanceCounterWMI",
	"NetworkPerformanceCounterPDH",
	"copyACL",
	"adjustPrivilege",
	"getRegistryValue",
	"setRegistryValue",
	"createRegistryKey",
	"getFreeDrive",
	"getDiskSpaceUsage",
	"mount",
	"umount",
	"getActiveConsoleSessionId",
	"getActiveDesktopName",
	"getActiveSessionIds",
	"getActiveSessionId",
	"getSessionInformation",
	"getActiveSessionInformation",
	"getUserSessionIds",
	"logoffSession",
	"logoffCurrentUser",
	"lockSession",
	"lockWorkstation",
	"reboot",
	"shutdown",
	"abortShutdown",
	"createWindowStation",
	"createDesktop",
	"getDesktops",
	"switchDesktop",
	"addUserToDesktop",
	"addUserToWindowStation",
	"which",
	"execute",
	"getPids",
	"getPid",
	"getProcessName",
	"getProcessHandle",
	"getProcessWindowHandles",
	"closeProcessWindows",
	"terminateProcess",
	"getUserToken",
	"runCommandInSession",
	"createUser",
	"deleteUser",
	"existsUser",
	"getUserSidFromHandle",
	"getUserSid",
	"getAdminGroupName",
	"setLocalSystemTime",
	"Impersonate",
	"get_available_drive_letter",
)

hooks = []

HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE

TH32CS_SNAPPROCESS = 0x00000002
MAX_INTERFACE_NAME_LEN = 256
MAXLEN_IFDESCR = 256
MAXLEN_PHYSADDR = 8
MAX_INTERFACES = 32

logger = get_logger("opsi.general")


class PROCESSENTRY32(Structure):
	_fields_ = [
		("dwSize", c_ulong),
		("cntUsage", c_ulong),
		("th32ProcessID", c_ulong),
		("th32DefaultHeapID", c_ulong),
		("th32ModuleID", c_ulong),
		("cntThreads", c_ulong),
		("th32ParentProcessID", c_ulong),
		("pcPriClassBase", c_ulong),
		("dwFlags", c_ulong),
		("szExeFile", c_char * 260),
	]


class MIB_IFROW(Structure):
	_fields_ = [
		("wszName", c_wchar * MAX_INTERFACE_NAME_LEN),
		("dwIndex", c_uint),
		("dwType", c_uint),
		("dwMtu", c_uint),
		("dwSpeed", c_uint),
		("dwPhysAddrLen", c_uint),
		("bPhysAddr", c_char * MAXLEN_PHYSADDR),
		("dwAdminStatus", c_uint),
		("dwOperStatus", c_uint),
		("dwLastChange", c_uint),
		("dwInOctets", c_uint),
		("dwInUcastPkts", c_uint),
		("dwInNUcastPkts", c_uint),
		("dwInDiscards", c_uint),
		("dwInErrors", c_uint),
		("dwInUnknownProtos", c_uint),
		("dwOutOctets", c_uint),
		("dwOutUcastPkts", c_uint),
		("dwOutNUcastPkts", c_uint),
		("dwOutDiscards", c_uint),
		("dwOutErrors", c_uint),
		("dwOutQLen", c_uint),
		("dwDescrLen", c_uint),
		("bDescr", c_char * MAXLEN_IFDESCR),
	]


class MIB_IFTABLE(Structure):
	_fields_ = [
		("dwNumEntries", c_uint),
		("table", MIB_IFROW * MAX_INTERFACES),
	]


class SystemSpecificHook:
	def __init__(self):
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
def getArchitecture():
	try:
		if win32process.IsWow64Process():
			return "x64"
		return "x86"
	except Exception as err:
		logger.error(
			"Error determining OS-Architecture: '%s'; returning default: 'x86'", err
		)
		return "x86"


def getOpsiHotfixName(helper=None):
	arch = getArchitecture()
	major = sys.getwindowsversion().major
	minor = sys.getwindowsversion().minor
	_os = "unknown"
	lang = "glb"

	if major == 6:
		if minor == 0:
			_os = "vista-win2008"
		elif minor == 1:
			if arch == "x86":
				_os = "win7"
			else:
				_os = "win7-win2008r2"
		elif minor == 2:
			if arch == "x86":
				_os = "win8"
			else:
				_os = "win8-win2012"
		elif minor == 3:
			if arch == "x86":
				_os = "win81"
			else:
				_os = "win81-win2012r2"

	elif major == 10:
		if arch == "x86":
			_os = "win10"
		else:
			_os = "win10-win2016"

	elif major == 11:
		_os = "win11"

	return f"mshotfix-{_os}-{arch}-{lang}"


def getHostname():
	return forceUnicodeLower(win32api.GetComputerName())


def getFQDN():
	fqdn = socket.getfqdn().lower()
	if fqdn.count(".") < 2:
		return getHostname()

	return forceUnicodeLower(getHostname() + "." + ".".join(fqdn.split(".")[1:]))


def getFileVersionInfo(filename):
	filename = forceFilename(filename)
	info = {}
	keys = [
		"CompanyName",
		"SpecialBuild",
		"Comments",
		"FileDescription",
		"FileVersion",
		"InternalName",
		"LegalCopyright",
		"LegalTrademarks",
		"OriginalFilename",
		"PrivateBuild",
		"ProductName",
		"ProductVersion",
	]
	for key in keys:
		info[key] = ""

	try:
		pe = pefile.PE(filename)
		pe.close()
	except pefile.PEFormatError:
		logger.warning("File %s is not a valid PE file", filename)
		return info
	if not hasattr(pe, "VS_VERSIONINFO"):
		logger.warning("Could not find file version info in file %s", filename)
		return info
	for idx in range(len(pe.VS_VERSIONINFO)):
		if not hasattr(pe, "FileInfo") or len(pe.FileInfo) <= idx:
			break
		for entry in pe.FileInfo[idx]:
			if not hasattr(entry, "StringTable"):
				continue
			for st_entry in entry.StringTable:
				for key, value in st_entry.entries.items():
					info[key.decode("utf-8", "backslashreplace")] = value.decode(
						"utf-8", "backslashreplace"
					)

	logger.debug("File version info for '%s': %s", filename, info)
	return info


def getProgramFilesDir():
	return getRegistryValue(
		HKEY_LOCAL_MACHINE,
		"Software\\Microsoft\\Windows\\CurrentVersion",
		"ProgramFilesDir",
	)


def getSystemDrive():
	return forceUnicode(os.getenv("SystemDrive", "c:"))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            NETWORK                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getNetworkInterfaces():
	try:
		# This code is from Michael Amrhein
		# http://www.mailinglistarchive.com/python-dev@python.org/msg07330.html
		MAX_ADAPTER_DESCRIPTION_LENGTH = 128
		MAX_ADAPTER_NAME_LENGTH = 256
		MAX_ADAPTER_ADDRESS_LENGTH = 8

		class IP_ADDR_STRING(Structure):
			pass

		LP_IP_ADDR_STRING = POINTER(IP_ADDR_STRING)
		IP_ADDR_STRING._fields_ = [
			("next", LP_IP_ADDR_STRING),
			("ipAddress", c_char * 16),
			("ipMask", c_char * 16),
			("context", c_ulong),
		]

		class IP_ADAPTER_INFO(Structure):
			pass

		LP_IP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
		IP_ADAPTER_INFO._fields_ = [
			("next", LP_IP_ADAPTER_INFO),
			("comboIndex", c_ulong),
			("adapterName", c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
			("description", c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
			("addressLength", c_uint),
			("address", c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
			("index", c_ulong),
			("type", c_uint),
			("dhcpEnabled", c_uint),
			("currentIpAddress", LP_IP_ADDR_STRING),
			("ipAddressList", IP_ADDR_STRING),
			("gatewayList", IP_ADDR_STRING),
			("dhcpServer", IP_ADDR_STRING),
			("haveWins", c_uint),
			("primaryWinsServer", IP_ADDR_STRING),
			("secondaryWinsServer", IP_ADDR_STRING),
			("leaseObtained", c_ulong),
			("leaseExpires", c_ulong),
		]
		GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
		GetAdaptersInfo.restype = c_ulong
		GetAdaptersInfo.argtypes = [LP_IP_ADAPTER_INFO, POINTER(c_ulong)]
		adapterList = (IP_ADAPTER_INFO * 10)()
		buflen = c_ulong(sizeof(adapterList))
		GetAdaptersInfo(byref(adapterList[0]), byref(buflen))
		return adapterList
	except Exception as err:
		logger.error(err, exc_info=True)
		raise RuntimeError(f"Failed to get network interfaces: {err}") from err


def getDefaultNetworkInterfaceName():
	for interface in getNetworkInterfaces():
		if interface.gatewayList.ipAddress:
			return interface.description
	return None


def getSystemProxySetting():
	# TODO: read proxy settings from system registry
	# HINTS: If proxycfg is not installed read this way (you have to cut)
	# netsh winhttp show proxy
	return None


class NetworkPerformanceCounter(threading.Thread):
	def __init__(self, interface):
		threading.Thread.__init__(self)
		self.interface = None
		self._lastBytesIn = 0
		self._lastBytesOut = 0
		self._lastTime = None
		self._bytesInPerSecond = 0
		self._bytesOutPerSecond = 0
		self._running = False
		self._stopped = False

		iftable = MIB_IFTABLE()
		iftable_size = c_ulong(sizeof(iftable))
		iftable.dwNumEntries = 0
		windll.iphlpapi.GetIfTable(byref(iftable), byref(iftable_size), 0)
		bestRatio = 0.0
		if iftable.dwNumEntries <= 0:
			raise RuntimeError(
				f"No network interfaces found while searching for interface '{interface}'"
			)

		for i in range(iftable.dwNumEntries):
			ratio = difflib.SequenceMatcher(
				None, iftable.table[i].bDescr, interface
			).ratio()
			logger.info(
				"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s",
				interface,
				iftable.table[i].bDescr,
				ratio,
			)
			if ratio > bestRatio:
				bestRatio = ratio
				self.interface = iftable.table[i].bDescr

		if not self.interface:
			raise ValueError(f"Network interface '{interface}' not found")

		logger.info(
			"NetworkPerformanceCounter: using interface '%s' match ratio (%s)",
			self.interface,
			bestRatio,
		)
		self.start()

	def __del__(self):
		self.stop()

	def stop(self):
		self._stopped = True

	def run(self):
		while not self._stopped:
			self._getStatistics()
			time.sleep(1)

	def _getStatistics(self):
		now = time.time()
		bytesIn = 0
		bytesOut = 0
		iftable = MIB_IFTABLE()
		iftable_size = c_ulong(sizeof(iftable))
		iftable.dwNumEntries = 0
		windll.iphlpapi.GetIfTable(byref(iftable), byref(iftable_size), 0)
		for i in range(iftable.dwNumEntries):
			if iftable.table[i].bDescr == self.interface:
				bytesIn = iftable.table[i].dwInOctets
				bytesOut = iftable.table[i].dwOutOctets
				break

		timeDiff = 1
		if self._lastTime:
			timeDiff = now - self._lastTime

		if self._lastBytesIn:
			self._bytesInPerSecond = (bytesIn - self._lastBytesIn) / timeDiff
			self._bytesInPerSecond = max(self._bytesInPerSecond, 0)

		if self._lastBytesOut:
			self._bytesOutPerSecond = (bytesOut - self._lastBytesOut) / timeDiff
			self._bytesOutPerSecond = max(self._bytesOutPerSecond, 0)

		self._lastBytesIn = bytesIn
		self._lastBytesOut = bytesOut
		self._lastTime = now

	def getBytesInPerSecond(self):
		return self._bytesInPerSecond

	def getBytesOutPerSecond(self):
		return self._bytesOutPerSecond


class NetworkPerformanceCounterWMI(threading.Thread):
	def __init__(self, interface):
		threading.Thread.__init__(self)
		self.interface = interface
		self._lastBytesIn = 0
		self._lastBytesOut = 0
		self._lastTime = None
		self._bytesInPerSecond = 0
		self._bytesOutPerSecond = 0
		self._running = False
		self._stopped = False
		self.wmi = None
		self.start()

	def __del__(self):
		self.stop()

	def stop(self):
		self._stopped = True

	def run(self):
		try:
			interface = self.interface
			self._running = True
			import pythoncom
			import wmi

			pythoncom.CoInitialize()
			self.wmi = wmi.WMI()
			bestRatio = 0.0
			for instance in self.wmi.Win32_PerfRawData_Tcpip_NetworkInterface():
				ratio = difflib.SequenceMatcher(None, instance.Name, interface).ratio()
				logger.info(
					"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s",
					interface,
					instance.Name,
					ratio,
				)
				if ratio > bestRatio:
					bestRatio = ratio
					self.interface = instance.Name
			logger.info(
				"NetworkPerformanceCounter: using interface '%s' match ratio (%s)",
				self.interface,
				bestRatio,
			)
		except Exception as err:
			logger.error(err, exc_info=True)

		try:
			while not self._stopped:
				self._getStatistics()
				time.sleep(1)
		finally:
			try:
				import pythoncom

				pythoncom.CoUninitialize()
			except Exception:
				pass

	def _getStatistics(self):
		now = time.time()
		for instance in self.wmi.Win32_PerfRawData_Tcpip_NetworkInterface(
			["BytesReceivedPersec", "BytesSentPersec"], Name=self.interface
		):
			bytesIn = instance.BytesReceivedPersec
			bytesOut = instance.BytesSentPersec

		timeDiff = 1
		if self._lastTime:
			timeDiff = now - self._lastTime

		if self._lastBytesIn:
			self._bytesInPerSecond = (bytesIn - self._lastBytesIn) / timeDiff
			self._bytesInPerSecond = max(self._bytesInPerSecond, 0)

		if self._lastBytesOut:
			self._bytesOutPerSecond = (bytesOut - self._lastBytesOut) / timeDiff
			self._bytesOutPerSecond = max(self._bytesOutPerSecond, 0)

		self._lastBytesIn = bytesIn
		self._lastBytesOut = bytesOut
		self._lastTime = now

	def getBytesInPerSecond(self):
		return self._bytesInPerSecond

	def getBytesOutPerSecond(self):
		return self._bytesOutPerSecond


class NetworkPerformanceCounterPDH(threading.Thread):
	def __init__(self, interface):
		threading.Thread.__init__(self)
		self.interface = None
		self._queryHandle = None
		self._inCounterHandle = None
		self._outCounterHandle = None
		self._running = False
		self._stopped = False
		self._bytesInPerSecond = 0.0
		self._bytesOutPerSecond = 0.0

		(items, instances) = win32pdh.EnumObjectItems(
			None,
			None,
			win32pdhutil.find_pdh_counter_localized_name("Network Interface"),
			win32pdh.PERF_DETAIL_WIZARD,
		)

		bestRatio = 0.0
		for instance in instances:
			ratio = difflib.SequenceMatcher(None, instance, interface).ratio()
			logger.info(
				"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s",
				interface,
				instance,
				ratio,
			)
			if ratio > bestRatio:
				bestRatio = ratio
				self.interface = instance
		logger.info(
			"NetworkPerformanceCounter: using interface '%s' match ratio (%s) with available counters: %s",
			self.interface,
			bestRatio,
			items,
		)

		# For correct translations (find_pdh_counter_localized_name) see:
		# HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib
		self._queryHandle = win32pdh.OpenQuery()
		self.bytesInPerSecondCounter = win32pdh.MakeCounterPath(
			(
				None,
				win32pdhutil.find_pdh_counter_localized_name("Network Interface"),
				self.interface,
				None,
				-1,
				win32pdhutil.find_pdh_counter_localized_name("Bytes In/sec"),
			)
		)
		self.bytesOutPerSecondCounter = win32pdh.MakeCounterPath(
			(
				None,
				win32pdhutil.find_pdh_counter_localized_name("Network Interface"),
				self.interface,
				None,
				-1,
				win32pdhutil.find_pdh_counter_localized_name("Bytes Sent/sec"),
			)
		)

		try:
			self._inCounterHandle = win32pdh.AddCounter(
				self._queryHandle, self.bytesInPerSecondCounter
			)
		except Exception as err:
			raise RuntimeError(
				f"Failed to add inCounterHandle {win32pdhutil.find_pdh_counter_localized_name('Network Interface')}->"
				f"{win32pdhutil.find_pdh_counter_localized_name('Bytes In/sec')}: {err}"
			) from err
		try:
			self._outCounterHandle = win32pdh.AddCounter(
				self._queryHandle, self.bytesOutPerSecondCounter
			)
		except Exception as err:
			raise RuntimeError(
				f"Failed to add inCounterHandle {win32pdhutil.find_pdh_counter_localized_name('Network Interface')}->"
				f"{win32pdhutil.find_pdh_counter_localized_name('Bytes Sent/sec')}: {err}"
			) from err
		self.start()

	def __del__(self):
		self.stop()

	def stop(self):
		self._stopped = True

	def run(self):
		self._running = True

		while not self._stopped:
			inbytes = 0.0
			outbytes = 0.0
			for _i in range(10):
				win32pdh.CollectQueryData(self._queryHandle)
				(_tp, val) = win32pdh.GetFormattedCounterValue(
					self._inCounterHandle, win32pdh.PDH_FMT_LONG
				)
				inbytes += val
				(_tp, val) = win32pdh.GetFormattedCounterValue(
					self._outCounterHandle, win32pdh.PDH_FMT_LONG
				)
				outbytes += val
				time.sleep(0.1)

			self._bytesInPerSecond = inbytes / 10.0
			self._bytesOutPerSecond = outbytes / 10.0

		if self._inCounterHandle:
			win32pdh.RemoveCounter(self._inCounterHandle)

		if self._outCounterHandle:
			win32pdh.RemoveCounter(self._outCounterHandle)

		if self._queryHandle:
			win32pdh.CloseQuery(self._queryHandle)

	def getBytesInPerSecond(self):
		return self._bytesInPerSecond

	def getBytesOutPerSecond(self):
		return self._bytesOutPerSecond


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            HELPERS                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def copyACL(src, dest):
	revision = src.GetAclRevision()
	logger.trace("copyACL: ace count is %s", src.GetAceCount())
	for i in range(src.GetAceCount()):
		logger.trace("copyACL: processing ace #%s", i)
		ace = src.GetAce(i)
		logger.trace("copyACL: ace: %s", ace)
		# XXX: Not sure if these are actually correct.
		# See http://aspn.activestate.com/ASPN/docs/ActivePython/2.4/pywin32/PyACL__GetAce_meth.html
		if ace[0][0] == win32con.ACCESS_ALLOWED_ACE_TYPE:
			dest.AddAccessAllowedAce(revision, ace[1], ace[2])
		elif ace[0][0] == win32con.ACCESS_DENIED_ACE_TYPE:
			dest.AddAccessDeniedAce(revision, ace[1], ace[2])
		elif ace[0][0] == win32con.SYSTEM_AUDIT_ACE_TYPE:
			dest.AddAuditAccessAce(revision, ace[1], ace[2], 1, 1)
		elif ace[0][0] == win32con.ACCESS_ALLOWED_OBJECT_ACE_TYPE:
			dest.AddAccessAllowedObjectAce(
				revision, ace[0][1], ace[1], ace[2], ace[3], ace[4]
			)
		elif ace[0][0] == win32con.ACCESS_DENIED_OBJECT_ACE_TYPE:
			dest.AddAccessDeniedObjectAce(
				revision, ace[0][1], ace[1], ace[2], ace[3], ace[4]
			)
		elif ace[0][0] == win32con.SYSTEM_AUDIT_OBJECT_ACE_TYPE:
			dest.AddAuditAccessObjectAce(
				revision, ace[0][1], ace[1], ace[2], ace[3], ace[4], 1, 1
			)

	return src.GetAceCount()


def adjustPrivilege(priv, enable=1):
	# Get the process token.
	flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
	htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
	# Get the ID for the system shutdown privilege.
	_id = win32security.LookupPrivilegeValue(None, priv)
	# Now obtain the privilege for this process.
	# Create a list of the privileges to be added.
	if enable:
		newPrivileges = [(_id, win32security.SE_PRIVILEGE_ENABLED)]
	else:
		newPrivileges = [(_id, 0)]
	# and make the adjustment.
	win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                             REGISTRY                                              -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getRegistryValue(
	key, subKey, valueName, view: Literal["32bit", "64bit", "sysnative"] = "sysnative"
):
	"""
	Get the value of a registry key.
	A view can be specified to explicitly read from the 32bit or 64bit registry view.
	If no view is specified, a WOW process will be redirected to the corresponding registration view.
	"""
	if view == "sysnative":
		view = "64bit" if "64" in platform.architecture()[0] else "32bit"

	flags = winreg.KEY_READ
	if view == "32bit":
		flags |= winreg.KEY_WOW64_32KEY
	elif view == "64bit":
		flags |= winreg.KEY_WOW64_64KEY

	with winreg.OpenKeyEx(key, subKey, 0, flags) as hkey:
		return winreg.QueryValueEx(hkey, valueName)[0]


def setRegistryValue(
	key,
	subKey,
	valueName,
	value,
	view: Literal["32bit", "64bit", "sysnative"] = "sysnative",
):
	"""
	Set the value of a registry key.
	A view can be specified to explicitly write to the 32bit or 64bit registry view.
	IF sysnative is specified, the view will be choosen based on the architecture of the operating system.
	"""
	if view == "sysnative":
		view = "64bit" if "64" in platform.architecture()[0] else "32bit"

	flags = winreg.KEY_WRITE
	if view == "32bit":
		flags |= winreg.KEY_WOW64_32KEY
	elif view == "64bit":
		flags |= winreg.KEY_WOW64_64KEY

	with winreg.CreateKeyEx(key, subKey, 0, flags) as hkey:
		if isinstance(value, int):
			winreg.SetValueEx(
				hkey,
				valueName,
				0,
				winreg.REG_QWORD if value > 0xFFFFFFFF else winreg.REG_DWORD,
				value,
			)
		else:
			winreg.SetValueEx(hkey, valueName, 0, winreg.REG_SZ, value)


def createRegistryKey(key, subKey):
	hkey = winreg.CreateKey(key, subKey)
	winreg.CloseKey(hkey)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            FILESYSTEMS                                            -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getFreeDrive(startLetter="a"):
	startLetter = forceUnicodeLower(startLetter)
	startLetterSeen = False
	for letter in "abcdefghijklmnopqrstuvwxyz":
		if startLetter == letter:
			startLetterSeen = True

		if not startLetterSeen:
			continue

		letter += ":"
		if win32file.GetDriveType(letter) == 1:
			return letter

	raise RuntimeError("No free drive available")


def getDiskSpaceUsage(path):
	path = forceUnicode(path)
	if len(path) == 1:
		# Assuming a drive letter like "C"
		path = path + ":"

	(sectPerCluster, bytesPerSector, freeClusters, totalClusters) = (
		win32file.GetDiskFreeSpace(path)
	)

	capacity = totalClusters * sectPerCluster * bytesPerSector
	available = freeClusters * sectPerCluster * bytesPerSector

	info = {
		"capacity": capacity,
		"available": available,
		"used": capacity - available,
		"usage": (capacity - available) / capacity,
	}
	logger.info("Disk space usage for path '%s': %s", path, info)
	return info


def get_available_drive_letter(start="c", end="z"):
	drive_letters_in_use = [
		x[0].lower() for x in win32api.GetLogicalDriveStrings().split("\0") if x
	]

	for i in range(ord(start), ord(end)):
		drive = forceUnicode(chr(i))
		if drive not in drive_letters_in_use:
			logger.info("Available drive letter '%s' found", drive)
			return drive

	return None


def mount(dev, mountpoint, **options):
	"""
	Mount *dev* to the given *mountpoint*.

	The mountpoint can either be a Windows drive letter ranging from
	``a:`` to ``z:`` or ``'dynamic'``.
	If *mountpoint* is ``'dynamic'`` it will try to find a free
	mountpoint for the operation.
	This may raise an exception if no free mountpoint is found.
	"""
	dev = forceUnicode(dev)
	mountpoint = forceUnicode(mountpoint)

	match = re.search(r"^([a-z]:|dynamic)$", mountpoint, re.IGNORECASE)
	if not match:
		logger.error("Invalid mountpoint '%s'", mountpoint)
		raise ValueError(f"Invalid mountpoint '{mountpoint}'")

	if mountpoint == "dynamic":
		mountpoint = get_available_drive_letter().rstrip(":") + ":"
		if not mountpoint:
			raise RuntimeError(
				"Dynamic mountpoint detection and no free mountpoint available"
			)

	if not dev.lower().startswith(("smb://", "cifs://", "webdavs://", "https://")):
		raise NotImplementedError(f"Mounting fs type '{dev}' not implemented")

	if "username" not in options or not options["username"]:
		options["username"] = None
	if "password" not in options or not options["password"]:
		options["password"] = None
	else:
		secret_filter.add_secrets(options["password"])

	if dev.lower().startswith(("smb://", "cifs://")):
		match = re.search(r"^(smb|cifs)://([^/]+/.+)$", dev, re.IGNORECASE)
		if not match:
			raise ValueError(f"Bad smb/cifs uri '{dev}'")
		parts = match.group(2).split("/")
		dev = f"\\\\{parts[0]}\\{parts[1]}"

		domain = options.get("domain") or getHostname()
		if options["username"] and "\\" in options["username"]:
			domain = options["username"].split("\\")[0]
			options["username"] = options["username"].split("\\")[-1]

		if options["username"]:
			options["username"] = f"{domain}\\{options['username']}"

	elif dev.lower().startswith(("webdavs://", "https://")):
		dev = dev.replace("webdavs://", "https://")
		# HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\WebClient\Parameters FileSizeLimitInBytes = 0xffffffff
		# HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\ZoneMap\Domains\<fqdn>@SSL@4447 file = 1

	try:
		try:
			# Remove connection and update user profile (remove persistent connection)
			win32wnet.WNetCancelConnection2(
				mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True
			)
		except pywintypes.error as cc_err:
			if cc_err.winerror == 2250:
				# Not connected
				logger.debug("Failed to umount '%s': %s", mountpoint, cc_err)
			else:
				raise

		logger.notice("Mounting '%s' to '%s'", dev, mountpoint)
		# Mount (not persistent)
		win32wnet.WNetAddConnection2(
			win32netcon.RESOURCETYPE_DISK,
			mountpoint,
			dev,
			None,
			options["username"],
			options["password"],
			0,
		)

	except Exception as err:
		logger.error("Failed to mount '%s': %s", dev, err)
		raise RuntimeError(f"Failed to mount '{dev}': {err}") from err


def umount(mountpoint):
	try:
		# Remove connection and update user profile (remove persistent connection)
		win32wnet.WNetCancelConnection2(
			mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True
		)
	except pywintypes.error as cc_err:
		if cc_err.winerror == 2250:
			# Not connected
			logger.debug("Failed to umount '%s': %s", mountpoint, cc_err)
		else:
			raise
	except Exception as err:
		logger.error("Failed to umount '%s': %s", mountpoint, err)
		raise RuntimeError("Failed to umount '{mountpoint}': {err}") from err


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                               SESSION / WINSTA / DESKTOP HANDLING                                 -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getActiveConsoleSessionId():
	"""
	Retrieves the session id of the console session.
	The console session is the session that is currently attached to the physical console.
	"""
	try:
		return int(win32ts.WTSGetActiveConsoleSessionId())
	except Exception as err:
		logger.warning(
			"Failed to get WTSGetActiveConsoleSessionId: %s, returning 1", err
		)
		return 1


def getActiveDesktopName():
	desktop = win32service.OpenInputDesktop(0, True, win32con.MAXIMUM_ALLOWED)
	return forceUnicode(
		win32service.GetUserObjectInformation(desktop, win32con.UOI_NAME)
	)


WTS_PROTOCOLS = {
	win32ts.WTS_PROTOCOL_TYPE_CONSOLE: "console",
	win32ts.WTS_PROTOCOL_TYPE_ICA: "citrix",
	win32ts.WTS_PROTOCOL_TYPE_RDP: "rdp",
}
WTS_STATES = {
	win32ts.WTSActive: "active",
	win32ts.WTSConnected: "connected",
	win32ts.WTSConnectQuery: "connect_query",
	win32ts.WTSShadow: "shadow",
	win32ts.WTSDisconnected: "disconnected",
	win32ts.WTSIdle: "idle",
	win32ts.WTSListen: "listen",
	win32ts.WTSReset: "reset",
	win32ts.WTSDown: "down",
	win32ts.WTSInit: "init",
}


def getActiveSessionIds(protocol=None, states=None):
	"""
	Retrieves ids of all active user sessions.

	:raises ValueError: In case an invalid protocol is provided.

	:param protocol: Return only sessions of this protocol type (console / rdp / citrix)
	:type protocol: str

	:param states: Return only sessions in one of this states (active / connected / disconnected)
	:type protocol: list

	:returns: List of active sessions
	:rtype: list
	"""
	if states is None:
		states = ["active", "disconnected"]
	if states:
		new_states = []
		for state in states:
			if state not in WTS_STATES:
				for _state, _name in WTS_STATES.items():
					if _name == state:
						state = _state
						break
				if state not in WTS_STATES:
					logger.warning("Invalid session state '%s'", state)
					continue
			new_states.append(state)
		states = new_states

	if protocol is not None:
		if protocol not in WTS_PROTOCOLS:
			for proto, name in WTS_PROTOCOLS.items():
				if name == protocol:
					protocol = proto
					break
		if protocol not in WTS_PROTOCOLS:
			logger.warning("Invalid session protocol '%s'", protocol)
			protocol = None

	session_ids = []
	server = win32ts.WTS_CURRENT_SERVER_HANDLE
	for session in win32ts.WTSEnumerateSessions(server):
		# WTS_CONNECTSTATE_CLASS:
		# WTSActive,WTSConnected,WTSConnectQuery,WTSShadow,WTSDisconnected,
		# WTSIdle,WTSListen,WTSReset,WTSDown,WTSInit
		if states and session.get("State") not in states:
			continue
		if not win32ts.WTSQuerySessionInformation(
			server, session["SessionId"], win32ts.WTSUserName
		):
			continue
		if protocol and protocol != win32ts.WTSQuerySessionInformation(
			server, session["SessionId"], win32ts.WTSClientProtocolType
		):
			continue
		session_ids.append(int(session["SessionId"]))
	return session_ids


def getActiveSessionId():
	"""
	Retrieves the active user session id.
	"""
	sessions = getActiveSessionIds()
	if sessions:
		return sessions[0]
	return None


def getSessionInformation(sessionId):
	sessionId = int(sessionId)
	server = win32ts.WTS_CURRENT_SERVER_HANDLE
	for session in win32ts.WTSEnumerateSessions(server):
		session["SessionId"] = int(session["SessionId"])
		if session["SessionId"] != sessionId:
			continue

		session["UserName"] = win32ts.WTSQuerySessionInformation(
			server, session["SessionId"], win32ts.WTSUserName
		)
		session["Protocol"] = win32ts.WTSQuerySessionInformation(
			server, session["SessionId"], win32ts.WTSClientProtocolType
		)
		# session["WorkingDirectory"] = win32ts.WTSQuerySessionInformation(server, session["SessionId"], win32ts.WTSWorkingDirectory)
		session["DomainName"] = win32ts.WTSQuerySessionInformation(
			server, session["SessionId"], win32ts.WTSDomainName
		)
		session["StateName"] = WTS_STATES.get(session["State"], "unknown")
		session["ProtocolName"] = WTS_PROTOCOLS.get(session["Protocol"], "unknown")
		return session

	return {}


def getActiveSessionInformation():
	info = []
	for sessionId in getActiveSessionIds():
		info.append(getSessionInformation(sessionId))
	return info


def getUserSessionIds(username):
	sessionIds = []
	if not username:
		return sessionIds

	if "\\" in username:
		username = username.split("\\")[-1]

	for session in getActiveSessionInformation():
		if (
			session.get("UserName")
			and session.get("UserName").lower() == username.lower()
		):
			sessionIds.append(session["SessionId"])
	return sessionIds


def _getSessionIdByUsername(username):
	for session in getActiveSessionInformation():
		if session["UserName"] and session["UserName"].lower() == username.lower():
			return session["SessionId"]
	raise ValueError(f"Session of user {username} not found")


def logoffSession(session_id=None, username=None):
	if not session_id and username:
		session_id = _getSessionIdByUsername(username)
	if not session_id:
		session_id = getActiveConsoleSessionId()
	if session_id:
		win32ts.WTSLogoffSession(
			win32ts.WTS_CURRENT_SERVER_HANDLE, int(session_id), False
		)


logoffCurrentUser = logoffSession


def lockSession(session_id=None, username=None):
	if not session_id and username:
		session_id = _getSessionIdByUsername(username)
	if not session_id:
		session_id = getActiveConsoleSessionId()
	if session_id:
		win32ts.WTSDisconnectSession(
			win32ts.WTS_CURRENT_SERVER_HANDLE, int(session_id), False
		)


lockWorkstation = lockSession


def reboot(wait=10):
	logger.notice("Rebooting in %s seconds", wait)
	wait = forceInt(wait)
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, "Opsi reboot", wait, True, True)


def shutdown(wait=10):
	logger.notice("Shutting down in %s seconds", wait)
	wait = forceInt(wait)
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, "Opsi shutdown", wait, True, False)


def abortShutdown():
	logger.notice("Aborting system shutdown")
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.AbortSystemShutdown(None)


def createWindowStation(name):
	name = forceUnicode(name)
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 1
	sa.SECURITY_DESCRIPTOR = None

	try:
		return win32service.CreateWindowStation(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error as err:
		logger.error("Failed to create window station '%s': %s", name, err)
	return None


def createDesktop(name, runCommand=None):
	name = forceUnicode(name)
	if runCommand:
		runCommand = forceUnicode(runCommand)
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 0

	try:
		sa.SECURITY_DESCRIPTOR = win32security.GetUserObjectSecurity(
			win32service.OpenDesktop("default", 0, 0, win32con.MAXIMUM_ALLOWED),
			win32con.DACL_SECURITY_INFORMATION,
		)
	except Exception as err:
		logger.error(err)
		sa.SECURITY_DESCRIPTOR = None

	hdesk = None
	try:
		hdesk = win32service.CreateDesktop(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error as error:
		logger.error("Failed to create desktop '%s': %s", name, forceUnicode(error))

	if runCommand:
		sti = win32process.STARTUPINFO()
		sti.lpDesktop = name
		win32process.CreateProcess(
			None,
			runCommand,
			None,
			None,
			True,
			win32con.CREATE_NEW_CONSOLE,
			None,
			"c:\\",
			sti,
		)

	return hdesk


def getDesktops(winsta=None):
	if not winsta:
		winsta = win32service.GetProcessWindowStation()

	return [forceUnicodeLower(d) for d in winsta.EnumDesktops()]


def switchDesktop(name):
	name = forceUnicode(name)
	hdesk = win32service.OpenDesktop(name, 0, 0, win32con.MAXIMUM_ALLOWED)
	hdesk.SwitchDesktop()


def addUserToDesktop(desktop, userSid):
	"""
	Adds the given PySID representing a user to the given desktop's
	discretionary access-control list. The old security descriptor for
	desktop is returned.
	"""
	desktopAll = (
		win32con.DESKTOP_CREATEMENU
		| win32con.DESKTOP_CREATEWINDOW
		| win32con.DESKTOP_ENUMERATE
		| win32con.DESKTOP_HOOKCONTROL
		| win32con.DESKTOP_JOURNALPLAYBACK
		| win32con.DESKTOP_JOURNALRECORD
		| win32con.DESKTOP_READOBJECTS
		| win32con.DESKTOP_SWITCHDESKTOP
		| win32con.DESKTOP_WRITEOBJECTS
		| win32con.DELETE
		| win32con.READ_CONTROL
		| win32con.WRITE_DAC
		| win32con.WRITE_OWNER
	)

	securityDesc = win32security.GetUserObjectSecurity(
		desktop, win32con.DACL_SECURITY_INFORMATION
	)

	# Get discretionary access-control list (DACL) for desktop.
	acl = securityDesc.GetSecurityDescriptorDacl()

	# Create a new access control list for desktop.
	newAcl = win32security.ACL()

	if acl:
		copyACL(acl, newAcl)

	# Add the ACE for user_sid to the desktop.
	ace0Index = newAcl.GetAceCount()
	newAcl.AddAccessAllowedAce(win32con.ACL_REVISION, desktopAll, userSid)

	# Create a new security descriptor and set its new DACL.
	newSecurityDesc = win32security.SECURITY_DESCRIPTOR()
	newSecurityDesc.SetSecurityDescriptorDacl(True, newAcl, False)

	# Set the new security descriptor for desktop.
	win32security.SetUserObjectSecurity(
		desktop, win32con.DACL_SECURITY_INFORMATION, newSecurityDesc
	)

	return [ace0Index]


def addUserToWindowStation(winsta, userSid):
	"""
	Adds the given PySID representing a user to the given window station's
	discretionary access-control list. The old security descriptor for
	winsta is returned.
	"""
	winstaAll = (
		win32con.WINSTA_ACCESSCLIPBOARD
		| win32con.WINSTA_ACCESSGLOBALATOMS
		| win32con.WINSTA_CREATEDESKTOP
		| win32con.WINSTA_ENUMDESKTOPS
		| win32con.WINSTA_ENUMERATE
		| win32con.WINSTA_EXITWINDOWS
		| win32con.WINSTA_READATTRIBUTES
		| win32con.WINSTA_READSCREEN
		| win32con.WINSTA_WRITEATTRIBUTES
		| win32con.DELETE
		| win32con.READ_CONTROL
		| win32con.WRITE_DAC
		| win32con.WRITE_OWNER
	)

	genericAccess = (
		win32con.GENERIC_READ
		| win32con.GENERIC_WRITE
		| win32con.GENERIC_EXECUTE
		| win32con.GENERIC_ALL
	)

	# Get the security description for winsta.
	securityDesc = win32security.GetUserObjectSecurity(
		winsta, win32con.DACL_SECURITY_INFORMATION
	)

	# Get discretionary access-control list (DACL) for winsta.
	acl = securityDesc.GetSecurityDescriptorDacl()

	# Create a new access control list for winsta.
	newAcl = win32security.ACL()

	if acl:
		copyACL(acl, newAcl)

	# Add the first ACE for userSid to the window station.
	ace0Index = newAcl.GetAceCount()
	aceFlags = (
		win32con.CONTAINER_INHERIT_ACE
		| win32con.INHERIT_ONLY_ACE
		| win32con.OBJECT_INHERIT_ACE
	)
	newAcl.AddAccessAllowedAceEx(
		win32con.ACL_REVISION, aceFlags, genericAccess, userSid
	)

	# Add the second ACE for userSid to the window station.
	ace1Index = newAcl.GetAceCount()
	aceFlags = win32con.NO_PROPAGATE_INHERIT_ACE
	newAcl.AddAccessAllowedAceEx(win32con.ACL_REVISION, aceFlags, winstaAll, userSid)

	# Create a new security descriptor and set its new DACL.
	# NOTE: Simply creating a new security descriptor and assigning it as
	# the security descriptor for winsta (without setting the DACL) is
	# sufficient to allow windows to be opened, but that is probably not
	# providing any kind of security on winsta.
	newSecurityDesc = win32security.SECURITY_DESCRIPTOR()
	newSecurityDesc.SetSecurityDescriptorDacl(True, newAcl, False)

	# Set the new security descriptor for winsta.
	win32security.SetUserObjectSecurity(
		winsta, win32con.DACL_SECURITY_INFORMATION, newSecurityDesc
	)

	return [ace0Index, ace1Index]


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                        PROCESS HANDLING                                           -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
@lru_cache(100)
def which(cmd: str) -> str:
	path = shutil.which(cmd)
	if not path:
		raise CommandNotFoundException(f"Command '{cmd}' not found in PATH")
	return path


def get_subprocess_environment():
	return os.environ.copy()


def execute(
	cmd,
	waitForEnding=True,
	getHandle=False,
	ignoreExitCode=[],
	exitOnStderr=False,
	captureStderr=True,
	encoding=None,
	timeout=0,
	shell=True,
	env={},
	stdin_data=b"",
):
	if not isinstance(cmd, list):
		cmd = forceUnicode(cmd)
	waitForEnding = forceBool(waitForEnding)
	getHandle = forceBool(getHandle)
	exitOnStderr = forceBool(exitOnStderr)
	captureStderr = forceBool(captureStderr)
	timeout = forceInt(timeout)
	shell = forceBool(shell)

	sp_env = opsicommon_get_subprocess_environment()
	sp_env.update(env)

	exitCode = 0
	result = []
	startTime = time.time()
	try:
		logger.info("Executing: %s", cmd)
		if getHandle:
			stderr = subprocess.STDOUT if captureStderr else None
			with subprocess.Popen(
				cmd,
				shell=shell,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				stderr=stderr,
				env=sp_env,
			) as proc:
				return proc.stdout

		data = b""
		ret = None

		with subprocess.Popen(
			cmd,
			shell=shell,
			stdin=subprocess.PIPE if stdin_data else None,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE if captureStderr else None,
			env=sp_env,
		) as proc:
			if stdin_data:
				proc.stdin.write(stdin_data)
				proc.stdin.flush()

			while ret is None:
				ret = proc.poll()
				try:
					chunk = proc.stdout.read()
					if len(chunk) > 0:
						data += chunk
				except IOError as error:
					if error.errno != 11:
						raise

				if captureStderr:
					try:
						chunk = proc.stderr.read()
						if len(chunk) > 0:
							if exitOnStderr:
								raise IOError(
									exitCode, f"Command '{cmd}' failed: {chunk}"
								)
							data += chunk
					except IOError as error:
						if error.errno != 11:
							raise

				if time.time() - startTime >= timeout > 0:
					try:
						proc.kill()
					except Exception:
						pass

					raise IOError(
						exitCode,
						f"Command '{cmd}' timed out atfer {(time.time() - startTime)} seconds",
					)

				time.sleep(0.001)

		exitCode = ret
		if data:
			lines = data.split(b"\n")
			lineCount = len(lines)
			for i, origLine in enumerate(lines):
				line = origLine.decode("cp850", "replace").replace("\r", "")
				if (i == lineCount - 1) and not line:
					break

				logger.debug(">>> %s", line)
				result.append(line)
	except (os.error, IOError) as err:
		# Some error occurred during execution
		raise IOError(err.errno, f"Command '{cmd}' failed:\n{err}") from err

	logger.debug("Exit code: %s", exitCode)
	if exitCode:
		if isinstance(ignoreExitCode, bool) and ignoreExitCode:
			pass
		elif isinstance(ignoreExitCode, list) and exitCode in ignoreExitCode:
			pass
		else:
			result = "\n".join(result)
			raise IOError(exitCode, f"Command '{cmd}' failed ({exitCode}):\n{result}")

	return result


def getPids(process, sessionId=None):
	process = forceUnicode(process)
	if sessionId is not None:
		sessionId = forceInt(sessionId)

	logger.info(
		"Searching pids of process name %s (session id: %s)", process, sessionId
	)
	processIds = []
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.trace("Getting first process")
	if Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE:
		logger.error("Failed to get first process")
		return None

	while True:
		pid = pe32.th32ProcessID
		sid = "unknown"
		try:
			sid = win32ts.ProcessIdToSessionId(pid)
		except Exception:
			pass
		processName = pe32.szExeFile.decode("Windows-1252")
		logger.trace(
			"   got process %s with pid %d in session %s", processName, pid, sid
		)
		if processName.lower() == process.lower():
			logger.info(
				"Found process %s with matching name (pid %d, session %s)",
				processName.lower(),
				pid,
				sid,
			)
			if sessionId is None or (sid == sessionId):
				processIds.append(forceInt(pid))

		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break

	CloseHandle(hProcessSnap)
	if not processIds:
		logger.debug(
			"No process with name %s found (session id: %s)", process, sessionId
		)

	return processIds


def getPid(process, sessionId=None):
	process = forceUnicode(process)
	if sessionId is not None:
		sessionId = forceInt(sessionId)

	processId = 0
	processIds = getPids(process, sessionId)
	if processIds:
		processId = processIds[0]

	return processId


def getProcessName(processId):
	processId = forceInt(processId)
	logger.notice("Searching name of process %d", processId)

	processName = ""
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.info("Getting first process")
	if Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE:
		logger.error("Failed getting first process")
		return None

	while True:
		pid = pe32.th32ProcessID
		if pid == processId:
			processName = pe32.szExeFile.decode("Windows-1252")
			break

		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break

	CloseHandle(hProcessSnap)
	return processName


def getProcessHandle(processId):
	processId = forceInt(processId)
	processHandle = win32api.OpenProcess(1, 0, processId)
	return processHandle


def getProcessWindowHandles(processId):
	processId = forceInt(processId)
	logger.info("Getting window handles of process with id %s", processId)

	def callback(windowHandle, windowHandles):
		if win32process.GetWindowThreadProcessId(windowHandle)[1] == processId:
			logger.debug(
				"Found window %s of process with id %s", windowHandle, processId
			)
			windowHandles.append(windowHandle)

		return True

	windowHandles = []
	win32gui.EnumWindows(callback, windowHandles)
	return windowHandles


def closeProcessWindows(processId):
	processId = forceInt(processId)
	logger.info("Closing windows of process with id %s", processId)
	for windowHandle in getProcessWindowHandles(processId):
		logger.debug("Sending WM_CLOSE message to window %s", windowHandle)
		win32gui.SendMessage(windowHandle, win32con.WM_CLOSE, 0, 0)


def terminateProcess(processHandle=None, processId=None):
	if processId is not None:
		processId = forceInt(processId)

	if not processHandle and not processId:
		raise ValueError("Neither process handle not process id given")

	if not processHandle:
		processHandle = getProcessHandle(processId)

	win32process.TerminateProcess(processHandle, 0)


def getUserToken(sessionId=None, duplicateFrom="winlogon.exe"):
	if sessionId is not None:
		sessionId = forceInt(sessionId)
	duplicateFrom = forceUnicode(duplicateFrom)

	if sessionId is None or (sessionId < 0):
		sessionId = getActiveSessionId()

	pid = getPid(process=duplicateFrom, sessionId=sessionId)
	if not pid:
		raise RuntimeError(
			f"Failed to get user token, pid of '{duplicateFrom}' not found in session '{sessionId}'"
		)

	hProcess = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, False, pid)
	hPToken = win32security.OpenProcessToken(
		hProcess,
		win32con.TOKEN_ADJUST_PRIVILEGES
		| win32con.TOKEN_QUERY
		| win32con.TOKEN_DUPLICATE
		| win32con.TOKEN_ASSIGN_PRIMARY
		| win32con.TOKEN_READ
		| win32con.TOKEN_WRITE,
	)

	_id = win32security.LookupPrivilegeValue(None, win32security.SE_DEBUG_NAME)

	newPrivileges = [(_id, win32security.SE_PRIVILEGE_ENABLED)]

	hUserTokenDup = win32security.DuplicateTokenEx(
		ExistingToken=hPToken,
		DesiredAccess=win32con.MAXIMUM_ALLOWED,
		ImpersonationLevel=win32security.SecurityIdentification,
		TokenType=ntsecuritycon.TokenPrimary,
		TokenAttributes=None,
	)

	# Adjust Token privilege
	win32security.SetTokenInformation(
		hUserTokenDup, ntsecuritycon.TokenSessionId, sessionId
	)
	win32security.AdjustTokenPrivileges(hUserTokenDup, 0, newPrivileges)

	return hUserTokenDup


def runCommandInSession(
	command,
	sessionId=None,
	desktop="default",
	duplicateFrom="winlogon.exe",
	waitForProcessEnding=True,
	timeoutSeconds=0,
	noWindow=False,
	shell=True,
):
	"""
	put command arguments in double, not single, quotes.
	"""
	command = forceUnicode(command)
	if sessionId is not None:
		sessionId = forceInt(sessionId)

	desktop = forceUnicodeLower(desktop)
	if desktop.find("\\") == -1:
		desktop = "winsta0\\" + desktop

	duplicateFrom = forceUnicode(duplicateFrom)
	waitForProcessEnding = forceBool(waitForProcessEnding)
	timeoutSeconds = forceInt(timeoutSeconds)

	logger.debug("Session id given: %s", sessionId)
	if sessionId is None or (sessionId < 0):
		logger.debug("No session id given, running in active session")
		sessionId = getActiveSessionId()

	if desktop.split("\\")[-1] not in ("default", "winlogon"):
		logger.info("Creating new desktop '%s'", desktop.split("\\")[-1])
		try:
			createDesktop(desktop.split("\\")[-1])
		except Exception as err:
			logger.warning(err)

	userToken = getUserToken(sessionId, duplicateFrom)

	dwCreationFlags = win32con.NORMAL_PRIORITY_CLASS
	if noWindow:
		dwCreationFlags |= win32con.CREATE_NO_WINDOW

	sti = win32process.STARTUPINFO()
	sti.lpDesktop = desktop

	logger.notice(
		"Executing: '%s' in session '%s' on desktop '%s'", command, sessionId, desktop
	)
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(
		userToken, None, command, None, None, 1, dwCreationFlags, None, None, sti
	)

	logger.info("Process startet, pid: %d", dwProcessId)
	if not waitForProcessEnding:
		return (hProcess, hThread, dwProcessId, dwThreadId)

	logger.info(
		"Waiting for process ending: %d (timeout: %d seconds)",
		dwProcessId,
		timeoutSeconds,
	)
	sec = 0.0
	while win32event.WaitForSingleObject(hProcess, timeoutSeconds):
		if timeoutSeconds > 0:
			if sec >= timeoutSeconds:
				terminateProcess(processId=dwProcessId)
				raise RuntimeError(
					f"Timed out after {sec} seconds while waiting for process {dwProcessId}"
				)
			sec += 0.1
		time.sleep(0.1)

	exitCode = win32process.GetExitCodeProcess(hProcess)
	log = logger.notice
	if exitCode != 0:
		log = logger.warning
	log("Process %d ended with exit code %d", dwProcessId, exitCode)
	return (None, None, None, None)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                     USER / GROUP HANDLING                                         -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def createUser(username, password, groups=[]):
	username = forceUnicode(username)
	password = forceUnicode(password)
	groups = forceUnicodeList(groups)
	secret_filter.add_secrets(password)

	domain = getHostname().upper()
	if "\\" in username:
		domain = username.split("\\")[0]
		username = username.split("\\")[-1]

	domain = domain.upper()
	if domain != getHostname().upper():
		raise ValueError(f"Can only handle domain {getHostname().upper()}")

	userData = {
		"name": username,
		"full_name": "",
		"password": password,
		"flags": win32netcon.UF_NORMAL_ACCOUNT | win32netcon.UF_SCRIPT,
		"priv": win32netcon.USER_PRIV_USER,
		"home_dir": None,
		"home_dir_drive": None,
		"primary_group_id": ntsecuritycon.DOMAIN_GROUP_RID_USERS,
		"password_expired": 0,
	}

	win32net.NetUserAdd("\\\\" + domain, 1, userData)
	if not groups:
		return

	usr = {"domainandname": domain + "\\" + username}
	for group in groups:
		logger.info("Adding user '%s' to group '%s'", username, group)
		win32net.NetLocalGroupAddMembers("\\\\" + domain, group, 3, [usr])


def deleteUser(username, deleteProfile=True):
	username = forceUnicode(username)
	domain = getHostname()
	if "\\" in username:
		domain = username.split("\\")[0]
		username = username.split("\\")[-1]

	domain = domain.upper()
	if domain != getHostname().upper():
		raise ValueError(f"Can only handle domain {getHostname().upper()}")

	if deleteProfile:
		try:
			sid = getUserSid(username)
			if sid:
				try:
					win32profile.DeleteProfile(sid)
				except Exception as err:
					logger.info(
						"Failed to delete user profile '%s' (sid %s): %s",
						username,
						sid,
						err,
					)
		except Exception:
			pass
	try:
		win32net.NetUserDel("\\\\" + domain, username)
	except win32net.error as error:
		logger.info("Failed to delete user '%s': %s", username, forceUnicode(error))


def existsUser(username):
	username = forceUnicode(username)
	domain = getHostname()
	if "\\" in username:
		domain = username.split("\\")[0]
		username = username.split("\\")[-1]

	domain = domain.upper()
	if domain != getHostname().upper():
		raise ValueError(f"Can only handle domain {getHostname().upper()}")

	for user in win32net.NetUserEnum("\\\\" + domain, 0)[0]:
		if user.get("name").lower() == username.lower():
			return True

	return False


def getUserSidFromHandle(userHandle):
	tic = win32security.GetTokenInformation(userHandle, ntsecuritycon.TokenGroups)
	for sid, flags in tic:
		if flags & win32con.SE_GROUP_LOGON_ID:
			return sid
	return None


def getUserSid(username):
	username = forceUnicode(username)
	domain = getHostname()
	if "\\" in username:
		domain = username.split("\\")[0]
		username = username.split("\\")[-1]

	domain = domain.upper()
	return win32security.ConvertSidToStringSid(
		win32security.LookupAccountName(None, domain + "\\" + username)[0]
	)


def getAdminGroupName():
	subAuths = (
		ntsecuritycon.SECURITY_BUILTIN_DOMAIN_RID,
		ntsecuritycon.DOMAIN_ALIAS_RID_ADMINS,
	)
	sidAdmins = win32security.SID(ntsecuritycon.SECURITY_NT_AUTHORITY, subAuths)
	groupName = forceUnicode(win32security.LookupAccountSid(None, sidAdmins)[0])
	logger.info("Admin group name is '%s'", groupName)
	return groupName


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
		dt = datetime.strptime(timestring, "%Y-%m-%d %H:%M:%S.%f")
		logger.info("Setting Systemtime Time to %s", timestring)
		win32api.SetSystemTime(
			dt.year, dt.month, 0, dt.day, dt.hour, dt.minute, dt.second, 0
		)
	except Exception as err:
		logger.error("Failed to set System Time: '%s'", err)


class Impersonate:
	def __init__(self, username="", password="", userToken=None, desktop="default"):
		self.userProfile = None
		self.userEnvironment = None
		self.saveWindowStation = None
		self.saveDesktop = None
		self.newWindowStation = None
		self.newDesktop = None
		self.logonType = None

		if not username and not userToken:
			raise ValueError("Neither username nor user token given")

		self.domain = getHostname()
		self.username = forceUnicode(username)
		if "\\" in self.username:
			self.domain = self.username.split("\\")[0]
			self.username = self.username.split("\\")[-1]

		self.domain = self.domain.upper()
		self.password = forceUnicode(password)
		if not desktop:
			desktop = "default"

		if "\\" not in desktop:
			desktop = "winsta0\\" + desktop

		(self.winsta, self.desktop) = desktop.split("\\", 1)
		self.winsta = forceUnicodeLower(self.winsta)
		self.desktop = forceUnicodeLower(self.desktop)
		self.userToken = userToken

	def start(self, logonType="INTERACTIVE", newDesktop=False, createEnvironment=False):
		try:
			logonType = forceUnicode(logonType)
			winLogonType = None
			newDesktop = forceBool(newDesktop)
			if logonType == "NEW_CREDENTIALS":
				# Stay who you are but add credentials for network connections
				winLogonType = win32security.LOGON32_LOGON_NEW_CREDENTIALS
			elif logonType == "INTERACTIVE":
				winLogonType = win32con.LOGON32_LOGON_INTERACTIVE
			else:
				raise ValueError(f"Invalid logon type '{logonType}'")
			self.logonType = logonType

			if not self.userToken:
				# TODO: Use (UPN) format for username <USER>@<DOMAIN> ?
				logger.debug("Logon user: '%s\\%s'", self.domain, self.username)
				self.userToken = win32security.LogonUser(
					self.username,
					self.domain,
					self.password,
					winLogonType,
					win32con.LOGON32_PROVIDER_DEFAULT,
				)

			if newDesktop:
				self.saveWindowStation = win32service.GetProcessWindowStation()
				logger.debug("Got current window station")

				self.saveDesktop = win32service.GetThreadDesktop(
					win32api.GetCurrentThreadId()
				)
				logger.debug("Got current desktop")

				self.newWindowStation = win32service.OpenWindowStation(
					self.winsta, False, win32con.READ_CONTROL | win32con.WRITE_DAC
				)

				self.newWindowStation.SetProcessWindowStation()
				logger.debug("Process window station set")

				self.newDesktop = None
				if self.desktop not in ("default", "winlogon"):
					logger.info("Creating new desktop '%s'", self.desktop)
					try:
						self.newDesktop = createDesktop(self.desktop)
					except Exception as err:
						logger.warning(err)

				if not self.newDesktop:
					self.newDesktop = win32service.OpenDesktop(
						self.desktop,
						win32con.DF_ALLOWOTHERACCOUNTHOOK,
						True,
						win32con.READ_CONTROL
						| win32con.WRITE_DAC
						| win32con.DESKTOP_CREATEMENU
						| win32con.DESKTOP_CREATEWINDOW
						| win32con.DESKTOP_ENUMERATE
						| win32con.DESKTOP_HOOKCONTROL
						| win32con.DESKTOP_JOURNALPLAYBACK
						| win32con.DESKTOP_JOURNALRECORD
						| win32con.DESKTOP_READOBJECTS
						| win32con.DESKTOP_SWITCHDESKTOP
						| win32con.DESKTOP_WRITEOBJECTS,
					)

				self.newDesktop.SetThreadDesktop()
				logger.debug("Thread desktop set")

				userSid = getUserSidFromHandle(self.userToken)
				if not userSid:
					logger.warning(
						"Failed to determine sid of user '%s'", self.username
					)
				else:
					logger.debug("Got sid of user '%s'", self.username)

					addUserToWindowStation(self.newWindowStation, userSid)
					logger.debug("Added user to window station")

					addUserToDesktop(self.newDesktop, userSid)
					logger.debug("Added user to desktop")

			elif logonType == "INTERACTIVE":
				userSid = getUserSidFromHandle(self.userToken)
				if not userSid:
					logger.warning(
						"Failed to determine sid of user '%s'", self.username
					)
				else:
					logger.debug("Got sid of user '%s'", self.username)

					addUserToWindowStation(
						win32service.GetProcessWindowStation(), userSid
					)
					logger.debug("Added user to window station")

					addUserToDesktop(
						win32service.GetThreadDesktop(win32api.GetCurrentThreadId()),
						userSid,
					)
					logger.debug("Added user to desktop")

			if createEnvironment:
				self.userProfile = win32profile.LoadUserProfile(
					self.userToken, {"UserName": self.username}
				)
				logger.debug("User profile loaded")

				self.userEnvironment = win32profile.CreateEnvironmentBlock(
					self.userToken, False
				)
				logger.debug("Environment block created")

			win32security.ImpersonateLoggedOnUser(self.userToken)
			logger.debug("User impersonated")
		except Exception as err:
			logger.error(err, exc_info=True)
			self.end()
			raise

	def runCommand(
		self, command, waitForProcessEnding=True, timeoutSeconds=0, environment=None
	):
		command = forceUnicode(command)
		waitForProcessEnding = forceBool(waitForProcessEnding)
		timeoutSeconds = forceInt(timeoutSeconds)
		if not environment:
			environment = self.userEnvironment

		dwCreationFlags = win32process.CREATE_NEW_CONSOLE
		sti = win32process.STARTUPINFO()
		sti.dwFlags = win32process.STARTF_USESHOWWINDOW ^ win32con.STARTF_USESTDHANDLES
		sti.wShowWindow = win32con.SW_NORMAL
		sti.lpDesktop = self.winsta + "\\" + self.desktop

		if self.logonType == "INTERACTIVE":
			logger.notice(
				"Running command '%s' as user '%s' on desktop '%s'",
				command,
				self.username,
				self.desktop,
			)
		else:
			logger.notice(
				"Running command '%s' on desktop '%s', using network credentials of user '%s'",
				command,
				self.desktop,
				self.username,
			)
		(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(
			self.userToken,
			None,
			command,
			None,
			None,
			0,
			dwCreationFlags,
			environment,
			None,
			sti,
		)

		logger.info("Process startet, pid: %s", dwProcessId)
		if not waitForProcessEnding:
			return (hProcess, hThread, dwProcessId, dwThreadId)

		logger.info(
			"Waiting for process ending: %s (timeout: %s seconds)",
			dwProcessId,
			timeoutSeconds,
		)
		sec = 0.0
		while win32event.WaitForSingleObject(hProcess, timeoutSeconds):
			if timeoutSeconds > 0:
				if sec >= timeoutSeconds:
					terminateProcess(processId=dwProcessId)
					raise RuntimeError(
						f"Timed out after {sec} seconds while waiting for process {dwProcessId}"
					)
				sec += 0.1
			time.sleep(0.1)

		exitCode = win32process.GetExitCodeProcess(hProcess)
		logger.notice("Process %s ended with exit code %s", dwProcessId, exitCode)
		return (None, None, None, None)

	def end(self):
		try:
			try:
				win32security.RevertToSelf()
			except Exception:
				pass
			if self.saveWindowStation:
				try:
					self.saveWindowStation.SetProcessWindowStation()
				except Exception as err:
					logger.debug("Failed to set process WindowStation: %s", err)

			if self.saveDesktop:
				try:
					self.saveDesktop.SetThreadDesktop()
				except Exception as err:
					logger.debug("Failed to set thread Desktop: %s", err)

			if self.newDesktop:
				try:
					self.newWindowStation.CloseDesktop()
				except Exception as err:
					logger.debug("Failed to close Desktop: %s", err)

			if self.newWindowStation:
				try:
					self.newWindowStation.CloseWindowStation()
				except Exception as err:
					logger.debug("Failed to close WindowStation: %s", err)

			if self.userProfile:
				logger.debug("Unloading user profile")
				try:
					win32profile.UnloadUserProfile(self.userToken, self.userProfile)
				except Exception as err:
					logger.debug("Failed to unload user profile: %s", err)

			if self.userToken:
				try:
					self.userToken.Close()
				except Exception as err:
					logger.debug("Failed to close user token: %s", err)
		except Exception as err:
			logger.error(err, exc_info=True)

	def __del__(self):
		self.end()
