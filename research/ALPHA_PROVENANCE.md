# Attribution and scope of native-cloud research

Carrier SmartHome v1.2.42 APK, uploaded by device owner, supplied the GraphQL operation names, entry-level model fields and candidate production URLs. The separately maintained MIT-licensed `dahlb/carrier_api` source independently confirmed the legacy/entry-level assistedLogin request and `getEntryLevelSystems` read query, along with a refresh-token request and `updateEntryLevelZone` structure. Our alpha uses independently authored Python asyncio/aiohttp code to exercise these observed endpoints. We did not vendor their Python package or claim affiliation with Carrier or its authors.

Source: https://github.com/dahlb/carrier_api, MIT license.

Public API implementation is unofficial, subject to change and **not yet validated against this owner's exact TSTATCCEWF-01**. This alpha does **not** expose Matter, depend on Matter, modify firmware, intercept certificates, or redirect DNS. Proprietary LAN API support remains unverified.

Never commit account credentials, session tokens, full MAC/serial numbers, pairing codes, or raw Omada exports.
