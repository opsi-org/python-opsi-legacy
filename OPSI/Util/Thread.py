# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - Thread
"""

import ctypes
import inspect
import threading
from queue import Empty, Queue

from opsicommon.logging import get_logger

logger = get_logger("opsi.general")
global_pool = None  # pylint: disable=invalid-name


class ThreadPoolException(Exception):
	pass


def getGlobalThreadPool(*args, **kwargs):
	global global_pool  # pylint: disable=global-statement,invalid-name
	if not global_pool:
		global_pool = ThreadPool(*args, **kwargs)
	else:
		size = kwargs.get("size", 0)
		global_pool.increaseUsageCount()
		if global_pool.size < size:
			global_pool.adjustSize(size)

	return global_pool


def _async_raise(tid, exctype):
	"""raises the exception, performs cleanup if needed"""
	if not inspect.isclass(exctype):
		raise TypeError("Only types can be raised (not instances)")

	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
		ctypes.c_long(tid), ctypes.py_object(exctype)
	)
	if res == 0:
		logger.warning("Invalid thread id %s", tid)
		return
	if res != 1:
		# if it returns a number greater than one, you're in trouble,
		# and you should call it again with exc=NULL to revert the effect
		ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), 0)
		raise SystemError("PyThreadState_SetAsyncExc failed")


class KillableThread(threading.Thread):
	def _get_my_tid(self):
		"""determines this (self's) thread id"""
		# do we have it cached?
		if hasattr(self, "_thread_id"):
			return self._thread_id  # pylint: disable=access-member-before-definition

		# no, look for it in the _active dict
		for tid, tobj in threading._active.items():  # pylint: disable=protected-access
			if tobj is self:
				self._thread_id = tid  # pylint: disable=attribute-defined-outside-init
				return tid

		logger.warning("Cannot terminate, could not determine the thread's id")
		return None

	def raise_exc(self, exctype):
		"""raises the given exception type in the context of this thread"""
		_async_raise(self._get_my_tid(), exctype)

	def terminate(self):
		"""raises SystemExit in the context of the given thread, which should
		cause the thread to exit silently (unless caught)"""
		if not self.is_alive():
			logger.debug("Cannot terminate, thread must be started")
			return
		self.raise_exc(SystemExit)


class ThreadPool:
	def __init__(self, size=20, autostart=True):
		self.size = int(size)
		self.started = False
		self.worker = []
		self.workerLock = threading.Lock()
		self.jobQueue = Queue()
		self.usageCount = 1
		if autostart:
			self.start()

	def increaseUsageCount(self):
		self.usageCount += 1

	def decreaseUsageCount(self):
		self.usageCount -= 1
		if self.usageCount <= 0:
			self.stop()

	free = decreaseUsageCount

	def start(self):
		self.started = True
		self.adjustSize(self.size)

	def adjustSize(self, size):
		size = int(size)
		if size < 1:
			raise ThreadPoolException(f"Threadpool size {size} is invalid")

		with self.workerLock:
			self.size = size
			if self.started:
				if len(self.worker) > self.size:
					self.__deleteWorkers(num=len(self.worker) - self.size)
				if len(self.worker) < self.size:
					self.__createWorkers(num=self.size - len(self.worker))

	def __deleteWorkers(self, num, wait=False):
		logger.debug("Deleting %d workers", num)
		deleteWorkers = set()

		for worker in self.worker:
			if (not worker.busy) and worker not in deleteWorkers:
				deleteWorkers.add(worker)
				worker.stop()
				num -= 1
				if num == 0:
					break

		if num > 0:
			for worker in self.worker:
				if worker not in deleteWorkers:
					deleteWorkers.add(worker)
					worker.stop()
					num -= 1
					if num == 0:
						break

		self.worker = [worker for worker in self.worker if worker not in deleteWorkers]

		if wait:
			for worker in deleteWorkers:
				worker.join(60)

	def __createWorkers(self, num):
		logger.debug("Creating %s new workers", num)
		while num > 0:
			self.worker.append(Worker(self, len(self.worker) + 1))
			num -= 1

	def addJob(self, function, *args, callback=None, **kwargs):
		logger.debug("New job added: %s(%s, %s)", callback, args, kwargs)
		if not self.started:
			raise ThreadPoolException("Pool is not running.")
		self.jobQueue.put((function, callback, args, kwargs))

	def stop(self):
		logger.debug("Stopping ThreadPool")
		with self.workerLock:
			self.started = False
			self.__deleteWorkers(num=len(self.worker), wait=True)


class Worker(threading.Thread):
	def __init__(self, threadPool, name=None):
		threading.Thread.__init__(self, name=name)
		self.threadPool = threadPool
		self.name = name
		self.busy = False
		self.stopped = False
		self.start()

	def run(self):
		while True:
			if self.stopped:
				break

			try:
				callResult = self.threadPool.jobQueue.get(block=True, timeout=1)
				if callResult:
					self.busy = True
					(function, callback, args, kwargs) = callResult
					success = False
					try:
						result = function(*args, **kwargs)
						success = True
						errors = None
					except Exception as error:  # pylint: disable=broad-except
						logger.debug("Problem running function: '%s'", error)
						result = None
						errors = error

					if callback:
						callback(success, result, errors)

					self.threadPool.jobQueue.task_done()
					self.busy = False
			except Empty:
				pass

	def stop(self):
		self.stopped = True
