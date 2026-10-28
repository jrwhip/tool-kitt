---
id: REQ-ARC-10
title: Play against JOSHUA
priority: 10
depends_on: [REQ-ARC-1, REQ-ARC-3, REQ-ARC-5, REQ-ARC-6, REQ-ARC-8]
status: pending
---

## Requirement
A player can choose from the lobby to play a rated game against JOSHUA instead of waiting for a human opponent. JOSHUA plays perfectly: it never loses, and it wins whenever the player makes a mistake.

## Acceptance criteria
1. The lobby offers a game against JOSHUA, which starts a new game immediately with no queue; sides are assigned at random.
2. JOSHUA's moves go through the same server authority as a human player's; the rules, win and draw detection, and immutability of REQ-ARC-3 apply unchanged.
3. JOSHUA plays perfectly: across every possible sequence of player moves, JOSHUA never loses, and from any position where the player's move allows a forced win, JOSHUA wins.
4. JOSHUA chooses its moves without calling any AI service; a game against JOSHUA plays normally with no AI service reachable.
5. The game is rated and recorded under REQ-ARC-5 like any other completed game. JOSHUA has its own rating, updated by the same Elo scheme as a player's, and appears on the leaderboard like any player.
6. Host commentary under REQ-ARC-6 applies to a game against JOSHUA, including the draw outro.
7. After a game, the player can offer JOSHUA a rematch under REQ-ARC-8; JOSHUA always accepts, and sides swap with each game in the series.
8. No player can use or claim the callsign JOSHUA.
