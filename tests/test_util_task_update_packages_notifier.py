# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the opsi-package-updater functionality.
"""

import pytest

from OPSI.Util.Task.UpdatePackages.Notifier import DummyNotifier, EmailNotifier

from opsicommon.logging import secret_filter


@pytest.fixture(
	params=[DummyNotifier, EmailNotifier], ids=["DummyNotifier", "EmailNotifier"]
)
def notifierClass(request):
	yield request.param


@pytest.fixture
def notifierConfig(notifierClass):
	if issubclass(notifierClass, EmailNotifier):
		return {"receivers": ["devnull@mailserver.local"]}

	return {}


@pytest.fixture
def notifier(notifierClass, notifierConfig):
	yield notifierClass(**notifierConfig)


def testSetupNotifier(notifierClass, notifierConfig):
	dummy = notifierClass(**notifierConfig)
	assert dummy

	assert not dummy.hasMessage()


def testAddingMessages(notifier):
	assert not notifier.hasMessage()

	notifier.appendLine("Bla bla bla")

	assert notifier.hasMessage()


def testSecrets(notifier):
	secret_filter.add_secrets("testsecret")
	notifier.appendLine("this is a testsecret secret blubb")

	assert "testsecret" not in notifier.message
