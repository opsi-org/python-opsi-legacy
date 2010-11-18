#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Repository    =
   = = = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2010 uib GmbH
   
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

__version__ = '4.0.1'

# Imports
import re, stat, base64, urllib, httplib, os, shutil, codecs, time, inspect

from OPSI.web2 import responsecode
from OPSI.web2.dav import davxml

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Util.Message import ProgressSubject
from OPSI.Util import md5sum, randomString
from OPSI.Util.File.Opsi import PackageContentFile
from OPSI.Util.HTTP import getSharedConnectionPool, urlsplit
from OPSI.System import *

# Get Logger instance
logger = Logger()

def _(string):
	return string

# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Repositories                                                                =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

def getRepository(url, **kwargs):
	if re.search('^file://', url, re.IGNORECASE):
		return FileRepository(url, **kwargs)
	if re.search('^https?://', url, re.IGNORECASE):
		return HTTPRepository(url, **kwargs)
	if re.search('^webdavs?://', url, re.IGNORECASE):
		return WebDAVRepository(url, **kwargs)
	if re.search('^(smb|cifs)://', url, re.IGNORECASE):
		return CIFSRepository(url, **kwargs)
	raise RepositoryError(u"Repository url '%s' not supported" % url)

class RepositoryHook(object):
	def __init__(self):
		pass
	
	def pre_Repository_copy(self, source, destination, overallProgressSubject, currentProgressSubject):
		return (source, destination, overallProgressSubject, currentProgressSubject)
	
	def post_Repository_copy(self, source, destination, overallProgressSubject, currentProgressSubject):
		return None
	
	def error_Repository_copy(self, source, destination, overallProgressSubject, currentProgressSubject, exception):
		pass
	
class Repository:
	def __init__(self, url, **kwargs):
		'''
		maxBandwith must be in byte/s
		'''
		self._url              = forceUnicode(url)
		self._maxBandwidth     = forceInt(kwargs.get('maxBandwidth', 0))
		self._dynamicBandwidth = forceBool(kwargs.get('dynamicBandwidth', False))
		self._path             = u''
		
		if (self._maxBandwidth < 0):
			self._maxBandwidth = 0
		
		self._dynamicBandwidthLimit = 0.0
		self._dynamicBandwidthLimitTime = None
		self._dynamicBandwidthNoLimitTime = None
		self._lastUnlimitedSpeed = 0.0
		self._bandwidthSleepTime = 0.0
		
		self._networkPerformanceCounter = None
		if self._dynamicBandwidth:
			from OPSI.System import getDefaultNetworkInterfaceName, NetworkPerformanceCounter
			self._networkPerformanceCounter = NetworkPerformanceCounter(getDefaultNetworkInterfaceName())
		self._hooks = []
		
	def __del__(self):
		if self._networkPerformanceCounter:
			try:
				self._networkPerformanceCounter.stop()
			except:
				pass
		
	def __unicode__(self):
		return u'<%s %s>' % (self.__class__.__name__, self._url)
	
	def __str__(self):
		return self.__unicode__().encode("ascii", "replace")
	
	def __repr__(self):
		return self.__str__()
	
	def addHook(self, hook):
		if not isinstance(hook, RepositoryHook):
			raise ValueError(u"Not a RepositoryHook: %s" % hook)
		if not hook in self._hooks:
			self._hooks.append(hook)
	
	def removeHook(self, hook):
		if not isinstance(hook, RepositoryHook):
			raise ValueError(u"Not a RepositoryHook: %s" % hook)
		if hook in self._hooks:
			self._hooks.remove(hook)
	
	def _sleepForBandwidth(self):
		bwlimit = 0.0
		
		if (self._averageSpeed == 0):
			return
		if not (self._dynamicBandwidth and self._networkPerformanceCounter) and not self._maxBandwidth:
			return
		
		if self._dynamicBandwidth and self._networkPerformanceCounter:
			now = time.time()
			networkUsage = 0
			if (self._transferDirection == 'out'):
				networkUsage = self._networkPerformanceCounter.getBytesOutPerSecond()
			else:
				networkUsage = self._networkPerformanceCounter.getBytesInPerSecond()
			
			if (networkUsage > 0):
				usage = float(self._currentSpeed)/float(networkUsage)
				logger.debug2("Current %0.2f kByte/s, average %0.2f kByte/s, total network usage %0.2f kByte/s, using %0.2f%% of total bandwidth" \
					% ((self._currentSpeed/1024), (self._averageSpeed/1024), (networkUsage/1024), usage*100))
				
				if self._dynamicBandwidthLimit:
					bwlimit = self._dynamicBandwidthLimit
					if (usage >= 0.90) or ((usage >= 0.70) and (self._lastUnlimitedSpeed/networkUsage > 2)):
						self._dynamicBandwidthLimitTime = None
						if self._dynamicBandwidthNoLimitTime:
							delta = (now - self._dynamicBandwidthNoLimitTime)
							if (delta >= 5):
								# Use 100%
								logger.info(u"No other traffic detected, resetting dynamically limited bandwidth, using 100%")
								bwlimit = self._dynamicBandwidthLimit = 0.0
								self._bandwidthSleepTime = 0
								self._lastUnlimitedSpeed = 0
						else:
							self._dynamicBandwidthNoLimitTime = now
					else:
						self._dynamicBandwidthNoLimitTime = None
				else:
					if (usage <= 0.90):
						self._dynamicBandwidthNoLimitTime = None
						if self._dynamicBandwidthLimitTime:
							delta = (now - self._dynamicBandwidthLimitTime)
							if (delta >= 1.0):
								# Use 5% only
								self._lastUnlimitedSpeed = self._averageSpeed
								bwlimit = self._dynamicBandwidthLimit = self._averageSpeed*0.05
								logger.info(u"Other traffic detected, dynamically limiting bandwidth to 5%% of last average to %0.2f kByte/s" \
									% (bwlimit/1024))
								# For faster limiting:
								self._bandwidthSleepTime = 0.1
						else:
							self._dynamicBandwidthLimitTime = now
					else:
						self._dynamicBandwidthLimitTime = None
		
		if self._maxBandwidth and ((bwlimit == 0) or (bwlimit > self._maxBandwidth)):
			bwlimit = float(self._maxBandwidth)
		
		if (bwlimit == 0):
			return
		
		if (self._averageSpeed > bwlimit):
			# To fast
			factor = float(self._averageSpeed)/float(bwlimit)
			logger.debug2(u"Transfer speed %0.2f kByte/s is to fast, limit: %0.2f kByte/s, factor: %0.5f" \
				% ((self._averageSpeed/1024), (bwlimit/1024), factor))
			self._bandwidthSleepTime += (0.003 * (factor*factor))
			
			if (self._bandwidthSleepTime <= 0.0):
				self._bandwidthSleepTime = 0.0001
			#elif (self._bandwidthSleepTime > 0.5):
			#	self._bandwidthSleepTime = 0.5
			elif (self._bandwidthSleepTime > 0.4):
				self._bandwidthSleepTime = 0.4
		else:
			# To slow
			factor = float(bwlimit)/float(self._averageSpeed)
			logger.debug2(u"Transfer speed %0.2f kByte/s is to slow, limit: %0.2f kByte/s, factor: %0.5f" \
				% ((self._averageSpeed/1024), (bwlimit/1024), factor))
			
			self._bandwidthSleepTime -= (0.001 * (factor*factor))
			if (self._bandwidthSleepTime <= 0.0):
				self._bandwidthSleepTime = 0
			
		if (self._bandwidthSleepTime > 0):
			logger.debug2(u"Sleeping %f seconds to correct bandwidth" % self._bandwidthSleepTime)
			time.sleep(self._bandwidthSleepTime)
	
	def _transferDown(self, src, dst, progressSubject=None, bytes=-1):
		self._transfer('in', src, dst, progressSubject, bytes=bytes)
		
	def _transferUp(self, src, dst, progressSubject=None):
		self._transfer('out', src, dst, progressSubject)
	
	
	def _transfer(self, transferDirection, src, dst, progressSubject=None, bytes=-1):
		self._transferDirection = transferDirection
		bytesTransfered = 0
		lastBytes = 0
		lastAverageBytes = 0
		lastTime = lastAverageTime = transferStartTime = time.time()
		buf = True
		if not hasattr(self, '_bufferSize'):
			self._bufferSize = 16384 #8192
		self._averageSpeed = 0.0
		self._currentSpeed = 0.0
		
		while buf and ( (bytes < 0) or (bytesTransfered < bytes) ):
			buf = src.read(self._bufferSize)
			read = len(buf)
			if (read > 0):
				if (bytes >= 0):
					if ((bytesTransfered + read) > bytes):
						buf = buf[:bytes-bytesTransfered]
						read = len(buf)
				lastAverageBytes += read
				lastBytes += read
				bytesTransfered += read
				if isinstance(dst, httplib.HTTPConnection) or isinstance(dst, httplib.HTTPSConnection):
					dst.send(buf)
				else:
					dst.write(buf)
				
				if progressSubject:
					progressSubject.addToState(read)
				
				now = time.time()
				
				delta = (now-lastTime)
				if (delta >= 1):
					self._currentSpeed = lastBytes/delta
					lastBytes = 0
					lastTime = now
				delta = (now-lastAverageTime)
				if (delta > 2):
					self._averageSpeed = lastAverageBytes/delta
					lastAverageTime = time.time() - 1
					lastAverageBytes = self._averageSpeed
					if (self._averageSpeed > 1000000):
						self._bufferSize = 131072
					
				if (bytesTransfered > self._bufferSize) and (self._maxBandwidth or self._dynamicBandwidth):
					self._sleepForBandwidth()
		
		transferTime = time.time() - transferStartTime
		if (transferTime == 0):
			transferTime = 0.0000001
		logger.info( u"Transfered %0.2f kByte in %0.2f minutes, average speed was %0.2f kByte/s" % \
			( (float(bytesTransfered)/1024), (float(transferTime)/60), (float(bytesTransfered)/transferTime)/1024) )
	
	def setMaxBandwidth(self, maxBandwidth):
		''' maxBandwidth in byte/s'''
		self._maxBandwidth = forceInt(maxBandwidth)
		if (self._maxBandwidth < 0):
			self._maxBandwidth = 0
	
	def _preProcessPath(self, path):
		return path
	
	def content(self, source='', recursive=False):
		raise RepositoryError(u"Not implemented")
	
	def listdir(self, source=''):
		result = []
		for c in self.content(source, recursive=False):
			result.append(c['name'])
		return result
	
	def getCountAndSize(self, source=''):
		source = forceUnicode(source)
		(count, size) = (0, 0)
		for entry in self.content(source, recursive = True):
			if (entry.get('type', '') == 'file'):
				count += 1
				size += entry.get('size', 0)
		return (count, size)
	
	def fileInfo(self, source):
		source = forceUnicode(source)
		info = {}
		try:
			parts = source.split('/')
			dirname = u'/'.join(parts[:-1])
			filename = parts[-1]
			if not filename:
				return {'name': dirname.split('/')[:-1], 'path': dirname.split('/')[:-1], 'type': 'dir', 'size': long(0)}
			for c in self.content(dirname):
				if (c['name'] == filename):
					info = c
					return info
			raise Exception(u'File not found')
		except Exception, e:
			#logger.logException(e)
			raise RepositoryError(u"Failed to get file info for '%s': %s" % (source, e))
		
	def exists(self, source):
		try:
			self.fileInfo(source)
		except:
			return False
		return True
	
	def islink(self, source):
		return False
	
	def isfile(self, source):
		try:
			info = self.fileInfo(source)
			return (info.get('type', '') == 'file')
		except:
			return False
	
	def isdir(self, source):
		try:
			info = self.fileInfo(source)
			return (info.get('type', '') == 'dir')
		except:
			return False
	
	def copy(self, source, destination, overallProgressSubject=None, currentProgressSubject=None):
		for hook in self._hooks:
			(source, destination, overallProgressSubject, currentProgressSubject) = hook.pre_Repository_copy(source, destination, overallProgressSubject, currentProgressSubject)
		
		'''
		source = file,  destination = file              => overwrite destination
		source = file,  destination = dir               => copy into destination
		source = file,  destination = not existent      => create destination directories, copy source to destination
		source = dir,   destination = file              => error
		source = dir,   destination = dir               => copy source dir into destination
		source = dir,   destination = not existent      => create destination, copy content of source into destination
		source = dir/*, destination = dir/not existent  => create destination if not exists, copy content of source into destination
		'''
		try:
			source = forceFilename(source)
			destination = forceFilename(destination)
			
			copySrcContent = False
			
			if source.endswith('/*.*') or source.endswith('\\*.*'):
				source = source[:-4]
				copySrcContent = True
				
			elif source.endswith('/*') or source.endswith('\\*'):
				source = source[:-2]
				copySrcContent = True
			
			if copySrcContent and not self.isdir(source):
				raise Exception(u"Source directory '%s' not found" % source)
			
			logger.info(u"Copying from '%s' to '%s'" % (source, destination))
			
			(totalFiles, size) = (0, 0)
			info = self.fileInfo(source)
			
			if overallProgressSubject:
				overallProgressSubject.reset()
				if (info.get('type') == 'file'):
					(totalFiles, size) = (1, info['size'])
				else:
					(totalFiles, size) = self.getCountAndSize(source)
				overallProgressSubject.setEnd(size)
			
			if (info.get('type') == 'file'):
				destinationFile = destination
				if not os.path.exists(destination):
					parent = os.path.dirname(destination)
					if not os.path.exists(parent):
						os.makedirs(parent)
				elif os.path.isdir(destination):
					destinationFile = os.path.join(destination, info['name'])
				
				if overallProgressSubject:
					sizeString = "%d Byte" % info['size']
					if (info['size'] > 1024*1024):
						sizeString = "%0.2f MByte" % ( float(info['size'])/(1024*1024) )
					elif (info['size'] > 1024):
						sizeString = "%0.2f kByte" % ( float(info['size'])/(1024) )
					overallProgressSubject.setMessage(u"[1/1] %s (%s)" % (info['name'], sizeString ) )
				try:
					self.download(source, destinationFile, currentProgressSubject)
				except OSError, e:
					if (e.errno != 1):
						raise
					# Operation not permitted
					logger.debug(e)
				if overallProgressSubject:
					overallProgressSubject.addToState(info['size'])
				
			elif (info.get('type') == 'dir'):
				if not os.path.exists(destination):
					os.makedirs(destination)
				elif os.path.isfile(destination):
					raise Exception(u"Cannot copy directory '%s' into file '%s'" % (source, destination))
				elif os.path.isdir(destination):
					if not copySrcContent:
						destination = os.path.join(destination, info['name'])
				content = self.content(source, recursive = True)
				fileCount = 0
				for c in content:
					if (c.get('type') == 'dir'):
						path = [ destination ]
						path.extend(c['path'].split('/'))
						targetDir = os.path.join(*path)
						if not targetDir:
							raise Exception(u"Bad target directory '%s'" % targetDir)
						if not os.path.isdir(targetDir):
							os.makedirs(targetDir)
					elif (c.get('type') == 'file'):
						fileCount += 1
						if overallProgressSubject:
							countLen = len(str(totalFiles))
							countLenFormat = '%' + str(countLen) + 's'
							sizeString = "%d Byte" % c['size']
							if (c['size'] > 1024*1024):
								sizeString = "%0.2f MByte" % ( float(c['size'])/(1024*1024) )
							elif (c['size'] > 1024):
								sizeString = "%0.2f kByte" % ( float(c['size'])/(1024) )
							overallProgressSubject.setMessage(u"[%s/%s] %s (%s)" \
									% (countLenFormat % fileCount, totalFiles, c['name'], sizeString ) )
						
						path = [ destination ]
						path.extend(c['path'].split('/')[:-1])
						targetDir = os.path.join(*path)
						if not targetDir:
							raise Exception(u"Bad target directory '%s'" % targetDir)
						if targetDir and not os.path.isdir(targetDir):
							os.makedirs(targetDir)
						self.download(u'/'.join((source, c['path'])), os.path.join(targetDir, c['name']), currentProgressSubject)
						
						if overallProgressSubject:
							overallProgressSubject.addToState(c['size'])
			else:
				raise Exception(u"Failed to copy: unknown source type '%s'" % source)
			logger.info(u'Copy done')
			if overallProgressSubject:
				overallProgressSubject.setState(size)
		except Exception, e:
			for hook in self._hooks:
				hook.error_Repository_copy(source, destination, overallProgressSubject, currentProgressSubject, e)
			raise
		
		for hook in self._hooks:
			hook.post_Repository_copy(source, destination, overallProgressSubject, currentProgressSubject)
	
	def upload(self, source, destination):
		raise RepositoryError(u"Not implemented")
	
	def download(self, source, destination, progressSubject=None, startByteNumber=-1, endByteNumber=-1):
		raise RepositoryError(u"Not implemented")
	
	def delete(self, destination):
		raise RepositoryError(u"Not implemented")
	
	def makeDirectory(self, destination):
		raise RepositoryError(u"Not implemented")
	
	def disconnect(self):
		raise RepositoryError(u"Not implemented")
	
	def __del__(self):
		try:
			self.disconnect()
		except:
			pass
	
class FileRepository(Repository):
	
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)
		
		match = re.search('^file://(/[^/]+.*)$', self._url, re.IGNORECASE)
		if not match:
			raise RepositoryError(u"Bad file url: '%s'" % self._url)
		self._path = match.group(1)
	
	def _preProcessPath(self, path):
		path = forceUnicode(path)
		if path.startswith('/'):
			path = path[1:]
		if path.endswith('/'):
			path = path[:-1]
		path = self._path + u'/' + path
		if (os.name == 'nt'):
			path = path.replace('/', '\\')
		return path
	
	def fileInfo(self, source):
		source = self._preProcessPath(source)
		try:
			info = {
				'name': os.path.basename(source),
				'path': source[len(self._path)+1:],
				'type': 'file',
				'size': long(0)
			}
			if not os.path.exists(source):
				raise Exception(u'File not found')
			if os.path.isdir(source):
				info['type'] = 'dir'
			if os.path.isfile(source):
				info['size'] = os.path.getsize(source)
			return info
		except Exception, e:
			#logger.logException(e)
			raise RepositoryError(u"Failed to get file info for '%s': %s" % (source, e))
	
	def exists(self, source):
		return os.path.exists(self._preProcessPath(source))
	
	def islink(self, source):
		return os.path.islink(self._preProcessPath(source))
		
	def isfile(self, source):
		return os.path.isfile(self._preProcessPath(source))
	
	def isdir(self, source):
		return os.path.isdir(self._preProcessPath(source))
	
	def content(self, source='', recursive=False):
		source = self._preProcessPath(source)
		
		content = []
		srcLen = len(source)
		def _recurse(path, content):
			path = os.path.abspath(forceFilename(path))
			for entry in os.listdir(path):
				try:
					info = { 'name': entry, 'size': long(0), 'type': 'file' }
					entry = os.path.join(path, entry)
					info['path'] = entry[srcLen:]
					size = 0
					if os.path.islink(entry):
						pass
					elif os.path.isfile(entry):
						info['size'] = os.path.getsize(entry)
						content.append(info)
					elif os.path.isdir(entry):
						info['type'] = 'dir'
						content.append(info)
						if recursive:
							_recurse(path = entry, content = content)
				except Exception, e:
					logger.error(e)
			return content
		return _recurse(path = source, content = content)
	
	def download(self, source, destination, progressSubject=None, startByteNumber=-1, endByteNumber=-1):
		'''
		startByteNumber: position of first byte to be read
		endByteNumber:   position of last byte to be read
		'''
		size = self.fileInfo(source)['size']
		source = self._preProcessPath(source)
		destination = forceUnicode(destination)
		startByteNumber = forceInt(startByteNumber)
		endByteNumber = forceInt(endByteNumber)
		
		if (endByteNumber > -1):
			size -= endByteNumber
		if (startByteNumber > -1):
			size -= startByteNumber
		
		logger.debug(u"Length of binary data to download: %d bytes" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			if (startByteNumber > -1):
				src.seek(startByteNumber)
			bytes = -1
			if (endByteNumber > -1):
				bytes = endByteNumber + 1
				if (startByteNumber > -1):
					bytes -= startByteNumber
			if (startByteNumber > 0) and os.path.exists(destination):
				dst = open(destination, 'ab')
			else:
				dst = open(destination, 'wb')
			self._transferDown(src, dst, progressSubject, bytes = bytes)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError(u"Failed to download '%s' to '%s': %s" \
						% (source, destination, e))
	
	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug(u"Length of binary data to upload: %d" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			dst = open(destination, 'wb')
			self._transferUp(src, dst, progressSubject)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError(u"Failed to upload '%s' to '%s': %s" \
						% (source, destination, e))
	
	def delete(self, destination):
		destination = self._preProcessPath(destination)
		os.unlink(destination)
	
	def makeDirectory(self, destination):
		destination = self._preProcessPath(destination)
		if not os.path.isdir(destination):
			os.mkdir(destination)
	
	def disconnect(self):
		pass

class HTTPRepository(Repository):
	
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)
		
		self._application = str(kwargs.get('application', 'opsi repository module version %s' % __version__))
		self._username = forceUnicode(kwargs.get('username', ''))
		self._password = forceUnicode(kwargs.get('password', ''))
		proxy = kwargs.get('proxy')
		
		self._port = 80
		self._path = u'/'
		self._socketTimeout = None
		self._connectTimeout = 30
		self._retryTime = 5
		self._connectionPoolSize = 1
		self._cookie = ''
		
		(scheme, host, port, baseurl, username, password) = urlsplit(self._url)
		
		if not scheme in ('http', 'https', 'webdav', 'webdavs'):
			raise RepositoryError(u"Bad http url: '%s'" % self._url)
		self._protocol = scheme
		if port:
			self._port = port
		elif self._protocol.endswith('s'):
			self._port = 443
		
		self._host = host
		self._path = baseurl
		if not self._username and username: self._username = username
		if not self._password and password: self._password = password
		self._username = forceUnicode(self._username)
		self._password = forceUnicode(self._password)
		if self._password:
			logger.addConfidentialString(self._password)
		
		auth = u'%s:%s' % (self._username, self._password)
		self._auth = 'Basic '+ base64.encodestring(auth.encode('latin-1')).strip()
		self._proxy = None
		
		if proxy:
			self._proxy = forceUnicode(proxy)
			self._auth = None
			match = re.search('^(https?)://([^:]+:*[^:]+):(\d+)$', proxy, re.IGNORECASE)
			if not match:
				raise RepositoryError(u"Bad proxy url: '%s'" % proxy)
			proxyProtocol = match.group(1)
			proxyHost = match.group(2)
			if (self._host.find('@') != -1):
				(proxyUsername, proxyHost) = proxyHost.split('@', 1)
				proxyPassword = ''
				if (proxyUsername.find(':') != -1):
					(proxyUsername, proxyPassword) = proxyUsername.split(':', 1)
				auth = u'%s:%s' % (proxyUsername, proxyPassword)
				self._auth = 'Basic '+ base64.encodestring(auth.encode('latin-1')).strip()
			proxyPort = forceInt(match.group(3))
			if self._username and self._password:
				self._url = u'%s://%s:%s@%s:%d%s' % (self._protocol, self._username, self._password, self._host, self._port, self._path)
			else:
				self._url = u'%s://%s:%d%s' % (self._protocol, self._host, self._port, self._path)
			self._protocol = proxyProtocol
			self._host = proxyHost
			self._port = proxyPort
		
		self._connectionPool = getSharedConnectionPool(
			scheme         = self._protocol,
			host           = self._host,
			port           = self._port,
			socketTimeout  = self._socketTimeout,
			connectTimeout = self._connectTimeout,
			retryTime      = self._retryTime,
			maxsize        = self._connectionPoolSize,
			block          = True
		)
		
	def _preProcessPath(self, path):
		path = forceUnicode(path)
		if path.startswith('/'):
			path = path[1:]
		if self._proxy:
			if self._url.endswith('/'):
				path = self._url + path
			else:
				path = self._url + u'/' + path
		else:
			path = self._path + u'/' + path
		if path.endswith('/'):
			path = path[:-1]
		return urllib.quote(path.encode('utf-8'))
	
	def _headers(self):
		headers = { 'user-agent': self._application }
		if self._cookie:
			headers['cookie'] = self._cookie
		if self._auth:
			headers['authorization'] = self._auth
		return headers
	
	def _processResponseHeaders(self, response):
		# Get cookie from header
		cookie = response.getheader('set-cookie', None)
		if cookie:
			# Store cookie
			self._cookie = cookie.split(';')[0].strip()
		
	def download(self, source, destination, progressSubject=None, startByteNumber=-1, endByteNumber=-1):
		'''
		startByteNumber: position of first byte to be read
		endByteNumber:   position of last byte to be read
		'''
		destination = forceUnicode(destination)
		startByteNumber = forceInt(startByteNumber)
		endByteNumber = forceInt(endByteNumber)
		source = self._preProcessPath(source)
		
		dst = None
		try:
			headers = self._headers()
			if (startByteNumber > -1) or (endByteNumber > -1):
				sbn = startByteNumber
				ebn = endByteNumber
				if (sbn <= -1):
					sbn = 0
				if (ebn <= -1):
					reb = ''
				headers['range'] = 'bytes=%s-%s' % (sbn, ebn)
			
			response = self._connectionPool.urlopen(method = 'GET', url = source, body = None, headers = headers, retry = True, redirect = True)
			self._processResponseHeaders(response)
			if response.status not in (responsecode.OK, responsecode.PARTIAL_CONTENT):
				raise Exception(response.status)
			
			size = forceInt(response.getheader('content-length', 0))
			logger.debug(u"Length of binary data to download: %d bytes" % size)
			
			if progressSubject: progressSubject.setEnd(size)
			
			if (startByteNumber > 0) and os.path.exists(destination):
				dst = open(destination, 'ab')
			else:
				dst = open(destination, 'wb')
			self._transferDown(response, dst, progressSubject)
			dst.close()
			
		except Exception, e:
			logger.logException(e)
			if dst: dst.close()
			raise RepositoryError(u"Failed to download '%s' to '%s': %s" % (source, destination, e))
		logger.debug2(u"HTTP download done")
	
	def disconnect(self):
		if self._connectionPool:
			self._connectionPool.free()
	
class WebDAVRepository(HTTPRepository):
	
	def __init__(self, url, **kwargs):
		HTTPRepository.__init__(self, url, **kwargs)
		parts = self._url.split('/')
		if (len(parts) < 3) or parts[0].lower() not in ('webdav:', 'webdavs:'):
			raise RepositoryError(u"Bad http url: '%s'" % self._url)
		self._contentCache = {}
		
	def _connect(self):
		HTTPRepository._connect(self)
		
		#self._connection.putrequest('PROPFIND', self._preProcessPath('/'))
		#self._connection.putheader('user-agent', self._application)
		#if self._cookie:
		#	# Add cookie to header
		#	self._connection.putheader('cookie', self._cookie)
		#if self._auth:
		#	self._connection.putheader('authorization', self._auth)
		#self._connection.putheader('depth', '0')
		#self._connection.endheaders()
		#
		#response = self._connection.getresponse()
		#if (response.status != responsecode.MULTI_STATUS):
		#	raise RepositoryError(u"Failed to connect to '%s://%s:%s': %s" \
		#		% (self._protocol, self._host, self._port, response.status))
		## We have to read the response!
		#response.read()
		#
		## Get cookie from header
		#cookie = response.getheader('set-cookie', None)
		#if cookie:
		#	# Store cookie
		#	self._cookie = cookie.split(';')[0].strip()
	
	def content(self, source='', recursive=False):
		source = forceUnicode(source)
		
		source = self._preProcessPath(source)
		if not source.endswith('/'):
			source += '/'
		
		if recursive and self._contentCache.has_key(source):
			if (time.time() - self._contentCache[source]['time'] > 60):
				del self._contentCache[source]
			else:
				return self._contentCache[source]['content']
		
		content = []
		
		headers = self._headers()
		depth = '1'
		if recursive:
			depth = 'infinity'
		headers['depth'] = depth
		
		response = self._connectionPool.urlopen(method = 'PROPFIND', url = source, body = None, headers = headers, retry = True, redirect = True)
		self._processResponseHeaders(response)
		if (response.status != responsecode.MULTI_STATUS):
			raise RepositoryError(u"Failed to list dir '%s': %s" % (source, response.status))
		
		encoding = 'utf-8'
		contentType = response.getheader('content-type', '').lower()
		for part in contentType.split(';'):
			if (part.find('charset=') != -1):
				encoding = part.split('=')[1].replace('"', '').strip()
		
		msr = davxml.WebDAVDocument.fromString(response.data)
		if not msr.root_element.children[0].childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer).childOfType(davxml.ResourceType).children:
			raise RepositoryError(u"Not a directory: '%s'" % source)
		
		srcLen = len(source)
		for child in msr.root_element.children[1:]:
			pContainer = child.childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer)
			info = { 'size': long(0), 'type': 'file' }
			info['path'] = unicode(urllib.unquote(child.childOfType(davxml.HRef).children[0].data), encoding)[srcLen:]
			info['name'] = unicode(pContainer.childOfType(davxml.DisplayName).children[0].data, encoding)
			if (str(pContainer.childOfType(davxml.GETContentLength)) != 'None'):
				info['size'] = long( str(pContainer.childOfType(davxml.GETContentLength)) )
			if pContainer.childOfType(davxml.ResourceType).children:
				info['type'] = 'dir'
				if info['path'].endswith('/'):
					info['path'] = info['path'][:-1]
			content.append(info)
		
		if recursive:
			self._contentCache[source] = {
				'time':    time.time(),
				'content': content
			}
		return content
	
	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)
		self._contentCache = {}
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug(u"Length of binary data to upload: %d" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		src = None
		conn = None
		response = None
		try:
			headers = self._headers()
			headers['content-length'] = size
			
			now = time.time()
			while True:
				conn = self._connectionPool.getConnection()
				conn.putrequest('PUT', destination)
				for (k, v) in headers.items():
					conn.putheader(k, v)
				conn.endheaders()
				conn.sock.settimeout(self._socketTimeout)
				
				try:
					src = open(source, 'rb')
					self._transferUp(src, conn, progressSubject)
				except Exception, e:
					src.close()
					if (time.time() - now > 3):
						raise
					logger.info(u"Error '%s' occured while uploading, retrying" % e)
					conn = None
					self._connectionPool.endConnection(conn)
					continue
				src.close()
				response = self._connectionPool.endConnection(conn)
				conn = None
				break
			
			self._processResponseHeaders(response)
			if (response.status != responsecode.CREATED) and (response.status != responsecode.NO_CONTENT):
				raise Exception(response.status)
			## Do we have to read the response?
			#response.read()
		except Exception, e:
			logger.logException(e)
			if src: src.close()
			if conn:
				self._connectionPool.endConnection(None)
			raise RepositoryError(u"Failed to upload '%s' to '%s': %s" % (source, destination, e))
		logger.debug2(u"WebDAV upload done")
	
	def delete(self, destination):
		destination = self._preProcessPath(destination)
		
		headers = self._headers()
		response = self._connectionPool.urlopen(method = 'DELETE', url = destination, body = None, headers = headers, retry = True, redirect = True)
		self._processResponseHeaders(response)
		if (response.status != responsecode.NO_CONTENT):
			raise RepositoryError(u"Failed to delete '%s': %s" % (destination, response.status))
		## Do we have to read the response?
		#response.read()

class CIFSRepository(FileRepository):
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)
		
		match = re.search('^(smb|cifs)://([^/]+/.+)$', self._url, re.IGNORECASE)
		if not match:
			raise RepositoryError(u"Bad smb/cifs url: '%s'" % self._url)
		
		if not os.name in ('posix', 'nt'):
			raise NotImplementedError(u"CIFSRepository not yet avaliable on os '%s'" % os.name)
		
		self._mounted = False
		self._mountPointCreated = False
		
		self._mountPoint = kwargs.get('mountPoint')
		if not self._mountPoint:
			if   (os.name == 'posix'):
				self._mountPoint = u'/tmp/.cifs-mount.%s' % randomString(5)
			elif (os.name == 'nt'):
				self._mountPoint = getFreeDrive(startLetter = 'g')
		
		self._username = forceUnicode(kwargs.get('username', 'guest'))
		self._password = forceUnicode(kwargs.get('password', ''))
		if self._password:
			logger.addConfidentialString(self._password)
		
		self._mountOptions = kwargs.get('mountOptions', {})
		
		self._path = self._mountPoint
		parts = match.group(2).split('/')
		if (len(parts) > 2):
			self._path += u'/' + u'/'.join(parts[2:])
		if self._path.endswith('/'):
			self._path = self._path[:-1]
		
		self._mount()
	
	def getMountPoint(self):
		return self._mountPoint
	
	def _mount(self):
		if self._mounted:
			self._umount()
		if not self._mountPoint:
			raise ValueError(u"Mount point not defined")
		
		logger.info(u"Mounting '%s' to '%s'" % (self._url, self._mountPoint))
		if (os.name == 'posix') and not os.path.isdir(self._mountPoint):
			os.makedirs(self._mountPoint)
			self._mountPointCreated = True
		try:
			mountOptions = self._mountOptions
			mountOptions['username'] = self._username
			mountOptions['password'] = self._password
			mount(self._url, self._mountPoint, **mountOptions)
			self._mounted = True
		except Exception, e:
			if self._mountPointCreated:
				try:
					os.rmdir(self._mountPoint)
				except Exception, e2:
					logger.error(e2)
			raise e
		
	def _umount(self):
		if not self._mounted or not self._mountPoint:
			return
		
		logger.info(u"Umounting '%s' from '%s'" % (self._url, self._mountPoint))
		
		umount(self._mountPoint)
		
		self._mounted = False
		if self._mountPointCreated:
			os.rmdir(self._mountPoint)
	
	def disconnect(self):
		self._umount()
	
class DepotToLocalDirectorySychronizer(object):
	def __init__(self, sourceDepot, destinationDirectory, productIds=[], maxBandwidth=0, dynamicBandwidth=False):
		self._sourceDepot          = sourceDepot
		self._destinationDirectory = forceUnicode(destinationDirectory)
		self._productIds           = forceUnicodeList(productIds)
		self._maxBandwidth         = forceInt(maxBandwidth)
		self._dynamicBandwidth     = forceBool(dynamicBandwidth)
		if not os.path.isdir(self._destinationDirectory):
			os.mkdir(self._destinationDirectory)
	
	def _synchronizeDirectories(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = forceUnicode(destination)
		logger.debug(u"Syncing directory %s to %s" % (source, destination))
		if not os.path.isdir(destination):
			os.mkdir(destination)
		
		for f in os.listdir(destination):
			relSource = (source + u'/' + f).split(u'/', 1)[1]
			if (relSource == self._productId + u'.files'):
				continue
			if self._fileInfo.has_key(relSource):
				continue
			
			logger.info(u"Deleting '%s'" % relSource)
			path = os.path.join(destination, f)
			if os.path.isdir(path) and not os.path.islink(path):
				shutil.rmtree(path)
			else:
				os.remove(path)
			
		for f in self._sourceDepot.content(source):
			source = forceUnicode(source)
			(s, d) = (source + u'/' + f['name'], os.path.join(destination, f['name']))
			relSource = s.split(u'/', 1)[1]
			if (relSource == self._productId + u'.files'):
				continue
			if not self._fileInfo.has_key(relSource):
				continue
			if (f['type'] == 'dir'):
				self._synchronizeDirectories(s, d, progressSubject)
			else:
				logger.debug(u"Syncing %s with %s %s" % (relSource, d, self._fileInfo[relSource]))
				if (self._fileInfo[relSource]['type'] == 'l'):
					self._linkFiles[relSource] = self._fileInfo[relSource]['target']
					continue
				size = 0
				localSize = 0
				exists = False
				if (self._fileInfo[relSource]['type'] == 'f'):
					size = int(self._fileInfo[relSource]['size'])
					exists = os.path.exists(d)
					if exists:
						md5s = md5sum(d)
						logger.debug(u"Destination file '%s' already exists (size: %s, md5sum: %s)" % (d, size, md5s))
						localSize = os.path.getsize(d)
						if (localSize == size) and (md5s == self._fileInfo[relSource]['md5sum']):
							#if progressSubject: progressSubject.addToState(size)
							continue
				
				if progressSubject: progressSubject.setMessage( _(u"Downloading file '%s'") % f['name'] )
				if exists and (localSize < size):
					partialEndFile = d + '.endpart'
					# First byte needed is byte number <localSize>
					logger.info(u"Downloading file '%s' starting at byte number %d" % (f['name'], localSize))
					if os.path.exists(partialEndFile):
						os.remove(partialEndFile)
					self._sourceDepot.download(s, partialEndFile, startByteNumber = localSize)
					(f1, f2) = (None, None)
					try:
						f1 = open(d, 'ab')
						f2 = open(partialEndFile, 'rb')
						f1.write(f2.read())
					finally:
						if f1: f1.close(); f1 = None
						if f2: f2.close(); f2 = None
					md5s = md5sum(d)
					if (md5s != self._fileInfo[relSource]['md5sum']):
						logger.warning(u"MD5sum of composed file differs")
						partialStartFile = d + '.startpart'
						if os.path.exists(partialStartFile):
							os.remove(partialStartFile)
						# Last byte needed is byte number <localSize> - 1
						logger.info(u"Downloading file '%s' ending at byte number %d" % (f['name'], localSize-1))
						self._sourceDepot.download(s, partialStartFile, endByteNumber = localSize-1)
						(f1, f2) = (None, None)
						try:
							f1 = open(partialStartFile, 'ab')
							f2 = open(partialEndFile, 'rb')
							f1.write(f2.read())
						finally:
							if f1: f1.close(); f1 = None
							if f2: f2.close(); f2 = None
						if os.path.exists(d):
							os.remove(d)
						os.rename(partialStartFile, d)
					os.remove(partialEndFile)
				else:
					logger.info(u"Downloading file '%s'" % f['name'])
					self._sourceDepot.download(s, d, progressSubject = progressSubject)
				md5s = md5sum(d)
				if (md5s != self._fileInfo[relSource]['md5sum']):
					raise Exception(u"Download error: MD5sum mismatch (%s != %s)" % (md5s, self._fileInfo[relSource]['md5sum']))
				#if progressSubject: progressSubject.addToState(size)
				
	def synchronize(self, productProgressObserver=None, overallProgressObserver=None):
		
		if not self._productIds:
			logger.info(u"Getting product dirs of depot '%s'" % self._sourceDepot)
			for c in self._sourceDepot.content():
				self._productIds.append(c['name'])
		
		overallProgressSubject = ProgressSubject(id = 'sync_products_overall', type = 'product_sync', end = len(self._productIds), fireAlways = True)
		overallProgressSubject.setMessage( _(u'Synchronizing products') )
		if overallProgressObserver: overallProgressSubject.attachObserver(overallProgressObserver)
		
		for self._productId in self._productIds:
			productProgressSubject = ProgressSubject(id = 'sync_product_' + self._productId, type = 'product_sync', fireAlways = True)
			productProgressSubject.setMessage( _(u"Synchronizing product %s") % self._productId )
			if productProgressObserver: productProgressSubject.attachObserver(productProgressObserver)
			packageContentFile = None
			
			try:
				self._linkFiles = {}
				logger.notice(u"Syncing product %s of depot %s with local directory %s" \
						% (self._productId, self._sourceDepot, self._destinationDirectory))
				
				productDestinationDirectory = os.path.join(self._destinationDirectory, self._productId)
				if not os.path.isdir(productDestinationDirectory):
					os.mkdir(productDestinationDirectory)
				
				logger.info(u"Downloading package content file")
				packageContentFile = os.path.join(productDestinationDirectory, u'%s.files' % self._productId)
				self._sourceDepot.download(u'%s/%s.files' % (self._productId, self._productId), packageContentFile)
				self._fileInfo = PackageContentFile(packageContentFile).parse()
				
				size = 0
				for value in self._fileInfo.values():
					if value.has_key('size'):
						size += int(value['size'])
				productProgressSubject.setMessage( _(u"Synchronizing product %s (%.2f kByte)") % (self._productId, (size/1024)) )
				productProgressSubject.setEnd(size)
				productProgressSubject.setEndChangable(False)
				
				self._synchronizeDirectories(self._productId, productDestinationDirectory, productProgressSubject)
				
				fs = self._linkFiles.keys()
				fs.sort()
				for f in fs:
					t = self._linkFiles[f]
					cwd = os.getcwd()
					os.chdir(productDestinationDirectory)
					try:
						if (os.name == 'nt'):
							if t.startswith('/'): t = t[1:]
							if f.startswith('/'): f = f[1:]
							t = os.path.join(productDestinationDirectory, t.replace('/', '\\'))
							f = os.path.join(productDestinationDirectory, f.replace('/', '\\'))
							if os.path.exists(f):
								if os.path.isdir(f):
									shutil.rmtree(f)
								else:
									os.remove(f)
							logger.info(u"Symlink => copying '%s' to '%s'" % (t, f))
							if os.path.isdir(t):
								shutil.copytree(t, f)
							else:
								shutil.copyfile(t, f)
						else:
							if os.path.exists(f):
								if os.path.isdir(f) and not os.path.islink(f):
									shutil.rmtree(f)
								else:
									os.remove(f)
							parts = len(f.split('/'))
							parts -= len(t.split('/'))
							for i in range(parts):
								t = os.path.join('..', t)
							logger.info(u"Symlink '%s' to '%s'" % (f, t))
							os.symlink(t, f)
					finally:
						os.chdir(cwd)
			except Exception, e:
				productProgressSubject.setMessage( _(u"Failed to sync product %s: %s") % (self._productId, e) )
				if packageContentFile and os.path.exists(packageContentFile):
					os.unlink(packageContentFile)
				raise
				
			overallProgressSubject.addToState(1)
			if productProgressObserver: productProgressSubject.detachObserver(productProgressObserver)
			
		if overallProgressObserver: overallProgressSubject.detachObserver(overallProgressObserver)




#class ProductSynchronizer(object):
#	def __init__(self, configService, depotId, destinationDirectory, productIds=[], maxBandwidth=0, dynamicBandwidth=False):
#		self._configService        = configService
#		self._depotId              = depotId
#		self._destinationDirectory = destinationDirectory
#		self._productIds           = productIds
#		self._maxBandwidth         = maxBandwidth
#		self._dynamicBandwidth     = dynamicBandwidth
#	
#	def synchronize(self):
#		try:
#			depot = self._configService.host_getObjects(id = self._depotId)[0]
#		except Exception, e:
#			raise Exception(u"Failed to get info for depot '%s': %s" % (self._depotId, e))
#		depot.depotWebdavUrl
#		
#		for productId in self._productIds:
#			logger.notice(u"Syncing product %s from depot %s to local directory %s" \
#						% (productId, self._sourceDepot, self._destinationDirectory))
#				
#			productDestinationDirectory = os.path.join(self._destinationDirectory, productId)
#			if not os.path.isdir(productDestinationDirectory):
#				os.mkdir(productDestinationDirectory)
#			
#			logger.info(u"Downloading package content file")
#			packageContentFile = os.path.join(productDestinationDirectory, u'%s.files' % self._productId)
#			self._sourceDepot.download(u'%s/%s.files' % (self._productId, self._productId), packageContentFile)
#			self._fileInfo = PackageContentFile(packageContentFile).parse()
#			
#			bytes = 0
#			for value in self._fileInfo.values():
#				if value.has_key('size'):
#					bytes += int(value['size'])
#			productProgressSubject.setMessage( _(u"Synchronizing product %s (%.2f kByte)") % (self._productId, (bytes/1024)) )
#			productProgressSubject.setEnd(bytes)
				


#class OpsiDepot(object):
#	def __init__(self, serviceUrl, depotId, username, password):
#		from OPSI.Backend.JSONRPC import JSONRPCBackend
#		
#		self._configService = JSONRPCBackend(address = serviceUrl, username = username, password = password, connectOnInit = True)
#		self._depotId = depotId
#		try:
#			self._depot = self._configService.host_getObjects(id = self._depotId)[0]
#			self._depotLocalDir = self._depot.depotLocalUrl.replace('file://', '')
#		except Exception, e:
#			raise Exception(u"Failed to get info for depot '%s': %s" % (self._depotId, e))
#		self._repository = getRepository(url = self._depot.depotWebdavUrl, username = username, password = password)
#		
#	def __getattr__(self, name):
#		if hasattr(self._repository, name):
#			return getattr(self._repository, name)
#		return self.__dict__[name]
#	
#	def download(self, source, destination, progressSubject=None, rangeStart=-1, rangeEnd=-1):
#		if os.path.exists(destination):
#			depotLocalFile = self._depotLocalDir + source
#			print self._configService.depot_librsyncSignature(depotLocalFile)
#		else:
#			return self._repository.download(source = source, destination = destination, progressSubject = progressSubject, rangeStart = rangeStart)
#		

if (__name__ == "__main__"):
	#logger.setConsoleLevel(LOG_DEBUG2)
	logger.setConsoleLevel(LOG_INFO)
	logger.setConsoleColor(True)
	
	tempDir = '/tmp/testdir'
	#if os.path.exists(tempDir):
	#	shutil.rmtree(tempDir)
	if not os.path.exists(tempDir):
		os.mkdir(tempDir)
	
	##rep = HTTPRepository(url = u'webdav://download.uib.de:80/opsi4.0', dynamicBandwidth = True)
	##rep.download(u'opsi3.4-client-boot-cd_20091028.iso', '/tmp/opsi3.4-client-boot-cd_20091028.iso', progressSubject=None)
	#sourceDepot = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'stb-40-wks-101.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#dtlds = DepotToLocalDirectorySychronizer(sourceDepot, destinationDirectory = tempDir, productIds=['opsi-client-agent', 'opsi-winst', 'thunderbird'], maxBandwidth=0, dynamicBandwidth=False)
	#dtlds.synchronize()
	
	#sourceDepot = getRepository(url = u'cifs://bonifax/opt_pcbin/install', username = u'pcpatch', password = u'xxxxxx', mountOptions = { "iocharset": 'iso8859-1' })
	#dtlds = DepotToLocalDirectorySychronizer(sourceDepot, destinationDirectory = tempDir, productIds=['opsi-client-agent', 'opsi-winst', 'thunderbird'], maxBandwidth=0, dynamicBandwidth=False)
	#dtlds.synchronize()
	
	#print rep.listdir()
	#print rep.isdir('javavm')
	
	rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'stb-40-wks-101.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	print rep.listdir()
	rep.disconnect()
	
	#destination = os.path.join(tempDir, 'AdbeRdr930_de_DE.msi')
	#rep.download('/acroread9/files/AdbeRdr930_de_DE.msi', destination, endByteNumber = 20000000)
	#rep.download('/acroread9/files/AdbeRdr930_de_DE.msi', destination, startByteNumber = 20000001)
	
	#rep = getRepository(url = u'cifs://bonifax/opt_pcbin/install', username = u'', password = u'', mountOptions = { "iocharset": 'iso8859-1' })
	#print rep.listdir()
	#print rep.isdir('javavm')
	#
	#sys.exit(0)
	tempFile = '/tmp/testfile.bin'
	#tempDir = '/tmp/testdir'
	#tempDir2 = '/tmp/testdir2'
	#if os.path.exists(tempFile):
	#	os.unlink(tempFile)
	#if os.path.exists(tempDir):
	#	shutil.rmtree(tempDir)
	#if os.path.exists(tempDir2):
	#	shutil.rmtree(tempDir2)
	
	#rep = HTTPRepository(url = u'http://download.uib.de:80', username = u'', password = u'')
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	
	#rep = HTTPRepository(url = u'http://download.uib.de', username = u'', password = u'')
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'http://download.uib.de:80', username = u'', password = u'', proxy="http://192.168.1.254:3128")
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'http://download.uib.de', username = u'', password = u'', proxy="http://192.168.1.254:3128")
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'https://forum.opsi.org:443', username = u'', password = u'')
	#rep.download(u'/index.php', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/repository', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#rep.download(u'xpconfig_2.6-1.opsi', tempFile, progressSubject=None)
	#for c in rep.content():
	#	print c
	#print rep.getCountAndSize()
	#print rep.exists('shutdownwanted_1.0-2.opsi')
	#print rep.exists('notthere')
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#shutil.rmtree(tempDir)
	#os.makedirs(tempDir)
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#
	#shutil.rmtree(tempDir)
	
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('winvista-x64/installfiles', recursive=True):
	#	print c
	#rep.copy(source = 'winvista-x64/installfiles', destination = tempDir)
	
	#from UI import UIFactory
	#ui = UIFactory()
	#from Message import ProgressObserver
	#overallProgressSubject = ProgressSubject(id = u'copy_overall', title = u'Copy test')
	#currentProgressSubject = ProgressSubject(id = u'copy_current', title = u'Copy test')
	##class SimpleProgressObserver(ProgressObserver):
	##	def messageChanged(self, subject, message):
	##		print u"%s" % message
	##	
	##	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
	##		print u"state: %s, percent: %0.2f%%, timeSpend: %0.2fs, timeLeft: %0.2fs, speed: %0.2f" \
	##			% (state, percent, timeSpend, timeLeft, speed)
	##progressSubject.attachObserver(SimpleProgressObserver())
	##copyBox = ui.createCopyProgressBox(width = 120, height = 20, title = u'Copy', text = u'')
	#copyBox = ui.createCopyDualProgressBox(width = 120, height = 20, title = u'Copy', text = u'')
	#copyBox.show()
	#copyBox.setOverallProgressSubject(overallProgressSubject)
	#copyBox.setCurrentProgressSubject(currentProgressSubject)
	
	#progressSubject.attachObserver(copyBox)
	
	#overallProgressSubject = None
	#currentProgressSubject = None
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('swaudit', recursive=True):
	#	print c
	
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot/swaudit', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('swaudit', recursive=True):
	#	print c
	#print rep.listdir()
	#rep.copy(source = '/*', destination = tempDir, overallProgressSubject = overallProgressSubject, currentProgressSubject = currentProgressSubject)
	
	#time.sleep(1)
	
	#overallProgressSubject.reset()
	#currentProgressSubject.reset()
	#rep = FileRepository(url = u'file://%s' % tempDir)
	#for c in rep.content('', recursive=True):
	#	print c
	#print rep.exists('/MSVCR71.dll')
	#print rep.isdir('lib')
	#print rep.isfile('äää.txt')
	#print rep.listdir()
	#rep.copy(source = '/*', destination = tempDir2, overallProgressSubject = overallProgressSubject, currentProgressSubject = currentProgressSubject)
	
	#rep = FileRepository(url = u'file:///usr')
	#print rep.fileInfo('')
	#for f in rep.listdir('src'):
	#	print rep.fileInfo('src' + '/' + f)
	
	#ui.exit()
	#rep = FileRepository(url = u'file:///tmp')
	#for c in rep.content('', recursive=True):
	#	print c
	
	






















