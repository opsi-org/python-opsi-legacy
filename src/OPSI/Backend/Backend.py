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

__version__ = '0.9.9'

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
SOFTWARE_LICENSE_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\.\-]+$")
SOFTWARE_LICENSE_KEY_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\.\-]+$")
LICENSE_CONTRACT_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\.\-]+$")
LICENSE_POOL_ID_REGEX = re.compile("^[a-zA-Z0-9\s\_\.\-]+$")
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
	
	def __init__(self, message = None):
		self.message = message
	
	def __str__(self):
		#return "<%s: %s>" % (self.__class__.__name__, self.message)
		return str(self.message)
	
	def complete_message(self):
		if self.message:
			return "%s: %s" % (self.ExceptionShortDescription, self.message)
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

class DataBackendReplicator(object):
	def __init__(self, readBackend, writeBackend, newServerId=None, cleanupFirst=True):
		self.__readBackend  = readBackend
		self.__writeBackend = writeBackend
		self.__newServerId  = newServerId
		self.__cleanupFirst = cleanupFirst
		self.__oldServerId  = ''
		self.__serverIds = []
		self.__depotIds = []
		self.__clientIds = {}
		self.__groupIds = []
		self.__productIds = {}
		self.__progressSubject = ProgressSubject(id='replicator')
		
	def getServersIds(self):
		if not self.__serverIds:
			self.__serverIds = self.__readBackend.getServerIds_list()
		return self.__serverIds
	
	def getDepotIds(self):
		if not self.__depotIds:
			self.__depotIds = self.__readBackend.getDepotIds_list()
		return self.__depotIds
	
	def getClientIds(self, depotIds=[]):
		if not self.__clientIds:
			for depotId in self.getDepotIds():
				self.__clientIds[depotId] = self.__readBackend.getClientIds_list(depotIds = [ depotId ])
		clientIds = []
		for (depotId, ids) in self.__clientIds.items():
			if not depotIds or depotId in depotIds:
				clientIds.extend(ids)
		return clientIds
	
	def getGroupIds(self):
		if not self.__groupIds:
			self.__groupIds = self.__readBackend.getGroupIds_list()
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
	
	def replicate(self, depotIds=[], clientIds=[], productIds=[]):
		if depotIds:
			self.__depotIds = depotIds
		if clientIds:
			for depotId in self.getDepotIds():
				self.__clientIds[depotId] = []
				for clientId in self.__readBackend.getClientIds_list(depotIds = [ depotId ]):
					if clientId in clientIds:
						self.__clientIds[depotId].append(clientId)
		if productIds:
			for depotId in self.getDepotIds():
				self.__productIds[depotId] = {}
				for productType in ('localboot', 'netboot'):
					self.__productIds[depotId][productType] = []
					for productId in self.__readBackend.getProductIds_list(productType = productType, objectId = depotId):
						if productId in productIds:
							self.__productIds[depotId][productType].append(productId)
		self.createOpsiBase()
		
		if self.__cleanupFirst:
			self.deleteGeneralConfigs()
			self.deleteNetworkConfigs()
			self.deleteProducts()
			self.deleteClients()
			self.deleteGroups()
			self.deleteServers()
			self.deleteDepots()
		
		self.replicateServers()
		self.replicateDepots()
		self.replicateClients()
		self.replicateGroups()
		self.replicateGeneralConfigs()
		self.replicateNetworkConfigs()
		self.replicateProducts()
		self.replicateProductStates()
		self.replicateProductProperties()
		
	def createOpsiBase(self):
		logger.info("Creating opsi base")
		self.__progressSubject.setMessage("Creating opsi base.")
		self.__writeBackend.createOpsiBase()
	
	def deleteServers(self):
		logger.info("Deleting servers")
		self.__progressSubject.setMessage("Deleting servers.")
		for serverId in self.__writeBackend.getServerIds_list():
			self.__writeBackend.deleteServer(serverId)
	
	def replicateServers(self):
		logger.info("Replicating servers")
		self.__progressSubject.setMessage("Replicating servers.")
		serverIds = self.getServersIds()
		for i in range(len(serverIds)):
			serverId = serverIds[i]
			server = self.__readBackend.getHost_hash(serverId)
			logger.info("      Replicating server '%s' (%s/%s)" % (server.get('hostId'), i+1, len(serverIds)))
			self.__progressSubject.setMessage("      Replicating server '%s' (%s/%s)" % (server.get('hostId'), i+1, len(serverIds)))
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
				
				self.__writeBackend.setOpsiHostKey( newServerId, self.__readBackend.getOpsiHostKey(server.get('hostId')) )
				self.__writeBackend.setPcpatchPassword( newServerId, self.__readBackend.getPcpatchPassword(server.get('hostId')) )
				
			except Exception, e:
				logger.error(e)
				raise
	
	def deleteDepots(self):
		logger.info("Deleting depots")
		self.__progressSubject.setMessage("Deleting depots.")
		for depotId in self.__writeBackend.getDepotIds_list():
			self.__writeBackend.deleteDepot(depotId)
	
	def replicateDepots(self):
		logger.info("Replicating depots")
		self.__progressSubject.setMessage("Replicating depots.")
		depotIds = self.getDepotIds()
		for i in range(len(depotIds)):
			depotId = depotIds[i]
			depot = self.__readBackend.getDepot_hash(depotId)
			host = self.__readBackend.getHost_hash(depotId)
			logger.info("      Replicating depot '%s' (%s/%s)" % (depotId, i+1, len(depotIds)) )
			self.__progressSubject.setMessage("      Replicating depot '%s' (%s/%s)" % (depotId, i+1, len(depotIds)) )
			try:
				newDepotId = depotId
				if self.__newServerId and (self.__oldServerId == depotId):
					newDepotId = self.__newServerId
				
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
				self.__writeBackend.setOpsiHostKey( newDepotId, self.__readBackend.getOpsiHostKey(depotId) )
			
			except Exception, e:
				logger.error(e)
				raise Exception("Failed to convert depot '%s': %s" % (depotId, e))
	
	def deleteClients(self):
		logger.info("Deleting clients")
		self.__progressSubject.setMessage("Deleting clients.")
		for clientId in self.__writeBackend.getClientIds_list():
			self.__writeBackend.deleteClient(clientId)
	
	def replicateClients(self):
		logger.info("Replicating clients")
		self.__progressSubject.setMessage("Replicating clients.")
		clientIds = self.getClientIds()
		for i in range(len(clientIds)):
			clientId = clientIds[i]
			client = self.__readBackend.getHost_hash(clientId)
			hardwareAddress = self.__readBackend.getMacAddress(clientId)
			logger.info("      Replicating client '%s' (%s/%s)" % (client.get('hostId'), i+1, len(clientIds)) )
			self.__progressSubject.setMessage("      Replicating client '%s' (%s/%s)" % (client.get('hostId'), i+1, len(clientIds)) )
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
				serverKey = self.__writeBackend.getOpsiHostKey( self.__writeBackend.getServerId(client.get('hostId')) )
				encryptedPcpatchPass = self.__writeBackend.getPcpatchPassword( self.__writeBackend.getServerId(client.get('hostId')) )
				self.__writeBackend.setPcpatchPassword( client.get('hostId'), Tools.blowfishEncrypt(opsiHostKey, Tools.blowfishDecrypt(serverKey, encryptedPcpatchPass)) )
			
			except Exception, e:
				logger.error(e)
				raise
		
	def deleteGroups(self):
		logger.info("Deleting groups")
		self.__progressSubject.setMessage("Deleting groups.")
		for groupId in self.__writeBackend.getGroupIds_list():
			self.__writeBackend.deleteGroup(groupId)
		
	def replicateGroups(self):
		logger.info("Replicating groups")
		self.__progressSubject.setMessage("Replicating groups.")
		knownClientIds = self.getClientIds()
		groupIds = self.getGroupIds()
		for i in range(len(groupIds)):
			groupId = groupIds[i]
			logger.info("      Converting group '%s' (%s/%s)" % (groupId, i+1, len(groupIds)) )
			self.__progressSubject.setMessage("      Converting group '%s' (%s/%s)" % (groupId, i+1, len(groupIds)) )
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
	
	def deleteGeneralConfigs(self):
		logger.info("Deleting general configs")
		self.__progressSubject.setMessage("Deleting general configs.")
		self.__writeBackend.deleteGeneralConfig(self.__writeBackend.getServerId())
		for clientId in self.__writeBackend.getClientIds_list():
			try:
				self.__writeBackend.deleteGeneralConfig(clientId)
			except Exception, e:
				logger.error(e)
				raise
		
	def replicateGeneralConfigs(self):
		logger.info("Replicating general configs")
		self.__progressSubject.setMessage("Replicating general configs.")
		generalConfig = self.__readBackend.getGeneralConfig_hash()
		self.__writeBackend.setGeneralConfig(generalConfig)
		for clientId in self.getClientIds():
			logger.info("      Searching general config for client '%s'" % clientId)
			self.__progressSubject.setMessage("      Searching general config for client '%s'" % clientId)
			
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
				logger.info("            Converting general config")
				self.__progressSubject.setMessage("            Converting general config.")
				self.__writeBackend.setGeneralConfig(gc , clientId)
	
	def deleteNetworkConfigs(self):
		logger.info("Deleting network configs")
		self.__progressSubject.setMessage("Deleting network configs.")
		self.__writeBackend.deleteNetworkConfig(self.__writeBackend.getServerId())
		for clientId in self.__writeBackend.getClientIds_list():
			try:
				self.__writeBackend.deleteNetworkConfig(clientId)
			except Exception, e:
				logger.error(e)
				raise
	
	def replicateNetworkConfigs(self):
		logger.info("Replicating network configs")
		self.__progressSubject.setMessage("Replicating network configs.")
		networkConfig = self.__readBackend.getNetworkConfig_hash()
		if self.__newServerId:
			networkConfig['opsiServer'] = self.__newServerId
			if (networkConfig.get('depotId') == self.__oldServerId):
				networkConfig['depotId'] = self.__newServerId
		
		self.__writeBackend.setNetworkConfig(networkConfig)
		
		for clientId in self.getClientIds():
			logger.info("      Searching network config for client '%s'" % clientId)
			self.__progressSubject.setMessage("      Searching network config for client '%s'" % clientId)
			
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
				logger.info("            Converting network config")
				self.__progressSubject.setMessage("            Converting network config.")
				self.__writeBackend.setNetworkConfig(nc , clientId)
	
	def deleteProducts(self):
		logger.info("Deleting products")
		self.__progressSubject.setMessage("Deleting products.")
		for depotId in self.__writeBackend.getDepotIds_list():
			for productId in self.__writeBackend.getProductIds_list(objectId = depotId):
				self.__writeBackend.deleteProduct(productId = productId, depotIds = [ depotId ])
		
	def replicateProducts(self):
		objectId=None
		depotIds = self.getDepotIds()
		for i in range(len(depotIds)):
			depotId = depotIds[i]
			newDepotId = depotId
			if self.__newServerId and (self.__oldServerId == depotId):
				newDepotId = self.__newServerId
			for type in ('netboot', 'localboot'):
				logger.info("Converting %s products on depot '%s'." % (type, depotId) )
				self.__progressSubject.setMessage("Converting %s products on depot '%s'." % (type, depotId) )
				productIds = self.getProductIds(productType = type, depotId = depotId)
				for j in range(len(productIds)):
					productId = productIds[j]
					logger.info("      Converting product '%s' of depot '%s' (%s/%s)" % (productId, depotId, j+1, len(productIds)) )
					self.__progressSubject.setMessage("      Converting product '%s' of depot '%s' (%s/%s)" % (productId, depotId, j+1, len(productIds)) )
					
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
						logger.info("            Converting product dependency '%s'" \
							% dependency.get('requiredProductId', dependency.get('requiredProductClassId')) )
						self.__progressSubject.setMessage("            Converting product dependency '%s'" \
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
						logger.info("            Converting product property definition '%s'" % definition.get('name') )
						self.__progressSubject.setMessage("            Converting product property definition '%s'" % definition.get('name') )
						self.__writeBackend.createProductPropertyDefinition(
								productId 	= productId,
								name		= definition.get('name'),
								description	= definition.get('description'),
								defaultValue	= definition.get('default'),
								possibleValues	= definition.get('values'),
								depotIds	= [ newDepotId ] )
				self.__progressSubject.setMessage("")
	
	def replicateProductStates(self):
		logger.info("Replicating product states")
		self.__progressSubject.setMessage("Replicating product states.")
		
		clientIds = self.getClientIds()
		i = 0
		for (clientId, states) in self.__readBackend.getProductStates_hash(clientIds, {}).items():
			depotId = self.__writeBackend.getDepotId(clientId)
			productIds = self.getProductIds(depotId = depotId)
			i += 1
			logger.info("      Converting product states of client '%s' (%s/%s)" % ( clientId, i, len(clientIds) ) )
			self.__progressSubject.setMessage("      Converting product states of client '%s' (%s/%s)" % ( clientId, i, len(clientIds) ) )
			for state in states:
				if state.get('productId') not in productIds:
					logger.debug("Skipping product state replication of product '%s': product not installed on depot" % state.get('productId'))
					continue
				
				self.__progressSubject.setMessage("               Converting product state for product '%s' on '%s' (%s/%s)" \
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
							licenseKey = "" )
					#self.__writeBackend.setProductInstallationStatus(state.get('productId'), hostId, state.get('installationStatus'))
					#if state.get('actionRequest') and state.get('actionRequest') not in ('undefined', 'none'):
					#	self.__writeBackend.setProductActionRequest(state.get('productId'), hostId, state.get('actionRequest'))
				except Exception, e:
					logger.error(e)
					raise
	
	def replicateProductProperties(self):
		logger.info("Replicating product properties.")
		self.__progressSubject.setMessage("Replicating product properties.")
		for depotId in self.getDepotIds():
			i = 0
			productIds = self.getProductIds(depotId = depotId)
			clientIds = self.getClientIds(depotIds = [ depotId ])
			newDepotId = depotId
			if self.__newServerId and (self.__oldServerId == depotId):
				newDepotId = self.__newServerId
			for productId in productIds:
				i += 1
				logger.info("      Replicating product properties for product '%s' (%s/%s)" % (productId, i, len(productIds)) )
				self.__progressSubject.setMessage("      Replicating product properties for product '%s' (%s/%s)" % (productId, i, len(productIds)) )
				productProperties = self.__readBackend.getProductProperties_hash(productId, objectId = depotId)
				try:
					self.__writeBackend.setProductProperties(productId, productProperties, objectId = newDepotId)
				except Exception, e:
					logger.error(e)
					raise
				
				for clientId in clientIds:
					logger.info("            Replicating product properties for product '%s' on '%s' (%s/%s)" % (productId, clientId, i, len(productIds)) )
					self.__progressSubject.setMessage("            Replicating product properties for product '%s' on '%s' (%s/%s)" % (productId, clientId, i, len(productIds)) )
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



