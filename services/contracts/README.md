# Kafka Event Contracts

JSON Schema definitions for all Kafka events exchanged between microservices.

These schemas are the **single source of truth** for inter-service communication. Each service validates events against these schemas — if a producer changes a schema, consuming service tests should break.

## Events

| Schema | Topic | Producer | Consumer |
|--------|-------|----------|----------|
| [chat.message](events/chat.message.schema.json) | `chat.messages` | Chat & Room (Go) | Message Service (Python) |
| [chat.private](events/chat.private.schema.json) | `chat.private` | Chat & Room (Go) | Message Service (Python) |
| [chat.event](events/chat.event.schema.json) | `chat.events` | Chat & Room (Go) | — (future) |
| [chat.dlq](events/chat.dlq.schema.json) | `chat.dlq` | Message Service (Python) | — (monitoring) |
| [file.uploaded](events/file.uploaded.schema.json) | `file.events` | File Service (Node.js) | Chat & Room (Go) |
| [auth.event](events/auth.event.schema.json) | `auth.events` | Auth Service (Python) | — (future) |

## Rules

1. **Never break consumers** — add new optional fields, never remove or rename existing ones
2. **Version via new schema files** if breaking changes are needed (e.g., `chat.message.v2.schema.json`)
3. **All services validate** incoming events against these schemas in their test suites
