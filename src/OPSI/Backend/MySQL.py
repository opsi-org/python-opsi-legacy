#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - MySQL   =
   = = = = = = = = = = = = = = = = = =
   
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

__version__ = '0.3.3.2'

# Imports
import MySQLdb, warnings, time
from _mysql_exceptions import *

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                       CLASS MYSQL                                                  =
# ======================================================================================================

class MySQL:
	def __init__(self, username = 'root', password = '', address = 'localhost', database = 'opsi'):
		self.__conn__ = None
		self.__username__ = username
		self.__password__ = password
		self.__address__ = address
		self.__database__ = database
		
	def connect(self):
		try:
			self.__conn__ = MySQLdb.connect(
							host = self.__address__,
							user = self.__username__,
							passwd = self.__password__,
							db = self.__database__,
							use_unicode = True,
							charset = 'utf8' )
		except Exception, e:
			raise BackendIOError("Failed to connect to database '%s' address '%s': %s" % (self.__database__, self.__address__, e))
		
		self.__cursor__ = self.__conn__.cursor(MySQLdb.cursors.DictCursor)
		
	def db_query(self, query):
		logger.debug2("db_query: %s" % query)
		self.db_execute(query)
		return self.__cursor__.rowcount
		
	def db_getSet(self, query):
		logger.debug2("db_getSet: %s" % query)
		self.db_execute(query)
		valueSet = self.__cursor__.fetchall()
		if not valueSet:
			logger.debug("No result for query '%s'" % query)
			return []
		return valueSet
		
	def db_getRow(self, query):
		logger.debug2("db_getRow: %s" % query)
		self.db_execute(query)
		row = self.__cursor__.fetchone()
		if not row:
			logger.debug("No result for query '%s'" % query)
			return {}
		logger.debug2("Result: '%s'" % row)
		return row
		
	def db_insert(self, table, valueHash):
		colNames = values = ''
		for (key, value) in valueHash.items():
			colNames += "`%s`, " % key
			if type(value) in (float, long, int, bool):
				values += "%s, " % value
			elif type(value) is str:
				values += "\'%s\', " % ('%s' % value.decode("utf-8")).replace("\\", "\\\\").replace("'", "\\\'")
			else:
				values += "\'%s\', " % ('%s' % value).replace("\\", "\\\\").replace("'", "\\\'")
			
		query = "INSERT INTO `%s` (%s) VALUES (%s);" % (table, colNames[:-2], values[:-2])
		logger.debug2("db_insert: %s" % query)
		self.db_execute(query)
		return self.__cursor__.lastrowid
		#return self.__cursor__.rowcount
		
	def db_update(self, table, where, valueHash):
		if not valueHash:
			raise ValueError("No values given")
		query = "UPDATE `%s` SET " % table
		for (key, value) in valueHash.items():
			query += "`%s` = " % key
			if type(value) in (float, long, int, bool):
				query += "%s, " % value
			else:
				query += "\'%s\', " % ('%s' % value).replace("\\", "\\\\").replace("'", "\\\'")
		
		query = '%s WHERE %s;' % (query[:-2], where)
		
		logger.debug2("db_update: %s" % query)
		self.db_execute(query)
		self.db_commit()
		return self.__cursor__.lastrowid
	
	def db_delete(self, table, where):
		query = "DELETE FROM `%s` WHERE %s;" % (table, where)
		logger.debug2("db_delete: %s" % query)
		self.db_execute(query)
		return self.__cursor__.lastrowid
	
	def db_commit(self):
		self.__conn__.commit()
		
	def db_execute(self, query):
		if not self.__conn__:
			self.connect()
		if not type(query) is unicode:
			query = unicode(query, 'utf-8')
		res = self.__cursor__.execute(query)
		self.db_commit()
		return res
	
	def db_info(self):
		if not self.__conn__:
			self.connect()
		return self.__conn__.info()
	
	def db_warning_count(self):
		if not self.__conn__:
			self.connect()
		return self.__conn__.warning_count()
		
	def db_close(self):
		if not self.__conn__:
			return
		logger.debug("Closing database connection")
		self.__cursor__.close()
		self.__conn__.commit()
		self.__conn__.close()

# ======================================================================================================
# =                                    CLASS MYSQLBACKEND                                              =
# ======================================================================================================
class MySQLBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = 'localhost', backendManager=None, args={}):
		''' MySQLBackend constructor. '''
		
		self.__backendManager = backendManager
		
		# Default values
		self._defaultDomain = 'opsi.org'
		self._username = username
		self._password = password
		self._address = address
		self._database = 'opsi'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'database'):		self._database = value
			elif (option.lower() == 'defaultdomain'): 	self._defaultDomain = value
			elif (option.lower() == 'host'):		self._address = value
			elif (option.lower() == 'username'):		self._username = value
			elif (option.lower() == 'password'):		self._password = value
			else:
				logger.warning("Unknown argument '%s' passed to MySQLBackend constructor" % option)
		
		warnings.showwarning = self._showwarning
		self.__mysql__ = MySQL(username = self._username, password = self._password, address = self._address, database = self._database)
		
		self._licenseManagementEnabled = True
		if self.__backendManager:
			self._licenseManagementEnabled = False
			try:
				modules = self.__backendManager.getOpsiInformation_hash()['modules']
				if modules.get('valid') and modules.get('license_management'):
					import base64, twisted.conch.ssh.keys
					try:
						from hashlib import md5
					except ImportError:
						from md5 import md5
					publicKey = twisted.conch.ssh.keys.getPublicKeyObject(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP'))
					data = ''
					mks = modules.keys()
					mks.sort()
					for module in mks:
						if module in ('valid', 'signature'):
							continue
						val = modules[module]
						if (val == False): val = 'no'
						if (val == True):  val = 'yes'
						data += module.lower().strip() + ' = ' + val + '\r\n'
					if (modules.get('expires', '') != 'never') and (time.mktime(time.strptime(modules.get('expires', '2000-01-01'), "%Y-%m-%d")) - time.time() <= 0):
						raise Exception("Modules file signature expired")
					self._licenseManagementEnabled = bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ]))
			except Exception, e:
				logger.error(e)
		
	def _showwarning(self, message, category, filename, lineno, file=None):
		#logger.warning("%s (file: %s, line: %s)" % (message, filename, lineno))
		if str(message).startswith('Data truncated for column'):
			logger.error(message)
		else:
			logger.warning(message)
	
	def _writeToServer_(self, queries):
		for query in queries.split(';'):
			if query.strip():
				self.__mysql__.db_query(query + ' ;')
	
	def updateHardwareInfoTable(self, hostId = None):
		if hostId:
			self._writeToServer_('DELETE FROM `HARDWARE_INFO` WHERE hostId = "%s";' % hostId)
		else:
			self._writeToServer_('TRUNCATE TABLE HARDWARE_INFO;')
		for config in self.getOpsiHWAuditConf():
			hwClass = config['Class']['Opsi']
			
			# Get all active (audit_state=1) hardware configurations of this hardware class (and host)
			res = []
			if hostId:
				res = self.__mysql__.db_getSet('SELECT * FROM `HARDWARE_CONFIG_%s` WHERE `hostId` = "%s"' % (hwClass, hostId))
			else:
				res = self.__mysql__.db_getSet("SELECT * FROM `HARDWARE_CONFIG_%s`" % hwClass)
			
			for hwConfig in res:
				hardware = self.__mysql__.db_getRow("SELECT * FROM `HARDWARE_DEVICE_%s` WHERE `hardware_id`='%s'" \
									% (hwClass, hwConfig['hardware_id']))
				hwConfig.update(hardware)
				hwConfig['hardware_class'] = hwClass
				self.__mysql__.db_insert( "HARDWARE_INFO", hwConfig )
	
	def deleteOpsiBase(self):
		# Drop database
		failure = 0
		done = False
		while not done and (failure < 100):
			done = True
			for i in self.__mysql__.db_getSet('SHOW TABLES;'):
				try:
					self.__mysql__.db_execute('DROP TABLE %s;' % i.values()[0])
				except Exception, e:
					logger.error(e)
					done = False
					failure += 1
		
	def createOpsiBase(self):
		# Hardware audit database
		tables = {}
		logger.debug("Current tables:")
		for i in self.__mysql__.db_getSet('SHOW TABLES;'):
			tableName = i.values()[0]
			logger.debug(" [ %s ]" % tableName)
			tables[tableName] = []
			for j in self.__mysql__.db_getSet('SHOW COLUMNS FROM `%s`' % tableName):
				logger.debug("      %s" % j)
				tables[tableName].append(j['Field'])
		
		logger.notice('Creating opsi base')
		
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		# = Client Management                                                                           =
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		
		# Host table
		if not 'HOST' in tables.keys():
			logger.debug('Creating table HOST')
			hostTable = 'CREATE TABLE `HOST` (\n' + \
						'`hostId` varchar(50) NOT NULL,\n' + \
						'PRIMARY KEY( `hostId` ),\n' + \
						'`type` varchar(20),\n' + \
						'`description` varchar(100),\n' + \
						'`notes` varchar(500),\n' + \
						'`hardwareAddress` varchar(17),\n' + \
						'`lastSeen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\'\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			logger.debug(hostTable)
			self._writeToServer_(hostTable)
			
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		# = Hardware / software inventory                                                               =
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		
		# Hardware audit database (utf-8 encoded)
		opsiHWAuditConf = self.getOpsiHWAuditConf()
		for config in opsiHWAuditConf:
			hwClass = config['Class']['Opsi']
			logger.info("Processing hardware class '%s'" % hwClass)
			
			hardwareDeviceTableName = 'HARDWARE_DEVICE_' + hwClass
			hardwareConfigTableName = 'HARDWARE_CONFIG_' + hwClass
			
			hardwareDeviceTable = 'CREATE TABLE `' + hardwareDeviceTableName + '` (\n' + \
						'`hardware_id` INT NOT NULL AUTO_INCREMENT,\n' + \
						'PRIMARY KEY( `hardware_id` ),\n'
			hardwareConfigTable = 'CREATE TABLE `' + hardwareConfigTableName + '` (\n' + \
						'`config_id` INT NOT NULL AUTO_INCREMENT,\n' + \
						'PRIMARY KEY( `config_id` ),\n' + \
						'`hostId` varchar(50) NOT NULL,\n' + \
						'`hardware_id` INT NOT NULL,\n' + \
						'`audit_firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						'`audit_lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						'`audit_state` TINYINT NOT NULL,\n'
			
			hardwareDeviceTableExists = hardwareDeviceTableName in tables.keys()
			hardwareConfigTableExists = hardwareConfigTableName in tables.keys()
			
			if hardwareDeviceTableExists:
				hardwareDeviceTable = 'ALTER TABLE `' + hardwareDeviceTableName + '`\n'
			if hardwareConfigTableExists:
				hardwareConfigTable = 'ALTER TABLE `' + hardwareConfigTableName + '`\n'
			
			for value in config['Values']:
				logger.debug("  Processing value '%s'" % value['Opsi'])
				if   (value['Scope'] == 'g'):
					if hardwareDeviceTableExists:
						if value['Opsi'] in tables[hardwareDeviceTableName]:
							# Column exists => change
							hardwareDeviceTable += 'CHANGE `%s` `%s` %s NULL,\n' % (value['Opsi'], value['Opsi'], value["Type"])
						else:
							# Column does not exist => add
							hardwareDeviceTable += 'ADD `%s` %s NULL,\n' % (value['Opsi'], value["Type"])
					else:
						hardwareDeviceTable += '`%s` %s NULL,\n' % (value['Opsi'], value["Type"])
				elif (value['Scope'] == 'i'):
					if hardwareConfigTableExists:
						if value['Opsi'] in tables[hardwareConfigTableName]:
							# Column exists => change
							hardwareConfigTable += 'CHANGE `%s` `%s` %s NULL,\n' % (value['Opsi'], value['Opsi'], value["Type"])
						else:
							# Column does not exist => add
							hardwareConfigTable += 'ADD `%s` %s NULL,\n' % (value['Opsi'], value["Type"])
					else:
						hardwareConfigTable += '`%s` %s NULL,\n' % (value['Opsi'], value["Type"])
			
			# Remove leading and trailing whitespace
			hardwareDeviceTable = hardwareDeviceTable.strip()
			hardwareConfigTable = hardwareConfigTable.strip()
			
			# Remove trailing comma
			if (hardwareDeviceTable[-1] == ','):
				hardwareDeviceTable = hardwareDeviceTable[:-1]
			if (hardwareConfigTable[-1] == ','):
				hardwareConfigTable = hardwareConfigTable[:-1]
			
			# Finish sql query
			if hardwareDeviceTableExists:
				hardwareDeviceTable += ' ;\n'
			else:
				hardwareDeviceTable += '\n) ENGINE=MyISAM DEFAULT CHARSET=utf8;\n'
			
			if hardwareConfigTableExists:
				hardwareConfigTable += ' ;\n'
			else:
				hardwareConfigTable += '\n) ENGINE=MyISAM DEFAULT CHARSET=utf8;\n'
			
			# Log sql query
			logger.debug(hardwareDeviceTable)
			logger.debug(hardwareConfigTable)
			
			# Execute sql query
			self._writeToServer_(hardwareDeviceTable)
			self._writeToServer_(hardwareConfigTable)
		
		# Software audit database
		if not 'SOFTWARE' in tables.keys():
			softwareTable  =  'CREATE TABLE `SOFTWARE` (\n' + \
						'`softwareId` varchar(100) NOT NULL,\n' + \
						'PRIMARY KEY( `softwareId` ),\n' + \
						'`displayName` varchar(100),\n' + \
						'`displayVersion` varchar(100),\n' + \
						'`uninstallString` varchar(200),\n' + \
						'`binaryName` varchar(100),\n' + \
						'`installSize` BIGINT\n' + \
					') ENGINE=MyISAM DEFAULT CHARSET=utf8;\n'
			logger.debug(softwareTable)
			self._writeToServer_(softwareTable)
		
		if not 'SOFTWARE_CONFIG' in tables.keys():
			softwareConfigTable  =  'CREATE TABLE `SOFTWARE_CONFIG` (\n' + \
							'`config_id` INT NOT NULL AUTO_INCREMENT,\n' + \
							'PRIMARY KEY( `config_id` ),\n' + \
							'`hostId` varchar(50) NOT NULL,\n' + \
							'`softwareId` varchar(100) NOT NULL,\n' + \
							'`audit_firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
							'`audit_lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
							'`audit_state` TINYINT NOT NULL,\n' + \
							'`usageFrequency` int NOT NULL DEFAULT -1,\n' + \
							'`lastUsed` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\'\n' + \
						'\n) ENGINE=MyISAM DEFAULT CHARSET=utf8;\n'
			logger.debug(softwareConfigTable)
			self._writeToServer_(softwareConfigTable)
		
		# Create merged hardware info table
		properties = {}
		for config in opsiHWAuditConf:
			for value in config['Values']:
				if properties.has_key(value['Opsi']) and (properties[value['Opsi']] != value['Type']):
					type1 = properties[value['Opsi']].strip()
					type2 = value['Type'].strip()
					try:
						(type1, size1) = type1[:-1].split('(')
						(type2, size2) = type2[:-1].split('(')
						if (type1 != type2):
							raise Exception('')
					except:
						raise BackendBadValueError("Got duplicate property '%s' of different types: %s, %s" \
										% (value['Opsi'], type1, type2))
					size1 = int(size1)
					size2 = int(size2)
					logger.warning("Got duplicate property '%s' of same type '%s' but different sizes: %s, %s" \
										% (value['Opsi'], type1, size1, size2))
					if (size1 > size2):
						logger.warning("Using type %s(%d) for property '%s'" % (type1, size1, value['Opsi']))
						continue
					else:
						logger.warning("Using type %s(%d) for property '%s'" % (type1, size2, value['Opsi']))
				properties[value['Opsi']] = value['Type']
				
		logger.debug("Merged properties: %s" % properties)
		
		table = ''
		tableExists = 'HARDWARE_INFO' in tables.keys()
		if tableExists:
			table = 'ALTER TABLE `HARDWARE_INFO`\n'
		else:
			#'`info_id` INT NOT NULL AUTO_INCREMENT,\n' + \
			table = 'CREATE TABLE `HARDWARE_INFO` (\n' + \
					'`config_id` INT NOT NULL,\n' + \
					'`hostId` varchar(50) NOT NULL,\n' + \
					'`hardware_id` INT NOT NULL,\n' + \
					'`hardware_class` VARCHAR(50) NOT NULL,\n' + \
					'PRIMARY KEY( `config_id`, `hostId`, `hardware_class`, `hardware_id` ),\n' + \
					'`audit_firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
					'`audit_lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
					'`audit_state` TINYINT NOT NULL,\n'
		
		pNames = properties.keys()
		pNames.sort()
		for p in pNames:
			if tableExists:
				if p in tables['HARDWARE_INFO']:
					# Column exists => change
					table += 'CHANGE `%s` `%s` %s NULL,\n' % (p, p, properties[p])
				else:
					# Column does not exist => add
					table += 'ADD `%s` %s NULL,\n' % (p, properties[p])
			else:
				table += '`%s` %s NULL,\n' % (p, properties[p])
		
		# Remove leading and trailing whitespace
		table = table.strip()
		
		# Remove trailing comma
		if (table[-1] == ','):
			table = table[:-1]
		
		# Finish sql query
		if tableExists:
			table += ' ;\n'
		else:
			table += '\n) ENGINE=MyISAM DEFAULT CHARSET=utf8;\n'
		
		# Log sql query
		logger.debug(table)
		
		# Execute sql query
		self._writeToServer_(table)
		
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		# = License Management                                                                          =
		# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
		
		# LicenseContract
		if not 'LICENSE_CONTRACT' in tables.keys():
			table = 'CREATE TABLE `LICENSE_CONTRACT` (\n' + \
					'`licenseContractId` VARCHAR(100) NOT NULL,\n' + \
					'PRIMARY KEY( `licenseContractId` ),\n' + \
					'`partner` VARCHAR(100),\n' + \
					'`conclusionDate` DATE NOT NULL DEFAULT \'0000-00-00\',\n' + \
					'`notificationDate` DATE NOT NULL DEFAULT \'0000-00-00\',\n' + \
					'`expirationDate` DATE NOT NULL DEFAULT \'0000-00-00\',\n' + \
					'`notes` VARCHAR(1000)\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		# SoftwareLicense
		if not 'SOFTWARE_LICENSE' in tables.keys():
			#'FOREIGN KEY ( `boundToHost` ) REFERENCES HOST( `hostId` ),\n' + \
			table = 'CREATE TABLE `SOFTWARE_LICENSE` (\n' + \
					'`softwareLicenseId` VARCHAR(100) NOT NULL,\n' + \
					'PRIMARY KEY( `softwareLicenseId` ),\n' + \
					'`licenseContractId` VARCHAR(100) NOT NULL,\n' + \
					'FOREIGN KEY ( `licenseContractId` ) REFERENCES LICENSE_CONTRACT( `licenseContractId` ),\n' + \
					'`boundToHost` varchar(50),\n' + \
					'`licenseType` VARCHAR(20),\n' + \
					'`maxInstallations` INT,\n' + \
					'`expirationDate` DATE NOT NULL DEFAULT \'0000-00-00\'\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		# LicensePool
		if not 'LICENSE_POOL' in tables.keys():
			table = 'CREATE TABLE `LICENSE_POOL` (\n' + \
					'`licensePoolId` VARCHAR(100) NOT NULL,\n' + \
					'PRIMARY KEY( `licensePoolId` ),\n' + \
					'`description` VARCHAR(200)\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		if not 'WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL' in tables.keys():
			table = 'CREATE TABLE `WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL` (\n' + \
					'`licensePoolId` VARCHAR(100) NOT NULL,\n' + \
					'FOREIGN KEY ( `licensePoolId` ) REFERENCES LICENSE_POOL( `licensePoolId` ),\n' + \
					'`windowsSoftwareId` VARCHAR(100) NOT NULL,\n' + \
					'PRIMARY KEY( `licensePoolId`, `windowsSoftwareId` )\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		if not 'PRODUCT_ID_TO_LICENSE_POOL' in tables.keys():
			table = 'CREATE TABLE `PRODUCT_ID_TO_LICENSE_POOL` (\n' + \
					'`licensePoolId` VARCHAR(100) NOT NULL,\n' + \
					'FOREIGN KEY ( `licensePoolId` ) REFERENCES LICENSE_POOL( `licensePoolId` ),\n' + \
					'`productId` VARCHAR(100) NOT NULL,\n' + \
					'PRIMARY KEY( `licensePoolId`, `productId` )\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		if not 'SOFTWARE_LICENSE_TO_LICENSE_POOL' in tables.keys():
			table = 'CREATE TABLE `SOFTWARE_LICENSE_TO_LICENSE_POOL` (\n' + \
					'`softwareLicenseId` VARCHAR(100) NOT NULL,\n' + \
					'FOREIGN KEY ( `softwareLicenseId` ) REFERENCES SOFTWARE_LICENSE( `softwareLicenseId` ),\n' + \
					'`licensePoolId` VARCHAR(100) NOT NULL,\n' + \
					'FOREIGN KEY ( `licensePoolId` ) REFERENCES LICENSE_POOL( `licensePoolId` ),\n' + \
					'PRIMARY KEY( `softwareLicenseId`, `licensePoolId` ),\n' + \
					'`licenseKey` VARCHAR(100) NOT NULL DEFAULT \'\'\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		if not 'LICENSE_USED_BY_HOST' in tables.keys():
			table = 'CREATE TABLE `LICENSE_USED_BY_HOST` (\n' + \
					'`softwareLicenseId` VARCHAR(100) NOT NULL,\n' + \
					'`licensePoolId` VARCHAR(100) NOT NULL,\n' + \
					'`hostId` varchar(50),\n' + \
					'PRIMARY KEY( `softwareLicenseId`, `licensePoolId`, `hostId` ),\n' + \
					'FOREIGN KEY( `softwareLicenseId`, `licensePoolId` ) \n' + \
					'REFERENCES SOFTWARE_LICENSE_TO_LICENSE_POOL( `softwareLicenseId`, `licensePoolId` ), \n' + \
					'`licenseKey` VARCHAR(100) NOT NULL,\n' + \
					'`notes` VARCHAR(1024) NOT NULL DEFAULT \'\'\n' + \
					') ENGINE=InnoDB DEFAULT CHARSET=utf8;\n'
			# Log sql query
			logger.debug(table)
			
			# Execute sql query
			self._writeToServer_(table)
		
		
	# -------------------------------------------------
	# -     Host Management                           -
	# -------------------------------------------------
	def createClient(self, clientName, domain=None, description=None, notes=None, ipAddress=None, hardwareAddress=None):
		if not re.search(HOST_NAME_REGEX, clientName):
			raise BackendBadValueError("Unallowed char in hostname")
		
		if not domain:
			domain = self._defaultDomain
		
		hostId = self._preProcessHostId(clientName + '.' + domain)
		#if hostId in self.getDepotIds_list():
		#	raise BackendBadValueError("Refusing to create client '%s' which is registered as depot server" % hostId)
		
		if self.__mysql__.db_getRow('SELECT `hostId` FROM `HOST` WHERE `hostId`="%s"' % hostId):
			host = {}
			if description: 	host['description'] = description
			if notes: 		host['notes'] = notes
			if hardwareAddress: 	host['hardwareAddress'] = hardwareAddress
			hostId = self.__mysql__.db_update('HOST', '`hostId` = "%s"' % hostId, host)
		else:
			host = {
				'hostId': 		hostId,
				'type':			'OPSI_CLIENT',
				'description':		description,
				'notes':		notes,
				'hardwareAddress':	hardwareAddress
			}
			self.__mysql__.db_insert('HOST', host)
		return hostId
		
	def getHost_hash(self, hostId):
		hostId = self._preProcessHostId(hostId)
		host = self.__mysql__.db_getRow('SELECT * FROM `HOST` WHERE `hostId`="%s"' % hostId)
		if not host:
			raise BackendMissingDataError("Host '%s' does not exist" % hostId)
		del host['type']
		host['hostId'] = hostId
		host['notes'] = host['notes'].encode('utf-8')
		host['description'] = host['description'].encode('utf-8')
		host['hardwareAddress'] = host['hardwareAddress'].encode('utf-8')
		if host['lastSeen']:
			host['lastSeen'] = time.strftime('%Y%m%d%H%M%S', time.strptime(str(host['lastSeen']), '%Y-%m-%d %H:%M:%S'))
		else:
			host['lastSeen'] =  ''
		return host
	
	def getClientIds_list(self, serverId = None, depotId = None, groupId = None, productId = None, installationStatus = None, actionRequest = None, productVersion = None, packageVersion = None):
		clientIds = []
		# TODO
		for res in self.__mysql__.db_getSet("SELECT hostId FROM `HOST` WHERE `type`='OPSI_CLIENT'"):
			clientIds.append(res['hostId'].encode('utf-8'))
		return clientIds
	
	def deleteClient(self, clientId):
		clientId = self._preProcessHostId(clientId)
		#if clientId in self.getDepotIds_list():
		#	raise BackendBadValueError("Refusing to delete client '%s' which is registered as depot server" % clientId)
		
		if self.__mysql__.db_getRow('SELECT `hostId` FROM `HOST` WHERE `hostId`="%s" AND `type`="OPSI_CLIENT"' % clientId):
			self.__mysql__.db_delete('HOST', '`hostId`="%s"' % clientId)
	
	# -------------------------------------------------
	# -     Software Inventory                        -
	# -------------------------------------------------
	def getSoftwareInformation_hash(self, hostId):
		hostId = self._preProcessHostId(hostId)
		
		info = {}
		if not self.__mysql__.db_getRow('SELECT `hostId` FROM `HOST` WHERE `hostId`="%s"' % hostId):
			logger.warning("Host '%s' not found" % hostId)
			return info
		
		# Timestamp of the latest scan
		scantime = time.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
		
		for swConfig in self.__mysql__.db_getSet('SELECT * FROM `SOFTWARE_CONFIG` WHERE `audit_state`=1 AND `hostId`="%s"' % hostId):
			softwareId = ''
			softwareInfo = {}
			
			for (key, value) in swConfig.items():
				if key in ('config_id', 'hostId', 'audit_firstseen', 'audit_state'):
					# Filter out this information
					continue
				if (key == 'audit_lastseen'):
					lastseen = time.strptime(str(value), "%Y-%m-%d %H:%M:%S")
					if (scantime < lastseen):
						scantime = lastseen
					continue
				if (value == None):
					value = ""
				if (key == 'lastUsed'):
					value = str(value)
				if type(value) is unicode:
					value = value.encode('utf-8')
				softwareInfo[key] = value
				
			# Add general hardware device information
			software = self.__mysql__.db_getRow('SELECT * FROM `SOFTWARE` WHERE `softwareId`="%s"' % swConfig['softwareId'])
			for (key, value) in software.items():
				if type(value) is unicode:
					value = value.encode('utf-8')
				if key in ('softwareId'):
					softwareId = value
					continue
				if (value == None):
					value = ""
				softwareInfo[key] = value
			
			if softwareId and softwareInfo:
				info[softwareId] = softwareInfo
		
		if not info:
			return info
		info['SCANPROPERTIES'] = {'scantime': time.strftime("%Y-%m-%d %H:%M:%S", scantime) }
		return info
	
	def getSoftwareInformation_listOfHashes(self):
		software = []
		for sw in self.__mysql__.db_getSet('SELECT * FROM `SOFTWARE`'):
			installedOn = []
			for res in self.__mysql__.db_getSet('SELECT `hostId` FROM `SOFTWARE_CONFIG` WHERE `audit_state` = 1 AND `softwareId` = "%s"' % sw['softwareId']):
				installedOn.append(res['hostId'].encode('utf-8'))
			
			for key in ('displayName', 'displayVersion', 'uninstallString', 'binaryName'):
				if not sw[key]:
					sw[key] = ''
				sw[key] = sw[key].encode('utf-8')
			if not sw['installSize']:
				sw['installSize'] = 0
			sw['windowsSoftwareId'] = sw['softwareId'].encode('utf-8')
			sw['installedOn'] = installedOn
			sw['installationCount'] = len(installedOn)
			del sw['softwareId']
			software.append(sw)
		return software
	
	def setSoftwareInformation(self, hostId, info):
		hostId = self._preProcessHostId(hostId)
		if not type(info) is dict:
			raise BackendBadValueError("Software information must be dict")
		
		# Time of scan (may be overwritten by SCANPROPERTIES)
		scantime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
		try:
			scantime = info['SCANPROPERTIES']['scantime']
		except:
			pass
		
		# Create host if not exists
		if not self.__mysql__.db_getRow('SELECT hostId FROM HOST WHERE hostId="%s"' % hostId):
			# Add host to database
			parts = hostId.split('.')
			self.createClient(clientName = parts[0], domain = '.'.join(parts[1:]))
		
		configIdsSeen = []
		
		for (softwareId, softwareInfo) in info.items():
			if (softwareId == 'SCANPROPERTIES'):
				continue
			
			logger.info("Processing softwareId '%s'" % softwareId)
			# This dict contains general (unchangeable) software information
			software = { 'softwareId': softwareId }
			# This dict contains host specific software configuration
			softwareConfig = {}
			
			for (opsiName, opsiValue) in softwareInfo.items():
				if (type(opsiValue) == type(None)):
					continue
				
				if opsiName in ('displayName', 'displayVersion', 'uninstallString', 'installSize', 'binaryName'):
					# This is a general (unchangeable) software information, put it into the software table
					if type(opsiValue) is unicode:
						software[opsiName] = opsiValue.encode('utf-8')
					else:
						software[opsiName] = opsiValue
				else:
					
					# This is a configuration information, put it into the configuration table
					if type(opsiValue) is unicode:
						softwareConfig[opsiName] = opsiValue.encode('utf-8')
					else:
						softwareConfig[opsiName] = opsiValue
					
			# Update / insert software into database
			if self.__mysql__.db_getSet('SELECT `softwareId` FROM `SOFTWARE` WHERE softwareId="%s";' % softwareId):
				# Software already exists in database
				logger.debug("Software already in database")
			else:
				# Software does not exist in database, create
				logger.info("Adding software to database")
				self.__mysql__.db_insert('SOFTWARE', software)
			
			# Update / insert software configuration into database
			softwareConfig["softwareId"] = softwareId
			softwareConfig["hostId"] = hostId
			softwareConfig["audit_firstseen"] = scantime
			softwareConfig["audit_lastseen"] = scantime
			softwareConfig["audit_state"] = 1
			confId = -1
			query = 'SELECT `config_id` FROM `SOFTWARE_CONFIG` WHERE'
			for (k, v) in softwareConfig.items():
				if k in ('audit_firstseen', 'audit_lastseen', 'audit_state'):
					continue
				if k in ('usageFrequency', 'lastUsed'):
					# Update only, do not create new entry in history
					continue
				if type(v) in (str, unicode):
					# String-value
					query += " `%s` = '%s' AND" % (k, v.replace("\\", "\\\\").replace("'", "\\\'"))
				else:
					query += " `%s` = %s AND" % (k, v)
			query = query + " `audit_state`=1 AND `audit_lastseen` != '%s'" % scantime
			current = self.__mysql__.db_getSet(query)
			if (len(current) >= 1):
				# Host specific software config already exists in database
				logger.debug("Host specific software config already in database")
				if (len(current) > 1):
					# Host specific software config exists more than once
					confIds = []
					for c in current:
						confIds.append(str(c['config_id']))
					logger.warning("Redundant entries in software config database: table 'SOFTWARE', config_ids: %s" \
								% ', '.join(confIds) )
				confId = current[0]['config_id']
				# Update config
				self.__mysql__.db_query("UPDATE `SOFTWARE_CONFIG` SET " + \
								"`audit_lastseen`='%s', `usageFrequency`=%d, `lastUsed`='%s' WHERE `config_id` = %d;" \
								% (	scantime, 
									softwareConfig.get('usageFrequency', -1),
									softwareConfig.get('lastUsed', '0000-00-00 00:00:00'),
									confId ) )
			else:
				# Host specific software config does not exist in database, create
				logger.info("Adding host specific software config to database")
				confId = self.__mysql__.db_insert("SOFTWARE_CONFIG", softwareConfig)
			# Add config_id to the list of active software configurations
			configIdsSeen.append(confId)
		
		# Search for inactive software configurations, to mark them as inactive (audit_state 0)
		for config in self.__mysql__.db_getSet('SELECT `config_id` FROM `SOFTWARE_CONFIG` WHERE `audit_state` = 1 AND `hostId` = "%s";' % hostId):
			if config['config_id'] not in configIdsSeen:
				# This configuration is marked as active but not in the list of active configs, setting audit_state to 0
				logger.notice("Software config with config_id %d vanished (table SOFTWARE_CONFIG), updating audit_state" \
							% config['config_id'])
				self.__mysql__.db_query("UPDATE `SOFTWARE_CONFIG` SET `audit_state` = 0 WHERE `config_id` = %d;" % config['config_id'])
	
	def deleteSoftwareInformation(self, hostId):
		hostId = self._preProcessHostId(hostId)
		self.__mysql__.db_delete('SOFTWARE_CONFIG', '`hostId` = "%s"' % hostId)
		try:
			self.deleteClient(hostId)
		except:
			pass
	
	# -------------------------------------------------
	# -     Hardware Inventory                        -
	# -------------------------------------------------
	def getHardwareInformation_listOfHashes(self, hostId):
		return []
	
	def getHardwareInformation_hash(self, hostId):
		hostId = self._preProcessHostId(hostId)
		info = {}
		info = {}
		if not self.__mysql__.db_getRow('SELECT `hostId` FROM `HOST` WHERE `hostId`="%s"' % hostId):
			logger.warning("Host '%s' not found" % hostId)
			return info
		
		# Timestamp of the latest scan
		scantime = time.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
		
		for config in self.getOpsiHWAuditConf():
			hwClass = config['Class']['Opsi']
			devices = []
			# Get all active (audit_state=1) hardware configurations of this hardware class and host
			for hwConfig in self.__mysql__.db_getSet('SELECT * FROM `HARDWARE_CONFIG_%s` WHERE `audit_state`=1 AND `hostId`="%s"' \
									% (hwClass, hostId)):
				device = {}
				for (key, value) in hwConfig.items():
					if key in ('config_id', 'hardware_id', 'hostId', 'audit_firstseen', 'audit_state'):
						# Filter out this information
						continue
					if (key == 'audit_lastseen'):
						lastseen = time.strptime(str(value), "%Y-%m-%d %H:%M:%S")
						if (scantime < lastseen):
							scantime = lastseen
						continue
					if (value == None):
						value = ""
					if type(value) is unicode:
						value = value.encode('utf-8')
					device[key] = value
				
				# Add general hardware device information
				hardware = self.__mysql__.db_getRow("SELECT * FROM `HARDWARE_DEVICE_%s` WHERE `hardware_id`='%s'" % (hwClass, hwConfig['hardware_id']))
				for (key, value) in hardware.items():
					if type(value) is unicode:
						value = value.encode('utf-8')
					if key in ('hardware_id'):
						# Filter out this information
						continue
					if (value == None):
						value = ""
					device[key] = value
				
				if device:
					devices.append(device)
			if devices:
				info[hwClass] = devices
		
		if not info:
			return info
		info['SCANPROPERTIES'] = [ {'scantime': time.strftime("%Y-%m-%d %H:%M:%S", scantime) } ]
		return info
	
	def setHardwareInformation(self, hostId, info):
		hostId = self._preProcessHostId(hostId)
		if not type(info) is dict:
			raise BackendBadValueError("Hardware information must be dict")
		
		# Time of scan (may be overwritten by SCANPROPERTIES)
		scantime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
		try:
			scantime = info['SCANPROPERTIES'][0]['scantime']
		except:
			pass
		
		# Create host if not exists
		if not self.__mysql__.db_getRow('SELECT hostId FROM HOST WHERE hostId="%s"' % hostId):
			# Add host to database
			parts = hostId.split('.')
			self.createClient(clientName = parts[0], domain = '.'.join(parts[1:]))
		
		# Get and reorganize the opsi hw audit config
		config = self.getOpsiHWAuditConf()
		configNew = {}
		for i in config:
			for j in i['Values']:
				if not configNew.has_key(i['Class']['Opsi']):
					configNew[i['Class']['Opsi']] = {}
				configNew[i['Class']['Opsi']][j['Opsi']] = j['Scope']
		
		queries = ''
		for (hwClass, devices) in info.items():
			if (hwClass == 'SCANPROPERTIES'):
				continue
			
			logger.info("Processing hardware class '%s'" % hwClass)
			
			# This list contains all currently active config_ids of this hardware class and host
			configIdsSeen = []
			
			for device in devices:
				# This dict contains general (unchangeable) hardware device information
				hardwareDevice = {}
				# This dict contains host specific hardware configuration
				hardwareConfig = {}
				
				for (opsiName, opsiValue) in device.items():
					if (type(opsiValue) == type(None)):
						continue
					
					if (configNew[hwClass][opsiName] == 'g'):
						# This is a general (unchangeable) hardware information, put it into the hardware table
						if type(opsiValue) is unicode:
							hardwareDevice[opsiName] = opsiValue.encode('utf-8')
						else:
							hardwareDevice[opsiName] = opsiValue
					else:	
						# This is a configuration information, put it into the configuration table
						if type(opsiValue) is unicode:
							hardwareConfig[opsiName] = opsiValue.encode('utf-8')
						else:
							hardwareConfig[opsiName] = opsiValue
					
				# Update / insert hardware device into database
				hwId = -1
				query = 'SELECT `hardware_id` FROM `HARDWARE_DEVICE_%s` WHERE' % hwClass
				for (k, v) in hardwareDevice.items():
					if type(v) in (str, unicode):
						# String-value
						query += " `%s` = '%s' AND" % (k, v.replace("\\", "\\\\").replace("'", "\\\'"))
					else:
						query += " `%s` = %s AND" % (k, v)
				query = query[:-4] + ';'
				current = self.__mysql__.db_getSet(query)
				if (len(current) >= 1):
					# Hardware device already exists in database
					logger.debug("Hardware device already in database")
					if (len(current) > 1):
						# Hardware device exists more than once
						hwIds = []
						for c in current:
							hwIds.append(str(c['hardware_id']))
						logger.warning("Redundant entries in hardware database: table 'HARDWARE_DEVICE_%s', hardware_ids: %s" \
									% (hwClass, ', '.join(hwIds)) )
					hwId = current[0]['hardware_id']
				else:
					# Hardware device does not exist in database, create
					logger.info("Adding hardware device to database")
					hwId = self.__mysql__.db_insert('HARDWARE_DEVICE_' + hwClass, hardwareDevice)
				
				# Update / insert hardware configuration into database
				hardwareConfig["hardware_id"] = hwId
				hardwareConfig["hostId"] = hostId
				hardwareConfig["audit_firstseen"] = scantime
				hardwareConfig["audit_lastseen"] = scantime
				hardwareConfig["audit_state"] = 1
				confId = -1
				query = 'SELECT `config_id` FROM `HARDWARE_CONFIG_%s` WHERE' % hwClass
				for (k, v) in hardwareConfig.items():
					if k in ('audit_firstseen', 'audit_lastseen', 'audit_state'):
						continue
					if type(v) in (str, unicode):
						# String-value
						query += " `%s` = '%s' AND" % (k, v.replace("\\", "\\\\").replace("'", "\\\'"))
					else:
						query += " `%s` = %s AND" % (k, v)
				query = query + " `audit_state`=1 AND `audit_lastseen` != '%s'" % scantime
				current = self.__mysql__.db_getSet(query)
				if (len(current) >= 1):
					# Host specific hardware config already exists in database
					logger.debug("Host specific hardware config already in database")
					if (len(current) > 1):
						# Host specific hardware config exists more than once
						confIds = []
						for c in current:
							confIds.append(str(c['config_id']))
						logger.info("Redundant entries in hardware config database: table 'HARDWARE_CONFIG_%s', config_ids: %s" \
									% (hwClass, ', '.join(confIds)) )
					confId = current[0]['config_id']
					self.__mysql__.db_query("UPDATE `HARDWARE_CONFIG_%s` SET `audit_lastseen`='%s' WHERE `config_id` = %d;" % (hwClass, scantime, confId))
				else:
					# Host specific hardware config does not exist in database, create
					logger.info("Adding host specific hardware config to database")
					confId = self.__mysql__.db_insert("HARDWARE_CONFIG_%s" % hwClass, hardwareConfig)
				# Add config_id to the list of active hardware configurations
				configIdsSeen.append(confId)
			
			# Search for inactive hardware configurations, to mark them as inactive (audit_state 0)
			for config in self.__mysql__.db_getSet('SELECT `config_id` FROM `HARDWARE_CONFIG_%s` WHERE `audit_state` = 1 AND `hostId`="%s";' % (hwClass, hostId)):
				if config['config_id'] not in configIdsSeen:
					# This configuration is marked as active but not in the list of active configs, setting audit_state to 0
					logger.notice("Hardware config with config_id %d vanished (table HARDWARE_CONFIG_%s), updating audit_state" \
								% (config['config_id'], hwClass))
					self.__mysql__.db_query("UPDATE `HARDWARE_CONFIG_%s` SET `audit_state` = 0 WHERE `config_id` = %d;" % (hwClass, config['config_id']))
		
		self.updateHardwareInfoTable(hostId)
		
	def deleteHardwareInformation(self, hostId):
		hostId = self._preProcessHostId(hostId)
		for config in self.getOpsiHWAuditConf():
			self.__mysql__.db_delete('HARDWARE_CONFIG_%s' % config['Class']['Opsi'], '`hostId` = "%s"' % hostId)
		self.__mysql__.db_delete('HARDWARE_INFO', '`hostId` = "%s"' % hostId)
		try:
			self.deleteClient(hostId)
		except:
			pass
		
	# -------------------------------------------------
	# -     License Management                        -
	# -------------------------------------------------
	def createLicenseContract(self, licenseContractId="", partner="", conclusionDate="", notificationDate="", expirationDate="", notes=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licenseContractId:
			i=0
			while True:
				licenseContractId = time.strftime('c_%Y-%m-%d_%H:%M:%S_', time.localtime()) + str(i)
				if not self.__mysql__.db_getRow('SELECT `licenseContractId` FROM `LICENSE_CONTRACT` WHERE `licenseContractId`="%s"' % licenseContractId):
					break
				i+=1
			
		if conclusionDate:   conclusionDate   = time.strftime('%Y-%m-%d', time.strptime(conclusionDate,   '%Y-%m-%d'))
		if notificationDate: notificationDate = time.strftime('%Y-%m-%d', time.strptime(notificationDate, '%Y-%m-%d'))
		if expirationDate:   expirationDate   = time.strftime('%Y-%m-%d', time.strptime(expirationDate,   '%Y-%m-%d'))
		if not re.search(LICENSE_CONTRACT_ID_REGEX, licenseContractId):
			raise BackendBadValueError("Bad license contract id '%s'" % licenseContractId)
		
		licenseContract = {
			'partner':		partner,
			'conclusionDate':	conclusionDate,
			'notificationDate':	notificationDate,
			'expirationDate':	expirationDate,
			'notes':		notes
		}
		if self.__mysql__.db_getRow('SELECT `licenseContractId` FROM `LICENSE_CONTRACT` WHERE `licenseContractId`="%s"' % licenseContractId):
			self.__mysql__.db_update('LICENSE_CONTRACT', "`licenseContractId`='%s'" % licenseContractId, licenseContract)
		else:
			licenseContract['licenseContractId'] = licenseContractId
			self.__mysql__.db_insert('LICENSE_CONTRACT', licenseContract)
		return licenseContractId
	
	def getLicenseContractIds_list(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		licenseContractIds = []
		for res in self.__mysql__.db_getSet("SELECT licenseContractId FROM `LICENSE_CONTRACT`"):
			licenseContractIds.append(res['licenseContractId'].encode('utf-8'))
		return licenseContractIds
	
	def getLicenseContract_hash(self, licenseContractId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(LICENSE_CONTRACT_ID_REGEX, licenseContractId):
			raise BackendBadValueError("Bad license contract id '%s'" % licenseContractId)
		
		licenseContract = self.__mysql__.db_getRow('SELECT * FROM `LICENSE_CONTRACT` WHERE `licenseContractId`="%s"' % licenseContractId)
		if not licenseContract:
			raise BackendMissingDataError("License contract '%s' does not exist" % licenseContractId)
		
		licenseContract['licenseContractId'] = licenseContractId
		licenseContract['partner'] = licenseContract['partner'].encode('utf-8')
		licenseContract['notes'] = licenseContract['notes'].encode('utf-8')
		
		if not licenseContract['conclusionDate']:
			licenseContract['conclusionDate'] = ''
		else:
			licenseContract['conclusionDate'] = time.strftime('%Y-%m-%d', time.strptime(str(licenseContract['conclusionDate']), '%Y-%m-%d'))
		
		if not licenseContract['notificationDate']:
			licenseContract['notificationDate'] = ''
		else:
			licenseContract['notificationDate'] = time.strftime('%Y-%m-%d', time.strptime(str(licenseContract['notificationDate']), '%Y-%m-%d'))
		
		if not licenseContract['expirationDate']:
			licenseContract['expirationDate'] = ''
		else:
			licenseContract['expirationDate'] = time.strftime('%Y-%m-%d', time.strptime(str(licenseContract['expirationDate']), '%Y-%m-%d'))
		
		
		licenseContract['softwareLicenseIds'] = []
		for result in self.__mysql__.db_getSet('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE` WHERE `licenseContractId`="%s"' % licenseContractId):
			licenseContract['softwareLicenseIds'].append(result['softwareLicenseId'].encode('utf-8'))
		
		return licenseContract
	
	def getLicenseContracts_listOfHashes(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		licenseContracts = []
		for licenseContract in self.__mysql__.db_getSet('SELECT `licenseContractId` FROM `LICENSE_CONTRACT`'):
			licenseContracts.append(self.getLicenseContract_hash(licenseContract['licenseContractId'].encode('utf-8')))
		return licenseContracts
	
	def deleteLicenseContract(self, licenseContractId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(LICENSE_CONTRACT_ID_REGEX, licenseContractId):
			raise BackendBadValueError("Bad license contract id '%s'" % licenseContractId)
		if self.__mysql__.db_getRow('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE` WHERE `licenseContractId`="%s"' % licenseContractId):
			raise BackendReferentialIntegrityError("Refusing to delete contract '%s', one or more software licenses refer to license contract" % licenseContractId)
		self.__mysql__.db_delete('LICENSE_CONTRACT', '`licenseContractId`="%s"' % licenseContractId)
	
	
	def createSoftwareLicense(self, softwareLicenseId="", licenseContractId="", licenseType="", maxInstallations="", boundToHost="", expirationDate=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not softwareLicenseId:
			i=0
			while True:
				softwareLicenseId = time.strftime('l_%Y-%m-%d_%H:%M:%S_', time.localtime()) + str(i)
				if not self.__mysql__.db_getRow('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE` WHERE `softwareLicenseId`="%s"' % softwareLicenseId):
					break
				i+=1
		availableLicenseContractIds = self.getLicenseContractIds_list()
		if not licenseContractId:
			licenseContractId = 'c_default'
			if not 'c_default' in availableLicenseContractIds:
				logger.notice("Creating license contract 'c_default'")
				self.createLicenseContract(licenseContractId="c_default", notes="Auto generated default license contract")
				availableLicenseContractIds.append('c_default')
		if not licenseType:
			licenseType = 'VOLUME'
		if not maxInstallations or (maxInstallations < 0):
			maxInstallations = 0
		if (licenseType == 'OEM'):
			maxInstallations = 1
		if expirationDate:
			expirationDate = time.strftime('%Y-%m-%d', time.strptime(expirationDate, '%Y-%m-%d'))
		if not licenseType in SOFTWARE_LICENSE_TYPES:
			raise BackendBadValueError("Unkown license type '%s', known license types: %s" % (licenseType, SOFTWARE_LICENSE_TYPES))
		if not re.search(SOFTWARE_LICENSE_ID_REGEX, softwareLicenseId):
			raise BackendBadValueError("Bad software license id '%s'" % softwareLicenseId)
		if not licenseContractId in availableLicenseContractIds:
			raise BackendReferentialIntegrityError("License contract with id '%s' does not exist" % licenseContractId)
		if (licenseType == 'OEM') and not boundToHost:
			raise BackendBadValueError("Software license type 'OEM' expects boundToHost value")
		
		softwareLicense = {
			'licenseContractId':	licenseContractId,
			'licenseType':		licenseType,
			'maxInstallations':	maxInstallations,
			'expirationDate':	expirationDate
		}
		if boundToHost:
			softwareLicense['boundToHost'] = boundToHost
		
		if self.__mysql__.db_getRow('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE` WHERE `softwareLicenseId`="%s"' % softwareLicenseId):
			self.__mysql__.db_update('SOFTWARE_LICENSE', '`softwareLicenseId`="%s"' % softwareLicenseId, softwareLicense)
		else:
			softwareLicense['softwareLicenseId'] = softwareLicenseId
			self.__mysql__.db_insert('SOFTWARE_LICENSE', softwareLicense)
		return softwareLicenseId
		
	def getSoftwareLicenseIds_list(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		softwareLicenseIds = []
		for res in self.__mysql__.db_getSet("SELECT softwareLicenseId FROM `SOFTWARE_LICENSE`"):
			softwareLicenseIds.append(res['softwareLicenseId'].encode('utf-8'))
		return softwareLicenseIds
	
	def getSoftwareLicense_hash(self, softwareLicenseId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(SOFTWARE_LICENSE_ID_REGEX, softwareLicenseId):
			raise BackendBadValueError("Bad software license id '%s'" % softwareLicenseId)
		
		softwareLicense = self.__mysql__.db_getRow('SELECT * FROM `SOFTWARE_LICENSE` WHERE `softwareLicenseId`="%s"' % softwareLicenseId)
		if not softwareLicense:
			raise BackendMissingDataError("Software license '%s' does not exist" % softwareLicenseId)
		
		softwareLicense['softwareLicenseId'] = softwareLicenseId
		softwareLicense['licenseContractId'] = softwareLicense['licenseContractId'].encode('utf-8')
		softwareLicense['licenseType'] = softwareLicense['licenseType'].encode('utf-8')
		softwareLicense['maxInstallations'] = int(softwareLicense['maxInstallations'])
		if not softwareLicense['boundToHost']:
			softwareLicense['boundToHost'] = ''
		else:
			softwareLicense['boundToHost'] = softwareLicense['boundToHost'].encode('utf-8')
		if not softwareLicense['expirationDate']:
			softwareLicense['expirationDate'] = ''
		else:
			softwareLicense['expirationDate'] = time.strftime('%Y-%m-%d', time.strptime(str(softwareLicense['expirationDate']), '%Y-%m-%d'))
		softwareLicense['licensePoolIds'] = []
		softwareLicense['licenseKeys'] = {}
		
		for result in self.__mysql__.db_getSet('SELECT `licensePoolId`, `licenseKey` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `softwareLicenseId`="%s"' % softwareLicenseId):
			softwareLicense['licenseKeys'][result['licensePoolId'].encode('utf-8')] = result['licenseKey'].encode('utf-8')
			softwareLicense['licensePoolIds'].append(result['licensePoolId'].encode('utf-8'))
			
		return softwareLicense
	
	def getSoftwareLicenses_listOfHashes(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		softwareLicences = []
		for softwareLicense in self.__mysql__.db_getSet('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE`'):
			softwareLicences.append(self.getSoftwareLicense_hash(softwareLicense['softwareLicenseId'].encode('utf-8')))
		return softwareLicences
		
	
	def deleteSoftwareLicense(self, softwareLicenseId, removeFromPools=False):
		if not re.search(SOFTWARE_LICENSE_ID_REGEX, softwareLicenseId):
			raise BackendBadValueError("Bad software license id '%s'" % softwareLicenseId)
		
		result = self.__mysql__.db_getSet('SELECT `hostId` FROM `LICENSE_USED_BY_HOST` WHERE `softwareLicenseId`="%s"' % softwareLicenseId)
		if result:
			hostIds = []
			for res in result:
				hostIds.append(res['hostId'])
			raise BackendReferentialIntegrityError("Refusing to delete software license '%s', since the software license is used by hosts: %s" \
									% (softwareLicenseId, hostIds))
		
		result = self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `softwareLicenseId`="%s"' % softwareLicenseId)
		if result:
			if not removeFromPools:
				licensePoolIds = []
				for res in result:
					licensePoolIds.append(res['licensePoolId'])
				raise BackendReferentialIntegrityError("Refusing to delete software license '%s', delete first the assignments to the license pools: %s" \
									% (softwareLicenseId, licensePoolIds))
			else:
				self.__mysql__.db_delete('SOFTWARE_LICENSE_TO_LICENSE_POOL', '`softwareLicenseId`="%s"' % softwareLicenseId)
		self.__mysql__.db_delete('SOFTWARE_LICENSE', '`softwareLicenseId`="%s"' % softwareLicenseId)
		
	def createLicensePool(self, licensePoolId="", description="", productIds=[], windowsSoftwareIds=[]):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId:
			i=0
			while True:
				licensePoolId = time.strftime('p_%Y-%m-%d_%H:%M:%S_', time.localtime()) + str(i)
				if not self.__mysql__.db_getRow('SELECT `licensePoolId` FROM `LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId):
					break
				i+=1
		if not re.search(LICENSE_POOL_ID_REGEX, licensePoolId):
			raise BackendBadValueError("Bad license pool id '%s'" % licensePoolId)
		
		licensePool = {
			'description':	description
		}
		if self.__mysql__.db_getRow('SELECT `licensePoolId` FROM `LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId):
			self.__mysql__.db_update('LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId, licensePool)
		else:
			licensePool['licensePoolId'] = licensePoolId
			self.__mysql__.db_insert('LICENSE_POOL', licensePool)
		
		# TODO: check products id
		self.__mysql__.db_delete('PRODUCT_ID_TO_LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId)
		self.__mysql__.db_delete('WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId)
		if productIds:
			for productId in productIds:
				self.__mysql__.db_insert('PRODUCT_ID_TO_LICENSE_POOL', { 'licensePoolId': licensePoolId, 'productId': productId })
		if windowsSoftwareIds:
			for windowsSoftwareId in windowsSoftwareIds:
				self.__mysql__.db_insert('WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL', { 'licensePoolId': licensePoolId, 'windowsSoftwareId': windowsSoftwareId })
		
		return licensePoolId
		
	def getLicensePoolIds_list(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		licensePoolIds = []
		for res in self.__mysql__.db_getSet("SELECT `licensePoolId` FROM `LICENSE_POOL`"):
			licensePoolIds.append(res['licensePoolId'].encode('utf-8'))
		return licensePoolIds
	
	def getLicensePool_hash(self, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(LICENSE_POOL_ID_REGEX, licensePoolId):
			raise BackendBadValueError("Bad license pool id '%s'" % licensePoolId)
		
		licensePool = self.__mysql__.db_getRow('SELECT * FROM `LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId)
		if not licensePool:
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		
		licensePool['licensePoolId'] = licensePoolId
		licensePool['description'] = licensePool['description'].encode('utf-8')
		licensePool['productIds'] = []
		licensePool['windowsSoftwareIds'] = []
		for res in self.__mysql__.db_getSet('SELECT productId FROM `PRODUCT_ID_TO_LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId):
			licensePool['productIds'].append(res['productId'].encode('utf-8'))
		for res in self.__mysql__.db_getSet('SELECT windowsSoftwareId FROM `WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId):
			licensePool['windowsSoftwareIds'].append(res['windowsSoftwareId'].encode('utf-8'))
		return licensePool
	
	def getLicensePools_listOfHashes(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		licencePools = []
		for licensePool in self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `LICENSE_POOL`'):
			licencePools.append(self.getLicensePool_hash(licensePool['licensePoolId'].encode('utf-8')))
		return licencePools
	
	def deleteLicensePool(self, licensePoolId, deleteLicenses=False):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(LICENSE_POOL_ID_REGEX, licensePoolId):
			raise BackendBadValueError("Bad license pool id '%s'" % licensePoolId)
		
		result = self.__mysql__.db_getSet('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId)
		if result:
			if not deleteLicenses:
				raise BackendReferentialIntegrityError("Refusing to delete license pool '%s', one ore more licenses/keys refer to pool" % licensePoolId)
			else:
				for res in result:
					softwareLicenseId = res['softwareLicenseId']
					self.__mysql__.db_delete('LICENSE_USED_BY_HOST', '`softwareLicenseId` = "%s"' % softwareLicenseId)
					self.__mysql__.db_delete('SOFTWARE_LICENSE_TO_LICENSE_POOL', '`softwareLicenseId` = "%s"' % softwareLicenseId)
					self.__mysql__.db_delete('SOFTWARE_LICENSE', '`softwareLicenseId` = "%s"' % softwareLicenseId)
					
		self.__mysql__.db_delete('PRODUCT_ID_TO_LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId)
		self.__mysql__.db_delete('WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId)
		self.__mysql__.db_delete('LICENSE_POOL', '`licensePoolId`="%s"' % licensePoolId)
	
	def addSoftwareLicenseToLicensePool(self, softwareLicenseId, licensePoolId, licenseKey=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(SOFTWARE_LICENSE_ID_REGEX, softwareLicenseId):
			raise BackendBadValueError("Bad software license id '%s'" % softwareLicenseId)
		if not re.search(LICENSE_POOL_ID_REGEX, licensePoolId):
			raise BackendBadValueError("Bad license pool id '%s'" % licensePoolId)
		if not licensePoolId in self.getLicensePoolIds_list():
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		if not softwareLicenseId in self.getSoftwareLicenseIds_list():
			raise BackendMissingDataError("Software license '%s' does not exist" % softwareLicenseId)
		
		data = { 'licenseKey': licenseKey }
		
		if self.__mysql__.db_getRow('SELECT * FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `softwareLicenseId`="%s" AND `licensePoolId`="%s"' % (softwareLicenseId, licensePoolId)):
			self.__mysql__.db_update('SOFTWARE_LICENSE_TO_LICENSE_POOL', '`softwareLicenseId`="%s" AND `licensePoolId`="%s"' % (softwareLicenseId, licensePoolId), data)
		else:
			data['softwareLicenseId'] = softwareLicenseId
			data['licensePoolId'] = licensePoolId
			self.__mysql__.db_insert('SOFTWARE_LICENSE_TO_LICENSE_POOL', data)
	
	def removeSoftwareLicenseFromLicensePool(self, softwareLicenseId, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId in self.getLicensePoolIds_list():
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		if not softwareLicenseId in self.getSoftwareLicenseIds_list():
			raise BackendMissingDataError("Software license '%s' does not exist" % softwareLicenseId)
		
		if self.__mysql__.db_getRow('SELECT * FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `softwareLicenseId`="%s" AND `licensePoolId`="%s"' % (softwareLicenseId, licensePoolId)):
			self.__mysql__.db_delete('SOFTWARE_LICENSE_TO_LICENSE_POOL', '`softwareLicenseId`="%s" AND `licensePoolId`="%s"' % (softwareLicenseId, licensePoolId))
	
	def addProductIdsToLicensePool(self, productIds, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not re.search(LICENSE_POOL_ID_REGEX, licensePoolId):
			raise BackendBadValueError("Bad license pool id '%s'" % licensePoolId)
		if not licensePoolId in self.getLicensePoolIds_list():
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		if not type(productIds) is list:
			productIds = [ productIds ]
		for productId in productIds:
			if not self.__mysql__.db_getRow('SELECT * FROM `PRODUCT_ID_TO_LICENSE_POOL` WHERE `productId`="%s" AND `licensePoolId`="%s"' % (productId, licensePoolId)):
				self.__mysql__.db_insert('PRODUCT_ID_TO_LICENSE_POOL', { 'licensePoolId': licensePoolId, 'productId': productId })
	
	def removeProductIdsFromLicensePool(self, productIds, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId in self.getLicensePoolIds_list():
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		if not type(productIds) is list:
			productIds = [ productIds ]
		for productId in productIds:
			where = '`productId`="%s" AND `licensePoolId`="%s"' % (productId, licensePoolId)
			if self.__mysql__.db_getRow('SELECT * FROM `PRODUCT_ID_TO_LICENSE_POOL` WHERE ' + where):
				self.__mysql__.db_delete('PRODUCT_ID_TO_LICENSE_POOL', where)
	
	def setWindowsSoftwareIdsToLicensePool(self, windowsSoftwareIds, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId in self.getLicensePoolIds_list():
			raise BackendMissingDataError("License pool '%s' does not exist" % licensePoolId)
		self.__mysql__.db_delete('WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL', '`licensePoolId`="%s"' % (licensePoolId))
		if not type(windowsSoftwareIds) is list:
			windowsSoftwareIds = [ windowsSoftwareIds ]
		for windowsSoftwareId in windowsSoftwareIds:
			if not self.__mysql__.db_getRow('SELECT * FROM `WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL` WHERE `windowsSoftwareId`="%s" AND `licensePoolId`="%s"' % (windowsSoftwareId, licensePoolId)):
				self.__mysql__.db_insert('WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL', { 'licensePoolId': licensePoolId, 'windowsSoftwareId': windowsSoftwareId })
	
	def getLicensePoolId(self, productId="", windowsSoftwareId=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if productId:
			result = self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `PRODUCT_ID_TO_LICENSE_POOL` WHERE `productId`="%s"' % productId)
			if (len(result) < 1):
				raise LicenseConfigurationError("No license pool for product id '%s' found" % productId)
			elif (len(result) > 1):
				raise LicenseConfigurationError("Multiple license pools for product id '%s' found" % productId)
			return result[0]['licensePoolId']
		elif windowsSoftwareId:
			result = self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `WINDOWS_SOFTWARE_ID_TO_LICENSE_POOL` WHERE `windowsSoftwareId`="%s"' % windowsSoftwareId)
			if (len(result) < 1):
				raise LicenseConfigurationError("No license pool for windows software id '%s' found" % windowsSoftwareId)
			elif (len(result) > 1):
				raise LicenseConfigurationError("Multiple license pools for windows software id '%s' found" % windowsSoftwareId)
			return result[0]['licensePoolId']
		else:
			raise BackendBadValueError("Neither product id nor windows software id given.")
	
	def _getFreeSoftwareLicense(self, hostId, licensePoolId):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		softwareLicenseId = ''
		licenseKey = ''
		# Get software license keys
		result = list(self.__mysql__.db_getSet('SELECT `softwareLicenseId`, `licenseKey` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId))
		for res in result:
			# Test if a license is exclusivly set for the host
			boundToHost = self.__mysql__.db_getRow('SELECT `boundToHost` FROM `SOFTWARE_LICENSE`' + \
								' WHERE `softwareLicenseId`="%s"' % res['softwareLicenseId']).get('boundToHost')
			if (boundToHost == hostId):
				softwareLicenseId = res['softwareLicenseId']
				licenseKey = res['licenseKey']
				logger.info("Using license bound to host")
				break
		
		sumMaxInstallations = 0
		sumInstallations = 0
		if not softwareLicenseId:
			# Search an available license
			for res in result:
				maxInstallations = -1
				installations = len(self.__mysql__.db_getSet(	'SELECT * FROM `LICENSE_USED_BY_HOST`' + \
										' WHERE `softwareLicenseId`="%s"' % res['softwareLicenseId']))
				sumInstallations += installations
				lic = self.__mysql__.db_getRow('SELECT `maxInstallations` FROM `SOFTWARE_LICENSE`' + \
								' WHERE `softwareLicenseId`="%s" AND `licenseType`!="OEM"' \
											% res['softwareLicenseId'])
				if lic:
					maxInstallations = int(lic['maxInstallations'])
					if (maxInstallations == 0):
						# 0 = infinite
						softwareLicenseId = res['softwareLicenseId']
						licenseKey = res['licenseKey']
						sumMaxInstallations = 'infinite'
						break
					sumMaxInstallations += maxInstallations
				if (installations < maxInstallations):
					softwareLicenseId = res['softwareLicenseId']
					licenseKey = res['licenseKey']
					break
		
		logger.info("Sum installations: %d, sum max installations: %s" % (sumInstallations, sumMaxInstallations))
		
		if not softwareLicenseId:
			raise LicenseMissingError("No license available")
		return (softwareLicenseId, licenseKey)
	
	def getOrCreateSoftwareLicenseUsage_hash(self, hostId, licensePoolId="", productId="", windowsSoftwareId=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId:
			licensePoolId = self.getLicensePoolId(productId = productId, windowsSoftwareId = windowsSoftwareId)
		
		# Test if a license is already used by the host
		result = self.__mysql__.db_getRow('SELECT * FROM `LICENSE_USED_BY_HOST` WHERE `licensePoolId`="%s" AND `hostId`="%s"' \
															% (licensePoolId, hostId))
		if result:
			logger.info("Using already assigned license")
			result['softwareLicenseId'] = result['softwareLicenseId'].encode('utf-8')
			result['licenseKey']        = result['licenseKey'].encode('utf-8')
			result['notes']             = result['notes'].encode('utf-8')
		else:
			(softwareLicenseId, licenseKey) = self._getFreeSoftwareLicense(hostId, licensePoolId)
			if not licenseKey:
				logger.info("License available but no license key found")
			
			logger.info("Using software license id '%s', license key '%s' for host '%s' and license pool '%s'" \
					% (softwareLicenseId, licenseKey, hostId, licensePoolId))
			
			self.__mysql__.db_insert( "LICENSE_USED_BY_HOST", { 'licensePoolId': licensePoolId, 'softwareLicenseId': softwareLicenseId, 'hostId': hostId, 'licenseKey': licenseKey } )
			
			result['softwareLicenseId'] = softwareLicenseId.encode('utf-8')
			result['licenseKey']        = licenseKey.encode('utf-8')
			result['notes']             = ''
		
		result['licensePoolId'] = licensePoolId
		result['hostId']        = hostId
		
		return result
	
	def getAndAssignSoftwareLicenseKey(self, hostId, licensePoolId="", productId="", windowsSoftwareId=""):
		return self.getOrCreateSoftwareLicenseUsage_hash(hostId, licensePoolId, productId, windowsSoftwareId).get('licenseKey', '')
	
	def getSoftwareLicenseUsages_listOfHashes(self, hostIds=[], licensePoolIds=[]):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		
		sql = 'SELECT * FROM `LICENSE_USED_BY_HOST`'
		
		if licensePoolIds:
			sql += ' WHERE `licensePoolId` in ('
			if not type(licensePoolIds) is list:
				licensePoolIds = [ licensePoolIds ]
			for licensePoolId in licensePoolIds:
				sql += '"%s", ' % licensePoolId
			sql = sql[:-2]+')'
		
		if hostIds:
			if licensePoolIds:
				sql += ' AND `hostId` IN ('
			else:
				sql += ' WHERE `hostId` IN ('
			if not type(hostIds) is list:
				hostIds = [ hostIds ]
			for hostId in hostIds:
				sql += '"%s", ' % hostId
			sql = sql[:-2]+')'
		
		licenseUsages = []
		for res in self.__mysql__.db_getSet(sql):
			licenseUsages.append({
				"hostId":            res["hostId"].encode('utf-8'),
				"softwareLicenseId": res["softwareLicenseId"].encode('utf-8'),
				"licensePoolId":     res["licensePoolId"].encode('utf-8'),
				"notes":             res.get("notes", "").encode('utf-8'),
				"licenseKey":        res.get("licenseKey", "").encode('utf-8'),
			})
		return licenseUsages
	
	def setSoftwareLicenseUsage(self, hostId, licensePoolId, softwareLicenseId, licenseKey="", notes=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		
		licenseUsedByHost = { 'licenseKey': licenseKey, 'notes': notes }
		where = '`hostId`="%s" AND `licensePoolId`="%s" AND `softwareLicenseId`="%s"' % (hostId, licensePoolId, softwareLicenseId)
		if self.__mysql__.db_getRow('SELECT * FROM `LICENSE_USED_BY_HOST` WHERE ' + where):
			self.__mysql__.db_update('LICENSE_USED_BY_HOST', where, licenseUsedByHost)
		else:
			licenseUsedByHost['hostId'] = hostId
			licenseUsedByHost['licensePoolId'] = licensePoolId
			licenseUsedByHost['softwareLicenseId'] = softwareLicenseId
			self.__mysql__.db_insert('LICENSE_USED_BY_HOST', licenseUsedByHost)
			
		key = {	'hostId' :  hostId, 'softwareLicenseId': softwareLicenseId, 'licensePoolId' : licensePoolId }  
		return key
		
	def deleteSoftwareLicenseUsage(self, hostId, softwareLicenseId="", licensePoolId="", productId="", windowsSoftwareId=""):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not licensePoolId:
			licensePoolId = self.getLicensePoolId(productId = productId, windowsSoftwareId = windowsSoftwareId)
		
		where = ''
		if (softwareLicenseId):
			where = '`hostId`="%s" AND `licensePoolId`="%s" AND `softwareLicenseId`="%s"' % (hostId, licensePoolId, softwareLicenseId)
		else:
			where = '`hostId`="%s" AND `licensePoolId`="%s"' % (hostId, licensePoolId)
		
		result = self.__mysql__.db_getRow('SELECT * FROM `LICENSE_USED_BY_HOST` WHERE ' +  where)
		if result:
			logger.debug("Deleting software license usage for hostId '%s', licensePoolId '%s', softwareLicenseId '%s'" \
								% (hostId, licensePoolId, softwareLicenseId))
			self.__mysql__.db_delete('LICENSE_USED_BY_HOST', where)
		else:
			logger.info('No software license usage found for deleting, `hostId`="%s". `licensePoolId`="%s",`softwareLicenseId`="%s"' \
								% (hostId, licensePoolId, softwareLicenseId))
	
	def deleteAllSoftwareLicenseUsages(self, hostIds):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		if not type(hostIds) is list:
			hostIds = [ hostIds ]
		
		where = '`hostId` IN ('
		for hostId in hostIds:
			where += '"%s", ' % hostId
		where = where[:-2]+')'
		self.__mysql__.db_delete('LICENSE_USED_BY_HOST', where)
	
	def getLicenseStatistics_hash(self):
		if not self._licenseManagementEnabled: raise BackendModuleDisabledError("License management module currently disabled")
		
		result = {}
		
		for pool in self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `LICENSE_POOL`'):
			licensePoolId = pool['licensePoolId'].encode('utf-8')
			
			licenses = 0
			usedBy = []
			maxInstallations = 0
			remainingInstallations = 0
			additionalLicensePoolIds = []
			
			for res in self.__mysql__.db_getSet('SELECT `softwareLicenseId` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `licensePoolId`="%s"' % licensePoolId):
				for res2 in self.__mysql__.db_getSet('SELECT `licensePoolId` FROM `SOFTWARE_LICENSE_TO_LICENSE_POOL` WHERE `softwareLicenseId`="%s"' % res['softwareLicenseId']):
					if (res2['licensePoolId'] == licensePoolId):
						continue
					if not res2['licensePoolId'] in additionalLicensePoolIds:
						additionalLicensePoolIds.append(res2['licensePoolId'])
				licenses += 1
				mi = int(self.__mysql__.db_getRow('SELECT `maxInstallations` FROM `SOFTWARE_LICENSE`' + \
										' WHERE `softwareLicenseId`="%s"' % res['softwareLicenseId']).get('maxInstallations'))
				if (mi == 0):
					maxInstallations = 'infinite'
				elif (maxInstallations != 'infinite'):
					maxInstallations += mi
			
			for res in self.__mysql__.db_getSet('SELECT `hostId` FROM `LICENSE_USED_BY_HOST` WHERE `licensePoolId`="%s"' % licensePoolId):
				usedBy.append(res['hostId'].encode('utf-8'))
			
			if (maxInstallations == 'infinite'):
				remainingInstallations = 'infinite'
			else:
				remainingInstallations = maxInstallations - len(usedBy)
				where = ''
				for additionalLicensePoolId in additionalLicensePoolIds:
					if where: where += ' OR '
					where += '`licensePoolId`="%s"' % additionalLicensePoolId
					remainingInstallations -= len(self.__mysql__.db_getSet('SELECT `licenseKey` FROM `LICENSE_USED_BY_HOST` WHERE %s' % where))
					if (remainingInstallations < 1):
						remainingInstallations = 0
			
			result[licensePoolId] = {
				'licenses': licenses,
				'usedBy': usedBy,
				'usageCount': len(usedBy),
				'maxInstallations': maxInstallations,
				'remainingInstallations': remainingInstallations }
			
		return result
		
	# -------------------------------------------------
	# -     Cleanup                                   -
	# -------------------------------------------------
	def exit(self):
		self.__mysql__.db_close()


if (__name__ == "__main__"):
	logger.setConsoleLevel(LOG_INFO)
	print "This test will destroy your opsi database!"
	print "Do you want to continue (NO/yes): ",
	if (sys.stdin.readline().strip() != 'yes'):
		sys.exit(0)
	print ""
	
	serverId = socket.getfqdn()
	serverName = serverId.split('.')[0]
	defaultDomain = '.'.join( serverId.split('.')[1:] )
	be = MySQLBackend(
			username = 'opsi',
			password = 'opsi',
			address = '127.0.0.1',
			args = { "defaultDomain": defaultDomain, "database": "opsi_test" }
	)
	
	print "\n[ BASE ]"
	print "   Deleting base"
	be.deleteOpsiBase()
	
	print "   Creating base"
	be.createOpsiBase()
	
	print "\n[ HOST MANAGEMENT ]"
	print "   Creating clients"
	be.createClient( clientName = "test-client1", domain = defaultDomain, description = "Test Client 1", notes = "Note 1\nNote 2\n", ipAddress = "192.168.1.101", hardwareAddress = "01:00:00:00:00:01" )
	be.createClient( clientName = "test-client2", domain = defaultDomain, description = "Test Client 2", notes = "Note 1\nNote 2\n", ipAddress = "192.168.1.102", hardwareAddress = "02:00:00:00:00:02" )
	be.createClient( clientName = "test-client3", domain = defaultDomain, description = "Test Client 3", notes = "Note 1\nNote 2\n", ipAddress = "192.168.1.103", hardwareAddress = "03:00:00:00:00:03" )
	be.createClient( clientName = "test-client4", domain = defaultDomain, description = "Test Client 4", notes = "Note 1\nNote 2\n", ipAddress = "192.168.1.104", hardwareAddress = "04:00:00:00:00:04" )
	be.createClient( clientName = "test-client5", domain = defaultDomain, description = "Test Client 5", notes = "Note 1\nNote 2\n", ipAddress = "192.168.1.105", hardwareAddress = "04:00:00:00:00:05" )
	
	print "   Deleting client 'test-client5.%s'" % defaultDomain
	be.deleteClient('test-client5.%s' % defaultDomain)
	
	print "   Getting clients"
	clientIds = be.getClientIds_list()
	print "      =>>>", clientIds
	assert len(clientIds) == 4
	assert 'test-client1.%s' % defaultDomain in clientIds
	assert 'test-client2.%s' % defaultDomain in clientIds
	assert 'test-client3.%s' % defaultDomain in clientIds
	assert 'test-client4.%s' % defaultDomain in clientIds
	
	for clientId in clientIds:
		print "   Getting host info for %s" % clientId
		print "      =>>>", be.getHost_hash( hostId = clientId )
	
	print "\n[ LICENSE MANAGEMENT ]"
	print "   Creating license pools"
	be.createLicensePool( 'windows_xp_pro', description="Microsoft Windows professional", productId='winxppro', windowsSoftwareId='' )
	be.createLicensePool( 'windows_vista_business', description="Microsoft Windows Vista Business", productId='winvista', windowsSoftwareId='' )
	be.createLicensePool( 'avg_anti_malware', description="AVG Anti-Malware", productId='avgam', windowsSoftwareId='AVG7Uninstall' )
	be.createLicensePool( 'office_2003', description="Microsoft Office 2003", productId='office2003', windowsSoftwareId='{xxxxxx-xxxxx-xxxxx-xxxxx-xxxxx}' )
	be.createLicensePool( 'access_2003', description="Microsoft Office 2003 - Access", productId='office2003', windowsSoftwareId='{yyyyyy-yyyyxx-xxyyx-xyyxx-xyyyx}' )
	
	print "   Deleting license pool 'avg_anti_malware'"
	be.deleteLicensePool( licensePoolId = 'avg_anti_malware' )
	
	print "   Getting license pools"
	licensePoolIds = be.getLicensePoolIds_list()
	print "      =>>>", licensePoolIds
	assert len(licensePoolIds) == 4
	assert 'windows_xp_pro' in licensePoolIds
	assert 'windows_vista_business' in licensePoolIds
	assert 'office_2003' in licensePoolIds
	assert 'access_2003' in licensePoolIds
	
	for licensePoolId in licensePoolIds:
		print "   Getting license pool info for %s" % licensePoolId
		print "      =>>>", be.getLicensePool_hash( licensePoolId = licensePoolId )
	
	print ""
	
	print "   Creating license contracts"
	be.createLicenseContract( licenseContractId = "1", partner="Microsoft", conclusionDate="2008-01-01", notificationDate="", expirationDate="2010-01-01", notes="See folder xyz" )
	be.createLicenseContract( licenseContractId = "2", partner="Adobe", conclusionDate="", notificationDate="", expirationDate="", notes="" )
	be.createLicenseContract( licenseContractId = "3", partner="Somebody", conclusionDate="", notificationDate="2009-01-01", notes="" )
	
	print "   Deleting license contract '2'"
	be.deleteLicenseContract( licenseContractId = '2' )
	
	print "   Getting license contracts"
	licenseContractIds = be.getLicenseContractIds_list()
	print "      =>>>", licenseContractIds
	assert len(licenseContractIds) == 2
	assert '1' in licenseContractIds
	assert '3' in licenseContractIds
	
	for licenseContractId in licenseContractIds:
		print "   Getting license contract info for %s" % licenseContractId
		print "      =>>>", be.getLicenseContract_hash( licenseContractId = licenseContractId )
	
	print ""
	
	print "   Creating software licenses"
	be.createSoftwareLicense( softwareLicenseId="1", licenseContractId="1", licenseType="OEM", maxInstallations=1, boundToHost='test-client4.%s' % defaultDomain )
	be.createSoftwareLicense( softwareLicenseId="2", licenseContractId="1", licenseType="VOLUME", maxInstallations=2 )
	be.createSoftwareLicense( softwareLicenseId="3", licenseContractId="1", licenseType="RETAIL", maxInstallations=1, expirationDate="2010-01-01" )
	be.createSoftwareLicense( softwareLicenseId="4", licenseContractId="3", licenseType="RETAIL", maxInstallations=1, expirationDate="2011-01-01" )
	be.createSoftwareLicense( softwareLicenseId="5", licenseContractId="3", licenseType="RETAIL", maxInstallations=1 )
	
	print "   Deleting software license '5'"
	be.deleteSoftwareLicense( softwareLicenseId = '5' )
	
	print "   Creating software license keys"
	be.createSoftwareLicenseKey( softwareLicenseId="1", licensePoolId='windows_xp_pro', licenseKey='WINXP-HR7YV-68XDT-81GTZ-HHZ75' )
	be.createSoftwareLicenseKey( softwareLicenseId="2", licensePoolId='windows_vista_business', licenseKey='VISTA-G7Z65-KKT6F-L7892-YKKY1' )
	be.createSoftwareLicenseKey( softwareLicenseId="2", licensePoolId='windows_xp_pro')
	be.createSoftwareLicenseKey( softwareLicenseId="3", licensePoolId='office_2003', licenseKey='OFFICE-8821K-L97GRT-6FR5S-8VH53' )
	be.createSoftwareLicenseKey( softwareLicenseId="4", licensePoolId='access_2003', licenseKey='ACCESS-GJ66F-HGT5E-XVX5Y-8GGR1' )
	
	print "   Getting software licenses"
	softwareLicenseIds = be.getSoftwareLicenseIds_list()
	print "      =>>>", softwareLicenseIds
	assert len(softwareLicenseIds) == 4
	assert '1' in softwareLicenseIds
	assert '2' in softwareLicenseIds
	assert '3' in softwareLicenseIds
	assert '4' in softwareLicenseIds
	
	for softwareLicenseId in softwareLicenseIds:
		print "   Getting software license info for %s" % softwareLicenseId
		print "      =>>>", be.getSoftwareLicense_hash( softwareLicenseId = softwareLicenseId )
	
	print ""
	
	print "   Getting and assigning software license key for product 'winxppro' host 'test-client1.%s'" % defaultDomain
	licenseKey = be.getAndAssignSoftwareLicenseKey( hostId="test-client1.%s" % defaultDomain, productId="winxppro" )
	print "      =>>>", licenseKey
	assert licenseKey == 'WINXP-HR7YV-68XDT-81GTZ-HHZ75'
	print "   Getting assigned software license key for product 'winxppro', host 'test-client1.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client1.%s" % defaultDomain, productId="winxppro" )
	print "      =>>>", licenseKey
	assert licenseKey == 'WINXP-HR7YV-68XDT-81GTZ-HHZ75'
	
	print "   Getting and assigning software license key from pool 'windows_vista_business' host 'test-client2.%s'" % defaultDomain
	licenseKey = be.getAndAssignSoftwareLicenseKey( hostId="test-client2.%s" % defaultDomain, licensePoolId="windows_vista_business" )
	print "      =>>>", licenseKey
	assert licenseKey == 'VISTA-G7Z65-KKT6F-L7892-YKKY1'
	print "   Getting assigned software license key for pool 'windows_vista_business', host 'test-client2.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client2.%s" % defaultDomain, licensePoolId="windows_vista_business" )
	print "      =>>>", licenseKey
	assert licenseKey == 'VISTA-G7Z65-KKT6F-L7892-YKKY1'
	
	print "   Getting and assigning software license key from pool 'windows_xp_pro' host 'test-client3.%s'" % defaultDomain
	try:
		licenseKey = be.getAndAssignSoftwareLicenseKey( hostId="test-client3.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
		print "      =>>>", licenseKey
	except BackendMissingDataError, e:
		print "      =>>>", e
		licenseKey = 'NO_MORE_LICENSES'
	assert licenseKey == 'NO_MORE_LICENSES'
	print "   Getting assigned software license key for pool 'windows_xp_pro', host 'test-client3.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client3.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "      =>>>", licenseKey
	assert licenseKey == ''
	
	print "   Getting and assigning software license key from pool 'windows_xp_pro' host 'test-client4.%s'" % defaultDomain
	licenseKey = be.getAndAssignSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "      =>>>", licenseKey
	assert licenseKey == 'WINXP-HR7YV-68XDT-81GTZ-HHZ75'
	print "   Getting assigned software license key for pool 'windows_xp_pro', host 'test-client4.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "      =>>>", licenseKey
	assert licenseKey == 'WINXP-HR7YV-68XDT-81GTZ-HHZ75'
	
	print ""
	
	for licensePoolId in be.getLicensePoolIds_list():
		print "   Getting license statistics for pool '%s'" % licensePoolId
		print "      =>>>", be.getLicenseStatistics(licensePoolId)
	
	print ""
	
	print "   Freeing assigned software license key for pool 'windows_xp_pro', host 'test-client4.%s'" % defaultDomain
	be.freeSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "   Getting assigned software license key for pool 'windows_xp_pro', host 'test-client4.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "      =>>>", licenseKey
	assert licenseKey == ''
	
	print ""
	
	for licensePoolId in be.getLicensePoolIds_list():
		print "   Getting license statistics for pool '%s'" % licensePoolId
		print "      =>>>", be.getLicenseStatistics(licensePoolId)
	
	print ""
	
	print "   Assigning software license key 'WINXP-HR7YV-68XDT-81GTZ-HHZ75' for pool 'windows_xp_pro', host 'test-client4.%s'" % defaultDomain
	be.assignSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licenseKey="WINXP-HR7YV-68XDT-81GTZ-HHZ75", licensePoolId="windows_xp_pro" )
	print "   Getting assigned software license key for pool 'windows_xp_pro', host 'test-client4.%s'" % defaultDomain
	licenseKey = be.getAssignedSoftwareLicenseKey( hostId="test-client4.%s" % defaultDomain, licensePoolId="windows_xp_pro" )
	print "      =>>>", licenseKey
	assert licenseKey == 'WINXP-HR7YV-68XDT-81GTZ-HHZ75'
	
	print ""
	
	for licensePoolId in be.getLicensePoolIds_list():
		print "   Getting license statistics for pool '%s'" % licensePoolId
		print "      =>>>", be.getLicenseStatistics(licensePoolId)
	
	print ""
	
	











