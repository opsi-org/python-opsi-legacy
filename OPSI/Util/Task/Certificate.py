#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2013 uib GmbH <info@uib.de>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
opsi python library - Util - Task - Certificate

Functionality to work with certificates.
Certificates play an important role in the encrypted communication
between servers and clients.

.. versionadded:: 4.0.4

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import unicode_literals

import os
import shutil
from OpenSSL import crypto, rand
from tempfile import NamedTemporaryFile

from OPSI.Logger import Logger
from OPSI.System import which, execute
from OPSI.Types import forceHostId, forceInt
from OPSI.Util import getfqdn

OPSI_GLOBAL_CONF = '/etc/opsi/global.conf'
OPSICONFD_CERTFILE = '/etc/opsi/opsiconfd.pem'
DEFAULT_CERTIFICATE_PARAMETERS = {
	"country": "DE",
	"state": "RP",
	"locality": "Mainz",
	"organization": "uib gmbh",
	"organizationalUnit": "",
	"commonName": forceHostId(getfqdn(conf=OPSI_GLOBAL_CONF)),
	"emailAddress": "",
	"expires": 2,
}
LOGGER = Logger()


class NoCertificateError(Exception):
	pass


class CertificateCreationError(Exception):
	pass


class UnreadableCertificateError(Exception):
	pass


def renewCertificate(path=None, yearsUntilExpiration=2, config=None):
	"""
	Renews an existing certificate and creates a backup of the old file

	If an error occurs during the creation of the new certificate the backup
	will be restored.

	:param path: The path of the certificate.
	:type path: str
	:param yearsUntilExpiration: How many years will the certificate be valid? \
Will always overwrite an existing value in ``config``.
	:type yearsUntilExpiration: int
	:param config: Settings for the new certificate. If this is \
`None` the values for the configuration will be read from the \
existing certificate.
	:type config: dict
	"""
	if path is None:
		path = OPSICONFD_CERTFILE

	if not os.path.exists(path):
		raise NoCertificateError('No certificate found at {0}'.format(path))

	if config is None:
		config = loadConfigurationFromCertificate(path)
	config["expires"] = yearsUntilExpiration

	backupfile = ''.join((path, ".bak"))
	LOGGER.notice("Creating backup of existing certifcate to {0}".format(backupfile))
	shutil.copy(path, backupfile)

	try:
		createCertificate(path, config)
	except CertificateCreationError as error:
		LOGGER.warning('Problem during the creation of the certificate: {0}'.format(error))
		LOGGER.notice('Restoring backup.')
		shutil.move(backupfile, path)
		raise error


def createCertificate(path=None, config=None):
	"""
	Creates a certificate.

	Will overwrite any certificate that may exists in ``path``.

	:param path: The path of the certificate. \
If this is `None` the default will be used.
	:type path: str
	:param config: The configuration of the certificate. \
If not given will use a default.
	:type config: dict
	"""
	try:
		which("ucr")
		LOGGER.notice("Don't use certificate creation method on UCS-Systems")
		return
	except Exception:
		pass

	if path is None:
		path = OPSICONFD_CERTFILE

	if config is None:
		certparams = DEFAULT_CERTIFICATE_PARAMETERS
	else:
		certparams = config

	try:
		certparams["expires"] = forceInt(certparams["expires"])
	except Exception:
		raise CertificateCreationError(
			"No valid expiration date given. Must be an integer."
		)

	if certparams["commonName"] != forceHostId(getfqdn(conf=OPSI_GLOBAL_CONF)):
		raise CertificateCreationError(
			"commonName must be the FQDN of the local server"
		)

	LOGGER.notice("Creating new opsiconfd cert")
	LOGGER.notice("Generating new key pair")
	k = crypto.PKey()
	k.generate_key(crypto.TYPE_RSA, 2048)

	LOGGER.notice("Generating new self-signed cert")
	cert = crypto.X509()
	cert.get_subject().C = certparams['country']
	cert.get_subject().ST = certparams['state']
	cert.get_subject().L = certparams['locality']
	cert.get_subject().O = certparams['organization']
	cert.get_subject().CN = certparams['commonName']

	if 'organizationalUnit' in certparams:
		if certparams['organizationalUnit']:
			cert.get_subject().OU = certparams['organizationalUnit']
		else:
			del certparams['organizationalUnit']

	if 'emailAddress' in certparams:
		if certparams['emailAddress']:
			cert.get_subject().emailAddress = certparams['emailAddress']
		else:
			del certparams['emailAddress']

	LOGGER.notice("Generating new Serialnumber")
	#TODO: generating serial number
	#TODO: some info on the serial number:
	#      	https://tools.ietf.org/html/rfc2459#page-18
	cert.set_serial_number(1000)
	LOGGER.notice(
		"Setting new expiration date (%d years)" % certparams["expires"]
	)
	cert.gmtime_adj_notBefore(0)
	cert.gmtime_adj_notAfter(certparams["expires"] * 365 * 24 * 60 * 60)

	LOGGER.notice("Filling certificate with new data")
	cert.set_issuer(cert.get_subject())
	cert.set_pubkey(k)
	cert.set_version(2)

	LOGGER.notice("Signing Certificate")
	cert.sign(k, str('sha1'))

	certcontext = "".join(
		(
			crypto.dump_certificate(crypto.FILETYPE_PEM, cert),
			crypto.dump_privatekey(crypto.FILETYPE_PEM, k)
		)
	)

	LOGGER.notice("Beginning to write certificate.")
	with open(path, "wt") as certfile:
		certfile.write(certcontext)

	with NamedTemporaryFile(mode="wt") as randfile:
		LOGGER.notice(u"Generating and filling new randomize string")
		try:
			randomBytes = rand.bytes(512)
		except AttributeError as error:
			LOGGER.debug("Getting rand.bytes failed: {0}".format(error))
			LOGGER.debug("Using workaround with random.getrandbits")
			# SLES11SP3 ships a version so old that rand.bytes does not
			# even exist yet. As a workaround we use plain old random
			import random
			randomBytes = str(bytearray(random.getrandbits(8) for _ in range(512)))
		randfile.write(randomBytes)

		execute(
			"{command} gendh -rand {tempfile} 512 >> {target}".format(
				command=which("openssl"), tempfile=randfile.name, target=path
			)
		)

	LOGGER.notice('Certificate creation done.')


def loadConfigurationFromCertificate(path=None):
	"""
	Loads certificate configuration from a file.

	:param path: The path to the certificate. \
Uses `OPSICONFD_CERTFILE` if no path is given.
	:type path: str
	:return: The configuration as read from the certificate.
	:rtype: dict
	"""
	if path is None:
		path = OPSICONFD_CERTFILE

	if not os.path.exists(path):
		raise NoCertificateError('No certificate found at {path}.'.format(
				path=path
			)
		)

	certparams = {}
	with open(path) as data:
		try:
			cert = crypto.load_certificate(crypto.FILETYPE_PEM, data.read())
		except crypto.Error as error:
			raise UnreadableCertificateError(
				'Could not read from {path}: {error}'.format(
					path=path,
					error=error
				)
			)

		certparams["country"] = cert.get_subject().C
		certparams["state"] = cert.get_subject().ST
		certparams["locality"] = cert.get_subject().L
		certparams["organization"] = cert.get_subject().O
		certparams["organizationalUnit"] = cert.get_subject().OU
		certparams["commonName"] = cert.get_subject().CN
		certparams["emailAddress"] = cert.get_subject().emailAddress

	return certparams
