#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - HTTP    =
   = = = = = = = = = = = = = = = = = =

   This module is part of the desktop management solution opsi
   Based on urllib3
   (open pc server integration) http://www.opsi.org

   Copyright (C) 2010 Andrey Petrov
   Copyright (C) 2010-2014 uib GmbH

   http://www.uib.de/

   All rights reserved.

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License version 2 as
   published by the Free Software Foundation.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

   @copyright:	uib GmbH <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

import base64
import os
import random
import re
import socket
import time
from Queue import Queue, Empty, Full
from httplib import HTTPConnection, HTTPSConnection, HTTPException
from socket import error as SocketError, timeout as SocketTimeout
import ssl as ssl_module
from OpenSSL import crypto

from OPSI.Types import *
from OPSI.Logger import LOG_DEBUG, LOG_INFO, Logger
from OPSI.Util import encryptWithPublicKeyFromX509CertificatePEMFile, randomString
logger = Logger()


connectionPools = {}
totalRequests = 0

# This could be an import - but support for pycurl is currently not fully implrement
pycurl = None

if hasattr(ssl_module, '_create_unverified_context'):
      ssl_module._create_default_https_context = ssl_module._create_unverified_context


def hybi10Encode(data):
	# Code stolen from http://lemmingzshadow.net/files/2011/09/Connection.php.txt
	frame = [0x81]
	mask = [
		random.randint(0, 255), random.randint(0, 255),
		random.randint(0, 255), random.randint(0, 255)
	]
	dataLength = len(data)

	if dataLength <= 125:
		frame.append(dataLength + 128)
	else:
		frame.append(254)
		frame.append(dataLength >> 8)
		frame.append(dataLength & 0xff)

	frame.extend(mask)
	for i in range(len(data)):
		frame.append(ord(data[i]) ^ mask[i % 4])

	encodedData = ''
	for i in range(len(frame)):
		encodedData += chr(frame[i])
	return encodedData


def hybi10Decode(data):
	if len(data.strip()) < 2:
		return ''
	# Code stolen from http://lemmingzshadow.net/files/2011/09/Connection.php.txt
	mask = ''
	codedData = ''
	decodedData = ''
	secondByte = bin(ord(data[1]))[2:]
	masked = False
	dataLength = ord(data[1])

	if secondByte[0] == '1':
		masked = True
		dataLength = ord(data[1]) & 127

	if masked:
		if dataLength == 126:
			mask = data[4:8]
			codedData = data[8:]
		elif dataLength == 127:
			mask = data[10:14]
			codedData = data[14:]
		else:
			mask = data[2:6]
			codedData = data[6:]
		for i in range(len(codedData)):
			decodedData += chr( ord(codedData[i]) ^ ord(mask[i % 4]) )
	else:
		if dataLength == 126:
			decodedData = data[4:]
		elif dataLength == 127:
			decodedData = data[10:]
		else:
			decodedData = data[2:]
	return decodedData


def non_blocking_connect_http(self, connectTimeout=0):
	''' Non blocking connect, needed for KillableThread '''
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	#sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
	#sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
	sock.settimeout(3.0)
	started = time.time()
	lastError = None
	while True:
		try:
			if connectTimeout > 0 and ((time.time() - started) >= connectTimeout):
				raise OpsiTimeoutError(u"Timed out after %d seconds (%s)" % (connectTimeout, forceUnicode(lastError)))
			sock.connect((self.host, self.port))
			break
		except socket.error as e:
			logger.logException(e, LOG_DEBUG)
			logger.debug(e)
			if e[0] in (106, 10056):
				# Transport endpoint is already connected
				break
			if e[0] not in (114, ) or not lastError:
				lastError = e
			time.sleep(0.5)
	sock.settimeout(None)
	self.sock = sock


def non_blocking_connect_https(self, connectTimeout=0, verifyByCaCertsFile=None):
	non_blocking_connect_http(self, connectTimeout)
	if verifyByCaCertsFile:
		self.sock = ssl_module.wrap_socket(self.sock, keyfile=self.key_file, certfile=self.cert_file, cert_reqs=ssl_module.CERT_REQUIRED, ca_certs=verifyByCaCertsFile)
		logger.debug(u"Server verified by CA")
	else:
		self.sock = ssl_module.wrap_socket(self.sock, keyfile=self.key_file, certfile=self.cert_file, cert_reqs=ssl_module.CERT_NONE)


def getPeerCertificate(httpsConnectionOrSSLSocket, asPEM=True):
	try:
		sock = httpsConnectionOrSSLSocket
		if hasattr(sock, 'sock'):
			sock = sock.sock
		cert = crypto.load_certificate(crypto.FILETYPE_ASN1, sock.getpeercert(binary_form=True))
		if not asPEM:
			return cert
		return crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
	except Exception as e:
		logger.debug(u"Failed to get peer cert: %s" % e)
		return None


class HTTPError(Exception):
	"Base exception used by this module."
	pass


class TimeoutError(HTTPError):
	"Raised when a socket timeout occurs."
	pass


class HostChangedError(HTTPError):
	"Raised when an existing pool gets a request for a foreign host."
	pass


class HTTPResponse(object):
	"""
	HTTP Response container.

	Similar to httplib's HTTPResponse but the data is pre-loaded.
	"""
	def __init__(self, data='', headers={}, status=0, version=0, reason=None, strict=0):
		self.data    = data
		self.headers = headers
		self.status  = status
		self.version = version
		self.reason  = reason
		self.strict  = strict

	def addData(self, data):
		self.data += data

	def curlHeader(self, header):
		header = header.strip()
		if header.upper().startswith('HTTP'):
			try:
				(version, status, reason) = header.split(None, 2)
				self.version = 9
				if version == 'HTTP/1.0':
					self.version = 10
				elif version.startswith('HTTP/1.'):
					self.version = 11
				self.status = int(status.strip())
				self.reason = reason.strip()
			except Exception:
				pass
		elif header.count(':') > 0:
			(k, v) = header.split(':', 1)
			k = k.lower().strip()
			v = v.strip()
			if k == 'content-length':
				try:
					v = int(v)
					if v < 0:
						v = 0
				except:
					return
			self.headers[k] = v

	@staticmethod
	def from_httplib(r):
		"""
		Given an httplib.HTTPResponse instance, return a corresponding
		urllib3.HTTPResponse object.

		NOTE: This method will perform r.read() which will have side effects
		on the original http.HTTPResponse object.
		"""
		return HTTPResponse(
			data=r.read(),
			headers=dict(r.getheaders()),
			status=r.status,
			version=r.version,
			reason=r.reason,
			strict=r.strict
		)

	# Backwards-compatibility methods for httplib.HTTPResponse
	def getheaders(self):
		return self.headers

	def getheader(self, name, default=None):
		return self.headers.get(name, default)

class HTTPConnectionPool(object):

	scheme = 'http'

	def __init__(self, host, port, socketTimeout=None, connectTimeout=None, retryTime=0, maxsize=1, block=False, reuseConnection=False, verifyServerCert=False, serverCertFile=None, caCertFile=None, verifyServerCertByCa=False):

		self.host                 = forceUnicode(host)
		self.port                 = forceInt(port)
		self.socketTimeout        = forceInt(socketTimeout or 0)
		self.connectTimeout       = forceInt(connectTimeout or 0)
		self.retryTime            = forceInt(retryTime)
		self.block                = forceBool(block)
		self.reuseConnection      = forceBool(reuseConnection)
		self.pool                 = None
		self.usageCount           = 1
		self.num_connections      = 0
		self.num_requests         = 0
		self.httplibDebugLevel    = 0
		self.peerCertificate      = None
		self.serverVerified       = False
		self.verifyServerCert     = False
		self.serverCertFile       = None
		self.caCertFile           = None
		self.verifyServerCertByCa = False

		if isinstance(self, HTTPSConnectionPool):
			if self.host in ('localhost', '127.0.0.1'):
				self.serverVerified = True
				logger.debug(u"No host verification for localhost")
			else:
				if caCertFile:
					self.caCertFile = forceFilename(caCertFile)
				self.verifyServerCertByCa = forceBool(verifyServerCertByCa)

				if self.verifyServerCertByCa:
					if not self.caCertFile:
						raise Exception(u"Server certificate verfication by CA enabled but no CA cert file given")
					logger.info(u"Server certificate verfication by CA file '%s' enabled for host '%s'" % (self.caCertFile, self.host))
				else:
					self.verifyServerCert = forceBool(verifyServerCert)
					if serverCertFile:
						self.serverCertFile = forceFilename(serverCertFile)
					if self.verifyServerCert:
						if not self.serverCertFile:
							raise Exception(u"Server verfication enabled but no server cert file given")
						logger.info(u"Server verfication by server certificate enabled for host '%s'" % self.host)
		self.adjustSize(maxsize)

	def increaseUsageCount(self):
		self.usageCount += 1

	def decreaseUsageCount(self):
		self.usageCount -= 1
		if self.usageCount == 0:
			destroyPool(self)

	free = decreaseUsageCount

	def delPool(self):
		if self.pool:
			while True:
				try:
					conn = self.pool.get(block=False)
					if conn:
						try:
							if conn.sock:
								conn.sock.close()
							conn.close()
						except:
							pass
					time.sleep(0.001)
				except Empty:
					break

	def adjustSize(self, maxsize):
		if maxsize < 1:
			raise Exception(u"Connection pool size %d is invalid" % maxsize)
		self.maxsize = forceInt(maxsize)
		self.delPool()
		self.pool = Queue(self.maxsize)
		# Fill the queue up so that doing get() on it will block properly
		[self.pool.put(None) for i in xrange(self.maxsize)]

	def __del__(self):
		self.delPool()

	def _new_conn(self):
		"""
		Return a fresh HTTPConnection.
		"""
		self.num_connections += 1
		logger.debug(u"Starting new HTTP connection (%d) to %s:%d" % (self.num_connections, self.host, self.port))
		conn = HTTPConnection(host=self.host, port=self.port)
		non_blocking_connect_http(conn, self.connectTimeout)
		logger.debug(u"Connection established to: %s" % self.host)
		return conn

	def _get_conn(self, timeout=None):
		"""
		Get a connection. Will return a pooled connection if one is available.
		Otherwise, a fresh connection is returned.
		"""
		conn = None
		try:
			conn = self.pool.get(block=self.block, timeout=timeout)
		except Empty:
			pass  # Oh well, we'll create a new connection then

		return conn or self._new_conn()

	def _put_conn(self, conn):
		"""
		Put a connection back into the pool.
		If the pool is already full, the connection is discarded because we
		exceeded maxsize. If connections are discarded frequently, then maxsize
		should be increased.
		"""
		try:
			self.pool.put(conn, block=False)
			if conn is None:
				self.num_connections -= 1
		except Full:
			# This should never happen if self.block == True
			logger.warning(u"HttpConnectionPool is full, discarding connection: %s" % self.host)

	def is_same_host(self, url):
		return url.startswith('/') or get_host(url) == (self.scheme, self.host, self.port)

	def getPeerCertificate(self, asPem=False):
		if not self.peerCertificate:
			return None
		if asPem:
			return self.peerCertificate
		return crypto.load_certificate(crypto.FILETYPE_PEM, self.peerCertificate)

	def getConnection(self):
		return self._get_conn()

	def endConnection(self, conn):
		if conn:
			httplib_response = conn.getresponse()
			response = HTTPResponse.from_httplib(httplib_response)
			if self.reuseConnection:
				self._put_conn(conn)
			else:
				self._put_conn(None)
			return response
		self._put_conn(None)
		return None

	def urlopen(self, method, url, body=None, headers={}, retry=True, redirect=True, assert_same_host=True, firstTryTime=None):
		"""
		Get a connection from the pool and perform an HTTP request.

		method
			HTTP request method (such as GET, POST, PUT, etc.)

		body
			Data to send in the request body (useful for creating POST requests,
			see HTTPConnectionPool.post_url for more convenience).

		headers
			Custom headers to send (such as User-Agent, If-None-Match, etc.)

		retry
			Retry on connection failure in between self.retryTime seconds

		redirect
			Automatically handle redirects (status codes 301, 302, 303, 307),
			each redirect counts as a retry.
		"""
		now = time.time()
		if not firstTryTime:
			firstTryTime = now

		conn = None
		# Check host
		if assert_same_host and not self.is_same_host(url):
			host = "%s://%s" % (self.scheme, self.host)
			if self.port:
				host = "%s:%d" % (host, self.port)
			raise HostChangedError(u"Connection pool with host '%s' tried to open a foreign host: %s" % (host, url))

		try:
			# Request a connection from the queue
			conn = self._get_conn()

			if self.httplibDebugLevel:
				conn.set_debuglevel(self.httplibDebugLevel)

			# Make the request
			self.num_requests += 1

			global totalRequests
			totalRequests += 1
			#logger.essential("totalRequests: %d" % totalRequests)

			randomKey = None
			if isinstance(self, HTTPSConnectionPool) and self.verifyServerCert and not self.serverVerified:
				try:
					logger.info(u"Encoding authorization")
					randomKey = randomString(32).encode('latin-1')
					encryptedKey = encryptWithPublicKeyFromX509CertificatePEMFile(randomKey, self.serverCertFile)
					headers['X-opsi-service-verification-key'] = base64.encodestring(encryptedKey)
					for (key, value) in headers.items():
						if (key.lower() == 'authorization'):
							if value.lower().startswith('basic'):
								value = value[5:].strip()
							value = base64.decodestring(value).strip()
							encodedAuth = encryptWithPublicKeyFromX509CertificatePEMFile(value, self.serverCertFile)
							headers[key] = 'Opsi ' + base64.encodestring(encodedAuth).strip()
				except Exception as e:
					logger.logException(e, LOG_INFO)
					logger.critical(u"Cannot verify server based on certificate file '%s': %s" % (self.serverCertFile, e))
					randomKey = None

			conn.request(method, url, body=body, headers=headers)
			if self.socketTimeout:
				conn.sock.settimeout(self.socketTimeout)
			else:
				conn.sock.settimeout(None)
			httplib_response = conn.getresponse()
			#logger.debug(u"\"%s %s %s\" %s %s" % (method, url, conn._http_vsn_str, httplib_response.status, httplib_response.length))

			# from_httplib will perform httplib_response.read() which will have
			# the side effect of letting us use this connection for another
			# request.
			response = HTTPResponse.from_httplib(httplib_response)

			if randomKey:
				try:
					key = response.getheader('x-opsi-service-verification-key', None)
					if not key:
						raise Exception(u"HTTP header 'X-opsi-service-verification-key' missing")
					if (key.strip() != randomKey.strip()):
						raise Exception(u"opsi-service-verification-key '%s' != '%s'" % (key, randomKey))
					self.serverVerified = True
					logger.notice(u"Service verified by opsi-service-verification-key")
				except Exception as e:
					logger.error(u"Service verification failed: %s" % e)
					raise OpsiServiceVerificationError(u"Service verification failed: %s" % e)

			if self.serverCertFile and self.peerCertificate:
				try:
					certDir = os.path.dirname(self.serverCertFile)
					if not os.path.exists(certDir):
						os.makedirs(certDir)
					f = open(self.serverCertFile, 'w')
					f.write(self.peerCertificate)
					f.close()
				except Exception as e:
					logger.error(u"Failed to create server cert file '%s': %s" % (self.serverCertFile, e))

			# Put the connection back to be reused
			if self.reuseConnection:
				self._put_conn(conn)
			else:
				logger.debug(u"Closing connection: %s" % conn)
				self._put_conn(None)
				try:
					if conn.sock:
						conn.sock.close()
					conn.close()
				except:
					pass

		except (SocketTimeout, Empty, HTTPException, SocketError) as e:
			try:
				logger.debug(u"Request to host '%s' failed, retry: %s, firstTryTime: %s, now: %s, retryTime: %s, connectTimeout: %s, socketTimeout: %s (%s)" \
					% (self.host, retry, firstTryTime, now, self.retryTime, self.connectTimeout, self.socketTimeout, forceUnicode(e)))
			except:
				try:
					logger.debug(u"Request to host '%s' failed, retry: %s, firstTryTime: %s, now: %s, retryTime: %s, connectTimeout: %s, socketTimeout: %s" \
						% (self.host, retry, firstTryTime, now, self.retryTime, self.connectTimeout, self.socketTimeout))
				except:
					pass

			self._put_conn(None)
			try:
				if conn:
					if conn.sock:
						conn.sock.close()
					conn.close()
			except:
				pass
			if retry and (now - firstTryTime < self.retryTime):
				logger.debug(u"Request to '%s' failed: %s, retrying" % (self.host, forceUnicode(e)))
				time.sleep(0.1)
				return self.urlopen(method, url, body, headers, retry, redirect, assert_same_host, firstTryTime)
			else:
				raise
		except Exception:
			self._put_conn(None)
			try:
				if conn:
					if conn.sock:
						conn.sock.close()
					conn.close()
			except:
				pass
			raise

		# Handle redirection
		if redirect and response.status in (301, 302, 303, 307) and 'location' in response.headers: # Redirect, retry
			logger.info(u"Redirecting %s -> %s" % (url, response.headers.get('location')))
			time.sleep(0.1)
			self._put_conn(None)
			try:
				if conn:
					if conn.sock:
						conn.sock.close()
					conn.close()
			except:
				pass
			return self.urlopen(method, url, body, headers, retry, redirect, assert_same_host, firstTryTime)

		return response


class HTTPSConnectionPool(HTTPConnectionPool):
	"""
	Same as HTTPConnectionPool, but HTTPS.
	"""

	scheme = 'https'

	def _new_conn(self):
		"""
		Return a fresh HTTPSConnection.
		"""
		logger.debug(u"Starting new HTTPS connection (%d) to %s:%d" % (self.num_connections, self.host, self.port))
		conn = HTTPSConnection(host = self.host, port = self.port)
		if self.verifyServerCert or self.verifyServerCertByCa:
			try:
				non_blocking_connect_https(conn, self.connectTimeout, self.caCertFile)
				if not self.verifyServerCertByCa:
					self.serverVerified = True
			except Exception as e:
				logger.debug(e)
				if (e.__class__.__name__ != 'SSLError') or self.verifyServerCertByCa:
					raise OpsiServiceVerificationError(u"Failed to verify server cert by CA: %s" % e)
				non_blocking_connect_https(conn, self.connectTimeout)

		logger.debug(u"Connection established to: %s" % self.host)
		self.num_connections += 1
		self.peerCertificate = getPeerCertificate(conn, asPEM=True)
		if self.verifyServerCertByCa:
			try:
				if self.peerCertificate:
					commonName = crypto.load_certificate(crypto.FILETYPE_PEM, self.peerCertificate).get_subject().commonName
					host = self.host
					if re.search('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', host):
						fqdn = socket.getfqdn(host)
						if fqdn == host:
							raise Exception(u"Failed to get fqdn for ip %s" % host)
						host = fqdn
					if not host or not commonName or (host.lower() != commonName.lower()):
						raise Exception(u"Host '%s' does not match common name '%s'" % (host, commonName))
					self.serverVerified = True
				else:
					raise Exception(u"Failed to get peer certificate")
			except Exception:
				if conn.sock:
					conn.sock.close()
				conn.close()
				raise
		return conn


def urlsplit(url):
	url = forceUnicode(url)
	scheme = None
	baseurl = u'/'
	port = None
	username = None
	password = None
	if url.find('://') != -1:
		(scheme, url) = url.split('://', 1)
		scheme = scheme.lower()
	parts = url.split('/', 1)
	host = parts[0]
	if len(parts) > 1:
		baseurl += parts[1]
	if host.find('@') != -1:
		(username, host) = host.split('@', 1)
		if (username.find(':') != -1):
			(username, password) = username.split(':', 1)
	if host.find(':') != -1:
		(host, port) = host.split(':', 1)
		port = int(port)
	return (scheme, host, port, baseurl, username, password)


def getSharedConnectionPoolFromUrl(url, **kw):
	"""
	Given a url, return an HTTP(S)ConnectionPool instance of its host.

	This is a shortcut for not having to determine the host of the url
	before creating an HTTP(S)ConnectionPool instance.

	Passes on whatever kw arguments to the constructor of
	HTTP(S)ConnectionPool. (e.g. timeout, maxsize, block)
	"""
	(scheme, host, port, baseurl, username, password) = urlsplit(url)
	if not port:
		if scheme in ('https', 'webdavs'):
			port = 443
		else:
			port = 80
	return getSharedConnectionPool(scheme, host, port, **kw)


def getSharedConnectionPool(scheme, host, port, **kw):
	scheme = forceUnicodeLower(scheme)
	host = forceUnicode(host)
	port = forceInt(port)
	curl = False
	if 'preferCurl' in kw:
		if kw['preferCurl'] and pycurl is not None:
			curl = True
		del kw['preferCurl']
	global connectionPools
	if curl:
		poolKey = u'curl:%s:%d' % (host, port)
	else:
		poolKey = u'httplib:%s:%d' % (host, port)
	if not connectionPools.has_key(poolKey):
		if scheme in ('https', 'webdavs'):
			if curl:
				connectionPools[poolKey] = CurlHTTPSConnectionPool(host, port=port, **kw)
			else:
				connectionPools[poolKey] = HTTPSConnectionPool(host, port=port, **kw)
		else:
			if curl:
				connectionPools[poolKey] = CurlHTTPConnectionPool(host, port=port, **kw)
			else:
				connectionPools[poolKey] = HTTPConnectionPool(host, port=port, **kw)
	else:
		connectionPools[poolKey].increaseUsageCount()
		maxsize = kw.get('maxsize', 0)
		if maxsize > connectionPools[poolKey].maxsize:
			connectionPools[poolKey].adjustSize(maxsize)
	return connectionPools[poolKey]


def destroyPool(pool):
	global connectionPools
	for (k, p) in connectionPools.items():
		if (p == pool):
			del connectionPools[k]
			break


if (__name__ == '__main__'):
	pass

	#pool = HTTPSConnectionPool(host = 'download.uib.de', port = 443, connectTimeout=5, caCertFile = '/tmp/xxx', verifyServerCertByCa=True)
	#resp = pool.urlopen('GET', url = '/index.html', body=None, headers={"accept": "text/html", "user-agent": "test"})
	#print resp.data
	#time.sleep(5)
	#pool = CurlHTTPSConnectionPool(host = 'download.uib.de', port = 443, connectTimeout=5)
	#resp = pool.urlopen('GET', url = '/index.html', body=None, headers={"accept": "text/html", "user-agent": "test"})
	#print resp.data
	#pool = CurlHTTPConnectionPool(host = 'www.uib.de', port = 80, socketTimeout=None, connectTimeout=5, reuseConnection=True)
	#resp = pool.urlopen('GET', url = '/www/home/index.html', body=None, headers={"accept": "text/html", "user-agent": "test"})
	#print resp.headers
	#resp = pool.urlopen('GET', url = '/www/home/index.html', body=None, headers={"accept": "text/html", "user-agent": "test"})
	#print resp.data
	#print resp.headers
	#print resp.status
	#print resp.version
	#print resp.reason
	#print resp.strict
