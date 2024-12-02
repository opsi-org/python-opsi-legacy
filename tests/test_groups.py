# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing group functionality.
"""

from OPSI.Object import HostGroup, ProductGroup, ObjectToGroup

from .test_hosts import getClients


def getGroups():
	return list(getHostGroups()) + [getProductGroup()]


def getHostGroups():
	group1 = HostGroup(
		id="host_group_1",
		description="Group 1",
		notes="First group",
		parentGroupId=None,
	)

	group2 = HostGroup(
		id="host group 2",
		description="Group 2",
		notes="Test\nTest\nTest",
		parentGroupId=group1.id,
	)

	group3 = HostGroup(
		id="host group 3", description="Group 3", notes="", parentGroupId=None
	)

	return group1, group2, group3


def getProductGroup():
	return ProductGroup(
		id="products group 4", description="Group 4", notes="", parentGroupId=None
	)


def getObjectToGroups(groups, clients):
	group1, group2 = groups[:2]
	client1, client2 = clients[:2]

	objectToGroup1 = ObjectToGroup(
		groupType=group1.getType(), groupId=group1.getId(), objectId=client1.getId()
	)

	objectToGroup2 = ObjectToGroup(
		groupType=group1.getType(), groupId=group1.getId(), objectId=client2.getId()
	)

	objectToGroup3 = ObjectToGroup(
		groupType=group2.getType(), groupId=group2.getId(), objectId=client2.getId()
	)

	return objectToGroup1, objectToGroup2, objectToGroup3


def fillBackendWithGroups(backend):
	groups = getGroups()
	backend.group_createObjects(groups)

	return groups


def fillBackendWithObjectToGroups(backend):
	clients = getClients()
	backend.host_createObjects(clients)

	groups = fillBackendWithGroups(backend)

	o2g = getObjectToGroups(groups, clients)
	backend.objectToGroup_createObjects(o2g)

	return o2g, groups, clients


def testSelectingGroupByDescrition(extendedConfigDataBackend):
	groupsIn = fillBackendWithGroups(extendedConfigDataBackend)

	group1 = groupsIn[0]

	groups = extendedConfigDataBackend.group_getObjects(description=group1.description)
	assert 1 == len(groups)
	assert groups[0].getId() == group1.id


def testUpdatingGroup(extendedConfigDataBackend):
	groupsIn = fillBackendWithGroups(extendedConfigDataBackend)

	group1 = groupsIn[0]
	group1.setDescription("new description")
	extendedConfigDataBackend.group_updateObject(group1)

	groups = extendedConfigDataBackend.group_getObjects(description=group1.description)
	assert 1 == len(groups)
	assert groups[0].getDescription() == "new description"


def testDeletingGroup(extendedConfigDataBackend):
	groupsIn = fillBackendWithGroups(extendedConfigDataBackend)

	group1 = groupsIn[0]
	extendedConfigDataBackend.group_deleteObjects(group1)
	groups = extendedConfigDataBackend.group_getObjects()
	assert len(groups) == len(groupsIn) - 1

	extendedConfigDataBackend.group_createObjects(group1)
	groups = extendedConfigDataBackend.group_getObjects()
	assert len(groups) == len(groupsIn)


def testCreatingGroup(extendedConfigDataBackend):
	groupsIn = fillBackendWithGroups(extendedConfigDataBackend)

	groupsOut = extendedConfigDataBackend.group_getObjects()
	assert len(groupsOut) == len(groupsIn)

	for group in groupsOut:
		assert group in groupsIn


def testNotCreatingDuplicateGroup(extendedConfigDataBackend):
	groups = fillBackendWithGroups(extendedConfigDataBackend)

	group1 = groups[0]
	extendedConfigDataBackend.group_createObjects(group1)
	groupsFromBackend = extendedConfigDataBackend.group_getObjects()
	assert len(groupsFromBackend) == len(groups)


def testUpdatingObjectToGroupDoesNotOverwriteExisting(extendedConfigDataBackend):
	o2g, _, _ = fillBackendWithObjectToGroups(extendedConfigDataBackend)

	objToUpdate = ObjectToGroup.fromHash(o2g[2].toHash())
	extendedConfigDataBackend.objectToGroup_updateObject(objToUpdate)

	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects()
	assert len(o2g) == len(objectToGroups)


def testGettingObjectToGroupFromBackend(extendedConfigDataBackend):
	o2g, _, _ = fillBackendWithObjectToGroups(extendedConfigDataBackend)

	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects()
	assert len(objectToGroups) == len(o2g)

	for objToGroup in objectToGroups:
		assert objToGroup in o2g


def testSelectingObjectToGroupByObjectId(extendedConfigDataBackend):
	o2g, _, clients = fillBackendWithObjectToGroups(extendedConfigDataBackend)

	client1 = clients[0]
	client2 = clients[1]

	client1ObjectToGroups = [
		objectToGroup for objectToGroup in o2g if objectToGroup.objectId == client1.id
	]
	client2ObjectToGroups = [
		objectToGroup for objectToGroup in o2g if objectToGroup.objectId == client2.id
	]

	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects(
		objectId=client1.getId()
	)
	assert len(objectToGroups) == len(client1ObjectToGroups)

	for objectToGroup in objectToGroups:
		assert objectToGroup.objectId == client1.id

	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects(
		objectId=client2.getId()
	)
	assert len(objectToGroups) == len(client2ObjectToGroups)

	for objectToGroup in objectToGroups:
		assert objectToGroup.objectId == client2.id


def testDeletingObjectToGroupObject(extendedConfigDataBackend):
	o2g, _, _ = fillBackendWithObjectToGroups(extendedConfigDataBackend)

	objectToGroup3 = o2g[2]
	extendedConfigDataBackend.objectToGroup_deleteObjects(objectToGroup3)
	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects()
	assert len(objectToGroups) == len(o2g) - 1

	# And a re-insert...
	extendedConfigDataBackend.objectToGroup_createObjects(objectToGroup3)
	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects()
	assert len(objectToGroups) == len(o2g)


def testCreatingDuplicateObjectToGroupDoesNotWork(extendedConfigDataBackend):
	o2g, _, _ = fillBackendWithObjectToGroups(extendedConfigDataBackend)

	objectToGroup3 = o2g[2]
	extendedConfigDataBackend.objectToGroup_createObjects(objectToGroup3)
	objectToGroups = extendedConfigDataBackend.objectToGroup_getObjects()
	assert len(objectToGroups) == len(o2g)
