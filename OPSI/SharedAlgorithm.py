# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Algorithms to get a product order for an installation.

.. versionchanged:: 4.0.6.1

.. versionchanged:: 4.0.7.1

	Refactored algorithm 1.
"""

from collections import defaultdict
from typing import Any, Optional

from opsicommon.logging import get_logger

from OPSI.Exceptions import BackendUnaccomplishableError, OpsiProductOrderingError
from OPSI.Object import Product, ProductDependency, ProductOnClient
from OPSI.Types import forceBool, forceInt

BOTTOM = -100

logger = get_logger("opsi.general")


class CircularProductDependencyError(BackendUnaccomplishableError):
	ExceptionShortDescription = "A circular dependency between products."


def addActionRequest(  # pylint: disable=too-many-branches,too-many-statements
	productOnClientByProductId: dict[str, ProductOnClient],
	productId: str,
	productDependenciesByProductId: dict[str, ProductDependency],
	availableProductsByProductId: dict[str, Product],
	addedInfo: Optional[dict[str, Any]] = None,
) -> None:
	logger.debug(
		"Checking dependencies for product %s, action %s",
		productId,
		productOnClientByProductId[productId].actionRequest,
	)
	addedInfo = addedInfo or {}

	poc = productOnClientByProductId[productId]
	if poc.actionRequest == "none" or not productDependenciesByProductId.get(productId):
		return

	for dependency in productDependenciesByProductId[productId]:
		if dependency.productAction != poc.actionRequest:
			continue

		logger.debug(
			"   need to check dependency to product %s", dependency.requiredProductId
		)
		if dependency.requiredAction:
			logger.debug(
				"   product %s requires action %s of product %s %s-%s on action %s",
				productId,
				dependency.requiredAction,
				dependency.requiredProductId,
				dependency.requiredProductVersion,
				dependency.requiredPackageVersion,
				dependency.productAction,
			)
		elif dependency.requiredInstallationStatus:
			logger.debug(
				"   product %s requires status %s of product %s %s-%s on action %s",
				productId,
				dependency.requiredInstallationStatus,
				dependency.requiredProductId,
				dependency.requiredProductVersion,
				dependency.requiredPackageVersion,
				dependency.productAction,
			)

		requiredAction = dependency.requiredAction
		installationStatus = "not_installed"
		actionRequest = "none"
		if dependency.requiredProductId in productOnClientByProductId:
			installationStatus = productOnClientByProductId[
				dependency.requiredProductId
			].installationStatus
			actionRequest = productOnClientByProductId[
				dependency.requiredProductId
			].actionRequest
		logger.debug("addActionRequest: requiredAction %s", requiredAction)
		if not requiredAction:
			if dependency.requiredInstallationStatus == installationStatus:
				logger.debug(
					"   required installation status %s is fulfilled",
					dependency.requiredInstallationStatus,
				)
				continue

			if dependency.requiredInstallationStatus == "installed":
				requiredAction = "setup"
			elif dependency.requiredInstallationStatus == "not_installed":
				requiredAction = "uninstall"

		# An action is required => check if possible
		logger.debug(
			"   need to set action %s for product %s to fulfill dependency",
			requiredAction,
			dependency.requiredProductId,
		)

		setActionRequestToNone = False
		if dependency.requiredProductId not in availableProductsByProductId:
			logger.warning(
				"   product %s defines dependency to product %s, which is not avaliable on depot",
				productId,
				dependency.requiredProductId,
			)
			setActionRequestToNone = True
		elif (
			dependency.requiredProductVersion is not None
			and dependency.requiredProductVersion
			!= availableProductsByProductId[dependency.requiredProductId].productVersion
		):
			logger.warning(
				"   product %s defines dependency to product %s, but product version %s is not available",
				productId,
				dependency.requiredProductId,
				dependency.requiredProductVersion,
			)
			setActionRequestToNone = True
		elif (
			dependency.requiredPackageVersion is not None
			and dependency.requiredPackageVersion
			!= availableProductsByProductId[dependency.requiredProductId].packageVersion
		):
			logger.warning(
				"   product %s defines dependency to product %s, but package version %s is not available",
				productId,
				dependency.requiredProductId,
				dependency.requiredProductId,
			)
			setActionRequestToNone = True

		if setActionRequestToNone:
			logger.notice(
				"   => setting action request for product %s to 'none'!", productId
			)
			productOnClientByProductId[productId].actionRequest = "none"
			continue

		if actionRequest == requiredAction:
			logger.debug("   => required action %s is already set", requiredAction)
			continue

		if actionRequest not in (None, "none"):
			logger.debug(
				"   => cannot fulfill dependency of product %s to product %s: action %s needed but action %s already set",
				productId,
				dependency.requiredProductId,
				requiredAction,
				actionRequest,
			)
			continue

		if dependency.requiredProductId in addedInfo:
			logger.warning(
				"   => Product dependency loop including product %s detected, skipping",
				productId,
			)
			logger.debug(
				"Circular dependency at %s. Processed product: %s addedInfo: %s",
				dependency.requiredProductId,
				productId,
				addedInfo,
			)
			continue

		logger.info(
			"   => adding action %s for product %s",
			requiredAction,
			dependency.requiredProductId,
		)

		if dependency.requiredProductId not in productOnClientByProductId:
			productOnClientByProductId[dependency.requiredProductId] = ProductOnClient(
				productId=dependency.requiredProductId,
				productType=availableProductsByProductId[
					dependency.requiredProductId
				].getType(),
				clientId=poc.clientId,
				installationStatus=None,
				actionRequest="none",
			)

		addedInfo[dependency.requiredProductId] = {
			"addedForProduct": productId,
			"requiredAction": requiredAction,
			"requirementType": dependency.requirementType,
		}
		productOnClientByProductId[dependency.requiredProductId].setActionRequest(
			requiredAction
		)

		addActionRequest(
			productOnClientByProductId,
			dependency.requiredProductId,
			productDependenciesByProductId,
			availableProductsByProductId,
			addedInfo,
		)


def addDependentProductOnClients(
	productOnClients: list[ProductOnClient],
	availableProducts: list[Product],
	productDependencies: list[ProductDependency],
) -> list[ProductOnClient]:
	availableProductsByProductId = {}
	for availableProduct in availableProducts:
		availableProductsByProductId[availableProduct.id] = availableProduct

	productDependenciesByProductId = defaultdict(list)
	for productDependency in productDependencies:
		productDependenciesByProductId[productDependency.productId].append(
			productDependency
		)

	pocsByClientIdAndProductId = defaultdict(dict)
	for productOnClient in productOnClients:
		pocsByClientIdAndProductId[productOnClient.clientId][
			productOnClient.productId
		] = productOnClient

	dependendProductOnClients = []
	for clientId, productOnClientByProductId in pocsByClientIdAndProductId.items():
		logger.debug("Adding dependent productOnClients for client %s", clientId)

		addedInfo = {}
		for productId in tuple(productOnClientByProductId.keys()):
			addActionRequest(
				productOnClientByProductId,
				productId,
				productDependenciesByProductId,
				availableProductsByProductId,
				addedInfo,
			)
		dependendProductOnClients.extend(list(productOnClientByProductId.values()))

	return dependendProductOnClients


class XClassifiedProduct:
	"""
	has String member id, int members priority, revisedPriority, and a member that is intendend to be a reference to a Product
	"""

	def __init__(self, product: Product) -> None:
		self.id = product.id  # pylint: disable=invalid-name
		self.priority = product.priority  # handle this variable as final
		self.revisedPriority = product.priority  # start value which may be modified
		self.product = (
			product  # keep pointer to the original standard product structure
		)

	def __str__(self) -> str:
		return f"<{self.__class__.__name__}(productId={self.id}, priority={self.priority}, revisedPriority={self.revisedPriority})>"

	def __repr__(self) -> str:
		return self.__str__()


class OrderRequirement:
	"""
	Represents a request for ordering of two elements with a notice
	if it is fulfilled.
	"""

	def __init__(self, prior: int, posterior: int, fulfilled: bool = False) -> None:
		self.prior = forceInt(prior)
		self.posterior = forceInt(posterior)
		self.fulfilled = forceBool(fulfilled)

	def __str__(self) -> str:
		return f"<OrderRequirement(prior={self.prior!r}, posterior={self.posterior!r}, fulfilled={self.fulfilled!r}>"

	def __repr__(self) -> str:
		return self.__str__()


class Requirements:
	"""Comprises a list with ordering requirements and ordered lists of them"""

	def __init__(self) -> None:
		self.list = []
		self.orderByPrior = []
		self.orderByPosterior = []

	def add(self, requirement: OrderRequirement) -> None:
		assert isinstance(requirement, OrderRequirement), "not an OrderRequirement"
		self.list.append(requirement)
		# Extend the other lists by dummy valuesnoInListOrderedByPriors
		self.orderByPrior.append(-1)
		self.orderByPosterior.append(-1)
		logger.trace("Length of list: %s", len(self.list))
		logger.trace("Length of orderByPrior: %s", len(self.orderByPrior))

		# Continue building the transform map of list indices
		# such that the transformed list is ordered by its prior values
		# therefore:
		#  Determine first the place of the added item
		#  in the ordered sequence i -> list[orderByPrior[i]]
		#  then fix orderByPrior such that it gets this place
		i = 0
		located = False
		while (i < len(self.list) - 1) and not located:
			logger.trace(
				"Requirement.prior: %s, self.list[self.orderByPrior[i]].prior: %s",
				requirement.prior,
				self.list[self.orderByPrior[i]].prior,
			)
			if requirement.prior > self.list[self.orderByPrior[i]].prior:
				i += 1
			else:
				located = True
				# we take the first place that fits to the ordering
				# shift all items by one place
				j = len(self.list) - 1
				while j > i:
					self.orderByPrior[j] = self.orderByPrior[j - 1]
					j -= 1
				# finally we map place i to the new element
				self.orderByPrior[i] = len(self.list) - 1

		if not located:
			# noInListOrderedByPriors
			# if i = len(self.list) - 1 nothing is moved
			self.orderByPrior[i] = len(self.list) - 1

		logger.trace("Set orderByPrior[%s] = %s", i, (len(self.list) - 1))

		# The analogous procedure to get a transformation
		# i -> orderByPosterior[i] such that the sequence
		# i ->  self.list[orderByPosterior[i]]
		# is ordered by the posterior values

		i = 0
		located = False
		while (i < len(self.list) - 1) and not located:
			logger.trace(
				"Requirement.posterior %s, self.list[self.orderByPosterior[i]].posterior) %s",
				requirement.posterior,
				self.list[self.orderByPosterior[i]].posterior,
			)
			if requirement.posterior > self.list[self.orderByPosterior[i]].posterior:
				i += 1
			else:
				located = True
				# We take the first place that fits to the ordering
				# shift all items by one place
				j = len(self.list) - 1
				while j > i:
					self.orderByPosterior[j] = self.orderByPosterior[j - 1]
					j -= 1
				# Finally we map place i to the new element
				self.orderByPosterior[i] = len(self.list) - 1

		if not located:
			# If i = len(self.list) - 1 nothing is moved
			self.orderByPosterior[i] = len(self.list) - 1

	def posteriorIndexOf(self, posti: int) -> int:
		"""Searches first occurrence of posti as posterior value in the posterior-ordered sequence of requirements"""

		j = 0
		searching = True
		candidate = None
		while (j < len(self.list)) and searching:
			candidate = self.list[self.orderByPosterior[j]]
			if candidate.fulfilled or (candidate.posterior < posti):
				j += 1
			else:
				searching = False

		if searching:
			# All candidates were less than the comparevalue or were not to be regarded any more
			return -1

		# Candidate is not fulfilled and has posterior value >= posti
		if candidate and candidate.posterior == posti:
			return j

		# There are no more possible occurrences of posterior
		return -1

	def indexOfFirstNotFulfilledRequirementOrderedByPrior(self) -> int:
		i = 0
		found = False
		while not found and (i < len(self.list)):
			if self.list[self.orderByPrior[i]].fulfilled:
				i += 1
			else:
				found = True

		if found:
			return i

		return -1

	def firstPriorNotOccurringAsPosterior(self, startI: int) -> tuple[Any, int]:
		j = startI
		found = False
		candidate = self.list[self.orderByPrior[startI]].prior
		lastcandidate = -1
		candidatesCausingProblemes = []

		while (j < len(self.list)) and not found:
			if (
				not self.list[self.orderByPrior[j]].fulfilled
				and self.posteriorIndexOf(candidate) == -1
			):
				# If requ j still not fulfilled and candidate does not occur
				# as posterior among the not fulfilled
				# then we adopt candidate (i.e. the prior element of requ j in requ list ordered by priors)
				# as next element in our ordered sequence
				found = True
			else:
				if (self.posteriorIndexOf(candidate) > -1) and (
					lastcandidate != candidate
				):
					candidatesCausingProblemes.append(candidate)
					lastcandidate = candidate

				# Go on searching
				j += 1
				if j < len(self.list):
					candidate = self.list[self.orderByPrior[j]].prior

		if found:
			noInListOrderedByPriors = j
			return (candidate, noInListOrderedByPriors)

		errorMessage = (
			f"Potentially conflicting requirements for: {candidatesCausingProblemes}"
		)
		logger.error(errorMessage)
		raise OpsiProductOrderingError(errorMessage, candidatesCausingProblemes)

	def getCount(self) -> int:
		return len(self.list)

	def getRequlist(self) -> list[OrderRequirement]:
		return self.list

	def getOrderByPrior(self) -> list[OrderRequirement]:
		return self.orderByPrior

	def getOrderByPosteriors(self) -> list[OrderRequirement]:
		return self.orderByPosterior


class OrderBuild:  # pylint: disable=too-many-instance-attributes
	"""Describes the building of an ordering"""

	def __init__(
		self, elementCount: int, requs: Requirements, completing: bool
	) -> None:
		self.ordering = []
		self.elementCount = elementCount
		self.completing = completing
		self.errorFound = False
		self.allFulfilled = False

		assert isinstance(requs, Requirements), "Expected instance of Requirements"

		self.requs = requs
		self.indexIsAmongPosteriors = []
		j = 0
		while j < elementCount:
			self.indexIsAmongPosteriors.append(False)
			j += 1

		self.indexUsed = []
		j = 0
		while j < elementCount:
			self.indexUsed.append(False)
			j += 1

		self.usedCount = 0
		logger.trace("OrderBuild initialized")

	def proceed(self) -> bool:  # pylint: disable=too-many-branches
		result = True
		lastSortedCount = 0

		if self.usedCount >= self.elementCount:
			return result

		indexRequToFulfill = (
			self.requs.indexOfFirstNotFulfilledRequirementOrderedByPrior()
		)
		if indexRequToFulfill == -1:
			self.allFulfilled = True
			# Get the posteriors that did not occur as priors
			j = 0
			while j < self.elementCount:
				if self.indexIsAmongPosteriors[j] and not self.indexUsed[j]:
					self.ordering.append(j)
					self.indexUsed[j] = True
					self.usedCount = self.usedCount + 1
				j += 1
			lastSortedCount = self.usedCount

			if self.completing:
				# Take rest from list
				j = 0
				while j < self.elementCount:
					if not self.indexUsed[j]:
						self.ordering.append(j)
						self.indexUsed[j] = True
						self.usedCount = self.usedCount + 1
					j += 1

				# Move the sorted items to the end of the list
				if lastSortedCount > 0:
					newordering = []
					k = 0
					while k < self.elementCount:
						newordering.append(k)
						k += 1

					# Rearrange not sorted elements
					for k in range(self.elementCount - lastSortedCount):
						newordering[k] = self.ordering[lastSortedCount + k]

					# Sorted elements
					for k in range(lastSortedCount):
						newordering[self.elementCount - lastSortedCount + k] = (
							self.ordering[k]
						)

					# Put back
					self.ordering = newordering
		else:
			# At indexRequToFulfill we found a not fulfilled requirement,
			# lets try to fulfill a requirement
			# look only at not fulfilled reqirements
			# Find the first one, in ordering by priors, with the
			# property that it does not occur as posterior
			# take it as newEntry for the ordered list
			# Automatically any requirement is fulfilled where newEntry
			# is the prior; do the markings

			(newEntry, requNoInListOrderedByPriors) = (
				self.requs.firstPriorNotOccurringAsPosterior(indexRequToFulfill)
			)

			if newEntry == -1:
				result = False
			else:
				self.ordering.append(newEntry)
				self.usedCount = self.usedCount + 1
				# Mark all requirements with candidate in prior position
				# as fulfilled and collect the posteriors
				k = requNoInListOrderedByPriors
				orderByPrior = self.requs.getOrderByPrior()
				requK = self.requs.getRequlist()[orderByPrior[k]]
				while (k < self.requs.getCount()) and (newEntry == requK.prior):
					requK.fulfilled = True
					self.indexIsAmongPosteriors[requK.posterior] = True
					k += 1
					if k < self.requs.getCount():
						requK = self.requs.getRequlist()[orderByPrior[k]]
				self.indexUsed[newEntry] = True

			logger.debug("proceed newEntry %s", newEntry)

		logger.debug("proceed result %s", result)
		return result

	def getOrdering(self) -> list[Any]:
		return self.ordering


def generateProductOnClientSequence(
	productOnClients: list[ProductOnClient], sortedList: list[str]
) -> list[ProductOnClient]:
	pocsByClientIdAndProductId = defaultdict(dict)
	for productOnClient in productOnClients:
		pocsByClientIdAndProductId[productOnClient.clientId][
			productOnClient.productId
		] = productOnClient

	productOnClients = []
	for productOnClientsByProductId in pocsByClientIdAndProductId.values():
		sequence = 0
		for productId in sortedList:
			if productId in productOnClientsByProductId:
				productOnClientsByProductId[productId].actionSequence = sequence
				productOnClients.append(productOnClientsByProductId[productId])
				del productOnClientsByProductId[productId]
				sequence += 1

		if sortedList:
			logger.debug("handle remaining if existing  ")
			for productId in productOnClientsByProductId.keys():
				productOnClientsByProductId[productId].actionSequence = sequence
				productOnClients.append(productOnClientsByProductId[productId])
				sequence += 1

	return productOnClients


def generateProductOnClientSequenceX(
	productOnClients: list[ProductOnClient], sortedList: list[str]
) -> list[ProductOnClient]:
	fProductId2ProductOnClients = {}
	for productOnClient in productOnClients:
		if productOnClient.productId not in fProductId2ProductOnClients:
			fProductId2ProductOnClients[productOnClient.productId] = []
		fProductId2ProductOnClients[productOnClient.productId].append(productOnClient)
		# the list should contain exactly one element, if applied to a list "productOnClients" from one depot

	result = []

	givenIds = list(fProductId2ProductOnClients.keys())

	if sortedList:
		for productId in sortedList:
			for prod in fProductId2ProductOnClients[productId].values():
				result.append(prod)
			givenIds.remove(productId)

	# add remainings ids
	for productId in givenIds:
		for prod in fProductId2ProductOnClients[productId].values():
			result.append(prod)

	return result


def getSetupRequirements(
	productDependencies: list[ProductDependency],
) -> list[tuple[str, str]]:
	# Requirements are list of pairs (install_prior, install_posterior)
	# We treat only setup requirements
	setupRequirements = []

	for dependency in productDependencies:
		if dependency.productAction != "setup":
			continue
		if (
			dependency.requiredInstallationStatus != "installed"
			and dependency.requiredAction != "setup"
		):
			continue
		if dependency.requirementType == "before":
			setupRequirements.append(
				(dependency.requiredProductId, dependency.productId)
			)
		elif dependency.requirementType == "after":
			setupRequirements.append(
				(dependency.productId, dependency.requiredProductId)
			)

	return setupRequirements


def generateProductSequence_algorithm1(
	availableProducts: list[Product], productDependencies: list[ProductDependency]
) -> list[Product]:
	logger.info("Generating product sequence by algorithm 1.")
	setupRequirements = getSetupRequirements(productDependencies)

	return generateProductSequenceFromRequPairs_algorithm1(
		availableProducts, setupRequirements
	)


def modifySortingClassesForAlgorithm1(
	products: list[Product], setupRequirements: list[Any]
) -> bool:  # pylint: disable=too-many-branches
	# idea:
	# we reconstruct the priority chain
	# by pushing the products upwards into it when required by a dependency

	recursionNecessary = False

	fId2Prod = {}
	for prod in products:
		fId2Prod[prod.id] = prod
		logger.debug("prod %s", prod)

	fLevel2Prodlist = {}
	# state of priorityClasses
	for level in reversed(range(BOTTOM, 101)):
		fLevel2Prodlist[level] = []

	for prod in products:
		fLevel2Prodlist[prod.revisedPriority].append(prod)

	requsByPosterior = {}
	for requ in setupRequirements:
		if requ[1] not in requsByPosterior:
			requsByPosterior[requ[1]] = []

		requsByPosterior[requ[1]].append(requ)

	for level in range(BOTTOM, 101):  # pylint: disable=too-many-nested-blocks
		logger.trace("we are about to correct level %s...", level)
		if not fLevel2Prodlist[level]:
			logger.trace("no elements in this level")
			continue

		for posti in fLevel2Prodlist[level]:
			logger.trace("posti %s", posti)
			if posti.id in requsByPosterior:
				removeRequs = []
				for requ in requsByPosterior[posti.id]:
					if requ[0] not in fId2Prod:
						logger.debug(
							"product %s should be arranged before product %s but is not available",
							requ[0],
							requ[1],
						)
						removeRequs.append(requ)
					else:
						if fId2Prod[requ[0]].revisedPriority < level:
							logger.debug(
								"product %s must be pushed upwards from level %s to level %s, the level of %s, to meet the requirement first %s, later %s",
								requ[0],
								fId2Prod[requ[0]].revisedPriority,
								level,
								posti.id,
								requ[0],
								requ[1],
							)
							fId2Prod[requ[0]].revisedPriority = level
							recursionNecessary = True

				for requ in removeRequs:
					requsByPosterior[posti.id].remove(requ)

	return recursionNecessary


def generateProductSequenceFromRequPairs_algorithm1(
	availableProducts: list[Product], setupRequirements: list[Any]
) -> list[Product]:
	logger.debug("availableProducts %s", availableProducts)

	xProducts = []
	for product in availableProducts:
		xProducts.append(XClassifiedProduct(product))

	requsByPosterior = {}
	for requ in setupRequirements:
		if requ[1] not in requsByPosterior:
			requsByPosterior[requ[1]] = []

		requsByPosterior[requ[1]].append(requ)

	# recursively modify the priority levels
	# we move prods upwards as long as there are movements necessary
	# the algorithm halts since the moves are only upwards and are bounded
	ready = False
	while not ready:
		ready = not modifySortingClassesForAlgorithm1(xProducts, setupRequirements)
		if ready:
			logger.debug("recursion finished")
		else:
			logger.debug("was modified, step to next recursion")

	# we map xProduct onto Product
	for product in xProducts:
		product.priority = product.revisedPriority

	return generateProductSequenceFromRequPairs_algorithm2(xProducts, setupRequirements)


def generateProductSequenceFromRequPairs_algorithm2(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
	availableProducts: list[Product], setupRequirements: list[Any]
) -> list[Product]:
	"""Build priority classes and indices"""
	logger.debug("availableProducts %s", availableProducts)

	productIds = []
	priorityClasses = defaultdict(list)
	productIndexInClass = {}
	productById = {}
	for product in availableProducts:
		productIds.append(product.id)
		productById[product.id] = product
		prio = str(0)
		if product.priority:
			prio = str(product.priority)

		priorityClasses[prio].append(product.id)
		productIndexInClass[product.id] = len(priorityClasses[prio]) - 1

	logger.debug("productIndexInClass %s", productIndexInClass)
	logger.debug("priorityClasses %s", priorityClasses)

	requirementsByClasses = defaultdict(list)

	for prod1, prod2 in setupRequirements:
		logger.debug("First product: %s", prod1)
		if prod1 not in productById:
			logger.debug("Product %s is requested but not available", prod1)
			continue

		logger.debug("Second product: %s", prod2)
		if prod2 not in productById:
			logger.debug("Product %s is requested but not available", prod2)
			continue

		prio1 = productById[prod1].priority or 0
		prio2 = productById[prod2].priority or 0

		logger.debug("Priority %s: %s", prod1, prio1)
		logger.debug("Priority %s: %s", prod2, prio2)
		if prio1 > prio2:
			logger.debug("The ordering is guaranteed by priority handling")
		elif prio1 < prio2:
			logger.warning(
				"Dependency declaration between %s and %s contradicts priority declaration, will be ignored",
				prod1,
				prod2,
			)
		else:
			prioclasskey = str(prio1)
			requirementsByClasses[prioclasskey].append(
				[productIndexInClass[prod1], productIndexInClass[prod2]]
			)

	foundClasses = []
	orderingsByClasses = {}
	sortedList = []
	order_build = None
	try:
		for priority in reversed(range(BOTTOM, 101)):
			prioclasskey = str(priority)
			if prioclasskey not in priorityClasses:
				continue
			foundClasses.append(prioclasskey)
			prioclass = priorityClasses[prioclasskey]

			if prioclasskey in requirementsByClasses:
				requs = requirementsByClasses[prioclasskey]
				requObjects = Requirements()
				for item in requs:
					requObjects.add(OrderRequirement(item[0], item[1], False))

				order_build = OrderBuild(len(prioclass), requObjects, True)
				try:
					for _ in prioclass:
						order_build.proceed()
				except OpsiProductOrderingError as err:
					logger.warning(
						"Product sort algorithm 2 caught OpsiProductOrderingError: %s",
						err,
					)
					for i, prio in enumerate(prioclass):
						logger.info(" product %s %s", i, prio)

					raise OpsiProductOrderingError(
						"Potentially conflicting requirements for: "
						f"{', '.join([prioclass[index] for index in err.problematicRequirements])}"
					) from err

				orderingsByClasses[prioclasskey] = order_build.getOrdering()
				logger.debug(
					"prioclasskey, ordering %s, %s",
					prioclasskey,
					order_build.getOrdering(),
				)

		for prioclasskey in foundClasses:
			prioclass = priorityClasses[prioclasskey]
			logger.debug("prioclasskey has prioclass %s, %s", prioclasskey, prioclass)
			if prioclasskey in orderingsByClasses:
				ordering = orderingsByClasses[prioclasskey]

				logger.debug(
					"prioclasskey in found classes, ordering %s, %s",
					prioclasskey,
					order_build.getOrdering(),
				)

				for idx in ordering:
					sortedList.append(prioclass[idx])
			else:
				for element in prioclass:
					sortedList.append(element)

		logger.debug("sortedList algo2 %s", sortedList)
	except OpsiProductOrderingError as error:
		logger.error("algo2 outer caught OpsiProductOrderingError: %s", error)
		raise error

	return sortedList


def generateProductOnClientSequence_algorithm1(
	productOnClients: list[ProductOnClient],
	availableProducts: list[Product],
	productDependencies: list[ProductDependency],
) -> list[ProductOnClient]:
	logger.info("Generating productOnClient sequence with algorithm 1.")

	setupRequirements = getSetupRequirements(productDependencies)
	sortedProductList = generateProductSequenceFromRequPairs_algorithm1(
		availableProducts, setupRequirements
	)

	productOnClients = generateProductOnClientSequence(
		productOnClients, sortedProductList
	)
	return productOnClients
