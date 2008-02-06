# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =          OPSI Etherwake Module             =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.1'

# Imports
import os

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *
import OPSI.System
import OPSI.Tools

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                    CLASS ETHERWAKEBACKEND                                          =
# ======================================================================================================
class EtherwakeBackend(Backend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' EtherwakeBackend constructor. '''
		
		self.__backendManager = backendManager
		self.__etherwakeCommand = None
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'etherwakecommand'):	self.__etherwakeCommand = value
			elif (option.lower() == 'defaultdomain'): 	self.__defaultDomain = value
			else:
				logger.warning("Unknown argument '%s' passed to EtherwakeBackend constructor" % option)
		
		if not self.__etherwakeCommand:
			self.__etherwakeCommand = OPSI.Tools.which('etherwake')
		
		# Test if etherwake command is executable
		if not os.access(self.__etherwakeCommand, os.X_OK):
			raise BackendIOError("Command %s not executable!" % self.__etherwakeCommand )
	
	def powerOnHost(self, mac):
		cmd = '%s %s 2>&1' % (self.__etherwakeCommand, mac)
		try:
			OPSI.System.execute(cmd)
		except Exception, e:
			raise BackendIOError("Command '%s' failed: %s" % (cmd, e) )
		
	
