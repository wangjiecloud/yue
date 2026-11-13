# Yue 项目 Agent 指南

错题图片自动生成教学视频：deepseek-v4.1-flash 识题解题 + 本地 CosyVoice3-2512 配音 + 程序动画渲染 + FFmpeg 合成；配套 Vue 制课后台与 Expo 安卓离线 App。需求与验收基线是根目录《系统方案.md》（V1.2），改需求或验收口径先读它。

## 环境关键点

- Python 必须 3.12（pyproject 限定 >=3.12,<3.13）；本机默认 python3 是 3.13，不能直接用。已装 /opt/homebrew/bin/python3.12 和 uv。
- 一律项目内安装：venv 放仓库根 `.venv/`（gitignored），模型权重等下载到项目内新目录；用户要求不装全局环境。
- 必须在 `projects/yue` 目录内启动 Python：SuperJAI 根目录的 logging.py 会遮蔽标准库（logging.getLogger 报 AttributeError）。
- ffmpeg 必须在 PATH（视频渲染与音频转码都调用它）。
- GitHub 远程 wangjiecloud/yue 是公开仓库：严禁提交 .env、密钥、孩子数据、未授权角色素材、模型权重、APK。

## 常用命令（仓库根执行）

```bash
# 一次性环境搭建
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# 测试：必须 python -m，不能用裸 .venv/bin/pytest（原因见下）
.venv/bin/python -m pytest                                # 全量 75 个测试，约 6s
.venv/bin/python -m pytest tests/test_mathcheck.py -k 名字  # 单文件/单函数

# Lint（改完代码必须过；line-length 100，忽略 E501）
.venv/bin/ruff check .

# 后端本地服务：127.0.0.1:8765，仅回环；会话令牌写 data/reports/session_token.txt，
# 改动类请求需 x-yue-token 头（studio 前端经 /api/session 自动获取）
.venv/bin/yue-probe serve

# 探针：调真实 DeepSeek / 本地 CosyVoice，与单测不同，注意费用与限流
.venv/bin/yue-probe probe-env | probe-deepseek | probe-tts | render-probe | demo | validate <plan.json>

# schemas/*.schema.json 由 pydantic 模型生成，不要手改
.venv/bin/yue-probe export-schemas
```

**测试命令坑**：`tests/test_deepseek_adapter.py` 和 `tests/test_tts_adapter.py` 有 `from tests.conftest import ...`；裸 `pytest` 不把仓库根加进 sys.path，这两个文件收集时报 `ModuleNotFoundError: No module named 'tests'`。必须 `python -m pytest`。

## 子项目与结构

- `backend/yue_backend/`：FastAPI。api.py 的 `create_app` 带本地白名单中间件；pipeline/orchestrator.py 是单图→视频全流程（预处理→识题→validate_plan 校验+一次修复重试→TTS→渲染→打包 .yuepack）；adapters/（deepseek.py、tts.py）；mathcheck.py 算术独立验算；db.py 用 SQLite（data/yue.sqlite3）。
- CosyVoice 走隔离工作进程（cosyvoice_worker.py + YUE_COSYVOICE_* 配置），推理依赖不装进 .venv、不混入 API 进程。macOS `say` 占位音频仅限工程探针（YUE_ALLOW_PLACEHOLDER_TTS），不得用于验收课程。
- `studio/`：Vue 3 + Vite。`npm run dev`（127.0.0.1:5175，/api 代理到 8765）；`npm run typecheck`（vue-tsc）；`npm run build` 产出 dist/ 后由后端自动挂载到 `/`。
- `mobile/`：Expo SDK 58 + Expo Router。动代码前先读 mobile/AGENTS.md——Expo 每个 SDK 版本都有 breaking change，勿凭训练记忆写 API，查版本化文档。`.npmrc` 用 npmmirror 镜像；typecheck 用 `npx tsc --noEmit`。
- `schemas/`：课程/教学计划 JSON Schema（生成物）。`data/`：运行期产物（gitignored）：uploads/jobs/courses/media/reports/tmp/assets + yue.sqlite3。
- 配置：仓库根 `.env`（YUE_ 前缀，模板 .env.example；pydantic-settings 自动读取）。

## 开发约定

- 单测全部用 conftest.py 的 FakeTTS / FakeAnalyzer，不联网、不调真实模型；Mock 验证工程行为，真实模型验证能力，两者分开标记。
- 失败样例不得靠硬编码答案、专用分镜或预渲染视频通过验收；不为每道题新增代码，模板按教学能力复用。
- 测试与验收产物用 JSON/日志/截图/视频存受限输出目录，不生成总结类 Markdown。
- 用户未要求时不创建 Git 提交。
