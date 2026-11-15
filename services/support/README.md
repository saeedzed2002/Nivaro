# Support foundation

Include `compose.support.yaml` with the base Compose file. Run `scripts/Initialize-LocalSecrets.ps1` to provision its separate PostgreSQL password and Identity service key. The gateway routes the browser API, and the private Identity session check stays on the Compose network.

Customers create and list their conversations under `/api/v1/support/conversations`. Conversation creation accepts a stable `client_conversation_id`. Both conversation scopes support `GET` and `POST` at `/{conversation_id}/messages`. History is ordered by sequence and accepts `after` and `limit`. A retry with the same sender, conversation, client message ID and text returns the committed original. Each sender may commit up to five new messages in a rolling second across conversations.

Staff use `/api/v1/admin/support/conversations`. Support agents see their assignments and the claimable queue. Reading or sending messages requires the assignment unless the caller is a super administrator. Staff claim and super administrators reassign through `PUT /{conversation_id}/assignment`. Use the current version for changes, including `PUT /{conversation_id}/status`. Closing records the time and prevents new messages. Committed history remains available to authorized participants.

A committed message has one private outbox row. The authenticated WebSocket, fan-out worker, read acknowledgements, and retention execution are subsequent P09 work. Tests use `scripts/Verify-SupportFoundation.ps1` with disposable Docker data.
