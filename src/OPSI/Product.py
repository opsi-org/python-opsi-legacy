# -*- coding: utf-8 -*-
"""
   ===============================================
   =            OPSI Product Module              =
   ===============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.7.0'

# Imports
import os
if os.name == 'posix':
	import stat, gettext, time, pwd, grp, re
else:
	import stat, gettext, time, re

# OPSI imports
from OPSI.Logger import *
from OPSI.System import *
from OPSI.Config import OpsiConfig
from OPSI import Tools
if os.name == 'nt':
	from _winreg import *

# Get Logger instance
logger = Logger()

# Globals
if os.name == 'posix':
	PRODUCTS_SOURCE_DIR = '/home/root/BK-ServerInstallation'
	LOCK_DIR = '/tmp'
else:
	PRODUCTS_SOURCE_DIR = 'C:\opsidemo'
	LOCK_DIR = 'C:\tmp'

opsiConfig = OpsiConfig()

ARCHIVE_FORMAT = 'cpio'
#ARCHIVE_FORMAT = 'tar'

DEFAULT_CLIENT_DATA_GROUP = 'pcpatch'
DEFAULT_CLIENT_DATA_FILE_MODE = 0660
DEFAULT_CLIENT_DATA_DIR_MODE = 0770
EXCLUDE_DIRS_ON_PACK = '^\.svn$'

PRODUCT_ID_REGEX = re.compile("^[a-zA-Z0-9\_\.-]+$")
PACKAGE_VERSION_REGEX = re.compile("^[\w\.]+$")
PRODUCT_VERSION_REGEX = re.compile("^[\w\.]+$")

POSSIBLE_PRODUCT_ACTIONS = (	'undefined',	'by_policy',
				'setup',	'setup_by_policy',
				'start_install',
				'update',	'update_by_policy',
				'uninstall',	'uninstall_by_policy',
				'once', 
				'always', 
				'none',		'none_by_policy' )

POSSIBLE_FORCED_PRODUCT_ACTIONS = ( 'undefined', 'setup', 'start_install', 'update', 'uninstall', 'once', 'always', 'none' )

# TODO: uninstalled ???
POSSIBLE_PRODUCT_INSTALLATION_STATUS = ('undefined', 'installing', 'installed', 'uninstalled', 'not_installed', 'failed')
POSSIBLE_REQUIREMENT_TYPES = ('before', 'after')
POSSIBLE_PRODUCT_TYPES = ('netboot', 'localboot', 'server')

def getPossibleProductActions():
	return POSSIBLE_PRODUCT_ACTIONS

def getPossibleProductInstallationStatus():
	return POSSIBLE_PRODUCT_INSTALLATION_STATUS
	
def getPossibleRequirementTypes():
	return POSSIBLE_REQUIREMENT_TYPES


# Get locale
try:
	t = gettext.translation('product', LOCALE_DIR)
	_ = t.ugettext
except Exception, e:
	logger.info("Locale not found: %s" % e)
	def _(string):
		"""Dummy method, created and called when no locale is found.
		Uses the fallback language (called C; means english) then."""
		return string

class Product:
	
	def __init__(self, productId="", productType=None, name='', productVersion='', packageVersion='', licenseRequired=False,
			   setupScript='', uninstallScript='', updateScript='', alwaysScript='', onceScript='', 
			   priority=0, description='', advice='', productClassNames=[], pxeConfigTemplate=''):
		self.productId = productId
		self.productType = productType
		self.name = name
		self.productVersion = productVersion
		self.packageVersion = packageVersion
		self.licenseRequired = licenseRequired
		self.setupScript = setupScript
		self.uninstallScript = uninstallScript
		self.updateScript = updateScript
		self.alwaysScript = alwaysScript
		self.onceScript = onceScript
		self.priority = priority
		self.description = description
		self.advice = advice
		self.productClassNames = productClassNames
		self.pxeConfigTemplate = pxeConfigTemplate
		
		if not self.productVersion:
			self.productVersion = '1.0'
		if not self.packageVersion:
			self.packageVersion = '1'
		if not self.productClassNames:
			self.productClassNames = []
		if not self.licenseRequired:
			self.licenseRequired = False
		if not self.priority:
			self.priority = 0
		
		self.productProperties = []
		self.productDependencies = []
		
		if self.productId:
			self.setProductId(self.productId)
		if self.productType:
			self.setProductType(self.productType)
		if self.name:
			self.setName(self.name)
		if self.productVersion:
			self.setProductVersion(self.productVersion)
		if self.packageVersion:
			self.setPackageVersion(self.packageVersion)
		if self.licenseRequired:
			self.setLicenseRequired(self.licenseRequired)
		if self.priority:
			self.setPriority(self.priority)
		if self.description:
			self.setDescription(self.description)
		if self.advice:
			self.setAdvice(self.advice)
		if self.productClassNames:
			self.setProductClassNames(self.productClassNames)
		if self.pxeConfigTemplate:
			self.setPxeConfigTemplate(self.pxeConfigTemplate)
		
	def setProductId(self, productId):
		if not re.search(PRODUCT_ID_REGEX, productId):
			raise Exception ("Bad value '%s' for product id" % productId)
		
		self.productId = productId
		self.filesFile = os.path.join( PRODUCTS_SOURCE_DIR, self.productId, self.productId + '.files')
		self.filelistFile = os.path.join(PRODUCTS_SOURCE_DIR, self.productId, self.productId + ".filelist")
		self.productSourceDir = os.path.join(PRODUCTS_SOURCE_DIR, self.productId)
	
	def setProductType(self, productType):
		if not productType in POSSIBLE_PRODUCT_TYPES:
			raise Exception ("Bad value '%s' for product type. Possible values are: %s" \
				% (productType, POSSIBLE_PRODUCT_TYPES) )
		self.productType = productType
	
	def setName(self, name):
		if not name:
			raise Exception ("Bad value '%s' for product name" % name)
		self.name = str(name)
	
	def setProductVersion(self, productVersion):
		if not re.search(PRODUCT_VERSION_REGEX, productVersion):
			raise Exception ("Bad value '%s' for product version" % productVersion)
		self.productVersion = str(productVersion)
	
	def setPackageVersion(self, packageVersion):
		if not re.search(PACKAGE_VERSION_REGEX, packageVersion):
			raise Exception ("Bad value '%s' for package version" % packageVersion)
		self.packageVersion = str(packageVersion)
			
	def setLicenseRequired(self, licenseRequired):
		if type(licenseRequired) is bool:
			self.licenseRequired = licenseRequired
			return
		if not licenseRequired or licenseRequired.lower() in ['0', 'no', 'nein', 'false']:
			self.licenseRequired = False
		else:
			self.licenseRequired = True
	
	def setPriority(self, priority):
		try:
			self.priority = int(priority)
		except:
			raise Exception ("Bad value '%s' for priority (integer required)" % priority)
	
	def setDescription(self, description):
		self.description = str(description)
		
	def setAdvice(self, advice):
		self.advice = str(advice)
		
	def setProductClassNames(self, productClassNames):
		if (type(productClassNames) != type(()) and type(productClassNames) != type([])):
			raise Exception ("Bad value '%s' for product class names (list required)" % productClassNames)
		self.productClassNames = productClassNames
	
	def setPxeConfigTemplate(self, pxeConfigTemplate):
		if pxeConfigTemplate and (self.productType != 'netboot'):
			logger.warning("Cannot set pxeConfigTemplate for product type '%s'" % self.productType)
			self.pxeConfigTemplate = ''
			return
		self.pxeConfigTemplate = pxeConfigTemplate
	
	def setSetupScript(self, setupScript):
		self.setupScript = setupScript
	
	def setUninstallScript(self, uninstallScript):
		self.uninstallScript = uninstallScript
	
	def setUpdateScript(self, updateScript):
		self.updateScript = updateScript
	
	def setAlwaysScript(self, alwaysScript):
		self.alwaysScript = alwaysScript
	
	def setOnceScript(self, onceScript):
		self.onceScript = onceScript
	
	''' 
	end set/get
	'''
	
	def addProductProperty(self, productProperty):
		self.productProperties.append(productProperty)
	
	def addProductDependency(self, productDependency):
		self.productDependencies.append(productDependency)
	
	def readControlFile(self, controlFile):
		logger.info("Reading control file '%s'" % controlFile)
		cf = open (controlFile)
		
		result= []
		section = None
		option = None
		lineNum = 0
		for line in cf.readlines():
			lineNum += 1
			if line.startswith(';') or line.startswith('#'):
				# Comment
				continue
			
			if (line.rstrip().lower() == '[package]'):
				section = 'package'
				result.append({ 'section': section })
				continue
			
			elif (line.rstrip().lower() == '[product]'):
				section = 'product'
				result.append({ 'section': section })
				continue
				
			elif (line.rstrip().lower() == '[productdependency]'):
				section = 'productdependency'
				result.append({ 'section': section })
				continue
				
			elif (line.rstrip().lower() == '[productproperty]'):
				section = 'productproperty'
				result.append({ 'section': section })
				continue
			
			elif not section and line:
				raise Exception("Parse error in line '%s': not in a section" % lineNum)
			
			key = None
			value = None
			if re.search("^\s+", line):
				value = line
			elif re.search("^\S+\:", line):
				(key, value) = line.split(':', 1)
				key = key.lower()
				value = value.lstrip()
			
			if (section == 'package' and key in \
					['version', 'depends', 'incremental']):
				option = key
			
			elif (section == 'product' and key in \
					['id', 'type', 'name', 	'description', 'advice', 
					 'version', 'packageversion', 'priority', 
					 'licenserequired', 'productclasses', 'pxeconfigtemplate',
					 'setupscript', 'uninstallscript', 'updatescript',
					 'alwaysscript', 'oncescript']):
				option = key
			
			elif (section == 'productdependency' and key in \
					['action', 'requiredproduct', 'requiredclass', 
					 'requiredstatus', 'requiredaction', 'requirementtype']):
				option = key
			
			elif (section == 'productproperty' and key in \
					['name', 'default', 'values', 'description']):
				option = key
			
			else:
				value = line
			
			if not option:
				raise Exception("Parse error in line '%s': no option / bad option defined" % lineNum)
				
			if not result[-1].has_key(option):
				result[-1][option] = value.rstrip()
			else:
				result[-1][option] += '\n' + value.rstrip()
		
		for section in result:
			for (option, value) in section.items():
				if (option == 'description'):
					value = value.rstrip()
				
				elif (section['section'] == 'product' and option == 'productclasses') or \
				     (section['section'] == 'package' and option == 'depends') or \
				     (section['section'] == 'productproperty' and option == 'values'):
					value = value.replace('\n', '')
					value = value.replace('\t', '')
					value = value.split(',')
					value = map ( lambda x:x.strip(), value )
					# Remove duplicates
					tmp = []
					for v in value:
						if v and v not in tmp:
							tmp.append(v)
					value = tmp
				else:
					value = value.replace('\n', '')
					value = value.replace('\t', '')
				
				section[option] = value
			
			if (section['section'] == 'package'):
				if section.get('version'):
					self.setPackageVersion( section['version'] )
			
			elif (section['section'] == 'product'):
				try:
					self.setProductId( section['id'] )
					self.setProductType( section['type'] )
					self.setName( section['name'] )
					self.setProductVersion( section['version'] )
					if section.get('packageversion'):
						self.setPackageVersion( section['packageversion'] )
					self.setLicenseRequired( section['licenserequired'] )
					self.setPriority( section['priority'] )
					self.setDescription( section['description'] )
					self.setAdvice( section['advice'] )
					self.setProductClassNames( section['productclasses'] )
					self.setSetupScript( section['setupscript'] )
					self.setUninstallScript( section['uninstallscript'] )
					self.setUpdateScript( section['updatescript'] )
					self.setAlwaysScript( section['alwaysscript'] )
					self.setOnceScript( section['oncescript'] )
					if section.get('pxeconfigtemplate'):
						self.setPxeConfigTemplate( section['pxeconfigtemplate'] )
					
				except Exception, e:
					raise Exception("Missing option %s in control file '%s'" % (e, controlFile) )
		
		for section in result:
			if (section['section'] == 'productproperty'):
				productProperty = ProductProperty(
					productId	= self.productId,
					name		= section.get('name'),
					description	= section.get('description', ''),
					possibleValues	= section.get('values', []),
					defaultValue	= section.get('default', ''), 
				)
				self.addProductProperty(productProperty)
			
			elif (section['section'] == 'productdependency'):
				productDependency = ProductDependency(
					productId 			= self.productId,
					action 				= section.get('action'),
					requiredProductId 		= section.get('requiredproduct'),
					requiredProductClassId		= section.get('requiredclass'),
					requiredAction 			= section.get('requiredaction'),
					requiredInstallationStatus 	= section.get('requiredstatus'),
					requirementType 		= section.get('requirementtype'),
				)
				self.addProductDependency(productDependency)
			
			
		#for section in result:
		#	logger.debug(section['section'])
		#	for (key, value) in section.items():
		#		if (key == section):
		#			pass
		#		else:
		#			logger.debug("%s: %s" % (key, value))
		#	logger.debug("")
		
		cf.close()
	
	def writeControlFile(self, controlFile):
		logger.info("Writing control file '%s'" % controlFile)
		# Write control file
		control = open(controlFile, 'w')
		print >> control, '[Package]'
		print >> control, 'version: %s' % self.packageVersion
		print >> control, 'depends:'
		print >> control, 'incremental: False'
		print >> control, ''
		print >> control, '[Product]'
		print >> control, 'type: %s' % self.productType
		print >> control, 'id: %s' % self.productId
		print >> control, 'name: %s' % self.name
		print >> control, 'description:',
		for line in self.description.split('\\n'):
			print >> control, line
		print >> control, 'advice: %s' % self.advice
		print >> control, 'version: %s' % self.productVersion
		print >> control, 'priority: %s' % self.priority
		print >> control, 'licenseRequired: %s' % self.licenseRequired
		print >> control, 'productClasses: %s' % ', '.join(self.productClassNames)
		print >> control, 'setupScript: %s' % self.setupScript
		print >> control, 'uninstallScript: %s' % self.uninstallScript
		print >> control, 'updateScript: %s' % self.updateScript
		print >> control, 'alwaysScript: %s' % self.alwaysScript
		print >> control, 'onceScript: %s' % self.onceScript
		if (self.productType == 'netboot'):
			print >> control, 'pxeConfigTemplate: %s' % self.pxeConfigTemplate
		
		if (self.productType != 'server'):
			for dependency in self.productDependencies:
				print >> control, '\n[ProductDependency]'
				print >> control, 'action: %s' % dependency.action
				if dependency.requiredProductId:
					print >> control, 'requiredProduct: %s' % dependency.requiredProductId
				if dependency.requiredProductClassId:
					print >> control, 'requiredClass: %s' % dependency.requiredProductClassId
				if dependency.requiredAction:
					print >> control, 'requiredAction: %s' % dependency.requiredAction
				if dependency.requiredInstallationStatus:
					print >> control, 'requiredStatus: %s' % dependency.requiredInstallationStatus
				if dependency.requirementType:
					print >> control, 'requirementType: %s' % dependency.requirementType
			
			for productProperty in self.productProperties:
				print >> control, '\n[ProductProperty]'
				print >> control, 'name: %s' % productProperty.name
				if productProperty.description:
					print >> control, 'description:',
					for line in productProperty.description.split('\\n'):
						print >> control, line
				if productProperty.possibleValues:
					print >> control, 'values: %s' % ', '.join(productProperty.possibleValues)
				if productProperty.defaultValue:
					print >> control, 'default: %s' % productProperty.defaultValue
		
		control.close()
	
	
class ProductPackage:
	def __init__(self, product):
		if not product or not product.productId:
			raise Exception('Product ID is not set')
		self.product = product
		self.clientDataDir = os.path.join(opsiConfig.getDepotDir(), self.product.productId)
		self.controlFile = None
		self.accessRights = {}
		self.customName = None
		self.incremental = False
		self.dependencies = []
	
	def lock(self):
		lockFile = os.path.join(LOCK_DIR, 'lock.' + self.product.productId)
		
		# Test if other processes are accessing same product
		try:
			lf = open(lockFile, 'r')
			p = lf.readline().strip()
			lf.close()
		
			if p:
				for line in execute("ps -A"):
					line = line.strip()
					if not line:
						continue
					if (p == line.split()[0].strip()):
						pName = line.split()[-1].strip()
						# process is running
						raise Exception("Product '%s' is currently locked by process %s (%s)." \
									% (self.product.productId, pName, p) )
		
		except IOError:
			pass
		
		# Write lock-file
		lf = open(lockFile, 'w')
		print >> lf, os.getpid()
		lf.close()
	
	def unlock(self):
		if not self.product or not self.product.productId:
			raise Exception('Product ID is not set')
		
		lockFile = os.path.join(LOCK_DIR, 'lock.' + self.product.productId)
		
		if os.path.isfile(lockFile):
			os.unlink(lockFile)
	
	def checkDependencies(self):
		logger.info("Checking package dependencies")
		for dependency in self.dependencies:
			package = dependency.get('package')
			version = dependency.get('version')
			clientDataDir = os.path.join(opsiConfig.getDepotDir(), package)
			if not os.path.isdir(clientDataDir):
				raise Exception("Dependent package '%s' not found at '%s'" % (package, clientDataDir))
			
			if not version:
				logger.info("Fulfilled product dependency '%s'" % package)
				continue
			
			condition = '=='
			requiredVersion = '0'
			match = re.search('^\s*([<>]?=?)\s*([\w\.]+-*[\w\.]*)\s*$', version)
			if not match:
				raise Exception("Bad version string '%s' in dependency" % version)
			
			condition = match.group(1)
			requiredVersion = match.group(2)
			
			controlFile = None
			for f in os.listdir(clientDataDir):
				if f.startswith(package) and f.endswith('.control'):
					controlFile = os.path.join(clientDataDir, f)
			if not controlFile:
				raise Exception("Control-file of dependent package '%s' not found in '%s'" % (package, clientDataDir))
			
			dependendPackage = ProductPackage(Product(package))
			dependendPackage.controlFile = controlFile
			dependendPackage.readControlFile()
			availableVersion = dependendPackage.product.productVersion + '-' + dependendPackage.product.packageVersion
			
			if Tools.compareVersions(availableVersion, condition, requiredVersion):
				logger.info("Fulfilled product dependency '%s %s %s' (available version: %s)" \
							% (package, condition, requiredVersion, availableVersion))
			else:
				raise Exception("Unfulfilled product dependency '%s %s %s' (available version: %s)" \
							% (package, condition, requiredVersion, availableVersion))
			
	def deleteClientDataDir(self):
		if os.path.isdir(self.clientDataDir):
			logger.notice("Deleting client data dir '%s'" % self.clientDataDir)
			rmdir(self.clientDataDir, recursive=True)
		else:
			logger.warning("Cannot delete client data dir '%s': no such directory." % self.clientDataDir)
	
	def readControlFile(self):
		self.product = Product()
		self.product.readControlFile(self.controlFile)
		
		logger.notice("Trying to read control file '%s'" % self.controlFile)
		
		cf = open (self.controlFile)
		
		section = ''
		lineNum = 0
		for line in cf.readlines():
			lineNum += 1
			line = line.strip()
			
			if not line or line.startswith(';') or line.startswith('#'):
				# Comment
				continue
			
			if line.startswith('[') and line.endswith(']'):
				section = line[1:-1].strip().lower()
				continue
			
			if (section != 'package'):
				continue
			
			if not line.find(':'):
				logger.error("Parse error in file '%s', line %s: %s" % (self.controlFile, lineNum, line))
				continue
			
			(option, value) = line.split(':')
			option = option.strip()
			value = value.strip()
			logger.debug("Processing option '%s', value: %s" % (option, value))
			
			if (option == 'depends'):
				value = value.replace('\n', '')
				value = value.replace('\t', '')
				value = value.split(',')
				value = map ( lambda x:x.replace(" ",""), value )
				# Remove duplicates
				tmp = []
				for v in value:
					if v and v not in tmp:
						tmp.append(v)
				value = tmp
				for dep in value:
					match = re.search('^\s*([^\(]+)\s*\(*\s*([^\)]*)\s*\)*', dep)
					if not match.group(1):
						logger.error("Bad package dependency '%s' in control file" % dep)
						continue
					package = match.group(1)
					version = match.group(2)
					self.dependencies.append( { 'package': package, 'version': version } )
				
			elif (option == 'incremental'):
				if value.lower() in ['1', 'true', 'yes']:
					self.incremental = True
			elif (option == 'version'):
				continue
			else:
				logger.error("Unknown option '%s' in section '[package]' of file '%s', line %s" % (option, self.controlFile, lineNum))
		
		cf.close()
	
class ProductPackageSource(ProductPackage):
	def __init__(self, sourceDir, tempDir = None, customName = None, packageFileDestDir = None):
		self.product = None
		self.dependencies = []
		
		if not tempDir:
			if os.name == 'posix':
				tempDir = '/tmp'
			else:
				tempDir = 'C:\tmp'
		
		self.sourceDir = os.path.abspath(sourceDir)
		self.tempDir = os.path.abspath(tempDir)
		
		controlFile = os.path.join(self.sourceDir, 'OPSI', 'control')
		# Read control file
		f = open(controlFile, "r")
		content = f.read()
		f.close()
		
		# Save control file as utf-8
		f = open(controlFile, "w")
		f.write(content)
		f.close()
		
		self.controlFile = controlFile
		self.readControlFile()
		ProductPackage.__init__(self, self.product)
		self.controlFile = controlFile
		
		if customName and re.search('[\_\s\-]+', customName):
			raise Exception("Custom name '%s' is not allowed!" % customName)
		self.customName = customName
		
		if self.customName:
			self.product.packageVersion += '_' + self.customName
		
		self.packageFile = "%s_%s-%s.opsi" \
			% (	self.product.productId, self.product.productVersion, 
				self.product.packageVersion )
		
		if packageFileDestDir:
			self.packageFile = os.path.join(packageFileDestDir, self.packageFile)
	
	def cleanup(self):
		if os.path.isdir(self.tmpPackDir):
			rmdir(self.tmpPackDir, recursive=True)
	
	def pack(self, format=ARCHIVE_FORMAT, compress='gz', dereference=False):
		
		self.tmpPackDir = os.path.join( self.tempDir, 'pack.%s.%s' % (self.product.productId, Tools.randomString(5)) )
		
		# Create temporary directory
		if os.path.exists(self.tmpPackDir):
			rmdir(self.tmpPackDir, recursive=True)
		os.mkdir(self.tmpPackDir)
		
		try:
			archives = []
			dirs = [ 'CLIENT_DATA', 'SERVER_DATA', 'OPSI' ]
			if self.customName:
				found = False
				for i in range(len(dirs)):
					customDir = dirs[i] + '.' + self.customName
					if os.path.exists( os.path.join(self.sourceDir, customDir) ):
						found = True
					dirs.append(customDir)
				if not found:
					raise Exception("No custom dirs found for '%s'" % self.customName)
			
			for d in dirs:
				if not os.path.exists( os.path.join(self.sourceDir, d) ) and (d != 'OPSI'):
					logger.warning("Directory '%s' does not exist!" % \
								os.path.join(self.sourceDir, d) )
					continue
				
				fileList = Tools.findFiles( os.path.join(self.sourceDir, d), excludeDir=EXCLUDE_DIRS_ON_PACK )
				
				if d.startswith('SERVER_DATA'):
					# never change permissions of existing directories in /
					tmp = []
					for f in fileList:
						if (f.find(os.sep) == -1):
							logger.info("Skipping dir '%s'" % f)
							continue
						tmp.append(f)
						
					fileList = tmp
				
				if not fileList:
					logger.notice("Skipping empty dir '%s'" % os.path.join(self.sourceDir, d))
					continue
				
				try:
					Tools.createArchive(
						filename = os.path.join(self.tmpPackDir, d + '.' + format),
						fileList = fileList,
						format = format,
						dereference = dereference,
						chdir = os.path.join(self.sourceDir, d) )
				except Exception, e:
					self.cleanup()
					raise Exception("Failed to create archive for '%s': %s" % (d, e))
				
				archive = os.path.join(self.tmpPackDir, d + '.' + format)
				if compress:
					archive = Tools.compressFile(archive, compress)
				archives.append( os.path.basename(archive) )
		
			Tools.createArchive(
					filename = self.packageFile,
					fileList = archives,
					format = format,
					chdir = self.tmpPackDir )
		except Exception, e:
			self.cleanup()
			raise Exception("Failed to create archive '%s': %s" % (self.packageFile, e))
		
		self.cleanup()
	
	def testTopicality(self):
		logger.notice("Testing topicality")
		for name in ['SERVER_DATA', 'CLIENT_DATA']:
			dirs = [ os.path.join(self.sourceDir, name) ]
			if self.customName:
				dirs.append( os.path.join(self.sourceDir, name + '.' + self.customName) )
			for d in dirs:
				if not os.path.isdir(d):
					continue
				for destination in Tools.findFiles(d):
					source = os.path.join(d, destination)
					if os.path.isdir(source):
						continue
					if (name == 'CLIENT_DATA'):
						destination = os.path.join(opsiConfig.getDepotDir(), self.product.productId, destination)
					else:
						destination = os.path.join('/', destination)
					try:
						if ( os.path.getmtime(destination) > os.path.getmtime(source) ):
							logger.warning("File '%s' is newer than '%s'" % (destination, source) )
					except:
						pass
	

class ProductPackageFile(ProductPackage):
	
	def __init__(self, packageFile, tempDir = None):
		
		if not tempDir:
			if os.name == 'posix':
				tempDir = '/tmp'
			else:
				tempDir = 'C:\tmp'
		
		self.product = Product()
		self.packageFile = os.path.abspath(packageFile)
		self.tempDir = os.path.abspath(tempDir)
		self.installedFiles = []
		
		if self.packageFile.endswith('.opsi'):
			infoFromFileName = os.path.basename(self.packageFile)[:-1*len('.opsi')].split('_')
			self.product.productId = infoFromFileName[0]
			if (len(infoFromFileName) > 1):
				i = infoFromFileName[1].find('-')
				if (i != -1):
					self.product.productVersion = infoFromFileName[1][:i]
					self.product.packageVersion = infoFromFileName[1][i+1:]
			if (len(infoFromFileName) > 2):
				self.product.customName = infoFromFileName[2]
		
		if not self.product.productId:
			self.product.productId = 'unkown'
		
		ProductPackage.__init__(self, self.product)
		self.clientDataDir = None
		
		self.tmpUnpackDir = os.path.join( self.tempDir, 'unpack.%s.%s' % (self.product.productId, Tools.randomString(5)) )
		
		# Unpack and read control file
		self.lock()
		self.unpack(dataArchives = False)
		self.unlock()
				
		self.clientDataDir = os.path.join(opsiConfig.getDepotDir(), self.product.productId)
		
		
		
	def install(self):
		self.checkDependencies()
		self.runPreinst()
		self.unpack()
		self.setAccessRights()
		self.runPostinst()
		self.cleanup()
	
	def runPostinst(self):
		postinst = os.path.join(self.tmpUnpackDir, 'postinst')
		if not os.path.exists(postinst):
			logger.warning("Postinst script '%s' does not exist" % postinst)
			return []
		os.chmod(postinst, 0700)
		
		os.putenv('PRODUCT_ID', self.product.productId)
		os.putenv('CLIENT_DATA_DIR', self.clientDataDir)
		
		try:
			return execute(postinst)
		except Exception, e:
			self.cleanup()
			raise Exception("Failed to execute '%s': %s" % (postinst, e))
	
	def runPreinst(self):
		preinst = os.path.join(self.tmpUnpackDir, 'preinst')
		if not os.path.exists(preinst):
			logger.warning("Preinst script '%s' does not exist" % preinst)
			return []
		os.chmod(preinst, 0700)
		
		os.putenv('PRODUCT_ID', self.product.productId)
		os.putenv('CLIENT_DATA_DIR', self.clientDataDir)
		
		try:
			return execute(preinst)
		except Exception, e:
			self.cleanup()
			raise Exception("Failed to execute '%s': %s" % (preinst, e))
	
	def cleanup(self):
		if os.path.isdir(self.tmpUnpackDir):
			rmdir(self.tmpUnpackDir, recursive=True)
	
	
	def unpackSource(self, sourceDir=''):
		if not sourceDir:
			raise Exception("Failed to unpack source: no destination directory given.")
		
		sourceDir = os.path.join(sourceDir, self.product.productId)
		
		if not os.path.exists(sourceDir):
			os.mkdir(sourceDir)
		
		prevUmask = os.umask(0077)
		# Create temporary directory
		if os.path.exists(self.tmpUnpackDir):
			rmdir(self.tmpUnpackDir, recursive=True)
		os.mkdir(self.tmpUnpackDir)
		os.umask(prevUmask)
		
		try:
			logger.notice("Extracting archive content to: '%s'" % self.tmpUnpackDir)
			Tools.extractArchive(self.packageFile, chdir=self.tmpUnpackDir)
		except Exception, e:
			self.cleanup()
			raise Exception("Failed to extract '%s': %s" % (self.packageFile, e))
		
		
		for f in os.listdir(self.tmpUnpackDir):
			dst = ''
			if f.endswith('.cpio.gz'):
				dst = os.path.join(sourceDir, f[:-8])
			elif f.endswith('.cpio'):
				dst = os.path.join(sourceDir, f[:-5])
			elif f.endswith('.tar.gz'):
				dst = os.path.join(sourceDir, f[:-7])
			elif f.endswith('tar'):
				dst = os.path.join(sourceDir, f[:-4])
			else:
				logger.warning("Unkown content in archive: %s" % f)
				continue
			
			if not os.path.exists(dst):
				os.mkdir(dst)
			
			f = os.path.join(self.tmpUnpackDir, f)
			logger.info("Extracting archive '%s' to '%s'" % (f, dst))
			try:
				Tools.extractArchive(f, chdir=dst)
			except Exception, e:
				self.cleanup()
				raise Exception("Failed to extract archive '%s' to '%s': %s" % (f, dst, e))
		
		self.cleanup()
		
		if not os.path.isdir( os.path.join(sourceDir, 'OPSI') ):
			os.mkdir( os.path.join(sourceDir, 'OPSI') )
		if not os.path.isdir( os.path.join(sourceDir, 'CLIENT_DATA') ):
			os.mkdir( os.path.join(sourceDir, 'CLIENT_DATA') )
		if not os.path.isdir( os.path.join(sourceDir, 'SERVER_DATA') ):
			os.mkdir( os.path.join(sourceDir, 'SERVER_DATA') )
		
		
		
	def unpack(self, dataArchives=True):
		
		prevUmask = os.umask(0077)
		# Create temporary directory
		if os.path.exists(self.tmpUnpackDir):
			rmdir(self.tmpUnpackDir, recursive=True)
		os.mkdir(self.tmpUnpackDir)
		os.umask(prevUmask)
		
		try:
			logger.notice("Extracting archive content to: '%s'" % self.tmpUnpackDir)
			Tools.extractArchive(self.packageFile, chdir=self.tmpUnpackDir)
		except Exception, e:
			self.cleanup()
			raise Exception("Failed to extract '%s': %s" % (self.packageFile, e))
		
		self.customName = None
		
		for f in os.listdir(self.tmpUnpackDir):
			if not f.endswith('cpio.gz') and not f.endswith('tar.gz') and f.endswith('cpio') and not f.endswith('tar'):
				logger.warning("Unkown content in archive: %s" % f)
			if f.endswith('.gz'):
				f = f[:-3]
			
			parts = f.split('.')
			if (len(parts) > 2):
				name = '.'.join(parts[1:-1])
				logger.notice("Custom name found: %s" % name)
				if self.customName and (self.customName != name):
					self.cleanup()
					raise Exception("More than one custom name found in archive!")
				self.customName = name
		
		names = ['OPSI']
		if dataArchives:
			mkdir( os.path.join(opsiConfig.getDepotDir(), self.product.productId) )
			self.installedFiles.append( os.path.join(opsiConfig.getDepotDir(), self.product.productId) )
			names.extend( ['SERVER_DATA', 'CLIENT_DATA'] )
		
		
		for name in names:
			archives = []
			if os.path.exists( os.path.join(self.tmpUnpackDir, name + '.tar.gz') ):
				archives.append( os.path.join(self.tmpUnpackDir, name + '.tar.gz') )
			elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.tar') ):
				archives.append( os.path.join(self.tmpUnpackDir, name + '.tar') )
			elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.cpio.gz') ):
				archives.append( os.path.join(self.tmpUnpackDir, name + '.cpio.gz') )
			elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.cpio') ):
				archives.append( os.path.join(self.tmpUnpackDir, name + '.cpio') )
			
			if self.customName:
				if os.path.exists( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.tar.gz') ):
					archives.append( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.tar.gz') )
				elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.tar') ):
					archives.append( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.tar') )
				elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.cpio.gz') ):
					archives.append( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.cpio.gz') )
				elif os.path.exists( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.cpio') ):
					archives.append( os.path.join(self.tmpUnpackDir, name + '.' + self.customName + '.cpio') )
			
			if not archives:
				if (name == 'OPSI'):
					raise Exception("Bad package: OPSI.{cpio|tar}[.gz] not found.")
				else:
					logger.warning("No %s archive found." % name)
			
			dstDir = self.tmpUnpackDir
			if (name == 'SERVER_DATA'):
				dstDir = '/'
			elif (name == 'CLIENT_DATA'):
				dstDir = self.clientDataDir
			
			for archive in archives:
				try:
					if (name != 'OPSI'):
						for filename in Tools.getArchiveContent(archive):
							self.installedFiles.append( os.path.join(dstDir, filename) )
					Tools.extractArchive(archive, chdir=dstDir)
				except Exception, e:
					self.cleanup()
					raise Exception("Failed to extract '%s': %s" % (self.packageFile, e))
					
				os.unlink(archive)
			
			if (name == 'OPSI'):
				self.controlFile = os.path.join(self.tmpUnpackDir, 'control')
				self.readControlFile()
				
				if self.clientDataDir:
					# Copy control file into client data dir
					cfName = '%s_%s-%s' % (self.product.productId, self.product.productVersion, self.product.packageVersion)
					if self.customName:
						cfName = '%s_%s' % (cfName, self.customName)
					cfName = '%s.control' % cfName
					
					ci = open(self.controlFile, 'r')
					co = open(os.path.join(self.clientDataDir, cfName), 'w')
					co.write(ci.read())
					co.close()
					ci.close()
					self.installedFiles.append( os.path.join(self.clientDataDir, cfName) )
					
		if self.installedFiles:
			self.installedFiles.sort()
			for filename in self.installedFiles:
				logger.debug("Installed file: %s" % filename)
		
		
		
	def setAccessRights(self):
		
		logger.notice("Setting access rights of files")
		
		user = pwd.getpwuid(os.getuid())[0]
		
		for filename in self.installedFiles:
			
			(mode, group) = (None, None)
			
			if not filename.startswith(opsiConfig.getDepotDir()):
				continue
			
			group = DEFAULT_CLIENT_DATA_GROUP
			mode = DEFAULT_CLIENT_DATA_FILE_MODE
			if os.path.isdir(filename):
				mode = DEFAULT_CLIENT_DATA_DIR_MODE
			
			logger.info("Setting owner of '%s' to '%s:%s'" \
						% (filename, user, group))
			try:
				os.chown(filename, pwd.getpwnam(user)[2], grp.getgrnam(group)[2])
				
			except Exception, e:
				raise Exception("Failed to change owner of '%s' to '%s:%s': %s" \
						% (filename, user, group, e))
			
			logger.info("Setting access rights of '%s' to '%o'" \
						% (filename, mode))
			try:
				os.chmod(filename, mode)
			except Exception, e:
				raise Exception("Failed to set access rights of '%s' to '%o': %s" \
						% (filename, mode, e))
				
	
class ProductDependency:
	def __init__(self, productId, action, requiredProductId="", requiredProductClassId="", requiredAction="", requiredInstallationStatus="", requirementType=""):
		if not action in getPossibleProductActions():
			raise Exception("Action '%s' is not known" % action)
		if not requiredProductId and not requiredProductClassId:
			raise Exception("Either a required product or a required productClass must be set")
		elif requiredProductId and requiredProductClassId:
			raise Exception("Either a required product or a required productClass must be set, not both")
		if not requiredAction and not requiredInstallationStatus:
			raise Exception("Either a required action or a required installationStatus must be set")
		elif requiredAction and requiredInstallationStatus:
			raise Exception("Either a required action or a required installationStatus must be set, not both")
		if requiredAction and not requiredAction in getPossibleProductActions():
			raise Exception("Required action '%s' is not known" % requiredAction)
		if requiredInstallationStatus and not requiredInstallationStatus in getPossibleProductInstallationStatus():
			raise Exception("Required installationStatus '%s' is not known" % requiredInstallationStatus)
		if requirementType and requirementType not in getPossibleRequirementTypes():
			raise Exception("Requirement type '%s' is not known" % requirementType)
		
		self.productId = productId
		self.action = action
		self.requiredProductId = requiredProductId
		self.requiredProductClassId = requiredProductClassId
		self.requiredAction = requiredAction
		self.requiredInstallationStatus = requiredInstallationStatus
		self.requirementType = requirementType
		
class ProductProperty:
	def __init__(self, productId, name, description='', possibleValues=[], defaultValue='', value=''):
		if not productId:
			raise Exception("Product id is required")
		if not name:
			raise Exception("Name is required")
		if possibleValues and defaultValue and defaultValue not in possibleValues:
			raise Exception("Default value not in possible values")
		
		self.productId = productId
		self.name = name
		self.description = description
		self.possibleValues = possibleValues
		self.defaultValue = defaultValue
		self.value = value


