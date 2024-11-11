# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the update of the MySQL backend from an older version.
"""

import os

import pytest

from OPSI.Backend.MySQL import MySQL, MySQLBackend
from OPSI.Backend.SQL import DATABASE_SCHEMA_VERSION, createSchemaVersionTable
from OPSI.Util.Task.ConfigureBackend import updateConfigFile
from OPSI.Util.Task.UpdateBackend.MySQL import (
	getTableColumns,
	readSchemaVersion,
	updateMySQLBackend,
	updateSchemaVersion,
)

from .Backends.MySQL import MySQLconfiguration, cleanDatabase, getTableNames


@pytest.fixture
def mysqlBackendConfig():
	if not MySQLconfiguration:
		pytest.skip("Missing configuration for MySQL.")

	return MySQLconfiguration


@pytest.fixture
def mySQLBackendConfigFile(mysqlBackendConfig, tempDir):
	configFile = os.path.join(tempDir, "asdf")
	with open(configFile, "w"):
		pass

	updateConfigFile(configFile, mysqlBackendConfig)

	yield configFile


def getColumnLength(columnType):
	_, currentLength = columnType.split("(")
	currentLength = int(currentLength[:-1])

	return currentLength


def testCorrectingLicenseOnClientLicenseKeyLength(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	"""
	Test if the license key length is correctly set.

	An backend updated from an older version has the field 'licenseKey'
	on the LICENSE_ON_CLIENT table as VARCHAR(100).
	A fresh backend has the length of 1024.
	The size should be the same.
	"""
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		for tableName in (
			"LICENSE_ON_CLIENT",
			"SOFTWARE_CONFIG",
			"SOFTWARE_LICENSE_TO_LICENSE_POOL",
		):
			print("Checking {0}...".format(tableName))

			with db.session() as session:
				assert tableName in getTableNames(db, session)

				assertColumnIsVarchar(db, session, tableName, "licenseKey", 1024)


def testCorrectingProductIdLength(mysqlBackendConfig, mySQLBackendConfigFile):
	"""
	Test if the product id length is correctly set.
	"""
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		for tableName in ("PRODUCT_PROPERTY",):
			print("Checking {0}...".format(tableName))

			with db.session() as session:
				assert tableName in getTableNames(db, session)

				assertColumnIsVarchar(db, session, tableName, "productId", 255)


def test_correcting_ipaddres_length(mysqlBackendConfig, mySQLBackendConfigFile):
	"""
	Test if host.ipAddress length is correctly set.
	"""
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		for tableName in ("HOST",):
			print("Checking {0}...".format(tableName))

			with db.session() as session:
				assert tableName in getTableNames(db, session)

				assertColumnIsVarchar(db, session, tableName, "ipAddress", 255)


def testDropTableBootConfiguration(mysqlBackendConfig, mySQLBackendConfigFile):
	"""
	Test if the BOOT_CONFIGURATION table gets dropped with an update.
	"""
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with db.session() as session:
			assert "BOOT_CONFIGURATION" not in getTableNames(db, session)


def createRequiredTables(database):
	with database.session() as session:
		table = """CREATE TABLE `LICENSE_POOL` (
				`licensePoolId` VARCHAR(100) NOT NULL,
				`type` varchar(30) NOT NULL,
				`description` varchar(200),
				PRIMARY KEY (`licensePoolId`)
			) %s;
			""" % database.getTableCreationOptions("LICENSE_POOL")
		database.execute(session, table)
		database.execute(
			session,
			"CREATE INDEX `index_license_pool_type` on `LICENSE_POOL` (`type`);",
		)

		table = """CREATE TABLE `LICENSE_CONTRACT` (
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
			""" % database.getTableCreationOptions("LICENSE_CONTRACT")
		database.execute(session, table)
		database.execute(
			session,
			"CREATE INDEX `index_license_contract_type` on `LICENSE_CONTRACT` (`type`);",
		)

		table = """CREATE TABLE `SOFTWARE_LICENSE` (
				`softwareLicenseId` VARCHAR(100) NOT NULL,
				`licenseContractId` VARCHAR(100) NOT NULL,
				`type` varchar(30) NOT NULL,
				`boundToHost` varchar(255),
				`maxInstallations` integer,
				`expirationDate` TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00',
				PRIMARY KEY (`softwareLicenseId`),
				FOREIGN KEY (`licenseContractId`) REFERENCES `LICENSE_CONTRACT` (`licenseContractId`)
			) %s;
			""" % database.getTableCreationOptions("SOFTWARE_LICENSE")
		database.execute(session, table)
		database.execute(
			session,
			"CREATE INDEX `index_software_license_type` on `SOFTWARE_LICENSE` (`type`);",
		)
		database.execute(
			session,
			"CREATE INDEX `index_software_license_boundToHost` on `SOFTWARE_LICENSE` (`boundToHost`);",
		)

		database.execute(
			session,
			"""CREATE TABLE `PRODUCT_PROPERTY` (
			`productId` varchar(128) NOT NULL,
			`productVersion` varchar(32) NOT NULL,
			`packageVersion` varchar(16) NOT NULL,
			`propertyId` varchar(200) NOT NULL,
			`type` varchar(30) NOT NULL,
			`description` TEXT,
			`multiValue` bool NOT NULL,
			`editable` bool NOT NULL,
			PRIMARY KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`)
		) ENGINE=InnoDB DEFAULT CHARSET utf8 COLLATE utf8_general_ci """,
		)

		database.execute(
			session,
			"""CREATE TABLE `BOOT_CONFIGURATION` (
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
			PRIMARY KEY (`name`, `clientId`)
		) ENGINE=InnoDB DEFAULT CHARSET utf8 COLLATE utf8_general_ci """,
		)

		database.execute(
			session,
			"""CREATE TABLE `SOFTWARE_LICENSE_TO_LICENSE_POOL` (
			`softwareLicenseId` VARCHAR(100) NOT NULL,
			`licensePoolId` VARCHAR(100) NOT NULL,
			`licenseKey` VARCHAR(100),
			PRIMARY KEY (`softwareLicenseId`, `licensePoolId`),
			FOREIGN KEY (`softwareLicenseId`) REFERENCES `SOFTWARE_LICENSE` (`softwareLicenseId`),
			FOREIGN KEY (`licensePoolId`) REFERENCES `LICENSE_POOL` (`licensePoolId`)
		) %s;"""
			% database.getTableCreationOptions("SOFTWARE_LICENSE_TO_LICENSE_POOL"),
		)

		database.execute(
			session,
			"""CREATE TABLE `LICENSE_USED_BY_HOST` (
			`softwareLicenseId` VARCHAR(100) NOT NULL,
			`licensePoolId` VARCHAR(100) NOT NULL,
			`hostId` varchar(255),
			`licenseKey` VARCHAR(100),
			`notes` VARCHAR(1024)
		) ENGINE=InnoDB DEFAULT CHARSET utf8 COLLATE utf8_general_ci """,
		)

		database.execute(
			session,
			"""CREATE TABLE `SOFTWARE_CONFIG` (
			`config_id` integer NOT NULL AUTO_INCREMENT,
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
			`licenseKey` VARCHAR(100),
			PRIMARY KEY (`config_id`)
		) %s;
		"""
			% database.getTableCreationOptions("SOFTWARE_CONFIG"),
		)

		database.execute(
			session,
			"""CREATE TABLE `PRODUCT` (
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
			"""
			% database.getTableCreationOptions("PRODUCT"),
		)
		database.execute(
			session, "CREATE INDEX `index_product_type` on `PRODUCT` (`type`);"
		)

		database.execute(
			session,
			"""CREATE TABLE `PRODUCT_PROPERTY_VALUE` (
			`product_property_id` integer NOT NULL """
			+ database.AUTOINCREMENT
			+ """,
			`productId` varchar(255) NOT NULL,
			`productVersion` varchar(32) NOT NULL,
			`packageVersion` varchar(16) NOT NULL,
			`propertyId` varchar(200) NOT NULL,
			`value` text,
			`isDefault` bool,
			PRIMARY KEY (`product_property_id`),
			FOREIGN KEY (`productId`, `productVersion`, `packageVersion`, `propertyId`) REFERENCES `PRODUCT_PROPERTY` (`productId`, `productVersion`, `packageVersion`, `propertyId`)
		) %s; """
			% database.getTableCreationOptions("PRODUCT_PROPERTY_VALUE"),
		)

		createOpsi40HostTable(database, session)

		database.execute(
			session,
			"""CREATE TABLE `GROUP` (
			`type` varchar(30) NOT NULL,
			`groupId` varchar(255) NOT NULL,
			`parentGroupId` varchar(255),
			`description` varchar(100),
			`notes` varchar(500),
			PRIMARY KEY (`type`, `groupId`)
		) %s;
		"""
			% database.getTableCreationOptions("GROUP"),
		)
		database.execute(
			session,
			"CREATE INDEX `index_group_parentGroupId` on `GROUP` (`parentGroupId`);",
		)

		database.execute(
			session,
			"""CREATE TABLE `OBJECT_TO_GROUP` (
			`object_to_group_id` integer NOT NULL """
			+ database.AUTOINCREMENT
			+ """,
			`groupType` varchar(30) NOT NULL,
			`groupId` varchar(100) NOT NULL,
			`objectId` varchar(255) NOT NULL,
			PRIMARY KEY (`object_to_group_id`),
			FOREIGN KEY (`groupType`, `groupId`) REFERENCES `GROUP` (`type`, `groupId`)
		) %s;
		"""
			% database.getTableCreationOptions("OBJECT_TO_GROUP"),
		)
		database.execute(
			session,
			"CREATE INDEX `index_object_to_group_objectId` on `OBJECT_TO_GROUP` (`objectId`);",
		)

		database.execute(
			session,
			"""CREATE TABLE `WINDOWS_SOFTWARE_ID_TO_PRODUCT` (
			`windowsSoftwareId` VARCHAR(100) NOT NULL,
			`productId` varchar(255) NOT NULL,
			PRIMARY KEY (`windowsSoftwareId`, `productId`)
		) %s;
		"""
			% database.getTableCreationOptions("WINDOWS_SOFTWARE_ID_TO_PRODUCT"),
		)


def createOpsi40HostTable(database, session):
	"Creates a table for hosts as seen in opsi 4.0."

	query = """CREATE TABLE `HOST` (
		`hostId` varchar(255) NOT NULL,
		`type` varchar(30),
		`description` varchar(100),
		`notes` varchar(500),
		`hardwareAddress` varchar(17),
		`ipAddress` varchar(15),
		`inventoryNumber` varchar(30),
		`created` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
	) %s;""" % database.getTableCreationOptions("HOST")
	database.execute(session, query)


def assertColumnIsVarchar(database, session, tableName, columnName, length):
	for column in getTableColumns(database, session, tableName):
		if column.name.lower() == columnName.lower():
			assert column.type.lower().startswith("varchar(")
			assert getColumnLength(column.type) == length
			break
	else:
		raise ValueError(
			"Missing column '{1}' in table {0!r}".format(tableName, columnName)
		)


def testInsertingSchemaNumber(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with db.session() as session:
			assert "OPSI_SCHEMA" in getTableNames(db, session)

			for column in getTableColumns(db, session, "OPSI_SCHEMA"):
				name = column.name
				if name == "version":
					assert column.type.lower().startswith("int")
				elif name == "updateStarted":
					assert column.type.lower().startswith("timestamp")
				elif name == "updateEnded":
					assert column.type.lower().startswith("timestamp")
				else:
					raise Exception("Unexpected column!")


def testReadingSchemaVersionIfTableIsMissing(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		with db.session() as session:
			assert readSchemaVersion(db, session) is None


def testReadingSchemaVersionFromEmptyTable(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		with db.session() as session:
			createSchemaVersionTable(db, session)
			assert readSchemaVersion(db, session) is None


def testUpdatingSchemaVersion(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		with db.session() as session:
			createSchemaVersionTable(db, session)

			version = readSchemaVersion(db, session)
			assert version is None

			with updateSchemaVersion(db, session, version=2):
				pass  # NOOP

			version = readSchemaVersion(db, session)
			assert version == 2


def testReadingSchemaVersionOnlyReturnsNewestValue(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		with db.session() as session:
			createSchemaVersionTable(db, session)

			with updateSchemaVersion(db, session, version=1):
				pass

			with updateSchemaVersion(db, session, version=15):
				pass

			for number in range(1, 4):
				with updateSchemaVersion(db, session, version=number * 2):
					pass

			with updateSchemaVersion(db, session, version=3):
				pass

			assert readSchemaVersion(db, session) == 15


# def testReadingSchemaVersionFailsOnUnfinishedUpdate(mysqlBackendConfig, mySQLBackendConfigFile):
# 	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
# 		with db.session() as session:
# 			createSchemaVersionTable(db, session)

# 			try:
# 				with updateSchemaVersion(db, session, version=10):
# 					raise RuntimeError("For testing.")
# 			except RuntimeError:
# 				pass

# 			with pytest.raises(DatabaseMigrationUnfinishedError):
# 				readSchemaVersion(db, session)


def testUpdatingCurrentBackendDoesBreakNothing(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)):
		with MySQLBackend(**mysqlBackendConfig) as freshBackend:
			freshBackend.backend_createBase()

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)
		# Updating again. Should break nothing.
		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with MySQLBackend(**mysqlBackendConfig) as anotherBackend:
			# We want to have the latest schema version
			with anotherBackend._sql.session() as session:
				assert DATABASE_SCHEMA_VERSION == readSchemaVersion(
					anotherBackend._sql, session
				)


def testCreatingBackendSetsTheLatestSchemaVersion(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		with MySQLBackend(**mysqlBackendConfig) as freshBackend:
			freshBackend.backend_createBase()
			with db.session() as session:
				assert readSchemaVersion(db, session) == DATABASE_SCHEMA_VERSION


def testAddingIndexToProductPropertyValues(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)
		# Just making sure nothing breaks because checking if the right
		# index exists in mysql comes near totally senseless torture.

		# Calling the update procedure a second time must not fail.
		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)


def testAddingWorkbenchAttributesToHost(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with db.session() as session:
			changesFound = 0
			for column in getTableColumns(db, session, "HOST"):
				if column.name == "workbenchLocalUrl":
					assert column.type.lower().startswith("varchar(")
					assert getColumnLength(column.type) == 128
					changesFound += 1
				elif column.name == "workbenchRemoteUrl":
					assert column.type.lower().startswith("varchar(")
					assert getColumnLength(column.type) == 255
					changesFound += 1

				if changesFound == 2:
					break

			assert changesFound == 2


def testCorrectingObjectToGroupGroupIdFieldLength(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)
		with db.session() as session:
			for column in getTableColumns(db, session, "OBJECT_TO_GROUP"):
				if column.name == "groupId":
					assert column.type.lower().startswith("varchar(")
					assert getColumnLength(column.type) == 255
					break


def testIncreasingInventoryNumberFieldLength(
	mysqlBackendConfig, mySQLBackendConfigFile
):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with db.session() as session:
			for column in getTableColumns(db, session, "HOST"):
				if column.name == "inventoryNumber":
					assert column.type.lower().startswith("varchar(")
					assert getColumnLength(column.type) == 64
					break
			else:
				raise RuntimeError("Expected to find matching column.")


def testChangingSoftwareConfigIdToBigInt(mysqlBackendConfig, mySQLBackendConfigFile):
	with cleanDatabase(MySQL(**mysqlBackendConfig)) as db:
		createRequiredTables(db)

		updateMySQLBackend(backendConfigFile=mySQLBackendConfigFile)

		with db.session() as session:
			for column in getTableColumns(db, session, "SOFTWARE_CONFIG"):
				if column.name == "config_id":
					assert column.type.lower().startswith("bigint")
					break
			else:
				raise RuntimeError("Unable to find column SOFTWARE_CONFIG.config_id")
