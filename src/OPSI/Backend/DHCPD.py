#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - DHCPD   =
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

__version__ = '0.5.5.5'

# Imports
import re, socket, time

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Backend.File import File
from OPSI.Logger import *
from OPSI import Tools
from OPSI import System

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                     CLASS DHCPDBACKEND                                             =
# ======================================================================================================
class DHCPDBackend(Backend):
	''' 
	This class implements parts of the abstract class Backend 
	
	You will have to add something like
	username ALL=NOPASSWD: /etc/init.d/dhcp3-server restart
	to the /etc/sudoers file to allow the user running this Module to restart the dhcp-server
	'''
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' DHCPDBackend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		self._dhcpdConfigFile = '/etc/dhcp3/dhcpd.conf'
		self._reloadConfigCommand = '/usr/bin/sudo /etc/init.d/dhcp3-server restart'
		self._fixedAddressFormat = 'IP'
		self._defaultClientParameters = { 'next-server': socket.gethostbyname(socket.gethostname()), 'filename': 'linux/pxelinux.0' }
		self._defaultDomain = 'uib.local'
		
		for (option, value) in args.items():
			if   (option.lower() == 'dhcpdconfigfile'):		self._dhcpdConfigFile = value
			elif (option.lower() == 'reloadconfigcommand'): 	self._reloadConfigCommand = value
			elif (option.lower() == 'defaultclientparameters'): 	self._defaultClientParameters = value
			elif (option.lower() == 'defaultdomain'): 		self._defaultDomain = value
			elif (option.lower() == 'fixedaddressformat'):
				if value not in ['IP', 'FQDN']:
					raise BackendBadValueError("Bad value '%s' for fixedAddressFormat, possible values are %s" \
									% (value, ', '.join(['IP', 'FQDN'])) )
				self._fixedAddressFormat = value
			else:
				logger.warning("Unknown argument '%s' passed to DHCPBackend constructor" % option)
	
	def getMacAddresses_list(self, hostId):
		''' Get host's mac address from dhcpd config '''
		hostId = self._preProcessHostId(hostId)
		
		conf = Config(self._dhcpdConfigFile)
		host = conf.getHost( self.getHostname(hostId) )
		
		if not host or not host.has_key('hardware'):
			return []
		
		logger.info("Returning mac addresses: [ %s ]" % host['hardware'].split()[1].lower())
		
		return [ host['hardware'].split()[1].lower() ]
	
	def getMacAddress(self, hostId):
		macs = self.getMacAddresses_list(hostId)
		if macs:
			return macs[0]
		return ''
	
	def setMacAddresses(self, hostId, macs=[]):
		hostId = self._preProcessHostId(hostId)
		
		logger.info("Setting mac addresses for host '%s'" % hostId)
		
		if not macs:
			raise BackendBadValueError("No mac address given")
		if (len(macs) > 1):
			raise BackendBadValueError("More than one mac address given, not supported by DHCPD backend")
		
		hardwareAddress = macs[0].lower()
		if not re.search('^[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}$', hardwareAddress):
			raise BackendBadValueError("Bad hardware ethernet address '%s'" % hardwareAddress)
		
		conf = Config(self._dhcpdConfigFile)
		host = None
		try:
			host = conf.getHost( self.getHostname(hostId) )
		except BackendMissingDataError, e:
			#raise BackendMissingDataError("Host '%s' not found in dhcpd configuration" % hostId)
			logger.warning("Host '%s' not found in dhcpd configuration, trying to create" % hostId)
			self.createClient(
				clientName	= hostId.split('.')[0],
				domain		= '.'.join(hostId.split('.')[1:]),
				hardwareAddress	= hardwareAddress
			)
			return
			
		
		# example: {'hardware': 'ethernet 00:01:01:01:01:01', 'fixed-address': 'test.uib.local', 'next-server': '192.168.1.1', 'filename': 'linux/pxelinux.0'}
		if (host.get('hardware', '') == "ethernet %s" % hardwareAddress):
			return
		
		host['hardware'] = "ethernet %s" % hardwareAddress
		
		try:
			conf.modifyHost(hostname = self.getHostname(hostId), parameters = host)
		except Exception, e:
			logger.error(e)
			raise
		
		conf.writeConfig()
		self._restartDhcpd()
		
	def createClient(self, clientName, domain = None, description = None, notes = None, ipAddress = None, hardwareAddress = None):
		if not hardwareAddress:
			logger.error("Hardware ethernet address not specified")
			return
			#raise BackendBadValueError("Hardware ethernet address not specified")
		hardwareAddress = hardwareAddress.lower()
		clientName = clientName.lower()
		if not re.search('^[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}$', hardwareAddress):
			raise BackendBadValueError("Bad hardware ethernet address '%s'" % hardwareAddress)
		
		if not domain:
			domain = self._defaultDomain
		domain = domain.lower()
		if not ipAddress:
			ipAddress = socket.gethostbyname("%s.%s" % (clientName, domain))
			if not re.search('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ipAddress):
				raise BackendIOError("Failed to resolve %s.%s" % (clientName, domain))
			
		if not re.search('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ipAddress):
			raise BackendBadValueError("Bad ipaddress '%s'" % ipAddress)
		
		conf = Config(self._dhcpdConfigFile)
		fixedAddress = ipAddress
		if (self._fixedAddressFormat == 'FQDN'):
			fixedAddress = '%s.%s' % (clientName, domain)
		conf.addHost(hostname=clientName, hardwareAddress=hardwareAddress, ipAddress=ipAddress, fixedAddress=fixedAddress, parameters = dict(self._defaultClientParameters))
		conf.writeConfig()
		self._restartDhcpd()
	
	def deleteClient(self, clientId):
		clientId = self._preProcessHostId(clientId)
		conf = Config(self._dhcpdConfigFile)
		try:
			conf.deleteHost( hostname = self.getHostname(clientId) )
		except BackendMissingDataError:
			# Client does not exists
			return
		conf.writeConfig()
		self._restartDhcpd()
	
	def setIpAddress(self, hostId, ipAddress):
		hostId = self._preProcessHostId(hostId)
		
		logger.info("Setting ip address for host '%s'" % hostId)
		
		if not ipAddress:
			raise BackendBadValueError("No ip address given")
		
		if not re.search('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ipAddress):
			raise BackendBadValueError("Bad ipaddress '%s'" % ipAddress)
		
		conf = Config(self._dhcpdConfigFile)
		host = conf.getHost( self.getHostname(hostId) )
		host['fixed-address'] = ipAddress
		
		try:
			conf.modifyHost(hostname = self.getHostname(hostId), parameters = host)
		except Exception, e:
			logger.error(e)
			raise
		
		conf.writeConfig()
		self._restartDhcpd()
	
	def setNetworkConfig(self, config, objectId = None):
		depotIp = None
		for (key, value) in config.items():
			key = key.lower()
			if (key == 'depotid'):
				depotIp = socket.gethostbyname(value)
		if not depotIp:
			return
		
		conf = Config(self._dhcpdConfigFile)
		try:
			objectId = self._preProcessHostId(objectId)
			host = conf.getHost( self.getHostname(objectId) )
		except BackendMissingDataError, e:
			return
		
		# example: {'hardware': 'ethernet 00:01:01:01:01:01', 'fixed-address': 'test.uib.local', 'next-server': '192.168.1.1', 'filename': 'linux/pxelinux.0'}
		if (host.get('next-server', '') == depotIp):
			return
		
		host['next-server'] = depotIp
		
		try:
			conf.modifyHost(hostname = self.getHostname(objectId), parameters = host)
		except Exception, e:
			logger.error(e)
			raise
		
		conf.writeConfig()
		self._restartDhcpd()

	def _restartDhcpd(self):
		if self._reloadConfigCommand:
			# thread-safe
			lockfile = '/var/lock/opsi-dhcpd-restart.lock'
			lf = None
			try:
				f = File()
				try:
					lf = f.openFile(lockfile, mode = 'w')
				except BackendIOError:
					# File missing?
					f.createFile(lockfile, mode = 0666)
					lf = f.openFile(lockfile, mode = 'w')
				# File successfuly locked
				result = System.execute(self._reloadConfigCommand)
				for line in result:
					if (line.find('error') != -1):
						raise Exception('\n'.join(result))
				lf.close()
			except Exception, e:
				if lf: lf.close()
				raise BackendIOError("Failed to restart dhcpd: %s" % e)
		
class Config(File):
	''' This class parses an generates dhcpd.conf files '''
	def __init__(self, configFile):
		File.__init__(self)
		self._configFile = configFile
		self._parsed = False
	
	def _parseConfig(self):
		''' This method parses the dhcpd.conf file. '''
		logger.info("Parsing dhcpd config file '%s'" % self._configFile)
		# Open dhcpd.conf, read and close it.
		f = self.openFile(self._configFile, mode = 'r')
		self._lines = f.readlines()
		f.close()
		
		self._currentBlock = self._globalBlock = GlobalBlock()
		self._globalBlock.endLine = len(self._lines)
		
		self._currentData = ''
		self._currentLine = 0
		
		while ( self._currentLine < len(self._lines) ):
			newData = ''
			
			while ( not newData and self._currentLine < len(self._lines) ):
				# Read next line
				newData = self._lines[self._currentLine]
				self._currentLine += 1
				self._currentData += newData
			while (True):
				if re.search('^\s*\n$', self._currentData):
					# The line is empty
					logger.debug2("Empty line: %s" % self._currentData.rstrip())
					self._currentBlock.addComponent(
						EmptyLine(
							startLine = self._currentLine,
							parentBlock = self._currentBlock ) )
					self._currentData = ''
				
				self._currentData = self._currentData.lstrip()
				if ( self._currentData.startswith('#')):
					# The line is a comment
					logger.debug2("Comment: %s" % self._currentData.rstrip())
					self._currentBlock.addComponent(
						Comment(
							startLine = self._currentLine,
							parentBlock = self._currentBlock,
							data = self._currentData[1:].rstrip()) )
					self._currentData = ''
				
				elif ( self._currentData.find('{') != -1 ):
					# Start of a block
					logger.debug2("Start block: %s" % self._currentData.rstrip())
					match = re.search('^([^{]+){(.*)$', self._currentData)
					if not match:
						raise BackendIOError("Parse error in file '%s' line %d: %s" % (self._configFile, self._currentLine, self._currentData) )
					
					# Keep the rest of the line
					self._currentData = match.group(2)
					
					# Split the block definition at whitespace
					# The first value is the block type
					# Example: subnet 194.31.185.0 netmask 255.255.255.0 => type is subnet
					block = Block(
						startLine = self._currentLine,
						parentBlock = self._currentBlock,
						type = match.group(1).split()[0].strip(),
						settings = match.group(1).split() )
					self._currentBlock.addComponent(block)
					self._currentBlock = block
				
				elif ( self._currentData.find(';') != -1 ) and ( self._currentData.find('}') == -1 ):
					if (self._currentData.find(';') == 0):
						self._currentData = self._currentData[1:]
						continue
					# Parameter
					logger.debug2("Parameter: %s" % self._currentData.rstrip())
					match = re.search('^([^;]+);\s*(.*)$', self._currentData)
					if not match:
						raise BackendIOError("Parse error in file '%s' line %d: %s" % (self._configFile, self._currentLine, self._currentData) )
					
					parameter = match.group(1).split()
					# Keep the rest of the line (after ';')
					self._currentData = match.group(2)
					
					isOption = False
					key = match.group(1).split()[0]
					value = ' '.join(match.group(1).split()[1:]).strip()
					if value.startswith('"') and value.endswith('"'):
						value = value.replace('"', '')
					if (key == 'option'):
						isOption = True
						key = match.group(1).split()[1]
						value = ' '.join(match.group(1).split()[2:])
						values = []
						quote = ''
						current = ''
						for l in value:
							if (l == '"'):
								if (quote == '"'):
									quote = ''
								elif (quote == "'"):
									current += l
								else:
									quote = '"'
							elif (l == "'"):
								if (quote == "'"):
									quote = ''
								elif (quote == '"'):
									current += l
								else:
									quote = "'"
							elif re.search('\s', l):
								#if quote:
								current += l
							elif (l == ','):
								if quote:
									current += l
								else:
									values.append(current)
									current = ''
							else:
								current += l
						if current:
							values.append(current)
						value = values
						for i in range(len(values)):
							values[i] = values[i].strip()
						
					if isOption:
						self._currentBlock.addComponent(
							Option(
								startLine = self._currentLine,
								parentBlock = self._currentBlock,
								key = key,
								value = value ) )
					else:
						self._currentBlock.addComponent(
							Parameter(
								startLine = self._currentLine,
								parentBlock = self._currentBlock,
								key = key,
								value = value ) )
				
				elif ( self._currentData.find('}') != -1 ):
					# End of a block
					logger.debug2("End block: %s" % self._currentData.rstrip())
					match = re.search('^([^}]*)}(.*)$', self._currentData)
					if not match:
						raise BackendIOError("Parse error in file '%s' line %d: %s" % (self._configFile, self._currentLine, self._currentData) )
					
					# Keep the rest of the line
					self._currentData = match.group(2)
					self._currentBlock.endLine = self._currentLine
					
					# Set the current context back to the blocks parent
					self._currentBlock = self._currentBlock.parentBlock
				
				else:
					break
				
		self._parsed = True
		return True
	
	def writeConfig(self):
		logger.info("Writing dhcpd config file '%s'" % self._configFile)
		f = self.openFile(self._configFile, mode = 'w')
		f.write(self._globalBlock.asText())
		f.close()

	def getHost(self, hostname):
		if not self._parsed:
			# Parse dhcpd.conf
			self._parseConfig()
		
		logger.info("Searching host '%s' in dhcpd config file '%s'" % (hostname, self._configFile))
		hostBlocks = []
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				hostBlocks.append(block)
			#else:
			#	for (key, value) in block.getParameters_hash().items():
			#		if (key == 'fixed-address') and (value == hostname):
			#			hostBlocks.append(block)
		if (len(hostBlocks) < 1):
			raise BackendMissingDataError("Host '%s' not found" % hostname)
		if (len(hostBlocks) > 1):
			raise BackendIOError("Host '%s' more than one (%s) times" % (hostname, len(hostBlocks)))
		# Return inherited options up to group as hash
		return hostBlocks[0].getParameters_hash(inherit = 'group')
		
	def addHost(self, hostname, hardwareAddress, ipAddress, fixedAddress, parameters = {}):
		hardwareAddress = hardwareAddress.lower()
		fixedAddress = fixedAddress.lower()
		if not self._parsed:
			# Parse dhcpd.conf
			self._parseConfig()
		
		logger.info("Creating host '%s', hardwareAddress '%s', ipAddress '%s', fixedAddress '%s', parameters '%s'" % \
					(hostname, hardwareAddress, ipAddress, fixedAddress, parameters) )
		
		existingHost = None
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				existingHost = block
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value.lower() == fixedAddress):
						raise BackendBadValueError("The host '%s' uses the same fixed address" % block.settings[1])
					elif (key == 'hardware') and (value.lower() == 'ethernet %s' % hardwareAddress):
						raise BackendBadValueError("The host '%s' uses the same hardware ethernet address" % block.settings[1])
		if existingHost:
			logger.warning("Host '%s' already exists in config file '%s', deleting first" % (hostname, self._configFile))
			self.deleteHost(hostname)
		
		for (key, value) in parameters.items():
			parameters[key] = Parameter(-1, None, key, value).asHash()[key]
		
		# Calculate bitmask of host's ipaddress
		n = ipAddress.split('.')
		for i in range(4):
			n[i] = int(n[i])	
		ip = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
		
		# Default parent block is global
		parentBlock = self._globalBlock
		
		# Search the right subnet block
		for block in self._globalBlock.getBlocks('subnet'):
			# Calculate bitmask of subnet
			n = (block.settings[1]).split('.')
			for i in range(4):
				n[i] = int(n[i])
			network = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
			n = (block.settings[3]).split('.')
			for i in range(4):
				n[i] = int(n[i])
			netmask = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
			
			wildcard = netmask ^ 0xFFFFFFFFL
			if (wildcard | ip == wildcard | network):
				# Host matches the subnet
				parentBlock = block
		
		# Search the right group for the host
		bestGroup = None
		bestMatchCount = 0
		for block in parentBlock.getBlocks('group'):
			matchCount = 0
			blockParameters = block.getParameters_hash(inherit = 'global')
			if blockParameters:
				# Block has parameters set, check if they match the hosts parameters
				for (key, value) in blockParameters.items():
					if not parameters.has_key(key):
						continue
					if (parameters[key] == value):
						matchCount += 1
					else:
						matchCount -= 1
			
			if (matchCount > bestMatchCount) or (matchCount >= 0 and not bestGroup):
				matchCount = bestMatchCount
				bestGroup = block
		
		if bestGroup:
			parentBlock = bestGroup
		
		# Remove parameters which are already defined in parents
		blockParameters = parentBlock.getParameters_hash(inherit = 'global')
		if blockParameters:
			for (key, value) in blockParameters.items():
				if parameters.has_key(key) and (parameters[key] == value):
					del parameters[key]
		
		hostBlock = Block(	startLine = -1,
					parentBlock = parentBlock,
					type = 'host',
					settings = ['host', hostname] )
		hostBlock.addComponent( Parameter( startLine = -1, parentBlock = hostBlock, key = 'fixed-address', value = fixedAddress ) )
		hostBlock.addComponent( Parameter( startLine = -1, parentBlock = hostBlock, key = 'hardware', value = "ethernet %s" % hardwareAddress ) )
		for (key, value) in parameters.items():
			hostBlock.addComponent(
				Parameter( startLine = -1, parentBlock = hostBlock, key = key, value = value ) )
		
		parentBlock.addComponent(hostBlock)
	
	def deleteHost(self, hostname):
		if not self._parsed:
			# Parse dhcpd.conf
			self._parseConfig()
		
		logger.notice("Deleting host '%s' from dhcpd config file '%s'" % (hostname, self._configFile))
		hostBlocks = []
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				hostBlocks.append(block)
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value == hostname):
						hostBlocks.append(block)
		if (len(hostBlocks) < 1):
			raise BackendMissingDataError("Host '%s' not found" % hostname)
		
		for block in hostBlocks:
			block.parentBlock.removeComponent(block)
	
	def modifyHost(self, hostname, parameters):
		if not self._parsed:
			# Parse dhcpd.conf
			self._parseConfig()
		
		logger.notice("Modifying host '%s' in dhcpd config file '%s'" % (hostname, self._configFile))
		
		hostBlocks = []
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				hostBlocks.append(block)
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value == hostname):
						hostBlocks.append(block)
					elif (key == 'hardware') and (value.lower() == parameters.get('hardware')):
						raise BackendBadValueError("The host '%s' uses the same hardware ethernet address" % block.settings[1])
		if (len(hostBlocks) != 1):
			raise BackendBadValueError("Host '%s' found %d times" % (hostname, len(hostBlocks)))
		
		hostBlock = hostBlocks[0]
		hostBlock.removeComponents()
		
		for (key, value) in parameters.items():
			parameters[key] = Parameter(-1, None, key, value).asHash()[key]
		
		for (key, value) in hostBlock.parentBlock.getParameters_hash(inherit = 'global').items():
			if not parameters.has_key(key):
				continue
			if (parameters[key] == value):
				del parameters[key]
		
		for (key, value) in parameters.items():
			hostBlock.addComponent(
				Parameter( startLine = -1, parentBlock = hostBlock, key = key, value = value ) )
		
class Component:
	def __init__(self, startLine, parentBlock):
		self.startLine = startLine
		self.endLine = startLine
		self.parentBlock = parentBlock
	
	def getShifting(self):
		shifting = ''
		if not self.parentBlock:
			return shifting
		parentBlock = self.parentBlock.parentBlock
		while(parentBlock):
			shifting += '\t'
			parentBlock = parentBlock.parentBlock
		return shifting
	
	def asText(self):
		return self.getShifting()
	
class Parameter(Component):
	def __init__(self, startLine, parentBlock, key, value):
		Component.__init__(self, startLine, parentBlock)
		self.key = key
		self.value = value
		if type(self.value) is str:
			if self.value.lower() in ['yes', 'true', 'on']:
				self.value = True
			elif self.value.lower() in ['no', 'false', 'off']:
				self.value = False
	
	def asText(self):
		value = self.value
		if type(value) is bool:
			if value:
				value = 'on'
			else:
				value = 'off'
		elif self.key in ['filename', 'ddns-domainname'] or \
		     re.match('.*[\'/\\\].*', value) or \
		     re.match('^\w+\.\w+$', value) or \
		     self.key.endswith('-name'):
			value = '"%s"' % value
		return "%s%s %s;" % (self.getShifting(), self.key, value)
	
	def asHash(self):
		return { self.key: self.value }
	
class Option(Component):
	def __init__(self, startLine, parentBlock, key, value):
		Component.__init__(self, startLine, parentBlock)
		self.key = key
		if not type(value) is list:
			value = [ value ]
		self.value = value
	
	def asText(self):
		text = "%soption %s " % (self.getShifting(), self.key)
		for i in range(len(self.value)):
			value = self.value[i]
			if re.match('.*[\'/\\\].*', value) or \
			   re.match('^\w+\.\w+$', value) or \
			   self.key.endswith('-name') or \
			   self.key.endswith('-identifier'):
				value = '"%s"' % value
			if (i+1 < len(self.value)):
				value += ', '
			text += value
		return text + ';'
	
	def asHash(self):
		return { self.key: self.value }
	
class Comment(Component):
	def __init__(self, startLine, parentBlock, data):
		Component.__init__(self, startLine, parentBlock)
		self.data = data
	
	def asText(self):
		return self.getShifting() + '#%s' % self.data
	
class EmptyLine(Component):
	def __init__(self, startLine, parentBlock):
		Component.__init__(self, startLine, parentBlock)
	
class Block(Component):
	def __init__(self, startLine, parentBlock, type, settings = []):
		Component.__init__(self, startLine, parentBlock)
		self.type = type
		self.settings = settings
		self.lineRefs = {}
		self.components = []
	
	def getComponents(self):
		return self.components
	
	def removeComponents(self):
		logger.debug("Removing components: %s" % self.components)
		for c in list(self.components):
			self.removeComponent(c)
			
	def addComponent(self, component):
		self.components.append(component)
		if not self.lineRefs.has_key(component.startLine):
			self.lineRefs[component.startLine] = []
		self.lineRefs[component.startLine].append(component)
	
	def removeComponent(self, component):
		index = -1
		for i in range(len(self.components)):
			if (self.components[i] == component):
				index = i
				break
		if (index < 0):
			raise BackendMissingDataError("Component '%s' not found")
		del self.components[index]
		index = -1
		
		if self.lineRefs.has_key(component.startLine):
			for i in range(len(self.lineRefs[component.startLine])):
				if (self.lineRefs[component.startLine][i] == component):
					index = i
					break
		if (index >= 0):
			del self.lineRefs[component.startLine][index]
		
	def getOptions_hash(self, inherit = None):
		options = {}
		for component in self.components:
			if not isinstance(component, Option):
				continue
			options[component.key] = component.value
		
		if inherit and (self.type != inherit) and self.parentBlock:
			for (key, value) in self.parentBlock.getOptions_hash(inherit).items():
				if not options.has_key(key):
					options[key] = value
		return options
	
	def getOptions(self, inherit = None):
		options = []
		for component in self.components:
			if not isinstance(component, Option):
				continue
			options.append(component)
		
		if inherit and (self.type != inherit) and self.parentBlock:
			options.extend(self.parentBlock.getOptions(inherit))
		
		return options
	
	def getParameters_hash(self, inherit = None):
		parameters = {}
		for component in self.components:
			if not isinstance(component, Parameter):
				continue
			parameters[component.key] = component.value
		
		if inherit and (self.type != inherit) and self.parentBlock:
			for (key, value) in self.parentBlock.getParameters_hash(inherit).items():
				if not parameters.has_key(key):
					parameters[key] = value
		return parameters
	
	def getParameters(self, inherit = None):
		parameters = []
		for component in self.components:
			if not isinstance(component, Parameter):
				continue
			options.append(component)
		
		if inherit and (self.type != inherit) and self.parentBlock:
			parameters.extend(self.parentBlock.getParameters(inherit))
		
		return parameters
	
	def getBlocks(self, type, recursive = False):
		blocks = []
		for component in self.components:
			if not isinstance(component, Block):
				continue
			if (component.type == type):
				blocks.append(component)
			if recursive:
				blocks.extend(component.getBlocks(type, recursive))
		return blocks
	
	def asText(self):
		text = ''
		shifting = self.getShifting()
		if not isinstance(self, GlobalBlock):
			text += shifting + ' '.join(self.settings) + ' {\n'
		
		notWritten = self.components
		lineNumber = self.startLine
		if (lineNumber < 1): lineNumber = 1
		while (lineNumber <= self.endLine):
			if not self.lineRefs.has_key(lineNumber) or not self.lineRefs[lineNumber]:
				lineNumber += 1
				continue
			for i in range(len(self.lineRefs[lineNumber])):
				compText = self.lineRefs[lineNumber][i].asText()
				if (i > 0) and isinstance(self.lineRefs[lineNumber][i], Comment):
					compText = ' ' + compText.lstrip()
				text += compText
				# Mark component as written
				index = -1
				for j in range(len(notWritten)):
					if (notWritten[j] == self.lineRefs[lineNumber][i]):
						index = j
						break
				if (index > -1):
					del notWritten[index]
				
			text += '\n'
			lineNumber += 1
		
		for component in notWritten:
			text += component.asText() + '\n'
		
		if not isinstance(self, GlobalBlock):
			# Write '}' to close block
			text += shifting + '}'
		return text
		
class GlobalBlock(Block):
	def __init__(self):
		Block.__init__(self, 1, None, 'global')
		
		
