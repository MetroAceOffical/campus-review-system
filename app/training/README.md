# 期末离线数据与训练

当前依据为 `docs/技术设计.md` 的期末细化设计及10月26日扩大正式训练的补充。旧路线B小样本不作为采集、训练的前置。本文不是训练全部完成或质量验收通过的证明。

所有命令从项目根目录运行，解释器为 `runtime/environments/final-training/Scripts/python.exe`。该环境按用户批准建立，复用现有Torch2.8.0+cu128、Transformers4.57.1，新增依赖固定在requirements.txt；不会修改生产环境。不要直接运行安装或升级命令。

## 已有作业

- `collect_corpus.py --sources app/training/campus-sources.json`：各host单worker、1.5秒间隔、robots、最多三次网络退避、SQLite断点与原页面。额外入口见campus-extra-sources.json；须先确认同host没有活跃worker再启动，避免重复采集。同一hostname不等于独立学校。
- `collect_platforms.py`：读取已经从学校页面发现的公开微信/微博链接；遇robots不可访问、拒绝、登录或无正文明确记录失败，不绕过验证。主体未确认的页面不能自动冒称学校官方原文。
- `prepare_campus.py --output runtime/datasets/<全新版本>`：冻结一个清洗快照，复用已校验历史本校正文、去完全重复与近重复转载，并从缓存原页恢复明确发布栏日期；源簇不冒充人工确认事件。输出明确NOT_FINAL_SPLIT，必须完成公共训练文本去污染及事件分区后再冻结开发/最终材料。v1快照实际4,624正文，非5,000目标已完成；后续快照使用新目录。
- `prepare_training_data.py`：重新检查旧公开下载字节，混合标签隔离，事件/故事关系只进入检索辅助；相同正文及正关系连通分量隔离。未完成校园近重复/事件聚簇，不能将此auxiliary split当作校园最终划分。
- `acquire_models.py`：只取设计指定模型数据，固定revision及哈希，不执行远程代码。大文件使用download_assets.py的有界Range及断点，最终SHA不符拒绝。
- `acquire_retrieval_data.py`：只取固定版本T2Ranking训练查询、qrels、collection及说明，不取全部16.5GB仓库或测试集。
- `prepare_t2ranking.py`：流式扫描collection，仅保存选中的50,000个查询组及其1正+4个明确负例，共250,000个不同query/passage配对。正例为公开2/3级、负例仅0级，不将1级或未知关系当负例；只作检索相关性，不用于M3对应头。官方qrels已实数检查60,737查询满足条件。该数量是配置目标，只有READY、实际统计和训练日志才能证明完成。
- `run_t2_stage.py`：已启动的衔接作业最多等待六小时，只有T2下载完整且SHA验证后才准备主分片，继承已验证辅助checkpoint并开始真实训练。上游失败则不能宣称主训练已开始；见stage-status.json。
- `train_text_models.py`：当前实现BGE检索训练，四个显式负例真实参与损失、BF16、checkpointing、2epoch、有效32、每500优化步/epoch保存。支持`--initial-weights`衔接新阶段和`--resume`同配置断点；校验输入READY，包含优化器/调度器/随机状态/游标，最终实际重载比对输出。不支持通过重复启动覆盖旧run。M3 LoRA及校园适配仍待后续实现，不能因脚本命名而称二者已训练。
- `evaluate_auxiliary.py`：首个新闻分片的10组五候选辅助验证，保存逐例预测。不是全库Recall@K或校园最终测试。

原始数据在 `runtime/datasets/`，新权重在 `runtime/models/final/`，作业与checkpoint在 `runtime/experiments/final-training-20261026/`，日志在 `runtime/logs/final-*.log`。均不上传GitHub。旧validation、v1/v2配置、历史库代与报告不覆盖；只有另行满足开发/最终评价与真实业务回归后才能激活v3。

## 当前真实完成与缺口

首个新闻辅助分片2,836组、2epoch/178步、最终重载核对通过；记录见 `docs/assets/final-auxiliary-training-20261026.json`。其中177步有参数片段变化，首个warmup学习率为0；全部178步有有限梯度记录。它是辅助启动分片，不是正式规模或校园效果结论。

主T2分片、校园对应材料/生成、M3 LoRA、稿级校准、图片几何/OCR回退、v3索引/报告接入、400开发/1,200最终自动评价及送审回归尚须按实际状态完成。清洗后训练库必须再与校园开发/最终来源近重复比对，不能直接将辅助训练文本当作无污染背景。

仅运行离线模块回归：

```powershell
& runtime/environments/final-training/Scripts/python.exe -B -m unittest discover -s app/training/tests
```

测试涉及临时本机HTTP服务器，沙箱拒绝回环网络时须使用已授权的本机执行权限；不得为通过测试关闭业务权限。Web完整回归仍用 `app/scripts/check.ps1 -Task ALL` 的独立测试库，默认真实模型skip须单列。训练与生成串行占GPU，不能将GPU作业塞进Web队列，也不能为新增训练删除未来扩展预留。各作业原件与断点独立于聊天保存，电脑重启后须核对状态和完整checkpoint再续跑；不要同时启动第二个同名作业。
