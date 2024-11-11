# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the backend initialisation.
"""

import OPSI.Util.Task.InitializeBackend as initBackend


def testGettingServerConfig():
	networkConfig = {
		"ipAddress": "192.168.12.34",
		"hardwareAddress": "acabacab",
		"subnet": "192.168.12.0",
		"netmask": "255.255.255.0",
	}
	fqdn = "blackwidow.test.invalid"

	config = initBackend._getServerConfig(fqdn, networkConfig)  # pylint: disable=protected-access

	assert config["id"] == fqdn
	for key in (
		"opsiHostKey",
		"description",
		"notes",
		"inventoryNumber",
		"masterDepotId",
	):
		assert config[key] is None

	assert config["ipAddress"] == networkConfig["ipAddress"]
	assert config["hardwareAddress"] == networkConfig["hardwareAddress"]
	assert config["maxBandwidth"] == 0
	assert config["isMasterDepot"] is True
	assert config["depotLocalUrl"] == "file:///var/lib/opsi/depot"
	assert config["depotRemoteUrl"] == f"smb://{fqdn}/opsi_depot"
	assert config["depotWebdavUrl"] == f"webdavs://{fqdn}:4447/depot"
	assert config["repositoryLocalUrl"] == "file:///var/lib/opsi/repository"
	assert config["repositoryRemoteUrl"] == f"webdavs://{fqdn}:4447/repository"
	assert config["workbenchLocalUrl"] == "file:///var/lib/opsi/workbench"
	assert config["workbenchRemoteUrl"] == f"smb://{fqdn}/opsi_workbench"
	assert (
		config["networkAddress"]
		== f"{networkConfig['subnet']}/{networkConfig['netmask']}"
	)
