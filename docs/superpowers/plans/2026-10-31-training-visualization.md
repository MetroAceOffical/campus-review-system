# 训练与评价图表扩充 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans in the current conversation. Steps use checkbox syntax.

**Goal:** 将训练、资源、评价、版本及调参联动扩充为30种真实数据图表视图。
**Architecture:** 复用ECharts、事件/SSE、模型版本和预测工件；神经训练增加旁路采集，Java流式聚合验证/测试结果，前端页签懒挂载。
**Tech Stack:** 现有Vue/TS/ECharts、Java21/Spring、Python/Torch/psutil，无新依赖。
**Spec:** docs/superpowers/specs/2026-10-31-training-visualization-design.md

## Global Constraints
- 直角、紧凑、无图表导出，不恢复正式生成或自动调参训练；无数据/轮数缩减。
- 训练ADMIN；查看/评价沿用原角色。旧模型、配置、报告、稿件保持。
- 定向验证；完成阶段记录已完成/剩余/耗时并同步GitHub连接器分支codex/final-workbench-20261028。
- 原工作区.git不可用且metadata只读，延用已授权运行工作区，不重建git；远端基线eb8393c76af0b8b46f49fd33d2aa1ad59de9318b/tree2d8e44b688a5bc42fd9fa22b7f8b64b5a9e12d24，同步前重新查HEAD。

## Review Focus
1. SVM间隔/概率、空分箱/单类别不能混淆，测试集不得成为可应用的阈值调参入口。
2. 统计必须读取完整且哈希匹配的授权工件，不能将分页首批当全量。
3. 新日志不可改变优化/累积/随机状态，旧适配器哈希不能失效。
4. 不同划分、family、初始化不能合成误导性调参或规模曲线。
5. 异步切换任务与隐藏页签不得串数据、丢主题或产生零宽图。

## Task 1: 真实训练采集与训练过程/资源图
Files: 新training_telemetry.py、training-charts.ts；改training.py/training_resume.py/api/training.ts/TrainingProgress.vue/ExperimentChart.vue。
Interfaces: TRAINING事件新增elapsedSeconds/batchSeconds/samplesPerSecond/gradientNorm/hostRssBytes/cpuPercent/cudaAllocatedBytes/cudaReservedBytes；EPOCH新增trainMetrics/validationLoss/trainSeconds/validationSeconds/checkpointSeconds；新训练manifest新增validationDataSha256/validation-predictions.jsonl。
- [x] RED：一个真实小型Torch定向检查证明采集有值、有限、每轮记录；梯度步数/重载与既有CNN续训检查保持。
- [x] 加入实际Web神经路径采集、保存验证预测与度量身份，不改已有工件。
- [x] 12过程/资源视图、页签懒挂载及ECharts箱线/雷达/桑基/平行坐标注册；主题/缩放/无导出。
- [x] GREEN：定向检查、类型/Vite，记录阶段进度并同步。

## Task 2: 完整评价统计与8种评价视图
Files: 新TrainingAnalyticsService/Controller/Test、PredictionAnalysis.vue、evaluation-charts.ts；改TrainingService、ModelView、TrainingProgress、API。
Interfaces: GET /api/workbench/training/runs/{id}/analytics 返回partition/count/scoreType/histogram/reliability/lengthErrors/thresholdSweep/metrics，工件SHA有界缓存；TRAIN为validation，EVALUATE为test，后者thresholdSweep为空。
- [x] RED：同一聚合检查覆盖边界概率/空分箱/SVM/验证与测试阈值差别；工件读取沿用权限、目录和SHA核验。
- [x] 实现流式完整预测聚合及API；有标签预测绘图，无标签批量预测保留原展示。
- [x] 接入数量/归一化矩阵、ROC/PR、分布、验证阈值、可靠性、长度错误；与分页错误样本联动。
- [x] GREEN：定向Java/Vitest和构建，真实旧评价读取，记录同步。

## Task 3: 模型、父子、调参对比10种视图
Files: 改ModelComparison/ParentModelComparison/ModelView，新ExperimentAnalysis.vue/experiment-charts.ts及定向检查；必要增加同条件模型历史查询API。
Interfaces: 对比组按输入SHA/划分SHA；规模曲线按验证SHA+family+参数+初始化身份分组。父子图使用已完成共同评价及全量improved/regressed统计。
- [x] RED：前端纯聚合检查跨划分拒并、缺失不是零、同条件规模曲线和父子总数。
- [x] 多模型4图、父子2图、调参4图，保留全部历史记录分页，不自动创建训练。
- [x] GREEN：目标检查、真实已训练模型/父子共同评价页面走查；缺数据项显示简短操作引导。

## Task 4: 最终部署、复核与交付
- [x] 检查影响范围，空闲打包部署，已授权admin/reviewer本机恢复登录。
- [x] 实际页面核对历史训练、评价、父子和调参页签，保留截图；一次独立只读复核、集中修正重要项。
- [x] 更新当前进度、图表数据来源与本轮实际证据，GitHub逐blob回读和最终HEAD校验；新采集尚无历史值的事实如实记录。

实际完成记录：3轮CUDA同参数联调b1a6d6f6、原48输入/24训练/12验证；没有自动参数搜索或正式生成。定向Java8、Python2、前端6项通过，最终实况以当前进度和阶段JSON为准。原计时诊断cd347e92保留；Windows QPC计时、MySQL浮点身份判定及一次复核6项已修正。
