export type ActorWindow = {
  actorId: number
  start: string
  end: string
  availabilityType: string
}

type Window = { start: Date; end: Date }

export function effectiveWindows(
  actorId: number,
  windows: ActorWindow[],
): Window[] {
  const actorWindows = windows.filter((window) => window.actorId === actorId)
  let available = actorWindows
    .filter((window) => window.availabilityType !== 'BUSY')
    .map((window) => ({
      start: new Date(window.start),
      end: new Date(window.end),
    }))
    .filter((window) => window.end > window.start)
    .sort((a, b) => +a.start - +b.start)
  const merged: Window[] = []
  for (const window of available) {
    const last = merged.at(-1)
    if (last && window.start <= last.end)
      last.end = new Date(Math.max(+last.end, +window.end))
    else merged.push({ ...window })
  }
  available = merged
  for (const busy of actorWindows.filter(
    (window) => window.availabilityType === 'BUSY',
  )) {
    const start = new Date(busy.start),
      end = new Date(busy.end)
    available = available.flatMap((window) => {
      if (end <= window.start || start >= window.end) return [window]
      const parts: Window[] = []
      if (start > window.start) parts.push({ start: window.start, end: start })
      if (end < window.end) parts.push({ start: end, end: window.end })
      return parts
    })
  }
  return available
}

/** Narrow existing availability to Google free times, preserving failed actors. */
export function matchGoogleWindows(
  current: ActorWindow[],
  google: ActorWindow[],
  importedActorIds: number[],
  rangeStart: string,
  rangeEnd: string,
): ActorWindow[] {
  const imported = new Set(importedActorIds)
  const result = current.filter((window) => !imported.has(window.actorId))
  for (const actorId of imported) {
    const existing = current.filter((window) => window.actorId === actorId)
    const free = google.filter((window) => window.actorId === actorId)
    const positive = existing.filter(
      (window) => window.availabilityType !== 'BUSY',
    )
    result.push(
      ...existing.filter((window) => window.availabilityType === 'BUSY'),
    )
    const matched = positive.length
      ? positive.flatMap((window) =>
          free.flatMap((slot) => {
            const start = window.start > slot.start ? window.start : slot.start
            const end = window.end < slot.end ? window.end : slot.end
            return start < end ? [{ ...window, start, end }] : []
          }),
        )
      : free
    result.push(...matched)
    // Keep an explicit closed window so a subsequent match cannot reopen an empty result.
    if (!matched.length)
      result.push({
        actorId,
        start: rangeStart,
        end: rangeEnd,
        availabilityType: 'BUSY',
      })
  }
  return result
}
