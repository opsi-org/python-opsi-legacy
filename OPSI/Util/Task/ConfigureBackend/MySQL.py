# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Functionality to automatically configure an OPSI MySQL backend.

.. versionadded:: 4.0.4.6
"""

from contextlib import closing, contextmanager

MySQLdb = None
try:
	import MySQLdb
except ImportError:
	pass

from opsicommon.logging import get_logger  # noqa: E402

import OPSI.Util.Task.ConfigureBackend as backendUtils  # noqa: E402
from OPSI.Backend.MySQL import MySQLBackend  # noqa: E402

DATABASE_EXISTS_ERROR_CODE = 1007
ACCESS_DENIED_ERROR_CODE = 1044
INVALID_DEFAULT_VALUE = 1067

logger = get_logger("opsi.general")


class DatabaseConnectionFailedException(Exception):
	pass


def configureMySQLBackend(
	dbAdminUser,
	dbAdminPass,
	config=None,
	systemConfiguration=None,
	additionalBackendConfig=None,
	backendConfigFile="/etc/opsi/backends/mysql.conf",
	notificationFunction=None,
	errorFunction=None,
):
	"""
	Does the initial configuration of an MySQL backend.

	It will set up the database for OPSI, grant the specified user the
	rights needed, try if the connection works, save the configuration
	to the backend file and create the backend base.

	:param dbAdminUser: Username of the DBA.
	:param dbAdminPass: Password for the DBA.
	:param backendConfigFile: Path to mysql backend configuration file.
	:param config: The configuration for the database. \
This should include values for the keys `database`, `username`, \
`password` and `address`. `address` is also the address of the database. \
If not given this will be read from ``backendConfigFile``.
	:type config: dict
	:param additionalBackendConfig: If given this will update ``config``
	:param notificationFunction: A function that notifications will be \
passed on to. Defaults to ``logger.notice``.
	:type notificationFunction: func
	:param errorFunction: A function that error messages will be passed \
on to. Defaults to ``logger.error``.
	:type errorFunction: func
	"""

	if notificationFunction is None:
		notificationFunction = logger.notice

	if errorFunction is None:
		errorFunction = logger.error

	if config is None:
		config = backendUtils.getBackendConfiguration(backendConfigFile)

	if additionalBackendConfig is not None:
		config.update(additionalBackendConfig)

	try:
		initializeDatabase(
			dbAdminUser,
			dbAdminPass,
			config,
			systemConfig=systemConfiguration,
			notificationFunction=notificationFunction,
		)
	except DatabaseConnectionFailedException as err:
		errorFunction(
			"Failed to connect to host '%s' as user '%s': %s",
			config["address"],
			dbAdminUser,
			err,
		)
		raise err
	except Exception as err:
		errorFunction(err)
		raise err

	backendUtils.updateConfigFile(backendConfigFile, config, notificationFunction)

	notificationFunction("Initializing mysql backend")
	backend = MySQLBackend(**config)
	try:
		backend.backend_createBase()
	except Exception as err:  # pylint: disable=broad-except
		if err.args[0] == INVALID_DEFAULT_VALUE:
			errorFunction(  # pylint: disable=logging-fstring-interpolation
				f"It seems you have the MySQL strict mode enabled. Please read the opsi handbook.\n{err}"
			)
		raise err

	notificationFunction("Finished initializing mysql backend.")


def initializeDatabase(
	dbAdminUser,
	dbAdminPass,
	config,
	systemConfig=None,
	notificationFunction=None,
	errorFunction=None,
):
	"""
	Create a database and grant the OPSI user the needed rights on it.
	"""

	if not MySQLdb:
		raise ModuleNotFoundError(
			"Missing mysqlclient module to perform initializeDatabase operation."
		)

	@contextmanager
	def connectAsDBA():
		conConfig = {
			"host": config["address"],
			"user": dbAdminUser,
			"passwd": dbAdminPass,
		}

		try:
			with closing(MySQLdb.connect(**conConfig)) as db:
				yield db
		except Exception as err:  # pylint: disable=broad-except
			if config["address"] == "127.0.0.1":
				logger.info(
					"Failed to connect with tcp/ip (%s), retrying with socket", err
				)
				try:
					conConfig["host"] = "localhost"
					with closing(MySQLdb.connect(**conConfig)) as db:
						yield db
				except Exception as error:  # pylint: disable=broad-except
					raise DatabaseConnectionFailedException(error) from error
			else:
				raise DatabaseConnectionFailedException(err) from err

	def createUser(host):
		notificationFunction(
			f"Creating user '{config['username']}' and granting all rights on '{config['database']}'"
		)
		db.query(f"CREATE USER IF NOT EXISTS '{config['username']}'@'{host}'")
		try:
			db.query(
				f"ALTER USER '{config['username']}'@'{host}' IDENTIFIED WITH mysql_native_password BY '{config['password']}'"
			)
		except Exception as err:  # pylint: disable=broad-except
			logger.debug(err)
			try:
				db.query(
					f"ALTER USER '{config['username']}'@'{host}' IDENTIFIED BY '{config['password']}'"
				)
			except Exception as error:  # pylint: disable=broad-except
				logger.debug(error)
				db.query(
					f"SET PASSWORD FOR'{config['username']}'@'{host}' = PASSWORD('{config['password']}')"
				)
		db.query(
			f"GRANT ALL ON {config['database']}.* TO '{config['username']}'@'{host}'"
		)
		db.query("FLUSH PRIVILEGES")
		notificationFunction(f"User '{config['username']}' created and privileges set")

	if notificationFunction is None:
		notificationFunction = logger.notice

	if errorFunction is None:
		errorFunction = logger.error

	if systemConfig is None:
		systemConfig = backendUtils._getSysConfig()  # pylint: disable=protected-access

	# Connect to database host
	notificationFunction(
		"Connecting to host '{0[address]}' as user '{username}'".format(
			config, username=dbAdminUser
		)
	)
	with connectAsDBA() as db:
		notificationFunction(
			"Successfully connected to host '{0[address]}'"
			" as user '{username}'".format(config, username=dbAdminUser)
		)

		# Create opsi database and user
		notificationFunction("Creating database '{database}'".format(**config))
		try:
			db.query(
				"CREATE DATABASE {database} DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_bin;".format(
					**config
				)
			)
		except MySQLdb.OperationalError as err:
			if err.args[0] == ACCESS_DENIED_ERROR_CODE:
				raise DatabaseConnectionFailedException(str(err)) from err
			raise err
		except MySQLdb.ProgrammingError as err:
			if err.args[0] != DATABASE_EXISTS_ERROR_CODE:
				raise err
		notificationFunction("Database '{database}' created".format(**config))

		if config["address"] in (
			"localhost",
			"127.0.0.1",
			systemConfig["hostname"],
			systemConfig["fqdn"],
		):
			createUser("localhost")
			if config["address"] not in ("localhost", "127.0.0.1"):
				createUser(config["address"])
		else:
			createUser(systemConfig["ipAddress"])
			createUser(systemConfig["fqdn"])
			createUser(systemConfig["hostname"])

	# Test connection / credentials
	notificationFunction(
		"Testing connection to database '{database}' as " "user '{username}'".format(
			**config
		)
	)

	userConnectionSettings = {
		"host": config["address"],
		"user": config["username"],
		"passwd": config["password"],
		"db": config["database"],
	}
	try:
		with closing(MySQLdb.connect(**userConnectionSettings)):
			pass
	except Exception as err:  # pylint: disable=broad-except
		raise DatabaseConnectionFailedException(err) from err

	notificationFunction(
		"Successfully connected to host '{address}' as user" " '{username}'".format(
			**config
		)
	)
