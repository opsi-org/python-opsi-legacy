#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = =
   =   opsi-fire-event.py    =
   = = = = = = = = = = = = = =
   
   This script is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2009 uib GmbH
   
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

import os, sys, httplib, urllib, base64, json
from OPSI.Backend.BackendManager import *

def usage():
	print "Usage: %s <clientId> <event>" % os.path.basename(sys.argv[0])
	print " Fires the opsiclientd event <event> on client <clientId>"

def main():
	clientId = sys.argv[1]
	event = sys.argv[2]
	
	print "Client: %s, event: %s" % (clientId, event)
	
	backend = BackendManager(configFile = '/etc/opsi/backendManager.d', authRequired = False)
	clientHostKey = backend.getOpsiHostKey(clientId)
	backend.exit()
	
	host = clientId
	query = json.write( { 'id': 1, 'method': 'fireEvent', 'params': [ event ] } )
	connection = httplib.HTTPSConnection(host, 4441)
	connection.putrequest('POST', '/opsiclientd')
	connection.putheader('content-type', 'application/json-rpc')
	connection.putheader('content-length', str(len(query)))
	auth = urllib.unquote('%s:%s' % (clientId, clientHostKey))
	connection.putheader('Authorization', 'Basic '+ base64.encodestring(auth).strip() )
	connection.endheaders()
	connection.send(query)

	response = connection.getresponse()
	response = response.read()
	
	if json.read(response).get('error'):
		# Error occurred
		raise Exception( json.read(response).get('error') )
	result = json.read(response).get('result')
	if result:
		print "OK: %s" % result
	else:
		print "OK"


if (len(sys.argv) < 3):
	usage()
	sys.exit(1)
try:
	main()
except Exception, e:
	print "Error: %s" % e
	sys.exit(1)
sys.exit(0)


