# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the opsi-package-updater functionality.
"""

import json
import os
import shutil
import subprocess

import pytest
from opsicommon.testing.helpers import http_test_server

from OPSI.Util import md5sum
from OPSI.Util.File import ZsyncFile
from OPSI.Util.Task.UpdatePackages import OpsiPackageUpdater
from OPSI.Util.Task.UpdatePackages.Config import DEFAULT_CONFIG
from OPSI.Util.Task.UpdatePackages.Notifier import DummyNotifier
from OPSI.Util.Task.UpdatePackages.Repository import (
	LinksExtractor,
	ProductRepositoryInfo,
)

from .helpers import createTemporaryTestfile, mock
from .test_hosts import getConfigServer


@pytest.fixture
def package_updater_class(backendManager) -> OpsiPackageUpdater:
	configServer = getConfigServer()
	backendManager.host_insertObject(configServer)

	klass = OpsiPackageUpdater
	with mock.patch.object(klass, "getConfigBackend", return_value=backendManager):
		yield klass


def test_listing_local_packages(tmpdir, package_updater_class):  # pylint: disable=redefined-outer-name
	config_file = os.path.join(tmpdir, "emptyconfig.conf")
	with open(config_file, "wb"):
		pass

	filenames = ["not.tobefound.opsi.nono", "thingy_1.2-3.opsi", "thingy_1.2-3.opsi.no"]

	for filename in filenames:
		with open(os.path.join(tmpdir, filename), "wb"):
			pass

	config = DEFAULT_CONFIG.copy()
	config["packageDir"] = tmpdir
	config["configFile"] = config_file

	package_updater = package_updater_class(config)
	local_packages = package_updater.getLocalPackages()
	package_info = local_packages.pop()
	assert not local_packages, "There should only be one package!"

	expected_info = {
		"productId": "thingy",
		"version": "1.2-3",
		"packageFile": os.path.join(tmpdir, "thingy_1.2-3.opsi"),
		"filename": "thingy_1.2-3.opsi",
		"md5sum": None,
	}

	assert set(package_info.keys()) == set(expected_info.keys())
	assert package_info["md5sum"]  # We want any value

	del expected_info["md5sum"]  # Not comparing this
	for key, expected_value in expected_info.items():
		assert package_info[key] == expected_value


@pytest.fixture
def example_config_path(test_data_path):
	file_path = os.path.join(
		test_data_path, "util", "task", "updatePackages", "example_updater.conf"
	)
	with createTemporaryTestfile(file_path) as new_path:
		yield new_path


def test_parsing_config_file(tmpdir, example_config_path, package_updater_class):  # pylint: disable=redefined-outer-name
	prepared_config = DEFAULT_CONFIG.copy()
	prepared_config["packageDir"] = tmpdir
	prepared_config["configFile"] = example_config_path

	repo_path = os.path.join(tmpdir, "repos.d")
	os.mkdir(repo_path)

	patch_config_file(
		example_config_path,
		logFile=os.path.join(tmpdir, "opsi-package-updater.log"),
		packageDir=tmpdir,
		repositoryConfigDir=repo_path,
	)
	copy_example_repo_configs(repo_path)

	package_updater = package_updater_class(prepared_config)
	config = package_updater.config

	assert config
	assert config["repositories"]
	assert len(config["repositories"]) == 3
	for repo in config["repositories"]:
		assert isinstance(repo, ProductRepositoryInfo)

	assert config["packageDir"] == tmpdir
	assert config["tempdir"] == "/tmp"
	assert config["repositoryConfigDir"] == repo_path

	# Global proxy
	assert not config["proxy"]

	# e-mail notification settings
	assert config["notification"] is False
	assert config["smtphost"] == "smtp"
	assert config["smtpport"] == 25
	assert config["smtpuser"] == DEFAULT_CONFIG["smtpuser"]
	assert config["smtppassword"] == DEFAULT_CONFIG["smtppassword"]
	assert config["use_starttls"] is False
	assert config["sender"] == "opsi-package-updater@localhost"
	assert config["receivers"] == ["root@localhost", "anotheruser@localhost"]
	assert config["subject"] == "opsi-package-updater example config"

	# Automatic installation settings
	assert config["installationWindowStartTime"] == "01:23"
	assert config["installationWindowEndTime"] == "04:56"
	assert config["installationWindowExceptions"] == ["firstproduct", "second-product"]

	# Wake-On-LAN settings
	assert config["wolAction"] is False
	assert config["wolActionExcludeProductIds"] == ["this", "that"]
	assert config["wolShutdownWanted"] is True
	assert config["wolStartGap"] == 10


def patch_config_file(filename, **values):
	with open(filename, encoding="utf-8") as config_file:
		lines = config_file.readlines()

	new_lines = []
	for line in lines:
		for key, value in values.items():
			if line.startswith(key):
				new_lines.append(f"{key} = {value}\n")
				break
		else:
			new_lines.append(line)

	with open(filename, "w", encoding="utf-8") as config_file:
		for line in new_lines:
			config_file.write(line)


def copy_example_repo_configs(target_dir):
	from .conftest import TEST_DATA_PATH  # pylint: disable=import-outside-toplevel

	for filename in ("experimental.repo",):
		file_path = os.path.join(
			TEST_DATA_PATH, "util", "task", "updatePackages", filename
		)
		shutil.copy(file_path, target_dir)


@pytest.fixture(params=["apachelisting.html"], ids=["apache"])
def repository_listing_page(test_data_path, request):
	file_path = os.path.join(
		test_data_path, "util", "task", "updatePackages", request.param
	)

	with open(file_path, encoding="utf-8") as example_file:
		return example_file.read()


def test_link_extracting(repository_listing_page):  # pylint: disable=redefined-outer-name
	extractor = LinksExtractor()
	extractor.feed(repository_listing_page)
	extractor.close()

	for _link in extractor.getLinks():
		# Currently just checking their existance
		break
	else:
		raise RuntimeError("No links found!")


def test_global_proxy_applied_to_repos(
	tmpdir, example_config_path, package_updater_class
):  # pylint: disable=redefined-outer-name
	test_proxy = "http://hurr:durr@someproxy:1234"

	prepared_config = DEFAULT_CONFIG.copy()
	prepared_config["packageDir"] = tmpdir
	prepared_config["configFile"] = example_config_path

	repo_path = os.path.join(tmpdir, "repos.d")
	os.mkdir(repo_path)

	patch_config_file(
		example_config_path,
		logFile=os.path.join(tmpdir, "opsi-package-updater.log"),
		packageDir=tmpdir,
		repositoryConfigDir=repo_path,
		proxy=test_proxy,
	)
	copy_example_repo_configs(repo_path)

	package_updater = package_updater_class(prepared_config)
	config = package_updater.config

	assert config["proxy"] == test_proxy

	for repo in config["repositories"]:
		assert repo.proxy == test_proxy


def test_check_accept_ranges(tmp_path, package_updater_class):  # pylint: disable=redefined-outer-name,too-many-locals,too-many-statements
	zsync_curl = False
	try:
		proc = subprocess.run(["zsync-curl", "-V"], capture_output=True, check=False)
		if "zsync_curl" in proc.stdout.decode("utf-8"):
			zsync_curl = True
	except FileNotFoundError:
		pass

	if not zsync_curl:
		pytest.skip("zsync-curl not available")

	config_file = tmp_path / "empty.conf"
	config_file.touch()
	local_dir = tmp_path / "local_packages"
	local_dir.mkdir()
	server_dir = tmp_path / "server_packages"
	server_dir.mkdir()
	repo_conf_path = tmp_path / "repos.d"
	repo_conf_path.mkdir()
	test_repo_conf = repo_conf_path / "test.repo"
	server_log = tmp_path / "server.log"

	config = DEFAULT_CONFIG.copy()
	config["configFile"] = str(config_file)
	config["packageDir"] = str(local_dir)

	config_file.write_text(
		data=(
			"[general]\n"
			f"packageDir = {str(local_dir)}\n"
			f"repositoryConfigDir = {str(repo_conf_path)}\n"
		),
		encoding="utf-8",
	)

	server_package_file = server_dir / "hwaudit_4.2.0.0-1.opsi"
	server_package_file.write_bytes(b"abc" * 3_000_000)
	zsync_file = server_dir / "hwaudit_4.2.0.0-1.opsi.zsync"
	ZsyncFile(str(zsync_file)).generate(str(server_package_file))
	md5sum_file = server_dir / "hwaudit_4.2.0.0-1.opsi.md5"
	server_package_md5sum = md5sum(str(server_package_file))
	md5sum_file.write_text(server_package_md5sum, encoding="ascii")

	def write_repo_conf(base_url, proxy):
		test_repo_conf.write_text(
			data=(
				f"[repository_test]\nactive = true\nbaseUrl = {base_url}\ndirs = /\nproxy = {proxy}\n"
				"autoInstall = true\nusername = user\npassword = pass\n"
			),
			encoding="utf-8",
		)

	for accept_ranges in (True, False):
		with http_test_server(
			serve_directory=server_dir,
			response_headers={"accept-ranges": "bytes"} if accept_ranges else None,
			log_file=str(server_log),
		) as server:
			base_url = f"http://localhost:{server.port}"
			proxy = ""
			# base_url = "https://download.uib.de/4.2/stable/packages/windows/localboot"
			# proxy = "http://proxy:3128"

			write_repo_conf(base_url, proxy)

			local_package_file = local_dir / "hwaudit_4.1.0.0-1.opsi"
			local_package_file.write_bytes(
				server_package_file.read_bytes() + b"def" * 3_000_000
			)

			package_updater: OpsiPackageUpdater = package_updater_class(config)

			available_packages = package_updater.getDownloadablePackages()
			package = None
			for available_package in available_packages:
				if available_package["productId"] == "hwaudit":
					package = available_package
					break
			assert package is not None

			local_packages = package_updater.getLocalPackages()

			assert package["version"] == "4.2.0.0-1"
			assert package["packageFile"] == f"{base_url}/hwaudit_4.2.0.0-1.opsi"
			assert package["filename"] == server_package_file.name
			assert package["zsyncFile"] == f"{base_url}/{zsync_file.name}"
			with package_updater.makeSession(package["repository"]) as session:
				assert (
					package_updater._useZsync(session, package, local_packages[0])
					== accept_ranges
				)  # pylint: disable=protected-access

			if "localhost" in base_url:
				server_log.unlink()
			new_packages = package_updater.get_packages(DummyNotifier())
			assert len(new_packages) == 1

			request = json.loads(
				server_log.read_text(encoding="utf-8").rstrip().split("\n")[-1]
			)
			if "localhost" in base_url:
				assert request["headers"].get("Authorization") == "Basic dXNlcjpwYXNz"
				assert (
					md5sum(str(local_dir / server_package_file.name))
					== server_package_md5sum
				)
				server_log.unlink()
				if accept_ranges:
					assert "Range" in request["headers"]
				else:
					assert "Range" not in request["headers"]
