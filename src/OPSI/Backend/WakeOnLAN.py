#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - WakeOnLAN     =
   = = = = = = = = = = = = = = = = = = = = =
   
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

__version__ = '0.9.2'

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
		data = ''.join(['FFFFFFFFFFFF', mac * 16])
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
		sock.sendto(send_data, ('<broadcast>', 12287))
	
