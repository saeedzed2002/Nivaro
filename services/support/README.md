# Support service

Include `compose.support.yaml` with the base Compose file. Run `scripts/Initialize-LocalSecrets.ps1` to provision its separate PostgreSQL password and Identity service key. The gateway routes the browser API, and the private Identity session check stays on the Compose network.

Customers create and list their conversations under `/api/v1/support/conversations`. Conversation creation accepts a stable `client_conversation_id`. Both conversation scopes support `GET` and `POST` at `/{conversation_id}/messages`. History is ordered by sequence and accepts `after` and `limit`. A retry with the same sender, conversation, client message ID and text returns the committed original. Each sender may commit up to five new messages in a rolling second across conversations.

Staff use `/api/v1/admin/support/conversations`. Support agents see their assignments and the claimable queue. Reading or sending messages requires the assignment unless the caller is a super administrator. Staff claim and super administrators reassign through `PUT /{conversation_id}/assignment`. Use the current version for changes, including `PUT /{conversation_id}/status`. Closing records the time and prevents new messages. Committed history remains available to authorized participants.

The browser connects to `/ws/support` using its same-origin access cookie. Use subprotocol `nivaro.support.customer.v1` for customer sessions or `nivaro.support.staff.v1` for staff sessions. A connection without a subprotocol uses the customer scope. Configure `SUPPORT_ALLOWED_ORIGINS` as an exact JSON allowlist alongside the corresponding Identity origins.

Use `conversation.subscribe` for initial history and `sync.request` after reconnect. Send your last applied sequence as `payload.after`, starting at zero. A `sync.result` contains at most ten messages. If `has_more` is true, request the next page after the last sequence in the result. `message.accepted` confirms database commit. Keep the same `client_message_id` when retrying an unacknowledged send and issue a new `request_id` for each attempt. Match errors against the echoed identifiers. Both versioned schemas are in `contracts/websocket/`.

The server checks the session for every operation and after each 25-second wait for an incoming frame. Reconnect after HTTP refresh when the server closes with `4401`. A `4403` closure means the session lost permission. A `1013` closure calls for backoff. The transport uses a 25-second ping interval and a 35-second pong timeout. Client text messages have a 16 KiB limit.

Each committed message has one private outbox row. Push notifications, read acknowledgements, and retention execution are subsequent P09 work. Use `scripts/Verify-SupportFoundation.ps1` to exercise HTTP and WebSocket with disposable Docker data and check the exported schemas.
