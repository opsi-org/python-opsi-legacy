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

__version__ = '0.1.1'

# Imports
import json, threading
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ServerFactory, ClientFactory
from twisted.internet import reactor, ssl

# OPSI imports
from Logger import *

# Get Logger instance
logger = Logger()


import threading
import ctypes
 
 
def _async_raise(tid, excobj):
	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(excobj))
	if (res == 0):
		raise ValueError("nonexistent thread id")
	elif (res > 1):
		# """if it returns a number greater than one, you're in trouble, 
		# and you should call it again with exc=NULL to revert the effect"""
		ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
		raise SystemError("PyThreadState_SetAsyncExc failed")
 
class KillableThread(threading.Thread):
	def raise_exc(self, excobj):
		assert self.isAlive(), "thread must be started"
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
	def __init__(self, id):
		self._id = id
		self._observers = []
	
	def getId(self):
		return self._id
	
	def getType(self):
		return self.__class__.__name__
	
	def attachObserver(self, observer):
		if not observer in self._observers:
			self._observers.append(observer)
	
	def detachObserver(self, observer):
		if observer in self._observers:
			self._observers.remove(observer)
	
	def serializable(self):
		return { "id": self.getId(), "type": self.getType() }
	
class MessageSubject(Subject):
	def __init__(self, id):
		Subject.__init__(self, id)
		self._message = ""
	
	def setMessage(self, message):
		self._message = str(message)
		self._notifyMessageChanged(message)
	
	def getMessage(self):
		return self._message
	
	def _notifyMessageChanged(self, message):
		for o in self._observers:
			o.messageChanged(self, message)
	
	def serializable(self):
		s = Subject.serializable(self)
		s['message'] = self.getMessage()
		return s

class ChoiceSubject(MessageSubject):
	def __init__(self, id):
		MessageSubject.__init__(self, id)
		self._message = ""
		self._choices = []
		self._selectedIndex = -1
		self._callbacks = []
		
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
		self._notifyChoicesChanged(choices)
	
	def getChoices(self):
		return self._choices
	
	def selectChoice(self):
		logger.info("selectChoice")
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
	
class NotificationObserver(ChoiceObserver):
	def __init__(self):
		pass
	
	def subjectsChanged(self, subjects):
		pass
	
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Notification server                                                         =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

class NotificationServerProtocol(LineReceiver):
	def connectionMade(self):
		logger.info("Notification server: client connection made")
		self.factory.connectionMade(self)
		
	def connectionLost(self, reason):
		logger.info("Notification server: client connection lost")
		self.factory.connectionLost(self, reason)
	
	def lineReceived(self, line):
		logger.info("Notification server: received line %s" % line)
		self.factory.rpc(self, line)

class NotificationServerFactory(ServerFactory, NotificationObserver):
	protocol = NotificationServerProtocol
	
	def __init__(self):
		self.clients = []
		self._subjects = []
		self._rpcs = {}
	
	def setSubjects(self, subjects):
		for subject in self._subjects:
			subject.detachObserver(self)
		self._subjects = subjects
		for subject in self._subjects:
			subject.attachObserver(self)
		self.subjectsChanged(subjects)
	
	def getSubjects(self):
		return self._subjects
	
	def connectionMade(self, client):
		self.clients.append(client)
		self.subjectsChanged(self.getSubjects())
		
	def connectionLost(self, client, reason):
		self.clients.remove(client)
		
	def rpc(self, client, line):
		id = None
		try:
			rpc = json.read( line )
			method = rpc['method']
			id = rpc['id']
			params = rpc['params']
			#if (method == 'getSubjects'):
			#	subjects = []
			#	for subject in self.getSubjects():
			#		subjects.append(subject.serializable())
			#	result = json.write( {"id": id, "error": None, "result": subjects } )
			#	logger.info("Sending result to client '%s'" % result)
			#	client.sendLine(result)
			if (method == 'setSelectedIndex'):
				subjectId = params[0]
				selectedIndex = params[1]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (subject.getId() != subjectId):
						continue
					result = subject.setSelectedIndex(selectedIndex)
					#result = json.write( {"id": id, "error": None, "result": result } )
					#logger.info("Sending result to client '%s'" % result)
					#client.sendLine(result)
					break
			elif (method == 'selectChoice'):
				logger.info("Notification server: selectChoice(%s)" % str(params)[1:-1])
				subjectId = params[0]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (subject.getId() != subjectId):
						continue
					result = subject.selectChoice()
					#result = json.write( {"id": id, "error": None, "result": result } )
					#logger.info("Sending result to client '%s' method was '%s'" % (result, method))
					#client.sendLine(result)
					break
			else:
				raise ValueError("Notification server: unkown method '%s'" % method)
		except Exception, e:
			logger.error("Failed to execute rpc: %s" % e)
			#error = json.write( {"id": None, "error": str(e), "result": None } )
			#logger.info("Sending error to client '%s'" % error)
			#client.sendLine(error)
	
	def messageChanged(self, subject, message):
		logger.debug("Notification server: messageChanged subject: %s" % subject)
		self.notify( name = "messageChanged", params = [subject.serializable(), message] )
	
	def selectedIndexChanged(self, subject, selectedIndex):
		self.notify( name = "selectedIndexChanged", params = [ subject.serializable(), selectedIndex ] )
	
	def choicesChanged(self, subject, choices):
		self.notify( name = "choicesChanged", params = [ subject.serializable(), choices ] )
	
	def subjectsChanged(self, subjects):
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
			return
		logger.info("Notification server: Sending notification '%s' to clients" % name)
		for client in self.clients:
			# json-rpc: notifications have id null
			client.sendLine( json.write( {"id": None, "method": name, "params": params } ) )


class NotificationServer(threading.Thread):
	def __init__(self, address, port, subjects):
		threading.Thread.__init__(self)
		self._address = address
		if not self._address:
			self._address = '0.0.0.0'
		self._port = int(port)
		self._subjects = subjects
		self._factory = NotificationServerFactory()
		self._factory.setSubjects(self._subjects)
	
	def addSubject(self, subject):
		if not subject in self._subjects:
			self._subjects.append(subject)
		self._factory.setSubjects(self._subjects)
		
	def removeSubject(self, subject):
		if subject in self._subjects:
			self._subjects.remove(subject)
		self._factory.setSubjects(self._subjects)
		
	def run(self):
		logger.info("Notification server: starting")
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
			reactor.stop()


# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Notification client                                                         =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
class NotificationClientProtocol(LineReceiver):
	def connectionMade(self):
		self.factory.clientReady(self)
		
	def lineReceived(self, line):
		logger.info("Notification client: received line %s" % line)
		self.factory.receive(line)
		
	def connectionLost(self, reason):
		#reactor.stop()
		pass

class NotificationClientFactory(ClientFactory):
	protocol = NotificationClientProtocol
	_client = None
	_observer = None
	
	def __init__(self, observer):
		self._observer = observer
		self._rpcs = {}
		self._timeout = 5
	
	def clientConnectionFailed(self, connector, reason):
		#reactor.stop()
		pass
	
	def clientConnectionLost(self, connector, reason):
		#reactor.stop()
		pass
	
	def clientReady(self, client):
		logger.info("Notification client:client ready")
		self._client = client
	
	def isReady(self):
		return (self._client != None)
	
	def sendLine(self, line):
		self._client.sendLine(line)
	
	def receive(self, rpc):
		id = None
		try:
			rpc = json.read( rpc )
			id = rpc['id']
			if id:
				# Received rpc answer
				self._rpcs[id] = rpc
			else:
				# Notification
				method = rpc['method']
				params = rpc['params']
				logger.info( "Notification client: eval self._observer.%s(%s)" % (method, str(params)[1:-1]) )
				eval( "self._observer.%s(%s)" % (method, str(params)[1:-1]) )
				
		except Exception, e:
			logger.error(e)
	
	def execute(self, method, params):
		if not params:
			params = []
		if not type(params) in (list, tuple):
			params = [ params ]
		
		timeout = 0
		while not self.isReady() and (timeout < self._timeout):
			time.sleep(0.1)
			timeout += 0.1
		if (timeout >= self._timeout):
			raise Exception("Notification client: timed out after %d seconds" % self._timeout)
		
		id = None
		#while id in self._rpcs.keys():
		#	id += 1
		#
		rpc = {'id': id, "method": method, "params": params }
		#self._rpcs[id] = {}
		logger.debug("Notification client: executing rpc: %s" % rpc)
		self.sendLine( json.write( rpc ) )
		#while not self._rpcs[id]:
		#	time.sleep(0.1)
		#error = self._rpcs[id]['error']
		#result = self._rpcs[id]['result']
		#del self._rpcs[id]
		#if error:
		#	raise Exception(self._rpcs[id]['error'])
		#logger.info("Got result: %s" % result)
		#return result

class NotificationClient(threading.Thread):
	def __init__(self, address, port, observer):
		threading.Thread.__init__(self)
		self._address = address
		self._port = port
		self._observer = observer
		self._factory = NotificationClientFactory(self._observer)
		#self._timeout = 5
	
	def run(self):
		logger.info("Notification client: starting")
		try:
			# TODO: address
			#ccf = ssl.ClientContextFactory()
			#ccf.method = SSL.TLSv1_METHOD
			#reactor.connectSSL(self._address, self._port, self._factory, ccf)
			reactor.connectTCP(self._address, self._port, self._factory)
			if not reactor.running:
				reactor.run(installSignalHandlers=0)
		except Exception, e:
			logger.logException(e)
	
	def stop(self):
		if reactor and reactor.running:
			reactor.stop()
	
	
	#def getSubjects(self):
	#	timeout = 0
	#	while not self._factory.isReady() and (timeout < self._timeout):
	#		time.sleep(0.1)
	#		timeout += 0.1
	#	if (timeout >= self._timeout):
	#		raise Exception("timed out after %d seconds" % self._timeout)
	#	
	#	logger.debug("Getting subjects...")
	#	return self._factory.execute(method = 'getSubjects', params = [])
	
	def setSelectedIndex(self, subjectId, choiceIndex):
		self._factory.execute(method = 'setSelectedIndex', params = [ subjectId, choiceIndex ])
	
	def selectChoice(self, subjectId):
		self._factory.execute(method = 'selectChoice', params = [ subjectId ])









