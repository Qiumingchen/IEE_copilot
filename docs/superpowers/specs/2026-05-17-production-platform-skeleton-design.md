# IEE-Copilot 生产型平台骨架设计

日期：2026-05-17

## 1. 目标

IEE-Copilot 第一轮建设目标是搭建一个可长期演进的生产型平台骨架，并跑通一个最小业务纵切。

第一轮不是完整实现所有科研计算功能，而是验证以下主链路可以可靠工作：

```text
Web 搜索
  -> FastAPI 解析查询
  -> PostgreSQL 本地缓存检查
  -> UniProt / RCSB / AlphaFold 外部数据检索
  -> 本地数据库保存
  -> Celery 创建并执行占位分析任务
  -> MinIO 保存 artifact 元数据或占位文件
  -> Web 展示酶概要、缓存更新时间、任务状态
```

这个设计同时服务两个目标：

1. 日常使用：本地 Docker Compose 可启动，开发者和实验室成员可以试用。
2. 论文与后续上线：数据来源、权限、审核、任务状态和 artifact 都有清晰边界，后续可扩展到真实 MSA、Rosetta ddG、MD、MMPBSA 和主动学习。

## 2. 已确认的产品边界

### 2.1 运行方式

采用“本地先跑通，生产可迁移”的策略。

第一版必须支持：

- 本地 `docker compose up --build` 启动主要服务。
- 本地开发环境包含 PostgreSQL、Redis、MinIO、FastAPI、Celery worker、Next.js web。
- 目录和配置预留生产部署路径，但第一轮不实现 Nginx、HTTPS、Kubernetes 或云平台 IaC。

### 2.2 技术栈

前端：

- Next.js
- React
- Tailwind CSS
- 后续可接 shadcn/ui、ECharts、Mol* 或 3Dmol.js

后端：

- FastAPI
- SQLAlchemy 或 SQLModel
- Alembic
- PostgreSQL
- Redis
- Celery
- MinIO

工程管理：

- pnpm workspace 管理前端 workspace
- uv 或 Poetry 管理 Python 依赖
- Docker Compose 管理本地服务

### 2.3 第一轮业务范围

第一轮范围是“生产骨架 + 最小业务纵切”。

包括：

- monorepo 目录结构
- Web / API / Worker 三个应用
- PostgreSQL schema 与 Alembic migration
- Redis 队列
- MinIO artifact storage
- 邮箱登录、项目 owner 权限、角色字段
- 两类 enzyme family seed
- 酶搜索 API
- 15 天缓存 freshness 判断
- UniProt、RCSB PDB、AlphaFold DB 真实 client
- PubMed / Europe PMC 接口占位与人工导入路径
- 分析任务创建和 worker 状态更新
- Web 页面展示搜索结果和任务状态

不包括：

- 真实 Rosetta ddG 执行
- 真实 MAFFT / MSA 计算
- 真实 MD / MMPBSA 流程
- 完整主动学习模型
- 完整审核后台 UI
- 全文文献挖掘和自动突变体抽取

## 3. Monorepo 结构

```text
apps/
  web/              # Next.js 前端
  api/              # FastAPI 后端
  worker/           # Celery worker

packages/
  shared/           # 共享枚举、schema 说明、类型定义

docker/
  api.Dockerfile
  web.Dockerfile
  worker.Dockerfile
  compose/

docs/
  superpowers/specs/
  architecture/
  api/

scripts/
  seed/
  dev/
  data_import/

tests/
  api/
  worker/
  integration/
```

说明：

- `apps/api` 和 `apps/worker` 可以共享 Python 包代码，例如数据库模型、配置、Celery app、外部 client。
- `packages/shared` 第一版只放稳定枚举和字段约定，避免过早做复杂跨语言生成。
- `docker/compose` 保存本地开发 compose 文件和生产示例片段。

## 4. 服务架构

### 4.1 Web

Next.js 负责用户界面：

- 登录
- Dashboard
- 项目列表
- 搜索页
- 酶概要页
- 任务状态页
- 审核入口占位

Web 通过 API 调用后端，不直接访问数据库、Redis 或 MinIO。

### 4.2 API

FastAPI 负责：

- 鉴权
- 项目与用户权限
- 酶搜索和查询解析
- 缓存检查
- 外部数据 client 调用
- 分析任务创建
- artifact 元数据管理

API 不同步运行长任务。凡是可能超过普通 HTTP 请求时长的分析任务都进入 Celery。

### 4.3 Worker

Celery worker 负责：

- 外部数据刷新任务
- 第一版占位 family profile 构建
- 第一版占位 artifact 生成
- 后续真实 MSA、结构分析、Rosetta、MD、MMPBSA 任务

Worker 更新 `analysis_job` 状态和 `analysis_artifact` 记录。

### 4.4 PostgreSQL

PostgreSQL 保存：

- 用户、角色、项目、成员
- 酶条目、序列、结构、性质、突变体、文献
- 实验数据、可见性、审核、审计
- 任务状态、artifact 元数据

### 4.5 Redis

Redis 用作 Celery broker 和 result backend。第一版不把 Redis 当业务数据库。

### 4.6 MinIO

MinIO 保存文件型 artifact：

- 用户上传 PDB
- 下载的 PDB/mmCIF
- AlphaFold 结构文件
- FASTA
- 后续 MSA 文件
- 后续 Rosetta 输出
- CSV / XLSX 导出

数据库只保存 bucket、object key、checksum、content type、size、来源和可见性。

## 5. 数据库设计

### 5.1 身份与权限

`users`

- id
- email
- password_hash
- display_name
- role: `user | curator | admin`
- is_active
- created_at
- updated_at

`projects`

- id
- owner_user_id
- name
- description
- target_enzyme_module
- default_visibility
- created_at
- updated_at

`project_members`

- id
- project_id
- user_id
- role: `owner | member`
- created_at

权限规则：

- 第一版前端实现邮箱密码登录。
- 第一版项目权限以 owner 为主，schema 保留 member。
- `curator` 和 `admin` 角色进入数据模型和 API 权限边界。
- 审核后台 UI 第一版只做入口占位。

### 5.2 酶与序列

`enzyme_family`

- id
- module: `ANTHRAQUINONE_GLYCOSYLTRANSFERASE | MICROBIAL_TRANSGLUTAMINASE_MATURE`
- name
- description
- last_refreshed_at

`enzyme_entry`

- id
- family_id
- name
- organism
- ec_number
- uniprot_id
- pdb_id
- alphafold_id
- source
- last_refreshed_at
- created_at
- updated_at

`protein_sequence`

- id
- enzyme_entry_id
- sequence
- mature_sequence
- is_engineering_target
- source
- checksum
- created_at

规则：

- MTGase 的工程目标只允许使用 mature sequence。
- pro-region 信息后续可作为 annotation 保存，但第一版不用于突变设计。
- Anthraquinone glycosyltransferase 支持用户自定义底物，但第一轮只保留数据模型入口。

### 5.3 结构与 artifact

`structure_entry`

- id
- enzyme_entry_id
- structure_type: `pdb | alphafold | uploaded`
- complex_state: `apo | complex | unknown`
- pdb_id
- chain_summary
- ligand_summary
- artifact_id
- source
- created_at
- updated_at

`analysis_artifact`

- id
- project_id
- enzyme_entry_id
- job_id
- artifact_type
- bucket
- object_key
- checksum
- content_type
- size_bytes
- source
- visibility
- created_at

### 5.4 科学数据

`property_record`

- id
- enzyme_entry_id
- property_type
- value_original
- unit_original
- value_standardized
- unit_standardized
- standardization_status
- substrate
- assay_temperature
- assay_pH
- buffer
- method
- reference_id
- evidence_text
- visibility
- curation_status
- created_at

`kinetic_record`

- id
- enzyme_entry_id
- substrate
- km
- kcat
- kcat_km
- unit_original
- assay_temperature
- assay_pH
- method
- reference_id
- visibility
- curation_status
- created_at

`mutation_record`

- id
- enzyme_entry_id
- parent_enzyme_entry_id
- mutation_string
- mutation_positions
- effect_summary
- property_delta
- substrate
- assay_condition_summary
- reference_id
- is_user_uploaded
- visibility
- curation_status
- created_at

`literature_reference`

- id
- title
- authors
- journal
- year
- doi
- pubmed_id
- source
- metadata_json
- created_at

第一版不强行做复杂单位换算；能可靠标准化时填 `value_standardized`，否则保留原始值并标记状态。

### 5.5 实验、可见性、审核与审计

`user_experiment`

- id
- project_id
- enzyme_entry_id
- variant_name
- mutation_string
- sequence
- measured_property
- measured_value
- unit
- assay_condition_json
- visibility
- curation_status
- created_by
- created_at

`visibility_request`

- id
- project_id
- target_type
- target_id
- requested_visibility
- status: `pending | approved | rejected`
- requested_by
- reviewed_by
- review_comment
- created_at
- reviewed_at

`curation_task`

- id
- visibility_request_id
- status
- assigned_to
- summary
- created_at
- updated_at

`audit_log`

- id
- actor_user_id
- action
- target_type
- target_id
- metadata_json
- created_at

规则：

- 用户上传实验数据默认 `private`。
- `private` 数据只对项目 owner/member 可见，只用于项目模型。
- 公开必须经过审核。
- 只有审核通过的数据才进入公开视图和后续全局模型训练。

### 5.6 任务

`analysis_job`

- id
- project_id
- enzyme_entry_id
- job_type
- status: `queued | running | finished | failed | cancelled`
- parameters_json
- result_summary_json
- error_message
- created_by
- created_at
- started_at
- finished_at

第一版 job 类型：

- `external_data_refresh`
- `family_profile_placeholder`
- `structure_analysis_placeholder`

后续 job 类型：

- `msa`
- `conservation_analysis`
- `rosetta_ddg`
- `md`
- `mmpbsa`
- `active_learning`

## 6. API 设计

第一版 API 分组：

```text
GET  /health
GET  /health/db

POST /auth/register
POST /auth/login
GET  /auth/me

GET  /projects
POST /projects
GET  /projects/{project_id}

POST /enzymes/search
GET  /enzymes/{enzyme_id}

GET  /jobs
GET  /jobs/{job_id}

GET  /artifacts/{artifact_id}

GET  /curation/requests
```

`/enzymes/search` 请求：

```json
{
  "query": "microbial transglutaminase",
  "organism": null,
  "enzyme_module": "MICROBIAL_TRANSGLUTAMINASE_MATURE",
  "project_id": "..."
}
```

`/enzymes/search` 行为：

1. 标准化 query。
2. 判断 UniProt ID、PDB ID、EC number、关键词。
3. 检查 Level 1 本地命中。
4. 检查 15 天 freshness。
5. 命中且新鲜则返回本地数据。
6. 未命中或过期则调用外部 client。
7. 保存或更新 enzyme、sequence、structure。
8. 创建 `analysis_job`。
9. 返回酶概要和 job id。

错误处理：

- 外部 API 部分失败时返回可用数据和 warning。
- 任务失败时保存 `error_message`，前端展示。
- API 返回结构化错误，不暴露内部 stack trace。

## 7. 外部数据连接器

### 7.1 UniProt

第一版真实实现：

- keyword search
- EC search
- organism filter
- accession fetch
- FASTA fetch
- entry metadata fetch

保存：

- UniProt accession
- protein name
- organism
- EC number
- sequence
- source payload 摘要
- refresh time

### 7.2 RCSB PDB

第一版真实实现：

- PDB ID metadata fetch
- UniProt 映射结构搜索
- 结构元数据保存
- 下载链接或 artifact 入口

### 7.3 AlphaFold DB

第一版真实实现：

- 按 UniProt accession 查询模型元数据
- 保存 AlphaFold ID、置信度摘要和下载链接

### 7.4 PubMed / Europe PMC

第一版只实现：

- client interface
- mock result
- manual import 数据路径
- `literature_reference` 保存结构

不阻塞搜索主流程。

## 8. 前端设计

第一版不是营销首页，而是科研工作台。

页面：

- `/login`
- `/dashboard`
- `/projects/[id]`
- `/search`
- `/enzymes/[id]`
- `/jobs/[id]`
- `/curation`

界面原则：

- 信息密度适中，适合重复使用。
- 所有科学数据展示来源和更新时间。
- 长任务显示状态，不让用户猜后台是否运行。
- 审核入口先占位，但权限边界要存在。
- PDB 上传、MSA、Rosetta、MD/MMPBSA、主动学习在第一版以模块入口或占位形式出现，不制造“已经真实计算”的错觉。

## 9. 本地开发与生产预留

### 9.1 本地开发

`docker compose up --build` 启动：

- postgres
- redis
- minio
- api
- worker
- web

提供：

- `.env.example`
- `.env.local.example`
- seed 脚本
- Alembic migration
- API health check
- Web 启动说明

Seed 数据：

- 默认 admin 或 demo user
- 两个 enzyme family
- 一个 demo project

### 9.2 生产预留

预留但不完整实现：

- `.env.production.example`
- Web/API/Worker 独立 Dockerfile
- MinIO 替换为 S3-compatible storage 的配置
- PostgreSQL/Redis 托管服务连接配置
- Nginx/HTTPS 文档占位

第一轮不实现：

- Kubernetes
- Terraform
- 自动证书
- 多实例扩缩容

## 10. 测试与验收

### 10.1 API 测试

必须覆盖：

- health check
- auth register/login/me
- project create/list
- enzyme search cache miss
- enzyme search cache hit
- analysis job create/status

### 10.2 Worker 测试

必须覆盖：

- queued -> running -> finished
- failed job 保存错误摘要
- artifact 记录创建

### 10.3 Web 验证

必须验证：

- 登录页渲染
- dashboard 渲染
- search 页面可提交 query
- enzyme detail 页面显示返回数据
- job 页面显示状态

### 10.4 Compose 验收

本地验收命令应证明：

- Web 可访问
- API health 返回 ok
- API 可连接 PostgreSQL
- Worker 可连接 Redis
- MinIO 可被 API 访问
- 搜索纵切能返回 enzyme summary 和 job id

## 11. 主要风险与处理

### 11.1 外部 API 不稳定

处理：

- client 设置 timeout
- 保存 partial result
- 返回 warning
- 不让外部 API 失败破坏本地数据

### 11.2 科学数据标准化过早复杂化

处理：

- 第一版保存原始值和单位。
- 标准化字段可为空。
- 无法可靠换算时明确标记。

### 11.3 权限模型过重

处理：

- 数据库完整保留 role、visibility、curation、audit。
- 前端只实现必要入口，避免第一版后台 UI 过大。

### 11.4 长任务边界不清

处理：

- API 只创建任务和查询状态。
- Worker 负责执行。
- 所有输出进入 artifact 模型。

### 11.5 第一轮范围膨胀

处理：

- 第一轮只跑通最小业务纵切。
- Rosetta、MSA、MD、MMPBSA、主动学习都只保留扩展点。

## 12. 第一轮完成定义

第一轮完成时，用户应能够：

1. 本地启动所有服务。
2. 用 demo 账号登录。
3. 创建或打开项目。
4. 搜索 MTGase 或蒽醌糖基转移酶关键词。
5. 看到本地缓存命中或外部检索结果。
6. 看到酶概要、序列和结构来源摘要。
7. 看到分析任务状态从 queued/running 到 finished。
8. 在数据库中看到核心科学数据和任务数据。
9. 在 MinIO 或 artifact 表中看到占位产物。
10. 后续可以在这个骨架上继续实现 MSA、结构分析、Rosetta、实验数据上传和主动学习。

