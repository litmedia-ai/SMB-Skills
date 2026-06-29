---
name: chatart-music
description: Generate music (instrumental or with vocals) using Suno models via the ChatArt Pro API. Describe the style/scene, optionally pick a music genre tag, and get back 2 tracks with cover art and lyrics.
---

# ChatArt Music Skill

Generate AI music — pure instrumental or with vocals + lyrics — using ChatArt's Suno-backed music API. Just describe the style/scene, optionally pick genre tags, and get back 2 tracks with cover art.

> 🎵 **Always use the `scripts/` Python scripts. Do NOT call `curl` or the API directly.**

## Core Capabilities

- **Pure instrumental** (`is_pure_music=true`) — no vocals, no lyrics
- **Vocal tracks** (`is_pure_music=false`) — with singing voice (male/female/random) and custom lyrics
- **5 Suno-backed models** — Art Music 3.5 / 4 / 4.5 / 4.5 Plus / 5
- **320+ style tags** — pop, rock, jazz, R&B, classical, etc.
- **Each task returns 2 tracks** with audio URL, cover art, and lyrics (for vocal)

## Execution Rules

> **Always use the `scripts/` Python scripts. Never use `curl` or direct HTTP calls.**

## User Reply Rules (Highest Priority)

1. **Keep replies short** — give the result or next step
2. **Use plain language** — no API terms, terminal references, env vars
3. **Never mention terminal details** — no command output, logs, file paths
4. **Never ask the user to operate a browser popup** — send the auth link directly in chat
5. **Always send the direct login link** — extract `URL:` from `auth.py login` output and use the login template
6. **Wait for user confirmation after login** — ask user to reply "好了"/"done" before continuing
7. **Handle account switching properly** — use `auth.py accountswitch`
8. **Explain errors simply** — one sentence, ask if they want to retry
9. **Be result-oriented** — show the link/audio when done
10. **Always stand in the user's shoes** — they only see the chat window
11. **Don't ask the user to register separately** — the auth page includes registration
12. **Act directly, don't ask how** — when login is needed, just run it and send the link
13. **Tell the user the expected generation time**

## Estimated Generation Time

| Task Type | Model                     | Estimated Time |
|-----------|---------------------------|----------------|
| Music     | Art Music 3.5 / 4         | ~1–2 minutes   |
| Music     | Art Music 4.5 / 4.5 Plus  | ~2–3 minutes   |
| Music     | Art Music 5 / 5.5         | ~3–5 minutes   |

> Music typically generates **2 tracks** per task. The agent polls until both tracks are complete.

## Login Message Template

**Chinese:**

Output the following as **markdown** (no code fences):

> 安装完成，ChatArt Music Skill 已连接到你的智能助手。
>
> 复制下方链接到浏览器中登录，登录后将解锁以下能力：
>
> **<LOGIN_URL>**
>
> 🎵 **AI 音乐生成**
> - 文字生成纯音乐或带人声歌曲，2 首/任务，自动封面与歌词。
> - 音乐模型：Art Music 3.5 · Art Music 4 · Art Music 4.5 · Art Music 4.5 Plus · Art Music 5 · Art Music 5.5
>
> 登录完成后回我一句"好了"，我马上继续。

**English:**

> Installation complete. ChatArt Music Skill is now connected to your agent.
>
> Copy the link below into your browser to sign in. After signing in, the following capabilities will be unlocked.
>
> **<LOGIN_URL>**
>
> 🎵 **AI Music Generation**
> - Text-to-music, instrumental or with vocals — 2 tracks per task, auto cover and lyrics.
> - Models: Art Music 3.5 · Art Music 4 · Art Music 4.5 · Art Music 4.5 Plus · Art Music 5 · Art Music 5.5
>
> Once you've signed in, just reply "done" and I'll continue right away.

## Prerequisites

- **Python 3.8+**
- **Authenticated** — see `references/auth.md`
  - First install: `python {baseDir}/scripts/auth.py login`
  - Check status:   `python {baseDir}/scripts/auth.py status`
- Sufficient credits — see `references/user.md`
- Env vars `CHATARTPRO_UID` + `CHATARTPRO_API_KEY` are auto-set after login

```bash
pip install -r {baseDir}/scripts/requirements.txt
```

## Agent Workflow Rules

1. **Always start with `run`** — submit + auto-poll
2. **Never let the user check task status themselves** — the agent polls
3. **Use `query` only when `run` has timed out and a `task-id` exists**
4. **`query` keeps polling** — every `--interval` seconds until done or timeout
5. **`query` timeout? Increase `--timeout`**, do not resubmit

**Decision tree:**
```
→ New request?            Use run
→ run timed out?          Use query --task-id <id>
→ query timed out?        Use query --task-id <id> --timeout 1200
→ Task status = 2 (fail)? ❌ Do NOT auto-resubmit
                          → Return error, ask user if retry
                          → User agrees → back to step 1
```

**Task status:**

| Status | Meaning            |
|--------|--------------------|
| `0`    | working            |
| `1`    | completed          |
| `2`    | failed             |

## Mandatory Pre-Execution Protocol

> **Run these steps before every generation task. No exceptions.**

### Step 1: Estimate Cost

```bash
python {baseDir}/scripts/music_gen.py estimate-cost \
    --model "Art Music 4.5"
```

### Step 2: Validate Parameters

```bash
python {baseDir}/scripts/music_gen.py list-models
```

### Step 3: Confirm With User

Show the planned task, model, and cost, then ask for confirmation before running.

## Module List

| Module        | Script                          | Reference Doc         | Description |
|---------------|---------------------------------|-----------------------|-------------|
| Auth          | `scripts/auth.py`               | `auth.md`             | OAuth 2.0 device flow — login link, polling, credentials |
| Music Gen     | `scripts/music_gen.py`          | `music_gen.md`        | Text-to-music (Suno): pure instrumental or with vocals |
| User          | `scripts/user.py`               | `user.md`             | Credit balance and usage history |
| Shared Client | `scripts/shared/client.py`      | (internal)            | Authenticated HTTP client, task polling, URL shortening |
| Shared Upload | `scripts/shared/upload.py`      | (internal)            | Local file → OSS upload |

## Creative Guide

### Step 1 — Intent Analysis

| Dimension            | Ask yourself                              | Default                 |
|----------------------|-------------------------------------------|-------------------------|
| **Model**             | Which Art Music model to use?              | Art Music 5.5（default）|
| **Pure or vocal?**   | Instrumental or with singing + lyrics?     | Ask the user            |
| **Lyrics provided?** | Did the user provide lyrics?               | → is_pure_music=false（人声模式） |
| **Purpose**          | Background music? Social media? Personal? | Background music        |
| **Mood / vibe**      | Happy? Sad? Energetic? Calm?               | Ask the user            |
| **Genre**            | Pop, rock, jazz, classical, R&B, ...?     | Optional multi-select   |
| **Voice** (vocal)    | Male, female, random?                     | random                  |
| **Title**            | Should it have a name?                    | optional                |
| **Language**         | What language for lyrics?                 | Match user's language   |

**Available models**（列出给用户参考）:
- Art Music 3.5（16 credits）
- Art Music 4（20 credits）
- Art Music 4.5（24 credits）
- Art Music 4.5 Plus（28 credits）
- Art Music 5（32 credits）
- Art Music 5.5（默认，20 credits）

> 如果用户已明确指定模型 → 直接使用该模型，并在确认页中展示可选模型供后续更换。
> 如果用户未指定 → 默认 Art Music 5.5，可在确认页引导升级。

**风格标签（可多选，直接告诉我即可）：**
流行 | 说唱 | 贝斯 | 吉他 | 摇滚 | 钢琴 | 鼓乐 | 情绪摇滚 | 嘻哈 | 浪漫 | 悲伤

> 支持 320+ 风格标签，以上为常用推荐。如需其他风格（如 Lo-fi、Jazz、Classical 等），可直接描述或告诉智能体"我要看完整标签列表"。

**人声选项（人声模式时）：**
男声 / 女声 / 随机（默认随机）

### Step 2 — Tool Selection

```
User needs music?
│
├─ Pure instrumental, no vocals?
│  → music_gen --is-pure-music true
│
├─ With singing + lyrics?
│  → music_gen --is-pure-music false --singing-voice <random|male|female> --lyrics "..."
   (Note: if the user provides lyrics, automatically use vocal mode — no need to ask)
│
├─ Continue / resume a pending task?
│  → music_gen query --task-id <id>
│
├─ Check credit balance?
│  → user credit
│
├─ Review generation history?
│  → user logs
│
└─ Out of scope?
   → Tell the user to use the ChatArt Pro web UI
```

**Quick routing:**

| User says...                                        | Command |
|-----------------------------------------------------|---------|
| "Generate a chill lo-fi beat"                       | `music_gen.py run --is-pure-music true --music-style "Lofi,Hip Hop" --prompt "..."` |
| "Make a sad R&B song with lyrics"                   | `music_gen.py run --is-pure-music false --singing-voice female --lyrics "..."` |
| "Continue my music task"                            | `music_gen.py query --task-id <id>` |
| "How many credits do I have?"                       | `user.py credit` |
| "Show my recent music"                              | `user.py logs` |

## Pre-Execution Protocol (Detail)

1. **Estimate cost** — `estimate-cost`
2. **Validate params** — confirm model, style, voice
3. **Ask for missing key params**:
   - **music_gen**: pure vs vocal, prompt/style, voice, lyrics (vocal), title
4. **Show confirmation page**

### Confirmation Page Template

**Chinese — 人声歌曲（用户提供歌词时）：**

Output the following as **markdown** (no code fences), so the chat UI renders line breaks correctly:

> 🎵 **音乐生成确认**
>
> - **模式**：人声歌曲 ✓（根据你提供的歌词自动判断）
> - **模型**：Art Music 5.5（默认）✓
> - **可选模型**：Art Music 3.5 / Art Music 4 / Art Music 4.5 / Art Music 4.5 Plus / Art Music 5 / Art Music 5.5
> - **风格**：Pop
> - **人声**：随机（男声 / 女声 / 随机）
> - **标题**：Sweet Confessions
> - **预估消耗**：20 credits
>
> 请确认歌词无误，确认无误请回复"确认"，或告诉我需要修改的参数。
> 如需更换模型、风格或人声，请直接告诉我。

**Chinese — 纯音乐（无人声）：**

> 🎵 **音乐生成确认**
>
> - **模式**：纯音乐（无人声）✓
> - **模型**：Art Music 5.5（默认）✓
> - **可选模型**：Art Music 3.5 / Art Music 4 / Art Music 4.5 / Art Music 4.5 Plus / Art Music 5 / Art Music 5.5
> - **风格**：Pop
> - **标题**：Sweet Confessions
> - **预估消耗**：20 credits
>
> 如需更换模型或风格，请直接告诉我。
> 确认无误请回复"确认"，或告诉我需要修改的参数。

**English — Vocal track (lyrics provided):**

> 🎵 **Music Generation Confirmation**
>
> - **Mode**: Vocal ✓ (auto-detected from provided lyrics)
> - **Model**: Art Music 5.5 (default) ✓
> - **Available models**: Art Music 3.5 / Art Music 4 / Art Music 4.5 / Art Music 4.5 Plus / Art Music 5 / Art Music 5.5
> - **Style**: Pop
> - **Voice**: Random (Male / Female / Random)
> - **Title**: Sweet Confessions
> - **Estimated cost**: 20 credits
>
> Please confirm the lyrics are correct, then reply "confirm" to proceed.
> To change model, style, or voice, just let me know.

**English — Pure instrumental:**

> 🎵 **Music Generation Confirmation**
>
> - **Mode**: Pure instrumental ✓
> - **Model**: Art Music 5.5 (default) ✓
> - **Available models**: Art Music 3.5 / Art Music 4 / Art Music 4.5 / Art Music 4.5 Plus / Art Music 5 / Art Music 5.5
> - **Style**: Pop
> - **Title**: Sweet Confessions
> - **Estimated cost**: 20 credits
>
> Please reply "confirm" to proceed, or let me know if you'd like to change anything.

| Module      | Available Models                                       | Current Default |
|-------------|--------------------------------------------------------|-----------------|
| music_gen   | Art Music 3.5 / Art Music 4 / Art Music 4.5 / Art Music 4.5 Plus / Art Music 5 / Art Music 5.5 | Art Music 5.5 |

**User response handling:**

| User response                                | Agent action |
|----------------------------------------------|--------------|
| "确认" / "ok" / "是" / "confirm"             | Execute immediately |
| "换成 <model>" / "用 <model>"                  | Update model → re-estimate cost → re-show confirmation |
| "改成 <style>" / "加个 <style>"                | Update style → re-estimate → re-show confirmation |
| "换成 <voice>" / "人声改成 <voice>"            | Update voice → re-show confirmation |
| "跳过确认" / "直接生成"                         | Set auto-confirm flag; skip confirmation for subsequent tasks |
| Subsequent tasks                             | Show confirmation page (with params), omit "是否确认" prompt |

## Agent Behavior Protocol

### During Execution

1. **Pass local paths directly** — scripts auto-upload to OSS
2. **Parallelize independent steps** — multiple music tasks can run concurrently
3. **Maintain consistency across tracks** — use the same params if user wants variations of the same vibe

### After Execution

**Chinese — music result template:**

Output the following as **markdown** (no code fences):

> 🎵 **音乐已生成完成**
>
> 🔗 **曲目 1**：<MUSIC_URL_1>
>
> 🔗 **曲目 2**：<MUSIC_URL_2>
>
>
> - **标题**：<TITLE>
> - **模型**：<MODEL_NAME>
> - **模式**：<纯音乐 / 人声>
> - **消耗**：<COST> credits
>
> 不满意的话可以告诉我，我帮你调整后重新生成。

**English — music result template:**

> 🎵 **Music generation complete**
>
> 🔗 **Track 1**: <MUSIC_URL_1>
>
> 🔗 **Track 2**: <MUSIC_URL_2>
>
>
> - **Title**: <TITLE>
> - **Model**: <MODEL_NAME>
> - **Mode**: <pure / vocal>
> - **Cost**: <COST> credits
>
> If you'd like adjustments, just let me know and I'll regenerate.

**Result display rules:**
1. **Result link first** — always show music URLs at the top
2. **Show key metadata only** — title, model, mode, cost
3. **Offer iteration** — end with a prompt to ask for adjustments
4. **Multiple outputs** — number them, each with link and metadata
5. **Match user's language**

## Error Handling

> See `references/error_handling.md`

> **🚨 Critical: Don't auto-switch models on failure**
>
> When a task fails or times out:
> 1. **Do NOT auto-resubmit** — don't switch models and retry
> 2. **Return error to user** — explain in plain language
> 3. **Ask if they want to retry** — if yes, go back to pre-execution step 1
> 4. **Only the user decides** if they want to try a different model
>
> Only exception: `query` timeout (exit code 2) can use the same `question_id` to keep polling — that's not a resubmit.

## Capability Boundaries

| Capability                       | Status      | Script |
|----------------------------------|-------------|--------|
| Credit management                | available   | `scripts/user.py` |
| Pure instrumental music          | available   | `scripts/music_gen.py --is-pure-music true` |
| Vocal music with custom lyrics   | available   | `scripts/music_gen.py --is-pure-music false` |
| Music style tags (320+)          | available   | `music_style` arg in `music_gen.py` |
| Music generation history         | available   | `scripts/user.py logs` |
| Music editing (post-process)     | not available | suggest chatartpro.com web UI |
| Multi-track stem export          | not available | suggest chatartpro.com web UI |
| Music → video combo              | not available | suggest chatartpro.com web UI |

> **Never promise capabilities that don't exist as modules.**
