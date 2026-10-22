# Carrier SmartHome 1.2.42 — GraphQL inventory

Source: user-supplied XAPK, offline Hermes string-table extraction. These are **document definitions**, not authenticated API results.

- 140 recovered GraphQL definitions
- 137 standalone document strings
- 3 partial/unreliable fragments (not safe to invoke)

## Inventory by domain

| Family | Queries | Mutations | Fragments |
|---|---:|---:|---:|
| authentication | 1 | 12 | 0 |
| entry_level | 6 | 10 | 0 |
| infinity | 9 | 7 | 0 |
| other | 22 | 15 | 3 |
| shared_devices_accounts | 20 | 33 | 2 |

## Relevant entry-level operations

| Operation | Type | Variables from APK |
|---|---|---|
| `createEntryLevelSchedule` | mutation | `input: CreateEntryLevelScheduleInput!` |
| `createEntryLevelScheduleBatch` | mutation | `input: CreateEntryLevelScheduleBatchInput!` |
| `removeEntryLevelSchedule` | mutation | `input: RemoveEntryLevelScheduleInput!` |
| `resetEntryLevelPushNotificationReminders` | mutation | `input: ResetEntryLevelPushNotificationRemindersInput!` |
| `updateEntryLevelComfortProfile` | mutation | `input: EntryLevelComfortProfileInput!` |
| `updateEntryLevelDealerPreferences` | mutation | `input: EntryLevelDealerPreferencesInput!` |
| `updateEntryLevelPushNotificationPrefs` | mutation | `input: UpdateEntryLevelPushNotificationPrefsInput!` |
| `updateEntryLevelSchedule` | mutation | `input: UpdateEntryLevelScheduleInput!` |
| `updateEntryLevelSystem` | mutation | `input: EntryLevelSystemInput!` |
| `updateEntryLevelZone` | mutation | `input: EntryLevelZoneInput!` |
| `getEntryLevelNotificationPrefs` | query | `serial: String!` |
| `getEntryLevelReminders` | query | `serial: String!` |
| `getEntryLevelSchedules` | query | `serial: String!` |
| `getEntryLevelSystemData` | query | `serial: String!` |
| `getEtBleSessionKey` | query | `input: EntryLevelSessionInput` |
| `runtimeUsageEntryLevel` | query | `input: GetRuntimeUsageInput!` |

## Limitations

- GraphQL input object names are available; their complete field schemas may not be. Never invent required arguments.
- The presence of an operation in a universal Carrier app does not show it works for TSTATCCEWF-01.
- LocalControl/MQTT strings are separate evidence; they do not establish any specific device protocol.
- The exact Carrier SmartHome GraphQL hostname and login flow remain unconfirmed until verified.
