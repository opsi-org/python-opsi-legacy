#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Backend   =
   = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008, 2009, 2010 uib GmbH
   
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
import types, new, inspect, socket, base64, os, threading
import copy as pycopy
from twisted.conch.ssh import keys
try:
	from hashlib import md5
except ImportError:
	from md5 import md5

if (os.name == 'posix'):
	from ldaptor.protocols import pureldap
	from ldaptor import ldapfilter

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Util import timestamp, compareVersions, blowfishDecrypt, blowfishEncrypt
from OPSI.Util.File import ConfigFile
import OPSI.SharedAlgorithm

logger = Logger()
OPSI_VERSION_FILE = u'/etc/opsi/version'
OPSI_MODULES_FILE = u'/etc/opsi/modules'
OPSI_PASSWD_FILE  = u'/etc/opsi/passwd'
LOG_DIR           = u'/var/log/opsi'

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                                                                                    =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

def getArgAndCallString(method):
	argString = u''
	callString = u''
	(args, varargs, varkwargs, argDefaults) = inspect.getargspec(method)
	#logger.debug2(u"args: %s" % unicode(args))
	#logger.debug2(u"varargs: %s" % unicode(varargs))
	#logger.debug2(u"varkwargs: %s" % unicode(varkwargs))
	#logger.debug2(u"argDefaults: %s" % unicode(argDefaults))
	for i in range(len(args)):
		#logger.debug2(u"Processing arg [%s] %s" % (i, args[i]))
		if (args[i] == 'self'):
			continue
		if (argString):
			argString += u', '
			callString += u', '
		argString += args[i]
		callString += u'%s=%s' % (args[i], args[i])
		if type(argDefaults) is tuple and (len(argDefaults) + i >= len(args)):
			default = argDefaults[len(argDefaults)-len(args)+i]
			if type(default) is str:
				default = u"'%s'" % default
			elif type(default) is unicode:
				default = u"u'%s'" % default
			#logger.debug2(u"   Using default [%s] %s" % (len(argDefaults)-len(args)+i, default))
			argString += u'=%s' % unicode(default)
	if varargs:
		for vararg in varargs:
			if argString:
				argString += u', '
				callString += u', '
			argString += u'*%s' % vararg
			callString += u'*%s' % vararg
	if varkwargs:
		if argString:
			argString += u', '
			callString += u', '
		argString += u'**%s' % varkwargs
		callString += u'**%s' % varkwargs
	logger.debug3(u"Arg string is: %s" % argString)
	logger.debug3(u"Call string is: %s" % callString)
	return (argString, callString)



'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                      CLASS DEFERREDCALL                                            =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class DeferredCall(object):
	def __init__(self, callback = None):
		self.error = None
		self.result = None
		self.finished = threading.Event()
		self.callback = callback
		self.callbackArgs = []
		self.callbackKwargs = {}
		
	def waitForResult(self):
		self.finished.wait()
		#return (self.result, self.error)
		if self.error:
			raise self.error
		return self.result
		
	def setCallback(self, callback, *args, **kwargs):
		self.callback = callback
		self.callbackArgs = args
		self.callbackKwargs = kwargs
	
	def _gotResult(self):
		self.finished.set()
		if self.callback:
			self.callback(self, *self.callbackArgs, **self.callbackKwargs)
		
'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                        CLASS BACKEND                                               =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class Backend:
	def __init__(self, **kwargs):
		# Parse arguments
		self._name = None
		self._username = None
		self._password = None
		self._context = self
		
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('name',):
				self._name = value
			elif option in ('username',):
				self._username = value
			elif option in ('password',):
				self._password = value
			elif option in ('context',):
				self._context = value
				logger.info(u"Backend context was set to %s" % self._context)
		self._options = {}
	
	def _setContext(self, context):
		self._context = context
	
	def _getContext(self):
		return self._context
	
	matchCache = {}
	def _objectHashMatches(self, objHash, **filter):
		matchedAll = True
		for (attribute, value) in objHash.items():
			if not filter.get(attribute):
				continue
			matched = False
			try:
				logger.debug(u"Testing match of filter '%s' of attribute '%s' with value '%s'" \
							% (filter[attribute], attribute, value))
				filterValues = forceUnicodeList(filter[attribute])
				if (forceUnicodeList(value) == filterValues) or forceUnicode(value) in filterValues:
					matched = True
				else:
					for filterValue in filterValues:
						if (attribute == 'type'):
							match = False
							Class = eval(filterValue)
							for subClass in Class.subClasses:
								if (subClass == value):
									matched = True
									break
							continue
						
						if type(value) in (float, long, int):# or type(filterValue) in (float, long, int):
							operator = '=='
							v = filterValue
							match = re.search('^\s*([>=<]+)\s*([\d\.]+)', filterValue) #forceUnicode(filterValue))
							if match:
								operator = match.group(1)
								v = match.group(2)
								if operator == '=':
									operator = '=='
							try:
								matched = eval('%s %s %s' % (value, operator, v))
								if matched:
									break
							except:
								pass
							continue
						
						if type(value) is list:
							if filterValue in value:
								matched = True
								break
							continue
						
						#if type(filterValue) in (types.NoneType, types.BooleanType):
						#	continue
						if type(value) in (types.NoneType, types.BooleanType):
							continue
						
						if (filterValue.find('*') != -1) and re.search('^%s$' % filterValue.replace('*', '.*'), value):
							matched = True
							break
					
					
				if matched:
					logger.debug(u"Value '%s' matched filter '%s', attribute '%s'" \
								% (value, filter[attribute], attribute))
				else:
					matchedAll = False
					break
			except Exception, e:
				raise Exception(u"Testing match of filter '%s' of attribute '%s' with value '%s' failed: %s" \
							% (filter[attribute], attribute, value, e))
		return matchedAll
	
	def backend_setOptions(self, options):
		options = forceDict(options)
		for (key, value) in options.items():
			if not key in self._options.keys():
				#raise ValueError(u"No such option '%s'" % key)
				continue
			if type(value) != type(self._options[key]):
				#raise ValueError(u"Wrong type '%s' for option '%s', expecting type '%s'" % (type(value), key, type(self._options[key])))
				continue
			self._options[key] = value
		
	def backend_getOptions(self):
		return self._options
	
	def backend_getInterface(self):
		methods = {}
		for member in inspect.getmembers(self, inspect.ismethod):
			methodName = member[0]
			if methodName.startswith('_'):
				# protected / private
				continue
			(args, varargs, keywords, defaults) = inspect.getargspec(member[1])
			#logger.debug2(u"args: %s" % unicode(args))
			#logger.debug2(u"varargs: %s" % unicode(varargs))
			#logger.debug2(u"keywords: %s" % unicode(keywords))
			#logger.debug2(u"defaults: %s" % unicode(defaults))
			params = []
			if args:
				for arg in forceList(args):
					if (arg != 'self'):
						params.append(arg)
			if ( defaults != None and len(defaults) > 0 ):
				offset = len(params) - len(defaults)
				for i in range(len(defaults)):
					params[offset+i] = '*' + params[offset+i]
			
			if varargs:
				for arg in forceList(varargs):
					params.append('*' + arg)
			
			if keywords:
				for arg in forceList(keywords):
					params.append('**' + arg)
			
			logger.debug2(u"%s interface method: name '%s', params %s" % (self.__class__.__name__, methodName, params))
			methods[methodName] = { 'name': methodName, 'params': params, 'args': args, 'varargs': varargs, 'keywords': keywords, 'defaults': defaults}
		
		methodList = []
		methodNames = methods.keys()
		methodNames.sort()
		for methodName in methodNames:
			methodList.append(methods[methodName])
		return methodList
	
	def backend_info(self):
		opsiVersion = 'unknown'
		try:
			f = codecs.open(OPSI_VERSION_FILE, 'r', 'utf-8')
			opsiVersion = f.readline().strip()
			f.close()
		except Exception, e:
			logger.error(u"Failed to read version info from file '%s': %s" % (OPSI_VERSION_FILE, e))
		
		modules = {}
		try:
			modules['valid'] = False
			f = codecs.open(OPSI_MODULES_FILE, 'r', 'utf-8')
			for line in f.readlines():
				line = line.strip()
				if (line.find('=') == -1):
					logger.error(u"Found bad line '%s' in modules file '%s'" % (line, OPSI_MODULES_FILE))
					continue
				(module, state) = line.split('=', 1)
				module = module.strip().lower()
				state = state.strip()
				if module in ('signature', 'customer', 'expires'):
					modules[module] = state
					continue
				state = state.lower()
				if not state in ('yes', 'no'):
					logger.error(u"Found bad line '%s' in modules file '%s'" % (line, OPSI_MODULES_FILE))
					continue
				modules[module] = (state == 'yes')
			f.close()
			if not modules.get('signature'):
				modules = {'valid': False}
				raise Exception(u"Signature not found")
			if not modules.get('customer'):
				modules = {'valid': False}
				raise Exception(u"Customer not found")
			if (modules.get('expires', '') != 'never') and (time.mktime(time.strptime(modules.get('expires', '2000-01-01'), "%Y-%m-%d")) - time.time() <= 0):
				modules = {'valid': False}
				raise Exception(u"Signature expired")
			publicKey = keys.Key.fromString(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP')).keyObject
			data = u''
			mks = modules.keys()
			mks.sort()
			for module in mks:
				if module in ('valid', 'signature'):
					continue
				val = modules[module]
				if (val == False): val = 'no'
				if (val == True):  val = 'yes'
				data += u'%s = %s\r\n' % (module.lower().strip(), val)
			modules['valid'] = bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ]))
		except Exception, e:
			logger.warning(u"Failed to read opsi modules file '%s': %s" % (OPSI_MODULES_FILE, e))
		
		return {
			"opsiVersion": opsiVersion,
			"modules":     modules
		}
	
	def backend_getSharedAlgorithm(self, function):
		if not hasattr(OPSI.SharedAlgorithm, 'def_%s' % function):
			raise ValueError(u"No such function: %s" % function)
		return getattr(OPSI.SharedAlgorithm, 'def_%s' % function)
	
	def backend_exit(self):
		pass

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                    CLASS EXTENDEDBACKEND                                           =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class ExtendedBackend(Backend):
	def __init__(self, backend, overwrite = True):
		Backend.__init__(self)
		self._backend = backend
		if (self._context is self):
			logger.info(u"Setting context to backend %s" % self._context)
			self._context = self._backend
		self._overwrite = forceBool(overwrite)
		self._createInstanceMethods()
		
	def _createInstanceMethods(self):
		logger.debug(u"%s is creating instance methods" % self.__class__.__name__)
		for member in inspect.getmembers(self._backend, inspect.ismethod):
			methodName = member[0]
			if methodName.startswith('_'):
				# Not a public method
				continue
			logger.debug2(u"Found public %s method '%s'" % (self._backend.__class__.__name__, methodName))
			#if hasattr(self.__class__, methodName):
			if hasattr(self, methodName):
				if self._overwrite:
					logger.debug(u"%s: overwriting method %s of backend instance %s" % (self.__class__.__name__, methodName, self._backend))
					continue
				else:
					logger.debug(u"%s: not overwriting method %s of backend instance %s" % (self.__class__.__name__, methodName, self._backend))
			(argString, callString) = getArgAndCallString(member[1])
			
			exec(u'def %s(self, %s): return self._executeMethod("%s", %s)' % (methodName, argString, methodName, callString))
			setattr(self, methodName, new.instancemethod(eval(methodName), self, self.__class__))
		
	def _executeMethod(self, methodName, **kwargs):
		logger.debug(u"ExtendedBackend %s: executing '%s' on backend '%s'" % (self, methodName, self._backend))
		return eval(u'self._backend.%s(**kwargs)' % methodName)
	
	def backend_setOptions(self, options):
		Backend.backend_setOptions(self, options)
		if self._backend:
			self._backend.backend_setOptions(options)
		
	def backend_getOptions(self):
		options = Backend.backend_getOptions(self)
		if self._backend:
			options.update(self._backend.backend_getOptions())
		return options
		
	def backend_exit(self):
		if self._backend:
			logger.debug(u"Calling backend_exit() on backend %s" % self._backend)
			self._backend.backend_exit()

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                   CLASS CONFIGDATABACKEND                                          =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class ConfigDataBackend(Backend):
	
	def __init__(self, **kwargs):
		Backend.__init__(self, **kwargs)
		self._auditHardwareConfigFile       = u'/etc/opsi/hwaudit/opsihwaudit.conf'
		self._auditHardwareConfigLocalesDir = u'/etc/opsi/hwaudit/locales'
		
	def _testFilterAndAttributes(self, Class, attributes, **filter):
		if not attributes:
			attributes = []
		attributes = forceUnicodeList(attributes)
		possibleAttributes = getPossibleClassAttributes(Class)
		for attribute in attributes:
			if not attribute in possibleAttributes:
				raise BackendBadValueError("Class '%s' has not attribute '%s'" % (Class, attribute))
		for attribute in filter.keys():
			if not attribute in possibleAttributes:
				raise BackendBadValueError("Class '%s' has not attribute '%s'" % (Class, attribute))
	
	def backend_createBase(self):
		pass
	
	def backend_deleteBase(self):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Logs                                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def log_write(self, logType, data, objectId=None, append=False):
		logType = forceUnicode(logType)
		data = forceUnicode(data)
		if not objectId:
			objectId = None
		else:
			objectId = forceObjectId(objectId)
		append = forceBool(append)
		
		if logType not in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError(u"Unknown log type '%s'" % logType)
		
		if not objectId and logType in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError(u"Log type '%s' requires objectId" % logType)
		
		if not os.path.exists( os.path.join(LOG_DIR, logType) ):
			os.mkdir(os.path.join(LOG_DIR, logType), 02770)
		
		logFile = os.path.join(LOG_DIR, logType, objectId + '.log')
		
		f = None
		if append:
			f = codecs.open(logFile, 'a+', 'utf-8', 'replace')
		else:
			f = codecs.open(logFile, 'w', 'utf-8', 'replace')
		f.write(data)
		f.close()
		os.chmod(logFile, 0640)
		
	def log_read(self, logType, objectId=None, maxSize=0):
		logType = forceUnicode(logType)
		if not objectId:
			objectId = None
		else:
			objectId = forceObjectId(objectId)
		maxSize = forceInt(maxSize)
		if logType not in ('bootimage', 'clientconnect', 'instlog', 'opsiconfd'):
			raise BackendBadValueError(u'Unknown log type %s' % logType)
		
		if not objectId and logType in ('bootimage', 'clientconnect', 'instlog'):
			raise BackendBadValueError(u"Log type '%s' requires objectId" % logType)
		
		if not objectId:
			logFile = os.path.join(LOG_DIR, logType, 'opsiconfd.log')
		else:
			logFile = os.path.join(LOG_DIR, logType, objectId + '.log')
		data = u''
		if not os.path.exists(logFile):
			return data
		logFile = codecs.open(logFile, 'r', 'utf-8', 'replace')
		data = logFile.read()
		logFile.close()
		if maxSize and (len(data) > maxSize):
			start = data.find('\n', len(data)-maxSize)
			if (start == -1):
				start = len(data)-maxSize
			return data[start+1:]
		return data
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Users                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def user_getCredentials(self, username = u'pcpatch', hostId = None):
		username = forceUnicodeLower(username)
		if hostId:
			hostId = forceHostId(hostId)
		depotId = forceHostId(socket.getfqdn())
		
		result = { 'password': u'', 'rsaPrivateKey': u'' }
		
		cf = ConfigFile(filename = OPSI_PASSWD_FILE)
		lineRegex = re.compile('^\s*([^:]+)\s*:\s*(\S+)\s*$')
		for line in cf.parse():
			match = lineRegex.search(line)
			if not match:
				continue
			if (match.group(1) == username):
				result['password'] = match.group(2)
				break
		if not result['password']:
			raise BackendMissingDataError(u"Username '%s' not found in '%s'" % (username, OPSI_PASSWD_FILE))
		
		depot = self.host_getObjects(id = depotId)
		if not depot:
			raise Exception(u"Depot '%s' not found in backend" % depotId)
		depot = depot[0]
		if not depot.opsiHostKey:
			raise Exception(u"Host key for depot '%s' not found" % depotId)
		
		result['password'] = blowfishDecrypt(depot.opsiHostKey, result['password'])
		
		if (username == 'pcpatch'):
			try:
				import pwd
				idRsa = os.path.join(pwd.getpwnam(username)[5], u'.ssh', u'id_rsa')
				f = open(idRsa, 'r')
				result['rsaPrivateKey'] = f.read()
				f.close()
			except Exception, e:
				logger.debug(e)
		if hostId:
			host  = self._context.host_getObjects(id = hostId)
			if not host:
				raise Exception(u"Host '%s' not found in backend" % hostId)
			host = host[0]
			result['password'] = blowfishEncrypt(host.opsiHostKey, result['password'])
			if result['rsaPrivateKey']:
				result['rsaPrivateKey'] = blowfishEncrypt(host.opsiHostKey, result['rsaPrivateKey'])
		return result
		
	def user_setCredentials(self, username, password):
		username = forceUnicodeLower(username)
		password = forceUnicode(password)
		depotId = forceHostId(socket.getfqdn())
		
		depot = self._context.host_getObjects(id = depotId)
		if not depot:
			raise Exception(u"Depot '%s' not found in backend" % depotId)
		depot = depot[0]
		
		encodedPassword = blowfishEncrypt(depot.opsiHostKey, password)
		
		cf = ConfigFile(filename = OPSI_PASSWD_FILE)
		lineRegex = re.compile('^\s*([^:]+)\s*:\s*(\S+)\s*$')
		lines = []
		for line in cf.readlines():
			match = lineRegex.search(line)
			if not match or (match.group(1) != username):
				lines.append(line.rstrip())
		lines.append(u'%s:%s' % (username, encodedPassword))
		cf.open('w')
		cf.writelines(lines)
		cf.close()
		
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_insertObject(self, host):
		host = forceObjectClass(host, Host)
		host.setDefaults()
	
	def host_updateObject(self, host):
		host = forceObjectClass(host, Host)
		
	def host_getObjects(self, attributes = [], **filter):
		self._testFilterAndAttributes(Host, attributes, **filter)
		return []
		
	def host_deleteObjects(self, hosts):
		for host in forceObjectClassList(hosts, Host):
			# Remove from groups
			self._context.objectToGroup_deleteObjects(
				self._context.objectToGroup_getObjects(
					groupType = 'HostGroup',
					objectId  = host.id ))
			if isinstance(host, OpsiClient):
				# Remove product states
				self._context.productOnClient_deleteObjects(
					self._context.productOnClient_getObjects(
						clientId = host.id ))
			elif isinstance(host, OpsiDepotserver):
				# This is also true for OpsiConfigservers
				# Remove products
				self._context.productOnDepot_deleteObjects(
					self._context.productOnDepot_getObjects(
						depotId = host.id ))
			# Remove product property states
			self._context.productPropertyState_deleteObjects(
				self._context.productPropertyState_getObjects(
					objectId = host.id ))
			# Remove config states
			self._context.configState_deleteObjects(
				self._context.configState_getObjects(
					objectId = host.id ))
			
			if isinstance(host, OpsiClient):
				# Remove audit softwares
				self._context.auditSoftwareOnClient_deleteObjects(
					self._context.auditSoftwareOnClient_getObjects(
						clientId = host.id ))
			
			# Remove audit hardwares
			self._context.auditHardwareOnHost_deleteObjects(
				self._context.auditHardwareOnHost_getObjects(
					hostId = host.id ))
			
			if isinstance(host, OpsiClient):
				# Free software licenses
				self._context.licenseOnClient_deleteObjects(
					self._context.licenseOnClient_getObjects(
						clientId = host.id ))
				
				for softwareLicense in self._context.softwareLicense_getObjects(boundToHost = host.id):
					softwareLicense.boundToHost = None
					self._context.softwareLicense_insertObject(softwareLicense)
			
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config):
		config = forceObjectClass(config, Config)
		config.setDefaults()
		
	def config_updateObject(self, config):
		config = forceObjectClass(config, Config)
	
	def config_getObjects(self, attributes = [], **filter):
		self._testFilterAndAttributes(Config, attributes, **filter)
		return []
		
	def config_deleteObjects(self, configs):
		ids = []
		for config in forceObjectClassList(configs, Config):
			ids.append(config.id)
		if ids:
			self._context.configState_deleteObjects(
				self._context.configState_getObjects(
					configId = ids,
					objectId = []))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)
		configState.setDefaults()
		
		configIds = []
		for config in self._context.config_getObjects(attributes = ['id']):
			configIds.append(config.id)
		if configState.configId not in configIds:
			raise BackendReferentialIntegrityError(u"Config with id '%s' not found" % configState.configId)
		
	def configState_updateObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)
	
	def configState_getObjects(self, attributes = [], **filter):
		self._testFilterAndAttributes(ConfigState, attributes, **filter)
		return []
		
	def configState_deleteObjects(self, configStates):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product):
		product = forceObjectClass(product, Product)
		product.setDefaults()
		
	def product_updateObject(self, product):
		product = forceObjectClass(product, Product)
	
	def product_getObjects(self, attributes = [], **filter):
		self._testFilterAndAttributes(Product, attributes, **filter)
		return []
		
	def product_deleteObjects(self, products):
		productByIdAndVersion = {}
		for product in forceObjectClassList(products, Product):
			if not productByIdAndVersion.has_key(product.id):
				productByIdAndVersion[product.id] = {}
			if not productByIdAndVersion[product.id].has_key(product.productVersion):
				productByIdAndVersion[product.id][product.productVersion] = []
			productByIdAndVersion[product.id][product.productVersion].append(product.packageVersion)
			
			self._context.productProperty_deleteObjects(
				self._context.productProperty_getObjects(
					productId      = product.id,
					productVersion = product.productVersion,
					packageVersion = product.packageVersion ))
			self._context.productDependency_deleteObjects(
				self._context.productDependency_getObjects(
					productId      = product.id,
					productVersion = product.productVersion,
					packageVersion = product.packageVersion ))
			self._context.productOnDepot_deleteObjects(
				self._context.productOnDepot_getObjects(
					productId      = product.id,
					productVersion = product.productVersion,
					packageVersion = product.packageVersion ))
			
		for (productId, versions) in productByIdAndVersion.items():
			allProductVersionsWillBeDeleted = True
			for product in self._context.product_getObjects(attributes = ['id', 'productVersion', 'packageVersion'], id = productId):
				if not product.packageVersion in versions.get(product.productVersion, []):
					allProductVersionsWillBeDeleted = False
					break
			if not allProductVersionsWillBeDeleted:
				continue
			self._context.productOnClient_deleteObjects(
				self._context.productOnClient_getObjects(productId = productId)
			)
			self._context.productPropertyState_deleteObjects(
				self._context.productPropertyState_getObjects(productId = productId)
			)
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)
		productProperty.setDefaults()
		
		if not self._context.product_getObjects(attributes = ['id', 'productVersion', 'packageVersion'],
				id             = productProperty.productId,
				productVersion = productProperty.productVersion,
				packageVersion = productProperty.packageVersion):
			raise BackendReferentialIntegrityError(u"Product with id '%s', productVersion '%s', packageVersion '%s' not found" \
				% (productProperty.productId, productProperty.productVersion, productProperty.packageVersion))
		
	def productProperty_updateObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)
	
	def productProperty_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductProperty, attributes, **filter)
		return []
		
	def productProperty_deleteObjects(self, productProperties):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                       -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)
		productDependency.setDefaults()
		if not productDependency.getRequiredAction() and not productDependency.getRequiredInstallationStatus():
			raise BackendBadValueError(u"Either a required action or a required installation status must be given")
		if not self._context.product_getObjects(attributes = ['id', 'productVersion', 'packageVersion'],
				id                = productDependency.productId,
				productVersion    = productDependency.productVersion,
				packageVersion    = productDependency.packageVersion):
			raise BackendReferentialIntegrityError(u"Product with id '%s', productVersion '%s', packageVersion '%s' not found" \
				% (productDependency.productId, productDependency.productVersion, productDependency.packageVersion))
		
	def productDependency_updateObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)
	
	def productDependency_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductDependency, attributes, **filter)
		return []
		
	def productDependency_deleteObjects(self, productDependencies):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		productOnDepot.setDefaults()
		if not self._context.product_getObjects(attributes = ['id', 'productVersion', 'packageVersion'],
			id = productOnDepot.productId,
			productVersion = productOnDepot.productVersion,
			packageVersion = productOnDepot.packageVersion):
			
			raise BackendReferentialIntegrityError(u"Product with id '%s', productVersion '%s', packageVersion '%s' not found" \
				% (productOnDepot.productId, productOnDepot.productVersion, productOnDepot.packageVersion))
		
	def productOnDepot_updateObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		if not self._context.product_getObjects(attributes = ['id', 'productVersion', 'packageVersion'],
			id = productOnDepot.productId,
			productVersion = productOnDepot.productVersion,
			packageVersion = productOnDepot.packageVersion):
			
			raise BackendReferentialIntegrityError(u"Product with id '%s', productVersion '%s', packageVersion '%s' not found" \
				% (productOnDepot.productId, productOnDepot.productVersion, productOnDepot.packageVersion))
	
	def productOnDepot_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductOnDepot, attributes, **filter)
		return []
		
	def productOnDepot_deleteObjects(self, productOnDepots):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		productOnClient.setDefaults()
		
		if (productOnClient.installationStatus == 'installed') and (not (productOnClient.productVersion) or not (productOnClient.packageVersion)):
			raise BackendReferentialIntegrityError(u"Cannot set installationStatus for product '%s', client '%s' to 'installed' without productVersion and packageVersion" \
				% (productOnClient.productId, productOnClient.clientId))
		
		if (productOnClient.installationStatus != 'installed'):
			productOnClient.productVersion = None
			productOnClient.packageVersion = None
		
	def productOnClient_updateObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		
	def productOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductOnClient, attributes, **filter)
		return []
		
	def productOnClient_deleteObjects(self, productOnClients):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(self, productPropertyState):
		productPropertyState = forceObjectClass(productPropertyState, ProductPropertyState)
		productPropertyState.setDefaults()
		if not self._context.productProperty_getObjects(attributes = ['productId', 'propertyId'],
					productId  = productPropertyState.productId,
					propertyId = productPropertyState.propertyId):
			raise BackendReferentialIntegrityError(u"ProductProperty with id '%s' for product '%s' not found"
				% (productPropertyState.propertyId, productPropertyState.productId))
	
	def productPropertyState_updateObject(self, productPropertyState):
		productPropertyState = forceObjectClass(productPropertyState, ProductPropertyState)
	
	def productPropertyState_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ProductPropertyState, attributes, **filter)
		return []
		
	def productPropertyState_deleteObjects(self, productPropertyStates):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group):
		group = forceObjectClass(group, Group)
		group.setDefaults()
		if group.parentGroupId and not self._context.group_getObjects(attributes = ['id'], id = group.parentGroupId):
			raise BackendReferentialIntegrityError(u"Parent group '%s' of group '%s' not found" % (group.parentGroupId, group.id))
		
	def group_updateObject(self, group):
		group = forceObjectClass(group, Group)
	
	def group_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(Group, attributes, **filter)
		return []
		
	def group_deleteObjects(self, groups):
		for group in forceObjectClassList(groups, Group):
			self._context.objectToGroup_deleteObjects(
				self._context.objectToGroup_getObjects(
					groupType = group.getType(),
					groupId   = group.id ))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		objectToGroup.setDefaults()
	
	def objectToGroup_updateObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
	
	def objectToGroup_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(ObjectToGroup, attributes, **filter)
		return []
		
	def objectToGroup_deleteObjects(self, objectToGroups):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_insertObject(self, licenseContract):
		licenseContract = forceObjectClass(licenseContract, LicenseContract)
		licenseContract.setDefaults()
	
	def licenseContract_updateObject(self, licenseContract):
		licenseContract = forceObjectClass(licenseContract, LicenseContract)
	
	def licenseContract_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicenseContract, attributes, **filter)
		return []
		
	def licenseContract_deleteObjects(self, licenseContracts):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_insertObject(self, softwareLicense):
		softwareLicense = forceObjectClass(softwareLicense, SoftwareLicense)
		softwareLicense.setDefaults()
		if not softwareLicense.licenseContractId:
			raise BackendBadValueError(u"License contract missing")
		if not self._context.licenseContract_getObjects(attributes = ['id'], id = softwareLicense.licenseContractId):
			raise BackendReferentialIntegrityError(u"License contract with id '%s' not found" % softwareLicense.licenseContractId)
		
	def softwareLicense_updateObject(self, softwareLicense):
		softwareLicense = forceObjectClass(softwareLicense, SoftwareLicense)
	
	def softwareLicense_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(SoftwareLicense, attributes, **filter)
		return []
		
	def softwareLicense_deleteObjects(self, softwareLicenses):
		softwareLicenseIds = []
		for softwareLicense in forceObjectClassList(softwareLicenses, SoftwareLicense):
			softwareLicenseIds.append(softwareLicense.id)
		self._context.softwareLicenseToLicensePool_deleteObjects(
			self._context.softwareLicenseToLicensePool_getObjects(
				softwareLicenseId = softwareLicenseIds ))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePools                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_insertObject(self, licensePool):
		licensePool = forceObjectClass(licensePool, LicensePool)
		licensePool.setDefaults()
	
	def licensePool_updateObject(self, licensePool):
		licensePool = forceObjectClass(licensePool, LicensePool)
	
	def licensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicensePool, attributes, **filter)
		return []
		
	def licensePool_deleteObjects(self, licensePools):
		licensePoolIds = []
		for licensePool in forceObjectClassList(licensePools, LicensePool):
			licensePoolIds.append(licensePool.id)
		if licensePoolIds:
			softwareLicenseToLicensePools = self._context.softwareLicenseToLicensePool_getObjects(licensePoolId = licensePoolIds)
			if softwareLicenseToLicensePools:
				raise BackendReferentialIntegrityError(u"Refusing to delete license pool(s) %s, one ore more licenses/keys refer to pool: %s" % \
					(licensePoolIds, softwareLicenseToLicensePools))
			self._context.auditSoftwareToLicensePool_deleteObjects(
				self._context.auditSoftwareToLicensePool_getObjects(
								name          = [],
								version       = [],
								subVersion    = [],
								language      = [],
								architecture  = [],
								licensePoolId = licensePoolIds))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_insertObject(self, softwareLicenseToLicensePool):
		softwareLicenseToLicensePool = forceObjectClass(softwareLicenseToLicensePool, SoftwareLicenseToLicensePool)
		softwareLicenseToLicensePool.setDefaults()
		if not self._context.softwareLicense_getObjects(attributes = ['id'], id = softwareLicenseToLicensePool.softwareLicenseId):
			raise BackendReferentialIntegrityError(u"Software license with id '%s' not found" % softwareLicenseToLicensePool.softwareLicenseId)
		if not self._context.licensePool_getObjects(attributes = ['id'], id = softwareLicenseToLicensePool.licensePoolId):
			raise BackendReferentialIntegrityError(u"License with id '%s' not found" % softwareLicenseToLicensePool.licensePoolId)
		
	def softwareLicenseToLicensePool_updateObject(self, softwareLicenseToLicensePool):
		softwareLicenseToLicensePool = forceObjectClass(softwareLicenseToLicensePool, SoftwareLicenseToLicensePool)
	
	def softwareLicenseToLicensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(SoftwareLicenseToLicensePool, attributes, **filter)
		return []
		
	def softwareLicenseToLicensePool_deleteObjects(self, softwareLicenseToLicensePools):
		softwareLicenseIds = []
		for softwareLicenseToLicensePool in forceObjectClassList(softwareLicenseToLicensePools, SoftwareLicenseToLicensePool):
			softwareLicenseIds.append(softwareLicenseToLicensePool.softwareLicenseId)
		if softwareLicenseIds:
			if self._context.licenseOnClient_getObjects(softwareLicenseId = softwareLicenseIds):
				raise BackendReferentialIntegrityError(u"Refusing to delete softwareLicenseToLicensePool(s), one ore more licenses in use: %s"\
					% licenseOnClientIdents)
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_insertObject(self, licenseOnClient):
		licenseOnClient = forceObjectClass(licenseOnClient, LicenseOnClient)
		licenseOnClient.setDefaults()
	
	def licenseOnClient_updateObject(self, licenseOnClient):
		licenseOnClient = forceObjectClass(licenseOnClient, LicenseOnClient)
	
	def licenseOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(LicenseOnClient, attributes, **filter)
		return []
		
	def licenseOnClient_deleteObjects(self, licenseOnClients):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_insertObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		auditSoftware.setDefaults()
	
	def auditSoftware_updateObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
	
	def auditSoftware_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftware, attributes, **filter)
		return []
		
	def auditSoftware_deleteObjects(self, auditSoftwares):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_insertObject(self, auditSoftwareToLicensePool):
		auditSoftwareToLicensePool = forceObjectClass(auditSoftwareToLicensePool, AuditSoftwareToLicensePool)
		auditSoftwareToLicensePool.setDefaults()
	
	def auditSoftwareToLicensePool_updateObject(self, auditSoftwareToLicensePool):
		auditSoftwareToLicensePool = forceObjectClass(auditSoftwareToLicensePool, AuditSoftwareToLicensePool)
	
	def auditSoftwareToLicensePool_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftwareToLicensePool, attributes, **filter)
		return []
	
	def auditSoftwareToLicensePool_deleteObjects(self, auditSoftwareToLicensePools):
		pass

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(auditSoftwareOnClient, AuditSoftwareOnClient)
		auditSoftwareOnClient.setDefaults()
	
	def auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(auditSoftwareOnClient, AuditSoftwareOnClient)
	
	def auditSoftwareOnClient_getObjects(self, attributes=[], **filter):
		self._testFilterAndAttributes(AuditSoftwareOnClient, attributes, **filter)
		return []
		
	def auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardware_insertObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		auditHardware.setDefaults()
	
	def auditHardware_updateObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
	
	def auditHardware_getObjects(self, attributes=[], **filter):
		return []
	
	def auditHardware_deleteObjects(self, auditHardwares):
		pass
	
	def auditHardware_getConfig(self, language=None):
		if not language:
			language = 'en_US'
		language = forceLanguageCode(language).replace('-', '_')
		
		localeFile = os.path.join(self._auditHardwareConfigLocalesDir, language)
		if not os.path.exists(localeFile):
			logger.error(u"No translation file found for language %s, falling back to en_US" % language)
			language = 'en_US'
			localeFile = os.path.join(self._auditHardwareConfigLocalesDir, language)
		
		locale = {}
		try:
			lf = ConfigFile(localeFile)
			for line in lf.parse():
				if (line.count('=') == 0):
					continue
				(k, v) = line.split('=', 1)
				locale[k.strip()] = v.strip()
		except Exception, e:
			logger.error(u"Failed to read translation file for language %s: %s" % (language, e))
		
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
					logger.error(u"Super class '%s' of class '%s' not found!" % (scname, c['Class'].get('Opsi')))
		
		classes = []
		try:
			execfile(self._auditHardwareConfigFile)
			for i in range(len(OPSI_HARDWARE_CLASSES)):
				opsiClass = OPSI_HARDWARE_CLASSES[i]['Class']['Opsi']
				if (OPSI_HARDWARE_CLASSES[i]['Class']['Type'] == 'STRUCTURAL'):
					if locale.get(opsiClass):
						OPSI_HARDWARE_CLASSES[i]['Class']['UI'] = locale[opsiClass]
					else:
						logger.error(u"No translation for class '%s' found" % opsiClass)
						OPSI_HARDWARE_CLASSES[i]['Class']['UI'] = opsiClass
				for j in range(len(OPSI_HARDWARE_CLASSES[i]['Values'])):
					opsiProperty = OPSI_HARDWARE_CLASSES[i]['Values'][j]['Opsi']
					if locale.get(opsiClass + '.' + opsiProperty):
						OPSI_HARDWARE_CLASSES[i]['Values'][j]['UI'] = locale[opsiClass + '.' + opsiProperty]
					
			for c in OPSI_HARDWARE_CLASSES:
				try:
					if (c['Class'].get('Type') == 'STRUCTURAL'):
						logger.debug(u"Found STRUCTURAL hardware class '%s'" % c['Class'].get('Opsi'))
						ccopy = pycopy.deepcopy(c)
						if ccopy['Class'].has_key('Super'):
							__inheritFromSuperClasses(OPSI_HARDWARE_CLASSES, ccopy)
							del ccopy['Class']['Super']
						del ccopy['Class']['Type']
						
						# Fill up empty display names
						for j in range(len(ccopy.get('Values', []))):
							if not ccopy['Values'][j].get('UI'):
								logger.warning("No translation for property '%s.%s' found" % (ccopy['Class']['Opsi'], ccopy['Values'][j]['Opsi']))
								ccopy['Values'][j]['UI'] = ccopy['Values'][j]['Opsi']
						
						classes.append(ccopy)
				except Exception, e:
					logger.error(u"Error in config file '%s': %s" % (self._auditHardwareConfigFile, e))
		except Exception, e:
			raise Exception(u"Failed to read audit hardware configuration from file '%s': %s" % (self._auditHardwareConfigFile, e))
		
		return classes
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardwareOnHost_insertObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		auditHardwareOnHost.setDefaults()
		self._context.auditHardware_insertObject( AuditHardware.fromHash(auditHardwareOnHost.toHash()) )
		
	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
	
	def auditHardwareOnHost_getObjects(self, attributes=[], **filter):
		return []
	
	def auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts):
		pass
	
'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                               CLASS EXTENDEDCONFIGDATABACKEND                                      =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''
class ExtendedConfigDataBackend(ExtendedBackend):
	
	def __init__(self, configDataBackend):
		#if not isinstance(configDataBackend, ConfigDataBackend):
		#	raise Exception(u"ExtendedConfigDataBackend needs instance of ConfigDataBackend as backend, got %s" % configDataBackend.__class__.__name__)
		ExtendedBackend.__init__(self, configDataBackend, overwrite = True)
		self._options = {
			#'processProductPriorities':            False,
			#'processProductDependencies':          False,
			'addProductOnClientDefaults':          False,
			'addProductPropertyStateDefaults':     False,
			'addConfigStateDefaults':              False,
			'deleteConfigStateIfDefault':          False,
			#'deleteProductPropertyStateIfDefault': False,
			'returnObjectsOnUpdateAndCreate':      False,
			'addDependentProductOnClients':        False,
			'processProductOnClientSequence':      False
		}
		self._auditHardwareConfig = {}
		
		if hasattr(self._backend, 'auditHardware_getConfig'):
			ahwconf = self._backend.auditHardware_getConfig()
			AuditHardware.setHardwareConfig(ahwconf)
			AuditHardwareOnHost.setHardwareConfig(ahwconf)
			for config in ahwconf:
				hwClass = config['Class']['Opsi']
				self._auditHardwareConfig[hwClass] = {}
				for value in config['Values']:
					self._auditHardwareConfig[hwClass][value['Opsi']] = {
						'Type':  value["Type"],
						'Scope': value["Scope"]
					}
	
	def backend_searchIdents(self, filter):
		logger.info(u"=== Starting search, filter: %s" % filter)
		try:
			parsedFilter = ldapfilter.parseFilter(filter)
		except Exception, e:
			raise BackendBadValueError(u"Failed to parse filter '%s'" % filter)
		logger.debug(u"Parsed search filter: %s" % repr(parsedFilter))
		
		
		def combineResults(result1, result2, operator):
			if not result1:
				return result2
			if not result2:
				return result1
			
			result1IdentIndex = -1
			result2IdentIndex = -1
			
			for i in range(len(result1['identAttributes'])):
				for j in range(len(result2['identAttributes'])):
					if (result1['identAttributes'][i] == result2['identAttributes'][j]):
						if (result1['identAttributes'][i] != 'id') or (result1['objectClass'] == result2['objectClass']):
							result1IdentIndex = i
							result2IdentIndex = j
							break
			if (result1IdentIndex == -1):
				logger.debug(u"No matching identAttributes found (%s, %s)" % (result1['identAttributes'], result2['identAttributes']))
			
			if (result1IdentIndex == -1):
				#if (len(result1['identAttributes']) == 1) and result1['foreignIdAttributes']:
				if 'id' in result1['identAttributes'] and result1['foreignIdAttributes']:
					logger.debug(u"Trying foreignIdAttributes of result1: %s" % result1['foreignIdAttributes'])
					for attr in result1['foreignIdAttributes']:
						for i in range(len(result2['identAttributes'])):
							logger.debug2("%s == %s" % (attr, result2['identAttributes'][i]))
							if (attr == result2['identAttributes'][i]):
								result2IdentIndex = i
								for a in range(len(result1['identAttributes'])):
									if (result1['identAttributes'][a] == 'id'):
										result1IdentIndex = a
								break
				else:
					logger.debug(u"Cannot use foreignIdAttributes of result1")
				
			if (result1IdentIndex == -1):
				#if (len(result2['identAttributes']) == 1) and result2['foreignIdAttributes']:
				if 'id' in result2['identAttributes'] and result2['foreignIdAttributes']:
					logger.debug(u"Trying foreignIdAttributes of result2: %s" % result2['foreignIdAttributes'])
					for attr in result2['foreignIdAttributes']:
						for i in range(len(result1['identAttributes'])):
							logger.debug2("%s == %s" % (attr, result1['identAttributes'][i]))
							if (attr == result1['identAttributes'][i]):
								result1IdentIndex = i
								for a in range(len(result2['identAttributes'])):
									if (result2['identAttributes'][a] == 'id'):
										result2IdentIndex = a
								break
				else:
					logger.debug(u"Cannot use foreignIdAttributes of result2")
			
			if (result1IdentIndex == -1):
				raise BackendBadValueError(u"Failed to combine partial results %s(%s | %s) %s(%s | %s)" \
					% (result1['objectClass'], result1['identAttributes'], result1['foreignIdAttributes'],
					   result2['objectClass'], result2['identAttributes'], result2['foreignIdAttributes']))
			
			logger.info(u"Using attributes %s.%s and %s.%s to combine results (%s)" \
				% (result1['objectClass'], result1['identAttributes'][result1IdentIndex],
				   result2['objectClass'], result2['identAttributes'][result2IdentIndex],
				   operator))
			
			values1 = []
			for v in result1['identValues']:
				values1.append(v[result1IdentIndex])
			values2 = []
			for v in result2['identValues']:
				values2.append(v[result2IdentIndex])
			
			foreignIdAttributes = result1["foreignIdAttributes"]
			for attr in result2["foreignIdAttributes"]:
				if attr in result1["foreignIdAttributes"]:
					continue
				foreignIdAttributes.append(attr)
			
			result = {
				"objectClass":         result2["objectClass"],
				"foreignIdAttributes": foreignIdAttributes,
				"identAttributes":     [ result2['identAttributes'][result2IdentIndex] ],
				"identValues":         []
			}
			
			if (operator == 'OR'):
				vals = []
				values1.extend(values2)
				for v in values1:
					if v in vals:
						continue
					vals.append(v)
					result['identValues'].append([v])
			elif (operator == 'AND'):
				vals = []
				for v in values2:
					if not v in values1 or v in vals:
						continue
					vals.append(v)
					result['identValues'].append([v])
			
			return result
			
		def handleFilter(f, level=0):
			objectClass = None
			objectFilter = {}
			result = None
			
			logger.debug(u"Level %s, processing: %s" % (level, repr(f)))
			
			if isinstance(f, pureldap.LDAPFilter_equalityMatch):
				logger.debug(u"Handle equality attribute '%s', value '%s'" % (f.attributeDesc.value, f.assertionValue.value))
				if (f.attributeDesc.value.lower() == 'objectclass'):
					objectClass = f.assertionValue.value
				else:
					objectFilter = { f.attributeDesc.value: f.assertionValue.value }
			
			elif isinstance(f, pureldap.LDAPFilter_greaterOrEqual):
				logger.debug(u"Handle greaterOrEqual attribute '%s', value '%s'" % (f.attributeDesc.value, f.assertionValue.value))
				objectFilter = { f.attributeDesc.value: u'>=%s' % f.assertionValue.value }
				
			elif isinstance(f, pureldap.LDAPFilter_lessOrEqual):
				logger.debug(u"Handle lessOrEqual attribute '%s', value '%s'" % (f.attributeDesc.value, f.assertionValue.value))
				objectFilter = { f.attributeDesc.value: u'<=%s' % f.assertionValue.value }
				
			elif isinstance(f, pureldap.LDAPFilter_substrings):
				logger.debug(u"Handle substrings type %s: %s" % (f.type, repr(f.substrings)))
				if (f.type.lower() == 'objectclass'):
					raise BackendBadValueError(u"Substring search not allowed for objectClass")
				if   isinstance(f.substrings[0], pureldap.LDAPFilter_substrings_initial):
					# string*
					objectFilter = { f.type: '%s*' % f.substrings[0].value }
				elif isinstance(f.substrings[0], pureldap.LDAPFilter_substrings_final):
					# *string
					objectFilter = { f.type: '*%s' % f.substrings[0].value }
				elif isinstance(f.substrings[0], pureldap.LDAPFilter_substrings_any):
					# *string*
					objectFilter = { f.type: '*%s*' % f.substrings[0].value }
				else:
					raise BackendBadValueError(u"Unsupported substring class: %s" % repr(f))
			elif isinstance(f, pureldap.LDAPFilter_present):
				objectFilter = { f.value: '*' }
				
			elif isinstance(f, pureldap.LDAPFilter_and) or isinstance(f, pureldap.LDAPFilter_or):
				operator = None
				if isinstance(f, pureldap.LDAPFilter_and):
					operator = 'AND'
				elif isinstance(f, pureldap.LDAPFilter_or):
					operator = 'OR'
				
				for fChild in f.data:
					(res, oc, of) = handleFilter(fChild, level+1)
					logger.debug(u"Got return values: %s, %s, %s" % (res, oc, of))
					if oc:
						objectClass = oc
					if of:
						objectFilter.update(of)
					if res:
						#if (objectClass or objectFilter):
						#	raise BackendBadValueError(u"Unsupported search filter: %s" % repr(f))
						result = combineResults(result, res, operator)
				
				if objectFilter or objectClass:
					if objectFilter and not objectClass:
						raise BackendBadValueError(u"Bad search filter '%s': objectClass not defined" % repr(f))
					
					try:
						oc = eval(objectClass)
						if not ('type' in objectFilter):
							types = [ objectClass ]
							for c in oc.subClasses:
								types.append(c)
							if (len(types) > 1):
								objectFilter['type'] = types
							
						this = self
						objectFilterNew = {}
						for (key, value) in objectFilter.items():
							if (key != 'type'):
								try:
									value = eval(value)
								except:
									pass
							objectFilterNew[str(key)] = value
						objectFilter = objectFilterNew
						
						logger.debug(u"Executing: this.%s_getIdents(returnType = 'list', %s)" % (getBackendMethodPrefix(oc), objectFilter))
						addProductOnClientDefaults = self._options.get('addProductOnClientDefaults', False)
						addConfigStateDefaults = self._options.get('addConfigStateDefaults', False)
						addProductPropertyStateDefaults = self._options.get('addProductPropertyStateDefaults', False)
						if (objectClass == 'ProductOnClient'):
							self._options['addProductOnClientDefaults'] = True
						elif (objectClass == 'ConfigState'):
							self._options['addConfigStateDefaults'] = True
						elif (objectClass == 'ProductPropertyState'):
							self._options['addProductPropertyStateDefaults'] = True
						try:
							res = {
								"objectClass":         objectClass,
								"foreignIdAttributes": getForeignIdAttributes(oc),
								"identAttributes":     getIdentAttributes(oc),
								"identValues":         eval("this.%s_getIdents(returnType = 'list', **objectFilter)" % getBackendMethodPrefix(oc))
							}
						finally:
							self._options['addProductOnClientDefaults'] = addProductOnClientDefaults
							self._options['addConfigStateDefaults'] = addConfigStateDefaults
							self._options['addProductPropertyStateDefaults'] = addProductPropertyStateDefaults
						if (level == 0):
							result = combineResults(result, res, operator)
						else:
							result = res
						logger.debug("Result: %s" % result)
					except Exception, e:
						logger.logException(e)
						raise BackendBadValueError(u"Failed to process search filter '%s': %s" % (repr(f), e))
					
					objectClass = None
					objectFilter = {}
					
			elif isinstance(f, pureldap.LDAPFilter_not):
				raise BackendBadValueError(u"Operator '!' not allowed")
			else:
				raise BackendBadValueError(u"Unsupported search filter: %s" % repr(f))
			
			return (result, objectClass, objectFilter)
		
		result = []
		for v in handleFilter(parsedFilter)[0].get('identValues', []):
			result.append(v[0])
		result.sort()
		logger.info(u"=== Search done, result: %s" % result)
		return result
	
	def host_getIdents(self, returnType='unicode', **filter):
		result = []
		for host in self.host_getObjects(attributes = ['id'], **filter):
			result.append(host.getIdent(returnType))
		return result
	
	def config_getIdents(self, returnType='unicode', **filter):
		result = []
		for config in self.config_getObjects(attributes = ['id'], **filter):
			result.append(config.getIdent(returnType))
		return result
	
	def configState_getIdents(self, returnType='unicode', **filter):
		result = []
		for configState in self.configState_getObjects(attributes = ['configId', 'objectId'], **filter):
			result.append(configState.getIdent(returnType))
		return result
	
	def product_getIdents(self, returnType='unicode', **filter):
		result = []
		for product in self.product_getObjects(attributes = ['id'], **filter):
			result.append(product.getIdent(returnType))
		return result
	
	def productProperty_getIdents(self, returnType='unicode', **filter):
		result = []
		for productProperty in self.productProperty_getObjects(attributes = ['productId', 'productVersion', 'packageVersion', 'propertyId'], **filter):
			result.append(productProperty.getIdent(returnType))
		return result
	
	def productDependency_getIdents(self, returnType='unicode', **filter):
		result = []
		for productDependency in self.productDependency_getObjects(attributes = ['productId', 'productVersion', 'packageVersion', 'productAction', 'requiredProductId'], **filter):
			result.append(productDependency.getIdent(returnType))
		return result
	
	def productOnDepot_getIdents(self, returnType='unicode', **filter):
		result = []
		for productOnDepot in self.productOnDepot_getObjects(attributes = ['productId', 'productType', 'depotId'], **filter):
			result.append(productOnDepot.getIdent(returnType))
		return result
	
	def productOnClient_getIdents(self, returnType='unicode', **filter):
		result = []
		for productOnClient in self.productOnClient_getObjects(attributes = ['productId', 'productType', 'clientId'], **filter):
			result.append(productOnClient.getIdent(returnType))
		return result
	
	def productPropertyState_getIdents(self, returnType='unicode', **filter):
		result = []
		for productPropertyState in self.productPropertyState_getObjects(attributes = ['productId', 'propertyId', 'objectId'], **filter):
			result.append(productPropertyState.getIdent(returnType))
		return result
	
	def group_getIdents(self, returnType='unicode', **filter):
		result = []
		for group in self.group_getObjects(attributes = ['id'], **filter):
			result.append(group.getIdent(returnType))
		return result
	
	def objectToGroup_getIdents(self, returnType='unicode', **filter):
		result = []
		for objectToGroup in self.objectToGroup_getObjects(attributes = ['groupType', 'groupId', 'objectId'], **filter):
			result.append(objectToGroup.getIdent(returnType))
		return result
	
	def licenseContract_getIdents(self, returnType='unicode', **filter):
		result = []
		for licenseContract in self.licenseContract_getObjects(attributes = ['id'], **filter):
			result.append(licenseContract.getIdent(returnType))
		return result
	
	def softwareLicense_getIdents(self, returnType='unicode', **filter):
		result = []
		for softwareLicense in self.softwareLicense_getObjects(attributes = ['id', 'licenseContractId'], **filter):
			result.append(softwareLicense.getIdent(returnType))
		return result
	
	def licensePool_getIdents(self, returnType='unicode', **filter):
		result = []
		for licensePool in self.licensePool_getObjects(attributes = ['id'], **filter):
			result.append(licensePool.getIdent(returnType))
		return result
	
	def softwareLicenseToLicensePool_getIdents(self, returnType='unicode', **filter):
		result = []
		for softwareLicenseToLicensePool in self.softwareLicenseToLicensePool_getObjects(attributes = ['softwareLicenseId', 'licensePoolId'], **filter):
			result.append(softwareLicenseToLicensePool.getIdent(returnType))
		return result
	
	def licenseOnClient_getIdents(self, returnType='unicode', **filter):
		result = []
		for licenseOnClient in self.licenseOnClient_getObjects(attributes = ['softwareLicenseId', 'licensePoolId', 'clientId'], **filter):
			result.append(licenseOnClient.getIdent(returnType))
		return result
	
	def auditSoftware_getIdents(self, returnType='unicode', **filter):
		result = []
		for auditSoftware in self.auditSoftware_getObjects(attributes = ['name', 'version', 'subVersion', 'language', 'architecture'], **filter):
			result.append(auditSoftware.getIdent(returnType))
		return result
	
	def auditSoftwareToLicensePool_getIdents(self, returnType='unicode', **filter):
		result = []
		for auditSoftwareToLicensePool in self.auditSoftwareToLicensePool_getObjects(attributes = ['name', 'version', 'subVersion', 'language', 'architecture', 'licensePoolId'], **filter):
			result.append(auditSoftwareToLicensePool.getIdent(returnType))
		return result
	
	def auditSoftwareOnClient_getIdents(self, returnType='unicode', **filter):
		result = []
		for auditSoftwareOnClient in self.auditSoftwareOnClient_getObjects(attributes = ['name', 'version', 'subVersion', 'language', 'architecture', 'clientId'], **filter):
			result.append(auditSoftwareOnClient.getIdent(returnType))
		return result
	
	def auditHardware_getIdents(self, returnType='unicode', **filter):
		result = []
		for auditHardware in self.auditHardware_getObjects(**filter):
			result.append(auditHardware.getIdent(returnType))
		return result
	
	def auditHardwareOnHost_getIdents(self, returnType='unicode', **filter):
		result = []
		for auditHardwareOnHost in self.auditHardwareOnHost_getObjects(**filter):
			result.append(auditHardwareOnHost.getIdent(returnType))
		return result
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_createObjects(self, hosts):
		result = []
		for host in forceObjectClassList(hosts, Host):
			logger.info(u"Creating host '%s'" % host)
			self._backend.host_insertObject(host)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.host_getObjects(id = host.id)
				)
		return result
	
	def host_updateObjects(self, hosts):
		result = []
		for host in forceObjectClassList(hosts, Host):
			logger.info(u"Updating host '%s'" % host)
			if self.host_getIdents(id = host.id):
				self._backend.host_updateObject(host)
			else:
				logger.info(u"Host %s does not exist, creating" % host)
				self._backend.host_insertObject(host)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.host_getObjects(id = host.id)
				)
		return result
	
	def host_renameOpsiClient(self, id, newId):
		id    = forceHostId(id)
		newId = forceHostId(newId)
		clients = self._backend.host_getObjects(type = 'OpsiClient', id = id)
		if not clients:
			raise BackendMissingDataError(u"Cannot rename: client '%s' not found" % id)
		if self._backend.host_getObjects(id = newId):
			raise BackendError(u"Cannot rename: host '%s' already exists" % newId)
		
		client = clients[0]
		
		objectToGroups = []
		for objectToGroup in self._backend.objectToGroup_getObjects(groupType = 'HostGroup', objectId  = client.id):
			objectToGroup.setObjectId(newId)
			objectToGroups.append(objectToGroup)
		
		productOnClients = []
		for productOnClient in self._backend.productOnClient_getObjects(clientId = client.id):
			productOnClient.setClientId(newId)
			productOnClients.append(productOnClient)
		
		productPropertyStates = []
		for productPropertyState in self._backend.productPropertyState_getObjects(objectId = client.id):
			productPropertyState.setObjectId(newId)
			productPropertyStates.append(productPropertyState)
		
		configStates = []
		for configState in self._backend.configState_getObjects(objectId = client.id):
			configState.setObjectId(newId)
			configStates.append(configState)
		
		auditSoftwareOnClients = []
		for auditSoftwareOnClient in self._backend.auditSoftwareOnClient_getObjects(clientId = client.id):
			auditSoftwareOnClient.setClientId(newId)
			auditSoftwareOnClients.append(auditSoftwareOnClient)
		
		auditHardwareOnHosts = []
		for auditHardwareOnHost in self._backend.auditHardwareOnHost_getObjects(hostId = client.id):
			auditHardwareOnHost.setHostId(newId)
			auditHardwareOnHosts.append(auditHardwareOnHost)
		
		licenseOnClients = []
		for licenseOnClient in self._backend.licenseOnClient_getObjects(clientId = client.id):
			licenseOnClient.setClientId(newId)
			licenseOnClients.append(licenseOnClient)
		
		softwareLicenses = []
		for softwareLicense in self._backend.softwareLicense_getObjects(boundToHost = client.id):
			softwareLicense.setBoundToHost(newId)
			softwareLicenses.append(softwareLicense)
		
		logger.info(u"Deleting client '%s'" % client)
		self._backend.host_deleteObjects([ client ])
		
		client.setId(newId)
		self.host_createObjects([ client ])
		
		if objectToGroups:
			self.objectToGroup_createObjects(objectToGroups)
		if productOnClients:
			self.productOnClient_createObjects(productOnClients)
		if productPropertyStates:
			self.productPropertyState_createObjects(productPropertyStates)
		if configStates:
			self.configState_createObjects(configStates)
		if auditSoftwareOnClients:
			self.auditSoftwareOnClient_createObjects(auditSoftwareOnClients)
		if auditHardwareOnHosts:
			self.auditHardwareOnHost_createObjects(auditHardwareOnHosts)
		if licenseOnClients:
			self.licenseOnClient_createObjects(licenseOnClients)
		if softwareLicenses:
			self.softwareLicense_createObjects(softwareLicenses)
	
	def host_renameOpsiDepotserver(self, id, newId):
		id          = forceHostId(id)
		newId       = forceHostId(newId)
		oldHostname = id.split('.')[0]
		newHostname = newId.split('.')[0]
		
		depots = self._backend.host_getObjects(type = 'OpsiDepotserver', id = id)
		if not depots:
			raise BackendMissingDataError(u"Cannot rename: depot '%s' not found" % id)
		if self._backend.host_getObjects(id = newId):
			raise BackendError(u"Cannot rename: host '%s' already exists" % newId)
		
		depot = depots[0]
		isConfigServer = bool(self.host_getIdents(type = 'OpsiConfigserver', id = id))
		
		productOnDepots = []
		for productOnDepot in self._backend.productOnDepot_getObjects(depotId = id):
			productOnDepot.setDepotId(newId)
			productOnDepots.append(productOnDepot)
		
		modifiedProductProperties = []
		for productProperty in self._backend.productProperty_getObjects():
			if productProperty.possibleValues and id in productProperty.possibleValues:
				productProperty.possibleValues.remove(id)
				productProperty.possibleValues.append(newId)
				if not productProperty in modifiedProductProperties:
					modifiedProductProperties.append(productProperty)
			if productProperty.defaultValues and id in productProperty.defaultValues:
				productProperty.defaultValues.remove(id)
				productProperty.defaultValues.append(newId)
				if not productProperty in modifiedProductProperties:
					modifiedProductProperties.append(productProperty)
		if modifiedProductProperties:
			self.productProperty_updateObjects(modifiedProductProperties)
		
		productPropertyStates = []
		for productPropertyState in self._backend.productPropertyState_getObjects(objectId = id):
			productPropertyState.setObjectId(newId)
			if productPropertyState.values and id in productPropertyState.values:
				productPropertyState.values.remove(id)
				productPropertyState.values.append(newId)
			productPropertyStates.append(productPropertyState)
		
		modifiedConfigs = []
		for config in self._backend.config_getObjects():
			if config.possibleValues and id in config.possibleValues:
				config.possibleValues.remove(id)
				config.possibleValues.append(newId)
				if not config in modifiedConfigs:
					modifiedConfigs.append(config)
			if config.defaultValues and id in config.defaultValues:
				config.defaultValues.remove(id)
				config.defaultValues.append(newId)
				if not config in modifiedConfigs:
					modifiedConfigs.append(config)
		if modifiedConfigs:
			self.config_updateObjects(modifiedConfigs)
		
		configStates = []
		for configState in self._backend.configState_getObjects(objectId = id):
			configState.setObjectId(newId)
			if configState.values and id in configState.values:
				configState.values.remove(id)
				configState.values.append(newId)
			configStates.append(configState)
		
		logger.info(u"Deleting depot '%s'" % depot)
		self._backend.host_deleteObjects([ depot ])
		
		depot.setId(newId)
		if depot.repositoryRemoteUrl:
			depot.setRepositoryRemoteUrl(depot.repositoryRemoteUrl.replace(id, newId).replace(oldHostname, newHostname))
		if depot.depotRemoteUrl:
			depot.setDepotRemoteUrl(depot.depotRemoteUrl.replace(id, newId).replace(oldHostname, newHostname))
		if depot.depotWebdavUrl:
			depot.setDepotWebdavUrl(depot.depotWebdavUrl.replace(id, newId).replace(oldHostname, newHostname))
		self.host_createObjects([ depot ])
		
		if productOnDepots:
			self.productOnDepot_createObjects(productOnDepots)
		if productPropertyStates:
			self.productPropertyState_createObjects(productPropertyStates)
		if configStates:
			self.configState_createObjects(configStates)
		
		updateConfigs = []
		for config in self._backend.config_getObjects(id = ['clientconfig.configserver.url', 'clientconfig.depot.id']):
			if config.defaultValues:
				changed = False
				for i in range(len(config.defaultValues)):
					if (config.defaultValues[i].find(id) != -1):
						config.defaultValues[i] = config.defaultValues[i].replace(id, newId)
						changed = True
				if changed:
					updateConfigs.append(config)
		if updateConfigs:
			self.config_updateObjects(updateConfigs)
		
		updateConfigStates = []
		for configState in self._backend.configState_getObjects(configId = ['clientconfig.configserver.url', 'clientconfig.depot.id']):
			if configState.values:
				changed = False
				for i in range(len(configState.values)):
					if (configState.values[i].find(id) != -1):
						configState.values[i] = configState.values[i].replace(id, newId)
						changed = True
				if changed:
					updateConfigStates.append(configState)
		if updateConfigStates:
			self.configState_updateObjects(updateConfigStates)
		
		modifiedDepots = []
		for depot in self._backend.host_getObjects(type = 'OpsiDepotserver'):
			if depot.masterDepotId and (depot.masterDepotId == id):
				depot.masterDepotId = newId
				modifiedDepots.append(depot)
		if modifiedDepots:
			self.host_updateObjects(modifiedDepots)
		
	def host_createOpsiClient(self, id, opsiHostKey=None, description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, oneTimePassword=None, created=None, lastSeen=None):
		hash = locals()
		del hash['self']
		return self.host_createObjects(OpsiClient.fromHash(hash))
	
	def host_createOpsiDepotserver(self, id, opsiHostKey=None, depotLocalUrl=None, depotRemoteUrl=None, depotWebdavUrl=None, repositoryLocalUrl=None, repositoryRemoteUrl=None,
					description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, networkAddress=None, maxBandwidth=None, isMasterDepot=None, masterDepotId=None):
		hash = locals()
		del hash['self']
		return self.host_createObjects(OpsiDepotserver.fromHash(hash))
	
	def host_createOpsiConfigserver(self, id, opsiHostKey=None, depotLocalUrl=None, depotRemoteUrl=None, depotWebdavUrl=None, repositoryLocalUrl=None, repositoryRemoteUrl=None,
					description=None, notes=None, hardwareAddress=None, ipAddress=None, inventoryNumber=None, networkAddress=None, maxBandwidth=None, isMasterDepot=None, masterDepotId=None):
		hash = locals()
		del hash['self']
		return self.host_createObjects(OpsiConfigserver.fromHash(hash))
	
	def host_delete(self, id):
		if id is None: id = []
		return self._backend.host_deleteObjects(
				self._backend.host_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_createObjects(self, configs):
		result = []
		for config in forceObjectClassList(configs, Config):
			logger.info(u"Creating config '%s'" % config)
			self._backend.config_insertObject(config)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.config_getObjects(id = config.id)
				)
		return result
	
	def config_updateObjects(self, configs):
		result = []
		for config in forceObjectClassList(configs, Config):
			logger.info(u"Updating config %s" % config)
			if self.config_getIdents(id = config.id):
				self._backend.config_updateObject(config)
			else:
				logger.info(u"Config %s does not exist, creating" % config)
				self._backend.config_insertObject(config)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.config_getObjects(id = config.id)
				)
		return result
	
	def config_create(self, id, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		hash = locals()
		del hash['self']
		return self.config_createObjects(Config.fromHash(hash))
	
	def config_createUnicode(self, id, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		hash = locals()
		del hash['self']
		return self.config_createObjects(UnicodeConfig.fromHash(hash))
	
	def config_createBool(self, id, description=None, defaultValues=None):
		hash = locals()
		del hash['self']
		return self.config_createObjects(BoolConfig.fromHash(hash))
	
	def config_delete(self, id):
		if id is None: id = []
		return self._backend.config_deleteObjects(
				self.config_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_getObjects(self, attributes=[], **filter):
		'''
		Add default objects to result for objects which do not exist in backend
		'''
		# objectIds can only be client ids
		
		# Get config states from backend
		configStates = self._backend.configState_getObjects(attributes, **filter)
		
		if not self._options['addConfigStateDefaults']:
			return configStates
		
		# Create data structure for config states to find missing ones
		css = {}
		for cs in self._backend.configState_getObjects(
						attributes = ['objectId', 'configId'],
						objectId   = filter.get('objectId', []),
						configId   = filter.get('configId', [])):
			if not css.has_key(cs.objectId):
				css[cs.objectId] = []
			css[cs.objectId].append(cs.configId)
		
		clientIds = self.host_getIdents(id = filter.get('objectId'), returnType = 'unicode')
		# Create missing config states
		for config in self._backend.config_getObjects(id = filter.get('configId')):
			logger.debug(u"Default values for '%s': %s" % (config.id, config.defaultValues))
			for clientId in clientIds:
				if not config.id in css.get(clientId, []):
					# Config state does not exist for client => create default
					cf = ConfigState(
						configId = config.id,
						objectId = clientId,
						values   = config.defaultValues
					)
					cf.setGeneratedDefault(True)
					configStates.append(cf)
		return configStates
	
	def _configStateMatchesDefault(self, configState):
		isDefault = False
		configs = self._backend.config_getObjects(attributes = ['defaultValues'], id = configState.configId)
		if configs and not configs[0].defaultValues and (len(configs[0].defaultValues) == len(configState.values)):
			isDefault = True
			for v in configState.values:
				if not v in configs[0].defaultValues:
					isDefault = False
					break
		return isDefault
	
	def _configState_checkValid(self, configState):
		if (configState.configId == 'clientconfig.depot.id'):
			if not configState.values or not configState.values[0]:
				raise ValueError(u"No valid depot id given")
			depotId = forceHostId(configState.values[0])
			if not self.host_getIdents(type = 'OpsiDepotserver', id = depotId, isMasterDepot = True):
				raise ValueError(u"Depot '%s' does not exist or is not a master depot" % depotId)
			
	def configState_insertObject(self, configState):
		if self._options['deleteConfigStateIfDefault'] and self._configStateMatchesDefault(configState):
			# Do not insert configStates which match the default
			logger.debug(u"Not inserting configState '%s', because it does not differ from defaults" % configState)
			return
		self._configState_checkValid(configState)
		self._backend.configState_insertObject(configState)
	
	def configState_updateObject(self, configState):
		if self._options['deleteConfigStateIfDefault'] and self._configStateMatchesDefault(configState):
			# Do not update configStates which match the default
			logger.debug(u"Deleting configState '%s', because it does not differ from defaults" % configState)
			return self._backend.configState_deleteObjects(configState)
		self._configState_checkValid(configState)
		self._backend.configState_updateObject(configState)
	
	def configState_createObjects(self, configStates):
		result = []
		for configState in forceObjectClassList(configStates, ConfigState):
			logger.info(u"Creating configState '%s'" % configState)
			self.configState_insertObject(configState)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.configState_getObjects(
						configId = configState.configId,
						objectId = configState.objectId
					)
				)
		return result
	
	def configState_updateObjects(self, configStates):
		result = []
		for configState in forceObjectClassList(configStates, ConfigState):
			logger.info(u"Updating configState %s" % configState)
			if self.configState_getIdents(
					configId = configState.configId,
					objectId = configState.objectId):
				self.configState_updateObject(configState)
			else:
				logger.info(u"ConfigState %s does not exist, creating" % configState)
				self.configState_insertObject(configState)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.configState_getObjects(
						configId = configState.configId,
						objectId = configState.objectId
					)
				)
		return result
	
	def configState_create(self, configId, objectId, values=None):
		hash = locals()
		del hash['self']
		return self.configState_createObjects(ConfigState.fromHash(hash))
	
	def configState_delete(self, configId, objectId):
		if configId is None: configId = []
		if objectId is None: objectId = []
		return self._backend.configState_deleteObjects(
				self._backend.configState_getObjects(
					configId = configId,
					objectId = objectId))
	
	def configState_getClientToDepotserver(self, depotIds=[], clientIds=[], masterOnly=True, productIds=[]):
		#addConfigStateDefaults = self._options['addConfigStateDefaults']
		addConfigStateDefaults = self.backend_getOptions().get('addConfigStateDefaults', False)
		result = []
		masterDepotIds = self.host_getIdents(type = 'OpsiDepotserver', isMasterDepot = True, id = depotIds)
		clientIds = self.host_getIdents(type = 'OpsiClient', id = clientIds)
		if not clientIds:
			return result
		usedMasterDepotIds = []
		try:
			#self._options['addConfigStateDefaults'] = True
			self.backend_setOptions({'addConfigStateDefaults': True})
			for configState in self.configState_getObjects(configId = u'clientconfig.depot.id', objectId = clientIds):
				#if not configState.objectId in knownClientIds:
				#	logger.debug(u"Skipping objectId '%s': not a opsi client" % configState.objectId)
				#	continue
				if not configState.values or not configState.values[0]:
					logger.error(u"No depot server configured for client '%s'" % configState.objectId)
					continue
				depotId = configState.values[0]
				if not depotId in masterDepotIds:
					continue
				if not depotId in usedMasterDepotIds:
					usedMasterDepotIds.append(depotId)
				result.append({ 'depotId': depotId, 'clientId': configState.objectId, 'slaveDepotIds': [] })
		finally:
			self.backend_setOptions({'addConfigStateDefaults': addConfigStateDefaults})
			#self._options['addConfigStateDefaults'] = addConfigStateDefaults
		if masterOnly:
			return result
		
		masterDepotIds = usedMasterDepotIds
		if not masterDepotIds:
			raise BackendConfigurationError(u"No master depots found")
		
		depotIds = []
		masterToSlave = {}
		for masterDepotId in masterDepotIds:
			depotIds.append(masterDepotId)
			masterToSlave[masterDepotId] = []
		
		for depot in self.host_getObjects(type = 'OpsiDepotserver'):
			if not depot.masterDepotId or not depot.masterDepotId in masterDepotIds:
				continue
			masterToSlave[depot.masterDepotId].append(depot.id)
			if not depot.id in depotIds:
				depotIds.append(depot.id)
		
		if (len(depotIds) <= 1):
			return result
		
		pHash = {}
		for depotId in depotIds:
			pHash[depotId] = []
		
		for pod in self.productOnDepot_getObjects(depotId = depotIds, productId = productIds):
			if not pHash.has_key(pod.depotId):
				continue
			pHash[pod.depotId].append(u'%s;%s;%s' % (pod.productId, pod.productVersion, pod.packageVersion))
		
		if productIds:
			for masterDepotId in masterDepotIds:
				pIds = []
				for p in pHash[masterDepotId]:
					pIds.append(p.split(';')[0])
				for productId in productIds:
					if not productId in pIds:
						raise ValueError(u"Product '%s' not found on master depot '%s'" % (productId, masterDepotId))
		
		for (masterDepotId, slaveDepotIds) in masterToSlave.items():
			synchronousSlaveDepotIds = []
			for slaveDepotId in slaveDepotIds:
				if not pHash.has_key(slaveDepotId):
					continue
				synchronous = True
				for product in pHash[masterDepotId]:
					if not product in pHash[slaveDepotId]:
						synchronous = False
						break
				if synchronous:
					synchronousSlaveDepotIds.append(slaveDepotId)
			masterToSlave[masterDepotId] = synchronousSlaveDepotIds
		
		for i in range(len(result)):
			result[i]['slaveDepotIds'] = masterToSlave[result[i]['depotId']]
		
		return result
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_createObjects(self, products):
		result = []
		for product in forceObjectClassList(products, Product):
			logger.info(u"Creating product %s" % product)
			self._backend.product_insertObject(product)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.product_getObjects(
						id             = product.id,
						productVersion = product.productVersion,
						packageVersion = product.packageVersion
					)
				)
		return result
	
	def product_updateObjects(self, products):
		result = []
		for product in forceObjectClassList(products, Product):
			logger.info(u"Updating product %s" % product)
			if self.product_getIdents(
					id             = product.id,
					productVersion = product.productVersion,
					packageVersion = product.packageVersion):
				self._backend.product_updateObject(product)
			else:
				logger.info(u"Product %s does not exist, creating" % product)
				self._backend.product_insertObject(product)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.product_getObjects(
						id             = product.id,
						productVersion = product.productVersion,
						packageVersion = product.packageVersion
					)
				)
		return result
		
	def product_createLocalboot(self, id, productVersion, packageVersion, name=None, licenseRequired=None,
					setupScript=None, uninstallScript=None, updateScript=None, alwaysScript=None, onceScript=None,
					priority=None, description=None, advice=None, changelog=None, productClassIds=None, windowsSoftwareIds=None):
		hash = locals()
		del hash['self']
		return self.product_createObjects(LocalbootProduct.fromHash(hash))
	
	def product_createNetboot(self, id, productVersion, packageVersion, name=None, licenseRequired=None,
					setupScript=None, uninstallScript=None, updateScript=None, alwaysScript=None, onceScript=None,
					priority=None, description=None, advice=None, changelog=None, productClassIds=None, windowsSoftwareIds=None,
					pxeConfigTemplate=None):
		hash = locals()
		del hash['self']
		return self.product_createObjects(NetbootProduct.fromHash(hash))
	
	def product_delete(self, productId, productVersion, packageVersion):
		if productId is None:      productId = []
		if productVersion is None: productVersion = []
		if packageVersion is None: packageVersion = []
		return self._backend.product_deleteObjects(
				self._backend.product_getObjects(
					productId      = productId,
					productVersion = productVersion,
					packageVersion = packageVersion))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _adjustProductPropertyStates(self, productProperty):
		'''
		A productProperty was created or updated
		check if the current productPropertyStates are valid
		'''
		if productProperty.editable or not productProperty.possibleValues:
			return
		
		# Check if productPropertyStates are possible
		depotIds = []
		for productOnDepot in self.productOnDepot_getObjects(
					productId      = productProperty.productId,
					productVersion = productProperty.productVersion,
					packageVersion = productProperty.packageVersion):
			if not productOnDepot.depotId in depotIds:
				depotIds.append(productOnDepot.depotId)
		
		if not depotIds:
			return
		
		# Get depot to client assignment
		clientIds = []
		for clientToDepot in self.configState_getClientToDepotserver(depotIds = depotIds):
			if not clientToDepot['clientId'] in clientIds:
				clientIds.append(clientToDepot['clientId'])
		deleteProductPropertyStates = []
		objectIds = depotIds
		objectIds.extend(clientIds)
		
		for productPropertyState in self.productPropertyState_getObjects(
					objectId   = objectIds,
					productId  = productProperty.productId,
					propertyId = productProperty.propertyId):
			changed = False
			newValues = []
			for v in productPropertyState.values:
				if v in productProperty.possibleValues:
					newValues.append(v)
				else:
					changed = True
			if changed:
				productPropertyState.setValues(newValues)
				deleteProductPropertyStates.append(productPropertyState)
		if deleteProductPropertyStates:
			self.productPropertyState_deleteObjects(deleteProductPropertyStates)
	
	def productProperty_createObjects(self, productProperties):
		result = []
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			logger.info(u"Creating productProperty %s" % productProperty)
			self._backend.productProperty_insertObject(productProperty)
			###########self._adjustProductPropertyStates(productProperty)
			
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productProperty_getObjects(
						productId      = productProperty.productId,
						productVersion = productProperty.productVersion,
						packageVersion = productProperty.packageVersion,
						propertyId     = productProperty.propertyId
					)
				)
		return result
		
	def productProperty_updateObjects(self, productProperties):
		result = []
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			logger.info(u"Creating productProperty %s" % productProperty)
			if self.productProperty_getIdents(
					productId      = productProperty.productId,
					productVersion = productProperty.productVersion,
					packageVersion = productProperty.packageVersion,
					propertyId     = productProperty.propertyId):
				self._backend.productProperty_updateObject(productProperty)
				####################self._adjustProductPropertyStates(productProperty)
			else:
				logger.info(u"ProductProperty %s does not exist, creating" % productProperty)
				self._backend.productProperty_insertObject(productProperty)
				####################self._adjustProductPropertyStates(productProperty)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productProperty_getObjects(
						productId      = productProperty.productId,
						productVersion = productProperty.productVersion,
						packageVersion = productProperty.packageVersion,
						propertyId     = productProperty.propertyId
					)
				)
		return result
		
	def productProperty_create(self, productId, productVersion, packageVersion, propertyId, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		hash = locals()
		del hash['self']
		return self.productProperty_createObjects(ProductProperty.fromHash(hash))
	
	def productProperty_createUnicode(self, productId, productVersion, packageVersion, propertyId, description=None, possibleValues=None, defaultValues=None, editable=None, multiValue=None):
		hash = locals()
		del hash['self']
		return self.productProperty_createObjects(UnicodeProductProperty.fromHash(hash))
	
	def productProperty_createBool(self, productId, productVersion, packageVersion, propertyId, description=None, defaultValues=None):
		hash = locals()
		del hash['self']
		return self.productProperty_createObjects(BoolProductProperty.fromHash(hash))
	
	def productProperty_delete(self, productId, productVersion, packageVersion, propertyId):
		if productId is None:      productId      = []
		if productVersion is None: productVersion = []
		if packageVersion is None: packageVersion = []
		if propertyId is None:     propertyId     = []
		return self._backend.productOnDepot_deleteObjects(
				self._backend.productOnDepot_getObjects(
					productId      = productId,
					productVersion = productVersion,
					packageVersion = packageVersion,
					propertyIds    = propertyId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                       -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_createObjects(self, productDependencies):
		result = []
		for productDependency in forceObjectClassList(productDependencies, ProductDependency):
			logger.info(u"Creating productDependency %s" % productDependency)
			self._backend.productDependency_insertObject(productDependency)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productDependency_getObjects(
						productId         = productDependency.productId,
						productVersion    = productDependency.productVersion,
						packageVersion    = productDependency.packageVersion,
						productAction     = productDependency.productAction,
						requiredProductId = productDependency.requiredProductId
					)
				)
		return result
		
	def productDependency_updateObjects(self, productDependencies):
		result = []
		for productDependency in forceObjectClassList(productDependencies, ProductDependency):
			logger.info(u"Updating productDependency %s" % productDependency)
			if self.productDependency_getIdents(
					productId         = productDependency.productId,
					productVersion    = productDependency.productVersion,
					packageVersion    = productDependency.packageVersion,
					productAction     = productDependency.productAction,
					requiredProductId = productDependency.requiredProductId):
				self._backend.productDependency_updateObject(productDependency)
			else:
				logger.info(u"ProductDependency %s does not exist, creating" % productDependency)
				self._backend.productDependency_insertObject(productDependency)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productDependency_getObjects(
						productId         = productDependency.productId,
						productVersion    = productDependency.productVersion,
						packageVersion    = productDependency.packageVersion,
						productAction     = productDependency.productAction,
						requiredProductId = productDependency.requiredProductId
					)
				)
		return result
	
	def productDependency_create(self, productId, productVersion, packageVersion, productAction, requiredProductId, requiredProductVersion=None, requiredPackageVersion=None, requiredAction=None, requiredInstallationStatus=None, requirementType=None):
		hash = locals()
		del hash['self']
		return self.productDependency_createObjects(ProductDependency.fromHash(hash))
	
	def productDependency_delete(self, productId, productVersion, packageVersion, productAction, requiredProductId):
		if productId is None:         productId         = []
		if productVersion is None:    productVersion    = []
		if packageVersion is None:    packageVersion    = []
		if productAction is None:     productAction     = []
		if requiredProductId is None: requiredProductId = []
		return self._backend.productDependency_deleteObjects(
				self._backend.productDependency_getObjects(
					productId         = productId,
					productVersion    = productVersion,
					packageVersion    = packageVersion,
					productAction     = productAction,
					requiredProductId = requiredProductId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		'''
		If productOnDepot exits (same productId, same depotId, different version)
		then update existing productOnDepot instead of creating a new one
		'''
		currentProductOnDepots = self._backend.productOnDepot_getObjects(
						productId = productOnDepot.productId,
						depotId   = productOnDepot.depotId)
		if currentProductOnDepots:
			currentProductOnDepot = currentProductOnDepots[0]
			logger.info(u"Updating productOnDepot %s instead of creating a new one" % currentProductOnDepot)
			currentProductOnDepot.update(productOnDepot)
			self._backend.productOnDepot_insertObject(currentProductOnDepot)
		else:
			self._backend.productOnDepot_insertObject(productOnDepot)
	
	def productOnDepot_createObjects(self, productOnDepots):
		result = []
		for productOnDepot in forceObjectClassList(productOnDepots, ProductOnDepot):
			logger.info(u"Creating productOnDepot %s" % productOnDepot.toHash())
			self.productOnDepot_insertObject(productOnDepot)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productOnDepot_getObjects(
						productId = productOnDepot.productId,
						depotId   = productOnDepot.depotId
					)
				)
		return result
	
	def productOnDepot_updateObjects(self, productOnDepots):
		result = []
		productOnDepots = forceObjectClassList(productOnDepots, ProductOnDepot)
		for productOnDepot in productOnDepots:
			logger.info(u"Updating productOnDepot '%s'" % productOnDepot)
			if self.productOnDepot_getIdents(
					productId      = productOnDepot.productId,
					productType    = productOnDepot.productType,
					productVersion = productOnDepot.productVersion,
					packageVersion = productOnDepot.packageVersion,
					depotId        = productOnDepot.depotId):
				self._backend.productOnDepot_updateObject(productOnDepot)
			else:
				logger.info(u"ProductOnDepot %s does not exist, creating" % productOnDepot)
				self.productOnDepot_insertObject(productOnDepot)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productOnDepot_getObjects(
						productId = productOnDepot.productId,
						depotId   = productOnDepot.depotId
					)
				)
		return result
	
	def productOnDepot_create(self, productId, productType, productVersion, packageVersion, depotId, locked=None):
		hash = locals()
		del hash['self']
		return self.productOnDepot_createObjects(ProductOnDepot.fromHash(hash))
	
	def productOnDepot_deleteObjects(self, productOnDepots):
		productOnDepots = forceObjectClassList(productOnDepots, ProductOnDepot)
		products = {}
		for productOnDepot in productOnDepots:
			if not products.has_key(productOnDepot.productId):
				products[productOnDepot.productId] = {}
			if not products[productOnDepot.productId].has_key(productOnDepot.productVersion):
				products[productOnDepot.productId][productOnDepot.productVersion] = []
			if not productOnDepot.packageVersion in products[productOnDepot.productId][productOnDepot.productVersion]:
				products[productOnDepot.productId][productOnDepot.productVersion].append(productOnDepot.packageVersion)
		
		ret = self._backend.productOnDepot_deleteObjects(productOnDepots)
		
		if products:
			for (productId, versions) in products.items():
				for (productVersion, packageVersions) in versions.items():
					for packageVersion in packageVersions:
						if not self.productOnDepot_getIdents(
								productId      = productId,
								productVersion = productVersion,
								packageVersion = packageVersion):
							# Product not found on any depot
							self._backend.product_deleteObjects(
								self._backend.product_getObjects(
									id      = [ productId ],
									productVersion = [ productVersion ],
									packageVersion = [ packageVersion ]))
		return ret
		
	def productOnDepot_delete(self, productId, productVersion, packageVersion, depotId):
		if productId is None:      productId      = []
		if productVersion is None: productVersion = []
		if packageVersion is None: packageVersion = []
		if depotId is None:        depotId        = []
		return self._backend.productOnDepot_deleteObjects(
				self._backend.productOnDepot_getObjects(
					productId      = productId,
					productVersion = productVersion,
					packageVersion = packageVersion,
					depotId        = depotId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	
	def _productOnClient_processWithFunction(self, productOnClients, function):
		# Get client and product ids
		productOnClientsByClient = {}
		productIds = []
		for poc in productOnClients:
			if not poc.getClientId() in productOnClientsByClient.keys():
				productOnClientsByClient[poc.getClientId()] = []
			productOnClientsByClient[poc.getClientId()].append(poc)
			if not poc.productId in productIds:
				productIds.append(poc.productId)
			
		# Get depot to client assignment
		depotToClients = {}
		for clientToDepot in self.configState_getClientToDepotserver(clientIds = productOnClientsByClient.keys()):
			if not depotToClients.has_key(clientToDepot['depotId']):
				depotToClients[clientToDepot['depotId']] = []
			depotToClients[clientToDepot['depotId']].append(clientToDepot['clientId'])
		
		productByProductIdAndVersion = {}
		for product in self._backend.product_getObjects(id = productIds):
			if not productByProductIdAndVersion.has_key(product.id):
				productByProductIdAndVersion[product.id] = {}
			if not productByProductIdAndVersion[product.id].has_key(product.productVersion):
				productByProductIdAndVersion[product.id][product.productVersion] = {}
			productByProductIdAndVersion[product.id][product.productVersion][product.packageVersion] = product
		
		additionalProductIds = []
		productDependenciesByProductIdAndVersion = {}
		def addDependencies(additionalProductIds, productDependency, productDependenciesByProductIdAndVersion):
			if not productDependenciesByProductIdAndVersion.has_key(productDependency.productId):
				productDependenciesByProductIdAndVersion[productDependency.productId] = {}
			if not productDependenciesByProductIdAndVersion[productDependency.productId].has_key(productDependency.productVersion):
				productDependenciesByProductIdAndVersion[productDependency.productId][productDependency.productVersion] = {}
			if not productDependenciesByProductIdAndVersion[productDependency.productId][productDependency.productVersion].has_key(productDependency.packageVersion):
				productDependenciesByProductIdAndVersion[productDependency.productId][productDependency.productVersion][productDependency.packageVersion] = []
			productDependenciesByProductIdAndVersion[productDependency.productId][productDependency.productVersion][productDependency.packageVersion].append(productDependency)
			if not productDependency.requiredProductId in productIds and not productDependency.requiredProductId in additionalProductIds:
				additionalProductIds.append(productDependency.requiredProductId)
				for productDependency in self._backend.productDependency_getObjects(productId = productDependency.requiredProductId):
					addDependencies(additionalProductIds, productDependency, productDependenciesByProductIdAndVersion)
		for productDependency in self._backend.productDependency_getObjects(productId = productIds):
			addDependencies(additionalProductIds, productDependency, productDependenciesByProductIdAndVersion)
		
		if additionalProductIds:
			for product in self._backend.product_getObjects(id = additionalProductIds):
				if not productByProductIdAndVersion.has_key(product.id):
					productByProductIdAndVersion[product.id] = {}
				if not productByProductIdAndVersion[product.id].has_key(product.productVersion):
					productByProductIdAndVersion[product.id][product.productVersion] = {}
				productByProductIdAndVersion[product.id][product.productVersion][product.packageVersion] = product
			productIds.extend(additionalProductIds)
		
		productOnClients = []
		for (depotId, clientIds) in depotToClients.items():
			products = []
			productDependencies = []
			for productOnDepot in self._backend.productOnDepot_getObjects(depotId = depotId, productId = productIds):
				product = productByProductIdAndVersion.get(productOnDepot.productId, {}).get(productOnDepot.productVersion, {}).get(productOnDepot.packageVersion)
				if product is None:
					raise BackendMissingDataError(u"Product '%s', productVersion '%s', packageVersion '%s' not found" \
							% (productOnDepot.productId, productOnDepot.productVersion, productOnDepot.packageVersion))
				products.append(product)
				def addDependencies(product, products, productDependencies, productByProductIdAndVersion, productDependenciesByProductIdAndVersion):
					dependencies = productDependenciesByProductIdAndVersion.get(product.id, {}).get(product.productVersion, {}).get(product.packageVersion, [])
					for dep in dependencies:
						product = productByProductIdAndVersion.get(dep.productId, {}).get(dep.productVersion, {}).get(dep.packageVersion)
						if product:
							if not product in products:
								products.append(product)
							if not dep in productDependencies:
								productDependencies.append(dep)
								addDependencies(product, products, productDependencies, productByProductIdAndVersion, productDependenciesByProductIdAndVersion)
				addDependencies(product, products, productDependencies, productByProductIdAndVersion, productDependenciesByProductIdAndVersion)
				
			for clientId in clientIds:
				productOnClients.extend(
					function(
						productOnClients    = productOnClientsByClient[clientId],
						availableProducts   = products,
						productDependencies = productDependencies
					)
				)
		return productOnClients
	
	def productOnClient_generateSequence(self, productOnClients):
		generateProductOnClientSequence = OPSI.SharedAlgorithm.generateProductOnClientSequence_algorithm2
		configs = self._context.config_getObjects(id = "product_sort_algorithm")
		if configs and ("product_on_client" in configs[0].getDefaultValues() or "algorithm1" in configs[0].getDefaultValues()):
			generateProductOnClientSequence = OPSI.SharedAlgorithm.generateProductOnClientSequence_algorithm1
		
		return self._productOnClient_processWithFunction(productOnClients, generateProductOnClientSequence)
		
	def productOnClient_addDependencies(self, productOnClients):
		return self._productOnClient_processWithFunction(productOnClients, OPSI.SharedAlgorithm.addDependentProductOnClients)
	
	def productOnClient_getObjects(self, attributes=[], **filter):
		'''
		possible attributes/filter-keys of ProductOnClient are:
			productId
			productType
			clientId
			targetState
			installationStatus
			actionRequest
			lastAction
			actionProgress
			actionResult
			productVersion
			packageVersion
			modificationTime
		
		missing ProductOnClients will be created with the following defaults:
			installationStatus = u'not_installed'
			actionRequest      = u'none'
			productVersion     = None
			packageVersion     = None
			modificationTime   = None
			targetState        = None
			lastAction         = None
			actionProgress     = None
			actionResult       = None
		'''
		
		pocAttributes = attributes
		pocFilter = dict(filter)
		
		defaultMatchesFilter = \
				    (not filter.get('installationStatus') or 'not_installed' in forceList(filter['installationStatus'])) \
				and (not filter.get('actionRequest')      or 'none'          in forceList(filter['actionRequest'])) \
				and (not filter.get('productVersion')     or None            in forceList(filter['productVersion'])) \
				and (not filter.get('packageVersion')     or None            in forceList(filter['packageVersion'])) \
				and (not filter.get('modificationTime')   or None            in forceList(filter['modificationTime'])) \
				and (not filter.get('targetState')        or None            in forceList(filter['targetState'])) \
				and (not filter.get('lastAction')         or None            in forceList(filter['lastAction'])) \
				and (not filter.get('actionProgress')     or None            in forceList(filter['actionProgress'])) \
				and (not filter.get('actionResult')       or None            in forceList(filter['actionResult']))
		
		if (self._options['addProductOnClientDefaults'] and defaultMatchesFilter) or self._options['processProductOnClientSequence']:
			# Do not filter out ProductOnClients on the basis of these attributes in this case
			# If filter is kept unchanged we cannot distinguish between "missing" and "filtered" ProductOnClients
			# We also need to know installationStatus and actionRequest of every product to create sequence
			pocFilter = {}
			for (key, value) in filter.items():
				if key in ('installationStatus', 'actionRequest', 'productVersion', 'packageVersion', 'modificationTime', 'targetState', 'lastAction', 'actionProgress', 'actionResult'):
					continue
				pocFilter[key] = value
				
		if (self._options['addProductOnClientDefaults'] or self._options['processProductOnClientSequence']) and attributes:
			# In this case we definetly need to add the following attributes
			if not 'installationStatus' in pocAttributes: pocAttributes.append('installationStatus')
			if not 'actionRequest'      in pocAttributes: pocAttributes.append('actionRequest')
			if not 'productVersion'     in pocAttributes: pocAttributes.append('productVersion')
			if not 'packageVersion'     in pocAttributes: pocAttributes.append('packageVersion')
		
		# Get product states from backend
		productOnClients = self._backend.productOnClient_getObjects(pocAttributes, **pocFilter)
		logger.debug(u"Got productOnClients")
		
		if not (self._options['addProductOnClientDefaults'] and defaultMatchesFilter) and not self._options['processProductOnClientSequence']:
			# No adjustment needed => done!
			return productOnClients
		
		logger.debug(u"Need to adjust productOnClients")
		
		# Create missing product states if addProductOnClientDefaults is set
		if self._options['addProductOnClientDefaults']:
			# Get all client ids which match the filter
			clientIds = self.host_getIdents(id = pocFilter.get('clientId'), returnType = 'unicode')
			logger.debug(u"   * got clientIds")
			
			# Get depot to client assignment
			depotToClients = {}
			for clientToDepot in self.configState_getClientToDepotserver(clientIds = clientIds):
				if not depotToClients.has_key(clientToDepot['depotId']):
					depotToClients[clientToDepot['depotId']] = []
				depotToClients[clientToDepot['depotId']].append(clientToDepot['clientId'])
			logger.debug(u"   * got depotToClients")
			
			
			productOnDepots = {}
			# Get product on depots which match the filter
			for depotId in depotToClients.keys():
				productOnDepots[depotId] = self._backend.productOnDepot_getObjects(
								depotId        = depotId,
								productId      = pocFilter.get('productId'),
								productType    = pocFilter.get('productType'),
								productVersion = pocFilter.get('productVersion'),
								packageVersion = pocFilter.get('packageVersion'))
			
			logger.debug(u"   * got productOnDepots")
			
			# Create data structure for product states to find missing ones
			pocByClientIdAndProductId = {}
			for clientId in clientIds:
				pocByClientIdAndProductId[clientId] = {}
			for poc in productOnClients:
				pocByClientIdAndProductId[poc.clientId][poc.productId] = poc
			
			logger.debug(u"   * created pocByClientIdAndProductId")
			#for (clientId, pocs) in pocByClientIdAndProductId.items():
			#	for (productId, poc) in pocs.items():
			#		logger.debug2(u"      [%s] %s: %s" % (clientId, productId, poc.toHash()))
			
			for (depotId, depotClientIds) in depotToClients.items():
				for clientId in depotClientIds:
					for pod in productOnDepots[depotId]:
						if not pocByClientIdAndProductId[clientId].has_key(pod.productId):
							logger.debug(u"      - creating default productOnClient for clientId '%s', productId '%s'" % (clientId, pod.productId))
							poc = ProductOnClient(
									productId          = pod.productId,
									productType        = pod.productType,
									clientId           = clientId,
									installationStatus = u'not_installed',
									actionRequest      = u'none',
							)
							poc.setGeneratedDefault(True)
							productOnClients.append(poc)
			
			logger.debug(u"   * created productOnClient defaults")
			#for (clientId, pocs) in pocByClientIdAndProductId.items():
			#	for (productId, poc) in pocs.items():
			#		logger.debug2(u"      [%s] %s: %s" % (clientId, productId, poc.toHash()))
		
		if not self._options['addProductOnClientDefaults'] and not self._options['processProductOnClientSequence']:
			return productOnClients
		
		if self._options['processProductOnClientSequence']:
			logger.debug(u"   * generating productOnClient sequence")
			productOnClients = self.productOnClient_generateSequence(productOnClients)
		
		productOnClientsFiltered = []
		for productOnClient in productOnClients:
			if self._objectHashMatches(productOnClient.toHash(), **filter):
				productOnClientsFiltered.append(productOnClient)
		return productOnClientsFiltered
		
		
	def _productOnClientUpdateOrCreate(self, productOnClient, update=False):
		nextProductOnClient = None
		currentProductOnClients = self._backend.productOnClient_getObjects(
							productId = productOnClient.productId,
							clientId  = productOnClient.clientId)
		if currentProductOnClients:
			'''
			If productOnClient exits (same productId, same clientId, different version)
			then update existing productOnClient instead of creating a new one
			'''
			nextProductOnClient = currentProductOnClients[0].clone()
			if update:
				nextProductOnClient.update(productOnClient, updateWithNoneValues = False)
			else:
				logger.info(u"Updating productOnClient %s instead of creating a new one" % nextProductOnClient)
				nextProductOnClient.update(productOnClient, updateWithNoneValues = True)
		else:
			nextProductOnClient = productOnClient.clone()
		
		if nextProductOnClient.installationStatus:
			#if not nextProductOnClient.actionResult:
			#	nextProductOnClient.setActionResult('none')
			#if not nextProductOnClient.actionProgress:
			#	nextProductOnClient.setActionProgress(u'')
			if (nextProductOnClient.installationStatus == 'installed'):
				# TODO: Check if product exists?
				if not nextProductOnClient.productVersion or not nextProductOnClient.packageVersion:
					clientToDepots = self.configState_getClientToDepotserver(clientIds = [nextProductOnClient.clientId])
					if not clientToDepots:
						raise BackendError(u"Cannot set productInstallationStatus 'installed' for product '%s' on client '%s': product/package version not set and depot for client not found" \
									% (nextProductOnClient.productId, nextProductOnClient.clientId))
					
					productOnDepots = self._backend.productOnDepot_getObjects(
										depotId   = clientToDepots[0]['depotId'],
										productId = nextProductOnClient.productId)
					if not productOnDepots:
						raise BackendError(u"Cannot set productInstallationStatus 'installed' for product '%s' on client '%s': product/package version not set and product not found on depot '%s'" \
									% (nextProductOnClient.productId, nextProductOnClient.clientId, clientToDepots[0]['depotId']))
					nextProductOnClient.setProductVersion(productOnDepots[0].productVersion)
					nextProductOnClient.setPackageVersion(productOnDepots[0].packageVersion)
			else:
				nextProductOnClient.productVersion = None
				nextProductOnClient.packageVersion = None
			
		#if productOnClient.actionRequest:
		#	# An action request is about to change
		#	if not productOnClient.lastAction and (productOnClient.actionRequest != 'none'):
		#		nextProductOnClient.setLastAction(productOnClient.actionRequest)
		#	if not productOnClient.targetConfiguration:
		#		if   (productOnClient.actionRequest == 'setup'):
		#			nextProductOnClient.setTargetConfiguration('installed')
		#		elif (productOnClient.actionRequest == 'always'):
		#			nextProductOnClient.setTargetConfiguration('always')
		#		elif (productOnClient.actionRequest == 'uninstall'):
		#			nextProductOnClient.setTargetConfiguration('undefined')
		#	if not productOnClient.actionResult:
		#		nextProductOnClient.setActionResult('none')
		#	if not productOnClient.actionProgress:
		#		nextProductOnClient.setActionProgress(u'')
		
		nextProductOnClient.setModificationTime(timestamp())
		
		return self._backend.productOnClient_insertObject(nextProductOnClient)
		
	def productOnClient_insertObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		return self._productOnClientUpdateOrCreate(productOnClient, update = False)
	
	def productOnClient_updateObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		return self._productOnClientUpdateOrCreate(productOnClient, update = True)
	
	def productOnClient_createObjects(self, productOnClients):
		result = []
		
		productOnClients = forceObjectClassList(productOnClients, ProductOnClient)
		if self._options['addDependentProductOnClients']:
			productOnClients = self.productOnClient_addDependencies(productOnClients)
		
		for productOnClient in productOnClients:
			logger.info(u"Creating productOnClient %s" % productOnClient)
			self.productOnClient_insertObject(productOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productOnClient_getObjects(
						productId = productOnClient.productId,
						clientId  = productOnClient.clientId
					)
				)
		return result
	
	def productOnClient_updateObjects(self, productOnClients):
		result = []
		
		productOnClients = forceObjectClassList(productOnClients, ProductOnClient)
		if self._options['addDependentProductOnClients']:
			productOnClients = self.productOnClient_addDependencies(productOnClients)
		
		for productOnClient in productOnClients:
			logger.info(u"Updating productOnClient '%s'" % productOnClient)
			if self.productOnClient_getIdents(
					productId   = productOnClient.productId,
					productType = productOnClient.productType,
					clientId    = productOnClient.clientId):
				logger.info(u"ProductOnClient %s exist, updating" % productOnClient)
				self.productOnClient_updateObject(productOnClient)
			else:
				logger.info(u"ProductOnClient %s does not exist, creating" % productOnClient)
				self.productOnClient_insertObject(productOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productOnClient_getObjects(
						productId = productOnClient.productId,
						clientId  = productOnClient.clientId
					)
				)
		return result
		
	
	def productOnClient_create(self, productId, productType, clientId, installationStatus=None, actionRequest=None, lastAction=None, actionProgress=None, actionResult=None, productVersion=None, packageVersion=None, modificationTime=None):
		hash = locals()
		del hash['self']
		return self.productOnClient_createObjects(ProductOnClient.fromHash(hash))
	
	def productOnClient_delete(self, productId, clientId):
		if productId is None:  productId  = []
		if clientId is None:   clientId   = []
		return self._backend.productOnClient_deleteObjects(
				self._backend.productOnClient_getObjects(
					productId = productId,
					clientId  = clientId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_getObjects(self, attributes=[], **filter):
		'''
		Add default objects to result for objects which do not exist in backend
		'''
		# objectIds can be depot ids or client ids
		
		# Get product property states
		productPropertyStates = self._backend.productPropertyState_getObjects(attributes, **filter)
		
		if not self._options['addProductPropertyStateDefaults']:
			return productPropertyStates
		
		# Get depot to client assignment
		depotToClients = {}
		for clientToDepot in self.configState_getClientToDepotserver(clientIds = filter.get('objectId', [])):
			if not depotToClients.has_key(clientToDepot['depotId']):
				depotToClients[clientToDepot['depotId']] = []
			depotToClients[clientToDepot['depotId']].append(clientToDepot['clientId'])
		
		# Create data structure for product property states to find missing ones
		ppss = {}
		for pps in self._backend.productPropertyState_getObjects(
						attributes = ['objectId', 'productId', 'propertyId'],
						objectId   = filter.get('objectId', []),
						productId  = filter.get('productId', []),
						propertyId = filter.get('propertyId', [])):
			if not ppss.has_key(pps.objectId):
				ppss[pps.objectId] = {}
			if not ppss[pps.objectId].has_key(pps.productId):
				ppss[pps.objectId][pps.productId] = []
			ppss[pps.objectId][pps.productId].append(pps.propertyId)
		
		# Create missing product property states
		for (depotId, clientIds) in depotToClients.items():
			depotFilter = dict(filter)
			depotFilter['objectId'] = depotId
			for pps in self._backend.productPropertyState_getObjects(attributes, **depotFilter):
				for clientId in clientIds:
					if not pps.propertyId in ppss.get(clientId, {}).get(pps.productId, []):
						# Product property for client does not exist => add default (values of depot)
						productPropertyStates.append(
							ProductPropertyState(
								productId   = pps.productId,
								propertyId  = pps.propertyId,
								objectId    = clientId,
								values      = pps.values
							)
						)
		return productPropertyStates
	
	def productPropertyState_createObjects(self, productPropertyStates):
		result = []
		for productPropertyState in forceObjectClassList(productPropertyStates, ProductPropertyState):
			logger.info(u"Updating productPropertyState %s" % productPropertyState)
			self._backend.productPropertyState_insertObject(productPropertyState)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productPropertyState_getObjects(
						productId  = productPropertyState.productId,
						objectId   = productPropertyState.objectId,
						propertyId = productPropertyState.propertyId
					)
				)
		return result
	
	def productPropertyState_updateObjects(self, productPropertyStates):
		result = []
		productPropertyStates = forceObjectClassList(productPropertyStates, ProductPropertyState)
		for productPropertyState in productPropertyStates:
			logger.info(u"Updating productPropertyState '%s'" % productPropertyState)
			if self.productPropertyState_getIdents(
						productId  = productPropertyState.productId,
						objectId   = productPropertyState.objectId,
						propertyId = productPropertyState.propertyId):
				self._backend.productPropertyState_updateObject(productPropertyState)
			else:
				logger.info(u"ProductPropertyState %s does not exist, creating" % productPropertyState)
				self._backend.productPropertyState_insertObject(productPropertyState)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.productPropertyState_getObjects(
						productId  = productPropertyState.productId,
						objectId   = productPropertyState.objectId,
						propertyId = productPropertyState.propertyId
					)
				)
		return result
		
		
	def productPropertyState_create(self, productId, propertyId, objectId, values=None):
		hash = locals()
		del hash['self']
		return self.productPropertyState_createObjects(ProductPropertyState.fromHash(hash))
	
	def productPropertyState_delete(self, productId, propertyId, objectId):
		if productId is None:  productId  = []
		if propertyId is None: propertyId = []
		if objectId is None:   objectId   = []
		return self._backend.productPropertyState_deleteObjects(
				self._backend.productPropertyState_getObjects(
					productId  = productId,
					propertyId = propertyId,
					objectId   = objectId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_createObjects(self, groups):
		result = []
		for group in forceObjectClassList(groups, Group):
			logger.info(u"Creating group '%s'" % group)
			self._backend.group_insertObject(group)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.group_getObjects(id = group.id)
				)
		return result
	
	def group_updateObjects(self, groups):
		result = []
		groups = forceObjectClassList(groups, Group)
		for group in groups:
			logger.info(u"Updating group '%s'" % group)
			if self.group_getIdents(id = group.id):
				self._backend.group_updateObject(group)
			else:
				logger.info(u"Group %s does not exist, creating" % group)
				self._backend.group_insertObject(group)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.group_getObjects(id = group.id)
				)
		return result
	
	def group_createHostGroup(self, id, description=None, notes=None, parentGroupId=None):
		hash = locals()
		del hash['self']
		return self.group_createObjects(HostGroup.fromHash(hash))
	
	def group_delete(self, id):
		if id is None: id = []
		return self._backend.group_deleteObjects(
				self._backend.group_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_createObjects(self, objectToGroups):
		result = []
		for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
			logger.info(u"Creating objectToGroup %s" % objectToGroup)
			self._backend.objectToGroup_insertObject(objectToGroup)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.objectToGroup_getObjects(
						groupType = objectToGroup.groupType,
						groupId   = objectToGroup.groupId,
						objectId  = objectToGroup.objectId
					)
				)
		return result
	
	def objectToGroup_updateObjects(self, objectToGroups):
		result = []
		objectToGroups = forceObjectClassList(objectToGroups, ObjectToGroup)
		for objectToGroup in objectToGroups:
			logger.info(u"Updating objectToGroup %s" % objectToGroup)
			if self.objectToGroup_getIdents(
					groupType = objectToGroup.groupType,
					groupId   = objectToGroup.groupId,
					objectId  = objectToGroup.objectId):
				self._backend.objectToGroup_updateObject(objectToGroup)
			else:
				logger.info(u"ObjectToGroup %s does not exist, creating" % objectToGroup)
				self._backend.objectToGroup_insertObject(objectToGroup)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.objectToGroup_getObjects(
						groupType = objectToGroup.groupType,
						groupId   = objectToGroup.groupId,
						objectId  = objectToGroup.objectId
					)
				)
		return result
		
	
	def objectToGroup_create(self, groupType, groupId, objectId):
		hash = locals()
		del hash['self']
		return self.objectToGroup_createObjects(ObjectToGroup.fromHash(hash))
	
	def objectToGroup_delete(self, groupType, groupId, objectId):
		if not groupType: groupType  = []
		if not groupId:   groupId  = []
		if not objectId:  objectId = []
		return self._backend.objectToGroup_deleteObjects(
				self._backend.objectToGroup_getObjects(
					groupType = groupType,
					groupId   = groupId,
					objectId  = objectId))
	
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_createObjects(self, licenseContracts):
		result = []
		for licenseContract in forceObjectClassList(licenseContracts, LicenseContract):
			logger.info(u"Creating licenseContract %s" % licenseContract)
			self._backend.licenseContract_insertObject(licenseContract)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licenseContract_getObjects(id = licenseContract.id)
				)
		return result
		
	def licenseContract_updateObjects(self, licenseContracts):
		result = []
		licenseContracts = forceObjectClassList(licenseContracts, LicenseContract)
		for licenseContract in licenseContracts:
			logger.info(u"Updating licenseContract '%s'" % licenseContract)
			if self.licenseContract_getIdents(id = licenseContract.id):
				self._backend.licenseContract_updateObject(licenseContract)
			else:
				logger.info(u"LicenseContract %s does not exist, creating" % licenseContract)
				self._backend.licenseContract_insertObject(licenseContract)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licenseContract_getObjects(id = licenseContract.id)
				)
		return result
	
	def licenseContract_create(self, id, description=None, notes=None, partner=None, conclusionDate=None, notificationDate=None, expirationDate=None):
		hash = locals()
		del hash['self']
		return self.licenseContract_createObjects(LicenseContract.fromHash(hash))
	
	def licenseContract_delete(self, id):
		if id is None: id = []
		return self._backend.licenseContract_deleteObjects(
				self._backend.licenseContract_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_createObjects(self, softwareLicenses):
		result = []
		for softwareLicense in forceObjectClassList(softwareLicenses, SoftwareLicense):
			logger.info(u"Creating softwareLicense '%s'" % softwareLicense)
			self._backend.softwareLicense_insertObject(softwareLicense)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.softwareLicense_getObjects(id = softwareLicense.id)
				)
		return result
	
	def softwareLicense_updateObjects(self, softwareLicenses):
		result = []
		softwareLicenses = forceObjectClassList(softwareLicenses, SoftwareLicense)
		for softwareLicense in softwareLicenses:
			logger.info(u"Updating softwareLicense '%s'" % softwareLicense)
			if self.softwareLicense_getIdents(id = softwareLicense.id):
				self._backend.softwareLicense_updateObject(softwareLicense)
			else:
				logger.info(u"ProducSoftwareLicenset %s does not exist, creating" % softwareLicense)
				self._backend.softwareLicense_insertObject(softwareLicense)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.softwareLicense_getObjects(id = softwareLicense.id)
				)
		return result
	
	def softwareLicense_createRetail(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		hash = locals()
		del hash['self']
		return self.softwareLicense_createObjects(RetailSoftwareLicense.fromHash(hash))
	
	def softwareLicense_createOEM(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		hash = locals()
		del hash['self']
		return self.softwareLicense_createObjects(OEMSoftwareLicense.fromHash(hash))
	
	def softwareLicense_createVolume(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		hash = locals()
		del hash['self']
		return self.softwareLicense_createObjects(VolumeSoftwareLicense.fromHash(hash))
	
	def softwareLicense_createConcurrent(self, id, licenseContractId, maxInstallations=None, boundToHost=None, expirationDate=None):
		hash = locals()
		del hash['self']
		return self.softwareLicense_createObjects(ConcurrentSoftwareLicense.fromHash(hash))
	
	def softwareLicense_delete(self, id):
		if id is None: id = []
		return self._backend.softwareLicense_deleteObjects(
				self._backend.softwareLicense_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePool                                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_createObjects(self, licensePools):
		result = []
		for licensePool in forceObjectClassList(licensePools, LicensePool):
			logger.info(u"Creating licensePool '%s'" % licensePool)
			self._backend.licensePool_insertObject(licensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licensePool_getObjects(id = licensePool.id)
				)
		return result
	
	def licensePool_updateObjects(self, licensePools):
		result = []
		licensePools = forceObjectClassList(licensePools, LicensePool)
		for licensePool in licensePools:
			logger.info(u"Updating licensePool '%s'" % licensePool)
			if self.licensePool_getIdents(id = licensePool.id):
				self._backend.licensePool_updateObject(licensePool)
			else:
				logger.info(u"LicensePool %s does not exist, creating" % licensePool)
				self._backend.licensePool_insertObject(licensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licensePool_getObjects(id = licensePool.id)
				)
		return result
	
	def licensePool_create(self, id, description=None, productIds=None):
		hash = locals()
		del hash['self']
		return self.licensePool_createObjects(LicensePool.fromHash(hash))
	
	def licensePool_delete(self, id):
		if id is None: id = []
		return self._backend.licensePool_deleteObjects(
				self._backend.licensePool_getObjects(
					id = id))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_createObjects(self, softwareLicenseToLicensePools):
		result = []
		for softwareLicenseToLicensePool in forceObjectClassList(softwareLicenseToLicensePools, SoftwareLicenseToLicensePool):
			logger.info(u"Creating softwareLicenseToLicensePool %s" % softwareLicenseToLicensePool)
			self._backend.softwareLicenseToLicensePool_insertObject(softwareLicenseToLicensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.softwareLicenseToLicensePool_getObjects(
						softwareLicenseId = softwareLicenseToLicensePool.softwareLicenseId,
						licensePoolId     = softwareLicenseToLicensePool.licensePoolId
					)
				)
		return result
	
	def softwareLicenseToLicensePool_updateObjects(self, softwareLicenseToLicensePools):
		result = []
		softwareLicenseToLicensePools = forceObjectClassList(softwareLicenseToLicensePools, SoftwareLicenseToLicensePool)
		for softwareLicenseToLicensePool in softwareLicenseToLicensePools:
			logger.info(u"Updating %s" % softwareLicenseToLicensePool)
			if self.softwareLicenseToLicensePool_getIdents(
					softwareLicenseId = softwareLicenseToLicensePool.softwareLicenseId,
					licensePoolId     = softwareLicenseToLicensePool.licensePoolId):
				self._backend.softwareLicenseToLicensePool_updateObject(softwareLicenseToLicensePool)
			else:
				logger.info(u"SoftwareLicenseToLicensePool %s does not exist, creating" % softwareLicenseToLicensePool)
				self._backend.softwareLicenseToLicensePool_insertObject(softwareLicenseToLicensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.softwareLicenseToLicensePool_getObjects(
						softwareLicenseId = softwareLicenseToLicensePool.softwareLicenseId,
						licensePoolId     = softwareLicenseToLicensePool.licensePoolId
					)
				)
		return result
	
	def softwareLicenseToLicensePool_create(self, softwareLicenseId, licensePoolId, licenseKey=None):
		hash = locals()
		del hash['self']
		return self.softwareLicenseToLicensePool_createObjects(SoftwareLicenseToLicensePool.fromHash(hash))
	
	def softwareLicenseToLicensePool_delete(self, softwareLicenseId, licensePoolId):
		if not softwareLicenseId: softwareLicenseId  = []
		if not licensePoolId:     licensePoolId = []
		return self._backend.softwareLicenseToLicensePool_deleteObjects(
				self._backend.softwareLicenseToLicensePool_getObjects(
					softwareLicenseId = softwareLicenseId,
					licensePoolId     = licensePoolId))
		
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_createObjects(self, licenseOnClients):
		result = []
		for licenseOnClient in forceObjectClassList(licenseOnClients, LicenseOnClient):
			logger.info(u"Creating licenseOnClient %s" % licenseOnClient)
			self._backend.licenseOnClient_insertObject(licenseOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licenseOnClient_getObjects(
						softwareLicenseId = licenseOnClient.softwareLicenseId,
						licensePoolId     = licenseOnClient.licensePoolId,
						clientId          = licenseOnClient.clientId
					)
				)
		return result
	
	def licenseOnClient_updateObjects(self, licenseOnClients):
		result = []
		licenseOnClients = forceObjectClassList(licenseOnClients, LicenseOnClient)
		for licenseOnClient in licenseOnClients:
			logger.info(u"Updating licenseOnClient %s" % licenseOnClient)
			if self.licenseOnClient_getIdents(
					softwareLicenseId = licenseOnClient.softwareLicenseId,
					licensePoolId     = licenseOnClient.licensePoolId,
					clientId          = licenseOnClient.clientId):
				self._backend.licenseOnClient_updateObject(licenseOnClient)
			else:
				logger.info(u"LicenseOnClient %s does not exist, creating" % licenseOnClient)
				self._backend.licenseOnClient_insertObject(licenseOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.licenseOnClient_getObjects(
						softwareLicenseId = licenseOnClient.softwareLicenseId,
						licensePoolId     = licenseOnClient.licensePoolId,
						clientId          = licenseOnClient.clientId
					)
				)
		return result
	
	def licenseOnClient_create(self, softwareLicenseId, licensePoolId, clientId, licenseKey=None, notes=None):
		hash = locals()
		del hash['self']
		return self.licenseOnClient_createObjects(LicenseOnClient.fromHash(hash))
	
	def licenseOnClient_delete(self, softwareLicenseId, licensePoolId, clientId):
		if softwareLicenseId is None: softwareLicenseId  = []
		if licensePoolId is None:     licensePoolId = []
		if clientId is None:          clientId = []
		return self._backend.licenseOnClient_deleteObjects(
				self._backend.licenseOnClient_getObjects(
					softwareLicenseId = softwareLicenseId,
					licensePoolId     = licensePoolId,
					clientId          = clientId))
	
	def licenseOnClient_getOrCreateObject(self, clientId, licensePoolId = None, productId = None, windowsSoftwareId = None):
		clientId = forceHostId(clientId)
		if licensePoolId:
			licensePoolId = forceLicensePoolId(licensePoolId)
		elif productId or windowsSoftwareId:
			licensePoolIds = []
			if productId:
				productId = forceProductId(productId)
				licensePoolIds = self.licensePool_getIdents(productIds = productId, returnType = 'unicode')
			
			elif windowsSoftwareId:
				windowsSoftwareId = forceUnicode(windowsSoftwareId)
				
				auditSoftwares = self.auditSoftware_getObjects(windowsSoftwareId = windowsSoftwareId)
				for auditSoftware in auditSoftwares:
					auditSoftwareToLicensePools = self.auditSoftwareToLicensePool_getObjects(
									name         = auditSoftware.name,
									version      = auditSoftware.version,
									subVersion   = auditSoftware.subVersion,
									language     = auditSoftware.language,
									architecture = auditSoftware.architecture
					)
					if auditSoftwareToLicensePools:
						licensePoolIds.append(auditSoftwareToLicensePools[0].licensePoolId)
			
			if (len(licensePoolIds) < 1):
				raise LicenseConfigurationError(u"No license pool for product id '%s', windowsSoftwareId '%s' found" % (productId, windowsSoftwareId))
			elif (len(licensePoolIds) > 1):
				raise LicenseConfigurationError(u"Multiple license pools for product id '%s', windowsSoftwareId '%s' found: %s" \
						% (productId, windowsSoftwareId, licensePoolIds))
			licensePoolId = licensePoolIds[0]
		else:
			raise ValueError(u"You have to specify one of: licensePoolId, productId, windowsSoftwareId")
		
		if not self.licensePool_getIdents(id = licensePoolId):
			raise LicenseConfigurationError(u"License pool '%s' not found" % licensePoolId)
		
		# Test if a license is already used by the host
		licenseOnClient = None
		licenseOnClients = self._backend.licenseOnClient_getObjects(licensePoolId = licensePoolId, clientId = clientId)
		if licenseOnClients:
			logger.info(u"Using already assigned license '%s' for client '%s', license pool '%s'" \
					% (licenseOnClients[0].getSoftwareLicenseId(), clientId, licensePoolId))
			licenseOnClient = licenseOnClients[0]
		else:
			(softwareLicenseId, licenseKey) = self._getUsableSoftwareLicense(clientId, licensePoolId)
			if not licenseKey:
				logger.info(u"License available but no license key found")
			
			logger.info(u"Using software license id '%s', license key '%s' for host '%s' and license pool '%s'" \
						% (softwareLicenseId, licenseKey, clientId, licensePoolId))
			
			licenseOnClient = LicenseOnClient(
						softwareLicenseId = softwareLicenseId,
						licensePoolId     = licensePoolId,
						clientId          = clientId,
						licenseKey        = licenseKey,
						notes             = None)
			self.licenseOnClient_createObjects(licenseOnClient)
		return licenseOnClient
	
	def _getUsableSoftwareLicense(self, clientId, licensePoolId):
		softwareLicenseId = u''
		licenseKey = u''
		
		licenseOnClients = self._backend.licenseOnClient_getObjects(licensePoolId = licensePoolId, clientId = clientId)
		if licenseOnClients:
			# Already registered
			return (licenseOnClients[0].getSoftwareLicenseId(), licenseOnClients[0].getLicenseKey())
		
		softwareLicenseToLicensePools = self._backend.softwareLicenseToLicensePool_getObjects(licensePoolId = licensePoolId)
		if not softwareLicenseToLicensePools:
			raise LicenseMissingError(u"No license available")
		
		softwareLicenseIds = []
		for softwareLicenseToLicensePool in softwareLicenseToLicensePools:
			softwareLicenseIds.append(softwareLicenseToLicensePool.softwareLicenseId)
		
		softwareLicensesBoundToHost = self._backend.softwareLicense_getObjects(id = softwareLicenseIds, boundToHost = clientId)
		if softwareLicensesBoundToHost:
			logger.info(u"Using license bound to host: %s" % softwareLicensesBoundToHost[0])
			softwareLicenseId = softwareLicensesBoundToHost[0].getId()
		else:
			# Search an available license
			for softwareLicense in self._backend.softwareLicense_getObjects(id = softwareLicenseIds, boundToHost = [ None, '' ]):
				logger.debug(u"Checking license '%s', maxInstallations %d" \
					% (softwareLicense.getId(), softwareLicense.getMaxInstallations()))
				if (softwareLicense.getMaxInstallations() == 0):
					# 0 = infinite
					softwareLicenseId = softwareLicense.getId()
					break
				installations = len(self.licenseOnClient_getIdents(softwareLicenseId = softwareLicense.getId()))
				logger.debug(u"Installations registered: %d" % installations)
				if (installations < softwareLicense.getMaxInstallations()):
					softwareLicenseId = softwareLicense.getId()
					break
			
			if softwareLicenseId:
				logger.info(u"Found available license: %s" % softwareLicenseId)
			
		if not softwareLicenseId:
			raise LicenseMissingError(u"No license available")
		
		licenseKeys = []
		for softwareLicenseToLicensePool in softwareLicenseToLicensePools:
			if softwareLicenseToLicensePool.getLicenseKey():
				if (softwareLicenseToLicensePool.getSoftwareLicenseId() == softwareLicenseId):
					licenseKey = softwareLicenseToLicensePool.getLicenseKey()
					break
				logger.debug(u"Found license key: %s" % licenseKey)
				licenseKeys.append(softwareLicenseToLicensePool.getLicenseKey())
		
		if not licenseKey and licenseKeys:
			import random
			licenseKey = random.choice(licenseKeys)
			logger.info(u"Randomly choosing license key")
			
		logger.debug(u"Using license '%s', license key: %s" % (softwareLicenseId, licenseKey))
		return (softwareLicenseId, licenseKey)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_createObjects(self, auditSoftwares):
		result = []
		for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware):
			logger.info(u"Creating auditSoftware %s" % auditSoftware)
			self._backend.auditSoftware_insertObject(auditSoftware)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftware_getObjects(
						name           = auditSoftware.name,
						version        = auditSoftware.version,
						subVersion     = auditSoftware.subVersion,
						language       = auditSoftware.language,
						architecture   = auditSoftware.architecture
					)
				)
		return result
	
	def auditSoftware_updateObjects(self, auditSoftwares):
		result = []
		auditSoftwares = forceObjectClassList(auditSoftwares, AuditSoftware)
		for auditSoftware in auditSoftwares:
			logger.info(u"Updating %s" % auditSoftware)
			if self.auditSoftware_getIdents(
					name           = auditSoftware.name,
					version        = auditSoftware.version,
					subVersion     = auditSoftware.subVersion,
					language       = auditSoftware.language,
					architecture   = auditSoftware.architecture):
				self._backend.auditSoftware_updateObject(auditSoftware)
			else:
				logger.info(u"AuditSoftware %s does not exist, creating" % auditSoftware)
				self._backend.auditSoftware_insertObject(auditSoftware)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftware_getObjects(
						name           = auditSoftware.name,
						version        = auditSoftware.version,
						subVersion     = auditSoftware.subVersion,
						language       = auditSoftware.language,
						architecture   = auditSoftware.architecture
					)
				)
		return result
		
	
	def auditSoftware_create(self, name, version, subVersion, language, architecture, windowsSoftwareId=None, windowsDisplayName=None, windowsDisplayVersion=None, installSize=None):
		hash = locals()
		del hash['self']
		return self.auditSoftware_createObjects(AuditSoftware.fromHash(hash))
	
	def auditSoftware_delete(self, name, version, subVersion, language, architecture):
		if name is None:         name  = []
		if version is None:      version = []
		if subVersion is None:   subVersion = []
		if language is None:     language = []
		if architecture is None: architecture = []
		return self._backend.auditSoftware_deleteObjects(
				self._backend.auditSoftware_getObjects(
					name           = name,
					version        = version,
					subVersion     = subVersion,
					language       = language,
					architecture   = architecture))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_createObjects(self, auditSoftwareToLicensePools):
		result = []
		for auditSoftwareToLicensePool in forceObjectClassList(auditSoftwareToLicensePools, AuditSoftwareToLicensePool):
			logger.info(u"Creating %s" % auditSoftwareToLicensePool)
			self._backend.auditSoftwareToLicensePool_insertObject(auditSoftwareToLicensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftwareToLicensePool_getObjects(
						name           = auditSoftwareToLicensePool.name,
						version        = auditSoftwareToLicensePool.version,
						subVersion     = auditSoftwareToLicensePool.subVersion,
						language       = auditSoftwareToLicensePool.language,
						architecture   = auditSoftwareToLicensePool.architecture
					)
				)
		return result
	
	def auditSoftwareToLicensePool_updateObjects(self, auditSoftwareToLicensePools):
		result = []
		auditSoftwareToLicensePools = forceObjectClassList(auditSoftwareToLicensePools, AuditSoftwareToLicensePool)
		for auditSoftwareToLicensePool in auditSoftwareToLicensePools:
			logger.info(u"Creating %s" % auditSoftwareToLicensePool)
			if self.auditSoftwareToLicensePool_getIdents(
					name           = auditSoftwareToLicensePool.name,
					version        = auditSoftwareToLicensePool.version,
					subVersion     = auditSoftwareToLicensePool.subVersion,
					language       = auditSoftwareToLicensePool.language,
					architecture   = auditSoftwareToLicensePool.architecture):
				self._backend.auditSoftwareToLicensePool_updateObject(auditSoftwareToLicensePool)
			else:
				logger.info(u"AuditSoftwareToLicensePool %s does not exist, creating" % auditSoftwareToLicensePool)
				self._backend.auditSoftwareToLicensePool_insertObject(auditSoftwareToLicensePool)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftwareToLicensePool_getObjects(
						name           = auditSoftwareToLicensePool.name,
						version        = auditSoftwareToLicensePool.version,
						subVersion     = auditSoftwareToLicensePool.subVersion,
						language       = auditSoftwareToLicensePool.language,
						architecture   = auditSoftwareToLicensePool.architecture
					)
				)
		return result
	
	def auditSoftwareToLicensePool_create(self, name, version, subVersion, language, architecture, licensePoolId):
		hash = locals()
		del hash['self']
		return self.auditSoftwareToLicensePool_createObjects(AuditSoftwareToLicensePool.fromHash(hash))
	
	def auditSoftwareToLicensePool_delete(self, name, version, subVersion, language, architecture, licensePoolId):
		if name is None:          name  = []
		if version is None:       version = []
		if subVersion is None:    subVersion = []
		if language is None:      language = []
		if architecture is None:  architecture = []
		if licensePoolId is None: licensePoolId  = []
		return self._backend.auditSoftwareToLicensePool_deleteObjects(
				self._backend.auditSoftwareToLicensePool_getObjects(
					name           = name,
					version        = version,
					subVersion     = subVersion,
					language       = language,
					architecture   = architecture,
					licensePoolId  = licensePoolId))
		
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_createObjects(self, auditSoftwareOnClients):
		result = []
		for auditSoftwareOnClient in forceObjectClassList(auditSoftwareOnClients, AuditSoftwareOnClient):
			logger.info(u"Creating auditSoftwareOnClient %s" % auditSoftwareOnClient)
			self._backend.auditSoftwareOnClient_insertObject(auditSoftwareOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftwareOnClient_getObjects(
						name           = auditSoftwareOnClient.name,
						version        = auditSoftwareOnClient.version,
						subVersion     = auditSoftwareOnClient.subVersion,
						language       = auditSoftwareOnClient.language,
						architecture   = auditSoftwareOnClient.architecture,
						clientId       = auditSoftwareOnClient.clientId
					)
				)
		return result
	
	def auditSoftwareOnClient_updateObjects(self, auditSoftwareOnClients):
		result = []
		auditSoftwareOnClients = forceObjectClassList(auditSoftwareOnClients, AuditSoftwareOnClient)
		for auditSoftwareOnClient in auditSoftwareOnClients:
			logger.info(u"Updating auditSoftwareOnClient %s" % auditSoftwareOnClient)
			if self.auditSoftwareOnClient_getIdents(
					name           = auditSoftwareOnClient.name,
					version        = auditSoftwareOnClient.version,
					subVersion     = auditSoftwareOnClient.subVersion,
					language       = auditSoftwareOnClient.language,
					architecture   = auditSoftwareOnClient.architecture,
					clientId       = auditSoftwareOnClient.clientId):
				self._backend.auditSoftwareOnClient_updateObject(auditSoftwareOnClient)
			else:
				logger.info(u"AuditSoftwareOnClient %s does not exist, creating" % auditSoftwareOnClient)
				self._backend.auditSoftwareOnClient_insertObject(auditSoftwareOnClient)
			if self._options['returnObjectsOnUpdateAndCreate']:
				result.extend(
					self._backend.auditSoftwareOnClient_getObjects(
						name           = auditSoftwareOnClient.name,
						version        = auditSoftwareOnClient.version,
						subVersion     = auditSoftwareOnClient.subVersion,
						language       = auditSoftwareOnClient.language,
						architecture   = auditSoftwareOnClient.architecture,
						clientId       = auditSoftwareOnClient.clientId
					)
				)
		return result
		
	
	def auditSoftwareOnClient_create(self, name, version, subVersion, language, architecture, clientId, uninstallString=None, binaryName=None, firstseen=None, lastseen=None, state=None, usageFrequency=None, lastUsed=None, licenseKey=None):
		hash = locals()
		del hash['self']
		return self.auditSoftwareOnClient_createObjects(AuditSoftwareOnClient.fromHash(hash))
	
	def auditSoftwareOnClient_delete(self, name, version, subVersion, language, architecture, clientId):
		if name is None:         name  = []
		if version is None:      version = []
		if subVersion is None:   subVersion = []
		if language is None:     language = []
		if architecture is None: architecture = []
		if clientId is None:     clientId = []
		return self._backend.auditSoftwareOnClient_deleteObjects(
				self._backend.auditSoftwareOnClient_getObjects(
					name           = name,
					version        = version,
					subVersion     = subVersion,
					language       = language,
					architecture   = architecture,
					clientId       = clientId))
	
	def auditSoftwareOnClient_setObsolete(self, clientId):
		if clientId is None: clientId  = []
		clientId = forceHostIdList(clientId)
		self._backend.auditSoftwareOnClient_deleteObjects(
			self._backend.auditSoftwareOnClient_getObjects(
				clientId = clientId))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardware_createObjects(self, auditHardwares):
		result = []
		auditHardwares = forceObjectClassList(auditHardwares, AuditHardware)
		for auditHardware in auditHardwares:
			logger.info(u"Creating auditHardware %s" % auditHardware)
			self.auditHardware_insertObject(auditHardware)
		return result
	
	def auditHardware_updateObjects(self, auditHardwares):
		result = []
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			logger.info(u"Updating auditHardware %s" % auditHardware)
			# You can't update auditHardwares, because the ident contains all attributes
			self.auditHardware_insertObject(auditHardware)
		return result
	
	def auditHardware_create(self, hardwareClass, **kwargs):
		hash = locals()
		del hash['self']
		return self.auditHardware_createObjects(AuditHardware.fromHash(hash))
	
	def auditHardware_delete(self, hardwareClass, **kwargs):
		if hardwareClass is None: hardwareClass  = []
		for key in kwargs.keys():
			if kwargs[key] is None: kwargs[key] = []
		
		return self._backend.auditHardware_deleteObjects(
				self._backend.auditHardware_getObjects(
					hardwareClass  = hardwareClass,
					**kwargs ))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		auditHardwareOnHost.setLastseen(timestamp())
		auditHardwareOnHost.setState(1)
		self._backend.auditHardwareOnHost_updateObject(auditHardwareOnHost)
		
	def auditHardwareOnHost_createObjects(self, auditHardwareOnHosts):
		result = []
		for auditHardwareOnHost in forceObjectClassList(auditHardwareOnHosts, AuditHardwareOnHost):
			logger.info(u"Creating auditHardwareOnHost %s" % auditHardwareOnHost)
			self._backend.auditHardwareOnHost_insertObject(auditHardwareOnHost)
		return result
	
	def auditHardwareOnHost_updateObjects(self, auditHardwareOnHosts):
		result = []
		auditHardwareOnHosts = forceObjectClassList(auditHardwareOnHosts, AuditHardwareOnHost)
		for auditHardwareOnHost in auditHardwareOnHosts:
			filter = {}
			for (attribute, value) in auditHardwareOnHost.toHash().items():
				if attribute in ('firstseen', 'lastseen', 'state'):
					continue
				if value is None:
					filter[attribute] = [ None ]
				else:
					filter[attribute] = value
			if self.auditHardwareOnHost_getObjects(attributes = ['hostId'], **filter):
				self.auditHardwareOnHost_updateObject(auditHardwareOnHost)
			else:
				logger.info(u"AuditHardwareOnHost %s does not exist, creating" % auditHardwareOnHost)
				self._backend.auditHardwareOnHost_insertObject(auditHardwareOnHost)
		return result
	
	def auditHardwareOnHost_create(self, hostId, hardwareClass, firstseen=None, lastseen=None, state=None, **kwargs):
		hash = locals()
		del hash['self']
		return self.auditHardwareOnHost_createObjects(AuditHardwareOnHost.fromHash(hash))
	
	def auditHardwareOnHost_delete(self, hostId, hardwareClass, firstseen=None, lastseen=None, state=None, **kwargs):
		if hostId is None:        hostId  = []
		if hardwareClass is None: hardwareClass  = []
		if firstseen is None:     firstseen  = []
		if lastseen is None:      lastseen  = []
		if state is None:         state  = []
		for key in kwargs.keys():
			if kwargs[key] is None: kwargs[key] = []
		
		return self._backend.auditHardwareOnHost_deleteObjects(
				self._backend.auditHardwareOnHost_getObjects(
					hostId         = hostId,
					hardwareClass  = hardwareClass,
					firstseen      = firstseen,
					lastseen       = lastseen,
					state          = state,
					**kwargs ))
	
	def auditHardwareOnHost_setObsolete(self, hostId):
		if hostId is None: hostId  = []
		hostId = forceHostIdList(hostId)
		auditHardwareOnHosts = self.auditHardwareOnHost_getObjects(hostId = hostId, state = 1)
		for i in range(len(auditHardwareOnHosts)):
			auditHardwareOnHosts[i].setState(0)
			self._backend.auditHardwareOnHost_updateObject(auditHardwareOnHosts[i])
	
	
	
	
	
	
	

