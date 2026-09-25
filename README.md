# rekordbox-setbuilder — Next-Gen DJ SetBuilder

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
