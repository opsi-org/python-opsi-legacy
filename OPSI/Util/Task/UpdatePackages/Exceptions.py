# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Exceptions used in updating packages.
"""

from OPSI.Exceptions import OpsiError

__all__ = (
	"ConfigurationError",
	"MissingConfigurationValueError",
	"RequiringBackendError",
)


class ConfigurationError(ValueError):
	pass


class MissingConfigurationValueError(ConfigurationError):
	pass


class NoActiveRepositoryError(ConfigurationError):
	pass


class RequiringBackendError(OpsiError):
	pass
