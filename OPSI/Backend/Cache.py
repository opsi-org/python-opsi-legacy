#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
opsi python library - Cache

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2010-2013 uib GmbH

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
@author: Erol Ueluekmen <e.ueluekmen@uib.de>
@license: GNU General Public License version 2
"""

import codecs
import inspect
import json
import time

from OPSI.Logger import LOG_NOTICE, Logger
from OPSI.Types import forceHostId
from OPSI.Object import *
from OPSI.Backend.Backend import *
from OPSI.Backend.Replicator import BackendReplicator
from OPSI.Util import blowfishDecrypt

logger = Logger()


class ClientCacheBackend(ConfigDataBackend, ModificationTrackingBackend):

	def __init__(self, **kwargs):
		ConfigDataBackend.__init__(self, **kwargs)

		self._workBackend = None
		self._masterBackend = None
		self._snapshotBackend = None
		self._clientId = None
		self._depotId = None
		self._backendChangeListeners = []

		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('workbackend',):
				self._workBackend = value
			elif option in ('snapshotbackend',):
				self._snapshotBackend = value
			elif option in ('masterbackend',):
				self._masterBackend = value
			elif option in ('clientid',):
				self._clientId = forceHostId(value)
			elif option in ('depotid',):
				self._depotId = forceHostId(value)
			elif option in ('backendinfo',):
				self._backendInfo = value

		if not self._workBackend:
			raise Exception(u"Work backend undefined")
		if not self._snapshotBackend:
			raise Exception(u"Snapshot backend undefined")
		if not self._clientId:
			raise Exception(u"Client id undefined")
		if not self._depotId:
			raise Exception(u"Depot id undefined")

		self._workBackend._setContext(self)
		self._backend = self._workBackend
		self._createInstanceMethods()

	def log_write(self, logType, data, objectId=None, append=False):
		pass

	def licenseOnClient_getObjects(self, attributes=[], **filter):
		licenseOnClients = self._workBackend.licenseOnClient_getObjects(attributes, **filter)
		for licenseOnClient in licenseOnClients:
			# Recreate for later sync to server
			self.licenseOnClient_insertObject(licenseOnClient)
		return licenseOnClients

	def _setMasterBackend(self, masterBackend):
		self._masterBackend = masterBackend

	def _syncModifiedObjectsWithMaster(self, objectClass, modifiedObjects, getFilter, objectsDifferFunction, createUpdateObjectFunction, mergeObjectsFunction):
		masterObjects = {}
		deleteObjects = []
		updateObjects = []
		meth = getattr(self._masterBackend, '%s_getObjects' % objectClass.backendMethodPrefix)
		for obj in meth(**getFilter):
			masterObjects[obj.getIdent()] = obj
		for mo in modifiedObjects:
			masterObj = masterObjects.get(mo['object'].getIdent())

			if (mo['command'].lower() == 'delete'):
				if not masterObj:
					logger.info(u"No need to delete object %s because object has been deleted on server since last sync" % mo['object'])
					continue
				meth = getattr(self._snapshotBackend, '%s_getObjects' % objectClass.backendMethodPrefix)
				snapshotObj = meth(**(mo['object'].getIdent(returnType = 'dict')))
				if not snapshotObj:
					logger.info(u"Deletion of object %s prevented because object has been created on server since last sync" % mo['object'])
					continue
				snapshotObj = snapshotObj[0]
				if objectsDifferFunction(snapshotObj, masterObj):
					logger.info(u"Deletion of object %s prevented because object has been modified on server since last sync" % mo['object'])
					continue
				logger.debug(u"Object %s marked for deletion" % mo['object'])
				deleteObjects.append(mo['object'])

			elif mo['command'].lower() in ('update', 'insert'):
				logger.debug(u"Modified object: %s" % mo['object'].toHash())
				updateObj = createUpdateObjectFunction(mo['object'])

				if masterObj:
					logger.debug(u"Master object: %s" % masterObj.toHash())
					meth = getattr(self._snapshotBackend, '%s_getObjects' % objectClass.backendMethodPrefix)
					snapshotObj = meth(**(updateObj.getIdent(returnType = 'dict')))
					if snapshotObj:
						snapshotObj = snapshotObj[0]
						logger.debug(u"Snapshot object: %s" % snapshotObj.toHash())
						updateObj = mergeObjectsFunction(snapshotObj, updateObj, masterObj)
				if updateObj:
					logger.debug(u"Object %s marked for update" % mo['object'])
					updateObjects.append(updateObj)
		if deleteObjects:
			meth = getattr(self._masterBackend, '%s_deleteObjects' % objectClass.backendMethodPrefix)
			meth(deleteObjects)
		if updateObjects:
			meth = getattr(self._masterBackend, '%s_updateObjects' % objectClass.backendMethodPrefix)
			meth(updateObjects)

	def _updateMasterFromWorkBackend(self, modifications = []):
		modifiedObjects = {}
		for modification in modifications:
			try:
				if not modifiedObjects.has_key(modification['objectClass']):
					modifiedObjects[modification['objectClass']] = []
				ObjectClass = eval(modification['objectClass'])
				identValues = modification['ident'].split(ObjectClass.identSeparator)
				identAttributes = getIdentAttributes(ObjectClass)
				filter = {}
				for i in range(len(identAttributes)):
					if (i >= len(identValues)):
						raise Exception(u"Bad ident '%s' for objectClass '%s'" % (identValues, modification['objectClass']))
					filter[identAttributes[i]] = identValues[i]
				meth = getattr(self._workBackend, ObjectClass.backendMethodPrefix + '_getObjects')
				modification['object'] = meth(**filter)[0]
				modifiedObjects[modification['objectClass']].append(modification)
			except Exception as e:
				logger.error(u"Failed to sync backend modification %s: %s" % (modification, e))
				continue

		if modifiedObjects.has_key('AuditHardwareOnHost'):
			self._masterBackend.auditHardwareOnHost_setObsolete(self._clientId)
			objects = []
			for mo in modifiedObjects['AuditHardwareOnHost']:
				objects.append(mo['object'])
			self._masterBackend.auditHardwareOnHost_updateObjects(objects)

		if modifiedObjects.has_key('AuditSoftware'):
			objects = []
			for mo in modifiedObjects['AuditSoftware']:
				objects.append(mo['object'])
			self._masterBackend.auditSoftware_updateObjects(objects)

		if modifiedObjects.has_key('AuditSoftwareOnClient'):
			self._masterBackend.auditSoftwareOnClient_setObsolete(self._clientId)
			objects = []
			for mo in modifiedObjects['AuditSoftwareOnClient']:
				objects.append(mo['object'])
			self._masterBackend.auditSoftwareOnClient_updateObjects(objects)

		if modifiedObjects.has_key('ProductOnClient'):
			def objectsDifferFunction(snapshotObj, masterObj):
				return objectsDiffer(snapshotObj, masterObj, excludeAttributes = ['modificationTime', 'actionProgress', 'actionResult', 'lastAction'])

			def createUpdateObjectFunction(modifiedObj):
				updateObj = modifiedObj.clone(identOnly = False)
				return updateObj

			def mergeObjectsFunction(snapshotObj, updateObj, masterObj):
				if (snapshotObj.actionRequest != masterObj.actionRequest):
					logger.info(u"Action request of %s changed on server since last sync, not updating actionRequest" % snapshotObj)
					updateObj.actionRequest = None
					updateObj.targetConfiguration = None
				return updateObj

			self._syncModifiedObjectsWithMaster(ProductOnClient, modifiedObjects['ProductOnClient'], {"clientId": self._clientId}, objectsDifferFunction, createUpdateObjectFunction, mergeObjectsFunction)

		if modifiedObjects.has_key('LicenseOnClient'):
			def objectsDifferFunction(snapshotObj, masterObj):
				result = objectsDiffer(snapshotObj, masterObj)
				return result

			def createUpdateObjectFunction(modifiedObj):
				updateObj = modifiedObj.clone(identOnly = False)
				return updateObj

			def mergeObjectsFunction(snapshotObj, updateObj, masterObj):
				return updateObj

			self._syncModifiedObjectsWithMaster(LicenseOnClient, modifiedObjects['LicenseOnClient'], {"clientId": self._clientId}, objectsDifferFunction, createUpdateObjectFunction, mergeObjectsFunction)

		for objectClassName in ('ProductPropertyState', 'ConfigState'):
			def objectsDifferFunction(snapshotObj, masterObj):
				return objectsDiffer(snapshotObj, masterObj)

			def createUpdateObjectFunction(modifiedObj):
				return modifiedObj.clone()

			def mergeObjectsFunction(snapshotObj, updateObj, masterObj):
				if (len(snapshotObj.values) != len(masterObj.values)):
					logger.info(u"Values of %s changed on server since last sync, not updating values" % snapshotObj)
					return None
				if snapshotObj.values:
					for v in snapshotObj.values:
						if not v in masterObj.values:
							logger.info(u"Values of %s changed on server since last sync, not updating values" % snapshotObj)
							return None
				if masterObj.values:
					for v in masterObj.values:
						if not v in snapshotObj.values:
							logger.info(u"Values of %s changed on server since last sync, not updating values" % snapshotObj)
							return None
				return updateObj

			if modifiedObjects.has_key(objectClassName):
				self._syncModifiedObjectsWithMaster(eval(objectClassName), modifiedObjects[objectClassName], {"objectId": self._clientId}, objectsDifferFunction, createUpdateObjectFunction, mergeObjectsFunction)

	def _replicateMasterToWorkBackend(self):
		if not self._masterBackend:
			raise Exception(u"Master backend undefined")

		self._cacheBackendInfo(self._masterBackend.backend_info())

		self._workBackend.backend_deleteBase()
		self._workBackend.backend_createBase()
		br = BackendReplicator(readBackend = self._masterBackend, writeBackend = self._workBackend)
		br.replicate(
			serverIds    = [ ],
			depotIds     = [ self._depotId ],
			clientIds    = [ self._clientId ],
			groupIds     = [ ],
			productIds   = [ ],
			productTypes = [ 'LocalbootProduct' ],
			audit        = False,
			license      = False)

		self._snapshotBackend.backend_deleteBase()

		licenseOnClients = self._masterBackend.licenseOnClient_getObjects(clientId = self._clientId)
		for productOnClient in self._workBackend.productOnClient_getObjects(clientId = self._clientId):
			if productOnClient.actionRequest in (None, 'none'):
				continue
			licensePools = self._masterBackend.licensePool_getObjects(productIds = [ productOnClient.productId ])
			if not licensePools:
				logger.debug(u"No license pool found for product '%s'" % productOnClient.productId)
				continue
			licensePool = licensePools[0]
			try:
				licenseOnClient = None
				for loc in licenseOnClients:
					if (loc.licensePoolId == licensePool.id):
						licenseOnClient = loc
						break
				if licenseOnClient:
					logger.notice(u"Reusing existing licenseOnClient '%s'" % licenseOnClient)
				else:
					logger.notice(u"Acquiring license for product '%s'" % productOnClient.productId)
					licenseOnClient = self._masterBackend.licenseOnClient_getOrCreateObject(clientId = self._clientId, productId = productOnClient.productId)
					# Fake deletion for later sync to server
					self._fireEvent('objectsDeleted', [ licenseOnClient ])
					self._fireEvent('backendModified')
				for licensePool in self._masterBackend.licensePool_getObjects(id = licenseOnClient.licensePoolId):
					self._workBackend.licensePool_insertObject(licensePool)
				for softwareLicense in self._masterBackend.softwareLicense_getObjects(id = licenseOnClient.softwareLicenseId):
					for licenseContract in self._masterBackend.licenseContract_getObjects(id = softwareLicense.licenseContractId):
						self._workBackend.licenseContract_insertObject(licenseContract)
					self._workBackend.softwareLicense_insertObject(softwareLicense)
				self._workBackend.licenseOnClient_insertObject(licenseOnClient)

			except Exception as e:
				logger.error(u"Failed to acquire license for product '%s': %s" % (productOnClient.productId, e))

		self._snapshotBackend.backend_createBase()
		br = BackendReplicator(readBackend = self._workBackend, writeBackend = self._snapshotBackend)
		br.replicate()

		password = self._masterBackend.user_getCredentials(username = 'pcpatch', hostId = self._clientId)['password']
		opsiHostKey = self._workBackend.host_getObjects(id = self._clientId)[0].getOpsiHostKey()
		logger.notice(u"Creating opsi passwd file '%s'" % self._opsiPasswdFile)
		self.user_setCredentials(
			username = 'pcpatch',
			password = blowfishDecrypt(opsiHostKey, password)
		)
		auditHardwareConfig = self._masterBackend.auditHardware_getConfig()
		with codecs.open(self._auditHardwareConfigFile, 'w', 'utf8') as f:
			f.write(json.dumps(auditHardwareConfig))

		self._workBackend._setAuditHardwareConfig(auditHardwareConfig)
		self._workBackend.backend_createBase()

	def _createInstanceMethods(self):
		for Class in (Backend, ConfigDataBackend):
			for member in inspect.getmembers(Class, inspect.ismethod):
				methodName = member[0]
				if methodName.startswith('_') or methodName in ('backend_info', 'user_getCredentials', 'user_setCredentials', 'log_write', 'licenseOnClient_getObjects'):
				#if methodName.startswith('_') or methodName in ('backend_info', 'user_getCredentials', 'user_setCredentials', 'auditHardware_getConfig', 'log_write'):
					continue

				(argString, callString) = getArgAndCallString(member[1])

				logger.debug2(u"Adding method '%s' to execute on work backend" % methodName)
				exec(u'def %s(self, %s): return self._executeMethod("%s", %s)' % (methodName, argString, methodName, callString))
				setattr(self, methodName, new.instancemethod(eval(methodName), self, self.__class__))

	def _cacheBackendInfo(self, backendInfo):
		with codecs.open(self._opsiModulesFile, 'w', 'utf-8') as f:
			modules = backendInfo['modules']
			helpermodules = backendInfo['realmodules']
			for (module, state) in modules.items():
				if helpermodules in ('customer', 'expires'):
					continue
				if helpermodules.has_key(module):
					state = helpermodules[module]
				else:
					if state:
						state = 'yes'
					else:
						state = 'no'
				f.write('%s = %s\n' % (module.lower(), state))
			f.write('customer = %s\n' % modules.get('customer', ''))
			f.write('expires = %s\n' % modules.get('expires', time.strftime("%Y-%m-%d", time.localtime(time.time()))))
			f.write('signature = %s\n' % modules.get('signature', ''))

		with codecs.open(self._opsiVersionFile, 'w', 'utf-8') as f:
			f.write(backendInfo.get('opsiVersion', '').strip())


if (__name__ == '__main__'):
	from OPSI.Backend.SQLite import SQLiteBackend
	from OPSI.Backend.JSONRPC import JSONRPCBackend

	logger.setConsoleColor(True)
	logger.setConsoleLevel(LOG_NOTICE)

	workBackend = SQLiteBackend(database = ':memory:')
	#workBackend = SQLiteBackend(database = '/tmp/opsi-cache.sqlite')

	serviceBackend = JSONRPCBackend(
		address  = 'https://bonifax.uib.local:4447/rpc',
		username = 'cachetest.uib.local',
		password = '12c1e40a6d3038d3eb2b4d489e978973')

	cb = ClientCacheBackend(
		workBackend   = workBackend,
		masterBackend = serviceBackend,
		depotId       = 'bonifax.uib.local',
		clientId      = 'cachetest.uib.local'
	)

	#workBackend._sql.execute('PRAGMA synchronous=OFF')
	cb._replicateMasterToWorkBackend()

	be = ExtendedConfigDataBackend(cb)

	#cb.host_insertObject( OpsiClient(id = 'cachetest.uib.local', description = 'description') )
	#print cb.host_getObjects()
	#print workBackend._sql.getSet('select * from HOST')
	#for productPropertyState in cb.productPropertyState_getObjects(objectId = 'cachetest.uib.local'):
	#	print productPropertyState.toHash()
	#for productOnClient in cb.productOnClient_getObjects(clientId = 'cachetest.uib.local'):
	#	print productOnClient.toHash()

	print be.licenseOnClient_getOrCreateObject(clientId = 'cachetest.uib.local', productId = 'license-test-oem')
