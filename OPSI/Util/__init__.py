# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
General utility functions.

This module holds various utility functions for the work with opsi.
This includes functions for (de)serialisation, converting classes from
or to JSON, working with librsync and more.
"""

import base64
import binascii
import codecs
import ipaddress
import json
import os
import random
import re
import shutil
import socket
import struct
import sys
from collections import namedtuple
from functools import lru_cache
from hashlib import md5
from itertools import islice

# pyright: reportMissingImports=false
try:
	# PyCryptodome from pypi installs into Crypto
	from Crypto.Cipher import Blowfish
	from Crypto.PublicKey import RSA
	from Crypto.Util.number import bytes_to_long
except (ImportError, OSError):
	# python3-pycryptodome installs into Cryptodome
	from Cryptodome.Cipher import Blowfish
	from Cryptodome.PublicKey import RSA
	from Cryptodome.Util.number import bytes_to_long

from opsicommon.logging import get_logger
from opsicommon.objects import deserialize as oc_deserialize
from opsicommon.objects import from_json, serialize, to_json
from opsicommon.types import (  # noqa: F401
	_PACKAGE_VERSION_REGEX,
	_PRODUCT_VERSION_REGEX,
	forceBool,
	forceFilename,
	forceFqdn,
	forceUnicode,
)
from opsicommon.utils import (
	Singleton,
	compare_versions,
	monkeypatch_subprocess_for_frozen,  # pylint: disable=unused-import  # noqa: F401
)
from opsicommon.utils import generate_opsi_host_key as generateOpsiHostKey
from opsicommon.utils import timestamp as oc_timestamp

__all__ = (
	"BLOWFISH_IV",
	"RANDOM_DEVICE",
	"UNIT_REGEX",
	"CryptoError",
	"BlowfishError",
	"PickleString",
	"blowfishDecrypt",
	"blowfishEncrypt",
	"chunk",
	"compareVersions",
	"deserialize",
	"findFiles",
	"findFilesGenerator",
	"formatFileSize",
	"fromJson",
	"generateOpsiHostKey",
	"getfqdn",
	"ipAddressInNetwork",
	"isRegularExpressionPattern",
	"md5sum",
	"objectToBash",
	"objectToBeautifiedText",
	"objectToHtml",
	"randomString",
	"removeDirectory",
	"removeUnit",
	"replaceSpecialHTMLCharacters",
	"serialize",
	"timestamp",
	"toJson",
	"getPublicKey",
	"Singleton",
)

BLOWFISH_IV = b"OPSI1234"
RANDOM_DEVICE = "/dev/urandom"
UNIT_REGEX = re.compile(r"^(\d+\.*\d*)\s*(\w{0,4})$")
_ACCEPTED_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

logger = get_logger("opsi.general")
Version = namedtuple("Version", "product package")


class CryptoError(ValueError):
	pass


class BlowfishError(CryptoError):
	pass


class PickleString(str):
	def __getstate__(self):
		return base64.standard_b64encode(self)

	def __setstate__(self, state):
		self = base64.standard_b64decode(state)  # pylint: disable=self-cls-assignment  # noqa: F841


def formatFileSize(sizeInBytes, base: int = 2):  # pylint: disable=too-many-return-statements
	"""
	https://wiki.ubuntu.com/UnitsPolicy

	Correct basis

	Use base-10 for:
		* network bandwidth (for example, 6 Mbit/s or 50 kB/s)
		* disk sizes (for example, 500 GB hard drive or 4.7 GB DVD)

	Use base-2 for:
		* RAM sizes (for example, 2 GiB RAM)

	For file sizes there are two possibilities:
		* Show both, base-10 and base-2 (in this order). An example is the Linux kernel:
			"2930277168 512-byte hardware sectors: (1.50 TB/1.36 TiB)"
		* Only show base-10, or give the user the opportunity to decide between base-10 and base-2 (the default must be base-10).
	"""
	if base == 10:
		if sizeInBytes < 1_000:
			return f"{sizeInBytes:0.0f}B"
		if sizeInBytes < 1_000_000:
			return f"{sizeInBytes / 1000:0.0f}kB"
		if sizeInBytes < 1_000_000_000:
			return f"{sizeInBytes / 1_000_000:0.0f}MB"
		if sizeInBytes < 1_000_000_000_000:
			return f"{sizeInBytes / 1_000_000_000:0.0f}GB"
		return f"{sizeInBytes / 1_000_000_000_000:0.0f}TB"

	if sizeInBytes < 1_024:
		return f"{sizeInBytes:0.0f}B"
	if sizeInBytes < 1_048_576:  # 1024**2
		return f"{sizeInBytes / 1024:0.0f}KiB"
	if sizeInBytes < 107_374_1824:  # 1024**3
		return f"{sizeInBytes / 1048576:0.0f}MiB"
	if sizeInBytes < 1_099_511_627_776:  # 1024**4
		return f"{sizeInBytes / 1_073_741_824:0.0f}GiB"
	return f"{sizeInBytes / 1_099_511_627_776:0.0f}TiB"


def md5sum(filename):
	"""Returns the md5sum of the given file."""
	md5object = md5()

	with open(filename, "rb") as fileToHash:
		for data in iter(lambda: fileToHash.read(524288), b""):
			md5object.update(data)

	return md5object.hexdigest()


def randomString(length, characters=_ACCEPTED_CHARACTERS):
	"""
	Generates a random string for a given length.

	:param characters: The characters to choose from. This defaults to 0-9a-Z.
	"""
	return "".join(random.choice(characters) for _ in range(length))


def timestamp(secs=0, dateOnly=False):
	"""Returns a timestamp of the current system time format: YYYY-mm-dd[ HH:MM:SS]"""
	return oc_timestamp(secs=secs, date_only=dateOnly)


def fromJson(obj, objectType=None, preventObjectCreation=False):
	return from_json(
		obj, object_type=objectType, prevent_object_creation=preventObjectCreation
	)


def toJson(obj):
	return to_json(obj, deep=True)


def deserialize(obj, preventObjectCreation=False):
	return oc_deserialize(obj, prevent_object_creation=preventObjectCreation)


def objectToBeautifiedText(obj):
	return json.dumps(serialize(obj), indent=4)


def objectToBash(obj, bashVars=None, level=0):  # pylint: disable=too-many-branches
	"""
	Converts `obj` into bash-compatible format.

	:type bashVars: dict
	:type level: int
	:rtype: dict
	"""
	if bashVars is None:
		bashVars = {}

	if level == 0:
		obj = serialize(obj)
		varName = "RESULT"
		compress = True
	else:
		varName = f"RESULT{level}"
		compress = False

	try:
		obj = obj.serialize()
	except AttributeError:
		pass

	try:
		append = bashVars[varName].append
	except KeyError:
		emptyList = []
		bashVars[varName] = emptyList
		append = emptyList.append

	if isinstance(obj, (list, set)):
		append("(\n")
		for element in obj:
			if isinstance(element, (dict, list)):
				level += 1
				objectToBash(element, bashVars, level)
				append(f"RESULT{level}=${{RESULT{level}[*]}}")
			else:
				objectToBash(element, bashVars, level)
			append("\n")
		append(")")
	elif isinstance(obj, dict):
		append("(\n")
		for key, value in obj.items():
			append(f"{key}=")
			if isinstance(value, (dict, list)):
				level += 1
				objectToBash(value, bashVars, level)
				append(f"${{RESULT{level}[*]}}")
			else:
				objectToBash(value, bashVars, level)
			append("\n")
		append(")")
	elif obj is None:
		append('""')
	else:
		append(f'"{obj}"')

	if compress:
		for key, value in bashVars.items():
			bashVars[key] = "".join(value)

	return bashVars


def objectToHtml(obj, level=0):  # pylint: disable=too-many-branches
	if level == 0:
		obj = serialize(obj)

	html = []
	append = html.append

	if isinstance(obj, (list, set)):
		append("[")
		if len(obj) > 0:
			append('<div style="padding-left: 3em;">')
			for i, currentElement in enumerate(obj):
				append(objectToHtml(currentElement, level + 1))
				if i < len(obj) - 1:
					append(",<br />\n")
			append("</div>")
		append("]")
	elif isinstance(obj, dict):
		append("{")
		if len(obj) > 0:
			append('<div style="padding-left: 3em;">')
			for i, (key, value) in enumerate(obj.items()):
				append('<font class="json_key">')
				append(objectToHtml(key))
				append("</font>: ")
				append(objectToHtml(value, level + 1))
				if i < len(obj) - 1:
					append(",<br />\n")
			append("</div>")
		append("}")
	elif isinstance(obj, bool):
		append(str(obj).lower())
	elif obj is None:
		append("null")
	else:
		if isinstance(obj, str):
			append(replaceSpecialHTMLCharacters(obj).join(('"', '"')))
		else:
			append(replaceSpecialHTMLCharacters(obj))

	return "".join(html)


def replaceSpecialHTMLCharacters(text):
	return (
		str(text)
		.replace("\r", "")
		.replace("\t", "   ")
		.replace("&", "&amp;")
		.replace('"', "&quot;")
		.replace("'", "&apos;")
		.replace(" ", "&nbsp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace("\n", "<br />\n")
	)


compareVersions = compare_versions


def removeUnit(value: str) -> int:  # pylint: disable=invalid-name,too-many-return-statements
	"""
	Take a string representing a byte-based size and return the
	value in bytes.

	:param value: str
	:returns: `value` in bytes.
	:rtype: int or float
	"""
	value = str(value)
	match = UNIT_REGEX.search(value)
	if not match:
		return value

	if "." in match.group(1):
		value = float(match.group(1))
	else:
		value = int(match.group(1))

	unit = match.group(2)
	mult = 1000

	if unit.lower().endswith("hz"):
		unit = unit[:-2]
	elif unit.lower().endswith("bits"):
		mult = 1024
		unit = unit[:-4]
	elif unit.lower().endswith("b"):
		mult = 1024
		unit = unit[:-1]
	elif unit.lower().endswith(("s", "v")):
		unit = unit[:-1]

	if unit.endswith("n"):
		return float(value) / (mult * mult)
	if unit.endswith("m"):
		return float(value) / mult
	if unit.lower().endswith("k"):
		return value * mult
	if unit.endswith("M"):
		return value * mult * mult
	if unit.endswith("G"):
		return value * mult * mult * mult

	return value


def blowfishEncrypt(key, cleartext):
	"""
	Takes `cleartext` string, returns hex-encoded,
	blowfish-encrypted string.

	:type key: str
	:type cleartext: str
	:raises BlowfishError: In case things go wrong.
	:rtype: str
	"""
	if not key:
		raise BlowfishError("Missing key")

	key = _prepareBlowfishKey(key)
	cleartext = forceUnicode(cleartext)
	cleartext = cleartext.encode("utf-8")
	while len(cleartext) % 8 != 0:
		# Fill up with \0 until length is a mutiple of 8
		cleartext += b"\x00"

	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	try:
		crypt = blowfish.encrypt(cleartext)
	except Exception as err:
		logger.debug(err, exc_info=True)
		raise BlowfishError("Failed to encrypt") from err

	return crypt.hex()


def blowfishDecrypt(key, crypt):
	"""
	Takes hex-encoded, blowfish-encrypted string,
	returns cleartext string.

	:type key: str
	:param crypt: The encrypted text as hex.
	:type crypt: str
	:raises BlowfishError: In case things go wrong.
	:rtype: str
	"""
	if not key:
		raise BlowfishError("Missing key")

	key = _prepareBlowfishKey(key)
	crypt = bytes.fromhex(crypt)

	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	try:
		cleartext = blowfish.decrypt(crypt)
	except Exception as err:
		logger.debug(err, exc_info=True)
		raise BlowfishError("Failed to decrypt") from err

	# Remove possible \0-chars
	cleartext = cleartext.rstrip(b"\0")

	try:
		return cleartext.decode("utf-8")
	except Exception as err:
		logger.error(err)
		raise BlowfishError("Failed to convert decrypted text to unicode.") from err


def _prepareBlowfishKey(key: str) -> bytes:
	"Transform the key into hex."
	try:
		key = forceUnicode(key).encode()
		return codecs.decode(key, "hex")
	except (binascii.Error, Exception) as err:
		raise BlowfishError(f"Unable to prepare key: {err}") from err


def findFilesGenerator(  # pylint: disable=too-many-branches,too-many-locals,too-many-arguments,too-many-statements
	directory,
	prefix="",
	excludeDir=None,
	excludeFile=None,
	includeDir=None,
	includeFile=None,
	returnDirs=True,
	returnLinks=True,
	followLinks=False,
	repository=None,
):
	directory = forceFilename(directory)
	prefix = forceUnicode(prefix)

	if excludeDir:
		if not isRegularExpressionPattern(excludeDir):
			excludeDir = re.compile(forceUnicode(excludeDir))
	else:
		excludeDir = None

	if excludeFile:
		if not isRegularExpressionPattern(excludeFile):
			excludeFile = re.compile(forceUnicode(excludeFile))
	else:
		excludeFile = None

	if includeDir:
		if not isRegularExpressionPattern(includeDir):
			includeDir = re.compile(forceUnicode(includeDir))
	else:
		includeDir = None

	if includeFile:
		if not isRegularExpressionPattern(includeFile):
			includeFile = re.compile(forceUnicode(includeFile))
	else:
		includeFile = None

	returnDirs = forceBool(returnDirs)
	returnLinks = forceBool(returnLinks)
	followLinks = forceBool(followLinks)

	if repository:
		islink = repository.islink
		isdir = repository.isdir
		listdir = repository.listdir
	else:
		islink = os.path.islink
		isdir = os.path.isdir
		listdir = os.listdir

	for entry in listdir(directory):
		pp = os.path.join(prefix, entry)
		dp = os.path.join(directory, entry)
		isLink = False
		if islink(dp):
			isLink = True
			if not returnLinks and not followLinks:
				continue
		if isdir(dp) and (not isLink or followLinks):
			if excludeDir and re.search(excludeDir, entry):
				logger.debug("Excluding dir '%s' and containing files", entry)
				continue
			if includeDir:
				if not re.search(includeDir, entry):
					continue
				logger.debug("Including dir '%s' and containing files", entry)
			if returnDirs:
				yield pp
			yield from findFilesGenerator(
				directory=dp,
				prefix=pp,
				excludeDir=excludeDir,
				excludeFile=excludeFile,
				includeDir=includeDir,
				includeFile=includeFile,
				returnDirs=returnDirs,
				returnLinks=returnLinks,
				followLinks=followLinks,
				repository=repository,
			)
			continue

		if excludeFile and re.search(excludeFile, entry):
			if isLink:
				logger.debug("Excluding link '%s'", entry)
			else:
				logger.debug("Excluding file '%s'", entry)
			continue

		if includeFile:
			if not re.search(includeFile, entry):
				continue
			if isLink:
				logger.debug("Including link '%s'", entry)
			else:
				logger.debug("Including file '%s'", entry)
		yield pp


def findFiles(  # pylint: disable=too-many-arguments
	directory,
	prefix="",
	excludeDir=None,
	excludeFile=None,
	includeDir=None,
	includeFile=None,
	returnDirs=True,
	returnLinks=True,
	followLinks=False,
	repository=None,
):
	return list(
		findFilesGenerator(
			directory,
			prefix,
			excludeDir,
			excludeFile,
			includeDir,
			includeFile,
			returnDirs,
			returnLinks,
			followLinks,
			repository,
		)
	)


if sys.version_info >= (3, 7):

	def isRegularExpressionPattern(object):  # pylint: disable=redefined-builtin
		return isinstance(object, re.Pattern)

else:

	def isRegularExpressionPattern(object):  # pylint: disable=redefined-builtin
		return "SRE_Pattern" in str(type(object))


def ipAddressInNetwork(ipAddress, networkAddress):
	"""
	Checks if the given IP address is in the given network range.
	Returns ``True`` if the given address is part of the network.
	Returns ``False`` if the given address is not part of the network.

	:param ipAddress: The IP which we check.
	:type ipAddress: str
	:param networkAddress: The network address written with slash notation.
	:type networkAddress: str
	"""
	if not isinstance(ipAddress, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
		ipAddress = ipaddress.ip_address(ipAddress)
	if isinstance(ipAddress, ipaddress.IPv6Address) and ipAddress.ipv4_mapped:
		ipAddress = ipAddress.ipv4_mapped

	if not isinstance(networkAddress, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
		networkAddress = ipaddress.ip_network(networkAddress)

	return ipAddress in networkAddress


def getfqdn(name="", conf=None):
	"""
	Get the fqdn.

	If ``name`` is not given it will try various ways to get a valid
	fqdn from the current host.
	If ``conf`` but no name is given it will try to read the FQDN from
	the specified configuration file.
	"""
	if name:
		return forceFqdn(socket.getfqdn(name))

	host_id = os.environ.get("OPSI_HOST_ID") or os.environ.get("OPSI_HOSTNAME")
	if host_id:
		try:
			return forceFqdn(host_id)
		except ValueError:
			# Not a fqdn
			pass

	# lazy import to avoid circular dependency
	from OPSI.Util.Config import (
		getGlobalConfig,  # pylint: disable=import-outside-toplevel
	)

	if conf is not None:
		host_id = getGlobalConfig("hostname", conf)
	else:
		host_id = getGlobalConfig("hostname")

	if host_id:
		return forceFqdn(host_id)

	return forceFqdn(socket.getfqdn())


def removeDirectory(directory):
	"""
	Removing an directory.

	If this fails with shutil it will try to use system calls.

	.. versionadded:: 4.0.5.1


	:param directory: Path to the directory
	:tye directory: str
	"""
	logger.debug("Removing directory: %s", directory)
	try:
		shutil.rmtree(directory)
	except UnicodeDecodeError:
		# See http://bugs.python.org/issue3616
		logger.info(
			"Client data directory seems to contain filenames with unicode characters. Trying fallback."
		)

		# late import to avoid circular dependency
		import OPSI.System  # pylint: disable=import-outside-toplevel

		OPSI.System.execute("rm -rf {directory}")


def chunk(iterable, size):
	"""
	Returns chunks (parts) of a specified `size` from `iterable`.
	It will not pad (fill) the chunks.

	This works lazy and therefore can be used with any iterable without
	much overhead.

	Original recipe from http://stackoverflow.com/a/22045226
	"""
	it = iter(iterable)
	return iter(lambda: tuple(islice(it, size)), ())


@lru_cache(maxsize=4)
def getPublicKey(data):
	# Key type can be found in 4:11.
	rest = data[11:]
	count = 0
	mp = []
	for _ in range(2):
		length = struct.unpack(">L", rest[count : count + 4])[0]
		mp.append(bytes_to_long(rest[count + 4 : count + 4 + length]))
		count += 4 + length

	return RSA.construct((mp[1], mp[0]))
