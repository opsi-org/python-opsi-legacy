# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend mixin for testing software / hardware audit functionality.
"""

import pytest

from OPSI.Object import (
	AuditSoftware,
	AuditSoftwareOnClient,
	AuditHardware,
	AuditHardwareOnHost,
	AuditSoftwareToLicensePool,
)

from .test_hosts import getClients
from .test_products import getLocalbootProducts
from .test_license_management import createLicensePool


def getAuditHardwares():
	auditHardware1 = AuditHardware(
		hardwareClass="COMPUTER_SYSTEM",
		description="a pc",
		vendor="Dell",
		model="xyz",
	)

	auditHardware2 = AuditHardware(
		hardwareClass="COMPUTER_SYSTEM",
		description=None,
		vendor="HP",
		model="0815",
	)

	auditHardware3 = AuditHardware(
		hardwareClass="BASE_BOARD",
		name="MSI 2442",
		description="AMD motherboard",
		vendor="MSI",
		model="äüöüöäüöüäüööüö11",
		product=None,
	)

	auditHardware4 = AuditHardware(
		hardwareClass="CHASSIS",
		name="Manufacturer XX-112",
		description="A chassis",
		chassisType="Desktop",
	)

	return auditHardware1, auditHardware2, auditHardware3, auditHardware4


def getAuditSoftwares(product=None):
	auditSoftware1 = AuditSoftware(
		name="A software",
		version="1.0.21",
		subVersion="",
		language="",
		architecture="",
		windowsSoftwareId="{480aa013-93a7-488c-89c3-b985b6c8440a}",
		windowsDisplayName="A Software",
		windowsDisplayVersion="1.0.21",
		installSize=129012992,
	)

	if product is None:
		product = getLocalbootProducts()[0]

	auditSoftware2 = AuditSoftware(
		name=product.getName(),
		version=product.getProductVersion(),
		subVersion="",
		language="de",
		architecture="x64",
		windowsSoftwareId=product.getWindowsSoftwareIds()[0],
		windowsDisplayName=product.getName(),
		windowsDisplayVersion=product.getProductVersion(),
		installSize=217365267,
	)

	auditSoftware3 = AuditSoftware(
		name="my software",
		version="",
		subVersion="12;00;01",
		language="",
		architecture="",
		windowsSoftwareId="my software",
		windowsDisplayName="",
		windowsDisplayVersion="",
		installSize=-1,
	)

	auditSoftware4 = AuditSoftware(
		name="söftwäre\n;?&%$$$§$§§$$$§$",
		version="\\0012",
		subVersion="\n",
		language="de",
		architecture="",
		windowsSoftwareId="söftwäre\n;?&%$$$§$§§$$$§$",
		windowsDisplayName="söftwäre\n;?&%$$$§$§§$$$§$",
		windowsDisplayVersion="\n\r",
		installSize=-1,
	)

	return auditSoftware1, auditSoftware2, auditSoftware3, auditSoftware4


def getAuditSoftwareOnClient(auditSoftwares, clients):
	auditSoftware1, auditSoftware2, auditSoftware3 = auditSoftwares[:3]
	client1, client2 = clients[:2]

	auditSoftwareOnClient1 = AuditSoftwareOnClient(
		name=auditSoftware1.getName(),
		version=auditSoftware1.getVersion(),
		subVersion=auditSoftware1.getSubVersion(),
		language=auditSoftware1.getLanguage(),
		architecture=auditSoftware1.getArchitecture(),
		clientId=client1.getId(),
		uninstallString="c:\\programme\\a software\\unistall.exe /S",
		binaryName="",
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=2,
		lastUsed="2009-02-12 09:48:22",
	)

	auditSoftwareOnClient2 = AuditSoftwareOnClient(
		name=auditSoftware2.getName(),
		version=auditSoftware2.getVersion(),
		subVersion=auditSoftware2.getSubVersion(),
		language=auditSoftware2.getLanguage(),
		architecture=auditSoftware2.getArchitecture(),
		clientId=client1.getId(),
		uninstallString="msiexec /x %s" % auditSoftware2.getWindowsSoftwareId(),
		binaryName="",
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=None,
		lastUsed=None,
	)

	auditSoftwareOnClient3 = AuditSoftwareOnClient(
		name=auditSoftware3.getName(),
		version=auditSoftware3.getVersion(),
		subVersion=auditSoftware3.getSubVersion(),
		language=auditSoftware3.getLanguage(),
		architecture=auditSoftware3.getArchitecture(),
		clientId=client1.getId(),
		uninstallString=None,
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=0,
		lastUsed="2009-08-01 14:11:00",
	)

	auditSoftwareOnClient4 = AuditSoftwareOnClient(
		name=auditSoftware2.getName(),
		version=auditSoftware2.getVersion(),
		subVersion=auditSoftware2.getSubVersion(),
		language=auditSoftware2.getLanguage(),
		architecture=auditSoftware2.getArchitecture(),
		clientId=client2.getId(),
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=0,
		lastUsed=None,
	)

	return (
		auditSoftwareOnClient1,
		auditSoftwareOnClient2,
		auditSoftwareOnClient3,
		auditSoftwareOnClient4,
	)


def getAuditHardwareOnHost(auditHardwares=None, clients=None):
	auditHardwares = auditHardwares or getAuditHardwares()
	auditHardware1, auditHardware2, auditHardware3 = auditHardwares[:3]

	clients = clients or getClients()
	client1, client2, client3 = clients[:3]

	auditHardwareOnHost1 = AuditHardwareOnHost(
		hostId=client1.getId(),
		hardwareClass="COMPUTER_SYSTEM",
		description=auditHardware1.description,
		vendor=auditHardware1.vendor,
		model=auditHardware1.model,
		serialNumber="843391034-2192",
		systemType="Desktop",
		totalPhysicalMemory=1073741824,
	)

	auditHardwareOnHost2 = AuditHardwareOnHost(
		hostId=client2.getId(),
		hardwareClass="COMPUTER_SYSTEM",
		description=auditHardware1.description,
		vendor=auditHardware1.vendor,
		model=auditHardware1.model,
		serialNumber="142343234-9571",
		systemType="Desktop",
		totalPhysicalMemory=1073741824,
	)

	auditHardwareOnHost3 = AuditHardwareOnHost(
		hostId=client3.getId(),
		hardwareClass="COMPUTER_SYSTEM",
		description=auditHardware2.description,
		vendor=auditHardware2.vendor,
		model=auditHardware2.model,
		serialNumber="a63c09dd234a213",
		systemType=None,
		totalPhysicalMemory=536870912,
	)

	auditHardwareOnHost4 = AuditHardwareOnHost(
		hostId=client1.getId(),
		hardwareClass="BASE_BOARD",
		name=auditHardware3.name,
		description=auditHardware3.description,
		vendor=auditHardware3.vendor,
		model=auditHardware3.model,
		product=auditHardware3.product,
		serialNumber="xxxx-asjdks-sll3kf03-828112",
	)

	auditHardwareOnHost5 = AuditHardwareOnHost(
		hostId=client2.getId(),
		hardwareClass="BASE_BOARD",
		name=auditHardware3.name,
		description=auditHardware3.description,
		vendor=auditHardware3.vendor,
		model=auditHardware3.model,
		product=auditHardware3.product,
		serialNumber="xxxx-asjdks-sll3kf03-213791",
	)

	auditHardwareOnHost6 = AuditHardwareOnHost(
		hostId=client3.getId(),
		hardwareClass="BASE_BOARD",
		name=auditHardware3.name,
		description=auditHardware3.description,
		vendor=auditHardware3.vendor,
		model=auditHardware3.model,
		product=auditHardware3.product,
		serialNumber="xxxx-asjdks-sll3kf03-132290",
	)

	return (
		auditHardwareOnHost1,
		auditHardwareOnHost2,
		auditHardwareOnHost3,
		auditHardwareOnHost4,
		auditHardwareOnHost5,
		auditHardwareOnHost6,
	)


def test_insertAuditHardwareOnHost(hardwareAuditBackendWithHistory):
	backend = hardwareAuditBackendWithHistory

	clients = getClients()
	auditHardwares = getAuditHardwares()
	ahoh = getAuditHardwareOnHost(auditHardwares, clients)
	backend.auditHardwareOnHost_createObjects(ahoh)

	historyRelevantActions = 0

	auditHardwareOnHost4update = ahoh[3].clone()
	auditHardwareOnHost4update.setLastseen("2000-01-01 01:01:01")
	backend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)
	historyRelevantActions += 1

	auditHardwareOnHosts = backend.auditHardwareOnHost_getObjects()
	assert len(auditHardwareOnHosts) == len(ahoh) + historyRelevantActions

	auditHardwareOnHosts = backend.auditHardwareOnHost_getObjects(
		lastseen="2000-01-01 01:01:01"
	)
	assert 1 == len(auditHardwareOnHosts)
	assert auditHardwareOnHost4update == auditHardwareOnHosts[0]

	auditHardwareOnHost4update.setState(0)
	backend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)
	historyRelevantActions += 1

	auditHardwareOnHosts = backend.auditHardwareOnHost_getObjects()
	assert len(auditHardwareOnHosts) == len(ahoh) + historyRelevantActions

	auditHardwareOnHost4update.setLastseen(None)
	backend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)
	historyRelevantActions += 1

	auditHardwareOnHosts = backend.auditHardwareOnHost_getObjects()
	assert len(auditHardwareOnHosts) == len(ahoh) + historyRelevantActions


def testInventoryObjectMethods(licenseManagentAndAuditBackend):
	backend = licenseManagentAndAuditBackend

	auditSoftwaresIn = getAuditSoftwares()
	backend.auditSoftware_createObjects(auditSoftwaresIn)

	licensePools, _ = createLicensePool(backend)

	auditSoftware1 = auditSoftwaresIn[0]
	auditSoftware2 = auditSoftwaresIn[1]
	licensePool1 = licensePools[0]
	licensePool2 = licensePools[1]

	auditSoftwareToLicensePool1 = AuditSoftwareToLicensePool(
		name=auditSoftware1.name,
		version=auditSoftware1.version,
		subVersion=auditSoftware1.subVersion,
		language=auditSoftware1.language,
		architecture=auditSoftware1.architecture,
		licensePoolId=licensePool1.id,
	)
	auditSoftwareToLicensePool2 = AuditSoftwareToLicensePool(
		name=auditSoftware2.name,
		version=auditSoftware2.version,
		subVersion=auditSoftware2.subVersion,
		language=auditSoftware2.language,
		architecture=auditSoftware2.architecture,
		licensePoolId=licensePool2.id,
	)

	auditSoftwareToLicensePoolsIn = [
		auditSoftwareToLicensePool1,
		auditSoftwareToLicensePool2,
	]
	backend.auditSoftwareToLicensePool_createObjects(auditSoftwareToLicensePoolsIn)

	auditSoftwareToLicensePools = backend.auditSoftwareToLicensePool_getObjects()
	assert len(auditSoftwareToLicensePools) == len(auditSoftwareToLicensePoolsIn)


def test_getAuditSoftwareFromBackend(auditDataBackend):
	auditSoftwaresIn = getAuditSoftwares()
	auditDataBackend.auditSoftware_createObjects(auditSoftwaresIn)

	auditSoftwaresOut = auditDataBackend.auditSoftware_getObjects()
	assert len(auditSoftwaresIn) == len(auditSoftwaresOut)
	# TODO: provide a check that no data was changed.


def test_updateAuditSoftware(auditDataBackend):
	auditSoftwaresIn = getAuditSoftwares()
	auditDataBackend.auditSoftware_createObjects(auditSoftwaresIn)

	auditSoftware3 = auditSoftwaresIn[2]
	auditSoftware3update = AuditSoftware(
		name=auditSoftware3.name,
		version=auditSoftware3.version,
		subVersion=auditSoftware3.subVersion,
		language=auditSoftware3.language,
		architecture=auditSoftware3.architecture,
		windowsSoftwareId=auditSoftware3.windowsSoftwareId,
		windowsDisplayName="updatedDN",
		windowsDisplayVersion=auditSoftware3.windowsDisplayVersion,
		installSize=auditSoftware3.installSize,
	)

	auditDataBackend.auditSoftware_updateObject(auditSoftware3update)
	auditSoftwares = auditDataBackend.auditSoftware_getObjects(
		windowsDisplayName="updatedDN"
	)
	assert 1 == len(auditSoftwares), (
		"Expected one audit software object, but found %s on backend."
		% len(auditSoftwares)
	)
	assert auditSoftware3update == auditSoftwares[0]


def test_deleteAuditSoftware(auditDataBackend):
	auditSoftwaresIn = getAuditSoftwares()
	auditDataBackend.auditSoftware_createObjects(auditSoftwaresIn)

	as3 = auditSoftwaresIn[2]
	auditDataBackend.auditSoftware_deleteObjects(as3)
	auditSoftwares = auditDataBackend.auditSoftware_getObjects()

	assert len(auditSoftwares) == len(auditSoftwaresIn) - 1
	assert as3.name not in [a.name for a in auditSoftwares]


def test_insertAuditSoftware(auditDataBackend):
	auditSoftwaresIn = getAuditSoftwares()
	auditDataBackend.auditSoftware_createObjects(auditSoftwaresIn)

	auditSoftware3 = auditSoftwaresIn[2]
	auditDataBackend.auditSoftware_deleteObjects(auditSoftware3)
	auditDataBackend.auditSoftware_insertObject(auditSoftware3)
	auditSoftwares = auditDataBackend.auditSoftware_getObjects()

	assert len(auditSoftwares) == len(auditSoftwaresIn)


def test_getAuditSoftwareOnClients(auditDataBackend):
	asoc, _, _ = fillBackendWithAuditSoftwareOnClient(auditDataBackend)
	auditDataBackend.auditSoftwareOnClient_createObjects(asoc)

	auditSoftwareOnClients = auditDataBackend.auditSoftwareOnClient_getObjects()
	assert len(asoc) == len(auditSoftwareOnClients)


def test_updateAuditSoftwareOnClient(auditDataBackend):
	asoc, auditSoftwaresIn, clients = fillBackendWithAuditSoftwareOnClient(
		auditDataBackend
	)

	client1 = clients[0]
	auditSoftware1 = auditSoftwaresIn[0]
	auditSoftwareOnClient1update = AuditSoftwareOnClient(
		name=auditSoftware1.getName(),
		version=auditSoftware1.getVersion(),
		subVersion=auditSoftware1.getSubVersion(),
		language=auditSoftware1.getLanguage(),
		architecture=auditSoftware1.getArchitecture(),
		clientId=client1.getId(),
		uninstallString=None,
		binaryName="updatedBN",
		firstseen=None,
		lastseen=None,
		state=None,
		usageFrequency=2,
		lastUsed="2009-02-12 09:48:22",
	)

	auditDataBackend.auditSoftwareOnClient_updateObject(auditSoftwareOnClient1update)
	auditSoftwareOnClients = auditDataBackend.auditSoftwareOnClient_getObjects(
		binaryName="updatedBN"
	)
	assert 1 == len(auditSoftwareOnClients)
	assert auditSoftwareOnClient1update == auditSoftwareOnClients[0]


def test_deleteAuditSoftwareOnClient(auditDataBackend):
	asoc, _, _ = fillBackendWithAuditSoftwareOnClient(auditDataBackend)
	auditDataBackend.auditSoftwareOnClient_createObjects(asoc)

	asoc1 = asoc[0]
	auditDataBackend.auditSoftwareOnClient_deleteObjects(asoc1)
	auditSoftwareOnClients = auditDataBackend.auditSoftwareOnClient_getObjects()
	assert len(asoc) - 1 == len(auditSoftwareOnClients)


def test_insertAuditSoftwareOnClient(auditDataBackend):
	asoc, _, _ = fillBackendWithAuditSoftwareOnClient(auditDataBackend)

	asoc1 = asoc[0]

	auditDataBackend.auditSoftwareOnClient_deleteObjects(asoc1)
	auditSoftwareOnClients = auditDataBackend.auditSoftwareOnClient_getObjects()
	assert len(auditSoftwareOnClients) == len(asoc) - 1

	auditDataBackend.auditSoftwareOnClient_insertObject(asoc1)
	auditSoftwareOnClients = auditDataBackend.auditSoftwareOnClient_getObjects()

	assert len(auditSoftwareOnClients) == len(asoc)


def fillBackendWithAuditSoftwareOnClient(backend):
	auditSoftwares = getAuditSoftwares()
	backend.auditSoftware_createObjects(auditSoftwares)

	clients = getClients()
	backend.host_createObjects(clients)

	asoc = getAuditSoftwareOnClient(auditSoftwares, clients)
	backend.auditSoftwareOnClient_createObjects(asoc)

	return asoc, auditSoftwares, clients


def testUpdatingAuditHardware(auditDataBackend):
	auditHardwaresIn = getAuditHardwares()
	auditDataBackend.auditHardware_createObjects(auditHardwaresIn)

	auditHardwares = auditDataBackend.auditHardware_getObjects()
	assert len(auditHardwares) == len(auditHardwaresIn)

	auditHardware1 = auditHardwaresIn[0]
	auditHardware2 = auditHardwaresIn[1]
	auditDataBackend.auditHardware_deleteObjects([auditHardware1, auditHardware2])
	auditHardwares = auditDataBackend.auditHardware_getObjects()
	assert len(auditHardwares) == len(auditHardwaresIn) - 2

	auditDataBackend.auditHardware_updateObjects([auditHardware1, auditHardware2])
	assert len(auditHardwares) == len(auditHardwaresIn) - 2


def testDeletingHostShouldDeleteHardwareAuditData(auditDataBackend):
	"""
	Deleting a host should delete it's audit data.
	"""
	clients = getClients()
	auditHardwares = getAuditHardwares()
	auditHardwareOnHosts = getAuditHardwareOnHost(auditHardwares, clients)

	client1 = clients[0]
	auditHardwareOnHost1 = auditHardwareOnHosts[0]

	auditDataBackend.host_createObjects(client1)
	auditDataBackend.auditHardwareOnHost_createObjects(auditHardwareOnHost1)

	assert 1 == len(
		auditDataBackend.host_getObjects()
	), "Self-test failed: Too much hosts."
	assert 1 == len(
		auditDataBackend.auditHardwareOnHost_getObjects()
	), "Self-test failed: Too much auditHardwareOnHosts."

	auditDataBackend.host_deleteObjects([client1])
	assert 0 == len(auditDataBackend.host_getObjects())
	assert 0 == len(auditDataBackend.auditHardwareOnHost_getObjects())

	auditDataBackend.host_createObjects(client1)
	assert 1 == len(auditDataBackend.host_getObjects())
	assert 0 == len(auditDataBackend.auditHardwareOnHost_getObjects())


def testSelecingAuditHardwareOnHostByLastseen(auditDataBackend):
	ahoh, _, _ = fillBackendWithAuditHardwareOnHosts(auditDataBackend)

	auditHardwareOnHost4update = ahoh[3].clone()
	auditHardwareOnHost4update.setLastseen("2000-01-01 01:01:01")
	auditDataBackend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)

	auditHardwareOnHosts = auditDataBackend.auditHardwareOnHost_getObjects(
		lastseen="2000-01-01 01:01:01"
	)
	assert len(auditHardwareOnHosts) == 1
	assert auditHardwareOnHost4update == auditHardwareOnHosts[0]


@pytest.mark.parametrize(
	"searchTerms", [["CHASSIS", "COMPUTER_SYSTEM"], ["CHA*IS", "*UTER_SYS*"]]
)
def test_selectAuditHardwareClasses(auditDataBackend, searchTerms):
	auditHardwaresIn = getAuditHardwares()
	auditDataBackend.auditHardware_createObjects(auditHardwaresIn)

	auditHardwareClasses = [
		x.getHardwareClass()
		for x in auditDataBackend.auditHardware_getObjects(hardwareClass=searchTerms)
	]
	assert auditHardwareClasses

	for auditHardwareClass in auditHardwareClasses:
		assert auditHardwareClass in ["CHASSIS", "COMPUTER_SYSTEM"]


def test_deleteAuditHardware(auditDataBackend):
	auditHardwaresIn = getAuditHardwares()
	auditDataBackend.auditHardware_createObjects(auditHardwaresIn)

	auditHardware1, auditHardware2 = auditHardwaresIn[:2]

	auditDataBackend.auditHardware_deleteObjects([auditHardware1, auditHardware2])
	auditHardwares = auditDataBackend.auditHardware_getObjects()
	assert len(auditHardwares) == len(auditHardwaresIn) - 2


def testDeletingAllAuditHardware(auditDataBackend):
	auditHardwares = getAuditHardwares()
	auditDataBackend.auditHardware_createObjects(auditHardwares)
	assert auditDataBackend.auditHardware_getObjects()

	auditDataBackend.auditHardware_deleteObjects(auditHardwares)
	auditHardwares = auditDataBackend.auditHardware_getObjects()
	assert 0 == len(auditHardwares), (
		"Expected 0 audit hardware objects, but found %s on backend."
		% len(auditHardwares)
	)


def testCreatingAndGetingAuditHardwareFromBackend(auditDataBackend):
	auditHardwaresIn = getAuditHardwares()
	auditDataBackend.auditHardware_createObjects(auditHardwaresIn)

	auditHardwares = auditDataBackend.auditHardware_getObjects()
	assert len(auditHardwares) == len(auditHardwaresIn)
	# TODO: check content


def testCreatingAuditHardwareAfterDeletion(auditDataBackend):
	auditHardwares = getAuditHardwares()

	auditDataBackend.auditHardware_createObjects(auditHardwares)
	auditDataBackend.auditHardware_deleteObjects(
		auditDataBackend.auditHardware_getObjects()
	)

	auditDataBackend.auditHardware_createObjects(auditHardwares)
	receivedAuditHardwares = auditDataBackend.auditHardware_getObjects()
	assert len(receivedAuditHardwares) == len(auditHardwares)


def testDeletingAllAuditHardwareOnHost(auditDataBackend):
	ahoh, _, _ = fillBackendWithAuditHardwareOnHosts(auditDataBackend)
	auditDataBackend.auditHardwareOnHost_createObjects(ahoh)

	assert auditDataBackend.auditHardwareOnHost_getObjects()

	auditDataBackend.auditHardwareOnHost_delete(
		hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[]
	)
	auditHardwareOnHosts = auditDataBackend.auditHardwareOnHost_getObjects()
	assert 0 == len(auditHardwareOnHosts), (
		"Expected no audit hardware objects on host, but found %s on backend."
		% len(auditHardwareOnHosts)
	)


def test_createAuditHardwareOnHost(auditDataBackend):
	ahoh, _, _ = fillBackendWithAuditHardwareOnHosts(auditDataBackend)

	auditDataBackend.auditHardwareOnHost_delete(
		hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[]
	)
	auditDataBackend.auditHardwareOnHost_createObjects(ahoh)
	auditHardwareOnHosts = auditDataBackend.auditHardwareOnHost_getObjects()
	assert len(auditHardwareOnHosts) == len(ahoh)
	# TODO: check the returned data


def test_updatingAuditHardwareOnHost(auditDataBackend):
	auditHardwareOnHosts, _, _ = fillBackendWithAuditHardwareOnHosts(auditDataBackend)

	numBefore = len(auditDataBackend.auditHardwareOnHost_getObjects())
	assert numBefore == len(auditHardwareOnHosts)

	auditHardwareOnHost4 = auditHardwareOnHosts[3]
	auditHardwareOnHost4update = auditHardwareOnHost4.clone()
	auditDataBackend.auditHardwareOnHost_updateObject(auditHardwareOnHost4update)
	auditHardwareOnHosts = auditDataBackend.auditHardwareOnHost_getObjects()
	numAfter = len(auditDataBackend.auditHardwareOnHost_getObjects())
	assert numBefore == numAfter


def test_deleteAuditHardwareOnHost(auditDataBackend):
	auditHardwareOnHostsIn, _, _ = fillBackendWithAuditHardwareOnHosts(auditDataBackend)

	ahoh3, ahoh4 = auditHardwareOnHostsIn[2:4]
	auditDataBackend.auditHardwareOnHost_deleteObjects([ahoh3, ahoh4])
	auditHardwareOnHostsOut = auditDataBackend.auditHardwareOnHost_getObjects()
	assert len(auditHardwareOnHostsIn) - 2 == len(auditHardwareOnHostsOut)

	# Making sure that the deleted IDs arent found anymore.
	assert ahoh3 not in auditHardwareOnHostsOut
	assert ahoh4 not in auditHardwareOnHostsOut


def testAuditHardwareOnHostSetObsolete(auditDataBackend):
	auditHardwareOnHostsIn, _, clients = fillBackendWithAuditHardwareOnHosts(
		auditDataBackend
	)

	client3 = clients[2]

	auditDataBackend.auditHardwareOnHost_setObsolete(client3.id)
	auditHardwareOnHosts = auditDataBackend.auditHardwareOnHost_getObjects(
		hostId=client3.id
	)
	for auditHardwareOnHost in auditHardwareOnHosts:
		assert auditHardwareOnHost.getState() == 0


def fillBackendWithAuditHardwareOnHosts(backend):
	clients = getClients()
	backend.host_createObjects(clients)

	auditHardwares = getAuditHardwares()
	backend.auditHardware_createObjects(auditHardwares)

	auditHardwareOnHosts = getAuditHardwareOnHost(auditHardwares, clients)
	backend.auditHardwareOnHost_createObjects(auditHardwareOnHosts)

	return auditHardwareOnHosts, auditHardwares, clients
