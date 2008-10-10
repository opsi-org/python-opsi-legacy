# -*- test-case-name: OPSI.web2.test.test_cgi,OPSI.web2.test.test_http -*-
# See LICENSE for details.

"""
Various backend channel implementations for web2.
"""
from OPSI.web2.channel.cgi import startCGI
from OPSI.web2.channel.scgi import SCGIFactory
from OPSI.web2.channel.http import HTTPFactory
from OPSI.web2.channel.fastcgi import FastCGIFactory

__all__ = ['startCGI', 'SCGIFactory', 'HTTPFactory', 'FastCGIFactory']
