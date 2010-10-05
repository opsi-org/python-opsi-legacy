#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - setup file  =
   = = = = = = = = = = = = = = = = = = = =
   
   opsiconfd is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2010 uib GmbH
   
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
   @author: Christian Kampka <c.kampka@uib.de>
   @license: GNU General Public License version 2
"""

from setuptools import setup, find_packages
import os, sys

f = open("debian/changelog")
VERSION = f.readline().split('(')[1].split('-')[0]
f.close()

if not VERSION:
    raise Exception(u"Failed to get version info")

f = open("data/version", "w")
f.write(VERSION)
f.close()

data_files=[('/etc/opsi/backendManager', ['data/backendManager/acl.conf.default', 
					  'data/backendManager/dispatch.conf.default']),
	    ('/etc/opsi/backendManager/extend.d', ['data/backendManager/extend.d/10_opsi.conf',
						   'data/backendManager/extend.d/20_legacy.conf']),
	    ('/etc/opsi/backendManager/extend.d/configed', ['data/backendManager/extend.d/configed/30_configed.conf']),
	    ('/etc/opsi/backends/', ['data/backends/dhcpd.conf',
				     'data/backends/file.conf',
				     'data/backends/jsonrpc.conf',
				     'data/backends/ldap.conf',
				     'data/backends/mysql.conf',
				     'data/backends/multiplex.conf',
				     'data/backends/opsipxeconfd.conf']),
	    ('/etc/opsi/', ['data/version']),
	    ('/etc/opsi/hwaudit/', ['data/hwaudit/opsihwaudit.conf']),
	    ('/etc/opsi/hwaudit/locales', ['data/hwaudit/locales/de_DE',
					   'data/hwaudit/locales/en_US',
					   'data/hwaudit/locales/fr_FR'])]
if bool(os.getenv("RPM_BUILD_ROOT")):
	data_files.append( ('/etc/openldap/schema/', ['data/opsi.schema', 'data/opsi-standalone.schema']) )
else:
	data_files.append( ('/etc/ldap/schema/', ['data/opsi.schema', 'data/opsi-standalone.schema']) )

if not os.path.exists('locale/de/LC_MESSAGES'):
	os.makedirs('locale/de/LC_MESSAGES')
os.system('msgfmt -o locale/de/LC_MESSAGES/python-opsi.mo gettext/python-opsi_de.po')
data_files.append( ('/usr/share/locale/de/LC_MESSAGES', ['locale/de/LC_MESSAGES/python-opsi.mo']) )

setup(
	name='python-opsi',
	version=VERSION,
	license='GPL-2',
	url="http://www.opsi.org",
	description='The opsi python library',
	#long-description='Long description goes here',
	packages=find_packages(),
	data_files=data_files
)





