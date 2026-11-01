import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import './App.css'
import scheduleTemplateUrl from './assets/actor-schedule-template.csv?url'
import { effectiveWindows, matchGoogleWindows } from './availability'
import { BlockingTool } from './BlockingTool'
import {
  importActorSpreadsheet,
  type SpreadsheetImport,
  analyzeScript,
  analyzeScriptFile,
  type CalendarDiagnostic,
  type CalendarPlanPayload,
  type CalendarPreview,
  type CalendarPublishReport,
  type CalendarStatus,
  diagnoseCalendarConnection,
  getCalendarStatus,
  type GoogleAvailabilityImport,
  importGoogleAvailability,
  previewCalendar,
  publishCalendar,
  type ScriptAnalysis,
  type ScriptUploadAnalysis,
  validateSchedule,
} from './api'

const workflowSteps = [
  'SCRIPT',
  'CAST',
  'AVAILABILITY',
  'REQUIREMENTS',
  'SCHEDULE',
  'PUBLISH',
  'BLOCKING',
] as const

type WorkflowStep = (typeof workflowSteps)[number]

function workflowStepFromHash(): WorkflowStep | '' {
  const hash = window.location.hash.slice(1).toUpperCase()
  return workflowSteps.find((step) => step === hash) ?? ''
}

type Production = {
  name: string
  rehearsalStartDate: string
  rehearsalEndDate: string
  dailyStartTime: string
  dailyEndTime: string
  slotDurationMinutes: number
}

type Actor = {
  id: number
  name: string
  email: string
}

type Character = {
  id: number
  name: string
}

type Scene = {
  id: number
  sceneCode: string
  title: string
  priority: string
  targetRehearsalMinutes: number
}

type CastAssignment = {
  id: number
  actorId: number
  characterId: number
}

type SceneCharacter = {
  id: number
  sceneId: number
  characterId: number
  required: boolean
}

type Availability = {
  id: number
  actorId: number
  start: string
  end: string
  availabilityType: string
}

type PlanMode = 'efficient' | 'balanced' | 'scene_priority'

type ScheduleSession = {
  id: number
  sceneId: number
  sceneCode: string
  actorIds: number[]
  start: string
  end: string
  durationMinutes: number
}

type SceneDebt = {
  sceneCode: string
  requiredMinutes: number
  scheduledMinutes: number
  remainingMinutes: number
}

type SchedulePlan = {
  id: PlanMode
  label: string
  inputConflicts: string[]
  sessions: ScheduleSession[]
  debts: SceneDebt[]
  conflicts: string[]
  metrics: {
    days: number
    rehearsalHours: number
    actorIdleMinutes: number
    criticalCoverage: number
    debtCompleted: number
  }
}

function relativeDateInputValue(offsetDays: number) {
  const value = new Date()
  value.setDate(value.getDate() + offsetDays)
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const defaultProduction: Production = {
  name: '',
  rehearsalStartDate: relativeDateInputValue(0),
  rehearsalEndDate: relativeDateInputValue(14),
  dailyStartTime: '18:00',
  dailyEndTime: '22:00',
  slotDurationMinutes: 30,
}

const storedProductionKey = 'stage-scheduler-production'

function loadStoredProduction(): Production {
  try {
    const stored = localStorage.getItem(storedProductionKey)
    if (!stored) {
      return defaultProduction
    }
    const parsed = JSON.parse(stored) as Partial<Production>
    return {
      name: typeof parsed.name === 'string' ? parsed.name : '',
      rehearsalStartDate:
        typeof parsed.rehearsalStartDate === 'string' &&
        parsed.rehearsalStartDate
          ? parsed.rehearsalStartDate
          : defaultProduction.rehearsalStartDate,
      rehearsalEndDate:
        typeof parsed.rehearsalEndDate === 'string' && parsed.rehearsalEndDate
          ? parsed.rehearsalEndDate
          : defaultProduction.rehearsalEndDate,
      dailyStartTime:
        typeof parsed.dailyStartTime === 'string'
          ? parsed.dailyStartTime
          : defaultProduction.dailyStartTime,
      dailyEndTime:
        typeof parsed.dailyEndTime === 'string'
          ? parsed.dailyEndTime
          : defaultProduction.dailyEndTime,
      slotDurationMinutes:
        typeof parsed.slotDurationMinutes === 'number'
          ? parsed.slotDurationMinutes
          : defaultProduction.slotDurationMinutes,
    }
  } catch {
    return defaultProduction
  }
}

function App() {
  const actorNameInputRef = useRef<HTMLInputElement>(null)
  const [activeWorkflowStep, setActiveWorkflowStep] = useState<
    WorkflowStep | ''
  >(workflowStepFromHash)
  const [production, setProduction] = useState<Production>(loadStoredProduction)
  const [actors, setActors] = useState<Actor[]>([])
  const [characters, setCharacters] = useState<Character[]>([])
  const [scenes, setScenes] = useState<Scene[]>([])
  const [castAssignments, setCastAssignments] = useState<CastAssignment[]>([])
  const [sceneCharacters, setSceneCharacters] = useState<SceneCharacter[]>([])
  const [sheetPreview, setSheetPreview] = useState<SpreadsheetImport | null>(
    null,
  )
  const [sheetError, setSheetError] = useState('')
  const [sheetPending, setSheetPending] = useState(false)
  const [matchExisting, setMatchExisting] = useState(true)
  const [availability, setAvailability] = useState<Availability[]>([])
  const [schedulePlans, setSchedulePlans] = useState<SchedulePlan[]>([])
  const [selectedPlanId, setSelectedPlanId] = useState<PlanMode>('efficient')
  const [validationPending, setValidationPending] = useState(false)
  const [scriptText, setScriptText] = useState('')
  const [scriptAnalysis, setScriptAnalysis] = useState<ScriptAnalysis | null>(
    null,
  )
  const [scriptError, setScriptError] = useState('')
  const [scriptPending, setScriptPending] = useState(false)
  const [scriptUpload, setScriptUpload] = useState<ScriptUploadAnalysis | null>(
    null,
  )
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus | null>(
    null,
  )
  const [calendarDiagnostic, setCalendarDiagnostic] =
    useState<CalendarDiagnostic | null>(null)
  const [calendarDiagnosticPending, setCalendarDiagnosticPending] =
    useState(false)
  const [calendarApproved, setCalendarApproved] = useState(false)
  const [calendarPreview, setCalendarPreview] =
    useState<CalendarPreview | null>(null)
  const [publishReport, setPublishReport] =
    useState<CalendarPublishReport | null>(null)
  const [calendarError, setCalendarError] = useState('')
  const [calendarPending, setCalendarPending] = useState(false)
  const [availabilityImport, setAvailabilityImport] =
    useState<GoogleAvailabilityImport | null>(null)
  const [availabilityImportError, setAvailabilityImportError] = useState('')
  const [availabilityImportPending, setAvailabilityImportPending] =
    useState(false)
  const [manualSessionDraft, setManualSessionDraft] = useState({
    sceneId: '',
    start: '',
    durationMinutes: 60,
  })
  const [actorDraft, setActorDraft] = useState({ name: '', email: '' })
  const [characterDraft, setCharacterDraft] = useState({ name: '' })
  const [sceneDraft, setSceneDraft] = useState({
    sceneCode: '',
    title: '',
    priority: '2',
    targetRehearsalMinutes: 60,
  })
  const [assignmentDraft, setAssignmentDraft] = useState({
    actorId: '',
    characterId: '',
  })
  const [sceneCharacterDraft, setSceneCharacterDraft] = useState({
    sceneId: '',
    characterId: '',
    required: true,
  })
  const [availabilityDraft, setAvailabilityDraft] = useState({
    actorId: '',
    start: '',
    end: '',
    availabilityType: 'AVAILABLE',
  })

  const nextId = useMemo(
    () => ({
      actor: nextNumericId(actors),
      character: nextNumericId(characters),
      scene: nextNumericId(scenes),
      assignment: nextNumericId(castAssignments),
      sceneCharacter: nextNumericId(sceneCharacters),
      availability: nextNumericId(availability),
    }),
    [
      actors,
      availability,
      castAssignments,
      characters,
      sceneCharacters,
      scenes,
    ],
  )
  const selectedPlan =
    schedulePlans.find((plan) => plan.id === selectedPlanId) ?? schedulePlans[0]
  const actorEmailCount = actors.filter((actor) => actor.email).length
  const availabilityImportBlocker = !calendarStatus?.connected
    ? calendarStatus?.configured
      ? 'CONNECT GOOGLE CALENDAR TO IMPORT'
      : 'CALENDAR API NOT AVAILABLE'
    : !production.rehearsalStartDate || !production.rehearsalEndDate
      ? 'ENTER PRODUCTION START AND END DATES'
      : !production.dailyStartTime || !production.dailyEndTime
        ? 'ENTER DAILY START AND END TIMES'
        : actors.length === 0
          ? 'ADD ACTORS BEFORE IMPORTING'
          : actorEmailCount === 0
            ? 'ADD AT LEAST ONE ACTOR EMAIL'
            : ''

  useEffect(() => {
    const syncWorkflowStep = () => {
      setActiveWorkflowStep(workflowStepFromHash())
    }

    window.addEventListener('hashchange', syncWorkflowStep)
    return () => window.removeEventListener('hashchange', syncWorkflowStep)
  }, [])

  useEffect(() => {
    void getCalendarStatus()
      .then(setCalendarStatus)
      .catch((error: unknown) =>
        setCalendarError(
          error instanceof Error
            ? error.message
            : 'calendar status unavailable',
        ),
      )
  }, [])

  useEffect(() => {
    localStorage.setItem(storedProductionKey, JSON.stringify(production))
  }, [production])

  function saveProduction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    syncProductionForm(event.currentTarget)
  }

  function syncProductionForm(form: HTMLFormElement) {
    const formData = new FormData(form)
    setProduction({
      name: stringValue(formData, 'productionName'),
      rehearsalStartDate: stringValue(formData, 'rehearsalStartDate'),
      rehearsalEndDate: stringValue(formData, 'rehearsalEndDate'),
      dailyStartTime: stringValue(formData, 'dailyStartTime'),
      dailyEndTime: stringValue(formData, 'dailyEndTime'),
      slotDurationMinutes: numberValue(formData, 'slotDurationMinutes'),
    })
  }

  function loadDemoProduction() {
    setProduction({
      name: 'Hamlet Demo',
      rehearsalStartDate: '2026-07-14',
      rehearsalEndDate: '2026-07-18',
      dailyStartTime: '18:00',
      dailyEndTime: '22:00',
      slotDurationMinutes: 30,
    })
    setActors([
      { id: 1, name: 'Rina Feng', email: 'rina@example.com' },
      { id: 2, name: 'Maya Chen', email: 'maya@example.com' },
    ])
    setCharacters([
      { id: 1, name: 'Hamlet' },
      { id: 2, name: 'Ophelia' },
    ])
    setScenes([
      {
        id: 1,
        sceneCode: 'A1S1',
        title: 'Battlements',
        priority: '4',
        targetRehearsalMinutes: 120,
      },
      {
        id: 2,
        sceneCode: 'A1S2',
        title: 'The Court',
        priority: '3',
        targetRehearsalMinutes: 60,
      },
    ])
    setCastAssignments([
      { id: 1, characterId: 1, actorId: 1 },
      { id: 2, characterId: 2, actorId: 2 },
    ])
    setSceneCharacters([
      { id: 1, sceneId: 1, characterId: 1, required: true },
      { id: 2, sceneId: 1, characterId: 2, required: true },
      { id: 3, sceneId: 2, characterId: 1, required: true },
    ])
    setAvailability([
      {
        id: 1,
        actorId: 1,
        start: '2026-07-14T18:00',
        end: '2026-07-14T22:00',
        availabilityType: 'AVAILABLE',
      },
      {
        id: 2,
        actorId: 2,
        start: '2026-07-14T18:00',
        end: '2026-07-14T22:00',
        availabilityType: 'AVAILABLE',
      },
    ])
    setScriptText(
      'HAMLET\n\nACT I, SCENE I: Battlements\n\nHAMLET\nWho is there?\n\nOPHELIA\nMy lord, I have remembrances of yours.',
    )
    setSchedulePlans([])
    setCalendarApproved(false)
    setCalendarPreview(null)
    setPublishReport(null)
    setCalendarError('')
    setAvailabilityImport(null)
    setAvailabilityImportError('')
  }

  function addActor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!actorDraft.name.trim()) {
      return
    }
    setActors((current) => [
      ...current,
      {
        id: nextId.actor,
        name: actorDraft.name.trim(),
        email: actorDraft.email.trim(),
      },
    ])
    setActorDraft({ name: '', email: '' })
  }

  function addCharacter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!characterDraft.name.trim()) {
      return
    }
    setCharacters((current) => [
      ...current,
      { id: nextId.character, name: characterDraft.name.trim() },
    ])
    setCharacterDraft({ name: '' })
  }

  function addScene(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!sceneDraft.sceneCode.trim()) {
      return
    }
    setScenes((current) => [
      ...current,
      {
        id: nextId.scene,
        sceneCode: sceneDraft.sceneCode.trim().toUpperCase(),
        title: sceneDraft.title.trim(),
        priority: sceneDraft.priority,
        targetRehearsalMinutes: sceneDraft.targetRehearsalMinutes,
      },
    ])
    setSceneDraft({
      sceneCode: '',
      title: '',
      priority: '2',
      targetRehearsalMinutes: 60,
    })
  }

  async function runScriptAnalysis() {
    setScriptPending(true)
    setScriptError('')
    try {
      setScriptAnalysis(await analyzeScript(scriptText))
      setScriptUpload(null)
    } catch (error) {
      setScriptAnalysis(null)
      setScriptError(
        error instanceof Error ? error.message : 'script analysis failed',
      )
    } finally {
      setScriptPending(false)
    }
  }

  async function runScriptFileAnalysis(file: File) {
    setScriptPending(true)
    setScriptError('')
    try {
      const result = await analyzeScriptFile(file)
      setScriptUpload(result)
      setScriptAnalysis(result)
      setScriptError('FILE ANALYSIS READY // REVIEW BEFORE IMPORT')
    } catch (error) {
      setScriptUpload(null)
      setScriptAnalysis(null)
      setScriptError(
        error instanceof Error ? error.message : 'script upload failed',
      )
    } finally {
      setScriptPending(false)
    }
  }

  function updateAnalyzedScene(
    index: number,
    patch: Partial<ScriptAnalysis['scenes'][number]>,
  ) {
    setScriptAnalysis((current) =>
      current
        ? {
            ...current,
            scenes: current.scenes.map((scene, sceneIndex) =>
              sceneIndex === index ? { ...scene, ...patch } : scene,
            ),
          }
        : current,
    )
  }

  function confirmScriptImport() {
    if (!scriptAnalysis) {
      return
    }
    const importedCharacters = [...characters]
    const characterIdByName = new Map(
      importedCharacters.map((character) => [
        character.name.toLowerCase(),
        character.id,
      ]),
    )
    let characterId = nextNumericId(importedCharacters)
    for (const name of new Set(
      scriptAnalysis.scenes.flatMap((scene) => scene.characters),
    )) {
      if (!characterIdByName.has(name.toLowerCase())) {
        importedCharacters.push({ id: characterId, name })
        characterIdByName.set(name.toLowerCase(), characterId)
        characterId += 1
      }
    }

    const importedScenes = [...scenes]
    const sceneIdByCode = new Map(
      importedScenes.map((scene) => [scene.sceneCode.toUpperCase(), scene.id]),
    )
    let sceneId = nextNumericId(importedScenes)
    for (const parsed of scriptAnalysis.scenes) {
      const code = parsed.sceneCode.trim().toUpperCase()
      if (!sceneIdByCode.has(code)) {
        importedScenes.push({
          id: sceneId,
          sceneCode: code,
          title: parsed.title.trim(),
          priority: '2',
          targetRehearsalMinutes: 60,
        })
        sceneIdByCode.set(code, sceneId)
        sceneId += 1
      }
    }

    const importedRequirements = [...sceneCharacters]
    let requirementId = nextNumericId(importedRequirements)
    for (const parsed of scriptAnalysis.scenes) {
      const parsedSceneId = sceneIdByCode.get(
        parsed.sceneCode.trim().toUpperCase(),
      )
      for (const name of parsed.characters) {
        const parsedCharacterId = characterIdByName.get(name.toLowerCase())
        if (
          parsedSceneId &&
          parsedCharacterId &&
          !importedRequirements.some(
            (item) =>
              item.sceneId === parsedSceneId &&
              item.characterId === parsedCharacterId,
          )
        ) {
          importedRequirements.push({
            id: requirementId,
            sceneId: parsedSceneId,
            characterId: parsedCharacterId,
            required: true,
          })
          requirementId += 1
        }
      }
    }

    setCharacters(importedCharacters)
    setScenes(importedScenes)
    setSceneCharacters(importedRequirements)
    setScriptError('SCRIPT IMPORT CONFIRMED')
    actorNameInputRef.current?.focus()
  }

  function addCastAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!assignmentDraft.actorId || !assignmentDraft.characterId) {
      return
    }
    const actorId = Number(assignmentDraft.actorId)
    const characterId = Number(assignmentDraft.characterId)
    setCastAssignments((current) => [
      ...current.filter((assignment) => assignment.characterId !== characterId),
      { id: nextId.assignment, actorId, characterId },
    ])
    setAssignmentDraft({ actorId: '', characterId: '' })
  }

  function addSceneCharacter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!sceneCharacterDraft.sceneId || !sceneCharacterDraft.characterId) {
      return
    }
    setSceneCharacters((current) => [
      ...current,
      {
        id: nextId.sceneCharacter,
        sceneId: Number(sceneCharacterDraft.sceneId),
        characterId: Number(sceneCharacterDraft.characterId),
        required: sceneCharacterDraft.required,
      },
    ])
    setSceneCharacterDraft({ sceneId: '', characterId: '', required: true })
  }

  function addAvailability(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      !availabilityDraft.actorId ||
      !availabilityDraft.start ||
      !availabilityDraft.end
    ) {
      return
    }
    setAvailability((current) => [
      ...current,
      {
        id: nextId.availability,
        actorId: Number(availabilityDraft.actorId),
        start: availabilityDraft.start,
        end: availabilityDraft.end,
        availabilityType: availabilityDraft.availabilityType,
      },
    ])
    setAvailabilityDraft({
      actorId: '',
      start: '',
      end: '',
      availabilityType: 'AVAILABLE',
    })
  }

  async function previewSpreadsheet(file: File) {
    setSheetPending(true)
    setSheetPreview(null)
    setSheetError('')
    try {
      setSheetPreview(await importActorSpreadsheet(file, actors))
    } catch (error) {
      setSheetError(
        error instanceof Error ? error.message : 'Spreadsheet import failed',
      )
    } finally {
      setSheetPending(false)
    }
  }

  function applySpreadsheet() {
    if (!sheetPreview) return
    if (
      sheetPreview.windows.some(
        (window) => !actors.some((actor) => actor.id === window.actorId),
      )
    ) {
      setSheetError('Cast changed. Upload the spreadsheet again.')
      setSheetPreview(null)
      return
    }
    setAvailability((current) => {
      let id = nextNumericId(current)
      return [
        ...current,
        ...sheetPreview.windows
          .filter(
            (window) =>
              !current.some(
                (item) =>
                  item.actorId === window.actorId &&
                  item.start === window.start &&
                  item.end === window.end &&
                  item.availabilityType === window.availabilityType,
              ),
          )
          .map((window) => ({ ...window, id: id++ })),
      ]
    })
    setSheetPreview(null)
    invalidateImportedSchedule()
  }

  function invalidateImportedSchedule() {
    setSchedulePlans([])
    setCalendarApproved(false)
    setCalendarPreview(null)
    setPublishReport(null)
  }

  async function replaceAvailabilityFromGoogle() {
    if (
      !production.rehearsalStartDate ||
      !production.rehearsalEndDate ||
      !production.dailyStartTime ||
      !production.dailyEndTime
    ) {
      setAvailabilityImportError('ENTER PRODUCTION DATES AND DAILY HOURS FIRST')
      return
    }
    setAvailabilityImportPending(true)
    setAvailabilityImportError('')
    try {
      const result = await importGoogleAvailability({
        actors: actors.map(({ id, email }) => ({ id, email })),
        start_date: production.rehearsalStartDate,
        end_date: production.rehearsalEndDate,
        daily_start_time: production.dailyStartTime,
        daily_end_time: production.dailyEndTime,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      })
      const importedActorIds = new Set(result.importedActorIds)
      setAvailability((current) => {
        if (matchExisting) {
          return matchGoogleWindows(
            current,
            result.windows,
            result.importedActorIds,
            `${production.rehearsalStartDate}T${production.dailyStartTime}`,
            `${production.rehearsalEndDate}T${production.dailyEndTime}`,
          ).map((window, index) => ({ ...window, id: index + 1 }))
        }
        const retained = current.filter(
          (window) => !importedActorIds.has(window.actorId),
        )
        let id = nextNumericId(retained)
        return [
          ...retained,
          ...result.windows.map((window) => ({
            id: id++,
            actorId: window.actorId,
            start: window.start,
            end: window.end,
            availabilityType: window.availabilityType,
          })),
        ]
      })
      invalidateImportedSchedule()
      setAvailabilityImport(result)
    } catch (error) {
      setAvailabilityImport(null)
      setAvailabilityImportError(
        error instanceof Error
          ? error.message
          : 'Google availability import failed',
      )
    } finally {
      setAvailabilityImportPending(false)
    }
  }

  async function verifyGoogleConnection() {
    setCalendarDiagnosticPending(true)
    setCalendarDiagnostic(null)
    try {
      setCalendarDiagnostic(await diagnoseCalendarConnection())
    } catch (error) {
      setCalendarDiagnostic({
        configured: Boolean(calendarStatus?.configured),
        connected: false,
        freeBusyReachable: false,
        message:
          error instanceof Error
            ? error.message
            : 'Google connection test failed',
      })
    } finally {
      setCalendarDiagnosticPending(false)
    }
  }

  async function generateSchedulePlans() {
    const plans = buildSchedulePlans({
      actors,
      availability,
      castAssignments,
      sceneCharacters,
      scenes,
    })
    setSchedulePlans(
      plans.map((plan) => ({
        ...plan,
        conflicts: ['VALIDATING WITH PYTHON...'],
      })),
    )
    setSelectedPlanId(plans[0]?.id ?? 'efficient')
    setValidationPending(true)
    const validated = await Promise.all(plans.map((plan) => validatePlan(plan)))
    setSchedulePlans(validated)
    setValidationPending(false)
  }

  async function updateSelectedPlanSessions(
    updater: (sessions: ScheduleSession[]) => ScheduleSession[],
  ) {
    if (!selectedPlan) {
      return
    }
    const sessions = updater(selectedPlan.sessions).sort((left, right) =>
      left.start.localeCompare(right.start),
    )
    const pendingPlan = {
      ...selectedPlan,
      sessions,
      conflicts: ['VALIDATING WITH PYTHON...'],
      metrics: calculatePlanMetrics(scenes, sessions),
    }
    setSchedulePlans((current) =>
      current.map((plan) => (plan.id === selectedPlanId ? pendingPlan : plan)),
    )
    setValidationPending(true)
    const validated = await validatePlan(pendingPlan)
    setSchedulePlans((current) =>
      current.map((plan) => (plan.id === selectedPlanId ? validated : plan)),
    )
    setValidationPending(false)
  }

  async function validatePlan(plan: SchedulePlan): Promise<SchedulePlan> {
    try {
      const result = await validateSchedule({
        actors: actors.map(({ id, name }) => ({ id, name })),
        availability: availability.map((window) => ({
          actor_id: window.actorId,
          start: window.start,
          end: window.end,
          availability_type: window.availabilityType,
        })),
        scenes: scenes.map((scene) => ({
          id: scene.id,
          scene_code: scene.sceneCode,
          target_rehearsal_minutes: scene.targetRehearsalMinutes,
        })),
        sessions: plan.sessions.map((session) => ({
          id: session.id,
          scene_id: session.sceneId,
          scene_code: session.sceneCode,
          actor_ids: session.actorIds,
          start: session.start,
          end: session.end,
          duration_minutes: session.durationMinutes,
        })),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        slot_duration_minutes: production.slotDurationMinutes,
        minimum_session_minutes: 60,
      })
      return {
        ...plan,
        debts: result.debts,
        conflicts: [
          ...plan.inputConflicts,
          ...result.conflicts.map((conflict) => conflict.message),
        ],
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'unknown error'
      return { ...plan, conflicts: [`VALIDATION API ERROR: ${message}`] }
    }
  }

  function moveSession(sessionId: number, start: string) {
    void updateSelectedPlanSessions((sessions) =>
      sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              start,
              end: toLocalInputValue(
                addMinutes(
                  parseLocalInputValue(start),
                  session.durationMinutes,
                ),
              ),
            }
          : session,
      ),
    )
  }

  function changeSessionDuration(sessionId: number, durationMinutes: number) {
    void updateSelectedPlanSessions((sessions) =>
      sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              durationMinutes,
              end: toLocalInputValue(
                addMinutes(
                  parseLocalInputValue(session.start),
                  durationMinutes,
                ),
              ),
            }
          : session,
      ),
    )
  }

  function deleteSession(sessionId: number) {
    void updateSelectedPlanSessions((sessions) =>
      sessions.filter((session) => session.id !== sessionId),
    )
  }

  function addManualSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const scene = scenes.find(
      (item) => item.id === Number(manualSessionDraft.sceneId),
    )
    if (!scene || !manualSessionDraft.start) {
      return
    }

    const durationMinutes = manualSessionDraft.durationMinutes
    const actorIds = requiredActorIdsForScene(scene, {
      castAssignments,
      sceneCharacters,
    })
    const nextSessionId =
      Math.max(
        0,
        ...(selectedPlan?.sessions.map((session) => session.id) ?? []),
      ) + 1
    const start = manualSessionDraft.start
    const end = toLocalInputValue(
      addMinutes(parseLocalInputValue(start), durationMinutes),
    )

    void updateSelectedPlanSessions((sessions) => [
      ...sessions,
      {
        id: nextSessionId,
        sceneId: scene.id,
        sceneCode: scene.sceneCode,
        actorIds,
        start,
        end,
        durationMinutes,
      },
    ])
    setManualSessionDraft({ sceneId: '', start: '', durationMinutes: 60 })
  }

  function calendarPlanPayload(): CalendarPlanPayload | null {
    if (!selectedPlan) {
      return null
    }
    return {
      sessions: selectedPlan.sessions.map((session) => ({
        id: session.id,
        scene_code: session.sceneCode,
        start: session.start,
        end: session.end,
        called: calledActorsForSession(session, {
          actors,
          castAssignments,
          characters,
          sceneCharacters,
        }),
      })),
      conflicts: selectedPlan.conflicts,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }
  }

  async function previewApprovedPlan() {
    const payload = calendarPlanPayload()
    if (!payload) {
      return
    }
    setCalendarPending(true)
    setCalendarError('')
    setPublishReport(null)
    try {
      setCalendarPreview(await previewCalendar(payload))
    } catch (error) {
      setCalendarError(
        error instanceof Error ? error.message : 'calendar preview failed',
      )
    } finally {
      setCalendarPending(false)
    }
  }

  async function publishApprovedPlan() {
    const payload = calendarPlanPayload()
    if (!payload) {
      return
    }
    setCalendarPending(true)
    setCalendarError('')
    try {
      setPublishReport(
        await publishCalendar({
          ...payload,
          approved: calendarApproved,
          provider: 'fake',
        }),
      )
    } catch (error) {
      setCalendarError(
        error instanceof Error ? error.message : 'calendar publish failed',
      )
    } finally {
      setCalendarPending(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <h1>STAGE SCHEDULER</h1>
      </header>

      <nav className="workflow" aria-label="Production workflow">
        {workflowSteps.map((step, index) => (
          <a
            aria-current={activeWorkflowStep === step ? 'step' : undefined}
            className="workflow-step"
            href={`#${step.toLowerCase()}`}
            key={step}
            onClick={() => setActiveWorkflowStep(step)}
          >
            {String(index + 1).padStart(2, '0')} {step}
          </a>
        ))}
      </nav>

      <section
        className="panel"
        id="production"
        aria-labelledby="production-heading"
      >
        <h2 id="production-heading">CREATE PRODUCTION</h2>
        <button
          className="demo-button"
          type="button"
          onClick={loadDemoProduction}
        >
          [ LOAD DEMO PRODUCTION ]
        </button>
        <form
          className="grid-form"
          onInput={(event) => syncProductionForm(event.currentTarget)}
          onSubmit={saveProduction}
        >
          <label>
            NAME
            <input
              name="productionName"
              type="text"
              value={production.name}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            START DATE
            <input
              name="rehearsalStartDate"
              type="date"
              value={production.rehearsalStartDate}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  rehearsalStartDate: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            END DATE
            <input
              name="rehearsalEndDate"
              type="date"
              value={production.rehearsalEndDate}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  rehearsalEndDate: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            DAILY START
            <input
              name="dailyStartTime"
              type="time"
              value={production.dailyStartTime}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  dailyStartTime: event.target.value,
                }))
              }
            />
          </label>
          <label>
            DAILY END
            <input
              name="dailyEndTime"
              type="time"
              value={production.dailyEndTime}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  dailyEndTime: event.target.value,
                }))
              }
            />
          </label>
          <label>
            SLOT MINUTES
            <input
              min="5"
              name="slotDurationMinutes"
              step="5"
              type="number"
              value={production.slotDurationMinutes}
              onChange={(event) =>
                setProduction((current) => ({
                  ...current,
                  slotDurationMinutes: Number(event.target.value),
                }))
              }
            />
          </label>
          <button type="submit">[ SAVE PRODUCTION ]</button>
        </form>
        <SummaryRow
          label="CURRENT"
          value={production.name || 'NO PRODUCTION SAVED'}
        />
      </section>

      <section className="panel" id="cast" aria-labelledby="cast-heading">
        <h2 id="cast-heading">ACTORS + CHARACTERS</h2>
        {scriptError === 'SCRIPT IMPORT CONFIRMED' && (
          <div className="workflow-action" role="status">
            <p className="status-message">
              CHARACTERS IMPORTED // ADD ACTORS AND ASSIGN ROLES
            </p>
            <a className="text-link" href="#cast">
              [ ADD FIRST ACTOR ]
            </a>
          </div>
        )}
        <div className="two-column">
          <form className="stack-form" onSubmit={addActor}>
            <label>
              ACTOR NAME
              <input
                aria-label="Actor name"
                ref={actorNameInputRef}
                value={actorDraft.name}
                onChange={(event) =>
                  setActorDraft((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                required
              />
            </label>
            <label>
              ACTOR EMAIL
              <input
                aria-label="Actor email"
                type="email"
                value={actorDraft.email}
                onChange={(event) =>
                  setActorDraft((current) => ({
                    ...current,
                    email: event.target.value,
                  }))
                }
              />
            </label>
            <button type="submit">[ ADD ACTOR ]</button>
          </form>

          <form className="stack-form" onSubmit={addCharacter}>
            <label>
              CHARACTER NAME
              <input
                aria-label="Character name"
                value={characterDraft.name}
                onChange={(event) =>
                  setCharacterDraft({ name: event.target.value })
                }
                required
              />
            </label>
            <button type="submit">[ ADD CHARACTER ]</button>
          </form>
        </div>

        <div className="two-column">
          <DataTable
            emptyMessage="NO ACTORS"
            headers={['ACTOR', 'EMAIL']}
            rows={actors.map((actor) => [
              actor.name,
              actor.email || 'NO EMAIL',
            ])}
          />
          <DataTable
            emptyMessage="NO CHARACTERS"
            headers={['CHARACTER']}
            rows={characters.map((character) => [character.name])}
          />
        </div>

        <form className="inline-form" onSubmit={addCastAssignment}>
          <SelectField
            label="CHARACTER"
            value={assignmentDraft.characterId}
            onChange={(value) =>
              setAssignmentDraft((current) => ({
                ...current,
                characterId: value,
              }))
            }
            options={characters.map((character) => ({
              label: character.name,
              value: String(character.id),
            }))}
          />
          <SelectField
            label="ACTOR"
            value={assignmentDraft.actorId}
            onChange={(value) =>
              setAssignmentDraft((current) => ({ ...current, actorId: value }))
            }
            options={actors.map((actor) => ({
              label: actor.name,
              value: String(actor.id),
            }))}
          />
          <button type="submit">[ ASSIGN CHARACTER ]</button>
        </form>
        <DataTable
          emptyMessage="NO CAST ASSIGNMENTS"
          headers={['CHARACTER', 'ACTOR']}
          rows={castAssignments.map((assignment) => [
            characterName(characters, assignment.characterId),
            actorName(actors, assignment.actorId),
          ])}
        />
      </section>

      <section className="panel" id="script" aria-labelledby="script-heading">
        <h2 id="script-heading">SCRIPT ANALYSIS</h2>
        <div className="file-import">
          <label>
            SCRIPT FILE // TXT PDF SCRIPT FOUNTAIN MD
            <input
              aria-label="Script file"
              accept=".txt,.text,.script,.fountain,.md,.pdf,text/plain,application/pdf"
              disabled={scriptPending}
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  void runScriptFileAnalysis(file)
                }
                event.target.value = ''
              }}
            />
          </label>
        </div>
        <div className="section-label paste-label">OR PASTE TEXT</div>
        <div className="script-analysis-input">
          <label>
            SCRIPT TEXT
            <textarea
              aria-label="Script text"
              rows={12}
              value={scriptText}
              onChange={(event) => setScriptText(event.target.value)}
              placeholder="ACT I, SCENE I..."
            />
          </label>
          <button
            type="button"
            disabled={scriptPending || !scriptText.trim()}
            onClick={() => void runScriptAnalysis()}
          >
            {scriptPending ? '[ ANALYZING... ]' : '[ ANALYZE SCRIPT ]'}
          </button>
        </div>
        {scriptError && <p className="status-message">{scriptError}</p>}
        {scriptUpload && (
          <div className="upload-summary" aria-label="Uploaded script summary">
            <SummaryRow label="FILE" value={scriptUpload.fileName} />
            <SummaryRow label="TYPE" value={scriptUpload.fileType} />
            <SummaryRow
              label="EXTRACTED CHARACTERS"
              value={String(scriptUpload.extractedCharacterCount)}
            />
            <SummaryRow
              label="DETECTED SCENES"
              value={String(scriptUpload.scenes.length)}
            />
            <SummaryRow
              label="CHARACTER CANDIDATES"
              value={String(scriptUpload.characterCandidates.length)}
            />
          </div>
        )}
        {scriptAnalysis && (
          <div className="script-review" aria-label="Script analysis review">
            <div className="section-label">
              DETECTED // REVIEW BEFORE IMPORT
            </div>
            {scriptAnalysis.scenes.map((scene, index) => (
              <article
                className="detected-scene"
                key={`${scene.sceneCode}-${index}`}
              >
                <label>
                  SCENE CODE
                  <input
                    aria-label={`Detected scene code ${index + 1}`}
                    value={scene.sceneCode}
                    onChange={(event) =>
                      updateAnalyzedScene(index, {
                        sceneCode: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  TITLE
                  <input
                    aria-label={`Detected scene title ${index + 1}`}
                    value={scene.title}
                    onChange={(event) =>
                      updateAnalyzedScene(index, { title: event.target.value })
                    }
                  />
                </label>
                <label>
                  DETECTED CHARACTERS
                  <input
                    aria-label={`Detected characters ${index + 1}`}
                    value={scene.characters.join(', ')}
                    onChange={(event) =>
                      updateAnalyzedScene(index, {
                        characters: event.target.value
                          .split(',')
                          .map((value) => value.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <span>{`${scene.dialogueCueCount} CUES // ${scene.stageDirectionCount} DIRECTIONS // LINE ${scene.sourceLine}`}</span>
              </article>
            ))}
            {scriptAnalysis.warnings.length > 0 && (
              <ul className="conflict-list">
                {scriptAnalysis.warnings.map((warning) => (
                  <li
                    key={`${warning.code}-${warning.line}`}
                  >{`LINE ${warning.line}: ${warning.message}`}</li>
                ))}
              </ul>
            )}
            <h3 className="candidate-label">CHARACTER CANDIDATES</h3>
            <DataTable
              emptyMessage="NO CHARACTER CANDIDATES"
              headers={['CHARACTER', 'CUES', 'STATUS']}
              rows={scriptAnalysis.characterCandidates.map((candidate) => [
                candidate.name,
                String(candidate.cueCount),
                candidate.accepted ? 'DETECTED' : 'REVIEW',
              ])}
            />
            <button type="button" onClick={confirmScriptImport}>
              [ CONFIRM IMPORT ]
            </button>
          </div>
        )}

        <h2 className="subsection-heading">MANUAL SCENE TABLE</h2>
        <form className="grid-form" onSubmit={addScene}>
          <label>
            SCENE CODE
            <input
              aria-label="Scene code"
              value={sceneDraft.sceneCode}
              onChange={(event) =>
                setSceneDraft((current) => ({
                  ...current,
                  sceneCode: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            TITLE
            <input
              aria-label="Scene title"
              value={sceneDraft.title}
              onChange={(event) =>
                setSceneDraft((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
            />
          </label>
          <label>
            PRIORITY
            <select
              aria-label="Scene priority"
              value={sceneDraft.priority}
              onChange={(event) =>
                setSceneDraft((current) => ({
                  ...current,
                  priority: event.target.value,
                }))
              }
            >
              <option value="1">1 LOW</option>
              <option value="2">2 NORMAL</option>
              <option value="3">3 HIGH</option>
              <option value="4">4 CRITICAL</option>
            </select>
          </label>
          <label>
            TARGET MINUTES
            <input
              aria-label="Target rehearsal minutes"
              min="0"
              step="30"
              type="number"
              value={sceneDraft.targetRehearsalMinutes}
              onChange={(event) =>
                setSceneDraft((current) => ({
                  ...current,
                  targetRehearsalMinutes: Number(event.target.value),
                }))
              }
            />
          </label>
          <button type="submit">[ ADD SCENE ]</button>
        </form>
        <DataTable
          emptyMessage="NO SCENES"
          headers={['SCENE', 'TITLE', 'PRIORITY', 'TARGET']}
          rows={scenes.map((scene) => [
            scene.sceneCode,
            scene.title || 'UNTITLED',
            scene.priority,
            `${scene.targetRehearsalMinutes} MIN`,
          ])}
        />
      </section>

      <section
        className="panel"
        id="requirements"
        aria-labelledby="requirements-heading"
      >
        <h2 id="requirements-heading">ASSIGN CHARACTERS TO SCENES</h2>
        <form className="inline-form" onSubmit={addSceneCharacter}>
          <SelectField
            label="SCENE"
            value={sceneCharacterDraft.sceneId}
            onChange={(value) =>
              setSceneCharacterDraft((current) => ({
                ...current,
                sceneId: value,
              }))
            }
            options={scenes.map((scene) => ({
              label: scene.sceneCode,
              value: String(scene.id),
            }))}
          />
          <SelectField
            label="CHARACTER"
            value={sceneCharacterDraft.characterId}
            onChange={(value) =>
              setSceneCharacterDraft((current) => ({
                ...current,
                characterId: value,
              }))
            }
            options={characters.map((character) => ({
              label: character.name,
              value: String(character.id),
            }))}
          />
          <label className="checkbox-label">
            <input
              checked={sceneCharacterDraft.required}
              type="checkbox"
              onChange={(event) =>
                setSceneCharacterDraft((current) => ({
                  ...current,
                  required: event.target.checked,
                }))
              }
            />
            REQUIRED
          </label>
          <button type="submit">[ ADD REQUIREMENT ]</button>
        </form>
        <DataTable
          emptyMessage="NO REQUIREMENTS"
          headers={['SCENE', 'CHARACTER', 'CALL']}
          rows={sceneCharacters.map((requirement) => [
            sceneCode(scenes, requirement.sceneId),
            characterName(characters, requirement.characterId),
            requirement.required ? 'REQUIRED' : 'OPTIONAL',
          ])}
        />
      </section>

      <section
        className="panel"
        id="availability"
        aria-labelledby="availability-heading"
      >
        <h2 id="availability-heading">ACTOR WINDOWS</h2>
        <div className="availability-sync">
          <h3>IMPORT ACTOR SPREADSHEETS</h3>
          <p>
            Upload .xlsx or .csv with actor (exact cast name), email, or
            actor_id; start; end; and optional type (AVAILABLE, BUSY,
            PREFERRED). Use ISO dates and times, or a date column with start/end
            times. Times use your browser timezone.
          </p>
          <a href={scheduleTemplateUrl} download>
            Download schedule template
          </a>
          <label>
            Actor schedule file
            <input
              type="file"
              accept=".xlsx,.csv"
              disabled={
                !actors.length || sheetPending || availabilityImportPending
              }
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void previewSpreadsheet(file)
                event.target.value = ''
              }}
            />
          </label>
          {sheetPending && <p role="status">Reading actor schedules…</p>}
          {sheetError && <p role="alert">{sheetError}</p>}
          {sheetPreview && (
            <div>
              <p>
                {sheetPreview.windowCount} windows matched. Review before
                adding; existing windows are kept. Import spreadsheets before
                matching Google.
              </p>
              <div style={{ maxHeight: '18rem', overflow: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Actor</th>
                      <th>Type</th>
                      <th>Start</th>
                      <th>End</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sheetPreview.windows.map((window, index) => (
                      <tr key={index}>
                        <td>
                          {
                            actors.find((actor) => actor.id === window.actorId)
                              ?.name
                          }
                        </td>
                        <td>{window.availabilityType}</td>
                        <td>{window.start}</td>
                        <td>{window.end}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button
                type="button"
                disabled={availabilityImportPending}
                onClick={applySpreadsheet}
              >
                [ ADD IMPORTED WINDOWS ]
              </button>
              <button type="button" onClick={() => setSheetPreview(null)}>
                [ CANCEL IMPORT ]
              </button>
            </div>
          )}
          <label>
            <input
              type="checkbox"
              checked={matchExisting}
              disabled={availabilityImportPending}
              onChange={(event) => setMatchExisting(event.target.checked)}
            />{' '}
            Match Google with existing actor windows
          </label>
          <p>
            Matching keeps only times allowed by both sources. Busy windows
            always block rehearsal. Actors without available windows use Google
            free time; inaccessible calendars keep their existing windows.
          </p>
          <div className="metrics-grid">
            <SummaryRow
              label="GOOGLE FREE/BUSY"
              value={
                calendarStatus?.connected
                  ? 'CONNECTED'
                  : calendarStatus?.configured
                    ? 'AUTH READY'
                    : 'NOT CONFIGURED'
              }
            />
            <SummaryRow
              label="ACTORS WITH EMAIL"
              value={`${actorEmailCount} / ${actors.length}`}
            />
          </div>
          <div className="publish-actions">
            {!calendarStatus?.connected && calendarStatus?.authUrl && (
              <a className="text-link" href={calendarStatus.authUrl}>
                [ CONNECT GOOGLE CALENDAR ]
              </a>
            )}
            <button
              type="button"
              disabled={
                !calendarStatus?.configured || calendarDiagnosticPending
              }
              onClick={() => void verifyGoogleConnection()}
            >
              {calendarDiagnosticPending
                ? '[ TESTING GOOGLE CONNECTION... ]'
                : '[ TEST GOOGLE CONNECTION ]'}
            </button>
            <button
              type="button"
              disabled={
                Boolean(availabilityImportBlocker) || availabilityImportPending
              }
              onClick={() => void replaceAvailabilityFromGoogle()}
            >
              {availabilityImportPending
                ? '[ IMPORTING GOOGLE AVAILABILITY... ]'
                : matchExisting
                  ? '[ MATCH WITH GOOGLE AVAILABILITY ]'
                  : '[ REPLACE WITH GOOGLE AVAILABILITY ]'}
            </button>
          </div>
          {calendarDiagnostic && (
            <p
              className={`status-message ${
                calendarDiagnostic.freeBusyReachable ? '' : 'warning-text'
              }`}
            >
              {calendarDiagnostic.freeBusyReachable
                ? 'GOOGLE CONNECTION TEST // READY'
                : `GOOGLE CONNECTION TEST // ${calendarDiagnostic.message.toUpperCase()}`}
            </p>
          )}
          {availabilityImportBlocker && (
            <p className="status-message warning-text">
              {`IMPORT BLOCKED // ${availabilityImportBlocker}`}
            </p>
          )}
          {availabilityImport && (
            <p className="status-message">
              {`GOOGLE IMPORT // ${availabilityImport.importedActorCount} ACTORS // ${availabilityImport.windowCount} WINDOWS`}
            </p>
          )}
          {availabilityImport?.errors.length ? (
            <>
              <ul className="import-errors" aria-label="Google import errors">
                {availabilityImport.errors.map((error) => (
                  <li key={`${error.actorId}-${error.reason}`}>
                    {`${actorName(actors, error.actorId)} // ${calendarImportReason(error.reason)}`}
                  </li>
                ))}
              </ul>
              {availabilityImport.errors.some((error) =>
                ['FORBIDDEN', 'NOTFOUND'].includes(error.reason),
              ) && (
                <a
                  className="text-link"
                  href="https://support.google.com/calendar/answer/37082"
                  rel="noreferrer"
                  target="_blank"
                >
                  [ GOOGLE CALENDAR SHARING HELP ]
                </a>
              )}
            </>
          ) : null}
          {availabilityImportError && (
            <p className="status-message warning-text">
              {availabilityImportError}
            </p>
          )}
        </div>
        {actors.length === 0 && (
          <div className="workflow-action">
            <p className="status-message">NO ACTORS AVAILABLE</p>
            <a className="text-link" href="#cast">
              [ ADD ACTORS IN CAST ]
            </a>
          </div>
        )}
        <form className="grid-form" onSubmit={addAvailability}>
          <SelectField
            label="ACTOR"
            disabled={actors.length === 0}
            emptyLabel={actors.length === 0 ? 'NO ACTORS ADDED' : 'SELECT'}
            value={availabilityDraft.actorId}
            onChange={(value) =>
              setAvailabilityDraft((current) => ({
                ...current,
                actorId: value,
              }))
            }
            options={actors.map((actor) => ({
              label: actor.name,
              value: String(actor.id),
            }))}
          />
          <label>
            START
            <input
              aria-label="Availability start"
              type="datetime-local"
              value={availabilityDraft.start}
              onChange={(event) =>
                setAvailabilityDraft((current) => ({
                  ...current,
                  start: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            END
            <input
              aria-label="Availability end"
              type="datetime-local"
              value={availabilityDraft.end}
              onChange={(event) =>
                setAvailabilityDraft((current) => ({
                  ...current,
                  end: event.target.value,
                }))
              }
              required
            />
          </label>
          <label>
            TYPE
            <select
              aria-label="Availability type"
              value={availabilityDraft.availabilityType}
              onChange={(event) =>
                setAvailabilityDraft((current) => ({
                  ...current,
                  availabilityType: event.target.value,
                }))
              }
            >
              <option>AVAILABLE</option>
              <option>BUSY</option>
              <option>PREFERRED</option>
            </select>
          </label>
          <button type="submit">[ ADD AVAILABILITY ]</button>
        </form>
        <DataTable
          emptyMessage="NO AVAILABILITY"
          headers={['ACTOR', 'TYPE', 'START', 'END']}
          rows={availability.map((window) => [
            actorName(actors, window.actorId),
            window.availabilityType,
            window.start,
            window.end,
          ])}
        />
      </section>

      <section
        className="panel"
        id="schedule"
        aria-labelledby="schedule-heading"
      >
        <h2 id="schedule-heading">GENERATE SCHEDULE OPTIONS</h2>
        <div className="metrics-grid">
          <SummaryRow label="PRODUCTION" value={production.name || 'MISSING'} />
          <SummaryRow label="ACTORS" value={String(actors.length)} />
          <SummaryRow label="CHARACTERS" value={String(characters.length)} />
          <SummaryRow label="SCENES" value={String(scenes.length)} />
          <SummaryRow
            label="CAST ASSIGNMENTS"
            value={String(castAssignments.length)}
          />
          <SummaryRow
            label="SCENE REQUIREMENTS"
            value={String(sceneCharacters.length)}
          />
          <SummaryRow
            label="AVAILABILITY WINDOWS"
            value={String(availability.length)}
          />
        </div>
        <button type="button" onClick={() => void generateSchedulePlans()}>
          [ GENERATE SCHEDULE ]
        </button>

        {schedulePlans.length > 0 && (
          <div className="schedule-workspace">
            <div className="plan-grid" aria-label="Generated schedule plans">
              {schedulePlans.map((plan, index) => (
                <article className="plan-card" key={plan.id}>
                  <h3>{`PLAN ${String.fromCharCode(65 + index)} // ${plan.label}`}</h3>
                  <dl className="plan-metrics">
                    <div>
                      <dt>DAYS</dt>
                      <dd>{plan.metrics.days}</dd>
                    </div>
                    <div>
                      <dt>REHEARSAL HOURS</dt>
                      <dd>{plan.metrics.rehearsalHours.toFixed(1)}</dd>
                    </div>
                    <div>
                      <dt>ACTOR IDLE MINUTES</dt>
                      <dd>{plan.metrics.actorIdleMinutes}</dd>
                    </div>
                    <div>
                      <dt>CRITICAL COVERAGE</dt>
                      <dd>{`${plan.metrics.criticalCoverage}%`}</dd>
                    </div>
                    <div>
                      <dt>DEBT COMPLETED</dt>
                      <dd>{`${plan.metrics.debtCompleted}%`}</dd>
                    </div>
                  </dl>
                  <button
                    type="button"
                    aria-pressed={selectedPlan?.id === plan.id}
                    onClick={() => setSelectedPlanId(plan.id)}
                  >
                    [ REVIEW PLAN ]
                  </button>
                </article>
              ))}
            </div>

            <section aria-labelledby="metrics-table-heading">
              <h3 id="metrics-table-heading">PLAN COMPARISON</h3>
              <DataTable
                emptyMessage="NO PLANS"
                headers={['PLAN', 'DAYS', 'HOURS', 'IDLE', 'CRITICAL', 'DEBT']}
                rows={schedulePlans.map((plan) => [
                  plan.label,
                  String(plan.metrics.days),
                  plan.metrics.rehearsalHours.toFixed(1),
                  `${plan.metrics.actorIdleMinutes} MIN`,
                  `${plan.metrics.criticalCoverage}%`,
                  `${plan.metrics.debtCompleted}%`,
                ])}
              />
            </section>

            {selectedPlan && (
              <div className="schedule-detail">
                <section aria-labelledby="timeline-heading">
                  <h3 id="timeline-heading">
                    DAILY TIMELINE: {selectedPlan.label}
                  </h3>
                  <Timeline
                    actors={actors}
                    emptyMessage="NO SESSIONS GENERATED"
                    sessions={selectedPlan.sessions}
                  />
                </section>

                <section aria-labelledby="manual-edit-heading">
                  <h3 id="manual-edit-heading">OVERRIDE + REVALIDATE</h3>
                  <div className="edit-session-list">
                    {selectedPlan.sessions.length === 0 ? (
                      <p>NO SESSIONS TO EDIT</p>
                    ) : (
                      selectedPlan.sessions.map((session) => (
                        <div className="edit-session-row" key={session.id}>
                          <strong>{session.sceneCode}</strong>
                          <label>
                            START
                            <input
                              aria-label={`Move ${session.sceneCode} start`}
                              type="datetime-local"
                              value={session.start}
                              onChange={(event) =>
                                moveSession(session.id, event.target.value)
                              }
                            />
                          </label>
                          <label>
                            DURATION
                            <input
                              aria-label={`Change ${session.sceneCode} duration`}
                              min="0"
                              step="30"
                              type="number"
                              value={session.durationMinutes}
                              onChange={(event) =>
                                changeSessionDuration(
                                  session.id,
                                  Number(event.target.value),
                                )
                              }
                            />
                          </label>
                          <button
                            type="button"
                            onClick={() => deleteSession(session.id)}
                          >
                            {`[ DELETE ${session.sceneCode} ]`}
                          </button>
                        </div>
                      ))
                    )}
                  </div>

                  <form
                    className="manual-session-form"
                    onSubmit={addManualSession}
                  >
                    <SelectField
                      label="MANUAL SCENE"
                      value={manualSessionDraft.sceneId}
                      onChange={(value) =>
                        setManualSessionDraft((current) => ({
                          ...current,
                          sceneId: value,
                        }))
                      }
                      options={scenes.map((scene) => ({
                        label: scene.sceneCode,
                        value: String(scene.id),
                      }))}
                    />
                    <label>
                      START
                      <input
                        aria-label="Manual start"
                        type="datetime-local"
                        value={manualSessionDraft.start}
                        onChange={(event) =>
                          setManualSessionDraft((current) => ({
                            ...current,
                            start: event.target.value,
                          }))
                        }
                        required
                      />
                    </label>
                    <label>
                      DURATION
                      <input
                        aria-label="Manual duration"
                        min="0"
                        step="30"
                        type="number"
                        value={manualSessionDraft.durationMinutes}
                        onChange={(event) =>
                          setManualSessionDraft((current) => ({
                            ...current,
                            durationMinutes: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                    <button type="submit">[ ADD MANUAL SESSION ]</button>
                  </form>
                </section>

                <section aria-labelledby="debt-heading">
                  <h3 id="debt-heading">SCENE DEBT</h3>
                  <DataTable
                    emptyMessage="NO SCENE DEBT"
                    headers={['SCENE', 'REQUIRED', 'SCHEDULED', 'REMAINING']}
                    rows={selectedPlan.debts.map((debt) => [
                      debt.sceneCode,
                      `${debt.requiredMinutes} MIN`,
                      `${debt.scheduledMinutes} MIN`,
                      `${debt.remainingMinutes} MIN`,
                    ])}
                  />
                </section>

                <section aria-labelledby="conflicts-heading">
                  <h3 id="conflicts-heading">CONFLICTS</h3>
                  <ul className="conflict-list">
                    {validationPending ? (
                      <li>VALIDATING WITH PYTHON...</li>
                    ) : selectedPlan.conflicts.length === 0 ? (
                      <li>NO CONFLICTS DETECTED</li>
                    ) : (
                      selectedPlan.conflicts.map((conflict) => (
                        <li key={conflict}>{conflict}</li>
                      ))
                    )}
                  </ul>
                </section>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="panel" id="publish" aria-labelledby="publish-heading">
        <h2 id="publish-heading">CALENDAR APPROVAL</h2>
        <div className="metrics-grid">
          <SummaryRow
            label="CALENDAR CONNECTION"
            value={
              calendarStatus?.connected
                ? 'GOOGLE CONNECTED'
                : calendarStatus?.configured
                  ? 'GOOGLE AUTH READY'
                  : 'GOOGLE NOT CONFIGURED'
            }
          />
          <SummaryRow
            label="LOCAL DEMO PUBLISHER"
            value={
              calendarStatus?.demoPublisherAvailable ? 'READY' : 'CHECKING'
            }
          />
          <SummaryRow
            label="SELECTED PLAN"
            value={selectedPlan?.label ?? 'NONE'}
          />
          <SummaryRow
            label="SESSIONS"
            value={String(selectedPlan?.sessions.length ?? 0)}
          />
          <SummaryRow
            label="CONFLICT WARNINGS"
            value={String(selectedPlan?.conflicts.length ?? 0)}
          />
        </div>
        {!calendarStatus?.connected && calendarStatus?.authUrl && (
          <a className="text-link" href={calendarStatus.authUrl}>
            [ CONNECT GOOGLE CALENDAR ]
          </a>
        )}
        <label className="checkbox-label approval-check">
          <input
            checked={calendarApproved}
            type="checkbox"
            onChange={(event) => setCalendarApproved(event.target.checked)}
          />
          I APPROVE THE SELECTED SCHEDULE
        </label>
        <div className="publish-actions">
          <button
            type="button"
            disabled={!selectedPlan || validationPending || calendarPending}
            onClick={() => void previewApprovedPlan()}
          >
            [ PREVIEW CALENDAR EVENTS ]
          </button>
          <button
            type="button"
            disabled={
              !calendarApproved ||
              !calendarPreview ||
              Boolean(selectedPlan?.conflicts.length) ||
              calendarPending
            }
            onClick={() => void publishApprovedPlan()}
          >
            [ PUBLISH APPROVED SESSIONS ]
          </button>
        </div>
        {calendarError && (
          <p className="status-message warning-text">{calendarError}</p>
        )}
        {calendarPreview && (
          <div className="calendar-preview">
            <h3>EVENT PREVIEW</h3>
            <div className="metrics-grid">
              <SummaryRow
                label="SESSION COUNT"
                value={String(calendarPreview.sessionCount)}
              />
              <SummaryRow
                label="INVITED ACTORS"
                value={String(calendarPreview.invitedActorCount)}
              />
              <SummaryRow
                label="DATE RANGE"
                value={
                  calendarPreview.dateRange
                    ? `${calendarPreview.dateRange.start} TO ${calendarPreview.dateRange.end}`
                    : 'NO EVENTS'
                }
              />
            </div>
            <DataTable
              emptyMessage="NO EVENTS"
              headers={['EVENT', 'START', 'END', 'INVITES']}
              rows={calendarPreview.events.map((event) => [
                event.title,
                event.start,
                event.end,
                String(event.attendeeEmails.length),
              ])}
            />
          </div>
        )}
        {publishReport && (
          <div className="publish-report" role="status">
            {`PUBLISH COMPLETE // ${publishReport.publishedCount} PUBLISHED // ${publishReport.failedCount} FAILED`}
          </div>
        )}
      </section>

      <BlockingTool actors={actors} scenes={scenes} />
    </main>
  )
}

type SelectFieldProps = {
  disabled?: boolean
  emptyLabel?: string
  label: string
  value: string
  options: { label: string; value: string }[]
  onChange: (value: string) => void
}

function SelectField({
  disabled = false,
  emptyLabel = 'SELECT',
  label,
  onChange,
  options,
  value,
}: SelectFieldProps) {
  return (
    <label>
      {label}
      <select
        aria-label={sentenceCase(label)}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      >
        <option value="">{emptyLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

type DataTableProps = {
  emptyMessage: string
  headers: string[]
  rows: string[][]
}

function DataTable({ emptyMessage, headers, rows }: DataTableProps) {
  return (
    <table>
      <thead>
        <tr>
          {headers.map((header) => (
            <th key={header}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={headers.length}>{emptyMessage}</td>
          </tr>
        ) : (
          rows.map((row) => (
            <tr key={row.join('|')}>
              {row.map((cell, index) => (
                <td key={`${cell}-${index}`}>{cell}</td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Timeline({
  actors,
  emptyMessage,
  sessions,
}: {
  actors: Actor[]
  emptyMessage: string
  sessions: ScheduleSession[]
}) {
  if (sessions.length === 0) {
    return (
      <table>
        <tbody>
          <tr>
            <td>{emptyMessage}</td>
          </tr>
        </tbody>
      </table>
    )
  }

  return (
    <ol className="timeline-list">
      {sessions.map((session) => (
        <li key={`${session.sceneCode}-${session.start}`}>
          <time>{`${dateLabel(session.start)} ${timeLabel(session.start)}-${timeLabel(
            session.end,
          )}`}</time>
          <strong>{session.sceneCode}</strong>
          <span>
            {session.actorIds.map((id) => actorName(actors, id)).join(', ')}
          </span>
        </li>
      ))}
    </ol>
  )
}

function buildSchedulePlans(input: {
  actors: Actor[]
  availability: Availability[]
  castAssignments: CastAssignment[]
  sceneCharacters: SceneCharacter[]
  scenes: Scene[]
}): SchedulePlan[] {
  return [
    buildSchedulePlan(input, 'efficient', 'EFFICIENT'),
    buildSchedulePlan(input, 'balanced', 'BALANCED'),
    buildSchedulePlan(input, 'scene_priority', 'SCENE PRIORITY'),
  ]
}

function buildSchedulePlan(
  input: {
    actors: Actor[]
    availability: Availability[]
    castAssignments: CastAssignment[]
    sceneCharacters: SceneCharacter[]
    scenes: Scene[]
  },
  id: PlanMode,
  label: string,
): SchedulePlan {
  const sessions: ScheduleSession[] = []
  const conflicts: string[] = []
  const cursorByActor = new Map<number, Date>()
  const orderedScenes = orderScenesForMode(input.scenes, id)

  for (const scene of orderedScenes) {
    const actorIds = requiredActorIdsForScene(scene, input)
    if (actorIds.length === 0) {
      conflicts.push(`${scene.sceneCode} HAS NO REQUIRED CHARACTERS`)
      continue
    }

    const startAfter = latestCursor(actorIds, cursorByActor)
    const window = firstCommonWindow(
      actorIds,
      input.availability,
      startAfter,
      scene.targetRehearsalMinutes,
    )

    if (!window) {
      conflicts.push(`${scene.sceneCode} HAS NO COMMON AVAILABLE WINDOW`)
      continue
    }

    const end = addMinutes(window.start, scene.targetRehearsalMinutes)
    const session = {
      id: sessions.length + 1,
      sceneId: scene.id,
      sceneCode: scene.sceneCode,
      actorIds,
      start: toLocalInputValue(window.start),
      end: toLocalInputValue(end),
      durationMinutes: scene.targetRehearsalMinutes,
    }
    sessions.push(session)
    for (const actorId of actorIds) {
      cursorByActor.set(actorId, end)
    }
  }

  const debts = input.scenes.map((scene) => {
    const scheduledMinutes = sessions
      .filter((session) => session.sceneId === scene.id)
      .reduce((total, session) => total + session.durationMinutes, 0)
    return {
      sceneCode: scene.sceneCode,
      requiredMinutes: scene.targetRehearsalMinutes,
      scheduledMinutes,
      remainingMinutes: Math.max(
        0,
        scene.targetRehearsalMinutes - scheduledMinutes,
      ),
    }
  })

  return {
    id,
    label,
    inputConflicts: conflicts.filter((conflict) =>
      conflict.endsWith('HAS NO REQUIRED CHARACTERS'),
    ),
    sessions: sessions.sort((left, right) =>
      left.start.localeCompare(right.start),
    ),
    debts,
    conflicts: [...conflicts],
    metrics: calculatePlanMetrics(input.scenes, sessions),
  }
}

function orderScenesForMode(scenes: Scene[], mode: PlanMode) {
  return [...scenes].sort((left, right) => {
    if (mode === 'scene_priority') {
      return (
        Number(right.priority) - Number(left.priority) || left.id - right.id
      )
    }
    if (mode === 'efficient') {
      return (
        right.targetRehearsalMinutes - left.targetRehearsalMinutes ||
        left.id - right.id
      )
    }
    return left.id - right.id
  })
}

function requiredActorIdsForScene(
  scene: Scene,
  input: {
    castAssignments: CastAssignment[]
    sceneCharacters: SceneCharacter[]
  },
) {
  const actorIds = input.sceneCharacters
    .filter(
      (requirement) => requirement.sceneId === scene.id && requirement.required,
    )
    .map((requirement) =>
      input.castAssignments.find(
        (assignment) => assignment.characterId === requirement.characterId,
      ),
    )
    .filter((assignment): assignment is CastAssignment => Boolean(assignment))
    .map((assignment) => assignment.actorId)

  return [...new Set(actorIds)].sort((left, right) => left - right)
}

function calledActorsForSession(
  session: ScheduleSession,
  input: {
    actors: Actor[]
    castAssignments: CastAssignment[]
    characters: Character[]
    sceneCharacters: SceneCharacter[]
  },
) {
  return session.actorIds.flatMap((actorId) => {
    const actor = input.actors.find((item) => item.id === actorId)
    if (!actor) {
      return []
    }
    const characterNames = input.castAssignments
      .filter((assignment) => assignment.actorId === actorId)
      .filter((assignment) =>
        input.sceneCharacters.some(
          (item) =>
            item.sceneId === session.sceneId &&
            item.characterId === assignment.characterId &&
            item.required,
        ),
      )
      .map((assignment) =>
        characterName(input.characters, assignment.characterId),
      )
    return (characterNames.length > 0 ? characterNames : ['UNASSIGNED']).map(
      (character) => ({
        character_name: character,
        actor_name: actor.name,
        email: actor.email,
      }),
    )
  })
}

function firstCommonWindow(
  actorIds: number[],
  availability: Availability[],
  startAfter: Date | null,
  durationMinutes: number,
) {
  const windowsByActor = actorIds.map((actorId) =>
    effectiveWindows(actorId, availability),
  )

  if (windowsByActor.some((windows) => windows.length === 0)) {
    return null
  }

  let overlaps = windowsByActor[0]
  for (const actorWindows of windowsByActor.slice(1)) {
    overlaps = intersectDateWindows(overlaps, actorWindows)
  }

  for (const window of overlaps) {
    const start =
      startAfter && startAfter > window.start ? startAfter : window.start
    const end = addMinutes(start, durationMinutes)
    if (end <= window.end) {
      return { start, end: window.end }
    }
  }

  return null
}

function intersectDateWindows(
  leftWindows: { start: Date; end: Date }[],
  rightWindows: { start: Date; end: Date }[],
) {
  const overlaps: { start: Date; end: Date }[] = []
  for (const left of leftWindows) {
    for (const right of rightWindows) {
      const start = left.start > right.start ? left.start : right.start
      const end = left.end < right.end ? left.end : right.end
      if (start < end) {
        overlaps.push({ start, end })
      }
    }
  }
  return overlaps.sort(
    (left, right) => left.start.getTime() - right.start.getTime(),
  )
}

function latestCursor(actorIds: number[], cursorByActor: Map<number, Date>) {
  const cursors = actorIds
    .map((actorId) => cursorByActor.get(actorId))
    .filter((cursor): cursor is Date => Boolean(cursor))

  if (cursors.length === 0) {
    return null
  }

  return cursors.reduce((latest, cursor) => (cursor > latest ? cursor : latest))
}

function calculatePlanMetrics(scenes: Scene[], sessions: ScheduleSession[]) {
  const scheduledMinutes = sessions.reduce(
    (total, session) => total + session.durationMinutes,
    0,
  )
  const targetMinutes = scenes.reduce(
    (total, scene) => total + scene.targetRehearsalMinutes,
    0,
  )
  const criticalTarget = scenes
    .filter((scene) => scene.priority === '4')
    .reduce((total, scene) => total + scene.targetRehearsalMinutes, 0)
  const criticalScheduled = sessions
    .filter((session) =>
      scenes.some(
        (scene) => scene.id === session.sceneId && scene.priority === '4',
      ),
    )
    .reduce((total, session) => total + session.durationMinutes, 0)

  return {
    days: new Set(sessions.map((session) => dateLabel(session.start))).size,
    rehearsalHours: scheduledMinutes / 60,
    actorIdleMinutes: calculateActorIdleMinutes(sessions),
    criticalCoverage: percentage(criticalScheduled, criticalTarget),
    debtCompleted: percentage(scheduledMinutes, targetMinutes),
  }
}

function calculateActorIdleMinutes(sessions: ScheduleSession[]) {
  const sessionsByActorAndDay = new Map<string, ScheduleSession[]>()
  for (const session of sessions) {
    for (const actorId of session.actorIds) {
      const key = `${actorId}-${dateLabel(session.start)}`
      sessionsByActorAndDay.set(key, [
        ...(sessionsByActorAndDay.get(key) ?? []),
        session,
      ])
    }
  }

  let idleMinutes = 0
  for (const actorSessions of sessionsByActorAndDay.values()) {
    const orderedSessions = actorSessions.sort((left, right) =>
      left.start.localeCompare(right.start),
    )
    for (let index = 1; index < orderedSessions.length; index += 1) {
      idleMinutes += Math.max(
        0,
        minutesBetween(
          orderedSessions[index - 1].end,
          orderedSessions[index].start,
        ),
      )
    }
  }
  return idleMinutes
}

function percentage(value: number, total: number) {
  if (total <= 0) {
    return 0
  }
  return Math.round((value / total) * 100)
}

function addMinutes(value: Date, minutes: number) {
  return new Date(value.getTime() + minutes * 60_000)
}

function minutesBetween(start: string, end: string) {
  return Math.round(
    (parseLocalInputValue(end).getTime() -
      parseLocalInputValue(start).getTime()) /
      60_000,
  )
}

function parseLocalInputValue(value: string) {
  return new Date(value)
}

function toLocalInputValue(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  const hour = String(value.getHours()).padStart(2, '0')
  const minute = String(value.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hour}:${minute}`
}

function dateLabel(value: string) {
  return value.slice(0, 10)
}

function timeLabel(value: string) {
  return value.slice(11, 16)
}

function nextNumericId(items: { id: number }[]) {
  return items.reduce((highest, item) => Math.max(highest, item.id), 0) + 1
}

function calendarImportReason(reason: string) {
  const labels: Record<string, string> = {
    FORBIDDEN: 'CALENDAR NOT SHARED WITH CONNECTED ACCOUNT',
    NOTFOUND: 'CALENDAR NOT FOUND OR NOT SHARED WITH CONNECTED ACCOUNT',
    MISSING_EMAIL: 'ACTOR EMAIL MISSING',
    NO_RESPONSE: 'GOOGLE RETURNED NO CALENDAR DATA',
  }
  return labels[reason] ?? reason.replaceAll('_', ' ')
}

function stringValue(form: FormData, name: string) {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}

function numberValue(form: FormData, name: string) {
  const value = Number(stringValue(form, name))
  return Number.isFinite(value) ? value : 0
}

function actorName(actors: Actor[], actorId: number) {
  return actors.find((actor) => actor.id === actorId)?.name ?? 'UNKNOWN ACTOR'
}

function characterName(characters: Character[], characterId: number) {
  return (
    characters.find((character) => character.id === characterId)?.name ??
    'UNKNOWN CHARACTER'
  )
}

function sceneCode(scenes: Scene[], sceneId: number) {
  return (
    scenes.find((scene) => scene.id === sceneId)?.sceneCode ?? 'UNKNOWN SCENE'
  )
}

function sentenceCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()
}

export default App
