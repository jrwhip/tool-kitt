---
id: REQ-GOLD-2
title: Tic-tac-toe game engine (REST)
priority: 1
depends_on: []
status: pending
---

## Requirement
A server-authoritative tic-tac-toe engine over REST. Clients create a game and submit moves carrying their symbol; the server validates every move, tracks turns, and detects results. Carved from a larger multiplayer requirement: authentication, matchmaking, and WebSocket push are explicitly out of scope here; this is a hot-seat engine where the caller supplies the symbol.

## Acceptance criteria
1. POST /games returns 201 with a unique game id, an empty 3x3 board, status "in_progress", and "X" to move.
2. A move by the symbol whose turn it is, to an empty in-range cell, returns 200 with the updated board and the turn flipped to the other symbol.
3. A move by the symbol whose turn it is NOT returns 409 with error code "out_of_turn"; board and turn are unchanged.
4. A move to an occupied cell returns 409 with error code "cell_occupied"; state unchanged.
5. A move with row or column outside 0..2 returns 422; state unchanged.
6. A move completing any winning line ends the game: the response and subsequent fetches report status "won", the winning symbol, and the winning line's cells. All 8 lines (3 rows, 3 columns, 2 diagonals) are covered by tests.
7. A ninth move with no winner ends the game with status "draw".
8. Any move submitted to a finished game returns 409 with error code "game_over"; the final state is immutable.
9. Any request referencing an unknown game id returns 404.
10. GET /games/{id} returns board, whose turn (null when finished), status, and result details consistent with the move history.
11. All endpoints and their request/response schemas appear in the OpenAPI document with named typed fields (no untyped dict schemas).
12. Full test suite passes including the pre-existing health test, line coverage >= 90 percent and branch coverage >= 80 percent on app/, and ruff reports zero findings.
