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
