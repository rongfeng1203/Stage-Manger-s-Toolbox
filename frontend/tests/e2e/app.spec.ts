import { expect, test } from '@playwright/test'

test('loads the Day 1 scheduler shell', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'REHEARSAL REQUIREMENTS' }),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: '04 REQUIREMENTS' }),
  ).toHaveAttribute('aria-current', 'step')
  await expect(
    page.getByRole('button', { name: '[ GENERATE SCHEDULE ]' }),
  ).toBeVisible()
})
