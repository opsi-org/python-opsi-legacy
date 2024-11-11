# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Handling repositories.
"""

from html.parser import HTMLParser

from OPSI.Types import forceBool, forceUnicode, forceUnicodeList

__all__ = ("LinksExtractor", "ProductRepositoryInfo")


class ProductRepositoryInfo:  # pylint: disable=dangerous-default-value,too-many-instance-attributes,too-few-public-methods,too-many-arguments,too-many-locals
	def __init__(
		self,
		name,
		baseUrl,
		dirs=[],
		username="",
		password="",
		authcertfile="",
		authkeyfile="",
		opsiDepotId=None,
		autoInstall=False,
		autoUpdate=True,
		autoSetup=False,
		proxy=None,
		excludes=[],
		includes=[],
		active=False,
		autoSetupExcludes=[],
		verifyCert=False,
	):
		self.name = forceUnicode(name)
		self.baseUrl = forceUnicode(baseUrl)
		self.dirs = forceUnicodeList(dirs)
		self.excludes = excludes
		self.includes = includes
		self.username = forceUnicode(username)
		self.password = forceUnicode(password)
		self.authcertfile = forceUnicode(authcertfile)
		self.authkeyfile = forceUnicode(authkeyfile)
		self.autoInstall = autoInstall
		self.autoUpdate = autoUpdate
		self.autoSetup = autoSetup
		self.autoSetupExcludes = autoSetupExcludes
		self.opsiDepotId = opsiDepotId
		self.onlyDownload = None
		self.inheritProductProperties = None
		self.description = ""
		self.active = forceBool(active)
		self.verifyCert = forceBool(verifyCert)

		self.proxy = None
		if proxy:
			self.proxy = proxy
		if self.baseUrl.startswith("webdav"):
			self.baseUrl = f"http{self.baseUrl[6:]}"

	def getDownloadUrls(self):
		urls = set()
		for directory in self.dirs:
			if directory in ("", "/", "."):
				url = self.baseUrl
			else:
				url = f"{self.baseUrl}/{directory}"
			if not url.endswith("/"):
				url = f"{url}/"
			urls.add(url)
		return urls


class LinksExtractor(HTMLParser):  # pylint: disable=abstract-method
	def __init__(self):
		super().__init__()
		self.links = set()

	def handle_starttag(self, tag, attrs):
		if tag != "a":
			return

		for attr in attrs:
			if attr[0] != "href":
				continue
			link = attr[1]
			self.links.add(link)

	def getLinks(self):
		return self.links
