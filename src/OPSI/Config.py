# -*- coding: utf-8 -*-
"""
   ======================================
   =        OPSI Config Module          =
   ======================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.1'

# Imports
import os, ConfigParser

if os.name == 'nt':
	# Windows imports for file locking
	import win32con
	import win32file
	import pywintypes
	import win32security
	import win32api
	LOCK_EX = win32con.LOCKFILE_EXCLUSIVE_LOCK
	LOCK_SH = 0 # the default
	LOCK_NB = win32con.LOCKFILE_FAIL_IMMEDIATELY
	__overlapped = pywintypes.OVERLAPPED()
	ov=pywintypes.OVERLAPPED()
	highbits=0x7fff0000
	secur_att = win32security.SECURITY_ATTRIBUTES()
	secur_att.Initialize()


elif os.name == 'posix':
	# Posix imports for file locking
	import fcntl
	LOCK_EX = fcntl.LOCK_EX
	LOCK_SH = fcntl.LOCK_SH
	LOCK_NB = fcntl.LOCK_NB

# OPSI imports
from OPSI.Logger import *

# Get logger instance
logger = Logger()

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                CLASS OPSICONFIGIMPLEMENTATION                                      =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class OpsiConfigImplementation:
	
	def __init__(self, opsiConfigFile = None):
		if not opsiConfigFile:
			opsiConfigFile = '/etc/opsi/opsi.conf'
		
		self._opsiConfigFile = opsiConfigFile
		self._loaded = False
		self._depotDir = '/opt/pcbin/install'
		
	def getDepotDir(self):
		if not self._loaded: self.readOpsiConfigFile()
		return self._depotDir
	
	def openFile(self, filename, mode = 'r'):
		''' 
		Opens a file for reading or writing.
		Locks the file (exclusive mode for writing, shared mode for reading). 
		If the lock cannot be created an exception will be raised 
		after a timeout (__fileOpenTimeout)
		'''
		# Open the file
		try:
			f = open(filename, mode)
		except IOError, e:
			raise BackendIOError(e)
		
		timeout = 0
		locked = False
		while (not locked and timeout < 2000):
			# While not timed out and not locked
			logger.debug("Trying to lock file '%s' (%s/%s)" % (filename, timeout, self.__fileOpenTimeout))
			try:
				# Try to lock file
				if (os.name == 'nt'):
					flags = win32con.LOCKFILE_EXCLUSIVE_LOCK | win32con.LOCKFILE_FAIL_IMMEDIATELY
					if (mode == 'r'):
						flags = win32con.LOCKFILE_FAIL_IMMEDIATELY
					global ov
					global highbits
					hfile = win32file._get_osfhandle(f.fileno())
					win32file.LockFileEx(hfile, flags, 0, highbits, ov)
				
				elif (os.name =='posix'):
					# Flags for exclusive, non-blocking lock
					flags = LOCK_EX | LOCK_NB
					if (mode == 'r'):
						# Flags for shared, non-blocking lock
						flags = LOCK_SH | LOCK_NB
					fcntl.flock(f.fileno(), flags)
				
			except IOError, e:
				# Locking failed 
				# increase timeout counter, sleep 100 millis
				timeout += 100
				time.sleep(0.1)
			else:
				# File successfully locked
				logger.debug("File '%s' locked" % filename)
				locked = True
		
		if not locked:
			# File lock failed => raise BackendIOError
			raise BackendIOError("Cannot lock file '%s', timeout was %s" 
						% (filename,  self.__fileOpenTimeout))
		# File opened and locked => return filehandle
		return f
	
	'''- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	-                                    Private Methods                                                 -
	- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -'''
	def readOpsiConfigFile(self):
		from OPSI.Backend.File import File
		logger.info("Reading config file '%s'" % self._opsiConfigFile)
		try:
			f = File()
			ini = f.readIniFile(self._opsiConfigFile, caseIgnore = True, raw = False)
			try:
				self._depotDir = ini.get('paths', 'depotdir')
				if self._depotDir.startswith('"') and self._epotDir.endswith('"'):
					self._depotDir = self._depotDir[1:-1]
				logger.info("%s: depot dir set to '%s'" % (self._opsiConfigFile, self._depotDir))
			except ConfigParser.NoOptionError, e:
				logger.warning("Failed to get depot-dir from config file '%s': %s" % (self._opsiConfigFile, e))
		except Exception, e:
			logger.error("Failed to read config file '%s': %s" % (self._opsiConfigFile, e))


'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                      CLASS OPSICONFIG                                              =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class OpsiConfig(OpsiConfigImplementation):
	''' This class implements a SINGLETON used for 
	    logging to console, file or syslog. '''
	
	# Storage for the instance reference
	__instance = None
	
	def __init__(self, opsiConfigFile = None):
		""" Create singleton instance """
		
		# Check whether we already have an instance
		if OpsiConfig.__instance is None:
			# Create and remember instance
			OpsiConfig.__instance = OpsiConfigImplementation(opsiConfigFile)
		
		# Store instance reference as the only member in the handle
		self.__dict__['_OpsiConfig__instance'] = OpsiConfig.__instance
	
	
	def __getattr__(self, attr):
		""" Delegate access to implementation """
		return getattr(self.__instance, attr)

	def __setattr__(self, attr, value):
		""" Delegate access to implementation """
	 	return setattr(self.__instance, attr, value)

