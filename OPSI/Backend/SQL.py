#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
opsi python library - Backend - SQL

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2013 uib GmbH

http://www.uib.de/

All rights reserved.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License, version 3
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Affero General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

@copyright:	uib GmbH <info@uib.de>
@author: Jan Schneider <j.schneider@uib.de>
@author: Erol Ueluekmen <e.ueluekmen@uib.de>
@license: GNU Affero GPL version 3
"""

import time
from hashlib import md5
from twisted.conch.ssh import keys

from OPSI.Logger import Logger
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Backend.Backend import *

logger = Logger()


class SQL(object):

	AUTOINCREMENT = 'AUTO_INCREMENT'
	ALTER_TABLE_CHANGE_SUPPORTED = True
	ESCAPED_BACKSLASH  = "\\\\"
	ESCAPED_APOSTROPHE = "\\\'"
	ESCAPED_UNDERSCORE = "\\_"
	ESCAPED_PERCENT    = "\\%"
	ESCAPED_ASTERISK   = "\\*"
	doCommit = True

	def __init__(self, **kwargs):
		pass

	def connect(self):
		pass

	def close(self, conn, cursor):
		pass

	def getSet(self, query):
		return []

	def getRow(self, query):
		return {}

	def insert(self, table, valueHash):
		return -1

	def update(self, table, where, valueHash, updateWhereNone=False):
		return 0

	def delete(self, table, where):
		return 0

	def getTables(self):
		return {}

	def execute(self, query, conn=None, cursor=None):
		return None

	def query(self, query, conn=None, cursor=None):
		return self.execute(query)

	def getTableCreationOptions(self, table):
		return u''

	def escapeBackslash(self, string):
		return string.replace('\\', self.ESCAPED_BACKSLASH)

	def escapeApostrophe(self, string):
		return string.replace("'", self.ESCAPED_APOSTROPHE)

	def escapeUnderscore(self, string):
		return string.replace('_', self.ESCAPED_UNDERSCORE)

	def escapePercent(self, string):
		return string.replace('%', self.ESCAPED_PERCENT)

	def escapeAsterisk(self, string):
		return string.replace('*', self.ESCAPED_ASTERISK)


class SQLBackendObjectModificationTracker(BackendModificationListener):
	def __init__(self, **kwargs):
		BackendModificationListener.__init__(self)
		self._sql = None
		self._lastModificationOnly = False
		for (option, value) in kwargs.items():
			option = option.lower()
			if option in ('lastmodificationonly',):
				self._lastModificationOnly = forceBool(value)

	def _createTables(self):
		tables = self._sql.getTables()
		if not 'OBJECT_MODIFICATION_TRACKER' in tables.keys():
			logger.debug(u'Creating table OBJECT_MODIFICATION_TRACKER')
			table = u'''CREATE TABLE `OBJECT_MODIFICATION_TRACKER` (
					`id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`command` varchar(6) NOT NULL,
					`objectClass` varchar(128) NOT NULL,
					`ident` varchar(1024) NOT NULL,
					`date` TIMESTAMP,
					PRIMARY KEY (`id`)
				) %s;
				''' % self._sql.getTableCreationOptions('OBJECT_MODIFICATION_TRACKER')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `objectClass` on `OBJECT_MODIFICATION_TRACKER` (`objectClass`);')
			self._sql.execute('CREATE INDEX `ident` on `OBJECT_MODIFICATION_TRACKER` (`ident`);')
			self._sql.execute('CREATE INDEX `date` on `OBJECT_MODIFICATION_TRACKER` (`date`);')

	def _trackModification(self, command, obj):
		command = forceUnicodeLower(command)
		if not command in ('insert', 'update', 'delete'):
			raise Exception(u"Unhandled command '%s'" % command)
		data = {
			'command':     command,
			'objectClass': obj.__class__.__name__,
			'ident':       obj.getIdent(),
			'date':        timestamp()
		}
		if self._lastModificationOnly:
			objectClass = data['objectClass']
			ident = self._sql.escapeApostrophe(self._sql.escapeBackslash(data['ident']))
			self._sql.delete('OBJECT_MODIFICATION_TRACKER', "`objectClass` = '%s' AND `ident` = '%s'" % (objectClass, ident))
		start = time.time()
		self._sql.insert('OBJECT_MODIFICATION_TRACKER', data)
		logger.debug(u"Took %0.2f seconds to track modification of objectClass %s, ident %s" % ((time.time() - start), data['objectClass'], data['ident']))

	def getModifications(self, sinceDate = 0):
		return self._sql.getSet("SELECT * FROM `OBJECT_MODIFICATION_TRACKER` WHERE `date` > '%s'" % forceOpsiTimestamp(sinceDate))

	def clearModifications(self, objectClass = None, sinceDate = 0):
		where ="`date` > '%s'" % forceOpsiTimestamp(sinceDate)
		if objectClass:
			where += ' AND `objectClass` = "%s"' % objectClass
		self._sql.execute("DELETE FROM `OBJECT_MODIFICATION_TRACKER` WHERE %s" % where)

	def objectInserted(self, backend, obj):
		self._trackModification('insert', obj)

	def objectUpdated(self, backend, obj):
		self._trackModification('update', obj)

	def objectsDeleted(self, backend, objs):
		for obj in forceList(objs):
			self._trackModification('delete', obj)


class SQLBackend(ConfigDataBackend):

	def __init__(self, **kwargs):
		self._name = 'sql'

		ConfigDataBackend.__init__(self, **kwargs)

		self._sql = None
		self._auditHardwareConfig = {}
		self._setAuditHardwareConfig(self.auditHardware_getConfig())

	def _setAuditHardwareConfig(self, config):
		self._auditHardwareConfig = {}
		for conf in config:
			hwClass = conf['Class']['Opsi']
			self._auditHardwareConfig[hwClass] = {}
			for value in conf['Values']:
				self._auditHardwareConfig[hwClass][value['Opsi']] = {
					'Type':  value["Type"],
					'Scope': value["Scope"]
				}

	def _filterToSql(self, filter={}):
		where = u''
		for (key, values) in filter.items():
			if values is None:
				continue
			values = forceList(values)
			if not values:
				continue
			if where:
				where += u' and '
			where += u'('
			for value in values:
				operator = '='
				if type(value) is bool:
					if value:
						where += u"`%s` %s %s" % (key, operator, 1)
					else:
						where += u"`%s` %s %s" % (key, operator, 0)
				elif type(value) in (float, long, int):
					where += u"`%s` %s %s" % (key, operator, value)
				elif value is None:
					where += u"`%s` is NULL" % key
				else:
					value = value.replace(self._sql.ESCAPED_ASTERISK, u'\uffff')
					value = self._sql.escapeApostrophe(self._sql.escapeBackslash(value))
					match = re.search('^\s*([>=<]+)\s*(\d\.?\d*)', value)
					if match:
						operator = match.group(1)
						value = match.group(2)
						value = value.replace(u'\uffff', self._sql.ESCAPED_ASTERISK)
						where += u"`%s` %s %s" % (key, operator, forceUnicode(value))
					else:
						if (value.find('*') != -1):
							operator = 'LIKE'
							value = self._sql.escapeUnderscore(self._sql.escapePercent(value)).replace('*', '%')
						value = value.replace(u'\uffff', self._sql.ESCAPED_ASTERISK)
						where += u"`%s` %s '%s'" % (key, operator, forceUnicode(value))
				where += u' or '
			where = where[:-4] + u')'
		return where

	def _createQuery(self, table, attributes=[], filter={}):
		select = u''
		for attribute in attributes:
			if select:
				select += u','
			select += u'`%s`' % attribute
		if not select:
			select = u'*'

		where = self._filterToSql(filter)
		query = u''
		if where:
			query = u'select %s from `%s` where %s' % (select, table, where)
		else:
			query = u'select %s from `%s`' % (select, table)
		logger.debug(u"Created query: '%s'" % query)
		return query

	def _adjustAttributes(self, objectClass, attributes, filter):
		if not attributes:
			attributes = []
		# Work on copies of attributes and filter!
		newAttributes = list(forceUnicodeList(attributes))
		newFilter = dict(forceDict(filter))
		id = self._objectAttributeToDatabaseAttribute(objectClass, 'id')
		if newFilter.has_key('id'):
			newFilter[id] = newFilter['id']
			del newFilter['id']
		if 'id' in newAttributes:
			newAttributes.remove('id')
			newAttributes.append(id)
		if 'type' in filter.keys():
			for oc in forceList(filter['type']):
				if (objectClass.__name__ == oc):
					newFilter['type'] = forceList(filter['type']).append(objectClass.subClasses.values())
		if newAttributes:
			if issubclass(objectClass, Entity) and not 'type' in newAttributes:
				newAttributes.append('type')
			objectClasses = [ objectClass ]
			objectClasses.extend(objectClass.subClasses.values())
			for oc in objectClasses:
				for arg in mandatoryConstructorArgs(oc):
					if (arg == 'id'):
						arg = id
					if not arg in newAttributes:
						newAttributes.append(arg)
		return (newAttributes, newFilter)

	def _adjustResult(self, objectClass, result):
		id = self._objectAttributeToDatabaseAttribute(objectClass, 'id')
		if result.has_key(id):
			result['id'] = result[id]
			del result[id]
		return result

	def _objectToDatabaseHash(self, object):
		hash = object.toHash()
		if (object.getType() == 'ProductOnClient'):
			if hash.has_key('actionSequence'):
				del hash['actionSequence']

		if issubclass(object.__class__, Relationship):
			if hash.has_key('type'):
				del hash['type']

		for (key, value) in hash.items():
			arg = self._objectAttributeToDatabaseAttribute(object.__class__, key)
			if (key != arg):
				hash[arg] = hash[key]
				del hash[key]
		return hash

	def _objectAttributeToDatabaseAttribute(self, objectClass, attribute):
		if (attribute == 'id'):
			# A class is considered a subclass of itself
			if issubclass(objectClass, Product):
				return 'productId'
			if issubclass(objectClass, Host):
				return 'hostId'
			if issubclass(objectClass, Group):
				return 'groupId'
			if issubclass(objectClass, Config):
				return 'configId'
			if issubclass(objectClass, LicenseContract):
				return 'licenseContractId'
			if issubclass(objectClass, SoftwareLicense):
				return 'softwareLicenseId'
			if issubclass(objectClass, LicensePool):
				return 'licensePoolId'
		return attribute

	def _uniqueCondition(self, object):
		condition = u''
		args = mandatoryConstructorArgs(object.__class__)
		for arg in args:
			value = getattr(object, arg)
			if value is None:
				continue
			arg = self._objectAttributeToDatabaseAttribute(object.__class__, arg)
			if condition:
				condition += u' and '
			if type(value) is bool:
				if value:
					condition += u"`%s` = %s" % (arg, 1)
				else:
					condition += u"`%s` = %s" % (arg, 0)
			elif type(value) in (float, long, int):
				condition += u"`%s` = %s" % (arg, value)
			#elif value is None:
			#	where += u"`%s` is NULL" % key
			else:
				condition += u"`%s` = '%s'" % (arg, self._sql.escapeApostrophe(self._sql.escapeBackslash(value)))
		if isinstance(object, HostGroup) or isinstance(object, ProductGroup):
			condition += u" and `type` = '%s'" % object.getType()
		return condition

	def _objectExists(self, table, object):
		query = 'select * from `%s` where %s' % (table, self._uniqueCondition(object))
		return bool(self._sql.getRow(query))

	def backend_exit(self):
		pass

	def backend_deleteBase(self):
		ConfigDataBackend.backend_deleteBase(self)
		# Drop database
		errors = 0
		done = False
		while not done and (errors < 100):
			done = True
			for i in self._sql.getTables().keys():
				try:
					logger.debug(u'DROP TABLE `%s`;' % i)
					self._sql.execute(u'DROP TABLE `%s`;' % i)
				except Exception as e:
					logger.error(e)
					done = False
					errors += 1

	def backend_createBase(self):
		ConfigDataBackend.backend_createBase(self)

		tables = self._sql.getTables()

		logger.notice(u'Creating opsi base')

		# Host table
		if not 'HOST' in tables.keys():
			self._createTableHost()

		if not 'CONFIG' in tables.keys():
			logger.debug(u'Creating table CONFIG')
			table = u'''CREATE TABLE `CONFIG` (
					`configId` varchar(200) NOT NULL,
					`type` varchar(30) NOT NULL,
					`description` varchar(256),
					`multiValue` bool NOT NULL,
					`editable` bool NOT NULL,
					PRIMARY KEY (`configId`)
				) %s;
				''' % self._sql.getTableCreationOptions('CONFIG')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_config_type` on `CONFIG` (`type`);')

		if not 'CONFIG_VALUE' in tables.keys():
			logger.debug(u'Creating table CONFIG_VALUE')
			table = u'''CREATE TABLE `CONFIG_VALUE` (
					`config_value_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`configId` varchar(200) NOT NULL,
					`value` TEXT,
					`isDefault` bool,
					PRIMARY KEY (`config_value_id`),
					FOREIGN KEY (`configId`) REFERENCES `CONFIG` (`configId`)
				) %s;
				''' % self._sql.getTableCreationOptions('CONFIG_VALUE')
			logger.debug(table)
			self._sql.execute(table)

		if not 'CONFIG_STATE' in tables.keys():
			logger.debug(u'Creating table CONFIG_STATE')
			table = u'''CREATE TABLE `CONFIG_STATE` (
					`config_state_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`configId` varchar(200) NOT NULL,
					`objectId` varchar(255) NOT NULL,
					`values` text,
					PRIMARY KEY (`config_state_id`)
				) %s;
				''' % self._sql.getTableCreationOptions('CONFIG_STATE')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_config_state_configId` on `CONFIG_STATE` (`configId`);')
			self._sql.execute('CREATE INDEX `index_config_state_objectId` on `CONFIG_STATE` (`objectId`);')

		if not 'PRODUCT' in tables.keys():
			logger.debug(u'Creating table PRODUCT')
			table = u'''CREATE TABLE `PRODUCT` (
					`productId` varchar(255) NOT NULL,
					`productVersion` varchar(32) NOT NULL,
					`packageVersion` varchar(16) NOT NULL,
					`type` varchar(32) NOT NULL,
					`name` varchar(128) NOT NULL,
					`licenseRequired` varchar(50),
					`setupScript` varchar(50),
					`uninstallScript` varchar(50),
					`updateScript` varchar(50),
					`alwaysScript` varchar(50),
					`onceScript` varchar(50),
					`customScript` varchar(50),
					`userLoginScript` varchar(50),
					`priority` integer,
					`description` TEXT,
					`advice` TEXT,
					`pxeConfigTemplate` varchar(50),
					`changelog` TEXT,
					PRIMARY KEY (`productId`, `productVersion`, `packageVersion`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_product_type` on `PRODUCT` (`type`);')

		# FOREIGN KEY ( `productId` ) REFERENCES `PRODUCT` ( `productId` ),
		if not 'WINDOWS_SOFTWARE_ID_TO_PRODUCT' in tables.keys():
			logger.debug(u'Creating table WINDOWS_SOFTWARE_ID_TO_PRODUCT')
			table = u'''CREATE TABLE `WINDOWS_SOFTWARE_ID_TO_PRODUCT` (
					`windowsSoftwareId` VARCHAR(100) NOT NULL,
					`productId` varchar(255) NOT NULL,
					PRIMARY KEY (`windowsSoftwareId`, `productId`)
				) %s;
				''' % self._sql.getTableCreationOptions('WINDOWS_SOFTWARE_ID_TO_PRODUCT')
			logger.debug(table)
			self._sql.execute(table)

		if not 'PRODUCT_ON_DEPOT' in tables.keys():
			logger.debug(u'Creating table PRODUCT_ON_DEPOT')
			table = u'''CREATE TABLE `PRODUCT_ON_DEPOT` (
					`productId` varchar(255) NOT NULL,
					`productVersion` varchar(32) NOT NULL,
					`packageVersion` varchar(16) NOT NULL,
					`depotId` varchar(50) NOT NULL,
					`productType` varchar(16) NOT NULL,
					`locked` bool,
					PRIMARY KEY (`productId`, `depotId`),
					FOREIGN KEY (`productId`, `productVersion`, `packageVersion` ) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`),
					FOREIGN KEY (`depotId`) REFERENCES `HOST` (`hostId`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_ON_DEPOT')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_product_on_depot_productType` on `PRODUCT_ON_DEPOT` (`productType`);')

		if not 'PRODUCT_PROPERTY' in tables.keys():
			logger.debug(u'Creating table PRODUCT_PROPERTY')
			table = u'''CREATE TABLE `PRODUCT_PROPERTY` (
					`productId` varchar(255) NOT NULL,
					`productVersion` varchar(32) NOT NULL,
					`packageVersion` varchar(16) NOT NULL,
					`propertyId` varchar(200) NOT NULL,
					`type` varchar(30) NOT NULL,
					`description` TEXT,
					`multiValue` bool NOT NULL,
					`editable` bool NOT NULL,
					PRIMARY KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`),
					FOREIGN KEY (`productId`, `productVersion`, `packageVersion`) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_PROPERTY')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_product_property_type` on `PRODUCT_PROPERTY` (`type`);')

		if not 'PRODUCT_PROPERTY_VALUE' in tables.keys():
			logger.debug(u'Creating table PRODUCT_PROPERTY_VALUE')
			table = u'''CREATE TABLE `PRODUCT_PROPERTY_VALUE` (
					`product_property_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`productId` varchar(255) NOT NULL,
					`productVersion` varchar(32) NOT NULL,
					`packageVersion` varchar(16) NOT NULL,
					`propertyId` varchar(200) NOT NULL,
					`value` text,
					`isDefault` bool,
					PRIMARY KEY (`product_property_id`),
					FOREIGN KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`) REFERENCES `PRODUCT_PROPERTY` (`productId`, `productVersion`, `packageVersion`, `propertyId`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_PROPERTY_VALUE')
			logger.debug(table)
			self._sql.execute(table)

		if not 'PRODUCT_DEPENDENCY' in tables.keys():
			logger.debug(u'Creating table PRODUCT_DEPENDENCY')
			table = u'''CREATE TABLE `PRODUCT_DEPENDENCY` (
					`productId` varchar(255) NOT NULL,
					`productVersion` varchar(32) NOT NULL,
					`packageVersion` varchar(16) NOT NULL,
					`productAction` varchar(16) NOT NULL,
					`requiredProductId` varchar(255) NOT NULL,
					`requiredProductVersion` varchar(32),
					`requiredPackageVersion` varchar(16),
					`requiredAction` varchar(16),
					`requiredInstallationStatus` varchar(16),
					`requirementType` varchar(16),
					PRIMARY KEY (`productId`, `productVersion`, `packageVersion`, `productAction`, `requiredProductId`),
					FOREIGN KEY (`productId`, `productVersion`, `packageVersion`) REFERENCES `PRODUCT` (`productId`, `productVersion`, `packageVersion`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_DEPENDENCY')
			logger.debug(table)
			self._sql.execute(table)

		# FOREIGN KEY ( `productId` ) REFERENCES PRODUCT( `productId` ),
		if not 'PRODUCT_ON_CLIENT' in tables.keys():
			logger.debug(u'Creating table PRODUCT_ON_CLIENT')
			table = u'''CREATE TABLE `PRODUCT_ON_CLIENT` (
					`productId` varchar(255) NOT NULL,
					`clientId` varchar(255) NOT NULL,
					`productType` varchar(16) NOT NULL,
					`targetConfiguration` varchar(16),
					`installationStatus` varchar(16),
					`actionRequest` varchar(16),
					`actionProgress` varchar(255),
					`actionResult` varchar(16),
					`lastAction` varchar(16),
					`productVersion` varchar(32),
					`packageVersion` varchar(16),
					`modificationTime` TIMESTAMP,
					PRIMARY KEY (`productId`, `clientId`),
					FOREIGN KEY (`clientId`) REFERENCES `HOST` (`hostId`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_ON_CLIENT')
			logger.debug(table)
			self._sql.execute(table)

		# FOREIGN KEY ( `productId` ) REFERENCES `PRODUCT` ( `productId` ),
		if not 'PRODUCT_PROPERTY_STATE' in tables.keys():
			logger.debug(u'Creating table PRODUCT_PROPERTY_STATE')
			table = u'''CREATE TABLE `PRODUCT_PROPERTY_STATE` (
					`product_property_state_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`productId` varchar(255) NOT NULL,
					`propertyId` varchar(200) NOT NULL,
					`objectId` varchar(255) NOT NULL,
					`values` text,
					PRIMARY KEY (`product_property_state_id`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_PROPERTY_STATE')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_product_property_state_objectId` on `PRODUCT_PROPERTY_STATE` (`objectId`);')

		if not 'GROUP' in tables.keys():
			logger.debug(u'Creating table GROUP')
			table = u'''CREATE TABLE `GROUP` (
					`type` varchar(30) NOT NULL,
					`groupId` varchar(255) NOT NULL,
					`parentGroupId` varchar(255),
					`description` varchar(100),
					`notes` varchar(500),
					PRIMARY KEY (`type`, `groupId`)
				) %s;
				''' % self._sql.getTableCreationOptions('GROUP')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_group_parentGroupId` on `GROUP` (`parentGroupId`);')

		if not 'OBJECT_TO_GROUP' in tables.keys():
			logger.debug(u'Creating table OBJECT_TO_GROUP')
			table = u'''CREATE TABLE `OBJECT_TO_GROUP` (
					`object_to_group_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`groupType` varchar(30) NOT NULL,
					`groupId` varchar(100) NOT NULL,
					`objectId` varchar(255) NOT NULL,
					PRIMARY KEY (`object_to_group_id`),
					FOREIGN KEY (`groupType`, `groupId`) REFERENCES `GROUP` (`type`, `groupId`)
				) %s;
				''' % self._sql.getTableCreationOptions('OBJECT_TO_GROUP')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_object_to_group_objectId` on `OBJECT_TO_GROUP` (`objectId`);')

		if not 'LICENSE_CONTRACT' in tables.keys():
			logger.debug(u'Creating table LICENSE_CONTRACT')
			table = u'''CREATE TABLE `LICENSE_CONTRACT` (
					`licenseContractId` VARCHAR(100) NOT NULL,
					`type` varchar(30) NOT NULL,
					`description` varchar(100),
					`notes` varchar(1000),
					`partner` varchar(100),
					`conclusionDate` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					`notificationDate` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					`expirationDate` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					PRIMARY KEY (`licenseContractId`)
				) %s;
				''' % self._sql.getTableCreationOptions('LICENSE_CONTRACT')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_license_contract_type` on `LICENSE_CONTRACT` (`type`);')

		if not 'SOFTWARE_LICENSE' in tables.keys():
			logger.debug(u'Creating table SOFTWARE_LICENSE')
			table = u'''CREATE TABLE `SOFTWARE_LICENSE` (
					`softwareLicenseId` VARCHAR(100) NOT NULL,
					`licenseContractId` VARCHAR(100) NOT NULL,
					`type` varchar(30) NOT NULL,
					`boundToHost` varchar(255),
					`maxInstallations` integer,
					`expirationDate` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					PRIMARY KEY (`softwareLicenseId`),
					FOREIGN KEY (`licenseContractId`) REFERENCES `LICENSE_CONTRACT` (`licenseContractId`)
				) %s;
				''' % self._sql.getTableCreationOptions('SOFTWARE_LICENSE')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_software_license_type` on `SOFTWARE_LICENSE` (`type`);')
			self._sql.execute('CREATE INDEX `index_software_license_boundToHost` on `SOFTWARE_LICENSE` (`boundToHost`);')

		if not 'LICENSE_POOL' in tables.keys():
			logger.debug(u'Creating table LICENSE_POOL')
			table = u'''CREATE TABLE `LICENSE_POOL` (
					`licensePoolId` VARCHAR(100) NOT NULL,
					`type` varchar(30) NOT NULL,
					`description` varchar(200),
					PRIMARY KEY (`licensePoolId`)
				) %s;
				''' % self._sql.getTableCreationOptions('LICENSE_POOL')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_license_pool_type` on `LICENSE_POOL` (`type`);')

		if not 'AUDIT_SOFTWARE_TO_LICENSE_POOL' in tables.keys():
			logger.debug(u'Creating table AUDIT_SOFTWARE_TO_LICENSE_POOL')
			table = u'''CREATE TABLE `AUDIT_SOFTWARE_TO_LICENSE_POOL` (
					`licensePoolId` VARCHAR(100) NOT NULL,
					`name` varchar(100) NOT NULL,
					`version` varchar(100) NOT NULL,
					`subVersion` varchar(100) NOT NULL,
					`language` varchar(10) NOT NULL,
					`architecture` varchar(3) NOT NULL,
					PRIMARY KEY (`name`, `version`, `subVersion`, `language`, `architecture`),
					FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
				) %s;
				''' % self._sql.getTableCreationOptions('AUDIT_SOFTWARE_TO_LICENSE_POOL')
			logger.debug(table)
			self._sql.execute(table)

		if not 'PRODUCT_ID_TO_LICENSE_POOL' in tables.keys():
			logger.debug(u'Creating table PRODUCT_ID_TO_LICENSE_POOL')
			table = u'''CREATE TABLE `PRODUCT_ID_TO_LICENSE_POOL` (
					`licensePoolId` VARCHAR(100) NOT NULL,
					`productId` VARCHAR(255) NOT NULL,
					PRIMARY KEY (`licensePoolId`, `productId`),
					FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
				) %s;
				''' % self._sql.getTableCreationOptions('PRODUCT_ID_TO_LICENSE_POOL')
			logger.debug(table)
			self._sql.execute(table)

		if not 'SOFTWARE_LICENSE_TO_LICENSE_POOL' in tables.keys():
			logger.debug(u'Creating table SOFTWARE_LICENSE_TO_LICENSE_POOL')
			table = u'''CREATE TABLE `SOFTWARE_LICENSE_TO_LICENSE_POOL` (
					`softwareLicenseId` VARCHAR(100) NOT NULL,
					`licensePoolId` VARCHAR(100) NOT NULL,
					`licenseKey` VARCHAR(1024),
					PRIMARY KEY (`softwareLicenseId`, `licensePoolId`),
					FOREIGN KEY (`softwareLicenseId`) REFERENCES `SOFTWARE_LICENSE` (`softwareLicenseId`),
					FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
				) %s;
				''' % self._sql.getTableCreationOptions('SOFTWARE_LICENSE_TO_LICENSE_POOL')
			logger.debug(table)
			self._sql.execute(table)

		if not 'LICENSE_ON_CLIENT' in tables.keys():
			logger.debug(u'Creating table LICENSE_ON_CLIENT')
			table = u'''CREATE TABLE `LICENSE_ON_CLIENT` (
					`license_on_client_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`softwareLicenseId` VARCHAR(100) NOT NULL,
					`licensePoolId` VARCHAR(100) NOT NULL,
					`clientId` varchar(255),
					`licenseKey` VARCHAR(1024),
					`notes` VARCHAR(1024),
					PRIMARY KEY (`license_on_client_id`),
					FOREIGN KEY (`softwareLicenseId`, `licensePoolId`) REFERENCES `SOFTWARE_LICENSE_TO_LICENSE_POOL` (`softwareLicenseId`, `licensePoolId`)
				) %s;
				''' % self._sql.getTableCreationOptions('LICENSE_ON_CLIENT')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_license_on_client_clientId` on `LICENSE_ON_CLIENT` (`clientId`);')

		if not 'BOOT_CONFIGURATION' in tables.keys():
			logger.debug(u'Creating table BOOT_CONFIGURATION')
			table = u'''CREATE TABLE `BOOT_CONFIGURATION` (
					`name` varchar(64) NOT NULL,
					`clientId` varchar(255) NOT NULL,
					`priority` integer DEFAULT 0,
					`description` TEXT,
					`netbootProductId` varchar(255),
					`pxeTemplate` varchar(255),
					`options` varchar(255),
					`disk` integer,
					`partition` integer,
					`active` bool,
					`deleteAfter` integer,
					`deactivateAfter` integer,
					`accessCount` integer,
					`osName` varchar(128),
					PRIMARY KEY (`name`, `clientId`),
					FOREIGN KEY (`clientId`) REFERENCES `HOST` (`hostId`)
				) %s;
				''' % self._sql.getTableCreationOptions('BOOT_CONFIGURATION')
			logger.debug(table)
			self._sql.execute(table)

		# Software audit tables
		if not 'SOFTWARE' in tables.keys():
			logger.debug(u'Creating table SOFTWARE')
			table = u'''CREATE TABLE `SOFTWARE` (
					`name` varchar(100) NOT NULL,
					`version` varchar(100) NOT NULL,
					`subVersion` varchar(100) NOT NULL,
					`language` varchar(10) NOT NULL,
					`architecture` varchar(3) NOT NULL,
					`windowsSoftwareId` varchar(100),
					`windowsDisplayName` varchar(100),
					`windowsDisplayVersion` varchar(100),
					`type` varchar(30) NOT NULL,
					`installSize` BIGINT,
					PRIMARY KEY (`name`, `version`, `subVersion`, `language`, `architecture`)
				) %s;
				''' % self._sql.getTableCreationOptions('SOFTWARE')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_software_windowsSoftwareId` on `SOFTWARE` (`windowsSoftwareId`);')
			self._sql.execute('CREATE INDEX `index_software_type` on `SOFTWARE` (`type`);')

		if not 'SOFTWARE_CONFIG' in tables.keys():
			logger.debug(u'Creating table SOFTWARE_CONFIG')
			table = u'''CREATE TABLE `SOFTWARE_CONFIG` (
					`config_id` integer NOT NULL ''' + self._sql.AUTOINCREMENT + ''',
					`clientId` varchar(255) NOT NULL,
					`name` varchar(100) NOT NULL,
					`version` varchar(100) NOT NULL,
					`subVersion` varchar(100) NOT NULL,
					`language` varchar(10) NOT NULL,
					`architecture` varchar(3) NOT NULL,
					`uninstallString` varchar(200),
					`binaryName` varchar(100),
					`firstseen` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					`lastseen` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					`state` TINYINT NOT NULL,
					`usageFrequency` integer NOT NULL DEFAULT -1,
					`lastUsed` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
					`licenseKey` VARCHAR(1024),
					PRIMARY KEY (`config_id`)
				) %s;
				''' % self._sql.getTableCreationOptions('SOFTWARE_CONFIG')
			logger.debug(table)
			self._sql.execute(table)
			self._sql.execute('CREATE INDEX `index_software_config_clientId` on `SOFTWARE_CONFIG` (`clientId`);')
			self._sql.execute('CREATE INDEX `index_software_config_nvsla` on `SOFTWARE_CONFIG` (`name`, `version`, `subVersion`, `language`, `architecture`);')

		# Hardware audit tables
		for (hwClass, values) in self._auditHardwareConfig.items():
			logger.debug(u"Processing hardware class '%s'" % hwClass)
			hardwareDeviceTableName = u'HARDWARE_DEVICE_' + hwClass
			hardwareConfigTableName = u'HARDWARE_CONFIG_' + hwClass

			hardwareDeviceTable = u'CREATE TABLE `' + hardwareDeviceTableName + '` (\n' + \
						u'`hardware_id` INTEGER NOT NULL ' + self._sql.AUTOINCREMENT + ',\n'
			hardwareConfigTable = u'CREATE TABLE `' + hardwareConfigTableName + '` (\n' + \
						u'`config_id` INTEGER NOT NULL ' + self._sql.AUTOINCREMENT + ',\n' + \
						u'`hostId` varchar(50) NOT NULL,\n' + \
						u'`hardware_id` INTEGER NOT NULL,\n' + \
						u'`firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						u'`lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						u'`state` TINYINT NOT NULL,\n'

			hardwareDeviceTableExists = hardwareDeviceTableName in tables.keys()
			hardwareConfigTableExists = hardwareConfigTableName in tables.keys()

			if hardwareDeviceTableExists:
				hardwareDeviceTable = u'ALTER TABLE `' + hardwareDeviceTableName + u'`\n'
			if hardwareConfigTableExists:
				hardwareConfigTable = u'ALTER TABLE `' + hardwareConfigTableName + u'`\n'

			hardwareDeviceValuesProcessed = 0;
			hardwareConfigValuesProcessed = 0;
			for (value, valueInfo) in values.items():
				logger.debug(u"  Processing value '%s'" % value)
				if   (valueInfo['Scope'] == 'g'):
					if hardwareDeviceTableExists:
						if value in tables[hardwareDeviceTableName]:
							# Column exists => change
							if not self._sql.ALTER_TABLE_CHANGE_SUPPORTED:
								continue
							hardwareDeviceTable += u'CHANGE `%s` `%s` %s NULL,\n' % (value, value, valueInfo['Type'])
						else:
							# Column does not exist => add
							hardwareDeviceTable += u'ADD `%s` %s NULL,\n' % (value, valueInfo["Type"])
					else:
						hardwareDeviceTable += u'`%s` %s NULL,\n' % (value, valueInfo["Type"])
					hardwareDeviceValuesProcessed += 1
				elif (valueInfo['Scope'] == 'i'):
					if hardwareConfigTableExists:
						if value in tables[hardwareConfigTableName]:
							# Column exists => change
							if not self._sql.ALTER_TABLE_CHANGE_SUPPORTED:
								continue
							hardwareConfigTable += u'CHANGE `%s` `%s` %s NULL,\n' % (value, value, valueInfo['Type'])
						else:
							# Column does not exist => add
							hardwareConfigTable += u'ADD `%s` %s NULL,\n' % (value, valueInfo['Type'])
					else:
						hardwareConfigTable += u'`%s` %s NULL,\n' % (value, valueInfo['Type'])
					hardwareConfigValuesProcessed += 1

			if not hardwareDeviceTableExists:
				hardwareDeviceTable += u'PRIMARY KEY (`hardware_id`)\n'
			if not hardwareConfigTableExists:
				hardwareConfigTable += u'PRIMARY KEY (`config_id`)\n'

			# Remove leading and trailing whitespace
			hardwareDeviceTable = hardwareDeviceTable.strip()
			hardwareConfigTable = hardwareConfigTable.strip()

			# Remove trailing comma
			if (hardwareDeviceTable[-1] == u','):
				hardwareDeviceTable = hardwareDeviceTable[:-1]
			if (hardwareConfigTable[-1] == u','):
				hardwareConfigTable = hardwareConfigTable[:-1]

			# Finish sql query
			if hardwareDeviceTableExists:
				hardwareDeviceTable += u' ;\n'
			else:
				hardwareDeviceTable += u'\n) %s;\n' % self._sql.getTableCreationOptions(hardwareDeviceTableName)

			if hardwareConfigTableExists:
				hardwareConfigTable += u' ;\n'
			else:
				hardwareConfigTable += u'\n) %s;\n' % self._sql.getTableCreationOptions(hardwareConfigTableName)

			# Execute sql query
			if hardwareDeviceValuesProcessed or not hardwareDeviceTableExists:
				logger.debug(hardwareDeviceTable)
				self._sql.execute(hardwareDeviceTable)
			if hardwareConfigValuesProcessed or not hardwareConfigTableExists:
				logger.debug(hardwareConfigTable)
				self._sql.execute(hardwareConfigTable)

	def _createTableHost(self):
		logger.debug(u'Creating table HOST')
		table = u'''CREATE TABLE `HOST` (
				`hostId` varchar(255) NOT NULL,
				`type` varchar(30),
				`description` varchar(100),
				`notes` varchar(500),
				`hardwareAddress` varchar(17),
				`ipAddress` varchar(15),
				`inventoryNumber` varchar(30),
				`created` TIMESTAMP,
				`lastSeen` TIMESTAMP,
				`opsiHostKey` varchar(32),
				`oneTimePassword` varchar(32),
				`maxBandwidth` integer,
				`depotLocalUrl` varchar(128),
				`depotRemoteUrl` varchar(255),
				`depotWebdavUrl` varchar(255),
				`repositoryLocalUrl` varchar(128),
				`repositoryRemoteUrl` varchar(255),
				`networkAddress` varchar(31),
				`isMasterDepot` bool,
				`masterDepotId` varchar(255),
				PRIMARY KEY (`hostId`)
			) %s;''' % self._sql.getTableCreationOptions('HOST')
		logger.debug(table)
		self._sql.execute(table)
		self._sql.execute('CREATE INDEX `index_host_type` on `HOST` (`type`);')

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_insertObject(self, host):
		ConfigDataBackend.host_insertObject(self, host)
		data = self._objectToDatabaseHash(host)
		where = self._uniqueCondition(host)
		if self._sql.getRow('select * from `HOST` where %s' % where):
			self._sql.update('HOST', where, data, updateWhereNone = True)
		else:
			self._sql.insert('HOST', data)

	def host_updateObject(self, host):
		ConfigDataBackend.host_updateObject(self, host)
		data = self._objectToDatabaseHash(host)
		where = self._uniqueCondition(host)
		self._sql.update('HOST', where, data)

	def host_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.host_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting hosts, filter: %s" % filter)
		hosts = []
		type = forceList(filter.get('type', []))
		if 'OpsiDepotserver' in type and not 'OpsiConfigserver' in type:
			type.append('OpsiConfigserver')
			filter['type'] = type
		(attributes, filter) = self._adjustAttributes(Host, attributes, filter)
		for res in self._sql.getSet(self._createQuery('HOST', attributes, filter)):
			self._adjustResult(Host, res)
			hosts.append(Host.fromHash(res))
		return hosts

	def host_deleteObjects(self, hosts):
		ConfigDataBackend.host_deleteObjects(self, hosts)
		for host in forceObjectClassList(hosts, Host):
			logger.info(u"Deleting host %s" % host)
			where = self._uniqueCondition(host)
			self._sql.delete('HOST', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Configs                                                                                   -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def config_insertObject(self, config):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.config_insertObject(self, config)
		data = self._objectToDatabaseHash(config)
		possibleValues = data['possibleValues']
		defaultValues = data['defaultValues']
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data['possibleValues']
		del data['defaultValues']

		where = self._uniqueCondition(config)
		if self._sql.getRow('select * from `CONFIG` where %s' % where):
			self._sql.update('CONFIG', where, data, updateWhereNone = True)
		else:
			self._sql.insert('CONFIG', data)

		self._sql.delete('CONFIG_VALUE', where)
		for value in possibleValues:
			self._sql.insert('CONFIG_VALUE', {
				'configId': data['configId'],
				'value': value,
				'isDefault': (value in defaultValues)
				})

	def config_updateObject(self, config):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.config_updateObject(self, config)
		data = self._objectToDatabaseHash(config)
		where = self._uniqueCondition(config)
		possibleValues = data['possibleValues']
		defaultValues = data['defaultValues']
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data['possibleValues']
		del data['defaultValues']

		self._sql.update('CONFIG', where, data)
		self._sql.delete('CONFIG_VALUE', where)
		for value in possibleValues:
			self._sql.insert('CONFIG_VALUE', {
				'configId': data['configId'],
				'value': value,
				'isDefault': (value in defaultValues)
				})

	def config_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.config_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting configs, filter: %s" % filter)
		configs = []
		(attributes, filter) = self._adjustAttributes(Config, attributes, filter)

		if filter.has_key('defaultValues'):
			if filter['defaultValues']:
				configIds = filter.get('configId')
				filter['configId'] = []
				for res in self._sql.getSet(self._createQuery('CONFIG_VALUE', ['configId'], {'configId': configIds, 'value': filter['defaultValues'], 'isDefault': True})):
					filter['configId'].append(res['configId'])
				if not filter['configId']:
					return []
			del filter['defaultValues']
		if filter.has_key('possibleValues'):
			if filter['possibleValues']:
				configIds = filter.get('configId')
				filter['configId'] = []
				for res in self._sql.getSet(self._createQuery('CONFIG_VALUE', ['configId'], {'configId': configIds, 'value': filter['possibleValues']})):
					filter['configId'].append(res['configId'])
				if not filter['configId']:
					return []
			del filter['possibleValues']
		attrs = []
		for attr in attributes:
			if not attr in ('defaultValues', 'possibleValues'):
				attrs.append(attr)
		for res in self._sql.getSet(self._createQuery('CONFIG', attrs, filter)):
			res['possibleValues'] = []
			res['defaultValues'] = []
			if not attributes or 'possibleValues' in attributes or 'defaultValues' in attributes:
				for res2 in self._sql.getSet(u"select * from CONFIG_VALUE where `configId` = '%s'" % res['configId']):
					res['possibleValues'].append(res2['value'])
					if res2['isDefault']:
						res['defaultValues'].append(res2['value'])
			self._adjustResult(Config, res)
			configs.append(Config.fromHash(res))
		return configs

	def config_deleteObjects(self, configs):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.config_deleteObjects(self, configs)
		for config in forceObjectClassList(configs, Config):
			logger.info(u"Deleting config %s" % config)
			where = self._uniqueCondition(config)
			self._sql.delete('CONFIG_VALUE', where)
			self._sql.delete('CONFIG', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.configState_insertObject(self, configState)
		data = self._objectToDatabaseHash(configState)
		data['values'] = json.dumps(data['values'])

		where = self._uniqueCondition(configState)
		if self._sql.getRow('select * from `CONFIG_STATE` where %s' % where):
			self._sql.update('CONFIG_STATE', where, data, updateWhereNone = True)
		else:
			self._sql.insert('CONFIG_STATE', data)

	def configState_updateObject(self, configState):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.configState_updateObject(self, configState)
		data = self._objectToDatabaseHash(configState)
		where = self._uniqueCondition(configState)
		data['values'] = json.dumps(data['values'])
		self._sql.update('CONFIG_STATE', where, data)

	def configState_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.configState_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting configStates, filter: %s" % filter)
		configStates = []
		(attributes, filter) = self._adjustAttributes(ConfigState, attributes, filter)
		for res in self._sql.getSet(self._createQuery('CONFIG_STATE', attributes, filter)):
			if res.has_key('values'):
				res['values'] = json.loads(res['values'])
			configStates.append(ConfigState.fromHash(res))
		return configStates

	def configState_deleteObjects(self, configStates):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.configState_deleteObjects(self, configStates)
		for configState in forceObjectClassList(configStates, ConfigState):
			logger.info("Deleting configState %s" % configState)
			where = self._uniqueCondition(configState)
			self._sql.delete('CONFIG_STATE', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Products                                                                                  -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def product_insertObject(self, product):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		backendinfo = self._context.backend_info()
		modules = backendinfo['modules']
		helpermodules = backendinfo['realmodules']

		publicKey = keys.Key.fromString(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP')).keyObject
		data = u''; mks = modules.keys(); mks.sort()
		for module in mks:
			if module in ('valid', 'signature'):
				continue
			if helpermodules.has_key(module):
				val = helpermodules[module]
				if int(val) > 0:
					modules[module] = True
			else:
				val = modules[module]
				if (val == False): val = 'no'
				if (val == True):  val = 'yes'
			data += u'%s = %s\r\n' % (module.lower().strip(), val)
		if not bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ])):
			logger.error(u"Failed to verify modules signature")
			return

		ConfigDataBackend.product_insertObject(self, product)
		data = self._objectToDatabaseHash(product)
		windowsSoftwareIds = data['windowsSoftwareIds']
		del data['windowsSoftwareIds']
		del data['productClassIds']

		where = self._uniqueCondition(product)
		if self._sql.getRow('select * from `PRODUCT` where %s' % where):
			self._sql.update('PRODUCT', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT', data)

		self._sql.delete('WINDOWS_SOFTWARE_ID_TO_PRODUCT', "`productId` = '%s'" % data['productId'])
		for windowsSoftwareId in windowsSoftwareIds:
			self._sql.insert('WINDOWS_SOFTWARE_ID_TO_PRODUCT', {'windowsSoftwareId': windowsSoftwareId, 'productId': data['productId']})

	def product_updateObject(self, product):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.product_updateObject(self, product)
		data = self._objectToDatabaseHash(product)
		where = self._uniqueCondition(product)
		windowsSoftwareIds = data['windowsSoftwareIds']
		del data['windowsSoftwareIds']
		del data['productClassIds']
		self._sql.update('PRODUCT', where, data)
		self._sql.delete('WINDOWS_SOFTWARE_ID_TO_PRODUCT', "`productId` = '%s'" % data['productId'])
		if windowsSoftwareIds:
			for windowsSoftwareId in windowsSoftwareIds:
				self._sql.insert('WINDOWS_SOFTWARE_ID_TO_PRODUCT', {'windowsSoftwareId': windowsSoftwareId, 'productId': data['productId']})

	def product_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.product_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting products, filter: %s" % filter)
		products = []
		(attributes, filter) = self._adjustAttributes(Product, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT', attributes, filter)):
			res['windowsSoftwareIds'] = []
			res['productClassIds'] = []
			if not attributes or 'windowsSoftwareIds' in attributes:
				for res2 in self._sql.getSet(u"select * from WINDOWS_SOFTWARE_ID_TO_PRODUCT where `productId` = '%s'" % res['productId']):
					res['windowsSoftwareIds'].append(res2['windowsSoftwareId'])
			if not attributes or 'productClassIds' in attributes:
				pass
			self._adjustResult(Product, res)
			products.append(Product.fromHash(res))
		return products

	def product_deleteObjects(self, products):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.product_deleteObjects(self, products)
		for product in forceObjectClassList(products, Product):
			logger.info("Deleting product %s" % product)
			where = self._uniqueCondition(product)
			self._sql.delete('WINDOWS_SOFTWARE_ID_TO_PRODUCT', "`productId` = '%s'" % product.getId())
			self._sql.delete('PRODUCT', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductProperties                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productProperty_insertObject(self, productProperty):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productProperty_insertObject(self, productProperty)
		data = self._objectToDatabaseHash(productProperty)
		possibleValues = data['possibleValues']
		defaultValues = data['defaultValues']
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data['possibleValues']
		del data['defaultValues']

		where = self._uniqueCondition(productProperty)
		if self._sql.getRow('select * from `PRODUCT_PROPERTY` where %s' % where):
			self._sql.update('PRODUCT_PROPERTY', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT_PROPERTY', data)

		if not possibleValues is None:
			self._sql.delete('PRODUCT_PROPERTY_VALUE', where)
		for value in possibleValues:
			self._sql.insert('PRODUCT_PROPERTY_VALUE', {
					'productId': data['productId'],
					'productVersion': data['productVersion'],
					'packageVersion': data['packageVersion'],
					'propertyId': data['propertyId'],
					'value': value,
					'isDefault': (value in defaultValues)
					})
	
	def productProperty_updateObject(self, productProperty):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productProperty_updateObject(self, productProperty)
		data = self._objectToDatabaseHash(productProperty)
		where = self._uniqueCondition(productProperty)
		possibleValues = data['possibleValues']
		defaultValues = data['defaultValues']
		if possibleValues is None:
			possibleValues = []
		if defaultValues is None:
			defaultValues = []
		del data['possibleValues']
		del data['defaultValues']
		self._sql.update('PRODUCT_PROPERTY', where, data)

		if not possibleValues is None:
			self._sql.delete('PRODUCT_PROPERTY_VALUE', where)

		for value in possibleValues:
			self._sql.insert('PRODUCT_PROPERTY_VALUE', {
					'productId': data['productId'],
					'productVersion': data['productVersion'],
					'packageVersion': data['packageVersion'],
					'propertyId': data['propertyId'],
					'value': value,
					'isDefault': (value in defaultValues)
					})
	
	def productProperty_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productProperty_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting product properties, filter: %s" % filter)
		productProperties = []
		(attributes, filter) = self._adjustAttributes(ProductProperty, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT_PROPERTY', attributes, filter)):
			res['possibleValues'] = []
			res['defaultValues'] = []
			if not attributes or 'possibleValues' in attributes or 'defaultValues' in attributes:
				for res2 in self._sql.getSet(u"select * from PRODUCT_PROPERTY_VALUE where " \
					+ u"`propertyId` = '%s' AND `productId` = '%s' AND `productVersion` = '%s' AND `packageVersion` = '%s'" \
					% (res['propertyId'], res['productId'], res['productVersion'], res['packageVersion'])):
					res['possibleValues'].append(res2['value'])
					if res2['isDefault']:
						res['defaultValues'].append(res2['value'])
			productProperties.append(ProductProperty.fromHash(res))
		return productProperties

	def productProperty_deleteObjects(self, productProperties):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productProperty_deleteObjects(self, productProperties)
		for productProperty in forceObjectClassList(productProperties, ProductProperty):
			logger.info("Deleting product property %s" % productProperty)
			where = self._uniqueCondition(productProperty)
			self._sql.delete('PRODUCT_PROPERTY_VALUE', where)
			self._sql.delete('PRODUCT_PROPERTY', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductDependencies                                                                         -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productDependency_insertObject(self, productDependency):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productDependency_insertObject(self, productDependency)
		data = self._objectToDatabaseHash(productDependency)

		where = self._uniqueCondition(productDependency)
		if self._sql.getRow('select * from `PRODUCT_DEPENDENCY` where %s' % where):
			self._sql.update('PRODUCT_DEPENDENCY', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT_DEPENDENCY', data)

	def productDependency_updateObject(self, productDependency):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productDependency_updateObject(self, productDependency)
		data = self._objectToDatabaseHash(productDependency)
		where = self._uniqueCondition(productDependency)

		self._sql.update('PRODUCT_DEPENDENCY', where, data)

	def productDependency_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productDependency_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting product dependencies, filter: %s" % filter)
		productDependencies = []
		(attributes, filter) = self._adjustAttributes(ProductDependency, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT_DEPENDENCY', attributes, filter)):
			productDependencies.append(ProductDependency.fromHash(res))
		return productDependencies

	def productDependency_deleteObjects(self, productDependencies):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productDependency_deleteObjects(self, productDependencies)
		for productDependency in forceObjectClassList(productDependencies, ProductDependency):
			logger.info("Deleting product dependency %s" % productDependency)
			where = self._uniqueCondition(productDependency)
			self._sql.delete('PRODUCT_DEPENDENCY', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnDepots                                                                           -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnDepot_insertObject(self, productOnDepot):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnDepot_insertObject(self, productOnDepot)
		data = self._objectToDatabaseHash(productOnDepot)

		productOnDepotClone = productOnDepot.clone(identOnly = True)
		productOnDepotClone.productVersion = None
		productOnDepotClone.packageVersion = None
		productOnDepotClone.productType = None
		where = self._uniqueCondition(productOnDepotClone)
		if self._sql.getRow('select * from `PRODUCT_ON_DEPOT` where %s' % where):
			self._sql.update('PRODUCT_ON_DEPOT', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT_ON_DEPOT', data)

	def productOnDepot_updateObject(self, productOnDepot):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnDepot_updateObject(self, productOnDepot)
		data = self._objectToDatabaseHash(productOnDepot)
		where = self._uniqueCondition(productOnDepot)
		self._sql.update('PRODUCT_ON_DEPOT', where, data)

	def productOnDepot_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnDepot_getObjects(self, attributes=[], **filter)
		productOnDepots = []
		(attributes, filter) = self._adjustAttributes(ProductOnDepot, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT_ON_DEPOT', attributes, filter)):
			productOnDepots.append(ProductOnDepot.fromHash(res))
		return productOnDepots

	def productOnDepot_deleteObjects(self, productOnDepots):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnDepot_deleteObjects(self, productOnDepots)
		for productOnDepot in forceObjectClassList(productOnDepots, ProductOnDepot):
			logger.info(u"Deleting productOnDepot %s" % productOnDepot)
			where = self._uniqueCondition(productOnDepot)
			self._sql.delete('PRODUCT_ON_DEPOT', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnClient_insertObject(self, productOnClient)
		data = self._objectToDatabaseHash(productOnClient)

		productOnClientClone = productOnClient.clone(identOnly = True)
		productOnClientClone.productVersion = None
		productOnClientClone.packageVersion = None
		productOnClientClone.productType = None
		where = self._uniqueCondition(productOnClientClone)

		if self._sql.getRow('select * from `PRODUCT_ON_CLIENT` where %s' % where):
			self._sql.update('PRODUCT_ON_CLIENT', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT_ON_CLIENT', data)

	def productOnClient_updateObject(self, productOnClient):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnClient_updateObject(self, productOnClient)
		data = self._objectToDatabaseHash(productOnClient)
		where = self._uniqueCondition(productOnClient)
		self._sql.update('PRODUCT_ON_CLIENT', where, data)

	def productOnClient_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnClient_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting productOnClients, filter: %s" % filter)
		productOnClients = []
		(attributes, filter) = self._adjustAttributes(ProductOnClient, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT_ON_CLIENT', attributes, filter)):
			productOnClients.append(ProductOnClient.fromHash(res))
		return productOnClients

	def productOnClient_deleteObjects(self, productOnClients):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productOnClient_deleteObjects(self, productOnClients)
		for productOnClient in forceObjectClassList(productOnClients, ProductOnClient):
			logger.info(u"Deleting productOnClient %s" % productOnClient)
			where = self._uniqueCondition(productOnClient)
			self._sql.delete('PRODUCT_ON_CLIENT', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductPropertyStates                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productPropertyState_insertObject(self, productPropertyState):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productPropertyState_insertObject(self, productPropertyState)
		if not self._sql.getSet(self._createQuery('HOST', ['hostId'], {"hostId": productPropertyState.objectId})):
			raise BackendReferentialIntegrityError(u"Object '%s' does not exist" % productPropertyState.objectId)
		data = self._objectToDatabaseHash(productPropertyState)
		data['values'] = json.dumps(data['values'])

		where = self._uniqueCondition(productPropertyState)
		if self._sql.getRow('select * from `PRODUCT_PROPERTY_STATE` where %s' % where):
			self._sql.update('PRODUCT_PROPERTY_STATE', where, data, updateWhereNone = True)
		else:
			self._sql.insert('PRODUCT_PROPERTY_STATE', data)

	def productPropertyState_updateObject(self, productPropertyState):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productPropertyState_updateObject(self, productPropertyState)
		data = self._objectToDatabaseHash(productPropertyState)
		where = self._uniqueCondition(productPropertyState)
		data['values'] = json.dumps(data['values'])
		self._sql.update('PRODUCT_PROPERTY_STATE', where, data)

	def productPropertyState_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productPropertyState_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting productPropertyStates, filter: %s" % filter)
		productPropertyStates = []
		(attributes, filter) = self._adjustAttributes(ProductPropertyState, attributes, filter)
		for res in self._sql.getSet(self._createQuery('PRODUCT_PROPERTY_STATE', attributes, filter)):
			if res.has_key('values'):
				res['values'] = json.loads(res['values'])
			productPropertyStates.append(ProductPropertyState.fromHash(res))
		return productPropertyStates

	def productPropertyState_deleteObjects(self, productPropertyStates):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.productPropertyState_deleteObjects(self, productPropertyStates)
		for productPropertyState in forceObjectClassList(productPropertyStates, ProductPropertyState):
			logger.info(u"Deleting productPropertyState %s" % productPropertyState)
			where = self._uniqueCondition(productPropertyState)
			self._sql.delete('PRODUCT_PROPERTY_STATE', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Groups                                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def group_insertObject(self, group):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.group_insertObject(self, group)
		data = self._objectToDatabaseHash(group)

		where = self._uniqueCondition(group)
		if self._sql.getRow('select * from `GROUP` where %s' % where):
			self._sql.update('GROUP', where, data, updateWhereNone = True)
		else:
			self._sql.insert('GROUP', data)

	def group_updateObject(self, group):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.group_updateObject(self, group)
		data = self._objectToDatabaseHash(group)
		where = self._uniqueCondition(group)
		self._sql.update('GROUP', where, data)

	def group_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.group_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting groups, filter: %s" % filter)
		groups = []
		(attributes, filter) = self._adjustAttributes(Group, attributes, filter)
		for res in self._sql.getSet(self._createQuery('GROUP', attributes, filter)):
			self._adjustResult(Group, res)
			groups.append(Group.fromHash(res))
		return groups

	def group_deleteObjects(self, groups):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.group_deleteObjects(self, groups)
		for group in forceObjectClassList(groups, Group):
			logger.info(u"Deleting group %s" % group)
			where = self._uniqueCondition(group)
			self._sql.delete('GROUP', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ObjectToGroups                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def objectToGroup_insertObject(self, objectToGroup):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.objectToGroup_insertObject(self, objectToGroup)
		data = self._objectToDatabaseHash(objectToGroup)

		where = self._uniqueCondition(objectToGroup)
		if self._sql.getRow('select * from `OBJECT_TO_GROUP` where %s' % where):
			self._sql.update('OBJECT_TO_GROUP', where, data, updateWhereNone = True)
		else:
			self._sql.insert('OBJECT_TO_GROUP', data)

	def objectToGroup_updateObject(self, objectToGroup):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.objectToGroup_updateObject(self, objectToGroup)
		data = self._objectToDatabaseHash(objectToGroup)
		where = self._uniqueCondition(objectToGroup)
		self._sql.update('OBJECT_TO_GROUP', where, data)

	def objectToGroup_getObjects(self, attributes=[], **filter):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.objectToGroup_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting objectToGroups, filter: %s" % filter)
		objectToGroups = []
		(attributes, filter) = self._adjustAttributes(ObjectToGroup, attributes, filter)
		for res in self._sql.getSet(self._createQuery('OBJECT_TO_GROUP', attributes, filter)):
			objectToGroups.append(ObjectToGroup.fromHash(res))
		return objectToGroups

	def objectToGroup_deleteObjects(self, objectToGroups):
		if not self._sqlBackendModule:
			raise Exception(u"SQL backend module disabled")

		ConfigDataBackend.objectToGroup_deleteObjects(self, objectToGroups)
		for objectToGroup in forceObjectClassList(objectToGroups, ObjectToGroup):
			logger.info(u"Deleting objectToGroup %s" % objectToGroup)
			where = self._uniqueCondition(objectToGroup)
			self._sql.delete('OBJECT_TO_GROUP', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseContracts                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseContract_insertObject(self, licenseContract):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseContract_insertObject(self, licenseContract)
		data = self._objectToDatabaseHash(licenseContract)

		where = self._uniqueCondition(licenseContract)
		if self._sql.getRow('select * from `LICENSE_CONTRACT` where %s' % where):
			self._sql.update('LICENSE_CONTRACT', where, data, updateWhereNone = True)
		else:
			self._sql.insert('LICENSE_CONTRACT', data)

	def licenseContract_updateObject(self, licenseContract):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseContract_updateObject(self, licenseContract)
		data = self._objectToDatabaseHash(licenseContract)
		where = self._uniqueCondition(licenseContract)
		self._sql.update('LICENSE_CONTRACT', where, data)

	def licenseContract_getObjects(self, attributes=[], **filter):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return []

		ConfigDataBackend.licenseContract_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting licenseContracts, filter: %s" % filter)
		licenseContracts = []
		(attributes, filter) = self._adjustAttributes(LicenseContract, attributes, filter)
		for res in self._sql.getSet(self._createQuery('LICENSE_CONTRACT', attributes, filter)):
			self._adjustResult(LicenseContract, res)
			licenseContracts.append(LicenseContract.fromHash(res))
		return licenseContracts

	def licenseContract_deleteObjects(self, licenseContracts):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseContract_deleteObjects(self, licenseContracts)
		for licenseContract in forceObjectClassList(licenseContracts, LicenseContract):
			logger.info(u"Deleting licenseContract %s" % licenseContract)
			where = self._uniqueCondition(licenseContract)
			self._sql.delete('LICENSE_CONTRACT', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenses                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicense_insertObject(self, softwareLicense):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicense_insertObject(self, softwareLicense)
		data = self._objectToDatabaseHash(softwareLicense)

		where = self._uniqueCondition(softwareLicense)
		if self._sql.getRow('select * from `SOFTWARE_LICENSE` where %s' % where):
			self._sql.update('SOFTWARE_LICENSE', where, data, updateWhereNone = True)
		else:
			self._sql.insert('SOFTWARE_LICENSE', data)

	def softwareLicense_updateObject(self, softwareLicense):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicense_updateObject(self, softwareLicense)
		data = self._objectToDatabaseHash(softwareLicense)
		where = self._uniqueCondition(softwareLicense)
		self._sql.update('SOFTWARE_LICENSE', where, data)

	def softwareLicense_getObjects(self, attributes=[], **filter):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return []

		ConfigDataBackend.softwareLicense_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting softwareLicenses, filter: %s" % filter)
		softwareLicenses = []
		(attributes, filter) = self._adjustAttributes(SoftwareLicense, attributes, filter)
		for res in self._sql.getSet(self._createQuery('SOFTWARE_LICENSE', attributes, filter)):
			self._adjustResult(SoftwareLicense, res)
			softwareLicenses.append(SoftwareLicense.fromHash(res))
		return softwareLicenses

	def softwareLicense_deleteObjects(self, softwareLicenses):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicense_deleteObjects(self, softwareLicenses)
		for softwareLicense in forceObjectClassList(softwareLicenses, SoftwareLicense):
			logger.info(u"Deleting softwareLicense %s" % softwareLicense)
			where = self._uniqueCondition(softwareLicense)
			self._sql.delete('SOFTWARE_LICENSE', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicensePools                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licensePool_insertObject(self, licensePool):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		backendinfo = self._context.backend_info()
		modules = backendinfo['modules']
		helpermodules = backendinfo['realmodules']

		publicKey = keys.Key.fromString(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP')).keyObject
		data = u''; mks = modules.keys(); mks.sort()
		for module in mks:
			if module in ('valid', 'signature'):
				continue

			if helpermodules.has_key(module):
				val = helpermodules[module]
				if int(val) > 0:
					modules[module] = True
			else:
				val = modules[module]
				if (val == False): val = 'no'
				if (val == True):  val = 'yes'

			data += u'%s = %s\r\n' % (module.lower().strip(), val)
		if not bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ])):
			logger.error(u"Failed to verify modules signature")
			return

		ConfigDataBackend.licensePool_insertObject(self, licensePool)
		data = self._objectToDatabaseHash(licensePool)
		productIds = data['productIds']
		del data['productIds']

		where = self._uniqueCondition(licensePool)
		if self._sql.getRow('select * from `LICENSE_POOL` where %s' % where):
			self._sql.update('LICENSE_POOL', where, data, updateWhereNone = True)
		else:
			self._sql.insert('LICENSE_POOL', data)

		self._sql.delete('PRODUCT_ID_TO_LICENSE_POOL', "`licensePoolId` = '%s'" % data['licensePoolId'])
		for productId in productIds:
			self._sql.insert('PRODUCT_ID_TO_LICENSE_POOL', {'productId': productId, 'licensePoolId': data['licensePoolId']})

	def licensePool_updateObject(self, licensePool):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licensePool_updateObject(self, licensePool)
		data = self._objectToDatabaseHash(licensePool)
		where = self._uniqueCondition(licensePool)
		productIds = data['productIds']
		del data['productIds']
		self._sql.update('LICENSE_POOL', where, data)
		self._sql.delete('PRODUCT_ID_TO_LICENSE_POOL', "`licensePoolId` = '%s'" % data['licensePoolId'])
		for productId in productIds:
			self._sql.insert('PRODUCT_ID_TO_LICENSE_POOL', {'productId': productId, 'licensePoolId': data['licensePoolId']})

	def licensePool_getObjects(self, attributes=[], **filter):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return []

		ConfigDataBackend.licensePool_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting licensePools, filter: %s" % filter)
		licensePools = []
		(attributes, filter) = self._adjustAttributes(LicensePool, attributes, filter)

		if filter.has_key('productIds'):
			if filter['productIds']:
				licensePoolIds = filter.get('licensePoolId')
				filter['licensePoolId'] = []
				for res in self._sql.getSet(self._createQuery('PRODUCT_ID_TO_LICENSE_POOL', ['licensePoolId'], {'licensePoolId': licensePoolIds, 'productId': filter['productIds']})):
					filter['licensePoolId'].append(res['licensePoolId'])
				if not filter['licensePoolId']:
					return []
			del filter['productIds']
		attrs = []
		for attr in attributes:
			if not attr in ('productIds',):
				attrs.append(attr)
		for res in self._sql.getSet(self._createQuery('LICENSE_POOL', attrs, filter)):
			res['productIds'] = []
			if not attributes or 'productIds' in attributes:
				for res2 in self._sql.getSet(u"select * from PRODUCT_ID_TO_LICENSE_POOL where `licensePoolId` = '%s'" % res['licensePoolId']):
					res['productIds'].append(res2['productId'])
			self._adjustResult(LicensePool, res)
			licensePools.append(LicensePool.fromHash(res))
		return licensePools

	def licensePool_deleteObjects(self, licensePools):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licensePool_deleteObjects(self, licensePools)
		for licensePool in forceObjectClassList(licensePools, LicensePool):
			logger.info(u"Deleting licensePool %s" % licensePool)
			where = self._uniqueCondition(licensePool)
			self._sql.delete('PRODUCT_ID_TO_LICENSE_POOL', "`licensePoolId` = '%s'" % licensePool.id)
			self._sql.delete('LICENSE_POOL', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   SoftwareLicenseToLicensePools                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def softwareLicenseToLicensePool_insertObject(self, softwareLicenseToLicensePool):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicenseToLicensePool_insertObject(self, softwareLicenseToLicensePool)
		data = self._objectToDatabaseHash(softwareLicenseToLicensePool)

		where = self._uniqueCondition(softwareLicenseToLicensePool)
		if self._sql.getRow('select * from `SOFTWARE_LICENSE_TO_LICENSE_POOL` where %s' % where):
			self._sql.update('SOFTWARE_LICENSE_TO_LICENSE_POOL', where, data, updateWhereNone = True)
		else:
			self._sql.insert('SOFTWARE_LICENSE_TO_LICENSE_POOL', data)

	def softwareLicenseToLicensePool_updateObject(self, softwareLicenseToLicensePool):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicenseToLicensePool_updateObject(self, softwareLicenseToLicensePool)
		data = self._objectToDatabaseHash(softwareLicenseToLicensePool)
		where = self._uniqueCondition(softwareLicenseToLicensePool)
		self._sql.update('SOFTWARE_LICENSE_TO_LICENSE_POOL', where, data)

	def softwareLicenseToLicensePool_getObjects(self, attributes=[], **filter):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return []

		ConfigDataBackend.softwareLicenseToLicensePool_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting softwareLicenseToLicensePool, filter: %s" % filter)
		softwareLicenseToLicensePools = []
		(attributes, filter) = self._adjustAttributes(SoftwareLicenseToLicensePool, attributes, filter)
		for res in self._sql.getSet(self._createQuery('SOFTWARE_LICENSE_TO_LICENSE_POOL', attributes, filter)):
			softwareLicenseToLicensePools.append(SoftwareLicenseToLicensePool.fromHash(res))
		return softwareLicenseToLicensePools

	def softwareLicenseToLicensePool_deleteObjects(self, softwareLicenseToLicensePools):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.softwareLicenseToLicensePool_deleteObjects(self, softwareLicenseToLicensePools)
		for softwareLicenseToLicensePool in forceObjectClassList(softwareLicenseToLicensePools, SoftwareLicenseToLicensePool):
			logger.info(u"Deleting softwareLicenseToLicensePool %s" % softwareLicenseToLicensePool)
			where = self._uniqueCondition(softwareLicenseToLicensePool)
			self._sql.delete('SOFTWARE_LICENSE_TO_LICENSE_POOL', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   LicenseOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def licenseOnClient_insertObject(self, licenseOnClient):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseOnClient_insertObject(self, licenseOnClient)
		data = self._objectToDatabaseHash(licenseOnClient)

		where = self._uniqueCondition(licenseOnClient)
		if self._sql.getRow('select * from `LICENSE_ON_CLIENT` where %s' % where):
			self._sql.update('LICENSE_ON_CLIENT', where, data, updateWhereNone = True)
		else:
			self._sql.insert('LICENSE_ON_CLIENT', data)

	def licenseOnClient_updateObject(self, licenseOnClient):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseOnClient_updateObject(self, licenseOnClient)
		data = self._objectToDatabaseHash(licenseOnClient)
		where = self._uniqueCondition(licenseOnClient)
		self._sql.update('LICENSE_ON_CLIENT', where, data)

	def licenseOnClient_getObjects(self, attributes=[], **filter):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return []

		ConfigDataBackend.licenseOnClient_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting licenseOnClient, filter: %s" % filter)
		licenseOnClients = []
		(attributes, filter) = self._adjustAttributes(LicenseOnClient, attributes, filter)
		for res in self._sql.getSet(self._createQuery('LICENSE_ON_CLIENT', attributes, filter)):
			licenseOnClients.append(LicenseOnClient.fromHash(res))
		return licenseOnClients

	def licenseOnClient_deleteObjects(self, licenseOnClients):
		if not self._licenseManagementModule:
			logger.warning(u"License management module disabled")
			return

		ConfigDataBackend.licenseOnClient_deleteObjects(self, licenseOnClients)
		for licenseOnClient in forceObjectClassList(licenseOnClients, LicenseOnClient):
			logger.info(u"Deleting licenseOnClient %s" % licenseOnClient)
			where = self._uniqueCondition(licenseOnClient)
			self._sql.delete('LICENSE_ON_CLIENT', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftware_insertObject(self, auditSoftware):
		ConfigDataBackend.auditSoftware_insertObject(self, auditSoftware)
		data = self._objectToDatabaseHash(auditSoftware)

		where = self._uniqueCondition(auditSoftware)
		if self._sql.getRow('select * from `SOFTWARE` where %s' % where):
			self._sql.update('SOFTWARE', where, data, updateWhereNone = True)
		else:
			self._sql.insert('SOFTWARE', data)

	def auditSoftware_updateObject(self, auditSoftware):
		ConfigDataBackend.auditSoftware_updateObject(self, auditSoftware)
		data = self._objectToDatabaseHash(auditSoftware)
		where = self._uniqueCondition(auditSoftware)
		self._sql.update('SOFTWARE', where, data)

	def auditSoftware_getHashes(self, attributes=[], **filter):
		(attributes, filter) = self._adjustAttributes(AuditSoftware, attributes, filter)
		return self._sql.getSet(self._createQuery('SOFTWARE', attributes, filter))

	def auditSoftware_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditSoftware_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting auditSoftware, filter: %s" % filter)
		auditSoftwares = []
		for h in self.auditSoftware_getHashes(attributes, **filter):
			auditSoftwares.append(AuditSoftware.fromHash(h))
		return auditSoftwares

	def auditSoftware_deleteObjects(self, auditSoftwares):
		ConfigDataBackend.auditSoftware_deleteObjects(self, auditSoftwares)
		for auditSoftware in forceObjectClassList(auditSoftwares, AuditSoftware):
			logger.info(u"Deleting auditSoftware %s" % auditSoftware)
			where = self._uniqueCondition(auditSoftware)
			self._sql.delete('SOFTWARE', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareToLicensePools                                                               -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareToLicensePool_insertObject(self, auditSoftwareToLicensePool):
		ConfigDataBackend.auditSoftwareToLicensePool_insertObject(self, auditSoftwareToLicensePool)
		data = self._objectToDatabaseHash(auditSoftwareToLicensePool)

		where = self._uniqueCondition(auditSoftwareToLicensePool)
		if self._sql.getRow('select * from `AUDIT_SOFTWARE_TO_LICENSE_POOL` where %s' % where):
			self._sql.update('AUDIT_SOFTWARE_TO_LICENSE_POOL', where, data, updateWhereNone = True)
		else:
			self._sql.insert('AUDIT_SOFTWARE_TO_LICENSE_POOL', data)

	def auditSoftwareToLicensePool_updateObject(self, auditSoftwareToLicensePool):
		ConfigDataBackend.auditSoftwareToLicensePool_updateObject(self, auditSoftwareToLicensePool)
		data = self._objectToDatabaseHash(auditSoftwareToLicensePool)
		where = self._uniqueCondition(auditSoftwareToLicensePool)
		self._sql.update('AUDIT_SOFTWARE_TO_LICENSE_POOL', where, data)

	def auditSoftwareToLicensePool_getHashes(self, attributes=[], **filter):
		(attributes, filter) = self._adjustAttributes(AuditSoftwareToLicensePool, attributes, filter)
		return self._sql.getSet(self._createQuery('AUDIT_SOFTWARE_TO_LICENSE_POOL', attributes, filter))

	def auditSoftwareToLicensePool_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditSoftwareToLicensePool_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting auditSoftwareToLicensePool, filter: %s" % filter)
		auditSoftwareToLicensePools = []
		for h in self.auditSoftwareToLicensePool_getHashes(attributes, **filter):
			auditSoftwareToLicensePools.append(AuditSoftwareToLicensePool.fromHash(h))
		return auditSoftwareToLicensePools

	def auditSoftwareToLicensePool_deleteObjects(self, auditSoftwareToLicensePools):
		ConfigDataBackend.auditSoftwareToLicensePool_deleteObjects(self, auditSoftwareToLicensePools)
		for auditSoftwareToLicensePool in forceObjectClassList(auditSoftwareToLicensePools, AuditSoftwareToLicensePool):
			logger.info(u"Deleting auditSoftware %s" % auditSoftwareToLicensePool)
			where = self._uniqueCondition(auditSoftwareToLicensePool)
			self._sql.delete('AUDIT_SOFTWARE_TO_LICENSE_POOL', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditSoftwareOnClients                                                                    -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient):
		ConfigDataBackend.auditSoftwareOnClient_insertObject(self, auditSoftwareOnClient)
		data = self._objectToDatabaseHash(auditSoftwareOnClient)

		where = self._uniqueCondition(auditSoftwareOnClient)
		if self._sql.getRow('select * from `SOFTWARE_CONFIG` where %s' % where):
			self._sql.update('SOFTWARE_CONFIG', where, data, updateWhereNone = True)
		else:
			self._sql.insert('SOFTWARE_CONFIG', data)

	def auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient):
		ConfigDataBackend.auditSoftwareOnClient_updateObject(self, auditSoftwareOnClient)
		data = self._objectToDatabaseHash(auditSoftwareOnClient)
		where = self._uniqueCondition(auditSoftwareOnClient)
		self._sql.update('SOFTWARE_CONFIG', where, data)

	def auditSoftwareOnClient_getHashes(self, attributes=[], **filter):
		(attributes, filter) = self._adjustAttributes(AuditSoftwareOnClient, attributes, filter)
		return self._sql.getSet(self._createQuery('SOFTWARE_CONFIG', attributes, filter))

	def auditSoftwareOnClient_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditSoftwareOnClient_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting auditSoftwareOnClient, filter: %s" % filter)
		auditSoftwareOnClients = []
		for h in self.auditSoftwareOnClient_getHashes(attributes, **filter):
			auditSoftwareOnClients.append(AuditSoftwareOnClient.fromHash(h))
		return auditSoftwareOnClients

	def auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients):
		ConfigDataBackend.auditSoftwareOnClient_deleteObjects(self, auditSoftwareOnClients)
		for auditSoftwareOnClient in forceObjectClassList(auditSoftwareOnClients, AuditSoftwareOnClient):
			logger.info(u"Deleting auditSoftwareOnClient %s" % auditSoftwareOnClient)
			where = self._uniqueCondition(auditSoftwareOnClient)
			self._sql.delete('SOFTWARE_CONFIG', where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwares                                                                            -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _uniqueAuditHardwareCondition(self, auditHardware):
		if hasattr(auditHardware, 'toHash'):
			auditHardware = auditHardware.toHash()

		condition = u''
		for (attribute, value) in auditHardware.items():
			if attribute in ('hardwareClass', 'type'):
				continue
			if condition:
				condition += u' and '
			if value is None or (value == [None]):
				condition += u"`%s` is NULL" % attribute
			elif type(value) in (float, long, int, bool):
				condition += u"`%s` = %s" % (attribute, value)
			else:
				condition += u"`%s` = '%s'" % (attribute, self._sql.escapeApostrophe(self._sql.escapeBackslash(value)))
		return condition

	def _getHardwareIds(self, auditHardware):
		if hasattr(auditHardware, 'toHash'):
			auditHardware = auditHardware.toHash()

		for (attribute, value) in auditHardware.items():
			if value is None:
				auditHardware[attribute] = [ None ]
			elif type(value) is unicode:
				auditHardware[attribute] = self._sql.escapeAsterisk(value)

		logger.debug(u"Getting hardware ids, filter %s" % auditHardware)
		hardwareIds = self._auditHardware_search(returnHardwareIds = True, attributes=[], **auditHardware)
		logger.debug(u"Found hardware ids: %s" % hardwareIds)
		return hardwareIds

	def auditHardware_insertObject(self, auditHardware):
		ConfigDataBackend.auditHardware_insertObject(self, auditHardware)

		logger.info(u"Inserting auditHardware: %s" % auditHardware)
		filter = {}
		for (attribute, value) in auditHardware.toHash().items():
			if value is None:
				filter[attribute] = [ None ]
			elif type(value) is unicode:
				filter[attribute] = self._sql.escapeAsterisk(value)
			else:
				filter[attribute] = value
		res = self.auditHardware_getObjects(**filter)
		if res:
			return

		data = auditHardware.toHash()
		table = u'HARDWARE_DEVICE_' + data['hardwareClass']
		del data['hardwareClass']
		del data['type']

		self._sql.insert(table, data)

	def auditHardware_updateObject(self, auditHardware):
		ConfigDataBackend.auditHardware_updateObject(self, auditHardware)

		logger.info(u"Updating auditHardware: %s" % auditHardware)
		filter = {}
		for (attribute, value) in auditHardware.toHash().items():
			if value is None:
				filter[attribute] = [ None ]
		if not self.auditHardware_getObjects(**filter):
			raise Exception(u"AuditHardware '%s' not found" % auditHardware.getIdent())

	def auditHardware_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditHardware_getObjects(self, attributes=[], **filter)

		logger.info(u"Getting auditHardwares, filter: %s" % filter)
		auditHardwares = []
		for h in self.auditHardware_getHashes(attributes, **filter):
			auditHardwares.append(AuditHardware.fromHash(h))
		return auditHardwares

	def auditHardware_getHashes(self, attributes=[], **filter):
		return self._auditHardware_search(returnHardwareIds = False, attributes = attributes, **filter)

	def _auditHardware_search(self, returnHardwareIds=False, attributes=[], **filter):
		results = []
		hardwareClasses = []
		hardwareClass = filter.get('hardwareClass')
		if not hardwareClass in ([], None):
			for hwc in forceUnicodeList(hardwareClass):
				regex = re.compile(u'^' + hwc.replace('*', '.*') + u'$')
				for key in self._auditHardwareConfig.keys():
					if regex.search(key):
						if not key in hardwareClasses:
							hardwareClasses.append(key)
			if not hardwareClasses:
				return results
		if not hardwareClasses:
			for key in self._auditHardwareConfig.keys():
				hardwareClasses.append(key)

		if filter.has_key('hardwareClass'):
			del filter['hardwareClass']
		if filter.has_key('type'):
			del filter['type']

		if 'hardwareClass' in attributes:
			attributes.remove('hardwareClass')
		for attribute in attributes:
			if not filter.has_key(attribute):
				filter[attribute] = None

		if returnHardwareIds and attributes and not 'hardware_id' in attributes:
			attributes.append('hardware_id')

		for hardwareClass in hardwareClasses:
			classFilter = {}
			skipHardwareClass = False
			for (attribute, value) in filter.items():
				valueInfo = self._auditHardwareConfig[hardwareClass].get(attribute)
				if not valueInfo:
					skipHardwareClass = True
					logger.debug(u"Skipping hardwareClass '%s', because of missing info for attribute '%s'" % (hardwareClass, attribute))
					break
				if (valueInfo.get('Scope', '') != 'g'):
					continue
				if not value is None:
					value = forceList(value)
				classFilter[attribute] = value

			if skipHardwareClass:
				continue

			if not classFilter and filter:
				continue

			logger.debug(u"Getting auditHardwares, hardwareClass '%s', filter: %s" % (hardwareClass, classFilter))
			query = self._createQuery(u'HARDWARE_DEVICE_' + hardwareClass, attributes, classFilter)
			for res in self._sql.getSet(query):
				if returnHardwareIds:
					results.append(res['hardware_id'])
					continue
				elif res.has_key('hardware_id'):
					del res['hardware_id']
				res['hardwareClass'] = hardwareClass
				for (attribute, valueInfo) in self._auditHardwareConfig[hardwareClass].items():
					if (valueInfo.get('Scope', 'g') == 'i'):
						continue
					if not res.has_key(attribute):
						res[attribute] = None
				results.append(res)
		return results

	def auditHardware_deleteObjects(self, auditHardwares):
		ConfigDataBackend.auditHardware_deleteObjects(self, auditHardwares)
		for auditHardware in forceObjectClassList(auditHardwares, AuditHardware):
			logger.info(u"Deleting auditHardware: %s" % auditHardware)

			where = self._uniqueAuditHardwareCondition(auditHardware)
			for hardware_id in self._getHardwareIds(auditHardware):
				self._sql.delete( u'HARDWARE_CONFIG_' + auditHardware.getHardwareClass(), u'`hardware_id` = %s' % hardware_id)
			self._sql.delete( u'HARDWARE_DEVICE_' + auditHardware.getHardwareClass(), where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   AuditHardwareOnHosts                                                                      -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def _extractAuditHardwareHash(self, auditHardwareOnHost):
		if hasattr(auditHardwareOnHost, 'toHash'):
			auditHardwareOnHost = auditHardwareOnHost.toHash()

		hardwareClass = auditHardwareOnHost['hardwareClass']

		auditHardware = { 'type': 'AuditHardware' }
		auditHardwareOnHostNew = {}
		for (attribute, value) in auditHardwareOnHost.items():
			#if value is None or (attribute == 'type'):
			#	continue
			if (attribute == 'type'):
				continue
			if attribute in ('hostId', 'state', 'firstseen', 'lastseen'):
				auditHardwareOnHostNew[attribute] = value
				continue
			if attribute in ('hardwareClass',):
				auditHardware[attribute] = value
				auditHardwareOnHostNew[attribute] = value
				continue
			valueInfo = self._auditHardwareConfig[hardwareClass].get(attribute)
			if valueInfo is None:
				raise BackendConfigurationError(u"Attribute '%s' not found in config of hardware class '%s'" % (attribute, hardwareClass))
			scope = valueInfo.get('Scope', '')
			if (scope == 'g'):
				auditHardware[attribute] = value
				continue
			auditHardwareOnHostNew[attribute] = value

		return (auditHardware, auditHardwareOnHostNew)

	def _uniqueAuditHardwareOnHostCondition(self, auditHardwareOnHost):
		(auditHardware, auditHardwareOnHost) = self._extractAuditHardwareHash(auditHardwareOnHost)

		hardwareClass = auditHardwareOnHost['hardwareClass']
		del auditHardwareOnHost['hardwareClass']

		filter = {}
		for (attribute, value) in auditHardwareOnHost.items():
			if value is None:
				filter[attribute] = [ None ]
			elif type(value) is unicode:
				filter[attribute] = self._sql.escapeAsterisk(value)
			else:
				filter[attribute] = value

		where = self._filterToSql(filter)

		hwIdswhere = u''
		for hardwareId in self._getHardwareIds(auditHardware):
			if hwIdswhere: hwIdswhere += u' or '
			hwIdswhere += u'`hardware_id` = %s' % hardwareId
		if not hwIdswhere:
			raise BackendReferentialIntegrityError(u"Hardware device %s not found" % auditHardware)
		return where + u' and (%s)' % hwIdswhere

	def _auditHardwareOnHostObjectToDatabaseHash(self, auditHardwareOnHost):
		(auditHardware, auditHardwareOnHost) = self._extractAuditHardwareHash(auditHardwareOnHost)

		hardwareClass = auditHardwareOnHost['hardwareClass']

		data = {}
		for (attribute, value) in auditHardwareOnHost.items():
			if attribute in ('hardwareClass', 'type'):
				continue
			data[attribute] = value

		for (key, value) in auditHardware.items():
			if value is None:
				auditHardware[key] = [ None ]
		hardwareIds = self._getHardwareIds(auditHardware)
		if not hardwareIds:
			raise BackendReferentialIntegrityError(u"Hardware device %s not found" % auditHardware)
		data['hardware_id'] = hardwareIds[0]
		return data

	def auditHardwareOnHost_insertObject(self, auditHardwareOnHost):
		ConfigDataBackend.auditHardwareOnHost_insertObject(self, auditHardwareOnHost)

		hardwareClass = auditHardwareOnHost.getHardwareClass()
		table = u'HARDWARE_CONFIG_' + hardwareClass

		where = self._uniqueAuditHardwareOnHostCondition(auditHardwareOnHost)
		if not self._sql.getRow('select * from `%s` where %s' % (table, where)):
			data = self._auditHardwareOnHostObjectToDatabaseHash(auditHardwareOnHost)
			self._sql.insert(table, data)

	def auditHardwareOnHost_updateObject(self, auditHardwareOnHost):
		ConfigDataBackend.auditHardwareOnHost_updateObject(self, auditHardwareOnHost)

		logger.info(u"Updating auditHardwareOnHost: %s" % auditHardwareOnHost)
		data = auditHardwareOnHost.toHash()
		update = {}
		for (attribute, value) in data.items():
			if attribute in ('state', 'lastseen', 'firstseen'):
				if not value is None:
					update[attribute] = value
				del data[attribute]
		if update:
			where = self._uniqueAuditHardwareOnHostCondition(data)
			self._sql.update('HARDWARE_CONFIG_%s' % auditHardwareOnHost.hardwareClass, where, update)

	def auditHardwareOnHost_getHashes(self, attributes=[], **filter):
		hashes = []
		hardwareClasses = []
		hardwareClass = filter.get('hardwareClass')
		if not hardwareClass in ([], None):
			for hwc in forceUnicodeList(hardwareClass):
				regex = re.compile(u'^' + hwc.replace('*', '.*') + u'$')
				for key in self._auditHardwareConfig.keys():
					if regex.search(key):
						if not key in hardwareClasses:
							hardwareClasses.append(key)
			if not hardwareClasses:
				return hashes
		if not hardwareClasses:
			for key in self._auditHardwareConfig.keys():
				hardwareClasses.append(key)

		if filter.has_key('hardwareClass'):
			del filter['hardwareClass']
		if filter.has_key('type'):
			del filter['type']

		for attribute in attributes:
			if not filter.has_key(attribute):
				filter[attribute] = None

		for hardwareClass in hardwareClasses:
			auditHardwareFilter = {}
			classFilter = {}
			skipHardwareClass = False
			for (attribute, value) in filter.items():
				valueInfo = None
				if not attribute in ('hostId', 'state', 'firstseen', 'lastseen'):
					valueInfo = self._auditHardwareConfig[hardwareClass].get(attribute)
					if not valueInfo:
						logger.debug(u"Skipping hardwareClass '%s', because of missing info for attribute '%s'" % (hardwareClass, attribute))
						skipHardwareClass = True
						break
					if (valueInfo.get('Scope', '') == 'g'):
						auditHardwareFilter[attribute] = value
						continue
					if (valueInfo.get('Scope', '') != 'i'):
						continue
				if not value is None:
					value = forceList(value)
				classFilter[attribute] = value

			if skipHardwareClass:
				continue

			hardwareIds = []
			if auditHardwareFilter:
				auditHardwareFilter['hardwareClass'] = hardwareClass
				hardwareIds = self._getHardwareIds(auditHardwareFilter)
				logger.debug2(u"Filtered matching hardware ids: %s" % hardwareIds)
				if not hardwareIds:
					continue
			classFilter['hardware_id'] = hardwareIds

			if attributes and not 'hardware_id' in attributes:
				attributes.append('hardware_id')

			logger.debug(u"Getting auditHardwareOnHosts, hardwareClass '%s', hardwareIds: %s, filter: %s" % (hardwareClass, hardwareIds, classFilter))
			for res in self._sql.getSet(self._createQuery(u'HARDWARE_CONFIG_' + hardwareClass, attributes, classFilter)):
				data = self._sql.getSet(u'SELECT * from `HARDWARE_DEVICE_%s` where `hardware_id` = %s' \
								% (hardwareClass, res['hardware_id']))
				if not data:
					logger.error(u"Hardware device of class '%s' with hardware_id '%s' not found" % (hardwareClass, res['hardware_id']))
					continue
				data = data[0]
				data.update(res)
				data['hardwareClass'] = hardwareClass
				del data['hardware_id']
				if data.has_key('config_id'):
					del data['config_id']

				for attribute in self._auditHardwareConfig[hardwareClass].keys():
					if not data.has_key(attribute):
						data[attribute] = None
				hashes.append(data)
		return hashes

	def auditHardwareOnHost_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.auditHardwareOnHost_getObjects(self, attributes=[], **filter)

		logger.info(u"Getting auditHardwareOnHosts, filter: %s" % filter)
		auditHardwareOnHosts = []
		for h in self.auditHardwareOnHost_getHashes(attributes, **filter):
			auditHardwareOnHosts.append(AuditHardwareOnHost.fromHash(h))
		return auditHardwareOnHosts

	def auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts):
		ConfigDataBackend.auditHardwareOnHost_deleteObjects(self, auditHardwareOnHosts)
		for auditHardwareOnHost in forceObjectClassList(auditHardwareOnHosts, AuditHardwareOnHost):
			logger.info(u"Deleting auditHardwareOnHost: %s" % auditHardwareOnHost)
			where = self._uniqueAuditHardwareOnHostCondition(auditHardwareOnHost)
			self._sql.delete( u'HARDWARE_CONFIG_' + auditHardwareOnHost.getHardwareClass(), where)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   BootConfigurations                                                                        -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def bootConfiguration_insertObject(self, bootConfiguration):
		ConfigDataBackend.bootConfiguration_insertObject(self, bootConfiguration)
		data = self._objectToDatabaseHash(bootConfiguration)

		where = self._uniqueCondition(bootConfiguration)
		if self._sql.getRow('select * from `BOOT_CONFIGURATION` where %s' % where):
			self._sql.update('BOOT_CONFIGURATION', where, data, updateWhereNone = True)
		else:
			self._sql.insert('BOOT_CONFIGURATION', data)

	def bootConfiguration_updateObject(self, bootConfiguration):
		ConfigDataBackend.bootConfiguration_updateObject(self, bootConfiguration)
		data = self._objectToDatabaseHash(bootConfiguration)
		where = self._uniqueCondition(bootConfiguration)
		self._sql.update('BOOT_CONFIGURATION', where, data)

	def bootConfiguration_getObjects(self, attributes=[], **filter):
		ConfigDataBackend.bootConfiguration_getObjects(self, attributes=[], **filter)
		logger.info(u"Getting bootConfigurations, filter: %s" % filter)
		bootConfigurations = []
		(attributes, filter) = self._adjustAttributes(BootConfiguration, attributes, filter)
		for res in self._sql.getSet(self._createQuery('BOOT_CONFIGURATION', attributes, filter)):
			self._adjustResult(BootConfiguration, res)
			bootConfigurations.append(BootConfiguration.fromHash(res))
		return bootConfigurations

	def bootConfiguration_deleteObjects(self, bootConfigurations):
		ConfigDataBackend.bootConfiguration_deleteObjects(self, bootConfigurations)
		for bootConfiguration in forceObjectClassList(bootConfigurations, BootConfiguration):
			logger.info(u"Deleting bootConfiguration %s" % bootConfiguration)
			where = self._uniqueCondition(bootConfiguration)
			self._sql.delete('BOOT_CONFIGURATION', where)
