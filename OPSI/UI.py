# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
opsi python library - UI

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2010-2019 uib GmbH

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
@author: Niko Wenselowski <n.wenselowski@uib.de>
@license: GNU General Public License version 2
"""

import gettext
import locale
import os
import signal as ui_signal
import time
from typing import Any, List

from opsicommon.logging import get_logger
from snack import (
	Button,
	CheckboxTree,
	Entry,
	Grid,
	GridForm,
	Label,
	Listbox,
	Scale,
	SnackScreen,
	Textbox,
)

from OPSI.Types import forceBool, forceInt, forceList, forceUnicode, forceUnicodeList
from OPSI.Util.Message import MessageObserver, ProgressObserver

logger = get_logger("opsi.general")

encoding = locale.getpreferredencoding()
try:
	sp = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	if os.path.exists(os.path.join(sp, "site-packages")):
		sp = os.path.join(sp, "site-packages")
	sp = os.path.join(sp, "python-opsi_data", "locale")
	translation = gettext.translation("python-opsi", sp)
	_ = translation.gettext
except Exception as error:
	logger.debug("Failed to load locale from %s: %s", sp, error)

	def _(string):
		"""Fallback function"""
		return string


class MessageBox:
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		pass

	def show(self, seconds: int = 0) -> None:
		pass

	def hide(self) -> None:
		pass

	def setText(self, text: str) -> None:
		pass

	def addText(self, text: str) -> None:
		pass


class ProgressBox(MessageBox):
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		total: int = 100,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		pass

	def setState(self, state: Any) -> None:
		pass

	def getState(self) -> None:
		pass


class CopyProgressBox(ProgressBox):
	pass


class DualProgressBox(MessageBox):
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		total: int = 100,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		pass


class CopyDualProgressBox(DualProgressBox):
	pass


class SnackMessageBox(MessageBox, MessageObserver):
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		MessageObserver.__init__(self)

		try:
			self._ui = ui

			width = forceInt(width)
			height = forceInt(height)
			title = forceUnicode(title)
			text = forceUnicode(text)

			self._visible = False
			self._title = title
			self._text = text

			for string in self._ui.confidentialStrings:
				self._text = self._text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self._ui.getScreen().width - 7
			if height <= 0:
				height = self._ui.getScreen().height - 7

			self._width = width
			self._height = self._textHeight = height

			self._gridForm = GridForm(self._ui.getScreen(), title, 1, 1)
			self._textbox = Textbox(
				self._width, self._height, self._text, scroll=0, wrap=1
			)
			self._gridForm.add(self._textbox, 0, 0)

			# help line
			self._ui.getScreen().pushHelpLine("")
		except Exception as err:
			self._ui.exit()
			logger.error(err, exc_info=True)
			raise

	def show(self, seconds: int = 0) -> None:
		try:
			self._gridForm.draw()
			self._ui.refresh()
			self._visible = True
			if seconds:
				time.sleep(seconds)
				self.hide()
		except Exception as err:
			self._ui.exit()
			logger.error(err, exc_info=True)
			raise

	def hide(self) -> None:
		try:
			if self._visible:
				self._ui.getScreen().popWindow()
			self._visible = False
		except Exception as err:
			self._ui.exit()
			logger.error(err, exc_info=True)
			raise

	def setText(self, text: str) -> None:
		try:
			self._text = forceUnicode(text)
			for string in self._ui.confidentialStrings:
				self._text = self._text.replace(string, "*** confidential ***")

			lines = self._text.split("\n")
			for i, line in enumerate(lines):
				if "\r" in line:
					parts = line.split("\r")
					for j in range(len(parts) - 1, -1, -1):
						if parts[j]:
							lines[i] = parts[j] + "\r"
							break

			if len(lines) > self._textHeight:
				self._text = "\n".join(lines[-1 * self._textHeight :])

			try:
				self._textbox.setText(self._text)
			except Exception as err:
				logger.error(err, exc_info=True)
			self.show()
		except Exception as err:
			self._ui.exit()
			logger.error(err, exc_info=True)
			raise

	def addText(self, text: str) -> None:
		try:
			self.setText(self._text + forceUnicode(text))
		except Exception as err:
			self._ui.exit()
			logger.error(err, exc_info=True)
			raise

	def messageChanged(self, subject: Any, message: str) -> None:
		self.addText("%s\n" % message)


class SnackProgressBox(SnackMessageBox, ProgressBox, ProgressObserver):
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		total: int = 100,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		ProgressObserver.__init__(self)

		self._ui = ui
		width = forceInt(width)
		height = forceInt(height)
		total = forceInt(total)
		title = forceUnicode(title)
		text = forceUnicode(text)

		if width <= 0:
			width = self._ui.getScreen().width - 7
		if height <= 0:
			height = self._ui.getScreen().height - 7

		SnackMessageBox.__init__(self, ui, width, height - 4, title, text)

		self._total = total
		self._state = -1
		self._factor = 1
		self._width = width
		self._height = height

		self._gridForm = GridForm(self._ui.getScreen(), title, 1, 2)
		self._scale = Scale(self._width, self._total)
		self._gridForm.add(self._textbox, 0, 0)
		self._gridForm.add(self._scale, 0, 1)

		self._ui.getScreen().pushHelpLine("")

	def setState(self, state: Any) -> None:
		self._state = state
		self._scale.set(int(self._state * self._factor))
		self.show()

	def getState(self) -> Any:
		return self._state

	def endChanged(self, subject: Any, end: int) -> None:
		if end <= 0 or self._total <= 0:
			self.setState(0)
		else:
			self._factor = self._total / end
			self.setState(self._state)

	def progressChanged(
		self,
		subject: Any,
		state: Any,
		percent: Any,
		timeSpend: Any,
		timeLeft: Any,
		speed: Any,
	) -> None:
		self.setState(state)


class SnackCopyProgressBox(SnackProgressBox):
	def messageChanged(self, subject: Any, message: str) -> None:
		minLeft = 0
		secLeft = subject.getTimeLeft()
		if secLeft >= 60:
			minLeft = int(secLeft // 60)
			secLeft -= minLeft * 60

		if minLeft < 10:
			minLeft = "0%d" % minLeft

		if secLeft < 10:
			secLeft = "0%d" % secLeft

		message = "[%s:%s ETA] %s" % (minLeft, secLeft, message)
		self.addText("%s\n" % message)


class SnackDualProgressBox(SnackMessageBox, ProgressObserver):
	def __init__(
		self,
		ui: Any,
		width: int = 0,
		height: int = 0,
		total: int = 100,
		title: str = _("Title"),
		text: str = "",
	) -> None:
		ProgressObserver.__init__(self)

		self._ui = ui
		width = forceInt(width)
		height = forceInt(height)
		total = forceInt(total)
		title = forceUnicode(title)
		text = forceUnicode(text)

		if width <= 0:
			width = self._ui.getScreen().width - 7
		if height <= 0:
			height = self._ui.getScreen().height - 7

		SnackMessageBox.__init__(self, ui, width, height - 4, title, text)

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

		self._gridForm = GridForm(self._ui.getScreen(), title, 1, 3)
		self._currentScale = Scale(self._width, self._currentTotal)
		self._overallScale = Scale(self._width, self._overallTotal)

		self._gridForm.add(self._textbox, 0, 0)
		self._gridForm.add(self._currentScale, 0, 1)
		self._gridForm.add(self._overallScale, 0, 2)

		self._ui.getScreen().pushHelpLine("")

	def setOverallProgressSubject(self, subject: Any) -> None:
		self._overallProgressSubject = subject
		self._overallProgressSubject.attachObserver(self)

	def setCurrentProgressSubject(self, subject: Any) -> None:
		self._currentProgressSubject = subject
		self._currentProgressSubject.attachObserver(self)

	def setOverallState(self, state: Any) -> None:
		self._overallState = state
		self._overallScale.set(int(self._overallState * self._overallFactor))
		self.show()

	def setCurrentState(self, state: Any) -> None:
		self._currentState = state
		self._currentScale.set(int(self._currentState * self._currentFactor))
		self.show()

	def getState(self) -> Any:
		return self._overallState

	def endChanged(self, subject: Any, end: int) -> None:
		if subject == self._overallProgressSubject:
			if end <= 0 or self._overallTotal <= 0:
				self.setOverallState(0)
			else:
				self._overallFactor = self._overallTotal / end
				self.setOverallState(self._overallState)
		elif subject == self._currentProgressSubject:
			if end <= 0 or self._currentTotal <= 0:
				self.setCurrentState(0)
			else:
				self._currentFactor = self._currentTotal / end
				self.setCurrentState(self._currentState)

	def progressChanged(
		self,
		subject: Any,
		state: Any,
		percent: Any,
		timeSpend: Any,
		timeLeft: Any,
		speed: Any,
	) -> None:
		if subject == self._overallProgressSubject:
			self.setOverallState(state)
		elif subject == self._currentProgressSubject:
			self.setCurrentState(state)


class SnackCopyDualProgressBox(SnackDualProgressBox):
	def messageChanged(self, subject: Any, message: str) -> None:
		minLeft = 0
		secLeft = subject.getTimeLeft()
		if secLeft >= 60:
			minLeft = secLeft // 60
			secLeft -= minLeft * 60
		if minLeft < 10:
			minLeft = "0%d" % minLeft
		if secLeft < 10:
			secLeft = "0%d" % secLeft
		message = "[%s:%s ETA] %s" % (minLeft, secLeft, message)
		self.addText("%s\n" % message)


class UI:
	def __init__(self) -> None:
		self.confidentialStrings = []

	def setConfidentialStrings(self, strings: list[str]) -> None:
		strings = forceUnicodeList(strings)
		self.confidentialStrings = []
		for string in strings:
			self.addConfidentialString(string)

	def addConfidentialString(self, string: str) -> None:
		string = forceUnicode(string)
		if not string:
			raise ValueError("Cannot use empty string as confidential string")
		if string in self.confidentialStrings:
			return
		self.confidentialStrings.append(string)

	def getScreen(self) -> None:
		pass

	def refresh(self) -> None:
		pass

	def getWidth(self) -> int:
		return 0

	def getHeight(self) -> int:
		return 0

	def exit(self) -> None:
		pass

	def drawRootText(self, x: int = 1, y: int = 1, text: str = "") -> None:
		pass

	def showError(
		self,
		text: str,
		title: str = _("An error occurred"),
		okLabel: str = _("OK"),
		width: int = -1,
		height: int = -1,
		seconds: int = 0,
	) -> None:
		pass

	def showMessage(
		self,
		text: str,
		title: str = _("Message"),
		okLabel: str = _("OK"),
		width: int = -1,
		height: int = -1,
		seconds: int = 0,
	) -> None:
		pass

	def createProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Progress"),
		text: str = "",
	) -> ProgressBox:
		return ProgressBox(self)

	def createCopyProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Copy progress"),
		text: str = "",
	) -> CopyProgressBox:
		return CopyProgressBox(self)

	def createDualProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Progress"),
		text: str = "",
	) -> DualProgressBox:
		return DualProgressBox(self)

	def createCopyDualProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Copy progress"),
		text: str = "",
	) -> CopyDualProgressBox:
		return CopyDualProgressBox(self)

	def createMessageBox(
		self,
		width: int = -1,
		height: int = -1,
		title: str = _("Text"),
		text: str = "",
	) -> MessageBox:
		return MessageBox(self)

	def getMessageBox(self) -> MessageBox:
		return MessageBox(self)

	def getValue(
		self,
		width: int = -1,
		height: int = -1,
		title: str = _("Please type text"),
		default: str = "",
		password: bool = False,
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	) -> None:
		return None

	def getSelection(
		self,
		entries: Any,
		radio: bool = False,
		width: int = -1,
		height: int = -1,
		title: str = _("Please select"),
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	) -> List:
		return []

	def getValues(
		self,
		entries: Any,
		width: int = -1,
		height: int = -1,
		title: str = _("Please fill in"),
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	) -> Any:
		return entries

	def yesno(
		self,
		text: str,
		title: str = _("Question"),
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
		width: int = -1,
		height: int = -1,
	) -> bool:
		return True


class SnackUI(UI):
	def __init__(self) -> None:
		super().__init__()

		self._screen = SnackScreen()
		if self._screen.width < 40 or self._screen.height < 24:
			self.exit()
			raise RuntimeError(
				"Display to small (at least 24 lines by 40 columns needed)"
			)
		self.messageBox = None
		self._screen.pushHelpLine("")

		ui_signal.signal(ui_signal.SIGWINCH, self.sigwinchHandler)

	def __del__(self) -> None:
		try:
			self.exit()
		except Exception:
			pass

	def sigwinchHandler(self, signo: Any, stackFrame: Any) -> None:
		self.refresh()

	def getScreen(self) -> SnackScreen:
		return self._screen

	def refresh(self) -> None:
		self._screen.refresh()

	def getWidth(self) -> int:
		return self._screen.width

	def getHeight(self) -> int:
		return self._screen.height

	def exit(self) -> None:
		if self._screen:
			self._screen.finish()

	def drawRootText(self, x: int = 1, y: int = 1, text: str = "") -> None:
		text = forceUnicode(text)
		for string in self.confidentialStrings:
			text = text.replace(string, "*** confidential ***")

		try:
			self._screen.drawRootText(x, y, text)
			self.refresh()
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def showError(
		self,
		text: str,
		title: str = _("An error occurred"),
		okLabel: str = _("OK"),
		width: int = -1,
		height: int = -1,
		seconds: int = 0,
	) -> Any:
		try:
			text = forceUnicode(text)
			title = forceUnicode(title)
			okLabel = forceUnicode(okLabel)
			width = forceInt(width)
			height = forceInt(height)
			seconds = forceInt(seconds)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15
			if height <= 0:
				height = len(text.split("\n")) + 2

			textBox = Textbox(width=width, height=height, text=text, scroll=1, wrap=1)
			button = Button(okLabel)
			rows = 2
			if seconds:
				rows = 1
			gridForm = GridForm(self._screen, title, 1, rows)
			gridForm.add(textBox, 0, 0)
			if seconds:
				gridForm.draw()
				self.refresh()
				time.sleep(seconds)
				self._screen.popWindow()
			else:
				gridForm.add(button, 0, 1)
				helpLine = (
					_("<F12> %s | <Space> select | <Up/Down> scroll text") % okLabel
				)
				self.getScreen().pushHelpLine(forceUnicode(helpLine))
				return gridForm.runOnce()
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def showMessage(
		self,
		text: str,
		title: str = _("Message"),
		okLabel: str = _("OK"),
		width: int = -1,
		height: int = -1,
		seconds: int = 0,
	) -> Any:
		try:
			text = forceUnicode(text)
			title = forceUnicode(title)
			okLabel = forceUnicode(okLabel)
			width = forceInt(width)
			height = forceInt(height)
			seconds = forceInt(seconds)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15
			if height <= 0:
				height = len(text.split("\n")) + 2

			textBox = Textbox(width=width, height=height, text=text, scroll=1, wrap=1)
			button = Button(okLabel)
			rows = 2
			if seconds:
				rows = 1
			gridForm = GridForm(self._screen, title, 1, rows)
			gridForm.add(textBox, 0, 0)
			if seconds:
				gridForm.draw()
				self.refresh()
				time.sleep(seconds)
				self._screen.popWindow()
			else:
				gridForm.add(button, 0, 1)
				helpLine = (
					_("<F12> %s | <Space> select | <Up/Down> scroll text") % okLabel
				)
				self.getScreen().pushHelpLine(forceUnicode(helpLine))
				return gridForm.runOnce()
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def createProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Progress"),
		text: str = "",
	) -> SnackProgressBox:
		try:
			width = forceInt(width)
			height = forceInt(height)
			total = forceInt(total)
			title = forceUnicode(title)
			text = forceUnicode(text)

			progressBox = SnackProgressBox(
				ui=self, width=width, height=height, total=total, title=title, text=text
			)
			return progressBox
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def createCopyProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Copy progress"),
		text: str = "",
	) -> SnackCopyProgressBox:
		try:
			width = forceInt(width)
			height = forceInt(height)
			total = forceInt(total)
			title = forceUnicode(title)
			text = forceUnicode(text)

			progressBox = SnackCopyProgressBox(
				ui=self, width=width, height=height, total=total, title=title, text=text
			)
			return progressBox
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def createDualProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Progress"),
		text: str = "",
	) -> SnackDualProgressBox:
		try:
			width = forceInt(width)
			height = forceInt(height)
			total = forceInt(total)
			title = forceUnicode(title)
			text = forceUnicode(text)

			dualProgressBox = SnackDualProgressBox(
				ui=self, width=width, height=height, total=total, title=title, text=text
			)
			return dualProgressBox
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def createCopyDualProgressBox(
		self,
		width: int = -1,
		height: int = -1,
		total: int = 100,
		title: str = _("Copy progress"),
		text: str = "",
	) -> SnackCopyDualProgressBox:
		try:
			width = forceInt(width)
			height = forceInt(height)
			total = forceInt(total)
			title = forceUnicode(title)
			text = forceUnicode(text)

			progressBox = SnackCopyDualProgressBox(
				ui=self, width=width, height=height, total=total, title=title, text=text
			)
			return progressBox
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def createMessageBox(
		self, width: int = -1, height: int = -1, title: str = _("Text"), text: str = ""
	) -> SnackMessageBox:
		width = forceInt(width)
		height = forceInt(height)
		title = forceUnicode(title)
		text = forceUnicode(text)

		self.messageBox = SnackMessageBox(
			ui=self, width=width, height=height, title=title, text=text
		)
		return self.messageBox

	def getMessageBox(self) -> SnackMessageBox:
		if not self.messageBox:
			self.createMessageBox()
		return self.messageBox

	def getValue(
		self,
		width: int = -1,
		height: int = -1,
		title: str = _("Please type text"),
		default: str = "",
		password: bool = False,
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	) -> Any:
		try:
			width = forceInt(width)
			height = forceInt(height)
			title = forceUnicode(title)
			default = forceUnicode(default)
			password = forceBool(password)
			text = forceUnicode(text)
			okLabel = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15

			# create text grid
			textGrid = Grid(1, 1)
			if text:
				textHeight = 0
				if height <= 0:
					height = self.getScreen().height - 15
					textHeight = height - 5
					if textHeight < 2:
						textHeight = 2
					elif textHeight > len(text.split("\n")) + 1:
						textHeight = len(text.split("\n")) + 1
				else:
					textHeight = height - len(text.split("\n")) + 1

				textBox = Textbox(
					width=width, height=textHeight, text=text, scroll=1, wrap=1
				)
				textGrid.setField(textBox, col=0, row=0)

			# create grid for input
			entryGrid = Grid(1, 1)
			entry = Entry(
				width=width,
				text=default,
				hidden=False,
				password=password,
				scroll=1,
				returnExit=0,
			)
			entryGrid.setField(entry, col=0, row=0, padding=(0, 0, 0, 0))

			# create grid for buttons
			buttonsGrid = Grid(2, 1)

			cancelButton = Button(cancelLabel)
			buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))

			okButton = Button(okLabel)
			buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))

			gridForm = GridForm(self._screen, title, 1, 3)
			gridForm.add(textGrid, col=0, row=0, padding=(0, 0, 0, 1))
			gridForm.add(entryGrid, col=0, row=1, padding=(0, 0, 0, 1))
			gridForm.add(buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))
			gridForm.addHotKey("ESC")

			# help line
			helpLine = _("<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (
				cancelLabel,
				okLabel,
			)
			if text:
				helpLine += _(" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine))

			# run
			gridForm.addHotKey("ESC")
			gridForm.draw()
			buttonPressed = None
			while buttonPressed not in [okButton, "F12", cancelButton, "ESC"]:
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if buttonPressed not in [okButton, "F12"]:
				return None

			return entry.value()
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def getSelection(
		self,
		entries: list[Any],
		radio: bool = False,
		width: int = -1,
		height: int = -1,
		title: str = _("Please select"),
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	) -> list[Any]:
		try:
			entries = forceList(entries)
			radio = forceBool(radio)
			width = forceInt(width)
			height = forceInt(height)
			title = forceUnicode(title)
			text = forceUnicode(text)
			okLabel = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15

			if height <= 14:
				height = 13 + len(entries)
				if text:
					height += len(text.split("\n")) + 1
				if height > self.getScreen().height - 5:
					height = self.getScreen().height - 5

			entriesHeight = len(entries)
			if entriesHeight > height - 13:
				entriesHeight = height - 13

			# create text grid
			textGrid = Grid(1, 1)
			if text:
				textHeight = len(text.split("\n")) + 1
				diff = textHeight + entriesHeight + 13 - height
				if diff > 0:
					entriesHeight -= diff
					if entriesHeight < 3:
						textHeight = textHeight - 3 + entriesHeight
						entriesHeight = 3

				textBox = Textbox(
					width=width, height=textHeight, text=text, scroll=1, wrap=1
				)
				textGrid.setField(textBox, col=0, row=0)

			# create widget for entries
			entriesWidget = None
			if radio:
				entriesWidget = Listbox(
					height=entriesHeight, scroll=1, returnExit=0, width=0, showCursor=0
				)
			else:
				entriesWidget = CheckboxTree(height=entriesHeight, scroll=1)

			row = 0
			numSelected = 0
			for i, entry in enumerate(entries):
				selected = forceBool(entry.get("selected", False))
				if radio and (numSelected >= 1):
					selected = False
				if selected:
					numSelected += 1
				if radio:
					entriesWidget.append(
						text=forceUnicode(entry.get("name", "???")), item=i
					)
					if selected:
						entriesWidget.setCurrent(i)
				else:
					entriesWidget.append(
						text=forceUnicode(entry.get("name", "???")),
						item=i,
						selected=selected,
					)
				row += 1

			# create grid for buttons
			buttonsGrid = Grid(2, 1)

			cancelButton = Button(cancelLabel)
			buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))

			okButton = Button(okLabel)
			buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))

			gridForm = GridForm(self._screen, title, 1, 3)
			gridForm.add(textGrid, col=0, row=0, padding=(0, 0, 0, 1))
			gridForm.add(entriesWidget, col=0, row=1, padding=(0, 0, 0, 1))
			gridForm.add(buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))

			# help line
			helpLine = _("<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (
				cancelLabel,
				okLabel,
			)
			if text:
				helpLine += _(" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine))

			# run
			gridForm.addHotKey("ESC")
			gridForm.draw()
			buttonPressed = None
			while buttonPressed not in [okButton, "F12", cancelButton, "ESC"]:
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if buttonPressed not in [okButton, "F12"]:
				return None

			result = []
			if radio:
				result.append(entries[entriesWidget.current()]["name"])
			else:
				for sel in entriesWidget.getSelection():
					result.append(entries[sel]["name"])
			return result
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def getValues(
		self,
		entries: list[Any],
		width: int = -1,
		height: int = -1,
		title: str = _("Please fill in"),
		text: str = "",
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
	):
		try:
			entries = forceList(entries)
			width = forceInt(width)
			height = forceInt(height)
			title = forceUnicode(title)
			text = forceUnicode(text)
			okLabel = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15

			if height <= 0:
				height = 11 + len(entries)
				if text:
					height += len(text.split("\n"))
				if height > self.getScreen().height - 10:
					height = self.getScreen().height - 10

			# create text grid
			textGrid = Grid(1, 1)
			if text:
				textHeight = len(text.split("\n"))
				diff = textHeight + len(entries) + 11 - height
				if diff > 0:
					textHeight -= diff
				if textHeight > 0:
					textBox = Textbox(
						width=width, height=textHeight, text=text, scroll=1, wrap=1
					)
					textGrid.setField(textBox, col=0, row=0)

			# create grid for entries
			entriesGrid = Grid(2, len(entries))

			row = 0
			labelWidth = 10
			for entry in entries:
				entryLength = len(entry.get("name", ""))
				if entryLength > labelWidth:
					labelWidth = entryLength

			width = width - labelWidth
			if width < 5:
				width = 5
			for entry in entries:
				label = Label(forceUnicode(entry.get("name", "???")))
				value = forceUnicodeList(entry.get("value"))
				value = ", ".join(value)
				entry["entry"] = Entry(
					width=width,
					text=value,
					hidden=entry.get("hidden", False),
					password=entry.get("password", False),
					scroll=1,
					returnExit=0,
				)
				entriesGrid.setField(
					label, col=0, row=row, anchorLeft=1, padding=(2, 0, 1, 0)
				)
				entriesGrid.setField(
					entry["entry"], col=1, row=row, anchorRight=1, padding=(1, 0, 2, 0)
				)
				row += 1

			# create grid for buttons
			buttonsGrid = Grid(2, 1)

			cancelButton = Button(cancelLabel)
			buttonsGrid.setField(cancelButton, col=0, row=0, padding=(0, 0, 10, 0))

			okButton = Button(okLabel)
			buttonsGrid.setField(okButton, col=1, row=0, padding=(10, 0, 0, 0))

			gridForm = GridForm(self._screen, title, 1, 3)
			gridForm.add(textGrid, col=0, row=0, padding=(0, 0, 0, 1))
			gridForm.add(entriesGrid, col=0, row=1, padding=(0, 0, 0, 1))
			gridForm.add(buttonsGrid, col=0, row=2, padding=(0, 0, 0, 0))

			# help line
			helpLine = _("<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (
				cancelLabel,
				okLabel,
			)
			if text:
				helpLine += _(" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine))

			# run
			gridForm.addHotKey("ESC")
			gridForm.draw()
			buttonPressed = None
			while buttonPressed not in [okButton, "F12", cancelButton, "ESC"]:
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if buttonPressed not in [okButton, "F12"]:
				return None

			for i in range(len(entries)):
				value = entries[i]["entry"].value()
				if entries[i].get("multivalue") and "," in value:
					value = [x.strip() for x in value.split(",")]

				entries[i]["value"] = value
				del entries[i]["entry"]
			return entries
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise

	def yesno(
		self,
		text: str,
		title: str = _("Question"),
		okLabel: str = _("OK"),
		cancelLabel: str = _("Cancel"),
		width: int = -1,
		height: int = -1,
	) -> bool:
		try:
			text = forceUnicode(text)
			title = forceUnicode(title)
			okLabel = forceUnicode(okLabel)
			cancelLabel = forceUnicode(cancelLabel)
			width = forceInt(width)
			height = forceInt(height)

			for string in self.confidentialStrings:
				text = text.replace(string, "*** confidential ***")

			if width <= 0:
				width = self.getScreen().width - 15
				if width > len(text) + 5:
					width = len(text) + 5
			if height <= 0:
				height = 10

			gridForm = GridForm(self._screen, title, 1, 2)

			textBox = Textbox(
				width=width, height=height - 6, text=text, scroll=1, wrap=1
			)
			gridForm.add(textBox, col=0, row=0)

			grid = Grid(2, 1)
			cancelButton = Button(cancelLabel)
			grid.setField(cancelButton, 0, 0, (0, 0, 5, 0))
			okButton = Button(okLabel)
			grid.setField(okButton, 1, 0, (5, 0, 0, 0))
			gridForm.add(grid, col=0, row=1)

			# help line
			helpLine = _("<ESC> %s | <F12> %s | <Tab> move cursor | <Space> select") % (
				cancelLabel,
				okLabel,
			)
			if text:
				helpLine += _(" | <Up/Down> scroll text")
			self.getScreen().pushHelpLine(forceUnicode(helpLine))

			# run
			gridForm.addHotKey("ESC")
			gridForm.draw()
			buttonPressed = None
			while buttonPressed not in (okButton, "F12", cancelButton, "ESC"):
				buttonPressed = gridForm.run()
			self._screen.popWindow()
			if buttonPressed in (okButton, "F12"):
				return True
			return False
		except Exception as err:
			self.exit()
			logger.error(err, exc_info=True)
			raise


def UIFactory(type: str = "") -> UI:
	uiType = forceUnicode(type)
	if uiType in ("snack", "SnackUI"):
		return SnackUI()
	if uiType in ("dummy", "UI"):
		return UI()

	try:
		return SnackUI()
	except Exception as err:
		logger.warning("Failed to create SnackUI: %s", err)
		return UI()
