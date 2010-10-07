#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Object    =
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

__version__ = '4.0'

# imports
import re, time, inspect, types
import copy as pycopy

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Util import deserialize, serialize, fromJson, toJson, generateOpsiHostKey, timestamp

# Get logger instance
logger = Logger()


mandatoryConstructorArgsCache = {}
def mandatoryConstructorArgs(Class):
	cacheKey = Class.__name__
	if mandatoryConstructorArgsCache.has_key(cacheKey):
		return mandatoryConstructorArgsCache[cacheKey]
	(args, varargs, varkwargs, defaults) = inspect.getargspec(Class.__init__)
	if not defaults:
		defaults = []
	last = -1*len(defaults)
	if (last == 0):
		last = len(args)
	mandatory = args[1:][:last]
	logger.debug2(u"mandatoryConstructorArgs for %s: %s" % (Class.__class__, mandatory))
	mandatoryConstructorArgsCache[cacheKey] = mandatory
	return mandatory

def getIdentAttributes(Class):
	return tuple(mandatoryConstructorArgs(Class))

def getForeignIdAttributes(Class):
	return Class.foreignIdAttributes
	
def getPossibleClassAttributes(Class):
	attributes = inspect.getargspec(Class.__init__)[0]
	for subClass in Class.subClasses.values():
		attributes.extend(inspect.getargspec(subClass.__init__)[0])
	attributes = list(set(attributes))
	attributes.remove('self')
	attributes.append('type')
	return attributes

def getBackendMethodPrefix(Class):
	return Class.backendMethodPrefix

def decodeIdent(Class, hash):
	if hash.has_key('ident') and hash['ident']:
		ident = {}
		if type(hash['ident']) is types.DictType:
			ident = hash['ident']
		else:
			identValues = []
			if   type(hash['ident']) in (str, unicode):
				identValues = hash['ident'].split(Class.identSeparator)
			elif type(hash['ident']) is (tuple, list):
				identValues = hash['ident']
			args = mandatoryConstructorArgs(Class)
			if (len(identValues) == len(args)):
				for i in range(len(args)):
					ident[args[i]] = identValues[i]
		del hash['ident']
		hash.update(ident)
	return hash
	
class BaseObject(object):
	subClasses = {}
	identSeparator = u';'
	foreignIdAttributes = []
	backendMethodPrefix = ''
	_isGeneratedDefault = False
	
	def getBackendMethodPrefix(self):
		return self.backendMethodPrefix
	
	def getForeignIdAttributes(self):
		return self.foreignIdAttributes
	
	def getIdentAttributes(self):
		return getIdentAttributes(self.__class__)
	
	def getIdent(self, returnType='unicode'):
		returnType = forceUnicodeLower(returnType)
		identAttributes = self.getIdentAttributes()
		identValues = []
		for attr in identAttributes:
			try:
				v = getattr(self, attr)
				if v is None:
					v = u''
			except AttributeError, e:
				v = u''
			identValues.append(forceUnicode(v))
		if returnType in ('list',):
			return identValues
		elif returnType in ('tuple',):
			return tuple(identValues)
		elif returnType in ('dict', 'hash'):
			ret = {}
			for i in range(len(identAttributes)):
				ret[identAttributes[i]] = identValues[i]
			return ret
		else:
			return self.identSeparator.join(identValues)
	
	def setDefaults(self):
		pass
	
	def emptyValues(self, keepAttributes = []):
		keepAttributes = forceUnicodeList(keepAttributes)
		for attribute in self.getIdentAttributes():
			if not attribute in keepAttributes:
				keepAttributes.append(attribute)
		keepAttributes.append('type')
		
		for attribute in self.__dict__.keys():
			if not attribute in keepAttributes:
				self.__dict__[attribute] = None
	
	def update(self, updateObject, updateWithNoneValues=True):
		if not issubclass(updateObject.__class__, self.__class__):
			raise Exception(u"Cannot update instance of %s with instance of %s" % (self.__class__.__name__, updateObject.__class__.__name__))
		hash = updateObject.toHash()
		if hash.has_key('type'):
			del hash['type']
		if not updateWithNoneValues:
			for (key, value) in hash.items():
				if value is None:
					del hash[key]
		self.__dict__.update(hash)
		
	def getType(self):
		return unicode(self.__class__.__name__)
	
	def setGeneratedDefault(self, flag = True):
		self._isGeneratedDefault = forceBool(flag)
		
	def isGeneratedDefault(self):
		return self._isGeneratedDefault
	
	def __unicode__(self):
		return u"<%s>" % self.getType()
	
	def toHash(self):
		# FIXME: Do we need deepcopy here? slow!
		#hash = pycopy.deepcopy(self.__dict__)
		hash = dict(self.__dict__)
		hash['type'] = self.getType()
		return hash
	
	def toJson(self):
		return toJson(self)
	
	def __eq__(self, other):
		if not isinstance(other, self.__class__):
			return False
		if self.isGeneratedDefault() or other.isGeneratedDefault():
			return False
		return (self.getIdent() == other.getIdent())
	
	def __unicode__(self):
		return u"<%s>" % (self.getType())
	
	def __str__(self):
		return self.__unicode__().encode("ascii", "replace")
	
	def __repr__(self):
		return self.__str__()
	
	
class Entity(BaseObject):
	subClasses = {}
	
	def setDefaults(self):
		BaseObject.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Entity'
		Class = eval(hash['type'])
		kwargs = {}
		decodeIdent(Class, hash)
		for varname in Class.__init__.func_code.co_varnames[1:]:
			if hash.has_key(varname):
				kwargs[varname] = hash[varname]
		return Class(**kwargs)
	
	def clone(self, identOnly = False):
		hash = {}
		if identOnly:
			identAttributes = self.getIdentAttributes()
			for (attribute, value) in self.toHash().items():
				if (attribute != 'type') and attribute not in self.getIdentAttributes():
					continue
				hash[attribute] = value
		else:
			hash = self.toHash()
		return self.fromHash(hash)
		
	def serialize(self):
		hash = self.toHash()
		hash['ident'] = self.getIdent()
		return hash
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Entity')
	
BaseObject.subClasses['Entity'] = Entity

class Relationship(BaseObject):
	subClasses = {}
	
	def setDefaults(self):
		BaseObject.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Relationship'
		Class = eval(hash['type'])
		kwargs = {}
		decodeIdent(Class, hash)
		for varname in Class.__init__.func_code.co_varnames[1:]:
			if hash.has_key(varname):
				kwargs[varname] = hash[varname]
		return Class(**kwargs)
	
	def clone(self, identOnly = False):
		hash = {}
		if identOnly:
			identAttributes = self.getIdentAttributes()
			for (attribute, value) in self.toHash().items():
				if (attribute != 'type') and attribute not in self.getIdentAttributes():
					continue
				hash[attribute] = value
		else:
			hash = self.toHash()
		return self.fromHash(hash)
	
	def serialize(self):
		hash = self.toHash()
		hash['type'] = self.getType()
		hash['ident'] = self.getIdent()
		return hash
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Relationship')
	
BaseObject.subClasses['Relationship'] = Relationship

class Object(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes + ['objectId']
	
	def __init__(self, id, description=None, notes=None):
		self.description = None
		self.notes = None
		self.setId(id)
		if not description is None:
			self.setDescription(description)
		if not notes is None:
			self.setNotes(notes)
	
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.description is None:
			self.setDescription(u"")
		if self.notes is None:
			self.setNotes(u"")
	
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceObjectId(id)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def getNotes(self):
		return self.notes
	
	def setNotes(self, notes):
		self.notes = forceUnicode(notes)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Object'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Object')
	
	def __unicode__(self):
		return u"<%s id '%s'>" % (self.getType(), self.id)

Entity.subClasses['Object'] = Object

class Host(Object):
	subClasses = {}
	foreignIdAttributes = Object.foreignIdAttributes + ['hostId']
	backendMethodPrefix = 'host'
	
	def __init__(self, id, description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None):
		Object.__init__(self, id, description, notes)
		self.hardwareAddress = None
		self.ipAddress = None
		self.inventoryNumber = None
		self.setId(id)
		if not hardwareAddress is None:
			self.setHardwareAddress(hardwareAddress)
		if not ipAddress is None:
			self.setIpAddress(ipAddress)
		if not inventoryNumber is None:
			self.setInventoryNumber(inventoryNumber)
		
	def setDefaults(self):
		Object.setDefaults(self)
		if self.inventoryNumber is None:
			self.setInventoryNumber(u"")
		
	def setId(self, id):
		self.id = forceHostId(id)
	
	def getHardwareAddress(self):
		return self.hardwareAddress
	
	def setHardwareAddress(self, hardwareAddress):
		self.hardwareAddress = forceHardwareAddress(hardwareAddress)
	
	def getIpAddress(self):
		return self.ipAddress
	
	def setIpAddress(self, ipAddress):
		self.ipAddress = forceIPAddress(ipAddress)
	
	def getInventoryNumber(self):
		return self.inventoryNumber
	
	def setInventoryNumber(self, inventoryNumber):
		self.inventoryNumber = forceUnicode(inventoryNumber)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Host'
		return Object.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Host')
	
	def __unicode__(self):
		return u"<%s id '%s'>" % (self.getType(), self.id)
	
Object.subClasses['Host'] = Host

class OpsiClient(Host):
	subClasses = {}
	foreignIdAttributes = Host.foreignIdAttributes + ['clientId']
	
	def __init__(self, id, opsiHostKey=None, description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, oneTimePassword = None, created=None, lastSeen=None):
		Host.__init__(self, id, description, notes, hardwareAddress, ipAddress, inventoryNumber)
		self.opsiHostKey = None
		self.created = None
		self.lastSeen = None
		self.oneTimePassword = None
		if not opsiHostKey is None:
			self.setOpsiHostKey(opsiHostKey)
		if not created is None:
			self.setCreated(created)
		if not lastSeen is None:
			self.setLastSeen(lastSeen)
		if not oneTimePassword is None:
			self.setOneTimePassword(oneTimePassword)
		
	def setDefaults(self):
		Host.setDefaults(self)
		if self.opsiHostKey is None:
			self.setOpsiHostKey(generateOpsiHostKey())
		if self.created is None:
			self.setCreated(timestamp())
	
	def getLastSeen(self):
		return self.lastSeen
	
	def setLastSeen(self, lastSeen):
		self.lastSeen = forceOpsiTimestamp(lastSeen)
	
	def getCreated(self):
		return self.created
	
	def setCreated(self, created):
		self.created = forceOpsiTimestamp(created)
	
	def getOpsiHostKey(self):
		return self.opsiHostKey
	
	def setOpsiHostKey(self, opsiHostKey):
		self.opsiHostKey = forceOpsiHostKey(opsiHostKey)
	
	def getOneTimePassword(self):
		return self.oneTimePassword
	
	def setOneTimePassword(self, oneTimePassword):
		self.oneTimePassword = forceUnicode(oneTimePassword)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'OpsiClient'
		return Host.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'OpsiClient')
	
	def __unicode__(self):
		return u"<%s id '%s'>" % (self.getType(), self.id)
	
Host.subClasses['OpsiClient'] = OpsiClient

class OpsiDepotserver(Host):
	subClasses = {}
	foreignIdAttributes = Host.foreignIdAttributes + ['depotId']
	
	def __init__(self, id, opsiHostKey=None, depotLocalUrl=None, depotRemoteUrl=None, depotWebdavUrl=None, repositoryLocalUrl=None, repositoryRemoteUrl=None,
		     description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, networkAddress=None, maxBandwidth=None,
		     isMasterDepot=None, masterDepotId=None):
		Host.__init__(self, id, description, notes, hardwareAddress, ipAddress, inventoryNumber)
		self.opsiHostKey = None
		self.depotLocalUrl = None
		self.depotRemoteUrl = None
		self.depotWebdavUrl = None
		self.repositoryLocalUrl = None
		self.repositoryRemoteUrl = None
		self.networkAddress = None
		self.maxBandwidth = None
		self.isMasterDepot = None
		self.masterDepotId = None
		if not opsiHostKey is None:
			self.setOpsiHostKey(opsiHostKey)
		if not depotLocalUrl is None:
			self.setDepotLocalUrl(depotLocalUrl)
		if not depotRemoteUrl is None:
			self.setDepotRemoteUrl(depotRemoteUrl)
		if not depotWebdavUrl is None:
			self.setDepotWebdavUrl(depotWebdavUrl)
		if not repositoryLocalUrl is None:
			self.setRepositoryLocalUrl(repositoryLocalUrl)
		if not repositoryRemoteUrl is None:
			self.setRepositoryRemoteUrl(repositoryRemoteUrl)
		if not networkAddress is None:
			self.setNetworkAddress(networkAddress)
		if not maxBandwidth is None:
			self.setMaxBandwidth(maxBandwidth)
		if not isMasterDepot is None:
			self.setIsMasterDepot(isMasterDepot)
		if not masterDepotId is None:
			self.setMasterDepotId(masterDepotId)
		
	def setDefaults(self):
		Host.setDefaults(self)
		if self.opsiHostKey is None:
			self.setOpsiHostKey(generateOpsiHostKey())
		if self.isMasterDepot is None:
			self.setIsMasterDepot(False)
		
	def getOpsiHostKey(self):
		return self.opsiHostKey
	
	def setOpsiHostKey(self, opsiHostKey):
		self.opsiHostKey = forceOpsiHostKey(opsiHostKey)
	
	def getDepotLocalUrl(self):
		return self.depotLocalUrl
	
	def setDepotLocalUrl(self, depotLocalUrl):
		self.depotLocalUrl = forceUrl(depotLocalUrl)
	
	def getDepotRemoteUrl(self):
		return self.depotRemoteUrl
	
	def setDepotWebdavUrl(self, depotWebdavUrl):
		self.depotWebdavUrl = forceUrl(depotWebdavUrl)
	
	def getDepotWebdavUrl(self):
		return self.depotWebdavUrl
	
	def setDepotRemoteUrl(self, depotRemoteUrl):
		self.depotRemoteUrl = forceUrl(depotRemoteUrl)
	
	def getRepositoryLocalUrl(self):
		return self.repositoryLocalUrl
	
	def setRepositoryLocalUrl(self, repositoryLocalUrl):
		self.repositoryLocalUrl = forceUrl(repositoryLocalUrl)
	
	def getRepositoryRemoteUrl(self):
		return self.repositoryRemoteUrl
	
	def setRepositoryRemoteUrl(self, repositoryRemoteUrl):
		self.repositoryRemoteUrl = forceUrl(repositoryRemoteUrl)
	
	def getNetworkAddress(self):
		return self.networkAddress
	
	def setNetworkAddress(self, networkAddress):
		self.networkAddress = forceNetworkAddress(networkAddress)
	
	def getMaxBandwidth(self):
		return self.maxBandwidth
	
	def setMaxBandwidth(self, maxBandwidth):
		self.maxBandwidth = forceInt(maxBandwidth)
	
	def setIsMasterDepot(self, isMasterDepot):
		self.isMasterDepot = forceBool(isMasterDepot)
	
	def getIsMasterDepot(self):
		return self.isMasterDepot
	
	def setMasterDepotId(self, masterDepotId):
		self.masterDepotId = forceHostId(masterDepotId)
	
	def getMasterDepotId(self):
		return self.masterDepotId
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'OpsiDepotserver'
		return Host.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'OpsiDepotserver')
	
	def __unicode__(self):
		return u"<%s id '%s'>" % (self.getType(), self.id)
	
Host.subClasses['OpsiDepotserver'] = OpsiDepotserver

class OpsiConfigserver(OpsiDepotserver):
	subClasses = {}
	foreignIdAttributes = OpsiDepotserver.foreignIdAttributes + ['serverId']
	
	def __init__(self, id, opsiHostKey=None, depotLocalUrl=None, depotRemoteUrl=None, depotWebdavUrl=None, repositoryLocalUrl=None, repositoryRemoteUrl=None,
		     description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, networkAddress=None, maxBandwidth=None,
		     isMasterDepot=None, masterDepotId=None):
		OpsiDepotserver.__init__(self, id, opsiHostKey, depotLocalUrl, depotRemoteUrl, depotWebdavUrl, repositoryLocalUrl, repositoryRemoteUrl,
		     description, notes, hardwareAddress, ipAddress, inventoryNumber, networkAddress, maxBandwidth, isMasterDepot, masterDepotId)
	
	def setDefaults(self):
		if self.isMasterDepot is None:
			self.setIsMasterDepot(True)
		OpsiDepotserver.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'OpsiConfigserver'
		return OpsiDepotserver.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'OpsiConfigserver')
	
OpsiDepotserver.subClasses['OpsiConfigserver'] = OpsiConfigserver
Host.subClasses['OpsiConfigserver'] = OpsiConfigserver

class Config(Entity):
	subClasses = {}
	foreignIdAttributes = Object.foreignIdAttributes + ['configId']
	backendMethodPrefix = 'config'
	
	def __init__(self, id, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		self.description = None
		self.possibleValues = None
		self.defaultValues = None
		self.editable = None
		self.multiValue = None
		
		self.setId(id)
		if not description is None:
			self.setDescription(description)
		if not possibleValues is None:
			self.setPossibleValues(possibleValues)
		if not defaultValues is None:
			self.setDefaultValues(defaultValues)
		if not editable is None:
			self.setEditable(editable)
		if not multiValue is None:
			self.setMultiValue(multiValue)
	
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.editable is None:
			self.editable = True
		if self.multiValue is None:
			self.multiValue = False
		if self.possibleValues is None:
			self.possibleValues = []
		if self.defaultValues is None:
			self.defaultValues = []
	
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceConfigId(id)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def _updateValues(self):
		if self.possibleValues is None:
			self.possibleValues = []
		if self.possibleValues and self.defaultValues:
			for defaultValue in self.defaultValues:
				if not defaultValue in self.possibleValues:
					self.defaultValues.remove(defaultValue)
		elif not self.possibleValues and self.defaultValues:
			self.possibleValues = self.defaultValues
		if self.defaultValues and (len(self.defaultValues) > 1):
			self.multiValue = True
		if not self.possibleValues is None:
			self.possibleValues.sort()
		if not self.defaultValues is None:
			self.defaultValues.sort()
		
	def getPossibleValues(self):
		return self.possibleValues
	
	def setPossibleValues(self, possibleValues):
		self.possibleValues = []
		# Remove duplicates
		for value in forceList(possibleValues):
			if not value in self.possibleValues:
				self.possibleValues.append(value)
		self._updateValues()
		
	def getDefaultValues(self):
		return self.defaultValues
	
	def setDefaultValues(self, defaultValues):
		self.defaultValues = []
		# Remove duplicates
		for value in forceList(defaultValues):
			if not value in self.defaultValues:
				self.defaultValues.append(value)
		self._updateValues()
	
	def getEditable(self):
		return self.editable
	
	def setEditable(self, editable):
		self.editable = forceBool(editable)
	
	def getMultiValue(self):
		return self.multiValue
	
	def setMultiValue(self, multiValue):
		self.multiValue = forceBool(multiValue)
		if not self.defaultValues is None and (len(self.defaultValues) > 1):
			self.multiValue = True
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Config'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Config')
	
	def __unicode__(self):
		return u"<%s id '%s'>" % (self.getType(), self.id)
	
Entity.subClasses['Config'] = Config

class UnicodeConfig(Config):
	subClasses = {}
	
	def __init__(self, id, description='', possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		Config.__init__(self, id, description, possibleValues, defaultValues, editable, multiValue)
		if not possibleValues is None:
			self.setPossibleValues(possibleValues)
		if not defaultValues is None:
			self.setDefaultValues(defaultValues)
		
	def setDefaults(self):
		if self.possibleValues is None:
			self.possibleValues = [u'']
		if self.defaultValues is None:
			self.defaultValues = [u'']
		Config.setDefaults(self)
		
	def setPossibleValues(self, possibleValues):
		Config.setPossibleValues(self, forceUnicodeList(possibleValues))
	
	def setDefaultValues(self, defaultValues):
		Config.setDefaultValues(self, forceUnicodeList(defaultValues))
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'UnicodeConfig'
		return Config.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'UnicodeConfig')
	
Config.subClasses['UnicodeConfig'] = UnicodeConfig

class BoolConfig(Config):
	subClasses = {}
	
	def __init__(self, id, description = None, defaultValues = None):
		Config.__init__(self, id, description, [ True, False ], defaultValues, False, False)
	
	def setDefaults(self):
		if self.defaultValues is None:
			self.defaultValues = [ False ]
		Config.setDefaults(self)
		
	def setPossibleValues(self, possibleValues):
		Config.setPossibleValues(self, [ True, False ])
	
	def setDefaultValues(self, defaultValues):
		defaultValues = forceBoolList(defaultValues)
		if (len(defaultValues) > 1):
			raise BackendBadValueError(u"Bool config cannot have multiple default values: %s" % defaultValues)
		Config.setDefaultValues(self, defaultValues)
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'BoolConfig'
		return Config.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'BoolConfig')
	
Config.subClasses['BoolConfig'] = BoolConfig

class ConfigState(Relationship):
	subClasses = {}
	backendMethodPrefix = 'configState'
	
	def __init__(self, configId, objectId, values=None):
		self.values = None
		self.setConfigId(configId)
		self.setObjectId(objectId)
		if not values is None:
			self.setValues(values)
	
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.values is None:
			self.setValues([])
	
	def getObjectId(self):
		return self.objectId
	
	def setObjectId(self, objectId):
		self.objectId = forceObjectId(objectId)
	
	def getConfigId(self):
		return self.configId
	
	def setConfigId(self, configId):
		self.configId = forceConfigId(configId)
	
	def getValues(self):
		return self.values
	
	def setValues(self, values):
		self.values = forceList(values)
		self.values.sort()
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ConfigState'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ConfigState')
	
	def __unicode__(self):
		return u"<%s configId '%s', objectId '%s'>" % (self.getType(), self.configId, self.objectId)

Relationship.subClasses['ConfigState'] = ConfigState

class Product(Entity):
	subClasses = {}
	foreignIdAttributes = Object.foreignIdAttributes + ['productId']
	backendMethodPrefix = 'product'
	
	def __init__(self, id, productVersion, packageVersion, name=None, licenseRequired=None,
		     setupScript=None, uninstallScript=None, updateScript=None, alwaysScript=None, onceScript=None, customScript=None, userLoginScript=None,
		     priority=None, description=None, advice=None, changelog=None, productClassIds=None, windowsSoftwareIds=None):
		self.name = None
		self.licenseRequired = None
		self.setupScript = None
		self.uninstallScript = None
		self.updateScript = None
		self.alwaysScript = None
		self.onceScript = None
		self.customScript = None
		self.userLoginScript = None
		self.priority = None
		self.description = None
		self.advice = None
		self.changelog = None
		self.productClassIds = None
		self.windowsSoftwareIds = None
		self.setId(id)
		self.setProductVersion(productVersion)
		self.setPackageVersion(packageVersion)
		if not name is None:
			self.setName(name)
		if not licenseRequired is None:
			self.setLicenseRequired(licenseRequired)
		if not setupScript is None:
			self.setSetupScript(setupScript)
		if not uninstallScript is None:
			self.setUninstallScript(uninstallScript)
		if not updateScript is None:
			self.setUpdateScript(updateScript)
		if not alwaysScript is None:
			self.setAlwaysScript(alwaysScript)
		if not onceScript is None:
			self.setOnceScript(onceScript)
		if not customScript is None:
			self.setCustomScript(customScript)
		if not userLoginScript is None:
			self.setUserLoginScript(userLoginScript)
		if not priority is None:
			self.setPriority(priority)
		if not description is None:
			self.setDescription(description)
		if not advice is None:
			self.setAdvice(advice)
		if not changelog is None:
			self.setChangelog(changelog)
		if not productClassIds is None:
			self.setProductClassIds(productClassIds)
		if not windowsSoftwareIds is None:
			self.setWindowsSoftwareIds(windowsSoftwareIds)
	
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.name is None:
			self.setName(u"")
		if self.licenseRequired is None:
			self.setLicenseRequired(False)
		if self.setupScript is None:
			self.setSetupScript(u"")
		if self.uninstallScript is None:
			self.setUninstallScript(u"")
		if self.updateScript is None:
			self.setUpdateScript(u"")
		if self.alwaysScript is None:
			self.setAlwaysScript(u"")
		if self.onceScript is None:
			self.setOnceScript(u"")
		if self.customScript is None:
			self.setCustomScript(u"")
		if self.userLoginScript is None:
			self.setUserLoginScript(u"")
		if self.priority is None:
			self.setPriority(0)
		if self.description is None:
			self.setDescription(u"")
		if self.advice is None:
			self.setAdvice(u"")
		if self.changelog is None:
			self.setChangelog(u"")
		if self.productClassIds is None:
			self.setProductClassIds([])
		if self.windowsSoftwareIds is None:
			self.setWindowsSoftwareIds([])
		
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceProductId(id)
	
	def getProductVersion(self):
		return self.productVersion
	
	def setProductVersion(self, productVersion):
		self.productVersion = forceProductVersion(productVersion)
	
	def getPackageVersion(self):
		return self.packageVersion
	
	def setPackageVersion(self, packageVersion):
		self.packageVersion = forcePackageVersion(packageVersion)
	
	def getName(self):
		return self.name
	
	def setName(self, name):
		self.name = forceUnicode(name)
	
	def getLicenseRequired(self):
		return self.licenseRequired
	
	def setLicenseRequired(self, licenseRequired):
		self.licenseRequired = forceBool(licenseRequired)
	
	def getSetupScript(self):
		return self.setupScript
	
	def setSetupScript(self, setupScript):
		self.setupScript = forceFilename(setupScript)
	
	def getUninstallScript(self):
		return self.uninstallScript
	
	def setUninstallScript(self, uninstallScript):
		self.uninstallScript = forceFilename(uninstallScript)
	
	def getUpdateScript(self):
		return self.updateScript
	
	def setUpdateScript(self, updateScript):
		self.updateScript = forceFilename(updateScript)
	
	def getAlwaysScript(self):
		return self.alwaysScript
	
	def setAlwaysScript(self, alwaysScript):
		self.alwaysScript = forceFilename(alwaysScript)
	
	def getOnceScript(self):
		return self.onceScript
	
	def setOnceScript(self, onceScript):
		self.onceScript = forceFilename(onceScript)
	
	def getCustomScript(self):
		return self.customScript
	
	def setCustomScript(self, customScript):
		self.customScript = forceFilename(customScript)
	
	def getUserLoginScript(self):
		return self.userLoginScript
	
	def setUserLoginScript(self, userLoginScript):
		self.userLoginScript = forceFilename(userLoginScript)
	
	def getPriority(self):
		return self.priority
	
	def setPriority(self, priority):
		self.priority = forceProductPriority(priority)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def getAdvice(self):
		return self.advice
	
	def setAdvice(self, advice):
		self.advice = forceUnicode(advice)
	
	def getChangelog(self):
		return self.changelog
	
	def setChangelog(self, changelog):
		self.changelog = forceUnicode(changelog)
	
	def getProductClassIds(self):
		return self.productClassIds
	
	def setProductClassIds(self, productClassIds):
		self.productClassIds = forceUnicodeList(productClassIds)
		self.productClassIds.sort()
		
	def getWindowsSoftwareIds(self):
		return self.windowsSoftwareIds
	
	def setWindowsSoftwareIds(self, windowsSoftwareIds):
		self.windowsSoftwareIds = forceUnicodeList(windowsSoftwareIds)
		self.windowsSoftwareIds.sort()
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Product'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Product')
	
	def __unicode__(self):
		return u"<%s id '%s', name '%s'>" % (self.getType(), self.id, self.name)
	
Entity.subClasses['Product'] = Product

class LocalbootProduct(Product):
	subClasses = {}
	
	def __init__(self, id, productVersion, packageVersion, name=None, licenseRequired=None,
		     setupScript=None, uninstallScript=None, updateScript=None, alwaysScript=None, onceScript=None, customScript=None, userLoginScript=None,
		     priority=None, description=None, advice=None, changelog=None, productClassIds=None, windowsSoftwareIds=None):
		Product.__init__(self, id, productVersion, packageVersion, name, licenseRequired,
		     setupScript, uninstallScript, updateScript, alwaysScript, onceScript, customScript, userLoginScript,
		     priority, description, advice, changelog, productClassIds, windowsSoftwareIds)
	
	def setDefaults(self):
		Product.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'LocalbootProduct'
		return Product.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'LocalbootProduct')
	
Product.subClasses['LocalbootProduct'] = LocalbootProduct

class NetbootProduct(Product):
	subClasses = {}
	
	def __init__(self, id, productVersion, packageVersion, name=None, licenseRequired=None,
		     setupScript=None, uninstallScript=None, updateScript=None, alwaysScript=None, onceScript=None, customScript=None,
		     priority=None, description=None, advice=None, changelog=None, productClassIds=None, windowsSoftwareIds=None,
		     pxeConfigTemplate=u''):
		Product.__init__(self, id, productVersion, packageVersion, name, licenseRequired,
		     setupScript, uninstallScript, updateScript, alwaysScript, onceScript, customScript, None,
		     priority, description, advice, changelog, productClassIds, windowsSoftwareIds)
		self.setPxeConfigTemplate(pxeConfigTemplate)
	
	def setDefaults(self):
		Product.setDefaults(self)
	
	def getPxeConfigTemplate(self):
		return self.pxeConfigTemplate
	
	def setPxeConfigTemplate(self, pxeConfigTemplate):
		if pxeConfigTemplate:
			self.pxeConfigTemplate = forceFilename(pxeConfigTemplate)
		else:
			self.pxeConfigTemplate = None
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'NetbootProduct'
		return Product.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'NetbootProduct')
	
Product.subClasses['NetbootProduct'] = NetbootProduct

class ProductProperty(Entity):
	subClasses = {}
	backendMethodPrefix = 'productProperty'
	
	def __init__(self, productId, productVersion, packageVersion, propertyId, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		self.description = None
		self.possibleValues = None
		self.defaultValues = None
		self.editable = None
		self.multiValue = None
		self.setProductId(productId)
		self.setProductVersion(productVersion)
		self.setPackageVersion(packageVersion)
		self.setPropertyId(propertyId)
		if not description is None:
			self.setDescription(description)
		if not possibleValues is None:
			self.setPossibleValues(possibleValues)
		if not defaultValues is None:
			self.setDefaultValues(defaultValues)
		if not editable is None:
			self.setEditable(editable)
		if not multiValue is None:
			self.setMultiValue(multiValue)
	
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.description is None:
			self.setDescription(u"")
		if self.possibleValues is None:
			self.setPossibleValues([])
		if self.defaultValues is None:
			self.setDefaultValues([])
		if self.editable is None:
			self.setEditable(True)
		if self.multiValue is None:
			self.setMultiValue(False)
		
	def getProductId(self):
		return self.productId
	
	def setProductId(self, productId):
		self.productId = forceProductId(productId)
	
	def getProductVersion(self):
		return self.productVersion
	
	def setProductVersion(self, productVersion):
		self.productVersion = forceProductVersion(productVersion)
	
	def getPackageVersion(self):
		return self.packageVersion
	
	def setPackageVersion(self, packageVersion):
		self.packageVersion = forcePackageVersion(packageVersion)
	
	def getPropertyId(self):
		return self.propertyId
	
	def setPropertyId(self, propertyId):
		self.propertyId = forceProductPropertyId(propertyId)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def _updateValues(self):
		if self.possibleValues is None:
			self.possibleValues = []
		if self.possibleValues and self.defaultValues:
			for defaultValue in self.defaultValues:
				if not defaultValue in self.possibleValues:
					self.defaultValues.remove(defaultValue)
		elif not self.possibleValues and self.defaultValues:
			self.possibleValues = self.defaultValues
		if self.defaultValues and (len(self.defaultValues) > 1):
			self.multiValue = True
		if not self.possibleValues is None:
			self.possibleValues.sort()
		if not self.defaultValues is None:
			self.defaultValues.sort()
		
	def getPossibleValues(self):
		return self.possibleValues
	
	def setPossibleValues(self, possibleValues):
		self.possibleValues = []
		# Remove duplicates
		for value in forceList(possibleValues):
			if not value in self.possibleValues:
				self.possibleValues.append(value)
		self._updateValues()
		
	def getDefaultValues(self):
		return self.defaultValues
	
	def setDefaultValues(self, defaultValues):
		self.defaultValues = []
		# Remove duplicates
		for value in forceList(defaultValues):
			if not value in self.defaultValues:
				self.defaultValues.append(value)
		self._updateValues()
		
	def getEditable(self):
		return self.editable
	
	def setEditable(self, editable):
		self.editable = forceBool(editable)
	
	def getMultiValue(self):
		return self.multiValue
	
	def setMultiValue(self, multiValue):
		self.multiValue = forceBool(multiValue)
		if not self.defaultValues is None and (len(self.defaultValues) > 1):
			self.multiValue = True
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ProductProperty'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ProductProperty')
	
	def __unicode__(self):
		return u"<%s productId '%s', productVersion '%s', packageVersion '%s', propertyId '%s'>" \
			% (self.getType(), self.productId, self.productVersion, self.packageVersion, self.propertyId)
	
Entity.subClasses['ProductProperty'] = ProductProperty

class UnicodeProductProperty(ProductProperty):
	subClasses = {}
	
	def __init__(self, productId, productVersion, packageVersion, propertyId, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		ProductProperty.__init__(self, productId, productVersion, packageVersion, propertyId, description, possibleValues, defaultValues, editable, multiValue)
		self.possibleValues = None
		self.defaultValues = None
		if not possibleValues is None:
			self.setPossibleValues(possibleValues)
		if not defaultValues is None:
			self.setDefaultValues(defaultValues)
	
	def setDefaults(self):
		if self.possibleValues is None:
			self.possibleValues = [u'']
		if self.defaultValues is None:
			self.defaultValues = [u'']
		ProductProperty.setDefaults(self)
	
	def setPossibleValues(self, possibleValues):
		ProductProperty.setPossibleValues(self, forceUnicodeList(possibleValues))
	
	def setDefaultValues(self, defaultValues):
		ProductProperty.setDefaultValues(self, forceUnicodeList(defaultValues))
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'UnicodeProductProperty'
		return ProductProperty.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'UnicodeProductProperty')
	
ProductProperty.subClasses['UnicodeProductProperty'] = UnicodeProductProperty

class BoolProductProperty(ProductProperty):
	subClasses = {}
	
	def __init__(self, productId, productVersion, packageVersion, propertyId, description=None, defaultValues=None):
		ProductProperty.__init__(self, productId, productVersion, packageVersion, propertyId, description, [ True, False ], defaultValues, False, False)
		if not self.defaultValues is None and (len(self.defaultValues) > 1):
			raise BackendBadValueError(u"Bool product property cannot have multiple default values: %s" % self.defaultValues)
	
	def setDefaults(self):
		if self.defaultValues is None:
			self.defaultValues = [ False ]
		ProductProperty.setDefaults(self)
	
	def setPossibleValues(self, possibleValues):
		ProductProperty.setPossibleValues(self, [ True, False ])
	
	def setDefaultValues(self, defaultValues):
		defaultValues = forceBoolList(defaultValues)
		if (len(defaultValues) > 1):
			raise BackendBadValueError(u"Bool config cannot have multiple default values: %s" % defaultValues)
		ProductProperty.setDefaultValues(self, defaultValues)
	
	def setEditable(self, editable):
		self.editable = False
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'BoolProductProperty'
		return ProductProperty.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'BoolProductProperty')
	
ProductProperty.subClasses['BoolProductProperty'] = BoolProductProperty

class ProductDependency(Relationship):
	subClasses = {}
	backendMethodPrefix = 'productDependency'
	
	def __init__(self, productId, productVersion, packageVersion, productAction, requiredProductId, requiredProductVersion=None, requiredPackageVersion=None, requiredAction=None, requiredInstallationStatus=None, requirementType=None):
		self.requiredProductVersion = None
		self.requiredPackageVersion = None
		self.requiredAction = None
		self.requiredInstallationStatus = None
		self.requirementType = None
		self.setProductId(productId)
		self.setProductVersion(productVersion)
		self.setPackageVersion(packageVersion)
		self.setProductAction(productAction)
		self.setRequiredProductId(requiredProductId)
		if not requiredProductVersion is None:
			self.setRequiredProductVersion(requiredProductVersion)
		if not requiredPackageVersion is None:
			self.setRequiredPackageVersion(requiredPackageVersion)
		if not requiredAction is None:
			self.setRequiredAction(requiredAction)
		if not requiredInstallationStatus is None:
			self.setRequiredInstallationStatus(requiredInstallationStatus)
		if not requirementType is None:
			self.setRequirementType(requirementType)
	
	def setDefaults(self):
		Relationship.setDefaults(self)
	
	def getProductId(self):
		return self.productId
	
	def setProductId(self, productId):
		self.productId = forceProductId(productId)
	
	def getProductVersion(self):
		return self.productVersion
	
	def setProductVersion(self, productVersion):
		self.productVersion = forceProductVersion(productVersion)
	
	def getPackageVersion(self):
		return self.packageVersion
	
	def setPackageVersion(self, packageVersion):
		self.packageVersion = forcePackageVersion(packageVersion)
	
	def getProductAction(self):
		return self.productAction
	
	def setProductAction(self, productAction):
		self.productAction = forceActionRequest(productAction)
	
	def getRequiredProductId(self):
		return self.requiredProductId
	
	def setRequiredProductId(self, requiredProductId):
		self.requiredProductId = forceProductId(requiredProductId)
	
	def getRequiredProductVersion(self):
		return self.requiredProductVersion
	
	def setRequiredProductVersion(self, requiredProductVersion):
		self.requiredProductVersion = forceProductVersion(requiredProductVersion)
	
	def getRequiredPackageVersion(self):
		return self.requiredPackageVersion
	
	def setRequiredPackageVersion(self, requiredPackageVersion):
		self.requiredPackageVersion = forcePackageVersion(requiredPackageVersion)
	
	def getRequiredAction(self):
		return self.requiredAction
	
	def setRequiredAction(self, requiredAction):
		self.requiredAction = forceActionRequest(requiredAction)
	
	def getRequiredInstallationStatus(self):
		return self.requiredInstallationStatus
	
	def setRequiredInstallationStatus(self, requiredInstallationStatus):
		self.requiredInstallationStatus = forceInstallationStatus(requiredInstallationStatus)
	
	def getRequirementType(self):
		return self.requirementType
	
	def setRequirementType(self, requirementType):
		self.requirementType = forceRequirementType(requirementType)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ProductDependency'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ProductDependency')
	
	def __unicode__(self):
		return u"<%s productId '%s', productVersion '%s', packageVersion '%s', productAction '%s', requiredProductId '%s'>" \
			% (self.getType(), self.productId, self.productVersion, self.packageVersion, self.productAction, self.requiredProductId)
	
Relationship.subClasses['ProductDependency'] = ProductDependency

class ProductOnDepot(Relationship):
	subClasses = {}
	backendMethodPrefix = 'productOnDepot'
	
	def __init__(self, productId, productType, productVersion, packageVersion, depotId, locked=None):
		self.locked = None
		self.setProductId(productId)
		self.setProductType(productType)
		self.setProductVersion(productVersion)
		self.setPackageVersion(packageVersion)
		self.setDepotId(depotId)
		if not locked is None:
			self.setLocked(locked)
	
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.locked is None:
			self.setLocked(False)
	
	def getProductId(self):
		return self.productId
	
	def setProductId(self, productId):
		self.productId = forceProductId(productId)
	
	def getProductType(self):
		return self.productType
	
	def setProductType(self, productType):
		self.productType = forceProductType(productType)
	
	def getProductVersion(self):
		return self.productVersion
	
	def setProductVersion(self, productVersion):
		self.productVersion = forceProductVersion(productVersion)
	
	def getPackageVersion(self):
		return self.packageVersion
	
	def setPackageVersion(self, packageVersion):
		self.packageVersion = forcePackageVersion(packageVersion)
	
	def getDepotId(self):
		return self.depotId
	
	def setDepotId(self, depotId):
		self.depotId = forceHostId(depotId)
	
	def getLocked(self):
		return self.locked
	
	def setLocked(self, locked):
		self.locked = forceBool(locked)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ProductOnDepot'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ProductOnDepot')
	
	def __unicode__(self):
		return u"<%s productId '%s', depotId '%s'>" \
			% (self.getType(), self.productId, self.depotId)
	
Relationship.subClasses['ProductOnDepot'] = ProductOnDepot


class ProductOnClient(Relationship):
	subClasses = {}
	backendMethodPrefix = 'productOnClient'
	
	def __init__(self, productId, productType, clientId, targetConfiguration=None, installationStatus=None, actionRequest=None, lastAction=None, actionProgress=None, actionResult=None, productVersion=None, packageVersion=None, modificationTime=None, actionSequence=None):
		self.targetConfiguration = None
		self.installationStatus = None
		self.actionRequest = None
		self.lastAction = None
		self.actionProgress = None
		self.actionResult = None
		self.productVersion = None
		self.packageVersion = None
		self.modificationTime = None
		self.actionSequence = -1
		self.setProductId(productId)
		self.setProductType(productType)
		self.setClientId(clientId)
		if not targetConfiguration is None:
			self.setTargetConfiguration(targetConfiguration)
		if not installationStatus is None:
			self.setInstallationStatus(installationStatus)
		if not actionRequest is None:
			self.setActionRequest(actionRequest)
		if not lastAction is None:
			self.setLastAction(lastAction)
		if not actionProgress is None:
			self.setActionProgress(actionProgress)
		if not actionResult is None:
			self.setActionResult(actionResult)
		if not productVersion is None:
			self.setProductVersion(productVersion)
		if not packageVersion is None:
			self.setPackageVersion(packageVersion)
		if not modificationTime is None:
			self.setModificationTime(modificationTime)
		if not actionSequence is None:
			self.setActionSequence(actionSequence)
		
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.installationStatus is None:
			self.setInstallationStatus('not_installed')
		if self.actionRequest is None:
			self.setActionRequest('none')
		if self.modificationTime is None:
			self.setModificationTime(timestamp())
		
	def getProductId(self):
		return self.productId
	
	def setProductId(self, productId):
		self.productId = forceProductId(productId)
	
	def getProductType(self):
		return self.productType
	
	def setProductType(self, productType):
		self.productType = forceProductType(productType)
	
	def getClientId(self):
		return self.clientId
	
	def setClientId(self, clientId):
		self.clientId = forceHostId(clientId)
	
	def getTargetConfiguration(self):
		return self.targetConfiguration
	
	def setTargetConfiguration(self, targetConfiguration):
		self.targetConfiguration = forceProductTargetConfiguration(targetConfiguration)
	
	def getInstallationStatus(self):
		return self.installationStatus
	
	def setInstallationStatus(self, installationStatus):
		self.installationStatus = forceInstallationStatus(installationStatus)
	
	def getActionRequest(self):
		return self.actionRequest
	
	def setActionRequest(self, actionRequest):
		self.actionRequest = forceActionRequest(actionRequest)
	
	def getActionProgress(self):
		return self.actionProgress
	
	def setActionProgress(self, actionProgress):
		self.actionProgress = forceActionProgress(actionProgress)
	
	def getLastAction(self):
		return self.lastAction
	
	def setLastAction(self, lastAction):
		self.lastAction = forceActionRequest(lastAction)
	
	def getActionResult(self):
		return self.actionResult
	
	def setActionResult(self, actionResult):
		self.actionResult = forceActionResult(actionResult)
		
	def getProductVersion(self):
		return self.productVersion
	
	def setProductVersion(self, productVersion):
		self.productVersion = forceProductVersion(productVersion)
		
	def getPackageVersion(self):
		return self.packageVersion
	
	def setPackageVersion(self, packageVersion):
		self.packageVersion = forcePackageVersion(packageVersion)
	
	def getModificationTime(self):
		return self.modificationTime
	
	def setModificationTime(self, modificationTime):
		self.modificationTime = forceOpsiTimestamp(modificationTime)
	
	def getActionSequence(self):
		return self.actionSequence
	
	def setActionSequence(self, actionSequence):
		self.actionSequence = forceInt(actionSequence)
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ProductOnClient'
		return Relationship.fromHash(hash)

	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ProductOnClient')
	
	def __unicode__(self):
		return u"<%s clientId '%s', productId '%s', installationStatus '%s', actionRequest '%s'>" \
			% (self.getType(), self.clientId, self.productId, self.installationStatus, self.actionRequest)
	
Relationship.subClasses['ProductOnClient'] = ProductOnClient

class ProductPropertyState(Relationship):
	subClasses = {}
	backendMethodPrefix = 'productPropertyState'
	
	def __init__(self, productId, propertyId, objectId, values=None):
		self.values = None
		self.setProductId(productId)
		self.setPropertyId(propertyId)
		self.setObjectId(objectId)
		if not values is None:
			self.setValues(values)
	
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.values is None:
			self.setValues([])
	
	def getProductId(self):
		return self.productId
	
	def setProductId(self, productId):
		self.productId = forceProductId(productId)
	
	def getObjectId(self):
		return self.objectId
	
	def setObjectId(self, objectId):
		self.objectId = forceObjectId(objectId)
	
	def getPropertyId(self):
		return self.propertyId
	
	def setPropertyId(self, propertyId):
		self.propertyId = forceProductPropertyId(propertyId)
	
	def getValues(self):
		return self.values
	
	def setValues(self, values):
		self.values = forceList(values)
		self.values.sort()
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ProductPropertyState'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ProductPropertyState')
	
	def __unicode__(self):
		return u"<%s productId '%s', propertyId '%s', objectId '%s'>" \
			% (self.getType(), self.productId, self.propertyId, self.objectId)
	
Relationship.subClasses['ProductPropertyState'] = ProductPropertyState

class Group(Object):
	subClasses = {}
	foreignIdAttributes = Object.foreignIdAttributes + ['groupId']
	backendMethodPrefix = 'group'
	
	def __init__(self, id, description=None, notes=None, parentGroupId=None):
		Object.__init__(self, id, description, notes)
		self.parentGroupId = None
		self.setId(id)
		if not parentGroupId is None:
			self.setParentGroupId(parentGroupId)
	
	def setDefaults(self):
		Object.setDefaults(self)
	
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceGroupId(id)
	
	def getParentGroupId(self):
		return self.parentGroupId
	
	def setParentGroupId(self, parentGroupId):
		self.parentGroupId = forceGroupId(parentGroupId)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'Group'
		return Object.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'Group')
	
	def __unicode__(self):
		return u"<%s id '%s', parentGroupId '%s'>" % (self.getType(), self.id, self.parentGroupId)
	
Object.subClasses['Group'] = Group

class HostGroup(Group):
	subClasses = {}
	
	def __init__(self, id, description=None, notes=None, parentGroupId=None):
		Group.__init__(self, id, description, notes, parentGroupId)
	
	def setDefaults(self):
		Group.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'HostGroup'
		return Group.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'HostGroup')
	
Group.subClasses['HostGroup'] = HostGroup

class ObjectToGroup(Relationship):
	subClasses = {}
	backendMethodPrefix = 'objectToGroup'
	
	def __init__(self, groupType, groupId, objectId):
		self.setGroupType(groupType)
		self.setGroupId(groupId)
		self.setObjectId(objectId)
	
	def setDefaults(self):
		Relationship.setDefaults(self)
	
	def getGroupType(self):
		return self.groupType
	
	def setGroupType(self, groupType):
		self.groupType = forceGroupType(groupType)
	
	def getGroupId(self):
		return self.groupId
	
	def setGroupId(self, groupId):
		self.groupId = forceGroupId(groupId)
	
	def getObjectId(self):
		return self.objectId
	
	def setObjectId(self, objectId):
		self.objectId = forceObjectId(objectId)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ObjectToGroup'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ObjectToGroup')
	
	def __unicode__(self):
		return u"<%s groupType '%s', groupId '%s', objectId '%s'>" \
			% (self.getType(), self.groupType, self.groupId, self.objectId)
	
Relationship.subClasses['ObjectToGroup'] = ObjectToGroup


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -   License management                                                                        -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
class LicenseContract(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes + ['licenseContractId']
	backendMethodPrefix = 'licenseContract'
	
	def __init__(self, id, description=None, notes=None, partner=None, conclusionDate=None, notificationDate=None, expirationDate=None):
		self.description = None
		self.notes = None
		self.partner = None
		self.conclusionDate = None
		self.notificationDate = None
		self.expirationDate = None
		self.setId(id)
		if not description is None:
			self.setDescription(description)
		if not notes is None:
			self.setNotes(notes)
		if not partner is None:
			self.setPartner(partner)
		if not conclusionDate is None:
			self.setConclusionDate(conclusionDate)
		if not notificationDate is None:
			self.setNotificationDate(notificationDate)
		if not conclusionDate is None:
			self.setExpirationDate(expirationDate)
	
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.description is None:
			self.setDescription(u"")
		if self.notes is None:
			self.setNotes(u"")
		if self.partner is None:
			self.setPartner(u"")
		if self.conclusionDate is None:
			self.setConclusionDate(timestamp())
		if self.notificationDate is None:
			self.setNotificationDate('0000-00-00 00:00:00')
		if self.expirationDate is None:
			self.setExpirationDate('0000-00-00 00:00:00')
		
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceLicenseContractId(id)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def getNotes(self):
		return self.notes
	
	def setNotes(self, notes):
		self.notes = forceUnicode(notes)
	
	def getPartner(self):
		return self.partner
	
	def setPartner(self, partner):
		self.partner = forceUnicode(partner)
	
	def getConclusionDate(self):
		return self.conclusionDate
	
	def setConclusionDate(self, conclusionDate):
		self.conclusionDate = forceOpsiTimestamp(conclusionDate)
	
	def getNotificationDate(self):
		return self.notificationDate
	
	def setNotificationDate(self, notificationDate):
		self.notificationDate = forceOpsiTimestamp(notificationDate)
	
	def getExpirationDate(self):
		return self.expirationDate
	
	def setExpirationDate(self, expirationDate):
		self.expirationDate = forceOpsiTimestamp(expirationDate)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'LicenseContract'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'LicenseContract')
	
	def __unicode__(self):
		return u"<%s id '%s', description '%s'>" \
			% (self.getType(), self.id, self.description)
	
Entity.subClasses['LicenseContract'] = LicenseContract

class SoftwareLicense(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes + ['softwareLicenseId']
	backendMethodPrefix = 'softwareLicense'
	
	def __init__(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		self.maxInstallations = None
		self.boundToHost = None
		self.expirationDate = None
		self.setId(id)
		self.setLicenseContractId(licenseContractId)
		if not maxInstallations is None:
			self.setMaxInstallations(maxInstallations)
		if not boundToHost is None:
			self.setBoundToHost(boundToHost)
		if not expirationDate is None:
			self.setExpirationDate(expirationDate)
		
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.maxInstallations is None:
			self.setMaxInstallations(1)
		if self.expirationDate is None:
			self.setExpirationDate('0000-00-00 00:00:00')
		
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceSoftwareLicenseId(id)
	
	def getLicenseContractId(self):
		return self.licenseContractId
	
	def setLicenseContractId(self, licenseContractId):
		self.licenseContractId = forceLicenseContractId(licenseContractId)
	
	def getMaxInstallations(self):
		return self.maxInstallations
	
	def setMaxInstallations(self, maxInstallations):
		self.maxInstallations = forceUnsignedInt(maxInstallations)
	
	def getBoundToHost(self):
		return self.boundToHost
	
	def setBoundToHost(self, boundToHost):
		self.boundToHost = forceHostId(boundToHost)
	
	def getExpirationDate(self):
		return self.expirationDate
	
	def setExpirationDate(self, expirationDate):
		self.expirationDate = forceOpsiTimestamp(expirationDate)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'SoftwareLicense'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'SoftwareLicense')
	
	def __unicode__(self):
		return u"<%s id '%s', licenseContractId '%s'>" \
			% (self.getType(), self.id, self.licenseContractId)
	
Entity.subClasses['LicenseContract'] = LicenseContract

class RetailSoftwareLicense(SoftwareLicense):
	subClasses = {}
	
	def __init__(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		SoftwareLicense.__init__(self, id, licenseContractId, maxInstallations, boundToHost, expirationDate)
		
	def setDefaults(self):
		SoftwareLicense.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'RetailSoftwareLicense'
		return SoftwareLicense.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'RetailSoftwareLicense')
	
SoftwareLicense.subClasses['RetailSoftwareLicense'] = RetailSoftwareLicense

class OEMSoftwareLicense(SoftwareLicense):
	subClasses = {}
	
	def __init__(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		SoftwareLicense.__init__(self, id, licenseContractId, 1, boundToHost, expirationDate)
		
	def setDefaults(self):
		SoftwareLicense.setDefaults(self)
	
	def setMaxInstallations(self, maxInstallations):
		maxInstallations = forceUnsignedInt(maxInstallations)
		if (maxInstallations > 1):
			raise BackendBadValueError(u"OEM software license max installations can only be set to 1")
		self.maxInstallations = maxInstallations
	
	def setBoundToHost(self, boundToHost):
		self.boundToHost = forceHostId(boundToHost)
		if not self.boundToHost:
			raise BackendBadValueError("OEM software license requires boundToHost value")
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'OEMSoftwareLicense'
		return SoftwareLicense.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'OEMSoftwareLicense')
	
SoftwareLicense.subClasses['OEMSoftwareLicense'] = OEMSoftwareLicense

class VolumeSoftwareLicense(SoftwareLicense):
	subClasses = {}
	
	def __init__(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		SoftwareLicense.__init__(self, id, licenseContractId, maxInstallations, boundToHost, expirationDate)
	
	def setDefaults(self):
		SoftwareLicense.setDefaults(self)
		if self.maxInstallations is None:
			self.setMaxInstallations(1)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'VolumeSoftwareLicense'
		return SoftwareLicense.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'VolumeSoftwareLicense')
	
SoftwareLicense.subClasses['VolumeSoftwareLicense'] = VolumeSoftwareLicense

class ConcurrentSoftwareLicense(SoftwareLicense):
	subClasses = {}
	
	def __init__(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		SoftwareLicense.__init__(self, id, licenseContractId, maxInstallations, boundToHost, expirationDate)
	
	def setDefaults(self):
		SoftwareLicense.setDefaults(self)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'ConcurrentSoftwareLicense'
		return SoftwareLicense.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'ConcurrentSoftwareLicense')
	
SoftwareLicense.subClasses['ConcurrentSoftwareLicense'] = ConcurrentSoftwareLicense

class LicensePool(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes + ['licensePoolId']
	backendMethodPrefix = 'licensePool'
	
	def __init__(self, id, description=None, productIds=None):
		self.description = None
		self.productIds = None
		self.setId(id)
		if not description is None:
			self.setDescription(description)
		if not productIds is None:
			self.setProductIds(productIds)
		
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.description is None:
			self.setDescription(u"")
		if self.productIds is None:
			self.setProductIds([])
		
	def getId(self):
		return self.id
	
	def setId(self, id):
		self.id = forceLicensePoolId(id)
	
	def getDescription(self):
		return self.description
	
	def setDescription(self, description):
		self.description = forceUnicode(description)
	
	def getProductIds(self):
		return self.productIds
	
	def setProductIds(self, productIds):
		self.productIds = forceProductIdList(productIds)
		self.productIds.sort()
		
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'LicensePool'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'LicensePool')
	
	def __unicode__(self):
		return u"<%s id '%s', description '%s'>" \
			% (self.getType(), self.id, self.description)
	
Entity.subClasses['LicensePool'] = LicensePool

class AuditSoftwareToLicensePool(Relationship):
	subClasses = {}
	
	def __init__(self, name, version, subVersion, language, architecture, licensePoolId):
		self.setName(name)
		self.setVersion(version)
		self.setSubVersion(subVersion)
		self.setLanguage(language)
		self.setArchitecture(architecture)
		self.setLicensePoolId(licensePoolId)
	
	def getLicensePoolId(self):
		return self.licensePoolId
	
	def setLicensePoolId(self, licensePoolId):
		self.licensePoolId = forceLicensePoolId(licensePoolId)
	
	def setName(self, name):
		self.name = forceUnicode(name)
	
	def getName(self):
		return self.name
	
	def setVersion(self, version):
		if not version:
			self.version = u''
		else:
			self.version = forceUnicodeLower(version)
	
	def getVersion(self):
		return self.version
	
	def setSubVersion(self, subVersion):
		if not subVersion:
			self.subVersion = u''
		else:
			self.subVersion = forceUnicodeLower(subVersion)
	
	def getSubVersion(self):
		return self.subVersion
	
	def setLanguage(self, language):
		if not language:
			self.language = u''
		else:
			self.language = forceLanguageCode(language)
	
	def getLanguage(self):
		return self.language
	
	def setArchitecture(self, architecture):
		if not architecture:
			self.architecture = u''
		else:
			self.architecture = forceArchitecture(architecture)
	
	def getArchitecture(self):
		return self.architecture
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'AuditSoftwareToLicensePool'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'AuditSoftwareToLicensePool')
	
	def __unicode__(self):
		return u"<%s licensePoolId '%s', name '%s'>" \
			% (self.getType(), self.licensePoolId, self.name)
	
Relationship.subClasses['AuditSoftwareToLicensePool'] = AuditSoftwareToLicensePool

class SoftwareLicenseToLicensePool(Relationship):
	subClasses = {}
	
	def __init__(self, softwareLicenseId, licensePoolId, licenseKey = None):
		self.licenseKey = None
		self.setSoftwareLicenseId(softwareLicenseId)
		self.setLicensePoolId(licensePoolId)
		if not licenseKey is None:
			self.setLicenseKey(licenseKey)
		
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.licenseKey is None:
			self.setLicenseKey(u'')
	
	def getSoftwareLicenseId(self):
		return self.softwareLicenseId
	
	def setSoftwareLicenseId(self, softwareLicenseId):
		self.softwareLicenseId = forceSoftwareLicenseId(softwareLicenseId)
	
	def getLicensePoolId(self):
		return self.licensePoolId
	
	def setLicensePoolId(self, licensePoolId):
		self.licensePoolId = forceLicensePoolId(licensePoolId)
	
	def getLicenseKey(self):
		return self.licenseKey
	
	def setLicenseKey(self, licenseKey):
		self.licenseKey = forceUnicodeLower(licenseKey)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'SoftwareLicenseToLicensePool'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'SoftwareLicenseToLicensePool')
	
	def __unicode__(self):
		return u"<%s softwareLicenseId '%s', licensePoolId '%s'>" \
			% (self.getType(), self.softwareLicenseId, self.licensePoolId)
	
Relationship.subClasses['SoftwareLicenseToLicensePool'] = SoftwareLicenseToLicensePool

class LicenseOnClient(Relationship):
	subClasses = {}
	backendMethodPrefix = 'licenseOnClient'
	
	def __init__(self, softwareLicenseId, licensePoolId, clientId, licenseKey=None, notes=None):
		self.licenseKey = None
		self.notes = None
		self.setSoftwareLicenseId(softwareLicenseId)
		self.setLicensePoolId(licensePoolId)
		self.setClientId(clientId)
		if not licenseKey is None:
			self.setLicenseKey(licenseKey)
		if not notes is None:
			self.setNotes(notes)
		
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.licenseKey is None:
			self.setLicenseKey(u'')
		if self.notes is None:
			self.setNotes(u'')
		
	def getSoftwareLicenseId(self):
		return self.softwareLicenseId
	
	def setSoftwareLicenseId(self, softwareLicenseId):
		self.softwareLicenseId = forceSoftwareLicenseId(softwareLicenseId)
	
	def getLicensePoolId(self):
		return self.licensePoolId
	
	def setLicensePoolId(self, licensePoolId):
		self.licensePoolId = forceLicensePoolId(licensePoolId)
	
	def getClientId(self):
		return self.clientId
	
	def setClientId(self, clientId):
		self.clientId = forceHostId(clientId)
	
	def getLicenseKey(self):
		return self.licenseKey
	
	def setLicenseKey(self, licenseKey):
		self.licenseKey = forceUnicodeLower(licenseKey)
	
	def getNotes(self):
		return self.notes
	
	def setNotes(self, notes):
		self.notes = forceUnicode(notes)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'LicenseOnClient'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'LicenseOnClient')
	
	def __unicode__(self):
		return u"<%s softwareLicenseId '%s', licensePoolId '%s', clientId '%s'>" \
			% (self.getType(), self.softwareLicenseId, self.licensePoolId, self.clientId)
	
Relationship.subClasses['LicenseOnClient'] = LicenseOnClient




class AuditSoftware(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes
	backendMethodPrefix = 'auditSoftware'
	
	def __init__(self, name, version, subVersion, language, architecture, windowsSoftwareId=None, windowsDisplayName=None, windowsDisplayVersion=None, installSize=None):
		self.windowsSoftwareId = None
		self.windowsDisplayName = None
		self.windowsDisplayVersion = None
		self.installSize = None
		self.setName(name)
		self.setVersion(version)
		self.setSubVersion(subVersion)
		self.setLanguage(language)
		self.setArchitecture(architecture)
		if not windowsSoftwareId is None:
			self.setWindowsSoftwareId(windowsSoftwareId)
		if not windowsDisplayName is None:
			self.setWindowsDisplayName(windowsDisplayName)
		if not windowsDisplayVersion is None:
			self.setWindowsDisplayVersion(windowsDisplayVersion)
		if not installSize is None:
			self.setInstallSize(installSize)
		
	def setDefaults(self):
		Entity.setDefaults(self)
		if self.installSize is None:
			self.setInstallSize(0)
		
	def setName(self, name):
		self.name = forceUnicode(name)
	
	def getName(self):
		return self.name
	
	def setVersion(self, version):
		if not version:
			self.version = u''
		else:
			self.version = forceUnicodeLower(version)
	
	def getVersion(self):
		return self.version
	
	def setSubVersion(self, subVersion):
		if not subVersion:
			self.subVersion = u''
		else:
			self.subVersion = forceUnicodeLower(subVersion)
	
	def getSubVersion(self):
		return self.subVersion
	
	def setLanguage(self, language):
		if not language:
			self.language = u''
		else:
			self.language = forceLanguageCode(language)
	
	def getLanguage(self):
		return self.language
	
	def setArchitecture(self, architecture):
		if not architecture:
			self.architecture = u''
		else:
			self.architecture = forceArchitecture(architecture)
	
	def getArchitecture(self):
		return self.architecture
	
	def getWindowsSoftwareId(self):
		return self.windowsSoftwareId
	
	def setWindowsSoftwareId(self, windowsSoftwareId):
		self.windowsSoftwareId = forceUnicodeLower(windowsSoftwareId)
	
	def getWindowsDisplayName(self):
		return self.windowsDisplayName
	
	def setWindowsDisplayName(self, windowsDisplayName):
		self.windowsDisplayName = forceUnicode(windowsDisplayName)
	
	def getWindowsDisplayVersion(self):
		return self.windowsDisplayVersion
	
	def setWindowsDisplayVersion(self, windowsDisplayVersion):
		self.windowsDisplayVersion = forceUnicode(windowsDisplayVersion)
	
	def getInstallSize(self):
		return self.installSize
	
	def setInstallSize(self, installSize):
		self.installSize = forceInt(installSize)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'AuditSoftware'
		return Entity.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'AuditSoftware')
	
	def __unicode__(self):
		return u"<%s name '%s', version '%s', subVersion '%s', language '%s', architecture '%s'>" \
			% (self.getType(), self.name, self.version, self.subVersion, self.language, self.architecture)
	
Entity.subClasses['AuditSoftware'] = AuditSoftware


class AuditSoftwareOnClient(Relationship):
	subClasses = {}
	backendMethodPrefix = 'auditSoftwareOnClient'
	def __init__(self, name, version, subVersion, language, architecture, clientId, uninstallString=None, binaryName=None, firstseen=None, lastseen=None, state=None, usageFrequency=None, lastUsed=None, licenseKey=None):
		self.uninstallString = None
		self.binaryName = None
		self.firstseen = None
		self.lastseen = None
		self.state = None
		self.usageFrequency = None
		self.lastUsed = None
		self.licenseKey = None
		self.setName(name)
		self.setVersion(version)
		self.setSubVersion(subVersion)
		self.setLanguage(language)
		self.setArchitecture(architecture)
		self.setClientId(clientId)
		if not uninstallString is None:
			self.setUninstallString(uninstallString)
		if not binaryName is None:
			self.setBinaryName(binaryName)
		if not firstseen is None:
			self.setFirstseen(firstseen)
		if not lastseen is None:
			self.setLastseen(lastseen)
		if not state is None:
			self.setState(state)
		if not usageFrequency is None:
			self.setUsageFrequency(usageFrequency)
		if not lastUsed is None:
			self.setLastUsed(lastUsed)
		if not licenseKey is None:
			self.setLicenseKey(licenseKey)
		
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.uninstallString is None:
			self.setUninstallString(u"")
		if self.binaryName is None:
			self.setBinaryName(u"")
		if self.firstseen is None:
			self.setFirstseen(timestamp())
		if self.lastseen is None:
			self.setLastseen(timestamp())
		if self.state is None:
			self.setState(1)
		if self.usageFrequency is None:
			self.setUsageFrequency(-1)
		if self.lastUsed is None:
			self.setLastUsed('0000-00-00 00:00:00')
	
	def setName(self, name):
		self.name = forceUnicode(name)
	
	def getName(self):
		return self.name
	
	def setVersion(self, version):
		self.version = forceUnicodeLower(version)
	
	def getVersion(self):
		return self.version
	
	def setSubVersion(self, subVersion):
		self.subVersion = forceUnicodeLower(subVersion)
	
	def getSubVersion(self):
		return self.subVersion
	
	def setLanguage(self, language):
		if not language:
			self.language = u''
		else:
			self.language = forceLanguageCode(language)
	
	def getLanguage(self):
		return self.language
	
	def setArchitecture(self, architecture):
		if not architecture:
			self.architecture = u''
		else:
			self.architecture = forceArchitecture(architecture)
	
	def getArchitecture(self):
		return self.architecture
	
	def getClientId(self):
		return self.clientId
	
	def setClientId(self, clientId):
		self.clientId = forceHostId(clientId)
	
	def getUninstallString(self):
		return self.uninstallString
	
	def setUninstallString(self, uninstallString):
		self.uninstallString = forceUnicode(uninstallString)
	
	def getBinaryName(self):
		return self.binaryName
	
	def setBinaryName(self, binaryName):
		self.binaryName = forceUnicode(binaryName)
	
	def getFirstseen(self):
		return self.firstseen
	
	def setFirstseen(self, firstseen):
		self.firstseen = forceOpsiTimestamp(firstseen)
	
	def getLastseen(self):
		return self.firstseen
	
	def setLastseen(self, lastseen):
		self.lastseen = forceOpsiTimestamp(lastseen)
	
	def getState(self):
		return self.state
	
	def setState(self, state):
		self.state = forceAuditState(state)
	
	def getUsageFrequency(self):
		return self.usageFrequency
	
	def setUsageFrequency(self, usageFrequency):
		self.usageFrequency = forceInt(usageFrequency)
	
	def getLastUsed(self):
		return self.lastUsed
	
	def setLastUsed(self, lastUsed):
		self.lastUsed = forceOpsiTimestamp(lastUsed)
	
	def getLicenseKey(self):
		return self.licenseKey
	
	def setLicenseKey(self, licenseKey):
		self.licenseKey = forceUnicodeLower(licenseKey)
	
	@staticmethod
	def fromHash(hash):
		if not hash.has_key('type'): hash['type'] = 'AuditSoftwareOnClient'
		return Relationship.fromHash(hash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'AuditSoftwareOnClient')
	
	def __unicode__(self):
		return u"<%s name '%s', version '%s', subVersion '%s', language '%s', architecture '%s', clientId '%s'>" \
			% (self.getType(), self.name, self.version, self.subVersion, self.language, self.architecture, self.clientId)
	
Relationship.subClasses['AuditSoftwareOnClient'] = AuditSoftwareOnClient




class AuditHardware(Entity):
	subClasses = {}
	foreignIdAttributes = Entity.foreignIdAttributes
	backendMethodPrefix = 'auditHardware'
	hardwareAttributes = {}
	
	def __init__(self, hardwareClass, **kwargs):
		self.setHardwareClass(hardwareClass)
		for attribute in self.hardwareAttributes.get(hardwareClass, {}).keys():
			if not kwargs.has_key(attribute):
				if kwargs.has_key(attribute.lower()):
					kwargs[attribute] = kwargs[attribute.lower()]
					del kwargs[attribute.lower()]
				else:
					kwargs[attribute] = None
		
		if self.hardwareAttributes.get(hardwareClass):
			for (attribute, value) in kwargs.items():
				attrType = self.hardwareAttributes[hardwareClass].get(attribute)
				if not attrType:
					del kwargs[attribute]
					continue
				if value is None:
					continue
				if attrType.startswith('varchar'):
					kwargs[attribute] = forceUnicode(value)
					size = 0
					try:
						size = int(attrType.split('(')[1].split(')')[0].strip())
					except:
						pass
					if size and (len(kwargs[attribute]) > size):
						logger.warning(u'Truncating value of attribute %s of hardware class %s to length %d' % (attribute, hardwareClass, size))
						kwargs[attribute] = kwargs[attribute][:size].rstrip()
				elif (attrType.find('int') != -1):
					try:
						kwargs[attribute] = forceInt(value)
					except Exception, e:
						logger.debug2(e)
						kwargs[attribute] = None
				elif (attrType == 'double'):
					try:
						kwargs[attribute] = forceFloat(value)
					except Exception, e:
						logger.debug2(e)
						kwargs[attribute] = None
				else:
					raise BackendConfigurationError(u"Attribute '%s' of hardware class '%s' has unknown type '%s'" % (attribute, hardwareClass, type))
		else:
			for (attribute, value) in kwargs.items():
				if type(value) is str:
					kwargs[attribute] = forceUnicode(value)
		
		self.__dict__.update(kwargs)
		
		if hasattr(self, 'vendorId') and self.vendorId:
			self.vendorId = forceHardwareVendorId(self.vendorId)
		if hasattr(self, 'subsystemVendorId') and self.subsystemVendorId:
			self.subsystemVendorId = forceHardwareVendorId(self.subsystemVendorId)
		if hasattr(self, 'deviceId') and self.deviceId:
			self.deviceId = forceHardwareDeviceId(self.deviceId)
		if hasattr(self, 'subsystemDeviceId') and self.subsystemDeviceId:
			self.subsystemDeviceId = forceHardwareDeviceId(self.subsystemDeviceId)
		
	@staticmethod
	def setHardwareConfig(hardwareConfig):
		hardwareAttributes = {}
		for config in hardwareConfig:
			hwClass = config['Class']['Opsi']
			hardwareAttributes[hwClass] = {}
			for value in config['Values']:
				if (value["Scope"] == 'g'):
					hardwareAttributes[hwClass][value['Opsi']] = value["Type"]
		AuditHardware.hardwareAttributes = hardwareAttributes
	
	def setDefaults(self):
		Entity.setDefaults(self)
		
	def setHardwareClass(self, hardwareClass):
		self.hardwareClass = forceUnicode(hardwareClass)
	
	def getHardwareClass(self):
		return self.hardwareClass
	
	def getIdentAttributes(self):
		attributes = self.hardwareAttributes.get(self.hardwareClass, {}).keys()
		attributes.sort()
		attributes.insert(0, 'hardwareClass')
		return attributes
		
	def serialize(self):
		hash = self.toHash()
		return hash
	
	@staticmethod
	def fromHash(hash):
		initHash = {}
		for (k, v) in hash.items():
			if (k == 'type'):
				continue
			if type(k) is unicode:
				k = str(k)
			initHash[k] = v
		return AuditHardware(**initHash)
	
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'AuditHardware')
	
	def __unicode__(self):
		res = u"<%s" % self.getType()
		hardwareClass = self.getHardwareClass()
		if hardwareClass:
			res += u", hardwareClass '%s'" % hardwareClass
		if hasattr(self, 'name'):
			res += u", name '%s'" % self.name
		return res + u">"
	
Entity.subClasses['AuditHardware'] = AuditHardware


class AuditHardwareOnHost(Relationship):
	subClasses = {}
	backendMethodPrefix = 'auditHardwareOnHost'
	hardwareAttributes = {}
	
	def __init__(self, hardwareClass, hostId, firstseen=None, lastseen=None, state=None, **kwargs):
		self.firstseen = None
		self.lastseen = None
		self.state = None
		self.setHostId(hostId)
		self.setHardwareClass(hardwareClass)
		for attribute in self.hardwareAttributes.get(hardwareClass, {}).keys():
			if not kwargs.has_key(attribute):
				if kwargs.has_key(attribute.lower()):
					kwargs[attribute] = kwargs[attribute.lower()]
					del kwargs[attribute.lower()]
				else:
					kwargs[attribute] = None
		
		
		if self.hardwareAttributes.get(hardwareClass):
			for (attribute, value) in kwargs.items():
				attrType = self.hardwareAttributes[hardwareClass].get(attribute)
				if not attrType:
					del kwargs[attribute]
					continue
				if value is None:
					continue
				if attrType.startswith('varchar'):
					kwargs[attribute] = forceUnicode(value)
					size = 0
					try:
						size = int(attrType.split('(')[1].split(')')[0].strip())
					except:
						pass
					if size and (len(kwargs[attribute]) > size):
						logger.warning(u'Truncating value of attribute %s of hardware class %s to length %d' % (attribute, hardwareClass, size))
						kwargs[attribute] = kwargs[attribute][:size].rstrip()
				elif (attrType.find('int') != -1):
					try:
						kwargs[attribute] = forceInt(value)
					except Exception, e:
						logger.debug2(e)
						kwargs[attribute] = None
				elif (attrType == 'double'):
					try:
						kwargs[attribute] = forceFloat(value)
					except Exception, e:
						logger.debug2(e)
						kwargs[attribute] = None
				else:
					raise BackendConfigurationError(u"Attribute '%s' of hardware class '%s' has unknown type '%s'" % (attribute, hardwareClass, type))
		else:
			for (attribute, value) in kwargs.items():
				if type(value) is str:
					kwargs[attribute] = forceUnicode(value)
		
		self.__dict__.update(kwargs)
		if not firstseen is None:
			self.setFirstseen(firstseen)
		if not lastseen is None:
			self.setLastseen(lastseen)
		if not state is None:
			self.setState(state)
		
		if hasattr(self, 'vendorId') and self.vendorId:
			self.vendorId = forceHardwareVendorId(self.vendorId)
		if hasattr(self, 'subsystemVendorId') and self.subsystemVendorId:
			self.subsystemVendorId = forceHardwareVendorId(self.subsystemVendorId)
		if hasattr(self, 'deviceId') and self.deviceId:
			self.deviceId = forceHardwareDeviceId(self.deviceId)
		if hasattr(self, 'subsystemDeviceId') and self.subsystemDeviceId:
			self.subsystemDeviceId = forceHardwareDeviceId(self.subsystemDeviceId)

		
	@staticmethod
	def setHardwareConfig(hardwareConfig):
		hardwareAttributes = {}
		for config in hardwareConfig:
			hwClass = config['Class']['Opsi']
			hardwareAttributes[hwClass] = {}
			for value in config['Values']:
				hardwareAttributes[hwClass][value['Opsi']] = value["Type"]
		AuditHardwareOnHost.hardwareAttributes = hardwareAttributes
	
	def setDefaults(self):
		Relationship.setDefaults(self)
		if self.firstseen is None:
			self.setFirstseen(timestamp())
		if self.lastseen is None:
			self.setLastseen(timestamp())
		if self.state is None:
			self.setState(1)
	
	def getHostId(self):
		return self.hostId
	
	def setHostId(self, hostId):
		self.hostId = forceHostId(hostId)
	
	def setHardwareClass(self, hardwareClass):
		self.hardwareClass = forceUnicode(hardwareClass)
	
	def getHardwareClass(self):
		return self.hardwareClass
	
	def getFirstseen(self):
		return self.firstseen
	
	def setFirstseen(self, firstseen):
		self.firstseen = forceOpsiTimestamp(firstseen)
	
	def getLastseen(self):
		return self.firstseen
	
	def setLastseen(self, lastseen):
		self.lastseen = forceOpsiTimestamp(lastseen)
	
	def getState(self):
		return self.state
	
	def setState(self, state):
		self.state = forceAuditState(state)
	
	def toAuditHardware(self):
		auditHardwareHash = { 'type': 'AuditHardware' }
		attributes = AuditHardware.hardwareAttributes.get(self.getHardwareClass(), {}).keys()
		
		for (attribute, value) in self.toHash():
			if (attribute == 'type'):
				continue
			if attribute in ('hardwareClass',):
				auditHardwareHash[attribute] = value
				continue
			if attribute in attributes:
				auditHardwareHash[attribute] = value
		
		return AuditHardware.fromHash(auditHardwareHash)
		
	def getIdentAttributes(self):
		attributes = self.hardwareAttributes.get(self.hardwareClass, {}).keys()
		attributes.sort()
		attributes.insert(0, 'hostId')
		attributes.insert(0, 'hardwareClass')
		return attributes
	
	def serialize(self):
		hash = self.toHash()
		#hash['ident'] = self.getIdent()
		return hash
	
	@staticmethod
	def fromHash(hash):
		initHash = {}
		for (k, v) in hash.items():
			if (k == 'type'):
				continue
			if type(k) is unicode:
				k = str(k)
			initHash[k] = v
		return AuditHardwareOnHost(**initHash)
		
	@staticmethod
	def fromJson(jsonString):
		return fromJson(jsonString, 'AuditHardwareOnHost')
	
	def __unicode__(self):
		res = u"<%s hostId '%s'" % (self.getType(), self.hostId)
		hardwareClass = self.getHardwareClass()
		if hardwareClass:
			res += u", hardwareClass '%s'" % hardwareClass
		if hasattr(self, 'name'):
			res += u", name '%s'" % self.name
		return res + u">"
		
	
Relationship.subClasses['AuditHardwareOnHost'] = AuditHardwareOnHost


