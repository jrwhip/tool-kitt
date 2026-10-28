import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      exclude: ['amplify_outputs.json', '.amplify/**'],
    },
  },
});
