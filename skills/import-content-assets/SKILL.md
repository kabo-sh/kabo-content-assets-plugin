---
name: import-content-assets
description: "Import what this conversation produced into the internal content assets platform (内容资产管理中台) as drafts: the workflow (steps, prompts, files), the finished videos made with it, the materials, and the viral reference links. Use only when the user explicitly mentions this plugin or asks to import, save or upload this work to the content assets platform / 内容中台 / 中台 (e.g. 「导入中台」「存到内容中台」「把这次做的传上去」). Never start on your own."
compatibility: "Requires Python 3.9+, read access to the working directory, and network access from scripts to the platform and to the upload links it returns. Needs a content assets import token that the user stores themselves."
metadata:
  version: "0.2.2"
---

# Import content assets

You turn the work done in this conversation into draft records on the content assets platform,
following the team's import data standard (schema_version 1). Nothing is published: every item
lands as a draft that only the user sees, and they publish it on the web page.

Talk to the user in their language (usually Chinese). Keep every message short.

`hub.py` below means `python3 "<this skill's folder>/scripts/hub.py"`.

## Rules that never bend

1. **Ask before reading.** Your first message asks whether you may read this conversation and the
   working directory to prepare the import. Read nothing for this purpose until they say yes.
2. **One required question.** The only thing you must ask the user for is the Project. Everything
   else you fill in yourself; do not turn the import into a questionnaire.
3. **Confirm before upload.** Show the checklist (step 5) and wait for a clear yes. No yes, no upload.
4. **No secrets.** Never put a key, token or password value in the manifest, the checklist or your
   messages. The script strips them from workflow files; you only ever name them.
5. **Never touch the token.** Do not ask the user to paste the import token into the chat, do not
   read the token file, do not print environment variables. If the script says the token is missing,
   relay its instruction and stop.
6. **Only the final way.** Record how the delivered result was actually made. Leave out attempts
   that were abandoned, prompts that were replaced, and failed scripts.
7. **No transcript.** Summarise into steps. Do not copy the conversation into any field.
8. **Do not invent.** If neither the conversation nor the files show a model, a call count or a
   price, leave it out. A missing cost is correct; a guessed one is not.
9. **Stay inside this piece of work.** In a large working directory, look only at the paths this
   conversation created or used. Do not survey the rest.

## Steps

### 1. Ask permission

Say what you will read (this conversation, files this conversation created or used in the working
directory) and that everything becomes a private draft. Wait for yes.

### 2. Get platform context

Run `hub.py context`. It returns the Projects, the account pool, the existing material groups and
the workflows already on the platform (`workflow_id`, `name`, versions). If it reports a missing or
rejected token, tell the user what it said and stop here.

### 3. Work out what there is to import

Read `references/what-to-import.md` and `references/fields.md`, then decide:

- **Workflows (工作流)**: the way of making, as ordered steps, plus the files that implement it.
  This is where the method lives.
- **Outputs (成片)**: each finished video made with a workflow. If it remakes a viral video, it is
  that video's 复刻.
- **Assets (素材)**: reusable files that went into the videos.
- **Virals (爆款)**: links of the videos the work was modelled on, from any platform. Everything imported in one batch is linked to these virals on the platform: the workflows, the outputs (as 复刻) and the materials, so list the viral even when it is on X or another site.

Then ask the single question: which Project. Offer the list from step 2. If the user already named
the project in this conversation, use it and say so instead of asking.

### 4. Write the manifest and pack

Create a folder `.content-assets-import/` in the working directory. Write
`.content-assets-import/manifest.json` (format in `references/fields.md`), then run this **from the
working directory** (paths in the manifest resolve against the directory you run it in):

```
hub.py pack --manifest .content-assets-import/manifest.json --out .content-assets-import/plan
```

The script checks what the platform will check, copies each workflow's files into a package with
secret values replaced, leaves `.env` files out, writes the package's `manifest.json` (your steps
plus the file list and hashes it computes), and prints a summary. If it reports an error, fix the
manifest and run it again. It never changes the user's original files.

**Check every removed secret.** The summary lists each one as `NAME（file:line）`. Open each of
those lines in the original file. Detection is by pattern and can be wrong in both directions:

- If a removal is not a secret (a constant, a URN, a variable name), the packed file is now broken.
  Show the user the line, and if they agree it is not a secret, add `"file:line"` to that
  workflow's `notSecrets` and pack again. Never add a line to `notSecrets` on your own judgement.
- If you know of a secret the summary does not list, do not pack that file as it is. Tell the user.

The summary's `需要核对` lists what the standard says a workflow should have and yours lacks
(description, input materials, cost …). Fill in what the conversation supports; leave the rest and
mention it in the checklist. Do not invent to make the list empty.

### 5. Show the checklist and wait

Show, in this order:

1. The Project.
2. How many of each type.
3. Each workflow: name, number of steps, whether it is new or comes from a workflow on the platform.
4. Each output: file name, which workflow, which viral it remakes or "未关联".
5. Each asset: name, group, size.
6. Each viral link.
7. **Secrets**: for each workflow, the name and file of every secret removed, the `.env` files left
   out, and the secrets someone must supply to run it (by name). If none were found, say none were
   found. Always say that automatic detection can miss things.
8. What you left out and why (temporary frames, caches, abandoned attempts). Name every distinct
   finished video you left out, so the user can ask for it back; earlier versions of a video you
   did include are summarised as a group, not listed one by one.
9. Total size.

Then ask two things in one message: whether to upload, and whether they have checked that no
secret remains in each workflow. The user may remove items, rename them or change the split; if so,
update the manifest, pack again and show the checklist again.

### 6. Upload

For every workflow the user confirmed, pass `--secrets-checked <key>`:

```
hub.py upload --plan .content-assets-import/plan --secrets-checked <key> [--secrets-checked <key2>]
```

A workflow without that confirmation is skipped, and so is any output that depends on it. The
script registers the batch, uploads each file straight to storage, and asks the platform for the
result.

### 7. Report

For each item: saved as draft with its link, already on the platform (viral links), or failed with
the reason given. Give the link to the import job. Remind the user once that drafts are private
until they publish them on the web page. If something failed, say what they can do (fix and say
"retry"). Retrying an unchanged batch is safe: its key comes from its content, so nothing is
created twice.

Delete `.content-assets-import/` only if the user asks.

## When there is nothing to import

If the conversation produced no finished video, no reusable way of making and no links, say so in
one sentence and stop. Do not import the conversation itself.

A workflow without a finished video is fine: import the workflow alone. A finished video that
cannot be tied to any workflow cannot be an output; offer to import it as an asset instead.
