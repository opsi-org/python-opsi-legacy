# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =             OPSI Logger Module             =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.6.1'

#Imports
import os
if os.name == 'posix':
	import os
else:
	import win32evtlogutil

# Loglevels
LOG_CONFIDENTIAL = 9
LOG_DEBUG2 = 7
LOG_DEBUG = 6
LOG_INFO = 5
LOG_NOTICE = 4
LOG_WARNING = 3
LOG_ERROR = 2
LOG_CRITICAL = 1
LOG_COMMENT = 0
LOG_NONE = -1

# Imports
import sys, time, os, thread, threading

if os.name == 'nt':
	# Windows imports for file locking
	import win32con, win32file, pywintypes
	LOCK_EX = win32con.LOCKFILE_EXCLUSIVE_LOCK
	LOCK_SH = 0 # the default
	LOCK_NB = win32con.LOCKFILE_FAIL_IMMEDIATELY
	__overlapped = pywintypes.OVERLAPPED()
	
	# Colors
	COLOR_NORMAL =	''
	COLOR_BLACK = ''
	COLOR_RED = ''
	COLOR_GREEN = ''
	COLOR_YELLOW = ''
	COLOR_BLUE = ''
	COLOR_MAGENTA = ''
	COLOR_CYAN = ''
	COLOR_WHITE = ''
	COLOR_LIGHT_BLACK = ''
	COLOR_LIGHT_RED = ''
	COLOR_LIGHT_GREEN = ''
	COLOR_LIGHT_YELLOW = ''
	COLOR_LIGHT_BLUE = ''
	COLOR_LIGHT_MAGENTA = ''
	COLOR_LIGHT_CYAN = ''
	COLOR_LIGHT_WHITE = ''

elif os.name == 'posix':
	# Posix imports for file locking
	import fcntl
	LOCK_EX = fcntl.LOCK_EX
	LOCK_SH = fcntl.LOCK_SH
	LOCK_NB = fcntl.LOCK_NB
	
	# Colors
	COLOR_NORMAL =	'\033[0;0;0m'
	COLOR_BLACK = '\033[0;30;40m'
	COLOR_RED = '\033[0;31;40m'
	COLOR_GREEN = '\033[0;32;40m'
	COLOR_YELLOW = '\033[0;33;40m'
	COLOR_BLUE = '\033[0;34;40m'
	COLOR_MAGENTA = '\033[0;35;40m'
	COLOR_CYAN = '\033[0;36;40m'
	COLOR_WHITE = '\033[0;37;40m'
	COLOR_LIGHT_BLACK = '\033[1;30;40m'
	COLOR_LIGHT_RED = '\033[1;31;40m'
	COLOR_LIGHT_GREEN = '\033[1;32;40m'
	COLOR_LIGHT_YELLOW = '\033[1;33;40m'
	COLOR_LIGHT_BLUE = '\033[1;34;40m'
	COLOR_LIGHT_MAGENTA = '\033[1;35;40m'
	COLOR_LIGHT_CYAN = '\033[1;36;40m'
	COLOR_LIGHT_WHITE = '\033[1;37;40m'
	
COLORS_AVAILABLE = [ 	COLOR_NORMAL, COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW,
			COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE, COLOR_LIGHT_BLACK,
			COLOR_LIGHT_RED, COLOR_LIGHT_GREEN, COLOR_LIGHT_YELLOW, COLOR_LIGHT_BLUE,
			COLOR_LIGHT_MAGENTA, COLOR_LIGHT_CYAN, COLOR_LIGHT_WHITE ]

DEBUG_COLOR = COLOR_WHITE
INFO_COLOR = COLOR_LIGHT_WHITE
NOTICE_COLOR = COLOR_GREEN
WARNING_COLOR = COLOR_YELLOW
ERROR_COLOR = COLOR_RED
CRITICAL_COLOR = COLOR_LIGHT_RED
CONFIDENTIAL_COLOR = COLOR_LIGHT_YELLOW
COMMENT_COLOR = COLOR_LIGHT_CYAN

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                   CLASS LOGGERIMPLEMENTATION                                       =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class LoggerImplementation:
	''' Implementation of the singleton interface '''
	
	def __init__(self, logFile = None):
		self.__syslogLevel = LOG_NONE
		self.__consoleLevel = LOG_NONE
		self.__fileLevel = LOG_NONE
		self.__fileColor = False
		self.__consoleColor = False
		self.__logFile = logFile
		self.__syslogFormat = '%M'
		self.__consoleFormat = '%M'
		self.__fileFormat = '%D [%L] %M (%F|%N)'
		self.univentionLogger_priv = None
		self.__univentionClass = None
		self.__univentionFormat = 'opsi: %M'
		self.__threadConfig = {}
		self.__stdout = VirtFile(self, LOG_NOTICE)
		self.__stderr = VirtFile(self, LOG_ERROR)
	
	def getStderr(self):
		return self.__stderr
	
	def getStdout(self):
		return self.__stdout
	
	def setLogFormat(self, format, currentThread=False):
		self.setConsoleFormat(format, currentThread)
		self.setSyslogFormat(format, currentThread)
		self.setFileFormat(format, currentThread)
		
	def setConsoleFormat(self, format, currentThread=False):
		if currentThread:
			self._setThreadConfig('consoleFormat', format)
		else:
			self.__consoleFormat = format
	
	def setSyslogFormat(self, format, currentThread=False):
		if currentThread:
			self._setThreadConfig('syslogFormat', format)
		else:
			self.__syslogFormat = format
		
	def setFileFormat(self, format, currentThread=False):
		if currentThread:
			self._setThreadConfig('fileFormat', format)
		else:
			self.__fileFormat = format
	
	def setUniventionFormat(self, format, currentThread=False):
		if currentThread:
			self._setThreadConfig('univentionFormat', format)
		else:
			self.__univentionFormat = format
	
	def setUniventionLogger(self, logger):
		self.univentionLogger_priv = logger
	
	def setUniventionClass(self, c):
		self.__univentionClass = c
	
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
		if os.name == 'posix':
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
	
	def setConsoleLevel(self, level = LOG_NONE):
		''' Maximum level of messages to print to stderr
		    Set LOG_NONE to disable output to stderr (default) '''
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__consoleLevel = level
	
	def setLogFile(self, logFile, currentThread=False):
		''' Set the filename of logfile. '''
		if currentThread:
			self._setThreadConfig('logFile', logFile)
			self.info("Now using log-file: '%s' for thread %s" \
				% (logFile, thread.get_ident()))
		else:
			self.__logFile = logFile
			self.info("Now using log-file: '%s'" % self.__logFile)
	
	def linkLogFile(self, linkFile, currentThread=False):
		''' Set the filename of logfile. '''
		logFile = None
		if currentThread:
			logFile = self._getThreadConfig('logFile')
		else:
			logFile = self.__logFile
		if not os.path.isabs(linkFile):
			linkFile = os.path.join( os.path.dirname(logFile), linkFile)
		
		try:
			if (logFile == linkFile):
				raise Exception('logFile and linkFile are the same file!')
			if os.path.exists(linkFile):
				os.unlink(linkFile)
			os.symlink(logFile, linkFile)
		except Exception, e:
			self.error("Failed to create symlink from '%s' to '%s': %s" % (logFile, linkFile, e))
		
	def setFileLevel(self, level = LOG_NONE):
		''' Maximum level of messages to appear in logfile
		    Set LOG_NONE to disable output to logfile (default) '''
		if (level < LOG_NONE):  level = LOG_NONE
		if (level > LOG_CONFIDENTIAL): level = LOG_CONFIDENTIAL
		self.__fileLevel = level
	
	def exit(self):
		threadId = str(long(thread.get_ident()))
		if self.__threadConfig.has_key(threadId):
			self.debug("Deleting config of thread %s" % threadId)
			del self.__threadConfig[threadId]
		for threadId in self.__threadConfig.keys():
			self.debug2("Got special config for thread %s" % threadId)
	
	def _setThreadConfig(self, key, value):
		threadId = str(long(thread.get_ident()))
		if not self.__threadConfig.has_key(threadId):
			self.__threadConfig[threadId] = {}
		self.__threadConfig[threadId][key] = value
		
	def _getThreadConfig(self, key):
		threadId = str(long(thread.get_ident()))
		if not self.__threadConfig.has_key(threadId):
			return None
		return self.__threadConfig[threadId].get(key)
	
	def log(self, level, message):
		''' Log a message '''
		
		if (level > self.__consoleLevel and 
		    level > self.__fileLevel and 
		    level > self.__syslogLevel and
		    not self.univentionLogger_priv):
			    return
		
		if type(message) not in (str, unicode):
			message = "%s" % message
		levelname = ''
		color = COLOR_NORMAL
		filename = ''
		linenumber = ''
		datetime = time.strftime( "%b %d %H:%M:%S", time.localtime() )
		threadId = str(long(thread.get_ident()))
		
		if (level == LOG_CONFIDENTIAL): 
			levelname = 'confidential'
			color = CONFIDENTIAL_COLOR
		elif (level == LOG_DEBUG2): 
			levelname = 'debug2'
			color = DEBUG_COLOR
		elif (level == LOG_DEBUG): 
			levelname = 'debug'
			color = DEBUG_COLOR
		elif (level == LOG_INFO):
			levelname = 'info'
			color = INFO_COLOR
		elif (level == LOG_NOTICE):
			levelname = 'notice'
			color = NOTICE_COLOR
		elif (level == LOG_WARNING):
			levelname = 'warning'
			color = WARNING_COLOR
		elif (level == LOG_ERROR):
			levelname = 'error'
			color = ERROR_COLOR
		elif (level == LOG_CRITICAL):
			levelname = 'critical'
			color = CRITICAL_COLOR
		elif (level == LOG_COMMENT):
			levelname = 'comment'
			color = COMMENT_COLOR
		
		try:
			raise Exception
		except Exception:
			try:
				frame = sys.exc_traceback.tb_frame
				frame = frame.f_back
				frame = frame.f_back
				#function = frame.f_code.co_name
				linenumber = str(frame.f_lineno)
				filename = frame.f_code.co_filename
				filename = os.path.basename(filename)
			except:
				pass
			
		if (level <= self.__consoleLevel):
			# Log to terminal
			m = self._getThreadConfig('consoleFormat')
			if not m:
				m = self.__consoleFormat
			m = m.replace('%D', datetime)
			m = m.replace('%T', threadId)
			m = m.replace('%l', str(level))
			m = m.replace('%L', levelname)
			m = m.replace('%M', message)
			m = m.replace('%F', filename)
			m = m.replace('%N', linenumber)
			if self.__consoleColor:
				print >> sys.stderr, "%s%s%s" % (color, m, COLOR_NORMAL)
			else:
				print >> sys.stderr, m
		
		if (level <= self.__fileLevel):
			logFile = self._getThreadConfig('logFile')
			if not logFile:
				logFile = self.__logFile
			if not logFile:
				return
			
			# Log to file
			m = self._getThreadConfig('fileFormat')
			if not m:
				m = self.__fileFormat
			
			m = m.replace('%D', datetime)
			m = m.replace('%T', threadId)
			m = m.replace('%l', str(level))
			m = m.replace('%L', levelname)
			m = m.replace('%M', message)
			m = m.replace('%F', filename)
			m = m.replace('%N', linenumber)
			
			
			# Open the file
			lf = None
			try:
				lf = open(logFile, 'a+')
			except Exception, e:
				pass
			
			if lf:
				# Flags for exclusive, non-blocking lock
				flags = LOCK_EX | LOCK_NB
				
				timeout = 0
				locked = False
				while (not locked and timeout < 2000):
					# While not timed out and not locked
					try:
						# Try to lock file
						if (os.name == 'nt'):
							hfile = win32file._get_osfhandle(lf.fileno())
							self.ov=pywintypes.OVERLAPPED()
							win32file.LockFileEx(hfile, win32con.LOCKFILE_EXCLUSIVE_LOCK, 0,-0x7fff0000,self.ov)
							#win32file.LockFileEx(hfile, flags, 0, -0x10000, __overlapped)
						elif (os.name =='posix'):
							fcntl.flock(lf.fileno(), flags)
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
						print >> lf, "%s%s%s" % (color, m, COLOR_NORMAL)
					else:
						print >> lf, m
					lf.close()
		
		if (level <= self.__syslogLevel):
			# Log to syslog
			m = self._getThreadConfig('syslogFormat')
			if not m:
				m = self.__syslogFormat
			m = m.replace('%D', datetime)
			m = m.replace('%T', threadId)
			m = m.replace('%l', str(level))
			m = m.replace('%L', levelname)
			m = m.replace('%M', message)
			m = m.replace('%F', filename)
			m = m.replace('%N', linenumber)
			
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
			m = self._getThreadConfig('univentionFormat')
			if not m:
				m = self.__univentionFormat
			m = m.replace('%D', datetime)
			m = m.replace('%T', threadId)
			m = m.replace('%l', str(level))
			m = m.replace('%L', levelname)
			m = m.replace('%M', message)
			m = m.replace('%F', filename)
			m = m.replace('%N', linenumber)
			
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
	
	def logException(self, e):
		self.logTraceback(sys.exc_info()[2])
		self.log(LOG_CRITICAL,'     ==>>> %s' % e)
	
	def logTraceback(self, tb):
		''' Log an exception. '''
		self.log(LOG_CRITICAL, 'Traceback:')
		# Traceback
		while (tb != None):
			f = tb.tb_frame
			c = f.f_code
			self.log(LOG_CRITICAL, "     line %s in '%s' in file '%s'" % (tb.tb_lineno, c.co_name, c.co_filename))
			tb = tb.tb_next
	
	def confidential( self, message ):
		''' Log a confidential message. '''
		self.log(LOG_CONFIDENTIAL, message)
	
	def debug2( self, message ):
		''' Log a debug message. '''
		self.log(LOG_DEBUG2, message)
	
	def debug( self, message ):
		''' Log a debug message. '''
		self.log(LOG_DEBUG, message)
	
	def info( self, message ):
		''' Log a info message. '''
		self.log(LOG_INFO, message)
	
	def notice( self, message ):
		''' Log a notice message. '''
		self.log(LOG_NOTICE, message)
	
	def warning( self, message, ):
		''' Log a warning message. '''
		self.log(LOG_WARNING, message)
	
	def error( self, message ):
		''' Log a error message. '''
		self.log(LOG_ERROR, message)
	
	def critical( self, message ):
		''' Log a critical message. '''
		self.log(LOG_CRITICAL, message)
	
	def comment( self, message ):
		''' Log a critical message. '''
		self.log(LOG_COMMENT, message)
	

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                          CLASS LOGGER                                              =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class Logger(LoggerImplementation):
	''' This class implements a SINGLETON used for 
	    logging to console, file or syslog. '''
	
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
		
	def write(self, s):
		self.logger.log(self.level, s)

