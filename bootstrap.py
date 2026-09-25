#!/usr/bin/env python3
"""
Bootstrap de rekordbox-setbuilder.

Uso:
    python bootstrap.py            # crea carpetas y escribe los ficheros que falten
    python bootstrap.py --force    # sobrescribe también los existentes (¡cuidado!)
    python bootstrap.py --dry-run  # muestra qué haría sin tocar el disco

Es idempotente: sin ``--force`` nunca pisa un fichero existente, así que es
seguro ejecutarlo sobre un repo con trabajo propio (p. ej. harmonic_engine.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent

DIRECTORIES: Final[tuple[str, ...]] = (
    "src/core",
    "src/parsers",
    "src/graph",
    "src/app",
    "src/enrichment",
    "src/exporters",
    "tests",
)

FILES: Final[dict[str, str]] = {
    '.gitignore': r'''__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
build/
dist/
.pytest_cache/
.mypy_cache/
.streamlit/secrets.toml
.DS_Store
''',
    'README.md': r'''# rekordbox-setbuilder — Next-Gen DJ SetBuilder

> A DJ set is not a list of good tracks: it is a curve. This app builds it.

`rekordbox-setbuilder` plans DJ sets around an energy curve. You set a target
duration, genres, a BPM range, an energy profile (editable phase by phase) and a
harmonic-mixing policy. The app then works in one of two ways:

- **With a collection** (Rekordbox, Engine DJ, Traktor, VirtualDJ, CSV), it picks
  real tracks. Each pick fits the curve and mixes cleanly from the previous one
  (Camelot wheel + tempo + energy).
- **Without a collection**, it produces a **proposal**: the ideal track for every
  slot of the set, with BPM, energy and a Camelot key that follows a valid
  harmonic route. You can use it as a shopping or crate-digging list.

It has a **web UI** (Streamlit) and a **Python API**. Under the hood the pipeline
is a [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` with
deterministic nodes and a pluggable curator node where an LLM can add a
narrative pass.

---

## Table of contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Running the web app](#running-the-web-app)
4. [Supported collection formats](#supported-collection-formats)
5. [Proposal mode (no collection)](#proposal-mode-no-collection)
6. [Exporting the set](#exporting-the-set)
7. [Using the Python API](#using-the-python-api)
8. [Configuration](#configuration)
9. [Plugging in an LLM curator](#plugging-in-an-llm-curator)
10. [Project layout](#project-layout)
11. [How the pipeline works](#how-the-pipeline-works)
12. [Testing and type checking](#testing-and-type-checking)
13. [Troubleshooting](#troubleshooting)
14. [Current limitations](#current-limitations)

---

## Requirements

- Python **3.11+**
- Core: `pydantic >= 2.6`, `langgraph >= 0.2`
- Optional extras:

| Extra | Installs | Needed for |
|---|---|---|
| `web` | `streamlit >= 1.45`, `pandas`, `altair` | The web UI |
| `rekordbox` | `pyrekordbox >= 0.4` | Reading the local Rekordbox 6 database directly |
| `spotify` | `spotipy >= 2.24` | Optional Spotify enrichment/suggestions (see the caveat below) |
| `lastfm` | `requests >= 2.31` | Optional Last.fm track suggestions in proposal mode |
| `agent` | `anthropic >= 0.40` | Optional LLM + web-search agent suggestions in proposal mode |
| `all` | all of the above | |
| `dev` | `web` + `pytest`, `mypy` | Development |

---

## Installation

### Fresh checkout (scaffold with `bootstrap.py`)

`bootstrap.py` contains every file of the project. It creates the folder
structure and writes any file that does not exist yet.

```bash
python bootstrap.py            # create folders + missing files (never overwrites)
python bootstrap.py --dry-run  # show what would be written, touch nothing
python bootstrap.py --force    # overwrite existing files with the bundled versions
python bootstrap.py --root /path/to/other/dir
```

Without `--force` it is idempotent and safe to run on a repo that already has
your own changes: existing files are reported as `= keep` and left untouched.

### Install dependencies

```bash
cd "Next-Gen DJ SetBuilder"
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

`requirements.txt` installs everything needed to run the app. For development,
use `python -m pip install -e ".[dev]"`; the extras are listed in the table above.

> Always use `python -m pip` and `python -m streamlit`. This way pip and
> Streamlit run with the same interpreter. If you call a bare `streamlit`, it
> may come from another Python, such as a global install left over from the old
> version of the app, that does not have `langgraph`.

---

## Running the web app

```bash
source .venv/bin/activate          # if you are not already in the virtual environment
python -m streamlit run app.py
```

Streamlit opens the app at `http://localhost:8501`. The UI is in Spanish.

1. **Source** (sidebar): choose where the tracks come from.
   - *Sin colección · propuesta*: no collection; the app generates a proposal.
   - *Subir colección*: upload a collection file (formats below). The format is
     detected automatically.
   - *Rekordbox 6 · BD local*: read the Rekordbox 6 database on this machine.
     **Rekordbox must be fully closed**, because it locks its database.
   - *Demo sintética*: a synthetic collection of 160 Tech House tracks, to try
     the app.

   If the collection contains playlists, you can restrict the set to one of them.
2. **Parameters**:
   - **Duration** of the set.
   - **Genres**: pick from the collection's genres, or type your own.
   - **Minutes per track**: automatic uses the collection's median track length.
     Manual is the effective play time per track, net of mix overlaps.
   - **BPM range**: optional. Without it, the app uses the collection's range or,
     with no collection, the genre's typical range.
   - **Harmonic strictness**.
   - **Energy curve profile**, with a weight and an energy range for every phase.
   - **Start key**: only in proposal mode.
3. **Build set** (*Construir set*) shows:
   - **Curva**: an energy chart (allowed band, target line and the actual set)
     and a BPM chart.
   - **Tracklist**: the table of tracks with phase, start time, key, energy, the
     incoming transition type, the pitch % needed and a valid/invalid flag.
   - **Notas y avisos**: the curator's notes and every warning raised along the way.
   - **Export** buttons.

---

## Supported collection formats

| Software | What to upload | How to get it | Playlists |
|---|---|---|---|
| **Rekordbox** (any version) | Collection XML | *File → Export Collection in xml format* | ✅ |
| **Rekordbox 6** | Nothing: read directly | Local database via `pyrekordbox` (Rekordbox closed) | ✅ |
| **Engine DJ** | `m.db` | `Engine Library/Database2/m.db` | ✅ |
| **Traktor** | `collection.nml` | `Documents/Native Instruments/Traktor x.y.z/` | ✅ |
| **VirtualDJ** | `database.xml` | `Documents/VirtualDJ/database.xml` | — |
| **Serato / anything else** | CSV | Export your library or crate to CSV | — |

**Key notation.** Keys are normalized to Camelot whatever notation the source
uses: Camelot (`8A`), Open Key (`1m`), classic (`Am`, `F#m`, `Bb`, `C# minor`,
`G♯m`), or the numeric indexes that Traktor, Engine DJ and Spotify store. The
conversion follows the circle of fifths, so enharmonics (G# = A♭) always map to
the same key.

**CSV columns.** Headers are matched case-insensitively, in English or Spanish.
The delimiter can be `,`, `;` or tab. The required columns are title, BPM, key
and duration.

| Field | Accepted headers |
|---|---|
| title* | `title`, `name`, `track`, `título`, `nombre` |
| bpm* | `bpm`, `tempo`, `averagebpm` |
| key* | `key`, `camelot`, `tonality`, `tonalidad`, `clave` |
| duration* | `duration_sec`, `duration`, `length`, `time`, `duración` (seconds or `m:ss`) |
| artist | `artist`, `artista` |
| energy | `energy`, `energía` (0–10; estimated from BPM if missing) |
| genre | `genre`, `género` |
| tags | `tags`, `etiquetas` (comma-separated) |
| location | `location`, `path`, `file`, `ruta` (needed for M3U8/XML export) |
| id | `id`, `track_id` (defaults to the row number) |

Tracks with no BPM, no recognizable key or no duration are skipped. The UI
reports how many were skipped and why.

**Duplicate tracks.** Real-world libraries often contain the same song twice
under a different id — typically the same audio file re-imported or
re-analyzed in Rekordbox, which assigns it a new `TrackID`. Deduplication is
therefore not by id: `UniversalTrack.dedupe_key()` keys on the file path when
one is available, and otherwise on normalized title + artist + rounded BPM.
`parse_collection_node` drops these before the search, so the same song never
ends up in two slots of the built set, and the UI reports how many duplicates
were discarded.

---

## Proposal mode (no collection)

With no collection, or when no track passes the genre/BPM filters, the graph
switches to `proposal_node` and generates the ideal set from your parameters
alone:

- **Slots**: the number of tracks is the duration divided by the minutes per
  track (5 min by default in the UI).
- **BPM**: interpolated across the BPM range according to each slot's target
  energy. Without an explicit range, the app uses the genre's typical range:
  tech house 122–128, techno 128–138, house 118–126, DnB 170–176, and so on
  (see `src/core/genres.py`).
- **Key route**: starts at the key you choose (8A by default) and follows the
  curve:
  - When energy rises, the key moves forward on the wheel: +1, or +2 when energy
    boosts are allowed.
  - When energy falls, it moves backward: −1, or −2 in permissive mode.
  - When energy holds, it alternates between the relative key and the adjacent
    key.

  Every step is checked against the chosen strictness, so a proposal never
  contains an invalid transition.

Each row reads like a search query, for example
`Techno · 132 BPM · 10A · energía 8.2`.

### Real track suggestions for a proposal (optional)

A proposal's rows are placeholders: BPM, energy and Camelot key, but no real
song. The sidebar's **"Canciones reales"** section (proposal mode only) lets
you pick one of three sources to fill in a real, distinct track per slot. All
three are optional and off by default (*Sin sugerencias*), and none of them
ever touches the slot's BPM/key/energy — those are what keep the curve and
the harmonic route valid. Whichever source you use, the tracklist shows a
*Sugerencia* column (artist – title), a *Fuente* column naming the provider,
and an *Enlace* link, next to the existing search-query hint; the CSV export
carries the same four fields (`suggested_artist`, `suggested_title`,
`suggested_url`, `suggested_source`).

#### Spotify

Uses the `genre` **field filter** of Spotify's search endpoint
(`q=genre:"…"`), confirmed against the
[official reference](https://developer.spotify.com/documentation/web-api/reference/search)
to work for both track and artist search:

1. Primary path: search tracks directly — `/v1/search?type=track&q=genre:"…"`.
   One call, real tracks, correct genre.
2. Fallback, only if that doesn't gather enough distinct tracks: search
   **artists** tagged with the genre (`type=artist`, same filter) and pull
   each artist's most-listened tracks (`/v1/artists/{id}/top-tracks`).

Two earlier attempts at this both failed silently: plain-text search
(`q=<genre>` with no filter) almost never matches anything, because track
titles don't contain the word "techno"; and an artist-only genre filter
turned out to be wrong too — Spotify's docs say `genre` works for track
search as well, which is simpler and is now the primary path.

None of this uses `audio-features` or `recommendations` — both restricted
since 27 November 2024 — so it works with an ordinary Spotify app, no
pre-existing extended quota needed; a
[Client ID and Secret](https://developer.spotify.com/dashboard) is free to
create.

#### Last.fm

An alternative that needs no approval or special quota: the API key is free
and instant at [last.fm/api/account/create](https://www.last.fm/api/account/create).
Uses a single endpoint, `tag.getTopTracks`
([reference](https://www.last.fm/api/show/tag.getTopTracks)), which returns
the most-tagged tracks for a genre tag, ranked by tag weight — no artist
detour like Spotify's fallback needs. Its tag system covers electronic
micro-genres ("tech house", "melodic techno"…) as well as or better than
Spotify's.

Neither Spotify's search nor Last.fm's tags filter by tempo or key, so
either suggestion is a real track of the right genre, not one verified
beat-for-beat against the slot's exact BPM. If a genre doesn't have enough
distinct tracks/artists to cover every slot, or the call fails, the
remaining slots keep their synthetic placeholder rather than being dropped
or repeated; the app reports how many slots got a real suggestion.

#### LLM agent with web search

The one source that reads the **whole curve**, not just the genre: it sends
every slot's genre, phase, BPM, Camelot key and energy in a single call to a
Claude model with the built-in
[web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
(`web_search_20250305`, restricted to Beatport, 1001Tracklists, Resident
Advisor, Spotify and SoundCloud), and asks it to search the web and return
one real track per slot — the closest real match to that slot's *whole*
target, not just its genre tag. It never invents an artist or title; a slot
it can't match stays a placeholder.

This needs your **own Anthropic API key** ([console.anthropic.com](https://console.anthropic.com/))
and has a real cost per use: normal model tokens, plus Anthropic's ~10 USD
per 1,000 web searches. It is the only source of the three that isn't free,
which is why it's opt-in and never selected by default.

**Beatport**, whose BPM/key metadata is exactly what genre-based matching
would ideally check against, does not offer a self-serve API — access is
partner/label-only, so it isn't wired in as its own source here (the LLM
agent can still search Beatport's public pages). If your organization has
Beatport API access, add a client alongside `spotify.py`/`lastfm.py` in
`src/enrichment/` (same shape: a function returning
`(list[UniversalTrack], SuggestionReport)`, using `assign_candidates` from
`src/enrichment/common.py`) and wire it into `sidebar_suggestions`/`run_build`
in `src/app/web.py` the same way.

---

## Exporting the set

| Format | Contents | Load it in |
|---|---|---|
| **CSV** | Full tracklist: phase, key, BPM, energy, transition, pitch %, valid, file path | Spreadsheets, any app |
| **M3U8** | Playlist of file paths | Rekordbox, Engine DJ, Traktor, Serato, VirtualDJ, media players |
| **Rekordbox XML** | Collection and a playlist with your set name | Rekordbox: *Preferences → Advanced → Database → rekordbox xml*, then drag the playlist in from the *rekordbox xml* tree |

M3U8 and XML need the audio file path, which comes from the source collection.
Proposals and the demo have no files, so they export to CSV only. Engine DJ stores paths
relative to its `Database2` folder, and those paths are exported as they are.

---

## Using the Python API

```python
from src.core.models import SetConstraint, PhaseSpec
from src.graph.builder import build_set_graph
from src.graph.state import initial_state
from src.parsers import parse_file

# 1. Load any supported collection (format auto-detected)
with open("collection.xml", "rb") as fh:
    collection = parse_file("collection.xml", fh.read())

# 2. Describe the set
constraints = SetConstraint(
    total_duration_min=90,
    target_genres=["Tech House"],
    bpm_min=120, bpm_max=128,                  # optional
    harmonic_strictness="energy_boost",
    energy_curve_profile="warmup_to_peak",
    energy_phases=None,                        # or a tuple of PhaseSpec to override the profile
    avg_track_duration_min=None,               # None = median length of the collection
)

# 3. Build it
graph = build_set_graph()
result = graph.invoke(initial_state(constraints, collection.tracks))

result["mode"]            # "collection" or "proposal"
result["selected_set"]    # list[UniversalTrack], in play order
result["target_slots"]    # list[TimelineSlot], the target curve
result["transitions"]     # list[TransitionEvaluation], one per mix
result["violations"]      # list[str], warnings accumulated by every node
result["curator_notes"]   # str, human-readable per-phase summary
```

**Proposal mode**: call `initial_state` without tracks.

```python
constraints = SetConstraint(
    total_duration_min=60, target_genres=["Techno"],
    avg_track_duration_min=5, start_key="5A", harmonic_strictness="strict",
)
proposal = build_set_graph().invoke(initial_state(constraints))
for t in proposal["selected_set"]:
    print(t.raw_source.payload["search_hint"])   # "Techno · 130.5 BPM · 5A · energía 2.5"
```

**Exports:**

```python
from src.exporters import set_rows, to_csv, to_m3u8, to_rekordbox_xml

csv_text = to_csv(set_rows(result["selected_set"], result["target_slots"], result["transitions"]))
m3u_text, skipped = to_m3u8(result["selected_set"], "Friday")
xml_text, skipped = to_rekordbox_xml(result["selected_set"], "Friday")
```

**Demo from the command line** (no UI): `python -m src.app`

---

## Configuration

### `SetConstraint`: what you ask for

| Field | Type | Default | Notes |
|---|---|---|---|
| `total_duration_min` | `int` (1–720) | required | Target set length. |
| `target_genres` | `list[str]` | `[]` | Case-insensitive match. Empty means any genre. Also selects the typical BPM range in proposal mode. |
| `bpm_min` / `bpm_max` | `float \| None` | `None` | Hard filter. A missing bound comes from the collection, then from the genre, then from 120–128. |
| `harmonic_strictness` | `"strict" \| "energy_boost" \| "permissive"` | `"energy_boost"` | See below. |
| `energy_curve_profile` | `"warmup_to_peak" \| "rollercoaster" \| "constant"` | `"warmup_to_peak"` | See below. |
| `energy_phases` | `tuple[PhaseSpec, ...] \| None` | `None` | Custom phases (`name`, `weight`, `energy_min`, `energy_max`). They override the profile. Weights are relative and are normalized. |
| `avg_track_duration_min` | `float \| None` | `None` | Effective minutes per track. `None` uses the median length of the collection. |
| `start_key` | `str \| None` | `None` | Camelot key where a proposal starts (defaults to 8A). |

### Harmonic strictness

A transition is **valid** only if both its harmonic type and its pitch change
are allowed. Invalid transitions can still be chosen as a last resort, but they
get a +25 cost penalty and the curator reports them.

| Level | Allowed Camelot moves | Max pitch change |
|---|---|---|
| `strict` | same key, ±1 (adjacent), relative A↔B | 4 % |
| `energy_boost` | the moves above, plus diagonal (±1 with mode switch), +2 and +7 energy boosts | 6 % |
| `permissive` | anything except discordant jumps (adds the −2 energy drop) | 8 % |

Half-time and double-time are resolved automatically: 87 → 174 BPM counts as a 0 % pitch change.

### Energy curve profiles

| Profile | Phases (weight, energy range) |
|---|---|
| `warmup_to_peak` | warmup 25 % (2.0–5.0) → peak_time 50 % (7.0–10.0) → closing 25 % (4.0–6.5) |
| `rollercoaster` | warmup 15 % (3–5) → build 20 % (6–8) → breather 15 % (4–6) → peak_time 30 % (8–10) → closing 20 % (4–6.5) |
| `constant` | sustain 100 % (6–8) |

Within a phase, the target energy ramps linearly from the phase's minimum to its
maximum. If no track falls inside a phase's window, the search **widens it by
±2** instead of returning an incomplete set, and records a warning.

### Energy estimation

Rekordbox, Traktor, Engine DJ and VirtualDJ exports have no energy field. The
app estimates it from BPM:

```
energy = clamp((BPM − 110) / 3, 1, 10)      # src/core/energy.py
```

It is crude across genres but works well within a single genre, which is the
intended use case. A CSV with an `energy` column uses real values instead.

### Spotify enrichment (optional, collection mode)

With a collection loaded, the sidebar's Spotify expander replaces estimated
energy and key with real data (`audio-features`). Only candidate tracks
(after the genre/BPM filter) are queried, up to 500. **This only works for
legacy apps**: Spotify removed the `audio-features` endpoint on 27 November
2024. Only apps that already had (or had requested) an extended quota before
that date still get data; a new app receives `403`, and there is no official
replacement.

In **proposal mode** this expander is replaced by the suggestion-source
picker described in
[Real track suggestions for a proposal](#real-track-suggestions-for-a-proposal-optional)
above — Spotify is one of its three options, and it uses different,
non-deprecated endpoints, so it works with any Spotify app, old or new.

The failure is never silent. The app reports how many tracks/slots got real
data and how many fell back to the estimate (BPM-based energy, or the search
hint), together with the first error. Leave the credential fields empty if
you'd rather not use Spotify at all — the app works the same either way.

### Tuning constants

All scoring weights are module-level `Final` constants:

| Module | Constant | Default | Effect |
|---|---|---|---|
| `src/core/transitions.py` | `MAX_BPM_DELTA_PCT` | 4 / 6 / 8 | Pitch limit per strictness level |
| | `ALLOWED_HARMONIC_TYPES` | see table | Valid Camelot moves per strictness level |
| | `BPM_COST_PER_PCT` | 0.5 | Edge cost per 1 % of pitch |
| | `ENERGY_COST_PER_POINT` | 0.3 | Edge cost per energy point jumped |
| | `INVALID_PENALTY` | 25.0 | Extra cost of an invalid transition |
| `src/graph/nodes.py` | `ENERGY_WINDOW_WIDENING` | 2.0 | Fallback widening of the energy window |
| | `ENERGY_FIT_WEIGHT` | 0.8 | How strongly a track must match the slot's target energy |
| | `BPM_FIT_WEIGHT_PER_PCT` | 0.3 | How strongly a track must match the slot's target BPM |
| | `DURATION_TOLERANCE` | 0.10 | Curator warns if the set is more than ±10 % off the target length |
| `src/core/proposal.py` | `DEFAULT_START_KEY` | `8A` | First key of a proposal |
| | `BIG_STEP` / `SMALL_STEP` | 1.0 / 0.25 | Energy change that triggers a ±2 / ±1 move on the wheel |
| `src/core/genres.py` | `GENRE_BPM_RANGES` | — | Typical BPM per genre (add your own) |
| `src/app/web.py` | `SPOTIFY_MAX_TRACKS` | 500 | Maximum number of tracks queried on Spotify |

---

## Plugging in an LLM curator

`llm_curator_node` runs a **curator**: any callable that takes
`SetGraphState` and returns a `CuratorReport`:

```python
class CuratorReport(BaseModel):
    notes: str
    violations: list[str] = []
    reordered_ids: list[str] | None = None   # optional new play order
```

The default is `rule_based_curator`. It has no LLM dependency: it audits the
transitions and total duration, and writes a per-phase summary. To use an LLM,
pass your own curator:

```python
# pip install langchain-anthropic   (or any chat model with structured output)
from langchain_anthropic import ChatAnthropic

from src.graph.builder import build_set_graph
from src.graph.nodes import CuratorReport
from src.graph.state import SetGraphState

llm = ChatAnthropic(model="claude-sonnet-5").with_structured_output(CuratorReport)

def llm_curator(state: SetGraphState) -> CuratorReport:
    tracklist = "\n".join(
        f"{t.id} | {t.key} | {t.bpm} BPM | E{t.energy} | {t.artist} - {t.title}"
        for t in state["selected_set"]
    )
    return llm.invoke(
        "You are a club DJ. Review this set for narrative flow. "
        "Only reorder if it clearly improves the energy curve, and "
        "return every id exactly once.\n\n" + tracklist
    )

graph = build_set_graph(curator=llm_curator)
```

The graph applies `reordered_ids` only if it is an exact permutation of the
selected set. Otherwise it rejects the reordering, keeps the original order and
records a warning, so a hallucinated id can never corrupt the set.

---

## Project layout

```
.
├── app.py                    # web entry point: python -m streamlit run app.py
├── requirements.txt          # everything needed to run the app
├── bootstrap.py              # scaffolder (idempotent)
├── pyproject.toml
├── src/
│   ├── core/                 # pure domain logic, no I/O, no vendor formats
│   │   ├── models.py         # UniversalTrack, SetConstraint, PhaseSpec, TransitionEvaluation
│   │   ├── harmonic_engine.py# Camelot wheel classification and harmonic cost
│   │   ├── keys.py           # any key notation → Camelot
│   │   ├── transitions.py    # edge cost: harmonic + tempo + energy
│   │   ├── timeline.py       # energy profiles/phases → TimelineSlot list
│   │   ├── proposal.py       # proposal mode: key route + ideal-track placeholders
│   │   ├── genres.py         # typical BPM ranges per genre
│   │   └── energy.py         # BPM → energy estimation
│   ├── parsers/              # vendor collections → UniversalTrack
│   │   ├── base.py           # CollectionParser protocol, ParseResult
│   │   ├── common.py         # shared field normalization
│   │   ├── rekordbox_xml.py  # Rekordbox collection XML
│   │   ├── rekordbox_db.py   # Rekordbox 6 local DB (pyrekordbox)
│   │   ├── engine_dj.py      # Engine DJ m.db
│   │   ├── traktor_nml.py    # Traktor collection.nml
│   │   ├── virtualdj_xml.py  # VirtualDJ database.xml
│   │   └── csv_parser.py     # generic CSV (Serato, spreadsheets…)
│   ├── enrichment/
│   │   ├── common.py         # shared SuggestionReport + assign_candidates for all suggestion sources
│   │   ├── spotify.py        # Spotify audio-features enrichment + track/genre search suggestions
│   │   ├── lastfm.py         # Last.fm tag.getTopTracks suggestions (no approval/quota needed)
│   │   └── llm_agent.py      # Claude + web-search agent suggestions (needs your own API key)
│   ├── exporters/
│   │   └── exports.py        # CSV, M3U8, Rekordbox XML
│   ├── graph/                # LangGraph orchestration
│   │   ├── state.py          # SetGraphState
│   │   ├── nodes.py          # nodes + curator contract
│   │   └── builder.py        # build_set_graph()
│   └── app/
│       ├── web.py            # Streamlit UI
│       ├── presenters.py     # result → tables/chart data (UI-agnostic)
│       └── __main__.py       # CLI demo (python -m src.app)
└── tests/
```

**Architecture rule:** nothing outside `src/parsers` (and `src/enrichment`) may
depend on a vendor SDK or file format. Parsers translate into `UniversalTrack`,
and the original record is kept in `UniversalTrack.raw_source` for exporters.

### Adding a new format

Implement the `CollectionParser` protocol and register it in
`src/parsers/__init__.py` (`FILE_PARSERS`, before the CSV parser):

```python
from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

class MyFormatParser:
    source = TrackSource.CSV   # or add a new TrackSource member

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith(".myext")

    def parse(self, data: bytes) -> ParseResult:
        acc = TrackAccumulator(self.source)
        for record in ...:                       # your decoding
            acc.add(track_id=..., title=..., artist=..., bpm=..., key=..., duration=...)
        return ParseResult(source=self.source, tracks=acc.tracks, skipped=acc.skipped,
                           energy_estimated=acc.energy_estimated, warnings=acc.warnings())
```

`TrackAccumulator.add` converts keys to Camelot, handles BPM stored ×100,
accepts `m:ss` durations, estimates missing energy and counts skipped rows.

---

## How the pipeline works

```
START → parse_collection_node → build_timeline_slots_node ─┬─(tracks)──→ graph_search_node ─┬→ llm_curator_node → END
                                                           └─(no tracks)→ proposal_node ─────┘
```

| Node | Does | Writes |
|---|---|---|
| `parse_collection_node` | Removes duplicate ids, filters by genre and BPM, sorts, and sets the mode | `available_tracks`, `mode` |
| `build_timeline_slots_node` | Builds the target curve (slots with BPM and energy) | `target_slots` |
| `graph_search_node` | For each slot, picks the unused track that minimizes slot-fit cost plus transition cost. The search is deterministic, and ties are broken by id. | `selected_set`, `transitions` |
| `proposal_node` | Generates ideal-track placeholders along a valid key route | `selected_set`, `transitions` |
| `llm_curator_node` | Audits the set and writes notes; can reorder the set | `curator_notes`, optionally `selected_set` |

`violations` uses an `operator.add` reducer: each node returns only its new
warnings, and LangGraph accumulates them across the run.

---

## Testing and type checking

```bash
pytest            # 129 tests: models, core, parsers, exports, graph, suggestion providers, web UI (Streamlit AppTest)
mypy src app.py   # strict mode, pydantic plugin
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'langgraph'` (or the app shows *Faltan dependencias*) | Streamlit runs under a Python that does not have the project's dependencies | Activate the virtual environment, run `python -m pip install -r requirements.txt`, then start the app with `python -m streamlit run app.py`. The error screen shows the exact interpreter in use and the command to fix it. |
| *No se pudo abrir la base de datos de Rekordbox* | Rekordbox is open, or `pyrekordbox` cannot find the database | Close Rekordbox completely, or use the XML export instead |
| Spotify: *N usan la estimación por BPM* with a `403` | The Spotify app was created after 27 November 2024 | Expected. Leave the credentials empty; BPM-based energy is used instead |
| `RuntimeError: requests no está instalado` when picking Last.fm | The `lastfm` extra isn't installed | `pip install -e '.[lastfm]'` (or `.[all]`) |
| `RuntimeError: 'anthropic' no está instalado` when picking the LLM agent | The `agent` extra isn't installed | `pip install -e '.[agent]'` (or `.[all]`) |
| LLM agent falls back for every slot | Invalid/missing Anthropic API key, or the response wasn't parseable JSON | Check the key in the sidebar; the app reports the first error under the *Fuente* summary |

---

## Current limitations

- **The search is greedy.** It picks slot by slot, so it cannot plan ahead for a
  phase change. For example, the jump from warmup to peak_time can need more
  pitch than the limit allows; the UI flags it with ⚠️. The next step is
  Dijkstra/A* over the same edge cost in `src/core/transitions.py`.
- **Serato** stores crates in a binary format; use its CSV export.
- **The Rekordbox DB reader** targets Rekordbox 6 through `pyrekordbox`. For
  Rekordbox 7, or to avoid closing the app, use the XML export.
- **The Engine DJ and VirtualDJ parsers** were tested against synthetic databases
  that follow their documented schemas. Real libraries from other software
  versions may use different column names.
- **Known issue in `harmonic_engine.py`:** in `STANDARD_TO_CAMELOT`,
  `"G#": "11B"` should be `"4B"` (G# major = A♭ major). The parsers are not
  affected, because they use `src/core/keys.py`. mypy strict also flags two
  missing annotations in that file.
''',
    'app.py': r'''"""Punto de entrada de la interfaz web: ``python -m streamlit run app.py``."""

from __future__ import annotations

import importlib.util
import sys

REQUIRED: dict[str, str] = {
    "pydantic": "pydantic>=2.6",
    "langgraph": "langgraph>=0.2",
    "pandas": "pandas>=2.2",
    "altair": "altair>=5",
}

missing = [spec for module, spec in REQUIRED.items() if importlib.util.find_spec(module) is None]

if missing:
    import streamlit as st

    st.set_page_config(page_title="Next-Gen DJ SetBuilder", page_icon="🎧")
    st.error("Faltan dependencias en el Python con el que se está ejecutando Streamlit.")
    st.markdown(f"**Python en uso:** `{sys.executable}`")
    st.markdown("**No encontrados:** " + ", ".join(f"`{m}`" for m in missing))
    st.markdown("Instálalas con **este mismo** intérprete y vuelve a arrancar:")
    st.code(
        f'"{sys.executable}" -m pip install -r requirements.txt\n'
        f'"{sys.executable}" -m streamlit run app.py',
        language="bash",
    )
    st.stop()

from src.app.web import main  # noqa: E402

main()
''',
    'pyproject.toml': r'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "rekordbox-setbuilder"
version = "0.2.0"
description = "Un set no es una lista de buenos temas: es una curva. Esta app la construye."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "langgraph>=0.2",
]

[project.optional-dependencies]
web = ["streamlit>=1.45", "pandas>=2.2", "altair>=5"]
rekordbox = ["pyrekordbox>=0.4"]
spotify = ["spotipy>=2.24"]
lastfm = ["requests>=2.31"]
agent = ["anthropic>=0.40"]
all = ["rekordbox-setbuilder[web,rekordbox,spotify,lastfm,agent]"]
dev = ["rekordbox-setbuilder[web]", "pytest>=8.0", "mypy>=1.10"]

[tool.setuptools.packages.find]
where = ["."]
include = ["src", "src.*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = [
    "pyrekordbox", "pyrekordbox.*",
    "spotipy", "spotipy.*",
    "pandas", "pandas.*",
    "altair", "altair.*",
    "anthropic", "anthropic.*",
    "requests", "requests.*",
]
ignore_missing_imports = true
''',
    'requirements.txt': r'''# Instalación rápida: python -m pip install -r requirements.txt
pydantic>=2.6
langgraph>=0.2
streamlit>=1.45
pandas>=2.2
altair>=5
# Opcionales:
pyrekordbox>=0.4   # leer la BD local de Rekordbox 6
spotipy>=2.24      # enriquecimiento con Spotify (solo apps antiguas)
''',
    'src/__init__.py': r'''"""src package."""
''',
    'src/app/__init__.py': r'''"""app package."""
''',
    'src/app/__main__.py': r'''"""
Demo en modo standalone/sintético: ``python -m src.app``.

Genera una colección determinista, construye un set de 60 min y lo imprime.
"""

from __future__ import annotations

import random

from src.core.energy import estimate_energy_from_bpm
from src.core.models import SetConstraint, UniversalTrack
from src.graph.builder import build_set_graph
from src.graph.state import initial_state

CAMELOT_KEYS: tuple[str, ...] = tuple(f"{n}{m}" for n in range(1, 13) for m in ("A", "B"))


def synthetic_collection(size: int = 80, seed: int = 7) -> list[UniversalTrack]:
    rng = random.Random(seed)
    tracks: list[UniversalTrack] = []
    for i in range(size):
        bpm = round(rng.uniform(116.0, 134.0), 1)
        tracks.append(
            UniversalTrack(
                id=f"syn-{i:03d}",
                title=f"Synthetic Track {i:03d}",
                artist=f"Artist {rng.randint(1, 20)}",
                bpm=bpm,
                key=rng.choice(CAMELOT_KEYS),
                energy=estimate_energy_from_bpm(bpm),
                duration_sec=rng.randint(300, 480),
                genre="Tech House",
            )
        )
    return tracks


def main() -> None:
    constraints = SetConstraint(
        total_duration_min=60,
        target_genres=["Tech House"],
        harmonic_strictness="energy_boost",
        energy_curve_profile="warmup_to_peak",
    )
    graph = build_set_graph()
    result = graph.invoke(initial_state(constraints, synthetic_collection()))

    print(result["curator_notes"], end="\n\n")
    for pos, track in enumerate(result["selected_set"], start=1):
        print(f"{pos:>2}. {track.key:>3}  {track.bpm:6.1f} BPM  E{track.energy:4.1f}  {track.title}")
    if result["violations"]:
        print("\nAvisos:")
        for violation in result["violations"]:
            print(f" - {violation}")


if __name__ == "__main__":
    main()
''',
    'src/app/presenters.py': r'''"""
Transformaciones puras del resultado del grafo a tablas para la UI.
Sin dependencia de Streamlit: testeables por separado.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from src.core.models import TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot
from src.exporters import set_rows

PHASE_LABELS: dict[str, str] = {
    "warmup": "Warmup",
    "build": "Build",
    "breather": "Respiro",
    "peak_time": "Peak time",
    "closing": "Closing",
    "sustain": "Sostenido",
}

TRANSITION_LABELS: dict[str, str] = {
    "perfect": "Misma clave",
    "adjacent": "Adyacente ±1",
    "relative": "Relativa A↔B",
    "energy_boost_1": "Energy boost +7",
    "energy_boost_2": "Energy boost +2",
    "energy_drop": "Energy drop −2",
    "diagonal": "Diagonal",
    "discordant": "Disonante",
}


def phase_label(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase.replace("_", " ").capitalize())


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"


def set_table(
    selected: Sequence[UniversalTrack],
    slots: Sequence[TimelineSlot],
    transitions: Sequence[TransitionEvaluation],
    proposal: bool,
) -> pd.DataFrame:
    """Tabla del set: una fila por tema con su tramo y la transición de entrada."""
    has_suggestions = proposal and any(
        t.raw_source.payload.get("suggested_artist") for t in selected
    )
    records: list[dict[str, Any]] = []
    elapsed = 0
    for row in set_rows(selected, slots, transitions):
        t, tr = row.track, row.transition
        record: dict[str, Any] = {
            "#": row.position,
            "Inicio": format_duration(elapsed),
            "Tramo": phase_label(row.phase),
        }
        if proposal:
            if has_suggestions:
                artist = t.raw_source.payload.get("suggested_artist")
                title = t.raw_source.payload.get("suggested_title")
                record["Sugerencia"] = f"{artist} – {title}" if artist and title else "—"
                record["Fuente"] = t.raw_source.payload.get("suggested_source", "") or ""
                record["Enlace"] = t.raw_source.payload.get("suggested_url", "") or ""
            record["Busca"] = str(t.raw_source.payload.get("search_hint", ""))
        else:
            record["Artista"] = t.artist
            record["Título"] = t.title
        record.update(
            {
                "BPM": t.bpm,
                "Camelot": t.key,
                "Energía": t.energy,
                "Objetivo": row.target_energy if row.target_energy is not None else float("nan"),
                "Transición": TRANSITION_LABELS.get(tr.transition_type.value, tr.transition_type.value)
                if tr
                else "—",
                "Pitch %": round(tr.bpm_delta_pct, 1) if tr else float("nan"),
                "OK": ("✅" if tr.is_valid else "⚠️") if tr else "",
            }
        )
        records.append(record)
        elapsed += t.duration_sec
    return pd.DataFrame.from_records(records)


def curve_frames(
    selected: Sequence[UniversalTrack], slots: Sequence[TimelineSlot]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve (banda, series):
    - banda: rango de energía permitido por slot (para el área de fondo).
    - series: formato largo con la energía objetivo y la real del set.
    """
    band = pd.DataFrame.from_records(
        [
            {
                "Posición": s["index"] + 1,
                "Tramo": phase_label(s["phase"]),
                "Mín": s["energy_min"],
                "Máx": s["energy_max"],
            }
            for s in slots
        ]
    )
    series_records: list[dict[str, Any]] = []
    for slot, track in zip(slots, selected):
        common = {"Posición": slot["index"] + 1, "Tramo": phase_label(slot["phase"])}
        series_records.append(
            {**common, "Serie": "Objetivo", "Energía": slot["target_energy"], "BPM": slot["target_bpm"], "Tema": "—", "Camelot": "—"}
        )
        series_records.append(
            {
                **common,
                "Serie": "Set",
                "Energía": track.energy,
                "BPM": track.bpm,
                "Tema": f"{track.artist} – {track.title}",
                "Camelot": track.key,
            }
        )
    return band, pd.DataFrame.from_records(series_records)
''',
    'src/app/web.py': r'''"""
Interfaz web (Streamlit) del set builder.

Arranque:  python -m streamlit run app.py

Dos modos:
- Con colección (Rekordbox, Engine DJ, Traktor, VirtualDJ, CSV o la BD local de
  Rekordbox 6): elige temas reales siguiendo la curva y las reglas armónicas.
- Sin colección: genera una propuesta slot a slot (BPM, energía, clave Camelot)
  a partir solo de los parámetros.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, Sequence, cast

import altair as alt
import streamlit as st

from src.app.presenters import curve_frames, phase_label, set_table
from src.core.genres import DEFAULT_BPM_RANGE, genre_bpm_range, known_genres
from src.core.models import (
    EnergyCurveProfile,
    HarmonicStrictness,
    PhaseSpec,
    SetConstraint,
    UniversalTrack,
)
from src.core.timeline import ENERGY_PROFILES, estimate_track_count
from src.enrichment.common import SuggestionReport
from src.enrichment.lastfm import suggest_tracks_for_proposal_lastfm
from src.enrichment.llm_agent import DEFAULT_MODEL as DEFAULT_LLM_MODEL, suggest_tracks_for_proposal_llm
from src.enrichment.spotify import EnrichmentReport, enrich_with_spotify, suggest_tracks_for_proposal
from src.exporters import set_rows, to_csv, to_m3u8, to_rekordbox_xml
from src.graph.builder import SetGraph, build_set_graph
from src.graph.nodes import parse_collection_node
from src.graph.state import SetGraphState, initial_state
from src.parsers import SUPPORTED_EXTENSIONS, ParseResult, Rekordbox6DatabaseReader, parse_file

SourceMode = Literal["proposal", "upload", "rekordbox_db", "demo"]

SOURCE_OPTIONS: Final[dict[SourceMode, str]] = {
    "proposal": "Sin colección · propuesta",
    "upload": "Subir colección",
    "rekordbox_db": "Rekordbox 6 · BD local",
    "demo": "Demo sintética",
}
STRICTNESS_OPTIONS: Final[dict[HarmonicStrictness, str]] = {
    "strict": "Estricto",
    "energy_boost": "Energy boost",
    "permissive": "Permisivo",
}
STRICTNESS_HELP: Final[dict[HarmonicStrictness, str]] = {
    "strict": "Solo misma clave, ±1 y relativa A↔B. Pitch máx. 4 %.",
    "energy_boost": "Añade diagonal y saltos de energía +2 / +7. Pitch máx. 6 %.",
    "permissive": "Todo salvo saltos disonantes (incluye energy drop −2). Pitch máx. 8 %.",
}
PROFILE_OPTIONS: Final[dict[EnergyCurveProfile, str]] = {
    "warmup_to_peak": "Warmup → Peak → Closing",
    "rollercoaster": "Montaña rusa",
    "constant": "Constante",
}
CAMELOT_KEYS: Final[list[str]] = [f"{n}{m}" for n in range(1, 13) for m in ("A", "B")]
SPOTIFY_MAX_TRACKS: Final[int] = 500

SuggestionProvider = Literal["none", "spotify", "lastfm", "llm"]

SUGGESTION_PROVIDER_OPTIONS: Final[dict[SuggestionProvider, str]] = {
    "none": "Sin sugerencias (solo BPM/clave/energía)",
    "spotify": "Spotify (búsqueda por género)",
    "lastfm": "Last.fm (tags de género)",
    "llm": "Agente IA con búsqueda web (tu API key)",
}

COLOR_SET: Final[str] = "#2a78d6"  # categórico slot 1 (válido en claro y oscuro)
COLOR_TARGET: Final[str] = "#8a8984"  # referencia neutra
COLOR_BAND: Final[str] = "#8a8984"


@dataclass(slots=True)
class LoadedCollection:
    label: str
    result: ParseResult
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SuggestionConfig:
    """Fuente de canciones reales elegida para el modo propuesta, y sus credenciales."""

    provider: SuggestionProvider = "none"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    lastfm_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = DEFAULT_LLM_MODEL


# --------------------------------------------------------------------------- #
# Carga de datos (cacheada)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_graph() -> SetGraph:
    return build_set_graph()


@st.cache_data(show_spinner="Leyendo colección…", max_entries=4)
def cached_parse(filename: str, data: bytes, digest: str) -> ParseResult:
    del digest  # solo forma parte de la clave de caché
    return parse_file(filename, data)


def demo_collection() -> ParseResult:
    from src.app.__main__ import synthetic_collection

    tracks = synthetic_collection(size=160)
    return ParseResult(source=tracks[0].raw_source.system, tracks=tracks, energy_estimated=len(tracks))


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar_source() -> tuple[SourceMode, LoadedCollection | None]:
    st.sidebar.header("1 · Fuente")
    mode: SourceMode = st.sidebar.radio(
        "¿De dónde salen los temas?",
        options=list(SOURCE_OPTIONS),
        format_func=lambda m: SOURCE_OPTIONS[m],
        key="source_mode",
    )

    loaded: LoadedCollection | None = None
    if mode == "proposal":
        st.sidebar.caption(
            "Sin colección se genera el set ideal slot a slot: BPM, energía y clave Camelot "
            "de cada tema, listo para buscar en tu tienda o crate."
        )
    elif mode == "upload":
        st.sidebar.caption(
            "Formatos: XML de colección de **Rekordbox** · `m.db` de **Engine DJ** · "
            "`collection.nml` de **Traktor** · `database.xml` de **VirtualDJ** · **CSV** "
            "(Serato y cualquier otra app vía exportación)."
        )
        upload = st.sidebar.file_uploader(
            "Archivo de colección", type=list(SUPPORTED_EXTENSIONS), key="collection_file"
        )
        if upload is not None:
            data = upload.getvalue()
            try:
                result = cached_parse(upload.name, data, hashlib.sha256(data).hexdigest())
                loaded = LoadedCollection(label=upload.name, result=result)
            except ValueError as exc:
                st.sidebar.error(str(exc))
    elif mode == "rekordbox_db":
        st.sidebar.warning("Rekordbox tiene que estar **completamente cerrado**: bloquea su base de datos.")
        db_dir = st.sidebar.text_input("Carpeta de la BD (vacío = ubicación por defecto)", key="rb_db_dir")
        if st.sidebar.button("Leer base de datos", key="rb_read"):
            try:
                with st.spinner("Leyendo Rekordbox…"):
                    reader = Rekordbox6DatabaseReader(Path(db_dir) if db_dir.strip() else None)
                    st.session_state["rb_db_result"] = reader.read()
            except RuntimeError as exc:
                st.sidebar.error(str(exc))
        if "rb_db_result" in st.session_state:
            loaded = LoadedCollection(label="Rekordbox 6", result=st.session_state["rb_db_result"])
    else:
        loaded = LoadedCollection(label="Demo sintética (160 temas Tech House)", result=demo_collection())

    if loaded is not None:
        result = loaded.result
        st.sidebar.success(f"{loaded.label}: {len(result.tracks)} temas válidos")
        details = []
        if result.skipped:
            details.append(f"{result.skipped} descartados")
        if result.energy_estimated:
            details.append(f"{result.energy_estimated} con energía estimada por BPM")
        if details:
            st.sidebar.caption(" · ".join(details))
        for warning in result.warnings:
            st.sidebar.caption(f"⚠️ {warning}")
    return mode, loaded


def sidebar_playlist(loaded: LoadedCollection | None) -> list[UniversalTrack]:
    if loaded is None:
        return []
    tracks = loaded.result.tracks
    playlists = {name: ids for name, ids in loaded.result.playlists.items() if ids}
    if not playlists:
        return tracks
    choice = st.sidebar.selectbox(
        "Limitar a una playlist",
        options=["Toda la colección", *sorted(playlists)],
        key="playlist_choice",
    )
    if choice == "Toda la colección":
        return tracks
    wanted = set(playlists[choice])
    return [t for t in tracks if t.id in wanted]


def sidebar_spotify() -> tuple[str, str]:
    """Credenciales de Spotify para el enriquecimiento de una colección (audio-features)."""
    with st.sidebar.expander("🔑 Spotify (opcional)"):
        st.caption(
            "Con credenciales, se sustituye la energía y la clave estimadas por las reales "
            "de Spotify (audio-features)."
        )
        st.caption(
            "Spotify retiró `audio-features` el 27-11-2024: solo responden apps con cuota "
            "ampliada anterior a esa fecha; el resto recibe 403. Si no es tu caso, déjalo "
            "vacío: la app funciona igual con la energía estimada por BPM. Si falla, te "
            "avisará de cuántos temas se quedan sin datos reales."
        )
        client_id = st.text_input("Client ID", type="password", key="spotify_client_id")
        client_secret = st.text_input("Client Secret", type="password", key="spotify_client_secret")
    return client_id.strip(), client_secret.strip()


def sidebar_suggestions() -> SuggestionConfig:
    """
    Elige, para el modo propuesta, de dónde sale el tema real y distinto que se añade a
    cada slot. Nunca toca BPM/clave/energía -esos siguen siendo los del slot, calculados
    por la curva y la ruta armónica-, solo aporta título, artista y enlace reales.
    """
    st.sidebar.header("🎵 Canciones reales (opcional)")
    st.sidebar.caption(
        "Sin elegir fuente, la propuesta se queda con la búsqueda por parámetros de cada "
        "slot (BPM, clave, energía). Con una fuente, además se sugiere un tema real."
    )
    provider: SuggestionProvider = st.sidebar.radio(
        "Fuente de sugerencias",
        options=list(SUGGESTION_PROVIDER_OPTIONS),
        format_func=lambda p: SUGGESTION_PROVIDER_OPTIONS[p],
        key="suggestion_provider",
    )
    cfg = SuggestionConfig(provider=provider)
    if provider == "spotify":
        with st.sidebar.expander("🔑 Spotify", expanded=True):
            st.caption(
                "Búsqueda normal de Spotify, abierta para cualquier app -no hace falta una app "
                "antigua con cuota ampliada-: solo un Client ID y Secret gratis en el "
                "[dashboard de Spotify for Developers](https://developer.spotify.com/dashboard)."
            )
            cfg.spotify_client_id = st.text_input(
                "Client ID", type="password", key="spotify_client_id_proposal"
            ).strip()
            cfg.spotify_client_secret = st.text_input(
                "Client Secret", type="password", key="spotify_client_secret_proposal"
            ).strip()
    elif provider == "lastfm":
        with st.sidebar.expander("🔑 Last.fm", expanded=True):
            st.caption(
                "Alternativa a Spotify: la API key se obtiene al instante y gratis en "
                "[last.fm/api/account/create](https://www.last.fm/api/account/create), sin "
                "aprobación ni cuota especial."
            )
            cfg.lastfm_api_key = st.text_input("API key", type="password", key="lastfm_api_key").strip()
    elif provider == "llm":
        with st.sidebar.expander("🔑 Agente IA (Anthropic)", expanded=True):
            st.caption(
                "Un agente de Claude con búsqueda web real lee la curva completa del set -BPM, "
                "clave, energía y tramo de cada slot- y busca un tema real y coherente para cada "
                "uno en Beatport, 1001Tracklists, Resident Advisor, Spotify y SoundCloud."
            )
            st.caption(
                "Tiene coste por uso (tokens del modelo + ~10 USD por cada 1000 búsquedas web). "
                "Necesitas tu propia API key de "
                "[console.anthropic.com](https://console.anthropic.com/)."
            )
            cfg.llm_api_key = st.text_input(
                "API key de Anthropic", type="password", key="llm_api_key"
            ).strip()
            cfg.llm_model = (
                st.text_input("Modelo", value=DEFAULT_LLM_MODEL, key="llm_model").strip()
                or DEFAULT_LLM_MODEL
            )
    return cfg


# --------------------------------------------------------------------------- #
# Parámetros
# --------------------------------------------------------------------------- #
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())


def phase_editor(profile: EnergyCurveProfile) -> tuple[PhaseSpec, ...]:
    """Un control por tramo: peso en % y rango de energía. Se reinicia al cambiar de perfil."""
    defaults = ENERGY_PROFILES[profile]
    columns = st.columns(len(defaults))
    phases: list[PhaseSpec] = []
    for column, phase in zip(columns, defaults):
        with column:
            st.markdown(f"**{phase_label(phase.name)}**")
            weight = st.number_input(
                "Peso (%)",
                min_value=1,
                max_value=100,
                value=round(phase.weight * 100),
                step=5,
                key=f"w_{profile}_{_slug(phase.name)}",
            )
            low, high = st.slider(
                "Energía",
                min_value=0.0,
                max_value=10.0,
                value=(phase.energy_min, phase.energy_max),
                step=0.5,
                key=f"e_{profile}_{_slug(phase.name)}",
            )
        phases.append(PhaseSpec(name=phase.name, weight=float(weight), energy_min=low, energy_max=high))
    return tuple(phases)


def parameters(mode: SourceMode, pool: Sequence[UniversalTrack]) -> SetConstraint:
    st.subheader("2 · Parámetros del set")

    c1, c2, c3 = st.columns(3)
    with c1:
        duration = st.number_input("Duración (min)", min_value=15, max_value=720, value=60, step=15, key="duration")
    with c2:
        collection_genres = sorted({t.genre for t in pool if t.genre}, key=str.lower)
        options = collection_genres or known_genres()
        genres = st.multiselect(
            "Género(s)",
            options=options,
            default=[],
            accept_new_options=True,
            placeholder="Cualquiera" if pool else "Elige o escribe un género",
            key="genres",
        )
    with c3:
        auto_len = st.toggle("Minutos por tema automáticos", value=bool(pool), key=f"auto_len_{bool(pool)}",
                             help="Automático = mediana de duración de la colección. "
                                  "Manual = tiempo efectivo por tema, descontando solapes de mezcla.")
        avg_len: float | None = None
        if not auto_len:
            avg_len = st.number_input("Minutos por tema", min_value=2.0, max_value=12.0, value=5.0, step=0.5, key=f"avg_len_{bool(pool)}")

    genre_range = genre_bpm_range(genres)
    if pool:
        default_range = (float(min(t.bpm for t in pool)), float(max(t.bpm for t in pool)))
    else:
        default_range = genre_range or DEFAULT_BPM_RANGE

    c4, c5 = st.columns([1, 2])
    with c4:
        limit_bpm = st.toggle("Fijar rango de BPM", value=False, key="limit_bpm",
                              help="Sin fijar se usa el rango de la colección o, sin colección, el típico del género.")
    with c5:
        bpm_min: float | None = None
        bpm_max: float | None = None
        if limit_bpm:
            lo, hi = st.slider(
                "BPM",
                min_value=60.0,
                max_value=200.0,
                # Streamlit exige que min_value/max_value/value/step compartan tipo:
                # round() sin ndigits devuelve int, así que hay que forzarlo a float
                # o el slider lanza StreamlitAPIException al activar el toggle.
                value=(float(round(default_range[0])), float(round(default_range[1]))),
                step=1.0,
                key="bpm_range",
            )
            bpm_min, bpm_max = float(lo), float(hi)
        else:
            source = "colección" if pool else ("género" if genre_range else "por defecto")
            st.caption(f"Rango de BPM ({source}): {default_range[0]:g}–{default_range[1]:g}")

    st.markdown("**Mezcla armónica (rueda Camelot)**")
    c6, c7 = st.columns([2, 1])
    with c6:
        strictness: HarmonicStrictness = st.segmented_control(
            "Rigor armónico",
            options=list(STRICTNESS_OPTIONS),
            format_func=lambda s: STRICTNESS_OPTIONS[s],
            default="energy_boost",
            key="strictness",
            label_visibility="collapsed",
        ) or "energy_boost"
        st.caption(STRICTNESS_HELP[strictness])
    with c7:
        start_key: str | None = None
        if mode == "proposal":
            start_key = st.selectbox("Clave de inicio", CAMELOT_KEYS, index=CAMELOT_KEYS.index("8A"), key="start_key")

    st.markdown("**Curva de energía**")
    profile: EnergyCurveProfile = st.selectbox(
        "Perfil",
        options=list(PROFILE_OPTIONS),
        format_func=lambda p: PROFILE_OPTIONS[p],
        key="profile",
    )
    phases = phase_editor(profile)

    constraints = SetConstraint(
        total_duration_min=int(duration),
        target_genres=list(genres),
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        harmonic_strictness=strictness,
        energy_curve_profile=profile,
        energy_phases=phases,
        start_key=start_key,
        avg_track_duration_min=avg_len,
    )

    candidates = [t for t in pool if t.matches_genres(constraints.target_genres)]
    n_tracks = estimate_track_count(
        constraints.total_duration_sec, candidates, avg_len * 60 if avg_len else None
    )
    if pool:
        st.info(f"⏱️ {duration} min → **{n_tracks} temas**. Candidatos tras filtrar por género: {len(candidates)}.")
    else:
        st.info(f"⏱️ {duration} min → **{n_tracks} slots** en la propuesta.")
    return constraints


# --------------------------------------------------------------------------- #
# Ejecución y resultados
# --------------------------------------------------------------------------- #
def _progress_callback(progress: Any) -> Any:
    def on_progress(done: int, total: int, text: str) -> None:
        progress.progress(done / total, text=text)

    return on_progress


def run_build(
    constraints: SetConstraint,
    pool: Sequence[UniversalTrack],
    spotify: tuple[str, str],
    suggestion: SuggestionConfig | None,
) -> tuple[SetGraphState, EnrichmentReport | SuggestionReport | None]:
    tracks = list(pool)
    report: EnrichmentReport | SuggestionReport | None = None
    client_id, client_secret = spotify

    if tracks and client_id and client_secret:
        candidates = parse_collection_node(initial_state(constraints, tracks))["available_tracks"]
        if len(candidates) > SPOTIFY_MAX_TRACKS:
            st.warning(
                f"Spotify: solo se consultan los primeros {SPOTIFY_MAX_TRACKS} de "
                f"{len(candidates)} candidatos para no agotar la cuota."
            )
            candidates = candidates[:SPOTIFY_MAX_TRACKS]
        progress = st.progress(0.0, text="Consultando Spotify…")
        try:
            enriched, report = enrich_with_spotify(
                candidates, client_id, client_secret, _progress_callback(progress)
            )
            by_id = {t.id: t for t in enriched}
            tracks = [by_id.get(t.id, t) for t in tracks]
        except RuntimeError as exc:
            st.error(str(exc))
        finally:
            progress.empty()

    state = cast(SetGraphState, get_graph().invoke(initial_state(constraints, tracks)))

    if not tracks and suggestion is not None and suggestion.provider != "none" and state.get("selected_set"):
        progress = st.progress(0.0, text="Buscando canciones reales…")
        try:
            if suggestion.provider == "spotify" and suggestion.spotify_client_id and suggestion.spotify_client_secret:
                suggested, report = suggest_tracks_for_proposal(
                    state["selected_set"],
                    constraints.target_genres,
                    suggestion.spotify_client_id,
                    suggestion.spotify_client_secret,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            elif suggestion.provider == "lastfm" and suggestion.lastfm_api_key:
                suggested, report = suggest_tracks_for_proposal_lastfm(
                    state["selected_set"],
                    constraints.target_genres,
                    suggestion.lastfm_api_key,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            elif suggestion.provider == "llm" and suggestion.llm_api_key:
                suggested, report = suggest_tracks_for_proposal_llm(
                    state["selected_set"],
                    suggestion.llm_api_key,
                    suggestion.llm_model,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            else:
                st.warning(
                    "Falta la clave de la fuente de sugerencias elegida: la propuesta se queda "
                    "solo con la búsqueda por parámetros (BPM/clave/energía)."
                )
        except RuntimeError as exc:
            st.error(str(exc))
        finally:
            progress.empty()

    return state, report


def energy_chart(state: SetGraphState) -> alt.LayerChart:
    band, series = curve_frames(state.get("selected_set", []), state.get("target_slots", []))
    x = alt.X("Posición:Q", title="Posición en el set", axis=alt.Axis(tickMinStep=1, grid=False))
    band_layer = (
        alt.Chart(band)
        .mark_area(opacity=0.14, color=COLOR_BAND, interpolate="step-after")
        .encode(x=x, y=alt.Y("Mín:Q", title="Energía", scale=alt.Scale(domain=[0, 10])), y2="Máx:Q")
    )
    color = alt.Color(
        "Serie:N",
        scale=alt.Scale(domain=["Objetivo", "Set"], range=[COLOR_TARGET, COLOR_SET]),
        legend=alt.Legend(orient="top", title=None, symbolType="stroke", symbolStrokeWidth=3),
    )
    tooltip = [
        alt.Tooltip("Posición:Q", title="#"),
        alt.Tooltip("Tramo:N"),
        alt.Tooltip("Serie:N"),
        alt.Tooltip("Energía:Q", format=".1f"),
        alt.Tooltip("BPM:Q", format=".1f"),
        alt.Tooltip("Camelot:N"),
        alt.Tooltip("Tema:N"),
    ]
    lines = (
        alt.Chart(series)
        .mark_line(strokeWidth=2)
        .encode(
            x=x,
            y=alt.Y("Energía:Q", scale=alt.Scale(domain=[0, 10])),
            color=color,
            strokeDash=alt.StrokeDash(
                "Serie:N", scale=alt.Scale(domain=["Objetivo", "Set"], range=[[5, 4], [1, 0]]), legend=None
            ),
        )
    )
    hover = alt.selection_point(fields=["Posición"], nearest=True, on="pointerover", empty=False)
    points = (
        alt.Chart(series)
        .mark_point(filled=True, size=80)
        .encode(
            x=x,
            y="Energía:Q",
            color=color,
            opacity=alt.condition(hover, alt.value(1.0), alt.value(0.75)),
            tooltip=tooltip,
        )
        .add_params(hover)
    )
    rule = (
        alt.Chart(series)
        .mark_rule(color=COLOR_TARGET, strokeWidth=1)
        .encode(x=x, opacity=alt.condition(hover, alt.value(0.5), alt.value(0.0)))
    )
    return cast(alt.LayerChart, (band_layer + lines + rule + points).properties(height=280))


def bpm_chart(state: SetGraphState) -> alt.Chart:
    _, series = curve_frames(state.get("selected_set", []), state.get("target_slots", []))
    data = series[series["Serie"] == "Set"]
    return cast(alt.Chart, (
        alt.Chart(data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=60), strokeWidth=2, color=COLOR_SET)
        .encode(
            x=alt.X("Posición:Q", title="Posición en el set", axis=alt.Axis(tickMinStep=1, grid=False)),
            y=alt.Y("BPM:Q", title="BPM", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Posición:Q", title="#"), "Tramo:N", alt.Tooltip("BPM:Q", format=".1f"), "Camelot:N", "Tema:N"],
        )
        .properties(height=180)
    ))


def results(state: SetGraphState, report: EnrichmentReport | SuggestionReport | None) -> None:
    selected = state.get("selected_set", [])
    slots = state.get("target_slots", [])
    transitions = state.get("transitions", [])
    violations = state.get("violations", [])
    proposal = state.get("mode") == "proposal"

    st.subheader("3 · Resultado")
    if report is not None:
        (st.warning if report.fell_back else st.success)(report.summary())
    if not selected:
        st.error("No se ha podido construir el set.")
        return

    total_sec = sum(t.duration_sec for t in selected)
    valid = sum(1 for tr in transitions if tr.is_valid)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Modo", "Propuesta" if proposal else "Colección")
    m2.metric("Temas", len(selected))
    m3.metric("Duración", f"{total_sec / 60:.0f} min")
    m4.metric("Transiciones OK", f"{valid}/{len(transitions)}")

    if proposal:
        st.info(
            "Propuesta sin colección: cada fila es el tema **ideal** para ese momento del set. "
            "Úsala como guía de búsqueda (BPM, clave y energía) en tu tienda o en tus crates."
        )

    tab_curve, tab_table, tab_notes = st.tabs(["📈 Curva", "📋 Tracklist", "📝 Notas y avisos"])
    with tab_curve:
        st.altair_chart(energy_chart(state), width="stretch")
        st.caption("Área gris: rango de energía permitido en cada tramo. Línea discontinua: objetivo. Línea azul: el set.")
        st.altair_chart(bpm_chart(state), width="stretch")
    with tab_table:
        table = set_table(selected, slots, transitions, proposal)
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "BPM": st.column_config.NumberColumn(format="%.1f"),
                "Energía": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.1f"),
                "Objetivo": st.column_config.NumberColumn(format="%.1f"),
                "Pitch %": st.column_config.NumberColumn(format="%.1f"),
                "Enlace": st.column_config.LinkColumn(display_text="Abrir ↗"),
            },
        )
    with tab_notes:
        st.text(state.get("curator_notes", ""))
        if violations:
            st.markdown("**Avisos**")
            for violation in violations:
                st.markdown(f"- {violation}")
        else:
            st.success("Sin avisos: todas las reglas se cumplen.")

    downloads(selected, slots, transitions, proposal)


def downloads(
    selected: Sequence[UniversalTrack],
    slots: Sequence[Any],
    transitions: Sequence[Any],
    proposal: bool,
) -> None:
    st.markdown("**Exportar**")
    name = st.text_input("Nombre de la playlist", value="SetBuilder", key="export_name")
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇️ CSV",
        data=to_csv(set_rows(selected, slots, transitions)),
        file_name=f"{name}.csv",
        mime="text/csv",
        width="stretch",
    )
    if proposal:
        c2.caption("M3U8 y XML de Rekordbox necesitan temas reales con ruta de archivo.")
        return
    m3u, missing_m3u = to_m3u8(selected, name)
    xml, missing_xml = to_rekordbox_xml(selected, name)
    exportable = len(selected) - missing_m3u
    c2.download_button(
        "⬇️ M3U8 (cualquier software)",
        data=m3u,
        file_name=f"{name}.m3u8",
        mime="audio/x-mpegurl",
        disabled=exportable == 0,
        width="stretch",
    )
    c3.download_button(
        "⬇️ Rekordbox XML",
        data=xml,
        file_name=f"{name}.xml",
        mime="application/xml",
        disabled=len(selected) - missing_xml == 0,
        width="stretch",
    )
    if missing_m3u:
        st.caption(f"{missing_m3u} temas no tienen ruta de archivo y no se incluyen en M3U8/XML.")


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Next-Gen DJ SetBuilder", page_icon="🎧", layout="wide")
    st.title("🎧 Next-Gen DJ SetBuilder")
    st.caption("Un set no es una lista de buenos temas: es una curva. Esta app la construye.")

    mode, loaded = sidebar_source()
    pool = sidebar_playlist(loaded)
    spotify = ("", "")
    suggestion: SuggestionConfig | None = None
    if mode == "proposal":
        suggestion = sidebar_suggestions()
    else:
        spotify = sidebar_spotify()

    if mode != "proposal" and not pool:
        st.info("Carga una colección en la barra lateral, o elige **Sin colección · propuesta**.")
        return

    constraints = parameters(mode, pool)

    if st.button("🚀 Construir set", type="primary", key="build"):
        with st.spinner("Construyendo la curva…"):
            state, report = run_build(constraints, pool, spotify, suggestion)
        st.session_state["last_result"] = (mode, state, report)

    last = st.session_state.get("last_result")
    if last is not None and last[0] == mode:
        _, state, report = last
        results(state, report)


if __name__ == "__main__":
    main()
''',
    'src/core/__init__.py': r'''"""core package."""
''',
    'src/core/energy.py': r'''"""Estimación de energía cuando la fuente no la proporciona (p. ej. Rekordbox)."""

from __future__ import annotations

ENERGY_FLOOR: float = 1.0
ENERGY_CEIL: float = 10.0
BPM_ENERGY_OFFSET: float = 110.0
BPM_ENERGY_DIVISOR: float = 3.0


def estimate_energy_from_bpm(bpm: float) -> float:
    """
    Heurística del proyecto: ``(BPM − 110) / 3`` acotado a 1–10.

    Burda entre géneros, razonable dentro de un mismo género (el caso de uso).
    """
    if bpm <= 0:
        raise ValueError(f"BPM debe ser positivo, recibido {bpm}")
    raw = (bpm - BPM_ENERGY_OFFSET) / BPM_ENERGY_DIVISOR
    return round(min(max(raw, ENERGY_FLOOR), ENERGY_CEIL), 2)
''',
    'src/core/genres.py': r'''"""
Rangos de BPM típicos por género. Se usan cuando no hay colección (modo
propuesta) y el DJ no ha fijado bpm_min/bpm_max.
"""

from __future__ import annotations

from typing import Final, Sequence

DEFAULT_BPM_RANGE: Final[tuple[float, float]] = (120.0, 128.0)

GENRE_BPM_RANGES: Final[dict[str, tuple[float, float]]] = {
    "downtempo": (90.0, 110.0),
    "disco": (110.0, 124.0),
    "nu disco": (112.0, 122.0),
    "deep house": (115.0, 124.0),
    "afro house": (118.0, 124.0),
    "house": (118.0, 126.0),
    "organic house": (112.0, 122.0),
    "melodic house & techno": (120.0, 126.0),
    "melodic techno": (120.0, 126.0),
    "progressive house": (120.0, 128.0),
    "tech house": (122.0, 128.0),
    "minimal": (124.0, 130.0),
    "breaks": (125.0, 135.0),
    "techno": (128.0, 138.0),
    "peak time techno": (130.0, 140.0),
    "trance": (132.0, 140.0),
    "psytrance": (138.0, 146.0),
    "dubstep": (138.0, 142.0),
    "hard techno": (140.0, 155.0),
    "hardstyle": (150.0, 160.0),
    "drum and bass": (170.0, 176.0),
    "drum & bass": (170.0, 176.0),
    "dnb": (170.0, 176.0),
}


def genre_bpm_range(genres: Sequence[str]) -> tuple[float, float] | None:
    """Rango combinado de los géneros conocidos; ``None`` si ninguno lo es."""
    ranges = [GENRE_BPM_RANGES[g.strip().lower()] for g in genres if g.strip().lower() in GENRE_BPM_RANGES]
    if not ranges:
        return None
    return (min(r[0] for r in ranges), max(r[1] for r in ranges))


def known_genres() -> list[str]:
    return sorted({g.title() for g in GENRE_BPM_RANGES if g not in ("dnb", "drum & bass")})
''',
    'src/core/harmonic_engine.py': r'''"""
Harmonic Transition Engine using the Camelot Wheel system.

Calculates compatibility, transition costs, and harmonic relationships
between track keys for intelligent set building algorithms.
"""

from enum import Enum
from typing import Tuple, Optional, Dict, List
import re


class StrictnessLevel(str, Enum):
    STRICT = "strict"              # Perfect harmonic matches or adjacent keys only
    ENERGY_BOOST = "energy_boost"  # Allows harmonic jumps (+1, +2 semitones)
    PERMISSIVE = "permissive"      # Allows wider jumps and experimental transitions


class TransitionType(str, Enum):
    PERFECT = "perfect"                # Same key (e.g., 8A -> 8A)
    ADJACENT = "adjacent"              # +/- 1 on Camelot Wheel (e.g., 8A -> 7A / 9A)
    RELATIVE = "relative"              # Same number, A <-> B (e.g., 8A -> 8B)
    ENERGY_BOOST_1 = "energy_boost_1"  # +1 semitone / +7 Camelot numbers (e.g., 8A -> 3A)
    ENERGY_BOOST_2 = "energy_boost_2"  # +2 semitones / +2 Camelot numbers (e.g., 8A -> 10A)
    ENERGY_DROP = "energy_drop"        # -2 Camelot numbers (e.g., 8A -> 6A)
    DIAGONAL = "diagonal"              # +/- 1 and mode switch (e.g., 8A -> 7B)
    DISCORDANT = "discordant"          # Clashing harmonic jump


class CamelotKey:
    """Represents a Camelot Wheel key notation (1A-12A, 1B-12B)."""
    
    # Mapping standard musical keys to Camelot
    STANDARD_TO_CAMELOT = {
        "Abm": "1A", "G#m": "1A", "B": "1B",
        "Ebm": "2A", "D#m": "2A", "F#": "2B", "Gb": "2B",
        "Bbm": "3A", "A#m": "3A", "Db": "3B", "C#": "3B",
        "Fm": "4A", "Ab": "4B",
        "Cm": "5A", "Eb": "5B",
        "Gm": "6A", "Bb": "6B",
        "Dm": "7A", "F": "7B",
        "Am": "8A", "C": "8B",
        "Em": "9A", "G": "9B",
        "Bm": "10A", "D": "10B",
        "F#m": "11A", "G#": "11B", "A": "11B",
        "C#m": "12A", "Dbm": "12A", "E": "12B"
    }

    def __init__(self, key_str: str):
        normalized = self._normalize_key(key_str)
        if not normalized:
            raise ValueError(f"Invalid harmonic key format: '{key_str}'")
        self.number: int = int(normalized[:-1])
        self.letter: str = normalized[-1].upper()
        self.raw: str = f"{self.number}{self.letter}"

    @classmethod
    def _normalize_key(cls, key_str: str) -> Optional[str]:
        """Parses Camelot (8A) or standard music notation (Am, C) into Camelot format."""
        if not key_str or not isinstance(key_str, str):
            return None
            
        clean_key = key_str.strip()
        
        # Check if already Camelot format (e.g., 8A, 12B)
        match = re.match(r"^([1-9]|1[0-2])([a-bA-B])$", clean_key)
        if match:
            num = match.group(1)
            let = match.group(2).upper()
            return f"{num}{let}"
            
        # Try matching standard musical notation
        return cls.STANDARD_TO_CAMELOT.get(clean_key)

    def __str__(self) -> str:
        return self.raw

    def __eq__(self, other) -> bool:
        if isinstance(other, CamelotKey):
            return self.number == other.number and self.letter == other.letter
        return False


def get_camelot_distance(num1: int, num2: int) -> int:
    """Calculates shortest circular distance on the 1-12 Camelot clock."""
    diff = abs(num1 - num2) % 12
    return min(diff, 12 - diff)


def evaluate_harmonic_transition(
    key_from_str: str, 
    key_to_str: str, 
    strictness: StrictnessLevel = StrictnessLevel.ENERGY_BOOST
) -> Tuple[TransitionType, float]:
    """
    Evaluates the transition quality between two keys.
    
    Returns:
        Tuple[TransitionType, float]: The classified transition type and its cost score 
        (0.0 = perfect transition, 10.0 = severe harmonic conflict).
    """
    try:
        k1 = CamelotKey(key_from_str)
        k2 = CamelotKey(key_to_str)
    except ValueError:
        # Penalty for unparseable key data
        return TransitionType.DISCORDANT, 8.0

    # 1. Perfect Match (8A -> 8A)
    if k1 == k2:
        return TransitionType.PERFECT, 0.0

    same_mode = (k1.letter == k2.letter)
    number_diff = (k2.number - k1.number) % 12  # Forward movement on wheel
    clock_distance = get_camelot_distance(k1.number, k2.number)

    # 2. Relative Scale (8A <-> 8B)
    if clock_distance == 0 and not same_mode:
        return TransitionType.RELATIVE, 0.5

    # 3. Adjacent Fifth (+/- 1) (8A -> 7A / 9A)
    if clock_distance == 1 and same_mode:
        return TransitionType.ADJACENT, 0.2

    # 4. Diagonal Transition (8A -> 7B / 9B)
    if clock_distance == 1 and not same_mode:
        return TransitionType.DIAGONAL, 1.5

    # 5. Energy Boost +2 (+2 semitones / +2 numbers) (e.g., 8A -> 10A)
    if number_diff == 2 and same_mode:
        cost = 1.0 if strictness != StrictnessLevel.STRICT else 4.0
        return TransitionType.ENERGY_BOOST_2, cost

    # 6. Energy Boost +1 (+1 semitone / +7 numbers) (e.g., 8A -> 3A)
    if number_diff == 7 and same_mode:
        cost = 2.0 if strictness != StrictnessLevel.STRICT else 6.0
        return TransitionType.ENERGY_BOOST_1, cost

    # 7. Energy Drop (-2 numbers) (e.g., 8A -> 6A)
    if number_diff == 10 and same_mode:  # -2 mod 12 = 10
        cost = 2.5 if strictness == StrictnessLevel.PERMISSIVE else 5.0
        return TransitionType.ENERGY_DROP, cost

    # 8. Discordant / High Cost Jump
    base_cost = 5.0 + (clock_distance * 1.2)
    if strictness == StrictnessLevel.STRICT:
        base_cost += 3.0

    return TransitionType.DISCORDANT, min(base_cost, 10.0)


def calculate_harmonic_cost(
    key_from: str, 
    key_to: str, 
    strictness: str = "energy_boost"
) -> float:
    """
    Helper function returning only the scalar transition cost (0.0 to 10.0).
    Suitable for A* / Dijkstra graph edge weight calculation.
    """
    try:
        level = StrictnessLevel(strictness)
    except ValueError:
        level = StrictnessLevel.ENERGY_BOOST

    _, cost = evaluate_harmonic_transition(key_from, key_to, level)
    return cost


def get_compatible_keys(key_str: str, max_cost: float = 2.5) -> List[str]:
    """Returns a list of Camelot keys compatible with the given key within a cost threshold."""
    compatible = []
    try:
        base_key = CamelotKey(key_str)
    except ValueError:
        return compatible

    all_keys = [f"{num}{let}" for num in range(1, 13) for let in ["A", "B"]]
    
    for candidate in all_keys:
        cost = calculate_harmonic_cost(base_key.raw, candidate)
        if cost <= max_cost:
            compatible.append(candidate)

    return compatible''',
    'src/core/keys.py': r'''"""
Conversión de tonalidades a notación Camelot.

Acepta:
- Camelot: ``8A``, ``12b``
- Open Key (Traktor): ``1m``, ``6d``
- Clásica: ``Am``, ``F#m``, ``Bb``, ``C# minor``, ``Ebmaj``, ``G♯m``
- Pitch class + modo (Spotify): ``pitch_class_to_camelot(9, minor=True)``

La posición en la rueda se calcula por círculo de quintas en lugar de con una
tabla escrita a mano, así que todos los enarmónicos (G# = Ab, etc.) salen bien.
"""

from __future__ import annotations

import re
from typing import Final

_CAMELOT_RE: Final[re.Pattern[str]] = re.compile(r"^(1[0-2]|[1-9])\s*([ABab])$")
_OPEN_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^(1[0-2]|[1-9])\s*([mdMD])$")
_CLASSIC_RE: Final[re.Pattern[str]] = re.compile(
    r"^([A-Ga-g])\s*([#♯b♭]?)\s*(m|min|minor|maj|major|M)?$"
)

_NATURAL_PITCH: Final[dict[str, int]] = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}


def _wheel_number(value: int) -> int:
    number = value % 12
    return 12 if number == 0 else number


def pitch_class_to_camelot(pitch_class: int, minor: bool) -> str:
    """
    Pitch class (0 = C … 11 = B) + modo → Camelot.

    Mayor: C = 8B y cada quinta suma 1 → ``8 + 7·pc``.
    Menor: la relativa mayor está 3 semitonos arriba → ``5 + 7·pc``.
    """
    if not 0 <= pitch_class <= 11:
        raise ValueError(f"pitch_class fuera de rango: {pitch_class}")
    if minor:
        return f"{_wheel_number(5 + 7 * pitch_class)}A"
    return f"{_wheel_number(8 + 7 * pitch_class)}B"


def camelot_to_pitch_class(key: str) -> tuple[int, int]:
    """
    Camelot → (pitch class 0–11, modo: 1 = mayor, 0 = menor), como espera la
    API de Spotify. Inversa exacta de ``pitch_class_to_camelot``.
    """
    match = _CAMELOT_RE.match(key.strip())
    if not match:
        raise ValueError(f"Clave Camelot inválida: '{key}'")
    number = int(match.group(1))
    if match.group(2).upper() == "B":
        return (7 * (number - 8)) % 12, 1
    return (7 * (number - 5)) % 12, 0


def to_camelot(value: str | None) -> str | None:
    """Normaliza cualquier notación soportada a Camelot; ``None`` si no se reconoce."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    if match := _CAMELOT_RE.match(text):
        return f"{int(match.group(1))}{match.group(2).upper()}"

    if match := _OPEN_KEY_RE.match(text):
        number = _wheel_number(int(match.group(1)) + 7)
        mode = "A" if match.group(2).lower() == "m" else "B"
        return f"{number}{mode}"

    if match := _CLASSIC_RE.match(text):
        letter, accidental, quality = match.groups()
        pitch = _NATURAL_PITCH[letter.upper()]
        if accidental in ("#", "♯"):
            pitch += 1
        elif accidental in ("b", "♭"):
            pitch -= 1
        minor = quality is not None and quality.lower() in ("m", "min", "minor") and quality != "M"
        return pitch_class_to_camelot(pitch % 12, minor)

    return None
''',
    'src/core/models.py': r'''"""
Modelos de dominio agnósticos del fabricante.

Ningún componente interno (core, graph, app) debe conocer el formato nativo de
Pioneer, Denon, Native Instruments o Serato: los parsers de ``src/parsers``
traducen cada colección a ``UniversalTrack`` y, a partir de ahí, todo el
sistema trabaja sobre estos modelos.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from src.core.harmonic_engine import TransitionType

CAMELOT_PATTERN: re.Pattern[str] = re.compile(r"^(1[0-2]|[1-9])[AB]$")

HarmonicStrictness = Literal["strict", "energy_boost", "permissive"]
EnergyCurveProfile = Literal["warmup_to_peak", "rollercoaster", "constant"]


class TrackSource(str, Enum):
    """Ecosistema del que procede un track."""

    REKORDBOX = "rekordbox"
    ENGINE_DJ = "engine_dj"
    TRAKTOR = "traktor"
    SERATO = "serato"
    VIRTUALDJ = "virtualdj"
    M3U8 = "m3u8"
    CSV = "csv"
    SYNTHETIC = "synthetic"


class RawSource(BaseModel):
    """
    Referencia opaca al registro original.

    Se conserva para poder exportar de vuelta al formato nativo, pero el core
    nunca lee ``payload``: solo los parsers y exporters lo interpretan.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: TrackSource
    native_id: str | None = None
    location: str | None = Field(default=None, description="Ruta o URI del fichero de audio.")
    payload: dict[str, Any] = Field(default_factory=dict)


class UniversalTrack(BaseModel):
    """Track normalizado, independiente del software de origen."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artist: str = Field(default="Unknown Artist")
    bpm: float = Field(gt=0.0, le=300.0)
    key: str = Field(description="Tonalidad en notación Camelot (1A–12B).")
    energy: float = Field(ge=0.0, le=10.0)
    duration_sec: int = Field(gt=0)
    genre: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)
    raw_source: RawSource = Field(
        default_factory=lambda: RawSource(system=TrackSource.SYNTHETIC)
    )

    @field_validator("key", mode="before")
    @classmethod
    def _normalize_and_validate_key(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError("key debe ser un string en notación Camelot")
        normalized = value.strip().upper()
        if not CAMELOT_PATTERN.fullmatch(normalized):
            raise ValueError(
                f"Clave Camelot inválida: '{value}'. Formato esperado 1A–12A / 1B–12B."
            )
        return normalized

    @field_validator("genre", mode="before")
    @classmethod
    def _normalize_genre(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        seen: dict[str, None] = {}
        for tag in value:
            clean = str(tag).strip().lower()
            if clean:
                seen.setdefault(clean, None)
        return tuple(seen)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def camelot_number(self) -> int:
        return int(self.key[:-1])

    @computed_field  # type: ignore[prop-decorator]
    @property
    def camelot_mode(self) -> Literal["A", "B"]:
        return "A" if self.key.endswith("A") else "B"

    @property
    def duration_min(self) -> float:
        return self.duration_sec / 60.0

    def matches_genres(self, genres: list[str]) -> bool:
        """Coincidencia case-insensitive; una lista vacía acepta cualquier género."""
        if not genres:
            return True
        if self.genre is None:
            return False
        wanted = {g.strip().lower() for g in genres}
        return self.genre.lower() in wanted

    def dedupe_key(self) -> str:
        """
        Clave para detectar el mismo tema aunque tenga un ``id`` distinto.

        Las bibliotecas de DJ acumulan duplicados reales: el mismo archivo
        importado dos veces recibe un TrackID distinto en cada copia. Con
        ruta de archivo, dos tracks son el mismo tema si apuntan al mismo
        fichero; sin ruta, se comparan título, artista y BPM redondeado.
        """
        location = self.raw_source.location
        if location:
            return f"loc:{location.strip().lower()}"
        return f"meta:{self.title.strip().lower()}|{self.artist.strip().lower()}|{round(self.bpm)}"

    def __hash__(self) -> int:
        return hash((self.raw_source.system, self.id))


class PhaseSpec(BaseModel):
    """Tramo del set: peso relativo en la duración y rango de energía objetivo."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    weight: float = Field(gt=0.0, le=100.0, description="Peso relativo; se normaliza.")
    energy_min: float = Field(ge=0.0, le=10.0)
    energy_max: float = Field(ge=0.0, le=10.0)

    @model_validator(mode="after")
    def _check_energy_range(self) -> PhaseSpec:
        if self.energy_min > self.energy_max:
            raise ValueError(
                f"Tramo '{self.name}': energy_min ({self.energy_min}) > energy_max ({self.energy_max})"
            )
        return self


class SetConstraint(BaseModel):
    """Parámetros que el DJ define para el set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_duration_min: int = Field(gt=0, le=720)
    target_genres: list[str] = Field(default_factory=list)
    bpm_min: float | None = Field(default=None, gt=0.0, le=300.0)
    bpm_max: float | None = Field(default=None, gt=0.0, le=300.0)
    harmonic_strictness: HarmonicStrictness = "energy_boost"
    energy_curve_profile: EnergyCurveProfile = "warmup_to_peak"
    energy_phases: tuple[PhaseSpec, ...] | None = Field(
        default=None,
        description="Tramos personalizados; si se indican, sustituyen al perfil.",
    )
    start_key: str | None = Field(
        default=None,
        description="Clave Camelot de arranque para el modo propuesta (sin colección).",
    )
    avg_track_duration_min: float | None = Field(
        default=None,
        gt=0.5,
        le=20.0,
        description="Minutos efectivos por tema; None = mediana de la colección.",
    )

    @field_validator("target_genres", mode="before")
    @classmethod
    def _clean_genres(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(g).strip() for g in value if str(g).strip()]

    @model_validator(mode="after")
    def _check_bpm_range(self) -> SetConstraint:
        if self.bpm_min is not None and self.bpm_max is not None and self.bpm_min > self.bpm_max:
            raise ValueError(
                f"bpm_min ({self.bpm_min}) no puede ser mayor que bpm_max ({self.bpm_max})"
            )
        return self

    @field_validator("start_key", mode="before")
    @classmethod
    def _validate_start_key(cls, value: Any) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        normalized = str(value).strip().upper()
        if not CAMELOT_PATTERN.fullmatch(normalized):
            raise ValueError(f"start_key inválida: '{value}'. Formato esperado 1A–12B.")
        return normalized

    @field_validator("energy_phases")
    @classmethod
    def _check_phases(
        cls, value: tuple[PhaseSpec, ...] | None
    ) -> tuple[PhaseSpec, ...] | None:
        if value is not None and len(value) == 0:
            raise ValueError("energy_phases no puede estar vacío; usa None para el perfil")
        return value

    @property
    def total_duration_sec(self) -> int:
        return self.total_duration_min * 60


class TransitionEvaluation(BaseModel):
    """Resultado de evaluar la mezcla Track_n → Track_n+1 (peso de arista del grafo)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_track_id: str
    to_track_id: str
    cost: float = Field(ge=0.0)
    transition_type: TransitionType
    bpm_delta: float = Field(description="BPM destino − BPM origen (con half/double-time resuelto).")
    bpm_delta_pct: float = Field(ge=0.0, description="Pitch necesario en % respecto al origen.")
    energy_delta: float
    is_valid: bool
''',
    'src/core/proposal.py': r'''"""
Modo propuesta: sin colección de entrada, genera un plan de set slot a slot.

Cada slot se convierte en un ``UniversalTrack`` de marcador (fuente SYNTHETIC)
con el BPM, la energía, la duración y la clave Camelot que debería tener el
tema ideal. Las claves siguen una ruta armónica que respeta el rigor pedido y
acompaña la curva: si la energía sube, la rueda avanza (+1, o +2 si se permiten
energy boosts); si baja, retrocede; si se mantiene, alterna relativa y adyacente.
"""

from __future__ import annotations

from typing import Final, Sequence

from src.core.harmonic_engine import StrictnessLevel, evaluate_harmonic_transition
from src.core.models import (
    HarmonicStrictness,
    RawSource,
    SetConstraint,
    TrackSource,
    UniversalTrack,
)
from src.core.timeline import TimelineSlot
from src.core.transitions import ALLOWED_HARMONIC_TYPES

DEFAULT_START_KEY: Final[str] = "8A"
BIG_STEP: Final[float] = 1.0
SMALL_STEP: Final[float] = 0.25
PROPOSAL_ARTIST: Final[str] = "Propuesta"


def shift_key(key: str, steps: int = 0, switch_mode: bool = False) -> str:
    """Mueve ``steps`` posiciones en la rueda y opcionalmente cambia A↔B."""
    number = int(key[:-1])
    mode = key[-1]
    new_number = (number - 1 + steps) % 12 + 1
    if switch_mode:
        mode = "B" if mode == "A" else "A"
    return f"{new_number}{mode}"


def _candidate_moves(energy_delta: float, index: int) -> list[tuple[int, bool]]:
    """Movimientos preferidos (pasos, cambio de modo) según la dirección de la energía."""
    if energy_delta > BIG_STEP:
        return [(2, False), (1, False), (0, False)]
    if energy_delta > SMALL_STEP:
        return [(1, False), (0, False)]
    if energy_delta < -BIG_STEP:
        return [(-2, False), (-1, False), (0, False)]
    if energy_delta < -SMALL_STEP:
        return [(-1, False), (0, False)]
    if index % 2:
        return [(0, True), (0, False)]
    return [(1, False), (0, False)]


def plan_key_path(
    slots: Sequence[TimelineSlot],
    strictness: HarmonicStrictness,
    start_key: str | None = None,
) -> list[str]:
    """Una clave por slot; cada paso es una transición válida para ``strictness``."""
    if not slots:
        return []
    allowed = ALLOWED_HARMONIC_TYPES[strictness]
    keys = [start_key or DEFAULT_START_KEY]
    for index in range(1, len(slots)):
        current = keys[-1]
        delta = slots[index]["target_energy"] - slots[index - 1]["target_energy"]
        chosen = current
        for steps, switch in _candidate_moves(delta, index):
            candidate = shift_key(current, steps, switch)
            kind, _ = evaluate_harmonic_transition(current, candidate, StrictnessLevel(strictness))
            if kind in allowed:
                chosen = candidate
                break
        keys.append(chosen)
    return keys


def build_proposal_tracks(
    slots: Sequence[TimelineSlot], constraints: SetConstraint
) -> list[UniversalTrack]:
    """Marcadores de tema ideal por slot, listos para pasar por el resto del grafo."""
    keys = plan_key_path(slots, constraints.harmonic_strictness, constraints.start_key)
    genre = constraints.target_genres[0] if constraints.target_genres else None
    tracks: list[UniversalTrack] = []
    for slot, key in zip(slots, keys):
        bpm = round(slot["target_bpm"] * 2) / 2
        energy = round(slot["target_energy"], 1)
        hint = f"{genre or 'cualquier género'} · {bpm:g} BPM · {key} · energía {energy:g}"
        tracks.append(
            UniversalTrack(
                id=f"slot-{slot['index'] + 1:02d}",
                title=f"Slot {slot['index'] + 1} · {slot['phase']}",
                artist=PROPOSAL_ARTIST,
                bpm=bpm,
                key=key,
                energy=energy,
                duration_sec=max(1, slot["end_sec"] - slot["start_sec"]),
                genre=genre,
                tags=("propuesta", slot["phase"]),
                raw_source=RawSource(
                    system=TrackSource.SYNTHETIC,
                    native_id=f"slot-{slot['index'] + 1:02d}",
                    payload={"search_hint": hint},
                ),
            )
        )
    return tracks
''',
    'src/core/timeline.py': r'''"""
Construcción de la curva del set: reparte la duración en tramos (fases) y
genera un slot por track con BPM y energía objetivo.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Final, Sequence, TypedDict

from src.core.genres import DEFAULT_BPM_RANGE, genre_bpm_range
from src.core.models import EnergyCurveProfile, PhaseSpec, SetConstraint, UniversalTrack

DEFAULT_TRACK_DURATION_SEC: Final[int] = 360

Phase = PhaseSpec


ENERGY_PROFILES: Final[dict[str, tuple[Phase, ...]]] = {
    "warmup_to_peak": (
        Phase(name="warmup", weight=0.25, energy_min=2.0, energy_max=5.0),
        Phase(name="peak_time", weight=0.50, energy_min=7.0, energy_max=10.0),
        Phase(name="closing", weight=0.25, energy_min=4.0, energy_max=6.5),
    ),
    "rollercoaster": (
        Phase(name="warmup", weight=0.15, energy_min=3.0, energy_max=5.0),
        Phase(name="build", weight=0.20, energy_min=6.0, energy_max=8.0),
        Phase(name="breather", weight=0.15, energy_min=4.0, energy_max=6.0),
        Phase(name="peak_time", weight=0.30, energy_min=8.0, energy_max=10.0),
        Phase(name="closing", weight=0.20, energy_min=4.0, energy_max=6.5),
    ),
    "constant": (Phase(name="sustain", weight=1.0, energy_min=6.0, energy_max=8.0),),
}


class TimelineSlot(TypedDict):
    index: int
    phase: str
    start_sec: int
    end_sec: int
    target_bpm: float
    energy_min: float
    energy_max: float
    target_energy: float


def estimate_track_count(
    total_duration_sec: int,
    candidates: Sequence[UniversalTrack],
    avg_track_duration_sec: float | None = None,
) -> int:
    """
    Nº de temas necesarios. Usa la duración media indicada por el DJ (tiempo
    efectivo por tema, descontando solapes de mezcla) o, si no la hay, la
    mediana de duración de los candidatos.
    """
    if avg_track_duration_sec is not None:
        typical: float = avg_track_duration_sec
    elif candidates:
        typical = median(t.duration_sec for t in candidates)
    else:
        typical = DEFAULT_TRACK_DURATION_SEC
    return max(1, math.ceil(total_duration_sec / typical))


def resolve_phases(constraints: SetConstraint) -> tuple[PhaseSpec, ...]:
    """Tramos personalizados si existen; si no, los del perfil elegido."""
    return constraints.energy_phases or ENERGY_PROFILES[constraints.energy_curve_profile]


def resolve_bpm_range(
    constraints: SetConstraint, candidates: Sequence[UniversalTrack]
) -> tuple[float, float]:
    """
    Prioridad: rango del usuario → rango real de la colección → rango típico
    del género (modo propuesta) → rango por defecto.
    """
    if candidates:
        pool_min = min(t.bpm for t in candidates)
        pool_max = max(t.bpm for t in candidates)
    else:
        pool_min, pool_max = genre_bpm_range(constraints.target_genres) or DEFAULT_BPM_RANGE
    low = constraints.bpm_min if constraints.bpm_min is not None else pool_min
    high = constraints.bpm_max if constraints.bpm_max is not None else pool_max
    return (min(low, high), max(low, high))


def allocate_slot_counts(phases: Sequence[Phase], total_slots: int) -> list[int]:
    """
    Reparto por mayor resto: la suma es exactamente ``total_slots``.
    Los pesos se normalizan, así que no hace falta que sumen 1.
    """
    total_weight = sum(p.weight for p in phases)
    raw = [p.weight / total_weight * total_slots for p in phases]
    counts = [math.floor(r) for r in raw]
    remainder = total_slots - sum(counts)
    order = sorted(range(len(phases)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1
    return counts


def build_timeline(
    constraints: SetConstraint,
    candidates: Sequence[UniversalTrack],
    profile: EnergyCurveProfile | None = None,
) -> list[TimelineSlot]:
    phases = ENERGY_PROFILES[profile] if profile else resolve_phases(constraints)
    total_sec = constraints.total_duration_sec
    avg_sec = (
        constraints.avg_track_duration_min * 60.0
        if constraints.avg_track_duration_min is not None
        else None
    )
    n_slots = estimate_track_count(total_sec, candidates, avg_sec)
    slot_len = total_sec / n_slots
    bpm_low, bpm_high = resolve_bpm_range(constraints, candidates)

    slots: list[TimelineSlot] = []
    index = 0
    for phase, count in zip(phases, allocate_slot_counts(phases, n_slots)):
        if count == 0:
            continue
        for k in range(count):
            # Rampa lineal dentro del tramo: del mínimo al máximo de energía.
            progress = (k + 0.5) / count
            target_energy = phase.energy_min + progress * (phase.energy_max - phase.energy_min)
            target_bpm = bpm_low + (target_energy / 10.0) * (bpm_high - bpm_low)
            slots.append(
                TimelineSlot(
                    index=index,
                    phase=phase.name,
                    start_sec=round(index * slot_len),
                    end_sec=round((index + 1) * slot_len),
                    target_bpm=round(target_bpm, 2),
                    energy_min=phase.energy_min,
                    energy_max=phase.energy_max,
                    target_energy=round(target_energy, 2),
                )
            )
            index += 1
    return slots
''',
    'src/core/transitions.py': r'''"""
Evaluación de transiciones entre dos ``UniversalTrack``.

Combina el coste armónico (``harmonic_engine``) con el coste de tempo y de
energía. El resultado (``TransitionEvaluation.cost``) es el peso de arista que
usarán los algoritmos de búsqueda (greedy hoy, Dijkstra/A* después).
"""

from __future__ import annotations

from typing import Final

from src.core.harmonic_engine import (
    StrictnessLevel,
    TransitionType,
    evaluate_harmonic_transition,
)
from src.core.models import HarmonicStrictness, TransitionEvaluation, UniversalTrack

# Pitch máximo aceptable (%) según el rigor pedido.
MAX_BPM_DELTA_PCT: Final[dict[str, float]] = {
    "strict": 4.0,
    "energy_boost": 6.0,
    "permissive": 8.0,
}

# Tipos armónicos aceptados según el rigor pedido.
ALLOWED_HARMONIC_TYPES: Final[dict[str, frozenset[TransitionType]]] = {
    "strict": frozenset(
        {TransitionType.PERFECT, TransitionType.ADJACENT, TransitionType.RELATIVE}
    ),
    "energy_boost": frozenset(
        {
            TransitionType.PERFECT,
            TransitionType.ADJACENT,
            TransitionType.RELATIVE,
            TransitionType.DIAGONAL,
            TransitionType.ENERGY_BOOST_1,
            TransitionType.ENERGY_BOOST_2,
        }
    ),
    "permissive": frozenset(t for t in TransitionType if t is not TransitionType.DISCORDANT),
}

BPM_COST_PER_PCT: Final[float] = 0.5
ENERGY_COST_PER_POINT: Final[float] = 0.3
INVALID_PENALTY: Final[float] = 25.0
TEMPO_RATIOS: Final[tuple[float, ...]] = (1.0, 0.5, 2.0)


def effective_bpm_delta(bpm_from: float, bpm_to: float) -> tuple[float, float]:
    """
    Devuelve (delta_bpm, delta_pct) resolviendo half/double-time
    (p. ej. 87 → 174 en DnB/halftime cuenta como 0 %).
    """
    best_delta = bpm_to - bpm_from
    best_pct = abs(best_delta) / bpm_from * 100.0
    for ratio in TEMPO_RATIOS[1:]:
        delta = bpm_to * ratio - bpm_from
        pct = abs(delta) / bpm_from * 100.0
        if pct < best_pct:
            best_delta, best_pct = delta, pct
    return round(best_delta, 3), round(best_pct, 3)


def evaluate_transition(
    track_from: UniversalTrack,
    track_to: UniversalTrack,
    strictness: HarmonicStrictness = "energy_boost",
) -> TransitionEvaluation:
    """Calcula tipo, coste y validez de la mezcla ``track_from → track_to``."""
    harmonic_type, harmonic_cost = evaluate_harmonic_transition(
        track_from.key, track_to.key, StrictnessLevel(strictness)
    )
    bpm_delta, bpm_delta_pct = effective_bpm_delta(track_from.bpm, track_to.bpm)
    energy_delta = round(track_to.energy - track_from.energy, 3)

    harmonic_ok = harmonic_type in ALLOWED_HARMONIC_TYPES[strictness]
    tempo_ok = bpm_delta_pct <= MAX_BPM_DELTA_PCT[strictness]
    is_valid = harmonic_ok and tempo_ok

    cost = (
        harmonic_cost
        + bpm_delta_pct * BPM_COST_PER_PCT
        + abs(energy_delta) * ENERGY_COST_PER_POINT
        + (0.0 if is_valid else INVALID_PENALTY)
    )

    return TransitionEvaluation(
        from_track_id=track_from.id,
        to_track_id=track_to.id,
        cost=round(cost, 4),
        transition_type=harmonic_type,
        bpm_delta=bpm_delta,
        bpm_delta_pct=bpm_delta_pct,
        energy_delta=energy_delta,
        is_valid=is_valid,
    )
''',
    'src/enrichment/__init__.py': r'''"""Enriquecimiento opcional de metadatos desde servicios externos."""

from src.enrichment.spotify import EnrichmentReport, enrich_with_spotify

__all__ = ["EnrichmentReport", "enrich_with_spotify"]
''',
    'src/enrichment/common.py': r'''"""
Tipos y utilidades compartidas por los proveedores de sugerencias de temas
reales para el modo propuesta (``spotify.py``, ``lastfm.py``, ``llm_agent.py``).

Los tres proveedores devuelven la misma forma -``(list[UniversalTrack],
SuggestionReport)``- para que la UI y los exportadores no necesiten saber
cuál se usó: el tema real sugerido vive en ``raw_source.payload`` bajo las
claves ``suggested_artist`` / ``suggested_title`` / ``suggested_url`` /
``suggested_source``, sin prefijo de proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from src.core.models import UniversalTrack

ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class SuggestionReport:
    attempted: int = 0
    suggested: int = 0
    failed: int = 0
    first_error: str = ""
    source: str = ""

    @property
    def fell_back(self) -> int:
        """Slots que se quedan solo con el marcador BPM/clave/energía."""
        return self.attempted - self.suggested

    def summary(self) -> str:
        prefix = f"{self.source}: " if self.source else ""
        text = (
            f"{prefix}{self.suggested}/{self.attempted} slots con una canción real sugerida. "
            f"{self.fell_back} se quedan con la búsqueda por parámetros (BPM/clave/energía)."
        )
        if self.first_error:
            text += f" Primer error: {self.first_error}"
        return text


def search_query_terms(genres: Sequence[str], fallback: str = "electronic") -> list[str]:
    """
    Términos a probar en orden: primero los géneros tal cual los escribió el
    usuario (más específicos), luego un término genérico de reserva.
    """
    terms = [g.strip() for g in genres if g.strip()]
    if fallback.lower() not in (t.lower() for t in terms):
        terms.append(fallback)
    return terms


def assign_candidates(
    placeholders: Sequence[UniversalTrack],
    candidates: Sequence[dict[str, str]],
    report: SuggestionReport,
) -> list[UniversalTrack]:
    """
    Reparte los candidatos reales (``{"artist", "title", "url"}``) uno a uno
    sobre los marcadores de la propuesta, en orden. Nunca toca BPM/clave/
    energía. Un marcador sin candidato disponible conserva el suyo tal cual.
    """
    suggested: list[UniversalTrack] = []
    for index, track in enumerate(placeholders):
        if index >= len(candidates):
            suggested.append(track)
            continue
        pick = candidates[index]
        report.suggested += 1
        payload: dict[str, Any] = {
            **track.raw_source.payload,
            "suggested_artist": pick["artist"],
            "suggested_title": pick["title"],
            "suggested_source": report.source,
        }
        if pick.get("url"):
            payload["suggested_url"] = pick["url"]
        suggested.append(
            track.model_copy(update={"raw_source": track.raw_source.model_copy(update={"payload": payload})})
        )
    return suggested
''',
    'src/enrichment/lastfm.py': r'''"""
Sugerencia de temas reales para el modo propuesta usando Last.fm (opcional).

Alternativa a Spotify: Last.fm no exige aprobación ni cuota especial -la
``api_key`` se obtiene al instante y gratis en
https://www.last.fm/api/account/create-, y su sistema de tags cubre
microgéneros electrónicos ("tech house", "melodic techno"…) tan bien como
Spotify o mejor.

Usa ``tag.getTopTracks`` (https://www.last.fm/api/show/tag.getTopTracks):
para un tag de género, devuelve los temas más etiquetados con él, ordenados
por peso del tag. Un único endpoint, sin autenticación de usuario, sin el
paso adicional de artistas que hace falta en Spotify. Verificado contra la
documentación oficial el 25-09-2026: parámetros ``tag`` + ``api_key``
(requeridos), ``limit``/``page`` (opcionales); respuesta
``{"tracks": {"track": [{"name", "artist": {"name", ...}, "url", ...}]}}``.

Igual que con Spotify: no filtra por tempo ni tonalidad, así que la
sugerencia es un tema real del género correcto, no uno verificado nota a
nota contra el BPM del slot. El BPM, la clave y la energía del slot -los que
respetan la curva y la ruta armónica- nunca cambian.
"""

from __future__ import annotations

from typing import Any, Callable, Final, Sequence

from src.core.models import UniversalTrack
from src.enrichment.common import ProgressCallback, SuggestionReport, assign_candidates, search_query_terms

LASTFM_API_URL: Final[str] = "http://ws.audioscrobbler.com/2.0/"
LASTFM_PAGE: Final[int] = 50
LASTFM_MAX_PAGES_PER_TERM: Final[int] = 4

LastfmCall = Callable[..., dict[str, Any]]


def _make_client(api_key: str) -> LastfmCall:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "requests no está instalado. Instálalo con: pip install -e '.[lastfm]'"
        ) from exc

    def call(method: str, **params: str) -> dict[str, Any]:
        response = requests.get(
            LASTFM_API_URL,
            params={"method": method, "api_key": api_key, "format": "json", **params},
            timeout=10,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise RuntimeError(f"Last.fm: {data.get('message', 'error desconocido')} (código {data['error']})")
        return data

    return call


def _tracks_for_tag(call: LastfmCall, tag: str, page: int) -> list[dict[str, Any]]:
    data = call("tag.gettoptracks", tag=tag, limit=str(LASTFM_PAGE), page=str(page))
    items = (data.get("tracks") or {}).get("track") or []
    if isinstance(items, dict):
        # Last.fm devuelve un objeto suelto, no una lista, cuando solo hay un resultado.
        items = [items]
    return list(items)


def _track_from_item(item: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
    title = item.get("name")
    artist = (item.get("artist") or {}).get("name")
    if not (title and artist):
        return None
    key = f"{artist.strip().lower()}::{title.strip().lower()}"
    return key, {"artist": artist, "title": title, "url": item.get("url", "")}


def _search_candidates(
    call: LastfmCall, terms: Sequence[str], needed: int, progress: ProgressCallback | None
) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(1, LASTFM_MAX_PAGES_PER_TERM + 1):
            if len(seen) >= needed:
                break
            if progress:
                progress(min(len(seen) + 1, needed), needed, f"Buscando temas de {term} en Last.fm…")
            items = _tracks_for_tag(call, term, page)
            if not items:
                break
            for item in items:
                if len(seen) >= needed:
                    break
                parsed = _track_from_item(item)
                if parsed and parsed[0] not in seen:
                    seen[parsed[0]] = parsed[1]
    return list(seen.values())[:needed]


def suggest_tracks_for_proposal_lastfm(
    placeholders: Sequence[UniversalTrack],
    genres: Sequence[str],
    api_key: str,
    progress: ProgressCallback | None = None,
    client: LastfmCall | None = None,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Busca, para cada término de género, los temas más etiquetados con ese tag
    en Last.fm y sustituye el nombre/artista de cada marcador por uno real y
    distinto. Nunca cambia el BPM/clave/energía del slot: solo añade el
    título, artista y enlace reales al ``payload`` del marcador. Si no hay
    bastantes temas distintos, o la llamada falla, los slots restantes
    conservan su marcador sintético tal cual.
    """
    report = SuggestionReport(attempted=len(placeholders), source="Last.fm")
    if not placeholders:
        return [], report
    call = client if client is not None else _make_client(api_key)
    terms = search_query_terms(genres)

    try:
        candidates = _search_candidates(call, terms, len(placeholders), progress)
    except Exception as exc:
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    return assign_candidates(placeholders, candidates, report), report
''',
    'src/enrichment/llm_agent.py': r'''"""
Sugerencia de temas reales para el modo propuesta usando un agente de Claude
con búsqueda web (opcional, requiere una API key de Anthropic propia).

A diferencia de Spotify y Last.fm -que solo emparejan por *tag* de género-,
este agente recibe la curva completa de la propuesta (BPM, clave, energía y
tramo de cada slot, en orden) en una sola llamada y busca en la web
(Beatport, 1001Tracklists, Resident Advisor, Spotify, SoundCloud) un tema
real y coherente con esa curva para cada slot, no solo con el género.

Usa la herramienta de búsqueda web integrada de la API de Mensajes de Claude
(https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool,
verificado el 25-09-2026): un bloque ``{"type": "web_search_20250305",
"name": "web_search"}`` en ``tools``, sin que el código tenga que implementar
la búsqueda ni el scraping -los hace el propio modelo, servidor a servidor-.

Tiene coste (tokens del modelo + ~10 USD por cada 1000 búsquedas web), y
requiere que el usuario pegue su propia API key de
https://console.anthropic.com/ en la barra lateral: por eso es opt-in y
nunca se activa por defecto ni comparte esa clave con nada más que la
llamada a la API de Anthropic.
"""

from __future__ import annotations

import json
from typing import Any, Final, Sequence

from src.core.models import UniversalTrack
from src.enrichment.common import ProgressCallback, SuggestionReport

DEFAULT_MODEL: Final[str] = "claude-sonnet-5"
WEB_SEARCH_TOOL: Final[str] = "web_search_20250305"
MAX_SEARCHES: Final[int] = 25
DEFAULT_ALLOWED_DOMAINS: Final[tuple[str, ...]] = (
    "beatport.com",
    "1001tracklists.com",
    "residentadvisor.net",
    "open.spotify.com",
    "soundcloud.com",
)

_SYSTEM_PROMPT = (
    "Eres un digger de música electrónica que ayuda a un DJ a completar un set. "
    "Para cada slot recibirás el género, el tramo del set (warmup/peak_time/closing…), "
    "el BPM objetivo, la clave Camelot objetivo y la energía objetivo (1-10). "
    "Busca en la web (Beatport, 1001Tracklists, Resident Advisor, Spotify, SoundCloud) "
    "un tema REAL, publicado, que encaje con esos parámetros para cada slot -nunca "
    "inventes un artista o título; si no encuentras algo perfecto, elige el tema real más "
    "cercano de ese género y tramo en vez de inventar uno-. No repitas el mismo tema en dos "
    "slots distintos. Responde ÚNICAMENTE con un array JSON, sin texto antes ni después, con "
    "un objeto por slot EN EL MISMO ORDEN en que te los he dado: "
    '[{"artist": "...", "title": "...", "url": "..."}, ...]. '
    'Si de verdad no encuentras nada razonable para un slot, usa {"artist": null, "title": null} '
    "en esa posición, sin saltártela."
)


def _slot_line(track: UniversalTrack, index: int) -> str:
    phase = track.tags[1] if len(track.tags) > 1 else ""
    return (
        f"{index + 1}. género={track.genre or 'cualquiera'} · tramo={phase} · "
        f"bpm={track.bpm:g} · clave={track.key} · energía={track.energy:g}"
    )


def _make_client(api_key: str) -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "El paquete 'anthropic' no está instalado. Instálalo con: pip install -e '.[agent]'"
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type", ""))
    return str(getattr(block, "type", "") or "")


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text", ""))
    return str(getattr(block, "text", "") or "")


def _extract_json_array(text: str) -> list[Any]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("la respuesta del agente no contiene un array JSON reconocible")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("la respuesta del agente no es un array JSON")
    return parsed


def _parse_candidates(picks: Sequence[Any]) -> list[dict[str, str] | None]:
    """Valida cada elemento del array del agente; descarta inventos y repetidos."""
    seen: set[str] = set()
    candidates: list[dict[str, str] | None] = []
    for pick in picks:
        if not isinstance(pick, dict):
            candidates.append(None)
            continue
        artist, title = pick.get("artist"), pick.get("title")
        if not (isinstance(artist, str) and isinstance(title, str) and artist.strip() and title.strip()):
            candidates.append(None)
            continue
        dedupe_key = f"{artist.strip().lower()}::{title.strip().lower()}"
        if dedupe_key in seen:
            candidates.append(None)
            continue
        seen.add(dedupe_key)
        url = pick.get("url")
        candidates.append(
            {"artist": artist.strip(), "title": title.strip(), "url": url.strip() if isinstance(url, str) else ""}
        )
    return candidates


def suggest_tracks_for_proposal_llm(
    placeholders: Sequence[UniversalTrack],
    api_key: str,
    model: str = DEFAULT_MODEL,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
    allowed_domains: Sequence[str] = DEFAULT_ALLOWED_DOMAINS,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Pide a un modelo de Claude con búsqueda web activada que rellene, en una
    sola llamada, un tema real por slot de la propuesta -coherente con el
    BPM/clave/energía/tramo de cada uno, no solo con el género-. Nunca
    cambia el BPM/clave/energía del slot: solo añade el título, artista y
    enlace reales, o deja el slot como estaba si el agente no encuentra nada
    razonable para él, o si la llamada falla.
    """
    report = SuggestionReport(attempted=len(placeholders), source="Agente IA (búsqueda web)")
    if not placeholders:
        return [], report
    sp = client if client is not None else _make_client(api_key)

    if progress:
        progress(0, len(placeholders), "Preguntando al agente (puede tardar: está buscando en la web)…")

    slots_text = "\n".join(_slot_line(track, i) for i, track in enumerate(placeholders))
    try:
        response = sp.messages.create(
            model=model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "type": WEB_SEARCH_TOOL,
                    "name": "web_search",
                    "max_uses": MAX_SEARCHES,
                    "allowed_domains": list(allowed_domains),
                }
            ],
            messages=[{"role": "user", "content": f"Slots del set ({len(placeholders)}):\n{slots_text}"}],
        )
        text = "\n".join(_block_text(block) for block in response.content if _block_type(block) == "text")
        candidates = _parse_candidates(_extract_json_array(text))
    except Exception as exc:
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    if progress:
        progress(len(placeholders), len(placeholders), "Agente terminado.")

    suggested: list[UniversalTrack] = []
    for index, track in enumerate(placeholders):
        pick = candidates[index] if index < len(candidates) else None
        if pick is None:
            suggested.append(track)
            continue
        report.suggested += 1
        payload: dict[str, Any] = {
            **track.raw_source.payload,
            "suggested_artist": pick["artist"],
            "suggested_title": pick["title"],
            "suggested_source": report.source,
        }
        if pick["url"]:
            payload["suggested_url"] = pick["url"]
        suggested.append(
            track.model_copy(update={"raw_source": track.raw_source.model_copy(update={"payload": payload})})
        )
    return suggested, report
''',
    'src/enrichment/spotify.py': r'''"""
Enriquecimiento de energía y tonalidad, y sugerencia de temas reales, con
Spotify (opcional).

AVISO sobre ``audio-features`` (modo colección, ``enrich_with_spotify``):
Spotify retiró este endpoint el 27-11-2024. Solo responden las apps que tenían
(o habían pedido) una ampliación de cuota antes de esa fecha; el resto recibe
403 y no hay sustituto oficial. Por eso el fallo NUNCA es silencioso: el
informe cuenta cuántos temas se quedan sin datos reales y guarda el primer
error.

La sugerencia de temas reales para el modo propuesta (``suggest_tracks_for_
proposal``) NO usa ``audio-features`` ni ``recommendations`` -ambos con la
misma restricción-. Tampoco busca el género como texto libre contra el
título/artista de la canción (``/v1/search?type=track&q=<texto>``): un track
de Spotify no lleva género como campo, así que ese texto libre solo
encuentra temas cuyo título o artista *contiene literalmente* la palabra del
género, que en la práctica es casi ninguno.

En su lugar usa el filtro de campo ``genre:"..."`` de la búsqueda de Spotify
-que, según la documentación oficial
(https://developer.spotify.com/documentation/web-api/reference/search),
funciona tanto en ``type=artist`` como en ``type=track``, verificado el
25-09-2026-:

1. Primero busca temas directamente con ``/v1/search?type=track&
   q=genre:"..."``: un único filtro, real y del género correcto.
2. Si eso no reúne bastantes temas distintos (género poco tageado, término
   no reconocido…), recurre a buscar **artistas** con ese mismo filtro
   (``type=artist``) y coge los temas más escuchados de cada uno
   (``/v1/artists/{id}/top-tracks``), como red de seguridad.

Ninguno de estos tres endpoints está restringido por el cambio de cuota del
27-11-2024, así que todo esto funciona con credenciales de Spotify normales,
sin necesitar una app antigua con cuota ampliada. El precio es que ninguno
filtra por tempo o tonalidad: la canción sugerida es real y del género
correcto, pero no está verificada nota a nota contra el BPM del slot; el
BPM, la clave y la energía del slot -los que respetan la curva y la ruta
armónica- nunca cambian.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Sequence

from src.core.keys import pitch_class_to_camelot
from src.core.models import UniversalTrack
from src.enrichment.common import ProgressCallback, SuggestionReport, assign_candidates, search_query_terms

FEATURES_BATCH: Final[int] = 100
SEARCH_PAGE: Final[int] = 50
SEARCH_MAX_PAGES_PER_TERM: Final[int] = 4

# Subconjunto de géneros conocidos por Spotify más cercano a cada género
# interno, usado como término de búsqueda de reserva cuando el género tal
# cual lo escribió el usuario no encuentra temas etiquetados con él.
# Spotify etiqueta con microgéneros bastante literales (p. ej. "tech house"
# existe tal cual), así que el texto del usuario suele bastar.
GENRE_SEED_OVERRIDES: Final[dict[str, str]] = {
    "downtempo": "chill",
    "disco": "disco",
    "nu disco": "disco",
    "deep house": "deep-house",
    "afro house": "house",
    "house": "house",
    "organic house": "house",
    "melodic house & techno": "techno",
    "melodic techno": "techno",
    "progressive house": "progressive-house",
    "tech house": "house",
    "minimal": "minimal-techno",
    "breaks": "breakbeat",
    "techno": "techno",
    "peak time techno": "techno",
    "trance": "trance",
    "psytrance": "trance",
    "dubstep": "dubstep",
    "hard techno": "techno",
    "hardstyle": "hardstyle",
    "drum and bass": "drum-and-bass",
    "drum & bass": "drum-and-bass",
    "dnb": "drum-and-bass",
}
DEFAULT_SEED_GENRE: Final[str] = "electronic"


def seed_genre(genres: Sequence[str]) -> str:
    """El primer género reconocido de la lista, o un valor genérico por defecto."""
    for genre in genres:
        mapped = GENRE_SEED_OVERRIDES.get(genre.strip().lower())
        if mapped:
            return mapped
    return DEFAULT_SEED_GENRE


@dataclass(slots=True)
class EnrichmentReport:
    attempted: int = 0
    enriched: int = 0
    not_found: int = 0
    failed: int = 0
    first_error: str = ""

    @property
    def fell_back(self) -> int:
        """Tracks que siguen con la energía/tonalidad de origen."""
        return self.attempted - self.enriched

    def summary(self) -> str:
        text = (
            f"Spotify: {self.enriched}/{self.attempted} temas enriquecidos, "
            f"{self.not_found} no encontrados, {self.failed} con error. "
            f"{self.fell_back} usan la estimación por BPM."
        )
        if self.first_error:
            text += f" Primer error: {self.first_error}"
        return text


def _make_client(client_id: str, client_secret: str) -> Any:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError as exc:
        raise RuntimeError(
            "spotipy no está instalado. Instálalo con: pip install -e '.[spotify]'"
        ) from exc
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret),
        requests_timeout=10,
        retries=1,
    )


def enrich_with_spotify(
    tracks: Sequence[UniversalTrack],
    client_id: str,
    client_secret: str,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
) -> tuple[list[UniversalTrack], EnrichmentReport]:
    """
    Busca cada track en Spotify y sustituye energía (0–1 → 0–10) y tonalidad.
    Devuelve SIEMPRE la lista completa: los que fallan quedan como estaban.
    """
    report = EnrichmentReport(attempted=len(tracks))
    sp = client if client is not None else _make_client(client_id, client_secret)

    spotify_ids: dict[str, str] = {}
    for index, track in enumerate(tracks, start=1):
        if progress:
            progress(index, len(tracks), f"Buscando {track.artist} – {track.title}")
        try:
            result = sp.search(q=f"track:{track.title} artist:{track.artist}", type="track", limit=1)
        except Exception as exc:
            report.failed += 1
            report.first_error = report.first_error or str(exc)
            continue
        items = (result or {}).get("tracks", {}).get("items", [])
        if items:
            spotify_ids[track.id] = items[0]["id"]
        else:
            report.not_found += 1

    features_by_track: dict[str, dict[str, Any]] = {}
    pending = list(spotify_ids.items())
    for start in range(0, len(pending), FEATURES_BATCH):
        chunk = pending[start : start + FEATURES_BATCH]
        try:
            features = sp.audio_features([sid for _, sid in chunk]) or []
        except Exception as exc:
            # Típicamente 403 para apps creadas después del 27-11-2024: no insistir.
            report.failed += len(pending) - start
            report.first_error = report.first_error or str(exc)
            break
        for (track_id, _), feature in zip(chunk, features):
            if feature:
                features_by_track[track_id] = feature
            else:
                report.not_found += 1

    enriched: list[UniversalTrack] = []
    for track in tracks:
        feature = features_by_track.get(track.id)
        if feature is None:
            enriched.append(track)
            continue
        update: dict[str, Any] = {}
        energy = feature.get("energy")
        if isinstance(energy, (int, float)):
            update["energy"] = round(min(max(float(energy) * 10.0, 0.0), 10.0), 2)
        key, mode = feature.get("key"), feature.get("mode")
        if isinstance(key, int) and 0 <= key <= 11 and mode in (0, 1):
            update["key"] = pitch_class_to_camelot(key, minor=mode == 0)
        if update:
            report.enriched += 1
            enriched.append(track.model_copy(update=update))
        else:
            enriched.append(track)
    return enriched, report


def _track_from_item(item: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
    track_id = item.get("id")
    title = item.get("name")
    artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
    if not (track_id and title and artists):
        return None
    return track_id, {
        "artist": artists,
        "title": title,
        "url": item.get("external_urls", {}).get("spotify", ""),
    }


def _tracks_by_genre_filter(
    sp: Any, terms: Sequence[str], needed: int, seen: dict[str, dict[str, str]], progress: ProgressCallback | None
) -> None:
    """
    Vía principal: ``/v1/search?type=track&q=genre:"..."``. El filtro
    ``genre`` está documentado para ``type=track``, no solo para artistas
    (verificado contra la referencia oficial de Spotify).
    """
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(SEARCH_MAX_PAGES_PER_TERM):
            if len(seen) >= needed:
                break
            if progress:
                progress(min(len(seen) + 1, needed), needed, f"Buscando temas de {term}…")
            result = sp.search(q=f'genre:"{term}"', type="track", limit=SEARCH_PAGE, offset=page * SEARCH_PAGE)
            items = (result or {}).get("tracks", {}).get("items", []) or []
            if not items:
                break
            for item in items:
                if len(seen) >= needed:
                    break
                parsed = _track_from_item(item)
                if parsed and parsed[0] not in seen:
                    seen[parsed[0]] = parsed[1]


def _tracks_by_artist_top_tracks(
    sp: Any, terms: Sequence[str], needed: int, seen: dict[str, dict[str, str]], progress: ProgressCallback | None
) -> None:
    """
    Red de seguridad si la vía principal no reúne bastantes temas: busca
    artistas con el mismo filtro ``genre:"..."`` (``type=artist``, también
    documentado) y coge los temas más escuchados de cada uno
    (``/v1/artists/{id}/top-tracks``). Un artista sin top-tracks disponible
    simplemente se salta, sin abortar la búsqueda.
    """
    seen_artists: set[str] = set()
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(SEARCH_MAX_PAGES_PER_TERM):
            if len(seen) >= needed:
                break
            result = sp.search(q=f'genre:"{term}"', type="artist", limit=SEARCH_PAGE, offset=page * SEARCH_PAGE)
            artists = (result or {}).get("artists", {}).get("items", []) or []
            if not artists:
                break
            for artist in artists:
                if len(seen) >= needed:
                    break
                artist_id = artist.get("id")
                if not artist_id or artist_id in seen_artists:
                    continue
                seen_artists.add(artist_id)
                if progress:
                    progress(
                        min(len(seen) + 1, needed), needed, f"Buscando temas de {artist.get('name') or term}…"
                    )
                try:
                    top = sp.artist_top_tracks(artist_id) or {}
                except Exception:
                    continue
                for item in top.get("tracks", []) or []:
                    if len(seen) >= needed:
                        break
                    parsed = _track_from_item(item)
                    if parsed and parsed[0] not in seen:
                        seen[parsed[0]] = parsed[1]


def _search_candidates(
    sp: Any, terms: Sequence[str], needed: int, progress: ProgressCallback | None
) -> list[dict[str, str]]:
    """Hasta ``needed`` temas reales y distintos del género, con la vía principal y, si hace falta, la de reserva."""
    seen: dict[str, dict[str, str]] = {}
    _tracks_by_genre_filter(sp, terms, needed, seen, progress)
    if len(seen) < needed:
        _tracks_by_artist_top_tracks(sp, terms, needed, seen, progress)
    return list(seen.values())[:needed]


def suggest_tracks_for_proposal(
    placeholders: Sequence[UniversalTrack],
    genres: Sequence[str],
    client_id: str,
    client_secret: str,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Busca artistas reales del género de la propuesta y coge sus temas más
    escuchados, para sustituir el nombre y artista de cada marcador por uno
    real y distinto. Nunca cambia el BPM/clave/energía del slot (son los que
    respetan la curva y la ruta armónica): solo añade el título, artista y
    enlace reales al ``payload`` del marcador. Si no hay bastantes temas
    distintos para cubrir todos los slots, o la búsqueda falla, los slots
    restantes conservan su marcador sintético tal cual.
    """
    report = SuggestionReport(attempted=len(placeholders), source="Spotify")
    if not placeholders:
        return [], report
    sp = client if client is not None else _make_client(client_id, client_secret)
    terms = search_query_terms(genres, seed_genre(genres).replace("-", " "))

    try:
        candidates = _search_candidates(sp, terms, len(placeholders), progress)
    except Exception as exc:
        # P. ej. credenciales inválidas o un fallo de red: no insistir, todos
        # los slots se quedan con el marcador sintético.
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    return assign_candidates(placeholders, candidates, report), report
''',
    'src/exporters/__init__.py': r'''"""Exportación del set a formatos que cargan los programas de DJ."""

from src.exporters.exports import SetRow, set_rows, to_csv, to_m3u8, to_rekordbox_xml

__all__ = ["SetRow", "set_rows", "to_csv", "to_m3u8", "to_rekordbox_xml"]
''',
    'src/exporters/exports.py': r'''"""
Exportadores del set final:

- ``to_csv``: tabla completa (tramo, transición, pitch…), para revisar o compartir.
- ``to_m3u8``: playlist universal (Rekordbox, Engine DJ, Traktor, Serato, VLC…).
- ``to_rekordbox_xml``: XML importable en Rekordbox (Preferencias → Avanzado →
  Base de datos → rekordbox xml) con el set como playlist.

M3U8 y XML necesitan la ruta del fichero de audio (``raw_source.location``),
que solo existe si la colección viene de Rekordbox o de un CSV con columna de ruta.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Sequence
from urllib.parse import quote

from src.core.models import TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot

PRODUCT_NAME = "rekordbox-setbuilder"
PRODUCT_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class SetRow:
    position: int
    phase: str
    track: UniversalTrack
    target_energy: float | None
    transition: TransitionEvaluation | None


def set_rows(
    selected: Sequence[UniversalTrack],
    slots: Sequence[TimelineSlot],
    transitions: Sequence[TransitionEvaluation],
) -> list[SetRow]:
    """Une track, slot y transición de entrada (la del tema anterior a este)."""
    incoming = {t.to_track_id: t for t in transitions}
    rows: list[SetRow] = []
    for index, track in enumerate(selected):
        slot = slots[index] if index < len(slots) else None
        rows.append(
            SetRow(
                position=index + 1,
                phase=slot["phase"] if slot else "",
                track=track,
                target_energy=slot["target_energy"] if slot else None,
                transition=incoming.get(track.id) if index > 0 else None,
            )
        )
    return rows


def to_csv(rows: Sequence[SetRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["position", "phase", "artist", "title", "bpm", "key", "energy", "target_energy",
         "duration_sec", "genre", "transition", "pitch_pct", "valid", "location",
         "suggested_artist", "suggested_title", "suggested_url", "suggested_source"]
    )
    for row in rows:
        t, tr = row.track, row.transition
        payload = t.raw_source.payload
        writer.writerow(
            [row.position, row.phase, t.artist, t.title, t.bpm, t.key, t.energy,
             row.target_energy if row.target_energy is not None else "",
             t.duration_sec, t.genre or "",
             tr.transition_type.value if tr else "",
             f"{tr.bpm_delta_pct:.2f}" if tr else "",
             ("yes" if tr.is_valid else "no") if tr else "",
             t.raw_source.location or "",
             payload.get("suggested_artist", ""),
             payload.get("suggested_title", ""),
             payload.get("suggested_url", ""),
             payload.get("suggested_source", "")]
        )
    return buffer.getvalue()


def to_m3u8(tracks: Sequence[UniversalTrack], title: str = "Set") -> tuple[str, int]:
    """Devuelve (contenido, nº de tracks omitidos por no tener ruta)."""
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    missing = 0
    for t in tracks:
        if not t.raw_source.location:
            missing += 1
            continue
        lines.append(f"#EXTINF:{t.duration_sec},{t.artist} - {t.title}")
        lines.append(t.raw_source.location)
    return "\n".join(lines) + "\n", missing


def path_to_location(path: str) -> str:
    """Ruta local → URI ``file://localhost/...`` que espera Rekordbox."""
    if len(path) > 1 and path[1] == ":":
        posix = PureWindowsPath(path).as_posix()
        return "file://localhost/" + quote(posix, safe="/:")
    return "file://localhost" + quote(str(PurePosixPath(path)), safe="/")


def to_rekordbox_xml(tracks: Sequence[UniversalTrack], playlist_name: str = "Set") -> tuple[str, int]:
    """Devuelve (XML, nº de tracks omitidos por no tener ruta)."""
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name=PRODUCT_NAME, Version=PRODUCT_VERSION, Company="")
    exportable = [t for t in tracks if t.raw_source.location]
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(exportable)))
    for number, t in enumerate(exportable, start=1):
        ET.SubElement(
            collection,
            "TRACK",
            TrackID=str(number),
            Name=t.title,
            Artist=t.artist,
            Genre=t.genre or "",
            TotalTime=str(t.duration_sec),
            AverageBpm=f"{t.bpm:.2f}",
            Tonality=t.key,
            Location=path_to_location(t.raw_source.location or ""),
        )
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    playlist = ET.SubElement(
        root_node, "NODE", Name=playlist_name, Type="1", KeyType="0", Entries=str(len(exportable))
    )
    for number in range(1, len(exportable) + 1):
        ET.SubElement(playlist, "TRACK", Key=str(number))
    ET.indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return xml + "\n", len(tracks) - len(exportable)
''',
    'src/graph/__init__.py': r'''"""graph package."""
''',
    'src/graph/builder.py': r'''"""Compilación del ``StateGraph`` del set builder."""

from __future__ import annotations

from typing import Final, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.graph.nodes import (
    SetCurator,
    build_timeline_slots_node,
    graph_search_node,
    make_llm_curator_node,
    parse_collection_node,
    proposal_node,
    route_after_timeline,
)
from src.graph.state import SetGraphState

PARSE: Final = "parse_collection_node"
TIMELINE: Final = "build_timeline_slots_node"
SEARCH: Final[Literal["graph_search_node"]] = "graph_search_node"
PROPOSAL: Final[Literal["proposal_node"]] = "proposal_node"
CURATOR: Final = "llm_curator_node"

SetGraph = CompiledStateGraph[SetGraphState, None, SetGraphState, SetGraphState]


def _after_timeline(state: SetGraphState) -> Literal["graph_search_node", "proposal_node"]:
    return SEARCH if route_after_timeline(state) else PROPOSAL


def build_set_graph(curator: SetCurator | None = None) -> SetGraph:
    """
    START → parse → timeline ─┬─(hay colección)→ graph_search ─┬→ curator → END
                              └─(sin colección)→ proposal ──────┘
    """
    graph: StateGraph[SetGraphState, None, SetGraphState, SetGraphState] = StateGraph(
        SetGraphState
    )

    graph.add_node(PARSE, parse_collection_node)
    graph.add_node(TIMELINE, build_timeline_slots_node)
    graph.add_node(SEARCH, graph_search_node)
    graph.add_node(PROPOSAL, proposal_node)
    graph.add_node(CURATOR, make_llm_curator_node(curator))

    graph.add_edge(START, PARSE)
    graph.add_edge(PARSE, TIMELINE)
    graph.add_conditional_edges(TIMELINE, _after_timeline, {SEARCH: SEARCH, PROPOSAL: PROPOSAL})
    graph.add_edge(SEARCH, CURATOR)
    graph.add_edge(PROPOSAL, CURATOR)
    graph.add_edge(CURATOR, END)

    return graph.compile()
''',
    'src/graph/nodes.py': r'''"""
Nodos del grafo. Todos son funciones puras ``state -> actualización parcial``,
lo que permite testearlos sin compilar el grafo.

- ``parse_collection_node``: normaliza y filtra la colección (género, BPM, duplicados).
- ``build_timeline_slots_node``: genera la curva objetivo (slots con BPM/energía).
- ``proposal_node``: sin colección (o si nada pasa los filtros), genera el set
  ideal slot a slot con BPM, energía y ruta de claves Camelot.
- ``graph_search_node``: selección determinista slot a slot. Implementación base
  greedy sobre el mismo coste de arista que usará el futuro Dijkstra/A*.
- ``llm_curator_node``: curaduría narrativa. Recibe un ``SetCurator`` inyectable;
  por defecto usa ``rule_based_curator`` (sin dependencia de ningún LLM).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Final, Protocol, Sequence

from pydantic import BaseModel, Field

from src.core.models import SetConstraint, TransitionEvaluation, UniversalTrack
from src.core.proposal import build_proposal_tracks
from src.core.timeline import TimelineSlot, build_timeline
from src.core.transitions import evaluate_transition
from src.graph.state import SetGraphState, SetMode

StateUpdate = dict[str, Any]


class GraphNode(Protocol):
    """Firma de un nodo de LangGraph sobre ``SetGraphState``."""

    def __call__(self, state: SetGraphState) -> StateUpdate: ...

ENERGY_WINDOW_WIDENING: Final[float] = 2.0
ENERGY_FIT_WEIGHT: Final[float] = 0.8
BPM_FIT_WEIGHT_PER_PCT: Final[float] = 0.3
DURATION_TOLERANCE: Final[float] = 0.10


# --------------------------------------------------------------------------- #
# 1. Parseo / normalización
# --------------------------------------------------------------------------- #
def parse_collection_node(state: SetGraphState) -> StateUpdate:
    constraints = state["constraints"]
    violations: list[str] = []

    unique: dict[str, UniversalTrack] = {}
    for track in state["available_tracks"]:
        unique.setdefault(track.dedupe_key(), track)
    duplicates = len(state["available_tracks"]) - len(unique)
    if duplicates:
        violations.append(
            f"parse: {duplicates} tracks duplicados descartados (mismo archivo o misma "
            "combinación título/artista/BPM con un id distinto)."
        )

    filtered = [
        t
        for t in unique.values()
        if t.matches_genres(constraints.target_genres)
        and (constraints.bpm_min is None or t.bpm >= constraints.bpm_min)
        and (constraints.bpm_max is None or t.bpm <= constraints.bpm_max)
    ]
    filtered.sort(key=lambda t: (t.energy, t.bpm, t.id))

    mode: SetMode = "collection" if filtered else "proposal"
    if not filtered and state["available_tracks"]:
        violations.append(
            "parse: ningún track cumple género/BPM "
            f"(géneros={constraints.target_genres or 'cualquiera'}, "
            f"bpm={constraints.bpm_min}–{constraints.bpm_max}); se genera una propuesta."
        )

    return {
        "available_tracks": filtered,
        "mode": mode,
        "violations": violations,
        "current_step": "parse_collection",
    }


def route_after_timeline(state: SetGraphState) -> bool:
    """True si hay colección con la que buscar; False → modo propuesta."""
    return bool(state["available_tracks"])


# --------------------------------------------------------------------------- #
# 2. Curva objetivo
# --------------------------------------------------------------------------- #
def build_timeline_slots_node(state: SetGraphState) -> StateUpdate:
    tracks = state["available_tracks"]
    slots = build_timeline(state["constraints"], tracks)
    violations: list[str] = []
    if tracks and len(tracks) < len(slots):
        violations.append(
            f"timeline: colección insuficiente, {len(tracks)} temas para {len(slots)} slots."
        )
    return {
        "target_slots": slots,
        "violations": violations,
        "current_step": "build_timeline_slots",
    }


# --------------------------------------------------------------------------- #
# 3. Búsqueda
# --------------------------------------------------------------------------- #
def _slot_fit_cost(track: UniversalTrack, slot: TimelineSlot) -> float:
    energy_gap = abs(track.energy - slot["target_energy"])
    bpm_gap_pct = abs(track.bpm - slot["target_bpm"]) / slot["target_bpm"] * 100.0
    return energy_gap * ENERGY_FIT_WEIGHT + bpm_gap_pct * BPM_FIT_WEIGHT_PER_PCT


def _candidates_for_slot(
    pool: Sequence[UniversalTrack], slot: TimelineSlot
) -> tuple[list[UniversalTrack], float | None]:
    """
    Devuelve candidatos y la tolerancia usada: 0 → ventana nominal,
    ±2 → ventana ampliada (regla del proyecto), None → sin ventana (último recurso).
    """
    for tolerance in (0.0, ENERGY_WINDOW_WIDENING):
        low = slot["energy_min"] - tolerance
        high = slot["energy_max"] + tolerance
        inside = [t for t in pool if low <= t.energy <= high]
        if inside:
            return inside, tolerance
    return list(pool), None


def graph_search_node(state: SetGraphState) -> StateUpdate:
    constraints = state["constraints"]
    slots = state.get("target_slots", [])
    remaining: dict[str, UniversalTrack] = {t.id: t for t in state["available_tracks"]}
    selected: list[UniversalTrack] = []
    transitions: list[TransitionEvaluation] = []
    violations: list[str] = []

    for slot in slots:
        if not remaining:
            violations.append(
                f"search: sin temas para slot {slot['index']} ({slot['phase']}); set incompleto."
            )
            break

        candidates, tolerance = _candidates_for_slot(list(remaining.values()), slot)
        if tolerance is None:
            violations.append(
                f"search: slot {slot['index']} ({slot['phase']}) sin temas en energía "
                f"{slot['energy_min']}–{slot['energy_max']} ni ampliando ±{ENERGY_WINDOW_WIDENING}."
            )
        elif tolerance > 0:
            violations.append(
                f"search: slot {slot['index']} ({slot['phase']}) ventana de energía "
                f"ampliada ±{tolerance}."
            )

        previous = selected[-1] if selected else None
        best_track: UniversalTrack | None = None
        best_eval: TransitionEvaluation | None = None
        best_score = float("inf")
        for cand in sorted(candidates, key=lambda t: t.id):
            evaluation = (
                evaluate_transition(previous, cand, constraints.harmonic_strictness)
                if previous
                else None
            )
            score = _slot_fit_cost(cand, slot) + (evaluation.cost if evaluation else 0.0)
            if score < best_score:
                best_track, best_eval, best_score = cand, evaluation, score

        assert best_track is not None  # candidates nunca está vacío aquí
        selected.append(best_track)
        del remaining[best_track.id]
        if best_eval is not None:
            transitions.append(best_eval)

    return {
        "selected_set": selected,
        "transitions": transitions,
        "violations": violations,
        "current_step": "graph_search",
    }


# --------------------------------------------------------------------------- #
# 3b. Propuesta (sin colección)
# --------------------------------------------------------------------------- #
def proposal_node(state: SetGraphState) -> StateUpdate:
    """Genera el set ideal slot a slot a partir solo de los parámetros."""
    constraints = state["constraints"]
    slots = state.get("target_slots", [])
    placeholders = build_proposal_tracks(slots, constraints)
    transitions = [
        evaluate_transition(a, b, constraints.harmonic_strictness)
        for a, b in zip(placeholders, placeholders[1:])
    ]
    return {
        "selected_set": placeholders,
        "transitions": transitions,
        "violations": [],
        "current_step": "proposal",
    }


# --------------------------------------------------------------------------- #
# 4. Curaduría
# --------------------------------------------------------------------------- #
class CuratorReport(BaseModel):
    """Salida de cualquier curador (reglas o LLM)."""

    notes: str
    violations: list[str] = Field(default_factory=list)
    reordered_ids: list[str] | None = Field(
        default=None,
        description="Permutación opcional del set propuesta por el curador.",
    )


SetCurator = Callable[[SetGraphState], CuratorReport]


def _phase_summary(tracks: Sequence[UniversalTrack], slots: Sequence[TimelineSlot]) -> str:
    by_phase: dict[str, list[UniversalTrack]] = defaultdict(list)
    order: list[str] = []
    for track, slot in zip(tracks, slots):
        if slot["phase"] not in by_phase:
            order.append(slot["phase"])
        by_phase[slot["phase"]].append(track)
    lines: list[str] = []
    for phase in order:
        items = by_phase[phase]
        lines.append(
            f"{phase}: {len(items)} temas, "
            f"{items[0].bpm:g}→{items[-1].bpm:g} BPM, "
            f"energía {items[0].energy:g}→{items[-1].energy:g}, "
            f"claves {' → '.join(t.key for t in items)}"
        )
    return "\n".join(lines)


def rule_based_curator(state: SetGraphState) -> CuratorReport:
    """Curador determinista: audita el set y redacta un resumen por tramo."""
    constraints: SetConstraint = state["constraints"]
    selected = state.get("selected_set", [])
    slots = state.get("target_slots", [])
    transitions = state.get("transitions", [])
    violations: list[str] = []

    for ev in transitions:
        if not ev.is_valid:
            violations.append(
                f"curator: transición {ev.from_track_id}→{ev.to_track_id} fuera de reglas "
                f"({ev.transition_type.value}, pitch {ev.bpm_delta_pct:.1f}%)."
            )

    total_sec = sum(t.duration_sec for t in selected)
    target_sec = constraints.total_duration_sec
    if selected and abs(total_sec - target_sec) > target_sec * DURATION_TOLERANCE:
        violations.append(
            f"curator: duración {total_sec / 60:.1f} min vs objetivo "
            f"{constraints.total_duration_min} min (±{DURATION_TOLERANCE:.0%})."
        )

    valid = sum(1 for ev in transitions if ev.is_valid)
    prefix = "Propuesta sin colección · " if state.get("mode") == "proposal" else ""
    header = (
        f"{prefix}Set de {len(selected)} temas · {total_sec / 60:.1f} min · "
        f"perfil {constraints.energy_curve_profile} · "
        f"{valid}/{len(transitions)} transiciones dentro de reglas ({constraints.harmonic_strictness})."
    )
    notes = header if not selected else f"{header}\n{_phase_summary(selected, slots)}"
    return CuratorReport(notes=notes, violations=violations)


def make_llm_curator_node(curator: SetCurator | None = None) -> GraphNode:
    """
    Fábrica del nodo de curaduría. ``curator`` puede envolver un LLM
    (p. ej. un chat model con salida estructurada ``CuratorReport``).
    """
    active: SetCurator = curator or rule_based_curator

    def llm_curator_node(state: SetGraphState) -> StateUpdate:
        report = active(state)
        selected = state.get("selected_set", [])
        violations = list(report.violations)
        update: StateUpdate = {"curator_notes": report.notes, "current_step": "llm_curator"}

        if report.reordered_ids is not None:
            by_id = {t.id: t for t in selected}
            if sorted(report.reordered_ids) == sorted(by_id):
                update["selected_set"] = [by_id[i] for i in report.reordered_ids]
            else:
                violations.append(
                    "curator: reordenación rechazada, no es una permutación del set seleccionado."
                )

        update["violations"] = violations
        return update

    llm_curator_node.__name__ = "llm_curator_node"
    return llm_curator_node


llm_curator_node: GraphNode = make_llm_curator_node()
''',
    'src/graph/state.py': r'''"""Estado global que circula entre los nodos del grafo de LangGraph."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, Required, Sequence, TypedDict

from src.core.models import SetConstraint, TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot

SetMode = Literal["collection", "proposal"]


class SetGraphState(TypedDict, total=False):
    """
    ``constraints`` y ``available_tracks`` son la entrada obligatoria; el resto
    lo van rellenando los nodos.

    ``violations`` usa un reducer de concatenación: cada nodo devuelve solo sus
    avisos nuevos y LangGraph los acumula a lo largo de la ejecución.
    """

    constraints: Required[SetConstraint]
    available_tracks: Required[list[UniversalTrack]]
    target_slots: NotRequired[list[TimelineSlot]]
    selected_set: NotRequired[list[UniversalTrack]]
    violations: NotRequired[Annotated[list[str], operator.add]]
    current_step: NotRequired[str]
    mode: NotRequired[SetMode]
    transitions: NotRequired[list[TransitionEvaluation]]
    curator_notes: NotRequired[str]


def initial_state(
    constraints: SetConstraint, tracks: Sequence[UniversalTrack] = ()
) -> SetGraphState:
    """Estado de entrada listo para ``graph.invoke``. Sin tracks → modo propuesta."""
    return SetGraphState(
        constraints=constraints,
        available_tracks=list(tracks),
        target_slots=[],
        selected_set=[],
        violations=[],
        current_step="init",
        mode="proposal" if not tracks else "collection",
        transitions=[],
        curator_notes="",
    )
''',
    'src/parsers/__init__.py': r'''"""
Parsers de colecciones → UniversalTrack.

Formatos soportados (detección automática por nombre y contenido):
- Rekordbox: XML de colección (cualquier versión) y BD local de Rekordbox 6 (pyrekordbox)
- Engine DJ: m.db (SQLite)
- Traktor: collection.nml
- VirtualDJ: database.xml
- CSV genérico (Serato y cualquier otra app vía exportación a CSV)
"""

from src.parsers.base import CollectionParser, ParseResult
from src.parsers.csv_parser import CsvCollectionParser
from src.parsers.engine_dj import EngineDjParser
from src.parsers.rekordbox_db import Rekordbox6DatabaseReader
from src.parsers.rekordbox_xml import RekordboxXmlParser
from src.parsers.traktor_nml import TraktorNmlParser
from src.parsers.virtualdj_xml import VirtualDjXmlParser

# El orden importa: los detectores por contenido van antes que el CSV (que acepta por extensión).
FILE_PARSERS: tuple[CollectionParser, ...] = (
    EngineDjParser(),
    RekordboxXmlParser(),
    TraktorNmlParser(),
    VirtualDjXmlParser(),
    CsvCollectionParser(),
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = ("xml", "nml", "db", "csv", "tsv", "txt")


def parse_file(filename: str, data: bytes) -> ParseResult:
    """Elige el parser adecuado según nombre y contenido."""
    head = data[:4096]
    for parser in FILE_PARSERS:
        if parser.can_parse(filename, head):
            return parser.parse(data)
    raise ValueError(
        f"Formato no soportado: '{filename}'. Admitidos: XML de Rekordbox, m.db de Engine DJ, "
        "collection.nml de Traktor, database.xml de VirtualDJ o CSV."
    )


__all__ = [
    "CollectionParser",
    "CsvCollectionParser",
    "EngineDjParser",
    "FILE_PARSERS",
    "ParseResult",
    "Rekordbox6DatabaseReader",
    "RekordboxXmlParser",
    "SUPPORTED_EXTENSIONS",
    "TraktorNmlParser",
    "VirtualDjXmlParser",
    "parse_file",
]
''',
    'src/parsers/base.py': r'''"""Contrato común para todos los parsers de colecciones."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from src.core.models import TrackSource, UniversalTrack


class ParseResult(BaseModel):
    """Salida normalizada de cualquier parser."""

    model_config = ConfigDict(frozen=True)

    source: TrackSource
    tracks: list[UniversalTrack] = Field(default_factory=list)
    playlists: dict[str, list[str]] = Field(
        default_factory=dict, description="Nombre de playlist → ids de track, en orden."
    )
    skipped: int = 0
    energy_estimated: int = Field(
        default=0, description="Tracks cuya energía se ha estimado por BPM."
    )
    warnings: list[str] = Field(default_factory=list)

    @property
    def genres(self) -> list[str]:
        return sorted({t.genre for t in self.tracks if t.genre}, key=str.lower)


@runtime_checkable
class CollectionParser(Protocol):
    """
    Parser de ficheros exportados (XML, CSV…). Cada fabricante implementa este
    protocolo; el resto del sistema solo ve ``UniversalTrack``.
    """

    source: TrackSource

    def can_parse(self, filename: str, head: bytes) -> bool:
        """True si el fichero pertenece a este formato (por nombre y primeros bytes)."""
        ...

    def parse(self, data: bytes) -> ParseResult:
        """Lee el contenido completo del fichero y devuelve tracks normalizados."""
        ...
''',
    'src/parsers/common.py': r'''"""Utilidades compartidas por los parsers: normalización de campos sueltos a UniversalTrack."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.core.energy import estimate_energy_from_bpm
from src.core.keys import to_camelot
from src.core.models import RawSource, TrackSource, UniversalTrack

_DURATION_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_duration_sec(value: Any) -> int | None:
    """Acepta segundos (``392``, ``392.4``) o reloj (``6:32``, ``1:02:03``)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if match := _DURATION_RE.match(text):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return round(hours * 3600 + minutes * 60 + seconds)
    number = parse_float(text)
    return round(number) if number is not None else None


def normalize_bpm(value: Any) -> float | None:
    """Rekordbox DB guarda BPM×100 (12400 = 124.00)."""
    bpm = parse_float(value)
    if bpm is None or bpm <= 0:
        return None
    return round(bpm / 100.0, 2) if bpm > 1000 else round(bpm, 2)


@dataclass(slots=True)
class TrackAccumulator:
    """Acumula tracks válidos y cuenta los descartados por motivo."""

    source: TrackSource
    tracks: list[UniversalTrack] = field(default_factory=list)
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    energy_estimated: int = 0

    def skip(self, reason: str) -> None:
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1

    @property
    def skipped(self) -> int:
        return sum(self.skipped_reasons.values())

    def warnings(self) -> list[str]:
        return [f"{count} tracks descartados: {reason}." for reason, count in self.skipped_reasons.items()]

    def add(
        self,
        *,
        track_id: Any,
        title: Any,
        artist: Any,
        bpm: Any,
        key: Any,
        duration: Any,
        genre: Any = None,
        energy: Any = None,
        tags: Any = None,
        location: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> UniversalTrack | None:
        bpm_value = normalize_bpm(bpm)
        if bpm_value is None:
            self.skip("sin BPM")
            return None
        camelot = to_camelot(str(key)) if key is not None else None
        if camelot is None:
            self.skip("sin tonalidad reconocible")
            return None
        duration_sec = parse_duration_sec(duration)
        if duration_sec is None or duration_sec <= 0:
            self.skip("sin duración")
            return None

        energy_value = parse_float(energy)
        if energy_value is None:
            energy_value = estimate_energy_from_bpm(bpm_value)
            self.energy_estimated += 1

        title_text = str(title).strip() if title else ""
        try:
            track = UniversalTrack(
                id=str(track_id),
                title=title_text or f"Track {track_id}",
                artist=(str(artist).strip() if artist else "") or "Unknown Artist",
                bpm=bpm_value,
                key=camelot,
                energy=energy_value,
                duration_sec=duration_sec,
                genre=genre,
                tags=tags or (),
                raw_source=RawSource(
                    system=self.source,
                    native_id=str(track_id),
                    location=location,
                    payload=payload or {},
                ),
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            self.skip(f"dato inválido en '{first['loc'][0] if first['loc'] else '?'}'")
            return None
        self.tracks.append(track)
        return track
''',
    'src/parsers/csv_parser.py': r'''"""
Parser CSV genérico (exportaciones propias, hojas de cálculo, otras apps).

Reconoce cabeceras en inglés y español, separador ``,`` o ``;`` y duraciones
en segundos o ``mm:ss``. Columnas mínimas: título, BPM, tonalidad y duración.
"""

from __future__ import annotations

import csv
import io
from typing import Final

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

COLUMN_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "id": ("id", "track_id", "trackid"),
    "title": ("title", "name", "track", "título", "titulo", "nombre"),
    "artist": ("artist", "artista"),
    "bpm": ("bpm", "tempo", "averagebpm"),
    "key": ("key", "camelot", "tonality", "tonalidad", "clave", "tono"),
    "energy": ("energy", "energía", "energia"),
    "duration": ("duration_sec", "duration", "length", "time", "totaltime", "duración", "duracion"),
    "genre": ("genre", "género", "genero"),
    "tags": ("tags", "etiquetas"),
    "location": ("location", "path", "file", "filepath", "ruta"),
}
REQUIRED: Final[tuple[str, ...]] = ("title", "bpm", "key", "duration")


def _resolve_columns(header: list[str]) -> dict[str, str]:
    lowered = {h.strip().lower(): h for h in header if h}
    mapping: dict[str, str] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field_name] = lowered[alias]
                break
    return mapping


class CsvCollectionParser:
    source: TrackSource = TrackSource.CSV

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith((".csv", ".tsv", ".txt"))

    def parse(self, data: bytes) -> ParseResult:
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        columns = _resolve_columns(list(reader.fieldnames or []))
        missing = [f for f in REQUIRED if f not in columns]
        if missing:
            raise ValueError(
                "Faltan columnas obligatorias en el CSV: "
                + ", ".join(missing)
                + f". Cabeceras encontradas: {reader.fieldnames}"
            )

        acc = TrackAccumulator(self.source)
        for index, row in enumerate(reader, start=1):
            def get(name: str) -> str | None:
                column = columns.get(name)
                return row.get(column) if column else None

            raw_tags = get("tags")
            acc.add(
                track_id=get("id") or f"row-{index}",
                title=get("title"),
                artist=get("artist"),
                bpm=get("bpm"),
                key=get("key"),
                duration=get("duration"),
                genre=get("genre"),
                energy=get("energy"),
                tags=[t for t in (raw_tags or "").replace(";", ",").split(",") if t.strip()],
                location=get("location") or None,
                payload={k: v for k, v in row.items() if k},
            )

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
''',
    'src/parsers/engine_dj.py': r'''"""
Parser de la base de datos de Engine DJ (``Engine Library/Database2/m.db``).

La BD es SQLite. El esquema cambia entre versiones, así que las columnas se
detectan con ``PRAGMA table_info`` en lugar de asumirlas.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

SQLITE_MAGIC = b"SQLite format 3\x00"


def engine_key(value: Any) -> str | None:
    """
    Engine DJ numera las tonalidades 0–23 recorriendo el círculo de quintas en
    parejas (mayor, relativa menor): 0 = C (8B), 1 = Am (8A), 2 = G (9B), …
    """
    if value is None:
        return None
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= index <= 23:
        return None
    number = (7 + index // 2) % 12 + 1
    return f"{number}{'B' if index % 2 == 0 else 'A'}"


def _first_present(columns: set[str], *names: str) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


class EngineDjParser:
    source: TrackSource = TrackSource.ENGINE_DJ

    def can_parse(self, filename: str, head: bytes) -> bool:
        return head.startswith(SQLITE_MAGIC)

    def parse(self, data: bytes) -> ParseResult:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "m.db"
            db_path.write_bytes(data)
            return self.parse_path(db_path)

    def parse_path(self, db_path: Path) -> ParseResult:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return self._read(connection)
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"No es una base de datos de Engine DJ válida: {exc}") from exc
        finally:
            connection.close()

    def _read(self, connection: sqlite3.Connection) -> ParseResult:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(Track)")}
        if not columns:
            raise ValueError("La base de datos no tiene tabla 'Track' (¿es el m.db de Engine DJ?).")

        bpm_col = _first_present(columns, "bpmAnalyzed", "bpm")
        wanted = {
            "id": "id",
            "title": _first_present(columns, "title"),
            "artist": _first_present(columns, "artist"),
            "bpm": bpm_col,
            "key": _first_present(columns, "key"),
            "length": _first_present(columns, "length"),
            "genre": _first_present(columns, "genre"),
            "path": _first_present(columns, "path"),
            "label": _first_present(columns, "label"),
        }
        selected = {alias: col for alias, col in wanted.items() if col}
        sql = "SELECT " + ", ".join(f'"{col}" AS {alias}' for alias, col in selected.items()) + " FROM Track"
        connection.row_factory = sqlite3.Row

        acc = TrackAccumulator(self.source)
        for row in connection.execute(sql):
            record = dict(row)
            acc.add(
                track_id=record.get("id", ""),
                title=record.get("title"),
                artist=record.get("artist"),
                bpm=record.get("bpm"),
                key=engine_key(record.get("key")),
                duration=record.get("length"),
                genre=record.get("genre"),
                tags=[record["label"]] if record.get("label") else [],
                location=record.get("path"),
                payload={k: v for k, v in record.items() if isinstance(v, (str, int, float))},
            )

        valid_ids = {t.id for t in acc.tracks}
        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=self._playlists(connection, valid_ids),
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    @staticmethod
    def _playlists(connection: sqlite3.Connection, valid_ids: set[str]) -> dict[str, list[str]]:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"Playlist", "PlaylistEntity"} <= tables:
            return {}
        entity_cols = {row[1] for row in connection.execute("PRAGMA table_info(PlaylistEntity)")}
        playlists: dict[str, list[str]] = {}
        for pl in connection.execute("SELECT id, title FROM Playlist"):
            rows = list(connection.execute("SELECT * FROM PlaylistEntity WHERE listId = ?", (pl["id"],)))
            ordered = rows
            if "nextEntityId" in entity_cols and rows:
                # Engine guarda el orden como lista enlazada: se reconstruye desde el primer elemento.
                by_id = {r["id"]: r for r in rows}
                pointed = {r["nextEntityId"] for r in rows}
                head = next((r for r in rows if r["id"] not in pointed), rows[0])
                ordered, seen = [], set()
                node = head
                while node is not None and node["id"] not in seen:
                    ordered.append(node)
                    seen.add(node["id"])
                    node = by_id.get(node["nextEntityId"])
            ids = [str(r["trackId"]) for r in ordered]
            playlists[str(pl["title"])] = [i for i in ids if i in valid_ids]
        return playlists
''',
    'src/parsers/rekordbox_db.py': r'''"""
Lector de la base de datos local de Rekordbox 6 mediante ``pyrekordbox``.

Rekordbox debe estar COMPLETAMENTE CERRADO: bloquea su base de datos mientras
está abierto. Para Rekordbox 7 (o si no quieres cerrar la app) usa la
exportación XML y ``RekordboxXmlParser``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

SMART_PLAYLIST_ATTRIBUTE = 4
FOLDER_ATTRIBUTE = 1


def _name_of(related: Any) -> str | None:
    """Lee ``.Name`` de una relación (Artist, Genre…) tolerando None."""
    if related is None:
        return None
    name = getattr(related, "Name", None)
    return str(name) if name else None


def _key_of(content: Any) -> str | None:
    key = getattr(content, "Key", None)
    if key is None:
        return None
    for attr in ("ScaleName", "Scale", "Name"):
        value = getattr(key, attr, None)
        if value:
            return str(value)
    return None


def content_to_fields(content: Any) -> dict[str, Any]:
    """Traduce un ``DjmdContent`` de pyrekordbox a campos planos (testeable sin BD)."""
    return {
        "track_id": getattr(content, "ID", ""),
        "title": getattr(content, "Title", None),
        "artist": _name_of(getattr(content, "Artist", None)),
        "bpm": getattr(content, "BPM", None),
        "key": _key_of(content),
        "duration": getattr(content, "Length", None),
        "genre": _name_of(getattr(content, "Genre", None)),
        "location": getattr(content, "FolderPath", None),
    }


class Rekordbox6DatabaseReader:
    source: TrackSource = TrackSource.REKORDBOX

    def __init__(self, db_dir: Path | None = None) -> None:
        self.db_dir = db_dir

    def read(self) -> ParseResult:
        try:
            from pyrekordbox import Rekordbox6Database
        except ImportError as exc:
            raise RuntimeError(
                "pyrekordbox no está instalado. Instálalo con: pip install -e '.[rekordbox]'"
            ) from exc

        try:
            db = Rekordbox6Database(db_dir=str(self.db_dir)) if self.db_dir else Rekordbox6Database()
        except Exception as exc:  # pyrekordbox lanza varios tipos según la causa
            raise RuntimeError(
                "No se pudo abrir la base de datos de Rekordbox. Comprueba que Rekordbox "
                f"está completamente cerrado. Detalle: {exc}"
            ) from exc

        try:
            acc = TrackAccumulator(self.source)
            for content in db.get_content():
                fields = content_to_fields(content)
                acc.add(**fields, payload={"ID": str(fields["track_id"])})
            valid_ids = {t.id for t in acc.tracks}
            playlists = self._read_playlists(db, valid_ids)
        finally:
            db.close()

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    @staticmethod
    def _read_playlists(db: Any, valid_ids: set[str]) -> dict[str, list[str]]:
        playlists: dict[str, list[str]] = {}
        try:
            for playlist in db.get_playlist():
                attribute = getattr(playlist, "Attribute", 0)
                if attribute in (FOLDER_ATTRIBUTE, SMART_PLAYLIST_ATTRIBUTE):
                    continue
                songs = sorted(getattr(playlist, "Songs", []) or [], key=lambda s: getattr(s, "TrackNo", 0) or 0)
                ids = [str(getattr(s, "ContentID", "")) for s in songs]
                playlists[str(getattr(playlist, "Name", "Playlist"))] = [i for i in ids if i in valid_ids]
        except Exception:  # las playlists son opcionales: si fallan, se usa la colección entera
            return {}
        return playlists
''',
    'src/parsers/rekordbox_xml.py': r'''"""
Parser del XML de colección de Rekordbox (Archivo → Exportar colección en formato xml).

Funciona con cualquier versión de Rekordbox (6 y 7) y no requiere cerrar la app.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

PLAYLIST_NODE_TYPE = "1"


def location_to_path(location: str | None) -> str | None:
    """``file://localhost/Users/x/My%20Track.mp3`` → ``/Users/x/My Track.mp3``."""
    if not location:
        return None
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    path = unquote(parsed.path)
    # Windows: /C:/Music/... → C:/Music/...
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


def _split_tags(*values: str | None) -> list[str]:
    tags: list[str] = []
    for value in values:
        if value:
            tags.extend(part for part in value.replace(",", " / ").split(" / ") if part.strip())
    return tags


class RekordboxXmlParser:
    source: TrackSource = TrackSource.REKORDBOX

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith(".xml") and b"DJ_PLAYLISTS" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"XML de Rekordbox mal formado: {exc}") from exc
        if root.tag != "DJ_PLAYLISTS":
            raise ValueError("El fichero no es un XML de colección de Rekordbox (falta DJ_PLAYLISTS).")

        acc = TrackAccumulator(self.source)
        for node in root.iterfind("./COLLECTION/TRACK"):
            attrs = dict(node.attrib)
            acc.add(
                track_id=attrs.get("TrackID", ""),
                title=attrs.get("Name"),
                artist=attrs.get("Artist"),
                bpm=attrs.get("AverageBpm"),
                key=attrs.get("Tonality"),
                duration=attrs.get("TotalTime"),
                genre=attrs.get("Genre"),
                tags=_split_tags(attrs.get("Label"), attrs.get("Grouping")),
                location=location_to_path(attrs.get("Location")),
                payload=attrs,
            )

        valid_ids = {t.id for t in acc.tracks}
        playlists: dict[str, list[str]] = {}
        self._collect_playlists(root.find("./PLAYLISTS/NODE"), [], playlists, valid_ids)

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    def _collect_playlists(
        self,
        node: ET.Element | None,
        path: list[str],
        out: dict[str, list[str]],
        valid_ids: set[str],
    ) -> None:
        if node is None:
            return
        name = node.get("Name", "")
        if node.get("Type") == PLAYLIST_NODE_TYPE:
            ids = [t.get("Key", "") for t in node.iterfind("TRACK")]
            label = " / ".join([*path, name]) if path else name
            out[label] = [i for i in ids if i in valid_ids]
            return
        child_path = path if name == "ROOT" else [*path, name]
        for child in node.iterfind("NODE"):
            self._collect_playlists(child, child_path, out, valid_ids)
''',
    'src/parsers/traktor_nml.py': r'''"""Parser de la colección de Traktor (``collection.nml``)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.core.keys import pitch_class_to_camelot
from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator


def traktor_key(musical_key_value: str | None, info_key: str | None) -> str | None:
    """
    ``MUSICAL_KEY VALUE``: 0–11 mayores (C…B), 12–23 menores (Cm…Bm).
    Si falta, se usa el texto de ``INFO KEY`` (Open Key, Camelot o clásica).
    """
    if musical_key_value is not None and musical_key_value.strip().isdigit():
        value = int(musical_key_value)
        if 0 <= value <= 23:
            return pitch_class_to_camelot(value % 12, minor=value >= 12)
    return info_key


def traktor_path(volume: str | None, directory: str | None, filename: str | None) -> str | None:
    """``DIR="/:Users/:me/:Music/:"`` → ``/Users/me/Music/``; en Windows antepone el volumen."""
    if not filename:
        return None
    path = (directory or "").replace("/:", "/") + filename
    if volume and len(volume) == 2 and volume[1] == ":":
        return volume + path
    return path


def primary_key(volume: str | None, directory: str | None, filename: str | None) -> str:
    """Formato de ``PRIMARYKEY KEY`` en las playlists de Traktor."""
    return f"{volume or ''}{directory or ''}{filename or ''}"


class TraktorNmlParser:
    source: TrackSource = TrackSource.TRAKTOR

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith(".nml") or b"<NML" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"NML de Traktor mal formado: {exc}") from exc
        if root.tag != "NML":
            raise ValueError("El fichero no es una colección de Traktor (falta <NML>).")

        acc = TrackAccumulator(self.source)
        for entry in root.iterfind("./COLLECTION/ENTRY"):
            location = entry.find("LOCATION")
            info = entry.find("INFO")
            tempo = entry.find("TEMPO")
            musical_key = entry.find("MUSICAL_KEY")
            volume = location.get("VOLUME") if location is not None else None
            directory = location.get("DIR") if location is not None else None
            filename = location.get("FILE") if location is not None else None
            acc.add(
                track_id=primary_key(volume, directory, filename) or entry.get("AUDIO_ID", ""),
                title=entry.get("TITLE"),
                artist=entry.get("ARTIST"),
                bpm=tempo.get("BPM") if tempo is not None else None,
                key=traktor_key(
                    musical_key.get("VALUE") if musical_key is not None else None,
                    info.get("KEY") if info is not None else None,
                ),
                duration=info.get("PLAYTIME") if info is not None else None,
                genre=info.get("GENRE") if info is not None else None,
                tags=[info.get("LABEL", "")] if info is not None and info.get("LABEL") else [],
                location=traktor_path(volume, directory, filename),
                payload={k: v for k, v in entry.attrib.items()},
            )

        valid_ids = {t.id for t in acc.tracks}
        playlists: dict[str, list[str]] = {}
        for node in root.iter("NODE"):
            if node.get("TYPE") != "PLAYLIST":
                continue
            playlist = node.find("PLAYLIST")
            if playlist is None:
                continue
            ids = [pk.get("KEY", "") for pk in playlist.iter("PRIMARYKEY")]
            playlists[node.get("NAME", "Playlist")] = [i for i in ids if i in valid_ids]

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
''',
    'src/parsers/virtualdj_xml.py': r'''"""Parser de la base de datos de VirtualDJ (``database.xml``)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator, parse_float


def vdj_bpm(value: str | None) -> float | None:
    """VirtualDJ guarda segundos por beat (0.483871 → 124 BPM); versiones antiguas, BPM directo."""
    number = parse_float(value)
    if number is None or number <= 0:
        return None
    return round(60.0 / number, 2) if number < 5 else round(number, 2)


class VirtualDjXmlParser:
    source: TrackSource = TrackSource.VIRTUALDJ

    def can_parse(self, filename: str, head: bytes) -> bool:
        return b"VirtualDJ_Database" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"database.xml de VirtualDJ mal formado: {exc}") from exc
        if root.tag != "VirtualDJ_Database":
            raise ValueError("El fichero no es una base de datos de VirtualDJ.")

        acc = TrackAccumulator(self.source)
        for song in root.iterfind("Song"):
            tags = song.find("Tags")
            infos = song.find("Infos")
            scan = song.find("Scan")
            path = song.get("FilePath")
            key = (tags.get("Key") if tags is not None else None) or (
                scan.get("Key") if scan is not None else None
            )
            bpm_raw = (scan.get("Bpm") if scan is not None else None) or (
                tags.get("Bpm") if tags is not None else None
            )
            acc.add(
                track_id=path or f"vdj-{len(acc.tracks) + acc.skipped + 1}",
                title=tags.get("Title") if tags is not None else None,
                artist=tags.get("Author") if tags is not None else None,
                bpm=vdj_bpm(bpm_raw),
                key=key,
                duration=infos.get("SongLength") if infos is not None else None,
                genre=tags.get("Genre") if tags is not None else None,
                location=path,
                payload=dict(song.attrib),
            )

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
''',
    'tests/__init__.py': r'''"""Tests."""
''',
    'tests/conftest.py': r'''from __future__ import annotations

import pytest

from src.core.models import RawSource, SetConstraint, TrackSource, UniversalTrack


def make_track(
    track_id: str,
    bpm: float = 124.0,
    key: str = "8A",
    energy: float = 5.0,
    duration_sec: int = 360,
    genre: str | None = "Tech House",
    title: str | None = None,
    artist: str = "Test",
    location: str | None = None,
) -> UniversalTrack:
    return UniversalTrack(
        id=track_id,
        title=title or f"Track {track_id}",
        artist=artist,
        bpm=bpm,
        key=key,
        energy=energy,
        duration_sec=duration_sec,
        genre=genre,
        raw_source=RawSource(system=TrackSource.SYNTHETIC, location=location),
    )


@pytest.fixture
def collection() -> list[UniversalTrack]:
    keys = ["8A", "9A", "9B", "10A", "10B", "11A", "8B", "7A", "6A", "5A", "4A", "3A"]
    tracks: list[UniversalTrack] = []
    for i in range(36):
        energy = 2.0 + (i % 9)  # 2..10
        tracks.append(
            make_track(
                f"t{i:02d}",
                bpm=118.0 + (energy - 2.0) * 1.2,
                key=keys[i % len(keys)],
                energy=min(energy, 10.0),
            )
        )
    return tracks


@pytest.fixture
def constraints() -> SetConstraint:
    return SetConstraint(total_duration_min=60, target_genres=["tech house"])
''',
    'tests/test_core.py': r'''from __future__ import annotations
import pytest

from src.core.harmonic_engine import TransitionType
from src.core.models import SetConstraint
from src.core.timeline import allocate_slot_counts, build_timeline, ENERGY_PROFILES
from src.core.transitions import effective_bpm_delta, evaluate_transition
from tests.conftest import make_track


def test_half_double_time_resolution() -> None:
    delta, pct = effective_bpm_delta(87.0, 174.0)
    assert pct == 0.0 and delta == 0.0


def test_adjacent_transition_is_valid_and_cheap() -> None:
    ev = evaluate_transition(make_track("a", key="8A"), make_track("b", key="9A", bpm=125.0))
    assert ev.transition_type is TransitionType.ADJACENT
    assert ev.is_valid and ev.cost < 1.0


def test_strict_rejects_energy_boost() -> None:
    a, b = make_track("a", key="8A"), make_track("b", key="10A")
    assert evaluate_transition(a, b, "energy_boost").is_valid
    assert not evaluate_transition(a, b, "strict").is_valid


def test_big_pitch_is_invalid() -> None:
    ev = evaluate_transition(make_track("a", bpm=120.0), make_track("b", bpm=132.0))
    assert not ev.is_valid


def test_slot_allocation_sums_exactly() -> None:
    for profile in ENERGY_PROFILES.values():
        for n in range(1, 30):
            assert sum(allocate_slot_counts(profile, n)) == n


def test_warmup_to_peak_timeline_shape(collection: list) -> None:
    constraints = SetConstraint(total_duration_min=60)
    slots = build_timeline(constraints, collection)
    assert len(slots) == 10  # 3600 s / 360 s
    phases = [s["phase"] for s in slots]
    assert phases.count("peak_time") == 5
    assert phases[0] == "warmup" and phases[-1] == "closing"
    assert slots[-1]["end_sec"] == 3600


def test_custom_phases_override_profile(collection: list) -> None:
    from src.core.models import PhaseSpec

    constraints = SetConstraint(
        total_duration_min=60,
        avg_track_duration_min=5.0,
        energy_phases=(
            PhaseSpec(name="intro", weight=1, energy_min=1, energy_max=3),
            PhaseSpec(name="drive", weight=3, energy_min=6, energy_max=9),
        ),
    )
    slots = build_timeline(constraints, collection)
    assert len(slots) == 12
    assert [s["phase"] for s in slots].count("intro") == 3
    assert all(1 <= s["target_energy"] <= 3 for s in slots if s["phase"] == "intro")


def test_phase_spec_validation() -> None:
    import pytest
    from pydantic import ValidationError

    from src.core.models import PhaseSpec

    with pytest.raises(ValidationError):
        PhaseSpec(name="x", weight=0.5, energy_min=8, energy_max=3)
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, energy_phases=())


@pytest.mark.parametrize("strictness", ["strict", "energy_boost", "permissive"])
@pytest.mark.parametrize("profile", ["warmup_to_peak", "rollercoaster", "constant"])
def test_proposal_key_path_is_always_valid(strictness: str, profile: str) -> None:
    from src.core.harmonic_engine import StrictnessLevel, evaluate_harmonic_transition
    from src.core.proposal import plan_key_path
    from src.core.transitions import ALLOWED_HARMONIC_TYPES

    constraints = SetConstraint(
        total_duration_min=120, harmonic_strictness=strictness, energy_curve_profile=profile  # type: ignore[arg-type]
    )
    slots = build_timeline(constraints, [])
    keys = plan_key_path(slots, constraints.harmonic_strictness, "11B")
    assert keys[0] == "11B" and len(keys) == len(slots)
    for a, b in zip(keys, keys[1:]):
        kind, _ = evaluate_harmonic_transition(a, b, StrictnessLevel(strictness))
        assert kind in ALLOWED_HARMONIC_TYPES[strictness]


def test_genre_bpm_presets() -> None:
    from src.core.genres import genre_bpm_range
    from src.core.timeline import resolve_bpm_range

    assert genre_bpm_range(["Drum and Bass"]) == (170.0, 176.0)
    assert genre_bpm_range(["unknown"]) is None
    c = SetConstraint(total_duration_min=60, target_genres=["house", "techno"], bpm_max=130)
    assert resolve_bpm_range(c, []) == (118.0, 130.0)
''',
    'tests/test_enrichment_providers.py': r'''"""Tests de los proveedores alternativos de sugerencias del modo propuesta."""

from __future__ import annotations

from typing import Any

import pytest

from src.enrichment.common import SuggestionReport
from src.enrichment.lastfm import suggest_tracks_for_proposal_lastfm
from src.enrichment.llm_agent import suggest_tracks_for_proposal_llm
from tests.conftest import make_track


# --------------------------------------------------------------------------- #
# Last.fm
# --------------------------------------------------------------------------- #
class FakeLastfm:
    """Doble de ``tag.gettoptracks``: ``tracks_by_tag[tag]`` es la lista completa de items."""

    def __init__(self, tracks_by_tag: dict[str, list[dict[str, Any]]] | None = None, fail: bool = False) -> None:
        self.tracks_by_tag = tracks_by_tag or {}
        self.fail = fail
        self.calls: list[tuple[str, int]] = []  # (tag, page)

    def __call__(self, method: str, **params: str) -> dict[str, Any]:
        assert method == "tag.gettoptracks"
        if self.fail:
            raise RuntimeError("Last.fm: Invalid API key (código 10)")
        tag, page, limit = params["tag"], int(params["page"]), int(params["limit"])
        self.calls.append((tag, page))
        items = self.tracks_by_tag.get(tag, [])
        start = (page - 1) * limit
        return {"tracks": {"track": items[start : start + limit]}}


def _item(artist: str, title: str) -> dict[str, Any]:
    return {"name": title, "artist": {"name": artist}, "url": f"https://www.last.fm/music/{artist}/_/{title}"}


def test_suggest_tracks_for_proposal_lastfm_success() -> None:
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9B")]
    fake = FakeLastfm({"tech house": [_item("A1", "T1"), _item("A2", "T2")]})
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, ["tech house"], "key", client=fake)
    assert {t.raw_source.payload["suggested_title"] for t in out} == {"T1", "T2"}
    assert all(t.raw_source.payload["suggested_source"] == "Last.fm" for t in out)
    assert all(t.raw_source.payload["suggested_url"].startswith("https://www.last.fm/") for t in out)
    # El BPM/clave/energía del slot original nunca cambian.
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert report.suggested == 2 and report.fell_back == 0 and report.source == "Last.fm"


def test_suggest_tracks_for_proposal_lastfm_single_result_is_a_dict_not_a_list() -> None:
    """Last.fm devuelve un objeto suelto (no una lista) cuando el tag solo tiene un resultado."""

    class SingleResultLastfm(FakeLastfm):
        def __call__(self, method: str, **params: str) -> dict[str, Any]:
            assert method == "tag.gettoptracks"
            if params["page"] != "1":
                return {"tracks": {"track": []}}
            return {"tracks": {"track": _item("Solo Artist", "Solo Track")}}

    out, report = suggest_tracks_for_proposal_lastfm(
        [make_track("s1")], ["deep house"], "key", client=SingleResultLastfm()
    )
    assert out[0].raw_source.payload["suggested_artist"] == "Solo Artist"
    assert report.suggested == 1


def test_suggest_tracks_for_proposal_lastfm_not_enough_candidates_keeps_rest() -> None:
    placeholders = [make_track(f"s{i}", key="8A") for i in range(3)]
    fake = FakeLastfm({"electronic": [_item("A1", "T1")]})
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, [], "key", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "A1"
    assert out[1:] == placeholders[1:]
    assert report.suggested == 1 and report.fell_back == 2 and report.failed == 0


def test_suggest_tracks_for_proposal_lastfm_hard_failure_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, [], "bad-key", client=FakeLastfm(fail=True))
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and "10" in report.first_error


def test_suggest_tracks_for_proposal_lastfm_empty_input() -> None:
    out, report = suggest_tracks_for_proposal_lastfm([], [], "key", client=FakeLastfm())
    assert out == [] and report.attempted == 0


# --------------------------------------------------------------------------- #
# Agente IA (búsqueda web)
# --------------------------------------------------------------------------- #
class FakeAnthropicMessages:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleTextResponse(self.text or "[]")


class SimpleTextResponse:
    def __init__(self, text: str) -> None:
        self.content = [SimpleTextBlock(text)]


class SimpleTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class FakeAnthropicClient:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.messages = FakeAnthropicMessages(text=text, error=error)


def test_suggest_tracks_for_proposal_llm_success() -> None:
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9B")]
    text = (
        'Aquí tienes los temas:\n'
        '[{"artist": "Real Artist 0", "title": "Real Title 0", "url": "https://beatport.com/t/0"},'
        ' {"artist": "Real Artist 1", "title": "Real Title 1", "url": ""}]'
    )
    client = FakeAnthropicClient(text=text)
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=client)
    assert out[0].raw_source.payload["suggested_artist"] == "Real Artist 0"
    assert out[0].raw_source.payload["suggested_url"] == "https://beatport.com/t/0"
    assert out[1].raw_source.payload["suggested_artist"] == "Real Artist 1"
    assert "suggested_url" not in out[1].raw_source.payload
    assert all(t.raw_source.payload["suggested_source"] == "Agente IA (búsqueda web)" for t in out)
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert report.suggested == 2 and report.fell_back == 0
    assert client.messages.calls[0]["tools"][0]["type"] == "web_search_20250305"


def test_suggest_tracks_for_proposal_llm_keeps_placeholder_when_agent_finds_nothing() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    text = '[{"artist": null, "title": null}, {"artist": "Real Artist 1", "title": "Real Title 1"}]'
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=FakeAnthropicClient(text=text))
    assert out[0] == placeholders[0]
    assert out[1].raw_source.payload["suggested_artist"] == "Real Artist 1"
    assert report.suggested == 1 and report.fell_back == 1


def test_suggest_tracks_for_proposal_llm_malformed_response_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    client = FakeAnthropicClient(text="no soy json en absoluto")
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=client)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and report.first_error


def test_suggest_tracks_for_proposal_llm_api_failure_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    client = FakeAnthropicClient(error=RuntimeError("invalid x-api-key"))
    out, report = suggest_tracks_for_proposal_llm(placeholders, "bad-key", client=client)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and "invalid x-api-key" in report.first_error


def test_suggest_tracks_for_proposal_llm_empty_input() -> None:
    out, report = suggest_tracks_for_proposal_llm([], "key", client=FakeAnthropicClient(text="[]"))
    assert out == [] and report.attempted == 0


def test_suggest_tracks_for_proposal_llm_missing_package_raises_helpful_error() -> None:
    """Sin ``client`` inyectado y sin el paquete ``anthropic`` instalado, el error explica cómo instalarlo."""
    with pytest.raises(RuntimeError, match="anthropic"):
        suggest_tracks_for_proposal_llm([make_track("s1")], "key")


def test_suggestion_report_summary_includes_source_prefix() -> None:
    report = SuggestionReport(attempted=3, suggested=2, source="Last.fm")
    assert report.summary().startswith("Last.fm: 2/3")
''',
    'tests/test_graph.py': r'''from __future__ import annotations

from src.core.models import SetConstraint, UniversalTrack
from src.graph.builder import build_set_graph
from src.graph.nodes import CuratorReport, graph_search_node, parse_collection_node
from src.graph.state import SetGraphState, initial_state
from tests.conftest import make_track


def test_graph_has_expected_nodes() -> None:
    nodes = set(build_set_graph().get_graph().nodes)
    assert {
        "parse_collection_node",
        "build_timeline_slots_node",
        "graph_search_node",
        "llm_curator_node",
        "proposal_node",
    } <= nodes


def test_full_run_builds_complete_set(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    result = build_set_graph().invoke(initial_state(constraints, collection))
    assert result["current_step"] == "llm_curator"
    assert len(result["selected_set"]) == len(result["target_slots"]) == 10
    assert len({t.id for t in result["selected_set"]}) == 10
    assert len(result["transitions"]) == 9
    assert "peak_time" in result["curator_notes"]
    peak = [t for t, s in zip(result["selected_set"], result["target_slots"]) if s["phase"] == "peak_time"]
    assert all(t.energy >= 5.0 for t in peak)


def test_run_is_deterministic(collection: list[UniversalTrack], constraints: SetConstraint) -> None:
    graph = build_set_graph()
    first = graph.invoke(initial_state(constraints, collection))
    second = graph.invoke(initial_state(constraints, list(reversed(collection))))
    assert [t.id for t in first["selected_set"]] == [t.id for t in second["selected_set"]]


def test_no_collection_builds_proposal() -> None:
    constraints = SetConstraint(
        total_duration_min=60, target_genres=["Techno"], avg_track_duration_min=5,
        harmonic_strictness="strict", start_key="5A",
    )
    result = build_set_graph().invoke(initial_state(constraints))
    assert result["mode"] == "proposal"
    selected = result["selected_set"]
    assert len(selected) == 12 and selected[0].key == "5A"
    assert all(128 <= t.bpm <= 138 for t in selected)  # rango típico de techno
    assert all(ev.is_valid for ev in result["transitions"])
    assert result["curator_notes"].startswith("Propuesta sin colección")
    assert result["violations"] == []


def test_filtered_out_collection_falls_back_to_proposal(constraints: SetConstraint) -> None:
    tracks = [make_track("a", genre="Techno")]
    result = build_set_graph().invoke(initial_state(constraints, tracks))
    assert result["mode"] == "proposal"
    assert len(result["selected_set"]) == 10
    assert any("se genera una propuesta" in v for v in result["violations"])


def test_parse_dedupes_and_filters_bpm() -> None:
    constraints = SetConstraint(total_duration_min=30, bpm_min=120, bpm_max=126)
    tracks = [make_track("a", bpm=124), make_track("a", bpm=124), make_track("b", bpm=130)]
    update = parse_collection_node(initial_state(constraints, tracks))
    assert [t.id for t in update["available_tracks"]] == ["a"]
    assert any("duplicados" in v for v in update["violations"])


def test_energy_window_widens_instead_of_failing(constraints: SetConstraint) -> None:
    state: SetGraphState = initial_state(constraints, [make_track("a", energy=4.0)])
    state["target_slots"] = [
        {
            "index": 0, "phase": "peak_time", "start_sec": 0, "end_sec": 360,
            "target_bpm": 126.0, "energy_min": 5.5, "energy_max": 10.0, "target_energy": 7.0,
        }
    ]
    update = graph_search_node(state)
    assert [t.id for t in update["selected_set"]] == ["a"]
    assert any("ampliada" in v for v in update["violations"])


def test_custom_curator_can_reorder(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    def reversing_curator(state: SetGraphState) -> CuratorReport:
        ids = [t.id for t in state["selected_set"]]
        return CuratorReport(notes="reversed", reordered_ids=list(reversed(ids)))

    baseline = build_set_graph().invoke(initial_state(constraints, collection))
    result = build_set_graph(curator=reversing_curator).invoke(initial_state(constraints, collection))
    assert result["curator_notes"] == "reversed"
    assert [t.id for t in result["selected_set"]] == [t.id for t in reversed(baseline["selected_set"])]


def test_curator_rejects_invalid_permutation(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    def bad_curator(state: SetGraphState) -> CuratorReport:
        return CuratorReport(notes="bad", reordered_ids=["nope"])

    result = build_set_graph(curator=bad_curator).invoke(initial_state(constraints, collection))
    assert any("permutación" in v for v in result["violations"])
    assert len(result["selected_set"]) == 10
''',
    'tests/test_io.py': r'''from __future__ import annotations

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.keys import camelot_to_pitch_class, pitch_class_to_camelot, to_camelot
from src.enrichment.spotify import enrich_with_spotify, suggest_tracks_for_proposal
from src.exporters import set_rows, to_csv, to_m3u8, to_rekordbox_xml
from src.graph.nodes import parse_collection_node
from src.graph.state import initial_state
from src.parsers import parse_file
from src.parsers.rekordbox_db import content_to_fields
from src.parsers.rekordbox_xml import location_to_path
from tests.conftest import make_track

RB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>
  <COLLECTION Entries="4">
    <TRACK TrackID="1" Name="Night Drive" Artist="A" Genre="Tech House" TotalTime="392"
           AverageBpm="124.00" Tonality="Am" Location="file://localhost/Users/me/Music/Night%20Drive.aiff"/>
    <TRACK TrackID="2" Name="Sunrise" Artist="B" Genre="Tech House" TotalTime="410"
           AverageBpm="126.00" Tonality="9A" Location="file://localhost/C:/Music/Sunrise.mp3"/>
    <TRACK TrackID="3" Name="No Key" Artist="C" Genre="Techno" TotalTime="300" AverageBpm="130.00" Tonality=""/>
    <TRACK TrackID="4" Name="G sharp" Artist="D" Genre="Techno" TotalTime="300" AverageBpm="131.00" Tonality="G#"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Type="0" Name="Gigs" Count="1">
        <NODE Name="Friday" Type="1" KeyType="0" Entries="3">
          <TRACK Key="2"/><TRACK Key="1"/><TRACK Key="3"/>
        </NODE>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Am", "8A"), ("C", "8B"), ("G#", "4B"), ("Abm", "1A"), ("F#m", "11A"), ("Bb", "6B"),
     ("8a", "8A"), ("1m", "8A"), ("6d", "1B"), ("C# minor", "12A"), ("", None), ("xx", None)],
)
def test_key_conversion(raw: str, expected: str | None) -> None:
    assert to_camelot(raw) == expected


def test_pitch_class_wheel_is_complete() -> None:
    keys = {pitch_class_to_camelot(pc, m) for pc in range(12) for m in (True, False)}
    assert len(keys) == 24


@pytest.mark.parametrize("number", range(1, 13))
@pytest.mark.parametrize("letter", ["A", "B"])
def test_camelot_to_pitch_class_round_trip(number: int, letter: str) -> None:
    """Inversa exacta: Camelot → pitch class/modo → Camelot debe devolver la misma clave."""
    camelot = f"{number}{letter}"
    pitch_class, mode = camelot_to_pitch_class(camelot)
    assert 0 <= pitch_class <= 11
    assert mode in (0, 1)
    assert pitch_class_to_camelot(pitch_class, minor=mode == 0) == camelot


def test_camelot_to_pitch_class_invalid() -> None:
    with pytest.raises(ValueError, match="Clave Camelot inválida"):
        camelot_to_pitch_class("Am")


def test_rekordbox_xml_parser() -> None:
    result = parse_file("collection.xml", RB_XML)
    assert [t.id for t in result.tracks] == ["1", "2", "4"]
    assert result.tracks[0].key == "8A" and result.tracks[2].key == "4B"
    assert result.tracks[0].raw_source.location == "/Users/me/Music/Night Drive.aiff"
    assert result.tracks[1].raw_source.location == "C:/Music/Sunrise.mp3"
    assert result.skipped == 1 and result.energy_estimated == 3
    assert result.playlists == {"Gigs / Friday": ["2", "1"]}
    assert result.genres == ["Tech House", "Techno"]


def test_location_to_path_passthrough() -> None:
    assert location_to_path(None) is None
    assert location_to_path("/plain/path.mp3") == "/plain/path.mp3"


def test_csv_parser_spanish_semicolon() -> None:
    data = (
        "Título;Artista;BPM;Tonalidad;Duración;Género;Energía\n"
        "Uno;X;124,5;Am;6:30;Techno;7\n"
        "Dos;Y;;Am;6:30;Techno;\n"
        "Tres;Z;128;F#m;400;Techno;\n"
    ).encode()
    result = parse_file("set.csv", data)
    assert [t.title for t in result.tracks] == ["Uno", "Tres"]
    assert result.tracks[0].bpm == 124.5 and result.tracks[0].duration_sec == 390
    assert result.tracks[0].energy == 7.0
    assert result.energy_estimated == 1 and result.skipped == 1


def test_csv_parser_missing_columns() -> None:
    with pytest.raises(ValueError, match="Faltan columnas"):
        parse_file("x.csv", b"title,artist\nA,B\n")


def test_unsupported_file() -> None:
    with pytest.raises(ValueError, match="Formato no soportado"):
        parse_file("x.mp3", b"ID3")


def test_rekordbox_db_content_mapping() -> None:
    content = SimpleNamespace(
        ID=77, Title="T", BPM=12400, Length=380, FolderPath="/m/t.mp3",
        Key=SimpleNamespace(ScaleName="Fm"), Genre=SimpleNamespace(Name="Techno"),
        Artist=SimpleNamespace(Name="Art"),
    )
    fields = content_to_fields(content)
    assert fields["key"] == "Fm" and fields["artist"] == "Art" and fields["genre"] == "Techno"
    assert fields["bpm"] == 12400


class FakeSpotify:
    def __init__(self, fail_features: bool) -> None:
        self.fail_features = fail_features

    def search(self, q: str, type: str, limit: int) -> dict[str, Any]:
        if "missing" in q:
            return {"tracks": {"items": []}}
        return {"tracks": {"items": [{"id": "sp-" + q}]}}

    def audio_features(self, ids: list[str]) -> list[dict[str, Any]]:
        if self.fail_features:
            raise RuntimeError("http status: 403")
        return [{"energy": 0.83, "key": 9, "mode": 0} for _ in ids]


def test_spotify_enrichment_success() -> None:
    tracks = [make_track("a", key="1A", energy=3.0), make_track("missing", key="1A")]
    tracks[1] = tracks[1].model_copy(update={"title": "missing"})
    out, report = enrich_with_spotify(tracks, "", "", client=FakeSpotify(False))
    assert out[0].energy == 8.3 and out[0].key == "8A"
    assert out[1] == tracks[1]
    assert report.enriched == 1 and report.not_found == 1 and report.fell_back == 1


def test_spotify_403_is_reported_not_silent() -> None:
    tracks = [make_track("a"), make_track("b")]
    out, report = enrich_with_spotify(tracks, "", "", client=FakeSpotify(True))
    assert out == tracks
    assert report.failed == 2 and "403" in report.first_error
    assert "2 usan la estimación por BPM" in report.summary()


def test_exports() -> None:
    parsed = parse_file("collection.xml", RB_XML).tracks
    no_path = make_track("np")
    tracks = [*parsed[:2], no_path]
    m3u, missing = to_m3u8(tracks, "Friday")
    assert missing == 1 and "/Users/me/Music/Night Drive.aiff" in m3u and m3u.startswith("#EXTM3U")

    xml, missing_xml = to_rekordbox_xml(tracks, "Friday")
    assert missing_xml == 1
    root = ET.fromstring(xml.split("\n", 1)[1])
    locations = [t.get("Location") for t in root.iterfind("./COLLECTION/TRACK")]
    assert locations == [
        "file://localhost/Users/me/Music/Night%20Drive.aiff",
        "file://localhost/C:/Music/Sunrise.mp3",
    ]
    assert [t.get("Key") for t in root.iterfind(".//NODE[@Name='Friday']/TRACK")] == ["1", "2"]
    # Ida y vuelta: el XML exportado se vuelve a leer igual.
    assert [t.title for t in parse_file("x.xml", xml.encode()).tracks] == ["Night Drive", "Sunrise"]

    csv_text = to_csv(set_rows(tracks, [], []))
    assert csv_text.splitlines()[0].startswith("position,phase,artist")
    assert len(csv_text.splitlines()) == 4


NML = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19"><COLLECTION ENTRIES="2">
<ENTRY TITLE="Deep One" ARTIST="T1"><LOCATION DIR="/:Users/:me/:Music/:" FILE="deep.mp3" VOLUME="Macintosh HD"/>
<INFO GENRE="Techno" PLAYTIME="400" KEY="1m"/><TEMPO BPM="130.000"/><MUSICAL_KEY VALUE="21"/></ENTRY>
<ENTRY TITLE="Win Track" ARTIST="T2"><LOCATION DIR="/:Music/:" FILE="w.mp3" VOLUME="C:"/>
<INFO GENRE="Techno" PLAYTIME="380" KEY="6d"/><TEMPO BPM="131.000"/></ENTRY>
</COLLECTION><PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1">
<NODE TYPE="PLAYLIST" NAME="Sat"><PLAYLIST ENTRIES="1" TYPE="LIST">
<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="C:/:Music/:w.mp3"/></ENTRY></PLAYLIST></NODE>
</SUBNODES></NODE></PLAYLISTS></NML>"""

VDJ = b"""<?xml version="1.0" encoding="UTF-8"?>
<VirtualDJ_Database Version="2024">
<Song FilePath="D:\\Music\\a.mp3" FileSize="1"><Tags Author="V" Title="VA" Genre="House" Key="Am"/>
<Infos SongLength="360.5"/><Scan Bpm="0.483871" Key="Am"/></Song>
<Song FilePath="D:\\Music\\b.mp3"><Tags Author="V" Title="No bpm" Key="C"/><Infos SongLength="300"/></Song>
</VirtualDJ_Database>"""


def test_traktor_nml_parser() -> None:
    result = parse_file("collection.nml", NML)
    first, second = result.tracks
    assert first.key == "8A"  # MUSICAL_KEY 21 → 21-12 = 9 → A minor
    assert first.raw_source.location == "/Users/me/Music/deep.mp3"
    assert second.key == "1B" and second.raw_source.location == "C:/Music/w.mp3"
    assert result.playlists == {"Sat": ["C:/:Music/:w.mp3"]}


def test_virtualdj_parser() -> None:
    result = parse_file("database.xml", VDJ)
    assert [t.title for t in result.tracks] == ["VA"]
    assert result.tracks[0].bpm == 124.0 and result.tracks[0].key == "8A"
    assert result.tracks[0].duration_sec == 360 and result.skipped == 1


def _make_engine_db(path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE Track (id INTEGER PRIMARY KEY, title TEXT, artist TEXT, bpm REAL,
                            bpmAnalyzed REAL, key INTEGER, length INTEGER, genre TEXT, path TEXT);
        INSERT INTO Track VALUES (1,'E1','X',124,124.0,1,390,'House','../Music/e1.mp3');
        INSERT INTO Track VALUES (2,'E2','Y',126,126.0,23,400,'House','../Music/e2.mp3');
        INSERT INTO Track VALUES (3,'E3','Z',126,126.0,NULL,400,'House','../Music/e3.mp3');
        CREATE TABLE Playlist (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE PlaylistEntity (id INTEGER PRIMARY KEY, listId INTEGER, trackId INTEGER, nextEntityId INTEGER);
        INSERT INTO Playlist VALUES (1, 'Warm');
        INSERT INTO PlaylistEntity VALUES (10, 1, 2, 11), (11, 1, 1, 0);
        """
    )
    con.commit()
    con.close()


def test_engine_dj_parser(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "m.db"
    _make_engine_db(db)
    result = parse_file("m.db", db.read_bytes())
    assert [(t.id, t.key) for t in result.tracks] == [("1", "8A"), ("2", "7A")]
    assert result.skipped == 1
    assert result.playlists == {"Warm": ["2", "1"]}


# --------------------------------------------------------------------------- #
# Deduplicación de temas repetidos en la biblioteca (mismo tema, id distinto)
# --------------------------------------------------------------------------- #
def test_dedupe_key_same_location_different_id() -> None:
    """El mismo fichero de audio reimportado en Rekordbox recibe un TrackID nuevo."""
    a = make_track("1", location="/Music/track.mp3")
    b = make_track("2", location="/Music/track.mp3")
    assert a.dedupe_key() == b.dedupe_key()


def test_dedupe_key_same_metadata_no_location() -> None:
    """Sin ruta de archivo, el mismo título/artista/BPM (redondeado) cuenta como duplicado."""
    a = make_track("1", title="Same Song", artist="Same Artist", bpm=124.1)
    b = make_track("2", title="Same Song", artist="Same Artist", bpm=124.4)
    assert a.dedupe_key() == b.dedupe_key()


def test_dedupe_key_distinguishes_different_songs() -> None:
    a = make_track("1", title="Song A", artist="Artist", bpm=124.0)
    b = make_track("2", title="Song B", artist="Artist", bpm=124.0)
    c = make_track("3", location="/Music/a.mp3")
    d = make_track("4", location="/Music/b.mp3")
    assert a.dedupe_key() != b.dedupe_key()
    assert c.dedupe_key() != d.dedupe_key()


def test_parse_collection_node_drops_real_world_duplicates(constraints) -> None:  # type: ignore[no-untyped-def]
    """
    Reproduce el bug reportado: la misma colección de Rekordbox con un tema
    reimportado (mismo archivo, TrackID distinto) no debe producir el tema
    dos veces en ``available_tracks``.
    """
    tracks = [
        make_track("1", genre="Tech House", location="/Music/a.mp3"),
        make_track("2", genre="Tech House", location="/Music/a.mp3"),  # reimportado
        make_track("3", genre="Tech House", title="Other", artist="X", bpm=125.0),
    ]
    state = initial_state(constraints, tracks)
    update = parse_collection_node(state)
    assert len(update["available_tracks"]) == 2
    assert any("duplicados descartados" in v for v in update["violations"])


class FakeGenreSearch:
    """
    Doble de ``spotipy.Spotify`` para probar ``suggest_tracks_for_proposal``:
    simula la vía principal (``search(type="track", q='genre:"..."')``) y la
    de reserva (``search(type="artist", ...)`` + ``artist_top_tracks``), tal
    como hace la implementación real. Ninguna de las dos usa texto libre ni
    ``recommendations``.
    """

    def __init__(
        self,
        track_hits: int = 0,
        artist_hits: int = 0,
        tracks_per_artist: int = 3,
        fail: bool = False,
    ) -> None:
        self.track_hits = track_hits
        self.artist_hits = artist_hits
        self.tracks_per_artist = tracks_per_artist
        self.fail = fail
        self.search_calls: list[tuple[str, str]] = []  # (q, type)

    def search(self, q: str, type: str, limit: int, offset: int = 0) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("http status: 403")
        self.search_calls.append((q, type))
        if type == "track":
            items = [
                {
                    "id": f"direct{i}",
                    "name": f"Direct Track {i}",
                    "artists": [{"name": f"Direct Artist {i}"}],
                    "external_urls": {"spotify": f"https://open.spotify.com/track/direct{i}"},
                }
                for i in range(offset, min(offset + limit, self.track_hits))
            ]
            return {"tracks": {"items": items}}
        if type == "artist":
            items = [
                {"id": f"artist{i}", "name": f"Real Artist {i}"}
                for i in range(offset, min(offset + limit, self.artist_hits))
            ]
            return {"artists": {"items": items}}
        raise AssertionError(f"tipo de búsqueda inesperado: {type}")

    def artist_top_tracks(self, artist_id: str, country: str = "US") -> dict[str, Any]:
        n = artist_id.removeprefix("artist")
        return {
            "tracks": [
                {
                    "id": f"top-{n}-{i}",
                    "name": f"Top Track {n}-{i}",
                    "artists": [{"name": f"Real Artist {n}"}],
                    "external_urls": {"spotify": f"https://open.spotify.com/track/top-{n}-{i}"},
                }
                for i in range(self.tracks_per_artist)
            ]
        }


def test_suggest_tracks_for_proposal_success_via_direct_track_search() -> None:
    """La vía principal (temas directos con filtro de género) basta por sí sola."""
    placeholders = [make_track("s1", key="8A", bpm=124.0), make_track("s2", key="9B", bpm=126.0)]
    fake = FakeGenreSearch(track_hits=10)
    out, report = suggest_tracks_for_proposal(placeholders, ["tech house"], "", "", client=fake)
    assert {t.raw_source.payload["suggested_title"] for t in out} == {"Direct Track 0", "Direct Track 1"}
    assert all(t.raw_source.payload["suggested_url"].startswith("https://open.spotify.com/track/") for t in out)
    # El BPM/clave/energía del slot original nunca cambian.
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert out[1].bpm == placeholders[1].bpm and out[1].key == placeholders[1].key
    assert report.suggested == 2 and report.fell_back == 0
    assert all(t == "track" for _, t in fake.search_calls)  # nunca hizo falta la reserva por artista


def test_suggest_tracks_for_proposal_falls_back_to_artist_top_tracks() -> None:
    """Si los temas directos no bastan, completa con artistas del género + su top."""
    placeholders = [make_track(f"s{i}", key="8A") for i in range(4)]
    fake = FakeGenreSearch(track_hits=1, artist_hits=3, tracks_per_artist=2)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    titles = {t.raw_source.payload["suggested_artist"] for t in out}
    assert "Direct Artist 0" in titles
    assert any(a.startswith("Real Artist") for a in titles)
    assert report.suggested == 4 and report.fell_back == 0
    assert any(t == "artist" for _, t in fake.search_calls)  # sí recurrió a la reserva


def test_suggest_tracks_for_proposal_not_enough_candidates_keeps_rest() -> None:
    """Si ni temas directos ni artistas del género dan bastantes, el resto conserva el marcador."""
    placeholders = [make_track(f"s{i}", key="8A") for i in range(5)]
    fake = FakeGenreSearch(track_hits=0, artist_hits=1, tracks_per_artist=1)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "Real Artist 0"
    assert out[1:] == placeholders[1:]
    assert report.suggested == 1 and report.fell_back == 4 and report.failed == 0


def test_suggest_tracks_for_proposal_hard_failure_falls_back_for_all() -> None:
    """Credenciales inválidas u otro fallo de red: ningún slot se queda a medias."""
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9A"), make_track("s3", key="10A")]
    fake = FakeGenreSearch(fail=True)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 3 and "403" in report.first_error


def test_suggest_tracks_for_proposal_empty_input() -> None:
    out, report = suggest_tracks_for_proposal([], [], "", "", client=FakeGenreSearch())
    assert out == [] and report.attempted == 0


def test_suggest_tracks_for_proposal_uses_user_genre_before_fallback() -> None:
    """Prueba primero el género tal cual lo escribió el usuario, con el filtro de campo genre:."""
    fake = FakeGenreSearch()  # sin resultados en ninguna vía
    suggest_tracks_for_proposal([make_track("s1")], ["Progressive House"], "", "", client=fake)
    assert fake.search_calls[0] == ('genre:"Progressive House"', "track")


def test_suggest_tracks_for_proposal_skips_artist_with_no_top_tracks() -> None:
    """Un artista sin temas destacados no debe abortar la búsqueda para el resto."""

    class PartialArtists(FakeGenreSearch):
        def artist_top_tracks(self, artist_id: str, country: str = "US") -> dict[str, Any]:
            if artist_id == "artist0":
                raise RuntimeError("no top tracks")
            return super().artist_top_tracks(artist_id, country)

    placeholders = [make_track("s1", key="8A")]
    fake = PartialArtists(track_hits=0, artist_hits=2, tracks_per_artist=1)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "Real Artist 1"
    assert report.suggested == 1
''',
    'tests/test_models.py': r'''from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.energy import estimate_energy_from_bpm
from src.core.harmonic_engine import TransitionType
from src.core.models import SetConstraint, TransitionEvaluation
from tests.conftest import make_track


@pytest.mark.parametrize("key", ["1A", "9B", "10A", "12B", " 8a "])
def test_valid_camelot_keys(key: str) -> None:
    assert make_track("x", key=key).key == key.strip().upper()


@pytest.mark.parametrize("key", ["0A", "13B", "8C", "Am", "", "1AA"])
def test_invalid_camelot_keys(key: str) -> None:
    with pytest.raises(ValidationError):
        make_track("x", key=key)


def test_energy_bounds() -> None:
    with pytest.raises(ValidationError):
        make_track("x", energy=10.5)
    with pytest.raises(ValidationError):
        make_track("x", energy=-0.1)


def test_track_is_immutable_and_hashable() -> None:
    track = make_track("x")
    with pytest.raises(ValidationError):
        track.bpm = 130.0  # type: ignore[misc]
    assert len({track, make_track("x")}) == 1
    assert track.camelot_number == 8 and track.camelot_mode == "A"


def test_tags_normalized() -> None:
    track = make_track("x").model_copy(update={"tags": ("Vocal", "vocal", "Peak")})
    rebuilt = type(track).model_validate(track.model_dump(exclude={"camelot_number", "camelot_mode"}))
    assert rebuilt.tags == ("vocal", "peak")


def test_genre_matching() -> None:
    track = make_track("x", genre="Tech House")
    assert track.matches_genres([])
    assert track.matches_genres(["tech house"])
    assert not track.matches_genres(["techno"])
    assert not make_track("y", genre=None).matches_genres(["techno"])


def test_constraint_bpm_range_validation() -> None:
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, bpm_min=130, bpm_max=120)
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, harmonic_strictness="loose")  # type: ignore[arg-type]
    assert SetConstraint(total_duration_min=60, target_genres="Techno").target_genres == ["Techno"]


def test_transition_evaluation_model() -> None:
    ev = TransitionEvaluation(
        from_track_id="a",
        to_track_id="b",
        cost=0.2,
        transition_type=TransitionType.ADJACENT,
        bpm_delta=1.0,
        bpm_delta_pct=0.8,
        energy_delta=0.5,
        is_valid=True,
    )
    assert ev.transition_type is TransitionType.ADJACENT


@pytest.mark.parametrize(("bpm", "expected"), [(100, 1.0), (125, 5.0), (140, 10.0), (200, 10.0)])
def test_energy_estimation(bpm: float, expected: float) -> None:
    assert estimate_energy_from_bpm(bpm) == expected
''',
    'tests/test_web.py': r'''"""Smoke tests de la interfaz con el runner oficial de Streamlit (sin navegador)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.app.presenters import set_table  # noqa: E402
from src.core.models import SetConstraint  # noqa: E402
from src.graph.builder import build_set_graph  # noqa: E402
from src.graph.state import initial_state  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _run(at: AppTest) -> AppTest:
    at.run(timeout=30)
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_proposal_mode_end_to_end() -> None:
    at = _run(AppTest.from_file(APP))
    at.multiselect(key="genres").set_value(["Techno"])
    _run(at)
    at.button(key="build").click()
    _run(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Modo"] == "Propuesta"
    assert metrics["Temas"] == "12"  # 60 min / 5 min por tema
    assert at.dataframe[0].value["Camelot"].iloc[0] == "8A"


def test_demo_collection_end_to_end() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("demo")
    _run(at)
    at.button(key="build").click()
    _run(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Modo"] == "Colección"
    assert int(metrics["Temas"]) > 0


def test_upload_mode_prompts_for_file() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("upload")
    _run(at)
    assert any("Carga una colección" in i.value for i in at.info)


def test_limit_bpm_toggle_does_not_crash() -> None:
    """
    Regresión: ``st.slider`` exige que min_value/max_value/value/step compartan
    tipo. ``round()`` sin ``ndigits`` devuelve ``int``, así que construir
    ``value`` con ``round(...)`` sin convertir a ``float`` lanzaba
    ``StreamlitAPIException`` en cuanto se activaba "Fijar rango de BPM".
    """
    at = _run(AppTest.from_file(APP))
    at.toggle(key="limit_bpm").set_value(True)
    _run(at)
    lo, hi = at.slider(key="bpm_range").value
    assert isinstance(lo, float) and isinstance(hi, float)
    assert lo < hi


def test_proposal_mode_offers_suggestion_provider_choices() -> None:
    at = _run(AppTest.from_file(APP))
    radio = at.radio(key="suggestion_provider")
    assert radio.options == [
        "Sin sugerencias (solo BPM/clave/energía)",
        "Spotify (búsqueda por género)",
        "Last.fm (tags de género)",
        "Agente IA con búsqueda web (tu API key)",
    ]

    radio.set_value("Last.fm (tags de género)")
    at = _run(at)
    assert at.text_input(key="lastfm_api_key") is not None

    at.radio(key="suggestion_provider").set_value("Agente IA con búsqueda web (tu API key)")
    at = _run(at)
    assert at.text_input(key="llm_api_key") is not None
    assert at.text_input(key="llm_model").value == "claude-sonnet-5"


def test_collection_mode_hides_suggestion_provider_and_shows_spotify_enrichment() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("demo")
    at = _run(at)
    with pytest.raises(KeyError):
        at.radio(key="suggestion_provider")
    assert at.text_input(key="spotify_client_id") is not None


def test_proposal_table_has_search_hint() -> None:
    constraints = SetConstraint(total_duration_min=30, target_genres=["House"], avg_track_duration_min=5)
    state = build_set_graph().invoke(initial_state(constraints))
    table = set_table(state["selected_set"], state["target_slots"], state["transitions"], proposal=True)
    assert list(table.columns)[:4] == ["#", "Inicio", "Tramo", "Busca"]
    assert table["Busca"].iloc[0].startswith("House · ")


def test_proposal_table_shows_real_suggestions_when_present() -> None:
    """Cuando al menos un slot tiene una sugerencia real (de cualquier proveedor), aparecen sus columnas."""
    constraints = SetConstraint(total_duration_min=30, target_genres=["House"], avg_track_duration_min=5)
    state = build_set_graph().invoke(initial_state(constraints))
    selected = state["selected_set"]
    suggested_first = selected[0].model_copy(
        update={
            "raw_source": selected[0].raw_source.model_copy(
                update={
                    "payload": {
                        **selected[0].raw_source.payload,
                        "suggested_artist": "Real Artist",
                        "suggested_title": "Real Title",
                        "suggested_url": "https://open.spotify.com/track/1",
                        "suggested_source": "Spotify",
                    }
                }
            )
        }
    )
    enriched = [suggested_first, *selected[1:]]
    table = set_table(enriched, state["target_slots"], state["transitions"], proposal=True)
    assert "Sugerencia" in table.columns and "Fuente" in table.columns and "Enlace" in table.columns
    assert table["Sugerencia"].iloc[0] == "Real Artist – Real Title"
    assert table["Fuente"].iloc[0] == "Spotify"
    assert table["Enlace"].iloc[0] == "https://open.spotify.com/track/1"
    assert table["Sugerencia"].iloc[1] == "—"
''',
}


def ensure_directories(root: Path, dry_run: bool) -> list[Path]:
    created: list[Path] = []
    for rel in DIRECTORIES:
        path = root / rel
        if not path.is_dir():
            created.append(path)
            if not dry_run:
                path.mkdir(parents=True, exist_ok=True)
    return created


def write_files(root: Path, force: bool, dry_run: bool) -> tuple[list[Path], list[Path]]:
    written: list[Path] = []
    skipped: list[Path] = []
    for rel, content in FILES.items():
        path = root / rel
        if path.exists() and not force:
            skipped.append(path)
            continue
        written.append(path)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return written, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera la estructura inicial del proyecto.")
    parser.add_argument("--force", action="store_true", help="Sobrescribe ficheros existentes.")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada, solo informa.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Directorio destino.")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    created_dirs = ensure_directories(root, args.dry_run)
    written, skipped = write_files(root, args.force, args.dry_run)

    prefix = "[dry-run] " if args.dry_run else ""
    for path in created_dirs:
        print(f"{prefix}+ dir   {path.relative_to(root)}")
    for path in written:
        print(f"{prefix}+ file  {path.relative_to(root)}")
    for path in skipped:
        print(f"{prefix}= keep  {path.relative_to(root)}")
    print(
        f"\n{prefix}{len(created_dirs)} carpetas, {len(written)} ficheros escritos, "
        f"{len(skipped)} conservados."
    )
    if written and not args.dry_run:
        print("Siguiente paso: pip install -e '.[all]' && streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
