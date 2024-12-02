# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
BackendManager.

If you want to work with an opsi backend in i.e. a script a
BackendManager instance should be your first choice.
A BackendManager instance does the heavy lifting for you so you don't
need to set up you backends, ACL, multiplexing etc. yourself.
"""

from __future__ import absolute_import

import os
import re
import warnings

from opsicommon.logging import get_logger
from opsicommon.objects import BaseObject

from OPSI.Backend.Base import Backend, ExtendedBackend, ExtendedConfigDataBackend
from OPSI.Backend.Depotserver import DepotserverBackend
from OPSI.Backend.HostControl import HostControlBackend
from OPSI.Backend.HostControlSafe import HostControlSafeBackend
from OPSI.Exceptions import BackendConfigurationError
from OPSI.Types import forceBool

from .AccessControl import BackendAccessControl
from .Config import loadBackendConfig
from .Dispatcher import BackendDispatcher
from .Extender import BackendExtender

__all__ = ("BackendManager", "backendManagerFactory")

_BACKEND_CONFIG_NAME_REGEX = re.compile(r"^[a-zA-Z0-9-_]+$")

logger = get_logger("opsi.general")


class BackendManager(ExtendedBackend):
	"""
	The BackendManager manages the backend and glues together various parts.

	This includes extending the backends, dispatching calls to backends,
	limiting the access through ACL.
	"""

	default_config = {
		"dispatchConfigFile": "/etc/opsi/backendManager/dispatch.conf",
		"backendConfigDir": "/etc/opsi/backends",
		"extensionConfigDir": "/etc/opsi/backendManager/extend.d",
		"depotBackend": False,
		"hostControlBackend": True,
		"hostControlSafeBackend": True,
	}

	def __init__(self, **kwargs):
		"""
		Creating a BackendManager.

		If no configuration is given a default config for accessing the
		local backend as configured through the files in
		/etc/opsi/backendManager/ will be used.

		The constructor takes several parameters and these are all optional.

		:param username: A username for authentication.
		:type username: str
		:param password: The corresponding password.
		:type password: str
		:param backend: A backend to use.
		:param dispatchconfig: A pre-definded dispatch config to use.
		:param dispatchconfigfile: The configuration file for dispatching.
		:type dispatchconfigfile: str
		:param backendconfigdir: The location of backend configurations.
		:type backendconfigdir: str
		:param depotbackend: Allow depot actions?
		:type depotbackend: bool
		:param hostcontrolbackend: Allow controlling hosts?
		:type hostcontrolbackend: bool
		:param hostcontrolsafebackend: Allow controlling hosts (safe variant)?
		:type hostcontrolsafebackend: bool
		:param extensionconfigdir: The directory where backend extensions can be found.
		:type extensionconfigdir: str
		:param extend: Extend the backends?
		:type extend: bool
		:param acl: An access control list (ACL) configuration to use.
		:type acl: [[str, ]]
		:param aclfile: Load the ACL from this file.
		:type aclfile: str
		"""
		BaseObject.copy_from_hash = True

		self._backend = None
		self._backendConfigDir = None
		self._overwrite = True
		self._context = self
		self.backendAccessControl = None

		bmc = dict(self.default_config)
		if kwargs:
			if "backend" in kwargs:
				# Do not use any defaults if concrete backend specified
				bmc = {}
			for key, val in kwargs.items():
				found = False
				for bmc_key in list(bmc):
					if bmc_key.lower() == key.lower():
						bmc[bmc_key] = val
						found = True
						break
				if not found:
					bmc[key] = val
		kwargs = bmc

		Backend.__init__(self, **kwargs)

		dispatch = False
		extend = False
		extensionConfigDir = None
		extensionClass = None
		accessControl = False
		accessControlClass = BackendAccessControl
		depotBackend = False
		hostControlBackend = False
		hostControlSafeBackend = False
		loadBackend = None

		argumentToDelete = set()
		for option, value in kwargs.items():
			option = option.lower()
			if option == "backend":
				if isinstance(value, str):
					loadBackend = value
				else:
					self._backend = value
				argumentToDelete.add(option)
			elif option == "backendconfigdir":
				self._backendConfigDir = value
			elif option in ("dispatchconfig", "dispatchconfigfile") and value:
				dispatch = True
			elif option == "depotbackend":
				depotBackend = forceBool(value)
			elif option == "hostcontrolbackend":
				hostControlBackend = forceBool(value)
			elif option == "hostcontrolsafebackend":
				hostControlSafeBackend = forceBool(value)
			elif option == "extensionconfigdir" and value:
				extensionConfigDir = value
				extend = True
			elif option == "extensionclass":
				extensionClass = value
				extend = True
			elif option == "extend":
				extend = forceBool(value)
			elif option in ("acl", "aclfile") and value:
				accessControl = True
			elif option == "accesscontrolclass":
				accessControlClass = value

		for argument in argumentToDelete:
			del kwargs[argument]

		if loadBackend:
			logger.info("* BackendManager is loading backend '%s'", loadBackend)
			self._backend = self.__loadBackend(loadBackend)
			# self._backend is now a ConfigDataBackend

		if not dispatch and not self._backend:
			raise BackendConfigurationError("Neither backend nor dispatch config given")

		if dispatch:
			logger.info("* BackendManager is creating BackendDispatcher")
			self._backend = BackendDispatcher(context=self, **kwargs)
			# self._backend is now a BackendDispatcher which is a ConfigDataBackend

		if extend or depotBackend:
			if dispatch and self._backend.is_extended_config_data_backend:
				logger.info(
					"* BackendManager is using BackendDispatcher as ExtendedConfigDataBackend"
				)
			else:
				logger.info("* BackendManager is creating ExtendedConfigDataBackend")
				# DepotserverBackend/BackendExtender need ExtendedConfigDataBackend backend
				self._backend = ExtendedConfigDataBackend(self._backend, **kwargs)
				# self._backend is now an ExtendedConfigDataBackend

		if depotBackend:
			logger.info("* BackendManager is creating DepotserverBackend")
			self._backend = DepotserverBackend(self._backend, **kwargs)

		if hostControlBackend:
			logger.info("* BackendManager is creating HostControlBackend")
			hostControlBackendConfig = dict(kwargs)
			try:
				hostControlBackendConfig.update(
					self.__loadBackendConfig("hostcontrol")["config"]
				)
			except Exception as err:
				logger.error(
					"Failed to load configuration for HostControlBackend: %s", err
				)
			self._backend = HostControlBackend(
				self._backend, **hostControlBackendConfig
			)

		if hostControlSafeBackend:
			logger.info("* BackendManager is creating HostControlSafeBackend")
			hostControlSafeBackendConfig = dict(kwargs)
			try:
				hostControlSafeBackendConfig.update(
					self.__loadBackendConfig("hostcontrol")["config"]
				)
			except Exception as err:
				logger.error(
					"Failed to load configuration for HostControlSafeBackend: %s", err
				)
			self._backend = HostControlSafeBackend(
				self._backend, **hostControlSafeBackendConfig
			)

		if accessControl:
			logger.info("* BackendManager is creating %s", accessControlClass.__name__)
			self._backend = self.backendAccessControl = accessControlClass(
				backend=self._backend, **kwargs
			)

		if extensionConfigDir or extensionClass:
			logger.info("* BackendManager is creating BackendExtender")
			self._backend = BackendExtender(self._backend, **kwargs)

		self._createInstanceMethods()

	def get_jsonrpc_backend(self):
		dispatcher = self._get_backend_dispatcher()
		return dispatcher._backends.get("jsonrpc", {}).get("instance")

	def __loadBackendConfig(self, name):
		if not self._backendConfigDir:
			raise BackendConfigurationError("Backend config dir not given")
		if not os.path.exists(self._backendConfigDir):
			raise BackendConfigurationError(
				f"Backend config dir '{self._backendConfigDir}' not found"
			)
		if not _BACKEND_CONFIG_NAME_REGEX.search(name):
			raise ValueError(f"Bad backend config name '{name}'")
		name = name.lower()
		backendConfigFile = os.path.join(self._backendConfigDir, f"{name}.conf")
		return loadBackendConfig(backendConfigFile)

	def __loadBackend(self, name):
		config = self.__loadBackendConfig(name)
		if not config["module"]:
			raise BackendConfigurationError(
				f"No module defined in backend config file for '{name}'"
			)
		if not isinstance(config["config"], dict):
			raise BackendConfigurationError(
				f"Bad type for 'config' var in backend config file for '{name}': has to be dict"
			)
		config["config"]["name"] = name
		moduleName = config["module"]
		backendClassName = f"{config['module']}Backend"
		exec_locals: dict[str, object] = {}
		with warnings.catch_warnings():
			exec(
				f"from OPSI.Backend.{moduleName} import {backendClassName}",
				None,
				exec_locals,
			)
		return exec_locals[backendClassName](**config["config"])

	_loadBackend = __loadBackend


def backendManagerFactory(
	user,
	password,
	dispatchConfigFile,
	backendConfigDir,
	extensionConfigDir,
	aclFile,
	depotId,
	postpath,
	context,
	**kwargs,
):
	backendManager = None
	if len(postpath) == 2 and postpath[0] == "backend":
		backendManager = BackendManager(
			backend=postpath[1],
			accessControlContext=context,
			backendConfigDir=backendConfigDir,
			aclFile=aclFile,
			username=user,
			password=password,
			**kwargs,
		)
	elif len(postpath) == 2 and postpath[0] == "extend":
		extendPath = postpath[1]
		if not re.search(r"^[a-zA-Z0-9_-]+$", extendPath):
			raise ValueError(f"Extension config path '{extendPath}' refused")
		backendManager = BackendManager(
			dispatchConfigFile=dispatchConfigFile,
			backendConfigDir=backendConfigDir,
			extensionConfigDir=os.path.join(extensionConfigDir, extendPath),
			aclFile=aclFile,
			accessControlContext=context,
			depotBackend=bool(depotId),
			hostControlBackend=True,
			hostControlSafeBackend=True,
			username=user,
			password=password,
			**kwargs,
		)
	else:
		backendManager = BackendManager(
			dispatchConfigFile=dispatchConfigFile,
			backendConfigDir=backendConfigDir,
			extensionConfigDir=extensionConfigDir,
			aclFile=aclFile,
			accessControlContext=context,
			depotBackend=bool(depotId),
			hostControlBackend=True,
			hostControlSafeBackend=True,
			username=user,
			password=password,
			**kwargs,
		)

	return backendManager
