#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
= = = = = = = = = = = = = = = = = = =
=   opsi python library - Util      =
= = = = = = = = = = = = = = = = = = =

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
@author: Erol Ueluekmen <e.ueluekmen@uib.de>
@license: GNU General Public License version 2
"""

__version__ = '4.0.4.3'

import base64
import codecs
import os
import random
import re
import socket
import struct
import time
import types
from Crypto.Cipher import Blowfish
from sys import version_info

if (version_info >= (2, 6)):
	import json
else:
	import simplejson as json

try:
	from hashlib import md5
except ImportError:
	from md5 import md5

try:
	import argparse
except ImportError:
	import _argparse as argparse

from OPSI.Logger import Logger
from OPSI.Types import (forceBool, forceFilename, forceFqdn, forceInt,
						forceIPAddress, forceNetworkAddress, forceUnicode)

logger = Logger()

if (os.name == 'posix'):
	from duplicity import librsync
elif (os.name == 'nt'):
	try:
		import librsync
	except Exception, e:
		logger.error(u"Failed to import librsync: %s" % e)

BLOWFISH_IV = 'OPSI1234'
OPSI_GLOBAL_CONF = u'/etc/opsi/global.conf'
RANDOM_DEVICE = u'/dev/urandom'


class PickleString(str):

	def __getstate__(self):
		return base64.standard_b64encode(self)

	def __setstate__(self, state):
		self = base64.standard_b64decode(state)


def deserialize(obj, preventObjectCreation=False):
	newObj = None
	if not preventObjectCreation and type(obj) is dict and obj.has_key('type'):
		try:
			import OPSI.Object
			c = eval('OPSI.Object.%s' % obj['type'])
			newObj = c.fromHash(obj)
		except Exception, e:
			logger.debug(u"Failed to get object from dict '%s': %s" % (obj, forceUnicode(e)))
			return obj
	elif type(obj) is list:
		newObj = []
		for o in obj:
			newObj.append(deserialize(o, preventObjectCreation = preventObjectCreation))
	elif type(obj) is dict:
		newObj = {}
		for (k, v) in obj.items():
			newObj[k] = deserialize(v, preventObjectCreation = preventObjectCreation)
	else:
		return obj
	return newObj


def serialize(obj):
	newObj = None
	if type(obj) in (unicode, str):
		return obj
	elif hasattr(obj, 'serialize'):
		newObj = obj.serialize()
	elif type(obj) is list:
		newObj = []
		for o in obj:
			newObj.append(serialize(o))
	elif type(obj) is dict:
		newObj = {}
		for (k, v) in obj.items():
			newObj[k] = serialize(v)
	else:
		return obj
	return newObj


def formatFileSize(sizeInBytes):
	if sizeInBytes < 1024:
		return '%i' % sizeInBytes
	elif sizeInBytes < (1024**2):
		return '%iK' % (sizeInBytes / 1024)
	elif sizeInBytes < (1024**3):
		return '%iM' % (sizeInBytes / (1024**2))
	else:
		return '%iG' % (sizeInBytes / (1024**3))


def fromJson(obj, objectType=None, preventObjectCreation=False):
	obj = json.loads(obj)
	if type(obj) is dict and objectType:
		obj['type'] = objectType
	return deserialize(obj, preventObjectCreation = preventObjectCreation)


def toJson(obj, ensureAscii=False):
	return json.dumps(serialize(obj), ensure_ascii = ensureAscii)


def librsyncSignature(filename, base64Encoded = True):
	#if (os.name != 'posix'):
	#	raise NotImplementedError(u"Not implemented for non-posix os")

	(f, sf) = (None, None)
	try:
		f = open(filename, 'rb')
		sf = librsync.SigFile(f)
		if base64Encoded:
			sig = base64.encodestring(sf.read())
		else:
			sig = sf.read()
		f.close()
		sf.close()
		return sig
	except Exception, e:
		if f: f.close()
		if sf: sf.close()
		raise Exception(u"Failed to get librsync signature: %s" % forceUnicode(e))


def librsyncPatchFile(oldfile, deltafile, newfile):
	logger.debug(u"Librsync : %s, %s, %s" % (oldfile, deltafile, newfile))
	if (oldfile == newfile):
		raise ValueError(u"Oldfile and newfile are the same file")
	if (deltafile == newfile):
		raise ValueError(u"deltafile and newfile are the same file")
	if (deltafile == oldfile):
		raise ValueError(u"oldfile and deltafile are the same file")

	(of, df, nf, pf) = (None, None, None, None)
	bufsize = 1024*1024
	try:
		of = open(oldfile, "rb")
		df = open(deltafile, "rb")
		nf = open(newfile, "wb")
		pf = librsync.PatchedFile(of, df)
		data = True
		while(data):
			data = pf.read(bufsize)
			nf.write(data)
		nf.close()
		pf.close()
		df.close()
		of.close()
	except Exception, e:
		if nf: nf.close()
		if pf: pf.close()
		if df: df.close()
		if of: of.close()
		raise Exception(u"Failed to patch file: %s" % forceUnicode(e))


def librsyncDeltaFile(filename, signature, deltafile):
	(f, df, ldf) = (None, None, None)
	bufsize = 1024*1024
	try:
		f = open(filename, "rb")
		df = open(deltafile, "wb")
		ldf = librsync.DeltaFile(signature, f)

		data = True
		while(data):
			data = ldf.read(bufsize)
			df.write(data)
		df.close()
		f.close()
		ldf.close()
	except Exception, e:
		if df:  df.close()
		if f:   f.close()
		if ldf: ldf.close()
		raise Exception(u"Failed to write delta file: %s" % forceUnicode(e))


def md5sum(filename):
	f = open(filename, 'rb')
	m = md5()
	while True:
		d = f.read(524288)
		if not d:
			break
		m.update(d)
	f.close()
	return m.hexdigest()


def randomString(length):
	string = u''
	for i in range(length):
		string = string + random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
	return unicode(string)


def generateOpsiHostKey():
	key = u''
	if (os.name == 'posix'):
		logger.debug(u"Opening random device '%s' to generate opsi host key" % RANDOM_DEVICE)
		r = open(RANDOM_DEVICE)
		key = r.read(16)
		r.close()
		logger.debug("Random device closed")
		key = unicode(key.encode("hex"))
	else:
		logger.debug(u"Using python random module to generate opsi host key")
		while (len(key) < 32):
			key += random.choice([u'0',u'1',u'2',u'3',u'4',u'5',u'6',u'7',u'8',u'9',u'a',u'b',u'c',u'd',u'e',u'f'])
	return key


def timestamp(secs=0, dateOnly=False):
	''' Returns a timestamp of the current system time format: YYYY-mm-dd[ HH:MM:SS] '''
	if not secs:
		secs = time.time()
	if dateOnly:
		return time.strftime( u"%Y-%m-%d", time.localtime(secs) )
	else:
		return time.strftime( u"%Y-%m-%d %H:%M:%S", time.localtime(secs) )

def objectToBeautifiedText(obj,level=0):
	if (level == 0):
		obj = serialize(obj)

	hspace = level*10
	text = u''
	if type(obj) is types.ListType:
		text = u'%s%s[ \n' % (text, u' '*hspace)
		for i in range( len(obj) ):
			if not type(obj[i]) in (types.DictType, types.ListType):
				text = u'%s%s' % (text, u' '*hspace)
			text = u'%s%s' % (text, objectToBeautifiedText(obj[i], level+1))

			if (i < len(obj)-1):
				text = u"%s,\n" % (text)
		text = u'%s\n%s]' % (text, u' '*hspace)
	elif type(obj) is types.DictType:
		text = u'%s%s{ \n' % (text, u' '*hspace)
		i = 0
		for (key, value) in obj.items():
			text = u'%s%s"%s" : ' % (text, u' '*hspace, key)
			if type(value) in (types.DictType, types.ListType):
				text = u'%s\n' % text
			text = u'%s%s' % (text, objectToBeautifiedText(value, level+1))

			if (i < len(obj)-1):
				text = u'%s,\n' % text
			i+=1
		text = u'%s\n%s}' % (text, u' '*hspace)
	elif type(obj) is str:
		text = u'%s%s' % (text, toJson(forceUnicode(obj)))
	else:
		text = u'%s%s' % (text, toJson(obj))
	return text


def objectToBash(obj, bashVars = {}, level=0):
	if (level == 0):
		obj = serialize(obj)

	varName = 'RESULT'
	if (level > 0):
		varName = 'RESULT%d' % level

	if not bashVars.get(varName):
		bashVars[varName] = u''

	if hasattr(obj, 'serialize'):
		obj = obj.serialize()

	if type(obj) is types.ListType:
		bashVars[varName] += u'(\n'
		for i in range( len(obj) ):
			if type(obj[i]) in (types.DictType, types.ListType):
				hashFound = True
				level += 1
				objectToBash(obj[i], bashVars, level)
				bashVars[varName] += u'RESULT%d=${RESULT%d[*]}' % (level, level)
			else:
				objectToBash(obj[i], bashVars, level)
			bashVars[varName] += u'\n'
		bashVars[varName] = bashVars[varName][:-1] + u'\n)'
	elif type(obj) is types.DictType:
		bashVars[varName] += u'(\n'
		for (key, value) in obj.items():
			bashVars[varName] += '%s=' % key
			if type(value) in (types.DictType, types.ListType):
				level += 1
				v = objectToBash(value, bashVars, level)
				bashVars[varName] += u'${RESULT%d[*]}' % level
			else:
				objectToBash(value, bashVars, level)
			bashVars[varName] += u'\n'
		bashVars[varName] = bashVars[varName][:-1] + u'\n)'

	elif obj is None:
		bashVars[varName] += u'""'

	else:
		bashVars[varName] += u'"%s"' % forceUnicode(obj)

	return bashVars


def objectToHtml(obj, level=0):
	if (level == 0):
		obj = serialize(obj)

	html = u''
	if type(obj) is types.ListType:
		html += u'['
		if (len(obj) > 0):
			html += u'<div style="padding-left: 3em;">'
			for i in range( len(obj) ):
				html += objectToHtml(obj[i], level+1)
				if (i < len(obj)-1):
					html += u',<br />\n'
			html += u'</div>'
		html += u']'
	elif type(obj) is types.DictType:
		html += u'{'
		if (len(obj) > 0):
			html += u'<div style="padding-left: 3em;">'
			i = 0
			for (key, value) in obj.items():
				html += u'<font class="json_key">%s</font>: ' % objectToHtml(key)
				html += objectToHtml(value, level+1)
				if (i < len(obj)-1):
					html += u',<br />\n'
				i+=1
			html += u'</div>'
		html += u'}'
	elif type(obj) is types.BooleanType:
		html += str(obj).lower()
	elif type(obj) is types.NoneType:
		html += 'null'
	else:
		isStr = type(obj) in (str, unicode)
		if isStr:
			html += u'"'
		html += forceUnicode(obj)\
			.replace(u'\r', u'')\
			.replace(u'\t', u'   ')\
			.replace(u'&',  u'&amp;')\
			.replace(u'"',  u'&quot;')\
			.replace(u"'",  u'&apos;')\
			.replace(u' ',  u'&nbsp;')\
			.replace(u'<',  u'&lt;')\
			.replace(u'>',  u'&gt;')\
			.replace(u'\n', u'<br />\n')
		if isStr:
			html += u'"'
	return html


def compareVersions(v1, condition, v2):
	v1 = forceUnicode(v1)
	v2 = forceUnicode(v2)

	if "~" in v1:
		v1 = v1[:v1.find("~")]
	if "~" in v2:
		v2 = v2[:v2.find("~")]

	if not condition:
		condition = u'=='
	if not condition in (u'==', u'=', u'<', u'<=', u'>', u'>='):
		raise Exception(u"Bad condition '%s'" % condition)
	if (condition == u'='):
		condition = u'=='

	v1ProductVersion = u'0'
	v1PackageVersion = u'0'

	match = re.search('^\s*([\w\.]+)-*([\w\.]*)\s*$', v1)
	if not match:
		raise Exception(u"Bad version string '%s'" % v1)

	v1ProductVersion = match.group(1)
	if match.group(2):
		v1PackageVersion = match.group(2)

	v2ProductVersion = u'0'
	v2PackageVersion = u'0'

	match = re.search('^\s*([\w\.]+)-*([\w\.]*)\s*$', v2)
	if not match:
		raise Exception(u"Bad version string '%s'" % v2)

	v2ProductVersion = match.group(1)
	if match.group(2):
		v2PackageVersion = match.group(2)

	for (v1, v2) in ( (v1ProductVersion, v2ProductVersion), (v1PackageVersion, v2PackageVersion) ):
		v1p = v1.split(u'.')
		v2p = v2.split(u'.')
		while len(v1p) < len(v2p):
			v1p.append(u'0')
		while len(v2p) < len(v1p):
			v2p.append(u'0')
		for i in range(len(v1p)):
			while (len(v1p[i]) > 0) or (len(v2p[i]) > 0):
				cv1 = u''
				cv2 = u''

				match = re.search('^(\d+)(\D*.*)$', v1p[i])
				if match:
					cv1 = int(match.group(1))
					v1p[i] = match.group(2)
				else:
					match = re.search('^(\D+)(\d*.*)$', v1p[i])
					if match:
						cv1 = match.group(1)
						v1p[i] = match.group(2)

				match = re.search('^(\d+)(\D*.*)$', v2p[i])
				if match:
					cv2 = int(match.group(1))
					v2p[i] = match.group(2)
				else:
					match = re.search('^(\D+)(\d*.*)$', v2p[i])
					if match:
						cv2 = match.group(1)
						v2p[i] = match.group(2)

				if (cv1 == u''): cv1 = chr(1)
				if (cv2 == u''): cv2 = chr(1)
				if (cv1 == cv2):
					logger.debug2(u"%s == %s => continue" % (cv1, cv2))
					continue

				if type(cv1) is not int: cv1 = u"'%s'" % cv1
				if type(cv2) is not int: cv2 = u"'%s'" % cv2

				b = eval( u"%s %s %s" % (cv1, condition, cv2) )
				logger.debug2(u"%s(%s) %s %s(%s) => %s | '%s' '%s'" % (type(cv1), cv1, condition, type(cv2), cv2, b, v1p[i], v2p[i]) )
				if not b:
					logger.debug(u"Unfulfilled condition: %s-%s %s %s-%s" \
						% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
					return False
				else:
					logger.debug(u"Fulfilled condition: %s-%s %s %s-%s" \
						% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
					return True
	if (condition.find(u'=') == -1):
		logger.debug(u"Unfulfilled condition: %s-%s %s %s-%s" \
			% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
		return False
	logger.debug(u"Fulfilled condition: %s-%s %s %s-%s" \
		% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
	return True


unitRegex = re.compile('^(\d+\.*\d*)\s*([\w]{0,4})$')
def removeUnit(x):
	x = forceUnicode(x)
	match = unitRegex.search(x)
	if not match:
		return x

	if (match.group(1).find(u'.') != -1):
		value = float(match.group(1))
	else:
		value = int(match.group(1))
	unit = match.group(2)
	mult = 1000

	if   unit.lower().endswith('hz'):
		unit = unit[:-2]
	elif unit.lower().endswith('bits'):
		mult = 1024
		unit = unit[:-4]
	elif unit.lower().endswith('b'):
		mult = 1024
		unit = unit[:-1]
	elif unit.lower().endswith('s') or unit.lower().endswith('v'):
		unit = unit[:-1]

	if unit.endswith('n'):
		return float(value)/(mult*mult)
	if unit.endswith('m'):
		return float(value)/(mult)
	if unit.lower().endswith('k'):
		return value*mult
	if unit.endswith('M'):
		return value*mult*mult
	if unit.endswith('G'):
		return value*mult*mult*mult

	return value


def blowfishEncrypt(key, cleartext):
	''' Takes cleartext string,
	    returns hex-encoded, blowfish-encrypted string '''
	cleartext = forceUnicode(cleartext).encode('utf-8')
	key = forceUnicode(key)

	while ( len(cleartext) % 8 != 0 ):
		# Fill up with \0 until length is a mutiple of 8
		cleartext += chr(0)
	try:
		key = key.decode("hex")
	except TypeError:
		raise Exception(u"Failed to hex decode key '%s'" % key)

	blowfish = Blowfish.new(key,  Blowfish.MODE_CBC, BLOWFISH_IV)
	crypt = blowfish.encrypt(cleartext)
	return unicode(crypt.encode("hex"))


def blowfishDecrypt(key, crypt):
	''' Takes hex-encoded, blowfish-encrypted string,
	    returns cleartext string '''
	key = forceUnicode(key)
	crypt = forceUnicode(crypt)
	try:
		key = key.decode("hex")
	except TypeError, e:
		raise Exception(u"Failed to hex decode key '%s'" % key)
	crypt = crypt.decode("hex")
	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	cleartext = blowfish.decrypt(crypt)
	# Remove possible \0-chars
	if (cleartext.find('\0') != -1):
		cleartext = cleartext[:cleartext.find('\0')]
	try:
		return unicode(cleartext, 'utf-8')
	except Exception, e:
		logger.error(e)
		raise Exception(u"Failed to decrypt")


def encryptWithPublicKeyFromX509CertificatePEMFile(data, filename):
	import M2Crypto
	f = open(filename, 'r')
	try:
		cert = M2Crypto.X509.load_cert_string(f.read())
		rsa = cert.get_pubkey().get_rsa()
		enc = ''
		chunks = []
		while (len(data) > 16):
			chunks.append(data[:16])
			data = data[16:]
		chunks.append(data)
		for chunk in chunks:
			enc += rsa.public_encrypt(data = chunk, padding = M2Crypto.RSA.pkcs1_oaep_padding)
		return enc
	finally:
		f.close()


def decryptWithPrivateKeyFromPEMFile(data, filename):
	import M2Crypto
	privateKey = M2Crypto.RSA.load_key(filename)
	chunks = []
	while (len(data) > 128):
		chunks.append(data[:128])
		data = data[128:]
	chunks.append(data)
	res = ''
	for chunk in chunks:
		res += privateKey.private_decrypt(data = chunk, padding = M2Crypto.RSA.pkcs1_oaep_padding)
	if (res.find('\0') != -1):
		res = res[:res.find('\0')]
	return res


def findFiles(directory, prefix=u'', excludeDir=None, excludeFile=None, includeDir=None, includeFile=None, returnDirs=True, returnLinks=True, followLinks=False, repository=None):
	directory = forceFilename(directory)
	prefix = forceUnicode(prefix)
	if excludeDir:
		if (str(type(excludeDir)).find("SRE_Pattern") == -1):
			excludeDir = re.compile(forceUnicode(excludeDir))
	else:
		excludeDir = None
	if excludeFile:
		if (str(type(excludeFile)).find("SRE_Pattern") == -1):
			excludeFile = re.compile(forceUnicode(excludeFile))
	else:
		excludeFile = None
	if includeDir:
		if (str(type(includeDir)).find("SRE_Pattern") == -1):
			includeDir = re.compile(forceUnicode(includeDir))
	else:
		includeDir = None
	if includeFile:
		if (str(type(includeFile)).find("SRE_Pattern") == -1):
			includeFile = re.compile(forceUnicode(includeFile))
	else:
		includeFile = None
	returnDirs = forceBool(returnDirs)
	returnLinks = forceBool(returnLinks)
	followLinks = forceBool(followLinks)

	islink  = os.path.islink
	isdir   = os.path.isdir
	listdir = os.listdir
	if repository:
		islink  = repository.islink
		isdir   = repository.isdir
		listdir = repository.listdir

	files = []
	for entry in listdir(directory):
		if type(entry) is str:
			logger.error(u"Bad filename '%s' found in directory '%s', skipping entry!" % (unicode(entry, 'ascii', 'replace'), directory))
			continue
		pp = os.path.join(prefix, entry)
		dp = os.path.join(directory, entry)
		isLink = False
		if islink(dp):
			isLink = True
			if not returnLinks and not followLinks:
				continue
		if isdir(dp) and (not isLink or followLinks):
			if excludeDir and re.search(excludeDir, entry):
				logger.debug(u"Excluding dir '%s' and containing files" % entry)
				continue
			if includeDir:
				if not re.search(includeDir, entry):
					continue
				logger.debug(u"Including dir '%s' and containing files" % entry)
			if returnDirs:
				files.append(pp)
			files.extend(
				findFiles(
					directory   = dp,
					prefix      = pp,
					excludeDir  = excludeDir,
					excludeFile = excludeFile,
					includeDir  = includeDir,
					includeFile = includeFile,
					returnDirs  = returnDirs,
					returnLinks = returnLinks,
					followLinks = followLinks,
					repository  = repository) )
			continue
		if excludeFile and re.search(excludeFile, entry):
			if isLink:
				logger.debug(u"Excluding link '%s'" % entry)
			else:
				logger.debug(u"Excluding file '%s'" % entry)
			continue
		if includeFile:
			if not re.search(includeFile, entry):
				continue
			if isLink:
				logger.debug(u"Including link '%s'" % entry)
			else:
				logger.debug(u"Including file '%s'" % entry)
		files.append(pp)
	return files


def ipAddressInNetwork(ipAddress, networkAddress):
	ipAddress = forceIPAddress(ipAddress)
	networkAddress = forceNetworkAddress(networkAddress)

	n = ipAddress.split('.')
	for i in range(4):
		n[i] = forceInt(n[i])
	ip = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]

	(network, netmask) = networkAddress.split(u'/')
	while (network.count('.') < 3):
		network = network + u'.0'
	if (netmask.find('.') == -1):
		netmask = forceUnicode(socket.inet_ntoa(struct.pack('>I',0xffffffff ^ (1 << 32 - forceInt(netmask)) - 1)))
	while (netmask.count('.') < 3):
		netmask = netmask + u'.0'

	logger.debug(u"Testing if ip %s is part of network %s/%s" % (ipAddress, network, netmask))

	n = network.split('.')
	for i in range(4):
		n[i] = int(n[i])
	network = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
	n = netmask.split('.')
	for i in range(4):
		n[i] = int(n[i])
	netmask = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]

	wildcard = netmask ^ 0xFFFFFFFFL
	if (wildcard | ip == wildcard | network):
		return True
	return False


def flattenSequence(sequence):
	list = []
	for s in sequence:
		if type(s) in (types.ListType, types.TupleType):
			list.extend(flattenSequence(s))
		else:
			list.append(s)
	return list


def getfqdn(name='', conf=None):
	if not name:
		env = os.environ.copy()
		if "OPSI_HOSTNAME" in env:
			return forceFqdn(env["OPSI_HOSTNAME"])
		hn = getGlobalConfig('hostname')
		if hn:
			return forceFqdn(hn)
	return forceFqdn(socket.getfqdn(name))


def getGlobalConfig(name, configFile=OPSI_GLOBAL_CONF):
	name = forceUnicode(name)
	if os.path.exists(configFile):
		f = codecs.open(configFile, 'r', 'utf8')
		try:
			for line in f.readlines():
				line = line.strip()
				if not line or line[0] in ('#', ';') or (line.find('=') == -1):
					continue
				(k, v) = line.split('=', 1)
				if (k.strip().lower() == name.lower()):
					return v.strip()
		finally:
			f.close()
	return None
