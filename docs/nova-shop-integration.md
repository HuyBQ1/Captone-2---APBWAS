# Nova Commerce website integration

Source: https://nova-commerce-neon.vercel.app. APBWAS uses only GET requests to the integration API and the public categories endpoint. Required scopes: `products:read`, `inventory:read`, `orders:read`, `finance:read`.

## Operation

Admin opens Connections and manages the Nova Commerce card. The supplied API key is encrypted using the existing server-side Fernet vault. It is never returned to the browser. Hostname is fixed to the owner-provided Nova website; no arbitrary server URLs are accepted.

The first connection requires explicit replacement of old business data. Every remote page and each monthly finance report must be fetched and reconciled before local replacement. First replacement is blocked while workflows or email deliveries are active. An owner-requested complete PostgreSQL backup was made before cutover. The importer also saves a business JSON backup under the persistent uploads volume before changing tables. Upload backups are not public download endpoints.

Products, current stock, images, delivery/return sales events, aggregate monthly expenses and stock movements are mirrored into APBWAS. Stable UUIDs derive from remote IDs. Repeated full refresh replaces only imported sales/expenses/movements and upserts products, avoiding duplication. Remote order snapshots store only ID, status, timestamps, monetary total and units, never recipient addresses, phone numbers or emails.

The worker checks for a refresh every five minutes when running. An Admin can request one manually. Failed API requests, missing scopes, incomplete pagination, inconsistent totals or revoked keys do not erase the previous snapshot. The connection card exposes the last successful synchronization and errors. This is periodic synchronization, not a webhook or a real-time transaction feed. A busy worker can delay its next refresh.

Order lookups by the Agent now read the read-only integration orders API directly, after permission checks, so a just-created order does not wait for the periodic financial/catalog mirror. Live lookup failures are surfaced rather than silently falling back to the old order count. `date` and `order_status` are independent filters; explicit today/yesterday requests override an inherited month. `pending` means waiting for confirmation and `confirmed` means already confirmed. The LLM selects the tool; backend normalization enforces explicit user date/status constraints. No customer PII is retrieved by this connector. Products, inventory and finance still use the five-minute mirror.

API endpoints on APBWAS:

- GET `/api/connections/shop`: source status; finance details are hidden from users without sales.read.
- PUT `/api/connections/shop`: Admin/settings.manage configuration and initial synchronization.
- POST `/api/connections/shop/sync`: Admin/settings.manage manual synchronization.

Business data writes in APBWAS are blocked while this source is active. Update goods, sales, costs, expense confirmation and stock on the sales website. Existing local Excel imports cannot overwrite the source.

## Financial definitions

- A positive sales event occurs at `recognized_at`. A return is a negative event at `returned_at`.
- Net revenue is quantity times historical price minus per-unit discount, with returns subtracted.
- Historical line costs are retained. Missing costs remain unknown.
- Expenses are imported as one aggregate row per month because the integration API does not expose individual expense records. The export labels this explicitly.
- Operating result remains unknown until the website marks expenses complete and all costs are known.
- Orders created in a month are separate from distinct orders with delivery/return events in that month. `created_order_count` and the `query_shop_orders` tool provide the former; the finance workbook's existing order-count formulas count the latter. The workbook explains both.
- Shipping and cash collection/refunds are not substituted for merchandise revenue. Tax profit is not inferred.

Scope is bounded to 10,000 records per paginated collection, 36 months and 8 MB per API response. Larger data requires an incremental connector. Source changes during pagination/reconciliation can require a retry. A source transaction moving between the individual GET requests is not a distributed snapshot.

## Old data

The initial cutover replaces old products, sales, inventory, stock movements, expenses, financial period flags and legacy revenue reports. It removes generated policy text referenced by the old operational dataset manifest and retires its Agent knowledge bindings. Owner-uploaded documents, accounts, Gmail, model connections and audit history remain. Earlier business-generated files are marked superseded and cannot be downloaded, attached or reused as the current source; existing historical chat text and already-sent email cannot be recalled. Full pre-cutover history remains in the PostgreSQL backup.

## Verification

Initial live mirror: 56 products, 385 orders, 758 delivery/return lines, 1,179 stock movements, reporting months May through November 2026. Revenue and costs were reconciled to the source finance API before replacement. Six accounts, one Gmail connection and one saved model provider were preserved; credential fingerprints matched before/after initial cutover. These are counts of website records, not a claim that source transactions represent a legally operating business.

Tests exercise failed upstream rollback, explicit replacement, repeat import without duplication, return arithmetic, period completeness, role isolation, read-only business source, source order filtering and retirement of generated policies while keeping uploaded documents. No test sends employee/customer PII to an LLM.
