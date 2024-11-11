# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the setting of rights.
"""

import grp
import os
import pwd
from contextlib import contextmanager

import pytest
from OPSI.Util.Task.Rights import (
	DirPermission,
	FilePermission,
	PermissionRegistry,
	set_rights,
	setRightsOnSSHDirectory,
)

from .helpers import mock

OS_CHECK_FUNCTIONS = ["isRHEL", "isCentOS", "isSLES", "isOpenSUSE", "isUCS"]


@pytest.fixture
def patchUserInfo():
	"Calls to find uid / gid will always succeed."
	uid = 1234
	gid = 5678
	with mock.patch(
		"OPSI.Util.Task.Rights.pwd.getpwnam", return_value=(None, None, uid)
	):
		with mock.patch(
			"OPSI.Util.Task.Rights.grp.getgrnam", return_value=(None, None, gid)
		):
			yield uid, gid


@pytest.fixture
def some_secondary_group_name():
	user_id = os.getuid()
	user = pwd.getpwuid(user_id)
	primary_gid = user.pw_gid
	for gid in os.getgrouplist(user.pw_name, primary_gid):
		if gid != primary_gid:
			return grp.getgrgid(gid).gr_name
	pytest.skip("No group for test found. Aborting.")


def test_permission_registry():
	registry = PermissionRegistry()
	permission_count = len(registry.permissions)
	assert permission_count > 0

	registry.remove_permissions()
	assert len(registry.permissions) == 0

	registry.register_permission(
		DirPermission("/tmp", None, None, 0o600, 0o700, recursive=True)
	)
	assert len(registry.permissions) == 1

	registry.register_default_permissions()
	assert len(registry.permissions) == permission_count + 1

	registry.register_permission(
		DirPermission("/tmp", None, None, 0o600, 0o700, recursive=True)
	)
	assert len(registry.permissions) == permission_count + 1

	registry.reinit()
	assert len(registry.permissions) == permission_count


def test_set_rights_recursive(tempDir, some_secondary_group_name):
	registry = PermissionRegistry()

	user_id = os.getuid()
	user = pwd.getpwuid(user_id)
	primary_gid = user.pw_gid
	username = user.pw_name
	some_secondary_group_id = grp.getgrnam(some_secondary_group_name).gr_gid

	dir1 = os.path.join(tempDir, "dir1")
	fil1 = os.path.join(dir1, "fil1")
	fil2 = os.path.join(dir1, "fil2")
	dir2 = os.path.join(dir1, "dir2")
	fil3 = os.path.join(dir2, "fil3")
	fil4 = os.path.join(dir2, "fil4")
	dir3 = os.path.join(dir1, "dir3")
	fil5 = os.path.join(dir3, "fil5")
	fil6 = os.path.join(dir3, "fil6")
	fil7 = os.path.join(dir3, "fil7")
	dir4 = os.path.join(dir2, "dir4")

	for path in (dir1, dir2, dir3, dir4):
		os.mkdir(path)
		os.chmod(path, 0o707)
	for path in (fil1, fil2, fil3, fil4, fil5, fil6, fil7):
		open(path, "w").close()
		os.chmod(path, 0o606)

	for permission in (
		DirPermission(
			dir1, username, some_secondary_group_name, 0o666, 0o777, recursive=True
		),
		DirPermission(dir2, None, None, 0o600, 0o700, recursive=True),
		FilePermission(fil1, None, None, 0o660),
		FilePermission(fil6, None, None, 0o660),
		FilePermission(fil7, username, some_secondary_group_name, 0o606),
	):
		registry.register_permission(permission)

	set_rights(dir1)

	for path in (dir1, dir2, dir3, dir4, fil1, fil2, fil3, fil4, fil5, fil6, fil7):
		assert os.stat(path).st_uid == user_id

	for path in (dir1, dir3, fil2, fil5, fil7):
		assert os.stat(path).st_gid == some_secondary_group_id
	for path in (dir2, dir4, fil1, fil3, fil4, fil6):
		assert os.stat(path).st_gid == primary_gid

	assert os.stat(dir1).st_mode & 0o7777 == 0o777
	assert os.stat(fil1).st_mode & 0o7777 == 0o660
	assert os.stat(fil2).st_mode & 0o7777 == 0o666
	assert os.stat(dir2).st_mode & 0o7777 == 0o700
	assert os.stat(fil3).st_mode & 0o7777 == 0o600
	assert os.stat(fil4).st_mode & 0o7777 == 0o600
	assert os.stat(dir3).st_mode & 0o7777 == 0o777
	assert os.stat(fil5).st_mode & 0o7777 == 0o666
	assert os.stat(fil6).st_mode & 0o7777 == 0o660
	assert os.stat(fil7).st_mode & 0o7777 == 0o606
	assert os.stat(dir4).st_mode & 0o7777 == 0o700


def test_set_rights_modify_file_exe(tempDir):
	registry = PermissionRegistry()

	dir1 = os.path.join(tempDir, "dir1")
	fil1 = os.path.join(dir1, "fil1")
	fil2 = os.path.join(dir1, "fil2")
	fil3 = os.path.join(dir1, "fil3")

	for path in (dir1,):
		os.mkdir(path)
		os.chmod(path, 0o777)
	for path in (fil1, fil2, fil3):
		open(path, "w").close()
	os.chmod(fil1, 0o666)
	os.chmod(fil2, 0o775)
	os.chmod(fil3, 0o777)

	registry.register_permission(
		DirPermission(dir1, None, None, 0o666, 0o770, modify_file_exe=False)
	)

	set_rights(dir1)

	assert os.stat(dir1).st_mode & 0o7777 == 0o770
	assert os.stat(fil1).st_mode & 0o7777 == 0o666
	assert os.stat(fil2).st_mode & 0o7777 == 0o777
	assert os.stat(fil3).st_mode & 0o7777 == 0o777

	os.chmod(fil1, 0o666)
	os.chmod(fil2, 0o775)
	os.chmod(fil3, 0o777)

	registry.register_permission(
		DirPermission(dir1, None, None, 0o660, 0o770, modify_file_exe=False)
	)

	set_rights(dir1)

	assert os.stat(dir1).st_mode & 0o7777 == 0o770
	assert os.stat(fil1).st_mode & 0o7777 == 0o660
	assert os.stat(fil2).st_mode & 0o7777 == 0o770
	assert os.stat(fil3).st_mode & 0o7777 == 0o770

	os.chmod(fil1, 0o666)
	os.chmod(fil2, 0o775)
	os.chmod(fil3, 0o777)

	registry.register_permission(
		DirPermission(dir1, None, None, 0o660, 0o770, modify_file_exe=True)
	)

	set_rights(dir1)

	assert os.stat(dir1).st_mode & 0o7777 == 0o770
	assert os.stat(fil1).st_mode & 0o7777 == 0o660
	assert os.stat(fil2).st_mode & 0o7777 == 0o660
	assert os.stat(fil3).st_mode & 0o7777 == 0o660


def test_set_rights_file_in_dir(tempDir):
	registry = PermissionRegistry()
	registry.remove_permissions()

	dir1 = os.path.join(tempDir, "dir1")
	dir2 = os.path.join(dir1, "dir2")
	fil1 = os.path.join(dir2, "fil1")
	fil2 = os.path.join(dir2, "fil2")

	for path in (dir1, dir2):
		os.mkdir(path)
		os.chmod(path, 0o777)
	for path in (fil1, fil2):
		open(path, "w").close()
		os.chmod(path, 0o666)

	registry.register_permission(
		DirPermission(dir1, None, None, 0o660, 0o770, recursive=True),
		DirPermission(dir2, None, None, 0o600, 0o700, recursive=True),
	)

	set_rights(fil1)
	assert os.stat(fil1).st_mode & 0o7777 == 0o600
	assert os.stat(fil2).st_mode & 0o7777 == 0o666

	set_rights(fil2)
	assert os.stat(fil2).st_mode & 0o7777 == 0o600


@pytest.fixture(scope="session")
def currentUserId():
	yield os.getuid()


@pytest.fixture
def nonRootUserId():
	userId = os.getuid()
	isRoot = os.geteuid() == 0
	changedUid = None

	if isRoot:
		for uid in range(2, 60000):
			try:
				pwd.getpwuid(uid)
				changedUid = uid
				break
			except KeyError:
				pass
		else:
			pytest.skip("No userId for test found. Aborting.")

		if userId == changedUid:
			pytest.skip("Could not find another user.")

		return changedUid
	else:
		return -1


@pytest.fixture(scope="session")
def currentGroupId():
	yield os.getgid()


@pytest.fixture
def nonRootGroupId(currentGroupId):
	for gid in range(2, 60000):
		try:
			grp.getgrgid(gid)
			if currentGroupId == gid:
				# We do not want to use the same group ID.
				continue

			return gid
		except KeyError:
			pass
	pytest.skip("No group for test found. Aborting.")


@contextmanager
def disableOSChecks(functions):
	try:
		func = functions.pop()
		with mock.patch("OPSI.Util.Task.Rights.{0}".format(func), return_value=False):
			with disableOSChecks(functions):
				yield
	except IndexError:
		yield


def testSetRightsOnSSHDirectory(tempDir):
	groupId = os.getgid()
	userId = os.getuid()

	sshDir1 = os.path.join(tempDir, "ssh1")
	os.mkdir(sshDir1)

	PermissionRegistry().remove_permissions()

	expectedFilemod = {
		os.path.join(sshDir1, "id_rsa"): 0o640,
		os.path.join(sshDir1, "id_rsa.pub"): 0o644,
		os.path.join(sshDir1, "authorized_keys"): 0o600,
	}

	for filename in expectedFilemod:
		open(filename, "w").close()
		os.chmod(filename, 0o666)

	setRightsOnSSHDirectory(userId=userId, groupId=groupId, path=sshDir1)

	for filename, mod in expectedFilemod.items():
		assert os.path.exists(filename)
		stats = os.stat(filename)
		assert stats.st_mode & 0o7777 == mod
		assert stats.st_gid == groupId
		assert stats.st_uid == userId

	with mock.patch(
		"OPSI.Util.Task.Rights._get_default_depot_user_ssh_dir", lambda: sshDir2
	):
		with mock.patch("OPSI.Util.Task.Rights.DEFAULT_DEPOT_USER", None):
			with mock.patch("OPSI.Util.Task.Rights.FILE_ADMIN_GROUP", None):
				sshDir2 = os.path.join(tempDir, "ssh2")
				os.mkdir(sshDir2)

				PermissionRegistry().reinit()

				expectedFilemod = {
					os.path.join(sshDir2, "id_rsa"): 0o640,
					os.path.join(sshDir2, "id_rsa.pub"): 0o644,
					os.path.join(sshDir2, "authorized_keys"): 0o600,
				}

				for filename in expectedFilemod:
					open(filename, "w").close()
					os.chmod(filename, 0o666)

				set_rights(sshDir2)

				for filename, mod in expectedFilemod.items():
					assert os.path.exists(filename)
					stats = os.stat(filename)
					assert stats.st_mode & 0o7777 == mod
					assert stats.st_gid == groupId
					assert stats.st_uid == userId
