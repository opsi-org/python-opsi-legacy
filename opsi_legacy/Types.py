# python-opsi-legacy is part of the desktop management solution opsi http://www.opsi.org
# Copyright (c) 2008-2026 uib GmbH <info@uib.de>
# This code is owned by the uib GmbH, Mainz, Germany (uib.de). All rights reserved.
# License: AGPL-3.0-only

"""
Type forcing features.

This module contains various methods to ensure force a special type
on an object.
Deprecated, use opsi.opsi.service.model.type instead.
"""

from opsi.opsi.service.model.type import *  # noqa: F403

forceActionProgress = to_action_progress
forceActionRequest = to_action_request
forceActionRequestList = to_action_request_list
forceActionResult = to_action_result
forceArchitecture = to_architecture
forceArchitectureList = to_architecture_list
forceAuditState = to_audit_state
forceBool = to_bool
forceBoolList = to_bool_list
forceConfigId = to_config_id
forceDict = to_dict
forceDictList = to_dict_list
forceDomain = to_domain
forceEmailAddress = to_email_address
forceFilename = to_filename
forceFloat = to_float
forceFqdn = to_fqdn
forceGroupId = to_group_id
forceGroupIdList = to_group_id_list
forceGroupType = to_group_type
forceGroupTypeList = to_group_type_list
forceHardwareAddress = to_hardware_address
forceHardwareDeviceId = to_hardware_device_id
forceHardwareVendorId = to_hardware_vendor_id
forceHostAddress = to_host_address
forceHostId = to_host_id
forceHostIdList = to_host_id_list
forceHostname = to_hostname
forceInstallationStatus = to_installation_status
forceInt = to_int
forceIntList = to_int_list
forceIpAddress = to_ip_address
forceIPAddress = to_ip_address
forceLanguageCode = to_language_code
forceLanguageCodeList = to_language_code_list
forceLicenseContractId = to_license_contract_id
forceLicenseContractIdList = to_license_contract_id_list
forceLicensePoolId = to_license_pool_id
forceLicensePoolIdList = to_license_pool_id_list
forceList = to_list
forceNetmask = to_netmask
forceNetworkAddress = to_network_address
forceObjectClass = to_object_class
forceObjectClassList = to_object_class_list
forceObjectId = to_object_id
forceObjectIdList = to_object_id_list
forceOct = to_oct
forceOpsiHostKey = to_opsi_host_key
forceOpsiTimestamp = to_opsi_timestamp
forcePackageCustomName = to_package_custom_name
forcePackageVersion = to_package_version
forcePackageVersionList = to_package_version_list
forceProductId = to_product_id
forceProductIdList = to_product_id_list
forceProductPriority = to_product_priority
forceProductPropertyId = to_product_property_id
forceProductPropertyType = to_product_property_type
forceProductTargetConfiguration = to_product_target_configuration
forceProductType = to_product_type
forceProductVersion = to_product_version
forceProductVersionList = to_product_version_list
forceRequirementType = to_requirement_type
forceSoftwareLicenseId = to_software_license_id
forceSoftwareLicenseIdList = to_software_license_id_list
forceString = to_string
forceStringList = to_string_list
forceStringLower = to_string_lower
forceStringUpper = to_string_upper
forceTime = to_time
forceUnicode = to_string
forceUnicodeList = to_string_list
forceUnicodeLower = to_string_lower
forceUnicodeLowerList = to_string_list_lower
forceUniqueList = to_unique_list
forceUnsignedInt = to_unsigned_int
forceUrl = to_url
forceUsername = to_username
forceUUID = to_uuid
forceUUIDString = to_uuid_string
