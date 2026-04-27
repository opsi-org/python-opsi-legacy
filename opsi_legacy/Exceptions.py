# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
OPSI Exceptions.
Deprecated, use opsi.exception instead.
"""

from opsi.exception import (  # noqa: F401
	BackendAuthenticationError,
	BackendBadValueError,
	BackendConfigurationError,
	BackendError,
	BackendIOError,
	BackendMissingDataError,
	BackendModuleDisabledError,
	BackendPermissionDeniedError,
	BackendReferentialIntegrityError,
	BackendTemporaryError,
	BackendUnableToConnectError,
	BackendUnaccomplishableError,
	OperatingSystemUnsupportedError,
	OpsiBadRpcError,
	OpsiError,
	OpsiLicenseConfigurationError,
	OpsiLicenseMissingError,
	OpsiRepositoryError,
	OpsiRpcError,
	OpsiServiceAuthenticationError,
	OpsiServiceClientCertificateError,
	OpsiServiceConnectionError,
	OpsiServiceConnectionRefusedError,
	OpsiServiceError,
	OpsiServicePermissionError,
	OpsiServiceTimeoutError,
	OpsiServiceUnavailableError,
	OpsiServiceVerificationError,
)


class CommandNotFoundException(RuntimeError):
	pass


class RepositoryError(OpsiError):
	pass


class OpsiBackupFileError(OpsiError):
	ExceptionShortDescription = "Opsi backup file error"


class OpsiBackupFileNotFound(OpsiBackupFileError):
	ExceptionShortDescription = "Opsi backup file not found"


class OpsiBackupBackendNotFound(OpsiBackupFileError):
	ExceptionShortDescription = "Opsi backend not found in backup"


class OpsiProductOrderingError(OpsiError):
	ExceptionShortDescription = "A condition for ordering cannot be fulfilled"

	def __init__(self, message: str = "", problematicRequirements: list[int] | list[str] | None = None) -> None:
		super().__init__(message)
		self.problematicRequirements: list[int] | list[str] | list = problematicRequirements or []

	def __str__(self) -> str:
		if self.message:
			if self.problematicRequirements:
				return f"{self.ExceptionShortDescription}: {self.message} ({self.problematicRequirements})"
			return f"{self.ExceptionShortDescription}: {self.message}"
		return self.ExceptionShortDescription

	def __repr__(self) -> str:
		if self.message:
			if self.problematicRequirements:
				return f'<{self.__class__.__name__}("{self.message}", {self.problematicRequirements})>'
			return f'<{self.__class__.__name__}("{self.message}")>'
		return f"<{self.__class__.__name__}>"


class LicenseConfigurationError(OpsiError):
	"""Exception raised if a configuration error occurs in the license data base."""

	ExceptionShortDescription = "License configuration error"


class LicenseMissingError(OpsiError):
	"""Exception raised if a license is requested but cannot be found."""

	ExceptionShortDescription = "License missing error"


class CanceledException(Exception):
	ExceptionShortDescription = "CanceledException"
