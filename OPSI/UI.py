#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - UI      =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2010 uib GmbH
   
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

__version__ = '4.0'


snackError = None

# Imports
import time, gettext, locale
from snack import *
import signal as ui_signal

# OPSI imports
from Logger import *
from OPSI.Types import *
from OPSI.Util.Message import MessageObserver, ProgressObserver

# Get Logger instance
logger = Logger()
encoding = locale.getpreferredencoding()

try:
	t = gettext.translation('python-opsi', '/usr/share/locale')
	_ = t.ugettext
except Exception, e:
	logger.error(u"Locale not found: %s" % e)
	def _(string):
		return string

def UIFactory(type = u''):
	type = forceUnicode(type)
	if   (type == u'snack' or type == u'SnackUI'):
		return SnackUI()
	
	elif (type == u'dummy' or type == u'UI'):
		return UI()
	
	try:
		return SnackUI()
	except Exception, e:
		logger.warning(u"Failed to create SnackUI: %s" % e)
		return UI()

class UI:
	def __init__(self):
		self.confidentialStrings = []
	
	def setConfidentialStrings(self, strings):
		strings = forceUnicodeList(strings)
		self.confidentialStrings = []
		for string in strings:
			self.addConfidentialString(string)
		
	def addConfidentialString(self, string):
		string = forceUnicode(string)
		if not string:
			raise ValueError(u"Cannot use empty string as confidential string")
		if string in self.confidentialStrings:
			return
		self.confidentialStrings.append(string)
		
	def getScreen(self):
		pass
	
	def refresh(self):
		pass
	
	def getWidth(self):
		return 0
	
	def getHeight(self):
		return 0
	
	def exit(self):
		pass
	
	def drawRootText(self, x=1, y=1, text=''):
		pass
	
	def showError(self, text, title=_(u'An error occured'), okLabel=_(u'OK'), width=-1, height=-1, seconds=0):
		pass
	
	def showMessage(self, text, title=_(u'Message'), okLabel=_(u'OK'), width=-1, height=-1, seconds=0):
		pass
	
	def createProgressBox(self, width=-1, height=-1, total=100, title=_(u'Progress'), text=u''):
		return ProgressBox(self)
	
	def createCopyProgressBox(self, width=-1, height=-1, total=100, title=_(u'Copy progress'), text=u''):
		return CopyProgressBox(self)
	
	def createDualProgressBox(self, width=-1, height=-1, total=100, title=_(u'Progress'), text=u''):
		return DualProgressBox(self)
	
	def createCopyDualProgressBox(self, width=-1, height=-1, total=100, title=_(u'Copy progress'), text=u''):
		return CopyDualProgressBox(self)
	
	def createMessageBox(self, width=-1, height=-1, title=_(u'Text'), text=u''):
		return MessageBox(self)
		
	def getMessageBox(self):
		return MessageBox(self)
	
	def getValue(self, width=-1, height=-1, title=_(u'Please type text'), default=u'', password=False, text=u'', okLabel=_(u'OK'), cancelLabel=_('Cancel')):
		return None
	
	def getSelection(self, entries, radio=False, width=-1, height=-1, title=_(u'Please select'), text=u'', okLabel=_(u'OK'), cancelLabel=_(u'Cancel')):
		return []
	
	def getValues(self, entries, width=-1, height=-1, title=_(u'Please fill in'), text=u'', okLabel=_(u'OK'), cancelLabel=_(u'Cancel')):
		return entries
	
	def yesno(self, text, title=_(u'Question'), okLabel=_(u'OK'), cancelLabel=_(u'Cancel'), width=-1, height=-1):
		return True
	
class MessageBox:
	def __init__(self, ui, width=0, height=0, title=_(u'Title'), text=u''):
		pass
	
	def show(self, seconds=0):
		pass
	
	def hide(self):
		pass
		
	def setText(self, text):
		pass
		
	def addText(self, text):
		pass
	

class ProgressBox(MessageBox):
	def __init__(self, ui, width=0, height=0, total=100, title=_(u'Title'), text=u''):
		pass
		
	def setState(self, state):
		pass

	def getState(self):
		pass

class CopyProgressBox(ProgressBox):
	pass

class DualProgressBox(MessageBox):
	def __init__(self, ui, width=0, height=0, total=100, title=_(u'Title'), text=u''):
		pass

class CopyDualProgressBox(DualProgressBox):
	pass


# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       SNACK                                                                       =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

class SnackUI(UI):
	def __init__(self):
		UI.__init__(self)
		
		self._screen = SnackScreen()
		if (self._screen.width < 40) or (self._screen.height < 24):
			self.exit()
			raise Exception(u'Display to small (at least 24 lines by 40 columns needed)')
		self.messageBox = None
		self._screen.pushHelpLine(u"")
		
		ui_signal.signal(ui_signal.SIGWINCH, self.sigwinchHandler)
		
	def __del__(self):
		try:
			self.exit()
		except:
			pass
	
	def sigwinchHandler(self, signo, stackFrame):
		#self._screen.finish()
		#self._screen = SnackScreen()
		self.refresh()
		
	def getScreen(self):
		return self._screen
	
	def refresh(self):
		self._screen.refresh()
		
	def getWidth(self):
		return self._screen.width
	
	def getHeight(self):
		return self._screen.height
	
	def exit(self):
		if self._screen:
			self._screen.finish()
	
	def drawRootText(self, x=1, y=1, text=u''):
		text = forceUnicode(text)
		for string in self.confidentialStrings:
			text = text.replace(string, u'*** confidential ***')
		try:
			self._screen.drawRootText(x, y, text.encode('ascii', 'replace'))
			self.refresh()
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
	
	def showError(self, text, title=_(u'An error occured'), okLabel=_(u'OK'), width=-1, height=-1, seconds=0):
		try:
			text    = forceUnicode(text)
			title   = forceUnicode(title)
			okLabel = forceUnicode(okLabel)
			width   = forceInt(width)
			height  = forceInt(height)
			seconds = forceInt(seconds)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
			if (height <= 0):
				height = len(text.split(u'\n')) + 2
			
			textBox = Textbox(width = width, height = height, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
			button = Button(okLabel.encode(encoding, 'replace'))
			rows = 2
			if seconds:
				rows = 1
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, rows)
			gridForm.add(textBox, 0, 0)
			if seconds:
				gridForm.draw()
				self.refresh()
				time.sleep(seconds)
				self._screen.popWindow()
			else:
				gridForm.add(button, 0, 1)
				helpLine = _(u"<F12> %s | <Space> select | <Up/Down> scroll text") % okLabel
				self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
				return gridForm.runOnce()
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
		
	def showMessage(self, text, title=_(u'Message'), okLabel=_(u'OK'), width=-1, height=-1, seconds=0):
		try:
			text    = forceUnicode(text)
			title   = forceUnicode(title)
			okLabel = forceUnicode(okLabel)
			width   = forceInt(width)
			height  = forceInt(height)
			seconds = forceInt(seconds)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
			if (height <= 0):
				height = len(text.split(u'\n')) + 2
			
			textBox = Textbox(width = width, height = height, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
			button = Button(okLabel.encode(encoding, 'replace'))
			rows = 2
			if seconds:
				rows = 1
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, rows)
			gridForm.add(textBox, 0, 0)
			if seconds:
				gridForm.draw()
				self.refresh()
				time.sleep(seconds)
				self._screen.popWindow()
			else:
				gridForm.add(button, 0, 1)
				helpLine = _(u"<F12> %s | <Space> select | <Up/Down> scroll text") % okLabel
				self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
				return gridForm.runOnce()
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
		
	def createProgressBox(self, width=-1, height=-1, total=100, title=_(u'Progress'), text=u''):
		try:
			width   = forceInt(width)
			height  = forceInt(height)
			total   = forceInt(total)
			title   = forceUnicode(title)
			text    = forceUnicode(text)
			
			progressBox = SnackProgressBox(ui = self, width = width, height = height, total = total, title = title, text = text)
			return progressBox
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
	
	def createCopyProgressBox(self, width=-1, height=-1, total=100, title=_(u'Copy progress'), text=u''):
		try:
			width   = forceInt(width)
			height  = forceInt(height)
			total   = forceInt(total)
			title   = forceUnicode(title)
			text    = forceUnicode(text)
			
			progressBox = SnackCopyProgressBox(ui = self, width = width, height = height, total = total, title = title, text = text)
			return progressBox
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
	
	def createDualProgressBox(self, width=-1, height=-1, total=100, title=_(u'Progress'), text=u''):
		try:
			width   = forceInt(width)
			height  = forceInt(height)
			total   = forceInt(total)
			title   = forceUnicode(title)
			text    = forceUnicode(text)
			
			dualProgressBox = SnackDualProgressBox(ui = self, width = width, height = height, total = total, title = title, text = text)
			return dualProgressBox
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
	
	def createCopyDualProgressBox(self, width=-1, height=-1, total=100, title=_(u'Copy progress'), text=u''):
		try:
			width   = forceInt(width)
			height  = forceInt(height)
			total   = forceInt(total)
			title   = forceUnicode(title)
			text    = forceUnicode(text)
			
			progressBox = SnackCopyDualProgressBox(ui = self, width = width, height = height, total = total, title = title, text = text)
			return progressBox
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
	
	def createMessageBox(self, width=-1, height=-1, title=_(u'Text'), text=u''):
		width   = forceInt(width)
		height  = forceInt(height)
		title   = forceUnicode(title)
		text    = forceUnicode(text)
		
		self.messageBox = SnackMessageBox(ui=self, width=width, height=height, title=title, text=text)
		return self.messageBox
		
	def getMessageBox(self):
		if not self.messageBox:
			self.createMessageBox()
		return self.messageBox
	
	def getValue(self, width=-1, height=-1, title=_(u'Please type text'), default=u'', password=False, text=u'', okLabel=_(u'OK'), cancelLabel=_(u'Cancel')):
		try:
			width       = forceInt(width)
			height      = forceInt(height)
			title       = forceUnicode(title)
			default     = forceUnicode(default)
			password    = forceBool(password)
			text        = forceUnicode(text)
			okLabel     = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
			
			# create text grid
			textGrid = Grid(1, 1)
			if text:
				textHeight = 0
				if (height <= 0):
					height = self.getScreen().height - 15
					textHeight = height - 5
					if (textHeight < 2):
						textHeight = 2
					elif (textHeight > len(text.split('\n')) + 1):
						textHeight = len(text.split('\n')) + 1
				else:
					textHeight = height - len(text.split('\n')) + 1
				
				textBox = Textbox(width = width, height = textHeight, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
				textGrid.setField(textBox, col = 0, row = 0)
			
			# create grid for input
			entryGrid = Grid(1, 1)
			entry = Entry(width = width, text = default.encode(encoding, 'replace'), hidden = False, password = password, scroll = 1, returnExit = 0)
			entryGrid.setField(entry, col = 0, row = 0, padding = (0, 0, 0, 0))
			
			# create grid for buttons
			buttonsGrid = Grid(2, 1)
			
			cancelButton = Button(cancelLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(cancelButton, col = 0, row = 0, padding = (0, 0, 10, 0))
			
			okButton = Button(okLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(okButton, col = 1, row = 0, padding = (10, 0, 0, 0))
			
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, 3)
			gridForm.add (textGrid,    col = 0, row = 0, padding = (0, 0, 0, 1))
			gridForm.add (entryGrid,   col = 0, row = 1, padding = (0, 0, 0, 1))
			gridForm.add (buttonsGrid, col = 0, row = 2, padding = (0, 0, 0, 0))
			gridForm.addHotKey('ESC')
			
			# help line
			helpLine = _(u"<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (cancelLabel, okLabel)
			if text:
				helpLine += _(u" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
			
			# run
			gridForm.addHotKey('ESC')
			gridForm.draw()
			buttonPressed = None
			while (buttonPressed not in [ okButton, 'F12', cancelButton, 'ESC' ] ):
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if (buttonPressed not in [ okButton, 'F12' ] ):
				return None
			
			return unicode(entry.value(), encoding)
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
		
	def getSelection(self, entries, radio=False, width=-1, height=-1, title=_(u'Please select'), text=u'', okLabel=_(u'OK'), cancelLabel=_(u'Cancel')):
		try:
			entries     = forceList(entries)
			radio       = forceBool(radio)
			width       = forceInt(width)
			height      = forceInt(height)
			title       = forceUnicode(title)
			text        = forceUnicode(text)
			okLabel     = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
			
			# create text grid
			textGrid = Grid(1, 1)
			if text:
				textHeight = 0
				if (height <= 0):
					height = self.getScreen().height - 15
					textHeight = height - len(entries)
					if (textHeight < 2):
						textHeight = 2
					elif (textHeight > len(text.split(u'\n'))):
						textHeight = len(text.split(u'\n'))
				else:
					textHeight = height - len(entries)
				
				textBox = Textbox(width = width, height = textHeight, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
				textGrid.setField(textBox, col = 0, row = 0)
			
			# create grid for entries
			entriesGrid = Grid(1, len(entries))
			
			row = 0
			group = None
			numSelected = 0
			for entry in entries:
				selected = forceBool(entry.get('selected', False))
				if radio and (numSelected >= 1):
					selected = False
				if selected:
					numSelected += 1
				
				if radio:
					group = entry['entry'] = SingleRadioButton(
							text  = forceUnicode(entry.get('name', '???')).encode(encoding, 'replace'),
							group = group,
							isOn  = selected )
				else:
					entry['entry'] = Checkbox(
							text = forceUnicode(entry.get('name', '???')).encode(encoding, 'replace'),
							isOn = selected )
				
				entriesGrid.setField(entry['entry'], col = 0, row = row, anchorLeft = 1, padding = (0, 0, 0, 0))
				
				row += 1
			
			# create grid for buttons
			buttonsGrid = Grid(2, 1)
			
			cancelButton = Button(cancelLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(cancelButton, col = 0, row = 0, padding = (0, 0, 10, 0))
			
			okButton = Button(okLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(okButton, col = 1, row = 0, padding = (10, 0, 0, 0))
			
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, 3)
			gridForm.add (textGrid,    col = 0, row = 0, padding = (0, 0, 0, 1))
			gridForm.add (entriesGrid, col = 0, row = 1, padding = (0, 0, 0, 1))
			gridForm.add (buttonsGrid, col = 0, row = 2, padding = (0, 0, 0, 0))
			
			# help line
			helpLine = _(u"<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (cancelLabel, okLabel)
			if text:
				helpLine += _(u" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
			
			# run
			gridForm.addHotKey('ESC')
			gridForm.draw()
			buttonPressed = None
			while (buttonPressed not in [ okButton, 'F12', cancelButton, 'ESC' ] ):
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if (buttonPressed not in [ okButton, 'F12' ] ):
				return None
			
			result = []
			for i in range( len(entries) ):
				if entries[i]['entry'].selected():
					if radio:
						return [ entries[i]['name'] ]
					else:
						result.append(entries[i]['name'])
			return result
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
		
	def getValues(self, entries, width=-1, height=-1, title=_(u'Please fill in'), text=u'', okLabel=_(u'OK'), cancelLabel=_(u'Cancel')):
		try:
			entries     = forceList(entries)
			width       = forceInt(width)
			height      = forceInt(height)
			title       = forceUnicode(title)
			text        = forceUnicode(text)
			okLabel     = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
			
			if (height <= 0):
				height = self.getScreen().height - 15
			
			# create text grid
			textGrid = Grid(1, 1)
			
			if text:
				height -= len(entries)
				if (height < 2):
					height = 2
				textBox = Textbox(width = width, height = height, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
				textGrid.setField(textBox, col = 0, row = 0)
			
			# create grid for entries
			entriesGrid = Grid(2, len(entries))
			
			row = 0
			labelWidth = 10
			for entry in entries:
				l = len(entry.get('name', u''))
				if (l > labelWidth):
					labelWidth = l
			width = width-labelWidth
			if (width < 5):
				width = 5
			for entry in entries:
				label = Label( forceUnicode(entry.get('name', u'???')).encode(encoding, 'replace') )
				value = forceUnicodeList(entry.get('value'))
				value = u', '.join(value)
				entry['entry'] = Entry(	width = width, text = value.encode(encoding, 'replace'),
							hidden = entry.get('hidden', False), password = entry.get('password', False),
							scroll = 1, returnExit = 0)
				entriesGrid.setField(label, col = 0, row = row, anchorLeft = 1, padding = (2, 0, 1, 0))
				entriesGrid.setField(entry['entry'], col = 1, row = row, anchorRight = 1, padding = (1, 0, 2, 0))
				row += 1
			
			# create grid for buttons
			buttonsGrid = Grid(2, 1)
			
			cancelButton = Button(cancelLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(cancelButton, col = 0, row = 0, padding = (0, 0, 10, 0))
			
			okButton = Button(okLabel.encode(encoding, 'replace'))
			buttonsGrid.setField(okButton, col = 1, row = 0, padding = (10, 0, 0, 0))
			
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, 3)
			gridForm.add (textGrid,    col = 0, row = 0, padding = (0, 0, 0, 1))
			gridForm.add (entriesGrid, col = 0, row = 1, padding = (0, 0, 0, 1))
			gridForm.add (buttonsGrid, col = 0, row = 2, padding = (0, 0, 0, 0))
			
			# help line
			helpLine = _(u"<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (cancelLabel, okLabel)
			if text:
				helpLine += _(u" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
			
			# run
			gridForm.addHotKey('ESC')
			gridForm.draw()
			buttonPressed = None
			while (buttonPressed not in [ okButton, 'F12', cancelButton, 'ESC' ] ):
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if (buttonPressed not in [ okButton, 'F12' ] ):
				return None
			
			for i in range( len(entries) ):
				value = unicode(entries[i]['entry'].value(), encoding)
				if entries[i].get('multivalue') and ( value.find(u',') != -1 ):
					value = map(lambda x:x.strip(), value.split(u','))
				
				entries[i]['value'] = value
				del(entries[i]['entry'])
			return entries
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise
		
	def yesno(self, text, title=_(u'Question'), okLabel=_(u'OK'), cancelLabel=_(u'Cancel'), width=-1, height=-1):
		try:
			text        = forceUnicode(text)
			title       = forceUnicode(title)
			okLabel     = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)
			width       = forceInt(width)
			height      = forceInt(height)
			
			for string in self.confidentialStrings:
				text = text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self.getScreen().width - 15
				if width > len(text) + 5:
					width = len(text) + 5
			if (height <= 0):
				height = 10
			
			gridForm = GridForm(self._screen, title.encode(encoding, 'replace'), 1, 2)
			
			textBox = Textbox(width = width, height = height-6, text = text.encode(encoding, 'replace'), scroll = 1, wrap = 1)
			gridForm.add(textBox, col = 0, row = 0)
			
			grid = Grid(2, 1)
			cancelButton = Button(cancelLabel.encode(encoding, 'replace'))
			grid.setField(cancelButton, 0, 0, (0, 0, 5, 0))
			okButton = Button(okLabel.encode(encoding, 'replace'))
			grid.setField(okButton, 1, 0, (5, 0, 0, 0))
			gridForm.add(grid, col = 0, row = 1)
			
			# help line
			helpLine = _(u"<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (cancelLabel, okLabel)
			if text:
				helpLine += _(u" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine).encode(encoding, 'replace'))
			
			# run
			gridForm.addHotKey('ESC')
			gridForm.draw()
			buttonPressed = None
			while (buttonPressed not in [ okButton, 'F12', cancelButton, 'ESC' ] ):
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if (buttonPressed in [ okButton, 'F12' ] ):
				return True
			return False
		except Exception, e:
			self.exit()
			logger.logException(e)
			raise


class SnackMessageBox(MessageBox, MessageObserver):
	def __init__(self, ui, width=0, height=0, title=_(u'Title'), text=u''):
		MessageObserver.__init__(self)
		
		try:
			self._ui = ui
			
			width  = forceInt(width)
			height = forceInt(height)
			title  = forceUnicode(title)
			text   = forceUnicode(text)
			
			self._visible = False
			self._title = title
			self._text = text
			
			for string in self._ui.confidentialStrings:
				self._text = self._text.replace(string, u'*** confidential ***')
			
			if (width <= 0):
				width = self._ui.getScreen().width - 7
			if (height <= 0):
				height = self._ui.getScreen().height - 7
			
			self._width = width
			self._height = self._textHeight = height
			
			self._gridForm = GridForm(self._ui.getScreen(), title.encode(encoding, 'replace'), 1, 1)
			self._textbox = Textbox(self._width, self._height, self._text.encode(encoding, 'replace'), scroll=0, wrap=1)
			self._gridForm.add(self._textbox, 0, 0)
			
			# help line
			self._ui.getScreen().pushHelpLine(u"")
		except Exception, e:
			self._ui.exit()
			logger.logException(e)
			raise
		
	def show(self, seconds=0):
		try:
			self._gridForm.draw()
			self._ui.refresh()
			self._visible = True
			if seconds:
				time.sleep(seconds)
				self.hide()
		except Exception, e:
			self._ui.exit()
			logger.logException(e)
			raise
		
	def hide(self):
		try:
			if self._visible:
				self._ui.getScreen().popWindow()
			self._visible = False
		except Exception, e:
			self._ui.exit()
			logger.logException(e)
			raise
		
	def setText(self, text):
		try:
			self._text = forceUnicode(text)
			for string in self._ui.confidentialStrings:
				self._text = self._text.replace(string, u'*** confidential ***')
			
			lines = self._text.split(u"\n")
			for i in range( len(lines) ):
				pos = lines[i].find(u"\r")
				if (pos != -1):
					parts = lines[i].split(u"\r")
					for j in range (len(parts)-1, -1, -1):
						if parts[j]:
							lines[i] = parts[j] + u"\r"
							break
			if (lines > self._textHeight):
				self._text = u"\n".join( lines[(-1)*self._textHeight:] )
			try:
				self._textbox.setText(self._text.encode(encoding, 'replace'))
			except Exception, e:
				logger.logException(e)
			self.show()
		except Exception, e:
			self._ui.exit()
			logger.logException(e)
			raise
		
	def addText(self, text):
		try:
			self.setText( self._text + forceUnicode(text) )
		except Exception, e:
			self._ui.exit()
			logger.logException(e)
			raise
	
	def messageChanged(self, subject, message):
		self.addText(u"%s\n" % message)

class SnackProgressBox(SnackMessageBox, ProgressBox, ProgressObserver):
	def __init__(self, ui, width=0, height=0, total=100, title=_(u'Title'), text=u''):
		ProgressObserver.__init__(self)
		
		self._ui = ui
		width  = forceInt(width)
		height = forceInt(height)
		total  = forceInt(total)
		title  = forceUnicode(title)
		text   = forceUnicode(text)
		
		if (width <= 0):
			width = self._ui.getScreen().width - 7
		if (height <= 0):
			height = self._ui.getScreen().height - 7
		
		SnackMessageBox.__init__(self, ui, width, height-4, title, text)
		
		self._total = total
		self._state = -1
		self._factor = 1
		self._width = width
		self._height = height
		
		self._gridForm = GridForm(self._ui.getScreen(), title.encode(encoding, 'replace'), 1, 2)
		self._scale = Scale(self._width, self._total)
		self._gridForm.add(self._textbox, 0, 0)
		self._gridForm.add(self._scale, 0, 1)
		
		self._ui.getScreen().pushHelpLine("")
		
	def setState(self, state):
		self._state = state
		self._scale.set(int(self._state*self._factor))
		self.show()
	
	def getState(self):
		return self._state
	
	def endChanged(self, subject, end):
		if (end <= 0) or (self._total <= 0):
			self.setState(0)
		else:
			self._factor = float(self._total)/end
			self.setState(self._state)
	
	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		self.setState(state)


class SnackCopyProgressBox(SnackProgressBox):
	def messageChanged(self, subject, message):
		minLeft = 0
		secLeft = subject.getTimeLeft()
		if (secLeft >= 60):
			minLeft = int(secLeft/60)
			secLeft -= (minLeft*60)
		if (minLeft < 10):
			minLeft = '0%d' % minLeft
		if (secLeft < 10):
			secLeft = '0%d' % secLeft
		message = u"[%s:%s ETA] %s" % (minLeft, secLeft, message)
		self.addText(u"%s\n" % message)

class SnackDualProgressBox(SnackMessageBox, ProgressObserver):
	def __init__(self, ui, width=0, height=0, total=100, title=_(u'Title'), text=u''):
		ProgressObserver.__init__(self)
		
		self._ui = ui
		width  = forceInt(width)
		height = forceInt(height)
		total  = forceInt(total)
		title  = forceUnicode(title)
		text   = forceUnicode(text)
		
		if (width <= 0):
			width = self._ui.getScreen().width - 7
		if (height <= 0):
			height = self._ui.getScreen().height - 7
		
		SnackMessageBox.__init__(self, ui, width, height-4, title, text)
		
		self._overallTotal = total
		self._overallState = -1
		self._overallFactor = 1
		self._overallProgressSubject = None
		
		self._currentTotal = 100
		self._currentState = -1
		self._currentFactor = 1
		self._currentProgressSubject = None
		
		self._width = width
		self._height = height
		
		self._gridForm = GridForm(self._ui.getScreen(), title.encode(encoding, 'replace'), 1, 3)
		self._currentScale = Scale(self._width, self._currentTotal)
		self._overallScale = Scale(self._width, self._overallTotal)
		
		self._gridForm.add(self._textbox, 0, 0)
		self._gridForm.add(self._currentScale, 0, 1)
		self._gridForm.add(self._overallScale, 0, 2)
		
		self._ui.getScreen().pushHelpLine("")
		
	def setOverallProgressSubject(self, subject):
		self._overallProgressSubject = subject
		self._overallProgressSubject.attachObserver(self)
		
	def setCurrentProgressSubject(self, subject):
		self._currentProgressSubject = subject
		self._currentProgressSubject.attachObserver(self)
	
	def setOverallState(self, state):
		self._overallState = state
		self._overallScale.set(int(self._overallState*self._overallFactor))
		self.show()
	
	def setCurrentState(self, state):
		self._currentState = state
		self._currentScale.set(int(self._currentState*self._currentFactor))
		self.show()
	
	def getState(self):
		return self._overallState
	
	def endChanged(self, subject, end):
		if (subject == self._overallProgressSubject):
			if (end <= 0) or (self._overallTotal <= 0):
				self.setOverallState(0)
			else:
				self._overallFactor = float(self._overallTotal)/end
				self.setOverallState(self._overallState)
		elif (subject == self._currentProgressSubject):
			if (end <= 0) or (self._currentTotal <= 0):
				self.setCurrentState(0)
			else:
				self._currentFactor = float(self._currentTotal)/end
				self.setCurrentState(self._currentState)
		
	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
		if (subject == self._overallProgressSubject):
			self.setOverallState(state)
		elif (subject == self._currentProgressSubject):
			self.setCurrentState(state)

class SnackCopyDualProgressBox(SnackDualProgressBox):
	def messageChanged(self, subject, message):
		minLeft = 0
		secLeft = subject.getTimeLeft()
		if (secLeft >= 60):
			minLeft = int(secLeft/60)
			secLeft -= (minLeft*60)
		if (minLeft < 10):
			minLeft = '0%d' % minLeft
		if (secLeft < 10):
			secLeft = '0%d' % secLeft
		message = u"[%s:%s ETA] %s" % (minLeft, secLeft, message)
		self.addText(u"%s\n" % message)

if (__name__ == "__main__"):
	uiTest = UIFactory('snack')
	uiTest.drawRootText(x = 1, y = 1, text = u'Test ä root text')
	uiTest.drawRootText(x = 1, y = 2, text = u'Test root text 2')
	uiTest.drawRootText(x = 5, y = 5, text = u'Test root text 3')
	time.sleep(1)
	uiTest.createMessageBox(title = "TEST").show()
	time.sleep(1)
	
	uiTest.showError(text = u'Test error', title = u'An error occured', okLabel = u'Read', width = -1, height = -1, seconds = 2)
	uiTest.showError(text = u'Test error äöü', title = u'An €rror occured', okLabel = u'ÖK', width = 30, height = 10)
	uiTest.showMessage(text = u'A message', title = u'Message', width = 5, height = 5, seconds = 2)
	uiTest.showMessage(text = u'Ä$§€€üüüüüüüüßßßßßßßßßß', title = u'Titel ä', okLabel = u'ÖK', width = -1, height = -1, seconds = 0)
	pb = uiTest.createProgressBox(width = -1, height = -1, total = 100, title = u'Progress', text = u'please wait')
	state = 0
	while (state < 100):
		state += 10
		pb.setState(state)
		time.sleep(0.2)
	time.sleep(1)
	
	pb = uiTest.createProgressBox(width = 30, height = 10, total = 200, title = u'Prögress', text = u'please wäit')
	state = 0
	while (state < 200):
		state += 20
		pb.setState(state)
		time.sleep(0.5)
	time.sleep(1)
	
	mb = uiTest.createMessageBox(width = -1, height = -1, title = u'€€€€€€€€', text = u'@&%$§"ß')
	mb.show()
	time.sleep(1)
	mb.setText(u'New text äöü')
	time.sleep(1)
	mb.addText(u'a\nü\nß\n')
	time.sleep(1)
	
	mb2 = uiTest.createMessageBox(width = 30, height = 20, title = u'smaller window', text = u'text\ntext\ntext')
	mb2.show()
	
	time.sleep(1)
	mbx = uiTest.getMessageBox()
	mbx.addText(u'\n\nTEST\nßßßßßßßßßßßßßßßßßßßß')
	mbx.show(seconds = 1)
	
	value = uiTest.getValue(width = 20, height = 10, title = u'€ Bitte text eingeben €', default = u'äääää', password = False, text = u'Bitte text eingeben üüüü', okLabel = u'ÖK', cancelLabel = u'Cäncel')
	mbx = uiTest.getMessageBox()
	mbx.setText(u'Got value: %s' % value)
	mbx.show(seconds = 1)
	
	entries = [ { 'name': u'€ntry 1', 'selected': False }, { 'name': u'€ntry 2', 'selected': True }, { 'name': u'€ntry 3', 'selected': True } ]
	selection = uiTest.getSelection(entries, radio = False, width = 20, height = 20, title = u'Select one or more entries', text = u'ßßßß', okLabel = u'ÖK', cancelLabel = u'Cäncel')
	mbx.setText(u'Got selection: %s' % selection)
	mbx.show(seconds = 1)
	
	entries = [ { 'name': u'€ntry 1', 'selected': False }, { 'name': u'€ntry 2', 'selected': True }, { 'name': u'€ntry 3', 'selected': True } ]
	selection = uiTest.getSelection(entries, radio = True, width = 20, height = 20, title = u'Select äntry', text = u'ßßßß', okLabel = u'ÖK', cancelLabel = u'Cäncel')
	mbx.setText(u'Got selection: %s' % selection)
	mbx.show(seconds = 1)
	
	entries = [ { 'name': u'€ntry 1', 'value': False }, { 'name': u'€ntry 2', 'value': [1, '2', 'üö'], 'multivalue': True }, { 'name': u'€ntry 3', 'value': u'söme value' } ]
	values = uiTest.getValues(entries, width = 30, title = u'Select välues', text = u'ßßßß', okLabel = u'ÖK', cancelLabel = u'Cäncel')
	uiTest.showMessage(text = u'Got values: %s' % values, title = u'Titel', okLabel = u'ÖK', width = -1, height = -1, seconds = 0)
	
	answer = uiTest.yesno(text = u'Täxt', title = u'Yäs Or Nö', okLabel = u'ÖK', cancelLabel = u'Cäncel', width = -1, height = -1)
	uiTest.showMessage(text = u'Answer was: %s' % answer, seconds = 2)
	
	time.sleep(2)
	uiTest.exit()

















