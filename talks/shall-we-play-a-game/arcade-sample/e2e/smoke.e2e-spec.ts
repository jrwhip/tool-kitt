import { expect, test } from '@playwright/test';

test('the shell loads and shows the WOPR ARCADE title', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveTitle('WOPR ARCADE');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('WOPR ARCADE');
});
