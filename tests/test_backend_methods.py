# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing unbound methods for the backends.
"""

from OPSI.Backend.Base.Extended import get_function_signature_and_args


def test_getting_signature_for_method_without_arguments():
	def foo():
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "()"
	assert not args


def test_getting_signature_for_method_with_one_positional_argument():
	def foo(bar):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar)"
	assert args == "bar=bar"


def test_getting_signature_for_method_with_multiple_positional_arguments():
	def foo(bar, baz):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar, baz)"
	assert args == "bar=bar, baz=baz"


def test_getting_signature_for_method_with_keyword_argument_only():
	def foo(bar=None):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert "(bar=None)" == sig
	assert "bar=bar" == args


def test_getting_signature_for_method_with_multiple_keyword_arguments_only():
	def foo(bar=None, baz=None):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar=None, baz=None)"
	assert args == "bar=bar, baz=baz"


def test_getting_signature_for_method_with_mixed_arguments():
	def foo(bar, baz=None):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar, baz=None)"
	assert args == "bar=bar, baz=baz"


def test_self_as_first_argument_is_ignored():
	def foo(self, bar=None):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar=None)"
	assert args == "bar=bar"


def test_argument_with_string_default():
	def foo(bar="baz"):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar='baz')"
	assert args == "bar=bar"


def test_argument_with_variable_argument_count():
	def foo(*bar):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(*bar)"
	assert args == "*bar"


def test_argument_with_positional_argument_and_variable_argument_count():
	def foo(bar, *baz):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(bar, *baz)"
	assert args == "bar=bar, *baz"


def test_variable_keyword_arguments():
	def foo(**bar):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(**bar)"
	assert args == "**bar"


def test_method_with_all_types_of_arguments():
	def foo(ironman, blackWidow=True, *hulk, **deadpool):
		pass

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(ironman, blackWidow=True, *hulk, **deadpool)"
	assert args == "ironman=ironman, blackWidow=blackWidow, *hulk, **deadpool"


def test_method_with_all_types_of_arguments_and_annotations():
	def foo(self, ironman, blackWidow: bool = True, *hulk, **deadpool) -> int:
		return 1

	sig, args = get_function_signature_and_args(foo)

	assert sig == "(ironman, blackWidow: bool = True, *hulk, **deadpool) -> int"
	assert args == "ironman=ironman, blackWidow=blackWidow, *hulk, **deadpool"
