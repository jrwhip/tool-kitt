---
id: REQ-ARC-6
title: JOSHUA, the AI host
priority: 6
depends_on: [REQ-ARC-3]
status: pending
---

## Requirement
JOSHUA is the WarGames AI host: it comments on each match in character, and players can speak to it in chat. Host commentary is curated content, not live-generated; gameplay never waits on it, and no player text can turn JOSHUA into a mouthpiece.

## Acceptance criteria
1. JOSHUA comments at the key beats of a match: an intro naming both players, at most one mid-game quip, and an outro for a win, draw, or forfeit, with at most a few lines per game.
2. The draw outro always includes the exact line "THE ONLY WINNING MOVE IS NOT TO PLAY".
3. Match commentary (intro, quip, outro) is drawn from curated content and makes no live model call; a match plays normally with no AI service reachable.
4. Host commentary never blocks or delays a move.
5. A player can address JOSHUA directly in chat and receive an in-character reply. A direct reply is generated live when the AI service is reachable and within budget; when the service times out, fails, refuses, or the budget is spent, JOSHUA answers with a curated line instead. Live-generated direct replies are limited to 10 per game and 2000 per UTC day across all players.
6. JOSHUA also interjects in chat on its own, unprompted, using curated lines only, with no live model call.
7. No player-supplied text (callsign or message) can make JOSHUA emit instructions, markup, or content outside its host character; an injection attempt yields a safe in-character line or nothing.
