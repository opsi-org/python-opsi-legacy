# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing jsonrpc backend functionality.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from OPSI.Backend.JSONRPC import JSONRPCBackend
from opsicommon.exceptions import OpsiServiceConnectionError
from opsicommon.testing.helpers import http_test_server


def test_jsonrpc_backend(tmp_path: Path) -> None:
	log_file = tmp_path / "request.log"
	interface: list[dict[str, Any]] = [
		{
			"name": "test_method",
			"params": ["arg1", "*arg2", "**arg3"],
			"args": ["arg1", "arg2"],
			"varargs": None,
			"keywords": "arg4",
			"defaults": ["default2"],
			"deprecated": False,
			"alternative_method": None,
			"doc": None,
			"annotations": {},
		},
		{
			"name": "backend_getInterface",
			"params": [],
			"args": ["self"],
			"varargs": None,
			"keywords": None,
			"defaults": None,
			"deprecated": False,
			"alternative_method": None,
			"doc": None,
			"annotations": {},
		},
		{
			"name": "backend_exit",
			"params": [],
			"args": ["self"],
			"varargs": None,
			"keywords": None,
			"defaults": None,
			"deprecated": False,
			"alternative_method": None,
			"doc": None,
			"annotations": {},
		},
	]
	with http_test_server(
		generate_cert=True,
		log_file=log_file,
		response_headers={"server": "opsiconfd 4.3.0.0 (uvicorn)"},
	) as server:
		server.response_body = json.dumps(
			{"jsonrpc": "2.0", "result": interface}
		).encode("utf-8")
		server.response_headers["Content-Type"] = "application/json"
		backend = JSONRPCBackend(address=f"https://localhost:{server.port}")
		backend.test_method("arg1")  # pylint: disable=no-member

		with pytest.raises(OpsiServiceConnectionError):
			backend = JSONRPCBackend(address=f"https://localhost:{server.port+1}")
