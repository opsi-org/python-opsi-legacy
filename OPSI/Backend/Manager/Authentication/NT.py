# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
PAM authentication.
"""

from typing import Set

# pyright: reportMissingImports=false
import win32net
import win32security
from opsicommon.logging import get_logger

from OPSI.Backend.Manager.Authentication import AuthenticationModule
from OPSI.Config import OPSI_ADMIN_GROUP
from OPSI.Exceptions import BackendAuthenticationError

logger = get_logger("opsi.general")


class NTAuthentication(AuthenticationModule):
	def __init__(self, admin_group_sid: str = None):
		super().__init__()
		self._admin_group_sid = admin_group_sid
		self._admin_groupname = OPSI_ADMIN_GROUP
		if self._admin_group_sid is not None:
			try:
				self._admin_groupname = win32security.LookupAccountSid(
					None, win32security.ConvertStringSidToSid(self._admin_group_sid)
				)[0]
			except Exception as err:
				logger.error(
					"Failed to lookup group with sid '%s': %s",
					self._admin_group_sid,
					err,
				)

	def get_instance(self):
		return NTAuthentication(self._admin_group_sid)

	def authenticate(self, username: str, password: str) -> None:
		"""
		Authenticate a user by Windows-Login on current machine

		:raises BackendAuthenticationError: If authentication fails.
		"""
		logger.confidential(
			"Trying to authenticate user %s with password %s by win32security",
			username,
			password,
		)

		try:
			win32security.LogonUser(
				username,
				"None",
				password,
				win32security.LOGON32_LOGON_NETWORK,
				win32security.LOGON32_PROVIDER_DEFAULT,
			)
		except Exception as err:
			raise BackendAuthenticationError(
				f"Win32security authentication failed for user '{username}': {err}"
			) from err

	def get_admin_groupname(self) -> str:
		return self._admin_groupname.lower()

	def get_groupnames(self, username: str) -> Set[str]:
		"""
		Read the groups of a user.

		:returns: List og group names the user is a member of.
		:rtype: set()
		"""
		collected_groupnames = set()

		gresume = 0
		while True:
			(groups, gtotal, gresume) = win32net.NetLocalGroupEnum(None, 0, gresume)
			logger.trace(
				"Got %s groups, total=%s, resume=%s", len(groups), gtotal, gresume
			)
			for groupname in (u["name"] for u in groups):
				logger.trace("Found group '%s'", groupname)
				uresume = 0
				while True:
					(users, utotal, uresume) = win32net.NetLocalGroupGetMembers(
						None, groupname, 0, uresume
					)
					logger.trace(
						"Got %s users, total=%s, resume=%s", len(users), utotal, uresume
					)
					for sid in (u["sid"] for u in users):
						(group_username, _domain, _group_type) = (
							win32security.LookupAccountSid(None, sid)
						)
						if group_username.lower() == username.lower():
							collected_groupnames.add(groupname)
							logger.debug(
								"User %s is member of group %s", username, groupname
							)
					if uresume == 0:
						break
			if gresume == 0:
				break

		return {g.lower() for g in collected_groupnames}
