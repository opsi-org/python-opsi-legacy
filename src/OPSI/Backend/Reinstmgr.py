# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =          OPSI Reinstmgr Module             =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.4'

# Imports
import os

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *
import OPSI.System

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                    CLASS REINSTMGRBACKEND                                          =
# ======================================================================================================
class ReinstmgrBackend(Backend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' ReinstmgrBackend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		if os.name == 'posix':
			self.__reinstmgrCommand = '/usr/sbin/reinstmgr'
		else:
			self.__reinstmgrCommand = 'C:\\Programme\\opsi.org\\opsiconfd\\opsi\\Reinstmgr.exe'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'reinstmgrcommand'):	self.__reinstmgrCommand = value
			elif (option.lower() == 'defaultdomain'): 	self.__defaultDomain = value
			else:
				logger.warning("Unknown argument '%s' passed to ReinstmgrBackend constructor" % option)
		
		# Test if reinstmgr command is executable
		if os.name == "posix":
			if not os.access(self.__reinstmgrCommand, os.X_OK):
				raise BackendIOError("Command %s not executable!" % self.__reinstmgrCommand )
	
	def getBootimages_list(self):
		bootfiles = []
		
		# Build command string
		cmd = '%s 2>&1' % self.__reinstmgrCommand
		# Execute command
		result = OPSI.Tools.execute(cmd)
		for line in result:
			# Result should contain a line like:
			#   Bootfiles: bootfile_1 bootfile_2 other_bootfile
			if line.startswith('Bootfiles:'):
				bootfiles = line.split()[1:]
				for i in range( len(bootfiles) ):
					bootfiles[i] = bootfiles[i].strip()
		
		#if (len(bootfiles) < 1):
		#	if os.name == "posix":
		#		raise BackendMissingDataError('No bootimages found')
		
		return bootfiles
		
	def setBootimage(self, bootimage, hostId, mac=None):
		if not mac: 
			mac = ''
		
		cmd = '%s %s %s %s 2>&1' % (self.__reinstmgrCommand, bootimage, self.getHostname(hostId), mac)
		# Execute command
		result = OPSI.Tools.execute(cmd)
		if not result[-2].lower().startswith('now writing bootimage %s' % bootimage):
			raise BackendIOError("Command '%s' failed: %s" % (cmd, '\n'.join(result)) )
		
	def unsetBootimage(self, hostId):
		cmd = '%s unset %s 2>&1' % (self.__reinstmgrCommand, self.getHostname(hostId))
		result = OPSI.Tools.execute(cmd)
		if not result[-2].lower().startswith('%s is unset' % self.getHostname(hostId).lower()):
			raise BackendIOError("Command '%s' failed: %s" % (cmd, '\n'.join(result)) )
		
		
	

