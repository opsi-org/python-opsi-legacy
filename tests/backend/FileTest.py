import os, pwd, grp

from OPSI.Backend.File import FileBackend
from OPSI.Backend.Backend import ExtendedConfigDataBackend
from OPSI.Object import *

from BackendTest import BackendTestCase
from BackendMixins.ObjectMethodsMixin import ObjectMethodsMixin
from BackendMixins.NonObjectMethodsMixin import NonObjectMethodsMixin
from BackendMixins.InventoryObjectMethodMixin import InventoryObjectMethodMixin

class FileTestCase(BackendTestCase,
		   ObjectMethodsMixin,
		   NonObjectMethodsMixin,
		   InventoryObjectMethodMixin
		   ):
		

	def createBackend(self):
		env = os.environ.copy()
		uid = gid = env["USER"]
		fileBackend = FileBackend(baseDir = u'/tmp/opsi-file-backend-test', hostKeyFile = u'/tmp/opsi-file-backend-test/pckeys')
		fileBackend.__fileUid = pwd.getpwnam(uid)[2]
		fileBackend.__fileGid = grp.getgrnam(gid)[2]
		fileBackend.__dirUid  = pwd.getpwnam(uid)[2]
		fileBackend.__dirGid  = grp.getgrnam(gid)[2]
		
		self.backend = ExtendedConfigDataBackend(fileBackend)