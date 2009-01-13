#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - File    =
   = = = = = = = = = = = = = = = = = =
   
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

__version__ = '0.9.7.6'

# Imports
import socket, os, time, re, ConfigParser, json, StringIO, codecs

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
from OPSI.Backend.Backend import *
from OPSI.Backend.File import *
from OPSI.Logger import *
from OPSI.Product import *
from OPSI import Tools

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                         CLASS FILE                                                 =
# ======================================================================================================
class File:
	def __init__(self, fileOpenTimeout = 2000):
		''' Constructor of File class.
		    Timeout waiting for file lock in millis. '''
		self.__fileOpenTimeout = fileOpenTimeout
	
	def readIniFile(self, filename, caseIgnore = True, raw = False):
		''' 
		This function opens an ini-file creates a ConfigParser,
		reads and closes the file.
		Returns ConfigParser. 
		'''
		logger.debug("Reading ini file '%s'" % filename)
		start = time.time()
		# Open file read-only
		iniFile = self.openFile(filename, 'r')
		# Read file
		lines = iniFile.readlines()
		if caseIgnore:
			for i in range(len(lines)):
				lines[i] = lines[i].strip()
				if not lines[i] or lines[i].startswith('#') or lines[i].startswith(';'):
					continue
				
				if lines[i].startswith('['):
					lines[i] = lines[i].lower()
				
				match = re.search('^([^\:\=]+)([\:\=].*)$', lines[i])
				if match:
					lines[i] = match.group(1).lower() + match.group(2)
				
		# Close file
		self.closeFile(iniFile)
		# Create ConfigParser 
		cp = None
		if raw:
			cp = ConfigParser.RawConfigParser()
		else:
			cp = ConfigParser.SafeConfigParser()
		
		for i in range(len(lines)):
			lines[i] = lines[i].lstrip()
		
		try:
			cp.readfp( StringIO.StringIO('\r\n'.join(lines)) )
		except Exception, e:
			raise BackendIOError("Failed to read ini file '%s': %s" % (filename, e))
			
		logger.debug("Finished reading file (%s)" % (time.time() - start))
		
		# Return ConfigParser
		return cp
	
	def writeIniFile(self, filename, cp):
		''' 
		This function is used to write a 
		ConfigParser object into an ini-file. 
		'''
		data = StringIO.StringIO()
		cp.write(data)
		# Open ini-file for writing
		iniFile = self.openFile(filename, 'w', unicode = True)
		# Write ConfigParser data
		iniFile.write(data.getvalue().replace('\r', '').replace('\n', '\r\n').decode('utf-8', 'replace'))
		# Close file
		self.closeFile(iniFile)
	
	def createFile(self, filename, mode = 0600):
		''' Creates a 0 byte file. '''
		logger.debug("Creating file '%s'" % filename)
		f = self.openFile(filename, 'w')
		self.closeFile(f)
		logger.debug("Changing file permissions of '%s' to %s" % (filename, oct(mode)))
		os.chmod(filename, mode)
		
	def deleteFile(self, filename):
		''' Deletes a file. '''
		os.remove(filename)
	
	def openFile(self, filename, mode = 'r', unicode=False):
		''' 
		Opens a file for reading or writing.
		Locks the file (exclusive mode for writing, shared mode for reading). 
		If the lock cannot be created an exception will be raised 
		after a timeout (__fileOpenTimeout)
		'''
		# Open the file
		try:
			if unicode:
				f = codecs.open(filename, mode, 'utf-8')
			else:
				f = open(filename, mode)
		except IOError, e:
			raise BackendIOError(e)
		
		timeout = 0
		locked = False
		while (not locked and timeout < self.__fileOpenTimeout):
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
		
	def closeFile(self, f):
		""" This function is not really needed, use filehandle.close() instead,
		    which should also close the file and remove the lock. """
		if (os.name == 'nt'):
			global ov
			global highbits
			hfile = win32file._get_osfhandle(f.fileno())
			win32file.UnlockFileEx(hfile,0,highbits,ov)
		elif (os.name =='posix'):
			fcntl.flock(f.fileno(), fcntl.LOCK_UN)
		
		f.close()
		

# ======================================================================================================
# =                                       CLASS TFTPFILE                                               =
# ======================================================================================================
class TFTPFile(File):
	def __init__(self, address):
		''' 
		Constructor of TFTPFile class.
		'''
		self._address = address
		self._files = {}
		
	def openFile(self, filename, mode = 'r'):
		if (mode != 'r'):
			raise NotImplemented("Writing files via TFTP not supported.")
		try:
			logger.info("Trying to get file '%s' from TFTP-Server '%s'" % (filename, self._address))
			
			import tftplib
			
			self._tftp = tftplib.TFTP(addr = self._address)
			f = open( os.path.join('/tmp', os.path.basename(filename)), 'w+')
			self._files[f.fileno()] = os.path.join('/tmp', os.path.basename(filename))
			self._tftp.retrieve(filename, f)
			f.seek(0,0)
			return f
		
		except Exception, e:
			raise BackendIOError("Failed to open file '%s': %s" % (filename, e) )

	def closeFile(self, f):
		fileno = f.fileno()
		f.close()
		if not fileno:
			return
		filename = self._files.get(fileno)
		if not filename:
			return
		if os.path.isfile(filename):
			os.unlink(filename)
			logger.debug("Local copy '%s' of TFTP file deleted." % filename)
		del self._files[fileno]
		
# ======================================================================================================
# =                                     CLASS FILEBACKEND                                              =
# ======================================================================================================
class FileBackend(File, DataBackend):
	''' This class implements parts of the abstract class Backend '''
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' FileBackend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		self.__fileOpenTimeout = 2000
		self._defaultDomain = 'opsi.org'
		
		logger.debug("Getting Arguments:'%s'" % args)
		
		if os.name == 'nt':
			windefaultdir = os.getenv("ProgramFiles")+'\opsi.org\opsiconfd'
			self.__pclogDir = windefaultdir+'\\pclog'
			self.__pcpatchDir = windefaultdir+'\\share\\pcpatch'
			self.__depotDir = windefaultdir+'\\depot'
			self.__pckeyFile = windefaultdir+'\\opsi\\pckeys'
			self.__passwdFile = windefaultdir+'\\opsi\\passwd'
			self.__productsFile = windefaultdir+'\\share\\utils\\produkte.txt'
			self.__groupsFile = windefaultdir+'\\opsi\\groups.ini'
			self.__licensesFile = windefaultdir+'\\opsi\\licenses.ini'
			self.__opsiTFTPDir = windefaultdir+'\\opsi\\tftpboot'
		else:
			self.__pclogDir = '/opt/pcbin/pcpatch/pclog'
			self.__pcpatchDir = '/opt/pcbin/pcpatch'
			self.__depotDir = '/opt/pcbin/install'
			self.__pckeyFile = '/etc/opsi/pckeys'
			self.__passwdFile = '/etc/opsi/passwd'
			self.__productsFile = '/opt/pcbin/utils/produkte.txt'
			self.__groupsFile = '/opt/pcbin/utils/groups.ini'
			self.__licensesFile = '/opt/pcbin/utils/licenses.ini'
			self.__opsiTFTPDir = '/tftpboot/opsi'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'pclogdir'):		self.__pclogDir = value
			elif (option.lower() == 'pcpatchdir'): 	self.__pcpatchDir = value
			elif (option.lower() == 'depotdir'):		self.__depotDir = value
			elif (option.lower() == 'pckeyfile'):		self.__pckeyFile = value
			elif (option.lower() == 'passwdfile'):		self.__passwdFile = value
			elif (option.lower() == 'productsfile'): 	self.__productsFile = value
			elif (option.lower() == 'opsitftpdir'): 	self.__opsiTFTPDir = value
			elif (option.lower() == 'fileopentimeout'): 	self.__fileOpenTimeout = value
			elif (option.lower() == 'groupsfile'): 	self.__groupsFile = value
			elif (option.lower() == 'licensesfile'): 	self.__licensesFile = value
			elif (option.lower() == 'defaultdomain'): 	self._defaultDomain = value
			else:
				logger.warning("Unknown argument '%s' passed to FileBackend constructor" % option)
		
		# Call File constructor
		File.__init__(self, self.__fileOpenTimeout)
	
	def _aliaslist(self):
		hostname = ''
		aliaslist = []
		try:
			hostname = socket.gethostname()
		except Exception, e:
			raise BackendIOError("Failed to get my own hostname: %s" % e)
		
		try:
			(name, aliaslist, addresslist) = socket.gethostbyname_ex(hostname)
			aliaslist.append(name)
		except Exception, e:
			raise BackendIOError("Failed to get aliaslist for hostname '%s': %s" % (hostname, e))
		
		return aliaslist
	
	def checkForErrors(self):
		import stat, grp, pwd
		errors = []
		(pcpatchUid, pcpatchGid) = (-1, -1)
		try:
			pcpatchUid = pwd.getpwnam('pcpatch')[2]
		except KeyError:
			errors.append('User pcpatch does not exist')
			logger.error('User pcpatch does not exist')
		try:
			pcpatchGid = grp.getgrnam('pcpatch')[2]
		except KeyError:
			errors.append('Group pcpatch does not exist')
			logger.error('Group pcpatch does not exist')
		
		files = [self.__productsFile, self.__pckeyFile, self.__passwdFile]
		if os.path.exists(self.__groupsFile):
			files.append(self.__groupsFile)
		if os.path.exists(self.__licensesFile):
			files.append(self.__licensesFile)
		
		for path in [self.__pcpatchDir, self.__opsiTFTPDir, self.__pclogDir, self.__depotDir]:
			if not os.path.isdir(path):
				errors.append("Directory '%s' does not exists" % path)
				logger.error("Directory '%s' does not exists" % path)
				continue
			statinfo = os.stat(path)
			if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
				errors.append("Directory '%s' should be owned by group pcpatch" % path)
				logger.error("Directory '%s' should be owned by group pcpatch" % path)
			
			mode = stat.S_ISGID | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
			if (path == self.__depotDir):
				mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
			
			if (statinfo[stat.ST_MODE] & mode != mode):
				errors.append("Bad permissions for directory '%s', should be 277X" % path)
				logger.error("Bad permissions for directory '%s', should be 277X" % path)
			
			if (path not in [self.__pclogDir, self.__depotDir]):
				for filename in os.listdir(path):
					if not os.path.isdir(os.path.join(path, filename)):
						if filename.startswith('.'):
							continue
						if not filename.endswith('.ini') and not filename.endswith('.sysconf'):
							errors.append("Not an ini file: '%s'" % os.path.join(path, filename))
							continue
						files.append(os.path.join(path, filename))
		
		for f in files:
			mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP
			statinfo = os.stat(f)
			if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
				errors.append("File '%s' should be owned by group pcpatch" % f)
				logger.error("File '%s' should be owned by group pcpatch" % f)
			
			if f in [self.__pckeyFile, self.__passwdFile]:
				if (statinfo[stat.ST_MODE] != 32768 | mode):
					errors.append("Bad permissions for file '%s', should be 0660" % f)
					logger.error("Bad permissions for file '%s', should be 0660" % f)
				
			else:
				if ((statinfo[stat.ST_MODE] & mode) != mode):
					errors.append("Bad permissions for file '%s', should be 066X" % f)
					logger.error("Bad permissions for file '%s', should be 066X" % f)
				try:
					self.readIniFile(f)
				except Exception, e:
					errors.append("Cannot read file '%s': %s" % (f, e))
					logger.error("Cannot read file '%s': %s" % (f, e))
		
		return errors
		
	def getHostId(self, iniFile):
		parts = iniFile.lower().split('.')
		# Replace file extension with domain name
		return parts[0] + '.' + self._defaultDomain
	
	def getIniFile(self, hostId):
		''' Returns the filename of the host specific ini file. '''
		hostId = hostId.lower()
		parts = hostId.split('.')
		# Hostname plus extension '.ini'
		return parts[0] + '.ini'
	
	def getSysconfFile(self, hostId):
		''' Returns the filename of the host specific sysconfig file. '''
		hostId = hostId.lower()
		# Hostname plus extension '.sysconf'
		parts = hostId.split('.')
		# Only use lower case characters for sysconf files!
		return parts[0].lower() + '.sysconf'
	
	
	# -------------------------------------------------
	# -     GENERAL CONFIG                            -
	# -------------------------------------------------
	def setGeneralConfig(self, config, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
		self.deleteGeneralConfig(objectId)
		
		basename = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# Global network config (all hosts) => edit global.sysconf
			basename = 'global'
		else:
			# General config for special host => edit <hostname>.sysconf
			basename = self.getHostname(objectId)
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		except BackendIOError:
			self.createFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), mode=0660)
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		
		for (key, value) in config.items():
			if key in [ 'pcptchBitmap1', 'pcptchBitmap2', 'pcptchLabel1', 'pcptchLabel2', 'clientSideConfigCaching', 'button_stopnetworking', 'secsUntilConnectionTimeOut' ]:
				# Create section pcptch if not exists
				if not ini.has_section("pcptch"):
					ini.add_section("pcptch")
				
				# Set pcptch options
				if   (key == 'pcptchBitmap1'): 		ini.set('pcptch', 'bitmap1', value)
				elif (key == 'pcptchBitmap2'): 		ini.set('pcptch', 'bitmap2', value)
				elif (key == 'pcptchLabel1'): 			ini.set('pcptch', 'label1', value)
				elif (key == 'pcptchLabel2'): 			ini.set('pcptch', 'label2', value)
				elif (key == 'button_stopnetworking'): 	ini.set('pcptch', 'button_stopnetworking', value)
				elif (key == 'secsUntilConnectionTimeOut'): 	ini.set('pcptch', 'secsUntilConnectionTimeOut', value)
				elif (key == 'clientSideConfigCaching'):
					if value:
						ini.set('pcptch', 'makelocalcopyofinifile', 'true')
					else:
						ini.set('pcptch', 'makelocalcopyofinifile', 'false')
			else:
				# Create section general if not exists
				if not ini.has_section("general"):
					ini.add_section("general")
				ini.set('general', key, value)
		
		# Write back ini file
		self.writeIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), ini)
	
	def getGeneralConfig_hash(self, objectId = None):
		
		if not objectId:
			objectId = self._defaultDomain
		
		iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
		if (objectId != self.getServerId()) and (objectId != self._defaultDomain):
			# Add client specific general config
			iniFiles.append( "%s.sysconf" % os.path.join(self.__opsiTFTPDir, self.getHostname(objectId)) )
		
		generalConfig = { 
			'pcptchBitmap1': 		'',
			'pcptchBitmap2':		'',
			'pcptchLabel1':			'',
			'pcptchLabel2':			'',
			'button_stopnetworking':	'',
			'secsUntilConnectionTimeOut':	'180' }
		
		# Read the ini-files, priority of client-specific values is higher
		# than global values
		for iniFile in iniFiles:
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				logger.debug(e)
				continue
			
			try:
				for item in ini.items('pcptch'):
					if   (item[0] == 'bitmap1'):				generalConfig['pcptchBitmap1'] = item[1]
					elif (item[0] == 'bitmap2'):				generalConfig['pcptchBitmap2'] = item[1]
					elif (item[0] == 'label1'):				generalConfig['pcptchLabel1'] = item[1]
					elif (item[0] == 'label2'):				generalConfig['pcptchLabel2'] = item[1]
					elif (item[0] == 'button_stopnetworking'):		generalConfig['button_stopnetworking'] = item[1]
					elif (item[0] == 'secsuntilconnectiontimeout'):	generalConfig['secsUntilConnectionTimeOut'] = item[1]
					
			except ConfigParser.NoSectionError, e:
				# Section pcptch does not exist => try the next ini-file
				logger.warning("No section 'pcptch' in ini-file '%s'" % iniFile)
			
			
			try:
				for item in ini.items('general'):
					if item[0].lower() in ['askbeforeinst', 'windomain', 'opsiservertype', 'opsiserviceurl']:
						continue
					generalConfig[item[0]] = item[1]
			
			except ConfigParser.NoSectionError, e:
				# Section general does not exist => try the next ini-file
				logger.warning("No section 'general' in ini-file '%s'" % iniFile)
				continue
		
		return generalConfig
	
	
	def deleteGeneralConfig(self, objectId):
		# General config for special host => edit <hostname>.sysconf
		basename = self.getHostname(objectId)
		if (objectId == self._defaultDomain):
			# Global general config (all hosts) => edit global.sysconf
			basename = 'global'
		
		# Read the ini file
		try:
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		except BackendIOError, e:
			logger.warning("Cannot delete general config for object '%s': %s" % (objectId, e))
			self.createFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), mode=0660)
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		
		# Delete section pcptch if exists
		if ini.has_section("pcptch"):
			ini.remove_section("pcptch")
		
		if ini.has_section("general"):
			for (key, value) in ini.items('general'):
				if key.lower() in ['askbeforeinst', 'windomain', 'opsiservertype', 'opsiserviceurl']:
					continue
				ini.remove_option("general", key)
		
		# Write back ini file
		self.writeIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), ini)
	
	# -------------------------------------------------
	# -     NETWORK FUNCTIONS                         -
	# -------------------------------------------------
	def setNetworkConfig(self, config, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
		self.deleteNetworkConfig(objectId)
		
		basename = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# Global network config (all hosts) => edit global.sysconf
			basename = 'global'
		else:
			# Network config for special host => edit <hostname>.sysconf
			basename = self.getHostname(objectId)
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		except BackendIOError:
			self.createFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), mode=0660)
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		
		if ( config.get('utilsDrive') or config.get('depotDrive') or config.get('configDrive') or 
		     config.get('utilsUrl') or config.get('depotUrl') or config.get('configUrl') ):
			# Create section shareinfo if not exists
			if not ini.has_section("shareinfo"):
				ini.add_section("shareinfo")
			
			# Set shareinfo options
			if config.get('utilsDrive'): 	ini.set('shareinfo', 'utilsdrive', config.get('utilsDrive') )
			if config.get('depotDrive'): 	ini.set('shareinfo', 'depotdrive', config.get('depotDrive') )
			if config.get('configDrive'):	ini.set('shareinfo', 'configdrive',config.get('configDrive') )
			if config.get('utilsUrl'): 	ini.set('shareinfo', 'utilsurl', config.get('utilsUrl') ) 
			if config.get('depotUrl'): 	ini.set('shareinfo', 'depoturl', config.get('depotUrl') )
			if config.get('configUrl'): 	ini.set('shareinfo', 'configurl', config.get('configUrl') )
		
		if config.get('winDomain') or config.get('nextBootServiceURL') or config.get('nextBootServerType'):
			if not ini.has_section("general"):
				ini.add_section("general")
			if config.get('winDomain'): 		ini.set('general', 'windomain', config.get('winDomain'))
			if config.get('nextBootServiceURL'): 	ini.set('general', 'opsiserviceurl', config.get('nextBootServiceURL'))
			if config.get('nextBootServerType'): 	ini.set('general', 'opsiservertype', config.get('nextBootServerType'))
		
		# Write back ini file
		self.writeIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), ini)
		
	def getNetworkConfig_hash(self, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
		# Global network config
		iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
		if (objectId != self.getServerId()) and (objectId != self._defaultDomain):
			# Add client specific network config
			iniFiles.append( "%s.sysconf" % os.path.join(self.__opsiTFTPDir, self.getHostname(objectId)) )
		
		networkConfig = { 
			'opsiServer': 	self.getServerId(objectId),
			'utilsDrive':	'',
			'depotDrive':	'',
			'configDrive':	'',
			'utilsUrl':	'',
			'depotUrl':	'',
			'configUrl':	'',
			'winDomain':	'',
			'nextBootServerType': '',
			'nextBootServiceURL': ''}
		
		# Read the ini-files, priority of client-specific values is higher
		# than global values
		for iniFile in iniFiles:
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				logger.debug(e)
				continue
			
			try:
				for item in ini.items('shareinfo'):
					if   (item[0] == 'utilsdrive'):	networkConfig['utilsDrive'] = item[1]
					elif (item[0] == 'depotdrive'):	networkConfig['depotDrive'] = item[1]
					elif (item[0] == 'configdrive'):	networkConfig['configDrive'] = item[1]
					elif (item[0] == 'utilsurl'):		networkConfig['utilsUrl'] = item[1]
					elif (item[0] == 'depoturl'):		networkConfig['depotUrl'] = item[1]
					elif (item[0] == 'configurl'):		networkConfig['configUrl'] = item[1]
					
			except ConfigParser.NoSectionError, e:
				# Section shareinfo does not exist => try the next ini-file
				logger.warning("No section 'shareinfo' in ini-file '%s'" % iniFile)
				continue
			
			try:
				for item in ini.items('general'):
					if   (item[0] == 'windomain'):		networkConfig['winDomain'] = item[1]
					elif (item[0] == 'opsiservertype'):	networkConfig['nextBootServerType'] = item[1]
					elif (item[0] == 'opsiserviceurl'):	networkConfig['nextBootServiceURL'] = item[1]
					
			except ConfigParser.NoSectionError, e:
				# Section general does not exist => try the next ini-file
				logger.warning("No section 'general' in ini-file '%s'" % iniFile)
				continue
		
		# Check if all needed values are set
		if (not networkConfig['opsiServer']
		    or not networkConfig['utilsDrive'] or not networkConfig['depotDrive'] or not networkConfig['configDrive']
		    or not networkConfig['utilsUrl'] or not networkConfig['depotUrl'] or not networkConfig['configUrl']):
			raise BackendMissingDataError("Networkconfig for object '%s' incomplete" % objectId)
		
		return networkConfig
	
	def deleteNetworkConfig(self, objectId):
		
		if not objectId:
			objectId = self.getServerId()
		
		basename = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# Global network config (all hosts) => edit global.sysconf
			basename = 'global'
		else:
			# Network config for special host => edit <hostname>.sysconf
			basename = self.getHostname(objectId)
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		except BackendIOError, e:
			logger.warning("Cannot delete network config for object '%s': %s" % (objectId, e))
			self.createFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), mode=0660)
			ini = self.readIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename))
		
		# Delete section shareinfo if exists
		if ini.has_section("shareinfo"):
			if not ini.has_option('shareinfo', 'pcpatchpass'):
				ini.remove_section("shareinfo")
			else:
				for (key, value) in ini.items('shareinfo'):
					if (key.lower() == 'pcpatchpass'):
						continue
					ini.remove_option('shareinfo', key)
		
		if ini.has_section("general"):
			for option in ('windomain', 'opsiservertype', 'opsiserviceurl'):
				if ini.has_option('general', option):
					ini.remove_option('general', option)
		
		# Write back ini file
		self.writeIniFile("%s.sysconf" % os.path.join(self.__opsiTFTPDir, basename), ini)
	
	
	# -------------------------------------------------
	# -     HOST FUNCTIONS                            -
	# -------------------------------------------------
	def createServer(self, serverName, domain, description=None, notes=None):
		return serverName.lower() + '.' + domain.lower()
	
	def createClient(self, clientName, domain=None, description=None, notes=None, ipAddress=None, hardwareAddress=None):
		if not re.search(CLIENT_ID_REGEX, clientName):
			raise BackendBadValueError("Unallowed char in hostname")
		
		if not domain:
			domain = self._defaultDomain
		if not description:
			description = ''
		if not notes:
			notes = ''
		
		clientId = clientName.lower() + '.' + domain.lower()
		
		# Copy the client configuration prototype
		if not os.path.exists( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) ):
			self.createFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)), mode=0660 )
			pcproto = self.openFile(os.path.join(self.__pcpatchDir, 'pcproto.ini'), 'r')
			try:
				newclient = self.openFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)), 'w' )
			except BackendIOError, e:
				self.closeFile(pcproto)
				raise
			
			newclient.write(pcproto.read())
			self.closeFile(pcproto)
			self.closeFile(newclient)
			
		# Add host info to client's config file
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set("info", "description", description.replace('\n', '\\n'))
		ini.set("info", "notes", notes.replace('\n', '\\n'))
		ini.set("info", "lastseen", '')
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)), ini )
		
		# Create tftp file
		if not os.path.exists( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) ):
			self.createFile( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)), mode=0664 )
		
		logger.debug("Client created")
		
		# Return the clientid
		return clientId
	
	def deleteServer(self, serverId):
		logger.error("Cannot delete server '%s': Not supported by File backend." % serverId)
	
	def deleteClient(self, clientId):
		# Delete client from groups
		try:
			ini = self.readIniFile(self.__groupsFile)
			for groupId in ini.sections():
				logger.debug("Searching for client '%s' in group '%s'" % (clientId, groupId))
				if ini.has_option(groupId, clientId):
					ini.remove_option(groupId, clientId)
					logger.info("Client '%s' removed from group '%s'" % (clientId, groupId))
			
			self.writeIniFile(self.__groupsFile, ini)
		except BackendIOError, e:
			pass
		
		# Delete sysconf file
		if os.path.exists( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) ):
			self.deleteFile( "%s" % os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) )
		# Delete ini file
		if os.path.exists( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) ):
			self.deleteFile( "%s" % os.path.join(self.__pcpatchDir, self.getIniFile(clientId))  )
	
	def setHostLastSeen(self, hostId, timestamp):
		logger.debug("Setting last-seen timestamp for host '%s' to '%s'" % (hostId, timestamp))
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)) )
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'lastseen', timestamp)
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)), ini )
	
	def setHostDescription(self, hostId, description):
		logger.debug("Setting description for host '%s' to '%s'" % (hostId, description))
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)) )
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'description', description.replace('\n', '\\n'))
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)), ini )
	
	def setHostNotes(self, hostId, notes):
		logger.debug("Setting notes for host '%s' to '%s'" % (hostId, notes))
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)) )
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'notes', notes.replace('\n', '\\n'))
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)), ini )
	
	def getHardwareInformation_listOfHashes(self, hostId):
		# Deprecated
		try:
			ini = self.readIniFile( "%s.hw" % os.path.join(self.__pclogDir, self.getHostname(hostId)) )
		except BackendIOError, e:
			logger.warning("No hardware info for host '%s' found: %s" % (hostId, e))
			return []
		except ConfigParser.MissingSectionHeaderError, e:
			logger.warning("Hardware info file of host '%s' is no ini file: %s" % (hostId, e))
			f = self.openFile( "%s.hw" % os.path.join(self.__pclogDir, self.getHostname(hostId)) )
			content = f.read()
			f.close()
			return [ { "hardwareinfo": content } ]
			
			
		hardware = []
		
		for section in ini.sections():
			info = {}
			info['id'] = section
			for (key, value) in ini.items(section, raw=True):
				if   (key.lower() == 'busaddress'):			key = 'busAddress'
				elif (key.lower() == 'macaddress'):			key = 'macAddress'
				elif (key.lower() == 'subsystemvendor'):		key = 'subsystemVendor'
				elif (key.lower() == 'subsystemname'):			key = 'subsystemName'
				elif (key.lower() == 'externalclock'):			key = 'externalClock'
				elif (key.lower() == 'maxspeed'):			key = 'maxSpeed'
				elif (key.lower() == 'currentspeed'):			key = 'currentSpeed'
				elif (key.lower() == 'totalwidth'):			key = 'totalWidth'
				elif (key.lower() == 'datawidth'):			key = 'dataWidth'
				elif (key.lower() == 'formfactor'):			key = 'formFactor'
				elif (key.lower() == 'banklocator'):			key = 'bankLocator'
				elif (key.lower() == 'internalconnectorname'):		key = 'internalConnectorName'
				elif (key.lower() == 'internalconnectortype'):		key = 'internalConnectorType'
				elif (key.lower() == 'externalconnectorname'):		key = 'externalConnectorName'
				elif (key.lower() == 'externalconnectortype'):		key = 'externalConnectorType'
				try:
					info[key] = json.read(value)
				except Exception, e:
					info[key] = ''
					logger.warning("File: %s, section: '%s', option '%s': %s" \
							% ( os.path.join(self.__pclogDir, self.getHostname(hostId)), section, key, e))
			
			hardware.append(info)
		
		return hardware
	
	def getHardwareInformation_hash(self, hostId):
		hostId = hostId.lower()
		ini = None
		try:
			ini = self.readIniFile( "%s.hw" % os.path.join(self.__pclogDir, hostId) )
		except BackendIOError, e:
			logger.warning("No hardware info for host '%s' found: %s" % (hostId, e))
			return []
		
		info = {}
		for section in ini.sections():
			dev = {}
			for (key, value) in ini.items(section):
				try:
					dev[key] = json.read(value)
				except:
					dev[key] = ''
			
			section = '_'.join(section.split('_')[:-1])
			if not info.has_key(section):
				info[section] = []
			
			info[section].append(dev)
		
		return info
	
	def setHardwareInformation(self, hostId, info):
		hostId = hostId.lower()
		if not type(info) is dict:
			raise BackendBadValueError("Hardware information must be dict")
		
		self.deleteHardwareInformation(hostId)
		
		iniFile = "%s.hw" % os.path.join(self.__pclogDir, hostId)
		
		if not os.path.exists(iniFile):
			self.createFile(iniFile, 0660)
		ini = self.readIniFile(iniFile)
		
		for (key, values) in info.items():
			n = 0
			for value in values:
				section = '%s_%d' % (key, n)
				ini.add_section(section)
				for (opsiName, opsiValue) in value.items():
					if type(opsiValue) is unicode:
						ini.set(section, opsiName, json.write(opsiValue.encode('utf-8')))
					else:
						ini.set(section, opsiName, json.write(opsiValue))
				n += 1
		
		self.writeIniFile(iniFile, ini)
	
	def deleteHardwareInformation(self, hostId):
		hostId = hostId.lower()
		try:
			self.deleteFile( "%s.hw" % os.path.join(self.__pclogDir, hostId) )
		except Exception, e:
			logger.error("Failed to delete hardware information for host '%s': %s" % (hostId, e))
	
	def getHost_hash(self, hostId):
		logger.notice("Getting infos for host '%s'" % hostId)
		
		if (hostId in self._aliaslist()):
			return { "hostId": hostId, "description": "Depotserver", "notes": "", "lastSeen": "" }
		
		info = {
			"hostId": 	hostId,
			"description":	"",
			"notes":	"",
			"lastSeen":	"",
			"created":	"" }
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(hostId)) )
		
		if ini.has_section('info'):
			if ini.has_option('info', 'description'):
				info['description'] = ini.get('info', 'description').replace('\\n', '\n')
			if ini.has_option('info', 'notes'):
				info['notes'] = ini.get('info', 'notes').replace('\\n', '\n')
			if ini.has_option('info', 'lastseen'):
				info['lastSeen'] = ini.get('info', 'lastseen')
		else:
			logger.warning("Ini file '%s' has no section 'info'" % \
				os.path.join(self.__pcpatchDir, self.getIniFile(hostId)) )
		
		if not info['description']:
			if os.name == "posix":
				# Open /etc/hosts file and search for a comment behind host's entry
				hostname = self.getHostname(hostId)
				found = False
				done = False
				etcHosts = self.openFile('/etc/hosts', 'r')
				for line in etcHosts.readlines():
					if (line.find(hostname) == -1):
						continue
					
					parts = line.split()
					for part in parts:
						if (part == hostId or part == hostname):
							commentStart = line.find('#')
							if (commentStart != -1):
								# Comment found
								info['description'] = line[commentStart+1:].strip()
								found = True
							else:
								logger.info("Cannot get comment for host '%s' from file '/etc/hosts'" % hostId)
							
							done = True
							break
					if done:
						break
				etcHosts.close()
				
				if not found:
					# Host not found in /etc/hosts
					logger.info("Cannot find host '%s' in file '/etc/hosts'" % hostId)
			else:
				logger.info("Host lookup not yet implemented for this OS")
		return info
		
	def getClients_listOfHashes(self, serverId=None, depotIds=[], groupId=None, productId=None, installationStatus=None, actionRequest=None, productVersion=None, packageVersion=None):
		""" Returns a list of client-ids which are connected 
		    to the server with the specified server-id. 
		    If no server is specified, all registered clients are returned """
		
		if productId:
			productId = productId.lower()
		
		if groupId and not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		if (serverId and serverId not in self._aliaslist()):
			raise BackendMissingDataError("Can only access data on server: %s" % ', '.join(self._aliaslist()) )
		try:
			files = os.listdir(self.__pcpatchDir)
		except OSError, e:
			raise BackendIOError(e)
		
		hostIds = []
		if groupId:
			try:
				ini = self.readIniFile(self.__groupsFile)
			except BackendIOError, e:
				raise BackendMissingDataError("Group '%s' does not exist: %s" % (groupId, e) )
						
			if not ini.has_section(groupId):
				raise BackendMissingDataError("Group '%s' does not exist" % groupId)
			
			for (key, value) in ini.items(groupId):
				if (value == '0'):
					logger.notice("Skipping host '%s' in group '%s' (value = 0)" % (key, groupId))
					continue
				if ( key.find(self._defaultDomain) == -1):
					key = '.'.join(key, self._defaultDomain)
				try:
					hostIds.append( key.encode('ascii') )
				except Exception, e:
					logger.error("Skipping hostId: '%s': %s" % (key, e))
			
		else:
			for filename in files:
				if (filename.endswith('.ini') and filename != 'pcproto.ini' and filename != 'pathnams.ini'):
					hostId = self.getHostId(filename)
					if hostId not in hostIds:
						try:
							hostIds.append( hostId.encode('ascii') )
						except Exception, e:
							logger.error("Skipping hostId: '%s': %s" % (hostId, e))
					
		if installationStatus or actionRequest or productVersion or packageVersion:
			filteredHostIds = []
			
			productVersionC = None
			productVersionS = None
			if productVersion not in ('', None):
				productVersionC = '='
				match = re.search('^\s*([<>]?=?)\s*([\w\.]+)\s*$', productVersion)
				if not match:
					raise BackendBadValueError("Bad productVersion: '%s'" % productVersion)
				productVersionC = match.group(1)
				productVersionS = match.group(2)
			
			packageVersionC = None
			packageVersionS = None
			if packageVersion not in ('', None):
				packageVersionC = '='
				match = re.search('^\s*([<>]?=?)\s*([\w\.]+)\s*$', packageVersion)
				if not match:
					raise BackendBadValueError("Bad productVersion: '%s'" % packageVersion)
				packageVersionC = match.group(1)
				packageVersionS = match.group(2)
			
			logger.info("Filtering hostIds by productId: '%s', installationStatus: '%s', actionRequest: '%s', productVersion: '%s', packageVersion: '%s'" \
				% (productId, installationStatus, actionRequest, productVersion, packageVersion))
			productStates = self.getProductStates_hash(hostIds)
			for hostId in hostIds:
				if productStates.has_key(hostId):
					for state in productStates[hostId]:
						if productId and (state.get('productId') != productId):
							continue
						
						if installationStatus and (installationStatus != state['installationStatus']):
							continue
						
						if actionRequest and (actionRequest != state['actionRequest']):
							continue
						
						if productVersion not in ('', None):
							v = state.get('productVersion')
							if not v: v = '0'
							if not Tools.compareVersions(v, productVersionC, productVersionS):
								continue
						if packageVersion not in ('', None):
							v = state.get('packageVersion')
							if not v: v = '0'
							if not Tools.compareVersions(v, packageVersionC, packageVersionS):
								continue
							
						logger.info("Host %s matches filter" % hostId)
						filteredHostIds.append(hostId)
						break
				else:
					logger.warning("Cannot get installationStatus/actionRequests for host '%s': %s" 
								% (hostId, e) )
				
			hostIds = filteredHostIds
		
		infos = []
		defaultDepotId = self.getDepotId()
		for hostId in hostIds:
			try:
				info = self.getHost_hash(hostId)
				info['depotId'] = defaultDepotId
				infos.append(info)
			except BackendIOError, e:
				logger.error(e)
		
		return infos
		
		
	def getClientIds_list(self, serverId=None, depotIds=[], groupId=None, productId=None, installationStatus=None, actionRequest=None, productVersion=None, packageVersion=None):
		clientIds = []
		for info in self.getClients_listOfHashes(serverId, depotIds, groupId, productId, installationStatus, actionRequest, productVersion, packageVersion):
			clientIds.append( info.get('hostId') )
		return clientIds

	def getServerIds_list(self):
		return [ self.getServerId() ]
	
	def getServerId(self, clientId=None):
		# Return hostid of localhost
		return self.getHostId(socket.gethostname())

	def getDepotIds_list(self):
		return self.getServerIds_list()
		
	def getDepotId(self, clientId=None):
		return self.getServerId()
	
	def getDepot_hash(self, depotId):
		depotId = self._preProcessHostId(depotId)
		return {
			"description" : "",
			"notes" : "",
			"network" : "0.0.0.0/0",
			"depotLocalUrl" : "file:///opt/pcbin/install",
			"depotRemoteUrl" : "smb://%s/opt_pcbin/install" % depotId.split('.')[0],
			"repositoryLocalUrl" : "file:///var/lib/opsi/products",
			"repositoryRemoteUrl" : "webdavs://%s:4447/products" % depotId,
			"repositoryMaxBandwidth" : 0
		}
	
	def deleteDepot(self, depotId):
		depotId = self._preProcessHostId(depotId)
		logger.error("Cannot delete depot '%s': not implemented in File backend" % depotId)
		return
	
	def getOpsiHostKey(self, hostId):
		hostId = hostId.lower()
		# Open the file containing the host keys
		pckeys = self.openFile(self.__pckeyFile, 'r')
		# Read and close file
		lines = pckeys.readlines()
		self.closeFile(pckeys)
		# Search matching entry
		i=0
		for line in lines:
			i+=1
			line = line.strip()
			if not line:
				continue
			if line.startswith('#') or line.startswith(';'):
				continue
			if (line.find(':') == -1):
				logger.error("Parsing error in file '%s', line %s: '%s'" % (self.__pckeyFile, i, line))
				continue
			(hostname, key) = line.split(':', 1)
			hostname = hostname.strip()
			if (hostname.lower() == self.getHostname(hostId)):
				# Entry found => return key
				return key.strip()
		# No matching entry found => raise error
		raise BackendMissingDataError("Cannot find opsiHostKey for host '%s' in file '%s'" % (hostId, self.__pckeyFile))
	
	def setOpsiHostKey(self, hostId, opsiHostKey):
		hostId = hostId.lower()
		# Open, read and close host key file
		pckeys = self.openFile(self.__pckeyFile, 'r')
		lines = pckeys.readlines()
		self.closeFile(pckeys)
		
		exists = False
		
		for i in range( len(lines) ):
			if lines[i].lower().startswith( self.getHostname(hostId) + ':' ):
				# Host entry exists => change key
				lines[i] = self.getHostname(hostId) + ':' + opsiHostKey + "\n"
				exists = True
				break;
		if not exists:
			# Host key does not exist => add line
			lines.append(self.getHostname(hostId) + ':' + opsiHostKey + "\n")
		
		# Writeback file
		pckeys = self.openFile(self.__pckeyFile, 'w')
		pckeys.writelines(lines)
		self.closeFile(pckeys)
	
	def deleteOpsiHostKey(self, hostId):
		hostId = hostId.lower()
		# Delete host from pckey file
		pckeys = self.openFile(self.__pckeyFile, 'r')
		lines = pckeys.readlines()
		self.closeFile(pckeys)
		
		lineNum = -1
		for i in range( len(lines) ):
			if lines[i].lower().startswith( self.getHostname(hostId) + ':' ):
				lineNum = i
				break;
		
		if (lineNum == -1):
			# Host not found
			return
		
		pckeys = self.openFile(self.__pckeyFile, 'w')
		for i in range( len(lines) ):
			if (i == lineNum):
				continue
			print >> pckeys, lines[i],
		self.closeFile(pckeys)
	
	def getMacAddresses_list(self, hostId):
		macs = []
		for hw in self.getHardwareInformation_listOfHashes(hostId):
			if (hw.get('class') == 'ETHERNET_CONTROLLER'):
				mac = hw.get('macAddress')
				if mac:
					macs.append(mac.lower())
		return macs
		#raise BackendMissingDataError("Cannot get mac address for host '%s' from harware-info." % hostId)
	
	def createGroup(self, groupId, members = [], description = ""):
		if not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		if ( type(members) != type([]) and type(members) != type(()) ):
			members = [ members ]
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile(self.__groupsFile)
		except BackendIOError:
			self.createFile(self.__groupsFile, mode=0660)
			ini = self.readIniFile(self.__groupsFile)
		
		if ini.has_section(groupId):
			ini.remove_section(groupId)
		ini.add_section(groupId)
		for member in members:
			ini.set(groupId, member, '1')
		
		# Write back ini file
		self.writeIniFile(self.__groupsFile, ini)
		
	def getGroupIds_list(self):
		try:
			ini = self.readIniFile(self.__groupsFile)
			return ini.sections()
		except BackendIOError, e:
			logger.warning("No groups found: %s" % e)
		return []
		
	def deleteGroup(self, groupId):
		if not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		ini = self.readIniFile(self.__groupsFile)
		if ini.has_section(groupId):
			ini.remove_section(groupId)
		# Write back ini file
		self.writeIniFile(self.__groupsFile, ini)
	
	# -------------------------------------------------
	# -     PASSWORD FUNCTIONS                        -
	# -------------------------------------------------
	def getPcpatchPassword(self, hostId):
		# Open global.sysconf and hosts sysconfig file and read pcpatchpass option from section shareinfo
		
		password = None
		
		if (hostId == self.getServerId()):
			f = open(self.__passwdFile)
			for line in f.readlines():
				if line.startswith('pcpatch:'):
					password = line.split(':')[1].strip()
					break
			f.close()
			if not password:
				raise Exception("Failed to get pcpatch password for host '%s' from '%s'" % (hostId, self.__passwdFile))
			
			return password
		
		iniFiles = [ 	os.path.join(self.__opsiTFTPDir, "global.sysconf"), 
				os.path.join(self.__opsiTFTPDir, self.getSysconfFile(hostId)) ]
		
		for iniFile in iniFiles:
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				logger.warning(e)
				continue
			try:
				password = ini.get('shareinfo', 'pcpatchpass')
			
			except ConfigParser.NoSectionError:
				logger.warning("No section 'shareinfo' in ini-file '%s'" % iniFile)
				continue
			except ConfigParser.NoOptionError:
				logger.warning("No option 'pcpatchpass' in ini-file '%s'" % iniFile)
				continue
			except Exception, e:
				logger.logException(e)
				continue
			
		if not password:
			raise BackendMissingDataError("Cannot find pcpatch password for host '%s'" % hostId)
		return password
	
	def setPcpatchPassword(self, hostId, password):
		if (hostId == self.getServerId()):
			lines = []
			f = open(self.__passwdFile)
			for line in f.readlines():
				if line.startswith('pcpatch:'):
					continue
				lines.append(line)
			f.close()
			lines.append('pcpatch:%s\n' % password)
			
			f = open(self.__passwdFile, 'w')
			f.writelines(lines)
			f.close()
			
			return
		
		iniFile = os.path.join(self.__opsiTFTPDir, self.getSysconfFile(hostId))
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError:
			logger.warning("Sysconf file '%s' for host '%s' does not exists, trying to create..." \
					% (iniFile, hostId))
			self.createFile(iniFile, mode=0664)
			ini = self.readIniFile(iniFile)
		
		if not ini.has_section("shareinfo"):
			ini.add_section("shareinfo")
		
		ini.set("shareinfo", "pcpatchpass", password)
		
		self.writeIniFile(iniFile, ini)
		
	# -------------------------------------------------
	# -     PRODUCT FUNCTIONS                         -
	# -------------------------------------------------
	def lockProduct(self, productId, depotIds=[]):
		return
	
	def unlockProduct(self, productId, depotIds=[]):
		return
	
	def getProductLocks_hash(self, depotIds=[]):
		return {}
	
	def createProduct(self, productType, productId, name, productVersion, packageVersion, licenseRequired=0,
			   setupScript="", uninstallScript="", updateScript="", alwaysScript="", onceScript="",
			   priority=0, description="", advice="", productClassNames=(), pxeConfigTemplate='',
			   windowsSoftwareIds=[], depotIds=[]):
		
		if not re.search(PRODUCT_ID_REGEX, productId):
			raise BackendBadValueError("Unallowed chars in productId!")
		
		productId = productId.lower()
		
		if (productType == 'localboot'):
			# Add section <productid>-install to pathnams.ini 
			ini = self.readIniFile(os.path.join(self.__pcpatchDir, "pathnams.ini"))
			if ini.has_section(productId + "-install"):
				ini.remove_section(productId + "-install")
			ini.add_section(productId + "-install")
			
			for script in [ setupScript, uninstallScript, updateScript, alwaysScript, onceScript ]:
				if not script:
					# Script does not exist => next script
					continue
				
				if not script.startswith(productId + '\\'):
					##filename = productId + script
					logger.warning("Script path '%s' does not start with '\\%s'" % (script, productId))
				
				option = 'setupwinst'
				if   (script == uninstallScript): 	option = 'deinstallwinst'
				elif (script == updateScript): 	option = 'updatewinst'
				elif (script == alwaysScript): 	option = 'alwayswinst'
				elif (script == onceScript): 		option = 'oncewinst'
				# Set script filename
				ini.set(productId + "-install", option, script)
			
			# Writeback pathnams.ini
			self.writeIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini"), ini )
			
			# Read product info file
			ini = self.readIniFile(self.__productsFile)
			# Create section <productid>-info
			if ini.has_section(productId + "-info"):
				ini.remove_section(productId + "-info")
			ini.add_section(productId + "-info")
			# Set product infos
			ini.set(productId + "-info", 'produktname', name)
			ini.set(productId + "-info", 'hinweis', advice.replace('\r', '').replace('\n', '\\n'))
			ini.set(productId + "-info", 'infotext', description.replace('\r', '').replace('\n', '\\n'))
			ini.set(productId + "-info", 'version', productVersion)
			ini.set(productId + "-info", 'packageVersion', packageVersion)
			# Write prouct info file
			self.writeIniFile(self.__productsFile, ini)
			
			# Add product entry to client configuartion prototype
			ini = self.readIniFile( os.path.join(self.__pcpatchDir, 'pcproto.ini') )
			if not ini.has_section("products-installed"):
				ini.add_section("products-installed")
			ini.set("products-installed", productId, 'off')
			self.writeIniFile( os.path.join(self.__pcpatchDir, 'pcproto.ini'), ini )
			
			# Try to add product entry to every client's configuration file
			errorList = []		
			for clientId in self.getClientIds_list():
				try:
					installationStatus = self.getProductInstallationStatus_hash(productId, clientId)
				except BackendMissingDataError, e:
					# No installation status found => set to not_installed
					self.setProductInstallationStatus(productId, clientId, 'not_installed')
				except BackendIOError, e:
					# IO error occured => append error to error list, but continue with next client
					err = "Failed to register product '%s' for client '%s': '%s'" % (productId, clientId, e)
					errorList.append(err)
					logger.error(err)
			if ( len(errorList) > 0 ):
				# One or more errors occured => raise error
				raise BackendIOError( ', '.join(errorList) )
			
		elif (productType == 'netboot'):
			# Open global.sysconf
			ini = self.readIniFile( os.path.join(self.__opsiTFTPDir, "global.sysconf") )
			if ini.has_section(productId):
				logger.warning("Product '%s' already exists, overwriting")
				ini.remove_section(productId)
			
			# Create product's section in global.sysconf
			ini.add_section(productId)
			instscript = setupScript
			if not instscript:
				instscript = alwaysScript
			if not instscript:
				instscript = onceScript
			
			#ini.set(productId, 'instscript', instscript.split('/')[-1])
			#ini.set(productId, 'insturl', instscript[: (-1*len(instscript.split('/')[-1]))-1 ])
			ini.set(productId, 'instscript', instscript)
			self.writeIniFile( os.path.join(self.__opsiTFTPDir, "global.sysconf"), ini )
			
		elif (productType == 'server'):
			logger.warning("Nothing to do for product type 'server'")
		
		else:
			raise BackendBadValueError("Unknown product type '%s'" % productType)
			
	def deleteProduct(self, productId, depotIds=[]):
		
		productId = productId.lower()
		errorList = []
		
		# TODO: delete all client specific settings / installation status ???
		if productId in self.getProductIds_list('netboot'):
			# Product is a netboot-product
			iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
			for clientId in self.getClientIds_list():
				iniFiles.append( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) )
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					if not ini.has_section(productId):
						continue
					ini.remove_section(productId)
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Cannot delete product '%s': %s" % (productId, e)
					errorList.append(err)
					logger.error(err)
			
			iniFiles = [ os.path.join(self.__pcpatchDir, "pcproto.ini") ]
			for clientId in self.getClientIds_list():
				iniFiles.append( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					if ini.has_section('%s-state' % productId):
						ini.remove_section('%s-state' % productId)
					if ini.has_section('netboot_product_states') and ini.has_option('netboot_product_states', productId):
						ini.remove_option('netboot_product_states', productId)
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Cannot delete product '%s': %s" % (productId, e)
					errorList.append(err)
					logger.error(err)
		
		else:
			# Remove from pathnams.ini
			ini = self.readIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini") )
			ini.remove_section(productId + "-install")
			self.writeIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini"), ini )
			
			# Remove from productsFile
			ini = self.readIniFile(self.__productsFile)
			for section in ini.sections():
				if (section.lower().startswith(productId + "-info") or
				    section.lower().startswith(productId + "-requires") ):
					   ini.remove_section(section)
			self.writeIniFile(self.__productsFile, ini)
			
			errorList = []
			iniFiles = [ os.path.join(self.__pcpatchDir, "pcproto.ini") ]
			for clientId in self.getClientIds_list():
				iniFiles.append( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
			
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					if ini.has_section(productId + "-install"):
						ini.remove_section(productId + "-install")
					if ini.has_section('%s-state' % productId):
						ini.remove_section('%s-state' % productId)
					if ini.has_section('products-installed') and ini.has_option('products-installed', productId):
						ini.remove_option('products-installed', productId)
					self.writeIniFile(iniFile, ini)
				
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Failed to delete product '%s': %s" % (productId, e)
					errorList.append(err)
					logger.error(err)
					continue
		
		if ( len(errorList) > 0 ):
			# One or more errors occured => raise error
			raise BackendIOError( ', '.join(errorList) )
		
	def getProduct_hash(self, productId, depotId=None):
		
		productId = productId.lower()
		
		if productId in self.getProductIds_list('netboot'):
			
			# Product is a netboot-product
			product = { 	
				'name': 		 productId,
				'advice': 	 	 '',
				'priority': 		 0,
				'licenseRequired': 	 False,
				'productClassProvided':	 [ 'netBoot' ] }
			try:
				# Read product's section from global.sysconf
				ini = self.readIniFile( os.path.join(self.__opsiTFTPDir, "global.sysconf") )
				setupScript = ini.get(productId, 'instscript')
				try:
					insturl = ini.get(productId, 'insturl')
					if insturl:
						if insturl.endswith('/'):
							insturl = insturl[:-1]
						setupScript = insturl + '/' + setupScript
				except ConfigParser.NoOptionError, e:
					pass
				
				product['setupScript'] = setupScript
			
			except BackendIOError, e:
				raise BackendMissingDataError( "Cannot open '%s': %s" % (os.path.join(self.__opsiTFTPDir, "global.sysconf"), e) )
			except ConfigParser.NoSectionError, e:
				raise BackendMissingDataError( "Section not found in '%s': %s" % (os.path.join(self.__opsiTFTPDir, "global.sysconf"), e) )
			except ConfigParser.NoOptionError, e:
				raise BackendMissingDataError( "Option not found in '%s': %s" % (os.path.join(self.__opsiTFTPDir, "global.sysconf"), e) )
			
			# Get product creation timestamp (creation date of product installation dir)
			try:
				product['creationTimestamp'] = Tools.timestamp( os.path.getmtime(os.path.join(self.__depotDir, productId)) ) 
			except OSError, e:
				# Setup script not found => log warning but do not raise error
				logger.warning( "Installation dir '%s' of net-boot-product '%s' not found: %s" \
					% (os.path.join(self.__depotDir, productId), productId, e) )
				product['creationTimestamp'] = '00000000000000'
			
			# Return product hash (dict)
			return product
		
		# Product is a local-boot product
		(setupPath, setupWinst, deinstallWinst, updateWinst, onceWinst, alwaysWinst) = ('', None, None, None, None, None)
		
		# Get product scripts from pathnams.ini
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini") )
		try:
			for item in ini.items(productId + "-install"):
				if   (item[0] == 'setuppath'):      setupPath = item[1]
				elif (item[0] == 'setupwinst'):     setupWinst = item[1]
				elif (item[0] == 'deinstallwinst'): deinstallWinst = item[1]
				elif (item[0] == 'updatewinst'):    updateWinst = item[1]
				elif (item[0] == 'oncewinst'):      onceWinst = item[1]
				elif (item[0] == 'alwayswinst'):    alwaysWinst = item[1]
		except ConfigParser.NoSectionError, e:
			raise BackendMissingDataError("Script paths not found for product '%s': %s" % (productId, e))
		logger.debug("setupPath = %s, setupWinst = %s, deinstallWinst = %s, updateWinst = %s, alwaysWinst = %s, onceWinst = %s" % 
			(setupPath, setupWinst, deinstallWinst, updateWinst, alwaysWinst, onceWinst ) )
		
		###if not setupPath:
		###	raise BackendMissingDataError("SetupPath not found for product '%s'" % productId)
		#if not setupPath:
		#	setupPath = productId
		
		timestamp = '00000000000000'
		if not os.path.isdir( os.path.join(self.__depotDir, productId) ):
			logger.error( "SetupPath '%s' does not exist or is no directory" % os.path.join(self.__depotDir, productId) )
		else:
			# Create product creation timestamp (modification time of installation dir)
			timestamp = Tools.timestamp( os.path.getmtime( os.path.join(self.__depotDir, productId) ) ) 
		
		# Add ending '\' to path if not exists
		if setupPath and not setupPath.endswith('\\'):
			setupPath += '\\'
		
		
		product = { 	'name': 		 productId,
				'advice': 	 	 '',
				'priority': 		 0,
				'licenseRequired': 	 False,
				'productClassProvided': [],
				'creationTimestamp': 	 timestamp }
		if setupWinst:     product['setupScript'] = setupPath + setupWinst
		if deinstallWinst: product['uninstallScript'] = setupPath + deinstallWinst
		if updateWinst:    product['updateScript'] = setupPath + updateWinst
		if alwaysWinst:    product['alwaysScript'] = setupPath + alwaysWinst
		if onceWinst:      product['onceScript'] = setupPath + onceWinst
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		try:
			for item in ini.items(productId + "-info"):
				if (len(item) > 1 and item[1]):
					if   (item[0] == 'produktname'):
						product['name'] = item[1]
					elif (item[0] == 'hinweis'):
						product['advice'] = item[1].replace('\\n', '\n')
					elif (item[0] == 'infotext'):
						product['description'] = item[1].replace('\\n', '\n')
					elif   (item[0] == 'version' or item[0] == 'productversion'):
						product['productVersion'] = item[1]
					elif   (item[0] == 'packageversion'):
						product['packageVersion'] = item[1]
		except ConfigParser.NoSectionError, e:
			pass
		
		# Return product hash (dict)
		return product
	
	def getProductIds_list(self, productType=None, objectId=None, installationStatus=None):
		productIds = []
		if (not productType or productType == 'localboot'):
			# Get all <productid>-info sections from product info file
			ini = self.readIniFile(self.__productsFile)
			for section in ini.sections():
				if section.lower().endswith("-info"):
					productIds.append(section[:-5])
					logger.debug("Added productId '%s'" % section[:-5])
			if not productIds:
				logger.warning("No local-boot products exist")
			
			if (objectId and objectId != self.getServerId()):
				actionOrState = ''
				if (installationStatus == 'installed'):
					actionOrState = 'on'
				elif (installationStatus == 'uninstalled' or installationStatus == 'not_installed'):
					actionOrState = 'off'
				
				# Get all products marked with actionOrState from hosts config file
				ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) )
				try:
					for item in ini.items("products-installed"):
						if (len(item) > 1 and item[1].lower() != actionOrState):
							logger.debug("State of '%s' is '%s', removing from list..." % (item[0], item[1]))
							try:
								del productIds[item[0]]
							except:
								logger.error("Client '%s' defines state for product '%s' which does not exist in '%s'" \
										% (objectId, item[0], self.__productsFile) )
				except ConfigParser.NoSectionError, e:
					raise BackendMissingDataError("Cannot find %s products for host '%s': %s" \
								% (installationStatus, objectId, e))
			
			logger.debug("Localboot products matching installationStatus '%s' on objectId '%s': %s" \
							% (installationStatus, objectId, productIds))
		
		if (not productType or productType == 'netboot'):
			if objectId and (objectId != self.getServerId()) and (installationStatus == 'installed'):
					netBootProduct = None
					iniFiles = [ 	os.path.join(self.__opsiTFTPDir, "global.sysconf"), 
							os.path.join(self.__opsiTFTPDir, self.getSysconfFile(objectId)) ]
					
					for iniFile in iniFiles:
						try:
							ini = self.readIniFile(iniFile)
						except BackendIOError, e:
							logger.debug(e)
							continue
						try:
							netBootProduct = ini.get('general', 'os')
						except ConfigParser.NoSectionError, e:
							logger.warning("No section 'general' in ini-file '%s'" % iniFile)
							continue
						except ConfigParser.NoOptionError, e:
							logger.warning("No option 'os' in ini-file '%s'" % iniFile)
							continue
					if not netBootProduct:
						logger.warning("Cannot find installed net-boot product for host '%s'" % hostId)
					else:
						productIds.append(netBootProduct)
				
			else:
				# Get all sectionnames containing option "instscript"
				ini = self.readIniFile( os.path.join(self.__opsiTFTPDir, "global.sysconf") )
				for section in ini.sections():
					try:
						ini.get(section, 'instscript')
						productIds.append(str(section))
					except:
						pass
				if not productIds:
					logger.warning("No net-boot products exist")
		
		if (not productType or productType == 'server'):
			logger.warning("No server products exist")
		
		return productIds
	
	
	def getProductInstallationStatus_hash(self, productId, objectId):
		
		productId = productId.lower()
		
		status = { 
			'productId':		productId,
			'installationStatus':	'not_installed',
			'productVersion':	'',
			'packageVersion':	'',
			'lastStateChange':	'',
			'deploymentTimestamp':	'' }
		
		if (objectId in self._aliaslist()):
			if productId in self.getProductIds_list():
				status['installationStatus'] = 'installed'
			return status
			
		productType = None
		if productId in self.getProductIds_list('netboot'):
			productType = 'netboot'
		elif productId in self.getProductIds_list('localboot'):
			productType = 'localboot'
		else:
			raise Exception("product '%s': is neither localboot nor netboot product" % productId)
		
		# Read hosts config file
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) )
		if (productType == 'locaboot'):
			if ini.has_section('products-installed'):
				try:
					value = ini.get('products-installed', productId)
					if (value.lower() in ['on', 'deinstall', 'update']):
						status['installationStatus'] = 'installed'
					elif (value.lower() == 'off'): 
						status['installationStatus'] = 'not_installed'
					elif (value.lower() == 'failed'): 
						status['installationStatus'] = 'failed'
				except ConfigParser.NoOptionError, e:
					pass
		
		elif (productType == 'netboot'):
			if ini.has_section('netboot_product_states'):
				try:
					value = ini.get('netboot_product_states', productId)
					installationStatus = value.lower().split(':', 1)[0]
					
					if installationStatus not in getPossibleProductInstallationStatus():
						logger.error("Unknown installationStatus '%s' in ini file '%s'" \
								% (installationStatus, os.path.join(self.__pcpatchDir, self.getIniFile(objectId))) )
					else:
						status['installationStatus'] = installationStatus
				except ConfigParser.NoOptionError, e:
					pass
		
		try:
			for item in ini.items('%s-state' % productId):
				if (item[0].lower() == 'productversion'):
					status['productVersion'] = item[1]
				elif (item[0].lower() == 'packageversion'):
					status['packageVersion'] = item[1]
				elif (item[0].lower() == 'laststatechange'):
					status['lastStateChange'] = item[1]
		
		except ConfigParser.NoSectionError, e:
			logger.warning("Cannot get version information for product '%s' on host '%s': %s" \
					% (productId, objectId, e) )
		
		return status
	
	def getProductInstallationStatus_listOfHashes(self, objectId):
		installationStatus = []
		
		if (objectId in self._aliaslist()):
			for productId in self.getProductIds_list():
				installationStatus.append( { 'productId': productId, 'installationStatus': 'installed' } )
			return installationStatus
		
		for productId in self.getProductIds_list():
			installationStatus.append( { 'productId': productId, 'installationStatus': 'not_installed', 'actionRequest': 'none' } )
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) )
		if ini.has_section('products-installed'):
			for i in range(len(installationStatus)):
				try:
					value = ini.get("products-installed", installationStatus[i].get('productId'))
					status = 'not_installed'
					if (value.lower() in ['on', 'deinstall', 'update']):
						status = 'installed'
					elif (value.lower() == 'failed'): 
						status = 'failed'
					
					installationStatus[i]['installationStatus'] = status
				except ConfigParser.NoOptionError, e:
					continue
		
		if ini.has_section('netboot_product_states'):
			for i in range(len(installationStatus)):
				try:
					value = ini.get('netboot_product_states', installationStatus[i].get('productId'))
					status = value.lower().split(':', 1)[0]
					
					if status not in getPossibleProductInstallationStatus():
						logger.error("Unknown installationStatus '%s' in ini file '%s'" \
								% (status, os.path.join(self.__pcpatchDir, self.getIniFile(objectId))) )
						continue
					
					if (installationStatus[i]['installationStatus'] != status):
						logger.warning("Sections 'products-installed' and '%s' defining different installationStatus, section '%s' wins" \
								% ('netboot_product_states', 'netboot_product_states') )
					
					installationStatus[i]['installationStatus'] = status
				except ConfigParser.NoOptionError, e:
					continue
		
		return installationStatus
	
	def setProductState(self, productId, objectId, installationStatus="", actionRequest="", productVersion="", packageVersion="", lastStateChange="", licenseKey=""):
		productId = productId.lower()
		
		if objectId in self._aliaslist():
			return
		
		productType = None
		if productId in self.getProductIds_list('netboot'):
			productType = 'netboot'
		elif productId in self.getProductIds_list('localboot'):
			productType = 'localboot'
		else:
			raise Exception("product '%s': is neither localboot nor netboot product" % productId)
		
		if not installationStatus:
			installationStatus = 'undefined'
		if not installationStatus in getPossibleProductInstallationStatus():
			raise BackendBadValueError("InstallationStatus has unsupported value '%s'" %  installationStatus )
		
		if not actionRequest:
			actionRequest = 'undefined'
		if not actionRequest in getPossibleProductActions():
			raise BackendBadValueError("ActionRequest has unsupported value '%s'" % actionRequest)
		
		product = self.getProduct_hash(productId)
		
		if not lastStateChange:
			lastStateChange = Tools.timestamp()
		
		# Read client's config file, add or change option and write ini-file
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) )
		
		if not ini.has_section('%s-state' % productId):
			ini.add_section('%s-state' % productId)
		
		if (productType == 'localboot'):
			if not ini.has_section("products-installed"):
				ini.add_section("products-installed")
			
			currentValue = 'off'
			if ini.has_option("products-installed", productId):
				currentValue = ini.get("products-installed", productId)
			newValue = currentValue
			
			# Map new installation status values to old switches
			if (actionRequest != 'undefined'):
				if (actionRequest != 'none') or (currentValue not in ['on', 'off', 'failed']):
					newValue = actionRequest
					if (newValue == 'uninstall'):
						newValue = 'deinstall'
			elif (installationStatus == 'uninstalled'): 	newValue = 'off'
			elif (installationStatus == 'not_installed'): 	newValue = 'off'
			elif (installationStatus == 'installed'): 	newValue = 'on'
			elif (installationStatus == 'failed'): 	newValue = 'failed'
			
			logger.info("Setting product installation status '%s', product action request '%s' for product '%s' => value: '%s'" \
					% (installationStatus, actionRequest, productId, newValue))
			
			ini.set("products-installed", productId, newValue)
			
			if not productVersion:
				productVersion = ''
				if   (installationStatus == 'installed') or (installationStatus == 'installing') or (installationStatus == 'failed'):
					     productVersion = product.get('productVersion', '')
				elif (installationStatus == 'undefined') and \
				     ( (newValue == 'on') or (newValue == 'deinstall') or (newValue == 'failed') ):
					     productVersion = ini.get('%s-state' % productId, 'productversion', '')
			
			if not packageVersion:
				packageVersion = ''
				if   (installationStatus == 'installed') or (installationStatus == 'installing') or (installationStatus == 'failed'):
					     packageVersion = product.get('packageVersion', '')
				elif (installationStatus == 'undefined') and \
				     ( (newValue == 'on') or (newValue == 'deinstall') or (newValue == 'failed') ):
					     packageVersion = ini.get('%s-state' % productId, 'packageversion', '')
			
			
		elif (productType == 'netboot'):
			if not ini.has_section('netboot_product_states'):
				ini.add_section('netboot_product_states')
			
			(currentInstallationStatus, currentActionRequest) = ('undefined', 'undefined')
			
			try:
				value = ini.get('netboot_product_states', productId)
				if (value.lower().find(':') != -1):
					(currentInstallationStatus, currentActionRequest) = value.lower().split(':', 1)
				else:
					currentInstallationStatus = value.lower()
				
			except ConfigParser.NoOptionError, e:
				pass
			
			if not productVersion:
				productVersion = ''
				if   (installationStatus == 'installed') or (installationStatus == 'uninstalled') or \
				     (installationStatus == 'installing') or (installationStatus == 'failed'):
					     productVersion = product.get('productVersion', '')
				elif (installationStatus == 'undefined') and \
				     ( (currentInstallationStatus == 'installed') or (currentInstallationStatus == 'uninstalled') or \
				       (currentInstallationStatus == 'installing') or (currentInstallationStatus == 'failed') ):
					     productVersion = ini.get('%s-state' % productId, 'productversion', '')
			
			if not packageVersion:
				packageVersion = ''
				if   (installationStatus == 'installed') or (installationStatus == 'uninstalled') or \
				     (installationStatus == 'installing') or (installationStatus == 'failed'):
					     packageVersion = product.get('packageVersion', '')
				elif (installationStatus == 'undefined') and \
				     ( (currentInstallationStatus == 'installed') or (currentInstallationStatus == 'uninstalled') or \
				       (currentInstallationStatus == 'installing') or (currentInstallationStatus == 'failed') ):
					     packageVersion = ini.get('%s-state' % productId, 'packageversion', '')
			
			if (installationStatus == 'undefined') and currentInstallationStatus:
				installationStatus = currentInstallationStatus
				
			if (actionRequest == 'undefined') and currentActionRequest:
				actionRequest = currentActionRequest
			
			logger.info("Setting product version '%s', package version '%s' for product '%s'" \
					% (productVersion, packageVersion, productId))
			
			ini.set('netboot_product_states', productId, '%s:%s' % (installationStatus, actionRequest))
			
		logger.info("Setting product version '%s', package version '%s' for product '%s'" \
					% (productVersion, packageVersion, productId))
		
		ini.set('%s-state' % productId, 'productVersion', productVersion)
		ini.set('%s-state' % productId, 'packageVersion', packageVersion)
		ini.set('%s-state' % productId, 'lastStateChange', lastStateChange)
		
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)), ini)
		
		return
		# TODO
		
		if (installationStatus in ['not_installed', 'uninstalled']):
			logger.debug("Removing license key assignement for host '%s' and product '%s' if exists" \
					% (objectId, productId) )
			# Update licenses ini file
			try:
				ini = self.readIniFile(self.__licensesFile)
				if ini.has_section(productId):
					for (key, value) in ini.items(productId):
						if (value == objectId):
							ini.set(productId, key, '')
							self.writeIniFile(self.__licensesFile, ini)
							logger.info("License key assignement for host '%s' and product '%s' removed" \
									% (objectId, productId) )
							break
			except BackendIOError, e:
				logger.warning("Cannot update license file '%s': %s" % (self.__licensesFile, e))
			
		
		if not licenseKey:
			return
		
		# Read licenses ini file or create if not exists
		try:
			ini = self.readIniFile(self.__licensesFile)
		except BackendIOError:
			logger.warning("Cannot read license file '%s', trying to create" % self.__licensesFile)
			self.createFile(self.__licensesFile, mode=0660)
			ini = self.readIniFile(self.__licensesFile)
		
		if not ini.has_section(productId):
			ini.add_section(productId)
		
		ini.set(productId, licenseKey, objectId)
		
		# Write back ini file
		self.writeIniFile(self.__licensesFile, ini)
	
	def setProductInstallationStatus(self, productId, objectId, installationStatus, policyId="", licenseKey=""):
		self.setProductState(productId, objectId, installationStatus = installationStatus, licenseKey = licenseKey)
	
	def getPossibleProductActions_list(self, productId=None, depotId=None):
		
		if not productId:
			return POSSIBLE_FORCED_PRODUCT_ACTIONS
		
		actions = ['none']
		productId = productId.lower()
		
		if productId in self.getProductIds_list('netboot'):
			actions.append('setup')
			return actions
		
		# Get all action scripts set in pathnams.ini file
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini") )
		try:
			for item in ini.items(productId + "-install"):
				logger.debug(item)
				if   (item[0] == 'setupwinst'):	actions.append('setup')
				elif (item[0] == 'deinstallwinst'):	actions.append('uninstall')
				elif (item[0] == 'updatewinst'):	actions.append('update')
				elif (item[0] == 'oncewinst'):		actions.append('once')
				elif (item[0] == 'alwayswinst'):	actions.append('always')
		
		except ConfigParser.NoSectionError, e:
			raise BackendMissingDataError("Script paths not found for product '%s': %s" % (productId, e))	
		return actions
	
	def getPossibleProductActions_hash(self, depotId=None):
		
		actions = {}
		
		for productId in self.getProductIds_list('netboot'):
			actions[productId] = ['none', 'setup']
		
		# Get all action scripts set in pathnams.ini file
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, "pathnams.ini") )
		for section in ini.sections():
			if not section.endswith("-install"):
				continue
			productId = section[:-8]
			actions[productId] = ['none']
			for item in ini.items(productId + "-install"):
				if   (item[0] == 'setupwinst'):	actions[productId].append('setup')
				elif (item[0] == 'deinstallwinst'):	actions[productId].append('uninstall')
				elif (item[0] == 'updatewinst'):	actions[productId].append('update')
				elif (item[0] == 'oncewinst'):		actions[productId].append('once')
				elif (item[0] == 'alwayswinst'):	actions[productId].append('always')
		
		return actions
	
	def getProductActionRequests_listOfHashes(self, clientId):
		actionRequests = []
		# Read all actions set in client's config file and map them to the new values
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
		if ini.has_section('products-installed'):
			for item in ini.items("products-installed"):
				if (item[1].lower() == 'setup'):
					actionRequests.append( { 'productId': item[0], 'actionRequest': 'setup' } )
				elif (item[1].lower() == 'deinstall'):
					actionRequests.append( { 'productId': item[0], 'actionRequest': 'uninstall' } )
				elif (item[1].lower() == 'update'):
					actionRequests.append( { 'productId': item[0], 'actionRequest': 'update' } )
				elif (item[1].lower() == 'once'):
					actionRequests.append( { 'productId': item[0], 'actionRequest': 'once' } )
				elif (item[1].lower() == 'always'):
					actionRequests.append( { 'productId': item[0], 'actionRequest': 'always' } )
		
		if ini.has_section('netboot_product_states'):
			for item in ini.items('netboot_product_states'):
				if (item[1].find(':') == -1):
					continue
				actionRequest = item[1].lower().split(':', 1)[1]
				if actionRequest not in getPossibleProductActions():
					logger.error("Unknown actionRequest '%s' in ini file '%s'" \
							% (actionRequest, os.path.join(self.__pcpatchDir, self.getIniFile(clientId))) )
					continue
				
				actionRequests.append( { 'productId': item[0], 'actionRequest': actionRequest } )
		
		return actionRequests
	
	def getDefaultNetBootProductId(self, clientId):
		netBootProduct = None
		# Get option "os" from sysconf files.
		# Priority of clients sysconf file higher than global.sysconf
		iniFiles = [ 	os.path.join(self.__opsiTFTPDir, "global.sysconf"), 
				os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) ]
		for iniFile in iniFiles:
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				logger.debug(e)
				continue
		
			try:
				netBootProduct = ini.get('general', 'os').strip()
				netBootProduct = netBootProduct.replace('\r', '')
				netBootProduct = netBootProduct.replace('\0', '')
			except (ConfigParser.NoSectionError, ConfigParser.NoOptionError), e:
				pass
		if not netBootProduct:	
			raise BackendMissingDataError("No default net-boot product found in global.sysconf and %s" % self.getSysconfFile(clientId) )
		return netBootProduct
	
	def setProductActionRequest(self, productId, clientId, actionRequest):
		self.setProductState(productId, clientId, actionRequest = actionRequest)
	
	def unsetProductActionRequest(self, productId, clientId):
		
		productId = productId.lower()
		
		productType = None
		if productId in self.getProductIds_list('netboot'):
			productType = 'netboot'
		elif productId in self.getProductIds_list('localboot'):
			productType = 'localboot'
		else:
			raise Exception("product '%s': is neither localboot nor netboot product" % productId)
		
		ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
		
		if (productType == 'localboot'):
			if ini.has_section('products-installed'):
				currentValue = None
				try:
					currentValue = ini.get("products-installed", productId)
				except ConfigParser.NoOptionError, e:
					pass
				
				# Installation status not known => Trying to guess it
				if (currentValue == 'deinstall'):
					ini.set("products-installed", productId, 'on')
				elif (currentValue == 'setup'):
					ini.set("products-installed", productId, 'off')
		
		elif (productType == 'netboot'):
			if not ini.has_section('netboot_product_states'):
				ini.add_section('netboot_product_states')
			
			installationStatus = ''
			try:
				value = ini.get('netboot_product_states', productId)
				installationStatus = value.lower().split(':', 1)[0]
			except ConfigParser.NoOptionError, e:
				pass
			ini.set('netboot_product_states', productId, '%s:%s' % (installationStatus, 'none'))
			
		if not ini.has_section("%s-state" % productId):
			ini.add_section("%s-state" % productId)
		ini.set("%s-state" % productId, 'lastStateChange',  Tools.timestamp())
		
		self.writeIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)), ini)
	
	def _getProductStates_hash(self, objectIds=[], productType=None):
		
		result = {}
		
		if not objectIds or ( (len(objectIds) == 1) and not objectIds[0] ):
			objectIds = self.getClientIds_list()
		elif ( type(objectIds) != type([]) and type(objectIds) != type(()) ):
			objectIds = [ objectIds ]
		
		productTypes = []
		if not productType or (productType == 'localboot'):
			productTypes.append('localboot')
		if not productType or (productType == 'netboot'):
			productTypes.append('netboot')
		
		for objectId in objectIds:
			result[objectId] = []
			for productType in productTypes:
				productIds = []
				if (productType == 'localboot'):
					productIds = self.getProductIds_list('localboot')
				elif (productType == 'netboot'):
					productIds = self.getProductIds_list('netboot')
				
				if (objectId in self._aliaslist()):
					for productId in productIds:
						result[objectId].append( { 	'productId': productId, 
										'installationStatus': 'installed',
										'actionRequest': 'none' } )
					continue
				
				states = []
				
				iniFile = os.path.join(self.__pcpatchDir, self.getIniFile(objectId))
				ini = self.readIniFile(iniFile)
				
				for productId in productIds:
					productVersion = None
					packageVersion = None
					lastStateChange = None
					if ini.has_section('%s-state' % productId):
						for (key, value) in ini.items('%s-state' % productId):
							if (key.lower() == 'productversion'):
								productVersion = value
							elif (key.lower() == 'packageversion'):
								packageVersion = value
							elif (key.lower() == 'laststatechange'):
								lastStateChange = value
					
					states.append( { 	'productId':		productId, 
								'installationStatus':	'not_installed',
								'actionRequest':	'none',
								'productVersion':	productVersion,
								'packageVersion':	packageVersion,
								'lastStateChange':	lastStateChange,
								'deploymentTimestamp':	None } )
				
				if (productType == 'localboot') and ini.has_section('products-installed'):
					for i in range(len(states)):
						try:
							value = ini.get("products-installed", states[i].get('productId'))
							status = 'not_installed'
							action = 'none'
							
							if   (value.lower() == 'on'):
								status = 'installed'
							elif (value.lower() == 'setup'):
								action = 'setup'
							elif (value.lower() == 'deinstall'):
								status = 'installed'
								action = 'uninstall'
							elif (value.lower() == 'update'):
								status = 'installed'
								action = 'update'
							elif (value.lower() == 'once'):
								action = 'once'
							elif (value.lower() == 'always'):
								action = 'always'
							elif (value.lower() == 'failed'): 
								status = 'failed'
							
							states[i]['installationStatus'] = status
							states[i]['actionRequest'] = action
						except ConfigParser.NoOptionError, e:
							continue
				
				elif (productType == 'netboot') and ini.has_section('netboot_product_states'):
					for i in range(len(states)):
						try:
							value = ini.get('netboot_product_states', states[i].get('productId'))
							status = ''
							action = ''
							
							if (value.find(':') == -1):
								status = value
							else:
								(status, action) = value.lower().split(':', 1)
							
							if status and status not in getPossibleProductInstallationStatus():
								logger.error("Unknown installationStatus '%s' in ini file '%s'" \
										% (status, os.path.join(self.__pcpatchDir, self.getIniFile(objectId))) )
								status = ''
							
							if action and action not in getPossibleProductActions():
								logger.error("Unknown actionRequest '%s' in ini file '%s'" \
										% (action, os.path.join(self.__pcpatchDir, self.getIniFile(objectId))) )
								action = ''
							
							if status:
								states[i]['installationStatus'] = status
							if action:
								states[i]['actionRequest'] = action
						except ConfigParser.NoOptionError, e:
							continue
				
				result[objectId].extend(states)
		return result
	
	def getProductStates_hash(self, objectIds=[]):
		result = self.getLocalBootProductStates_hash(objectIds)
		for (key, value) in self.getNetBootProductStates_hash(objectIds).items():
			if not result.has_key(key):
				result[key] = []
			result[key].extend(value)
		
		return result
	
	def getNetBootProductStates_hash(self, objectIds=[]):
		return self._getProductStates_hash(objectIds, 'netboot')
	
	def getLocalBootProductStates_hash(self, objectIds=[]):
		return self._getProductStates_hash(objectIds, 'localboot')
	
	def getProductStates_hash(self, objectIds=[]):
		return self._getProductStates_hash(objectIds)
	
	def getProductPropertyDefinitions_hash(self, depotId=None):
		definitions = {}
		
		regex = re.compile('^(\S+)-property-(\S+)$', re.IGNORECASE)
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		for section in ini.sections():
			definition = {
				'name': 	'',
				'description':	'',
				'values':	[],
				'default':	''
			}
			
			match = re.search(regex, section)
			if not match:
				continue
			
			productId = match.group(1)
			definition['name'] = match.group(2)
			
			for item in ini.items(section):
				if   (item[0].lower() == 'description'):
					definition['description'] = item[1].replace('\\n', '\n')
				
				elif (item[0].lower() == 'values'):
					definition['values'] = item[1].split(',')
					for i in (range(len(definition['values']))):
						definition['values'][i] = definition['values'][i].strip()
				
				elif (item[0].lower() == 'default'):
					definition['default'] = item[1]
			
			if not definitions.has_key(productId):
				definitions[productId] = []
			
			definitions[productId].append(definition)
		
		return definitions
	
	def getProductPropertyDefinitions_listOfHashes(self, productId, depotId=None):
		definitions = []
		
		if productId in self.getProductIds_list('netboot'):
			return definitions
		
		regex = re.compile('^%s-property-(\S+)$' % productId, re.IGNORECASE)
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		for section in ini.sections():
			definition = {
				'name': 	'',
				'description':	'',
				'values':	[],
				'default':	''
			}
			
			match = re.search(regex, section)
			if not match:
				continue
			
			definition['name'] = match.group(1)
			
			for item in ini.items(section):
				if   (item[0].lower() == 'description'):
					definition['description'] = item[1].replace('\\n', '\n')
				
				elif (item[0].lower() == 'values'):
					definition['values'] = item[1].split(',')
					for i in (range(len(definition['values']))):
						definition['values'][i] = definition['values'][i].strip()
				
				elif (item[0].lower() == 'default'):
					definition['default'] = item[1]
			
			definitions.append(definition)
			
		return definitions
	
	def deleteProductPropertyDefinition(self, productId, name, depotIds=[]):
		
		if productId in self.getProductIds_list('netboot'):
			return
		
		regex = re.compile('^%s-property-%s$' % (productId, name), re.IGNORECASE)
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		found = False
		for section in ini.sections():
			if re.search(regex, section):
				found = True
				ini.remove_section(section)
				break
		
		if not found:
			raise BackendMissingDataError("Cannot delete product property definition '%s' of product '%s': no such section" \
					% (name, productId) )
		
		# Write product info file
		try:
			self.writeIniFile(self.__productsFile, ini)
		except BackendIOError, e:
			raise BackendIOError("Cannot delete product property definition '%s' of product '%s': %s" \
					% (name, productId, e) )
		
	def deleteProductPropertyDefinitions(self, productId, depotIds=[]):
		
		if productId in self.getProductIds_list('netboot'):
			return
		
		regex = re.compile('^%s-property-' % productId, re.IGNORECASE)
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		for section in ini.sections():
			if re.search(regex, section):
				ini.remove_section(section)
		
		try:
			self.writeIniFile(self.__productsFile, ini)
		except BackendIOError, e:
			raise BackendIOError("Cannot delete product property definitions of product '%s': %s" \
					% (productId, e) )
		
	def createProductPropertyDefinition(self, productId, name, description=None, defaultValue=None, possibleValues=[], depotIds=[]):
		
		productId = productId.lower()
		name = name.lower()
		
		if productId in self.getProductIds_list('netboot'):
			return
		
		section = '%s-property-%s' % (productId, name)
		
		# Read product info file
		ini = self.readIniFile(self.__productsFile)
		
		if ini.has_section(section):
			ini.remove_section(section)
		
		ini.add_section(section)
		if description:
			ini.set(section, 'description', description.replace('\r', '').replace('\n', '\\n'))
		if possibleValues:
			ini.set(section, 'values', ','.join(possibleValues))
		if defaultValue:
			ini.set(section, 'default', defaultValue)
		
		try:
			self.writeIniFile(self.__productsFile, ini)
		except BackendIOError, e:
			raise BackendIOError("Failed to create product property definition '%s' for product '%s': %s" \
					% (name, productId, e) )
	
	def getProductProperties_hash(self, productId, objectId = None):
		
		if not objectId or (objectId.lower() == self.getDepotId().lower()):
			objectId = self._defaultDomain
		
		productId = productId.lower()
		properties = {}
		
		if productId in self.getProductIds_list('netboot'):
			# Product is an net-boot product
			logger.debug("Product %s is an net-boot product" % productId)
			iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
			if (objectId != self._defaultDomain):
				# Append client specific sysconf file
				iniFiles.append( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(objectId)) )
		
			#properties = { 'debug': 'off' }
			
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
				except BackendIOError, e:
					logger.debug(e)
					# Sysconf file not found => try next file
					continue
				#try:
				#	properties['debug'] = ini.get('general', 'debug')
				#except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
				#	# Option debug not found
				#	pass
				try:
					for item in ini.items(productId):
						if (item[0] != 'insturl' and item[0] != 'instscript'):
							# Some property found
							properties[item[0]] = item[1]
				except ConfigParser.NoSectionError, e:
					logger.warning("No section '%s' in ini-file '%s'" % (productId, iniFile))
					continue
			return properties
		
		# Product is a local-boot product
		logger.debug("Product %s is an local-boot product" % productId)
		ini = None
		if (objectId == self._defaultDomain):
			# No specific client selected => use config prototype
			ini = self.readIniFile( os.path.join(self.__pcpatchDir, 'pcproto.ini') )
		else:
			# Specific client selected => use client's config
			ini = self.readIniFile( os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) )
		
		try:
			# Read all properites from section <productid>-install
			for item in ini.items(productId + "-install"):
				properties[ item[0] ] = item[1]
		except ConfigParser.NoSectionError, e:
			pass
		
		return properties
		
	def setProductProperties(self, productId, properties, objectId = None):
		
		if not objectId or (objectId.lower() == self.getDepotId().lower()):
			objectId = self._defaultDomain
		
		productId = productId.lower()
		
		if productId in self.getProductIds_list('netboot'):
			# The product is a net-boot product
			iniFile = None
			if (objectId == self._defaultDomain):
				iniFile = os.path.join(self.__opsiTFTPDir, "global.sysconf")
			else:
				iniFile = os.path.join(self.__opsiTFTPDir, self.getSysconfFile(objectId))
			
			ini = self.readIniFile(iniFile)
			
			if not ini.has_section(productId):
				ini.add_section(productId)
			
			# Set all properties
			for (key, value) in properties.items():
				ini.set(productId, key, value)
			
			globalProperties = self.getProductProperties_hash(productId)
			
			# Remove properties matching global properties
			for (key, value) in ini.items(productId):
				if globalProperties.has_key(key) and (globalProperties[key] == value):
					ini.remove_option(productId, key)
			
			# Remove section if empty
			if ( len(ini.items(productId)) == 0 ):
				ini.remove_section(productId)
			
			# Write ini file
			self.writeIniFile(iniFile, ini)
			
			return
		
		# The product is a local-boot product
		setIniFiles = []
		iniFiles = []
		if (objectId == self._defaultDomain):
			# No specific client selected => change config files of all clients and prototype file
			setIniFiles = [ os.path.join(self.__pcpatchDir, "pcproto.ini") ]
			for clientId in self.getClientIds_list():
				iniFiles.append( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
		else:
			# Specific client selected => change client's config only
			setIniFiles = [ os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) ]
		
		errorList = []
		iniFiles.extend(setIniFiles)
		for iniFile in iniFiles:
			ini = None
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				# Error occured => log error, add error to error list but continue
				err = "Failed to read ini-file '%s': %s" % (iniFile, e)
				errorList.append(err)
				logger.error(err)
				continue
			
			if iniFile in setIniFiles:
				# Recreate section if exists
				if ini.has_section(productId + "-install"):
					ini.remove_section(productId.lower() + "-install")
				ini.add_section(productId + "-install")
				# Set all properties
				for (key, value) in properties.items():
					ini.set(productId + "-install", key, value)
			else:
				clientProperties = dict(properties)
				if ini.has_section(productId + "-install"):
					# Keep old property values
					for (key, value) in ini.items(productId + "-install"):
						if not clientProperties.has_key(key):
							continue
						clientProperties[key] = value
					ini.remove_section(productId.lower() + "-install")
				ini.add_section(productId + "-install")
				
				# Update properties
				remove = []
				for item in ini.items(productId + "-install"):
					remove.append(item[0])
				
				# Set all properties
				for (key, value) in clientProperties.items():
					ini.set(productId + "-install", key, value)
			
			# Write ini file
			try:
				self.writeIniFile(iniFile, ini)
			except BackendIOError, e:
				# Error occured => log error, add error to error list but continue
				err = "Cannot set product properties for product '%s' and client '%s': %s" % (productId, clientId, e)
				errorList.append(err)
				logger.error(err)
				continue
		
		if ( len(errorList) > 0 ):
			# One or more errors occured => raise esception
			raise BackendIOError( ', '.join(errorList) )
	
	def deleteProductProperty(self, productId, property, objectId = None):
		
		if not objectId or (objectId.lower() == self.getDepotId().lower()):
			objectId = self._defaultDomain
		
		productId = productId.lower()
		
		iniFiles = []
		errorList = []
		
		if productId in self.getProductIds_list('netboot'):
			# The product is a net-boot product
			if (objectId == self._defaultDomain):
				iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
				for clientId in self.getClientIds_list():
					iniFiles.append( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) )
			else:
				iniFiles = [ os.path.join(self.__opsiTFTPDir, self.getSysconfFile(objectId)) ]
			
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					if not ini.has_section(productId) or not ini.has_option(productId, property):
						continue
					
					ini.remove_option(productId, property)
					
					# Remove section if empty
					if ( len(ini.items(productId)) == 0 ):
						ini.remove_section(productId)
					
					# Write ini file
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Failed to deleteProductProperty '%s' from iniFile '%s': %s" % (property, iniFile, e)
					errorList.append(err)
					logger.error(err)
					continue
			
		else:
			# The product is a local-boot product
			if (objectId == self._defaultDomain):
				# No specific client selected => change config files of all clients and prototype file
				iniFiles = [ os.path.join(self.__pcpatchDir, "pcproto.ini") ]
				for clientId in self.getClientIds_list():
					iniFiles.append( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
			else:
				# Specific client selected => change client's config only
				iniFiles = [ os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) ]
			
			for iniFile in iniFiles:
				ini = None
				try:
					ini = self.readIniFile(iniFile)
					
					if not ini.has_section(productId + "-install") or not ini.has_option(productId + "-install", property):
						continue
					
					ini.remove_option(productId + "-install", property)
					
					# Remove section if empty
					if ( len(ini.items(productId + "-install")) == 0 ):
						ini.remove_section(productId + "-install")
					
					# Write ini file
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Failed delete product property '%s' for product '%s' from ini-file '%s': %s" % (property, productId, iniFile, e)
					errorList.append(err)
					logger.error(err)
					continue
		
		if ( len(errorList) > 0 ):
			# One or more errors occured => raise esception
			raise BackendIOError( ', '.join(errorList) )
		
	
	def deleteProductProperties(self, productId, objectId = None):
		if not objectId or (objectId.lower() == self.getDepotId().lower()):
			objectId = self._defaultDomain
		
		productId = productId.lower()
		
		iniFiles = []
		errorList = []
		
		if productId in self.getProductIds_list('netboot'):
			# The product is a net-boot product
			if (objectId == self._defaultDomain):
				iniFiles = [ os.path.join(self.__opsiTFTPDir, "global.sysconf") ]
				for clientId in self.getClientIds_list():
					iniFiles.append( os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) )
			else:
				iniFiles = [ os.path.join(self.__opsiTFTPDir, self.getSysconfFile(objectId)) ]
			
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					
					if not ini.has_section(productId):
						continue
					
					newItems = {}
					for (key, value) in ini.items(productId):
						if (key in ['insturl', 'instscript']):
							newItems[key] = value
					
					ini.remove_section(productId)
					if newItems:
						ini.add_section(productId)
						for (key, value) in newItems.items():
							ini.set(productId, key, value)
					
					# Write ini file
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Failed to delete product properties for product '%s' from ini-file '%s': %s" % (productId, iniFile, e)
					errorList.append(err)
					logger.error(err)
					continue
			
		else:
			# The product is a local-boot product
			if (objectId == self._defaultDomain):
				# No specific client selected => change config files of all clients and prototype file
				iniFiles = [ os.path.join(self.__pcpatchDir, "pcproto.ini") ]
				for clientId in self.getClientIds_list():
					iniFiles.append( os.path.join(self.__pcpatchDir, self.getIniFile(clientId)) )
			else:
				# Specific client selected => change client's config only
				iniFiles = [ os.path.join(self.__pcpatchDir, self.getIniFile(objectId)) ]
			
			for iniFile in iniFiles:
				ini = None
				try:
					ini = self.readIniFile(iniFile)
				
					if not ini.has_section(productId + "-install"):
						continue
					
					ini.remove_section(productId + "-install")
					
					# Write ini file
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# Error occured => log error, add error to error list but continue
					err = "Failed to delete product properties for product '%s' from ini-file '%s': %s" % (productId, iniFile, e)
					errorList.append(err)
					logger.error(err)
					continue
		
		if ( len(errorList) > 0 ):
			# One or more errors occured => raise esception
			raise BackendIOError( ', '.join(errorList) )	
	
	def getProductDependencies_listOfHashes(self, productId=None, depotId=None):
		pattern = re.compile('^(\S+)-(requires.*)$')
		
		if productId:
			productId = productId.lower()
		
		dependencyList = []
		ini = self.readIniFile(self.__productsFile)
		# Get dependencies for all known dependency types
		for section in ini.sections():
			
			match = re.search(pattern, section)
			if not match:
				continue
			
			pid = match.group(1)
			dependencyType = match.group(2)
			
			if productId and (pid != productId):
				continue
			if dependencyType not in ('requires', 'requires_after', 'requires_before', 'requires_deinstall'):
				if (dependencyType != 'info'):
					logger.error("Unkown dependency-type '%s' in file '%s', section '%s'" \
						% (dependencyType, self.__productsFile, section))
				continue
			
			typeName = ''
			action = 'setup'
			if (dependencyType == 'requires_after'):
				typeName = 'after'
			if (dependencyType == 'requires_before'):
				typeName = 'before'
			if (dependencyType == 'requires_deinstall'):
				typeName = ''
				action = 'uninstall'
			try:
				for item in ini.items(section):
					installationStatus = ''
					actionRequired = ''
					if   (item[1].lower() == 'on'):     	installationStatus = 'installed'
					elif (item[1].lower() == 'off'):    	installationStatus = 'not_installed'
					elif (item[1].lower() == 'update'): 	actionRequired = 'update'
					elif (item[1].lower() == 'setup'):  	actionRequired = 'setup'
					elif (item[1].lower() == 'deinstall'): actionRequired = 'uninstall'
					if (installationStatus or action):
						dependencyList.append( 
							{ 'productId': pid,
							  'action': action,
						 	  'requiredProductId': item[0].lower(),
							  'requiredAction': actionRequired,
							  'requiredInstallationStatus': installationStatus,
							  'requirementType': typeName } )
							  
			except ConfigParser.NoSectionError, e:
				continue
		
		return dependencyList
	
	def createProductDependency(self, productId, action, requiredProductId="", requiredProductClassId="", requiredAction="", requiredInstallationStatus="", requirementType="", depotIds=[]):
		productId = productId.lower()
		requiredProductId = requiredProductId.lower()
		
		try:
			pd = ProductDependency(productId, action, requiredProductId, requiredProductClassId, 
						requiredAction, requiredInstallationStatus, requirementType)
		except Exception, e:
			raise BackendBadValueError(e)
		
		if not pd.requiredProductId:
			# This backend does not handle product classes yet
			pd.requiredProductId = pd.requiredProductClassId
		
		ini = self.readIniFile(self.__productsFile)
		
		section = pd.productId + '-requires'
		if (pd.action == 'uninstall'):
			pd.requirementType = 'deinstall'
		if (pd.requirementType):
			section += '_' + pd.requirementType
		if not ini.has_section(section):
			ini.add_section(section)
		
		installationStatusOrAction = ''
		if   (pd.requiredInstallationStatus == 'installed'):		installationStatusOrAction = 'on'
		elif (pd.requiredInstallationStatus == 'not_installed'):	installationStatusOrAction = 'off'
		elif (pd.requiredInstallationStatus == 'uninstalled'):		installationStatusOrAction = 'off'
		elif (pd.requiredAction == 'uninstall'):			installationStatusOrAction = 'deinstall'
		elif (pd.requiredAction == 'update'):				installationStatusOrAction = 'update'
		elif (pd.requiredAction == 'reinstall'):			installationStatusOrAction = 'setup'
		elif (pd.requiredAction == 'setup'):				installationStatusOrAction = 'setup'
		
		ini.set(section, pd.requiredProductId, installationStatusOrAction)
		self.writeIniFile(self.__productsFile, ini)
		
	def deleteProductDependency(self, productId, action="", requiredProductId="", requiredProductClassId="", requirementType="", depotIds=[]):
		
		productId = productId.lower()
		requiredProductId = requiredProductId.lower()
		
		if action and not action in getPossibleProductActions():
			raise BackendBadValueError("Action '%s' is not known" % action)
		#if not requiredProductId and not requiredProductClassId:
		#	raise BackendBadValueError("Either a required product or a required productClass must be set")
		if requirementType and requirementType not in getPossibleRequirementTypes():
			raise BackendBadValueError("Requirement type '%s' is not known" % requirementType)
		
		if not requiredProductId and requiredProductClassId:
			# This backend does not handle product classes yet
			requiredProductId = requiredProductClassId
		
		ini = self.readIniFile(self.__productsFile)
		
		sections = []
		for section in ini.sections():
			if not section.startswith(productId + '-requires'):
				continue
			if requirementType and not (section == productId + '-requires' + '_' + requirementType):
				continue
			if action and (action == 'uninstall') and not (section == productId + '-requires_deinstall'):
				continue
			sections.append(section)
		
		for section in sections:
			if requiredProductId:
				try:
					ini.remove_option(section, requiredProductId)
				except ConfigParser.NoOptionError, e:
					logger.warning(e)
			else:
				ini.remove_section(section)
		
		self.writeIniFile(self.__productsFile, ini)
		
	
	def createLicenseKey(self, productId, licenseKey):
		productId = productId.lower()
		if productId in self.getProductIds_list('netboot'):
			raise NotImplementedError("License managment for netboot-products not yet supported")
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile(self.__licensesFile)
		except BackendIOError:
			logger.warning("Cannot read license file '%s', trying to create" % self.__licensesFile)
			self.createFile(self.__licensesFile, mode=0660)
			ini = self.readIniFile(self.__licensesFile)
		
		if not ini.has_section(productId):
			ini.add_section(productId)
		
		ini.set(productId, licenseKey, '')
		
		# Write back ini file
		self.writeIniFile(self.__licensesFile, ini)
		
	def getLicenseKeys_listOfHashes(self, productId):
		productId = productId.lower()
		if productId in self.getProductIds_list('netboot'):
			raise NotImplementedError("License managment for netboot-products not yet supported")
		
		# Read the ini file
		try:
			ini = self.readIniFile(self.__licensesFile)
		except BackendIOError, e:
			logger.error("Cannot get license keys for product '%s': %s" % (productId, e))
			return []
		
		if not ini.has_section(productId):
			logger.error("Cannot get license keys for product '%s': Section missing" % productId)
			return []
		
		licenses = []
		for (key, value) in ini.items(productId):
			licenses.append( { "licenseKey": key, "hostId": value } )
		return licenses

	def getLicenseKey(self, productId, clientId):
		productId = productId.lower()
		licenseKey = ''
		
		if productId in self.getProductIds_list('netboot'):
			# The product is an net-boot product
			iniFiles = [ 
				os.path.join(self.__opsiTFTPDir, "global.sysconf"),
				os.path.join(self.__opsiTFTPDir, self.getSysconfFile(clientId)) ]
			
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					licenseKey = ini.get(productId, 'productkey')
				except BackendIOError, e:
					logger.debug(e)
					continue
				except ConfigParser.NoSectionError, e:
					logger.warning("No section '%s' in ini-file '%s'" % (productId, iniFile))
					continue
				except ConfigParser.NoOptionError, e:
					logger.warning("No option 'productkey' in ini-file '%s'" % iniFile)
			
			if not licenseKey:
				raise BackendMissingDataError('No product license found')
			return licenseKey
		
		freeLicenses = []
		for license in self.getLicenseKeys_listOfHashes(productId):
			hostId = license.get('hostId', '')
			if not hostId:
				freeLicenses.append(license.get('licenseKey', ''))
			elif (hostId == clientId):
				logger.info("Returning licensekey for product '%s' which is assigned to host '%s'"
						% (productId, clientId))
				return license.get('licenseKey', '')
		
		if (len(freeLicenses) > 0):
			logger.debug( "%s free license(s) found for product '%s'" % (len(freeLicenses), productId) )
			return freeLicenses[0]
		
		raise BackendMissingDataError("No more licenses available for product '%s'" % productId)
	
	
	def deleteLicenseKey(self, productId, licenseKey):
		productId = productId.lower()
		if productId in self.getProductIds_list('netboot'):
			raise NotImplementedError("License managment for netboot-products not yet supported")
		
		# Read the ini file
		try:
			ini = self.readIniFile(self.__licensesFile)
		except BackendIOError, e:
			logger.error("Cannot delete license key: %s" % e)
			return
		
		if not ini.has_section(productId):
			logger.error("Cannot delete license key: No section '%s' in file '%s'" \
						% (productId, self.__licensesFile))
			return
		
		if ini.has_option(productId, licenseKey):
			ini.remove_option(productId, licenseKey)
			
			# Write back ini file
			self.writeIniFile(self.__licensesFile, ini)


# ======================================================================================================
# =                                   CLASS TFTPFILEBACKEND                                            =
# ======================================================================================================
class TFTPFileBackend(TFTPFile, FileBackend):
	def __init__(self, address, args={}):
		''' TFTPFileBackend constructor. '''
		
		self.__address = address
		opsiTFTPDir = '/opsi'
		for (option, value) in args.items():
			if (option.lower() == 'opsitftpdir'):
				opsiTFTPDir = value
		
		args['opsitftpdir'] = opsiTFTPDir
		
		# Call FileBackend constructor
		FileBackend.__init__(self, args)
		# Call TFTPFile constructor
		TFTPFile.__init__(self, address = self.__address)
		
		
