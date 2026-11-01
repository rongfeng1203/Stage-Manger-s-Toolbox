import { expect, test } from '@playwright/test'

test('previews spreadsheet actor matches before adding windows', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByLabel('Actor name', { exact: true }).fill('Alex')
  await page.getByRole('button', { name: '[ ADD ACTOR ]' }).click()
  await page.getByLabel('Actor schedule file').setInputFiles({
    name: 'schedule.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'actor,date,start,end,type\nAlex,2026-11-02,18:00,22:00,AVAILABLE\nAlex,2026-11-02,19:00,20:00,BUSY',
    ),
  })
  await expect(page.getByText(/2 windows matched/)).toBeVisible()
  await page.getByRole('button', { name: '[ ADD IMPORTED WINDOWS ]' }).click()
  await expect(
    page.getByRole('cell', { name: '2026-11-02T19:00', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('cell', { name: 'BUSY', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByLabel('Match Google with existing actor windows'),
  ).toBeChecked()
})

test('matches spreadsheet busy times with Google before scheduling', async ({
  page,
}) => {
  await page.route('**/api/calendar/status', (route) =>
    route.fulfill({
      json: {
        provider: 'google',
        configured: true,
        connected: true,
        demoPublisherAvailable: true,
        authUrl: null,
      },
    }),
  )
  await page.route('**/api/calendar/freebusy/import', (route) =>
    route.fulfill({
      json: {
        importedActorIds: [1, 2],
        importedActorCount: 2,
        windowCount: 2,
        errors: [],
        windows: [1, 2].map((actorId) => ({
          actorId,
          start: '2026-07-14T18:00',
          end: '2026-07-14T22:00',
          availabilityType: 'AVAILABLE',
        })),
      },
    }),
  )
  await page.goto('/')
  await page.getByRole('button', { name: '[ LOAD DEMO PRODUCTION ]' }).click()
  await page.getByLabel('Actor schedule file').setInputFiles({
    name: 'commitments.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'email,start,end,type\nrina@example.com,2026-07-14T18:00,2026-07-14T19:00,BUSY',
    ),
  })
  await page.getByRole('button', { name: '[ ADD IMPORTED WINDOWS ]' }).click()
  await page
    .getByRole('button', { name: '[ MATCH WITH GOOGLE AVAILABILITY ]' })
    .click()
  await expect(
    page.getByText('GOOGLE IMPORT // 2 ACTORS // 2 WINDOWS'),
  ).toBeVisible()
  await page.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }).click()
  await expect(page.getByText('NO CONFLICTS DETECTED')).toBeVisible()
  const previewResponse = page.waitForResponse('**/api/calendar/preview')
  await page
    .getByRole('button', { name: '[ PREVIEW CALENDAR EVENTS ]' })
    .click()
  const preview = (await (await previewResponse).json()) as {
    events: { title: string; start: string }[]
  }
  expect(
    preview.events.find((event: { title: string }) =>
      event.title.includes('A1S1'),
    )?.start,
  ).toContain('2026-07-14T19:00')
})
