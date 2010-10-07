from OPSI.Object import *

class InventoryObjectMethodMixin(object):
	
	def test_getAuditSoftwareFromBackend(self):
		
		auditSoftwares = self.backend.auditSoftware_getObjects()
		self.assertEqual(len(auditSoftwares), len(self.auditSoftwares), u"Expected %s audit software objects, but found %s on backend." % (len(self.auditSoftwares), len(auditSoftwares)))
	
	def test_updateAuditSoftware(self):
		auditSoftware3update = AuditSoftware(
			name=self.auditSoftware3.name,
			version=self.auditSoftware3.version,
			subVersion=self.auditSoftware3.subVersion,
			language=self.auditSoftware3.language,
			architecture=self.auditSoftware3.architecture,
			windowsSoftwareId=self.auditSoftware3.windowsSoftwareId,
			windowsDisplayName='updatedDN',
			windowsDisplayVersion=self.auditSoftware3.windowsDisplayVersion,
			installSize=self.auditSoftware3.installSize
		)
		
		self.backend.auditSoftware_updateObject(auditSoftware3update)
		auditSoftwares = self.backend.auditSoftware_getObjects(windowsDisplayName='updatedDN')
		self.assertEqual(len(auditSoftwares), 1, u"Expected one audit software object, but found %s on backend." % (len(auditSoftwares)))
	
	def test_deleteAuditSoftware(self):
		self.backend.auditSoftware_deleteObjects(self.auditSoftware3)
		auditSoftwares = self.backend.auditSoftware_getObjects()
		self.assertEqual(len(auditSoftwares), len(self.auditSoftwares) - 1, u"Expected %s audit software objects, but found %s on backend." % (len(self.auditSoftwares) - 1, len(auditSoftwares)))
			
	def test_insertAuditSoftware(self):
		self.backend.auditSoftware_deleteObjects(self.auditSoftware3)
		self.backend.auditSoftware_insertObject(self.auditSoftware3)
		auditSoftwares = self.backend.auditSoftware_getObjects()
		self.assertEqual(len(auditSoftwares), len(self.auditSoftwares), u"Expected %s audit software objects, but found %s on backend." % (len(self.auditSoftwares), len(auditSoftwares)))
		
		
	def test_getAuditSoftewareLicensePoolFromBackend(self):
		if not self.licenseManagement:
			self.skipTest("LicenseManagement is not enabled on %s." % self.__class__.__name__)
			# AuditSoftwareToLicensePools
			
		self.backend.auditSoftwareToLicensePool_createObjects(self.auditSoftwareToLicensePools)
		
		auditSoftwareToLicensePools = self.backend.auditSoftwareToLicensePool_getObjects()
		self.assertEqual(len(auditSoftwareToLicensePools), len(self.auditSoftwareToLicensePools), u"Expected %s audit license objects in pool, but found %s on backend." % (len(self.auditSoftwareToLicensePools), len(auditSoftwareToLicensePools)))
			
			
	def test_getAuditSoftwareOnClients(self):
		auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects()
		self.assertEqual(len(auditSoftwareOnClients), len(self.auditSoftwareOnClients), "Expected %s software objects in pool, but found %s on backend." % (len(self.auditSoftwareOnClients), len(auditSoftwareOnClients)))
		

	def test_updateAuditSoftwareOnClient(self):
		auditSoftwareOnClient1update = AuditSoftwareOnClient(
			name=self.auditSoftware1.getName(),
			version=self.auditSoftware1.getVersion(),
			subVersion=self.auditSoftware1.getSubVersion(),
			language=self.auditSoftware1.getLanguage(),
			architecture=self.auditSoftware1.getArchitecture(),
			clientId=self.client1.getId(),
			uninstallString=None,
			binaryName='updatedBN',
			firstseen=None,
			lastseen=None,
			state=None,
			usageFrequency=2,
			lastUsed='2009-02-12 09:48:22'
		)
		
		self.backend.auditSoftwareOnClient_updateObject(auditSoftwareOnClient1update)
		auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects(binaryName='updatedBN')
		self.assertEqual(len(auditSoftwareOnClients), 1, "Expected one software object in pool, but found %s on backend." % (len(auditSoftwareOnClients)))
			
	def test_deleteAuditSoftwareOnClient(self):
		self.backend.auditSoftwareOnClient_deleteObjects(self.auditSoftwareOnClient1)
		auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects()
		self.assertEqual(len(auditSoftwareOnClients), len(self.auditSoftwareOnClients) - 1, u"Expected %s audit software objects, but found %s on backend." % (len(self.auditSoftwareOnClients) - 1, len(auditSoftwareOnClients)))
		
	def test_insertAuditSoftwareOnClient(self):
		self.backend.auditSoftwareOnClient_deleteObjects(self.auditSoftwareOnClient1)
		self.backend.auditSoftwareOnClient_insertObject(self.auditSoftwareOnClient1)
		auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects()
		self.assertEqual(len(auditSoftwareOnClients), len(self.auditSoftwareOnClients), u"Expected %s audit software objects, but found %s on backend." % (len(self.auditSoftwareOnClients), len(auditSoftwareOnClients)))
		
		
	def test_getAuditHardwareFromBackend(self):
		auditHardwares = self.backend.auditHardware_getObjects()
		self.assertEqual(len(auditHardwares), len(self.auditHardwares), u"Expected %s audit hardware objects, but found %s on backend." % (len(self.auditHardwares), len(auditHardwares)))
		
	
	def test_selectAuditHardwareClasses(self):
		auditHardwareClasses = map((lambda x: x.getHardwareClass()),self.backend.auditHardware_getObjects(hardwareClass=['CHASSIS', 'COMPUTER_SYSTEM']))
		for auditHardwareClass in auditHardwareClasses:
			self.assertIn(auditHardwareClass, ['CHASSIS', 'COMPUTER_SYSTEM'], u"Hardware class '%s' not in '%s'." % (auditHardwareClass, ['CHASSIS', 'COMPUTER_SYSTEM']))
		
		auditHardwareClasses = map((lambda x: x.getHardwareClass()), self.backend.auditHardware_getObjects(hardwareClass=['CHA*IS', '*UTER_SYS*']))
		for auditHardwareClass in auditHardwareClasses:
			self.assertIn(auditHardwareClass, ['CHASSIS', 'COMPUTER_SYSTEM'], u"Hardware class '%s' not in '%s'." % (auditHardwareClass, ['CHASSIS', 'COMPUTER_SYSTEM']))
	
	def test_deleteAuditHardware(self):
		self.backend.auditHardware_deleteObjects([ self.auditHardware1, self.auditHardware2 ])
		auditHardwares = self.backend.auditHardware_getObjects()
		self.assertEqual(len(auditHardwares), len(self.auditHardwares) - 2, u"Expected %s audit hardware objects, but found %s on backend." % (len(self.auditHardwares)-2, len(auditHardwares)))
	
	def test_deleteAllAuditHardware(self):
		self.backend.auditHardware_deleteObjects(self.backend.auditHardware_getObjects())
		auditHardwares = self.backend.auditHardware_getObjects()
		self.assertEqual(len(auditHardwares), 0, u"Expected 0 audit hardware objects, but found %s on backend." % (len(auditHardwares)))
		
	def test_createAuditHardware(self):
		self.backend.auditHardware_deleteObjects([ self.auditHardware1, self.auditHardware2 ])
		self.backend.auditHardware_createObjects([ self.auditHardware1, self.auditHardware2 ])
		auditHardwares = self.backend.auditHardware_getObjects()
		self.assertEqual(len(auditHardwares), len(self.auditHardwares), u"Expected %s audit hardware objects, but found %s on backend." % (len(self.auditHardwares), len(auditHardwares)))
		
		self.backend.auditHardware_deleteObjects(self.backend.auditHardware_getObjects())
		self.backend.auditHardware_createObjects(self.auditHardwares)
		auditHardwares = self.backend.auditHardware_getObjects()
		self.assertEqual(len(auditHardwares), len(self.auditHardwares), u"Expected %s audit hardware objects, but found %s on backend." % (len(self.auditHardwares), len(auditHardwares)))
		
	def test_getAuditHardwareOnHost(self):
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts), u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts), auditHardwareOnHosts))
		
	
	def test_insertAuditHardwareOnHost(self):
		auditHardwareOnHost4update = self.auditHardwareOnHost4.clone()
		auditHardwareOnHost4update.setLastseen('2000-01-01 01:01:01')
		self.backend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		if self.inventoryHistory:
			self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts) + 1, u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts)+1, len(auditHardwareOnHosts)))
		else:
			self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts), u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts), len(auditHardwareOnHosts)))
				
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects(lastseen='2000-01-01 01:01:01')
		self.assertEqual(len(auditHardwareOnHosts), 1, u"Expected one audit hardware object on host, but found %s on backend." % (len(auditHardwareOnHosts)))
		
		auditHardwareOnHost4update.setState(0)
		self.backend.auditHardwareOnHost_insertObject(auditHardwareOnHost4update)
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		if self.inventoryHistory:
			self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts) + 2, u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts)+2, len(auditHardwareOnHosts)))
		else:
			self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts), u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts), len(auditHardwareOnHosts)))
			
	
	def test_deleteAllAuditHardwareOnHost(self):
		self.backend.auditHardwareOnHost_delete(hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[])
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		self.assertEqual(len(auditHardwareOnHosts), 0, u"Expected no audit hardware objects on host, but found %s on backend." % (len(auditHardwareOnHosts)))
		
	def test_createAuditHardwareOnHost(self):
		self.backend.auditHardwareOnHost_delete(hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[])
		self.backend.auditHardwareOnHost_createObjects(self.auditHardwareOnHosts)
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts), u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts), len(auditHardwareOnHosts)))
		
	def test_createDuplicateAuditHardwareOnHost(self):
		auditHardwareOnHost4update = self.auditHardwareOnHost4.clone()
		self.backend.auditHardwareOnHost_updateObject(auditHardwareOnHost4update)
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts), u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts), len(auditHardwareOnHosts)))

	def test_deleteAuditHardwareOnHost(self):
		self.backend.auditHardwareOnHost_deleteObjects([self.auditHardwareOnHost4, self.auditHardwareOnHost3])
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
		self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts) - 2, u"Expected %s audit hardware objects on host, but found %s on backend." % (len(self.auditHardwareOnHosts)-2, len(auditHardwareOnHosts)))
	
	def test_setObsoleteAuditHardwareOnHost(self):
		self.backend.auditHardwareOnHost_setObsolete(self.client3.id)
		auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects(hostId = self.client3.id)
		for auditHardwareOnHost in auditHardwareOnHosts:
			self.assertEqual(auditHardwareOnHost.getState(), 0, u"Expected state 0 in audit hardware on host %s, but found state %s on backend." % (auditHardwareOnHost, auditHardwareOnHost.getState()))
	







