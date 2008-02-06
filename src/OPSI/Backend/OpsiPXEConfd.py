# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =          OPSI OpsiPXEConfd Module          =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.2'

# Imports
import socket

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                   CLASS OPSIPXECONFDBACKEND                                        =
# ======================================================================================================
class OpsiPXEConfdBackend(Backend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' OpsiPXEConfdBackend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		self.__port = '/tmp/reinstmgr.socket'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'port'):		self.__port = value
			elif (option.lower() == 'defaultdomain'): 	self.__defaultDomain = value
			else:
				logger.warning("Unknown argument '%s' passed to OpsiPXEConfdBackend constructor" % option)
	
	def setPXEBootConfiguration(self, hostId, args={}):
		cmd = 'set %s' % hostId
		for (k,v) in args.items():
			cmd += ' %s' % k
			if v: cmd += '=%s' % v
		
		try:
			sc = ServerConnection(self.__port)
			logger.info("Sending command '%s'" % cmd)
			result = sc.sendCommand(cmd)
			logger.info("Got result '%s'" % result)
		except Exception, e:
			raise BackendIOError("Failed to set PXE boot configuration: %s" % e)
		
	def unsetPXEBootConfiguration(self, hostId):
		cmd = 'unset %s' % hostId
		try:
			sc = ServerConnection(self.__port)
			logger.info("Sending command '%s'" % cmd)
			result = sc.sendCommand(cmd)
			logger.info("Got result '%s'" % result)
		except Exception, e:
			raise BackendIOError("Failed to unset PXE boot configuration: %s" % e)
	

class ServerConnection:
	def __init__(self, port):
		self.port = port
	
	def createUnixSocket(self):
		logger.notice("Creating unix socket '%s'" % self.port)
		self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self._socket.settimeout(5.0)
		try:
			self._socket.connect(self.port)
		except Exception, e:
			raise Exception("Failed to connect to socket '%s': %s" % (self.port, e))
		
	
	def sendCommand(self, cmd):
		self.createUnixSocket()
		self._socket.send(cmd)
		result = None
		try:
			result = self._socket.recv(4096)
		except Exception, e:
			raise Exception("Failed to receive: %s" % e)
		self._socket.close()
		if result.startswith('(ERROR)'):
			raise Exception("Command '%s' failed: %s" % (cmd, result))
		return result
	

