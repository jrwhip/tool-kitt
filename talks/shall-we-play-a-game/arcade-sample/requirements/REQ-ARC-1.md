---
id: REQ-ARC-1
title: Identity and callsigns
priority: 1
depends_on: []
status: pending
---

## Requirement
A player is identified by a callsign, which is a permanent identity. Any player may use any callsign that no account has officially claimed; a registered account can claim a callsign to own it exclusively from then on. An unclaimed callsign is shared on the honor system: its record and rating belong to the callsign, not to whoever typed it, so the app tells players plainly what they are choosing and asks them to use or claim only a callsign that is theirs. Callsign rules also bound what player text can reach the AI host.

## Acceptance criteria
1. A player can start playing by choosing a callsign of 3 to 16 characters from [A-Za-z0-9_-], with no email or password. Callsigns are case-insensitive: callsigns differing only in letter case are the same callsign for identity, claiming, matching, ratings, and reserved names. A callsign is displayed with the letter case the player typed; where one display stands for the callsign as a whole, such as the leaderboard, it uses the letter case with which the callsign was first typed.
2. A callsign outside the length or character rules, or containing any term on the profanity blocklist anywhere in it (case-insensitive), is refused with a message tied to the callsign field that never echoes a blocked callsign back.
3. A player can register an account and sign in; the account and its identity persist across sessions and devices. Registration, email confirmation, sign-in, sign-out, and forgotten-password reset use Cognito's standard flows.
4. A callsign is a permanent identity that any player may use until it is officially claimed; an account can claim exactly one callsign, and from then on that callsign is exclusive to that account.
5. Any attempt to use or claim a callsign already claimed by another account is refused with a distinct, human-readable reason.
6. A player starting play with an unclaimed callsign is told that anyone can use or claim it unless they claim it, and is offered the chance to claim it before continuing.
7. A player starting play with an unclaimed callsign that already has completed games is told it has been used before and has an established record and rating, and is asked to continue only if that history is theirs.
8. An account claiming a callsign that already has completed games is told it has been used before and has an established record and rating, and is asked to claim it only if that history is theirs; a completed claim keeps the callsign's existing record and rating.
9. Every gameplay action is attributed to the acting player's own identity; the server never accepts a client's claim to be a different player.
