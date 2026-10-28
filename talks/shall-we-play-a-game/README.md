# Shall We Play a Game? — deck + recordings

A talk for frontend developers on using Tool-Kitt (KITT) with Claude Code. Twenty-one slides in one
HTML page. Four of the slides replay real Claude Code sessions recorded against the sample app in
`fixture/`. No build step and no server: open `index.html` in Chrome from the folder. Fonts, images,
and recordings are all local files, so the deck renders the same with the network down.

## Run it

```
# any machine with Chrome or Chromium
open index.html        # macOS
xdg-open index.html    # Linux
```

If a browser blocks local scripts, serve the folder instead: `python3 -m http.server 8765` and open
http://127.0.0.1:8765/.

Keys: `←`/`→` slides · `R` replay the recording on this slide · `S` skip to the end of the recording ·
`1` `2` `3` replay speed · `N` speaker notes · `F` fullscreen · `?` help. The slide number is in the
URL hash (`#14` is the first crew slide).

## Folders

| Path | What it is |
|---|---|
| `index.html`, `styles.css`, `app.js` | The deck. Edit slide copy in `index.html`; speaker notes are the `<aside class="notes">` in each slide. |
| `fonts/` | Self-hosted woff2 fonts (Anton for display, Instrument Sans for body, Martian Mono and VT323 for terminals). |
| `images/` | `title.jpg` is the title slide. Robot art goes here as `doctor.png`, `scout.png`, `coder.png`, `tester.png`, `auditor.png`, `gate.png`, `monday.png`; a slide shows a labelled placeholder until its file exists. |
| `fixture/` | The Mission Log sample app: Angular 22, one list component, a generated API client in `src/api/`, an OpenAPI document in `api/`, five Vitest tests. Run `npm install` here once before recording. |
| `arcade-sample/` | A scratch copy of the WOPR Arcade at its "Project setup" commit: the real requirements, specs, and contract file, an empty app, and a `kitt.yml` without the visual check. Recording 4 (the crew slides) runs REQ-ARC-3 against it. `node_modules` is a symlink to the arcade's. |
| `fixture-configured/` | The same app after `/kitt-init-project`, with `kitt.yml`, specs, tracking document, `LEARNINGS.md`, and `requirements/REQ-ML-1.md`. The crew recording runs against this one. |
| `prompts/` | The exact prompt each recording was given. |
| `replays/` | Recordings. `record.py` writes a `.json`, a `.js` twin the deck loads, and a `.raw.ndjson` of the untouched stream. `replays/artifacts/crew/` holds the audit report, learnings file, tracking document, scout contract, and source patch the crew run produced; slide 17 quotes them. |
| `record.py` | The recorder. `tojs.py` rebuilds the `.js` twins from the `.json` files. |

## Re-record

Each recording copies the fixture to a scratch directory, runs `claude -p` with
`--output-format stream-json`, and writes a timed event log plus what changed and whether the test
suite still passes. The session loads the KITT plugins straight from `../../plugins/` and uses
`--setting-sources project,local`, so the operator's own hooks, user CLAUDE.md, and user-installed
plugins stay out of the recording. Login state is shared with the normal `claude` install.

```
python3 record.py @prompts/naked.txt  replays/naked.json  --label naked  --no-plugins --model sonnet
python3 record.py @prompts/doctor.txt replays/doctor.json --label doctor --model sonnet
python3 record.py @prompts/init.txt   replays/init.json   --label init   --model sonnet
python3 record.py @prompts/crew.txt   replays/crew.json   --label crew   --fixture fixture-configured
python3 record.py @prompts/arcade.txt replays/arcade-crew.json --label arcade-crew --fixture arcade-sample
```

The crew run dispatches four agents and takes several minutes. The prompt files carry the operator's
answers to every intake question up front, because a `-p` session cannot stop to ask. The scratch
directory is kept and its path is printed, so the generated files (audit report, learnings entry,
tracking document) can be copied into the deck afterwards.

Recording shape (`version: 2`): `events[]` of `tool`, `agent`, `text`, `output`, and `result` events
with millisecond offsets; `after.changed`, `after.diffstat`, `after.tests`, and `after.patch`; and
`usage` from the final result message. Events inside a subagent carry `agent: "<role>"`.

## Numbers on the slides

Slide 18 quotes `docs/harness-thesis.md` in the KITT repo (the Python golden requirement, two runs
per column). The counters on the replay slides come from the recordings themselves.
