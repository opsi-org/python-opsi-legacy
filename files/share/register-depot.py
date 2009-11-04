#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = =
   =   register-depot.py   =
   = = = = = = = = = = = = =
   
   This script is part of the desktop management solution opsi
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

__version__ = '1.1.2'

import sys, os, getpass, socket

from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Logger import *
from OPSI import Tools
from OPSI.System import *

logger = Logger()
logger.setConsoleLevel(LOG_NOTICE)
logger.setConsoleColor(True)

backendConfigFile = '/etc/opsi/backendManager.d/15_jsonrpc.conf'
configServer = 'localhost'
adminUser = 'root'
adminPass = 'password'
fqdn = socket.getfqdn()
depotName = fqdn.split('.')[0]
domain = '.'.join( fqdn.split('.')[1:] )
depotLocalUrl = 'file:///opt/pcbin/install'
depotRemoteUrl = 'smb://%s/opt_pcbin/install' % depotName
repositoryLocalUrl = 'file:///var/lib/opsi/products'
repositoryRemoteUrl = 'webdavs://%s:4447/products' % fqdn
network = '0.0.0.0/0'
description = 'Depotserver %s' % depotName
maxBandwidth = 0
notes = ''         

try:
	if (os.getuid() != 0):
		raise Exception(_("Please run this script as user root!"))
	
	print ""
	print "*********************************************************************************"
	print "*         This tool will register the current server as depotserver.            *"
	print "* The config file " +         backendConfigFile          + " will be recreated. *"
	print "*                  =>>> Press <CTRL> + <C> to abort <<<=                        *"
	print "*********************************************************************************"
	print ""
	
	# Ask config
	print " Config server [%s]: " % configServer,
	uin = sys.stdin.readline().strip()
	if uin: configServer = uin
	
	print "Account name to use for login [%s]: " % adminUser,
	uin = sys.stdin.readline().strip()
	if uin: adminUser = uin
	
	print "Account password [%s]: " % adminPass,
	uin = getpass.getpass('')
	if uin: adminPass = uin
	
	# Connect to config server
	logger.notice("Connecting to host '%s' as user '%s'" % (configServer, adminUser))
	be = JSONRPCBackend(address = configServer, username = adminUser, password = adminPass )
	try:
		depot = be.getDepot_hash(fqdn)
		network = depot.get('network', network)
		description = depot.get('description', description)
		notes = depot.get('notes', notes)
		maxBandwidth = depot.get('repositoryMaxBandwidth', maxBandwidth)
	except:
		pass
	
	print " The subnet this depotserver is responsible for [%s]: " % network,
	uin = sys.stdin.readline().strip()
	if uin: network = uin
	
	print "Description for this depotserver [%s]: " % description,
	uin = sys.stdin.readline().strip()
	if uin: description = uin
	
	print "Additional notes for this depotserver [%s]: " % notes,
	uin = sys.stdin.readline().strip()
	if uin: notes = uin
	
	print "Maximum upload bandwith in kilobyte per second (0=unlimited) [%s]: " % maxBandwidth,
	uin = sys.stdin.readline().strip()
	if uin: maxBandwidth = uin
	
	print ""
	
	# Create depot server
	logger.notice("Creating depot '%s'" % fqdn)
	depotId = be.createDepot(
			depotName = depotName,
			domain = domain,
			depotLocalUrl = depotLocalUrl,
			depotRemoteUrl = depotRemoteUrl,
			repositoryLocalUrl = repositoryLocalUrl,
			repositoryRemoteUrl = repositoryRemoteUrl,
			network = network,
			description = description,
			notes = notes,
			maxBandwidth = maxBandwidth)
	
	hostKey = be.getOpsiHostKey(depotId)
	be.exit()
	
	# Test connection / credentials / setting pcpatch password
	logger.notice("Testing connection and setting pcpatch password")
	
	be = JSONRPCBackend(address = configServer, username = depotId, password = hostKey )
	
	password = Tools.blowfishDecrypt(hostKey, be.getPcpatchPassword(depotId))
	
	try:
		# Nothing to do on univention
		uva = which('univention-admin')
	except:
		# Not running on ucs
		f = os.popen(which('chpasswd'), 'w')
		f.write("pcpatch:%s\n" % password)
		f.close()
		
		f = os.popen('%s -a -s pcpatch 1>/dev/null 2>/dev/null' % which('smbpasswd'), 'w')
		f.write("%s\n%s\n" % (password, password))
		f.close()
		
	be.exit()
	
	logger.notice("Connection / credentials ok, pcpatch password set!")
	
	# Connection ok, write backend config
	logger.notice("Creating jsonrpc backend config file %s" % backendConfigFile)
	if os.path.exists(backendConfigFile):
		os.system('cp %s %s.sav' % (backendConfigFile, backendConfigFile))
		os.system('chmod 600 %s.sav' % backendConfigFile)
	f = open(backendConfigFile, 'w')
	print >> f, "''' - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -"
	print >> f, "-     JSONRPC backend                                                     -"
	print >> f, "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - '''"
	print >> f, "global BACKEND_JSONRPC"
	print >> f, "BACKEND_JSONRPC = 'JSONRPC'"
	print >> f, ""
	print >> f, "self.backends[BACKEND_JSONRPC] = {"
	print >> f, "        'load': True"
	print >> f, "}"
	print >> f, ""
	print >> f, "self.backends[BACKEND_JSONRPC]['config'] = {"
	print >> f, '        "address":     "%s",' % configServer
	print >> f, '        "username":    "%s",' % depotId
	print >> f, '        "password":    "%s",' % hostKey
	print >> f, '        "timeout":     None'
	print >> f, "}"
	f.close()
	
	backendConfigFile = '/etc/opsi/backendManager.d/30_vars.conf'
	logger.notice("Patching config file %s" % backendConfigFile)
	
	if os.path.exists(backendConfigFile):
		os.system('cp %s %s.sav' % (backendConfigFile, backendConfigFile))
		os.system('chmod 600 %s.sav' % backendConfigFile)
	
	lines = []
	f = open(backendConfigFile, 'r')
	for line in f.readlines():
		if (line.find("BACKEND") != -1):
			continue
		lines.append(line.strip())
	f.close()
	
	f = open(backendConfigFile, 'w')
	for i in range(len(lines)):
		if (i == len(lines)-1) and not lines[i] and not lines[i-1]:
			continue
		print >> f, lines[i]
	print >> f, "self.defaultBackend        = BACKEND_JSONRPC"
	print >> f, "self.clientManagingBackend = BACKEND_JSONRPC"
	print >> f, "self.pxebootconfBackend    = BACKEND_OPSIPXECONFD"
	print >> f, "self.passwordBackend       = BACKEND_JSONRPC"
	print >> f, "self.pckeyBackend          = BACKEND_JSONRPC"
	print >> f, "self.swinventBackend       = BACKEND_JSONRPC"
	print >> f, "self.hwinventBackend       = BACKEND_JSONRPC"
	print >> f, "self.loggingBackend        = BACKEND_JSONRPC"
	f.close()
	
except KeyboardInterrupt:
	pass
except Exception, e:
	logger.logException(e)
	print >> sys.stderr, "ERROR: %s" % e

print ""
sys.exit(0)

