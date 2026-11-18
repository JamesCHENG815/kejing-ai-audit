# 客经 AI 审核工具（kejing-ai-audit）

把业务员门店拜访的 **Excel 填报 + 现场录音**，变成一份「AI 初判 + 经理复核」的审核表。

原来的流程是经理逐段听录音、手工核对 Excel 里的 47 个字段。这个工具先用 ASR 转写录音、让模型把字段值从对话里抽出来，每个值都必须绑定「哪段录音、第几秒、原话是什么」，经理只需要复核有争议的字段。

## 它做什么

- **导入**拜访 Excel（一家门店一行），解析成待审核任务
- **上传**门店录音，按文件名自动推荐门店，人工确认关联
- **转写 + 提取**：OpenAI `gpt-4o-transcribe-diarize` 转写，Responses API Structured Outputs 提取 47 个字段
- **证据绑定**：每个字段值记录录音 ID、起止秒、原文；后端还会用正则回查原文里到底有没有这个数字，对不上就降级为「待确认」
- **四状态判定**：一致 / 待确认 / 冲突 / 缺失，由确定性规则计算，不交给模型自评
- **经理审核**：四模块页面逐字段改值、填原因、存草稿、提交
- **导出** CSV 交给 SFA

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js（App Router）+ TypeScript + Tailwind |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| AI | OpenAI 转写（diarize）+ Responses API Structured Outputs |
| 音频 | ffmpeg / ffprobe |

## 环境要求

- **Python** 3.11+
- **Node.js** 20+
- **ffmpeg**：转写前的音频规范化要用。缺了不会报错，但会静默降级成「原文件直接上传」，失去识别率收益。

```bash
# Windows
winget install Gyan.FFmpeg     # 或解压后把 bin 加入 PATH
# macOS
brew install ffmpeg
# 验证两个都要有
ffmpeg -version && ffprobe -version
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填 OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

> ⚠️ 如果仓库里已经带了 `backend/.venv`，那是 macOS 上创建的（`pyvenv.cfg` 指向 `/Library/Frameworks/...`），在其他系统上不能用，请删掉重建。

### 前端

```bash
cd frontend
npm install
cp .env.example .env.local         # 本地开发保持默认即可
npm run dev                        # http://localhost:3000
```

打开 http://localhost:3000 → `/import` 导入 Excel 和录音 → `/review` 审核。

## 配置

### 后端（`backend/.env`）

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `APP_AUTH_TOKEN` | 接口访问令牌。**留空时只允许本机 127.0.0.1 访问** | 空 |
| `OPENAI_API_KEY` | 必填，缺失时分析接口直接报配置错误 | 空 |
| `OPENAI_TRANSCRIPTION_MODEL` | 转写模型 | `gpt-4o-transcribe-diarize` |
| `OPENAI_EXTRACTION_MODEL` | 字段提取模型 | `gpt-5.6-terra` |
| `OPENAI_AUDIO_NORMALIZE` | 转写前是否做音频规范化 | `true` |
| `OPENAI_AUDIO_FILTERS` | ffmpeg 滤镜链 | `highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11` |
| `OPENAI_AUDIO_CHUNK_SECONDS` | 超 25 MB 时的切片长度 | `300` |
| `OPENAI_PROXY_URL` | 走代理访问 OpenAI 时填 | 空 |
| `OPENAI_REQUEST_TIMEOUT_SECONDS` | 单次请求超时 | `600` |
| `OPENAI_MAX_RETRIES` | SDK 重试次数 | `4` |
| `ANALYSIS_CONFIDENCE_THRESHOLD` | 低于此置信度判为「待确认」 | `0.75` |

### 前端（`frontend/.env.local`）

| 变量 | 作用 |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | 后端地址，默认 `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_API_TOKEN` | 必须与后端 `APP_AUTH_TOKEN` 一致 |

### 鉴权行为（容易踩）

- 未配令牌时**不是全放开**，而是只允许回环地址访问：本地开发零配置可用，一旦有人从内网访问就会 403 并提示去配令牌。
- 生成令牌并两端保持一致：

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- 后端跑在 Nginx / 容器后面时，`request.client.host` 变成代理地址，**那时必须配令牌**，否则全部 403。
- 录音 `<audio>` 无法自定义请求头，所以只有这一个接口允许 `?token=`。

## 目录结构

```
kejing-ai-audit/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI 入口、路由挂载
│   │   ├── settings.py             环境变量 → 配置对象
│   │   ├── models.py / schemas.py  数据表与接口模型
│   │   ├── database.py             SQLite 连接与建表
│   │   ├── field_rules.py          47 个字段定义、单位推断、证据校验、状态判定
│   │   ├── auth.py                 访问令牌校验
│   │   ├── security.py             CSV 转义、上传上限、回环地址判定
│   │   ├── audio_preprocess.py     ffmpeg 封装（规范化 / 压缩）
│   │   ├── transcript_quality.py   转写幻觉过滤
│   │   ├── transcription_prompt.py 热词提示词加载与拼接
│   │   ├── api/                    import-batches / review-tasks / recordings
│   │   └── services/               导入、分析、审核业务逻辑
│   ├── prompts/                    热词表与幻觉词表（可直接编辑）
│   ├── tests/
│   ├── data/                       SQLite 数据库
│   └── storage/                    导入文件与录音
├── frontend/
│   └── src/
│       ├── app/                    /、/import、/review、/review/[taskId]
│       ├── components/
│       └── lib/
└── docs/
```

## 常用命令

```bash
# 后端自检（纯标准库，不需要装任何依赖）
cd backend
python -m app.security             # CSV 转义 + 回环地址判定
python -m app.transcript_quality   # 幻觉过滤规则
python -m app.transcription_prompt # 打印模型实际收到的提示词
python -m app.audio_preprocess 某段录音.m4a   # 试跑音频规范化

# 测试
pip install -r requirements-dev.txt
pytest -q

# 前端
cd frontend
npm run lint
npx tsc --noEmit
```

## 改文件即生效的调优点

这两个文件是给人改的，改完不用动代码、不用重启（按 mtime 自动重载）：

| 文件 | 用途 |
| --- | --- |
| `backend/prompts/transcription_prompt.md` | 品牌 / 产品 / 行业术语热词表。`#` 开头为注释，总长上限 800 字符 |
| `backend/prompts/hallucination_phrases.txt` | 模型在静音段凭空生成的词条，一行一个 |

## 文档

- [开发清单](docs/开发清单.md)：功能清单、核对记录、待办
- [安全加固（2026-11-13）](docs/安全加固-2026-11-13.md)：鉴权、录音访问控制、CSV 注入、上传限额
- [转写准确率（2026-11-14）](docs/转写准确率-2026-11-14.md)：热词、音频规范化、无损切片、幻觉过滤
- [审核留痕（2026-11-14）](docs/审核留痕-2026-11-14.md)：`review_events` 事件表、改前值追溯、存量回填

## 已知限制

- **后台分析用 `BackgroundTasks`**，进程重启或热更新会丢任务，任务永久停在 `pending_analysis`。生产环境需换持久化队列。
- **共享令牌，没有用户身份**：审核人虽然已写进 `review_events`，但前端没有登录态，`reviewer` 仍默认是「当前经理」，多人协作时需在前端把真实姓名传上来。
- **已完成的审核仍可被草稿改写**：状态保持 `completed`，导出内容会跟着变；改动会被记入 `review_events` 可追查，但没有「重新打开审核」的显式流转。
- **列表接口无分页**，计数靠 Python 遍历。导出已改掉 N+1，但列表本身在任务量上到几百时仍会变慢；改分页需同时把搜索/筛选下沉到 SQL。
- **数据库迁移靠手写 `ALTER TABLE`**，没有 Alembic。新增表由 `create_all` 处理，加列仍要手写补丁。
- **前端没有自动化测试**。
