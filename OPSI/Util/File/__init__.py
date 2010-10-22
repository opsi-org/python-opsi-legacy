#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =    opsi python library - File     =
   = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008, 2009 uib GmbH
   
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

__version__ = "4.0.2"

import os, codecs, re, ConfigParser, StringIO, locale

if (os.name == 'posix'):
	import fcntl, grp, pwd

elif (os.name == 'nt'):
	import win32con
	import win32file
	import pywintypes

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *

# Get logger instance
logger = Logger()

class File(object):
	def __init__(self, filename):
		self._filename = forceFilename(filename)
		self._fileHandle = None
		
	def getFilename(self):
		return self._filename
	
	def setFilename(self, filename):
		self._filename = forceFilename(filename)
	
	def exists(self):
		return os.path.exists(self._filename)
			
	def delete(self):
		if os.path.exists(self._filename):
			os.unlink(self._filename)
	
	def chown(self, user, group):
		if (os.name == 'nt'):
			logger.warning(u"Not implemented on windows")
			return
		uid = -1
		if type(user) is int:
			if (user > -1):
				uid = user
		elif not user is None:
			try:
				uid = pwd.getpwnam(user)[2]
			except KeyError:
				raise Exception(u"Unknown user '%s'" % user)
		
		gid = -1
		if type(group) is int:
			if (group > -1):
				gid = group
		elif not group is None:
			try:
				gid = grp.getgrnam(group)[2]
			except KeyError:
				raise Exception(u"Unknown group '%s'" % group)
		
		os.chown(self._filename, uid, gid)
	
	def chmod(self, mode):
		mode = forceOct(mode)
		os.chmod(self._filename, mode)
	
	def create(self, user = None, group = None, mode = None):
		if not os.path.exists(self._filename):
			self.open('w')
			self.close()
		
		if not user is None or not group is None:
			self.chown(user, group)
		if not mode is None:
			self.chmod(mode)
	
	def open(self, mode = 'r'):
		self._fileHandle = __builtins__['open'](self._filename, mode)
		return self._fileHandle
		
	def close(self):
		if not self._fileHandle:
			return
		self._fileHandle.close()
		self._fileHandle = None
		
	def __getattr__(self, attr):
		if self.__dict__.has_key(attr):
			return self.__dict__[attr]
		elif self.__dict__['_fileHandle']:
			return getattr(self.__dict__['_fileHandle'], attr)

class LockableFile(File):
	_fileLockLock = threading.Lock()
	
	def __init__(self, filename, lockFailTimeout = 2000):
		File.__init__(self, filename)
		self._lockFailTimeout = forceInt(lockFailTimeout)
	
	def open(self, mode = 'r', encoding = None, errors = 'replace'):
		truncate = False
		if mode in ('w', 'wb') and os.path.exists(self._filename):
			if (mode == 'w'):
				mode = 'r+'
				truncate = True
			elif (mode == 'wb'):
				mode = 'rb+'
				truncate = True
		if encoding:
			self._fileHandle = codecs.open(self._filename, mode, encoding, errors)
		else:
			self._fileHandle = __builtins__['open'](self._filename, mode)
		self._lockFile(mode)
		if truncate:
			self._fileHandle.seek(0)
			self._fileHandle.truncate()
		return self._fileHandle
		
	def close(self):
		if not self._fileHandle:
			return
		self._fileHandle.flush()
		File.close(self)
		
	def _lockFile(self, mode='r'):
		timeout = 0
		while (timeout < self._lockFailTimeout):
			# While not timed out and not locked
			logger.debug("Trying to lock file '%s' (%s/%s)" % (self._filename, timeout, self._lockFailTimeout))
			try:
				if (os.name == 'posix'):
					# Flags for exclusive, non-blocking lock
					flags = fcntl.LOCK_EX | fcntl.LOCK_NB
					if mode in ('r', 'rb'):
						# Flags for shared, non-blocking lock
						flags = fcntl.LOCK_SH | fcntl.LOCK_NB
					fcntl.flock(self._fileHandle.fileno(), flags)
				elif (os.name == 'nt'):
					flags = win32con.LOCKFILE_EXCLUSIVE_LOCK | win32con.LOCKFILE_FAIL_IMMEDIATELY
					if mode in ('r', 'rb'):
						flags = win32con.LOCKFILE_FAIL_IMMEDIATELY
					hfile = win32file._get_osfhandle(self._fileHandle.fileno())
					win32file.LockFileEx(hfile, flags, 0, 0x7fff0000, pywintypes.OVERLAPPED())
				
			except IOError, e:
				# increase timeout counter, sleep 100 millis
				timeout += 100
				time.sleep(0.1)
				continue
			# File successfully locked
			logger.debug("File '%s' locked after %d millis" % (self._filename, timeout))
			return self._fileHandle
		
		File.close(self)
		# File lock failed => raise IOError
		raise IOError("Failed to lock file '%s' after %d millis" % (self._filename,  self._lockFailTimeout))
	
	def _unlockFile(self):
		if not self._fileHandle:
			return
		if (os.name == 'posix'):
			fcntl.flock(self._fileHandle.fileno(), fcntl.LOCK_UN)
		elif (os.name == 'nt'):
			hfile = win32file._get_osfhandle(self._fileHandle.fileno())
			win32file.UnlockFileEx(hfile, 0, 0x7fff0000, pywintypes.OVERLAPPED())
		
class TextFile(LockableFile):
	def __init__(self, filename, lockFailTimeout = 2000):
		LockableFile.__init__(self, filename, lockFailTimeout)
		self._lines = []
		self._lineSeperator = u'\n'
		
	def open(self, mode = 'r', encoding='utf-8', errors='replace'):
		#self._fileHandle = LockableFile.open(mode, encoding, errors)
		#self._lockFile(mode)
		#return self._fileHandle
		return LockableFile.open(self, mode, encoding, errors)
		
	def write(self, str):
		if not self._fileHandle:
			raise IOError("File not opened")
		str = forceUnicode(str)
		self._fileHandle.write(str)
	
	def readlines(self):
		self._lines = []
		if not self._fileHandle:
			for encoding in ('utf-8', 'utf-16', 'latin_1', 'cp1252', 'replace'):
				errors = 'strict'
				if (encoding == 'replace'):
					errors = 'replace'
					encoding = 'utf-8'
				
				self.open(encoding = encoding, errors = errors)
				try:
					self._lines = self._fileHandle.readlines()
					self.close()
					break
				except ValueError, e:
					self.close()
					continue
		return self._lines
	
	def getLines(self):
		return self._lines
	
	def writelines(self, sequence=[]):
		if not self._fileHandle:
			raise IOError("File not opened")
		if sequence:
			self._lines = forceUnicodeList(sequence)
		for i in range(len(self._lines)):
			self._lines[i] += self._lineSeperator
		self._fileHandle.writelines(self._lines)

class ChangelogFile(TextFile):
	'''
	package (version) distribution(s); urgency=urgency
	    [optional blank line(s), stripped]
	  * change details
	     more change details
	      [blank line(s), included]
	  * even more change details
	      [optional blank line(s), stripped]
	[one space]-- maintainer name <email address>[two spaces]date

	'''
	releaseLineRegex = re.compile('^\s*(\S+)\s+\(([^\)]+)\)\s+([^\;]+)\;\s+urgency\=(\S+)\s*$')
	
	def __init__(self, filename, lockFailTimeout = 2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._entries = []
	
	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		self._entries = []
		currentEntry = {}
		for lineNum in range(len(self._lines)):
			try:
				line = self._lines[lineNum]
				match = self.releaseLineRegex.search(line)
				if match:
					if currentEntry:
						self.addEntry(currentEntry)
					
					currentEntry = {
						'package':         match.group(1),
						'version':         match.group(2),
						'release':         match.group(3),
						'urgency':         match.group(4),
						'changelog':       [],
						'maintainerName':  u'',
						'maintainerEmail': u'',
						'date':            None
					}
					continue
				
				if line.startswith(' --'):
					if (line.find('  ') == -1):
						raise Exception(u"maintainer must be separated from date using two spaces")
					if not currentEntry or currentEntry['date']:
						raise Exception(u"found trailer out of release")
					
					(maintainer, date) = line[3:].strip().split('  ', 1)
					email = u''
					if (maintainer.find('<') != -1):
						(maintainer, email) = maintainer.split('<', 1)
						maintainer = maintainer.strip()
						email = email.strip().replace('<', '').replace('>', '')
					currentEntry['maintainerName'] = maintainer
					currentEntry['maintainerEmail'] = email
					if (date.find('+') != -1):
						date = date.split('+')[0]
					currentEntry['date'] = time.strptime(date.strip(), "%a, %d %b %Y %H:%M:%S")
					changelog = []
					buf = []
					for l in currentEntry['changelog']:
						if not changelog and not l.strip():
							continue
						if not l.strip():
							buf.append(l)
						else:
							changelog.extend(buf)
							buf = []
							changelog.append(l)
					currentEntry['changelog'] = changelog
					
				else:
					if not currentEntry and line.strip():
						raise Exception(u"text not in release")
					if currentEntry:
						currentEntry['changelog'].append(line.rstrip())
			except Exception, e:
				raise Exception(u"Parse error in line %d: %s" % (lineNum, e))
		if currentEntry:
			self.addEntry(currentEntry)
		self._parsed = True
		return self._entries
		
	def generate(self):
		# get current locale
		loc = locale.getlocale()
		locale.setlocale(locale.LC_ALL, 'C')
		try:
			if not self._entries:
				raise Exception(u"No entries to write")
			self._lines = []
			for entry in self._entries:
				self._lines.append(u'%s (%s) %s; urgency=%s' % (entry['package'], entry['version'], entry['release'], entry['urgency']))
				self._lines.append(u'')
				for line in entry['changelog']:
					self._lines.append(line)
				if self._lines[-1].strip():
					self._lines.append(u'')
				self._lines.append(u' -- %s <%s>  %s' % (entry['maintainerName'], entry['maintainerEmail'], time.strftime('%a, %d %b %Y %H:%M:%S +0000', entry['date'])))
				self._lines.append(u'')
			self.open('w')
			self.writelines()
			self.close()
		finally:
			if loc:
				try:
					locale.setlocale(locale.LC_ALL, loc)
				except:
					pass
		
	def getEntries(self):
		if not self._parsed:
			self.parse()
		return self._entries
	
	def setEntries(self, entries):
		entries = forceList(entries)
		self._entries = []
		for entry in entries:
			self.addEntry(entry)
	
	def addEntry(self, entry):
		entry = forceDict(entry)
		for key in ('package', 'version', 'release', 'urgency', 'changelog', 'maintainerName', 'maintainerEmail', 'date'):
			if not entry.has_key(key):
				raise Exception(u"Missing key '%s' in entry %s" % (key, entry))
		entry['package']         = forceProductId(entry['package'])
		entry['version']         = forceUnicode(entry['version'])
		entry['release']         = forceUnicode(entry['release'])
		entry['urgency']         = forceUnicode(entry['urgency'])
		entry['changelog']       = forceUnicodeList(entry['changelog'])
		entry['maintainerName']  = forceUnicode(entry['maintainerName'])
		entry['maintainerEmail'] = forceEmailAddress(entry['maintainerEmail'])
		entry['date']            = forceTime(entry['date'])
		self._entries.append(entry)
		
class ConfigFile(TextFile):
	def __init__(self, filename, lockFailTimeout = 2000, commentChars=[';', '#'], lstrip = True):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._commentChars = forceList(commentChars)
		self._lstrip = forceBool(lstrip)
		self._parsed = False
	
	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		lines = []
		for line in self._lines:
			l = line.strip()
			if not l or l[0] in self._commentChars:
				continue
			if self._lstrip:
				line = line.strip()
			else:
				line = line.rstrip()
			for cc in self._commentChars:
				index = line.find(cc)
				if (index == -1):
					continue
				parts = line.split(cc)
				quote = 0
				doublequote = 0
				cut = -1
				for i in range(len(parts)):
					quote += parts[i].count("'")
					doublequote += parts[i].count('"')
					if (len(parts[i]) > 0) and (parts[i][-1] == '\\'):
						# escaped comment
						continue
					if (i == len(parts)-1):
						break
					if not (quote % 2) and not (doublequote % 2):
						cut = i
						break
				if (cut > -1):
					line = cc.join(parts[:cut+1])
			if not line:
				continue
			#for cc in self._commentChars:
			#	line = line.replace(u'\\' + cc, cc)
			lines.append(line)
		self._parsed = True
		return lines

class IniFile(ConfigFile):
	optionMatch = re.compile('^([^\:\=]+)([\:\=].*)$')
	
	def __init__(self, filename, lockFailTimeout = 2000, ignoreCase = True, raw = True):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars = [';', '#'])
		self._ignoreCase = forceBool(ignoreCase)
		self._raw = forceBool(raw)
		self._configParser = None
		self._parsed = False
		self._sectionSequence = []
	
	def setSectionSequence(self, sectionSequence):
		self._sectionSequence = forceUnicodeList(sectionSequence)
		
	def parse(self, lines=None):
		self._parsed = False
		logger.debug(u"Parsing ini file '%s'" % self._filename)
		start = time.time()
		lines = ConfigFile.parse(self, lines)
		self._parsed = False
		if self._ignoreCase:
			for i in range(len(lines)):
				lines[i] = lines[i].strip()
				if lines[i].startswith('['):
					lines[i] = lines[i].lower()
				
				match = self.optionMatch.search(lines[i])
				if not match:
					continue
				lines[i] = match.group(1).lower() + match.group(2)
		
		self._configParser = None
		if self._raw:
			self._configParser = ConfigParser.RawConfigParser()
		else:
			self._configParser = ConfigParser.SafeConfigParser()
		try:
			self._configParser.readfp( StringIO.StringIO(u'\r\n'.join(lines)) )
		except Exception, e:
			raise Exception(u"Failed to parse ini file '%s': %s" % (self._filename, e))
		
		logger.debug(u"Finished reading file after %0.3f seconds" % (time.time() - start))
		
		self._parsed = True
		return self._configParser
	
	def generate(self, configParser):
		self._configParser = configParser
		self._lines = []
		
		if not self._configParser:
			raise Exception(u"Got no data to write")
		
		sections = self._configParser.sections()
		sections.sort()
		
		sequence = list(self._sectionSequence)
		sequence.reverse()
		for section in sequence:
			if section in sections:
				logger.debug2(u"Moving section %s to top" % section)
				sections.remove(section)
				sections.insert(0, section)
		logger.debug2(u"Section sequence: %s" % sections)
		
		for section in sections:
			self._lines.append(u'[%s]' % forceUnicode(section))
			options = self._configParser.options(section)
			options.sort()
			for option in options:
				self._lines.append(u'%s = %s' % (forceUnicode(option), forceUnicode(self._configParser.get(section, option))))
			self._lines.append(u'')
			
		self.open('w')
		self.writelines()
		self.close()
	
	def generate_old(self, configParser):
		self._configParser = configParser
		
		if not self._configParser:
			raise Exception(u"Got no data to write")
		
		sections = {}
		for section in self._configParser.sections():
			if type(section) is unicode:
				section = section.encode('utf-8')
			sections[section] = {}
			for (option, value) in self._configParser.items(section):
				if type(option) is unicode:
					option = option.encode('utf-8')
				if type(value) is unicode:
					value = value.encode('utf-8')
				sections[section][option] = value
			self._configParser.remove_section(section)
		
		sectionNames = sections.keys()
		sectionNames.sort()
		
		# Move section 'info' to first place
		if ( 'info' in sectionNames ):
			sectionNames.insert(0, sectionNames.pop(sectionNames.index('info')))
		
		for section in sectionNames:
			self._configParser.add_section(section)
			options = sections[section].keys()
			options.sort()
			for option in options:
				self._configParser.set(section, option, sections[section][option])
		
		data = StringIO.StringIO()
		self._configParser.write(data)
		self._lines = data.getvalue().decode('utf-8').replace('\r', '').split('\n')
		self.open('w')
		self.writelines()
		self.close()

class InfFile(ConfigFile):
	sectionRegex       = re.compile('\[\s*([^\]]+)\s*\]')
	pciDeviceRegex     = re.compile('VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)', re.IGNORECASE)
	hdaudioDeviceRegex = re.compile('HDAUDIO\\\.*VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)', re.IGNORECASE)
	usbDeviceRegex     = re.compile('USB.*VID_([\da-fA-F]+)&PID_([\da-fA-F]+)', re.IGNORECASE)
	acpiDeviceRegex    = re.compile('ACPI\\\(\S+)_-_(\S+)', re.IGNORECASE)
	varRegex           = re.compile('\%([^\%]+)\%')
	classRegex         = re.compile('class\s*=')
	
	def __init__(self, filename, lockFailTimeout = 2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars = [';', '#'])
		self._devices = []
	
	def getDevices(self):
		if not self._parsed:
			self.parse()
		return self._devices
	
	def isDeviceKnown(self, vendorId, deviceId, deviceType = None):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		if not self._parsed:
			self.parse()
		for d in self._devices:
			if (not deviceType or (d.get('type') == deviceType)) and (d.get('vendor') == vendorId) and (not d.get('device') or (d['device'] == deviceId)):
				return True
		return False
	
	def parse(self, lines=None):
		logger.debug(u"Parsing inf file %s" % self._filename)
		lines = ConfigFile.parse(self, lines)
		self._parsed = False
		self._devices = []
		
		path = os.path.dirname(self._filename)
		
		deviceClass = u'???'
		deviceSections = []
		appendNext = False
		newLines = []
		for line in lines:
			if appendNext:
				newLines[-1] = lines[-1][:-1] + line
			else:
				newLines.append(line)
			
			if line.endswith(u'\\'):
				appendNext = True
			else:
				appendNext = False
		lines = newLines
		
		# Get strings
		logger.debug(u"   - Getting strings")
		strings = {}
		section = u''
		for line in lines:
			match = re.search(self.sectionRegex, line)
			if match:
				if (section.lower() == u'strings'):
					break
				section = match.group(1)
			else:
				if (section.lower() == u'strings'):
					try:
						(var, string) = line.split(u'=', 1)
						string = string.strip()
						if string.startswith(u'"') and string.endswith(u'"'):
							string = string[1:-1]
						strings[var.strip().lower()] = string
					except:
						pass
		logger.debug2(u"        got strings: %s" % strings)
		
		# Get devices
		logger.debug(u"   - Getting devices")
		section = u''
		for line in lines:
			match = re.search(self.sectionRegex, line)
			if match:
				if (section.lower() == u'manufacturer'):
					break
				section = match.group(1)
			else:
				if (section.lower() == u'version'):
					if line.lower().startswith(u'class'):
						if re.search(self.classRegex, line.lower()):
							deviceClass = line.split('=')[1].strip().lower()
							match = re.search(self.varRegex, deviceClass)
							if match:
								var = match.group(1).lower()
								if strings.has_key(var):
									deviceClass = deviceClass.replace(u'%'+var+u'%', strings[var])
				
				elif (section.lower() == u'manufacturer'):
					if line and (line.find(u'=') != -1):
						for d in line.split(u'=')[1].split(u','):
							deviceSections.append(d.strip())
		
		devSections = []
		for deviceSection in deviceSections:
			for i in deviceSection.split('.'):
				if not i in devSections:
					devSections.append(i)
		deviceSections = devSections
		logger.debug(u"      - Device sections: %s" % ', '.join(deviceSections))
		
		def isDeviceSection(section):
			if section in deviceSections:
				return True
			for s in section.split(u'.'):
				if not s in deviceSections:
					return False
			return True
		
		found = []
		section = ''
		sectionsParsed = []
		for line in lines:
			try:
				match = re.search(self.sectionRegex, line)
				if match:
					if section and isDeviceSection(section):
						sectionsParsed.append(section)
					section = match.group(1)
					if isDeviceSection(section): logger.debug(u"   - Parsing device section: %s" % section)
				else:
					if isDeviceSection(section) and not section in sectionsParsed:
						try:
							if (line.find('=') == -1) or (line.find(',') == -1):
								continue
							devString = line.split(u'=')[1].split(u',')[1].strip()
							logger.debug(u"      - Processing device string: %s" % devString)
							type = ''
							match = re.search(self.hdaudioDeviceRegex, devString)
							if match:
								type = u'HDAUDIO'
							else:
								match = re.search(self.pciDeviceRegex, devString)
								if match:
									type = u'PCI'
								else:
									match = re.search(self.usbDeviceRegex, devString)
									if match:
										type = u'USB'
									else:
										match = re.search(self.acpiDeviceRegex, devString)
										if match:
											type = u'ACPI'
							if match:
								logger.debug(u"         - Device type is %s" % type)
								if (type == u'ACPI'):
									vendor = match.group(1)
									device = match.group(2)
								else:
									vendor = forceHardwareVendorId(match.group(1))
									device = forceHardwareDeviceId(match.group(2))
								if u"%s:%s" % (vendor, device) not in found:
									logger.debug(u"         - Found %s device: %s:%s" % (type, vendor, device))
									found.append(u"%s:%s:%s" % (type, vendor, device))
									self._devices.append( { 'path': path, 'class': deviceClass, 'vendor': vendor, 'device': device, 'type': type } )
						except IndexError:
							logger.warning(u"Skipping bad line '%s' in file %s" % (line, self._filename))
			except Exception, e:
				logger.error(u"Parse error in inf file '%s' line '%s': %s" % (self._filename, line, e))
		self._parsed = True


class PciidsFile(ConfigFile):
	
	def __init__(self, filename, lockFailTimeout = 2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars = [';', '#'], lstrip = False)
		self._devices = {}
		self._vendors = {}
		self._subDevices = {}
		
	def getVendor(self, vendorId):
		vendorId = forceHardwareVendorId(vendorId)
		if not self._parsed:
			self.parse()
		return self._vendors.get(vendorId, None)
	
	def getDevice(self, vendorId, deviceId):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		if not self._parsed:
			self.parse()
		return self._devices.get(vendorId, {}).get(deviceId, None)
	
	def getSubDevice(self, vendorId, deviceId, subVendorId, subDeviceId):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		subVendorId = forceHardwareVendorId(subVendorId)
		subDeviceId = forceHardwareDeviceId(subDeviceId)
		if not self._parsed:
			self.parse()
		return self._subDevices.get(vendorId, {}).get(deviceId, {}).get(subVendorId + ':' + subDeviceId, None)
	
	def parse(self, lines=None):
		logger.debug(u"Parsing ids file %s" % self._filename)
		
		lines = ConfigFile.parse(self, lines)
		self._parsed = False
		
		self._devices = {}
		self._vendors = {}
		self._subDevices = {}
		
		currentVendorId = None
		currentDeviceId = None
		for line in lines:
			try:
				if line.startswith(u'C '):
					# Start of list of known device classes, subclasses and programming interfaces
					break
				
				if line.startswith(u'\t'):
					if not currentVendorId or not self._devices.has_key(currentVendorId):
						raise Exception(u"Parse error in file '%s': %s" % (self._filename, line))
					if line.startswith(u'\t\t'):
						if not currentDeviceId or not self._subDevices.has_key(currentVendorId) or not self._subDevices[currentVendorId].has_key(currentDeviceId):
							raise Exception(u"Parse error in file '%s': %s" % (self._filename, line))
						(subVendorId, subDeviceId, subName) = line.lstrip().split(None, 2)
						subVendorId = forceHardwareVendorId(subVendorId)
						subDeviceId = forceHardwareDeviceId(subDeviceId)
						self._subDevices[currentVendorId][currentDeviceId][subVendorId + ':' + subDeviceId] = subName.strip()
					else:
						(deviceId, deviceName) = line.lstrip().split(None, 1)
						currentDeviceId = deviceId = forceHardwareDeviceId(deviceId)
						if not self._subDevices[vendorId].has_key(deviceId):
							self._subDevices[vendorId][deviceId] = {}
						self._devices[currentVendorId][deviceId] = deviceName.strip()
				else:
					(vendorId, vendorName) = line.split(None, 1)
					currentVendorId = vendorId = forceHardwareVendorId(vendorId)
					if not self._devices.has_key(vendorId):
						self._devices[vendorId] = {}
					if not self._subDevices.has_key(vendorId):
						self._subDevices[vendorId] = {}
					self._vendors[vendorId] = vendorName.strip()
			except Exception, e:
				logger.error(e)
		self._parsed = True

UsbidsFile = PciidsFile

class TxtSetupOemFile(ConfigFile):
	sectionRegex     = re.compile('\[\s*([^\]]+)\s*\]')
	pciDeviceRegex   = re.compile('VEN_([\da-fA-F]+)(&DEV_([\da-fA-F]+))?(\S*)\s*$')
	usbDeviceRegex   = re.compile('USB.*VID_([\da-fA-F]+)(&PID_([\da-fA-F]+))?(\S*)\s*$', re.IGNORECASE)
	filesRegex       = re.compile('^files\.(computer|display|keyboard|mouse|scsi)\.(.+)$', re.IGNORECASE)
	configsRegex     = re.compile('^config\.(.+)$', re.IGNORECASE)
	hardwareIdsRegex = re.compile('^hardwareids\.(computer|display|keyboard|mouse|scsi)\.(.+)$', re.IGNORECASE)
	dllEntryRegex    = re.compile('^(dll\s*\=\s*)(\S+.*)$', re.IGNORECASE)
	
	def __init__(self, filename, lockFailTimeout = 2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars = [';', '#'])
		self._devices = []
		self._files = []
		self._componentNames = []
		self._componentOptions = []
		self._defaultComponentIds = []
		self._serviceNames = []
		self._driverDisks = []
		self._configs = []
		
	def getDevices(self):
		if not self._parsed:
			self.parse()
		return self._devices
	
	def isDeviceKnown(self, vendorId, deviceId, deviceType = None):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		if not self._parsed:
			self.parse()
		for d in self._devices:
			if (not deviceType or (d.get('type') == deviceType)) and (d.get('vendor') == vendorId) and (not d.get('device') or (d['device'] == deviceId)):
				return True
		return False
	
	def getDevice(self, vendorId, deviceId, deviceType = None, architecture='x86'):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		architecture = forceArchitecture(architecture)
		
		if not self._parsed:
			self.parse()
		device = None
		for d in self._devices:
			if (not deviceType or (d.get('type') == deviceType)) and (d.get('vendor') == vendorId) and (not d.get('device') or d['device'] == deviceId):
				if (architecture == 'x86'):
					if (d['componentId'].lower().find('amd64') != -1) or (d['componentId'].lower().find('x64') != -1):
						logger.debug(u"Skipping device with component id '%s' which does not seem to match architecture '%s'" % (d['componentId'], architecture))
						continue
				elif (architecture == 'x64'):
					if (d['componentId'].lower().find('i386') != -1) or (d['componentId'].lower().find('x86') != -1):
						logger.debug(u"Skipping device with component id '%s' which does not seem to match architecture '%s'" % (d['componentId'], architecture))
						continue
				device = d
				break
		if not device:
			raise Exception(u"Device '%s:%s' not found in txtsetup.oem file '%s'" % (vendorId, deviceId, self._filename))
		return device
		
	def getFilesForDevice(self, vendorId, deviceId, deviceType = None, fileTypes = [], architecture='x86'):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		fileTypes = forceUnicodeLowerList(fileTypes)
		architecture = forceArchitecture(architecture)
		
		device = self.getDevice(vendorId = vendorId, deviceId = deviceId, deviceType = deviceType, architecture = architecture)
		
		files = []
		diskDriverDirs = {}
		for d in self._driverDisks:
			diskDriverDirs[d["diskName"]] = d["driverDir"]
		
		for f in self._files:
			if (f['componentName'] != device['componentName']) or (f['componentId'] != device['componentId']):
				continue
			if fileTypes and f['fileType'] not in fileTypes:
				continue
			if not diskDriverDirs.has_key(f['diskName']):
				raise Exception(u"Driver disk for file %s not found in txtsetup.oem file '%s'" % (f, self._filename))
			files.append(os.path.join(diskDriverDirs[f['diskName']], f['filename']))
		return files
	
	def getComponentOptionsForDevice(self, vendorId, deviceId, deviceType = None, architecture='x86'):
		vendorId = forceHardwareVendorId(vendorId)
		deviceId = forceHardwareDeviceId(deviceId)
		
		device = self.getDevice(vendorId = vendorId, deviceId = deviceId, deviceType = deviceType, architecture = architecture)
		
		for componentOptions in self._componentOptions:
			if (componentOptions['componentName'] == device['componentName']) and (componentOptions["componentId"] == device['componentId']):
				return componentOptions
		raise Exception(u"Component name '%s' not found in txtsetup.oem file '%s'" % (componentName, self._filename))
		
	def applyWorkarounds(self):
		if not self._parsed:
			self.parse()
		if not self._defaultComponentIds:
			# Missing default component will cause problems in windows textmode setup
			logger.info(u"No default component ids found, using '%s' as default component id" % self._componentOptions[0]['componentId'])
			self._defaultComponentIds.append({ 'componentName': self._componentOptions[0]['componentName'], 'componentId': self._componentOptions[0]['componentId'] })
		files = []
		for f in self._files:
			if (f['fileType'] == 'dll'):
				# dll entries will cause problems in windows textmode setup
				continue
			files.append(f)
		self._files = files
		
	def parse(self, lines=None):
		logger.debug(u"Parsing txtsetup.oem file %s" % self._filename)
		
		lines = ConfigFile.parse(self, lines)
		self._parsed = False
		
		self._devices = []
		self._files = []
		self._componentNames = []
		self._componentOptions = []
		self._defaultComponentIds = []
		self._serviceNames = []
		self._driverDisks = []
		self._configs = []
		
		sections = {}
		section = None
		for line in lines:
			logger.debug2(u"txtsetup.oem: %s" % line)
			match = re.search(self.sectionRegex, line)
			if match:
				section = match.group(1)
				sections[section] = []
			elif section:
				sections[section].append(line)
		
		# Search for component options
		logger.info(u"Searching for component names and options")
		for (section, lines) in sections.items():
			if not section.lower() in ('computer', 'display', 'keyboard', 'mouse', 'scsi'):
				continue
			componentName = section#.lower()
			for line in lines:
				if (line.find(u'=') == -1):
					continue
				optionName = None
				(componentId, value) = line.split('=', 1)
				componentId = componentId.strip()
				if (value.find(u',') != -1):
					(description, optionName) = value.split(',', 1)
					optionName = optionName.strip()
				else:
					description = value
				description = description.strip()
				if description.startswith(u'"') and description.endswith(u'"'):
					description = description[1:-1]
				if not componentName in self._componentNames:
					self._componentNames.append(componentName)
				self._componentOptions.append({"componentName": componentName, "description": description, "componentId": componentId, "optionName": optionName })
				
		logger.info(u"Component names found: %s" % self._componentNames)
		logger.info(u"Component options found: %s" % self._componentOptions)
		
		# Search for default component ids
		logger.info(u"Searching for default component ids")
		for (section, lines) in sections.items():
			if (section.lower() != 'defaults'):
				continue
			for line in lines:
				(componentName, componentId) = line.split('=', 1)
				self._defaultComponentIds.append({ 'componentName': componentName.strip(), 'componentId': componentId.strip() })
		
		if self._defaultComponentIds:
			logger.info(u"Found default component ids: %s" % self._defaultComponentIds)
		
		# Search for hardware ids
		logger.info(u"Searching for devices")
		for (section, lines) in sections.items():
			match = re.search(self.hardwareIdsRegex, section)
			if not match:
				continue
			componentName = match.group(1)
			componentId   = match.group(2)
			logger.info(u"Found hardwareIds section '%s', component name '%s', component id '%s'" % (section, componentName, componentId))
			found = []
			for line in lines:
				if not re.search('[iI][dD]\s*=', line):
					continue
				(device, serviceName) = line.split(u'=', 1)[1].strip().split(u',', 1)
				device = device.strip()
				if device.startswith(u'"') and device.endswith(u'"'):
					device = device[1:-1]
				serviceName = serviceName.strip()
				if serviceName.startswith(u'"') and serviceName.endswith(u'"'):
					serviceName = serviceName[1:-1]
				match = re.search(self.pciDeviceRegex, device)
				if match:
					type = u'PCI'
				else:
					match = re.search(self.usbDeviceRegex, device)
					if match:
						type = u'USB'
					else:
						logger.error(u"Parse error: =>%s<=" % device)
				if (type != u'PCI'):
					continue
				vendor = forceHardwareVendorId(match.group(1))
				device = None
				if match.group(3):
					device = forceHardwareDeviceId(match.group(3))
				extra = None
				if match.group(4):
					extra = forceUnicode(match.group(4))
				logger.debug(u"   Found %s device: %s:%s, service name: %s" % (type, vendor, device, serviceName))
				self._devices.append( { 'vendor': vendor, 'device': device, 'extra': extra, 'type': type, 'serviceName': serviceName, \
							'componentName': componentName, 'componentId': componentId } )
				if not serviceName in self._serviceNames:
					self._serviceNames.append(serviceName)
		
		if not self._devices:
			raise Exception(u"No devices found in txtsetup file '%s'" % self._filename)
		
		logger.info(u"Found services: %s" % self._serviceNames)
		logger.debug(u"Found devices: %s" % self._devices)
		
		# Search for disks
		logger.info(u"Searching for disks")
		for (section, lines) in sections.items():
			if (section.lower() != 'disks'):
				continue
			for line in lines:
				if (line.find(u'=') == -1):
					continue
				(diskName, value) = line.split('=', 1)
				diskName = diskName.strip()
				(desc, tf, dd) = value.split(',', 2)
				desc = desc.strip()
				if desc.startswith(u'"') and desc.endswith(u'"'):
					desc = desc[1:-1]
				tf = tf.strip()
				if tf.startswith(u'\\'): tf = tf[1:]
				dd = dd.strip()
				if dd.startswith(u'\\'): dd = dd[1:]
				self._driverDisks.append({"diskName": diskName, "description": desc, "tagfile": tf, "driverDir": dd })
		if not self._driverDisks:
			raise Exception(u"No driver disks found in txtsetup file '%s'" % self._filename)
		logger.info(u"Found driver disks: %s" % self._driverDisks)
		
		# Search for files
		logger.info(u"Searching for files")
		for (section, lines) in sections.items():
			match = re.search(self.filesRegex, section)
			if not match:
				continue
			componentName = match.group(1)#.lower()
			componentId   = match.group(2)
			logger.info(u"Found files section '%s', component name '%s', component id '%s'" % (section, componentName, componentId))
			for line in lines:
				(fileType, value) = line.split(u'=', 1)
				fileType = fileType.strip()
				parts = value.split(u',')
				diskName = parts[0].strip()
				filename = parts[1].strip()
				optionName = None
				if (len(parts) > 2):
					optionName = parts[2].strip()
				self._files.append({ 'fileType': fileType, 'diskName': diskName, 'filename': filename, 'componentName': componentName, 'componentId': componentId, 'optionName': optionName })
		logger.debug(u"Found files: %s" % self._files)
		
		
		# Search for configs
		logger.info(u"Searching for configs")
		for (section, lines) in sections.items():
			match = re.search(self.configsRegex, section)
			if not match:
				continue
			componentId   = match.group(1)
			logger.info(u"Found configs section '%s', component id '%s'" % (section, componentId))
			for line in lines:
				value = line.split(u'=', 1)[1]
				(keyName, valueName, valueType, value) = value.split(u',', 3)
				keyName = keyName.strip()
				valueName = valueName.strip()
				valueType = valueType.strip()
				value = value.strip()
				self._configs.append({ 'keyName': keyName.strip(), 'valueName': valueName.strip(), 'valueType': valueType.strip(), 'value': value.strip(), 'componentId': componentId })
		logger.debug(u"Found configs: %s" % self._configs)
		self._parsed = True
		
	def generate(self):
		lines = []
		lines.append(u'[Disks]\r\n')
		for disk in self._driverDisks:
			lines.append(u'%s = "%s", \\%s, \\%s\r\n' % (disk["diskName"], disk["description"], disk["tagfile"], disk["driverDir"]))
		lines.append(u'\r\n')
		lines.append(u'[Defaults]\r\n')
		for default in self._defaultComponentIds:
			lines.append(u'%s = %s\r\n' % (default["componentName"], default["componentId"]))
		
		for name in self._componentNames:
			lines.append(u'\r\n')
			lines.append(u'[%s]\r\n' % name)
			for options in self._componentOptions:
				if (options["componentName"] != name):
					continue
				line = u'%s = "%s"' % (options["componentId"], options["description"])
				if options["optionName"]:
					line += u', %s' % options["optionName"]
				lines.append(line + u'\r\n')
		
		for name in self._componentNames:
			for options in self._componentOptions:
				if (options["componentName"] != name):
					continue
				lines.append(u'\r\n')
				lines.append(u'[Files.%s.%s]\r\n' % (name, options["componentId"]))
				for f in self._files:
					if (f['componentName'] != name) or (f['componentId'] != options["componentId"]):
						continue
					line = u'%s = %s, %s' % (f['fileType'], f['diskName'], f['filename'])
					if f["optionName"]:
						line += u', %s' % f["optionName"]
					lines.append(line + u'\r\n')
		
		for name in self._componentNames:
			for options in self._componentOptions:
				if (options["componentName"] != name):
					continue
				lines.append(u'\r\n')
				lines.append(u'[HardwareIds.%s.%s]\r\n' % (name, options["componentId"]))
				for dev in self._devices:
					if (dev['componentName'] != name) or (dev['componentId'] != options["componentId"]):
						continue
					
					line = u'id = "%s\\VEN_%s' % (dev['type'], dev['vendor'])
					if dev['device']:
						line += u'&DEV_%s' % dev['device']
					if dev['extra']:
						line += dev['extra']
					if (dev['type'] == 'USB'):
						line = line.replace(u'VEN_', u'VID_').replace(u'DEV_', u'PID_')
					line += '", "%s"' % dev['serviceName']
					lines.append(line + u'\r\n')
		
		configComponents = {}
		for config in self._configs:
			if not configComponents.has_key(config['componentId']):
				configComponents[config['componentId']] = []
			configComponents[config['componentId']].append(config)
		for (componentId, configs) in configComponents.items():
			lines.append(u'\r\n')
			lines.append(u'[Config.%s]\r\n' % componentId)
			for conf in configs:
				lines.append(u'value = %s, %s, %s, %s\r\n' % (conf['keyName'], conf['valueName'], conf['valueType'], conf['value']))
		
		self._lines = lines
		self._fileHandle = codecs.open(self._filename, 'w', 'cp1250')
		self.writelines()
		self.close()






class DHCPDConf_Component(object):
	def __init__(self, startLine, parentBlock):
		self.startLine = startLine
		self.endLine = startLine
		self.parentBlock = parentBlock
	
	def getShifting(self):
		shifting = u''
		if not self.parentBlock:
			return shifting
		parentBlock = self.parentBlock.parentBlock
		while(parentBlock):
			shifting += u'\t'
			parentBlock = parentBlock.parentBlock
		return shifting
	
	def asText(self):
		return self.getShifting()
	
	def __unicode__(self):
		return u'<%s line %d-%d>' % (self.__class__.__name__, self.startLine, self.endLine)
	
	def __str__(self):
		return self.__unicode__().encode("ascii", "replace")
	
	def __repr__(self):
		return self.__str__()
	
class DHCPDConf_Parameter(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, key, value):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.key = key
		self.value = value
		if type(self.value) in (unicode, str):
			if self.value.lower() in [u'yes', u'true', u'on']:
				self.value = True
			elif self.value.lower() in [u'no', u'false', u'off']:
				self.value = False
	
	def asText(self):
		value = self.value
		if type(value) is bool:
			if value:
				value = u'on'
			else:
				value = u'off'
		elif self.key in [u'filename', u'ddns-domainname'] or \
		     re.match('.*[\'/\\\].*', value) or \
		     re.match('^\w+\.\w+$', value) or \
		     self.key.endswith(u'-name'):
			value = u'"%s"' % value
		return u"%s%s %s;" % (self.getShifting(), self.key, value)
	
	def asHash(self):
		return { self.key: self.value }
	
class DHCPDConf_Option(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, key, value):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.key = key
		self.value = value
		if not type(self.value) is list:
			self.value = [ self.value ]
	def asText(self):
		text = u"%soption %s " % (self.getShifting(), self.key)
		for i in range(len(self.value)):
			value = self.value[i]
			if re.match('.*[\'/\\\].*', value) or \
			   re.match('^\w+\.\w+$', value) or \
			   self.key.endswith(u'-name') or \
			   self.key.endswith(u'-domain') or \
			   self.key.endswith(u'-identifier'):
				value = u'"%s"' % value
			if (i+1 < len(self.value)):
				value += u', '
			text += value
		return text + u';'
	
	def asHash(self):
		return { self.key: self.value }
	
class DHCPDConf_Comment(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, data):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self._data = data
	
	def asText(self):
		return self.getShifting() + u'#%s' % self._data
	
class DHCPDConf_EmptyLine(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
	
class DHCPDConf_Block(DHCPDConf_Component):
	def __init__(self, startLine, parentBlock, type, settings = []):
		DHCPDConf_Component.__init__(self, startLine, parentBlock)
		self.type = type
		self.settings = settings
		self.lineRefs = {}
		self.components = []
		
	def getComponents(self):
		return self.components
	
	def removeComponents(self):
		logger.debug(u"Removing components: %s" % self.components)
		for c in forceList(self.components):
			self.removeComponent(c)
		
	def addComponent(self, component):
		self.components.append(component)
		if not self.lineRefs.has_key(component.startLine):
			self.lineRefs[component.startLine] = []
		self.lineRefs[component.startLine].append(component)
	
	def removeComponent(self, component):
		index = -1
		for i in range(len(self.components)):
			if (self.components[i] == component):
				index = i
				break
		if (index < 0):
			raise BackendMissingDataError(u"Component '%s' not found")
		del self.components[index]
		index = -1
		
		if self.lineRefs.has_key(component.startLine):
			for i in range(len(self.lineRefs[component.startLine])):
				if (self.lineRefs[component.startLine][i] == component):
					index = i
					break
		if (index >= 0):
			del self.lineRefs[component.startLine][index]
		
	def getOptions_hash(self, inherit = None):
		options = {}
		for component in self.components:
			if not isinstance(component, DHCPDConf_Option):
				continue
			options[component.key] = component.value
		
		if inherit and (self.type != inherit) and self.parentBlock:
			for (key, value) in self.parentBlock.getOptions_hash(inherit).items():
				if not options.has_key(key):
					options[key] = value
		return options
	
	def getOptions(self, inherit = None):
		options = []
		for component in self.components:
			if not isinstance(component, DHCPDConf_Option):
				continue
			options.append(component)
		
		if inherit and (self.type != inherit) and self.parentBlock:
			options.extend(self.parentBlock.getOptions(inherit))
		
		return options
	
	def getParameters_hash(self, inherit = None):
		parameters = {}
		for component in self.components:
			if not isinstance(component, DHCPDConf_Parameter):
				continue
			parameters[component.key] = component.value
		
		if inherit and (self.type != inherit) and self.parentBlock:
			for (key, value) in self.parentBlock.getParameters_hash(inherit).items():
				if not parameters.has_key(key):
					parameters[key] = value
		return parameters
	
	def getParameters(self, inherit = None):
		parameters = []
		for component in self.components:
			if not isinstance(component, DHCPDConf_Parameter):
				continue
			options.append(component)
		
		if inherit and (self.type != inherit) and self.parentBlock:
			parameters.extend(self.parentBlock.getParameters(inherit))
		
		return parameters
	
	def getBlocks(self, type, recursive = False):
		blocks = []
		for component in self.components:
			if not isinstance(component, DHCPDConf_Block):
				continue
			if (component.type == type):
				blocks.append(component)
			if recursive:
				blocks.extend(component.getBlocks(type, recursive))
		return blocks
	
	def asText(self):
		text = u''
		shifting = self.getShifting()
		if not isinstance(self, DHCPDConf_GlobalBlock):
			text += shifting + u' '.join(self.settings) + u' {\n'
		
		notWritten = self.components
		lineNumber = self.startLine
		if (lineNumber < 1): lineNumber = 1
		while (lineNumber <= self.endLine):
			if not self.lineRefs.has_key(lineNumber) or not self.lineRefs[lineNumber]:
				lineNumber += 1
				continue
			for i in range(len(self.lineRefs[lineNumber])):
				compText = self.lineRefs[lineNumber][i].asText()
				if (i > 0) and isinstance(self.lineRefs[lineNumber][i], DHCPDConf_Comment):
					compText = u' ' + compText.lstrip()
				text += compText
				# Mark component as written
				if self.lineRefs[lineNumber][i] in notWritten:
					notWritten.remove(self.lineRefs[lineNumber][i])
			text += u'\n'
			lineNumber += 1
		
		for component in notWritten:
			text += component.asText() + u'\n'
		
		if not isinstance(self, DHCPDConf_GlobalBlock):
			# Write '}' to close block
			text += shifting + u'}'
		
		return text
		
class DHCPDConf_GlobalBlock(DHCPDConf_Block):
	def __init__(self):
		DHCPDConf_Block.__init__(self, 1, None, u'global')

class DHCPDConfFile(TextFile):
	
	def __init__(self, filename, lockFailTimeout = 2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		
		self._currentLine = 0
		self._currentToken = None
		self._currentIndex = -1
		self._data = u''
		self._currentBlock = None
		self._globalBlock = None
		self._parsed = False
		
		logger.debug(u"Parsing dhcpd conf file '%s'" % self._filename)
	
	def getGlobalBlock(self):
		return self._globalBlock
		
	def parse(self, lines=None):
		self._currentLine = 0
		self._currentToken = None
		self._currentIndex = -1
		self._data = u''
		self._currentBlock = self._globalBlock = DHCPDConf_GlobalBlock()
		self._parsed = False
		
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._globalBlock.endLine = len(self._lines)
		
		minIndex = 0
		while True:
			self._currentToken = None
			self._currentIndex = -1
			if not self._data.strip():
				if not self._getNewData():
					break
				if not self._data.strip():
					self._parse_emptyline()
				continue
			for token in ('#', ';', '{', '}'):
				index = self._data.find(token)
				if (index != -1) and (index >= minIndex) and ((self._currentIndex == -1) or (index < self._currentIndex)):
					if (self._data[:index].count('"') % 2 == 1) or (self._data[:index].count("'") % 2 == 1):
						continue
					self._currentToken = token
					self._currentIndex = index
			if not self._currentToken:
				minIndex = len(self._data)
				if not self._getNewData():
					break
				continue
			minIndex = 0
			if   (self._currentToken == '#'):
				self._parse_comment()
			elif (self._currentToken == ';'):
				self._parse_semicolon()
			elif (self._currentToken == '{'):
				self._parse_lbracket()
			elif (self._currentToken == '}'):
				self._parse_rbracket()
		self._parsed = True
		
	def generate(self):
		if not self._globalBlock:
			raise Exception(u"Got no data to write")
		
		self.open('w')
		self.write(self._globalBlock.asText())
		self.close()
	
	def addHost(self, hostname, hardwareAddress, ipAddress, fixedAddress, parameters = {}):
		if not parameters: parameters = {}
		hostname        = forceHostname(hostname)
		hardwareAddress = forceHardwareAddress(hardwareAddress)
		ipAddress       = forceIPAddress(ipAddress)
		fixedAddress    = forceUnicodeLower(fixedAddress)
		parameters      = forceDict(parameters)
		
		if not self._parsed:
			self.parse()
		
		logger.notice(u"Creating host '%s', hardwareAddress '%s', ipAddress '%s', fixedAddress '%s', parameters '%s' in dhcpd config file '%s'" % \
					(hostname, hardwareAddress, ipAddress, fixedAddress, parameters, self._filename) )
		
		existingHost = None
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1].lower() == hostname):
				existingHost = block
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value.lower() == fixedAddress):
						raise BackendBadValueError(u"Host '%s' uses the same fixed address" % block.settings[1])
					elif (key == 'hardware') and (value.lower() == 'ethernet %s' % hardwareAddress):
						raise BackendBadValueError(u"Host '%s' uses the same hardware ethernet address" % block.settings[1])
		if existingHost:
			logger.info(u"Host '%s' already exists in config file '%s', deleting first" % (hostname, self._filename))
			self.deleteHost(hostname)
		
		for (key, value) in parameters.items():
			parameters[key] = DHCPDConf_Parameter(-1, None, key, value).asHash()[key]
		
		# Calculate bitmask of host's ipaddress
		n = ipAddress.split('.')
		for i in range(4):
			n[i] = forceInt(n[i])
		ip = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
		
		# Default parent block is global
		parentBlock = self._globalBlock
		
		# Search the right subnet block
		for block in self._globalBlock.getBlocks('subnet'):
			# Calculate bitmask of subnet
			n = (block.settings[1]).split('.')
			for i in range(4):
				n[i] = int(n[i])
			network = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
			n = (block.settings[3]).split('.')
			for i in range(4):
				n[i] = int(n[i])
			netmask = (n[0] << 24) + (n[1] << 16) + (n[2] << 8) + n[3]
			
			wildcard = netmask ^ 0xFFFFFFFFL
			if (wildcard | ip == wildcard | network):
				# Host matches the subnet
				logger.debug(u"Choosing subnet %s/%s for host %s" % (block.settings[1], block.settings[3], hostname))
				parentBlock = block
		
		# Search the right group for the host
		bestGroup = None
		bestMatchCount = 0
		for block in parentBlock.getBlocks('group'):
			matchCount = 0
			blockParameters = block.getParameters_hash(inherit = 'global')
			if blockParameters:
				# Block has parameters set, check if they match the hosts parameters
				for (key, value) in blockParameters.items():
					if not parameters.has_key(key):
						continue
					if (parameters[key] == value):
						matchCount += 1
					else:
						matchCount -= 1
			
			if (matchCount > bestMatchCount) or (matchCount >= 0 and not bestGroup):
				matchCount = bestMatchCount
				bestGroup = block
		
		if bestGroup:
			parentBlock = bestGroup
		
		# Remove parameters which are already defined in parents
		blockParameters = parentBlock.getParameters_hash(inherit = 'global')
		if blockParameters:
			for (key, value) in blockParameters.items():
				if parameters.has_key(key) and (parameters[key] == value):
					del parameters[key]
		
		hostBlock = DHCPDConf_Block(
					startLine = -1,
					parentBlock = parentBlock,
					type = 'host',
					settings = ['host', hostname] )
		hostBlock.addComponent( DHCPDConf_Parameter( startLine = -1, parentBlock = hostBlock, key = 'fixed-address', value = fixedAddress ) )
		hostBlock.addComponent( DHCPDConf_Parameter( startLine = -1, parentBlock = hostBlock, key = 'hardware', value = "ethernet %s" % hardwareAddress ) )
		for (key, value) in parameters.items():
			hostBlock.addComponent(
				DHCPDConf_Parameter( startLine = -1, parentBlock = hostBlock, key = key, value = value ) )
		
		parentBlock.addComponent(hostBlock)
		
	def getHost(self, hostname):
		hostname = forceHostname(hostname)
		
		if not self._parsed:
			self.parse()
		
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				return block.getParameters_hash()
		return None
		
	def deleteHost(self, hostname):
		hostname = forceHostname(hostname)
		
		if not self._parsed:
			self.parse()
		
		logger.notice(u"Deleting host '%s' from dhcpd config file '%s'" % (hostname, self._filename))
		hostBlocks = []
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				hostBlocks.append(block)
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value == hostname):
						hostBlocks.append(block)
		if not hostBlocks:
			logger.warning(u"Failed to remove host '%s': not found" % hostname)
			return
		
		for block in hostBlocks:
			block.parentBlock.removeComponent(block)
	
	def modifyHost(self, hostname, parameters):
		hostname   = forceHostname(hostname)
		parameters = forceDict(parameters)
		
		if not self._parsed:
			self.parse()
		
		logger.notice(u"Modifying host '%s' in dhcpd config file '%s'" % (hostname, self.filename))
		
		hostBlocks = []
		for block in self._globalBlock.getBlocks('host', recursive = True):
			if (block.settings[1] == hostname):
				hostBlocks.append(block)
			else:
				for (key, value) in block.getParameters_hash().items():
					if (key == 'fixed-address') and (value == hostname):
						hostBlocks.append(block)
					elif (key == 'hardware') and (value.lower() == parameters.get('hardware')):
						raise BackendBadValueError(u"Host '%s' uses the same hardware ethernet address" % block.settings[1])
		if (len(hostBlocks) != 1):
			raise BackendBadValueError(u"Host '%s' found %d times" % (hostname, len(hostBlocks)))
		
		hostBlock = hostBlocks[0]
		hostBlock.removeComponents()
		
		for (key, value) in parameters.items():
			parameters[key] = Parameter(-1, None, key, value).asHash()[key]
		
		for (key, value) in hostBlock.parentBlock.getParameters_hash(inherit = 'global').items():
			if not parameters.has_key(key):
				continue
			if (parameters[key] == value):
				del parameters[key]
		
		for (key, value) in parameters.items():
			hostBlock.addComponent(
				DHCPDConf_Parameter( startLine = -1, parentBlock = hostBlock, key = key, value = value ) )
		
	def _getNewData(self):
		if (self._currentLine >= len(self._lines)):
			return False
		self._data += self._lines[self._currentLine]
		self._currentLine += 1
		return True
	
	def _parse_emptyline(self):
		logger.debug(u"_parse_emptyline")
		self._currentBlock.addComponent(
			DHCPDConf_EmptyLine(
				startLine   = self._currentLine,
				parentBlock = self._currentBlock
			)
		)
		self._data = self._data[:self._currentIndex]
	
	def _parse_comment(self):
		logger.debug(u"_parse_comment")
		self._currentBlock.addComponent(
			DHCPDConf_Comment(
				startLine   = self._currentLine,
				parentBlock = self._currentBlock,
				data        = self._data.strip()[1:]
			)
		)
		self._data = self._data[:self._currentIndex]
		
	def _parse_semicolon(self):
		logger.debug(u"_parse_semicolon")
		data = self._data[:self._currentIndex]
		self._data = self._data[self._currentIndex+1:]
		
		key = data.split()[0]
		if (key != 'option'):
			# Parameter
			value = u' '.join(data.split()[1:]).strip()
			if (len(value) > 1) and value.startswith('"') and value.endswith('"'):
				value = value[1:-1]
			self._currentBlock.addComponent(
				DHCPDConf_Parameter(
					startLine   = self._currentLine,
					parentBlock = self._currentBlock,
					key         = key,
					value       = value
				)
			)
			return
		
		# Option
		key = data.split()[1]
		value = u' '.join(data.split()[2:]).strip()
		if (len(value) > 1) and value.startswith('"') and value.endswith('"'):
			value = value[1:-1]
		values  = []
		quote   = u''
		current = u''
		for l in value:
			if   (l == u'"'):
				if   (quote == u'"'):
					quote = u''
				elif (quote == u"'"):
					current += l
				else:
					quote = u'"'
			elif (l == u"'"):
				if   (quote == u"'"):
					quote = u''
				elif (quote == u'"'):
					current += l
				else:
					quote = u"'"
			elif re.search('\s', l):
				current += l
			elif (l == u','):
				if quote:
					current += l
				else:
					values.append(current.strip())
					current = u''
			else:
				current += l
		if current:
			values.append(current.strip())
		
		self._currentBlock.addComponent(
			DHCPDConf_Option(
				startLine   = self._currentLine,
				parentBlock = self._currentBlock,
				key         = key,
				value       = values
			)
		)
		
	def _parse_lbracket(self):
		logger.debug(u"_parse_lbracket")
		# Start of a block
		data = self._data[:self._currentIndex]
		self._data = self._data[self._currentIndex+1:]
		# Split the block definition at whitespace
		# The first value is the block type
		# Example: subnet 194.31.185.0 netmask 255.255.255.0 => type is subnet
		block = DHCPDConf_Block(
			startLine   = self._currentLine,
			parentBlock = self._currentBlock,
			type        = data.split()[0].strip(),
			settings    = data.split()
		)
		self._currentBlock.addComponent(block)
		self._currentBlock = block
		
	def _parse_rbracket(self):
		logger.debug(u"_parse_rbracket")
		# End of a block
		data = self._data[:self._currentIndex]
		self._data = self._data[self._currentIndex+1:]
		
		self._currentBlock.endLine = self._currentLine
		self._currentBlock = self._currentBlock.parentBlock
	
	
infTestData = [
'''
;-----------------------------------------------
;----------1002181718-8.593.100-100210a-095952E-ATI
;-----------------------------------------------
; ATI Display Information file : ATIIXPAG.INF
; Installation INF for the ATI display driver.
; Copyright(C) 1998-2004 ATI Technologies Inc.
; Windows XP
; Base INF Last Updated 2005/11/01

[Version]
Signature="$Windows NT$"
Provider=%ATI%
ClassGUID={4D36E968-E325-11CE-BFC1-08002BE10318}
Class=Display
DriverVer=02/10/2010, 8.593.100.0000
CatalogFile=CX_95952.CAT

[DestinationDirs]
DefaultDestDir      = 11
ati2mtag.OGL        = 10  ;Windows
ati2mtag.Miniport   = 12  ; drivers
ati2mtag.Display    = 11  ; system32
ati2mtag.OD	    = 11  ; system32

[ControlFlags]
ExcludeFromSelect=*
;
; Driver information
;

[Manufacturer]
%ATI% = ATI.Mfg, NTx86

[ATI.Mfg.NTx86]
"ATI Radeon X1050" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001002
"ATI Radeon X1050 " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001002
"ATI Radeon X1050  " = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001002
"ATI Radeon X1050   " = ati2mtag_RV360, PCI\VEN_1002&DEV_4152&SUBSYS_30001002
"ATI Radeon X1050 Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011002
"ATI Radeon X1050 Secondary " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011002
"ATI Radeon X1050 Secondary  " = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011002
"ATI Radeon X1050 Secondary   " = ati2mtag_RV360, PCI\VEN_1002&DEV_4172&SUBSYS_30011002
"ATI Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001002
"ATI Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001002
"ATI Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011002
"ATI Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011002
"ATI Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001002
"ATI Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001002
"ATI Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011002
"ATI Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011002
"Radeon X1800 CrossFire Edition" = ati2mtag_R520, PCI\VEN_1002&DEV_7109&SUBSYS_0D021002
"Radeon X1800 CrossFire Edition Secondary" = ati2mtag_R520, PCI\VEN_1002&DEV_7129&SUBSYS_0D031002
"Radeon X1900 CrossFire Edition" = ati2mtag_R580, PCI\VEN_1002&DEV_7249&SUBSYS_0D021002
"Radeon X1900 CrossFire Edition Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_7269&SUBSYS_0D031002
"Radeon X1950 CrossFire Edition" = ati2mtag_R580, PCI\VEN_1002&DEV_7240&SUBSYS_0D021002
"Radeon X1950 CrossFire Edition Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_7260&SUBSYS_0D031002
"Radeon X800 CrossFire Edition" = ati2mtag_R430, PCI\VEN_1002&DEV_554D&SUBSYS_0D021002
"Radeon X800 CrossFire Edition Secondary" = ati2mtag_R430, PCI\VEN_1002&DEV_556D&SUBSYS_0D031002
"RADEON X850 CrossFire Edition" = ati2mtag_R480, PCI\VEN_1002&DEV_5D52&SUBSYS_0D021002
"RADEON X850 CrossFire Edition Secondary" = ati2mtag_R480, PCI\VEN_1002&DEV_5D72&SUBSYS_0D031002
"ATI RADEON XPRESS 1100 Series" = ati2mtag_RC410, PCI\VEN_1002&DEV_5A61&SUBSYS_2A4B103C
"Asus Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001043
"Asus Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011043
"ASUS Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001043
"ASUS Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001043
"ASUS Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011043
"ASUS Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011043
"ASUS Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001043
"ASUS Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001043
"ASUS Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011043
"ASUS Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011043
"ASUS X550 Series" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_31001043
"ASUS X550 Series Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_31011043
"ATI Radeon X1050    " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001043
"ATI Radeon X1050     " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001043
"ATI Radeon X1050 Secondary    " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011043
"ATI Radeon X1050 Secondary     " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011043
"RADEON X800 GTO" = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_01381043
"RADEON X800 GTO Secondary" = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_01391043
"Diamond Radeon X1050" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001092
"Diamond Radeon X1050 " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001092
"Diamond Radeon X1050  " = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001092
"Diamond Radeon X1050 Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011092
"Diamond Radeon X1050 Secondary " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011092
"Diamond Radeon X1050 Secondary  " = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011092
"Diamond Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001092
"Diamond Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001092
"Diamond Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011092
"Diamond Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011092
"Diamond Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001092
"Diamond Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001092
"Diamond Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011092
"Diamond Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011092
"ATI Radeon X1050      " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001458
"ATI Radeon X1050       " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001458
"ATI Radeon X1050 Secondary      " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011458
"ATI Radeon X1050 Secondary       " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011458
"GigaByte Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001458
"GigaByte Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011458
"GIGABYTE Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001458
"GIGABYTE Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001458
"GIGABYTE Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011458
"GIGABYTE Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011458
"GIGABYTE Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001458
"GIGABYTE Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001458
"GIGABYTE Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011458
"GIGABYTE Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011458
"RADEON X800 GTO " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_21361458
"RADEON X800 GTO Secondary " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_21371458
"ATI Radeon X1050        " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001462
"ATI Radeon X1050         " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001462
"ATI Radeon X1050 Secondary        " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011462
"ATI Radeon X1050 Secondary         " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011462
"MSI Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001462
"MSI Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011462
"MSI Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001462
"MSI Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001462
"MSI Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011462
"MSI Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011462
"MSI Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001462
"MSI Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001462
"MSI Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011462
"MSI Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011462
"RADEON X800 GTO  " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_09721462
"RADEON X800 GTO Secondary  " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_09731462
"ABIT Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_3000147B
"ABIT Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_3001147B
"ABIT Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_3001147B
"ABIT Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_3000147B
"ABIT Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_3000147B
"ABIT Radeon X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_3000147B
"ABIT Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_3001147B
"ABIT Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_3001147B
"ATI Radeon X1050          " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_3000147B
"ATI Radeon X1050           " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_3000147B
"ATI Radeon X1050 Secondary          " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_3001147B
"ATI Radeon X1050 Secondary           " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_3001147B
"ATI Radeon X1050            " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_3000148C
"ATI Radeon X1050             " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_3000148C
"ATI Radeon X1050 Secondary            " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_3001148C
"ATI Radeon X1050 Secondary             " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_3001148C
"PowerColor Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_3000148C
"PowerColor Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_3001148C
"PowerColor Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_3000148C
"PowerColor Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_3000148C
"PowerColor Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_3001148C
"PowerColor Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_3001148C
"PowerColor Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_3000148C
"PowerColor Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_3000148C
"PowerColor Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_3001148C
"PowerColor Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_3001148C
"Radeon X700 Series" = ati2mtag_RV410, PCI\VEN_1002&DEV_564F&SUBSYS_148C148C
"Radeon X700 Series Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_566F&SUBSYS_148D148C
"RADEON X800 GTO   " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_2160148C
"RADEON X800 GTO    " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_2160148C
"RADEON X800 GTO     " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_2160148C
"RADEON X800 GTO Secondary   " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_2161148C
"RADEON X800 GTO Secondary    " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_2161148C
"RADEON X800 GTO Secondary     " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_2161148C
"VisionTek Radeon X1050" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001545
"VisionTek Radeon X1050 " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001545
"VisionTek Radeon X1050  " = ati2mtag_RV360, PCI\VEN_1002&DEV_4152&SUBSYS_30001545
"VisionTek Radeon X1050 AGP" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001545
"VisionTek Radeon X1050 AGP Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011545
"VisionTek Radeon X1050 Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011545
"VisionTek Radeon X1050 Secondary " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011545
"VisionTek Radeon X1050 Secondary  " = ati2mtag_RV360, PCI\VEN_1002&DEV_4172&SUBSYS_30011545
"VisionTek Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001545
"VisionTek Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001545
"VisionTek Radeon X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001545
"VisionTek Radeon X1550 Series   " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001545
"VisionTek Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011545
"VisionTek Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011545
"VisionTek Radeon X1550 Series Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011545
"VisionTek Radeon X1550 Series Secondary   " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011545
"ATI Radeon X1050              " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001569
"ATI Radeon X1050               " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001569
"ATI Radeon X1050 Secondary              " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011569
"ATI Radeon X1050 Secondary               " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011569
"Palit Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001569
"Palit Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011569
"PALIT Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001569
"PALIT Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001569
"PALIT Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011569
"PALIT Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011569
"PALIT Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001569
"PALIT Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001569
"PALIT Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011569
"PALIT Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011569
"RADEON X550 Series" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4F&SUBSYS_5E4F1569
"RADEON X550 Series Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6F&SUBSYS_5E501569
"RADEON X550XT" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4F&SUBSYS_1E4F1569
"RADEON X550XT Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6F&SUBSYS_1E4E1569
"ATI Radeon X1050                " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_3000174B
"ATI Radeon X1050                 " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_3000174B
"ATI Radeon X1050 Secondary                " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_3001174B
"ATI Radeon X1050 Secondary                 " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_3001174B
"Radeon X1050" = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_3490174B
"Radeon X1050 " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_3500174B
"Radeon X1050 Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_3491174B
"Radeon X1050 Secondary " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_3501174B
"Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_5920174B
"Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_5940174B
"Radeon X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_5940174B
"Radeon X1550 Series   " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_5920174B
"Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_5921174B
"Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_5941174B
"Radeon X1550 Series Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_5941174B
"Radeon X1550 Series Secondary   " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_5921174B
"Radeon X1650 GTO" = ati2mtag_RV530, PCI\VEN_1002&DEV_71C0&SUBSYS_E160174B
"Radeon X1650 GTO Secondary" = ati2mtag_RV530, PCI\VEN_1002&DEV_71E0&SUBSYS_E161174B
"Radeon X1650 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7181&SUBSYS_5920174B
"Radeon X1650 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_71A1&SUBSYS_5921174B
"Radeon X550XTX" = ati2mtag_M26, PCI\VEN_1002&DEV_564F&SUBSYS_0490174B
"Radeon X550XTX " = ati2mtag_M26, PCI\VEN_1002&DEV_564F&SUBSYS_0500174B
"Radeon X550XTX  " = ati2mtag_M26, PCI\VEN_1002&DEV_564F&SUBSYS_0580174B
"Radeon X550XTX   " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0530174B
"Radeon X550XTX    " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0800174B
"Radeon X550XTX     " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0490174B
"Radeon X550XTX      " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0580174B
"Radeon X550XTX       " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0500174B
"Radeon X550XTX        " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_0750174B
"Radeon X550XTX Secondary   " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0531174B
"Radeon X550XTX Secondary    " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0801174B
"Radeon X550XTX Secondary     " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0491174B
"Radeon X550XTX Secondary      " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0581174B
"Radeon X550XTX Secondary       " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0501174B
"Radeon X550XTX Secondary        " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_0751174B
"RADEON X800 GTO      " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_1590174B
"RADEON X800 GTO       " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_1590174B
"RADEON X800 GTO        " = ati2mtag_R420, PCI\VEN_1002&DEV_4A49&SUBSYS_2620174B
"RADEON X800 GTO         " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_1600174B
"RADEON X800 GTO          " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_1600174B
"RADEON X800 GTO           " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_1600174B
"RADEON X800 GTO Secondary      " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_1591174B
"RADEON X800 GTO Secondary       " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_1591174B
"RADEON X800 GTO Secondary        " = ati2mtag_R420, PCI\VEN_1002&DEV_4A69&SUBSYS_2621174B
"RADEON X800 GTO Secondary         " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_1601174B
"RADEON X800 GTO Secondary          " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_1601174B
"RADEON X800 GTO Secondary           " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_1601174B
"RADEON X800GT" = ati2mtag_R420, PCI\VEN_1002&DEV_4A4A&SUBSYS_2610174B
"RADEON X800GT Secondary" = ati2mtag_R420, PCI\VEN_1002&DEV_4A6A&SUBSYS_2611174B
"Sapphire Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_3000174B
"Sapphire Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_3001174B
"SAPPHIRE Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_3000174B
"SAPPHIRE Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_3000174B
"SAPPHIRE Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_3001174B
"SAPPHIRE Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_3001174B
"SAPPHIRE Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_3000174B
"SAPPHIRE Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_3000174B
"SAPPHIRE Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_3001174B
"SAPPHIRE Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_3001174B
"ATI Radeon X1050                  " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_30001787
"ATI Radeon X1050                   " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_30001787
"ATI Radeon X1050                    " = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_30001787
"ATI Radeon X1050 Secondary                  " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_30011787
"ATI Radeon X1050 Secondary                   " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_30011787
"ATI Radeon X1050 Secondary                    " = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_30011787
"ATI Radeon X1300/X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7143&SUBSYS_30001787
"ATI Radeon X1300/X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7163&SUBSYS_30011787
"ATI Radeon X1550  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_30001787
"ATI Radeon X1550   " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_30001787
"ATI Radeon X1550 Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_30011787
"ATI Radeon X1550 Secondary   " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_30011787
"ATI Radeon X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_30001787
"ATI Radeon X1550 Series   " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_30001787
"ATI Radeon X1550 Series Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_30011787
"ATI Radeon X1550 Series Secondary   " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_30011787
"Radeon X1550 Series    " = ati2mtag_RV515, PCI\VEN_1002&DEV_7140&SUBSYS_30001787
"Radeon X1550 Series Secondary    " = ati2mtag_RV515, PCI\VEN_1002&DEV_7160&SUBSYS_30011787
"RADEON X550XT " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4F&SUBSYS_1E4F1787
"RADEON X550XT Secondary " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6F&SUBSYS_1E4E1787
"RADEON X700 Series " = ati2mtag_RV410, PCI\VEN_1002&DEV_5657&SUBSYS_06571787
"RADEON X700 Series Secondary " = ati2mtag_RV410, PCI\VEN_1002&DEV_5677&SUBSYS_06561787
"RADEON X800 GTO            " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_15491787
"RADEON X800 GTO             " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_154F1787
"RADEON X800 GTO              " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_1D4F1787
"RADEON X800 GTO Secondary            " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_154A1787
"RADEON X800 GTO Secondary             " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_15501787
"RADEON X800 GTO Secondary              " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_1D501787
"RADEON X800 GTO Secondary               " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_15481787
"RADEON X800 GTO Secondary                " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_15501787
"RADEON X800 GTO Secondary                 " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_154E1787
"RADEON X800 GTO Secondary                  " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_1D4E1787
"ATI RADEON 9600/X1050 Series" = ati2mtag_RV350, PCI\VEN_1002&DEV_4150&SUBSYS_300017AF
"ATI RADEON 9600/X1050 Series Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4170&SUBSYS_300117AF
"ATI Radeon X1050                     " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_300017AF
"ATI Radeon X1050                      " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_300017AF
"ATI Radeon X1050 Secondary                     " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_300117AF
"ATI Radeon X1050 Secondary                      " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_300117AF
"ATI Radeon X1050 Series" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_201E17AF
"ATI Radeon X1050 Series Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_201F17AF
"ATI Radeon X1300/X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7143&SUBSYS_300017AF
"ATI Radeon X1300/X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_7163&SUBSYS_300117AF
"HIS Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_300017AF
"HIS Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_300117AF
"HIS Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_300017AF
"HIS Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_300017AF
"HIS Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_300117AF
"HIS Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_300117AF
"HIS Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_300017AF
"HIS Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_300017AF
"HIS Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_300117AF
"HIS Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_300117AF
"RADEON X800 GTO               " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_204617AF
"RADEON X800 GTO                " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_204617AF
"RADEON X800 GTO                 " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_204617AF
"RADEON X800 GTO Secondary                   " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_204717AF
"RADEON X800 GTO Secondary                    " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_204717AF
"RADEON X800 GTO Secondary                     " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_204717AF
"ATI Radeon X1050                       " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_300017EE
"ATI Radeon X1050                        " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_300017EE
"ATI Radeon X1050 Secondary                       " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_300117EE
"ATI Radeon X1050 Secondary                        " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_300117EE
"Connect3D Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_300017EE
"Connect3D Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_300117EE
"Connect3D Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_300017EE
"Connect3D Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_300017EE
"Connect3D Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_300117EE
"Connect3D Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_300117EE
"Connect3D Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_300017EE
"Connect3D Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_300017EE
"Connect3D Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_300117EE
"Connect3D Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_300117EE
"ATI Radeon X1050                         " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63&SUBSYS_300018BC
"ATI Radeon X1050                          " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60&SUBSYS_300018BC
"ATI Radeon X1050 Secondary                         " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73&SUBSYS_300118BC
"ATI Radeon X1050 Secondary                          " = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70&SUBSYS_300118BC
"GECUBE Radeon X1050" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153&SUBSYS_300018BC
"GECUBE Radeon X1050 Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173&SUBSYS_300118BC
"GeCube Radeon X1550" = ati2mtag_RV515, PCI\VEN_1002&DEV_7142&SUBSYS_300018BC
"GeCube Radeon X1550 " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183&SUBSYS_300018BC
"GeCube Radeon X1550 Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7162&SUBSYS_300118BC
"GeCube Radeon X1550 Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3&SUBSYS_300118BC
"GeCube Radeon X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146&SUBSYS_300018BC
"GeCube Radeon X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187&SUBSYS_300018BC
"GeCube Radeon X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166&SUBSYS_300118BC
"GeCube Radeon X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7&SUBSYS_300118BC
"RADEON X800 GTO                  " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_145018BC
"RADEON X800 GTO                   " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_145218BC
"RADEON X800 GTO                    " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_149018BC
"RADEON X800 GTO                     " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_149218BC
"RADEON X800 GTO                      " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_153018BC
"RADEON X800 GTO                       " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_153218BC
"RADEON X800 GTO                        " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_157018BC
"RADEON X800 GTO                         " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_157218BC
"RADEON X800 GTO                          " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_161018BC
"RADEON X800 GTO                           " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_161218BC
"RADEON X800 GTO                            " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_165018BC
"RADEON X800 GTO                             " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_165218BC
"RADEON X800 GTO Secondary                      " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_145118BC
"RADEON X800 GTO Secondary                       " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_145318BC
"RADEON X800 GTO Secondary                        " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_149118BC
"RADEON X800 GTO Secondary                         " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_149318BC
"RADEON X800 GTO Secondary                          " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_153118BC
"RADEON X800 GTO Secondary                           " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_153318BC
"RADEON X800 GTO Secondary                            " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_157118BC
"RADEON X800 GTO Secondary                             " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_157318BC
"RADEON X800 GTO Secondary                              " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_161118BC
"RADEON X800 GTO Secondary                               " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_161318BC
"RADEON X800 GTO Secondary                                " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_165118BC
"RADEON X800 GTO Secondary                                 " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_165318BC
"RADEON X800 GTO                              " = ati2mtag_R423, PCI\VEN_1002&DEV_5549&SUBSYS_1089196D
"RADEON X800 GTO                               " = ati2mtag_R430, PCI\VEN_1002&DEV_554F&SUBSYS_1089196D
"RADEON X800 GTO                                " = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F&SUBSYS_1089196D
"RADEON X800 GTO Secondary                                  " = ati2mtag_R423, PCI\VEN_1002&DEV_5569&SUBSYS_1088196D
"RADEON X800 GTO Secondary                                   " = ati2mtag_R430, PCI\VEN_1002&DEV_556F&SUBSYS_1088196D
"RADEON X800 GTO Secondary                                    " = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F&SUBSYS_1088196D
"ATI MOBILITY RADEON XPRESS 200" = ati2mtag_RS480M, PCI\VEN_1002&DEV_5955
"ATI Radeon 2100" = ati2mtag_RS690, PCI\VEN_1002&DEV_796E
"ATI Radeon 9550 / X1050 Series" = ati2mtag_RV350, PCI\VEN_1002&DEV_4153
"ATI Radeon 9550 / X1050 Series Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4173
"ATI Radeon 9600 / X1050 Series" = ati2mtag_RV360, PCI\VEN_1002&DEV_4152
"ATI Radeon 9600 / X1050 Series Secondary" = ati2mtag_RV360, PCI\VEN_1002&DEV_4172
"ATI Radeon 9600/9550/X1050 Series" = ati2mtag_RV350, PCI\VEN_1002&DEV_4150
"ATI Radeon 9600/9550/X1050 Series " = ati2mtag_RV350, PCI\VEN_1002&DEV_4E51
"ATI Radeon 9600/9550/X1050 Series - Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4170
"ATI Radeon 9600/9550/X1050 Series Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4E71
"ATI Radeon X1200 Series" = ati2mtag_RS690, PCI\VEN_1002&DEV_791E
"ATI Radeon X1200 Series " = ati2mtag_RS690M, PCI\VEN_1002&DEV_791F
"ATI Radeon X1300 Series" = ati2mtag_RV515PCI, PCI\VEN_1002&DEV_714E
"ATI Radeon X1300 Series " = ati2mtag_RV515PCI, PCI\VEN_1002&DEV_718F
"ATI Radeon X1300/X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7143
"ATI Radeon X1300/X1550 Series Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7163
"ATI Radeon X1650 Series" = ati2mtag_R580, PCI\VEN_1002&DEV_7293
"ATI Radeon X1650 Series Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_72B3
"ATI Radeon X1950 GT" = ati2mtag_R580, PCI\VEN_1002&DEV_7288
"ATI Radeon X1950 GT Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_72A8
"ATI Radeon X300/X550/X1050 Series" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B60
"ATI Radeon X300/X550/X1050 Series " = ati2mtag_RV380x, PCI\VEN_1002&DEV_5B62
"ATI Radeon X300/X550/X1050 Series Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B70
"ATI Radeon X300/X550/X1050 Series Secondary " = ati2mtag_RV380x, PCI\VEN_1002&DEV_5B72
"ATI Radeon Xpress 1150" = ati2mtag_RS482, PCI\VEN_1002&DEV_5974
"ATI Radeon Xpress 1150 Secondary" = ati2mtag_RS482, PCI\VEN_1002&DEV_5874
"ATI Radeon Xpress 1200 Series" = ati2mtag_RS600, PCI\VEN_1002&DEV_7941
"ATI Radeon Xpress 1200 Series " = ati2mtag_RS600, PCI\VEN_1002&DEV_793F
"ATI RADEON XPRESS 200 Series" = ati2mtag_RC410, PCI\VEN_1002&DEV_5A61
"ATI RADEON XPRESS 200 Series " = ati2mtag_RS400, PCI\VEN_1002&DEV_5A41
"ATI RADEON XPRESS 200 Series  " = ati2mtag_RS480, PCI\VEN_1002&DEV_5954
"ATI RADEON XPRESS 200 Series Secondary" = ati2mtag_RS400, PCI\VEN_1002&DEV_5A43
"ATI RADEON XPRESS 200 Series Secondary " = ati2mtag_RS480, PCI\VEN_1002&DEV_5854
"ATI RADEON XPRESS 200 Series Secondary  " = ati2mtag_RC410, PCI\VEN_1002&DEV_5A63
"Radeon  X1300XT/X1600Pro/X1650 Series" = ati2mtag_RV530, PCI\VEN_1002&DEV_71CE
"RADEON 9500" = ati2mtag_R300, PCI\VEN_1002&DEV_4144
"RADEON 9500 - Secondary" = ati2mtag_R300, PCI\VEN_1002&DEV_4164
"RADEON 9500 PRO / 9700" = ati2mtag_R300, PCI\VEN_1002&DEV_4E45
"RADEON 9500 PRO / 9700 - Secondary" = ati2mtag_R300, PCI\VEN_1002&DEV_4E65
"RADEON 9600 SERIES" = ati2mtag_RV350, PCI\VEN_1002&DEV_4151
"RADEON 9600 Series " = ati2mtag_RV350, PCI\VEN_1002&DEV_4155
"RADEON 9600 SERIES - Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4171
"RADEON 9600 Series Secondary" = ati2mtag_RV350, PCI\VEN_1002&DEV_4175
"RADEON 9600 TX" = ati2mtag_R300, PCI\VEN_1002&DEV_4E46
"RADEON 9600 TX - Secondary" = ati2mtag_R300, PCI\VEN_1002&DEV_4E66
"RADEON 9700 PRO" = ati2mtag_R300, PCI\VEN_1002&DEV_4E44
"RADEON 9700 PRO - Secondary" = ati2mtag_R300, PCI\VEN_1002&DEV_4E64
"RADEON 9800" = ati2mtag_R350, PCI\VEN_1002&DEV_4E49
"RADEON 9800 - Secondary" = ati2mtag_R350, PCI\VEN_1002&DEV_4E69
"RADEON 9800 PRO" = ati2mtag_R350, PCI\VEN_1002&DEV_4E48
"RADEON 9800 PRO - Secondary" = ati2mtag_R350, PCI\VEN_1002&DEV_4E68
"RADEON 9800 SERIES" = ati2mtag_R350, PCI\VEN_1002&DEV_4148
"RADEON 9800 SERIES - Secondary" = ati2mtag_R350, PCI\VEN_1002&DEV_4168
"RADEON 9800 XT" = ati2mtag_R360, PCI\VEN_1002&DEV_4E4A
"RADEON 9800 XT - Secondary" = ati2mtag_R360, PCI\VEN_1002&DEV_4E6A
"Radeon X1300 / X1600 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7140
"Radeon X1300 / X1600 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7160
"Radeon X1300 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_714D
"Radeon X1300 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_716D
"Radeon X1300/X1550 Series" = ati2mtag_RV515, PCI\VEN_1002&DEV_7146
"Radeon X1300/X1550 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7142
"Radeon X1300/X1550 Series  " = ati2mtag_RV515, PCI\VEN_1002&DEV_7183
"Radeon X1300/X1550 Series   " = ati2mtag_RV515, PCI\VEN_1002&DEV_7187
"Radeon X1300/X1550 Series Secondary" = ati2mtag_RV515, PCI\VEN_1002&DEV_7166
"Radeon X1300/X1550 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_7162
"Radeon X1300/X1550 Series Secondary  " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A3
"Radeon X1300/X1550 Series Secondary   " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A7
"Radeon X1300XT/X1600Pro/X1650 Series Secondary" = ati2mtag_RV530, PCI\VEN_1002&DEV_71EE
"Radeon X1550 Series     " = ati2mtag_RV515, PCI\VEN_1002&DEV_7147
"Radeon X1550 Series      " = ati2mtag_RV515, PCI\VEN_1002&DEV_715F
"Radeon X1550 Series       " = ati2mtag_RV515, PCI\VEN_1002&DEV_7193
"Radeon X1550 Series        " = ati2mtag_RV515, PCI\VEN_1002&DEV_719F
"Radeon X1550 Series Secondary     " = ati2mtag_RV515, PCI\VEN_1002&DEV_7167
"Radeon X1550 Series Secondary      " = ati2mtag_RV515, PCI\VEN_1002&DEV_717F
"Radeon X1550 Series Secondary       " = ati2mtag_RV515, PCI\VEN_1002&DEV_71B3
"Radeon X1600 Series" = ati2mtag_RV530, PCI\VEN_1002&DEV_71C0
"Radeon X1600 Series " = ati2mtag_RV515, PCI\VEN_1002&DEV_7181
"Radeon X1600 Series Secondary" = ati2mtag_RV530, PCI\VEN_1002&DEV_71E0
"Radeon X1600 Series Secondary " = ati2mtag_RV515, PCI\VEN_1002&DEV_71A1
"Radeon X1600/1650 Series" = ati2mtag_RV535, PCI\VEN_1002&DEV_71C3
"Radeon X1600/1650 Series Secondary" = ati2mtag_RV530, PCI\VEN_1002&DEV_71E2
"Radeon X1600/1650 Series Secondary " = ati2mtag_RV535, PCI\VEN_1002&DEV_71E3
"Radeon X1600/X1650 Series" = ati2mtag_RV530, PCI\VEN_1002&DEV_71CD
"Radeon X1600/X1650 Series " = ati2mtag_RV530, PCI\VEN_1002&DEV_71C2
"Radeon X1600/X1650 Series Secondary" = ati2mtag_RV530, PCI\VEN_1002&DEV_71ED
"Radeon X1650 Series " = ati2mtag_RV530, PCI\VEN_1002&DEV_71C6
"Radeon X1650 Series  " = ati2mtag_RV535, PCI\VEN_1002&DEV_71C1
"Radeon X1650 Series   " = ati2mtag_R580, PCI\VEN_1002&DEV_7291
"Radeon X1650 Series    " = ati2mtag_RV535, PCI\VEN_1002&DEV_71C7
"Radeon X1650 Series Secondary " = ati2mtag_RV530, PCI\VEN_1002&DEV_71E6
"Radeon X1650 Series Secondary  " = ati2mtag_RV535, PCI\VEN_1002&DEV_71E1
"Radeon X1650 Series Secondary   " = ati2mtag_R580, PCI\VEN_1002&DEV_72B1
"Radeon X1650 Series Secondary    " = ati2mtag_RV535, PCI\VEN_1002&DEV_71E7
"Radeon X1800 GTO" = ati2mtag_R520, PCI\VEN_1002&DEV_710A
"Radeon X1800 GTO Secondary" = ati2mtag_R520, PCI\VEN_1002&DEV_712A
"Radeon X1800 Series" = ati2mtag_R520, PCI\VEN_1002&DEV_7100
"Radeon X1800 Series " = ati2mtag_R520, PCI\VEN_1002&DEV_7109
"Radeon X1800 Series Secondary" = ati2mtag_R520, PCI\VEN_1002&DEV_7120
"Radeon X1800 Series Secondary " = ati2mtag_R520, PCI\VEN_1002&DEV_7129
"Radeon X1900 GT" = ati2mtag_R580, PCI\VEN_1002&DEV_724B
"Radeon X1900 GT Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_726B
"Radeon X1900 Series" = ati2mtag_R580, PCI\VEN_1002&DEV_7249
"Radeon X1900 Series Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_7269
"Radeon X1950 Pro" = ati2mtag_R580, PCI\VEN_1002&DEV_7280
"Radeon X1950 Pro Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_72A0
"Radeon X1950 Series" = ati2mtag_R580, PCI\VEN_1002&DEV_7240
"Radeon X1950 Series " = ati2mtag_R580, PCI\VEN_1002&DEV_7248
"Radeon X1950 Series  " = ati2mtag_R580, PCI\VEN_1002&DEV_7244
"Radeon X1950 Series Secondary" = ati2mtag_R580, PCI\VEN_1002&DEV_7260
"Radeon X1950 Series Secondary " = ati2mtag_R580, PCI\VEN_1002&DEV_7268
"Radeon X1950 Series Secondary  " = ati2mtag_R580, PCI\VEN_1002&DEV_7264
"Radeon X300/X550/X1050 Series" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B63
"Radeon X300/X550/X1050 Series Secondary" = ati2mtag_RV370, PCI\VEN_1002&DEV_5B73
"Radeon X550/X700 Series" = ati2mtag_RV410, PCI\VEN_1002&DEV_5657
"Radeon X550/X700 Series " = ati2mtag_M26, PCI\VEN_1002&DEV_564F
"Radeon X550/X700 Series Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_5677
"RADEON X600/X550 Series" = ati2mtag_RV380, PCI\VEN_1002&DEV_3E50
"RADEON X600/X550 Series Secondary" = ati2mtag_RV380, PCI\VEN_1002&DEV_3E70
"RADEON X700 SE" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4F
"RADEON X700 SE Secondary" = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6F
"RADEON X700 Series  " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4B
"RADEON X700 Series   " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4D
"RADEON X700 Series    " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E4C
"RADEON X700 Series Secondary  " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6B
"RADEON X700 Series Secondary   " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6D
"RADEON X700 Series Secondary    " = ati2mtag_RV410, PCI\VEN_1002&DEV_5E6C
"RADEON X800 PRO/GTO" = ati2mtag_R420, PCI\VEN_1002&DEV_4A49
"RADEON X800 PRO/GTO Secondary" = ati2mtag_R420, PCI\VEN_1002&DEV_4A69
"RADEON X800 Series" = ati2mtag_R420, PCI\VEN_1002&DEV_4A4B
"RADEON X800 Series " = ati2mtag_R420, PCI\VEN_1002&DEV_4A50
"RADEON X800 Series  " = ati2mtag_R423, PCI\VEN_1002&DEV_5549
"RADEON X800 Series   " = ati2mtag_R420, PCI\VEN_1002&DEV_4A4A
"RADEON X800 Series    " = ati2mtag_R430, PCI\VEN_1002&DEV_554F
"RADEON X800 Series     " = ati2mtag_R430, PCI\VEN_1002&DEV_554D
"RADEON X800 Series - Secondary" = ati2mtag_R430, PCI\VEN_1002&DEV_556D
"RADEON X800 Series -Secondary" = ati2mtag_R430, PCI\VEN_1002&DEV_556F
"RADEON X800 Series Secondary" = ati2mtag_R420, PCI\VEN_1002&DEV_4A6B
"RADEON X800 Series Secondary " = ati2mtag_R420, PCI\VEN_1002&DEV_4A70
"RADEON X800 Series Secondary  " = ati2mtag_R423, PCI\VEN_1002&DEV_5569
"RADEON X800 Series Secondary   " = ati2mtag_R420, PCI\VEN_1002&DEV_4A6A
"RADEON X800 XT" = ati2mtag_R423, PCI\VEN_1002&DEV_5D57
"RADEON X800 XT Platinum Edition" = ati2mtag_R423, PCI\VEN_1002&DEV_554A
"RADEON X800 XT Platinum Edition Secondary" = ati2mtag_R423, PCI\VEN_1002&DEV_556A
"RADEON X800 XT Secondary" = ati2mtag_R423, PCI\VEN_1002&DEV_5D77
"RADEON X800/X850 Series" = ati2mtag_R480, PCI\VEN_1002&DEV_5D4F
"RADEON X800/X850 Series - Secondary" = ati2mtag_R480, PCI\VEN_1002&DEV_5D6F
"RADEON X800GT " = ati2mtag_R423, PCI\VEN_1002&DEV_554B
"RADEON X800GT Secondary " = ati2mtag_R423, PCI\VEN_1002&DEV_556B
"RADEON X850 Series" = ati2mtag_R480, PCI\VEN_1002&DEV_5D4D
"RADEON X850 Series " = ati2mtag_R480, PCI\VEN_1002&DEV_5D52
"RADEON X850 Series  " = ati2mtag_R481, PCI\VEN_1002&DEV_4B4B
"RADEON X850 Series   " = ati2mtag_R481, PCI\VEN_1002&DEV_4B49
"RADEON X850 Series    " = ati2mtag_R481, PCI\VEN_1002&DEV_4B4C
"RADEON X850 Series - Secondary" = ati2mtag_R480, PCI\VEN_1002&DEV_5D6D
"RADEON X850 Series - Secondary " = ati2mtag_R480, PCI\VEN_1002&DEV_5D72
"RADEON X850 Series - Secondary  " = ati2mtag_R481, PCI\VEN_1002&DEV_4B6B
"RADEON X850 Series - Secondary   " = ati2mtag_R481, PCI\VEN_1002&DEV_4B69
"RADEON X850 Series - Secondary    " = ati2mtag_R481, PCI\VEN_1002&DEV_4B6C
;
; General installation section
;

[ati2mtag_R300]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R300_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R350]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R350_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R360]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R360_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV350]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV350_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV360]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV360_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV370]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV370_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV380x]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV380x_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV380]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV380_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV410]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV410_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R420]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R420_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R423]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R423_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R430]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R430_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R480]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R480_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R481]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R481_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R4x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R520]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R520_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_R580]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_R580_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV515]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV515_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV515PCI]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV515_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_PCI_SoftwareDeviceSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV530]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV530_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RV535]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RV535_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings, ati2mtag_R5x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS400]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS400_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RC410]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RC410_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS480]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS480_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS482]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS482_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS600]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS600_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS690]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS690_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Desktop_SoftwareDeviceSettings, ati2mtag_LargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_M26]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, Uninstall.CopyFiles, FGL_OGL.sys, ati2mtag.OGL, ati2mtag.ORCA ;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, FGL_OGL.sys, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_M26_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, atioglgl_WsOpenGLSoftwareSettings, ati2mtag_Mobile_SoftwareDeviceSettings, ati2mtag_MobileLargeDesktopSettings, ati2mtag_R3x_SoftwareDeviceSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS480M]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS480M_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Mobile_SoftwareDeviceSettings, ati2mtag_MobileLargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RS690M]
Include=msdv.inf
CopyFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, Uninstall.CopyFiles, ati2mtag.OGL, ati2mtag.ORCA;, DVCR.CopyCodec
AddReg=Uninstall.AddReg
DelFiles=ati2mtag_DelFiles
;UpdateInis=DVCR.UpdateIni
UninstallFiles=Uninstall.CopyFiles
UninstallReg=Uninstall.AddReg
CleanFiles=ati2mtag.Miniport, ati2mtag.Display, ati2mtag.OpenGL, ati2mtag.OGL, ati2mtag.ORCA
CleanReg=ati2mtag_SoftwareDeviceSettings, ati2mtag_RS690M_SoftwareDeviceSettings, atioglxx_OpenGLSoftwareSettings, ati2mtag_Mobile_SoftwareDeviceSettings, ati2mtag_MobileLargeDesktopSettings
CleanService=ati2mtag_RemoveService

[ati2mtag_RemoveService]
ati2mtag
Ati HotKey Poller
;
; File sections
;

[Uninstall.CopyFiles]
atiiiexx.dll

[ati2mtag.Miniport]
ati2mtag.sys
ati2erec.dll

[ati2mtag.Display]
ati2dvag.dll
ati2cqag.dll
Ati2mdxx.exe
ati3duag.dll
ativvaxx.dll
atiicdxx.dat
ativva5x.dat
ativva6x.dat
amdpcom32.dll
atiadlxx.dll
ativvaxx.cap
ATIDDC.DLL
atitvo32.dll
ativcoxx.dll
ati2evxx.exe
ati2evxx.dll
atipdlxx.dll
Oemdspif.dll
ati2edxx.dll
atikvmag.dll
atifglpf.xml
ATIDEMGX.dll
aticaldd.dll
aticalrt.dll
aticalcl.dll
atibrtmon.exe

[ati2mtag.OGL]
atiogl.xml
atiogl.xml

[ati2mtag.OpenGL]
atiok3x2.dll
atiok3x2.dll
atioglxx.dll

[FGL_OGL.sys]
atiok3x2.dll
atioglxx.dll

[ati2mtag.ORCA]
atiok3x2.dll
atioglxx.dll

[Uninstall.AddReg]
HKLM,"Software\Microsoft\Windows\CurrentVersion\Uninstall\ATI Display Driver",DisplayName,,"ATI Display Driver"
HKLM,"Software\Microsoft\Windows\CurrentVersion\Uninstall\ATI Display Driver",UninstallString,,"rundll32 %11%\atiiiexx.dll,_InfEngUnInstallINFFile_RunDLL@16 -force_restart -flags:0x2010001 -inf_class:DISPLAY -clean"
HKLM,"SOFTWARE\ATI Technologies\Installed Drivers\ATI Display Driver"
HKLM,"Software\Microsoft\Windows\CurrentVersion\Uninstall\ATI Display Driver",DisplayVersion,,"8.593.100-100210a-095952E-ATI"

[ati2mtag_DelFiles]
amdcalcl.dll
amdcaldd.dll
amdcalrt.dll
;
; Service Installation
;

[ati2mtag_R300.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R350.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R360.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV350.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV360.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV370.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV380x.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV380.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV410.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R420.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R423.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R430.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R480.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R481.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R520.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_R580.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV515.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV515PCI.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst

[ati2mtag_RV530.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RV535.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS400.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RC410.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS600.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS690.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS480.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS482.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_M26.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS480M.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_RS690M.Services]
AddService = ati2mtag, 0x00000002, ati2mtag_Service_Inst, ati2mtag_EventLog_Inst
AddService = Ati HotKey Poller,, Ati2evxx_Generic_Service_Inst, Ati2evxx_EventLog_Inst

[ati2mtag_Service_Inst]
ServiceType    = 1                  ; SERVICE_KERNEL_DRIVER
StartType      = 3                  ; SERVICE_DEMAND_START
ErrorControl   = 0                  ; SERVICE_ERROR_IGNORE
LoadOrderGroup = Video
ServiceBinary  = %12%\ati2mtag.sys

[ati2mtag_EventLog_Inst]
AddReg = ati2mtag_EventLog_AddReg

[ati2mtag_EventLog_AddReg]
HKR,,EventMessageFile,0x00020000,"%SystemRoot%\System32\IoLogMsg.dll;%SystemRoot%\System32\drivers\ati2erec.dll;%SystemRoot%\System32\drivers\ati2mtag.sys"
HKR,,TypesSupported,0x00010001,7
HKR,, CategoryMessageFile, 0x00020000, "%SystemRoot%\System32\drivers\ati2erec.dll"
HKR,, CategoryCount, 0x00010001, 63

[Ati2evxx_Generic_Service_Inst]
ServiceType    = 0x110
StartType      = 2
ErrorControl   = 1
ServiceBinary  = %11%\Ati2evxx.exe
LoadOrderGroup = Event log

[Ati2evxx_EventLog_Inst]
AddReg=Ati2evxx_EventLog_AddReg

[Ati2evxx_EventLog_AddReg]
HKR,,EventMessageFile,0x00020000,"%11%\Ati2evxx.exe"
HKR,,TypesSupported,0x00010001,7
;
; Software Installation
;

[ati2mtag_R300.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R300_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R350.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R350_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R360.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R360_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV350.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV350_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV360.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV360_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV370.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV370_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV380x.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV380x_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV380.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV380_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV410.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV410_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R420.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R420_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R423.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R423_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R430.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R430_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R480.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R480_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R481.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R481_SoftwareDeviceSettings
AddReg = ati2mtag_R4x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R520.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R520_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_R580.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_R580_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV515.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV515_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV515PCI.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV515_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_PCI_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV530.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV530_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RV535.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RV535_SoftwareDeviceSettings
AddReg = ati2mtag_R5x_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RS400.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS400_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RC410.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RC410_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RS480.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS480_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RS482.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS482_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RS600.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS600_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_RS690.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS690_SoftwareDeviceSettings
AddReg = ati2mtag_Desktop_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_LargeDesktopSettings

[ati2mtag_M26.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_M26_SoftwareDeviceSettings
AddReg = ati2mtag_R3x_SoftwareDeviceSettings
AddReg = ati2mtag_Mobile_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_MobileLargeDesktopSettings

[ati2mtag_RS480M.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS480M_SoftwareDeviceSettings
AddReg = ati2mtag_Mobile_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_MobileLargeDesktopSettings

[ati2mtag_RS690M.SoftwareSettings]
AddReg = ati2mtag_SoftwareDeviceSettings
AddReg = ati2mtag_RS690M_SoftwareDeviceSettings
AddReg = ati2mtag_Mobile_SoftwareDeviceSettings
AddReg = atioglxx_OpenGLSoftwareSettings
DelReg = ati2mtag_RemoveDeviceSettings
AddReg = ati2mtag_MobileLargeDesktopSettings

[ati2mtag_R300_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,06,40,04,80,00,00,01,60,06,40,04,80,00,00,02,00,08,00,06,00,00,00,01,60,08,00,06,00,00,00,02,00,10,24,07,68,00,00,01,50,10,24,07,68,00,00,01,60,10,24,07,68,00,00,02,00,12,80,10,24,00,00,01,60
HKR,, DALRestrictedModesBCD2, %REG_BINARY%,12,80,10,24,00,00,02,00,16,00,12,00,00,00,01,00,16,00,12,00,00,00,01,20,17,92,13,44,00,00,00,90,17,92,13,44,00,00,01,00,18,00,14,40,00,00,00,90,18,00,14,40,00,00,01,00,19,20,12,00,00,00,00,85
HKR,, DALRestrictedModesBCD3, %REG_BINARY%,19,20,14,40,00,00,00,85,19,20,14,40,00,00,01,00,20,48,15,36,00,00,00,66
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R350_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R360_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV350_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,60,12,80,08,00,00,00,00,75,12,80,08,00,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV360_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV370_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, DisableVLD,        %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV380x_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,12,80,09,60,00,00,00,00,17,92,13,44,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV380_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCOOPTION_MaxTmdsPllOutFreq,    %REG_BINARY%,   50,c3,00,00
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1 
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, DisableVLD,        %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV410_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,00,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R420_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,12,80,09,60,00,00,00,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R423_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,12,80,09,60,00,00,00,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R430_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,12,80,09,60,00,00,00,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R480_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,00,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R481_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, GCORULE_FracFbDivSupport,      %REG_DWORD%, 0
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,00,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R520_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 1
HKR,, AreaAniso_DEF, %REG_SZ%, 0
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, GI_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,00,04,80,00,00,00,60,08,00,04,80,00,00,00,70,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,13,60,07,68,00,00,00,70,13,60,07,68,00,00,00,72,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,14,40,09,00,00,00,00,00,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,16,80,10,50,00,00,01,00,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,38,40,10,80,00,00,00,30,38,40,10,80,00,00,00,41,38,40,10,80,00,00,00,60
HKR,, DALNonStandardModesBCD6, %REG_BINARY%,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_R580_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 1
HKR,, AreaAniso_DEF, %REG_SZ%, 0
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, GI_NA, %REG_SZ%, 1
HKR,, DisableWorkstation,               %REG_DWORD%,    1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,70,07,20,05,76,00,00,00,00,08,00,04,80,00,00,00,60,08,00,04,80,00,00,00,70,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,60,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,70
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,13,60,07,68,00,00,00,72,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,14,40,09,00,00,00,00,00,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,16,80,10,50,00,00,01,00
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,38,40,10,80,00,00,00,30,38,40,10,80,00,00,00,41,38,40,10,80,00,00,00,60,12,80,09,60,00,00,00,00
HKR,, DALNonStandardModesBCD6, %REG_BINARY%,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV515_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 1
HKR,, AreaAniso_DEF, %REG_SZ%, 0
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, GI_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,00,04,80,00,00,00,60,08,00,04,80,00,00,00,70,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,13,60,07,68,00,00,00,70,13,60,07,68,00,00,00,72,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,14,40,09,00,00,00,00,00,25,60,16,00,00,00,00,59,25,60,16,00,00,00,00,60,38,40,10,80,00,00,00,30
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,38,40,10,80,00,00,00,41,38,40,10,80,00,00,00,60,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, GXODisablePllFracFbDiv,      %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, DALRULE_EnableOverdriveNoThermalChip,      %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV530_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 1
HKR,, AreaAniso_DEF, %REG_SZ%, 0
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, GI_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,00,04,80,00,00,00,60,08,00,04,80,00,00,00,70,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,12,80,08,00,00,00,00,59
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,13,60,07,68,00,00,00,60
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,13,60,07,68,00,00,00,70,13,60,07,68,00,00,00,72,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,14,40,09,00,00,00,00,00,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,25,60,16,00,00,00,00,59
HKR,, DALNonStandardModesBCD5, %REG_BINARY%,25,60,16,00,00,00,00,60,38,40,10,80,00,00,00,30,38,40,10,80,00,00,00,41,38,40,10,80,00,00,00,60,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00
HKR,, DALNonStandardModesBCD6, %REG_BINARY%,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, DALRULE_EnableOverdriveNoThermalChip,      %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RV535_SoftwareDeviceSettings]
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, GCOOPTION_DigitalCrtInfo,    %REG_BINARY%,   A3,38,61,C1,A3,38,61,B1
HKR,, PrimaryTiling,                 %REG_SZ%,    1
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 1
HKR,, AreaAniso_DEF, %REG_SZ%, 0
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, GI_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,70,08,00,04,80,00,00,00,60,08,00,04,80,00,00,00,70,12,80,08,00,00,00,00,59,12,80,08,00,00,00,00,60,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,70
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,13,60,07,68,00,00,00,72,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,14,40,09,00,00,00,00,00,38,40,10,80,00,00,00,30,38,40,10,80,00,00,00,41,38,40,10,80,00,00,00,60,12,80,07,68,00,00,00,00
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DALRestrictedModesBCD1, %REG_BINARY%,08,00,06,00,00,00,00,43,08,00,06,00,00,00,00,47
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, DALRULE_EnableOverdriveNoThermalChip,      %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS400_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,12,80,07,68,00,00,00,00,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, GCORULE_PPUseBIOSVideoPlaybackAdjustment,      %REG_DWORD%,    0
HKR,, GCORULE_PPEnableVideoPlaybackSupport,      %REG_DWORD%,    0
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RC410_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,12,80,07,68,00,00,00,00,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, GCORULE_PPUseBIOSVideoPlaybackAdjustment,      %REG_DWORD%,    0
HKR,, GCORULE_PPEnableVideoPlaybackSupport,      %REG_DWORD%,    0
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS480_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, R6GxO_UseI2cLayer,      %REG_DWORD%,    1
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, ExtEvent_VideoPlaybackCpuThrottle,        %REG_DWORD%,    0x64
HKR,, GCORULE_PPUseBIOSVideoPlaybackAdjustment,      %REG_DWORD%,    0
HKR,, GCORULE_PPEnableVideoPlaybackSupport,      %REG_DWORD%,    0
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS482_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, R6GxO_UseI2cLayer,      %REG_DWORD%,    1
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,07,20,04,80,00,00,00,60,07,20,04,80,00,00,00,75,07,20,04,80,00,00,00,85,07,20,05,76,00,00,00,00,08,48,04,80,00,00,00,60,08,48,04,80,00,00,00,75,08,48,04,80,00,00,00,85,12,80,07,20,00,00,00,60
HKR,, DALNonStandardModesBCD2, %REG_BINARY%,12,80,07,20,00,00,00,75,12,80,07,20,00,00,00,85,12,80,07,68,00,00,00,60,12,80,07,68,00,00,00,75,12,80,07,68,00,00,00,85,13,60,07,68,00,00,00,60,13,60,07,68,00,00,00,75,13,60,07,68,00,00,00,85
HKR,, DALNonStandardModesBCD3, %REG_BINARY%,13,60,10,24,00,00,00,60,13,60,10,24,00,00,00,75,13,60,10,24,00,00,00,85,14,40,09,00,00,00,00,60,14,40,09,00,00,00,00,75,14,40,09,00,00,00,00,85,16,80,10,50,00,00,00,60,16,80,10,50,00,00,00,75
HKR,, DALNonStandardModesBCD4, %REG_BINARY%,16,80,10,50,00,00,00,85,19,20,10,80,00,00,00,30,19,20,10,80,00,00,00,85,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, ExtEvent_VideoPlaybackCpuThrottle,        %REG_DWORD%,    0x64
HKR,, GCORULE_PPUseBIOSVideoPlaybackAdjustment,      %REG_DWORD%,    0
HKR,, GCORULE_PPEnableVideoPlaybackSupport,      %REG_DWORD%,    0
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS600_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, "1"
HKR,, 3to2Pulldown, %REG_SZ%, 0
HKR,, 3to2Pulldown_DEF, %REG_SZ%, 0
HKR,, 3to2Pulldown_NA, %REG_SZ%, 0
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, DXVA_NOHDDECODE, %REG_SZ%, "1"
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, ColorVibrance_NA, %REG_SZ%, "1"
HKR,, Fleshtone_NA, %REG_SZ%, "1"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,12,80,07,68,00,00,00,00,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS690_SoftwareDeviceSettings]
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,    %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, "1"
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, DXVA_NOHDDECODE, %REG_SZ%, "1"
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, ColorVibrance_NA, %REG_SZ%, "1"
HKR,, Fleshtone_NA, %REG_SZ%, "1"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,10,24,07,68,00,00,00,00,12,80,07,68,00,00,00,00,12,80,09,60,00,00,00,00,16,00,12,00,00,00,00,70,17,92,13,44,00,00,00,00,18,00,14,40,00,00,00,00,18,56,13,92,00,00,00,00
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT, %REG_DWORD%, 1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, CVRULE_ENABLEPALTIMINGSUPPORT,      %REG_DWORD%,    1
HKR,, ExtEvent_VideoPlaybackCpuThrottle,        %REG_DWORD%,    0x64
HKR,, 3to2Pulldown, %REG_SZ%, "0"
HKR,, 3to2Pulldown_DEF, %REG_SZ%, "0"
HKR,, 3to2Pulldown_NA, %REG_SZ%, "0"
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_M26_SoftwareDeviceSettings]
HKR,, DALRULE_NOTVANDLCDONCRTC,             %REG_DWORD%,    1
HKR,, WmAgpMaxIdleClk,			    %REG_DWORD%,    0x20
HKR,, DisableIDCT,                          %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,                  %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00
HKR,, DisableFullAdapterInit,      %REG_DWORD%,    0
HKR,, MemInitLatencyTimer,         %REG_DWORD%,    0x775771BF
HKR,, GCORULE_FlickerWA,             %REG_DWORD%, 1
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION HD"
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,08,00,04,80,00,00,00,60,10,24,04,80,00,00,00,60,10,24,06,00,00,00,00,60,12,80,07,68,00,00,00,60,14,00,10,50,00,00,00,60
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, ExtEvent_EnablePolling,      %REG_DWORD%,    1
HKR,, ExtEvent_BroadcastDispChange,      %REG_DWORD%,    0
HKR,, ExtEvent_UpdateAdapterInfoOnHK,      %REG_DWORD%,    1
HKR,, GCORULE_DisableHotKeyIfDDExclusiveMode,          %REG_DWORD%,    0
HKR,, ExtEvent_LCDSetMaxResOnDockChg,      %REG_DWORD%,    0
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, HDTVRULE_HDTVGDOENABLE,        %REG_DWORD%,    1
HKR,, HDTVRULE_HDTVSIGNALFORMAT,   %REG_DWORD%,    1
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, OVShiftOddDown,                         %REG_DWORD%,    0
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, DALRULE_POWERPLAYOPTIONCOLORDEPTHREDUCTION,      %REG_DWORD%,    0
HKR,, DALRULE_POWERPLAYOPTIONCOLORDEPTHREDUCTION,      %REG_DWORD%,    0
HKR,, R6LCD_FOLLOWLIDSTATE,   %REG_DWORD%,    0
HKR,, DisableFakeOSDualViewNotify,      %REG_DWORD%,    1
HKR,, DisableSWInterrupt,      		   %REG_DWORD%,    1
HKR,, ExtEvent_BIOSEventByInterrupt,      %REG_DWORD%,    0
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, ExtEvent_EnableChgLCDResOnHotKey,                  %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DisableDalValidateChild,        %REG_DWORD%,    0
HKR,, DALRULE_ENABLESHOWACSLIDER,                  %REG_DWORD%,    1
HKR,, DALRULE_ENABLESHOWDCLOWSLIDER,                  %REG_DWORD%,    1
HKR,, R6LCD_RETURNALLBIOSMODES,              %REG_DWORD%,    0
HKR,, ExtEvent_RestoreLargeDesktopOnResume,      %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DfpUsePixSlip,                  %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1
HKR,, CurrentProfile_DEF, %REG_SZ%, "Default"
HKR,, Capabilities_DEF, %REG_DWORD%, 0x00000000
HKR,, CapabilitiesEx_DEF, %REG_DWORD%, 0
HKR,, VisualEnhancements_Capabilities_DEF, %REG_DWORD%, 0

[ati2mtag_RS480M_SoftwareDeviceSettings]
HKR,, DALRULE_NOTVANDLCDONCRTC,             %REG_DWORD%,    1
HKR,, WmAgpMaxIdleClk,                      %REG_DWORD%,    0x20
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,                  %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00 
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, R6GxO_UseI2cLayer,      %REG_DWORD%,    1
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, R6GxO_UseI2cLayer, %REG_DWORD%, 1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, 3to2Pulldown_NA, %REG_SZ%, 1
HKR,, Transcode_NA, %REG_SZ%, 1
HKR,, ASTT_NA, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,08,00,04,80,00,00,00,60,10,24,04,80,00,00,00,60,10,24,06,00,00,00,00,60,12,80,06,00,00,00,00,60,12,80,07,68,00,00,00,60,14,00,10,50,00,00,00,60
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, ExtEvent_EnablePolling,      %REG_DWORD%,    1
HKR,, ExtEvent_BroadcastDispChange,      %REG_DWORD%,    0
HKR,, GCORULE_DisableHotKeyIfDDExclusiveMode,          %REG_DWORD%,    0
HKR,, ExtEvent_LCDSetMaxResOnDockChg,      %REG_DWORD%,    0
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, DALRULE_POWERPLAYOPTIONCOLORDEPTHREDUCTION,      %REG_DWORD%,    0
HKR,, R6LCD_FOLLOWLIDSTATE,   %REG_DWORD%,    0
HKR,, DisableSWInterrupt,      		   %REG_DWORD%,    1
HKR,, ExtEvent_BIOSEventByInterrupt,      %REG_DWORD%,    0
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, ExtEvent_EnableChgLCDResOnHotKey,                  %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, TVM6Flag,   %REG_DWORD%,    0
HKR,, DALRULE_ENABLESHOWACSLIDER,                  %REG_DWORD%,    1
HKR,, DALRULE_ENABLESHOWDCLOWSLIDER,                  %REG_DWORD%,    1
HKR,, R6LCD_RETURNALLBIOSMODES,              %REG_DWORD%,    0
HKR,, ExtEvent_RestoreLargeDesktopOnResume,      %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALRULE_DISABLEDISPLAYSWITCHINGIFDDEXCLUSIVEMODE,      %REG_DWORD%,    1
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, ExtEvent_VideoPlaybackCpuThrottle,        %REG_DWORD%,    0x64
HKR,, GCORULE_PPUseBIOSVideoPlaybackAdjustment,      %REG_DWORD%,    0
HKR,, GCORULE_PPEnableVideoPlaybackSupport,      %REG_DWORD%,    0
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_RS690M_SoftwareDeviceSettings]
HKR,, DALRestrictedModesBCD, %REG_BINARY%,20,48,15,36,00,32,00,85, 20,48,15,36,00,32,00,75, 20,48,15,36,00,32,00,70, 19,20,14,40,00,32,00,85, 19,20,12,00,00,32,00,85
HKR,, DALRULE_NOTVANDLCDONCRTC,             %REG_DWORD%,    1
HKR,, WmAgpMaxIdleClk,                      %REG_DWORD%,    0x20
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DALR6 CRT_MaxModeInfo,                  %REG_BINARY%,00,00,00,00,40,06,00,00,B0,04,00,00,00,00,00,00,3C,00,00,00 
HKR,, SMOOTHVISION_NAME, %REG_SZ%, "SMOOTHVISION 2.1"
HKR,, DisableQuickApply3D,                %REG_DWORD%,    1
HKR,, R6GxO_UseI2cLayer, %REG_DWORD%, 1
HKR,, GI_DEF, %REG_SZ%, 0
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, ASD_DEF, %REG_SZ%, 1
HKR,, AreaAniso_NA, %REG_SZ%, "1"
HKR,, AreaAniso_NA, %REG_SZ%, 1
HKR,, SameOnAllUsingStandardInVideoTheaterCloneMode, %REG_SZ%, "1"
HKR,, VIDEO_NAME_SUFFIX, %REG_SZ%, "Avivo(TM)"
HKR,, DXVA_NOHDDECODE, %REG_SZ%, "1"
HKR,, AntiAliasMapping_SET, %REG_SZ%, "0(0:0,1:0) 2(0:2,1:2) 4(0:4,1:4,2:8,3:10) 6(0:6,1:6,2:12,3:14)"
HKR,, ASTT_DEF, %REG_SZ%, 0
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, ColorVibrance_NA, %REG_SZ%, "1"
HKR,, Fleshtone_NA, %REG_SZ%, "1"
HKR,, DALNonStandardModesBCD1, %REG_BINARY%,08,00,04,80,00,00,00,60,10,24,04,80,00,00,00,60,10,24,06,00,00,00,00,60,12,80,06,00,00,00,00,60,12,80,07,68,00,00,00,60,14,00,10,50,00,00,00,60
HKR,, DisableDualView,                 %REG_DWORD%,    0
HKR,, DisableDualviewWithHotKey,    %REG_DWORD%,    1
HKR,, ExtEvent_EnablePolling,      %REG_DWORD%,    1
HKR,, ExtEvent_BroadcastDispChange,      %REG_DWORD%,    0
HKR,, GCORULE_DisableHotKeyIfDDExclusiveMode,          %REG_DWORD%,    0
HKR,, ExtEvent_LCDSetMaxResOnDockChg,      %REG_DWORD%,    0
HKR,, GCORULE_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER,      %REG_DWORD%,    1
HKR,, GCORULE_IntTMDSReduceBlankTiming,      %REG_DWORD%,    1
HKR,, TVDisableModes,   %REG_DWORD%,    0
HKR,, GCORULE_ENABLERMXFILTER, %REG_DWORD%,   1
HKR,, DALRULE_RESTRICT2ACTIVEDISPLAYS,      %REG_DWORD%,    0
HKR,, DALRULE_POWERPLAYOPTIONCOLORDEPTHREDUCTION,      %REG_DWORD%,    0
HKR,, R6LCD_FOLLOWLIDSTATE,   %REG_DWORD%,    0
HKR,, DisableSWInterrupt,      		   %REG_DWORD%,    1
HKR,, ExtEvent_BIOSEventByInterrupt,      %REG_DWORD%,    0
HKR,, DisableD3DExclusiveModeChange,             %REG_DWORD%,    1
HKR,, DisableOpenGLExclusiveModeChange,             %REG_DWORD%,    1
HKR,, ExtEvent_EnableChgLCDResOnHotKey,                  %REG_DWORD%,    0
HKR,, DisableDalValidateChild,        %REG_DWORD%,    0
HKR,, DALRULE_ENABLESHOWACSLIDER,                  %REG_DWORD%,    1
HKR,, R6LCD_RETURNALLBIOSMODES,              %REG_DWORD%,    0
HKR,, ExtEvent_RestoreLargeDesktopOnResume,      %REG_DWORD%,    0
HKR,, ExtEvent_OverDriveSupport,      %REG_DWORD%,    1
HKR,, DXVA_WMV_DEF,                 %REG_SZ%,    1
HKR,, DXVA_WMV,                 %REG_SZ%,    1
HKR,, DALOPTION_MaxResBCD,                  %REG_BINARY%,   00,00,00,00,00,00,00,85
HKR,, Gxo50HzTimingSupport,          %REG_DWORD%,    1
HKR,, CVRULE_ENABLEPALTIMINGSUPPORT,      %REG_DWORD%,    1
HKR,, ExtEvent_VideoPlaybackCpuThrottle,        %REG_DWORD%,    0x64
HKR,, 3to2Pulldown, %REG_SZ%, "0"
HKR,, 3to2Pulldown_DEF, %REG_SZ%, "0"
HKR,, 3to2Pulldown_NA, %REG_SZ%, "0"
HKR,, Main3D_DEF, %REG_SZ%, 3
HKR,, AntiAlias_DEF, %REG_SZ%, 1
HKR,, AntiAliasSamples_DEF, %REG_SZ%, 0
HKR,, AnisoType_DEF, %REG_SZ%, 0
HKR,, AnisoDegree_DEF, %REG_SZ%, 0
HKR,, TextureOpt_DEF, %REG_SZ%, 0
HKR,, TextureLod_DEF, %REG_SZ%, 0
HKR,, TruformMode_DEF, %REG_SZ%, 0
HKR,, VSyncControl_DEF, %REG_SZ%, 1
HKR,, SwapEffect_DEF, %REG_SZ%, 0
HKR,, TemporalAAMultiplier_DEF, %REG_SZ%, 0
HKR,, ExportCompressedTex_DEF, %REG_SZ%, 1
HKR,, PixelCenter_DEF, %REG_SZ%, 0
HKR,, ForceZBufferDepth_DEF, %REG_SZ%, 0
HKR,, EnableTripleBuffering_DEF, %REG_SZ%, 0
HKR,, ColourDesktopGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourDesktopBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourDesktopContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenGamma_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, ColourFullscreenBrightness_DEF, %REG_SZ%, "0 0 0"
HKR,, ColourFullscreenContrast_DEF, %REG_SZ%, "1.0 1.0 1.0"
HKR,, 3D_Refresh_Rate_Override_DEF, %REG_DWORD%, 0
HKR,, Display_Detection_DEF, %REG_DWORD%, 0
HKR,, Panning_Mode_DEF, %REG_DWORD%, 0
HKR,, Mouse_Track_Orientation_DEF, %REG_DWORD%, 1
HKR,, Force_TV_Detection_DEF, %REG_DWORD%, 0
HKR,, CatalystAI_DEF, %REG_SZ%, 1

[ati2mtag_SoftwareDeviceSettings]
HKR,, DDC2Disabled,                         %REG_DWORD%,    0
HKR,, DisableBlockWrite,                    %REG_DWORD%,    1
HKR,, DisableDMACopy,                       %REG_DWORD%,    0
HKR,, InstalledDisplayDrivers,              %REG_MULTI_SZ%, ati2dvag
HKR,, MultiFunctionSupported,               %REG_DWORD%,    1
HKR,, TestEnv,                              %REG_DWORD%,    0
HKR,, TimingSelection,                      %REG_DWORD%,    0
HKR,, VgaCompatible,                        %REG_DWORD%,    0
HKR,,"Adaptive De-interlacing",             %REG_DWORD%,    1
HKR,,"VPE Adaptive De-interlacing",         %REG_DWORD%,    1
HKR,, GCOOPTION_DisableGPIOPowerSaveMode,   %REG_DWORD%,    1
HKLM,"Software\ATI Technologies\CBT",ReleaseVersion,,"8.593.100-100210a-095952E-ATI"
HKR,, ReleaseVersion,,"8.593.100-100210a-095952E-ATI"
HKR,, BuildNumber,,"95952"
HKR,, drv,, "ati2dvag.dll"
HKR,, DALGameGammaScale,       %REG_DWORD%,   0x00646464
HKR,"ATI WDM Configurations","PnP ID Version",%REG_SZ%,"34"
HKR,, UseNewOGLRegPath,      %REG_DWORD%,    1
HKR,, DALRULE_DYNAMICFIXEDDISPLAYMODEREPORTING,      %REG_DWORD%,    1
HKR,, SwapEffect_NA, %REG_SZ%, 1
HKR,, GXOPPUseExclusiveExecution,  %REG_DWORD%,    1
HKLM,"SYSTEM\CurrentControlSet\Control\GraphicsDrivers\EnableMapIOSpaceProtection"
HKR,, OvlTheaterModeType_DEF, %REG_SZ%,"0"
HKR,, LRTCCoef_DEF, %REG_SZ%,"0"
HKR,, ColorVibrance_NA, %REG_SZ%, "1"
HKR,, Fleshtone_NA, %REG_SZ%, "1"
HKR,, LRTCEnable, %REG_SZ%, "0"
HKR,, LRTCEnable_DEF, %REG_SZ%, "0"
HKR,, ATMS_NA, %REG_SZ%, 1
HKR,, DI_METHOD_DEF, %REG_SZ%, "-1"
HKR,, Force_CV_Detection_DEF,      %REG_DWORD%, 0
HKR,, DefaultSettings.BitsPerPel,           %REG_DWORD%, 32
HKR,, DefaultSettings.XResolution,          %REG_DWORD%, 800
HKR,, DefaultSettings.YResolution,          %REG_DWORD%, 600
HKR,, DefaultSettings.VRefresh,             %REG_DWORD%, 75
HKR,, DALDefaultModeBCD,           %REG_BINARY%,   08,00,06,00,00,32,00,75
HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",ATIModeChange,,"Ati2mdxx.exe"
HKR,, DisableTimeStampWriteBack,   %REG_DWORD%,    0
HKR,, DALRULE_GETVGAEXPANSIONATBOOT,                  %REG_DWORD%,    0
HKLM, "Software\CLASSES\CLSID\{EBB5845F-CA80-11CF-BD3C-008029E89281}\InProcServer32",,,"atitvo32.dll"
HKLM, "Software\CLASSES\CLSID\{EBB5845F-CA80-11CF-BD3C-008029E89281}\InProcServer32",ThreadingModel,,"Both"
HKR,, DisableTiling,                        %REG_DWORD%,    0
HKR,, DALRULE_ENABLEDALRESUMESUPPORT, %REG_DWORD%,   1
HKR,, ExtEvent_EnableHotPlug,      %REG_DWORD%,    1
HKR,, DisableHotPlugDFP,	%REG_DWORD%,	0
HKR,, ExtEvent_EnableMouseRotation,      %REG_DWORD%,    0
HKR,, ExtEvent_EnableAlpsMouseOrientation,      %REG_DWORD%,    0
HKR,, ExtEvent_SafeEscapeSupport,   %REG_DWORD%,    1
HKR,, DFPRULE_HotplugSupported, %REG_DWORD%, 1
HKR,, DALRULE_DISABLEPSEUDOLARGEDESKTOP,      %REG_DWORD%,    0
HKR,, OvlTheaterMode, %REG_BINARY%, 00,00,00,00
HKR,, DisableOvlTheaterMode,%REG_DWORD%,0
HKR,, UseVMRPitch,                        %REG_DWORD%,    1
HKR,, DisableMMSnifferCode,               %REG_DWORD%,    0
HKR,, DisableProgPCILatency,               %REG_DWORD%,    0
HKR,, DALRULE_NOTVANDCRTONSAMECONTROLLER,   %REG_DWORD%,    0
HKR,, DALRULE_GetTVFakeEDID,        %REG_DWORD%,    1
HKR,, Catalyst_Version,,"10.2"
HKR,, DALRULE_REGISTRYACCESS,      %REG_DWORD%,    0
HKR,, DALRULE_RESTRICTCRTANALOGDETECTIONONEDIDMISMATCH,   %REG_DWORD%,    0
HKR,, DALRULE_ENABLEDRIVERMODEPRUNNING,   %REG_DWORD%,    0
HKR,, GCORULE_ENABLETILEDMEMORYCALCULATION,               %REG_DWORD%,    1
HKR,, DALRULE_MACROVISIONINFOREPORT,      %REG_DWORD%,    0
HKR,, DALRULE_BANDWIDTHMODEENUM, %REG_DWORD%, 1
HKR,, DALRULE_NOCRTANDLCDONSAMECONTROLLER, %REG_DWORD%, 0
HKR,, ExtEvent_LCDSetNativeModeOnResume,      %REG_DWORD%,    0
HKR,, DALRULE_LIMITTMDSMODES ,      %REG_DWORD%,    0
HKR,, DALRULE_RESTRICT640x480MODE,        %REG_DWORD%,    0
HKR,, DALRULE_DISPLAYSRESTRICTMODES,   %REG_DWORD%,    0
HKR,, DALRULE_RESTRICT8BPPON2NDDRV,      %REG_DWORD%,    0
HKR,, TVForceDetection,   %REG_DWORD%,    0
HKR,, DALRULE_ADAPTERBANDWIDTHMODEENUM,      %REG_DWORD%,    0
HKR,, GCOOPTION_MinMemEff,      %REG_DWORD%,    0
HKR,, GCORULE_IncreaseMinMemEff,      %REG_DWORD%,    0
HKR,, DALRULE_DISABLECWDDEDETECTION,      %REG_DWORD%,    0
HKR,, DALRULE_SELECTION_SCHEME, %REG_DWORD%, 0
HKR,, DALRULE_NOCRTANDDFPACTIVESIMULTANEOUSLY,      %REG_DWORD%,    0
HKR,, DisableTabletPCRotation,      %REG_DWORD%,    1
HKR,, VPUEnableSubmissionBox,      %REG_SZ%,    "0"
HKR,, VPUEnableSubmissionBox_NA,      %REG_SZ%,    "1"
HKR,, DisableSmartSave_DEF,      %REG_DWORD%,    0
HKR,, VPUEnableSubmissionBox_DEF,      %REG_SZ%,    "1"
HKR,, DisableSmartSave,      %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",DLLName,,"Ati2evxx.dll"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Asynchronous,      %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Impersonate,      %REG_DWORD%,    1
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Lock,,"AtiLockEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Logoff,,"AtiLogoffEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Logon,,"AtiLogonEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Disconnect,,"AtiDisConnectEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Reconnect,, "AtiReConnectEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Safe,      %REG_DWORD%,    0
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Shutdown,, "AtiShutdownEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",StartScreenSaver,, "AtiStartScreenSaverEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",StartShell,,"AtiStartShellEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Startup,,"AtiStartupEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",StopScreenSaver,,"AtiStopScreenSaverEvent"
HKLM,"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Notify\AtiExtEvent",Unlock,,"AtiUnLockEvent"
HKR,, ExtEvent_EnableMultiSessions,      %REG_DWORD%,    1
HKR,, TVEnableOverscan,      %REG_DWORD%,    1
HKR,, DALRULE_NOFORCEBOOT,       %REG_DWORD%,    1
HKR,, DALRULE_DYNAMICMODESUPPORT,                  %REG_DWORD%,    1
HKR,, CVRULE_CUSTOMIZEDMODESENABLED,      %REG_DWORD%,    1
HKR,, DALRULE_ADDNATIVEMODESTOMODETABLE,    %REG_DWORD%,    1
HKR,, DALRULE_CUSTOMODSUPPORT,    %REG_DWORD%,    1
HKR,, Denoise_NA, %REG_SZ%, 1
HKR,, Detail_NA, %REG_SZ%, 1
HKR,, AutoColorDepthReduction_NA,   %REG_DWORD%,    1
HKLM,"SYSTEM\CurrentControlSet\Services\Atierecord",eRecordEnable,          %REG_DWORD%,    1
HKLM,"SYSTEM\CurrentControlSet\Services\Atierecord",eRecordEnablePopups,          %REG_DWORD%,    1
HKR,, DisableOGLx2Loader, %REG_DWORD%, 0x00000000

[ati2mtag_PCI_SoftwareDeviceSettings]
HKR,, 3D_Preview, %REG_SZ%, "StaticPreview.bmp"

[ati2mtag_Mobile_SoftwareDeviceSettings]
HKR,, DALRULE_LCDSHOWRESOLUTIONCHANGEMESSAGE, %REG_DWORD%, 0
HKR,, DALRULE_GETLCDFAKEEDID, %REG_DWORD%, 0
HKR,, DisableEnumAllChilds,        %REG_DWORD%,    0
HKR,, DALRULE_SETMODEAFTERPOWERSTATECHANGE, %REG_DWORD%, 0
HKR,, DALRULE_USEOLDPOWERPLAYINTERFACE,               %REG_DWORD%,    0
HKR,, DALRULE_USEOLDPOWERPLAYPROPERTYPAGE,               %REG_DWORD%,    0
HKR,, DALOPTION_MinResBCD,  %REG_BINARY%, 00,00,00,00,00,00,00,60
HKR,, ExtEvent_EnableADCLogicalMapping,      %REG_DWORD%,    1

[ati2mtag_Desktop_SoftwareDeviceSettings]
HKR,, DisableEnumAllChilds,        %REG_DWORD%,    1

[ati2mtag_R3x_SoftwareDeviceSettings]
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"

[ati2mtag_R4x_SoftwareDeviceSettings]
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "1"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"

[ati2mtag_R5x_SoftwareDeviceSettings]
HKR,, Denoise_DEF, %REG_SZ%, "50"
HKR,, Denoise_ENABLE_DEF, %REG_SZ%, "1"
HKR,, Detail_ENABLE_DEF, %REG_SZ%, "0"
HKR,, ColorVibrance_ENABLE_DEF, %REG_SZ%, "0"
HKR,, Fleshtone_ENABLE_DEF, %REG_SZ%, "0"
HKR,, DynamicContrast_NA, %REG_SZ%, "1"
HKR,, Detail_NA, %REG_SZ%, "1"
HKR,, Denoise_NA, %REG_SZ%, "0"
HKR,, MainVideo_SET, %REG_SZ%, "0 1 2 3 4"
HKR,, MainVideo_TBL, %REG_SZ%, "1:Brightness=0.0,Contrast=1.0,Saturation=1.0,Gamma=0.0,Hue=0.0;2:Brightness=-3.0,Contrast=1.16,Saturation=1.25,Gamma=0.0,Hue=0.0;3:Brightness=-3.0,Contrast=1.07,Saturation=1.10,Gamma=0.0,Hue=0.0;4:Brightness=7.0,Contrast=1.25,Saturation=0.96,Gamma=0.0,Hue=0.0"
HKR,, DisplayCrossfireLogo_NA, %REG_SZ%, 1
HKR,, CVRULE_ENABLEPALTIMINGSUPPORT,      %REG_DWORD%,    1
HKR,, Gxo24HzTimingSupport,          %REG_DWORD%,    1

[atioglxx_OpenGLSoftwareSettings]
HKLM, "Software\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers\ati2dvag", Version, %REG_DWORD%, 2
HKLM, "Software\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers\ati2dvag", DriverVersion, %REG_DWORD%, 1
HKLM, "Software\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers\ati2dvag", Flags, %REG_DWORD%, 1
HKLM, "Software\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers\ati2dvag", Dll, %REG_SZ%, atioglxx.dll

[atioglgl_WsOpenGLSoftwareSettings]
HKR,, Capabilities, %REG_DWORD%, 0x00000000

[ati2mtag_LargeDesktopSettings]
HKR,, DALRULE_AUTOGENERATELARGEDESKTOPMODES,     %REG_DWORD%,    1

[ati2mtag_MobileLargeDesktopSettings]
HKR,, DALRULE_AUTOGENERATELARGEDESKTOPMODES,     %REG_DWORD%,    1

[ati2mtag_RemoveDeviceSettings]
HKR,"Desktop",NoAtipta
HKR,, ActiveBusCaps
HKR,, Adaptive De-interlacing
HKR,, AgpLevel
HKR,, AntiAlias
HKR,, ATIPoll
HKR,, DALCurrentObjectData
HKR,, DALLastConnected
HKR,, DALLastSelected
HKR,, DALLastTypes
HKR,, DALNonStandardModesBCD
HKR,, DALNonStandardModesBCD1
HKR,, DALNonStandardModesBCD2
HKR,, DALNonStandardModesBCD3
HKR,, DALNonStandardModesBCD4
HKR,, DALNonStandardModesBCD5
HKR,, DALObjectData
HKR,, DALObjectData0
HKR,, DALObjectData1
HKR,, DALR6 CRT_MaxModeInfo
HKR,, DALR6 CRT2_MaxModeInfo
HKR,, DALR6 DFP_MaxModeInfo
HKR,, DALR6 DFPx_MaxModeInfo
HKR,, DALR6 GCO_Index0
HKR,, DALRestrictedModesBCD
HKR,, DALRestrictedModesBCD1
HKR,, DALRestrictedModesBCD2
HKR,, DALRestrictedModesBCD3
HKR,, DALRestrictedModesBCD4
HKR,, DALRestrictedModesBCD5
HKR,, DALRULE_ADDNATIVEMODESTOMODETABLE
HKR,, DALRULE_CRTSUPPORTSALLMODES
HKR,, DALRULE_DISABLEBANDWIDTH
HKR,, DALRULE_DISPLAYSRESTRICTMODES
HKR,, DALRULE_NOCRTANDLCDONSAMECONTROLLER
HKR,, DALRULE_NOFORCEBOOT
HKR,, DALRULE_NOTVANDCRTONSAMECONTROLLER
HKR,, DALRULE_RESTRICTUNKNOWNMONITOR
HKR,, DALRULE_SAVEPANLOCK
HKR,, DALSelectObjectData0
HKR,, DALSelectObjectData1
HKR,, DDC2Disabled
HKR,, DefaultMode
HKR,, DFPRULE_HotplugSupported
HKR,, DisableAGP
HKR,, DisableAGPDFB
HKR,, DisableAGPPM4
HKR,, DisableAGPTexture
HKR,, DisableAGPWrite
HKR,, DisableBlockWrite
HKR,, DisableD3D
HKR,, DisableDMA
HKR,, DisableDMACopy
HKR,, DisableDrvAlphaBlend
HKR,, DisableDrvStretchBlt
HKR,, DisableDynamicEnableMode
HKR,, DisableEngine
HKR,, DisableEnumAllChilds
HKR,, DisableFullAdapterInit
HKR,, DisableHierarchicalZ
HKR,, DisableHWAAFonts
HKR,, DisableIDCT
HKR,, DisableLCD
HKR,, DisableMMLIB
HKR,, DisableOpenGLScrAccelerate
HKR,, DisablePllInit
HKR,, DisablePrimaryTiling
HKR,, DisableRptrWriteBack
HKR,, DisableTCL
HKR,, DisableTiling
HKR,, DisableTimeStampWriteBack
HKR,, DisableUSWC
HKR,, DisableVideoUSWC
HKR,, DisableVPE
HKR,, EnableWaitUntilIdxTriList2
HKR,, ExtEvent_BroadcastDispChange
HKR,, ExtEvent_DriverMessageSupport
HKR,, ExtEvent_EnableChgLCDResOnHotKey
HKR,, ExtEvent_EnableHotPlug
HKR,, ExtEvent_EnableMouseRotation
HKR,, ExtEvent_EnablePolling
HKR,, ExtEvent_EnablePowerPlay
HKR,, ExtEvent_LCDSetMaxResOnDockChg
HKR,, ExtEvent_UpdateAdapterInfoOnHK
HKR,, GCORULE_HIGHDISPRI
HKR,, GCORULE_R200TVPLLWA
HKR,, LVB
HKR,, MaxAgpVb
HKR,, MaxAGPVB
HKR,, MaxLocalVb
HKR,, MaxLocalVB
HKR,, MemInitLatencyTimer
HKR,, QSindirectBufferLocation
HKR,, QSringBufferLocation
HKR,, RequestedBusCaps
HKR,, SubmitOnDraw
HKR,, TestedBusCaps
HKR,, TestEnv
HKR,, TimingSelection
HKR,, TVR200Flag
HKR,, VgaCompatible
HKR,, VPE Adaptive De-interlacing
HKR,, DALInstallFlag
HKR,, FireGLRocketScience
HKLM, "Software\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers\atifglws"
HKR,, CurrentProfile
HKR,, RebootFlags
HKR,, RebootFlagsEx
HKR,, Capabilities
HKR,, CapabilitiesEx
HKR,, DALPowerPlayOptions
HKR,, DALRULE_NOCRTANDDFPONSAMECONTROLLER
HKR,, DALRULE_NOCRTANDLCDONSAMECONTROLLER
HKR,, GCORULE_DISABLETMDSREDUCEDBLANKING
HKR,, GCORULE_IntTMDSReduceBlankTiming
HKR,, GCORULE_R200TVPLLWA
HKR,, TVR200Flag
HKR,, AntiAlias
HKR,, GCORULE_DisableHotKeyIfOverlayAllocated
HKR,, DisableDualView
HKR,, DisableDualviewWithHotKey
HKR,"OpenGL",OGLEnableSharedBackZ
HKR,, DALRULE_LARGEPANELSUPPORT
HKR,, DFPRULE_ResyncCRTCs
HKR,, GCORULE_SameDividersForIntAndExtTMDS
HKR,, DALOPTION_MinResBCD
HKR,, DALOPTION_MaxResBCD
HKR,, DALOPTION_MinRes2BCD
HKR,, DALOPTION_MaxRes2BCD
HKR,, DALRULE_MOBILEFEATURES
HKR,, GCORULE_ForceCoherentTMDSForHighMode
HKR,, DALRV100TMDSiReducedBlanking
HKR,, DALRV200TMDSiReducedBlanking
HKR,, DALR200TMDSiReducedBlanking
HKR,, DALRV250TMDSiReducedBlanking
HKR,, DALRV280TMDSiReducedBlanking
HKR,, DALRV350TMDSiReducedBlanking
HKR,, DALR300TMDSiReducedBlanking
HKR,, DALR350TMDSiReducedBlanking
HKR,, DALR360TMDSiReducedBlanking
HKR,, DALATI M6TMDSiReducedBlanking
HKR,, DALATI M7TMDSiReducedBlanking
HKR,, DALATI M9TMDSiReducedBlanking
HKR,, DALATI M9 PLUSTMDSiReducedBlanking
HKR,, DALM10TMDSiReducedBlanking
HKR,, DALRV380TMDSiReducedBlanking
HKR,, DALR420TMDSiReducedBlanking
HKR,, DALM18TMDSiReducedBlanking
HKR,, DALM24TMDSiReducedBlanking
HKR,, DALR300TMDSiCoherentMode
HKR,, DALR350TMDSiCoherentMode
HKR,, DALR360TMDSiCoherentMode
HKR,, DALRV280TMDSiCoherentMode
HKR,, DALRV350TMDSiCoherentMode
HKR,, DALATI M9 PLUSTMDSiCoherentMode
HKR,, DALM10TMDSiCoherentMode
HKR,, DALRV380TMDSiCoherentMode
HKR,, DALR420TMDSiCoherentMode
HKR,, DALM18TMDSiCoherentMode
HKR,, DALM24TMDSiCoherentMode
HKR,, DALRULE_MODESUPPORTEDSIMPLECHECK
HKR,, DALRULE_DISPLAYSRESTRICTMODESLARGEDESKTOP
HKR,, OptimalNB
HKR,, OptimalPamac0
HKR,, OptimalPamac1
HKR,, GCOOPTION_MaxTmdsPllOutFreq
HKR,, DAL2ndDisplayDefaultMode
HKR,, R6LCD_RETURNALLBIOSMODES
HKR,, VPUEnableSubmissionBox
HKR,, VPUEnableSubmissionBox_NA
HKR,, VPURecover_NA
HKR,, DisplaysManagerRotation_NA
HKR,, GCORULE_MemoryClockGraduallyChange
HKR,, DALRULE_AUTOGENERATELARGEDESKTOPMODES
HKR,, UseCentredCVTiming
HKR,, GCORULE_R200TVPLLWA
HKR,, TVR200Flag
HKR,, DALRULE_POWERPLAYFORCEREFRESHSCREEN
HKR,, GI
HKR,, DALR6 CRT_INFO
HKR,, DefaultSettings.BitsPerPel
HKR,, DefaultSettings.XResolution
HKR,, DefaultSettings.YResolution
HKR,, DefaultSettings.VRefresh
HKR,, TruformMode_NA
HKR,, 3D_Preview
HKR,, VPURecover_NA
HKR,, SMARTGART_NA
HKR,, OGL_Specific_NA
HKR,, TemporalAAMultiplier_NA
HKR,, CatalystAI_NA
HKR,, SwapEffect_NA
HKR,, AutoColorDepthReduction_NA
HKR,, "3D_Preview"
HKR,, 3D_Refresh_Rate_Override_DEF
HKR,, ACE
HKR,, ACE_Copy
HKR,, AnisoDegree_DEF
HKR,, AnisoType_DEF
HKR,, AntiAlias_DEF
HKR,, AntiAliasSamples_DEF
HKR,, Capabilities_DEF
HKR,, CapabilitiesEx_DEF
HKR,, CatalystAI_DEF
HKR,, ColourDesktopBrightness_DEF
HKR,, ColourDesktopContrast_DEF
HKR,, ColourDesktopGamma_DEF
HKR,, ColourFullscreenBrightness_DEF
HKR,, ColourFullscreenContrast_DEF
HKR,, ColourFullscreenGamma_DEF
HKR,, CurrentProfile_DEF
HKR,, DisableSmartSave_DEF
HKR,, DisableSmartSave
HKR,, Display_Detection_DEF
HKR,, DitherAlpha_DEF
HKR,, EnableTripleBuffering_DEF
HKR,, ExportCompressedTex_DEF
HKR,, Force_TV_Detection_DEF
HKR,, ForceZBufferDepth_DEF
HKR,, FSAAPerfMode_DEF
HKR,, GI_DEF
HKR,, Main3D_DEF
HKR,, Mouse_Track_Orientation_DEF
HKR,, Panning_Mode_DEF
HKR,, PixelCenter_DEF
HKR,, SwapEffect_DEF
HKR,, TemporalAAMultiplier_DEF
HKR,, TextureLod_DEF
HKR,, TextureOpt_DEF
HKR,, TruformMode_DEF
HKR,, VisualEnhancements_Capabilities_DEF
HKR,, VPUEnableSubmissionBox_DEF
HKR,, VSyncControl_DEF
HKR,, ZFormats_DEF
HKR,, DALRULE_ONEDISPLAYBOOTDEFAULT
HKR,, DisableSWInterrupt
HKR,, ExtEvent_BIOSEventByInterrupt
HKR,, DisableDirectDraw
HKLM,"SYSTEM\CurrentControlSet\Services\Atierecord",eRecordEnable
HKLM,"SYSTEM\CurrentControlSet\Services\Atierecord",eRecordEnablePopups
HKR,, DALVariBrightStatus
HKR,, GI_NA
HKR,, RotationSupportLevel
HKR,, NewRotation
HKR,, SGCountDown
HKR,, TVM6Flag
HKR,, TheaterMode_NA
HKR,, ASTT_NA
HKR,, DisableDFB
HKR, "UMD\DXVA", DXVA_NOHDDECODE
HKR,, PP_PhmUseDummyBackEnd
HKR,, SORTOverrideFPSCaps
HKR,, SORTOverrideVidSizeCaps
HKR,, DXVA_Only24FPS1080MPEG2
HKR,, DXVA_Only24FPS1080H264
HKR,, DXVA_Only24FPS1080VC1
HKR,, DisableCFExtendedDesktop
HKR,, ATMS_DEF
HKR,, AAAMethod_DEF
HKR,, TestEnv
HKR,, PP_DisablePPLib
HKR,, FrameBufferMode
HKR,, EnableUnifiedGartSegment
HKR,, EnablePDMA
HKR,, PP_PhmUseDummyBackEnd
HKR,, DisableRejectCf
HKR,, PP_GFXClockGatingEnabled
HKR,, DisablePCIEGen2Support
HKR,, DynamicContrast_ENABLE_DEF
HKR,, DynamicContrast_NA
HKR,, DynamicContrast_DEF
HKR,, DP_EnableSSByDefault
HKR,, DXVA_WMV_DEF
HKR,, DXVA_WMV
HKR,, DisableCfSpSupport
HKR,, AntiAliasMapping_SET
HKR,, DisableMultiMonEnum
HKR,, DALRULE_ALLOWNONDDCCRTALLMODESUPTO1600x1200
HKR,, ATIPOLLINTERVAL
HKR,"OpenGL",OGLEnableSharedBackZ
HKR,"Desktop\UIO\Color",DefaultGammaDesktop
HKR,, ExtEvent_EnableFjsuMouseOrientation
HKR,, ExtEvent_EnablePowerPlay
HKR,, ExtEvent_DriverMessageSupport
HKR,, TVContrastDefaultNTSC
HKR,, GCORULE_DisableHotKeyIfOverlayAllocated
HKR,, DisableFlush2DCache
HKR,, HDTVRULE_HDTVGDOENABLE
HKR,, HDTVRULE_HDTVSIGNALFORMAT
HKR,, DALRULE_NOEDIDTOOS
HKR,, GCORULE_TMDSiCoherentMode
HKR,, GCOHOOK_TMDSiCoherentMode
HKR,, DALRULE_POWERPLAYSUSPENDSUPPORT
HKR,, DALRULE_POWERPLAYOPTIONENABLEDBYDEFAULT
HKR,, DALRULE_USECMOSDISPLAYSETTINGS
HKR,, TabletPCRotateClockwise
HKR,, ExtEvent_EnableAutoDisplayConfig
HKR,, DALRULE_USERDEVICEPROFILEUPDATE
HKR,, ExtEvent_EnableMpAtLogon
HKR,, ExtEvent_NonExtendedADCProfileOnHotKey
HKR,, ExtEvent_EnableMpAtDocking
HKR,, ExtEvent_EnableMpAtSessionChange
HKR,, ExtEvent_EnableMpAtLidSwitch
HKR,, ExtEvent_EnableMpAtHotPlug
HKR,, ExtEvent_EnableMpAtHotKeyAcpi
HKR,, ExtEvent_EnableMpAtHotKeyExtEvent
HKR,, DALRULE_OTHEREXPANSIONMODEDEFAULT
HKR,, DisableOSModePruning
HKR,, DALRULE_WADSUPPORT
HKR,, GCORULE_WADSUPPORT
HKR,, DALRULE_RESTRICTNONDDCCRTTO1024x768
HKR,, DALRULE_ALLOWNONDDCCRTALLMODESUPTO1024x768
HKR,, DALRULE_ALLOWNONDDCCRTALLMODESUPTO1920x1200
HKR,, DisablePM4TSInterrupt
HKR,, GCORule_ForceSingleController
HKR,, DALRULE_DISABLEDISPLAYSWITCHINGIFOVERLAYALLOCATED
HKR,, ExtEvent_ApplyADCAtFUS
HKLM,"Software\ATI Technologies\WDMCapture",Keep704AspectRatio
HKR,, ExtEvent_SaveProfileBySelected
HKR,, ExtEvent_ApplyADCAtSBiosRequest
HKR,, DALRULE_EDIDPROFILE
HKR,, DALRULE_DONOTTURNONTVBYDEFAULT
HKR,, TVLumaFlicker
HKR,, TVDotCrawl
HKR,, TVCompositeFilter
HKR,, DALDisplayPrioritySequence
HKR,, DALRULE_SETNONDDCCRTPREFERREDMODE800x600
HKR,, DALRULE_DISABLEPOWERPLAYMESSAGES
HKR,, ExtEvent_EnableADCRotationSupport
HKR,, ExtEvent_SaveADCProfileGlobally
HKR,, ApplyRotationDefaultMode
HKR,, ExtEvent_NonExtendedADCProfileOnHotKey
HKR,, DALRULE_ADDEXTDESKTOPTOPROFILEKEY
HKR,, ExtEvent_DeviceTypeBasedADCProfile
HKR,, DALRULE_DEVICETYPEBASEDPROFILEKEY
HKR,, GCORULE_PPForceBlankDisplays
HKR,, ExtEvent_SaveExpansionInADCProfile
HKR,, DALRULE_DISABLEOVERDRIVE
HKR,, DALOverdrive
HKR,, ExtEvent_OverDriveSupport
HKR,, DALRULE_GETDEFAULTTVFORMATATBOOT
HKR,, HibernationPatch
HKR,, DALRULE_CVALLOCOV480IONLY
HKR,, DALRULE_USEENABLEDATBOOTSCHEME
HKR,, DisableCursor
HKR,, DALRULE_UNRESTRICTSXGAPCRTONOWNCRTC
HKR,, GCOOPTION_RemoveOverscanBorder
HKR,, DALRULE_USERESTRICTEDNATIVETIMING
HKR,, DFPOption_MaxFreq
HKR,, DALRestrictedModesCRTC2BCD1
HKR,, GCORULE_ModeBWException
HKR,, DXVA_HWSP_1CRTC
HKR,, DisableAGPFW
HKR,, UseBT601CSC
HKR,, ExtEvent_EnableADCAtUndocking
HKR,, DALRULE_SETCRTANDDFPTYPESONPRIMARYCONTROLLER
HKR,, BootInLandscape
HKR,, BootInLandscapeDefaultModeBCD
HKR,, DALRULE_LCDENABLEDONPRIMARYCONTROLLER
HKR,, CVRULE_CENTRETIMINGDISABLED
HKR,, DAL2ndDrvMin1stMode
HKR,, GCORULE_CloneModeBWException
HKR,, DALRULE_DISABLEPOWERPLAYSWITCHATRESUME
HKR,, CRTRULE_FORCECRTDAC1DETECTED
HKR,, CRTRULE_FORCECRTDAC2DETECTED
HKR,, CRTRULE_FORCECRTDACTYPESDETECTED
HKR,, DisableAGPSizeOverride
HKR,, DALRULE_NOTVANDDVIACTIVESIMULTANEOUSLY
HKR,, GCORULE_PowerPlayClearMemBase
HKR,, DALRULE_PROFILEPREFERREDMODEBASEDONEXTDEVICE
HKR,, GCORULE_TMDSReducedBlankingUseCVT
HKR,, LRTCEnable
HKR,, GSettingControl
HKR,, DisableDTM
HKR,, DFPOption_SingleLink
HKR,, DFPXOption_SingleLink
HKR,, TVContrastDefaultNTSCJ
HKR,, TVContrastDefaultPAL
HKR,, R6LCD_ALLOWDISABLELOWREFRESHBYUSER
HKR,, ExtEvent_SaveProfileAtShutdown
HKR,, TVDACSettings
HKR,, DALRULE_ALLOWMONITORRANGELIMITMODES
HKR,, DALRULE_ALLOWMONITORRANGELIMITMODESCRT
HKR,, GCORULE_TMDSForceReducedBlanking
HKR,, ExtEvent_EnableADCExclusiveModeHandling
HKR,, DXVA_ELEGANT
HKR,, ExtEvent_EnableChgCVResOnHotKey
HKR,, GCOOPTION_DefaultOvlBrightness
HKR,, GCOOPTION_DefaultOvlSaturation
HKR,, GCOOPTION_DefaultOvlContrast
HKR,, DAL_CRTRestrictedModesBCD
HKR,, RegKeyLight
HKR,, PP_GFXClockGatingEnabled
HKR,, DisableFBCSupport
HKR,, GXODFPxDVODDRSupport
HKR,, DeltaAgpPoolSize
HKR,, InitialAgpPoolSize
HKR,, DALRULE_NOCRTANDTVACTIVESIMULTANEOUSLY
HKR,, GCORULE_ExtTMDSReduceBlankTiming
HKR,, GCOOPTION_ExtTMDSMaxTMDSClockSpeed
HKR,, OverDrive3_NA
HKR,, OverDrive2_NA
HKR,, CRTRULE_EIAJ_TRANSLATION
HKR,, DAL_CvRestrictedModesBCD
HKR,, CRTRULE_480PALWAYSSUPPORTED
HKR,, DFPRULE_ExtTMDSEncoderSupport
HKR,, AutoClockConfig_NA
HKR,, Acceleration.Level
HKR,, DALRULE_DISABLEVARIBRIGHTBYDEFAULT
HKR,, DALRULE_HIDEVARIBRIGHT
HKR,, DALRULE_DONTSHOWWADOPTION
HKR,, NotSupportedRotationModesExt
HKR,, ExtEvent_SetDefault32BppOn2ndDrv
HKR,, OvlRotation
HKR,, GCORULE_EnableOption
HKR,, OvlDisableOverlay
HKR,, DALRULE_DONOTUSECUSTOMISEDMODEFORCVPANNING
HKR,, RotationAngle
HKR,, DefaultSettings.Orientation
HKR,, DALRULE_SENDCONTROLLERCONFIGCHANGEMESSAGE
HKR,, maMethod
HKR,, GCORULE_CvImproveClkPrecision
HKR,, DisableSkippingS5Dpms
HKR,, GCORULE_X1DETECT
HKR,, LimitDFBCreation
HKR,, DALDefaultCvModeBCD
HKR,, DALRULE_CVUSEOPTIMODEASDEFAULT
HKR,, DALDefaultCEDTVModeBCD
HKR,, DALRULE_CEDTVUSEOPTIMODEASDEFAULT
HKR,, DALRULE_ADDEDIDSTANDARDMODESTOMODETABLE
HKR,, DisableConditionalMutex
HKR,, DAL_CVDeviceData
HKR,, GXONoLineReplication
HKR,, GXOM5XDisableLaneSwitch
HKR,, DisableTurnOnAllDisplaysAtResume
HKR,, GXOPPDCDEFAULTTOBALANCEDMODE
HKR,, GXOPPDCLOWDEFAULTTOBALANCEDMODE
HKR,, DisableMFunction
HKR,, GXODisableDefaultVideoPowerSwitch
HKR,, MVPUAllowCompatibleAFR
HKR,, DALRULE_LIMITEDGREYSCALESUPPORT
HKR,, Extevent_HotplugUseCurrentMapping
HKR,, DALRULE_ALWAYSREPORTLARGEDESKTOPMODES
HKR,, DAL_TVRestrictedModesBCD
HKR,, Disable5299
HKR,, HWUVD_DisableH264
HKR,, HWUVD_DisableVC1
HKR,, DisableVForceMode
HKR,, PP_ForceReportOverdrive4
HKR,, EnablePPSMSupport
HKR,, PPSMSupportLevel
HKR,, EnableSPSurface
HKR,, PP_DeferFirstStateSwitch
HKR,, GXODontDisableVGAAtResume
HKR,, PP_RS780CGINTGFXMISC2
HKR,, EnableGeminiAutoLink
HKR,, DisableFBCSupport
HKR,, FBCSupportLevel
HKR,, HDTVRULE_HDTVGDOENABLE
HKR,, HDTVRULE_HDTVSIGNALFORMAT
HKR,, ForceHigh3DClocks_NA
HKR,, TMDS_DisableDither
HKR,, DigitalHDTVDefaultUnderscan
HKR,, PP_VariBrightFeatureEnable
HKR,, GXODFPxDVODDRSupport
HKR,,   DisableVLDForSingleFireMVAsic
HKR,, DALRULE_AllowNonCEModes
HKR,, DisableOGL10BitPixelFormats
HKR,, DALRULE_AllowNativeModeAsDefaultModes
HKR,, GXODFPxDVODDRSupport
HKR,, GXOUseSclkforProgrammableDispClk
HKR,, DALDefaultACPowerState
HKR,, DALDCLowThresholdValue
HKR,, PO_SwRi
HKR,, DALPanelPatchByID
HKR,, GXOTwoDigitalPanelPLLWa
HKR,, GxoAllCvFormatSupportedAtBoot
HKR,, DALRULE_ENABLEMONITORTIMEOUTPWRSTATE
HKR,, Gxo30BppPanels
HKR,, GXODFPDefaultCoherentMode
HKR,, GXODFP2DefaultCoherentMode
HKR,, GXODFPXDefaultCoherentMode
HKR,, DisplayCrossfireLogo_DEF
HKR,, DALRULE_SkipEDIDReadForNoSink
HKR,, DisablePCIEx1LaneUVD
HKR,, PP_DCPowerSourceUIMapping_Default
HKR,, MaxDPMClock
HKR,, Disable8435
HKR,, GCOOPTION_MaxOverlayBandwidth
HKR,, Gxo_AdapterOverlayBandwidth
HKR,, CRTRULE_R520FORCECRTDAC2DETECTED
HKR,, DisableTearFreeDesktop
HKR,, Disable3dOptVSync
HKR,, PP_DisableODStateInDC
HKR,, PP_DisableDCODT
HKR,, DisableConsumerStretchRotation
HKR,, DisableIGPDirectAccess
HKR,, ExtEvent_ADCApplyCurrentModeWhenNothingConnected

[ati2mtag_R300.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R350.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R360.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV350.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV360.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV370.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV380x.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV380.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV410.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R420.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R423.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R430.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R480.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R481.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R520.GeneralConfigData]
MaximumDeviceMemoryConfiguration=512
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_R580.GeneralConfigData]
MaximumDeviceMemoryConfiguration=512
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV515.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV515PCI.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV530.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RV535.GeneralConfigData]
MaximumDeviceMemoryConfiguration=256
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS400.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RC410.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS480.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS482.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS600.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS690.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_M26.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS480M.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[ati2mtag_RS690M.GeneralConfigData]
MaximumDeviceMemoryConfiguration=128
MaximumNumberOfDevices=4
SessionImageSize = 16

[SourceDisksNames.x86]
1 = %DiskId%,,,.\B_95503

[SourceDisksNames.ia64]
1 = %DiskID%,,,.\B_95503

[SourceDisksFiles]
amdpcom32.dll=1
ati2cqag.dll=1
ati2dvag.dll=1
ati2edxx.dll=1
ati2erec.dll=1
ati2evxx.dll=1
ati2evxx.exe=1
ati2mdxx.exe=1
ati2mtag.sys=1
ati3duag.dll=1
atiadlxx.dll=1
atibrtmon.exe=1
aticalcl.dll=1
aticaldd.dll=1
aticalrt.dll=1
atiddc.dll=1
atidemgx.dll=1
atifglpf.xml=1
atiicdxx.dat=1
atiiiexx.dll=1
atikvmag.dll=1
atiogl.xml=1
atioglxx.dll=1
atiok3x2.dll=1
atipdlxx.dll=1
atitvo32.dll=1
ativcoxx.dll=1
ativva5x.dat=1
ativva6x.dat=1
ativvaxx.cap=1
ativvaxx.dll=1
oemdspif.dll=1

[Strings]
;
; Non-Localizable Strings
;
REG_SZ         ="0x00000000"
REG_MULTI_SZ   ="0x00010000"
REG_EXPAND_SZ  ="0x00020000"
REG_BINARY     ="0x00000001"
REG_DWORD      ="0x00010001"
SERVICEROOT    ="System\CurrentControlSet\Services"
;
; Localizable Strings
;
DiskId       = "ATI Technologies Inc. Installation DISK (VIDEO)"
GraphAdap    = "Graphics Adapter"
ATI          = "ATI Technologies Inc."
ATIR200="Chaplin (R200)" 
; Driver Information Entries
; These items will be set by IHV...
DriverMfgr="ATI Technologies Inc."			; IHV name
DriverVersionID="7.xx"					; The IHV driver version
BaseDriverFileName="ati2mtag.sys" 			; Key file for version 
BaseDriverFileVersion="5.13.01.3210" 			; version of key file 
; These items will be set by IHV and updated by OEM 
DriverOEM="ATI Technologies Inc."			; name of the OEM 
DriverFamily="Video" 					; device family (NIC, Storage, Video...)
DriverProduct="ATI Radeon" 				; Specific Name of device (chipset, for example)
DriverDescription="Graphics Driver" 			; Description of device (product name, OS or system supported)
DriverOEMVersion="Centralized Build"                    ; OEM-specified version 
''',
'''
; SMBUSati.inf
;
; Installation file (.inf) for the ATI SMBus device.
;
; (c) Copyright 2002-2006 ATI Technologies Inc
;

[Version]
Signature="$CHICAGO$"
Provider=%ATI%
ClassGUID={4d36e97d-e325-11ce-bfc1-08002be10318}
Class=System
CatalogFile=SMbusati.cat
DriverVer=02/26/2007,5.10.1000.8

[DestinationDirs]
DefaultDestDir   = 12

;
; Driver information
;

[Manufacturer]
%ATI%   = ATI.Mfg, NTamd64


[ATI.Mfg]
%ATI.DeviceDesc0% = ATISMBus, PCI\VEN_1002&DEV_4353
%ATI.DeviceDesc0% = ATISMBus, PCI\VEN_1002&DEV_4363
%ATI.DeviceDesc0% = ATISMBus, PCI\VEN_1002&DEV_4372
%ATI.DeviceDesc0% = ATISMBus, PCI\VEN_1002&DEV_4385

[ATI.Mfg.NTamd64]
%ATI.DeviceDesc0% = ATISMBus64, PCI\VEN_1002&DEV_4353
%ATI.DeviceDesc0% = ATISMBus64, PCI\VEN_1002&DEV_4363
%ATI.DeviceDesc0% = ATISMBus64, PCI\VEN_1002&DEV_4372
%ATI.DeviceDesc0% = ATISMBus64, PCI\VEN_1002&DEV_4385

;
; General installation section
;

[ATISMBus]
AddReg=Install.AddReg

[ATISMBus64]
AddReg=Install.AddReg.NTamd64

;
; Service Installation
;                     

[ATISMBus.Services]
AddService = , 0x00000002

[ATISMBus64.Services]
AddService = , 0x00000002

[ATISMBus_Service_Inst]
ServiceType    = 1                  ; SERVICE_KERNEL_DRIVER
StartType      = 3                  ; SERVICE_DEMAND_START 
ErrorControl   = 0                  ; SERVICE_ERROR_IGNORE
LoadOrderGroup = Pointer Port

[ATISMBus_EventLog_Inst]
AddReg = ATISMBus_EventLog_AddReg

[ATISMBus_EventLog_AddReg]

[Install.AddReg]
HKLM,"Software\ATI Technologies\Install\South Bridge\SMBus",DisplayName,,"ATI SMBus"
HKLM,"Software\ATI Technologies\Install\South Bridge\SMBus",Version,,"5.10.1000.8"
HKLM,"Software\ATI Technologies\Install\South Bridge\SMBus",Install,,"Success"

[Install.AddReg.NTamd64]
HKLM,"Software\Wow6432Node\ATI Technologies\Install\South Bridge\SMBus",DisplayName,,"ATI SMBus"
HKLM,"Software\Wow6432Node\ATI Technologies\Install\South Bridge\SMBus",Version,,"5.10.1000.8"
HKLM,"Software\Wow6432Node\ATI Technologies\Install\South Bridge\SMBus",Install,,"Success"

;
; Source file information
;

[SourceDisksNames]
1 = %DiskId1%,,,

[SourceDisksFiles]
; Files for disk ATI Technologies Inc Installation Disk #1 (System)

[Strings]

;
; Non-Localizable Strings
;

REG_SZ         = 0x00000000
REG_MULTI_SZ   = 0x00010000
REG_EXPAND_SZ  = 0x00020000
REG_BINARY     = 0x00000001
REG_DWORD      = 0x00010001
SERVICEROOT    = "System\CurrentControlSet\Services"

;
; Localizable Strings
;

ATI.DeviceDesc0 = "ATI SMBus"
DiskId1 = "ATI Technologies Inc Installation Disk #1 (System)"
ATI = "ATI Technologies Inc"
''',
'''
[Version]
Signature="$WINDOWS NT$"
Class=Processor
ClassGuid={50127DC3-0F36-415e-A6CC-4CB3BE910B65}
Provider=%AMD%
DriverVer=10/26/2004, 1.2.2.0
CatalogFile=AmdK8.cat

[DestinationDirs]
DefaultDestDir = 12

[SourceDisksNames]
1 = %DiskDesc%,,, 

[SourceDisksFiles]
AmdK8.sys = 1

[ControlFlags]
;
; Exclude all devices from Select Device list
;
ExcludeFromSelect = *

[ClassInstall32]
AddReg=Processor_Class_Addreg

[Processor_Class_Addreg]
HKR,,,0,%ProcessorClassName%
HKR,,NoInstallClass,,1
HKR,,Icon,,"-28"

[Manufacturer]
%AMD%=AmdK8

[AmdK8]
%AmdK8.DeviceDesc% = AmdK8_Inst,ACPI\AuthenticAMD_-_x86_Family_15
%AmdK8.DeviceDesc% = AmdK8_Inst,ACPI\AuthenticAMD_-_AMD64_Family_15

[AmdK8_Inst.NT]
Copyfiles = @AmdK8.sys

[AmdK8_Inst.NT.Services]
AddService = AmdK8,%SPSVCINST_ASSOCSERVICE%,AmdK8_Service_Inst,AmdK8_EventLog_Inst

[AmdK8_Service_Inst]
DisplayName    = %AmdK8.SvcDesc%
ServiceType    = %SERVICE_KERNEL_DRIVER%
StartType      = %SERVICE_SYSTEM_START%
ErrorControl   = %SERVICE_ERROR_NORMAL%
ServiceBinary  = %12%\AmdK8.sys
LoadOrderGroup = Extended Base
AddReg         = AmdK8_Inst_AddReg

[AmdK8_Inst_AddReg]
HKR,"Parameters",Capabilities,0x00010001,0x80

[AmdK8_EventLog_Inst]
AddReg = AmdK8_EventLog_AddReg

[AmdK8_EventLog_AddReg]
HKR,,EventMessageFile,0x00020000,"%%SystemRoot%%\System32\IoLogMsg.dll;%%SystemRoot%%\System32\drivers\AmdK8.sys"
HKR,,TypesSupported,0x00010001,7

[strings]
AMD                   = "Advanced Micro Devices"
ProcessorClassName    = "Processors"
AmdK8.DeviceDesc      = "AMD K8 Processor"
AmdK8.SvcDesc         = "AMD Processor Driver"
DiskDesc              = "AMD Processor Driver Disk"

SPSVCINST_ASSOCSERVICE= 0x00000002
SERVICE_KERNEL_DRIVER = 1
SERVICE_SYSTEM_START  = 1
SERVICE_ERROR_NORMAL  = 1
''',
'''
;
; SYMMPI.INF - version XP.10 (Windows XP)
;
; This is the INF file for Windows XP for the SYMMPI based PCI MPI
; environment
;
; ********************************************************************
;                                                                    *
;   Copyright 2005 LSI Logic, Inc. All rights reserved.              *
;                                                                    *
;   This file is property of LSI Logic, Inc. and is licensed for     *
;   use as is.  The receipt of or possession of this file does not   *
;   convey any rights to modify its contents, in whole, or in part,  *
;   without the specific written consent of LSI Logic, Inc.          *
;                                                                    *
; ********************************************************************

[version]
signature="$Windows NT$"
Class=SCSIAdapter
ClassGUID={4D36E97B-E325-11CE-BFC1-08002BE10318}
Provider=%LSI%
DriverVer=08/04/2006,1.21.25.00
CatalogFile.ntx86=mpixp32.cat

[DestinationDirs]
DefaultDestDir = 12 ; DIRID_DRIVERS

[SourceDisksFiles.x86]
symmpi.sys = 1
lsipseud.inf = 1

[SourceDisksNames]
1 = %DiskDesc%,,

[Manufacturer]
%LSI%=LSI
%DELL%=DELL

[LSI]
%DevDesc2% = SYMMPI_Inst, PCI\VEN_1000&DEV_0622
%DevDesc3% = SYMMPI_Inst, PCI\VEN_1000&DEV_0624
%DevDesc4% = SYMMPI_Inst, PCI\VEN_1000&DEV_0626
%DevDesc5% = SYMMPI_Inst, PCI\VEN_1000&DEV_0628
%DevDesc6% = SYMMPI_Inst, PCI\VEN_1000&DEV_0030
%DevDesc7% = SYMMPI_Inst, PCI\VEN_1000&DEV_0032
%DevDesc8% = SYMMPI_Inst, PCI\VEN_1000&DEV_0050
%DevDesc9% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054
%DevDesc10% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058
%DevDesc11% = SYMMPI_Inst, PCI\VEN_1000&DEV_0056
%DevDesc12% = SYMMPI_Inst, PCI\VEN_1000&DEV_0640
%DevDesc13% = SYMMPI_Inst, PCI\VEN_1000&DEV_0646
%DevDesc14% = SYMMPI_Inst, PCI\VEN_1000&DEV_0062

[DELL]
%DevDescD1% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F041028
%DevDescD2% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F051028
%DevDescD3% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F061028
%DevDescD4% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F071028
%DevDescD5% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F081028
%DevDescD6% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F091028
%DevDescD7% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F0E1028
%DevDescD8% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F0F1028
%DevDescD9% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F101028

[ControlFlags]
ExcludeFromSelect = *

[SYMMPI_Inst]
CopyFiles = SYMMPI_CopyFiles
AddReg = SYMMPI_AddReg
CopyINF = lsipseud.inf

[SYMMPI_Inst.HW]
AddReg = Shutdown_addreg
DelReg = LegacyScsiportValues

[SYMMPI_Inst.Services]
AddService = SYMMPI, %SPSVCINST_ASSOCSERVICE%, SYMMPI_Service_Inst, Miniport_EventLog_Inst

[SYMMPI_Service_Inst]
ServiceType    = %SERVICE_KERNEL_DRIVER%
StartType      = %SERVICE_BOOT_START%
ErrorControl   = %SERVICE_ERROR_NORMAL%
ServiceBinary  = %12%\symmpi.sys
LoadOrderGroup = SCSI Miniport
AddReg         = pnpsafe_pci_addreg
AddReg         = bus_type_scsi

[SYMMPI_CopyFiles]
symmpi.sys,,,1

[SYMMPI_AddReg]
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,DriverParameter,0x00000002,"EnablePseudoDevice=1;"
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,MaximumSGList,0x00010001,0xFF
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,NumberOfRequests,0x00010001,0xFF

[Shutdown_addreg]
HKR,"ScsiPort","NeedsSystemShutdownNotification",0x00010001,1

[LegacyScsiportValues]
HKR,Scsiport,BusNumber
HKR,Scsiport,LegacyInterfaceType
HKR,Scsiport,SlotNumber

[pnpsafe_pci_addreg]
HKR, "Parameters\PnpInterface", "5", 0x00010001, 0x00000001

[bus_type_scsi]
HKR, "Parameters", "BusType", 0x00010001, 0x00000001

[Miniport_EventLog_Inst]
AddReg = Miniport_EventLog_AddReg

[Miniport_EventLog_AddReg]
HKR,,EventMessageFile,%REG_EXPAND_SZ%,"%%SystemRoot%%\System32\IoLogMsg.dll"
HKR,,TypesSupported,%REG_DWORD%,7

[Strings]
LSI = "LSI Logic"
DELL = "Dell"
DiskDesc = "LSI Logic PCI Fusion-MPT Driver Install Disk"
DevDesc2 = "LSI Adapter, 2Gb FC, models 44929, G2 with 929"
DevDesc3 = "LSI Adapter, 2Gb FC, models 40919 with 919"
DevDesc4 = "LSI Adapter, 2Gb FC, models 7202,7402 with 929X"
DevDesc5 = "LSI Adapter, 2Gb FC, models 7102 with 919X"
DevDesc6 = "LSI Adapter, Ultra320 SCSI 2000 series, w/1020/1030"
DevDesc7 = "LSI Adapter, Ultra320 SCSI RAID series, w/1035"
DevDesc8 = "LSI Adapter, SAS 3000 series, 4-port with 1064"
DevDesc9 = "LSI Adapter, SAS 3000 series, 8-port with 1068"
DevDesc10 = "LSI Adapter, SAS 3000 series, 8-port with 1068E"
DevDesc11 = "LSI Adapter, SAS 3000 series, 4-port with 1064E"
DevDesc12 = "LSI Adapter, 4Gb FC, models 7104,7204,7404 with 949X"
DevDesc13 = "LSI Adapter, 4Gb FC, models 7104,7204,7404 with 949E"
DevDesc14 = "LSI Adapter, SAS RAID-on-Chip, 8-port with 1078"
DevDescD1 = "Dell SAS 5/E Adapter"
DevDescD2 = "Dell SAS 5/i Adapter"
DevDescD3 = "Dell SAS 5/i Integrated"
DevDescD4 = "Dell SAS 5/iR Integrated D/C"
DevDescD5 = "Dell SAS 5/iR Integrated Emb"
DevDescD6 = "Dell SAS 5/iR Adapter"
DevDescD7 = "Dell SAS 6/iR Adapter"
DevDescD8 = "Dell SAS 6/iR Integrated"
DevDescD9 = "Dell SAS 6/i Integrated"

;*******************************************
;Handy macro substitutions (non-localizable)
SPSVCINST_ASSOCSERVICE = 0x00000002
SERVICE_KERNEL_DRIVER  = 1
SERVICE_BOOT_START     = 0
SERVICE_ERROR_NORMAL   = 1
REG_EXPAND_SZ          = 0x00020000
REG_DWORD              = 0x00010001
'''
,
'''
;
;   SER2PL.INF (for Windows 2000)
;
;   Copyright (c) 2000, Prolific Technology Inc.

[version]
signature="$Windows NT$"
Class=Ports
ClassGuid={4D36E978-E325-11CE-BFC1-08002BE10318}
Provider=%Pro%
catalogfile=pl2303.cat
DriverVer=12/31/2002,2.0.0.7

[SourceDisksNames]
1=%Pro.Disk%,,,

[ControlFlags]
ExcludeFromSelect = USB\VID_067b&PID_2303

[SourceDisksFiles]
ser2pl.sys=1

[DestinationDirs]
DefaultDestDir=12
ComPort.NT.Copy=12

[Manufacturer]
%Pro%=Pro

[Pro]
%DeviceDesc% = ComPort, USB\VID_067B&PID_2303

[ComPort.NT]
CopyFiles=ComPort.NT.Copy
AddReg=ComPort.NT.AddReg

[ComPort.NT.HW]
AddReg=ComPort.NT.HW.AddReg

[ComPort.NT.Copy]
ser2pl.sys

[ComPort.NT.AddReg]
HKR,,DevLoader,,*ntkern
HKR,,NTMPDriver,,ser2pl.sys
HKR,,EnumPropPages32,,"MsPorts.dll,SerialPortPropPageProvider"

[ComPort.NT.HW.AddReg]
HKR,,"UpperFilters",0x00010000,"serenum"

[ComPort.NT.Services]
AddService = Ser2pl, 0x00000002, Serial_Service_Inst
AddService = Serenum,,Serenum_Service_Inst

[Serial_Service_Inst]
DisplayName    = %Serial.SVCDESC%
ServiceType    = 1               ; SERVICE_KERNEL_DRIVER
StartType      = 3               ; SERVICE_SYSTEM_START (this driver may do detection)
ErrorControl   = 1               ; SERVICE_ERROR_IGNORE
ServiceBinary  = %12%\ser2pl.sys
LoadOrderGroup = Base

[Serenum_Service_Inst]
DisplayName    = %Serenum.SVCDESC%
ServiceType    = 1               ; SERVICE_KERNEL_DRIVER
StartType      = 3               ; SERVICE_DEMAND_START
ErrorControl   = 1               ; SERVICE_ERROR_NORMAL
ServiceBinary  = %12%\serenum.sys
LoadOrderGroup = PNP Filter

[linji]
Pro = "Prolific"
Pro.Disk="USB-Serial Cable Diskette"
DeviceDesc = "Prolific USB-to-Serial Comm Port"
Serial.SVCDESC   = "Prolific Serial port driver"
Serenum.SVCDESC = "Serenum Filter Driver"
'''
,
'''
[Version]
CatalogFile=RTHDMI32.cat
Signature = "$chicago$"
Class=MEDIA
ClassGuid={4d36e96c-e325-11ce-bfc1-08002be10318}
Provider=%OrganizationName%
DriverPackageType=PlugAndPlay
DriverPackageDisplayName=%PackageDisplayName%
DriverVer=03/02/2007, 5.10.0.5368

[Manufacturer]
%MfgName% = AzaliaManufacturerID

[ControlFlags]
ExcludeFromSelect = *

[AzaliaManufacturerID]
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_791A
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_793C
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA01
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA09
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA11
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA19

[SourceDisksNames]
222="Realtek HD Audio Installation Disk",,,

[SourceDisksFiles]
RtHDMI.sys=222
RtkUpd.exe=222

[DestinationDirs]
DefaultDestDir=10; dirid = \system32\drivers
RtAzAudModelCopyFiles = 10,system32\drivers
RTUninstall.CopyList = 10           ;; WINDOWS

[RtAzAudModelCopyFiles]
RtHDMI.sys

[RTUninstall.CopyList]
RtkUpd.exe

[RtAzAudModel.NTX86]
Include=ks.inf,wdmaudio.inf
Needs=KS.Registration,WDMAUDIO.Registration
CopyFiles = RtAzAudModelCopyFiles, RTUninstall.CopyList
AddReg    = RtAzAudModelAddReg, DS3DConfiguration.AddReg, RTUninstall.AddReg

[RtAzAudModel.NTX86.HW]
AddReg=HdAudSecurity.AddReg

[RtAzAudModel.NTX86.Services]
AddService = RTHDMIAzAudService, 0x00000002, RTHDMIAzAudServiceInstall

[RTHDMIAzAudServiceInstall]
DisplayName   = "Service for HDMI"
ServiceType   = 1
StartType     = 3
ErrorControl  = 1
ServiceBinary = %10%\system32\drivers\RtHDMI.sys


[RtAzAudModel.NTX86.Interfaces]
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifWave%, RtAzAudModel.RtSpdifWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifWave%, RtAzAudModel.RtSpdifWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifTopo%, RtAzAudModel.RtSpdifTopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifTopo%, RtAzAudModel.RtSpdifTopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifHDMIWave%, RtAzAudModel.RtSpdifHDMIWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifHDMIWave%, RtAzAudModel.RtSpdifHDMIWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifHDMITopo%, RtAzAudModel.RtSpdifHDMITopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifHDMITopo%, RtAzAudModel.RtSpdifHDMITopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifRCAWave%, RtAzAudModel.RtSpdifRCAWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifRCAWave%, RtAzAudModel.RtSpdifRCAWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifRCATopo%, RtAzAudModel.RtSpdifRCATopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifRCATopo%, RtAzAudModel.RtSpdifRCATopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifOptWave%, RtAzAudModel.RtSpdifOptWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifOptWave%, RtAzAudModel.RtSpdifOptWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifOptTopo%, RtAzAudModel.RtSpdifOptTopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifOptTopo%, RtAzAudModel.RtSpdifOptTopo

[DS3DConfiguration.AddReg]
HKR,DS3D,ForwardSpeakerConfiguration,0x00010001,0
HKR,DS3D,IgnoreDSSpeakerConfiguration,0x00010001,1
HKR,"DS3D\OldArch",ForwardSpeakerConfiguration,0x00010001,0
HKR,"DS3D\OldArch",IgnoreDSSpeakerConfiguration,0x00010001,1

[RTUninstall.AddReg]
HKLM,%RT_UNINSTALL%,DisplayName,,"Realtek High Definition Audio Driver"
HKLM,%RT_UNINSTALL%,UninstallString,,"RtkUpd.exe -r -m"

[HdAudSecurity.AddReg]
HKR,,DeviceType,0x10001,0x0000001D

[RtAzAudModelAddReg]
HKR,,AssociatedFilters,,"wdmaud,swmidi,redbook"
HKR,,Driver,,RtHDMI.sys

HKR,Drivers,SubClasses,,"wave,midi,mixer,aux"

HKR,Drivers\wave\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\midi\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\mixer\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\aux\wdmaud.drv,Driver,,wdmaud.drv

HKR,Drivers\wave\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\midi\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\mixer\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\aux\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%

HKR,,SetupPreferredAudioDevices,3,01,00,00,00

[RtAzAudModel.RtSpdifWave]
AddReg = RtAzAudModel.RtSpdifWave.AddReg
[RtAzAudModel.RtSpdifWave.AddReg]
HKR,,FriendlyName,,%RtSpdifWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifTopo]
AddReg = RtAzAudModel.RtSpdifTopo.AddReg
[RtAzAudModel.RtSpdifTopo.AddReg]
HKR,,FriendlyName,,%RtSpdifTopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[RtAzAudModel.RtSpdifHDMIWave]
AddReg = RtAzAudModel.RtSpdifHDMIWave.AddReg
[RtAzAudModel.RtSpdifHDMIWave.AddReg]
HKR,,FriendlyName,,%RtSpdifHDMIWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifHDMITopo]
AddReg = RtAzAudModel.RtSpdifHDMITopo.AddReg

[RtAzAudModel.RtSpdifHDMITopo.AddReg]
HKR,,FriendlyName,,%RtSpdifHDMITopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

HKLM,%MediaCategories%\%GUID.RTSPDIFOut%,Name,,%Node.RTSPDIFOut%
HKLM,%MediaCategories%\%GUID.RTSPDIFOut%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTHDMIOut%,Name,,%Node.RTHDMIOut%
HKLM,%MediaCategories%\%GUID.RTHDMIOut%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTSPDIFOutRCA%,Name,,%Node.RTSPDIFOutRCA%
HKLM,%MediaCategories%\%GUID.RTSPDIFOutRCA%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTSPDIFOutOpt%,Name,,%Node.RTSPDIFOutOpt%
HKLM,%MediaCategories%\%GUID.RTSPDIFOutOpt%,Display,1,00,00,00,00

[RtAzAudModel.RtSpdifRCAWave]
AddReg = RtAzAudModel.RtSpdifRCAWave.AddReg
[RtAzAudModel.RtSpdifRCAWave.AddReg]
HKR,,FriendlyName,,%RtSpdifRCAWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifRCATopo]
AddReg = RtAzAudModel.RtSpdifRCATopo.AddReg
[RtAzAudModel.RtSpdifRCATopo.AddReg]
HKR,,FriendlyName,,%RtSpdifRCATopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[RtAzAudModel.RtSpdifOptWave]
AddReg = RtAzAudModel.RtSpdifOptWave.AddReg
[RtAzAudModel.RtSpdifOptWave.AddReg]
HKR,,FriendlyName,,%RtSpdifOptWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifOptTopo]
AddReg = RtAzAudModel.RtSpdifOptTopo.AddReg
[RtAzAudModel.RtSpdifOptTopo.AddReg]
HKR,,FriendlyName,,%RtSpdifOptTopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[Strings]
MfgName="Realtek"
MediaCategories="SYSTEM\CurrentControlSet\Control\MediaCategories"

OrganizationName="Realtek Semiconductor Corp."
PackageDisplayName="HD Audio Driver"
IntcAzAudioDeviceDescription = "Realtek High Definition Audio"

RT_UNINSTALL="Software\Microsoft\Windows\CurrentVersion\Uninstall\{F132AF7F-7BCA-4EDE-8A7C-958108FE7DBC}"

KSNAME_RtSpdifWave="RtSpdifWave"
KSNAME_RtSpdifTopo="RtSpdifTopo"
KSNAME_RtSpdifHDMIWave="RtSpdifHDMIWave"
KSNAME_RtSpdifHDMITopo="RtSpdifHDMITopo"
KSNAME_RtSpdifRCAWave="RtSpdifRCAWave"
KSNAME_RtSpdifRCATopo="RtSpdifRCATopo"
KSNAME_RtSpdifOptWave="RtSpdifOptWave"
KSNAME_RtSpdifOptTopo="RtSpdifOptTopo"

RtSpdifWaveDeviceName="Realtek HDA SPDIF Out"
RtSpdifTopoDeviceName="Realtek HDA SPDIF Out Mixer"
RtSpdifHDMIWaveDeviceName="Realtek HDA HDMI Out"
RtSpdifHDMITopoDeviceName="Realtek HDA HDMI Out Mixer"
RtSpdifRCAWaveDeviceName="Realtek HDA SPDIF RCA Out"
RtSpdifRCATopoDeviceName="Realtek HDA SPDIF RCA Out Mixer"
RtSpdifOptWaveDeviceName="Realtek HDA SPDIF Optical Out"
RtSpdifOptTopoDeviceName="Realtek HDA SPDIF Optical Out Mixer"


KSCATEGORY_AUDIO = "{6994AD04-93EF-11D0-A3CC-00A0C9223196}"
KSCATEGORY_RENDER="{65E8773E-8F56-11D0-A3B9-00A0C9223196}"
KSCATEGORY_CAPTURE="{65E8773D-8F56-11D0-A3B9-00A0C9223196}"
KSCATEGORY_TOPOLOGY="{DDA54A40-1E4C-11D1-A050-405705C10000}"
Proxy.CLSID ="{17CCA71B-ECD7-11D0-B908-00A0C9223196}"

GUID.RTSPDIFOut			="{8FD300D2-FFE1-44f3-A9EB-6F4395D73C9F}"
Node.RTSPDIFOut			="Realtek Digital Output"
GUID.RTHDMIOut			="{9C8E490E-877D-48fe-9EF1-AD83C91CC057}"
Node.RTHDMIOut			="Realtek HDMI Output"
GUID.RTSPDIFOutRCA		="{3FF4EDB6-3FF3-4b5a-B164-10FFF0367547}"
Node.RTSPDIFOutRCA		="Realtek Digital Output(RCA)"
GUID.RTSPDIFOutOpt		="{94FCA009-B26E-4cdc-AC75-051613EF01BB}"
Node.RTSPDIFOutOpt		="Realtek Digital Output(Optical)"
'''
,
'''
; Copyright (C) 2002-2008  NVIDIA Corporation
; Unauthorized copying or use without explicit permission of NVIDIA
; is prohibited
;
[Version] 
Signature = "$Windows NT$" 
Class=HDC
ClassGUID={4d36e96a-e325-11ce-bfc1-08002be10318} 
Provider=%NVIDIA% 
CatalogFile=nvata.cat
DriverVer=11/12/2008,10.3.0.46

[DestinationDirs] 
NVStor.Files.x86_12 = 12 
NVStor.CoInstFiles = 11


[SourceDisksNames.x86]
0=%Desc_x860%

[SourceDisksFiles.x86]
nvgts.sys=0
nvraidco.dll=0
NvRCoAr.dll=0
NvRCoCs.dll=0
NvRCoDa.dll=0
NvRCoDe.dll=0
NvRCoEl.dll=0
NvRCoEng.dll=0
NvRCoENU.dll=0
NvRCoEs.dll=0
NvRCoEsm.dll=0
NvRCoFi.dll=0
NvRCoFr.dll=0
NvRCoHe.dll=0
NvRCoHu.dll=0
NvRCoIt.dll=0
NvRCoJa.dll=0
NvRCoKo.dll=0
NvRCoNl.dll=0
NvRCoNo.dll=0
NvRCoPl.dll=0
NvRCoPt.dll=0
NvRCoPtb.dll=0
NvRCoRu.dll=0
NvRCoSk.dll=0
NvRCoSl.dll=0
NvRCoSv.dll=0
NvRCoTh.dll=0
NvRCoTr.dll=0
NvRCoZhc.dll=0
NvRCoZht.dll=0

[Manufacturer] 
%NVIDIA%=NVIDIA, ntx86, ntx86.6.0


[NVIDIA.ntx86.6.0]

[NVIDIA]
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0054&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0055&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0266&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0267&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_037F&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_03F6&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_044D&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0554&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0555&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_07F4&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AD5&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AD4&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AB9&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AB8&CC_0106

[NVIDIA.ntx86]
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0054&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0055&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0266&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0267&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_037F&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_03F6&CC_0101
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_044D&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0554&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0555&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_07F4&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AD5&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AD4&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AB9&CC_0106
%NVSTOR_DESC%=NVStor_Inst,PCI\VEN_10DE&DEV_0AB8&CC_0106

                                           
[NVStor_Inst.ntx86] 
CopyFiles = NVStor.Files.x86_12

[NVStor_Inst.ntx86.HW] 
AddReg=NVStor_Inst.ntx86.AddReg.HW

[NVStor_Inst.ntx86.AddReg.HW]
; allow access from system and administrator only
HKR,,"Security",,"D:P(A;;GA;;;SY)(A;;GA;;;BA)"

[NVStor_Inst.ntx86.CoInstallers]
CopyFiles = NVStor.CoInstFiles
AddReg = NVStor_Inst.CoInst_AddReg

[NVStor_Inst.CoInst_AddReg]
HKR,,CoInstallers32,0x00010000,		\
	"nvraiins.dll,NvRaidCoInstaller"


HKR, Uninstall, Script,0,"nvide.nvu"
HKR, Uninstall, Name,0,"NVIDIA IDE Driver"
HKR, Uninstall, INFSrcDir, 0, %01% 
HKR, Uninstall, Uninstaller,0,"nvuide.exe"

[NVStor_Inst.ntx86.Services] 
AddService = nvgts,0x00000002,NVStor_Service_Instx86,NVStor_EventLog_Instx86

[NVStor_Service_Instx86] 
ServiceType = %SERVICE_KERNEL_DRIVER% 
StartType = %SERVICE_BOOT_START% 
ErrorControl = %SERVICE_ERROR_CRITICAL% 
ServiceBinary = %12%\nvgts.sys
LoadOrderGroup = "SCSI Miniport"
AddReg = NVStor_DisableFltCache_AddReg
AddReg = pnpsafe_pci_addreg

[NVStor_EventLog_Instx86]
AddReg = NVStor_EventLog_AddReg

[NVStor_EventLog_AddReg]
HKR,,EventMessageFile,0x00020000,"%%SystemRoot%%\System32\IoLogMsg.dll;%%SystemRoot%%\System32\drivers\nvgts.sys"
HKR,,TypesSupported,0x00010001,7 

[NVStor_DisableFltCache_AddReg]
HKR,,DisableFilterCache,0x00010001,1

[pnpsafe_pci_addreg]
HKR, "Parameters\PnpInterface", "5", %REG_DWORD%, 0x00000001
HKR, "Parameters", "BusType", %REG_DWORD%, 0x00000003 ;; bus type =  ATA (0x3)


[NVStor.Files.x86_12] 
nvgts.sys

[NVStor.CoInstFiles]
nvraidco.dll
nvraiins.dll,nvraidco.dll
NvRCoAr.dll
NvRCoCs.dll
NvRCoDa.dll
NvRCoDe.dll
NvRCoEl.dll
NvRCoEng.dll
NvRCoENU.dll
NvRCoEs.dll
NvRCoEsm.dll
NvRCoFi.dll
NvRCoFr.dll
NvRCoHe.dll
NvRCoHu.dll
NvRCoIt.dll
NvRCoJa.dll
NvRCoKo.dll
NvRCoNl.dll
NvRCoNo.dll
NvRCoPl.dll
NvRCoPt.dll
NvRCoPtb.dll
NvRCoRu.dll
NvRCoSk.dll
NvRCoSl.dll
NvRCoSv.dll
NvRCoTh.dll
NvRCoTr.dll
NvRCoZhc.dll
NvRCoZht.dll



[Strings] 

;  *******Localizable Strings******* 
NVIDIA= "NVIDIA Corporation" 
Desc_x860= "SRCDATA" 
NVSTOR_DESC= "NVIDIA nForce Serial ATA Controller"

;  *******Non Localizable Strings******* 

SERVICE_BOOT_START = 0x0 
SERVICE_SYSTEM_START = 0x1 
SERVICE_AUTO_START = 0x2 
SERVICE_DEMAND_START = 0x3 
SERVICE_DISABLED = 0x4 

SERVICE_KERNEL_DRIVER = 0x1 
SERVICE_ERROR_IGNORE = 0x0 
SERVICE_ERROR_NORMAL = 0x1 
SERVICE_ERROR_SEVERE = 0x2 
SERVICE_ERROR_CRITICAL = 0x3 

REG_EXPAND_SZ = 0x00020000 
REG_DWORD = 0x00010001 
'''
]

txtsetupoemTestData = \
[
'''
;
; format for txtsetup.oem.
;
; Follow this format for non-PNP adapters ISA
;
; Follow the txtsetup.oem in initio for PNP adapters like PCI and ISAPNP
;
; Txtsetup.oem is a generic way to install Storage adapters to get them through
; textmode setup.  Do as little as possible and allow GUI mode setup to do the 
; remaining work using the supplied inf.
;
; General format:
;
; [section]
; key = value1,value2,...
;
;
; The hash ('#') or semicolon (';') introduces a comment.
; Strings with embedded spaces, commas, or hashes should be double-quoted
;


; This section lists all disks in the disk set.
;
; <description> is a descriptive name for a disk, used when
;   prompting for the disk
; <tagfile> is a file whose presence allows setup to recognize
;   that the disk is inserted.
; <directory> is where the files are located on the disk.
;
[Disks]
d1 = "NVIDIA AHCI DRIVER (SCSI)",\\disk1,\\testdir

; This section lists the default selection for each 'required'
; hardware component.  If a line is not present for a component,
; the default defaults to the first item in the [<component_name>]
; section (see below).
;
; <component_name> is one of computer, display, keyboard, mouse, scsi
; <id> is a unique <within the component> string to be associated
;   with an option.
[Defaults]


; This section lists the options available for a particular component.
;
; <id> is the unique string for the option
; <description> is a text string, presented to the user in a menu
; <key_name> gives the name of the key to be created for the component in
;   HKEY_LOCAL_MACHINE\ControlSet001\Services
[scsi]
BUSDRV = "NVIDIA nForce Storage Controller (required)"


; This section lists the files that should be copied if the user
; selects a particular component option.
;
; <file_type> is one of driver, port, class, dll, hal, inf, or detect.
;   See below.
; <source_disk> identifies where the file is to be copied from, and must
;   match en entry in the [Disks] section.
; <filename> is the name of the file. This will be appended to the
;   directory specified for the disk in the [Disks] section to form the
;   full path of the file on the disk.
; <driverkey> this is the name that will show under the services\driver key
; this should be the same name as the driver that is being installed.

[Files.scsi.BUSDRV]
driver = d1,nvgts.sys,BUSDRV
inf    = d1, nvgts.inf
catalog = d1, nvata.cat
dll    = d1,nvraidco.dll
dll     = d1,NvRCoENU.dll
dll     = d1,NvRCoAr.dll
dll     = d1,NvRCoCs.dll
dll     = d1,NvRCoDa.dll
dll     = d1,NvRCoDe.dll
dll     = d1,NvRCoEl.dll
dll     = d1,NvRCoEng.dll
dll     = d1,NvRCoEs.dll
dll     = d1,NvRCoEsm.dll
dll     = d1,NvRCoFi.dll
dll     = d1,NvRCoFr.dll
dll     = d1,NvRCoHe.dll
dll     = d1,NvRCoHu.dll
dll     = d1,NvRCoIt.dll
dll     = d1,NvRCoJa.dll
dll     = d1,NvRCoKo.dll
dll     = d1,NvRCoNl.dll
dll     = d1,NvRCoNo.dll
dll     = d1,NvRCoPl.dll
dll     = d1,NvRCoPt.dll
dll     = d1,NvRCoPtb.dll
dll     = d1,NvRCoRu.dll
dll     = d1,NvRCoSk.dll
dll     = d1,NvRCoSl.dll
dll     = d1,NvRCoSv.dll
dll     = d1,NvRCoTh.dll
dll     = d1,NvRCoTr.dll
dll     = d1,NvRCoZhc.dll
dll     = d1,NvRCoZht.dll

; This section specifies values to be set in the registry for
; particular component options.  Required values in the services\\xxx
; key are created automatically -- use this section to specify additional
; keys to be created in services\\xxx and values in services\\xxx and
; services\\xxx\\yyy.
;
; This section must be filled out for storage controllers that 
; are PNP adapters like PCI and ISA PNP adapters.  Failure to do this 
; can cause the driver to fail to load. Must also add the section
; [HardwareIds.scsi.ID] to identify the supported ID's.
;
; <value_name> specifies the value to be set within the key
; <value_type> is a string like REG_DWORD.  See below.
; <value> specifies the actual value; its format depends on <value_type>
;

[Config.BUSDRV]
value = parameters\PnpInterface,5,REG_DWORD,1

; A HardwareIds.scsi.Service section specifies the hardware IDs of 
; the devices that a particular mass-storage driver supports. 
;
; [HardwareIds.scsi.Service]
; id = "deviceID","service"
;
; HardwareIds.scsi.Service 
;   Service specifies the service to be installed. 
;
; <deviceId > Specifies the device ID for a mass-storage device. 
; <service > Specifies the service to be installed for the device. 
;The following example excerpt shows a HardwareIds.scsi.Service section for a disk device:
;


[HardwareIds.scsi.BUSDRV]
id = "PCI\VEN_10DE&DEV_0036", "nvgts"
id = "PCI\VEN_10DE&DEV_003E", "nvgts"
id = "PCI\VEN_10DE&DEV_0054", "nvgts"
id = "PCI\VEN_10DE&DEV_0055", "nvgts"
id = "PCI\VEN_10DE&DEV_0266", "nvgts"
id = "PCI\VEN_10DE&DEV_0267", "nvgts"
id = "PCI\VEN_10DE&DEV_037E", "nvgts"
id = "PCI\VEN_10DE&DEV_037F", "nvgts"
id = "PCI\VEN_10DE&DEV_036F", "nvgts"
id = "PCI\VEN_10DE&DEV_03F6", "nvgts"
id = "PCI\VEN_10DE&DEV_03F7", "nvgts"
id = "PCI\VEN_10DE&DEV_03E7", "nvgts"
id = "PCI\VEN_10DE&DEV_044D", "nvgts"
id = "PCI\VEN_10DE&DEV_044E", "nvgts"
id = "PCI\VEN_10DE&DEV_044F", "nvgts"
id = "PCI\VEN_10DE&DEV_0554", "nvgts"
id = "PCI\VEN_10DE&DEV_0555", "nvgts"
id = "PCI\VEN_10DE&DEV_0556", "nvgts"
id = "PCI\VEN_10DE&DEV_07F4", "nvgts"
id = "PCI\VEN_10DE&DEV_07F5", "nvgts"
id = "PCI\VEN_10DE&DEV_07F6", "nvgts"
id = "PCI\VEN_10DE&DEV_07F7", "nvgts"
id = "PCI\VEN_10DE&DEV_0768", "nvgts"
id = "PCI\VEN_10DE&DEV_0AD5", "nvgts"
id = "PCI\VEN_10DE&DEV_0AD4", "nvgts"
id = "PCI\VEN_10DE&DEV_0AB9", "nvgts"
id = "PCI\VEN_10DE&DEV_0AB8", "nvgts"
id = "PCI\VEN_10DE&DEV_0BCC", "nvgts"
id = "PCI\VEN_10DE&DEV_0BCD", "nvgts"

#--The following lines give additional USB floppy support
id = "USB\VID_03F0&PID_2001", "usbstor" #--HP
id = "USB\VID_054C&PID_002C", "usbstor" #--Sony
id = "USB\VID_057B&PID_0001", "usbstor" #--Y-E Data
id = "USB\VID_0409&PID_0040", "usbstor" #--NEC
id = "USB\VID_0424&PID_0FDC", "usbstor" #--SMSC
id = "USB\VID_08BD&PID_1100", "usbstor" #--Iomega
id = "USB\VID_055D&PID_2020", "usbstor" #--Samsung

id = "USB\VID_03EE&PID_6901", "usbstor" #--Mitsumi
''',
'''
# txtsetup.oem - version XP.8 for SYMMPI Windows XP driver
#
# ***********************************************************************
#                                                                       *
#   Copyright 2004 LSI Logic, Corp.  All rights reserved.               *
#                                                                       *
#   This file is property of LSI Logic, Corp. and is licensed for       *
#   use as is.  The receipt of or posession of this file does not       *
#   convey any rights to modify its contents, in whole, or in part,     *
#   without the specific written consent of LSI Logic, Corp.            *
#                                                                       *
# ***********************************************************************
#
# format for txtsetup.oem.
#
# General format:
#
# [section]
# key = value1,value2,...
#
#
# The hash ('#') introduces a comment.
# Strings with embedded spaces, commas, or hashes should be double-quoted
#


[Disks]

# This section lists all disks in the disk set.
#
# <description> is a descriptive name for a disk, used when
#   prompting for the disk
# <tagfile> is a file whose presence allows setup to recognize
#   that the disk is inserted.
# <directory> is where the files are located on the disk.
#

d1 = "LSI Logic PCI Fusion-MPT Miniport Driver",\symmpi.tag,\


[Defaults]

# This section lists the default selection for each 'required'
# hardware component.  If a line is not present for a component,
# the default defaults to the first item in the [<component_name>]
# section (see below).
#
# <component_name> is one of computer, display, keyboard, mouse, scsi
# <id> is a unique <within the component> string to be associated
#   with an option.

scsi = SYMMPI_32


[scsi]

# This section lists the options available for a particular component.
#
# <id> is the unique string for the option
# <description> is a text string, presented to the user in a menu
# <key_name> gives the name of the key to be created for the component in
#   HKEY_LOCAL_MACHINE\ControlSet001\Services

SYMMPI_32    = "LSI Logic PCI Fusion-MPT Driver (XP 32-bit)",symmpi


[HardwareIds.scsi.SYMMPI_32]

id = "PCI\VEN_1000&DEV_0622", "symmpi"
id = "PCI\VEN_1000&DEV_0624", "symmpi"
id = "PCI\VEN_1000&DEV_0626", "symmpi"
id = "PCI\VEN_1000&DEV_0628", "symmpi"
id = "PCI\VEN_1000&DEV_0030", "symmpi"
id = "PCI\VEN_1000&DEV_0032", "symmpi"
id = "PCI\VEN_1000&DEV_0050", "symmpi"
id = "PCI\VEN_1000&DEV_0054", "symmpi"
id = "PCI\VEN_1000&DEV_0058", "symmpi"
id = "PCI\VEN_1000&DEV_005E", "symmpi"
id = "PCI\VEN_1000&DEV_0056", "symmpi"
id = "PCI\VEN_1000&DEV_005A", "symmpi"
id = "PCI\VEN_1000&DEV_0640", "symmpi"
id = "PCI\VEN_1000&DEV_0646", "symmpi"
id = "PCI\VEN_1000&DEV_0062", "symmpi"


# This section lists the files that should be copied if the user
# selects a particular component option.
#
# <file_type> is one of driver, port, class, dll, hal, inf, or detect.
#   See below.
# <source_disk> identifies where the file is to be copied from, and must
#   match en entry in the [Disks] section.
# <filename> is the name of the file. This will be appended to the
#   directory specified for the disk in the [Disks] section to form the
#   full path of the file on the disk.

[Files.scsi.SYMMPI_32]
driver  = d1,symmpi.sys,SYMMPI
inf     = d1,symmpi.inf
inf     = d1,lsipseud.inf
catalog = d1,mpixp32.cat


[Config.SYMMPI]

# This section specifies values to be set in the registry for
# particular component options.  Required values in the services\\xxx
# key are created automatically -- use this section to specify additional
# keys to be created in services\\xxx and values in services\\xxx and
# services\\xxx\\yyy.
#
# <key_name> is relative to the services node for this device.
#   If it is empty, then it refers to the services node.
#   If specified, the key is created first.
# <value_name> specifies the value to be set within the key
# <value_type> is a string like REG_DWORD.  See below.
# <value> specifies the actual value; its format depends on <value_type>
value = Parameters\PnpInterface,5,REG_DWORD,1
''',
'''
[Disks]
d1 = "NVIDIA AHCI DRIVER (SCSI)",\disk1,\

[Defaults]

[scsi]
BUSDRV = "NVIDIA nForce Storage Controller (required)"

[Files.scsi.BUSDRV]
driver = d1,nvgts.sys,BUSDRV
inf    = d1, nvgts.inf
catalog = d1, nvata.cat
dll    = d1,nvraidco.dll
dll     = d1,NvRCoENU.dll
dll     = d1,NvRCoAr.dll
dll     = d1,NvRCoCs.dll
dll     = d1,NvRCoDa.dll
dll     = d1,NvRCoDe.dll
dll     = d1,NvRCoEl.dll
dll     = d1,NvRCoEng.dll
dll     = d1,NvRCoEs.dll
dll     = d1,NvRCoEsm.dll
dll     = d1,NvRCoFi.dll
dll     = d1,NvRCoFr.dll
dll     = d1,NvRCoHe.dll
dll     = d1,NvRCoHu.dll
dll     = d1,NvRCoIt.dll
dll     = d1,NvRCoJa.dll
dll     = d1,NvRCoKo.dll
dll     = d1,NvRCoNl.dll
dll     = d1,NvRCoNo.dll
dll     = d1,NvRCoPl.dll
dll     = d1,NvRCoPt.dll
dll     = d1,NvRCoPtb.dll
dll     = d1,NvRCoRu.dll
dll     = d1,NvRCoSk.dll
dll     = d1,NvRCoSl.dll
dll     = d1,NvRCoSv.dll
dll     = d1,NvRCoTh.dll
dll     = d1,NvRCoTr.dll
dll     = d1,NvRCoZhc.dll
dll     = d1,NvRCoZht.dll

[Config.BUSDRV]
value = parameters\PnpInterface,5,REG_DWORD,1

[HardwareIds.scsi.BUSDRV]
id = "PCI\VEN_10DE&DEV_0036", "nvgts"
id = "PCI\VEN_10DE&DEV_003E", "nvgts"
id = "PCI\VEN_10DE&DEV_0054", "nvgts"
id = "PCI\VEN_10DE&DEV_0055", "nvgts"
id = "PCI\VEN_10DE&DEV_0266", "nvgts"
id = "PCI\VEN_10DE&DEV_0267", "nvgts"
id = "PCI\VEN_10DE&DEV_037E", "nvgts"
id = "PCI\VEN_10DE&DEV_037F", "nvgts"
id = "PCI\VEN_10DE&DEV_036F", "nvgts"
id = "PCI\VEN_10DE&DEV_03F6", "nvgts"
id = "PCI\VEN_10DE&DEV_03F7", "nvgts"
id = "PCI\VEN_10DE&DEV_03E7", "nvgts"
id = "PCI\VEN_10DE&DEV_044D", "nvgts"
id = "PCI\VEN_10DE&DEV_044E", "nvgts"
id = "PCI\VEN_10DE&DEV_044F", "nvgts"
id = "PCI\VEN_10DE&DEV_0554", "nvgts"
id = "PCI\VEN_10DE&DEV_0555", "nvgts"
id = "PCI\VEN_10DE&DEV_0556", "nvgts"
id = "PCI\VEN_10DE&DEV_07F4", "nvgts"
id = "PCI\VEN_10DE&DEV_07F5", "nvgts"
id = "PCI\VEN_10DE&DEV_07F6", "nvgts"
id = "PCI\VEN_10DE&DEV_07F7", "nvgts"
id = "PCI\VEN_10DE&DEV_0768", "nvgts"
id = "PCI\VEN_10DE&DEV_0AD5", "nvgts"
id = "PCI\VEN_10DE&DEV_0AD4", "nvgts"
id = "PCI\VEN_10DE&DEV_0AB9", "nvgts"
id = "PCI\VEN_10DE&DEV_0AB8", "nvgts"
id = "PCI\VEN_10DE&DEV_0BCC", "nvgts"
id = "PCI\VEN_10DE&DEV_0BCD", "nvgts"
''',
'''
[Disks] 
disk0 = "AMD AHCI Compatible RAID Controller Driver Diskette", \\ahcix86, \\
disk1 = "AMD AHCI Compatible RAID Controller Driver Diskette", \\ahcix86, \\x86
disk2 = "AMD AHCI Compatible RAID Controller Driver Diskette", \\ahcix64, \\x64

[Defaults] 
SCSI = Napa_i386_ahci8086

[SCSI] 
Napa_i386_ahci8086 = "AMD AHCI Compatible RAID Controller-x86 platform", ahcix86 
Napa_amd64_ahci    = "AMD AHCI Compatible RAID Controller-x64 platform", ahcix64

[Files.SCSI.Napa_i386_ahci8086] 
inf	= disk1, ahcix86.inf
driver	= disk1, ahcix86.sys, ahcix86
catalog = disk1, ahcix86.cat

[Files.SCSI.Napa_amd64_ahci] 
inf	= disk2, ahcix64.inf
driver	= disk2, ahcix64.sys, ahcix64
catalog = disk2, ahcix64.cat

[HardwareIds.SCSI.Napa_i386_ahci8086] 
id = "PCI\VEN_1002&DEV_4380&SUBSYS_280A103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_2814103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_3029103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_3029103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E08105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E08105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_C2151631", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_C2151631", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_E2191631", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_E2191631", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_E2171631", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_E2171631", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE10105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE11105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE13105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE14105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE0E105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE0F105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_76401558", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_76411558", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_2A6E103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_2A6E103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E13105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E13105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E14105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E14105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_A7051478", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_A7051478", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_55021565", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_55021565", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_700116F3", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_700116F3", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_31331297", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_31331297", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_100415BD", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_100415BD", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014C1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014C1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_75011462", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_75011462", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_73021462", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_73021462", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_73041462", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_73041462", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01551025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01551025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02591028", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_02591028", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_027E1028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_82EF1043", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_82EF1043", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF6A1179", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF621179", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113E1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113E1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113A1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113A1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113B1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113B1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113D1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113D1734", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_88AD1033", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01471025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01471025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014B1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014B1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01481025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01481025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01491025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01491025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30E3103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30F2103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30F2103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_3600103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_3600103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30F1103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30E4103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30E4103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FB103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FB103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FE103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FE103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FC103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FC103C", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_149210CF", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43901019", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43901019", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_82881043", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_82881043", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_025B1028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_025A1028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02571028", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_02571028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02551028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43911849", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43921849", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_43931849", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_B0021458", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_B0021458", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014E1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014E1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014F1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014F1025", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_303617AA", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_303617AA", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_303F17AA", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_303F17AA", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF501179", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02641028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02651028", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E0E105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E0F105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E10105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E11105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E0E105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E0F105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E10105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E11105B", "ahcix86"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43911002", "ahcix86"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43921002", "ahcix86"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_43931002", "ahcix86"
id = "PCI\VEN_1002&DEV_4381&SUBSYS_43811002", "ahcix86"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_43821002", "ahcix86"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_43811002", "ahcix86" 

[HardwareIds.SCSI.Napa_amd64_ahci] 
id = "PCI\VEN_1002&DEV_4380&SUBSYS_280A103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_2814103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_3029103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_3029103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E08105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E08105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_C2151631", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_C2151631", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_E2191631", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_E2191631", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_E2171631", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_E2171631", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE10105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE11105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE13105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE14105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE0E105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_OE0F105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_76401558", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_76411558", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_2A6E103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_2A6E103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E13105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E13105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E14105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E14105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_A7051478", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_A7051478", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_55021565", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_55021565", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_700116F3", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_700116F3", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_31331297", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_31331297", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_100415BD", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_100415BD", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014C1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014C1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_75011462", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_75011462", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_73021462", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_73021462", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_73041462", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_73041462", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01551025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01551025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02591028", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_02591028", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_027E1028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_82EF1043", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_82EF1043", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF6A1179", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF621179", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113E1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113E1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113A1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113A1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113B1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113B1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_113D1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_113D1734", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_88AD1033", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01471025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01471025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014B1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014B1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01481025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01481025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_01491025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_01491025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30E3103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30F2103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30F2103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_3600103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_3600103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30F1103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30E4103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30E4103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FB103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FB103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FE103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FE103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_30FC103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_30FC103C", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_149210CF", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43901019", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43901019", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_82881043", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_82881043", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_025B1028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_025A1028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02571028", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_02571028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02551028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43911849", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43921849", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_43931849", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_B0021458", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_B0021458", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014E1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014E1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_014F1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_014F1025", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_303617AA", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_303617AA", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_303F17AA", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_303F17AA", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_FF501179", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02641028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_02651028", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E0E105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E0F105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E10105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_0E11105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E0E105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E0F105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E10105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_0E11105B", "ahcix64"
id = "PCI\VEN_1002&DEV_4391&SUBSYS_43911002", "ahcix64"
id = "PCI\VEN_1002&DEV_4392&SUBSYS_43921002", "ahcix64"
id = "PCI\VEN_1002&DEV_4393&SUBSYS_43931002", "ahcix64"
id = "PCI\VEN_1002&DEV_4381&SUBSYS_43811002", "ahcix64"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_43821002", "ahcix64"
id = "PCI\VEN_1002&DEV_4380&SUBSYS_43811002", "ahcix64"

[Config.ahcix86]
value = "", Tag, REG_DWORD, 1

[Config.ahcix64]
value = "", Tag, REG_DWORD, 1
''',
'''
[Disks]
d1 = "Promise FastTrak TX4310 Driver Diskette", \\fttxr5_O, \\
d2 = "Promise FastTrak TX4310 Driver Diskette", \\fttxr5_O, \\i386
d3 = "Promise FastTrak TX4310 Driver Diskette", \\fttxr5_O, \\x86_64

[Defaults]
scsi = fttxr5_O_i386

[scsi]
fttxr5_O_i386 = "Promise FastTrak TX4310 (tm) Controller-Intel x86", fttxr5_O
fttxr5_O_x86_64 = "Promise FastTrak TX4310 (tm) Controller-x86_64", fttxr5_O

[Files.scsi.fttxr5_O_i386]
driver = d2, fttxr5_O.sys, fttxr5_O
;driver = d2, bb_run.sys, bb_run
;driver = d1, DontGo.sys, dontgo
;dll = d1, ftutil2.dll
inf    = d2, fttxr5_O.inf
catalog= d2, fttxr5_O.cat

[Files.scsi.fttxr5_O_x86_64]
driver = d3, fttxr5_O.sys, fttxr5_O
;driver = d3, bb_run.sys, bb_run
;driver = d1, DontGo.sys, dontgo
;dll = d1, ftutil2.dll
inf    = d3, fttxr5_O.inf
catalog= d3, fttxr5_O.cat



[HardwareIds.scsi.fttxr5_O_i386]
id="PCI\VEN_105A", "fttxr5_O"

[HardwareIds.scsi.fttxr5_O_x86_64]
id="PCI\VEN_105A", "fttxr5_O"


[Config.fttxr5_O]
value = "", Tag, REG_DWORD, 1
''',
'''
; Copyright (c) 2003-09 Intel Corporation
;#############################################################################
;#
;#    Filename:  TXTSETUP.OEM
;#
;#############################################################################
[Disks]
disk1 = "Intel Matrix Storage Manager driver", iaStor.sys, \\

[Defaults]
scsi = iaStor_ICH8MEICH9ME
;scsi = iaAHCI_ICH8

;#############################################################################
[scsi]

; iaAHCI.inf
iaAHCI_ESB2               = "Intel(R) ESB2 SATA AHCI Controller"
iaAHCI_ICH7RDH            = "Intel(R) ICH7R/DH SATA AHCI Controller"
iaAHCI_ICH7MMDH           = "Intel(R) ICH7M/MDH SATA AHCI Controller"
iaAHCI_ICH8               = "Intel(R) 82801HB SATA AHCI Controller (Desktop ICH8)"
iaAHCI_ICH8RDHDO          = "Intel(R) ICH8R/DH/DO SATA AHCI Controller"
iaAHCI_ICH8MEM            = "Intel(R) ICH8M-E/M SATA AHCI Controller"
iaAHCI_ICH9RDODH          = "Intel(R) ICH9R/DO/DH SATA AHCI Controller"
iaAHCI_ICH9MEM            = "Intel(R) ICH9M-E/M SATA AHCI Controller"
iaAHCI_ICH10DDO           = "Intel(R) ICH10D/DO SATA AHCI Controller"
iaAHCI_ICH10R             = "Intel(R) ICH10R SATA AHCI Controller"

; iaStor.inf
iaStor_ESB2               = "Intel(R) ESB2 SATA RAID Controller"
iaStor_ICH7RDH            = "Intel(R) ICH7R/DH SATA RAID Controller"
iaStor_ICH7MDH            = "Intel(R) ICH7MDH SATA RAID Controller"
iaStor_ICH8RICH9RICH10RDO = "Intel(R) ICH8R/ICH9R/ICH10R/DO SATA RAID Controller"
iaStor_ICH8MEICH9ME       = "Intel(R) ICH8M-E/ICH9M-E SATA RAID Controller"

;#############################################################################

; iaAHCI.inf
[Files.scsi.iaAHCI_ESB2]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH7RDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH7MMDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH8]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH8RDHDO]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH8MEM]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH9RDODH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH9MEM]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH10DDO]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat

[Files.scsi.iaAHCI_ICH10R]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat


; iaStor.inf
[Files.scsi.iaStor_ESB2]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat

[Files.scsi.iaStor_ICH7RDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat

[Files.scsi.iaStor_ICH7MDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat

[Files.scsi.iaStor_ICH8RICH9RICH10RDO]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat

[Files.scsi.iaStor_ICH8MEICH9ME]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat


;#############################################################################
[Config.iaStor]
value = "", tag, REG_DWORD, 1b
value = "", ErrorControl, REG_DWORD, 1
value = "", Group, REG_SZ, "SCSI Miniport"
value = "", Start, REG_DWORD, 0
value = "", Type, REG_DWORD, 1

;#############################################################################

; iaAHCI.inf
[HardwareIds.scsi.iaAHCI_ESB2]
id = "PCI\VEN_8086&DEV_2681&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH7RDH]
id = "PCI\VEN_8086&DEV_27C1&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH7MMDH]
id = "PCI\VEN_8086&DEV_27C5&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH8RDHDO]
id = "PCI\VEN_8086&DEV_2821&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH8]
id = "PCI\VEN_8086&DEV_2824&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH8MEM]
id = "PCI\VEN_8086&DEV_2829&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH9RDODH]
id = "PCI\VEN_8086&DEV_2922&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH9MEM]
id = "PCI\VEN_8086&DEV_2929&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH10DDO]
id = "PCI\VEN_8086&DEV_3A02&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_ICH10R]
id = "PCI\VEN_8086&DEV_3A22&CC_0106","iaStor"


; iaStor.inf
[HardwareIds.scsi.iaStor_ESB2]
id = "PCI\VEN_8086&DEV_2682&CC_0104","iaStor"

[HardwareIds.scsi.iaStor_ICH7RDH]
id = "PCI\VEN_8086&DEV_27C3&CC_0104","iaStor"

[HardwareIds.scsi.iaStor_ICH7MDH]
id = "PCI\VEN_8086&DEV_27C6&CC_0104","iaStor"

[HardwareIds.scsi.iaStor_ICH8RICH9RICH10RDO]
id = "PCI\VEN_8086&DEV_2822&CC_0104","iaStor"

[HardwareIds.scsi.iaStor_ICH8MEICH9ME]
id = "PCI\VEN_8086&DEV_282A&CC_0104","iaStor"


''',
'''
[Disks]
disk1 = "Intel(R) Rapid Storage Technology Driver", iaStor.sys, \\
[Defaults]
scsi = iaStor_8ME9ME5
[scsi]
iaAHCI_ESB2       = "Intel(R) ESB2 SATA AHCI Controller"
iaAHCI_7RDH       = "Intel(R) ICH7R/DH SATA AHCI Controller"
iaAHCI_7MMDH      = "Intel(R) ICH7M/MDH SATA AHCI Controller"
iaAHCI_8RDHDO     = "Intel(R) ICH8R/DH/DO SATA AHCI Controller"
iaAHCI_8MEM       = "Intel(R) ICH8M-E/M SATA AHCI Controller"
iaAHCI_9RDODH     = "Intel(R) ICH9R/DO/DH SATA AHCI Controller"
iaAHCI_9MEM       = "Intel(R) ICH9M-E/M SATA AHCI Controller"
iaAHCI_10DDO      = "Intel(R) ICH10D/DO SATA AHCI Controller"
iaAHCI_10R        = "Intel(R) ICH10R SATA AHCI Controller"
iaAHCI_5          = "Intel(R) 5 Series 4 Port SATA AHCI Controller"
iaAHCI_5_1        = "Intel(R) 5 Series 6 Port SATA AHCI Controller"
iaAHCI_5_1_1      = "Intel(R) 5 Series/3400 Series SATA AHCI Controller"
iaStor_ESB2       = "Intel(R) ESB2 SATA RAID Controller"
iaStor_7RDH       = "Intel(R) ICH7R/DH SATA RAID Controller"
iaStor_7MDH       = "Intel(R) ICH7MDH SATA RAID Controller"
iaStor_8R9R10RDO5 = "Intel(R) ICH8R/ICH9R/ICH10R/DO/5 Series/3400 Series SATA RAID Controller"
iaStor_8ME9ME5    = "Intel(R) ICH8M-E/ICH9M-E/5 Series SATA RAID Controller"
[Files.scsi.iaAHCI_ESB2]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_7RDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_7MMDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_8RDHDO]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_8MEM]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_9RDODH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_9MEM]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_10DDO]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_10R]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_5]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_5_1]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaAHCI_5_1_1]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaAHCI.inf
catalog = disk1, iaAHCI.cat
[Files.scsi.iaStor_ESB2]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat
[Files.scsi.iaStor_7RDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat
[Files.scsi.iaStor_7MDH]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat
[Files.scsi.iaStor_8R9R10RDO5]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat
[Files.scsi.iaStor_8ME9ME5]
driver = disk1, iaStor.sys, iaStor
inf = disk1, iaStor.inf
catalog = disk1, iaStor.cat
[Config.iaStor]
value = "", tag, REG_DWORD, 1b
value = "", ErrorControl, REG_DWORD, 1
value = "", Group, REG_SZ, "SCSI Miniport"
value = "", Start, REG_DWORD, 0
value = "", Type, REG_DWORD, 1
[HardwareIds.scsi.iaAHCI_ESB2]
id = "PCI\VEN_8086&DEV_2681&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_7RDH]
id = "PCI\VEN_8086&DEV_27C1&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_7MMDH]
id = "PCI\VEN_8086&DEV_27C5&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_8RDHDO]
id = "PCI\VEN_8086&DEV_2821&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_8MEM]
id = "PCI\VEN_8086&DEV_2829&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_9RDODH]
id = "PCI\VEN_8086&DEV_2922&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_9MEM]
id = "PCI\VEN_8086&DEV_2929&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_10DDO]
id = "PCI\VEN_8086&DEV_3A02&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_10R]
id = "PCI\VEN_8086&DEV_3A22&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_5]
id = "PCI\VEN_8086&DEV_3B29&CC_0106","iaStor"
[HardwareIds.scsi.iaAHCI_5_1]
id = "PCI\VEN_8086&DEV_3B2F&CC_0106","iaStor"

[HardwareIds.scsi.iaAHCI_5_1_1]
id = "PCI\VEN_8086&DEV_3B22&CC_0106","iaStor"

[HardwareIds.scsi.iaStor_ESB2]
id = "PCI\VEN_8086&DEV_2682&CC_0104","iaStor"
[HardwareIds.scsi.iaStor_7RDH]
id = "PCI\VEN_8086&DEV_27C3&CC_0104","iaStor"
[HardwareIds.scsi.iaStor_7MDH]
id = "PCI\VEN_8086&DEV_27C6&CC_0104","iaStor"
[HardwareIds.scsi.iaStor_8R9R10RDO5]
id = "PCI\VEN_8086&DEV_2822&CC_0104","iaStor"
[HardwareIds.scsi.iaStor_8ME9ME5]
id = "PCI\VEN_8086&DEV_282A&CC_0104","iaStor"
'''
]

iniTestData = [
'''
#[section1]
# abc = def

[section2]
abc = def # comment

[section3]
key = value ;comment ; comment2

[section4]
key = value \; no comment \# comment2 ;# comment3

[section5]
key = \;\;\;\;\;\;\;\;\;\;\;\;
'''
]
if (__name__ == "__main__"):
	#logger.setConsoleLevel(LOG_DEBUG2)
	logger.setConsoleLevel(LOG_INFO)
	logger.setConsoleColor(True)
	
	
	for data in infTestData:
		infFile = InfFile('/tmp/test.inf')
		infFile.parse(data.split('\n'))
		devices = infFile.getDevices()
		if not devices:
			logger.error(u"No devices found!")
		for dev in devices:
			logger.notice(u"Found device: %s" % dev)
	
	for data in txtsetupoemTestData:
		print "============================================================================================================="
		try:
			txtSetupOemFile = TxtSetupOemFile('/tmp/txtsetup.oem')
			txtSetupOemFile.parse(data.split('\n'))
			#print "isDeviceKnown:", txtSetupOemFile.isDeviceKnown(vendorId = '10DE', deviceId = '0AD4')
			#for f in txtSetupOemFile.getFilesForDevice(vendorId = '10DE', deviceId = '0AD4', fileTypes = []):
			#	print f
			##for f in txtSetupOemFile.getFilesForDevice(vendorId = '10DE', deviceId = '07F6', fileTypes = []):
			##	print f
			#print "isDeviceKnown:", txtSetupOemFile.isDeviceKnown(vendorId = '10DE', deviceId = '0754')
			#print "description:", txtSetupOemFile.getComponentOptionsForDevice(vendorId = '10DE', deviceId = '0AD4')['description']
			
			for (vendorId, deviceId) in (('8086', '3B22'), ('1002', '4391'), ('10DE', '07F6')):
				print "isDeviceKnown:", txtSetupOemFile.isDeviceKnown(vendorId = vendorId, deviceId = deviceId)
				if txtSetupOemFile.isDeviceKnown(vendorId = vendorId, deviceId = deviceId):
					print "Files:"
					for f in txtSetupOemFile.getFilesForDevice(vendorId = vendorId, deviceId = deviceId, fileTypes = []):
						print f
					print "description:", txtSetupOemFile.getComponentOptionsForDevice(vendorId = vendorId, deviceId = deviceId)['description']
					
					txtSetupOemFile.applyWorkarounds()
					txtSetupOemFile.generate()
					print "Fixed files:"
					for f in txtSetupOemFile.getFilesForDevice(vendorId = vendorId, deviceId = deviceId, fileTypes = []):
						print f
			
			txtSetupOemFile.generate()
			#for line in txtSetupOemFile._lines:
			#	print line.rstrip()
			
		except Exception, e:
			logger.logException(e)
			continue
		
		#devices = txtSetupOemFile.getDevices()
		#if not devices:
		#	logger.error(u"No devices found!")
		#for dev in devices:
		#	logger.notice(u"Found device: %s" % dev)
	
	#for data in iniTestData:
	#	iniFile = IniFile('/tmp/test.ini')
	#	iniFile.parse(data.split('\n'))
	
	
	
	
	
	
