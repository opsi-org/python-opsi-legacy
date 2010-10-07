#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Logger    =
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

# Loglevels
LOG_CONFIDENTIAL = 9
LOG_DEBUG2       = 8
LOG_DEBUG        = 7
LOG_INFO         = 6
LOG_NOTICE       = 5
LOG_WARNING      = 4
LOG_ERROR        = 3
LOG_CRITICAL     = 2
LOG_ESSENTIAL    = 1
LOG_COMMENT      = LOG_ESSENTIAL
LOG_NONE         = 0

# Imports
import sys, locale, time, os, thread, threading, codecs, types

if (os.name == 'nt'):
	# Windows imports for file locking
	import win32con, win32file, pywintypes
	
	# Colors
	COLOR_NORMAL        = ''
	COLOR_BLACK         = ''
	COLOR_RED           = ''
	COLOR_GREEN         = ''
	COLOR_YELLOW        = ''
	COLOR_BLUE          = ''
	COLOR_MAGENTA       = ''
	COLOR_CYAN          = ''
	COLOR_WHITE         = ''
	COLOR_LIGHT_BLACK   = ''
	COLOR_LIGHT_RED     = ''
	COLOR_LIGHT_GREEN   = ''
	COLOR_LIGHT_YELLOW  = ''
	COLOR_LIGHT_BLUE    = ''
	COLOR_LIGHT_MAGENTA = ''
	COLOR_LIGHT_CYAN    = ''
	COLOR_LIGHT_WHITE   = ''

elif (os.name == 'posix'):
	# Posix imports for file locking
	import fcntl
	
	# Colors
	COLOR_NORMAL        = '\033[0;0;0m'
	COLOR_BLACK         = '\033[0;30;40m'
	COLOR_RED           = '\033[0;31;40m'
	COLOR_GREEN         = '\033[0;32;40m'
	COLOR_YELLOW        = '\033[0;33;40m'
	COLOR_BLUE          = '\033[0;34;40m'
	COLOR_MAGENTA       = '\033[0;35;40m'
	COLOR_CYAN          = '\033[0;36;40m'
	COLOR_WHITE         = '\033[0;37;40m'
	COLOR_LIGHT_BLACK   = '\033[1;30;40m'
	COLOR_LIGHT_RED     = '\033[1;31;40m'
	COLOR_LIGHT_GREEN   = '\033[1;32;40m'
	COLOR_LIGHT_YELLOW  = '\033[1;33;40m'
	COLOR_LIGHT_BLUE    = '\033[1;34;40m'
	COLOR_LIGHT_MAGENTA = '\033[1;35;40m'
	COLOR_LIGHT_CYAN    = '\033[1;36;40m'
	COLOR_LIGHT_WHITE   = '\033[1;37;40m'
	
COLORS_AVAILABLE = [ 	COLOR_NORMAL, COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW,
			COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE, COLOR_LIGHT_BLACK,
			COLOR_LIGHT_RED, COLOR_LIGHT_GREEN, COLOR_LIGHT_YELLOW, COLOR_LIGHT_BLUE,
			COLOR_LIGHT_MAGENTA, COLOR_LIGHT_CYAN, COLOR_LIGHT_WHITE ]

DEBUG_COLOR        = COLOR_WHITE
INFO_COLOR         = COLOR_LIGHT_WHITE
NOTICE_COLOR       = COLOR_GREEN
WARNING_COLOR      = COLOR_YELLOW
ERROR_COLOR        = COLOR_RED
CRITICAL_COLOR     = COLOR_LIGHT_RED
CONFIDENTIAL_COLOR = COLOR_LIGHT_YELLOW
ESSENTIAL_COLOR    = COLOR_LIGHT_CYAN
COMMENT_COLOR      = ESSENTIAL_COLOR

encoding = sys.getfilesystemencoding()
def forceUnicode(var):
	if type(var) is types.UnicodeType:
		return var
	if type(var) is types.StringType:
		return unicode(var, 'utf-8', 'replace')
	if (os.name == 'nt') and type(var) is WindowsError:
		return u"[Error %s] %s" % (var.args[0], var.args[1].decode(encoding))
	if hasattr(var, '__unicode__'):
		try:
			return var.__unicode__()
		except:
			pass
	try:
		return unicode(var)
	except:
		pass
	if hasattr(var, '__repr__'):
		var = var.__repr__()
		if type(var) is types.UnicodeType:
			return var
		return unicode(var, 'utf-8', 'replace')
	return unicode(var)
	
class LoggerSubject:
	def __init__(self):
		self._observers = []
		self._message = u""
		self._severity = 0
	
	def getId(self):
		return u'logger'
	
	def getType(self):
		return u'Logger'
	
	def getClass(self):
		return u'MessageSubject'
	
	def setMessage(self, message, severity = 0):
		self._message = forceUnicode(message)
		self._severity = severity
		for o in self._observers:
			o.messageChanged(self, message)
	
	def getMessage(self):
		return self._message
	
	def getSeverity(self):
		return self._severity
	
	def attachObserver(self, observer):
		if not observer in self._observers:
			self._observers.append(observer)
	
	def detachObserver(self, observer):
		if observer in self._observers:
			self._observers.remove(observer)
	
	def serializable(self):
		return { "message": self.getMessage(), "severity": self.getSeverity(), "id": self.getId(), "class": self.getClass(), "type": self.getType() }
	
'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                   CLASS LOGGERIMPLEMENTATION                                       =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class LoggerImplementation:
	''' Implementation of the singleton interface '''
	
	def __init__(self, logFile = None):
		self.__syslogLevel = LOG_NONE
		self.__consoleLevel = LOG_NONE
		self.__fileLevel = LOG_NONE
		self.__messageSubjectLevel = LOG_NONE
		self.__fileColor = False
		self.__consoleColor = False
		self.__logFile = logFile
		self.__syslogFormat = u'%M'
		self.__consoleFormat = u'%M'
		self.__consoleStdout = False
		self.__fileFormat = u'%D [%L] %M (%F|%N)'
		self.__messageSubjectFormat = u'%M'
		self.univentionLogger_priv = None
		self.__univentionClass = None
		self.__univentionFormat = u'opsi: %M'
		self.__confidentialStrings = []
		self.__componentName = u''
		self.__threadConfig = {}
		self.__objectConfig = {}
		self.__stdout = VirtFile(self, LOG_NOTICE)
		self.__stderr = VirtFile(self, LOG_ERROR)
		self.__lock = threading.Lock()
		self.__loggerSubject = LoggerSubject()
		
	def getStderr(self):
		return self.__stderr
	
	def getStdout(self):
		return self.__stdout
	
	def setConfidentialStrings(self, strings):
		if not type(strings) in (list, tuple):
			strings = [ strings ]
		self.__confidentialStrings = []
		for string in strings:
			self.addConfidentialString(string)
	
	def addConfidentialString(self, string):
		string = forceUnicode(string)
		if not string:
			raise ValueError(u"Cannot use empty string as confidential string")
		if string in self.__confidentialStrings:
			return
		self.__confidentialStrings.append(string)
	
	def setLogFormat(self, format, currentThread=False, object=None):
		self.setConsoleFormat(format, currentThread, object)
		self.setSyslogFormat(format, currentThread, object)
		self.setFileFormat(format, currentThread, object)
		
	def setConsoleFormat(self, format, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('consoleFormat', format)
		elif object:
			self._setObjectConfig(id(object), 'consoleFormat', format)
		else:
			self.__consoleFormat = format
	
	def setComponentName(self, componentName, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('componentName', componentName)
		elif object:
			self._setObjectConfig(id(object), 'componentName', componentName)
		else:
			self.__componentName = componentName
	
	def logToStdout(self, stdout):
		self.__consoleStdout = stdout
	
	def setSyslogFormat(self, format, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('syslogFormat', format)
		elif object:
			self._setObjectConfig(id(object), 'syslogFormat', format)
		else:
			self.__syslogFormat = format
		
	def setFileFormat(self, format, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('fileFormat', format)
		elif object:
			self._setObjectConfig(id(object), 'fileFormat', format)
		else:
			self.__fileFormat = format
	
	def setUniventionFormat(self, format, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('univentionFormat', format)
		elif object:
			self._setObjectConfig(id(object), 'univentionFormat', format)
		else:
			self.__univentionFormat = format
	
	def setMessageSubjectFormat(self, format, currentThread=False, object=None):
		if currentThread:
			self._setThreadConfig('messageSubjectFormat', format)
		elif object:
			self._setObjectConfig(id(object), 'messageSubjectFormat', format)
		else:
			self.__messageSubjectFormat = format
		
	def setUniventionLogger(self, logger):
		self.univentionLogger_priv = logger
	
	def setUniventionClass(self, c):
		self.__univentionClass = c
	
	def getMessageSubject(self):
		return self.__loggerSubject
	
	def setColor(self, color):
		''' Enable or disable ansi color output '''
		self.__fileColor = self.__consoleColor = color
	
	def setFileColor(self, color):
		''' Enable or disable ansi color output '''
		self.__fileColor = color
	
	def setConsoleColor(self, color):
		''' Enable or disable ansi color output '''
		self.__consoleColor = color
	
	def setSyslogLevel(self, level = LOG_NONE):
		''' Maximum level of messages to log by syslog.
		    Set LOG_NONE to disable syslog (default) '''
		
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__syslogLevel = level
		if (os.name == 'posix'):
			if (self.__syslogLevel != LOG_NONE):
				# Import syslog module
				global syslog
				import syslog
				
				# Set ident string for syslog
				ident = 'opsi'
				try:
					raise Exception
				except Exception:
					# Go back 2 frames
					frame = sys.exc_traceback.tb_frame.f_back.f_back
					# Get caller's filename
					filename = frame.f_code.co_filename
					ident = filename.split('/')[-1]
				#syslog.openlog(ident, syslog.LOG_PID | syslog.LOG_CONS, syslog.LOG_DAEMON)
				syslog.openlog(ident, syslog.LOG_CONS, syslog.LOG_DAEMON)
		else:
			#not yet implemented
			pass
	
	def setMessageSubjectLevel(self, level = LOG_NONE):
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__messageSubjectLevel = level
	
	def setConsoleLevel(self, level = LOG_NONE):
		''' Maximum level of messages to print to stderr
		    Set LOG_NONE to disable output to stderr (default) '''
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__consoleLevel = level
	
	def getConsoleLevel(self):
		return self.__consoleLevel
	
	def setLogFile(self, logFile, currentThread=False, object=None):
		''' Set the filename of logfile. '''
		if currentThread:
			self._setThreadConfig('logFile', logFile)
			self.debug(u"Now using log-file '%s' for thread %s" \
				% (logFile, thread.get_ident()))
		elif object:
			self._setObjectConfig(id(object), 'logFile', logFile)
			self.debug(u"Now using log-file '%s' for object 0x%x" % (logFile, id(object)))
		else:
			self.__logFile = logFile
			self.debug(u"Now using log-file '%s'" % self.__logFile)
	
	def linkLogFile(self, linkFile, currentThread=False, object=None):
		''' Set the filename of logfile. '''
		logFile = None
		if currentThread:
			logFile = self._getThreadConfig('logFile')
		elif object:
			logFile = self._getObjectConfig(id(object), 'logFile')
		else:
			logFile = self.__logFile
		
		if not logFile:
			self.error(u"Cannot create symlink '%s': log-file unknown" % linkFile)
			return
		
		if not os.path.isabs(linkFile):
			linkFile = os.path.join( os.path.dirname(logFile), linkFile )
		
		try:
			if (logFile == linkFile):
				raise Exception(u'logFile and linkFile are the same file!')
			if os.path.exists(linkFile):
				os.unlink(linkFile)
			os.symlink(logFile, linkFile)
		except Exception, e:
			self.error(u"Failed to create symlink from '%s' to '%s': %s" % (logFile, linkFile, e))
	
	def setFileLevel(self, level = LOG_NONE):
		''' Maximum level of messages to appear in logfile
		    Set LOG_NONE to disable output to logfile (default) '''
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__fileLevel = level
	
	def exit(self, object=None):
		if object:
			if self.__objectConfig.has_key(id(object)):
				self.debug(u"Deleting config of object 0x%x" % id(object))
				del self.__objectConfig[id(object)]
			for objectId in self.__objectConfig.keys():
				self.debug2(u"Got special config for object 0x%x" % objectId)
			
		threadId = unicode(thread.get_ident())
		if self.__threadConfig.has_key(threadId):
			self.debug(u"Deleting config of thread %s" % threadId)
			del self.__threadConfig[threadId]
		for threadId in self.__threadConfig.keys():
			self.debug2(u"Got special config for thread %s" % threadId)
	
	def _setThreadConfig(self, key, value):
		threadId = unicode(thread.get_ident())
		if not self.__threadConfig.has_key(threadId):
			self.__threadConfig[threadId] = {}
		self.__threadConfig[threadId][key] = value
	
	def _getThreadConfig(self, key = None):
		threadId = unicode(thread.get_ident())
		if not self.__threadConfig.has_key(threadId):
			return None
		if not key:
			return self.__threadConfig[threadId]
		return self.__threadConfig[threadId].get(key)
	
	def _setObjectConfig(self, objectId, key, value):
		if not self.__objectConfig.has_key(objectId):
			self.__objectConfig[objectId] = {}
		self.__objectConfig[objectId][key] = value
	
	def _getObjectConfig(self, objectId, key = None):
		if not self.__objectConfig.has_key(objectId):
			return None
		if not key:
			return self.__objectConfig[objectId]
		return self.__objectConfig[objectId].get(key)
	
	def log(self, level, message, raiseException = False):
		''' Log a message '''
		try:
			if (level > self.__messageSubjectLevel and
			    level > self.__consoleLevel and 
			    level > self.__fileLevel and 
			    level > self.__syslogLevel and
			    not self.univentionLogger_priv):
				    return
			
			if not type(message) is unicode:
				if not type(message) is str:
					message = unicode(message)
				else:
					message = unicode(message, 'utf-8', 'replace')
			
			levelname     = u''
			componentname = self.__componentName
			color         = COLOR_NORMAL
			filename      = u''
			linenumber    = u''
			datetime      = unicode(time.strftime(u"%b %d %H:%M:%S", time.localtime()), 'utf-8', 'replace')
			threadId      = unicode(thread.get_ident())
			specialConfig = None
			
			if (level == LOG_CONFIDENTIAL):
				levelname = u'confidential'
				color     = CONFIDENTIAL_COLOR
			elif (level == LOG_DEBUG2):
				levelname = u'debug2'
				color     = DEBUG_COLOR
			elif (level == LOG_DEBUG):
				levelname = u'debug'
				color     = DEBUG_COLOR
			elif (level == LOG_INFO):
				levelname = u'info'
				color     = INFO_COLOR
			elif (level == LOG_NOTICE):
				levelname = u'notice'
				color     = NOTICE_COLOR
			elif (level == LOG_WARNING):
				levelname = u'warning'
				color     = WARNING_COLOR
			elif (level == LOG_ERROR):
				levelname = u'error'
				color     = ERROR_COLOR
			elif (level == LOG_CRITICAL):
				levelname = u'critical'
				color     = CRITICAL_COLOR
			elif (level == LOG_ESSENTIAL):
				levelname = u'essential'
				color     = COMMENT_COLOR
			
			try:
				filename = unicode(os.path.basename( sys._getframe(2).f_code.co_filename ))
				linenumber = unicode( sys._getframe(2).f_lineno )
				
				specialConfig = self._getThreadConfig()
				if not specialConfig and self.__objectConfig:
					# Ouch, this hurts...
					f = sys._getframe(2)
					while (f != None):
						obj = f.f_locals.get('self')
						if obj:
							c = self._getObjectConfig(id(obj))
							if c:
								specialConfig = c
								break
						f = f.f_back
			except:
				# call stack not deep enough?
				pass
			
			if specialConfig:
				componentname = specialConfig.get('componentName', componentname)
			
			if (level <= self.__messageSubjectLevel):
				m = self.__messageSubjectFormat
				if specialConfig:
					m = specialConfig.get('messageSubjectFormat', m)
				m = unicode(m)
				m = m.replace(u'%D', datetime)
				m = m.replace(u'%T', threadId)
				m = m.replace(u'%l', unicode(level))
				m = m.replace(u'%L', levelname)
				m = m.replace(u'%C', componentname)
				m = m.replace(u'%M', message)
				m = m.replace(u'%F', filename)
				m = m.replace(u'%N', linenumber)
				if (self.__messageSubjectLevel < LOG_CONFIDENTIAL):
					for string in self.__confidentialStrings:
						m = m.replace(string, u'*** confidential ***')
				
				self.__loggerSubject.setMessage(m, level)
			
			if (level <= self.__consoleLevel):
				# Log to terminal
				m = self.__consoleFormat
				if specialConfig:
					m = specialConfig.get('consoleFormat', m)
				m = unicode(m)
				m = m.replace(u'%D', datetime)
				m = m.replace(u'%T', threadId)
				m = m.replace(u'%l', unicode(level))
				m = m.replace(u'%L', levelname)
				m = m.replace(u'%C', componentname)
				m = m.replace(u'%M', message)
				m = m.replace(u'%F', filename)
				m = m.replace(u'%N', linenumber)
				if (self.__consoleLevel < LOG_CONFIDENTIAL):
					for string in self.__confidentialStrings:
						m = m.replace(string, u'*** confidential ***')
				
				fh = sys.stderr
				if (self.__consoleStdout):
					fh = sys.stdout
				
				fhEncoding = None
				try:
					fhEncoding = fh.encoding
				except:
					pass
				if fhEncoding is None:
					fhEncoding = locale.getpreferredencoding()
				
				if self.__consoleColor:
					m = u"%s%s%s\n" % (color, m, COLOR_NORMAL)
				else:
					m = u"%s\n" % m
				fh.write(m.encode(fhEncoding, 'backslashreplace'))
				
			if (level <= self.__fileLevel):
				# Log to file
				logFile = self.__logFile
				if specialConfig:
					logFile = specialConfig.get('logFile', logFile)
				if logFile:
					m = self.__fileFormat
					if specialConfig:
						m = specialConfig.get('fileFormat', m)
					m = unicode(m)
					m = m.replace(u'%D', datetime)
					m = m.replace(u'%T', threadId)
					m = m.replace(u'%l', unicode(level))
					m = m.replace(u'%L', levelname)
					m = m.replace(u'%C', componentname)
					m = m.replace(u'%M', message)
					m = m.replace(u'%F', filename)
					m = m.replace(u'%N', linenumber)
					if (self.__fileLevel < LOG_CONFIDENTIAL):
						for string in self.__confidentialStrings:
							m = m.replace(string, u'*** confidential ***')
					
					# Open the file
					lf = None
					try:
						lf = codecs.open(logFile, 'a+', 'utf-8', 'replace')
					except Exception, e:
						pass
					
					if lf:
						timeout = 0
						locked = False
						while (not locked and timeout < 2000):
							# While not timed out and not locked
							try:
								# Try to lock file
								if (os.name == 'nt'):
									hfile = win32file._get_osfhandle(lf.fileno())
									win32file.LockFileEx(hfile, win32con.LOCKFILE_EXCLUSIVE_LOCK, 0, -0x7fff0000, pywintypes.OVERLAPPED())
									#win32file.LockFileEx(hfile, flags, 0, -0x10000, __overlapped)
								elif (os.name == 'posix'):
									# Flags for exclusive, non-blocking lock
									fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
							except IOError, e:
								# Locking failed
								# increase timeout counter, sleep 100 millis
								timeout += 100
								time.sleep(0.1)
							else:
								# File successfully locked
								locked = True
						
						if locked:
							if self.__fileColor:
								m = u"%s%s%s" % (color, m, COLOR_NORMAL)
							m += u'\n'
							if (os.name == 'nt'):
								m = m.replace(u'\n', u'\r\n')
							lf.write(m)
							lf.close()
			
			if (level <= self.__syslogLevel):
				# Log to syslog
				m = self.__syslogFormat
				if specialConfig:
					m = specialConfig.get('syslogFormat', m)
				m = unicode(m)
				m = m.replace(u'%D', datetime)
				m = m.replace(u'%T', threadId)
				m = m.replace(u'%l', unicode(level))
				m = m.replace(u'%L', levelname)
				m = m.replace(u'%C', componentname)
				m = m.replace(u'%M', message)
				m = m.replace(u'%F', filename)
				m = m.replace(u'%N', linenumber)
				if (self.__syslogLevel < LOG_CONFIDENTIAL):
					for string in self.__confidentialStrings:
						m = m.replace(string, u'*** confidential ***')
				
				if (os.name == 'posix'):
					if (level == LOG_CONFIDENTIAL):
						syslog.syslog(syslog.LOG_DEBUG, m)
					elif (level == LOG_DEBUG2): 
						syslog.syslog(syslog.LOG_DEBUG, m)
					elif (level == LOG_DEBUG):
						syslog.syslog(syslog.LOG_DEBUG, m)
					elif (level == LOG_INFO):
						syslog.syslog(syslog.LOG_INFO, m)
					elif (level == LOG_NOTICE):
						syslog.syslog(syslog.LOG_NOTICE, m)
					elif (level == LOG_WARNING):
						syslog.syslog(syslog.LOG_WARNING, m)
					elif (level == LOG_ERROR):
						syslog.syslog(syslog.LOG_ERR, m)
					elif (level == LOG_CRITICAL):
						syslog.syslog(syslog.LOG_CRIT, m)
					elif (level == LOG_COMMENT):
						syslog.syslog(syslog.LOG_CRIT, m)
				else:
					#not yet implemented
					pass
			
			if (self.univentionLogger_priv):
				# univention log
				m = self.__univentionFormat
				if specialConfig:
					m = specialConfig.get('univentionFormat', m)
				m = unicode(m)
				m = m.replace(u'%D', datetime)
				m = m.replace(u'%T', threadId)
				m = m.replace(u'%l', unicode(level))
				m = m.replace(u'%L', levelname)
				m = m.replace(u'%C', componentname)
				m = m.replace(u'%M', message)
				m = m.replace(u'%F', filename)
				m = m.replace(u'%N', linenumber)
				for string in self.__confidentialStrings:
					m = m.replace(string, u'*** confidential ***')
				
				if (level == LOG_CONFIDENTIAL):
					pass
				elif (level == LOG_DEBUG2):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ALL, m)
				elif (level == LOG_DEBUG):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ALL, m)
				elif (level == LOG_INFO):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ALL, m)
				elif (level == LOG_NOTICE):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.INFO, m)
				elif (level == LOG_WARNING):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.WARN, m)
				elif (level == LOG_ERROR):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ERROR, m)
				elif (level == LOG_CRITICAL):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ERROR, m)
				elif (level == LOG_COMMENT):
					self.univentionLogger_priv.debug(self.__univentionClass, self.univentionLogger_priv.ERROR, m)
		except Exception, e:
			if raiseException:
				raise
		
	def logException(self, e, logLevel=LOG_CRITICAL):
		self.logTraceback(sys.exc_info()[2], logLevel)
		message = forceUnicode(e)
		self.log(logLevel, u'     ==>>> %s' % message)
		
	def logTraceback(self, tb, logLevel=LOG_CRITICAL):
		''' Log an exception. '''
		self.log(logLevel, u'Traceback:')
		# Traceback
		try:
			while (tb != None):
				f = tb.tb_frame
				c = f.f_code
				self.log(logLevel, u"     line %s in '%s' in file '%s'" % (tb.tb_lineno, c.co_name, c.co_filename))
				tb = tb.tb_next
		except Exception, e:
			self.log(LOG_CRITICAL, u"    Failed to log traceback for '%s': %s" % (tb, e))

	def confidential( self, message ):
		''' Log a confidential message. '''
		self.log(LOG_CONFIDENTIAL, message)
	
	def debug3( self, message ):
		''' Log a debug message. '''
		self.debug2(message)
	
	def debug2( self, message ):
		''' Log a debug message. '''
		self.log(LOG_DEBUG2, message)
	
	def debug( self, message ):
		''' Log a debug message. '''
		self.log(LOG_DEBUG, message)
	
	def info( self, message ):
		''' Log a info message. '''
		self.log(LOG_INFO, message)
	
	def msg( self, message ):
		''' Log a info message. '''
		self.info(message)
	
	def notice( self, message ):
		''' Log a notice message. '''
		self.log(LOG_NOTICE, message)
	
	def warning( self, message, ):
		''' Log a warning message. '''
		self.log(LOG_WARNING, message)
	
	def error( self, message ):
		''' Log a error message. '''
		self.log(LOG_ERROR, message)
	
	def err( self, message ):
		''' Log a error message. '''
		self.error(message)
	
	def critical( self, message ):
		''' Log a critical message. '''
		self.log(LOG_CRITICAL, message)
	
	def essential( self, message ):
		''' Log a essential message. '''
		self.log(LOG_ESSENTIAL, message)
	
	def comment( self, message ):
		''' Log a comment message. '''
		self.essential(message)
	

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                          CLASS LOGGER                                              =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class Logger(LoggerImplementation):
	''' This class implements a SINGLETON used for logging to console, file or syslog. '''
	
	# Storage for the instance reference
	__instance = None
	
	def __init__(self, logFile = None):
		""" Create singleton instance """
		
		# Check whether we already have an instance
		if Logger.__instance is None:
			# Create and remember instance
			Logger.__instance = LoggerImplementation()
		
		# Store instance reference as the only member in the handle
		self.__dict__['_Logger__instance'] = Logger.__instance
	
	
	def __getattr__(self, attr):
		""" Delegate access to implementation """
		return getattr(self.__instance, attr)

	def __setattr__(self, attr, value):
		""" Delegate access to implementation """
	 	return setattr(self.__instance, attr, value)

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                          CLASS VIRTFILE                                            =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class VirtFile:
	
	def __init__(self, logger, level):
		self.logger = logger
		self.level = level
		self.encoding = 'utf-8'
		
	def write(self, s):
		self.logger.log(self.level, s)
	
	def flush(self):
		return
	
