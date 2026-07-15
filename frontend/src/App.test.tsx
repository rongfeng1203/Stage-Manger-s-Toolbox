import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/calendar/status') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              provider: 'google',
              configured: false,
              connected: false,
              demoPublisherAvailable: true,
              authUrl: null,
            }),
        })
      }
      if (url === '/api/scripts/analyze') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              title: 'HAMLET',
              scenes: [
                {
                  sceneCode: 'A1S1',
                  title: 'Battlements',
                  sourceHeader: 'ACT I, SCENE I',
                  sourceLine: 3,
                  characters: ['Hamlet', 'Horatio'],
                  dialogueCueCount: 3,
                  stageDirectionCount: 1,
                },
              ],
              characterCandidates: [
                { name: 'Hamlet', cueCount: 2, accepted: true },
                { name: 'Horatio', cueCount: 1, accepted: true },
              ],
              warnings: [],
            }),
        })
      }
      if (url === '/api/scripts/upload') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              fileName: 'aladdin.txt',
              fileType: 'text/plain',
              extractedCharacterCount: 106871,
              title: 'ALADDIN: THE COMPLETE SCRIPT',
              scenes: [
                {
                  sceneCode: 'A1S1',
                  title: 'Opening',
                  sourceHeader: 'INFERRED OPENING',
                  sourceLine: 2,
                  characters: ['Peddler'],
                  dialogueCueCount: 1,
                  stageDirectionCount: 0,
                },
              ],
              characterCandidates: [
                { name: 'Peddler', cueCount: 1, accepted: true },
              ],
              warnings: [
                {
                  code: 'INFERRED_SCENES',
                  message: 'no authored scene headers found',
                  line: 2,
                },
              ],
            }),
        })
      }
      if (url === '/api/calendar/preview') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              sessionCount: 1,
              invitedActorCount: 0,
              dateRange: { start: '2026-07-14', end: '2026-07-14' },
              conflictWarnings: [],
              events: [
                {
                  sessionId: 1,
                  title: 'REHEARSAL // A1S1',
                  description: 'SCENE: A1S1',
                  start: '2026-07-14T18:00:00-04:00',
                  end: '2026-07-14T20:00:00-04:00',
                  attendeeEmails: [],
                },
              ],
            }),
        })
      }
      if (url === '/api/calendar/publish') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              publishedCount: 1,
              failedCount: 0,
              events: [
                { sessionId: 1, eventId: 'fake-event-1', status: 'PUBLISHED' },
              ],
            }),
        })
      }
      if (typeof init?.body !== 'string') {
        throw new Error('test request body must be JSON text')
      }
      const payload = JSON.parse(init.body) as {
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
      }
      const conflicts: { code: string; message: string }[] = []
      for (const session of payload.sessions) {
        const start = new Date(session.start)
        const end = new Date(session.end)
        if (session.duration_minutes < 60) {
          conflicts.push({
            code: 'SESSION_TOO_SHORT',
            message: `${session.scene_code}: SESSION SHORTER THAN 60 MIN`,
          })
        }
        for (const actorId of session.actor_ids) {
          const window = payload.availability.find(
            (item) =>
              item.actor_id === actorId &&
              item.availability_type !== 'BUSY' &&
              start >= new Date(item.start) &&
              end <= new Date(item.end),
          )
          if (!window) {
            const name =
              payload.actors.find((actor) => actor.id === actorId)?.name ??
              `ACTOR ${actorId}`
            conflicts.push({
              code: 'ACTOR_BUSY',
              message: `${session.scene_code}: ${name} BUSY ${timeRange(start, end)}`,
            })
          }
        }
      }
      for (let index = 0; index < payload.sessions.length; index += 1) {
        const left = payload.sessions[index]
        for (const right of payload.sessions.slice(index + 1)) {
          const shared = right.actor_ids.find((id) =>
            left.actor_ids.includes(id),
          )
          if (
            shared &&
            new Date(left.start) < new Date(right.end) &&
            new Date(right.start) < new Date(left.end)
          ) {
            const name =
              payload.actors.find((actor) => actor.id === shared)?.name ??
              `ACTOR ${shared}`
            conflicts.push({
              code: 'ACTOR_OVERLAP',
              message: `${right.scene_code}: ${name} DOUBLE BOOKED ${timeRange(new Date(right.start), new Date(right.end))}`,
            })
          }
        }
      }
      const debts = payload.scenes.map((scene) => {
        const scheduledMinutes = payload.sessions
          .filter((session) => session.scene_id === scene.id)
          .reduce((total, session) => total + session.duration_minutes, 0)
        return {
          sceneCode: scene.scene_code,
          requiredMinutes: scene.target_rehearsal_minutes,
          scheduledMinutes,
          remainingMinutes: Math.max(
            0,
            scene.target_rehearsal_minutes - scheduledMinutes,
          ),
        }
      })
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ valid: conflicts.length === 0, conflicts, debts }),
      })
    }),
  )
})

function timeRange(start: Date, end: Date) {
  return `${start.toTimeString().slice(0, 5)}-${end.toTimeString().slice(0, 5)}`
}

describe('App', () => {
  it('renders the release candidate workspace', async () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'STAGE SCHEDULER' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'CREATE PRODUCTION' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'ACTORS + CHARACTERS' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'MANUAL SCENE TABLE' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01 SCRIPT' })).toHaveAttribute(
      'aria-current',
      'step',
    )
    expect(await screen.findByText('GOOGLE NOT CONFIGURED')).toBeInTheDocument()
  })

  it('loads the complete demo production', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(
      screen.getByRole('button', { name: '[ LOAD DEMO PRODUCTION ]' }),
    )

    expect(screen.getAllByText('Hamlet Demo').length).toBeGreaterThan(0)
    expect(screen.getAllByText('A1S2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Maya Chen').length).toBeGreaterThan(0)
    expect(screen.getByText('3', { selector: 'strong' })).toBeInTheDocument()
  })

  it('saves production setup and updates the summary', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByLabelText('NAME'), 'Hamlet')
    await user.clear(screen.getByLabelText('START DATE'))
    await user.type(screen.getByLabelText('START DATE'), '2026-07-13')
    await user.clear(screen.getByLabelText('END DATE'))
    await user.type(screen.getByLabelText('END DATE'), '2026-07-31')
    await user.click(
      screen.getByRole('button', { name: '[ SAVE PRODUCTION ]' }),
    )

    const summary = screen.getByRole('heading', {
      name: 'GENERATE SCHEDULE OPTIONS',
    }).parentElement
    expect(summary).not.toBeNull()
    expect(
      within(summary as HTMLElement).getByText('Hamlet'),
    ).toBeInTheDocument()
  })

  it('creates actors, characters, cast assignments, scenes, requirements, and availability', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByLabelText('Actor name'), 'Rina Feng')
    await user.type(screen.getByLabelText('Actor email'), 'rina@example.com')
    await user.click(screen.getByRole('button', { name: '[ ADD ACTOR ]' }))

    await user.type(screen.getByLabelText('Character name'), 'Hamlet')
    await user.click(screen.getByRole('button', { name: '[ ADD CHARACTER ]' }))

    await user.selectOptions(screen.getAllByLabelText('Character')[0], '1')
    await user.selectOptions(screen.getAllByLabelText('Actor')[0], '1')
    await user.click(
      screen.getByRole('button', { name: '[ ASSIGN CHARACTER ]' }),
    )

    await user.type(screen.getByLabelText('Scene code'), 'a1s1')
    await user.type(screen.getByLabelText('Scene title'), 'Battlements')
    await user.selectOptions(screen.getByLabelText('Scene priority'), '3')
    await user.clear(screen.getByLabelText('Target rehearsal minutes'))
    await user.type(screen.getByLabelText('Target rehearsal minutes'), '120')
    await user.click(screen.getByRole('button', { name: '[ ADD SCENE ]' }))

    await user.selectOptions(screen.getByLabelText('Scene'), '1')
    await user.selectOptions(screen.getAllByLabelText('Character')[1], '1')
    await user.click(
      screen.getByRole('button', { name: '[ ADD REQUIREMENT ]' }),
    )

    await user.selectOptions(screen.getAllByLabelText('Actor')[1], '1')
    await user.type(
      screen.getByLabelText('Availability start'),
      '2026-07-14T18:00',
    )
    await user.type(
      screen.getByLabelText('Availability end'),
      '2026-07-14T22:00',
    )
    await user.click(
      screen.getByRole('button', { name: '[ ADD AVAILABILITY ]' }),
    )

    expect(screen.getAllByText('Rina Feng').length).toBeGreaterThan(1)
    expect(screen.getAllByText('Hamlet').length).toBeGreaterThan(1)
    expect(screen.getAllByText('A1S1').length).toBeGreaterThan(1)
    expect(screen.getByText('Battlements')).toBeInTheDocument()
    expect(screen.getByText('120 MIN')).toBeInTheDocument()
    expect(screen.getAllByText('AVAILABLE').length).toBeGreaterThan(1)
    expect(screen.getByText('2026-07-14T18:00')).toBeInTheDocument()
    expect(screen.getByText('SCENE REQUIREMENTS')).toBeInTheDocument()
    expect(screen.getByText('AVAILABILITY WINDOWS')).toBeInTheDocument()
  })

  it('replaces accessible actor windows with Google free/busy availability', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        if (url === '/api/calendar/status') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                provider: 'google',
                configured: true,
                connected: true,
                demoPublisherAvailable: true,
                authUrl: '/api/calendar/oauth/start',
                scope: 'calendar.freebusy',
              }),
          })
        }
        if (url === '/api/calendar/diagnostics') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                configured: true,
                connected: true,
                freeBusyReachable: true,
                message: 'Google primary calendar free/busy is reachable',
              }),
          })
        }
        if (url === '/api/calendar/freebusy/import') {
          if (typeof init?.body !== 'string') {
            throw new Error('Google import request body must be JSON text')
          }
          expect(JSON.parse(init.body)).toMatchObject({
            actors: [{ id: 1, email: 'rina@example.com' }],
            start_date: '2026-07-14',
            end_date: '2026-07-14',
          })
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                importedActorIds: [1],
                importedActorCount: 1,
                windowCount: 2,
                windows: [
                  {
                    actorId: 1,
                    start: '2026-07-14T18:00',
                    end: '2026-07-14T19:00',
                    availabilityType: 'AVAILABLE',
                  },
                  {
                    actorId: 1,
                    start: '2026-07-14T20:00',
                    end: '2026-07-14T22:00',
                    availabilityType: 'AVAILABLE',
                  },
                ],
                errors: [],
              }),
          })
        }
        throw new Error(`unexpected request: ${url}`)
      }),
    )
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByLabelText('NAME'), 'Hamlet')
    await user.clear(screen.getByLabelText('START DATE'))
    await user.type(screen.getByLabelText('START DATE'), '2026-07-14')
    await user.clear(screen.getByLabelText('END DATE'))
    await user.type(screen.getByLabelText('END DATE'), '2026-07-14')
    await user.type(screen.getByLabelText('Actor name'), 'Rina Feng')
    await user.type(screen.getByLabelText('Actor email'), 'rina@example.com')
    await user.click(screen.getByRole('button', { name: '[ ADD ACTOR ]' }))
    await screen.findByText('CONNECTED')
    expect(
      screen.getByRole('button', {
        name: '[ REPLACE WITH GOOGLE AVAILABILITY ]',
      }),
    ).toBeEnabled()

    await user.click(
      screen.getByRole('button', { name: '[ TEST GOOGLE CONNECTION ]' }),
    )
    expect(
      await screen.findByText('GOOGLE CONNECTION TEST // READY'),
    ).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', {
        name: '[ REPLACE WITH GOOGLE AVAILABILITY ]',
      }),
    )

    expect(
      await screen.findByText('GOOGLE IMPORT // 1 ACTORS // 2 WINDOWS'),
    ).toBeInTheDocument()
    expect(screen.getByText('2026-07-14T18:00')).toBeInTheDocument()
    expect(screen.getByText('2026-07-14T20:00')).toBeInTheDocument()
  })

  it('reviews and confirms deterministic script analysis before import', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(
      screen.getByLabelText('Script text'),
      'HAMLET\n\nACT I, SCENE I\n\nHAMLET\nTo be.',
    )
    await user.click(screen.getByRole('button', { name: '[ ANALYZE SCRIPT ]' }))

    expect(
      await screen.findByLabelText('Script analysis review'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Detected scene code 1')).toHaveValue('A1S1')
    await user.click(screen.getByRole('button', { name: '[ CONFIRM IMPORT ]' }))

    expect(screen.getByText('SCRIPT IMPORT CONFIRMED')).toBeInTheDocument()
    expect(screen.getAllByText('A1S1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Horatio').length).toBeGreaterThan(0)
  })

  it('uploads and automatically analyzes a script file', async () => {
    const user = userEvent.setup()
    render(<App />)
    const file = new File(['ALADDIN\n\nPEDDLER: Welcome.'], 'aladdin.txt', {
      type: 'text/plain',
    })

    await user.upload(screen.getByLabelText('Script file'), file)

    expect(
      await screen.findByLabelText('Uploaded script summary'),
    ).toBeInTheDocument()
    expect(screen.getByText('aladdin.txt')).toBeInTheDocument()
    expect(screen.getByText('106871')).toBeInTheDocument()
    expect(screen.getByLabelText('Detected characters 1')).toHaveValue(
      'Peddler',
    )
    expect(
      screen.getByText('FILE ANALYSIS READY // REVIEW BEFORE IMPORT'),
    ).toBeInTheDocument()
  })

  it('generates three comparable schedule plans from manual input', async () => {
    const user = userEvent.setup()
    render(<App />)

    await createCompleteSchedulingInput(user)

    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )

    expect(
      screen.getByRole('heading', { name: 'PLAN A // EFFICIENT' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'PLAN B // BALANCED' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'PLAN C // SCENE PRIORITY' }),
    ).toBeInTheDocument()
    expect(screen.getByText('METRICS TABLE')).toBeInTheDocument()
    expect(screen.getByText('DAILY TIMELINE')).toBeInTheDocument()
    expect(screen.getByText('SCENE DEBT')).toBeInTheDocument()
    expect(screen.getByText('CONFLICTS')).toBeInTheDocument()
    expect(screen.getByText('NO CONFLICTS DETECTED')).toBeInTheDocument()
    expect(screen.getAllByText('A1S1').length).toBeGreaterThan(1)
    expect(screen.getByText('DEBT COMPLETE')).toBeInTheDocument()
  })

  it('shows conflicts when schedule inputs are incomplete', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByLabelText('Scene code'), 'a1s1')
    await user.click(screen.getByRole('button', { name: '[ ADD SCENE ]' }))
    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )

    expect(screen.getByText('CONFLICTS')).toBeInTheDocument()
    expect(
      screen.getAllByText('A1S1 HAS NO REQUIRED CHARACTERS').length,
    ).toBeGreaterThan(0)
  })

  it('revalidates a moved session against actor availability', async () => {
    const user = userEvent.setup()
    render(<App />)

    await createCompleteSchedulingInput(user)
    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )
    await user.clear(screen.getByLabelText('Move A1S1 start'))
    await user.type(
      screen.getByLabelText('Move A1S1 start'),
      '2026-07-14T17:00',
    )

    expect(
      screen.getByText('A1S1: Rina Feng BUSY 17:00-19:00'),
    ).toBeInTheDocument()
  })

  it('revalidates duration changes and deletion against scene debt', async () => {
    const user = userEvent.setup()
    render(<App />)

    await createCompleteSchedulingInput(user)
    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )
    await user.clear(screen.getByLabelText('Change A1S1 duration'))
    await user.type(screen.getByLabelText('Change A1S1 duration'), '30')

    expect(
      screen.getByText('A1S1: SESSION SHORTER THAN 60 MIN'),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '[ DELETE A1S1 ]' }))

    expect(screen.getAllByText('120 MIN').length).toBeGreaterThan(0)
  })

  it('adds a manual session and reports actor double booking', async () => {
    const user = userEvent.setup()
    render(<App />)

    await createCompleteSchedulingInput(user)
    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )
    await user.selectOptions(screen.getByLabelText('Manual scene'), '1')
    await user.type(screen.getByLabelText('Manual start'), '2026-07-14T18:30')
    await user.clear(screen.getByLabelText('Manual duration'))
    await user.type(screen.getByLabelText('Manual duration'), '60')
    await user.click(
      screen.getByRole('button', { name: '[ ADD MANUAL SESSION ]' }),
    )

    expect(
      screen.getByText('A1S1: Rina Feng DOUBLE BOOKED 18:30-19:30'),
    ).toBeInTheDocument()
  })

  it('previews, explicitly approves, and publishes a clean plan', async () => {
    const user = userEvent.setup()
    render(<App />)
    await createCompleteSchedulingInput(user)
    await user.click(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    )
    await screen.findByText('NO CONFLICTS DETECTED')

    await user.click(
      screen.getByRole('button', { name: '[ PREVIEW CALENDAR EVENTS ]' }),
    )
    expect(await screen.findByText('REHEARSAL // A1S1')).toBeInTheDocument()
    await user.click(screen.getByLabelText('I APPROVE THE SELECTED SCHEDULE'))
    await user.click(
      screen.getByRole('button', { name: '[ PUBLISH APPROVED SESSIONS ]' }),
    )

    expect(
      await screen.findByText('PUBLISH COMPLETE // 1 PUBLISHED // 0 FAILED'),
    ).toBeInTheDocument()
  })
})

async function createCompleteSchedulingInput(
  user: ReturnType<typeof userEvent.setup>,
) {
  await user.type(screen.getByLabelText('NAME'), 'Hamlet')
  await user.clear(screen.getByLabelText('START DATE'))
  await user.type(screen.getByLabelText('START DATE'), '2026-07-13')
  await user.clear(screen.getByLabelText('END DATE'))
  await user.type(screen.getByLabelText('END DATE'), '2026-07-31')
  await user.click(screen.getByRole('button', { name: '[ SAVE PRODUCTION ]' }))

  await user.type(screen.getByLabelText('Actor name'), 'Rina Feng')
  await user.click(screen.getByRole('button', { name: '[ ADD ACTOR ]' }))

  await user.type(screen.getByLabelText('Character name'), 'Hamlet')
  await user.click(screen.getByRole('button', { name: '[ ADD CHARACTER ]' }))

  await user.selectOptions(screen.getAllByLabelText('Character')[0], '1')
  await user.selectOptions(screen.getAllByLabelText('Actor')[0], '1')
  await user.click(screen.getByRole('button', { name: '[ ASSIGN CHARACTER ]' }))

  await user.type(screen.getByLabelText('Scene code'), 'a1s1')
  await user.selectOptions(screen.getByLabelText('Scene priority'), '4')
  await user.clear(screen.getByLabelText('Target rehearsal minutes'))
  await user.type(screen.getByLabelText('Target rehearsal minutes'), '120')
  await user.click(screen.getByRole('button', { name: '[ ADD SCENE ]' }))

  await user.selectOptions(screen.getByLabelText('Scene'), '1')
  await user.selectOptions(screen.getAllByLabelText('Character')[1], '1')
  await user.click(screen.getByRole('button', { name: '[ ADD REQUIREMENT ]' }))

  await user.selectOptions(screen.getAllByLabelText('Actor')[1], '1')
  await user.type(
    screen.getByLabelText('Availability start'),
    '2026-07-14T18:00',
  )
  await user.type(screen.getByLabelText('Availability end'), '2026-07-14T22:00')
  await user.click(screen.getByRole('button', { name: '[ ADD AVAILABILITY ]' }))
}
