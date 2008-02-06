# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =          OPSI WakeOnLAN Module             =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.1'

# Imports
import socket, struct, re

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *
import OPSI.System
import OPSI.Tools

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                    CLASS WAKEONLANBACKEND                                          =
# ======================================================================================================
class WakeOnLANBackend(Backend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, args={}):
		''' WakeOnLANBackend constructor. '''
		
		self.__backendManager = backendManager
		self.__etherwakeCommand = None
		
		# Parse arguments
		for (option, value) in args.items():
			if (option.lower() == 'defaultdomain'): 	self.__defaultDomain = value
			else:
				logger.warning("Unknown argument '%s' passed to WakeOnLAN constructor" % option)
	
	def powerOnHost(self, mac):
		''' Switches on remote computers using WOL. '''
		
		# Check macaddress format and try to compensate.
		if (re.search("^[0-9a-fA-F]{12}$", mac)):
			pass
		
		elif (re.search("^[0-9a-fA-F\:]{17}$", mac)):
			mac = mac.replace(':', '')
		
		else:
			raise BackendBadValueError("Incorrect MAC address format: '%s'" % mac)
		
		logger.notice("Trying to switch on host with mac '%s'" % mac)
		
		# Pad the synchronization stream.
		data = ''.join(['FFFFFFFFFFFF', mac * 20])
		send_data = '' 
		
		# Split up the hex values and pack.
		for i in range(0, len(data), 2):
			send_data = ''.join([
				send_data,
				struct.pack('B', int(data[i: i + 2], 16)) ])
		
		logger.debug("Sending data to network broadcast [%s]" % data)
		# Broadcast it to the LAN.
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
		sock.sendto(send_data, ('<broadcast>', 7))
		
		
	
