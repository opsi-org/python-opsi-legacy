#! /usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2014 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Configuration data for the backend.

.. versionadded:: 4.0.5.2

:author: Niko Wenselowski <n.wenselowski@uib.de>
:author: Erol Ueluekmen <e.ueluekmen@uib.de>
:license: GNU Affero General Public License version 3
"""
import codecs
import os
import re

import OPSI.Backend.BackendManager as bm
import OPSI.Object as oobject
import OPSI.System.Posix as Posix

from OPSI.Logger import Logger

LOGGER = Logger()
SMB_CONF = u'/etc/samba/smb.conf'


def initializeConfigs(backend=None, configServer=None, pathToSMBConf=SMB_CONF):
	"""
	Adding default configurations to the backend.

	:param backend: The backend to use. If this is ``None`` an backend \
will be created.
	:param configServer: The ConfigServer that should be used as \
default. Supply this if ``clientconfig.configserver.url`` or \
``clientconfig.depot.id`` are not yet set.
	:type configServer: OPSI.Object.OpsiConfigserver
	:param pathToSMBConf: The path the samba configuration.
	:type pathToSMBConf: str
	"""
	def runningOnUCS():
		return 'univention' in Posix.Distribution().distributor.lower()

	backendProvided = True

	if backend is None:
		backendProvided = False
		backend = bm.BackendManager(
			dispatchConfigFile=u'/etc/opsi/backendManager/dispatch.conf',
			backendConfigDir=u'/etc/opsi/backends',
			extensionConfigDir=u'/etc/opsi/backendManager/extend.d',
			depotbackend=False
		)
		backend.backend_createBase()

	configs = []
	configIdents = backend.config_getIdents(returnType='unicode')

	if runningOnUCS():
		# We have a domain present and people might want to change this.
		if 'clientconfig.depot.user' not in configIdents:
			depotuser = u'pcpatch'
			depotdomain = readWindowsDomainFromSambaConfig(pathToSMBConf)
			if depotdomain:
				depotuser = '\\'.join((depotdomain, depotuser))

			configs.append(
				oobject.UnicodeConfig(
					id=u'clientconfig.depot.user',
					description=u'User for depot share',
					possibleValues=[],
					defaultValues=[depotuser],
					editable=True,
					multiValue=False
				)
			)

	if configServer and 'clientconfig.configserver.url' not in configIdents:
		LOGGER.debug("Missing clientconfig.configserver.url - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.configserver.url',
				description=u'URL(s) of opsi config service(s) to use',
				possibleValues=[u'https://%s:4447/rpc' % configServer.getIpAddress()],
				defaultValues=[u'https://%s:4447/rpc' % configServer.getIpAddress()],
				editable=True,
				multiValue=True
			)
		)
	if configServer and 'clientconfig.depot.id' not in configIdents:
		LOGGER.debug("Missing clientconfig.depot.id - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.depot.id',
				description=u'ID of the opsi depot to use',
				possibleValues=[configServer.getId()],
				defaultValues=[configServer.getId()],
				editable=True,
				multiValue=False
			)
		)
	if 'clientconfig.depot.dynamic' not in configIdents:
		LOGGER.debug("Missing clientconfig.depot.dynamic - adding it.")
		configs.append(
			oobject.BoolConfig(
				id=u'clientconfig.depot.dynamic',
				description=u'Use dynamic depot selection',
				defaultValues=[False]
			)
		)
	if 'clientconfig.depot.drive' not in configIdents:
		LOGGER.debug("Missing clientconfig.depot.drive - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.depot.drive',
				description=u'Drive letter for depot share',
				possibleValues=[
					u'c:', u'd:', u'e:', u'f:', u'g:', u'h:', u'i:', u'j:',
					u'k:', u'l:', u'm:', u'n:', u'o:', u'p:', u'q:', u'r:',
					u's:', u't:', u'u:', u'v:', u'w:', u'x:', u'y:', u'z:'
				],
				defaultValues=[u'p:'],
				editable=False,
				multiValue=False
			)
		)

	if 'clientconfig.depot.protocol' not in configIdents:
		LOGGER.debug("Missing clientconfig.depot.protocol - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.depot.protocol',
				description=u'Protocol for file transfer',
				possibleValues=['cifs', 'webdav'],
				defaultValues=['cifs'],
				editable=False,
				multiValue=False
			)
		)
	if 'clientconfig.windows.domain' not in configIdents:
		LOGGER.debug("Missing clientconfig.windows.domain - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.windows.domain',
				description=u'Windows domain',
				possibleValues=[],
				defaultValues=[readWindowsDomainFromSambaConfig(pathToSMBConf)],
				editable=True,
				multiValue=False
			)
		)
	if 'opsi-linux-bootimage.append' not in configIdents:
		LOGGER.debug("Missing opsi-linux-bootimage.append - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'opsi-linux-bootimage.append',
				description=u'Extra options to append to kernel command line',
				possibleValues=[
					u'acpi=off', u'irqpoll', u'noapic', u'pci=nomsi',
					u'vga=normal', u'reboot=b'
				],
				defaultValues=[u''],
				editable=True,
				multiValue=True
			)
		)
	if 'license-management.use' not in configIdents:
		LOGGER.debug("Missing license-management.use - adding it.")
		configs.append(
			oobject.BoolConfig(
				id=u'license-management.use',
				description=u'Activate license management',
				defaultValues=[False]
			)
		)
	if 'software-on-demand.active' not in configIdents:
		LOGGER.debug("Missing software-on-demand.active - adding it.")
		configs.append(
			oobject.BoolConfig(
				id=u'software-on-demand.active',
				description=u'Activate software-on-demand',
				defaultValues=[False]
			)
		)
	if 'software-on-demand.show-details' not in configIdents:
		LOGGER.debug("Missing software-on-demand.show-details - adding it.")
		configs.append(
			oobject.BoolConfig(
				id=u'software-on-demand.show-details',
				description=u'Show more details for software-on-demand',
				defaultValues=[False]
			)
		)
	if 'software-on-demand.product-group-ids' not in configIdents:
		LOGGER.debug("Missing software-on-demand.product-group-ids - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'software-on-demand.product-group-ids',
				description=(
					u'Product group ids containing products which are '
					u'allowed to be installed on demand'
				),
				possibleValues=[u'software-on-demand'],
				defaultValues=[u'software-on-demand'],
				editable=True,
				multiValue=True
			)
		)
	if 'product_sort_algorithm' not in configIdents:
		LOGGER.debug("Missing product_sort_algorithm - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'product_sort_algorithm',
				description=u'Product sorting algorithm',
				possibleValues=[u'algorithm1', u'algorithm2'],
				defaultValues=[u'algorithm1'],
				editable=False,
				multiValue=False
			)
		)

	if 'clientconfig.dhcpd.filename' not in configIdents:
		LOGGER.debug("Missing clientconfig.dhcpd.filename - adding it.")
		configs.append(
			oobject.UnicodeConfig(
				id=u'clientconfig.dhcpd.filename',
				description=(
					u"The name of the file that will be presented to the "
					u"client on an TFTP request. For an client that should "
					u"boot via UEFI this must include the term 'elilo'."
				),
				possibleValues=[u'elilo'],
				defaultValues=[u''],
				editable=True,
				multiValue=False
			)
		)

	if configs:
		LOGGER.notice('Setting up default values.')
		backend.config_createObjects(configs)
		LOGGER.notice('Finished setting up default values.')

	if not backendProvided:
		backend.backend_exit()


def readWindowsDomainFromSambaConfig(pathToConfig=SMB_CONF):
	"""
	Get the Windows domain (workgroup) from smb.conf.
	If no workgroup can be found this returns an empty string.

	:param pathToConfig: Path to the smb.conf
	:type pathToConfig: str
	:return: The Windows domain in uppercase letters.
	:returntype: str
	"""
	winDomain = u''
	if os.path.exists(pathToConfig):
		pattern = re.compile(r'^\s*workgroup\s*=\s*(\S+)\s*$')
		with codecs.open(pathToConfig, 'r', 'utf-8') as sambaConfig:
			for line in sambaConfig:
				match = pattern.search(line)
				if match:
					winDomain = match.group(1).upper()
					break

	return winDomain
