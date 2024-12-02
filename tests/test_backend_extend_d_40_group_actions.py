# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for the dynamically loaded group actions extensions.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/40_groupActions.conf``.

.. versionadded:: 4.0.5.4
"""

import pytest

from OPSI.Exceptions import BackendMissingDataError
from OPSI.Object import (
	HostGroup,
	LocalbootProduct,
	ProductOnDepot,
	ObjectToGroup,
	OpsiClient,
	OpsiDepotserver,
)


def testSetProductActionRequestForHostGroup(backendManager):
	testGroup = HostGroup(id="host_group_1")

	client1 = OpsiClient(id="client1.test.invalid")
	client2 = OpsiClient(id="client2.test.invalid")

	client1ToGroup = ObjectToGroup(testGroup.getType(), testGroup.id, client1.id)
	client2ToGroup = ObjectToGroup(testGroup.getType(), testGroup.id, client2.id)

	depot = OpsiDepotserver(id="depotserver1.test.invalid")

	product2 = LocalbootProduct(
		id="product2",
		name="Product 2",
		productVersion="2.0",
		packageVersion="test",
		setupScript="setup.ins",
	)

	prodOnDepot = ProductOnDepot(
		productId=product2.getId(),
		productType=product2.getType(),
		productVersion=product2.getProductVersion(),
		packageVersion=product2.getPackageVersion(),
		depotId=depot.getId(),
	)

	backendManager.host_insertObject(client1)
	backendManager.host_insertObject(client2)
	backendManager.host_insertObject(depot)
	backendManager.group_insertObject(testGroup)
	backendManager.objectToGroup_createObjects([client1ToGroup, client2ToGroup])
	backendManager.config_create("clientconfig.depot.id")
	backendManager.configState_create(
		"clientconfig.depot.id", client1.getId(), values=[depot.getId()]
	)
	backendManager.configState_create(
		"clientconfig.depot.id", client2.getId(), values=[depot.getId()]
	)
	backendManager.product_insertObject(product2)
	backendManager.productOnDepot_insertObject(prodOnDepot)

	backendManager.setProductActionRequestForHostGroup(
		"host_group_1", "product2", "setup"
	)

	pocs = backendManager.productOnClient_getObjects()
	assert pocs
	assert len(pocs) == 2

	for poc in backendManager.productOnClient_getObjects():
		assert poc.productId == product2.getId()
		assert poc.clientId in (client1.id, client2.id)


def testGroupnameExists(backendManager):
	testGroup, _ = fillBackendForRenaming(backendManager)

	assert backendManager.groupname_exists(testGroup.id)
	assert not backendManager.groupname_exists("testgruppe")


def testRenamingGroupToAlreadyExistingGroupFails(backendManager):
	testGroup, _ = fillBackendForRenaming(backendManager)

	newGroup = HostGroup(id="new_group_1")
	backendManager.group_insertObject(newGroup)

	with pytest.raises(Exception):
		backendManager.group_rename(testGroup.id, newGroup.id)


def testRenamingNonexistingGroupFails(backendManager):
	with pytest.raises(BackendMissingDataError):
		backendManager.group_rename("notExisting", "newGroupId")


def testRenamingKeepsSettingsOfOldGroup(backendManager):
	"""
	After a rename non-key attributes of the new object must be the same.
	"""
	testGroup, _ = fillBackendForRenaming(backendManager)
	newGroupId = "new_group_1"

	backendManager.group_rename(testGroup.id, newGroupId)

	group = backendManager.group_getObjects(id=newGroupId)[0]
	assert group.id == "new_group_1"
	assert group.description == testGroup.description
	assert group.notes == testGroup.notes
	assert group.parentGroupId == testGroup.parentGroupId

	assert not backendManager.groupname_exists(testGroup.id)


def testGroupRenameUpdatesObjectToGroups(backendManager):
	testGroup, clients = fillBackendForRenaming(backendManager)
	client1, client2 = clients[:2]
	newGroupId = "new_group_1"

	backendManager.group_rename(testGroup.id, newGroupId)

	objTpGrp_client1 = backendManager.objectToGroup_getObjects(objectId=client1.id)[0]
	assert objTpGrp_client1.groupId == newGroupId

	objTpGrp_client2 = backendManager.objectToGroup_getObjects(objectId=client2.id)[0]
	assert objTpGrp_client2.groupId == newGroupId

	objsToGrp = backendManager.objectToGroup_getObjects()
	# Removal of old group ID
	assert not any(obj.groupId == testGroup.id for obj in objsToGrp)
	# Existance of new group ID
	assert any(obj.groupId == newGroupId for obj in objsToGrp)


def fillBackendForRenaming(backend):
	group = HostGroup(id="host_group_1")

	client1 = OpsiClient(id="client1.test.invalid")
	client2 = OpsiClient(id="client2.test.invalid")

	client1ToGroup = ObjectToGroup(group.getType(), group.id, client1.id)
	client2ToGroup = ObjectToGroup(group.getType(), group.id, client2.id)

	backend.host_insertObject(client1)
	backend.host_insertObject(client2)
	backend.group_insertObject(group)
	backend.objectToGroup_createObjects([client1ToGroup, client2ToGroup])

	return (group, (client1, client2))
