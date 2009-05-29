#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Backend   =
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

__version__ = '1.0.2'

# Imports
import socket, re
import copy as pycopy
from OPSI import Product
from OPSI import Tools
from OPSI.Logger import *
from OPSI.Util import ProgressSubject

# Get logger instance
logger = Logger()

OPSI_HW_AUDIT_CONF_FILE = '/etc/opsi/hwaudit/opsihwaudit.conf'
OPSI_HW_AUDIT_LOCALE_DIR = '/etc/opsi/hwaudit/locales'

# Define possible values for actions, installationStatus and requirement types

HARDWARE_CLASSES = (	'UNKNOWN',
			'BRIDGE',
			'HOST_BRIDGE',
			'ISA_BRIDGE',
			'SM_BUS',
			'USB_CONTROLLER',
			'AUDIO_CONTROLLER',
			'IDE_INTERFACE',
			'SCSI_CONTROLLER',
			'PCI_BRIDGE',
			'VGA_CONTROLLER',
			'FIREWIRE_CONTROLLER',
			'ETHERNET_CONTROLLER',
			'BASE_BOARD',
			'SYSTEM',
			'SYSTEM_SLOT',			
			'SYSTEM_BIOS',
			'CHASSIS',
			'MEMORY_CONTROLLER',
			'MEMORY_MODULE',
			'PROCESSOR',
			'CACHE',
			'PORT_CONNECTOR',
			'HARDDISK' )

SOFTWARE_LICENSE_TYPES = ( 'OEM', 'RETAIL', 'VOLUME' )
SOFTWARE_LICENSE_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\:\.\-]+$")
LICENSE_CONTRACT_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\:\.\-]+$")
LICENSE_POOL_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\:\.\-]+$")
GROUP_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\.\-]+$")
HOST_NAME_REGEX = re.compile("^[a-zA-Z0-9\_\-]+$")
CLIENT_NAME_REGEX = HOST_NAME_REGEX
HOST_ID_REGEX = re.compile("^[a-zA-Z0-9\_\-\.]+$")
CLIENT_ID_REGEX = HOST_ID_REGEX

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                      EXCEPTION CLASSES                                             =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class genericError(Exception):
	""" Base class for OPSI Backend exceptions. """
	
	ExceptionShortDescription = "OPSI-Backend generic exception"
	_message = None
	
	
	def __init__(self, message = None):
		self._message = message
	
	def __str__(self):
		#return "<%s: %s>" % (self.__class__.__name__, self.message)
		return str(self._message)
	
	def message():
		def get(self):
			return self._message
		def set(self, value):
			self._message = value
		return property(get, set)
	
	def complete_message(self):
		if self.message:
			return "%s: %s" % (self.ExceptionShortDescription, self._message)
		else:
			return "%s" % self.ExceptionShortDescription
	
	
class BackendError(genericError):
	""" Exception raised if there is an error in the backend. """
	ExceptionShortDescription = "Backend error"

class BackendIOError(genericError):
	""" Exception raised if there is a read or write error in the backend. """
	ExceptionShortDescription = "Backend I/O error"

class BackendReferentialIntegrityError(genericError):
	""" Exception raised if there is a referential integration error occurs in the backend. """
	ExceptionShortDescription = "Backend referential integrity error"

class BackendBadValueError(genericError):
	""" Exception raised if a malformed value is found. """
	ExceptionShortDescription = "Backend bad value error"

class BackendMissingDataError(genericError):
	""" Exception raised if expected data not found. """
	ExceptionShortDescription = "Backend missing data error"

class BackendAuthenticationError(genericError):
	""" Exception raised if authentication failes. """
	ExceptionShortDescription = "Backend authentication error"

class BackendPermissionDeniedError(genericError):
	""" Exception raised if a permission is denied. """
	ExceptionShortDescription = "Backend permission denied error"

class BackendTemporaryError(genericError):
	""" Exception raised if a temporary error occurs. """
	ExceptionShortDescription = "Backend temporary error"

class BackendUnaccomplishableError(genericError):
	""" Exception raised if a temporary error occurs. """
	ExceptionShortDescription = "Backend unaccomplishable error"

class BackendModuleDisabledError(genericError):
	""" Exception raised if a needed module is disabled. """
	ExceptionShortDescription = "Backend module disabled error"

class LicenseConfigurationError(genericError):
	""" Exception raised if a configuration error occurs in the license data base. """
	ExceptionShortDescription = "License configuration error"

class LicenseMissingError(genericError):
	""" Exception raised if a license is requested but cannot be found. """
	ExceptionShortDescription = "License missing error"

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                        CLASS BACKEND                                               =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class Backend:
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		pass
	
	def exit(self):
		pass
	
	def checkForErrors(self):
		return []
	
	def _preProcessHostId(self, hostId):
		if (hostId.split('.') < 3):
			raise BackendBadValueError("Bad host id '%s'" % hostId)
		return hostId.lower()
	
	def getDomain(self, hostId = None):
		''' Returns the domain of a host specified by an id. '''
		# HostId is the host's FQDN by default
		# Split the FQDN at the separators and return everything but first part
		if not hostId:
			return self._defaultDomain
		
		parts = hostId.split('.')
		return '.'.join(parts[1:])
	
	def getHostname(self, hostId):
		''' Returns the hostname of a host specified by an id. '''
		if not hostId or not hostId.find('.'):
			raise BackendBadValueError("Bad hostId '%s'" % hostId)
		
		# HostId is the host's FQDN by default
		# Split the FQDN at the separators and return the first part
		parts = hostId.split('.')
		return parts[0]
	
	def getIpAddress(self, hostId):
		addresslist = []
		hostname = self.getHostname(hostId)
		try:
			# Try to get IP by FQDN
			(name, aliasList, addressList) = socket.gethostbyname_ex(hostId)
		except socket.gaierror:
			try:
				# Failed to get IP by FQDN, try to get IP by hostname only
				(name, aliasList, addressList) = socket.gethostbyname_ex(hostname)
			except socket.gaierror, e:
				raise BackendIOError("Cannot get IP-Address for host '%s': %s" % (hostId, e))
		
		for a in addressList:
			# If more than one address exist, do not return the address of the loopback interface
			if (a != '127.0.0.1'):
				return a
		return '127.0.0.1'
	
'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                      CLASS DATABACKEND                                             =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class DataBackend(Backend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		Backend.__init__(self, username, password, address, backendManager, args)
	
	def createOpsiBase(self):
		pass
	
	def getPossibleProductActionRequests_list(self):
		return Product.POSSIBLE_PRODUCT_ACTIONS
	
	def getPossibleProductInstallationStatus_list(self):
		return Product.POSSIBLE_PRODUCT_INSTALLATION_STATUS
	
	def getPossibleRequirementTypes_list(self):
		return Product.POSSIBLE_REQUIREMENT_TYPES
	
	def getOpsiHWAuditConf(self, lang=None):
		if not lang:
			lang = 'en_US'
		
		locale = {}
		try:
			f = open(os.path.join(OPSI_HW_AUDIT_LOCALE_DIR, lang))
			i = 0
			for line in f.readlines():
				i += 1
				line = line.strip()
				if not line or line[0] in ('/', ';', '#'):
					continue
				if (line.find('=') == -1):
					logger.error("Parse error in file '%s' line %d" \
						% (os.path.join(OPSI_HW_AUDIT_LOCALE_DIR, lang), i))
				(k, v) = line.split('=', 1)
				locale[k.strip()] = v.strip()
			f.close()
		except Exception, e:
			logger.error("Failed to read translation file for language %s: %s" % (lang, e))
		
		def __inheritFromSuperClasses(classes, c, scname=None):
			if not scname:
				for scname in c['Class'].get('Super', []):
					__inheritFromSuperClasses(classes, c, scname)
			else:
				sc = None
				found = False
				for cl in classes:
					if (cl['Class'].get('Opsi') == scname):
						clcopy = pycopy.deepcopy(cl)
						__inheritFromSuperClasses(classes, clcopy)
						newValues = []
						for newValue in clcopy['Values']:
							foundAt = -1
							for i in range(len(c['Values'])):
								if (c['Values'][i]['Opsi'] == newValue['Opsi']):
									if not c['Values'][i].get('UI'):
										c['Values'][i]['UI'] = newValue.get('UI', '')
									foundAt = i
									break
							if (foundAt > -1):
								newValue = c['Values'][foundAt]
								del c['Values'][foundAt]
							newValues.append(newValue)
						found = True
						newValues.extend(c['Values'])
						c['Values'] = newValues
						break
				if not found:
					logger.error("Super class '%s' of class '%s' not found!" % (scname, c['Class'].get('Opsi')))
			
		
		global OPSI_HARDWARE_CLASSES
		OPSI_HARDWARE_CLASSES = []
		execfile(OPSI_HW_AUDIT_CONF_FILE)
		classes = []
		for i in range(len(OPSI_HARDWARE_CLASSES)):
			opsiClass = OPSI_HARDWARE_CLASSES[i]['Class']['Opsi']
			if (OPSI_HARDWARE_CLASSES[i]['Class']['Type'] == 'STRUCTURAL'):
				if locale.get(opsiClass):
					OPSI_HARDWARE_CLASSES[i]['Class']['UI'] = locale[opsiClass]
				else:
					logger.error("No translation for class '%s' found" % opsiClass)
					OPSI_HARDWARE_CLASSES[i]['Class']['UI'] = opsiClass
			for j in range(len(OPSI_HARDWARE_CLASSES[i]['Values'])):
				opsiProperty = OPSI_HARDWARE_CLASSES[i]['Values'][j]['Opsi']
				if locale.get(opsiClass + '.' + opsiProperty):
					OPSI_HARDWARE_CLASSES[i]['Values'][j]['UI'] = locale[opsiClass + '.' + opsiProperty]
				
		for c in OPSI_HARDWARE_CLASSES:
			try:
				if (c['Class'].get('Type') == 'STRUCTURAL'):
					logger.info("Found STRUCTURAL hardware class '%s'" % c['Class'].get('Opsi'))
					ccopy = pycopy.deepcopy(c)
					if ccopy['Class'].has_key('Super'):
						__inheritFromSuperClasses(OPSI_HARDWARE_CLASSES, ccopy)
						del ccopy['Class']['Super']
					del ccopy['Class']['Type']
					
					# Fill up empty display names
					for j in range(len(ccopy.get('Values', []))):
						if not ccopy['Values'][j].get('UI'):
							logger.error("No translation for property '%s.%s' found" % (ccopy['Class']['Opsi'], ccopy['Values'][j]['Opsi']))
							ccopy['Values'][j]['UI'] = ccopy['Values'][j]['Opsi']
					
					classes.append(ccopy)
			except Exception, e:
				logger.error("Error in config file '%s': %s" % (OPSI_HW_AUDIT_CONF_FILE, e))
		
		return classes
	
	def getProductType(self, productId, depotId):
		productId = productId.lower()
		productType = None
		if productId in self.getProductIds_list('netboot', depotId):
			productType = 'netboot'
		elif productId in self.getProductIds_list('localboot', depotId):
			productType = 'localboot'
		else:
			raise Exception("product '%s': is neither localboot nor netboot product" % productId)
		return productType
	
	def setPXEBootConfiguration(self, hostId, args={}):
		pass
	
	def unsetPXEBootConfiguration(self, hostId):
		pass
	
class DataBackendReplicator(object):
	def __init__(self, readBackend, writeBackend, newServerId=None, cleanupFirst=True, privileges='FULL'):
		self.__readBackend  = readBackend
		self.__writeBackend = writeBackend
		self.__newServerId  = newServerId
		self.__cleanupFirst = cleanupFirst
		self.__privileges = privileges
		self.__oldServerId  = ''
		self.__serverIds = []
		self.__depotIds = []
		self.__clientIds = {}
		self.__groupIds = []
		self.__productIds = {}
		self.__overallProgressSubject = ProgressSubject(id='overall_replication', title='Replicating', end=100, fireAlways=True)
		self.__currentProgressSubject = ProgressSubject(id='current_replication', fireAlways=True)
		
	def getCurrentProgressSubject(self):
		return self.__currentProgressSubject
	
	def getOverallProgressSubject(self):
		return self.__overallProgressSubject
	
	def getServerId(self):
		if not self.__serverIds:
			return None
		return self.__serverIds[0]
	
	def getServerIds(self):
		return self.__serverIds
	
	def getDepotIds(self):
		return self.__depotIds
	
	def getClientIds(self, depotIds=[]):
		if not type(depotIds) is list: depotIds = [ depotIds ]
		if not depotIds:
			depotIds = self.getDepotIds()
		clientIds = []
		for (depotId, ids) in self.__clientIds.items():
			if depotId in depotIds:
				clientIds.extend(ids)
		return clientIds
	
	def getGroupIds(self):
		return self.__groupIds
	
	def getProductIds(self, productType='', depotId=''):
		if not self.__productIds:
			for depotId in self.getDepotIds():
				self.__productIds[depotId] = {}
				for productType in ('localboot', 'netboot'):
					self.__productIds[depotId][productType] = self.__readBackend.getProductIds_list(productType = productType, objectId = depotId)
		productIds = []
		if not depotId:
			depotId = self.getServersIds()[0]
		for (dId, pTypes) in self.__productIds.items():
			if (dId == depotId):
				for (pType, pIds) in pTypes.items():
					if not productType or (productType == pType):
						productIds.extend(pIds)
		return productIds
	
	def replicate(self, serverIds=[], depotIds=[], clientIds=[], groupIds=[], productIds=[]):
		'''
		Replicate (a part) of a opsi configuration database
		An empty list passed as a param means: replicate all known
		None as the only element of a list means: replicate none
		'''
		if not type(serverIds)  is list: serverIds  = [ serverIds ]
		if not type(depotIds)   is list: depotIds   = [ depotIds ]
		if not type(clientIds)  is list: clientIds  = [ clientIds ]
		if not type(groupIds)   is list: groupIds   = [ groupIds ]
		if not type(productIds) is list: productIds = [ productIds ]
		
		logger.info("replicate(serverIds=%s, depotIds=%s, clientIds=%s, groupIds=%s, productIds=%s)" \
				% (serverIds, depotIds, clientIds, groupIds, productIds))
		
		# Servers
		knownServerIds = self.__readBackend.getServerIds_list()
		if serverIds:
			for serverId in serverIds:
				if serverId in knownServerIds:
					self.__serverIds.append(serverId)
		else:
			self.__serverIds = knownServerIds
		
		# Depots
		knownDepotIds = self.__readBackend.getDepotIds_list()
		if depotIds:
			for depotId in depotIds:
				if depotId in knownDepotIds:
					self.__depotIds.append(depotId)
		else:
			self.__depotIds = knownDepotIds
		
		# Clients
		knownClientIds = {}
		for depotId in self.getDepotIds():
			knownClientIds[depotId] = []
			for clientId in self.__readBackend.getClientIds_list(depotIds = [ depotId ]):
				if self.__newServerId and (clientId == self.__newServerId):
					continue
				knownClientIds[depotId].append(clientId)
		if clientIds:
			for clientId in clientIds:
				for depotId in depotIds:
					self.__clientIds[depotId] = []
					if clientId in knownClientIds[depotId]:
						self.__clientIds[depotId].append(clientId)
						break
		else:
			self.__clientIds = knownClientIds
		
		# Groups
		knownGroupIds = self.__readBackend.getGroupIds_list()
		if groupIds:
			for groupId in groupIds:
				if groupId in knownGroupIds:
					self.__groupIds.append(groupId)
		else:
			self.__groupIds = knownGroupIds
		
		# Products
		knownProductIds = {}
		for depotId in self.getDepotIds():
			knownProductIds[depotId] = {}
			for productType in ('localboot', 'netboot'):
				knownProductIds[depotId][productType] = []
				for productId in self.__readBackend.getProductIds_list(productType = productType, objectId = depotId):
					knownProductIds[depotId][productType].append(productId)
		if productIds:
			for productId in productIds:
				for depotId in depotIds:
					if not self.__productIds.has_key(depotId):
						self.__productIds[depotId] = {}
					for productType in ('localboot', 'netboot'):
						if not self.__productIds[depotId].has_key(productType):
							self.__productIds[depotId][productType] = []
						if productId in knownProductIds[depotId][productType]:
							self.__productIds[depotId][productType].append(productId)
							break
		else:
			self.__productIds = knownProductIds
		
		logger.info("replicate: self.__serverIds=%s, self.__depotIds=%s, self.__clientIds=%s, self.__groupIds=%s, self.__productIds=%s" \
				% (self.__serverIds, self.__depotIds, self.__clientIds, self.__groupIds, self.__productIds))
		
		# Create opsi base
		self.createOpsiBase()
		self.__overallProgressSubject.setState(1)
		
		# Clean up new backend
		if self.__cleanupFirst:
			self.deleteGeneralConfigs()
			self.__overallProgressSubject.setState(2)
			self.deleteNetworkConfigs()
			self.__overallProgressSubject.setState(3)
			self.deleteProducts()
			self.__overallProgressSubject.setState(4)
			self.deleteClients()
			self.__overallProgressSubject.setState(5)
			self.deleteGroups()
			self.__overallProgressSubject.setState(6)
			self.deleteServers()
			self.__overallProgressSubject.setState(7)
			self.deleteDepots()
		
		# Replicate
		self.__overallProgressSubject.setState(10)
		self.replicateServers()
		self.__overallProgressSubject.setState(15)
		self.replicateDepots()
		self.__overallProgressSubject.setState(20)
		self.replicateClients()
		self.__overallProgressSubject.setState(30)
		self.replicateGroups()
		self.__overallProgressSubject.setState(35)
		self.replicateGeneralConfigs()
		self.__overallProgressSubject.setState(45)
		self.replicateNetworkConfigs()
		self.__overallProgressSubject.setState(55)
		self.replicateProducts()
		self.__overallProgressSubject.setState(60)
		self.replicateProductStates()
		self.__overallProgressSubject.setState(80)
		self.replicateProductProperties()
		self.__overallProgressSubject.setState(100)
		
	def createOpsiBase(self):
		logger.info("Creating opsi base for write backend %s" % self.__writeBackend)
		self.__overallProgressSubject.setMessage("Creating opsi base.")
		self.__currentProgressSubject.reset()
		self.__currentProgressSubject.setEnd(1)
		
		self.__writeBackend.createOpsiBase()
		
		self.__currentProgressSubject.setState(1)
	
	def deleteServers(self):
		logger.info("Deleting servers")
		self.__overallProgressSubject.setMessage("Deleting servers.")
		self.__currentProgressSubject.reset()
		self.__currentProgressSubject.setEnd(1)
		
		for serverId in self.__writeBackend.getServerIds_list():
			self.__writeBackend.deleteServer(serverId)
		
		self.__currentProgressSubject.setState(1)
		
	def replicateServers(self):
		logger.info("Replicating servers")
		self.__overallProgressSubject.setMessage("Replicating servers.")
		self.__currentProgressSubject.reset()
		
		serverIds = self.getServerIds()
		if (len(serverIds) > 1):
			raise NotImplemented("Replication of more than one server not supported")
		
		self.__currentProgressSubject.setEnd(len(serverIds))
		
		for i in range(len(serverIds)):
			serverId = serverIds[i]
			server = self.__readBackend.getHost_hash(serverId)
			logger.info("      Replicating server '%s' (%s/%s)" % (server.get('hostId'), i+1, len(serverIds)))
			self.__currentProgressSubject.setMessage("      Replicating server '%s' (%s/%s)" % (server.get('hostId'), i+1, len(serverIds)))
			try:
				newServerId = server.get('hostId')
				if self.__newServerId:
					self._oldServerId = server.get('hostId')
					newServerId = self.__newServerId
				
				serverName = newServerId.split('.')[0]
				domain = '.'.join( newServerId.split('.')[1:] )
				self.__writeBackend.createServer(	serverName	= serverName, 
							domain		= domain,
							description	= server.get('description', ''),
							notes		= server.get('notes', '') )
				
				if (self.__privileges == 'FULL'):
					self.__writeBackend.setOpsiHostKey( newServerId, self.__readBackend.getOpsiHostKey(server.get('hostId')) )
					self.__writeBackend.setPcpatchPassword( newServerId, self.__readBackend.getPcpatchPassword(server.get('hostId')) )
				
			except Exception, e:
				logger.error(e)
				raise
			self.__currentProgressSubject.addToState(1)
	
	def deleteDepots(self):
		logger.info("Deleting depots")
		self.__overallProgressSubject.setMessage("Deleting depots.")
		self.__currentProgressSubject.reset()
		
		depotIds = self.__writeBackend.getDepotIds_list()
		self.__currentProgressSubject.setEnd(len(depotIds))
		for depotId in depotIds:
			self.__writeBackend.deleteDepot(depotId)
			self.__currentProgressSubject.addToState(1)
		
	def replicateDepots(self):
		logger.info("Replicating depots")
		self.__overallProgressSubject.setMessage("Replicating depots.")
		self.__currentProgressSubject.reset()
		
		depotIds = self.getDepotIds()
		self.__currentProgressSubject.setEnd(len(depotIds))
		for i in range(len(depotIds)):
			depotId = depotIds[i]
			depot = self.__readBackend.getDepot_hash(depotId)
			host = self.__readBackend.getHost_hash(depotId)
			logger.info("      Replicating depot '%s' (%s/%s)" % (depotId, i+1, len(depotIds)) )
			self.__currentProgressSubject.setMessage("      Replicating depot '%s' (%s/%s)" % (depotId, i+1, len(depotIds)) )
			try:
				newDepotId = depotId
				if self.__newServerId and (self.__oldServerId == depotId):
					newDepotId = self.__newServerId
					oldServerName = self.__oldServerId.split('.')[0]
					newServerName = self.__newServerId.split('.')[0]
					if depot.get('depotRemoteUrl'):
						depot['depotRemoteUrl'] = depot['depotRemoteUrl'].replace(self.__oldServerId, self.__newServerId)
						depot['depotRemoteUrl'] = depot['depotRemoteUrl'].replace(oldServerName, newServerName)
					if depot.get('repositoryRemoteUrl'):
						depot['repositoryRemoteUrl'] = depot['repositoryRemoteUrl'].replace(self.__oldServerId, self.__newServerId)
						depot['repositoryRemoteUrl'] = depot['repositoryRemoteUrl'].replace(oldServerName, newServerName)
				
				depotName = newDepotId.split('.')[0]
				domain = '.'.join( newDepotId.split('.')[1:] )
				
				self.__writeBackend.createDepot(
							depotName		= depotName,
							domain			= domain,
							description		= depot.get('description', ''),
							notes			= depot.get('notes', ''),
							depotLocalUrl		= depot.get('depotLocalUrl', ''),
							depotRemoteUrl		= depot.get('depotRemoteUrl', ''),
							repositoryLocalUrl	= depot.get('repositoryLocalUrl', ''),
							repositoryRemoteUrl	= depot.get('repositoryRemoteUrl', ''),
							network			= depot.get('network', ''),
							maxBandwidth		= depot.get('repositoryMaxBandwidth', '')
				)
				if (self.__privileges == 'FULL'):
					self.__writeBackend.setOpsiHostKey( newDepotId, self.__readBackend.getOpsiHostKey(depotId) )
			
			except Exception, e:
				logger.error(e)
				raise Exception("Failed to replicate depot '%s': %s" % (depotId, e))
			self.__currentProgressSubject.addToState(1)
	
	def deleteClients(self):
		logger.info("Deleting clients")
		self.__overallProgressSubject.setMessage("Deleting clients.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.__writeBackend.getClientIds_list()
		self.__currentProgressSubject.setEnd(len(clientIds))
		for clientId in clientIds:
			self.__writeBackend.deleteClient(clientId)
			self.__currentProgressSubject.addToState(1)
		
	def replicateClients(self):
		logger.info("Replicating clients")
		self.__overallProgressSubject.setMessage("Replicating clients.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.getClientIds()
		self.__currentProgressSubject.setEnd(len(clientIds))
		for i in range(len(clientIds)):
			clientId = clientIds[i]
			client = self.__readBackend.getHost_hash(clientId)
			hardwareAddress = self.__readBackend.getMacAddress(clientId)
			logger.info("      Replicating client '%s' (%s/%s)" % (client.get('hostId'), i+1, len(clientIds)) )
			self.__currentProgressSubject.setMessage("      Replicating client '%s' (%s/%s)" % (client.get('hostId'), i+1, len(clientIds)) )
			try:
				clientName = client.get('hostId').split('.')[0]
				domain = '.'.join( client.get('hostId').split('.')[1:] )
				self.__writeBackend.createClient(
							clientName	= clientName,
							domain		= domain,
							description	= client.get('description', ''),
							notes		= client.get('notes', ''),
							hardwareAddress = hardwareAddress )
				
				if client.get('lastSeen'):
					self.__writeBackend.setHostLastSeen(client.get('hostId'), client.get('lastSeen'))
				
				opsiHostKey = self.__readBackend.getOpsiHostKey( client.get('hostId') )
				self.__writeBackend.setOpsiHostKey( client.get('hostId'), opsiHostKey )
				if (self.__privileges == 'FULL'):
					serverKey = self.__writeBackend.getOpsiHostKey( self.getServerId() )
					encryptedPcpatchPass = self.__writeBackend.getPcpatchPassword( self.getServerId() )
					self.__writeBackend.setPcpatchPassword( client.get('hostId'), Tools.blowfishEncrypt(opsiHostKey, Tools.blowfishDecrypt(serverKey, encryptedPcpatchPass)) )
			
			except Exception, e:
				logger.error(e)
				raise
			self.__currentProgressSubject.addToState(1)
		
	def deleteGroups(self):
		logger.info("Deleting groups")
		self.__overallProgressSubject.setMessage("Deleting groups.")
		self.__currentProgressSubject.reset()
		
		groupIds = self.__writeBackend.getGroupIds_list()
		self.__currentProgressSubject.setEnd(len(groupIds))
		for groupId in groupIds:
			self.__writeBackend.deleteGroup(groupId)
			self.__currentProgressSubject.addToState(1)
		
	def replicateGroups(self):
		logger.info("Replicating groups")
		self.__overallProgressSubject.setMessage("Replicating groups.")
		self.__currentProgressSubject.reset()
		
		knownClientIds = self.getClientIds()
		groupIds = self.getGroupIds()
		self.__currentProgressSubject.setEnd(len(groupIds))
		for i in range(len(groupIds)):
			groupId = groupIds[i]
			logger.info("      Replicating group '%s' (%s/%s)" % (groupId, i+1, len(groupIds)) )
			self.__currentProgressSubject.setMessage("      Replicating group '%s' (%s/%s)" % (groupId, i+1, len(groupIds)) )
			clientIds = []
			for clientId in self.__readBackend.getClientIds_list(groupId = groupId):
				if self.__newServerId and (self.__newServerId == clientId):
					continue
				if not clientId in knownClientIds:
					continue
				clientIds.append(clientId)
			
			try:
				self.__writeBackend.createGroup(
							groupId	= groupId,
							members	= clientIds )
			except Exception, e:
				logger.error(e)
				raise
			self.__currentProgressSubject.addToState(1)
	
	def deleteGeneralConfigs(self):
		logger.info("Deleting general configs")
		self.__overallProgressSubject.setMessage("Deleting general configs.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.__writeBackend.getClientIds_list()
		self.__currentProgressSubject.setEnd(len(clientIds)+1)
		try:
			self.__writeBackend.deleteGeneralConfig(self.getServerId())
		except BackendMissingDataError, e:
			pass
		self.__currentProgressSubject.addToState(1)
		for clientId in clientIds:
			try:
				self.__writeBackend.deleteGeneralConfig(clientId)
			except BackendMissingDataError, e:
				pass
			self.__currentProgressSubject.addToState(1)
		
	def replicateGeneralConfigs(self):
		logger.info("Replicating general configs")
		self.__overallProgressSubject.setMessage("Replicating general configs.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.__writeBackend.getClientIds_list()
		self.__currentProgressSubject.setEnd(len(clientIds)+1)
		
		generalConfig = {}
		if self.getServerId():
			generalConfig = self.__readBackend.getGeneralConfig_hash(self.getServerId())
			self.__writeBackend.setGeneralConfig(generalConfig)
		self.__currentProgressSubject.addToState(1)
		
		for clientId in clientIds:
			logger.info("      Searching general config for client '%s'" % clientId)
			self.__currentProgressSubject.setMessage("      Searching general config for client '%s'" % clientId)
			
			gc = self.__readBackend.getGeneralConfig_hash(clientId)
			new = False
			
			for (key, value) in gc.items():
				if not generalConfig.has_key(key):
					new = True
					break
				elif (generalConfig.get(key) != value):
					new = True
					break
				
			if new:
				logger.info("            Replicating general config")
				self.__currentProgressSubject.setMessage("            Replicating general config.")
				self.__writeBackend.setGeneralConfig(gc , clientId)
			self.__currentProgressSubject.addToState(1)
	
	def deleteNetworkConfigs(self):
		logger.info("Deleting network configs")
		self.__overallProgressSubject.setMessage("Deleting network configs.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.__writeBackend.getClientIds_list()
		self.__currentProgressSubject.setEnd(len(clientIds)+1)
		
		try:
			self.__writeBackend.deleteNetworkConfig(self.getServerId())
		except BackendMissingDataError, e:
			pass
		self.__currentProgressSubject.addToState(1)
		
		for clientId in clientIds:
			try:
				self.__writeBackend.deleteNetworkConfig(clientId)
			except Exception, e:
				pass
			self.__currentProgressSubject.addToState(1)
	
	def replicateNetworkConfigs(self):
		logger.info("Replicating network configs")
		self.__overallProgressSubject.setMessage("Replicating network configs.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.getClientIds()
		self.__currentProgressSubject.setEnd(len(clientIds)+1)
		
		networkConfig = {}
		if self.getServerId():
			networkConfig = self.__readBackend.getNetworkConfig_hash(self.getServerId())
			if self.__newServerId:
				networkConfig['opsiServer'] = self.__newServerId
				if (networkConfig.get('depotId') == self.__oldServerId):
					networkConfig['depotId'] = self.__newServerId
			
			self.__writeBackend.setNetworkConfig(networkConfig)
		self.__currentProgressSubject.addToState(1)
		
		for clientId in clientIds:
			logger.info("      Searching network config for client '%s'" % clientId)
			self.__currentProgressSubject.setMessage("      Searching network config for client '%s'" % clientId)
			
			nc = self.__readBackend.getNetworkConfig_hash(clientId)
			if self.__newServerId:
				nc['opsiServer'] = self.__newServerId
				if (nc.get('depotId') == self.__oldServerId):
					nc['depotId'] = self.__newServerId
			new = False
			
			for (key, value) in nc.items():
				if not networkConfig.has_key(key):
					new = True
					break
				elif (networkConfig.get(key) != value):
					new = True
					break
				
			if new:
				logger.info("            Replicating network config")
				self.__currentProgressSubject.setMessage("            Replicating network config.")
				self.__writeBackend.setNetworkConfig(nc , clientId)
			self.__currentProgressSubject.addToState(1)
		
	def deleteProducts(self):
		logger.info("Deleting products")
		self.__overallProgressSubject.setMessage("Deleting products.")
		self.__currentProgressSubject.reset()
		
		depotIds = self.__writeBackend.getDepotIds_list()
		self.__currentProgressSubject.setEnd(len(depotIds))
		
		for depotId in depotIds:
			for productId in self.__writeBackend.getProductIds_list(objectId = depotId):
				self.__writeBackend.deleteProduct(productId = productId, depotIds = [ depotId ])
			self.__currentProgressSubject.addToState(1)
		
	def replicateProducts(self):
		objectId=None
		depotIds = self.getDepotIds()
		for i in range(len(depotIds)):
			depotId = depotIds[i]
			newDepotId = depotId
			if self.__newServerId and (self.__oldServerId == depotId):
				newDepotId = self.__newServerId
			for type in ('netboot', 'localboot'):
				logger.info("Replicating %s products of depot '%s'." % (type, depotId) )
				self.__overallProgressSubject.setMessage("Replicating %s products of depot '%s'." % (type, depotId) )
				self.__currentProgressSubject.reset()
				
				productIds = self.getProductIds(productType = type, depotId = depotId)
				self.__currentProgressSubject.setEnd(len(productIds))
				
				for j in range(len(productIds)):
					productId = productIds[j]
					logger.info("      Replicating product '%s' of depot '%s' (%s/%s)" % (productId, depotId, j+1, len(productIds)) )
					self.__currentProgressSubject.setMessage("      Replicating product '%s' of depot '%s' (%s/%s)" % (productId, depotId, j+1, len(productIds)) )
					
					product = self.__readBackend.getProduct_hash(productId = productId, depotId = depotId)
					try:
						setupScript = product.get('setupScript', '')
						uninstallScript	= product.get('uninstallScript', '')
						updateScript = product.get('updateScript', '')
						alwaysScript = product.get('alwaysScript', '')
						onceScript = product.get('onceScript', '')
						
						regexPath = re.compile('^\w:\\\\.*\\\\%s\\\\(.*)$' % productId, re.IGNORECASE)
						regexURL = re.compile('^\w+:/.*/%s/(.*)$' % productId, re.IGNORECASE)
						
						for script in ('setupScript', 'uninstallScript', 'updateScript', 'alwaysScript', 'onceScript'):
							
							if not eval(script):
								continue
							match = re.search(regexPath, eval(script))
							if match:
								logger.info("Changing scriptname from '%s' to '%s'" % (eval(script), match.group(1)))
								exec("%s = '%s'" % (script, match.group(1)))
								continue
							match = re.search(regexURL, eval(script))
							if match:
								logger.info("Changing scriptname from '%s' to '%s'" % (eval(script), match.group(1)))
								exec("%s = '%s'" % (script, match.group(1)))
							
						self.__writeBackend.createProduct(	productType		= type, 
									productId		= productId,
									name			= product.get('name'),
									productVersion		= product.get('productVersion', '1.0'),
									packageVersion		= product.get('packageVersion', '1'),
									licenseRequired		= product.get('licenseRequired', 0),
									setupScript		= setupScript,
									uninstallScript		= uninstallScript,
									updateScript		= updateScript,
									alwaysScript		= alwaysScript,
									onceScript		= onceScript,
									priority		= product.get('priority', 0),
									description		= product.get('description', ''),
									advice			= product.get('advice', ''),
									productClassNames	= product.get('productClassNames', []),
									pxeConfigTemplate	= product.get('pxeConfigTemplate', None),
									windowsSoftwareIds	= product.get('windowsSoftwareIds', []),
									depotIds		= [ newDepotId ] )
					except Exception, e:
						logger.logException(e)
						raise
					
					for dependency in self.__readBackend.getProductDependencies_listOfHashes(productId = productId, depotId = depotId):
						logger.info("            Replicating product dependency '%s'" \
							% dependency.get('requiredProductId', dependency.get('requiredProductClassId')) )
						self.__currentProgressSubject.setMessage("            Replicating product dependency '%s'" \
							% dependency.get('requiredProductId', dependency.get('requiredProductClassId')) )
						self.__writeBackend.createProductDependency(
								productId			= productId,
								action				= dependency.get('action'),
								requiredProductId		= dependency.get('requiredProductId'),
								requiredProductClassId		= dependency.get('requiredProductClassId'),
								requiredAction			= dependency.get('requiredAction'),
								requiredInstallationStatus	= dependency.get('requiredInstallationStatus'),
								requirementType			= dependency.get('requirementType'),
								depotIds			= [ newDepotId ] )
						
					for definition in self.__readBackend.getProductPropertyDefinitions_listOfHashes(productId = productId, depotId = depotId):
						logger.info("            Replicating product property definition '%s'" % definition.get('name') )
						self.__currentProgressSubject.setMessage("            Replicating product property definition '%s'" % definition.get('name') )
						self.__writeBackend.createProductPropertyDefinition(
								productId 	= productId,
								name		= definition.get('name'),
								description	= definition.get('description'),
								defaultValue	= definition.get('default'),
								possibleValues	= definition.get('values'),
								depotIds	= [ newDepotId ] )
					self.__currentProgressSubject.addToState(1)
				self.__currentProgressSubject.setMessage("")
	
	def replicateProductStates(self):
		logger.info("Replicating product states")
		self.__overallProgressSubject.setMessage("Replicating product states.")
		self.__currentProgressSubject.reset()
		
		clientIds = self.getClientIds()
		self.__currentProgressSubject.setEnd(len(clientIds))
		
		i = 0
		for (clientId, states) in self.__readBackend.getProductStates_hash(clientIds).items():
			depotId = self.__writeBackend.getDepotId(clientId)
			productIds = self.getProductIds(depotId = depotId)
			i += 1
			logger.info("      Replicating product states of client '%s' (%s/%s)" % ( clientId, i, len(clientIds) ) )
			self.__currentProgressSubject.setMessage("      Replicating product states of client '%s' (%s/%s)" % ( clientId, i, len(clientIds) ) )
			for state in states:
				if state.get('productId') not in productIds:
					logger.debug("Skipping product state replication of product '%s': product not installed on depot" % state.get('productId'))
					continue
				
				self.__currentProgressSubject.setMessage("               Replicating product state for product '%s' on '%s' (%s/%s)" \
								% ( state.get('productId'), clientId, i, len(clientIds) ) )
				try:
					self.__writeBackend.setProductState(
							state.get('productId'),
							clientId,
							installationStatus = state.get('installationStatus'),
							actionRequest = state.get('actionRequest'),
							productVersion = state.get('productVersion'),
							packageVersion = state.get('packageVersion'),
							lastStateChange = state.get('lastStateChange'),
							productActionProgress = state.get('productActionProgress', {}))
					#self.__writeBackend.setProductInstallationStatus(state.get('productId'), hostId, state.get('installationStatus'))
					#if state.get('actionRequest') and state.get('actionRequest') not in ('undefined', 'none'):
					#	self.__writeBackend.setProductActionRequest(state.get('productId'), hostId, state.get('actionRequest'))
				except Exception, e:
					logger.error(e)
					raise
			self.__currentProgressSubject.addToState(1)
	
	def replicateProductProperties(self):
		logger.info("Replicating product properties.")
		self.__overallProgressSubject.setMessage("Replicating product properties.")
		
		for depotId in self.getDepotIds():
			i = 0
			productIds = self.getProductIds(depotId = depotId)
			clientIds = self.getClientIds(depotIds = [ depotId ])
			newDepotId = depotId
			if self.__newServerId and (self.__oldServerId == depotId):
				newDepotId = self.__newServerId
			
			self.__currentProgressSubject.reset()
			self.__currentProgressSubject.setEnd(len(productIds)+1)
			
			for productId in productIds:
				i += 1
				logger.info("      Replicating product properties for product '%s' (%s/%s)" % (productId, i, len(productIds)) )
				self.__currentProgressSubject.setMessage("      Replicating product properties for product '%s' (%s/%s)" % (productId, i, len(productIds)) )
				
				productProperties = self.__readBackend.getProductProperties_hash(productId, objectId = depotId)
				try:
					self.__writeBackend.setProductProperties(productId, productProperties, objectId = newDepotId)
				except Exception, e:
					logger.error(e)
					raise
				
				self.__currentProgressSubject.addToState(1)
				
				for clientId in clientIds:
					logger.info("            Replicating product properties for product '%s' on '%s' (%s/%s)" % (productId, clientId, i, len(productIds)) )
					self.__currentProgressSubject.setMessage("            Replicating product properties for product '%s' on '%s' (%s/%s)" % (productId, clientId, i, len(productIds)) )
					pp = self.__readBackend.getProductProperties_hash(productId, clientId)
					new = False
					
					for (key, value) in pp.items():
						if not productProperties.has_key(key):
							new = True
							break
						elif (productProperties.get(key) != value):
							new = True
							break
						
					if new:
						try:
							self.__writeBackend.setProductProperties(productId, pp, clientId)
						except Exception, e:
							logger.error(e)
							raise
			self.__currentProgressSubject.addToState(1)


