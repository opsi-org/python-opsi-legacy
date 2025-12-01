# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

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

	config = initBackend._getServerConfig(fqdn, networkConfig)

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
