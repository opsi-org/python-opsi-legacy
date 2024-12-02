# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing ACL on the backend.
"""

import os

import pytest

import OPSI.Object
from OPSI.Exceptions import BackendPermissionDeniedError
from OPSI.Types import forceHostId
from OPSI.Util import getfqdn
from OPSI.Util.File.Opsi import BackendACLFile
from OPSI.Backend.BackendManager import BackendAccessControl

from .test_backend_replicator import (
	fillBackendWithHosts,
	fillBackendWithProducts,
	fillBackendWithProductOnClients,
)
from .test_hosts import getClients
from .test_products import getProducts


def testParsingBackendACLFile(tempDir):
	expectedACL = [
		[
			"host_.*",
			[
				{
					"denyAttributes": [],
					"type": "opsi_depotserver",
					"ids": ["depot1.test.invalid", "depot2.test.invalid"],
					"allowAttributes": [],
				},
				{
					"denyAttributes": [],
					"type": "opsi_client",
					"ids": ["self"],
					"allowAttributes": ["attr1", "attr2"],
				},
				{
					"denyAttributes": [],
					"type": "sys_user",
					"ids": ["some user", "some other user"],
					"allowAttributes": [],
				},
				{
					"denyAttributes": [],
					"type": "sys_group",
					"ids": ["a_group", "group2"],
					"allowAttributes": [],
				},
			],
		]
	]

	aclFile = os.path.join(tempDir, "acl.conf")
	with open(aclFile, "w") as exampleConfig:
		exampleConfig.write("""
host_.*: opsi_depotserver(depot1.test.invalid, depot2.test.invalid); opsi_client(self,  attributes (attr1, attr2)); sys_user(some user, some other user); sys_group(a_group, group2)
""")

	assert expectedACL == BackendACLFile(aclFile).parse()


def testAllowingMethodsForSpecificClient(extendedConfigDataBackend):
	"""
	Access to methods can be limited to specific clients.

	In this example client1 can access host_getObjects but not
	config_getObjects.
	"""
	backend = extendedConfigDataBackend
	_, _, clients = fillBackendWithHosts(backend)

	client1, client2 = clients[:2]

	backendAccessControl = BackendAccessControl(
		username=client1.id,
		password=client1.opsiHostKey,
		backend=backend,
		acl=[
			[
				"host_getObjects",
				[
					{
						"type": "opsi_client",
						"ids": [client1.id],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			],
			[
				"config_getObjects",
				[
					{
						"type": "opsi_client",
						"ids": [client2.id],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			],
		],
	)

	backendAccessControl.host_getObjects()

	with pytest.raises(BackendPermissionDeniedError):
		backendAccessControl.config_getObjects()


def testDenyingAttributes(extendedConfigDataBackend):
	"""
	Access to attributes can be denied.

	In this case the backend can only access its own opsiHostKey and
	for other clients no value is given.
	"""
	backend = extendedConfigDataBackend
	_, _, clients = fillBackendWithHosts(backend)

	client1 = clients[0]

	backendAccessControl = BackendAccessControl(
		username=client1.id,
		password=client1.opsiHostKey,
		backend=backend,
		acl=[
			[
				"host_getObjects",
				[
					{
						"type": "self",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			],
			[
				"host_getObjects",
				[
					{
						"type": "opsi_client",
						"ids": [],
						"denyAttributes": ["opsiHostKey"],
						"allowAttributes": [],
					}
				],
			],
		],
	)

	for host in backendAccessControl.host_getObjects():
		if host.id == client1.id:
			assert host.opsiHostKey == client1.opsiHostKey
		else:
			assert host.opsiHostKey is None


# def testAllowingOnlyUpdatesOfSpecificAttributes(extendedConfigDataBackend):
# # TODO: this test has been disabled for quite a while.
# # Check why this is the cause and maybe fix. If unfixable: delete.
# backend = extendedConfigDataBackend

# clients = getClients()
# backend.host_createObjects(clients)
# client1 = clients[0]
# client2 = clients[1]
# client3 = clients[2]

# backendAccessControl = BackendAccessControl(
# username=client1.id,
# password=client1.opsiHostKey,
# backend=backend,
# acl=[
# ['host_.*',	   [{'type': 'self',		'ids': [], 'denyAttributes': [],			  'allowAttributes': []}]],
# ['host_get.*',	[{'type': 'opsi_client', 'ids': [], 'denyAttributes': ['opsiHostKey'], 'allowAttributes': []}]],
# ['host_update.*', [{'type': 'opsi_client', 'ids': [], 'denyAttributes': [],			  'allowAttributes': ['notes']}]]
# ]
# )

# assert len(backendAccessControl.host_getObjects()) > 1, "Backend must be able to access all objects not only itself!"

# client1.setDescription("Access to self is allowed.")
# client1.setNotes("Access to self is allowed.")
# backendAccessControl.host_updateObject(client1)

# client2.setDescription("Only updating notes is allowed.")
# with pytest.raises(OPSI.Types.BackendPermissionDeniedError):
# backendAccessControl.host_updateObject(client2)

# assert not backendAccessControl.host_getObjects()
# newClient3 = OPSI.Object.OpsiClient(
# id=client3.id,
# notes="New notes are okay"
# )
# # backendAccessControl.host_updateObject(newClient3)
# assert not backendAccessControl.host_getObjects(id=client3.id)
# client3FromBackend = backendAccessControl.host_getObjects(id=client3.id)[0]
# assert client3FromBackend.notes == newClient3.notes


def testDenyingAccessToOtherObjects(extendedConfigDataBackend):
	"""
	It must be possible to deny access to foreign objects.

	In this test we first make sure that the access to productOnClient_create
	is possible for the object accessing the backend.
	After that we test the same referencing another object which we
	want to fail.
	"""
	backend = extendedConfigDataBackend

	serverFqdn = forceHostId(getfqdn())  # using local FQDN
	depotserver1 = {
		"isMasterDepot": True,
		"type": "OpsiConfigserver",
		"id": serverFqdn,
	}

	backend.host_createObjects(depotserver1)

	clients = getClients()
	backend.host_createObjects(clients)
	client1 = clients[0]
	client2 = clients[1]

	products = getProducts()
	backend.product_createObjects(products)

	product1 = products[0]

	backend.config_createObjects(
		[
			{
				"id": "clientconfig.depot.id",
				"type": "UnicodeConfig",
			}
		]
	)
	backend.configState_create(
		"clientconfig.depot.id", client1.getId(), values=[depotserver1["id"]]
	)

	productOnDepot1 = OPSI.Object.ProductOnDepot(
		productId=product1.getId(),
		productType=product1.getType(),
		productVersion=product1.getProductVersion(),
		packageVersion=product1.getPackageVersion(),
		depotId=depotserver1["id"],
		locked=False,
	)

	backend.productOnDepot_createObjects([productOnDepot1])

	backendAccessControl = BackendAccessControl(
		username=client1.id,
		password=client1.opsiHostKey,
		backend=backend,
		acl=[
			[
				"productOnClient_create",
				[
					{
						"type": "self",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			],
		],
	)

	backendAccessControl.productOnClient_create(
		productId=product1.id,
		productType=product1.getType(),
		clientId=client1.id,
		installationStatus="installed",
	)

	with pytest.raises(Exception):
		backendAccessControl.productOnClient_create(
			productId=product1.id,
			productType=product1.getType(),
			clientId=client2.id,  # here is the difference
			installationStatus="installed",
		)


def testGettingFullAccess(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	configServer, depotServer, clients = fillBackendWithHosts(backend)
	createdHosts = list(depotServer) + list(clients) + [configServer]

	backend = BackendAccessControl(
		backend=backend,
		username=configServer.id,
		password=configServer.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "opsi_depotserver",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			]
		],
	)

	hosts = backend.host_getObjects()
	assert len(createdHosts) == len(hosts)

	for host in hosts:
		for h in createdHosts:
			if h.id != host.id:
				continue

			assert h.opsiHostKey == host.opsiHostKey


def testOnlyAccessingSelfIsPossible(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	configServer, _, _ = fillBackendWithHosts(backend)

	backend = BackendAccessControl(
		backend=backend,
		username=configServer.id,
		password=configServer.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "self",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			]
		],
	)

	hosts = backend.host_getObjects()
	assert 1 == len(hosts)


def testDenyingAccessToSpecifiedAttributes(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	configServer, depotServer, clients = fillBackendWithHosts(backend)
	createdHosts = list(depotServer) + list(clients) + [configServer]

	denyAttributes = set(["opsiHostKey", "description"])
	backend = BackendAccessControl(
		backend=backend,
		username=configServer.id,
		password=configServer.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "opsi_depotserver",
						"ids": [],
						"denyAttributes": denyAttributes,
						"allowAttributes": [],
					}
				],
			]
		],
	)

	hosts = backend.host_getObjects()
	assert len(createdHosts) == len(hosts)

	for host in hosts:
		for attribute, value in host.toHash().items():
			if attribute in denyAttributes:
				assert value is None


def testGettingAccessAndOnlyAllowingSomeAttributes(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	configServer, depotServer, clients = fillBackendWithHosts(backend)
	createdHosts = list(depotServer) + list(clients) + [configServer]

	allowAttributes = set(["type", "id", "description", "notes"])
	backend = BackendAccessControl(
		backend=backend,
		username=configServer.id,
		password=configServer.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "opsi_depotserver",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": allowAttributes,
					}
				],
			]
		],
	)

	hosts = backend.host_getObjects()
	assert len(createdHosts) == len(hosts)

	for host in hosts:
		for attribute, value in host.toHash().items():
			if attribute not in allowAttributes:
				assert value is None


def testGettingAccessButDenyingAttributesOnSelf(extendedConfigDataBackend):
	backend = extendedConfigDataBackend

	configServer, depotServer, clients = fillBackendWithHosts(backend)
	createdHosts = list(depotServer) + list(clients) + [configServer]

	denyAttributes = set(["opsiHostKey", "description"])
	backend = BackendAccessControl(
		backend=backend,
		username=configServer.id,
		password=configServer.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "opsi_depotserver",
						"ids": [],
						"denyAttributes": denyAttributes,
						"allowAttributes": [],
					},
					{
						"type": "self",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					},
				],
			]
		],
	)

	hosts = backend.host_getObjects()
	assert len(createdHosts) == len(hosts)

	for host in hosts:
		if host.id == configServer.id:
			assert configServer.opsiHostKey == host.opsiHostKey
		else:
			for attribute, value in host.toHash().items():
				if attribute in denyAttributes:
					assert value is None


def testAccessingSelfProductOnClients(extendedConfigDataBackend):
	dataBackend = extendedConfigDataBackend

	configServer, depotServer, clients = fillBackendWithHosts(dataBackend)
	products = fillBackendWithProducts(dataBackend)
	productOnClients = fillBackendWithProductOnClients(dataBackend, products, clients)

	for client in clients:
		if client.id == productOnClients[0].clientId:
			break
	else:
		raise RuntimeError("Missing client!")

	backend = BackendAccessControl(
		backend=dataBackend,
		username=client.id,
		password=client.opsiHostKey,
		acl=[
			[
				".*",
				[
					{
						"type": "self",
						"ids": [],
						"denyAttributes": [],
						"allowAttributes": [],
					}
				],
			]
		],
	)

	productOnClients = backend.productOnClient_getObjects()
	for productOnClient in productOnClients:
		assert client.id == productOnClient.clientId, (
			"Expected client id %s in productOnClient, but got client id '%s'"
			% (client.id, productOnClient.clientId)
		)

	for c in clients:
		if client.id != c.id:
			otherClientId = c.id
			break
	else:
		raise RuntimeError("Failed to get different clientID.")

	productOnClient = productOnClients[0].clone()
	productOnClient.clientId = otherClientId

	with pytest.raises(Exception):
		backend.productOnClient_updateObjects(productOnClient)
