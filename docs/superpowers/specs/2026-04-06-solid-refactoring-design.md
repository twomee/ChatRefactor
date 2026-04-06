# SOLID Refactoring: Auth, Message, and Chat Services

**Date:** 2026-04-06
**Branch:** `refactor/solid-service-cleanup`
**Scope:** Pure refactoring — no new features, no API changes, no breaking changes.

## Problem

Three of four backend services have accumulated organizational debt:

1. **Auth service** (`auth_service.py`, 525 lines) mixes core auth flows (register, login, logout) with 275+ lines of 2FA/TOTP logic. Different change reasons in one file.
2. **Message service** (`routers/messages.py`, 509 lines) has business logic leaked into the router — filtering, enrichment, orchestration that belongs in a service layer. The actual `message_service.py` is only 30 lines. Additionally, the Kafka consumer has a **bug**: `edit_pm` and `delete_pm` events on the `chat.private` topic fall into the wrong `else` branch and are silently mishandled.
3. **Chat service** handler package has a god struct (`WSHandler` with 9 deps + 3 mutex maps), a 483-line lifecycle file mixing utilities with lifecycle logic, rate limiter embedded in the message handler, ambiguous file boundaries (`room.go` contains admin ops), and a fully redundant 365-line test file in `tests/`.

File service is well-organized and excluded from this refactoring.

## Design

### Auth Service

**Goal:** Split `auth_service.py` by responsibility.

**New files:**
- `app/utils/totp.py` — Pure TOTP helpers: `generate_totp_secret()`, `verify_totp()`, `get_totp_uri()`, `check_and_mark_totp_replay()`. These are stateless crypto functions with no business logic. Moved from `auth_service.py` lines 298-343.
- `app/services/two_factor_service.py` — 2FA business flows: `setup_2fa()`, `verify_2fa_setup()`, `disable_2fa()`, `verify_login_2fa()`, `get_2fa_status()`, plus the temp token helpers (`_store_2fa_temp_token`, `_peek_2fa_temp_token`, `_consume_2fa_temp_token`). Moved from `auth_service.py` lines 238-525.

**Modified files:**
- `app/services/auth_service.py` — Retains only: `register()`, `login()`, `logout()`, `ping()`, `update_password()`, `update_email()`. The `login()` function still checks `user.is_2fa_enabled` and returns the temp_token dict, but delegates to `two_factor_service._store_2fa_temp_token()` for token creation.
- `app/routers/auth.py` — Update imports: 2FA endpoints now call `two_factor_service.*` instead of `auth_service.*`.

**Result:** `auth_service.py` goes from 525 → ~200 lines. 2FA logic is isolated and independently testable.

### Message Service

**Goal:** Move business logic from router to service layer. Fix consumer bug.

**New files:**
- `app/services/search_service.py` — `search_messages(db, user_id, query, room_id, limit)` — wraps DAL search call + applies per-user clear filters (both single-room and cross-room).
- `app/services/clear_service.py` — `clear_history()`, `delete_pm_conversation()`, `get_deleted_conversations()`, `apply_clear_filter()`, `apply_pm_deletion_filter()` — consolidates the scattered filtering logic.

**Modified files:**
- `app/services/message_service.py` — Expand from 30 → ~120 lines: add `get_pm_history()` (auth client call + DAL + clear filter + deletion filter + reaction enrichment), `get_message_context()`, `get_pm_context()`, `enrich_with_reactions()`.
- `app/routers/messages.py` — Slim from 509 → ~180 lines: each endpoint becomes 5-10 lines of request parsing + delegation to service + response formatting.
- `app/consumers/persistence_consumer.py` — **Bug fix**: Add explicit handlers for `edit_pm` and `delete_pm` event types in the `TOPIC_PRIVATE` branch. Currently these fall into the `else` → `_persist_private_message()` which silently fails. The fix reuses the existing `_handle_edit_message()` and `_handle_delete_message()` methods (they work on `message_id` + `sender_id`, which PM events also carry).

**Result:** Router is thin delegation. Service layer is testable. PM edits/deletes are properly persisted via Kafka.

### Chat Service

**Goal:** Reduce WSHandler god struct, improve file organization, delete redundant tests.

**New files:**
- `internal/handler/lifecycle_state.go` — Extract the 3 mutex-guarded maps and their methods into a focused struct:
  ```go
  type lifecycleState struct {
      kickedMu    sync.Mutex
      kickedUsers map[string]bool
      leftMu      sync.Mutex
      leftUsers   map[string]bool
      pendingLeaveMu sync.Mutex
      pendingLeaves  map[string]context.CancelFunc
  }
  ```
  Methods: `markKicked()`, `wasKicked()`, `markLeft()`, `wasLeft()`, `storePendingLeave()`, `cancelPendingLeave()`, `flushPendingLeaves()`. WSHandler embeds this struct.

- `internal/handler/ws_helpers.go` — Extract utility methods from `ws_lifecycle.go` that are shared across WS handlers: `getAdminUsernames()`, `getMutedUsernames()`, `produceEvent()`, `sendHistory()`, `sendReadPosition()`, `sendEmptyHistory()`, `transformHistoryMessages()`.

- `internal/handler/ratelimiter.go` — Extract the `rateLimiter` struct and `newRateLimiter()` from `ws_message.go`. Currently 60 lines embedded at the top of the message handler file.

- `internal/handler/room_admin.go` — Extract per-room admin operations from `room.go`: `AddAdmin()`, `RemoveAdmin()`, `MuteUser()`, `UnmuteUser()`, `isCallerRoomOrGlobalAdmin()`. `room.go` retains: `ListRooms()`, `CreateRoom()`, `GetRoomUsers()`, `SetActive()`, `broadcastRoomListUpdated()`.

**Deleted files:**
- `tests/handler_test.go` — All 15 tests are covered by more focused tests in `internal/handler/`, `internal/middleware/`, and `internal/ws/`.

**Modified files:**
- `internal/handler/websocket.go` — WSHandler struct embeds `lifecycleState` instead of inlining the 3 mutex maps. Remove `markKicked()`, `wasKicked()` methods (moved to lifecycle_state.go).
- `internal/handler/ws_lifecycle.go` — Remove utility methods (moved to ws_helpers.go). Remove `wasLeft()` (moved to lifecycle_state.go). File goes from 483 → ~220 lines (join, leave, disconnect, broadcastLeave, handleAdminSuccession, scheduleGracePeriodLeave).
- `internal/handler/ws_message.go` — Remove rateLimiter struct (moved to ratelimiter.go). File goes from 210 → ~150 lines.
- `internal/handler/room.go` — Remove admin operations (moved to room_admin.go). File goes from 335 → ~170 lines.

**Result:** WSHandler has fewer direct fields. Each file has one clear purpose. Stale tests deleted.

## What This Does NOT Change

- No API endpoint changes (all Kong routes unchanged)
- No Kafka message format changes
- No database schema changes
- No new dependencies
- No file-service changes
- No frontend changes
- No E2E test changes (backend E2E, UI E2E, load tests all hit Kong/browser, not internal modules)

## Verification

1. `cd services/auth-service && python -m pytest tests/ -v`
2. `cd services/message-service && python -m pytest tests/ -v`
3. `cd services/chat-service && go test ./... -v`
4. `cd services/file-service && npm test`
5. Verify no import errors: each service starts cleanly
