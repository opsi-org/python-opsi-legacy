# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Message

Working with subjects and progress information.
"""

import json
import threading
import time

from opsicommon.logging import get_logger
from twisted.internet import defer, reactor
from twisted.internet.protocol import ClientFactory, ServerFactory
from twisted.protocols.basic import LineReceiver

from OPSI.Types import (
	forceBool,
	forceInt,
	forceIntList,
	forceIpAddress,
	forceList,
	forceUnicode,
	forceUnicodeList,
)

__all__ = (
	"Subject",
	"MessageSubject",
	"ChoiceSubject",
	"ProgressSubject",
	"MessageObserver",
	"ChoiceObserver",
	"ProgressObserver",
	"SubjectsObserver",
	"MessageSubjectProxy",
	"ChoiceSubjectProxy",
	"ProgressSubjectProxy",
	"NotificationServerProtocol",
	"NotificationServerFactory",
	"NotificationServer",
	"NotificationClientProtocol",
	"NotificationClientFactory",
	"NotificationClient",
)

logger = get_logger("opsi.general")


class Subject:
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin,unused-argument
		self._id = forceUnicode(id)
		self._type = forceUnicode(type)
		self._title = forceUnicode(title)
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

	def setTitle(self, title):
		self._title = forceUnicode(title)

	def attachObserver(self, observer):
		if observer not in self._observers:
			self._observers.append(observer)

	def detachObserver(self, observer):
		if observer in self._observers:
			self._observers.remove(observer)

	def serializable(self):
		return {
			"id": self.getId(),
			"type": self.getType(),
			"title": self.getTitle(),
			"class": self.getClass(),
		}

	def __str__(self):
		return "<%s type: %s, id: %s>" % (self.__class__.__name__, self._type, self._id)

	def __repr__(self):
		return self.__str__()


class MessageSubject(Subject):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin
		Subject.__init__(self, id, type, title, **args)
		self.reset()
		try:
			self._message = forceUnicode(args["message"])
		except KeyError:
			pass  # no matching key

		try:
			self._severity = forceInt(args["severity"])
		except KeyError:
			pass  # no matching key

		logger.debug("MessageSubject '%s' created", self._id)

	def reset(self):
		Subject.reset(self)
		self._message = ""
		self._severity = 0

	def setMessage(self, message, severity=0):
		self._message = forceUnicode(message)
		self._severity = forceInt(severity)
		self._notifyMessageChanged()

	def getMessage(self):
		return self._message

	def getSeverity(self):
		return self._severity

	def _notifyMessageChanged(self):
		for observer in self._observers:
			observer.messageChanged(self, self._message)

	def serializable(self):
		subject = Subject.serializable(self)
		subject["message"] = self.getMessage()
		subject["severity"] = self.getSeverity()
		return subject


class ChoiceSubject(MessageSubject):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin
		MessageSubject.__init__(self, id, type, title, **args)
		self.reset()
		self._callbacks = []
		try:
			self._multiValue = forceBool(args["multiValue"])
		except KeyError:
			pass

		try:
			self._choices = forceUnicodeList(args["choices"])
		except KeyError:
			pass

		try:
			self._selectedIndexes = forceIntList(args["selectedIndexes"])
		except KeyError:
			pass

		try:
			self._callbacks = args["callbacks"]
		except KeyError:
			pass

		logger.debug("ChoiceSubject '%s' created", self._id)

	def reset(self):
		MessageSubject.reset(self)
		self._choices = []
		self._selectedIndexes = []
		self._multiValue = True

	def getMultiValue(self):
		return self._multiValue

	def setSelectedIndexes(self, selectedIndexes):
		self._selectedIndexes = []
		for selectedIndex in forceIntList(selectedIndexes):
			if (
				(selectedIndex < 0)
				or (selectedIndex > len(self._choices) - 1)
				or selectedIndex in self._selectedIndexes
			):
				continue
			if self._multiValue:
				self._selectedIndexes = [selectedIndex]
			else:
				self._selectedIndexes.append(selectedIndex)
		self._notifySelectedIndexesChanged()

	def getSelectedIndexes(self):
		return self._selectedIndexes

	def setChoices(self, choices):
		self._choices = forceUnicodeList(choices)
		if self._choices and not self._selectedIndexes:
			self._selectedIndexes = [0]
		self._notifyChoicesChanged()

	def getChoices(self):
		return self._choices

	def selectChoice(self):
		logger.debug("ChoiceSubject.selectChoice()")
		for selectedIndex in self._selectedIndexes:
			if (selectedIndex >= 0) and (selectedIndex < len(self._callbacks)):
				# Exceute callback
				logger.notice("Executing callback %s", self._callbacks[selectedIndex])
				self._callbacks[selectedIndex](self)

	def setCallbacks(self, callbacks):
		callbacks = forceList(callbacks)
		self._callbacks = callbacks

	def _notifySelectedIndexesChanged(self):
		for observer in self._observers:
			observer.selectedIndexesChanged(self, self._selectedIndexes)

	def _notifyChoicesChanged(self):
		for observer in self._observers:
			observer.choicesChanged(self, self._choices)

	def serializable(self):
		subject = MessageSubject.serializable(self)
		subject["choices"] = self.getChoices()
		subject["selectedIndexes"] = self.getSelectedIndexes()
		return subject


class ProgressSubject(MessageSubject):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin,unused-argument
		MessageSubject.__init__(self, id, type, title, **args)
		self.reset()
		self._fireAlways = True
		self._endChangable = True
		try:
			self._end = forceInt(args["end"])
			if self._end < 0:
				self._end = 0
		except KeyError:
			pass

		try:
			self._percent = args["percent"]
		except KeyError:
			pass

		try:
			self._state = args["state"]
		except KeyError:
			pass

		try:
			self._timeStarted = args["timeStarted"]
		except KeyError:
			pass

		try:
			self._timeSpend = args["timeSpend"]
		except KeyError:
			pass

		try:
			self._timeLeft = args["timeLeft"]
		except KeyError:
			pass

		try:
			self._timeFired = args["timeFired"]
		except KeyError:
			pass

		try:
			self._speed = args["speed"]
		except KeyError:
			pass

		try:
			self._fireAlways = forceBool(args["fireAlways"])
		except KeyError:
			pass

		logger.debug("ProgressSubject '%s' created", self._id)

	def reset(self):
		MessageSubject.reset(self)
		self._end = 0
		self._endChangable = True
		self._percent = 0
		self._state = 0
		self._timeStarted = time.time()
		self._timeSpend = 0
		self._timeLeft = 0
		self._timeFired = 0
		self._speed = 0
		self._notifyEndChanged()
		self._notifyProgressChanged()

	def setEndChangable(self, changable):
		self._endChangable = forceBool(changable)

	def setEnd(self, end):
		if not self._endChangable:
			return

		self._end = forceInt(end)
		if self._end < 0:
			self._end = 0
		self.setState(self._state)
		self._notifyEndChanged()

	def setState(self, state):
		state = forceInt(state)
		if state <= 0:
			state = 0
			self._percent = 0
		if state > self._end:
			state = self._end
			self._percent = 100
		self._state = state

		now = int(time.time())
		if (
			self._fireAlways
			or (self._timeFired != now)
			or (self._state in (0, self._end))
		):
			if self._state == 0:
				self._percent = 0
			elif self._end == 0:
				self._percent = 100
			else:
				self._percent = 100 * (self._state / self._end)

			self._timeSpend = now - self._timeStarted
			if self._timeSpend:
				self._speed = int(self._state / self._timeSpend)
				if self._speed < 0:
					self._speed = 0
				elif self._speed > 0:
					self._timeLeft = int(
						(
							(self._timeLeft * 2.0)
							+ (self._end - self._state) / self._speed
						)
						/ 3.0
					)

			self._timeFired = now
			self._notifyProgressChanged()

	def addToState(self, amount):
		self.setState(self._state + forceInt(amount))

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

	def _notifyProgressChanged(self):
		for observer in self._observers:
			observer.progressChanged(
				self,
				self._state,
				self._percent,
				self._timeSpend,
				self._timeLeft,
				self._speed,
			)

	def _notifyEndChanged(self):
		for observer in self._observers:
			observer.endChanged(self, self._end)

	def serializable(self):
		subject = MessageSubject.serializable(self)
		subject["end"] = self.getEnd()
		subject["state"] = self.getState()
		subject["percent"] = self.getPercent()
		subject["timeSpend"] = self.getTimeSpend()
		subject["timeLeft"] = self.getTimeLeft()
		subject["speed"] = self.getSpeed()
		return subject


class MessageObserver:
	def __init__(self):
		pass

	def messageChanged(self, subject, message):
		pass


class ChoiceObserver(MessageObserver):
	def __init__(self):
		MessageObserver.__init__(self)

	def selectedIndexesChanged(self, subject, selectedIndexes):
		pass

	def choicesChanged(self, subject, choices):
		pass


class ProgressObserver(MessageObserver):
	def __init__(self):  # pylint: disable=super-init-not-called
		pass

	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		pass

	def endChanged(self, subject, end):
		pass


class SubjectsObserver(ChoiceObserver, ProgressObserver):
	def __init__(self):  # pylint: disable=super-init-not-called
		self._subjects = []

	def setSubjects(self, subjects):
		for subject in self._subjects:
			subject.detachObserver(self)
		self._subjects = subjects
		for subject in self._subjects:
			subject.attachObserver(self)
		self.subjectsChanged(self._subjects)

	def addSubject(self, subject):
		if subject not in self._subjects:
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


class MessageSubjectProxy(
	ProgressSubject, ProgressObserver, ChoiceSubject, ChoiceObserver
):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin
		ChoiceSubject.__init__(self, id, type, title, **args)
		ChoiceObserver.__init__(self)
		ProgressSubject.__init__(self, id, type, title, **args)
		ProgressObserver.__init__(self)

	def messageChanged(self, subject, message):
		self.setMessage(message, severity=subject.getSeverity())

	def selectedIndexesChanged(self, subject, selectedIndexes):
		self.setSelectedIndexes(selectedIndexes)

	def choicesChanged(self, subject, choices):
		self.setChoices(choices)

	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		self.setState(state)

	def endChanged(self, subject, end):
		self.setEnd(end)


class ChoiceSubjectProxy(MessageSubjectProxy):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin
		MessageSubjectProxy.__init__(self, id, type, title, **args)


class ProgressSubjectProxy(MessageSubjectProxy):
	def __init__(self, id, type="", title="", **args):  # pylint: disable=redefined-builtin
		MessageSubjectProxy.__init__(self, id, type, title, **args)


class NotificationServerProtocol(LineReceiver):  # pylint: disable=abstract-method
	def connectionMade(self):
		self.factory.connectionMade(self)  # pylint: disable=no-member

	def connectionLost(self, reason=None):
		self.factory.connectionLost(self, reason)

	def lineReceived(self, line):
		# rpcs can be separated by "\r\n" or "\1e"
		for rpc in line.split(b"\x1e"):
			self.factory.rpc(self, rpc)


class NotificationServerFactory(ServerFactory, SubjectsObserver):
	protocol = NotificationServerProtocol

	def __init__(self):  # pylint: disable=super-init-not-called
		self.clients = []
		self._subjects = []
		self._rpcs = {}

	def connectionCount(self):
		return len(self.clients)

	def connectionMade(self, client):
		self.clients.append(client)
		logger.info(
			"Client connection made: %s, %d client(s) connected",
			client.transport,
			self.connectionCount(),
		)
		self.subjectsChanged(self.getSubjects())

	def connectionLost(self, client, reason):
		self.clients.remove(client)
		logger.info(
			"Client connection lost: %s (%s), %d client(s) connected",
			client.transport,
			reason,
			self.connectionCount(),
		)

	def rpc(self, client, line):  # pylint: disable=unused-argument
		logger.info("Received rpc '%s'", line)
		try:
			rpc = json.loads(line)
			method = rpc["method"]
			params = rpc["params"]

			if method == "setSelectedIndexes":
				subjectId = params[0]
				selectedIndexes = params[1]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (
						subject.getId() != subjectId
					):
						continue
					subject.setSelectedIndexes(selectedIndexes)
					break

			elif method == "selectChoice":
				logger.debug("selectChoice(%s)", str(params)[1:-1])
				subjectId = params[0]
				for subject in self.getSubjects():
					if not isinstance(subject, ChoiceSubject) or (
						subject.getId() != subjectId
					):
						continue
					subject.selectChoice()
					break
			else:
				raise ValueError(f"Unknown method '{method}'")
		except Exception as error:  # pylint: disable=broad-except
			logger.error("Failed to execute rpc: %s", error)

	def messageChanged(self, subject, message):
		if subject not in self.getSubjects():
			logger.info(
				"Unknown subject %s passed to messageChanged, automatically adding subject",
				subject,
			)
			self.addSubject(subject)
		logger.debug(
			"messageChanged: subject id '%s', message '%s'", subject.getId(), message
		)
		self.notify(name="messageChanged", params=[subject.serializable(), message])

	def selectedIndexesChanged(self, subject, selectedIndexes):
		if subject not in self.getSubjects():
			logger.info(
				"Unknown subject %s passed to selectedIndexesChanged, automatically adding subject",
				subject,
			)
			self.addSubject(subject)
		logger.debug(
			"selectedIndexesChanged: subject id '%s', selectedIndexes %s",
			subject.getId(),
			selectedIndexes,
		)
		self.notify(
			name="selectedIndexesChanged",
			params=[subject.serializable(), selectedIndexes],
		)

	def choicesChanged(self, subject, choices):
		if subject not in self.getSubjects():
			logger.info(
				"Unknown subject %s passed to choicesChanged, automatically adding subject",
				subject,
			)
			self.addSubject(subject)
		logger.debug(
			"choicesChanged: subject id '%s', choices %s", subject.getId(), choices
		)
		self.notify(name="choicesChanged", params=[subject.serializable(), choices])

	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):  # pylint:disable=too-many-arguments
		if subject not in self.getSubjects():
			logger.info(
				"Unknown subject %s passed to progressChanged, automatically adding subject",
				subject,
			)
			self.addSubject(subject)
		logger.debug(
			"progressChanged: subject id '%s', state %s, percent %s, timeSpend %s, timeLeft %s, speed %s",
			subject.getId(),
			state,
			percent,
			timeSpend,
			timeLeft,
			speed,
		)
		self.notify(
			name="progressChanged",
			params=[subject.serializable(), state, percent, timeSpend, timeLeft, speed],
		)

	def endChanged(self, subject, end):
		if subject not in self.getSubjects():
			logger.info(
				"Unknown subject %s passed to endChanged, automatically adding subject",
				subject,
			)
			self.addSubject(subject)
		logger.debug("endChanged: subject id '%s', end %s", subject.getId(), end)
		self.notify(name="endChanged", params=[subject.serializable(), end])

	def subjectsChanged(self, subjects):
		logger.debug("subjectsChanged: subjects %s", subjects)
		param = [subject.serializable() for subject in subjects]
		self.notify(name="subjectsChanged", params=[param])

	def requestEndConnections(self, clientIds=None):
		if not self.clients:
			return
		self.notify(name="endConnection", params=[clientIds])

	def notify(self, name, params, clients=None):
		if not isinstance(params, list):
			params = [params]
		if not clients:
			clients = self.clients
		if not isinstance(clients, list):
			clients = [clients]

		logger.debug("Sending notification '%s' to %d client(s)", name, len(clients))

		if not clients:
			return

		# json-rpc: notifications have id null
		jsonBytes = json.dumps({"id": None, "method": name, "params": params}).encode(
			"utf-8"
		)
		for client in clients:
			try:
				logger.debug("Sending line '%s' to client %s", jsonBytes, client)
				client.sendLine(jsonBytes)
			except Exception as err:  # pylint: disable=broad-except
				logger.warning("Failed to send line to client %s: %s", client, err)


class NotificationServer(threading.Thread, SubjectsObserver):
	def __init__(self, address, start_port, subjects):  # pylint: disable=super-init-not-called
		threading.Thread.__init__(self)
		self._address = forceIpAddress(address)
		if not self._address:
			self._address = "0.0.0.0"
		self._start_port = forceInt(start_port)
		self._factory = NotificationServerFactory()
		self._factory.setSubjects(subjects)
		self._server = None
		self._listening = False
		self._error = None
		self._port = 0
		self._running_event = threading.Event()

	@property
	def port(self):
		return self._port

	def isListening(self):
		return self._listening

	def errorOccurred(self):
		return self._error

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

	def requestEndConnections(self, clientIds=None):
		if not clientIds:
			clientIds = []
		if self._factory:
			self._factory.requestEndConnections(clientIds)

	def run(self):
		logger.info("Notification server starting")

		trynum = 0
		port = self._start_port
		while True:
			trynum += 1
			try:
				logger.debug(
					"Notification server - attempt %d, trying port %d", trynum, port
				)
				if self._address == "0.0.0.0":
					self._server = reactor.listenTCP(port, self._factory)  # pylint: disable=no-member
				else:
					self._server = reactor.listenTCP(
						port, self._factory, interface=self._address
					)  # pylint: disable=no-member
				self._port = port
				self._listening = True
				logger.info(
					"Notification server is now listening on port %d after %d attempts",
					port,
					trynum,
				)
				if not reactor.running:  # pylint: disable=no-member
					logger.info("Starting reactor")
					reactor.run(installSignalHandlers=0)  # pylint: disable=no-member
				break
			except Exception as error:  # pylint: disable=broad-except
				logger.debug(
					"Notification server - attempt %d, failed to listen on port %d: %s",
					trynum,
					port,
					error,
				)
				if trynum >= 20:
					self._error = forceUnicode(error)
					logger.error(error, exc_info=True)
					break
				port += 1
		self._running_event.set()

	def start_and_wait(self, timeout=30):
		self.start()
		self._running_event.wait(timeout)
		return self._listening

	def _stopListeningCompleted(self, result):  # pylint: disable=unused-argument
		self._listening = False

	def stop(self, stopReactor=True):
		self.requestEndConnections()
		reactor.callLater(3.0, self._stopServer, stopReactor)  # pylint: disable=no-member

	def _stopServer(self, stopReactor=True):
		if self._server:
			result = self._server.stopListening()
			if isinstance(result, defer.Deferred):
				result.addCallback(self._stopListeningCompleted)
			else:
				self._listening = False
		if stopReactor:
			reactor.callLater(3.0, self._stopReactor)  # pylint: disable=no-member
		logger.info("Notification server stopped")

	def _stopReactor(self):
		if reactor and reactor.running:  # pylint: disable=no-member
			try:
				reactor.stop()  # pylint: disable=no-member
			except Exception as error:  # pylint: disable=broad-except
				logger.error("Failed to stop reactor: %s", error)


class NotificationClientProtocol(LineReceiver):  # pylint:disable=abstract-method
	def connectionMade(self):
		self.factory.connectionMade(self)

	def lineReceived(self, line):
		self.factory.receive(line)

	def connectionLost(self, reason=None):
		self.factory.connectionLost(reason)


class NotificationClientFactory(ClientFactory):
	protocol = NotificationClientProtocol
	_client = None
	_observer = None

	def __init__(self, notificationClient, observer):
		self._notificationClient = notificationClient
		self._observer = observer
		self._rpcs = {}
		self._timeout = 5

	def connectionLost(self, reason):  # pylint: disable=unused-argument
		logger.info("Server connection lost")

	def connectionMade(self, client):
		logger.info("Server connection made")
		self._client = client

	def isReady(self):
		return self._client is not None

	def sendLine(self, line):
		logger.debug("Sending line '%s'", line)
		self._client.sendLine(line)

	def receive(self, rpc):
		logger.debug("Received rpc '%s'", rpc)
		id = None  # pylint: disable=redefined-builtin
		try:
			rpc = json.loads(rpc)
			id = rpc["id"]
			if id:
				# Received rpc answer
				self._rpcs[id] = rpc
			else:
				# Notification
				method = rpc["method"]
				params = rpc["params"]
				if method == "endConnection":
					logger.info("Server requested connection end")
					if (
						not params
						or not params[0]
						or not self._notificationClient.getId()
						or self._notificationClient.getId() in forceList(params[0])
					):
						self._notificationClient.endConnectionRequested()
				else:
					logger.debug("self._observer.%s(*params)", method)
					eval("self._observer.%s(*params)", method)  # pylint: disable=eval-used
		except Exception as error:  # pylint: disable=broad-except
			logger.error(error)

	def execute(self, method, params):
		logger.debug("Executing method '%s', params %s", method, params)
		if not params:
			params = []
		if not isinstance(params, (list, tuple)):
			params = [params]

		timeout = 0
		while not self.isReady() and (timeout < self._timeout):
			time.sleep(0.1)
			timeout += 0.1
		if timeout >= self._timeout:
			raise RuntimeError(f"Execute timed out after {self._timeout} seconds")

		rpc = {"id": None, "method": method, "params": params}
		self.sendLine(json.dumps(rpc))


class NotificationClient(threading.Thread):
	def __init__(self, address, port, observer, clientId=None):
		threading.Thread.__init__(self)
		self._address = address
		self._port = port
		self._observer = observer
		self._id = clientId
		self._factory = NotificationClientFactory(self, self._observer)
		self._client = None
		self._endConnectionRequestedCallbacks = []

	def getId(self):
		return self._id

	def addEndConnectionRequestedCallback(self, endConnectionRequestedCallback):
		if endConnectionRequestedCallback not in self._endConnectionRequestedCallbacks:
			self._endConnectionRequestedCallbacks.append(endConnectionRequestedCallback)

	def removeEndConnectionRequestedCallback(self, endConnectionRequestedCallback):
		if endConnectionRequestedCallback in self._endConnectionRequestedCallbacks:
			self._endConnectionRequestedCallbacks.remove(endConnectionRequestedCallback)

	def endConnectionRequested(self):
		for endConnectionRequestedCallback in self._endConnectionRequestedCallbacks:
			try:
				endConnectionRequestedCallback()
			except Exception as error:  # pylint: disable=broad-except
				logger.error(error)

	def getFactory(self):
		return self._factory

	def run(self):
		logger.info("Notification client starting")
		try:
			logger.info("Connecting to %s:%s", self._address, self._port)
			reactor.connectTCP(self._address, self._port, self._factory)  # pylint: disable=no-member
			if not reactor.running:  # pylint: disable=no-member
				reactor.run(installSignalHandlers=0)  # pylint: disable=no-member
		except Exception as error:  # pylint: disable=broad-except
			logger.error(error, exc_info=True)

	def stop(self, stopReactor=True):
		if self._client:
			self._client.disconnect()
		if stopReactor and reactor and reactor.running:  # pylint: disable=no-member
			reactor.stop()  # pylint: disable=no-member

	def setSelectedIndexes(self, subjectId, selectedIndexes):
		self._factory.execute(
			method="setSelectedIndexes", params=[subjectId, selectedIndexes]
		)

	def selectChoice(self, subjectId):
		self._factory.execute(method="selectChoice", params=[subjectId])
