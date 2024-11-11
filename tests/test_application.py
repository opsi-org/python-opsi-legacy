# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing application behaviour.

This is based on work by Christian Kampka.
"""

import os
import pytest
import sys

from OPSI.Application import Application, ProfileRunner, CProfileRunner

try:
	import pstats
except ImportError:
	print("Could not import 'pstats'. Please run: apt-get install python-profiler")
	pstats = None


@pytest.fixture
def temporaryProfileFile(tempDir):
	yield os.path.join(tempDir, "profile")


class MockApp(object):
	def __init__(self):
		self.ran = False

	def run(self):
		if self.ran:
			raise Exception("App already ran.")

		self.ran = True


class FakeApplication(Application):
	def __init__(self, config):
		Application.__init__(self, config)
		self.steps = []

	def setup(self):
		self.steps.append("setup")

	def shutdown(self):
		self.steps.append("shutdown")

	def _getApplication(self):
		return MockApp()


def testSetupShutdown():
	"""
	First we should do a setup and the last thing should be shutdown.
	"""
	a = FakeApplication({})

	class MockRunner(object):
		def run(self):
			a.steps.append("run")

	a._runner = MockRunner()
	a.run()

	assert ["setup", "run", "shutdown"] == a.steps


@pytest.mark.skipif(pstats is None, reason="Missing pstats module")
def testProfiler(temporaryProfileFile):
	config = {"profile": temporaryProfileFile, "profiler": "profiler"}

	a = FakeApplication(config)
	a.run()
	assert a._app.ran

	with open(temporaryProfileFile) as f:
		data = f.read()

	assert "MockApp.run" in data
	assert "function calls" in data


@pytest.mark.skipif(pstats is None, reason="Missing pstats module")
def testCProfiler(temporaryProfileFile):
	config = {"profile": temporaryProfileFile, "profiler": "cProfiler"}

	a = FakeApplication(config)
	a.run()
	assert a._app.ran

	with open(temporaryProfileFile) as f:
		data = f.read()

	assert "run" in data
	assert "function calls" in data


def testReactingToMissingProfiler(temporaryProfileFile):
	mods = sys.modules.copy()
	try:
		sys.modules["cProfile"] = None

		config = {"profile": temporaryProfileFile, "profiler": "cProfiler"}

		a = FakeApplication(config)

		with pytest.raises(ImportError):
			a.run()
	finally:
		sys.modules.clear()
		sys.modules.update(mods)


def testUnknownProfiler(temporaryProfileFile):
	config = {"profile": temporaryProfileFile, "profiler": "foobar"}

	with pytest.raises(NotImplementedError):
		FakeApplication(config)


def testDefaultProfiler(temporaryProfileFile):
	config = {"profile": temporaryProfileFile}
	a = FakeApplication(config)
	assert a._runner.__class__ == ProfileRunner


def testCaseInsensitiveProfilerName(temporaryProfileFile):
	config = {"profile": temporaryProfileFile, "profiler": "cPrOfIlEr"}

	a = FakeApplication(config)
	assert a._runner.__class__ == CProfileRunner
