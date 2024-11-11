# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0

import pytest

from OPSI.Service.JsonRpc import JsonRpc


@pytest.mark.parametrize(
	"invalidRpcInfo",
	[
		None,
		{},
		{"id": 0},
		{"tid": 0},
		{"id": 1},
		{"id": 1, "method": ""},
		{"id": 1, "method": None},
		{"id": 1, "method": 0},
		{"id": 1, "method": False},
	],
)
def testJsonRpcRequiresTransactionId(invalidRpcInfo):
	with pytest.raises(Exception):  # TODO: better Exception class
		JsonRpc(None, None, invalidRpcInfo)


def testLoggingTraceback():
	j = JsonRpc(None, interface=[], rpc={"id": 1, "method": "foo"})
	j.execute()

	assert j.ended
	assert j.exception
	assert j.traceback

	print(
		"Old traceback was something like this: {0!r}".format(
			[
				"	 line 105 in 'execute' in file '/root/python-opsi/OPSI/Service/JsonRpc.py'"
			]
		)
	)
	print("Collected traceback: {0!r}".format(j.traceback))
	print("Collected Exception: {0!r}".format(j.exception))

	assert "line" in "".join(j.traceback).lower()
	assert "file" in "".join(j.traceback).lower()
	assert "jsonrpc" in "".join(j.traceback).lower()  # Module name
	assert "execute" in "".join(j.traceback).lower()  # Function name


def testExecutingMethodOnInstance():
	class TestInstance:
		def testMethod(self):
			return ["yeah it works!"]

	j = JsonRpc(
		instance=TestInstance(),
		interface=[{"name": "testMethod", "keywords": []}],
		rpc={"id": 42, "method": "testMethod"},
	)
	j.execute()

	assert j.ended
	assert not j.traceback
	assert not j.exception

	response = j.getResponse()
	assert response

	assert response["id"] == 42
	assert response["result"] == ["yeah it works!"]
	assert not response["error"]


def testRequiringValidMethod():
	j = JsonRpc(None, [], {"id": 1, "method": "foo"})
	j.execute()

	assert j.ended
	assert j.traceback
	assert j.exception

	print("Collected Exception: {0!r}".format(j.exception))

	assert "Method 'foo' is not valid" in str(j.exception)


def testGettingMetainformation():
	j = JsonRpc(None, None, {"id": 1, "method": "foo"})

	assert not j.isStarted()
	assert not j.hasEnded()
	assert j.getMethodName() == "foo"

	assert j.getDuration() is None

	j.execute()

	assert j.isStarted()
	assert j.hasEnded()
	assert j.getDuration() is not None
