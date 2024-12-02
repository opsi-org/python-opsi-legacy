# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Message

Working with subjects and progress information.
"""

import time

from opsicommon.logging import get_logger

from OPSI.Types import (
	forceBool,
	forceInt,
	forceIntList,
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
)

logger = get_logger("opsi.general")


class Subject:
	def __init__(self, id, type="", title="", **args):
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
	def __init__(self, id, type="", title="", **args):
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
	def __init__(self, id, type="", title="", **args):
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
	def __init__(self, id, type="", title="", **args):
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
	def __init__(self):
		pass

	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		pass

	def endChanged(self, subject, end):
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
	def __init__(self, id, type="", title="", **args):
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
	def __init__(self, id, type="", title="", **args):
		MessageSubjectProxy.__init__(self, id, type, title, **args)


class ProgressSubjectProxy(MessageSubjectProxy):
	def __init__(self, id, type="", title="", **args):
		MessageSubjectProxy.__init__(self, id, type, title, **args)
