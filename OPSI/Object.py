# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
General classes used in the library.

As an example this contains classes for hosts, products, configurations.

Deprecated, use opsicommon.objects instead.
"""

from typing import Any

from opsicommon.objects import *  # noqa: F403

mandatoryConstructorArgs = mandatory_constructor_args
getIdentAttributes = get_ident_attributes
getForeignIdAttributes = get_foreign_id_attributes
getBackendMethodPrefix = get_backend_method_prefix
getPossibleClassAttributes = get_possible_class_attributes
decodeIdent = decode_ident


def objectsDiffer(obj1: Any, obj2: Any, excludeAttributes: list[str] = None) -> bool:
	return objects_differ(obj1, obj2, exclude_attributes=excludeAttributes)
