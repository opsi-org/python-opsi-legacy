# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Applications for the use of opsi in an twisted-application context.
"""

from typing import Any

from opsicommon.logging import get_logger

logger = get_logger("opsi.general")


class AppRunner:  # pylint: disable=too-few-public-methods
	def __init__(self, app: Any, config: dict[str, Any]) -> None:
		self._app = app
		self._config = config

	def run(self) -> None:
		self._app.run()


class _BaseProfiler(AppRunner):  # pylint: disable=too-few-public-methods
	def _getProfiler(self) -> Any:
		raise NotImplementedError("Subclass must implement this.")

	def run(self) -> None:
		try:
			import pstats  # pylint: disable=import-outside-toplevel

			profiler = self._getProfiler()
			profiler.runcall(self._app.run)

			out = self._config.get("profile")

			with open(out, mode="w", encoding="utf-8") as outputfile:
				statistics = pstats.Stats(profiler, stream=outputfile)
				statistics.strip_dirs()
				statistics.sort_stats(-1)
				statistics.print_stats()

		except ImportError as error:
			logger.error(
				"Failed to load profiler %s. Make sure the profiler module is installed on your system. (%s)",
				self._config.get("profiler"),
				error,
			)
			raise error


class ProfileRunner(_BaseProfiler):  # pylint: disable=too-few-public-methods
	def _getProfiler(self) -> Any:
		import profile  # pylint: disable=import-outside-toplevel

		return profile.Profile()


class CProfileRunner(_BaseProfiler):  # pylint: disable=too-few-public-methods
	def _getProfiler(self) -> Any:
		import cProfile  # pylint: disable=import-outside-toplevel

		return cProfile.Profile()


class Application:  # pylint: disable=too-few-public-methods
	profiler = {"profiler": ProfileRunner, "cprofiler": CProfileRunner}

	def __init__(self, config: dict[str, Any]) -> None:
		self._config = config
		self._app = self._getApplication()
		self._runner = self._getRunner()

	def _getApplication(self):
		raise NotImplementedError("Subclass must implement this function.")

	def _getRunner(self) -> AppRunner:
		if self._config.get("profile", False):
			profiler = self._config.get("profiler", "profiler").lower()
			if profiler in self.profiler:
				return self.profiler[profiler](self._app, self._config)

			raise NotImplementedError(f"Profiler {profiler} is not supported.")

		return AppRunner(self._app, self._config)

	def setup(self) -> None:
		pass

	def shutdown(self) -> None:
		pass

	def run(self) -> None:
		try:
			self.setup()
			return self._runner.run()
		finally:
			self.shutdown()
