# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend access control.
"""

import inspect
import os
import re
import types
import typing  # This is needed for dynamic loading  # noqa: F401
from functools import lru_cache
from typing import Any, Generator  # This is needed for dynamic loading  # noqa: F401

import opsicommon  # This is needed for dynamic loading  # noqa: F401
from opsicommon.logging import get_logger

from OPSI.Backend.Base import ConfigDataBackend, ExtendedConfigDataBackend
from OPSI.Backend.Base.Extended import get_function_signature_and_args
from OPSI.Backend.Depotserver import DepotserverBackend
from OPSI.Backend.HostControl import HostControlBackend
from OPSI.Backend.HostControlSafe import HostControlSafeBackend
from OPSI.Config import OPSI_ADMIN_GROUP
from OPSI.Exceptions import (
	BackendAuthenticationError,
	BackendConfigurationError,
	BackendIOError,
	BackendMissingDataError,
	BackendPermissionDeniedError,
	BackendUnaccomplishableError,
)
from OPSI.Object import *  # This is needed for dynamic loading  # pylint: disable=wildcard-import,unused-wildcard-import  # noqa: F401,F403
from OPSI.Types import forceBool, forceList, forceUnicodeList, forceUnicodeLowerList
from OPSI.Util.File.Opsi import BackendACLFile, OpsiConfFile

__all__ = ("BackendAccessControl",)

logger = get_logger("opsi.general")


class UserStore:  # pylint: disable=too-few-public-methods
	"""Stores user information"""

	def __init__(self):
		self.username = None
		self.password = None
		self.userGroups = set()
		self.host = None
		self.authenticated = False
		self.isAdmin = False
		self.isReadOnly = False


class BackendAccessControl:
	"""Access control for a Backend"""

	def __init__(self, backend, **kwargs):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
		self._backend = backend
		self._context = backend
		self._acl = None
		self._aclFile = None
		self._user_store = UserStore()
		self._auth_module = None

		pam_service = None
		kwargs = {k.lower(): v for k, v in kwargs.items()}
		for option, value in kwargs.items():
			if option == "acl":
				self._acl = value
			elif option == "aclfile":
				self._aclFile = value
			elif option == "pamservice":
				logger.debug("Using PAM service %s", value)
				pam_service = value
			elif option in ("context", "accesscontrolcontext"):
				self._context = value
			elif option in ("user_store", "userstore"):
				self._user_store = value
			elif option in ("auth_module", "authmodule"):
				self._auth_module = value

		if not self._backend:
			raise BackendAuthenticationError("No backend specified")
		if isinstance(self._backend, BackendAccessControl):
			raise BackendConfigurationError(
				"Cannot use BackendAccessControl instance as backend"
			)

		if not self._auth_module:  # pylint: disable=too-many-nested-blocks
			try:
				ldap_conf = OpsiConfFile().get_ldap_auth_config()
				if ldap_conf:
					logger.debug("Using ldap auth with config: %s", ldap_conf)

					available_modules = self._context.backend_getLicensingInfo()[
						"available_modules"
					]
					if "directory-connector" in available_modules:
						import OPSI.Backend.Manager.Authentication.LDAP  # pylint: disable=import-outside-toplevel

						self._auth_module = (
							OPSI.Backend.Manager.Authentication.LDAP.LDAPAuthentication(
								**ldap_conf
							)
						)
					else:
						logger.error(
							"Disabling ldap authentication: directory-connector module not available"
						)

			except Exception as err:  # pylint: disable=broad-except
				logger.debug(err)
			if not self._auth_module:
				if os.name == "posix":
					import OPSI.Backend.Manager.Authentication.PAM  # pylint: disable=import-outside-toplevel

					self._auth_module = (
						OPSI.Backend.Manager.Authentication.PAM.PAMAuthentication(
							pam_service
						)
					)
				elif os.name == "nt":
					import OPSI.Backend.Manager.Authentication.NT  # pylint: disable=import-outside-toplevel

					self._auth_module = (
						OPSI.Backend.Manager.Authentication.NT.NTAuthentication()
					)

		self._createInstanceMethods()
		if self._aclFile:
			self.__loadACLFile()

		if not self._acl:
			admin_groupname = OPSI_ADMIN_GROUP
			if self._auth_module:
				admin_groupname = self._auth_module.get_admin_groupname()
			self._acl = [
				[
					r".*",
					[
						{
							"type": "sys_group",
							"ids": [admin_groupname],
							"denyAttributes": [],
							"allowAttributes": [],
						}
					],
				]
			]

		# Pre-compiling regex patterns for speedup.
		for i, (pattern, acl) in enumerate(self._acl):
			self._acl[i] = (re.compile(pattern), acl)

		if kwargs.get("username") and kwargs.get("password"):
			self.authenticate(
				kwargs["username"], kwargs["password"], kwargs.get("forcegroups")
			)

	@property
	def user_store(self):
		if callable(self._user_store):
			return self._user_store()
		return self._user_store

	@user_store.setter
	def user_store(self, user_store):
		self._user_store = user_store

	def authenticate(
		self,
		username: str,
		password: str,
		forceGroups: list[str] = None,
		auth_type: str = None,
	):  # pylint: disable=too-many-branches,too-many-statements
		if not auth_type:
			if re.search(r"^[^.]+\.[^.]+\.\S+$", username) or re.search(
				r"^[a-fA-F0-9]{2}(:[a-fA-F0-9]{2}){5}$", username
			):
				# Username is a fqdn or mac address
				auth_type = "opsi-hostkey"
			else:
				auth_type = "auth-module"

		self.user_store.authenticated = False
		self.user_store.username = username
		self.user_store.password = password
		self.auth_type = auth_type

		if not self.user_store.username:
			raise BackendAuthenticationError("No username specified")
		if not self.user_store.password:
			raise BackendAuthenticationError("No password specified")
		try:
			if self.auth_type == "opsi-hostkey":
				self.user_store.username = self.user_store.username.lower()
				host_filter = {}
				if re.search(
					r"^[a-fA-F0-9]{2}(:[a-fA-F0-9]{2}){5}$", self.user_store.username
				):
					logger.debug(
						"Trying to authenticate by mac address and opsi host key"
					)
					host_filter["hardwareAddress"] = self.user_store.username
				else:
					logger.debug("Trying to authenticate by host id and opsi host key")
					self.user_store.username = self.user_store.username.rstrip(".")
					host_filter["id"] = self.user_store.username

				try:
					host = self._context.host_getObjects(**host_filter)
				except AttributeError as err:
					logger.debug(err)
					raise BackendUnaccomplishableError(
						f"Passed backend has no method 'host_getObjects', cannot authenticate host '{self.user_store.username}'"
					) from err

				try:
					self.user_store.host = host[0]
				except IndexError as err:
					logger.debug(err)
					raise BackendMissingDataError(
						f"Host '{self.user_store.username}' not found in backend {self._context}"
					) from err

				self.user_store.username = self.user_store.host.id

				if not self.user_store.host.opsiHostKey:
					raise BackendMissingDataError(
						f"OpsiHostKey not found for host '{self.user_store.username}'"
					)
				one_time_password = getattr(
					self.user_store.host, "oneTimePassword", None
				)

				logger.confidential(
					"Host '%s' authentication: password sent '%s', host key '%s', onetime password '%s'",
					self.user_store.host.id,
					self.user_store.password,
					self.user_store.host.opsiHostKey,
					one_time_password,
				)

				if (
					self.user_store.host.opsiHostKey
					and self.user_store.password == self.user_store.host.opsiHostKey
				):
					logger.info(
						"Host '%s' authenticated by host key", self.user_store.host.id
					)
				elif (
					one_time_password and self.user_store.password == one_time_password
				):
					logger.info(
						"Host '%s' authenticated by onetime password",
						self.user_store.host.id,
					)
					self.user_store.host.setOneTimePassword("")
					host = self._context.host_updateObject(self.user_store.host)
				else:
					raise BackendAuthenticationError(
						f"Authentication of host '{self.user_store.host.id}' failed"
					)

				self.user_store.authenticated = True
				self.user_store.isAdmin = self._isOpsiDepotserver()
				self.user_store.isReadOnly = False
			elif self.auth_type == "opsi-passwd":
				credentials = self._context.user_getCredentials(
					self.user_store.username
				)
				if (
					self.user_store.password
					and self.user_store.password == credentials.get("password")
				):
					self.user_store.authenticated = True
				else:
					raise BackendAuthenticationError(
						f"Authentication failed for user {self.user_store.username}"
					)
			elif self.auth_type == "auth-module":
				# Get a fresh instance
				auth_module = self._auth_module.get_instance()
				# System user trying to log in with username and password
				logger.debug(
					"Trying to authenticate by user authentication module %s",
					auth_module,
				)

				if not auth_module:
					raise BackendAuthenticationError(
						"Authentication module unavailable"
					)

				try:
					auth_module.authenticate(
						self.user_store.username, self.user_store.password
					)
				except Exception as err:
					raise BackendAuthenticationError(
						f"Authentication failed for user '{self.user_store.username}': {err}"
					) from err

				# Authentication did not throw exception => authentication successful
				self.user_store.authenticated = True
				if forceGroups:
					self.user_store.userGroups = forceUnicodeList(forceGroups)
					logger.info(
						"Forced groups for user %s: %s",
						self.user_store.username,
						", ".join(self.user_store.userGroups),
					)
				else:
					self.user_store.userGroups = auth_module.get_groupnames(
						self.user_store.username
					)
				self.user_store.isAdmin = auth_module.user_is_admin(
					self.user_store.username
				)
				self.user_store.isReadOnly = auth_module.user_is_read_only(
					self.user_store.username, set(forceGroups) if forceGroups else None
				)

				logger.info(
					"Authentication successful for user '%s', groups '%s', "
					"admin group is '%s', admin: %s, readonly groups %s, readonly: %s",
					self.user_store.username,
					",".join(self.user_store.userGroups),
					auth_module.get_admin_groupname(),
					self.user_store.isAdmin,
					auth_module.get_read_only_groupnames(),
					self.user_store.isReadOnly,
				)
			else:
				raise BackendAuthenticationError(f"Invalid auth type {self.auth_type}")
		except Exception as err:
			logger.debug(err, exc_info=True)
			raise BackendAuthenticationError(
				f"{err} (auth_type={self.auth_type})"
			) from err

	def accessControl_authenticated(self):
		return self.user_store.authenticated

	def accessControl_userIsAdmin(self):
		return self.user_store.isAdmin

	def accessControl_userIsReadOnlyUser(self):
		return self.user_store.isReadOnly

	def accessControl_getUserGroups(self):
		return self.user_store.userGroups

	def __loadACLFile(self):
		try:
			if not self._aclFile:
				raise BackendConfigurationError("No acl file defined")

			self._acl = _readACLFile(self._aclFile)
			logger.debug("Read acl from file %s: %s", self._aclFile, self._acl)
		except Exception as err:
			logger.error(err, exc_info=True)
			raise BackendConfigurationError(
				f"Failed to load acl file '{self._aclFile}': {err}"
			) from err

	def _createInstanceMethods(self):
		protectedMethods = set()
		for Class in (
			ExtendedConfigDataBackend,
			ConfigDataBackend,
			DepotserverBackend,
			HostControlBackend,
			HostControlSafeBackend,
		):
			methodnames = (
				name
				for name, _ in inspect.getmembers(Class, inspect.isfunction)
				if not name.startswith("_")
			)
			for methodName in methodnames:
				protectedMethods.add(methodName)

		for methodName, functionRef in inspect.getmembers(
			self._backend, inspect.ismethod
		):
			if getattr(functionRef, "no_export", False):
				continue
			if methodName.startswith("_"):
				# Not a public method
				continue

			sig, arg = get_function_signature_and_args(functionRef)
			sig = "(self)" if sig == "()" else f"(self, {sig[1:]}"
			exec_locals: dict[str, object] = {}
			if methodName in protectedMethods:
				logger.trace("Protecting method '%s'", methodName)
				exec(  # pylint: disable=exec-used
					f'def {methodName}{sig}: return self._executeMethodProtected("{methodName}", {arg})',
					locals=exec_locals,
				)
			else:
				logger.trace("Not protecting method '%s'", methodName)
				exec(  # pylint: disable=exec-used
					f'def {methodName}{sig}: return self._executeMethod("{methodName}", {arg})',
					locals=exec_locals,
				)

			new_function = exec_locals[methodName]
			if getattr(functionRef, "deprecated", False):
				new_function.deprecated = functionRef.deprecated
			if getattr(functionRef, "alternative_method", None):
				new_function.alternative_method = functionRef.alternative_method
			if functionRef.__doc__:
				new_function.__doc__ = functionRef.__doc__
			setattr(self, methodName, types.MethodType(new_function, self))

	def _isMemberOfGroup(self, ids):
		for groupId in forceUnicodeLowerList(ids):
			if groupId in self.user_store.userGroups:
				return True
		return False

	def _isUser(self, ids):
		return self.user_store.username in forceUnicodeLowerList(ids)

	def _isOpsiDepotserver(self, ids=None):
		if not self.user_store.host or not isinstance(
			self.user_store.host, OpsiDepotserver
		):
			return False
		if not ids:
			return True

		for hostId in forceUnicodeLowerList(ids or []):
			if hostId == self.user_store.host.id:
				return True
		return False

	def _isOpsiClient(self, ids=None):
		if not self.user_store.host or not isinstance(self.user_store.host, OpsiClient):
			return False

		if not ids:
			return True

		return forceBool(self.user_store.host.id in forceUnicodeLowerList(ids or []))

	def _isSelf(self, **params):
		if not params:
			return False
		for param, value in params.items():
			if issubclass(value, Object) and value.id == self.user_store.username:
				return True
			if param in (
				"id",
				"objectId",
				"hostId",
				"clientId",
				"serverId",
				"depotId",
			) and (value == self.user_store.username):
				return True
		return False

	def _executeMethod(self, methodName, **kwargs):
		meth = getattr(self._backend, methodName)
		return meth(**kwargs)

	def _executeMethodProtected(self, methodName, **kwargs):  # pylint: disable=too-many-branches,too-many-statements
		granted = False
		newKwargs = {}
		acls = []
		logger.debug("Access control for method %s with params %s", methodName, kwargs)
		for regex, acl in self._acl:
			logger.trace(
				"Testing if ACL pattern %s matches method %s", regex.pattern, methodName
			)  # pylint: disable=no-member
			if not regex.search(methodName):  # pylint: disable=no-member
				logger.trace("No match -> skipping.")
				continue

			logger.debug("Found matching acl for method %s: %s", acl, methodName)
			for entry in acl:
				aclType = entry.get("type")
				ids = entry.get("ids", [])
				newGranted = False
				if aclType == "all":
					newGranted = True
				elif aclType == "opsi_depotserver":
					newGranted = self._isOpsiDepotserver(ids)
				elif aclType == "opsi_client":
					newGranted = self._isOpsiClient(ids)
				elif aclType == "sys_group":
					newGranted = self._isMemberOfGroup(ids)
				elif aclType == "sys_user":
					newGranted = self._isUser(ids)
				elif aclType == "self":
					newGranted = "partial_object"
				else:
					logger.error("Unhandled acl entry type: %s", aclType)
					continue

				if newGranted is False:
					continue

				if entry.get("denyAttributes") or entry.get("allowAttributes"):
					newGranted = "partial_attributes"

				if newGranted:
					acls.append(entry)
					granted = newGranted

				if granted is True:
					break
			break

		logger.debug("Method %s using acls: %s", methodName, acls)
		if granted is True:
			logger.debug(
				"Full access to method %s granted to user %s by acl %s",
				methodName,
				self.user_store.username,
				acls[0],
			)
			newKwargs = kwargs
		elif granted is False:
			raise BackendPermissionDeniedError(
				f"Access to method '{methodName}' denied for user '{self.user_store.username}'"
			)
		else:
			logger.debug(
				"Partial access to method %s granted to user %s by acls %s",
				methodName,
				self.user_store.username,
				acls,
			)
			try:
				newKwargs = self._filterParams(kwargs, acls)
				if not newKwargs:
					raise BackendPermissionDeniedError("No allowed param supplied")
			except Exception as err:
				logger.info(err, exc_info=True)
				raise BackendPermissionDeniedError(
					f"Access to method '{methodName}' denied for user '{self.user_store.username}': {err}"
				) from err

		if methodName == "backend_getLicensingInfo" and not self.user_store.isAdmin:
			if (
				newKwargs.get("licenses")
				or newKwargs.get("legacy_modules")
				or newKwargs.get("dates")
			):
				raise BackendPermissionDeniedError(
					f"Access to method '{methodName}' with params {newKwargs} denied for user '{self.user_store.username}'"
				)

		logger.trace("newKwargs: %s", newKwargs)

		meth = getattr(self._backend, methodName)
		result = meth(**newKwargs)

		if granted is True:
			return result

		return self._filterResult(result, acls)

	def _filterParams(self, params, acls):
		logger.debug("Filtering params: %s", params)
		for key, value in tuple(params.items()):
			valueList = forceList(value)
			if not valueList:
				continue

			if issubclass(valueList[0].__class__, BaseObject) or isinstance(
				valueList[0], dict
			):
				valueList = self._filterObjects(
					valueList, acls, exceptionOnTruncate=False
				)
				if isinstance(value, list):
					params[key] = valueList
				else:
					if valueList:
						params[key] = valueList[0]
					else:
						del params[key]
		return params

	def _filterResult(self, result, acls):
		if result:
			resultList = forceList(result)
			if issubclass(resultList[0].__class__, BaseObject) or isinstance(
				resultList[0], dict
			):
				return self._filterObjects(
					result, acls, exceptionOnTruncate=False, exceptionIfAllRemoved=False
				)
		return result

	def _filterObjects(
		self, objects, acls, exceptionOnTruncate=True, exceptionIfAllRemoved=True
	):  # pylint: disable=too-many-branches,too-many-locals
		logger.info("Filtering objects by acls")
		is_list = type(objects) in (tuple, list)
		newObjects = []
		for obj in forceList(objects):
			isDict = isinstance(obj, dict)
			if isDict:
				objHash = obj
			else:
				objHash = obj.toHash()

			allowedAttributes = set()
			for acl in acls:
				if acl.get("type") == "self":
					objectId = None
					for identifier in (
						"id",
						"objectId",
						"hostId",
						"clientId",
						"depotId",
						"serverId",
					):
						try:
							objectId = objHash[identifier]
							break
						except KeyError:
							pass

					if not objectId or objectId != self.user_store.username:
						continue

				if acl.get("allowAttributes"):
					attributesToAdd = acl["allowAttributes"]
				elif acl.get("denyAttributes"):
					attributesToAdd = (
						attribute
						for attribute in objHash
						if attribute not in acl["denyAttributes"]
					)
				else:
					attributesToAdd = list(objHash.keys())

				for attribute in attributesToAdd:
					allowedAttributes.add(attribute)

			if not allowedAttributes:
				continue

			if not isDict:
				allowedAttributes.add("type")

				for attribute in mandatoryConstructorArgs(obj.__class__):
					allowedAttributes.add(attribute)

			keysToDelete = set()
			for key in objHash.keys():
				if key not in allowedAttributes:
					if exceptionOnTruncate:
						raise BackendPermissionDeniedError(
							f"Access to attribute '{key}' denied"
						)
					keysToDelete.add(key)

			for key in keysToDelete:
				del objHash[key]

			if isDict:
				newObjects.append(objHash)
			else:
				newObjects.append(obj.__class__.fromHash(objHash))

		orilen = len(objects) if is_list else 1
		newlen = len(newObjects)
		if newlen < orilen:
			logger.warning(
				"%s objects removed by acl, %s objects left", (orilen - newlen), newlen
			)
			if newlen == 0 and exceptionIfAllRemoved:
				raise BackendPermissionDeniedError("Access denied")

		return newObjects if is_list else newObjects[0]


@lru_cache(maxsize=None)
def _readACLFile(path):
	if not os.path.exists(path):
		raise BackendIOError(f"Acl file '{path}' not found")

	return BackendACLFile(path).parse()
