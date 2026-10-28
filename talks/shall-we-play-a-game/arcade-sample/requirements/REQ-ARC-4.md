---
id: REQ-ARC-4
title: Live state and disconnect resilience
priority: 4
depends_on: [REQ-ARC-3]
status: pending
---

## Requirement
Both players see the game update in real time, and a lost or flaky connection never corrupts a match or hands anyone an unfair result. Correctness never depends on a single notification arriving.

## Acceptance criteria
1. An opponent's move appears to the other player in real time, without a manual refresh.
2. If a live update is missed, the client detects the gap and recovers the correct state from the authoritative record; no outcome depends on any single notification being delivered.
3. When a player drops mid-game, the game holds and the remaining player is shown a countdown; the dropped player has a fixed, server-timed 30-second window to return and resume.
4. Returning within the window resumes play with full state; failing to return forfeits the game, recorded as such, with the other player notified.
5. The window is server-timed and cannot be extended by a stalling client; a drop after the game is already over changes nothing; if both players are dropped and neither returns within their window, the game resolves exactly once, as a draw.
