---
id: REQ-ARC-3
title: Game rules and server authority
priority: 3
depends_on: [REQ-ARC-2]
status: pending
---

## Requirement
The server is the sole authority on the board. It decides every move's legality and every outcome; a client can never make an illegal move stick or fabricate a result.

## Acceptance criteria
1. Only the player whose turn it is may move, and only to an empty cell in the 3x3 grid; any other attempt is rejected with a specific reason and leaves the board unchanged.
2. A player who is not a participant of a game cannot affect it.
3. A win is detected on any of the 8 lines (3 rows, 3 columns, 2 diagonals) and names the winner and the winning line; a full board with no line is a draw.
4. A finished game is immutable: no further move changes it.
5. The authoritative game state (board, whose turn, participants, result) can be read at any time and is the source of truth over any live notification.
