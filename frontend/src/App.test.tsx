import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the stage scheduler Day 1 shell', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'REHEARSAL REQUIREMENTS' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('DETERMINISTIC STAGE SCHEDULER // DAY 01 FOUNDATION'),
    ).toBeInTheDocument()
  })

  it('shows the six-step workflow with requirements as the current step', () => {
    render(<App />)

    expect(
      screen.getByRole('navigation', { name: 'Production workflow' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01 SCRIPT' })).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '04 REQUIREMENTS' }),
    ).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('link', { name: '06 PUBLISH' })).toBeInTheDocument()
  })

  it('states the non-LLM product rule', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        name: 'THE APPLICATION MUST FUNCTION WITHOUT AN LLM',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
    ).toBeInTheDocument()
  })
})
