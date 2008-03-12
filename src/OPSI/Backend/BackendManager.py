# -*- coding: utf-8 -*-
"""
   ==============================================
   =        OPSI BackendManager Module          =
   ==============================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.9.4.0'

# Imports
import os, stat, types, re, socket, new

# OS dependend imports
if os.name == 'posix':
	import pwd, grp
else:
	import win32security
	from _winreg import *

# OPSI imports
from OPSI.Product import *
from OPSI.Backend.Backend import *
from OPSI.Logger import *
from OPSI.Tools import *

# Get logger instance
logger = Logger()

HOST_GROUP = '|HOST_GROUP|'

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                  CLASS BACKENDMANAGER                                              =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class BackendManager(DataBackend):
	
	def __init__(self, username = '', password = '', address = 'localhost', 
		     configFile = None, backend = None, authRequired=True):
		
		self._pamService = 'common-auth'
		self._sshRSAPublicKeyFile = '/etc/ssh/ssh_host_rsa_key.pub'
		
		if os.name == 'nt':
			try:
				regroot = ConnectRegistry(None,HKEY_LOCAL_MACHINE)
				regpath = "SOFTWARE\\opsi.org\\opsiconfd"
				reg = OpenKey(regroot,regpath)
				windefaultdir = QueryValueEx(reg,"BaseDir")[0]
			except:
				windefaultdir = 'C:\\Programme\\opsi.org\\opsiconfd'
			configFile = windefaultdir+'\\backendManager.conf'
		
		if not configFile:
			configFile = '/etc/opsi/backendManager.d'
			if not os.path.isdir(configFile):
				configFile = '/etc/opsi/backendManager.conf'
		
		''' 
		The constructor of the class BackendManager creates an instance of the
		class and initializes the backends to use. It will also read the values
		from the config file (default: /etc/opsi/backendManager.conf).
		'''
		
		self.__authRequired = authRequired
		
		if self.__authRequired:
			if not username:
				raise BackendAuthenticationError("No username specified")
			if not password:
				raise BackendAuthenticationError("No password specified")
			
		self.__username = username
		self.__password = password
		self.__address = address
		
		# Default values
		self.defaultDomain = 'localdomain'

		try:
			self.defaultDomain = '.'.join(socket.getfqdn().split('.')[1:])
			logger.info("OS reports '%s' as default domain" % self.defaultDomain)
		except Exception, e:
			logger.error("Cannot get domain: %s" % e)
		
		
		self.__configFile = configFile
		self.__userGroups = []
		self.backends = {}
		
		# If a special backend is passed to the constructor, this backend
		# will be used for all function groups no matter what the config file says
		self.forcedBackend = backend
		
		# Now read the config file to overwrite the defaults
		self._readConfigFile()
		if os.name == 'nt':
			self.__readConfigFromReg()
		
		logger.info("Using default domain '%s'" % self.defaultDomain)
		
		self._initializeBackends()
		
		self._defaultDomain = self.defaultDomain
		
		if not self.__authRequired:
			# Authenticate by remote server
			self.__userGroups = []
			logger.debug("Authorization disabled...")
			
		elif re.search('^\S+\.\S+\.\S+$', self.__username):
			# Username starts with something like xxx.yyy.zzz: 
			# Assuming it is a client passing his FQDN  as username
			logger.debug("Trying to authenticate by opsiHostKey...")
			
			hostKey = self.getOpsiHostKey(self.__username)
			
			logger.confidential("Client '%s', key sent '%s', key stored '%s'" \
					% (self.__username, self.__password, hostKey))
			
			if (self.__password != hostKey):
				raise BackendAuthenticationError("opsiHostKey authentication failed for host '%s': wrong key" \
									% self.__username)
			
			self.__userGroups = [ HOST_GROUP ]
			logger.info("opsiHostKey authentication successful for host '%s'" % self.__username)
		else:
			# System user trying to log in with username and password
			logger.debug("Trying to authenticate by Operating System...")
			self._authenticate(self.__username, self.__password)
			# Authentication did not throw exception => authentication successful
			logger.info("Operating System authentication successful for user '%s', groups '%s'" \
								% (self.__username, ','.join(self.__userGroups)))
	
	
	'''- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	-                                    Private Methods                                                 -
	- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -'''

	def _initializeBackends(self):
		''' This function will initialize the needed backends and asign them
		    to the function groups according to the configuration '''
		
		backendsUsed = []
		for (key, value) in self.backends.items():
			if self.forcedBackend:
				if (self.forcedBackend != key):
					continue
			
			elif not value.get('load', False):
				continue
			
			if not re.search('^[\w\d]+$', key):
				logger.error('Bad backend name: %s' % key)
				continue
			
			if not self.backends[key].get('config'):
				self.backends[key]['config'] = {}
			if not self.backends[key]['config'].get('defaultdomain'):
				self.backends[key]['config']['defaultdomain'] = self.defaultDomain
			
			logger.info("Backend config for '%s': %s" % (key, self.backends[key]['config']) )
			
			exec('from %s import %sBackend' % (key, key))
			exec('b = %sBackend(	address 	= "%s", \
						username 	= "%s", \
						password 	= "%s", \
						args 		= %s, \
						backendManager	= self )' \
				% (	key,
					self.__address,
					self.__username,
					self.__password,
					self.backends[key]['config'] ) )
			
			self.backends[key]['instance'] = b
			backendsUsed.append(key)
			logger.info("Using backend %s." % b.__class__)
			
			if self.forcedBackend:
				for (n, t) in b.__class__.__dict__.items():
					if ( (type(t) == types.FunctionType or type(t) == types.MethodType ) and not n.startswith('_') ):
						argCount = t.func_code.co_argcount
						args = list(t.func_code.co_varnames[1:argCount])
						argDefaults = t.func_defaults
						argsWithDefaults = list(args)
						if ( argDefaults != None and len(argDefaults) > 0 ):
							offset = argCount - len(argDefaults) - 1
							for i in range( len(argDefaults) ):
								if type(argDefaults[i]) is str:
									argsWithDefaults[offset+i] = "%s='%s'" % (args[offset+i], argDefaults[i])
								else:
									argsWithDefaults[offset+i] = "%s=%s" % (args[offset+i], argDefaults[i])
						
						logger.debug("Overwriting instance method '%s'" % n)
						argString = ''
						if (len(args) > 0):
							argString = ', ' + ', '.join(args)
						logger.debug2('def %s(self, %s): self._execMethod(self.defaultBackend, "%s"%s)' % (n, ', '.join(argsWithDefaults), n, argString))
						exec('def %s(self, %s): return self._execMethod(self.defaultBackend, "%s"%s)' % (n, ', '.join(argsWithDefaults), n, argString))
						setattr( self.__class__, n, new.instancemethod(eval(n), None, self.__class__) )
			
		if ( len(backendsUsed) == 1 and backendsUsed[0] == 'JSONRPC' ):
			logger.warning('No authentication required!')
			# json-rpc backend is asigned to all methods
			# authentication is done by json-rpc service
			self.__authRequired = False
		
		
		
	def _authenticate(self, user, password):
		''' Authenticate a user by the underlying operating system.
		    Throws BackendAuthenticationError on failure. '''
		if (os.name == 'posix'):
			# Posix os => authenticate by PAM
			return self._pamAuthenticate(user, password)
		elif (os.name == 'nt'):
			# NT os => authenticate by windows-login
			return self._winAuthenticate(user,password)
		else:
			# Other os, not implemented yet 
			raise NotImplementedError("Sorry, operating system '%s' not supported yet!" % os.name)
		
	def _winAuthenticate(self, user, password):
		'''
		Authenticate a user by Windows-Login on current machine
		'''
		
		#Import win32 security modules
		import win32security, win32net
		
		win32security.LogonUser(user,'None',password,win32security.LOGON32_LOGON_NETWORK,win32security.LOGON32_PROVIDER_DEFAULT)
		
		'''Group-member check'''
		server = '127.0.0.1'
		groupName = SYSTEM_ADMIN_GROUP
		level = 1
		resumeHandle = 0
		prefLen = 4096
		'''list members of group 'groupName' '''
		groups = win32net.NetLocalGroupGetMembers(server, groupName , level , resumeHandle , prefLen )
		'''search in list of members for 'user' '''
		i = 0
		while i < len(groups[0]):
			if groups[0][i]['name'] == user:
				self.__userGroups.append(groupName)
				logger.debug("User '%s' is member of group '%s'" % (user, groupName))
			i = i + 1
		
	def _pamAuthenticate(self, user, password):
		''' 
		Authenticate a user by PAM (Pluggable Authentication Modules).
		Important: the uid running this code needs access to /etc/shadow 
		if os uses traditional Unix authentication mechanisms.
		'''
		logger.confidential("Trying to authenticate user '%s' with password '%s' by PAM" % (user, password))
		
		# Import PAM modules
		import PAM
		
		class AuthConv:
			''' Handle PAM conversation '''
			def __init__(_, password):
				_.password = password
			
			def __call__(_, auth, queryList, userData):
				''' Callback conversation function '''
				response = []
				for query, qt in queryList:
					if (qt == PAM.PAM_PROMPT_ECHO_ON or qt == PAM.PAM_PROMPT_ECHO_OFF):
						response.append((_.password, 0))
					elif qt == PAM.PAM_PROMPT_ERROR_MSG or type == PAM.PAM_PROMPT_TEXT_INFO:
						response.append(('', 0))
					else:
						return None
				return response
		try:
			# Create instance
			auth = PAM.pam()
			auth.start(self._pamService)
			# Authenticate
			auth.set_item(PAM.PAM_USER, user)
			auth.set_item(PAM.PAM_CONV, AuthConv(password))
			# Set the tty
			# Workaround for:
			#   If running as daemon without a tty the following error
			#   occurs with older versions of pam:
			#      pam_access: couldn't get the tty name
			auth.set_item(PAM.PAM_TTY, '/dev/null')
			auth.authenticate()
			auth.acct_mgmt()
			
			self.__userGroups = [ grp.getgrgid( pwd.getpwnam(user)[3] )[0] ]
			logger.debug("Primary group of user '%s' is '%s'" % (user, self.__userGroups[0]))
			groups = grp.getgrall()
			for group in groups:
				if user in group[3]:
					self.__userGroups.append(group[0])
					logger.debug("User '%s' is member of group '%s'" % (user, group[0]))
		
		except Exception, e:
			# Something failed => raise authentication error
			raise BackendAuthenticationError("PAM authentication failed for user '%s': %s" % (user, e))
		
		
	def _readConfigFile(self):
		''' Get settings from config file '''
		try:
			# Read Config-File
			confFiles = [ self.__configFile ]
			if os.path.isdir(self.__configFile):
				confFiles = []
				files = os.listdir(self.__configFile)
				files.sort()
				for f in files:
					if f.endswith('.conf'):
						confFiles.append( os.path.join(self.__configFile, f) )
			
			try:
				for confFile in confFiles:
					logger.info("Reading config file '%s'" % confFile)
					st = os.stat(confFile)
					mode = st[stat.ST_MODE] & 0777
					if (mode & 0007 != 0):
						logger.critical("Check file permissions of '%s'." % confFile + 
								 " File permissions are: '%s', should not be world readable!" %
								 oct(mode) )
					
					
					execfile(confFile)
			except Exception, e:
				raise Exception("error reading file '%s': %s" % (confFile, e))
			
			for (key, val) in locals().items():
				if ( type(val) == types.FunctionType ):
					logger.debug("Adding instancemethod: '%s'" % key )
					setattr( self.__class__, key, new.instancemethod(val, None, self.__class__) )
		except Exception, e:
			raise Exception("Failed to read config from '%s': %s" % (self.__configFile, e))
	
	def __readConfigFromReg(self):
		''' Getting setting from Windows Registry '''
		try:
			regroot = ConnectRegistry(None,HKEY_LOCAL_MACHINE)
			regpath = "SOFTWARE\\opsi.org\\opsiconfd"
			reg = OpenKey(regroot,regpath)
			# Read Reg-Values
			self.backends[BACKEND_FILE]['config']['pclogDir'] = QueryValueEx(reg,"pclogDir")[0]
			self.backends[BACKEND_FILE]['config']['pcpatchDir'] = QueryValueEx(reg,"pcpatchDir")[0]
			self.backends[BACKEND_FILE]['config']['depotDir'] = QueryValueEx(reg,"depotDir")[0]
			self.backends[BACKEND_FILE]['config']['productsFile'] = QueryValueEx(reg,"productsFile")[0]
			self.backends[BACKEND_FILE]['config']['groupsFile'] = QueryValueEx(reg,"groupsFile")[0]
			self.backends[BACKEND_FILE]['config']['licensesFile'] = QueryValueEx(reg,"licensesFile")[0]
			self.backends[BACKEND_FILE]['config']['pckeyFile'] = QueryValueEx(reg,"pckeyFile")[0]
			self.backends[BACKEND_FILE]['config']['opsiTFTPDir'] = QueryValueEx(reg,"opsiTFTPDir")[0]
		except Exception, e:
			logger.warning("Failed to read Registry: %s" % e)
		
	def _verifyGroupMembership(self, *groups):
		if not self.__authRequired: 
			return
		
		temp = []
		for group in groups:
			if group:
				temp.append(group)
		groups = temp
		
		allow = False
		for group in groups:
			if group in self.__userGroups:
				allow = True
				break
		if not allow:
			raise BackendPermissionDeniedError("Access denied: Group membership '%s' required!" % ' or '.join(groups))
	
	def _verifyUser(self, *userIds):
		if not self.__authRequired: 
			return
		
		temp = []
		for userId in userIds:
			if userId:
				temp.append(userId)
		userIds = temp
		
		allow = False
		for userId in userIds:
			if (userId == self.__username):
				allow = True
				break
		logger.debug("Username '%s' currently stored, '%s' required." % (self.__username, ' or '.join(userIds)))
		if not allow:
			raise BackendPermissionDeniedError("Access denied: Connection as user '%s' required, logged in as '%s'!" % (' or '.join(userIds), self.__username ) )
	
	def _execMethod(self, backend=None, method=None, *params):
		if self.forcedBackend:
			backend = self.forcedBackend
		
		if not backend:
			raise BackendBadValueError('neither backend given nor backend forced!')
		
		if not method:
			raise BackendBadValueError('No methodname given!')
		
		params = str(params)
		if params.endswith(',)'):
			params = params[:-2] + ')'
		
		if (type(backend) != list):
			backend = [ backend ]
		
		result = None
		for be in backend:
			b = self.backends.get(be)
			if not b:
				raise Exception("Backend '%s' not defined!" % be)
			instance = self.backends[be].get('instance')
			if not instance:
				raise Exception("Backend '%s' not loaded!" % be)
			
			logger.debug("backend '%s' => executing: b.%s%s" % (instance.__class__, method, params))
			res = eval( "instance.%s%s" % (method, params) )
			if (result == None):
				result = res
			
			elif ( type(res) == list ) and ( type(result) == list ):
				result.extend(res)
			
			elif ( type(res) == dict ) and ( type(result) == dict ):
				for (key, value) in res.items():
					result[key] = value
			
			elif (( type(res) == str ) or ( type(res) == unicode )) and (( type(result) == str ) or ( type(result) == unicode )):
				if res:
					result += "\n" + res
			
			elif (res != None):
				result = res
		return result
	
	'''- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	-                                    Public Methods                                                  -
	- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -'''
	def exit(self):
		for (name, backend) in self.backends.items():
			instance = backend.get('instance')
			if instance:
				logger.debug("%s: exit()" % name)
				instance.exit()
	
	def getHostRSAPublicKey(self):
		
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP, HOST_GROUP)
		
		f = open(self._sshRSAPublicKeyFile, 'r')
		data = f.read()
		f.close()
		return data
	
	def getPcpatchRSAPrivateKey(self):
		
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP, HOST_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		sshDir = os.path.join(pwd.getpwnam("pcpatch")[5], '.ssh')
		pcpatchUid = pwd.getpwnam("pcpatch")[2]
		pcpatchGid = grp.getgrnam("pcpatch")[2]
		idRsa = os.path.join(sshDir, 'id_rsa')
		idRsaPub = os.path.join(sshDir, 'id_rsa.pub')
		authorizedKeys = os.path.join(sshDir, 'authorized_keys')
		if not os.path.exists(sshDir):
			mkdir(sshDir, 0750)
			os.chown(sshDir, pcpatchUid, pcpatchGid)
		if not os.path.exists(idRsa):
			logger.notice("Creating RSA private key for user pcpatch in '%s'" % idRsa)
			execute("%s -N '' -t rsa -f %s" % ( which('ssh-keygen'), idRsa))
			os.chmod(idRsa, 0640)
			os.chown(idRsa, pcpatchUid, pcpatchGid)
			os.chmod(idRsaPub, 0644)
			os.chown(idRsaPub, pcpatchUid, pcpatchGid)
		if not os.path.exists(authorizedKeys):
			f = open(idRsaPub, 'r')
			f2 = open(authorizedKeys, 'w')
			f2.write(f.read())
			f2.close()
			f.close()
			os.chmod(authorizedKeys, 0600)
			os.chown(authorizedKeys, pcpatchUid, pcpatchGid)
		f = open(idRsa, 'r')
		data = f.read()
		f.close()
		return data
	
	def getBackendInfos_listOfHashes(self):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		infos = []
		for (name, backend) in self.backends.items():
			config = backend.get('config')
			if config:
				for key in config.keys():
					if (key.lower() == "bindpw"):
						config[key] = '*******'
			info = { 
				'name':		name,
				'config':	config,
				'version':	'not available',
				'module':	'not loaded' }
			
			instance = backend.get('instance')
			if instance:
				info['module'] = instance.__module__
				exec( "import %s" % instance.__module__ )
				info['version'] = eval("%s.__version__" % instance.__module__)
			
			infos.append(info)
		
		return infos
	
	def authenticated(self):
		''' Checks if a user has been successfuly authenticated.
		    Raises an exception if not. '''
		return True
	
	def userIsAdmin(self):
		if SYSTEM_ADMIN_GROUP in self.__userGroups:
			return True
		return False
	
	def userIsHost(self):
		if HOST_GROUP in self.__userGroups:
			return True
		return False
	
	def getPossibleMethods_listOfHashes(self):
		''' This function returns a list of available interface methods.
		The methods are defined by hashes containing the keys "name" and
		"params", which is a list of parameter names used for a method.
		Parameters starting with an asterisk (*) are optional '''
		methodList = []
		methods = {}
		for (n, t) in Backend.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in DataBackend.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in self.__class__.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in methods.items():
				argCount = t.func_code.co_argcount
				argNames = list(t.func_code.co_varnames[1:argCount])
				argDefaults = t.func_defaults
				if ( argDefaults != None and len(argDefaults) > 0 ):
					offset = argCount - len(argDefaults) - 1
					for i in range( len(argDefaults) ):
						argNames[offset+i] = '*' + argNames[offset+i]		
				methodList.append( { 'name': n, 'params': argNames} )
		
		# Sort the function list by name
		methodList.sort()
		return methodList
	

	
