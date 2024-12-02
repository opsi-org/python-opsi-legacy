# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Basic backend.

This holds the basic backend classes.
"""

from __future__ import absolute_import

import base64
import codecs
import inspect
import os
import re
import time
from hashlib import md5
from textwrap import dedent
from typing import Union

# pyright: reportMissingImports=false
try:
	# PyCryptodome from pypi installs into Crypto
	from Crypto.Hash import MD5
	from Crypto.Signature import pkcs1_15
except (ImportError, OSError):
	# python3-pycryptodome installs into Cryptodome
	from Cryptodome.Hash import MD5
	from Cryptodome.Signature import pkcs1_15

from opsicommon.logging import get_logger

from OPSI import __version__ as LIBRARY_VERSION
from OPSI.Exceptions import BackendError
from OPSI.Object import *  # this is needed for dynamic loading # noqa: F401,F403
from OPSI.Types import (
	forceDict,
	forceFilename,
	forceList,
	forceUnicode,
	forceUnicodeList,
)
from OPSI.Util import compareVersions, getPublicKey

__all__ = ("describeInterface", "Backend")

OPSI_MODULES_FILE = "/etc/opsi/modules"
OPSI_LICENSE_PATH = "/etc/opsi/licenses"


logger = get_logger("opsi.general")


def describeInterface(instance):
	"""
	Describes what public methods are available and the signatures they use.

	These methods are represented as a dict with the following keys: \
	*name*, *params*, *args*, *varargs*, *keywords*, *defaults*.

	:rtype: [{},]
	"""
	methods = {}
	for _, function in inspect.getmembers(instance, inspect.ismethod):
		methodName = function.__name__
		if getattr(function, "no_export", False):
			continue
		if methodName.startswith("_"):
			# protected / private
			continue

		spec = inspect.getfullargspec(function)
		sig = inspect.signature(function)
		args = spec.args
		defaults = spec.defaults
		params = [arg for arg in args if arg != "self"]
		annotations_ = {}
		for param in params:
			str_param = str(sig.parameters[param])
			if ": " in str_param:
				annotations_[param] = str_param.split(": ", 1)[1].split(" = ", 1)[0]

		if defaults is not None:
			offset = len(params) - len(defaults)
			for i in range(len(defaults)):
				index = offset + i
				params[index] = f"*{params[index]}"

		for index, element in enumerate((spec.varargs, spec.varkw), start=1):
			if element:
				stars = "*" * index
				params.extend([f"{stars}{arg}" for arg in forceList(element)])

		logger.trace(
			"%s interface method: name %s, params %s",
			instance.__class__.__name__,
			methodName,
			params,
		)
		doc = function.__doc__
		if doc:
			doc = dedent(doc).lstrip() or None

		methods[methodName] = {
			"name": methodName,
			"params": params,
			"args": args,
			"varargs": spec.varargs,
			"keywords": spec.varkw,
			"defaults": defaults,
			"deprecated": getattr(function, "deprecated", False),
			"alternative_method": getattr(function, "alternative_method", None),
			"doc": doc,
			"annotations": annotations_,
		}

	return [methods[name] for name in sorted(list(methods.keys()))]


class BackendOptions:
	"""
	A class used to combine option defaults and changed options
	"""

	def __init__(
		self, option_defaults: dict, option_store: Union[dict, callable] = None
	):
		"""
		:param option_defaults: The default option items as dict
		:param options_store: A dict or a callable to retrieve a dict to store changed options
		"""
		self._option_defaults = option_defaults
		self._option_store = option_store or {}

	@property
	def option_store(self):
		if callable(self._option_store):
			return self._option_store()
		return self._option_store

	@option_store.setter
	def option_store(self, option_store):
		self._option_store = option_store

	def __setitem__(self, item, value):
		self.option_store[item] = value

	def __getitem__(self, item):
		if item in self.option_store:
			return self.option_store[item]
		return self._option_defaults[item]

	def __contains__(self, item):
		return item in self._option_defaults

	def keys(self):
		return list(self._option_defaults.keys())

	def items(self):
		items = dict(self._option_defaults)
		items.update(self.option_store)
		return items.items()

	def copy(self):
		return dict(self.items())


class Backend:
	"""
	Base backend.
	"""

	matchCache = {}
	option_defaults = {}

	def __init__(self, **kwargs):
		"""
		Constructor that only accepts keyword arguments.

		:param name: Name of the backend
		:param username: Username to use (if required)
		:param password: Password to use (if required)
		:param context: Context backend. Calling backend methods from \
other backend methods is done by using the context backend. \
This defaults to ``self``.
		"""
		self._name = None
		self._username = None
		self._password = None
		self._context = self
		self._opsiVersion = LIBRARY_VERSION
		self._opsiModulesFile = OPSI_MODULES_FILE
		self._opsi_license_path = OPSI_LICENSE_PATH
		option_store = {}

		for option, value in kwargs.items():
			option = option.lower()
			if option == "name":
				self._name = value
			elif option == "username":
				self._username = value
			elif option == "password":
				self._password = value
			elif option == "context":
				self._context = value
				logger.info("Backend context was set to %s", self._context)
			elif option == "opsimodulesfile":
				self._opsiModulesFile = forceFilename(value)
			elif option in ("option_store", "optionstore"):
				option_store = value

		self._options = BackendOptions(self.option_defaults, option_store)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.backend_exit()

	def _init_backend(self, config_data_backend):
		"""
		Init backend
		"""

	def _setContext(self, context):
		"""Setting the context backend."""
		self._context = context

	def _getContext(self):
		"""Getting the context backend."""
		return self._context

	def _objectHashMatches(self, objHash, **filter):
		"""
		Checks if the opsi object hash matches the filter.

		:rtype: bool
		"""
		for attribute, value in objHash.items():
			if not filter.get(attribute):
				continue
			matched = False

			try:
				logger.debug(
					"Testing match of filter %s of attribute %s with value %s",
					filter[attribute],
					attribute,
					value,
				)
				filterValues = forceUnicodeList(filter[attribute])
				if (
					forceUnicodeList(value) == filterValues
					or forceUnicode(value) in filterValues
				):
					matched = True
				else:
					for filterValue in filterValues:
						if attribute == "type":
							match = False
							Class = eval(filterValue)
							for subClass in Class.subClasses:
								if subClass == value:
									matched = True
									break

							continue

						if isinstance(value, list):
							if filterValue in value:
								matched = True
								break
							continue

						if value is None or isinstance(value, bool):
							continue

						if isinstance(value, (float, int)) or re.search(
							r"^\s*([>=<]+)\s*([\d.]+)", forceUnicode(filterValue)
						):
							operator = "=="
							val = forceUnicode(filterValue)
							match = re.search(r"^\s*([>=<]+)\s*([\d.]+)", filterValue)
							if match:
								operator = match.group(1)
								val = match.group(2)

							try:
								matched = compareVersions(value, operator, val)
								if matched:
									break
							except Exception:
								pass

							continue

						if "*" in filterValue and re.search(
							f"^{filterValue.replace('*', '.*')}$", value
						):
							matched = True
							break

				if matched:
					logger.debug(
						"Value %s matched filter %s, attribute %s",
						value,
						filter[attribute],
						attribute,
					)
				else:
					# No match, we can stop further checks.
					return False
			except Exception as err:
				raise BackendError(
					f"Testing match of filter {filter[attribute]} of attribute '{attribute}' "
					f"with value {value} failed: {err}"
				) from err

		return True

	def backend_setOptions(self, options):
		"""
		Change the behaviour of the backend.

		:param options: The options to set. Unknown keywords will be ignored.
		:type options: dict
		"""
		options = forceDict(options)
		for key, value in options.items():
			if key not in self._options:
				continue

			if not isinstance(value, self._options[key].__class__):
				logger.debug(
					"Wrong type %s for option %s, expecting type %s",
					type(value),
					key,
					type(self._options[key]),
				)
				continue

			self._options[key] = value

	def backend_getOptions(self):
		"""
		Get the current backend options.

		:rtype: dict
		"""
		return self._options.copy()

	def backend_getInterface(self):
		"""
		Returns what public methods are available and the signatures they use.

		These methods are represented as a dict with the following keys: \
		*name*, *params*, *args*, *varargs*, *keywords*, *defaults*.


		:rtype: [{},]
		"""
		return describeInterface(self)

	def backend_info(self):
		"""
		Get info about the used opsi version and the licensed modules.

		:rtype: dict
		"""
		modules = {"valid": False}
		helpermodules = {}

		if os.path.exists(self._opsiModulesFile):
			try:
				with codecs.open(self._opsiModulesFile, "r", "utf-8") as modulesFile:
					for line in modulesFile:
						line = line.strip()
						if "=" not in line:
							logger.error(
								"Found bad line '%s' in modules file '%s'",
								line,
								self._opsiModulesFile,
							)
							continue
						(module, state) = line.split("=", 1)
						module = module.strip().lower()
						state = state.strip()
						if module in ("signature", "customer", "expires"):
							modules[module] = state
							continue
						state = state.lower()
						if state not in ("yes", "no"):
							try:
								helpermodules[module] = state
								state = int(state)
							except ValueError:
								logger.error(
									"Found bad line '%s' in modules file '%s'",
									line,
									self._opsiModulesFile,
								)
								continue
						if isinstance(state, int):
							modules[module] = state > 0
						else:
							modules[module] = state == "yes"

				if not modules.get("signature"):
					modules = {"valid": False}
					raise ValueError("Signature not found")
				if not modules.get("customer"):
					modules = {"valid": False}
					raise ValueError("Customer not found")
				if (
					modules.get("expires", "") != "never"
					and time.mktime(
						time.strptime(modules.get("expires", "2000-01-01"), "%Y-%m-%d")
					)
					- time.time()
					<= 0
				):
					modules = {"valid": False}
					raise ValueError("Signature expired")

				publicKey = getPublicKey(
					data=base64.decodebytes(
						b"AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDo"
						b"jY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8"
						b"S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDU"
						b"lk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP"
					)
				)
				data = ""
				mks = list(modules.keys())
				mks.sort()
				for module in mks:
					if module in ("valid", "signature"):
						continue
					if module in helpermodules:
						val = helpermodules[module]
					else:
						val = modules[module]
						if isinstance(val, bool):
							val = "yes" if val else "no"
					data += f"{module.lower().strip()} = {val}\r\n"

				modules["valid"] = False
				if modules["signature"].startswith("{"):
					s_bytes = int(modules["signature"].split("}", 1)[-1]).to_bytes(
						256, "big"
					)
					try:
						pkcs1_15.new(publicKey).verify(MD5.new(data.encode()), s_bytes)
						modules["valid"] = True
					except ValueError:
						# Invalid signature
						pass
				else:
					h_int = int.from_bytes(md5(data.encode()).digest(), "big")
					s_int = publicKey._encrypt(int(modules["signature"]))
					modules["valid"] = h_int == s_int

			except Exception as err:
				logger.error(
					"Failed to read opsi modules file '%s': %s",
					self._opsiModulesFile,
					err,
				)
		else:
			logger.info("Opsi modules file '%s' not found", self._opsiModulesFile)

		return {
			"opsiVersion": self._opsiVersion,
			"modules": modules,
			"realmodules": helpermodules,
		}

	def backend_exit(self):
		"""
		Exit the backend.

		This method should be used to close connections or clean up \
		used resources.
		"""

	def __repr__(self):
		if self._name:
			return f"<{self.__class__.__name__}(name='{self._name}')>"
		return f"<{self.__class__.__name__}()>"
