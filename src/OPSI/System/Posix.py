#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Posix   =
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

__version__ = '1.1.6'

# Imports
import os, sys, re, shutil, time, gettext, popen2, select, signal
import copy as pycopy
if (os.name == 'posix'):
	import posix, fcntl
else:
	import win32file

# OPSI imports
from OPSI.Logger import *
from OPSI.Tools import *

# Get Logger instance
logger = Logger()

# Constants

BIN_WHICH = '/usr/bin/which'
WHICH_CACHE = {}

GEO_OVERWRITE_SO = '/usr/local/lib/geo_override.so'

LOCALE_DIR = '/usr/share/locale'
DOSEMU_CONF = '/etc/dosemu/dosemu.conf'
DOSEMU_BOOT_IMAGE = '/etc/dosemu/dosboot.img'

userInterface = None

# Get locale
try:
	t = gettext.translation('opsi_system', LOCALE_DIR)
	def _(string):
		return t.ugettext(string).encode('utf-8', 'replace')
	
except Exception, e:
	logger.error("Locale not found: %s" % e)
	def _(string):
		"""Dummy method, created and called when no locale is found.
		Uses the fallback language (called C; means english) then."""
		return string

def setUI(ui):
	global userInterface
	userInterface = ui

def which(cmd):
	if not WHICH_CACHE.has_key(cmd):
		w = os.popen('%s "%s"' % (BIN_WHICH, cmd))
		path = w.readline().strip()
		w.close()
		if not path:
			raise Exception("Command '%s' not found in PATH" % cmd)
		WHICH_CACHE[cmd] = path
		logger.debug("Command '%s' found: '%s'" % (cmd, WHICH_CACHE[cmd]))
	
	return WHICH_CACHE[cmd]

def execute(cmd, nowait=False, wait=1, getHandle=False, logLevel=LOG_DEBUG, exitOnErr=False, capturestderr=True):
	"""
	Executes a command and returns output lines as list
	"""
	exitCode = 0
	result = ''
	
	try:
		# Execute command
		if (logLevel > 0):
			logger.log(logLevel, "Executing: %s" % cmd)
		
		if nowait:
			os.spawnv(os.P_NOWAIT, which('bash'), [which('bash'), '-c', cmd])
			return []
		
		elif getHandle:
			if capturestderr:
				return os.popen4(cmd)[1]
			else:
				return os.popen(cmd)
		
		else:
			fi = popen2.Popen3(cmd, capturestderr=capturestderr)
			
			flags = fcntl.fcntl(fi.fromchild, fcntl.F_GETFL)
			fcntl.fcntl(fi.fromchild, fcntl.F_SETFL, flags | os.O_NONBLOCK)
			readList = [ fi.fromchild ]
			
			if capturestderr:
				flags = fcntl.fcntl(fi.childerr, fcntl.F_GETFL)
				fcntl.fcntl(fi.childerr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
				readList.append(fi.childerr)
			
			ret = -1
			
			curLine = ''
			curErrLine = ''
			while (ret == -1):
				ret = fi.poll()
				try:
					string = fi.fromchild.read()
					if (len(string) > 0):
						result += string
						curLine += string
						if (curLine.find('\n') != -1):
							lines = curLine.split('\n')
							for i in range(len(lines)):
								if (i == len(lines)-1):
									curLine = lines[i]
								else:
									logger.debug(" ->>> %s" % lines[i])
				except IOError, e:
					if (e.errno != 11):
						raise
				
				if capturestderr:
					try:
						string = fi.childerr.read()
						if (len(string) > 0):
							result += string
							curErrLine += string
							if (curErrLine.find('\n') != -1):
								if exitOnErr:
									if (type(exitOnErr) is bool) or (type(exitOnErr) in (str, type(re.compile(''))) and re.search(exitOnErr, curErrLine)):
										if (logLevel == LOG_CONFIDENTIAL):
											cmd = '***********************'
										raise Exception("Command '%s' failed: %s" % (cmd, curErrLine) )
								lines = curErrLine.split('\n')
								for i in range(len(lines)):
									if (i == len(lines)-1):
										curErrLine = lines[i]
									else:
										logger.error(" ->>> %s" % lines[i])
					except IOError, e:
						if (e.errno != 11):
							raise
				
				time.sleep(0.001)
			
			if curLine:
				logger.debug(" ->>> %s" % curLine)
			if curErrLine:
				logger.error(" ->>> %s" % curErrLine)
			
			exitCode = ret
			result = result.split('\n')
			
	except (os.error, IOError), e:
		# Some error occured during execution
		if (logLevel == LOG_CONFIDENTIAL):
			cmd = '***********************'
		raise Exception("Command '%s' failed: %s" % (cmd, e) )
	
	logger.debug("Exit code: %s" % exitCode)
	if exitCode:
		if (logLevel == LOG_CONFIDENTIAL):
			cmd = '***********************'
		raise Exception("Command '%s' failed (%s): %s" % (cmd, exitCode, '\n'.join(result)) )
	return result

def getKernelParams():
	""" 
	Reads the kernel cmdline and returns a dict
	containing all key=value pairs.
	keys are converted to lower case
	"""
	params = {}
	cmdline = None
	f = None
	try:
		logger.debug('Reading /proc/cmdline')
		f = open("/proc/cmdline", "r")
		cmdline = f.readline()
		cmdline = cmdline.strip()
		f.close()
	except IOError, e:
		if f: f.close()
		raise Exception("Error reading '/proc/cmdline': %s" % e)
	if cmdline:
		for option in cmdline.split():
			keyValue = option.split("=")
			if ( len(keyValue) < 2 ):
				params[keyValue[0].strip().lower()] = ''
			else:
				params[keyValue[0].strip().lower()] = keyValue[1].strip()
	return params


def getDHCPResult(retry=3):
	"""
	Reads DHCP result from pump
	returns possible key/values:
	ip, netmask, bootserver, nextserver, gateway, bootfile, hostname, domain.
	keys are converted to lower case
	"""
	interfaces = []
	for line in execute(which('ifconfig')):
		match = re.search('^(eth\d+)\s+', line)
		if match:
			logger.info("Found ethernet device: '%s'" % match.group(1))
			interfaces.append( { 'device': match.group(1) } )
	
	if not interfaces:
		raise Exception('No ethernet interfaces found!')
	
	for interface in interfaces:
		i = 0
		while (i < retry):
			try:
				for line in execute( '%s -s -i %s' % (which('pump'), interface['device']) ):
					line = line.strip()
					keyValue = line.split(":")
					if ( len(keyValue) < 2 ):
						# No ":" in pump output after "boot server" and "next server"
						if line.lstrip().startswith('Boot server'):
							keyValue[0] = 'Boot server'
							keyValue.append(line.split()[2])
						elif line.lstrip().startswith('Next server'):
							keyValue[0] = 'Next server'
							keyValue.append(line.split()[2])
						else:
							continue
					# Some DHCP-Servers are returning multiple domain names seperated by whitespace,
					# so we split all values at whitespace and take the first element
					interface[keyValue[0].replace(' ','').lower()] = keyValue[1].strip().split()[0]
			except Exception, e:
				logger.warning("Pump failed: %s" % e)
				#try:
				#	execute( '%s -i %s' % (which('pump'), interface['device']) )
				#except Exception, e:
				#	logger.warning("Pump failed: %s" % e)
				i += 1
			else:
				i = retry
			# Sleeping 3 seconds for 2 reasons:
			# 1. Pump failed: Waiting for DHCP server
			# 2. Pump successful: Pump needs some time to configure interface
			time.sleep(3)
	
	useIf = 0
	if (len(interfaces) > 1):
		useIf = -1
		for i in range(len(interfaces)):
			if interfaces[i].get('ip'):
				# Interface has been configured by dhcp
				if (useIf < 0):
					# No interface selected so far
					useIf = i
				elif (interfaces[i].get('bootserver') and not interfaces[useIf].get('bootserver')):
					# Bootserver found, prefering this interface
					useIf = i
					logger.info("Found tftpserver on interface '%s', prefering this interface." \
							% interfaces[i]['device'] )
		if (useIf < 0): 
			useIf = 0
	
	if interfaces[useIf].get('ip'):
		logger.info("Using interface '%s' with ip '%s'." \
				% (interfaces[useIf].get('device'), interfaces[useIf].get('ip')) )
	else:
		logger.warning("No interface with configured ip address found!")
		logger.info("Using interface '%s'." % interfaces[useIf].get('device'))
	
	return interfaces[useIf]

def ifconfig(device, address, netmask=None):
	cmd = '%s %s %s' % (which('ifconfig'), device, address)
	if netmask:
		cmd += ' netmask %s' % netmask
	execute(cmd)
	
def reboot(ui='default', wait=10):
	if ui == 'default': ui=userInterface
	if ui: 
		ui.getMessageBox().addText( _('System is going down for reboot now.\n') )
	execute('%s %s; %s -r now' % (which('sleep'), int(wait), which('shutdown')), nowait=True)

def halt(ui='default', wait=10):
	if ui == 'default': ui=userInterface
	if ui: 
		ui.getMessageBox().addText( _('System is going down for halt now.\n') )
	execute('%s %s; %s -h now' % (which('sleep'), int(wait), which('shutdown')), nowait=True)

def countFiles(src):
	count = 0
	if os.path.isfile(src):
		return 1
	
	logger.debug("Counting files in dir '%s'" % src)
	if src.endswith('/*'):
		src = src[:-2]
	names = os.listdir(src)
	for name in names:
		srcname = os.path.join(src, name)
		if os.path.isfile(srcname):
			count += 1
		elif os.path.isdir(srcname):
			count += countFiles(srcname)
	return count

def copy(src, dst, ui='default'):
	if ui == 'default': ui=userInterface
	logger.info('Copying from %s to %s' % (src, dst))
	progress = None
	total = 1
	if ui:
		ui.getMessageBox().addText(_('Copying from %s to %s\n') % (src, dst))
		total = countFiles(src)
		progress = ui.createProgressBox(
					width 	= int(ui.getWidth()/2), 
					height	= int(ui.getHeight()/2), 
					total	= total, 
					title	= _('Copying from %s to %s') % (src, dst) )
		progress.show()
	
	if os.path.isfile(src):
		if progress:
			size = os.stat(src)[6]
			if size > 1024*1024:
				size =  str( size/(1024*1024) ) + " MByte"
			elif size > 1024:
				size =  str( size/(1024) ) + " kByte"
			else:
				size =  str( size ) + " Byte"
			progress.addText("[1] %s (%s)\n" % ( os.path.basename(src), size ) )
		mkdir(os.path.dirname(dst), ui=None)
		try:
			shutil.copy2(src, dst)
		except os.error, e:
			if (e.errno != 1):
				raise
			# Operation not permitted
			logger.warning(e)
		if progress:
			progress.setState(1)
			progress.hide()
		logger.info('Copy done!')
		
		return
	
	if src.endswith('/*'):
		src = src[:-2]
	else:
		dst = os.path.join(dst, os.path.basename(src))
		mkdir(dst, ui=None)
	
	copyTree( src, dst, True, 0, total, progress)
	logger.info('Copy done!')
	if progress:
		progress.hide()

def copyTree(src, dst, symlinks=False, current=0, total=1, progress=None):
	logger.debug("Copying files from '%s' to '%s'" % (src, dst))
	mkdir(dst, ui=None)
	
	names = os.listdir(src)
	
	errors = []
	for name in names:
		srcname = os.path.join(src, name)
		dstname = os.path.join(dst, name)
		if symlinks and os.path.islink(srcname):
			linkto = os.readlink(srcname)
			os.symlink(linkto, dstname)
		elif os.path.isdir(srcname):
			current = copyTree(srcname, dstname, symlinks, current, total, progress)
		else:
			if progress:
				size = os.stat(srcname)[6]
				if size > 1024*1024:
					size =  str( size/(1024*1024) ) + " MByte"
				elif size > 1024:
					size =  str( size/(1024) ) + " kByte"
				else:
					size =  str( size ) + " Byte"
				progress.addText("[%d] %s (%s)\n" % 
					( current+1, name, size ) )
			try:
				shutil.copy2(srcname, dstname)
			except os.error, e:
				if (e.errno != 1):
					raise
				# Operation not permitted
				logger.warning(e)
			except IOError, e:
				raise Exception("Failed to copy: %s" % e)
			current += 1
			if progress:
				progress.setState(current)
	return current

def mkdir(newDir, mode=0750, ui='default'):
	"""
	- already exists, silently complete
	- regular file in the way, raise an exception
	- parent directory(ies) does not exist, make them as well
	"""
	if ui == 'default': ui=userInterface
	if ui: ui.getMessageBox().addText(_("Creating directory '%s'.\n") % newDir)
	
	if os.path.isdir(newDir):
		pass
	elif os.path.isfile(newDir):
		raise OSError(	"A file with the same name as the desired " \
				"dir, '%s', already exists." % newDir)
	else:
		(head, tail) = os.path.split(newDir)
		if head and not os.path.isdir(head):
			mkdir(head, mode=mode, ui=ui)
		if tail:
			os.mkdir(newDir)
			try:
				os.chmod(newDir, mode)
			except os.error, e:
				if (e.errno != 1):
					raise
				# Operation not permitted
				logger.warning("Failed to chmod %s (%s): %s" % (newDir, mode, e))
				
def rmdir(path, recursive=False, ui='default'):
	try:
		if recursive:
			for root, dirs, files in os.walk(path, topdown=False):
				for name in files:
					os.remove(os.path.join(root, name))
				for name in dirs:
					if os.path.islink( os.path.join(root, name) ):
						os.remove(os.path.join(root, name))
					else:
						os.rmdir(os.path.join(root, name))
		os.rmdir(path)
	except Exception, e:
		raise Exception("Failed to delete directory '%s': %s" % (path, e))
	
def mount(dev, mountpoint, ui='default', **options):
	if ui == 'default': ui=userInterface
	fs = ''
	
	if ui: ui.getMessageBox().addText(_("Mounting '%s' to '%s'.\n") % (dev, mountpoint))
	mkdir(mountpoint, ui=ui)
	
	logLevel = LOG_DEBUG
	
	if dev.lower().startswith('smb://'):
		# Do not log smb password
		logLevel = LOG_CONFIDENTIAL
		
		match = re.search('^smb://([^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			#fs = '-t smbfs'
			fs = '-t cifs'
			parts = match.group(1).split('/')
			dev = '//%s/%s' % (parts[0], parts[1])
		else:
			raise Exception("Bad smb uri '%s'" % dev)
		
		if not 'username' in options:
			options['username'] = 'guest'
		if not 'password' in options:
			options['password'] = ''
	
	elif dev.lower().startswith('webdav://') or dev.lower().startswith('webdavs://') or \
	     dev.lower().startswith('http://') or dev.lower().startswith('https://'):
		# Do not log webdav password
		#logLevel = LOG_CONFIDENTIAL
		
		match = re.search('^(http|webdav)(s*)(://[^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			fs = '-t davfs'
			dev = 'http' + match.group(2) + match.group(3)
		else:
			raise Exception("Bad webdav url '%s'" % dev)
		
		if not 'username' in options:
			options['username'] = ''
		if not 'password' in options:
			options['password'] = ''
		if not 'servercert' in options:
			options['servercert'] = ''
		
		f = open("/etc/davfs2/certs/trusted.pem", "w")
		f.write(options['servercert'])
		f.close()
		os.chmod("/etc/davfs2/certs/trusted.pem", 0644)
		
		f = open("/etc/davfs2/secrets", "r")
		lines = f.readlines()
		f.close()
		f = open("/etc/davfs2/secrets", "w")
		for line in lines:
			if re.search("^%s\s+" % dev, line):
				f.write("#")
			f.write(line)
		f.write('%s "%s" "%s"\n' % (dev, options['username'], options['password']))
		f.close()
		os.chmod("/etc/davfs2/secrets", 0600)
		
		f = open("/etc/davfs2/davfs2.conf", "r")
		lines = f.readlines()
		f.close()
		f = open("/etc/davfs2/davfs2.conf", "w")
		for line in lines:
			if re.search("^servercert\s+", line):
				f.write("#")
			f.write(line)
		f.write("servercert /etc/davfs2/certs/trusted.pem\n")
		f.close()
		
		del options['username']
		del options['password']
		del options['servercert']
		
	elif dev.lower().startswith('/'):
		pass
	
	elif dev.lower().startswith('file://'):
		dev = dev[7:]
	
	else:
		raise Exception("Cannot mount unknown fs type '%s'" % dev)
	
	optString = ''
	for (key, value) in options.items():
		if value:
			optString += ',' + key + '=' + value
		else:
			optString += ',' + key
	if optString:
		optString = "-o '%s'" % optString[1:]
	
	cmd = "%s %s %s %s %s" % (which('mount'), fs, optString, dev, mountpoint)
	try:
		result = execute(cmd, logLevel = logLevel)
	except Exception, e:
		logger.error("Cannot mount: %s" % e)
		raise Exception ("Cannot mount: %s" % e)

def umount(devOrMountpoint, ui='default'):
	if ui == 'default': ui=userInterface
	if ui: ui.getMessageBox().addText(_("Umounting '%s'.\n") % devOrMountpoint)
	
	cmd = "%s %s" % (which('umount'), devOrMountpoint)
	try:
		result = execute(cmd)
	except Exception, e:
		logger.error("Cannot umount: %s" % e)
		raise Exception ("Cannot umount: %s" % e)

def getHarddisks(ui='default'):
	if ui == 'default': ui=userInterface
	disks = []
	
	if ui: ui.getMessageBox().addText(_("Looking for harddisks.\n"))
	
	# Get all available disks
	result = execute(which('sfdisk') + ' -s -uB')
	for line in result:
		if not line.lstrip().startswith('/dev'):
			continue
		(dev, size) = line.split(':')
		size = size.strip()
		logger.debug("Found disk =>>> dev: '%s', size: '%s'" % (dev, size) )
		
		hd = Harddisk(dev)
		if ui: 	
			ui.getMessageBox().addText(_("Hardisk '%s' found (%s MB).\n") \
							% (hd.device, hd.size/(1000*1000)))
		disks.append(hd)
	
	if ( len(disks) <= 0 ):
		raise Exception('No harddisks found!')
	
	return disks

def getDiskSpaceUsage(path, ui='default'):
	disk = os.statvfs(path)
	info = {}
	info['capacity'] = disk.f_bsize * disk.f_blocks
	info['available'] = disk.f_bsize * disk.f_bavail
	info['used'] = disk.f_bsize * (disk.f_blocks - disk.f_bavail)
	info['usage'] = float(disk.f_blocks - disk.f_bavail) / float(disk.f_blocks)
	logger.info("Disk space usage for path '%s': %s" % (path, info))
	return info

def getDevice(path, ui='default'):
	(mountPoint, device) = ('', '')
	f = open('/etc/mtab')
	for line in f.readlines():
		line = line.strip()
		if not line or line.startswith("#"):
			continue
		(dev, mp, foo) = line.split(None, 2)
		if path.startswith(mp) and (len(mp) > len(mountPoint)):
			mountPoint = mp
			device = dev
	f.close()
	logger.info("Filesystem for path '%s' is on device '%s'" % (path, device))
	return device

def hardwareInventory(ui='default', filename=None, config=None):
	if ui == 'default': ui=userInterface
	
	if ui:
		ui.getMessageBox().addText(_("Collecting hardware information.\n"))
	
	if not config:
		logger.error("hardwareInventory: no config given")
		return {}
	
	import xml.dom.minidom
	
	opsiValues = {}
	
	def getAttribute(dom, tagname, attrname):
		nodelist = dom.getElementsByTagName(tagname)
		if nodelist:
			return nodelist[0].getAttribute(attrname).strip()
		else:
			return ""
	
	def getElementsByAttributeValue(dom, tagName, attributeName, attributeValue):
		elements = []
		for element in dom.getElementsByTagName(tagName):
			if re.search(attributeValue , element.getAttribute(attributeName)):
				elements.append(element)
		return elements
	
	# Read output from lshw
	xmlOut = '\n'.join(execute("%s -xml 2>/dev/null" % which("lshw"), capturestderr=False))
	xmlOut = re.sub('[%c%c%c%c%c%c%c%c%c%c%c%c%c]' % (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xbd, 0xbf, 0xef, 0xdd), '.', xmlOut)
	dom = xml.dom.minidom.parseString( xmlOut.decode('utf-8', 'replace').encode('utf-8') )
	
	# Read output from lspci
	lspci = {}
	busId = None
	devRegex = re.compile('([\d\.:a-f]+)\s+([\da-f]+):\s+([\da-f]+):([\da-f]+)\s*(\(rev ([^\)]+)\)|)')
	subRegex = re.compile('\s*Subsystem:\s+([\da-f]+):([\da-f]+)\s*')
	for line in execute("%s -vn" % which("lspci")):
		if not line.strip():
			continue
		match = re.search(devRegex, line)
		if match:
			busId = match.group(1)
			lspci[busId] = { 	'vendorId':		match.group(3),
						'deviceId':		match.group(4),
						'subsystemVendorId':	'',
						'subsystemDeviceId':	'',
						'revision':		match.group(6) or '' }
			continue
		match = re.search(subRegex, line)
		if match:
			lspci[busId]['subsystemVendorId'] = match.group(1)
			lspci[busId]['subsystemDeviceId'] = match.group(2)
	logger.debug("Parsed lspci info:")
	logger.debug(objectToBeautifiedText(lspci))
	
	# Read output from lsusb
	lsusb = {}
	busId = None
	devId = None
	indent = -1
	currentKey = None
	status = False
	
	devRegex = re.compile('^Bus\s+(\d+)\s+Device\s+(\d+)\:\s+ID\s+([\da-fA-F]{4})\:([\da-fA-F]{4})\s*(.*)$')
	descriptorRegex = re.compile('^(\s*)(.*)\s+Descriptor\:\s*$')
	deviceStatusRegex = re.compile('^(\s*)Device\s+Status\:\s+(\S+)\s*$')
	deviceQualifierRegex = re.compile('^(\s*)Device\s+Qualifier\s+.*\:\s*$')
	keyRegex = re.compile('^(\s*)([^\:]+)\:\s*$')
	keyValueRegex = re.compile('^(\s*)(\S+)\s+(.*)$')
	
	try:
		for line in execute("%s -v" % which("lsusb")):
			if not line.strip() or (line.find('** UNAVAILABLE **') != -1):
				continue
			match = re.search(devRegex, line)
			if match:
				busId = match.group(1)
				devId = match.group(2)
				descriptor = None
				indent = -1
				currentKey = None
				status = False
				logger.debug("Device: %s:%s" % (busId, devId))
				lsusb[busId+":"+devId] = {
					'device': {},
					'configuration': {},
					'interface': {},
					'endpoint': [],
					'hid device': {},
					'hub': {},
					'qualifier': {},
					'status': {}
				}
				continue
			
			if status:
				lsusb[busId+":"+devId]['status'].append(line.strip())
				continue
			
			match = re.search(deviceStatusRegex, line)
			if match:
				status = True
				lsusb[busId+":"+devId]['status'] = [ match.group(2) ]
				continue
			
			match = re.search(deviceQualifierRegex, line)
			if match:
				descriptor = 'qualifier'
				logger.debug("Qualifier")
				currentKey = None
				indent = -1
				continue
			
			match = re.search(descriptorRegex, line)
			if match:
				descriptor = match.group(2).strip().lower()
				logger.debug("Descriptor: %s" % descriptor)
				if type(lsusb[busId+":"+devId][descriptor]) is list:
					lsusb[busId+":"+devId][descriptor].append({})
				currentKey = None
				indent = -1
				continue
			
			if not descriptor:
				logger.error("No descriptor")
				continue
			
			if not lsusb[busId+":"+devId].has_key(descriptor):
				logger.error("Unkown descriptor '%s'" % descriptor)
				continue
			
			(key, value) = ('', '')
			match = re.search(keyRegex, line)
			if match:
				key = match.group(2)
				indent = len(match.group(1))
			else:
				match = re.search(keyValueRegex, line)
				if match:
					if (indent >= 0) and (len(match.group(1)) > indent):
						key = currentKey
						value = match.group(0).strip()
					else:
						(key, value) = (match.group(2), match.group(3).strip())
						indent = len(match.group(1))
			
			logger.debug("key: '%s', value: '%s'" % (key, value))
			
			if not key or not value:
				continue
			
			currentKey = key
			if type(lsusb[busId+":"+devId][descriptor]) is list:
				if not lsusb[busId+":"+devId][descriptor][-1].has_key(key):
					lsusb[busId+":"+devId][descriptor][-1][key] = [ ]
				lsusb[busId+":"+devId][descriptor][-1][key].append(value)
			
			else:
				if not lsusb[busId+":"+devId][descriptor].has_key(key):
					lsusb[busId+":"+devId][descriptor][key] = [ ]
				lsusb[busId+":"+devId][descriptor][key].append(value)
			
			
		logger.debug("Parsed lsusb info:")
		logger.debug(objectToBeautifiedText(lsusb))
	except Exception, e:
		logger.error(e)
	
	# Read output from dmidecode
	dmidecode = {}
	dmiType = None
	header = True
	option = None
	optRegex = re.compile('(\s+)([^:]+):(.*)')
	for line in execute(which("dmidecode")):
		try:
			if not line.strip():
				continue
			if line.startswith('Handle'):
				dmiType = None
				header = False
				option = None
				continue
			if header:
				continue
			if not dmiType:
				dmiType = line.strip()
				if (dmiType.lower() == 'end of table'):
					break
				if not dmidecode.has_key(dmiType):
					dmidecode[dmiType] = []
				dmidecode[dmiType].append({})
			else:
				match = re.search(optRegex, line)
				if match:
					option = match.group(2).strip()
					value = match.group(3).strip()
					dmidecode[dmiType][-1][option] = removeUnit(value)
				elif option:
					if not type(dmidecode[dmiType][-1][option]) is list:
						if dmidecode[dmiType][-1][option]:
							dmidecode[dmiType][-1][option] = [ dmidecode[dmiType][-1][option] ]
						else:
							dmidecode[dmiType][-1][option] = []
					dmidecode[dmiType][-1][option].append(removeUnit(line.strip()))
		except Exception, e:
			logger.error("Error while parsing dmidecode output '%s': %s" % (line.strip(), e))
	logger.debug("Parsed dmidecode info:")
	logger.debug(objectToBeautifiedText(dmidecode))
	
	# Build hw info structure
	for hwClass in config:
		
		if not hwClass.get('Class') or not hwClass['Class'].get('Opsi') or not hwClass['Class'].get('Linux'):
			continue
		
		opsiClass = hwClass['Class']['Opsi']
		linuxClass = hwClass['Class']['Linux']
		
		logger.debug( "Processing class '%s' : '%s'" % (opsiClass, linuxClass) )
		
		if linuxClass.startswith('[lshw]'):
			# Get matching xml nodes
			devices = []
			for hwclass in linuxClass[6:].split('|'):
				hwid = ''
				filter = None
				if (hwclass.find(':') != -1):
					(hwclass, hwid) = hwclass.split(':', 1)
					if (hwid.find(':') != -1):
						(hwid, filter) = hwid.split(':', 1)
				
				logger.debug( "Class is '%s', id is '%s', filter is: %s" % (hwClass, hwid, filter) )
				
				devs = getElementsByAttributeValue(dom, 'node', 'class', hwclass)
				for dev in devs:
					if dev.hasChildNodes():
						for child in dev.childNodes:
							if (child.nodeName == "businfo"):
								busInfo = child.firstChild.data.strip()
								if busInfo.startswith('pci@'):
									logger.debug("Getting pci bus info for '%s'" % busInfo)
									pciBusId = busInfo.split('@')[1]
									if pciBusId.startswith('0000:'):
										pciBusId = pciBusId[5:]
									pciInfo = lspci.get(pciBusId, {})
									for (key, value) in pciInfo.items():
										elem = dom.createElement(key)
										elem.childNodes.append( dom.createTextNode(value) )
										dev.childNodes.append( elem )
								break
				if hwid:
					filtered = []
					for dev in devs:
						if re.search(hwid, dev.getAttribute('id')):
							if not filter:
								filtered.append(dev)
							else:
								(attr, method) = filter.split('.', 1)
								if dev.getAttribute(attr):
									if eval("dev.getAttribute(attr).%s" % method):
										filtered.append(dev)
								elif dev.hasChildNodes():
									for child in dev.childNodes:
										if (child.nodeName == attr) and child.hasChildNodes():
											if eval("child.firstChild.data.strip().%s" % method):
												filtered.append(dev)
												break
										try:
											if child.hasAttributes() and child.getAttribute(attr):
												if eval("child.getAttribute(attr).%s" % method):
													filtered.append(dev)
													break
										except:
											pass
					devs = filtered
				
				logger.debug2( "Found matching devices: %s" % devs)
				devices.extend(devs)
			
			# Process matching xml nodes
			for i in range(len(devices)):
				
				if not opsiValues.has_key(opsiClass):
					opsiValues[opsiClass] = []
				opsiValues[opsiClass].append({})
				
				if not hwClass.get('Values'):
					break
				
				for attribute in hwClass['Values']:
					elements = [ devices[i] ]
					if not attribute.get('Opsi') or not attribute.get('Linux'):
						continue
					logger.debug2( "Processing attribute '%s' : '%s'" % (attribute['Linux'], attribute['Opsi']) )
					for attr in attribute['Linux'].split('||'):
						attr = attr.strip()
						method = None
						data = None
						for part in attr.split('/'):
							if (part.find('.') != -1):
								(part, method) = part.split('.', 1)
							nextElements = []
							for element in elements:
								for child in element.childNodes:
									try:
										if (child.nodeName == part):
											nextElements.append(child)
										elif child.hasAttributes() and \
										     ((child.getAttribute('class') == part) or (child.getAttribute('id').split(':')[0] == part)):
											nextElements.append(child)
									except:
										pass
							if not nextElements:
								logger.warning("Attribute part '%s' not found" % part)
								break
							elements = nextElements
						
						if not data:
							if not elements:
								opsiValues[opsiClass][i][attribute['Opsi']] = ''
								logger.warning("No data found for attribute '%s' : '%s'" % (attribute['Linux'], attribute['Opsi']))
								continue
							
							for element in elements:
								if element.getAttribute(attr):
									data = element.getAttribute(attr).strip()
								elif element.getAttribute('value'):
									data = element.getAttribute('value').strip()
								elif element.hasChildNodes():
									data = element.firstChild.data.strip()
						if method and data:
							try:
								logger.debug("Eval: %s.%s" % (data, method))
								data = eval("data.%s" % method)
							except Exception, e:
								logger.error("Failed to excecute '%s.%s': %s" % (data, method, e))
						logger.debug2("Data: %s" % data)
						opsiValues[opsiClass][i][attribute['Opsi']] = data
						if data:
							break
		
		# Get hw info from dmidecode
		elif linuxClass.startswith('[dmidecode]'):
			opsiValues[opsiClass] = []
			for hwclass in linuxClass[11:].split('|'):
				(filterAttr, filterExp) = (None, None)
				if (hwclass.find(':') != -1):
					(hwclass, filter) = hwclass.split(':', 1)
					if (filter.find('.') != -1):
						(filterAttr, filterExp) = filter.split('.', 1)
				
				for dev in dmidecode.get(hwclass, []):
					if filterAttr and dev.get(filterAttr) and not eval("str(dev.get(filterAttr)).%s" % filterExp):
						continue
					device = {}
					for attribute in hwClass['Values']:
						if not attribute.get('Linux'):
							continue
						for aname in attribute['Linux'].split('||'):
							aname = aname.strip()
							method = None
							if (aname.find('.') != -1):
								(aname, method) = aname.split('.', 1)
							if method:
								try:
									logger.debug("Eval: %s.%s" % (dev.get(aname, ''), method))
									device[attribute['Opsi']] = eval("dev.get(aname, '').%s" % method)
								except Exception, e:
									device[attribute['Opsi']] = ''
									logger.error("Failed to excecute '%s.%s': %s" % (dev.get(aname, ''), method, e))
							else:
								device[attribute['Opsi']] = dev.get(aname)
							if device[attribute['Opsi']]:
								break
					opsiValues[hwClass['Class']['Opsi']].append(device)
		
		# Get hw info from lsusb
		elif linuxClass.startswith('[lsusb]'):
			opsiValues[opsiClass] = []
			for (busId, dev) in lsusb.items():
				device = {}
				for attribute in hwClass['Values']:
					if not attribute.get('Linux'):
						continue
					try:
						value = pycopy.deepcopy(dev)
						for key in (attribute['Linux'].split('/')):
							method = None
							if (key.find('.') != -1):
								(key, method) = key.split('.', 1)
							if not type(value) is dict or not value.has_key(key):
								logger.error("Key '%s' not found" % key)
								value = ''
								break
							value = value[key]
							if type(value) is list:
								value = ', '.join(value)
							if method:
								value = eval("value.%s" % method)
							
						device[attribute['Opsi']] = value
					except Exception, e:
						logger.warning(e)
						device[attribute['Opsi']] = ''
				opsiValues[opsiClass].append(device)
	
	opsiValues['SCANPROPERTIES'] = [ { "scantime": time.strftime("%Y-%m-%d %H:%M:%S") } ]
	
	logger.debug("Result of hardware inventory:\n" + objectToBeautifiedText(opsiValues))
	
	return opsiValues
	
def runDosemu(harddisk = None, todo = ()):
	if type(todo) not in (list, tuple):
		todo = [ todo ]
	
	if harddisk:
		f = open(DOSEMU_CONF, 'r')
		lines = f.readlines()
		f.close()
		f = open(DOSEMU_CONF, 'w')
		for line in lines:
			if line.lstrip().startswith('$_hdimage'):
				 line = '$_hdimage = "%s"' % harddisk
			print >> f, line,
		f.close()
	
	if todo:
		mount(DOSEMU_BOOT_IMAGE, '/mnt/dos', ui=None, loop='')
		f = open('/mnt/dos/autoexec.bat')
		lines = f.readlines()
		f.close()
		f = open('/mnt/dos/autoexec.bat', 'w')
		for line in lines:
			line = line.rstrip()
			if (line == 'rem ---runDosemu---'):
				break
			print >> f, line, '\r'
		
		print >> f, 'rem ---runDosemu---\r'
		print >> f, 'call todo.bat\r'
		f.close()
		
		f = open('/mnt/dos/todo.bat', 'w')
		for line in todo:
			print >> f, str(line), '\r'
		f.close()
		umount('/mnt/dos')
	
	#tty = os.popen(which('tty')).readline().strip()
	#
	#(rows, cols) = execute('%s -F %s size' % (which('stty'), tty) )[0].split()
	#rows = int(rows.strip())
	#cols = int(cols.strip())
	#execute('%s -F %s rows 25 cols 80' % (which('stty'), tty) )
	#
	if not os.path.isdir('/root/.dosemu'):
		mkdir('/root/.dosemu')
	
	f = open('/root/.dosemu/disclaimer', 'w')
	f.close()
	
	logger.notice("Starting dosemu ...")
	os.system('HOME=/root %s -S -f %s' % (which('dosemu.bin'), DOSEMU_CONF))
	
	#execute('%s -F %s rows %s cols %s' % (which('stty'), tty, rows, cols))
	
	logger.debug("runDosemu(): end")

def getBlockDeviceBusType(device):
	# Returns either 'IDE', 'SCSI', 'SATA', 'RAID' or None (not found)
	(devs, type) = ([], None)
	for line in execute('%s --disk --cdrom' % which('hwinfo')):
		if not re.search('^\s+', line):
			(devs, type) = ([], None)
			continue
		
		match = re.search('^\s+Device Files:(.*)$', line)
		if match:
			devs = match.group(1).split(',')
			for i in range(len(devs)):
				devs[i] = devs[i].strip()
		
		match = re.search('^\s+Attached to:\s+[^\(]+\((\S+)\s*', line)
		if match:
			type = match.group(1)
		
		if devs and device in devs and type:
			logger.info("Bus type of device '%s' is '%s'" % (device, type))
			return type

# ======================================================================================================
# =                                       CLASS HARDDISK                                               =
# ======================================================================================================
class Harddisk:
	
	def __init__(self, device):
		''' Harddisk constructor. '''
		self.device = device
		self.model = ''
		self.signature = None
		self.biosDevice = None
		self.biosHeads = 0
		self.biosSectors = 0
		self.biosCylinders = 0
		self.cylinders = 0
		self.heads = 0
		self.sectors = 0
		self.label = None
		self.size = -1		# unit MB
		self.partitions = []
		self.ldPreload = None
		
		self.useBIOSGeometry()
		self.readPartitionTable()
	
	def getBusType(self):
		return getBlockDeviceBusType(self.device)
		
	def useBIOSGeometry(self):
		# Make sure your kernel supports edd (CONFIG_EDD=y/m) and module is loaded if not compiled in
		
		try:
			execute(which('modprobe') + ' edd')
		except Exception, e:
			logger.error(e)
			return
		# geo_override.so will affect all devices !
		logger.info("Using geo_override.so for all disks.")
		self.ldPreload = GEO_OVERWRITE_SO
		
	def getSignature(self):
		hd = posix.open('%s' % self.device, posix.O_RDONLY)
		posix.lseek(hd, 440, 0)
		x = posix.read(hd, 4)
		posix.close(hd)
		
		logger.debug("Read signature from device '%s': %s,%s,%s,%s" \
				% (self.device, ord(x[0]), ord(x[1]), ord(x[2]), ord(x[3])) )
		
		self.signature = 0
		self.signature += ord(x[3]) << 24
		self.signature += ord(x[2]) << 16
		self.signature += ord(x[1]) << 8
		self.signature += ord(x[0]) 
		logger.debug("Device Signature: '%s'" % hex(self.signature))
		
				
	def setDiskLabelType(self, label):
		if not label.lower() in ["bsd", "gpt", "loop", "mac", "mips", "msdos", "pc98", "sun"]:
			raise Exception("Unknown disk label '%s'" % label)
		
		self.label = label.lower()
	
	def readPartitionTable(self):
		self.partitions = []
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		
		result = execute(which('sfdisk') + ' -l ' + self.device)
		for line in result:
			if (line.find('unrecognized partition table type') != -1):
				execute('%s -e "0,0\n\n\n\n" | %s -D %s' % (which('echo'), which('sfdisk'), self.device))
				result = execute(which('sfdisk') + ' -l ' + self.device)
				break
		
		for line in result:
			line = line.strip()
			if line.lower().startswith('disk'):
				match = re.search('\s+(\d+)\s+cylinders,\s+(\d+)\s+heads,\s+(\d+)\s+sectors', line)
				if not match:
					raise Exception("Unable to get geometry for disk '%s'" % self.device)
				
				self.cylinders = int(match.group(1))
				self.heads = int(match.group(2))
				self.sectors = int(match.group(3))
			
			elif line.lower().startswith('units'):
				match = re.search('cylinders\s+of\s+(\d+)\s+bytes', line)
				if not match:
					raise Exception("Unable to get bytes/cylinder for disk '%s'" % self.device)
				self.bytesPerCylinder = int(match.group(1))
				
				self.size = self.bytesPerCylinder * self.cylinders
				logger.info("Size of disk '%s': %s Byte / %s MB" % ( self.device, self.size, (self.size/(1000*1000))) )
			
			elif line.startswith(self.device):
				match = re.search('(%sp*)(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\d+)[\+\-]*\s+(\S+)\s+(.*)' % self.device, line)
				if not match:
					raise Exception("Unable to read partition table of disk '%s'" % self.device)
				
				if match.group(5):
					boot = False
					if (match.group(3) == '*'):
						boot = True
					
					fs = 'unknown'
					if (match.group(8).lower() in ["b", "c", "e"]):
						fs = 'fat32'
					elif (match.group(8).lower() in ["7"]):
						fs = 'ntfs'
					
					self.partitions.append( {'device':	match.group(1) + match.group(2),
								  'number':	int(match.group(2)),
								  'cylStart':	int(match.group(4)),
								  'cylEnd':	int(match.group(5)),
								  'cylSize':	int(match.group(6)),
								  'start':	int(match.group(4)) * self.bytesPerCylinder,
								  'end':	int(match.group(5)) * self.bytesPerCylinder,
								  'size':	int(match.group(6)) * self.bytesPerCylinder,
								  'type':	match.group(8).lower(),
								  'fs':		fs,
								  'boot': 	boot } )
					
					logger.debug(	"Partition found =>>> number: %s, start: %s MB (%s cyl), end: %s MB (%s cyl), size: %s MB (%s cyl), " \
							% (	self.partitions[-1]['number'], 
								(self.partitions[-1]['start']/(1000*1000)), self.partitions[-1]['cylStart'], 
								(self.partitions[-1]['end']/(1000*1000)), self.partitions[-1]['cylEnd'], 
								(self.partitions[-1]['size']/(1000*1000)), self.partitions[-1]['cylSize'] ) \
							+ "type: %s, fs: %s, boot: %s" \
							% (match.group(8), fs, boot) )
		
		# Get sector data
		result = execute(which('sfdisk') + ' -uS -l ' + self.device)
		for line in result:
			line = line.strip()
			if line.startswith(self.device):
				match = re.search('%sp*(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\S+)\s+(.*)' % self.device, line)
				if not match:
					raise Exception("Unable to read partition table (sectors) of disk '%s'" % self.device)
				
				if match.group(4):
					for p in range(len(self.partitions)):
						if (int(self.partitions[p]['number']) == int(match.group(1))):
							self.partitions[p]['secStart'] = int(match.group(3))
							self.partitions[p]['secEnd'] = int(match.group(4))
							self.partitions[p]['secSize'] = int(match.group(5))
							logger.debug("Partition sector values =>>> number: %s, start: %s sec, end: %s sec, size: %s sec " \
									% ( self.partitions[p]['number'], self.partitions[p]['secStart'],
									    self.partitions[p]['secEnd'], self.partitions[p]['secSize']) )
							break
		
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
		
	def writePartitionTable(self):
		logger.debug("Partition table to write to disk")
		
		cmd = '%s -e "' % which('echo')
		for p in range(4):
			try:
				part = self.getPartition(p+1)
				logger.debug("   number: %s, start: %s MB (%s cyl), end: %s MB (%s cyl), size: %s MB (%s cyl), " \
							% (	part['number'], 
								(part['start']/(1000*1000)), part['cylStart'], 
								(part['end']/(1000*1000)), part['cylEnd'], 
								(part['size']/(1000*1000)), part['cylSize'] ) \
							+ "type: %s, fs: %s, boot: %s" \
							% (part['type'], part['fs'], part['boot']) )
				
				cmd += '%s,%s,%s' % (part['cylStart'], part['cylSize'], part['type'])
				if part['boot']:
					cmd += ',*'
			except Exception, e:
				logger.debug("Partition %d not found: %s" % ((p+1), e))
				cmd += '0,0'
			
			cmd += '\n'
			
		cmd +=  '" | %s -D %s' % (which('sfdisk'), self.device)
		
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		execute(cmd)
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
	
	
	def deletePartitionTable(self, ui='default'):
		if ui == 'default': ui=userInterface
		if ui: 
			ui.getMessageBox().addText(_("Deleting partition table on disk '%s'.\n") \
										% self.device)
		logger.info("Deleting partition table on '%s'." % self.device)
		cmd = which('dd') + ' if=/dev/zero of=' + self.device +' bs=512 count=1'
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		execute(cmd)
		
		logger.info("Forcing kernel to reread partition table of '%s'." % self.device)
		execute(which('sfdisk') + ' --re-read %s' % self.device)
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
		self.label = None
		self.partitions = []
	
	def shred(self, partition=0, iterations=25, ui='default'):
		if ui == 'default': ui=userInterface
		
		dev = self.device
		partition = int(partition)
		if (partition != 0):
			dev = self.getPartition(partition)['device']
		
		cmd = "%s -v -n %d %s 2>&1" % (which('shred'), iterations, dev)
		
		progress = None
		if ui:
			progress = ui.createProgressBox(
					width 	= int(ui.getWidth()/2), 
					height	= 8, 
					total	= 100, 
					title	= _("Shredding %s") % dev )
			progress.show()
		
		lineRegex = re.compile('\s(\d+)\/(\d+)\s\(([^\)]+)\)\.\.\.(.*)$')
		posRegex = re.compile('([^\/]+)\/(\S+)\s+(\d+)%')
		handle = execute(cmd, getHandle=True)
		position = ''
		error = ''
		while True:
			line = handle.readline().strip()
			logger.debug("From shred =>>> %s" % line)
			if not line:
				break
			'''
			shred: /dev/xyz: Pass 1/25 (random)...232MiB/512MiB 45%
			'''
			match = re.search(lineRegex, line)
			if match:
				iteration = int(match.group(1))
				dataType = match.group(3)
				logger.debug("Iteration: %d, data-type: %s" % (iteration, dataType))
				match = re.search(posRegex, match.group(4))
				if match:
					position = match.group(1) + '/' + match.group(2)
					percent = int(match.group(3))
					logger.debug("Position: %s, percent: %d" % (position, percent))
					if (percent != progress.getState()):
						progress.setState(percent)
				
				progress.setText(_("Pass %d/%d (%s)\n") % (iteration, iterations, dataType))
				progress.addText(_("Position: %s\n") % position)
			else:
				error = line
			
		ret = handle.close()
		logger.debug("Exit code: %s" % ret)
		if progress: progress.hide()
		if ret:
			raise Exception("Command '%s' failed: %s" % (cmd, error))
		
	def zeroFill(self, partition=0, ui='default'):
		fill(partition=partition, ui=ui, infile='/dev/zero')
	
	def randomFill(self, partition=0, ui='default'):
		fill(partition=partition, ui=ui, infile='/dev/urandom')
	
	def fill(self, partition=0, ui='default', infile=''):
		if ui == 'default': ui=userInterface
		if not infile:
			raise Exception("No input file given")
		
		partition = int(partition)
		xfermax = 0
		dev = self.device
		if (partition != 0):
			dev = self.getPartition(partition)['device']
			xfermax = int( round(float(self.getPartition(partition)['size'])/1024) )
		else:
			xfermax = int( round(float(self.size)/1024) )
		
		cmd = "%s -m %sk %s %s 2>&1" % (which('dd_rescue'), xfermax, infile, dev)
		
		progress = None
		if ui:
			progress = ui.createProgressBox(
					width 	= int(ui.getWidth()/2), 
					height	= 8, 
					total	= 100, 
					title	= _("Writing from %s to '%s'") % (infile, dev) )
			progress.show()
						
		handle = execute(cmd, getHandle=True)
		done = False
		
		skip = 0
		rate = 0
		position = 0
		timeout = 0		
		while not done:
			inp = handle.read(1024)
			'''
			dd_rescue: (info): ipos:    720896.0k, opos:    720896.0k, xferd:    720896.0k
					   errs:      0, errxfer:         0.0k, succxfer:    720896.0k
				     +curr.rate:    21843kB/s, avg.rate:    23526kB/s, avg.load: 17.4%
			'''
			if inp:
				timeout = 0
				skip += 1
				if (inp.find('Summary') != -1): 
					done = True
			
			elif (timeout >= 10):
				raise Exception(_("Failed"))
			
			else:
				timeout += 1
				continue
			
			if (skip < 10):
				time.sleep(0.1)
				continue
			else:
				skip = 0
			
			if progress:
				match = re.search('ipos:\s+(\d+)\.\d+k', inp)
				if match:
					position = int(match.group(1))
					percent = (position*100)/xfermax
					logger.debug("Position: %s, xfermax: %s, percent: %s" % (position, xfermax, percent))
					if (percent != progress.getState()):
						progress.setState(percent)
				
				match = re.search('avg\.rate:\s+(\d+)kB/s', inp)
				if match:
					rate = match.group(1)
					#logger.debug("Rate: %s" % rate)
					
				progress.setText(_("Average transfer rate: %s kB/s\n") % rate)
				progress.addText(_("Pos: %s MB\n") % round((position)/1000))
		time.sleep(3)
		if handle: handle.close	
		if progress: progress.hide()
	
	
	def writeMasterBootRecord(self, system = 'auto',ui='default'):
		if ui == 'default': ui=userInterface
		mbrType = '-w'
		if system in ['win2000', 'winxp', 'win2003']:
			mbrType = '--mbr'
		elif system in ['vista']:
			mbrType = '--mbrnt60'
		elif system in ['win9x']:
			mbrType = '--mbr95b'
		elif system in ['dos', 'winnt']:
			mbrType = '--mbrdos'
		
		if ui: ui.getMessageBox().addText(_("Writing master boot record (system: %s) to '%s'.\n") \
						% (system, self.device) )
		
		logger.info("Writing master boot record on '%s' (system: %s)." 
				% (self.device, system))
		
		cmd = "%s %s %s" % (which('ms-sys'), mbrType, self.device)
		try:
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			result = execute(cmd)
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
		except Exception, e:
			logger.error("Cannot write mbr: %s" % e)
			raise Exception ("Cannot write mbr: %s" % e)
	
	def writePartitionBootRecord(self, partition = 1, fsType = 'auto', ui='default'):
		if ui == 'default': ui=userInterface
		
		if ui: ui.getMessageBox().addText(_("Writing partition boot record (fs: %s) to '%s'.\n") \
						% (fsType, self.getPartition(partition)['device']) )
		
		logger.info("Writing partition boot record on '%s' (fs-type: %s)." 
					% (self.getPartition(partition)['device'], fsType))
		
		if (fsType == 'auto'):
			fsType = '-w'
		else:
			fsType = '--' + fsType
		
		cmd = "%s -p %s %s" % (which('ms-sys'), fsType, self.getPartition(partition)['device'])
		try:
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			result = execute(cmd)
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
			if (result[0].find('successfully') == -1):
				raise Exception(result)
			
		except Exception, e:
			logger.error("Cannot write partition boot record: %s" % e)
			raise Exception ("Cannot write partition boot record: %s" % e)
	
	def setNTFSPartitionStartSector(self, partition, sector=0, ui='default'):
		if ui == 'default': ui=userInterface
		if not sector:
			sector = self.getPartition(partition)['secStart']
			if not sector:
				err = "Failed to get partition start sector of partition '%s'" \
						% (self.getPartition(partition)['device'])
				logger.error(err)
				raise Exception(err)
		
		if ui: ui.getMessageBox().addText(_("Modifying NTFS boot record of partition '%s' (sector: %s).\n") \
						% (self.getPartition(partition)['device'], sector) )
						
		logger.info("Setting Partition start sector to %s in NTFS boot record " % sector \
				+ "on partition '%s'" % self.getPartition(partition)['device'] )
		
		x = [0, 0, 0, 0]
		x[0] = int ( (sector & 0x000000FFL) ) 
		x[1] = int ( (sector & 0x0000FF00L) >> 8 )
		x[2] = int ( (sector & 0x00FF0000L) >> 16 )
		x[3] = int ( (sector & 0xFFFFFFFFL) >> 24 )
		
		hd = posix.open(self.getPartition(partition)['device'], posix.O_RDONLY)
		posix.lseek(hd, 0x1c, 0)
		start = posix.read(hd, 4)
		logger.debug("NTFS Boot Record currently using %s %s %s %s as partition start sector" \
					% ( hex(ord(start[0])), hex(ord(start[1])), 
					    hex(ord(start[2])), hex(ord(start[3])) ) )
		posix.close(hd)
		
		logger.debug("Manipulating NTFS Boot Record!")
		hd = posix.open(self.getPartition(partition)['device'], posix.O_WRONLY)
		logger.info("Writing new value %s %s %s %s at 0x1c" % ( hex(x[0]), hex(x[1]), hex(x[2]), hex(x[3])))
		posix.lseek(hd, 0x1c, 0)
		for i in x:
			posix.write( hd, chr(i) )
		posix.close(hd)
		
		hd = posix.open(self.getPartition(partition)['device'], posix.O_RDONLY)
		posix.lseek(hd, 0x1c, 0)
		start = posix.read(hd, 4)
		logger.debug("NTFS Boot Record now using %s %s %s %s as partition start sector" \
					% ( hex(ord(start[0])), hex(ord(start[1])), 
					    hex(ord(start[2])), hex(ord(start[3])) ) )
		posix.close(hd)
	
	def getPartitions(self):
		return self.partitions
	
	def getPartition(self, number):
		for part in self.partitions:
			if (int(part['number']) == int(number)):
				return part
		raise Exception('Partition %s does not exist' % number)
	
	def createPartition(self, start, end, fs, type = 'primary', boot = False, lba = False, ui='default'):
		
		if ui == 'default': ui=userInterface
		
		partId = '00'
		fs = fs.lower()
		if re.search('^[a-fA-F0-9]{2}$', fs):
			partId = fs
		else:
			if (fs in ['ext2', 'ext3', 'xfs', 'reiserfs', 'reiser4']):
				partId = '83'
			elif (fs == 'linux-swap'):
				partId = '82'
			elif (fs == 'fat32'):
				partId = 'c'
			elif (fs == 'ntfs'):
				partId = '7'
			else:
				raise Exception("Filesystem '%s' not supported!" % fs)
		partId = partId.lower()
		
		if (type != 'primary'):
			raise Exception("Type '%s' not supported!" % type)
		
		start = start.replace(' ','')
		end = end.replace(' ','')
		
		if start.lower().endswith('m') or start.lower().endswith('mb'):
			match = re.search('^(\d+)\D', start)
			start = int(round( (int(match.group(1))*1024*1024) / self.bytesPerCylinder ))
			
		elif start.lower().endswith('%'):
			match = re.search('^(\d+)\D', start)
			start = int(round( (float(match.group(1))/100) * self.cylinders ))
		else:
			raise Exception("Unsupported unit '%s' (please use MB or %)" % start)
		
		
		if end.lower().endswith('m') or end.lower().endswith('mb'):
			match = re.search('^(\d+)\D', end)
			end = int(round( (int(match.group(1))*1024*1024) / self.bytesPerCylinder ))
			
		elif end.lower().endswith('%'):
			match = re.search('^(\d+)\D', end)
			end = int(round( (float(match.group(1))/100) * self.cylinders ))
		else:
			raise Exception("Unsupported unit '%s' (please use MB or %)" % end)
		
		
		if (start < 1):
			# Lowest possible cylinder is 1
			start = 1
		if (end >= self.cylinders):
			# Highest possible cylinder is total cylinders - 1
			end = self.cylinders-1
		
		number = len(self.partitions)+1
		for part in self.partitions:
			if (end <= part['cylStart']):
				if (part['number']-1 <= number):
					# Insert before
					number = part['number']-1
		
		try:
			prev = self.getPartition(number-1)
			if (start <= prev['cylEnd']):
				# Partitions overlap
				start = prev['cylEnd']+1
		except:
			pass
		
		try:
			next = self.getPartition(number+1)
			if (end >= next['cylStart']):
				# Partitions overlap
				end = next['cylStart']-1
		except:
			pass
		
		logger.info("Creating partition on '%s': number: %s, type '%s', filesystem '%s', start: %s cyl, end: %s cyl." \
					% (self.device, number, type, fs, start, end))
		
		if ui: ui.getMessageBox().addText( \
				_("Creating partition on '%s': number: %s, type '%s', filesystem '%s', start: %s cyl, end: %s cyl.\n") \
				% (self.device, number, type, fs, start, end) )
		
		if (number < 1) or (number > 4):
			raise Exception('Cannot create partition %s' % number)
		
		self.partitions.append( {'number':	number,
					  'cylStart':	start,
					  'cylEnd':	end,
					  'cylSize':	end-start+1,
					  'start':	start * self.bytesPerCylinder,
					  'end':	end * self.bytesPerCylinder,
					  'size':	(end-start+1) * self.bytesPerCylinder,
					  'type':	partId,
					  'fs':		fs,
					  'boot':	boot,
					  'lba':	lba } )
		
		self.writePartitionTable()
		self.readPartitionTable()
	
	
	def deletePartition(self, partition, ui='default'):
		if ui == 'default': ui=userInterface
		
		if not partition:
			raise Exception("No partition given!")
		
		if ui: ui.getMessageBox().addText( _("Deleting partition '%s' on '%s'.\n") \
							% (partition, self.device) )
		
		logger.info("Deleting partition '%s' on '%s'." \
					% (partition, self.device))
		
		partitions = []
		exists = False
		for part in self.partitions:
			if part.get('number') == partition:
				exists = True
			else:
				partitions.append(part)
		
		if not exists:
			logger.warning("Cannot delete non existing partition '%s'." % partition)
			return
			
		self.partitions = partitions
		
		self.writePartitionTable()
		self.readPartitionTable()
	
	def mountPartition(self, partition, mountpoint, ui='default'):
		if ui == 'default': ui=userInterface
		mount(self.getPartition(partition)['device'], mountpoint, ui=ui)
	
	def umountPartition(self, partition, ui='default'):
		if ui == 'default': ui=userInterface
		umount(self.getPartition(partition)['device'], ui=ui)
	
	def createFilesystem(self, partition, fs = None, ui='default'):
		if ui == 'default': ui=userInterface
		if not fs:
			fs = self.getPartition(partition)['fs']
		fs = fs.lower()
		
		if not fs in ['fat32', 'ntfs', 'linux-swap', 'ext2', 'ext3', 'reiserfs', 'reiser4', 'xfs']:
			raise Exception("Creation of filesystem '%s' not supported!" % fs)
		
		if ui: ui.getMessageBox().addText(_("Creating filesystem '%s' on '%s'.\n") \
							% (fs, self.getPartition(partition)['device']) )
		logger.info("Creating filesystem '%s' on '%s'." % (fs, self.getPartition(partition)['device']))
		
		if (fs == 'fat32'):
			cmd = ( "mkfs.vfat -F 32 %s" % self.getPartition(partition)['device'] )
		elif (fs == 'linux-swap'):
			cmd = ( "mkswap %s" % self.getPartition(partition)['device'] )
		else:
			options = ''
			if fs in ['ext2', 'ext3', 'ntfs']:
				options = '-F'
				if (fs == 'ntfs'):
					# quick format
					options += ' -Q'
			elif fs in ['xfs', 'reiserfs', 'reiser4']:
				options = '-f'
			cmd = ( "mkfs.%s %s %s" % (fs, options, self.getPartition(partition)['device']) )
		
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		execute(cmd)
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
		self.readPartitionTable()
		
		
	def resizeFilesystem(self, partition, size = 0, fs = None, ui='default'):
		if ui == 'default': ui=userInterface
		if not fs:
			fs = self.getPartition(partition)['fs']
		if not fs.lower() in ['ntfs']:
			raise Exception("Resizing of filesystem '%s' not supported!" % fs)
		
		if (size <= 0):
			size = self.getPartition(partition)['size'] - 5*1024*1024
		
		if (size <= 0):
			raise Exception("New filesystem size of %s MB is not possible!" % (size/(1000*1000)))
		
		if ui: ui.getMessageBox().addText(_("Resizing filesystem on partition '%s' (%s) to %s MB.\n") \
							% (self.getPartition(partition)['device'], fs, (size/(1000*1000))) )
		
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		
		if (fs.lower() == 'ntfs'):
			cmd = ( "%s --force --size %s %s" % (which('ntfsresize'), size, self.getPartition(partition)['device']) )
			execute(cmd)
		
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
		
	def saveImage(self, partition, imageFile, ui='default'):
		if ui == 'default': ui=userInterface
		imageType = None
		image = None
		
		part = self.getPartition(partition)
		if not part:
			raise Exception('Partition %s does not exist' % partition)
		
		if ui: ui.getMessageBox().addText(_("Writing filesystem image of '%s' to '%s'.\n") \
							% (part['device'], imageFile) )
		
		if (part['fs'].lower() == 'ntfs'):
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			pipe = ''
			if imageFile.startswith('|'):
				pipe = imageFile
				imageFile = '-'
			
			logger.info("Saving partition '%s' to ntfsclone-image '%s'" % \
						(part['device'], imageFile) )
			
			# "-f" will write images of "dirty" volumes too
			# Better run chkdsk under windows before saving image!
			cmd = '%s --save-image -f --overwrite %s %s %s' % \
							(which('ntfsclone'), imageFile, part['device'], pipe)
			
			progress = None
			if ui:
				progress = ui.createProgressBox(
						width 	= int(ui.getWidth()/2), 
						height	= 8, 
						total	= 100, 
						title	= _("Writing filesystem image of partition '%s' to ntfsclone-image '%s'") % \
								(part['device'], os.path.basename(imageFile)) )
				progress.show()
			
			
			handle = execute(cmd, getHandle=True)
			done = False
			
			timeout = 0
			buf = ['']
			lastMsg = ''
			while not done:
				inp = handle.read(128)
				
				if inp:
					inp = inp.decode("latin-1")
					timeout=0
					
					b = inp.splitlines()
					if inp.endswith('\n') or inp.endswith('\r'):
						b.append('')
					
					buf = [ buf[-1] + b[0] ] + b[1:]
					
					for i in range( len(buf)-1 ):
						if ( buf[i].find('Syncing') != -1 ):
							progress.addText(_('Syncing ...\n'))
							done = True
						elif ( buf[i].find('Scanning') != -1 ):
							progress.addText(_('Scanning filesystem ...\n'))
						elif ( buf[i].find('Saving') != -1 ):
							progress.addText(_('Writing image ...\n'))
						match = re.search('\s(\d+)\s+MB\s+\((\d+[\.\,]\d+\%)\)\s', buf[i])
						if match:
							progress.addText(_("Filesystem usage is %s MB (%s)\n") \
										% (match.group(1), match.group(2)))
						match = re.search('\s(\d+)[\.\,]\d+\s', buf[i])
						if match:
							percent = int(match.group(1))
							if (progress and percent != progress.getState()):
								logger.debug(" -->>> %s" % buf[i])
								progress.setState(percent)
						else:
							try:
								logger.debug(" -->>> %s" % buf[i])
							except:
								pass
							
					lastMsg = buf[-2]
					buf[:-1] = []
				
				elif (timeout >= 100):
					if progress: progress.hide()
					raise Exception(_("Failed: %s") % lastMsg)
				else:
					timeout += 1
					continue
			
			time.sleep(3)
			if handle: handle.close	
			if progress: progress.hide()
			
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
		else:
			raise Exception("Unsupported filesystem '%s'." % part['fs'])
	
	
	
	def restoreImage(self, partition, imageFile, ui='default'):
		if ui == 'default': ui=userInterface
		imageType = None
		image = None
		
		pipe = ''
		if imageFile.endswith('|'):
			pipe = imageFile
			imageFile = '-'
		
		if ui: ui.getMessageBox().addText(_("Restoring filesystem image '%s' to '%s'.\n") \
							% (imageFile, self.getPartition(partition)['device']) )
		try:
			if pipe:
				fi = popen2.Popen3(pipe[:-1] + " 2>/dev/null", capturestderr=False)
				pid = fi.pid
				head = fi.fromchild.read(128)
				logger.debug("Read 128 Bytes from pipe '%s': %s" % ('pipe', head))
				if (head.find('ntfsclone-image') != -1):
					logger.notice("Image type is ntfsclone")
					imageType = 'ntfsclone'
				
				fi.fromchild.close()
				
				while( fi.poll() == -1 ):
					pids = os.listdir("/proc")
					for p in pids:
						if not os.path.exists( os.path.join("/proc", p, "status") ):
							continue
						f = open( os.path.join("/proc", p, "status") )
						for line in f.readlines():
							if line.startswith("PPid:"):
								ppid = line.split()[1].strip()
								if (ppid == str(pid)):
									logger.info("Killing process %s" % p)
									os.kill(int(p), signal.SIGKILL)
									
					logger.info("Killing process %s" % pid)
					os.kill(pid, signal.SIGKILL)
					time.sleep(1)
				
			else:
				image = open(imageFile, 'r')
				head = image.read(128)
				logger.debug("Read 128 Bytes from file '%s': %s" % (imageFile, head))
				if (head.find('ntfsclone-image') != -1):
					logger.info("Image type is ntfsclone")
					imageType = 'ntfsclone'
				image.close()
		except:
			if image:
				image.close()
			raise
		
		if (imageType == 'ntfsclone'):
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			logger.info("Restoring ntfsclone-image '%s' to '%s'" % \
							(imageFile, self.getPartition(partition)['device']) )
			
			cmd = '%s %s --restore-image --overwrite %s %s' % \
							(pipe, which('ntfsclone'), self.getPartition(partition)['device'], imageFile)
			
			progress = None
			if ui:
				progress = ui.createProgressBox(
						width 	= int(ui.getWidth()/2), 
						height	= 8, 
						total	= 100, 
						title	= _("Restoring ntfsclone image '%s' to '%s'") \
								% (os.path.basename(imageFile), self.getPartition(partition)['device']) )
				progress.show()
			
			handle = execute(cmd, getHandle=True)
			done = False
			
			timeout = 0
			buf = ['']
			lastMsg = ''
			while not done:
				inp = handle.read(128)
				
				if inp:
					inp = inp.decode("latin-1")
					timeout=0
					
					b = inp.splitlines()
					if inp.endswith('\n') or inp.endswith('\r'):
						b.append('')
					
					buf = [ buf[-1] + b[0] ] + b[1:]
					
					for i in range( len(buf)-1 ):
						if ( buf[i].find('Syncing') != -1 ):
							progress.addText(_('Syncing ...\n'))
							done = True
						match = re.search('\s(\d+)[\.\,]\d\d\spercent', buf[i])
						if match:
							percent = int(match.group(1))
							if (progress and percent != progress.getState()):
								logger.debug(" -->>> %s" % buf[i])
								progress.setState(percent)
						else:
							logger.debug(" -->>> %s" % buf[i])
						
					lastMsg = buf[-2]
					buf[:-1] = []
				
				elif (timeout >= 100):
					if progress: progress.hide()
					raise Exception(_("Failed: %s") % lastMsg)
				else:
					timeout += 1
					continue
			
			time.sleep(3)
			if handle: handle.close	
			if progress: progress.hide()
			
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
			
			self.setNTFSPartitionStartSector(partition, ui=ui)
			self.resizeFilesystem(partition, fs='ntfs', ui=ui)
		else:
			raise Exception("Unknown image type.")
		



