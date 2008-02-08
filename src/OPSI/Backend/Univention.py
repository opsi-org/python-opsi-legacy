# -*- coding: utf-8 -*-
# auto detect encoding => äöü
"""
   ==============================================
   =          OPSI Univention Module            =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.4.7'

# Imports
import ldap, ldap.modlist, re

# OPSI imports
from OPSI.Backend.Backend import *
import OPSI.Backend.LDAP
from OPSI.Logger import *
from OPSI.Product import *
from OPSI import Tools
from OPSI.System import execute

# Get logger instance
logger = Logger()

# Globals
baseDn = 'dc=uib,dc=local'
opsiBaseDn = 'cn=opsi,' + baseDn
univentionBaseDn = 'cn=univention,' + baseDn
hostsContainerDn = 'cn=computers,' + baseDn
groupsContainerDn = 'cn=groups,' + opsiBaseDn
productsContainerDn = 'cn=products,' + opsiBaseDn
productDependenciesContainerDn = 'cn=productDependencies,' + opsiBaseDn
productClassesContainerDn = 'cn=productClasses,' + opsiBaseDn
productClassDependenciesContainerDn = 'cn=productClassDependencies,' + opsiBaseDn
productLicensesContainerDn = 'cn=productLicenses,' + opsiBaseDn
productStatesContainerDn = 'cn=productStates,' + opsiBaseDn
policiesContainerDn = 'cn=opsi,cn=policies,' + baseDn
productPropertyPoliciesContainerDn = 'cn=productProperties,' + policiesContainerDn
productDeploymentPoliciesContainerDn = 'cn=productDeployments,' + policiesContainerDn
networkConfigPoliciesContainerDn = 'cn=networkConfigs,' + policiesContainerDn
generalConfigPoliciesContainerDn = 'cn=generalConfigs,' + policiesContainerDn
univentionSyntaxesContainerDn = 'cn=opsiSyntax' + univentionBaseDn
univentionAdminPropertiesContainerDn = 'cn=custom attributes,' + univentionBaseDn
defaultContainersObjectDn = 'cn=default containers,' + univentionBaseDn

try:
	# Univention imports
	import univention.debug
	import univention.admin.filter
	import univention.admin.handlers
	import univention.admin.syntax
	
	# Mappings
	def boolToString(value):
		if value == '1':
			return 'TRUE'
		else:
			return 'FALSE'
		
	def stringToBool(value):
		if value[0] == 'TRUE':
			return '1'
		else:
			return '0'
	
	
	def timestampToTime(value):
		if (type(value) == type(())) or (type(value) == type([])):
			value = value[0]
		value = str(value).strip()
		if ( len(value) < 14):
			return value
		return u'%s.%s.%s %s:%s:%s' % (value[6:8], value[4:6], value[0:4], \
						value[8:10], value[10:12], value[12:14] )
		
	def timeToTimestamp(value):
		# TODO: syntax check
		if not re.search('^\d\d\.\d\d.\d\d\d\d \d\d:\d\d:\d\d$', value):
			return str(Tools.timestamp())
		(date, time) = value.split()
		date = date.split('.')
		time = time.split(':')
		return date[2]+date[1]+date[0]+time[0]+time[1]+time[2]
	
	def productDnToProductId(value):
		product = Object(value)
		return product.getCn()
	
	def mapActionRequest(value):
		if (value == 'undefined'):
			return ''
		return value
	
	def mapInstallationStatus(value):
		return value
	
	def defaultMapping():
		mapping = univention.admin.mapping.mapping()
		mapping.register('requiredObjectClasses', 'requiredObjectClasses')
		mapping.register('prohibitedObjectClasses', 'prohibitedObjectClasses')
		mapping.register('fixedAttributes', 'fixedAttributes')
		mapping.register('emptyAttributes', 'emptyAttributes')
		return mapping
	
	def defaultPolicyObjectDescriptions(*attributes):
		attributes = list(attributes)
		
		class PolicyFixedAttributeSelection(univention.admin.syntax.select):
			name = u'Festgelegte Attribute'
			choices = attributes
		
		class PolicyEmptyAttributeSelection(univention.admin.syntax.select):
			name = u'Leere Attribute'
			choices = attributes
		
		return {
			'requiredObjectClasses': univention.admin.property(
					short_description	= u'Benoetigte Objektklassen',
					long_description	= u'Benoetigte Objektklassen',
					syntax			= univention.admin.syntax.string,
					multivalue		= 1,
					options			= [],
					required		= 0,
					may_change		= 1,
					identifies		= 0
			),
			'prohibitedObjectClasses': univention.admin.property(
					short_description	= u'Ausgeschlossene Objektklassen',
					long_description	= u'Ausgeschlossene Objektklassen',
					syntax			= univention.admin.syntax.string,
					multivalue		= 1,
					options			= [],
					required		= 0,
					may_change		= 1,
					identifies		= 0
			),
			'fixedAttributes': univention.admin.property(
					short_description	= u'Festgelegte Attribute',
					long_description	= u'Festgelegte Attribute',
					syntax			= PolicyFixedAttributeSelection,
					multivalue		= 1,
					options			= [],
					required		= 0,
					may_change		= 1,
					identifies		= 0
			),
			'emptyAttributes': univention.admin.property(
					short_description	= u'Leere Attribute',
					long_description	= u'Leere Attribute',
					syntax			= PolicyEmptyAttributeSelection,
					multivalue		= 1,
					options			= [],
					required		= 0,
					may_change		= 1,
					identifies		= 0
			)
		}
	
	
	defaultPolicyObjectTab = univention.admin.tab( u'Objekt', u'Objekt',
		[ [ univention.admin.field( 'requiredObjectClasses' ),	univention.admin.field( 'prohibitedObjectClasses' ) ],
		  [ univention.admin.field( 'fixedAttributes' ),	univention.admin.field( 'emptyAttributes' ) ] ]
	)
	
	
	def getSession(univentionObject):
		return Session(ldap = univentionObject.lo.lo.lo)
	
	def getUniventionBackend(univentionObject):
		return UniventionBackend( session = getSession(univentionObject) )
	
	def getPolicyPositionDnPrefix(dn):
		parts = dn.split(',')
		for i in range(len(parts)):
			if (parts[i].strip() == 'cn=policies'):
				return ','.join(parts[:i])
		return dn
	
	# Syntax
	class opsiProductInstallationStatusSyntax(univention.admin.syntax.select):
		name = u'Installations-Status'
		choices = [ 	('undefined',		u'Unbekannt'),
				('installed',		u'Installiert'), 
				('not_installed',	u'Nicht installiert'),
				('uninstalled',		u'Deinstalliert'),
				('failed',		u'Fehlgeschlagen') ]
		#for status in getPossibleProductInstallationStatus():
		#	choices.append( (status, status) )
	
	class opsiProductActionRequestSyntax(univention.admin.syntax.select):
		name = u'Angeforderte Aktion'	
		choices = [ 	('undefined',		u'Undefiniert (Richtlinie folgen)'), 
				('by_policy',		u'Richtlinie folgen'),
				('setup',		u'Setup (erzwungen)'),
				('setup_by_policy',	u'Setup (Richtlinie)'),
				('update',		u'Update (erzwungen)'),
				('update_by_policy',	u'Update (Richtlinie)'),
				('uninstall',		u'Uninstall (erzwungen)'),
				('uninstall_by_policy',	u'Uninstall (Richtlinie)'),
				('once',		u'Once (erzwungen)'),
				('always',		u'Always (erzwungen)'),
				('none',		u'Keine (erzwungen)'),
				('none_by_policy',	u'Keine (Richtlinie)'),
				]
	
	class opsiProductActionRequestForcedSyntax(univention.admin.syntax.select):
		name = u'Angeforderte Aktion'
		choices = [ 	('undefined',		u'Undefiniert (Richtlinie folgen)'),
				('setup',		u'Setup'),
				('update',		u'Update'),
				('uninstall',		u'Uninstall'),
				('once',		u'Once'),
				('always',		u'Always'),
				('none',		u'Nichts tun')
				]
	
	class opsiProductRequirementTypeSyntax(univention.admin.syntax.select):
		name = u'Angeforderte Aktion'
		choices = [ 	('',		u'Muss erfuellt sein'),
				('before',	u'Muss vor der Aktion erfuellt sein'),
				('after',	u'Muss nach der Aktion erfuellt sein'),
				]
	
	class opsiHostKeySyntax(univention.admin.syntax.simple):
		name = u'OPSI-Host-Schluessel'
		min_length=32
		max_length=32
		_re = re.compile('^[a-hA-H0-9]{32}$')
		
		def parse(self, text):
			if self._re.match(text) != None:
				return text
			raise univention.admin.uexceptions.valueError, u'Kein gueltiger OPSI-Host-Schluessel'
	
	univention.admin.syntax.opsiHostKeySyntax = opsiHostKeySyntax
	
	class opsiProductIdSyntax(univention.admin.syntax.simple):
		name = u'Produkt-ID'
		min_length=4
		max_length=256
		_re = re.compile('^[a-zA-Z0-9.-]+$')
		
		def parse(self, text):
			if self._re.match(text) != None:
				return text
			raise univention.admin.uexceptions.valueError, u'Keine gueltige Produkt-ID'
	
	class opsiProductClassIdSyntax(univention.admin.syntax.simple):
		name = u'Produktklassen-ID'
		min_length=4
		max_length=256
		_re = re.compile('^[a-zA-Z0-9.-]+$')
		
		def parse(self, text):
			if self._re.match(text) != None:
				return text
			raise univention.admin.uexceptions.valueError, u'Keine gueltige Produktklassen-ID'
	
	class opsiProductPropertyNameSyntax(univention.admin.syntax.simple):
		name = u'Produkt-Options-Name'
		min_length=1
		max_length=256
		_re = re.compile('^[a-zA-Z0-9.-]+$')
		
		def parse(self, text):
			if self._re.match(text) != None:
				return text
			raise univention.admin.uexceptions.valueError, u'Keine gueltiger Produkt-Options-Name'
	
	class opsiTimeSyntax(univention.admin.syntax.simple):
		name = u'Zeitpunkt'
		min_length=19
		max_length=19
		_re = re.compile('^\d\d\.\d\d.\d\d\d\d \d\d:\d\d:\d\d$')
		
		def parse(self, text):
			if self._re.match(text) != None:
				return text
			raise univention.admin.uexceptions.valueError, u'Keine gueltiger Zeitpunkt'
	
	class notRequired(univention.admin.syntax.simple):
		name = u'Nicht benötigt'
		def parse(self, text):
			return text
		
		def new(self):
			return '-'
		
		
	class opsiProductDeploymentSyntax(univention.admin.syntax.complex):
		name='opsiProductDeploymentSyntax'
		searchFilter='(objectClass=opsiProduct)'
		
		subsyntaxes=[	('Produkt', univention.admin.syntax.LDAP_Search(
							filter = '(objectClass=opsiProduct)',
							attribute = [ 'opsiproducts/product: name' ],
							value = 'opsiproducts/product: id' ) ),
				('Installationsstatus', opsiProductInstallationStatusSyntax),
				('Produktversion', notRequired), 
				('Paketversion', notRequired),
				('Erstellungszeitpunkt', notRequired) ]
		all_required=0
	
	class opsiProductPropertySyntax(univention.admin.syntax.complex):
		name='opsiProductPropertySyntax'
		searchFilter='(objectClass=opsiProduct)'
		
		subsyntaxes=[	('Produkt', univention.admin.syntax.LDAP_Search(
							filter = '(objectClass=opsiProduct)',
							attribute = [ 'opsiproducts/product: name' ],
							value = 'opsiproducts/product: id' ) ),
				('Option', univention.admin.syntax.string),
				('Wert', univention.admin.syntax.string) ]
		all_required=0

	#class opsiProductDeploymentSyntax(univention.admin.syntax.complex):
	#	name='opsiProductDeploymentSyntax'
	#	searchFilter='(objectClass=opsiProduct)'
	#	
	#	subsyntaxes=[	('Produkt', univention.admin.syntax.string),
	#			('Installationsstatus', opsiProductInstallationStatusSyntax),
	#			('Produktversion', univention.admin.syntax.string), 
	#			('Paketversion', univention.admin.syntax.string),
	#			('Erstellungszeitpunkt', opsiTimeSyntax) ]
	#	all_required=0
	
	#class printQuotaUser(univention.admin.syntax.complex):
	#	name='printQuotaUser'
	#	searchFilter='(&(uid=*)(objectClass=posixAccount)(!(objectClass=univentionHost)))'
	#	
	#	subsyntaxes=[('Soft-Limit', integer), ('Hard-Limit', integer), ('User', string)]
	#	all_required=0
		
except Exception, e:
	#logger.logException(e)
	logger.error(e)


# ======================================================================================================
# =                                  CLASS UNIVENTIONBACKEND                                           =
# ======================================================================================================
class UniventionBackend(OPSI.Backend.LDAP.LDAPBackend):
	
	def __init__(self, username = '', password = '', address = '', backendManager=None, session=None, args={}):
		''' UniventionBackend constructor. '''
		
		self._address = address
		self._username = username
		self._password = password
		
		self._backendManager = backendManager
		
		# Default values
		self._baseDn = baseDn
		self._opsiBaseDn = opsiBaseDn
		self._univentionBaseDn = univentionBaseDn
		self._hostsContainerDn = hostsContainerDn
		self._groupsContainerDn = groupsContainerDn
		self._productsContainerDn = productsContainerDn
		self._productDependenciesContainerDn = productDependenciesContainerDn
		self._productClassesContainerDn = productClassesContainerDn
		self._productClassDependenciesContainerDn = productClassDependenciesContainerDn
		self._productLicensesContainerDn = productLicensesContainerDn
		self._productStatesContainerDn = productStatesContainerDn
		self._policiesContainerDn = policiesContainerDn
		self._productPropertyPoliciesContainerDn = productPropertyPoliciesContainerDn
		self._productDeploymentPoliciesContainerDn = productDeploymentPoliciesContainerDn
		self._networkConfigPoliciesContainerDn = networkConfigPoliciesContainerDn
		self._generalConfigPoliciesContainerDn = generalConfigPoliciesContainerDn
		self._univentionSyntaxesContainerDn = univentionSyntaxesContainerDn
		self._univentionAdminPropertiesContainerDn = univentionAdminPropertiesContainerDn
		self._defaultContainersObjectDn = defaultContainersObjectDn
		self._policyReferenceAttributeName = 'univentionPolicyReference'
		self._policyReferenceObjectClass = 'univentionPolicyReference'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'basedn'):					self._baseDn = value
			elif (option.lower() == 'opsibasedn'):					self._opsiBaseDn = value
			elif (option.lower() == 'univentionbasedn'):				self._univentionBaseDn = value
			elif (option.lower() == 'hostscontainerdn'):				self._hostsContainerDn = value
			elif (option.lower() == 'groupscontainerdn'):				self._groupsContainerDn = value
			elif (option.lower() == 'productscontainerdn'):			self._productsContainerDn = value
			elif (option.lower() == 'productdependenciescontainerdn'):		self._productDependenciesContainerDn = value
			elif (option.lower() == 'productclassescontainerdn'):			self._productClassesContainerDn = value
			elif (option.lower() == 'productclassdependenciescontainerdn'):	self._productClassDependenciesContainerDn = value
			elif (option.lower() == 'productlicensescontainerdn'):			self._productLicensesContainerDn = value
			elif (option.lower() == 'policiescontainerdn'):			self._policiesContainerDn = value
			elif (option.lower() == 'productpropertypoliciescontainerdn'):	self._productPropertyPoliciesContainerDn = value
			elif (option.lower() == 'productstatescontainerdn'):			self._productStatesContainerDn = value
			elif (option.lower() == 'productdeploymentpoliciescontainerdn'):	self._productDeploymentPoliciesContainerDn = value
			elif (option.lower() == 'networkconfigpoliciescontainerdn'):		self._networkConfigPoliciesContainerDn = value
			elif (option.lower() == 'generalconfigpoliciescontainerdn'):		self._generalConfigPoliciesContainerDn = value
			elif (option.lower() == 'univentionsyntaxescontainerdn'):		self._univentionSyntaxesContainerDn = value
			elif (option.lower() == 'univentionadminpropertiescontainerdn'):	self._univentionAdminPropertiesContainerDn = value
			elif (option.lower() == 'defaultcontainersobjectdn'):			self._defaultContainersObjectDn = value
			elif (option.lower() == 'defaultdomain'): 				self._defaultDomain = value
			elif (option.lower() == 'host'):					self._address = value
			elif (option.lower() == 'binddn'):					self._username = value
			elif (option.lower() == 'bindpw'):					self._password = value
			elif (option.lower() == 'policyreferenceattributename'):		self._policyReferenceAttributeName = value
			elif (option.lower() == 'policyreferenceobjectclass'):			self._policyReferenceObjectClass = value
			else:
				logger.warning("Unknown argument '%s' passed to UniventionBackend constructor" % option)

		if session:
			self._ldap = session
		else:
			logger.info("Connecting to ldap server '%s' as user '%s'" % (self._address, self._username))
			self._ldap = OPSI.Backend.LDAP.Session(	host	 = self._address,
									username = self._username, 
									password = self._password )
			self._ldap.baseDn = self._baseDn
			self._ldap.connect()
	
		
	def createUniventionSyntaxObjects(self):
		self.createOrganizationalRole(self._univentionSyntaxesContainerDn)
		
		classReference = Object("cn=opsiProductClassReferenceSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			classReference.new('univentionSyntax')
			classReference.setAttribute( 'univentionSyntaxDescription', 	[ 'OPSI Produkt Klasse' ] )
			classReference.setAttribute( 'univentionSyntaxLDAPAttribute', [ 'opsiproductclasses/productclass: description' ] ) # Mapping name not attribute name!
			classReference.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._productClassesContainerDn ] )
			classReference.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(objectClass=opsiProductClass)' ] )
			classReference.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'opsiproductclasses/productclass: dn' ] )
			classReference.setAttribute( 'univentionSyntaxViewOnly', 	[ 'FALSE' ] )
			classReference.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiProductClassReferenceSyntax object: %s" % e)
		
		productReference = Object("cn=opsiProductReferenceSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			productReference.new('univentionSyntax')
			productReference.setAttribute( 'univentionSyntaxDescription', [ 'OPSI Produkt' ] )
			productReference.setAttribute( 'univentionSyntaxLDAPAttribute', [ 'opsiproducts/product: name' ] )
			productReference.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._productsContainerDn ] )
			productReference.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(objectClass=opsiProduct)' ] )
			productReference.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'opsiproducts/product: dn' ] )
			productReference.setAttribute( 'univentionSyntaxViewOnly', 	[ 'FALSE' ] )
			productReference.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiProductReferenceSyntax object: %s" % e)
			
		serverReference = Object("cn=opsiServerReferenceSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			serverReference.new('univentionSyntax')
			serverReference.setAttribute( 'univentionSyntaxDescription', [ 'OPSI Depotserver' ] )
			serverReference.setAttribute( 'univentionSyntaxLDAPAttribute', [ 'computers/computer: name' ] )
			serverReference.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._hostsContainerDn ] )
			serverReference.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(objectClass=opsiServer)' ] )
			serverReference.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'computers/computer: dn' ] )
			serverReference.setAttribute( 'univentionSyntaxViewOnly', 	[ 'FALSE' ] )
			serverReference.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiServerReferenceSyntax object: %s" % e)
		
		clientReference = Object("cn=opsiClientReferenceSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			clientReference.new('univentionSyntax')
			clientReference.setAttribute( 'univentionSyntaxDescription', [ 'OPSI Client' ] )
			clientReference.setAttribute( 'univentionSyntaxLDAPAttribute', [ 'computers/computer: name' ] )
			clientReference.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._hostsContainerDn ] )
			clientReference.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(objectClass=opsiClient)' ] )
			clientReference.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'computers/computer: dn' ] )
			clientReference.setAttribute( 'univentionSyntaxViewOnly', 	[ 'FALSE' ] )
			clientReference.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiClientReferenceSyntax object: %s" % e)
		
		hostReference = Object("cn=opsiHostReferenceSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			hostReference.new('univentionSyntax')
			hostReference.setAttribute( 'univentionSyntaxDescription', [ 'OPSI Host' ] )
			hostReference.setAttribute( 'univentionSyntaxLDAPAttribute', [ 'computers/computer: name' ] )
			hostReference.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._hostsContainerDn ] )
			hostReference.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(|(objectClass=opsiClient)(objectClass=opsiServer))' ] )
			hostReference.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'computers/computer: dn' ] )
			hostReference.setAttribute( 'univentionSyntaxViewOnly', 	[ 'FALSE' ] )
			hostReference.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiHostReferenceSyntax object: %s" % e)
		
		productStates = Object("cn=opsiProductStateSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			productStates.new('univentionSyntax')
			productStates.setAttribute( 'univentionSyntaxDescription', 	[ 'Produkt-Status' ] )
			productStates.setAttribute( 'univentionSyntaxLDAPAttribute', 	[ 'opsiproductstates/productstate: installationStatus',
											  'opsiproductstates/productstate: actionRequestForced' ] )
			productStates.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._productStatesContainerDn ] )
			productStates.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(&(objectClass=opsiProductState)(opsiHostReference=<dn>))' ] )
			productStates.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'opsiproductstates/productstate: dn' ] )
			productStates.setAttribute( 'univentionSyntaxViewOnly', 	[ 'TRUE' ] )
			productStates.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiServerReferenceSyntax object: %s" % e)
			
		productClassMembers = Object("cn=opsiProductClassMemberSyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			productClassMembers.new('univentionSyntax')
			productClassMembers.setAttribute( 'univentionSyntaxDescription', 	[ 'Produkte der Klasse' ] )
			productClassMembers.setAttribute( 'univentionSyntaxLDAPAttribute', 	[ 'opsiproducts/product: name' ] )
			productClassMembers.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._productsContainerDn ] )
			productClassMembers.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(&(objectClass=opsiProduct)(opsiProductClassProvided=<dn>))' ] )
			productClassMembers.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'opsiproducts/product: dn' ] )
			productClassMembers.setAttribute( 'univentionSyntaxViewOnly', 	[ 'TRUE' ] )
			productClassMembers.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiProductClassMemberSyntax object: %s" % e)
		
		productDependencies = Object("cn=opsiProductDependencySyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			productDependencies.new('univentionSyntax')
			productDependencies.setAttribute( 'univentionSyntaxDescription', 	[ 'Produkt-Abhaengigkeiten eines Produkts' ] )
			productDependencies.setAttribute( 'univentionSyntaxLDAPAttribute', 	[ 'opsiproductdependencies/productdependency: action'] )
			productDependencies.setAttribute( 'univentionSyntaxLDAPBase', 	[ self._productDependenciesContainerDn ] )
			productDependencies.setAttribute( 'univentionSyntaxLDAPFilter', 	[ '(&(objectClass=opsiProductDependency)(opsiProductReference=<dn>))' ] )
			productDependencies.setAttribute( 'univentionSyntaxLDAPValue', 	[ 'opsiproducts/product: dn' ] )
			productDependencies.setAttribute( 'univentionSyntaxViewOnly', 	[ 'TRUE' ] )
			productDependencies.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiProductDependencySyntax object: %s" % e)
		
		productClassDependencies = Object("cn=opsiProductClassDependencySyntax,%s" % self._univentionSyntaxesContainerDn)
		try:
			productClassDependencies.new('univentionSyntax')
			productClassDependencies.setAttribute( 'univentionSyntaxDescription', 	[ 'Produktklassen-Abhaengigkeiten eines Produkts' ] )
			productClassDependencies.setAttribute( 'univentionSyntaxLDAPAttribute', 	[ 'opsiproductdependencies/productclassdependency: action'] )
			productClassDependencies.setAttribute( 'univentionSyntaxLDAPBase', 		[ self._productClassDependenciesContainerDn ] )
			productClassDependencies.setAttribute( 'univentionSyntaxLDAPFilter', 		[ '(&(objectClass=opsiProductClassDependency)(opsiProductReference=<dn>))' ] )
			productClassDependencies.setAttribute( 'univentionSyntaxLDAPValue', 		[ 'opsiproducts/product: dn' ] )
			productClassDependencies.setAttribute( 'univentionSyntaxViewOnly', 		[ 'TRUE' ] )
			productClassDependencies.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create opsiProductClassDependencySyntax object: %s" % e)
	
	def deleteUniventionSyntaxObjects(self):
		
		syntaxContainer = Object(self._univentionSyntaxesContainerDn)
		try:
			syntaxContainer.deleteFromDirectory(self._ldap, recursive=True)
		except Exception, e:
			logger.error("Failed to delete univentionSyntaxesContainer '%s': %s" % (syntaxContainer.getDn(), e))
	
	def createUniventionAdminProperties(self):
		self.createOrganizationalRole(self._univentionAdminPropertiesContainerDn)
		
		opsiClientKey = Object("cn=opsiClientKey,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			opsiClientKey.new('univentionAdminProperty')
			opsiClientKey.setAttribute( 'univentionAdminPropertyModule', 		[ 'computers/windows' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyLayoutTabName', 	[ 'OPSI: Einstellungen' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyShortDescription',[ 'Client-Schlüssel' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyLongDescription', [ 'OPSI-Client-Schlüssel' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyObjectClass', 	[ 'opsiClient' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertyLdapMapping', 	[ 'opsiHostKey' ] )
			opsiClientKey.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiHostKeySyntax' ] )
			opsiClientKey.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
		
		opsiServerKey = Object("cn=opsiServerKey,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			opsiServerKey.new('univentionAdminProperty')
			opsiServerKey.setAttribute( 'univentionAdminPropertyModule', 		[ 'computers/domaincontroller_master' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyLayoutTabName', 	[ 'OPSI: Einstellungen' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyShortDescription',[ 'Server-Schluessel' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyLongDescription', [ 'OPSI-Server-Schluessel' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyObjectClass', 	[ 'opsiServer' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertyLdapMapping', 	[ 'opsiHostKey' ] )
			opsiServerKey.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiHostKeySyntax' ] )
			opsiServerKey.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
		
		productState = Object("cn=opsiProductState,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			productState.new('univentionAdminProperty')
			productState.setAttribute( 'univentionAdminPropertyModule', 		[ 'computers/windows' ] )
			productState.setAttribute( 'univentionAdminPropertyLayoutTabName', 	[ 'OPSI: Produkt-Status' ] )
			productState.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			productState.setAttribute( 'univentionAdminPropertyShortDescription',	[ 'OPSI: Produkt-Status' ] )
			productState.setAttribute( 'univentionAdminPropertyLongDescription', 	[ 'OPSI: Produkt-Status' ] )
			productState.setAttribute( 'univentionAdminPropertyObjectClass', 	[ 'opsiProductState' ] )
			productState.setAttribute( 'univentionAdminPropertyLdapMapping', 	[ 'dn' ] ) # Egal was ???
			productState.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiProductStateSyntax' ] )
			productState.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
		
		productClassMember = Object("cn=opsiProductClassMember,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			productClassMember.new('univentionAdminProperty')
			productClassMember.setAttribute( 'univentionAdminPropertyModule', 		[ 'opsiproductclasses/productclass' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyLayoutTabName', 	[ 'Produkte' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyShortDescription',	[ 'Produkte' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyLongDescription', 	[ 'Produkte dieser Klasse' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyObjectClass', 	[ 'opsiProduct' ] )
			productClassMember.setAttribute( 'univentionAdminPropertyLdapMapping', 	[ 'dn' ] ) # Egal was ???
			productClassMember.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiProductClassMemberSyntax' ] )
			productClassMember.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
		
		productDependency = Object("cn=opsiProductDependency,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			productDependency.new('univentionAdminProperty')
			productDependency.setAttribute( 'univentionAdminPropertyModule', 		[ 'opsiproducts/product' ] )
			productDependency.setAttribute( 'univentionAdminPropertyLayoutTabName', 	[ 'Produkt-Abhaengigkeiten' ] )
			productDependency.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			productDependency.setAttribute( 'univentionAdminPropertyShortDescription',	[ 'Produkt-Abhaengigkeiten' ] )
			productDependency.setAttribute( 'univentionAdminPropertyLongDescription', 	[ 'Produkte zu denen Abhaengigkeiten bestehen' ] )
			productDependency.setAttribute( 'univentionAdminPropertyObjectClass', 	[ 'opsiProduct' ] )
			productDependency.setAttribute( 'univentionAdminPropertyLdapMapping', 	[ 'dn' ] ) # Egal was ???
			productDependency.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiProductDependencySyntax' ] )
			productDependency.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
		
		productClassDependency = Object("cn=opsiProductClassDependency,%s" % self._univentionAdminPropertiesContainerDn)
		try:
			productClassDependency.new('univentionAdminProperty')
			productClassDependency.setAttribute( 'univentionAdminPropertyModule', 		[ 'opsiproducts/product' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyLayoutTabName', 		[ 'Produktklassen-Abhaengigkeiten' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyLayoutPosition', 	[ '1' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyShortDescription',	[ 'Produktklassen-Abhaengigkeiten' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyLongDescription', 	[ 'Produktklassen zu denen Abhaengigkeiten bestehen' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyObjectClass', 		[ 'opsiProductClass' ] )
			productClassDependency.setAttribute( 'univentionAdminPropertyLdapMapping', 		[ 'dn' ] ) # Egal was ???
			productClassDependency.setAttribute( 'univentionAdminPropertySyntax', 		[ 'opsiProductClassDependencySyntax' ] )
			productClassDependency.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to create univentionAdminProperty object: %s" % e)
	
	def deleteUniventionAdminProperties(self):
		opsiClientKey = Object("cn=opsiClientKey,%s" % self._univentionAdminPropertiesContainerDn)
		opsiServerKey = Object("cn=opsiServerKey,%s" % self._univentionAdminPropertiesContainerDn)
		productState = Object("cn=opsiProductState,%s" % self._univentionAdminPropertiesContainerDn)
		productClassMember = Object("cn=opsiProductClassMember,%s" % self._univentionAdminPropertiesContainerDn)
		productDependency = Object("cn=opsiProductDependency,%s" % self._univentionAdminPropertiesContainerDn)
		productClassDependency = Object("cn=opsiProductClassDependency,%s" % self._univentionAdminPropertiesContainerDn)
		
		for obj in [ opsiClientKey , opsiServerKey, productState, productClassMember, productDependency, productClassDependency ]:
			try:
				obj.deleteFromDirectory(self._ldap)
			except Exception, e:
				logger.error("Failed to delete univentionAdminProperty object '%s': %s" % (obj.getDn(), e))
	
	def addDefaultPolicyContainer(self, dn):
		try:
			defaultContainers = Object(self._defaultContainersObjectDn)
			defaultContainers.readFromDirectory(self._ldap)
			defaultContainers.addAttributeValue('univentionPolicyObject', dn)
			defaultContainers.writeToDirectory(self._ldap)
		except Exception, e:
			logger.error("Failed to add default policy container: %s" % e)
	
	
	def createOpsiBase(self):
		# Create some containers
		self.createOrganizationalRole(self._opsiBaseDn)
		self.createOrganizationalRole(self._hostsContainerDn)
		self.createOrganizationalRole(self._groupsContainerDn)
		self.createOrganizationalRole(self._productsContainerDn)
		self.createOrganizationalRole(self._productDependenciesContainerDn)
		self.createOrganizationalRole(self._productClassesContainerDn)
		self.createOrganizationalRole(self._productClassDependenciesContainerDn)
		self.createOrganizationalRole(self._policiesContainerDn)
		self.createOrganizationalRole(self._productPropertyPoliciesContainerDn)
		self.createOrganizationalRole(self._productStatesContainerDn)
		self.createOrganizationalRole(self._productDeploymentPoliciesContainerDn)
		self.createOrganizationalRole(self._networkConfigPoliciesContainerDn)
		self.createOrganizationalRole(self._generalConfigPoliciesContainerDn)
		self.createOrganizationalRole(self._productLicensesContainerDn)
		
		self.addDefaultPolicyContainer(self._productPropertyPoliciesContainerDn)
		self.addDefaultPolicyContainer(self._productDeploymentPoliciesContainerDn)
		self.addDefaultPolicyContainer(self._networkConfigPoliciesContainerDn)
		self.addDefaultPolicyContainer(self._generalConfigPoliciesContainerDn)
		
		#self.createUniventionSyntaxObjects()
		#self.createUniventionAdminProperties()
	
	
	def createServer(self, serverName, domain, description=None, notes=None):
		if not re.search('^[a-zA-Z0-9\-]+$', serverName):
			raise BackendBadValueError("Unallowed char in hostname")
		
		if not domain:
			domain = self._defaultDomain
		
		serverDn = None
		# Search hostname in host conatiner of the domain
		try:
			search = ObjectSearch(self._ldap, self.getHostContainerDn(domain), 
					filter='(&(objectClass=univentionHost)(cn=%s))' % serverName)
			serverDn = search.getDn()
		except Exception, e:
			# Host not found
			# We will not create server objects in Univention LDAP!
			raise BackendMissingDataError("Server '%s' does not exist in LDAP, use Univention-Admin to create host!" % serverName)
		
		server = Object(serverDn)
		server.readFromDirectory(self._ldap)
		serverId = self.getHostId(serverDn)
		if 'opsiServer' in server.getObjectClasses():
			raise BackendIOError("Opsi-server '%s' already exists!" % serverId)
		
		server.addObjectClass('opsiServer')
		server.addObjectClass(self._policyReferenceObjectClass)
		server.writeToDirectory(self._ldap)
		logger.info("Added objectclass 'opsiServer' to object '%s'" % serverId)
		
		return serverId
	
	def createClient(self, clientName, domain=None, description=None, notes=None, ipAddress=None, hardwareAddress=None):
		if not re.search('^[a-zA-Z0-9\-]+$', clientName):
			raise BackendBadValueError("Unallowed char in hostname")
		
		if not domain:
			domain = self._defaultDomain
		
		clientDn = None
		# Search hostname in host conatiner of the domain
		try:
			search = ObjectSearch(self._ldap, self.getHostContainerDn(domain), 
					filter='(&(objectClass=univentionHost)(cn=%s))' % clientName)
			clientDn = search.getDn()
		except Exception, e:
			# Host not found
			if not (ipAddress and hardwareAddress):
				raise BackendMissingDataError("Client '%s' does not exist in LDAP, use Univention-Admin to create host!" % clientName)
			
			if not re.search('^[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}:[a-f\d]{2}$', hardwareAddress):
				raise BackendBadValueError("Bad hardware ethernet address '%s'" % hardwareAddress)
			if not re.search('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ipAddress):
				raise BackendBadValueError("Bad ipaddress '%s'" % ipAddress)
			execute( "/usr/sbin/univention-admin computers/windows create" + \
					" --binddn '%s' --bindpw '%s' --position='%s'" % (self._username, self._password, self._hostsContainerDn) + \
					" --set name='%s' --set mac='%s'" % (clientName, hardwareAddress) + \
					" --set ip='%s' --set network='cn=default,cn=networks,%s'" % (ipAddress, self._baseDn),
				logLevel = LOG_CONFIDENTIAL )
			clientDn = "cn=%s,%s" % (clientName, self._hostsContainerDn)
			
		client = Object(clientDn)
		client.readFromDirectory(self._ldap)
		clientId = self.getHostId(clientDn)
		if 'opsiClient' in client.getObjectClasses():
			raise BackendIOError("Opsi-client '%s' already exists!" % clientId)
		
		client.addObjectClass('opsiClient')
		client.addObjectClass(self._policyReferenceObjectClass)
		if description:
			client.setAttribute('description', [ description ])
		if notes:
			client.setAttribute('opsiNotes', [ notes ])
		client.writeToDirectory(self._ldap)
		logger.info("Added objectclass 'opsiClient' to object '%s'" % clientId)
		
		return clientId
	
	def getMacAddresses_list(self, objectId):
		''' Get host's mac address from ldap '''
		
		host = Object(self.getHostDn(objectId))
		host.readFromDirectory(self._ldap, 'macAddress')
		return host.getAttribute('macAddress', [], valuesAsList=True)
		
	def setProductInstallationStatus(self, productId, objectId, installationStatus, policyId="", licenseKey=""):
		OPSI.Backend.LDAP.LDAPBackend.setProductInstallationStatus(self, productId, objectId, installationStatus, policyId, licenseKey)
		
		# Read host object from backend
		hostDn = self.getHostDn(objectId)
		host = Object(hostDn)
		host.readFromDirectory(self._ldap)
		
		# Read product object from backend
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		product.readFromDirectory(self._ldap)
		
		if installationStatus in ['installed'] and 'opsiServer' in host.getObjectClasses():
			# Host is a server
			# Create productState objects for all connected clients
			# otherwise the searchFilter of univentionAdminProperty opsiProductState 
			# will not display all available products for a client
			for clientId in self.getClientIds_list(serverId = self.getHostId(host.getDn())):
				client = Object(self.getHostDn(clientId))
				productState = Object( 'cn=%s,cn=%s,%s' % (product.getCn(), client.getCn(), self._productStatesContainerDn) )
				try:
					productState.readFromDirectory(self._ldap)
				except BackendIOError, e:
					# Create productState container for selected host
					self.createOrganizationalRole( 'cn=%s,%s' % (client.getCn(), self._productStatesContainerDn) )
					
					productState.new('opsiProductState')
					productState.setAttribute( 'opsiHostReference', [ client.getDn() ] )
					productState.setAttribute( 'opsiProductReference', [ product.getDn() ] )
					productState.setAttribute( 'opsiProductInstallationStatus', [ 'not_installed' ] )
					productState.writeToDirectory(self._ldap)
	
	
	def getProductProperties_hash(self, productId, objectId = None):
		if not objectId:
			objectId = self._defaultDomain
		
		# Search product object
		properties = {}
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except Exception, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (prductId, e))
			return properties
		
		try:
			# Search policy
			policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyFilter = '(&(objectClass=opsiPolicyProductProperty)(opsiProductReference=%s))' % product.getDn(),
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
			
			for (key, value) in policySearch.getResult().items():
				logger.critical("%s=%s" % (key, value) )
				if (key == 'opsiProductReference'):
					continue
				properties[key] = value['value']
				
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
			return properties
		
		return properties
	
	def deleteProductProperty(self, productId, property, objectId = None):
		productId = productId.lower()
		property = property.lower()
		if not objectId or (objectId == self.getServerId()):
			# ObjectId not specified => delete from all policies
			objectId = self._defaultDomain
		
		# Search product object
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except Exception, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (productId, e))
			return properties
		
		try:
			policySearch = None
			if (objectId == self._defaultDomain):
				policySearch = ObjectSearch(
						self._ldap,
						self._productPropertyPoliciesContainerDn,
						filter='(objectClass=opsiPolicyProductProperty)' )
			
			else:
				policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyContainer = self._productPropertyPoliciesContainerDn,
						policyFilter = '(objectClass=opsiPolicyProductProperty)',
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
						
			for policy in policySearch.getObjects():
				policy.readFromDirectory(self._ldap)
				opsiProductProperties = []
				try:
					opsiProductProperties = policy.getAttribute('opsiProductProperty', valuesAsList=True)
				except BackendMissingDataError:
					continue
				logger.debug("Current properties in policy: %s" % opsiProductProperties)
				newOpsiProductProperties = []
				for opsiProductProperty in opsiProductProperties:
					if (opsiProductProperty.split()[0].strip().lower() == productId) and (opsiProductProperty.split()[1].strip().lower() == property):
						continue
					newOpsiProductProperties.append(opsiProductProperty)
				logger.debug("New properties in policy: %s" % newOpsiProductProperties)
				if newOpsiProductProperties:
					policy.setAttribute('opsiProductProperty', newOpsiProductProperties)
					policy.writeToDirectory(self._ldap)
				else:
					self.deletePolicy(policy.getDn())
				
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
		
	
	def deleteProductProperties(self, productId, objectId = None):
		productId = productId.lower()
		if not objectId or (objectId == self.getServerId()):
			# ObjectId not specified => delete from all policies
			objectId = self._defaultDomain
		
		# Search product object
		product = None
		try:
			search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
			product = search.getObject()
		except Exception, e:
			# Product not found
			logger.warning("Product '%s' not found: %s" % (productId, e))
			return properties
		
		try:
			policySearch = None
			if (objectId == self._defaultDomain):
				policySearch = ObjectSearch(
						self._ldap,
						self._productPropertyPoliciesContainerDn,
						filter='(objectClass=opsiPolicyProductProperty)' )
			
			else:
				policySearch = PolicySearch(
						self._ldap, self.getObjectDn(objectId),
						policyContainer = self._productPropertyPoliciesContainerDn,
						policyFilter = '(objectClass=opsiPolicyProductProperty)',
						policyReferenceObjectClass = self._policyReferenceObjectClass,
						policyReferenceAttributeName = self._policyReferenceAttributeName )
						
			for policy in policySearch.getObjects():
				policy.readFromDirectory(self._ldap)
				opsiProductProperties = []
				try:
					opsiProductProperties = policy.getAttribute('opsiProductProperty', valuesAsList=True)
				except BackendMissingDataError:
					continue
				logger.debug("Current properties in policy: %s" % opsiProductProperties)
				newOpsiProductProperties = []
				for opsiProductProperty in opsiProductProperties:
					if (opsiProductProperty.split()[0].strip().lower() == productId):
						continue
					newOpsiProductProperties.append(opsiProductProperty)
				logger.debug("New properties in policy: %s" % newOpsiProductProperties)
				if newOpsiProductProperties:
					policy.setAttribute('opsiProductProperty', newOpsiProductProperties)
					policy.writeToDirectory(self._ldap)
				else:
					self.deletePolicy(policy.getDn())
		
		except BackendMissingDataError, e:
			# No policy / no attributes found
			logger.warning(e)
	
	def setPXEBootConfiguration(self, hostId, args = {}):
		host = Object( self.getHostDn(hostId) )
		host.readFromDirectory(self._ldap)
		host.setAttribute('univentionWindowsReinstall', [ '1' ])
		host.writeToDirectory(self._ldap)
		
	def unsetPXEBootConfiguration(self, hostId):
		host = Object( self.getHostDn(hostId) )
		host.readFromDirectory(self._ldap)
		host.setAttribute('univentionWindowsReinstall', [ '0' ])
		host.writeToDirectory(self._ldap)
	
	def getPolicyDn(self, objectCn, policyContainerDn):
		''' This function returns a unique, unused dn for a new policy '''
		cns = []
		dn = ''
		try:
			search = ObjectSearch(self._ldap, policyContainerDn, scope=ldap.SCOPE_ONELEVEL)
			cns = search.getCns()
		except:
			pass
		if objectCn not in cns:
			dn = "cn=%s,%s" % (objectCn, policyContainerDn)
		else:
			num = 0
			while objectCn+'_'+str(num) in cns:
				num += 1
			dn = "cn=%s_uv%s,%s" % (objectCn, num, policyContainerDn)
		logger.debug("Returning unique policy dn '%s'" % dn)
		return dn
	
	def createProductPropertyPolicy(self, productId, containerDn, properties):
		# Sanity checks
		if ( type(properties) != type({}) ):
			raise BackendBadValueError("Type of Properties has to be dict")
		
		# Search product object
		search = ObjectSearch(self._ldap, self._productsContainerDn, filter='(&(objectClass=opsiProduct)(cn=%s))' % productId)
		product = search.getObject()
		
		# Read container object from backend
		container = Object(containerDn)
		container.readFromDirectory(self._ldap)
		
		policy = None
		new = True
		
		try:
			for policyReference in container.getAttribute(self._policyReferenceAttributeName, valuesAsList = True):
				policy = Object(policyReference)
				try:
					policy.readFromDirectory(self._ldap)
					if 'opsiPolicyProductProperty' in policy.getObjectClasses():
						new = False
						logger.debug("Modifying existing policy '%s'" % policy.getDn())
						for productProperty in policy.getAttribute('opsiProductProperty', [], valuesAsList = True):
							if (productProperty.split(' ')[0] == productId):
								logger.debug("Deleting productProperty: %s" % productProperty)
								policy.deleteAttributeValue('opsiProductProperty', productProperty)
				except BackendIOError, e:
					logger.error("Failed to read policy: %s" % e)
		
		except BackendMissingDataError, e:
			pass
		
		if new:
			policy = Object(
				self.getPolicyDn( 
					container.getCn(), self._productPropertyPoliciesContainerDn ) )
			policy.new('opsiPolicyProductProperty')
			logger.debug("Creating new policy '%s'" % policy.getDn())
		
		for (key, value) in properties.items():
			policy.addAttributeValue('opsiProductProperty', "%s %s %s" % (productId, key.lower(), value))			
		policy.writeToDirectory(self._ldap)
		
		if new:
			# Add policy reference to container
			logger.info("Adding policy reference '%s' to container '%s'" % (policy.getDn(), container.getDn()) )
			container.addAttributeValue(self._policyReferenceAttributeName, policy.getDn())
			
		container.writeToDirectory(self._ldap)

# ======================================================================================================
# =                                    CLASS POLICYSEARCH                                              =
# ======================================================================================================

class UniventionPolicySearch(OPSI.Backend.LDAP.LDAPPolicySearch):
	def __init__(self, ldapSession, dn, policyContainer = None, policyFilter = None, independenceAttribute = None,
		     maxLevel = 100, policyReferenceObjectClass = 'univentionPolicyReference', policyReferenceAttributeName = 'univentionPolicyReference'):
		''' 
		Search policies for an ldap-object given by dn. Specify a 
		policyContainer to ignore policies outside this container.
		Specify a policyFilter to ignore policies which do not
		match the filter. An independenceAttribute can be given 
		to treat policies of the same type as independent if this 
		attribute differs.
		'''
		logger.info("OPSI.Backend.Univention.PolicySearch constructor called")
		
		OPSI.Backend.LDAP.LDAPPolicySearch.__init__(self, ldapSession, dn, policyContainer, policyFilter, independenceAttribute,
								maxLevel, policyReferenceObjectClass, policyReferenceAttributeName)
		self.policyObjectClass = 'univentionPolicy'
		
	def search(self):
		logger.debug('using univention policy search')
		self._policies = []
		self._joinedAttributes = {}
		
		referencePriorities = [[]]
		
		dnPath = self.dn.split(',')
		for i in range( len(dnPath) ):
			dnPath[i] = dnPath[i].strip()
			referencePriorities.append([])
		
		# The closer a policy is connected to an ldap object (policyReference) the higher its priority
		for i in range( len(dnPath)-1 ):
			# Search all policy references, and sort by priority
			
			currentDn = ','.join(dnPath[i:])
			
			if (i > self.maxLevel-1):
				logger.debug( "Omitting dn '%s', maxLevel: %s" % (currentDn, self.maxLevel) )
				continue
			
			logger.info( "Searching policy references for dn '%s'" % currentDn )
			try:
				result = self.ldapSession.search(	
						baseDn     = currentDn,
						scope      = ldap.SCOPE_BASE,
						filter     = "(&(ObjectClass=%s)(%s=*))" \
							% (self.policyReferenceObjectClass, self.policyReferenceAttributeName),
						attributes = [ self.policyReferenceAttributeName ] )
			except BackendMissingDataError, e:
				logger.debug( "No policy references found!" )
				continue
			
			for j in range( len(result[0][1][self.policyReferenceAttributeName]) ):
				#if self.policyContainer and not result[0][1][self.policyReferenceAttributeName][j].endswith(self.policyContainer):
				#	logger.debug("Omitting policy reference '%s': does not match policyContainer" \
				#			% result[0][1][self.policyReferenceAttributeName][j])
				#	continue
				logger.debug( "Policy reference found: '%s', priority: %s" % (result[0][1][self.policyReferenceAttributeName][j], i) )
				referencePriorities[i].append( result[0][1][self.policyReferenceAttributeName][j] )
		
		policyResult = {}
		
		# Examine all found policies
		# Start with the lowest priority
		for i in range (len(referencePriorities)-1, -1, -1):
			if (referencePriorities[i] == []):
				# No policy references of that priority found
				continue
			
			for j in range( len(referencePriorities[i]) ):
				productReferenceFilter = None
				
				filter = "(ObjectClass=%s)" % self.policyObjectClass
				if self.policyFilter:
					filter = self.policyFilter
					if (self.policyFilter.find('objectClass=opsiPolicyProductProperty') != -1) or \
					   (self.policyFilter.find('objectClass=opsiPolicyProductDeployment') != -1):
						match = re.search("^(.*)\(opsiProductReference=([^\)]+)\)(.*)$", self.policyFilter)
						if match:
							productReferenceFilter = match.group(2)
							filter = match.group(1) + '(cn=*)'+ match.group(3)
							logger.debug("Filter '%s' rewritten to '%s'" % (self.policyFilter, filter))
							
				logger.info("Searching in baseDN '%s', filter: %s" % 
						(referencePriorities[i][j], filter) )
				
				# Read the policy object
				try:
					objectSearch = ObjectSearch(
								self.ldapSession, 
								referencePriorities[i][j], 
								scope = ldap.SCOPE_BASE, 
								filter = filter )
					policy = objectSearch.getObject()
					policy.readFromDirectory(self.ldapSession)
				except BackendIOError, e:
					logger.warning("Cannot read policy '%s' from LDAP" % 
								referencePriorities[i][j])
					continue
				except BackendMissingDataError, e:
					logger.debug("Policy '%s' does not match filter '%s'\n" % 
								(referencePriorities[i][j], filter) )
					continue
				
				# Policy matches filter and was successfully read
				
				policies = [ policy ]
				if 'opsiPolicyProductDeployment' in policy.getObjectClasses():
					# univention workaround
					logger.info("Special handling for policy type opsiPolicyProductDeployment needed (simulating multiple policies)")
					policies = []
					self.independenceAttribute = 'opsiProductReference'
					for productDeployment in policy.getAttribute('opsiProductDeployment', valuesAsList = True):
						try:
							productSearch = ObjectSearch(	self.ldapSession, 
											#self._productsContainerDn, 
											filter='(&(objectClass=opsiProduct)(cn=%s))' % productDeployment.split(' ')[0])
							
							if productReferenceFilter and (productSearch.getDn() != productReferenceFilter):
								logger.info("Not creating faked policy, product reference does not match")
								continue
							
							p = Object( policy.getDn() )
							p.new('opsiPolicyProductDeployment')
							p.setAttribute('opsiProductReference', 		[ productSearch.getDn() ])
							p.setAttribute('opsiProductInstallationStatus', 	[ productDeployment.split(' ')[1] ])
							p.setAttribute('opsiProductVersion', 			[ productDeployment.split(' ')[2] ])
							p.setAttribute('opsiPackageVersion', 			[ productDeployment.split(' ')[3] ])
							p.setAttribute('opsiProductDeploymentTimestamp', 	[ productDeployment.split(' ')[4] ])
							policies.append(p)
						except Exception, e:
							logger.error("Failed to create faked policy object: %s" % e)
				
				elif 'opsiPolicyProductProperty' in policy.getObjectClasses():
					# univention workaround
					logger.info("Special handling for policy type opsiPolicyProductProperty needed (simulating multiple policies)")
					policies = []
					self.independenceAttribute = 'opsiProductReference'
					
					for productProperty in policy.getAttribute('opsiProductProperty', valuesAsList = True):
						try:
							productSearch = ObjectSearch(	self.ldapSession, 
											#self._productsContainerDn, 
											filter='(&(objectClass=opsiProduct)(cn=%s))' % productProperty.split(' ')[0])
							
							if productReferenceFilter and (productSearch.getDn() != productReferenceFilter):
								logger.info("Not creating faked policy, product reference does not match")
								continue
							
							p = Object( policy.getDn() )
							p.new('opsiPolicyProductProperty')
							p.setAttribute('opsiProductReference',	[ productSearch.getDn() ])
							p.setAttribute('opsiKeyValuePair', 	[ productProperty.split(' ')[1] + '=' + productProperty.split(' ')[2] ])
							policies.append(p)
						except Exception, e:
							logger.error("Failed to create faked policy object: %s" % e)
				
				for policy in policies:
					logger.info("Processing matching policy '%s'\n" % policy.getDn() )
					
					# Sort policies by their type (objectClass)
					policyType = None
					for objectClass in policy.getObjectClasses():
						if (objectClass != self.policyObjectClass):
							policyType = objectClass
					
					if not policyType:
						logger.error("Cannot get policy-type for policy: '%s'" % policy.getDn())
						continue
					
					# Group policies by an attribute
					# Attributes of policies in the same group will overwrite each other by priority
					policyGroup = 'default'
					if (self.independenceAttribute):
						# An independence attribute was passed to the constructor
						policyGroup = policy.getAttribute(self.independenceAttribute)
						if not policyGroup:
							logger.error("Independence attribute given, cannot read attribute '%s' from policy '%s'" \
									% (self.independenceAttribute, policy.getDn()) )
							continue
					
					if not policyResult.has_key(policyType):
						policyResult[policyType] = {}
					
					policyResult[policyType][policyGroup] = policy
					
					logger.debug("Current policy result: %s" % policyResult)
					
					for (key, value) in policy.getAttributeDict().items():
						if ( key in ('cn', 'objectClass', 'emptyAttributes', 
							     'fixedAttributes', 'prohibitedObjectClasses',
							     'requiredObjectClasses', 'overwritePolicies') ): 	
							continue
						
						if (key == 'opsiKeyValuePair'):
							if type(value) != type(()) and type(value) != type([]):
								value = [ value ]
							for v in value:
								key = v
								pos = v.find('=')
								if (pos != -1):
									key = v[:pos]
									v = v[pos+1:]
								else:
									v = None
								# joinedAttributes can be overwritten by policies with a higher priority
								logger.debug("joinedAttributes: (opsiKeyValuePair) setting key '%s' to value '%s'" \
										% (key, v) )
								self._joinedAttributes[key] = { 'value': v, 'policy': policy.getDn() }
						else:
							# joinedAttributes can be overwritten by policies with a higher priority
							logger.debug("joinedAttributes: setting key '%s' to value '%s'" \
										% (key, value) )
							self._joinedAttributes[key] = { 'value': value, 'policy': policy.getDn() }
		
		for policyType in policyResult:
			if ( len(policyResult[policyType].values()) < 1 ): continue
			for policy in policyResult[policyType].values():
				self._policies.append(policy)
				
		if not self._policies:
			raise BackendMissingDataError("No policy found for: %s, con: %s, fil: %s, ia: %s, ml: %s" \
						% (self.dn, self.policyContainer, self.policyFilter, self.independenceAttribute, self.maxLevel) )
		
		logger.info("= = = = = = = = = = = < policy search result > = = = = = = = = = = =" )
		for policy in self._policies:
			logger.info(policy.getDn())
		logger.info("= = = = = = = = = = = = < joined attributes > = = = = = = = = = = = =" )
		for (key, value) in self._joinedAttributes.items():
			logger.info("'%s' = '%s'" % (key, value['value']))
		logger.info("= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = " )
		
class UniventionObject(OPSI.Backend.LDAP.LDAPObject):
	def __init__(self, dn):
		OPSI.Backend.LDAP.LDAPObject.__init__(self, dn)

class UniventionObjectSearch(OPSI.Backend.LDAP.LDAPObjectSearch):
	def __init__(self, ldapSession, baseDn='', scope=ldap.SCOPE_SUBTREE, filter='(ObjectClass=*)'):
		OPSI.Backend.LDAP.LDAPObjectSearch.__init__(self, ldapSession, baseDn, scope, filter)

class UniventionSession(OPSI.Backend.LDAP.LDAPSession):
	def __init__(self, host='127.0.0.1', username='', password='', ldap=None):
		OPSI.Backend.LDAP.LDAPSession.__init__(self, host, username, password, ldap)


Object = UniventionObject
ObjectSearch = UniventionObjectSearch
PolicySearch = UniventionPolicySearch
Session = UniventionSession

OPSI.Backend.LDAP.Object = UniventionObject
OPSI.Backend.LDAP.ObjectSearch = UniventionObjectSearch
OPSI.Backend.LDAP.PolicySearch = UniventionPolicySearch
OPSI.Backend.LDAP.Session = UniventionSession

