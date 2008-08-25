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

__version__ = '0.9.9.1'

# Imports
import time, json, gettext, os, re, random, md5

# OPSI imports
from Logger import *
import System

# Blowfish initialization vector
BLOWFISH_IV = 'OPSI1234'
#RANDOM_DEVICE = '/dev/random'
if os.name == "posix":
	RANDOM_DEVICE = '/dev/urandom'
else:
	RANDOM_DEVICE = 'PYTHON_LIB'

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
	f = open(filename)
	m = md5.new()
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
	
	fi = None
	import popen2
	
	if (format == 'cpio'):
		extraOptions = ''
		if dereference:
			extraOptions = '--dereference'
		logger.debug("Executing: '%s %s --quiet -o -H crc -O \"%s\"'" % (System.which('cpio'), extraOptions, filename) )
		fi = popen2.Popen3('%s %s --quiet -o -H crc -O "%s"' % (System.which('cpio'), extraOptions, filename), capturestderr=True)
	elif (format == 'tar'):
		extraOptions = ''
		if dereference:
			extraOptions = '--dereference'
		logger.debug("Executing: '%s %s --no-recursion --create --file \"%s\" -T -" % (System.which('tar'), extraOptions, filename))
		fi = popen2.Popen3('%s %s --no-recursion --create --file "%s" -T -' % (System.which('tar'), extraOptions, filename), capturestderr=True)
		
	flags = fcntl.fcntl(fi.childerr, fcntl.F_GETFL)
	fcntl.fcntl(fi.childerr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
	
	errors = []
	
	ret = -1
	for f in fileList:
		if not f:
			continue
		logger.info("Adding file '%s'" % f)
		fi.tochild.write("%s\n" % f)
		
		try:
			error = fi.childerr.readline()
			logger.error(error)
			errors.append(error)
		except:
			pass
	
	fi.tochild.close()
	
	ret = fi.poll()
	while (ret == -1):
		ret = fi.poll()
	
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
	
	
def findFiles(directory, prefix='', excludeDir=None, excludeFile=None):
	files = []
	entries = os.listdir(directory)
	for entry in entries:
		if ( (entry == '.') or (entry == '..') ):
			continue
		
		if os.path.isdir(os.path.join(directory, entry)):
			if excludeDir and re.match(excludeDir, entry):
				logger.debug("Excluding dir '%s' and contained files" % entry)
				continue
			files.append( os.path.join(prefix, entry) )
			files.extend(
				findFiles( 
					os.path.join(directory, entry), 
					os.path.join(prefix, entry),
					excludeDir, 
					excludeFile ) )
		else:
			if excludeFile and re.match(excludeFile, entry):
				logger.debug("Excluding file '%s'" % entry)
				continue
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
		logger.debug("Using randint")
		key = randint(0,1000000000000000)
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


