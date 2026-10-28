---
id: REQ-ARC-9
title: Client experience and visual design
priority: 9
depends_on: [REQ-ARC-2, REQ-ARC-3, REQ-ARC-6, REQ-ARC-7]
status: pending
---

## Requirement
The app looks and feels like a WarGames terminal, not a wireframe. It is a designed, cohesive interface in which the game is the focus, the world map dramatizes play, and the closing line lands.

## Acceptance criteria
1. A defined visual design (layout, hierarchy, color, type, motion) exists and every screen conforms to it; on the play screen the board is the visual focus and content uses the viewport rather than clustering in one corner.
2. Each move animates as a missile arc across a recognizable vector world map.
3. JOSHUA's lines and player chat are legible, attributed, and styled to the interface, not default browser controls.
4. Every finished game (win, loss, draw, or forfeit) resolves to the same terminal-styled end screen, which types out JOSHUA's outro for that result character by character, then shows the player's rating change and the rematch and return-to-lobby choices. A win or loss names the winner with the winning line still highlighted on the board; a forfeit states that the opponent failed to return; a draw ends on "THE ONLY WINNING MOVE IS NOT TO PLAY".
5. The lobby, the queue (with a live searching state), and the leaderboard are present and conform to the same design.
6. Every screen meets `design-standard.md`, so "looks finished" is a verifiable outcome rather than an opinion.
7. Every feature works and every screen meets `design-standard.md` on the current versions of Chrome, Safari, Firefox, and Edge on desktop, Safari on iPhone, and Chrome on Android.
