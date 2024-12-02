# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
OPSI.Util.Repository
"""

import ipaddress
import os
import posixpath
import re
import shutil
import socket
import stat
import statistics
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlparse

import requests
from opsicommon.logging import get_logger, secret_filter
from opsicommon.utils import prepare_proxy_environment
from requests.adapters import HTTPAdapter
from requests.packages import urllib3

from OPSI import __version__
from OPSI.Exceptions import RepositoryError
from OPSI.System import mount, umount
from OPSI.Types import (
	forceBool,
	forceFilename,
	forceInt,
	forceUnicode,
	forceUnicodeList,
)
from OPSI.Util import md5sum, randomString
from OPSI.Util.File.Opsi import PackageContentFile
from OPSI.Util.Message import ProgressSubject
from OPSI.Util.Path import cd

if os.name == "nt":
	from OPSI.System.Windows import getFreeDrive

urllib3.disable_warnings()
logger = get_logger("opsi.general")


def _(string):
	return string


def getRepository(url, **kwargs):
	if re.search(r"^file://", url, re.IGNORECASE):
		return FileRepository(url, **kwargs)
	if re.search(r"^https?://", url, re.IGNORECASE):
		return HTTPRepository(url, **kwargs)
	if re.search(r"^webdavs?://", url, re.IGNORECASE):
		return WebDAVRepository(url, **kwargs)
	if re.search(r"^(smb|cifs)://", url, re.IGNORECASE):
		return CIFSRepository(url, **kwargs)

	raise RepositoryError(f"Repository url '{url}' not supported")


def getFileInfosFromDavXML(davxmldata, encoding="utf-8"):
	content = []
	root = ET.fromstring(davxmldata)
	for child in root:
		info = {"size": 0, "type": "file", "path": "", "name": ""}
		if child.tag != "{DAV:}response":
			raise RepositoryError("No valid davxml given")

		if child[0].tag == "{DAV:}href":
			info["path"] = unquote(child[0].text)
			info["name"] = info["path"].rstrip("/").rsplit("/", maxsplit=1)[-1]

		if child[1].tag == "{DAV:}propstat":
			for node in child[1]:
				if node.tag != "{DAV:}prop":
					continue

				for childnode in node:
					tag = childnode.tag
					text = childnode.text
					if tag == "{DAV:}getcontenttype":
						if "directory" in text:
							info["type"] = "dir"
					elif tag == "{DAV:}resourcetype":
						for resChild in childnode:
							if resChild.tag == "{DAV:}collection":
								info["type"] = "dir"
					elif tag == "{DAV:}getcontentlength":
						if text != "None":
							info["size"] = int(text)
					# elif tag == "{DAV:}displayname":
					# info['name'] = text

				# IIS Fix: Remove trailing backslash on file-paths
				if info["type"] == "file" and info["path"].endswith("/"):
					info["path"] = info["path"][:-1]

			content.append(info)

	return content


class RepositoryHook:
	def __init__(self):
		pass

	def pre_Repository_copy(
		self, source, destination, overallProgressSubject, currentProgressSubject
	):
		return (source, destination, overallProgressSubject, currentProgressSubject)

	def post_Repository_copy(
		self, source, destination, overallProgressSubject, currentProgressSubject
	):
		return None

	def error_Repository_copy(
		self,
		source,
		destination,
		overallProgressSubject,
		currentProgressSubject,
		exception,
	):
		pass


class SpeedLimiter:
	_dynamic_bandwidth_threshold_limit = 0.75
	_dynamic_bandwidth_threshold_no_limit = 0.95
	_dynamic_bandwidth_limit_rate = 0.2
	_default_min_buffer_size = 16
	_default_max_buffer_size = 256 * 1024

	def __init__(
		self,
		min_buffer_size: int = _default_min_buffer_size,
		max_buffer_size: int = _default_max_buffer_size,
	):
		self._dynamic = False
		self._max_bandwidth = 0
		self._network_performance_counter = None
		self._min_buffer_size = int(min_buffer_size)
		self._max_buffer_size = int(max_buffer_size)

		self._transfer_direction = "out"

		self._speed_data = []
		self._current_speed = 0.0
		self._average_speed = 0.0

		self._network_usage_data = {}
		self._network_bandwidth = 0.0
		self._dynamic_bandwidth_limit = 0.0
		self._bandwidth_sleep_time = 0.0

	def __del__(self):
		if self._network_performance_counter:
			self._stop_network_performance_counter()

	def _reset(self):
		self._transfer_direction = "out"

		self._speed_data = []
		self._current_speed = 0.0
		self._average_speed = 0.0

		self._network_usage_data = {}
		self._network_bandwidth = 0.0
		self._dynamic_bandwidth_limit = 0.0
		self._bandwidth_sleep_time = 0.0

	def _start_network_performance_counter(self):
		if self._network_performance_counter:
			self._stop_network_performance_counter()
		retry = 0
		exception = None
		from OPSI.System import (
			NetworkPerformanceCounter,
			getDefaultNetworkInterfaceName,
		)

		while retry > 5:
			try:
				self._network_performance_counter = NetworkPerformanceCounter(
					getDefaultNetworkInterfaceName()
				)
				break
			except Exception as err:
				exception = str(err)
				logger.debug(
					"Setting dynamic bandwidth failed, waiting 5 sec and trying again."
				)
				retry += 1
				time.sleep(5)

		if exception:
			logger.error(exception)
			logger.error("Failed to enable dynamic bandwidth: %s", exception)
			self._dynamic = False
			self._network_performance_counter = None

	def _stop_network_performance_counter(self):
		try:
			self._network_performance_counter.stop()
		except Exception as err:
			logger.warning("Failed to stop NetworkPerformanceCounter: %s", err)
		self._network_performance_counter = None

	def _get_network_usage(self):
		if not self._network_performance_counter:
			return 0.0
		try:
			if self._transfer_direction == "out":
				return self._network_performance_counter.getBytesOutPerSecond()
			return self._network_performance_counter.getBytesInPerSecond()
		except Exception as err:
			logger.warning("NetworkPerformanceCounter failing: %s", err)
			return 0.0

	def _calc_speed(self, num_bytes: int):
		now = time.time()
		max_age = 5

		speed_data = []
		total_bytes = 0
		for timestamp, byte_count in self._speed_data:
			if now - timestamp < max_age:
				speed_data.append((timestamp, byte_count))
				total_bytes += byte_count
		speed_data.append((now, num_bytes))

		self._speed_data = speed_data

		min_time = self._speed_data[0][0]
		max_time = self._speed_data[-1][0]
		if min_time == max_time:
			min_time -= 0.5
		if max_time - min_time != 0:
			self._average_speed = float(total_bytes) / (max_time - min_time)

		last_time = now - 0.5
		if len(self._speed_data) > 1:
			last_time = self._speed_data[-2][0]
		if now - last_time != 0:
			self._current_speed = float(num_bytes) / (now - last_time)

	def _get_dynamic_limit(self):
		total_network_usage = self._get_network_usage()
		logger.trace("Total network usage: %d bytes/s", total_network_usage)
		if total_network_usage <= 0:
			logger.trace("No network usage, no limit")
			self._dynamic_bandwidth_limit = 0.0
			return self._dynamic_bandwidth_limit

		now = time.time()

		# Add current usage (our part of the total nework usage) to usage data
		usage = min((float(self._average_speed) / float(total_network_usage)), 1.0)
		self._network_usage_data[now] = {"total": total_network_usage, "usage": usage}

		max_age = 5
		for timestamp in list(self._network_usage_data):
			if now - timestamp > max_age:
				del self._network_usage_data[timestamp]

		avg_total = statistics.mean(
			[val["total"] for val in self._network_usage_data.values()]
		)
		avg_usage = statistics.mean(
			[val["usage"] for val in self._network_usage_data.values()]
		)
		logger.trace(
			"Average usage: %0.1f%%, average total: %0.2fkByte/s, average speed: %0.2fkByte/s",
			avg_usage * 100,
			float(avg_total) / 1000,
			float(self._average_speed) / 1000,
		)

		if self._average_speed < 20_000:
			if self._dynamic_bandwidth_limit:
				logger.debug(
					"Average usage %0.1f%%, average total: %0.2fkByte/s, not limiting traffic because average speed is only %0.2fkByte/s",
					avg_usage * 100,
					float(avg_total) / 1000,
					float(self._average_speed) / 1000,
				)
				self._dynamic_bandwidth_limit = 0.0
			return self._dynamic_bandwidth_limit

		if avg_usage >= self._dynamic_bandwidth_threshold_no_limit:
			if self._dynamic_bandwidth_limit:
				logger.debug(
					"Average usage %0.1f%%, average total: %0.2fkByte/s, no other traffic detected, resetting dynamic limit (no limit)",
					avg_usage * 100,
					float(avg_total) / 1000,
				)
				self._dynamic_bandwidth_limit = 0.0
			return self._dynamic_bandwidth_limit

		if avg_usage <= self._dynamic_bandwidth_threshold_limit:
			limit = max(avg_total * self._dynamic_bandwidth_limit_rate, 20_000)
			if self._max_bandwidth and self._max_bandwidth < limit:
				logger.debug(
					"Not setting dynamic limit, which would be higher than the hard limit"
				)
			else:
				self._dynamic_bandwidth_limit = limit
				logger.debug(
					"Average usage %0.1f%%, average total: %0.2fkByte/s, other traffic detected, dynamically limiting bandwidth to %0.2fkByte/s",
					avg_usage * 100,
					float(avg_total) / 1000,
					float(self._dynamic_bandwidth_limit) / 1000,
				)

		return self._dynamic_bandwidth_limit

	def _limit(self, buffer_size: int) -> int:
		bwlimit = self._max_bandwidth

		if self._dynamic:
			# Dynamic limit
			bwlimit = self._get_dynamic_limit()
			if self._max_bandwidth:
				if bwlimit <= 0 or bwlimit > self._max_bandwidth:
					bwlimit = self._max_bandwidth

		if bwlimit <= 0:
			return self._max_buffer_size

		bwlimit = float(bwlimit)
		speed = float(self._current_speed)
		logger.trace(
			"Transfer speed %f kByte/s, limit: %f kByte/s, max: %f kByte/s, dynamic: %f kByte/s",
			speed / 1000,
			bwlimit / 1000,
			self._max_bandwidth / 1000,
			self._dynamic_bandwidth_limit / 1000,
		)
		if bwlimit > 0 and speed > 0:
			factor = 1.0
			if speed > bwlimit:
				# Too fast
				factor = float(speed) / float(bwlimit)
				logger.debug(
					"Transfer speed %0.2fkByte/s is to fast, limit: %0.2fkByte/s, factor: %0.5f",
					speed / 1000,
					bwlimit / 1000,
					factor,
				)

				if factor < 1.001:
					bandwidthSleepTime = self._bandwidth_sleep_time + (0.00007 * factor)
				elif factor < 1.01:
					bandwidthSleepTime = self._bandwidth_sleep_time + (0.0007 * factor)
				else:
					bandwidthSleepTime = self._bandwidth_sleep_time + (0.007 * factor)
				self._bandwidth_sleep_time = (
					bandwidthSleepTime + self._bandwidth_sleep_time
				) / 2
			else:
				# Too slow
				factor = float(bwlimit) / float(speed)
				logger.debug(
					"Transfer speed %0.2fkByte/s is to slow, limit: %0.2fkByte/s, factor: %0.5f",
					speed / 1000,
					bwlimit / 1000,
					factor,
				)

				if factor < 1.001:
					bandwidthSleepTime = self._bandwidth_sleep_time - (0.00006 * factor)
				elif factor < 1.01:
					bandwidthSleepTime = self._bandwidth_sleep_time - (0.0006 * factor)
				else:
					bandwidthSleepTime = self._bandwidth_sleep_time - (0.006 * factor)
				self._bandwidth_sleep_time = (
					bandwidthSleepTime + self._bandwidth_sleep_time
				) / 2

			if self._bandwidth_sleep_time <= 0.0:
				self._bandwidth_sleep_time = 0.000001

			if self._bandwidth_sleep_time <= 0.2:
				buffer_size = int(float(buffer_size) * 1.03)
			elif self._bandwidth_sleep_time > 0.3:
				buffer_size = int(float(buffer_size) / 1.1)
				self._bandwidth_sleep_time = 0.3

			if buffer_size > self._max_buffer_size:
				buffer_size = self._max_buffer_size
			elif buffer_size < self._min_buffer_size:
				buffer_size = self._min_buffer_size

			logger.debug(
				"Transfer speed %0.2fkByte/s, limit: %0.2fkByte/s, sleep time: %0.6f, buffer size: %d",
				speed / 1000,
				bwlimit / 1000,
				self._bandwidth_sleep_time,
				buffer_size,
			)
		else:
			self._bandwidth_sleep_time = 0.000001

		time.sleep(self._bandwidth_sleep_time)
		return buffer_size

	def set_bandwidth(self, max_bandwidth: int = 0, dynamic: bool = False):
		"""maxBandwidth in byte/s"""
		logger.info(
			"Setting bandwidth limits to: max=%f kByte/s, dynamic=%s",
			max_bandwidth / 1000,
			dynamic,
		)
		self._dynamic = forceBool(dynamic)
		self._max_bandwidth = max(forceInt(max_bandwidth), 0)

	def transfer_started(self, transfer_direction: str):
		self._transfer_direction = transfer_direction
		if self._dynamic:
			if not self._network_performance_counter:
				self._start_network_performance_counter()
		else:
			if self._network_performance_counter:
				self._stop_network_performance_counter()

	def transfer_ended(self):
		pass

	def suspend(self):
		if self._network_performance_counter:
			self._stop_network_performance_counter()
		self._reset()

	def limit(self, num_bytes_received: int):
		new_buffer_size = num_bytes_received
		self._calc_speed(num_bytes_received)
		if self._dynamic or self._max_bandwidth:
			new_buffer_size = self._limit(buffer_size=num_bytes_received)
		else:
			new_buffer_size = self._max_buffer_size
		return new_buffer_size


class Repository:
	DEFAULT_BUFFER_SIZE = 32 * 1000

	def __init__(self, url, **kwargs):
		"""
		maxBandwidth must be in byte/s
		"""
		self._url = forceUnicode(url)
		self._path = ""
		self._maxBandwidth = 0
		self._dynamicBandwidth = False

		self.bufferSize = self.DEFAULT_BUFFER_SIZE
		self._bytesTransfered = 0

		self._hooks = []
		self._transferDirection = None
		self.speed_limiter = SpeedLimiter()

		self.setBandwidth(
			dynamicBandwidth=kwargs.get("dynamicBandwidth", self._dynamicBandwidth),
			maxBandwidth=kwargs.get("maxBandwidth", self._maxBandwidth),
		)

	def setBandwidth(self, dynamicBandwidth, maxBandwidth):
		self._dynamicBandwidth = dynamicBandwidth
		self._maxBandwidth = maxBandwidth
		self.speed_limiter.set_bandwidth(
			max_bandwidth=self._maxBandwidth, dynamic=self._dynamicBandwidth
		)

	def setMaxBandwidth(self, maxBandwidth):
		self._maxBandwidth = maxBandwidth
		self.speed_limiter.set_bandwidth(
			max_bandwidth=self._maxBandwidth, dynamic=self._dynamicBandwidth
		)

	def setDynamicBandwidth(self, dynamicBandwidth):
		self._dynamicBandwidth = dynamicBandwidth
		self.speed_limiter.set_bandwidth(
			max_bandwidth=self._maxBandwidth, dynamic=self._dynamicBandwidth
		)

	def __str__(self):
		return f"<{self.__class__.__name__}({self._url})>"

	def __repr__(self):
		return self.__str__()

	def addHook(self, hook):
		if not isinstance(hook, RepositoryHook):
			raise ValueError(f"Not a RepositoryHook: {hook}")

		if hook not in self._hooks:
			self._hooks.append(hook)

	def removeHook(self, hook):
		if not isinstance(hook, RepositoryHook):
			raise ValueError(f"Not a RepositoryHook: {hook}")

		try:
			self._hooks.remove(hook)
		except ValueError:  # element not in list
			pass

	def _transferDown(self, src, dst, size, progressSubject=None):
		return self._transfer("in", src, dst, size, progressSubject)

	def _transferUp(self, src, dst, size, progressSubject=None):
		return self._transfer("out", src, dst, size, progressSubject)

	def _transfer(self, transferDirection, src, dst, size, progressSubject=None):
		logger.debug(
			"Transfer %s from %s to %s (size=%s, dynamic bandwidth=%s, max bandwidth=%s)",
			transferDirection,
			src,
			dst,
			size,
			self._dynamicBandwidth,
			self._maxBandwidth,
		)
		try:
			self.speed_limiter.transfer_started(transfer_direction=transferDirection)
			self._transferDirection = transferDirection
			self._bytesTransfered = 0
			transferStartTime = time.time()
			buf = True

			while buf and self._bytesTransfered < size:
				remainingBytes = size - self._bytesTransfered
				logger.trace(
					"self.bufferSize: %d, self._bytesTransfered: %d, size: %d, remainingBytes: %d, dynamic bandwidth=%s, max bandwidth=%s",
					self.bufferSize,
					self._bytesTransfered,
					size,
					remainingBytes,
					self._dynamicBandwidth,
					self._maxBandwidth,
				)

				if 0 < remainingBytes < self.bufferSize:
					buf = src.read(remainingBytes)
				elif remainingBytes > 0:
					buf = src.read(self.bufferSize)
				else:
					break

				read = len(buf)

				if read > 0:
					if (self._bytesTransfered + read) > size >= 0:
						buf = buf[: size - self._bytesTransfered]
						read = len(buf)
					self._bytesTransfered += read

					if hasattr(dst, "send"):
						dst.send(buf)
					else:
						dst.write(buf)

					if progressSubject:
						progressSubject.addToState(read)

					self.bufferSize = self.speed_limiter.limit(read)

			transferTime = time.time() - transferStartTime
			if transferTime == 0:
				transferTime = 0.0000001
			self.speed_limiter.transfer_ended()
			logger.info(
				"Transfered %0.2fkByte in %0.2f minutes, average speed was %0.2fkByte/s",
				float(self._bytesTransfered) / 1000,
				float(transferTime) / 60,
				(float(self._bytesTransfered) / transferTime) / 1000,
			)
			return self._bytesTransfered
		except Exception as error:
			logger.info(error, exc_info=True)
			raise

	def _preProcessPath(self, path):
		return path

	def content(self, source="", recursive=False):
		"""
		List the content of the repository.

		The returned entries are a dict with the following keys:
		`name`, `size`, `path` and `type`.
		`name` is the name of file or folder.
		`path` is the relative path.
		`type` is either 'file' or 'dir'.

		:param recursive: Recursive listing?
		:type recursive: bool
		:returns: Content of the repository.
		:rtype: [dict, ]
		"""
		raise RepositoryError("Not implemented")

	def listdir(self, source=""):
		return [item["name"] for item in self.content(source, recursive=False)]

	def getCountAndSize(self, source=""):
		source = forceUnicode(source)
		count = 0
		size = 0
		for entry in self.content(source, recursive=True):
			if entry.get("type", "") == "file":
				count += 1
				size += entry.get("size", 0)

		return (count, size)

	def fileInfo(self, source):
		source = forceUnicode(source)
		info = {}
		try:
			parts = source.split("/")
			dirname = "/".join(parts[:-1])
			filename = parts[-1]
			if not filename:
				return {
					"name": dirname.split("/")[:-1],
					"path": dirname.split("/")[:-1],
					"type": "dir",
					"size": 0,
				}

			for item in self.content(dirname):
				if item["name"] == filename:
					info = item
					return info
			raise IOError("File not found")
		except Exception as err:
			raise RepositoryError(
				f"Failed to get file info for '{source}': {err}"
			) from err

	def exists(self, source):
		try:
			self.fileInfo(source)
		except Exception:
			return False

		return True

	def islink(self, source):
		return False

	def isfile(self, source):
		try:
			info = self.fileInfo(source)
			return info.get("type", "") == "file"
		except Exception:
			return False

	def isdir(self, source):
		try:
			info = self.fileInfo(source)
			return info.get("type", "") == "dir"
		except Exception:
			return False

	def copy(
		self,
		source,
		destination,
		overallProgressSubject=None,
		currentProgressSubject=None,
	):
		"""
		source = file,  destination = file              => overwrite destination
		source = file,  destination = dir               => copy into destination
		source = file,  destination = not existent      => create destination directories, copy source to destination
		source = dir,   destination = file              => error
		source = dir,   destination = dir               => copy source dir into destination
		source = dir,   destination = not existent      => create destination, copy content of source into destination
		source = dir/*, destination = dir/not existent  => create destination if not exists, copy content of source into destination
		"""
		for hook in self._hooks:
			(source, destination, overallProgressSubject, currentProgressSubject) = (
				hook.pre_Repository_copy(
					source, destination, overallProgressSubject, currentProgressSubject
				)
			)

		try:
			source = forceFilename(source)
			destination = forceFilename(destination)

			copySrcContent = False

			if source.endswith(("/*.*", "\\*.*")):
				source = source[:-4]
				copySrcContent = True

			elif source.endswith(("/*", "\\*")):
				source = source[:-2]
				copySrcContent = True

			if copySrcContent and not self.isdir(source):
				raise IOError(f"Source directory '{source}' not found")

			logger.info("Copying from '%s' to '%s'", source, destination)

			totalFiles = 0
			size = 0
			info = self.fileInfo(source)

			if overallProgressSubject:
				overallProgressSubject.reset()
				if info.get("type") == "file":
					(totalFiles, size) = (1, info["size"])
				else:
					(totalFiles, size) = self.getCountAndSize(source)
				overallProgressSubject.setEnd(size)

			if info.get("type") == "file":
				destinationFile = destination
				if not os.path.exists(destination):
					parent = os.path.dirname(destination)
					if not os.path.exists(parent):
						os.makedirs(parent)
				elif os.path.isdir(destination):
					destinationFile = os.path.join(destination, info["name"])

				if overallProgressSubject:
					sizeString = f"{info['size']} Byte"
					if info["size"] > 1000 * 1000:
						sizeString = f"{float(info['size']) / (1000 * 1000):0.2f} MByte"
					elif info["size"] > 1000:
						sizeString = f"{float(info['size']) / 1000:0.2f} kByte"
					overallProgressSubject.setMessage(
						f"[1/1] {info['name']} ({sizeString})"
					)

				try:
					self.download(source, destinationFile, currentProgressSubject)
				except OSError as error:
					if error.errno != 1:
						raise
					# Operation not permitted
					logger.debug(error)

				if overallProgressSubject:
					overallProgressSubject.addToState(info["size"])

			elif info.get("type") == "dir":
				if not os.path.exists(destination):
					os.makedirs(destination)
				elif os.path.isfile(destination):
					raise IOError(
						f"Cannot copy directory '{source}' into file '{destination}'"
					)
				elif os.path.isdir(destination):
					if not copySrcContent:
						destination = os.path.join(destination, info["name"])
				content = self.content(source, recursive=True)
				fileCount = 0
				for item in content:
					if item.get("type") == "dir":
						path = [destination]
						path.extend(item["path"].split("/"))
						targetDir = os.path.join(*path)
						if not targetDir:
							raise RuntimeError(f"Bad target directory '{targetDir}'")
						if not os.path.isdir(targetDir):
							os.makedirs(targetDir)
					elif item.get("type") == "file":
						fileCount += 1
						if overallProgressSubject:
							countLen = len(str(totalFiles))
							countLenFormat = "%" + str(countLen) + "s"
							sizeString = f"{item['size']:0.0f} Byte"
							if item["size"] > 1000 * 1000:
								sizeString = (
									f"{float(item['size']) / (1000 * 1000):0.2f} MByte"
								)
							elif item["size"] > 1000:
								sizeString = f"{float(item['size']) / 1000:0.2f} kByte"

							overallProgressSubject.setMessage(
								"[%s/%s] %s (%s)"
								% (
									countLenFormat % fileCount,
									totalFiles,
									item["name"],
									sizeString,
								)
							)
						path = [destination]
						path.extend(item["path"].split("/")[:-1])
						targetDir = os.path.join(*path)
						if not targetDir:
							raise RuntimeError(f"Bad target directory '{targetDir}'")
						if targetDir and not os.path.isdir(targetDir):
							os.makedirs(targetDir)
						self.download(
							"/".join((source, item["path"])),
							os.path.join(targetDir, item["name"]),
							currentProgressSubject,
						)

						if overallProgressSubject:
							overallProgressSubject.addToState(item["size"])
			else:
				raise RuntimeError(f"Failed to copy: unknown source type '{source}'")
			logger.info("Copy done")
			if overallProgressSubject:
				overallProgressSubject.setState(size)
		except Exception as error:
			for hook in self._hooks:
				hook.error_Repository_copy(
					source,
					destination,
					overallProgressSubject,
					currentProgressSubject,
					error,
				)
			raise error

		for hook in self._hooks:
			hook.post_Repository_copy(
				source, destination, overallProgressSubject, currentProgressSubject
			)

	def upload(self, source, destination, progressSubject=None):
		raise RepositoryError("Not implemented")

	def download(
		self,
		source,
		destination,
		progressSubject=None,
		startByteNumber=-1,
		endByteNumber=-1,
	):
		raise RepositoryError("Not implemented")

	def delete(self, destination):
		raise RepositoryError("Not implemented")

	def makeDirectory(self, destination):
		raise RepositoryError("Not implemented")

	def disconnect(self):
		self.speed_limiter.suspend()

	def __del__(self):
		try:
			self.disconnect()
		except Exception:
			pass


class FileRepository(Repository):
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)

		match = re.search(r"^file://(/[^/]+.*)$", self._url, re.IGNORECASE)
		if not match:
			raise RepositoryError(f"Bad file url: '{self._url}'")
		self._path = match.group(1)

	def _preProcessPath(self, path):
		path = forceUnicode(path)
		if path.startswith("/"):
			path = path[1:]
		if path.endswith("/"):
			path = path[:-1]
		path = self._path + "/" + path
		if os.name == "nt":
			path = path.replace("/", "\\")

		return path

	def fileInfo(self, source):
		source = self._preProcessPath(source)
		try:
			if not os.path.exists(source):
				raise IOError("File not found")

			info = {
				"name": os.path.basename(source),
				"path": source[len(self._path) + 1 :],
				"type": "file",
				"size": 0,
			}
			if os.path.isdir(source):
				info["type"] = "dir"
			if os.path.isfile(source):
				info["size"] = os.path.getsize(source)
			return info
		except Exception as err:
			raise RepositoryError(
				f"Failed to get file info for '{source}': {err}"
			) from err

	def exists(self, source):
		return os.path.exists(self._preProcessPath(source))

	def islink(self, source):
		return os.path.islink(self._preProcessPath(source))

	def isfile(self, source):
		return os.path.isfile(self._preProcessPath(source))

	def isdir(self, source):
		return os.path.isdir(self._preProcessPath(source))

	def content(self, source="", recursive=False):
		source = self._preProcessPath(source)
		srcLen = len(source)
		content = []

		def _recurse(path, content):
			path = os.path.abspath(forceFilename(path))
			for entry in os.listdir(path):
				try:
					info = {"name": entry, "size": 0, "type": "file"}

					entry = os.path.join(path, entry)
					info["path"] = entry[srcLen:]
					if os.path.islink(entry) and not os.path.isdir(entry):
						pass
					elif os.path.isfile(entry):
						info["size"] = os.path.getsize(entry)
						content.append(info)
					elif os.path.isdir(entry):
						info["type"] = "dir"
						content.append(info)
						if recursive:
							_recurse(path=entry, content=content)
				except Exception as err:
					logger.error(err)

			return content

		return _recurse(path=source, content=content)

	def download(
		self,
		source,
		destination,
		progressSubject=None,
		startByteNumber=-1,
		endByteNumber=-1,
	):
		"""
		startByteNumber: position of first byte to be read
		endByteNumber:   position of last byte to be read
		"""
		size = self.fileInfo(source)["size"]
		source = self._preProcessPath(source)
		destination = forceUnicode(destination)
		startByteNumber = forceInt(startByteNumber)
		endByteNumber = forceInt(endByteNumber)

		if endByteNumber > -1:
			size = endByteNumber + 1
		if startByteNumber > -1:
			size -= startByteNumber

		logger.debug("Length of binary data to download: %d bytes", size)

		if progressSubject:
			progressSubject.setEnd(size)

		try:
			with open(source, "rb") as src:
				if startByteNumber > -1:
					src.seek(startByteNumber)
				with open(destination, "wb") as dst:
					self._transferDown(src, dst, size, progressSubject)
		except Exception as err:
			raise RepositoryError(
				f"Failed to download '{source}' to '{destination}': {err}"
			) from err

	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)

		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug("Length of binary data to upload: %d", size)

		if progressSubject:
			progressSubject.setEnd(size)

		try:
			with open(source, "rb") as src:
				with open(destination, "wb") as dst:
					self._transferUp(src, dst, size, progressSubject)
		except Exception as err:
			raise RepositoryError(
				f"Failed to upload '{source}' to '{destination}': {err}"
			) from err

	def delete(self, destination):
		destination = self._preProcessPath(destination)
		os.unlink(destination)

	def makeDirectory(self, destination):
		destination = self._preProcessPath(destination)
		if not os.path.isdir(destination):
			os.mkdir(destination)


class TimeoutHTTPAdapter(HTTPAdapter):
	def __init__(self, *args, **kwargs):
		self.timeout = None
		if "timeout" in kwargs:
			self.timeout = kwargs["timeout"]
			del kwargs["timeout"]
		super().__init__(*args, **kwargs)

	def send(
		self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
	):
		if timeout is None:
			timeout = self.timeout
		return super().send(request, stream, timeout, verify, cert, proxies)


class HTTPRepository(Repository):
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)

		self._application = f"opsi-http-repository/{__version__}"
		self._ca_cert_file = None
		self._verify_server_cert = False
		self._proxy_url = "system"  # Use system proxy by default
		self._username = None
		self._password = None
		self._ip_version = "auto"
		self._connect_timeout = 10
		self._read_timeout = 3600
		self._http_pool_maxsize = 10
		self._http_max_retries = 1
		self._session_lifetime = 150
		self.base_url = None

		for option, value in kwargs.items():
			option = option.lower().replace("_", "")
			if option == "application":
				self._application = str(value)
			elif option == "username":
				self._username = str(value or "")
			elif option == "password":
				self._password = str(value or "")
			elif option == "connecttimeout" and value not in (None, ""):
				self._connect_timeout = int(value)
			elif option in (
				"readtimeout",
				"timeout",
				"sockettimeout",
			) and value not in (None, ""):
				self._read_timeout = int(value)
			elif option == "verifyservercert":
				self._verify_server_cert = bool(value)
			elif option == "cacertfile" and value not in (None, ""):
				self._ca_cert_file = str(value)
			elif option == "proxyurl":
				self._proxy_url = str(value) if value else None
			elif option == "ipversion" and value not in (None, ""):
				if str(value) in ("auto", "4", "6"):
					self._ip_version = str(value)
				else:
					logger.error(
						"Invalid ip version '%s', using %s", value, self._ip_version
					)
			elif option == "sessionlifetime" and value:
				self._session_lifetime = int(value)

		self._set_url(url)

		if self._password:
			secret_filter.add_secrets(self._password)

		self._session = requests.Session()
		self._session.auth = (self._username or "", self._password or "")
		self._session.headers.update(
			{
				"User-Agent": self._application,
				"X-opsi-session-lifetime": str(self._session_lifetime),
			}
		)

		no_proxy_addresses = ["localhost", "127.0.0.1", "ip6-localhost", "::1"]
		self._session = prepare_proxy_environment(
			url,
			self._proxy_url,
			no_proxy_addresses=no_proxy_addresses,
			session=self._session,
		)

		if self._verify_server_cert:
			self._session.verify = self._ca_cert_file or True
		else:
			self._session.verify = False

		self._http_adapter = TimeoutHTTPAdapter(
			timeout=(self._connect_timeout, self._read_timeout),
			pool_maxsize=self._http_pool_maxsize,
			max_retries=self._http_max_retries,
		)
		self._session.mount("http://", self._http_adapter)
		self._session.mount("https://", self._http_adapter)

		try:
			address = ipaddress.ip_address(self.hostname)
			if isinstance(address, ipaddress.IPv6Address) and self._ip_version != "6":
				logger.info("%s is an ipv6 address, forcing ipv6", self.hostname)
				self._ip_version = 6
			elif isinstance(address, ipaddress.IPv4Address) and self._ip_version != "4":
				logger.info("%s is an ipv4 address, forcing ipv4", self.hostname)
				self._ip_version = 4
		except ValueError:
			pass

		urllib3.util.connection.allowed_gai_family = self._allowed_gai_family

	@property
	def hostname(self):
		return urlparse(self.base_url).hostname

	def _allowed_gai_family(self):
		"""This function is designed to work in the context of
		getaddrinfo, where family=socket.AF_UNSPEC is the default and
		will perform a DNS search for both IPv6 and IPv4 records."""
		# https://github.com/urllib3/urllib3/blob/main/src/urllib3/util/connection.py

		logger.debug("Using ip version %s", self._ip_version)
		if self._ip_version == "4":
			return socket.AF_INET
		if self._ip_version == "6":
			return socket.AF_INET6
		if urllib3.util.connection.HAS_IPV6:
			return socket.AF_UNSPEC
		return socket.AF_INET

	def _set_url(self, url):
		url_str = str(url)
		url = urlparse(url_str)
		if url.scheme not in ("http", "https", "webdav", "webdavs"):
			raise ValueError(f"Protocol {url.scheme} not supported")
		if not url.hostname:
			raise ValueError(f"Invalid url '{url_str}', hostname missing")

		self._path = url.path

		scheme = "https" if url.scheme.endswith("s") else "http"

		port = url.port
		if not port:
			port = 80 if scheme == "http" else 443

		hostname = str(url.hostname)
		if ":" in hostname:
			hostname = f"[{hostname}]"

		self.base_url = f"{scheme}://{hostname}:{port}{url.path.rstrip('/')}"
		if url.username and not self._username:
			self._username = url.username
		if url.password and not self._password:
			self._password = url.password

	def _preProcessPath(self, path):
		path = "/" + forceUnicode(path).lstrip("/").rstrip("/")
		return quote(path.encode("utf-8"))

	def download(
		self,
		source,
		destination,
		progressSubject=None,
		startByteNumber=-1,
		endByteNumber=-1,
	):
		"""
		startByteNumber: position of first byte to be read
		endByteNumber:   position of last byte to be read
		"""
		destination = forceUnicode(destination)
		startByteNumber = forceInt(startByteNumber)
		endByteNumber = forceInt(endByteNumber)
		source = self._preProcessPath(source)
		source_url = self.base_url.rstrip("/") + source

		try:
			headers = {}
			if startByteNumber > -1 or endByteNumber > -1:
				sbn = startByteNumber
				ebn = endByteNumber
				if sbn <= -1:
					sbn = 0
				if ebn <= -1:
					ebn = ""
				headers["range"] = f"bytes={sbn}-{ebn}"

			response = self._session.get(source_url, headers=headers, stream=True)
			if response.status_code not in (
				requests.codes["ok"],
				requests.codes["partial_content"],
			):
				raise RuntimeError(f"{response.status_code} - {response.text}")

			size = int(response.headers.get("content-length", 0))
			logger.debug("Length of binary data to download: %d bytes", size)

			if progressSubject:
				progressSubject.setEnd(size)

			with open(destination, "wb") as dst:
				# Do not decompress files, otherwise files stored compressed on the
				# server side will be stored uncompressed on the client side.
				response.raw.decode_content = False
				self._transferDown(response.raw, dst, size, progressSubject)

		except Exception as err:
			logger.error(err, exc_info=True)
			raise RepositoryError(
				f"Failed to download '{source}' to '{destination}': {err}"
			) from err
		logger.trace("HTTP download done")

	def disconnect(self):
		Repository.disconnect(self)
		if self._session:
			try:
				self._session.close()
			except Exception:
				pass


class FileProgessWrapper:
	def __init__(self, file, repository: Repository, progress_subject):
		self.file = file
		self.repository = repository
		self.progress_subject = progress_subject

	def read(self, size):
		# Read buffer_size to speed up transfer
		data = self.file.read(self.repository.bufferSize)
		if self.progress_subject:
			self.progress_subject.addToState(len(data))
		self.repository.bufferSize = self.repository.speed_limiter.limit(len(data))
		return data


class WebDAVRepository(HTTPRepository):
	def __init__(self, url, **kwargs):
		HTTPRepository.__init__(self, url, **kwargs)

		self._application = f"opsi-webdav-repository/{__version__}"

		parts = self._url.split("/")
		if len(parts) < 3 or parts[0].lower() not in ("webdav:", "webdavs:"):
			raise RepositoryError(f"Bad webdav url: '{self._url}'")
		self._contentCache = {}

	def content(self, source="", recursive=False):
		source = "/" + source.lstrip("/")
		source_url = self.base_url.rstrip("/") + self._preProcessPath(source)
		source_url = source_url.rstrip("/") + "/"

		if recursive and source in self._contentCache:
			if time.time() - self._contentCache[source]["time"] > 60:
				del self._contentCache[source]
			else:
				return self._contentCache[source]["content"]

		headers = {}
		depth = "1"
		if recursive:
			depth = "infinity"
		headers["depth"] = depth

		response = self._session.request("PROPFIND", url=source_url, headers=headers)
		if response.status_code != requests.codes["multi_status"]:
			raise RepositoryError(
				f"Failed to list dir '{source}': {response.status_code} - {response.text}"
			)

		encoding = "utf-8"
		contentType = response.headers.get("content-type", "").lower()
		for part in contentType.split(";"):
			if "charset=" in part:
				encoding = part.split("=")[1].replace('"', "").strip()

		davxmldata = response.content
		logger.trace("davxmldata: %s", davxmldata)

		content = []
		for entry in getFileInfosFromDavXML(davxmldata=davxmldata, encoding=encoding):
			if entry["path"].startswith("/"):
				# Absolut path to realtive path
				entry["path"] = posixpath.relpath(
					entry["path"], start=self._path + source
				)
			if entry["path"] and entry["path"] not in (".", ".."):
				content.append(entry)
		logger.debug("fileinfo: %s", content)

		if recursive:
			self._contentCache[source] = {"time": time.time(), "content": content}

		return content

	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)
		destination_url = self.base_url.rstrip("/") + destination
		self._contentCache = {}

		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug("Length of binary data to upload: %d", size)

		if progressSubject:
			progressSubject.setEnd(size)

		try:
			headers = {"content-length": str(size)}
			with open(source, "rb") as src:
				self.speed_limiter.transfer_started("out")
				fpw = FileProgessWrapper(src, self, progressSubject)
				response = self._session.put(
					url=destination_url, headers=headers, data=fpw
				)
				self.speed_limiter.transfer_ended()
				if response.status_code not in (
					requests.codes["created"],
					requests.codes["no_content"],
				):
					raise RuntimeError(f"{response.status_code} - {response.text}")
		except Exception as err:
			logger.error(err, exc_info=True)
			raise RepositoryError(
				f"Failed to upload '{source}' to '{destination}': {err}"
			) from err
		logger.trace("WebDAV upload done")

	def delete(self, destination):
		destination = self._preProcessPath(destination)
		destination_url = self.base_url.rstrip("/") + destination
		response = self._session.delete(url=destination_url)
		if response.status_code != requests.codes["no_content"]:
			raise RepositoryError(
				f"Failed to delete '{destination}': {response.status_code}"
			)


class CIFSRepository(FileRepository):
	def __init__(self, url, **kwargs):
		Repository.__init__(self, url, **kwargs)

		match = re.search(r"^(smb|cifs)://([^/]+/.+)$", self._url, re.IGNORECASE)
		if not match:
			raise RepositoryError(f"Bad smb/cifs url: '{self._url}'")

		if os.name not in ("posix", "nt"):
			raise NotImplementedError(
				f"CIFSRepository not yet avaliable on os '{os.name}'"
			)

		self._mountShare = forceBool(kwargs.get("mount", True))
		self._mounted = False
		self._mountPointCreated = False

		self._mountPoint = kwargs.get("mountPoint")
		if not self._mountPoint:
			if os.name == "posix":
				self._mountPoint = f"/tmp/.cifs-mount.{randomString(5)}"
			elif os.name == "nt":
				self._mountPoint = getFreeDrive(startLetter="g")

		self._username = forceUnicode(kwargs.get("username", "guest"))
		self._password = forceUnicode(kwargs.get("password", ""))
		if self._password:
			secret_filter.add_secrets(self._password)

		self._mountOptions = kwargs.get("mountOptions", {})

		if self._mountShare:
			self._path = self._mountPoint
		parts = match.group(2).split("/")
		if len(parts) > 2:
			self._path += "/" + "/".join(parts[2:])
		if self._path.endswith("/"):
			self._path = self._path[:-1]
		if self._mountShare:
			self._mount()
		else:
			parts = self._url.split("/")
			self._path = (
				"\\\\" + parts[2] + "\\" + parts[3] + self._path.replace("/", "\\")
			)

	def getMountPoint(self):
		return self._mountPoint

	def _mount(self):
		if self._mounted:
			self._umount()
		if not self._mountPoint:
			raise ValueError("Mount point not defined")
		logger.info("Mountpoint: %s ", self._mountPoint)
		logger.info("Mounting '%s' to '%s'", self._url, self._mountPoint)
		if os.name == "posix" and not os.path.isdir(self._mountPoint):
			os.makedirs(self._mountPoint)
			self._mountPointCreated = True

		try:
			mountOptions = self._mountOptions
			mountOptions["username"] = self._username
			mountOptions["password"] = self._password
			mount(self._url, self._mountPoint, **mountOptions)
			self._mounted = True
		except Exception as mountError:
			if self._mountPointCreated:
				try:
					os.rmdir(self._mountPoint)
				except Exception as err:
					logger.error(err)
			raise mountError

	def _umount(self):
		if not self._mounted or not self._mountPoint:
			return

		logger.info("Umounting '%s' from '%s'", self._url, self._mountPoint)

		umount(self._mountPoint)

		self._mounted = False
		if self._mountPointCreated:
			os.rmdir(self._mountPoint)

	def disconnect(self):
		FileRepository.disconnect(self)
		self._umount()


class DepotToLocalDirectorySychronizer:
	def __init__(
		self,
		sourceDepot,
		destinationDirectory,
		productIds=None,
		maxBandwidth=0,
		dynamicBandwidth=False,
	):
		productIds = productIds or []
		self._sourceDepot = sourceDepot
		self._destinationDirectory = forceUnicode(destinationDirectory)
		self._productIds = forceUnicodeList(productIds)
		self._productId = None
		self._linkFiles = {}
		self._fileInfo = None
		if not os.path.isdir(self._destinationDirectory):
			os.mkdir(self._destinationDirectory)
		self._sourceDepot.setBandwidth(
			dynamicBandwidth=dynamicBandwidth, maxBandwidth=maxBandwidth
		)

	def _synchronizeDirectories(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = forceUnicode(destination)
		logger.debug("Syncing directory %s to %s", source, destination)
		if not os.path.isdir(destination):
			if os.path.exists(destination):
				os.remove(destination)
			os.mkdir(destination)

		# Local directory cleanup
		for item in os.listdir(destination):
			relSource = (source + "/" + item).split("/", 1)[1]
			if relSource == self._productId + ".files":
				continue
			if relSource in self._fileInfo:
				continue

			path = os.path.join(destination, item)
			logger.info("Deleting '%s'", relSource)
			if os.path.isdir(path) and not os.path.islink(path):
				shutil.rmtree(path)
			else:
				os.remove(path)

		# Start sync
		for item in self._sourceDepot.content(source):
			source = forceUnicode(source)
			sourcePath = source + "/" + item["name"]
			destinationPath = os.path.join(destination, item["name"])
			relSource = sourcePath.split("/", 1)[1]
			if relSource == self._productId + ".files":
				continue
			if relSource not in self._fileInfo:
				continue
			if self._fileInfo[relSource]["type"] == "d":
				self._synchronizeDirectories(
					sourcePath, destinationPath, progressSubject
				)
			else:
				logger.debug(
					"Syncing %s with %s %s",
					relSource,
					destinationPath,
					self._fileInfo[relSource],
				)
				if self._fileInfo[relSource]["type"] == "l":
					self._linkFiles[relSource] = self._fileInfo[relSource]["target"]
					continue
				size = 0
				localSize = 0
				exists = False
				if self._fileInfo[relSource]["type"] == "f":
					size = int(self._fileInfo[relSource]["size"])
					exists = os.path.exists(destinationPath)
					if exists and os.path.isdir(destinationPath):
						shutil.rmtree(destinationPath)
						exists = False
					if exists:
						md5s = md5sum(destinationPath)
						logger.debug(
							"Destination file '%s' already exists (size: %s, md5sum: %s)",
							destinationPath,
							size,
							md5s,
						)
						localSize = os.path.getsize(destinationPath)
						if (
							localSize == size
							and md5s == self._fileInfo[relSource]["md5sum"]
						):
							continue

				if progressSubject:
					progressSubject.setMessage(
						_("Downloading file '%s'") % item["name"]
					)

				partialEndFile = f"{destinationPath}.opsi_sync_endpart"
				partialStartFile = f"{destinationPath}.opsi_sync_startpart"

				composed = False
				if exists and (localSize < size):
					try:
						# First byte needed is byte number <localSize>
						logger.info(
							"Downloading file '%s' starting at byte number %d",
							item["name"],
							localSize,
						)
						if os.path.exists(partialEndFile):
							os.remove(partialEndFile)
						self._sourceDepot.download(
							sourcePath, partialEndFile, startByteNumber=localSize
						)

						with open(destinationPath, "ab") as f1:
							with open(partialEndFile, "rb") as f2:
								shutil.copyfileobj(f2, f1)

						md5s = md5sum(destinationPath)
						if md5s != self._fileInfo[relSource]["md5sum"]:
							logger.info(
								"MD5sum of composed file differs after downloading end part"
							)
							if os.path.exists(partialStartFile):
								os.remove(partialStartFile)
							# Last byte needed is byte number <localSize> - 1
							logger.info(
								"Downloading file '%s' ending at byte number %d",
								item["name"],
								localSize - 1,
							)
							self._sourceDepot.download(
								sourcePath,
								partialStartFile,
								endByteNumber=localSize - 1,
							)

							with open(partialStartFile, "ab") as f1:
								with open(partialEndFile, "rb") as f2:
									shutil.copyfileobj(f2, f1)

							if os.path.exists(destinationPath):
								os.remove(destinationPath)
							os.rename(partialStartFile, destinationPath)
							md5s = md5sum(destinationPath)
							if md5s != self._fileInfo[relSource]["md5sum"]:
								logger.info(
									"MD5sum of composed file differs after downloading start part"
								)
								raise RuntimeError("MD5sum differs")
						composed = True
					except Exception as err:
						logger.warning(
							"Error completing a partially downloaded file '%s': %s",
							item["name"],
							err,
							exc_info=True,
						)

				for fn in (partialEndFile, partialStartFile):
					if os.path.exists(fn):
						os.remove(fn)

				if not composed:
					if os.path.exists(destinationPath):
						os.remove(destinationPath)
					logger.info("Downloading file '%s'", item["name"])
					self._sourceDepot.download(
						sourcePath, destinationPath, progressSubject=progressSubject
					)

				md5s = md5sum(destinationPath)
				if md5s != self._fileInfo[relSource]["md5sum"]:
					error = (
						f"Failed to download '{item['name']}': "
						f"MD5sum mismatch (local:{md5s} != remote:{self._fileInfo[relSource]['md5sum']})"
					)
					logger.error(error)
					raise RuntimeError(error)

	def synchronize(self, productProgressObserver=None, overallProgressObserver=None):
		if not self._productIds:
			logger.info("Getting product dirs of depot '%s'", self._sourceDepot)
			for item in self._sourceDepot.content():
				self._productIds.append(item["name"])

		overallProgressSubject = ProgressSubject(
			id="sync_products_overall",
			type="product_sync",
			end=len(self._productIds),
			fireAlways=True,
		)
		overallProgressSubject.setMessage(_("Synchronizing products"))
		if overallProgressObserver:
			overallProgressSubject.attachObserver(overallProgressObserver)

		for self._productId in self._productIds:
			productProgressSubject = ProgressSubject(
				id="sync_product_" + self._productId,
				type="product_sync",
				fireAlways=True,
			)
			productProgressSubject.setMessage(
				_("Synchronizing product %s") % self._productId
			)
			if productProgressObserver:
				productProgressSubject.attachObserver(productProgressObserver)
			packageContentFile = None

			try:
				self._linkFiles = {}
				logger.notice(
					"Syncing product %s of depot %s with local directory %s",
					self._productId,
					self._sourceDepot,
					self._destinationDirectory,
				)

				productDestinationDirectory = os.path.join(
					self._destinationDirectory, self._productId
				)
				if not os.path.isdir(productDestinationDirectory):
					os.mkdir(productDestinationDirectory)

				logger.info("Downloading package content file")
				packageContentFile = os.path.join(
					productDestinationDirectory, f"{self._productId}.files"
				)
				self._sourceDepot.download(
					f"{self._productId}/{self._productId}.files", packageContentFile
				)
				self._fileInfo = PackageContentFile(packageContentFile).parse()

				size = 0
				for value in self._fileInfo.values():
					try:
						size += int(value["size"])
					except KeyError:
						pass

				productProgressSubject.setMessage(
					_("Synchronizing product %s (%.2fkByte)")
					% (self._productId, (size / 1000))
				)
				productProgressSubject.setEnd(size)
				productProgressSubject.setEndChangable(False)

				self._synchronizeDirectories(
					self._productId, productDestinationDirectory, productProgressSubject
				)

				links = list(self._linkFiles.keys())
				links.sort()
				for linkDestination in links:
					linkSource = self._linkFiles[linkDestination]

					with cd(productDestinationDirectory):
						if os.name == "nt":
							if linkSource.startswith("/"):
								linkSource = linkSource[1:]
							if linkDestination.startswith("/"):
								linkDestination = linkDestination[1:]
							linkSource = os.path.join(
								productDestinationDirectory,
								linkSource.replace("/", "\\"),
							)
							linkDestination = os.path.join(
								productDestinationDirectory,
								linkDestination.replace("/", "\\"),
							)
							if os.path.exists(linkDestination):
								if os.path.isdir(linkDestination):
									shutil.rmtree(linkDestination)
								else:
									os.remove(linkDestination)
							logger.info(
								"Symlink => copying '%s' to '%s'",
								linkSource,
								linkDestination,
							)
							if os.path.isdir(linkSource):
								shutil.copytree(linkSource, linkDestination)
							else:
								shutil.copyfile(linkSource, linkDestination)
						else:
							if os.path.exists(linkDestination):
								if os.path.isdir(
									linkDestination
								) and not os.path.islink(linkDestination):
									shutil.rmtree(linkDestination)
								else:
									os.remove(linkDestination)
							parts = len(linkDestination.split("/"))
							parts -= len(linkSource.split("/"))
							for _counter in range(parts):
								linkSource = os.path.join("..", linkSource)
							logger.info(
								"Symlink '%s' to '%s'", linkDestination, linkSource
							)
							os.symlink(linkSource, linkDestination)
			except Exception as error:
				productProgressSubject.setMessage(
					_("Failed to sync product %s: %s") % (self._productId, error)
				)
				if packageContentFile and os.path.exists(packageContentFile):
					os.unlink(packageContentFile)
				raise

			if overallProgressSubject:
				overallProgressSubject.addToState(1)

			if productProgressObserver:
				productProgressSubject.detachObserver(productProgressObserver)

		if overallProgressObserver:
			overallProgressSubject.detachObserver(overallProgressObserver)
