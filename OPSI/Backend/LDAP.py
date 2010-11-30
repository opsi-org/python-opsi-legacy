#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - LDAP    =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2010 uib GmbH
   
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
   @author: Erol Ülükmen <e.ueluekmen@uib.de>, Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '4.0.0.1'

# Imports
import ldap, ldap.modlist
from ldaptor.protocols import pureldap
from ldaptor import ldapfilter

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Backend.Backend import *
from OPSI import System

# Get logger instance
logger = Logger()

# ======================================================================================================
# =                                    CLASS LDAPBACKEND                                               =
# ======================================================================================================
class LDAPBackend(ConfigDataBackend):
	
	def __init__(self, **kwargs):
		'''
		If you want to speed up ldap backend, set something like:
		
			cachesize 10000
			
			index opsiObjectId eq
			index opsiHostId eq
			index opsiClientId eq
			index opsiDepotId eq
			index opsiConfigId eq
			index opsiPropertyId eq
			index opsiGroupId eq
			index opsiProductId eq
			index opsiProductVersion eq
			index opsiPackageVersion eq
			
			/etc/init.d/slapd stop
			slapindex
			chown openldap:openldap -R /var/lib/ldap
			/etc/init.d/slapd start
		'''
		
		self._name = 'ldap'
		
		ConfigDataBackend.__init__(self, **kwargs)
		
		self._address          = u'localhost'
		self._opsiBaseDn       = u'cn=opsi,dc=uib,dc=local'
		self._hostsContainerDn = u'cn=hosts,%s' % self._opsiBaseDn
		
		self._hostAttributeDescription     = u'opsiDescription'
		self._hostAttributeNotes           = u'opsiNotes'
		self._hostAttributeHardwareAddress = u'opsiHardwareAddress'
		self._hostAttributeIpAddress       = u'opsiIpAddress'
		self._hostAttributeInventoryNumber = u'opsiInventoryNumber' 
		
		self._clientObjectSearchFilter = u''
		self._createClientCommand      = u''
		self._deleteClient             = True
		self._deleteClientCommand      = u''
		
		self._serverObjectSearchFilter = u''
		self._createServerCommand      = u''
		self._deleteServer             = False
		self._deleteServerCommand      = u''
		
		# Parse arguments
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('address',):
				self._address = forceUnicode(value)
			elif option in ('username',):
				self._username = forceUnicode(value)
			elif option in ('password',):
				self._password = forceUnicode(value)
			elif option in ('opsibasedn',):
				self._opsiBaseDn = forceUnicode(value)
			elif option in ('hostscontainerdn',):
				self._hostsContainerDn = forceUnicode(value)
			elif option in ('hostattributedescription',):
				self._hostAttributeDescription = forceUnicode(value)
			elif option in ('hostattributenotes',):
				self._hostAttributeNotes = forceUnicode(value)
			elif option in ('hostattributehardwareaddress',):
				self._hostAttributeHardwareAddress = forceUnicode(value)
			elif option in ('hostattributeipaddress',):
				self._hostAttributeIpAddress = forceUnicode(value)
			elif option in ('hostattributeinventorynumber',):
				self._hostAttributeInventoryNumber = forceUnicode(value)
			elif option in ('clientobjectsearchfilter',):
				self._clientObjectSearchFilter = forceUnicode(value)
			elif option in ('createclientcommand',):
				self._createClientCommand = forceUnicode(value)
			elif option in ('deleteclient',):
				self._deleteClient = forceBool(value)
			elif option in ('deleteclientcommand',):
				self._deleteClientCommand = forceUnicode(value)
			elif option in ('serverobjectsearchfilter',):
				self._serverObjectSearchFilter = forceUnicode(value)
			elif option in ('createservercommand',):
				self._createServerCommand = forceUnicode(value)
			elif option in ('deleteserver',):
				self._deleteServer = forceBool(value)
			elif option in ('deleteservercommand',):
				self._deleteServerCommand = forceUnicode(value)
			
		self._configContainerDn                = u'cn=configs,%s'               % self._opsiBaseDn
		self._configStateContainerDn           = u'cn=configStates,%s'          % self._opsiBaseDn
		self._groupsContainerDn                = u'cn=groups,%s'                % self._opsiBaseDn
		self._productsContainerDn              = u'cn=products,%s'              % self._opsiBaseDn
		self._productOnDepotsContainerDn       = u'cn=productOnDepots,%s'       % self._opsiBaseDn
		self._productOnClientsContainerDn      = u'cn=productOnClients,%s'      % self._opsiBaseDn
		self._productPropertyStatesContainerDn = u'cn=productPropertyStates,%s' % self._opsiBaseDn
		#self._objectToGroupsContainerDn        = u'cn=objectToGroups,%s'        % self._opsiBaseDn
		
		if self._password:
			logger.addConfidentialString(self._password)
		
		self._mappings = [
				{
					'opsiClass':     'Host',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiHost' ],
					'attributes': [
						{ 'opsiAttribute': 'id',              'ldapAttribute': 'opsiHostId' },
						{ 'opsiAttribute': 'ipAddress',       'ldapAttribute': self._hostAttributeIpAddress },
						{ 'opsiAttribute': 'hardwareAddress', 'ldapAttribute': self._hostAttributeHardwareAddress },
						{ 'opsiAttribute': 'description',     'ldapAttribute': self._hostAttributeDescription },
						{ 'opsiAttribute': 'notes',           'ldapAttribute': self._hostAttributeNotes },
						{ 'opsiAttribute': 'inventoryNumber', 'ldapAttribute': self._hostAttributeInventoryNumber }
					]
				},
				{
					'opsiClass':      'OpsiClient',
					'opsiSuperClass': 'Host',
					'objectClasses':  [ 'opsiHost', 'opsiClient' ],
					'attributes': [
						{ 'opsiAttribute': 'created',         'ldapAttribute': 'opsiCreatedTimestamp' },
						{ 'opsiAttribute': 'lastSeen',        'ldapAttribute': 'opsiLastSeenTimestamp' },
						{ 'opsiAttribute': 'opsiHostKey',     'ldapAttribute': 'opsiHostKey' },
						{ 'opsiAttribute': 'oneTimePassword', 'ldapAttribute': 'opsiOneTimePassword' }
					]
				},
				{
					'opsiClass':      'OpsiDepotserver',
					'opsiSuperClass': 'Host',
					'objectClasses':  [ 'opsiHost', 'opsiDepotserver' ],
					'attributes': [
						{ 'opsiAttribute': 'depotLocalUrl',       'ldapAttribute': 'opsiDepotLocalUrl' },
						{ 'opsiAttribute': 'depotRemoteUrl',      'ldapAttribute': 'opsiDepotRemoteUrl' },
						{ 'opsiAttribute': 'depotWebdavUrl',      'ldapAttribute': 'opsiDepotWebdavUrl' },
						{ 'opsiAttribute': 'repositoryLocalUrl',  'ldapAttribute': 'opsiRepositoryLocalUrl' },
						{ 'opsiAttribute': 'repositoryRemoteUrl', 'ldapAttribute': 'opsiRepositoryRemoteUrl' },
						{ 'opsiAttribute': 'networkAddress',      'ldapAttribute': 'opsiNetworkAddress' },
						{ 'opsiAttribute': 'maxBandwidth',        'ldapAttribute': 'opsiMaximumBandwidth' },
						{ 'opsiAttribute': 'opsiHostKey',         'ldapAttribute': 'opsiHostKey' },
						{ 'opsiAttribute': 'isMasterDepot',       'ldapAttribute': 'opsiIsMasterDepot' },
						{ 'opsiAttribute': 'masterDepotId',       'ldapAttribute': 'opsiMasterDepotId' }
					]
				},
				{
					'opsiClass':      'OpsiConfigserver',
					'opsiSuperClass': 'OpsiDepotserver',
					'objectClasses':  [ 'opsiHost', 'opsiDepotserver', 'opsiConfigserver' ],
					'attributes': [
					]
				},
				{
					'opsiClass':     'Config',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiConfig' ],
					'attributes': [
						{ 'opsiAttribute': 'id',              'ldapAttribute': 'opsiConfigId' },
						{ 'opsiAttribute': 'description',     'ldapAttribute': 'opsiDescription' },
						{ 'opsiAttribute': 'defaultValues',   'ldapAttribute': 'opsiDefaultValue' },
						{ 'opsiAttribute': 'possibleValues',  'ldapAttribute': 'opsiPossibleValue' },
						{ 'opsiAttribute': 'editable',        'ldapAttribute': 'opsiEditable' },
						{ 'opsiAttribute': 'multiValue',      'ldapAttribute': 'opsiMultiValue' }
					]
				},
				{
					'opsiClass':      'UnicodeConfig',
					'opsiSuperClass': 'Config',
					'objectClasses':  [ 'opsiConfig', 'opsiUnicodeConfig' ],
					'attributes': [
					]
				},
				{
					'opsiClass':      'BoolConfig',
					'opsiSuperClass': 'Config',
					'objectClasses':  [ 'opsiConfig', 'opsiBoolConfig' ],
					'attributes': [
					]
				},
				{
					'opsiClass':     'ConfigState',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiConfigState' ],
					'attributes': [
						{ 'opsiAttribute': 'configId', 'ldapAttribute': 'opsiConfigId' },
						{ 'opsiAttribute': 'objectId', 'ldapAttribute': 'opsiObjectId' },
						{ 'opsiAttribute': 'values',   'ldapAttribute': 'opsiValue' }
					]
				},
				{
					'opsiClass':     'Product',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProduct' ],
					'attributes': [
						{ 'opsiAttribute': 'id',                 'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'productVersion',     'ldapAttribute': 'opsiProductVersion' },
						{ 'opsiAttribute': 'packageVersion',     'ldapAttribute': 'opsiPackageVersion' },
						{ 'opsiAttribute': 'name',               'ldapAttribute': 'opsiProductName' },
						{ 'opsiAttribute': 'licenseRequired',    'ldapAttribute': 'opsiProductLicenseRequired' },
						{ 'opsiAttribute': 'setupScript',        'ldapAttribute': 'opsiSetupScript' },
						{ 'opsiAttribute': 'uninstallScript',    'ldapAttribute': 'opsiUninstallScript' },
						{ 'opsiAttribute': 'updateScript',       'ldapAttribute': 'opsiUpdateScript' },
						{ 'opsiAttribute': 'alwaysScript',       'ldapAttribute': 'opsiAlwaysScript' },
						{ 'opsiAttribute': 'onceScript',         'ldapAttribute': 'opsiOnceScript' },
						{ 'opsiAttribute': 'customScript',       'ldapAttribute': 'opsiCustomScript' },
						{ 'opsiAttribute': 'userLoginScript',    'ldapAttribute': 'opsiUserLoginScript' },
						{ 'opsiAttribute': 'priority',        	 'ldapAttribute': 'opsiProductPriority' },
						{ 'opsiAttribute': 'description',        'ldapAttribute': 'description' },
						{ 'opsiAttribute': 'advice',             'ldapAttribute': 'opsiProductAdvice' },
						{ 'opsiAttribute': 'changelog',          'ldapAttribute': 'opsiProductChangeLog' },
						{ 'opsiAttribute': 'windowsSoftwareIds', 'ldapAttribute': 'opsiWindowsSoftwareId' },
						{ 'opsiAttribute': 'productClassIds',    'ldapAttribute': 'opsiProductClassId' }
						
					]
				},
				{
					'opsiClass':      'LocalbootProduct',
					'opsiSuperClass': 'Product',
					'objectClasses':  [ 'opsiProduct', 'opsiLocalBootProduct' ],
					'attributes': [
					]
				},
				{
					'opsiClass':     'NetbootProduct',
					'opsiSuperClass': 'Product',
					'objectClasses': [ 'opsiProduct', 'opsiNetBootProduct' ],
					'attributes': [
						{ 'opsiAttribute': 'pxeConfigTemplate', 'ldapAttribute': 'opsiPxeConfigTemplate' }
					]
				},
				{
					'opsiClass':     'ProductProperty',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProductProperty' ],
					'attributes': [
						{ 'opsiAttribute': 'productId',         'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'propertyId',        'ldapAttribute': 'opsiPropertyId' },
						{ 'opsiAttribute': 'productVersion',    'ldapAttribute': 'opsiProductVersion' },
						{ 'opsiAttribute': 'packageVersion',    'ldapAttribute': 'opsiPackageVersion' },
						{ 'opsiAttribute': 'description',       'ldapAttribute': 'opsiDescription' },
						{ 'opsiAttribute': 'requiredProductId', 'ldapAttribute': 'opsiRequiredProductId' },
						{ 'opsiAttribute': 'possibleValues',    'ldapAttribute': 'opsiPossibleValue' },
						{ 'opsiAttribute': 'defaultValues',     'ldapAttribute': 'opsiDefaultValue' },
						{ 'opsiAttribute': 'editable',          'ldapAttribute': 'opsiEditable' },
						{ 'opsiAttribute': 'multiValue',        'ldapAttribute': 'opsiMultiValue' }
					]
				},
				{
					'opsiClass':      'UnicodeProductProperty',
					'opsiSuperClass': 'ProductProperty',
					'objectClasses':  [ 'opsiProductProperty', 'opsiUnicodeProductProperty' ],
					'attributes': [
					]
				},
				{
					'opsiClass':     'BoolProductProperty',
					'opsiSuperClass': 'ProductProperty',
					'objectClasses': [ 'opsiProductProperty', 'opsiBoolProductProperty' ],
					'attributes': [
						{ 'opsiAttribute': 'pxeConfigTemplate', 'ldapAttribute': 'opsiPxeConfigTemplate' }
					]
				},
				{
					'opsiClass':     'ProductDependency',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProductDependency' ],
					'attributes': [
						{ 'opsiAttribute': 'productId',                  'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'productVersion',             'ldapAttribute': 'opsiProductVersion' },
						{ 'opsiAttribute': 'packageVersion',             'ldapAttribute': 'opsiPackageVersion' },
						{ 'opsiAttribute': 'requiredProductId',          'ldapAttribute': 'opsiRequiredProductId' },
						{ 'opsiAttribute': 'requiredAction',             'ldapAttribute': 'opsiActionRequired' },
						{ 'opsiAttribute': 'productAction',              'ldapAttribute': 'opsiProductAction' },
						{ 'opsiAttribute': 'requiredProductVersion',     'ldapAttribute': 'opsiRequiredProductVersion' },
						{ 'opsiAttribute': 'requiredPackageVersion',     'ldapAttribute': 'opsiRequiredPackageVersion' },
						{ 'opsiAttribute': 'requiredInstallationStatus', 'ldapAttribute': 'opsiInstallationStatusRequired' },
						{ 'opsiAttribute': 'requirementType',            'ldapAttribute': 'opsiRequirementType' }
					]
				},
				{
					'opsiClass':     'ProductOnDepot',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProductOnDepot' ],
					'attributes': [
						{ 'opsiAttribute': 'productId',      'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'productType',    'ldapAttribute': 'opsiProductType' },
						{ 'opsiAttribute': 'productVersion', 'ldapAttribute': 'opsiProductVersion' },
						{ 'opsiAttribute': 'packageVersion', 'ldapAttribute': 'opsiPackageVersion' },
						{ 'opsiAttribute': 'depotId',        'ldapAttribute': 'opsiDepotId' },
						{ 'opsiAttribute': 'locked',         'ldapAttribute': 'opsiLocked' }
					]
				},
				{
					'opsiClass':     'ProductOnClient',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProductOnClient' ],
					'attributes': [
						{ 'opsiAttribute': 'productId',          	'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'productType',        	'ldapAttribute': 'opsiProductType' },
						{ 'opsiAttribute': 'clientId',           	'ldapAttribute': 'opsiClientId' },
						{ 'opsiAttribute': 'targetConfiguration',       'ldapAttribute': 'opsiTargetConfiguration' },
						{ 'opsiAttribute': 'installationStatus', 	'ldapAttribute': 'opsiProductInstallationStatus' },
						{ 'opsiAttribute': 'actionRequest',      	'ldapAttribute': 'opsiProductActionRequest' },
						{ 'opsiAttribute': 'actionProgress',     	'ldapAttribute': 'opsiProductActionProgress' },
						{ 'opsiAttribute': 'actionResult',     		'ldapAttribute': 'opsiActionResult' },
						{ 'opsiAttribute': 'lastAction',     		'ldapAttribute': 'opsiLastAction' },
						{ 'opsiAttribute': 'productVersion',     	'ldapAttribute': 'opsiProductVersion' },
						{ 'opsiAttribute': 'packageVersion',     	'ldapAttribute': 'opsiPackageVersion' },
						{ 'opsiAttribute': 'modificationTime',    	'ldapAttribute': 'opsiModificationTime' },
						{ 'opsiAttribute': 'actionSequence',     	'ldapAttribute': None }
					]
				},
				{
					'opsiClass':     'ProductPropertyState',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiProductPropertyState' ],
					'attributes': [
						{ 'opsiAttribute': 'productId',  'ldapAttribute': 'opsiProductId' },
						{ 'opsiAttribute': 'propertyId', 'ldapAttribute': 'opsiPropertyId' },
						{ 'opsiAttribute': 'objectId',   'ldapAttribute': 'opsiObjectId' },
						{ 'opsiAttribute': 'values',     'ldapAttribute': 'opsiProductPropertyValue' }
					]
				},
				{
					'opsiClass':     'Group',
					'opsiSuperClass': None,
					'objectClasses': [ 'opsiGroup' ],
					'attributes': [
						{ 'opsiAttribute': 'id',            'ldapAttribute': 'opsiGroupId' },
						{ 'opsiAttribute': 'description',   'ldapAttribute': 'opsiDescription' },
						{ 'opsiAttribute': 'notes',         'ldapAttribute': 'opsiNotes' },
						{ 'opsiAttribute': 'parentGroupId', 'ldapAttribute': 'opsiParentGroupId' },
						{ 'opsiAttribute': 'objectId',      'ldapAttribute': 'opsiMemberObjectId' } # members
					]
				},
				{
					'opsiClass':     'HostGroup',
					'opsiSuperClass': 'Group',
					'objectClasses': [ 'opsiHostGroup' ],
					'attributes': [
					]
				}
				#,
				#{
				#	'opsiClass':     'ObjectToGroup',
				#	'opsiSuperClass': None,
				#	'objectClasses': [ 'opsiObjectToGroup' ],
				#	'attributes': [
				#		{ 'opsiAttribute': 'groupId',                     'ldapAttribute': 'opsiGroupId' },
				#		{ 'opsiAttribute': 'objectId',                    'ldapAttribute': 'opsiObjectId' }
				#	]
				#}
			]
		
		self._opsiAttributeToLdapAttribute = {}
		self._ldapAttributeToOpsiAttribute = {}
		self._opsiClassToLdapClasses = {}
		for mapping in self._mappings:
			self._opsiClassToLdapClasses[ mapping['opsiClass'] ] = mapping['objectClasses']
			self._opsiAttributeToLdapAttribute[ mapping['opsiClass'] ] = {}
			self._ldapAttributeToOpsiAttribute[ mapping['opsiClass'] ] = {}
			if mapping.get('opsiSuperClass'):
				self._opsiAttributeToLdapAttribute[ mapping['opsiClass'] ] = dict( self._opsiAttributeToLdapAttribute[ mapping['opsiSuperClass'] ] )
				self._ldapAttributeToOpsiAttribute[ mapping['opsiClass'] ] = dict( self._ldapAttributeToOpsiAttribute[ mapping['opsiSuperClass'] ] )
			for attribute in mapping['attributes']:
				self._opsiAttributeToLdapAttribute[ mapping['opsiClass'] ][ attribute['opsiAttribute'] ] = attribute['ldapAttribute']
				self._ldapAttributeToOpsiAttribute[ mapping['opsiClass'] ][ attribute['ldapAttribute'] ] = attribute['opsiAttribute']
		
		self._ldapClassesToOpsiClassCache = {}
		self._opsiLdapClasses = []
		for (opsiClass, ldapClasses) in self._opsiClassToLdapClasses.items():
			for ldapClass in ldapClasses:
				if not ldapClass in self._opsiLdapClasses:
					self._opsiLdapClasses.append(ldapClass)
		
		logger.info(u"Connecting to ldap server '%s' as user '%s'" % (self._address, self._username))
		self._ldap = LDAPSession(**kwargs)
		self._ldap.connect()
		
	
	# -------------------------------------------------
	# -     HELPERS                                   -
	# -------------------------------------------------
		
	def _objectFilterToLDAPFilter(self, filter):
		
		ldapFilter = None
		filters = []
		objectTypes = []
		for objectType in forceList(filter.get('type')):
			if not objectType in objectTypes:
				objectTypes.append(objectType)
			objectClasses = self._opsiClassToLdapClasses.get(objectType)
			if not objectClasses:
				continue
			
			classFilters = []
			for objectClass in objectClasses:
				classFilters.append(
					pureldap.LDAPFilter_equalityMatch(
						attributeDesc  = pureldap.LDAPAttributeDescription('objectClass'),
						assertionValue = pureldap.LDAPAssertionValue(objectClass)
					)
				)
			
			if classFilters:
				if (len(classFilters) == 1):
					filters.append(classFilters[0])
				else:
					filters.append(pureldap.LDAPFilter_and(classFilters))
			
		if filters:
			if (len(filters) == 1):
				ldapFilter = filters[0]
			else:
				ldapFilter = pureldap.LDAPFilter_or(filters)
		
		if not ldapFilter:
			ldapFilter = pureldap.LDAPFilter_present('objectClass')
		
		
		andFilters = []
		for (attribute, values) in filter.items():
			if (attribute == 'type'):
				continue
			if (attribute == 'cn'):
				continue
				
			if values is None:
				continue
			
			mappingFound = False
			for objectType in objectTypes:
				if self._opsiAttributeToLdapAttribute[objectType].has_key(attribute):
					attribute = self._opsiAttributeToLdapAttribute[objectType][attribute]
					mappingFound = True
					break
			
			if not mappingFound:
				logger.debug(u"No mapping found for opsi attribute '%s' of classes %s" % (attribute, objectTypes))
			
			filters = []
			for value in forceList(values):
				if value in (None, ""):
					filters.append(
						pureldap.LDAPFilter_not(
							pureldap.LDAPFilter_present(attribute)
						)
					)
					
				else:
					if type(value) is bool:
						if value: value = u'TRUE'
						else: value = u'FALSE'
					if type(value) is str:
						value = forceUnicode(value)
					
					filters.append( ldapfilter.parseFilter("(%s=%s)" % (attribute, value)) )
					
			if filters:
				if (len(filters) == 1):
					andFilters.append(filters[0])
				else:
					andFilters.append(pureldap.LDAPFilter_or(filters))
		if andFilters:
			newFilter = None
			if (len(andFilters) == 1):
				newFilter = andFilters[0]
			else:
				newFilter = pureldap.LDAPFilter_and(andFilters)
			ldapFilter = pureldap.LDAPFilter_and( [ldapFilter, newFilter] )
		
		textfilter = forceUnicode(ldapFilter.asText())
		logger.debug2(u"Filter is: %s" % textfilter)
		return textfilter
		
	def _createOrganizationalRole(self, dn):
		''' This method will add a oprganizational role object
		    with the specified DN, if it does not already exist. '''
		organizationalRole = LDAPObject(dn)
		if organizationalRole.exists(self._ldap):
			logger.info(u"Organizational role '%s' already exists" % dn)
		else:
			logger.debug(u"Creating organizational role '%s'" % dn)
			organizationalRole.new('organizationalRole')
			organizationalRole.writeToDirectory(self._ldap)
			logger.info(u"Organizational role '%s' created" % dn)
	
	def backend_deleteBase(self):
		ConfigDataBackend.backend_deleteBase(self)
		ldapobj = LDAPObject(self._opsiBaseDn)
		if ldapobj.exists(self._ldap):
			ldapobj.deleteFromDirectory(self._ldap, recursive = True)
		
		
	def backend_createBase(self):
		ConfigDataBackend.backend_createBase(self)
		
		# Create some containers
		self._createOrganizationalRole(self._opsiBaseDn)
		self._createOrganizationalRole(self._hostsContainerDn)
		self._createOrganizationalRole(self._configContainerDn)
		self._createOrganizationalRole(self._configStateContainerDn)
		self._createOrganizationalRole(self._groupsContainerDn)
		self._createOrganizationalRole(u"cn=hostGroups,%s" % self._groupsContainerDn)
		self._createOrganizationalRole(self._productsContainerDn)
		self._createOrganizationalRole(self._productOnDepotsContainerDn)
		self._createOrganizationalRole(self._productOnClientsContainerDn)
		self._createOrganizationalRole(self._productPropertyStatesContainerDn)
		#self._createOrganizationalRole(self._objectToGroupsContainerDn)
	
	
	def backend_exit(self):
		pass
	
	def _ldapObjectToOpsiObject(self, ldapObject, attributes=[], ignoreLdapAttributes=[]):
		'''
			Method to convert ldap-Object to opsi-Object
		
		'''
		self._ldapAttributeToOpsiAttribute
		self._opsiClassToLdapClasses
		
		
		ldapObject.readFromDirectory(self._ldap)
		
		#logger.debug2(u"Searching opsi class for ldap objectClasses: %s" % ldapObject.getObjectClasses())
		cacheKey = ':'.join(ldapObject.getObjectClasses())
		opsiClassName = self._ldapClassesToOpsiClassCache.get(cacheKey)
		if opsiClassName:
			#logger.debug2(u"Using cached mapping: %s <=> %s" % (cacheKey, opsiClassName))
			pass
		else:
			for (opsiClass, ldapClasses) in self._opsiClassToLdapClasses.items():
				#logger.debug2(u"Testing opsi class '%s' (ldapClasses: %s)" % (opsiClass, ldapClasses))
				matched = True
				for objectClass in ldapObject.getObjectClasses():
					if not objectClass in self._opsiLdapClasses:
						# Not an opsi ldap class
						continue
					if not objectClass in ldapClasses:
						matched = False
						continue
				for objectClass in ldapClasses:
					if not objectClass in ldapObject.getObjectClasses():
						matched = False
						continue
				
				if matched:
					opsiClassName = opsiClass
					self._ldapClassesToOpsiClassCache[cacheKey] = opsiClassName
					break
		
		if not opsiClassName:
			raise Exception(u"Failed to get opsi class for ldap objectClasses: %s" % ldapObject.getObjectClasses())
		
		#logger.debug2(u"Mapped ldap objectClasses %s to opsi class: %s" % (ldapObject.getObjectClasses(), opsiClassName))
		
		Class = eval(opsiClassName)
		identAttributes = mandatoryConstructorArgs(Class)
		if attributes:
			for identAttribute in identAttributes:
				if not identAttribute in attributes:
					attributes.append(identAttribute)
		
		opsiObjectHash = {}
		for (attribute, value) in ldapObject.getAttributeDict(valuesAsList = False).items():
			#logger.debug2(u"LDAP attribute is: %s" % attribute)
			if attribute in ('objectClass', 'cn') or attribute in ignoreLdapAttributes:
				continue
			
			if self._ldapAttributeToOpsiAttribute[opsiClassName].has_key(attribute):
				attribute = self._ldapAttributeToOpsiAttribute[opsiClassName][attribute]
			else:
				logger.debug(u"No mapping found for ldap attribute '%s' of class '%s'" % (attribute, opsiClassName))
			
			if attribute in ('cn',):
				continue
			
			if not attributes or attribute in attributes:
				opsiObjectHash[attribute] = value
		
		opsiObject = Class.fromHash(opsiObjectHash)
		# Call setDefaults because LDAPBackend cannot distinguish between None and []
		opsiObject.setDefaults()
		if attributes:
			for attribute in opsiObject.toHash().keys():
				if not attribute in attributes:
					setattr(opsiObject, attribute, None)
		return opsiObject
	
	def _opsiObjectToLdapObject(self, opsiObject, dn):
		'''
			Method to convert Opsi-Object to ldap-Object
		'''
		
		objectClasses = []
		
		for (opsiClass, ldapClasses) in self._opsiClassToLdapClasses.items():
			if (opsiObject.getType() == opsiClass):
				objectClasses = ldapClasses
				break
		
		if not objectClasses:
			raise Exception(u"Failed to get ldapClasses for OpsiClass: %s" % opsiObject)
			
		
		ldapObj = LDAPObject(dn)
		ldapObj.new(*objectClasses)
		for (attribute, value) in opsiObject.toHash().items():
			if (attribute == 'type'):
				continue
			if (attribute == 'productClassIds'):
				value = []
			if self._opsiAttributeToLdapAttribute[opsiObject.getType()].has_key(attribute):
				if self._opsiAttributeToLdapAttribute[opsiObject.getType()][attribute] is None:
					# Attribute which are mapped to None should not be writte to ldap
					continue
				attribute = self._opsiAttributeToLdapAttribute[opsiObject.getType()][attribute]
			else:
				logger.debug(u"No mapping found for opsi attribute '%s' of class '%s'" % (attribute, opsiObject.getType()))
			ldapObj.setAttribute(attribute, value)
		
		return ldapObj
	
	def _updateLdapObject(self, ldapObject, opsiObject, updateWhereNone=False):
		ldapObject.readFromDirectory(self._ldap)
		newLdapObject = self._opsiObjectToLdapObject(opsiObject, ldapObject.getDn())
		for (attribute, value) in newLdapObject.getAttributeDict(valuesAsList=True).items():
			if   (attribute == 'cn'):
				continue
			elif (attribute == 'objectClass'):
				if not value:
					value = []
				value = forceList(value)
				for oc in ldapObject.getObjectClasses():
					if not oc in value:
						value.append(oc)
			elif value in (None, []):
				if not updateWhereNone:
					continue
				value = []
			ldapObject.setAttribute(attribute, value)
		ldapObject.writeToDirectory(self._ldap)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _getHostDn(self, host):
		ldapFilter = self._objectFilterToLDAPFilter( { 'type': host.getType(),'id': host.id } )
		search = LDAPObjectSearch(self._ldap, self._hostsContainerDn, filter = ldapFilter)
		dn = search.getDn()
		if dn:
			return dn
		
		ldapFilter = None
		if (host.getType() == 'OpsiClient') and self._clientObjectSearchFilter:
			ldapFilter = self._clientObjectSearchFilter
		if host.getType() in ('OpsiConfigserver', 'OpsiDepotserver') and self._serverObjectSearchFilter:
			ldapFilter = self._serverObjectSearchFilter
		
		if ldapFilter:
			ldapFilter = ldapFilter.replace(u'%name%',            host.id.split(u'.')[0])
			ldapFilter = ldapFilter.replace(u'%hostname%',        host.id.split(u'.')[0])
			ldapFilter = ldapFilter.replace(u'%domain%',          u'.'.join(host.id.split('.')[1:]))
			ldapFilter = ldapFilter.replace(u'%id%',              host.id)
			ldapFilter = ldapFilter.replace(u'%fqdn%',            host.id)
			ldapFilter = ldapFilter.replace(u'%description%',     host.description or '')
			ldapFilter = ldapFilter.replace(u'%notes%',           host.notes or '')
			ldapFilter = ldapFilter.replace(u'%hardwareaddress%', host.hardwareAddress or '')
			ldapFilter = ldapFilter.replace(u'%ipaddress%',       host.ipAddress or '')
			ldapFilter = ldapFilter.replace(u'%inventorynumber%', host.inventoryNumber or '')
			ldapFilter = ldapFilter.replace(u'%username%',        self._username)
			ldapFilter = ldapFilter.replace(u'%password%',        self._password)
			
			search = LDAPObjectSearch(self._ldap, self._hostsContainerDn, filter = ldapFilter)
			dn = search.getDn()
			if not dn:
				createCommand = None
				if (host.getType() == 'OpsiClient') and self._createClientCommand:
					createCommand = self._createClientCommand
				if host.getType() in ('OpsiConfigserver', 'OpsiDepotserver') and self._createServerCommand:
					createCommand = self._createServerCommand
				if createCommand:
					createCommand = createCommand.replace(u'%name%',            host.id.split(u'.')[0])
					createCommand = createCommand.replace(u'%hostname%',        host.id.split(u'.')[0])
					createCommand = createCommand.replace(u'%domain%',          u'.'.join(host.id.split('.')[1:]))
					createCommand = createCommand.replace(u'%id%',              host.id)
					createCommand = createCommand.replace(u'%fqdn%',            host.id)
					createCommand = createCommand.replace(u'%description%',     host.description or '')
					createCommand = createCommand.replace(u'%notes%',           host.notes or '')
					createCommand = createCommand.replace(u'%hardwareaddress%', host.hardwareAddress or '')
					createCommand = createCommand.replace(u'%ipaddress%',       host.ipAddress or '')
					createCommand = createCommand.replace(u'%inventorynumber%', host.inventoryNumber or '')
					createCommand = createCommand.replace(u'%username%',        self._username)
					createCommand = createCommand.replace(u'%password%',        self._password)
					try:
						System.execute(createCommand)
					except Exception, e:
						raise BackendIOError(u"Failed to create host %s: %s" % (host, e))
					search = LDAPObjectSearch(self._ldap, self._hostsContainerDn, filter = ldapFilter)
					dn = search.getDn()
		if not dn:
			dn = 'cn=%s,%s' % (host.id, self._hostsContainerDn)
		return dn
		
	def host_insertObject(self, host):
		ConfigDataBackend.host_insertObject(self, host)
		
		dn = self._getHostDn(host)
		logger.info(u"Creating host: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			isOpsiHost = bool('OpsiHost' in ldapObject.getObjectClasses())
			if not isOpsiHost:
				if not host.description:     host.description = None
				if not host.notes:           host.notes = None
				if not host.hardwareAddress: host.hardwareAddress = None
				if not host.ipAddress:       host.ipAddress = None
				if not host.inventoryNumber: host.inventoryNumber = None
			self._updateLdapObject(ldapObject, host, updateWhereNone = isOpsiHost)
		else:
			ldapObject = self._opsiObjectToLdapObject(host, dn)
			ldapObject.writeToDirectory(self._ldap)
		
	def host_updateObject(self, host):
		ConfigDataBackend.host_updateObject(self, host)
		
		filter = { 'type': host.getType(), 'id': host.id }
		search = LDAPObjectSearch(self._ldap, self._hostsContainerDn, filter = self._objectFilterToLDAPFilter(filter) )
		dn = search.getDn()
		if not dn:
			raise Exception(u"Host %s not found" % host)
		logger.info(u"Updating host: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, host)
		
	def host_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.host_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting hosts, filter: %s" % filter)
		hosts = []
		
		if not filter.get('type'):
			filter['type'] = [ 'OpsiClient', 'OpsiDepotserver', 'OpsiConfigserver']
		
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._hostsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			hosts.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return hosts
		
	def host_deleteObjects(self, hosts):
		ConfigDataBackend.host_deleteObjects(self, hosts)
		
		for host in forceObjectClassList(hosts, Host):
			dn = self._getHostDn(host)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting host: %s" % dn)
				if ((host.getType() == 'OpsiClient') and self._deleteClient) or (host.getType() in ('OpsiConfigserver', 'OpsiDepotserver') and self._deleteServer):
					deleteCommand = None
					if (host.getType() == 'OpsiClient') and self._deleteClientCommand:
						deleteCommand = self._deleteClientCommand
					if (host.getType() in ('OpsiConfigserver', 'OpsiDepotserver') and self._deleteServerCommand):
						deleteCommand = self._deleteServerCommand
					if deleteCommand:
						deleteCommand = deleteCommand.replace(u'%dn%',              dn)
						deleteCommand = deleteCommand.replace(u'%name%',            host.id.split(u'.')[0])
						deleteCommand = deleteCommand.replace(u'%hostname%',        host.id.split(u'.')[0])
						deleteCommand = deleteCommand.replace(u'%domain%',          u'.'.join(host.id.split('.')[1:]))
						deleteCommand = deleteCommand.replace(u'%id%',              host.id)
						deleteCommand = deleteCommand.replace(u'%fqdn%',            host.id)
						deleteCommand = deleteCommand.replace(u'%description%',     host.description or '')
						deleteCommand = deleteCommand.replace(u'%notes%',           host.notes or '')
						deleteCommand = deleteCommand.replace(u'%hardwareaddress%', host.hardwareAddress or '')
						deleteCommand = deleteCommand.replace(u'%ipaddress%',       host.ipAddress or '')
						deleteCommand = deleteCommand.replace(u'%inventorynumber%', host.inventoryNumber or '')
						deleteCommand = deleteCommand.replace(u'%username%',        self._username)
						deleteCommand = deleteCommand.replace(u'%password%',        self._password)
						System.execute(deleteCommand)
					else:
						ldapObj.readFromDirectory(self._ldap)
						delete = False
						for (attribute, values) in ldapObj.getAttributeDict(valuesAsList = True).items():
							if (attribute == 'objectClass'):
								for oc in ('opsiHost', 'opsiClient', 'opsiDepotserver', 'opsiConfigserver'):
									if oc in values:
										values.remove(oc)
								if not values:
									# No objectclasses left
									delete = True
									break
							elif attribute in (	'opsiDescription', 'opsiNotes', 'opsiHardwareAddress', 'opsiIpAddress', 'opsiInventoryNumber', \
										'opsiHostId', 'opsiCreatedTimestamp', 'opsiLastSeenTimestamp', 'opsiHostKey', \
										'opsiDepotLocalUrl', 'opsiDepotRemoteUrl', 'opsiDepotWebdavUrl', 'opsiRepositoryLocalUrl', 'opsiRepositoryRemoteUrl', \
										'opsiNetworkAddress', 'opsiMaximumBandwidth', 'opsiHostKey', 'opsiIsMasterDepot', 'opsiMasterDepotId'):
								values = []
							else:
								continue
							logger.error("attribute: %s, value: %s" % (attribute, values))
							ldapObj.setAttribute(attribute, values)
						if delete:
							ldapObj.deleteFromDirectory(self._ldap, recursive = True)
						else:
							ldapObj.writeToDirectory(self._ldap)
						
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config):
		ConfigDataBackend.config_insertObject(self, config)
		
		dn = u'cn=%s,%s' % (config.id, self._configContainerDn)
		logger.info(u"Creating Config: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, config, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(config, dn)
			ldapObject.writeToDirectory(self._ldap)
		
	
	def config_updateObject(self, config):
		ConfigDataBackend.config_updateObject(self, config)
		
		dn = u'cn=%s,%s' % (config.id, self._configContainerDn)
		logger.info(u"Updating config: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, config)
		
	def config_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.config_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting configs, filter %s" % filter)
		configs = []
		
		if not filter.get('type'):
			filter['type'] = [ 'Config', 'UnicodeConfig', 'BoolConfig']
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._configContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			configs.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return configs
	
	def config_deleteObjects(self, configs):
		ConfigDataBackend.config_deleteObjects(self, configs)
		
		for config in forceObjectClassList(configs, Config):
			dn = u'cn=%s,%s' % (config.id, self._configContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting config: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		ConfigDataBackend.configState_insertObject(self, configState)
		
		containerDn = u'cn=%s,%s' % (configState.objectId, self._configStateContainerDn)
		self._createOrganizationalRole(containerDn)
		dn = u'cn=%s,%s' % (configState.configId, containerDn)
		
		logger.info(u"Creating ConfigState: %s" % dn)
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, configState, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(configState, dn)
			ldapObject.writeToDirectory(self._ldap)
	
	def configState_updateObject(self, configState):
		ConfigDataBackend.configState_updateObject(self, configState)
		
		dn = u'cn=%s,cn=%s,%s' % (configState.configId, configState.objectId, self._configStateContainerDn)
		logger.info(u"Updating configState: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, configState)
	
	def configState_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.configState_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting configStates, filter %s" % filter)
		configStates = []
		
		if not filter.get('type'):
			filter['type'] = ['ConfigState']
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._configStateContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			configStates.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return configStates
		
	def configState_deleteObjects(self, configStates):
		ConfigDataBackend.configState_deleteObjects(self, configStates)
		
		for configState in forceObjectClassList(configStates, ConfigState):
			dn = u'cn=%s,cn=%s,%s' % (configState.configId, configState.objectId, self._configStateContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting configState: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product):
		ConfigDataBackend.product_insertObject(self, product)
		
		dn = u'cn=%s_%s-%s,%s' % (product.id, product.productVersion, product.packageVersion, self._productsContainerDn)
		logger.info(u"Creating Product: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, product, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(product, dn)
			ldapObject.writeToDirectory(self._ldap)
	
	def product_updateObject(self, product):
		ConfigDataBackend.product_updateObject(self, product)
		
		dn = u'cn=%s_%s-%s,%s' % (product.id, product.productVersion, product.packageVersion, self._productsContainerDn)
		logger.info(u"Updating product: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, product)
		
	def product_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.product_getObjects(self, attributes=[], **filter)
	
		logger.info(u"Getting products, filter %s" % filter)
		products = []
		
		if not filter.get('type'):
			filter['type'] = [ 'Product', 'LocalbootProduct', 'NetbootProduct' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			products.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return products
		
	def product_deleteObjects(self, products):
		ConfigDataBackend.product_deleteObjects(self, products)
		
		for product in forceObjectClassList(products, Product):
			dn = u'cn=%s_%s-%s,%s' % (product.id, product.productVersion, product.packageVersion, self._productsContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting product: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
				
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty):
		ConfigDataBackend.productProperty_insertObject(self, productProperty)
		
		containerDn = u'cn=productProperties,cn=%s_%s-%s,%s' \
			% (productProperty.productId, productProperty.productVersion, productProperty.packageVersion, self._productsContainerDn)
		self._createOrganizationalRole(containerDn)
		dn = u'cn=%s,%s' % (productProperty.propertyId, containerDn)
		
		logger.info(u"Creating ProductProperty: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, productProperty, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(productProperty, dn)
			ldapObject.writeToDirectory(self._ldap)
		
	
	def productProperty_updateObject(self, productProperty):
		ConfigDataBackend.productProperty_updateObject(self, productProperty)
		
		dn = u'cn=%s,cn=productProperties,cn=%s_%s-%s,%s' \
			% (productProperty.propertyId, productProperty.productId, productProperty.productVersion, productProperty.packageVersion, self._productsContainerDn)
		logger.info(u"Updating ProductProperty: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, productProperty)
	
	def productProperty_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productProperty_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting productProperty, filter %s" % filter)
		properties = []
		
		if not filter.get('type'):
			filter['type'] = [ 'ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			properties.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return properties
	
	def productProperty_deleteObjects(self, productProperties):
		ConfigDataBackend.productProperty_deleteObjects(self, productProperties)
		
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			dn = u'cn=%s,cn=productProperties,cn=%s_%s-%s,%s' \
				% (productProperty.propertyId, productProperty.productId, productProperty.productVersion, productProperty.packageVersion, self._productsContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting configState: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                       -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(self, productDependency):
		ConfigDataBackend.productDependency_insertObject(self, productDependency)
		
		containerDn = u'cn=productDependencies,cn=%s_%s-%s,%s' \
			% (productDependency.productId, productDependency.productVersion, productDependency.packageVersion, self._productsContainerDn)
		self._createOrganizationalRole(containerDn)
		
		containerDn = u'cn=%s,%s' % (productDependency.productAction, containerDn)
		self._createOrganizationalRole(containerDn)
		
		dn = u'cn=%s,%s' % (productDependency.requiredProductId, containerDn)
		
		logger.info(u"Creating productDependency: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, productDependency, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(productDependency, dn)
			ldapObject.writeToDirectory(self._ldap)
		
	def productDependency_updateObject(self, productDependency):
		ConfigDataBackend.productDependency_updateObject(self, productDependency)
		
		dn = u'cn=%s,cn=%s,cn=productDependencies,cn=%s_%s-%s,%s' \
			% (productDependency.requiredProductId, productDependency.productAction, productDependency.productId, productDependency.productVersion, productDependency.packageVersion, self._productsContainerDn)
		logger.info(u"Updating ProductDependency: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, productDependency)
		
	def productDependency_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productDependency_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting productDependency, filter %s" % filter)
		dependencies = []
		
		if not filter.get('type'):
			filter['type'] = [ 'ProductDependency' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			dependencies.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return dependencies
	
	def productDependency_deleteObjects(self, productDependencies):
		ConfigDataBackend.productDependency_deleteObjects(self, productDependencies)
		
		for productDependency in forceObjectClassList(productDependencies, ProductDependency):
			dn = u'cn=%s,cn=%s,cn=productDependencies,cn=%s_%s-%s,%s' \
				% (productDependency.requiredProductId, productDependency.productAction, productDependency.productId, productDependency.productVersion, productDependency.packageVersion, self._productsContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting productDependency: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		ConfigDataBackend.productOnDepot_insertObject(self, productOnDepot)
		
		containerDn = u'cn=%s,%s' % (productOnDepot.depotId, self._productOnDepotsContainerDn)
		self._createOrganizationalRole(containerDn)
		
		dn = u'cn=%s,%s' % (productOnDepot.productId, containerDn)
		logger.info(u"Creating ProductOnDepot: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, productOnDepot, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(productOnDepot, dn)
			ldapObject.writeToDirectory(self._ldap)
	
	def productOnDepot_updateObject(self, productOnDepot):
		ConfigDataBackend.productOnDepot_updateObject(self, productOnDepot)
		
		dn = u'cn=%s,cn=%s,%s' % (productOnDepot.productId, productOnDepot.depotId, self._productOnDepotsContainerDn)
		logger.info(u"Updating ProductOnDepot: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, productOnDepot)
		
	def productOnDepot_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productOnDepot_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting productOnDepot, filter %s" % filter)
		products = []
		
		if not filter.get('type'):
			filter['type'] = [ 'ProductOnDepot' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productOnDepotsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			products.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return products
	
	def productOnDepot_deleteObjects(self, productOnDepots):
		ConfigDataBackend.productOnDepot_deleteObjects(self, productOnDepots)
		
		for productOnDepot in forceObjectClassList(productOnDepots, ProductOnDepot):
			dn = u'cn=%s,cn=%s,%s' % (productOnDepot.productId, productOnDepot.depotId, self._productOnDepotsContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting productOnDepot: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		ConfigDataBackend.productOnClient_insertObject(self, productOnClient)
		
		containerDn = u'cn=%s,%s' % (productOnClient.clientId, self._productOnClientsContainerDn)
		self._createOrganizationalRole(containerDn)
		
		dn = u'cn=%s,%s' % (productOnClient.productId, containerDn)
		logger.info(u"Creating ProductOnClient: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, productOnClient, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(productOnClient, dn)
			ldapObject.writeToDirectory(self._ldap)
		
	def productOnClient_updateObject(self, productOnClient):
		ConfigDataBackend.productOnClient_updateObject(self, productOnClient)
		
		dn = u'cn=%s,cn=%s,%s' % (productOnClient.productId, productOnClient.clientId, self._productOnClientsContainerDn)
		logger.info(u"Updating ProductOnClient: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, productOnClient)
	
	def productOnClient_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productOnClient_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting productOnClient, filter %s" % filter)
		products = []
		
		if not filter.get('type'):
			filter['type'] = [ 'ProductOnClient' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productOnClientsContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			products.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return products
		
	def productOnClient_deleteObjects(self, productOnClients):
		ConfigDataBackend.productOnClient_deleteObjects(self, productOnClients)
		
		for productOnClient in forceObjectClassList(productOnClients, ProductOnClient):
			dn = u'cn=%s,cn=%s,%s' % (productOnClient.productId, productOnClient.clientId, self._productOnClientsContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting productOnClient: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(self, productPropertyState):
		ConfigDataBackend.productPropertyState_insertObject(self, productPropertyState)
		hosts = self.host_getObjects( id = productPropertyState.objectId )
		if not hosts:
			raise BackendReferentialIntegrityError(u"Object '%s' does not exist" % productPropertyState.objectId)

		containerDn = u'cn=%s,%s' % (productPropertyState.objectId, self._productPropertyStatesContainerDn)
		self._createOrganizationalRole(containerDn)
		containerDn = u'cn=%s,%s' % (productPropertyState.productId, containerDn)
		self._createOrganizationalRole(containerDn)
		
		dn = u'cn=%s,%s' % (productPropertyState.propertyId, containerDn)
		logger.info(u"Creating ProductPropertyState: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, productPropertyState, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(productPropertyState, dn)
			ldapObject.writeToDirectory(self._ldap)
	
	def productPropertyState_updateObject(self, productPropertyState):
		ConfigDataBackend.productPropertyState_updateObject(self, productPropertyState)
		
		dn = u'cn=%s,cn=%s,cn=%s,%s' % (productPropertyState.propertyId, productPropertyState.productId, productPropertyState.objectId, self._productPropertyStatesContainerDn)
		logger.info(u"Updating ProductPropertyState: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, productOnClient)
	
	def productPropertyState_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productPropertyState_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting ProductPropertyState, filter %s" % filter)
		propertyStates = []
		
		if not filter.get('type'):
			filter['type'] = [ 'ProductPropertyState' ]
			
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, self._productPropertyStatesContainerDn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			propertyStates.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		return propertyStates
	
	def productPropertyState_deleteObjects(self, productPropertyStates):
		ConfigDataBackend.productPropertyState_deleteObjects(self, productPropertyStates)
		
		for productPropertyState in forceObjectClassList(productPropertyStates, ProductPropertyState):
			dn = u'cn=%s,cn=%s,cn=%s,%s' % (productPropertyState.propertyId, productPropertyState.productId, productPropertyState.objectId, self._productPropertyStatesContainerDn)
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting productPropertyState: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group):
		ConfigDataBackend.group_insertObject(self, group)
		
		dn = None
		if isinstance(group, HostGroup):
			dn = u'cn=%s,cn=hostGroups,%s' % (group.id, self._groupsContainerDn)
		else:
			dn = u'cn=%s,%s' % (group.id, self._groupsContainerDn)
		
		logger.info(u"Creating group: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if ldapObject.exists(self._ldap):
			self._updateLdapObject(ldapObject, group, updateWhereNone = True)
		else:
			ldapObject = self._opsiObjectToLdapObject(group, dn)
			ldapObject.writeToDirectory(self._ldap)
	
	def group_updateObject(self, group):
		ConfigDataBackend.group_updateObject(self, group)
		
		dn = None
		if isinstance(group, HostGroup):
			dn = u'cn=%s,cn=hostGroups,%s' % (group.id, self._groupsContainerDn)
		else:
			dn = u'cn=%s,%s' % (group.id, self._groupsContainerDn)
		
		logger.info(u"Updating group: %s" % dn)
		ldapObject = LDAPObject(dn)
		self._updateLdapObject(ldapObject, group)
	
	def group_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.group_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting groups, filter: %s" % filter)
		groups = []
		
		if not filter.get('type'):
			filter['type'] = [ 'Group', 'HostGroup' ]
		
		dn = self._groupsContainerDn
		ldapFilter = self._objectFilterToLDAPFilter(filter)
		
		search = LDAPObjectSearch(self._ldap, dn, filter=ldapFilter )
		for ldapObject in search.getObjects():
			groups.append( self._ldapObjectToOpsiObject(ldapObject, attributes, ignoreLdapAttributes = ['opsiMemberObjectId']) )
		return groups
	
	def group_deleteObjects(self, groups):
		ConfigDataBackend.group_deleteObjects(self, groups)
		
		for group in forceObjectClassList(groups, Group):
			dn = None
			if isinstance(group, HostGroup):
				dn = u'cn=%s,cn=hostGroups,%s' % (group.id, self._groupsContainerDn)
			else:
				dn = u'cn=%s,%s' % (group.id, self._groupsContainerDn)
			
			ldapObj = LDAPObject(dn)
			if ldapObj.exists(self._ldap):
				logger.info(u"Deleting group: %s" % dn)
				ldapObj.deleteFromDirectory(self._ldap, recursive = True)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup):
		ConfigDataBackend.objectToGroup_insertObject(self, objectToGroup)
		
		dn = None
		if not (objectToGroup.groupType == 'HostGroup'):
			dn = u'cn=%s,%s' % (objectToGroup.groupId, self._groupsContainerDn)
		else:
			dn = u'cn=%s,cn=hostGroups,%s' % (objectToGroup.groupId, self._groupsContainerDn)
		logger.info(u"Creating objectToGroup in group: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if not ldapObject.exists(self._ldap):
			raise BackendMissingDataError(u"Group '%s' not found" % dn)
		
		ldapObject.readFromDirectory(self._ldap)
		ldapObject.addAttributeValue('opsiMemberObjectId', objectToGroup.objectId)
		ldapObject.writeToDirectory(self._ldap)
		
		#containerDn = u'cn=%s,%s' % (objectToGroup.groupId, self._objectToGroupsContainerDn)
		#self._createOrganizationalRole(containerDn)
		#
		#dn = u'cn=%s,%s' % (objectToGroup.objectId, containerDn)
		#logger.info(u"Creating objectToGroup: %s" % dn)
		#
		#ldapObject = LDAPObject(dn)
		#if ldapObject.exists(self._ldap):
		#	self._updateLdapObject(ldapObject, objectToGroup, updateWhereNone = True)
		#else:
		#	ldapObject = self._opsiObjectToLdapObject(objectToGroup, dn)
		#	ldapObject.writeToDirectory(self._ldap)
	
	def objectToGroup_updateObject(self, objectToGroup):
		ConfigDataBackend.objectToGroup_updateObject(self, objectToGroup)
		
		dn = None
		if not (objectToGroup.groupType == 'HostGroup'):
			dn = u'cn=%s,%s' % (objectToGroup.groupId, self._groupsContainerDn)
		else:
			dn = u'cn=%s,cn=hostGroups,%s' % (objectToGroup.groupId, self._groupsContainerDn)
		logger.info(u"Updating objectToGroup in group: %s" % dn)
		
		ldapObject = LDAPObject(dn)
		if not ldapObject.exists(self._ldap):
			raise BackendMissingDataError(u"Group '%s' not found" % dn)
		
		ldapObject.readFromDirectory(self._ldap)
		ldapObject.addAttributeValue('opsiMemberObjectId', objectToGroup.objectId)
		ldapObject.writeToDirectory(self._ldap)
		
		#dn = u'cn=%s,cn=%s,%s' % (objectToGroup.objectId, objectToGroup.groupId, self._objectToGroupsContainerDn)
		#logger.info(u"Updating objectToGroup: %s" % dn)
		#ldapObject = LDAPObject(dn)
		#self._updateLdapObject(ldapObject, objectToGroup)
	
	def objectToGroup_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.objectToGroup_getObjects(self, attributes=[], **filter)
		
		logger.info(u"Getting objectToGroup, filter: %s" % filter)
		objectToGroups = []
		
		groupFilter = dict(filter)
		if not groupFilter.get('groupType'):
			groupFilter['groupType'] = [ 'Group', 'HostGroup' ]
		
		groupFilter['type'] = groupFilter['groupType']
		del groupFilter['groupType']
		
		if groupFilter.has_key('groupId'):
			groupFilter['id'] = groupFilter['groupId']
			del groupFilter['groupId']
		
		ldapFilter = self._objectFilterToLDAPFilter(groupFilter)
		search = LDAPObjectSearch(self._ldap, self._groupsContainerDn, filter=ldapFilter)
		for ldapObject in search.getObjects():
			ldapObject.readFromDirectory(self._ldap)
			groupId = ldapObject.getAttribute('opsiGroupId')
			groupType = None
			if 'opsiHostGroup' in ldapObject.getObjectClasses():
				groupType = 'HostGroup'
			else:
				raise Exception(u"Unhandled GroupType %s" % groupType) 
			for objectId in ldapObject.getAttribute('opsiMemberObjectId', default = [], valuesAsList = True):
				otg = ObjectToGroup(objectId = objectId, groupType = groupType, groupId = groupId)
				if self._objectHashMatches(otg.toHash(), **filter):
					objectToGroups.append( ObjectToGroup(objectId = objectId, groupType = groupType, groupId = groupId) )
		return objectToGroups
		
		#if not filter.get('type'):
		#	filter['type'] = [ 'ObjectToGroup' ]
		#
		#ldapFilter = self._objectFilterToLDAPFilter(filter)
		#
		#search = LDAPObjectSearch(self._ldap, self._objectToGroupsContainerDn, filter=ldapFilter )
		#for ldapObject in search.getObjects():
		#	objectToGroups.append( self._ldapObjectToOpsiObject(ldapObject, attributes) )
		#return objectToGroups
	
	def objectToGroup_deleteObjects(self, objectToGroups):
		ConfigDataBackend.objectToGroup_deleteObjects(self, objectToGroups)
		
		byTypeAndId = {}
		for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
			if not byTypeAndId.has_key(objectToGroup.groupType):
				byTypeAndId[objectToGroup.groupType] = {}
			if not byTypeAndId[objectToGroup.groupType].has_key(objectToGroup.groupId):
				byTypeAndId[objectToGroup.groupType][objectToGroup.groupId] = []
			byTypeAndId[objectToGroup.groupType][objectToGroup.groupId].append(objectToGroup.objectId)
		
		for (groupType, byId) in byTypeAndId.items():
			for (groupId, objectIds) in byId.items():
				dn = None
				if groupType == 'HostGroup':
					dn = u'cn=%s,cn=hostGroups,%s' % (groupId, self._groupsContainerDn)
				else:
					dn = u'cn=%s,%s' % (groupId, self._groupsContainerDn)
				ldapObj = LDAPObject(dn)
				if ldapObj.exists(self._ldap):
					ldapObj.readFromDirectory(self._ldap)
					newMembers = []
					for objectId in ldapObj.getAttribute('opsiMemberObjectId', default = [], valuesAsList = True):
						if not objectId in objectIds:
							newMembers.append(objectId)
					ldapObj.setAttribute('opsiMemberObjectId', newMembers)
					ldapObj.writeToDirectory(self._ldap)
				
		#for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
		#	dn = u'cn=%s,cn=%s,%s' % (objectToGroup.objectId, objectToGroup.groupId, self._objectToGroupsContainerDn)
		#	ldapObj = LDAPObject(dn)
		#	if ldapObj.exists(self._ldap):
		#		logger.info(u"Deleting objectToGroup: %s" % dn)
		#		ldapObj.deleteFromDirectory(self._ldap, recursive = True)



# ======================================================================================================
# =                                     CLASS LDAPOBJECT                                               =
# ======================================================================================================

class LDAPObject:
	''' This class handles ldap objects. '''
	
	def __init__(self, dn):
		if not dn:
			raise BackendBadValueError(u"Cannot create Object, dn not defined")
		self._dn = forceUnicode(dn)
		self._old = self._new = {}
		self._existsInBackend = False
	
	def getObjectClasses(self):
		return self.getAttribute('objectClass', default = [], valuesAsList = True)
	
	def addObjectClass(self, objectClass):
		try:
			self.addAttributeValue('objectClass', objectClass)
		except Exception, e:
			logger.warning(u"Failed to add objectClass '%s' to '%s': %s" % (objectClass, self.getDn(), e) )
		
	def removeObjectClass(self, objectClass):
		try:
			self.deleteAttributeValue('objectClass', objectClass)
		except Exception, e:
			logger.warning(u"Failed to delete objectClass '%s' from '%s': %s" % (objectClass, self.getDn(), e) )
	
	def getCn(self):
		return ( ldap.explode_dn(self._dn, notypes = 1) )[0]
	
	def getRdn(self):
		return ( ldap.explode_dn(self._dn, notypes = 0) )[0]
	
	def getDn(self):
		return self._dn
	
	def getContainerCn(self):
		return ( ldap.explode_dn(self._dn, notypes = 1) )[1]
	
	def exists(self, ldapSession):
		try:
			objectSearch = LDAPObjectSearch(ldapSession, self._dn, scope=ldap.SCOPE_BASE)
		except BackendMissingDataError:
			logger.debug(u"exists(): object '%s' does not exist" % self._dn)
			return False
		logger.debug(u"exists(): object '%s' does exist" % self._dn)
		return True
	
	def getContainer(self):
		return self.getParent()
	
	def getParent(self):
		parts = ( ldap.explode_dn(self._dn, notypes = 0) )[1:]
		if (parts <= 1):
			raise BackendBadValueError(u"Object '%s' has no parent" % self._dn)
		return LDAPObject(','.join(parts))
	
	def new(self, *objectClasses, **attributes):
		if ( len(objectClasses) <= 0 ):
			raise BackendBadValueError(u"No objectClasses defined!")
		
		self._new['objectClass'] = objectClasses
		self._new['cn'] = [ self.getCn() ]
		
		for (attribute, value) in attributes.items():
			self.setAttribute(attribute, value)
		
		logger.debug(u"Created new LDAP-Object: %s" % self._new)
			
	def deleteFromDirectory(self, ldapSession, recursive = False):
		if recursive:
			objects = []
			try:
				objectSearch = LDAPObjectSearch(ldapSession, self._dn, scope=ldap.SCOPE_ONELEVEL)
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
							filter     = u"(ObjectClass=*)",
							attributes = attributes )
		except Exception, e:
			raise BackendIOError(u"Cannot read object (dn: '%s') from ldap: %s" % (self._dn, e))
		
		self._existsInBackend = True
		self._old = result[0][1]
		# Copy the dict
		self._new = self._old.copy()
		# Copy the lists
		for attr in self._new:
			self._new[attr] = list(self._new[attr])

	def writeToDirectory(self, ldapSession):
		''' Writes the object to the ldap tree. '''
		logger.info(u"Writing object %s to directory" % self.getDn())
		if self._existsInBackend:
			if not self._readAllAttributes:
				raise BackendIOError(u"Not all attributes have been read from backend - not writing to backend!")
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
			if (values == [' ']):
				values = [u'']
			for i in range(len(values)):
				if   values[i] == 'TRUE':  self._new[key][i] = True
				elif values[i] == 'FALSE': self._new[key][i] = False
			if ( len(values) > 1 or valuesAsList):
				ret[key] = values
			else:
				ret[key] = values[0]
		return ret
		
	def getAttribute(self, attribute, default='DEFAULT_UNDEFINED', valuesAsList=False ):
		''' Get a specific attribute from object. 
		    Set valuesAsList to a boolean true value to get a list,
		    even if there is only one attribute value. '''
		if not self._new.has_key(attribute):
			if (default != 'DEFAULT_UNDEFINED'):
				return default
			raise BackendMissingDataError(u"Attribute '%s' does not exist" % attribute)
		values = self._new[attribute]
		if (values == [' ']):
			values = [u'']
		for i in range(len(values)):
			if   values[i] == 'TRUE':  values[i] = True
			elif values[i] == 'FALSE': values[i] = False
		if ( len(values) > 1 or valuesAsList):
			return values
		return values[0]
	
	def setAttribute(self, attribute, value):
		ldapValue = []
		if not value is None:
			value = forceList(value)
			for v in value:
				if type(v) is bool:
					if v: v = 'TRUE'
					else: v = 'FALSE'
				if (forceUnicode(v) == u''):
					v = u' '
				ldapValue.append(forceUnicode(v).encode('utf-8'))
		logger.debug(u"Setting attribute '%s' to '%s'" % (attribute, value))
		self._new[attribute] = ldapValue
	
	def addAttributeValue(self, attribute, value):
		''' Add a value to an object's attribute. '''
		values = forceList(self._new.get(attribute, []))
		if value in values:
			return
		values.append(value)
		self.setAttribute(attribute, values)
		
	def deleteAttributeValue(self, attribute, value):
		''' Delete a value from the list of attribute values. '''
		values = forceList(self._new.get(attribute, []))
		if not value in values:
			return
		values.remove(value)
		self.setAttribute(attribute, values)
	

# ======================================================================================================
# =                                  CLASS LDAPOBJECTSEARCH                                            =
# ======================================================================================================

class LDAPObjectSearch:
	''' This class simplifies object searchs. '''
	
	def __init__(self, ldapSession, baseDn='', scope=ldap.SCOPE_SUBTREE, filter=u'(ObjectClass=*)'):
		''' ObjectSearch constructor. '''
		
		if not baseDn:
			baseDn = ldapSession.baseDn
		filter = forceUnicode(filter)
		
		logger.info(u'Searching objects => baseDn: %s, scope: %s, filter: %s' % (baseDn, scope, filter))
		
		# Storage for matching DNs
		self._dns = []
		self._ldap = ldapSession
		
		# Execute search
		try:
			result = self._ldap.search( 	baseDn = baseDn,
							scope = scope,
							filter = filter,
							attributes = ['dn'] )
		except Exception, e:
			logger.debug(u'LDAPObjectSearch search error: %s' % e)
			raise
		
		logger.info(u'Search done, %d results' % len(result))
		for r in result:
			logger.debug(u'Found dn: %s' % r[0])
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
		objects = []
		for dn in self._dns:
			objects.append( LDAPObject(dn) )
		return objects
	
	def getLDAPObject(self):
		''' Returns the first object found as Object instance. '''
		if ( len(self._dns) <= 0 ):
			return None
		return LDAPObject(self._dns[0])

# ======================================================================================================
# =                                     CLASS LDAPSESSION                                              =
# ======================================================================================================	

class LDAPSession:
	''' This class handles the requests to a ldap server '''
	def __init__(self, **kwargs):
		''' Session constructor. '''
		self._address   = u'localhost'
		self._username  = u'cn=admin,dc=uib,dc=local'
		self._password  = u'opsi'
		self._referrals = True
		
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('address',):
				self._address = forceUnicode(value)
			elif option in ('username',):
				self._username = forceUnicode(value)
			elif option in ('password',):
				self._password = forceUnicode(value)
			elif option in ('referrals',):
				self._referrals = forceBool(value)
		
		self._commandCount = 0
		self._searchCount  = 0
		self._deleteCount  = 0
		self._addCount     = 0
		self._modifyCount  = 0
		
		self._ldap = None
	
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
		return {'total':  self._commandCount,
			'search': self._searchCount,
			'delete': self._deleteCount,
			'add':    self._addCount,
			'modify': self._modifyCount }
	
	def connect(self):
		''' Connect to a ldap server. '''
		self._ldap = ldap.open(self._address)
		self._ldap.protocol_version = ldap.VERSION3
		if self._referrals:
			self._ldap.set_option(ldap.OPT_REFERRALS, 1)
		else:
			self._ldap.set_option(ldap.OPT_REFERRALS, 0)
		try:
			self._ldap.bind_s(self._username, self._password, ldap.AUTH_SIMPLE)
			logger.info(u'Successfully connected to LDAP-Server.')
		except ldap.LDAPError, e:
			logger.error(u"Bind to LDAP failed: %s" % e)
			raise BackendIOError(u"Bind to LDAP server '%s' as '%s' failed: %s" % (self._address, self._username, e))
		
	def disconnect(self):
		''' Disconnect from ldap server '''
		if not self._ldap:
			return
		try:
			self._ldap.unbind()
		except Exception, e:
			pass
		
	def search(self, baseDn, scope, filter, attributes):
		''' This function is used to search in a ldap directory. '''
		self._commandCount += 1
		self._searchCount += 1
		logger.debug(u"Searching in baseDn: %s, scope: %s, filter: '%s', attributes: '%s' " \
					% (baseDn, scope, filter, attributes) )
		result = []
		try:
			try:
				result = self._ldap.search_s(baseDn, scope, filter, attributes)
			except ldap.LDAPError, e:
				if isinstance(e, ldap.SERVER_DOWN) or (e.__str__().lower().find('ldap connection invalid') != -1):
					# Possibly timed out
					logger.warning(u"LDAP connection possibly timed out: %s, trying to reconnect" % e)
					self.connect()
					result = self._ldap.search_s(baseDn, scope, filter, attributes)
				else:
					raise
		except Exception, e:
			logger.debug(u"LDAP search error %s: %s" % (e.__class__, e))
			if (e.__class__ == ldap.NO_SUCH_OBJECT):
				raise BackendMissingDataError(u"No results for search in baseDn: '%s', filter: '%s', scope: %s" \
					% (baseDn, filter, scope) )
			
			logger.critical(u"LDAP search error %s: %s" % (e.__class__, e))
			raise BackendIOError(u"Error searching in baseDn '%s', filter '%s', scope %s : %s" \
					% (baseDn, filter, scope, e) )
		if (result == []):
			logger.debug(u"No results for search in baseDn: '%s', filter: '%s', scope: %s" \
					% (baseDn, filter, scope) )
		return result
	
	def delete(self, dn):
		''' This function is used to delete an object in a ldap directory. '''
		self._commandCount += 1
		self._deleteCount += 1
		logger.debug(u"Deleting Object from LDAP, dn: '%s'" % dn)
		try:
			try:
				self._ldap.delete_s(dn)
			except ldap.LDAPError, e:
				if isinstance(e, ldap.SERVER_DOWN) or (e.__str__().lower().find('ldap connection invalid') != -1):
					# Possibly timed out
					logger.warning(u"LDAP connection possibly timed out: %s, trying to reconnect" % e)
					self.connect()
					self._ldap.delete_s(dn)
				else:
					raise
		except ldap.LDAPError, e:
			raise BackendIOError(e)
	
	def modifyByModlist(self, dn, old, new):
		''' This function is used to modify an object in a ldap directory. '''
		self._commandCount += 1
		self._modifyCount += 1
		
		logger.debug(u"[old]: %s" % old)
		logger.debug(u"[new]: %s" % new)
		attrs = ldap.modlist.modifyModlist(old,new)
		logger.debug(u"[change]: %s" % attrs)
		if (attrs == []):
			logger.debug(u"Object '%s' unchanged." % dn)
			return
		logger.debug(u"Modifying Object in LDAP, dn: '%s'" % dn)
		try:
			try:
				self._ldap.modify_s(dn,attrs)
			except ldap.LDAPError, e:
				if isinstance(e, ldap.SERVER_DOWN) or (e.__str__().lower().find('ldap connection invalid') != -1):
					# Possibly timed out
					logger.warning(u"LDAP connection possibly timed out: %s, trying to reconnect" % e)
					self.connect()
					self._ldap.modify_s(dn,attrs)
				else:
					raise
		except ldap.LDAPError, e:
			raise BackendIOError(e)
		except TypeError, e:
			raise BackendBadValueError(e)
		
		
	def addByModlist(self, dn, new):
		''' This function is used to add an object to the ldap directory. '''
		self._commandCount += 1
		self._addCount += 1
		
		attrs = ldap.modlist.addModlist(new)
		logger.debug(u"Adding Object to LDAP, dn: '%s'" % dn)
		logger.debug(u"attrs: '%s'" % attrs)
		try:
			try:
				self._ldap.add_s(dn,attrs)
			except ldap.LDAPError, e:
				if isinstance(e, ldap.SERVER_DOWN) or (e.__str__().lower().find('ldap connection invalid') != -1):
					# Possibly timed out
					logger.warning(u"LDAP connection possibly timed out: %s, trying to reconnect" % e)
					self.connect()
					self._ldap.add_s(dn,attrs)
				else:
					raise
		except ldap.LDAPError, e:
			raise BackendIOError(e)
		except TypeError, e:
			raise BackendBadValueError(e)










