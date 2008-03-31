# -*- coding: utf-8 -*-
"""
   ========================================
   =          OPSI MySQL Module           =
   ========================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Patrick Ohler <p.ohler@uib.de>, Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.1'

# Imports
import MySQLdb

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
		try:
			self.__conn__ = MySQLdb.connect(
							host = address,
							user = username,
							passwd = password,
							db = database )
		except Exception, e:
			raise BackendIOError("Failed to connect to database '%s' address '%s': %s" % (database, address, e))
		
		self.__cursor__ = self.__conn__.cursor(MySQLdb.cursors.DictCursor)
		
	def db_query(self, query):
		self.__cursor__.execute(query)
		return self.__cursor__.rowcount
		
	def db_getSet(self, query):
		self.__cursor__.execute(query)
		valueSet = self.__cursor__.fetchall()
		if not valueSet:
			return False
		return valueSet
		
	def db_getRow(self, query):
		self.__cursor__.execute(query)
		row = self.__cursor__.fetchone()
		if not row:
			return False
		return row
		
	def db_insert(self, table, valueHash):
		colNames = values = ''
		for (key, value) in valueHash.items():
			colNames += "`%s`, " % key
			if type(value)==type(""):
				values += "\'%s\', " % value
			else:
				values += "%s, " % value
		self.__cursor__.execute("INSERT INTO `%s` (%s) VALUES (%s);" % (table, colNames[:-2], values[:-2]))
		return self.__cursor__.lastrowid
		#return self.__cursor__.rowcount
		
	def db_update(self, table, valueHash):
		pass
		
	def db_close(self):
		self.__cursor__.close()
		self.__conn__.commit()
		self.__conn__.close()

# ======================================================================================================
# =                                    CLASS MYSQLBACKEND                                              =
# ======================================================================================================
class MySQLBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = 'localhost', backendManager=None, args={}):
		''' FileBackend constructor. '''
		
		self._backendManager = backendManager
		
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
				logger.warning("Unknown argument '%s' passed to FileBackend constructor" % option)
		
		self.__mysql__ = MySQL(username = self._username, password = self._password, address = self._address, database = self._database)
	
	def _getRulesFromFile_(self, RulesFile):
		general = relationalTable = additionalHardwareCols = ''
		
		f = open(RulesFile, 'r')
		section = ''
		for line in f.readlines():
			line2 = line.strip()
			if not line2 or line2[0] in ('#', '/', ';'):
				continue
			
			if re.match('\[(\w+)\]', line):
				match = re.search('\[(\w+)\]', line)
				section = match.group(1)
				continue
			
			if section and line:
				if section=='additionalHardwareCols':
					additionalHardwareCols += line.strip() + '\n'
				elif section=='general':
					general += line.strip() + '\n'
				elif section=='relationalTable':
					relationalTable += line.strip() + '\n'
		f.close()
		
		return {
			"additionalHardwareCols": additionalHardwareCols,
			"general": general,
			"relationalTable": relationalTable }
		
	def _toSQL_(self, classes, rules):
		'''
		example:
		CREATE TABLE `test` (
			`id` INT NOT NULL ,
			`text` VARCHAR( 255 ) NOT NULL ,
			`time` TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ,
			PRIMARY KEY ( `id` )
		) ENGINE = MYISAM ;
		'''
		
		text = ''
		for className in classes:
			hardwareTable = relationalTable = ''
			hardwareTable += 'CREATE TABLE `%s` (\n' % (className["Class"]["Opsi"])
			hardwareTable += rules["additionalHardwareCols"]
			
			relationalTable += 'CREATE TABLE `PC2%s` (\n' % (className["Class"]["Opsi"])
			relationalTable += rules["relationalTable"]
			
			for item in className["Values"]:
				if item["Scope"]=="g":
					hardwareTable += '`%s` %s NULL,\n' % (item["Opsi"], item["Type"])
				elif item["Scope"]=="i":
					relationalTable += '`%s` %s NULL,\n' % (item["Opsi"], item["Type"])
			if hardwareTable.strip()[-1:]==',':
				hardwareTable = hardwareTable.strip()[:-1]+'\n'
			if relationalTable.strip()[-1:]==',':
				relationalTable = relationalTable.strip()[:-1]+'\n'
			
			text += hardwareTable + ') ENGINE = MYISAM ;\n\n' + relationalTable + ') ENGINE = MYISAM ;\n\n'
		
		text += rules["general"]	
		return text
	
	def _writeToServer_(self, queries):
		for query in queries.split(';'):
			if query.strip():
				self.__mysql__.db_query(query + ' ;')
	
	def createOpsiBase(self):
		queries = self._toSQL_(self.getOpsiAuditConf(), self._getRulesFromFile_("opsiDbRules.conf"))
		self._writeToServer_(queries)
	
	def getHardwareInformation_hash(self, hostId):
		pass
	
	def setHardwareInformation(self, hostId, info):
		if not type(info) is dict:
			raise BackendBadValueError("Hardware information must be dict")
		
		'''
		INSERT INTO `test` ( `test1` , `test2` , `test3` , `test4` )
			VALUES (
			'test', '23', NOW( ) , '0000-00-00 00:00:00'
			);
		'''
		# is the host already in the db? when yes, wich id?
		hostDbId = self.__mysql__.db_getRow("SELECT PC_id FROM pc WHERE hostId='%s'" % hostId)
		
		if hostDbId:
			hostDbId = hostDbId['PC_id']
		else:
			hostDbId = self.__mysql__.db_insert("pc", {"hostId": hostId})
		
		config = self.getOpsiHWAuditConf()
		# reorganize the config quickly
		configNew = {}
		for i in config:
			for j in i["Values"]:
				if not configNew.has_key(i["Class"]["Opsi"]):
					configNew[i["Class"]["Opsi"]] = {}
				configNew[i["Class"]["Opsi"]][j["Opsi"]] = j["Scope"]
		
		#logger.debug2( jsonObjToBeautifiedText(configNew) )
		queries = ''
		for (key,values) in info.items():
			n = 0
			for value in values:
				individual = {}
				hardware = {}
				for (opsiName,opsiValue) in value.items():
					if (type(opsiValue) == type(None)):
						continue
					# this is an individual information, put it into the ralational table
					if configNew[key][opsiName]=="i":
						if type(opsiValue) is unicode:
							individual[opsiName] = opsiValue.encode('utf-8')
						else:
							individual[opsiName] = opsiValue
					# this musst be an global hardware information, put it into the hardware table
					else:
						if type(opsiValue) is unicode:
							hardware[opsiName] = opsiValue.encode('utf-8')
						else:
							hardware[opsiName] = opsiValue
				n += 1
				hw_id = self.__mysql__.db_insert(key, hardware)
				individual["hw_id"] = hw_id
				individual["pc_id"] = hostDbId
				self.__mysql__.db_insert("PC2%s" % key, individual)
	
	def deleteHardwareInformation(self, hostId):
		pass
	
	def exit(self):
		self.__mysql__.db_close()





