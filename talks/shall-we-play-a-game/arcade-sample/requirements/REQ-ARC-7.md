---
id: REQ-ARC-7
title: Player chat
priority: 7
depends_on: [REQ-ARC-3]
status: pending
---

## Requirement
Players in a match can talk to each other. Messages are attributed by the server and moderated, so chat can't be forged or abused.

## Acceptance criteria
1. The two participants of a game can exchange chat messages during that game; a non-participant cannot post to it.
2. Each message is attributed to its sender by the server; a client cannot post as a different sender.
3. A message containing a profanity blocklist term as a whole word (case-insensitive) is rejected; a term inside a longer word ("cockpit", "grape") is not. Messages are at most 280 characters, each sender is limited to 5 messages per 10 seconds, and there is no limit on the number of messages in a game.
4. The profanity blocklist is the list of terms in `blocklist.json`, shared by callsign and chat checks.
5. A rejected message is refused to its sender only, with a reason, and is never shown to anyone else.
6. Chat messages, including JOSHUA's lines, are kept permanently with their game.
