# AudioHarbor — Python 3 Web Application Specification

Version: 1.0 • Date: 2026-10-04 • Status: implementation-ready design

## 1. Product and deployment contract

AudioHarbor accepts a video or playlist URL, discovers its media entries, downloads the best available audio, converts each entry to MP3, and saves successful files beneath `~/Downloads`. Its primary platform is Ubuntu Linux. It runs as the signed-in operating-system user and presents a browser interface at `http://127.0.0.1:8787`.

**The output directory belongs to the machine running the backend.** A cloud-hosted web application cannot silently write into the visitor's Downloads directory. Local execution is therefore the required deployment for version 1. Remote deployment, if added later, must use explicit browser downloads or a local companion; it must not claim that server-side files are in the visitor's home directory. Containers require an explicit bind mount of the user's Downloads directory.

Application name is a proposed working name, with no claim of trademark availability. This document specifies the app; it does not implement it or download media.

### Required outcomes

- Accept supported HTTPS video and playlist URLs, primarily YouTube, including short links and Shorts.
- Process every discoverable playlist video, preserving order and reporting individual outcomes.
- Traverse nested playlist results with cycle detection and configurable bounds.
- Produce valid MP3 files and durable job history.
- Handle authentication, throttling, network failures, unavailable entries, and conversion failures without losing successful outputs.
- Pause affected work when authentication is needed, prompt the user, and resume after credentials are supplied.
- Run work outside HTTP request handlers; the UI remains responsive during long jobs.

### Scope boundaries

Only process media the user is entitled to download. DRM-protected content and unavailable access rights produce actionable failures. Authentication does not guarantee downloadable media. Do not implement DRM removal, CAPTCHA automation, account rotation, or proxy rotation to evade restrictions. Live streams are excluded in version 1; completed recordings can be processed. Channels, search queries, and indefinite dynamic mixes are not accepted as bounded playlists in version 1.

## 2. Technology and component architecture

| Component | Required design |
|---|---|
| Runtime | Python 3.12 or newer compatible release, exact tested version recorded in release lockfiles |
| Web/API | FastAPI, Uvicorn, Pydantic schemas |
| Front end | Jinja2 templates, locally bundled HTMX or small JavaScript modules, CSS; no required CDN |
| Database | SQLite with WAL, foreign keys, busy timeout; SQLAlchemy and Alembic migrations |
| Queue | Durable database-backed scheduler in a separate worker process |
| Media extraction | yt-dlp adapter, isolated child process per discovery/download attempt |
| Conversion | FFmpeg with MP3 encoder support; ffprobe verification |
| Secrets | Linux Secret Service through a supported keyring; ephemeral files when credentials are used |
| Events | Persisted event log delivered with Server-Sent Events (SSE) |
| Testing | pytest, API integration tests, browser workflow tests, synthetic media fixtures |
| Packaging | pyproject.toml, reproducible dependency lock, CLI launcher, optional systemd user units |

Web process owns input validation, HTML, REST endpoints, and event delivery. Worker owns discovery, scheduling, rate limits, process execution, conversion, and output publication. The adapter translates extractor-specific results into stable internal models and errors. Workers must never run synchronous extraction inside the web event loop.

yt-dlp supplies media extraction and browser-cookie facilities; FFmpeg provides audio conversion. The implementation must check the current extractor requirements, including supported JavaScript runtime/helper dependencies needed for YouTube, at release time rather than hardcode assumptions about platform behavior. See the upstream references in section 19.

## 3. User interface and workflows

### Home / new job

Show URL field, MP3 quality choice, output path, playlist behavior, and Start button. Defaults: MP3 VBR quality 2, playlist processing enabled, no thumbnail embedding, continue on individual failure, skip already completed media. Additional choices: CBR 128/192/256/320 kbps; embed artwork; include video only when a watch URL contains a playlist identifier.

A watch URL containing both video and playlist identifiers defaults to the entire playlist, with an explicit visible selection. Clearly show this choice before submission. MP3 bitrate is an encoding choice and cannot restore quality missing from the source.

Submit starts a durable discovery job immediately. Show discovery progress and discovered entries incrementally; for playlists, show a review screen before downloads begin. Review offers selection, range selection, total count, known duration, unknown-size warning, Start all, and Cancel. Single-video jobs start after discovery without another confirmation. If a configured limit is reached, display a paused limit state and retain the discovered list; never silently truncate and label it complete.

### Job detail

Show title, source host, phase, discovered/selected/completed/failed/skipped counts, rate-limit countdown, per-item status, bytes, speed, elapsed time, known ETA, and sanitized error messages. Unknown progress displays an indeterminate indicator. Network-download percentage and conversion progress are separate; a downloaded source is not a completed MP3.

Actions: pause, resume, cancel, retry failed entries, supply authentication, download a generated MP3 through the browser, and remove history. Removing history never deletes MP3 files. Version 1 provides Copy folder path; arbitrary operating-system command execution to open folders is not an API feature.

### Authentication dialog

Explain which service needs authentication and why. Offer anonymous retry if appropriate, import browser session, upload Netscape-format cookie file, or cancel affected entries. Sign-in takes place on the hosting service in the user's browser. The app does not ask for a Google password and does not promise a YouTube OAuth download integration. Display whether the selected method is supported by the installed adapter.

### Settings / diagnostics

Show resolved output path, writable-space check, concurrency, limits, supported hosts, installed dependency versions, and explicit update diagnostics. Credential screen lists service and expiry/status without cookie values. No auto-update during an active job.

Accessibility: keyboard-operable controls, labeled inputs, visible focus, readable contrast, ARIA live updates throttled to avoid excessive announcements, responsive layouts, and errors described in text.

## 4. URL validation and supported hosts

Accept one URL per submitted job, maximum 4,096 characters. Reject embedded username/password, control characters, unsupported schemes, nonstandard ports, local files, and private-network targets. Use parsed hostname comparisons, not substring matching. Canonicalize aliases through adapter rules while preserving playlist identifiers. Never trust a user-supplied output path or extractor option string.

YouTube is enabled by default. Other hosting services require a server-side allowlist and an adapter capability declaration; unknown URLs return `UNSUPPORTED_HOST`. Do not enable unrestricted generic extraction by default.

Protect all extractor traffic, media fetches, redirects, and nested results from SSRF: reject loopback, private, link-local, reserved, metadata-service, and local-domain destinations after DNS resolution; enforce again at connection time and after redirects. Implement this through a controlled egress gateway or network policy that covers child processes and FFmpeg, not just an initial URL check. Service adapters declare required public CDN hosts. Scope credentials to their actual domains and never forward them across unrelated redirects.

## 5. Discovery, playlists, and recursion

1. Validate and classify input through the service adapter.
2. Perform lightweight paginated enumeration without downloading media; persist entries as discovered.
3. A media result becomes a task. A supported playlist result becomes a traversal node. Unknown result types become explicit unsupported outcomes.
4. Traverse nested playlists using a bounded queue. Maintain a visited set keyed by service/extractor and canonical collection identifier. Maintain separate media deduplication keyed by service and media identifier. Persist both so restart cannot cause cycles.
5. Preserve source order using an index path such as `[3, 2]` for the second item in a nested third collection. Flatten the final list in that order. Duplicate playlist occurrences remain visible as skipped duplicates and reference the original task/output.
6. Private/deleted placeholders remain visible, even if no usable URL or ID exists. Never drop them from result accounting.
7. Once discovery finishes, freeze a playlist snapshot; source changes are reflected only by an explicit new discovery. Dynamic/infinite collections are rejected or pause at the configured bound.
8. Resolve full media details immediately before transfer. Signed media URLs are ephemeral and must not be stored as durable download identities.

Defaults: maximum 1,000 entries including unavailable occurrences; maximum nesting depth 5; maximum 20 collection nodes; discovery wall-clock budget 10 minutes. Limits can be raised in trusted local settings. A partial enumeration failure offers Retry discovery, Process discovered entries, or Cancel. Discovery continuation must deduplicate persisted results.

## 6. Audio pipeline and output policy

### Per-media sequence

Claim task → resolve metadata → select audio → download to private staging → validate input → convert → optionally tag/artwork → verify MP3 → publish atomically → mark succeeded.

Prefer audio-only source streams. If no separate audio stream exists, download a supported combined stream and discard video during conversion. Choose best available source audio within byte/duration limits. No need to download full video when audio-only is available.

Conversion uses FFmpeg `libmp3lame`, VBR quality 2 by default, or the selected CBR bitrate. Keep a compatible source sample rate; downmix more than two channels to stereo. Metadata fields: title, uploader/artist if available, playlist album if selected, track number, source webpage, and media identifier. Sanitize tags; do not invent artists. Optional JPEG/PNG artwork is bounded, validated, and embedded as an attached picture; artwork failure is a warning by default. Do not perform loudness normalization or silence trimming unless a future explicit feature adds it.

Run executables with argument arrays and `shell=False`; only structured internal options are allowed. FFmpeg accepts only the locally staged media file and bounded local artwork. Restrict protocols to those actually needed for local processing. Capture process progress through structured pipes; cap stderr retained for diagnosis.

### Filesystem contract

Resolve default output root as `Path.home() / 'Downloads'` under the actual runtime user. Create the directory if missing after validating its parent and permissions. Never run the app as root. Exact default layouts:

```text
~/Downloads/Title [service-media_id].mp3
~/Downloads/Playlist Title [playlist_id]/001 - Title [service-media_id].mp3
```

Nested playlists flatten into the root playlist folder with a sequential index. Preserve original index paths in the database. Unsafe/missing IDs use generated safe identifiers. Filename sanitization removes separators, NUL/control characters, traversal components and unsafe leading names, normalizes Unicode, and bounds UTF-8 byte length while retaining the stable suffix.

Staging resides on the output filesystem in a private `.audioharbor-tmp` directory, with per-task UUID subdirectories and mode 0700. Stage the completed MP3 there. Verify via ffprobe that it has MP3 audio, positive duration, and nonzero size; duration mismatch outside a documented tolerance produces a warning or failure according to source reliability. Publish with an atomic no-clobber operation; do not use a blind replacement that overwrites existing user files. Resolve collisions with a deterministic suffix, record the final path, and reconcile after a crash.

Prevent symlink escapes and concurrent path swaps with directory-relative operations and no-follow checks. Serialize final-path reservation. Normal API requests cannot change the output root. A trusted config change requires startup validation.

Global output identity is `(service, media_id, conversion_profile_hash)`. Skip prior successes only after the recorded file exists and its stored checksum/size matches. A missing file requeues; an altered file triggers a collision-safe new output. Different quality settings produce different profiles. Multiple jobs sharing a transfer attach to one durable task and publish one output; show references in each job. Explicit force-redownload creates a new generation without overwriting prior files.

Keep completed MP3s indefinitely. Retain resumable source fragments for 24 hours after failure/cancellation unless the user clears them. Delete successful staging sources after publication. Never count a partial MP3 as success.

## 7. Authentication and credential lifecycle

Maintain separate app-session authentication and source-service authentication. Source sessions grant access only to their matching hosting service; they are not application logins.

Authentication methods:

- **Browser session import:** user explicitly chooses a supported browser/profile from server-discovered options. Read cookies locally through the adapter, select required service domains, and create an isolated session snapshot. API must accept opaque profile IDs rather than arbitrary filesystem paths. Browser locks, inaccessible keyrings, and unsupported encryption produce instructions rather than a crash.
- **Cookie file upload:** accept Netscape-format cookie files up to 2 MiB, parse strictly, reject unrelated service domains, validate syntax/expiry, and avoid retaining uploaded original bytes unnecessarily. Treat cookies as secrets.
- **Service-specific credentials:** only where an implemented adapter explicitly supports them. Credentials enter through a protected form, never URL query strings; unsupported methods remain unavailable.

YouTube browser sign-in can require user interaction. Cookie import may still fail because of account rights, session expiry, platform challenges, or extractor incompatibility. Do not route service login through an iframe or assume an OAuth access token works for extraction.

`AUTH_REQUIRED` parks affected tasks without exhausting network-retry counters. A service-scoped auth gate pauses pending tasks with the same failing session while unrelated hosts continue. Show the dialog once per credential version, coalescing repeated failures. User imports a new session; perform one bounded validation against the affected resource, then explicitly resume affected tasks. A renewed session that still fails returns to an actionable wait state, without an automatic prompt loop.

Ephemeral credentials are the default: worker-private storage, mode 0600 files when required, excluded from logs/backups, destroyed when associated jobs finish or after one hour of inactivity. Restart invalidates ephemeral session references and asks the user to reauthenticate. Optional Remember session uses an OS keyring; if unavailable, disable persistence rather than writing plaintext secrets to SQLite. Revocation removes stored secrets and terminates affected in-flight attempts. Redact cookies, auth headers, signed query parameters, and passwords from all diagnostics.

## 8. Error classification and retry contract

Separate provider HTTP status from AudioHarbor API status. An upstream 401 belongs in a task error record; it must not inadvertently sign the user out of the app. Classify typed exceptions and nested causes first; use versioned, tested message patterns only as a fallback. Unknown failures remain unknown and show sanitized diagnostics.

| Condition | Stable error | Required action |
|---|---|---|
| Provider 401 / explicit login requirement | `AUTH_REQUIRED` | Pause affected scope and prompt for a supported session method |
| 403 with known expired-session/private-access signal | `AUTH_REQUIRED` or `ACCESS_DENIED` | Prompt once for renewable session; insufficient rights fails with explanation |
| Other 403 | `FORBIDDEN` | Diagnose rights, region policy, challenge, expired media URL, or extractor mismatch; do not universally prompt |
| Expired signed media URL | `MEDIA_URL_EXPIRED` | Re-extract once, then retry from validated source |
| Provider 429 | `RATE_LIMITED` | Persist shared host/session/egress cooldown; do not ask for login solely due to 429 |
| Provider 408, transient DNS/socket failure, 500/502/503/504 | `TRANSIENT_NETWORK` | Bounded retries with backoff |
| 400, unsupported URL/format | `INVALID_SOURCE` / `UNSUPPORTED_FORMAT` | Fail without automatic retry |
| 404/410, deleted/private unavailable item | `UNAVAILABLE` | Mark item failed/unavailable; continue playlist |
| Challenge / bot confirmation | `INTERACTION_REQUIRED` | Pause, explain browser action or session import where supported; no guaranteed bypass |
| Region restriction / DRM | `REGION_RESTRICTED` / `DRM_UNSUPPORTED` | Terminal actionable failure |
| Missing FFmpeg/encoder/runtime/helper | `DEPENDENCY_MISSING` | Block start/readiness; show remediation |
| ENOSPC, disk quota, permission denied | `DISK_FULL` / `OUTPUT_PERMISSION_DENIED` | Pause affected output scope; resume only after successful recheck |
| Conversion corruption/nonzero exit | `CONVERSION_FAILED` | Preserve source for diagnosis/retry; no repeated identical automatic conversion |
| Worker crash / interrupted process | `WORKER_INTERRUPTED` | Recover lease, inspect staging, and resume safely |

For transient failures, allow five attempts total with full jitter based on `min(120s, 2s * 2^(attempt-1))`. Respect any valid provider Retry-After when present as a lower bound; parse both seconds and HTTP dates. For 429, use valid Retry-After or exponential cooldown starting at 60 seconds, capped at 30 minutes when no server delay exists. Never shorten a longer server-requested delay; persist `next_attempt_at` and show the countdown. After five throttle episodes per task, enter `waiting_user` rather than retry forever. Operator resume retains shared cooldown.

One layer owns retry budgets. Configure yt-dlp internal request/fragment retries explicitly and boundedly; include those requests in adapter accounting so application retries do not multiply into an unbounded storm. Download resume validates that the re-resolved source representation matches the staged fragments; otherwise restart that item safely.

Default one active download per service/egress scope and one converter; maximum configurable download concurrency 3. Space successive item starts by a jittered 2–5 seconds. A 429 prevents all new requests within its scope, including discovery and metadata probes; in-flight attempts stop at the next safe boundary. Repeated 403s with a shared cause open a service circuit and surface one diagnostic incident.

## 9. Durable queue and state machines

Job states: `queued`, `discovering`, `awaiting_selection`, `running`, `paused`, `waiting_auth`, `waiting_retry`, `waiting_user`, `completed`, `completed_with_errors`, `failed`, `cancelled`. Item states: `discovered`, `queued`, `resolving`, `downloading`, `converting`, `verifying`, `waiting_auth`, `waiting_retry`, `paused`, `succeeded`, `failed`, `skipped`, `cancelled`.

Persist every transition with reason, version, timestamps, and event in one database transaction. Job visible state is derived from child states using explicit precedence: cancellation, manual pause, active work, blocking waits, terminal aggregation. Mixed authentication waits do not make unrelated running items appear stopped. Job counts and per-item statuses are authoritative.

Queue claims use atomic database transactions with lease owner, lease expiry, and attempt number. Heartbeat every 10 seconds; lease expires after 60 seconds. Expired tasks are reconciled against processes/staging before reassignment. Single local worker supervisor prevents competing processes; design claim semantics for future additional workers. No exactly-once promise: use at-least-once execution with idempotent publication.

Pause stops new claims and cooperatively stops downloads while preserving resumable fragments; conversion may finish before the job becomes fully paused. UI distinguishes pause requested from paused. Cancel terminates the child process group, waits up to 10 seconds, then kills remaining children. Preserve successful files. Reconcile cancellation racing with final publication: if publication completed, retain the successful item and cancel remaining work. Retry failed creates new attempt records and changes only eligible failed/cancelled entries selected by the user.

On restart, reconcile published-but-uncommitted files, reclaim stale leases, clean obsolete staging, restore rate-limit deadlines, and convert missing credential references into authentication waits. A verified file can satisfy recovery even if the final DB commit previously failed.

## 10. Database model

Use UUID primary keys; UTC timestamps; bounded JSON metadata; schema-versioned conversion profiles. Sensitive signed URLs and cookie material are never durable metadata.

| Table | Required fields and constraints |
|---|---|
| jobs | id, input_url_redacted, canonical_source, service, state, options_json, discovery_complete, limit_reason, created_at, updated_at, cancel_requested, pause_requested, version |
| collections | id, job_id, service, collection_key, parent_id, index_path, title, discovery_cursor, state; unique traversal identity per job |
| job_entries | id, job_id, collection_id, index_path, source_id nullable, task_id nullable, display_title, occurrence_status, selected; unique occurrence path |
| media_tasks | id, service, media_id, profile_hash, generation, state, auth_session_id nullable, attempt_count, next_attempt_at, lease_owner, lease_until, heartbeat_at, progress_json, output_id; unique identity/profile/generation |
| attempts | id, task_id, phase, number, started_at, ended_at, error_code, provider_http_status, retryable, sanitized_message, diagnostic_ref |
| outputs | id, service, media_id, profile_hash, generation, relative_path, sha256, size_bytes, duration_seconds, published_at; unique relative_path |
| auth_sessions | id, service, opaque_secret_ref nullable, credential_version, method, persistence, expires_at, state; no credential bytes |
| rate_limits | scope_key, next_allowed_at, throttle_count, reason, updated_at |
| events | monotonically increasing id, job_id, event_type, payload_json, created_at |

Index claimable task state/deadline, leases, job entries by job/order, and events by job/id. Store output paths relative to the validated root. Migration startup backs up metadata and refuses unsupported downgrade. Retain job history 90 days by default, events 7 days, sanitized diagnostics 14 days. Retention never deletes user MP3s.

## 11. REST API

All routes are under `/api/v1`. Mutations require the local app session and CSRF protection. Responses use explicit Pydantic contracts; unknown fields are rejected.

| Method / route | Contract |
|---|---|
| `POST /jobs` | URL, `playlist_mode: all|video_only`, encoding, embed_artwork; returns 202 with job ID |
| `GET /jobs` | Cursor pagination and state filter |
| `GET /jobs/{id}` | State, totals, active phase, waits and options |
| `GET /jobs/{id}/entries` | Cursor-paginated entries in stable source order |
| `POST /jobs/{id}/start` | Selected entry IDs or all; requires discovery review state |
| `POST /jobs/{id}/pause` | Idempotent request to pause |
| `POST /jobs/{id}/resume` | Recheck blocking conditions, resume eligible work |
| `POST /jobs/{id}/cancel` | Idempotent asynchronous cancellation |
| `POST /jobs/{id}/retry` | Explicit entry IDs or failed-only; new bounded attempts |
| `POST /jobs/{id}/discovery/retry` | Resume failed/partial enumeration |
| `GET /jobs/{id}/events` | SSE with event IDs, heartbeat, Last-Event-ID replay |
| `POST /auth-sessions` | Service, permitted method, opaque browser profile ID or bounded cookie upload |
| `POST /jobs/{id}/auth-session` | Associate permitted session and validate/resume |
| `DELETE /auth-sessions/{id}` | Revoke session and stop associated attempts |
| `GET /outputs/{id}/file` | Serve verified MP3 with sanitized Content-Disposition and Range support |
| `DELETE /jobs/{id}` | Remove terminal job history only; active job returns 409 |
| `GET /settings` | Nonsecret effective configuration |
| `GET /diagnostics` | Dependency and filesystem checks, sanitized versions |
| `GET /health/live`, `GET /health/ready` | Process liveness / database-worker-dependency readiness |

`POST /jobs` supports an `Idempotency-Key` scoped to local session for 24 hours. Same key with different payload returns 409. Mutations affecting versioned job selections accept expected version to avoid stale updates.

API errors: `{ "error": { "code": "INVALID_URL", "message": "Enter a supported HTTPS video or playlist URL.", "retryable": false, "request_id": "uuid", "details": {} } }`. API statuses: 400 invalid syntax, 401 invalid app session, 403 app-session/CSRF authorization denial, 404 unknown resource, 409 state conflict, 413 oversized credentials, 422 invalid fields, 429 local request quota, 503 readiness failure. Upstream errors remain task events.

SSE payloads include job state, item progress, warnings, auth requirement, retry deadline, and output publication. Retained event gap sends a reset/snapshot instruction. Reconnect must not start another download. Coalesce progress events to at most twice per second per active item; poll every two seconds as a fallback.

## 12. Local web security

Bind loopback only by default. Validate Host and Origin against configured loopback origins to resist DNS rebinding. Disable cross-origin API access. Establish a local session using a one-time bootstrap token printed/opened by the trusted launcher, then remove token from the address bar through a redirect; keep it out of logs. Use an HttpOnly SameSite=Strict session cookie and per-session CSRF token on mutations; Secure cookies are required if TLS is configured. Protect SSE and file routes too.

No source credentials in HTML, browser localStorage, analytics, or logs. Escape all service-provided titles and metadata; render no raw extractor HTML. Serve a restrictive CSP, local assets, no third-party trackers. Bound request bodies, queue length (100 jobs), maximum media duration (6 hours), downloaded source bytes (2 GiB/item), conversion CPU/memory, process count, and diagnostic buffers. Unknown size is handled by streaming byte limits, not trusted metadata.

Restrict child privileges and filesystem access where feasible; network access is needed only for extraction/download, not conversion. Do not load untrusted yt-dlp plugins, user config files, or arbitrary executable hooks. Disable automatic execution of global extractor configs. URLs are data, never shell commands.

Public/LAN exposure is outside the default deployment. Adding it requires real app authentication, TLS, per-user ownership/storage/secret isolation, request quotas, and explicit new security review. Source-cookie support alone does not provide application access control.

## 13. Configuration and operating limits

Use typed config from a user-owned TOML file and documented environment overrides. Refuse invalid values on startup. Suggested keys:

```toml
[server]
host = "127.0.0.1"
port = 8787

[storage]
output_dir = "~/Downloads"
minimum_free_bytes = 1073741824
history_days = 90
partial_retention_hours = 24

[worker]
download_concurrency = 1
conversion_concurrency = 1
socket_timeout_seconds = 30
max_attempts = 5

[limits]
playlist_entries = 1000
playlist_depth = 5
collection_nodes = 20
media_duration_seconds = 21600
source_bytes = 2147483648

[media]
format = "mp3"
quality_mode = "vbr"
vbr_quality = 2
embed_artwork = false
```

Persist state beneath `$XDG_STATE_HOME/audioharbor` or `~/.local/state/audioharbor`, configuration beneath `$XDG_CONFIG_HOME/audioharbor`, cache beneath `$XDG_CACHE_HOME/audioharbor`. Downloads remain exactly beneath the configured default `~/Downloads`. Reserve estimated staging/output capacity across concurrent tasks; monitor disk space continuously and suspend before breaching the 1 GiB safety reserve. Duration/size limits exceeded mid-transfer produce explicit limit errors.

Timeouts: discovery 10 minutes; media resolution 2 minutes; inactivity/socket timeout 30 seconds; conversion bounded by a configurable duration-based budget (default max 2 hours). Long known-duration downloads are governed by inactivity and maximum size rather than a short total timeout.

## 14. Installation, maintenance, and delivery

Deliver source repository, README, lockfile, example configuration, Alembic migrations, tests, user-service templates, and troubleshooting guide. Package a CLI with `audioharbor doctor`, `audioharbor serve`, `audioharbor worker`, and `audioharbor start` (supervised web plus worker). Launcher must shut down children cleanly and avoid duplicate worker instances.

Ubuntu installation guide covers Python virtual environment, locked app installation, FFmpeg/ffprobe, tested JavaScript runtime/helper dependencies, optional keyring support, and writable user directories. Native user execution is preferred for access to local browser sessions. A container variant mounts Downloads and state using the same user UID/GID and documents that host browser-cookie import is unavailable unless explicitly integrated; cookie-file upload remains available.

Optional systemd user units run without root, restart on failure, and preserve state. Record extractor and FFmpeg versions per attempt. Dependency updates happen through a controlled release process: test public synthetic fixtures and optional authorized provider smoke checks, pin validated versions, publish release notes, retain rollback instructions. YouTube compatibility can change independently of app releases; expose an extractor compatibility diagnostic without promising permanent service availability.

## 15. Observability and troubleshooting

Structured JSON logs include request ID, job/task/attempt IDs, phase, latency, stable error code, provider status when known, and dependency versions. Logs omit full cookie payloads and signed URLs; ordinary source URLs are sanitized too. Record sanitized provider diagnostics behind an explicit user-facing View details control.

Track queue depth, discovery count, success/failure by stable code, transfer bytes, conversion duration, worker heartbeat age, free disk, retry counts, and auth/rate-limit waits. Metrics remain local by default. Readiness fails for missing dependencies, unwritable state/output, and stale worker heartbeat. An external provider outage does not make process liveness fail.

Support guidance distinguishes expired session, insufficient rights, platform challenge, missing runtime/helper, blocked network, and unsupported media. Export diagnostics only after user action; scan/redact before producing a support bundle.

## 16. Validation and acceptance criteria

Use deterministic extractor doubles and a local HTTP fixture service for automated tests. Provider integration checks are optional, authorized, and separate from CI; do not depend on copyrighted public examples or a permanent YouTube test URL.

| Scenario | Acceptance criterion |
|---|---|
| Public single video | One playable verified MP3 appears under the runtime user's Downloads; job succeeds only after publication |
| Playlist of 10 with two unavailable entries | Eight outputs; two explicit failures; stable ordering; job `completed_with_errors` |
| Nested playlist and cycle | Each unique media is processed once; repeated collections stop; original occurrences remain visible |
| URL has watch and playlist identifiers | All mode processes playlist; video-only mode processes exactly one entry |
| Playlist limit/partial discovery | UI exposes incomplete discovery and explicit continuation choice; no false complete status |
| Provider 401 | Task parks; one auth dialog; valid new session resumes without duplicate successful outputs |
| Provider 403 | Auth prompt only when evidence supports it; permanent denial terminates; expired URL refresh occurs once |
| Provider 429 with seconds/date Retry-After | Scope issues no new requests before persisted deadline, including after restart |
| Network disconnect | Bounded attempts, coherent progress, compatible fragments resume or restart safely |
| Browser-cookie import failure | Actionable browser/keyring message, no leaked secret, upload fallback offered |
| Expired cookies/revocation | Reauthentication or cancellation; no prompt loop and no use of revoked session |
| Disk full / denied permissions | Pause before publication; previous outputs intact; resume after writable-space validation |
| Corrupt source / failed FFmpeg | Explicit conversion failure; no partial final MP3; source retained within policy |
| Crash before/after publication | Recovery produces one verified output and coherent database state |
| Duplicate submissions / filename collision | Idempotent reuse or distinct safe filename; existing user file never overwritten |
| Pause/cancel during transfer/conversion | Responsive UI; bounded process termination; successful files preserved |
| Hostile title/URL/redirect/symlink | No XSS, shell execution, private-network request, or output-root escape |
| SSE disconnect/replay | Snapshot or replay restores display; no new task created |
| Fresh Ubuntu install | Doctor identifies dependencies; startup and completed synthetic conversion succeed without root |

Include unit tests for classifications, Retry-After, filename rules, recursion, and aggregate states; integration tests for leases/publication/secrets/API; browser tests for selection/auth/retry/cancel; and process tests using synthetic audio. Simulate each required status (401, 403, 429 and 5xx) including nested extractor exception causes. CI includes formatting/lint, type checking, dependency auditing, database migrations, and meaningful tests.

Performance targets on a typical Ubuntu desktop: new-job HTTP response within 500 ms excluding asynchronous discovery; progress visible within 2 seconds of worker events; cancellation signal dispatched within 2 seconds; no full-playlist JSON loaded unboundedly into memory. Keep metadata browsing usable for 1,000 entries through pagination. Throughput depends on provider limits and hardware; correctness takes precedence over parallelism.

## 17. Suggested repository layout

```text
audioharbor/
  pyproject.toml
  README.md
  config.example.toml
  src/audioharbor/
    cli.py
    config.py
    web/{app.py,routes/,schemas/,templates/,static/}
    domain/{models.py,states.py,errors.py,profiles.py}
    db/{models.py,repositories.py,migrations/}
    worker/{scheduler.py,leases.py,recovery.py,processes.py}
    adapters/{base.py,yt_dlp_adapter.py,auth.py}
    media/{conversion.py,verification.py,publication.py}
    security/{sessions.py,csrf.py,egress.py,redaction.py}
  tests/{unit/,integration/,browser/,fixtures/}
  packaging/{systemd/,container/}
  docs/{installation.md,operations.md,troubleshooting.md}
```

Adapters expose `classify_url`, `discover`, `resolve_media`, `download_audio`, `validate_session`, and `classify_error`. Domain interfaces use typed models rather than leaking yt-dlp dictionaries across the app. Credentials are opaque session references outside the credential manager.

## 18. Implementation milestones and definition of done

1. Foundation: typed settings, local-session/CSRF security, schema/migrations, dependency doctor, filesystem and egress safeguards.
2. Single media: isolated extraction, download, MP3 conversion/verification/publication, durable attempts, UI/SSE.
3. Playlists: paginated discovery, review, nested traversal, placeholder accounting, deduplication, selection and aggregate results.
4. Recovery: bounded retries, 429 shared cooldowns, leases, crash reconciliation, pause/cancel, disk safety.
5. Authentication: browser/cookie methods, service gates, validation/resume, ephemeral/keyring lifecycle and redaction.
6. Release: acceptance tests, clean Ubuntu installation, user services, docs and reproducible dependencies.

Done means all acceptance scenarios pass, the default installation saves playable MP3s beneath `~/Downloads`, every playlist occurrence has an explained outcome, source authentication can be supplied and revoked safely, and restart cannot silently lose completed work or overwrite existing files. Deliver full runnable source when implementation is requested; no placeholder core extraction, authentication, retry, or queue behavior.

## 19. Upstream reference baseline

Checked 2026-10-04. These links ground dependency capabilities; retry numbers, UI choices, storage rules, and architecture above are AudioHarbor design decisions.

- yt-dlp project documentation, supported options, dependencies, and Python embedding: https://github.com/yt-dlp/yt-dlp
- yt-dlp extractor guidance, including YouTube session-cookie caveats: https://github.com/yt-dlp/yt-dlp/wiki/Extractors
- yt-dlp FAQ, including cookies and HTTP throttling troubleshooting: https://github.com/yt-dlp/yt-dlp/wiki/FAQ

Review upstream documentation again when implementing and lock the exact tested dependency set. Browser sign-in, source authorization, and extractor compatibility remain distinct conditions.
