#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = =
   =   opsi python library - Inf     =
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
import os, codecs, re

# OPSI imports
from Text import TextFile
from OPSI.Logger import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                       CLASS INF FILE                                               =
# ======================================================================================================
class InfFile(TextFile):
	def __init__(self, filename, encoding="ascii"):
		TextFile.__init__(self, filename, encoding)
		self._parsed = False
		self._devices = []
	
	def getDevices(self):
		if not self._parsed:
			self.parse()
		return self._devices
	
	def parse(self):
		logger.info("Parsing inf file %s" % self._filename)
		
		deviceClass = u'???'
		deviceSections = []
		sectionRegex = re.compile('\[\s*([^\]]+)\s*\]')
		pciDeviceRegex = re.compile('VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)', re.IGNORECASE)
		hdaudioDeviceRegex = re.compile('HDAUDIO\\\.*VEN_([\da-fA-F]+)&DEV_([\da-fA-F]+)', re.IGNORECASE)
		usbDeviceRegex = re.compile('USB.*VID_([\da-fA-F]+)&PID_([\da-fA-F]+)', re.IGNORECASE)
		acpiDeviceRegex = re.compile('ACPI\\\(\S+)_-_(\S+)', re.IGNORECASE)
		varRegex = re.compile('\%([^\%]+)\%')
		classRegex = re.compile('class\s*=')
		
		if not self.opened():
			self.open('r')
		self.readlines()
		lines = []
		appendNext = False
		for line in self._lines:
			if (line.find(';') != -1):
				line = line.split(';', 1)[0]
			if (line.find('#') != -1):
				line = line.split('#', 1)[0]
			line = line.strip()
			if not line:
				continue
			
			if appendNext:
				lines[-1] = lines[-1][:-1] + line
			else:
				lines.append(line)
			
			if line.endswith('\\'):
				appendNext = True
			else:
				appendNext = False
		
		# Get strings
		logger.debug("   - Getting strings")
		strings = {}
		section = ''
		for line in lines:
			match = re.search(sectionRegex, line)
			if match:
				if (section.lower() == 'strings'):
					break
				section = match.group(1)
			else:
				if (section.lower() == 'strings'):
					try:
						(var, string) = line.split('=', 1)
						string = string.strip()
						if string.startswith('"') and string.endswith('"'):
							string = string[1:-1]
						strings[var.strip().lower()] = string
					except:
						pass
		logger.debug2("        got strings: %s" % strings)
		
		# Get devices
		logger.debug("   - Getting devices")
		section = ''
		for line in lines:
			match = re.search(sectionRegex, line)
			if match:
				if (section.lower() == 'manufacturer'):
					break
				section = match.group(1)
			else:
				if (section.lower() == 'version'):
					if line.lower().startswith('class'):
						if re.search(classRegex, line.lower()):
							deviceClass = line.split('=')[1].strip().lower()
							match = re.search(varRegex, deviceClass)
							if match:
								var = match.group(1).lower()
								if strings.has_key(var):
									deviceClass = deviceClass.replace('%'+var+'%', strings[var])
				
				elif (section.lower() == 'manufacturer'):
					if line and (line.find('=') != -1):
						for d in line.split('=')[1].split(','):
							deviceSections.append(d.strip())
		
		logger.debug("      - Device sections: %s" % ', '.join(deviceSections))
		
		def isDeviceSection(section):
			if section in deviceSections:
				return True
			for section in section.split('.'):
				if section in deviceSections:
					return True
			return False
		
		found = []
		section = ''
		sectionsParsed = []
		for line in lines:
			match = re.search(sectionRegex, line)
			if match:
				if section and isDeviceSection(section):
					sectionsParsed.append(section)
				section = match.group(1)
				if isDeviceSection(section): logger.debug("   - Parsing device section: %s" % section)
			else:
				if isDeviceSection(section) and not section in sectionsParsed:
					try:
						devString = line.split('=')[1].split(',')[1].strip()
						logger.debug("      - Processing device string: %s" % devString)
						type = ''
						match = re.search(hdaudioDeviceRegex, devString)
						if match:
							type = u'HDAUDIO'
						else:
							match = re.search(pciDeviceRegex, devString)
							if match:
								type = u'PCI'
							else:
								match = re.search(usbDeviceRegex, devString)
								if match:
									type = u'USB'
								else:
									match = re.search(acpiDeviceRegex, devString)
									if match:
										type = u'ACPI'
						if match:
							logger.debug("         - Device type is %s" % type)
							if (type == 'ACPI'):
								vendor = match.group(1)
								device = match.group(2)
							else:
								vendor = match.group(1).upper()
								device = match.group(2).upper()
							if "%s:%s" % (vendor, device) not in found:
								logger.debug("         - Found %s device: %s:%s" % (type, vendor, device))
								found.append("%s:%s:%s" % (type, vendor, device))
								self._devices.append( { u'path': self._dirname, u'class': deviceClass, u'vendor': vendor, u'device': device, u'type': type } )
					except IndexError:
						logger.warning("Skipping bad line '%s' in file %s" % (line, self._filename))
		self._parsed = True



testData = [
'''
[Version]
Signature="$WINDOWS NT$"
Class=Processor
ClassGuid={50127DC3-0F36-415e-A6CC-4CB3BE910B65}
Provider=%AMD%
DriverVer=10/26/2004, 1.2.2.0
CatalogFile=AmdK8.cat

[DestinationDirs]
DefaultDestDir = 12

[SourceDisksNames]
1 = %DiskDesc%,,, 

[SourceDisksFiles]
AmdK8.sys = 1

[ControlFlags]
;
; Exclude all devices from Select Device list
;
ExcludeFromSelect = *

[ClassInstall32]
AddReg=Processor_Class_Addreg

[Processor_Class_Addreg]
HKR,,,0,%ProcessorClassName%
HKR,,NoInstallClass,,1
HKR,,Icon,,"-28"

[Manufacturer]
%AMD%=AmdK8

[AmdK8]
%AmdK8.DeviceDesc% = AmdK8_Inst,ACPI\AuthenticAMD_-_x86_Family_15
%AmdK8.DeviceDesc% = AmdK8_Inst,ACPI\AuthenticAMD_-_AMD64_Family_15

[AmdK8_Inst.NT]
Copyfiles = @AmdK8.sys

[AmdK8_Inst.NT.Services]
AddService = AmdK8,%SPSVCINST_ASSOCSERVICE%,AmdK8_Service_Inst,AmdK8_EventLog_Inst

[AmdK8_Service_Inst]
DisplayName    = %AmdK8.SvcDesc%
ServiceType    = %SERVICE_KERNEL_DRIVER%
StartType      = %SERVICE_SYSTEM_START%
ErrorControl   = %SERVICE_ERROR_NORMAL%
ServiceBinary  = %12%\AmdK8.sys
LoadOrderGroup = Extended Base
AddReg         = AmdK8_Inst_AddReg

[AmdK8_Inst_AddReg]
HKR,"Parameters",Capabilities,0x00010001,0x80

[AmdK8_EventLog_Inst]
AddReg = AmdK8_EventLog_AddReg

[AmdK8_EventLog_AddReg]
HKR,,EventMessageFile,0x00020000,"%%SystemRoot%%\System32\IoLogMsg.dll;%%SystemRoot%%\System32\drivers\AmdK8.sys"
HKR,,TypesSupported,0x00010001,7

[strings]
AMD                   = "Advanced Micro Devices"
ProcessorClassName    = "Processors"
AmdK8.DeviceDesc      = "AMD K8 Processor"
AmdK8.SvcDesc         = "AMD Processor Driver"
DiskDesc              = "AMD Processor Driver Disk"

SPSVCINST_ASSOCSERVICE= 0x00000002
SERVICE_KERNEL_DRIVER = 1
SERVICE_SYSTEM_START  = 1
SERVICE_ERROR_NORMAL  = 1
''',
'''
;
; SYMMPI.INF - version XP.10 (Windows XP)
;
; This is the INF file for Windows XP for the SYMMPI based PCI MPI
; environment
;
; ********************************************************************
;                                                                    *
;   Copyright 2005 LSI Logic, Inc. All rights reserved.              *
;                                                                    *
;   This file is property of LSI Logic, Inc. and is licensed for     *
;   use as is.  The receipt of or possession of this file does not   *
;   convey any rights to modify its contents, in whole, or in part,  *
;   without the specific written consent of LSI Logic, Inc.          *
;                                                                    *
; ********************************************************************

[version]
signature="$Windows NT$"
Class=SCSIAdapter
ClassGUID={4D36E97B-E325-11CE-BFC1-08002BE10318}
Provider=%LSI%
DriverVer=08/04/2006,1.21.25.00
CatalogFile.ntx86=mpixp32.cat

[DestinationDirs]
DefaultDestDir = 12 ; DIRID_DRIVERS

[SourceDisksFiles.x86]
symmpi.sys = 1
lsipseud.inf = 1

[SourceDisksNames]
1 = %DiskDesc%,,

[Manufacturer]
%LSI%=LSI
%DELL%=DELL

[LSI]
%DevDesc2% = SYMMPI_Inst, PCI\VEN_1000&DEV_0622
%DevDesc3% = SYMMPI_Inst, PCI\VEN_1000&DEV_0624
%DevDesc4% = SYMMPI_Inst, PCI\VEN_1000&DEV_0626
%DevDesc5% = SYMMPI_Inst, PCI\VEN_1000&DEV_0628
%DevDesc6% = SYMMPI_Inst, PCI\VEN_1000&DEV_0030
%DevDesc7% = SYMMPI_Inst, PCI\VEN_1000&DEV_0032
%DevDesc8% = SYMMPI_Inst, PCI\VEN_1000&DEV_0050
%DevDesc9% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054
%DevDesc10% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058
%DevDesc11% = SYMMPI_Inst, PCI\VEN_1000&DEV_0056
%DevDesc12% = SYMMPI_Inst, PCI\VEN_1000&DEV_0640
%DevDesc13% = SYMMPI_Inst, PCI\VEN_1000&DEV_0646
%DevDesc14% = SYMMPI_Inst, PCI\VEN_1000&DEV_0062

[DELL]
%DevDescD1% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F041028
%DevDescD2% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F051028
%DevDescD3% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F061028
%DevDescD4% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F071028
%DevDescD5% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F081028
%DevDescD6% = SYMMPI_Inst, PCI\VEN_1000&DEV_0054&SUBSYS_1F091028
%DevDescD7% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F0E1028
%DevDescD8% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F0F1028
%DevDescD9% = SYMMPI_Inst, PCI\VEN_1000&DEV_0058&SUBSYS_1F101028

[ControlFlags]
ExcludeFromSelect = *

[SYMMPI_Inst]
CopyFiles = SYMMPI_CopyFiles
AddReg = SYMMPI_AddReg
CopyINF = lsipseud.inf

[SYMMPI_Inst.HW]
AddReg = Shutdown_addreg
DelReg = LegacyScsiportValues

[SYMMPI_Inst.Services]
AddService = SYMMPI, %SPSVCINST_ASSOCSERVICE%, SYMMPI_Service_Inst, Miniport_EventLog_Inst

[SYMMPI_Service_Inst]
ServiceType    = %SERVICE_KERNEL_DRIVER%
StartType      = %SERVICE_BOOT_START%
ErrorControl   = %SERVICE_ERROR_NORMAL%
ServiceBinary  = %12%\symmpi.sys
LoadOrderGroup = SCSI Miniport
AddReg         = pnpsafe_pci_addreg
AddReg         = bus_type_scsi

[SYMMPI_CopyFiles]
symmpi.sys,,,1

[SYMMPI_AddReg]
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,DriverParameter,0x00000002,"EnablePseudoDevice=1;"
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,MaximumSGList,0x00010001,0xFF
HKLM,SYSTEM\CurrentControlSet\Services\Symmpi\Parameters\Device,NumberOfRequests,0x00010001,0xFF

[Shutdown_addreg]
HKR,"ScsiPort","NeedsSystemShutdownNotification",0x00010001,1

[LegacyScsiportValues]
HKR,Scsiport,BusNumber
HKR,Scsiport,LegacyInterfaceType
HKR,Scsiport,SlotNumber

[pnpsafe_pci_addreg]
HKR, "Parameters\PnpInterface", "5", 0x00010001, 0x00000001

[bus_type_scsi]
HKR, "Parameters", "BusType", 0x00010001, 0x00000001

[Miniport_EventLog_Inst]
AddReg = Miniport_EventLog_AddReg

[Miniport_EventLog_AddReg]
HKR,,EventMessageFile,%REG_EXPAND_SZ%,"%%SystemRoot%%\System32\IoLogMsg.dll"
HKR,,TypesSupported,%REG_DWORD%,7

[Strings]
LSI = "LSI Logic"
DELL = "Dell"
DiskDesc = "LSI Logic PCI Fusion-MPT Driver Install Disk"
DevDesc2 = "LSI Adapter, 2Gb FC, models 44929, G2 with 929"
DevDesc3 = "LSI Adapter, 2Gb FC, models 40919 with 919"
DevDesc4 = "LSI Adapter, 2Gb FC, models 7202,7402 with 929X"
DevDesc5 = "LSI Adapter, 2Gb FC, models 7102 with 919X"
DevDesc6 = "LSI Adapter, Ultra320 SCSI 2000 series, w/1020/1030"
DevDesc7 = "LSI Adapter, Ultra320 SCSI RAID series, w/1035"
DevDesc8 = "LSI Adapter, SAS 3000 series, 4-port with 1064"
DevDesc9 = "LSI Adapter, SAS 3000 series, 8-port with 1068"
DevDesc10 = "LSI Adapter, SAS 3000 series, 8-port with 1068E"
DevDesc11 = "LSI Adapter, SAS 3000 series, 4-port with 1064E"
DevDesc12 = "LSI Adapter, 4Gb FC, models 7104,7204,7404 with 949X"
DevDesc13 = "LSI Adapter, 4Gb FC, models 7104,7204,7404 with 949E"
DevDesc14 = "LSI Adapter, SAS RAID-on-Chip, 8-port with 1078"
DevDescD1 = "Dell SAS 5/E Adapter"
DevDescD2 = "Dell SAS 5/i Adapter"
DevDescD3 = "Dell SAS 5/i Integrated"
DevDescD4 = "Dell SAS 5/iR Integrated D/C"
DevDescD5 = "Dell SAS 5/iR Integrated Emb"
DevDescD6 = "Dell SAS 5/iR Adapter"
DevDescD7 = "Dell SAS 6/iR Adapter"
DevDescD8 = "Dell SAS 6/iR Integrated"
DevDescD9 = "Dell SAS 6/i Integrated"

;*******************************************
;Handy macro substitutions (non-localizable)
SPSVCINST_ASSOCSERVICE = 0x00000002
SERVICE_KERNEL_DRIVER  = 1
SERVICE_BOOT_START     = 0
SERVICE_ERROR_NORMAL   = 1
REG_EXPAND_SZ          = 0x00020000
REG_DWORD              = 0x00010001
'''
,
'''
;
;   SER2PL.INF (for Windows 2000)
;
;   Copyright (c) 2000, Prolific Technology Inc.

[version]
signature="$Windows NT$"
Class=Ports
ClassGuid={4D36E978-E325-11CE-BFC1-08002BE10318}
Provider=%Pro%
catalogfile=pl2303.cat
DriverVer=12/31/2002,2.0.0.7

[SourceDisksNames]
1=%Pro.Disk%,,,

[ControlFlags]
ExcludeFromSelect = USB\VID_067b&PID_2303

[SourceDisksFiles]
ser2pl.sys=1

[DestinationDirs]
DefaultDestDir=12
ComPort.NT.Copy=12

[Manufacturer]
%Pro%=Pro

[Pro]
%DeviceDesc% = ComPort, USB\VID_067B&PID_2303

[ComPort.NT]
CopyFiles=ComPort.NT.Copy
AddReg=ComPort.NT.AddReg

[ComPort.NT.HW]
AddReg=ComPort.NT.HW.AddReg

[ComPort.NT.Copy]
ser2pl.sys

[ComPort.NT.AddReg]
HKR,,DevLoader,,*ntkern
HKR,,NTMPDriver,,ser2pl.sys
HKR,,EnumPropPages32,,"MsPorts.dll,SerialPortPropPageProvider"

[ComPort.NT.HW.AddReg]
HKR,,"UpperFilters",0x00010000,"serenum"

[ComPort.NT.Services]
AddService = Ser2pl, 0x00000002, Serial_Service_Inst
AddService = Serenum,,Serenum_Service_Inst

[Serial_Service_Inst]
DisplayName    = %Serial.SVCDESC%
ServiceType    = 1               ; SERVICE_KERNEL_DRIVER
StartType      = 3               ; SERVICE_SYSTEM_START (this driver may do detection)
ErrorControl   = 1               ; SERVICE_ERROR_IGNORE
ServiceBinary  = %12%\ser2pl.sys
LoadOrderGroup = Base

[Serenum_Service_Inst]
DisplayName    = %Serenum.SVCDESC%
ServiceType    = 1               ; SERVICE_KERNEL_DRIVER
StartType      = 3               ; SERVICE_DEMAND_START
ErrorControl   = 1               ; SERVICE_ERROR_NORMAL
ServiceBinary  = %12%\serenum.sys
LoadOrderGroup = PNP Filter

[linji]
Pro = "Prolific"
Pro.Disk="USB-Serial Cable Diskette"
DeviceDesc = "Prolific USB-to-Serial Comm Port"
Serial.SVCDESC   = "Prolific Serial port driver"
Serenum.SVCDESC = "Serenum Filter Driver"
'''
,
'''
[Version]
CatalogFile=RTHDMI32.cat
Signature = "$chicago$"
Class=MEDIA
ClassGuid={4d36e96c-e325-11ce-bfc1-08002be10318}
Provider=%OrganizationName%
DriverPackageType=PlugAndPlay
DriverPackageDisplayName=%PackageDisplayName%
DriverVer=03/02/2007, 5.10.0.5368

[Manufacturer]
%MfgName% = AzaliaManufacturerID

[ControlFlags]
ExcludeFromSelect = *

[AzaliaManufacturerID]
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_791A
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_793C
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA01
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA09
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA11
"ATI HDMI Audio" = RtAzAudModel, HDAUDIO\FUNC_01&VEN_1002&DEV_AA19

[SourceDisksNames]
222="Realtek HD Audio Installation Disk",,,

[SourceDisksFiles]
RtHDMI.sys=222
RtkUpd.exe=222

[DestinationDirs]
DefaultDestDir=10; dirid = \system32\drivers
RtAzAudModelCopyFiles = 10,system32\drivers
RTUninstall.CopyList = 10           ;; WINDOWS

[RtAzAudModelCopyFiles]
RtHDMI.sys

[RTUninstall.CopyList]
RtkUpd.exe

[RtAzAudModel.NTX86]
Include=ks.inf,wdmaudio.inf
Needs=KS.Registration,WDMAUDIO.Registration
CopyFiles = RtAzAudModelCopyFiles, RTUninstall.CopyList
AddReg    = RtAzAudModelAddReg, DS3DConfiguration.AddReg, RTUninstall.AddReg

[RtAzAudModel.NTX86.HW]
AddReg=HdAudSecurity.AddReg

[RtAzAudModel.NTX86.Services]
AddService = RTHDMIAzAudService, 0x00000002, RTHDMIAzAudServiceInstall

[RTHDMIAzAudServiceInstall]
DisplayName   = "Service for HDMI"
ServiceType   = 1
StartType     = 3
ErrorControl  = 1
ServiceBinary = %10%\system32\drivers\RtHDMI.sys


[RtAzAudModel.NTX86.Interfaces]
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifWave%, RtAzAudModel.RtSpdifWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifWave%, RtAzAudModel.RtSpdifWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifTopo%, RtAzAudModel.RtSpdifTopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifTopo%, RtAzAudModel.RtSpdifTopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifHDMIWave%, RtAzAudModel.RtSpdifHDMIWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifHDMIWave%, RtAzAudModel.RtSpdifHDMIWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifHDMITopo%, RtAzAudModel.RtSpdifHDMITopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifHDMITopo%, RtAzAudModel.RtSpdifHDMITopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifRCAWave%, RtAzAudModel.RtSpdifRCAWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifRCAWave%, RtAzAudModel.RtSpdifRCAWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifRCATopo%, RtAzAudModel.RtSpdifRCATopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifRCATopo%, RtAzAudModel.RtSpdifRCATopo

AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifOptWave%, RtAzAudModel.RtSpdifOptWave
AddInterface=%KSCATEGORY_RENDER%,%KSNAME_RtSpdifOptWave%, RtAzAudModel.RtSpdifOptWave
AddInterface=%KSCATEGORY_AUDIO%,%KSNAME_RtSpdifOptTopo%, RtAzAudModel.RtSpdifOptTopo
AddInterface=%KSCATEGORY_TOPOLOGY%,%KSNAME_RtSpdifOptTopo%, RtAzAudModel.RtSpdifOptTopo

[DS3DConfiguration.AddReg]
HKR,DS3D,ForwardSpeakerConfiguration,0x00010001,0
HKR,DS3D,IgnoreDSSpeakerConfiguration,0x00010001,1
HKR,"DS3D\OldArch",ForwardSpeakerConfiguration,0x00010001,0
HKR,"DS3D\OldArch",IgnoreDSSpeakerConfiguration,0x00010001,1

[RTUninstall.AddReg]
HKLM,%RT_UNINSTALL%,DisplayName,,"Realtek High Definition Audio Driver"
HKLM,%RT_UNINSTALL%,UninstallString,,"RtkUpd.exe -r -m"

[HdAudSecurity.AddReg]
HKR,,DeviceType,0x10001,0x0000001D

[RtAzAudModelAddReg]
HKR,,AssociatedFilters,,"wdmaud,swmidi,redbook"
HKR,,Driver,,RtHDMI.sys

HKR,Drivers,SubClasses,,"wave,midi,mixer,aux"

HKR,Drivers\wave\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\midi\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\mixer\wdmaud.drv,Driver,,wdmaud.drv
HKR,Drivers\aux\wdmaud.drv,Driver,,wdmaud.drv

HKR,Drivers\wave\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\midi\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\mixer\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%
HKR,Drivers\aux\wdmaud.drv,Description,,%IntcAzAudioDeviceDescription%

HKR,,SetupPreferredAudioDevices,3,01,00,00,00

[RtAzAudModel.RtSpdifWave]
AddReg = RtAzAudModel.RtSpdifWave.AddReg
[RtAzAudModel.RtSpdifWave.AddReg]
HKR,,FriendlyName,,%RtSpdifWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifTopo]
AddReg = RtAzAudModel.RtSpdifTopo.AddReg
[RtAzAudModel.RtSpdifTopo.AddReg]
HKR,,FriendlyName,,%RtSpdifTopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[RtAzAudModel.RtSpdifHDMIWave]
AddReg = RtAzAudModel.RtSpdifHDMIWave.AddReg
[RtAzAudModel.RtSpdifHDMIWave.AddReg]
HKR,,FriendlyName,,%RtSpdifHDMIWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifHDMITopo]
AddReg = RtAzAudModel.RtSpdifHDMITopo.AddReg

[RtAzAudModel.RtSpdifHDMITopo.AddReg]
HKR,,FriendlyName,,%RtSpdifHDMITopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

HKLM,%MediaCategories%\%GUID.RTSPDIFOut%,Name,,%Node.RTSPDIFOut%
HKLM,%MediaCategories%\%GUID.RTSPDIFOut%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTHDMIOut%,Name,,%Node.RTHDMIOut%
HKLM,%MediaCategories%\%GUID.RTHDMIOut%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTSPDIFOutRCA%,Name,,%Node.RTSPDIFOutRCA%
HKLM,%MediaCategories%\%GUID.RTSPDIFOutRCA%,Display,1,00,00,00,00
HKLM,%MediaCategories%\%GUID.RTSPDIFOutOpt%,Name,,%Node.RTSPDIFOutOpt%
HKLM,%MediaCategories%\%GUID.RTSPDIFOutOpt%,Display,1,00,00,00,00

[RtAzAudModel.RtSpdifRCAWave]
AddReg = RtAzAudModel.RtSpdifRCAWave.AddReg
[RtAzAudModel.RtSpdifRCAWave.AddReg]
HKR,,FriendlyName,,%RtSpdifRCAWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifRCATopo]
AddReg = RtAzAudModel.RtSpdifRCATopo.AddReg
[RtAzAudModel.RtSpdifRCATopo.AddReg]
HKR,,FriendlyName,,%RtSpdifRCATopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[RtAzAudModel.RtSpdifOptWave]
AddReg = RtAzAudModel.RtSpdifOptWave.AddReg
[RtAzAudModel.RtSpdifOptWave.AddReg]
HKR,,FriendlyName,,%RtSpdifOptWaveDeviceName%
HKR,,CLSID,,%Proxy.CLSID%
[RtAzAudModel.RtSpdifOptTopo]
AddReg = RtAzAudModel.RtSpdifOptTopo.AddReg
[RtAzAudModel.RtSpdifOptTopo.AddReg]
HKR,,FriendlyName,,%RtSpdifOptTopoDeviceName%
HKR,,CLSID,,%Proxy.CLSID%

[Strings]
MfgName="Realtek"
MediaCategories="SYSTEM\CurrentControlSet\Control\MediaCategories"

OrganizationName="Realtek Semiconductor Corp."
PackageDisplayName="HD Audio Driver"
IntcAzAudioDeviceDescription = "Realtek High Definition Audio"

RT_UNINSTALL="Software\Microsoft\Windows\CurrentVersion\Uninstall\{F132AF7F-7BCA-4EDE-8A7C-958108FE7DBC}"

KSNAME_RtSpdifWave="RtSpdifWave"
KSNAME_RtSpdifTopo="RtSpdifTopo"
KSNAME_RtSpdifHDMIWave="RtSpdifHDMIWave"
KSNAME_RtSpdifHDMITopo="RtSpdifHDMITopo"
KSNAME_RtSpdifRCAWave="RtSpdifRCAWave"
KSNAME_RtSpdifRCATopo="RtSpdifRCATopo"
KSNAME_RtSpdifOptWave="RtSpdifOptWave"
KSNAME_RtSpdifOptTopo="RtSpdifOptTopo"

RtSpdifWaveDeviceName="Realtek HDA SPDIF Out"
RtSpdifTopoDeviceName="Realtek HDA SPDIF Out Mixer"
RtSpdifHDMIWaveDeviceName="Realtek HDA HDMI Out"
RtSpdifHDMITopoDeviceName="Realtek HDA HDMI Out Mixer"
RtSpdifRCAWaveDeviceName="Realtek HDA SPDIF RCA Out"
RtSpdifRCATopoDeviceName="Realtek HDA SPDIF RCA Out Mixer"
RtSpdifOptWaveDeviceName="Realtek HDA SPDIF Optical Out"
RtSpdifOptTopoDeviceName="Realtek HDA SPDIF Optical Out Mixer"


KSCATEGORY_AUDIO = "{6994AD04-93EF-11D0-A3CC-00A0C9223196}"
KSCATEGORY_RENDER="{65E8773E-8F56-11D0-A3B9-00A0C9223196}"
KSCATEGORY_CAPTURE="{65E8773D-8F56-11D0-A3B9-00A0C9223196}"
KSCATEGORY_TOPOLOGY="{DDA54A40-1E4C-11D1-A050-405705C10000}"
Proxy.CLSID ="{17CCA71B-ECD7-11D0-B908-00A0C9223196}"

GUID.RTSPDIFOut			="{8FD300D2-FFE1-44f3-A9EB-6F4395D73C9F}"
Node.RTSPDIFOut			="Realtek Digital Output"
GUID.RTHDMIOut			="{9C8E490E-877D-48fe-9EF1-AD83C91CC057}"
Node.RTHDMIOut			="Realtek HDMI Output"
GUID.RTSPDIFOutRCA		="{3FF4EDB6-3FF3-4b5a-B164-10FFF0367547}"
Node.RTSPDIFOutRCA		="Realtek Digital Output(RCA)"
GUID.RTSPDIFOutOpt		="{94FCA009-B26E-4cdc-AC75-051613EF01BB}"
Node.RTSPDIFOutOpt		="Realtek Digital Output(Optical)"
'''
]

if (__name__ == "__main__"):
	
	print "Unit test"
	#logger.setConsoleLevel(LOG_DEBUG2)
	for data in testData:
		tempFile = 'inf_unit_test_file.inf'
		infFile = InfFile(tempFile)
		infFile.open('w')
		infFile.write(data)
		infFile.close()
		print "\nFile: %s" % tempFile
		for dev in infFile.getDevices():
			print "   Found device: %s" % dev
		infFile.delete()
		
































