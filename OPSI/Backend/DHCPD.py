#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - DHCPD   =
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
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '4.0'

# Imports
import socket, threading

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI import System
from OPSI.Backend.Backend import *
from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Util.File import DHCPDConfFile

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                    CLASS DHCPDBACKEND                                              =
# ======================================================================================================
class DHCPDBackend(ConfigDataBackend):
	
	def __init__(self, **kwargs):
		self._name = 'dhcpd'
		
		ConfigDataBackend.__init__(self, **kwargs)
		
		self._dhcpdConfigFile         = u'/etc/dhcp3/dhcpd.conf'
		self._reloadConfigCommand     = u'/usr/bin/sudo /etc/init.d/dhcp3-server restart'
		self._fixedAddressFormat      = u'IP'
		self._defaultClientParameters = { 'next-server': socket.gethostbyname(socket.getfqdn()), 'filename': u'linux/pxelinux.0' }
		self._dhcpdOnDepot            = False
		
		# Parse arguments
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('dhcpdconfigfile',):
				self._dhcpdConfigFile = value
			elif option in ('reloadconfigcommand',):
				self._reloadConfigCommand = value
			elif option in ('defaultclientparameters',):
				self._defaultClientParameters = value
			elif option in ('fixedaddressformat',):
				if value not in (u'IP', u'FQDN'):
					raise BackendBadValueError(u"Bad value '%s' for fixedAddressFormat, possible values are %s" \
									% (value, u', '.join(['IP', 'FQDN'])) )
				self._fixedAddressFormat = value
			elif option in ('dhcpdondepot',):
				self._dhcpdOnDepot = forceBool(value)
			
		if self._defaultClientParameters.get('next-server') and self._defaultClientParameters['next-server'].startswith(u'127'):
			raise BackendBadValueError(u"Refusing to use ip address '%s' as default next-server" % self._defaultClientParameters['next-server'])
		
		self._dhcpdConfFile = DHCPDConfFile(self._dhcpdConfigFile)
		self._reloadEvent = threading.Event()
		self._reloadEvent.set()
		self._reloadLock = threading.Lock()
		self._reloadThread = None 
		self._depotId = forceHostId(socket.getfqdn())
		self._opsiHostKey = None
		self._depotConnections  = {}
		
	def _triggerReload(self):
		if not self._reloadConfigCommand:
			return
		if not self._reloadEvent.isSet():
			return
		class ReloadThread(threading.Thread):
			def __init__(self, reloadEvent, reloadLock, reloadConfigCommand):
				threading.Thread.__init__(self)
				self._reloadEvent = reloadEvent
				self._reloadLock = reloadLock
				self._reloadConfigCommand = reloadConfigCommand
				
			def run(self):
				self._reloadEvent.clear()
				self._reloadEvent.wait(2)
				self._reloadLock.acquire()
				try:
					result = System.execute(self._reloadConfigCommand)
					for line in result:
						if (line.find(u'error') != -1):
							raise Exception(u'\n'.join(result))
				except Exception, e:
					logger.critical("Failed to restart dhcpd: %s" % e)
				self._reloadLock.release()
				self._reloadEvent.set()
		self._reloadThread = ReloadThread(self._reloadEvent, self._reloadLock, self._reloadConfigCommand)
		self._reloadThread.start()
	
	def _getDepotConnection(self, depotId):
		depotId = forceHostId(depotId)
		if (depotId == self._depotId):
			return self
		if not self._depotConnections.get(depotId):
			if not self._opsiHostKey:
				depots = self._context.host_getObjects(id = self._depotId)
				if not depots or not depots[0].getOpsiHostKey():
					raise BackendMissingDataError(u"Failed to get opsi host key for depot '%s': %s" % (self._depotId, e))
				self._opsiHostKey = depots[0].getOpsiHostKey()
			try:
				self._depotConnections[depotId] = JSONRPCBackend(
									address  = u'https://%s:4447/rpc/backend/%s' % (depotId, self._name),
									username = self._depotId,
									password = self._opsiHostKey)
			except Exception, e:
				raise Exception(u"Failed to connect to depot '%s': %s" % (depotId, e))
			
		return self._depotConnections[depotId]
	
	def _getResponsibleDepotId(self, clientId):
		configStates = self._context.configState_getObjects(configId = u'clientconfig.depot.id', objectId = clientId)
		if configStates and configStates[0].values:
			depotId = configStates[0].values[0]
		else:
			configs = self._context.config_getObjects(id = u'clientconfig.depot.id')
			if not configs or not configs[0].defaultValues:
				raise Exception(u"Failed to get depotserver for client '%s', config 'clientconfig.depot.id' not set and no defaults found" % clientId)
			depotId = configs[0].defaultValues[0]
		return depotId
	
	def backend_exit(self):
		if self._reloadThread:
			self._reloadThread.join(10)
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def dhcpd_updateHost(self, host):
		host = forceObjectClass(host, Host)
		if not host.hardwareAddress:
			logger.warning(u"Cannot update dhcpd configuration for client %s: hardware address unknown" % host)
			return
		ipAddress = host.ipAddress
		if not ipAddress:
			try:
				logger.info(u"Ip addess of client %s unknown, trying to get host by name" % host)
				ipAddress = socket.gethostbyname(host.id)
				logger.info(u"Client fqdn resolved to '%s'" % ipAddress)
			except Exception, e:
				raise BackendIOError(u"Cannot update dhcpd configuration for client %s: ip address unknown and failed to get host by name" % host.id)
		
		if self._dhcpdOnDepot:
			depotId = self._getResponsibleDepotId(host.id)
			
			if (depotId != self._depotId):
				logger.info(u"Not responsible for client '%s', forwarding request to depot '%s'" % (host.id, depotId))
				return self._getDepotConnection(depotId).dhcpd_updateHost(host.id)
		
		fixedAddress = ipAddress
		if (self._fixedAddressFormat == 'FQDN'):
			fixedAddress = host.id
		
		self._reloadLock.acquire()
		try:
			self._dhcpdConfFile.parse()
			currentHostParams = self._dhcpdConfFile.getHost(host.id.split('.')[0])
			if currentHostParams and (currentHostParams.get('hardware', ' ').split(' ')[1] == host.hardwareAddress) and (currentHostParams.get('fixed-address') == fixedAddress):
				logger.debug(u"DHCPD config of host '%s' unchanged, no need to update config file" % host)
				self._reloadLock.release()
				return
			self._dhcpdConfFile.addHost(
				hostname        = host.id.split('.')[0],
				hardwareAddress = host.hardwareAddress,
				ipAddress       = ipAddress,
				fixedAddress    = fixedAddress,
				parameters      = self._defaultClientParameters)
			self._dhcpdConfFile.generate()
		except Exception, e:
			logger.error(e)
		self._reloadLock.release()
		self._triggerReload()
	
	def dhcpd_deleteHost(self, host):
		host = forceObjectClass(host, Host)
		
		if self._dhcpdOnDepot:
			depotId = self._getResponsibleDepotId(host.id)
			if (depotId != self._depotId):
				logger.info(u"Not responsible for client '%s', forwarding request to depot '%s'" % (host.id, depotId))
				return self._getDepotConnection(depotId).dhcpd_deleteHost(host.id)
		
		if not self._dhcpdConfFile.getHost(host.id.split('.')[0]):
			return
		self._dhcpdConfFile.deleteHost(host.id.split('.')[0])
		self._dhcpdConfFile.generate()
		self._triggerReload()
	
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_insertObject(self, host):
		if not isinstance(host, OpsiClient):
			return
		
		logger.debug(u"host_insertObject %s" % host)
		self.dhcpd_updateHost(host)
		
	def host_updateObject(self, host):
		if not isinstance(host, OpsiClient):
			return
		
		if not host.ipAddress and not host.hardwareAddress:
			# Not of interest
			return
		
		logger.debug(u"host_updateObject %s" % host)
		try:
			self.dhcpd_updateHost(host)
		except Exception, e:
			logger.info(e)
		
	def host_deleteObjects(self, hosts):
		
		logger.debug(u"host_deleteObjects %s" % hosts)
		
		self._dhcpdConfFile.parse()
		errors = []
		for host in hosts:
			if not isinstance(host, OpsiClient):
				continue
			try:
				self.dhcpd_deleteHost(host)
			except Exception, e:
				errors.append(forceUnicode(e))
		if errors:
			raise Exception(u', '.join(errors))
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	#def configState_insertObject(self, configState):
	#	if (configState.configId != 'clientconfig.depot.id'):
	#		return
	#	
	#def configState_updateObject(self, configState):
	#	if (configState.configId != 'clientconfig.depot.id'):
	#		return
	#	
	#def configState_deleteObjects(self, configStates):
	#	for configState in configStates:
	#		if (configState.configId != 'clientconfig.depot.id'):
	#			continue
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	

