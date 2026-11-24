# 内容资产管理中台 · 导入插件

在 Claude Code 或 Codex 里，把这次对话做出来的东西直接存成内容中台的草稿：工作流（步骤、提示词、文件）、用它做出的成片、素材、爆款链接。

数据按团队的《导入数据标准》（schema_version 1）整理。

状态：0.2.1，插件这一侧已完成并在本地测过。**后端的导入接口还不存在**，见 [docs/backend-api.md](docs/backend-api.md)。接口上线之前，可以用试运行模式看它会导入什么。

## 怎么用

在对话里提到插件，或者直接说「把这次做的导入内容中台」。之后：

1. 它先问能不能读当前对话和工作目录，你同意后才读。
2. 它只会问你一件事：导入到哪个 Project。
3. 它列出清单：要导入哪些工作流、成片、素材、链接，剔除了哪些密钥，没导入什么。
4. 你确认后它上传，返回每一条草稿的链接。
5. 草稿只有你自己看得到，去网页上核对后发布。

## 安装

Claude Code：

```sh
claude plugin marketplace add <组织>/<这个仓库>
claude plugin install content-assets@content-assets-plugin
```

Codex：

```sh
codex plugin marketplace add <组织>/<这个仓库>
codex plugin add content-assets@content-assets-plugin-codex
```

Codex 的清单是照 Kabo 公开插件的写法做的，还没有在 Codex 里实际装过。

## 导入令牌

在内容中台页面生成导入令牌后，自己保存到本机，二选一：

- 文件 `~/.kabo/content-assets-token`，权限设为 600。
- 环境变量 `KABO_CONTENT_ASSETS_TOKEN`。

不要把令牌贴进对话。插件和 agent 都不会读取或显示它，只有上传脚本在发请求时使用。

连预发环境：设置 `KABO_CONTENT_ASSETS_URL`。

## 目录

```
.claude-plugin/            Claude Code 的清单
.agents/plugins/           Codex 的清单
plugin.json                通用插件清单
skills/import-content-assets/
  SKILL.md                 流程和规则
  references/              什么算什么、字段怎么填
  scripts/hub.py           扫描密钥、打包、上传（只用 Python 标准库）
docs/backend-api.md        给研发：需要新增的导入令牌和接口
```

## 脚本

```sh
python3 skills/import-content-assets/scripts/hub.py scan <路径>
python3 skills/import-content-assets/scripts/hub.py pack --manifest manifest.json --out plan
python3 skills/import-content-assets/scripts/hub.py upload --plan plan --dry-run
```

- `scan`：报告看起来像密钥的位置，只给名称和行号，不显示值。
- `pack`：按标准校验清单，把工作流文件复制出来、把密钥的值替换成占位、生成包里的 `manifest.json`、打成 zip。`.env` 文件不打包。不会改动原文件。
- `upload --dry-run`：不发请求，只显示会发什么。

## 已知的限制

- 密钥是按常见格式识别的，可能漏。所以上传工作流前必须由人确认一次。
- 成片必须有视频文件，并且必须对得上一个工作流。
- 线上的内容中台现在存不下标准里的大部分字段（步骤、素材组、发布链接等），见接口说明第 1 节。
- 文件上传没有做断点续传。
- 还没有「把工作流拉取到本地」。
