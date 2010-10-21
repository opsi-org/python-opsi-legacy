#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - JSONRPC   =
   = = = = = = = = = = = = = = = = = = =
   
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

__version__ = '4.0.1'

# Imports
import base64, new, stat, time, threading, zlib, threading
from Queue import Queue, Empty, Full
from twisted.conch.ssh import keys
from sys import version_info
if (version_info >= (2,6)):
	import json
else:
	import simplejson as json

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from Backend import *
from OPSI import Object
from OPSI.Util import serialize, deserialize
from OPSI.Util.HTTP import urlsplit, getSharedConnectionPool

# Get logger instance
logger = Logger()

class JSONRPC(DeferredCall):
	def __init__(self, jsonrpcBackend, baseUrl, method, params=[], retry = True, callback = None):
		DeferredCall.__init__(self, callback = callback)
		self.jsonrpcBackend = jsonrpcBackend
		self.baseUrl = baseUrl
		self.id = self.jsonrpcBackend._getRpcId()
		self.method = method
		self.params = params
		self.retry = retry
		
	def execute(self):
		self.process()
	
	def getRpc(self):
		if self.jsonrpcBackend.isLegacyOpsi():
			for i in range(len(self.params)):
				if (self.params[i] == '__UNDEF__'):
					self.params[i] = None
		return { "id": self.id, "method": self.method, "params": serialize(self.params) }
	
	def processResult(self, result):
		try:
			if result.get('error'):
				error = result.get('error')
				# Error occurred
				if type(error) is dict and error.get('message'):
					message = error['message']
					exception = Exception(message)
					try:
						exceptionClass = eval(error.get('class', 'Exception'))
						index = message.find(':')
						if (index != -1) and (len(message) > index):
							message = message[index+1:].lstrip()
						exception = exceptionClass(u'%s (error on server)' % message)
					except:
						pass
					raise exception
				raise Exception(u'%s (error on server)' % error)
			self.result = deserialize(result.get('result'))
		except Exception, e:
			self.error = e
		self._gotResult()
		
	def process(self):
		try:
			logger.debug(u"Executing jsonrpc method '%s' on host %s" % (self.method, self.jsonrpcBackend._host))
			
			rpc = json.dumps(self.getRpc())
			logger.debug2(u"jsonrpc: %s" % rpc)
			response = self.jsonrpcBackend._request(baseUrl = self.baseUrl, data = rpc, retry = self.retry)
			self.processResult(json.loads(response))
		except Exception, e:
			if not self.method in ('backend_exit', 'exit'):
				logger.logException(e, LOG_INFO)
				self.error = e
			self._gotResult()

class JSONRPCThread(JSONRPC, threading.Thread):
	def __init__(self, jsonrpcBackend, baseUrl, method, params=[], retry = True, callback = None):
		threading.Thread.__init__(self)
		JSONRPC.__init__(self, jsonrpcBackend = jsonrpcBackend, baseUrl = baseUrl, method = method, params = params, retry = retry, callback = callback)
	
	def execute(self):
		self.start()
		return self.waitForResult()
	
	def run(self):
		self.process()
	
class RpcQueue(threading.Thread):
	def __init__(self, jsonrpcBackend, size, poll = 0.01):
		threading.Thread.__init__(self)
		self.jsonrpcBackend = jsonrpcBackend
		self.size = size
		self.queue = Queue(size)
		self.poll = poll
		self.stopped = False
		self.jsonrpcs = {}
		self.idle = threading.Event()
		
	def add(self, jsonrpc):
		logger.debug(u'Adding jsonrpc %s to queue (current queue size: %d)' % (jsonrpc, self.queue.qsize()))
		self.queue.put(jsonrpc, block = True)
		logger.debug2(u'Added jsonrpc %s to queue' % jsonrpc)
		
	def stop(self):
		self.stopped = True
		
	def run(self):
		logger.debug(u"RpcQueue started")
		self.idle.set()
		while not self.stopped or not self.queue.empty():
			self.idle.wait()
			jsonrpcs = []
			while not self.queue.empty():
				self.idle.clear()
				try:
					jsonrpc = self.queue.get(block = False)
					if jsonrpc:
						logger.debug(u'Got jsonrpc %s from queue' % jsonrpc)
						jsonrpcs.append(jsonrpc)
						if (len(jsonrpcs) >= self.size):
							break
				except Empty:
					break
			if jsonrpcs:
				self.process(jsonrpcs = jsonrpcs)
			time.sleep(self.poll)
		logger.debug(u"RpcQueue stopped (empty: %s, stopped: %s)" % (self.queue.empty(), self.stopped))
		
	def process(self, jsonrpcs):
		self.jsonrpcs = {}
		for jsonrpc in forceList(jsonrpcs):
			self.jsonrpcs[jsonrpc.id] = jsonrpc
		if not self.jsonrpcs:
			return
		logger.info("Executing bunched jsonrpcs: %s" % self.jsonrpcs)
		isExit = False
		try:
			retry = False
			baseUrl = None
			rpc = []
			for jsonrpc in self.jsonrpcs.values():
				if jsonrpc.method in ('backend_exit', 'exit'):
					isExit = True
				else:
					isExit = False
				if jsonrpc.retry:
					retry = True
				if not baseUrl:
					baseUrl = jsonrpc.baseUrl
				elif (baseUrl != jsonrpc.baseUrl):
					raise Exception(u"Can't execute jsonrpcs with different base urls at once: (%s != %s)" % (baseUrl, jsonrpc.baseUrl))
				rpc.append(jsonrpc.getRpc())
			rpc = json.dumps(rpc)
			logger.debug2(u"jsonrpc: %s" % rpc)
			
			response = self.jsonrpcBackend._request(baseUrl = baseUrl, data = rpc, retry = retry)
			logger.debug(u"Got response from host %s" % self.jsonrpcBackend._host)
			try:
				response = forceList(json.loads(response))
			except Exception, e:
				raise Exception(u"Failed to json decode response %s: %s" % (response, e))
			
			for resp in response:
				try:
					id = resp['id']
				except Exception, e:
					raise Exception(u"Failed to get id from: %s (%s): %s" % (resp, response, e))
				try:
					jsonrpc = self.jsonrpcs[id]
				except Exception, e:
					raise Exception(u"Failed to get jsonrpc with id %s: %s" % (id, e))
				try:
					jsonrpc.processResult(resp)
				except Exception, e:
					raise Exception(u"Failed to process response %s with jsonrpc %s: %s" % (resp, jsonrpc, e))
		except Exception, e:
			if not isExit:
				logger.logException(e)
			for jsonrpc in self.jsonrpcs.values():
				jsonrpc.error = e
				jsonrpc._gotResult()
		self.jsonrpcs = {}
		self.idle.set()
	
# ======================================================================================================
# =                                   CLASS JSONRPCBACKEND                                             =
# ======================================================================================================
class JSONRPCBackend(Backend):
	
	def __init__(self, address, **kwargs):
		self._name = 'jsonrpc'
		
		Backend.__init__(self, **kwargs)
		
		self._application         = 'opsi jsonrpc module version %s' % __version__
		self._sessionId           = None
		self._deflate             = False
		self._connectOnInit       = True
		self._connected           = False
		self._retryTime           = 5
		self._defaultHttpPort     = 4444
		self._defaultHttpsPort    = 4447
		self._host                = None
		self._port                = None
		self._baseUrl             = u'/rpc'
		self._protocol            = 'https'
		self._socketTimeout       = None
		self._connectTimeout      = 30
		self._connectionPoolSize  = 1
		self._legacyOpsi          = False
		self._interface           = None
		self._rpcId               = 0
		self._rpcIdLock           = threading.Lock()
		self._async               = False
		self._rpcQueue            = None
		self._rpcQueuePollingTime = 0.01
		self._rpcQueueSize        = 10
		
		retry = True
		for (option, value) in kwargs.items():
			option = option.lower()
			if option in ('application',):
				self._application = str(value)
			if option in ('sessionid',):
				self._sessionId = str(value)
			if option in ('deflate',):
				self._deflate = bool(value)
			if option in ('connectoninit',):
				self._connectOnInit = bool(value)
			if option in ('connecttimeout',) and not value is None:
				self._connectTimeout = forceInt(value)
			if option in ('connectionpoolsize',) and not value is None:
				self._connectionPoolSize = forceInt(value)
			if option in ('timeout', 'sockettimeout') and not value is None:
				self._socketTimeout = forceInt(value)
			if option in ('retry',):
				retry = bool(value)
			if option in ('retrytime',):
				self._retryTime = forceInt(value)
			if option in ('rpcqueuepollingtime',):
				self._rpcQueuePollingTime = forceFloat(value)
			if option in ('rpcqueuesize',):
				self._rpcQueueSize = forceInt(value)
		
		if not retry:
			self._retryTime = 0
		
		if self._password:
			logger.addConfidentialString(self._password)
		
		self._processAddress(address)
		self._connectionPool = getSharedConnectionPool(
			scheme         = self._protocol,
			host           = self._host,
			port           = self._port,
			socketTimeout  = self._socketTimeout,
			connectTimeout = self._connectTimeout,
			retryTime      = self._retryTime,
			maxsize        = self._connectionPoolSize,
			block          = True
		)
		
		if self._connectOnInit:
			self.connect()
	
	def stopRpcQueue(self):
		if self._rpcQueue:
			self._rpcQueue.stop()
			self._rpcQueue.join(20)
		
	def startRpcQueue(self):
		if not self._rpcQueue or not self._rpcQueue.is_alive():
			self._rpcQueue = RpcQueue(jsonrpcBackend = self, size = self._rpcQueueSize, poll = self._rpcQueuePollingTime)
			self._rpcQueue.start()
		
	def __del__(self):
		self.stopRpcQueue()
		if self._connectionPool:
			self._connectionPool.free()
		
	def backend_exit(self):
		res = None
		if self._connected:
			try:
				if self._legacyOpsi:
					res = self._jsonRPC('exit', retry = False)
				else:
					res = self._jsonRPC('backend_exit', retry = False)
			except:
				pass
		if self._rpcQueue:
			self._rpcQueue.stop()
		return res
		
	def setAsync(self, async):
		if not self._connected:
			raise Exception(u'Not connected')
		
		if async:
			if self.isLegacyOpsi():
				logger.error(u"Refusing to set async because we are connected to legacy opsi service")
				return
			self.startRpcQueue()
			self._async = True
		else:
			self._async = False
			self.stopRpcQueue()
		
	def setDeflate(self, deflate):
		if not self._connected:
			raise Exception(u'Not connected')
		
		deflate = forceBool(deflate)
		if deflate and self.isLegacyOpsi():
			logger.error(u"Refusing to set deflate because we are connected to legacy opsi service")
			return
		self._deflate = deflate
	
	def isConnected(self):
		return self._connected
	
	def connect(self):
		async = self._async
		self._async = False
		try:
			modules = None
			mysqlBackend = False
			try:
				self._interface = self._jsonRPC(u'backend_getInterface', retry = False)
				if (self._application.find('opsiclientd') != -1):
					try:
						modules = self._jsonRPC(u'backend_info', retry = False).get('modules', None)
						if modules:
							logger.confidential(u"Modules: %s" % modules)
						else:
							modules = {'customer': None}
						for m in self._interface:
							if (m.get('name') == 'dispatcher_getConfig'):
								for entry in self._jsonRPC(u'dispatcher_getConfig', retry=False):
									for bn in entry[1]:
										if (bn.lower().find("sql") != -1) and (len(entry[0]) <= 4) and (entry[0].find('*') != -1):
											mysqlBackend = True
								break
					except Exception, e:
						logger.info(e)
			except (OpsiAuthenticationError, OpsiTimeoutError):
				raise
			except Exception, e:
				logger.debug(u"backend_getInterface failed: %s, trying getPossibleMethods_listOfHashes" % e)
				self._interface = self._jsonRPC(u'getPossibleMethods_listOfHashes', retry = False)
				logger.info(u"Legacy opsi")
				self._legacyOpsi = True
				self._deflate = False
				self._jsonRPC(u'authenticated', retry = False)
			if self._legacyOpsi:
				self._createInstanceMethods34()
			else:
				self._createInstanceMethods(modules, mysqlBackend)
			self._connected = True
			logger.info(u"%s: Connected to service" % self)
		finally:
			self._async = async
		
	def _getRpcId(self):
		self._rpcIdLock.acquire()
		try:
			self._rpcId += 1
			if (self._rpcId > 100000):
				self._rpcId = 1
		finally:
			self._rpcIdLock.release()
		return self._rpcId
	
	def _processAddress(self, address):
		self._protocol = 'https'
		(scheme, host, port, baseurl, username, password) = urlsplit(address)
		if scheme:
			if not scheme in ('http', 'https'):
				raise Exception(u"Protocol %s not supported" % scheme)
			self._protocol = scheme
		self._host = host
		if port:
			self._port = port
		elif (self._protocol == 'https'):
			self._port = self._defaultHttpsPort
		else:
			self._port = self._defaultHttpPort
		if baseurl and (baseurl != '/'):
			self._baseUrl = baseurl
		
	def isOpsi35(self):
		return not self._legacyOpsi
	
	def isOpsi4(self):
		return not self._legacyOpsi
	
	def isLegacyOpsi(self):
		return self._legacyOpsi
	
	def jsonrpc_getSessionId(self):
		return self._sessionId
	
	def _createInstanceMethods34(self):
		for method in self._interface:
			# Create instance method
			params = ['self']
			params.extend( method.get('params', []) )
			paramsWithDefaults = list(params)
			for i in range(len(params)):
				if params[i].startswith('*'):
					params[i] = params[i][1:]
					paramsWithDefaults[i] = params[i] + '="__UNDEF__"'
			
			logger.debug2("Creating instance method '%s'" % method['name'])
			
			
			if (len(params) == 2):
				logger.debug2('def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._jsonRPC(method = "%s", params = [%s])'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._jsonRPC(method = "%s", params = [%s])'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:]))
			else:
				logger.debug2('def %s(%s): return self._jsonRPC(method = "%s", params = [%s])'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s): return self._jsonRPC(method = "%s", params = [%s])'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:]))
			
			setattr(self.__class__, method['name'], new.instancemethod(eval(method['name']), None, self.__class__))
		
	def _createInstanceMethods(self, modules=None, mysqlBackend=False):
		licenseManagementModule = True
		if modules:
			licenseManagementModule = False
			if not modules.get('customer'):
				logger.notice(u"Disabling mysql backend and license management module: no customer in modules file")
				if mysqlBackend:
					raise Exception(u"MySQL backend in use but not licensed")
				
			elif not modules.get('valid'):
				logger.notice(u"Disabling mysql backend and license management module: modules file invalid")
				if mysqlBackend:
					raise Exception(u"MySQL backend in use but not licensed")
				
			elif (modules.get('expires', '') != 'never') and (time.mktime(time.strptime(modules.get('expires', '2000-01-01'), "%Y-%m-%d")) - time.time() <= 0):
				logger.notice(u"Disabling mysql backend and license management module: modules file expired")
				if mysqlBackend:
					raise Exception(u"MySQL backend in use but not licensed")
			else:
				logger.info(u"Verifying modules file signature")
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
				if not bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ])):
					logger.error(u"Disabling mysql backend and license management module: modules file invalid")
					if mysqlBackend:
						raise Exception(u"MySQL backend in use but not licensed")
				else:
					logger.notice(u"Modules file signature verified (customer: %s)" % modules.get('customer'))
					
					if modules.get('license_management'):
						licenseManagementModule = True
					
					if mysqlBackend and not modules.get('mysql_backend'):
						raise Exception(u"MySQL backend in use but not licensed")
					
		
		for method in self._interface:
			try:
				methodName = method['name']
				args       = method['args']
				varargs    = method['varargs']
				keywords   = method['keywords']
				defaults   = method['defaults']
				
				if methodName in ('backend_exit', 'backend_getInterface'):
					continue
				
				argString = u''
				callString = u''
				for i in range(len(args)):
					if (args[i] == 'self'):
						continue
					if (argString):	 argString  += u', '
					if (callString): callString += u', '
					argString  += args[i]
					callString += args[i]
					if type(defaults) in (tuple, list) and (len(defaults) + i >= len(args)):
						default = defaults[len(defaults)-len(args)+i]
						if type(default) is str:
							default = u"'%s'" % default
						elif type(default) is unicode:
							default = u"u'%s'" % default
						argString += u'=%s' % unicode(default)
				if varargs:
					for vararg in varargs:
						if (argString):	 argString  += u', '
						if (callString): callString += u', '
						argString  += u'*%s' % vararg
						callString += vararg
				if keywords:
					if (argString):	 argString  += u', '
					if (callString): callString += u', '
					argString  += u'**%s' % keywords
					callString += keywords
					
				logger.debug2(u"Arg string is: %s" % argString)
				logger.debug2(u"Call string is: %s" % callString)
				# This would result in not overwriting Backend methods like log_read, log_write, ...
				#if getattr(self, methodName, None) is None:
				if not licenseManagementModule and (methodName.find("license") != -1):
					exec(u'def %s(self, %s): return' % (methodName, argString))
				else:
					exec(u'def %s(self, %s): return self._jsonRPC("%s", [%s])' % (methodName, argString, methodName, callString))
				setattr(self, methodName, new.instancemethod(eval(methodName), self, self.__class__))
			except Exception, e:
				logger.critical(u"Failed to create instance method '%s': %s" % (method, e))
	
	def _jsonRPC(self, method, params=[], retry=True):
		if self._async:
			self.startRpcQueue()
			jsonrpc = JSONRPC(jsonrpcBackend = self, baseUrl = self._baseUrl, method = method, params = params, retry = retry)
			self._rpcQueue.add(jsonrpc)
			return jsonrpc
		else:
			jsonrpc = JSONRPCThread(jsonrpcBackend = self, baseUrl = self._baseUrl, method = method, params = params, retry = retry)
			return jsonrpc.execute()
	
	def _request(self, baseUrl, data, retry = True):
		headers = {
			'user-agent': self._application,
			'Accept': 'application/json-rpc, text/plain'
		}
		if type(data) is types.StringType:
			data = unicode(data, 'utf-8')
		data = data.encode('utf-8')
		
		logger.debug2(u"Request to host '%s', baseUrl: %s, query '%s'" % (self._host, baseUrl, data))
		
		if self._deflate:
			logger.debug2(u"Compressing data")
			headers['Accept'] += ', gzip-application/json-rpc'
			headers['content-type'] = 'gzip-application/json-rpc'
			level = 1
			data = zlib.compress(data, level)
		else:
			headers['content-type'] = 'application/json-rpc'
		
		headers['content-length'] = len(data)
		
		headers['Authorization'] = 'Basic '+ base64.encodestring((self._username + u':' + self._password).encode('latin-1')).strip()
		if self._sessionId:
			headers['Cookie'] = self._sessionId
		
		response = self._connectionPool.urlopen(method = 'POST', url = baseUrl, body = data, headers = headers, retry = retry)
		
		# Get cookie from header
		cookie = response.getheader('set-cookie', None)
		if cookie:
			# Store sessionId cookie
			sessionId = cookie.split(';')[0].strip()
			if (sessionId != self._sessionId):
				self._sessionId = sessionId
		
		contentType = response.getheader('content-type', '')
		logger.debug(u"Content-Type: %s" % contentType)
		
		response = response.data
		if contentType.lower().startswith('gzip'):
			logger.debug(u"Expecting compressed data from server")
			response = zlib.decompress(response)
		logger.debug2(response)
		return response
	
	def getInterface(self):
		return self.backend_getInterface()
		
	def backend_getInterface(self):
		return self._interface
	
	
if (__name__ == '__main__'):
	import threading
	
	#logger.setConsoleLevel(LOG_ERROR)
	logger.setConsoleLevel(LOG_DEBUG2)
	logger.setConsoleColor(True)
	
	
	#be = JSONRPCBackend(address = '192.168.1.14', username = 'stb-40-wks-120.uib.local', password = '8ca221eee05e574c58fcc1d3d99de17c')
	be = JSONRPCBackend(address = '192.168.1.14', username = 'someone', password = '123')
	print be.authenticated()
	
	def callback(jsonrpc):
		print jsonrpc.result
	
	#class Thread(threading.Thread):
	#	def __init__(self, be):
	#		threading.Thread.__init__(self)
	#		self.be = be
	#	
	#	def run(self):
	#		for i in range(5):
	#			be.authenticated().setCallback(callback)
	#			time.sleep(0.3)
	#
	#be = JSONRPCBackend(address = '192.168.1.14', username = 'stb-40-wks-120.uib.local', password = '8ca221eee05e574c58fcc1d3d99de17c', deflate = True, connectionPoolSize = 30)
	
	#be.setAsync(True)
	#
	#threads = []
	#for i in range(20):
	#	t = Thread(be)
	#	threads.append(t)
	#	t.start()
	#
	#for t in threads:
	#	t.join()
	#while True:
	#print be.authenticated()
	#print be.group_getIdents()
	#print be.host_getIdents()
	#	time.sleep(2)
	
	
	#
	#be.setAsync(True)
	#
	##jsonrpc1 = JSONRPC(jsonrpcBackend = be, baseUrl = be._baseUrl, method = 'authenticated', params = [], retry = False)
	#be.authenticated().setCallback(callback)
	##jsonrpc2 = JSONRPC(jsonrpcBackend = be, baseUrl = be._baseUrl, method = 'group_getIdents', params = [], retry = False)
	#be.group_getIdents().setCallback(callback)
	##jsonrpc3 = JSONRPC(jsonrpcBackend = be, baseUrl = be._baseUrl, method = 'host_getIdents', params = [], retry = False)
	#be.host_getIdents().setCallback(callback)
	#be.host_getIdents().setCallback(callback)
	#be.host_getIdents().setCallback(callback)
	#be.host_getIdents().setCallback(callback)
	#be.host_getIdents().setCallback(callback)
	#
	#be.setAsync(False)
	#print "===", be.host_getIdents()
	
	be.backend_exit()
	
	#mult = MultiJSONRPC(be, [jsonrpc1, jsonrpc2, jsonrpc3])
	#mult.process()
	#
	#print "WAIT"
	#time.sleep(5)
	
	
	
















