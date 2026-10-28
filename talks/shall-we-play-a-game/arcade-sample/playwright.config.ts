import { defineConfig, devices, type Project } from '@playwright/test';

const port = 4300;
const externalBaseUrl = process.env['ARCADE_E2E_BASE_URL'];

const desktopViewports = [
  { name: 'desktop-1280', width: 1280, height: 720 },
  { name: 'desktop-1920', width: 1920, height: 1080 },
];

const phoneViewports = [
  { name: 'phone-portrait-360', width: 360, height: 800 },
  { name: 'phone-portrait-390', width: 390, height: 844 },
  { name: 'phone-landscape-800', width: 800, height: 360 },
  { name: 'phone-landscape-844', width: 844, height: 390 },
];

const desktopBrowsers = [
  { name: 'chromium', device: devices['Desktop Chrome'] },
  { name: 'firefox', device: devices['Desktop Firefox'] },
  { name: 'webkit', device: devices['Desktop Safari'] },
];

const phoneBrowsers = [
  { name: 'chromium', device: devices['Pixel 7'] },
  { name: 'webkit', device: devices['iPhone 14'] },
];

const desktopProjects: Project[] = desktopBrowsers.flatMap((browser) =>
  desktopViewports.map((viewport) => ({
    name: `${browser.name}-${viewport.name}`,
    use: { ...browser.device, viewport: { width: viewport.width, height: viewport.height } },
  })),
);

const phoneProjects: Project[] = phoneBrowsers.flatMap((browser) =>
  phoneViewports.map((viewport) => ({
    name: `${browser.name}-${viewport.name}`,
    use: { ...browser.device, viewport: { width: viewport.width, height: viewport.height } },
  })),
);

export default defineConfig({
  testDir: 'e2e',
  testMatch: '**/*.e2e-spec.ts',
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: externalBaseUrl ?? `http://localhost:${port}`,
    trace: 'retain-on-failure',
  },
  projects: [...desktopProjects, ...phoneProjects],
  webServer: externalBaseUrl
    ? undefined
    : {
        command: `npx ng serve --port ${port}`,
        url: `http://localhost:${port}`,
        reuseExistingServer: false,
        timeout: 180_000,
      },
});
