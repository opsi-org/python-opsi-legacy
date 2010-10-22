


class NonObjectMethodsMixin(object):



	def test_createDepotServer(self):	
		self.backend.host_createOpsiDepotserver(
				id = 'depot100.uib.local',
				opsiHostKey = '123456789012345678901234567890aa',
				depotLocalUrl = 'file:///opt/pcbin/install',
				depotRemoteUrl = 'smb://depot3.uib.local/opt_pcbin/install',
				repositoryLocalUrl = 'file:///var/lib/opsi/products',
				repositoryRemoteUrl = 'webdavs://depot3.uib.local:4447/products',
				description = 'A depot',
				notes = 'Depot 100',
				hardwareAddress = None,
				ipAddress = None,
				networkAddress = '192.168.100.0/24',
				maxBandwidth = 0)

		
		hosts = self.backend.host_getObjects(id = 'depot100.uib.local')
		self.assertEqual(len(hosts), 1, u"Expected one depotserver with id '%s', but found '%s' on backend." % ('depot100.uib.local', len(hosts)))

	def test_createClient(self):
		
		# FIXME
		#self.backend.productOnDepot_create(
		#	productId      = self.product4.getId(),
		#	productType    = self.product4.getType(),
		#	productVersion = self.product4.getProductVersion(),
		#	packageVersion = self.product4.getPackageVersion(),
		#	depotId        = 'depot100.uib.local',
		#	locked         = False
		#)
		#
		
		self.backend.host_createOpsiClient(
				id = 'client100.uib.local',
				opsiHostKey = None,
				description = 'Client 100',
				notes = 'No notes',
				hardwareAddress = '00:00:01:01:02:02',
				ipAddress = '192.168.0.200',
				created = None,
				lastSeen = None)

		hosts = self.backend.host_getObjects(id = 'client100.uib.local')
		self.assertEqual(len(hosts), 1, u"Expected one client with id '%s', but found '%s' on backend." % ('client100.uib.local', len(hosts)))

	def test_hostIdents(self):
		self.test_createDepotServer()
		self.test_createClient()
		numHosts = len(self.hosts)
		
		selfIdents = []
		for host in self.hosts:
			selfIdents.append(host.getIdent(returnType = 'dict'))
		
		selfIdents.append({'id': 'depot100.uib.local'})
		selfIdents.append({'id': 'client100.uib.local'})
		
		selfIds = map((lambda set: set['id']), selfIdents)
		
		ids = self.backend.host_getIdents()
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		
		for ident in ids:
			self.assertIn(ident, selfIds, u"'%s' not in '%s'" % (ident, selfIds))
			
		ids = self.backend.host_getIdents(id = '*100*')
		self.assertEqual(len(ids), 2, u"Expected %s idents, but found '%s' on backend." % (2, len(ids)))
		for ident in ids:
			self.assertIn(ident, selfIds, u"'%s' not in '%s'" % (ident, selfIds))
		
		ids = self.backend.host_getIdents(returnType = 'tuple')
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		for ident in ids:
			self.assertIn(ident[0], selfIds, u"'%s' not in '%s'" % (ident, selfIds))
			
		ids = self.backend.host_getIdents(returnType = 'list')
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		for ident in ids:
			self.assertIn(ident[0], selfIds, u"'%s' not in '%s'" % (ident, selfIds))
		
		ids = self.backend.host_getIdents(returnType = 'dict')
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		for ident in ids:
			self.assertIn(ident['id'], selfIds, u"'%s' not in '%s'" % (ident, selfIds))
		
		selfIdents = []
			
		for config in self.configs:
			selfIdents.append(config.getIdent(returnType = 'dict'))
		selfIds = map((lambda set: set['id']), selfIdents)
		
		ids = self.backend.config_getIdents()
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		for ident in ids:
			self.assertIn(ident, selfIds, u"'%s' not in '%s'" % (ident, selfIds))
		
		selfIdents = []
		for configState in self.configStates:
			selfIdents.append(configState.getIdent(returnType = 'dict'))
		
		self.backend.backend_setOptions({"addConfigStateDefaults": False})
		ids = self.backend.configState_getIdents()
		self.assertEqual(len(ids), len(selfIdents), u"Expected %s idents, but found '%s' on backend." % (len(selfIdents), len(ids)))
		for ident in ids:
			id = dict(zip(('configId', 'objectId'), tuple(ident.split(";"))))
			self.assertIn(id, selfIdents, u"'%s' not in '%s'" % (ident, selfIdents))
		
		expect = len(self.backend.host_getObjects()) * len(self.configs)
		self.backend.backend_setOptions({"addConfigStateDefaults": True})
		ids = self.backend.configState_getIdents()
		self.assertEqual(expect, len(ids), u"Expected %s idents, but found '%s' on backend." % (expect, len(ids)))
		
	def test_noException(self):
		try:
			self.backend.product_getIdents()
			self.backend.productProperty_getIdents()
			self.backend.productOnDepot_getIdents()
			self.backend.productOnDepot_getIdents()
			self.backend.productPropertyState_getIdents()
			self.backend.productPropertyState_getIdents(returnType = 'tuple')
			self.backend.productPropertyState_getIdents(returnType = 'list')
			self.backend.productPropertyState_getIdents(returnType = 'dict')
			self.backend.group_getIdents()
			self.backend.objectToGroup_getIdents()
			self.backend.product_getIdents(id = '*product*')
		except Exception, e:
			self.fail(e)
			
			
	
	def test_ldapSearchFilter(self):
		result = self.backend.backend_searchIdents('(&(objectClass=Host)(type=OpsiDepotserver))')
		expected = self.backend.host_getIdents(type="OpsiDepotserver")
		result.sort()
		expected.sort()
		self.assertListEqual(expected, result, u"Expected %s, got %s" % (expected, result))

		result = self.backend.backend_searchIdents('(&(&(objectClass=Host)(type=OpsiDepotserver))(objectClass=Host))')
		expected = self.backend.host_getIdents(type="OpsiDepotserver")
		result.sort()
		expected.sort()
		self.assertListEqual(expected, result, u"Expected %s, got %s" % (expected, result))
		
		result = self.backend.backend_searchIdents('(|(&(objectClass=OpsiClient)(id=client1*))(&(objectClass=OpsiClient)(id=client2*)))')
		expected = self.backend.host_getIdents(type="OpsiClient", id = ["client1*", "client2*" ] )
		result.sort()
		expected.sort()
		self.assertListEqual(expected, result, u"Expected %s, got %s" % (expected, result))
		
		result = self.backend.backend_searchIdents('(&(&(objectClass=OpsiClient))(&(objectClass=ProductOnClient)(installationStatus=installed))(&(objectClass=ProductOnClient)(productId=product1)))')
		expected = map((lambda x: x["clientId"]),self.backend.productOnClient_getIdents(returnType="dict", installationStatus="installed", productId="product1"))
		result.sort()
		expected.sort()
		self.assertListEqual(expected, result, u"Expected %s, got %s" % (expected, result))

		
		result = self.backend.backend_searchIdents('(&(objectClass=Host)(description=T*))')
		expected = self.backend.host_getIdents(description="T*")
		result.sort()
		expected.sort()
		self.assertListEqual(expected, result, u"Expected %s, got %s" % (expected, result))