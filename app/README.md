# 南京传媒学院图文审核系统 · 期中候选版

这是可运行的本机毕业设计候选实现，**待用户指定的另一个对话独立验收**。当前开发自检已覆盖投稿、真实检测、人工退回重提、通过发布、参考入库与新稿检索。功能自测不等同于教师验收或校园检测准确率评价。

## 组成与范围

- `backend/`：JDK21、Spring Boot3.5.16、MyBatis、Spring Security会话/CSRF、MySQL8持久任务。
- `frontend/`：Vue3、Vue Router、Element Plus、Tiptap、ECharts；版本由 `package-lock.json` 固定，TypeScript5.9.3。
- `python/`：冻结BERT文字辅助、DINOv2图片相似、独立PP-OCRv5识别服务；只运行推理，不在线训练。
- `scripts/`：初始化、构建、启动、状态、停止、测试、备份、隔离恢复与实际HTTP验收探针。

期中开放两组织投稿、手动草稿、不可变送审版本、三个独立检测项类别、人工处理、发布、参考管理和管理员实验看板。模型不会自动通过/退回/拒绝稿件。协作编辑、预检、撤回/替换、发布稿修改、外部抓取、图文一致性等后续入口未开放；必要数据与兼容基础见设计第22节和课程证据映射。

## 本机准备

项目根目录为 `D:\Data\GraduationProjectVersionC`。路径、端口、输入上限及超时读取 `app/config/local.json`，不存在时使用 `local.example.json`。当前使用现有JDK21、Maven3.9.6、Node26及两个既有Python环境；不依赖系统默认python或全局npm工具。

代码仓库不包含 `runtime/`、模型权重、数据集、虚拟环境、node_modules、生成静态文件或凭据。当前电脑已经具备这些本地资产；单独克隆GitHub代码不能自动获得模型。冻结资产位置和580项SHA记录见 `docs/midterm/evidence/frozen-assets.json`，环境原记录保留在本机 `validation/`。未提供资产时应明确报缺失，不能运行训练入口冒充恢复环境。

用户要求：新增依赖、安装环境或处理环境冲突前先征询；当前交付不需要再次安装。首次换机器准备必须先核对资产、版本与许可，再决定环境迁移。

## 启动

在项目根目录PowerShell中：

```powershell
# 当前电脑已经初始化，直接启动即可
& app/scripts/start.ps1
& app/scripts/status.ps1
```

正式演示访问 `http://127.0.0.1:8080`。网页由Java同源提供；主检测18081、OCR18082、项目MySQL3308均绑定本机，系统MySQL80独立保留。网页ready和模型ready分别显示，模型加载完成后才处理等待任务。

需要更新代码时，先等待队列空闲，再执行：

```powershell
& app/scripts/stop.ps1 -Component java
& app/scripts/build.ps1
& app/scripts/start.ps1 -Component java
```

`build`用现有项目依赖构建前端并打包Java，不自动执行npm安装。仅在真正的新运行目录且本地模型/环境资产齐全时使用 `app/scripts/init.ps1`；它创建项目3308及专用业务/测试库、迁移和初始账号，不重置已存在数据或旧密码。常规启动不代替初始化。

开发前端可在 `app/frontend` 使用配置所指Node目录的 `npm.cmd run dev`，访问5173，其 `/api` 代理到8080。统一停止入口不管理开发Vite。

## 四账号交付

| 账号 | 角色与页面 |
| --- | --- |
| member1 | 校学生会投稿成员，读写本组织稿件 |
| member2 | 校园融媒体中心投稿成员，读写本组织稿件 |
| reviewer | 审核员，正式检测报告与人工决定 |
| admin | 管理员，参考作品与冻结实验看板 |

随机密码只在本机 `runtime/private-config/accounts.json`，由用户在电脑上查看；不写入README、聊天、截图或GitHub。日常数据库专用账号与内部服务令牌也仅在私有配置，不能发给浏览器。后端重启后需重新登录，稿件及队列保留。

## 演示建议

1. 用member1新建图文稿，选择图片来源，手动保存并重开；最多六图。
2. 送审，查看版本和检测进度。使用reviewer打开当前版本，检查正文定位、图片候选、OCR原图框及质量标记。
3. 人工退回并写原因；member1修改后重提，确认第一版仍保持原内容。
4. reviewer通过第二版；所有账号可在“已发布”查看通过快照，admin可观察自动参考的实际就绪状态。
5. 入库切换完成后，用另一个组织提交包含已发布测试文字的新稿，检查来源命中与自身排除。相似证据不等于抄袭判定。
6. admin打开模型实验，切换模型/口径/页签。只读刷新，不触发训练。

本次新的M15自检对应稿件15、第一版13、第二版14、查询版15，参考作品200、库代6。它们均为明确测试材料，详见 `docs/midterm/evidence/M15-final-flow.json`。独立验收应自行创建新输入，不把这些预置结果代替独立检验。

## 自检与证据

```powershell
& app/scripts/check.ps1 -Task ALL
& app/scripts/check.ps1 -Task M12
& app/scripts/check.ps1 -Task M13
& app/scripts/check.ps1 -Task M14
```

后端测试只使用独立 `campus_review_midterm_test`，清理前核对库名。默认真实模型测试明确跳过，另有实际业务探针及容量证据。真实模型测试 `-RealModels` 要先按测试目录隔离主检测索引与端口，不能直接用业务索引伪装测试；不要为增加通过数量而改模型配置。

容量实测入口 `check_capacity.py` 与 `--cold` 会创建明确测试稿件；中断探针会有意停止项目服务。日常查看请使用证据文件；独立复验先读各脚本说明与runbook。已完成容量探针的再次调用保留原计时，不用空闲轮询覆盖资源观察。

六模型包若缺失，可用现有主Python执行 `app/scripts/export_experiments.py`，从本机冻结数据只读重建。不要执行 `validation/text/round2.py` 的训练或搜索命令来启动网站。

## 停止、备份与恢复

```powershell
& app/scripts/stop.ps1
# 仅当明确需要中断本项目计算时
& app/scripts/stop.ps1 -Interrupt
# 队列空闲，停止Java后创建新的本地备份
& app/scripts/backup.ps1
```

停止默认保留3308；`-StopMysql`才关闭经过datadir认证的项目实例。未知进程、复用PID或不同runId会被拒绝管理。备份包含私有信息，只能本地保留。

`restore.ps1 -Backup <实际备份目录> -Target <全新runtime/restores子目录> -Port 3318` 将备份导入独立临时实例核验后关闭，**不会覆盖或自动激活业务目录**。历史manifest绝对路径及哈希保留；跨机器迁移和原目录灾难切换另行明确处理。完整操作和限制见 [运行手册](../docs/midterm/runbook.md)。

## 交付资料

- [独立检查交接](../docs/midterm/independent-review-handoff.md)：供另一个对话从当前候选开始。
- [验收记录与限制](../docs/midterm/acceptance.md)：PASS、受限和未执行项分开。
- [课程证据](../docs/midterm/course-evidence.md)：EDA、六模型、预处理、选择及实际指标。
- [内部代码复核](../docs/midterm/code-review.md)：问题、复现和修复回归。
- [执行账本](../docs/midterm/progress.md)：阶段GitHub提交、测试日志与全部Ruling。

现有 `Z202508090123_陈泽同_期中报告.doc` 原件未改写。教师评分细则或指定报告格式未在本次实现中另行确认；这些材料提供事实依据，最终独立验收与课程提交由用户安排。
