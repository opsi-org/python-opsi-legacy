#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Text    =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2008 uib GmbH
   
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

__version__ = '0.1'

# Imports
import os, codecs

# OPSI imports
from OPSI.Logger import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                       CLASS TEXT FILE                                              =
# ======================================================================================================
class TextFile:
	def __init__(self, filename, encoding="ascii"):
		self._filename = filename
		self._dirname = os.path.dirname(self._filename)
		self._encoding = encoding
		self._fh = None
		self._lines = []
	
	def opened(self):
		return self._fh is not None
	
	def delete(self):
		os.unlink(self._filename)
	
	def open(self, mode='r'):
		if self.opened():
			raise IOError("File '%s' already opened" % self._filename)
		if os.path.exists(self._filename):
			fh = open(self._filename, 'rb')
			bom = fh.read(2)
			fh.close()
			if (bom == codecs.BOM):
				logger.debug("Encoding of file '%s' is utf-16" % self._filename)
				self._encoding = "utf-16"
		
		self._fh = codecs.open(self._filename, mode = mode, encoding = self._encoding)
	
	def close(self):
		if self.opened():
			res = self._fh.close()
			self._fh = None
			return res
	
	def write(self, data):
		if not self.opened():
			raise IOError("File '%s' is not opened for writing" % self._filename)
		self._fh.write(data)
		
	def read(self, length):
		if not self.opened():
			raise IOError("File '%s' is not opened for reading" % self._filename)
		return self._fh.read(length)
	
	def readlines(self):
		if not self.opened():
			raise IOError("File '%s' is not opened for reading" % self._filename)
		self._lines = self._fh.readlines()
	
	
