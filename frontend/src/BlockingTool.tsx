import {
  type FormEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useState,
} from 'react'

import './BlockingTool.css'
import {
  type BlockingValidationResponse,
  validateBlockingNotebook,
} from './api'

export type BlockingActor = {
  id: number
  name: string
}

export type BlockingScene = {
  id: number
  sceneCode: string
  title: string
}

type Position = {
  actorId: number
  x: number
  y: number
}

type Movement = {
  actorId: number
  fromX: number
  fromY: number
  toX: number
  toY: number
  sequence: number
}

type Cue = {
  id: number
  cueType: string
  label: string
  trigger: string
}

type BlockingBeat = {
  id: number
  sceneId: number
  label: string
  order: number
  positions: Position[]
  movements: Movement[]
  cues: Cue[]
}

type BlockingToolProps = {
  actors: BlockingActor[]
  scenes: BlockingScene[]
}

type StageMode = 'place' | 'move'

const storageKey = 'stage-scheduler-blocking-v1'
const actorColors = [
  '#176b87',
  '#a13d2d',
  '#486b38',
  '#75588c',
  '#a56616',
  '#1c6a5b',
]

export function BlockingTool({ actors, scenes }: BlockingToolProps) {
  const [beats, setBeats] = useState<BlockingBeat[]>(readStoredBeats)
  const [selectedBeatId, setSelectedBeatId] = useState<number | null>(null)
  const [sceneId, setSceneId] = useState('')
  const [beatLabel, setBeatLabel] = useState('')
  const [selectedActorId, setSelectedActorId] = useState('')
  const [mode, setMode] = useState<StageMode>('place')
  const [cueType, setCueType] = useState('LIGHT')
  const [cueLabel, setCueLabel] = useState('')
  const [cueTrigger, setCueTrigger] = useState('')
  const [status, setStatus] = useState('')
  const [validation, setValidation] =
    useState<BlockingValidationResponse | null>(null)
  const [validationPending, setValidationPending] = useState(false)

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(beats))
  }, [beats])

  const activeBeatId = selectedBeatId ?? beats[0]?.id ?? null
  const activeSceneId = sceneId || String(scenes[0]?.id ?? '')
  const activeActorId = selectedActorId || String(actors[0]?.id ?? '')
  const selectedBeat = beats.find((beat) => beat.id === activeBeatId) ?? null
  const selectedScene = scenes.find(
    (scene) => scene.id === selectedBeat?.sceneId,
  )
  const displayedPositions = useMemo(
    () => (selectedBeat ? finalActorPositions(selectedBeat) : []),
    [selectedBeat],
  )

  function addBeat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedSceneId = Number(activeSceneId)
    if (!parsedSceneId || !beatLabel.trim()) {
      setStatus('SCENE AND BEAT LABEL REQUIRED')
      return
    }
    const id = nextId(beats)
    const nextBeat: BlockingBeat = {
      id,
      sceneId: parsedSceneId,
      label: beatLabel.trim().toUpperCase(),
      order: beats.length + 1,
      positions: [],
      movements: [],
      cues: [],
    }
    setBeats((current) => [...current, nextBeat])
    setSelectedBeatId(id)
    setBeatLabel('')
    invalidateValidation(`BEAT ${id} ADDED`)
  }

  function handleStageClick(event: MouseEvent<HTMLButtonElement>) {
    if (!selectedBeat || !activeActorId) {
      setStatus('SELECT A BEAT AND ACTOR')
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.width || !rect.height) {
      setStatus('STAGE PLOT IS NOT AVAILABLE')
      return
    }
    const actorId = Number(activeActorId)
    const x = normalizedCoordinate(event.clientX - rect.left, rect.width)
    const y = normalizedCoordinate(event.clientY - rect.top, rect.height)

    if (mode === 'place') {
      updateSelectedBeat((beat) => ({
        ...beat,
        positions: [
          ...beat.positions.filter((position) => position.actorId !== actorId),
          { actorId, x, y },
        ],
        movements: beat.movements.filter(
          (movement) => movement.actorId !== actorId,
        ),
      }))
      invalidateValidation(`ACTOR PLACED // X ${x} // Y ${y}`)
      return
    }

    const origin = currentActorPosition(selectedBeat, actorId)
    if (!origin) {
      setStatus('PLACE THE ACTOR BEFORE RECORDING MOVEMENT')
      return
    }
    const sequence =
      Math.max(
        0,
        ...selectedBeat.movements
          .filter((movement) => movement.actorId === actorId)
          .map((movement) => movement.sequence),
      ) + 1
    updateSelectedBeat((beat) => ({
      ...beat,
      movements: [
        ...beat.movements,
        {
          actorId,
          fromX: origin.x,
          fromY: origin.y,
          toX: x,
          toY: y,
          sequence,
        },
      ],
    }))
    invalidateValidation(`MOVEMENT ${sequence} RECORDED // X ${x} // Y ${y}`)
  }

  function addCue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedBeat) {
      setStatus('SELECT A BLOCKING BEAT')
      return
    }
    if (!cueLabel.trim() || !cueTrigger.trim()) {
      setStatus('CUE LABEL AND TRIGGER REQUIRED')
      return
    }
    const cueId =
      Math.max(0, ...beats.flatMap((beat) => beat.cues.map((cue) => cue.id))) +
      1
    updateSelectedBeat((beat) => ({
      ...beat,
      cues: [
        ...beat.cues,
        {
          id: cueId,
          cueType,
          label: cueLabel.trim().toUpperCase(),
          trigger: cueTrigger.trim().toUpperCase(),
        },
      ],
    }))
    setCueLabel('')
    setCueTrigger('')
    invalidateValidation(`CUE ${cueId} ADDED`)
  }

  function removeCue(cueId: number) {
    updateSelectedBeat((beat) => ({
      ...beat,
      cues: beat.cues.filter((cue) => cue.id !== cueId),
    }))
    invalidateValidation(`CUE ${cueId} REMOVED`)
  }

  async function validateNotebook() {
    setValidationPending(true)
    setStatus('')
    try {
      const result = await validateBlockingNotebook({
        stage: { width: 100, depth: 100 },
        known_actor_ids: actors.map((actor) => actor.id),
        known_scene_ids: scenes.map((scene) => scene.id),
        beats: beats.map((beat) => ({
          id: beat.id,
          scene_id: beat.sceneId,
          label: beat.label,
          order: beat.order,
          positions: beat.positions.map((position) => ({
            actor_id: position.actorId,
            x: position.x,
            y: position.y,
          })),
          movements: beat.movements.map((movement) => ({
            actor_id: movement.actorId,
            from_x: movement.fromX,
            from_y: movement.fromY,
            to_x: movement.toX,
            to_y: movement.toY,
            sequence: movement.sequence,
          })),
          cues: beat.cues.map((cue) => ({
            id: cue.id,
            cue_type: cue.cueType,
            label: cue.label,
            trigger: cue.trigger,
          })),
        })),
      })
      setValidation(result)
      setStatus(
        result.valid ? 'BLOCKING NOTEBOOK READY' : 'BLOCKING ISSUES FOUND',
      )
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : 'BLOCKING VALIDATION FAILED',
      )
    } finally {
      setValidationPending(false)
    }
  }

  function updateSelectedBeat(update: (beat: BlockingBeat) => BlockingBeat) {
    if (activeBeatId === null) {
      return
    }
    setBeats((current) =>
      current.map((beat) => (beat.id === activeBeatId ? update(beat) : beat)),
    )
  }

  function invalidateValidation(message: string) {
    setValidation(null)
    setStatus(message)
  }

  return (
    <section
      className="panel blocking-module"
      id="blocking"
      aria-labelledby="blocking-heading"
    >
      <h2 id="blocking-heading">BLOCKING NOTEBOOK</h2>

      <div className="blocking-summary" aria-label="Blocking notebook summary">
        <SummaryMetric label="BEATS" value={beats.length} />
        <SummaryMetric
          label="PLACED ACTORS"
          value={beats.reduce(
            (total, beat) => total + beat.positions.length,
            0,
          )}
        />
        <SummaryMetric
          label="MOVEMENTS"
          value={beats.reduce(
            (total, beat) => total + beat.movements.length,
            0,
          )}
        />
        <SummaryMetric
          label="CUES"
          value={beats.reduce((total, beat) => total + beat.cues.length, 0)}
        />
      </div>

      {scenes.length === 0 && (
        <div className="workflow-action">
          <p className="status-message">NO SCENES AVAILABLE</p>
          <a className="text-link" href="#script">
            [ OPEN SCENE SETUP ]
          </a>
        </div>
      )}
      {actors.length === 0 && (
        <div className="workflow-action">
          <p className="status-message">NO ACTORS AVAILABLE</p>
          <a className="text-link" href="#cast">
            [ OPEN CAST SETUP ]
          </a>
        </div>
      )}

      <div className="blocking-workspace">
        <aside className="beat-sidebar" aria-labelledby="beat-list-heading">
          <h3 id="beat-list-heading">BLOCKING BEATS</h3>
          <form className="beat-form" onSubmit={addBeat}>
            <label>
              SCENE
              <select
                aria-label="Blocking scene"
                disabled={scenes.length === 0}
                value={activeSceneId}
                onChange={(event) => setSceneId(event.target.value)}
                required
              >
                <option value="">SELECT</option>
                {scenes.map((scene) => (
                  <option key={scene.id} value={scene.id}>
                    {scene.sceneCode} // {scene.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              BEAT LABEL
              <input
                aria-label="Beat label"
                value={beatLabel}
                onChange={(event) => setBeatLabel(event.target.value)}
                required
              />
            </label>
            <button disabled={scenes.length === 0} type="submit">
              [ ADD BEAT ]
            </button>
          </form>
          <ol className="beat-list">
            {beats.map((beat) => {
              const scene = scenes.find((item) => item.id === beat.sceneId)
              return (
                <li key={beat.id}>
                  <button
                    aria-pressed={beat.id === activeBeatId}
                    type="button"
                    onClick={() => {
                      setSelectedBeatId(beat.id)
                      setStatus('')
                    }}
                  >
                    <span>
                      {String(beat.order).padStart(2, '0')} //{' '}
                      {scene?.sceneCode ?? 'UNKNOWN'}
                    </span>
                    <strong>{beat.label}</strong>
                  </button>
                </li>
              )
            })}
          </ol>
        </aside>

        <div className="stage-workspace">
          <div className="stage-toolbar">
            <label>
              ACTOR
              <select
                aria-label="Blocking actor"
                disabled={actors.length === 0}
                value={activeActorId}
                onChange={(event) => setSelectedActorId(event.target.value)}
              >
                <option value="">SELECT</option>
                {actors.map((actor) => (
                  <option key={actor.id} value={actor.id}>
                    {actor.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mode-field">
              <span>MODE</span>
              <div
                className="mode-control"
                role="group"
                aria-label="Stage plot mode"
              >
                <button
                  aria-pressed={mode === 'place'}
                  type="button"
                  onClick={() => setMode('place')}
                >
                  PLACE
                </button>
                <button
                  aria-pressed={mode === 'move'}
                  type="button"
                  onClick={() => setMode('move')}
                >
                  MOVE
                </button>
              </div>
            </div>
            <div className="active-beat">
              <span>ACTIVE BEAT</span>
              <strong>
                {selectedBeat
                  ? `${selectedScene?.sceneCode ?? 'UNKNOWN'} // ${selectedBeat.label}`
                  : 'NONE'}
              </strong>
            </div>
          </div>

          <div className="stage-frame">
            <span className="stage-axis stage-upstage">UPSTAGE</span>
            <span className="stage-axis stage-right">STAGE RIGHT</span>
            <button
              aria-label="Stage plot"
              className="blocking-stage"
              disabled={!selectedBeat || !activeActorId}
              type="button"
              onClick={handleStageClick}
            >
              <svg aria-hidden="true" className="movement-layer">
                {selectedBeat?.movements.map((movement, index) => (
                  <g key={`${movement.actorId}-${movement.sequence}-${index}`}>
                    <line
                      x1={`${movement.fromX}%`}
                      y1={`${movement.fromY}%`}
                      x2={`${movement.toX}%`}
                      y2={`${movement.toY}%`}
                      stroke={colorForActor(movement.actorId, actors)}
                    />
                    <circle
                      cx={`${movement.toX}%`}
                      cy={`${movement.toY}%`}
                      fill={colorForActor(movement.actorId, actors)}
                      r="5"
                    />
                  </g>
                ))}
              </svg>
              {displayedPositions.map((position) => {
                const actor = actors.find(
                  (item) => item.id === position.actorId,
                )
                return (
                  <span
                    className="actor-marker"
                    key={position.actorId}
                    style={
                      {
                        '--actor-color': colorForActor(
                          position.actorId,
                          actors,
                        ),
                        left: `${position.x}%`,
                        top: `${position.y}%`,
                      } as React.CSSProperties
                    }
                  >
                    <span className="actor-initials">
                      {initials(actor?.name ?? String(position.actorId))}
                    </span>
                    <span className="actor-label">
                      {actor?.name ?? `ACTOR ${position.actorId}`}
                    </span>
                  </span>
                )
              })}
            </button>
            <span className="stage-axis stage-left">STAGE LEFT</span>
            <span className="stage-axis stage-downstage">
              DOWNSTAGE // AUDIENCE
            </span>
          </div>
        </div>
      </div>

      <section className="cue-workspace" aria-labelledby="cue-heading">
        <h3 id="cue-heading">CUES + TRIGGERS</h3>
        <form className="cue-form" onSubmit={addCue}>
          <label>
            TYPE
            <select
              value={cueType}
              onChange={(event) => setCueType(event.target.value)}
            >
              <option>LIGHT</option>
              <option>SOUND</option>
              <option>ACTOR</option>
              <option>SCENERY</option>
              <option>OTHER</option>
            </select>
          </label>
          <label>
            CUE LABEL
            <input
              value={cueLabel}
              onChange={(event) => setCueLabel(event.target.value)}
              required
            />
          </label>
          <label>
            TRIGGER
            <input
              value={cueTrigger}
              onChange={(event) => setCueTrigger(event.target.value)}
              required
            />
          </label>
          <button disabled={!selectedBeat} type="submit">
            [ ADD CUE ]
          </button>
        </form>
        <div className="cue-table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>TYPE</th>
                <th>CUE</th>
                <th>TRIGGER</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {selectedBeat?.cues.length ? (
                selectedBeat.cues.map((cue) => (
                  <tr key={cue.id}>
                    <td>{cue.id}</td>
                    <td>{cue.cueType}</td>
                    <td>{cue.label}</td>
                    <td>{cue.trigger}</td>
                    <td>
                      <button type="button" onClick={() => removeCue(cue.id)}>
                        REMOVE
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>NO CUES FOR ACTIVE BEAT</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="blocking-validation">
        <button
          disabled={beats.length === 0 || validationPending}
          type="button"
          onClick={() => void validateNotebook()}
        >
          {validationPending
            ? '[ VALIDATING... ]'
            : '[ VALIDATE BLOCKING NOTEBOOK ]'}
        </button>
        {status && (
          <p className="status-message" role="status">
            {status}
          </p>
        )}
      </div>
      {validation && (
        <div
          className="blocking-results"
          aria-label="Blocking validation results"
        >
          <strong>
            {validation.valid
              ? 'READY // NO BLOCKING CONFLICTS'
              : `${validation.issues.length} ISSUE(S)`}
          </strong>
          {validation.issues.length > 0 && (
            <ul>
              {validation.issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>{issue.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function SummaryMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function finalActorPositions(beat: BlockingBeat): Position[] {
  return beat.positions.map(
    (position) => currentActorPosition(beat, position.actorId) ?? position,
  )
}

function currentActorPosition(
  beat: BlockingBeat,
  actorId: number,
): Position | null {
  const start = beat.positions.find((position) => position.actorId === actorId)
  if (!start) {
    return null
  }
  const lastMovement = beat.movements
    .filter((movement) => movement.actorId === actorId)
    .sort((left, right) => left.sequence - right.sequence)
    .at(-1)
  return lastMovement
    ? { actorId, x: lastMovement.toX, y: lastMovement.toY }
    : start
}

function nextId(items: { id: number }[]) {
  return Math.max(0, ...items.map((item) => item.id)) + 1
}

function normalizedCoordinate(value: number, extent: number) {
  return Math.max(0, Math.min(100, Math.round((value / extent) * 100)))
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

function colorForActor(actorId: number, actors: BlockingActor[]) {
  const index = Math.max(
    0,
    actors.findIndex((actor) => actor.id === actorId),
  )
  return actorColors[index % actorColors.length]
}

function readStoredBeats(): BlockingBeat[] {
  try {
    const stored = localStorage.getItem(storageKey)
    if (!stored) {
      return []
    }
    const parsed: unknown = JSON.parse(stored)
    return Array.isArray(parsed) ? (parsed as BlockingBeat[]) : []
  } catch {
    return []
  }
}
