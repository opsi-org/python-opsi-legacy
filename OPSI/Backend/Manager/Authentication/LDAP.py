# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
LDAP authentication
"""

from typing import Set

import ldap3
from OPSI.Backend.Manager.Authentication import AuthenticationModule
from OPSI.Exceptions import BackendAuthenticationError
from opsicommon.logging import get_logger

logger = get_logger("opsi.general")


class LDAPAuthentication(AuthenticationModule):
	def __init__(self, ldap_url: str, bind_user: str = None, group_filter: str = None):
		"""
		Authentication module using LDAP.

		This can be used to authenticate users against OpenLDAP
		or an Active Directory server.

		:param ldap_url: The ldap connection url.
		:param bind_user: (optional) The simple bind is performed with this user.
			The ``bind_user`` has to contain the placeholder ``{username}`` which will be
			replaced by the username auth autenticating user.
			The placeholder ``{base}`` will be replaced by the base dn.
			For active directory ``{username}@your.realm`` should work.
			For OpenLDAP a dn like ``uid={username},ou=Users,{base}`` should be used.
			If ommitted the bind_user will be guessed.
		:param group_filter: (optional) The filter which is used when searching groups.
		Examples::
			>>> active_directory_auth = LDAPAuthentication("ldaps://ad.company.de/dc=company,dc=de", "{username}@company.de")
			>>> open_ldap_auth = LDAPAuthentication("ldap://ldap.company.de/dc=company,dc=de", "uid={username},dc=Users,{base}")
		"""
		super().__init__()
		self._ldap_url = ldap_url
		self._uri = ldap3.utils.uri.parse_uri(self._ldap_url)
		self._bind_user = bind_user
		self._group_filter = group_filter
		self._ldap = None
		if self._bind_user is None:
			if self._uri["base"]:
				realm = ".".join(
					[dc.split("=")[1] for dc in self._uri["base"].split(",")]
				)
			else:
				realm = self._uri["host"]
			self._bind_user = "{username}@" + realm
		logger.info(
			"LDAP auth configuration: server_url=%s, base=%s, bind_user=%s, group_filter=%s",
			self.server_url,
			self._uri["base"],
			self._bind_user,
			self._group_filter,
		)

	@property
	def server_url(self):
		url = self._uri["host"]
		if self._uri["port"]:
			url = url + ":" + str(self._uri["port"])
		if self._uri["ssl"]:
			url = "ldaps://" + url
		else:
			url = "ldap://" + url
		return url

	def get_instance(self):
		return LDAPAuthentication(self._ldap_url, self._bind_user, self._group_filter)

	def authenticate(self, username: str, password: str) -> None:
		"""
		Authenticate a user by LDAP bind

		:raises BackendAuthenticationError: If authentication fails.
		"""
		self._ldap = None
		try:
			bind_user = self._bind_user.replace("{username}", username).replace(
				"{base}", self._uri["base"]
			)
			logger.info("Binding as user %s to server %s", bind_user, self.server_url)
			# self._ldap = ldap3.Connection(server=self.server_url, client_strategy=ldap3.SAFE_SYNC, user=bind_user, password=password)
			self._ldap = ldap3.Connection(
				server=self.server_url, user=bind_user, password=password
			)
			if not self._ldap.bind():
				raise RuntimeError(f"bind failed: {self._ldap.result}")
			# self._ldap.extend.standard.who_am_i()
		except Exception as err:
			logger.info(
				"LDAP authentication failed for user '%s'", username, exc_info=True
			)
			raise BackendAuthenticationError(
				f"LDAP authentication failed for user '{username}': {err}"
			) from err

	def get_groupnames(self, username: str) -> Set[str]:  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
		groupnames = set()
		if not self._ldap:
			raise RuntimeError("Failed to get groupnames, not connected to ldap")

		ldap_type = "openldap"
		user_dn = None
		group_dns = []
		for uf in [
			f"(&(objectclass=user)(sAMAccountName={username}))",
			f"(&(objectclass=posixAccount)(uid={username}))",
		]:
			try:
				logger.debug(
					"Searching user in ldap base=%s, filter=%s", self._uri["base"], uf
				)
				self._ldap.search(
					self._uri["base"], uf, search_scope=ldap3.SUBTREE, attributes="*"
				)
				for entry in sorted(self._ldap.entries):
					user_dn = entry.entry_dn
					if "memberOf" in entry.entry_attributes:
						group_dns.extend(entry.memberOf)
					if "sAMAccountName" in entry.entry_attributes:
						ldap_type = "ad"
						groupnames.add("domain users")
				if user_dn:
					break
			except ldap3.core.exceptions.LDAPObjectClassError as err:
				logger.debug(err)
			if user_dn and ldap_type == "ad":
				break

		if not user_dn:
			raise RuntimeError(f"User {username} not found in {ldap_type} ldap")

		logger.info("User %s found in %s ldap: %s", username, ldap_type, user_dn)

		group_filter = self._group_filter
		attributes = []
		if ldap_type == "ad":
			if self._group_filter is None:
				group_filter = "(objectclass=group)"
			attributes = ["sAMAccountName", "member", "memberOf"]
		else:
			if self._group_filter is None:
				group_filter = "(objectclass=posixGroup)"
			attributes = ["cn", "member", "memberUid"]

		for base in group_dns or [self._uri["base"]]:
			scope = ldap3.BASE if group_dns else ldap3.SUBTREE

			logger.debug(
				"Searching groups in ldap base=%s, scope=%s, filter=%s",
				base,
				scope,
				group_filter,
			)
			self._ldap.search(
				base, group_filter, search_scope=scope, attributes=attributes
			)

			for entry in sorted(self._ldap.entries):
				group_name = None
				if "sAMAccountName" in entry.entry_attributes:
					group_name = str(entry.sAMAccountName)
				else:
					group_name = str(entry.cn)

				if group_dns:
					logger.debug("Entry %s by memberOf", entry.entry_dn)
					groupnames.add(group_name)
					# Get nested groups (one level only, uses RDN)
					if "memberOf" in entry.entry_attributes:
						logger.debug(
							"Nested groups of %s: %s", entry.entry_dn, entry.memberOf
						)
						for nested_group_dn in entry.memberOf:
							groupnames.add(
								nested_group_dn.split(",")[0].split("=", 1)[1]
							)

				elif "member" in entry.entry_attributes:
					logger.debug("Entry %s member: %s", entry.entry_dn, entry.member)
					for member in entry.member:
						if user_dn.lower() == member.lower():
							groupnames.add(group_name)
							break
				elif "memberUid" in entry.entry_attributes:
					logger.debug(
						"Entry %s memberUid: %s", entry.entry_dn, entry.memberUid
					)
					for member in entry.memberUid:
						if member.lower() == username.lower():
							groupnames.add(group_name)
							break
		return {g.lower() for g in groupnames}

	def __del__(self):
		if self._ldap:
			try:
				self._ldap.unbind()
			except Exception as err:  # pylint: disable=broad-except
				logger.warning(err)
