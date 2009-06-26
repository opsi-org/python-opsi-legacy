#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Tools   =
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

__version__ = '1.0.1'

# Imports
import time, json, gettext, os, re, random, subprocess
try:
	from hashlib import md5
except ImportError:
	from md5 import md5

# OPSI imports
from Logger import *
from Util import *
import System

# Blowfish initialization vector
BLOWFISH_IV = 'OPSI1234'
#RANDOM_DEVICE = '/dev/random'
RANDOM_DEVICE = '/dev/urandom'

# Get Logger instance
logger = Logger()

# Get locale
try:
	t = gettext.translation('opsi_tools', LOCALE_DIR)
	def _(string):
		return t.ugettext(string).encode('utf-8', 'replace')
	
except Exception, e:
	logger.info("Locale not found: %s" % e)
	def _(string):
		"""Dummy method, created and called when no locale is found.
		Uses the fallback language (called C; means english) then."""
		return string

def removeUnit(x):
	match = re.search('^(\d+\.*\d*)\s*([\w]{0,4})$', x)
	if not match:
		return x
	
	if (match.group(1).find('.') != -1):
		value = float(match.group(1))
	else:
		value = int(match.group(1))
	unit = match.group(2)
	mult = 1000
	
	if unit.lower().endswith('hz'):
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

def md5sum(filename):
	f = open(filename, 'rb')
	m = md5()
	while True:
		d = f.read(8096)
		if not d:
			break
		m.update(d)
	f.close()
	return m.hexdigest()

def randomString(length):
	string = ''
	for i in range(length):
		string = string + random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
	return string

def compareVersions(v1, condition, v2):
	
	v1ProductVersion = '0'
	v1PackageVersion = '0'
	
	match = re.search('^\s*([\w\.]+)-*([\w\.]*)\s*$', v1)
	if not match:
		raise Exception("Bad version string '%s'" % v1)
	
	v1ProductVersion = match.group(1)
	if match.group(2):
		v1PackageVersion = match.group(2)
	
	if condition:
		match = re.search('^\s*([<=>]?=?)\s*$', condition)
		if not match:
			raise Exception("Bad condition '%s'" % condition)
	if not condition or (condition == '='):
		condition = '=='
	
	v2ProductVersion = '0'
	v2PackageVersion = '0'
	
	match = re.search('^\s*([\w\.]+)-*([\w\.]*)\s*$', v2)
	if not match:
		raise Exception("Bad version string '%s'" % v2)
	
	v2ProductVersion = match.group(1)
	if match.group(2):
		v2PackageVersion = match.group(2)
	
	for (v1, v2) in ( (v1ProductVersion, v2ProductVersion), (v1PackageVersion, v2PackageVersion) ):
		v1p = v1.split('.')
		v2p = v2.split('.')
		while len(v1p) < len(v2p):
			v1p.append('0')
		while len(v2p) < len(v1p):
			v2p.append('0')
		for i in range(len(v1p)):
			while (len(v1p[i]) > 0) or (len(v2p[i]) > 0):
				cv1 = ''
				cv2 = ''
				
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
				
				if (cv1 == ''): cv1 = chr(1)
				if (cv2 == ''): cv2 = chr(1)
				if (cv1 == cv2):
					logger.debug2("%s == %s => continue" % (cv1, cv2))
					continue
				
				if type(cv1) is not int: cv1 = "'%s'" % cv1
				if type(cv2) is not int: cv2 = "'%s'" % cv2
				
				b = eval( "%s %s %s" % (cv1, condition, cv2) )
				logger.debug2("%s(%s) %s %s(%s) => %s | '%s' '%s'" % (type(cv1), cv1, condition, type(cv2), cv2, b, v1p[i], v2p[i]) )
				if not b:
					logger.debug("Unfulfilled condition: %s-%s %s %s-%s" \
						% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
					return False
				else:
					logger.debug("Fulfilled condition: %s-%s %s %s-%s" \
						% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
					return True
	if (condition.find('=') == -1):
		logger.debug("Unfulfilled condition: %s-%s %s %s-%s" \
			% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
		return False
	logger.debug("Fulfilled condition: %s-%s %s %s-%s" \
		% (v1ProductVersion, v1PackageVersion, condition, v2ProductVersion, v2PackageVersion ))
	return True
	
	
def compressFile(filename, format, rsyncable=True):
	
	logger.notice("Compressing file '%s', format: %s" % (filename, format) )
	
	if (format == 'gzip' or format == 'gz'):
		options = ''
		if rsyncable:
			options = '--rsyncable'
		if os.path.exists(filename + '.gz'):
			os.unlink(filename + '.gz')
		System.execute('%s %s "%s"' % (System.which('gzip'), options, filename) )
		return filename + '.gz'
	elif (format == 'bzip2' or format == 'bz2'):
		if os.path.exists(filename + '.bz2'):
			os.unlink(filename + '.bz2')
		System.execute('%s "%s"' % (System.which('bzip2'), filename) )
		return filename + '.bz2'
	else:
		raise Exception("Unsupported compression format '%s'" % format)

def createArchive(filename, fileList, format='cpio', dereference = False, chdir=None, exitOnErr=True):
	if chdir:
		os.chdir(chdir)
	
	logger.notice("Creating archive '%s', format: %s" % (filename, format))
	
	if format not in ['cpio', 'tar']:
		raise Exception("Unsupported archive format '%s'" % format)
	
	proc = None
	if (format == 'cpio'):
		extraOptions = ''
		if dereference:
			extraOptions = '--dereference'
		logger.debug("Executing: '%s %s --quiet -o -H crc -O \"%s\"'" % (System.which('cpio'), extraOptions, filename) )
		proc = subprocess.Popen('%s %s --quiet -o -H crc -O "%s"' % (System.which('cpio'), extraOptions, filename),
					shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	elif (format == 'tar'):
		extraOptions = ''
		if dereference:
			extraOptions = '--dereference'
		logger.debug("Executing: '%s %s --no-recursion --create --file \"%s\" -T -" % (System.which('tar'), extraOptions, filename))
		proc = subprocess.Popen('%s %s --no-recursion --create --file "%s" -T -' % (System.which('tar'), extraOptions, filename),
					shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	
	flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
	fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
	
	errors = []
	ret = None
	for f in fileList:
		if not f:
			continue
		logger.info("Adding file '%s'" % f)
		proc.stdin.write("%s\n" % f)
		
		try:
			error = proc.stderr.readline()
			logger.error(error)
			errors.append(error)
		except:
			pass
	
	proc.stdin.close()
	
	while ret is None:
		ret = proc.poll()
	
	logger.info("Exit code: %s" % ret)
	
	if (ret != 0):
		raise Exception('%s command failed with code %s: ' % (format, ret) + '\n'.join(errors))
	
	return filename

def extractArchive(filename, format=None, chdir=None, exitOnErr=True, patterns=[]):
	os.putenv("LC_ALL", "C")
	prevDir = None
	if chdir:
		try:
			prevDir = os.path.abspath(os.getcwd())
		except:
			pass
		logger.debug("Changing to directory '%s'" % chdir)
		os.chdir(chdir)
	
	try:
		if not format:
			logger.debug2("Testing archive format")
			if filename.lower().endswith('cpio.gz'):
				format = 'cpio.gz'
			elif filename.lower().endswith('cpio'):
				format = 'cpio'
			elif filename.lower().endswith('tar.gz'):
				format = 'tar.gz'
			elif filename.lower().endswith('tar.bz2'):
				format = 'tar.bz2'
			elif filename.lower().endswith('tar'):
				format = 'tar'
			else:
				f = open(filename)
				data = f.read(6)
				if data in ('070701', '070702', '070707'):
					format = 'cpio'
				else:
					f.seek(257)
					data = f.read(5)
					if (data == 'ustar'):
						format = 'tar'
				f.close()
			
			if not format:
				raise Exception("Unknown format")
			
		if not format in ['cpio', 'cpio.gz', 'tar', 'tar.gz', 'tar.bz2']:
			raise Exception("Unsupported archive format '%s'" % format)
		
		logger.notice("Extracting archive '%s', format: %s" % (filename, format))
		
		exclude = ''
		if format.startswith('tar') and patterns:
			for f in getArchiveContent(filename):
				for p in patterns:
					if not re.search(p, f):
						exclude += ' --exclude="%s"' % f
		if (format == 'cpio'):
			if exitOnErr:
				# No not exist if error is "operation not permitted"
				exitOnErr = re.compile('(?!(?:^.*operation not permitted.*$))(^.*$)', re.IGNORECASE)
			System.execute('%s "%s" | %s --quiet -idum %s' \
				% (System.which('cat'), filename, System.which('cpio'), ' '.join(patterns)), exitOnErr = exitOnErr)
			
		elif (format == 'cpio.gz'):
			if exitOnErr:
				# No not exist if error is "operation not permitted"
				exitOnErr = re.compile('(?!(?:^.*operation not permitted.*$))(^.*$)', re.IGNORECASE)
			System.execute('%s "%s" | %s | %s --quiet -idum %s' \
				% (System.which('cat'), filename, System.which('gunzip'), System.which('cpio'), ' '.join(patterns)), exitOnErr = exitOnErr)
		
		elif (format == 'tar'):
			System.execute('%s --extract --file "%s" %s' \
				% (System.which('tar'), filename, exclude), exitOnErr = exitOnErr)
		
		elif (format == 'tar.gz'):
			System.execute('%s --gunzip --extract --file "%s" %s' \
				% (System.which('tar'), filename, exclude), exitOnErr = exitOnErr)
		
		elif (format == 'tar.bz2'):
			System.execute('%s --bzip2 --extract --file "%s" %s' \
				% (System.which('tar'), filename, exclude), exitOnErr = exitOnErr)
	except Exception, e:
		logger.error("Failed to extract '%s': %s" % (filename, e))
		if prevDir:
			try:
				os.chdir(prevDir)
			except:
				pass
		raise e
	if prevDir:
		try:
			os.chdir(prevDir)
		except:
			pass
	
	
def getArchiveContent(filename, format=None):
	if not format:
		logger.debug2("Testing archive format")
		if filename.lower().endswith('cpio.gz'):
			format = 'cpio.gz'
		elif filename.lower().endswith('cpio'):
			format = 'cpio'
		elif filename.lower().endswith('tar.gz'):
			format = 'tar.gz'
		elif filename.lower().endswith('tar.bz2'):
			format = 'tar.bz2'
		elif filename.lower().endswith('tar'):
			format = 'tar'
		else:
			f = open(filename)
			data = f.read(6)
			if data in ('070701', '070702', '070707'):
				format = 'cpio'
			else:
				f.seek(257)
				data = f.read(5)
				if (data == 'ustar'):
					format = 'tar'
			f.close()
		
		if not format:
			raise Exception("Unknown format")
		
	if not format in ['cpio', 'cpio.gz', 'tar', 'tar.gz']:
		raise Exception("Unsupported archive format '%s'" % format)
	
	logger.notice("Getting content of archive '%s', format: %s" % (filename, format))
	
	filelist = []
	
	if (format == 'cpio'):
		for line in System.execute('%s "%s" | %s --quiet -it' % (System.which('cat'), filename, System.which('cpio'))):
			if line:
				filelist.append(line)
	elif (format == 'cpio.gz'):
		for line in System.execute('%s "%s" | %s | %s --quiet -it' % (System.which('cat'), filename, System.which('gunzip'), System.which('cpio'))):
			if line:
				filelist.append(line)
	elif (format == 'tar'):
		for line in System.execute('%s --list --file "%s"' % (System.which('tar'), filename)):
			if line:
				filelist.append(line)
	
	elif (format == 'tar.gz'):
		for line in System.execute('%s --gunzip --list --file "%s"' % (System.which('tar'), filename)):
			if line:
				filelist.append(line)
	
	elif (format == 'tar.bz2'):
		for line in System.execute('%s --bzip2 --list --file "%s"' % (System.which('tar'), filename)):
			if line:
				filelist.append(line)
	
	return filelist
	
	
def findFiles(directory, prefix='', excludeDir=None, excludeFile=None, includeDir=None, includeFile=None, returnDirs=True):
	files = []
	entries = os.listdir(directory)
	for entry in entries:
		if ( (entry == '.') or (entry == '..') ):
			continue
		
		if os.path.isdir(os.path.join(directory, entry)):
			if excludeDir and re.search(excludeDir, entry):
				logger.debug("Excluding dir '%s' and containing files" % entry)
				continue
			if includeDir:
				if not re.search(includeDir, entry):
					continue
				logger.debug("Including dir '%s' and containing files" % entry)
			if returnDirs:
				files.append( os.path.join(prefix, entry) )
			files.extend(
				findFiles(
					directory   = os.path.join(directory, entry),
					prefix      = os.path.join(prefix, entry),
					excludeDir  = excludeDir,
					excludeFile = excludeFile,
					includeDir  = includeDir,
					includeFile = includeFile,
					returnDirs  = returnDirs ) )
		else:
			if excludeFile and re.search(excludeFile, entry):
				logger.debug("Excluding file '%s'" % entry)
				continue
			if includeFile:
				if not re.search(includeFile, entry):
					continue
				logger.debug("Including file '%s'" % entry)
			files.append( os.path.join(prefix, entry) )
	return files

def generateOpsiHostKey():
	key = ''
	if (os.name == 'posix'):
		logger.debug("Opening random device '%s'" % RANDOM_DEVICE)
		r = open (RANDOM_DEVICE)
		key = r.read(16)
		r.close()
		logger.debug("Random device closed")
	else:
		logger.debug("Using random")
		while (len(key) < 32):
			key += random.choice(['0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f'])
		return key
	return key.encode("hex")
	
def blowfishEncrypt(key, cleartext):
	''' Takes cleartext string, 
	    returns hex-encoded, blowfish-encrypted string '''
	from Crypto.Cipher import Blowfish
	while ( len(cleartext) % 8 != 0 ):
		# Fill up with \0 until length is a mutiple of 8
		cleartext += chr(0)
	try:
		key = key.decode("hex")
	except TypeError, e:
		raise Exception("Failed to hex decode key '%s'" % key)
	
	blowfish = Blowfish.new(key,  Blowfish.MODE_CBC, BLOWFISH_IV)
	crypt = blowfish.encrypt(cleartext)
	return crypt.encode("hex")
	
def blowfishDecrypt(key, crypt):
	''' Takes hex-encoded, blowfish-encrypted string string, 
	    returns cleartext string '''
	from Crypto.Cipher import Blowfish
	try:
		key = key.decode("hex")
	except TypeError, e:
		raise Exception("Failed to hex decode key '%s'" % key)
	crypt = crypt.decode("hex")
	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	cleartext = blowfish.decrypt(crypt)
	# Remove possible \0-chars
	if (cleartext.find('\0') != -1):
		cleartext = cleartext[:cleartext.find('\0')]
	return cleartext

def timestamp(secs=0):
	''' Returns a timestamp of the current system time.
	    format: YYYYmmddHHMMSS '''
	if not secs:
		secs = time.time()
	return time.strftime( "%Y%m%d%H%M%S", time.localtime(secs) )


def jsonObjToBeautifiedText(jsonObj, level=0):
	return objectToBeautifiedText(jsonObj, level)
	
def objectToBeautifiedText(obj, level=0):
	hspace = level*10
	text = ''
	if ( type(obj) == type([]) ):
		text += ' '*hspace + '[ \n'
		for i in range( len(obj) ):
			if type(obj[i]) != type({}) and type(obj[i]) != type([]):
				text += ' '*hspace
			text += objectToBeautifiedText(obj[i], level+1)
			
			if (i < len(obj)-1):
				text += ',\n'
		text += '\n' + ' '*hspace + ']'
	elif ( type(obj) == type({}) ):
		text += ' '*hspace + '{ \n'
		i = 0
		for (key, value) in obj.items():
			text += ' '*hspace + '"' + key + '" : '
			if type(value) == type({}) or type(value) == type([]):
				text += '\n'
			text += objectToBeautifiedText(obj[key], level+1)
			
			if (i < len(obj)-1):
				text += ',\n'
			i+=1
		text += '\n' + ' '*hspace + '}'
	else:
		if hasattr(json, 'dumps'):
			# python 2.6 json module
			text+= json.dumps(obj)
		else:
			text+= json.write(obj)
	return text


def jsonObjToHtml(jsonObj, level=0):
	''' This function creates a beautified json 
	    serialisation from a json object'''
	hspace = level*10
	html = ''
	if ( type(jsonObj) == type([]) ):
		html += ' '*hspace + '[ <br />'
		for i in range( len(jsonObj) ):
			if type(jsonObj[i]) != type({}) and type(jsonObj[i]) != type([]):
				html += ' '*hspace
			html += jsonObjToHtml(jsonObj[i], level+1)
			
			if (i < len(jsonObj)-1):
				html += ',<br />'
		html += '<br />' + ' '*hspace + ']'
	elif ( type(jsonObj) == type({}) ):
		html += ' '*hspace + '{ <br />'
		i = 0
		for (key, value) in jsonObj.items():
			html += ' '*hspace + '"<font class="json_key">' + key +  '</font>": '
			if type(value) == type({}) or type(value) == type([]):
				html += '<br />'
			html += jsonObjToHtml(jsonObj[key], level+1)
			
			if (i < len(jsonObj)-1):
				html += ',<br />'
			i+=1
		html += '<br />' + ' '*hspace + '}'
	else:
		if hasattr(json, 'dumps'):
			# python 2.6 json module
			html += json.dumps(jsonObj).replace('<', '&lt;').replace('>', '&gt;')
		else:
			html += json.write(jsonObj).replace('<', '&lt;').replace('>', '&gt;')
	return html.replace('\\n', '<br />' + ' '*hspace)


def jsonObjToBash(jsonObj, bashVars={}, cur=-1):
	varName = 'RESULT'
	if (cur >= 0):
		varName = 'RESULT%s' % cur
	
	if not bashVars.get(varName):
		bashVars[varName] = ''
	
	if ( type(jsonObj) == type([]) ):
		bashVars[varName] += '(\n'
		for obj in jsonObj:
			if ( type(obj) == type({}) or type(obj) == type([]) ):
				hashFound = True
				cur += 1
				jsonObjToBash(obj, bashVars, cur)
				bashVars[varName] += 'RESULT%s=${RESULT%s[*]}' % (cur, cur)
			else:
				jsonObjToBash(obj, bashVars, cur)
			bashVars[varName] += '\n'
		bashVars[varName] = bashVars[varName][:-1] + '\n)'
		
		
	elif ( type(jsonObj) == type({}) ):
		bashVars[varName] += '(\n'
		for (key, obj) in jsonObj.items():
			bashVars[varName] += key + '='
			if ( type(obj) == type({}) or type(obj) == type([]) ):
				cur += 1
				v = jsonObjToBash(obj, bashVars, cur)
				bashVars[varName] += '${RESULT%s[*]}' % cur
			else:
				jsonObjToBash(obj, bashVars, cur)
			bashVars[varName] += '\n'
		bashVars[varName] = bashVars[varName][:-1] + '\n)'
	
	elif (jsonObj == None):
		bashVars[varName] += '""'
	
	else:
		bashVars[varName] += '"' + str(jsonObj) + '"'
	
	return bashVars

def integrateDrivers(driverSourceDirectories, driverDestinationDirectory, messageObserver=None, progressObserver=None):
	logger.info("Integrating drivers")
	
	messageSubject = MessageSubject(id='integrateDrivers')
	if messageObserver:
		messageSubject.attachObserver(messageObserver)
	messageSubject.setMessage("Integrating drivers")
	
	driverDestinationDirectories = []
	driverNumber = 0
	if not os.path.exists(driverDestinationDirectory):
		os.mkdir(driverDestinationDirectory)
	
	integratedFiles = []
	for filename in os.listdir(driverDestinationDirectory):
		dirname = os.path.join(driverDestinationDirectory, filename)
		if not os.path.isdir(dirname):
			continue
		if re.search('^\d+$', filename):
			if (int(filename) >= driverNumber):
				driverNumber = int(filename)
			files = []
			for f in os.listdir(dirname):
				files.append(f.lower())
			files.sort()
			integratedFiles.append(','.join(files))
	for driverSourceDirectory in driverSourceDirectories:
		logger.notice("Integrating driver dir '%s'" % driverSourceDirectory)
		messageSubject.setMessage("Integrating driver dir '%s'" % os.path.basename(driverSourceDirectory), severity='INFO')
		if not os.path.exists(driverSourceDirectory):
			logger.error("Driver directory '%s' not found" % driverSourceDirectory)
			messageSubject.setMessage("Driver directory '%s' not found" % driverSourceDirectory, severity='ERROR')
			continue
		files = []
		for f in os.listdir(driverSourceDirectory):
			files.append(f.lower())
		files.sort()
		files = ','.join(files)
		logger.debug("Driver files: %s" % files)
		for fs in integratedFiles:
			logger.debug("   Integrated files: %s" % fs)
		if files in integratedFiles:
			logger.notice("Driver directory '%s' already integrated" % driverSourceDirectory)
			messageSubject.setMessage("Driver directory '%s' already integrated" % driverSourceDirectory, severity = 'INFO')
			continue
		driverNumber += 1
		dstDriverPath = os.path.join(driverDestinationDirectory, str(driverNumber))
		if not os.path.exists(dstDriverPath):
			os.mkdir(dstDriverPath)
		System.copy(driverSourceDirectory + '/*', dstDriverPath)
		driverDestinationDirectories.append(str(dstDriverPath))
		integratedFiles.append(files)
	return driverDestinationDirectories

def integrateTextmodeDrivers(driverDirectory, destination, hardware, sifFile=None, messageObserver=None, progressObserver=None):
	logger.info("Integrating textmode drivers")
	
	messageSubject = MessageSubject(id='integrateTextmodeDrivers')
	if messageObserver:
		messageSubject.attachObserver(messageObserver)
	messageSubject.setMessage("Integrating textmode drivers")
	
	hardwareIds = {}
	for info in hardware.get("PCI_DEVICE", []):
		vendorId = info.get('vendorId', '').upper()
		deviceId = info.get('deviceId', '').upper()
		if not hardwareIds.has_key(vendorId):
			hardwareIds[vendorId] = []
		hardwareIds[vendorId].append(deviceId)
	
	logger.info("Searching for txtsetup.oem in '%s'" % driverDirectory)
	txtSetupOems = findFiles(directory = driverDirectory, prefix = driverDirectory, includeFile = re.compile('^txtsetup\.oem$', re.IGNORECASE), returnDirs=False)
	for txtSetupOem in txtSetupOems:
		logger.notice("'%s' found, integrating textmode driver" % txtSetupOem)
		messageSubject.setMessage("'%s' found, integrating textmode driver" % txtSetupOem, severity='INFO')
		driverPath = os.path.dirname(txtSetupOem)
		
		# Parse txtsetup.oem
		logger.info("Parsing txtsetup.oem")
		sections = {}
		sectionRegex = re.compile('\[\s*([^\]]+)\s*\]')
		deviceRegex = re.compile('VEN_([\da-fA-F]+)(&DEV_([\da-fA-F]+))?')
		f = open(txtSetupOem)
		section = None
		for line in f.readlines():
			line = line.strip()
			if not line or line.startswith('#') or line.startswith(';'):
				continue
			logger.debug("txtsetup.oem: %s" % line)
			match = re.search(sectionRegex, line)
			if match:
				section = match.group(1)
				sections[section] = []
			elif section:
				sections[section].append(line)
		f.close()
		
		# Search for default id
		defaultHwComponentId = ''
		logger.info("Searching for default hardware component id")
		for (section, lines) in sections.items():
			if (section.lower() != 'defaults'):
				continue
			for line in lines:
				(key, value) = line.split('=', 1)
				if (key.strip().lower() == 'scsi'):
					defaultHwComponentId = value.strip()
		if not defaultHwComponentId:
			logger.error("Default hardware component id not found in txtsetup.oem, failed to integrate textmode driver.")
			messageSubject.setMessage("Default hardware component id not found in txtsetup.oem, failed to integrate textmode driver", severity='ERROR')
			continue
		logger.notice("Found default hardware component id '%s'" % defaultHwComponentId)
		
		# Search for hardware id
		logger.info("Searching for hardware id and tagfile")
		tagfiles = {}
		for (section, lines) in sections.items():
			if not section.lower().startswith('hardwareids.'):
				continue
			logger.info("Found hardwareIds section %s" % section)
			for line in lines:
				if not re.search('[iI][dD]\s*=', line):
					continue
				(device, tf) = line.split('=', 1)[1].strip().split(',', 1)
				device = device.strip()
				if device.startswith('"') and device.endswith('"'):
					device = device[1:-1]
				tf = tf.strip()
				if tf.startswith('"') and tf.endswith('"'):
					tf = tf[1:-1]
				match = re.search(deviceRegex, device)
				if not match:
					logger.error("Parsing error: =>%s<=" % device)
					continue
				if match.group(1).upper() in hardwareIds.keys() and (not match.group(2) or match.group(3).upper() in hardwareIds[match.group(1).upper()]):
					hwComponentId = section.split('.', 2)[2].lower()
					tagfiles[hwComponentId] = tf
		if not tagfiles:
			logger.warning("No needed hardware component id found in txtsetup.oem, not integrating textmode driver.")
			messageSubject.setMessage("No needed hardware component id found in txtsetup.oem, not integrating textmode driver.", severity='WARNING')
			continue
		logger.debug("Found tagfiles: %s" % tagfiles)
		
		hwComponentId = tagfiles.keys()[0]
		if (len(tagfiles.keys()) > 0) and tagfiles.has_key(defaultHwComponentId.lower()):
			hwComponentId = defaultHwComponentId.lower()
		tagfile = tagfiles[hwComponentId]
		logger.notice("Using component id '%s' and tagfile '%s'" % (hwComponentId, tagfile))
		
		# Search for disks
		logger.info("Searching for disks")
		driverDisks = {}
		for (section, lines) in sections.items():
			if (section.lower() != 'disks'):
				continue
			for line in lines:
				if (line.find('=') == -1):
					continue
				(driverDisk, value) = line.split('=', 1)
				driverDisk = driverDisk.strip()
				(dn, tf, dd) = value.split(',', 2)
				tf = tf.strip()
				if tf.startswith('\\'): tf = tf[1:]
				dd = dd.strip()
				if dd.startswith('\\'): dd = dd[1:]
				driverDisks[driverDisk] = { "displayName": dn, "tagfile": tf, "driverDir": dd }
		if not driverDisks:
			logger.error("No disks found in txtsetup.oem, failed to integrate textmode driver.")
			messageSubject.setMessage("No disks found in txtsetup.oem, failed to integrate textmode driver", severity='ERROR')
			continue
		
		# Search for needed files
		logger.info("Searching for needed files")
		driver = []
		inf = []
		catalog = []
		filesRegex = re.compile('Files\.scsi\.%s' % hwComponentId, re.IGNORECASE)
		for (section, lines) in sections.items():
			match = re.search(filesRegex, section)
			if not match:
				continue
			for line in lines:
				(key, value) = line.split('=', 1)
				key = key.strip()
				driverDisk = value.split(',')[0].strip()
				filename = value.split(',')[1].strip()
				if   (key.lower() == 'driver'):
					driver.append( os.path.join(driverDisks[driverDisk]['driverDir'], filename) )
				elif (key.lower() == 'inf'):
					inf.append( os.path.join(driverDisks[driverDisk]['driverDir'], filename) )
				elif (key.lower() == 'catalog'):
					catalog.append( os.path.join(driverDisks[driverDisk]['driverDir'], filename) )
			break
		
		logger.notice("Needed files: %s, %s, %s" % (', '.join(driver), ', '.join(inf), ', '.join(catalog) ))
		if not (driver and inf and catalog):
			logger.error("Failed to find needed info")
			messageSubject.setMessage("Failed to find needed info", severity='ERROR')
			continue
		
		# Search for hardware description
		logger.info("Searching for hardware description")
		description = ''
		for (section, lines) in sections.items():
			if (section.lower() == 'scsi'):
				for line in lines:
					(key, value) = line.split('=', 1)
					if (key.strip().lower() == hwComponentId.lower()):
						description = value.split(',')[0].strip()
						if description.startswith('"') and description.endswith('"'):
							description = description[1:-1]
		if not description:
			logger.error("Hardware description not found in txtsetup.oem, failed to integrate textmode driver.")
			messageSubject.setMessage("Hardware description not found in txtsetup.oem, failed to integrate textmode driver.", severity='ERROR')
		logger.notice("Hardware description is '%s'" % description)
		
		# Copy files
		oemBootFiles = []
		oemBootFiles.append( os.path.basename(txtSetupOem) )
		for textmodePath in ( 	os.path.join(destination, '$', 'textmode'), \
					os.path.join(destination, '$win_nt$.~bt', '$oem$') ):
			if not os.path.exists(textmodePath):
				os.mkdir(textmodePath)
			System.System.copy(txtSetupOem, textmodePath)
		
		for one in inf, driver, catalog:
			for fn in one:
				System.copy(os.path.join(driverPath, fn), os.path.join(destination, '$', 'textmode', os.path.basename(fn)))
				System.copy(os.path.join(driverPath, fn), os.path.join(destination, '$win_nt$.~bt', '$oem$',fn))
				oemBootFiles.append(fn)
		
		# Patch winnt.sif
		if sifFile:
			logger.notice("Registering textmode drivers in sif file '%s'" % sifFile)
			lines = []
			massStorageDriverLines = []
			oemBootFileLines = []
			section = ''
			sif = open(sifFile, 'r')
			for line in sif.readlines():
				if line.strip():
					logger.debug2("Current sif file content: %s" % line.rstrip())
				if line.strip().startswith('['):
					section = line.strip().lower()[1:-1]
					if section in ('massstoragedrivers', 'oembootfiles'):
						continue
				if (section == 'massstoragedrivers'):
					massStorageDriverLines.append(line)
					continue
				if (section == 'oembootfiles'):
					oemBootFileLines.append(line)
					continue
				lines.append(line)
			sif.close()
			
			logger.info("Patching sections for driver '%s'" % description)
			
			if not massStorageDriverLines:
				massStorageDriverLines = ['\r\n', '[MassStorageDrivers]\r\n']
			massStorageDriverLines.append('"%s" = OEM\r\n' % description)
			
			if not oemBootFileLines:
				oemBootFileLines = ['\r\n', '[OEMBootFiles]\r\n']
			for obf in oemBootFiles:
				oemBootFileLines.append('%s\r\n' % obf)
			
			logger.debug("Patching [MassStorageDrivers] in file '%s':" % sifFile)
			logger.debug(massStorageDriverLines)
			lines.extend(massStorageDriverLines)
			logger.debug("Patching [OEMBootFiles] in file '%s':" % sifFile)
			logger.debug(oemBootFileLines)
			lines.extend(oemBootFileLines)
			
			sif = open(sifFile, 'w')
			sif.writelines(lines)
			sif.close()
		
def integrateAdditionalDrivers(driverSourceDirectory, driverDestinationDirectory, additionalDrivers, messageObserver=None, progressObserver=None):
	logger.info("Adding additional drivers")
	
	messageSubject = MessageSubject(id='integrateAdditionalDrivers')
	if messageObserver:
		messageSubject.attachObserver(messageObserver)
	messageSubject.setMessage("Adding additional drivers")
	
	driverDirectories = []
	for additionalDriver in additionalDrivers.split(','):
		additionalDriver = additionalDriver.strip()
		if not additionalDriver:
			continue
		additionalDriverDir = os.path.join(driverSourceDirectory, additionalDriver)
		if not os.path.exists(additionalDriverDir):
			logger.error("Additional drivers dir '%s' not found" % additionalDriverDir)
			messageSubject.setMessage("Additional drivers dir '%s' not found" % additionalDriverDir, severity='ERROR')
			continue
		infFiles = findFiles(directory = additionalDriverDir, prefix = additionalDriverDir, includeFile = re.compile('\.inf$', re.IGNORECASE), returnDirs=False)
		logger.info("Found inf files: %s in dir '%s'" % (infFiles, additionalDriverDir))
		if not infFiles:
			logger.error("No drivers found in dir '%s'" % additionalDriverDir)
			messageSubject.setMessage("No drivers found in dir '%s'" % additionalDriverDir, severity='ERROR')
			continue
		for infFile in infFiles:
			additionalDriverDir = os.path.dirname(infFile)
			if additionalDriverDir in driverDirectories:
				continue
			logger.info("Adding additional driver dir '%s'" % additionalDriverDir)
			messageSubject.setMessage("Adding additional driver dir '%s'" % additionalDriverDir, severity='INFO')
			driverDirectories.append(additionalDriverDir)
	
	if messageObserver:
		messageSubject.detachObserver(messageObserver)
	
	return integrateDrivers(driverDirectories, driverDestinationDirectory, messageObserver, progressObserver)

def integrateHardwareDrivers(driverSourceDirectory, driverDestinationDirectory, hardware, messageObserver=None, progressObserver=None):
	logger.info("Adding drivers for detected hardware")
	
	messageSubject = MessageSubject(id='integrateHardwareDrivers')
	if messageObserver:
		messageSubject.attachObserver(messageObserver)
	messageSubject.setMessage("Adding drivers for detected hardware")
	
	driverDirectories = []
	integratedFiles = []
	for type in ('PCI', 'USB', 'HDAUDIO'):
		devices = []
		baseDir = ''
		if (type == 'PCI'):
			devices = hardware.get("PCI_DEVICE", [])
			baseDir = 'pciids'
		elif (type == 'USB'):
			devices = hardware.get("USB_DEVICE", [])
			baseDir = 'usbids'
		elif (type == 'HDAUDIO'):
			devices = hardware.get("HDAUDIO_DEVICE", [])
			baseDir = 'hdaudioids'
		for info in devices:
			name = info.get('name', '???')
			name = name.replace('/', '_')
			vendorId = info.get('vendorId', '').upper()
			deviceId = info.get('deviceId', '').upper()
			if not vendorId or not deviceId:
				continue
			logger.info("Searching driver for %s device '%s', id '%s:%s'" % (type, name, vendorId, deviceId))
			messageSubject.setMessage("Searching driver for %s device '%s', id '%s:%s'" % (type, name, vendorId, deviceId), severity = 'INFO')
			srcDriverPath = os.path.join(driverSourceDirectory, baseDir, vendorId)
			if not os.path.exists(srcDriverPath):
				logger.error("%s Vendor directory '%s' not found" % (type, srcDriverPath))
				messageSubject.setMessage("%s Vendor directory '%s' not found" % (type, srcDriverPath), severity = 'ERROR')
				continue
			srcDriverPath = os.path.join(srcDriverPath, deviceId)
			if not os.path.exists(srcDriverPath):
				logger.error("%s Device directory '%s' not found" % (type, srcDriverPath))
				messageSubject.setMessage("%s Device directory '%s' not found" % (type, srcDriverPath), severity = 'ERROR')
				continue
			if os.path.exists( os.path.join(srcDriverPath, 'WINDOWS_BUILDIN') ):
				logger.notice("Using build-in windows driver")
				messageSubject.setMessage("Using build-in windows driver", severity = 'SUCCESS')
				continue
			logger.notice("Found driver for %s device '%s', in dir '%s'" % (type, name, srcDriverPath))
			logger.notice("Integrating driver for %s device '%s'" % (type, name))
			messageSubject.setMessage("Integrating driver for %s device '%s'" % (type, name), severity = 'SUCCESS')
			driverDirectories.append(srcDriverPath)
	
	if messageObserver:
		messageSubject.detachObserver(messageObserver)
	
	return integrateDrivers(driverDirectories, driverDestinationDirectory, messageObserver, progressObserver)

def getOemPnpDriversPath(driverDirectory, target, separator=';', prePath='', postPath=''):
	logger.info("Generating oemPnpDriversPath")
	if not driverDirectory.startswith(target):
		raise Exception("Driver directory '%s' not on target '%s'" % (driverDirectory, target))
	
	relPath = driverDirectory[len(target):]
	while relPath.startswith(os.sep):
		relPath = relPath[1:]
	while relPath.endswith(os.sep):
		relPath = relPath[:-1]
	relPath = '\\'.join(relPath.split(os.sep))
	oemPnpDriversPath = ''
	for dirname in os.listdir(driverDirectory):
		dirname = relPath + '\\' + dirname
		if prePath:
			dirname = prePath + '\\' + dirname
		if postPath:
			dirname = postPath + '\\' + dirname
		if oemPnpDriversPath:
			oemPnpDriversPath += separator
		oemPnpDriversPath += dirname
	logger.info("Returning oemPnpDriversPath '%s'" % oemPnpDriversPath)
	return oemPnpDriversPath

