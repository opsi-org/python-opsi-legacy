# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Tests for the dynamically loaded dynamic depot extensions.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/70_dynamic_depot.conf``.

The dynamic depot selection is dynamically loaded onto to the backend
and the user usually selects one of the offered variants.
The code is listet as cleartext because the client makes a call to the
webservice, receives the code and then makes a runnable version of it
through ``exec``.


.. versionadded:: 4.0.4.6
"""

import random

import pytest

from OPSI.Logger import Logger

# Logger is needed because the functions expect a global "logger"
logger = Logger()


def testDepotSelectionAlgorythmIsExecutable(depotSelectionAlgorythm):
	"""
	Executing the default configuration should never fail.
	"""
	currentLocals = locals()
	assert "selectDepot" not in currentLocals
	exec(depotSelectionAlgorythm, None, currentLocals)
	assert "selectDepot" in currentLocals
	selectDepot = currentLocals["selectDepot"]
	print(selectDepot)


def testDepotSelectionAlgorythmReturnsMasterDepotIfNoAlternativesAreGiven(
	depotSelectionAlgorythm,
):
	currentLocals = locals()
	exec(depotSelectionAlgorythm, None, currentLocals)
	selectDepot = currentLocals["selectDepot"]

	masterDepot = FakeDepot("clients.master.depot")
	assert masterDepot == selectDepot({}, masterDepot)


def testDepotSelectionAlgorithmByLowestLatency(depotSelectionAlgorithmByLatency):
	currentLocals = locals()
	exec(depotSelectionAlgorithmByLatency, None, currentLocals)
	selectDepot = currentLocals["selectDepot"]

	masterDepot = FakeDepot("clients.master.depot")
	lowLatencyRepo = FakeDepot("x.y.z", latency=1.5)
	alternativeDepots = [FakeDepot("a"), lowLatencyRepo, FakeDepot("b", latency=5)]
	random.shuffle(alternativeDepots)
	assert lowLatencyRepo == selectDepot({}, masterDepot, alternativeDepots)


def testDepotSelectionByLatencyIgnoresDepotsWithoutLatency(
	depotSelectionAlgorithmByLatency,
):
	currentLocals = locals()
	exec(depotSelectionAlgorithmByLatency, None, currentLocals)
	selectDepot = currentLocals["selectDepot"]

	highLatencyRepo = FakeDepot("a", latency=10)
	alternativeDepots = [highLatencyRepo]
	random.shuffle(alternativeDepots)
	assert highLatencyRepo == selectDepot(
		{}, FakeDepot("m", latency=None), alternativeDepots
	)


def testDepotSelectionAlgorithmByMasterDepotAndLatency(
	depotSelectionAlgorithmByMasterDepotAndLatency,
):
	masterDepot = FakeDepot("clients.master.depot")
	wantedRepo = FakeDepot(
		"our.wanted.repo", latency=1, masterDepotId="clients.master.depot"
	)
	alternativeDepots = [
		FakeDepot("another.master", latency=0.5),
		FakeDepot(
			"sub.for.another.master", latency=0.4, masterDepotId="another.master"
		),
		wantedRepo,
		FakeDepot(
			"slower.repo.with.right.master",
			latency=1.5,
			masterDepotId="clients.master.depot",
		),
	]
	random.shuffle(alternativeDepots)

	loc = {}
	exec(depotSelectionAlgorithmByMasterDepotAndLatency, locals=loc)
	selectDepot = loc["selectDepot"]
	assert wantedRepo == selectDepot({}, masterDepot, alternativeDepots)


def testDepotSelectionAlgorithmByRandom(depotSelectionAlgorithmByRandom):
	EXPECTATION_MARGIN = 0.7
	NUM_DEPOTS = 3  # at least 2
	NUM_RUNS = 300

	loc = {}
	exec(depotSelectionAlgorithmByRandom, locals=loc)
	selectDepot = loc["selectDepot"]

	masterDepot = FakeDepot("clients.master.depot")
	alternativeDepots = [FakeDepot(f"depot{num}") for num in range(NUM_DEPOTS - 1)]
	result_counts = [0] * NUM_DEPOTS
	for _ in range(NUM_RUNS):
		result = selectDepot({}, masterDepot, alternativeDepots)
		try:
			result_counts[alternativeDepots.index(result)] += 1
		except ValueError:  # in case of master depot
			result_counts[-1] += 1
	print("random depot selection distribution:", result_counts)
	for count in result_counts:
		assert count >= EXPECTATION_MARGIN * NUM_RUNS / NUM_DEPOTS


@pytest.fixture(
	params=[
		"getDepotSelectionAlgorithm",  # must always return a working algo
		"getDepotSelectionAlgorithmByLatency",
		"getDepotSelectionAlgorithmByMasterDepotAndLatency",
		"getDepotSelectionAlgorithmByNetworkAddress",
		"getDepotSelectionAlgorithmByRandom",
	]
)
def depotSelectionAlgorythm(request, backendManager):
	"""
	All possible algorythms.
	"""
	algorythm = getattr(backendManager, request.param)
	return algorythm()


@pytest.fixture
def depotSelectionAlgorithmByLatency(backendManager):
	algo = backendManager.getDepotSelectionAlgorithmByLatency()
	algo = patchPingFunctionalityInAlgorythm(algo)

	try:
		yield algo
	except Exception:
		showAlgoWithLineNumbers(algo)


@pytest.fixture
def depotSelectionAlgorithmByMasterDepotAndLatency(backendManager):
	algo = backendManager.getDepotSelectionAlgorithmByMasterDepotAndLatency()
	algo = patchPingFunctionalityInAlgorythm(algo)

	try:
		yield algo
	except Exception:
		showAlgoWithLineNumbers(algo)


@pytest.fixture
def depotSelectionAlgorithmByRandom(backendManager):
	algo = backendManager.getDepotSelectionAlgorithmByRandom()
	algo = patchPingFunctionalityInAlgorythm(algo)

	try:
		yield algo
	except Exception:
		showAlgoWithLineNumbers(algo)


def patchPingFunctionalityInAlgorythm(algorythm):
	# very dirty
	algorythm = algorythm.replace("ping(host)", "depot.latency")

	return algorythm


def showAlgoWithLineNumbers(algo):
	"""
	Prints the given algorythm with line numbers preceding each line.
	"""
	for number, line in enumerate(algo.split("\n")):
		print("{num}: {line}".format(num=number, line=line))


class FakeDepot:
	def __init__(self, id, latency=2, masterDepotId=None):
		self.id = id
		self.latency = latency
		self.repositoryRemoteUrl = self.id
		self.masterDepotId = masterDepotId

	def __repr__(self):
		return "<FakeDepot({id}, latency={latency}, masterDepotId={masterDepotId})>".format(
			**self.__dict__
		)
