# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the work with repositories.
"""

import json
import os
import pathlib
import shutil
import time
from unittest import mock

import pytest
from opsicommon.testing.helpers import http_test_server

from OPSI.Exceptions import RepositoryError
from OPSI.Util import findFilesGenerator, md5sum
from OPSI.Util.File.Opsi import PackageContentFile
from OPSI.Util.Repository import (
	DepotToLocalDirectorySychronizer,
	FileRepository,
	getFileInfosFromDavXML,
	getRepository,
)


def testGettingFileRepository():
	repo = getRepository("file:///not-here")
	assert isinstance(repo, FileRepository)


def testGettingRepositoryFailsOnUnsupportedURL():
	with pytest.raises(RepositoryError):
		getRepository("lolnope:///asdf")


def testListingRepository(tempDir):
	repo = FileRepository(url=f"file://{tempDir}")
	assert not repo.content("", recursive=True)

	os.mkdir(os.path.join(tempDir, "foobar"))

	assert 1 == len(repo.content("", recursive=True))
	for content in repo.content("", recursive=True):
		assert content == {"path": "foobar", "type": "dir", "name": "foobar", "size": 0}

	with open(os.path.join(tempDir, "bar"), "w", encoding="utf8"):
		pass

	assert 2 == len(repo.content("", recursive=True))
	assert 2 == len(repo.listdir())
	assert "bar" in repo.listdir()


def testFileRepositoryFailsWithWrongURL():
	with pytest.raises(RepositoryError):
		FileRepository("nofile://nada")


@pytest.fixture
def twistedDAVXMLPath(test_data_path):
	return os.path.join(test_data_path, "util", "davxml", "twisted-davxml.data")


@pytest.fixture
def twistedDAVXML(twistedDAVXMLPath):
	with open(twistedDAVXMLPath, "r", encoding="utf8") as file:
		return file.read()


def testGetFileInfosFromDavXML(twistedDAVXML):
	content = getFileInfosFromDavXML(twistedDAVXML)
	assert len(content) == 4

	dirs = 0
	files = 0
	for item in content:
		assert isinstance(item["size"], int)
		if item["type"] == "dir":
			dirs = dirs + 1
		elif item["type"] == "file":
			files = files + 1
		else:
			raise ValueError(
				f"Unexpected type '{item['type']}' found. Maybe creepy testdata?"
			)

	assert dirs == 1
	assert files == 3


def test_file_repo_start_end(tmpdir):
	src_dir = tmpdir.mkdir("src")
	src = src_dir.join("test.txt")
	src.write("123456789")
	dst_dir = tmpdir.mkdir("dst")
	dst = dst_dir.join("test.txt")

	with http_test_server(serve_directory=src_dir) as server:
		for repo_url in (f"file://{src_dir}", f"http://localhost:{server.port}"):
			repo = getRepository(repo_url)
			repo.download("test.txt", str(dst), startByteNumber=-1, endByteNumber=-1)
			assert dst.read() == "123456789"

			repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=-1)
			assert dst.read() == "123456789"

			repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=0)
			assert dst.read() == "1"

			repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=1)
			assert dst.read() == "12"

			repo.download("test.txt", str(dst), startByteNumber=1, endByteNumber=1)
			assert dst.read() == "2"

			repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=2)
			assert dst.read() == "123"

			repo.download("test.txt", str(dst), startByteNumber=5, endByteNumber=8)
			assert dst.read() == "6789"


@pytest.mark.parametrize(
	"repo_type,dynamic", [("file", False), ("http", False), ("http", True)]
)
def test_limit_download(tmpdir, repo_type, dynamic):
	data = "o" * 2_000_000
	limit = 100_000

	src_dir = tmpdir.mkdir("src")
	src = src_dir.join("test.txt")
	src.write(data)
	dst_dir = tmpdir.mkdir("dst")
	dst = dst_dir.join("test.txt")

	repo = None
	simulate_other_traffic = False

	def download():
		start = time.time()
		repo.download("test.txt", str(dst))
		end = time.time()

		assert dst.read() == data
		if not dynamic:
			assert abs(round(end - start) - round(len(data) / limit)) <= 1

	def get_network_usage(self):
		traffic_ratio = repo.speed_limiter._dynamic_bandwidth_threshold_no_limit
		if simulate_other_traffic:
			traffic_ratio = repo.speed_limiter._dynamic_bandwidth_limit_rate

		bandwidth = int(repo.speed_limiter._average_speed / traffic_ratio)
		if repo._bytesTransfered >= len(data) * 0.8:
			if simulate_other_traffic:
				assert (
					repo.speed_limiter._dynamic_bandwidth_limit / bandwidth
				) <= repo.speed_limiter._dynamic_bandwidth_limit_rate * 2
			else:
				assert repo.speed_limiter._dynamic_bandwidth_limit == 0
		return bandwidth

	# Setting DEFAULT_BUFFER_SIZE to slow down transfer
	with mock.patch(
		"OPSI.Util.Repository.Repository.DEFAULT_BUFFER_SIZE",
		1000 if dynamic else 32 * 1000,
	):
		if repo_type.startswith(("http", "webdav")):
			with http_test_server(serve_directory=src_dir) as server:
				repo_url = f"{repo_type}://localhost:{server.port}"
				repo = getRepository(
					repo_url,
					maxBandwidth=0 if dynamic else limit,
					dynamicBandwidth=dynamic,
				)
				with mock.patch(
					"OPSI.Util.Repository.SpeedLimiter._get_network_usage",
					get_network_usage,
				):
					download()
					if dynamic:
						simulate_other_traffic = True
						download()
		else:
			repo_url = f"{repo_type}://{src_dir}"
			repo = getRepository(repo_url, maxBandwidth=limit, dynamicBandwidth=dynamic)
			download()


@pytest.mark.parametrize("repo_type", ["file", "webdav"])
def test_limit_upload(tmpdir, repo_type):
	data = "o" * 1_000_000
	limit = 100_000
	seconds = len(data) / limit

	src_dir = tmpdir.mkdir("src")
	src = src_dir.join("test.txt")
	src.write(data)
	dst_dir = tmpdir.mkdir("dst")
	dst = dst_dir.join("test.txt")

	def upload(repo_url):
		start = time.time()
		repo = getRepository(repo_url, maxBandwidth=limit)
		repo.upload(str(src), "test.txt")
		end = time.time()

		assert dst.read() == data
		assert abs(round(end - start) - round(seconds)) <= 1

	if repo_type.startswith(("http", "webdav")):
		with http_test_server(serve_directory=dst_dir) as server:
			upload(f"{repo_type}://localhost:{server.port}")
	else:
		upload(f"{repo_type}://{dst_dir}")


def test_depot_to_local_sync(tmp_path: pathlib.Path):
	product_id = "test1"

	depot_path = tmp_path / "depot"
	depot_path.mkdir()
	product_path = depot_path / product_id
	product_path.mkdir()
	file1 = product_path / "file1.txt"
	file1.write_text("0123456789")
	file2 = product_path / "subdir" / "file2.txt"
	file2.parent.mkdir()
	file2.write_text("0123456789" * 100_000)
	package_content_file = product_path / f"{product_id}.files"

	local_path = tmp_path / "local"
	local_path.mkdir()
	local_product_path = local_path / product_id

	packageContentFile = PackageContentFile(str(package_content_file))
	packageContentFile.setProductClientDataDir(str(product_path))
	packageContentFile.setClientDataFiles(
		list(
			findFilesGenerator(
				directory=str(product_path), followLinks=True, returnLinks=False
			)
		)
	)
	packageContentFile.generate()

	assert sorted(package_content_file.read_text().split("\n")) == sorted(
		(
			"",
			"f 'file1.txt' 10 781e5e245d69b566979b86e28d23f2c7",
			"d 'subdir' 0 ",
			"f 'subdir/file2.txt' 1000000 174ac9a4f023a557a68ab0417355970e",
		)
	)

	file_depot = getRepository(f"file://{str(depot_path)}")
	server_log_file = tmp_path / "server.log"
	with http_test_server(
		serve_directory=depot_path, log_file=server_log_file
	) as server:
		webdav_depot = getRepository(f"webdav://localhost:{server.port}")
		# http_test_server does not support PROPFIND
		webdav_depot.content = file_depot.content

		for depot in (file_depot, webdav_depot):
			sync = DepotToLocalDirectorySychronizer(
				sourceDepot=depot,
				destinationDirectory=str(local_path),
				productIds=[product_id],
			)
			sync._productId = product_id
			sync._fileInfo = packageContentFile.parse()
			sync._synchronizeDirectories(product_id, str(local_product_path))

			file = local_product_path / "file1.txt"
			assert file.exists()
			assert md5sum(str(file)) == "781e5e245d69b566979b86e28d23f2c7"

			file = local_product_path / "subdir" / "file2.txt"
			assert file.exists()
			assert file.read_text() == file2.read_text()
			assert md5sum(str(file)) == "174ac9a4f023a557a68ab0417355970e"

			if depot == webdav_depot:
				# Test no transfer needed (no server request)
				server_log_file.unlink()
				sync._synchronizeDirectories(product_id, str(local_product_path))
				assert not server_log_file.exists()

				# Test correct but incomplete file part
				(local_product_path / "subdir" / "file2.txt").write_text(
					"0123456789" * 50_000
				)
				sync._synchronizeDirectories(product_id, str(local_product_path))
				request = json.loads(server_log_file.read_text())
				assert request["headers"]["range"] == "bytes=500000-"

				# Test incorrect and incomplete file part
				server_log_file.unlink()
				(local_product_path / "subdir" / "file2.txt").write_text(
					"xxxxxxxxxx" * 50_000
				)
				sync._synchronizeDirectories(product_id, str(local_product_path))

				requests = server_log_file.read_text().split("\n")
				request = json.loads(requests[0])
				assert request["headers"]["range"] == "bytes=500000-"

				request = json.loads(requests[1])
				assert request["headers"]["range"] == "bytes=0-499999"

			shutil.rmtree(local_product_path)
