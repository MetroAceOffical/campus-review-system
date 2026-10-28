# 数据工作台计算内核

此包独立于线上审核模型。数据部门字段只记录材料来源，Web归属必须由服务端账号权限决定。

首阶段支持NEWS原始新闻与PAIRS标签句对，CSV/JSONL、UTF-8/BOM、中文列名/显式映射、最多50MiB/100000条。质量报告统计缺失、长度、来源、日期、类别、重复和冲突；清洗生成新版本，保留来源和旧分区，冲突/坏行隔离。近重复/事件分组和模型训练属于后续步骤，当前版本不会执行它们。

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
