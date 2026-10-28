# Mission Log

A small Angular app that lists the crew's missions. It consumes the Mission Log API
through a generated client in `src/api/` (generated from `api/openapi.json`; do not edit).

- `npm start` serves the app on http://localhost:4200/ (the API is proxied in dev; see `proxy.conf.json`).
- `npm test` runs the Vitest suite through `ng test`.
- `npm run build` builds for production.
