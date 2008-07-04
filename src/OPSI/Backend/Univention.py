#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Univention    =
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

__version__ = '0.5'

# Imports
import ldap, ldap.modlist, re

# OPSI imports
from OPSI.Backend.Backend import *
import OPSI.Backend.LDAP
from OPSI.Logger import *
from OPSI.Product import *
from OPSI import Tools
from OPSI.System import execute

# Get logger instance
logger = Logger()

# ======================================================================================================
# =                                  CLASS UNIVENTIONBACKEND                                           =
# ======================================================================================================
class UniventionBackend(OPSI.Backend.LDAP.LDAPBackend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, session=None, args={}):
		''' UniventionBackend constructor. '''
		OPSI.Backend.LDAP.LDAPBackend.__init__(self, username, password, address, backendManager, session, args)
		
	def setPXEBootConfiguration(self, hostId, args = {}):
		host = OPSI.Backend.LDAP.Object( self.getHostDn(hostId) )
		host.readFromDirectory(self._ldap)
		host.setAttribute('univentionWindowsReinstall', [ '1' ])
		host.writeToDirectory(self._ldap)
		
	def unsetPXEBootConfiguration(self, hostId):
		host = OPSI.Backend.LDAP.Object( self.getHostDn(hostId) )
		host.readFromDirectory(self._ldap)
		host.setAttribute('univentionWindowsReinstall', [ '0' ])
		host.writeToDirectory(self._ldap)


