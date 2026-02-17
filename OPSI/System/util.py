# python-opsi is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2025 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

from __future__ import annotations

import struct
from uuid import UUID

from cryptography import x509
from opsicommon.logging import get_logger


def _get_secure_boot_certificates_from_efivar_payload(data: bytes) -> list[x509.Certificate]:
	logger = get_logger("opsi.general")
	certs = []
	offset = 0
	data_len = len(data)
	logger.debug("Parsing EFI variable payload of size %d bytes", data_len)
	while offset < data_len:
		# EFI_SIGNATURE_LIST header
		# typedef struct _EFI_SIGNATURE_LIST {
		#   GUID SignatureType
		#   UINT32 SignatureListSize
		#   UINT32 SignatureHeaderSize
		#   UINT32 SignatureSize
		# } EFI_SIGNATURE_LIST;
		if offset + 28 > data_len:
			logger.debug("Reached end of data while looking for EFI_SIGNATURE_LIST header")
			break

		sig_type_raw, list_size, header_size, sig_size = struct.unpack_from("<16sIII", data, offset)
		sig_type = UUID(bytes_le=sig_type_raw)
		if list_size < 28 or offset + list_size > data_len:
			logger.warning("Invalid EFI_SIGNATURE_LIST size %d at offset %d", list_size, offset)
			break
		if sig_size == 0:
			logger.warning("Invalid EFI_SIGNATURE_LIST signature size %d at offset %d", sig_size, offset)
			offset = offset + list_size
			continue

		list_end = offset + list_size
		if sig_type != UUID("a5c059a1-94e4-4aa7-87b5-ab155c2bf072"):
			logger.debug("Skipping unsupported EFI signature type %s at offset %d", sig_type, offset)
			offset = list_end
			continue

		offset = offset + 28 + header_size

		# Parse signature entries
		while offset + sig_size <= list_end:
			sig_data = data[offset : offset + sig_size]
			try:
				logger.debug("Parsing secure boot certificate at offset %d", offset)
				certs.append(x509.load_der_x509_certificate(sig_data[16:]))
			except Exception as err:
				logger.warning("Failed to parse secure boot certificate: %s", err)
			offset += sig_size

		# Safety: move to end of the list in case of padding
		offset = list_end

	logger.debug("Parsed %d secure boot certificates", len(certs))
	return certs
