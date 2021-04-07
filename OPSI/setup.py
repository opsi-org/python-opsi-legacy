# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0

import pwd
import grp
import subprocess

from OPSI.Config import OPSI_ADMIN_GROUP, FILE_ADMIN_GROUP, DEFAULT_DEPOT_USER, DEFAULT_DEPOT_USER_HOME
from OPSI.Logger import Logger
from OPSI.System import get_subprocess_environment
from OPSI.Util.Task.Rights import set_rights

logger = Logger()

def create_group(groupname: str, system: bool = False):
	logger.notice("Creating group: %s", groupname)
	cmd = ["groupadd"]
	if system:
		cmd.append("--system")
	cmd.append(groupname)
	logger.info("Running command: %s", cmd)
	subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment())

def create_user(username: str, primary_groupname: str, home: str, shell: str, system: bool = False):
	logger.notice("Creating user: %s", username)
	cmd = ["useradd", "-g", primary_groupname, "-d", home, "-s", shell]
	if system:
		cmd.append("--system")
	cmd.append(username)
	logger.info("Running command: %s", cmd)
	subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment())

def add_user_to_group(username: str, groupname: str):
	logger.notice("Adding user '%s' to group '%s'", username, groupname)
	cmd = ["usermod", "-a", "-G", groupname, username]
	logger.info("Running command: %s", cmd)
	subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment())

def set_primary_group(username: str, groupname: str):
	logger.notice("Setting primary group of user '%s' to '%s'", username, groupname)
	cmd = ["usermod", "-g", groupname, username]
	logger.info("Running command: %s", cmd)
	subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=get_subprocess_environment())

def get_groups():
	groups = {}
	for group in grp.getgrall():
		groups[group.gr_name] = group
	return groups

def get_users():
	users = {}
	for user in pwd.getpwall():
		users[user.pw_name] = user
	return users

def setup_users_and_groups():
	logger.info("Setup users and groups")
	groups = get_groups()
	users = get_users()

	if OPSI_ADMIN_GROUP not in groups:
		create_group(
			groupname=OPSI_ADMIN_GROUP,
			system=False
		)
		groups = get_groups()

	if FILE_ADMIN_GROUP not in groups:
		create_group(
			groupname=FILE_ADMIN_GROUP,
			system=True
		)
		groups = get_groups()

	if DEFAULT_DEPOT_USER not in users:
		create_user(
			username=DEFAULT_DEPOT_USER,
			primary_groupname=FILE_ADMIN_GROUP,
			home=DEFAULT_DEPOT_USER_HOME,
			shell="/bin/false",
			system=True
		)
		users = get_users()

def setup_file_permissions(path: str = '/'):
	set_rights(path)

def setup():
	logger.notice("Running setup")
	setup_users_and_groups()
	setup_file_permissions()
