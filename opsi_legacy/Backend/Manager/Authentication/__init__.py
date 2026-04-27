# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Authentication helper.
"""

from typing import Set

from opsi.logging import get_logger

from opsi_legacy.Config import OPSI_ADMIN_GROUP
from opsi_legacy.Exceptions import BackendAuthenticationError
from opsi_legacy.Util.File.Opsi import OpsiConfFile

logger = get_logger("opsi.general")


class AuthenticationModule:
	def __init__(self):
		pass

	def get_instance(self):
		return self.__class__()

	def authenticate(self, username: str, password: str) -> None:
		raise BackendAuthenticationError("Not implemented")

	def get_groupnames(self, username: str) -> Set[str]:
		return set()

	def get_admin_groupname(self) -> str:
		return OPSI_ADMIN_GROUP

	def get_read_only_groupnames(self) -> Set[str]:
		return set(OpsiConfFile().getOpsiGroups("readonly") or [])

	def user_is_admin(self, username: str) -> bool:
		return self.get_admin_groupname() in self.get_groupnames(username)

	def user_is_read_only(self, username: str, forced_user_groupnames: Set[str] = None) -> bool:
		user_groupnames = set()
		if forced_user_groupnames is None:
			user_groupnames = self.get_groupnames(username)
		else:
			user_groupnames = forced_user_groupnames

		read_only_groupnames = self.get_read_only_groupnames()
		for group_name in user_groupnames:
			if group_name in read_only_groupnames:
				return True
		return False
