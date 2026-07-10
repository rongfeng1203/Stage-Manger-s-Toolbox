import './App.css'

const workflowSteps = [
  'SCRIPT',
  'CAST',
  'AVAILABILITY',
  'REQUIREMENTS',
  'SCHEDULE',
  'PUBLISH',
] as const

const foundationChecks = [
  ['BACKEND', 'SQLITE + MODELS READY'],
  ['FRONTEND', 'REACT + TYPESCRIPT READY'],
  ['TESTS', 'PYTEST + VITEST + PLAYWRIGHT WIRED'],
] as const

function App() {
  return (
    <main className="app-shell">
      <header className="masthead">
        <p className="kicker">04 / 06</p>
        <h1>REHEARSAL REQUIREMENTS</h1>
        <p className="subtitle">
          DETERMINISTIC STAGE SCHEDULER // DAY 01 FOUNDATION
        </p>
      </header>

      <nav className="workflow" aria-label="Production workflow">
        {workflowSteps.map((step, index) => (
          <a
            aria-current={index === 3 ? 'step' : undefined}
            className="workflow-step"
            href={`#${step.toLowerCase()}`}
            key={step}
          >
            {String(index + 1).padStart(2, '0')} {step}
          </a>
        ))}
      </nav>

      <section className="panel" aria-labelledby="foundation-heading">
        <div className="section-label">FOUNDATION CHECK</div>
        <h2 id="foundation-heading">SYSTEM RUNS BEFORE SOLVER WORK BEGINS</h2>
        <div className="check-grid">
          {foundationChecks.map(([label, value]) => (
            <div className="check-row" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="rule-heading">
        <div className="section-label">PRODUCT RULE</div>
        <h2 id="rule-heading">THE APPLICATION MUST FUNCTION WITHOUT AN LLM</h2>
        <p>
          SCRIPT / MANUAL INPUT -- STRUCTURED SCENE DATA -- CAST ASSIGNMENTS --
          ACTOR AVAILABILITY -- CONSTRAINT SOLVER -- APPROVAL -- CALENDAR
        </p>
        <button type="button">[ GENERATE SCHEDULE ]</button>
      </section>
    </main>
  )
}

export default App
