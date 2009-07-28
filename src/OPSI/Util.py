#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Util    =
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

__version__ = '0.3.6.1'

# Imports
import json, threading, re, stat, base64, urllib, os, shutil, gettext
try:
	from hashlib import md5
except ImportError:
	from md5 import md5
from OPSI.web2 import responsecode
from OPSI.web2.dav import davxml
from httplib import HTTPConnection, HTTPSConnection
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ServerFactory, ClientFactory
from twisted.internet import reactor, ssl

# OPSI imports
from Logger import *

# Get Logger instance
logger = Logger()

# Get locale
try:
	t = gettext.translation('opsi_util', LOCALE_DIR)
	_ = t.ugettext
except Exception, e:
	logger.error("Locale not found: %s" % e)
	def _(string):
		"""Dummy method, created and called when no locale is found.
		Uses the fallback language (called C; means english) then."""
		return string

def _async_raise(tid, excobj):
	import ctypes
	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(excobj))
	if (res == 0):
		logger.error("_async_raise: nonexistent thread id")
		raise ValueError("nonexistent thread id")
	elif (res > 1):
		# if it returns a number greater than one, you're in trouble,
		# and you should call it again with exc=NULL to revert the effect
		ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
		logger.error("_async_raise: PyThreadState_SetAsyncExc failed")
		raise SystemError("PyThreadState_SetAsyncExc failed")
 
class KillableThread(threading.Thread):
	def raise_exc(self, excobj):
		if not self.isAlive():
			logger.error("Cannot terminate, thread must be started")
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

# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Subjects                                                                    =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class Subject(object):
	def __init__(self, id, type='', title='', **args):
		self._id = id
		self._type = type
		self._title = title
		self._observers = []
	
	def reset(self):
		pass
	
	def getClass(self):
		return self.__class__.__name__
	
	def getId(self):
		return self._id
	
	def getType(self):
		return self._type
	
	def getTitle(self):
		return self._title
	
	def attachObserver(self, observer):
		if not observer in self._observers:
			self._observers.append(observer)
	
	def detachObserver(self, observer):
		if observer in self._observers:
			self._observers.remove(observer)
	
	def serializable(self):
		return { "id": self.getId(), "type": self.getType(), "title": self.getTitle(), "class": self.getClass() }
	
	def __str__(self):
		return '<%s type: %s, id: %s>' % (self.__class__.__name__, self._type, self._id)
	
class MessageSubject(Subject):
	def __init__(self, id, type='', title='', **args):
		Subject.__init__(self, id, type, title, **args)
		self.reset()
		if args.has_key('message'):
			self._message = args['message']
		if args.has_key('severity'):
			self._severity = args['severity']
		logger.debug("MessageSubject '%s' created" % self._id)
	
	def reset(self):
		Subject.reset(self)
		self._message = ""
		self._severity = 0
	
	def setMessage(self, message, severity = 0):
		self._message = str(message)
		self._severity = severity
		self._notifyMessageChanged(message)
		
	def getMessage(self):
		return self._message
	
	def getSeverity(self):
		return self._severity
	
	def _notifyMessageChanged(self, message):
		for o in self._observers:
			o.messageChanged(self, message)
	
	def serializable(self):
		s = Subject.serializable(self)
		s['message'] = self.getMessage()
		s['severity'] = self.getSeverity()
		return s
	
class ChoiceSubject(MessageSubject):
	def __init__(self, id, type='', title='', **args):
		MessageSubject.__init__(self, id, type, title, **args)
		self.reset()
		self._callbacks = []
		if args.has_key('choices'):
			self._choices = args['choices']
		if args.has_key('selectedIndex'):
			self._selectedIndex = args['selectedIndex']
		if args.has_key('callbacks'):
			self._callbacks = args['callbacks']
		logger.debug("ChoiceSubject '%s' created" % self._id)
	
	def reset(self):
		MessageSubject.reset(self)
		self._choices = []
		self._selectedIndex = -1
		
	def setSelectedIndex(self, selectedIndex):
		if not type(selectedIndex) is int:
			return
		if (selectedIndex > len(self._choices)-1):
			return
		self._selectedIndex = selectedIndex
		self._notifySelectedIndexChanged(selectedIndex)
	
	def getSelectedIndex(self):
		return self._selectedIndex
	
	def setChoices(self, choices):
		if not type(choices) in (list, tuple):
			choices = [ choices ]
		self._choices = choices
		if (len(self._choices) > 0) and (self._selectedIndex < 0):
			self._selectedIndex = 0
		self._notifyChoicesChanged(choices)
	
	def getChoices(self):
		return self._choices
	
	def selectChoice(self):
		logger.info("ChoiceSubject.selectChoice()")
		if (self._selectedIndex >= 0) and (self._selectedIndex < len(self._callbacks)):
			# Exceute callback
			logger.notice("Executing callback %s" % self._callbacks[self._selectedIndex])
			self._callbacks[self._selectedIndex](self)
		
	def setCallbacks(self, callbacks):
		if not type(callbacks) in (list, tuple):
			callbacks = [ callbacks ]
		self._callbacks = callbacks
	
	def _notifySelectedIndexChanged(self, selectedIndex):
		for o in self._observers:
			o.selectedIndexChanged(self, selectedIndex)
	
	def _notifyChoicesChanged(self, choices):
		for o in self._observers:
			o.choicesChanged(self, choices)
	
	def serializable(self):
		s = MessageSubject.serializable(self)
		s['choices'] = self.getChoices()
		s['selectedIndex'] = self.getSelectedIndex()
		return s

class ProgressSubject(MessageSubject):
	def __init__(self, id, type='', title='', **args):
		MessageSubject.__init__(self, id, type, title, **args)
		self.reset()
		self._fireAlways = True
		if args.has_key('end'):
			self._end = args['end']
			if (self._end < 0): self._end = 0
		if args.has_key('percent'):
			self._percent = args['percent']
		if args.has_key('state'):
			self._state = args['state']
		if args.has_key('timeStarted'):
			self._timeStarted = args['timeStarted']
		if args.has_key('timeSpend'):
			self._timeSpend = args['timeSpend']
		if args.has_key('timeLeft'):
			self._timeLeft = args['timeLeft']
		if args.has_key('timeFired'):
			self._timeFired = args['timeFired']
		if args.has_key('speed'):
			self._speed = args['speed']
		if args.has_key('fireAlways'):
			self._fireAlways = bool(args['fireAlways'])
		logger.debug("ProgressSubject '%s' created" % self._id)
		
	def reset(self):
		MessageSubject.reset(self)
		self._end = 0
		self._percent = 0
		self._state = 0
		self._timeStarted = long(time.time())
		self._timeSpend = 0
		self._timeLeft = 0
		self._timeFired = 0
		self._speed = 0
	
	def setEnd(self, end):
		self._end = end
		if (self._end < 0):
			self._end = 0
		self.setState(self._state)
		
	def setState(self, state):
		if (state <= 0):
			state = 0
			self._percent = 0
		if (state > self._end):
			state = self._end
			self._percent = 100
		self._state = state
		
		now = long(time.time())
		if self._fireAlways or (self._timeFired != now) or (self._state == self._end):
			if (self._end == 0):
				self._percent = 100
			else:
				self._percent = float(100)*(float(self._state) / float(self._end))
			
			self._timeSpend = now - self._timeStarted
			if self._timeSpend:
				self._speed = int(self._state/self._timeSpend)
				if (self._speed > 0):
					self._timeLeft = ((self._end-self._state)/self._speed)
			
			self._timeFired = now
			self._notifyProgressChanged(self._state, self._percent, self._timeSpend, self._timeLeft, self._speed)
	
	def addToState(self, amount):
		self.setState(self._state + amount)
	
	def getEnd(self):
		return self._end
	
	def getState(self):
		return self._state
	
	def getPercent(self):
		return self._percent
	
	def getTimeSpend(self):
		return self._timeSpend
		
	def getTimeLeft(self):
		return self._timeLeft
		
	def getSpeed(self):
		return self._speed
		
	def _notifyProgressChanged(self, state, percent, timeSpend, timeLeft, speed):
		for o in self._observers:
			o.progressChanged(self, state, percent, timeSpend, timeLeft, speed)
	
	def serializable(self):
		s = MessageSubject.serializable(self)
		s['end'] = self.getEnd()
		s['state'] = self.getState()
		s['percent'] = self.getPercent()
		s['timeSpend'] = self.getTimeSpend()
		s['timeLeft'] = self.getTimeLeft()
		s['speed'] = self.getSpeed()
		return s

# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Observers                                                                   =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class MessageObserver(object):
	def __init__(self):
		pass
	
	def messageChanged(self, subject, message):
		pass

class ChoiceObserver(MessageObserver):
	def __init__(self):
		MessageObserver.__init__(self)
	
	def selectedIndexChanged(self, subject, selectedIndex):
		pass
	
	def choicesChanged(self, subject, choices):
		pass

class ProgressObserver(MessageObserver):
	def __init__(self):
		pass
	
	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		pass

class SubjectsObserver(ChoiceObserver, ProgressObserver):
	def __init__(self):
		self._subjects = []
	
	def setSubjects(self, subjects):
		for subject in self._subjects:
			subject.detachObserver(self)
		self._subjects = subjects
		for subject in self._subjects:
			subject.attachObserver(self)
		self.subjectsChanged(self._subjects)
	
	def addSubject(self, subject):
		if not subject in self._subjects:
			self._subjects.append(subject)
			subject.attachObserver(self)
		self.subjectsChanged(self._subjects)
	
	def removeSubject(self, subject):
		if subject in self._subjects:
			subject.detachObserver(self)
			self._subjects.remove(subject)
		self.subjectsChanged(self._subjects)
	
	def getSubjects(self):
		return self._subjects
	
	def subjectsChanged(self, subjects):
		pass


# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Subject proxies                                                             =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class MessageSubjectProxy(ProgressSubject, ProgressObserver, ChoiceSubject, ChoiceObserver):
	def __init__(self, id, type='', title='', **args):
		ChoiceSubject.__init__(self, id, type, title, **args)
		ChoiceObserver.__init__(self)
		ProgressSubject.__init__(self, id, type, title, **args)
		ProgressObserver.__init__(self)
		self._fireAlways = True
	
	def messageChanged(self, subject, message):
		self.setMessage(message, severity = subject.getSeverity())
	
	def selectedIndexChanged(self, subject, selectedIndex):
		self.setSelectedIndex(selectedIndex)
	
	def choicesChanged(self, subject, choices):
		self.setChoices(choices)
	
	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		self._end = subject.getEnd()
		self.setState(state)
	
class ChoiceSubjectProxy(MessageSubjectProxy):
	def __init__(self, id, type='', title='', **args):
		MessageSubjectProxy.__init__(self, id, type, title, **args)

class ProgressSubjectProxy(MessageSubjectProxy):
	def __init__(self, id, type='', title='', **args):
		MessageSubjectProxy.__init__(self, id, type, title, **args)
	
	
	

# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Notification server                                                         =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

class NotificationServerProtocol(LineReceiver):
	def connectionMade(self):
		self.factory.connectionMade(self)
		
	def connectionLost(self, reason):
		self.factory.connectionLost(self, reason)
	
	def lineReceived(self, line):
		self.factory.rpc(self, line)

class NotificationServerFactory(ServerFactory, SubjectsObserver):
	protocol = NotificationServerProtocol
	
	def __init__(self):
		self.clients = []
		self._subjects = []
		self._rpcs = {}
	
	def connectionMade(self, client):
		logger.info("client connection made")
		self.clients.append(client)
		self.subjectsChanged(self.getSubjects())
		
	def connectionLost(self, client, reason):
		logger.info("client connection lost")
		self.clients.remove(client)
		
	def rpc(self, client, line):
		logger.info("received line %s" % line)
		id = None
		try:
			if hasattr(json, 'loads'):
				# python 2.6 json module
				rpc = json.loads( line )
			else:
				rpc = json.read( line )
			method = rpc['method']
			id = rpc['id']
			params = rpc['params']
			
			if (method == 'setSelectedIndex'):
				subjectId = params[0]
				selectedIndex = params[1]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (subject.getId() != subjectId):
						continue
					result = subject.setSelectedIndex(selectedIndex)
					break
			
			elif (method == 'selectChoice'):
				logger.info("selectChoice(%s)" % str(params)[1:-1])
				subjectId = params[0]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (subject.getId() != subjectId):
						continue
					result = subject.selectChoice()
					break
			
			else:
				raise ValueError("unknown method '%s'" % method)
		except Exception, e:
			logger.error("Failed to execute rpc: %s" % e)
	
	def messageChanged(self, subject, message):
		if not subject in self.getSubjects():
			logger.info("Unknown subject %s passed to messageChanged, automatically adding subject" % subject)
			self.addSubject(subject)
		logger.debug("messageChanged: subject id '%s', message '%s'" % (subject.getId(), message))
		self.notify( name = "messageChanged", params = [subject.serializable(), message] )
	
	def selectedIndexChanged(self, subject, selectedIndex):
		if not subject in self.getSubjects():
			logger.info("Unknown subject %s passed to selectedIndexChanged, automatically adding subject" % subject)
			self.addSubject(subject)
		logger.debug("selectedIndexChanged: subject id '%s', selectedIndex '%s'" % (subject.getId(), selectedIndex))
		self.notify( name = "selectedIndexChanged", params = [ subject.serializable(), selectedIndex ] )
	
	def choicesChanged(self, subject, choices):
		if not subject in self.getSubjects():
			logger.info("Unknown subject %s passed to choicesChanged, automatically adding subject" % subject)
			self.addSubject(subject)
		logger.debug("choicesChanged: subject id '%s', choices %s" % (subject.getId(), choices))
		self.notify( name = "choicesChanged", params = [ subject.serializable(), choices ] )
	
	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		if not subject in self.getSubjects():
			logger.info("Unknown subject %s passed to progressChanged, automatically adding subject" % subject)
			self.addSubject(subject)
		logger.debug("progressChanged: subject id '%s', state %s, percent %s, timeSpend %s, timeLeft %s, speed %s" \
			% (subject.getId(), state, percent, timeSpend, timeLeft, speed))
		self.notify( name = "progressChanged", params = [ subject.serializable(), state, percent, timeSpend, timeLeft, speed ] )
	
	def subjectsChanged(self, subjects):
		logger.debug("subjectsChanged: subjects %s" % subjects)
		param = []
		for subject in subjects:
			param.append(subject.serializable())
		self.notify( name = "subjectsChanged", params = [ param ] )
	
	def notify(self, name, params, clients = []):
		if not type(params) is list:
			params = [ params ]
		if not clients:
			clients = self.clients
		if not type(clients) is list:
			clients = [ clients ]
		if not clients:
			logger.info("cannot send notification '%s', no client connected" % name)
			return
		logger.info("sending notification '%s' to clients" % name)
		for client in self.clients:
			# json-rpc: notifications have id null
			if hasattr(json, 'dumps'):
				# python 2.6 json module
				client.sendLine( json.dumps( {"id": None, "method": name, "params": params } ) )
			else:
				client.sendLine( json.write( {"id": None, "method": name, "params": params } ) )


class NotificationServer(threading.Thread, SubjectsObserver):
	def __init__(self, address, port, subjects):
		threading.Thread.__init__(self)
		self._address = address
		if not self._address:
			self._address = '0.0.0.0'
		self._port = int(port)
		self._factory = NotificationServerFactory()
		self._factory.setSubjects(subjects)
	
	def getFactory(self):
		return self._factory
	
	def getObserver(self):
		return self._factory
	
	def setSubjects(self, subjects):
		return self._factory.setSubjects(subjects)
		
	def addSubject(self, subject):
		return self._factory.addSubject(subject)
		
	def removeSubject(self, subject):
		return self._factory.removeSubject(subject)
	
	def getSubjects(self):
		return self._factory.getSubjects()
	
	def run(self):
		logger.info("Notification server starting")
		try:
			if (self._address == '0.0.0.0'):
				reactor.listenTCP(self._port, self._factory)
			else:
				reactor.listenTCP(self._port, self._factory, interface = self._address)
			
			if not reactor.running:
				reactor.run(installSignalHandlers=0)
		except Exception, e:
			logger.logException(e)
	
	def stop(self):
		if reactor and reactor.running:
			try:
				reactor.stop()
			except Exception, e:
				logger.error("Failed to stop reactor: %s" % e)


# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Notification client                                                         =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class NotificationClientProtocol(LineReceiver):
	def connectionMade(self):
		self.factory.connectionMade(self)
		
	def lineReceived(self, line):
		self.factory.receive(line)
		
	def connectionLost(self, reason):
		self.factory.connectionLost(reason)

class NotificationClientFactory(ClientFactory):
	protocol = NotificationClientProtocol
	_client = None
	_observer = None
	
	def __init__(self, observer):
		self._observer = observer
		self._rpcs = {}
		self._timeout = 5
	
	#def clientConnectionFailed(self, connector, reason):
	#	logger.error("client connection failed")
	
	#def clientConnectionLost(self, connector, reason):
	#	pass
	
	def connectionLost(self, reason):
		logger.info("server connection lost")
	
	def connectionMade(self, client):
		logger.info("server connection made")
		self._client = client
	
	def isReady(self):
		return (self._client != None)
	
	def sendLine(self, line):
		logger.debug("sending line '%s'" % line)
		self._client.sendLine(line)
	
	def receive(self, rpc):
		logger.debug("received rpc '%s'" % rpc)
		id = None
		try:
			if hasattr(json, 'loads'):
				# python 2.6 json module
				rpc = json.loads( rpc )
			else:
				rpc = json.read( rpc )
			id = rpc['id']
			if id:
				# Received rpc answer
				self._rpcs[id] = rpc
			else:
				# Notification
				method = rpc['method']
				params = rpc['params']
				logger.info( "eval self._observer.%s(%s)" % (method, str(params)[1:-1]) )
				eval( "self._observer.%s(%s)" % (method, str(params)[1:-1]) )
		except Exception, e:
			logger.error(e)
	
	def execute(self, method, params):
		logger.debug("executing method '%s', params %s" % (method, params))
		if not params:
			params = []
		if not type(params) in (list, tuple):
			params = [ params ]
		
		timeout = 0
		while not self.isReady() and (timeout < self._timeout):
			time.sleep(0.1)
			timeout += 0.1
		if (timeout >= self._timeout):
			raise Exception("execute timed out after %d seconds" % self._timeout)
		
		rpc = {'id': None, "method": method, "params": params }
		if hasattr(json, 'dumps'):
			# python 2.6 json module
			self.sendLine( json.dumps( rpc ) )
		else:
			self.sendLine( json.write( rpc ) )

class NotificationClient(threading.Thread):
	def __init__(self, address, port, observer):
		threading.Thread.__init__(self)
		self._address = address
		self._port = port
		self._observer = observer
		self._factory = NotificationClientFactory(self._observer)
	
	def getFactory(self):
		return self._factory
	
	def run(self):
		logger.info("Notification client starting")
		try:
			logger.info("Connecting to %s:%s" % (self._address, self._port))
			reactor.connectTCP(self._address, self._port, self._factory)
			if not reactor.running:
				reactor.run(installSignalHandlers=0)
		except Exception, e:
			logger.logException(e)
	
	def stop(self):
		if reactor and reactor.running:
			reactor.stop()
	
	def setSelectedIndex(self, subjectId, choiceIndex):
		self._factory.execute(method = 'setSelectedIndex', params = [ subjectId, choiceIndex ])
	
	def selectChoice(self, subjectId):
		self._factory.execute(method = 'selectChoice', params = [ subjectId ])



# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Repositories                                                                =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class RepositoryError(Exception):
	ExceptionShortDescription = "Repository error"
	
	def __init__(self, message = None):
		self.message = message
	
	def __str__(self):
		#return "<%s: %s>" % (self.__class__.__name__, self.message)
		return str(self.message)
	
	def complete_message(self):
		if self.message:
			return "%s: %s" % (self.ExceptionShortDescription, self.message)
		else:
			return "%s" % self.ExceptionShortDescription

def getRepository(url, username='', password='', maxBandwidth=0):
	if re.search('^file://', url):
		return FileRepository(url, username, password, maxBandwidth)
	if re.search('^webdavs*://', url):
		return WebDAVRepository(url, username, password, maxBandwidth)
	raise RepositoryError("Repository url '%s' not supported" % url)
	
class Repository:
	def __init__(self, url, username='', password='', maxBandwidth=0):
		''' maxBandwidth in bit/s'''
		self._url = url
		self._username = username
		self._password = password
		self._path = ''
		self._maxBandwidth = maxBandwidth
		if self._maxBandwidth:
			self._maxBandwidth = self._maxBandwidth/8
			if (self._maxBandwidth < 1):
				self._maxBandwidth = 1
		
	def __str__(self):
		return '<%s %s>' % (self.__class__.__name__, self._url)
		
	def _transfer(self, src, dst, progressSubject=None):
		buf = True
		waitTime = 0.0
		bufferSize = 64*1024
		if self._maxBandwidth:
			if (self._maxBandwidth < bufferSize*2):
				bufferSize = int(self._maxBandwidth/2)
			if (bufferSize < 512):
				bufferSize = 512
		
		while(buf):
			t1 = time.time()
			buf = src.read(bufferSize)
			read = len(buf)
			if (read > 0):
				if isinstance(dst, HTTPConnection) or isinstance(dst, HTTPSConnection):
					dst.send(buf)
				else:
					dst.write(buf)
				time.sleep(waitTime)
				t2 = time.time()
				dt = t2-t1
				if self._maxBandwidth and (self._maxBandwidth > 0) and (dt > 0):
					speed = int(read/dt)
					wt = 0
					if (speed > 0) and (speed > self._maxBandwidth):
						wt = ( (float(speed)/float(self._maxBandwidth)) ** (0.1) )
					elif (speed > 0) and (speed < self._maxBandwidth):
						wt = ( (float(self._maxBandwidth)/float(speed)) ** (0.1) )
					if wt:
						while (wt > 1):
							wt -= 1
						if (wt > 0.2):
							wt = 0.2
						if (speed > self._maxBandwidth):
							waitTime += wt
						else:
							waitTime -= wt
						if (waitTime < 0):
							waitTime = 0.00001
				if progressSubject:
					progressSubject.addToState(read)
	
	def setMaxBandwidth(self, maxBandwidth):
		''' maxBandwidth in bit/s'''
		self._maxBandwidth = maxBandwidth
		if self._maxBandwidth:
			self._maxBandwidth = int(self._maxBandwidth/8)
			if (self._maxBandwidth < 1):
				self._maxBandwidth = 1
	
	def content(self, destination=''):
		raise RepositoryError("Not implemented")
	
	def fileInfo(self, destination):
		raise RepositoryError("Not implemented")
	
	def upload(self, source, destination):
		raise RepositoryError("Not implemented")
	
	def download(self, source, destination, progressObserver=None):
		raise RepositoryError("Not implemented")
	
	def delete(self, destination):
		raise RepositoryError("Not implemented")
	
	def makeDirectory(self, destination):
		raise RepositoryError("Not implemented")
	
class FileRepository(Repository):
	def __init__(self, url, username='', password='', maxBandwidth=0):
		Repository.__init__(self, url, username, password, maxBandwidth)
		
		match = re.search('^file://(/[^/]+.*)$', self._url)
		if not match:
			raise RepositoryError("Bad url: '%s'" % self._url)
		self._path = match.group(1)
		
	def _absolutePath(self, destination):
		if destination.startswith('/'):
			destination = destination[1:]
		return self._path + '/' + destination
	
	def content(self, destination=''):
		content = []
		destination = self._absolutePath(destination)
		try:
			for e in os.listdir(destination):
				fs = os.stat(os.path.join(destination, e))
				type = 'file'
				if os.path.isdir(os.path.join(destination, e)):
					type = 'dir'
				content.append({
					'name': e,
					'size': fs[stat.ST_SIZE],
					'type': type })
		except:
			raise RepositoryError("Not a directory: '%s'" % destination)
		return content
		
	def fileInfo(self, destination):
		destination = self._absolutePath(destination)
		info = {}
		try:
			fs = os.stat(destination)
			info['size'] = fs[stat.ST_SIZE]
			return info
		except Exception, e:
			raise RepositoryError("Failed to get file info for '%s': %s" % (destination, e))
	
	def download(self, source, destination, progressObserver=None):
		
		size = self.fileInfo(source)['size']
		source = self._absolutePath(source)
		
		logger.debug("Length of binary data to download: %d" % size)
		
		progressSubject = ProgressSubject(id='download', end=size)
		progressSubject.setMessage( os.path.basename(source) + ' >> ' + self._path )
		
		if progressObserver: progressSubject.attachObserver(progressObserver)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			dst = open(destination, 'wb')
			self._transfer(src, dst, progressSubject)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError("Failed to download '%s' to '%s': %s" \
						% (source, destination, e))
	
	def upload(self, source, destination, progressObserver=None):
		
		destination = self._absolutePath(destination)
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug("Length of binary data to upload: %d" % size)
		
		progressSubject = ProgressSubject(id='upload', end=size)
		progressSubject.setMessage( os.path.basename(source) + ' >> ' + self._path )
		
		if progressObserver: progressSubject.attachObserver(progressObserver)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			dst = open(destination, 'wb')
			self._transfer(src, dst, progressSubject)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError("Failed to upload '%s' to '%s': %s" \
						% (source, destination, e))
	
	def delete(self, source, destination):
		destination = self._absolutePath(destination)
		os.unlink(destination)
	
	def makeDirectory(self, destination):
		destination = self._absolutePath(destination)
		if not os.path.isdir(destination):
			os.mkdir(destination)
		
	
class WebDAVRepository(Repository):
	def __init__(self, url, username='', password='', maxBandwidth=0):
		Repository.__init__(self, url, username, password, maxBandwidth)
		
		match = re.search('^(webdavs*)://([^:]+:*[^:]+):(\d+)(/.*)$', self._url)
		if not match:
			raise RepositoryError("Bad url: '%s'" % self._url)
		
		self._protocol = match.group(1)
		self._host = match.group(2)
		if (self._host.find('@') != -1):
			(username, self._host) = self._host.split('@', 1)
			password = ''
			if (username.find(':') != -1):
				(username, password) = username.split(':', 1)
			if not self._username and username: self._username = username
			if not self._password and password: self._password = password
		self._port = int(match.group(3))
		self._path = match.group(4)
		self._auth = 'Basic '+ base64.encodestring( urllib.unquote(self._username + ':' + self._password) ).strip()
		self._connection = None
		self._cookie = ''
		
	def _absolutePath(self, destination):
		if destination.startswith('/'):
			destination = destination[1:]
		return self._path + '/' + destination
	
	def _connect(self):
		logger.debug("WebDAVRepository _connect()")
		if self._protocol.endswith('s'):
			self._connection = HTTPSConnection(self._host, self._port)
		else:
			self._connection = HTTPConnection(self._host, self._port)
		
		self._connection.putrequest('PROPFIND', urllib.quote(self._absolutePath('/')))
		if self._cookie:
			# Add cookie to header
			self._connection.putheader('cookie', self._cookie)
		self._connection.putheader('authorization', self._auth)
		self._connection.putheader('depth', '0')
		self._connection.endheaders()
		
		response = self._connection.getresponse()
		if (response.status != responsecode.MULTI_STATUS):
			raise RepositoryError("Failed to connect to '%s://%s:%s': %s" \
				% (self._protocol, self._host, self._port, response.status))
		# We have to read the response!
		response.read()
		
		# Get cookie from header
		cookie = response.getheader('set-cookie', None)
		if cookie:
			# Store cookie 
			self._cookie = cookie.split(';')[0].strip()
	
	def _getContent(self, destination=''):
		content = []
		if not destination.endswith('/'):
			destination += '/'
		
		self._connect()
		
		self._connection.putrequest('PROPFIND', urllib.quote(destination))
		self._connection.putheader('depth', '1')
		if self._cookie:
			# Add cookie to header
			self._connection.putheader('cookie', self._cookie)
		self._connection.putheader('authorization', self._auth)
		self._connection.endheaders()
		
		response = self._connection.getresponse()
		if (response.status != responsecode.MULTI_STATUS):
			raise RepositoryError("Failed to list dir '%s': %s" \
				% (destination, response.status))
		
		msr = davxml.WebDAVDocument.fromString(response.read())
		if not msr.root_element.children[0].childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer).childOfType(davxml.ResourceType).children:
			raise RepositoryError("Not a directory: '%s'" % destination)
		for child in msr.root_element.children[1:]:
			#<prop>
			#	<resourcetype/>
			#	<getetag>W/"1737A0-373-47DFF2F3"</getetag>
			#	<getcontenttype>text/plain</getcontenttype>
			#	<getcontentlength>883</getcontentlength>
			#	<getlastmodified>Tue, 18 Mar 2008 17:50:59 GMT</getlastmodified>
			#	<creationdate>2008-03-18T17:50:59Z</creationdate>
			#	<displayname>connect.vnc</displayname>
			#</prop>
			pContainer = child.childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer)
			info = { 'size': long(0), 'type': 'file' }
			info['name'] = str(pContainer.childOfType(davxml.DisplayName))
			if (str(pContainer.childOfType(davxml.GETContentLength)) != 'None'):
				info['size'] = long( str(pContainer.childOfType(davxml.GETContentLength)) )
			if pContainer.childOfType(davxml.ResourceType).children:
				info['type'] = 'dir'
			
			content.append(info)
		
		return content
	
	def content(self, destination=''):
		result = []
		destination = self._absolutePath(destination)
		#for c in self._getContent(destination):
		#	result.append( c['name'] )
		return self._getContent(destination)
		return result
	
	def fileInfo(self, destination):
		info = {}
		try:
			path = self._absolutePath('/'.join(destination.split('/')[:-1]))
			name = destination.split('/')[-1]
			for c in self._getContent(path):
				if (c['name'] == name):
					info['size'] = c['size']
					return info
			raise Exception('file not found')
		except Exception, e:
			raise RepositoryError("Failed to get file info for '%s': %s" % (destination, e))
	
	def download(self, source, destination, progressObserver=None):
		
		size = self.fileInfo(source)['size']
		source = self._absolutePath(source)
		
		logger.debug("Length of binary data to download: %d" % size)
		
		progressSubject = ProgressSubject(id='upload', end=size)
		progressSubject.setMessage( os.path.basename(source) + ' >> ' + self._path )
		
		if progressObserver: progressSubject.attachObserver(progressObserver)
		
		dst = None
		try:
			self._connect()
			self._connection.putrequest('GET', urllib.quote(source))
			if self._cookie:
				# Add cookie to header
				self._connection.putheader('cookie', self._cookie)
			self._connection.putheader('authorization', self._auth)
			self._connection.endheaders()
			
			response = self._connection.getresponse()
			if (response.status != responsecode.OK):
				raise Exception(response.status)
			
			dst = open(destination, 'wb')
			self._transfer(response, dst, progressSubject)
			dst.close()
			
		except Exception, e:
			logger.logException(e)
			#if self._connection: self._connection.close()
			if dst: dst.close()
			raise RepositoryError("Failed to download '%s' to '%s': %s" \
						% (source, destination, e))
		logger.debug2("WebDAV download done")
	
	def upload(self, source, destination, progressObserver=None):
		destination = self._absolutePath(destination)
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug("Length of binary data to upload: %d" % size)
		
		progressSubject = ProgressSubject(id='upload', end=size)
		progressSubject.setMessage( os.path.basename(source) + ' >> ' + self._path )
		
		if progressObserver: progressSubject.attachObserver(progressObserver)
		
		src = None
		try:
			self._connect()
			self._connection.putrequest('PUT', urllib.quote(destination))
			if self._cookie:
				# Add cookie to header
				self._connection.putheader('cookie', self._cookie)
			self._connection.putheader('authorization', self._auth)
			self._connection.putheader('content-length', size)
			self._connection.endheaders()
			
			src = open(source, 'rb')
			self._transfer(src, self._connection, progressSubject)
			src.close()
			
			response = self._connection.getresponse()
			if (response.status != responsecode.CREATED) and (response.status != responsecode.NO_CONTENT):
				raise Exception(response.status)
			# We have to read the response!
			response.read()
		except Exception, e:
			logger.logException(e)
			#if self._connection: self._connection.close()
			if src: src.close()
			raise RepositoryError("Failed to upload '%s' to '%s': %s" \
						% (source, destination, e))
		logger.debug2("WebDAV upload done")
	
	def delete(self, destination):
		self._connect()
		
		destination = self._absolutePath(destination)
		
		self._connection.putrequest('DELETE', urllib.quote(destination))
		if self._cookie:
			# Add cookie to header
			self._connection.putheader('cookie', self._cookie)
		self._connection.putheader('authorization', self._auth)
		self._connection.endheaders()
		
		response = self._connection.getresponse()
		if (response.status != responsecode.NO_CONTENT):
			raise RepositoryError("Failed to delete '%s': %s" \
				% (destination, response.status))
		# We have to read the response!
		response.read()


class DepotToLocalDirectorySychronizer(object):
	def __init__(self, sourceDepot, destinationDirectory, productIds=[], maxBandwidth=0):
		self._sourceDepot = sourceDepot
		self._destinationDirectory = destinationDirectory
		self._productIds = productIds
		self._maxBandwidth = maxBandwidth
		if not os.path.isdir(self._destinationDirectory):
			os.mkdir(self._destinationDirectory)
	
	def _md5sum(self, filename):
		f = open(filename, 'rb')
		m = md5()
		while True:
			d = f.read(8096)
			if not d:
				break
			m.update(d)
		f.close()
		return m.hexdigest()
	
	def _synchronizeDirectories(self, source, destination, progressSubject=None):
		logger.debug("   Syncing directory %s to %s" % (source, destination))
		if not os.path.isdir(destination):
			os.mkdir(destination)
		
		for f in os.listdir(destination):
			relSource = (source + '/' + f).split('/', 1)[1]
			if (relSource == self._productId + '.files'):
				continue
			if self._fileInfo.has_key(relSource):
				continue
			
			logger.info("      Deleting '%s'" % relSource)
			path = os.path.join(destination, f)
			if os.path.isdir(path) and not os.path.islink(path):
				shutil.rmtree(path)
			else:
				os.remove(path)
			
		for f in self._sourceDepot.content(source):
			(s, d) = (source + '/' + f['name'], os.path.join(destination, f['name']))
			relSource = s.split('/', 1)[1]
			if not self._fileInfo.has_key(relSource):
				continue
			if (f['type'] == 'dir'):
				self._synchronizeDirectories(s, d, progressSubject)
			else:
				bytes = 0
				logger.debug("      Syncing %s: %s" % (relSource, self._fileInfo[relSource]))
				if (self._fileInfo[relSource]['type'] == 'l'):
					self._linkFiles[relSource] = self._fileInfo[relSource]['target']
					continue
				elif (self._fileInfo[relSource]['type'] == 'f'):
					bytes = int(self._fileInfo[relSource]['size'])
					if os.path.exists(d):
						md5s = self._md5sum(d)
						logger.debug("      Destination file '%s' already exists (size: %s, md5sum: %s)" % (d, bytes, md5s))
						if (os.path.getsize(d) == bytes) and (md5s == self._fileInfo[relSource]['md5sum']):
							if progressSubject: progressSubject.addToState(bytes)
							continue
				logger.info("      Downloading file '%s'" % f['name'])
				if progressSubject: progressSubject.setMessage( _("Downloading file '%s'") % f['name'] )
				self._sourceDepot.download(s, d)
				if progressSubject: progressSubject.addToState(bytes)
				
	def synchronize(self, productProgressObserver=None, overallProgressObserver=None):
		
		if not self._productIds:
			logger.info("Getting product dirs of depot '%s'" % self._sourceDepot)
			for c in self._sourceDepot.content():
				self._productIds.append(c['name'])
		
		overallProgressSubject = ProgressSubject(id = 'sync_products_overall', type = 'product_sync', end = len(self._productIds), fireAlways = True)
		overallProgressSubject.setMessage( _('Synchronizing products') )
		if overallProgressObserver: overallProgressSubject.attachObserver(overallProgressObserver)
		
		for self._productId in self._productIds:
			productProgressSubject = ProgressSubject(id = 'sync_product_' + self._productId, type = 'product_sync', fireAlways = True)
			productProgressSubject.setMessage( _("Synchronizing product %s") % self._productId )
			if productProgressObserver: productProgressSubject.attachObserver(productProgressObserver)
			
			self._linkFiles = {}
			logger.notice("Syncing product %s of depot %s with local directory %s" \
					% (self._productId, self._sourceDepot, self._destinationDirectory))
			
			productDestinationDirectory = os.path.join(self._destinationDirectory, self._productId)
			if not os.path.isdir(productDestinationDirectory):
				os.mkdir(productDestinationDirectory)
			
			logger.info("Downloading file info file")
			from OPSI import Product
			fileInfoFile = os.path.join(productDestinationDirectory, '%s.files' % self._productId)
			self._sourceDepot.download('%s/%s.files' % (self._productId, self._productId), fileInfoFile)
			self._fileInfo = Product.readFileInfoFile(fileInfoFile)
			
			bytes = 0
			for value in self._fileInfo.values():
				if value.has_key('size'):
					bytes += int(value['size'])
			productProgressSubject.setMessage( _("Synchronizing product %s (%.2f kByte)") % (self._productId, (bytes/1024)) )
			productProgressSubject.setEnd(bytes)
			
			self._synchronizeDirectories(self._productId, productDestinationDirectory, productProgressSubject)
			
			fs = self._linkFiles.keys()
			fs.sort()
			for f in fs:
				t = self._linkFiles[f]
				cwd = os.getcwd()
				os.chdir(productDestinationDirectory)
				try:
					if os.path.exists(f):
						if os.path.isdir(f) and not os.path.islink(f):
							shutil.rmtree(f)
						else:
							os.remove(f)
					if (os.name == 'posix'):
						parts = len(f.split('/'))
						parts -= len(t.split('/'))
						for i in range(parts):
							t = os.path.join('..', t)
						logger.info("Symlink '%s' to '%s'" % (f, t))
						os.symlink(t, f)
					else:
						t = os.path.join(productDestinationDirectory, t)
						f = os.path.join(productDestinationDirectory, f)
						logger.info("Copying '%s' to '%s'" % (t, f))
						if os.path.isdir(t):
							shutil.copytree(t, f)
						else:
							shutil.copyfile(t, f)
				finally:
					os.chdir(cwd)
			overallProgressSubject.addToState(1)
			if productProgressObserver: productProgressSubject.detachObserver(productProgressObserver)
		
		if overallProgressObserver: overallProgressSubject.detachObserver(overallProgressObserver)







