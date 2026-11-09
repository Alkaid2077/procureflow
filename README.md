# ProcureFlow 中文扫描报价复核

本分支基于 [ProcureFlow](https://github.com/mbs20/procureflow)（Apache-2.0，起点 `54faa94`）。目标是让采购员在原有报价复核页面发现扫描表格里的数值错误，核对原图，再决定是否接受修正。

## 上游能力与当前缺口

- 上游已经支持 RFQ、PDF／CSV／XLSX 报价导入、OCR、证据预览、人工复核、单位与币种换算、确定性比价和操作记录。
- OCR 命令行回退默认使用英文。上游的离线抽取评测没有覆盖中文和劣化扫描件。
- PDF 模型抽取会检查证据 ID 是否有效。页面级证据仍可能包含多条商品行，不能单凭证据 ID 识别串行、漏列和小数点误读。
- 模型能力与硬件分离。本地开发路径使用 CPU、SQLite 和离线 mock。可选视觉复核使用 OpenAI 兼容接口，仅发送问题区域。模型缺失、请求失败或证据不足时保留待人工复核状态。

## 实施阶段

| 阶段 | 优先级 | 交付和验收 | 状态 |
| --- | --- | --- | --- |
| 0. 基线与计划 | P0 | 固定上游版本，记录原有功能、已知缺口、安装路径和验收边界。 | 已记录 |
| 1. 中文 OCR 与异常识别 | P0 | 支持配置 OCR 语言，识别扫描行的数值矛盾；保留原始值和原始证据，补正常行和异常行测试。 | 完成，已实跑 CPU OCR |
| 2. 局部视觉复核 | P0 | 对有可定位证据的异常行裁切原图，调用可配置的视觉接口；在可校验时给出建议，否则保留人工复核。验证超时、冲突和禁用模型场景。 | 完成，已验证模拟视觉接口与失败回退 |
| 3. 接入复核与比价 | P0 | 复核界面展示原值、建议、理由和出处。采购员确认后复用现有编辑和比价链路；添加端到端回归。 | 完成，API 全流程和前端构建通过 |
| 4. 可复跑交付 | P1 | 提供合成样例、离线验证命令、上游与改版的可复核结果。分开报告 mock 验证与真实 OCR／视觉模型实测。 | 完成，样例生成与离线回归已验证 |

每完成一阶段，更新此表和下面的验证记录。真实视觉模型测试使用合成报价，需有支持图像输入的服务和有效凭据。所有配置示例仅使用占位值。

## 已接入的使用流程

设置 `OCR_LANGUAGE=chi_sim+eng` 后，CPU OCR 支持有「品名／数量／单价／金额」表头的常见中文扫描报价。识别到的数值矛盾、缺失和无法定位的行会进入人工复核。对可定位的异常行，可以显式配置 `SCAN_VISION_BASE_URL`、`SCAN_VISION_MODEL` 和服务所需凭据。接口仅接收被标记的行裁片，建议会和原值一起出现在现有复核页面。采购员核对后点击 Review suggested edit，在原有编辑框中确认修改，系统仍按原有规则审批和比价。

默认视觉请求上限为每个 PDF 4 行、单请求超时 15 秒，可通过环境变量调整。示例中 URL 应包含服务的 API 前缀，例如 `/v1`。启用远端服务会把裁片发送给配置的服务商，演示仅使用合成文件。

## 开发环境

首选 Windows 上的 Python、SQLite 和离线 mock。安装 Python 或前端依赖时优先使用国内镜像，例如 PyPI 清华镜像和 npmmirror，镜像设置仅作用于安装命令。PDF 中文 OCR 可以用 PyMuPDF 的 OCR 和相应 Tesseract 语言数据。也可安装 Tesseract 命令行作为回退。视觉复核使用可选远端接口或用户已有的兼容服务。离线流程只需要 CPU。

安装后端依赖可按下方上游说明使用锁文件。开发时可为 PyPI 或 npm 命令指定国内镜像，例如 `https://pypi.tuna.tsinghua.edu.cn/simple` 和 `https://registry.npmmirror.com`。本次验证使用了这两个镜像，并按上游锁文件校准 FastAPI、Starlette 和 Pydantic。

## 验证记录

在 `backend` 目录运行 `python -m pytest -q tests/unit/test_chinese_scan_review.py`，无需 OCR 语言包或模型服务。用例生成图像型中文 PDF，模拟 OCR 结果和视觉回复，并验证裁切尺寸、人工确认边界和失败回退。该用例用于软件回归。另有 API 测试覆盖上传、建议、人工确认、审批及比价。

在 `backend` 目录运行 `python -m procureflow.scripts.create_scan_demo chinese-demo.pdf` 可生成图像型中文报价。要实跑 CPU OCR，下载 [Tesseract 官方轻量语言包](https://github.com/tesseract-ocr/tessdata_fast) 中的 `chi_sim` 和 `eng`，将 `TESSDATA_PREFIX` 指向包含这两个文件的目录，设置 `OCR_LANGUAGE=chi_sim+eng` 和 `PROCUREFLOW_LLM_PROVIDER=mock`，再为同一命令加 `--check-ocr`。预期抽出钢制支架、数量 10、单价 28.50、行金额 285.00。

- 后端全套 184 项测试通过。扫描复核 API 测试覆盖从上传、暂缓审批到确认建议、审批、比价更新。
- 前端 TypeScript 类型检查、69 项测试和生产构建通过。构建保留 Vite 对上游大分包的体积提示。
- CPU 实跑真实 OCR 已通过。合成报价成功提取钢制支架、数量 10、单价 28.50、行金额 285.00。
- 视觉服务使用模拟响应验证请求结构、局部裁片、建议、冲突和超时。真实模型效果和更复杂的报价版式尚未评估。

## 上游说明

# ProcureFlow

A self-hosted, evidence-backed quotation comparison and deterministic scoring engine for procurement workflows.

[![CI](https://github.com/mbs20/procureflow/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mbs20/procureflow/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](backend/pyproject.toml)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](frontend/package.json)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](docker-compose.yml)

ProcureFlow is under active development. Bug reports, feature proposals, documentation contributions, and pull requests are welcome. Start with the [contributing guide](CONTRIBUTING.md) or [open an issue](https://github.com/mbs20/procureflow/issues/new/choose). Report security vulnerabilities privately using the [security policy](SECURITY.md).

> ProcureFlow was started as an open-source exploration of how supplier quotations can be compared more systematically, transparently, and reproducibly without relying on proprietary black-box procurement software.

## Project Status

| Scope | Status |
|---|---|
| Implemented | RFQs, PDF/CSV/XLSX ingestion, human review, comparison snapshots, deterministic scoring and sensitivity, draft narratives, explicit award confirmation, application event history. |
| Demonstration | The Compose demo uses synthetic supplier documents, fixed example exchange rates, a shared development API key, and an offline mock provider. It is for local evaluation, not a hardened public deployment. |
| Roadmap | Individual identity and roles, tenant isolation, object storage, live FX feeds, and ERP integrations are not implemented. See the [roadmap](docs/ROADMAP.md); proposed milestones are not delivery commitments. |

The CI badge reports the `main` workflow status. The other badges identify the license and technologies, not adoption or certification.

---

## Quickstart

Prerequisites: Git, Docker with Compose v2, and a running Docker engine. From a terminal:

```bash
git clone https://github.com/mbs20/procureflow.git
cd procureflow
```

Start the development/demo stack with a pre-seeded synthetic dataset using Docker Compose. Use a trusted machine; the supplied configuration is not suitable for public exposure:

```bash
docker compose --profile demo up --build
```

### Services Started

- **PostgreSQL 16**: Database with migrations applied.
- **FastAPI Backend**: REST API on port `8000`.
- **Celery Worker**: Asynchronous document ingestion and parsing.
- **Redis**: Message broker and task state storage.
- **Nginx & React Frontend**: Web interface on port `5173`.
- **Demo Seed**: Automatically loads a sample RFQ with three supplier quotes (PDF, Excel, CSV).

### Endpoints

- Web Interface: [http://localhost:5173](http://localhost:5173)
- API Documentation (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

To stop all containers:
```bash
docker compose --profile demo down
```

---

## Why I Built This

Comparing vendor proposals is an interesting problem: quotes arrive in diverse layouts (PDF documents, spreadsheets with varied column names, or CSV files). Looking at common procurement workflows out of curiosity, much of this comparison work still seems to involve copy-pasting numbers into informal spreadsheets.

This exploratory project was built to test a more structured approach:

1. **Extraction and linking**: Investigating whether parsed line items and prices can stay directly linked to their coordinates in the source files.
2. **Standardized comparison**: Testing how unit and currency conversions can be handled consistently in a clear matrix.
3. **Transparent scoring**: Experimenting with explicit linear formulas and knockout rules rather than complex or opaque ranking systems.

Rather than attempting to replace full-scale enterprise tools, ProcureFlow is a focused sandbox exploring how self-hosted software can make quote comparison clearer and more verifiable.

---

## Design Choices

- **Deterministic scoring over opaque algorithms**: Supplier rankings are calculated using explicit linear weights and configurable knockout criteria. Scoring formulas and weight breakdowns are directly visible in the interface.
- **Document-to-value traceability**: Parsers extract text with spatial bounding boxes where available. Where source evidence is available, clicking an extracted value navigates to its source. Table citations may lack bounding boxes and OCR citations may cover a whole page.
- **Buyer review and sign-off**: Automated extraction assists data entry, but the buyer retains authority. Award decisions require confirmation, and choosing a supplier other than the top-ranked vendor asks for a recorded justification.
- **Self-contained deployment**: The application runs within standard Docker containers without mandatory cloud dependencies.
- **Bilingual interface**: The user interface supports English and French, including numeric formatting and localized terminology.

---

## Core Workflow

```
Supplier Quotations (PDF, XLSX, CSV)
       │
       ▼
[Document Ingestion & Extraction]            ──► Available Source Citations
       │
       ▼
[Human Review & Correction]                  ──► Approved Values for Comparison
       │
       ▼
[Currency & Unit Normalization]              ──► Side-by-Side Comparison Matrix
       │
       ▼
[Deterministic Scoring Engine]               ──► Formula-Based, Verifiable Rankings
       │
       ▼
[Grounded Decision Memo]                     ──► Structured Claims Linked to Source Data
       │
       ▼
[Buyer Review & Award Authorization]         ──► Recorded Sign-Off and Rationale
```

### Key Capabilities

1. **Multi-Format Ingestion**: Upload PDF, XLSX, and CSV quotations. Extracted line items and commercial fields depend on the document layout and require review; legacy XLS is unsupported.
2. **Split-Pane Review Workspace**: Inspect parsed values alongside original documents and navigate available source citations. Not all fields have precise bounding boxes.
3. **Comparison Matrix**: Compare line items across vendors with currency conversion to the RFQ base currency and unit harmonization.
4. **Scoring & Sensitivity**: Adjust weights for cost, delivery time, warranty, and technical criteria. Sensitivity sweep views show how score adjustments influence rankings.
5. **Decision & Audit Log**: Review the structured decision memo, confirm the award, and maintain an append-only event log.
6. **Narrative Assistance**: Configurable providers can structure extracted text and propose draft memos. Scoring and knockout rules use deterministic calculations; award confirmation remains a separate explicit action. See [provider boundaries](docs/adr/0002-llm-abstraction-and-instructor.md).

---

## System Architecture

```mermaid
graph TD
    subgraph Client Layer
        UI["React 18 + TypeScript SPA<br/>(Nginx Container, Port 5173)"]
    end

    subgraph API & Task Layer
        API["FastAPI Backend<br/>(Python 3.12, Port 8000)"]
        Worker["Celery Worker<br/>(Document Processing & Ingestion)"]
        Redis[("Redis 7<br/>Broker & Task Results")]
    end

    subgraph Core Modules
        Parsers["Document Parsers<br/>(PDF, XLSX, CSV)"]
        Norm["Normalization Engine<br/>(Units & Currency)"]
        Scorer["Deterministic Scoring Engine<br/>(Weighted Criteria & Sensitivity)"]
        LLM["LLM / Mock Provider<br/>(Optional Extraction & Summary Draft)"]
    end

    subgraph Storage Layer
        DB[("PostgreSQL 16<br/>Alembic Migrations & Audit Trail")]
        Filesystem[("Local Storage<br/>(Quotation Files & Artifacts)")]
    end

    UI -->|Reverse Proxy /api/| API
    API --> DB
    API --> Filesystem
    API -->|Enqueue Task| Redis
    Worker --> Redis
    Worker --> Parsers
    Worker --> Norm
    Worker --> DB
    Worker --> Filesystem
    API --> Scorer
    API --> LLM
```

---

## Current Limitations

- **Authentication**: Protected operations use a shared API-key principal (`X-API-Key`), not verified individual identities or human signatures. The demo browser embeds a development key and document preview routes lack individual access checks. Restrict the whole deployment behind an authenticated perimeter; see [deployment boundaries](docs/LIMITATIONS.md).
- **Document Storage**: Uploaded files are stored on the local filesystem volume. Cloud object storage backends (such as S3 or GCS) are not yet integrated.
- **Exchange Rates**: The demo environment uses fixed synthetic exchange rates. Connecting live financial data feeds is planned for future iterations.
- **Complex Document Layouts**: Clean tabular documents extract reasonably well. Skewed scans, degraded photocopies, or irregular multi-column layouts may require manual adjustments during review.
- **Narrative Language**: While the user interface supports both English and French, generated narrative decision memos are currently produced in English.

---

## Local Development (Without Docker)

### Prerequisites

- Python 3.12 (the CI version) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Node.js 20 and npm (matching CI).
- Tesseract on your PATH if you want OCR for scanned PDFs; native PDF/CSV/XLSX fixtures do not require it.

The lightweight setup below uses SQLite, synchronous extraction, and the offline mock provider. No PostgreSQL, Redis, worker, or paid provider key is needed. Use Docker for the distributed PostgreSQL/Redis workflow.

### Backend Setup
```bash
cd backend
uv sync --frozen --extra dev
```

Activate the environment using the command for your shell:

```bat
:: Windows Command Prompt
.venv\Scripts\activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

Activation is optional: prefix backend commands with `uv run --no-sync` to use the installed environment directly, including when PowerShell script activation is unavailable.

Create `backend/.env` with the following local-only settings. Settings are read from the current working directory, so start backend commands from `backend/`:

```dotenv
PROCUREFLOW_ENV=development
PROCUREFLOW_LLM_PROVIDER=mock
DATABASE_URL=sqlite+aiosqlite:///./procureflow.db
DATABASE_URL_SYNC=sqlite:///./procureflow.db
CELERY_ALWAYS_EAGER=true
CELERY_BROKER_URL=memory://
CELERY_RESULT_BACKEND=cache+memory://
STORAGE_LOCAL_DIR=./data/storage
```

Then run:

```bash
alembic upgrade head
uvicorn procureflow.main:app --reload --port 8000
```

Eager mode runs extraction within the request and can block the API during parsing. For a separate worker, use the Docker quickstart or configure PostgreSQL/Redis URLs, set `CELERY_ALWAYS_EAGER=false`, and start `celery -A procureflow.tasks.celery_app worker --loglevel=info` from an activated backend terminal. Use Docker or WSL for workers on Windows.

The root `.env.example` documents additional settings; its PostgreSQL settings are an alternative to the SQLite setup, not prerequisites for it. A root `.env` is used by Compose for interpolation and is not automatically loaded by Python started inside `backend/`.

### Frontend Setup

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to the backend on port 8000. The browser uses the shared development API key. Do not run the Docker frontend and Vite on the same port at the same time.

---

## Testing

After installing dependencies, run from the repository root (no activation needed with `uv run`):

```bash
cd backend
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
uv run --no-sync mypy src/
uv run --no-sync pytest

cd ../frontend
npm run typecheck
npm test
npm run build
```

Backend tests use temporary SQLite databases and mock transports. CI runs schema-drift validation through `command.check(alembic_cfg)` inside `test_fresh_migration_and_schema_drift()`, which is part of the pytest suite. The standalone `alembic check` CLI command can also be run manually; CI does not invoke that command directly.

For browser tests, install Chromium once, start the Docker stack for live integration coverage, and run from `frontend/`:

```bash
npx playwright install chromium
npx playwright test
```

On Linux, use `npx playwright install --with-deps chromium` to install browser system dependencies. Without Docker, the live tests are skipped; see [validation and contribution instructions](CONTRIBUTING.md) for the explicit Docker command and test subset.

---

## Documentation & Reference

- [Architecture Decision Records (ADRs)](docs/adr/0001-architecture-and-tech-stack.md)
- [Limitations & Scope Document](docs/LIMITATIONS.md)
- [Provider Configuration](docs/adr/0002-llm-abstraction-and-instructor.md)
- [Reproducible Extraction Evaluation](docs/EXTRACTION_EVALUATION.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Product Roadmap](docs/ROADMAP.md)
- [OpenAPI Specification](docs/api/openapi.json)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

---

## License

ProcureFlow is open-source software licensed under the [Apache License 2.0](LICENSE).
