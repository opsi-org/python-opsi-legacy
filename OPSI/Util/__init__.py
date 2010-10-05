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
   @license: GNU General Public License version 2
"""

__version__ = '4.0'

# Imports
import ctypes, threading, os, random, base64, types, socket, httplib
from sys import version_info
if (version_info >= (2,6)):
	import json
else:
	import simplejson as json

try:
	from hashlib import md5
except ImportError:
	from md5 import md5
from Crypto.Cipher import Blowfish

if (os.name == 'posix'):
	from duplicity import librsync
if (os.name == 'nt'):
	try:
		import librsync
	except Exception, e:
		logger.error(u"Failed to import librsync: %s" % e)

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *

# Get logger instance
logger = Logger()

RANDOM_DEVICE = '/dev/urandom'

def _async_raise(tid, excobj):
	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(excobj))
	if (res == 0):
		logger.error(u"_async_raise: nonexistent thread id")
		raise ValueError(u"nonexistent thread id")
	elif (res > 1):
		# if it returns a number greater than one, you're in trouble,
		# and you should call it again with exc=NULL to revert the effect
		ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
		logger.error(u"_async_raise: PyThreadState_SetAsyncExc failed")
		raise SystemError(u"PyThreadState_SetAsyncExc failed")

class KillableThread(threading.Thread):
	def raise_exc(self, excobj):
		if not self.isAlive():
			logger.error(u"Cannot terminate, thread must be started")
			return
		for tid, tobj in threading._active.items():
			if tobj is self:
				_async_raise(tid, excobj)
				return
	
	# the thread was alive when we entered the loop, but was not found 
	# in the dict, hence it must have been already terminated. should we raise
	# an exception here? silently ignore?
	
	def terminate(self):
		# must raise the SystemExit type, instead of a SystemExit() instance
		# due to a bug in PyThreadState_SetAsyncExc
		self.raise_exc(SystemExit)



#def non_blocking_connect_http_OLD(self, connectTimeout=0):
#	''' Non blocking connect, needed for KillableThread '''
#	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#	sock.setblocking(0)
#	started = time.time()
#	while True:
#		try:
#			if (connectTimeout > 0) and ((time.time()-started) >= connectTimeout):
#				raise socket.timeout(u"Timed out after %d seconds" % connectTimeout)
#			sock.connect((self.host, self.port))
#		except socket.error, e:
#			if e[0] in (106, 10056):
#				# Transport endpoint is already connected
#				break
#			if e[0] not in (111, 114, 115, 10022, 10035):
#				# 111   = posix: Connection refused
#				# 10022 = nt: Invalid argument
#				if sock:
#					sock.close()
#				raise
#			time.sleep(0.5)
#	sock.setblocking(1)
#	self.sock = sock

def non_blocking_connect_http(self, connectTimeout=0):
	''' Non blocking connect, needed for KillableThread '''
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.settimeout(3.0)
	started = time.time()
	lastError = None
	while True:
		try:
			if (connectTimeout > 0) and ((time.time()-started) >= connectTimeout):
				raise Exception(u"Timed out after %d seconds (%s)" % (connectTimeout, forceUnicode(lastError)))
			sock.connect((self.host, self.port))
			break
		except socket.error, e:
			logger.debug(e)
			if e[0] in (106, 10056):
				# Transport endpoint is already connected
				break
			if e[0] not in (114, ) or not lastError:
				lastError = e
			time.sleep(0.5)
	sock.settimeout(None)
	self.sock = sock
	
def non_blocking_connect_https(self, connectTimeout=0):
	non_blocking_connect_http(self, connectTimeout)
	if (version_info >= (2,6)):
		import ssl
		self.sock = ssl.wrap_socket(self.sock, self.key_file, self.cert_file)
	else:
		ssl = socket.ssl(self.sock, self.key_file, self.cert_file)
		self.sock = httplib.FakeSocket(self.sock, ssl)


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
	#if (os.name != 'posix'):
	#	raise NotImplementedError(u"Not implemented for non-posix os")
	
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
	#if (os.name != 'posix'):
	#	raise NotImplementedError(u"Not implemented for non-posix os")
	
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

def objectToBeautifiedText(obj, level=0):
	if (level == 0):
		obj = serialize(obj)
	
	hspace = level*10
	text = u''
	if type(obj) is types.ListType:
		text += u' '*hspace + u'[ \n'
		for i in range( len(obj) ):
			if not type(obj[i]) in (types.DictType, types.ListType):
				text += u' '*hspace
			text += objectToBeautifiedText(obj[i], level+1)
			
			if (i < len(obj)-1):
				text += u',\n'
		text += u'\n' + u' '*hspace + u']'
	elif type(obj) is types.DictType:
		text += u' '*hspace + u'{ \n'
		i = 0
		for (key, value) in obj.items():
			text += u' '*hspace + u'"' + key + u'" : '
			if type(value) in (types.DictType, types.ListType):
				text += u'\n'
			text += objectToBeautifiedText(value, level+1)
			
			if (i < len(obj)-1):
				text += u',\n'
			i+=1
		text += u'\n' + u' '*hspace + u'}'
	elif type(obj) is str:
		text += toJson(forceUnicode(obj))
	else:
		text += toJson(obj)
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
				html += u'"<font class="json_key">%s</font>": ' % key
				html += objectToHtml(value, level+1)
				if (i < len(obj)-1):
					html += u',<br />\n'
				i+=1
			html += u'</div>'
		html += u'}'
	else:
		isStr = type(obj) in (str, unicode)
		if isStr:
			html += u'"'
		html += forceUnicode(obj)\
			.replace(u'\r', u'')\
			.replace(u'\t', u'   ')\
			.replace(u' ',  u'&#x202f;')\
			.replace(u'<',  u'&lt;')\
			.replace(u'>',  u'&gt;')\
			.replace(u'\n', u'<br />\n')
		if isStr:
			html += u'"'
	return html

def compareVersions(v1, condition, v2):
	v1 = forceUnicode(v1)
	v2 = forceUnicode(v2)
	
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


BLOWFISH_IV = 'OPSI1234'

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
	except TypeError, e:
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
	
	
if (__name__ == "__main__"):
	logger.setConsoleLevel(LOG_DEBUG2)
	logger.setConsoleColor(True)
	from OPSI.Object import *
	obj = []
	for i in range(1000):
		obj.append(
			LocalbootProduct(
				id = 'product%d' % i,
				productVersion = random.choice(('1.0', '2', 'xxx', '3.1', '4')),
				packageVersion = random.choice(('1', '2', 'y', '3', '10', 11, 22)),
				name = 'Product %d' % i,
				licenseRequired = random.choice((None, True, False)),
				setupScript = random.choice(('setup.ins', None)),
				uninstallScript = random.choice(('uninstall.ins', None)),
				updateScript = random.choice(('update.ins', None)),
				alwaysScript = random.choice(('always.ins', None)),
				onceScript = random.choice(('once.ins', None)),
				priority = random.choice((-100, -90, -30, 0, 30, 40, 60, 99)),
				description = random.choice(('Test product %d' % i, 'Some product', '--------', '', None)),
				advice = random.choice(('Nothing', 'Be careful', '--------', '', None)),
				changelog = None,
				windowsSoftwareIds = None
			)
		)
	start = time.time()
	print objectToHtml(obj, level=0)
	print time.time() - start
	
	
	
