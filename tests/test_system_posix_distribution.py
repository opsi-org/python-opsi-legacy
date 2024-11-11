# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing Distribution functionality from OPSI.System.Posix
"""

from OPSI.System.Posix import Distribution

import pytest


# The first tuple is retrieved by running platform.linux_distribution()
# or distro.linux_distribution() on the corresponding version.
DISTRI_INFOS = [
	(("debian", "8.11", ""), (8, 11)),
	(("debian", "10.0", ""), (10, 0)),
	# TODO: add CentOS 7
	(("Red Hat Enterprise Linux Server", "7.0", "Maipo"), (7, 0)),
	(("Ubuntu", "16.04", "xenial"), (16, 4)),
	(("Ubuntu", "19.04", "disco"), (19, 4)),
	(("Univention", '"4.4-0 errata175"', "Blumenthal"), (4, 4)),
	# TODO: add SLES12
	(("openSUSE project", "42.3", "n/a"), (42, 3)),
	(("openSUSE", "15.0", "n/a"), (15, 0)),
]


@pytest.mark.parametrize("dist_info, expected_version", DISTRI_INFOS)
def testDistributionHasVersionSet(dist_info, expected_version):
	dist = Distribution(distribution_information=dist_info)

	assert dist.version
	assert expected_version == dist.version
	assert isinstance(dist.version, tuple)


@pytest.mark.parametrize("dist_info, expected_version", DISTRI_INFOS)
def testDistributionReprContainsAllValues(dist_info, expected_version):
	dist = Distribution(distribution_information=dist_info)

	for part in dist_info:
		assert part.strip() in repr(dist)


@pytest.mark.parametrize("dist_info, expected_version", DISTRI_INFOS)
def testDistributionNameGetsWhitespaceStripped(dist_info, expected_version):
	dist = Distribution(distribution_information=dist_info)

	assert dist.distribution == dist_info[0].strip()


@pytest.mark.parametrize("dist_info, expected_version", DISTRI_INFOS)
def testDistributionHasDistributorSet(dist_info, expected_version):
	dist = Distribution(distribution_information=dist_info)

	assert dist.distributor
