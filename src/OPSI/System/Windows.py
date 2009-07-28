#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Windows   =
   = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008 uib GmbH
   
   http://www.uib.de/
   
   All rights reserved.
   
   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License version 2 as
   published by the Free Software Foundation.
   
   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   
   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
   
   @copyright:	uib GmbH <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '0.1.8.2'

# Imports
import re, os, time, socket, sys

# Win32 imports
from ctypes import *
import pywintypes
import ntsecuritycon
import win32service
import win32event
import win32con
import win32ts
import win32process
import win32api
import win32security
import win32gui
import win32net
import win32wnet
import win32netcon
import _winreg

# OPSI imports
from OPSI.Logger import *

# Get Logger instance
logger = Logger()

HKEY_CURRENT_USER = _winreg.HKEY_CURRENT_USER
HKEY_LOCAL_MACHINE = _winreg.HKEY_LOCAL_MACHINE

TH32CS_SNAPPROCESS = 0x00000002
class PROCESSENTRY32(Structure):
     _fields_ = [("dwSize", c_ulong),
                 ("cntUsage", c_ulong),
                 ("th32ProcessID", c_ulong),
                 ("th32DefaultHeapID", c_ulong),
                 ("th32ModuleID", c_ulong),
                 ("cntThreads", c_ulong),
                 ("th32ParentProcessID", c_ulong),
                 ("pcPriClassBase", c_ulong),
                 ("dwFlags", c_ulong),
                 ("szExeFile", c_char * 260)]

#def setWallpaper(filename):
#	win32gui.SystemParametersInfo ( win32con.SPI_SETDESKWALLPAPER, filename, win32con.SPIF_SENDCHANGE )

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                               INFO                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getHostname():
	hostname = socket.getfqdn().lower().split('.')[0]
	if (hostname != 'localhost'):
		return hostname
	return getRegistryValue(HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Control\\ComputerName\\ActiveComputerName', 'ComputerName').lower()
	
def getFQDN():
	fqdn = socket.getfqdn().lower()
	if ( len(fqdn.split('.')) < 2 ):
		return getHostname()
	return getHostname() + '.' + '.'.join(fqdn.split('.')[1:])

def getFileVersionInfo(filename):
	(lang, codepage) = win32api.GetFileVersionInfo(filename, '\\VarFileInfo\\Translation')[0]
	path = u'\\StringFileInfo\\%04X%04X\\%%s' % (lang, codepage)
	info = {
		'CompanyName':      win32api.GetFileVersionInfo(filename, path % 'CompanyName'),
		'SpecialBuild':     win32api.GetFileVersionInfo(filename, path % 'SpecialBuild'),
		'Comments':         win32api.GetFileVersionInfo(filename, path % 'Comments'),
		'FileDescription':  win32api.GetFileVersionInfo(filename, path % 'FileDescription'),
		'FileVersion':      win32api.GetFileVersionInfo(filename, path % 'FileVersion'),
		'InternalName':     win32api.GetFileVersionInfo(filename, path % 'InternalName'),
		'LegalCopyright':   win32api.GetFileVersionInfo(filename, path % 'LegalCopyright'),
		'LegalTrademarks':  win32api.GetFileVersionInfo(filename, path % 'LegalTrademarks'),
		'OriginalFilename': win32api.GetFileVersionInfo(filename, path % 'OriginalFilename'),
		'PrivateBuild':     win32api.GetFileVersionInfo(filename, path % 'PrivateBuild'),
		'ProductName':      win32api.GetFileVersionInfo(filename, path % 'ProductName'),
		'ProductVersion':   win32api.GetFileVersionInfo(filename, path % 'ProductVersion'),
	}
	logger.debug("File version info for '%s': %s" % (filename, info))
	return info

def getProgramFilesDir():
	return getRegistryValue(HKEY_LOCAL_MACHINE, 'Software\\Microsoft\\Windows\\CurrentVersion', 'ProgramFilesDir')

def getSystemDrive():
	return os.getenv('SystemDrive', 'c:')

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            HELPERS                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def copyACL(src, dest):
	revision = src.GetAclRevision()
	logger.debug("copyACL: ace count is %s" % src.GetAceCount())
	for i in range(src.GetAceCount()):
		logger.debug("copyACL: processing ace #%s" % i)
		ace = src.GetAce(i)
		logger.debug("copyACL: ace: %s" % str(ace))
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
def getRegistryValue(key, subKey, valueName):
	hkey = _winreg.OpenKey(key, subKey)
	(value, type) = _winreg.QueryValueEx(hkey, valueName)
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
def mkdir(newDir, mode=0750, ui='default'):
	"""
	- already exists, silently complete
	- regular file in the way, raise an exception
	- parent directory(ies) does not exist, make them as well
	"""
	if os.path.isdir(newDir):
		pass
	elif os.path.isfile(newDir):
		raise OSError(	"A file with the same name as the desired " \
				"dir, '%s', already exists." % newDir)
	else:
		(head, tail) = os.path.split(newDir)
		if head and not os.path.isdir(head):
			mkdir(head)
		if tail:
			os.mkdir(newDir)
		
def mount(dev, mountpoint, ui='default', **options):
	#if ui == 'default': ui=userInterface
	fs = ''
	
	#if ui: ui.getMessageBox().addText(_("Mounting '%s' to '%s'.\n") % (dev, mountpoint))
	
	match = re.search('^[a-zA-Z]:$', mountpoint)
	if not match:
		logger.error("Bad mountpoint '%s'" % mountpoint)
		raise ValueError("Bad mountpoint '%s'" % mountpoint)
	
	if dev.lower().startswith('smb://'):
		# Do not log smb password
		logLevel = LOG_CONFIDENTIAL
		
		match = re.search('^smb://([^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			parts = match.group(1).split('/')
			dev = '\\\\%s\\%s' % (parts[0], parts[1])
		else:
			raise Exception("Bad smb uri '%s'" % dev)
		
		if not 'username' in options:
			options['username'] = 'guest'
		if not 'password' in options:
			options['password'] = ''
		
		try:
			try:
				# Remove connection and update user profile (remove persistent connection)
				win32wnet.WNetCancelConnection2(mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True)
			except Exception,e:
				logger.info(e)
			
			logger.notice("Mounting '%s' to '%s'" % (dev, mountpoint))
			# Mount not persistent
			win32wnet.WNetAddConnection2(
				win32netcon.RESOURCETYPE_DISK,
				mountpoint,
				dev,
				None,
				options['username'],
				options['password'],
				0
			)
			
			
		except Exception, e:
			logger.error("Cannot mount: %s" % e)
			raise Exception ("Cannot mount: %s" % e)

def umount(mountpoint, ui='default'):
	#if ui == 'default': ui=userInterface
	#if ui: ui.getMessageBox().addText(_("Umounting '%s'.\n") % mountpoint)
	
	try:
		# Remove connection and update user profile (remove persistent connection)
		win32wnet.WNetCancelConnection2(mountpoint, win32netcon.CONNECT_UPDATE_PROFILE, True)
	except pywintypes.error, details:
		if (details[0] == 2250):
			# Not connected
			logger.warning("Failed to umount '%s': %s" % (mountpoint, details))
		else:
			raise
	
	except Exception, e:
		logger.error("Failed to umount '%s': %s" % (mountpoint, e))
		raise Exception ("Failed to umount '%s': %s" % (mountpoint, e))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                               SESSION / WINSTA / DESKTOP HANDLING                                 -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getActiveConsoleSessionId():
	try:
		return windll.kernel32.WTSGetActiveConsoleSessionId()
	except Exception, e:
		logger.warning(e)
		return 0

def getActiveDesktopName():
	desktop = win32service.OpenInputDesktop(0, True, win32con.MAXIMUM_ALLOWED)
	return win32service.GetUserObjectInformation(desktop, win32con.UOI_NAME)

def logoffCurrentUser():
	logger.notice("Logging off current user")
	#win32api.ExitWindows()
	#win32api.ExitWindowsEx(0)
	## Windows Server 2008 and Windows Vista:  A call to WTSShutdownSystem does not work when Remote Connection Manager (RCM) is disabled. This is the case when the Terminal Services service is stopped.
	#win32ts.WTSShutdownSystem(win32ts.WTS_CURRENT_SERVER_HANDLE, win32ts.WTS_WSD_LOGOFF)
	#runCommandInSession(
	#		command              = "logoff.exe",
	#		sessionId            = getActiveConsoleSessionId(),
	#		waitForProcessEnding = False )
	command = ''
	if (sys.getwindowsversion()[0] == 5):
		if (sys.getwindowsversion()[1] == 0):
			# NT5.0: win2k
			raise NotImplemented("Not available on win2k")
		else:
			# NT5.1: XP
			command = 'logoff.exe'
	elif (sys.getwindowsversion()[0] == 6):
		# NT6: Vista
		command = 'shutdown.exe /l'
	else:
		raise Exception("Operating system not supported")
	runCommandInSession(
			command              = command,
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )
	
def lockWorkstation():
	#windll.winsta.WinStationConnectW(0, 0, sessionId, "", 0)
	#windll.user32.LockWorkStation()
	runCommandInSession(
			command              = "rundll32.exe user32.dll,LockWorkStation",
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def reboot(wait=10):
	logger.notice("Rebooting in %s seconds" % wait)
	wait = int(wait)
	
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, "Opsi reboot", wait, True, True)
	return
	
	command = ''
	if (sys.getwindowsversion()[0] == 5):
		# NT5: XP
		command = 'shutdown.exe /l /r /t:%d "Opsi reboot" /y /c' % wait
	elif (sys.getwindowsversion()[0] == 6):
		# NT6: Vista
		command = 'shutdown.exe /r /c "Opsi reboot" /t %d' % wait
	else:
		raise Exception("Operating system not supported")
	runCommandInSession(
			command              = command,
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def shutdown(wait=10):
	logger.notice("Shutting down in %s seconds" % wait)
	wait = int(wait)
	
	adjustPrivilege(ntsecuritycon.SE_SHUTDOWN_NAME)
	win32api.InitiateSystemShutdown(None, "Opsi shutdown", wait, True, False)
	return
	
	if (sys.getwindowsversion()[0] == 5):
		# NT5: XP
		command = 'shutdown.exe /l /s /t:%d "Opsi shutdown" /y /c' % wait
	elif (sys.getwindowsversion()[0] == 6):
		# NT6: Vista
		command = 'shutdown.exe /s /c "Opsi shutdown" /t %d' % wait
	else:
		raise Exception("Operating system not supported")
	runCommandInSession(
			command              = command,
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def createWindowStation(name):
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 1
	sa.SECURITY_DESCRIPTOR = None
	
	try:
		return win32service.CreateWindowStation(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error, e:
		logger.error("Failed to create window station '%s': %s" % (name, e))
	

def createDesktop(name, cmd):
	sa = pywintypes.SECURITY_ATTRIBUTES()
	sa.bInheritHandle = 1
	sa.SECURITY_DESCRIPTOR = None
	
	try:
		hdesk = win32service.CreateDesktop(name, 0, win32con.MAXIMUM_ALLOWED, sa)
	except win32service.error, e:
		logger.error("Failed to create desktop '%s': %s" % (name, e))
	
	s = win32process.STARTUPINFO()
	s.lpDesktop = name
	prc_info = win32process.CreateProcess(None, cmd, None, None, True, win32con.CREATE_NEW_CONSOLE, None, 'c:\\', s)
	return hdesk

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
	
	securityDesc = win32security.GetUserObjectSecurity(desktop,
					win32con.DACL_SECURITY_INFORMATION)

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

def getPids(process, sessionId = None):
	#if not sessionId:
	#	sessionId = getActiveConsoleSessionId()
	logger.info("Searching pids of process name %s (session id: %s)" % (process, sessionId))
	processIds = []
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.debug2("Getting first process")
	if ( Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE ):
		logger.error("Failed to get first process")
		return
	while True:
		pid = pe32.th32ProcessID
		sid = 'unkown'
		try:
			sid = win32ts.ProcessIdToSessionId(pid)
		except:
			pass
		logger.debug2("   got process %s with pid %d in session %s" % (pe32.szExeFile, pid, sid))
		if (pe32.szExeFile.lower() == process.lower()):
			logger.info("Found process %s with matching name (pid %d, session %s)" % (pe32.szExeFile.lower(), pid, sid))
			if not sessionId or (sid == sessionId):
				processIds.append(pid)
		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break
	CloseHandle(hProcessSnap)
	if not processIds:
		logger.warning("No process with name %s found (session id: %s)" % (process, sessionId))
	return processIds

def getPid(process, sessionId = None):
	processId = 0
	processIds = getPids(process, sessionId)
	if processIds:
		processId = processIds[0]
	return processId

def getProcessName(processId):
	logger.notice("Searching name of process %d" % processId)
	processName = ''
	CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
	Process32First = windll.kernel32.Process32First
	Process32Next = windll.kernel32.Process32Next
	CloseHandle = windll.kernel32.CloseHandle
	hProcessSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	pe32 = PROCESSENTRY32()
	pe32.dwSize = sizeof(PROCESSENTRY32)
	logger.info("Getting first process")
	if ( Process32First(hProcessSnap, byref(pe32)) == win32con.FALSE ):
		logger.error("Failed getting first process")
		return
	while True:
		#logger.info("Got process %s" % pe32.szExeFile)
		#sid = win32ts.ProcessIdToSessionId(pe32.th32ProcessID)
		pid = pe32.th32ProcessID
		#logger.notice("Found process %s with pid %d in session %d" % (process, pid, sid))
		#logger.notice("Found process %s with pid %d" % (pe32.szExeFile, pid))
		if (pid == processId):
			processName = pe32.szExeFile
			break
		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break
	CloseHandle(hProcessSnap)
	return processName

def getProcessHandle(processId):
	processHandle = win32api.OpenProcess(1, 0, processId)
	return processHandle

def getProcessWindowHandles(processId):
	logger.info("Getting window handles of process with id %s" % processId)
	def callback (windowHandle, windowHandles):
		#if win32gui.IsWindowVisible(windowHandle) and win32gui.IsWindowEnabled(windowHandle):
		if (win32process.GetWindowThreadProcessId(windowHandle)[1] == processId):
			logger.debug("Found window %s of process with id %s" % (windowHandle, processId))
			windowHandles.append(windowHandle)
		return True
	windowHandles = []
	win32gui.EnumWindows(callback, windowHandles)
	return windowHandles

def closeProcessWindows(processId):
	logger.info("Closing windows of process with id %s" % processId)
	for windowHandle in getProcessWindowHandles(processId):
		logger.debug("Sending WM_CLOSE message to window %s" % windowHandle)
		win32gui.SendMessage(windowHandle, win32con.WM_CLOSE, 0, 0)

def terminateProcess(processHandle=None, processId=None):
	if not processHandle and not processId:
		raise ValueError("Neither process handle not process id given")
	exitCode = 0
	if not processHandle:
		processHandle = getProcessHandle(processId)
	win32process.TerminateProcess(processHandle, exitCode)
	return exitCode

def getUserToken(sessionId = None, duplicateFrom = "winlogon.exe"):
	if not type(sessionId) is int or (sessionId < 0):
		sessionId = getActiveConsoleSessionId()
	
	pid = getPid(process = duplicateFrom, sessionId = sessionId)
	if not pid:
		raise Exception("Failed to get user token, pid of '%s' not found in session '%s'" % (duplicateFrom, sessionId))
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

def runCommandInSession(command, sessionId = None, desktop = "default", duplicateFrom = "winlogon.exe", waitForProcessEnding=True):
	if not desktop:
		desktop = "default"
	if (desktop.find('\\') == -1):
		desktop = 'winsta0\\' + desktop
	
	if not type(sessionId) is int or (sessionId < 0):
		sessionId = getActiveConsoleSessionId()
	
	userToken = getUserToken(sessionId, duplicateFrom)
	
	dwCreationFlags = win32con.NORMAL_PRIORITY_CLASS|win32con.CREATE_NEW_CONSOLE
	
	s = win32process.STARTUPINFO()
	s.lpDesktop = desktop
	#s.wShowWindow = win32con.SW_MAXIMIZE
	
	try:
		logger.notice("Executing: '%s' in session '%s' on desktop '%s'" % (command, sessionId, desktop))
		(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(userToken,None,command,None,None,0,dwCreationFlags,None,None,s)
		logger.info("Process startet, pid: %d" % dwProcessId)
		if not waitForProcessEnding:
			return (hProcess, hThread, dwProcessId, dwThreadId)
		logger.info("Waiting for process ending: %d" % dwProcessId)
		while win32event.WaitForSingleObject(hProcess, 0):
			time.sleep(0.1)
		logger.notice("Process ended: %d" % dwProcessId)
	except Exception, e:
		logger.error(e)
		if (e[0] == 233) and (sys.getwindowsversion()[0] == 5):
			# No process is on the other end
			# Problem with pipe \\\\.\\Pipe\\TerminalServer\\SystemExecSrvr\\<sessionid>
			# After logging off from a session other than 0 csrss.exe does not create this pipe or CreateRemoteProcessW is not able to read the pipe.
			logger.info("Retrying to run command on winlogon desktop of session 0")
			return runCommandInSession(command, 0, 'winlogon', duplicateFrom, waitForProcessEnding)
		else:
			raise

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                     USER / GROUP HANDLING                                         -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def createUser(username, password, groups = []):
	servername = "\\\\" + win32api.GetComputerName()
	
	userData = {}
	userData['name'] = username
	userData['full_name'] = ""
	userData['password'] = password
	userData['flags'] = win32netcon.UF_NORMAL_ACCOUNT | win32netcon.UF_SCRIPT
	userData['priv'] = win32netcon.USER_PRIV_USER
	userData['home_dir'] = None
	userData['home_dir_drive'] = None
	userData['primary_group_id'] = ntsecuritycon.DOMAIN_GROUP_RID_USERS
	userData['password_expired'] = 1 # User must change password next logon.
	
	#win32net.NetUserAdd(serverName, 3, userData)
	win32net.NetUserAdd(servername, 1, userData)
	if not groups:
		return
	u = { 'domainandname': username }
	for group in groups:
		logger.info("Adding user '%s' to group '%s'" % (username, group))
		win32net.NetLocalGroupAddMembers(servername, group, 3, [ u ])
		
	
def deleteUser(username):
	servername = "\\\\" + win32api.GetComputerName()
	try:
		win32net.NetUserDel(servername, username)
	except win32net.error:
		pass

def existsUser(username):
	servername = "\\\\" + win32api.GetComputerName()
	for user in win32net.NetUserEnum(servername, 0)[0]:
		if (user.get('name') == username):
			return True
	return False

def getUserSidFromHandle(userHandle):
	tic = win32security.GetTokenInformation(userHandle, ntsecuritycon.TokenGroups)
	for (sid, flags) in tic:
		if (flags & win32con.SE_GROUP_LOGON_ID):
			return sid

def getAdminGroupName():
	subAuths = ntsecuritycon.SECURITY_BUILTIN_DOMAIN_RID, \
	           ntsecuritycon.DOMAIN_ALIAS_RID_ADMINS
	sidAdmins = win32security.SID(ntsecuritycon.SECURITY_NT_AUTHORITY, subAuths)
	groupName = win32security.LookupAccountSid(None, sidAdmins)[0]
	logger.info("Admin group name is '%s'" % groupName)
	return groupName

class Impersonate:
	def __init__(self, username="", password="", userToken = None, desktop = "default"):
		if not username and not userToken:
			raise Exception("Neither username nor user token given")
		#if username and not existsUser(username):
		#	raise Exception("User '%s' does not exist" % username)
		self.username = username
		self.password = password
		if not desktop:
			desktop = "default"
		if (desktop.find('\\') == -1):
			desktop = 'winsta0\\' + desktop
		(self.winsta, self.desktop) = desktop.split('\\', 1)
		self.domain = win32api.GetComputerName()
		self.userToken = userToken
		self.saveWindowStation = None 
		self.saveDesktop = None
		self.newWindowStation = None
		self.newDesktop = None
		
	def start(self, logonType='INTERACTIVE', newDesktop=False):
		try:
			if (logonType == 'NEW_CREDENTIALS'):
				# Stay who you are but add credentials for network connections
				logonType = win32security.LOGON32_LOGON_NEW_CREDENTIALS
			elif (logonType == 'INTERACTIVE'):
				logonType = win32con.LOGON32_LOGON_INTERACTIVE
			else:
				raise ValueError("Unhandled logon type '%s'" % logonType)
			
			if not self.userToken:
				self.userToken = win32security.LogonUser(
					self.username,
					self.domain,
					self.password,
					logonType,
					win32con.LOGON32_PROVIDER_DEFAULT)
			
			if newDesktop:
				self.saveWindowStation = win32service.GetProcessWindowStation()
				logger.debug("Got current window station")
				
				self.saveDesktop = win32service.GetThreadDesktop(win32api.GetCurrentThreadId())
				logger.debug("Got current desktop")
				
				self.newWindowStation = win32service.OpenWindowStation(
								self.winsta,
								False,
								win32con.READ_CONTROL |
								win32con.WRITE_DAC)
				
				self.newWindowStation.SetProcessWindowStation()
				logger.debug("Process window station set")
					
				self.newDesktop = win32service.OpenDesktop(
								self.desktop,
								win32con.DF_ALLOWOTHERACCOUNTHOOK, #0,
								False,
								win32con.READ_CONTROL |
								win32con.WRITE_DAC |
								win32con.DESKTOP_READOBJECTS |
								win32con.DESKTOP_WRITEOBJECTS)
				self.newDesktop.SetThreadDesktop()
				logger.debug("Thread desktop set")
				
				userSid = getUserSidFromHandle(self.userToken)
				if not userSid:
					logger.warning("Failed to determine sid of user '%s'" % self.username)
				else:
					logger.debug("Got sid of user '%s'" % self.username)
					
					winstaAceIndices = addUserToWindowStation(self.newWindowStation, userSid)
					logger.debug("Added user to window station")
						
					desktopAceIndices = addUserToDesktop(self.newDesktop, userSid)
					logger.debug("Added user to desktop")
			
			win32security.ImpersonateLoggedOnUser(self.userToken)
			logger.debug("User imersonated")
		except Exception, e:
			logger.logException(e)
			self.end()
			raise
	
	def runCommand(self, command, waitForProcessEnding=True):
		dwCreationFlags = win32process.CREATE_NEW_CONSOLE
		
		s = win32process.STARTUPINFO()
		s.dwFlags = win32process.STARTF_USESHOWWINDOW ^ win32con.STARTF_USESTDHANDLES
		s.wShowWindow = win32con.SW_NORMAL
		s.lpDesktop = self.winsta + '\\' + self.desktop
		
		logger.notice("Running command '%s' as user '%s' on desktop '%s'" % (command, self.username, self.desktop))
		
		(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(
					self.userToken, None, command, None, None, 0, dwCreationFlags, None, None, s)
		logger.info("Process startet, pid: %d" % dwProcessId)
		if not waitForProcessEnding:
			return (hProcess, hThread, dwProcessId, dwThreadId)
		logger.info("Waiting for process ending: %d" % dwProcessId)
		while win32event.WaitForSingleObject(hProcess, 0):
			time.sleep(0.1)
		logger.notice("Process ended: %d" % dwProcessId)

	def end(self):
		if self.userToken: self.userToken.Close()
		win32security.RevertToSelf()
		if self.saveWindowStation: self.saveWindowStation.SetProcessWindowStation()
		if self.saveDesktop:       self.saveDesktop.SetThreadDesktop()
		if self.newWindowStation:  self.newWindowStation.CloseWindowStation()
		if self.newDesktop:        self.newDesktop.CloseDesktop()
	
	def __del__(self):
		self.end()


