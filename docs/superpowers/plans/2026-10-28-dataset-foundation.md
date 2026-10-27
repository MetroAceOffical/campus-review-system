# 数据中心实施计划：解析、质量与清洗

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans逐任务实施，先RED再GREEN；持续更新执行账本。

**Goal:** 为已批准的期末方案提供可供Web任务调用的批量CSV/JSONL解析、真实质量指标、可追溯清洗版本与实际事件。

**Architecture:** 复用Python标准库，独立campus_workbench包与CLI；原文件只读、版本新目录写入。下一阶段Java持久任务调用同一CLI，前端读取真实事件和报告。

**Tech Stack:** 现有Python环境/标准库；随后Spring Boot/JdbcTemplate/MySQL和Vue/Element Plus/ECharts。

**Spec:** ../../期末重构完整计划-2026-10-27.md；../../检测效果提升与前端展示优化方案-2026-10-27.md；../../片段引用与来源核对设计-2026-10-27.md。

## Global Constraints

- 用户2026-10-28明确“开始实施”，解除编码暂停；原数据规模和评价边界不减，新增环境仍先请示。
- 以南京传媒学院不同部门为场景，数据中的学校/部门仅为材料来源，归属由Java账号授权。
- 输入UTF-8/BOM、CSV多行或JSONL，50MiB/100000条上限；不静默截断。
- 所有阶段/指标来自实际处理；保留原文件、旧配置/报告/权重。版本带SHA，训练尚未执行不得标完成。
- 本地.git现为无提交、无remote的空初始化记录，无法建工作树；不重置/修改它，不移动运行目录。使用源码快照和GitHub连接器功能分支保护旧版。
- GitHub基线0a3ed32280b163a2be5db4bcb5da124b17135b3f，分支codex/final-workbench-20261028；仅验证后的源码和文档上传。

## Review Focus

- CSV多行/畸形引号与JSONL坏行：行号准确，可恢复坏行有明细，不可恢复边界明确失败。
- 反向句对冲突、同文负例和重复ID：隔离异常，不静默翻标。
- 多段/嵌套HTML：不重复提取，不误删普通文本中的比较符号。
- 版本覆盖、超限、编码失败：原件和旧版本不变，不写伪完成清单。
- 同一内容多URL/来源：去重后保留来源，进度单调且输出可以复算。

## Task 1：解析、审计、清洗版本与CLI

Files: app/python/campus_workbench/{__init__,datasets}.py；app/python/tests/test_workbench_datasets.py；app/scripts/workbench.py。

Interfaces: read_dataset(path,kind,mapping=None,max_bytes=52428800,max_rows=100000)->dict；audit_dataset(dataset)->dict；clean_dataset(dataset,options=None,on_event=None)->dict；write_dataset_version(input_path,output_dir,kind,options=None,mapping=None,on_event=None)->dict。kind为NEWS或PAIRS，映射为标准字段→上传列名。JSON输出包含实际rows/issues/计数/来源；版本输出manifest/audit/cleaning/quarantine/corpus及events。

- [x] RED：BOM/多行CSV/中文别名/映射、坏JSONL、缺字段/编码/超限、重复及冲突、HTML提取、来源保留、真实事件、确定性SHA和旧目录拒绝覆盖测试。
- [x] GREEN：实现解析/指标/清洗、可审计隔离与版本写入，使用已有标准库。
- [x] 验证：现有生产Python运行15项内核测试及7项相关旧契约回归，共22项通过；5,043真实原作解析和3,021训练原作CLI处理及SHA复算通过。
- [ ] 阶段提交：只上传已验证任务，回读分支SHA；账本记录未接Web/未训练。

## Task 2：数据中心Web闭环（Task 1通过后细化接口）

Files: migration003、backend/workbench/{DatasetController,DatasetService,WorkbenchWorker}、frontend/{api/workbench.ts,views/DatasetView.vue,components/workbench/*}及对应测试。

- [ ] RED：部门越权、上传/字段映射、真实进度、取消/失败/断线恢复和计数交互。
- [ ] GREEN：MySQL数据集/版本/事件持久化；固定命令/安全路径调用Task 1；SSE+轮询恢复；统计卡、质量图、前后对照与样本分页。
- [ ] 验证：两个部门HTTP批量上传，实际浏览器清洗、查看图表/下载与跨部门拒绝；既有审核链路回归。
- [ ] 验证后阶段提交并汇报，转入主计划后续训练/评估/模型管理与共用稿件任务。

## 主计划后续依赖

训练入口消费固定清洗/样本/分组划分版本；原始新闻须先准备有依据样本，不能直接当标签。六模型训练/预测、SSE持续图表、参考批量入库、共用稿件、片段引用、语法/图文及正式v3按主计划继续实施。每个子系统沿用此RED→GREEN→真实验收→提交步骤，实施前补精确接口，不重复询问已批准范围。
