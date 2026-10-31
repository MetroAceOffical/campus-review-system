# 任务工作区、续训到实际审核 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 交付紧凑统一、可恢复的任务式前端，真实的已完成神经模型继续训练、兼容BERT到整篇审核发布、全文对照及当前配置复检。

**Architecture:** 复用现有数据/任务/检测服务，增加用户流程记录与模型版本关联。统一工作区绑定实际对象身份和运行状态；继续训练与断点恢复分别实现；BERT评分适配接入已有检索/对齐/聚合链路。

**Tech Stack:** 现有Vue/TypeScript/Element Plus/ECharts、Java21/Spring/JDBC/MySQL3308、Python/Torch/Transformers，不新增依赖。

**Spec:** `docs/superpowers/specs/2026-10-31-task-workspace-and-review-design.md`

## Global Constraints

- 直角、现有品牌/色彩；减少重复按钮和大留白；无图表导出、无免责声明式堆字。
- 训练仅管理员，审核员保留数据/入库；创作者无训练权限。所有记录列表保留分页/页码输入/自定义数量。
- 原报告、配置、权重和用户稿件保留；新检查/新模型存新版本；不擅自作审核决定。
- 正式样本准备保持暂停；不缩减既定正式数据/轮数；不装新环境或新依赖。
- 定向验证，不跑繁复全量回归。阶段完成说明实际完成/剩余/预计耗时并同步GitHub。
- 用户已明确“按这份设计开始实施”；本计划沿用本对话直接执行，不重复请求实施授权。

## Review Focus

1. 另一个账号/另一个浏览器页签不能污染或读取当前用户流程；并发更新返回冲突，不无声覆盖。
2. 一个数据版本的别的历史模型/评价不能冒充本次流程完成；只绑定具体任务身份。
3. 新数据续训不得把父模型的验证/测试材料纳入训练；重载必须证明继承父权重并实际更新。
4. 当前配置复检保留原始快照、旧结果/决定；新任务执行中不得混用其他发布配置。
5. 语义/局部改写的主要参数来自有效证据；重复窗口、旧参考版本及正确引用不能凑告警数量。

## Task 1: 持久化用户流程与阶段身份

Files: 新增`010_workbench_flow.sql`、`WorkbenchFlowService.java`/`WorkbenchFlowController.java`、`api/flows.ts`、`flow-navigation.ts`、`tests/flow-navigation.spec.ts`；修改`workflow-context.ts`。

Interfaces: `/api/workbench/flows` POST `{requestId,kind,name?}`/分页GET；`/flows/{id}` GET/PATCH `{revision,context}`。kind=`UPLOAD|TRAIN|CONTINUE|LIBRARY`；context为dataset/version/preparation/trainingRun/evaluationRun/model/parentModel/import身份，变更数据时清空不兼容下游。服务核验角色、创建者及引用对象关系，revision冲突409。

- [x] RED：单个前端检查覆盖流程目标、未准备阶段不可跳跃、别的历史训练不使本次完成；一个服务定向检查覆盖成员拒绝/审核员训练拒绝/错误绑定/创建者及revision。
- [x] 实现表和API；复用DatasetService及TrainingService对象验证，不建设通用流程引擎。
- [x] 实现`flowSteps(flow,detail)`及`flowDestination(flow,step)`；状态取实际绑定对象。
- [x] GREEN：定向Vitest及Java检查通过，旧数据服务接口保持。

## Task 2: 统一任务工作区、首页与紧凑样式

Files: `WorkflowNavigator.vue`改为固定流程带；新增`WorkflowList.vue`及`styles/density.css`；修改Home/AppLayout/router、数据/训练/模型/入库/发布页面、TextSourceEvidence。

Interfaces: Task1的flowId通过`?flow=`传递；旧记录可独立打开；首页创建流程，近期流程可恢复。阶段操作只在一个统一操作区；流程节点定位不重复“下一步”按钮。

- [x] 实现首页四任务入口（审核员仅授权项目）、流程分页恢复及旧链接兼容。
- [x] 路由同步当前数据/运行/模型身份，刷新/后退/切换账号恢复正确对象；上下文更新失败保留可重试状态。
- [x] 流程带始终在同一位置，数据页移除重复流程图；取消当前全局多个返回/下一步按钮，正文内部链接统一动作样式。
- [x] 收紧面板/表单/图表高度，按任务页签展示图表；语义/字面主要参数只展示有依据的非零指标，字面三个零值只在折叠详情。
- [x] 定向检查+类型构建，真实页面验证创建/恢复/返回/身份；空闲时部署、更新阶段文档和GitHub。

## Task 3: 已完成神经模型继续训练与逻辑模型版本

Files: 新增模型lineage迁移、`training_warmstart.py`及定向检查；修改TrainingService/Worker、`workbench_training.py`、training API/训练及模型页。

Interfaces: TRAIN新增`parentModelId`与`trainingMode=CONTINUE|FRESH`，原`resumeRunId`仍表示原配置断点恢复。版本保存logicalModelId、parentModelId、versionNumber、工件/编码器身份。CNN/BiLSTM/BERT继承父权重，LR/SVM/RF完整重新拟合并明确命名。

- [x] RED→GREEN：小型真实Torch检查父权重继承、梯度更新、重载一致；错误架构/测试泄漏拒绝。复用原冻结划分的来源/文本身份检查。
- [x] 继续训练允许新增轮数/学习率/合格数据，CNN词表兼容或可追溯扩充，BERT沿用兼容tokenizer；保存独立工件，不覆盖父版本。
- [x] 同一逻辑模型显示版本链；训练流程选择父模型、比较同一隔离评价集；原模型迁为首版本。
- [x] 使用现有演示数据进行一次真实神经续训并记录权重变化，阶段部署/记录/同步。

## Task 4: 兼容BERT到整篇审核发布

Files: `campus_detection/models.py`及配置装载模块、新的web BERT适配/校准文件，ReleaseService/Worker与发布前端，相关Python检查。

Interfaces: 正文TEXT_REUSE新增兼容网页BERT模式，绑定modelVersion/artifactSha/tokenizer/adapter/calibration、检索featureSpaceId。保留CURRENT/LEGACY/CAMPUS_V3。实际加载与身份核验通过才能READY/启用。

- [x] RED→GREEN：注册BERT分数进入实际对齐/聚合、错误架构/标签/哈希拒绝；原配置仍可回放。
- [x] 用现有隔离开发材料做校准及正常稿/改写对照，生成版本化配置；不拿测试集调阈值，不以句对F1替代整篇成绩。
- [x] 发布和回退选择实际已加载版本，任务绑定不可变配置；同稿复检确认工件身份，记录真实结果。

## Task 5: 全文审核、当前配置复检与证据结论

Files: 证据绑定的来源版本读取接口；InspectionService/Worker配置固定及响应元数据；ReviewDetailView/TextEvidence/TextSourceEvidence、共用稿件检查区及位置高亮工具。

Interfaces: source读取同时绑定report/check、sourceWorkId、sourceRevisionId并验证证据身份；当前复检复用`POST /submissions/{id}/checks`的CONTENT，从送审快照生成新记录并固定配置。报告选择器区分原送审/复检结果。

- [x] RED→GREEN：来源全文为证据当时版本、非证据来源不可读取；新复检不改变原报告/决定。
- [x] 左送审全文、右来源全文、紧凑结论/证据列表，片段点击双侧定位；移除旧重复刷新/下一步入口。
- [x] 统一疑似复用、已引用、相近片段状态；核验强匹配与多处去重有效片段聚合，复用R01/正常稿对照，仅确有漏检再改聚合。
- [x] 图片/OCR/语法/图文记录仍绑定当前稿件；已存在结果切换不重录输入，未执行项目不显示完成。

## Task 6: 其他页面统一与完整演练

Files: 剩余角色首页/系统/参考/稿件/来源/发布阅读页面及共享样式、进度与证据文档。

- [x] 清理其余重复或无作用按钮、链接式动作，保留实际列表CRUD/筛选/分页；收紧编辑区滚动和页面布局。
- [x] 用既有演示材料真实核对上传→评估→清洗→入库，以及BERT续训→共同评价→登记→发布→既有不可变送审稿复检→回退；权限及历史身份正确，不代作审核决定。
- [ ] 全新创作者稿件编辑→送审→人工处理的录制前演练留给用户；本轮未读取创作者凭据或修改其稿件。
- [x] 只运行受影响检查、最终类型构建/打包及真实页面核对，一次独立只读复核后处理重要发现。
- [x] 更新实际状态、剩余项、耗时与精确GitHub回读回执；不能宣称未完成的正式校园训练/独立效果验收完成。

## 最终实际记录

2026-10-31：阶段1证据见task-workspace-stage1-20261031.json；阶段2/3证据记录新旧审核配置、共同评价、历史报告和参考入库。正式生成保持暂停。新校准开发集12/12来源、正常对照0/4；32真实新闻提示23/32，尚未独立判读，因此默认配置已恢复，不宣称总体效果提升。Java10项、Python4项及前端13项定向通过；一次独立只读复核的8项已修正，不再安排重复全分支复核。
