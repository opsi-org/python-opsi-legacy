#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =  opsi python library - File31   =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006 - 2010 uib GmbH
   
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
   @author: Arne Kerz <a.kerz@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '4.0'

import os, socket, ConfigParser, shutil, types, pwd, grp

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Util import toJson, fromJson
from OPSI.Util.File import *
from OPSI.Util.File.Opsi import *
from OPSI.Object import *
from OPSI.Backend.Backend import *

# Get logger instance
logger = Logger()

# ======================================================================================================
# =                                   CLASS FILEBACKEND                                                =
# ======================================================================================================
class FileBackend(ConfigDataBackend):
	#example match (ignore spaces):      exampleexam_e.-ex  _ 1234.12 - 1234.12  . local     boot
	productFilenameRegex = re.compile('^([a-zA-Z0-9\_\.-]+)\_([\w\.]+)-([\w\.]+)\.(local|net)boot$')
	
	def __init__(self, **kwargs):
		self._name = 'file'
		
		ConfigDataBackend.__init__(self, **kwargs)
		
		self.__baseDir     = u'/var/lib/opsi/config'
		self.__hostKeyFile = u'/etc/opsi/pckeys'
		
		self.__fileUser  = u'opsiconfd'
		self.__fileGroup = u'pcpatch'
		self.__fileMode  = 0660
		self.__dirUser   = u'opsiconfd'
		self.__dirGroup  = u'pcpatch'
		self.__dirMode   = 0770
		
		# Parse arguments
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('basedir',):
				self.__baseDir = forceFilename(value)
			elif option in ('hostkeyfile',):
				self.__hostKeyFile = forceFilename(value)
		
		self.__fileUid = pwd.getpwnam(self.__fileUser)[2]
		self.__fileGid = grp.getgrnam(self.__fileGroup)[2]
		self.__dirUid  = pwd.getpwnam(self.__dirUser)[2]
		self.__dirGid  = grp.getgrnam(self.__dirGroup)[2]
		
		self.__clientConfigDir   = os.path.join(self.__baseDir, u'clients')
		self.__depotConfigDir    = os.path.join(self.__baseDir, u'depots')
		self.__productDir        = os.path.join(self.__baseDir, u'products')
		self.__auditDir          = os.path.join(self.__baseDir, u'audit')
		self.__configFile        = os.path.join(self.__baseDir, u'config.ini')
		self.__clientGroupsFile  = os.path.join(self.__baseDir, u'clientgroups.ini')
		self.__clientTemplateDir = os.path.join(self.__baseDir, u'templates')
		
		self.__defaultClientTemplateName = u'pcproto'
		self.__defaultClientTemplatePath = os.path.join(os.path.join(self.__clientTemplateDir, self.__defaultClientTemplateName + u'.ini'))
		
		self.__serverId = forceHostId(socket.getfqdn())
		self._placeholderRegex  = re.compile('^(.*)<([^>]+)>(.*)$')
		
		self._mappings = {
			'Config': [
				{ 'fileType': 'ini', 'attribute': 'type',           'section': '<id>', 'option': 'type',           'json': False },
				{ 'fileType': 'ini', 'attribute': 'description',    'section': '<id>', 'option': 'description',    'json': False },
				{ 'fileType': 'ini', 'attribute': 'editable',       'section': '<id>', 'option': 'editable' ,      'json': True  },
				{ 'fileType': 'ini', 'attribute': 'multiValue',     'section': '<id>', 'option': 'multivalue' ,    'json': True  },
				{ 'fileType': 'ini', 'attribute': 'possibleValues', 'section': '<id>', 'option': 'possiblevalues', 'json': True  },
				{ 'fileType': 'ini', 'attribute': 'defaultValues',  'section': '<id>', 'option': 'defaultvalues',  'json': True  }
			],
			'OpsiClient': [
				{ 'fileType': 'key', 'attribute': 'opsiHostKey' },
				{ 'fileType': 'ini', 'attribute': 'oneTimePassword', 'section': 'info', 'option': 'onetimepassword', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'description',     'section': 'info', 'option': 'description',     'json': False },
				{ 'fileType': 'ini', 'attribute': 'notes',           'section': 'info', 'option': 'notes',           'json': False },
				{ 'fileType': 'ini', 'attribute': 'hardwareAddress', 'section': 'info', 'option': 'hardwareaddress', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'ipAddress',       'section': 'info', 'option': 'ipaddress',       'json': False },
				{ 'fileType': 'ini', 'attribute': 'inventoryNumber', 'section': 'info', 'option': 'inventorynumber', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'created',         'section': 'info', 'option': 'created',         'json': False },
				{ 'fileType': 'ini', 'attribute': 'lastSeen',        'section': 'info', 'option': 'lastseen',        'json': False }
			],
			'OpsiDepotserver': [
				{ 'fileType': 'key', 'attribute': 'opsiHostKey' },
				{ 'fileType': 'ini', 'attribute': 'description',         'section': 'depotserver', 'option': 'description',     'json': False },
				{ 'fileType': 'ini', 'attribute': 'notes',               'section': 'depotserver', 'option': 'notes',           'json': False },
				{ 'fileType': 'ini', 'attribute': 'hardwareAddress',     'section': 'depotserver', 'option': 'hardwareaddress', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'ipAddress',           'section': 'depotserver', 'option': 'ipaddress',       'json': False },
				{ 'fileType': 'ini', 'attribute': 'inventoryNumber',     'section': 'depotserver', 'option': 'inventorynumber', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'networkAddress',      'section': 'depotserver', 'option': 'network',         'json': False },
				{ 'fileType': 'ini', 'attribute': 'isMasterDepot',       'section': 'depotserver', 'option': 'ismasterdepot',   'json': True  },
				{ 'fileType': 'ini', 'attribute': 'masterDepotId',       'section': 'depotserver', 'option': 'masterdepotid',   'json': False },
				{ 'fileType': 'ini', 'attribute': 'depotRemoteUrl',      'section': 'depotshare',  'option': 'remoteurl',       'json': False },
				{ 'fileType': 'ini', 'attribute': 'depotWebdavUrl',      'section': 'depotshare',  'option': 'webdavurl',       'json': False },
				{ 'fileType': 'ini', 'attribute': 'depotLocalUrl',       'section': 'depotshare',  'option': 'localurl',        'json': False },
				{ 'fileType': 'ini', 'attribute': 'repositoryRemoteUrl', 'section': 'repository',  'option': 'remoteurl',       'json': False },
				{ 'fileType': 'ini', 'attribute': 'repositoryLocalUrl',  'section': 'repository',  'option': 'localurl',        'json': False },
				{ 'fileType': 'ini', 'attribute': 'maxBandwidth',        'section': 'repository',  'option': 'maxbandwidth',    'json': False }
			],
			'ConfigState': [
				{ 'fileType': 'ini', 'attribute': 'values', 'section': 'generalconfig', 'option': '<configId>', 'json': True }
			],
			'Product': [
				{ 'fileType': 'pro', 'attribute': 'name',               'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'licenseRequired',    'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'setupScript',        'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'uninstallScript',    'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'updateScript',       'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'alwaysScript',       'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'onceScript',         'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'customScript',       'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'priority',           'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'description',        'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'advice',             'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'changelog',          'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'productClassNames',  'object': 'product' },
				{ 'fileType': 'pro', 'attribute': 'windowsSoftwareIds', 'object': 'product' }
			],
			'LocalbootProduct': [
				{ 'fileType': 'pro', 'attribute': 'userLoginScript', 'object': 'product' }
			],
			'NetbootProduct': [
				{ 'fileType': 'pro', 'attribute': 'pxeConfigTemplate', 'object': 'product' }
			],
			'ProductProperty': [
				{ 'fileType': 'pro', 'attribute': '*' }
			],
			'ProductDependency': [
				{ 'fileType': 'pro', 'attribute': '*' }
			],
			'ProductOnDepot': [
				{ 'fileType': 'ini', 'attribute': 'productType',    'section': '<productId>-state', 'option': 'producttype',    'json': False },
				{ 'fileType': 'ini', 'attribute': 'productVersion', 'section': '<productId>-state', 'option': 'productversion', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'packageVersion', 'section': '<productId>-state', 'option': 'packageversion', 'json': False }
			],
			'ProductOnClient': [
				{ 'fileType': 'ini', 'attribute': 'productType',         'section': '<productId>-state',            'option': 'producttype',         'json': False },
				{ 'fileType': 'ini', 'attribute': 'actionProgress',      'section': '<productId>-state',            'option': 'actionprogress',      'json': False },
				{ 'fileType': 'ini', 'attribute': 'productVersion',      'section': '<productId>-state',            'option': 'productversion',      'json': False },
				{ 'fileType': 'ini', 'attribute': 'packageVersion',      'section': '<productId>-state',            'option': 'packageversion',      'json': False },
				{ 'fileType': 'ini', 'attribute': 'modificationTime',    'section': '<productId>-state',            'option': 'modificationtime',    'json': False },
				{ 'fileType': 'ini', 'attribute': 'lastAction',          'section': '<productId>-state',            'option': 'lastaction',          'json': False },
				{ 'fileType': 'ini', 'attribute': 'actionResult',        'section': '<productId>-state',            'option': 'actionresult',        'json': False },
				{ 'fileType': 'ini', 'attribute': 'targetConfiguration', 'section': '<productId>-state',            'option': 'targetconfiguration', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'installationStatus',  'section': '<productType>_product_states', 'option': '<productId>',         'json': False },
				{ 'fileType': 'ini', 'attribute': 'actionRequest',       'section': '<productType>_product_states', 'option': '<productId>',         'json': False },
			],
			'ProductPropertyState': [
				{ 'fileType': 'ini', 'attribute': 'values', 'section': '<productId>-install', 'option': '<propertyId>', 'json': True }
			],
			'Group': [
				{ 'fileType': 'ini', 'attribute': 'description',   'section': '<id>', 'option': 'description'  , 'json': False },
				{ 'fileType': 'ini', 'attribute': 'parentGroupId', 'section': '<id>', 'option': 'parentgroupid', 'json': False },
				{ 'fileType': 'ini', 'attribute': 'notes',         'section': '<id>', 'option': 'notes'        , 'json': False }
			],
			'ObjectToGroup': [
				{ 'fileType': 'ini', 'attribute': '*', 'section': '<groupId>', 'option': '<objectId>', 'json': False }
			]
		}
		
		self._mappings['UnicodeConfig']          = self._mappings['Config']
		self._mappings['BoolConfig']             = self._mappings['Config']
		self._mappings['OpsiConfigserver']       = self._mappings['OpsiDepotserver']
		self._mappings['LocalbootProduct']       = self._mappings['Product']
		self._mappings['LocalbootProduct'].extend( self._mappings['LocalbootProduct'] )
		self._mappings['NetbootProduct']         = self._mappings['Product']
		self._mappings['NetbootProduct'].extend(   self._mappings['NetbootProduct'] )
		self._mappings['UnicodeProductProperty'] = self._mappings['ProductProperty']
		self._mappings['BoolProductProperty']    = self._mappings['ProductProperty']
		self._mappings['HostGroup']              = self._mappings['Group']
		
	def backend_exit(self):
		pass
	
	def backend_createBase(self):
		logger.notice(u"Creating base path: '%s'" % (self.__baseDir))
		for dirname in (self.__baseDir, self.__clientConfigDir, self.__depotConfigDir, self.__productDir, self.__auditDir, self.__clientTemplateDir):
			if not os.path.isdir(dirname):
				self._mkdir(dirname)
			self._setRights(dirname)
		
		defaultTemplate = os.path.join(self.__clientTemplateDir, self.__defaultClientTemplateName + '.ini')
		for filename in (defaultTemplate, self.__configFile, self.__hostKeyFile, self.__clientGroupsFile):
			if not os.path.isfile(filename):
				self._touch(filename)
			self._setRights(filename)
		
	def backend_deleteBase(self):
		logger.notice(u"Deleting base path: '%s'" % (self.__baseDir))
		if os.path.exists(self.__baseDir):
			shutil.rmtree(self.__baseDir)
		if os.path.exists(self.__clientConfigDir):
			shutil.rmtree(self.__clientConfigDir)
		if os.path.exists(self.__depotConfigDir):
			shutil.rmtree(self.__depotConfigDir)
		if os.path.exists(self.__productDir):
			shutil.rmtree(self.__productDir)
		if os.path.exists(self.__auditDir):
			shutil.rmtree(self.__auditDir)
		if os.path.exists(self.__configFile):
			os.unlink(self.__configFile)
		if os.path.exists(self.__hostKeyFile):
			os.unlink(self.__hostKeyFile)
		if os.path.exists(self.__clientGroupsFile):
			os.unlink(self.__clientGroupsFile)
	
	def _setRights(self, path):
		logger.debug(u"Setting rights for path '%s'" % (path))
		try:
			if os.path.isfile(path):
				logger.debug(u"Setting rights on file '%s'" % (path))
				os.chmod(path, self.__fileMode)
				if (os.geteuid() == 0):
					os.chown(path, self.__fileUid, self.__fileGid)
				else:
					os.chown(path, -1, self.__fileGid)
			elif os.path.isdir(path):
				logger.debug(u"Setting rights on directory '%s'" % (path))
				os.chmod(path, self.__dirMode)
				if (os.geteuid() == 0):
					os.chown(path, self.__dirUid, self.__dirGid)
				else:
					os.chown(path, -1, self.__dirGid)
		except Exception, e:
			logger.warning(u"Failed to set rights for path '%s': %s" % (path, e))
		
	def _mkdir(self, path):
		logger.debug(u"Creating path: '%s'" % (path))
		os.mkdir(path)
		self._setRights(path)
		
	def _touch(self, filename):
		logger.debug(u"Creating file: '%s'" % (filename))
		if not os.path.exists(filename):
			f = LockableFile(filename)
			f.create()
		else:
			logger.debug(u"Cannot create existing file, setting rights ..." % ())
		self._setRights(filename)
		
	def __escape(self, string):
		string = forceUnicode(string)
		logger.debug2(u"Escaping string: '%s'" % (string))
		string = string.replace(u'\n', u'\\n').replace(u';', u'\\;').replace(u'#', u'\\#').replace(u'%', u'%%')
		return string
	
	def __unescape(self, string):
		string = forceUnicode(string)
		logger.debug2(u"Unescaping string: '%s'" % (string))
		string = string.replace(u'\\n', u'\n').replace(u'\\;', u';').replace(u'\\#', u'#').replace(u'%%', u'%')
		return string
	
	def _getConfigFile(self, objType, ident, fileType):
		logger.debug(u"Getting config file for '%s', '%s', '%s'" % (objType, ident, fileType))
		filename = None
		
		if (fileType == 'key'):
			filename = self.__hostKeyFile
		
		elif (fileType == 'ini'):
			if objType in ('Config', 'UnicodeConfig', 'BoolConfig'):
				filename = self.__configFile
			elif objType in ('OpsiClient',):
				filename = os.path.join(self.__clientConfigDir, ident['id'] + u'.ini')
			elif objType in ('OpsiDepotserver', 'OpsiConfigserver'):
				filename = os.path.join(self.__depotConfigDir, ident['id'] + u'.ini')
			elif objType in ('ConfigState',):
				if os.path.isfile(os.path.join(os.path.join(self.__depotConfigDir, ident['objectId'] + u'.ini'))):
					filename = os.path.join(self.__depotConfigDir, ident['objectId'] + u'.ini')
				else:
					filename = os.path.join(self.__clientConfigDir, ident['objectId'] + u'.ini')
			elif objType in ('ProductOnDepot',):
				filename = os.path.join(self.__depotConfigDir, ident['depotId'] + u'.ini')
			elif objType in ('ProductOnClient',):
				filename = os.path.join(self.__clientConfigDir, ident['clientId'] + u'.ini')
			elif objType in ('ProductPropertyState',):
				if os.path.isfile(os.path.join(os.path.join(self.__depotConfigDir, ident['objectId'] + u'.ini'))):
					filename = os.path.join(self.__depotConfigDir, ident['objectId'] + u'.ini')
				else:
					filename = os.path.join(self.__clientConfigDir, ident['objectId'] + u'.ini')
			elif objType in ('Group', 'HostGroup', 'ObjectToGroup'):
				filename = os.path.join(self.__clientGroupsFile) #TODO: {'groupType': '___'}
		
		elif (fileType == 'pro'):
			pVer = u'_' + ident['productVersion'] + u'-' + ident['packageVersion']
			
			if objType == 'LocalbootProduct':
				filename = os.path.join(self.__productDir, ident['id'] + pVer + u'.localboot')
			elif objType == 'NetbootProduct':
				filename = os.path.join(self.__productDir, ident['id'] + pVer + u'.netboot')
			elif objType in ('Product', 'ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
				pId = None
				if objType == 'Product':
					pId = ident['id']
				else:
					pId = ident['productId']
				# instead of searching the whole dir, let's check the only possible files
				if os.path.isfile(os.path.join(self.__productDir, pId + pVer + u'.localboot')):
					filename = os.path.join(self.__productDir, pId + pVer + u'.localboot')
				elif os.path.isfile(os.path.join(self.__productDir, pId + pVer + u'.netboot')):
					filename = os.path.join(self.__productDir, pId + pVer + u'.netboot')
		
		elif (fileType == 'sw'):
			if objType == 'AuditSoftware':
				filename = os.path.join(self.__auditDir, u'global.sw')
			elif objType == 'AuditSoftwareOnClient':
				filename = os.path.join(self.__auditDir, ident['clientId'] + u'.sw')
		
		elif (fileType == 'hw'):
			if objType == 'AuditHardware':
				filename = os.path.join(self.__auditDir, u'global.hw')
			elif objType == 'AuditHardwareOnHost':
				filename = os.path.join(self.__auditDir, ident['hostId'] + u'.hw')
		
		if filename is None:
			raise Exception(u"No config-file returned! objType '%s', ident '%s', fileType '%s'" % (objType, ident, fileType))
		
		if objType in ('ConfigState', 'ProductOnDepot', 'ProductOnClient', 'ProductPropertyState'):
			if os.path.isfile(filename):
				return filename
			else:
				raise Exception(u"%s needs existing file '%s' ident '%s', fileType '%s'" % (objType, filename, ident, fileType))
		else:
			logger.debug2(u"Returning config file '%s'" % (filename))
			return filename
	
	def _getIdents(self, objType, **filter):
		logger.debug(u"Getting idents for '%s' with filter '%s'" % (objType, filter))
		objIdents = []
		
		if objType in ('Config', 'UnicodeConfig', 'BoolConfig'):
			filename = self._getConfigFile(objType, {}, 'ini')
			if os.path.isfile(filename):
				iniFile = IniFile(filename = filename, ignoreCase = False)
				cp = iniFile.parse()
				for section in cp.sections():
					objIdents.append({'id': section})
		
		elif objType in ('OpsiClient', 'ProductOnClient'):
			idFilter = {}
			if   objType in ('OpsiClient', ) and filter.get('id'):
				idFilter = { 'id': filter['id'] }
			elif objType in ('ProductOnClient', ) and filter.get('clientId'):
				idFilter = { 'id': filter['clientId'] }
			
			for entry in os.listdir(self.__clientConfigDir):
				if not entry.lower().endswith('.ini'):
					logger.debug2(u"Ignoring invalid client file '%s'" % (entry))
					continue
				
				try:
					hostId = forceHostId(entry[:-4])
				except:
					logger.warning(u"Ignoring invalid client file '%s'" % (entry))
					continue
				
				if idFilter and not self._objectHashMatches({'id': hostId}, **idFilter):
					continue
				
				if (objType == 'ProductOnClient'):
					filename = self._getConfigFile(objType, {'clientId': hostId}, 'ini')
					iniFile = IniFile(filename = filename, ignoreCase = False)
					cp = iniFile.parse()
					
					for section in cp.sections():
						if section.endswith('-state'):
							objIdents.append(
								{
								'productId':   section[:-6],
								'productType': cp.get(section, 'productType'),
								'clientId':    hostId
								}
							)
				else:
					objIdents.append({'id': hostId})
		
		elif objType in ('OpsiDepotserver', 'OpsiConfigserver', 'ProductOnDepot'):
			idFilter = {}
			if   objType in ('OpsiDepotserver', 'OpsiConfigserver') and filter.get('id'):
				idFilter = { 'id': filter['id'] }
			elif objType in ('ProductOnDepot',) and filter.get('depotId'):
				idFilter = { 'id': filter['depotId'] }
			
			for entry in os.listdir(self.__depotConfigDir):
				if not entry.lower().endswith('.ini'):
					logger.debug2(u"Ignoring invalid depot file '%s'" % (entry))
					continue
				
				try:
					hostId = forceHostId(entry[:-4])
				except:
					logger.warning(u"Ignoring invalid depot file '%s'" % (entry))
					continue
				
				if idFilter and not self._objectHashMatches({'id': hostId}, **idFilter):
					continue
				
				if (objType == 'OpsiConfigserver') and (hostId != self.__serverId):
					continue
				
				if (objType == 'ProductOnDepot'):
					filename = self._getConfigFile(objType, {'depotId': hostId}, 'ini')
					iniFile = IniFile(filename = filename, ignoreCase = False)
					cp = iniFile.parse()
					
					for section in cp.sections():
						if section.endswith('-state'):
							objIdents.append(
								{
								'productId':      section[:-6],
								'productType':    cp.get(section, 'producttype'),
								'productVersion': cp.get(section, 'productversion'),
								'packageVersion': cp.get(section, 'packageversion'),
								'depotId':        hostId
								}
							)
				else:
					objIdents.append({'id': hostId})
		
		elif objType in ('Product', 'LocalbootProduct', 'NetbootProduct', 'ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
			idFilter = {}
			if   objType in ('Product', 'LocalbootProduct', 'NetbootProduct') and filter.get('id'):
				idFilter = { 'id': filter['id'] }
			elif objType in ('ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency') and filter.get('productId'):
				idFilter = { 'id': filter['productId'] }
			
			for entry in os.listdir(self.__productDir):
				match = None
				
				entry = entry.lower()
				if (entry.endswith('.localboot')):
					if (objType == 'NetbootProduct'):
						continue
				elif (entry.endswith('.netboot')):
					if (objType == 'LocalbootProduct'):
						continue
				else:
					logger.debug2(u"Ignoring invalid product file '%s'" % (entry))
					continue
				
				match = self.productFilenameRegex.search(entry)
				if not match:
					logger.warning(u"Ignoring invalid product file '%s'" % (entry))
					continue
				
				if idFilter and not self._objectHashMatches({'id': match.group(1)}, **idFilter):
					continue
				
				logger.debug2(u"Found match: id='%s', productVersion='%s', packageVersion='%s'" \
					% (match.group(1), match.group(2), match.group(3)) )
				
				if objType in ('Product', 'LocalbootProduct', 'NetbootProduct'):
					objIdents.append({'id': match.group(1), 'productVersion': match.group(2), 'packageVersion': match.group(3)})
				
				elif objType in ('ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
					filename = os.path.join(self.__productDir, entry)
					packageControlFile = PackageControlFile(filename = filename)
					if (objType == 'ProductDependency'):
						for productDependency in packageControlFile.getProductDependencies():
							objIdents.append(productDependency.getIdent(returnType = 'dict'))
					else:
						for productProperty in packageControlFile.getProductProperties():
							objIdents.append(productProperty.getIdent(returnType = 'dict'))
		
		elif objType in ('ConfigState', 'ProductPropertyState'):
			for path in (self.__depotConfigDir, self.__clientConfigDir):
				for entry in os.listdir(path):
					filename = os.path.join(path, entry)
					
					if not entry.lower().endswith('.ini'):
						logger.debug2(u"Ignoring invalid file '%s'" % (filename))
						continue
					
					objectId = None
					try:
						objectId = forceHostId(entry[:-4])
					except Exception, e:
						logger.warning(u"Ignoring invalid file '%s': %s" % filename, e)
						continue
					
					if not self._objectHashMatches({'objectId': objectId }, **filter):
						continue
					
					iniFile = IniFile(filename = filename, ignoreCase = False)
					cp = iniFile.parse()
					
					if objType == 'ConfigState' and cp.has_section('generalconfig'):
						for option in cp.options('generalconfig'):
							objIdents.append(
								{
								'configId': option,
								'objectId': objectId
								}
							)
					elif objType == 'ProductPropertyState':
						for section in cp.sections():
							if not section.endswith('-install'):
								continue
							
							for option in cp.options(section):
								objIdents.append(
									{
									'productId':  section[:-8],
									'propertyId': option,
									'objectId':   objectId
									}
								)
		
		elif objType in ('Group', 'HostGroup', 'ObjectToGroup'):
			filename = self._getConfigFile(objType, {}, 'ini') #TODO: {'groupType': '___'}
			iniFile = IniFile(filename = filename, ignoreCase = False)
			cp = iniFile.parse()
			
			for section in cp.sections():
				if (objType == 'ObjectToGroup'):
					for option in cp.options(section):
						if option in ('description', 'notes', 'parentgroupid'):
							continue
						
						try:
							value = cp.get(section, option)
							if not forceBool(value):
								logger.debug(u"Skipping '%s' in section '%s' with False-value '%s'" \
									% (option, section, value))
								continue
							
							objIdents.append(
								{
								'groupType': u"HostGroup", #TODO: {'groupType': '___'}
								'groupId':  section,
								'objectId': forceHostId(option)
								}
							)
						except Exception, e:
							logger.error(u"Found invalid option '%s' in section '%s' in file '%s': %s" \
								% (option, section, filename, e))
				else:
					objIdents.append(
						{
							'id': section
						}
					)
		
		elif objType in ('AuditSoftware', 'AuditSoftwareOnClient', 'AuditHardware', 'AuditHardwareOnHost'):
			filenames = []
			
			fileType = 'sw'
			if objType in ('AuditHardware', 'AuditHardwareOnHost'):
				fileType = 'hw'
			
			if objType in ('AuditSoftware', 'AuditHardware'):
				filename = self._getConfigFile(objType, {}, fileType)
				if os.path.isfile(filename):
					filenames.append(filename)
			else:
				
					
				idFilter = {}
				if   objType in ('AuditSoftwareOnClient', ) and filter.get('clientId'):
					idFilter = { 'id': filter['clientId'] }
				elif objType in ('AuditHardwareOnHost', ) and filter.get('hostId'):
					idFilter = { 'id': filter['hostId'] }
				
				for entry in os.listdir(self.__auditDir):
					entry = entry.lower()
					filename = None
					
					if (entry == 'global.sw') or (entry == 'global.hw'):
						continue
					elif not entry.endswith('.%s' % fileType):
						logger.debug2(u"Ignoring invalid file '%s'" % (entry))
					
					try:
						if idFilter and not self._objectHashMatches({'id': forceHostId(entry[:-3])}, **idFilter):
							continue
					except:
						logger.warning(u"Ignoring invalid file '%s'" % (entry))
						continue
					
					filenames.append(os.path.join(self.__auditDir, entry))
			
			for filename in filenames:
				iniFile = IniFile(filename = filename)
				cp = iniFile.parse()
				
				for section in cp.sections():
					objIdent = {}
					
					if objType in ('AuditSoftware', 'AuditSoftwareOnClient'):
						objIdent = {
							'name' :        None,
							'version' :     None,
							'subVersion' :  None,
							'language' :    None,
							'architecture': None
							}
						for key in objIdent.keys():
							option = key.lower()
							if cp.has_option(section, option):
								objIdent[key] = self.__unescape(cp.get(section, option))
						
						if (objType == 'AuditSoftwareOnClient'):
							objIdent['clientId'] = os.path.basename(filename)[:-3]
					else:
						for (key, value) in cp.items(section):
							objIdent[str(key)] = self.__unescape(value)
						
						if (objType == 'AuditHardwareOnHost'):
							objIdent['hostId'] = os.path.basename(filename)[:-3]
					
					objIdents.append(objIdent)
		
		else:
			logger.warning(u"Unhandled objType '%s'" % objType)
		
		if not objIdents:
			logger.debug2(u"Could not retrieve any idents, returning empty list." % ())
			return []
		
		needFilter = False
		for attribute in objIdents[0].keys():
			if filter.get(attribute):
				needFilter = True
				break
		
		if not needFilter:
			logger.debug2(u"Returning idents without filter." % ())
			return objIdents
		
		filteredObjIdents = []
		for ident in objIdents:
			if self._objectHashMatches(ident, **filter):
				filteredObjIdents.append(ident)
		
		logger.debug2(u"Returning filtered idents." % ())
		return filteredObjIdents
	
	def _adaptObjectHashAttributes(self, objHash, ident, attributes):
		logger.debug2(u"Adapting objectHash with '%s', '%s', '%s'" % (objHash, ident, attributes))
		if not attributes:
			return objHash
		for attribute in objHash.keys():
			if not attribute in attributes and not attribute in ident.keys():
				del objHash[attribute]
		return objHash
	
	def _read(self, objType, attributes, **filter):
		if (objType == 'Group'): objType = 'HostGroup' #TODO: zwischen den einzelnen gruppen unterscheiden ...
		
		if filter.get('type'):
			match = False
			for objectType in forceList(filter['type']):
				if (objectType == objType):
					match = True
					break
				Class = eval(objectType)
				for subClass in Class.subClasses:
					if (subClass == objType):
						match = True
						break
				if match:
					break
			
			if not match:
				logger.debug2(u"Object type '%s' does not match filter %s" % (objType, filter))
				return []
		if not self._mappings.has_key(objType):
			raise Exception(u"Mapping not found for object type '%s'" % objType)
		
		logger.debug2(u"Now reading '%s' with:" % (objType))
		logger.debug2(u"   Attributes: '%s'" % (attributes))
		logger.debug2(u"   Filter: '%s'" % (filter))
		
		mappings = {}
		for mapping in self._mappings[objType]:
			if (not attributes or mapping['attribute'] in attributes) or mapping['attribute'] in filter.keys():
				if not mappings.has_key(mapping['fileType']):
					mappings[mapping['fileType']] = []
				
				mappings[mapping['fileType']].append(mapping)
		
		logger.debug2(u"Using mappings %s" % mappings)
		
		packageControlFileCache = {}
		iniFileCache = {}
		hostKeys = None
		
		objects = []
		for ident in self._getIdents(objType, **filter):
			ignoreHash = False
			objHash = dict(ident)
			
			for (fileType, mapping) in mappings.items():
				filename = self._getConfigFile(objType, ident, fileType)
				
				if not os.path.exists(os.path.dirname(filename)):
					raise BackendIOError(u"Directory '%s' not found" % os.path.dirname(filename))
				
				if (fileType == 'key'):
					if not hostKeys:
						hostKeys = HostKeyFile(filename = filename)
						hostKeys.parse()
					for m in mapping:
						objHash[m['attribute']] = hostKeys.getOpsiHostKey(ident['id'])
				
				elif (fileType == 'ini'):
					if not iniFileCache.has_key(filename):
						iniFile = IniFile(filename = filename, ignoreCase = False)
						iniFileCache[filename] = iniFile.parse()
					cp = iniFileCache[filename]
					
					if cp.has_section('LocalbootProduct_product_states') or cp.has_section('NetbootProduct_product_states'):
						if cp.has_section('LocalbootProduct_product_states'):
							if not cp.has_section('localboot_product_states'):
								cp.add_section('localboot_product_states')
							for (k, v) in cp.items('LocalbootProduct_product_states'):
								cp.set('localboot_product_states', k, v)
							cp.remove_section('LocalbootProduct_product_states')
						if cp.has_section('NetbootProduct_product_states'):
							if not cp.has_section('netboot_product_states'):
								cp.add_section('netboot_product_states')
							for (k, v) in cp.items('NetbootProduct_product_states'):
								cp.set('netboot_product_states', k, v)
							cp.remove_section('NetbootProduct_product_states')
						IniFile(filename = filename, ignoreCase = False).generate(cp)
						
					for m in mapping:
						attribute = m['attribute']
						section = m['section']
						option = m['option']
						
						match = self._placeholderRegex.search(section)
						if match:
							section = u'%s%s%s' % (match.group(1), objHash[match.group(2)], match.group(3))
							if (objType == 'ProductOnClient'): #<productType>_product_states
								section = section.replace('LocalbootProduct', 'localboot').replace('NetbootProduct', 'netboot')
						
						match = self._placeholderRegex.search(option)
						if match:
							option = u'%s%s%s' % (match.group(1), objHash[match.group(2)], match.group(3))
						
						if cp.has_option(section, option):
							value = cp.get(section, option)
							if m.get('json'):
								value = fromJson(value)
							elif ( isinstance(value, str) or isinstance(value, unicode) ):
								value = self.__unescape(value)
							
							# invalid values will throw exceptions later
							if (objType == 'ProductOnClient') and (section.endswith('_product_states')):
								index = value.find(':')
								if (index == -1):
									raise Exception(u"No ':' found in section '%s' in option '%s' in '%s'" % (section, option, filename))
								if attribute == 'installationStatus':
									#value = value.split(u':', 1)[0]
									value = value[:index]
								elif attribute == 'actionRequest':
									#value = value.split(u':', 1)[1]
									value = value[index + 1:]
							
							objHash[attribute] = value
						
						elif (objType == 'ProductOnClient') and (attribute.lower() == 'installationstatus'):
							objHash[attribute] = 'not_installed'
						elif (objType == 'ProductOnClient') and (attribute.lower() == 'actionrequest'):
							objHash[attribute] = 'none'
							
					logger.debug2(u"Got object hash from ini file: %s" % objHash)
					
				elif (fileType == 'pro'):
					if not packageControlFileCache.has_key(filename):
						packageControlFileCache[filename] = PackageControlFile(filename = filename)
						packageControlFileCache[filename].parse()
					packageControlFile = packageControlFileCache[filename]
					
					if   objType in ('Product', 'LocalbootProduct', 'NetbootProduct'):
						objHash = packageControlFile.getProduct().toHash()
					
					elif objType in ('ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
						knownObjects = []
						if objType in ('ProductDependency',):
							knownObjects = packageControlFile.getProductDependencies()
						else:
							knownObjects = packageControlFile.getProductProperties()
						
						for obj in knownObjects:
							objIdent = obj.getIdent(returnType = 'dict')
							matches = True
							for (key, value) in ident.items():
								if (objIdent[key] != value):
									matches = False
									break
							if matches:
								objHash = obj.toHash()
								break
			
			Class = eval(objType)
			if self._objectHashMatches(Class.fromHash(objHash).toHash(), **filter):
				objHash = self._adaptObjectHashAttributes(objHash, ident, attributes)
				objects.append(Class.fromHash(objHash))
		
		for obj in objects:
			logger.debug2(u"Returning object: %s" % obj.getIdent())
		
		return objects
	
	def _write(self, obj, mode='create'):
		objType = obj.getType()
		
		if (objType == 'OpsiConfigserver'):
			if (self.__serverId != obj.getId()):
				raise Exception(u"Filebackend can only handle this config server '%s', not '%s'" \
					% (self.__serverId, obj.getId()))
		
		if not self._mappings.has_key(objType):
			raise Exception(u"Mapping not found for object type '%s'" % objType)
		
		mappings = {}
		for mapping in self._mappings[objType]:
			if not mappings.has_key(mapping['fileType']):
				mappings[mapping['fileType']] = {}
			mappings[mapping['fileType']][mapping['attribute']] = mapping
		
		for (fileType, mapping) in mappings.items():
			filename = self._getConfigFile(objType, obj.getIdent(returnType = 'dict'), fileType)
			
			if (fileType == 'key'):
				if (mode == 'create') or (mode == 'update' and obj.getOpsiHostKey()):
					if not os.path.exists(filename):
						self._touch(filename)
					hostKeys = HostKeyFile(filename = filename)
					hostKeys.setOpsiHostKey(obj.getId(), obj.getOpsiHostKey())
					hostKeys.generate()
			
			elif (fileType == 'ini'):
				iniFile = IniFile(filename = filename, ignoreCase = False)
				if (mode == 'create'):
					if objType in ('OpsiClient',) and not iniFile.exists():
						proto = os.path.join(self.__clientTemplateDir, os.path.basename(filename))
						if not os.path.isfile(proto):
							proto = self.__defaultClientTemplatePath
						shutil.copyfile(proto, filename)
					
					self._touch(filename)
				
				cp = iniFile.parse()
				
				if (mode == 'create'):
					removeSections = []
					if objType in ('OpsiClient', 'OpsiDepotserver', 'OpsiConfigserver'):
						removeSections = ['info', 'depotshare', 'repository']
					elif   objType in ('Config', 'UnicodeConfig', 'BoolConfig', 'Group', 'HostGroup'):
						removeSections = [obj.getId()]
					elif objType in ('ProductOnDepot', 'ProductOnClient'):
						removeSections = [obj.getProductId() + u'-state']
					elif objType in ('ProductPropertyState',):
						removeSections = [obj.getPropertyId() + u'-install']
					
					for section in removeSections:
						if cp.has_section(section):
							cp.remove_section(section)
				
				objHash = obj.toHash()
				
				for (attribute, value) in objHash.items():
					if value is None and (mode == 'update'):
						continue
					
					attributeMapping = mapping.get(attribute, mapping.get('*'))
					
					if not attributeMapping is None:
						section = attributeMapping['section']
						option = attributeMapping['option']
						
						match = self._placeholderRegex.search(section)
						if match:
							section = u'%s%s%s' % (match.group(1), objHash[match.group(2)], match.group(3))
							if objType in ('ProductOnClient',):
								section = section.replace('LocalbootProduct', 'localboot').replace('NetbootProduct', 'netboot')
						
						match = self._placeholderRegex.search(option)
						if match:
							option = u'%s%s%s' % (match.group(1), objHash[match.group(2)], match.group(3))
						
						if objType in ('ProductOnClient',):
							if attribute in ('installationStatus', 'actionRequest'):
								(installationStatus, actionRequest) = (u'not_installed', u'none')
								combined = u''
								if cp.has_option(section, option):
									combined = cp.get(section, option)
								if (combined.find(u':') != -1):
									(installationStatus, actionRequest) = combined.split(u':', 1)
								elif combined:
									installationStatus = combined
								if not value is None:
									if   (attribute == 'installationStatus'):
										installationStatus = value
									elif (attribute == 'actionRequest'):
										actionRequest = value
								value = installationStatus + u':' + actionRequest
						elif objType in ('ObjectToGroup',):
							value = 1
						
						if not value is None:
							if attributeMapping.get('json'):
								value = toJson(value)
							elif ( isinstance(value, str) or isinstance(value, unicode) ):
								value = self.__escape(value)
							
							
							if not cp.has_section(section):
								cp.add_section(section)
							
							cp.set(section, option, value)
				
				iniFile.setSectionSequence(['info', 'generalconfig', 'localboot_product_states', 'netboot_product_states'])
				iniFile.generate(cp)
			
			elif (fileType == 'pro'):
				if not os.path.exists(filename):
					self._touch(filename)
				packageControlFile = PackageControlFile(filename = filename)
				
				if objType in ('Product', 'LocalbootProduct', 'NetbootProduct'):
					if (mode == 'create'):
						packageControlFile.setProduct(obj)
					else:
						productHash = packageControlFile.getProduct().toHash()
						for (attribute, value) in obj.toHash().items():
							if value is None:
								continue
							productHash[attribute] = value
						packageControlFile.setProduct(Product.fromHash(productHash))
				
				elif objType in ('ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
					currentObjects = []
					if (objType == 'ProductDependency'):
						currentObjects = packageControlFile.getProductDependencies()
					else:
						currentObjects = packageControlFile.getProductProperties()
					
					found = False
					for i in range(len(currentObjects)):
						if (currentObjects[i].getIdent(returnType = 'unicode') == obj.getIdent(returnType = 'unicode')):
							if (mode == 'create'):
								currentObjects[i] = obj
							else:
								newHash = currentObjects[i].toHash()
								for (attribute, value) in obj.toHash().items():
									if value is not None:
										newHash[attribute] = value
								
								Class = eval(objType)
								currentObjects[i] = Class.fromHash(newHash)
							found = True
							break
					
					if not found:
						currentObjects.append(obj)
						
					if (objType == 'ProductDependency'):
						packageControlFile.setProductDependencies(currentObjects)
					else:
						packageControlFile.setProductProperties(currentObjects)
					
				packageControlFile.generate()
	
	def _delete(self, objList):
		if not objList:
			return
	
		#objType is not always correct, but _getConfigFile() is
		#within ifs obj.getType() from obj in objList should be used
		objType = objList[0].getType()
		
		if objType in ('OpsiClient', 'OpsiConfigserver', 'OpsiDepotserver'):
			hostKeyFile = HostKeyFile(self._getConfigFile('', {}, 'key'))
			for obj in objList:
				if (obj.getId() == self.__serverId):
					logger.warning(u"Cannot delete %s '%s', ignored." % (obj.getType(), obj.getId()))
					continue
				
				logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
				hostKeyFile.deleteOpsiHostKey(obj.getId())
				
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'ini')
				if os.path.isfile(filename):
					os.unlink(filename)
			hostKeyFile.generate()
		
		elif objType in ('Config', 'UnicodeConfig', 'BoolConfig'):
			filename = self._getConfigFile(objType, {}, 'ini')
			iniFile = IniFile(filename = filename, ignoreCase = False)
			cp = iniFile.parse()
			for obj in objList:
				logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
				if cp.has_section(obj.getId()):
					cp.remove_section(obj.getId())
					logger.debug2(u"Removed section '%s'" % obj.getId())
			iniFile.generate(cp)
		
		elif objType in ('ConfigState',):
			filenames = []
			for obj in objList:
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'ini')
				if not filename in filenames:
					filenames.append(filename)
				
			for filename in filenames:
				iniFile = IniFile(filename = filename, ignoreCase = False)
				cp = iniFile.parse()
				for obj in objList:
					if not (obj.getObjectId() == os.path.basename(filename)[:-4]):
						continue
					
					logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
					if cp.has_option('generalconfig', obj.getConfigId()):
						cp.remove_option('generalconfig', obj.getConfigId())
						logger.debug2(u"Removed option in generalconfig '%s'" % obj.getConfigId())
				
				iniFile.generate(cp)
		
		elif objType in ('Product', 'LocalbootProduct', 'NetbootProduct'):
			for obj in objList:
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'pro' )
				logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
				if os.path.isfile(filename):
					os.unlink(filename)
					logger.debug2(u"Removed file '%s'" % filename)
		
		elif objType in ('ProductProperty', 'UnicodeProductProperty', 'BoolProductProperty', 'ProductDependency'):
			filenames = []
			for obj in objList:
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'pro')
				if not filename in filenames:
					filenames.append(filename)
			
			for filename in filenames:
				packageControlFile = PackageControlFile(filename = filename)
				newList = []
				oldList = []
				
				if objType == 'ProductDependency':
					oldList = packageControlFile.getProductDependencies()
				else:
					oldList = packageControlFile.getProductProperties()
				
				for oldItem in oldList:
					delete = False
					for obj in objList:
						if oldItem.getIdent(returnType = 'unicode') == obj.getIdent(returnType = 'unicode'):
							delete = True
							break
					if delete:
						logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
					else:
						newList.append(oldItem)
				
				if objType == 'ProductDependency':
					packageControlFile.setProductDependencies(newList)
				else:
					packageControlFile.setProductProperties(newList)
				
				packageControlFile.generate()
		
		elif objType in ('ProductOnDepot', 'ProductOnClient'):
			filenames = []
			for obj in objList:
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'ini')
				
				inFilenames = False
				for f in filenames:
					if filename == f:
						inFilenames = True
						break
				
				if not inFilenames:
					filenames.append(filename)
			
			for filename in filenames:
				iniFile = IniFile(filename = filename, ignoreCase = False)
				cp = iniFile.parse()
				
				for obj in objList:
					logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
					if cp.has_section(obj.getProductId() + '-state'):
						cp.remove_section(obj.getProductId() + '-state')
						logger.debug2(u"Removed section '%s'" % obj.getProductId() + '-state')
				
				iniFile.generate(cp)
		
		elif objType in ('ProductPropertyState',):
			for obj in objList:
				logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
				filename = self._getConfigFile(
					obj.getType(), obj.getIdent(returnType = 'dict'), 'ini')
				iniFile = IniFile(filename = filename, ignoreCase = False)
				cp = iniFile.parse()
				
				section = obj.getProductId() + '-install'
				option = obj.getPropertyId()
				
				if cp.has_option(section, option):
					cp.remove_option(section, option)
					logger.debug2(u"Removed option '%s' in section '%s'" % (option, section))
				
				if (cp.has_section(section)) and (len(cp.options(section)) == 0):
					cp.remove_section(section)
					logger.debug2(u"Removed empty section '%s'" % section)
				
				iniFile.generate(cp)
		
		elif objType in ('Group', 'HostGroup', 'ObjectToGroup'):
			filename = self._getConfigFile(objType, {}, 'ini')
			iniFile = IniFile(filename = filename, ignoreCase = False)
			cp = iniFile.parse()
			
			for obj in objList:
				section = None
				if (obj.getType() == 'ObjectToGroup'):
					if (obj.groupType != 'HostGroup'):
						raise BackendBadValueError(u"Unhandled group type '%s'" % obj.groupType)
					section = obj.getGroupId()
				else:
					section = obj.getId()
				
				logger.debug(u"Deleting %s: '%s'" % (obj.getType(), obj.getIdent()))
				if (obj.getType() == 'ObjectToGroup'):
					if cp.has_option(section, obj.getObjectId()):
						cp.remove_option(section, obj.getObjectId())
						logger.debug2(u"Removed option '%s' in section '%s'" \
							% (obj.getObjectId(), section))
				else:
					if cp.has_section(section):
						cp.remove_section(section)
						logger.debug2(u"Removed section '%s'" % section)
			
			iniFile.generate(cp)
		
		else:
			logger.warning(u"_delete(): unhandled objType: '%s' object: %s" % (objType, objList[0]))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_insertObject(self, host):
		host = forceObjectClass(host, Host)
		ConfigDataBackend.host_insertObject(self, host)
		
		logger.debug(u"Inserting host: '%s'" % host.getIdent())
		self._write(host, mode = 'create')
	
	def host_updateObject(self, host):
		host = forceObjectClass(host, Host)
		ConfigDataBackend.host_updateObject(self, host)
		
		logger.debug(u"Updating host: '%s'" % host.getIdent())
		self._write(host, mode = 'update')
	
	def host_getObjects(self, attributes = [], **filter):
		ConfigDataBackend.host_getObjects(self, attributes, **filter)
		
		logger.debug(u"Getting hosts ...")
		result = self._read('OpsiDepotserver', attributes, **filter)
		opsiConfigServers = self._read('OpsiConfigserver', attributes, **filter)
		
		if opsiConfigServers:
			contained = False
			for i in range(len(result)):
				if (result[i].getId() == opsiConfigServers[0].getId()):
					result[i] = opsiConfigServers[0]
					contained = True
					break
			
			if not contained:
				result.append(opsiConfigServers[0])
		result.extend(self._read('OpsiClient', attributes, **filter))
		
		return result
	
	def host_deleteObjects(self, hosts):
		ConfigDataBackend.host_deleteObjects(self, hosts)
		
		logger.debug(u"Deleting hosts ...")
		self._delete(forceObjectClassList(hosts, Host))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config):
		config = forceObjectClass(config, Config)
		ConfigDataBackend.config_insertObject(self, config)
		
		logger.debug(u"Inserting config: '%s'" % config.getIdent())
		self._write(config, mode = 'create')
	
	def config_updateObject(self, config):
		config = forceObjectClass(config, Config)
		ConfigDataBackend.config_updateObject(self, config)
		
		logger.debug(u"Updating config: '%s'" % config.getIdent())
		self._write(config, mode = 'update')
	
	def config_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.config_getObjects(self, attributes, **filter)
		
		logger.debug(u"Getting configs ...")
		result = self._read('Config', attributes, **filter)
		
		return result
	
	def config_deleteObjects(self, configs):
		ConfigDataBackend.config_deleteObjects(self, configs)
		
		logger.debug(u"Deleting configs ...")
		self._delete(forceObjectClassList(configs, Config))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)
		ConfigDataBackend.configState_insertObject(self, configState)
		
		logger.debug(u"Inserting configState: '%s'" % configState.getIdent())
		self._write(configState, mode = 'create')
	
	def configState_updateObject(self, configState):
		configState = forceObjectClass(configState, ConfigState)
		ConfigDataBackend.configState_updateObject(self, configState)
		
		logger.debug(u"Updating configState: '%s'" % configState.getIdent())
		self._write(configState, mode = 'update')
	
	def configState_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.configState_getObjects(self, attributes, **filter)
		
		logger.debug(u"Getting configStates ...")
		result = self._read('ConfigState', attributes, **filter)
		
		return result
	
	def configState_deleteObjects(self, configStates):
		ConfigDataBackend.configState_deleteObjects(self, configStates)
		
		logger.debug(u"Deleting configStates ...")
		self._delete(forceObjectClassList(configStates, ConfigState))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product):
		product = forceObjectClass(product, Product)
		ConfigDataBackend.product_insertObject(self, product)
		
		logger.debug(u"Inserting product: '%s'" % product.getIdent())
		self._write(product, mode = 'create')
	
	def product_updateObject(self, product):
		product = forceObjectClass(product, Product)
		ConfigDataBackend.product_updateObject(self, product)
		
		logger.debug(u"Updating product: '%s'" % product.getIdent())
		self._write(product, mode = 'update')
	
	def product_getObjects(self, attributes = [], **filter):
		ConfigDataBackend.product_getObjects(self, attributes, **filter)
		
		logger.debug(u"Getting products ...")
		result = self._read('LocalbootProduct', attributes, **filter)
		result.extend(self._read('NetbootProduct', attributes, **filter))
		
		return result
	
	def product_deleteObjects(self, products):
		ConfigDataBackend.product_deleteObjects(self, products)
		
		logger.debug(u"Deleting products ...")
		self._delete(forceObjectClassList(products, Product))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)
		ConfigDataBackend.productProperty_insertObject(self, productProperty)
		
		logger.debug(u"Inserting productProperty: '%s'" % productProperty.getIdent())
		self._write(productProperty, mode = 'create')
	
	def productProperty_updateObject(self, productProperty):
		productProperty = forceObjectClass(productProperty, ProductProperty)
		ConfigDataBackend.productProperty_updateObject(self, productProperty)
		
		logger.debug(u"Updating productProperty: '%s'" % productProperty.getIdent())
		self._write(productProperty, mode = 'update')
	
	def productProperty_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productProperty_getObjects(self, attributes, **filter)
		
		logger.debug(u"Getting productProperties ...")
		result = self._read('ProductProperty', attributes, **filter)
		
		return result
	
	def productProperty_deleteObjects(self, productProperties):
		ConfigDataBackend.productProperty_deleteObjects(self, productProperties)
		
		logger.debug(u"Deleting productProperties ...")
		self._delete(forceObjectClassList(productProperties, ProductProperty))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)
		ConfigDataBackend.productDependency_insertObject(self, productDependency)
		
		logger.debug(u"Inserting productDependency: '%s'" % productDependency.getIdent())
		self._write(productDependency, mode = 'create')
	
	def productDependency_updateObject(self, productDependency):
		productDependency = forceObjectClass(productDependency, ProductDependency)
		ConfigDataBackend.productDependency_updateObject(self, productDependency)
		
		logger.debug(u"Updating productDependency: '%s'" % productDependency.getIdent())
		self._write(productDependency, mode = 'update')
	
	def productDependency_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productDependency_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting productDependencies ...")
		result = self._read('ProductDependency', attributes, **filter)
		
		return result
	
	def productDependency_deleteObjects(self, productDependencies):
		ConfigDataBackend.productDependency_deleteObjects(self, productDependencies)
		
		logger.debug(u"Deleting productDependencies ...")
		self._delete(forceObjectClassList(productDependencies, ProductDependency))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		ConfigDataBackend.productOnDepot_insertObject(self, productOnDepot)
		
		logger.debug(u"Inserting productOnDepot: '%s'" % productOnDepot.getIdent())
		self._write(productOnDepot, mode = 'create')
	
	def productOnDepot_updateObject(self, productOnDepot):
		productOnDepot = forceObjectClass(productOnDepot, ProductOnDepot)
		ConfigDataBackend.productOnDepot_updateObject(self, productOnDepot)
		
		logger.debug(u"Updating productOnDepot: '%s'" % productOnDepot.getIdent())
		self._write(productOnDepot, mode = 'update')
	
	def productOnDepot_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productOnDepot_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting productOnDepots ...")
		result = self._read('ProductOnDepot', attributes, **filter)
		
		return result
	
	def productOnDepot_deleteObjects(self, productOnDepots):
		ConfigDataBackend.productOnDepot_deleteObjects(self, productOnDepots)
		
		logger.debug(u"Deleting productOnDepots ...")
		self._delete(forceObjectClassList(productOnDepots, ProductOnDepot))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		ConfigDataBackend.productOnClient_insertObject(self, productOnClient)
		
		logger.debug(u"Inserting productOnClient: '%s'" % productOnClient.getIdent())
		self._write(productOnClient, mode = 'create')
	
	def productOnClient_updateObject(self, productOnClient):
		productOnClient = forceObjectClass(productOnClient, ProductOnClient)
		ConfigDataBackend.productOnClient_updateObject(self, productOnClient)
		
		logger.debug(u"Updating productOnClient: '%s'" % productOnClient.getIdent())
		self._write(productOnClient, mode = 'update')
	
	def productOnClient_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productOnClient_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting productOnClient ...")
		result = self._read('ProductOnClient', attributes, **filter)
		
		return result
	
	def productOnClient_deleteObjects(self, productOnClients):
		ConfigDataBackend.productOnClient_deleteObjects(self, productOnClients)
		
		logger.debug(u"Deleting productOnClients ...")
		self._delete(forceObjectClassList(productOnClients, ProductOnClient))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(self, productPropertyState):
		productPropertyState = forceObjectClass(productPropertyState, ProductPropertyState)
		ConfigDataBackend.productPropertyState_insertObject(self, productPropertyState)
		
		logger.debug(u"Inserting productPropertyState: '%s'" % productPropertyState.getIdent())
		self._write(productPropertyState, mode = 'create')
	
	def productPropertyState_updateObject(self, productPropertyState):
		productPropertyState = forceObjectClass(productPropertyState, ProductPropertyState)
		ConfigDataBackend.productPropertyState_updateObject(self, productPropertyState)
		
		logger.debug(u"Updating productPropertyState: '%s'" % productPropertyState.getIdent())
		self._write(productPropertyState, mode = 'update')
	
	def productPropertyState_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.productPropertyState_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting productPropertyStates ...")
		result = self._read('ProductPropertyState', attributes, **filter)
		
		return result
	
	def productPropertyState_deleteObjects(self, productPropertyStates):
		ConfigDataBackend.productPropertyState_deleteObjects(self, productPropertyStates)
		
		logger.debug(u"Deleting productPropertyStates ...")
		self._delete(forceObjectClassList(productPropertyStates, ProductPropertyState))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group):
		group = forceObjectClass(group, Group)
		ConfigDataBackend.group_insertObject(self, group)
		
		logger.debug(u"Inserting group: '%s'" % group.getIdent())
		self._write(group, mode = 'create')
	
	def group_updateObject(self, group):
		group = forceObjectClass(group, Group)
		ConfigDataBackend.group_updateObject(self, group)
		
		logger.debug(u"Updating group: '%s'" % group.getIdent())
		self._write(group, mode = 'update')
	
	def group_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.group_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting groups ...")
		result = self._read('Group', attributes, **filter)
		
		return result
	
	def group_deleteObjects(self, groups):
		ConfigDataBackend.group_deleteObjects(self, groups)
		
		logger.debug(u"Deleting groups ...")
		self._delete(forceObjectClassList(groups, Group))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		ConfigDataBackend.objectToGroup_insertObject(self, objectToGroup)
		
		logger.debug(u"Inserting objectToGroup: '%s'" % objectToGroup.getIdent())
		self._write(objectToGroup, mode = 'create')
	
	def objectToGroup_updateObject(self, objectToGroup):
		objectToGroup = forceObjectClass(objectToGroup, ObjectToGroup)
		ConfigDataBackend.objectToGroup_updateObject(self, objectToGroup)
		
		logger.debug(u"Updating objectToGroup: '%s'" % objectToGroup.getIdent())
		self._write(objectToGroup, mode = 'update')
	
	def objectToGroup_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.objectToGroup_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting objectToGroups ...")
		result = self._read('ObjectToGroup', attributes, **filter)
		
		return result
	
	def objectToGroup_deleteObjects(self, objectToGroups):
		ConfigDataBackend.objectToGroup_deleteObjects(self, objectToGroups)
		
		logger.debug(u"Deleting objectToGroups ...")
		self._delete(forceObjectClassList(objectToGroups, ObjectToGroup))
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_insertObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		ConfigDataBackend.auditSoftware_insertObject(self, auditSoftware)
		
		logger.debug(u"Inserting auditSoftware: '%s'" % auditSoftware.getIdent())
		filename = self._getConfigFile('AuditSoftware', {}, 'sw')
		
		if not os.path.exists(filename):
			self._touch(filename)
		
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		
		auditSoftware = auditSoftware.toHash()
		for attribute in auditSoftware.keys():
			if (auditSoftware[attribute] is None) or (attribute == 'type'):
				continue
			auditSoftware[attribute] = self.__escape(auditSoftware[attribute])
		
		newNum = 0
		removeSection = None
		for section in ini.sections():
			num = int(section.split('_')[-1])
			if (num >= newNum):
				newNum = num + 1
			
			matches = True
			for attribute in ('name', 'version', 'subVersion', 'language', 'architecture'):
				if not ini.has_option(section, attribute):
					if not auditSoftware[attribute] is None:
						matches = False
						break
				elif (ini.get(section, attribute) != auditSoftware[attribute]):
					matches = False
					break
			if matches:
				removeSection = section
				newNum = num
				logger.debug(u"Found auditSoftware section '%s' to replace" % removeSection)
				break
			
		section = u'software_%d' % newNum
		if removeSection:
			ini.remove_section(removeSection)
		else:
			logger.debug(u"Inserting new auditSoftware section '%s'" % section)
		
		ini.add_section(section)
		for (attribute, value) in auditSoftware.items():
			if (value is None) or (attribute == 'type'):
				continue
			ini.set(section, attribute, value)
		iniFile.generate(ini)
		
	def auditSoftware_updateObject(self, auditSoftware):
		auditSoftware = forceObjectClass(auditSoftware, AuditSoftware)
		ConfigDataBackend.auditSoftware_updateObject(self, auditSoftware)
		
		logger.debug(u"Updating auditSoftware: '%s'" % auditSoftware.getIdent())
		filename = self._getConfigFile('AuditSoftware', {}, 'sw')
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		ident = auditSoftware.getIdent(returnType = 'dict')
		
		for section in ini.sections():
			found = True
			for (key, value) in ident.items():
				if (self.__unescape(ini.get(section, key.lower())) != value):
					found = False
					break
			if found:
				for (key, value) in auditSoftware.toHash().items():
					if value is None:
						continue
					ini.set(section, key, self.__escape(value))
				iniFile.generate(ini)
				return
		raise Exception(u"AuditSoftware %s not found" % auditSoftware)
		
	def auditSoftware_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditSoftware_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting auditSoftwares ...")
		result = []
		filename = self._getConfigFile('AuditSoftware', {}, 'sw')
		if not os.path.exists(filename):
			return result
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		fastFilter = {}
		if filter:
			for (attribute, value) in filter.items():
				if attribute in ("name", "version", "subVersion", "language", "architecture") and value:
					value = forceUnicodeList(value)
					if (len(value) == 1) and (value[0].find('*') == -1):
						fastFilter[attribute] = value[0]
		for section in ini.sections():
			objHash = {
				"name":                  None,
				"version":               None,
				"subVersion":            None,
				"language":              None,
				"architecture":          None,
				"windowsSoftwareId":     None,
				"windowsDisplayName":    None,
				"windowsDisplayVersion": None,
				"installSize":           None
			}
			fastFiltered = False
			for (key, value) in objHash.items():
				try:
					value = self.__unescape(ini.get(section, key.lower()))
					if fastFilter and value and fastFilter.has_key(key) and (fastFilter[key] != value):
						fastFiltered = True
						break
					objHash[key] = value
				except:
					pass
			if not fastFiltered and self._objectHashMatches(objHash, **filter):
				#TODO: adaptObjHash?
				result.append(AuditSoftware.fromHash(objHash))
		
		return result
	
	def auditSoftware_deleteObjects(self, auditSoftwares):
		ConfigDataBackend.auditSoftware_deleteObjects(self, auditSoftwares)
		
		logger.debug(u"Deleting auditSoftwares ...")
		filename = self._getConfigFile('AuditSoftware', {}, 'sw')
		if not os.path.exists(filename):
			return
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		idents = []
		for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware):
			idents.append(auditSoftware.getIdent(returnType = 'dict'))
		
		removeSections = []
		for section in ini.sections():
			for ident in idents:
				found = True
				for (key, value) in ident.items():
					if (self.__unescape(ini.get(section, key.lower())) != value):
						found = False
						break
				if found and not section in removeSections:
					removeSections.append(section)
		if removeSections:
			for section in removeSections:
				ini.remove_section(section)
			iniFile.generate(ini)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(auditSoftwareOnClient, AuditSoftwareOnClient)
		ConfigDataBackend.auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient)
		
		logger.debug(u"Inserting auditSoftwareOnClient: '%s'" % auditSoftwareOnClient.getIdent())
		filename = self._getConfigFile('AuditSoftwareOnClient', {"clientId": auditSoftwareOnClient.clientId }, 'sw')
		
		if not os.path.exists(filename):
			self._touch(filename)
		
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		
		auditSoftwareOnClient = auditSoftwareOnClient.toHash()
		for attribute in auditSoftwareOnClient.keys():
			if (auditSoftwareOnClient[attribute] is None):
				continue
			auditSoftwareOnClient[attribute] = self.__escape(auditSoftwareOnClient[attribute])
		newNum = 0
		removeSection = None
		for section in ini.sections():
			num = int(section.split('_')[-1])
			if (num >= newNum):
				newNum = num + 1
			
			matches = True
			for attribute in ('name', 'version', 'subVersion', 'language', 'architecture'):
				if not ini.has_option(section, attribute):
					if not auditSoftwareOnClient[attribute] is None:
						matches = False
						break
				elif (ini.get(section, attribute) != auditSoftwareOnClient[attribute]):
					matches = False
					break
			if matches:
				removeSection = section
				newNum = num
				logger.debug(u"Found auditSoftwareOnClient section '%s' to replace" % removeSection)
				break
			
		section = u'software_%d' % newNum
		if removeSection:
			ini.remove_section(removeSection)
		else:
			logger.debug(u"Inserting new auditSoftwareOnClient section '%s'" % section)
		
		ini.add_section(section)
		for (attribute, value) in auditSoftwareOnClient.items():
			if (value is None):
				continue
			ini.set(section, attribute, value)
		iniFile.generate(ini)
	
	def auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient):
		auditSoftwareOnClient = forceObjectClass(auditSoftwareOnClient, AuditSoftwareOnClient)
		ConfigDataBackend.auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient)
		
		logger.debug(u"Updating auditSoftwareOnClient: '%s'" % auditSoftwareOnClient.getIdent())
		filename = self._getConfigFile('AuditSoftwareOnClient', {"clientId": auditSoftwareOnClient.clientId }, 'sw')
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		ident = auditSoftwareOnClient.getIdent(returnType = 'dict')
		
		for section in ini.sections():
			found = True
			for (key, value) in ident.items():
				if (self.__unescape(ini.get(section, key.lower())) != value):
					found = False
					break
			if found:
				for (key, value) in auditSoftwareOnClient.toHash().items():
					if value is None:
						continue
					ini.set(section, key, self.__escape(value))
				iniFile.generate(ini)
				return
		raise Exception(u"auditSoftwareOnClient %s not found" % auditSoftwareOnClient)
	
	def auditSoftwareOnClient_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditSoftwareOnClient_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting auditSoftwareOnClients ...")
		filenames = {}
		for ident in self._getIdents('AuditSoftwareOnClient', **filter):
			if not ident['clientId'] in filenames.keys():
				filenames[ident['clientId']] = self._getConfigFile('AuditSoftwareOnClient', ident, 'sw')
		
		result = []
		for (clientId, filename) in filenames.items():
			if not os.path.exists(filename):
				continue
			iniFile = IniFile(filename = filename)
			ini = iniFile.parse()
			for section in ini.sections():
				objHash = {
					"name":            None,
					"version":         None,
					"subVersion":      None,
					"language":        None,
					"architecture":    None,
					"clientId":        None,
					"uninstallString": None,
					"binaryName":      None,
					"firstseen":       None,
					"lastseen":        None,
					"state":           None,
					"usageFrequency":  None,
					"lastUsed":        None,
					"licenseKey":      None
				}
				for (key, value) in objHash.items():
					try:
						objHash[key] = self.__unescape(ini.get(section, key.lower()))
					except:
						pass
				
				if self._objectHashMatches(objHash, **filter):
					result.append(AuditSoftwareOnClient.fromHash(objHash))
		
		return result
	
	def auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients):
		ConfigDataBackend.auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients)
		
		logger.debug(u"Deleting auditSoftwareOnClients ...")
		filenames = {}
		idents = {}
		for auditSoftwareOnClient in forceObjectClassList(auditSoftwareOnClients, AuditSoftwareOnClient):
			ident = auditSoftwareOnClient.getIdent(returnType = 'dict')
			if not idents.has_key(ident['clientId']):
				idents[ident['clientId']] = []
			idents[ident['clientId']].append(ident)
			if not ident['clientId'] in filenames.keys():
				filenames[ident['clientId']] = self._getConfigFile('AuditSoftwareOnClient', ident, 'sw')
		
		for (clientId, filename) in filenames.items():
			iniFile = IniFile(filename = filename)
			ini = iniFile.parse()
			removeSections = []
			for section in ini.sections():
				for ident in idents[clientId]:
					found = True
					for (key, value) in ident.items():
						if (self.__unescape(ini.get(section, key.lower())) != value):
							found = False
							break
					if found and not section in removeSections:
						removeSections.append(section)
			if removeSections:
				for section in removeSections:
					ini.remove_section(section)
				iniFile.generate(ini)
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	
	def auditHardware_insertObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		ConfigDataBackend.auditHardware_insertObject(self, auditHardware)
		
		logger.debug(u"Inserting auditHardware: '%s'" % auditHardware.getIdent())
		self.__doAuditHardwareObj(auditHardware, mode = 'insert')
		
	def auditHardware_updateObject(self, auditHardware):
		auditHardware = forceObjectClass(auditHardware, AuditHardware)
		ConfigDataBackend.auditHardware_updateObject(self, auditHardware)
		
		logger.debug(u"Updating auditHardware: '%s'" % auditHardware.getIdent())		
		self.__doAuditHardwareObj(auditHardware, mode = 'update')
		
	def auditHardware_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditHardware_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting auditHardwares ...")
		result = []
		filename = self._getConfigFile('AuditHardware', {}, 'hw')
		if not os.path.exists(filename):
			return result
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		for section in ini.sections():
			objHash = {}
			for option in ini.options(section):
				if (option.lower() == 'hardwareclass'):
					objHash['hardwareClass'] = self.__unescape(ini.get(section, option))
				else:
					objHash[str(option)] = self.__unescape(ini.get(section, option))
			
			auditHardware = AuditHardware.fromHash(objHash)
			if self._objectHashMatches(auditHardware.toHash(), **filter):
				result.append(auditHardware)
		
		return result
	
	def auditHardware_deleteObjects(self, auditHardwares):
		ConfigDataBackend.auditHardware_deleteObjects(self, auditHardwares)
		
		logger.debug(u"Deleting auditHardwares ...")
		#TODO: forceObjectClassList necessary?
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			self.__doAuditHardwareObj(auditHardware, mode = 'delete')
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	
	def auditHardwareOnHost_insertObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		ConfigDataBackend.auditHardwareOnHost_insertObject(self, auditHardwareOnHost)
		
		logger.debug(u"Inserting auditHardwareOnHost: '%s'" % auditHardwareOnHost.getIdent())

		self.__doAuditHardwareObj(auditHardwareOnHost, mode = 'insert')
		
	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		auditHardwareOnHost = forceObjectClass(auditHardwareOnHost, AuditHardwareOnHost)
		ConfigDataBackend.auditHardwareOnHost_updateObject(self, auditHardwareOnHost)
		
		logger.debug(u"Updating auditHardwareOnHost: '%s'" % auditHardwareOnHost.getIdent())

		self.__doAuditHardwareObj(auditHardwareOnHost, mode = 'update')
		
	def auditHardwareOnHost_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditHardwareOnHost_getObjects(self, attributes=[], **filter)
		
		logger.debug(u"Getting auditHardwareOnHosts ...")
		filenames = {}
		for ident in self._getIdents('AuditHardwareOnHost', **filter):
			if not ident['hostId'] in filenames.keys():
				filenames[ident['hostId']] = self._getConfigFile('AuditHardwareOnHost', ident, 'hw')
		
		result = []
		for (hostId, filename) in filenames.items():
			if not os.path.exists(filename):
				continue
			iniFile = IniFile(filename = filename)
			ini = iniFile.parse()
			for section in ini.sections():
				objHash = {
					'hostId': hostId
				}
				for option in ini.options(section):
					if option.lower() == u'hardwareclass':
						objHash['hardwareClass'] = self.__unescape(ini.get(section, option))
					else:
						objHash[str(option)] = self.__unescape(ini.get(section, option))
				
				auditHardwareOnHost = AuditHardwareOnHost.fromHash(objHash)
				if self._objectHashMatches(auditHardwareOnHost.toHash(), **filter):
					result.append(auditHardwareOnHost)
		
		return result
	
	def auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts):
		ConfigDataBackend.auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts)
		
		logger.debug(u"Deleting auditHardwareOnHosts ...")
		
		#TODO: forceObjectClassList necessary?
		for auditHardwareOnHost in forceObjectClassList(auditHardwareOnHosts, AuditHardwareOnHost):
			self.__doAuditHardwareObj(auditHardwareOnHost, mode = 'delete')
		
	def __doAuditHardwareObj(self, auditHardwareObj, mode):
		if not mode in ('insert', 'update', 'delete'):
			raise Exception(u"Unknown mode: %s" % mode)
		
		objType = auditHardwareObj.getType()
		if not objType in ('AuditHardware', 'AuditHardwareOnHost'):
			raise Exception(u"Unknown type: %s" % objType)
		
		#if (objType == 'AuditHardwareOnHost') and (auditHardwareObj.getState() == 0):
		#	mode = 'delete'
		
		filename = self._getConfigFile(objType, auditHardwareObj.getIdent(returnType = 'dict'), 'hw')
		self._touch(filename)
		iniFile = IniFile(filename = filename)
		ini = iniFile.parse()
		
		objHash = {}
		for (attribute, value) in auditHardwareObj.toHash().items():
			if attribute.lower() in ('hostid', 'type'):
				continue
			if value is None:
				objHash[attribute.lower()] = u''
			else:
				objHash[attribute.lower()] = forceUnicode(value)
		
		sectionFound = None
		for section in ini.sections():
			matches = True
			for (attribute, value) in objHash.items():
				if attribute in ('firstseen', 'lastseen', 'state'):
					continue
				if ini.has_option(section, attribute):
					if (self.__unescape(ini.get(section, attribute)) != value):
						matches = False
						break
				else:
					matches = False
					break
			if matches:
				logger.debug(u"Found matching section '%s' in audit file '%s' for object %s" % (section, filename, objHash))
				sectionFound = section
				break
		
		if (mode == 'delete'):
			if sectionFound:
				ini.remove_section(sectionFound)
		
		if (mode == 'update'):
			if sectionFound:
				for (attribute, value) in objHash.items():
					if attribute in ('firstseen', 'lastseen', 'state') and not value:
						continue
					ini.set(sectionFound, attribute, self.__escape(value))
			else:
				mode = 'insert'
		
		if (mode == 'insert'):
			if sectionFound:
				ini.remove_section(sectionFound)
			else:
				nums = []
				for section in ini.sections():
					nums.append(int(section[section.rfind('_') + 1:]))
				num = 0
				while num in nums:
					num += 1
				sectionFound = u'hardware_%d' % num
			ini.add_section(sectionFound)
			for (attribute, value) in objHash.items():
				ini.set(sectionFound, attribute, self.__escape(value))
		iniFile.generate(ini)
	
	
	
	
	
	





