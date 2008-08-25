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

__version__ = '0.0.3'

# Imports
import re, os, time

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
import win32wnet
import win32netcon
import _winreg

# OPSI imports
from OPSI.Logger import *
#from OPSI import Tools


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

def getRegistryValue(key, subKey, valueName):
	hkey = _winreg.OpenKey(key, subKey)
	(value, type) = _winreg.QueryValueEx(hkey, valueName)
	return value

def setRegistryValue(key, subKey, valueName, value):
	hkey = _winreg.OpenKey(key, subKey, 0, _winreg.KEY_WRITE)
	if type(value) is int:
		_winreg.SetValueEx(hkey, valueName, 0, _winreg.REG_DWORD, value)
	else:
		_winreg.SetValueEx(hkey, valueName, 0, _winreg.REG_SZ, value)

def getProgramFilesDir():
	return getRegistryValue(HKEY_LOCAL_MACHINE, 'Software\\Microsoft\\Windows\\CurrentVersion', 'ProgramFilesDir')

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
	
def getActiveConsoleSessionId():
	return windll.kernel32.WTSGetActiveConsoleSessionId()
	
def logonUser(username, password, domain=None):
	impersonated_user_handler = win32security.LogonUser(
		username,
		domain,
		password,
		win32con.LOGON32_LOGON_INTERACTIVE,
		win32con.LOGON32_PROVIDER_DEFAULT)
	win32security.ImpersonateLoggedOnUser(impersonated_user_handler)
	return impersonated_user_handler

def logoffCurrentUser():
	logger.notice("Logging off current user")
	#win32api.ExitWindows()
	#win32api.ExitWindowsEx(0)
	## Windows Server 2008 and Windows Vista:  A call to WTSShutdownSystem does not work when Remote Connection Manager (RCM) is disabled. This is the case when the Terminal Services service is stopped.
	#win32ts.WTSShutdownSystem(win32ts.WTS_CURRENT_SERVER_HANDLE, win32ts.WTS_WSD_LOGOFF)
	#runAsSystemInSession(
	#		command              = "logoff.exe",
	#		sessionId            = getActiveConsoleSessionId(),
	#		waitForProcessEnding = False )
	runAsSystemInSession(
			command              = 'shutdown.exe /l',
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )
	
def lockWorkstation():
	#windll.winsta.WinStationConnectW(0, 0, sessionId, "", 0)
	#windll.user32.LockWorkStation()
	runAsSystemInSession(
			command              = "rundll32.exe user32.dll,LockWorkStation",
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def reboot(wait=10):
	logger.notice("Rebooting in %s seconds" % wait)
	wait = int(wait)
	runAsSystemInSession(
			command              = 'shutdown.exe /r /c "Opsi reboot" /t %d' % wait,
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def shutdown(wait=10):
	logger.notice("Shutting down in %s seconds" % wait)
	wait = int(wait)
	runAsSystemInSession(
			command              = 'shutdown.exe /s /c "Opsi shutdown" /t %d' % wait,
			sessionId            = getActiveConsoleSessionId(),
			waitForProcessEnding = False )

def getActiveDesktopName():
	desktop = win32service.OpenInputDesktop(0, True, win32con.MAXIMUM_ALLOWED)
	return win32service.GetUserObjectInformation(desktop, win32con.UOI_NAME)

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


def getPids(process, sessionId = None):
	if not sessionId:
		sessionId = getActiveConsoleSessionId()
	logger.info("Searching pids of process name %s in session %d" % (process, sessionId))
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
		logger.debug2("   got process %s" % pe32.szExeFile)
		if (pe32.szExeFile == process):
			sid = win32ts.ProcessIdToSessionId(pe32.th32ProcessID)
			pid = pe32.th32ProcessID
			logger.info("Found process %s with pid %d in session %d" % (process, pid, sid))
			if (sid == sessionId):
				processIds.append(pid)
		if Process32Next(hProcessSnap, byref(pe32)) == win32con.FALSE:
			break
	CloseHandle(hProcessSnap)
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


def terminateProcess(hProcess):
	exitCode = 0
	win32process.TerminateProcess(hProcess, exitCode)
	return exitCode

def runAsSystem(command, waitForProcessEnding=True):
	logger.notice("Executing: %s" % command)
	
	sessionId = 1
	
	s = win32process.STARTUPINFO()
	s.lpDesktop = desktop = 'winsta0\\winlogon'
	dwCreationFlags = win32con.NORMAL_PRIORITY_CLASS|win32con.CREATE_NEW_CONSOLE
	
	s = win32process.STARTUPINFO()
	s.lpDesktop = desktop
	
	hProcess = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, False, getPid(process = "winlogon.exe", sessionId = sessionId))
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
	
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(hUserTokenDup,None,command,None,None,0,dwCreationFlags,None,None,s)
	#win32process.CreateProcess(None,command,None,None,0,dwCreationFlags,None,None,s)
	logger.info("Process startet, pid: %d" % dwProcessId)
	if not waitForProcessEnding:
		return (hProcess, hThread, dwProcessId, dwThreadId)
	logger.info("Waiting for process ending: %d" % dwProcessId)
	while win32event.WaitForSingleObject(hProcess, 0):
		time.sleep(0.1)
	logger.notice("Process ended: %d" % dwProcessId)
	
	
def runAsSystemInSession(command, sessionId = None, desktop = "default", duplicateFrom = "winlogon.exe", waitForProcessEnding=True):
	logger.notice("Executing: %s" % command)
	if not type(sessionId) is int or (sessionId < 0):
		sessionId = getActiveConsoleSessionId()
	if not desktop:
		desktop = "default"
	if (desktop.find('\\') == -1):
		desktop = 'winsta0\\' + desktop
	
	##############hUserToken = win32ts.WTSQueryUserToken(sessionId)
	dwCreationFlags = win32con.NORMAL_PRIORITY_CLASS|win32con.CREATE_NEW_CONSOLE
	
	s = win32process.STARTUPINFO()
	s.lpDesktop = desktop
	# Start maximized does not work?
	s.wShowWindow = win32con.SW_MAXIMIZE
	
	hProcess = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, False, getPid(process = duplicateFrom, sessionId = sessionId))
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
	
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcessAsUser(hUserTokenDup,None,command,None,None,0,dwCreationFlags,None,None,s)
	logger.info("Process startet, pid: %d" % dwProcessId)
	if not waitForProcessEnding:
		return (hProcess, hThread, dwProcessId, dwThreadId)
	logger.info("Waiting for process ending: %d" % dwProcessId)
	while win32event.WaitForSingleObject(hProcess, 0):
		time.sleep(0.1)
	logger.notice("Process ended: %d" % dwProcessId)
	
	
def getWindowsInSession(sessionId):
	try:
		windll.winsta.WinStationConnectW(0, 0, sessionId, "", 0)
		hWndDesktop = win32gui.GetDesktopWindow()
		logger.debug("hWndDesktop: %s" % hWndDesktop)
		hWndChild = win32gui.GetWindow(hWndDesktop, win32con.GW_CHILD)
		logger.debug("hWndChild: %s" % hWndChild)
		hWndChildProcessIDs = win32process.GetWindowThreadProcessId(hWndChild)
		logger.debug("hWndChildProcessIDs: %s" % hWndChildProcessIDs)
		for hWndChildProcessID in hWndChildProcessIDs:
			logger.debug("hWndChildProcessID: %s" % hWndChildProcessID)
			#sid = win32ts.ProcessIdToSessionId(hWndChildProcessID)
			#logger.debug("Runnig in session %d" % sid)
			logger.debug("Process name: %s" % getProcessName(hWndChildProcessID))
		#while hWndChild:
		#	hWndChild = win32gui.GetWindow(hWndChild, win32con.GW_CHILD)
		#	logger.debug("hWndChild: %s" % hWndChild)
		#	hWndChildProcessIDs = win32process.GetWindowThreadProcessId(hWndChild)
		#	for hWndChildProcessID in hWndChildProcessIDs:
		#		logger.debug("hWndChildProcessID: %s" % hWndChildProcessID)
		#		logger.debug("Process name: %s" % getProcessName(hWndChildProcessID))
		
	except Exception, e:
		logger.error(e)

