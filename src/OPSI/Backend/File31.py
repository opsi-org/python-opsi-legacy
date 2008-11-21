#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - File31    =
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

__version__ = '0.2.7.14'

# Imports
import socket, os, time, re, ConfigParser, json, StringIO, stat

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
from OPSI.System import mkdir, rmdir
from OPSI import Tools

# Get logger instance
logger = Logger()
		
# ======================================================================================================
# =                                    CLASS FILE31BACKEND                                             =
# ======================================================================================================
class File31Backend(File, FileBackend):
	''' This class implements parts of the abstract class DataBackend '''
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' File31Backend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		self.__fileOpenTimeout = 2000
		self._defaultDomain = 'opsi.org'
		
		logger.debug("Getting Arguments:'%s'" % args)
		
		if os.name == 'nt':
			windefaultdir = os.getenv("ProgramFiles")+'\opsi.org\opsiconfd'
			self.__logDir = windefaultdir + '\\opsi\\logs'
			self.__pckeyFile = windefaultdir + '\\opsi\\pckeys'
			self.__passwdFile = windefaultdir + '\\opsi\\passwd'
			self.__groupsFile = windefaultdir + '\\opsi\\config\\clientgroups.ini'
			self.__licensesFile = windefaultdir + '\\opsi\\config\\licenses.ini'
			self.__clientConfigDir = windefaultdir + '\\opsi\\config\\clients'
			self.__globalConfigFile = windefaultdir + '\\opsi\\config\\global.ini'
			self.__depotConfigDir = windefaultdir + '\\opsi\\config\\depots'
			self.__clientTemplatesDir = windefaultdir + '\\opsi\\config\\templates'
			self.__defaultClientTemplateFile = windefaultdir + '\\opsi\\config\\templates\\pcproto.ini'
			self.__productLockFile = windefaultdir + '\\opsi\\config\\depots\\product.locks'
			self.__auditInfoDir = windefaultdir + '\\opsi\\audit'
		else:
			self.__pckeyFile = '/etc/opsi/pckeys'
			self.__passwdFile = '/etc/opsi/passwd'
			self.__logDir = '/var/log/opsi'
			self.__groupsFile = '/var/lib/opsi/config/clientgroups.ini'
			self.__licensesFile = '/var/lib/opsi/config/licenses.ini'
			self.__clientConfigDir = '/var/lib/opsi/config/clients'
			self.__globalConfigFile = '/var/lib/opsi/config/global.ini'
			self.__depotConfigDir = '/var/lib/opsi/config/depots'
			self.__clientTemplatesDir = '/var/lib/opsi/config/templates'
			self.__defaultClientTemplateFile = '/var/lib/opsi/config/templates/pcproto.ini'
			self.__productLockFile = '/var/lib/opsi/config/depots/product.locks'
			self.__auditInfoDir = '/var/lib/opsi/audit'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'logdir'):			self.__logDir = value
			elif (option.lower() == 'pckeyfile'):			self.__pckeyFile = value
			elif (option.lower() == 'passwdfile'):			self.__passwdFile = value
			elif (option.lower() == 'groupsfile'): 		self.__groupsFile = value
			elif (option.lower() == 'licensesfile'): 		self.__licensesFile = value
			elif (option.lower() == 'defaultdomain'): 		self._defaultDomain = value
			elif (option.lower() == 'clientconfigdir'): 		self.__clientConfigDir = value
			elif (option.lower() == 'globalconfigfile'):		self.__globalConfigFile = value
			elif (option.lower() == 'depotconfigdir'): 		self.__depotConfigDir = value
			elif (option.lower() == 'auditinfodir'): 		self.__auditInfoDir = value
			elif (option.lower() == 'clienttemplatesdir'): 	self.__clientTemplatesDir = value
			elif (option.lower() == 'defaultclienttemplatefile'): 	self.__defaultClientTemplateFile = value
			elif (option.lower() == 'productlockfile'): 		self.__productLockFile = value
			elif (option.lower() == 'fileopentimeout'): 		self.__fileOpenTimeout = value
			else:
				logger.warning("Unknown argument '%s' passed to File31Backend constructor" % option)
		
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
		(pcpatchUid, pcpatchGid, opsiconfdUid) = (-1, -1, -1)
		try:
			pcpatchUid = pwd.getpwnam('pcpatch')[2]
		except KeyError:
			errors.append('User pcpatch does not exist')
			logger.error('User pcpatch does not exist')
		try:
			opsiconfdUid = pwd.getpwnam('opsiconfd')[2]
		except KeyError:
			errors.append('User opsiconfd does not exist')
			logger.error('User opsiconfd does not exist')
		try:
			pcpatchGid = grp.getgrnam('pcpatch')[2]
		except KeyError:
			errors.append('Group pcpatch does not exist')
			logger.error('Group pcpatch does not exist')
		
		for f in [self.__pckeyFile, self.__passwdFile]:
			if not os.path.isfile(f):
				errors.append("File '%s' does not exist" % f)
				logger.error("File '%s' does not exist" % f)
			statinfo = os.stat(f)
			if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
				errors.append("File '%s' should be owned by group pcpatch" % f)
				logger.error("File '%s' should be owned by group pcpatch" % f)
			if (00660 != stat.S_IMODE(statinfo[stat.ST_MODE])):
				errors.append("Bad permissions for file '%s', should be 0660" % f)
				logger.error("Bad permissions for file '%s', should be 0660" % f)
		
		for depotId in self.getDepotIds_list():
			info = self.getDepot_hash(depotId)
			if not info['depotLocalUrl'].startswith('file://'):
				errors.append("Bad url '%s' for depotLocalUrl on depot '%s'" % (info['depotLocalUrl'], depotId))
				logger.error("Bad url '%s' for depotLocalUrl on depot '%s'" % (info['depotLocalUrl'], depotId))
			elif (depotId == self.getDepotId()):
				path = info['depotLocalUrl'][7:]
				statinfo = os.stat(path)
				if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
					errors.append("Directory '%s' should be owned by group pcpatch" % path)
					logger.error("Directory '%s' should be owned by group pcpatch" % path)
				if (02770 != stat.S_IMODE(statinfo[stat.ST_MODE])):
					errors.append("Bad permissions for directory '%s', should be 2770" % path)
					logger.error("Bad permissions for directory '%s', should be 2770" % path)
				for d in os.listdir(path):
						d = os.path.join(path, d)
						if not os.path.isdir(d):
							continue
						statinfo = os.stat(d)
						if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
							errors.append("Directory '%s' should be owned by group pcpatch" % d)
							logger.error("Directory '%s' should be owned by group pcpatch" % d)
						if (00770 != stat.S_IMODE(statinfo[stat.ST_MODE])):
							errors.append("Bad permissions for directory '%s', should be 0770" % d)
							logger.error("Bad permissions for directory '%s', should be 0770" % d)
				
			if not info['repositoryLocalUrl'].startswith('file://'):
				errors.append("Bad url '%s' for repositoryLocalUrl on depot '%s'" % (info['repositoryLocalUrl'], depotId))
				logger.error("Bad url '%s' for repositoryLocalUrl on depot '%s'" % (info['repositoryLocalUrl'], depotId))
			elif (depotId == self.getDepotId()):
				path = info['repositoryLocalUrl'][7:]
				if not os.path.isdir(path):
					errors.append("Directory '%s' for repositoryLocalUrl does not exist on depot '%s'" % (path, depotId))
					logger.error("Directory '%s' for repositoryLocalUrl does not exist on depot '%s'" % (path, depotId))
				else:
					statinfo = os.stat(path)
					if (pcpatchGid > -1) and (statinfo[stat.ST_GID] != pcpatchGid):
						errors.append("Directory '%s' should be owned by group pcpatch" % path)
						logger.error("Directory '%s' should be owned by group pcpatch" % path)
					if (02770 != stat.S_IMODE(statinfo[stat.ST_MODE])):
						errors.append("Bad permissions for directory '%s', should be 2770" % path)
						logger.error("Bad permissions for directory '%s', should be 2770" % path)
					for f in os.listdir(path):
						if f.startswith('.'):
							continue
						f = os.path.join(path, f)
						statinfo = os.stat(f)
						if (opsiconfdUid > -1) and (statinfo[stat.ST_UID] != opsiconfdUid):
							errors.append("File '%s' should be owned by opsiconfd" % f)
							logger.error("File '%s' should be owned by opsiconfd" % f)
						if (00600 != stat.S_IMODE(statinfo[stat.ST_MODE])):
							errors.append("Bad permissions for file '%s', should be 0600" % f)
							logger.error("Bad permissions for file '%s', should be 0600" % f)
		
		try:
			self.getClients_listOfHashes()
		except Exception, e:
			errors.append(str(e))
			logger.error(str(e))
		
		for depotId in self.getDepotIds_list():
			for productId in self.getProductIds_list(objectId = depotId):
				try:
					self.getProduct_hash(productId = productId, depotId = depotId)
				except Exception, e:
					errors.append(str(e))
					logger.error(str(e))
		
		return errors
	
	def getHostId(self, iniFile):
		parts = iniFile.lower().split('.')
		if (len(parts) < 4):
			raise BackendBadValueError("Bad name '%s' for ini-file" % iniFile)
		return '.'.join(parts[0:-1])
	
	def getClientIniFile(self, hostId):
		hostId = hostId.lower()
		return os.path.join(self.__clientConfigDir, hostId + '.ini')
	
	def getDepotIniFile(self, depotId):
		return os.path.join(self.__depotConfigDir, depotId, 'depot.ini')
	
	
	# -------------------------------------------------
	# -     LOGGING                                   -
	# -------------------------------------------------
	def writeLog(self, type, data, objectId=None, append=True):
		if type not in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError("Unknown log type '%s'" % type)
		
		if not objectId and type in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError("Log type '%s' requires objectId" % type)
		
		if not os.path.exists( os.path.join(self.__logDir, type) ):
			mkdir(os.path.join(self.__logDir, type), mode=0770)
		
		if objectId and (objectId.find('/') != -1):
			raise BackendBadValueError("Bad objectId '%s'" % objectId)
			
		logFile = os.path.join(self.__logDir, type, objectId + '.log')
		
		f = None
		if append:
			f = open(logFile, 'a+')
		else:
			f = open(logFile, 'w')
		f.write(data)
		f.close()
		os.chmod(logFile, 0640)
		
	def readLog(self, type, objectId=None, maxSize=0):
		if type not in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError('Unknown log type %s' % type)
		
		if not objectId and type in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError("Log type '%s' requires objectId" % type)
		
		if objectId and (objectId.find('/') != -1):
			raise BackendBadValueError("Bad objectId '%s'" % objectId)
		
		if maxSize:
			maxSize = int(maxSize)
		
		logFile = os.path.join(self.__logDir, type, objectId + '.log')
		data = ''
		if not os.path.exists(logFile):
			return data
		logFile = open(logFile)
		data = logFile.read()
		logFile.close()
		if maxSize and (len(data) > maxSize):
			start = data.find('\n', len(data)-maxSize)
			if (start == -1):
				start = len(data)-maxSize
			return str(start) + " " + data[start:]
		return data
		
	# -------------------------------------------------
	# -     GENERAL CONFIG                            -
	# -------------------------------------------------
	def setGeneralConfig(self, config, objectId = None):
		if not objectId:
			# Set global (server)
			objectId = self.getServerId()
		
		objectId = objectId.lower()
		
		configNew = {}
		for (key, value) in config.items():
			configNew[key.lower()] = value
		config = configNew
		
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# General config for server/domain => edit general.ini
			iniFile = self.__globalConfigFile
		else:
			# General config for special host => edit <hostname>.ini
			ini = self.readIniFile(self.__globalConfigFile)
			for (key, value) in ini.items('generalconfig'):
				key = key.lower()
				if not config.has_key(key):
					continue
				if (value == config[key]):
					del config[key]
			iniFile = self.getClientIniFile(objectId)
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError:
			self.createFile(iniFile, mode=0660)
			ini = self.readIniFile(iniFile)
		
		# Delete section generalConfig if exists
		if ini.has_section("generalconfig"):
			ini.remove_section("generalconfig")
		if config:
			ini.add_section("generalconfig")
			
			for (key, value) in config.items():
				ini.set('generalconfig', key, value)
			
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	def getGeneralConfig_hash(self, objectId = None):
		if not objectId:
			# Get global (server)
			objectId = self.getServerId()
		
		objectId = objectId.lower()
		
		iniFiles = [ os.path.join(self.__globalConfigFile) ]
		if (objectId != self.getServerId()) and (objectId != self._defaultDomain):
			# Add client specific general config
			iniFiles.append(self.getClientIniFile(objectId))
		
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
				for (key, value) in ini.items('generalconfig'):
					found = False
					for knownKey in generalConfig.keys():
						if ( knownKey.lower() == key.lower() ):
							generalConfig[knownKey] = value
							found = True
							break
					if not found:
						generalConfig[key] = value
				
			except ConfigParser.NoSectionError, e:
				# Section generalConfig does not exist => try the next ini-file
				logger.info("No section 'generalconfig' in ini-file '%s'" % iniFile)
		
		return generalConfig
	
	
	def deleteGeneralConfig(self, objectId):
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			iniFile = self.__globalConfigFile
		else:
			# General config for special host => edit <hostname>.ini
			iniFile = self.getClientIniFile(objectId)
		
		# Read the ini file
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError, e:
			logger.warning("Cannot delete general config for object '%s': %s" % (objectId, e))
		
		# Delete section shareinfo if exists
		if ini.has_section("generalconfig"):
			ini.remove_section("generalconfig")
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	# -------------------------------------------------
	# -     NETWORK FUNCTIONS                         -
	# -------------------------------------------------
	def setNetworkConfig(self, config, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
		configNew = {}
		for (key, value) in config.items():
			key = key.lower()
			if key not in (	'opsiserver', 'utilsdrive', 'depotdrive', 'configdrive', 'utilsurl', 'depoturl', 'configurl', \
						'depotid', 'windomain', 'nextbootservertype', 'nextbootserviceurl' ):
				logger.error("Unknown networkConfig key '%s'" % key)
				continue
			if (key == 'depoturl'):
				logger.error("networkConfig: Setting key 'depotUrl' is no longer supported, use depotId")
				continue
			if key in ('configurl', 'utilsurl'):
				logger.error("networkConfig: Setting key '%s' is no longer supported" % key)
				continue
			configNew[key] = value
		config = configNew
		
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# Network config for server/domain => edit general.ini
			iniFile = self.__globalConfigFile
		else:
			# Network config for special host => edit <hostname>.ini
			ini = self.readIniFile(self.__globalConfigFile)
			for (key, value) in ini.items('networkconfig'):
				key = key.lower()
				if not config.has_key(key):
					continue
				if (value == config[key]):
					del config[key]
			iniFile = self.getClientIniFile(objectId)
		
		# Read the ini file or create if not exists
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError:
			self.createFile(iniFile, mode=0660)
			ini = self.readIniFile(iniFile)
		
		# Delete section generalConfig if exists
		if ini.has_section("networkconfig"):
			ini.remove_section("networkconfig")
		if config:
			ini.add_section("networkconfig")
			for (key, value) in config.items():
				ini.set('networkconfig', key, value)
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	def getNetworkConfig_hash(self, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		objectId = objectId.lower()
		
		iniFiles = [ os.path.join(self.__globalConfigFile) ]
		if (objectId != self.getServerId()) and (objectId != self._defaultDomain):
			# Add client specific network config
			iniFiles.append(self.getClientIniFile(objectId))
		
		networkConfig = { 
			'opsiServer': 	self.getServerId(objectId),
			'utilsDrive':	'',
			'depotDrive':	'',
			'configDrive':	'',
			'utilsUrl':	'',
			'depotId':	self.getDepotId(), # leave this as default !
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
				for (key, value) in ini.items('networkconfig'):
					found = False
					for knownKey in networkConfig.keys():
						if ( knownKey.lower() == key.lower() ):
							networkConfig[knownKey] = value
							found = True
							break
					if not found:
						logger.error("Unknown networkConfig key '%s' in file '%s'" % (key, iniFile))
			
			except ConfigParser.NoSectionError, e:
				# Section shareinfo does not exist => try the next ini-file
				logger.info("No section 'networkConfig' in ini-file '%s'" % iniFile)
				continue
		
		if networkConfig['depotId']:
			networkConfig['depotUrl'] = self.getDepot_hash(networkConfig['depotId'])['depotRemoteUrl']
			networkConfig['utilsUrl'] = 'smb://%s/opt_pcbin/utils' % networkConfig['depotId'].split('.')[0]
			networkConfig['configUrl'] = 'smb://%s/opt_pcbin/pcpatch' % networkConfig['depotId'].split('.')[0]
			
		# Check if all needed values are set
		if (not networkConfig['opsiServer']
		    or not networkConfig['utilsDrive'] or not networkConfig['depotDrive'] 
		    or not networkConfig['utilsUrl'] or not networkConfig['depotUrl'] ):
			logger.warning("Networkconfig for object '%s' incomplete" % objectId)
		
		return networkConfig
	
	def deleteNetworkConfig(self, objectId):
		objectId = objectId.lower()
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			iniFile = self.__globalConfigFile
		else:
			# Network config for special host => edit <hostname>.ini
			iniFile = self.getClientIniFile(objectId)
		
		# Read the ini file
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError, e:
			logger.warning("Cannot delete network config for object '%s': %s" % (objectId, e))
		
		# Delete section shareinfo if exists
		if ini.has_section("networkconfig"):
			ini.remove_section("networkconfig")
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	
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
		if not hardwareAddress:
			hardwareAddress = ''
		
		clientId = clientName.lower() + '.' + domain.lower()
		iniFile = self.getClientIniFile(clientId)
		
		if os.path.exists(iniFile):
			logger.notice("Client %s already exists, recreating" % clientId)
		else:
			# Copy the client configuration prototype
			self.createFile(iniFile, mode=0660)
			globalConfig = self.openFile(self.__defaultClientTemplateFile)
			try:
				newclient = self.openFile(iniFile, 'w' )
			except BackendIOError, e:
				self.closeFile(globalConfig)
				raise
			
			newclient.write(globalConfig.read())
			self.closeFile(globalConfig)
			self.closeFile(newclient)
		
		# Add host info to client's config file
		ini = self.readIniFile(iniFile)
		if not ini.has_section('info'):
			ini.add_section('info')
		if description:
			ini.set("info", "description", description.replace('\n', '\\n').replace('%', ''))
		if notes:
			ini.set("info", "notes", notes.replace('\n', '\\n').replace('%', ''))
		if hardwareAddress:
			ini.set('info', 'macaddress', hardwareAddress)
		
		self.writeIniFile(iniFile, ini)
		
		logger.debug("Client created")
		
		# Return the clientid
		return clientId
	
	def deleteServer(self, serverId):
		logger.error("Cannot delete server '%s': Not supported by File31 backend." % serverId)
	
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
		
		# Delete ini file
		iniFile = self.getClientIniFile(clientId)
		if os.path.exists(iniFile):
			self.deleteFile(iniFile)
	
	def setHostLastSeen(self, hostId, timestamp):
		logger.debug("Setting last-seen timestamp for host '%s' to '%s'" % (hostId, timestamp))
		
		if hostId in self.getDepotIds_list():
			# TODO
			return
		
		iniFile = self.getClientIniFile(hostId)
		
		ini = self.readIniFile(iniFile)
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'lastseen', timestamp)
		self.writeIniFile(iniFile, ini)
	
	def setHostDescription(self, hostId, description):
		logger.debug("Setting description for host '%s' to '%s'" % (hostId, description))
		
		iniFile = self.getClientIniFile(hostId)
		
		ini = self.readIniFile(iniFile)
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'description', description.replace('\n', '\\n').replace('%', ''))
		self.writeIniFile(iniFile, ini)
	
	def setHostNotes(self, hostId, notes):
		logger.debug("Setting notes for host '%s' to '%s'" % (hostId, notes))
		
		iniFile = self.getClientIniFile(hostId)
		
		ini = self.readIniFile(iniFile)
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'notes', notes.replace('\n', '\\n').replace('%', ''))
		self.writeIniFile(iniFile, ini)
	
	def getSoftwareInformation_hash(self, hostId):
		hostId = hostId.lower()
		ini = None
		try:
			ini = self.readIniFile( "%s.sw" % os.path.join(self.__auditInfoDir, hostId) )
		except BackendIOError, e:
			logger.warning("No software info for host '%s' found: %s" % (hostId, e))
			return []
		
		info = {}
		for section in ini.sections():
			software = {}
			for (key, value) in ini.items(section):
				if   (key.lower() == "displayname"): key = "displayName"
				elif (key.lower() == "displayversion"): key = "displayVersion"
				software[key] = value
			info[section] = software
		
		return info
	
	def setSoftwareInformation(self, hostId, info):
		hostId = hostId.lower()
		
		if not type(info) is dict:
			raise BackendBadValueError("Software information must be dict")
		
		# Time of scan
		if not info.has_key('SCANPROPERTIES') or not info['SCANPROPERTIES']:
			info['SCANPROPERTIES'] = { 'scantime': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) }
		
		self.deleteSoftwareInformation(hostId)
		
		iniFile = "%s.sw" % os.path.join(self.__auditInfoDir, hostId)
		
		if not os.path.exists(iniFile):
			self.createFile(iniFile, 0660)
		ini = self.readIniFile(iniFile)
		
		for (key, value) in info.items():
			ini.add_section(key)
			for (k, v) in value.items():
				ini.set(key, str(k), str(v))
		
		self.writeIniFile(iniFile, ini)
	
	def deleteSoftwareInformation(self, hostId):
		hostId = hostId.lower()
		try:
			self.deleteFile( "%s.sw" % os.path.join(self.__auditInfoDir, hostId) )
		except Exception, e:
			logger.error("Failed to delete software information for host '%s': %s" % (hostId, e))
		
	def getHardwareInformation_listOfHashes(self, hostId):
		# Deprecated
		return []
	
	def getHardwareInformation_hash(self, hostId):
		hostId = hostId.lower()
		ini = None
		try:
			ini = self.readIniFile( "%s.hw" % os.path.join(self.__auditInfoDir, hostId) )
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
			
			section = ('_'.join(section.split('_')[:-1])).upper()
			if not info.has_key(section):
				info[section] = []
			
			info[section].append(dev)
		
		return info
	
	def setHardwareInformation(self, hostId, info):
		hostId = hostId.lower()
		
		# Time of scan
		if not info.has_key('SCANPROPERTIES') or not info['SCANPROPERTIES']:
			info['SCANPROPERTIES'] = [ { 'scantime': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) } ]
		
		if not type(info) is dict:
			raise BackendBadValueError("Hardware information must be dict")
		
		self.deleteHardwareInformation(hostId)
		
		iniFile = "%s.hw" % os.path.join(self.__auditInfoDir, hostId)
		
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
			self.deleteFile( "%s.hw" % os.path.join(self.__auditInfoDir, hostId) )
		except Exception, e:
			logger.error("Failed to delete hardware information for host '%s': %s" % (hostId, e))
	
	def getHost_hash(self, hostId):
		logger.info("Getting infos for host '%s'" % hostId)
		
		#if hostId in self._aliaslist():
		#	return { "hostId": hostId, "description": "Depotserver", "notes": "", "lastSeen": "" }
		
		info = {
			"hostId": 	hostId,
			"description":	"",
			"notes":	"",
			"lastSeen":	"" }
		
		if hostId in self.getDepotIds_list():
			depot = self.getDepot_hash(hostId)
			info['description'] = depot.get('description')
			info['notes'] = depot.get('notes')
			return info
		
		iniFile = self.getClientIniFile(hostId)
		ini = self.readIniFile(iniFile)
		
		if ini.has_section('info'):
			if ini.has_option('info', 'description'):
				info['description'] = ini.get('info', 'description').replace('\\n', '\n')
			if ini.has_option('info', 'notes'):
				info['notes'] = ini.get('info', 'notes').replace('\\n', '\n')
			if ini.has_option('info', 'lastseen'):
				info['lastSeen'] = ini.get('info', 'lastseen')
		else:
			logger.warning("No section 'info' in ini file '%s'" % iniFile)
		
		return info
		
	def getClients_listOfHashes(self, serverId=None, depotId=None, groupId=None, productId=None, installationStatus=None, actionRequest=None, productVersion=None, packageVersion=None):
		""" Returns a list of client-ids which are connected 
		    to the server with the specified server-id. 
		    If no server is specified, all registered clients are returned """
		
		if (serverId and serverId != self.getServerId()):
			raise BackendMissingDataError("Can only access data on server: %s" % self.getServerId())
		
		if depotId:
			depotId = depotId.lower()
		
		if productId:
			productId = productId.lower()
		
		if groupId and not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		clientFiles = []
		try:
			for f in os.listdir(self.__clientConfigDir):
				if f.endswith('.ini'):
					clientFiles.append(f)
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
			for filename in clientFiles:
				hostId = self.getHostId(filename)
				if hostId not in hostIds:
					try:
						hostIds.append( hostId.encode('ascii') )
					except Exception, e:
						logger.error("Skipping hostId: '%s': %s" % (hostId, e))
		
		# Filter by depot-id
		if depotId:
			filteredHostIds = []
			for hostId in hostIds:
				if (self.getDepotId(hostId) == depotId):
					filteredHostIds.append(hostId)
			hostIds = filteredHostIds
			
		# Filter by product state
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
		for hostId in hostIds:
			try:
				infos.append( self.getHost_hash(hostId) )
			except BackendIOError, e:
				logger.error(e)
		
		return infos
		
		
	def getClientIds_list(self, serverId=None, depotId=None, groupId=None, productId=None, installationStatus=None, actionRequest=None, productVersion=None, packageVersion=None):
		clientIds = []
		
		if not depotId and not groupId and not productId and not installationStatus and not actionRequest and not productVersion and not packageVersion:
			try:
				for f in os.listdir(self.__clientConfigDir):
					if f.endswith('.ini'):
						clientIds.append(self.getHostId(f))
			except OSError, e:
				raise BackendIOError(e)
			return clientIds
		
		for info in self.getClients_listOfHashes(serverId, depotId, groupId, productId, installationStatus, actionRequest, productVersion, packageVersion):
			clientIds.append( info.get('hostId') )
		return clientIds
                                                     
	def getServerIds_list(self):
		return [ self.getServerId() ]
	
	def getServerId(self, clientId=None):
		# Return hostid of localhost
		serverId = socket.getfqdn()
		parts = serverId.split('.')
		if (len(parts) < 3):
			serverId = parts[0] + '.' + self._defaultDomain
		return serverId.lower()
	
	def createDepot(self, depotName, domain, depotLocalUrl, depotRemoteUrl, repositoryLocalUrl, repositoryRemoteUrl, network, description=None, notes=None, maxBandwidth=0):
		if not re.search(HOST_NAME_REGEX, depotName):
			raise BackendBadValueError("Unallowed char in hostname")
		depotId = depotName + '.' + domain
		depotId = self._preProcessHostId(depotId)
		for i in (depotLocalUrl, depotRemoteUrl, repositoryLocalUrl, repositoryRemoteUrl):
			if not i.startswith('file:///') and not i.startswith('smb://') and \
			   not i.startswith('http://') and not i.startswith('https://') and \
			   not i.startswith('webdav://') and not i.startswith('webdavs://'):
				raise BackendBadValueError("Bad url '%s'" % i)
		if not re.search('\d+\.\d+\.\d+\.\d+\/\d+', network):
			raise BackendBadValueError("Bad network '%s'" % network)
		if not description:
			description = ''
		if not notes:
			notes = ''
		
		# Create config directory for depot
		depotPath = os.path.join(self.__depotConfigDir, depotId)
		if not os.path.exists(depotPath):
			os.mkdir(depotPath)
		try:
			os.chmod(depotPath, 0770)
		except:
			pass
		
		# Create depot ini file
		depotIniFile = self.getDepotIniFile(depotId)
		if not os.path.exists(depotIniFile):
			self.createFile(depotIniFile, mode=0660)
		
		ini = self.readIniFile(depotIniFile)
		if not ini.has_section('depotshare'):
			ini.add_section('depotshare')
		ini.set('depotshare', 'localurl', depotLocalUrl)
		ini.set('depotshare', 'remoteurl', depotRemoteUrl)
		
		if not ini.has_section('repository'):
			ini.add_section('repository')
		ini.set('repository', 'localurl', repositoryLocalUrl)
		ini.set('repository', 'remoteurl', repositoryRemoteUrl)
		ini.set('repository', 'maxbandwidth', str(maxBandwidth))
		
		if not ini.has_section('depotserver'):
			ini.add_section('depotserver')
		ini.set('depotserver', 'network', network )
		ini.set('depotserver', 'description', description )
		ini.set('depotserver', 'notes', notes )
		
		# Write back ini file
		self.writeIniFile(depotIniFile, ini)
		
		return depotId
	
	def getDepotIds_list(self):
		depotIds = []
		for d in os.listdir(self.__depotConfigDir):
			if os.path.isdir( os.path.join(self.__depotConfigDir, d) ):
				depotIds.append( d.lower() )
		return depotIds
	
	def getDepotId(self, clientId=None):
		logger.debug('getDepotId()')
		depotId = self.getServerId()
		if clientId:
			clientId = self._preProcessHostId(clientId)
			depotId = self.getNetworkConfig_hash(objectId = clientId).get('depotId', self.getServerId())
		depotIds = self.getDepotIds_list()
		if depotId not in depotIds:
			raise BackendMissingDataError("Configured depotId '%s' for host '%s' not in list of known depotIds %s" \
								% (depotId, clientId, depotIds) )
		return depotId
	
	def getDepot_hash(self, depotId):
		depotId = self._preProcessHostId(depotId)
		depotIniFile = self.getDepotIniFile(depotId)
		if not os.path.exists(depotIniFile):
			raise BackendMissingDataError("Failed to get info for depot-id '%s': File '%s' not found" % (depotId, depotIniFile))
		ini = None
		try:
			ini = self.readIniFile(depotIniFile)
		except Exception, e:
			raise BackendIOError("Failed to get info for depot-id '%s': %s" % (depotId, e))
		
		info = {}
		try:
			info['depotLocalUrl'] 		= ini.get('depotshare', 'localurl')
			info['depotRemoteUrl'] 		= ini.get('depotshare', 'remoteurl')
			info['repositoryLocalUrl'] 	= ini.get('repository', 'localurl')
			info['repositoryRemoteUrl'] 	= ini.get('repository', 'remoteurl')
			info['network'] 		= ini.get('depotserver', 'network')
			info['description'] 		= ini.get('depotserver', 'description')
			info['notes'] 			= ini.get('depotserver', 'notes')
			if ini.has_option('repository', 'maxbandwidth'):
				info['repositoryMaxBandwidth'] = int(ini.get('repository', 'maxbandwidth'))
			else:
				info['repositoryMaxBandwidth'] = 0
		except Exception, e:
			raise BackendIOError("Failed to get info for depot-id '%s': %s" % (depotId, e))
		return info
	
	def deleteDepot(self, depotId):
		depotId = self._preProcessHostId(depotId)
		if not depotId in self.getDepotIds_list():
			logger.error("Cannot delete depot '%s': does not exist" % depotId)
			return
		rmdir( os.path.join(self.__depotConfigDir, depotId), recursive=True )
	
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
			if (hostname.lower() == hostId):
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
			if lines[i].lower().startswith( hostId + ':' ):
				# Host entry exists => change key
				lines[i] = hostId + ':' + opsiHostKey + "\n"
				exists = True
				break;
		if not exists:
			# Host key does not exist => add line
			lines.append(hostId + ':' + opsiHostKey + "\n")
		
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
			if lines[i].lower().startswith( hostId + ':' ):
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
		logger.info("Getting mac addresses for host '%s'" % hostId)
		
		if hostId in self._aliaslist():
			return macs
		
		iniFile = self.getClientIniFile(hostId)
		ini = self.readIniFile(iniFile)
		
		if ini.has_section('info'):
			if ini.has_option('info', 'macaddress'):
				for mac in ini.get('info', 'macaddress').split(','):
					if mac:
						macs.append(mac.strip().lower())
		else:
			logger.warning("No section 'info' in ini file '%s'" % iniFile)
		
		for hw in self.getHardwareInformation_listOfHashes(hostId):
			if (hw.get('class') == 'ETHERNET_CONTROLLER'):
				mac = hw.get('macAddress')
				if mac and not mac in macs:
					macs.append(mac.strip().lower())
		return macs
		
	def setMacAddresses(self, hostId, macs=[]):
		
		logger.info("Setting mac addresses for host '%s'" % hostId)
		
		if hostId in self._aliaslist():
			return
		
		for i in range(len(macs)):
			macs[i] = macs[i].lower()
		
		iniFile = self.getClientIniFile(hostId)
		ini = self.readIniFile(iniFile)
		
		if not ini.has_section('info'):
			ini.add_section('info')
		ini.set('info', 'macaddress', ', '.join(macs))
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
		
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
		hostId = self._preProcessHostId(hostId)
		if (hostId == self.getServerId()):
			password = None
			
			f = open(self.__passwdFile)
			for line in f.readlines():
				if line.startswith('pcpatch:'):
					password = line.split(':')[1].strip()
					break
			f.close()
			if not password:
				raise Exception("Failed to get pcpatch password for host '%s' from '%s'" % (hostId, self.__passwdFile))
			
			return password
		
		else:
			serverId = self.getServerId(hostId)
			if (serverId == hostId):
				# Avoid loops
				raise BackendError("Bad backend configuration: server of host '%s' is '%s', current server id is '%s'" \
								% (hostId, serverId, self.getServerId()))
			cleartext = Tools.blowfishDecrypt( self.getOpsiHostKey(serverId), self.getPcpatchPassword(serverId) )
			return Tools.blowfishEncrypt( self.getOpsiHostKey(hostId), cleartext )
	
	def setPcpatchPassword(self, hostId, password):
		hostId = self._preProcessHostId(hostId)
		if (hostId != self.getServerId()):
			# Not storing client passwords they will be calculated on the fly
			return
		
		hostname = hostId.split('.')[0]
		
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
		
	# -------------------------------------------------
	# -     PRODUCT FUNCTIONS                         -
	# -------------------------------------------------
	def lockProduct(self, productId, depotIds=[]):
		if not productId:
			raise BackendBadValueError("Product id empty")
		productId = productId.lower()
		if not depotIds:
			depotIds = self.getDepotIds_list()
		if type(depotIds) not in (list, tuple):
			depotIds = [ depotIds ]
		
		logger.debug("Locking product '%s' on depots: %s" % (productId, depotIds))
		
		newDepotIds = []
		for depotId in depotIds:
			try:
				self.getProduct_hash(productId = productId, depotId = depotId)
				newDepotIds.append(depotId)
			except BackendMissingDataError, e:
				logger.warning("Depot '%s': %s" % (depotId, e))
		depotIds = newDepotIds
		
		if not depotIds:
			#raise BackendMissingDataError("Product '%s' not installed on any of the given depots" % productId)
			logger.warning("Product '%s' not installed on any of the given depots" % productId)
			return
		
		if not os.path.exists(self.__productLockFile):
			self.createFile(self.__productLockFile, mode=0660)
		
		ini = self.readIniFile(self.__productLockFile)
		
		if not ini.has_section(productId):
			ini.add_section(productId)
		for depotId in depotIds:
			ini.set(productId, depotId, 'locked')
		
		self.writeIniFile(self.__productLockFile, ini)
		
	def unlockProduct(self, productId, depotIds=[]):
		productId = productId.lower()
		if not depotIds:
			depotIds = self.getDepotIds_list()
		if type(depotIds) not in (list, tuple):
			depotIds = [ depotIds ]
		
		logger.debug("Unlocking product '%s' on depots: %s" % (productId, depotIds))
		
		if not os.path.exists(self.__productLockFile):
			self.createFile(self.__productLockFile, mode=0660)
		
		ini = self.readIniFile(self.__productLockFile)
		
		if not ini.has_section(productId):
			return
		
		for depotId in depotIds:
			if ini.has_option(productId, depotId):
				ini.remove_option(productId, depotId)
		
		if not ini.items(productId):
			ini.remove_section(productId)
		
		self.writeIniFile(self.__productLockFile, ini)
	
	def getProductLocks_hash(self, depotIds=[]):
		locks = {}
		if not depotIds:
			depotIds = self.getDepotIds_list()
		if type(depotIds) not in (list, tuple):
			depotIds = [ depotIds ]
		if not os.path.exists(self.__productLockFile):
			self.createFile(self.__productLockFile, mode=0660)
		
		ini = self.readIniFile(self.__productLockFile)
		
		for productId in ini.sections():
			locks[productId] = []
			for (depotId, value) in ini.items(productId):
				locks[productId].append(depotId)
		return locks
		
	def createProduct(self, productType, productId, name, productVersion, packageVersion, licenseRequired=0,
			   setupScript="", uninstallScript="", updateScript="", alwaysScript="", onceScript="",
			   priority=0, description="", advice="", productClassNames=(), pxeConfigTemplate='',
			   windowsSoftwareIds=[], depotIds=[]):
		
		if not re.search(PRODUCT_ID_REGEX, productId):
			raise BackendBadValueError("Unallowed chars in productId!")
		
		productId = productId.lower()
		
		if (productType == 'server'):
			logger.warning("Nothing to do for product type 'server'")
			return
		elif productType not in ['localboot', 'netboot']:
			raise BackendBadValueError("Unknown product type '%s'" % productType)
		
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		product = Product(
			productType		= productType,
			productId		= productId,
			name			= name,
			productVersion		= productVersion,
			packageVersion		= packageVersion,
			licenseRequired		= licenseRequired,
			setupScript		= setupScript,
			uninstallScript		= uninstallScript,
			updateScript		= updateScript,
			alwaysScript		= alwaysScript,
			onceScript		= onceScript,
			priority		= priority,
			description		= description,
			advice			= advice,
			productClassNames	= productClassNames,
			pxeConfigTemplate	= pxeConfigTemplate,
			windowsSoftwareIds	= windowsSoftwareIds )
		
		if (depotIds == self.getDepotIds_list()):
			ini = self.readIniFile( self.__defaultClientTemplateFile )
			
			if not ini.has_section('%s_product_states' % productType):
				ini.add_section('%s_product_states' % productType)
			
			if not ini.has_option('%s_product_states' % productType, productId):
				ini.set('%s_product_states' % productType, productId, 'not_installed:none')
			
			self.writeIniFile( self.__defaultClientTemplateFile, ini)
		
		for depotId in depotIds:
			depotId = depotId.lower()
			productDir = os.path.join(self.__depotConfigDir, depotId, 'products', productType)
			if not os.path.exists(productDir):
				mkdir(productDir, mode = 0770 | stat.S_ISGID)
			product.writeControlFile( os.path.join(productDir, productId) )
			try:
				os.chmod( os.path.join(productDir, productId), 0660 )
			except:
				pass
			
			for clientId in self.getClientIds_list(serverId = None, depotId = depotId):
				ini = self.readIniFile( self.getClientIniFile(clientId) )
				
				if not ini.has_section('%s_product_states' % productType):
					ini.add_section('%s_product_states' % productType)
				
				if not ini.has_option('%s_product_states' % productType, productId):
					ini.set('%s_product_states' % productType, productId, 'not_installed:none')
				
				self.writeIniFile( self.getClientIniFile(clientId), ini)
	
	
	def deleteProduct(self, productId, depotIds=[]):
		
		productId = productId.lower()
		
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		if (depotIds == self.getDepotIds_list()):
			ini = self.readIniFile( self.__defaultClientTemplateFile )
			
			for productType in ('localboot', 'netboot'):
				if not ini.has_section('%s_product_states' % productType):
					continue
				
				if ini.has_option('%s_product_states' % productType, productId):
					ini.remove_option('%s_product_states' % productType, productId)
				
			self.writeIniFile( self.__defaultClientTemplateFile, ini)
		
		errorList = []
		for depotId in depotIds:
			depotId = depotId.lower()
			productType = None
			productDir = None
			if productId in self.getProductIds_list('localboot', depotId):
				productDir = os.path.join(self.__depotConfigDir, depotId, 'products', 'localboot')
				productType = 'localboot'
			elif productId in self.getProductIds_list('netboot'):
				productDir = os.path.join(self.__depotConfigDir, depotId, 'products', 'netboot')
				productType = 'netboot'
			else:
				logger.warning("Cannot delete product '%s': is neither localboot nor netboot product" % productId)
				continue
			
			
			# Try to delete product status entry from every client's configuration file
			iniFiles =[]
			for clientId in self.getClientIds_list(serverId = None, depotId = depotId):
				iniFiles.append( self.getClientIniFile(clientId) )
			for iniFile in iniFiles:
				try:
					ini = self.readIniFile(iniFile)
					if ini.has_section('%s_product_states' % productType):
						if ini.has_option('%s_product_states' % productType, productId):
							ini.remove_option('%s_product_states' % productType, productId)
					if ini.has_section('%s-state' % productId):
						ini.remove_section('%s-state' % productId)
					self.writeIniFile(iniFile, ini)
				except BackendIOError, e:
					# IO error occured => append error to error list, but continue with next ini file
					err = "Failed to unregister product '%s' in ini file '%s': '%s'" % (productId, iniFile, e)
					errorList.append(err)
					logger.error(err)
			
			f = os.path.join(productDir, productId)
			if os.path.exists(f):
				try:
					os.unlink(f)
				except Exception, e:
					raise BackendIOError("Failed to delete product '%s', depotId: '%s': %s" % (productId, depotId, e))
			
		if ( len(errorList) > 0 ):
			# One or more errors occured => raise error
			raise BackendIOError( ', '.join(errorList) )
		
		
	def getProduct_hash(self, productId, depotId=None):
		
		productId = productId.lower()
		if not depotId:
			depotId = self.getDepotId()
		depotId = depotId.lower()
		
		productFile = None
		
		try:
			for d in ('localboot', 'netboot'):
				d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
				if not os.path.isdir(d):
					logger.warning("Is not a directory: '%s'" % d)
					continue
				for f in os.listdir(d):
					if (f.lower() == productId):
						productFile = os.path.join(d, f)
						break
		except OSError, e:
			raise BackendIOError(e)
		
		if not productFile:
			raise BackendMissingDataError("Product '%s' not found on depot '%s'" % (productId, depotId))
		
		timestamp = Tools.timestamp( os.path.getmtime(productFile) ) 
		
		product = Product()
		product.readControlFile(productFile)
		
		return {
			"name":				product.name,
			"description":			product.description,
			"advice":			product.advice,
			"priority":			product.priority,
			"licenseRequired":		product.licenseRequired,
			"productVersion":		product.productVersion,
			"packageVersion":		product.packageVersion,
			"creationTimestamp":		timestamp,
			"setupScript":			product.setupScript,
			"uninstallScript":		product.uninstallScript,
			"updateScript":			product.updateScript,
			"onceScript":			product.onceScript,
			"alwaysScript":			product.alwaysScript,
			"productClassNames":		product.productClassNames,
			"pxeConfigTemplate":		product.pxeConfigTemplate,
			"windowsSoftwareIds":		product.windowsSoftwareIds
		}
	
	def getProductIds_list(self, productType=None, objectId=None, installationStatus=None):
		
		productIds = []
		if not objectId:
			objectId = self.getDepotId()
		
		objectId = objectId.lower()
		
		if objectId in self.getDepotIds_list():
			depotDir = os.path.join(self.__depotConfigDir, objectId, 'products')
			if not os.path.exists(depotDir):
				logger.error("Directory '%s' does not exist" % depotDir)
				return []
			if (not productType or productType == 'localboot'):
				localbootDir = os.path.join(depotDir, 'localboot')
				if not os.path.exists(localbootDir):
					logger.error("Directory '%s' does not exist" % localbootDir)
				else:
					for f in os.listdir(localbootDir):
						productIds.append(f)
			
			if (not productType or productType == 'netboot'):
				netbootDir = os.path.join(depotDir, 'netboot')
				if not os.path.exists(netbootDir):
					logger.error("Directory '%s' does not exist" % netbootDir)
				else:
					for f in os.listdir(netbootDir):
						productIds.append(f)
		
		else:
			depotId = self.getDepotId(objectId)
			if (depotId == objectId):
				# Avoid loops
				raise BackendBadValueError("DepotId for host '%s' is '%s'" % (objectId, depotId))
			
			productTypes = ['localboot', 'netboot']
			if productType:
				productTypes = [ productType ]
			
			ini = self.readIniFile( self.getClientIniFile(objectId) )
			productsFound = []
			for productType in productTypes:
				if ini.has_section('%s_product_states' % productType):
					for (key, value) in ini.items('%s_product_states' % productType):
						productsFound.append(key)
						if ( not installationStatus or value.lower().split(':', 1)[0] == installationStatus):
							productIds.append(key)
			
			if not installationStatus or installationStatus in ['not_installed']:
				for productId in self.getProductIds_list(productType, depotId):
					if not productId in productsFound:
						productIds.append(productId)
		
		logger.debug("Products matching installationStatus '%s' on objectId '%s': %s" \
						% (installationStatus, objectId, productIds))
		
		return productIds
	
	
	def getProductInstallationStatus_hash(self, productId, objectId):
		productId = productId.lower()
		objectId = objectId.lower()
		
		status = { 
			'productId':		productId,
			'installationStatus':	'not_installed',
			'productVersion':	'',
			'packageVersion':	'',
			'lastStateChange':	'',
			'deploymentTimestamp':	'' }
		
		if objectId in self.getDepotIds_list():
			if productId in self.getProductIds_list(None, objectId):
				status['installationStatus'] = 'installed'
				p = self.getProduct_hash(productId)
				status['productVersion'] = p['productVersion']
				status['packageVersion'] = p['packageVersion']
				status['lastStateChange'] = p['creationTimestamp']
			return status
		
		# Read hosts config file
		ini = self.readIniFile( self.getClientIniFile(objectId) )
		
		for productType in ['localboot', 'netboot']:
			if ini.has_section('%s_product_states' % productType):
				try:
					value = ini.get('%s_product_states' % productType, productId)
					installationStatus = value.lower().split(':', 1)[0]
					if not installationStatus:
						installationStatus = 'undefined'
					
					if installationStatus not in getPossibleProductInstallationStatus():
						logger.error("Unknown installationStatus '%s' in ini file '%s'" \
								% (installationStatus, self.getClientIniFile(objectId)) )
						continue
					status['installationStatus'] = installationStatus
				except ConfigParser.NoOptionError, e:
					pass
		
		try:
			for (key, value) in ini.items('%s-state' % productId):
				if (key.lower() == 'productversion'):
					status['productVersion'] = value
				elif (key.lower() == 'packageversion'):
					status['packageVersion'] = value
				elif (key.lower() == 'laststatechange'):
					status['lastStateChange'] = value
		
		except ConfigParser.NoSectionError, e:
			logger.warning("Cannot get version information for product '%s' on host '%s': %s" \
					% (productId, objectId, e) )
		
		return status
	
	def getProductInstallationStatus_listOfHashes(self, objectId):
		objectId = objectId.lower()
		
		installationStatus = []
		
		if objectId in self.getDepotIds_list():
			for productId in self.getProductIds_list(None, objectId):
				p = self.getProduct_hash(productId)
				installationStatus.append( { 
					'productId': 		productId,
					'productVersion':	p['productVersion'],
					'packageVersion':	p['packageVersion'],
					'lastStateChange':	p['creationTimestamp'],
					'installationStatus':	'installed'
				} )
			return installationStatus
		
		for productId in self.getProductIds_list(None, self.getDepotId(objectId)):
			installationStatus.append( { 
					'productId':		productId,
					'installationStatus':	'undefined',
					'actionRequest':	'undefined',
					'productVersion':	'',
					'packageVersion':	'',
					'lastStateChange':	'' 
			} )
		
		ini = self.readIniFile( self.getClientIniFile(objectId) )
		
		for productType in ['localboot', 'netboot']:
			if ini.has_section('%s_product_states' % productType):
				for i in range(len(installationStatus)):
					try:
						value = ini.get('%s_product_states' % productType, installationStatus[i].get('productId'))
						status = value.lower().split(':', 1)[0]
						if not status:
							status = 'undefined'
						
						if status not in getPossibleProductInstallationStatus():
							logger.error("Unknown installationStatus '%s' in ini file '%s'" \
									% (status, self.getClientIniFile(objectId)) )
							continue
						installationStatus[i]['installationStatus'] = status
					except ConfigParser.NoOptionError, e:
						continue
					
					if ini.has_section('%s-state' % installationStatus[i].get('productId')):
						for (key, value) in ini.items('%s-state' % installationStatus[i].get('productId')):
							if (key.lower() == 'productversion'):
								installationStatus[i]['productVersion'] = value
							elif (key.lower() == 'packageversion'):
								installationStatus[i]['packageVersion'] = value
							elif (key.lower() == 'laststatechange'):
								installationStatus[i]['lastStateChange'] = value
		
		return installationStatus
	
	def setProductState(self, productId, objectId, installationStatus="", actionRequest="", productVersion="", packageVersion="", lastStateChange="", licenseKey=""):
		
		productId = productId.lower()
		
		if objectId in self.getDepotIds_list():
			return
		
		depotId = self.getDepotId(objectId)
		
		productType = None
		if productId in self.getProductIds_list('netboot', depotId):
			productType = 'netboot'
		elif productId in self.getProductIds_list('localboot', depotId):
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
		
		product = self.getProduct_hash(productId, depotId)
		
		if not lastStateChange:
			lastStateChange = Tools.timestamp()
		
		ini = self.readIniFile( self.getClientIniFile(objectId) )
		
		if not ini.has_section('%s_product_states' % productType):
			ini.add_section('%s_product_states' % productType)
		
		if not ini.has_section('%s-state' % productId):
			ini.add_section('%s-state' % productId)
		
		(currentInstallationStatus, currentActionRequest) = ('undefined', 'undefined')
		
		try:
			value = ini.get('%s_product_states' % productType, productId)
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
		
		logger.info("Setting product installation status '%s', product action request '%s' for product '%s'" \
					% (installationStatus, actionRequest, productId))
		
		ini.set('%s_product_states' % productType, productId, '%s:%s' % (installationStatus, actionRequest))
		
		logger.info("Setting product version '%s', package version '%s' for product '%s'" \
					% (productVersion, packageVersion, productId))
		
		ini.set('%s-state' % productId, 'productVersion', productVersion)
		ini.set('%s-state' % productId, 'packageVersion', packageVersion)
		ini.set('%s-state' % productId, 'lastStateChange', lastStateChange)
		
		self.writeIniFile( self.getClientIniFile(objectId), ini)
		
		return
		################################################## TODO
		
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
		productId = productId.lower()
		
		if not depotId:
			depotId = self.getDepotId()
		depotId = depotId.lower()
		
		actions = ['none']
		product = self.getProduct_hash(productId, depotId)
		if product.get('setupScript'):		actions.append('setup')
		if product.get('uninstallScript'):	actions.append('uninstall')
		if product.get('updateScript'):	actions.append('update')
		if product.get('onceScript'):		actions.append('once')
		if product.get('alwaysScript'):	actions.append('always')
		return actions
	
	def getPossibleProductActions_hash(self, depotId=None):
		
		if not depotId:
			depotId = self.getDepotId()
		depotId = depotId.lower()
		
		actions = {}
		
		for productId in self.getProductIds_list(None, depotId):
			actions[productId] = self.getPossibleProductActions_list(productId, depotId)
		
		return actions
	
	def getProductActionRequests_listOfHashes(self, clientId):
		
		clientId = self._preProcessHostId(clientId)
		
		actionRequests = []
		
		# Read all actions set in client's config file and map them to the new values
		iniFile = self.getClientIniFile(clientId)
		ini = self.readIniFile(iniFile)
		
		for productType in ['localboot', 'netboot']:
			if ini.has_section('%s_product_states' % productType):
				for (key, value) in ini.items('%s_product_states' % productType):
					if (value.find(':') == -1):
						continue
					actionRequest = value.lower().split(':', 1)[1]
					if not actionRequest:
						actionRequest = 'undefined'
					if actionRequest not in getPossibleProductActions():
						logger.error("Unknown actionRequest '%s' in ini file '%s'" % (actionRequest, iniFile) )
						continue
					
					actionRequests.append( { 'productId': key, 'actionRequest': actionRequest } )
		
		return actionRequests
	
	def getDefaultNetBootProductId(self, clientId):
		
		clientId = self._preProcessHostId(clientId)
		
		netBootProduct = self.getGeneralConfig_hash(clientId).get('os')
		
		if not netBootProduct:
			raise BackendMissingDataError("No default netboot product for client '%s' found in generalConfig" % clientId )
		return netBootProduct
	
	def setProductActionRequest(self, productId, clientId, actionRequest):
		self.setProductState(productId, clientId, actionRequest = actionRequest)
		
	def unsetProductActionRequest(self, productId, clientId):
		self.setProductState(productId, clientId, actionRequest="none")
	
	def _getProductStates_hash(self, objectIds = [], productType = None):
		result = {}
		if not objectIds or ( (len(objectIds) == 1) and not objectIds[0] ):
			objectIds = self.getClientIds_list()
		elif ( type(objectIds) != type([]) and type(objectIds) != type(()) ):
			objectIds = [ objectIds ]
		
		depotIds = self.getDepotIds_list()
		
		for objectId in objectIds:
			objectId = objectId.lower()
			
			isDepot = (objectId in depotIds)
			
			logger.info("Getting product states for host '%s'" % objectId)
			result[objectId] = []
			
			(depotId, iniFile, ini) = (None, None, None)
			if not isDepot:
				iniFile = self.getClientIniFile(objectId)
				ini = self.readIniFile(iniFile)
				depotId = self.getDepotId(objectId)
			
			productTypes = []
			localbootProductIds = []
			netbootProductIds = []
			if not productType or (productType == 'localboot'):
				productTypes.append('localboot')
				localbootProductIds = self.getProductIds_list('localboot', depotId)
			if not productType or (productType == 'netboot'):
				productTypes.append('netboot')
				netbootProductIds = self.getProductIds_list('netboot', depotId)
			
			for pt in productTypes:
				logger.info("ProductType: '%s'" % pt)
				productIds = []
				if (pt == 'localboot'):
					productIds = localbootProductIds
				elif (pt == 'netboot'):
					productIds = netbootProductIds
				
				if isDepot:
					for productId in productIds:
						p = self.getProduct_hash(productId, objectId)
						result[objectId].append( { 	'productId':		productId, 
										'installationStatus':	'installed',
										'actionRequest':	'none',
										'productVersion':	p['productVersion'],
										'packageVersion':	p['packageVersion'],
										'lastStateChange':	p['creationTimestamp'] } )
					continue
				
				states = []
				logger.debug("ProductType: '%s', productIds: %s" % (pt, productIds))
				for productId in productIds:
					productVersion = ''
					packageVersion = ''
					lastStateChange = ''
					if ini.has_section('%s-state' % productId):
						for (key, value) in ini.items('%s-state' % productId):
							if (key.lower() == 'productversion'):
								productVersion = value
							elif (key.lower() == 'packageversion'):
								packageVersion = value
							elif (key.lower() == 'laststatechange'):
								lastStateChange = value
					
					states.append( { 	'productId':		productId, 
								'installationStatus':	'undefined',
								'actionRequest':	'undefined',
								'productVersion':	productVersion,
								'packageVersion':	packageVersion,
								'lastStateChange':	lastStateChange } )
				
				if ini.has_section('%s_product_states' % pt):
					for i in range(len(states)):
						try:
							value = ini.get('%s_product_states' % pt, states[i].get('productId'))
							status = ''
							action = ''
							
							if (value.find(':') == -1):
								status = value
							else:
								(status, action) = value.lower().split(':', 1)
								if not status: status = 'undefined'
								if not action: action = 'undefined'
								
							if status and status not in getPossibleProductInstallationStatus():
								logger.error("Unknown installationStatus '%s' in ini file '%s'" \
										% (status, iniFile) )
							
							if action and action not in getPossibleProductActions():
								logger.error("Unknown actionRequest '%s' in ini file '%s'" \
										% (status, iniFile) )
							
							states[i]['installationStatus'] = status
							states[i]['actionRequest'] = action
						except ConfigParser.NoOptionError, e:
							continue
				
				result[objectId].extend(states)
		return result
	
	def getProductStates_hash(self, objectIds = []):
		result = self.getLocalBootProductStates_hash(objectIds)
		for (key, value) in self.getNetBootProductStates_hash(objectIds).items():
			if not result.has_key(key):
				result[key] = []
			result[key].extend(value)
		
		return result
	
	def getNetBootProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds, 'netboot')
		
	def getLocalBootProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds, 'localboot')
		
	def getProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds)
	
	def getProductPropertyDefinitions_hash(self, depotId=None):
		if not depotId:
			depotId = self.getDepotId()
		depotId = depotId.lower()
		
		definitions = {}
		productFiles = []
		
		try:
			for d in ('localboot', 'netboot'):
				d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
				if not os.path.isdir(d):
					logger.warning("Is not a directory: '%s'" % d)
					continue
				for f in os.listdir(d):
					productFiles.append(os.path.join(d, f))
		except OSError, e:
			raise BackendIOError(e)
		
		for productFile in productFiles:
			product = Product()
			product.readControlFile(productFile)
			for prop in product.productProperties:
				if not definitions.has_key(prop.productId):
					definitions[prop.productId] = []
				
				definitions[prop.productId].append( {
					'name': 	prop.name.lower(),
					'description':	prop.description,
					'values':	prop.possibleValues,
					'default':	prop.defaultValue
				} )
	
		return definitions
	
	def getProductPropertyDefinitions_listOfHashes(self, productId, depotId=None):
		productId = productId.lower()
		if not depotId:
			depotId = self.getDepotId()
		depotId = depotId.lower()
		
		definitions = []
		productFile = None
		
		try:
			for d in ('localboot', 'netboot'):
				d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
				if not os.path.isdir(d):
					logger.warning("Is not a directory: '%s'" % d)
					continue
				
				for f in os.listdir(d):
					if (f == productId):
						productFile = os.path.join(d, f)
						break
		except OSError, e:
			raise BackendIOError(e)
		
		if not productFile:
			raise BackendMissingDataError("Product '%s' does not exist" % productId)
		
		product = Product()
		product.readControlFile(productFile)
		for prop in product.productProperties:
			definitions.append( {
				'name': 	prop.name.lower(),
				'description':	prop.description,
				'values':	prop.possibleValues,
				'default':	prop.defaultValue
			} )

		return definitions
	
	def deleteProductPropertyDefinition(self, productId, name, depotIds=[]):
		productId = productId.lower()
		name = name.lower()
		
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		for depotId in depotIds:
			depotId = depotId.lower()
			
			productFile = None
			num = -1
			try:
				for d in ('localboot', 'netboot'):
					d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
					if not os.path.isdir(d):
						logger.warning("Is not a directory: '%s'" % d)
						continue
					for f in os.listdir(d):
						if (f == productId):
							productFile = os.path.join(d, f)
							break
			except OSError, e:
				raise BackendIOError(e)
			
			if not productFile:
				raise BackendMissingDataError("Cannot delete product property definition '%s' of product '%s': no such product" \
						% (name, productId) )
			
			product = Product()
			product.readControlFile(productFile)
			for i in range(len(product.productProperties)):
				if (product.productProperties[i].name == name):
					num = i
			if (num == -1):
				raise BackendIOError("Cannot delete product property definition '%s' of product '%s': no such product property" \
						% (name, productId) )
			
			del product.productProperties[num]
			product.writeControlFile(productFile)
			
			errorList = []
			for clientId in self.getClientIds_list(None, depotId):
				try:
					self.deleteProductProperty(productId, name, objectId = clientId)
				except Exception, e:
					errorList.append(e)
			if (len(errorList) > 0):
				raise BackendIOError('\n'.join(errorList))
		
	def deleteProductPropertyDefinitions(self, productId, depotIds=[]):
		
		productId = productId.lower()
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		for depotId in depotIds:
			depotId = depotId.lower()
			
			productFile = None
			try:
				for d in ('localboot', 'netboot'):
					d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
					if not os.path.isdir(d):
						logger.warning("Is not a directory: '%s'" % d)
						continue
					for f in os.listdir(d):
						if (f == productId):
							productFile = os.path.join(d, f)
							break
			except OSError, e:
				raise BackendIOError(e)
			
			if not productFile:
				raise BackendMissingDataError("Cannot delete product property definitions of product '%s': no such product" % productId)
			
			product = Product()
			product.readControlFile(productFile)
			product.productProperties = []
			product.writeControlFile(productFile)
			
		
	def createProductPropertyDefinition(self, productId, name, description=None, defaultValue=None, possibleValues=[], depotIds=[]):
		productId = productId.lower()
		name = name.lower()
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		for depotId in depotIds:
			depotId = depotId.lower()
			productFile = None
			try:
				for d in ('localboot', 'netboot'):
					d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
					if not os.path.isdir(d):
						logger.warning("Is not a directory: '%s'" % d)
						continue
					for f in os.listdir(d):
						if (f == productId):
							productFile = os.path.join(d, f)
							break
			except OSError, e:
				raise BackendIOError(e)
			
			if not productFile:
				raise BackendMissingDataError("Cannot create product property definition for product '%s': no such product" % productId)
			
			logger.debug("Creating product property definition for product '%s': name '%s', description: '%s', defaultValue: '%s', possibleValues: %s" \
						% (productId, name, description, defaultValue, possibleValues) )
			product = Product()
			product.readControlFile(productFile)
			product.productProperties.append(
				ProductProperty(productId	= productId, 
						name		= name,
						description	= description,
						possibleValues	= possibleValues,
						defaultValue	= defaultValue
				)
			)
			product.writeControlFile(productFile)
		
	def getProductProperties_hash(self, productId, objectId = None):
		productId = productId.lower()
		
		if not objectId:
			objectId = self.getDepotId()
		objectId = objectId.lower()
		
		properties = {}
		
		if objectId in self.getDepotIds_list():
			for prop in self.getProductPropertyDefinitions_listOfHashes(productId, objectId):
				properties[prop['name'].lower()] = prop.get('default')
			return properties
		
		for prop in self.getProductPropertyDefinitions_listOfHashes(productId, self.getDepotId(objectId)):
			properties[prop['name'].lower()] = prop.get('default')
		
		iniFile = self.getClientIniFile(objectId)
		ini = self.readIniFile(iniFile)
				
		try:
			for (key, value) in ini.items(productId + "-install"):
				if properties.has_key(key.lower()):
					properties[key.lower()] = value
				else:
					logger.warning("Property '%s' in file '%s' not available for product '%s'" % (key, iniFile, productId))
			
		except ConfigParser.NoSectionError, e:
			# Section <productId>-install does not exist => try the next ini-file
			logger.info("No section '%s-install' in ini-file '%s'" % (productId, self.getClientIniFile(objectId)))
		
		return properties
		
	def setProductProperties(self, productId, properties, objectId = None):
		productId = productId.lower()
		
		props = {}
		for (key, value) in properties.items():
			props[key.lower()] = value
		properties = props
		
		if not objectId:
			objectId = self.getDepotId()
		objectId = objectId.lower()
		
		if objectId in self.getDepotIds_list():
			propDefs = self.getProductPropertyDefinitions_listOfHashes(productId, objectId)
			self.deleteProductPropertyDefinitions(productId, depotIds=[ objectId ])
			for i in range(len(propDefs)):
				if properties.has_key(propDefs[i]['name'].lower()):
					propDefs[i]['default'] = properties[propDefs[i]['name'].lower()]
				self.createProductPropertyDefinition(
							productId = 		productId, 
							name = 			propDefs[i]['name'].lower(),
							description = 		propDefs[i].get('description'),
							defaultValue =		propDefs[i].get('default'),
							possibleValues =	propDefs[i].get('values'),
							depotIds =		[ objectId ])
		else:
			iniFile = self.getClientIniFile(objectId)
			
			# Read the ini file or create if not exists
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError:
				self.createFile(iniFile, mode=0660)
				ini = self.readIniFile(iniFile)
			
			# Remove section if exists
			if ini.has_section(productId + "-install"):
				ini.remove_section(productId.lower() + "-install")
			# Add section
			ini.add_section(productId + "-install")
			
			# Set all properties
			for (key, value) in properties.items():
				ini.set(productId + "-install", key, value)
				
			self.writeIniFile(iniFile, ini)
		
	def deleteProductProperty(self, productId, property, objectId = None):
		productId = productId.lower()
		property = property.lower()
		if not objectId:
			objectId = self.getDepotId()
		objectId = objectId.lower()
		
		iniFiles = []
		if objectId in self.getDepotIds_list():
			self.deleteProductPropertyDefinition(productId = productId, name = property, depotIds = [ objectId ])
			for clientId in self.getClientIds_list(None, objectId):
				iniFiles.append( self.getClientIniFile(clientId) )
		else:
			iniFiles = [ self.getClientIniFile(objectId) ]
		
		errorList = []
		for iniFile in iniFiles:
			ini = None
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				error = "Cannot delete product property '%s' for product '%s' from ini-file '%s': %s" \
							% (property, productId, iniFile, e)
				logger.error(error)
				errorList.append(error)
				continue
			
			if ini.has_section(productId + "-install"):
				if ini.has_option(productId.lower() + "-install", property):
					ini.remove_option(productId.lower() + "-install", property)
				
				if (len(ini.items(productId.lower() + "-install")) == 0):
					# Remove empty section
					ini.remove_section(productId + "-install")
			
			# Write ini file
			try:
				self.writeIniFile(iniFile, ini)
			except BackendIOError, e:
				error = "Cannot delete product property '%s' for product '%s' from ini-file '%s': %s" \
							% (property, productId, iniFile, e)
				logger.error(error)
				errorList.append(error)
				continue
		
		if (len(errorList) > 0):
			raise BackendIOError('\n'.join(errorList))
		
		
	def deleteProductProperties(self, productId, objectId = None):
		productId = productId.lower()
		if not objectId:
			objectId = self.getDepotId()
		objectId = objectId.lower()
		
		iniFiles = []
		if objectId in self.getDepotIds_list():
			self.deleteProductPropertyDefinitions(productId = productId, depotIds = [ objectId ])
			for clientId in self.getClientIds_list(None, objectId):
				iniFiles.append( self.getClientIniFile(clientId) )
		else:
			iniFiles = [ self.getClientIniFile(objectId) ]
		
		errorList = []
		for iniFile in iniFiles:
			ini = None
			try:
				ini = self.readIniFile(iniFile)
			except BackendIOError, e:
				error = "Cannot delete product properties for product '%s' from ini-file '%s': %s" % (productId, iniFile, e)
				logger.error(error)
				errorList.append(error)
				continue
			
			if ini.has_section(productId + "-install"):
				ini.remove_section(productId + "-install")
			
			# Write ini file
			try:
				self.writeIniFile(iniFile, ini)
			except BackendIOError, e:
				error = "Cannot delete product properties for product '%s' from ini-file '%s': %s" % (productId, iniFile, e)
				logger.error(error)
				errorList.append(error)
				continue
		
		if (len(errorList) > 0):
			raise BackendIOError('\n'.join(errorList))
			
	def getProductDependencies_listOfHashes(self, productId = None, depotId=None):
		if productId:
			productId = productId.lower()
		
		if not depotId:
			depotId = self.getDepotId()
		
		dependencies = []
		productFiles = []
		
		try:
			for d in ('localboot', 'netboot'):
				d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
				if not os.path.isdir(d):
					logger.warning("Is not a directory: '%s'" % d)
					continue
				for f in os.listdir(d):
					if not productId or (f == productId):
						productFiles.append( os.path.join(d, f) )
		
		except OSError, e:
			raise BackendIOError(e)
		
		if productId and not productFiles:
			raise BackendMissingDataError("Product '%s' does not exist" % productId)
		
		for productFile in productFiles:
			product = Product()
			product.readControlFile(productFile)
			for dep in product.productDependencies:
				dependencies.append( {
					'productId':			dep.productId,
					'action': 			dep.action,
					'requiredProductId': 		dep.requiredProductId or '',
					'requiredProductClassId': 	dep.requiredProductClassId or '',
					'requiredAction': 		dep.requiredAction or '',
					'requiredInstallationStatus': 	dep.requiredInstallationStatus or '',
					'requirementType': 		dep.requirementType or '',
				} )
		
		return dependencies
	
	
	def createProductDependency(self, productId, action, requiredProductId="", requiredProductClassId="", requiredAction="", requiredInstallationStatus="", requirementType="", depotIds=[]):
		
		productId = productId.lower()
		requiredProductId = requiredProductId.lower()
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		try:
			pd = ProductDependency(productId, action, requiredProductId, requiredProductClassId, 
						requiredAction, requiredInstallationStatus, requirementType)
		except Exception, e:
			raise BackendBadValueError(e)
		
		for depotId in depotIds:
			productFile = None
			try:
				for d in ('localboot', 'netboot'):
					d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
					if not os.path.isdir(d):
						logger.warning("Is not a directory: '%s'" % d)
						continue
					for f in os.listdir(d):
						if (f == productId):
							productFile = os.path.join(d, f)
							break
			except OSError, e:
				raise BackendIOError(e)
			
			if not productFile:
				raise BackendMissingDataError("Product '%s' does not exist" % productId)
			
			product = Product()
			product.readControlFile(productFile)
			product.productDependencies.append(pd)
			product.writeControlFile(productFile)
		
	def deleteProductDependency(self, productId, action="", requiredProductId="", requiredProductClassId="", requirementType="", depotIds=[]):
		
		productId = productId.lower()
		requiredProductId = requiredProductId.lower()
		
		if action and not action in getPossibleProductActions():
			raise BackendBadValueError("Action '%s' is not known" % action)
		#if not requiredProductId and not requiredProductClassId:
		#	raise BackendBadValueError("Either a required product or a required productClass must be set")
		if requirementType and requirementType not in getPossibleRequirementTypes():
			raise BackendBadValueError("Requirement type '%s' is not known" % requirementType)
		
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
		for depotId in depotIds:
			productFile = None
			num = -1
			try:
				for d in ('localboot', 'netboot'):
					d = os.path.join(self.__depotConfigDir, depotId, 'products', d)
					if not os.path.isdir(d):
						logger.warning("Is not a directory: '%s'" % d)
						continue
					for f in os.listdir(d):
						if (f == productId):
							productFile = os.path.join(d, f)
							break
			except OSError, e:
				raise BackendIOError(e)
			
			if not productFile:
				raise BackendMissingDataError("Cannot delete product dependency no such product '%s'" % productId )
			
			product = Product()
			product.readControlFile(productFile)
			if (len(product.productDependencies) == 0):
				logger.warning("Cannot delete product dependency of product '%s': no dependencies exist" % productId )
				return
			
			for i in range(len(product.productDependencies)):
				if ( (not action or (product.productDependencies[i].action == action)) and
				     (not requiredProductId or (product.productDependencies[i].requiredProductId == requiredProductId)) and
				     (not requiredProductClassId or (product.productDependencies[i].requiredProductClassId == requiredProductClassId)) and
				     (not requirementType or (product.productDependencies[i].requirementType == requirementType)) ):
					num = i
			if (num == -1):
				raise BackendIOError("Cannot delete product dependency of product '%s': no such product dependency" % productId )
			
			del product.productDependencies[num]
			product.writeControlFile(productFile)
		
	
	def createLicenseKey(self, productId, licenseKey):
		productId = productId.lower()
		# TODO: productLicenses for each depot ?
		raise NotImplementedError("createLicenseKey() not yet implemeted in File31 backend")
		
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
		
	def getLicenseKey(self, productId, clientId):
		productId = productId.lower()
		clientId = self._preProcessHostId(clientId)
		
		for (key, value) in self.getProductProperties_hash(productId, clientId).items():
			if (key.lower() == 'productkey'):
				return value
		
		freeLicenses = []
		for license in self.getLicenseKeys_listOfHashes(productId):
			hostId = license.get('hostId', '')
			if not hostId:
				freeLicenses.append(license.get('licenseKey', ''))
			elif (hostId == clientId):
				logger.info("Returning licensekey for product '%s' which is assigned to host '%s'"
						% (productId, clientId))
				return license.get('productkey', '')
		
		if (len(freeLicenses) > 0):
			logger.debug( "%s free license(s) found for product '%s'" % (len(freeLicenses), productId) )
			return freeLicenses[0]
		
		raise BackendMissingDataError("No more licenses available for product '%s'" % productId)
	
	def getLicenseKeys_listOfHashes(self, productId):
		productId = productId.lower()
		
		return []
		
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

