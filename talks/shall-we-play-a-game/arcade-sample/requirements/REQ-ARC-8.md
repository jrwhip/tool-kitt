---
id: REQ-ARC-8
title: Rematch
priority: 8
depends_on: [REQ-ARC-3, REQ-ARC-6, REQ-ARC-7]
status: pending
---

## Requirement
After a game, the two players can immediately play again against each other, and the match's conversation and host history carry forward so a rematch series reads as one continuous session.

## Acceptance criteria
1. When a game ends, either player can offer a rematch, and the other can accept or decline; an offer expires on its own if unanswered within 60 seconds.
2. Accepting starts a new game between the same two players with sides swapped; declining or an expired offer returns both to normal flow, and a fresh offer is allowed afterward.
3. Across a rematch series, the player chat and JOSHUA host history from every earlier game in the series remain visible in the new game as continuous history.
4. Each new game in the series still opens with a fresh JOSHUA intro for that game.
5. The carried history persists across the whole series with no silent loss of messages.
