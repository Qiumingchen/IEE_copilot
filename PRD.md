下面给出两份文档草案：

1. **PRD 产品需求文档**
2. **Codex 开发任务清单 / GitHub Issues**

项目暂定名：**IEE-Copilot：工业酶智能设计与闭环进化平台**

---

# 一、PRD 产品需求文档

# 1. 产品概述

## 1.1 产品名称

**IEE-Copilot**

全称：

**Industrial Enzyme Engineering Copilot**

中文名：

**工业酶智能设计与闭环进化平台**

## 1.2 产品定位

IEE-Copilot 是一个面向酶工程实验室的在线工具，聚焦两类工业酶：

1. **蒽醌类糖基转移酶**
2. **成熟型微生物源谷氨酰胺转氨酶**

平台整合公开数据库、文献数据、结构分析、同源序列分析、突变体知识库、Rosetta ddG 计算、实验数据反馈和主动学习模型，帮助用户完成从“找酶”到“设计突变”再到“下一轮进化推荐”的闭环流程。

## 1.3 产品目标

平台目标是帮助实验室用户完成：

```text
搜索工业酶
查看来源和已报道性质
查看已报道突变体
上传 PDB 或复合物结构
进行同源序列和保守性分析
推荐热点位点
推荐突变组合
生成实验突变库
上传湿实验数据
训练项目模型
推荐下一轮突变组合
```

最终形成：

```text
Search → Profile → Compare → Design → Test → Learn → Redesign
```

---

# 2. 产品背景

## 2.1 当前痛点

酶工程实验室在进行工业酶改造时，通常面临以下问题：

1. 数据分散
   酶序列、结构、文献性质、动力学参数、突变体信息分散在 UniProt、PDB、BRENDA、SABIO-RK、文献和实验记录中。

2. 数据不可直接比较
   不同文献中的比酶活、最适温度、最适 pH、Km、kcat 等数据常常来自不同底物、不同 pH、不同温度和不同测定方法。

3. 突变推荐缺乏解释
   现有工具通常给出候选位点，但缺少结构、进化、文献和实验条件层面的综合解释。

4. 计算结果与湿实验脱节
   很多平台停留在“推荐突变”，但没有继续支持实验数据上传、模型训练和下一轮推荐。

5. 小样本实验数据利用不足
   实验室经常只有几十到几百个突变体数据，传统深度学习不适合，需要小样本主动学习策略。

---

# 3. 目标用户

## 3.1 主要用户

```text
酶工程实验室研究生
天然产物糖基化研究人员
工业酶研发人员
食品酶制剂研发人员
生物催化实验人员
蛋白工程课题组 PI
```

## 3.2 次要用户

```text
计算生物学研究人员
合成生物学平台人员
企业研发项目经理
数据库维护人员
论文数据审核人员
```

---

# 4. 产品范围

## 4.1 MVP 聚焦酶类

### 4.1.1 蒽醌类糖基转移酶

底物范围：

```text
不限定具体蒽醌底物
允许用户自定义蒽醌类底物
```

重点优化目标：

```text
比酶活
产物选择性
底物特异性
表达量
可溶性
热稳定性
```

### 4.1.2 成熟型微生物源谷氨酰胺转氨酶

范围限制：

```text
只做 mature enzyme
pro-region 可作为注释保存
MVP 不把 pro-enzyme/pro-region 作为突变设计对象
```

重点优化目标：

```text
热稳定性
最适温度
最适 pH
比酶活
表达量
可溶性
工业条件适应性
```

---

# 5. 用户目标

用户可以选择以下目标：

```text
提高热稳定性
提高最适温度
提高比酶活
改变最适 pH
提高表达量/可溶性
提高产物选择性
提高对映选择性
```

默认目标：

```text
稳定性 + 酶活保持/提高
```

---

# 6. 核心用户流程

## 6.1 流程一：搜索酶

用户输入：

```text
酶名
EC 号
来源物种
UniProt ID
PDB ID
```

系统执行：

```text
解析输入
判断酶类模块
检查本地数据库
检查 15 天缓存
如本地数据可用，则直接返回
如无数据或数据过期，则调用外部 API 或文献检索
保存结果到本地数据库
返回酶详情
```

用户看到：

```text
酶基本信息
来源物种
序列
结构
AlphaFold/PDB 信息
已报道性质
已报道突变体
文献来源
数据更新时间
```

---

## 6.2 流程二：上传 PDB

用户上传：

```text
apo PDB
或
酶-底物复合物 PDB
```

系统判断：

```text
apo
complex
unknown
```

如果是 apo PDB，系统分析：

```text
链信息
序列
结构质量
表面残基
保守性映射
预测口袋残基
稳定性改造位点
可溶性相关位点
```

如果是 complex PDB，系统额外分析：

```text
配体识别
底物候选识别
4 Å / 6 Å / 8 Å 范围内残基
底物距离矩阵
结合口袋残基
选择性相关位点
MMPBSA 预留
MD 预留
```

---

## 6.3 流程三：设计突变

用户选择：

```text
起始酶
目标性质
是否使用上传结构
是否使用已报道突变体信息
实验库规模
```

系统执行：

```text
同源序列收集
MSA
保守性分析
结构映射
口袋残基识别
文献突变证据整合
Rosetta ddG 队列计算
热点位点评分
单点突变推荐
组合突变推荐
实验库设计
```

输出：

```text
热点位点
推荐突变
推荐组合
推荐理由
风险提示
Rosetta ddG 结果
96 孔板布局
CSV/Excel 导出
```

---

## 6.4 流程四：上传湿实验数据

用户上传：

```text
CSV
Excel
```

实验数据包括：

```text
突变体名称
突变字符串
序列
比酶活
相对活性
最适温度
最适 pH
表达量
可溶表达比例
Km
kcat
kcat/Km
底物
产物比例
对映选择性
测定温度
测定 pH
缓冲液
测定方法
重复数
备注
数据权限
```

系统执行：

```text
字段校验
突变格式校验
序列映射
单位保存
实验条件保存
权限保存
项目模型训练
下一轮突变推荐
```

输出：

```text
数据质量报告
模型性能
特征重要性
下一轮推荐突变
探索型候选
利用型候选
推荐实验库
```

---

# 7. 核心功能需求

# 7.1 酶搜索与本地缓存

## 功能描述

系统支持用户通过酶名、EC 号、来源物种、UniProt ID、PDB ID 或上传结构来检索目标酶。

## 缓存策略

```text
如果 Level 1 命中，且数据 15 天内更新：
    直接返回本地数据

如果 Level 2 命中，且 family profile 15 天内更新：
    返回本地 family profile 和位点映射信息

否则：
    触发外部数据检索
    更新本地数据库
    返回新结果
```

## Level 1 定义

```text
UniProt ID 相同
PDB 映射到相同 UniProt ID
上传序列 identity >= 98%
上传 PDB 链序列 identity >= 98%
```

## Level 2 定义

```text
同一酶类模块
序列 identity >= 40%
alignment coverage >= 70%
```

## 验收标准

```text
用户可以输入酶名并获得搜索结果
用户可以输入 UniProt ID 并获得精确结果
用户可以输入 PDB ID 并获得结构关联信息
系统可以判断本地数据是否过期
过期数据可以触发刷新任务
刷新结果可以保存到数据库
```

---

# 7.2 外部数据检索

## MVP 数据源

```text
UniProt
RCSB PDB
AlphaFold DB
PubMed / Europe PMC metadata
```

## 预留数据源

```text
BRENDA
SABIO-RK
手动整理数据导入
文献突变体抽取
```

## 验收标准

```text
系统可以通过 UniProt 获取序列和注释
系统可以通过 RCSB 获取结构元数据
系统可以通过 AlphaFold DB 获取预测结构
系统可以通过文献元数据接口保存参考文献信息
所有数据必须保存来源和更新时间
```

---

# 7.3 双酶类知识库

## 数据内容

每个酶条目应包含：

```text
酶名称
酶类模块
EC 号
来源物种
UniProt ID
PDB ID
AlphaFold ID
序列
成熟酶序列
结构
配体
底物
已报道性质
已报道突变体
文献来源
用户公开数据
```

## 验收标准

```text
可以区分蒽醌类糖基转移酶和成熟型微生物转谷氨酰胺酶
MTGase 只使用 mature enzyme 作为工程对象
蒽醌糖基转移酶允许用户自定义底物
每条性质数据都有来源和实验条件
```

---

# 7.4 同源序列、MSA 和保守性分析

## 默认参数

```text
identity_min = 40%
identity_max = 95%
coverage_min = 70%
max_sequences = 500
```

## 分析流程

```text
获取 query sequence
搜索同源序列
过滤 identity 和 coverage
去冗余
运行 MAFFT
计算 Shannon entropy
计算 wildtype residue frequency
映射到 query sequence 位点
```

## 验收标准

```text
系统可以为目标酶构建同源序列集
系统可以生成 MSA
系统可以计算每个位点的保守性分数
系统可以将保守性映射到结构位点
前端可以展示 MSA 和保守性结果
```

---

# 7.5 PDB 上传和结构分析

## 功能描述

用户可以上传 apo PDB 或酶-底物复合物 PDB。

## 结构分类

```text
apo
complex
unknown
```

## apo 分析内容

```text
链识别
序列提取
结构质量检查
表面残基识别
预测口袋残基
保守性映射
```

## complex 分析内容

```text
配体识别
底物候选识别
金属离子识别
4 Å / 6 Å / 8 Å 邻近残基
底物距离矩阵
结合口袋摘要
```

## 验收标准

```text
用户可以上传 PDB 文件
系统可以识别链和序列
系统可以判断 apo 或 complex
系统可以列出配体
系统可以列出配体附近残基
系统可以映射 PDB 编号和序列编号
```

---

# 7.6 性质数据与双排名

## 保存字段

每条性质数据必须保存：

```text
property_type
value_original
unit_original
value_standardized
unit_standardized
standardization_status
substrate
assay_temperature
assay_pH
buffer
method
organism
reference
evidence_text
visibility
curation_status
```

## 排名一：原文献值排名

名称：

```text
Reported Value Ranking
```

规则：

```text
按原始报道值排序
保留原始单位
展示原始实验条件
展示不可严格横向比较提示
```

## 排名二：同条件分组排名

名称：

```text
Condition-grouped Ranking
```

分组键：

```text
reference_id
substrate
assay_temperature
assay_pH
unit
method
```

## 验收标准

```text
用户可以查看原文献值排名
用户可以查看同条件分组排名
不同条件数据必须显示警告
无法标准化的数据不能被强行换算
每个数值可以追溯到来源
```

---

# 7.7 突变体知识库

## 内容

```text
突变体名称
parent enzyme
mutation string
突变位点
突变前氨基酸
突变后氨基酸
背景序列
对应性质变化
底物
实验条件
文献来源
是否用户上传
是否公开
```

## 验收标准

```text
用户可以查看已报道突变体
用户可以按性质筛选突变体
用户可以查看突变前后变化
突变编号可以通过 MSA 映射到当前目标酶
未审核数据不能显示为 verified
```

---

# 7.8 结构感知突变推荐

## 推荐输入

```text
目标酶
目标性质
MSA 结果
保守性结果
结构信息
配体信息
已报道突变体
Rosetta ddG
用户约束
```

## 通用评分因子

```text
保守性
野生型氨基酸频率
二级结构
溶剂可及性
距离配体
距离预测口袋
距离催化残基
已报道突变次数
已报道有益突变次数
Rosetta ddG
可溶性风险
```

## 蒽醌糖基转移酶特异评分

```text
蒽醌结合区域评分
UDP-sugar 结合区域评分
产物选择性评分
活性评分
可溶性评分
稳定性评分
```

## MTGase 特异评分

```text
热稳定性评分
最适温度评分
最适 pH 评分
酶活保持评分
表面电荷评分
可溶性评分
```

## 输出字段

```text
位点
野生型氨基酸
推荐突变
目标性质
总分
分项评分
推荐理由
风险提示
推荐实验策略
```

## 验收标准

```text
系统可以根据目标性质推荐突变位点
每个推荐必须有解释
每个推荐必须有风险提示
可以区分两个酶类的不同评分逻辑
可以导出推荐突变列表
```

---

# 7.9 Rosetta ddG 队列

## 功能描述

对候选突变进行 Rosetta ddG 计算。

## 任务状态

```text
queued
running
finished
failed
cancelled
```

## 规则

```text
Rosetta 任务必须异步执行
不能在 API 请求中同步运行
失败任务可以重试
结果需要保存到数据库
```

## 验收标准

```text
用户可以提交 Rosetta ddG 任务
前端可以查看任务状态
任务完成后可以查看 ddG 结果
失败任务可以显示错误信息
结果可用于突变评分
```

---

# 7.10 MD 和 MMPBSA 预留

## MVP 范围

只实现：

```text
数据表
API 占位
前端占位模块
任务状态
```

## 暂不实现

```text
真实 MD 流程
真实 MMPBSA 流程
自动轨迹分析
```

## 验收标准

```text
系统中存在 MD/MMPBSA 任务模型
前端显示该模块为预留功能
complex PDB 可以关联 MMPBSA 预留任务
不会执行真实模拟
```

---

# 7.11 组合突变和实验库设计

## 功能描述

系统根据单点突变推荐结果生成组合突变方案和实验库。

## 规则

```text
同一位点不能组合多个突变
避免高风险突变过度组合
优先组合稳定性突变和活性/选择性突变
惩罚空间冲突突变
支持用户定义实验库规模
```

## 输出

```text
Top single mutants
Top double mutants
focused mutation library
96-well plate layout
CSV/Excel export
```

## 验收标准

```text
用户可以选择实验库规模
系统可以生成组合突变
系统可以生成 96 孔板布局
用户可以下载 CSV/Excel
```

---

# 7.12 实验数据上传

## 支持格式

```text
.csv
.xlsx
```

## 推荐字段

```text
variant_id
mutation_string
sequence
specific_activity
relative_activity
opt_temperature
opt_pH
expression_level
soluble_expression
Km
kcat
kcat_Km
substrate
product_ratio
enantioselectivity
assay_temperature
assay_pH
buffer
method
replicate
notes
visibility
```

## 验收标准

```text
用户可以上传 CSV/Excel
系统可以校验字段
系统可以校验突变字符串
系统可以映射到 parent mature sequence
系统可以保存实验条件
默认 visibility 为 private
```

---

# 7.13 数据权限与审核

## 数据权限

```text
private
public
```

## 默认规则

```text
用户上传数据默认为 private
private 数据只对项目用户可见
private 数据只用于项目模型
public 数据所有用户可查看
public 数据可用于全局模型
```

## 公开审核流程

```text
private
    ↓
public_request
    ↓
curator_review
    ↓
approved_public / rejected
```

## 审核内容

```text
单位检查
实验条件检查
突变格式检查
来源检查
重复数据检查
审核意见
```

## 验收标准

```text
用户可以申请公开数据
审核员可以批准或拒绝
拒绝时必须填写原因
只有审核通过的数据才进入公开数据库
```

---

# 7.14 主动学习和下一轮推荐

## 模型

MVP 支持：

```text
Random Forest
XGBoost / LightGBM
Gaussian Process
Bayesian Optimization
```

## 特征

```text
mutation one-hot
氨基酸理化性质
保守性分数
Rosetta ddG
距离配体/口袋
已报道突变证据
酶类特异特征
```

## 推荐类型

```text
exploitation
exploration
```

## 输出

```text
推荐突变组合
预测值
不确定性
推荐类型
推荐理由
建议孔位
```

## 验收标准

```text
系统可以用项目实验数据训练模型
系统可以显示模型性能
系统可以输出下一轮推荐
系统可以区分探索型和利用型候选
推荐结果可以导出为实验库
```

---

# 8. 页面需求

## 8.1 首页

功能：

```text
选择酶类模块
搜索酶
上传 PDB
创建项目
查看最近项目
```

---

## 8.2 项目页

功能：

```text
查看项目基本信息
查看项目酶条目
查看实验数据
查看推荐历史
查看任务状态
```

---

## 8.3 酶详情页

功能：

```text
基本信息
来源物种
序列
结构
AlphaFold/PDB
文献数量
数据更新时间
```

---

## 8.4 性质数据页

功能：

```text
最适温度
最适 pH
比酶活
Km/kcat/kcat-Km
表达量
可溶性
选择性数据
原文献值排名
同条件分组排名
```

---

## 8.5 突变体知识页

功能：

```text
已报道突变体
突变前后性质变化
突变位点热图
文献证据
用户公开数据
```

---

## 8.6 MSA / 保守性页

功能：

```text
同源序列列表
MSA 浏览
保守性热图
位点保守性表格
导出结果
```

---

## 8.7 结构分析页

功能：

```text
PDB 上传
apo/complex 判断
链选择
配体选择
口袋残基
保守性映射
结构警告
```

---

## 8.8 突变设计页

功能：

```text
目标性质选择
推荐热点
推荐单点突变
推荐组合突变
Rosetta ddG 状态
风险解释
导出实验库
```

---

## 8.9 实验数据上传页

功能：

```text
上传 CSV/Excel
字段匹配
数据校验
权限设置
保存到项目
```

---

## 8.10 下一轮推荐页

功能：

```text
模型训练结果
模型性能
特征重要性
推荐突变体
探索/利用标签
导出 96 孔板布局
```

---

## 8.11 公开数据库页

功能：

```text
查看公开酶数据
查看公开突变体
查看公开实验数据
筛选
下载
引用
```

---

## 8.12 审核后台页

功能：

```text
查看公开申请
检查数据详情
批准公开
拒绝公开
填写审核意见
```

---

# 9. 非功能需求

## 9.1 性能

```text
普通查询响应时间 < 3 秒
本地缓存查询响应时间 < 2 秒
长任务必须异步执行
长任务状态可追踪
```

## 9.2 数据安全

```text
用户上传数据默认 private
private 数据不能被其他用户访问
公开数据必须审核
操作需要审计日志
```

## 9.3 可追溯性

所有科学数据必须保存：

```text
来源
文献
实验条件
单位
更新时间
审核状态
可见性
```

## 9.4 可扩展性

后续应支持：

```text
第三类酶
Level 3 相似性
MD 实际运行
MMPBSA 实际运行
全文文献挖掘
更多数据库接入
```

---

# 10. MVP 完成标准

MVP 完成后，用户应可以：

```text
搜索两类目标酶
查看本地或刷新后的酶数据
查看性质和突变体数据
查看两种排名
上传 apo 或 complex PDB
运行结构分析
运行 MSA 和保守性分析
获得突变推荐
提交 Rosetta ddG 任务
生成小型突变库
上传实验数据
申请公开数据
审核公开数据
训练项目模型
获得下一轮推荐
```

---

# 二、Codex 开发任务清单 / GitHub Issues

下面按 GitHub Issues 形式拆分。每个 issue 包含：

```text
标题
标签
优先级
任务说明
验收标准
```

---

# Epic 0：项目基础设施

---

## Issue 0.1：初始化 monorepo 项目结构

**Labels:** `setup`, `infrastructure`
**Priority:** P0

### 任务说明

创建项目基础结构：

```text
apps/web
apps/api
apps/worker
packages/shared
docker
docs
scripts
tests
```

### 验收标准

```text
仓库结构创建完成
README 中说明目录用途
前端、后端、worker 可以分别启动
```

---

## Issue 0.2：配置 Docker Compose 开发环境

**Labels:** `setup`, `docker`, `infrastructure`
**Priority:** P0

### 任务说明

配置以下服务：

```text
PostgreSQL
Redis
MinIO
FastAPI
Worker
Next.js
```

### 验收标准

```text
docker compose up 可以启动所有基础服务
PostgreSQL 可连接
Redis 可连接
MinIO 可访问
后端 health check 正常
前端页面可访问
```

---

## Issue 0.3：建立后端 FastAPI 基础应用

**Labels:** `backend`, `api`
**Priority:** P0

### 任务说明

实现：

```text
FastAPI app
health check endpoint
配置管理
日志系统
错误处理
CORS
```

### 验收标准

```text
GET /health 返回 ok
配置可通过环境变量读取
API 错误返回统一格式
```

---

## Issue 0.4：建立数据库连接和 Alembic 迁移

**Labels:** `backend`, `database`
**Priority:** P0

### 任务说明

配置：

```text
SQLAlchemy / SQLModel
PostgreSQL connection
Alembic migration
base model
created_at / updated_at
```

### 验收标准

```text
可以运行 alembic upgrade head
数据库表可以创建
测试数据库连接通过
```

---

## Issue 0.5：建立异步任务队列

**Labels:** `backend`, `worker`, `queue`
**Priority:** P0

### 任务说明

配置 Celery 或 RQ，用于：

```text
外部数据检索
MSA
Rosetta ddG
ML training
未来 MD/MMPBSA
```

### 验收标准

```text
worker 可以启动
可以提交测试任务
任务状态可查询
失败任务有错误信息
```

---

# Epic 1：核心数据模型

---

## Issue 1.1：实现用户、项目和权限基础模型

**Labels:** `database`, `auth`, `backend`
**Priority:** P0

### 任务说明

实现模型：

```text
User
Project
ProjectMember
```

### 验收标准

```text
用户可以创建项目
项目可以关联用户
项目数据有 owner 字段
```

---

## Issue 1.2：实现酶类模块和酶条目模型

**Labels:** `database`, `enzyme`
**Priority:** P0

### 任务说明

实现：

```text
EnzymeFamily
EnzymeEntry
ProteinSequence
```

酶类 enum：

```text
ANTHRAQUINONE_GLYCOSYLTRANSFERASE
MICROBIAL_TRANSGLUTAMINASE_MATURE
```

### 验收标准

```text
可以保存两类酶
可以保存成熟酶序列
MTGase 有 mature_sequence 字段
```

---

## Issue 1.3：实现结构、配体和底物模型

**Labels:** `database`, `structure`
**Priority:** P0

### 任务说明

实现：

```text
StructureEntry
LigandEntry
SubstrateEntry
```

### 验收标准

```text
结构可以关联酶
配体可以关联结构
底物可以关联酶类或实验记录
```

---

## Issue 1.4：实现性质、动力学和表达数据模型

**Labels:** `database`, `property`
**Priority:** P0

### 任务说明

实现：

```text
PropertyRecord
KineticRecord
ExpressionRecord
ExperimentCondition
```

必须包含：

```text
value_original
unit_original
value_standardized
unit_standardized
standardization_status
substrate
assay_temperature
assay_pH
buffer
method
reference_id
visibility
curation_status
```

### 验收标准

```text
可以保存原始单位
可以保存标准化单位
标准化失败时可以标记
每条记录有实验条件
```

---

## Issue 1.5：实现突变体和文献模型

**Labels:** `database`, `mutation`, `literature`
**Priority:** P0

### 任务说明

实现：

```text
MutationRecord
LiteratureReference
```

### 验收标准

```text
突变体可以关联 parent enzyme
突变体可以保存 mutation_string
突变体可以关联性质变化
文献可以关联性质和突变体
```

---

## Issue 1.6：实现用户实验数据、可见性和审核模型

**Labels:** `database`, `curation`, `privacy`
**Priority:** P0

### 任务说明

实现：

```text
UserExperiment
VisibilityRequest
CurationTask
AuditLog
```

### 验收标准

```text
实验数据默认 private
用户可以创建公开申请
审核员可以批准或拒绝
审核操作有日志
```

---

# Epic 2：搜索解析与缓存

---

## Issue 2.1：实现 query_resolver.py

**Labels:** `backend`, `search`
**Priority:** P0

### 任务说明

实现输入解析：

```text
detect_ec_number
detect_uniprot_id
detect_pdb_id
detect_enzyme_name
detect_organism
detect_enzyme_module
```

### 验收标准

```text
可以识别 EC 号
可以识别 UniProt ID
可以识别 PDB ID
可以识别两类酶模块
无法识别时返回明确错误或 low-confidence query
```

---

## Issue 2.2：实现 Level 1 精确匹配

**Labels:** `backend`, `search`, `cache`
**Priority:** P0

### 任务说明

Level 1 条件：

```text
UniProt ID 相同
PDB 映射 UniProt 相同
上传序列 identity >= 98%
上传结构链序列 identity >= 98%
```

### 验收标准

```text
相同 UniProt ID 可以命中本地酶
相同 PDB 映射可以命中本地酶
上传序列可以进行 identity 判断
```

---

## Issue 2.3：实现 Level 2 相似匹配

**Labels:** `backend`, `search`, `alignment`
**Priority:** P1

### 任务说明

Level 2 条件：

```text
同一酶类模块
sequence identity >= 40%
alignment coverage >= 70%
```

### 验收标准

```text
同类酶可以进行相似性匹配
返回 identity 和 coverage
低于阈值不命中
```

---

## Issue 2.4：实现 15 天缓存策略

**Labels:** `backend`, `cache`
**Priority:** P0

### 任务说明

实现按数据类型判断是否过期：

```text
sequence data
structure data
property data
mutation data
literature data
MSA/conservation profile
```

### 验收标准

```text
15 天内数据直接返回
超过 15 天触发刷新任务
可以部分刷新过期模块
```

---

# Epic 3：外部数据连接器

---

## Issue 3.1：实现 UniProt connector

**Labels:** `connector`, `uniprot`, `backend`
**Priority:** P0

### 任务说明

实现：

```text
search_by_keyword
search_by_ec
search_by_organism
fetch_entry
fetch_fasta
fetch_cross_references
```

### 验收标准

```text
可以通过酶名搜索 UniProt
可以通过 EC 搜索 UniProt
可以获取 fasta
可以保存 UniProt ID 和注释
测试使用 mock，不依赖真实 API
```

---

## Issue 3.2：实现 RCSB PDB connector

**Labels:** `connector`, `pdb`, `backend`
**Priority:** P0

### 任务说明

实现：

```text
search_by_uniprot
search_by_keyword
fetch_structure_metadata
download_pdb_or_cif
```

### 验收标准

```text
可以通过 UniProt 查找结构
可以获取 PDB 元数据
可以下载结构文件
可以保存结构到 MinIO
```

---

## Issue 3.3：实现 AlphaFold DB connector

**Labels:** `connector`, `alphafold`, `structure`
**Priority:** P1

### 任务说明

实现：

```text
fetch_model_by_uniprot
download_predicted_structure
store_confidence_metadata
```

### 验收标准

```text
可以根据 UniProt 获取 AlphaFold 模型
可以保存结构文件
可以保存置信度信息
```

---

## Issue 3.4：实现文献 metadata connector

**Labels:** `connector`, `literature`
**Priority:** P1

### 任务说明

实现：

```text
search_pubmed_metadata
search_by_enzyme_name
search_by_mutation_keyword
create_literature_reference
```

### 验收标准

```text
可以保存标题、作者、期刊、年份、DOI、摘要
可以关联酶条目
不需要 MVP 自动全文抽取
```

---

## Issue 3.5：实现 BRENDA/SABIO-RK 预留接口

**Labels:** `connector`, `placeholder`, `enzyme-data`
**Priority:** P2

### 任务说明

定义接口，不强制实现真实 API：

```text
fetch_opt_temperature
fetch_opt_pH
fetch_kinetic_parameters
fetch_mutants
```

### 验收标准

```text
存在接口定义
存在 mock adapter
后续可替换为真实数据源
```

---

# Epic 4：同源序列、MSA 和保守性

---

## Issue 4.1：实现同源序列收集 pipeline

**Labels:** `bioinformatics`, `homology`
**Priority:** P1

### 任务说明

实现：

```text
collect_homologs
filter_by_identity
filter_by_coverage
deduplicate_sequences
limit_max_sequences
```

默认参数：

```text
identity_min = 40%
identity_max = 95%
coverage_min = 70%
max_sequences = 500
```

### 验收标准

```text
可以输入 query sequence
可以输出过滤后的同源序列
返回 identity 和 coverage
```

---

## Issue 4.2：实现 MAFFT 运行封装

**Labels:** `bioinformatics`, `msa`, `worker`
**Priority:** P1

### 任务说明

实现异步 MAFFT 任务。

### 验收标准

```text
MSA 通过 worker 执行
可以保存 MSA 文件
失败时返回错误
```

---

## Issue 4.3：实现保守性评分

**Labels:** `bioinformatics`, `conservation`
**Priority:** P1

### 任务说明

计算：

```text
Shannon entropy
wildtype residue frequency
conservation category
```

### 验收标准

```text
每个位点有保守性分数
每个位点有 WT frequency
可以映射到 query sequence
```

---

## Issue 4.4：实现 MSA 和保守性前端页面

**Labels:** `frontend`, `msa`, `visualization`
**Priority:** P2

### 任务说明

页面展示：

```text
同源序列列表
MSA 简要视图
保守性热图
位点保守性表
```

### 验收标准

```text
用户可以查看 MSA
用户可以下载保守性结果
用户可以按保守性筛选位点
```

---

# Epic 5：PDB 上传和结构分析

---

## Issue 5.1：实现 PDB 文件上传

**Labels:** `backend`, `structure`, `upload`
**Priority:** P0

### 任务说明

支持上传：

```text
.pdb
.cif
```

保存到 MinIO，并记录到 StructureEntry。

### 验收标准

```text
用户可以上传结构文件
文件保存成功
数据库记录结构文件路径
```

---

## Issue 5.2：实现 PDB parser

**Labels:** `backend`, `structure`, `parser`
**Priority:** P0

### 任务说明

实现：

```text
parse_chains
extract_sequences
detect_hetero_ligands
detect_metal_ions
classify_apo_or_complex
```

### 验收标准

```text
可以识别链
可以提取序列
可以识别配体
可以判断 apo/complex
```

---

## Issue 5.3：实现配体邻近残基分析

**Labels:** `backend`, `structure`, `ligand`
**Priority:** P1

### 任务说明

计算：

```text
4 Å 邻近残基
6 Å 邻近残基
8 Å 邻近残基
ligand distance matrix
```

### 验收标准

```text
complex PDB 可以输出邻近残基表
每个残基包含链、编号、氨基酸、距离
```

---

## Issue 5.4：实现结构位点到序列位点映射

**Labels:** `backend`, `structure`, `mapping`
**Priority:** P1

### 任务说明

处理：

```text
PDB residue number
insertion code
missing residues
sequence position
```

### 验收标准

```text
PDB 编号可以映射到序列编号
缺失残基有 warning
映射质量有评分
```

---

## Issue 5.5：实现结构分析前端页面

**Labels:** `frontend`, `structure`
**Priority:** P2

### 任务说明

展示：

```text
结构摘要
链信息
配体信息
邻近残基
结构警告
3D 可视化
```

### 验收标准

```text
用户可以查看上传结构
用户可以选择链
用户可以查看配体和邻近残基
```

---

# Epic 6：性质数据和排名

---

## Issue 6.1：实现性质数据录入和查询 API

**Labels:** `backend`, `property`
**Priority:** P0

### 任务说明

支持保存和查询：

```text
最适温度
最适 pH
比酶活
Km
kcat
kcat/Km
表达量
可溶性
产物选择性
对映选择性
```

### 验收标准

```text
性质记录可以保存
性质记录可以按酶查询
性质记录包含实验条件和来源
```

---

## Issue 6.2：实现单位标准化服务

**Labels:** `backend`, `property`, `unit`
**Priority:** P1

### 任务说明

实现：

```text
unit_standardization
standardization_status
failed/not_applicable 标记
```

### 验收标准

```text
可转换单位被标准化
不可转换单位保留原值
不确定时不强行转换
```

---

## Issue 6.3：实现原文献值排名

**Labels:** `backend`, `ranking`
**Priority:** P1

### 任务说明

实现：

```text
reported_value_ranking
```

### 验收标准

```text
可以按原始值排序
保留原始单位
返回实验条件
返回比较警告
```

---

## Issue 6.4：实现同条件分组排名

**Labels:** `backend`, `ranking`
**Priority:** P1

### 任务说明

分组字段：

```text
reference_id
substrate
assay_temperature
assay_pH
unit
method
```

### 验收标准

```text
可以按条件分组
组内可以排序
跨组不混合比较
```

---

## Issue 6.5：实现性质数据看板

**Labels:** `frontend`, `dashboard`, `property`
**Priority:** P2

### 任务说明

展示：

```text
最适温度分布
最适 pH 分布
比酶活排名
Km/kcat 图
表达量数据
选择性数据
```

### 验收标准

```text
用户可以筛选性质类型
用户可以切换两种排名
用户可以查看每条数据来源
```

---

# Epic 7：突变体知识库

---

## Issue 7.1：实现突变字符串解析器

**Labels:** `backend`, `mutation`, `parser`
**Priority:** P0

### 任务说明

支持格式：

```text
A123V
A123V/G145D
A123V-G145D
```

### 验收标准

```text
可以解析单点突变
可以解析多点突变
可以校验 WT 氨基酸是否匹配 parent sequence
错误格式返回明确提示
```

---

## Issue 7.2：实现突变体数据查询 API

**Labels:** `backend`, `mutation`
**Priority:** P1

### 任务说明

支持：

```text
按酶查询
按位点查询
按性质变化查询
按来源查询
按 public/private 查询
```

### 验收标准

```text
可以查看已报道突变体
可以筛选有益突变
可以查看突变证据
```

---

## Issue 7.3：实现突变体知识前端页面

**Labels:** `frontend`, `mutation`
**Priority:** P2

### 任务说明

展示：

```text
突变体表
突变位点热图
突变前后变化
文献证据
```

### 验收标准

```text
用户可以查看突变体
用户可以按性质筛选
用户可以查看文献来源
```

---

# Epic 8：突变推荐

---

## Issue 8.1：实现 residue feature builder

**Labels:** `backend`, `mutation-design`
**Priority:** P1

### 任务说明

为每个位点构建特征：

```text
position
wildtype_aa
conservation_score
wildtype_frequency
secondary_structure
solvent_accessibility
distance_to_ligand
distance_to_predicted_pocket
reported_mutation_count
reported_beneficial_mutation_count
rosetta_ddg
solubility_risk
```

### 验收标准

```text
每个位点可以生成 feature record
缺失特征可以标记 unavailable
```

---

## Issue 8.2：实现通用突变评分引擎

**Labels:** `backend`, `mutation-design`, `scoring`
**Priority:** P1

### 任务说明

实现：

```text
calculate_general_score
generate_score_components
generate_risk_summary
```

### 验收标准

```text
每个候选突变有总分
每个候选突变有分项评分
每个候选突变有风险解释
```

---

## Issue 8.3：实现蒽醌糖基转移酶特异评分

**Labels:** `backend`, `mutation-design`, `glycosyltransferase`
**Priority:** P1

### 任务说明

实现特异评分：

```text
anthraquinone_binding_region_score
UDP_sugar_region_score
product_selectivity_score
activity_score
solubility_score
stability_score
```

### 验收标准

```text
糖基转移酶推荐结果包含模块特异解释
complex PDB 可以利用底物距离信息
无底物时显示低置信度提示
```

---

## Issue 8.4：实现 MTGase 特异评分

**Labels:** `backend`, `mutation-design`, `mtgase`
**Priority:** P1

### 任务说明

实现特异评分：

```text
thermostability_score
opt_temperature_score
opt_pH_score
activity_retention_score
surface_charge_score
solubility_score
```

### 验收标准

```text
MTGase 推荐结果聚焦 mature enzyme
不推荐 pro-region 突变
推荐结果包含热稳定性和活性保持解释
```

---

## Issue 8.5：实现突变候选生成器

**Labels:** `backend`, `mutation-design`
**Priority:** P1

### 任务说明

实现：

```text
generate_single_mutation_candidates
filter_high_risk_mutations
target_property_specific_filter
rank_candidates
```

### 验收标准

```text
可以生成单点突变候选
可以过滤高风险突变
可以按目标性质排序
```

---

## Issue 8.6：实现突变推荐前端页面

**Labels:** `frontend`, `mutation-design`
**Priority:** P2

### 任务说明

展示：

```text
目标性质选择
热点位点
推荐突变
分项评分
推荐理由
风险提示
```

### 验收标准

```text
用户可以选择目标性质
用户可以查看推荐结果
用户可以导出推荐表
```

---

# Epic 9：Rosetta ddG

---

## Issue 9.1：实现 Rosetta ddG 任务模型

**Labels:** `backend`, `rosetta`, `database`
**Priority:** P1

### 任务说明

实现：

```text
RosettaJob
RosettaResult
```

状态：

```text
queued
running
finished
failed
cancelled
```

### 验收标准

```text
可以创建 Rosetta job
可以保存 job 状态
可以保存 ddG 结果
```

---

## Issue 9.2：实现 Rosetta 输入准备

**Labels:** `backend`, `rosetta`
**Priority:** P1

### 任务说明

实现：

```text
prepare_structure
clean_pdb
generate_mutation_file
validate_mutation_against_structure
```

### 验收标准

```text
可以生成 Rosetta 输入文件
结构缺失时返回 warning
突变无法映射时返回错误
```

---

## Issue 9.3：实现 Rosetta runner

**Labels:** `worker`, `rosetta`
**Priority:** P1

### 任务说明

实现异步运行：

```text
submit_rosetta_job
parse_rosetta_output
store_results
handle_errors
retry_failed_jobs
```

### 验收标准

```text
Rosetta 不在 API 请求中同步运行
worker 可以执行任务
结果可以回写数据库
```

---

## Issue 9.4：实现 Rosetta 任务前端

**Labels:** `frontend`, `rosetta`
**Priority:** P2

### 任务说明

展示：

```text
任务列表
任务状态
突变
ddG
错误信息
```

### 验收标准

```text
用户可以查看 Rosetta 任务状态
任务完成后可查看结果
失败任务显示错误原因
```

---

# Epic 10：MD / MMPBSA 占位模块

---

## Issue 10.1：实现 SimulationJob schema

**Labels:** `backend`, `simulation`, `placeholder`
**Priority:** P2

### 任务说明

实现：

```text
SimulationJob
simulation_type: MD / MMPBSA
status: planned / queued / running / finished / failed
```

### 验收标准

```text
可以创建占位任务记录
不会实际运行 MD/MMPBSA
```

---

## Issue 10.2：实现 MD/MMPBSA 前端占位卡片

**Labels:** `frontend`, `simulation`, `placeholder`
**Priority:** P3

### 任务说明

显示：

```text
MD simulation: reserved module
MMPBSA: reserved module
```

### 验收标准

```text
complex PDB 页面可以看到 MMPBSA 预留模块
apo PDB 页面可以看到 MD 预留模块
```

---

# Epic 11：组合突变和实验库设计

---

## Issue 11.1：实现组合突变生成器

**Labels:** `backend`, `library-design`
**Priority:** P1

### 任务说明

实现：

```text
generate_double_mutants
generate_multi_mutants
avoid_same_position_conflict
avoid_high_risk_combinations
```

### 验收标准

```text
可以生成双点突变
不会组合相同位点冲突突变
高风险组合被过滤或降权
```

---

## Issue 11.2：实现组合突变评分

**Labels:** `backend`, `library-design`, `scoring`
**Priority:** P1

### 任务说明

实现：

```text
score_combinations
penalize_spatial_conflict
reward_complementary_goals
```

### 验收标准

```text
组合突变有总分
组合突变有推荐理由
组合突变有风险提示
```

---

## Issue 11.3：实现 96 孔板布局生成

**Labels:** `backend`, `library-design`, `export`
**Priority:** P1

### 任务说明

生成：

```text
96-well plate layout
variant_id
mutation_string
control wells
blank wells
```

### 验收标准

```text
可以生成 96 孔板布局
包含 WT control
包含 blank control
可以导出 CSV/Excel
```

---

## Issue 11.4：实现实验库设计前端

**Labels:** `frontend`, `library-design`
**Priority:** P2

### 任务说明

展示：

```text
单点推荐
组合推荐
实验库规模选择
孔板布局
导出按钮
```

### 验收标准

```text
用户可以选择 24/48/96/384 规模
用户可以下载实验库
```

---

# Epic 12：实验数据上传

---

## Issue 12.1：实现 CSV/Excel 解析器

**Labels:** `backend`, `experiment`, `upload`
**Priority:** P0

### 任务说明

支持：

```text
.csv
.xlsx
```

### 验收标准

```text
可以读取 CSV
可以读取 Excel
可以返回字段列表
```

---

## Issue 12.2：实现实验数据字段校验

**Labels:** `backend`, `experiment`, `validation`
**Priority:** P0

### 任务说明

校验：

```text
mutation_string
sequence
specific_activity
relative_activity
opt_temperature
opt_pH
substrate
assay_temperature
assay_pH
visibility
```

### 验收标准

```text
缺失必要字段时提示
格式错误时提示
visibility 默认为 private
```

---

## Issue 12.3：实现突变映射到 parent sequence

**Labels:** `backend`, `experiment`, `mutation`
**Priority:** P1

### 任务说明

实现：

```text
validate_mutation_against_parent
map_mutation_to_mature_sequence
```

### 验收标准

```text
突变编号可以映射到 parent mature sequence
WT 氨基酸不匹配时提示错误
```

---

## Issue 12.4：实现实验数据上传前端

**Labels:** `frontend`, `experiment`, `upload`
**Priority:** P2

### 任务说明

页面包含：

```text
文件上传
字段预览
错误提示
visibility 设置
提交按钮
```

### 验收标准

```text
用户可以上传文件
用户可以查看校验结果
用户可以保存实验数据
```

---

# Epic 13：数据权限和审核

---

## Issue 13.1：实现 private/public 权限控制

**Labels:** `backend`, `privacy`, `auth`
**Priority:** P0

### 任务说明

规则：

```text
private 数据仅项目用户可见
public 数据所有用户可见
```

### 验收标准

```text
非项目用户不能访问 private 数据
public 数据可以被公开数据库查询
```

---

## Issue 13.2：实现公开申请流程

**Labels:** `backend`, `curation`
**Priority:** P1

### 任务说明

实现：

```text
create_visibility_request
submit_for_review
approve_publication
reject_publication
```

### 验收标准

```text
用户可以申请公开
审核员可以批准
审核员可以拒绝
拒绝需要填写原因
```

---

## Issue 13.3：实现审核后台 API

**Labels:** `backend`, `curation`
**Priority:** P1

### 任务说明

提供：

```text
list_pending_requests
get_request_detail
approve
reject
```

### 验收标准

```text
审核员可以查看待审核数据
审核员可以查看实验条件和来源
审核操作写入 AuditLog
```

---

## Issue 13.4：实现审核后台前端

**Labels:** `frontend`, `curation`
**Priority:** P2

### 任务说明

页面包含：

```text
待审核列表
数据详情
通过按钮
拒绝按钮
审核意见
```

### 验收标准

```text
审核员可以完成公开审核
审核结果可追踪
```

---

# Epic 14：主动学习和下一轮推荐

---

## Issue 14.1：实现 variant feature builder

**Labels:** `backend`, `ml`, `features`
**Priority:** P1

### 任务说明

构建特征：

```text
mutation one-hot
氨基酸理化性质
保守性
Rosetta ddG
距离配体/口袋
已报道突变证据
酶类特异特征
```

### 验收标准

```text
每个 variant 可以生成特征向量
缺失特征可以填充或标记
```

---

## Issue 14.2：实现模型训练服务

**Labels:** `backend`, `ml`
**Priority:** P1

### 任务说明

支持：

```text
Random Forest
XGBoost / LightGBM
Gaussian Process
```

### 验收标准

```text
可以训练项目模型
可以保存模型性能
可以保存模型文件
```

---

## Issue 14.3：实现不确定性估计

**Labels:** `backend`, `ml`, `active-learning`
**Priority:** P1

### 任务说明

实现：

```text
prediction uncertainty
exploration score
exploitation score
```

### 验收标准

```text
每个推荐候选有预测值
每个推荐候选有不确定性
可以区分 exploration/exploitation
```

---

## Issue 14.4：实现下一轮推荐服务

**Labels:** `backend`, `ml`, `recommendation`
**Priority:** P1

### 任务说明

实现：

```text
generate_candidate_pool
rank_candidates
diversity_filter
recommend_next_round
```

### 验收标准

```text
可以推荐下一轮突变
可以设置推荐数量
可以导出推荐库
```

---

## Issue 14.5：实现下一轮推荐前端

**Labels:** `frontend`, `ml`, `recommendation`
**Priority:** P2

### 任务说明

展示：

```text
模型性能
特征重要性
推荐突变
预测值
不确定性
exploration/exploitation 标签
导出按钮
```

### 验收标准

```text
用户可以查看训练结果
用户可以查看下一轮推荐
用户可以下载推荐实验表
```

---

# Epic 15：公开数据库

---

## Issue 15.1：实现公开数据查询 API

**Labels:** `backend`, `public-database`
**Priority:** P2

### 任务说明

支持查询：

```text
公开酶条目
公开性质数据
公开突变体
公开实验数据
```

### 验收标准

```text
只返回 public 数据
支持按酶类、性质、来源筛选
```

---

## Issue 15.2：实现公开数据库前端页面

**Labels:** `frontend`, `public-database`
**Priority:** P2

### 任务说明

展示：

```text
公开酶数据
公开突变体
公开实验数据
筛选器
下载按钮
引用信息
```

### 验收标准

```text
用户可以浏览公开数据
用户可以筛选和下载
private 数据不会出现
```

---

# Epic 16：文档和测试

---

## Issue 16.1：编写 README.md

**Labels:** `docs`
**Priority:** P0

### 任务说明

说明：

```text
项目简介
技术栈
本地启动
目录结构
MVP 范围
```

### 验收标准

```text
新开发者可以按 README 启动项目
```

---

## Issue 16.2：编写 docs/architecture.md

**Labels:** `docs`, `architecture`
**Priority:** P1

### 任务说明

说明：

```text
系统架构
服务边界
数据流
任务队列
文件存储
```

### 验收标准

```text
文档清楚描述前端、后端、worker、数据库关系
```

---

## Issue 16.3：编写 docs/data_model.md

**Labels:** `docs`, `database`
**Priority:** P1

### 任务说明

说明：

```text
核心数据表
字段含义
表关系
可见性和审核逻辑
```

### 验收标准

```text
开发者可以根据文档理解数据库设计
```

---

## Issue 16.4：编写 docs/ranking_rules.md

**Labels:** `docs`, `ranking`
**Priority:** P1

### 任务说明

说明：

```text
Reported Value Ranking
Condition-grouped Ranking
单位标准化规则
不可比数据警告
```

### 验收标准

```text
排名逻辑可被复现
```

---

## Issue 16.5：编写 docs/mutation_recommendation.md

**Labels:** `docs`, `mutation-design`
**Priority:** P1

### 任务说明

说明：

```text
通用评分因子
GT 特异评分
MTGase 特异评分
风险提示逻辑
```

### 验收标准

```text
突变推荐逻辑有文档说明
```

---

## Issue 16.6：补充自动化测试

**Labels:** `test`, `quality`
**Priority:** P1

### 任务说明

至少覆盖：

```text
query resolver
cache manager
mutation parser
ranking service
PDB parser
experiment upload validation
visibility control
```

### 验收标准

```text
核心服务有单元测试
CI 可以运行测试
外部 API 使用 mock
```

---

# 三、推荐开发里程碑

## Milestone 1：基础平台和数据模型

包含：

```text
Epic 0
Epic 1
Epic 2
```

目标：

```text
项目可以启动
数据库结构完成
搜索解析和缓存策略完成
```

---

## Milestone 2：数据接入和知识库

包含：

```text
Epic 3
Epic 6
Epic 7
```

目标：

```text
可以搜索酶
可以保存性质数据
可以查看突变体
可以生成两种排名
```

---

## Milestone 3：结构和保守性分析

包含：

```text
Epic 4
Epic 5
```

目标：

```text
可以上传 PDB
可以判断 apo/complex
可以运行 MSA
可以展示保守性
```

---

## Milestone 4：突变推荐和实验库

包含：

```text
Epic 8
Epic 9
Epic 10
Epic 11
```

目标：

```text
可以推荐突变
可以提交 Rosetta ddG
可以生成组合突变和实验库
```

---

## Milestone 5：实验反馈和闭环推荐

包含：

```text
Epic 12
Epic 13
Epic 14
Epic 15
```

目标：

```text
可以上传实验数据
可以审核公开数据
可以训练模型
可以推荐下一轮突变
可以浏览公开数据库
```

---

# 四、第一版 MVP 优先级总结

## P0 必须先做

```text
项目骨架
数据库模型
搜索解析
缓存策略
UniProt connector
RCSB connector
PDB 上传
性质数据模型
突变字符串解析
实验数据上传
private/public 权限
```

## P1 核心功能

```text
AlphaFold connector
MSA
保守性分析
两种排名
结构位点映射
突变推荐
Rosetta ddG 队列
组合突变设计
主动学习模型
审核流程
```

## P2 展示和增强

```text
性质看板
突变体热图
结构可视化
公开数据库页面
审核后台前端
下一轮推荐页面
文档完善
```

## P3 后续增强

```text
MD 实际运行
MMPBSA 实际运行
全文文献挖掘
Level 3 相似性
更多酶类模块
复杂团队权限
```


