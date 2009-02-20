#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Cache     =
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

__version__ = '0.1'

# Imports


import time, types, new, json

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *

# Get logger instance
logger = Logger()



# ======================================================================================================
# =                                   CLASS CACHEBACKEND                                             =
# ======================================================================================================
class CacheBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		
		self.__backendManager = backendManager
		self.__possibleMethods = None
		self.__cacheOnly = False
		self.__mainOnly = False
		self.__cachedExecutions = []
		
		# Default values
		self.__mainBackend  = None
		self.__cacheBackend = None
		self.__workBackend = None
		self.__cleanupBackend = False
		self.__cachedExecutionsFile = ''
		self._defaultDomain = None
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'mainbackend'):          self.__mainBackend = value
			elif (option.lower() == 'cachebackend'):         self.__cacheBackend = value
			elif (option.lower() == 'workbackend'):          self.__workBackend = value
			elif (option.lower() == 'cleanupbackend'):       self.__cleanupBackend = bool(value)
			elif (option.lower() == 'cachedexecutionsfile'): self.__cachedExecutionsFile = value
			else:
				logger.warning("Unknown argument '%s' passed to CacheBackend constructor" % option)
		
		if not self.__mainBackend or not self.__cacheBackend or not self.__workBackend:
			raise Exception("MainBackend, cacheBackend and workingBackend needed")
		
		self.__cacheReplicator = DataBackendReplicator(
					readBackend  = self.__mainBackend,
					writeBackend = self.__cacheBackend,
					cleanupFirst = self.__cleanupBackend )
		
		self.__workReplicator = DataBackendReplicator(
					readBackend  = self.__cacheBackend,
					writeBackend = self.__workBackend,
					cleanupFirst = self.__cleanupBackend )
		
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
			
			logger.debug2("Creating instance method '%s'" % method['name'])
			
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
		
		self.readCachedExecutionsFile()
	
	def readCachedExecutionsFile(self):
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
			self.__cachedExecutions.append(json.read(line.strip()))
		f.close()
		
	def writeCachedExecutionsFile(self, lastOnly=False):
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
			f.write(json.write(ce) + '\n')
		f.close()
		
	def addCachedExecution(self, method, params=[]):
		self.__cachedExecutions.append({'method': method, 'params': params})
		self.writeCachedExecutionsFile(lastOnly=True)
	
	def getCachedExecutions(self):
		return self.__cachedExecutions
	
	def buildCache(self, depotIds=[], clientIds=[], productIds=[]):
		self.__cacheReplicator.replicate(depotIds = depotIds, clientIds = clientIds, productIds = productIds)
		for depotId in self.__cacheBackend.getDepotIds_list():
			# Do not store depot keys
			self.__cacheBackend.setOpsiHostKey(depotId, '00000000000000000000000000000000')
		self.__workReplicator.replicate(depotIds = depotIds, clientIds = clientIds, productIds = productIds)
		for depotId in self.__cacheBackend.getDepotIds_list():
			# Do not store depot keys
			self.__workBackend.setOpsiHostKey(depotId, '00000000000000000000000000000000')
		
	def writebackCache(self):
		self.__cacheOnly = False
		self.__mainOnly = True
		for i in range(len(self.__cachedExecutions)):
			try:
				ce = self.__cachedExecutions[i]
				self._execCachedExecution(ce['method'], params = ce['params'])
			except Exception, e:
				self.__cachedExecutions = self.__cachedExecutions[i:]
				raise
		self.__cachedExecutions = []
		self.writeCachedExecutionsFile()
		
	def workCached(self, cached):
		if cached:
			self.__cacheOnly = True
			self.__mainOnly = False
		else:
			self.__cacheOnly = False
		
	def getPossibleMethods_listOfHashes(self):
		if not self.__possibleMethods:
			self.__possibleMethods = []
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
		if not self.__cacheOnly:
			try:
				logger.notice('Executing on main backend: %s(%s)' % (method, str(params)[1:-1]))
				be = self.__mainBackend
				result = eval('be.%s(*params)' % method)
				return result
			except Exception, e:
				if self.__mainOnly:
					raise
				logger.info("Main backend failed, using cache: %s" % e)
		
		logger.notice('Executing on cache backend: %s(%s)' % (method, str(params)[1:-1]))
		be = self.__workBackend
		result = eval('be.%s(*params)' % method)
		self.addCachedExecution(method = method, params = params)
		return result
		
		raise BackendIOException("Failed to execute")
		
	def _execCachedExecution(self, method, **options):
		params = self._getParams(**options)
		
		if method in ('setProductActionRequest', 'unsetProductActionRequest'):
			cachedActionRequest = ''
			for ar in self.__cacheBackend.getProductActionRequests_listOfHashes(clientId = params[1]):
				if (ar['productId'] == params[0]):
					cachedActionRequest = ar['actionRequest']
					break
			actionRequest = ''
			for ar in self.__mainBackend.getProductActionRequests_listOfHashes(clientId = params[1]):
				if (ar['productId'] == params[0]):
					actionRequest = ar['actionRequest']
					break
			if (cachedActionRequest != actionRequest):
				logger.warning("Action request for client '%s', product '%s' changed from '%s' to '%s', updating cache with new value" \
					% (params[1], params[0], cachedActionRequest, actionRequest))
				self.__workBackend.setProductActionRequest(productId = params[0], clientId = params[1], actionRequest = actionRequest)
				self.__cacheBackend.setProductActionRequest(productId = params[0], clientId = params[1], actionRequest = actionRequest)
				return
		
		logger.notice('Executing on main backend: %s(%s)' % (method, str(params)[1:-1]))
		be = self.__mainBackend
		result = eval('be.%s(*params)' % method)
		return result
		
		
		
		
		
