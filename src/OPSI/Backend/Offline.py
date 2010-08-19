#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Offline     =
   = = = = = = = = = = = = = = = = = = = =
   
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

__version__ = '0.2.3'

# Imports
import time, types, new
from sys import version_info
if (version_info >= (2,6)):
	import json
else:
	import simplejson as json

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Logger import *
from OPSI.Util import ProgressSubjectProxy

# Get logger instance
logger = Logger()



# ======================================================================================================
# =                                   CLASS OFFLINEBACKEND                                             =
# ======================================================================================================
class OfflineBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		
		self.__backendManager = backendManager
		self.__possibleMethods = None
		self.__localOnly = False
		self.__remoteOnly = False
		self.__cachedExecutions = []
		
		# Default values
		self.__remoteBackend  = None
		self.__cacheBackend = None
		self.__workBackend = None
		self.__cleanupBackend = False
		self.__privileges = 'CLIENT'
		self._defaultDomain = None
		
		self.__storageDir = ''
		self.__cachedExecutionsFile = ''
		self.__hwauditConfFile = ''
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'remotebackend'):        self.__remoteBackend = value
			elif (option.lower() == 'cachebackend'):         self.__cacheBackend = value
			elif (option.lower() == 'workbackend'):          self.__workBackend = value
			elif (option.lower() == 'cleanupbackend'):       self.__cleanupBackend = bool(value)
			elif (option.lower() == 'privileges'):           self.__privileges = value
			elif (option.lower() == 'storagedir'):           self.__storageDir = value
			else:
				logger.warning("Unknown argument '%s' passed to CacheBackend constructor" % option)
		
		self.__cachedExecutionsFile = os.path.join(self.__storageDir, 'cached_exec')
		self.__hwauditConfFile = os.path.join(self.__storageDir, 'hwaudit.conf')
		
		if not self.__remoteBackend or not self.__cacheBackend or not self.__workBackend:
			raise Exception("RemoteBackend, cacheBackend and workingBackend needed")
		
		self.__cacheReplicator = DataBackendReplicator(
					readBackend   = self.__remoteBackend,
					writeBackend  = self.__cacheBackend,
					cleanupFirst  = self.__cleanupBackend,
					privileges    = self.__privileges )
		
		self.__workReplicator = DataBackendReplicator(
					readBackend  = self.__cacheBackend,
					writeBackend = self.__workBackend,
					cleanupFirst = self.__cleanupBackend,
					privileges   = self.__privileges )
		
		self._createInstanceMethods()
		self._readCachedExecutionsFile()
	
	def _createInstanceMethods(self):
		logger.debug("OfflineBackend: Creating instance methods")
		self.__possibleMethods = []
		for method in self.getPossibleMethods_listOfHashes():
			if (method['name'].lower() == "getpossiblemethods_listofhashes"):
				# Method already implemented
				continue
			
			# Create instance method
			params = ['self']
			params.extend( method.get('params', []) )
			paramsWithDefaults = list(params)
			for i in range(len(params)):
				if params[i].startswith('*'):
					params[i] = params[i][1:]
					paramsWithDefaults[i] = params[i] + '="__UNDEF__"'
			
			logger.debug2("OfflineBackend: Creating instance method '%s'" % method['name'])
			
			if (len(params) == 2):
				logger.debug2('def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._exec(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._exec(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:]))
			else:
				logger.debug2('def %s(%s): return self._exec(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s): return self._exec(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:]))
			
			setattr(self.__class__, method['name'], new.instancemethod(eval(method['name']), None, self.__class__))
		
	def _readCachedExecutionsFile(self):
		if not self.__cachedExecutionsFile:
			logger.warning("Cached executions file not given")
			return
		logger.notice("Reading cached executions from file '%s'" % self.__cachedExecutionsFile)
		if not os.path.exists(self.__cachedExecutionsFile):
			logger.warning("File '%s' does not exist" % self.__cachedExecutionsFile)
			return
		self.__cachedExecutions = []
		f = open(self.__cachedExecutionsFile)
		for line in f.readlines():
			self.__cachedExecutions.append(json.loads(line.strip()))
		f.close()
		
	def _writeCachedExecutionsFile(self, lastOnly=False):
		if not self.__cachedExecutionsFile:
			logger.warning("Cached executions file not given")
			return
		logger.notice("Writing cached executions to file '%s'" % self.__cachedExecutionsFile)
		f = None
		ces = []
		if lastOnly:
			f = open(self.__cachedExecutionsFile, 'a')
			if (len(self.__cachedExecutions) > 0):
				ces = [ self.__cachedExecutions[-1] ]
		else:
			f = open(self.__cachedExecutionsFile, 'w')
			ces = self.__cachedExecutions
		for ce in ces:
			f.write(json.dumps(ce) + '\n')
		f.close()
		
	def _addCachedExecution(self, method, params=[]):
		self.__cachedExecutions.append({'method': method, 'params': params})
		self._writeCachedExecutionsFile(lastOnly=True)
	
	def _getCachedExecutions(self):
		return self.__cachedExecutions
	
	def _buildCache(self, serverIds=[], depotIds=[], clientIds=[], groupIds = [], productIds=[], currentProgressObserver=None, overallProgressObserver=None):
		
		class BuildCacheProgress(ProgressSubjectProxy):
			def __init__(self):
				ProgressSubjectProxy.__init__(self, id='build_cache_overall')
				self._pass = 1
			
			def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
				self._end = subject.getEnd() * 2
				self.setState(state * self._pass)
		overallProgress = BuildCacheProgress()
		
		if overallProgressObserver: overallProgress.attachObserver(overallProgressObserver)
		try:
			self.__cacheReplicator.getOverallProgressSubject().attachObserver(overallProgress)
			if currentProgressObserver: self.__cacheReplicator.getCurrentProgressSubject().attachObserver(currentProgressObserver)
			try:
				self.__cacheReplicator.replicate(serverIds = serverIds, depotIds = depotIds, clientIds = clientIds, groupIds = groupIds, productIds = productIds)
			finally:
				self.__cacheReplicator.getOverallProgressSubject().detachObserver(overallProgress)
				if currentProgressObserver: self.__cacheReplicator.getCurrentProgressSubject().detachObserver(currentProgressObserver)
			
			overallProgress._pass = 2
			
			self.__workReplicator.getOverallProgressSubject().attachObserver(overallProgress)
			if currentProgressObserver: self.__workReplicator.getCurrentProgressSubject().attachObserver(currentProgressObserver)
			try:
				self.__workReplicator.replicate(serverIds = serverIds, depotIds = depotIds, clientIds = clientIds, groupIds = groupIds, productIds = productIds)
			finally:
				self.__workReplicator.getOverallProgressSubject().detachObserver(overallProgress)
				if currentProgressObserver: self.__workReplicator.getCurrentProgressSubject().detachObserver(currentProgressObserver)
			
			logger.info("Writing hwaudit conf file '%s'" % self.__hwauditConfFile)
			hwAuditConf = json.dumps(self.__remoteBackend.getOpsiHWAuditConf())
			f = open(self.__hwauditConfFile, 'wb')
			f.write(hwAuditConf)
			f.close()
		finally:
			if overallProgressObserver: overallProgress.detachObserver(overallProgressObserver)
		
	def _writebackCache(self, currentProgressObserver = None):
		if not self.__cachedExecutions:
			logger.debug("No cached executions to write back")
			return
		
		currentProgressSubject = ProgressSubject(id = 'writeback_cache', type = 'config_sync', end = len(self.__cachedExecutions))
		if currentProgressObserver: currentProgressSubject.attachObserver(currentProgressObserver)
		
		self._workRemoteOnly(True)
		for i in range(len(self.__cachedExecutions)):
			currentProgressSubject.setMessage( _("Writing back cached service call %d") % (i+1) )
			try:
				ce = self.__cachedExecutions[i]
				self._execCachedExecution(ce['method'], params = ce['params'])
			except Exception, e:
				self.__cachedExecutions = self.__cachedExecutions[i:]
				self._writeCachedExecutionsFile()
				raise
			currentProgressSubject.addToState(1)
		self.__cachedExecutions = []
		self._writeCachedExecutionsFile()
		
	def _workLocalOnly(self, local):
		if local:
			logger.info("Now working local only")
			self.__localOnly = True
			self.__remoteOnly = False
		else:
			self.__localOnly = False
	
	def _workRemoteOnly(self, remote):
		if remote:
			logger.info("Now working remote only")
			self.__remoteOnly = True
			self.__localOnly = False
			#if isinstance(self.__remoteBackend, JSONRPCBackend):
			#	# Connecting to get possible methods
			#	self.__remoteBackend._connect()
			#	self._createInstanceMethods()
		else:
			self.__remoteOnly = False
	
	def _getParams(self, **options):
		params = []
		logger.debug("Options: %s" % options)
		if options.has_key('params'):
			ps = options['params']
			if not isinstance(ps, tuple) and not isinstance(ps, list):
				ps = [ ps ]
			
			for p in ps:
				if (p == '__UNDEF__'):
					p = None
				logger.debug2("Appending param: %s, type: %s" % (p, type(p)))
				params.append(p)
		return params
		
	def _exec(self, method, **options):
		params = self._getParams(**options)
		ps = str(params)[1:-1]
		if (len(ps) > 200):
			# Do not log long strings like used in writeLog
			ps = ps[:200-3] + '...'
		
		if not self.__localOnly:
			try:
				logger.info('Executing on remote backend: %s(%s)' % (method, ps))
				be = self.__remoteBackend
				result = eval('be.%s(*params)' % method)
				return result
			except Exception, e:
				if self.__remoteOnly:
					raise
				logger.warning("Remote backend failed, using cache: %s" % e)
		
		logger.info('Executing on local work backend: %s(%s)' % (method, ps))
		
		if (method == 'getOpsiHWAuditConf'):
			return self.getOpsiHWAuditConf()
		
		be = self.__workBackend
		result = eval('be.%s(*params)' % method)
		self._addCachedExecution(method = method, params = params)
		return result
		
	def _execCachedExecution(self, method, **options):
		params = self._getParams(**options)
		
		if method in ('setProductActionRequest', 'unsetProductActionRequest'):
			cachedActionRequest = ''
			for ar in self.__cacheBackend.getProductActionRequests_listOfHashes(clientId = params[1]):
				if (ar['productId'] == params[0]):
					cachedActionRequest = ar['actionRequest']
					break
			actionRequest = ''
			for ar in self.__remoteBackend.getProductActionRequests_listOfHashes(clientId = params[1]):
				if (ar['productId'] == params[0]):
					actionRequest = ar['actionRequest']
					break
			if (cachedActionRequest != actionRequest):
				logger.warning("Action request for client '%s', product '%s' changed from '%s' to '%s', updating cache with new value" \
					% (params[1], params[0], cachedActionRequest, actionRequest))
				self.__workBackend.setProductActionRequest(productId = params[0], clientId = params[1], actionRequest = actionRequest)
				self.__cacheBackend.setProductActionRequest(productId = params[0], clientId = params[1], actionRequest = actionRequest)
				return
		
		logger.notice('Executing on remote backend: %s(%s)' % (method, str(params)[1:-1]))
		be = self.__remoteBackend
		result = eval('be.%s(*params)' % method)
		return result
		
	def getOpsiHWAuditConf(self, lang=''):
		logger.info("Reading hwaudit conf file '%s'" % self.__hwauditConfFile)
		f = open(self.__hwauditConfFile, 'rb')
		hwAuditConf = f.read()
		f.close()
		return json.loads(hwAuditConf)
	
	def getPossibleMethods_listOfHashes(self):
		if not self.__possibleMethods:
			logger.debug("OfflineBackend: Getting possible methods")
			#self.__possibleMethods = []
			#try:
			#	self.__possibleMethods = self.__remoteBackend.getPossibleMethods_listOfHashes()
			#except Exception, e:
			#	logger.info("Getting possible methods from cacheBackend")
			for (n, t) in self.__cacheBackend.__class__.__dict__.items():
				# Extract a list of all "public" functions (functionname does not start with '_') 
				if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
				      and not n.startswith('_') ):
					argCount = t.func_code.co_argcount
					argNames = list(t.func_code.co_varnames[1:argCount])
					argDefaults = t.func_defaults
					if ( argDefaults != None and len(argDefaults) > 0 ):
						offset = argCount - len(argDefaults) - 1
						for i in range( len(argDefaults) ):
							argNames[offset+i] = '*' + argNames[offset+i]		
					self.__possibleMethods.append( { 'name': n, 'params': argNames} )
		return self.__possibleMethods
		
		
