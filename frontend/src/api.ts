export type ScheduleValidationPayload = {
  actors: { id: number; name: string }[]
  availability: {
    actor_id: number
    start: string
    end: string
    availability_type: string
  }[]
  scenes: {
    id: number
    scene_code: string
    target_rehearsal_minutes: number
  }[]
  sessions: {
    id: number
    scene_id: number
    scene_code: string
    actor_ids: number[]
    start: string
    end: string
    duration_minutes: number
  }[]
  timezone: string
  slot_duration_minutes: number
  minimum_session_minutes: number
}

export type ScheduleValidationResponse = {
  valid: boolean
  conflicts: { code: string; message: string }[]
  debts: {
    sceneCode: string
    requiredMinutes: number
    scheduledMinutes: number
    remainingMinutes: number
  }[]
}

export type ScriptAnalysis = {
  title: string
  scenes: {
    sceneCode: string
    title: string
    sourceHeader: string
    sourceLine: number
    characters: string[]
    dialogueCueCount: number
    stageDirectionCount: number
  }[]
  characterCandidates: { name: string; cueCount: number; accepted: boolean }[]
  warnings: { code: string; message: string; line: number }[]
}

export type ScriptUploadAnalysis = ScriptAnalysis & {
  fileName: string
  fileType: string
  extractedCharacterCount: number
}

export type CalendarPlanPayload = {
  sessions: {
    id: number
    scene_code: string
    start: string
    end: string
    called: { character_name: string; actor_name: string; email: string }[]
  }[]
  conflicts: string[]
  timezone: string
}

export type CalendarPreview = {
  sessionCount: number
  invitedActorCount: number
  dateRange: { start: string; end: string } | null
  conflictWarnings: string[]
  events: {
    sessionId: number
    title: string
    description: string
    start: string
    end: string
    attendeeEmails: string[]
  }[]
}

export type CalendarPublishReport = {
  publishedCount: number
  failedCount: number
  events: { sessionId: number; eventId: string; status: string }[]
}

export type CalendarStatus = {
  provider: string
  configured: boolean
  connected: boolean
  demoPublisherAvailable: boolean
  authUrl: string | null
  scope?: string
}

export type CalendarDiagnostic = {
  configured: boolean
  connected: boolean
  freeBusyReachable: boolean
  message: string
}

export type GoogleAvailabilityImport = {
  importedActorIds: number[]
  importedActorCount: number
  windowCount: number
  windows: {
    actorId: number
    start: string
    end: string
    availabilityType: 'AVAILABLE'
  }[]
  errors: { actorId: number; email: string; reason: string }[]
}

export async function validateSchedule(
  payload: ScheduleValidationPayload,
): Promise<ScheduleValidationResponse> {
  const response = await fetch('/api/schedules/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string
    } | null
    throw new Error(
      error?.detail ?? `validation request failed (${response.status})`,
    )
  }
  return (await response.json()) as ScheduleValidationResponse
}

export async function analyzeScript(text: string): Promise<ScriptAnalysis> {
  const response = await fetch('/api/scripts/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string
    } | null
    throw new Error(
      error?.detail ?? `script analysis failed (${response.status})`,
    )
  }
  return (await response.json()) as ScriptAnalysis
}

export function analyzeScriptFile(file: File): Promise<ScriptUploadAnalysis> {
  const body = new FormData()
  body.append('file', file)
  return jsonRequest('/api/scripts/upload', { method: 'POST', body })
}

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string
    } | null
    throw new Error(error?.detail ?? `request failed (${response.status})`)
  }
  return (await response.json()) as T
}

export function getCalendarStatus(): Promise<CalendarStatus> {
  return jsonRequest('/api/calendar/status')
}

export function diagnoseCalendarConnection(): Promise<CalendarDiagnostic> {
  return jsonRequest('/api/calendar/diagnostics')
}

export function importGoogleAvailability(payload: {
  actors: { id: number; email: string }[]
  start_date: string
  end_date: string
  daily_start_time: string
  daily_end_time: string
  timezone: string
}): Promise<GoogleAvailabilityImport> {
  return jsonRequest('/api/calendar/freebusy/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function previewCalendar(
  payload: CalendarPlanPayload,
): Promise<CalendarPreview> {
  return jsonRequest('/api/calendar/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function publishCalendar(
  payload: CalendarPlanPayload & {
    approved: boolean
    provider: 'fake' | 'google'
    access_token?: string
  },
): Promise<CalendarPublishReport> {
  return jsonRequest('/api/calendar/publish', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
