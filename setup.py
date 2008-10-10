#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from distutils.core import setup, Extension

setup (
	name = 'python-opsi',
	version = '3.3.0.25',
	description = 'opsi python library',
	long_description = 'opsi python library.',
	author = "uib GmbH",
	author_email = 'info@uib.de',
	license = 'GPL',
	url='http://www.opsi.org',
	package_dir = {'': 'src'},
	packages = [
		'OPSI',
		'OPSI.Backend',
		'OPSI.System',
		'OPSI.web2',
		'OPSI.web2.client',
		'OPSI.web2.dav',
		'OPSI.web2.dav.element',
		'OPSI.web2.dav.method',
		'OPSI.web2.dav.test',
		'OPSI.web2.dav.test.data',
		'OPSI.web2.dav.test.data.xml',
		'OPSI.web2.test',
		'OPSI.web2.filter',
		'OPSI.web2.auth',
		'OPSI.web2.channel',
	],
	#data_files=[
	#	('/usr/share/locale/de/LC_MESSAGES opsi_system.mo', ['gettext/opsi_system.mo', 'gettext/opsi_ui.mo'])
	#]
)

