# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
This file is part of opsi - https://www.opsi.org
"""

import io
import logging
from contextlib import contextmanager

import pytest
from opsicommon.logging import logger, logging_config, secret_filter
from opsicommon.logging.constants import LOG_SECRET, LOG_TRACE

from OPSI.Logger import Logger as LegacyLogger

MY_FORMAT = "%(log_color)s[%(opsilevel)d] [%(asctime)s.%(msecs)03d]%(reset)s [%(contextstring)s] %(message)s"
OTHER_FORMAT = "[%(opsilevel)d] [%(asctime)s.%(msecs)03d] [%(contextstring)s] %(message)s   (%(filename)s:%(lineno)d)"


class Utils:
	@staticmethod
	@contextmanager
	def log_stream(new_level, format=None):
		stream = io.StringIO()
		logging_config(stderr_level=new_level, stderr_format=format, stderr_file=stream)
		try:
			yield stream
		finally:
			# somehow revert to previous values? Impossible as logging_config deletes all stream handlers
			pass


@pytest.fixture
def utils():
	return Utils


def test_legacy_logger_file(utils):
	with utils.log_stream(LOG_SECRET) as stream:
		legacy_logger = LegacyLogger("/tmp/test.log")
		assert legacy_logger == logger
		legacy_logger.info("test should appear")

		stream.seek(0)
		log = stream.read()
		assert "test should appear" in log

	with open("/tmp/test.log", encoding="utf-8") as logfile:
		content = logfile.read()
		assert "test should appear" in content


def test_legacy_logger(utils):
	with utils.log_stream(LOG_TRACE) as stream:
		legacy_logger = LegacyLogger()
		assert legacy_logger == logger
		# init_logging(file_level=logging.SECRET)
		# legacy_logger.setLogFile("/tmp/test.log")
		# This method does nothing
		legacy_logger.setLogFormat("xy")

		secret_filter.set_min_length(7)
		legacy_logger.setConfidentialStrings(["SECRETSTRING1", "SECRETSTRING2"])
		legacy_logger.addConfidentialString("SECRETSTRING3")
		legacy_logger.info("SECRETSTRING1 SECRETSTRING2 SECRETSTRING3")

		stream.seek(0)
		log = stream.read()
		assert "SECRETSTRING1" not in log
		assert "SECRETSTRING2" not in log
		assert "SECRETSTRING3" not in log

		legacy_logger.logException(
			Exception("LOG_EXCEPTION"), logLevel=logging.CRITICAL
		)
		stream.seek(0)
		log = stream.read()
		assert "LOG_EXCEPTION" in log


def test_legacy_logger_calls(utils):
	legacy_logger = LegacyLogger()
	assert legacy_logger == logger
	legacy_logger.getStderr()
	legacy_logger.getStdout()
	legacy_logger.setConfidentialStrings(["topsecret"])
	legacy_logger.addConfidentialString("evenmoresecret")
	legacy_logger.setLogFormat("%s some format %s", currentThread=False, object=None)
	legacy_logger.setConsoleFormat(
		"%s some format %s", currentThread=False, object=None
	)
	legacy_logger.setComponentName("name", currentThread=False, object=None)
	legacy_logger.logToStdout(None)
	legacy_logger.setSyslogFormat("%s some format %s", currentThread=False, object=None)
	legacy_logger.setFileFormat("%s some format %s", currentThread=False, object=None)
	legacy_logger.setUniventionFormat(
		"%s some format %s", currentThread=False, object=None
	)
	legacy_logger.setMessageSubjectFormat(
		"%s some format %s", currentThread=False, object=None
	)
	legacy_logger.setUniventionLogger(None)
	legacy_logger.setUniventionClass(None)
	legacy_logger.getMessageSubject()
	legacy_logger.setColor(True)
	legacy_logger.setConsoleColor(True)
	legacy_logger.setSyslogLevel(0)
	legacy_logger.setMessageSubjectLevel(0)
	legacy_logger.setConsoleLevel(0)
	legacy_logger.getConsoleLevel()
	legacy_logger.getFileLevel()
	legacy_logger.getLogFile(currentThread=False, object=None)
	legacy_logger.setLogFile("logfile.log", currentThread=False, object=None)
	legacy_logger.linkLogFile("logfile", currentThread=False, object=None)
	legacy_logger.setFileLevel(0)
	legacy_logger.exit(object=None)
	legacy_logger._setThreadConfig(None, None)
	legacy_logger._getThreadConfig(key=None)
	legacy_logger._setObjectConfig(None, None, None)
	legacy_logger._getObjectConfig(None, key=None)
	legacy_logger.logException(None)
	legacy_logger.logFailure(None)
	legacy_logger.logTraceback(None)
	legacy_logger.logWarnings()
	legacy_logger.startTwistedLogging()
	legacy_logger.setConsoleLevel(9)

	with utils.log_stream(LOG_SECRET) as stream:
		legacy_logger.confidential("mymessage %s", "fill-value")
		legacy_logger.debug3("mymessage %s", "fill-value")
		legacy_logger.debug2("mymessage %s", "fill-value")
		legacy_logger.debug("mymessage %s", "fill-value")
		legacy_logger.info("mymessage %s", "fill-value")
		legacy_logger.msg("mymessage %s", "fill-value")
		legacy_logger.notice("mymessage %s", "fill-value")
		legacy_logger.warning("mymessage %s", "fill-value")
		legacy_logger.error("mymessage %s", "fill-value")
		legacy_logger.err("mymessage %s", "fill-value")
		legacy_logger.critical("mymessage %s", "fill-value")
		legacy_logger.essential("mymessage %s", "fill-value")
		legacy_logger.comment("mymessage %s", "fill-value")
		# calling log still fails as method signature has changed with opsi 4.2
		# legacy_logger.log(3, "text %s", raiseException=False, formatArgs=["some format arg"], formatKwargs={})
		stream.seek(0)
		log = stream.read()
		assert log.count("fill-value") == 13
