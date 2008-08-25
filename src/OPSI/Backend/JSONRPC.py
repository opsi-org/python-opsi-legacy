#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - JSONRPC   =
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

__version__ = '0.9.5.7'

# Imports
import json, base64, urllib, httplib, new, stat, socket, random

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *

# Get logger instance
logger = Logger()

METHOD_POST = 1
METHOD_GET = 2

# ======================================================================================================
# =                                   CLASS JSONRPCBACKEND                                             =
# ======================================================================================================
class JSONRPCBackend(DataBackend):
	''' This class implements parts of the abstract class Backend '''
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' JSONRPCBackend constructor. '''
		
		self.__backendManager = backendManager
		
		self.__address = address
		self.__username = username
		self.__password = password
		self.__sessionId = None
		
		# Default values
		self.__defaultHttpPort = 4444
		self.__defaultHttpsPort = 4447
		self.__protocol = 'https'
		self.__method = METHOD_POST
		self.__timeout = None
		
		# Parse arguments
		for (option, value) in args.items():
			if (option.lower() == 'address'):
				if not self.__address:			self.__address = value
			elif (option.lower() == 'username'):
				if not self.__username:			self.__username = value
			elif (option.lower() == 'password'):
				if not self.__password:			self.__password = value
			elif (option.lower() == 'defaultdomain'): 	self.__defaultDomain = value
			elif (option.lower() == 'sessionid'): 		self.__sessionId = value
			elif (option.lower() == 'timeout'): 		self.__timeout = value
			elif (option.lower() == 'method'):
				if (value.lower() == 'get'):
					self.__method = METHOD_GET
				elif (value.lower() == 'post'):
					self.__method = METHOD_POST
				else:
					logger.error("Unkown method '%s' passed to JSONRPCBackend constructor, known methods are: POST, GET" % value)
			else:
				logger.warning("Unknown argument '%s' passed to JSONRPCBackend constructor" % option)
		
		if ( self.__address.find('/') == -1 and self.__address.find('=') == -1 ):
			if (self.__protocol == 'https'):
				self.__address = '%s://%s:4447/rpc' % (self.__protocol, self.__address)
			else:
				self.__address = '%s://%s:4444/rpc' % (self.__protocol, self.__address)
		
		try:
			self.possibleMethods = self.__backendManager.getPossibleMethods_listOfHashes()
		except Exception, e:
			self.possibleMethods = []
			logger.debug("Failed to get possible methods from backend manager")
		
		socket.setdefaulttimeout(self.__timeout)
		self._connect()
	
	def _connect(self):
		
		# Split address which should be something like http(s)://xxxxxxxxxx:yy/zzzzz
		parts = self.__address.split('/')
		if ( len(parts) < 3 or ( parts[0] != 'http:' and parts[0] != 'https:') ):
			raise BackendBadValueError("Bad address: '%s'" % self.__address)
		
		# Split port from host
		hostAndPort = parts[2].split(':')
		host = hostAndPort[0]
		port = self.__defaultHttpsPort
		if (parts[0][:-1] == 'http'):
			self.__protocol = 'http'
			port = self.__defaultHttpPort
		if ( len(hostAndPort) > 1 ):
			port = int(hostAndPort[1])
		self.__baseUrl = '/' + '/'.join(parts[3:])
		
		# Connect to host
		#self.possibleMethods = []
		
		try:
			if (self.__protocol == 'https'):
				logger.info("Opening https connection to %s:%s" % (host, port))
				self.__connection = httplib.HTTPSConnection(host, port)
			else:
				logger.info("Opening http connection to %s:%s" % (host, port))
				self.__connection = httplib.HTTPConnection(host, port)
			
			#self._jsonRPC('authenticated')
			if not self.possibleMethods:
				self.possibleMethods = self._jsonRPC('getPossibleMethods_listOfHashes', retry=False)
			
			logger.info( "Successfully connected to '%s:%s'" % (host, port) ) 
		except Exception, e:
			raise BackendIOError("Cannot connect to '%s': %s" % (self.__address, e))
		
		for method in self.possibleMethods:
			if (method['name'].lower() == "getpossiblemethods_listofhashes"):
				# Method already implemented (cached result)
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
				logger.debug2('def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._jsonRPC(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s):\n  if type(%s) == list: %s = [ %s ]\n  return self._jsonRPC(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), params[1], params[1], params[1], method['name'], ', '.join(params[1:]))
			else:
				logger.debug2('def %s(%s): return self._jsonRPC(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:])) )
				exec 'def %s(%s): return self._jsonRPC(method = "%s", params = (%s))'\
					% (method['name'], ', '.join(paramsWithDefaults), method['name'], ', '.join(params[1:]))
			
			setattr(self.__class__, method['name'], new.instancemethod(eval(method['name']), None, self.__class__))
	
	
	def _jsonRPC(self, method, retry=True, **options):
		''' This function executes a JSON-RPC and
		    returns the result as a JSON object. '''
		
		if method in ('installPackage', 'uninstallPackage', 'getMD5Sum'):
			retry = False
			## Execution of these methods can take very long
			#if socket.getdefaulttimeout():
			#	# A timeout is set, remove the timeout and reconnect
			#	logger.warning("Setting socket timeout to None")
			#	socket.setdefaulttimeout(None)
			#	self._connect()
		
		#elif not socket.getdefaulttimeout():
		#	# No timeout is set, set timeout and reconnect
		#	logger.warning("Setting socket timeout to %d" % self.__timeout)
		#	socket.setdefaulttimeout(self.__timeout)
		#	self._connect()
		
		# Get params
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
		
		# Create json-rpc object
		jsonrpc = json.write( {"id": 1, "method": method, "params": params } )
		logger.debug("jsonrpc string: %s" % jsonrpc)
		
		logger.debug("requesting: '%s', query '%s'" % (self.__address, jsonrpc))
		response = self.__request(self.__baseUrl, jsonrpc, retry=retry )
		
		# Read response
		if json.read(response).get('error'):
			# Error occurred => raise BackendIOError
			raise Exception( json.read(response).get('error') )
		
		# Return result as json object
		return json.read(response).get('result', None)
	
	def __request(self, baseUrl, query='', retry=True):
		''' Do a http request '''
		
		#logger.debug("__request(%s)" % request)
		response = None
		try:
			if (self.__method == METHOD_GET):
				# Request the resulting url
				logger.debug("Using method GET")
				get = baseUrl + '?' + urllib.quote(query)
				logger.debug("requesting: %s" % get)
				self.__connection.putrequest('GET', get)
			else:
				logger.debug("Using method POST")
				self.__connection.putrequest('POST', baseUrl)
				self.__connection.putheader('content-type', 'application/json-rpc')
				self.__connection.putheader('content-length', str(len(query)))
			
			# Add some http headers
			self.__connection.putheader('Accept', 'application/json-rpc')
			self.__connection.putheader('Accept', 'text/plain')
			if self.__sessionId:
				# Add sessionId cookie to header
				self.__connection.putheader('Cookie', self.__sessionId)
			
			# Add basic authorization header
			auth = urllib.unquote(self.__username + ':' + self.__password)
			self.__connection.putheader('Authorization', 'Basic '+ base64.encodestring(auth).strip() )
			
			self.__connection.endheaders()
			if (self.__method == METHOD_POST):
				logger.debug2("Sending query")
				self.__connection.send(query)
			
			# Get response
			logger.debug2("Getting response")
			response = self.__connection.getresponse()
			
			# Get cookie from header
			cookie = response.getheader('Set-Cookie', None)
			if cookie:
				# Store sessionId cookie 
				self.__sessionId = cookie.split(';')[0].strip()
		
		except Exception, e:
			if retry:
				logger.warning("Requesting '%s' failed: %s, trying to reconnect" % (self.__address, e))
				self._connect()
				return self.__request(baseUrl, query=query, retry=False)
			else:
				logger.logException(e)
				raise BackendIOError("Requesting '%s' failed: %s" % (self.__address, e))
		
		try:
			# Return response content (body)
			return response.read()
		except Exception, e:
			raise BackendIOError("Cannot read '%s'" % e)

	def getPossibleMethods_listOfHashes(self):
		return self.possibleMethods
		
	def getSessionId(self):
		return self.__sessionId
	

