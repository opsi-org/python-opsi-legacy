# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Setting access rights for opsi.

Opsi needs different access rights and ownerships for files and folders
during its use. To ease the setting of these permissions this modules
provides helpers for this task.
"""

import grp
import os
import pwd
import stat
from dataclasses import dataclass
from functools import lru_cache

from OPSI.Backend.Base.ConfigData import OPSI_PASSWD_FILE
from OPSI.Config import (
	DEFAULT_DEPOT_USER,
	DEFAULT_DEPOT_USER_HOME,
	FILE_ADMIN_GROUP,
	OPSI_ADMIN_GROUP,
	OPSICONFD_USER,
)
from OPSI.System.Posix import isOpenSUSE, isSLES
from opsicommon.logging import get_logger
from opsicommon.utils import Singleton

_HAS_ROOT_RIGHTS = os.geteuid() == 0

logger = get_logger("opsi.general")


@dataclass
class FilePermission:
	path: str
	username: str
	groupname: str
	file_permissions: int

	@staticmethod
	@lru_cache(maxsize=None)
	def username_to_uid(username: str) -> int:
		return pwd.getpwnam(username)[2]

	@staticmethod
	@lru_cache(maxsize=None)
	def groupname_to_gid(groupname: str) -> int:
		try:
			return grp.getgrnam(groupname)[2]
		except KeyError as err:
			logger.debug(err)
		return -1

	@property
	def uid(self) -> int:
		if not self.username:
			return -1
		return self.username_to_uid(self.username)

	@property
	def gid(self) -> int:
		if not self.groupname:
			return -1
		return self.groupname_to_gid(self.groupname)

	def chmod(self, path, stat_res=None):
		stat_res = stat_res or os.stat(path, follow_symlinks=False)
		cur_mode = stat_res.st_mode & 0o7777
		if cur_mode != self.file_permissions:
			logger.trace("%s: %o != %o", path, cur_mode, self.file_permissions)
			os.chmod(
				path,
				self.file_permissions,
				follow_symlinks=not stat.S_ISLNK(stat_res.st_mode),
			)

	def chown(self, path, stat_res=None):
		stat_res = stat_res or os.stat(path, follow_symlinks=False)
		# Unprivileged user cannot change file owner
		uid = self.uid if _HAS_ROOT_RIGHTS else -1
		if uid not in (-1, stat_res.st_uid) or self.gid not in (-1, stat_res.st_gid):
			logger.trace(
				"%s: %d:%d != %d:%d",
				path,
				stat_res.st_uid,
				stat_res.st_gid,
				uid,
				self.gid,
			)
			os.chown(
				path, uid, self.gid, follow_symlinks=not stat.S_ISLNK(stat_res.st_mode)
			)

	def apply(self, path):
		stat_res = os.stat(path, follow_symlinks=False)
		self.chmod(path, stat_res)
		self.chown(path, stat_res)


@dataclass
class DirPermission(FilePermission):
	dir_permissions: int
	recursive: bool = True
	correct_links: bool = False
	modify_file_exe: bool = True

	def chmod(self, path, stat_res=None):
		stat_res = stat_res or os.stat(path, follow_symlinks=False)
		if stat.S_ISLNK(stat_res.st_mode) and not self.correct_links:
			return

		cur_mode = stat_res.st_mode & 0o7777
		new_mode = self.file_permissions
		if stat.S_ISDIR(stat_res.st_mode):
			new_mode = self.dir_permissions
		elif stat.S_ISREG(stat_res.st_mode) and not self.modify_file_exe:
			# Do not modify executable flag
			if cur_mode & 0o100 and new_mode & 0o400:
				# User: executable bit currently set and new mode readable
				new_mode |= 0o100
			if cur_mode & 0o010 and new_mode & 0o040:
				# Group: executable bit currently set and new mode readable
				new_mode |= 0o010
			if cur_mode & 0o001 and new_mode & 0o004:
				# Other: executable bit currently set and new mode readable
				new_mode |= 0o001

		if cur_mode != new_mode:
			logger.trace("%s: %o != %o", path, cur_mode, new_mode)
			os.chmod(path, new_mode, follow_symlinks=not stat.S_ISLNK(stat_res.st_mode))

	def chown(self, path, stat_res=None):
		stat_res = stat_res or os.stat(path, follow_symlinks=False)
		if stat.S_ISLNK(stat_res.st_mode) and not self.correct_links:
			return None
		return super().chown(path, stat_res)


def _get_default_depot_user_ssh_dir():
	return os.path.join(DEFAULT_DEPOT_USER_HOME, ".ssh")


class PermissionRegistry(metaclass=Singleton):
	def __init__(self):
		self._permissions = {}
		self.reinit()

	def reinit(self):
		self._permissions = {}
		self.register_default_permissions()

	def register_permission(self, *permission: DirPermission):
		for perm in permission:
			self._permissions[perm.path] = perm

	def remove_permissions(self):
		self._permissions = {}

	@property
	def permissions(self):
		return self._permissions

	def register_default_permissions(self):
		self.register_permission(
			DirPermission("/etc/opsi", OPSICONFD_USER, OPSI_ADMIN_GROUP, 0o660, 0o770),
			DirPermission(
				"/var/log/opsi", OPSICONFD_USER, OPSI_ADMIN_GROUP, 0o660, 0o770
			),
			DirPermission(
				"/var/lib/opsi", OPSICONFD_USER, FILE_ADMIN_GROUP, 0o660, 0o770
			),
			DirPermission(
				"/etc/opsi/ssl", OPSICONFD_USER, OPSI_ADMIN_GROUP, 0o600, 0o750
			),
			FilePermission(
				"/etc/opsi/ssl/opsi-ca-cert.pem",
				OPSICONFD_USER,
				OPSI_ADMIN_GROUP,
				0o644,
			),
			DirPermission(
				"/var/lib/opsi/public",
				OPSICONFD_USER,
				FILE_ADMIN_GROUP,
				0o664,
				0o2775,
				modify_file_exe=False,
			),
			DirPermission(
				"/var/lib/opsi/depot",
				OPSICONFD_USER,
				FILE_ADMIN_GROUP,
				0o660,
				0o2770,
				modify_file_exe=False,
			),
			DirPermission(
				"/var/lib/opsi/repository",
				OPSICONFD_USER,
				FILE_ADMIN_GROUP,
				0o660,
				0o2770,
			),
			DirPermission(
				"/var/lib/opsi/depot/workbench",
				OPSICONFD_USER,
				FILE_ADMIN_GROUP,
				0o660,
				0o2770,
				modify_file_exe=False,
			),
		)

		pxe_dir = getPxeDirectory()
		if pxe_dir:
			self.register_permission(
				DirPermission(pxe_dir, OPSICONFD_USER, FILE_ADMIN_GROUP, 0o664, 0o775)
			)

		ssh_dir = _get_default_depot_user_ssh_dir()
		self.register_permission(
			DirPermission(
				ssh_dir,
				DEFAULT_DEPOT_USER,
				FILE_ADMIN_GROUP,
				0o640,
				0o750,
				recursive=False,
			),
			FilePermission(
				os.path.join(ssh_dir, "id_rsa"),
				DEFAULT_DEPOT_USER,
				FILE_ADMIN_GROUP,
				0o640,
			),
			FilePermission(
				os.path.join(ssh_dir, "id_rsa.pub"),
				DEFAULT_DEPOT_USER,
				FILE_ADMIN_GROUP,
				0o644,
			),
			FilePermission(
				os.path.join(ssh_dir, "authorized_keys"),
				DEFAULT_DEPOT_USER,
				FILE_ADMIN_GROUP,
				0o600,
			),
		)


def setRightsOnSSHDirectory(
	userId=None, groupId=None, path=_get_default_depot_user_ssh_dir()
):
	if not os.path.exists(path):
		raise FileNotFoundError(f"Path '{path}' not found")

	username = DEFAULT_DEPOT_USER
	groupname = FILE_ADMIN_GROUP

	if userId is not None:
		username = pwd.getpwuid(userId).pw_name
	if groupId is not None:
		groupname = grp.getgrgid(groupId).gr_name

	PermissionRegistry().register_permission(
		DirPermission(path, username, groupname, 0o640, 0o750, recursive=False),
		FilePermission(os.path.join(path, "id_rsa"), username, groupname, 0o640),
		FilePermission(os.path.join(path, "id_rsa.pub"), username, groupname, 0o644),
		FilePermission(
			os.path.join(path, "authorized_keys"), username, groupname, 0o600
		),
	)
	set_rights()


def set_rights(start_path="/"):  # pylint: disable=too-many-branches
	logger.debug("Setting rights on %s", start_path)
	permissions = PermissionRegistry().permissions
	permissions_to_process = []
	parent = None
	for path in sorted(list(permissions)):
		if not os.path.relpath(path, start_path).startswith(".."):
			# Sub path of start_path
			permissions_to_process.append(permissions[path])
		elif not os.path.relpath(start_path, path).startswith(".."):
			if not parent or len(parent.path) < len(path):
				parent = permissions[path]

	if parent:
		permissions_to_process.append(parent)

	processed_path = set()
	for permission in permissions_to_process:
		path = start_path
		if not os.path.relpath(permission.path, start_path).startswith(".."):
			# permission.path is sub path of start_path
			path = permission.path

		if path in processed_path or not os.path.lexists(path):
			continue
		processed_path.add(path)

		recursive = os.path.isdir(path) and getattr(permission, "recursive", True)

		logger.notice(
			"Setting rights %son '%s'", "recursively " if recursive else "", path
		)
		permission.apply(path)

		if not recursive:
			continue

		for root, dirs, files in os.walk(path, topdown=True):
			# logger.debug("Processing '%s'", root)
			for name in files:
				abspath = os.path.join(root, name)
				if abspath in permissions:
					continue
				if not permission.modify_file_exe and os.path.islink(abspath):
					continue
				permission.apply(abspath)

			remove_dirs = []
			for name in dirs:
				abspath = os.path.join(root, name)
				if abspath in permissions:
					remove_dirs.append(name)
					continue
				permission.apply(abspath)

			if remove_dirs:
				for name in remove_dirs:
					dirs.remove(name)


def setRights(path="/"):
	# Deprecated
	return set_rights(path)


def setPasswdRights():
	"""
	Setting correct permissions on ``/etc/opsi/passwd``.
	"""
	return set_rights(OPSI_PASSWD_FILE)


def getPxeDirectory():
	if isSLES() or isOpenSUSE():
		return "/var/lib/tftpboot/opsi"
	return "/tftpboot/linux"
