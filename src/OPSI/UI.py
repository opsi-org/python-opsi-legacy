#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - UI      =
   = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008 uib GmbH
   
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

__version__ = '0.9.1.2'

# Constants
LOCALE_DIR = '/usr/share/locale'
snackError = None

# Imports
import time, gettext, tty, fcntl, signal, struct, termios
try:
	from snack import *
except Exception, e:
	snackError = e

# OPSI imports
from Logger import *

# Get Logger instance
logger = Logger()

# Get locale
try:
	t = gettext.translation('opsi_ui', LOCALE_DIR)
	_ = t.ugettext
except Exception, e:
	logger.error("Locale not found: %s" % e)
	def _(string):
		"""Dummy method, created and called when no locale is found.
		Uses the fallback language (called C; means english) then."""
		return string

def UIFactory(type=None):
	if (type == 'snack' or type == 'SnackUI'):
		if snackError:
			raise snackError
		return SnackUI()
	
	elif(type == 'text' or type == 'TextUI'):
		return TextUI()
	
	elif(type == 'dummy' or type == 'UI'):
		return UI()
	
	try:
		if snackError:
			raise snackError
		return SnackUI()
	except Exception, e:
		logger.warning("Failed to create SnackUI: %s" % e)
		return TextUI()

class UI:
	def __init__(self):
		pass
	
	def getScreen(self):
		pass
	
	def getWidth(self):
		return 0
	
	def getHeight(self):
		return 0
	
	def exit(self):
		pass
	
	def drawRootText(self, x=1, y=1, text=''):
		pass
	
	def showError(self, text, title=_('An error occured'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		pass
	
	def showMessage(self, text, title=_('Message'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		pass
	
	def createProgressBox(self, width=-1, height=-1, total=100, title=_('Progress'), text=''):
		return ProgressBox(self)
	
	def createMessageBox(self, width=-1, height=-1, title=_('Text'), text=''):
		return MessageBox(self)
		
	def getMessageBox(self):
		return MessageBox(self)
	
	def getValue(self, width=-1, height=-1, title=_('Please type text'), default='', password=False, text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
		return None
	
	def getSelection(self, entries, radio=False, width=-1, height=-1, title=_('Please select'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):	
		return []
	
	def getValues(self, entries, width=-1, title=_('Please fill in'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
		return entries
	
	def yesno(self, text, title=_('Question'), okLabel=_('OK'), cancelLabel=_('Cancel'), width=-1, height=-1):	
		return True
	
class MessageBox:
	def __init__(self, ui, width=0, height=0, title=_('Title'), text=''):
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
	def __init__(self, ui, width=0, height=0, total=100, title=_('Title'), text=''):
		pass
		
	def setState(self, state):
		pass

	def getState(self):
		pass




# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       SNACK                                                                       =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

class SnackUI(UI):
	def __init__(self):
		
		self._screen = SnackScreen()
		if (self._screen.width < 40) or (self._screen.height < 24):
			self.exit()
			raise Exception('Display to small (at least 24 lines by 40 columns needed)')
		self.messageBox = None
		self._screen.pushHelpLine("")
			
	def getScreen(self):
		return self._screen
	
	def getWidth(self):
		return self._screen.width
	
	def getHeight(self):
		return self._screen.height
	
	def exit(self):
		self._screen.finish()
	
	def drawRootText(self, x=1, y=1, text=''):
		self._screen.drawRootText(x, y, text)
		self._screen.refresh()
	
	def showError(self, text, title=_('An error occured'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		if (width <= 0):
			width = self.getScreen().width - 15
		if (height <= 0):
			height = len(text.split('\n')) + 2
		textBox = Textbox(width=width, height=height, text=str(text), scroll=1, wrap=1)
		button = Button(okLabel)
		rows = 2
		if seconds:
			rows = 1
		gridForm = GridForm(self._screen, str(title), 1, rows)
		gridForm.add(textBox, 0, 0)
		if seconds:
			gridForm.draw()
			self._screen.refresh()
			time.sleep(seconds)
			self._screen.popWindow()
		else:
			gridForm.add(button, 0, 1)
			
			# help line
			helpLine = 	"<F12> %s" % okLabel + \
					" | <Space> %s" % _("select") + \
					" | <Up/Down> %s" % _("scroll text")
			self.getScreen().pushHelpLine(helpLine)
			
			return gridForm.runOnce()
	
	def showMessage(self, text, title=_('Message'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		if (width <= 0):
			width = self.getScreen().width - 15
		if (height <= 0):
			height = len(text.split('\n')) + 2
		textBox = Textbox(width=width, height=height, text=str(text), scroll=1, wrap=1)
		button = Button(okLabel)
		rows = 2
		if seconds:
			rows = 1
		gridForm = GridForm(self._screen, str(title), 1, rows)
		gridForm.add(textBox, 0, 0)
		if seconds:
			gridForm.draw()
			self._screen.refresh()
			time.sleep(seconds)
			self._screen.popWindow()
		else:
			gridForm.add(button, 0, 1)
			
			# help line
			helpLine = 	"<F12> %s" % okLabel + \
					" | <Space> %s" % _("select") + \
					" | <Up/Down> %s" % _("scroll text")
			self.getScreen().pushHelpLine(helpLine)
			
			return gridForm.runOnce()
	
	def createProgressBox(self, width=-1, height=-1, total=100, title=_('Progress'), text=''):
		progressBox = SnackProgressBox(ui=self, width=width, height=height, total=total, title=title, text=text)
		return progressBox
	
	def createMessageBox(self, width=-1, height=-1, title=_('Text'), text=''):
		self.messageBox = SnackMessageBox(ui=self, width=width, height=height, title=title, text=text)
		return self.messageBox
		
	def getMessageBox(self):
		if not self.messageBox:
			self.createMessageBox()
		return self.messageBox
	
	def getValue(self, width=-1, height=-1, title=_('Please type text'), default='', password=False, text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
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
			
			textBox = Textbox(width=width, height=textHeight, text=text, scroll=1, wrap=1)
			textGrid.setField(textBox, col=0, row=0)
		
		# create grid for input
		entryGrid = Grid(1, 1)
		entry = Entry(	width = width, text = str(default), 
				hidden = False, password=password, 
				scroll=1, returnExit=0)
		entryGrid.setField(entry, col=0, row=0, padding=(0, 0, 0, 0))
		
		# create grid for buttons
		buttonsGrid = Grid(2, 1)
		
		cancelButton = Button(str(cancelLabel))
		buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))
		
		okButton = Button(str(okLabel))
		buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))
		
		gridForm = GridForm(self._screen, str(title), 1, 3)
		gridForm.add (textGrid, col=0, row=0, padding=(0, 0, 0, 1))
		gridForm.add (entryGrid, col=0, row=1, padding=(0, 0, 0, 1))
		gridForm.add (buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))
	        
		# help line
		helpLine = 	"<ESC> %s | <F12> %s" % (cancelLabel, okLabel) + \
				" | <Tab> %s" % _("move cursor") + \
				" | <Space> %s" % _("select")
		if text:
			helpLine += " | <Up/Down> %s" % _("scroll text")
		self.getScreen().pushHelpLine(helpLine)
		
		# run
		buttonPressed = gridForm.runOnce()
		
		if (buttonPressed not in [ okButton, 'F12' ] ):
			return None
		
		return entry.value()
		
	def getSelection(self, entries, radio=False, width=-1, height=-1, title=_('Please select'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):	
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
				elif (textHeight > len(text.split('\n'))):
					textHeight = len(text.split('\n'))
			else:
				textHeight = height - len(entries)
			
			textBox = Textbox(width=width, height=textHeight, text=str(text), scroll=1, wrap=1)
			textGrid.setField(textBox, col=0, row=0)
		
		# create grid for entries
		entriesGrid = Grid(1, len(entries))
		
		row = 0
		group = None
		for entry in entries:
			if radio:
				group = entry['entry'] = SingleRadioButton(
						text = str(entry.get('name', '???')),
						group = group,
						isOn = bool(entry.get('selected', False)) )
			else:
				entry['entry'] = Checkbox(
						text = str(entry.get('name', '???')), 
						isOn = bool(entry.get('selected', False)) )
			
			entriesGrid.setField(entry['entry'], col=0, row=row, anchorLeft=1, padding=(0, 0, 0, 0))
			
			row += 1
		
		
		# create grid for buttons
		buttonsGrid = Grid(2, 1)
		
		cancelButton = Button(str(cancelLabel))
		buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))
		
		okButton = Button(str(okLabel))
		buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))
		
		gridForm = GridForm(self._screen, str(title), 1, 3)
		gridForm.add (textGrid, col=0, row=0, padding=(0, 0, 0, 1))
		gridForm.add (entriesGrid, col=0, row=1, padding=(0, 0, 0, 1))
		gridForm.add (buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))
		
		# help line
		helpLine = 	"<ESC> %s | <F12> %s" % (cancelLabel, okLabel) + \
				" | <Tab> %s" % _("move cursor") + \
				" | <Space> %s" % _("select")
		if text:
			helpLine += " | <Up/Down> %s" % _("scroll text")
		self.getScreen().pushHelpLine(helpLine)
		
		# run
		gridForm.draw()
		buttonPressed = gridForm.run()
		
		while (buttonPressed not in [ okButton, 'F12', cancelButton, 'ESC' ] ):
			buttonPressed = gridForm.run()
		
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
		
	
	def getValues(self, entries, width=-1, title=_('Please fill in'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
		if (width <= 0):
			width = self.getScreen().width - 15
		
		# create text grid
		textGrid = Grid(1, 1)
		if text:
			height = self.getScreen().height - 15 - len(entries)
			if (height < 2):
				height = 2
			textBox = Textbox(width=width, height=height, text=text, scroll=1, wrap=1)
			textGrid.setField(textBox, col=0, row=0)
		
		# create grid for entries
		entriesGrid = Grid(2, len(entries))
		
		row = 0
		labelWidth = 10
		for entry in entries:
			l = len(entry.get('name', ''))
			if (l > labelWidth):
				labelWidth = l
		width = width-labelWidth
		if (width < 5):
			width = 5
		for entry in entries:
			label = Label(entry.get('name', '???'))
			value = entry.get('value')
			if ( type(value) == type(()) or type(value) == type([]) ):
				value = ', '.join(value)
			if (value == None):
				value = ''
			
			entry['entry'] = Entry(	width=width, text=str(value), 
						hidden=entry.get('hidden', False), password=entry.get('password', False), 
						scroll=1, returnExit=0)
			entriesGrid.setField(label, col=0, row=row, anchorLeft=1, padding=(2, 0, 1, 0))
			entriesGrid.setField(entry['entry'], col=1, row=row, anchorRight=1, padding=(1, 0, 2, 0))
			row += 1
		
		
		# create grid for buttons
		buttonsGrid = Grid(2, 1)
		
		cancelButton = Button(cancelLabel)
		buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))
		
		okButton = Button(okLabel)
		buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))
		
		gridForm = GridForm(self._screen, str(title), 1, 3)
		gridForm.add (textGrid, col=0, row=0, padding=(0, 0, 0, 1))
		gridForm.add (entriesGrid, col=0, row=1, padding=(0, 0, 0, 1))
		gridForm.add (buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))
	        
		# help line
		helpLine = 	"<ESC> %s | <F12> %s" % (cancelLabel, okLabel) + \
				" | <Tab> %s" % _("move cursor") + \
				" | <Space> %s" % _("select")
		if text:
			helpLine += " | <Up/Down> %s" % _("scroll text")
		self.getScreen().pushHelpLine(helpLine)
		
		# run
		buttonPressed = gridForm.runOnce()
		
		if (buttonPressed not in [ okButton, 'F12' ] ):
			return None
		
		for i in range( len(entries) ):
			value = entries[i]['entry'].value()
			if entries[i].get('multivalue') and ( value.find(',') != -1 ):
				value = map(lambda x:x.strip(), value.split(','))
			
			entries[i]['value'] = value
			del(entries[i]['entry'])
		return entries
	
	def yesno(self, text, title=_('Question'), okLabel=_('OK'), cancelLabel=_('Cancel'), width=-1, height=-1):	
		if (width <= 0):
			width = self.getScreen().width - 15
			if width > len(text) + 5:
				width = len(text) + 5
		if (height <= 0):
			height = 10
		
		gridForm = GridForm(self._screen, str(title), 1, 2)
		
		textBox = Textbox(width=width, height=height-6, text=str(text), scroll=1, wrap=1)
		gridForm.add(textBox, col=0, row=0)
		
		grid = Grid(2, 1)
		cancelButton = Button(str(cancelLabel))
		grid.setField(cancelButton, 0, 0, (0, 0, 5, 0))
		okButton = Button(str(okLabel))
		grid.setField(okButton, 1, 0, (5, 0, 0, 0))
		gridForm.add(grid, col=0, row=1)
		
		# help line
		helpLine = 	"<ESC> %s | <F12> %s" % (cancelLabel, okLabel) + \
				" | <Tab> %s" % _("move cursor") + \
				" | <Space> %s" % _("select")
		self.getScreen().pushHelpLine(helpLine)
		
		# run
		buttonPressed = gridForm.runOnce()
		if (buttonPressed in [ okButton, 'F12' ] ):
			return True
		return False


class SnackMessageBox(MessageBox):
	def __init__(self, ui, width=0, height=0, title=_('Title'), text=''):
		self._ui = ui
		self._text = text
		if (width <= 0):
			width = self._ui.getScreen().width - 7
		if (height <= 0):
			height = self._ui.getScreen().height - 7
		
		self._width = width
		self._height = self._textHeight = height
		
		self._gridForm = GridForm(self._ui.getScreen(), str(title), 1, 1)
		self._textbox = Textbox(self._width, self._height, str(self._text), scroll=0, wrap=1)
		self._gridForm.add(self._textbox, 0, 0)
		
		# help line
		self._ui.getScreen().pushHelpLine("")
		
	def show(self, seconds=0):
		self._gridForm.draw()
		self._ui.getScreen().refresh()
		if seconds:
			time.sleep(seconds)
			self.hide()
	
	def hide(self):
		self._ui.getScreen().popWindow()
		
	def setText(self, text):
		self._text = text
		lines = self._text.split("\n")
		for i in range( len(lines) ):
			pos = lines[i].find("\r")
			if (pos != -1):
				parts = lines[i].split("\r")
				for j in range (len(parts)-1, -1, -1):
					if parts[j]:
						lines[i] = parts[j] + "\r"
						break
		if (lines > self._textHeight):
			self._text = "\n".join( lines[(-1)*self._textHeight:] )
		try:
			self._textbox.setText(self._text)
		except Exception, e:
			logger.logException(e)
		self.show()
		
	def addText(self, text):
		try:
			self.setText( self._text + text )
		except Exception, e:
			logger.error("Cannot add text: %s" % text)
			logger.logException(e)
		
	

class SnackProgressBox(SnackMessageBox, ProgressBox):
	def __init__(self, ui, width=0, height=0, total=100, title=_('Title'), text=''):
		self._ui = ui
		if (width <= 0):	
			width = self._ui.getScreen().width - 7
		if (height <= 0):
			height = self._ui.getScreen().height - 7
		
		SnackMessageBox.__init__(self, ui, width, height-4, title, text)
		
		self._state = -1
		self._width = width
		self._height = height
		
		self._gridForm = GridForm(self._ui.getScreen(), str(title), 1, 2)
		self._scale = Scale(self._width, total)
		self._gridForm.add(self._textbox, 0, 0)
		self._gridForm.add(self._scale, 0, 1)
		
		# help line
		self._ui.getScreen().pushHelpLine("")
		
	def setState(self, state):
		self._state = state
		self._scale.set(self._state)
		self.show()

	def getState(self):
		return self._state



# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       TEXT                                                                        =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

class TextUI(UI):
	from select import select
	
	global CRE	# erase to end of line
	global CLEAR	# clear and reset screen
	CRE="\r\033[K\r"
	CLEAR="\033c\r"
	
	def __init__(self):
		self.width = 0
		self.height = 0
		if not sys.stdin.isatty():
			raise Exception("No tty!")
		
		self.getTerminalSize()
		signal.signal(signal.SIGWINCH, self.updateTerminalSize)
		print >> sys.stdout, CLEAR,
		
		
	def updateTerminalSize(self, signo, stackFrame):
		if (signo == signal.SIGWINCH):
			self.getTerminalSize()
			
	def getTerminalSize(self):
		s = struct.pack('HHHH', 0, 0, 0, 0)
		x = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s)
		(self.height, self.width) = struct.unpack('HHHH', x)[:2]
		#print "(%s,%s)" % (self.height, self.width)
		
	def getch(self):
		saveAttr = tty.tcgetattr(sys.stdin)
		newAttr = saveAttr[:]
		newAttr[3] &= ~tty.ECHO & ~tty.ICANON
		tty.tcsetattr(sys.stdin, tty.TCSANOW, newAttr)
		c = ''
		try:
			c = sys.stdin.read(1)
		except:
			pass
		
		tty.tcsetattr(sys.stdin, tty.TCSANOW, saveAttr)
		return c
		
	def printText(self, text, align='LEFT'):
		for line in text.split('\n'):
			if align.lower().startswith('c'):
				line = int(round((self.width-len(line))/2))*' ' + line
				
			elif align.lower().startswith('r'):
				line = (self.width-len(line))*' ' + line
			print >> sys.stdout, line
		
	def getLine(self):
		try:
			return sys.stdin.readline()
		except:
			time.sleep(0.1)
			return self.getline()
	
	def getScreen(self):
		pass
	
	def getWidth(self):
		return self.width
		
	def getHeight(self):
		return self.height
	
	def exit(self):
		pass
	
	def drawRootText(self, x=1, y=1, text=''):
		print >> sys.stdout, text
	
	def showError(self, text, title=_('An error occured'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		print >> sys.stdout, CLEAR,
		self.printText('\n--=[ %s ]=--' % title, align='CENTER')
		if text:
			print >> sys.stdout, text, '\n'
		if seconds:
			time.sleep(seconds)
		else:
			print >> sys.stdout, _('(Please press any key to continue)')
			self.getch()
	
	def showMessage(self, text, title=_('Message'), okLabel=_('OK'), width=-1, height=-1, seconds=0):
		print >> sys.stdout, CLEAR,
		self.printText('\n--=[ %s ]=--' % title, align='CENTER')
		if text:
			print >> sys.stdout, text, '\n'
		if seconds:
			time.sleep(seconds)
		else:
			print >> sys.stdout, _('(Please press any key to continue)')
			self.getch()
		
	def createProgressBox(self, width=-1, height=-1, total=100, title=_('Progress'), text=''):
		progressBox = TextProgressBox(ui=self, width=width, height=height, total=total, title=title, text=text)
		return progressBox
	
	def createMessageBox(self, width=-1, height=-1, title=_('Text'), text=''):
		self.messageBox = TextMessageBox(ui=self, width=width, height=height, title=title, text=text)
		return self.messageBox
		
	def getMessageBox(self):
		if not self.messageBox:
			self.createMessageBox()
		return self.messageBox
	
	def getSelection(self, entries, radio=False, width=-1, height=-1, title=_('Please select'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
		print >> sys.stdout, CLEAR,
		self.printText('\n--=[ %s ]=--' % title, align='CENTER')
		if text:
			print >> sys.stdout, text, '\n'
		
		for i in range(len(entries)):
			print >> sys.stdout, CRE + '(' + str(i+1) + ') ' + entries[i].get('name', ''),
			if entries[i].get('selected'):
				print >> sys.stdout, '(*)'
			else:
				print ""
		print >> sys.stdout, _('\nPress <ENTER> to keep the default (*)')
		
		if radio:
			c = -1
			o = 0
			while c not in map(lambda x:str(x), (range(len(entries)+1)[1:])):
				print >> sys.stdout, '\r', _('Please select one of %s') % range(len(entries)+1)[1:], ':',
				c = self.getch()
				try:
					o = ord(c)
				except:
					pass
				if (o == 10):
					# Enter pressed => return default
					for entry in entries:
						if entry.get('selected'):
							return [ entry.get('name', '') ]
				print c
			return [ entries[int(c)-1].get('name') ]
		else:
			sel = []
			print >> sys.stdout, '\r', _('Please select one or more of %s') % range(len(entries)+1)[1:], ':'
			for i in range(len(entries)):
				c = ''
				o = 0
				print >> sys.stdout, CRE + '(' + str(i+1) + ') ' + entries[i].get('name', ''), '(y/n):',
				while (c.lower() not in ['y', 'n', 'j', 'n', '1', '0']):
					c = self.getch()
					try:
						o = ord(c)
					except:
						pass
					if (o == 10):
						# Enter pressed => return defaults
						sel = []
						for entry in entries:
							if entry.get('selected'):
								sel.append(entry.get('name', ''))
						return sel
				if c in ['y', 'j', '1']:
					sel.append(entries[i].get('name', ''))
					print >> sys.stdout,  "*"
				else:
					print >> sys.stdout, ""
			return sel
				
			
	def getValues(self, entries, width=-1, title=_('Please fill in'), text='', okLabel=_('OK'), cancelLabel=_('Cancel')):
		print >> sys.stdout, CLEAR,
		self.printText('\n--=[ %s ]=--' % title, align='CENTER')
		if text:
			print >> sys.stdout, text, '\n'
		for entry in entries:
			c = 0
			value = entry.get('value', '')			
			while True:
				if entry.get('password'):
					print >> sys.stdout, CRE + entry.get('name', '') + ': ' + '*'*len(value),
				else:
					print >> sys.stdout, CRE + entry.get('name', '') + ': ' + value,
				c = self.getch()
				o = 0
				try:
					o = ord(c)
					#print o
				except:
					pass
				if (o == 27):
					flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
					fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
					sys.stdin.read()
					fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags)
					continue
				elif (o == 10):
					# Enter
					print >> sys.stdout, ''
					break
				elif(o == 127 and len(value) > 0):
					# Backspace
					value = value[:-1]
				else:
					value += c
			
			if entry.get('multivalue') and ( value.find(',') != -1 ):
				value = map(lambda x:x.strip(), value.split(','))
			
			entry['value'] = value
			
		return entries
		
	def yesno(self, text, title=_('Question'), okLabel=_('OK'), cancelLabel=_('Cancel'), width=-1, height=-1):	
		print >> sys.stdout, CLEAR,
		self.printText('\n--=[ %s ]=--' % title, align='CENTER')
		if text:
			print >> sys.stdout, text, '\n'
		c = ''
		while (c.lower() not in ['y', 'n', 'j', 'n', '1', '0']):
			print >> sys.stdout, _('(y/n)'),
			c = self.getch()
			print c
		if c in ['y', 'j', '1']:
			return True
		return False

class TextMessageBox(MessageBox):
	def __init__(self, ui, width=0, height=0, title=_('Title'), text=''):
		self.ui = ui
		self.title = title
		self.text = text
	
	def show(self, seconds=0):
		print >> sys.stdout, CLEAR,
		self.ui.printText('\n--=[ %s ]=--' % self.title, align='CENTER')
		if self.text:
			print >> sys.stdout, self.text, '\n'
		
	def hide(self):
		pass
		
	def setText(self, text):
		self.text = text
		self.show()
		
	def addText(self, text):
		self.text += text
		self.show()
	

class TextProgressBox(TextMessageBox, ProgressBox):
	def __init__(self, ui, width=0, height=0, total=100, title=_('Title'), text=''):
		TextMessageBox.__init__(self, ui, width, height, title, text)
		self.total = total
		self.state = 0
	
	def update(self):
		percent = str(int(round(self.state*100/self.total)))
		barLen = int(round( ((self.ui.width)-9)*(float(self.state)/self.total) ))
		bar = '='*barLen
		bar += '-'*(self.ui.width-9-barLen)
		while ( len(percent) < 3):
			percent = ' ' + percent
		print >> sys.stdout, '\r' + percent + '% [' + bar +']',
		sys.stdout.flush()
		
	def setState(self, state):
		self.state = state
		if (self.state > self.total):
			self.state = self.total
		elif(self.state < 0):
			self.state = 0
		self.update()

	def getState(self):
		return self.state


