# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the Host Control backend.
"""

from ipaddress import IPv4Network, IPv4Address
import pytest

from opsicommon.objects import OpsiClient

from OPSI.Backend.HostControl import HostControlBackend
from OPSI.Exceptions import BackendMissingDataError

from .test_hosts import getClients


@pytest.fixture
def host_control_backend(extendedConfigDataBackend):
	yield HostControlBackend(extendedConfigDataBackend)


@pytest.mark.parametrize(
	"config, expected_result",
	(
		(
			["255.255.255.255", "192.168.10.255"],
			{
				IPv4Network("0.0.0.0/0"): {
					IPv4Address("255.255.255.255"): (7, 9, 12287),
					IPv4Address("192.168.10.255"): (7, 9, 12287),
				}
			},
		),
		(
			["255.255.255.255"],
			{IPv4Network("0.0.0.0/0"): {IPv4Address("255.255.255.255"): (7, 9, 12287)}},
		),
		(
			{"255.255.255.255": [9, 12287], "10.10.255.255": [12287]},
			{
				IPv4Network("0.0.0.0/0"): {
					IPv4Address("255.255.255.255"): (9, 12287),
					IPv4Address("10.10.255.255"): (12287,),
				}
			},
		),
		(
			{
				"0.0.0.0/0": {"255.255.255.255": [9, 12287]},
				"10.10.0.0/16": {"10.10.1.255": [9, 12287], "10.10.2.255": [12287]},
			},
			{
				IPv4Network("0.0.0.0/0"): {
					IPv4Address("255.255.255.255"): (9, 12287),
				},
				IPv4Network("10.10.0.0/16"): {
					IPv4Address("10.10.1.255"): (9, 12287),
					IPv4Address("10.10.2.255"): (12287,),
				},
			},
		),
	),
)
def test_set_broadcast_addresses(host_control_backend, config, expected_result):  # pylint: disable=redefined-outer-name
	host_control_backend._set_broadcast_addresses(config)  # pylint: disable=protected-access
	assert host_control_backend._broadcastAddresses == expected_result  # pylint: disable=protected-access


@pytest.mark.parametrize(
	"config, ip_address, expected_result",
	(
		(
			["255.255.255.255", "192.168.10.255"],
			None,
			[("255.255.255.255", (7, 9, 12287)), ("192.168.10.255", (7, 9, 12287))],
		),
		(
			{
				"0.0.0.0/0": {"255.255.255.255": [9, 12287]},
				"10.10.0.0/16": {"10.10.1.255": [9, 12287], "10.10.2.255": [12287]},
			},
			None,
			[
				("255.255.255.255", (9, 12287)),
				("10.10.1.255", (9, 12287)),
				("10.10.2.255", (12287,)),
			],
		),
		(
			{
				"192.0.0.0/8": {"255.255.255.255": [9, 12287]},
				"10.10.0.0/16": {"10.10.1.255": [9, 12287], "10.10.2.255": [12287]},
			},
			"10.1.1.1",
			[
				("255.255.255.255", (9, 12287)),
				("10.10.1.255", (9, 12287)),
				("10.10.2.255", (12287,)),
			],
		),
		(
			{
				"0.0.0.0/0": {"255.255.255.255": [9, 12287]},
				"10.10.0.0/16": {"10.10.1.255": [9, 12287], "10.10.2.255": [12287]},
			},
			"10.10.1.1",
			[("10.10.1.255", (9, 12287)), ("10.10.2.255", (12287,))],
		),
		(
			{
				"192.168.0.0/16": {"255.255.255.255": [9, 12287]},
				"10.10.1.0/24": {"10.10.1.255": [9, 12287]},
				"10.10.2.0/24": {"10.10.2.255": [12287]},
			},
			"10.10.2.1",
			[("10.10.2.255", (12287,))],
		),
	),
)
def test_get_broadcast_addresses_for_host(
	host_control_backend, config, ip_address, expected_result
):  # pylint: disable=redefined-outer-name
	host_control_backend._set_broadcast_addresses(config)  # pylint: disable=protected-access
	host = OpsiClient(id="test.opsi.org", ipAddress=ip_address)
	assert (
		list(host_control_backend._get_broadcast_addresses_for_host(host))
		== expected_result
	)  # pylint: disable=protected-access


def test_calling_start_and_stop_method(host_control_backend):  # pylint: disable=redefined-outer-name
	"""
	Test if calling the methods works.

	This test does not check if WOL on these clients work nor that
	they do exist.
	"""
	clients = getClients()
	host_control_backend.host_createObjects(clients)
	host_control_backend._hostRpcTimeout = (
		1  # for faster finishing of the test # pylint: disable=protected-access
	)
	host_control_backend.hostControl_start(["client1.test.invalid"])
	host_control_backend.hostControl_shutdown(["client1.test.invalid"])


def test_host_control_reachable_without_hosts(host_control_backend):  # pylint: disable=redefined-outer-name
	with pytest.raises(BackendMissingDataError):
		host_control_backend.hostControl_reachable()
