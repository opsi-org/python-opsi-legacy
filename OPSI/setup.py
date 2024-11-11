# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
setup tasks
"""

import grp
import pwd
import subprocess

from opsicommon.logging import get_logger

from OPSI.Config import (
	DEFAULT_DEPOT_USER,
	DEFAULT_DEPOT_USER_HOME,
	FILE_ADMIN_GROUP,
	OPSI_ADMIN_GROUP,
)
from OPSI.System import get_subprocess_environment
from OPSI.Util.Task.Rights import set_rights

logger = get_logger("opsi.general")


def create_group(groupname: str, system: bool = False) -> None:
	logger.notice("Creating group: %s", groupname)
	cmd = ["groupadd"]
	if system:
		cmd.append("--system")
	cmd.append(groupname)
	logger.info("Running command: %s", cmd)
	subprocess.check_output(
		cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment()
	)


def create_user(
	username: str, primary_groupname: str, home: str, shell: str, system: bool = False
) -> None:
	logger.notice("Creating user: %s", username)
	cmd = ["useradd", "-g", primary_groupname, "-d", home, "-s", shell]
	if system:
		cmd.append("--system")
	cmd.append(username)
	logger.info("Running command: %s", cmd)
	subprocess.check_output(
		cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment()
	)


def add_user_to_group(username: str, groupname: str) -> None:
	logger.notice("Adding user '%s' to group '%s'", username, groupname)
	cmd = ["usermod", "-a", "-G", groupname, username]
	logger.info("Running command: %s", cmd)
	subprocess.check_output(
		cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment()
	)


def set_primary_group(username: str, groupname: str) -> None:
	logger.notice("Setting primary group of user '%s' to '%s'", username, groupname)
	cmd = ["usermod", "-g", groupname, username]
	logger.info("Running command: %s", cmd)
	subprocess.check_output(
		cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment()
	)


def get_groups() -> dict[str, grp.struct_group]:
	groups = {}
	for group in grp.getgrall():
		groups[group.gr_name] = group
	return groups


def get_users() -> dict[str, pwd.struct_passwd]:
	users = {}
	for user in pwd.getpwall():
		users[user.pw_name] = user
	return users


def setup_users_and_groups(ignore_errors: bool = False) -> None:
	logger.info("Setup users and groups")

	try:
		grp.getgrnam(OPSI_ADMIN_GROUP)
	except KeyError:
		try:
			create_group(groupname=OPSI_ADMIN_GROUP, system=False)
		except Exception as err:  # pylint: disable=broad-except
			if not ignore_errors:
				raise
			logger.info(err)

	try:
		grp.getgrnam(FILE_ADMIN_GROUP)
	except KeyError:
		try:
			create_group(groupname=FILE_ADMIN_GROUP, system=True)
		except Exception as err:  # pylint: disable=broad-except
			if not ignore_errors:
				raise
			logger.info(err)

	try:
		pwd.getpwnam(DEFAULT_DEPOT_USER)
	except KeyError:
		try:
			create_user(
				username=DEFAULT_DEPOT_USER,
				primary_groupname=FILE_ADMIN_GROUP,
				home=DEFAULT_DEPOT_USER_HOME,
				shell="/bin/false",
				system=True,
			)
		except Exception as err:  # pylint: disable=broad-except
			if not ignore_errors:
				raise
			logger.info(err)


def setup_file_permissions(path: str = "/") -> None:
	set_rights(path)


def setup(ignore_errors: bool = False) -> None:
	logger.notice("Running setup")
	setup_users_and_groups(ignore_errors)
	setup_file_permissions()
