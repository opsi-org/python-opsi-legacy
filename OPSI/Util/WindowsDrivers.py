# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Functions to work with Windows drivers.
"""

import codecs
import os
import re

from opsicommon.logging import get_logger

from OPSI import System
from OPSI.Object import AuditHardware, AuditHardwareOnHost
from OPSI.Types import (
	forceFilename,
	forceInt,
	forceList,
	forceObjectClassList,
	forceUnicode,
	forceUnicodeList,
)
from OPSI.Util import findFilesGenerator
from OPSI.Util.File import InfFile, TxtSetupOemFile
from OPSI.Util.Repository import Repository

logger = get_logger("opsi.general")


def searchWindowsDrivers(
	driverDir, auditHardwares, messageSubject=None, srcRepository=None
):
	driverDir = forceFilename(driverDir)
	try:
		auditHardwares = forceObjectClassList(auditHardwares, AuditHardware)
	except Exception:
		auditHardwares = forceObjectClassList(auditHardwares, AuditHardwareOnHost)

	exists = os.path.exists
	listdir = os.listdir
	if srcRepository:
		if not isinstance(srcRepository, Repository):
			raise TypeError(f"Not a repository: {srcRepository}")
		exists = srcRepository.exists
		listdir = srcRepository.listdir

	drivers = []
	for auditHardware in auditHardwares:
		hwClass = auditHardware.getHardwareClass()
		baseDir = ""
		if hwClass == "PCI_DEVICE":
			baseDir = "pciids"
		elif hwClass == "USB_DEVICE":
			baseDir = "usbids"
		elif hwClass == "HDAUDIO_DEVICE":
			baseDir = "hdaudioids"
		else:
			logger.debug(
				"Skipping unhandled hardware class '%s' (%s)", hwClass, auditHardware
			)
			continue

		if not hasattr(auditHardware, "vendorId") or not auditHardware.vendorId:
			logger.debug(
				"Skipping %s device %s: vendor id not found", hwClass, auditHardware
			)
			continue
		if not hasattr(auditHardware, "deviceId") or not auditHardware.deviceId:
			logger.debug(
				"Skipping %s device %s: device id not found", hwClass, auditHardware
			)
			continue

		name = "unknown"
		try:
			if auditHardware.name:
				name = auditHardware.name.replace("/", "_")
		except AttributeError:
			pass

		logger.info(
			"Searching driver for %s '%s', id '%s:%s'",
			hwClass,
			name,
			auditHardware.vendorId,
			auditHardware.deviceId,
		)
		if messageSubject:
			messageSubject.setMessage(
				f"Searching driver for {hwClass} '{name}', id '{auditHardware.vendorId}:{auditHardware.deviceId}'"
			)

		driver = {
			"directory": None,
			"buildin": False,
			"textmode": False,
			"vendorId": auditHardware.vendorId,
			"deviceId": auditHardware.deviceId,
			"hardwareInfo": auditHardware,
		}
		srcDriverPath = os.path.join(driverDir, baseDir, auditHardware.vendorId)
		if not exists(srcDriverPath):
			logger.error("%s vendor directory '%s' not found", hwClass, srcDriverPath)
			continue

		srcDriverPath = os.path.join(srcDriverPath, auditHardware.deviceId)
		if not exists(srcDriverPath):
			logger.error("%s device directory '%s' not found", hwClass, srcDriverPath)
			continue

		if exists(os.path.join(srcDriverPath, "WINDOWS_BUILDIN")):
			logger.notice("Found windows built-in driver")
			driver["buildin"] = True
			drivers.append(driver)
			continue

		logger.notice(
			"Found driver for %s device '%s', in dir '%s'", hwClass, name, srcDriverPath
		)
		driver["directory"] = srcDriverPath

		for entry in listdir(srcDriverPath):
			if entry.lower() == "txtsetup.oem":
				driver["textmode"] = True
				break

		if not driver["textmode"]:
			srcDriverPath = os.path.dirname(srcDriverPath)
			for entry in listdir(srcDriverPath):
				if entry.lower() == "txtsetup.oem":
					driver["directory"] = srcDriverPath
					driver["textmode"] = True
					break
		drivers.append(driver)
	return drivers


def integrateWindowsDrivers(
	driverSourceDirectories,
	driverDestinationDirectory,
	messageSubject=None,
	srcRepository=None,
	drivers=None,
	checkDups=False,
):
	driverSourceDirectories = forceUnicodeList(driverSourceDirectories)
	driverDestinationDirectory = forceFilename(driverDestinationDirectory)

	if not driverSourceDirectories:
		logger.warning("No driver source directories passed")
		return []

	driversOnMachine = {}
	if drivers:
		for driver in drivers:
			vendorId = driver.get("vendorId", "")
			deviceId = driver.get("deviceId", "")
			if not vendorId or not deviceId:
				continue
			if vendorId not in driversOnMachine:
				driversOnMachine[vendorId] = []
			driversOnMachine[vendorId].append(deviceId)

	exists = os.path.exists
	copy = System.copy
	if srcRepository:
		if not isinstance(srcRepository, Repository):
			raise TypeError(f"Not a repository: {srcRepository}")
		exists = srcRepository.exists
		copy = srcRepository.copy

	logger.info("Integrating drivers: %s", driverSourceDirectories)

	if messageSubject:
		messageSubject.setMessage("Integrating drivers")

	System.mkdir(driverDestinationDirectory)
	driverNumber = 0
	for filename in os.listdir(driverDestinationDirectory):
		dirname = os.path.join(driverDestinationDirectory, filename)
		if not os.path.isdir(dirname):
			continue
		if re.search(r"^\d+$", filename):
			if forceInt(filename) >= driverNumber:
				driverNumber = forceInt(filename)

	integratedDrivers = {}
	infFiles = list(
		findFilesGenerator(
			directory=driverDestinationDirectory,
			prefix=driverDestinationDirectory,
			includeFile=re.compile(r"\.inf$", re.IGNORECASE),
			returnDirs=False,
			followLinks=True,
		)
	)
	logger.debug(
		"Found inf files: %s in dir '%s'", infFiles, driverDestinationDirectory
	)
	for infFile in infFiles:
		infFile = InfFile(infFile)
		for dev in infFile.getDevices():
			if dev["type"] not in integratedDrivers:
				integratedDrivers[dev["type"]] = {}
			if dev["vendor"] not in integratedDrivers[dev["type"]]:
				integratedDrivers[dev["type"]][dev["vendor"]] = []
			if dev["device"] in integratedDrivers[dev["type"]][dev["vendor"]]:
				continue
			integratedDrivers[dev["type"]][dev["vendor"]].append(dev["device"])
			logger.debug(
				"Integrated driver for %s device %s:%s, infFile: %s found.",
				dev["type"],
				dev["vendor"],
				dev["device"],
				os.path.abspath(infFile.getFilename()),
			)

	newDrivers = []
	for driverSourceDirectory in driverSourceDirectories:
		logger.notice("Integrating driver dir '%s'", driverSourceDirectory)
		if messageSubject:
			messageSubject.setMessage(
				f"Integrating driver dir '{os.path.basename(driverSourceDirectory)}'"
			)
		if not exists(driverSourceDirectory):
			logger.error("Driver directory '%s' not found", driverSourceDirectory)
			if messageSubject:
				messageSubject.setMessage(
					f"Driver directory '{driverSourceDirectory}' not found"
				)
			continue
		driverNeeded = True
		newDriversTmp = []
		infFiles = list(
			findFilesGenerator(
				directory=driverSourceDirectory,
				prefix=driverSourceDirectory,
				includeFile=re.compile(r"\.inf$", re.IGNORECASE),
				returnDirs=False,
				followLinks=True,
				repository=srcRepository,
			)
		)

		for infFile in infFiles:
			tempInfFile = None
			if srcRepository:
				tempInfFile = "/tmp/temp.inf"
				copy(infFile, tempInfFile)
				infFile = InfFile(tempInfFile)
			else:
				infFile = InfFile(infFile)
			devices = infFile.getDevices()
			newDriversTmp.append(
				{"devices": devices, "infFile": os.path.basename(infFile.getFilename())}
			)
			if checkDups:
				for dev in devices:
					if dev["device"] not in driversOnMachine.get(dev["vendor"], []):
						continue
					if dev["device"] in integratedDrivers.get(dev["type"], {}).get(
						dev["vendor"], []
					):
						logger.notice(
							"Driver for %s device %s:%s already integrated",
							dev["type"],
							dev["vendor"],
							dev["device"],
						)
						driverNeeded = False
					else:
						driverNeeded = True
					break
			if tempInfFile:
				os.remove(tempInfFile)
			if not driverNeeded:
				break

		if driverNeeded:
			driverNumber += 1
			dstDriverPath = os.path.join(
				driverDestinationDirectory, forceUnicode(driverNumber)
			)
			if not os.path.exists(dstDriverPath):
				os.mkdir(dstDriverPath)

			copy(driverSourceDirectory + "/*", dstDriverPath)
			for idx, driver in enumerate(newDriversTmp):
				newDriversTmp[idx]["driverNumber"] = driverNumber
				newDriversTmp[idx]["directory"] = dstDriverPath
				newDriversTmp[idx]["infFile"] = os.path.join(
					dstDriverPath, driver["infFile"]
				)
				for dev in driver["devices"]:
					if dev["type"] not in integratedDrivers:
						integratedDrivers[dev["type"]] = {}
					if dev["vendor"] not in integratedDrivers[dev["type"]]:
						integratedDrivers[dev["type"]][dev["vendor"]] = []
					integratedDrivers[dev["type"]][dev["vendor"]].append(dev["device"])
			newDrivers.extend(newDriversTmp)
	return newDrivers


def integrateWindowsHardwareDrivers(
	driverSourceDirectory,
	driverDestinationDirectory,
	auditHardwares,
	messageSubject=None,
	srcRepository=None,
):
	logger.info("Adding drivers for detected hardware")

	driverSourceDirectory = forceFilename(driverSourceDirectory)
	driverDestinationDirectory = forceFilename(driverDestinationDirectory)
	try:
		auditHardwares = forceObjectClassList(auditHardwares, AuditHardware)
	except Exception:
		auditHardwares = forceObjectClassList(auditHardwares, AuditHardwareOnHost)

	drivers = searchWindowsDrivers(
		driverDir=driverSourceDirectory,
		auditHardwares=auditHardwares,
		messageSubject=messageSubject,
		srcRepository=srcRepository,
	)

	driverDirectories = []
	for driver in drivers:
		if driver["buildin"] or not driver["directory"]:
			continue

		logger.debug("Got windows driver: %s", driver)

		if driver["directory"] not in driverDirectories:
			driverDirectories.append(driver["directory"])

		name = f"[{driver['vendorId']}:{driver['deviceId']}]"
		try:
			name += f" {driver['hardwareInfo'].vendor}"
		except AttributeError:
			pass

		try:
			name += f" : {driver['hardwareInfo'].name}"
		except AttributeError:
			pass

		logger.notice("Integrating driver for device %s", name)
		if messageSubject:
			messageSubject.setMessage(f"Integrating driver for device {name}")

	if not driverDirectories:
		logger.debug("No driver directories to integrate")
		return []

	return integrateWindowsDrivers(
		driverDirectories,
		driverDestinationDirectory,
		messageSubject=messageSubject,
		srcRepository=srcRepository,
		drivers=drivers,
		checkDups=True,
	)


def integrateWindowsTextmodeDrivers(
	driverDirectory, destination, devices, sifFile=None, messageSubject=None
):
	driverDirectory = forceFilename(driverDirectory)
	destination = forceFilename(destination)
	devices = forceList(devices)

	logger.notice("Integrating textmode drivers")

	if not os.path.exists(driverDirectory):
		logger.notice("Driver directory '%s' does not exist", driverDirectory)
		return

	if messageSubject:
		messageSubject.setMessage("Integrating textmode drivers")

	logger.info("Searching for txtsetup.oem in '%s'", driverDirectory)
	txtSetupOems = list(
		findFilesGenerator(
			directory=driverDirectory,
			prefix=driverDirectory,
			includeFile=re.compile(r"^txtsetup\.oem$", re.IGNORECASE),
			returnDirs=False,
		)
	)
	if not txtSetupOems:
		logger.info("No txtsetup.oem found in '%s'", driverDirectory)
		return

	for txtSetupOem in txtSetupOems:
		logger.info("File '%s' found", txtSetupOem)
		txtSetupOemFile = TxtSetupOemFile(txtSetupOem)
		driverPath = os.path.dirname(txtSetupOem)
		supportedDevice = None
		deviceKnown = None
		for device in devices:
			logger.trace(
				"Testing if textmode driver '%s' supports device %s", driverPath, device
			)
			try:
				deviceKnown = txtSetupOemFile.isDeviceKnown(
					vendorId=device.get("vendorId"), deviceId=device.get("deviceId")
				)
			except Exception as err:
				logger.critical(
					"Error by integrating TextMode driver, error was: %s", err
				)

			if deviceKnown:
				logger.debug(
					"Textmode driver '%s' supports device %s", driverPath, device
				)
				supportedDevice = device
				break
			logger.trace(
				"Textmode driver '%s' does not support device %s", driverPath, device
			)
			continue
		if not supportedDevice:
			logger.trace("Textmode driver '%s' not needed", driverPath)
			continue

		logger.notice("Integrating textmode driver '%s'", driverPath)
		if messageSubject:
			messageSubject.setMessage(f"Integrating textmode driver '{driverPath}'")

		oemBootFiles = []
		for fn in txtSetupOemFile.getFilesForDevice(
			vendorId=supportedDevice["vendorId"],
			deviceId=supportedDevice["deviceId"],
			fileTypes=["inf", "driver", "catalog", "dll"],
		):
			System.copy(
				os.path.join(driverPath, fn),
				os.path.join(destination, "$", "textmode", os.path.basename(fn)),
			)
			System.copy(
				os.path.join(driverPath, fn),
				os.path.join(destination, "$win_nt$.~bt", "$oem$", fn),
			)
			oemBootFiles.append(fn)

		# Apply workarounds for windows setup errors
		txtSetupOemFile.applyWorkarounds()
		txtSetupOemFile.generate()

		oemBootFiles.append(os.path.basename(txtSetupOem))
		for textmodePath in (
			os.path.join(destination, "$", "textmode"),
			os.path.join(destination, "$win_nt$.~bt", "$oem$"),
		):
			System.mkdir(textmodePath)
			System.copy(txtSetupOem, textmodePath)

		description = txtSetupOemFile.getComponentOptionsForDevice(
			vendorId=supportedDevice["vendorId"], deviceId=supportedDevice["deviceId"]
		)["description"]

		# Patch winnt.sif
		if sifFile:
			logger.notice("Registering textmode drivers in sif file '%s'", sifFile)
			lines = []
			massStorageDriverLines = []
			oemBootFileLines = []
			section = ""
			with codecs.open(sifFile, "r", "cp1250") as sif:
				for line in sif.readlines():
					if line.strip():
						logger.trace("Current sif file content: %s", line.rstrip())
					if line.strip().startswith("["):
						section = line.strip().lower()[1:-1]
						if section in ("massstoragedrivers", "oembootfiles"):
							continue
					if section == "massstoragedrivers":
						massStorageDriverLines.append(line)
						continue
					if section == "oembootfiles":
						oemBootFileLines.append(line)
						continue
					lines.append(line)

			logger.info("Patching sections for driver '%s'", description)

			if not massStorageDriverLines:
				massStorageDriverLines = ["\r\n", "[MassStorageDrivers]\r\n"]
			massStorageDriverLines.append(f'"{description}" = "OEM"\r\n')

			if not oemBootFileLines:
				oemBootFileLines = ["\r\n", "[OEMBootFiles]\r\n"]
			for obf in oemBootFiles:
				oemBootFileLines.append(f"{obf}\r\n")

			logger.debug("Patching [MassStorageDrivers] in file '%s':", sifFile)
			logger.debug(massStorageDriverLines)
			lines.extend(massStorageDriverLines)
			logger.debug("Patching [OEMBootFiles] in file '%s':", sifFile)
			logger.debug(oemBootFileLines)
			lines.extend(oemBootFileLines)

			with codecs.open(sifFile, "w", "cp1250") as sif:
				sif.writelines(lines)


def integrateAdditionalWindowsDrivers(
	driverSourceDirectory,
	driverDestinationDirectory,
	additionalDrivers,
	messageSubject=None,
	srcRepository=None,
	auditHardwareOnHosts=None,
):
	driverSourceDirectory = forceFilename(driverSourceDirectory)
	driverDestinationDirectory = forceFilename(driverDestinationDirectory)
	if not isinstance(additionalDrivers, list):
		additionalDrivers = [
			additionalDriver.strip()
			for additionalDriver in forceUnicodeList(additionalDrivers.split(","))
		]
	else:
		additionalDrivers = forceUnicodeList(additionalDrivers)

	if not auditHardwareOnHosts:
		auditHardwareOnHosts = []

	exists = os.path.exists
	listdir = os.listdir
	if srcRepository:
		if not isinstance(srcRepository, Repository):
			raise TypeError(f"Not a repository: {srcRepository}")
		exists = srcRepository.exists
		listdir = srcRepository.listdir

	logger.info("Adding additional drivers")

	if messageSubject:
		messageSubject.setMessage("Adding additional drivers")

	rulesdir = os.path.join(driverSourceDirectory, "byAudit")

	auditInfoByClass = {}
	for auditHardwareOnHost in auditHardwareOnHosts:
		if auditHardwareOnHost.hardwareClass not in ("COMPUTER_SYSTEM", "BASE_BOARD"):
			continue
		if auditHardwareOnHost.hardwareClass not in auditInfoByClass:
			auditInfoByClass[auditHardwareOnHost.hardwareClass] = auditHardwareOnHost

	invalidCharactersRegex = re.compile(r'[<>?":|\\/*]')
	byAuditIntegrated = False
	if exists(rulesdir) and "COMPUTER_SYSTEM" in auditInfoByClass:
		logger.info(
			"Checking if automated integrating of additional drivers are possible"
		)
		auditHardwareOnHost = auditInfoByClass["COMPUTER_SYSTEM"]
		vendorFromHost = invalidCharactersRegex.sub(
			"_", auditHardwareOnHost.vendor or ""
		)
		modelFromHost = invalidCharactersRegex.sub("_", auditHardwareOnHost.model or "")
		skuFromHost = auditHardwareOnHost.sku or ""
		skuLabel = ""
		fallbackPath = ""

		if vendorFromHost and modelFromHost:
			logger.notice(
				"Additional drivers for integration found using byAudit (System) for vendor: "
				"'%s' model : '%s' Check if drivers are available.",
				vendorFromHost,
				modelFromHost,
			)

			vendordirectories = listdir(rulesdir)
			if vendorFromHost not in vendordirectories:
				if vendorFromHost.endswith((".", " ")):
					vendorFromHost = f"{vendorFromHost[:-1]}_"

			for vendordirectory in vendordirectories:
				logger.info("ByAudit: Checking Vendor directory: %s", vendordirectory)
				if vendordirectory.lower() == vendorFromHost.lower():
					modeldirectories = listdir(os.path.join(rulesdir, vendordirectory))
					if skuFromHost and skuFromHost in modelFromHost:
						skuLabel = f"({skuFromHost})"
					if modelFromHost not in modeldirectories:
						if modelFromHost.endswith((".", " ")):
							modelFromHost = f"{modelFromHost[:-1]}_"
					modeldirectory = None
					for modeldirectory in modeldirectories:
						logger.info(
							"ByAudit: Checking Model directory: %s", vendordirectory
						)
						if modeldirectory.lower() == modelFromHost.lower():
							logger.info("ByAudit: Exact match found.")
							additionalDrivers.append(
								os.path.join("byAudit", vendordirectory, modeldirectory)
							)
							byAuditIntegrated = True
							break
						if (
							modeldirectory.lower()
							== modelFromHost.replace(skuLabel, "").strip().lower()
						):
							fallbackPath = os.path.join(
								"byAudit", vendordirectory, modeldirectory
							)
					if not byAuditIntegrated and fallbackPath:
						logger.info(
							"ByAudit: No Exact match found but model without sku found. Using Directory: '%s'",
							modeldirectory,
						)
						additionalDrivers.append(fallbackPath)
						byAuditIntegrated = True
					break

	if not byAuditIntegrated and exists(rulesdir) and "BASE_BOARD" in auditInfoByClass:
		logger.info(
			"Checking if mainboard-fallback for automated integrating of additional drivers are possible"
		)
		auditHardwareOnHost = auditInfoByClass["BASE_BOARD"]
		vendorFromHost = invalidCharactersRegex.sub(
			"_", auditHardwareOnHost.vendor or ""
		)
		productFromHost = invalidCharactersRegex.sub(
			"_", auditHardwareOnHost.product or ""
		)

		if vendorFromHost and productFromHost:
			logger.notice(
				"Additional drivers for integration found using byAudit (Board) for vendor: '%s' model : '%s' Check if drivers are available.",
				vendorFromHost,
				modelFromHost,
			)

			vendordirectories = listdir(rulesdir)
			if vendorFromHost not in vendordirectories:
				if vendorFromHost.endswith((".", " ")):
					vendorFromHost = f"{vendorFromHost[:-1]}_"

			for vendordirectory in vendordirectories:
				if vendordirectory.lower() == vendorFromHost.lower():
					productdirectories = listdir(
						os.path.join(rulesdir, vendordirectory)
					)
					if productFromHost not in productdirectories:
						if productFromHost.endswith((".", " ")):
							productFromHost = f"{productFromHost[:-1]}_"

					for productdirectory in productdirectories:
						if productdirectory.lower() == productFromHost.lower():
							additionalDrivers.append(
								os.path.join(
									"byAudit", vendordirectory, productdirectory
								)
							)

	driverDirectories = []
	for additionalDriver in additionalDrivers:
		if not additionalDriver:
			continue
		additionalDriverDir = os.path.join(driverSourceDirectory, additionalDriver)
		if not exists(additionalDriverDir):
			logger.error("Additional drivers dir '%s' not found", additionalDriverDir)
			if messageSubject:
				messageSubject.setMessage(
					f"Additional drivers dir '{additionalDriverDir}' not found"
				)
			continue
		infFiles = list(
			findFilesGenerator(
				directory=additionalDriverDir,
				prefix=additionalDriverDir,
				includeFile=re.compile(r"\.inf$", re.IGNORECASE),
				returnDirs=False,
				followLinks=True,
				repository=srcRepository,
			)
		)
		logger.info("Found inf files: %s in dir '%s'", infFiles, additionalDriverDir)
		if not infFiles:
			logger.error("No drivers found in dir '%s'", additionalDriverDir)
			if messageSubject:
				messageSubject.setMessage(
					f"No drivers found in dir '{additionalDriverDir}'"
				)
			continue
		for infFile in infFiles:
			additionalDriverDir = os.path.dirname(infFile)
			parentDir = os.path.dirname(additionalDriverDir)
			try:
				for entry in listdir(parentDir):
					if entry.lower() == "txtsetup.oem":
						additionalDriverDir = parentDir
						break
			except Exception as err:
				logger.debug(err)

			if additionalDriverDir in driverDirectories:
				continue
			logger.info("Adding additional driver dir '%s'", additionalDriverDir)
			if messageSubject:
				messageSubject.setMessage(
					f"Adding additional driver dir '{additionalDriverDir}'"
				)
			driverDirectories.append(additionalDriverDir)

	if not driverDirectories:
		logger.debug("No additional driver directories to integrate")
		return []

	return integrateWindowsDrivers(
		driverDirectories,
		driverDestinationDirectory,
		messageSubject=messageSubject,
		srcRepository=srcRepository,
	)


def getOemPnpDriversPath(
	driverDirectory, target, separator=";", prePath="", postPath=""
):
	logger.info("Generating oemPnpDriversPath")
	if not driverDirectory.startswith(target):
		raise TypeError(
			f"Driver directory '{driverDirectory}' not on target '{target}'"
		)

	relPath = driverDirectory[len(target) :]
	while relPath.startswith(os.sep):
		relPath = relPath[1:]
	while relPath.endswith(os.sep):
		relPath = relPath[:-1]
	relPath = "\\".join(relPath.split(os.sep))
	oemPnpDriversPath = ""
	if os.path.exists(driverDirectory):
		for dirname in os.listdir(driverDirectory):
			dirname = relPath + "\\" + dirname
			if prePath:
				dirname = prePath + "\\" + dirname
			if postPath:
				dirname = postPath + "\\" + dirname
			if oemPnpDriversPath:
				oemPnpDriversPath += separator
			oemPnpDriversPath += dirname
	logger.info("Returning oemPnpDriversPath '%s'", oemPnpDriversPath)
	return oemPnpDriversPath
