# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing ConfigDataBackend.
"""

import os

import pytest

import OPSI.Backend.Backend
from OPSI.Exceptions import BackendBadValueError
from OPSI.Util import removeUnit
from OPSI.Util.Log import truncateLogData

from .helpers import mock


@pytest.fixture
def logBackend(patchLogDir):
	yield OPSI.Backend.Backend.ConfigDataBackend()


@pytest.fixture
def patchLogDir(tempDir):
	with mock.patch("OPSI.Backend.Base.ConfigData.LOG_DIR", tempDir):
		yield tempDir


def testReadingLogFailsIfTypeUnknown(logBackend):
	with pytest.raises(BackendBadValueError):
		logBackend.log_read("unknowntype")


@pytest.mark.parametrize(
	"logType", ["bootimage", "clientconnect", "instlog", "userlogin", "winpe"]
)
def testReadingLogRequiresObjectId(logBackend, logType):
	with pytest.raises(BackendBadValueError):
		logBackend.log_read(logType)


def testReadingOpsiconfdLogDoesNotRequireObjectId(logBackend):
	logBackend.log_read("opsiconfd")


@pytest.mark.parametrize("objectId", [None, "unknown_object"])
def testReadingNonExistingLogReturnsEmptyString(logBackend, objectId):
	"""
	Valid calls to read logs should return empty strings if no file
	does exist.
	"""
	assert logBackend.log_read("opsiconfd", objectId) == ""


def testOnlyValidLogTypesAreWritten(logBackend):
	with pytest.raises(BackendBadValueError):
		logBackend.log_write("foobar", "")


@pytest.mark.parametrize(
	"objectId",
	[
		"foo.bar.baz",
		"opsiconfd",
		pytest.param("", marks=pytest.mark.xfail),
		pytest.param(None, marks=pytest.mark.xfail),
	],
)
@pytest.mark.parametrize(
	"logType",
	[
		"bootimage",
		"clientconnect",
		"instlog",
		"opsiconfd",
		"userlogin",
		"winpe",
	],
)
def testWritingLogRequiresValidObjectId(logBackend, logType, objectId):
	logBackend.log_write(logType, "logdata", objectId)


def testWritingAndThenReadingDataFromLog(logBackend):
	logBackend.log_write("opsiconfd", "data", objectId="foo.bar.baz")

	assert logBackend.log_read("opsiconfd", "foo.bar.baz") == "data"


@pytest.mark.parametrize(
	"logType",
	["bootimage", "clientconnect", "instlog", "opsiconfd", "userlogin", "winpe"],
)
def testWritingLogCreatesFile(patchLogDir, logType):
	cdb = OPSI.Backend.Backend.ConfigDataBackend()
	cdb.log_write(logType, "logdata", objectId="foo.bar.baz")

	expectedLogDir = os.path.join(patchLogDir, logType)
	assert os.path.exists(expectedLogDir)

	expectedLogPath = os.path.join(expectedLogDir, "foo.bar.baz.log")
	assert os.path.exists(expectedLogPath)


@pytest.mark.parametrize(
	"expected, text, length",
	[
		("", "hallo\nwelt", 0),
		("o", "hallo", 1),
		("llo", "hallo", 3),
		("elt", "hallo\nwelt", 3),
		("welt", "hallo\nwelt", 4),
		("welt", "hallo\nwelt", 5),
		("hallo\nwelt", "hallo\nwelt", 10),
		("welt\n", "hallo\nwelt\n", 10),
		("hallo\nwelt", "hallo\nwelt", 15),
	],
)
def testTruncatingLogData(text, length, expected):
	assert expected == truncateLogData(text, length)


def test_log_file_rotation_keep_0(patchLogDir):
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=10, keepRotatedLogs=0)
	object_id = "foo.bar.baz"

	data = "aaaaaaaaaaa"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert os.listdir(os.path.join(patchLogDir, "opsiconfd")) == [f"{object_id}.log"]
	assert data == cdb.log_read("opsiconfd", object_id)

	data = "bbbbbbbbbbb"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert os.listdir(os.path.join(patchLogDir, "opsiconfd")) == [f"{object_id}.log"]
	assert data == cdb.log_read("opsiconfd", object_id)


def test_log_file_rotation_append(patchLogDir):
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=10, keepRotatedLogs=2)
	object_id = "foo.bar.baz"

	data = "aaaaaaaaaaa"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert os.listdir(os.path.join(patchLogDir, "opsiconfd")) == [f"{object_id}.log"]
	assert data == cdb.log_read("opsiconfd", object_id)

	data = "bbbbbbbbbbb"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert sorted(os.listdir(os.path.join(patchLogDir, "opsiconfd"))) == [
		f"{object_id}.log",
		f"{object_id}.log.1",
	]
	assert data == cdb.log_read("opsiconfd", object_id)

	data = "ccccccccccc"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert sorted(os.listdir(os.path.join(patchLogDir, "opsiconfd"))) == [
		f"{object_id}.log",
		f"{object_id}.log.1",
		f"{object_id}.log.2",
	]
	assert data == cdb.log_read("opsiconfd", object_id)

	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=10, keepRotatedLogs=1)
	data = "ddddddddddd"
	cdb.log_write("opsiconfd", data, objectId=object_id, append=True)
	assert sorted(os.listdir(os.path.join(patchLogDir, "opsiconfd"))) == [
		f"{object_id}.log",
		f"{object_id}.log.1",
	]
	assert data == cdb.log_read("opsiconfd", object_id)

	with open(
		os.path.join(patchLogDir, "opsiconfd", f"{object_id}.log"), encoding="utf-8"
	) as file:
		assert file.read() == "ddddddddddd"
	with open(
		os.path.join(patchLogDir, "opsiconfd", f"{object_id}.log.1"), encoding="utf-8"
	) as file:
		assert file.read() == "ccccccccccc"


def testWritingAndThenReadingDataFromLogWithLimitedRead(logBackend):
	objId = "foo.bar.baz"
	longData = "data1\ndata2\ndata3\ndata4\n"
	logBackend.log_write("opsiconfd", longData, objectId=objId)

	assert logBackend.log_read("opsiconfd", objId, maxSize=10) == "data4\n"


def testAppendingLog(patchLogDir):
	data1 = "data1\ndata2\ndata3\ndata4\n"
	data2 = "data5\n"

	maxLogSize = len(data1 + data2)
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=maxLogSize)

	cdb.log_write("opsiconfd", data1, objectId="foo.bar.baz")
	cdb.log_write("opsiconfd", data2, objectId="foo.bar.baz", append=True)

	logData = cdb.log_read("opsiconfd", "foo.bar.baz", maxSize=maxLogSize)
	assert data1 + data2 == logData


def testWritingAndReadingLogWithoutLimits(patchLogDir):
	# 0 means no limit.
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=0)

	# The magic 218454 are meant to be more than:
	# MAX_LOG_SIZE / len('data1\ndata2\ndata3\ndata4\n')
	longData = "data1\ndata2\ndata3\ndata4\n" * 218454
	cdb.log_write("opsiconfd", longData, objectId="foo.bar.baz")

	assert longData == cdb.log_read("opsiconfd", "foo.bar.baz", maxSize=0)


def testOverwritingOldDataInAppendMode(patchLogDir):
	"""
	With size limits in place old data should be overwritten.

	Each write operation submits data that is as long as our limit.
	So every write operation should override the previously written
	data.
	"""
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=4)

	objId = "foo.bar.baz"
	cdb.log_write("opsiconfd", "data1", objectId=objId, append=True)
	cdb.log_write("opsiconfd", "data2", objectId=objId, append=True)
	cdb.log_write("opsiconfd", "data3", objectId=objId, append=True)

	assert cdb.log_read("opsiconfd", objectId=objId, maxSize=0) == "data3"


@pytest.fixture(scope="session", params=["2kb", "4kb"])
def longText(request):
	"""
	Create a long text roughly about the given size.
	The text will include unicode characters using more than one byte per
	character.
	The text will not be longer than the given size but may be a few bytes short.
	"""
	size = removeUnit(request.param)

	text = []
	i = 0
	length = 0
	while length <= size:
		snippet = (
			f"This is line {i} - we have some more text with special unicode: üöä \n"
		)
		curLenght = len(snippet.encode("utf-8"))
		if curLenght + length > size:
			break

		length += curLenght
		text.append(snippet)
		i += 1

	return "".join(text)


@pytest.mark.parametrize(
	"sizeLimit",
	[
		pytest.param("1kb", marks=pytest.mark.skip(reason="Todo: Fails but why?")),
		pytest.param("2kb", marks=pytest.mark.skip(reason="Todo: Fails but why?")),
		pytest.param("8kb", marks=pytest.mark.skip(reason="Todo: Fails but why?")),
	],
)
def testLimitingTheReadTextInSize(patchLogDir, longText, sizeLimit):
	"""
	Limiting text must work with all unicode characters.

	The text may include unicode characters using more than one byte.
	This must not hinder the text limitation.
	"""
	limit = removeUnit(sizeLimit)
	cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=limit)

	objId = "foo.bar.baz"
	cdb.log_write("instlog", longText, objectId=objId)
	textFromBackend = cdb.log_read("instlog", objectId=objId, maxSize=limit)

	assert len(textFromBackend.encode("utf-8")) < limit


def testGettingSystemConfig(configDataBackend):
	sysConfig = configDataBackend.backend_getSystemConfiguration()

	assert "log" in sysConfig

	logSizeLimit = sysConfig["log"]["size_limit"]
	logSizeLimit = int(logSizeLimit)
	assert logSizeLimit is not None

	for expectedLogType in (
		"bootimage",
		"clientconnect",
		"instlog",
		"opsiconfd",
		"userlogin",
		"winpe",
	):
		assert expectedLogType in sysConfig["log"]["types"]
