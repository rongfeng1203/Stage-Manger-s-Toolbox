import { describe, expect, it } from 'vitest'
import {
  effectiveWindows,
  matchGoogleWindows,
  type ActorWindow,
} from './availability'
const w = (
  start: string,
  end: string,
  availabilityType = 'AVAILABLE',
  actorId = 1,
): ActorWindow => ({
  actorId,
  start: `2026-11-02T${start}`,
  end: `2026-11-02T${end}`,
  availabilityType,
})

describe('actor schedule matching', () => {
  it('intersects Excel availability with Google and retains inaccessible actors', () => {
    const current = [
      w('18:00', '22:00'),
      w('19:00', '20:00', 'BUSY'),
      w('18:00', '22:00', 'AVAILABLE', 2),
    ]
    const matched = matchGoogleWindows(
      current,
      [w('18:00', '19:30'), w('20:30', '22:00')],
      [1],
      '2026-11-02T18:00',
      '2026-11-02T22:00',
    )
    expect(effectiveWindows(1, matched)).toEqual([
      {
        start: new Date('2026-11-02T18:00'),
        end: new Date('2026-11-02T19:00'),
      },
      {
        start: new Date('2026-11-02T20:30'),
        end: new Date('2026-11-02T22:00'),
      },
    ])
    expect(matched).toContainEqual(current[2])
  })
  it('does not reopen an actor with no overlap on a repeated match', () => {
    const match = (current: ActorWindow[]) =>
      matchGoogleWindows(
        current,
        [w('20:00', '22:00')],
        [1],
        '2026-11-02T18:00',
        '2026-11-02T22:00',
      )
    expect(effectiveWindows(1, match(match([w('18:00', '19:00')])))).toEqual([])
  })
  it('uses Google free time when only busy constraints exist', () => {
    const result = matchGoogleWindows(
      [w('19:00', '20:00', 'BUSY')],
      [w('18:00', '22:00')],
      [1],
      '2026-11-02T18:00',
      '2026-11-02T22:00',
    )
    expect(effectiveWindows(1, result)).toHaveLength(2)
  })
  it('merges adjacent availability before subtracting overlapping busy windows', () => {
    expect(
      effectiveWindows(1, [
        w('18:00', '19:00'),
        w('19:00', '22:00'),
        w('20:00', '21:00', 'BUSY'),
        w('20:30', '22:00', 'BUSY'),
      ]),
    ).toEqual([
      {
        start: new Date('2026-11-02T18:00'),
        end: new Date('2026-11-02T20:00'),
      },
    ])
  })
})
