#!/usr/bin/env python3
"""Generate music using the ChatArt Music API (Suno-backed).

## AGENT INSTRUCTIONS — READ FIRST
- Default workflow: ALWAYS use `run` (submit + auto-poll).
  Do NOT ask the user to run query manually.
- Only use `query` when `run` has already timed out and a question_id exists,
  or when the user explicitly provides a question_id to resume.
- When using `query`, keep polling (default timeout=900s) until
  status is 1 (completed) or 2 (failed). Do NOT stop after a single check.
- Never hand a pending question_id back to the user and say "check it later".
  Always poll to completion within the timeout window.

Subcommands:
    run     Submit task AND poll until done — DEFAULT, use this first
    submit  Submit only, print question_id, exit — use for parallel batch jobs
    query   Poll an existing question_id until done (or timeout)
    list-models    List supported music models
    estimate-cost  Estimate credit cost for a generation request

Usage:
    # Pure music (instrumental, no lyrics)
    python music_gen.py run --model "Art Music 4.5" --prompt "..." \\
        --is-pure-music true --music-style "Pop,Piano" --title "Sweet Confessions"

    # Music with lyrics
    python music_gen.py run --model "Art Music 4.5 Plus" --prompt "..." \\
        --is-pure-music false --singing-voice female --lyrics "[Verse 1]\\n..."

    # Query
    python music_gen.py query --task-id 577

    # List models
    python music_gen.py list-models

    # Estimate cost
    python music_gen.py estimate-cost --model "Art Music 4.5"

"""

import argparse
import json as json_mod
import os
import sys
import time
import datetime
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from typing import Any, Optional
from shared.client import ChatArtClient, ChatArtError

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

ENDPOINTS = {
    "submit": "/web/music/create",
    "query":  "/web/music/get-task",
}

DEFAULT_TIMEOUT = 900
DEFAULT_INTERVAL = 15

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_MAP = {
    "Art Music 3.5": "suno-3.5",
    "Art Music 4": "suno-4",
    "Art Music 4.5": "suno-4.5",
    "Art Music 4.5 Plus": "suno-4.5-plus",
    "Art Music 5": "suno-5",
    "Art Music 5.5": "suno-5.5",
}

DEFAULT_MODEL = "Art Music 5.5"

VALID_SINGING_VOICES = ["random", "male", "female"]

# Load valid music_style tags from music_styles.json
_STYLES_FILE = Path(__file__).parent.parent / "music_styles.json"
_VALID_MUSIC_STYLES: set[str] = set()
_NORMALIZED_STYLES: dict[str, str] = {}  # normalized key -> original tag
if _STYLES_FILE.exists():
    try:
        tags = json_mod.loads(_STYLES_FILE.read_text())
        _VALID_MUSIC_STYLES = set(tags)
        # Build normalized lookup: lowercase + no hyphen/no space -> original tag
        for tag in tags:
            key = tag.lower().replace("-", "").replace(" ", "")
            _NORMALIZED_STYLES[key] = tag
    except Exception:
        pass

# Pricing per generation in credits. A single music task typically produces 2
# tracks; values below are TOTAL credits for the whole question.
_PRICING = {
    "Art Music 3.5":      16,
    "Art Music 4":        20,
    "Art Music 4.5":      24,
    "Art Music 4.5 Plus": 28,
    "Art Music 5":        32,
    "Art Music 5.5":      20,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_model_id_by_name(model_name: str) -> Optional[str]:
    """Map a friendly model name to the API gpt_type id. Returns None on miss."""
    if not model_name:
        return None
    if model_name in MODEL_MAP:
        return MODEL_MAP[model_name]

    name = model_name.lower().replace(" ", "").replace("_", "")
    aliases = {
        "artmusic3.5":      "Art Music 3.5",
        "artmusic35":       "Art Music 3.5",
        "suno3.5":          "Art Music 3.5",
        "suno-3.5":         "Art Music 3.5",
        "artmusic4":        "Art Music 4",
        "suno4":            "Art Music 4",
        "suno-4":           "Art Music 4",
        "artmusic4.5":      "Art Music 4.5",
        "artmusic45":       "Art Music 4.5",
        "suno4.5":          "Art Music 4.5",
        "suno-4.5":         "Art Music 4.5",
        "artmusic4.5plus":  "Art Music 4.5 Plus",
        "artmusic45plus":   "Art Music 4.5 Plus",
        "suno4.5plus":      "Art Music 4.5 Plus",
        "suno-4.5-plus":    "Art Music 4.5 Plus",
        "suno4.5-plus":     "Art Music 4.5 Plus",
        "artmusic5":        "Art Music 5",
        "suno5":            "Art Music 5",
        "suno-5":           "Art Music 5",
        "artmusic5.5":      "Art Music 5.5",
        "suno5.5":          "Art Music 5.5",
    }
    target = aliases.get(name)
    return MODEL_MAP.get(target) if target else None

def estimate_cost(model: str, count: int = 1) -> Optional[float]:
    """Return estimated total cost in credits, or None if model is unknown."""
    if model not in _PRICING:
        return None
    unit = _PRICING[model]
    return round(unit * max(count, 1), 2)

def _normalize_bool(value) -> bool:
    """Best-effort convert string/bool/int to a clean bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y", "on")
    return False

# Chinese to English style tag aliases (for user-facing Chinese labels)
_STYLE_ALIASES: dict[str, str] = {
    "流行": "Pop",
    "说唱": "Rap",
    "贝斯": "Bass",
    "吉他": "Guitar",
    "摇滚": "Rock",
    "钢琴": "Piano",
    "鼓乐": "Drums",
    "情绪摇滚": "Emo Rock",
    "嘻哈": "Hip Hop",
    "浪漫": "Romantic",
    "悲伤": "Sad",
}

def _translate_style(tag: str) -> str:
    """Translate a style tag to its English / canonical equivalent.

    1. Exact match in _STYLE_ALIASES (Chinese → English).
    2. Fuzzy match via _NORMALIZED_STYLES (case/hyphen/space agnostic).
    3. Return as-is if no match (will fail strict validation downstream).
    """
    if tag in _STYLE_ALIASES:
        return _STYLE_ALIASES[tag]
    normalized = tag.lower().replace("-", "").replace(" ", "")
    if normalized in _NORMALIZED_STYLES:
        return _NORMALIZED_STYLES[normalized]
    return tag

def _normalize_music_style(value) -> Optional[str]:
    """Accept list, comma-separated string, or None. Returns comma-joined string."""
    if value is None or value == "":
        return None
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
    else:
        items = [v.strip() for v in str(value).split(",") if v.strip()]
    return ",".join(items) if items else None

def _normalize_singing_voice(value) -> str:
    """Default to 'random' if missing or invalid."""
    if not value:
        return "random"
    v = str(value).strip().lower()
    return v if v in VALID_SINGING_VOICES else "random"

def validate_args(args, parser) -> None:
    """Cross-field validation: enforce the contract described in the spec."""
    if not args.model:
        args.model = DEFAULT_MODEL

    if args.model not in MODEL_MAP:
        parser.error(
            f"--model '{args.model}' is not supported. "
            f"Available: {', '.join(MODEL_MAP.keys())}"
        )

    if not args.prompt or not args.prompt.strip():
        parser.error("--prompt is required")

    is_pure = _normalize_bool(args.is_pure_music)

    music_style = _normalize_music_style(args.music_style)
    if music_style:
        translated = ",".join(_translate_style(t) for t in music_style.split(","))
        invalid = [t for t in translated.split(",") if t not in _VALID_MUSIC_STYLES]
        if invalid:
            parser.error(f"Invalid music_style tag(s): {', '.join(invalid)}. Valid tags: {', '.join(sorted(_VALID_MUSIC_STYLES))}")

    if is_pure:
        # Pure music: action MUST be "custom"; no singing_voice; no lyrics.
        args.action = "custom"
        args.singing_voice = None
        args.lyrics = None
    else:
        # Vocal: action MUST be ""; singing_voice required; lyrics optional.
        args.action = ""
        if not args.singing_voice:
            args.singing_voice = "random"
        else:
            sv = str(args.singing_voice).strip().lower()
            if sv not in VALID_SINGING_VOICES:
                parser.error(
                    f"--singing-voice must be one of {VALID_SINGING_VOICES} "
                    f"(got '{args.singing_voice}')"
                )

def build_body(args) -> dict:
    """Build the request body for /web/music/create."""
    is_pure = _normalize_bool(args.is_pure_music)

    body: dict[str, Any] = {
        "gpt_type":     get_model_id_by_name(args.model),
        "prompt":       args.prompt.strip(),
        "is_pure_music": is_pure,
        "title":        (args.title or "").strip(),
        "action":       "custom" if is_pure else "",
    }

    music_style = _normalize_music_style(args.music_style)
    if music_style:
        body["music_style"] = ",".join(_translate_style(t) for t in music_style.split(","))

    if not is_pure:
        body["singing_voice"] = _normalize_singing_voice(args.singing_voice)
        if args.lyrics and args.lyrics.strip():
            body["lyrics"] = args.lyrics

    return body

# ---------------------------------------------------------------------------
# Submit / poll
# ---------------------------------------------------------------------------

def do_submit(client: ChatArtClient, body: dict, quiet: bool) -> str:
    """POST submit task, return question_id (printed as 'taskId' for consistency)."""
    if not quiet:
        print(f"Submitting music task (gpt_type={body.get('gpt_type')})...", file=sys.stderr)
    result = client.post(ENDPOINTS["submit"], json=body)
    # Server returns the question_id; some wrappers wrap in 'data'.
    question_id = result.get("question_id") or (result.get("data") or {}).get("question_id")
    if not question_id:
        raise ChatArtError("200", f"No question_id in submit response: {result}")
    if not quiet:
        print(f"Task submitted. question_id: {question_id}", file=sys.stderr)
    return str(question_id)

def do_poll(client: ChatArtClient, question_id: str,
            timeout: float, interval: float, quiet: bool) -> dict:
    """Poll until status is 1 (completed) / 2 (failed) or timeout is exceeded."""
    if not quiet:
        print(
            f"Polling task {question_id} (timeout={timeout}s, interval={interval}s)...",
            file=sys.stderr,
        )

    start = time.time()
    path = ENDPOINTS["query"]
    path += f"?question_ids[]={question_id}"
    # print(f"get path={path}")
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(
                f"Task {question_id} did not complete within {timeout}s"
            )
        

        # Server accepts either ?question_ids[]=xxx or json body; we use json body
        # to stay consistent with the rest of the client.
        resp = client.get(path, json={"question_id": question_id})

        # The endpoint returns data as a list of task dicts; take the first.
        data_list = resp if isinstance(resp, list) else (resp.get("list") or [resp])
        first = data_list[0] if data_list else {}

        # Status: 0 working, 1 done, 2 failed.
        status = first.get("status")
        if not quiet:
            label = {0: "working", 1: "completed", 2: "failed"}.get(status, "unknown")
            print(f"  [{elapsed:.0f}s] status: {label}", file=sys.stderr)

        if status == 1:
            return first
        if status == 2:
            err = first.get("error_message") or first.get("errorMsg") or "Task failed"
            raise ChatArtError("TASK_FAILED", err)

        time.sleep(interval)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _shorten_url(client: ChatArtClient, url: str) -> str:
    """Best-effort URL shortener; fall back to original on any failure."""
    try:
        return client.shorten_url(url)
    except Exception:
        return url

def print_result(result: dict, args, client: ChatArtClient) -> None:
    """Print final result: music URLs by default, full JSON with --json."""
    if args.json:
        print(json_mod.dumps(result, indent=2, ensure_ascii=False))
        return

    cost = result.get("cost_credit", "N/A")
    status = result.get("status", 0)
    print(f"status: {status}  cost: {cost} credits")

    if status != 1:
        err = result.get("error_message") or result.get("errorMsg") or "Task failed"
        print(f"  failed: {err}")
        return

    items = result.get("list") or []
    if not items:
        print("  No music files returned.")
        return

    for i, item in enumerate(items, 1):
        url = item.get("url", "")
        cover = item.get("cover_url", "")
        title = item.get("title", "")
        lyrics = item.get("lyrics", "")
        if not url:
            print(f"  [{i}] no url (status={item.get('status')})")
            continue
        # Optionally download the file
        if args.output_dir:
            try:
                os.makedirs(args.output_dir, exist_ok=True)
                from shared.download import download_file
                ext = "mp3"
                ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                out_path = os.path.join(args.output_dir, f"music_{ts}_{i}.{ext}")
                download_file(url, out_path, args.quiet)
                if cover:
                    cover_ext = "png"
                    cover_path = os.path.join(args.output_dir, f"music_{ts}_{i}_cover.{cover_ext}")
                    download_file(cover, cover_path, args.quiet)
            except Exception as e:
                if not args.quiet:
                    print(f"  download warning: {e}", file=sys.stderr)
        short_url = _shorten_url(client, url)
        print(f"  [{i}] music_url: {short_url}")
        if cover:
            print(f"      cover:     {cover}")
        if title:
            print(f"      title:     {title}")

# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_run(args, parser):
    """Submit task then poll until done — full flow (default)."""
    validate_args(args, parser)
    client = ChatArtClient()
    body = build_body(args)
    # 打印body
    print(f"body:{body}")
    if not args.quiet:
        print(f"Request body: {json_mod.dumps(body, ensure_ascii=False)}", file=sys.stderr)
    question_id = do_submit(client, body, args.quiet)
    result = do_poll(client, question_id, args.timeout, args.interval, args.quiet)
    print_result(result, args, client)

def cmd_submit(args, parser):
    """Submit task only — print question_id and exit immediately."""
    validate_args(args, parser)
    client = ChatArtClient()
    body = build_body(args)
    if not args.quiet:
        print(f"Request body: {json_mod.dumps(body, ensure_ascii=False)}", file=sys.stderr)
    question_id = do_submit(client, body, args.quiet)
    print(question_id)

def cmd_query(args, parser):
    """Poll an existing question_id until done or timeout."""
    if not args.task_id:
        parser.error("--task-id is required for query")
    client = ChatArtClient()
    try:
        result = do_poll(
            client, args.task_id,
            args.timeout, args.interval, args.quiet,
        )
        print_result(result, args, client)
    except TimeoutError as e:
        if not args.quiet:
            print(f"Timeout reached: {e}", file=sys.stderr)
            print("Fetching last known status...", file=sys.stderr)
        last = client.get(ENDPOINTS["query"], json={"question_id": args.task_id})
        if args.json:
            print(json_mod.dumps(last, indent=2, ensure_ascii=False))
        else:
            print(f"status: pending  question_id: {args.task_id}", file=sys.stderr)
        sys.exit(2)

def cmd_list_models(args, parser):
    """Print supported models and pricing."""
    if args.json:
        print(json_mod.dumps(
            {m: {"gpt_type": mid, "pricing": _PRICING.get(m, 0)}
             for m, mid in MODEL_MAP.items()},
            indent=2, ensure_ascii=False,
        ))
        return

    print("\nMusic Generation — Supported Models\n")
    print(f"{'Display Name':<22} {'gpt_type':<18} {'Credits (per task)'}")
    print("-" * 62)
    for name, mid in MODEL_MAP.items():
        credits = _PRICING.get(name, "N/A")
        print(f"{name:<22} {mid:<18} {credits}")
    print("\nNote: Each task produces 2 tracks. Pricing shown is per task.")

def cmd_estimate_cost(args, parser):
    """Print estimated cost for a model."""
    if not args.model:
        args.model = DEFAULT_MODEL
    if args.model not in MODEL_MAP:
        parser.error(
            f"--model '{args.model}' is not supported. "
            f"Available: {', '.join(MODEL_MAP.keys())}"
        )

    cost = estimate_cost(args.model)
    if cost is None:
        print(f"Cannot estimate cost for model '{args.model}'.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json_mod.dumps({
            "model": args.model,
            "gpt_type": get_model_id_by_name(args.model),
            "cost": cost,
        }))
    else:
        print(f"model: {args.model}  gpt_type: {get_model_id_by_name(args.model)}")
        print(f"estimated cost: {cost} credits")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ChatArt Music Generation — text-to-music and pure instrumental.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
AGENT WORKFLOW RULES:
  1. ALWAYS start with `run` — it submits and polls automatically.
  2. Only use `query` if `run` timed out and you have a question_id to resume.
  3. `query` polls continuously (not once) until done or --timeout.
  4. NEVER hand a pending question_id back to the user — always poll to completion.

Music styles (--music-style, comma-separated, optional):
  See the list in `references/music_style.md` or run the API docs.

Examples:
  # Pure music (instrumental)
  python music_gen.py run --model "Art Music 4.5" \\
      --prompt "Soul ballad, slow groove, rhodes and clavinet" \\
      --is-pure-music true --music-style "Pop,Piano,Sad" \\
      --title "Sweet Confessions"

  # Music with vocals
  python music_gen.py run --model "Art Music 4.5 Plus" \\
      --prompt "Emotional Depth Plane, slow lovelorn female singer, soft R&B" \\
      --is-pure-music false --singing-voice female \\
      --lyrics "[Verse 1]\\n..." --title "I need a break"

  # Submit only (for parallel batch jobs)
  python music_gen.py submit --model "Art Music 4" \\
      --prompt "..." --is-pure-music true --title "Demo"

  # Query / resume a pending task
  python music_gen.py query --task-id 577

  # List models
  python music_gen.py list-models

  # Estimate cost
  python music_gen.py estimate-cost --model "Art Music 4.5"
""",
    )

    sub = parser.add_subparsers(dest="subcommand")
    sub.required = True

    # ---- run (default full flow) ----
    p_run = sub.add_parser("run", help="[DEFAULT] Submit task and poll until done")
    add_music_args(p_run)
    add_poll_args(p_run)
    add_output_args(p_run)

    # ---- submit only ----
    p_submit = sub.add_parser("submit", help="Submit task only, print question_id and exit")
    add_music_args(p_submit)
    add_output_args(p_submit)

    # ---- query ----
    p_query = sub.add_parser("query", help="Poll existing question_id until done or timeout")
    p_query.add_argument("--task-id", required=True,
                         help="question_id returned by 'submit' or a previous 'run'")
    add_poll_args(p_query)
    add_output_args(p_query)

    # ---- list-models ----
    p_list = sub.add_parser("list-models", help="Show supported music models and pricing")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # ---- estimate-cost ----
    p_cost = sub.add_parser("estimate-cost", help="Estimate credit cost before running a task")
    p_cost.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model display name (default: {DEFAULT_MODEL})")
    p_cost.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.subcommand == "run":
        cmd_run(args, p_run)
    elif args.subcommand == "submit":
        cmd_submit(args, p_submit)
    elif args.subcommand == "query":
        cmd_query(args, p_query)
    elif args.subcommand == "list-models":
        cmd_list_models(args, p_list)
    elif args.subcommand == "estimate-cost":
        cmd_estimate_cost(args, p_cost)


def add_music_args(p):
    """Add arguments specific to music generation."""
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Model display name (default: {DEFAULT_MODEL}). "
                        f"Choices: {', '.join(MODEL_MAP.keys())}")
    p.add_argument("--prompt", default=None,
                   help="Music style / scene description (required).")
    p.add_argument("--is-pure-music", default="false",
                   help='false = instrumental (no lyrics/voice); false = with singing. '
                        'Default: "false"')
    p.add_argument("--music-style", default=None,
                   help='Comma-separated style tags, e.g. "Pop,Piano,Sad". Optional.')
    p.add_argument("--singing-voice", default=None,
                   help='Voice type when is-pure-music=false: random | male | female '
                        '(default: random). Ignored for pure music.')
    p.add_argument("--title", default=None,
                   help="Music title (optional).")
    p.add_argument("--lyrics", default=None,
                   help="Lyrics text (only valid when is-pure-music=false). "
                        "Use \\n for line breaks.")

def add_poll_args(p):
    """Polling control arguments."""
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help=f"Max polling time in seconds (default: {DEFAULT_TIMEOUT})")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                   help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL})")

def add_output_args(p):
    """Output / download arguments."""
    p.add_argument("--output-dir", default=None,
                   help="Download result audio (and cover) files to this directory")
    p.add_argument("--json", action="store_true",
                   help="Output full JSON response")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="Suppress status messages on stderr")

if __name__ == "__main__":
    main()
