# 数据工作台计算内核

此包独立于线上审核模型。数据部门字段只记录材料来源，Web归属必须由服务端账号权限决定。

数据中心支持NEWS原始新闻与PAIRS标签句对，CSV/JSONL、UTF-8/BOM、中文列名/显式映射、最多50MiB/100000条。质量报告统计缺失、长度、来源、日期、类别、重复和冲突；清洗生成新版本，保留来源和旧分区，冲突/坏行隔离。

项目根目录CMD示例：

```cmd
validation\text\env\python.exe -B app\scripts\workbench.py audit --input runtime\workbench\import-packages\campus-training-news-3021.jsonl --kind NEWS
validation\text\env\python.exe -B app\scripts\workbench.py clean --input runtime\workbench\import-packages\campus-training-news-3021.jsonl --output runtime\workbench\versions\example-new-version --kind NEWS
```

`--output`必须是新目录。参数用`--mapping-json`和`--options-json`传递JSON对象。CLI输出NDJSON，类型为event/result/error；退出码0才表示本次操作成功。COMPLETED仅指数据处理，不能解释为训练完成。

输出含manifest、corpus、audit、cleaning、quarantine、changes和events。manifest最后落盘，包含原文件和六个产物的SHA256；调用方须同时核验退出码/manifest/工件SHA。原上传文件应由Web保存，不在此覆盖。CSV出错且无法恢复边界时整批失败，JSONL可恢复坏行保留编号；明细中的rowNumber是记录编号，lineNumber是物理起始行。

处理器v2按所选清洗规则处理后的完整文本判断精确重复，保留单词边界；来源采用紧凑描述和输入SHA/行号追溯，内部再次清洗保留整个来源链。重复簇一致的分区/事件标识继承，冲突隔离。外部上传仍限50MiB，已登记内部版本由Java固定配置`internalVersion`选择512MiB读取边界，不能通过上传参数扩大限额；记录数仍限100000。内部空版本可以审计，训练需另行校验有效样本。

Java通过`--config-file`传递UTF-8任务配置，避免Windows命令行破坏中文JSON引号。配置键仅mapping/options/internalVersion；后者由服务端依据输入版本阶段设置。

核验：`set PYTHONPATH=app\python`后运行`validation\text\env\python.exe -B -m unittest discover -s app\python\tests -p test_workbench_datasets.py`。

## 可选模型工作台

`preparation.py`按来源、显式事件/分组和相同句子建立连通分组，整组划分；旧独立分区保持，全train输入可在原train域内生成新划分。NEWS保存原作分组及带范围的待标注段落池，PAIRS在三个分区均有两类时允许训练。它不把随机不同新闻直接标为负例。

`training.py`提供LR/SVM/RF/CNN/BiLSTM/BERT参数化训练、保存重载、独立测试评价及单条/批量预测。只读复用冻结实验中的纯结构/特征函数，预处理只拟合训练集；验证选择最佳轮次，测试在独立评价任务执行。记录SVM间隔分数与其他模型概率分数，保存逐条预测和混淆矩阵/ROC/PR。

Web入口：`#/training`、`#/models`，MEMBER和ADMIN按部门访问；历史实验数据和报告保留。训练完成登记实验模型，不自动切换正式审核。NEWS可在完成原稿分组后发起GENERATE准备标签句对；正式校园v3仍为后续独立阶段。

CMD调用同一执行器：

```cmd
runtime\environments\final-training\Scripts\python.exe -B app\scripts\workbench_training.py --config-file runtime\workbench\computations\任务编号\config.json
```

配置由服务端固定路径生成，action为PREPARE/TRAIN/EVALUATE/PREDICT；每次新run目录，保留输出和事件。模型计算使用项目文件锁；已知GPU任务或在线检测占用时返回RESOURCE_BUSY，Web队列等待。神经训练保存最后完整checkpoint，当前界面提供复制参数重跑，尚未提供续训按钮。

## 新闻样本自动准备

`news_samples.py`消费NEWS分组版本，保留原文码点范围，同分区检索候选并复用现有`negative_basis`规则；使用已有Qwen2.5-3B生成事实保持改写，记录数字/显式名称/长度/复制比例与每次输出。未找到有依据的负例只记录缺口，不能随机赋负标签。原文与改写的跨分区精确重复隔离，正反句对冲突隔离；近义未见重复和完整语义正确性仍须在正式材料质量阶段处理。

生成任务逐次提交SQLite。取消/重启后通过“继续样本准备”创建新run，只读复制旧检查点并校验分组版本、参数和算法身份；原run保留。系统可只读复用同一原文身份的历史及同版本Web改写，再执行当前检查。默认max_originals=0处理全部符合长度要求的原稿；用户显式数量只控制本次实验，不改变原正式校园训练规模。

输出四个固定分区、pairs.jsonl、quarantine.jsonl和最后落盘的manifest，包含标签来源、分区类别量、跳过原因、原文/候选位置及SHA。`trainReady`只表示分区具备所需类别，并非训练已执行。Web选择此样本版本后继续原六模型训练、评估及批量预测；语料、权重和业务默认审核模型仍分开管理。

旧“模型实验”已从日常导航移除，旧地址跳转模型管理，历史代码、报告和数据继续保留。
