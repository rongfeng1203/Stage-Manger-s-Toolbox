# Known Limitations

- The three frontend plan previews are deterministic browser-generated layouts;
  the pure Python CP-SAT schedule-option endpoint is not yet exposed through FastAPI.
- Production state is not persisted by the release UI. SQLModel entities and
  SQLite setup exist, but the browser workflow is in-memory.
- Google OAuth callback, refresh-token storage, and free/busy import are local
  single-connection features. They are suitable for a stage-manager account that
  can view the participating calendars. A public multi-user deployment needs a
  database-backed token store and a public HTTPS callback URL.
- External actor calendars must share free/busy visibility with the connected
  account. Google returns an access error otherwise; the importer reports that
  actor and preserves existing manual availability.
- The configured OAuth scope is `calendar.freebusy`. The local release demo still
  publishes through `FakeCalendarPublisher`; live event creation requires the
  broader `calendar.events` scope and may require Google verification.
- The deterministic parser supports simple act/scene headings and contextual
  character cues. Headerless screenplay transitions are inferred and may need
  editing before import. Arbitrary publisher-specific typography is not supported.
- PDF upload supports PDFs with embedded text. Scanned/image-only scripts require
  OCR before upload; the API reports this explicitly instead of returning an empty
  analysis.
- Ambiguous DST fallback local times are rejected and must be entered with an
  explicit timezone offset through an API client. Nonexistent spring-forward
  local times are also rejected.
- Rehearsal daily hours must start and end on the same civil date. Individual
  calendar event previews may cross midnight.
- Missing actor emails do not block scheduling or event creation, but those actors
  cannot receive calendar invitations.
- Google transport failures are reported per event; automatic retry and rollback
  are outside the MVP.
