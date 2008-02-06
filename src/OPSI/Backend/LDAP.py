# -*- coding: utf-8 -*-
"""
   ==============================================
   =             OPSI LDAP Module               =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.8'

# Imports
import ldap, ldap.modlist, re
import copy as pycopy

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *
from OPSI.Product import *
from OPSI import Tools

# Get logger instance
logger = Logger()

# Globals
POLICY_REF_ATTR_NAME = 'opsiPolicyReference'

# ======================================================================================================
# =                                     CLASS LDAPBACKEND                                              =
# ======================================================================================================
class LDAPBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, session=None, args={}):
		''' LDAPBackend constructor. '''
		
		self._address = address
		self._username = username
		self._password = password
		
		self._backendManager = backendManager
		
		# Default values
		self._baseDn = 'dc=uib,dc=local'
		self._opsiBaseDn = 'cn=opsi,' + self._baseDn
		self._hostsContainerDn = 'cn=hosts,' + self._opsiBaseDn
		self._groupsContainerDn = 'cn=groups,' + self._opsiBaseDn
		self._productsContainerDn = 'cn=products,' + self._opsiBaseDn
		self._productDependenciesContainerDn = 'cn=productDependencies,' + self._opsiBaseDn
		self._productClassesContainerDn = 'cn=productClasses,' + self._opsiBaseDn
		self._productClassDependenciesContainerDn = 'cn=productClassDependencies,' + self._opsiBaseDn
		self._productLicensesContainerDn = 'cn=productLicenses,' + self._opsiBaseDn
		self._productStatesContainerDn = 'cn=productStates,' + self._opsiBaseDn
		self._policiesContainerDn = 'cn=policies,' + self._opsiBaseDn
		self._productPropertyPoliciesContainerDn = 'cn=productProperties,' + self._policiesContainerDn 
		self._productDeploymentPoliciesContainerDn = 'cn=productDeployments,' + self._policiesContainerDn 
		self._networkConfigPoliciesContainerDn = 'cn=networkConfigs,' + self._policiesContainerDn 
		self._generalConfigPoliciesContainerDn = 'cn=generalConfigs,' + self._policiesContainerDn 
		self._policyReferenceAttributeName = 'opsiPolicyReference'
		self._policyReferenceObjectClass = 'opsiPolicyReference'
		
		self._defaultDomain = None
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'basedn'):					self._baseDn = value
			elif (option.lower() == 'opsibasedn'):					self._opsiBaseDn = value
			elif (option.lower() == 'hostscontainerdn'):				self._hostsContainerDn = value
			elif (option.lower() == 'groupscontainerdn'):				self._groupsContainerDn = value
			elif (option.lower() == 'productscontainerdn'):			self._productsContainerDn = value
			elif (option.lower() == 'productdependenciescontainerdn'):		self._productDependenciesContainerDn = value
			elif (option.lower() == 'productclassescontainerdn'):			self._productClassesContainerDn = value
			elif (option.lower() == 'productclassdependenciescontainerdn'):	self._productClassDependenciesContainerDn = value
			elif (option.lower() == 'productlicensescontainerdn'):			self._productLicensesContainerDn = value
			elif (option.lower() == 'policiescontainerdn'):			self._policiesContainerDn = value
			elif (option.lower() == 'productpropertypoliciescontainerdn'):	self._productPropertyPoliciesContainerDn = value
			elif (option.lower() == 'productstatescontainerdn'):			self._productStatesContainerDn = value
			elif (option.lower() == 'productdeploymentpoliciescontainerdn'):	self._productDeploymentPoliciesContainerDn = value
			elif (option.lower() == 'networkconfigpoliciescontainerdn'):		self._networkConfigPoliciesContainerDn = value
			elif (option.lower() == 'generalconfigpoliciescontainerdn'):		self._generalConfigPoliciesContainerDn = value
			elif (option.lower() == 'defaultdomain'): 				self._defaultDomain = value
			elif (option.lower() == 'host'):					self._address = value
			elif (option.lower() == 'binddn'):					self._username = value
			elif (option.lower() == 'bindpw'):					self._password = value
			elif (option.lower() == 'policyreferenceattributename'):		self._policyReferenceAttributeName = value
			elif (option.lower() == 'policyreferenceobjectclass'):			self._policyReferenceObjectClass = value
			else:
				logger.warning("Unknown argument '%s' passed to LDAPBackend constructor" % option)
		
		if session:
			self._ldap = session
		else:
			logger.info("Connecting to ldap server '%s' as user '%s'" % (self._address, self._username))
			self._ldap = Session(	host	 = self._address,
						username = self._username, 
						password = self._password )
			self._ldap.baseDn = self._baseDn
			self._ldap.connect()
		
	
	def exit(self):
		self._ldap.disconnect()
	
	def createOpsiBase(self):
		# Add policyReference objectClass to base-dn
		base = Object(self._baseDn)
		base.readFromDirectory(self._ldap)
		base.addAttributeValue('objectClass', self._policyReferenceObjectClass)
		base.setAttribute(self._policyReferenceAttributeName, [])
		base.writeToDirectory(self._ldap)
		
		# Create some containers
		self.createOrganizationalRole(self._opsiBaseDn)
		self.createOrganizationalRole(self._hostsContainerDn)
		self.createOrganizationalRole(self._groupsContainerDn)
		self.createOrganizationalRole(self._productsContainerDn)
		self.createOrganizationalRole(self._productDependenciesContainerDn)
		self.createOrganizationalRole(self._productClassesContainerDn)
		self.createOrganizationalRole(self._productClassDependenciesContainerDn)
		self.createOrganizationalRole(self._policiesContainerDn)
		self.createOrganizationalRole(self._productPropertyPoliciesContainerDn)
		self.createOrganizationalRole(self._productStatesContainerDn)
		self.createOrganizationalRole(self._productDeploymentPoliciesContainerDn)
		self.createOrganizationalRole(self._networkConfigPoliciesContainerDn)
		self.createOrganizationalRole(self._generalConfigPoliciesContainerDn)
		self.createOrganizationalRole(self._productLicensesContainerDn)
		
	
	def getHostContainerDn(self, domain = None):
		if not domain:
			domain = self._defaultDomain
		elif (self._defaultDomain and domain != self._defaultDomain):
			raise NotImplementedError ("Multiple domains not supported yet, domain was '%s', default domain is %s''" 
							% (domain, self._defaultDomain))
		return self._hostsContainerDn
	
	
	def getHostId(self, hostDn):
		#m = re.search('^cn=([^,]+),.*%s$' % self._hostsContainerDn, hostDn)
		m = re.search('^cn=([^,]+),(.*)', hostDn)
		if not m:
			raise BackendBadValueError("Bad hostDn '%s'" % hostDn)
		
		domain = ''
		for part in m.group(2).split(','):
			pos = part.find("=")
			if (part[:pos] == 'dc'):
				if domain:
					domain += '.'
				domain += part[pos+1:]
		return m.group(1).lower() + '.' + domain
	
	
	def getHostDn(self, hostId):
		''' Get a host's DN by host's ID. '''
		hostId = hostId.lower()
		
		parts = hostId.split('.')
		if ( len(parts) < 3 ):
			raise BackendBadValueError("Bad hostId '%s'" % hostId)
		hostName = parts[0]
		domain = '.'.join(parts[1:])
		# Search hostname in host conatiner of the domain
		try:
			search = ObjectSearch(self._ldap, self.getHostContainerDn(domain), 
					filter='(&(objectClass=opsiHost)(cn=%s))' % hostName)
			return search.getDn()
		except BackendMissingDataError, e:
			raise BackendMissingDataError("Host '%s' does not exist: %s" % (hostId, e))
	
	
	def getObjectDn(self, objectId):
		''' Get a object's DN by object's ID. '''
		
		if (objectId.find('=') != -1):
			# Object seems to be a dn
			return objectId
		elif (objectId == self._defaultDomain):
			# Object is the default domain
			return self._baseDn
		else:
			# Object is a host
			return self.getHostDn(objectId)
	
	# -------------------------------------------------
	# -     GENERAL CONFIG                            -
	# -------------------------------------------------
	def setGeneralConfig(self, config, objectId = None):
		if not objectId or (objectId == self.getServerId()):
			# set for whole domain
			objectId = self._defaultDomain
		
		# Create a GeneralConfigPolicy
		self.createGeneralConfigPolicy(self.getObjectDn(objectId), config)
		
	def getGeneralConfig_hash(self, objectId = None):
		if not objectId or (objectId == self.getServerId()):
			# get for whole domain
			objectId = self._defaultDomain
		
		generalConfig = { 
			'pcptchBitmap1': 		'',
			'pcptchBitmap2':		'',
			'pcptchLabel1':			'',
			'pcptchLabel2':			'',
			'button_stopnetworking':	'',
			'secsUntilConnectionTimeOut':	'180' }
		
		objectDn = self.getObjectDn(objectId)
		# Get result from networkConfigPolicies
		logger.debug("getGeneralConfig_hash for object: '%s'" % objectDn)
		try:
			search = PolicySearch(
					self._ldap, objectDn, 
					policyContainer = self._generalConfigPoliciesContainerDn, 
					policyFilter = '(objectClass=opsiPolicyGeneralConfig)',
					policyReferenceObjectClass = self._policyReferenceObjectClass,
					policyReferenceAttributeName = self._policyReferenceAttributeName )
		except BackendMissingDataError:
			logger.error("Failed to get general config for '%s': %s" % (objectId, e))
			return generalConfig
		
		for (key, value) in search.getResult().items():
			value = value['value']
			if (key == 'opsiButtonStopNetworking'):
				key = 'button_stopnetworking'
			elif key in [ 'opsiPcptchBitmap1', 'opsiPcptchBitmap2', 'opsiPcptchLabel1', 'opsiPcptchLabel2', 'opsiSecsUntilConnectionTimeOut' ]:
				key = key[4].lower() + key[5:]
			
			generalConfig[key] = value
			
		return generalConfig
	
	def deleteGeneralConfig(self, objectId):
		objectDn = self.getObjectDn(objectId)
		try:
			search = PolicySearch(
				self._ldap, objectDn, maxLevel = 1,
				policyContainer = self._generalConfigPoliciesContainerDn, 
				policyFilter = '(objectClass=opsiPolicyGeneralConfig)',
				policyReferenceObjectClass = self._policyReferenceObjectClass,
				policyReferenceAttributeName = self._policyReferenceAttributeName )
		except BackendMissingDataError, e:
			logger.warning("Failed to delete generalConfig for object '%s': %s" % (objectId, e))
			return
		
		for ref in search.getReferences():
			logger.debug("Deleting policy '%s'" % ref)
			self.deletePolicy(ref)
	
	# -------------------------------------------------
	# -     NETWORK FUNCTIONS                         -
	# -------------------------------------------------
	def setNetworkConfig(self, config, objectId = None):
		if not objectId or (objectId == self.getServerId()):
			# set for whole domain
			objectId = self._defaultDomain
		
		serverId = config.get('opsiServer')
		
		objectDn = self.getObjectDn(objectId)
		serverDn = None
		if serverId:
			serverDn = self.getHostDn(serverId)
		
		# Create a networkConfigPolicy
		self.createNetworkConfigPolicy( objectDn, config, serverDn)
		
	def getNetworkConfig_hash(self, objectId = None):
		if not objectId or (objectId == self.getServerId()):
			# get for whole domain
			objectId = self._defaultDomain
		
		objectDn = self.getObjectDn(objectId)
		
		networkConfig = { 
			'opsiServer': 	'',
			'utilsDrive':	'',
			'depotDrive':	'',
			'configDrive':	'',
			'utilsUrl':	'',
			'depotUrl':	'',
			'configUrl':	'',
			'winDomain':	'',
			'nextBootServerType': '',
			'nextBootServiceURL': ''}
		
		config = {}
		try:
			# Get result from networkConfigPolicies
			search = PolicySearch(	self._ldap, objectDn, 
						policyContainer = self._networkConfigPoliciesContainerDn, 
						policyFilter = '(objectClass=opsiPolicyNetworkConfig)',
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
			
			config = search.getAttributeDict()
		except BackendMissingDataError:
			logger.error("Failed to get network config for '%s': %s" % (objectId, e))
			return networkConfig
		
		for (key, value) in config.items():
			logger.debug(key)
			logger.debug(key[4].lower() + key[5:])
			if (key == "opsiServerReference"):
				networkConfig['opsiServer'] = self.getHostId(value)
			elif key.startswith("opsi"):
				networkConfig[key[4].lower() + key[5:]] = value
			
		return networkConfig
	
	def deleteNetworkConfig(self, objectId):
		objectDn = self.getObjectDn(objectId)
		try:
			search = PolicySearch(
				self._ldap, objectDn, maxLevel = 1,
				policyContainer = self._networkConfigPoliciesContainerDn, 
				policyFilter = '(objectClass=opsiPolicyNetworkConfig)',
				policyReferenceObjectClass = self._policyReferenceObjectClass,
				policyReferenceAttributeName = self._policyReferenceAttributeName )
		except BackendMissingDataError, e:
			logger.warning("Failed to delete networkConfig for object '%s': %s" % (objectId, e))
			return
		
		for ref in search.getReferences():
			logger.debug("Deleting policy '%s'" % ref)
			self.deletePolicy(ref)
		
	
	# -------------------------------------------------
	# -     HOST FUNCTIONS                            -
	# -------------------------------------------------
	def createServer(self, serverName, domain, description=None, notes=None):
		# Create a dn
		serverDn = "cn=%s,%s" % (serverName, self.getHostContainerDn(domain))
		# Create an LDAP object from dn
		server = Object(serverDn)
		# Set objectClasses
		server.new('opsiServer', self._policyReferenceObjectClass)
		# Set description attribute
		if description:
			server.setAttribute('description', [ description ])
		if notes:
			server.setAttribute('opsiNotes', [ notes ])
		# Write object to LDAP
		server.writeToDirectory(self._ldap)
		
		return self.getHostId(serverDn)
	
	def createClient(self, clientName, domain=None, description=None, notes=None, ipAddress=None, hardwareAddress=None):
		if not re.search(CLIENT_ID_REGEX, clientName):
			raise BackendBadValueError("Unallowed char in hostname")
		
		if not domain:
			domain = self._defaultDomain
		
		# Create client object
		clientDn = "cn=%s,%s" % (clientName, self.getHostContainerDn(domain))
		client = Object(clientDn)
		try:
			client.readFromDirectory(self._ldap)
		except BackendIOError:
			client.new('opsiClient', self._policyReferenceObjectClass)
		if description:
			client.setAttribute('description', [ description ])
		if notes:
			client.setAttribute('opsiNotes', [ notes ])
		client.writeToDirectory(self._ldap)
		
		# Create product states container
		self.createOrganizationalRole("cn=%s,%s" % (clientName, self._productStatesContainerDn))
		
		return self.getHostId(clientDn)
	
	def _deleteHost(self, hostId):
		client = Object( self.getHostDn(hostId) )
		
		# Delete product states container
		try:
			search = ObjectSearch(self._ldap, "cn=%s,%s" % (client.getCn(), self._productStatesContainerDn))
			productStatesCont = search.getObject()
			productStatesCont.deleteFromDirectory(self._ldap, recursive = True)
		except BackendMissingDataError, e:
			logger.info(e)
		
		# Delete all policies exclusively referenced by client
		client.readFromDirectory(self._ldap)
		for reference in client.getAttributeDict(valuesAsList = True).get(self._policyReferenceAttributeName, []):
			self.deletePolicyReference(reference, client.getDn())
		
		# Delete client from groups
		groups = []
		try:
			search = ObjectSearch(self._ldap, self._groupsContainerDn, 
						filter='(&(objectClass=opsiGroup)(uniqueMember=%s))' % client.getDn())
			groups = search.getObjects()
		except BackendMissingDataError, e:
			pass
		
		for group in groups:
			logger.info("Removing client '%s' from group '%s'" % (hostId, group.getCn()))
			group.readFromDirectory(self._ldap)
			group.deleteAttributeValue('uniqueMember', client.getDn())
			group.writeToDirectory(self._ldap)
		
		# Delete client object and possible childs
		client.deleteFromDirectory(self._ldap, recursive = True)
	
	def deleteServer(self, serverId):
		return self._deleteHost(serverId)
	
	def deleteClient(self, clientId):
		return self._deleteHost(clientId)
	
	def setHostLastSeen(self, hostId, timestamp):
		logger.debug("Setting last-seen timestamp for host '%s' to '%s'" % (hostId, timestamp))
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('opsiLastSeenTimestamp', [ timestamp ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
	
	def setHostDescription(self, hostId, description):
		logger.debug("Setting description for host '%s' to '%s'" % (hostId, description))
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('description', [ description ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
	
	def setHostNotes(self, hostId, notes):
		if not notes:
			return
		
		logger.debug("Setting notes for host '%s' to '%s'" % (hostId, notes))
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('opsiNotes', [ notes ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
	
	def addHardwareInformation(self, hostId, info):
		cn = ''
		if info.get('bus'):
			cn = info.get('bus') + '_' + info.get('busAddress', 'unknown')
		
		
		objectClass = 'opsiDevice'
		if info.get('class', '') not in HARDWARE_CLASSES:
			raise BackendBadValueError('Unknown hardware class: %s' % info.get('class'))
		
		if   (info.get('class') == 'BRIDGE'):			objectClass = 'opsiDeviceBridge'
		elif (info.get('class') == 'HOST_BRIDGE'):		objectClass = 'opsiDeviceHostBridge'
		elif (info.get('class') == 'ISA_BRIDGE'):		objectClass = 'opsiDeviceISABridge'
		elif (info.get('class') == 'PCI_BRIDGE'):		objectClass = 'opsiDevicePCIBridge'
		elif (info.get('class') == 'SM_BUS'):			objectClass = 'opsiDeviceSMBus'
		elif (info.get('class') == 'USB_CONTROLLER'):		objectClass = 'opsiDeviceUSBController'
		elif (info.get('class') == 'FIREWIRE_CONTROLLER'):	objectClass = 'opsiDeviceFireWireController'
		elif (info.get('class') == 'AUDIO_CONTROLLER'):	objectClass = 'opsiDeviceAudioController'
		elif (info.get('class') == 'ETHERNET_CONTROLLER'):	objectClass = 'opsiDeviceEthernetController'
		elif (info.get('class') == 'VGA_CONTROLLER'):		objectClass = 'opsiDeviceVGAController'
		elif (info.get('class') == 'IDE_INTERFACE'):		objectClass = 'opsiDeviceIDEInterface'
		elif (info.get('class') == 'SCSI_CONTROLLER'):		objectClass = 'opsiDeviceSCSIController'
		elif (info.get('class') == 'BASE_BOARD'):		
			objectClass = 'opsiDeviceBaseBoard'
			cn = 'base_board'
		elif (info.get('class') == 'SYSTEM'):			
			objectClass = 'opsiDeviceSystem'
			cn = 'system'
		elif (info.get('class') == 'SYSTEM_SLOT'):		
			objectClass = 'opsiDeviceSystemSlot'
			cn = 'slot_' + info.get('id', '?').replace(' ','')
		elif (info.get('class') == 'SYSTEM_BIOS'):		
			objectClass = 'opsiDeviceSystemBIOS'
			cn = 'system_bios'
		elif (info.get('class') == 'CHASSIS'):		
			objectClass = 'opsiDeviceChassis'
			cn = 'chassis'
		elif (info.get('class') == 'PROCESSOR'):		
			objectClass = 'opsiDeviceProcessor'
			cn = 'cpu_' + info.get('id', '?').replace(' ','')
		elif (info.get('class') == 'MEMORY_CONTROLLER'):		
			objectClass = 'opsiDeviceMemoryController'
			cn = 'memory_controller'
		elif (info.get('class') == 'MEMORY_MODULE'):
			objectClass = 'opsiDeviceMemoryModule'
			cn = 'memory_module_' + info.get('socket', info.get('locator','?')).replace(' ','')
		elif (info.get('class') == 'CACHE'):
			objectClass = 'opsiDeviceCache'
			cn = 'cache_' + info.get('id','?').replace(' ','')
		elif (info.get('class') == 'PORT_CONNECTOR'):
			objectClass = 'opsiDevicePortConnector'
			cn = 'port_' + info.get('name','?').replace(' ','_')
		elif (info.get('class') == 'HARDDISK'):
			objectClass = 'opsiDeviceHarddisk'
			cn = 'disk_' + info.get('serialnumber', info.get('busAddress','?'))
		
		hw = Object( 'cn=%s,%s' % (cn, self.getHostDn(hostId)) )
		
		hw.new(objectClass)
		hw.setAttribute('deviceBus', [ info.get('bus') ])
		hw.setAttribute('deviceName', [ info.get('name') ])
		hw.setAttribute('deviceVendor', [ info.get('vendor') ])
		hw.setAttribute('deviceVersion', [ info.get('version') ])
		hw.setAttribute('deviceSerialNumber', [ info.get('serialnumber') ])
		if info.get('info'):
			hw.setAttribute('deviceInfo', [ info.get('info') ] )
		hw.setAttribute('deviceSubsystemName', [ info.get('subsystemName') ])
		hw.setAttribute('deviceSubsystemVendor', [ info.get('subsystemVendor') ])
		hw.setAttribute('deviceBusAddress', [ info.get('busAddress') ])
		if info.get('id'):
			hw.setAttribute('deviceId', [ info.get('id') ])
		hw.setAttribute('deviceFlag', info.get('flags', []) )
		used = info.get('used', None)
		if (used == True):
			used = 'TRUE'
		elif (used == False):
			used = 'FALSE'
		hw.setAttribute('deviceUsed', [ used ])
		hw.setAttribute('deviceLength', [ info.get('length') ])
		hw.setAttribute('deviceType', [ info.get('type') ])
		hw.setAttribute('deviceLocator', [ info.get('locator') ])
		
		if (info.get('class') == 'ETHERNET_CONTROLLER'):
			hw.setAttribute('ethernetMacAddress', [ info.get('macAddress') ])
		
		if (info.get('class') == 'PROCESSOR'):
			hw.setAttribute('deviceSocket', [ info.get('socket') ])
			hw.setAttribute('processorFamily', [ info.get('family') ])
			hw.setAttribute('processorSignature', [ info.get('signature') ])
			hw.setAttribute('processorVoltage', [ info.get('voltage') ])
			hw.setAttribute('processorExternalClock', [ info.get('externalClock') ])
			hw.setAttribute('processorMaxSpeed', [ info.get('maxSpeed') ])
			hw.setAttribute('processorCurrentSpeed', [ info.get('currentSpeed') ])
		
		elif (info.get('class') == 'MEMORY_MODULE'):
			hw.setAttribute('deviceSocket', [ info.get('socket') ])
			hw.setAttribute('memoryTotalWidth', [ info.get('totalWidth') ] )
			hw.setAttribute('memoryDataWidth', [ info.get('dataWidth') ] )
			hw.setAttribute('memorySize', [ info.get('size') ])
			hw.setAttribute('memoryFormFactor', [ info.get('formFactor') ])
			hw.setAttribute('memoryBankLocator', [ info.get('bankLocator') ])
		
		elif (info.get('class') == 'CACHE'):
			hw.setAttribute('deviceSocket', [ info.get('socket') ])
		
		elif (info.get('class') == 'PORT_CONNECTOR'):
			hw.setAttribute('internalConnectorName', [ info.get('internalConnectorName') ])
			hw.setAttribute('internalConnectorType', [ info.get('internalConnectorType') ])
			hw.setAttribute('externalConnectorName', [ info.get('externalConnectorName') ])
			hw.setAttribute('externalConnectorType', [ info.get('externalConnectorType') ])
			
		elif (info.get('class') == 'HARDDISK'):
			partitions = []
			for p in info.get('partition', []):
				partitions.append(str(p)[1:-1])
			if partitions:
				hw.setAttribute('harddiskPartition', partitions)
			hw.setAttribute('harddiskSize', [ info.get('size') ])
			hw.setAttribute('harddiskCylinders', [ info.get('cylinders') ])
			hw.setAttribute('harddiskHeads', [ info.get('heads') ])
			hw.setAttribute('harddiskSectors', [ info.get('sectors') ])
		
		hw.writeToDirectory(self._ldap)
		
	
	def getHardwareInformation_listOfHashes(self, hostId):
		hardware = []
		try:
			# Search all hardware objects in hosts container
			search = ObjectSearch(self._ldap, self.getHostDn(hostId), filter='(objectClass=opsiDevice)')
		except BackendMissingDataError:
			# No hardware found
			logger.warning("No hardware info for host '%s' found in LDAP" % hostId)
			return []
		
		for hardwareObject in search.getObjects():
			hardwareObject.readFromDirectory(self._ldap)
			attributes = hardwareObject.getAttributeDict()
			newAttributes = {}
			for (key, value) in attributes.items():
				if (key == 'cn'):
					continue
				if (key == 'objectClass'):
					if   'opsiDeviceBridge' in value: 		newAttributes['class'] = 'BRIDGE'
					elif 'opsiDeviceHostBridge' in value: 		newAttributes['class'] = 'HOST_BRIDGE'
					elif 'opsiDeviceISABridge' in value: 		newAttributes['class'] = 'ISA_BRIDGE'
					elif 'opsiDevicePCIBridge' in value: 		newAttributes['class'] = 'PCI_BRIDGE'
					elif 'opsiDeviceSMBus' in value: 		newAttributes['class'] = 'SM_BUS'
					elif 'opsiDeviceUSBController' in value: 	newAttributes['class'] = 'USB_CONTROLLER'
					elif 'opsiDeviceFireWireController' in value: 	newAttributes['class'] = 'FIREWIRE_CONTROLLER'
					elif 'opsiDeviceAudioController' in value: 	newAttributes['class'] = 'AUDIO_CONTROLLER'
					elif 'opsiDeviceEthernetController' in value: 	newAttributes['class'] = 'ETHERNET_CONTROLLER'
					elif 'opsiDeviceVGAController' in value: 	newAttributes['class'] = 'VGA_CONTROLLER'
					elif 'opsiDeviceIDEInterface' in value: 	newAttributes['class'] = 'IDE_INTERFACE'
					elif 'opsiDeviceBaseBoard' in value:		newAttributes['class'] = 'BASE_BOARD'
					elif 'opsiDeviceSystemSlot' in value: 		newAttributes['class'] = 'SYSTEM_SLOT'
					elif 'opsiDeviceSystemBIOS' in value: 		newAttributes['class'] = 'SYSTEM_BIOS'
					elif 'opsiDeviceSystem' in value: 		newAttributes['class'] = 'SYSTEM'
					elif 'opsiDeviceChassis' in value: 		newAttributes['class'] = 'CHASSIS'
					elif 'opsiDeviceProcessor' in value: 		newAttributes['class'] = 'PROCESSOR'
					elif 'opsiDeviceMemoryModule' in value: 	newAttributes['class'] = 'MEMORY_MODULE'
					elif 'opsiDeviceMemoryController' in value: 	newAttributes['class'] = 'MEMORY_CONTROLLER'
					elif 'opsiDeviceCache' in value: 		newAttributes['class'] = 'CACHE'
					elif 'opsiDevicePortConnector' in value: 	newAttributes['class'] = 'PORT_CONNECTOR'
					elif 'opsiDeviceHarddisk' in value: 		newAttributes['class'] = 'HARDDISK'
					else : newAttributes['class'] = 'UNKNOWN'
				elif key.startswith('device'):
					newAttributes[key[6].lower()+key[7:]] = value
				elif key.startswith('processor'):
					newAttributes[key[9].lower()+key[10:]] = value
				elif key.startswith('memory'):
					newAttributes[key[6].lower()+key[7:]] = value
				elif key.startswith('ethernet'):
					newAttributes[key[8].lower()+key[9:]] = value
				elif key.startswith('harddisk'):
					newAttributes[key[8].lower()+key[9:]] = value
				else:
					newAttributes[key] = value
				
			hardware.append(newAttributes)
		
		return hardware
	
	def deleteHardwareInformation(self, hostId):
		try:
			# Search all hardware objects in hosts container
			search = ObjectSearch(self._ldap, self.getHostDn(hostId), filter='(objectClass=opsiDevice)')
			for obj in search.getObjects():
				obj.deleteFromDirectory(self._ldap)
		except BackendMissingDataError:
			# No hardware found
			logger.warning("No hardware info for host '%s' found in LDAP" % hostId)
			return []
	
	def getHost_hash(self, hostId):
		host = Object( self.getHostDn(hostId) )
		host.readFromDirectory(self._ldap, 'description', 'opsiNotes', 'opsiLastSeenTimestamp')
		return { 	'hostId': 	hostId,
				'description':	host.getAttribute('description', ""),
				'notes':	host.getAttribute('opsiNotes', ""),
				'lastSeen':	host.getAttribute('opsiLastSeenTimestamp', "") }
	
	def getClients_listOfHashes(self, serverId = None, depotId=None, groupId = None, productId = None, installationStatus = None, actionRequest = None, productVersion = None, packageVersion = None):
		# TODO: groups
		if productId:
			productId = productId.lower()
		
		if groupId and not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		hostDns = []
		if not serverId:
			# No server id given => search all registered clients
			try:
				# Search all opsiClient objects in host container
				search = ObjectSearch(self._ldap, self.getHostContainerDn(), filter='(objectClass=opsiClient)')
			except BackendMissingDataError:
				# No client found
				logger.warning("No clients found in LDAP")
				return []
			# Map client dns to client ids
			
			hostDns = search.getDns()
		
		else:
			# Specific server given => only search connected clients
			# Create LDAP object
			server = Object( self.getHostDn(serverId) )
			# Try if exists in LDAP
			server.readFromDirectory(self._ldap, 'dn')
			
			# Search all opsiClient objects in host container of server's domain
			clients = []
			try:
				search = ObjectSearch(self._ldap, self.getHostContainerDn( self.getDomain(serverId) ), filter='(objectClass=opsiClient)')
				clients = search.getObjects()
			except BackendMissingDataError:
				logger.warning("No clients found in LDAP")
				return []
			
			for client in clients:
				try:
					# Get client's networkConfig policy
					policySearch = PolicySearch(
							self._ldap, client.getDn(),
							policyContainer = self._networkConfigPoliciesContainerDn,
							policyFilter = '(&(objectClass=opsiPolicyNetworkConfig)(opsiServerReference=%s))' % server.getDn(),
							policyReferenceObjectClass = self._policyReferenceObjectClass,
							policyReferenceAttributeName = self._policyReferenceAttributeName )
					policy = policySearch.getObject()				
				except (BackendMissingDataError, BackendIOError), e:
					logger.warning("Error while searching policy: %s" % e)
					continue
				if not policy.getAttribute('opsiServerReference'):
					continue
				if ( policy.getAttribute('opsiServerReference') == server.getDn() ):
					# Client is connected to the specified server
					hostDns.append(client.getDn())
		
		if groupId:
			filteredHostDns = []
			group = Object( "cn=%s,%s" % (groupId, self._groupsContainerDn) )
			try:
				group.readFromDirectory(self._ldap)
			except BackendMissingDataError, e:
				raise BackendMissingDataError("Group '%s' not found: %s" % (groupId, e))
			
			for member in group.getAttribute('uniqueMember', valuesAsList=True):
				if member in hostDns and not member in filteredHostDns:
					filteredHostDns.append(member)
			hostDns = filteredHostDns
		
		if installationStatus or actionRequest or productVersion or packageVersion:
			filteredHostDns = []
			
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
			
			logger.info("Filtering hostIds by productId: '%s', installationStatus: '%s', actionRequest: '%s'" \
				% (productId, installationStatus, actionRequest))
			
			for hostDn in hostDns:
				# Search product ldap-object
				filter = '(&(objectClass=opsiProductState)(opsiHostReference=%s))' % hostDn
				if productId:
					filter = '(&%s(cn=%s))' % (filter, productId)
				if installationStatus:
					filter = '(&%s(opsiProductInstallationStatus=%s))' % (filter, installationStatus)
				# TODO: action by policy
				if actionRequest:
					filter = '(&%s(opsiProductActionRequestForced=%s))' % (filter, actionRequest)
				
				logger.debug("ProductStates filter: '%s'" % filter)
				
				try:
					hostCn = ((hostDn.split(','))[0].split('='))[1].strip()
					productStateSearch = ObjectSearch(
								self._ldap, 
								"cn=%s,%s" % (hostCn, self._productStatesContainerDn),
								filter = filter )
					
					state = productStateSearch.getObject()
					state.readFromDirectory(self._ldap, 'opsiProductVersion', 'opsiPackageVersion')
					if productVersion not in ('', None):
						v = state.getAttribute('opsiProductVersion', '0')
						if not v: v = '0'
						if not Tools.compareVersions(v, productVersionC, productVersionS):
							continue
					if packageVersion not in ('', None):
						v = state.getAttribute('opsiPackageVersion', '0')
						if not v: v = '0'
						if not Tools.compareVersions(v, packageVersionC, packageVersionS):
							continue
					
					logger.info("Host '%s' matches filter" % hostDn)
					filteredHostDns.append(hostDn)
				except BackendMissingDataError:
					pass
				
					
			hostDns = filteredHostDns
		
		infos = []
		for hostDn in hostDns:
			host = Object(hostDn)
			host.readFromDirectory(self._ldap, 'description', 'opsiNotes', 'opsiLastSeenTimestamp')
			infos.append( { 
				'hostId': 	self.getHostId(host.getDn()),
				'description':	host.getAttribute('description', ""),
				'notes':	host.getAttribute('opsiNotes', ""),
				'lastSeen':	host.getAttribute('opsiLastSeenTimestamp', "") } )
		return infos
	
	def getClientIds_list(self, serverId = None, depotId=None, groupId = None, productId = None, installationStatus = None, actionRequest = None, productVersion = None, packageVersion = None):
		clientIds = []
		for info in self.getClients_listOfHashes(serverId, depotId, groupId, productId, installationStatus, actionRequest, productVersion, packageVersion):
			clientIds.append( info.get('hostId') )
		return clientIds
	
	def getServerIds_list(self):
		# Search all ldap-objects of type opsiServer in the host container
		search = None
		try:
			search = ObjectSearch(self._ldap, self.getHostContainerDn(), filter='(objectClass=opsiServer)')
		except BackendMissingDataError:
			return []
		
		serverDns = search.getDns()
		ids = []
		for serverDn in serverDns:
			ids.append( self.getHostId(serverDn) )
		return ids
	
	def getServerId(self, clientId=None):
		if not clientId:
			(name, aliaslist, addresslist) = socket.gethostbyname_ex(socket.gethostname())
			if ( len(name.split('.')) > 1 ):
				self.fqdn = name
			else:
				raise Exception("Failed to get my own fully qualified domainname")
			return name
		
		# Get opsiServerReference from client's policy
		clientDn = self.getHostDn(clientId)
		policySearch = PolicySearch(	self._ldap, clientDn,
						policyContainer = self._networkConfigPoliciesContainerDn,
						policyFilter = '(objectClass=opsiPolicyNetworkConfig)',
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
		serverDn = policySearch.getAttribute('opsiServerReference')
		# Return server's id
		return self.getHostId(serverDn)
	
	def getDepotIds_list(self):
		return []
	
	def getDepotId(self, clientId=None):
		return
	
	def getOpsiHostKey(self, hostId):
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend (attribute opsiHostKey only)
		host.readFromDirectory(self._ldap, 'opsiHostKey')
		return host.getAttribute('opsiHostKey')
		
	def setOpsiHostKey(self, hostId, opsiHostKey):
		logger.debug("Setting host key for host '%s'" % hostId)
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('opsiHostKey', [ opsiHostKey ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
	
	def deleteOpsiHostKey(self, hostId):
		logger.debug("Deleting host key for host '%s'" % hostId)
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('opsiHostKey', [ ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
	
	def createGroup(self, groupId, members = [], description = ""):
		if not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		self.deleteGroup(groupId)
		
		# Create group object
		group = Object( "cn=%s,%s" % (groupId, self._groupsContainerDn) )
		group.new('opsiGroup')
		search = ObjectSearch(self._ldap, self.getHostContainerDn(), filter='(objectClass=opsiClient)')
		if ( type(members) != type([]) and type(members) != type(()) ):
			members = [ members ]
		for member in members:
			group.addAttributeValue('uniqueMember', self.getHostDn(member))
		if description:
			group.setAttribute('description', [ description ])
		group.writeToDirectory(self._ldap)
		
	def getGroupIds_list(self):
		try:
			search = ObjectSearch(self._ldap, self._groupsContainerDn, filter='(objectClass=opsiGroup)')
			groupIds = search.getCns()
			return groupIds
		except BackendMissingDataError, e:
			logger.warning("No groups found: %s" % e)
			return []
	
	def deleteGroup(self, groupId):
		if not re.search(GROUP_ID_REGEX, groupId):
			raise BackendBadValueError("Bad group-id: '%s'" % groupId)
		
		# Create group object
		group = Object( "cn=%s,%s" % (groupId, self._groupsContainerDn) )
		
		# Delete group object from ldap if exists
		try:
			group.deleteFromDirectory(self._ldap)
		except:
			pass
	
	# -------------------------------------------------
	# -     PASSWORD FUNCTIONS                        -
	# -------------------------------------------------
	def getPcpatchPassword(self, hostId):
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend (attribute opsiPcpatchPassword only)
		host.readFromDirectory(self._ldap, 'opsiPcpatchPassword')
		return host.getAttribute('opsiPcpatchPassword')
	
	def setPcpatchPassword(self, hostId, password):
		host = Object( self.getHostDn(hostId) )
		# Read client ldap-object from Backend
		host.readFromDirectory(self._ldap)
		# Set attribute to new value
		host.setAttribute('opsiPcpatchPassword', [ password ])
		# Write object to ldap
		host.writeToDirectory(self._ldap)
		
	# -------------------------------------------------
	# -     PRODUCT FUNCTIONS                         -
	# -------------------------------------------------
	def createProduct(self, productType, productId, name, productVersion, packageVersion, licenseRequired=0,
			   setupScript="", uninstallScript="", updateScript="", alwaysScript="", onceScript="",
			   priority=0, description="", advice="", productClassNames=(), pxeConfigTemplate='', depotIds=[]):
		""" Creates a new product. """
		
		if not re.search(PRODUCT_ID_REGEX, productId):
			raise BackendBadValueError("Unallowed chars in productId!")
		
		# Create opsiLocalBootProduct or opsiNetBootProduct ldap-object
		product = Object( "cn=%s,%s" % (productId, self._productsContainerDn) )
		
		# Delete if exists
		try:
			product.deleteFromDirectory(self._ldap, recursive = True)
		except:
			pass
		
		if (productType == 'localboot'):
			product.new('opsiLocalBootProduct')
		elif (productType == 'netboot'):
			product.new('opsiNetBootProduct')
		elif (productType == 'server'):
			logger.notice("create server product: nothing to do ...")
			return
		else:
			raise BackendBadValueError("Unknown product type '%s'" % productType)
		
		# Set product attributes
		product.setAttribute('opsiProductName', [ name ])
		
		if licenseRequired:
			product.setAttribute('opsiProductLicenseRequired', [ 'TRUE' ])
		else:
			product.setAttribute('opsiProductLicenseRequired', [ 'FALSE' ])
		product.setAttribute('opsiProductPriority', [ str(priority) ])
		product.setAttribute('opsiProductCreationTimestamp', [ Tools.timestamp() ])
		product.setAttribute('opsiProductVersion', [ str(productVersion) ])
		product.setAttribute('opsiPackageVersion', [ str(packageVersion) ])
		if setupScript:
			product.setAttribute('opsiSetupScript', [ setupScript ])
		if updateScript: 
			product.setAttribute('opsiUpdateScript', [ updateScript ])
		if uninstallScript: 
			product.setAttribute('opsiUninstallScript', [ uninstallScript ])
		if alwaysScript: 
			product.setAttribute('opsiAlwaysScript', [ alwaysScript ])
		if onceScript: 
			product.setAttribute('opsiOnceScript', [ onceScript ])
		if description: 
			product.setAttribute('description', [ description ])
		if advice: 
			product.setAttribute('opsiProductAdvice', [ advice ])
		if productClassNames:
			if ( type(productClassNames) != type(()) and type(productClassNames) != type([]) ):
				productClassNames = [ productClassNames ]
			for productClassName in productClassNames:
				if not productClassName:
					continue
				
				# Try if productClass exists
				productClass = Object( "cn=%s,%s" % ( productClassName, self._productClassesContainerDn ) )
				try:
					productClass.readFromDirectory(self._ldap, 'dn')
				except BackendIOError, e:
					# Product class does not exist => create it
					productClass.new('opsiProductClass')
					productClass.setAttribute('description', productClassName)
					productClass.writeToDirectory(self._ldap)
				product.addAttributeValue('opsiProductClassProvided', productClass.getDn())
		if pxeConfigTemplate and (productType == 'netboot'):
			product.setAttribute('opsiPxeConfigTemplate', [ pxeConfigTemplate ])
			
		# Write object to ldap
		product.writeToDirectory(self._ldap)
		
	def deleteProduct(self, productId, depotIds=[]):
		# TODO: delete all references ???
		
		self.deleteProductPropertyDefinitions(productId)
		
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Search product dependencies
		try:
			search = ObjectSearch(	self._ldap, 
						self._productDependenciesContainerDn, 
						filter='(&(objectClass=opsiProductDependency)(opsiProductReference=%s))' % product.getDn())
			
			for dependency in search.getObjects():
				dependency.readFromDirectory(self._ldap)
				self.deleteProductDependency(
					productId		= product.getCn(), 
					action			= dependency.getAttribute('opsiProductAction'),
					requiredProductId	= Object( dependency.getAttribute('opsiRequiredProductReference') ).getCn(),
					requirementType		= dependency.getAttribute('opsiRequirementType', '') )
		
		except BackendMissingDataError,e :
			# no product dependencies found
			logger.debug("No product dependencies found for product '%s', nothing deleted: %s." % (product.getCn(), e))
		
		# Search product class dependencies
		try:
			search = ObjectSearch(	self._ldap, 
						self._productClassDependenciesContainerDn, 
						filter='(&(objectClass=opsiProductClassDependency)(opsiProductReference=%s))' % product.getDn())
			
			for dependency in search.getObjects():
				dependency.readFromDirectory(self._ldap)
				self.deleteProductDependency(
					productId		= product.getCn(), 
					action			= dependency.getAttribute('opsiProductAction'),
					requiredProductClassId	= Object( dependency.getAttribute('opsiRequiredProductClassReference') ).getCn(),
					requirementType		= dependency.getAttribute('opsiRequirementType', '') )
		
		except BackendMissingDataError, e:
			# no product class dependencies found
			logger.debug("No product class dependencies found for product '%s', nothing deleted: %s." % (product.getCn(), e))
		
		
		# Delete product
		product.deleteFromDirectory(self._ldap, recursive = True)
		
	def getProduct_hash(self, productId, depotId=None):
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		product.readFromDirectory(self._ldap)
		
		# Product found => get all attributes
		attributes = product.getAttributeDict()
		if attributes.has_key('opsiProductClassProvided'):
			productClassIds = []
			productClassDns = attributes['opsiProductClassProvided']
			if ( type(productClassDns) != type(()) and type(productClassDns) != type([]) ):
				productClassDns = [productClassDns]
			for productClassDn in productClassDns:
				# Get cn from productClass if exists
				productClass = Object(productClassDn)
				try:
					productClass.readFromDirectory(self._ldap)
				except BackendIOError:
					logger.warning("ProductClass '%s' does not exist" % productClassDn)
					continue
				productClassIds.append(productClass.getAttribute('cn'))
			if productClassIds:
				attributes['opsiProductClassProvided'] = productClassIds
			else:
				del attributes['opsiProductClassProvided']
				
		# Return attributes as hash (dict)
		return {"name":				attributes.get('opsiProductName', ''),
			"description":			attributes.get('description', ''),
			"advice":			attributes.get('opsiProductAdvice', ''),
			"priority":			attributes.get('opsiProductPriority', 0),
			"licenseRequired":		attributes.get('opsiProductLicenseRequired') == 'TRUE',
			"productVersion":		attributes.get('opsiProductVersion', ''),
			"packageVersion":		attributes.get('opsiPackageVersion', ''),
			"creationTimestamp":		attributes.get('opsiProductCreationTimestamp', ''),
			"setupScript":			attributes.get('opsiSetupScript', ''),
			"uninstallScript":		attributes.get('opsiUninstallScript', ''),
			"updateScript":			attributes.get('opsiUpdateScript', ''),
			"onceScript":			attributes.get('opsiOnceScript', ''),
			"alwaysScript":			attributes.get('opsiAlwaysScript', ''),
			"productClassNames":		attributes.get('opsiProductClassProvided'),
			"pxeConfigTemplate":		attributes.get('opsiPxeConfigTemplate', '') }
	
	
	def getProductIds_list(self, productType=None, objectId=None, installationStatus=None):
		productIds = []
		
		objectClass = 'opsiProduct'
		if (productType == 'localboot'):
			objectClass = 'opsiLocalBootProduct'
		if (productType == 'netboot'):
			objectClass = 'opsiNetBootProduct'
		if (productType == 'server'):
			objectClass = 'opsiServerProduct'
		
		if not installationStatus:
			try:
				search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(objectClass=%s)' % objectClass)
				productIds.extend( search.getCns() )
			except BackendMissingDataError, e:
				logger.warning("No products found (objectClass: %s)" % objectClass)
			
			return productIds
		
		# Get host object
		hostDn = self.getHostDn(objectId)
		host = Object(hostDn)
		
		productStates = []
		try:
			productStateSearch = ObjectSearch(	self._ldap, 
						'cn=%s,%s' % (host.getCn(), self._productStatesContainerDn),
						filter='(&(objectClass=opsiProductState)(opsiProductInstallationStatus=%s))' \
							% installationStatus)
			
			productStates = productStateSearch.getObjects()
		except BackendMissingDataError:
			return productIds
		
		for productState in productStates:
			productState.readFromDirectory(self._ldap)
			try:
				if ( productState.getAttribute('opsiProductReference') ):
					# Get product's cn (productId)
					product = Object( productState.getAttribute('opsiProductReference') )
					product.readFromDirectory(self._ldap, 'objectClass')
					logger.debug("Object classes of '%s': %s" \
						% (product.getDn(), product.getObjectClasses()))
					if objectClass == 'opsiProduct' or objectClass in product.getObjectClasses():
						productIds.append( product.getCn() )
			except (BackendMissingDataError, BackendIOError):
				continue
		return productIds
	
	
	def getProductInstallationStatus_hash(self, productId, objectId):
		# Search product ldap-object
		productSearch = ObjectSearch(	self._ldap, 
						self._productsContainerDn, 
						filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = productSearch.getObject()
		
		status = { 
			'productId':		productId,
			'installationStatus':	'not_installed',
			'productVersion':	'',
			'packageVersion':	'',
			'lastStateChange':	'',
			'deploymentTimestamp':	'' }
		
		# Create host ldap-object
		hostDn = self.getHostDn(objectId)
		host = Object(hostDn)
		
		# Create productState object
		productState = Object('cn=%s,cn=%s,%s' \
					% (product.getCn(), host.getCn(), self._productStatesContainerDn))
		try:
			productState.readFromDirectory(self._ldap)
		except:
			return status
		
		# Get all attributes
		attributes = productState.getAttributeDict()
		
		status['installationStatus'] = attributes.get('opsiProductInstallationStatus', 'not_installed')
		status['productVersion'] = 	attributes.get('opsiProductVersion')
		status['packageVersion'] = 	attributes.get('opsiPackageVersion')
		status['lastStateChange'] = 	attributes.get('lastStateChange')
		status['deploymentTimestamp'] = attributes.get('opsiProductDeploymentTimestamp')
		
		return status
	
	def getProductInstallationStatus_listOfHashes(self, objectId):
		
		#### SPEED: 100% #####
		installationStatus = []
		
		# Create host ldap-object
		hostDn = self.getHostDn(objectId)
		host = Object(hostDn)
		
		# Get installationStatus of every known local-boot product
		for productId in self.getProductIds_list( None, self.getServerId(objectId), 'installed' ):
			try:
				productState = Object('cn=%s,cn=%s,%s' \
					% (productId, host.getCn(), self._productStatesContainerDn))
				
				productState.readFromDirectory(self._ldap)
				
				# Get all attributes
				attributes = productState.getAttributeDict()
				
				installationStatus.append( 
					{ 'productId':			productId,
					  'installationStatus': 	attributes.get('opsiProductInstallationStatus', 'not_installed'),
					  'productVersion':		attributes.get('opsiProductVersion'),
					  'packageVersion':		attributes.get('opsiPackageVersion'),
					  'lastStateChange':		attributes.get('lastStateChange'),
					  'deploymentTimestamp':	attributes.get('opsiProductDeploymentTimestamp')
					} )
			except Exception, e:
				# Status not found => not_installed
				installationStatus.append( { 	'productId': productId, 
								'installationStatus': 'not_installed',
								'productVersion': None,
								'packageVersion': None,
								'lastStateChange': None,
								'deploymentTimestamp': None } )
		
		return installationStatus
		
		
		#### SPEED: ~ 25% #####
		#installationStatus = []
		## Get installationStatus of every known installable product
		#for productId in self.getInstallableProductIds_list(objectId):
		#	try:
		#		status = self.getProductInstallationStatus_hash(productId, objectId)
		#		installationStatus.append( { 'productId': productId, 'installationStatus': status['installationStatus'] } )
		#	except Exception, e:
		#		# Status not found => not_installed
		#		installationStatus.append( { 'productId': productId, 'installationStatus': 'not_installed'} )
		#return installationStatus
	
	def setProductState(self, productId, objectId, installationStatus="", actionRequest="", productVersion="", packageVersion="", lastStateChange="", licenseKey=""):
		productId = productId.lower()
		
		if not installationStatus:
			installationStatus = 'undefined'
		if not installationStatus in getPossibleProductInstallationStatus():
			raise BackendBadValueError("InstallationStatus has unsupported value '%s'" %  installationStatus )
		
		if not actionRequest:
			actionRequest = 'undefined'
		if not actionRequest in getPossibleProductActions():
			raise BackendBadValueError("ActionRequest has unsupported value '%s'" % actionRequest)
		
		if not lastStateChange:
			lastStateChange = Tools.timestamp()
		
		product = None
		try:
			# Get product's dn and version
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
			product.readFromDirectory(self._ldap, 'opsiProductVersion', 'opsiPackageVersion')
		except Exception, e:
			raise BackendBadValueError("Product '%s' does not exist: %s" % (productId, e))
		
		# Read host object from backend
		hostDn = self.getHostDn(objectId)
		host = Object(hostDn)
		host.readFromDirectory(self._ldap)
		
		# Create productState container for selected host
		self.createOrganizationalRole( 'cn=%s,%s' % (host.getCn(), self._productStatesContainerDn) )
		
		# Create or load productState object and set the needed attributes
		productState = Object( 'cn=%s,cn=%s,%s' % (product.getCn(), host.getCn(), self._productStatesContainerDn) )
		try:
			productState.readFromDirectory(self._ldap)
		except BackendIOError, e:
			productState.new('opsiProductState')
		
		currentInstallationStatus = productState.getAttribute('opsiProductInstallationStatus', '')
		currentActionRequest = productState.getAttribute('opsiProductActionRequestForced', '')
		
		if not productVersion:
			productVersion = ''
			if   (installationStatus == 'installed') or (installationStatus == 'uninstalled') or \
			     (installationStatus == 'installing') or (installationStatus == 'failed'):
				     productVersion = product.getAttribute('opsiProductVersion', '')
			elif (installationStatus == 'undefined') and \
			     ( (currentInstallationStatus == 'installed') or (currentInstallationStatus == 'uninstalled') or \
			       (currentInstallationStatus == 'installing') or (currentInstallationStatus == 'failed') ):
				     productVersion = productState.getAttribute('opsiProductVersion', '')
		
		if not packageVersion:
			packageVersion = ''
			if   (installationStatus == 'installed') or (installationStatus == 'uninstalled') or \
			     (installationStatus == 'installing') or (installationStatus == 'failed'):
				     packageVersion = product.getAttribute('opsiPackageVersion', '')
			elif (installationStatus == 'undefined') and \
			     ( (currentInstallationStatus == 'installed') or (currentInstallationStatus == 'uninstalled') or \
			       (currentInstallationStatus == 'installing') or (currentInstallationStatus == 'failed') ):
				     packageVersion = productState.getAttribute('opsiPackageVersion', '')
		
		if (installationStatus == 'undefined') and currentInstallationStatus:
			installationStatus = currentInstallationStatus
		
		if (actionRequest == 'undefined') and currentActionRequest:
			actionRequest = currentActionRequest
		
		logger.info("Setting product installation status '%s', product action request '%s' for product '%s'" \
					% (installationStatus, actionRequest, productId))
		
		if (installationStatus != 'undefined') or not productState.getAttribute('opsiProductInstallationStatus', False):
			productState.setAttribute( 'opsiProductInstallationStatus', [ installationStatus ] )
		
		if (actionRequest == 'undefined') or actionRequest.endswith('by_policy'):
			# Do not store, because this would overwrite actionRequests resulting from productDeploymentPolicies
			productState.setAttribute( 'opsiProductActionRequestForced', [  ] )
		else:
			productState.setAttribute( 'opsiProductActionRequestForced', [ actionRequest ] )
		
		productState.setAttribute( 'opsiHostReference', 	[ host.getDn() ] )
		productState.setAttribute( 'opsiProductReference', 	[ product.getDn() ] )
		productState.setAttribute( 'lastStateChange', 		[ lastStateChange ] )
		
		logger.info("Setting product version '%s', package version '%s' for product '%s'" \
					% (productVersion, packageVersion, productId))
		
		productState.setAttribute( 'opsiProductVersion', 	[ productVersion ] )
		productState.setAttribute( 'opsiPackageVersion', 	[ packageVersion ] )
		
		productState.writeToDirectory(self._ldap)
		
		return
		###############################################################
		# Get licenseReference by licenseKey
		#licenseReference = None
		#if licenseKey:
		#	search = ObjectSearch(self._ldap, "cn=%s,%s" % (product.getCn(), self._productLicensesContainerDn), 
		#				filter='(&(objectClass=opsiProductLicense)(licenseKey=%s))' % licenseKey)
		#	licenseReference = search.getDn()
		#
		## Get deploymentPolicy timestamp
		#deploymentTimestamp = None
		#deploymentPolicy = None
		#if policyId:
		#	deploymentPolicy = Object(deploymentPolicyDn)
		#	deploymentPolicy.readFromDirectory(self._ldap, 'opsiProductDeploymentTimestamp')
		#	deploymentTimestamp = deploymentPolicy.getAttribute('opsiProductDeploymentTimestamp')
		
		## Search for actionRequests resulting from policies
		#if actionRequest:
		#	policyActionRequest = None
		#	try:
		#		policySearch = PolicySearch(	self._ldap, host.getDn(),
		#					policyContainer = self._productDeploymentPoliciesContainerDn,
		#					policyFilter = '(&(objectClass=opsiPolicyProductDeployment)(opsiProductReference=%s))' % product.getDn(),
		#					independenceAttribute = 'cn',
		#					policyReferenceObjectClass = self._policyReferenceObjectClass,
		#					policyReferenceAttributeName = self._policyReferenceAttributeName )
		#		
		#		policyActionRequest = self._getProductActionRequestFromPolicy(policySearch.getObject(), host.getDn())
		#	
		#	except BackendMissingDataError, e:
		#		# No deployment policy exists for host and product
		#		pass
		#	
		#	if (policyActionRequest and policyActionRequest == actionRequest):
		#		# ActionRequest matches action resulting from policy => not forcing an actionRequest !
		#		logger.info("Will not force actionRequest '%s', policy produces the same actionRequest." % actionRequest)
		#		actionRequest = ''
		#
		#if installationStatus in ['not_installed', 'uninstalled']:
		#	logger.info("License key assignement for host '%s' and product '%s' removed" \
		#							% (objectId, productId) )
		#	productState.setAttribute( 'licenseReference', [ ] )
		#elif licenseReference:
		#	productState.setAttribute( 'licenseReference', [ licenseReference ] )
		#
		#if deploymentPolicy:
		#	productState.setAttribute( 'opsiProductDeploymentPolicyReference', [ deploymentPolicy.getDn() ] )
		#if deploymentTimestamp:
		#	productState.setAttribute( 'opsiProductDeploymentTimestamp', [ deploymentTimestamp ] )	
		#
		#productState.writeToDirectory(self._ldap)
		
	def setProductInstallationStatus(self, productId, objectId, installationStatus, policyId="", licenseKey=""):
		self.setProductState(productId, objectId, installationStatus = installationStatus, licenseKey = licenseKey)
	
	def getPossibleProductActions_list(self, productId=None, depotId=None):
		
		if not productId:
			return POSSIBLE_PRODUCT_ACTIONS
		
		actions = ['none', 'by_policy']
		# Get product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Read needed product object values from ldap
		product.readFromDirectory(self._ldap, 'opsiSetupScript', 'opsiUninstallScript', 'opsiUpdateScript', 'opsiOnceScript', 'opsiAlwaysScript')
		
		# Get all attributes
		attributes = product.getAttributeDict()
		
		# If correspondent script exists actin is possible
		if attributes.has_key('opsiSetupScript'):	actions.append('setup')
		if attributes.has_key('opsiUninstallScript'):	actions.append('uninstall')
		if attributes.has_key('opsiUpdateScript'):	actions.append('update')
		if attributes.has_key('opsiOnceScript'):	actions.append('once')
		if attributes.has_key('opsiAlwaysScript'):	actions.append('always')
		
		return actions
	
	
	def getPossibleProductActions_hash(self, depotId=None):
		actions = {}
		# Get product object
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(objectClass=opsiProduct)')
		except Exception, e:
			logger.warning("No products found: %s" % e)
			return actions
		
		for product in search.getObjects():
			# Read needed product object values from ldap
			product.readFromDirectory(self._ldap, 'opsiSetupScript', 'opsiUninstallScript', 'opsiUpdateScript', 'opsiOnceScript', 'opsiAlwaysScript')
			
			actions[product.getCn()] = ['none', 'by_policy']
			
			# Get all attributes
			attributes = product.getAttributeDict()
			
			# If correspondent script exists actin is possible
			if attributes.has_key('opsiSetupScript'):	actions[product.getCn()].append('setup')
			if attributes.has_key('opsiUninstallScript'):	actions[product.getCn()].append('uninstall')
			if attributes.has_key('opsiUpdateScript'):	actions[product.getCn()].append('update')
			if attributes.has_key('opsiOnceScript'):	actions[product.getCn()].append('once')
			if attributes.has_key('opsiAlwaysScript'):	actions[product.getCn()].append('always')
		
		return actions
	
	def getProductActionRequests_listOfHashes(self, clientId):
		
		# Create client ldap-object
		client = Object( self.getHostDn(clientId) )
		
		# Search productStates and productDeployment policies for client
		policies = []
		productStates = []
		try:
			policySearch = PolicySearch(	self._ldap, client.getDn(),
							policyContainer = self._productDeploymentPoliciesContainerDn,
							policyFilter = '(objectClass=opsiPolicyProductDeployment)',
							independenceAttribute = 'opsiProductReference',
							policyReferenceObjectClass = self._policyReferenceObjectClass,
							policyReferenceAttributeName = self._policyReferenceAttributeName )
			policies = policySearch.getObjects()
		except BackendMissingDataError, e:
			logger.warning(e)
		
		try:
			productStateSearch = ObjectSearch(	self._ldap, 
						'cn=%s,%s' % (client.getCn(), self._productStatesContainerDn), 
						filter='objectClass=opsiProductState')
		
			productStates = productStateSearch.getObjects()
		except BackendMissingDataError, e:
			logger.warning(e)
		
		actionRequests = []
		forcedProductDns = []
		for productState in productStates:
			actionRequest = ''
			try:
				# Read productState object from ldap
				productState.readFromDirectory(self._ldap)
				actionRequest = productState.getAttribute('opsiProductActionRequestForced')
			except BackendMissingDataError:
				continue
			
			if (actionRequest == 'undefined'):
				continue
			
			# An actionRequest is forced
			product = Object( productState.getAttribute('opsiProductReference') )
			forcedProductDns.append(product.getDn())
			actionRequests.append( { 'productId': 		product.getCn(), 
						  'actionRequest': 	actionRequest, 
						  'policyId':		'' } )
		
		
		for policy in policies:
			# Reading from backend not needed for policy, policySearch returns initialized objects
			product = Object( policy.getAttribute('opsiProductReference') )
			if product.getDn() in forcedProductDns:
				# An action was forced => policy is ineffectual
				continue
			# Get action request resulting from policy
			actionRequest = self._getProductActionRequestFromPolicy(policy, client.getDn())
			if actionRequest:
				actionRequests.append( { 'productId': 		product.getCn(), 
							  'actionRequest': 	actionRequest, 
							  'policyId':		policy.getDn() } )
			
		return actionRequests
		
	
	def getDefaultNetBootProductId(self, clientId):
		# Get all installable net-boot product ids
		netBootProductIds = self.getProductIds_list('netboot', self.getServerId(clientId), 'installed')
		for (key, value) in self.getGeneralConfig_hash(clientId).items():
			if (key.lower() == 'os'):
				return value
	
	def setProductActionRequest(self, productId, clientId, actionRequest):
		self.setProductState(productId, clientId, actionRequest = actionRequest)
	
	def unsetProductActionRequest(self, productId, clientId):
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Create client object
		client = Object( self.getHostDn(clientId) )
		
		# Create or load productState object and set the needed attributes
		productState = Object( 'cn=%s,cn=%s,%s' % (product.getCn(), client.getCn(), self._productStatesContainerDn) )
		try:
			productState.readFromDirectory(self._ldap)
		except BackendIOError, e:
			# No such productState => nothing to unset
			return
		
		# Delete attribute opsiProductActionRequestForced
		productState.setAttribute('opsiProductActionRequestForced', [ ])
		productState.setAttribute( 'lastStateChange', [ Tools.timestamp() ] )
		
		# Write object to ldap
		productState.writeToDirectory(self._ldap)
	
	def _getProductStates_hash(self, objectIds = [], productType = None):
		if not objectIds:
			objectIds = self.getClientIds_list()
		elif ( type(objectIds) != type([]) and type(objectIds) != type(()) ):
			objectIds = [ objectIds ]
		
		objectClass = 'opsiProduct'
		if (productType == 'localboot'):
			objectClass = 'opsiLocalBootProduct'
		if (productType == 'netboot'):
			objectClass = 'opsiNetBootProduct'
		if (productType == 'server'):
			objectClass = 'opsiServerProduct'
		
		result = {}
		defaultStates = {}
		productIds = []
		productDns = []
		
				
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(objectClass=%s)' % objectClass)
			productIds = search.getCns()
			productDns = search.getDns()
		except BackendMissingDataError, e:
			logger.warning("No products found (objectClass: %s)" % objectClass)
		
		for productId in productIds:
			defaultStates[productId] = { 
				'productId':		productId,
				'installationStatus': 	'not_installed',
				'actionRequest': 	'undefined',
				'productVersion':	'',
				'packageVersion':	'',
				'lastStateChange': 	'',
				'deploymentTimestamp':	'' }
		
		for objectId in objectIds:
			# Copy defaults
			clientStates = pycopy.deepcopy(defaultStates)
			
			# Create client ldap-object
			client = Object( self.getHostDn(objectId) )
			
			# Search productStates and productDeployment policies for client
			policies = []
			productStates = []
			try:
				policySearch = PolicySearch(	self._ldap, client.getDn(),
								policyContainer = self._productDeploymentPoliciesContainerDn,
								policyFilter = '(objectClass=opsiPolicyProductDeployment)',
								independenceAttribute = 'opsiProductReference',
								policyReferenceObjectClass = self._policyReferenceObjectClass,
								policyReferenceAttributeName = self._policyReferenceAttributeName )
				policies = policySearch.getObjects()
			except BackendMissingDataError, e:
				logger.warning(e)
			
			try:
				productStateSearch = ObjectSearch(	self._ldap, 
							'cn=%s,%s' % (client.getCn(), self._productStatesContainerDn), 
							filter='objectClass=opsiProductState')
			
				productStates = productStateSearch.getObjects()
			except BackendMissingDataError, e:
				logger.warning(e)
			
			for productState in productStates:
				# Read productState object from ldap
				productState.readFromDirectory(self._ldap)
				
				logger.debug("Product state: %s" % productState.getAttributeDict())
				
				if productState.getAttribute('opsiProductReference') not in productDns:
					continue
				
				product = Object( productState.getAttribute('opsiProductReference') )
				productId = product.getCn()
				
				clientStates[productId]['actionRequest'] = productState.getAttribute('opsiProductActionRequestForced', 'undefined')
				clientStates[productId]['installationStatus'] = productState.getAttribute('opsiProductInstallationStatus', 'undefined')
				clientStates[productId]['productVersion'] = productState.getAttribute('opsiProductVersion', '')
				clientStates[productId]['packageVersion'] = productState.getAttribute('opsiPackageVersion', '')
				clientStates[productId]['lastStateChange'] = productState.getAttribute('lastStateChange', '')
				clientStates[productId]['deploymentTimestamp'] = productState.getAttribute('opsiProductDeploymentTimestamp', '')
				
			for policy in policies:
				# Reading from backend not needed for policy, policySearch returns initialized objects
				product = Object( policy.getAttribute('opsiProductReference') )
				productId = product.getCn()
				
				logger.info("Processing deployment policy for product '%s', client '%s', current state: '%s'" \
							% (product.getCn(), client.getCn(), clientStates.get(productId)))
				
				if product.getDn() not in productDns:
					logger.warning("Product '%s' not available" % productId)
					continue
				elif (clientStates.get(product.getCn()).get('actionRequest', 'undefined') not in ['undefined', 'none_by_policy']):
					logger.info("Client state '%s' not undefined or none_by_policy" \
							% clientStates.get(productId).get('actionRequest', 'undefined'))
					continue
				# Get action request resulting from policy
				logger.info("Getting action request resulting from policy '%s'" % policy.getDn())
				clientStates[productId]['actionRequest'] = self._getProductActionRequestFromPolicy(policy, client.getDn())
			
			result[objectId] = []
			for state in clientStates.values():
				result[objectId].append(pycopy.deepcopy(state))
		
		return result
		
	def getNetBootProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds, 'netboot')
		
	def getLocalBootProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds, 'localboot')
		
	def getProductStates_hash(self, objectIds = []):
		return self._getProductStates_hash(objectIds)
	
	def getProductPropertyDefinitions_hash(self, depotId=None):
		definitions = {}
		
		# Search product property definitions
		try:
			search = ObjectSearch(	self._ldap, 
						self._productsContainerDn,
						filter='objectClass=opsiProductPropertyDefinition')
		except BackendMissingDataError:
			logger.info("No ProductPropertyDefinitions found")
			return definitions
		
		for propertyDefinition in search.getObjects():
			propertyDefinition.readFromDirectory(self._ldap)
			productId = propertyDefinition.getParent().getParent().getCn()
			
			definition = {	"name":	
						propertyDefinition.getAttribute("opsiProductPropertyName").lower(),
					"description":	
						propertyDefinition.getAttribute("description", ""),
					"default":	
						propertyDefinition.getAttribute("opsiProductPropertyDefaultValue", None),
					"values":
						propertyDefinition.getAttribute("opsiProductPropertyPossibleValue", [], valuesAsList=True),
				}
			
			if not definitions.has_key(productId):
				definitions[productId] = []
			
			definitions[productId].append(definition)
		
		return definitions
	
	def getProductPropertyDefinitions_listOfHashes(self, productId, depotId=None):
		definitions = []
		
		# Search product property definition
		try:
			search = ObjectSearch(	self._ldap, 
						"cn=productPropertyDefinitions,cn=%s,%s" % (productId, self._productsContainerDn),
						filter='objectClass=opsiProductPropertyDefinition')
		except BackendMissingDataError:
			logger.info("No ProductPropertyDefinitions found for product '%s'" % productId)
			return definitions
		
		for propertyDefinition in search.getObjects():
			propertyDefinition.readFromDirectory(self._ldap)
			definitions.append(
				{	"name":	
						propertyDefinition.getAttribute("opsiProductPropertyName").lower(),
					"description":	
						propertyDefinition.getAttribute("description", ""),
					"default":	
						propertyDefinition.getAttribute("opsiProductPropertyDefaultValue", None),
					"values":
						propertyDefinition.getAttribute("opsiProductPropertyPossibleValue", [], valuesAsList=True),
				}
			)
		
		return definitions
	
	def deleteProductPropertyDefinition(self, productId, name, depotIds=[]):
		productId = productId.lower()
		name = name.lower()
		
		# Search product object
		try:
			search = ObjectSearch(	self._ldap, 
						"cn=productPropertyDefinitions,cn=%s,%s" % (productId, self._productsContainerDn),
						filter='(&(objectClass=opsiProductPropertyDefinition)(cn=%s))' % name)
		except BackendMissingDataError, e:
			logger.warning("ProductPropertyDefinition '%s' not found for product '%s': %s" % (name, productId, e))
			return
		
		search.getObject().deleteFromDirectory(self._ldap)
		
		# Delete productPropertyDefinitions container if empty
		self.deleteChildlessObject("cn=productPropertyDefinitions,cn=%s,%s" % (productId, self._productsContainerDn))
		
	
	def deleteProductPropertyDefinitions(self, productId, depotIds=[]):
		# Search product object
		try:
			search = ObjectSearch(	self._ldap, 
						"cn=productPropertyDefinitions,cn=%s,%s" % (productId, self._productsContainerDn),
						filter='objectClass=opsiProductPropertyDefinition')
		except BackendMissingDataError, e:
			logger.warning("No ProductPropertyDefinitions found for product '%s': %s" % (productId, e))
			return
		
		for propertyDefinition in search.getObjects():
			propertyDefinition.deleteFromDirectory(self._ldap)
		
		container = Object("cn=productPropertyDefinitions,cn=%s,%s" % (productId, self._productsContainerDn))
		container.deleteFromDirectory(self._ldap)
		
	def createProductPropertyDefinition(self, productId, name, description=None, defaultValue=None, possibleValues=[], depotIds=[]):
		productId = productId.lower()
		name = name.lower()
		
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Create productPropertyDefinitions container beneath product object
		containerDn = "cn=productPropertyDefinitions,%s" % product.getDn()
		self.createOrganizationalRole(containerDn)
		
		# Create ProductPropertyDefinition object
		propertyDefinition = Object("cn=%s,%s" % (name, containerDn))
		
		# Delete ProductPropertyDefinition from ldap if exists
		try:
			propertyDefinition.deleteFromDirectory(self._ldap)
		except:
			pass
		
		propertyDefinition.new('opsiProductPropertyDefinition')
		propertyDefinition.setAttribute('opsiProductReference', [ product.getDn() ])
		propertyDefinition.setAttribute('opsiProductPropertyName', [ name ])
		if description:
			propertyDefinition.setAttribute('description', [ description ])
		if defaultValue:
			propertyDefinition.setAttribute('opsiProductPropertyDefaultValue', [ defaultValue ])
		if  possibleValues:
			propertyDefinition.setAttribute('opsiProductPropertyPossibleValue', possibleValues)
		
		propertyDefinition.writeToDirectory(self._ldap)
	
	def getProductProperties_hash(self, productId, objectId = None):
		productId = productId.lower()
		if not objectId:
			objectId = self._defaultDomain
		
		# Search product object
		properties = {}
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except BackendMissingDataError, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (productId, e))
			return properties
		
		try:
			# Search policy
			policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyContainer = "cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						policyFilter = '(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn(),
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
			
			for (key, value) in policySearch.getResult().items():
				if (key == 'opsiProductReference'):
					continue
				#if (key == 'opsiProductPropertyName'):
				#	properties[key] = value['value'].lower()
				#	continue
				properties[key] = value['value']
				
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
			return properties
		
		return properties
	
	
	def setProductProperties(self, productId, properties, objectId = None):
		if not objectId or (objectId == self.getServerId()):
			# ObjectId not specified => set for whole domain
			objectId = self._defaultDomain
		return self.createProductPropertyPolicy(productId, self.getObjectDn(objectId), properties)
	
	def deleteProductProperty(self, productId, property, objectId = None):
		productId = productId.lower()
		property = property.lower()
		if not objectId or (objectId == self.getServerId()):
			# ObjectId not specified => delete from all policies
			objectId = self._defaultDomain
		
		# Search product object
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except BackendMissingDataError, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (productId, e))
			return properties
		
		try:
			policySearch = None
			if (objectId == self._defaultDomain):
				policySearch = ObjectSearch(
						self._ldap,
						"cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						filter='(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn() )
			
			else:
				policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyContainer = "cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						policyFilter = '(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn(),
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
						
			for policy in policySearch.getObjects():
				policy.readFromDirectory(self._ldap)
				opsiKeyValuePairs = []
				try:
					opsiKeyValuePairs = policy.getAttribute('opsiKeyValuePair', valuesAsList=True)
				except BackendMissingDataError:
					continue
				logger.debug("Current properties in policy: %s" % opsiKeyValuePairs)
				newOpsiKeyValuePairs = []
				for opsiKeyValuePair in opsiKeyValuePairs:
					if ( opsiKeyValuePair.split('=')[0].strip().lower() == property ):
						continue
					newOpsiKeyValuePairs.append(opsiKeyValuePair)
				logger.debug("New properties in policy: %s" % newOpsiKeyValuePairs)
				if newOpsiKeyValuePairs:
					policy.setAttribute('opsiKeyValuePair', newOpsiKeyValuePairs)
					policy.writeToDirectory(self._ldap)
				else:
					self.deletePolicy(policy.getDn())
					self.deleteChildlessObject(policy.getParent().getDn())
				
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
		
	
	def deleteProductProperties(self, productId, objectId = None):
		productId = productId.lower()
		if not objectId or (objectId == self.getServerId()):
			# ObjectId not specified => delete from all policies
			objectId = self._defaultDomain
		
		# Search product object
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except BackendMissingDataError, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (productId, e))
			return properties
		
		try:
			policySearch = None
			if (objectId == self._defaultDomain):
				policySearch = ObjectSearch(
						self._ldap,
						"cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						filter='(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn() )
			
			else:
				policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyContainer = "cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						policyFilter = '(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn(),
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
						
			for policyDn in policySearch.getDns():
				self.deletePolicy(policyDn)
			
			self.deleteChildlessObject("cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn))
			
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
	
	def getProductDependencies_listOfHashes(self, productId = None, depotId=None):
		
		productSearch = None
		
		# Search product objects
		if productId:
			productSearch = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		else:
			productSearch = ObjectSearch(self._ldap, self._productsContainerDn, filter='(objectClass=opsiProduct)')
		
		dependencyList = []
		
		for product in productSearch.getObjects():
			# Search for product(class) dependencies
			dependencies = []
			try:
				dependencySearch = ObjectSearch(self._ldap, "cn=%s,%s" % (product.getCn(), self._productDependenciesContainerDn),
							filter='(objectClass=opsiProductDependency)')
				dependencies.extend( dependencySearch.getObjects() )
			except BackendMissingDataError, e:
				# No product dependencies found
				logger.info("No product dependencies found for product '%s'" % product.getCn())
			
			try:
				dependencySearch = ObjectSearch(self._ldap, "cn=%s,%s" % (product.getCn(), self._productClassDependenciesContainerDn),
							filter='(objectClass=opsiProductClassDependency)')
				dependencies.extend( dependencySearch.getObjects() )
			
			except BackendMissingDataError, e:
				# No productclass dependencies found
				logger.info("No productclass dependencies found for product '%s'" % product.getCn())
			
			for dependency in dependencies:
				# Read dependency object from ldap
				dependency.readFromDirectory(self._ldap)
				try:
					action = dependency.getAttribute('opsiActionRequired')
				except BackendMissingDataError, e:
					action = ''
				try:
					installationStatus = dependency.getAttribute('opsiInstallationStatusRequired')
				except BackendMissingDataError, e:
					installationStatus = ''
				try:
					requirementType = dependency.getAttribute('opsiRequirementType')
				except BackendMissingDataError, e:
					requirementType = ''
				
				dep = { 'productId': product.getCn(),
					'action': dependency.getAttribute('opsiProductAction'),
					'requiredAction': action,
					'requiredInstallationStatus': installationStatus,
					'requirementType': requirementType }
				
				if ( 'opsiProductClassDependency' in dependency.getObjectClasses() ):
					# Dependency is a productclass dependency
					p = Object( dependency.getAttribute('opsiRequiredProductClassReference') )
					dep['requiredProductClassId'] = p.getCn()
				else:
					# Dependency is a product dependency
					p = Object( dependency.getAttribute('opsiRequiredProductReference') )
					dep['requiredProductId'] = p.getCn()
				
				logger.debug("Adding dependency: %s" % dep)
				dependencyList.append( dep )
			
		# Return all dependencies as a list of hashes (dicts)
		return dependencyList
	
	def createProductDependency(self, productId, action, requiredProductId="", requiredProductClassId="", requiredAction="", requiredInstallationStatus="", requirementType="", depotIds=[]):
		
		try:
			pd = ProductDependency(productId, action, requiredProductId, requiredProductClassId, 
						requiredAction, requiredInstallationStatus, requirementType)
		except Exception, e:
			raise BackendBadValueError(e)
		
		# Create product object
		productSearch = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % pd.productId)
		product = productSearch.getObject()
		
		requiredProduct = None
		requiredProductClass = None
		containerDn = None
		cn = None
		dn = None
		
		if pd.requiredProductId:
			# Create organizational role
			containerDn = "cn=%s,%s" % (product.getCn(), self._productDependenciesContainerDn)
			self.createOrganizationalRole(containerDn)
			dn = "cn=%s,%s" % (requiredProductId, self._productsContainerDn)
			requiredProduct = Object( dn )
			#requiredProduct.readFromDirectory(self._ldap, 'dn') # Test if exists
			cn = requiredProduct.getCn()
		else:
			# Create organizational role
			containerDn = "cn=%s,%s" % (product.getCn(), self._productClassDependenciesContainerDn)
			self.createOrganizationalRole(containerDn)
			dn = "cn=%s,%s" % (requiredProductClassId, self._productClassesContainerDn)
			requiredProductClass = Object( dn )
			#requiredProductClass.readFromDirectory(self._ldap, 'dn') # Test if exists
			cn = requiredProductClass.getCn()
		
		self.createOrganizationalRole( "cn=%s,%s" % (action, containerDn) )
		
		# Create dependency object
		productDependency = Object("cn=%s,cn=%s,%s" % (cn, action, containerDn))
		
		# Delete dependency from ldap if exists
		try:
			productDependency.deleteFromDirectory(self._ldap)
		except:
			pass
		
		# Set dependency's objectClass
		if requiredProduct:
			productDependency.new('opsiProductDependency')
			productDependency.setAttribute('opsiRequiredProductReference', [ dn ])
		else:
			productDependency.new('opsiProductClassDependency')
			productDependency.setAttribute('opsiRequiredProductClassReference', [ dn ])
		
		# Set dependency's attributes
		productDependency.setAttribute('opsiProductReference', [ product.getDn() ])
		
		productDependency.setAttribute('opsiProductAction', [ pd.action ])
		if requiredAction:
			productDependency.setAttribute('opsiActionRequired', [ pd.requiredAction ])
			productDependency.setAttribute('opsiInstallationStatusRequired', [])
		if requiredInstallationStatus:
			productDependency.setAttribute('opsiActionRequired', [ ])
			productDependency.setAttribute('opsiInstallationStatusRequired', [ pd.requiredInstallationStatus ])
		if requirementType:
			productDependency.setAttribute('opsiRequirementType', [ pd.requirementType ])
		
		# Write dependency to ldap
		productDependency.writeToDirectory(self._ldap)
	
	def deleteProductDependency(self, productId, action="", requiredProductId="", requiredProductClassId="", requirementType="", depotIds=[]):
		if action and not action in getPossibleProductActions():
			raise BackendBadValueError("Action '%s' is not known" % action)
		#if not requiredProductId and not requiredProductClassId:
		#	raise BackendBadValueError("Either a required product or a required productClass must be set")
		if requirementType and requirementType not in getPossibleRequirementTypes():
			raise BackendBadValueError("Requirement type '%s' is not known" % requirementType)
		
		# Create product object
		productSearch = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = productSearch.getObject()
		
		# Search dependency objects
		productDependencies = []
		
		if not action:
			action = "*"
		if not requiredProductId and not requiredProductClassId:
			requiredProductId = "*"
			requiredProductClassId = "*"
		if not requirementType:
			requirementType = "*"
		
		if requiredProductId:
			try:
				search = ObjectSearch(
					self._ldap,
					"cn=%s,%s" % (product.getCn(), self._productDependenciesContainerDn), 
					filter = '(&(&(&(objectClass=opsiProductDependency)(opsiProductAction=%s))(cn=%s))(opsiRequirementType=%s))' \
					% (action, requiredProductId, requirementType) )
				productDependencies.extend(search.getObjects())
			except BackendMissingDataError, e:
				logger.info("No such dependency: %s" % e)
		
		if requiredProductClassId:
			try:
				search = ObjectSearch(
					self._ldap,
					"cn=%s,%s" % (product.getCn(), self._productClassDependenciesContainerDn), 
					filter = '(&(&(&(objectClass=opsiProductClassDependency)(opsiProductAction=%s))(cn=%s))(opsiRequirementType=%s))' \
					% (action, requiredProductClassId, requirementType) )
				productDependencies.extend(search.getObjects())
			except BackendMissingDataError, e:
				logger.info("No such dependency: %s" % e)
			
		
		for productDependency in productDependencies:
			logger.info("Deleting productDependency '%s' of product '%s'" % (productDependency.getDn(), product.getCn()))
			# Delete dependency from ldap
			productDependency.deleteFromDirectory(self._ldap)
			
			# Delete parent object if empty
			parent = productDependency.getParent()
			if self.deleteChildlessObject( parent.getDn() ):
				# Was deleted, delete parent's parent object if empty
				parent = parent.getParent()
				self.deleteChildlessObject( parent.getDn() )
		
		
		
	def createLicenseKey(self, productId, licenseKey):
		# TODO: productLicenses as product child objects in ldap tree???
		
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Create organizational role with same cn as product beneath license container
		self.createOrganizationalRole( "cn=%s,%s" % (product.getCn(), self._productLicensesContainerDn) )
		
		# Create license's cn from licensekey
		licenseCn = licenseKey.replace(':','')
		licenseCn = licenseCn.replace('-','')
		licenseCn = licenseCn.replace(' ','')
		licenseCn = licenseCn.replace('/','')
		licenseCn = licenseCn.replace('\\','')
		
		# Create license object
		productLicense = Object( "cn=%s,cn=%s,%s" % (licenseCn, productId, self._productLicensesContainerDn) )
		productLicense.new('opsiProductLicense')
		
		# Set object attributes
		productLicense.setAttribute('licenseKey', [ licenseKey ])
		productLicense.setAttribute('opsiProductReference', [ product.getDn() ])
		
		# Write object to ldap
		productLicense.writeToDirectory(self._ldap)
	
	
	def getLicenseKey(self, productId, clientId):
		logger.debug("Searching licensekey for host '%s' and product '%s'" % (clientId, productId))
		
		freeLicenses = []
		for license in self.getLicenseKeys_listOfHashes(productId):
			hostId = license.get('hostId', '')
			if not hostId:
				freeLicenses.append(license.get('licenseKey', ''))
			elif (hostId == clientId):
				logger.info("Returning licensekey for product '%s' which is assigned to host '%s'"
						% (productId, clientId))
				return license.get('licenseKey', '')
		
		if (len(freeLicenses) <= 0):
			for (key, value) in self.getProductProperties_hash(productId, clientId).items():
				if (key.lower() == 'productkey'):
					freeLicenses.append(value)
		
		if (len(freeLicenses) > 0):
			logger.debug( "%s free license(s) found for product '%s'" % (len(freeLicenses), productId) )
			return freeLicenses[0]
		
		raise BackendMissingDataError("No more licenses available for product '%s'" % productId)
	
	def getLicenseKeys_listOfHashes(self, productId):
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		result = []
		licenses = {}
		try:
			search = ObjectSearch(self._ldap, "cn=%s,%s" % (product.getCn(), self._productLicensesContainerDn),
				      				filter='(objectClass=opsiProductLicense)')
			
			for license in search.getObjects():
				license.readFromDirectory(self._ldap)
				licenses[license.getDn()] = { "licenseKey": license.getAttribute('licenseKey'), 'hostId': '' }
		
		except BackendMissingDataError, e:
			return result
		
		
		# Search all use licenses (referenced in productStates)
		try:
			productStateSearch = ObjectSearch(
						self._ldap,
						self._productStatesContainerDn,
						filter='(&(objectClass=opsiProductState)(licenseReference=*))')
			
			productStates = productStateSearch.getObjects()
			for productState in productStates:
				
				productState.readFromDirectory(self._ldap, 'licenseReference', 'opsiHostReference')
				hostId = self.getHostId( productState.getAttribute('opsiHostReference') )
				licenseReference = productState.getAttribute('licenseReference')
				
				try:
					search = ObjectSearch(	self._ldap, licenseReference, filter='(objectClass=opsiProductLicense)')
				except BackendMissingDataError, e:
					logger.error("Host '%s' references the not existing license '%s'" % (hostId, licenseReference))
					continue
				
				if licenses.has_key(licenseReference):
					licenses[licenseReference]['hostId'] = hostId
		
		except BackendMissingDataError, e:
			pass
		
		
		for (key, value) in licenses.items():
			result.append(value)
		
		return result
	
	def deleteLicenseKey(self, productId, licenseKey):
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		search = ObjectSearch(self._ldap, "cn=%s,%s" % (product.getCn(), self._productLicensesContainerDn),
			      				filter='(&(objectClass=opsiProductLicense)(licenseKey=%s))' % licenseKey)
		
		search.getObject().deleteFromDirectory(self._ldap)
		
		
		
	def getProductClassIds_list(self):
		search = ObjectSearch(self._ldap, self._productClassesContainerDn,
				      		filter='(objectClass=opsiProductClass)')
		return search.getCns()
	
	# ------------------------------------------------------------------------------------------------------
	# -                                          POLICIES                                                  -
	# ------------------------------------------------------------------------------------------------------
	
	def _getProductActionRequestFromPolicy(self, policy, clientDn):
		''' This function returns an actionRequest resulting from
		    a productDeployment policy. '''
		
		# Search product object
		product = Object( policy.getAttribute('opsiProductReference') )
		product.readFromDirectory(self._ldap, 'opsiProductVersion')
		
		# Create host object
		host = Object( clientDn )
		
		desiredInstallationStatus = None
		# Get desired installation status
		try:
			desiredInstallationStatus = policy.getAttribute('opsiProductInstallationStatus')
		except Exception, e:
			logger.warning(e)
			return None
		
		
		desiredVersion = None
		# Get desired product version
		try:
			desiredVersion = policy.getAttribute('opsiProductVersion')
		except BackendMissingDataError, e:
			logger.warning("%s, product: '%s'" % (e, product.getCn()))
		
		# Get current installation status and installed product version
		currentInstallationStatus = None
		currentVersion = None
		try:
			productState = Object('cn=%s,cn=%s,%s' % \
						(product.getCn(), host.getCn(), self._productStatesContainerDn) )
			productState.readFromDirectory(self._ldap)
			currentInstallationStatus = productState.getAttribute('opsiProductInstallationStatus')
			currentVersion = productState.getAttribute('opsiProductVersion')
		except BackendIOError, e:
			logger.warning("%s, product: '%s'" % (e, product.getCn()))
		
		if not currentInstallationStatus:
			currentInstallationStatus = 'not_installed'
		
		
		actionRequest = 'none_by_policy'
		
		# TODO: unistalled ???
		if ( currentInstallationStatus == 'installed' and 
		     (desiredInstallationStatus == 'not_installed' or desiredInstallationStatus == 'uninstalled') ):
			actionRequest = 'uninstall_by_policy'
		elif ( currentInstallationStatus == desiredInstallationStatus):
			if ( desiredVersion and desiredVersion != currentVersion ):
				# TODO: setup only if new policy created?
				# actionRequest = 'setup_by_policy'
				actionRequest = 'none_by_policy'
		elif ( (currentInstallationStatus == 'uninstalled' or currentInstallationStatus == 'not_installed') and desiredInstallationStatus == 'installed' ):
			actionRequest = 'setup_by_policy'
		else:
			logger.error("No actionRequest is known to get from installationStatus '%s' to installationStatus '%s'" % (currentInstallationStatus, desiredInstallationStatus) )
		
		return actionRequest
	
	
	def assignPolicy(self, containerDn, policyDn):
		""" Assigns a policy to a container """
		
		# Read container object from ldap
		container = Object(containerDn)
		container.readFromDirectory(self_ldap)
		
		# Check if policy exists
		policy = Object(policyDn)
		policy.readFromDirectory(self_ldap, 'dn')
		
		# Add attribute to container
		container.addAttributeValue(self._policyReferenceAttributeName, policyDn)
		
		# Write container to ldap
		container.writeToDirectory(self._ldap)
	
	def deletePolicyReference(self, policyDn, containerDn):
		""" Deletes policy reference from container if exists and
		    deletes policy if there are no more references to the policy """
		
		# Remove policy reference assignment from container
		logger.debug("Deleting reference to policy '%s' from container '%s'" % (policyDn, containerDn))
		container = Object(containerDn)
		container.readFromDirectory(self._ldap)
		container.deleteAttributeValue(self._policyReferenceAttributeName, policyDn)
		container.writeToDirectory(self._ldap)
		
		# Find all object which reference the same policy
		try:
			search = ObjectSearch(	self._ldap, 
						self._baseDn, 
						filter='(%s=%s)' % (self._policyReferenceAttributeName, policyDn) )
		except BackendMissingDataError:
			# No more references found => delete policy
			logger.debug("Policy now unused, deleting policy '%s'" % policyDn)
			self.deletePolicy(policyDn)
	
	def deletePolicy(self, policyDn):
		''' Delete a policy and delete all references to the policy '''
		
		# Find all object which reference the policy to delete
		containers = []
		try:
			search = ObjectSearch(	self._ldap, 
						self._baseDn, 
						filter='(%s=%s)' % (self._policyReferenceAttributeName, policyDn) )
			containers = search.getObjects()
		except BackendMissingDataError:
			logger.info("No object found which references policy '%s'" % policyDn)
		
		# Remove policy reference from container
		for container in containers:
			try:
				container.readFromDirectory(self._ldap)
			except BackendIOError, e:
				continue
			container.deleteAttributeValue(self._policyReferenceAttributeName, policyDn)
			container.writeToDirectory(self._ldap)
		
		# Delete policy if it does not contain objects 
		self.deleteChildlessObject(policyDn)
	
	def deleteHigherPriorityPolicies(self, policyDn, policyFilter, containerDn):
		''' This function deletes all policies of the same type as the
		    policy of the given dn, if they have a higher priorty for the given container. '''
		
		# Search all policies of the same type
		search = ObjectSearch(self._ldap, self._policiesContainerDn, filter = policyFilter)
		policyDns = search.getDns()
		for dn in policyDns:
			if (dn == policyDn):
				continue
			# Delete policy references to the policy assigned to containers beneath containerDn
			search = ObjectSearch(	self._ldap, 
						containerDn, 
						filter='(%s=%s)' % (self._policyReferenceAttributeName, dn) )
			containerDns = search.getDns()
			for containerDn in containerDns:
				self.deletePolicyReference(dn, containerDn)
	
	
	def getPolicyDn(self, objectCn, policyContainerDn):
		''' This function returns a unique, unused dn for a new policy '''
		cns = []
		dn = ''
		try:
			search = ObjectSearch(self._ldap, policyContainerDn, scope=ldap.SCOPE_ONELEVEL)
			cns = search.getCns()
		except BackendMissingDataError:
			pass
		if objectCn not in cns:
			dn = "cn=%s,%s" % (objectCn, policyContainerDn)
		else:
			num = 0
			while objectCn+'_'+str(num) in cns:
				num += 1
			dn = "cn=%s_%s,%s" % (objectCn, num, policyContainerDn)
		logger.debug("Returning unique policy dn '%s'" % dn)
		return dn
	
	# -------------------------------------------------
	# -     GENERALCONFIG POLICIES                    -
	# -------------------------------------------------
	def createGeneralConfigPolicy(self, containerDn, config):
		''' This method creates a general-config-policy for the given container. '''
		
		# Sanity checks
		container = Object(containerDn)
		container.readFromDirectory(self._ldap)
		
		## Search for existing policy
		exists = True
		policy = None
		try:
			search = PolicySearch(
					self._ldap, containerDn, maxLevel = 1,
					policyContainer = self._generalConfigPoliciesContainerDn, 
					policyFilter = '(objectClass=opsiPolicyGeneralConfig)',
					policyReferenceObjectClass = self._policyReferenceObjectClass,
					policyReferenceAttributeName = self._policyReferenceAttributeName )
			policy = search.getObject()
			logger.notice("Deleting existing policy '%s'" % policy.getDn())
			policy.deleteFromDirectory(self._ldap)
		except BackendMissingDataError:
			exists = False
		
		# Create new policy object
		policy = Object( self.getPolicyDn(container.getCn(), self._generalConfigPoliciesContainerDn) )
		policy.new('opsiPolicyGeneralConfig')
		
		for (key, value) in config.items():
			if   (key == 'pcptchBitmap1'):				policy.setAttribute('opsiPcptchBitmap1',		[ value ] )
			elif (key == 'pcptchBitmap2'):				policy.setAttribute('opsiPcptchBitmap2',		[ value ] )
			elif (key == 'pcptchLabel1'):				policy.setAttribute('opsiPcptchLabel1',		[ value ] )
			elif (key == 'pcptchLabel2'):				policy.setAttribute('opsiPcptchLabel2',		[ value ] )
			elif (key == 'secsUntilConnectionTimeOut'):		policy.setAttribute('opsiSecsUntilConnectionTimeOut',	[ value ] )
			elif (key == 'button_stopnetworking'):			policy.setAttribute('opsiButtonStopNetworking', 	[ value ] )
			else:
				policy.addAttributeValue('opsiKeyValuePair', '%s=%s' % (key, value))
		
		# Write policy object to ldap
		policy.writeToDirectory(self._ldap)
		
		if not exists:
			# Add policy reference to conatianer
			container.addAttributeValue(self._policyReferenceAttributeName, policy.getDn())
			container.writeToDirectory(self._ldap)
		
	# -------------------------------------------------
	# -     NETWORKCONFIG POLICIES                    -
	# -------------------------------------------------
	def createNetworkConfigPolicy(self, containerDn, config, serverDn=''):
		''' This method creates a network-config-policy for the given container. '''
		
		# Sanity checks
		container = Object(containerDn)
		container.readFromDirectory(self._ldap)
		server = None
		if serverDn:
			server = Object(serverDn)
			server.readFromDirectory(self._ldap)
		
		# Search for existing policy
		exists = True
		policy = None
		try:
			search = PolicySearch(
					self._ldap, containerDn, maxLevel = 1,
					policyContainer = self._networkConfigPoliciesContainerDn, 
					policyFilter = '(objectClass=opsiPolicyNetworkConfig)',
					policyReferenceObjectClass = self._policyReferenceObjectClass,
					policyReferenceAttributeName = self._policyReferenceAttributeName )
			policy = search.getObject()
			logger.debug("Deleting existing policy '%s'" % policy.getDn())
			policy.deleteFromDirectory(self._ldap)
		except BackendMissingDataError:
			exists = False
		
		# Create new policy object
		policy = Object( self.getPolicyDn(container.getCn(), self._networkConfigPoliciesContainerDn) )
		policy.new('opsiPolicyNetworkConfig')
		
		if server:				policy.setAttribute('opsiServerReference',	[ server.getDn() ] )
		if config.get('configDrive'):		policy.setAttribute('opsiConfigDrive', 	[ config.get('configDrive') ] )
		if config.get('configUrl'):		policy.setAttribute('opsiConfigUrl',		[ config.get('configUrl') ] )
		if config.get('depotDrive'):		policy.setAttribute('opsiDepotDrive', 		[ config.get('depotDrive') ] )
		if config.get('depotUrl'):		policy.setAttribute('opsiDepotUrl',		[ config.get('depotUrl') ] )
		if config.get('utilsDrive'):		policy.setAttribute('opsiUtilsDrive',		[ config.get('utilsDrive') ] )
		if config.get('utilsUrl'):		policy.setAttribute('opsiUtilsUrl',		[ config.get('utilsUrl') ] )
		if config.get('winDomain'):		policy.setAttribute('opsiWinDomain',		[ config.get('winDomain') ] )
		if config.get('nextBootServiceURL'):	policy.setAttribute('opsiNextBootServiceURL',	[ config.get('nextBootServiceURL') ] )
		if config.get('nextBootServerType'):	policy.setAttribute('opsiNextBootServerType',	[ config.get('nextBootServerType') ] )
		
		# Write policy object to ldap
		policy.writeToDirectory(self._ldap)
		
		if not exists:
			# Add policy reference to conatianer
			container.addAttributeValue(self._policyReferenceAttributeName, policy.getDn())
			container.writeToDirectory(self._ldap)
	
	
	
	# -------------------------------------------------
	# -     PRODUCTPROPERTY POLICIES                  -
	# -------------------------------------------------
	# TODO: WRONG METHOD NAME !!!
	def createProductPropertyPolicy(self, productId, containerDn, properties):
		# Sanity checks
		if ( type(properties) != type({}) ):
			raise BackendBadValueError("Type of Properties has to be dict")
		
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Read container object from backend
		container = Object(containerDn)
		container.readFromDirectory(self._ldap)
		
		# Add container for policy if not exists
		self.createOrganizationalRole( 'cn=%s,%s' % (product.getCn(), self._productPropertyPoliciesContainerDn) )
		
		try:
			logger.info("Deleting old policies")
			# Search policies
			policySearch = PolicySearch(
						self._ldap, containerDn, maxLevel=1,
						policyContainer = "cn=%s,%s" % (product.getCn(), self._productPropertyPoliciesContainerDn),
						policyFilter = '(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn(),
						independenceAttribute = 'cn',
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
			
			for policy in policySearch.getObjects():
				logger.debug("Deleting policy '%s'" % policy.getDn())
				container.deleteAttributeValue(self._policyReferenceAttributeName, policy.getDn())
				policy.deleteFromDirectory(self._ldap)
			
		except BackendMissingDataError, e:
			pass
		
		new = False
		# TODO: search by opsiProductPropertyName
		policy = Object( 
			self.getPolicyDn( 
				container.getCn(), 'cn=%s,%s' % (product.getCn(), self._productPropertyPoliciesContainerDn) ) )
		try:
			policy.readFromDirectory(self._ldap)
			logger.debug("Modifying existing policy '%s'" % policy.getDn())
		except:
			new = True
			logger.debug("Creating new policy '%s'" % policy.getDn())
			policy.new('opsiPolicyProductProperty')
		
		policy.setAttribute('opsiProductReference', product.getDn())
		for (key, value) in properties.items():
			policy.addAttributeValue('opsiKeyValuePair', "%s=%s" % (key.lower(), value))			
		policy.writeToDirectory(self._ldap)
		
		if new:
			# Add policy reference to container
			logger.info("Adding policy reference '%s' to container '%s'" % (policy.getDn(), container.getDn()) )
			container.addAttributeValue(self._policyReferenceAttributeName, policy.getDn())
			
		container.writeToDirectory(self._ldap)
		
	
	
	# -------------------------------------------------
	# -     PRODUCTDEPLOYMENT POLICIES                -
	# -------------------------------------------------
	def createProductDeploymentPolicy(self, productId, containerDn, installationStatus, productVersion = '', overwritePolicies=0):
		''' This function creates a product deployment policy for the given container. '''
		
		# Sanity checks
		if not installationStatus in getPossibleProductInstallationStatus():
			raise BackendBadValueError("InstallationStatus '%s' is not known" % installationStatus)
		
		# Read the container object from ldap
		container = Object( containerDn )
		container.readFromDirectory(self._ldap)
		
		# Get product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Create deployment policy container
		self.createOrganizationalRole( 'cn=%s,%s' % (container.getCn(), self._productDeploymentPoliciesContainerDn) )
		
		# Search for existing policy
		exists = True
		policy = None
		try:
			search = PolicySearch(
				self._ldap, containerDn, maxLevel = 1,
				policyContainer = self._productDeploymentPoliciesContainerDn, 
				policyFilter = '(objectClass=opsiPolicyProductDeployment)',
				policyReferenceObjectClass = self._policyReferenceObjectClass,
				policyReferenceAttributeName = self._policyReferenceAttributeName )
			policy = search.getObject()
		except BackendMissingDataError:
			exists = False
		
		if exists:
			logger.debug("Modifying existing policy '%s'" % policy.getDn())
		else:
			# Create new policy object
			policy = Object( 
				self.getPolicyDn(
					container.getCn(),'cn=%s,%s' % (container.getCn(), self._productDeploymentPoliciesContainerDn) ) )
			policy.new('opsiPolicyProductDeployment')
		
		policy.setAttribute( 'opsiProductReference', [ product.getDn() ] )
		policy.setAttribute( 'opsiProductDeploymentTimestamp', [ Tools.timestamp() ] )
		policy.setAttribute( 'opsiProductInstallationStatus', installationStatus )
		if productVersion:
			policy.setAttribute( 'opsiProductVersion', [ productVersion ] )
		if overwritePolicies:
			policy.setAttribute( 'overwrite', [ 'TRUE' ] )
	
		policy.writeToDirectory(self._ldap)
		
		if not exists:
			# Add policy reference to container
			container.addAttributeValue(self._policyReferenceAttributeName, policy.getDn())
			container.writeToDirectory(self._ldap)
			if overwritePolicies:
				self.deleteHigherPriorityPolicies( 	
					policyDn = policy.getDn(),
					policyFilter = '(&(objectClass=opsiPolicyProductDeployment)(opsiProductReference=%s))' % product.getDn(),
					containerDn = containerDn )
	
	
	# -------------------------------------------------
	# -     HELPERS                                   -
	# -------------------------------------------------
	def createOrganizationalRole(self, dn):
		''' This method will add a oprganizational role object
		    with the specified DN, if it does not already exist. '''
		organizationalRole = Object(dn)
		logger.info("Trying to create organizational role '%s'" % dn)
		try:
			organizationalRole.readFromDirectory(self._ldap, 'dn')
			logger.info("Organizational role '%s' already exists" % dn)
		except BackendIOError:	
			organizationalRole.new('organizationalRole', self._policyReferenceObjectClass)
			organizationalRole.writeToDirectory(self._ldap)
			logger.info("Organizational role '%s' created" % dn)
		
		
	def deleteChildlessObject(self, dn):
		''' This method will delete the ldap object specified by DN, 
		    if exists and no child obejcts exist. '''
		try:
			search = ObjectSearch(self._ldap, dn, filter='(objectClass=*)')
		except BackendMissingDataError:
			# Object does not exist
			return False
		if ( len(search.getDns()) > 1):
			# object has childs
			return False
		search.getObject().deleteFromDirectory(self._ldap)
		return True






# ======================================================================================================
# =                                       CLASS OBJECT                                                 =
# ======================================================================================================

class LDAPObject:
	''' This class handles ldap objects. '''
	
	def __init__(self, dn):
		''' Constructor of the Object class. '''
		if not dn:
			raise BackendIOError("Cannot create Object, dn not defined")
		self._dn = dn
		self._old = self._new = {}
		self._existsInBackend = False
	
	def getObjectClasses(self):
		''' Returns object's objectClasses '''
		return self.getAttribute('objectClass', default=[], valuesAsList=True )
	
	def addObjectClass(self, objectClass):
		try:
			self.addAttributeValue('objectClass', objectClass)
		except Exception:
			pass
	
	def getCn(self):
		''' Returns the RDN without type.
		    assuming all subClasses use CN as RDN this method returns the CN '''
		return ( ldap.explode_dn(self._dn, notypes=1) )[0]
	
	def getRdn(self):
		''' Returns the object's RDN. '''
		return ( ldap.explode_dn(self._dn, notypes=0) )[0]
		
	def getDn(self):
		''' Returns the object's DN. '''
		return self._dn
	
	def getContainerCn(self):
		''' Returns the cn of the object's parent (container). '''
		return ( ldap.explode_dn(self._dn, notypes=1) )[1]
	
	def getContainer(self):
		return self.getParent()
	
	def getParent(self):
		parts = ( ldap.explode_dn(self._dn, notypes=0) )[1:]
		if (parts <= 1):
			raise BackendBadValueError("Object '%s' has no parent" % self._dn)
		return Object(','.join(parts))
	
	def new(self, *objectClasses, **attributes):
		''' Creates a new object. '''
		if ( len(objectClasses) <= 0 ):
			raise BackendBadValueError("No objectClasses defined!")
		
		self._new['objectClass'] = objectClasses
		
		self._new['cn'] = [ self.getCn() ]
		
		for attr in attributes:
			self._new[attr] = [ attributes[attr] ]
		
		logger.debug("Created new LDAP-Object: %s" % self._new)
			
	def deleteFromDirectory(self, ldapSession, recursive = False):
		''' Deletes an object from ldap directory. '''
		if recursive:
			objects = []
			try:
				objectSearch = ObjectSearch(ldapSession, self._dn, scope=ldap.SCOPE_ONELEVEL)
				objects = objectSearch.getObjects()
			except:
				pass
			if objects:
				for obj in objects:
					obj.deleteFromDirectory(ldapSession, recursive = True)
		
		return ldapSession.delete(self._dn)
		
	def readFromDirectory(self, ldapSession, *attributes):
		''' If no attributes are given, all attributes are read.
		    If attributes are specified for read speedup,
		    the object can NOT be written back to ldap! '''
		
		self._readAllAttributes = False
		if ( len(attributes) <= 0 ):
			attributes = None
			self._readAllAttributes = True
		
		try:
			result = ldapSession.search(	baseDn     = self._dn,
							scope      = ldap.SCOPE_BASE,
							filter     = "(ObjectClass=*)",
							attributes = attributes )
		except Exception, e:
			raise BackendIOError("Cannot read object (dn: '%s') from ldap: %s" % (self._dn, e))
		
		self._existsInBackend = True
		self._old = result[0][1]
		# Copy the dict
		self._new = self._old.copy()
		# Copy the lists
		for attr in self._new:
			self._new[attr] = list(self._new[attr])

	def writeToDirectory(self, ldapSession):
		''' Writes the object to the ldap tree. '''
		if self._existsInBackend:
			if not self._readAllAttributes:
				raise BackendIOError("Not all attributes have been read from backend - not writing to backend!")
			ldapSession.modifyByModlist(self._dn, self._old, self._new)
		else:
			ldapSession.addByModlist(self._dn, self._new)
	
	def getAttributeDict(self, valuesAsList=False):
		''' Get all attributes of object as dict.
		    All values in self._new are lists by default, 
		    a list of length 0 becomes the value None
		    if there is only one item the item's value is used '''
		ret = {}
		for (key, values) in self._new.items():
			if ( len(values) > 1 or valuesAsList):
				ret[key] = values
			else:
				ret[key] = values[0]
			
			#if (len(value) <= 0):
			#	ret[key] = None
			#if (len(value) == 1):
			#	ret[key] = value[0]
			#else:
			#	ret[key] = value
		return ret
		
	def getAttribute(self, attribute, default='DEFAULT_UNDEFINED', valuesAsList=False ):
		''' Get a specific attribute from object. 
		    Set valuesAsList to a boolean true value to get a list,
		    even if there is only one attribute value. '''
		if not self._new.has_key(attribute):
			if (default != 'DEFAULT_UNDEFINED'):
				return default
			raise BackendMissingDataError("Attribute '%s' does not exist" % attribute)
		values = self._new[attribute]
		if ( len(values) > 1 or valuesAsList):
			return values
		else:
			return values[0]
	
	def setAttribute(self, attribute, value):
		''' Set the attribute to the value given.
		    The value's type should be list. '''
		if ( type(value) != tuple ) and ( type(value) != list ):
			value = [ value ]
		if (value == ['']):
			value = []
		else:
			for i in range(len(value)):
				value[i] = self._encodeValue(value[i])
		logger.debug("Setting attribute '%s' to '%s'" % (attribute, value))
		self._new[attribute] = value
	
	def addAttributeValue(self, attribute, value):
		''' Add a value to an object's attribute. '''
		if not self._new.has_key(attribute):
			self.setAttribute(attribute, [ self._encodeValue(value) ])
			return
		if value in self._new[attribute]:
			#logger.warning("Attribute value '%s' already exists" % value.decode('utf-8', 'ignore'))
			return
		self._new[attribute].append( self._encodeValue(value) )
	
	def deleteAttributeValue(self, attribute, value):
		''' Delete a value from the list of attribute values. '''
		if not self._new.has_key(attribute):
			logger.warning("Failed to delete value '%s' of attribute '%s': does not exists" % (attribute, value))
			return
		for i in range( len(self._new[attribute]) ):
			if (self._new[attribute][i] == value):
				del self._new[attribute][i]
				logger.debug("Value '%s' of attribute '%s' successfuly deleted" % (attribute, value))
				return
	
	def _encodeValue(self, value):
		if not value:
			return value
		if (type(value) != unicode):
			value = value.decode('utf-8', 'replace')
		return value.encode('utf-8')



# ======================================================================================================
# =                                    CLASS OBJECTSEARCH                                              =
# ======================================================================================================

class LDAPObjectSearch:
	''' This class simplifies object searchs. '''
	
	def __init__(self, ldapSession, baseDn='', scope=ldap.SCOPE_SUBTREE, filter='(ObjectClass=*)'):
		''' ObjectSearch constructor. '''
		
		if not baseDn:
			baseDn = ldapSession.baseDn
		
		logger.debug( "Searching object => baseDn: %s, scope: %s, filter: %s" 
				% (baseDn, scope, filter) )
		
		# Storage for matching DNs
		self._dns = []
		self._ldap = ldapSession
		try:
			# Execute search
			result = self._ldap.search( 	baseDn = baseDn, 
							scope = scope, 
							filter = filter, 
							attributes = ['dn'] )
		except ldap.LDAPError, e:
			# Failed
			raise
		
		#if (result == []):
		#	# Nothing found
		#	raise BackendMissingDataError("Cannot find Object in baseDn '%s' matching filter '%s'" 
		#					% (baseDn, filter))
		for r in result:
			logger.debug( "Found dn: %s" % r[0] )
			self._dns.append(r[0])
		
	def getCns(self):
		''' Returns the cns of all objects found. '''
		cns = []
		for dn in self._dns:
			cns.append( ( ldap.explode_dn(dn, notypes=1) )[0] )
		return cns
	
	def getCn(self):
		''' Returns the cn of the first object found. '''
		if ( len(self._dns) >= 1 ):
			return ( ldap.explode_dn(self._dns[0], notypes=1) )[0]
			
	def getDns(self):
		''' Returns the dns of all objects found. '''
		return self._dns
	
	def getDn(self):
		''' Returns the dn of the first object found. '''
		if ( len(self._dns) >= 1 ):
			return self._dns[0]
		
	def getObjects(self):
		''' Returns all objects as Object instances. '''
		if ( len(self._dns) <= 0 ):
			raise BackendMissingDataError("No objects found")
		objects = []
		for dn in self._dns:
			objects.append( Object(dn) )
		return objects
	
	def getObject(self):
		''' Returns the first object found as Object instance. '''
		if ( len(self._dns) <= 0 ):
			raise BackendMissingDataError("No object found")
		return Object(self._dns[0])




# ======================================================================================================
# =                                    CLASS POLICYSEARCH                                              =
# ======================================================================================================

class LDAPPolicySearch:
	def __init__(self, ldapSession, dn, policyContainer = None, policyFilter = None, independenceAttribute = None,
		     maxLevel = 100, policyReferenceObjectClass = 'opsiPolicyReference', policyReferenceAttributeName = 'opsiPolicyReference'):
		''' 
		Search policies for an ldap-object given by dn. Specify a 
		policyContainer to ignore policies outside this container.
		Specify a policyFilter to ignore policies which do not
		match the filter. An independenceAttribute can be given 
		to treat policies of the same type as independent if this 
		attribute differs.
		'''
		
		self.ldapSession = ldapSession
		self.dn = dn
		self.policyContainer = policyContainer
		self.policyFilter = policyFilter
		self.independenceAttribute = independenceAttribute
		self.maxLevel = maxLevel
		self.policyReferenceObjectClass = policyReferenceObjectClass
		self.policyReferenceAttributeName = policyReferenceAttributeName
		self.policyObjectClass = 'univentionPolicy'
		
		return self.search()
		
	def search(self):
		self._policies = []
		self._joinedAttributes = {}
		
		referencePriorities = [[]]
		
		dnPath = self.dn.split(',')
		for i in range( len(dnPath) ):
			dnPath[i] = dnPath[i].strip()
			referencePriorities.append([])
		
		# The closer a policy is connected to an ldap object (policyReference) the higher its priority
		for i in range( len(dnPath)-1 ):
			# Search all policy references, and sort by priority
			
			currentDn = ','.join(dnPath[i:])
			
			if (i > self.maxLevel-1):
				logger.debug( "Omitting dn '%s', maxLevel: %s" % (currentDn, self.maxLevel) )
				continue
			
			logger.debug( "Searching policy references for dn '%s'" % currentDn )
			try:
				result = self.ldapSession.search(	
						baseDn     = currentDn,
						scope      = ldap.SCOPE_BASE,
						filter     = "(&(ObjectClass=%s)(%s=*))" \
							% (self.policyReferenceObjectClass, self.policyReferenceAttributeName),
						attributes = [ self.policyReferenceAttributeName ] )
			except BackendMissingDataError, e:
				logger.debug( "No policy references found!" )
				continue
			
			for j in range( len(result[0][1][self.policyReferenceAttributeName]) ):
				if self.policyContainer and not result[0][1][self.policyReferenceAttributeName][j].endswith(self.policyContainer):
					logger.debug("Omitting policy reference '%s': does not match policyContainer" \
							% result[0][1][self.policyReferenceAttributeName][j])
					continue
				logger.debug( "Policy reference found: '%s', priority: %s" % (result[0][1][self.policyReferenceAttributeName][j], i) )
				referencePriorities[i].append( result[0][1][self.policyReferenceAttributeName][j] )
		
		policyResult = {}
		
		# Examine all found policies
		# Start with the lowest priority
		for i in range (len(referencePriorities)-1, -1, -1):
			if (referencePriorities[i] == []):
				# No policy references of that priority found
				continue
			
			for j in range( len(referencePriorities[i]) ):
				
				filter = "(ObjectClass=%s)" % self.policyObjectClass
				if (self.policyFilter):
					# Use the filter passed to constructor
					filter = self.policyFilter
				
				logger.debug("Searching in baseDN '%s', filter: %s" % 
						(referencePriorities[i][j], filter) )
				
				# Read the policy object
				try:
					objectSearch = ObjectSearch(
								self.ldapSession, 
								referencePriorities[i][j], 
								scope = ldap.SCOPE_BASE, 
								filter = filter )
					policy = objectSearch.getObject()
					policy.readFromDirectory(self.ldapSession)
				except BackendIOError, e:
					logger.warning("Cannot read policy '%s' from LDAP" % 
								referencePriorities[i][j])
					continue
				except BackendMissingDataError, e:
					logger.debug("Policy '%s' does not match filter '%s'\n" % 
								(referencePriorities[i][j], filter) )
					continue
				
				# Policy matches filter and was successfully read
				logger.debug("Processing matching policy '%s'\n" % policy.getDn() )
				
				# Sort policies by their type (objectClass)
				policyType = None
				for objectClass in policy.getObjectClasses():
					if (objectClass != self.policyObjectClass):# and objectClass.startswith(self.policyObjectClass):
						policyType = objectClass
				
				if not policyType:
					logger.error("Cannot get policy-type for policy: '%s'" % policy.getDn())
					continue
				
				# Group policies by an attribute
				# Attributes of policies in the same group will overwrite each other by priority
				policyGroup = 'default'
				if (self.independenceAttribute):
					# An independence attribute was passed to the constructor
					policyGroup = policy.getAttribute(self.independenceAttribute)
					if not policyGroup:
						logger.error("Independence attribute given, cannot read attribute '%s' from policy '%s'" \
								% (self.independenceAttribute, policy.getDn()) )
						continue
				
				if not policyResult.has_key(policyType):
					policyResult[policyType] = {}
				
				policyResult[policyType][policyGroup] = policy
				
				logger.debug("Current policy result: %s" % policyResult)
				
				for (key, value) in policy.getAttributeDict().items():
					if ( key in ('cn', 'objectClass', 'emptyAttributes', 
						     'fixedAttributes', 'prohibitedObjectClasses',
						     'requiredObjectClasses', 'overwritePolicies') ): 	
						continue
					
					if (key == 'opsiKeyValuePair'):
						if type(value) != type(()) and type(value) != type([]):
							value = [ value ]
						for v in value:
							key = v
							pos = v.find('=')
							if (pos != -1):
								key = v[:pos]
								v = v[pos+1:]
							else:
								v = None
							# joinedAttributes can be overwritten by policies with a higher priority
							logger.debug("joinedAttributes: (opsiKeyValuePair) setting key '%s' to value '%s'" \
									% (key, v) )
							self._joinedAttributes[key] = { 'value': v, 'policy': policy.getDn() }
					else:
						# joinedAttributes can be overwritten by policies with a higher priority
						logger.debug("joinedAttributes: setting key '%s' to value '%s'" \
									% (key, value) )
						self._joinedAttributes[key] = { 'value': value, 'policy': policy.getDn() }
		
		for policyType in policyResult:
			if ( len(policyResult[policyType].values()) < 1 ): continue
			for policy in policyResult[policyType].values():
				self._policies.append(policy)
				
		if not self._policies:
			raise BackendMissingDataError("No policy found for: %s, con: %s, fil: %s, ia: %s, ml: %s" \
						% (self.dn, self.policyContainer, self.policyFilter, self.independenceAttribute, self.maxLevel) )
		
		logger.debug("= = = = = = = = = = = < policy search result > = = = = = = = = = = =" )
		for policy in self._policies:
			logger.debug(policy.getDn())
		logger.debug("= = = = = = = = = = = = < joined attributes > = = = = = = = = = = = =" )
		for (key, value) in self._joinedAttributes.items():
			logger.debug("'%s' = '%s'" % (key, value['value']))
		logger.debug("= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = " )
	
	def getDns(self):
		''' Returns the dns of all objects found. '''
		return self.getReferences()
	
	def getDn(self):
		''' Returns the dn of the first object found. '''
		refs = self.getReferences()
		if ( len(refs) >= 1 ):
			return refs[0]
	
	def getReferences(self):
		''' Get references to all policies found. '''
		references = []
		for policy in self._policies:
			references.append(policy.getDn())
		return references
	
	def getObjects(self):
		''' Returns all policies found as Object instances. '''
		if ( len(self._policies) <= 0 ):
			raise BackendMissingDataError("No policy found")
		return self._policies
	
	def getObject(self):
		''' Returns first policy found as Object instance. '''
		if ( len(self._policies) <= 0 ):
			raise BackendMissingDataError("No policy found")
		if ( len(self._policies) > 1 ):
			logger.warning("More than one existing Policy!")
		return self._policies[0]
	
	def getResult(self):
		''' Returns joined attributes of all policies found. '''
		return self._joinedAttributes
		
	def getAttributeDict(self, valuesAsList=False):
		''' Returns all joined attributes as a dict. '''
		attributes = {}
		if ( len(self._policies) > 1 ):
			logger.warning("More than one existing Policy!")
		for (key, value) in self._joinedAttributes.items():
			if (valuesAsList and value['value'] != type(())) and (value['value'] != type([])):
				attributes[key] = [ value['value'] ]
			else:
				attributes[key] = value['value']
		return attributes
	
	def getAttribute(self, attribute, default=None, valuesAsList=False ):
		''' Returns a specific attribute of the joined attributes
		    Set valuesAsList to a boolean true value to get a list,
		    even if there is only one attribute value. '''
		attributes = self.getAttributeDict()
		if not attributes.has_key(attribute):
			if default:
				return default
			raise BackendMissingDataError("Attribute '%s' does not exist" % attribute)
		if ( type (attributes[attribute]) != type(()) and 
		     type (attributes[attribute]) != type([]) and valuesAsList):
			return [ attributes[attribute] ]
		else:
			return attributes[attribute]





# ======================================================================================================
# =                                       CLASS SESSION                                                =
# ======================================================================================================	

class LDAPSession:
	''' This class handles the requests to a ldap server '''
	SCOPE_SUBTREE = ldap.SCOPE_SUBTREE
	SCOPE_BASE = ldap.SCOPE_BASE
	
	def __init__(self, host='127.0.0.1', username='', password='', ldap=None):
		''' Session constructor. '''
		self._host = host
		self._username = username
		self._password = password
		self._commandCount = 0
		self._searchCount = 0
		self._deleteCount = 0
		self._addCount = 0
		self._modifyCount = 0
		self._ldap = ldap
		self.baseDn = ''
	
	def getCommandCount(self):	
		''' Get number of all commands (requests) sent to ldap server. '''
		return self._commandCount
	def getSearchCount(self):
		''' Get number of all search commands (requests) sent to ldap server. '''
		return self._searchCount
	def getDeleteCount(self):	
		''' Get number of all delete commands (requests) sent to ldap server. '''
		return self._deleteCount
	def getAddCount(self):		
		''' Get number of all add commands (requests) sent to ldap server. '''
		return self._addCount
	def getModifyCount(self):
		''' Get number of all modify commands (requests) sent to ldap server. '''
		return self._modifyCount
	def getCommandStatistics(self):
		''' Get number of all commands as dict. '''
		return { 	'total': 	self._commandCount, 
				'search':	self._searchCount, 
				'delete':	self._deleteCount, 
				'add': 		self._addCount, 
				'modify':	self._modifyCount }
	
	def connect(self):
		''' Connect to a ldap server. '''
		self._ldap = ldap.open(self._host)
		self._ldap.protocol_version = ldap.VERSION3
		try:
			self._ldap.bind_s(self._username, self._password, ldap.AUTH_SIMPLE)
			logger.info('Successfully connected to LDAP-Server.')
		except ldap.LDAPError, e:
			logger.error("Bind to LDAP failed: %s" % e)
			raise BackendIOError("Bind to LDAP server '%s' as '%s' failed: %s" % (self._host, self._username, e))
	
	def disconnect(self):
		''' Disconnect from ldap server '''
		self._ldap.unbind()
	
	def search(self, baseDn, scope, filter, attributes):
		''' This function is used to search in a ldap directory. '''
		self._commandCount += 1
		self._searchCount += 1
		logger.debug("Searching in baseDn: %s, scope: %s, filter: '%s', attributes: '%s' " \
					% (baseDn, scope, filter, attributes) )
		try:
			result = self._ldap.search_s(baseDn, scope, filter, attributes)
		except ldap.LDAPError, e:
			if (e.__class__ == ldap.FILTER_ERROR):
				# Bad search filter
				logger.critical("Bad search filter: '%s' " % e)
			
			raise BackendMissingDataError("Error searching in baseDn '%s', filter '%s', scope %s : %s" \
					% (baseDn, filter, scope, e) )
		if (result == []):
			raise BackendMissingDataError("No results for search in baseDn: '%s', filter: '%s', scope: %s" \
					% (baseDn, filter, scope) )
		return result
	
	def delete(self, dn):
		''' This function is used to delete an object in a ldap directory. '''
		self._commandCount += 1
		self._deleteCount += 1
		logger.debug("Deleting Object from LDAP, dn: '%s'" % dn)
		try:
			self._ldap.delete_s(dn)
		except ldap.LDAPError, e:
			raise BackendIOError(e)
	
	def modifyByModlist(self, dn, old, new):
		''' This function is used to modify an object in a ldap directory. '''
		self._commandCount += 1
		self._modifyCount += 1
		
		logger.debug("[old]: %s" % old)
		logger.debug("[new]: %s" % new)
		attrs = ldap.modlist.modifyModlist(old,new)
		logger.debug("[change]: %s" % attrs)
		if (attrs == []):
			logger.debug("Object '%s' unchanged." % dn)
			return
		logger.debug("Modifying Object in LDAP, dn: '%s'" % dn)
		try:
			self._ldap.modify_s(dn,attrs)
		except ldap.LDAPError, e:
			raise BackendIOError(e)
		except TypeError, e:
			raise BackendBadValueError(e)
		
		
	def addByModlist(self, dn, new):
		''' This function is used to add an object to the ldap directory. '''
		self._commandCount += 1
		self._addCount += 1
		
		attrs = ldap.modlist.addModlist(new)
		logger.debug("Adding Object to LDAP, dn: '%s'" % dn)
		logger.debug("attrs: '%s'" % attrs)
		try:
			self._ldap.add_s(dn,attrs)
		except ldap.LDAPError, e:
			raise BackendIOError(e)
		except TypeError, e:
			raise BackendBadValueError(e)


Object = LDAPObject
ObjectSearch = LDAPObjectSearch
PolicySearch = LDAPPolicySearch
Session = LDAPSession

