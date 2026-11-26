# Manifest format and field guide

The manifest follows the team's import data standard (schema_version 1). You write the fields
marked **you**. The script adds the rest (`client_version`, `tool`, file lists, hashes,
`secrets_removed`) and the platform computes everything else (author, version number, titles and
statistics of viral videos, covers, durations). Do not write those.

```json
{
  "schema_version": 1,
  "client": "claude-plugin",
  "project": "Kabo",
  "title": "叠字短片 · 首次导入",
  "workflows": [
    {
      "key": "overlay-text",
      "name": "叠字短片工作流",
      "description": "在一段夜景或街景视频上叠加一句仿写的文案，按原视频的方式断行和出现。",
      "change_note": "首次导入，来自 Claude 对话。",
      "related_virals": ["https://www.tiktok.com/@someone/video/123"],
      "inputs": {
        "materials": [
          { "kind": "视频", "count": "1", "requirement": "竖屏夜景或街景，9 秒以上" },
          { "kind": "文案", "count": "1", "requirement": "原视频的那句字幕，用于仿写" }
        ],
        "secrets": [ { "name": "VIDEO_MODEL_API_KEY", "purpose": "步骤 4 调用视频生成模型" } ],
        "environment": "需要 ffmpeg、Node 20"
      },
      "steps": [
        { "type": "人工操作", "name": "准备素材", "content": "选 1 段 9 秒以上的竖屏夜景或街景视频。准备原视频的那句文案。" },
        { "type": "prompt", "name": "仿写文案", "model": "Claude", "calls": 1,
          "description": "让模型按原视频文案的结构仿写。", "content": "下面是一条爆款短视频的字幕。请仿写 5 句同结构的句子……" },
        { "type": "模型生成", "name": "延长背景素材", "model": "视频生成模型", "model_id": "veo-3.1-generate-001",
          "calls": 1, "conditional": "背景素材不足 9 秒时", "content": "把输入视频延长到 9 秒，保持镜头运动方向和光线不变。" },
        { "type": "代码", "name": "叠加字幕", "files": ["scripts/overlay.py"],
          "content": "scripts/overlay.py · 72 行。读取文案和视频，白色无衬线字体居中，每行间隔 0.4 秒出现。" },
        { "type": "剪辑", "name": "合成与配乐", "files": ["remotion/Overlay.tsx"],
          "content": "remotion/Overlay.tsx · 96 行。合成字幕层与背景，音乐起点对齐第一行文案。" }
      ],
      "cost": {
        "total": 0.45, "basis": "估算",
        "by_model": [
          { "model": "Claude", "steps": [2], "calls": 1, "amount": 0.05 },
          { "model": "视频生成模型", "steps": [3], "calls": 1, "amount": 0.40 }
        ]
      },
      "entry": "SKILL.md",
      "paths": ["SKILL.md", "scripts/overlay.py", "remotion/Overlay.tsx"]
    }
  ],
  "outputs": [
    { "key": "out-1", "file": "out/final.mp4", "workflow": "overlay-text",
      "viral": "https://www.tiktok.com/@someone/video/123", "assets": ["night-city", "bgm"] }
  ],
  "assets": [
    { "key": "night-city", "file": "assets/night-city.mp4", "name": "示例夜景 01", "groups": ["叠字短片"] },
    { "key": "bgm", "file": "assets/bgm.mp3", "name": "原曲片段", "groups": ["叠字短片"] }
  ],
  "virals": [
    { "url": "https://www.tiktok.com/@someone/video/123" }
  ]
}
```

All four lists are optional but at least one item must exist. Paths are relative to the working
directory, which is the directory you run `hub.py pack` from. If you must run it from elsewhere,
add a top-level `"baseDir"` with the working directory's absolute path.

Every workflow, output and asset has a `key`: lowercase letters, digits and hyphens, unique in the
manifest. Items refer to each other by `key`. Things already on the platform are referred to by
their own identifiers: a viral by its link, a workflow by `{"workflow_id": "…", "version": "v3"}`.

## Batch

| Field | Level | Who | Notes |
|---|---|---|---|
| `schema_version` | must | you | Always `1` |
| `client` | must | you | `claude-plugin` in Claude, `codex-plugin` in Codex |
| `project` | must | ask the user | From the list `hub.py context` returned. The one thing you ask. Skip the question only if the user said in this conversation which Project to import into; a product or brand name appearing in the content does not count |
| `accounts` | optional | — | Leave out unless the user named accounts from the pool |
| `title` | optional | you | Names the import job. Leave out if nothing obvious |

## Workflow

| Field | Level | Notes |
|---|---|---|
| `key` | must | |
| `name` | should | Says what it makes, in the user's language, at most 30 characters |
| `description` | should | One or two sentences: what goes in, what comes out |
| `change_note` | should | First import: where it came from ("首次导入，来自 Claude 对话"). Changed version of a platform workflow: what changed |
| `related_virals` | optional | Links this workflow was built to remake. Leave out when the batch has one viral: the platform links every workflow, output and asset in a batch to the batch's virals |
| `inputs.materials[]` | should | What someone must prepare before running: `kind` (`图片` / `视频` / `音乐` / `文案` / `其他`), `count`, `requirement` |
| `inputs.secrets[]` | when any | `name` and `purpose` only. The script adds the names it finds; you add the ones it cannot see (a key file read from disk, a login) and write each `purpose`. Never a value, never a personal file path |
| `inputs.environment` | optional | Tools and versions needed |
| `steps[]` | must, at least one | See below |
| `cost` | should | See below. Leave the whole object out if you cannot work it out |
| `entry` | should | The file to read first, usually `SKILL.md`. Must be among the packed files. If the work has no such document, leave it out and write `guide` |
| `guide` | when there is no entry document | A short text on how to use the package: what to run in what order, which files are current and which parts are leftovers, what is not in any file. The script packs it as `GUIDE.md` and makes it the entry. Do not point `entry` at a script or at a document that describes an abandoned method |
| `paths` | must | Files and folders to pack. See `what-to-import.md` |
| `origin` | when it exists | If this workflow was pulled from the platform, its `manifest.json` has an `origin` object. Copy it unchanged. Never write one yourself |
| `notSecrets` | optional | `"file:line"` entries the user confirmed are not secrets. Only ever add one after the user agrees |
| `tool` | — | The script fills it from `client`. Write `"n8n"` only for an n8n workflow |

### Steps

An ordered list; order is the list order. This is the heart of the import: someone who was not in
the conversation should be able to repeat the work from it.

| Field | Level | Notes |
|---|---|---|
| `type` | must | One of the five below |
| `name` | must | Verb phrase, at most 12 characters: 「仿写文案」 |
| `description` | should | One sentence on what this step does |
| `content` | see table | The prompt in full, or a summary of the code |
| `model` | see table | A name a non-engineer understands: `Claude`, `视频生成模型`. When the exact model is unknown, the generic kind is enough (`语音合成模型`) |
| `model_id` | optional | The exact identifier, from the scripts when there is one. Leave out if unknown |
| `calls` | should, when there is a model | Calls in one typical run without retries, counting only what the final method uses |
| `files` | optional | Packed files this step corresponds to |
| `conditional` | optional | When the step only sometimes runs |

| `type` | What it is | How to recognise it | `content` | `model` |
|---|---|---|---|---|
| `人工操作` | Something the person does | Material the user prepared; a choice the user made; a check done by eye; a decision about what to redo | must: what to do | no |
| `prompt` | A prompt to a model whose answer is text | Produces copy, structure, a script, or a judgement (a model that reviews a clip against a checklist is this type, even if the prompt lives in a script) | must: the prompt in full | must |
| `模型生成` | A call to an image, video or audio model | Generates or extends pictures, voice, music | must: the prompt or parameters sent | must |
| `代码` | Running a script | A script written and run in the conversation | should: file name, line count, one sentence on what it does. Not the code | no |
| `剪辑` | Assembling the video | Remotion, ffmpeg: compositing, music, captions | should: same as code | no |

Writing the steps:

- Only the way that finally worked. For a prompt that was revised, the last version.
- A workflow is reusable. In prompts, replace what changes per video (this video's subtitle, this
  room's description) with a bracketed note such as 「（这里放原视频的字幕）」.
- When a video needs many near-identical prompts (one per shot), write the shared rules and one
  representative prompt in `content`, say how the rest vary, and point to the packed file that
  holds them in `files`.
- Calls to the same model for the same purpose in a row are one step; `calls` is the total.
- Split by action, not by file. One script that first makes images and then videos is two steps,
  and both may name the same file.
- A one-off command that is not in any file is typed by what it does: `剪辑` if it assembles or
  mixes, otherwise `代码`. Put the command itself in `content`, since no file holds it.
- Put setup that is not a step (install this, log in there) in `inputs.environment`, and
  credentials in `inputs.secrets`.

### Cost

What one run costs someone else, in US dollars.

| Field | Level | Notes |
|---|---|---|
| `cost.total` | should | Two decimals |
| `cost.basis` | must, if `cost` is given | `实测` (from this conversation's actual usage) or `估算` (public unit price × calls) |
| `cost.by_model[]` | should | `model` (same as in the steps), `steps` (positions, starting at 1), `calls`, `amount` |

If the conversation only has a remembered or rough figure, leave `cost` out. Do not go and look
up prices to fill it.

## Output (成片)

| Field | Level | Notes |
|---|---|---|
| `key` | must | |
| `file` | must | The final video. mp4, mov, webm or m4v |
| `workflow` | must | The `key` of a workflow in this manifest, or `{"workflow_id", "version"}` for one on the platform |
| `viral` | optional | The link it remakes. Fill it when the conversation shows one; do not ask. Then the platform names it 「第 N 版」 |
| `name` | should | What this video is, enough to tell it from the others (「书房 · 暖灰原木」). Always give it when several outputs share one `viral`; otherwise they are all just 「第 N 版」 |
| `assets` | should | `key`s of assets in this manifest that actually went into this video |
| `publish_links` | optional | Only if the conversation shows it was already published. One per platform |

## Asset (素材)

| Field | Level | Notes |
|---|---|---|
| `key` | must | |
| `file` | must | Image, video or audio |
| `name` | should | Defaults to the file name. Give a readable name when the file name is a hash, a number or a code like `P0.png` |
| `groups` | optional | Pick from the groups `hub.py context` returned; otherwise a new name. If the user said what the material is for, use that |

## Viral (爆款)

Only the link. The platform fetches the title, author, cover, statistics and the video.

| Field | Level | Notes |
|---|---|---|
| `url` | must | The link of the video the work was modelled on. Any platform (TikTok, Instagram, YouTube, X, …). The platform reads titles and statistics only for the platforms it can fetch; for others it keeps the link |
| `method` | optional | Only if the **original author** published how they made it. Never your own guess |
