# Server-owned alert incidents with FCM as a delivery channel

Alembic will detect, persist, deduplicate, and resolve mobile alert incidents on the server, then use Firebase Cloud Messaging to wake the stock-Android Pixel client. Client polling and local threshold logic were rejected because they cannot meet the agreed background-delivery targets and would create a second definition of risk. FCM payloads contain only opaque incident routing data; the authenticated app fetches details from Alembic.

## Consequences

Alert state must survive restarts and record delivery attempts independently of Telegram. Google Play Services is an MVP device prerequisite. A future non-Google transport can implement the same delivery port without changing incident semantics.
