#!/usr/bin/env python
#-*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2015 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Testing the workers.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

import unittest
import zlib

from OPSI.Service.Worker import WorkerOpsiJsonRpc


class FakeHeader(object):
	def __init__(self, headers=None):
		self.headers = headers or {}

	def hasHeader(self, header):
		return header in self.headers

	def getHeader(self, header):
		return self.headers[header]


class FakeRequest(object):
	def __init__(self, headers=None):
		self.headers = headers or FakeHeader()


class FakeRPC(object):
			def __init__(self, result=None):
				self.result = result or None

			def getResponse(self):
				return self.result


class WorkerOpsiJsonRpcTestCase(unittest.TestCase):

	def testReturningEmptyResponse(self):
		"""
		Making sure that an empty uncompressed response is returned.

		We check the headers of the request and also make sure that
		the content is "null".
		"""
		worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertFalse(result.headers.hasHeader('content-encoding'))
		self.assertEquals('null', str(result.stream.read()))

	def testHandlingMultipleRPCs(self):
		"""
		With multiple RPCs the results are returned in a list.

		We do not use any compression in this testcase.
		"""
		class FakeRPC(object):
			def __init__(self, result=None):
				self.result = result or None

			def getResponse(self):
				return self.result

		worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
		worker._rpcs = [FakeRPC(), FakeRPC(1), FakeRPC(u"FÄKE!"),
						FakeRPC({"Narziss": "Morgen Nicht Geboren"})]

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertFalse(result.headers.hasHeader('content-encoding'))
		self.assertEquals('[null, 1, "F\xc3\x84KE!", {"Narziss": "Morgen Nicht Geboren"}]', str(result.stream.read()))

	def testHandlingSingleResult(self):
		"""
		A single RPC result must not be returned in a list.
		"""
		worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
		worker._rpcs = [FakeRPC("Hallo Welt")]

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertFalse(result.headers.hasHeader('content-encoding'))
		self.assertEquals('"Hallo Welt"', str(result.stream.read()))

	def testHandlingSingleResultConsistingOfList(self):
		"""
		If a single result is made the result is a list this list must not be unpacked.
		"""
		worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
		worker._rpcs = [FakeRPC(["Eins", "Zwei", "Drei"])]

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertFalse(result.headers.hasHeader('content-encoding'))
		self.assertEquals('["Eins", "Zwei", "Drei"]', str(result.stream.read()))


class CompressedResultsWithWorkerOpsiJsonRpcTestCase(unittest.TestCase):
	def testCompressingResponseDataWithGzip(self):
		"""
		Responding with data compressed by gzip.

		Problem here is that even though the accepted encoding is stated
		as "gzip" the returned result is compressed via zlib as it is
		expected when specifying "deflate".
		"""
		testHeader = FakeHeader({"Accept-Encoding": "gzip"})
		request = FakeRequest(testHeader)
		worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['gzip-application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertEquals(['gzip'], result.headers.getRawHeaders('content-encoding'))

		sdata = result.stream.read()
		data = zlib.decompress(sdata)
		self.assertEquals('null', data)

	def testCompressingResponseDataWithDeflate(self):
		"""
		Responding with data compressed by deflate.

		The returned "content-type" is invalid and makes no sense.
		Correct would be "application/json".
		"""
		testHeader = FakeHeader({"Accept-Encoding": "deflate"})
		request = FakeRequest(testHeader)
		worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['gzip-application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))
		self.assertEquals(['deflate'], result.headers.getRawHeaders('content-encoding'))

		sdata = result.stream.read()
		data = zlib.decompress(sdata)
		self.assertEquals('null', data)


class BackwardsCompatibilityWorkerJSONRPCTestCase(unittest.TestCase):
	def testCompressingResponseIfInvalidMimetype(self):
		"""
		Old clients connect to the server and send an "Accept" with
		the invalid mimetype "gzip-application/json-rpc".
		We must respond to these clients because not doing so could
		result in rendering an opsi landscape unresponding.

		The returned "content-type" is invalid and makes no sense.
		Correct would be "application/json".
		"""
		class FakeDictHeader(FakeHeader):
			def getHeader(self, header):
				class ReturnWithMediaType:
					def __init__(self, key):
						self.mediaType = key

				return dict((ReturnWithMediaType(self.headers[key]), self.headers[key]) for key in self.headers if key.startswith(header))


		testHeader = FakeDictHeader(
			{"Accept": "gzip-application/json-rpc",
			 "invalid": "ignoreme"})
		request = FakeRequest(testHeader)
		worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

		result = worker._generateResponse(None)
		self.assertTrue(200, result.code)
		self.assertTrue(result.headers.hasHeader('content-type'))
		self.assertEquals(['gzip'], result.headers.getRawHeaders('content-encoding'))
		self.assertEquals(['gzip-application/json;charset=utf-8'], result.headers.getRawHeaders('content-type'))

		sdata = result.stream.read()
		data = zlib.decompress(sdata)
		self.assertEquals('null', data)


if __name__ == '__main__':
	unittest.main()
