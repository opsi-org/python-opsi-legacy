# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2018 uib GmbH <info@uib.de>

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
Testing async backend usage.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

import time
import pytest

from OPSI.Backend._Async import AsyncBackendWrapper


class ClassicBackend:
    def some_method(self):
        return "Here we are."

    def arguments_required(self, arguments):
        return 'Got {}'.format(arguments)

    def _protected_func(self):
        raise RuntimeError("I am uncallable!")

    def backend_exit(self):
        print("Goodbye")


@pytest.mark.asyncio
async def testWrappingBackend():
    backend = AsyncBackendWrapper(ClassicBackend())
    result = await backend.some_method()
    assert "Here we are." == result


@pytest.mark.asyncio
async def testWrappingBackendAndPassingArguments():
    backend = AsyncBackendWrapper(ClassicBackend())
    result = await backend.arguments_required('something')
    assert "Got something" == result


@pytest.mark.asyncio
async def testNotPresentingProtectedFunctions():
    backend = AsyncBackendWrapper(ClassicBackend())
    with pytest.raises(AttributeError):
        await backend._protected_func()


async def testWorkingAsContextManager():
    with AsyncBackendWrapper(ClassicBackend()) as backend:
        assert "Here we are." == await backend.some_method()


async def testExitingBackend():
    """
    We want to support a proper backend exit.

    This is used by backends to be able to provide proper shutdowns.
    """
    with AsyncBackendWrapper(ClassicBackend()) as backend:
        await backend.backend_exit()


async def testExitingBackendWithoutMethod():
    class ShortBackend:
        def hey(self):
            return "Ohai"

    sbackend = ShortBackend()

    with AsyncBackendWrapper(sbackend) as backend:
        await backend.backend_exit()
