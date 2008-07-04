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

__version__ = '0.9.8.6'

# Imports
import socket, re
import copy as pycopy
from OPSI import Product
from OPSI.Logger import *

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





