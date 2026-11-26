# What counts as what

## The four types

| Type | What it is | How to recognise it |
|---|---|---|
| Workflow (工作流) | A way of making, as ordered steps, with the files that implement it | The conversation contains a method that produced a finished video: prompts, model calls, scripts or an edit project |
| Output (成片) | A finished video made with a workflow | The latest exported version of each distinct video the user kept. Not previews, test renders or earlier versions |
| Asset (素材) | A reusable file | Images, video clips, audio that went into a finished video, or that the user named |
| Viral (爆款) | The reference the work imitates | A link to the video the work was modelled on, from any platform (TikTok, Instagram, YouTube, X, …). A link shown only for comparison, as an example of a problem, or whose ideas were tried and then dropped is not one |

## How to split

| Situation | Result |
|---|---|
| One way of making, one finished video | 1 workflow, 1 output |
| One way of making, several finished videos | 1 workflow, several outputs all pointing to it |
| Two different ways of making, each with its own video | 2 workflows, each with its own outputs |
| A workflow from the platform was used unchanged | No new workflow. Outputs point to it by `workflow_id` and `version` |
| A workflow pulled from the platform was changed here | Import it with its `origin` copied unchanged. The platform decides whether it becomes a new version (you are its author) or a new workflow |
| A way of making, no finished video yet | Workflow only |
| Only files | Assets only |
| Only links | Virals only |

Two ways of making are "the same" when the method and the toolchain match: the same scripts, the
same kinds of model calls, the same assembly. Different subject matter (a bathroom needs tiling, a
bedroom needs painting) does not make a different workflow; it makes different outputs.

If you are unsure how to split, pick the simpler split and say so in the checklist so the user can
correct it.

## Which videos count

A long conversation exports many files. Work it out per distinct video:

- Take the **latest** version the user did not reject. The user does not have to have said "approved".
- A video the user later asked to remove, drop or delete is left out. List it under "left out" in
  the checklist so they can ask for it back.
- A video made by a method that was later abandoned is still a finished video if the user kept it;
  it then needs its own workflow. If you cannot tell whether they kept it, leave it out and say so.
- If the same video exists as a compressed copy and an original, use the original.
- A finished video you cannot tie to any workflow cannot be an output. Offer it as an asset.

## Turning the conversation into steps

The steps describe the method once, for the workflow. They are not a log of this conversation.

- Walk the final method from start to finish and write one step per distinct action, in order.
- Things that happened only as one-off commands or by hand still belong, so that someone can
  repeat the result even though no file holds them. `fields.md` says which type each one is.
- Checks the user insisted on (for example "every shot must make physical sense") are steps too.
- What differed between the videos made with this workflow is not a step. It shows in the outputs.

## What to leave out

- Attempts that were abandoned, and files only they used.
- Temporary frames, caches, render intermediates, dependency folders (`node_modules`, virtual
  environments). The script skips the common ones; do not list them in `paths` either.
- `.env` files and any file whose purpose is to hold credentials.
- Files unrelated to this piece of work that happen to be in the directory.
- The finished video itself is not an asset; it is an output.

## Workflow paths

List the smallest set of files or folders that someone else needs to repeat the work, **and keep
it runnable**: files keep their relative paths in the package, so if a script calls another by a
relative path, both must be packed where they are. Prefer naming specific files over a whole
project folder. Drop a duplicate copy of a script only when nothing refers to that copy.

Files the method cannot run without (a character reference image every run needs, a template)
belong in `paths` even if you also list them as assets: someone who pulls the workflow gets the
package, not the assets.

If a packed file contains a personal file path or user name, you cannot edit it (the script never
changes originals). Say so in the checklist so the user can decide.

When the work has no document that explains the current method, write `guide` (see `fields.md`).
An old document that describes an abandoned method is left out, not used as the entry.

Some packed files inevitably contain leftovers from abandoned attempts (unused shots in a shot
list, an old template). Say which parts are current in the `description` of the step that uses the
file.

## Assets

Assets are for reuse, not for archiving the run.

- List the few files someone would need to make a variant, and the generated pieces worth keeping
  besides the final video (a generated background, a voice track). Typically under ten per video.
- A file used by several outputs is listed once and referenced from each output's `assets`.
- Give every asset a readable `name`.
- If you think more than about 100 MB of assets are worth keeping, ask the user before listing them.

## Groups

A group says what a set of assets is for. Prefer an existing group from `hub.py context`. Otherwise
name the group after the kind of video (「房间改造短片」), not after this one video.
