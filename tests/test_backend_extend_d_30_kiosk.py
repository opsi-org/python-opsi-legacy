# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2017 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Tests for the kiosk client method.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

import pytest

from OPSI.Object import (
    LocalbootProduct, ObjectToGroup, OpsiClient,
    OpsiDepotserver, ProductGroup, ProductOnDepot, UnicodeConfig)
from OPSI.Types import BackendMissingDataError


def testGettingInfoForNonExistingClient(backendManager):
    with pytest.raises(BackendMissingDataError):
        backendManager.getKioskProductInfosForClient('foo.bar.baz')


# TODO: set custom configState for the client with different products in group.
# TODO: check that everything works if the client is assigned to different depots.
# TODO: check what happens if client is on different depot.
def testGettingEmptyInfo(backendManager, client, depot):
    backendManager.host_createObjects([client, depot])

    basicConfigs = [
        UnicodeConfig(
            id=u'software-on-demand.product-group-ids',
            defaultValues=["software-on-demand"],
            multiValue=True,
        ),
        UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        ),
    ]
    backendManager.config_createObjects(basicConfigs)

    assert [] == backendManager.getKioskProductInfosForClient(client.id)


@pytest.fixture()
def client():
    return OpsiClient(id='foo.test.invalid')


@pytest.fixture()
def depot():
    return OpsiDepotserver(id='depotserver1.test.invalid')


@pytest.fixture()
def anotherDepot():
    return OpsiDepotserver(id='depotserver2.some.test')


def createProducts(amount=2):
    for number in range(amount):
        yield LocalbootProduct(
            id='product{0}'.format(number),
            name=u'Product {0}'.format(number),
            productVersion='{0}'.format(number + 1),
            packageVersion='1',
            setupScript="setup.opsiscript",
            uninstallScript=u"uninstall.opsiscript",
            updateScript="update.opsiscript",
            description="This is product {0}".format(number),
            advice="Advice for product {0}".format(number),
        )


def testDoNotDuplicateProducts(backendManager, client, depot):
    backendManager.host_createObjects([client, depot])

    products = list(createProducts(10))
    backendManager.product_createObjects(products)

    for product in products:
        pod = ProductOnDepot(
            productId=product.id,
            productType=product.getType(),
            productVersion=product.getProductVersion(),
            packageVersion=product.getPackageVersion(),
            depotId=depot.id,
        )
        backendManager.productOnDepot_createObjects([pod])

    productGroupIds = set()
    for step in range(1, 4):
        productGroup = ProductGroup(id=u'group {0}'.format(step))
        backendManager.group_createObjects([productGroup])
        productGroupIds.add(productGroup.id)

        for product in products[::step]:
            groupAssignment = ObjectToGroup(
                groupType=productGroup.getType(),
                groupId=productGroup.id,
                objectId=product.id
            )
            backendManager.objectToGroup_createObjects([groupAssignment])

    basicConfigs = [
        UnicodeConfig(
            id=u'software-on-demand.product-group-ids',
            defaultValues=list(productGroupIds),
            multiValue=True,
        ),
        UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        ),
    ]
    backendManager.config_createObjects(basicConfigs)

    result = backendManager.getKioskProductInfosForClient(client.id)
    assert len(result) == len(products)


def testGettingKioskInfoFromDifferentDepot(backendManager, client, depot, anotherDepot):
    backendManager.host_createObjects([client, depot, anotherDepot])

    products = list(createProducts(10))
    backendManager.product_createObjects(products)

    expectedProducts = set()
    for index, product in enumerate(products):
        pod = ProductOnDepot(
            productId=product.id,
            productType=product.getType(),
            productVersion=product.getProductVersion(),
            packageVersion=product.getPackageVersion(),
            depotId=depot.id,
        )
        backendManager.productOnDepot_createObjects([pod])

        if index % 2 == 0:
            # Assign every second product to the second depot
            pod.depotId = anotherDepot.id
            backendManager.productOnDepot_createObjects([pod])
            expectedProducts.add(product.id)

    productGroup = ProductGroup(id=u'my product group')
    backendManager.group_createObjects([productGroup])

    for product in products:
        groupAssignment = ObjectToGroup(
            groupType=productGroup.getType(),
            groupId=productGroup.id,
            objectId=product.id
        )
        backendManager.objectToGroup_createObjects([groupAssignment])

    basicConfigs = [
        UnicodeConfig(
            id=u'software-on-demand.product-group-ids',
            defaultValues=[productGroup.id],
            multiValue=True,
        ),
        UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        ),
    ]
    backendManager.config_createObjects(basicConfigs)

    # Assign client to second depot
    backendManager.configState_create(u'clientconfig.depot.id', client.id, values=[anotherDepot.id])
    assert backendManager.getDepotId(client.id) == anotherDepot.id

    results = backendManager.getKioskProductInfosForClient(client.id)

    for result in results:
        assert result['productId'] in expectedProducts

    # assert len(results) == 5
