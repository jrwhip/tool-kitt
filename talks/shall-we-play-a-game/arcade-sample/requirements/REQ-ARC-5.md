---
id: REQ-ARC-5
title: Ratings, history, and leaderboard
priority: 5
depends_on: [REQ-ARC-3, REQ-ARC-4]
status: pending
---

## Requirement
Completed games are recorded and feed a competitive rating and leaderboard, so returning players build a track record. Ratings attach to the callsign, which is the identity.

## Acceptance criteria
1. Every completed game (win, draw, forfeit) is recorded permanently with both callsigns, the result, and its timing.
2. Ratings follow a defined Elo scheme (K=32, base 1000; win/loss/draw scored 1/0/0.5; a forfeit counts as a normal loss; a game both players abandon counts as a normal draw) and equal the hand-computed values for a fixture sequence of results.
3. Ratings attach to the callsign and continue across sessions.
4. A rating update is applied exactly once per completed game; re-reading or replaying a game never re-applies it.
5. The leaderboard lists players by rating (with win/loss/draw counts), breaking a rating tie by listing first the player who reached that rating most recently, shows a player only after their first completed game, and has a defined empty state.
