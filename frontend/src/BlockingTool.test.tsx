import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BlockingTool } from './BlockingTool'

const actors = [
  { id: 1, name: 'Rina Feng' },
  { id: 2, name: 'Maya Chen' },
]
const scenes = [{ id: 10, sceneCode: 'A1S1', title: 'Battlements' }]

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      expect(url).toBe('/api/blocking/validate')
      const body = init?.body
      if (typeof body !== 'string') {
        throw new Error('blocking request body must be JSON text')
      }
      const payload = JSON.parse(body) as {
        beats: {
          positions: unknown[]
          movements: unknown[]
          cues: unknown[]
        }[]
      }
      expect(payload.beats[0].positions).toHaveLength(1)
      expect(payload.beats[0].movements).toEqual([
        {
          actor_id: 1,
          from_x: 20,
          from_y: 40,
          to_x: 60,
          to_y: 70,
          sequence: 1,
        },
      ])
      expect(payload.beats[0].cues).toHaveLength(1)
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            valid: true,
            summary: {
              beatCount: 1,
              positionCount: 1,
              movementCount: 1,
              cueCount: 1,
            },
            issues: [],
          }),
      })
    }),
  )
})

describe('BlockingTool', () => {
  it('links empty production data back to scene and cast setup', () => {
    render(<BlockingTool actors={[]} scenes={[]} />)

    expect(
      screen.getByRole('link', { name: '[ OPEN SCENE SETUP ]' }),
    ).toHaveAttribute('href', '#script')
    expect(
      screen.getByRole('link', { name: '[ OPEN CAST SETUP ]' }),
    ).toHaveAttribute('href', '#cast')
  })

  it('records a beat, actor movement, cue, validation, and persisted notebook', async () => {
    const user = userEvent.setup()
    const view = render(<BlockingTool actors={actors} scenes={scenes} />)

    await user.type(screen.getByLabelText('Beat label'), 'Entrance')
    await user.click(screen.getByRole('button', { name: '[ ADD BEAT ]' }))
    expect(screen.getByText('ENTRANCE')).toBeInTheDocument()

    const stage = screen.getByRole('button', { name: 'Stage plot' })
    stage.getBoundingClientRect = () => ({
      bottom: 600,
      height: 600,
      left: 0,
      right: 1000,
      top: 0,
      width: 1000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    fireEvent.click(stage, { clientX: 200, clientY: 240 })
    expect(screen.getByRole('status')).toHaveTextContent(
      'ACTOR PLACED // X 20 // Y 40',
    )
    expect(screen.getByText('RF')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'MOVE' }))
    fireEvent.click(stage, { clientX: 600, clientY: 420 })
    expect(screen.getByRole('status')).toHaveTextContent(
      'MOVEMENT 1 RECORDED // X 60 // Y 70',
    )
    const movementLayer = stage.querySelector('.movement-layer')
    const movementLine = stage.querySelector('line')
    const actorMarker = screen.getByText('RF').closest('.actor-marker')
    expect(movementLayer).not.toHaveAttribute('viewBox')
    expect(movementLine).toHaveAttribute('x1', '20%')
    expect(movementLine).toHaveAttribute('y1', '40%')
    expect(movementLine).toHaveAttribute('x2', '60%')
    expect(movementLine).toHaveAttribute('y2', '70%')
    expect(actorMarker).toHaveStyle({ left: '60%', top: '70%' })
    expect(screen.getByText('STAGE RIGHT')).toHaveClass('stage-right')
    expect(screen.getByText('STAGE LEFT')).toHaveClass('stage-left')

    await user.type(screen.getByLabelText('CUE LABEL'), 'LX 1')
    await user.type(screen.getByLabelText('TRIGGER'), 'Door closes')
    await user.click(screen.getByRole('button', { name: '[ ADD CUE ]' }))
    expect(screen.getByText('DOOR CLOSES')).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: '[ VALIDATE BLOCKING NOTEBOOK ]' }),
    )
    expect(
      await screen.findByText('READY // NO BLOCKING CONFLICTS'),
    ).toBeInTheDocument()

    view.unmount()
    render(<BlockingTool actors={actors} scenes={scenes} />)
    expect(screen.getByText('ENTRANCE')).toBeInTheDocument()
    expect(screen.getByText('DOOR CLOSES')).toBeInTheDocument()
  })
})
