import { expect, test } from '@playwright/test'

test('creates a complete manual scheduling input', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'STAGE SCHEDULER' }),
  ).toBeVisible()

  await page.getByRole('textbox', { exact: true, name: 'NAME' }).fill('Hamlet')
  await page.getByLabel('START DATE', { exact: true }).fill('2026-07-13')
  await page.getByLabel('END DATE', { exact: true }).fill('2026-07-31')
  await expect(page.getByText('Hamlet').first()).toBeVisible()

  await page.getByLabel('Actor name').fill('Rina Feng')
  await page.getByLabel('Actor email').fill('rina@example.com')
  await page.getByRole('button', { name: '[ ADD ACTOR ]' }).click()

  await page.getByLabel('Character name').fill('Hamlet')
  await page.getByRole('button', { name: '[ ADD CHARACTER ]' }).click()

  await page
    .getByRole('combobox', { exact: true, name: 'Character' })
    .first()
    .selectOption('1')
  await page
    .getByRole('combobox', { exact: true, name: 'Actor' })
    .first()
    .selectOption('1')
  await page.getByRole('button', { name: '[ ASSIGN CHARACTER ]' }).click()

  await page.getByLabel('Scene code').fill('a1s1')
  await page.getByLabel('Scene title').fill('Battlements')
  await page.getByLabel('Scene priority').selectOption('3')
  await page.getByLabel('Target rehearsal minutes').fill('120')
  await page.getByRole('button', { name: '[ ADD SCENE ]' }).click()

  await page
    .getByRole('combobox', { exact: true, name: 'Scene' })
    .selectOption('1')
  await page
    .getByRole('combobox', { exact: true, name: 'Character' })
    .nth(1)
    .selectOption('1')
  await page.getByRole('button', { name: '[ ADD REQUIREMENT ]' }).click()

  await page
    .getByRole('combobox', { exact: true, name: 'Actor' })
    .nth(1)
    .selectOption('1')
  await page.getByLabel('Availability start').fill('2026-07-14T18:00')
  await page.getByLabel('Availability end').fill('2026-07-14T22:00')
  await page.getByRole('button', { name: '[ ADD AVAILABILITY ]' }).click()

  await expect(page.getByText('Hamlet').first()).toBeVisible()
  await expect(page.getByText('Rina Feng').first()).toBeVisible()
  await expect(page.getByText('A1S1').first()).toBeVisible()
  await expect(page.getByText('Battlements')).toBeVisible()
  await expect(page.getByText('120 MIN')).toBeVisible()
  await expect(page.getByText('2026-07-14T18:00')).toBeVisible()
  await expect(page.getByText('AVAILABILITY WINDOWS')).toBeVisible()
  await expect(
    page.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
  ).toBeVisible()
  await page.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }).click()

  await expect(
    page.getByRole('heading', { name: 'PLAN A // EFFICIENT' }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'PLAN B // BALANCED' }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'PLAN C // SCENE PRIORITY' }),
  ).toBeVisible()
  await expect(page.getByText('METRICS TABLE')).toBeVisible()
  await expect(page.getByText('DAILY TIMELINE')).toBeVisible()
  await expect(page.getByText('SCENE DEBT')).toBeVisible()
  await expect(page.getByText('CONFLICTS', { exact: true })).toBeVisible()
  await expect(page.getByText('NO CONFLICTS DETECTED')).toBeVisible()

  await page.getByLabel('Move A1S1 start').fill('2026-07-14T17:00')
  await expect(page.getByText('A1S1: Rina Feng BUSY 17:00-19:00')).toBeVisible()
})

test('runs the demo through balanced approval and publishing', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('button', { name: '[ LOAD DEMO PRODUCTION ]' }).click()
  await page.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }).click()
  await expect(page.getByText('NO CONFLICTS DETECTED')).toBeVisible()

  await page
    .getByRole('heading', { name: 'PLAN B // BALANCED' })
    .locator('..')
    .getByRole('button', { name: '[ REVIEW PLAN ]' })
    .click()
  await page
    .getByRole('button', { name: '[ PREVIEW CALENDAR EVENTS ]' })
    .click()
  await expect(page.getByText('REHEARSAL // A1S1')).toBeVisible()
  await page.getByLabel('I APPROVE THE SELECTED SCHEDULE').check()
  await page
    .getByRole('button', { name: '[ PUBLISH APPROVED SESSIONS ]' })
    .click()
  await expect(page.getByRole('status')).toContainText('PUBLISH COMPLETE')
})

test('uploads a script file and produces reviewable analysis', async ({
  page,
}) => {
  await page.goto('/#script')
  await page
    .getByLabel('Script file')
    .setInputFiles(
      '../backend/tests/services/script_parser/fixtures/fixture_hamlet_sample.txt',
    )

  await expect(page.getByLabel('Uploaded script summary')).toBeVisible()
  await expect(page.getByText('fixture_hamlet_sample.txt')).toBeVisible()
  await expect(page.getByLabel('Detected scene code 1')).toHaveValue('A1S1')
  await expect(page.getByLabel('Detected characters 1')).toHaveValue(
    'Hamlet, Horatio',
  )
  await expect(
    page.getByRole('button', { name: '[ CONFIRM IMPORT ]' }),
  ).toBeVisible()
})
