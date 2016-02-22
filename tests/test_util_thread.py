# -*- coding: utf-8 -*-
"""
Copyright (C) 2010-2016 uib GmbH

http://www.uib.de/

All rights reserved.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License version 2 as
published by the Free Software Foundation.

This program is distributed in the hope thatf it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

:author: Christian Kampka <c.kampka@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU General Public License version 2
"""
import datetime
import time
import threading
import unittest

from OPSI.Util.Thread import ThreadPoolException, ThreadPool, getGlobalThreadPool, KillableThread


class ThreadPoolTestCase(unittest.TestCase):
    POOL_SIZE = 10

    def setUp(self):
        self.pool = ThreadPool(size=self.POOL_SIZE, autostart=False)
        self.pool.start()

    def tearDown(self):
        self.pool.stop()

    def adjustSize(self, size):
        self.pool.adjustSize(size=size)

    def test_WorkerCreation(self):
        self.pool.adjustSize(size=10)
        self.assertEqual(10, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (10, len(self.pool.worker)))

    def test_stopPool(self):
        self.pool.adjustSize(size=10)
        for i in range(5):
            time.sleep(0.1)
        numThreads = threading.activeCount() - len(self.pool.worker)
        self.pool.stop()

        self.assertEqual(0, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (0, len(self.pool.worker)))
        self.assertFalse(self.pool.started, "Expected pool to have stopped, but it hasn't")
        self.assertEqual(threading.activeCount(), numThreads, "Expected %s thread to be alive, but got %s" % (numThreads, threading.activeCount()))

    def test_workerCallback(self):
        self.pool.adjustSize(2)

        result = []
        def assertCallback(success, returned, errors):
            result.append(success)
            result.append(returned)
            result.append(errors)


        self.pool.addJob(function=(lambda: 'test'), callback=assertCallback)

        #give thread time to finish
        time.sleep(1)

        self.assertEqual(True, result[0])
        self.assertEqual(result[1], 'test')
        self.assertEqual(None, result[2])

    def test_workerCallbackWithException(self):
        self.pool.adjustSize(2)

        result = []
        def assertCallback(success, returned, errors):
            result.append(success)
            result.append(returned)
            result.append(errors)

        def raiseError():
            raise Exception("TestException")

        self.pool.addJob(function=raiseError, callback=assertCallback)

        #give thread time to finish
        time.sleep(1)

        self.assertEqual(False, result[0])
        self.assertEqual(None, result[1])
        self.assertNotEqual(None, result[2])

    def test_invalidThreadPoolSize(self):
        try:
            self.pool.adjustSize(-1)
            self.fail("ThreadPool has an invalid size, but no exception was raised.")
        except ThreadPoolException as e:
            return
        except Exception as e:
            self.fail(e)

    def test_adjustPoolSize(self):
        self.pool.adjustSize(size=2)
        self.pool.adjustSize(size=10)

        time.sleep(1)

        self.assertEqual(10, self.pool.size, "Expected pool size to be %s, but got %s." % (10 , self.pool.size))
        self.assertEqual(10, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" %(10, len(self.pool.worker)))

        self.pool.adjustSize(size=2)

        self.assertEqual(2, self.pool.size, "Expected pool size to be %s, but got %s." % (2 , self.pool.size))
        self.assertEqual(2, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (2, len(self.pool.worker)))

    def test_floodPool(self):
        self.pool.adjustSize(2)

        results = []
        def callback(success, returned, errors):
            results.append(success)

        def waitJob():
            for i in range(3):
                time.sleep(1)

        for i in range(5):
            self.pool.addJob(waitJob, callback=callback)

        self.assertEquals(2, len(self.pool.worker),
            "Expected %s worker in pool, but got %s" % (2, len(self.pool.worker)))
        self.assertTrue(self.pool.jobQueue.unfinished_tasks > len(self.pool.worker),
        "Expected more tasks in Queue than workers in pool, but got %s tasks and %s worker" % (self.pool.jobQueue.unfinished_tasks, len(self.pool.worker)))

        for i in range(10):
            time.sleep(0.4)
        self.assertEquals(5, len(results), "Expected %s results but, but got %s" % (5, len(results)))

    def test_globalPool(self):
        pool1 = getGlobalThreadPool()
        pool2 = getGlobalThreadPool()

        self.assertTrue(isinstance(pool1, ThreadPool), "Expected %s to be a ThreadPool instance." % pool1)
        self.assertEqual(pool1, pool2)

        pool2.adjustSize(5)
        self.assertEqual(pool1.size, 5)

        pool1.stop()

    def test_dutyAfterNoDuty(self):
        self.pool.adjustSize(5)
        self.pool.stop()
        self.pool.start()

        results = []
        def callback(success, returned, errors):
            results.append(success)

        def shortJob():
            _ = 10 * 10

        for i in range(10):
            self.pool.addJob(shortJob, callback=callback)

        time.sleep(1)
        self.assertEquals(10, len(results), "Expected %s results, but got %s" % (10, len(results)))

        time.sleep(2)
        results = []
        for i in range(10):
            self.pool.addJob(shortJob, callback=callback)
        time.sleep(1)
        self.assertEquals(10, len(results), "Expected %s results, but got %s" % (10, len(results)))

    def test_grow(self):
        self.pool.adjustSize(2)
        self.pool.stop()
        self.pool.start()

        results = []
        def callback(success, returned, errors):
            results.append(success)

        def sleepJob():
            time.sleep(2)

        for i in range(10):
            self.pool.addJob(sleepJob, callback=callback)
        time.sleep(3)
        self.assertEqual(len(results), 2, "Expected %s results, but got %s" % (2, len(results)))

        self.pool.adjustSize(10)
        time.sleep(3)
        self.assertEquals(len(results), 10, "Expected %s results, but got %s" % (10, len(results)))

    def test_shrink(self):
        self.pool.adjustSize(5)
        self.pool.stop()
        self.pool.start()

        results = []
        def callback(success, returned, errors):
            results.append(success)

        def sleepJob():
            time.sleep(2)

        for i in range(12):
            self.pool.addJob(sleepJob, callback=callback)
        time.sleep(3)
        self.assertEqual(len(results), 5, "Expected %s results, but got %s" % (5, len(results)))

        self.pool.adjustSize(1)
        time.sleep(2)
        self.assertEquals(len(results), 10,  "Expected %s results, but got %s" % (10, len(results)))
        time.sleep(2)
        self.assertEquals(len(results), 11,  "Expected %s results, but got %s" % (11, len(results)))
        time.sleep(2)
        self.assertEquals(len(results), 12,  "Expected %s results, but got %s" % (12, len(results)))

    def testDecreasingUsageCount(self):
        self.pool.increaseUsageCount()
        self.assertEquals(2, self.pool.usageCount)

        self.pool.decreaseUsageCount()
        self.assertEquals(1, self.pool.usageCount)

    def testDecreasingUsageCountBelowZeroStopsThreadPool(self):
        self.assertTrue(self.pool.started)
        self.assertEquals(1, self.pool.usageCount)
        self.pool.decreaseUsageCount()
        self.assertEquals(0, self.pool.usageCount)
        self.assertFalse(self.pool.started)


class KillableThreadTestCase(unittest.TestCase):
    def test_terminating_running_thread(self):
        """
        It must be possible to interrupt running threads even though
        they may still be processing.
        """

        class ThirtySecondsToEndThread(KillableThread):
            def __init__(self, testCase):
                super(ThirtySecondsToEndThread, self).__init__()

                self.testCase = testCase

            def run(self):
                start = datetime.datetime.now()
                thirtySeconds = datetime.timedelta(seconds=30)

                while datetime.datetime.now() < (start + thirtySeconds):
                    time.sleep(0.1)

                self.testCase.fail("Thread did not get killed in time.")


        runningThread = ThirtySecondsToEndThread(self)
        runningThread.start()

        try:
            time.sleep(2)
            self.assertTrue(runningThread.isAlive(), "Thread should be running.")

            runningThread.terminate()

            time.sleep(2)
            self.assertFalse(runningThread.isAlive(), "Thread should be killed.")
        finally:
            runningThread.join(2)


if __name__ == '__main__':
    unittest.main()
