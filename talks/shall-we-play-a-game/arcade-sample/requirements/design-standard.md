# WOPR Arcade design standard

The design bar for REQ-ARC-9. Every rule here is a pass/fail check; a screen that breaks one fails AC1.

## 1. Look
A WarGames-era NORAD terminal: phosphor text on a near-black screen, monospace throughout, thin ruled borders, no rounded corners, no drop shadows, no gradients except the scanline and glow effects below.

## 2. Color
Components use only these tokens (declared in `src/styles.scss`), never raw color values.

| Token | Value | Use |
|---|---|---|
| `--wopr-bg` | `#010b06` | Page background |
| `--wopr-bg-panel` | `#041a0f` | Panel background |
| `--wopr-phosphor-green` | `#33ff66` | Primary text, borders, the player's own marks |
| `--wopr-phosphor-green-dim` | `#1a8033` | Inactive borders, disabled controls, the world map; text only at 24px or larger |
| `--wopr-phosphor-amber` | `#ffb000` | The opponent's marks, JOSHUA's lines, warnings |
| `--wopr-phosphor-red` | `#ff3b30` | Errors, refusals, missile impacts |

- Text contrast against its background is at least 4.5:1, or 3:1 for text 24px or larger. Measured: green 13.5:1, amber 9.9:1, red 5.1:1, dim green 3.6:1 (hence its large-text-only rule).
- Color is never the only signal: X and O are always shown as the letters X and O, and errors always carry text.

## 3. Type
- One monospace family (`--wopr-font-mono`) everywhere, including inputs and buttons.
- Four sizes only: 14px (secondary), 16px (body, chat), 24px (headings), 48px (screen titles and the end-screen line). On phone viewports the 48px size is 32px.
- All headings, labels, buttons, and JOSHUA's lines are uppercase. Player chat and callsigns keep the case the player typed.
- Text glow: `text-shadow: 0 0 4px currentColor` on 24px and 48px text only.

## 4. Layout
- Reference viewports: phone portrait 360x800 and 390x844, phone landscape 800x360 and 844x390, desktop 1280x720 and 1920x1080. Every screen passes every rule at all six.
- No viewport scrolls horizontally, and no text or control is clipped.
- Content fills the viewport inside a 24px outer margin (16px on phones); no screen leaves more than 25% of the viewport width empty on one side.
- Spacing uses multiples of 8px only.
- Panels have a 1px `--wopr-phosphor-green-dim` border and a 14px uppercase title set into the top border.

## 5. Screens

| Screen | Must show | Visual focus |
|---|---|---|
| Welcome | Title "WOPR ARCADE", play as guest, sign in, register | Title |
| Join | Callsign field, callsign warnings (REQ-ARC-1 AC6-8), continue | Callsign field |
| Register / Sign in | Form fields, field-tied errors | Form |
| Lobby | Callsign and rating, quick match, play JOSHUA, leaderboard, sign in/claim prompt for guests | Quick match and play JOSHUA |
| Queue | Live searching state with elapsed time, cancel | Searching state |
| Play | Board, world map, both callsigns and sides, whose turn, JOSHUA and chat feed, disconnect countdown when active | Board |
| End screen | REQ-ARC-9 AC4 | The typed outro line |
| Leaderboard | Rank, callsign, rating, W/L/D, empty state | Table |

### Play screen
- The board is the largest element on the screen and sits in the horizontal center of the play area.
- Board: 3x3 grid drawn with 2px `--wopr-phosphor-green` lines, square cells at least 120px on desktop, 96px on phone portrait, and 88px on phone landscape; marks are 64px letters (48px on phones).
- On phones the board is fully visible without scrolling, in either orientation. Whose turn sits above the board in portrait and beside it in landscape.
- The world map fills the space behind or beside the board and is drawn in `--wopr-phosphor-green-dim` so it never competes with the board.
- The JOSHUA and chat feed is one panel. On desktop it sits beside the board, at least 320px wide, filling the play area's height. On phone portrait it sits below the board; on phone landscape it sits beside the board. On phones the newest JOSHUA line is visible without scrolling.
- Whose turn is shown as text ("YOUR MOVE" / "OPPONENT'S MOVE" / "JOSHUA'S MOVE") above the board.

## 6. Controls
- Buttons: uppercase text in `[ BRACKETS ]`, 1px border, no fill; hover and focus invert (green fill, background-color text).
- Inputs: 1px bottom border only, blinking block cursor, no browser default styling visible (no default outlines, spinners, or autofill colors).
- Every control has a visible keyboard focus state, and every action on every screen can be done by keyboard.
- Every tap target is at least 44x44px.
- On phones the on-screen keyboard never covers the chat input while typing a message.

## 7. Chat and JOSHUA feed
- Each line shows its sender before the text: `BOB>` for players, `JOSHUA>` for JOSHUA.
- JOSHUA's lines are uppercase in `--wopr-phosphor-amber`; both players' lines are in `--wopr-phosphor-green`, told apart by the sender prefix.
- Rejected messages (REQ-ARC-7 AC4) appear only to the sender, in `--wopr-phosphor-red`, with the reason.
- The feed scrolls to the newest line unless the player has scrolled up.

## 8. Motion
| Motion | Timing |
|---|---|
| Missile arc per move (REQ-ARC-9 AC2) | 800ms, ends in a red impact flash on the target |
| Typed text (end screen, JOSHUA lines) | 40ms per character |
| Cursor blink | 1s cycle |
| Screen transitions | Instant cut, no fades or slides |

- No animation delays input: a player can move while a missile arc is still drawing.
- With `prefers-reduced-motion`, arcs draw instantly and typed text appears whole.

## 9. Effects
- A scanline overlay (horizontal 1px lines at 4px spacing, 6% opacity) covers every screen.
- Nothing else: no flicker, no screen curvature, no noise.

## 10. Checking
- Each rule above is checked on every screen listed in section 5 at all six reference viewports.
- Screenshots at all six viewports for every screen are the visual regression baselines; the operator approves them.
