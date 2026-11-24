#!/usr/bin/env python3
"""Content assets import helper. Standard library only (Python 3.9+).

Implements the import data standard (导入数据标准.md, schema_version 1).

Subcommands:
  scan    <path>...            report secret-looking values (names and locations only)
  pack    --manifest M --out D validate the batch, stage files, strip secrets, build workflow packages
  context                      fetch projects, accounts, asset groups and workflows from the platform
  upload  --plan D [--dry-run] register the batch, upload the files, report the drafts

The token is read from $KABO_CONTENT_ASSETS_TOKEN or ~/.kabo/content-assets-token.
It is never printed, logged or written anywhere by this script.
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = 1
DEFAULT_BASE = "https://kabo.sh"
API = "/v1/content-assets-import"
TOKEN_FILE = Path.home() / ".kabo" / "content-assets-token"

CLIENTS = {"claude-plugin": "claude", "codex-plugin": "codex"}
TOOLS = ("claude", "codex", "n8n")
STEP_TYPES = ("人工操作", "prompt", "模型生成", "代码", "剪辑")
STEP_NEEDS_MODEL = ("prompt", "模型生成")
MATERIAL_KINDS = ("图片", "视频", "音乐", "文案", "其他")
COST_BASIS = ("实测", "估算")
MEDIA_EXT = {"mov", "mp4", "webm", "m4v", "wav", "mp3", "m4a", "png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXT = {"mov", "mp4", "webm", "m4v"}
LINK_HOST = re.compile(r"(^|\.)(tiktok\.com|instagram\.com|youtube\.com|youtu\.be)$", re.I)
KEY = re.compile(r"[a-z0-9-]{1,40}")

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build",
    ".cache", ".turbo", ".idea", ".vscode", ".content-assets-import",
}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
TEXT_LIMIT = 2 * 1024 * 1024  # larger files are treated as binary and copied as-is

PLACEHOLDER = "<REMOVED:{name}>"
GUIDE_NAME = "GUIDE.md"
ASSIGN = re.compile(
    r"""(?<![A-Za-z0-9_:./-])(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?)[A-Za-z0-9_]*)
        (?P<sep>["']?\s*[:=]\s*)
        (?P<q>["']?)(?P<value>[^\s"'#,;]{8,})(?P=q)""",
    re.I | re.X,
)
BARE = [
    ("OPENAI_STYLE_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS_ACCESS_KEY_ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("BEARER_TOKEN", re.compile(r"(?<=Bearer )[A-Za-z0-9._~+/-]{20,}=*")),
]
PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S
)
LOOKS_LIKE_REFERENCE = re.compile(r"^(\$\{?|process\.env|os\.environ|<|\{\{|%|None$|null$|undefined$)", re.I)


def fail(message):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    sys.exit(1)


def ext_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_env_file(path):
    name = path.name.lower()
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def video_link(value):
    try:
        url = urlparse(value)
    except ValueError:
        return False
    return (
        url.scheme in ("http", "https")
        and not url.username
        and not url.password
        and bool(LINK_HOST.search(url.hostname or ""))
        and len(url.path) > 1
    )


def read_text(path):
    try:
        if path.stat().st_size > TEXT_LIMIT:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def redact(text, keep=()):
    """Return (clean_text, [{name, line}]). Values are replaced, never reported.

    `keep` is a set of line numbers the user confirmed are not secrets; they are left as they are.
    """
    found = []

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    def assign(m):
        if LOOKS_LIKE_REFERENCE.match(m.group("value")) or line_of(m.start()) in keep:
            return m.group(0)
        found.append({"name": m.group("name"), "line": line_of(m.start())})
        return m.group("name") + m.group("sep") + m.group("q") + PLACEHOLDER.format(name=m.group("name")) + m.group("q")

    clean = ASSIGN.sub(assign, text)
    for name, pattern in BARE:
        def bare(m, name=name):
            if line_of(m.start()) in keep:
                return m.group(0)
            found.append({"name": name, "line": line_of(m.start())})
            return PLACEHOLDER.format(name=name)
        clean = pattern.sub(bare, clean)

    def key(m):
        if line_of(m.start()) in keep:
            return m.group(0)
        found.append({"name": "PRIVATE_KEY", "line": line_of(m.start())})
        return PLACEHOLDER.format(name="PRIVATE_KEY")

    clean = PRIVATE_KEY.sub(key, clean)
    return clean, found


def walk(root):
    root = Path(root)
    if root.is_file():
        yield root, Path(root.name)
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name in SKIP_FILES:
                continue
            path = Path(current) / name
            yield path, path.relative_to(root.parent if root.is_dir() else root)


def env_names(text):
    names = []
    for line in text.splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m:
            names.append(m.group(1))
    return names


def cmd_scan(args):
    report = []
    for target in args.paths:
        if not Path(target).exists():
            fail(f"路径不存在：{target}")
        for path, rel in walk(target):
            try:
                rel = path.resolve().relative_to(Path.cwd().resolve())
            except ValueError:
                rel = path
            if is_env_file(path):
                text = read_text(path) or ""
                report.append({"file": str(rel), "envFile": True, "names": env_names(text)})
                continue
            text = read_text(path)
            if text is None:
                continue
            _, found = redact(text)
            if found:
                report.append({"file": str(rel), "found": found})
    print(json.dumps({"ok": True, "files": report}, ensure_ascii=False, indent=2))


def plugin_version():
    here = Path(__file__).resolve()
    for parent in here.parents:
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("version", "0")
            except ValueError:
                break
    return "0"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def need_file(base, value, label, exts=None):
    path = (base / str(value)).resolve()
    if not value or not path.is_file() or not path.stat().st_size:
        fail(f"{label}不存在或是空文件：{value}")
    if exts and ext_of(path.name) not in exts:
        fail(f"{label}的类型不支持：{path.name}（支持 {', '.join(sorted(exts))}）")
    return path


def check_steps(name, steps, packed, warnings):
    if not isinstance(steps, list) or not steps:
        fail(f"工作流「{name}」至少要有一步")
    for n, step in enumerate(steps, 1):
        kind = step.get("type")
        if kind not in STEP_TYPES:
            fail(f"工作流「{name}」第 {n} 步的类型不对：{kind}（只能是 {' / '.join(STEP_TYPES)}）")
        if not (step.get("name") or "").strip():
            fail(f"工作流「{name}」第 {n} 步缺少步骤名")
        if len(step["name"].strip()) > 12:
            warnings.append(f"第 {n} 步的步骤名超过 12 个字")
        if kind in STEP_NEEDS_MODEL:
            if not (step.get("content") or "").strip() or not (step.get("model") or "").strip():
                fail(f"工作流「{name}」第 {n} 步（{kind}）缺少原文或模型")
            if "calls" not in step:
                warnings.append(f"第 {n} 步没有写调用次数，预估成本可能不准")
        elif kind == "人工操作" and not (step.get("content") or "").strip():
            fail(f"工作流「{name}」第 {n} 步（人工操作）要写清做什么")
        elif not (step.get("content") or "").strip():
            warnings.append(f"第 {n} 步（{kind}）没有写摘要")
        for ref in step.get("files", []):
            if ref not in packed:
                fail(f"工作流「{name}」第 {n} 步引用的文件不在包里：{ref}")


def check_cost(name, cost, steps):
    if not cost:
        return
    if cost.get("basis") not in COST_BASIS:
        fail(f"工作流「{name}」的预估成本要写明是 {' 或 '.join(COST_BASIS)}")
    for row in cost.get("by_model", []):
        if not row.get("model") or "calls" not in row or "amount" not in row:
            fail(f"工作流「{name}」的预估成本里，每个模型要有 model、calls、amount")
        for pos in row.get("steps", []):
            if not isinstance(pos, int) or not 1 <= pos <= len(steps):
                fail(f"工作流「{name}」的预估成本引用了不存在的步骤：{pos}")


def build_workflow(item, batch, base, out):
    """Stage the files with secrets stripped, write manifest.json per the standard, zip it."""
    key = item["key"]
    name = (item.get("name") or "").strip()
    label = name or key
    stage = out / "_stage" / key
    removed, env_skipped, warnings = [], [], []
    keep = {}
    for spot in item.get("notSecrets", []):
        target, _, line = str(spot).rpartition(":")
        if not target or not line.isdigit():
            fail(f"notSecrets 的写法是 文件路径:行号，收到的是：{spot}")
        keep.setdefault(target, set()).add(int(line))
    if not item.get("paths"):
        fail(f"工作流「{label}」缺少 paths")
    for source in item["paths"]:
        root = (base / source).resolve()
        if not root.exists():
            fail(f"工作流「{label}」里的路径不存在：{source}")
        for path, rel in walk(root):
            try:  # keep the layout the author sees, relative to the working directory
                rel = path.resolve().relative_to(base)
            except ValueError:
                pass
            if str(rel) == "manifest.json":
                continue  # the standard manifest is generated below
            if is_env_file(path):
                env_skipped.append({"file": str(rel), "names": env_names(read_text(path) or "")})
                continue
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            text = read_text(path)
            if text is None:
                shutil.copy2(path, target)
            else:
                clean, found = redact(text, keep.get(str(rel), ()))
                target.write_text(clean, encoding="utf-8")
                removed += [{"file": str(rel), **f} for f in found]
    guide = (item.get("guide") or "").strip()
    if guide:
        clean, found = redact(guide)
        if found:
            fail(f"工作流「{label}」的使用说明里有看起来像密钥的内容，请去掉")
        stage.mkdir(parents=True, exist_ok=True)
        (stage / GUIDE_NAME).write_text(clean + "\n", encoding="utf-8")
    packed = sorted(str(p.relative_to(stage)) for p in stage.rglob("*") if p.is_file()) if stage.exists() else []
    if not packed:
        fail(f"工作流「{label}」没有可打包的文件")

    tool = item.get("tool") or CLIENTS[batch["client"]]
    if tool not in TOOLS:
        fail(f"工作流「{label}」的工具类型只能是 {' / '.join(TOOLS)}")
    if len(name) > 30:
        fail(f"工作流名称最多 30 个字：{name}")
    steps = item.get("steps")
    check_steps(label, steps, set(packed), warnings)
    check_cost(label, item.get("cost"), steps)
    for link in item.get("related_virals", []):
        if not video_link(link):
            fail(f"工作流「{label}」关联的爆款链接不是 TikTok / Instagram / YouTube：{link}")

    inputs = dict(item.get("inputs") or {})
    for m in inputs.get("materials", []):
        if m.get("kind") not in MATERIAL_KINDS or not (m.get("requirement") or "").strip():
            fail(f"工作流「{label}」的输入素材要有类型（{' / '.join(MATERIAL_KINDS)}）和要求")
    secrets = {s["name"]: dict(s) for s in inputs.get("secrets", []) if s.get("name")}
    for found in removed:
        secrets.setdefault(found["name"], {"name": found["name"]})
    for skipped in env_skipped:
        for env in skipped["names"]:
            secrets.setdefault(env, {"name": env})
    for secret in secrets.values():
        if redact(str(secret.get("purpose", "")))[1]:
            fail(f"工作流「{label}」的密钥「{secret['name']}」的用途里像是写了值。这里只能写名称和用途")
    inputs["secrets"] = list(secrets.values())

    for field, text in (("name", "名称"), ("description", "描述"), ("change_note", "更新说明")):
        if not (item.get(field) or "").strip():
            warnings.append(f"没有{text}")
    if not inputs.get("materials"):
        warnings.append("没有写需要准备的素材")
    if not item.get("cost"):
        warnings.append("没有预估成本")
    entry = item.get("entry") or (GUIDE_NAME if guide else "")
    if entry and entry not in packed:
        fail(f"工作流「{label}」的入口文件不在包里：{entry}")
    if not entry:
        warnings.append("没有入口文件：别人拿到包不知道先看什么。可以写一份 guide")

    manifest = {
        "schema_version": SCHEMA,
        "name": name,
        "description": (item.get("description") or "").strip(),
        "tool": tool,
        "project": item.get("project") or batch["project"],
        "change_note": (item.get("change_note") or "").strip(),
        "related_virals": item.get("related_virals", []),
        "inputs": inputs,
        "steps": steps,
        "entry": entry,
        "secrets_removed": len(removed),
        "files": [{"path": p, "size": (stage / p).stat().st_size, "sha256": sha256_file(stage / p)} for p in packed],
    }
    if item.get("cost"):
        manifest["cost"] = item["cost"]
    if item.get("origin"):
        manifest["origin"] = item["origin"]
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = out / "files" / f"{key}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(stage))
    shutil.rmtree(out / "_stage", ignore_errors=True)
    entry_out = {k: v for k, v in manifest.items() if k != "files"}
    entry_out.update({"key": key, "file": str(archive.relative_to(out))})
    summary = {
        "类型": "工作流", "名称": label, "步骤数": len(steps), "文件数": len(packed), "入口文件": entry or "（没有）",
        "大小": archive.stat().st_size,
        "是新工作流还是新版本": "来自平台上的工作流，由平台判断是新版本还是复制" if item.get("origin") else "新工作流",
        "已剔除密钥": [f'{r["name"]}（{r["file"]}:{r["line"]}）' for r in removed],
        "未打包的环境文件": env_skipped,
        "需要使用者自己准备的密钥": [s["name"] for s in inputs["secrets"]],
        "需要核对": warnings,
    }
    return entry_out, summary


def cmd_pack(args):
    manifest_path = Path(args.manifest).resolve()
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"读不了清单文件：{error}")
    base = Path(m.get("baseDir") or os.getcwd()).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        if any(out.iterdir()) and not (out / "batch.json").is_file():
            fail(f"输出目录不是空的，也不是上一次的打包结果，为了不误删没有继续：{out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    if m.get("schema_version") != SCHEMA:
        fail(f"清单的 schema_version 必须是 {SCHEMA}")
    if m.get("client") not in CLIENTS:
        fail("client 必须是 claude-plugin 或 codex-plugin")
    project = (m.get("project") or "").strip()
    if not project:
        fail("缺少所属 Project。这是唯一必须问用户的一项")
    batch = {
        "schema_version": SCHEMA, "client": m["client"], "client_version": plugin_version(),
        "project": project, "accounts": m.get("accounts", []), "title": (m.get("title") or "").strip(),
        "workflows": [], "outputs": [], "assets": [], "virals": [],
    }
    summary, keys = [], {}

    def take_key(item, kind):
        key = item.get("key") or ""
        if not KEY.fullmatch(key) or key in keys:
            fail(f"每个{kind}需要一个在这一批里唯一的 key（小写字母、数字、连字符），有问题的是：{key or '（空）'}")
        keys[key] = kind
        return key

    for w in m.get("workflows", []):
        take_key(w, "工作流")
        entry, info = build_workflow(w, batch, base, out)
        batch["workflows"].append(entry)
        summary.append(info)

    for a in m.get("assets", []):
        key = take_key(a, "素材")
        path = need_file(base, a.get("file"), "素材", MEDIA_EXT)
        name = (a.get("name") or path.name).strip()
        batch["assets"].append({
            "key": key, "name": name, "groups": a.get("groups", []),
            "project": a.get("project") or project, "accounts": a.get("accounts", batch["accounts"]),
            "source": str(path), "size": path.stat().st_size,
        })
        summary.append({"类型": "素材", "名称": name, "素材组": a.get("groups", []) or "（未分组）",
                        "大小": path.stat().st_size})

    viral_urls = set()
    for v in m.get("virals", []):
        url = (v.get("url") or "").strip()
        if not video_link(url):
            fail(f"不是 TikTok / Instagram / YouTube 的链接：{url}")
        viral_urls.add(url)
        batch["virals"].append({
            "url": url, "project": v.get("project") or project,
            "accounts": v.get("accounts", batch["accounts"]), "method": (v.get("method") or "").strip(),
        })
        summary.append({"类型": "爆款链接", "链接": url})

    for o in m.get("outputs", []):
        key = take_key(o, "成片")
        path = need_file(base, o.get("file"), "成片文件", VIDEO_EXT)
        workflow = o.get("workflow")
        if isinstance(workflow, str):
            if keys.get(workflow) != "工作流":
                fail(f"成片 {key} 引用的工作流 {workflow} 不在这一批里")
            shown = next(w["name"] or w["key"] for w in batch["workflows"] if w["key"] == workflow)
        elif isinstance(workflow, dict) and workflow.get("workflow_id") and workflow.get("version"):
            shown = f'平台上的工作流 {workflow["workflow_id"]} {workflow["version"]}'
        else:
            fail(f"成片 {key} 必须指明用的是哪个工作流。对不上工作流的视频请改按素材导入")
        viral = (o.get("viral") or "").strip()
        if viral and not video_link(viral):
            fail(f"成片 {key} 关联的爆款链接不是 TikTok / Instagram / YouTube：{viral}")
        for ref in o.get("assets", []):
            if keys.get(ref) != "素材":
                fail(f"成片 {key} 引用的素材 {ref} 不在这一批里")
        for link in o.get("publish_links", []):
            if not video_link(link):
                fail(f"成片 {key} 的发布链接不是 TikTok / Instagram / YouTube：{link}")
        name = (o.get("name") or "").strip()
        notes = []
        if not viral and not name:
            notes.append("没有关联爆款，也没有名称")
        if not o.get("assets"):
            notes.append("没有列出用到的素材")
        batch["outputs"].append({
            "key": key, "name": name, "workflow": workflow, "viral": viral,
            "assets": o.get("assets", []), "publish_links": o.get("publish_links", []),
            "project": o.get("project") or project, "source": str(path), "size": path.stat().st_size,
        })
        summary.append({
            "类型": "成片", "文件": path.name, "名称": name or "（关联爆款后由平台命名为第 N 版）",
            "工作流": shown, "关联爆款": viral or "未关联", "用到的素材数": len(o.get("assets", [])),
            "大小": path.stat().st_size, "需要核对": notes,
        })

    if not (batch["workflows"] or batch["outputs"] or batch["assets"] or batch["virals"]):
        fail("清单里没有任何要导入的内容")
    (out / "batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(i.get("大小", 0) for i in summary)
    print(json.dumps({"ok": True, "plan": str(out), "project": project, "items": summary, "合计大小": total},
                     ensure_ascii=False, indent=2))


def token():
    value = os.environ.get("KABO_CONTENT_ASSETS_TOKEN", "").strip()
    if not value and TOKEN_FILE.is_file():
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not value:
        fail(f"没有找到导入令牌。请在内容中台页面生成后，自己保存到 {TOKEN_FILE}（权限 600），"
             "或设置环境变量 KABO_CONTENT_ASSETS_TOKEN。不要把令牌贴进对话")
    return value


def base_url():
    return os.environ.get("KABO_CONTENT_ASSETS_URL", DEFAULT_BASE).rstrip("/")


def allowed(url):
    return url.scheme == "https" or url.hostname in ("localhost", "127.0.0.1")


def send(method, target, headers, body=None, body_path=None):
    """One HTTP request. `target` is a full URL. Returns (status, parsed JSON or {message})."""
    url = urlparse(target)
    if not allowed(url):
        fail("只允许通过 https 连接")
    connection_type = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    conn = connection_type(url.hostname, url.port, timeout=900)
    path = url.path + ("?" + url.query if url.query else "")
    try:
        if body_path:
            headers = {**headers, "Content-Length": str(os.path.getsize(body_path))}
            with open(body_path, "rb") as source:
                conn.request(method, path, body=source, headers=headers)
                response = conn.getresponse()
                raw = response.read()
        else:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
    except OSError as error:
        return 0, {"message": f"连不上：{type(error).__name__}"}
    finally:
        conn.close()
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        data = {"message": raw.decode("utf-8", "replace")[:200]}
    return response.status, data if isinstance(data, dict) else {"data": data}


def api(method, path, payload=None):
    headers = {"Authorization": "Bearer " + token(), "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    return send(method, base_url() + path, headers, body=body)


def cmd_context(_args):
    status, data = api("GET", API + "/context")
    if status != 200:
        fail(f"读取平台信息失败（{status}）：{data.get('message', '')}")
    print(json.dumps({"ok": True, **data}, ensure_ascii=False, indent=2))


def cmd_upload(args):
    plan_dir = Path(args.plan).resolve()
    try:
        batch = json.loads((plan_dir / "batch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"读不了 batch.json，请先运行 pack：{error}")
    confirmed = set(args.secrets_checked or [])
    skipped, files, labels = [], {}, {}

    # A workflow goes up only after the user confirmed its secrets were checked.
    kept = []
    for w in batch["workflows"]:
        if w["key"] in confirmed:
            w["secrets_checked"] = True
            kept.append(w)
        else:
            skipped.append({"名称": w["name"] or w["key"], "结果": "跳过：用户还没有确认密钥已核对"})
    kept_keys = {w["key"] for w in kept}
    batch["workflows"] = kept
    outputs = []
    for o in batch["outputs"]:
        if isinstance(o["workflow"], str) and o["workflow"] not in kept_keys:
            skipped.append({"名称": o["name"] or o["key"], "结果": "跳过：它用的工作流这次没有导入"})
        else:
            outputs.append(o)
    batch["outputs"] = outputs

    def attach(item, path):
        path = Path(path)
        item["file"] = {"ref": item["key"], "name": path.name, "size": path.stat().st_size,
                        "sha256": sha256_file(path)}
        files[item["key"]] = path
        labels[item["key"]] = item.get("name") or item["key"]

    for w in batch["workflows"]:
        attach(w, plan_dir / w["file"])
    for item in batch["assets"] + batch["outputs"]:
        attach(item, item.pop("source"))
        item.pop("size", None)
    # Same content gives the same key, so a retry of an unchanged batch creates nothing twice.
    batch["idempotency_key"] = hashlib.sha256(
        json.dumps(batch, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]

    counts = {"工作流": len(batch["workflows"]), "成片": len(batch["outputs"]),
              "素材": len(batch["assets"]), "爆款链接": len(batch["virals"])}
    if args.dry_run:
        print(json.dumps({
            "ok": True, "试运行": "没有发送任何请求", "会登记的批次": counts,
            "会上传的文件": [{"名称": labels[k], "文件": p.name, "大小": p.stat().st_size} for k, p in files.items()],
            "会跳过": skipped,
        }, ensure_ascii=False, indent=2))
        return
    if not any(counts.values()):
        print(json.dumps({"ok": False, "results": skipped}, ensure_ascii=False, indent=2))
        sys.exit(1)

    status, created = api("POST", API + "/batches", batch)
    if status not in (200, 201):
        fail(f"登记这一批失败（{status}）：{created.get('message', '')}")
    job = created.get("job_id", "")
    failed_uploads = []
    for target in created.get("uploads", []):
        path = files.get(target.get("ref"))
        if not path:
            continue
        status, data = send(target.get("method", "PUT"), target["url"], dict(target.get("headers") or {}),
                            body_path=str(path))
        if status not in (200, 201, 204):
            failed_uploads.append({"名称": path.name, "结果": f"上传失败（{status}）", "原因": data.get("message", "")})
    status, done = api("POST", f"{API}/batches/{job}/complete", {})
    if status not in (200, 201):
        fail(f"文件已上传，但确认这一批时失败（{status}）：{done.get('message', '')}。"
             f"可以在导入任务里查看：{created.get('url', '')}")
    results = [{"类型": i.get("type", ""), "名称": i.get("name", ""), "结果": i.get("status", ""),
                "链接": i.get("draft_url", ""), "原因": i.get("message", "")} for i in done.get("items", [])]
    results += failed_uploads + skipped
    bad = [r for r in results if not str(r["结果"]).startswith(("已存为草稿", "已存在"))]
    print(json.dumps({"ok": not bad, "导入任务": done.get("url") or created.get("url", ""), "results": results},
                     ensure_ascii=False, indent=2))
    sys.exit(1 if bad else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("paths", nargs="+")
    scan.set_defaults(run=cmd_scan)
    pack = sub.add_parser("pack")
    pack.add_argument("--manifest", required=True)
    pack.add_argument("--out", required=True)
    pack.set_defaults(run=cmd_pack)
    context = sub.add_parser("context")
    context.set_defaults(run=cmd_context)
    upload = sub.add_parser("upload")
    upload.add_argument("--plan", required=True)
    upload.add_argument("--dry-run", action="store_true")
    upload.add_argument("--secrets-checked", action="append", metavar="WORKFLOW_KEY",
                        help="repeat for each workflow whose secret removal the user confirmed")
    upload.set_defaults(run=cmd_upload)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
