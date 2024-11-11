# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Handling of sessions.

Sessions are managed by a SessionHandler.
It tracks all the present sessions.
Sessions do timeout after a specified time.
"""

import threading
import time

from opsicommon.logging import get_logger

from OPSI.Exceptions import OpsiServiceAuthenticationError
from OPSI.Types import forceInt, forceUnicode
from OPSI.Util import randomString

logger = get_logger("opsi.general")


class Session:  # pylint: disable=too-many-instance-attributes
	def __init__(self, sessionHandler, name="OPSISID", sessionMaxInactiveInterval=120):
		self.sessionHandler = sessionHandler
		self.name = forceUnicode(name)
		self.sessionMaxInactiveInterval = forceInt(sessionMaxInactiveInterval)
		self.created = time.time()
		self.lastModified = time.time()
		self.sessionTimer = None
		self.uid = randomString(32)
		self.ip = ""  # pylint: disable=invalid-name
		self.userAgent = ""
		self.hostname = ""
		self.user = ""
		self.password = ""
		self.authenticated = False
		self.postpath = []
		self.usageCount = 0
		self.usageCountLock = threading.Lock()
		self.markedForDeletion = False
		self.deleted = False
		self.touch()

	def __repr__(self):
		return (
			f"<{self.__class__.__name__}"
			f"({self.sessionHandler}, name={self.name}, sessionMaxInactiveInterval={self.sessionMaxInactiveInterval})>"
		)

	def decreaseUsageCount(self):
		if self.deleted:
			return

		with self.usageCountLock:
			self.usageCount -= 1

	def increaseUsageCount(self):
		if self.deleted:
			return

		with self.usageCountLock:
			self.usageCount += 1
			self.touch()

	def touch(self):
		if self.deleted:
			return

		self.lastModified = time.time()
		if self.sessionTimer:
			self.sessionTimer.cancel()
			self.sessionTimer.join(1)
		self.sessionTimer = threading.Timer(
			self.sessionMaxInactiveInterval, self.expire
		)
		self.sessionTimer.start()

	def setMarkedForDeletion(self):
		self.markedForDeletion = True

	def getMarkedForDeletion(self):
		return self.markedForDeletion

	def getValidity(self):
		if self.deleted:
			return 0

		return int(self.lastModified - time.time() + self.sessionMaxInactiveInterval)

	def expire(self):
		self.sessionHandler.sessionExpired(self)

	def delete(self):
		if self.deleted:
			return

		self.deleted = True
		if self.usageCount > 0:
			logger.debug("Deleting session in use: %s", self)

		if self.sessionTimer:
			try:
				self.sessionTimer.cancel()
				try:
					self.sessionTimer.join(1)
				except Exception:  # pylint: disable=broad-except
					pass
				logger.info("Session timer %s canceled", self.sessionTimer)
			except Exception as err:  # pylint: disable=broad-except
				logger.error("Failed to cancel session timer: %s", err)


class SessionHandler:
	def __init__(
		self,
		sessionName="OPSISID",
		sessionMaxInactiveInterval=120,
		maxSessionsPerIp=0,
		sessionDeletionTimeout=60,
	):
		self.sessionName = forceUnicode(sessionName)
		self.sessionMaxInactiveInterval = forceInt(sessionMaxInactiveInterval)
		self.maxSessionsPerIp = forceInt(maxSessionsPerIp)
		self.sessionDeletionTimeout = forceInt(sessionDeletionTimeout)
		self.sessions = {}

	def cleanup(self):
		self.deleteAllSessions()

	def getSessions(self, ip=None):  # pylint: disable=invalid-name
		"""
		Get the sessions handled by this handler.

		:param ip: Limit the returned values to sessions coming from this IP.
		:type ip: str
		:returns: a dict where the uid of the session is the key and \
the value holds the sesion.
		:rtype: {str: Session}
		"""
		if not ip:
			return self.sessions

		return {
			uid: session for uid, session in self.sessions.items() if session.ip == ip
		}

	def getSession(self, uid=None, ip=None):  # pylint: disable=invalid-name
		if uid:
			session = self.sessions.get(uid)
			if session:
				if session.getMarkedForDeletion():
					logger.info("Session found but marked for deletion")
				else:
					# Set last modified to current time
					session.increaseUsageCount()
					logger.confidential(
						"Returning session: %s (count: %d)",
						session.uid,
						session.usageCount,
					)
					return session
			else:
				logger.info("Failed to get session: session id %s not found", uid)

		if ip and self.maxSessionsPerIp > 0:
			sessions = self.getSessions(ip)
			if len(sessions) >= self.maxSessionsPerIp:
				logger.warning("Session limit for ip '%s' reached", ip)
				for sessionUid, session in sessions.items():
					if session.usageCount > 0:
						continue
					logger.info("Deleting unused session")
					self.deleteSession(sessionUid)

				if len(self.getSessions(ip)) >= self.maxSessionsPerIp:
					raise OpsiServiceAuthenticationError(
						f"Session limit for ip '{ip}' reached"
					)

		session = self.createSession()
		session.increaseUsageCount()
		return session

	def createSession(self):
		session = Session(self, self.sessionName, self.sessionMaxInactiveInterval)
		self.sessions[session.uid] = session
		logger.notice("New session created")
		return session

	def sessionExpired(self, session):
		logger.notice(
			"Session '%s' from ip '%s', application '%s' expired after %d seconds",
			session.uid,
			session.ip,
			session.userAgent,
			(time.time() - session.lastModified),
		)

		if session.usageCount > 0:
			logger.notice(
				"Session %s currently in use, waiting before deletion", session.uid
			)

		session.setMarkedForDeletion()
		timeout = self.sessionDeletionTimeout
		sleepInSeconds = 0.01
		while session.usageCount > 0 and timeout > 0:
			if not self.sessions.get(session.uid):
				# Session deleted (closed by client)
				return False
			time.sleep(sleepInSeconds)
			timeout -= sleepInSeconds

		if timeout == 0:
			logger.warning(
				"Session '%s': timeout occurred while waiting for session to get free for deletion",
				session.uid,
			)

		self.deleteSession(session.uid)
		return True

	def deleteSession(self, uid):
		session = self.sessions.get(uid)
		if not session:
			logger.warning("No such session id: %s", uid)
			return

		try:
			session.delete()
		except Exception:  # pylint: disable=broad-except
			pass

		try:
			del self.sessions[uid]
			logger.notice(
				"Session '%s' from ip '%s', application '%s' deleted",
				session.uid,
				session.ip,
				session.userAgent,
			)
			del session
		except KeyError:
			pass

	def deleteAllSessions(self):
		logger.notice("Deleting all sessions")

		class SessionDeletionThread(threading.Thread):
			def __init__(self, sessionHandler, uid):
				threading.Thread.__init__(self)
				self._sessionHandler = sessionHandler
				self._uid = uid

			def run(self):
				self._sessionHandler.deleteSession(self._uid)

		deletionThreads = []
		for uid in self.sessions:
			logger.debug("Deleting session %s", uid)
			thread = SessionDeletionThread(self, uid)
			deletionThreads.append(thread)

		for thread in deletionThreads:
			thread.start()

		for thread in deletionThreads:
			thread.join(2)

		self.sessions = {}
