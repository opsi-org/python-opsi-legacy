# -*- coding: utf-8 -*-
"""
   ==============================================
   =            OPSI File31 Module              =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.2.6'

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
from OPSI.System import mkdir
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
			self.__pclogDir = windefaultdir + '\\pclog'
			self.__pckeyFile = windefaultdir + '\\opsi\\pckeys'
			self.__passwdFile = windefaultdir + '\\opsi\\passwd'
			self.__groupsFile = windefaultdir + '\\opsi\\config\\clientgroups.ini'
			self.__licensesFile = windefaultdir + '\\opsi\\config\\licenses.ini'
			self.__clientConfigDir = windefaultdir + '\\opsi\\config\\clients'
			self.__globalConfigFile = windefaultdir + '\\opsi\\config\\global.ini'
			self.__depotConfigDir = windefaultdir + '\\opsi\\config\\depots'
			self.__clientTemplatesDir = windefaultdir + '\\opsi\\config\\templates'
			self.__defaultClientTemplateFile = windefaultdir + '\\opsi\\config\\templates\\pcproto.ini'
		else:
			self.__pckeyFile = '/etc/opsi/pckeys'
			self.__passwdFile = '/etc/opsi/passwd'
			self.__pclogDir = '/var/lib/opsi/log'
			self.__groupsFile = '/var/lib/opsi/config/clientgroups.ini'
			self.__licensesFile = '/var/lib/opsi/config/licenses.ini'
			self.__clientConfigDir = '/var/lib/opsi/config/clients'
			self.__globalConfigFile = '/var/lib/opsi/config/global.ini'
			self.__depotConfigDir = '/var/lib/opsi/config/depots'
			self.__clientTemplatesDir = '/var/lib/opsi/config/templates'
			self.__defaultClientTemplateFile = '/var/lib/opsi/config/templates/pcproto.ini'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'pclogdir'):			self.__pclogDir = value
			elif (option.lower() == 'pckeyfile'):			self.__pckeyFile = value
			elif (option.lower() == 'passwdfile'):			self.__passwdFile = value
			elif (option.lower() == 'groupsfile'): 		self.__groupsFile = value
			elif (option.lower() == 'licensesfile'): 		self.__licensesFile = value
			elif (option.lower() == 'defaultdomain'): 		self._defaultDomain = value
			elif (option.lower() == 'clientconfigdir'): 		self.__clientConfigDir = value
			elif (option.lower() == 'globalconfigfile'):		self.__globalConfigFile = value
			elif (option.lower() == 'depotconfigdir'): 		self.__depotConfigDir = value
			elif (option.lower() == 'clienttemplatesdir'): 	self.__clientTemplatesDir = value
			elif (option.lower() == 'defaultclienttemplatefile'): 	self.__defaultClientTemplateFile = value
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
	# -     GENERAL CONFIG                            -
	# -------------------------------------------------
	def setGeneralConfig(self, config, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			# General config for server/domain => edit general.ini
			iniFile = self.__globalConfigFile
		else:
			# General config for specific client => edit <hostname>.ini
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
		ini.add_section("generalconfig")
		
		for (key, value) in config.items():
			ini.set('generalconfig', key, value)
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	def getGeneralConfig_hash(self, objectId = None):
		if not objectId:
			objectId = self.getServerId()
		
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
		
		iniFile = ''
		if (objectId == self.getServerId()) or (objectId == self._defaultDomain):
			iniFile = self.__globalConfigFile
		else:
			# General config for special host => edit <hostname>.ini
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
		ini.add_section("networkconfig")
		
		for (key, value) in config.items():
			if key not in (	'opsiServer', 'utilsDrive', 'depotDrive', 'configDrive', 'utilsUrl', 'depotUrl', 'configUrl', \
					'depotId', 'winDomain', 'nextBootServerType', 'nextBootServiceURL' ):
				logger.error("Unknown networkConfig key '%s'" % key)
				continue
			if (key == 'depotUrl'):
				logger.error("networkConfig: Setting key 'depotUrl' is no longer supported, use depotId")
				continue
			ini.set('networkconfig', key, value)
		
		# Write back ini file
		self.writeIniFile(iniFile, ini)
	
	def getNetworkConfig_hash(self, objectId = None):
		
		if not objectId:
			objectId = self.getServerId()
		
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
			'depotId':	self.getDepotId(),
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
			networkConfig['depotUrl'] = self.getDepot_hash(networkConfig['depotId'])['urlForClient']
		
		# Check if all needed values are set
		if (not networkConfig['opsiServer']
		    or not networkConfig['utilsDrive'] or not networkConfig['depotDrive'] 
		    or not networkConfig['utilsUrl'] or not networkConfig['depotUrl'] ):
			logger.warning("Networkconfig for object '%s' incomplete" % objectId)
		
		return networkConfig
	
	def deleteNetworkConfig(self, objectId):
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
		
		# Copy the client configuration prototype
		if not os.path.exists(iniFile):
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
		ini.set("info", "description", description.replace('\n', '\\n').replace('%', ''))
		ini.set("info", "notes", notes.replace('\n', '\\n').replace('%', ''))
		ini.set('info', 'macaddress', hardwareAddress)
		ini.set("info", "lastseen", '')
		
		
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
			ini = self.readIniFile( "%s.sw" % os.path.join(self.__pclogDir, hostId) )
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
		
		self.deleteSoftwareInformation(hostId)
		
		iniFile = "%s.sw" % os.path.join(self.__pclogDir, hostId)
		
		if not os.path.exists(iniFile):
			self.createFile(iniFile, 0660)
		ini = self.readIniFile(iniFile)
		
		for (key, value) in info.items():
			ini.add_section(key)
			for (k, v) in value.items():
				ini.set(key, k, v)
		
		self.writeIniFile(iniFile, ini)
	
	def deleteSoftwareInformation(self, hostId):
		hostId = hostId.lower()
		try:
			self.deleteFile( "%s.sw" % os.path.join(self.__pclogDir, hostId) )
		except Exception, e:
			logger.error("Failed to delete software information for host '%s': %s" % (hostId, e))
		
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
			
			section = ('_'.join(section.split('_')[:-1])).upper()
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
		logger.info("Getting infos for host '%s'" % hostId)
		
		if hostId in self._aliaslist():
			return { "hostId": hostId, "description": "Depotserver", "notes": "", "lastSeen": "" }
		
		info = {
			"hostId": 	hostId,
			"description":	"",
			"notes":	"",
			"lastSeen":	"" }
		
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
		
		if not depotId:
			depotId = self.getDepotId()
		
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
		return serverId
	
	def getDepotIds_list(self):
		depotIds = []
		for d in os.listdir(self.__depotConfigDir):
			if os.path.isdir( os.path.join(self.__depotConfigDir, d) ):
				depotIds.append(d)
		return depotIds
		
	def getDepotId(self, clientId=None):
		depotId = self.getServerId()
		if clientId:
			depotId = self.getNetworkConfig_hash(objectId = clientId).get('depotId', self.getServerId())
		depotIds = self.getDepotIds_list()
		if depotId not in depotIds:
			raise BackendMissingDataError("Configured depotId '%s' for host '%s' not in list of known depotIds %s" \
								% (depotId, clientId, depotIds) )
		return depotId
	
	def getDepot_hash(self, depotId):
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
			info['urlForClient'] = ini.get('depotshare', 'urlforclient')
		except Exception, e:
			raise BackendIOError("Failed to get info for depot-id '%s': %s" % (depotId, e))
		return info
	
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
		
		iniFile = self.getClientIniFile(hostId)
		ini = self.readIniFile(iniFile)
		
		if not ini.has_section('info'):
			ini.add_Section('info')
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
		
		if hostId in self._aliaslist():
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
			# TODO: move to backendManager / backendManager-config
			cleartext = Tools.blowfishDecrypt( self.getOpsiHostKey(self.getServerId(hostId)), self.getPcpatchPassword(self.getServerId(hostId)) )
			return Tools.blowfishEncrypt( self.getOpsiHostKey(hostId), cleartext )
	
	def setPcpatchPassword(self, hostId, password):
		
		if hostId not in self._aliaslist():
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
	
	def createProduct(self, productType, productId, name, productVersion, packageVersion, licenseRequired=0,
			   setupScript="", uninstallScript="", updateScript="", alwaysScript="", onceScript="",
			   priority=0, description="", advice="", productClassNames=(), pxeConfigTemplate='', depotIds=[]):
		
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
			pxeConfigTemplate	= pxeConfigTemplate )
		
		if (depotIds == self.getDepotIds_list()):
			ini = self.readIniFile( self.__defaultClientTemplateFile )
			
			if not ini.has_section('%s_product_states' % productType):
				ini.add_section('%s_product_states' % productType)
			
			if not ini.has_option('%s_product_states' % productType, productId):
				ini.set('%s_product_states' % productType, productId, 'not_installed:none')
			
			self.writeIniFile( self.__defaultClientTemplateFile, ini)
		
		for depotId in depotIds:
			productDir = os.path.join(self.__depotConfigDir, depotId, 'products', productType)
			if not os.path.exists(productDir):
				mkdir(productDir, mode = 0770 | stat.S_ISGID)
			product.writeControlFile( os.path.join(productDir, productId) )
			os.chmod( os.path.join(productDir, productId), 0660 )
			
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
			raise BackendMissingDataError("Product '%s' not found" % productId)
		
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
			"pxeConfigTemplate":		product.pxeConfigTemplate
		}
	
	def getProductIds_list(self, productType=None, objectId=None, installationStatus=None):
		
		productIds = []
		if not objectId:
			objectId = self.getDepotId()
		
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
		
		installationStatus = []
		
		if objectId in self.getDepotIds_list():
			for productId in self.getProductIds_list(None, objectId):
				p = self.getProduct_hash(productId)
				installationStatus.append( { 
					'productId': productId,
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
		
		if not depotId:
			depotId = self.getDepotId()
		
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
		
		actions = {}
		
		for productId in self.getProductIds_list(None, depotId):
			actions[productId] = self.getPossibleProductActions_list(productId, depotId)
		
		return actions
	
	def getProductActionRequests_listOfHashes(self, clientId):
		
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
		
		netBootProduct = self.getGeneralConfig(clientId).get('os')
		
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
		if not depotIds:
			depotIds = self.getDepotIds_list()
		
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
		
		properties = {}
		
		if objectId in self.getDepotIds_list():
			for prop in self.getProductPropertyDefinitions_listOfHashes(productId, objectId):
				properties[prop['name'].lower()] = prop.get('default')
			return properties
		
		for prop in self.getProductPropertyDefinitions_listOfHashes(productId, self.getDepotId(objectId)):
			properties[prop['name'].lower()] = prop.get('default')
		
		iniFile = self.getClientIniFile(objectId)
		try:
			ini = self.readIniFile(iniFile)
		except BackendIOError, e:
			logger.warning(e)
		
		try:
			for (key, value) in ini.items(productId + "-install"):
				if propertiesdict.has_key(key.lower()):
					properties[key.lower()] = value
				else:
					logger.warning("Property '%s' in file '%s' not available for product '%s'" % (key, iniFile, productId))
			
		except ConfigParser.NoSectionError, e:
			# Section <productId>-install does not exist => try the next ini-file
			logger.info("No section '%s-install' in ini-file '%s'" % (productId, iniFile))
		
		return properties
		
	def setProductProperties(self, productId, properties, objectId = None):
		productId = productId.lower()
		
		props = {}
		for (key, value) in properties.items():
			props[key.lower()] = value
		properties = props
		
		if not objectId:
			objectId = self.getDepotId()
		
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

