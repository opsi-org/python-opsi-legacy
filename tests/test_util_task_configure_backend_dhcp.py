# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the backend configuration.
"""

import os
from contextlib import contextmanager

import pytest

import OPSI.Util.Task.ConfigureBackend as backendConfigUtils
from OPSI.Util import md5sum
from OPSI.Util.Task.ConfigureBackend.DHCPD import (
	configureDHCPD,
	insertDHCPDRestartCommand,
)

from .helpers import mock

FAKE_RESTART_COMMAND = "service opsi-test-dhcpd restart"


@contextmanager
def disableSystemCallsForConfigureDHCPD():
	with mock.patch(
		"OPSI.Util.Task.ConfigureBackend.DHCPD.pwd.getpwnam", lambda x: (0, 0, 1234)
	):
		with mock.patch(
			"OPSI.Util.Task.ConfigureBackend.DHCPD.grp.getgrnam", lambda x: (0, 0, 5678)
		):
			with mock.patch("OPSI.Util.Task.ConfigureBackend.DHCPD.execute"):

				def getFakeRestartCommand(default=None):
					return FAKE_RESTART_COMMAND

				with mock.patch(
					"OPSI.Util.Task.ConfigureBackend.DHCPD.getDHCPDRestartCommand",
					getFakeRestartCommand,
				):
					with mock.patch("OPSI.Util.Task.ConfigureBackend.DHCPD.os.chown"):
						with mock.patch(
							"OPSI.Util.Task.ConfigureBackend.DHCPD.os.chmod"
						):
							with mock.patch(
								"OPSI.Util.Task.ConfigureBackend.DHCPD.insertDHCPDRestartCommand"
							):
								yield


def testConfigureDHCPWorksIfFileIsMissing(tempDir):
	configureDHCPD("not.here")


def testConfiguringDHCPDNextServer(tempDir):
	targetFile = os.path.join(tempDir, "dhcpd_1.conf")

	with open(targetFile, "w", encoding="utf-8") as target:
		target.write(
			"""
use-host-decl-names on;
subnet 192.168.0.0 netmask 255.255.0.0 {
	group {
		filename "linux/pxelinux.0";
		host bh-win7 {
			fixed-address 192.168.20.81;
			hardware ethernet 52:54:00:29:23:16;
		}
	}
}
"""
		)

	with disableSystemCallsForConfigureDHCPD():
		configureDHCPD(targetFile)

	with open(targetFile, encoding="utf-8") as target:
		assert any(
			"next-server" in line for line in target
		), "next-server not fonud in new file."


def testConfiguringDHCPDBackendWithEmptyFile(tempDir):
	filename = "dhcpd_test.conf"
	with open(filename, "x", encoding="utf-8"):
		pass

	oldHash = md5sum(filename)

	with disableSystemCallsForConfigureDHCPD():
		configureDHCPD(filename)

	newHash = md5sum(filename)

	assert oldHash != newHash


def testConfiguringPatchesDHCPDBackendConfig(tempDir):
	filename = "dhcpd_test.conf"
	with open(filename, "x", encoding="utf-8"):
		pass

	funcMock = mock.Mock()
	with disableSystemCallsForConfigureDHCPD():
		with mock.patch(
			"OPSI.Util.Task.ConfigureBackend.DHCPD.insertDHCPDRestartCommand", funcMock
		):
			configureDHCPD(filename)

	backendConfigTarget = os.path.join("/etc", "opsi", "backends", "dhcpd.conf")
	funcMock.assert_called_with(backendConfigTarget, FAKE_RESTART_COMMAND)


def testConfiguringCreatesBackupFile(tempDir):
	filename = "dhcpd_test.conf"
	with open(filename, "w", encoding="utf-8"):
		pass

	assert len(os.listdir(tempDir)) == 1, "Too many files in temp directory"

	with disableSystemCallsForConfigureDHCPD():
		with mock.patch(
			"OPSI.Util.Task.ConfigureBackend.DHCPD.insertDHCPDRestartCommand",
			mock.Mock(),
		):
			configureDHCPD(filename)

	assert len(os.listdir(tempDir)) == 2, "No backup was created"


@pytest.mark.parametrize(
	"reload_command, expected_reload_command",
	(
		('u"sudo restart-dhcp-server"', "sudo service opsi-test-dhcpd restart"),
		('"sudo restart-dhcp-server"', "sudo service opsi-test-dhcpd restart"),
		('"restart-dhcp-server"', "service opsi-test-dhcpd restart"),
		('u"restart-dhcp-server"', "service opsi-test-dhcpd restart"),
	),
)
def testUpdatingDHCPDBackendConfigReplacesCurrentCommand(
	tempDir, reload_command, expected_reload_command
):
	target = os.path.join(tempDir, "dhcpd.test.conf")

	with open(target, "w", encoding="utf-8") as file:
		file.write(
			"""
# -*- coding: utf-8 -*-

module = 'DHCPD'

localip = socket.gethostbyname(socket.getfqdn())

config = {
"dhcpdOnDepot":			False,
"dhcpdConfigFile":		 u"/etc/dhcp3/dhcpd.conf",
# "reloadConfigCommand":	 "restart-dhcp-server",
"reloadConfigCommand":	 """
			+ reload_command
			+ """,
"fixedAddressFormat":	  u"IP", # or FQDN
"defaultClientParameters": { "next-server": localip, "filename": u"linux/pxelinux.0" }
}
"""
		)

	def getFakeRestartCommand(default=None):
		return FAKE_RESTART_COMMAND

	with mock.patch(
		"OPSI.Util.Task.ConfigureBackend.DHCPD.getDHCPDRestartCommand",
		getFakeRestartCommand,
	):
		insertDHCPDRestartCommand(target, FAKE_RESTART_COMMAND)

	config = backendConfigUtils.getBackendConfiguration(target)

	assert expected_reload_command == config["reloadConfigCommand"]
	assert not config["dhcpdOnDepot"]
	assert "/etc/dhcp3/dhcpd.conf" == config["dhcpdConfigFile"]
	assert "IP" == config["fixedAddressFormat"]
	assert config["defaultClientParameters"]
	assert "linux/pxelinux.0" == config["defaultClientParameters"]["filename"]
