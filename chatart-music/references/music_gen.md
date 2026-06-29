````
# Music Generation Module

Generate music (with or without vocals) using the ChatArt Music API, backed by Suno models.

## Subcommands

| Subcommand       | Description |
|------------------|-------------|
| `run`            | Submit task AND poll until done — **DEFAULT**, use this first |
| `submit`         | Submit only, print `question_id`, exit — use for parallel batch jobs |
| `query`          | Poll an existing `question_id` until done (or timeout) |
| `list-models`    | Show supported music models and pricing |
| `estimate-cost`  | Estimate credit cost for a generation request |

## Models (Display Name → gpt_type)

| Display Name        | gpt_type          | Credits (per task) |
|---------------------|-------------------|-------------------|
| Art Music 3.5       | suno-3.5          | 16                |
| Art Music 4         | suno-4            | 20                |
| Art Music 4.5       | suno-4.5          | 24                |
| Art Music 4.5 Plus  | suno-4.5-plus     | 28                |
| Art Music 5         | suno-5            | 32                |
| Art Music 5.5       | suno-5.5          | 20                |

Default: **Art Music 5.5**.

> Each task generates **2 tracks**. Pricing shown is the TOTAL cost per task (not per track). Price is the same for both pure instrumental and vocal tracks.

## Parameters

| Parameter         | Required | Description |
|-------------------|----------|-------------|
| `--model`         | optional | Display name (see table). Default: `Art Music 5.5` |
| `--prompt`        | **yes**  | Music style / scene description (e.g. "Soul ballad, slow groove") |
| `--is-pure-music` | **yes**  | `true` for instrumental, `false` for vocal |
| `--music-style`   | optional | Comma-separated style tags, e.g. `Pop,Piano,Sad`. See `music_style.md` |
| `--singing-voice` | conditional | Required when `--is-pure-music false`. One of `random` (default), `male`, `female` |
| `--title`         | optional | Music title |
| `--lyrics`        | conditional | Required when `--is-pure-music false` and user provides lyrics. Use `\n` for line breaks |

### Field contract (auto-enforced by `validate_args`)

```
is_pure_music = true   →  action = "custom"   (no singing_voice, no lyrics)
is_pure_music = false  →  action = ""         (singing_voice required; lyrics optional)
```

## Usage

### `run` — full flow (default, ALWAYS use this first)

```bash
# Pure music (instrumental, no lyrics)
python {baseDir}/scripts/music_gen.py run \
    --model "Art Music 4.5" \
    --prompt "Soul ballad, slow groove, rhodes and clavinet, sensual brushed drums" \
    --is-pure-music true \
    --music-style "Pop,Piano,Sad" \
    --title "Sweet Confessions"

# Music with vocals + lyrics
python {baseDir}/scripts/music_gen.py run \
    --model "Art Music 4.5 Plus" \
    --prompt "Emotional Depth Plane, slow lovelorn female singer, soft R&B" \
    --is-pure-music false \
    --singing-voice female \
    --lyrics "[Verse 1]\nHaven't seen my mama in more than a few days..." \
    --title "I need a break"
```

### `submit` — submit only (for parallel batch jobs)

```bash
python {baseDir}/scripts/music_gen.py submit \
    --model "Art Music 4" \
    --prompt "Lofi hip hop beats to study to" \
    --is-pure-music true \
    --title "Study Lofi"

# → prints question_id (e.g. 577)
```

### `query` — resume a pending task

```bash
python {baseDir}/scripts/music_gen.py query --task-id 577
# polls until status=1 (done) or status=2 (failed), or --timeout reached
```

### `list-models`

```bash
python {baseDir}/scripts/music_gen.py list-models
# or JSON:
python {baseDir}/scripts/music_gen.py list-models --json
```

### `estimate-cost`

```bash
python {baseDir}/scripts/music_gen.py estimate-cost \
    --model "Art Music 4.5"
```

## API Endpoints

| Method | Path                              | Purpose                  |
|--------|-----------------------------------|--------------------------|
| POST   | `/web/music/create`               | Submit a music task      |
| GET    | `/web/music/get-task`             | Poll task status         |

Base URL: `https://chatartpro-api.ifonelab.net`

## Output

Each completed task returns 2 tracks. For each, the result shows:

- `url`        — direct download URL for the audio file (`.mp3`)
- `cover_url`  — cover image URL (`.png`)
- `title`      — track title
- `lyrics`     — generated lyrics (for vocal tracks)

A task is complete when `status == 1`. A task has failed when `status == 2`.

## Agent Workflow

1. **Start with `run`** — submits and auto-polls.
2. **Never hand a pending question_id back to the user** — always poll to completion.
3. **Only use `query`** when `run` has timed out and you have a question_id to resume.
4. **`query` keeps polling** — not just one check.
5. **`query` timeout? Use `--timeout 1200`** to extend it; do NOT resubmit (wastes credits).
6. **Task `status: 2` (failed)?** Do NOT auto-resubmit. Tell the user, ask if they want to retry.

## Decision Tree

```
→ New request?            Use run
→ run timed out?          Use query --task-id <id>
→ query timed out?        Use query --task-id <id> --timeout 1200
→ Task status = 2 (fail)? ❌ DO NOT auto-resubmit
                          → Return error to user, ask if retry
                          → User agrees → back to step 1
```

## See Also

- `auth.md` — login flow
- `error_handling.md` — error codes and recovery
- `user.md` — credit balance and history
- `music_style.md` — full list of music_style tags
````
