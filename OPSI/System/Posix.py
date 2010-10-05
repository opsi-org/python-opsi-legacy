#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Posix   =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008, 2009, 2010 uib GmbH
   
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
import os, sys, subprocess, locale, threading, time, codecs, socket, posix
import copy as pycopy
from signal import *

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Util import objectToBeautifiedText, removeUnit

# Get Logger instance
logger = Logger()

# Constants
GEO_OVERWRITE_SO = '/usr/local/lib/geo_override.so'
BIN_WHICH        = '/usr/bin/which'
WHICH_CACHE      = {}

class SystemSpecificHook(object):
	def __init__(self):
		pass
	
	def pre_reboot(self, wait):
		return wait
	
	def post_reboot(self, wait):
		return None
	
	def error_reboot(self, wait, exception):
		pass
	
	
	def pre_halt(self, wait):
		return wait
	
	def post_halt(self, wait):
		return None
	
	def error_halt(self, wait, exception):
		pass
	
	
	def pre_Harddisk_deletePartitionTable(self, harddisk):
		return None
	
	def post_Harddisk_deletePartitionTable(self, harddisk):
		return None
	
	def error_Harddisk_deletePartitionTable(self, harddisk, exception):
		pass
	
	
	def pre_Harddisk_writePartitionTable(self, harddisk):
		return None
	
	def post_Harddisk_writePartitionTable(self, harddisk):
		return None
	
	def error_Harddisk_writePartitionTable(self, harddisk, exception):
		pass
	
	
	def pre_Harddisk_readPartitionTable(self, harddisk):
		return None
	
	def post_Harddisk_readPartitionTable(self, harddisk):
		return None
	
	def error_Harddisk_readPartitionTable(self, harddisk, exception):
		pass
	
	
	def pre_Harddisk_setPartitionBootable(self, harddisk, partition, bootable):
		return (partition, bootable)
	
	def post_Harddisk_setPartitionBootable(self, harddisk, partition, bootable):
		return None
	
	def error_Harddisk_setPartitionBootable(self, harddisk, partition, bootable, exception):
		pass
	
	
	def pre_Harddisk_setPartitionId(self, harddisk, partition, id):
		return (partition, id)
	
	def post_Harddisk_setPartitionId(self, harddisk, partition, id):
		return None
	
	def error_Harddisk_setPartitionId(self, harddisk, partition, id, exception):
		pass
	
	
	def pre_Harddisk_readMasterBootRecord(self, harddisk):
		return None
	
	def post_Harddisk_readMasterBootRecord(self, harddisk, result):
		return result
	
	def error_Harddisk_readMasterBootRecord(self, harddisk, exception):
		pass
	
	
	def pre_Harddisk_writeMasterBootRecord(self, harddisk, system):
		return system
	
	def post_Harddisk_writeMasterBootRecord(self, harddisk, system):
		return None
	
	def error_Harddisk_writeMasterBootRecord(self, harddisk, system, exception):
		pass
	
	
	def pre_Harddisk_readPartitionBootRecord(self, harddisk, partition):
		return partition
	
	def post_Harddisk_readPartitionBootRecord(self, harddisk, partition, result):
		return result
	
	def error_Harddisk_readPartitionBootRecord(self, harddisk, partition, exception):
		pass
	
	
	def pre_Harddisk_writePartitionBootRecord(self, harddisk, partition, fsType):
		return (partition, fsType)
	
	def post_Harddisk_writePartitionBootRecord(self, harddisk, partition, fsType):
		return None
	
	def error_Harddisk_writePartitionBootRecord(self, harddisk, partition, fsType, exception):
		pass
	
	
	def pre_Harddisk_setNTFSPartitionStartSector(self, harddisk, partition, sector):
		return (partition, sector)
	
	def post_Harddisk_setNTFSPartitionStartSector(self, harddisk, partition, sector):
		return None
	
	def error_Harddisk_setNTFSPartitionStartSector(self, harddisk, partition, sector, exception):
		pass
	
	
	def pre_Harddisk_createPartition(self, harddisk, start, end, fs, type, boot, lba):
		return (start, end, fs, type, boot, lba)
	
	def post_Harddisk_createPartition(self, harddisk, start, end, fs, type, boot, lba):
		return None
	
	def error_Harddisk_createPartition(self, harddisk, start, end, fs, type, boot, lba, exception):
		pass
	
	
	def pre_Harddisk_deletePartition(self, harddisk, partition):
		return partition
	
	def post_Harddisk_deletePartition(self, harddisk, partition):
		return None
	
	def error_Harddisk_deletePartition(self, harddisk, partition, exception):
		pass
	
	
	def pre_Harddisk_mountPartition(self, harddisk, partition, mountpoint, **options):
		return (partition, mountpoint, options)
	
	def post_Harddisk_mountPartition(self, harddisk, partition, mountpoint, **options):
		return None
	
	def error_Harddisk_mountPartition(self, harddisk, partition, mountpoint, exception, **options):
		pass
	
	
	def pre_Harddisk_umountPartition(self, harddisk, partition):
		return partition
	
	def post_Harddisk_umountPartition(self, harddisk, partition):
		return None
	
	def error_Harddisk_umountPartition(self, harddisk, partition, exception):
		pass
	
	
	def pre_Harddisk_createFilesystem(self, harddisk, partition, fs):
		return (partition, fs)
	
	def post_Harddisk_createFilesystem(self, harddisk, partition, fs):
		return None
	
	def error_Harddisk_createFilesystem(self, harddisk, partition, fs, exception):
		pass
	
	
	def pre_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs):
		return (partition, size, fs)
	
	def post_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs):
		return None
	
	def error_Harddisk_resizeFilesystem(self, harddisk, partition, size, fs, exception):
		pass
	
	
	def pre_Harddisk_shred(self, harddisk, partition, iterations, progressSubject):
		return (partition, iterations, progressSubject)
	
	def post_Harddisk_shred(self, harddisk, partition, iterations, progressSubject):
		return None
	
	def error_Harddisk_shred(self, harddisk, partition, iterations, progressSubject, exception):
		pass
	
	
	def pre_Harddisk_fill(self, harddisk, partition, infile, progressSubject):
		return (partition, infile, progressSubject)
	
	def post_Harddisk_fill(self, harddisk, partition, infile, progressSubject):
		return None
	
	def error_Harddisk_fill(self, harddisk, partition, infile, progressSubject, exception):
		pass
	
	
	def pre_Harddisk_saveImage(self, harddisk, partition, imageFile, progressSubject):
		return (partition, imageFile, progressSubject)
	
	def post_Harddisk_saveImage(self, harddisk, partition, imageFile, progressSubject):
		return None
	
	def error_Harddisk_saveImage(self, harddisk, partition, imageFile, progressSubject, exception):
		pass
	
	
	def pre_Harddisk_restoreImage(self, harddisk, partition, imageFile, progressSubject):
		return (partition, imageFile, progressSubject)
	
	def post_Harddisk_restoreImage(self, harddisk, partition, imageFile, progressSubject):
		return None
	
	def error_Harddisk_restoreImage(self, harddisk, partition, imageFile, progressSubject, exception):
		pass
	
	
	def pre_auditHardware(self, config, hostId, progressSubject):
		return (config, hostId, progressSubject)
	
	def post_auditHardware(self, config, hostId, result):
		return result
	
	def error_auditHardware(self, config, hostId, progressSubject, exception):
		pass
	
hooks = []
def addSystemHook(hook):
	global hooks
	if not hook in hooks:
		hooks.append(hook)

def removeSystemHook(hook):
	global hooks
	if hook in hooks:
		hooks.remove(hook)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                               INFO                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getHostname():
	return forceHostname(socket.gethostname())

def getFQDN():
	return forceUnicodeLower(socket.getfqdn())
	
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
		logger.debug(u'Reading /proc/cmdline')
		f = codecs.open("/proc/cmdline", "r", "utf-8")
		cmdline = f.readline()
		cmdline = cmdline.strip()
		f.close()
	except IOError, e:
		if f: f.close()
		raise Exception(u"Error reading '/proc/cmdline': %s" % e)
	if cmdline:
		for option in cmdline.split():
			keyValue = option.split(u"=")
			if ( len(keyValue) < 2 ):
				params[keyValue[0].strip().lower()] = u''
			else:
				params[keyValue[0].strip().lower()] = keyValue[1].strip()
	return params

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            NETWORK                                                -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def getEthernetDevices():
	devices = []
	f = open("/proc/net/dev")
	try:
		for line in f.readlines():
			line = line.strip()
			if not line or (line.find(':') == -1):
				continue
			device = line.split(':')[0].strip()
			if device.startswith('eth') or device.startswith('tr') or device.startswith('br'):
				logger.info(u"Found ethernet device: '%s'" % device)
				devices.append(device)
	finally:
		f.close()
		
	return devices

def getNetworkInterfaces():
	interfaces = []
	for device in getEthernetDevices():
		interfaces.append(getNetworkDeviceConfig(device))
	return interfaces
	
def getNetworkDeviceConfig(device):
	if not device:
		raise Exception(u"No device given")
	
	result = {
		'device':          device,
		'hardwareAddress': None,
		'ipAddress':       None,
		'broadcast':       None,
		'netmask':         None,
		'gateway':         None,
		'vendorId':        None,
		'deviceId':        None
	}
	for line in execute(u"%s %s" % (which(u'ifconfig'), device)):
		line = line.lower().strip()
		match = re.search('\s([\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}).*', line)
		if match:
			result['hardwareAddress'] = forceHardwareAddress(match.group(1))
			continue
		if line.startswith('inet '):
			parts = line.split(':')
			if (len(parts) != 4):
				logger.error(u"Unexpected ifconfig line '%s'" % line)
				continue
			result['ipAddress'] = forceIpAddress(parts[1].split()[0].strip())
			result['broadcast'] = forceIpAddress(parts[2].split()[0].strip())
			result['netmask']   = forceIpAddress(parts[3].split()[0].strip())
	
	for line in execute(u"%s route" % which(u'ip')):
		line = line.lower().strip()
		match = re.search('via\s(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\sdev\s(\S+)\s*', line)
		if match and (match.group(2).lower() == device.lower()):
			result['gateway'] = forceIpAddress(match.group(1))
	
	try:
		f = open('/sys/class/net/%s/device/vendor' % device)
		x = f.read().strip()
		f.close()
		if not x.startswith('0x'):
			x = "%x" % int(x)
			x = ((4-len(x))*'0') + x
		else:
			x = x[2:]
		result['vendorId'] = forceHardwareVendorId(x)
		
		f = open('/sys/class/net/%s/device/device' % device)
		x = f.read().strip()
		f.close()
		if not x.startswith('0x'):
			# FIXME: what is wrong with virtio devices?
			if (result['vendorId'] == '1AF4'):
				x = '100%d' % (int(x)-1)
			else:
				x = "%x" % int(x)
				x = ((4-len(x))*'0') + x
		else:
			x = x[2:]
		result['deviceId'] = forceHardwareDeviceId(x)
	except Exception, e:
		print e
		logger.error(u"Failed to get vendor/device id for network device %s" % device)
	return result
	
def getDefaultNetworkInterfaceName():
	for interface in getNetworkInterfaces():
		if interface['gateway']:
			logger.info(u"Default network interface found: %s" % interface['device'])
			return interface['device']
	logger.info(u"Default network interface not found")
	return None

class NetworkPerformanceCounter(threading.Thread):
	def __init__(self, interface):
		threading.Thread.__init__(self)
		if not interface:
			raise ValueError(u"No interface given")
		self.interface = interface
		self._lastBytesIn = 0
		self._lastBytesOut = 0
		self._lastTime = None
		self._bytesInPerSecond = 0
		self._bytesOutPerSecond = 0
		self._regex = re.compile('\s*(\S+)\:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)')
		self._running = False
		self._stopped = False
		self.start()
		
	def __del__(self):
		self.stop()
	
	def stop(self):
		self._stopped = True
		
	def run(self):
		self._running = True
		while not self._stopped:
			self._getStatistics()
			time.sleep(1)
		
	def _getStatistics(self):
		f = open('/proc/net/dev', 'r')
		try:
			for line in f.readlines():
				line = line.strip()
				match = self._regex.search(line)
				if match and (match.group(1) == self.interface):
					#       |   Receive                                                |  Transmit
					# iface: bytes    packets errs drop fifo frame compressed multicast bytes    packets errs drop fifo colls carrier compressed
					now = time.time()
					bytesIn = int(match.group(2))
					bytesOut = int(match.group(10))
					timeDiff = 1
					if self._lastTime:
						timeDiff = now - self._lastTime
					if self._lastBytesIn:
						self._bytesInPerSecond = (bytesIn - self._lastBytesIn)/timeDiff
						if (self._bytesInPerSecond < 0):
							self._bytesInPerSecond = 0
					if self._lastBytesOut:
						self._bytesOutPerSecond = (bytesOut - self._lastBytesOut)/timeDiff
						if (self._bytesOutPerSecond < 0):
							self._bytesOutPerSecond = 0
					self._lastBytesIn = bytesIn
					self._lastBytesOut = bytesOut
					self._lastTime = now
					break
		finally:
			f.close()
		
	def getBytesInPerSecond(self):
		return self._bytesInPerSecond
	
	def getBytesOutPerSecond(self):
		return self._bytesOutPerSecond

def getDHCPResult(device):
	"""
	Reads DHCP result from pump
	returns possible key/values:
	ip, netmask, bootserver, nextserver, gateway, bootfile, hostname, domain.
	keys are converted to lower case
	"""
	if not device:
		raise Exception(u"No device given")
	
	dhcpResult = {}
	try:
		for line in execute( u'%s -s -i %s' % (which('pump'), device) ):
			line = line.strip()
			keyValue = line.split(u":")
			if ( len(keyValue) < 2 ):
				# No ":" in pump output after "boot server" and "next server"
				if line.lstrip().startswith(u'Boot server'):
					keyValue[0] = u'Boot server'
					keyValue.append(line.split()[2])
				elif line.lstrip().startswith(u'Next server'):
					keyValue[0] = u'Next server'
					keyValue.append(line.split()[2])
				else:
					continue
			# Some DHCP-Servers are returning multiple domain names seperated by whitespace,
			# so we split all values at whitespace and take the first element
			dhcpResult[keyValue[0].replace(u' ',u'').lower()] = keyValue[1].strip().split()[0]
	except Exception, e:
		logger.warning(e)
	return dhcpResult
	
def ifconfig(device, address, netmask=None):
	cmd = u'%s %s %s' % (which('ifconfig'), device, forceIpAddress(address))
	if netmask:
		cmd += u' netmask %s' % forceNetmask(netmask)
	execute(cmd)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                   SESSION / DESKTOP HANDLING                                      -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def reboot(wait = 10):
	for hook in hooks:
		wait = hook.pre_reboot(wait)
	
	try:
		wait = forceInt(wait)
		if (wait > 0):
			execute(u'%s %d; %s -r now' % (which('sleep'), wait, which('shutdown')), nowait = True)
		else:
			execute(u'%s -r now' % which('shutdown'), nowait = True)
		#execute(u'%s %d; %s -r now' % (which('sleep'), int(wait), which('shutdown')), nowait = True)
		#execute(u'(%s %d; %s s > /proc/sysrq-trigger; %s u > /proc/sysrq-trigger; %s b > /proc/sysrq-trigger) >/dev/null 2>/dev/null </dev/null &' \
		#	% (which('sleep'), int(wait), which('echo'), which('echo'), which('echo')), nowait = True)
	except Exception, e:
		for hook in hooks:
			hook.error_reboot(wait, e)
		raise
	
	for hook in hooks:
		hook.post_reboot(wait)
	
def halt(wait = 10):
	for hook in hooks:
		wait = hook.pre_halt(wait)
	
	try:
		wait = forceInt(wait)
		if (wait > 0):
			execute(u'%s %d; %s -h now' % (which('sleep'), wait, which('shutdown')), nowait = True)
		else:
			execute(u'%s -h now' % which('shutdown'), nowait = True)
		#execute(u'(%s %d; %s s > /proc/sysrq-trigger; %s u > /proc/sysrq-trigger; %s o > /proc/sysrq-trigger) >/dev/null 2>/dev/null </dev/null &' \
		#	% (which('sleep'), int(wait), which('echo'), which('echo'), which('echo')), nowait = True)
	except Exception, e:
		for hook in hooks:
			hook.error_halt(wait, e)
		raise
	
	for hook in hooks:
		hook.post_halt(wait)
	

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                        PROCESS HANDLING                                           -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def which(cmd):
	if not WHICH_CACHE.has_key(cmd):
		w = os.popen(u'%s "%s" 2>/dev/null' % (BIN_WHICH, cmd))
		path = w.readline().strip()
		w.close()
		if not path:
			raise Exception(u"Command '%s' not found in PATH" % cmd)
		WHICH_CACHE[cmd] = path
		logger.debug(u"Command '%s' found at: '%s'" % (cmd, WHICH_CACHE[cmd]))
	
	return WHICH_CACHE[cmd]

def execute(cmd, nowait=False, getHandle=False, ignoreExitCode=[], exitOnStderr=False, captureStderr=True, encoding=None):
	"""
	Executes a command and returns output lines as list
	"""
	
	nowait          = forceBool(nowait)
	getHandle       = forceBool(getHandle)
	exitOnStderr    = forceBool(exitOnStderr)
	captureStderr   = forceBool(captureStderr)
	
	exitCode = 0
	result = []
	
	try:
		logger.info(u"Executing: %s" % cmd)
		
		if nowait:
			os.spawnv(os.P_NOWAIT, which('bash'), [which('bash'), '-c', cmd])
			return []
		
		elif getHandle:
			if captureStderr:
				return (subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)).stdout
			else:
				return (subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None)).stdout
		
		else:
			data = ''
			stderr = None
			if captureStderr:
				stderr	= subprocess.PIPE
			proc = subprocess.Popen(
				cmd,
				shell	= True,
				stdin	= subprocess.PIPE,
				stdout	= subprocess.PIPE,
				stderr	= stderr,
			)
			if not encoding:
				encoding = proc.stdin.encoding
				if (encoding == 'ascii'): encoding = 'utf-8'
			if not encoding:
				encoding = locale.getpreferredencoding()
				if (encoding == 'ascii'): encoding = 'utf-8'
			
			logger.info(u"Using encoding '%s'" % encoding)
			
			flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
			fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
			
			if captureStderr:
				flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
				fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
			
			ret = None
			while ret is None:
				ret = proc.poll()
				try:
					chunk = proc.stdout.read()
					if (len(chunk) > 0):
						data += chunk
				except IOError, e:
					if (e.errno != 11):
						raise
				
				if captureStderr:
					try:
						chunk = proc.stderr.read()
						if (len(chunk) > 0):
							if exitOnStderr:
								raise Exception(u"Command '%s' failed: %s" % (cmd, chunk) )
							data += chunk
					except IOError, e:
						if (e.errno != 11):
							raise
				
				time.sleep(0.001)
			
			exitCode = ret
			if data:
				lines = data.split('\n')
				for i in range(len(lines)):
					line = lines[i].decode(encoding, 'replace')
					if (i == len(lines) - 1) and not line:
						break
					logger.debug(u'>>> %s' % line)
					result.append(line)
			
	except (os.error, IOError), e:
		# Some error occured during execution
		raise Exception(u"Command '%s' failed:\n%s" % (cmd, e) )
	
	logger.debug(u"Exit code: %s" % exitCode)
	if exitCode:
		if   type(ignoreExitCode) is bool and ignoreExitCode:
			pass
		elif type(ignoreExitCode) is list and exitCode in ignoreExitCode:
			pass
		else:
			raise Exception(u"Command '%s' failed (%s):\n%s" % (cmd, exitCode, u'\n'.join(result)) )
	return result




# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                            FILESYSTEMS                                            -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def getHarddisks():
	disks = []
	
	#_("Looking for harddisks.\n")
	
	# Get all available disks
	result = execute(u'%s -s -uB' % which('sfdisk'))
	for line in result:
		if not line.lstrip().startswith(u'/dev'):
			continue
		(dev, size) = line.split(u':')
		size = forceInt(size.strip())
		logger.debug(u"Found disk =>>> dev: '%s', size: %0.2f GB" % (dev, size/(1024*1024)) )
		
		hd = Harddisk(dev)
		#_("Hardisk '%s' found (%s MB).\n") % (hd.device, hd.size/(1024*1024)))
		disks.append(hd)
	
	if ( len(disks) <= 0 ):
		raise Exception(u'No harddisks found!')
	
	return disks

def getDiskSpaceUsage(path):
	disk = os.statvfs(path)
	info = {}
	info['capacity'] = disk.f_bsize * disk.f_blocks
	info['available'] = disk.f_bsize * disk.f_bavail
	info['used'] = disk.f_bsize * (disk.f_blocks - disk.f_bavail)
	info['usage'] = float(disk.f_blocks - disk.f_bavail) / float(disk.f_blocks)
	logger.info(u"Disk space usage for path '%s': %s" % (path, info))
	return info

def mount(dev, mountpoint, **options):
	dev = forceUnicode(dev)
	mountpoint = forceFilename(mountpoint)
	if not os.path.isdir(mountpoint):
		os.makedirs(mountpoint)
	
	for (key, value) in options.items():
		options[key] = forceUnicode(value)
	
	fs = u''
	credentialsFiles = []
	if dev.lower().startswith('smb://'):
		match = re.search('^smb://([^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			fs = u'-t cifs'
			parts = match.group(1).split('/')
			dev = u'//%s/%s' % (parts[0], parts[1])
			if not 'username' in options:
				options['username'] = u'guest'
			if not 'password' in options:
				options['password'] = u''
			if (options['username'].find('\\') != -1):
				(options['domain'], options['username']) = options['username'].split('\\', 1)
			
			credentialsFile = u"/tmp/.cifs-credentials.%s" % parts[0]
			if os.path.exists(credentialsFile):
				os.remove(credentialsFile)
			f = open(credentialsFile, "w")
			f.close()
			os.chmod(credentialsFile, 0600)
			f = codecs.open(credentialsFile, "w", "iso-8859-15")
			f.write(u"username=%s\n" % options['username'])
			f.write(u"password=%s\n" % options['password'])
			f.close()
			options['credentials'] = credentialsFile
			credentialsFiles.append(credentialsFile)
			
			if not options['domain']:
				del options['domain']
			del options['username']
			del options['password']
		else:
			raise Exception(u"Bad smb uri '%s'" % dev)
		
	elif dev.lower().startswith('webdav://') or dev.lower().startswith('webdavs://') or \
	     dev.lower().startswith('http://') or dev.lower().startswith('https://'):
	     	# We need enough free space in /var/cache/davfs2
	     	# Maximum transfer file size <= free space in /var/cache/davfs2
		match = re.search('^(http|webdav)(s*)(://[^/]+\/.+)$', dev, re.IGNORECASE)
		if match:
			fs  = u'-t davfs'
			dev = u'http' + match.group(2) + match.group(3)
		else:
			raise Exception(u"Bad webdav url '%s'" % dev)
		
		if not 'username' in options:
			options['username'] = u''
		if not 'password' in options:
			options['password'] = u''
		if not 'servercert' in options:
			options['servercert'] = u''
		
		if options['servercert']:
			f = open(u"/etc/davfs2/certs/trusted.pem", "w")
			f.write(options['servercert'])
			f.close()
			os.chmod(u"/etc/davfs2/certs/trusted.pem", 0644)
		
		f = codecs.open(u"/etc/davfs2/secrets", "r", "utf8")
		lines = f.readlines()
		f.close()
		f = codecs.open(u"/etc/davfs2/secrets", "w", "utf8")
		for line in lines:
			if re.search("^%s\s+" % dev, line):
				f.write(u"#")
			f.write(line)
		f.write(u'%s "%s" "%s"\n' % (dev, options['username'], options['password']))
		f.close()
		os.chmod(u"/etc/davfs2/secrets", 0600)
		
		if options['servercert']:
			f = open(u"/etc/davfs2/davfs2.conf", "r")
			lines = f.readlines()
			f.close()
			f = open(u"/etc/davfs2/davfs2.conf", "w")
			for line in lines:
				if re.search("^servercert\s+", line):
					f.write("#")
				f.write(line)
			f.write(u"servercert /etc/davfs2/certs/trusted.pem\n")
			f.close()
		
		del options['username']
		del options['password']
		del options['servercert']
		
	elif dev.lower().startswith(u'/'):
		pass
	
	elif dev.lower().startswith(u'file://'):
		dev = dev[7:]
	
	else:
		raise Exception(u"Cannot mount unknown fs type '%s'" % dev)
	
	optString = u''
	for (key, value) in options.items():
		key   = forceUnicode(key)
		value = forceUnicode(value)
		if value:
			optString += u',%s=%s' % (key, value)
		else:
			optString += u',%s' % key
	if optString:
		optString = u'-o "%s"' % optString[1:].replace('"', '\\"')
	
	try:
		result = execute(u"%s %s %s %s %s" % (which('mount'), fs, optString, dev, mountpoint))
	except Exception, e:
		for f in credentialsFiles:
			os.remove(f)
		logger.error(u"Failed to mount '%s': %s" % (dev, e))
		raise Exception(u"Failed to mount '%s': %s" % (dev, e))
	for f in credentialsFiles:
		os.remove(f)
	
def umount(devOrMountpoint):
	cmd = u"%s %s" % (which('umount'), devOrMountpoint)
	try:
		result = execute(cmd)
	except Exception, e:
		logger.error(u"Cannot umount: %s" % e)
		raise Exception(u"Cannot umount: %s" % e)

def getBlockDeviceBusType(device):
	# Returns either 'IDE', 'SCSI', 'SATA', 'RAID' or None (not found)
	device = forceFilename(device)
	
	(devs, type) = ([], None)
	if os.path.islink(device):
		d = os.readlink(device)
		if not d.startswith(u'/'):
			d = os.path.join(os.path.dirname(device), d)
		device = d
		
	for line in execute(u'%s --disk --cdrom' % which('hwinfo')):
		if re.search('^\s+$', line):
			(devs, type) = ([], None)
			continue
		
		match = re.search('^\s+Device Files*:(.*)$', line)
		if match:
			if (match.group(1).find(u',') != -1):
				devs = match.group(1).split(u',')
			elif (match.group(1).find(u'(') != -1):
				devs = match.group(1).replace(u')', u' ').split(u'(')
			else:
				devs = [ match.group(1) ]
			for i in range(len(devs)):
				devs[i] = devs[i].strip()
		
		match = re.search('^\s+Attached to:\s+[^\(]+\((\S+)\s*', line)
		if match:
			type = match.group(1)
		
		if devs and device in devs and type:
			logger.info(u"Bus type of device '%s' is '%s'" % (device, type))
			return type


def getBlockDeviceContollerInfo(device):
	device = forceFilename(device)
	lines = execute(u'%s -short -numeric' % which('lshw'))
	'''
	example:
	...
	/0/100                      bridge     440FX - 82441FX PMC [Natoma] [8086:1237]
	/0/100/1                    bridge     82371SB PIIX3 ISA [Natoma/Triton II] [8086:7000]
	/0/100/1.1      scsi0       storage    82371SB PIIX3 IDE [Natoma/Triton II] [8086:7010]
	/0/100/1.1/0    /dev/sda    disk       10GB QEMU HARDDISK
	/0/100/1.1/0/1  /dev/sda1   volume     10236MiB Windows NTFS volume
	/0/100/1.1/1    /dev/cdrom  disk       SCSI CD-ROM
	...
	'''
	storageControllers = {}
	
	for line in lines:
		match = re.search('^(/\S+)\s+(\S+)\s+storage\s+(\S+.*)\s\[([a-fA-F0-9]{4})\:([a-fA-F0-9]{4})\]$', line)
		if match:
			storageControllers[match.group(1)] = {
				'hwPath':      forceUnicode(match.group(1)),
				'device':      forceUnicode(match.group(2)),
				'description': forceUnicode(match.group(3)),
				'vendorId':    forceHardwareVendorId(match.group(4)),
				'deviceId':    forceHardwareDeviceId(match.group(5))
			}
			continue
		
		parts = line.split(None, 3)
		if (len(parts) < 4):
			continue
		if (parts[1].lower() == device):
			for hwPath in storageControllers.keys():
				if parts[0].startswith(hwPath + u'/'):
					return storageControllers[hwPath]
	return None
	
class Harddisk:
	
	def __init__(self, device):
		''' Harddisk constructor. '''
		self.device        = forceFilename(device)
		self.model         = u''
		self.signature     = None
		self.biosDevice    = None
		self.biosHeads     = 0
		self.biosSectors   = 0
		self.biosCylinders = 0
		self.cylinders     = 0
		self.heads         = 0
		self.sectors       = 0
		self.label         = None
		self.size          = -1
		self.partitions    = []
		self.ldPreload     = None
		
		self.useBIOSGeometry()
		self.readPartitionTable()
	
	def getBusType(self):
		return getBlockDeviceBusType(self.device)
	
	def getControllerInfo(self):
		return getBlockDeviceContollerInfo(self.device)
	
	def useBIOSGeometry(self):
		# Make sure your kernel supports edd (CONFIG_EDD=y/m) and module is loaded if not compiled in
		
		try:
			execute(u'%s edd' % which('modprobe'))
		except Exception, e:
			logger.error(e)
			return
		# geo_override.so will affect all devices !
		logger.info(u"Using geo_override.so for all disks.")
		self.ldPreload = GEO_OVERWRITE_SO
		
	def getSignature(self):
		hd = posix.open(str(self.device), posix.O_RDONLY)
		posix.lseek(hd, 440, 0)
		x = posix.read(hd, 4)
		posix.close(hd)
		
		logger.debug(u"Read signature from device '%s': %s,%s,%s,%s" \
				% (self.device, ord(x[0]), ord(x[1]), ord(x[2]), ord(x[3])) )
		
		self.signature = 0
		self.signature += ord(x[3]) << 24
		self.signature += ord(x[2]) << 16
		self.signature += ord(x[1]) << 8
		self.signature += ord(x[0])
		logger.debug(u"Device Signature: '%s'" % hex(self.signature))
	
	def setDiskLabelType(self, label):
		label = forceUnicodeLower(label)
		if label not in (u"bsd", u"gpt", u"loop", u"mac", u"mips", u"msdos", u"pc98", u"sun"):
			raise Exception(u"Unknown disk label '%s'" % label)
		self.label = label
	
	def setPartitionId(self, partition, id):
		for hook in hooks:
			(partition, id) = hook.pre_Harddisk_setPartitionId(self, partition, id)
		try:
			partition = forceInt(partition)
			id = forceUnicodeLower(id)
			
			if (partition < 1) or (partition > 4):
				raise Exception(u"Partition has to be int value between 1 and 4")
			
			if not re.search('^[a-f0-9]{2}$', id):
				if id in (u'linux', u'ext2', u'ext3', u'ext4', u'xfs', u'reiserfs', u'reiser4'):
					id = u'83'
				elif (id == u'linux-swap'):
					id = u'82'
				elif (fs == u'fat32'):
					id = u'0c'
				elif (fs == u'ntfs'):
					id = u'07'
				else:
					raise Exception(u"Partition type '%s' not supported!" % id)
			id = eval('0x' + id)
			offset = 0x1be + (partition-1)*16 + 4
			f = open(self.device, 'rb+')
			f.seek(offset)
			f.write(chr(id))
			f.close()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_setPartitionId(self, partition, id, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_setPartitionId(self, partition, id)
		
	def setPartitionBootable(self, partition, bootable):
		for hook in hooks:
			(partition, bootable) = hook.pre_Harddisk_setPartitionBootable(self, partition, bootable)
		try:
			partition = forceInt(partition)
			bootable = forceBool(bootable)
			if (partition < 1) or (partition > 4):
				raise Exception("Partition has to be int value between 1 and 4")
			
			offset = 0x1be + (partition-1)*16 + 4
			f = open(self.device, 'rb+')
			f.seek(offset)
			if bootable:
				f.write(chr(0x80))
			else:
				f.write(chr(0x00))
			f.close()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_setPartitionBootable(self, partition, bootable, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_setPartitionBootable(self, partition, bootable)
	
	def readPartitionTable(self):
		for hook in hooks:
			hook.pre_Harddisk_readPartitionTable(self)
		try:
			self.partitions = []
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			result = execute(u"%s -l %s" % (which('sfdisk'), self.device))
			for line in result:
				if (line.find(u'unrecognized partition table type') != -1):
					execute('%s -e "0,0\n\n\n\n" | %s -D %s' % (which('echo'), which('sfdisk'), self.device))
					result = execute(which('sfdisk') + ' -l ' + self.device)
					break
			
			for line in result:
				line = line.strip()
				if line.lower().startswith(u'disk'):
					match = re.search('\s+(\d+)\s+cylinders,\s+(\d+)\s+heads,\s+(\d+)\s+sectors', line)
					if not match:
						raise Exception(u"Unable to get geometry for disk '%s'" % self.device)
					
					self.cylinders = forceInt(match.group(1))
					self.heads     = forceInt(match.group(2))
					self.sectors   = forceInt(match.group(3))
				
				elif line.lower().startswith(u'units'):
					match = re.search('cylinders\s+of\s+(\d+)\s+bytes', line)
					if not match:
						raise Exception(u"Unable to get bytes/cylinder for disk '%s'" % self.device)
					self.bytesPerCylinder = forceInt(match.group(1))
					
					self.size = self.bytesPerCylinder * self.cylinders
					logger.info(u"Size of disk '%s': %s Byte / %s MB" % ( self.device, self.size, (self.size/(1024*1024))) )
				
				elif line.startswith(self.device):
					match = re.search('(%sp*)(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\d+)[\+\-]*\s+(\S+)\s+(.*)' % self.device, line)
					if not match:
						raise Exception(u"Unable to read partition table of disk '%s'" % self.device)
					
					if match.group(5):
						boot = False
						if (match.group(3) == u'*'):
							boot = True
						
						fs = u'unknown'
						if (match.group(8).lower() in [u"b", u"c", u"e"]):
							fs = u'fat32'
						elif (match.group(8).lower() in [u"7"]):
							fs = u'ntfs'
						
						self.partitions.append( { 'device':	forceFilename(match.group(1) + match.group(2)),
									  'number':	forceInt(match.group(2)),
									  'cylStart':	forceInt(match.group(4)),
									  'cylEnd':	forceInt(match.group(5)),
									  'cylSize':	forceInt(match.group(6)),
									  'start':	forceInt(match.group(4)) * self.bytesPerCylinder,
									  'end':	forceInt(match.group(5)) * self.bytesPerCylinder,
									  'size':	forceInt(match.group(6)) * self.bytesPerCylinder,
									  'type':	forceUnicodeLower(match.group(8)),
									  'fs':		fs,
									  'boot': 	boot } )
						
						logger.debug(u"Partition found =>>> number: %s, start: %s MB (%s cyl), end: %s MB (%s cyl), size: %s MB (%s cyl), " \
								% (	self.partitions[-1]['number'],
									(self.partitions[-1]['start']/(1024*1024)), self.partitions[-1]['cylStart'],
									(self.partitions[-1]['end']/(1024*1024)),   self.partitions[-1]['cylEnd'],
									(self.partitions[-1]['size']/(1024*1024)),  self.partitions[-1]['cylSize'] ) \
								+ u"type: %s, fs: %s, boot: %s" \
								% (match.group(8), fs, boot) )
						
						if self.partitions[-1]['device']:
							logger.debug(u"Waiting for device '%s' to appear" % self.partitions[-1]['device'])
							timeout = 15
							while (timeout > 0):
								if os.path.exists(self.partitions[-1]['device']):
									break
								time.sleep(1)
								timeout -= 1
							if os.path.exists(self.partitions[-1]['device']):
								logger.debug(u"Device '%s' found" % self.partitions[-1]['device'])
							else:
								logger.warning(u"Device '%s' not found" % self.partitions[-1]['device'])
			# Get sector data
			result = execute(u"%s -uS -l %s" % (which('sfdisk'), self.device))
			for line in result:
				line = line.strip()
				if line.startswith(self.device):
					match = re.search('%sp*(\d+)\s+(\**)\s*(\d+)[\+\-]*\s+(\d*)[\+\-]*\s+(\d+)[\+\-]*\s+(\S+)\s+(.*)' % self.device, line)
					if not match:
						raise Exception(u"Unable to read partition table (sectors) of disk '%s'" % self.device)
					
					if match.group(4):
						for p in range(len(self.partitions)):
							if (forceInt(self.partitions[p]['number']) == forceInt(match.group(1))):
								self.partitions[p]['secStart'] = forceInt(match.group(3))
								self.partitions[p]['secEnd']   = forceInt(match.group(4))
								self.partitions[p]['secSize']  = forceInt(match.group(5))
								logger.debug(u"Partition sector values =>>> number: %s, start: %s sec, end: %s sec, size: %s sec " \
										% ( self.partitions[p]['number'], self.partitions[p]['secStart'],
										    self.partitions[p]['secEnd'], self.partitions[p]['secSize']) )
								break
			
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_readPartitionTable(self, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_readPartitionTable(self)
		
	def writePartitionTable(self):
		logger.debug(u"Writing partition table to disk %s" % self.device)
		for hook in hooks:
			hook.pre_Harddisk_writePartitionTable(self)
		try:
			cmd = u'%s -e "' % which('echo')
			for p in range(4):
				try:
					part = self.getPartition(p + 1)
					logger.debug(u"   number: %s, start: %s MB (%s cyl), end: %s MB (%s cyl), size: %s MB (%s cyl), " \
								% (	part['number'], 
									(part['start']/(1000*1000)), part['cylStart'], 
									(part['end']/(1000*1000)), part['cylEnd'], 
									(part['size']/(1000*1000)), part['cylSize'] ) \
								+ "type: %s, fs: %s, boot: %s" \
								% (part['type'], part['fs'], part['boot']) )
					
					cmd += u'%s,%s,%s' % (part['cylStart'], part['cylSize'], part['type'])
					if part['boot']:
						cmd += u',*'
				except Exception, e:
					logger.debug(u"Partition %d not found: %s" % ((p+1), e))
					cmd += u'0,0'
				
				cmd += u'\n'
				
			cmd +=  u'" | %s -D %s' % (which('sfdisk'), self.device)
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			execute(cmd)
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
			self._forceReReadPartionTable()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_writePartitionTable(self, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_writePartitionTable(self)
	
	def _forceReReadPartionTable(self):
		if self.ldPreload:
			os.putenv("LD_PRELOAD", self.ldPreload)
		logger.info(u"Forcing kernel to reread partition table of '%s'." % self.device)
		execute(u'%s --re-read %s' % (which('sfdisk'), self.device))
		if self.ldPreload:
			os.unsetenv("LD_PRELOAD")
		
	def deletePartitionTable(self):
		logger.info(u"Deleting partition table on '%s'" % self.device)
		for hook in hooks:
			hook.pre_Harddisk_deletePartitionTable(self)
		try:
			f = open(self.device, 'rb+')
			f.write(chr(0)*512)
			f.close()
			
			self._forceReReadPartionTable()
			self.label = None
			self.partitions = []
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_deletePartitionTable(self, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_deletePartitionTable(self)
		
	def shred(self, partition=0, iterations=25, progressSubject=None):
		for hook in hooks:
			(partition, iterations, progressSubject) = hook.pre_Harddisk_shred(self, partition, iterations, progressSubject)
		
		try:
			partition  = forceInt(partition)
			iterations = forceInt(iterations)
			
			dev = self.device
			if (partition != 0):
				dev = self.getPartition(partition)['device']
			
			cmd = u"%s -v -n %d %s 2>&1" % (which('shred'), iterations, dev)
			
			lineRegex = re.compile('\s(\d+)\/(\d+)\s\(([^\)]+)\)\.\.\.(.*)$')
			posRegex  = re.compile('([^\/]+)\/(\S+)\s+(\d+)%')
			handle    = execute(cmd, getHandle=True)
			position  = u''
			error     = u''
			if progressSubject:
				progressSubject.setEnd(100)
			while True:
				line = handle.readline().strip()
				logger.debug(u"From shred =>>> %s" % line)
				if not line:
					break
				'''
				shred: /dev/xyz: Pass 1/25 (random)...232MiB/512MiB 45%
				'''
				match = re.search(lineRegex, line)
				if match:
					iteration = forceInt(match.group(1))
					dataType  = match.group(3)
					logger.debug(u"Iteration: %d, data-type: %s" % (iteration, dataType))
					match = re.search(posRegex, match.group(4))
					if match:
						position = match.group(1) + '/' + match.group(2)
						percent = forceInt(match.group(3))
						logger.debug(u"Position: %s, percent: %d" % (position, percent))
						if progressSubject and (percent != progressSubject.getState()):
							progressSubject.setState(percent)
							progressSubject.setMessage(u"Pass %d/%d (%s), position: %s" \
									% (iteration, iterations, dataType, position))
				else:
					error = line
			
			ret = handle.close()
			logger.debug(u"Exit code: %s" % ret)
			
			
			if ret:
				raise Exception(u"Command '%s' failed: %s" % (cmd, error))
			
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_shred(self, partition, iterations, progressSubject, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_shred(self, partition, iterations, progressSubject)
		
		
	def zeroFill(self, partition=0, progressSubject=None):
		self.fill(forceInt(partition), u'/dev/zero', progressSubject)
	
	def randomFill(self, partition=0, progressSubject=None):
		self.fill(forceInt(partition), u'/dev/urandom', progressSubject)
	
	def fill(self, partition=0, infile=u'', progressSubject=None):
		for hook in hooks:
			(partition, infile, progressSubject) = hook.pre_Harddisk_fill(self, partition, infile, progressSubject)
		
		try:
			partition = forceInt(partition)
			if not infile:
				raise Exception(u"No input file given")
			infile = forceFilename(infile)
			
			xfermax = 0
			dev = self.device
			if (partition != 0):
				dev = self.getPartition(partition)['device']
				xfermax = int( round(float(self.getPartition(partition)['size'])/1024) )
			else:
				xfermax = int( round(float(self.size)/1024) )
			
			if progressSubject:
				progressSubject.setEnd(100)
			
			cmd = u"%s -m %sk %s %s 2>&1" % (which('dd_rescue'), xfermax, infile, dev)
			
			handle = execute(cmd, getHandle = True)
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
					if (inp.find(u'Summary') != -1):
						done = True
				
				elif (timeout >= 10):
					raise Exception(_(u"Failed (timed out)"))
				
				else:
					timeout += 1
					continue
				
				if (skip < 10):
					time.sleep(0.1)
					continue
				else:
					skip = 0
				
				if progressSubject:
					match = re.search('avg\.rate:\s+(\d+)kB/s', inp)
					if match:
						rate = match.group(1)
					match = re.search('ipos:\s+(\d+)\.\d+k', inp)
					if match:
						position = forceInt(match.group(1))
						percent  = (position*100)/xfermax
						logger.debug(u"Position: %s, xfermax: %s, percent: %s" % (position, xfermax, percent))
						if (percent != progressSubject.getState()):
							progressSubject.setState(percent)
							progressSubject.setMessage(u"Pos: %s MB, average transfer rate: %s kB/s" % (round((position)/1024), rate))
			
			if progressSubject:
				progressSubject.setState(100)
			time.sleep(3)
			if handle: handle.close
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_fill(self, partition, infile, progressSubject, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_fill(self, partition, infile, progressSubject)
		
	
	def readMasterBootRecord(self):
		for hook in hooks:
			hook.pre_Harddisk_readMasterBootRecord(self)
		mbr = None
		try:
			f = open(self.device, 'rb')
			mbr = f.read(512)
			f.close()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_readMasterBootRecord(self, e)
			raise
		
		for hook in hooks:
			mbr = hook.post_Harddisk_readMasterBootRecord(self, mbr)
		return mbr
		
	def writeMasterBootRecord(self, system=u'auto'):
		for hook in hooks:
			system = hook.pre_Harddisk_writeMasterBootRecord(self, system)
		
		try:
			system = forceUnicodeLower(system)
			mbrType = u'-w'
			if   system in (u'win2000', u'winxp', u'win2003', u'nt5'):
				mbrType = u'--mbr'
			elif system in (u'vista', u'win7', u'nt6'):
				mbrType = u'--mbrnt60'
			elif system in (u'win9x', u'win95', u'win98'):
				mbrType = u'--mbr95b'
			elif system in (u'dos', u'winnt'):
				mbrType = u'--mbrdos'
			
			logger.info(u"Writing master boot record on '%s' (system: %s)" % (self.device, system))
			
			cmd = u"%s %s %s" % (which('ms-sys'), mbrType, self.device)
			try:
				if self.ldPreload:
					os.putenv("LD_PRELOAD", self.ldPreload)
				result = execute(cmd)
				if self.ldPreload:
					os.unsetenv("LD_PRELOAD")
			except Exception, e:
				logger.error(u"Failed to write mbr: %s" % e)
				raise Exception(u"Failed to write mbr: %s" % e)
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_writeMasterBootRecord(self, system, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_writeMasterBootRecord(self, system)
		
	def readPartitionBootRecord(self, partition=1):
		for hook in hooks:
			partition = hook.pre_Harddisk_readPartitionBootRecord(self, partition)
		pbr = None
		try:
			f = open(self.getPartition(partition)['device'], 'rb')
			pbr = f.read(512)
			f.close()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_readPartitionBootRecord(self, partition, e)
			raise
		
		for hook in hooks:
			pbr = hook.post_Harddisk_readPartitionBootRecord(self, partition, pbr)
		return pbr
		
	def writePartitionBootRecord(self, partition=1, fsType=u'auto'):
		for hook in hooks:
			(partition, fsType) = hook.pre_Harddisk_writePartitionBootRecord(self, partition, fsType)
		try:
			partition = forceInt(partition)
			fsType = forceUnicodeLower(fsType)
			
			logger.info(u"Writing partition boot record on '%s' (fs-type: %s)" % (self.getPartition(partition)['device'], fsType))
			
			if (fsType == u'auto'):
				fsType = u'-w'
			else:
				fsType = u'--%s' % fsType
			
			cmd = u"%s -p %s %s" % (which('ms-sys'), fsType, self.getPartition(partition)['device'])
			try:
				if self.ldPreload:
					os.putenv("LD_PRELOAD", self.ldPreload)
				result = execute(cmd)
				if self.ldPreload:
					os.unsetenv("LD_PRELOAD")
				if (result[0].find(u'successfully') == -1):
					raise Exception(result)
				
			except Exception, e:
				logger.error(u"Cannot write partition boot record: %s" % e)
				raise Exception(u"Cannot write partition boot record: %s" % e)
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_writePartitionBootRecord(self, partition, fsType, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_writePartitionBootRecord(self, partition, fsType)
		
	def setNTFSPartitionStartSector(self, partition, sector=0):
		for hook in hooks:
			(partition, sector) = hook.pre_Harddisk_setNTFSPartitionStartSector(self, partition, sector)
		try:
			partition = forceInt(partition)
			sector = forceInt(sector)
			if not sector:
				sector = self.getPartition(partition)['secStart']
				if not sector:
					err = u"Failed to get partition start sector of partition '%s'" % (self.getPartition(partition)['device'])
					logger.error(err)
					raise Exception(err)
			
			logger.info(u"Setting Partition start sector to %s in NTFS boot record " % sector \
					+ u"on partition '%s'" % self.getPartition(partition)['device'] )
			
			x = [0, 0, 0, 0]
			x[0] = int ( (sector & 0x000000FFL) )
			x[1] = int ( (sector & 0x0000FF00L) >> 8 )
			x[2] = int ( (sector & 0x00FF0000L) >> 16 )
			x[3] = int ( (sector & 0xFFFFFFFFL) >> 24 )
			
			hd = posix.open(self.getPartition(partition)['device'], posix.O_RDONLY)
			posix.lseek(hd, 0x1c, 0)
			start = posix.read(hd, 4)
			logger.debug(u"NTFS Boot Record currently using %s %s %s %s as partition start sector" \
						% ( hex(ord(start[0])), hex(ord(start[1])), 
						    hex(ord(start[2])), hex(ord(start[3])) ) )
			posix.close(hd)
			
			logger.debug(u"Manipulating NTFS Boot Record!")
			hd = posix.open(self.getPartition(partition)['device'], posix.O_WRONLY)
			logger.info(u"Writing new value %s %s %s %s at 0x1c" % ( hex(x[0]), hex(x[1]), hex(x[2]), hex(x[3])))
			posix.lseek(hd, 0x1c, 0)
			for i in x:
				posix.write( hd, chr(i) )
			posix.close(hd)
			
			hd = posix.open(self.getPartition(partition)['device'], posix.O_RDONLY)
			posix.lseek(hd, 0x1c, 0)
			start = posix.read(hd, 4)
			logger.debug(u"NTFS Boot Record now using %s %s %s %s as partition start sector" \
						% ( hex(ord(start[0])), hex(ord(start[1])), 
						    hex(ord(start[2])), hex(ord(start[3])) ) )
			posix.close(hd)
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_setNTFSPartitionStartSector(self, partition, sector, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_setNTFSPartitionStartSector(self, partition, sector)
		
	def getPartitions(self):
		return self.partitions
	
	def getPartition(self, number):
		number = forceInt(number)
		for part in self.partitions:
			if (part['number'] == number):
				return part
		raise Exception(u'Partition %s does not exist' % number)
	
	def createPartition(self, start, end, fs, type = u'primary', boot = False, lba = False):
		for hook in hooks:
			(start, end, fs, type, boot, lba) = hook.pre_Harddisk_createPartition(self, start, end, fs, type, boot, lba)
		try:
			start = forceUnicodeLower(start)
			end   = forceUnicodeLower(end)
			fs    = forceUnicodeLower(fs)
			type  = forceUnicodeLower(type)
			boot  = forceBool(boot)
			lba   = forceBool(lba)
			
			partId = u'00'
			if re.search('^[a-f0-9]{2}$', fs):
				partId = fs
			else:
				if fs in (u'ext2', u'ext3', u'ext4', u'xfs', u'reiserfs', u'reiser4'):
					partId = u'83'
				elif (fs == u'linux-swap'):
					partId = u'82'
				elif (fs == u'fat32'):
					partId = u'c'
				elif (fs == u'ntfs'):
					partId = u'7'
				else:
					raise Exception("Filesystem '%s' not supported!" % fs)
			
			if (type != u'primary'):
				raise Exception("Type '%s' not supported!" % type)
			
			start = start.replace(u' ', u'')
			end   = end.replace(u' ', u'')
			
			if   start.endswith(u'm') or start.endswith(u'mb'):
				match = re.search('^(\d+)\D', start)
				start = int(round( (int(match.group(1))*1024*1024) / self.bytesPerCylinder ))
			elif start.endswith(u'g') or start.endswith(u'gb'):
				match = re.search('^(\d+)\D', start)
				start = int(round( (int(match.group(1))*1024*1024*1024) / self.bytesPerCylinder ))
			elif start.lower().endswith(u'%'):
				match = re.search('^(\d+)\D', start)
				start = int(round( (float(match.group(1))/100) * self.cylinders ))
			else:
				start = int(start)
			
			if   end.endswith(u'm') or end.endswith(u'mb'):
				match = re.search('^(\d+)\D', end)
				end = int(round( (int(match.group(1))*1024*1024) / self.bytesPerCylinder ))
			elif end.endswith(u'g') or end.endswith(u'gb'):
				match = re.search('^(\d+)\D', end)
				end = int(round( (int(match.group(1))*1024*1024*1024) / self.bytesPerCylinder ))
			elif end.lower().endswith(u'%'):
				match = re.search('^(\d+)\D', end)
				end = int(round( (float(match.group(1))/100) * self.cylinders ))
			else:
				end = int(end)
			
			if (start < 0):
				# Lowest possible cylinder is 0
				start = 0
			if (end >= self.cylinders):
				# Highest possible cylinder is total cylinders - 1
				end = self.cylinders-1
			
			number = len(self.partitions) + 1
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
			
			logger.info(u"Creating partition on '%s': number: %s, type '%s', filesystem '%s', start: %s cyl, end: %s cyl." \
						% (self.device, number, type, fs, start, end))
			
			if (number < 1) or (number > 4):
				raise Exception(u'Cannot create partition %s' % number)
			
			self.partitions.append( { 'number':	number,
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
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_createPartition(self, start, end, fs, type, boot, lba, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_createPartition(self, start, end, fs, type, boot, lba)
	
	
	def deletePartition(self, partition):
		for hook in hooks:
			partition = hook.pre_Harddisk_deletePartition(self, partition)
		try:
			partition = forceInt(partition)
			
			logger.info("Deleting partition '%s' on '%s'" % (partition, self.device))
			
			partitions = []
			exists = False
			deleteDev = None
			for part in self.partitions:
				if (part.get('number') == partition):
					exists = True
					deleteDev = part.get('device')
				else:
					partitions.append(part)
			
			if not exists:
				logger.warning(u"Cannot delete non existing partition '%s'." % partition)
				return
			
			self.partitions = partitions
			
			self.writePartitionTable()
			self.readPartitionTable()
			if deleteDev:
				logger.debug(u"Waiting for device '%s' to disappear" % deleteDev)
				timeout = 5
				while (timeout > 0):
					if not os.path.exists(deleteDev):
						break
					time.sleep(1)
					timeout -= 1
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_deletePartition(self, partition, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_deletePartition(self, partition)
		
	def mountPartition(self, partition, mountpoint, **options):
		for hook in hooks:
			(partition, mountpoint, options) = hook.pre_Harddisk_mountPartition(self, partition, mountpoint, **options)
		try:
			partition = forceInt(partition)
			mountpoint = forceFilename(mountpoint)
			mount(self.getPartition(partition)['device'], mountpoint, **options)
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_mountPartition(self, partition, mountpoint, e, **options)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_mountPartition(self, partition, mountpoint, **options)
	
	def umountPartition(self, partition):
		for hook in hooks:
			partition = hook.pre_Harddisk_umountPartition(self, partition)
		try:
			partition = forceInt(partition)
			umount(self.getPartition(partition)['device'])
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_umountPartition(self, partition, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_umountPartition(self, partition)
	
	def createFilesystem(self, partition, fs=None):
		for hook in hooks:
			(partition, fs) = hook.pre_Harddisk_createFilesystem(self, partition, fs)
		
		try:
			partition = forceInt(partition)
			if not fs:
				fs = self.getPartition(partition)['fs']
			fs = forceUnicodeLower(fs)
			
			if not fs in (u'fat32', u'ntfs', u'linux-swap', u'ext2', u'ext3', u'ext4', u'reiserfs', u'reiser4', u'xfs'):
				raise Exception(u"Creation of filesystem '%s' not supported!" % fs)
			
			logger.info(u"Creating filesystem '%s' on '%s'." % (fs, self.getPartition(partition)['device']))
			
			if   (fs == u'fat32'):
				cmd = u"mkfs.vfat -F 32 %s" % self.getPartition(partition)['device']
			elif (fs == u'linux-swap'):
				cmd = u"mkswap %s" % self.getPartition(partition)['device']
			else:
				options = u''
				if fs in (u'ext2', u'ext3', u'ext4', u'ntfs'):
					options = u'-F'
					if (fs == u'ntfs'):
						# quick format
						options += u' -Q'
				elif fs in (u'xfs', u'reiserfs', u'reiser4'):
					options = u'-f'
				cmd = u"mkfs.%s %s %s" % (fs, options, self.getPartition(partition)['device'])
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			execute(cmd)
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
			self.readPartitionTable()
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_createFilesystem(self, partition, fs, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_createFilesystem(self, partition, fs)
		
	def resizeFilesystem(self, partition, size=0, fs=None):
		for hook in hooks:
			(partition, size, fs) = hook.pre_Harddisk_resizeFilesystem(self, partition, size, fs)
		try:
			partition = forceInt(partition)
			size = forceInt(size)
			if not fs:
				fs = self.getPartition(partition)['fs']
			fs = forceUnicodeLower(fs)
			if not fs in (u'ntfs',):
				raise Exception(u"Resizing of filesystem '%s' not supported!" % fs)
			
			if (size <= 0):
				size = self.getPartition(partition)['size'] - 5*1024*1024
			
			if (size <= 0):
				raise Exception(u"New filesystem size of %0.2f MB is not possible!" % (float(size)/(1024*1024)))
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			if (fs.lower() == 'ntfs'):
				cmd = u"echo 'y' | %s --force --size %s %s" % (which('ntfsresize'), size, self.getPartition(partition)['device'])
				execute(cmd)
			
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_resizeFilesystem(self, partition, size, fs, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_resizeFilesystem(self, partition, size, fs)
			
	def saveImage(self, partition, imageFile, progressSubject=None):
		for hook in hooks:
			(partition, imageFile, progressSubject) = hook.pre_Harddisk_saveImage(self, partition, imageFile, progressSubject)
		
		try:
			partition = forceInt(partition)
			imageFile = forceUnicode(imageFile)
			
			imageType = None
			image = None
			
			part = self.getPartition(partition)
			if not part:
				raise Exception(u'Partition %s does not exist' % partition)
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			pipe = u''
			if imageFile.startswith(u'|'):
				pipe = imageFile
				imageFile = u'-'
			
			logger.info( u"Saving partition '%s' to partclone image '%s'" % (part['device'], imageFile) )
			
			# "-f" will write images of "dirty" volumes too
			# Better run chkdsk under windows before saving image!
			cmd = u'%s --rescue --clone --force --source %s --overwrite %s %s' % (which('partclone.' + part['fs']), part['device'], imageFile, pipe)
			
			if progressSubject:
				progressSubject.setEnd(100)
			
			handle = execute(cmd, getHandle = True)
			done = False
			
			timeout = 0
			buf = [u'']
			lastMsg = u''
			started = False
			while not done:
				inp = handle.read(128)
				
				if inp:
					inp = inp.decode("latin-1")
					timeout = 0
					
					b = inp.splitlines()
					if inp.endswith(u'\n') or inp.endswith(u'\r'):
						b.append(u'')
					
					buf = [ buf[-1] + b[0] ] + b[1:]
					
					for i in range( len(buf)-1 ):
						try:
							logger.debug(u" -->>> %s" % buf[i])
						except:
							pass
						if ( buf[i].find(u'Partclone fail') != -1 ):
							raise Exception(u"Failed: %s" % '\n'.join(buf))
						if ( buf[i].find(u'Partclone successfully') != -1 ):
							done = True
						if not started:
							if ( buf[i].find(u'Calculating bitmap') != -1 ):
								logger.info(u"Save image: Scanning filesystem")
								if progressSubject:
									progressSubject.setMessage(u"Scanning filesystem")
							elif ( buf[i].count(':') == 1 ) and (buf[i].find('http:') == -1):
								(k, v) = buf[i].split(':')
								k = k.strip()
								v = v.strip()
								logger.info(u"Save image: %s: %s" % (k, v))
								if progressSubject:
									progressSubject.setMessage(u"%s: %s" % (k, v))
								if (k.lower().find('used') != -1):
									if progressSubject:
										progressSubject.setMessage(u"Creating image")
									started = True
									continue
						else:
							match = re.search('Completed:\s*([\d\.]+)%', buf[i])
							if match:
								percent = int("%0.f" % float(match.group(1)))
								if progressSubject and (percent != progressSubject.getState()):
									logger.debug(u" -->>> %s" % buf[i])
									progressSubject.setState(percent)
					lastMsg = buf[-2]
					buf[:-1] = []
				
				elif (timeout >= 100):
					raise Exception(u"Failed: %s" % lastMsg)
				else:
					timeout += 1
					continue
			
			time.sleep(3)
			if handle: handle.close()
			
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_saveImage(self, partition, imageFile, progressSubject, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_saveImage(self, partition, imageFile, progressSubject)
		
	def restoreImage(self, partition, imageFile, progressSubject=None):
		for hook in hooks:
			(partition, imageFile, progressSubject) = hook.pre_Harddisk_restoreImage(self, partition, imageFile, progressSubject)
		
		try:
			partition = forceInt(partition)
			imageFile = forceUnicode(imageFile)
			
			imageType = None
			image = None
			
			pipe = u''
			if imageFile.endswith(u'|'):
				pipe = imageFile
				imageFile = u'-'
			
			try:
				head = u''
				if pipe:
					proc = subprocess.Popen(
						pipe[:-1] + u" 2>/dev/null",
						shell	= True,
						stdin	= subprocess.PIPE,
						stdout	= subprocess.PIPE,
						stderr	= None,
					)
					pid = proc.pid
					
					head = proc.stdout.read(128)
					logger.debug(u"Read 128 Bytes from pipe '%s': %s" % (pipe, head.decode('ascii', 'replace')))
					
					proc.stdout.close()
					proc.stdin.close()
					
					while( proc.poll() == None ):
						pids = os.listdir("/proc")
						for p in pids:
							if not os.path.exists( os.path.join("/proc", p, "status") ):
								continue
							f = open( os.path.join("/proc", p, "status") )
							for line in f.readlines():
								if line.startswith("PPid:"):
									ppid = line.split()[1].strip()
									if (ppid == str(pid)):
										logger.info(u"Killing process %s" % p)
										os.kill(int(p), SIGKILL)
										
						logger.info(u"Killing process %s" % pid)
						os.kill(pid, SIGKILL)
						time.sleep(1)
				else:
					image = open(imageFile, 'r')
					head = image.read(128)
					logger.debug(u"Read 128 Bytes from file '%s': %s" % (imageFile, head.decode('ascii', 'replace')))
					image.close()
				
				if   (head.find('ntfsclone-image') != -1):
					logger.notice(u"Image type is ntfsclone")
					imageType = u'ntfsclone'
				elif (head.find('partclone-image') != -1):
					logger.notice(u"Image type is partclone")
					imageType = u'partclone'
				
			except:
				if image:
					image.close()
				raise
			
			if imageType not in (u'ntfsclone', u'partclone'):
				raise Exception(u"Unknown image type.")
			
			if self.ldPreload:
				os.putenv("LD_PRELOAD", self.ldPreload)
			
			if (imageType == u'partclone'):
				logger.info(u"Restoring partclone image '%s' to '%s'" % \
								(imageFile, self.getPartition(partition)['device']) )
				
				cmd = u'%s %s --source %s --overwrite %s' % \
								(pipe, which('partclone.restore'), imageFile, self.getPartition(partition)['device'])
				
				if progressSubject:
					progressSubject.setEnd(100)
					progressSubject.setMessage(u"Scanning image")
					
				handle = execute(cmd, getHandle = True)
				done = False
				
				timeout = 0
				buf = [u'']
				lastMsg = u''
				started = False
				while not done:
					inp = handle.read(128)
					
					if inp:
						inp = inp.decode("latin-1")
						timeout = 0
						
						b = inp.splitlines()
						if inp.endswith(u'\n') or inp.endswith(u'\r'):
							b.append(u'')
						
						buf = [ buf[-1] + b[0] ] + b[1:]
						
						for i in range( len(buf)-1 ):
							try:
								logger.debug(u" -->>> %s" % buf[i])
							except:
								pass
							if ( buf[i].find(u'Partclone fail') != -1 ):
								raise Exception(u"Failed: %s" % '\n'.join(buf))
							if ( buf[i].find(u'Partclone successfully') != -1 ):
								done = True
							if not started:
								if ( buf[i].count(':') == 1 ) and (buf[i].find('http:') == -1):
									(k, v) = buf[i].split(':')
									k = k.strip()
									v = v.strip()
									logger.info(u"Save image: %s: %s" % (k, v))
									if progressSubject:
										progressSubject.setMessage(u"%s: %s" % (k, v))
									if (k.lower().find('used') != -1):
										if progressSubject:
											progressSubject.setMessage(u"Restoring image")
										started = True
										continue
							else:
								match = re.search('Completed:\s*([\d\.]+)%', buf[i])
								if match:
									percent = int("%0.f" % float(match.group(1)))
									if progressSubject and (percent != progressSubject.getState()):
										logger.debug(u" -->>> %s" % buf[i])
										progressSubject.setState(percent)
							
						lastMsg = buf[-2]
						buf[:-1] = []
					
					elif (timeout >= 100):
						if progressSubject:
							progressSubject.setMessage(u"Failed: %s" % lastMsg)
						raise Exception(u"Failed: %s" % lastMsg)
					else:
						timeout += 1
						continue
				
				time.sleep(3)
				if handle: handle.close()
			else:
				logger.info(u"Restoring ntfsclone-image '%s' to '%s'" % \
							(imageFile, self.getPartition(partition)['device']) )
			
				cmd = u'%s %s --restore-image --overwrite %s %s' % \
								(pipe, which('ntfsclone'), self.getPartition(partition)['device'], imageFile)
				
				if progressSubject:
					progressSubject.setEnd(100)
					progressSubject.setMessage(u"Restoring image")
					
				handle = execute(cmd, getHandle = True)
				done = False
				
				timeout = 0
				buf = [u'']
				lastMsg = u''
				while not done:
					inp = handle.read(128)
					
					if inp:
						inp = inp.decode("latin-1")
						timeout = 0
						
						b = inp.splitlines()
						if inp.endswith(u'\n') or inp.endswith(u'\r'):
							b.append(u'')
						
						buf = [ buf[-1] + b[0] ] + b[1:]
						
						for i in range( len(buf)-1 ):
							if ( buf[i].find('Syncing') != -1 ):
								logger.info(u"Restore image: Syncing")
								if progressSubject:
									progressSubject.setMessage(u"Syncing")
								done = True
							match = re.search('\s(\d+)[\.\,]\d\d\spercent', buf[i])
							if match:
								percent = int(match.group(1))
								if progressSubject and (percent != progressSubject.getState()):
									logger.debug(u" -->>> %s" % buf[i])
									progressSubject.setState(percent)
							else:
								logger.debug(u" -->>> %s" % buf[i])
							
						lastMsg = buf[-2]
						buf[:-1] = []
					
					elif (timeout >= 100):
						if progressSubject:
							progressSubject.setMessage(u"Failed: %s" % lastMsg)
						raise Exception(u"Failed: %s" % lastMsg)
					else:
						timeout += 1
						continue
				
				time.sleep(3)
				if handle: handle.close()
				
			if self.ldPreload:
				os.unsetenv("LD_PRELOAD")
			
			self.setNTFSPartitionStartSector(partition)
			if progressSubject:
				progressSubject.setMessage(u"Resizing filesystem to partition size")
			self.resizeFilesystem(partition, fs = u'ntfs')
			
		except Exception, e:
			for hook in hooks:
				hook.error_Harddisk_restoreImage(self, partition, imageFile, progressSubject, e)
			raise
		
		for hook in hooks:
			hook.post_Harddisk_restoreImage(self, partition, imageFile, progressSubject)
		


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# -                                       HARDWARE INVENTORY                                          -
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def auditHardware(config, hostId, progressSubject=None):
	for hook in hooks:
		(config, hostId, progressSubject) = hook.pre_auditHardware(config, hostId, progressSubject)
	
	try:
		hostId = forceHostId(hostId)
		
		AuditHardwareOnHost.setHardwareConfig(config)
		auditHardwareOnHosts = []
		
		info = hardwareInventory(config)
		for (hardwareClass, devices) in info.items():
			if (hardwareClass == 'SCANPROPERTIES'):
				continue
			for device in devices:
				data = { 'hardwareClass': hardwareClass }
				for (attribute, value) in device.items():
					data[str(attribute)] = value
				data['hostId'] = hostId
				auditHardwareOnHosts.append( AuditHardwareOnHost.fromHash(data) )
	except Exception, e:
		for hook in hooks:
			hook.error_auditHardware(config, hostId, progressSubject, e)
		raise
	
	for hook in hooks:
		auditHardwareOnHosts = hook.post_auditHardware(config, hostId, auditHardwareOnHosts)
	
	return auditHardwareOnHosts
	
def hardwareInventory(config, progressSubject=None):
	import xml.dom.minidom
	
	if not config:
		logger.error(u"hardwareInventory: no config given")
		return {}
	
	opsiValues = {}
	
	def getAttribute(dom, tagname, attrname):
		nodelist = dom.getElementsByTagName(tagname)
		if nodelist:
			return nodelist[0].getAttribute(attrname).strip()
		else:
			return u""
	
	def getElementsByAttributeValue(dom, tagName, attributeName, attributeValue):
		elements = []
		for element in dom.getElementsByTagName(tagName):
			if re.search(attributeValue , element.getAttribute(attributeName)):
				elements.append(element)
		return elements
	
	# Read output from lshw
	xmlOut = u'\n'.join(execute(u"%s -xml 2>/dev/null" % which("lshw"), captureStderr = False, encoding = None))
	xmlOut = re.sub('[%c%c%c%c%c%c%c%c%c%c%c%c%c]' % (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xbd, 0xbf, 0xef, 0xdd), u'.', xmlOut)
	dom = xml.dom.minidom.parseString( xmlOut.encode('utf-8') )
	
	# Read output from lspci
	lspci = {}
	busId = None
	devRegex = re.compile('([\d\.:a-f]+)\s+([\da-f]+):\s+([\da-f]+):([\da-f]+)\s*(\(rev ([^\)]+)\)|)')
	subRegex = re.compile('\s*Subsystem:\s+([\da-f]+):([\da-f]+)\s*')
	for line in execute(u"%s -vn" % which("lspci"), encoding = None):
		if not line.strip():
			continue
		match = re.search(devRegex, line)
		if match:
			busId = match.group(1)
			lspci[busId] = { 	'vendorId':		forceHardwareVendorId(match.group(3)),
						'deviceId':		forceHardwareDeviceId(match.group(4)),
						'subsystemVendorId':	'',
						'subsystemDeviceId':	'',
						'revision':		match.group(6) or '' }
			continue
		match = re.search(subRegex, line)
		if match:
			lspci[busId]['subsystemVendorId'] = forceHardwareVendorId(match.group(1))
			lspci[busId]['subsystemDeviceId'] = forceHardwareDeviceId(match.group(2))
	logger.debug2(u"Parsed lspci info:")
	logger.debug2(objectToBeautifiedText(lspci))
	
	# Read hdaudio information from alsa
	hdaudio = {}
	if os.path.exists('/proc/asound'):
		for card in os.listdir('/proc/asound'):
			if not re.search('^card\d$', card):
				continue
			logger.debug(u"Found hdaudio card '%s'" % card)
			for codec in os.listdir('/proc/asound/' + card):
				if not re.search('^codec#\d$', codec):
					continue
				if not os.path.isfile('/proc/asound/' + card + '/' + codec):
					continue
				f = open('/proc/asound/' + card + '/' + codec)
				logger.debug(u"   Found hdaudio codec '%s'" % codec)
				hdaudioId = card + codec
				hdaudio[hdaudioId] = {}
				for line in f.readlines():
					if   line.startswith(u'Codec:'):
						hdaudio[hdaudioId]['codec'] = line.split(':', 1)[1].strip()
					elif line.startswith(u'Address:'):
						hdaudio[hdaudioId]['address'] = line.split(':', 1)[1].strip()
					elif line.startswith(u'Vendor Id:'):
						vid = line.split('x', 1)[1].strip()
						hdaudio[hdaudioId]['vendorId'] = forceHardwareVendorId(vid[0:4])
						hdaudio[hdaudioId]['deviceId'] = forceHardwareDeviceId(vid[4:8])
					elif line.startswith(u'Subsystem Id:'):
						sid = line.split('x', 1)[1].strip()
						hdaudio[hdaudioId]['subsystemVendorId'] = forceHardwareVendorId(sid[0:4])
						hdaudio[hdaudioId]['subsystemDeviceId'] = forceHardwareDeviceId(sid[4:8])
					elif line.startswith(u'Revision Id:'):
						hdaudio[hdaudioId]['revision'] = line.split('x', 1)[1].strip()
				f.close()
				logger.debug(u"      Codec info: '%s'" % hdaudio[hdaudioId])
	
	# Read output from lsusb
	lsusb = {}
	busId = None
	devId = None
	indent = -1
	currentKey = None
	status = False
	
	devRegex             = re.compile('^Bus\s+(\d+)\s+Device\s+(\d+)\:\s+ID\s+([\da-fA-F]{4})\:([\da-fA-F]{4})\s*(.*)$')
	descriptorRegex      = re.compile('^(\s*)(.*)\s+Descriptor\:\s*$')
	deviceStatusRegex    = re.compile('^(\s*)Device\s+Status\:\s+(\S+)\s*$')
	deviceQualifierRegex = re.compile('^(\s*)Device\s+Qualifier\s+.*\:\s*$')
	keyRegex             = re.compile('^(\s*)([^\:]+)\:\s*$')
	keyValueRegex        = re.compile('^(\s*)(\S+)\s+(.*)$')
	
	try:
		for line in execute(u"%s -v" % which("lsusb")):
			if not line.strip() or (line.find(u'** UNAVAILABLE **') != -1):
				continue
			#line = line.decode('ISO-8859-15', 'replace').encode('utf-8', 'replace')
			match = re.search(devRegex, line)
			if match:
				busId = str(match.group(1))
				devId = str(match.group(2))
				descriptor = None
				indent = -1
				currentKey = None
				status = False
				logger.debug(u"Device: %s:%s" % (busId, devId))
				lsusb[ busId + ":" + devId] = {
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
				lsusb[busId + ":" + devId]['status'].append(line.strip())
				continue
			
			match = re.search(deviceStatusRegex, line)
			if match:
				status = True
				lsusb[busId + ":" + devId]['status'] = [ match.group(2) ]
				continue
			
			match = re.search(deviceQualifierRegex, line)
			if match:
				descriptor = 'qualifier'
				logger.debug(u"Qualifier")
				currentKey = None
				indent = -1
				continue
			
			match = re.search(descriptorRegex, line)
			if match:
				descriptor = match.group(2).strip().lower()
				logger.debug(u"Descriptor: %s" % descriptor)
				if type(lsusb[busId + ":" + devId][descriptor]) is list:
					lsusb[busId + ":" + devId][descriptor].append({})
				currentKey = None
				indent = -1
				continue
			
			if not descriptor:
				logger.error(u"No descriptor")
				continue
			
			if not lsusb[busId + ":" + devId].has_key(descriptor):
				logger.error(u"Unknown descriptor '%s'" % descriptor)
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
			
			logger.debug(u"key: '%s', value: '%s'" % (key, value))
			
			if not key or not value:
				continue
			
			currentKey = key
			if type(lsusb[busId + ":" + devId][descriptor]) is list:
				if not lsusb[busId + ":" + devId][descriptor][-1].has_key(key):
					lsusb[busId + ":" + devId][descriptor][-1][key] = [ ]
				lsusb[busId + ":" + devId][descriptor][-1][key].append(value)
			
			else:
				if not lsusb[busId + ":" + devId][descriptor].has_key(key):
					lsusb[busId + ":" + devId][descriptor][key] = [ ]
				lsusb[busId + ":" + devId][descriptor][key].append(value)
		
		logger.debug2(u"Parsed lsusb info:")
		logger.debug2(objectToBeautifiedText(lsusb))
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
			if line.startswith(u'Handle'):
				dmiType = None
				header = False
				option = None
				continue
			if header:
				continue
			if not dmiType:
				dmiType = line.strip()
				if (dmiType.lower() == u'end of table'):
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
			logger.error(u"Error while parsing dmidecode output '%s': %s" % (line.strip(), e))
	logger.debug2(u"Parsed dmidecode info:")
	logger.debug2(objectToBeautifiedText(dmidecode))
	
	# Build hw info structure
	for hwClass in config:
		
		if not hwClass.get('Class') or not hwClass['Class'].get('Opsi') or not hwClass['Class'].get('Linux'):
			continue
		
		opsiClass = hwClass['Class']['Opsi']
		linuxClass = hwClass['Class']['Linux']
		
		logger.debug(u"Processing class '%s' : '%s'" % (opsiClass, linuxClass))
		
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
				
				logger.debug(u"Class is '%s', id is '%s', filter is: %s" % (hwClass, hwid, filter))
				
				devs = getElementsByAttributeValue(dom, 'node', 'class', hwclass)
				for dev in devs:
					if dev.hasChildNodes():
						for child in dev.childNodes:
							if (child.nodeName == "businfo"):
								busInfo = child.firstChild.data.strip()
								if busInfo.startswith('pci@'):
									logger.debug(u"Getting pci bus info for '%s'" % busInfo)
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
					logger.debug2(u"Processing attribute '%s' : '%s'" % (attribute['Linux'], attribute['Opsi']) )
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
								logger.warning(u"Attribute part '%s' not found" % part)
								break
							elements = nextElements
						
						if not data:
							if not elements:
								opsiValues[opsiClass][i][attribute['Opsi']] = ''
								logger.warning(u"No data found for attribute '%s' : '%s'" % (attribute['Linux'], attribute['Opsi']))
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
								logger.debug(u"Eval: %s.%s" % (data, method))
								data = eval("data.%s" % method)
							except Exception, e:
								logger.error(u"Failed to excecute '%s.%s': %s" % (data, method, e))
						logger.debug2(u"Data: %s" % data)
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
									logger.debug(u"Eval: %s.%s" % (dev.get(aname, ''), method))
									device[attribute['Opsi']] = eval("dev.get(aname, '').%s" % method)
								except Exception, e:
									device[attribute['Opsi']] = u''
									logger.error(u"Failed to excecute '%s.%s': %s" % (dev.get(aname, ''), method, e))
							else:
								device[attribute['Opsi']] = dev.get(aname)
							if device[attribute['Opsi']]:
								break
					opsiValues[hwClass['Class']['Opsi']].append(device)
		
		# Get hw info from alsa hdaudio info
		elif linuxClass.startswith('[hdaudio]'):
			opsiValues[opsiClass] = []
			for (hdaudioId, dev) in hdaudio.items():
				device = {}
				for attribute in hwClass['Values']:
					if not attribute.get('Linux') or not dev.has_key(attribute['Linux']):
						continue
					try:
						device[attribute['Opsi']] = dev[attribute['Linux']]
					except Exception, e:
						logger.warning(e)
						device[attribute['Opsi']] = u''
				opsiValues[opsiClass].append(device)
		
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
								logger.error(u"Key '%s' not found" % key)
								value = u''
								break
							value = value[key]
							if type(value) is list:
								value = u', '.join(value)
							if method:
								value = eval("value.%s" % method)
							
						device[attribute['Opsi']] = value
					except Exception, e:
						logger.warning(e)
						device[attribute['Opsi']] = u''
				opsiValues[opsiClass].append(device)
	
	opsiValues['SCANPROPERTIES'] = [ { "scantime": time.strftime("%Y-%m-%d %H:%M:%S") } ]
	
	logger.debug(u"Result of hardware inventory:\n" + objectToBeautifiedText(opsiValues))
	
	return opsiValues


if (__name__ == "__main__"):
	print getBlockDeviceContollerInfo('/dev/sda')
	print getNetworkDeviceConfig(getDefaultNetworkInterfaceName())
	print getNetworkDeviceConfig('eth0')
	
