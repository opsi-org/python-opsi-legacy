#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
opsi python library - Windows

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2013 uib GmbH

http://www.uib.de/

All rights reserved.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License, version 3
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Affero General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

@copyright: uib GmbH <info@uib.de>
@author: Jan Schneider <j.schneider@uib.de>
@author: Erol Ueluekmen <e.ueluekmen@uib.de>
@license: GNU Affero GPL version 3
"""

__version__ = '4.0.4.4'

# Imports
import re, os, time, socket, sys, locale, subprocess, difflib, threading

# Win32 imports
from ctypes import *
from datetime import datetime
import pywintypes, ntsecuritycon, win32service, win32event, win32con, win32ts, win32process, win32file
import win32api, win32security, win32gui, win32net, win32wnet, win32netcon, _winreg
import win32pdhutil, win32pdh, win32pipe, msvcrt
import win32profile

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *

# Get Logger instance
logger = Logger()

# Constants
HKEY_CURRENT_USER = _winreg.HKEY_CURRENT_USER
HKEY_LOCAL_MACHINE = _winreg.HKEY_LOCAL_MACHINE

TH32CS_SNAPPROCESS = 0x00000002
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
		("szExeFile", c_char * 260)
	]

MAX_INTERFACE_NAME_LEN = 256
MAXLEN_IFDESCR = 256
MAXLEN_PHYSADDR = 8
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

MAX_INTERFACES = 32
class MIB_IFTABLE(Structure):
	_fields_ = [
		("dwNumEntries", c_uint),
		("table", MIB_IFROW * MAX_INTERFACES),
	]

class SystemSpecificHook(object):
	def __init__(self):
		pass

hooks = []
def addSystemHook(hook):
	global hooks
	if not hook in hooks:
		hooks.append(hook)

def removeSystemHook(hook):
	global hooks
	if hook in hooks:
		hooks.remove(hook)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                               INFO                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getArchitecture():
	try:
		if win32process.IsWow64Process():
			return u'x64'
		else:
			return u'x86'
	except Exception as e:
		logger.error("Error by determining OS-Architecture: '%s'; returning default: 'x86'")

def getOpsiHotfixName(helper = None):
	arch = getArchitecture()
	major = sys.getwindowsversion()[0]
	minor = sys.getwindowsversion()[1]
	os = u'unknown'
	lang = u'unknown'

	if (major == 5):
		loc = locale.getdefaultlocale()[0].split('_')[0]
		if   (loc == 'en'): lang = u'enu'
		elif (loc == 'de'): lang = u'deu'
		elif (loc == 'fr'): lang = u'fra'
		elif (loc == 'it'): lang = u'ita'
		elif (loc == 'ch'): lang = u'chs'
		if (minor == 1):
			os = u'winxp'
		elif (minor == 2):
			if (arch == 'x86'):
				os = u'win2003'
			else:
				os = u'win2003-winxp'
	elif (major == 6):
		lang = u'glb'
		if helper:
			try:
				result = execute(helper, shell=False)
				minor = int(result[0].split(".")[1])
			except:
				logger.warning(u"MSHotfix fix for Windows 8.1 don't work. Fallback to normal mode.")
		if (minor == 0):
			os = u'vista-win2008'
		elif (minor == 1):
			if (arch == 'x86'):
				os = u'win7'
			else:
				os = u'win7-win2008r2'
		elif (minor == 2):
			if (arch == 'x86'):
				os = u'win8'
			else:
				os = u'win8-win2012'
		elif (minor == 3):
			if (arch == 'x86'):
				os = u'win81'
			else:
				os = u'win81-win2012r2'

	return u'mshotfix-%s-%s-%s' % (os, arch, lang)

def getHostname():
	return forceUnicodeLower(win32api.GetComputerName())

def getFQDN():
	fqdn = socket.getfqdn().lower()
	if ( len(fqdn.split(u'.')) < 2 ):
		return getHostname()
	return forceUnicodeLower(getHostname() + u'.' + u'.'.join(fqdn.split(u'.')[1:]))

def getFileVersionInfo(filename):
	filename = forceFilename(filename)
	(lang, codepage) = win32api.GetFileVersionInfo(filename, u'\\VarFileInfo\\Translation')[0]
	path = u'\\StringFileInfo\\%04X%04X\\%%s' % (lang, codepage)
	info = {
		'CompanyName':      forceUnicode(win32api.GetFileVersionInfo(filename, path % 'CompanyName')),
		'SpecialBuild':     forceUnicode(win32api.GetFileVersionInfo(filename, path % 'SpecialBuild')),
		'Comments':         forceUnicode(win32api.GetFileVersionInfo(filename, path % 'Comments')),
		'FileDescription':  forceUnicode(win32api.GetFileVersionInfo(filename, path % 'FileDescription')),
		'FileVersion':      forceUnicode(win32api.GetFileVersionInfo(filename, path % 'FileVersion')),
		'InternalName':     forceUnicode(win32api.GetFileVersionInfo(filename, path % 'InternalName')),
		'LegalCopyright':   forceUnicode(win32api.GetFileVersionInfo(filename, path % 'LegalCopyright')),
		'LegalTrademarks':  forceUnicode(win32api.GetFileVersionInfo(filename, path % 'LegalTrademarks')),
		'OriginalFilename': forceUnicode(win32api.GetFileVersionInfo(filename, path % 'OriginalFilename')),
		'PrivateBuild':     forceUnicode(win32api.GetFileVersionInfo(filename, path % 'PrivateBuild')),
		'ProductName':      forceUnicode(win32api.GetFileVersionInfo(filename, path % 'ProductName')),
		'ProductVersion':   forceUnicode(win32api.GetFileVersionInfo(filename, path % 'ProductVersion'))
	}
	logger.debug(u"File version info for '%s': %s" % (filename, info))
	return info

def getProgramFilesDir():
	return getRegistryValue(HKEY_LOCAL_MACHINE, u'Software\\Microsoft\\Windows\\CurrentVersion', u'ProgramFilesDir')

def getSystemDrive():
	return forceUnicode(os.getenv('SystemDrive', u'c:'))

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
			("next",      LP_IP_ADDR_STRING),
			("ipAddress", c_char * 16),
			("ipMask",    c_char * 16),
			("context",   c_ulong)]
		class IP_ADAPTER_INFO(Structure):
			pass
		LP_IP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
		IP_ADAPTER_INFO._fields_ = [
			("next",                LP_IP_ADAPTER_INFO),
			("comboIndex",          c_ulong),
			("adapterName",         c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
			("description",         c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
			("addressLength",       c_uint),
			("address",             c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
			("index",               c_ulong),
			("type",                c_uint),
			("dhcpEnabled",         c_uint),
			("currentIpAddress",    LP_IP_ADDR_STRING),
			("ipAddressList",       IP_ADDR_STRING),
			("gatewayList",         IP_ADDR_STRING),
			("dhcpServer",          IP_ADDR_STRING),
			("haveWins",            c_uint),
			("primaryWinsServer",   IP_ADDR_STRING),
			("secondaryWinsServer", IP_ADDR_STRING),
			("leaseObtained",       c_ulong),
			("leaseExpires",        c_ulong)
		]
		GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
		GetAdaptersInfo.restype = c_ulong
		GetAdaptersInfo.argtypes = [LP_IP_ADAPTER_INFO, POINTER(c_ulong)]
		adapterList = (IP_ADAPTER_INFO * 10)()
		buflen = c_ulong(sizeof(adapterList))
		rc = GetAdaptersInfo(byref(adapterList[0]), byref(buflen))
		return adapterList
	except Exception as e:
		logger.logException(e)
		raise Exception(u"Failed to get network interfaces: %s" % forceUnicode(e))


def getDefaultNetworkInterfaceName():
	for interface in getNetworkInterfaces():
		if interface.gatewayList.ipAddress:
			return interface.description
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
		if (iftable.dwNumEntries <= 0):
			raise Exception(u"No network interfaces found while searching for interface '%s'" % interface)

		for i in range(iftable.dwNumEntries):
			ratio = difflib.SequenceMatcher(None, iftable.table[i].bDescr, interface).ratio()
			logger.info(u"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s" % (interface, iftable.table[i].bDescr, ratio))
			if (ratio > bestRatio):
				bestRatio = ratio
				self.interface = iftable.table[i].bDescr
		if not self.interface:
			raise Exception(u"Network interface '%s' not found" % interface)

		logger.info(u"NetworkPerformanceCounter: using interface '%s' match ratio (%s)" % (self.interface, bestRatio))
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
		(bytesIn, bytesOut) = (0, 0)
		iftable = MIB_IFTABLE()
		iftable_size = c_ulong(sizeof(iftable))
		iftable.dwNumEntries = 0
		windll.iphlpapi.GetIfTable(byref(iftable), byref(iftable_size), 0)
		for i in range(iftable.dwNumEntries):
			if (iftable.table[i].bDescr == self.interface):
				bytesIn = iftable.table[i].dwInOctets
				bytesOut = iftable.table[i].dwOutOctets
				break
		timeDiff = 1
		if self._lastTime:
			timeDiff = now - self._lastTime
		if self._lastBytesIn:
			self._bytesInPerSecond = (bytesIn - self._lastBytesIn)/timeDiff
			if (self._bytesInPerSecond < 0):
				self._bytesInPerSecond = 0
		if self._lastBytesOut:
			self._bytesOutPerSecond = (bytesOut - self._lastBytesOut)/timeDiff
			if (self._bytesOutPerSecond < 0):
				self._bytesOutPerSecond = 0
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
		self.start()

	def __del__(self):
		self.stop()

	def stop(self):
		self._stopped = True

	def run(self):
		try:
			interface = self.interface
			self._running = True
			import pythoncom, wmi
			pythoncom.CoInitialize()
			self.wmi = wmi.WMI()
			bestRatio = 0.0
			for instance in self.wmi.Win32_PerfRawData_Tcpip_NetworkInterface():
				ratio = difflib.SequenceMatcher(None, instance.Name, interface).ratio()
				logger.info(u"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s" % (interface, instance.Name, ratio))
				if (ratio > bestRatio):
					bestRatio = ratio
					self.interface = instance.Name
			logger.info(u"NetworkPerformanceCounter: using interface '%s' match ratio (%s)" % (self.interface, bestRatio))
		except Exception as e:
			logger.logException(e)
		try:
			while not self._stopped:
				self._getStatistics()
				time.sleep(1)
		finally:
			try:
				import pythoncom
				pythoncom.CoUninitialize()
			except:
				pass

	def _getStatistics(self):
		now = time.time()
		for instance in self.wmi.Win32_PerfRawData_Tcpip_NetworkInterface(["BytesReceivedPersec", "BytesSentPersec"], Name = self.interface):
			bytesIn = instance.BytesReceivedPersec
			bytesOut = instance.BytesSentPersec
		timeDiff = 1
		if self._lastTime:
			timeDiff = now - self._lastTime
		if self._lastBytesIn:
			self._bytesInPerSecond = (bytesIn - self._lastBytesIn)/timeDiff
			if (self._bytesInPerSecond < 0):
				self._bytesInPerSecond = 0
		if self._lastBytesOut:
			self._bytesOutPerSecond = (bytesOut - self._lastBytesOut)/timeDiff
			if (self._bytesOutPerSecond < 0):
				self._bytesOutPerSecond = 0
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
						win32pdhutil.find_pdh_counter_localized_name('Network Interface'),
						win32pdh.PERF_DETAIL_WIZARD)
		bestRatio = 0.0
		for instance in instances:
			ratio = difflib.SequenceMatcher(None, instance, interface).ratio()
			logger.info(u"NetworkPerformanceCounter: searching for interface '%s', got interface '%s', match ratio: %s" % (interface, instance, ratio))
			if (ratio > bestRatio):
				bestRatio = ratio
				self.interface = instance
		logger.info(u"NetworkPerformanceCounter: using interface '%s' match ratio (%s) with available counters: %s" % (self.interface, bestRatio, items))

		# For correct translations (find_pdh_counter_localized_name) see:
		# HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib
		self._queryHandle = win32pdh.OpenQuery()
		self.bytesInPerSecondCounter = win32pdh.MakeCounterPath( (
						None,
						win32pdhutil.find_pdh_counter_localized_name('Network Interface'),
						self.interface,
						None,
						-1,
						win32pdhutil.find_pdh_counter_localized_name('Bytes In/sec') ) )
		self.bytesOutPerSecondCounter = win32pdh.MakeCounterPath( (
						None,
						win32pdhutil.find_pdh_counter_localized_name('Network Interface'),
						self.interface,
						None,
						-1,
						win32pdhutil.find_pdh_counter_localized_name('Bytes Sent/sec') ) )
		try:
			self._inCounterHandle = win32pdh.AddCounter(self._queryHandle, self.bytesInPerSecondCounter)
		except Exception as e:
			raise Exception(u"Failed to add inCounterHandle %s->%s: %s" % (
				win32pdhutil.find_pdh_counter_localized_name('Network Interface'),
				win32pdhutil.find_pdh_counter_localized_name('Bytes In/sec'),
				e
			))
		try:
			self._outCounterHandle = win32pdh.AddCounter(self._queryHandle, self.bytesOutPerSecondCounter)
		except Exception as e:
			raise Exception(u"Failed to add outCounterHandle %s->%s: %s" % (
				win32pdhutil.find_pdh_counter_localized_name('Network Interface'),
				win32pdhutil.find_pdh_counter_localized_name('Bytes Sent/sec'),
				e
			))
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
			for i in range(10):
				win32pdh.CollectQueryData(self._queryHandle)
				(tp, val) = win32pdh.GetFormattedCounterValue(self._inCounterHandle, win32pdh.PDH_FMT_LONG)
				inbytes += val
				(tp, val) = win32pdh.GetFormattedCounterValue(self._outCounterHandle, win32pdh.PDH_FMT_LONG)
				outbytes += val
				time.sleep(0.1)
			self._bytesInPerSecond = inbytes/10.0
			self._bytesOutPerSecond = outbytes/10.0
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
	logger.debug2(u"copyACL: ace count is %s" % src.GetAceCount())
	for i in range(src.GetAceCount()):
		logger.debug2(u"copyACL: processing ace #%s" % i)
		ace = src.GetAce(i)
		logger.debug2(u"copyACL: ace: %s" % str(ace))
		# XXX: Not sure if these are actually correct.
		# See http://aspn.activestate.com/ASPN/docs/ActivePython/2.4/pywin32/PyACL__GetAce_meth.html
		if   (ace[0][0] == win32con.ACCESS_ALLOWED_ACE_TYPE):
			dest.AddAccessAllowedAce(revision, ace[1], ace[2])
		elif (ace[0][0] == win32con.ACCESS_DENIED_ACE_TYPE):
			dest.AddAccessDeniedAce(revision, ace[1], ace[2])
		elif (ace[0][0] == win32con.SYSTEM_AUDIT_ACE_TYPE):
			dest.AddAuditAccessAce(revision, ace[1], ace[2], 1, 1)
		elif (ace[0][0] == win32con.ACCESS_ALLOWED_OBJECT_ACE_TYPE):
			dest.AddAccessAllowedObjectAce(revision, ace[0][1], ace[1], ace[2], ace[3], ace[4])
		elif (ace[0][0] == win32con.ACCESS_DENIED_OBJECT_ACE_TYPE):
			dest.AddAccessDeniedObjectAce(revision, ace[0][1], ace[1], ace[2], ace[3], ace[4])
		elif (ace[0][0] == win32con.SYSTEM_AUDIT_OBJECT_ACE_TYPE):
			dest.AddAuditAccessObjectAce(revision, ace[0][1], ace[1], ace[2], ace[3], ace[4], 1, 1)
	return src.GetAceCount()

def adjustPrivilege(priv, enable = 1):
	# Get the process token.
	flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
	htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
	# Get the ID for the system shutdown privilege.
	id = win32security.LookupPrivilegeValue(None, priv)
	# Now obtain the privilege for this process.
	# Create a list of the privileges to be added.
	if enable:
		newPrivileges = [(id, win32security.SE_PRIVILEGE_ENABLED)]
	else:
		newPrivileges = [(id, 0)]
	# and make the adjustment.
	win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                             REGISTRY                                              -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getRegistryValue(key, subKey, valueName, reflection=True):
	hkey = _winreg.OpenKey(key, subKey)
	if not reflection and (getArchitecture() == 'x64'):
		_winreg.DisableReflectionKey(hkey)
	(value, type) = _winreg.QueryValueEx(hkey, valueName)
	if (getArchitecture() == 'x64') and not reflection:
		if _winreg.QueryReflectionKey(hkey):
			_winreg.EnableReflectionKey(hkey)
	return value

def setRegistryValue(key, subKey, valueName, value):
	_winreg.CreateKey(key, subKey)
	hkey = _winreg.OpenKey(key, subKey, 0, _winreg.KEY_WRITE)
	if type(value) is int:
		_winreg.SetValueEx(hkey, valueName, 0, _winreg.REG_DWORD, value)
	else:
		_winreg.SetValueEx(hkey, valueName, 0, _winreg.REG_SZ, value)

def createRegistryKey(key, subKey):
	_winreg.CreateKey(key, subKey)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            FILESYSTEMS                                            -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def getFreeDrive(startLetter = 'a'):
	startLetter = forceUnicodeLower(startLetter)
	startLetterSeen = False
	for letter in ('a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z'):
		if (startLetter == letter):
			startLetterSeen = True
		if not startLetterSeen:
			continue
		letter += ':'
		if (win32file.GetDriveType(letter) == 1):
			return letter
	raise Exception(u'No free drive available')

def getDiskSpaceUsage(path):
	path = forceUnicode(path)
	if (len(path) == 1):
		path = path + ':'
	info = {
		'capacity':  0,
		'available': 0,
		'used':      0,
		'usage':     0
	}
	#(items, instances) = win32pdh.EnumObjectItems(
	#			None,
	#			None,
	#			win32pdhutil.find_pdh_counter_localized_name('LogicalDisk'),
	#			win32pdh.PERF_DETAIL_WIZARD)
	#
	#for instance in instances:
	#	if path.lower().startswith(instance.lower()):
	(sectPerCluster, bytesPerSector, freeClusters, totalClusters) = win32file.GetDiskFreeSpace(path)
	info['capacity'] = totalClusters * sectPerCluster * bytesPerSector
	info['available'] = freeClusters * sectPerCluster * bytesPerSector
	info['used'] = info['capacity'] - info['available']
	info['usage'] = float(info['used']) / float(info['capacity'])
	#break

	logger.info(u"Disk space usage for path '%s': %s" % (path, info))
	return info

def mount(dev, mountpoint, **options):
	dev = forceUnicode(dev)
	mountpoint = forceUnicode(mountpoint)

	fs = u''

	match = re.search('^[a-zA-Z]:$', mountpoint)
	if not match:
		logger.error(u"Bad mountpoint '%s'" % mountpoint)
		raise ValueError(u"Bad mountpoint '%s'" % mountpoint)

	if dev.lower().startswith('smb://') or dev.lower().startswith('cifs://'):
		match = re.search('^(smb|cifs)://([^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			parts = match.group(2).split('/')
			dev = u'\\\\%s\\%s' % (parts[0], parts[1])

			if not 'username' in options:
				options['username'] = None

			elif options['username'] and (options['username'].find(u'\\') != -1):
				options['domain'] = options['username'].split(u'\\')[0]
				options['username'] = options['username'].split(u'\\')[-1]

			if not 'password' in options:
				options['password'] = None
			else:
				logger.addConfidentialString(options['password'])

			if not 'domain' in options:
				options['domain'] = getHostname()
			username = None
			if options['username']:
				username = options['domain'] + u'\\' + options['username']

			try:
				try:
					# Remove connection and update user profile (remove persistent connection)
					win32wnet.WNetCancelConnection2(mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True)
				except pywintypes.error as details:
					if (details[0] == 2250):
						# Not connected
						logger.debug(u"Failed to umount '%s': %s" % (mountpoint, details))
					else:
						raise

				logger.notice(u"Mounting '%s' to '%s'" % (dev, mountpoint))
				# Mount not persistent
				win32wnet.WNetAddConnection2(
					win32netcon.RESOURCETYPE_DISK,
					mountpoint,
					dev,
					None,
					username,
					options['password'],
					0
				)

			except Exception as e:
				logger.error(u"Failed to mount '%s': %s" % (dev, forceUnicode(e)))
				raise Exception(u"Failed to mount '%s': %s" % (dev, forceUnicode(e)))
		else:
			raise Exception(u"Bad smb/cifs uri '%s'" % dev)

	else:
		raise Exception(u"Cannot mount unknown fs type '%s'" % dev)

def umount(mountpoint):
	try:
		# Remove connection and update user profile (remove persistent connection)
		win32wnet.WNetCancelConnection2(mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True)
	except pywintypes.error as details:
		if (details[0] == 2250):
			# Not connected
			logger.warning(u"Failed to umount '%s': %s" % (mountpoint, details))
		else:
			raise

	except Exception as e:
		logger.error(u"Failed to umount '%s': %s" % (mountpoint, forceUnicode(e)))
		raise Exception (u"Failed to umount '%s': %s" % (mountpoint, forceUnicode(e)))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                               SESSION / WINSTA / DESKTOP HANDLING                                 -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getActiveConsoleSessionId():
	try:
		return forceInt(windll.kernel32.WTSGetActiveConsoleSessionId())
	except Exception as e:
		logger.warning(u"Failed to get WTSGetActiveConsoleSessionId: %s, returning 0" % forceUnicode(e))
		return 0

def getActiveDesktopName():
	desktop = win32service.OpenInputDesktop(0, True, win32con.MAXIMUM_ALLOWED)
	return forceUnicode(win32service.GetUserObjectInformation(desktop, win32con.UOI_NAME))

def getActiveSessionIds(winApiBugCommand = None):
	sessionIds = []
	logger.debug(u"Getting active sessions")
	if sys.getwindowsversion()[0] == 5 and getArchitecture() == "x64":
		logger.debug(u"Using Workarround for problems with buggy winapi from nt5 x64")
		try:
			result = execute(winApiBugCommand, shell=False)
			sessionIds = forceList(eval(result[0]))
			logger.debug(u"   Found sessionIds: %s" % sessionIds)
		except Exception,e:
			logger.debug("Working directory: '%s', scriptdirectory: '%s'" % (os.getcwd(),sys.path[0]))
			logger.logException(e)
	else:
		for s in win32security.LsaEnumerateLogonSessions():
			sessionData = win32security.LsaGetLogonSessionData(s)
			if not forceInt(sessionData['LogonType']) in (2, 10) or sessionData['LogonDomain'] == u'Window Manager':
				continue
			sessionId = forceInt(sessionData['Session'])
			if (sessionId == 0) and (sys.getwindowsversion()[0] >= 6):
				# Service session
				continue
			logger.debug(u"   Found session: %s" % sessionData)
			if not sessionId in sessionIds:
				sessionIds.append(sessionId)
	return sessionIds

def getActiveSessionId(verifyProcessRunning = "winlogon.exe", winApiBugCommand = None):
	logger.debug("Getting ActiveSessionId")
	defaultSessionId = getActiveConsoleSessionId()
	if (sys.getwindowsversion()[0] >= 6) and (defaultSessionId == 0):
		defaultSessionId = 1
	sessionIds = []
	newest = None
	if sys.getwindowsversion()[0] == 5 and getArchitecture() == "x64":
		logger.debug(u"Using Workarround for problems with buggy winapi from nt5 x64")
		try:
			result = execute(winApiBugCommand, shell=False)
			logger.debug(u"   Found sessionIds: %s" % eval(result[0]))
			for sessionId in forceList(eval(result[0])):
				res = execute("%s %s" % (winApiBugCommand,sessionId), shell=False)
				sessionData = forceDict(eval(res[0]))
				if verifyProcessRunning and not getPids(verifyProcessRunning, sessionId = sessionId):
					continue

				if not sessionId in sessionIds:
					sessionIds.append(sessionId)
				if newest:
					try:
						if not newest:
							newest = sessionData
							continue
						lt = newest['LogonTime']
						lts = sessionData['LogonTime']
						newestdt = datetime(lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second)
						sessiondt = datetime(lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second)
						if sessiondt > newestdt:
							logger.notice("Token in SessionData is newer then the cached one.")
							newest = sessionData
					except Exception as e:
						logger.warning(e)
						if (forceInt(sessionData['LogonId']) > forceInt(newest['LogonId'])):
							newest = sessionData
				else:
					newest = sessionData
		except Exception,e:
			logger.debug("Working directory: '%s', scriptdirectory: '%s'" % (os.getcwd(),sys.path[0]))
			logger.logException(e)
	else:
		for s in win32security.LsaEnumerateLogonSessions():
			sessionData = win32security.LsaGetLogonSessionData(s)
			if not forceInt(sessionData['LogonType']) in (2, 10):
				continue
			sessionId = forceInt(sessionData['Session'])
			if (sessionId == 0) and (sys.getwindowsversion()[0] >= 6):
				# Service session
				continue

			logger.debug(u"   Found session: %s" % sessionData)

			if verifyProcessRunning and not getPids(verifyProcessRunning, sessionId = sessionId):
				continue

			if not sessionId in sessionIds:
				sessionIds.append(sessionId)
			if newest:
				try:
					if not newest:
						newest = sessionData
						continue
					lt = newest['LogonTime']
					lts = sessionData['LogonTime']
					newestdt = datetime(lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second)
					sessiondt = datetime(lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second)
					if sessiondt > newestdt:
						logger.notice("Token in SessionData is newer then the cached one.")
						newest = sessionData
				except Exception as e:
					logger.warning(e)
					if (forceInt(sessionData['LogonId']) > forceInt(newest['LogonId'])):
							newest = sessionData
			else:
				newest = sessionData
	if (len(sessionIds) == 0):
		return defaultSessionId
	if newest:
		return forceInt(newest['Session'])
	if defaultSessionId in sessionIds:
		return defaultSessionId
	if (sys.getwindowsversion()[0]>= 6) and (sessionIds[0] == 0):
		if (len(sessionIds) > 1):
			return sessionIds[1]
		return defaultSessionId
	return sessionIds[0]

def getSessionInformation(sessionId, winApiBugCommand = None):
	#info = {}
	#for infoClass in ('WTSUserName', 'WTSApplicationName', 'WTSClientDirectory', 'WTSClientName', 'WTSDomainName', 'WTSInitialProgram',
	#                  'WTSOEMId', 'WTSUserName', 'WTSWinStationName', 'WTSWorkingDirectory', 'WTSClientProtocolType', 'WTSClientProductId',
	#                  'WTSClientBuildNumber', 'WTSClientHardwareId', 'WTSSessionId', 'WTSConnectState', 'WTSClientDisplay', 'WTSClientAddress'):
	#	try:
	#		info[infoClass] = win32ts.WTSQuerySessionInformation(None, sessionId, eval('win32ts.%s' % infoClass))
	#	except Exception, e:
	#		info[infoClass] = None
	#		logger.debug(e)
	#return info
	wtsUserName = None
	try:
		wtsUserName = win32ts.WTSQuerySessionInformation(None, sessionId, win32ts.WTSUserName)
	except:
		pass
	"""
	'UserName': u'Administrator',
	'AuthenticationPackage': u'NTLM',
	'LogonServer': u'COMPUTERNAME',
	'LogonId': 1753269L,
	'Upn': u'',
	'Session': 1,
	'DnsDomainName': u'',
	'Sid': <PySID object at 0x00CD7BA8>,
	'LogonType': 10,
	'LogonDomain': u'COMPUTERNAME',
	'LogonTime': <PyTime:19.04.2010 16:33:07>}
	"""
	if sys.getwindowsversion()[0] == 5 and getArchitecture() == "x64":
		logger.debug(u"Using Workarround for problems with buggy winapi from nt5 x64")
		try:
			result = execute("%s %s" % (winApiBugCommand,sessionId), shell=False)
			sessionData = forceDict(eval(result[0]))
			if sessionData:
				try:
					if wtsUserName and not sessionData['UserName'].lower() ==  wtsUserName.lower():
						sessionData['UserName'] = wtsUserName
				except:
					pass
				logger.debug(u"   Found session: %s" % sessionData)
				return sessionData
		except Exception,e:
			logger.debug("Working directory: '%s', scriptdirectory: '%s'" % (os.getcwd(),sys.path[0]))
			logger.logException(e)
	newest = None
	for s in win32security.LsaEnumerateLogonSessions():
		sessionData = win32security.LsaGetLogonSessionData(s)

		if (forceInt(sessionData['Session']) == forceInt(sessionId)):
			logger.debug("Session is found and checked. wtsUserName: '%s'" % wtsUserName)
			if wtsUserName and sessionData['UserName'].lower() != wtsUserName.lower():
				continue
			logger.debug(u"sessionData: '%s', wtsUserName: '%s'" % (sessionData['UserName'], wtsUserName))
			try:
				if not newest:
					logger.debug("No newest object found, so newest is Session with ID: '%s'" % sessionData['Session'])
					newest = sessionData
					continue
				lt = newest['LogonTime']
				lts = sessionData['LogonTime']
				newestdt = datetime(lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second)
				sessiondt = datetime(lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second)
				logger.debug("newest datetime: '%s'" % lt)
				logger.debug("newest datetime in session: '%s'" % lts)
				logger.debug("newest datetime timestamp: '%s'" % newestdt.timestamp())
				logger.debug("newest datetime in session timestamp: '%s'" % sessiondt.timestamp())
				if sessiondt > newestdt:
					logger.notice("Token in SessionData is newer then the cached one.")
					newest = sessionData
			except Exception as e:
				logger.warning("WARNING in getSessionInformation method: '%s'" % e)
				if (forceInt(sessionData['LogonId']) > forceInt(newest['LogonId'])):
					newest = sessionData
			else:
				newest = sessionData

	if newest:
		logger.debug("Found newest SessionId: '%s' for User: '%s'" % (newest['Session'], newest['UserName']))
		return newest
	elif sessionData:
		logger.debug("Found newest SessionId: '%s' for User: '%s'" % (sessionData['Session'], sessionData['UserName']))
		return sessionData
	else:
		return {}

def getActiveSessionInformation(winApiBugCommand = None):
	info = []
	for sessionId in getActiveSessionIds(winApiBugCommand):
		logger.debug("sessionid info: %s" % sessionId)
		sessionInfo = getSessionInformation(sessionId, winApiBugCommand)
		if info and sessionInfo:
			for item in info:
				if item['UserName'].lower() == sessionInfo['UserName'].lower():
					logger.debug("Duplicate Session Found, trying to figure out, which one is the newest.")
					lt = item['LogonTime']
					lts = sessionInfo['LogonTime']
					logger.debug2("lt '%s'" % lt)
					logger.debug2("lt: year: '%s', month: '%s', day: '%s', hour: '%s', minute: '%s', second: '%s'" % (lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second))
					logger.debug2("lts '%s'" % lts)
					logger.debug2("lts: year: '%s', month: '%s', day: '%s', hour: '%s', minute: '%s', second: '%s'" % (lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second))
					logger.debug2("lt-type '%s'" % type(lt))
					logger.debug2("lts-type '%s'" % type(lts))
					infodt = datetime.datetime(lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second)
					sessiondt = datetime.datetime(lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second)
					if sessiondt > infodt:
						logger.notice("Token in SessionData is newer then the cached one.")
						info.remove(item)
						info.append(sessionInfo)
		elif sessionInfo:
			info.append(sessionInfo)
		#info.append(getSessionInformation(sessionId, winApiBugCommand))
	logger.debug(u"info: '%s'" % info)
	return info

def getUserSessionIds(username, winApiBugCommand = None, onlyNewestId = None):
	sessionIds = []
	if not username:
		return sessionIds
	domain = None
	newest = None
	logger.debug(u"Getting sessions of user '%s'" % username)
	if (username.find('\\') != -1):
		domain = username.split('\\')[0]
		username = username.split('\\')[-1]
	for session in getActiveSessionInformation(winApiBugCommand):
		#if ( session.get('WTSUserName') and (session.get('WTSUserName').lower() == username.lower()) and \
		#     (not domain or (session.get('WTSDomainName') and (session.get('WTSDomainName').lower() == domain.lower()))) ):
		#	sessionIds.append(session.get('WTSSessionId'))
		#	logger.debug(u"   Found session id of user '%s': %s" % (username, session.get('WTSSessionId')))
		if ( session.get('UserName') and (session.get('UserName').lower() == username.lower()) and \
		     (not domain or (session.get('LogonDomain') and (session.get('LogonDomain').lower() == domain.lower()))) ):
			sessionIds.append(forceInt(session.get('Session')))
			if onlyNewestId:
				try:
					if not newest:
						newest = session
						continue
					lt = newest['LogonTime']
					lts = session['LogonTime']

					newestdt = datetime(lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second)
					sessiondt = datetime(lts.year, lts.month, lts.day, lts.hour, lts.minute, lts.second)
					if sessiondt > newestdt:
						logger.notice("Token in SessionData is newer then the cached one.")
						newest = sessionData
				except Exception as e:
					logger.warning(e)
					if (forceInt(session['LogonId']) > forceInt(newest['LogonId'])):
						newest = session
				else:
					newest = session
			logger.debug(u"   onlyNewestId: '%s' newest = '%s'" % (onlyNewestId, newest))
			logger.debug(u"   Found session id of user '%s': %s" % (username, session.get('Session')))
	if onlyNewestId and newest:
		return [ newest.get('Session') ]
	else:
		return sessionIds

def logoffCurrentUser():
	logger.notice("Logging off current user")
	#win32api.ExitWindows()
	#win32api.ExitWindowsEx(0)
	## Windows Server 2008 and Windows Vista:  A call to WTSShutdownSystem does not work when Remote Connection Manager (RCM) is disabled. This is the case when the Terminal Services service is stopped.
	#win32ts.WTSShutdownSystem(win32ts.WTS_CURRENT_SERVER_HANDLE, win32ts.WTS_WSD_LOGOFF)
	command = ''
	if (sys.getwindowsversion()[0] == 5):
		if (sys.getwindowsversion()[1] == 0):
			# NT5.0: win2k
			raise NotImplemented(u"Not available on win2k")
		else:
			# NT5.1: XP
			command = u'logoff.exe'
	elif (sys.getwindowsversion()[0] == 6):
		# NT6: Vista, Win7
		command = u'shutdown.exe /l'
	else:
		raise Exception(u"Operating system not supported")
	runCommandInSession(
			command              = command,
			sessionId            = getActiveSessionId(),
			waitForProcessEnding = False )

def lockWorkstation():
	#windll.winsta.WinStationConnectW(0, 0, sessionId, "", 0)
	#windll.user32.LockWorkStation()
	runCommandInSession(
			command              = u"rundll32.exe user32.dll,LockWorkStation",
			sessionId            = getActiveSessionId(),
			waitForProcessEnding = False )

def reboot(wait=10):
	logger.notice(u"Rebooting in %s seconds" % wait)
	wait = forceInt(wait)
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, u"Opsi reboot", wait, True, True)

def shutdown(wait=10):
	logger.notice(u"Shutting down in %s seconds" % wait)
	wait = forceInt(wait)
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, u"Opsi shutdown", wait, True, False)

def abortShutdown():
	logger.notice(u"Aborting system shutdown")
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.AbortSystemShutdown(None)

#def blockShutdown():
#	logger.notice(u"Blocking system shutdown")
#	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
#	win32api.ShutdownBlockReasonCreate()
#
#def unblockShutdown():
#	logger.notice(u"Unblocking system shutdown")
#	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
#	win32api.ShutdownBlockReasonDestroy()

def createWindowStation(name):
	name = forceUnicode(name)
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 1
	sa.SECURITY_DESCRIPTOR = None

	try:
		return win32service.CreateWindowStation(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error as e:
		logger.error(u"Failed to create window station '%s': %s" % (name, forceUnicode(e)))

def createDesktop(name, runCommand=None):
	name = forceUnicode(name)
	if runCommand:
		runCommand = forceUnicode(runCommand)
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 0

	try:
		sa.SECURITY_DESCRIPTOR = win32security.GetUserObjectSecurity(
			win32service.OpenDesktop('default', 0, 0, win32con.MAXIMUM_ALLOWED), win32con.DACL_SECURITY_INFORMATION)
	except Exception as e:
		logger.error(e)
		sa.SECURITY_DESCRIPTOR = None

	hdesk = None
	try:
		hdesk = win32service.CreateDesktop(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error as e:
		logger.error(u"Failed to create desktop '%s': %s" % (name, forceUnicode(e)))

	if runCommand:
		s = win32process.STARTUPINFO()
		s.lpDesktop = name
		prc_info = win32process.CreateProcess(None, runCommand, None, None, True, win32con.CREATE_NEW_CONSOLE, None, 'c:\\', s)
	return hdesk

def getDesktops(winsta = None):
	if not winsta:
		winsta = win32service.GetProcessWindowStation()
	desktops = []
	for d in winsta.EnumDesktops():
		desktops.append(forceUnicodeLower(d))
	return desktops

def switchDesktop(name):
	name = forceUnicode(name)
	hdesk = win32service.OpenDesktop(name, 0, 0, win32con.MAXIMUM_ALLOWED)
	hdesk.SwitchDesktop()

def addUserToDesktop(desktop, userSid):
	'''
	Adds the given PySID representing a user to the given desktop's
	discretionary access-control list. The old security descriptor for
	desktop is returned.
	'''

	desktopAll  = 	win32con.DESKTOP_CREATEMENU      | \
			win32con.DESKTOP_CREATEWINDOW    | \
			win32con.DESKTOP_ENUMERATE       | \
			win32con.DESKTOP_HOOKCONTROL     | \
			win32con.DESKTOP_JOURNALPLAYBACK | \
			win32con.DESKTOP_JOURNALRECORD   | \
			win32con.DESKTOP_READOBJECTS     | \
			win32con.DESKTOP_SWITCHDESKTOP   | \
			win32con.DESKTOP_WRITEOBJECTS    | \
			win32con.DELETE                  | \
			win32con.READ_CONTROL            | \
			win32con.WRITE_DAC               | \
			win32con.WRITE_OWNER

	securityDesc = win32security.GetUserObjectSecurity(desktop, win32con.DACL_SECURITY_INFORMATION)

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
	win32security.SetUserObjectSecurity(desktop,
			win32con.DACL_SECURITY_INFORMATION,
			newSecurityDesc)

	return [ ace0Index ]


def addUserToWindowStation(winsta, userSid):
	'''
	Adds the given PySID representing a user to the given window station's
	discretionary access-control list. The old security descriptor for
	winsta is returned.
	'''

	winstaAll  =	win32con.WINSTA_ACCESSCLIPBOARD   | \
			win32con.WINSTA_ACCESSGLOBALATOMS | \
			win32con.WINSTA_CREATEDESKTOP     | \
			win32con.WINSTA_ENUMDESKTOPS      | \
			win32con.WINSTA_ENUMERATE         | \
			win32con.WINSTA_EXITWINDOWS       | \
			win32con.WINSTA_READATTRIBUTES    | \
			win32con.WINSTA_READSCREEN        | \
			win32con.WINSTA_WRITEATTRIBUTES   | \
			win32con.DELETE                   | \
			win32con.READ_CONTROL             | \
			win32con.WRITE_DAC                | \
			win32con.WRITE_OWNER

	genericAccess = win32con.GENERIC_READ    | \
			win32con.GENERIC_WRITE   | \
			win32con.GENERIC_EXECUTE | \
			win32con.GENERIC_ALL

	# Get the security description for winsta.
	securityDesc = win32security.GetUserObjectSecurity(
						winsta,
						win32con.DACL_SECURITY_INFORMATION)

	# Get discretionary access-control list (DACL) for winsta.
	acl = securityDesc.GetSecurityDescriptorDacl()

	# Create a new access control list for winsta.
	newAcl = win32security.ACL()

	if acl:
		copyACL(acl, newAcl)

	# Add the first ACE for userSid to the window station.
	ace0Index = newAcl.GetAceCount()
	aceFlags   = 	win32con.CONTAINER_INHERIT_ACE | \
			win32con.INHERIT_ONLY_ACE      | \
			win32con.OBJECT_INHERIT_ACE
	newAcl.AddAccessAllowedAceEx(win32con.ACL_REVISION, aceFlags, genericAccess, userSid)

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
	win32security.SetUserObjectSecurity(	winsta,
						win32con.DACL_SECURITY_INFORMATION,
						newSecurityDesc)

	return [ ace0Index, ace1Index ]

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                        PROCESS HANDLING                                           -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def which(cmd):
	raise NotImplementedError(u"which() not implemented on windows")

def execute(cmd, waitForEnding=True, getHandle=False, ignoreExitCode=[], exitOnStderr=False, captureStderr=True, encoding=None, timeout=0, shell=True):
	cmd             = forceUnicode(cmd)
	waitForEnding   = forceBool(waitForEnding)
	getHandle       = forceBool(getHandle)
	exitOnStderr    = forceBool(exitOnStderr)
	captureStderr   = forceBool(captureStderr)
	timeout         = forceInt(timeout)
	shell              = forceBool(shell)

	exitCode = 0
	result = []

	startTime = time.time()
	try:
		logger.info(u"Executing: %s" % cmd)
		if getHandle:
			if captureStderr:
				return (subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)).stdout
			else:
				return (subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None)).stdout
		else:
			data = ''
			stderr = None
			if captureStderr:
				stderr	= subprocess.PIPE
			proc = subprocess.Popen(
				cmd,
				shell	= shell,
				stdin	= subprocess.PIPE,
				stdout	= subprocess.PIPE,
				stderr	= stderr,
			)
			if not encoding:
				encoding = proc.stdout.encoding
				logger.debug(u"proc.stdout.encoding: %s" % encoding)
				if (encoding == 'ascii'): encoding = None
			if not encoding:
				encoding = locale.getpreferredencoding()
				logger.debug(u"locale.getpreferredencoding(): %s" % encoding)
				if (encoding == 'ascii'): encoding = None
			if not encoding:
				encoding = sys.stdout.encoding
				logger.debug(u"sys.stdout.encoding: %s" % encoding)
				if (encoding == 'ascii'): encoding = None
			if not encoding:
				encoding = 'cp850'

			logger.info(u"Using encoding '%s'" % encoding)

			ret = None
			while ret is None:
				ret = proc.poll()
				try:
					chunk = proc.stdout.read()
					if (len(chunk) > 0):
						data += chunk
				except IOError as e:
					if (e.errno != 11):
						raise

				if captureStderr:
					try:
						chunk = proc.stderr.read()
						if (len(chunk) > 0):
							if exitOnStderr:
								raise IOError(exitCode, u"Command '%s' failed: %s" % (cmd, chunk) )
							data += chunk
					except IOError as e:
						if (e.errno != 11):
							raise

				if (timeout > 0) and (time.time() - startTime >= timeout):
					try:
						proc.kill()
					except:
						pass
					raise IOError(exitCode, u"Command '%s' timed out atfer %d seconds" % (cmd, (time.time() - startTime)) )

				time.sleep(0.001)

			exitCode = ret
			if data:
				lines = data.split('\n')
				for i in range(len(lines)):
					line = lines[i].decode(encoding, 'replace').replace('\r', '')
					if (i == len(lines) - 1) and not line:
						break
					logger.debug(u'>>> %s' % line)
					result.append(line)

	except (os.error, IOError) as e:
		# Some error occured during execution
		raise IOError(e.errno, u"Command '%s' failed:\n%s" % (cmd, e) )

	logger.debug(u"Exit code: %s" % exitCode)
	if exitCode:
		if   type(ignoreExitCode) is bool and ignoreExitCode:
			pass
		elif type(ignoreExitCode) is list and exitCode in ignoreExitCode:
			pass
		else:
			raise IOError(exitCode, u"Command '%s' failed (%s):\n%s" % (cmd, exitCode, u'\n'.join(result)))
	return result


def getPids(process, sessionId = None):
	process = forceUnicode(process)
	if not sessionId is None:
		sessionId = forceInt(sessionId)

	logger.info(u"Searching pids of process name %s (session id: %s)" % (process, sessionId))
	processIds = []
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.debug2(u"Getting first process")
	if ( Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE ):
		logger.error(u"Failed to get first process")
		return
	while True:
		pid = pe32.th32ProcessID
		sid = u'unknown'
		try:
			sid = win32ts.ProcessIdToSessionId(pid)
		except:
			pass
		logger.debug2(u"   got process %s with pid %d in session %s" % (pe32.szExeFile, pid, sid))
		if (pe32.szExeFile.lower() == process.lower()):
			logger.info(u"Found process %s with matching name (pid %d, session %s)" % (pe32.szExeFile.lower(), pid, sid))
			if sessionId is None or (sid == sessionId):
				processIds.append(forceInt(pid))
		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break
	CloseHandle(hProcessSnap)
	if not processIds:
		logger.debug(u"No process with name %s found (session id: %s)" % (process, sessionId))
	return processIds

def getPid(process, sessionId = None):
	process = forceUnicode(process)
	if not sessionId is None:
		sessionId = forceInt(sessionId)

	processId = 0
	processIds = getPids(process, sessionId)
	if processIds:
		processId = processIds[0]
	return processId

def getProcessName(processId):
	processId = forceInt(processId)

	logger.notice(u"Searching name of process %d" % processId)
	processName = u''
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.info(u"Getting first process")
	if ( Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE ):
		logger.error(u"Failed getting first process")
		return
	while True:
		#logger.info("Got process %s" % pe32.szExeFile)
		#sid = win32ts.ProcessIdToSessionId(pe32.th32ProcessID)
		pid = pe32.th32ProcessID
		#logger.notice("Found process %s with pid %d in session %d" % (process, pid, sid))
		#logger.notice("Found process %s with pid %d" % (pe32.szExeFile, pid))
		if (pid == processId):
			processName = forceUnicode(pe32.szExeFile)
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
	logger.info(u"Getting window handles of process with id %s" % processId)
	def callback (windowHandle, windowHandles):
		#if win32gui.IsWindowVisible(windowHandle) and win32gui.IsWindowEnabled(windowHandle):
		if (win32process.GetWindowThreadProcessId(windowHandle)[1] == processId):
			logger.debug(u"Found window %s of process with id %s" % (windowHandle, processId))
			windowHandles.append(windowHandle)
		return True
	windowHandles = []
	win32gui.EnumWindows(callback, windowHandles)
	return windowHandles

def closeProcessWindows(processId):
	processId = forceInt(processId)
	logger.info("Closing windows of process with id %s" % processId)
	for windowHandle in getProcessWindowHandles(processId):
		logger.debug("Sending WM_CLOSE message to window %s" % windowHandle)
		win32gui.SendMessage(windowHandle, win32con.WM_CLOSE, 0, 0)

def terminateProcess(processHandle=None, processId=None):
	if not processId is None:
		processId = forceInt(processId)

	if not processHandle and not processId:
		raise ValueError(u"Neither process handle not process id given")
	exitCode = 0
	if not processHandle:
		processHandle = getProcessHandle(processId)
	win32process.TerminateProcess(processHandle, exitCode)
	return exitCode

def getUserToken(sessionId = None, duplicateFrom = u"winlogon.exe"):
	if not sessionId is None:
		sessionId = forceInt(sessionId)
	duplicateFrom = forceUnicode(duplicateFrom)

	if sessionId is None or (sessionId < 0):
		sessionId = getActiveSessionId()

	pid = getPid(process = duplicateFrom, sessionId = sessionId)
	if not pid:
		raise Exception(u"Failed to get user token, pid of '%s' not found in session '%s'" % (duplicateFrom, sessionId))
	hProcess = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, False, pid)
	hPToken = win32security.OpenProcessToken(
				hProcess,
				win32con.TOKEN_ADJUST_PRIVILEGES|win32con.TOKEN_QUERY|\
				win32con.TOKEN_DUPLICATE|win32con.TOKEN_ASSIGN_PRIMARY|\
				win32con.TOKEN_READ|win32con.TOKEN_WRITE) # win32con.TOKEN_ADJUST_SESSIONID

	id = win32security.LookupPrivilegeValue(None, win32security.SE_DEBUG_NAME)

	newPrivileges = [(id, win32security.SE_PRIVILEGE_ENABLED)]

	hUserTokenDup = win32security.DuplicateTokenEx(
		ExistingToken = hPToken,
		DesiredAccess = win32con.MAXIMUM_ALLOWED,
		ImpersonationLevel = win32security.SecurityIdentification,
		TokenType = ntsecuritycon.TokenPrimary,
		TokenAttributes = None )

	# Adjust Token privilege

	win32security.SetTokenInformation(hUserTokenDup, ntsecuritycon.TokenSessionId, sessionId)

	win32security.AdjustTokenPrivileges(hUserTokenDup, 0, newPrivileges)

	return hUserTokenDup

def runCommandInSession(command, sessionId = None, desktop = u"default", duplicateFrom = u"winlogon.exe", waitForProcessEnding=True, timeoutSeconds=0):
	command = forceUnicode(command)
	if not sessionId is None:
		sessionId = forceInt(sessionId)
	desktop = forceUnicodeLower(desktop)
	if (desktop.find(u'\\') == -1):
		desktop = u'winsta0\\' + desktop
	duplicateFrom = forceUnicode(duplicateFrom)
	waitForProcessEnding = forceBool(waitForProcessEnding)
	timeoutSeconds = forceInt(timeoutSeconds)

	logger.debug(u"Session id given: %s" % sessionId)
	if sessionId is None or (sessionId < 0):
		logger.debug(u"No session id given, running in active session")
		sessionId = getActiveSessionId()

	if not desktop.split('\\')[-1] in ('default', 'winlogon'):
		logger.info(u"Creating new desktop '%s'" % desktop.split('\\')[-1])
		try:
			createDesktop(desktop.split('\\')[-1])
		except Exception as e:
			logger.warning(e)

	userToken = getUserToken(sessionId, duplicateFrom)

	dwCreationFlags = win32con.NORMAL_PRIORITY_CLASS#|win32con.CREATE_NEW_CONSOLE

	s = win32process.STARTUPINFO()
	s.lpDesktop = desktop
	#s.wShowWindow = win32con.SW_MAXIMIZE
	#s.dwFlags = win32process.STARTF_USESTDHANDLES

	logger.notice(u"Executing: '%s' in session '%s' on desktop '%s'" % (command, sessionId, desktop))
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(userToken, None, command, None, None, 1, dwCreationFlags, None, None, s)

	logger.info(u"Process startet, pid: %d" % dwProcessId)
	if not waitForProcessEnding:
		return (hProcess, hThread, dwProcessId, dwThreadId)
	logger.info(u"Waiting for process ending: %d (timeout: %d seconds)" % (dwProcessId, timeoutSeconds))
	t = 0.0
	while win32event.WaitForSingleObject(hProcess, timeoutSeconds):
		if (timeoutSeconds > 0):
			if (t >= timeoutSeconds):
				terminateProcess(processId = dwProcessId)
				raise Exception(u"Timed out after %s seconds while waiting for process %d" % (t, dwProcessId))
			t += 0.1
		time.sleep(0.1)
	exitCode = win32process.GetExitCodeProcess(hProcess)
	logger.notice(u"Process %d ended with exit code %d" % (dwProcessId, exitCode))
	return (None, None, None, None)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                     USER / GROUP HANDLING                                         -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def createUser(username, password, groups = []):
	username = forceUnicode(username)
	password = forceUnicode(password)
	groups = forceUnicodeList(groups)
	logger.addConfidentialString(password)

	domain = getHostname().upper()
	if (username.find(u'\\') != -1):
		domain = username.split(u'\\')[0]
		username = username.split(u'\\')[-1]
	domain = domain.upper()
	if (domain != getHostname().upper()):
		raise ValueError(u"Can only handle domain %s" % getHostname().upper())

	userData = {
		'name':             username,
		'full_name':        u"",
		'password':         password,
		'flags':            win32netcon.UF_NORMAL_ACCOUNT | win32netcon.UF_SCRIPT,
		'priv':             win32netcon.USER_PRIV_USER,
		'home_dir':         None,
		'home_dir_drive':   None,
		'primary_group_id': ntsecuritycon.DOMAIN_GROUP_RID_USERS,
		'password_expired': 0
	}

	#win32net.NetUserAdd(domain, 3, userData)
	win32net.NetUserAdd(u"\\\\" + domain, 1, userData)
	if not groups:
		return
	u = { 'domainandname': domain + u'\\' + username }
	for group in groups:
		logger.info(u"Adding user '%s' to group '%s'" % (username, group))
		win32net.NetLocalGroupAddMembers(u"\\\\" + domain, group, 3, [ u ])


def deleteUser(username, deleteProfile = True):
	username = forceUnicode(username)
	domain = getHostname()
	if (username.find(u'\\') != -1):
		domain = username.split(u'\\')[0]
		username = username.split(u'\\')[-1]
	domain = domain.upper()
	if (domain != getHostname().upper()):
		raise ValueError(u"Can only handle domain %s" % getHostname().upper())

	if deleteProfile:
		try:
			sid = getUserSid(username)
			if sid:
				try:
					win32profile.DeleteProfile(sid)
				except Exception as e:
					logger.info(u"Failed to delete user profile '%s' (sid %s): %s" % (username, sid, forceUnicode(e)))
		except Exception as e:
			pass
	try:
		win32net.NetUserDel(u"\\\\" + domain, username)
	except win32net.error as e:
		logger.info(u"Failed to delete user '%s': %s" % (username, forceUnicode(e)))

def existsUser(username):
	username = forceUnicode(username)
	domain = getHostname()
	if (username.find(u'\\') != -1):
		domain = username.split(u'\\')[0]
		username = username.split(u'\\')[-1]
	domain = domain.upper()
	if (domain != getHostname().upper()):
		raise ValueError(u"Can only handle domain %s" % getHostname().upper())

	for user in win32net.NetUserEnum(u"\\\\" + domain, 0)[0]:
		if (user.get('name').lower() == username.lower()):
			return True
	return False

def getUserSidFromHandle(userHandle):
	tic = win32security.GetTokenInformation(userHandle, ntsecuritycon.TokenGroups)
	for (sid, flags) in tic:
		if (flags & win32con.SE_GROUP_LOGON_ID):
			return sid

def getUserSid(username):
	username = forceUnicode(username)
	domain = getHostname()
	if (username.find(u'\\') != -1):
		domain = username.split(u'\\')[0]
		username = username.split(u'\\')[-1]
	domain = domain.upper()
	return win32security.ConvertSidToStringSid(win32security.LookupAccountName(None, domain + u'\\' + username)[0])

def getAdminGroupName():
	subAuths = ntsecuritycon.SECURITY_BUILTIN_DOMAIN_RID, ntsecuritycon.DOMAIN_ALIAS_RID_ADMINS
	sidAdmins = win32security.SID(ntsecuritycon.SECURITY_NT_AUTHORITY, subAuths)
	groupName = forceUnicode(win32security.LookupAccountSid(None, sidAdmins)[0])
	logger.info(u"Admin group name is '%s'" % groupName)
	return groupName

class Impersonate:
	def __init__(self, username=u"", password=u"", userToken = None, desktop = u"default"):
		if not username and not userToken:
			raise Exception(u"Neither username nor user token given")
		#if username and not existsUser(username):
		#	raise Exception("User '%s' does not exist" % username)
		self.domain = getHostname()
		self.username = forceUnicode(username)
		if (self.username.find('\\') != -1):
			self.domain = self.username.split('\\')[0]
			self.username = self.username.split('\\')[-1]
		self.domain = self.domain.upper()
		self.password = forceUnicode(password)
		if not desktop:
			desktop = u"default"
		if (desktop.find(u'\\') == -1):
			desktop = u'winsta0\\' + desktop
		(self.winsta, self.desktop) = desktop.split('\\', 1)
		self.winsta = forceUnicodeLower(self.winsta)
		self.desktop = forceUnicodeLower(self.desktop)
		self.userToken = userToken
		self.userProfile = None
		self.userEnvironment = None
		self.saveWindowStation = None
		self.saveDesktop = None
		self.newWindowStation = None
		self.newDesktop = None

	def start(self, logonType=u'INTERACTIVE', newDesktop=False, createEnvironment=False):
		try:
			logonType = forceUnicode(logonType)
			newDesktop = forceBool(newDesktop)
			if (logonType == u'NEW_CREDENTIALS'):
				# Stay who you are but add credentials for network connections
				logonType = win32security.LOGON32_LOGON_NEW_CREDENTIALS
			elif (logonType == u'INTERACTIVE'):
				logonType = win32con.LOGON32_LOGON_INTERACTIVE
			else:
				raise ValueError(u"Unhandled logon type '%s'" % logonType)

			if not self.userToken:
				# TODO: Use (UPN) format for username <USER>@<DOMAIN> ?
				logger.debug(u"Logon user: '%s\\%s'" % (self.domain, self.username))
				self.userToken = win32security.LogonUser(
							self.username,
							self.domain,
							self.password,
							logonType,
							win32con.LOGON32_PROVIDER_DEFAULT)

			if newDesktop:
				self.saveWindowStation = win32service.GetProcessWindowStation()
				logger.debug(u"Got current window station")

				self.saveDesktop = win32service.GetThreadDesktop(win32api.GetCurrentThreadId())
				logger.debug(u"Got current desktop")

				self.newWindowStation = win32service.OpenWindowStation(
								self.winsta,
								False,
								win32con.READ_CONTROL |
								win32con.WRITE_DAC)

				self.newWindowStation.SetProcessWindowStation()
				logger.debug(u"Process window station set")

				self.newDesktop = None
				if not self.desktop in ('default', 'winlogon'):
					logger.info(u"Creating new desktop '%s'" % self.desktop)
					try:
						self.newDesktop = createDesktop(self.desktop)
					except Exception as e:
						logger.warning(e)

				if not self.newDesktop:
					self.newDesktop = win32service.OpenDesktop(
								self.desktop,
								win32con.DF_ALLOWOTHERACCOUNTHOOK, #0,
								True, #False,
								win32con.READ_CONTROL |
								win32con.WRITE_DAC |
								win32con.DESKTOP_CREATEMENU |
								win32con.DESKTOP_CREATEWINDOW |
								win32con.DESKTOP_ENUMERATE |
								win32con.DESKTOP_HOOKCONTROL |
								win32con.DESKTOP_JOURNALPLAYBACK |
								win32con.DESKTOP_JOURNALRECORD |
								win32con.DESKTOP_READOBJECTS |
								win32con.DESKTOP_SWITCHDESKTOP |
								win32con.DESKTOP_WRITEOBJECTS)
				self.newDesktop.SetThreadDesktop()
				logger.debug(u"Thread desktop set")

				userSid = getUserSidFromHandle(self.userToken)
				if not userSid:
					logger.warning(u"Failed to determine sid of user '%s'" % self.username)
				else:
					logger.debug(u"Got sid of user '%s'" % self.username)

					winstaAceIndices = addUserToWindowStation(self.newWindowStation, userSid)
					logger.debug(u"Added user to window station")

					desktopAceIndices = addUserToDesktop(self.newDesktop, userSid)
					logger.debug(u"Added user to desktop")

			if createEnvironment:
				# http://www.java2s.com/Open-Source/Python/Windows/pyExcelerator/pywin32-214/win32/Demos/win32cred_demo.py.htm
				self.userProfile = win32profile.LoadUserProfile(self.userToken, {'UserName': self.username, 'Flags': 0, 'ProfilePath': None})
				logger.debug(u"User profile loaded")

				self.userEnvironment = win32profile.CreateEnvironmentBlock(self.userToken, False)
				logger.debug(u"Environment block created")

			win32security.ImpersonateLoggedOnUser(self.userToken)
			logger.debug(u"User impersonated")
		except Exception as e:
			logger.logException(e)
			self.end()
			raise

	def runCommand(self, command, waitForProcessEnding=True, timeoutSeconds=0):
		command = forceUnicode(command)
		waitForProcessEnding = forceBool(waitForProcessEnding)
		timeoutSeconds = forceInt(timeoutSeconds)

		dwCreationFlags = win32process.CREATE_NEW_CONSOLE

		s = win32process.STARTUPINFO()
		s.dwFlags = win32process.STARTF_USESHOWWINDOW ^ win32con.STARTF_USESTDHANDLES
		s.wShowWindow = win32con.SW_NORMAL
		s.lpDesktop = self.winsta + u'\\' + self.desktop

		logger.notice(u"Running command '%s' as user '%s' on desktop '%s'" % (command, self.username, self.desktop))
		self.userEnvironment
		(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(
					self.userToken, None, command, None, None, 0, dwCreationFlags, self.userEnvironment, None, s)
		logger.info(u"Process startet, pid: %d" % dwProcessId)
		if not waitForProcessEnding:
			return (hProcess, hThread, dwProcessId, dwThreadId)
		logger.info(u"Waiting for process ending: %d (timeout: %d seconds)" % (dwProcessId, timeoutSeconds))
		t = 0.0
		while win32event.WaitForSingleObject(hProcess, timeoutSeconds):
			if (timeoutSeconds > 0):
				if (t >= timeoutSeconds):
					terminateProcess(processId = dwProcessId)
					raise Exception(u"Timed out after %s seconds while waiting for process %d" % (t, dwProcessId))
				t += 0.1
			time.sleep(0.1)
		exitCode = win32process.GetExitCodeProcess(hProcess)
		logger.notice(u"Process %d ended with exit code %d" % (dwProcessId, exitCode))
		return (None, None, None, None)

	def end(self):
		try:
			win32security.RevertToSelf()
			if self.saveWindowStation:
				try:
					self.saveWindowStation.SetProcessWindowStation()
				except Exception as e:
					logger.debug(u"Failed to set process WindowStation: %s" % e)
			if self.saveDesktop:
				try:
					self.saveDesktop.SetThreadDesktop()
				except Exception as e:
					logger.debug(u"Failed to set thread Desktop: %s" % e)
			if self.newDesktop:
				try:
					self.newWindowStation.CloseDesktop()
				except Exception as e:
					logger.debug(u"Failed to close Desktop: %s" % e)
			if self.newWindowStation:
				try:
					self.newWindowStation.CloseWindowStation()
				except Exception as e:
					logger.debug(u"Failed to close WindowStation: %s" % e)
			if self.userProfile:
				logger.debug(u"Unloading user profile")
				try:
					win32profile.UnloadUserProfile(self.userToken, self.userProfile)
				except Exception as e:
					logger.debug(u"Failed to unload user profile: %s" % e)
			if self.userToken:
				try:
					self.userToken.Close()
				except Exception as e:
					logger.debug(u"Failed to close user token: %s" % e)
		except Exception as e:
			logger.logException(e)

	def __del__(self):
		self.end()



























