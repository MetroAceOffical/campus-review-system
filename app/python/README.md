# 检测计算模块

主环境复用 `validation/text/env/python.exe`。不要重新安装训练环境。OCR使用另一独立环境，在M05接入。

```powershell
app/scripts/check.ps1 -Task M04
app/scripts/check.ps1 -Task M04 -RealModels
$env:PYTHONPATH = "$PWD/app/python"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:HF_HUB_OFFLINE = '1'
& validation/text/env/python.exe -B -m campus_detection.http_service
```

服务只绑定127.0.0.1:18081，所有接口需要本地私有文件 `runtime/private-config/internal-token` 中的令牌；由Java发送，不发浏览器。GET /health单独报告模型ready和busy；并发计算返回PROCESS_BUSY。

`detect_text(request,library,models)` 与 `detect_image(...)` 是离线和HTTP共用的普通函数。正文采用冻结48/12分块、字符TF-IDF、公共片段抑制和字面证据；BERT只给候选的部分语义窗口，不改变alpha=0排序，不运行T0或注入已知anchor。图片使用已核验DINOv2-small慢速PIL处理器、FP32和归一化CLS向量。

M04实际验证包括194篇参考内容的冻结排序/分数回归、候选前自身排除、重新编码图片对冻结参考向量、HTTP与离线相同证据，以及身份/配置/空库/损坏索引/内部认证/忙进程边界。非RealModels运行明确跳过真实推理，不计为模型验证成功。

模型先从基础配置构造后加载已冻结微调checkpoint，基础构造阶段的classifier初始化提示不代表重新训练或最终使用随机分类头；实际微调权重SHA256和冻结分数回归见docs/midterm/evidence/M04-*.json。

完整本地报告与输入只存runtime/probes；仓库仅上传不含源材料的哈希和检查摘要。M04仍是独立计算/HTTP验证，持久队列和实际投稿连接由M06—M08实现。
