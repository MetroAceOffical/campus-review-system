# 期末离线数据与训练

## 10月28日两条模型对照接入（阶段11）

`ablation_models.py`登记两种**离线对照**，不改变正式校园模型包或线上配置：

- `untrained-dense`：已下载的官方原始BGE + 冻结旧BERT。当前真实包为`runtime/experiments/final-training-20261028/ablation-untrained-dense-v1`，绑定6,311参考原稿。BGE支持原始已验证pytorch_model.bin与训练后safetensors，明确选择一种、核对SHA并weights_only加载，不转换或覆盖原始权重。
- `trained-dense-unadapted-reranker`：完成原规模2epoch并重载的校园BGE + 官方原始M3。正式BGE未完成时明确拒绝登记；公共辅助权重不可冒称校园训练完成，原始M3不能用旧BERT替代。

两条均可通过`v3_workflow.py index/predict --ablation`复用既有执行流。`predict --split calibration`生成完整200查询的真实特征，随后`calibrate`拟合；开发预测必须使用对应校准包，再`freeze-point`绑定完整400开发；最终1,200要求完整真值、本校覆盖和相同工作点。`--ablation`不改变这些门槛，也不使对照包可供生产加载。每条方法需要独立索引/校准/开发/最终输出；参考版本或源码变化后使用新输出，禁止续接旧身份。

```cmd
runtime\environments\final-training\Scripts\python.exe -B app\training\ablation_models.py --help
runtime\environments\final-training\Scripts\python.exe -B app\training\v3_workflow.py index --help
runtime\environments\final-training\Scripts\python.exe -B app\training\v3_workflow.py predict --help
```

实际登记包已完成，不重复登记同一目录；索引/正式预测待资源和完整评价材料就绪。旧BERT为`LEGACY_SEMANTIC_SCORE`，原始M3为`PRETRAINED_RELEVANCE_SCORE`，校园任务M3为`CONTENT_CORRESPONDENCE_SCORE`；新对齐共用联合512上限、不得截断，旧v2的128输入和对齐政策单独保留。所有分数类型进入方法/校准身份，余弦不替代分类头输出。五组导出代码齐全不等于五组真实成绩已完成。

本阶段实际CPU核验仅3条训练域BGE编码和3对冻结BERT打分，未测改写准确率或最终集；原始M3只核对组件SHA，没有神经执行。原18个后台训练依赖和heldout-generation-v2绑定源码保持不变。

13:56后台接续：217篇Web准备已实际保存653配对，六个工件SHA通过；原正式控制器随后自动启动campus-generation-v4的3,684篇原稿生成。该Web输出不替代正式20,000配对和类别平衡要求，后台生成参数及各2epoch不变。

## 10月28日留出构造与旧基线导出（阶段10）

当前正式训练仍绑定campus-quality-20261028-v1，**不替换在跑配方**。新增只用于评价的campus-evaluation-partitions-20261028-v2为6,311篇，train文件与原版逐字节相同；新协议为text-evaluation-corrected-20261028-v3，当前仍只有340控制查询，不能称完整1,800条或独立质量已通过。

- `recover_home_cache.py`恢复旧公开API中此前未入语料的正文，核验原响应SHA、已知来源/事件和公共训练重合；`--raw-root`只接受已经READY的项目runtime新采集缓存。真实恢复32候选→30留出候选，2篇训练关联隔离；旧执行源分别保存在runtime/source-checkpoints/home-cache-recovery-v1-code.py及v2-code.py，后续只增加新缓存入口，未重写旧审计。
- `extend_heldout_partitions.py`只合并已审计的calibration/dev/final候选，复制原train字节，合并既有保守事件关系。原语料、训练计划和历史协议不覆盖。
- `heldout_queries.py prepare/generate/assemble`构造1,020条留出正例，实际3,085不同原段/48短尾原样控制。局部背景为同分区真实原稿，有明确范围和参考排除；整篇/局部/多源均保留码点映射。不能使用train父稿，不能按生成计划伪写已构造查询。生成失败、重复、预算超限或段缺失均保留待补；440正常稿仍要求完整负范围依据。
- 当前构造工作版本v2允许固定机构全名等作为原样控制保留，但整篇至少50%来源字数通过实质改写检查，并继续检查整篇复制率、事实和数字；局部/多来源片段全部要求改写。v1在神经生成前停止，仅本任务自己的未开算等待进程被替代，旧计划/执行源码保留。
- `export_legacy_evaluation.py --variant frozen-v2/semantic-disabled`导出旧基线或完全关闭语义的实际结果，并自动调用evaluate_final。GPU旧v2遵守共享锁；纯CPU字面分支不加载任何神经权重，使用独立CPU锁及至少2GiB空闲内存，运行进程的OMP/MKL/OPENBLAS线程可设为2，不修改全局设置。显式`--resume`只续接同一未完成输出。最终分支同样要求完整开发、正式规模和本校覆盖；`--diagnostic-controls`仅限开发控制。

当前后台状态文件：

- `runtime/experiments/final-training-20261028/heldout-generation-v2/status.json`：等待校园训练/导出，然后串行生成/自动组装，最多等待96小时，无开机/周期任务。
- `runtime/datasets/ncuc-public-api-20261028-v1/status.json`：先复用12份原缓存，等待官方站点恢复且robots允许，30分钟退避、最多12小时；未恢复不写READY，不关闭TLS或处理访客验证。
- `runtime/experiments/final-training-20261028/literal-dev-controls-v1-metrics/summary.json`：实际75条CPU开发控制结果（1个来源召回未命中、0运行失败、0无效偏移），无正常稿FPR，不能当洗稿准确率。已完成不要重跑同一输出。

重启后先确认对应原进程均已退出，再以同一源码/输入显式续接（CMD，勿在运行时重复执行）：

```cmd
runtime\environments\final-training\Scripts\python.exe -u -B app\training\heldout_queries.py generate --work runtime/experiments/final-training-20261028/heldout-generation-v2 --after-training-stage runtime/experiments/final-training-20261028/campus-training-stage-v2 --wait-hours 96 --assemble-output runtime/datasets/text-evaluation-generated-20261028-v4
runtime\environments\final-training\Scripts\python.exe -u -B app\training\collect_ncuc_api.py --output runtime/datasets/ncuc-public-api-20261028-v1 --max-wait-hours 12
```

若后续补到新的本校来源，需要新协议和新的heldout工作目录，不修改旧协议/已保存查询，不把同事件别名当新独立稿。仍须补本校60%、正常稿真值、两路密集/未适配M3对照、完整真实评价及生产库匹配配置。

## 10月28日模型接入与自动评价准备（阶段9）

`v3_workflow.py`已有`status/register/index/predict/calibrate/freeze-point`命令。当前只完成接入代码和协议准备，新校园BGE/M3还未完成训练；不要把可执行入口或被冻结的构造槽位记成新模型成绩。

当前状态命令（CMD，从项目根目录执行，不加载模型或占GPU）：

```cmd
runtime\environments\final-training\Scripts\python.exe -B app\training\v3_workflow.py status --recipe runtime/experiments/final-training-20261028/corrected-formal-recipe-v1.json --protocol runtime/datasets/text-evaluation-corrected-20261028-v2 --output runtime/workbench-implementation/v3-readiness.json
runtime\environments\final-training\Scripts\python.exe -B app\training\v3_workflow.py --help
```

当前新协议保留6,281参考原稿和200/400/1,200目标，但只有40/75/225条控制查询，其余待新版本补齐，不能直接运行正式预测。`prepare_corrected_evaluation.py`只从已修正分区和可重新核验的原页恢复自然关系，旧协议不改。正常稿需有覆盖整个参考库的排除/负范围依据，未知关系不补0标签；最终本校60%覆盖不足会被新入口拒绝。

完整材料和权重就绪后的执行顺序：

1. `register`显式指定`--retriever-run --correspondence-run --export --references --output`，核对校园BGE≥1,000组、M3≥20,000对、各2epoch和实际重载；输出只读bundle。不会把公共辅助checkpoint当校园模型。
2. `index --bundle ... --output ...`用固定BGE构建新的192/48密集索引，支持`--device cpu/cuda`；模型参数和索引实际精度/批量要一致。构建只需要BGE，预测会再加载M3及原v2模型。
3. `predict --split calibration --bundle ... --index ... --protocol <完整协议> --output ...`执行全部200校准查询并保留实际来源特征。随后`calibrate --features ... --protocol ... --partitions ... --output ...`拟合，支持`--whole-threshold/--local-threshold`。拟合默认工作点0.5/0.5，尚未视为最终冻结；只允许校准事件，训练/dev/final事件拒绝。
4. `predict --split dev --calibration ...`必须完整400条，保存逐条预测后自动调用现有evaluate_final输出独立metrics目录。`--diagnostic-controls`仅供开发控制诊断，不能用它冻结最终工作点。
5. `freeze-point --calibration ... --development-predictions ... --development-run <完整dev metrics> --output ...`在新目录冻结同一实际工作点，绑定完整开发证据。修改真实阈值会改变方法ID，必须重新完成相应开发评价。
6. `predict --split final --calibration <冻结包> --development-run <同一dev metrics>`才可执行全部1,200最终查询并自动评分。最终控制诊断、模型/参考库/查询/算法不一致或未冻结工作点均拒绝。

预测`--resume`要求未完成目录的run身份完全一致，SQLite每条提交；已READY导出不再改写，直接用evaluate_final重算评分。所有失败留在分母，不补虚假零分。当前完整联合预测使用既有CUDA环境并持有Web共享计算锁；CPU只提供索引构建，不偷偷改旧BERT执行环境。五组消融的完整导出仍待后续接线/执行。

服务接入使用`campus_detection.http_service --v3-profile <项目runtime中的profile.json>`显式选择；profile为`bundle/index/calibration`三个路径。必须选实际已完成并冻结的校准工作点。profile的参考文稿字典必须与该业务库代完全一致；6,281篇离线评价库不能直接冒充当前线上参考库。新索引/校准包不匹配就拒绝执行，旧v2默认服务和历史配置继续保留。当前阶段未部署/切换，也未在发布页开放未训练版本。

## 10月28日当前作业：修正语料与正式材料队列

当前采用新版本 `runtime/datasets/campus-quality-20261028-v1`（6,281原稿，train3,802），旧分区/报告/生成配置保留。下文旧1,200篇、旧v3、旧训练等待命令均为历史记录，**不要恢复旧材料来替代本轮修正版本，也不要重复启动正在运行的新作业**。

- `article_extraction.py`按DOM文字节点一次提取，保留真实重复段和段落边界；`repair_campus_material.py`只读缓存HTML/历史正文，记录SHA/谱系/排除，重算簇并保留旧留出边界，冲突隔离。原始缓存与冻结旧分区均不覆盖。
- `prepare_corrected_training.py`读取已冻结新分区，对旧生成和Web已提交部分作SQLite只读一致性快照；仅唯一完整规范化来源段、数字/名称/充分重写通过才复用，旧偏移不直接继承。实际起步7,678对，不等同正式20,000材料。
- 新生成全量3,684个符合原有选择规则的原稿，16,773窗口（440可复用），不将窗口当独立文章。候选CPU挖掘已启动（18,937窗口、每窗口30来源），未知候选经`audit_negative_candidates.py --partitions <新版本>`的实际内容差异核验才成为负例。
- `run_corrected_material.py`按冻结配方接续负例、生成、组装和有条件训练。使用现有Web的compute.lock等待资源，不停止Web作业；48小时是**等待资源**上限，真实工作不因该上限中断。源码/数据/配方身份变化会停止并保留产物，不静默换版本。
- 正式门槛仍是对应20,000对/各类20%、检索1,000组/一正四负/改写至少50%、来源至少1,200/自动事件600、BGE/M3各2epoch、有效32，长度512。未满足会明确停在材料缺口，绝不会自动降低训练量、轮数或切换生产模型。

当前配方的源码副本为`app/training/campus-corrected-recipe-20261028.json`，后台绑定的原样冻结副本为`runtime/experiments/final-training-20261028/corrected-formal-recipe-v1.json`。运行状态位于同目录下`corrected-material-stage-v1/status.json`，各child完整日志在该文件夹；独立CPU挖掘进度在`runtime/datasets/campus-correspondence-candidates-20261028-v3/progress.json`。Web217篇队列保持原数据版本，和这里的正式训练材料分开记录。

以下CMD命令仅供**重启后确认原进程已结束**、当前源码/数据身份仍相同的显式续接；正在运行时不要再次执行。CPU候选未READY且原矿工已退出时先续跑同样完整参数（该矿工从头重算候选输出，未冻结的部分不作已完成数据），候选已READY则跳过第一条：

```cmd
runtime\environments\final-training\Scripts\python.exe -u -B app\training\mine_correspondence_candidates.py --partitions runtime/datasets/campus-quality-20261028-v1 --output runtime/datasets/campus-correspondence-candidates-20261028-v3 --sources-per-window 30
runtime\environments\final-training\Scripts\python.exe -u -B app\training\run_corrected_material.py --recipe runtime/experiments/final-training-20261028/corrected-formal-recipe-v1.json --output runtime/experiments/final-training-20261028/corrected-material-stage-v1 --continue-existing-stage
```

若负例/组装/真实训练中断，控制器会保留未完成产物并停止；不要删除产物或反复重启，须先核对检查点/输入身份并显式恢复或建立新版本。两模型适配完成后，仍需校准、独立评价、新索引及兼容审核配置，不能直接发布为已通过质量验收。

以下按日期保留历史过程，最新状态以本节及真实status为准。

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

更新：主T2分片现已实际准备50,000组/250,000配对并在跑，500/1000步checkpoint已存在，尚未完成2epoch及最终重载；清洗v2已得到5,043正文、22学校、本校551，仍NOT_FINAL_SPLIT。最终生成器已下载校验但未加载GPU。旧run通用stage/warning字符串沿用event/story，实际数据manifest SHA绑定T2RANKING相关性；该命名欠准确单列披露。

## 校园任务阶段

`campus_partitions.py` 已冻结原作四区（3,021训练、339校准、522开发、1,161最终），按源簇、题名/时间保守事件组整体分配；19篇公共训练重合来源及其事件限于train。事件分组是自动规则，去污染保证至少71连续规范化字符的重合检出，不能声称已排除所有语义同源。修改分区必须新版本，不根据最终模型预测重新分配。

`construct_correspondence.py --max-originals 1200` 已建立可续跑生成队列，等待检索主训练完成并重载核对后才加载Qwen。只读train原作，每事件一个原作、每原作一份整篇变体；保留360码点分段及两侧范围、逐次输出和质量检查。程序检查不证明全部语义正确；最终评价、开发与校准材料没有因此被生成或训练。状态位于campus-generation-v1/status.json，失败段和尝试保留在SQLite。

`mine_correspondence_candidates.py` 在训练原文上按M3 tokenizer全文章切240token、重叠48，挖掘相似候选并保留原文范围，输出unknown/target=null；不能拿候选数当有效训练对数。`negative_basis.py` 为明确内容差异建立保守规则依据：不同来源/源簇/事件、明确主题名称、不同实质过程、发布期及无大段叙事复制等逐项留存；不以模型低分为负标签，不把仅改姓名日期作为负例。支持的规则负例标supported_rule，不冒称人工金标。

`train_correspondence.py` 是正式M3 LoRA训练入口：已实现冻结主干、query/value r16、分类头与独立学习率、联合512token、两轮BCE、500步/epoch断点及最终重载核对。入口要求带READY的pairs.jsonl、两类有依据标签、train分区和原作位置；oversize窗口明确拒绝，不静默截断。当前没有启动正式M3训练，小型XLM-R回归仅证明适配器及分类头更新和重载机制。原M3父模型为runtime/experiments/route-b-development-20261026/model，绑定同目录candidate-manifest.json，原文件不改。

正式M3默认至少20,000准备对，重复/反向相同文本对不能凑规模；两类占比及来源位置另行核验。`audit_negative_candidates.py` 对真实原文重建并保留事实依据，v1仅281支持对、v2为456对，未达到正式目标，因此未启动一个小规模M3正式run。v2同主题负例可基于不同的具体过程—对象事实，仍保留日期、名称与大段叙事复制保护。规则负例不等同人工金标，候选未知关系不进入BCE。

公共T2主训练已结束（3126步、2epoch、重载及最终SHA核对通过），Qwen现在已在GPU实际生成；本文前面的在跑/等待描述为历史检查点，以各run的status.json和主文档最新记录为准。当前生成队列1,200父原作/5,716段，早期估算剩约15小时。GPU作业不中断可继续，重启后必须先确认原进程已结束再显式恢复同配置。当前GPU生成源码在该run目录另留快照，原语料、权重及失败输出均不进GitHub。

当前在跑T2作业沿用对称辅助分组，实数审计有10/50,000组以段落作为锚点（关系没有反标，也没有增大独立计数）。已新增`--directed-retrieval`用于之后的新定向作业，固定官方query侧；当前run若断点续跑须保留原参数，勿加新flag或改configSha，不能将旧模型冒称按新方向策略重训。其实际源码已保存在run的training-code.py。后续新作业的衔接脚本使用定向模式，现有在跑父子进程不受源码更改影响。

## 最新生成与组装入口

扩大离线候选v2已冻结431,188候选；`audit_negative_candidates.py --source runtime/datasets/campus-correspondence-candidates-v2 --output runtime/datasets/campus-supported-negatives-v4`已完成8,451规则支持负例，覆盖1,309查询父来源。默认离线每窗口30来源独立于推理Top3；规则v3加入有具体原文事实范围的不同标题/实质过程路线，未知候选不补标签。旧v1/v2/v3负例快照均保留。

当前在跑的是提示词v3（不是产品text-v3），命令如下。**原进程活跃时不要重复执行。**

```powershell
& runtime/environments/final-training/Scripts/python.exe -u -B app/training/construct_correspondence.py --max-originals 1200 --prompt-version 3 --reuse-generation runtime/experiments/final-training-20261026/campus-generation-v2 --output runtime/experiments/final-training-20261026/campus-generation-v3
```

v1/v2的原配置、源代码、失败输出与转换记录不覆盖；新目录复用314重新检查合格片段，不新增独立父来源。v3明确绝对字数、禁止续写及0.25/0.15采样温度，长度/数字/名称门槛不变。段级刚性复制记录COPY_CONTROL，整篇仍检查改写比例；截断失败不能复用。原作1,200、队列5,716段尚未全部完成，机器筛选不能认证完整语义。

**仅在该生成status实际为TRAIN_CONSTRUCTION_FINISHED后**，执行以下CPU组装：

```powershell
& runtime/environments/final-training/Scripts/python.exe -B app/training/prepare_correspondence.py --generation runtime/experiments/final-training-20261026/campus-generation-v3 --negatives runtime/datasets/campus-supported-negatives-v4 --output runtime/datasets/campus-correspondence-training-v1
```

组装复核完成导出SHA及train身份，保留源段完整范围与查询不重叠120token切片范围，不按字符比例伪造对齐；每对联合512预算、原文重建、数字/名称、负例内容依据和文本反向去重均核对。生成片段内原样部分另算复制；复制与句序调整各不超过正例四分之一。READY只表明文件冻结，须另查formalScaleAndBalanceReady；不足20,000或类别占比不足20%时明确记缺口，不能据READY自动启动小规模M3。当前尚未组装/训练完成。

仅运行离线模块回归：

最新57项回归覆盖数据/LoRA/索引与图片工程，不代表正式模型成绩。`app/python/campus_detection/retrieval.py`和`alignment.py`为待接入的v3底层，当前没有改变旧路由；真实模型编码、邻接上下文、校准和业务接入仍需另行实现/核验。索引必须绑定权重/tokenizer/池化/精度/算法并在新目录写READY，不得将旧库直接冒称新特征空间。真实BGE/M3 tokenizer的50篇原文预算/偏移复查通过。

```powershell
& runtime/environments/final-training/Scripts/python.exe -B -m unittest discover -s app/training/tests
```

测试涉及临时本机HTTP服务器，沙箱拒绝回环网络时须使用已授权的本机执行权限；不得为通过测试关闭业务权限。Web完整回归仍用 `app/scripts/check.ps1 -Task ALL` 的独立测试库，默认真实模型skip须单列。训练与生成串行占GPU，不能将GPU作业塞进Web队列，也不能为新增训练删除未来扩展预留。各作业原件与断点独立于聊天保存，电脑重启后须核对状态和完整checkpoint再续跑；不要同时启动第二个同名作业。

## 图片采集、协议及开发探针

稿级汇总工程入口为`app/python/campus_detection/aggregation.py`。按来源字段计算模板剔除后的窗口并集，跨来源共享查询范围不累计；JSON校准系数绑定模型/特征/算法、冻结校准分区与事件集合，每行必须携带相同featureConfigSha256。正式拟合默认100行/30自动事件/每类20，不能拿6行机制单测工件用于正式判定；未知标签与非校准事件拒绝，PARTIAL时没有命中不等于无复用。尚无真实校准材料/正式校准器或业务接入；当前62项离线测试通过。

`collect_images.py`复用已冻结四区文章的图片链接，只采公开学校域名，robots、有界响应、事件限额和断点记录；已得490个不同像素候选。`prepare_image_protocol.py`按原图像素/近图pHash和文章事件合簇，预测前冻结300原图、295自动家族及2,100受控查询。自动家族不是人工事件金标；自然难负例没有因此被自动赋0。raw图片、查询及原URL仅在runtime，不能上传GitHub。

`evaluate_image_geometry.py`只在CPU上运行开发区已知来源几何核验，默认不提供最终区执行选项；目前1,064例接受969，95空间支持不足，未做DINO联合或自然负例误报率。该探针实际记录失败/不足分母、各变换、自动家族bootstrap及延迟。`--resume`仅允许同数据/代码/政策身份续跑，不重标失败。

图片核心位于`app/python/campus_detection/image_geometry.py`，SIFT配合L2和双向比率、RANSAC及内点凸包覆盖；实现依据[OpenCV匹配](https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html)和[单应性](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html)。pHash只提供近图候选，不能单凭低纹理近哈希宣称复用。区域坐标恢复EXIF方向后的原图像素中心；覆盖是空间支持，不是复制像素百分比。当前没有替换image-v1，OpenCV只使用用户已批准隔离环境，未修改生产依赖。

`prepare_correspondence.py ... --wait-for-generation`已经作为独立CPU作业排队：最多等待48小时完整生成导出，失败上游立即停止；就绪后自动组装和核对规模/类别，仍不会自动激活或用不足数量启动M3。不要重复启动同名输出的组装作业。当前状态见runtime/datasets/campus-correspondence-training-v1/status.json。

## OCR材料、恢复及评价

`prepare_ocr_materials.py`已冻结200已知文本合成查询（50原稿家族，开发/最终各100）和50张仅运行覆盖的真实图；真图无转录，不进入CER。字体为现有Windows微软雅黑，字体SHA/布局/变换/GT行框在本地协议；素材和原URL不进GitHub。合成主要单栏，不能冒称复杂真实海报代表性已充分。

`evaluate_ocr_recovery.py`使用**已有OCR Python**，不是训练venv；没有安装新依赖。新增fallback.py保留960对照，按质量条件1600及1024/128重叠分块，最多9块并明示PARTIAL。内容解码避免.img后缀拒绝，恢复坐标处于同一解码/EXIF原图框架；像素/特征/算法/处理策略身份独立。默认ocr-v1尚未替换。

已完成开发v2（100合成+50真图）和最终v1（100合成），命令仅供恢复参考，**完成作业不要重复执行**：

```powershell
& validation/remaining/vision/env-ocr/Scripts/python.exe -B app/training/evaluate_ocr_recovery.py --split development --include-real-runtime --output runtime/experiments/final-training-20261026/ocr-recovery-development-v2
& validation/remaining/vision/env-ocr/Scripts/python.exe -B app/training/evaluate_ocr_recovery.py --split final --development-run runtime/experiments/final-training-20261026/ocr-recovery-development-v2 --output runtime/experiments/final-training-20261026/ocr-recovery-final-v1
```

开发合成CER0.21838%→0.18151%，最终0.34165%→0.29930%，最终差区间上界0，恢复P95更高；50真图完成但6空/1PARTIAL，真实CER仍不可算。首轮开发v1的.img导致50真图失败，旧run及代码保留，不能写成已成功。当前只完成离线评价，未做OCR新服务业务接入。

## 自然关系与校园检索适配

`audit_natural_relations.py`复用已有缓存，不再请求用户重核同文。过滤URL/栏目别名、相同HTML和重复发布记录后，以原页SHA及规范化全文完全相同确认92条不同发布记录关系，按原split保存；最终仅20条，200目标未达。数据不意味着独立事件、作者先后、实际复制或版权许可，也不是自然改写准确率。

`prepare_campus_retrieval.py`等待正式对应分片，按实际查询重新核查每个负来源的内容差异，不直接继承父原文负标。四负来源与文本均不同，每侧512完整输入，最少1,000不同查询组、来源限8组、改写至少50%；实际准备量尚未知，不据入口称完成。BGE新作业参数为`--campus-correspondence --directed-retrieval --max-tokens 512 --microbatch 1`、有效32、两轮，从已完成T2权重衔接；默认旧辅助256/micro2配置不变。正式M3仍需至少20,000对应对。校园神经训练链目前尚未启动，下一步须核对完整材料再衔接，不能重复启动同名目录。

最新离线76项回归通过；旧版check ALL也已通过（真实模型项按默认跳过）。明日演示按用户选择重启后原入口启动，不添加演示模式或切换新模型；重启结束后台计算，保存结果/完整检查点保留。

M3正式作业额外固定：冻结主干BF16、LoRA/分类头参数FP32、前向BF16 autocast，防止低学习率在BF16分类头上难以形成参数变化；逐步分别记录adapterWeightChanged与classifierWeightChanged。续训和最终重载使用相同适配器精度。本机oneDNN不支持BF16主干CPU backward，CPU测试只检查dtype及FP32头低学习率更新，完整FP32 LoRA/头更新与重载另测通过；未改环境，CUDA混合精度仍待正式作业。最新完整离线77项通过，真实M3尚未训练。

## 10月27日接入基础补充

重启后已核对原进程退出及源码身份，按上文原命令恢复提示词v3生成和CPU组装等待；没有开机自动训练或新的神经训练控制器。准备材料达到formalScaleAndBalanceReady前不能启动校园正式微调；不要把旧status的GENERATING当作进程仍活着。

alignment.py现在可由source_contexts按`(sourceRevisionId, sourceKey)`提供原文字段及该字段的索引块，加入前后邻接块后按联合512拆窗，保存retrievedSourceRange。evaluate_pairs调用已绑定模型的scorePair，只从成功调用计算checkedRegions；失败、无候选、空输入及延后配对保持不完整状态。训练区25原作/75区域/76配对的真实分词预算与原文位置验证通过，最大511token，没有正式模型预测成绩。

`export_correspondence.py`是训练结束后的CPU导出入口，需要明确`--run --data --model --base-manifest --output`；output必须为runtime/models/final下新版本。要求正式至少20,000条、2epoch、完成状态及最终重载通过，检查完整checkpoint/数据/父模型哈希；先按训练BF16加载冻结主干再提升FP32，合并adapter及分类头并对比同输入、保存、普通Transformers重载，最后新目录READY。当前没有完成的正式M3，不能提前执行或称已导出。

`campus_detection/task_model.py`只读加载上述export，调用者必须指定expected_export_id；复核manifest/全部文件、模型类型、联合512和明确CPU FP32/CUDA BF16策略。生产加载路径不import PEFT，未安装生产新依赖。导出CPU等价和小型模型工程测试不能代替正式CUDA精度、v3服务路由及质量回归；本轮默认v2保持。

最新完整离线85项通过，含实际小模型更新/合并/序列化/加载器前向及篡改拒绝、模型失败/预算/空输入覆盖记录。正式神经训练、校准和新业务接入仍待材料及真实结果。

## 召回编排与有限训练衔接（10月27日08:53更新）

`retrieval_model.py`读取明确选择的检查点哈希，完整绑定BGE权重/config及tokenizer组件，实际CLS/L2编码、512输入保护与精度/设备身份；已有T2完成模型的CPU核验建立8校61块新索引并重载，8个原样块控制8/8来源Top1，不是校园Recall成绩。新索引算法身份变化需要新目录，旧字面索引不受影响。

`v3_pipeline.py`衔接混合Top30来源池、每区不同来源Top3、邻接块、联合512调度、实际成功调用和模板扣除后的来源特征。它仍为独立入口，不改默认text.py/旧acceptedCandidate。必须分别绑定BGE和M3 tokenizer；没有正式校准器返回PENDING_CALIBRATION，有校准器则推理前验证配置/算法/正式规模和工作点。字面输入是来源排名，不自动从旧v2结果伪造Top30；真正业务路由和报告接入仍待实现。

以下控制器已实际启动，**原进程活跃时不要重复运行**：

```powershell
& runtime/environments/final-training/Scripts/python.exe -u -B app/training/run_campus_stage.py --wait-for-material
```

run位于runtime/experiments/final-training-20261026/campus-training-stage-v1。最多等48小时完整正式材料；不少于20,000不同配对且类别各至少20%才允许进入训练，子训练器再次核对真实行/标签/预算。BGE适配需至少1,000不同查询组；不足时保留检索待补，M3可用其独立合格分片继续训练，不降低门槛。正常顺序为准备校园BGE分片→GPU空闲后BGE适配→M3→CPU合并导出，均不激活生产。

控制器快照8个实际脚本依赖及已有包版本，持有项目独占文件锁；每次启动子任务前后复查，源码变化停止。已有完整run逐项核验并跳过；已有未完成run报明确恢复状态，需先显式按完整checkpoint续训，不能自动覆盖或将ALREADY_COMPLETED打印当成最终重载成功。重启会结束控制器和子任务，确认无旧进程后，只有相同pipeline.json/源码环境才能加`--continue-existing-stage --wait-for-material`续接；发生代码/环境变化用新stage目录并保留旧记录。准备分片的.partial/非READY残留也先保留检查。

当前状态仅WAITING_FORMAL_MATERIAL、neuralTrainingStarted=false；尚无正式校园神经作业。18081检测服务在运行时控制器停止，不争用展示GPU，不自动停任何服务，也不安装依赖或设置开机启动。最新完整离线97项通过，实际进展见主文档和子作业日志。

## 评价协议构造与评分（10月27日后续）

`prepare_text_protocol.py`已实际运行并冻结runtime/datasets/text-evaluation-protocol-v1，含5043参考字段、1800构造槽（校准200/开发400/最终1200）及340已构造复制/句序控制。开发75/最终225不是完整400/1200。自然36条关系合并成33不同正文查询，最终20发布关系仅18不同查询；保留多条原页谱系。每事件最多两查询，最终计划主来源本校418/1200，60%未达。缺生成改写和全库正常真值的槽位继续pending，未加载神经模型。

`text_evaluation.py`评分正确来源及有支持证据的检出，保持FAILED/缺失分母；版本、码点文本、来源字段必须正确，多来源事件连通组件bootstrap。只有完整参考范围的负例依据才能算全库正常稿误报率，未知关系/额外来源单列，不将缺口填0。只有真实完整决策分数且有正负两类才生成PR，失败延迟不造0ms。340已知正控制不能产生正常稿FPR。

`evaluate_final.py`读取**已冻结真实预测目录**（run.json、predictions.jsonl、READY）评分，尚未接入模型批量推理/导出入口。正式执行要求当前split查询构造完整且开发400/最终1200；复制控制调试只允许显式`--diagnostic-controls --split dev`，不会成为正式指标。最终还要`--development-run`指向兼容的完整开发评分证据，并验证预测导出的工作点冻结/开发证据SHA。不要向真实目录写测试夹具或伪造预测来“跑通”指标。

预测目录run须声明实际消融variant：frozen-v2、untrained-dense、trained-dense-unadapted-reranker、full-v3或semantic-disabled；绑定protocolReadySha256、splitQueriesSha256、referenceManifestSha256、methodConfigId、split、diagnosticControls。full-v3还要求真实两项校园训练完成和正式校准冻结，实际状态仍须由子run/权重核验支撑。每条预测绑定queryId/querySha256/methodConfigId/referenceManifestSha256，保留coverageStatus、candidateSources、sourceDecisions、pairs及原始elapsedMs；语义pairs支持阈值必须来自冻结featureConfig，不能拿余弦值当任务证据。

本阶段实际只做了协议构造、6296映射完整性核验和正式评分拒绝检查，文字模型预测0、正式评价0。完整离线111项通过，合成测试预测仅在单元测试夹具中，不是项目模型结果。准备/构造脚本不在当前训练控制器8项依赖内，不会因新增评价代码打断已授权训练等待。
