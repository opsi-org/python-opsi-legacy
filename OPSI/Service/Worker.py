# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Worker for the various interfaces.
"""

import base64
import os
import tempfile
import urllib
import uuid
from msgspec import msgpack
import lz4

from OPSI.Exceptions import OpsiBadRpcError, OpsiServiceAuthenticationError
from OPSI.Service.JsonRpc import JsonRpc
from OPSI.Types import forceList, forceUnicode
from OPSI.Util import fromJson, objectToHtml, toJson
from OPSI.Util.HTTP import deflateDecode, deflateEncode, gzipDecode, gzipEncode
from opsicommon.logging import get_logger
from opsicommon.objects import serialize, deserialize
from twisted.internet import defer, threads
from twisted.python.failure import Failure

INTERFACE_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
	<meta http-equiv="Content-Type" content="text/xhtml; charset=utf-8" />
	<title>%(title)s</title>
	<style>
	a:link 	      { color: #555555; text-decoration: none; }
	a:visited     { color: #555555; text-decoration: none; }
	a:hover	      { color: #46547f; text-decoration: none; }
	a:active      { color: #555555; text-decoration: none; }
	body          { font-family: verdana, arial; font-size: 12px; }
	#title        { padding: 10px; color: #6276a0; font-size: 20px; letter-spacing: 5px; }
	input, select { background-color: #fafafa; border: 1px #abb1ef solid; width: 430px; font-family: verdana, arial; }
	.json         { color: #555555; width: 95%%; float: left; clear: both; margin: 30px; padding: 20px; background-color: #fafafa; border: 1px #abb1ef dashed; font-size: 11px; }
	.json_key     { color: #9e445a; }
	.json_label   { color: #abb1ef; margin-top: 20px; margin-bottom: 5px; font-size: 11px; }
	.title        { color: #555555; font-size: 20px; font-weight: bolder; letter-spacing: 5px; }
	.button       { color: #9e445a; background-color: #fafafa; border: none; margin-top: 20px; font-weight: bolder; }
	.box          { background-color: #fafafa; border: 1px #555555 solid; padding: 20px; margin-left: 30px; margin-top: 50px;}
	</style>
	<script type="text/javascript">
	var path = '%(path)s';
	var parameters = new Array();
	var method = '';
	var params = '';
	var id = '"id": 1';
	%(javascript)s

	function createElement(element) {
		if (typeof document.createElementNS != 'undefined') {
			return document.createElementNS('http://www.w3.org/1999/xhtml', element);
		}
		if (typeof document.createElement != 'undefined') {
			return document.createElement(element);
		}
		return false;
	}

	function selectPath(select) {
		path = select.value;
		document.getElementById('json_method').firstChild.data = '"backend_getInterface"';
		document.getElementById('json_params').firstChild.data = '[]';
		onSubmit();
	}
	function selectMethod(select) {
		method = select.value;
		tbody = document.getElementById('tbody');
		var button;
		var json;
		for (i=tbody.childNodes.length-1; i>=0; i--) {
			if (tbody.childNodes[i].id == 'tr_path') {
			}
			else if (tbody.childNodes[i].id == 'tr_method') {
			}
			else if (tbody.childNodes[i].id == 'tr_submit') {
				button = tbody.childNodes[i];
				tbody.removeChild(button);
			}
			else if (tbody.childNodes[i].id == 'tr_json') {
				json = tbody.childNodes[i];
				tbody.removeChild(json);
			}
			else {
				tbody.removeChild(tbody.childNodes[i]);
			}
		}

		for (i=0; i < parameters[select.value].length; i++) {
			tr = createElement("tr");
			td1 = createElement("td");
			text = document.createTextNode(parameters[select.value][i] + ":");
			td1.appendChild(text);
			td2 = createElement("td");
			input = createElement("input");
			input.setAttribute('onchange', 'jsonString()');
			input.setAttribute('type', 'text');
			if ((method == currentMethod) && (currentParams[i] != null)) {
				input.value = currentParams[i];
			}
			td2.appendChild(input);
			tr.appendChild(td1);
			tr.appendChild(td2);
			tbody.appendChild(tr)
		}
		tbody.appendChild(json)
		tbody.appendChild(button)

		jsonString();
	}

	function onSubmit() {
		var json = '{ "id": 1, "method": ';
		json += document.getElementById('json_method').firstChild.data;
		json += ', "params": ';
		json += document.getElementById('json_params').firstChild.data;
		json += ' }';
		window.location.href = '/' + path + '?' + json;
		return false;
	}

	function jsonString() {
		span = document.getElementById('json_method');
		for (i=span.childNodes.length-1; i>=0; i--) {
			span.removeChild(span.childNodes[i])
		}
		span.appendChild(document.createTextNode('"' + method + '"'));

		span = document.getElementById('json_params');
		for (i=span.childNodes.length-1; i>=0; i--) {
			span.removeChild(span.childNodes[i])
		}
		params = '['
		inputs = document.getElementsByTagName('input');
		for (i=0; i<inputs.length; i++) {
			if (inputs[i].id != 'submit') {
				if (inputs[i].value == '') {
					i = inputs.length;
				}
				else {
					if (i>0) {
						params += ', ';
					}
					params += inputs[i].value;
				}
			}
		}
		span.appendChild(document.createTextNode(params + ']'));
	}

	function onLoad() {
		selectMethod(document.getElementById('method_select'));
		window.history.replaceState(null, null, window.location.href.split('?')[0]);
	}
	</script>
</head>
<body onload="onLoad();">
	<p id="title">
		<img src="/opsi_logo.png" /><br /><br />
		<span style="padding: 1px">%(title)s</span>
	</p>
	<form method="post" onsubmit="return onSubmit()">
		<table class="box">
			<tbody id="tbody">
				<tr id="tr_path">
					<td style="width: 150px;">Path:</td>
					<td style="width: 440px;">
						<select id="path_select" onchange="selectPath(this)" name="path">
							%(select_path)s
						</select>
					</td>
				</tr>
				<tr id="tr_method">
					<td style="width: 150px;">Method:</td>
					<td style="width: 440px;">
						<select id="method_select" onchange="selectMethod(this)" name="method">
							%(select_method)s
						</select>
					</td>
				</tr>
				<tr id="tr_json">
					<td colspan="2">
						<div class="json_label">
							resulting json remote procedure call:
						</div>
						<div class="json" style="width: 480px;">
							{&nbsp;"<font class="json_key">method</font>": <span id="json_method"></span>,<br />
							&nbsp;&nbsp;&nbsp;"<font class="json_key">params</font>": <span id="json_params">[]</span>,<br />
							&nbsp;&nbsp;&nbsp;"<font class="json_key">id</font>": 1 }
						</div>
					</td>
				</tr>
				<tr id="tr_submit">
					<td align="center" colspan="2">
						<input value="Execute" id="submit" class="button" type="submit" />
					</td>
				</tr>
			</tbody>
		</table>
	</form>
	<div class="json_label" style="padding-left: 30px">json-rpc result</div>
	%(result)s
</body>
</html>
"""

logger = get_logger("opsi.general")


class WorkerOpsi:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
	"""Base worker class"""

	def __init__(self, service, request, resource):
		self.service = service
		self.request = request
		self.query = ""
		self.path = ""
		self.resource = resource
		self.session = None
		self.authRealm = "OPSI Service"
		self.debugDir = os.path.join(tempfile.gettempdir(), "opsiclientd-debug")

	def process(self):
		logger.info("Worker %s started processing", self)
		deferred = defer.Deferred()
		deferred.addCallback(self._getSession)
		deferred.addCallback(self._authenticate)
		if self.request.method != b"HEAD":
			deferred.addCallback(self._getQuery)
			deferred.addCallback(self._processQuery)
		deferred.addCallback(self._setCookie)
		deferred.addCallback(self._setResponse)
		deferred.addCallback(self._finishRequest)
		deferred.addCallback(self._freeSession)
		deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _finishRequest(self, result):  # pylint: disable=unused-argument
		self.request.finish()

	def _getSessionHandler(self):
		try:
			return self.service._getSessionHandler()  # pylint: disable=protected-access
		except AttributeError:  # no attribtue _getSessionHandler
			return None

	def _errback(self, failure):
		logger.trace("%s._errback", self.__class__.__name__)

		self._freeSession(failure)
		self._setCookie(failure)
		self.request.setResponseCode(500)

		try:
			failure.raiseException()
		except OpsiServiceAuthenticationError as err:
			logger.warning(err, exc_info=True)
			self.request.setResponseCode(401)
			self.request.setHeader("www-authenticate", f"basic realm={self.authRealm}")
		except OpsiBadRpcError as err:
			logger.warning(err, exc_info=True)
			self.request.setResponseCode(400)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)
		self._renderError(failure)
		self.request.finish()

	def _renderError(self, failure):
		self.request.setHeader("Content-Type", "text/html; charset=utf-8")
		error = "Unknown error"
		try:
			failure.raiseException()
		except Exception as err:  # pylint: disable=broad-except
			error = str(err)
		self.request.write(error.encode("utf-8"))

	def _freeSession(self, result):
		if self.session:
			logger.debug("Freeing session %s", self.session)
			self.session.decreaseUsageCount()
		return result

	def _getAuthorization(self):
		user = password = ""
		logger.debug("Trying to get username and password from Authorization header")
		auth = self.request.getHeader("Authorization")
		if auth:
			auth = auth.split()
			logger.debug("Authorization header found (type: %s)", auth[0])
			try:
				encoded = auth[1].encode("ascii")
				logger.confidential("Auth encoded: %s", encoded)
				parts = str(base64.decodebytes(encoded), encoding="latin-1").split(":")
				if len(parts) > 6:
					user = ":".join(parts[:6])
					password = ":".join(parts[6:])
				else:
					user = parts[0]
					password = ":".join(parts[1:])
				user = user.strip().lower()
				logger.confidential(
					"Client supplied username '%s' and password '%s'", user, password
				)
			except Exception as err:  # pylint: disable=broad-except
				request_address = self.request.getClientAddress()
				request_ip = None  # mimic getClientIP behaviour
				if hasattr(request_address, "host"):
					request_ip = request_address.host
				logger.error(
					"Bad Authorization header from '%s': %s",
					request_ip,
					err,
					exc_info=True,
				)

		return (user, password)

	def _getCredentials(self):
		return self._getAuthorization()

	def _getUserAgent(self):
		try:
			userAgent = self.request.getHeader("user-agent")
		except Exception:  # pylint: disable=broad-except
			request_address = self.request.getClientAddress()
			request_ip = None  # mimic getClientIP behaviour
			if hasattr(request_address, "host"):
				request_ip = request_address.host
			logger.info("Client '%s' did not supply user-agent", request_ip)
			userAgent = None

		if not userAgent:
			userAgent = "unknown"

		return userAgent

	def _getSessionId(self):
		"Get session id from cookie request header"
		sessionId = ""
		try:
			cookies = self.request.getHeader("cookie")
			if cookies:
				for cookie in cookies.split(";"):
					if "=" not in cookie:
						continue
					(name, value) = cookie.split("=", 1)
					if name.strip() == self._getSessionHandler().sessionName:
						sessionId = forceUnicode(value.strip())
						break
		except Exception as err:  # pylint: disable=broad-except
			logger.error("Failed to get cookie from header: %s", err)

		logger.confidential("sessionId: %s", sessionId)
		return sessionId

	def _getSession(self, result):
		"""This method restores a session or generates a new one."""
		self.session = None

		logger.confidential("Request headers: %s", self.request.getAllHeaders())

		userAgent = self._getUserAgent()
		sessionHandler = self._getSessionHandler()
		sessionId = self._getSessionId()

		request_address = self.request.getClientAddress()
		request_ip = None  # mimic getClientIP behaviour
		if hasattr(request_address, "host"):
			request_ip = request_address.host
		# Get Session object
		self.session = sessionHandler.getSession(sessionId, request_ip)
		if sessionId == self.session.uid:
			logger.info(
				"Reusing session for client '%s', application '%s'",
				request_ip,
				userAgent,
			)
		elif sessionId:
			logger.notice(
				"Application '%s' on client '%s' supplied non existing session id: %s",
				userAgent,
				request_ip,
				sessionId,
			)

		if sessionHandler and self.session.ip and (self.session.ip != request_ip):
			logger.critical(
				"Client ip '%s' does not match session ip '%s', deleting old session and creating a new one",
				request_ip,
				self.session.ip,
			)
			sessionHandler.deleteSession(self.session.uid)
			self.session = sessionHandler.getSession()

		# Set ip
		self.session.ip = request_ip

		# Set user-agent / application
		if self.session.userAgent and (self.session.userAgent != userAgent):
			logger.warning(
				"Application changed from '%s' to '%s' for existing session of client '%s'",
				self.session.userAgent,
				userAgent,
				request_ip,
			)
		self.session.userAgent = userAgent

		logger.confidential(
			"Session id is %s for client %s, application %s",
			self.session.uid,
			request_ip,
			self.session.userAgent,
		)

		logger.confidential("Session content: %s", self.session.__dict__)
		return result

	def _setCookie(self, result):  # pylint: disable=unused-argument
		logger.debug("%s._setCookie", self)
		if not self.session:
			return

		# Add cookie to headers
		logger.debug("Adding session cookie to headers")
		self.request.addCookie(self.session.name, self.session.uid, path="/")

	def _authenticate(self, result):
		"""
		This function tries to authenticate a user.
		Raises an exception on authentication failure.
		"""
		if self.session.authenticated:
			return result

		try:
			# Get authorization
			(self.session.user, self.session.password) = self._getCredentials()
			self.session.authenticated = True
		except Exception as err:
			logger.info(err, exc_info=True)
			self._freeSession(result)
			self._getSessionHandler().deleteSession(self.session.uid)
			raise OpsiServiceAuthenticationError(f"Forbidden: {err}") from err

		return result

	def _getQuery(self, result):
		self.query = ""
		if self.request.method == b"GET":
			self.query = urllib.parse.urlparse(
				urllib.parse.unquote(self.request.uri.decode("ascii"))
			).query
		elif self.request.method == b"POST":
			self.query = self.request.content.read()
		else:
			raise ValueError(f"Unhandled method '{self.request.method}'")
		return result

	def _decodeQuery(self, result):
		try:
			logger.debug("Decoding query, request method %s", self.request.method)
			if self.request.method == b"POST":
				logger.trace("Request headers: %s", self.request.getAllHeaders())
				try:
					contentType = self.request.getHeader("Content-Type").lower()
				except Exception:  # pylint: disable=broad-except
					contentType = None
				try:
					contentEncoding = self.request.getHeader("Content-Encoding").lower()
				except Exception:  # pylint: disable=broad-except
					contentEncoding = None

				logger.debug(
					"Content-Type: %s, Content-Encoding: %s",
					contentType,
					contentEncoding,
				)

				if contentType and "gzip" in contentType:
					# Invalid MIME type.
					# Probably it is gzip-application/json-rpc and therefore
					# we need to behave like we did before.
					logger.debug(
						"Expecting compressed data from client (backwards compatible)"
					)
					self.query = deflateDecode(self.query)
				elif contentEncoding == "lz4":
					self.query = lz4.frame.decompress(self.query)
				elif contentEncoding == "gzip":
					logger.debug("Expecting gzip compressed data from client")
					self.query = gzipDecode(self.query)
				elif contentEncoding == "deflate":
					logger.debug("Expecting deflate compressed data from client")
					self.query = deflateDecode(self.query)

		except Exception as err:
			logger.error("Error during decoding of query: %s", err, exc_info=True)
			logger.trace(self.query)
			raise

		logger.trace("query: %s", self.query)
		return result

	def _processQuery(self, result):
		logger.warning(
			"Class %s should overwrite _processQuery", self.__class__.__name__
		)
		return self._decodeQuery(result)

	def _generateResponse(self, result):  # pylint: disable=unused-argument
		self.request.setResponseCode(200)
		self.request.setHeader("Content-Type", "text/html; charset=utf-8")
		self.request.write("")

	def _setResponse(self, result):
		return self._generateResponse(result)


class WorkerOpsiJsonRpc(WorkerOpsi):  # pylint: disable=too-few-public-methods
	def __init__(self, service, request, resource):
		WorkerOpsi.__init__(self, service, request, resource)

		self._callInstance = None
		self._callInterface = {}
		self._rpcs = []

	def _getCallInstance(self, result):  # pylint: disable=unused-argument
		logger.warning(
			"Class %s should overwrite _getCallInstance", self.__class__.__name__
		)
		self._callInstance = None
		self._callInterface = {}

	def _getRpcs(self, result):
		if not self.query:
			raise ValueError("Got no rpcs")
		if not self._callInstance:
			raise RuntimeError(f"Call instance not defined in {self}")
		if not self._callInterface:
			raise RuntimeError(f"Call interface not defined in {self}")

		rpcs = []
		try:
			if self.request.getHeader("Content-Type") == "application/msgpack":
				rpcs = deserialize(
					msgpack.decode(self.query), deep=True, prevent_object_creation=True
				)
			else:
				rpcs = fromJson(self.query, preventObjectCreation=True)
			if not rpcs:
				raise ValueError("Got no rpcs")
		except Exception as err:
			if isinstance(err, UnicodeDecodeError) and self.debugDir:
				try:
					if not os.path.exists(self.debugDir):
						os.makedirs(self.debugDir)
					debug_file = os.path.join(
						self.debugDir, f"service-json-decode-error-{uuid.uuid1()}"
					)
					logger.notice("Writing debug file: %s", debug_file)
					with open(debug_file, "wb") as file:
						file.write(self.query)
				except Exception as err2:  # pylint: disable=broad-except
					logger.error(err2, exc_info=True)
			raise OpsiBadRpcError(f"Failed to decode rpc: {err}") from err

		for rpc in forceList(rpcs):
			rpc = JsonRpc(
				instance=self._callInstance, interface=self._callInterface, rpc=rpc
			)
			self._rpcs.append(rpc)

		return result

	def _executeRpc(self, result, rpc):  # pylint: disable=unused-argument,no-self-use
		deferred = threads.deferToThread(rpc.execute)
		return deferred

	def _executeRpcs(self, result):  # pylint: disable=unused-argument
		deferred = defer.Deferred()
		for rpc in self._rpcs:
			deferred.addCallback(self._executeRpc, rpc)
		# deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _processQuery(self, result):
		deferred = defer.Deferred()
		deferred.addCallback(self._decodeQuery)
		deferred.addCallback(self._getCallInstance)
		deferred.addCallback(self._getRpcs)
		deferred.addCallback(self._executeRpcs)
		# deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _generateResponse(self, result):  # pylint: disable=too-many-branches
		invalidMime = (
			False  # For handling the invalid MIME type "gzip-application/json-rpc"
		)
		encoding = None
		try:
			if "lz4" in self.request.getHeader("Accept-Encoding"):
				encoding = "lz4"
			elif "gzip" in self.request.getHeader("Accept-Encoding"):
				encoding = "gzip"
			elif "deflate" in self.request.getHeader("Accept-Encoding"):
				encoding = "deflate"
		except Exception as err:  # pylint: disable=broad-except
			logger.trace("Failed to get Accept-Encoding from request header: %s", err)

		try:
			if self.request.getHeader("Accept"):
				for accept in self.request.getHeader("Accept").split(","):
					if accept.strip().startswith("gzip"):
						invalidMime = True
						encoding = "gzip"
						break
		except Exception as err:  # pylint: disable=broad-except
			logger.error("Failed to get accepted mime types from header: %s", err)

		response = [serialize(rpc.getResponse()) for rpc in self._rpcs]

		if len(response) == 1:
			response = response[0]
		if not response:
			response = ""

		self.request.setResponseCode(200)

		data = b""
		if self.request.getHeader("Content-Type") == "application/msgpack":
			self.request.setHeader("Content-Type", "application/msgpack")
			data = msgpack.encode(serialize(response, deep=True))
		else:
			self.request.setHeader("Content-Type", "application/json; charset=utf-8")
			data = toJson(response).encode("utf-8")

		if invalidMime:
			# The invalid requests expect the encoding set to
			# gzip but the content is deflated.
			self.request.setHeader("Content-Encoding", "gzip")
			self.request.setHeader(
				"Content-Type", "gzip-application/json; charset=utf-8"
			)
			logger.debug(
				"Sending deflated data (backwards compatible - with Content-Encoding 'gzip')"
			)
			data = deflateEncode(data)
		elif encoding == "lz4":
			logger.debug("Sending lz4 compressed data")
			self.request.setHeader("Content-Encoding", encoding)
			data = lz4.frame.compress(data, compression_level=0, block_linked=True)
		elif encoding == "deflate":
			logger.debug("Sending deflated data")
			self.request.setHeader("Content-Encoding", encoding)
			data = deflateEncode(data)
		elif encoding == "gzip":
			logger.debug("Sending gzip compressed data")
			self.request.setHeader("Content-Encoding", encoding)
			data = gzipEncode(data)
		else:
			logger.debug("Sending plain data")

		logger.trace("Sending response: %s", data)
		self.request.write(data)
		return result

	def _renderError(self, failure):
		error = "Unknown error"
		try:
			failure.raiseException()
		except Exception as err:  # pylint: disable=broad-except
			error = {"class": err.__class__.__name__, "message": str(err)}
			error = {"id": None, "result": None, "error": error}

		data = b""
		if self.request.getHeader("Content-Type") == "application/msgpack":
			self.request.setHeader("Content-Type", "application/msgpack")
			data = msgpack.encode(error)
		else:
			self.request.setHeader("Content-Type", "application/json; charset=utf-8")
			data = toJson(error).encode("utf-8")

		self.request.write(data)
		return failure


class WorkerOpsiJsonInterface(WorkerOpsiJsonRpc):  # pylint: disable=too-few-public-methods
	"""
	Worker responsible for creating the human-usable interface page.
	"""

	def _generateResponse(self, result):  # pylint: disable=too-many-locals
		logger.info("Creating interface page")

		javascript = ["var currentParams = new Array();", "var currentMethod = null;"]
		currentMethod = ""
		if self._rpcs:
			currentMethod = self._rpcs[0].getMethodName()
			javascript.append(f"currentMethod = '{currentMethod}';")
			for index, param in enumerate(self._rpcs[0].params):
				javascript.append(f"currentParams[{index}] = '{toJson(param)}';")

		selectMethod = []
		if self._callInterface:
			try:
				for method in self._callInterface:
					methodName = method["name"]
					javascript.append(f"parameters['{methodName}'] = new Array();")
					for index, param in enumerate(method["params"]):
						javascript.append(
							f"parameters['{methodName}'][{index}]='{param}';"
						)

					selected = ""
					if method["name"] == currentMethod:
						selected = ' selected="selected"'
					selectMethod.append(f"<option{selected}>{method['name']}</option>")
			except Exception as err:  # pylint: disable=broad-except
				logger.error(err, exc_info=True)

		def wrapInDiv(obj):
			return f'<div class="json">{obj}</div>'

		results = ['<div id="result">']
		if isinstance(result, Failure):
			error = "Unknown error"
			try:
				result.raiseException()
			except Exception as err:  # pylint: disable=broad-except
				error = {"class": err.__class__.__name__, "message": str(err)}
				error = toJson({"id": None, "result": None, "error": error})
			results.append(wrapInDiv(objectToHtml(error)))
		else:
			for rpc in self._rpcs:
				results.append(wrapInDiv(objectToHtml(serialize(rpc.getResponse()))))
		results.append("</div>")

		html = INTERFACE_PAGE % {
			"path": self.path,
			"title": "opsi interface page",
			"javascript": "\n".join(javascript),
			"select_path": f'<option selected="selected">{self.path}</option>',
			"select_method": "".join(selectMethod),
			"result": "".join(results),
		}

		self.request.setHeader("Content-Type", "text/html; charset=utf-8")
		self.request.write(html.strip().encode("utf-8"))
		return result

	def _renderError(self, failure):
		return self._generateResponse(failure)
