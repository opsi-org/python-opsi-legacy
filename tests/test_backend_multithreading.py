# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing backend multithreading behaviour.
"""

import threading
import time

import pytest

from OPSI.Backend.Backend import ExtendedConfigDataBackend
from .test_groups import fillBackendWithObjectToGroups


@pytest.mark.parametrize("numberOfThreads", [50])
def testMultiThreadingBackend(multithreadingBackend, numberOfThreads):
	backend = ExtendedConfigDataBackend(multithreadingBackend)

	o2g, _, clients = fillBackendWithObjectToGroups(backend)

	print("====================START=============================")

	class MultiThreadTester(threading.Thread):
		def __init__(self, backend, clients, objectToGroups):
			threading.Thread.__init__(self)

			self.error = None

			self.backend = backend
			self.clients = clients
			self.objectToGroups = objectToGroups

		def run(self):
			self.client1 = clients[0]
			self.client2 = clients[1]
			self.objectToGroup1 = o2g[0]
			self.objectToGroup2 = o2g[1]

			try:
				print("Thread %s started" % self)
				time.sleep(1)
				self.backend.host_getObjects()
				self.backend.host_deleteObjects(self.client1)

				self.backend.host_getObjects()
				self.backend.host_deleteObjects(self.client2)

				self.backend.host_createObjects(self.client2)
				self.backend.host_createObjects(self.client1)
				self.backend.objectToGroup_createObjects(self.objectToGroup1)
				self.backend.objectToGroup_createObjects(self.objectToGroup2)

				self.backend.host_getObjects()
				self.backend.host_createObjects(self.client1)
				self.backend.host_deleteObjects(self.client2)
				self.backend.host_createObjects(self.client1)
				self.backend.host_getObjects()
			except Exception as err:
				if "duplicate entry" in str(err).lower():
					# Allow duplicate entry error
					pass
				else:
					self.error = err
			finally:
				print("Thread %s done" % self)

	mtts = [MultiThreadTester(backend, clients, o2g) for i in range(numberOfThreads)]
	for mtt in mtts:
		mtt.start()

	for mtt in mtts:
		mtt.join()

	client1 = clients[0]
	backend.host_createObjects(client1)

	while mtts:
		mtt = mtts.pop(0)
		if not mtt.is_alive():
			assert not mtt.error, f"Multithreading test failed: Exit Code {mtt.error}"
		else:
			mtts.append(mtt)
