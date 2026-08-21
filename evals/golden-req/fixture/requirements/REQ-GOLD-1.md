# REQ-GOLD-1: Echo endpoint

## Summary

Add a `GET /echo` endpoint to the fixture app. It accepts a required query
parameter `msg` and returns the message back along with its length.

## Behavior

- Route: `GET /echo`
- Query parameter: `msg` (string, required, minimum length 1, maximum length 200)
- Success response: `200 OK` with JSON body `{"echo": "<msg>", "length": <int>}`,
  where `<msg>` is the exact value supplied and `<int>` is its character length.
- Missing or invalid `msg` (absent, empty string, or longer than 200 characters):
  `422 Unprocessable Entity`, using FastAPI's default validation error response.
  No custom exception handler is required or wanted for this REQ.
- The endpoint must appear in the app's OpenAPI spec (`GET /openapi.json` at
  runtime) with the `msg` query parameter documented.

## Acceptance Criteria

1. `GET /echo?msg=hello` returns `200` with body `{"echo": "hello", "length": 5}`.
2. `GET /echo` (no `msg` query parameter at all) returns `422`.
3. `GET /echo?msg=` (empty string) returns `422`.
4. `GET /echo?msg=<201 characters>` returns `422`.
5. `GET /echo?msg=<1 character>` returns `200` with the correct `echo` and `length`.
6. `GET /echo?msg=<200 characters>` returns `200` with the correct `echo` and `length`.
7. `GET /openapi.json` includes a `/echo` path entry with `msg` listed as a
   required query parameter.
8. The full test suite (`uv run pytest`) passes with zero failures after the
   change, including the pre-existing `tests/test_health.py::test_health_returns_200_and_ok_status`.
9. Unit tests exist covering acceptance criteria 1 through 6 above (the 200
   path, the missing-param 422 path, and both length boundary cases).

## Out of Scope

- Authentication, rate limiting, logging, or persistence for this endpoint.
- Any change to the existing `GET /health` endpoint.
