# UI/UX Improvements Design Spec

**Date:** 2026-03-30
**Branch:** `feat/ui-ux-improvements` (from `feat/phase1-integration`)

## Overview

10 improvements to bring the cHATBOX UX to production quality: redesigned search, PM feature parity, settings page, email registration, and room name cleanup.

## Design Decisions

| # | Feature | Decision | Rationale |
|---|---------|----------|-----------|
| 1 | Search redesign | Command palette (Slack/VS Code style) | Centered floating panel with keyboard nav. Evolve existing SearchModal — preserves debounce, abort, highlight logic. |
| 2 | PM edit/delete/reactions | REST endpoints + WebSocket push | Matches existing PM pattern (POST /pm/send). Safer than modifying lobby read loop. |
| 3 | Unify PM styling | Remove `isPrivate: true` flag in PMView context | PMs rendered through `renderRegularMessage` path, gaining edit/delete/reaction buttons automatically. |
| 4 | Clear conversations | `user_message_clears` table with `cleared_at` timestamp | O(1) storage per clear. Permanent (not recoverable). Filter on fetch — messages still exist for other users. |
| 5 | Delete PM conversation | `deleted_pm_conversations` table | Like leaving a room. Conversation reappears if other user sends new message. |
| 6 | Email registration | Required for new users, nullable in DB | Supports existing users. Pydantic EmailStr validation. No email verification flow (separate future ticket). |
| 7 | Edit email/password | Require current password for both | Security best practice. New auth endpoints. |
| 8 | Settings page | Full page at `/settings` with react-grid-layout | Matches AdminPage pattern. Extensible for future settings. |
| 9 | User dropdown | Custom dropdown on avatar click | Settings, Admin (conditional), Logout. Replaces separate header buttons. |
| 10 | Remove # prefix | Direct text removal in 3 files | Simplest change in the sprint. |

## Architecture

### Data Flow: PM Edit/Delete

```
Frontend                    Chat Service                   Message Service
   |                            |                              |
   |-- PATCH /pm/edit/:id ----->|                              |
   |                            |-- Validate sender owns msg   |
   |                            |-- PATCH /messages/edit/:id ->|
   |                            |                              |-- Update DB
   |                            |<- 200 OK --------------------|
   |                            |                              |
   |                            |-- Push pm_message_edited     |
   |                            |   via lobby WS to both users |
   |<- pm_message_edited -------|                              |
```

### Data Flow: Clear History

```
Frontend                    Message Service
   |                            |
   |-- POST /messages/clear --->|
   |   { type: "room", id: 5 } |-- Upsert user_message_clears
   |                            |   (user_id, "room", 5, NOW())
   |<- 200 OK -----------------|
   |                            |
   | Next fetch: GET /messages/rooms/5/history
   |                            |-- Filter: sent_at > cleared_at
```

### Settings Page Layout

```
/settings (react-grid-layout)
+------------------+------------------+
|   Profile        |   Security       |
|  - Email         |  - 2FA Setup     |
|  - Password      |    (existing     |
|                  |     component)   |
+------------------+------------------+
|   Account                           |
|  - Clear room history               |
|  - Clear PM history                 |
|  - Delete PM conversations          |
+-------------------------------------+
```

### User Dropdown Menu

```
+------------------+
| [Avatar] username|  <-- click trigger
+------------------+
| Settings    ⚙    |
| Admin Panel 🔒   |  <-- only if is_global_admin
| ──────────────── |
| Logout      →    |
+------------------+
```

## Scope Exclusions

- No email verification flow (future ticket)
- No password reset via email (future ticket)
- No message pinning
- No thread/reply nesting
- No account deletion (placeholder in settings UI)
