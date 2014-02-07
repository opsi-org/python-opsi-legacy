#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
opsi python library - Worker

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2010, 2013 uib GmbH

http://www.uib.de/

All rights reserved.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

@copyright:	uib GmbH <info@uib.de>
@author: Jan Schneider <j.schneider@uib.de>
@author: Niko Wenselowski <n.wenselowski@uib.de>
@license: GNU Affero General Public License version 3
"""

import base64
import urllib
import zlib
from twisted.internet import defer, reactor, threads
from twisted.python import failure

from OPSI.web2 import responsecode, http_headers, http, stream

from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Util import objectToHtml, toJson, fromJson, serialize
from OPSI.Service.JsonRpc import JsonRpc

logger = Logger()

interfacePage = u'''<?xml version="1.0" encoding="UTF-8"?>
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
	// <![CDATA[
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
						params += inputs[i].value.replace(/\\\/g, '\\\\\\\\');
					}
				}
			}
			span.appendChild(document.createTextNode(params + ']'));
		}
	// ]]>
	</script>
</head>
<body onload="selectMethod(document.getElementById('method_select'))">
	<p id="title">
		<img src="/opsi_logo.png" />
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
'''


class WorkerOpsi:
	def __init__(self, service, request, resource):
		self.service   = service
		self.request   = request
		self.query     = u''
		self.gzip      = False
		self.path      = u''
		self.resource  = resource
		self.session   = None
		self.authRealm = 'OPSI Service'

	def process(self):
		logger.info(u"Worker %s started processing" % self)
		deferred = defer.Deferred()
		deferred.addCallback(self._getSession)
		deferred.addCallback(self._authenticate)
		deferred.addCallback(self._getQuery)
		deferred.addCallback(self._processQuery)
		deferred.addCallback(self._setResponse)
		deferred.addCallback(self._setCookie)
		deferred.addCallback(self._freeSession)
		deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _getSessionHandler(self):
		if hasattr(self.service, '_getSessionHandler'):
			return self.service._getSessionHandler()
		return None

	def _delayResult(self, seconds, result):
		class DelayResult:
			def __init__(self, seconds, result):
				self.result = result
				self.deferred = defer.Deferred()
				reactor.callLater(seconds, self.returnResult)

			def returnResult(self):
				self.deferred.callback(self.result)
		return DelayResult(seconds, result).deferred

	def _errback(self, failure):
		logger.debug2("%s._errback" % self.__class__.__name__)

		self._freeSession(failure)

		result = self._renderError(failure)
		result = self._setCookie(result)
		result.code = responsecode.INTERNAL_SERVER_ERROR
		try:
			failure.raiseException()
		except OpsiAuthenticationError as e:
			logger.logException(e)
			result.code = responsecode.UNAUTHORIZED
			result.headers.setHeader('www-authenticate', [('basic', { 'realm': self.authRealm } )])
		except OpsiBadRpcError as e:
			logger.logException(e)
			result.code = responsecode.BAD_REQUEST
		except Exception as e:
			logger.logException(e, LOG_ERROR)
			logger.error(failure)
		return result

	def _renderError(self, failure):
		result = http.Response()
		result.headers.setHeader('content-type', http_headers.MimeType("text", "html", {"charset": "utf-8"}))
		error = u'Unknown error'
		try:
			failure.raiseException()
		except Exception as e:
			error = forceUnicode(e)
		result.stream = stream.IByteStream(stream.IByteStream(error.encode('utf-8')))
		return result

	def _freeSession(self, result):
		if self.session:
			logger.debug(u"Freeing session %s" % self.session)
			self.session.decreaseUsageCount()
		return result

	def _getAuthorization(self):
		(user, password) = (u'', u'')
		logger.debug(u"Trying to get username and password from Authorization header")
		auth = self.request.headers.getHeader('Authorization')
		if auth:
			logger.debug(u"Authorization header found (type: %s)" % auth[0])
			try:
				encoded = auth[1]

				logger.confidential(u"Auth encoded: %s" % encoded)
				parts = unicode(base64.decodestring(encoded), 'latin-1').split(':')
				if (len(parts) > 6):
					user = u':'.join(parts[:6])
					password = u':'.join(parts[6:])
				else:
					user = parts[0]
					password = u':'.join(parts[1:])
				user = user.strip()
				logger.confidential(u"Client supplied username '%s' and password '%s'" % (user, password))
			except Exception as e:
				logger.error(u"Bad Authorization header from '%s': %s" % (self.request.remoteAddr.host, e))
		return (user, password)

	def _getCredentials(self):
		return self._getAuthorization()

	def _getUserAgent(self):
		# Get user agent
		userAgent = None
		try:
			userAgent = self.request.headers.getHeader('user-agent')
		except Exception:
			logger.info(u"Client '%s' did not supply user-agent" % self.request.remoteAddr.host)
		if not userAgent:
			userAgent = 'unknown'
		return userAgent

	def _getSessionId(self):
		# Get session id from cookie request header
		sessionId = u''
		try:
			for (k, v) in self.request.headers.getAllRawHeaders():
				if (k.lower() == 'cookie'):
					for cookie in v:
						for c in cookie.split(';'):
							if (c.find('=') == -1):
								continue
							(name, value) = c.split('=', 1)
							if (name.strip() == self._getSessionHandler().sessionName):
								sessionId = forceUnicode(value.strip())
								break
					break
		except Exception as e:
			logger.error(u"Failed to get cookie from header: %s" % e)
		return sessionId

	def _getSession(self, result):
		''' This method restores a session or generates a new one. '''
		self.session = None

		logger.confidential(u"Request headers: %s " % self.request.headers)

		userAgent = self._getUserAgent()

		# Get session handler
		sessionHandler = self._getSessionHandler()

		# Get session id from cookie request header
		sessionId = self._getSessionId()

		# Get Session object
		if self.request.headers.hasHeader("x-forwarded-for"):
			#overloading request because proxy detected
			self.request.remoteAddr.host = self.request.headers.getRawHeaders("x-forwarded-for")[0]

		self.session = sessionHandler.getSession(sessionId, self.request.remoteAddr.host)
		if (sessionId == self.session.uid):
			logger.info(u"Reusing session for client '%s', application '%s'" % (self.request.remoteAddr.host, userAgent))
		elif sessionId:
			logger.notice(u"Application '%s' on client '%s' supplied non existing session id: %s" % (userAgent, self.request.remoteAddr.host, sessionId))

		if sessionHandler and self.session.ip and (self.session.ip != self.request.remoteAddr.host):
			logger.critical(u"Client ip '%s' does not match session ip '%s', deleting old session and creating a new one" \
				% (self.request.remoteAddr.host, self.session.ip) )
			sessionHandler.deleteSession(self.session.uid)
			self.session = sessionHandler.getSession()

		# Set ip
		if self.request.headers.hasHeader("x-forwarded-for"):
			self.session.ip = self.request.headers.getRawHeaders("x-forwarded-for")[0]
		else:
			self.session.ip = self.request.remoteAddr.host

		# Set user-agent / application
		if self.session.userAgent and (self.session.userAgent != userAgent):
			logger.warning(u"Application changed from '%s' to '%s' for existing session of client '%s'" \
				% (self.session.userAgent, userAgent, self.request.remoteAddr.host))
		self.session.userAgent = userAgent

		logger.confidential(u"Session id is '%s' for client '%s', application '%s'" \
			% (self.session.uid, self.request.remoteAddr.host, self.session.userAgent))

		logger.confidential(u"Session content: %s" % self.session.__dict__)
		return result

	def _setCookie(self, result):
		logger.debug(u"%s._setCookie" % self)
		if not self.session:
			return result

		# Add cookie to headers
		cookie = http_headers.Cookie(self.session.name.encode('ascii', 'replace'), self.session.uid.encode('ascii', 'replace'), path='/')
		if not isinstance(result, http.Response):
			result = http.Response()
		result.headers.setHeader('set-cookie', [ cookie ] )
		return result

	def _authenticate(self, result):
		''' This function tries to authenticate a user.
		    Raises an exception on authentication failure. '''
		if self.session.authenticated:
			return result

		try:
			# Get authorization
			(self.session.user, self.session.password) = self._getCredentials()
			self.session.authenticated = True
		except Exception as e:
			logger.logException(e, LOG_INFO)
			self._freeSession(result)
			self._getSessionHandler().deleteSession(self.session.uid)
			raise OpsiAuthenticationError(u"Forbidden: %s" % e)
		return result

	def _getQuery(self, result):
		self.query = ''
		if   (self.request.method == 'GET'):
			self.query = urllib.unquote( self.request.querystring )
		elif (self.request.method == 'POST'):
			# Returning deferred needed for chaining
			d = stream.readStream(self.request.stream, self._handlePostData)
			return d
		else:
			raise ValueError(u"Unhandled method '%s'" % self.request.method)
		return result

	def _handlePostData(self, chunk):
		self.query += chunk

	def _decodeQuery(self, result):
		try:
			if (self.request.method == 'POST'):
				contentType = self.request.headers.getHeader('content-type')
				contentEncoding = None
				try:
					contentEncoding = self.request.headers.getHeader('content-encoding')[0].lower()
				except:
					pass
				logger.debug(u"Content-Type: %s, Content-Encoding: %s" % (contentType, contentEncoding))
				if (contentEncoding == 'gzip') or (contentType and contentType.mediaType.startswith('gzip')):
					logger.debug(u"Expecting compressed data from client")
					self.query = zlib.decompress(self.query)
					self.gzip = True
			self.query = unicode(self.query, 'utf-8')
		except (UnicodeError, UnicodeEncodeError):
			self.query = unicode(self.query, 'utf-8', 'replace')
		logger.debug2(u"query: %s" % self.query)
		return result

	def _processQuery(self, result):
		logger.warning(u"Class %s should overwrite _processQuery" % self.__class__.__name__)
		return self._decodeQuery(result)

	def _generateResponse(self, result):
		if not isinstance(result, http.Response):
			result = http.Response()
		result.code = responsecode.OK
		result.headers.setHeader('content-type', http_headers.MimeType("text", "html", {"charset": "utf-8"}))
		result.stream = stream.IByteStream("")
		return result

	def _setResponse(self, result):
		return self._generateResponse(result)


class WorkerOpsiJsonRpc(WorkerOpsi):
	def __init__(self, service, request, resource):
		WorkerOpsi.__init__(self, service, request, resource)

		self._callInstance = None
		self._callInterface = None
		self._rpcs = []

	def _getCallInstance(self, result):
		logger.warning(u"Class %s should overwrite _getCallInstance" % self.__class__.__name__)
		self._callInstance = None
		self._callInterface = None

	def _getRpcs(self, result):
		if not self.query:
			return result
		if not self._callInstance:
			raise Exception(u"Call instance not defined in %s" % self)
		if not self._callInterface:
			raise Exception(u"Call interface not defined in %s" % self)

		rpcs = []
		try:
			rpcs = fromJson(self.query, preventObjectCreation = True)
			if not rpcs:
				raise Exception(u"Got no rpcs")
		except Exception as e:
			raise OpsiBadRpcError(u"Failed to decode rpc: %s" % e)

		for rpc in forceList(rpcs):
			rpc = JsonRpc(instance = self._callInstance, interface = self._callInterface, rpc = rpc)
			self._rpcs.append(rpc)

		return result

	def _executeRpc(self, result, rpc):
		deferred = threads.deferToThread(rpc.execute)
		return deferred

	def _executeRpcs(self, result):
		deferred = defer.Deferred()
		for rpc in self._rpcs:
			deferred.addCallback(self._executeRpc, rpc)
		#deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _processQuery(self, result):
		deferred = defer.Deferred()
		deferred.addCallback(self._decodeQuery)
		deferred.addCallback(self._getCallInstance)
		deferred.addCallback(self._getRpcs)
		deferred.addCallback(self._executeRpcs)
		#deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _generateResponse(self, result):
		if not isinstance(result, http.Response):
			result = http.Response()
		result.code = responsecode.OK

		encoding = None
		try:
			if ('deflate' in self.request.headers.getHeader('Accept-Encoding')):
				encoding = 'deflate'
			if ('gzip' in self.request.headers.getHeader('Accept-Encoding')):
				encoding = 'gzip'
		except Exception as e:
			pass
		if not encoding:
			try:
				if self.request.headers.getHeader('Accept'):
					for accept in self.request.headers.getHeader('Accept').keys():
						if accept.mediaType.startswith('gzip'):
							encoding = 'gzip'
							break
			except Exception as e:
				logger.error(u"Failed to get accepted mime types from header: %s" % e)

		if encoding:
			result.headers.setHeader('content-type', http_headers.MimeType("gzip-application", "json", {"charset": "utf-8"}))
			result.headers.setHeader('content-encoding', [encoding])
		else:
			result.headers.setHeader('content-type', http_headers.MimeType("application", "json", {"charset": "utf-8"}))

		response = []

		for rpc in self._rpcs:
			response.append(serialize(rpc.getResponse()))
		if (len(response) == 1):
			response = response[0]
		if not response:
			response = None

		if encoding:
			# level 1 (fastest) to 9 (most compression)
			level = 1
			logger.debug(u"Sending compressed (level: %d) data" % level)
			result.stream = stream.IByteStream(zlib.compress(toJson(response).encode('utf-8'), level))
		else:
			result.stream = stream.IByteStream(toJson(response).encode('utf-8'))
		return result

	def _renderError(self, failure):
		result = http.Response()
		result.headers.setHeader('content-type', http_headers.MimeType("text", "html", {"charset": "utf-8"}))
		error = u'Unknown error'
		try:
			failure.raiseException()
		except Exception as e:
			error = {'class': e.__class__.__name__, 'message': unicode(e)}
			error = toJson({"id": None, "result": None, "error": error})
		result.stream = stream.IByteStream(error.encode('utf-8'))
		return result


class MultiprocessWorkerOpsiJsonRpc(WorkerOpsiJsonRpc):

	def _processQuery(self, result):

		logger.debug(u"Using multiprocessing to handle rpc.")



		def cleanup(rpc):
			if (rpc.getMethodName() == 'backend_exit'):
				logger.notice(u"User '%s' asked to close the session" % self.session.user)
				self._freeSession(result)
				self.service._getSessionHandler().deleteSession(self.session.uid)

		def processResult(rpcs):
			self._rpcs = rpcs

			for rpc in rpcs:
				cleanup(rpc)
				self._addRpcToStatistics(None, rpc)
				self.session.setLastRpcMethod(rpc.getMethodName())
			return rpcs

		def makeInstanceCall():
			contentType = self.request.headers.getHeader('content-type')
			contentEncoding = None
			try:
				contentEncoding = self.request.headers.getHeader('content-encoding')[0].lower()
			except:
				pass
			d = self._callInstance.processQuery(self.query,
				(contentEncoding == 'gzip') or (contentType and contentType.mediaType.startswith('gzip')))
			d.addCallback(processResult)
			return d

		deferred = self._getCallInstance(None)
		deferred.addCallback(lambda x: makeInstanceCall())

		return deferred


class WorkerOpsiJsonInterface(WorkerOpsiJsonRpc):
	def __init__(self, service, request, resource):
		WorkerOpsiJsonRpc.__init__(self, service, request, resource)

	def _generateResponse(self, result):
		logger.info(u"Creating interface page")

		javascript  = u"var currentParams = new Array();\n"
		javascript += u"var currentMethod = null;\n"
		currentMethod = u''
		if self._rpcs:
			currentMethod = self._rpcs[0].getMethodName()
			javascript += u"currentMethod = '%s';\n" % currentMethod
			for i in range(len(self._rpcs[0].params)):
				param = self._rpcs[0].params[i]
				javascript += u"currentParams[%d] = '%s';\n" % (i, toJson(param))

		selectMethod = u''
		for method in self._callInterface:
			javascript += u"parameters['%s'] = new Array();\n" % (method['name'])
			for param in range(len(method['params'])):
				javascript += u"parameters['%s'][%s]='%s';\n" % (method['name'], param, method['params'][param])
			selected = u''
			if (method['name'] == currentMethod):
				selected = u' selected="selected"'
			selectMethod += u'<option%s>%s</option>' % (selected, method['name'])

		resultDiv = u'<div id="result">'
		if isinstance(result, failure.Failure):
			error = u'Unknown error'
			try:
				result.raiseException()
			except Exception as e:
				error = {'class': e.__class__.__name__, 'message': unicode(e)}
				error = toJson({"id": None, "result": None, "error": error})
			resultDiv += u'<div class="json">'
			resultDiv += objectToHtml(error)
			resultDiv += u'</div>'
		else:
			for rpc in self._rpcs:
				resultDiv += u'<div class="json">'
				resultDiv += objectToHtml(serialize(rpc.getResponse()))
				resultDiv += u'</div>'
		resultDiv += u'</div>'

		html = interfacePage % {
			'path':          self.path,
			'title':         u'opsi interface page',
			'javascript':    javascript,
			'select_path':   u'<option selected="selected">%s</option>' % self.path,
			'select_method': selectMethod,
			'result':        resultDiv
		}

		if not isinstance(result, http.Response):
			result = http.Response()
		result.code = responsecode.OK
		result.stream = stream.IByteStream(html.encode('utf-8').strip())

		return result

	def _renderError(self, failure):
		return self._generateResponse(failure)


class WorkerOpsiDAV(WorkerOpsi):
	def __init__(self, service, request, resource):
		WorkerOpsi.__init__(self, service, request, resource)

	def process(self):
		logger.debug(u"Worker %s started processing" % self)
		deferred = defer.Deferred()
		if self.resource._authRequired:
			deferred.addCallback(self._getSession)
			deferred.addCallback(self._authenticate)
		deferred.addCallback(self._setResponse)
		if self.resource._authRequired:
			deferred.addCallback(self._setCookie)
			deferred.addCallback(self._freeSession)
		deferred.addErrback(self._errback)
		deferred.callback(None)
		return deferred

	def _setResponse(self, result):
		logger.debug(u"Client requests DAV operation: %s" % self.request)
		if not self.resource._authRequired and self.request.method not in ('GET', 'PROPFIND', 'OPTIONS', 'USERINFO', 'HEAD'):
			logger.critical(u"Method '%s' not allowed (read only)" % self.request.method)
			return http.Response(
				code	= responsecode.FORBIDDEN,
				stream	= "Readonly!" )

		return self.resource.renderHTTP_super(self.request, self)
