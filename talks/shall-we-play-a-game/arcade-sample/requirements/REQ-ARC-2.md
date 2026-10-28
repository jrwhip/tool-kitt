---
id: REQ-ARC-2
title: Matchmaking
priority: 2
depends_on: [REQ-ARC-1]
status: pending
---

## Requirement
A player looking for a game is matched with another waiting player automatically and dropped into a fresh game. There are no lobbies to manage and no opponent to pick.

## Acceptance criteria
1. A player can enter and leave a quick-match queue, and their state (idle, waiting with elapsed time, or matched) is always visible to them.
2. Two waiting players are paired in the order they arrived, each assigned X or O at random, and both are taken into the same new game automatically.
3. A player is never matched with themselves under any sequence of actions: two queue entries are never paired if they share a callsign or come from the same session.
4. A player who waits 2 minutes without a match is removed and told, rather than left waiting indefinitely.
