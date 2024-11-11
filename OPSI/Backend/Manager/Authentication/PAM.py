# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
PAM authentication.
"""

import grp
import os
import pwd
from typing import Set

import pam
from opsicommon.logging import get_logger

from OPSI.Backend.Manager.Authentication import AuthenticationModule
from OPSI.Exceptions import BackendAuthenticationError
from OPSI.System.Posix import isCentOS, isOpenSUSE, isRHEL, isSLES

logger = get_logger("opsi.general")


class PAMAuthentication(AuthenticationModule):
	def __init__(self, pam_service: str = None):
		super().__init__()
		self._pam_service = pam_service
		if not self._pam_service:
			if os.path.exists("/etc/pam.d/opsi-auth"):
				# Prefering our own - if present.
				self._pam_service = "opsi-auth"
			elif isSLES() or isOpenSUSE():
				self._pam_service = "sshd"
			elif isCentOS() or isRHEL():
				self._pam_service = "system-auth"
			else:
				self._pam_service = "common-auth"

	def get_instance(self):
		return PAMAuthentication(self._pam_service)

	def authenticate(self, username: str, password: str) -> None:
		"""
		Authenticate a user by PAM (Pluggable Authentication Modules).
		Important: the uid running this code needs access to /etc/shadow
		if os uses traditional unix authentication mechanisms.

		:param service: The PAM service to use. Leave None for autodetection.
		:type service: str
		:raises BackendAuthenticationError: If authentication fails.
		"""
		logger.confidential(
			"Trying to authenticate user %s with password %s by PAM", username, password
		)
		logger.trace(
			"Attempting PAM authentication as user %s (service=%s)...",
			username,
			self._pam_service,
		)

		try:
			auth = pam.pam()
			if not auth.authenticate(username, password, service=self._pam_service):
				logger.trace(
					"PAM authentication failed: %s (code %s)", auth.reason, auth.code
				)
				raise RuntimeError(auth.reason)

			logger.trace("PAM authentication successful.")
		except Exception as err:
			raise BackendAuthenticationError(
				f"PAM authentication failed for user '{username}': {err}"
			) from err

	def get_groupnames(self, username: str) -> Set[str]:
		"""
		Read the groups of a user.

		:returns: Group the user is a member of.
		:rtype: set()
		"""
		logger.debug("Getting groups of user %s", username)
		primary_gid = pwd.getpwnam(username).pw_gid
		logger.debug("Primary group id of user %s is %s", username, primary_gid)
		groups = set()
		for gid in os.getgrouplist(username, primary_gid):
			try:
				groups.add(grp.getgrgid(gid).gr_name)
			except KeyError as err:
				logger.warning(err)
		logger.debug("User %s is member of groups: %s", username, groups)
		return {g.lower() for g in groups}
