# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing functionality of OPSI.Systen.Posix

Various unittests to test functionality of python-opsi.
"""

import os
import re

import psutil
import pytest

import OPSI.System.Posix as Posix

from .helpers import mock

xorg_running = False
for proc in psutil.process_iter():
	if proc.name().lower() == "xorg":
		xorg_running = True
		break


def testGetBlockDeviceContollerInfo():
	data = [
		"/0/100/1f.2			   storage		82801JD/DO (ICH10 Family) SATA AHCI Controller [8086:3A02]",
		"/0/100/1f.3			   bus			82801JD/DO (ICH10 Family) SMBus Controller [8086:3A60]",
		"/0/1		  scsi0	   storage",
		"/0/1/0.0.0	/dev/sda	disk		   500GB ST3500418AS",
		"/0/1/0.0.0/1  /dev/sda1   volume		 465GiB Windows FAT volume",
	]

	deviceInfo = Posix.getBlockDeviceContollerInfo("dev/sda", data)
	assert deviceInfo

	assert "dev/sda" == deviceInfo["device"]
	assert "8086" == deviceInfo["vendorId"]
	assert "/0/100/1f.2" == deviceInfo["hwPath"]
	assert "82801JD/DO (ICH10 Family) SATA AHCI Controller" == deviceInfo["description"]
	assert "3A02" == deviceInfo["deviceId"]


@pytest.mark.skipif(not xorg_running, reason="Xorg not running")
def testGetActiveSessionIds():
	ids = Posix.getActiveSessionIds()
	assert len(ids) > 0, "No sessions found"
	assert re.search(r"^:\d+$", ids[0])


@pytest.mark.skipif(not xorg_running, reason="Xorg not running")
def testGetActiveSessionId():
	id = Posix.getActiveSessionId()
	assert re.search(r"^:\d+$", id)


def testGetNetworkInterfaces():
	# TODO: make this independent from the underlying hardware...
	# Idea: prepare a file with information, pass the filename
	# to the function and read from that.
	Posix.getNetworkInterfaces()


def testReadingDHCPLeasesFile(test_data_path):
	leasesFile = os.path.join(test_data_path, "system", "posix", "dhclient.leases")
	assert os.path.exists(leasesFile)

	dhcpConfig = Posix.getDHCPResult("eth0", leasesFile)
	assert "172.16.166.102" == dhcpConfig["fixed-address"]
	assert "linux/pxelinux.0" == dhcpConfig["filename"]
	assert "255.255.255.0" == dhcpConfig["subnet-mask"]
	assert "172.16.166.1" == dhcpConfig["routers"]
	assert "172.16.166.1" == dhcpConfig["domain-name-servers"]
	assert "172.16.166.1" == dhcpConfig["dhcp-server-identifier"]
	assert "win7client" == dhcpConfig["host-name"]
	assert "vmnat.local" == dhcpConfig["domain-name"]
	assert "3 2014/05/28 12:31:42" == dhcpConfig["renew"]
	assert "3 2014/05/28 12:36:36" == dhcpConfig["rebind"]
	assert "3 2014/05/28 12:37:51" == dhcpConfig["expire"]


def testGetHarddisks():
	testData = [
		"/dev/sda:  19922944",
		"total: 19922944 blocks",
	]

	with mock.patch("OPSI.System.Posix.execute"):
		disks = Posix.getHarddisks(data=testData)

	assert 1 == len(disks)


def testGetHarddisksIgnoresEverythingOutsideDev():
	testData = [
		"/no/dev/sdb:  19922944",
		"/dev/sda:  19922944",
		"/tmp/sda:  19922944",
		"total: 19922944 blocks",
	]

	with mock.patch("OPSI.System.Posix.execute"):
		disks = Posix.getHarddisks(data=testData)

	assert 1 == len(disks)


def testGetHarddisksFailsIfNoDisks():
	testData = [
		"/no/dev/sdb:  19922944",
		"total: 19922944 blocks",
	]

	with mock.patch("OPSI.System.Posix.execute"):
		with pytest.raises(Exception):
			Posix.getHarddisks(data=testData)


@pytest.fixture
def hardwareConfigAndHardwareInfo():
	config = [
		{
			"Values": [
				{
					"Opsi": "name",
					"WMI": "Name",
					"UI": "Name",
					"Linux": "id",
					"Scope": "i",
					"Type": "varchar(100)",
				},
				{
					"Opsi": "description",
					"WMI": "Description",
					"UI": "Description",
					"Linux": "description",
					"Scope": "g",
					"Type": "varchar(100)",
				},
				{
					"Opsi": "vendor",
					"WMI": "Manufacturer",
					"UI": "Vendor",
					"Linux": "vendor",
					"Scope": "g",
					"Type": "varchar(50)",
				},
				{
					"Opsi": "model",
					"WMI": "Model",
					"UI": "Model",
					"Linux": "product",
					"Scope": "g",
					"Type": "varchar(100)",
				},
				{
					"Opsi": "serialNumber",
					"WMI": "SerialNumber",
					"UI": "Serial number",
					"Linux": "serial",
					"Scope": "i",
					"Type": "varchar(50)",
				},
				{
					"Opsi": "systemType",
					"WMI": "SystemType",
					"UI": "Type",
					"Linux": "configuration/chassis",
					"Scope": "i",
					"Type": "varchar(50)",
				},
				{
					"Opsi": "totalPhysicalMemory",
					"WMI": "TotalPhysicalMemory",
					"UI": "Physical Memory",
					"Linux": "core/memory/size",
					"Scope": "i",
					"Type": "bigint",
					"Unit": "Byte",
				},
				{
					"Opsi": "dellexpresscode",
					"Python": "str(int(#{'COMPUTER_SYSTEM':'serialNumber','CHASSIS':'serialNumber'}#,36))",
					"Cmd": "#dellexpresscode\\dellexpresscode.exe#.split('=')[1]",
					"UI": "Dell Expresscode",
					"Scope": "i",
					"Type": "varchar(50)",
					"Condition": "vendor=[dD]ell*",
				},
			],
			"Class": {
				"Opsi": "COMPUTER_SYSTEM",
				"WMI": "select * from Win32_ComputerSystem",
				"UI": "Computer",
				"Linux": "[lshw]system",
			},
		},
	]

	hardwareInfo = {
		"COMPUTER_SYSTEM": [
			{
				"totalPhysicalMemory": "2147483648",
				"vendor": "Dell Inc.",
				"name": "de-sie-gar-hk01",
				"systemType": "desktop",
				"serialNumber": "",
				"model": "OptiPlex 755",
				"description": "Desktop Computer",
			}
		]
	}

	yield config, hardwareInfo


def testHardwareExtendedInventory(hardwareConfigAndHardwareInfo):
	config, hardwareInfo = hardwareConfigAndHardwareInfo
	result = Posix.hardwareExtendedInventory(config, hardwareInfo)

	expected = {
		"COMPUTER_SYSTEM": [
			{
				"dellexpresscode": None,
				"description": "Desktop Computer",
				"model": "OptiPlex 755",
				"name": "de-sie-gar-hk01",
				"serialNumber": "",
				"systemType": "desktop",
				"totalPhysicalMemory": "2147483648",
				"vendor": "Dell Inc.",
			}
		]
	}
	assert {} != result
	assert expected == result


def testHardwareExtendedInventoryReturnsSafelyWithoutConfig(
	hardwareConfigAndHardwareInfo,
):
	config, hardwareInfo = hardwareConfigAndHardwareInfo
	assert {} == Posix.hardwareExtendedInventory({}, hardwareInfo)


def testGetSambaServiceNameGettingDefaultIfNothingElseParsed():
	with mock.patch("OPSI.System.Posix.getServiceNames"):
		assert "blabla" == Posix.getSambaServiceName(
			default="blabla", staticFallback=False
		)


@pytest.mark.parametrize("values", ([], set("abc")))
def testGetSambaServiceNameFailsIfNoServiceFound(values):
	with mock.patch(
		"OPSI.System.Posix.getServiceNames", mock.Mock(return_value=values)
	):
		with pytest.raises(RuntimeError):
			Posix.getSambaServiceName(staticFallback=False)


@pytest.mark.parametrize(
	"expectedName, services",
	(
		("smb", set(["abc", "smb", "def"])),
		("smbd", set(["abc", "smbd", "def"])),
		("samba", set(["abc", "samba", "def"])),
	),
)
def testGetSambaServiceNameGettingFoundSambaServiceName(expectedName, services):
	with mock.patch("OPSI.System.Posix._SAMBA_SERVICE_NAME", None):
		with mock.patch(
			"OPSI.System.Posix.getServiceNames", mock.Mock(return_value=services)
		):
			assert expectedName == Posix.getSambaServiceName()


def testGetServiceNameParsingFromSystemd():
	output = [
		"iprdump.service - LSB: Start the ipr dump daemon",
		"   Loaded: loaded (/etc/rc.d/init.d/iprdump)",
		"   Active: active (running) since Di 2014-10-07 15:53:35 CEST; 4min 14s ago",
		"  Process: 572 ExecStart=/etc/rc.d/init.d/iprdump start (code=exited, status=0/SUCCESS)",
		" Main PID: 581 (iprdump)",
		"   CGroup: /system.slice/iprdump.service",
		"		   └─581 /sbin/iprdump --daemon",
		"",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid iprdump[572]: Starting iprdump: [  OK  ]",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid systemd[1]: Started LSB: Start the ipr dump daemon.",
		"iprinit.service - LSB: Start the ipr init daemon",
		"   Loaded: loaded (/etc/rc.d/init.d/iprinit)",
		"   Active: active (running) since Di 2014-10-07 15:53:35 CEST; 4min 15s ago",
		"  Process: 537 ExecStart=/etc/rc.d/init.d/iprinit start (code=exited, status=0/SUCCESS)",
		" Main PID: 566 (iprinit)",
		"   CGroup: /system.slice/iprinit.service",
		"		   └─566 /sbin/iprinit --daemon",
		"",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid iprinit[537]: Starting iprinit: [  OK  ]",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid systemd[1]: Started LSB: Start the ipr init daemon.",
		"iprupdate.service - LSB: Start the iprupdate utility",
		"   Loaded: loaded (/etc/rc.d/init.d/iprupdate)",
		"   Active: active (running) since Di 2014-10-07 15:53:35 CEST; 4min 15s ago",
		"  Process: 525 ExecStart=/etc/rc.d/init.d/iprupdate start (code=exited, status=0/SUCCESS)",
		" Main PID: 567 (iprupdate)",
		"   CGroup: /system.slice/iprupdate.service",
		"		   └─567 /sbin/iprupdate --daemon",
		"",
		"Okt 07 15:53:34 stb-40-srv-106.test.invalid systemd[1]: Starting LSB: Start the iprupdate utility...",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid iprupdate[525]: Starting iprupdate: [  OK  ]",
		"Okt 07 15:53:35 stb-40-srv-106.test.invalid systemd[1]: Started LSB: Start the iprupdate utility.",
		"Netconsole-Modul nicht geladen",
		"Konfigurierte Geräte:",
		"lo ens18",
		"Derzeit aktive Geräte:",
		"lo ens18",
	]

	assert set(["iprdump", "iprinit", "iprupdate"]) == Posix.getServiceNames(
		_serviceStatusOutput=output
	)


def testParsingSystemdOutputFromCentOS7():
	output = [
		"UNIT FILE								   STATE   ",
		"proc-sys-fs-binfmt_misc.automount		   static  ",
		"tmp.mount								   disabled",
		"brandbot.path							   disabled",
		"systemd-ask-password-console.path		   static  ",
		"session-1.scope							 static  ",
		"session-c2.scope							static  ",
		"dhcpd.service							   disabled",
		"dhcpd6.service							  disabled",
		"getty@.service							  enabled ",
		"initrd-cleanup.service					  static  ",
		"smb.service								 enabled ",
		"systemd-backlight@.service				  static  ",
		"-.slice									 static  ",
		"machine.slice							   static  ",
		"syslog.socket							   static  ",
		"systemd-udevd-kernel.socket				 static  ",
		"basic.target								static  ",
		"systemd-tmpfiles-clean.timer				static  ",
		"",
		"219 unit files listed.",
	]

	expectedServices = set(
		["dhcpd", "dhcpd6", "getty@", "initrd-cleanup", "smb", "systemd-backlight@"]
	)
	assert expectedServices == Posix.getServiceNames(_serviceStatusOutput=output)


def testExecutingWithWaitForEndingWorks():
	"""
	waitForEnding must be an accepted keyword.

	This is to have the same keywords and behaviours on Windows and
	Linux.
	"""
	Posix.execute("echo bla", waitForEnding=True)


def testExecutingWithShellWorks():
	"""
	'shell' must be an accepted keyword.

	This is to have the same keywords and behaviours on Windows and
	Linux.
	"""
	Posix.execute("echo bla", shell=True)
