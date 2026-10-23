# 供另一个对话独立检查的交接

用户明确将项目具体验收交给另一个对话。本项目当前状态应称为 **期中候选实现，已开发自检，待独立验收**。本文件提供核查入口，不预设独立检查必须得出通过。

## 建议给新对话的消息

> 请阅读 docs/midterm/independent-review-handoff.md 及其中列出的设计、计划和候选证据，对当前期中版独立检查。先核对源码、配置和运行状态，再按风险选择复验；请区分真实模型、自测故障、冻结实验与未完成质量评价。不要把已有自检结论当作你的验收结论。任何新依赖/环境安装或环境冲突处理先征询我，不覆盖业务数据或私有凭据。

## 工作区与基线

- 本机：`D:\Data\GraduationProjectVersionC`，Windows PowerShell；Asia/Shanghai。
- GitHub私有仓库：`MetroAceOffical/campus-review-system`，阶段通过后由GitHub插件更新main；本机没有Git仓库，不要为了检查擅自初始化或重新checkout覆盖文件。
- M14基线提交：`1fa04fafb769f446fd33ffa8d6aeaf53abea0a0b`；最终M15还含三项编辑器修复、现场闭环和交付文档。最终聊天回执及仓库main给出实际M15提交。`evidence/delivery-files.json`提供候选app源码SHA清单，可独立比对本地是否已有后续变动。
- 运行数据、模型、环境、凭据和构建物未上传GitHub；它们在此电脑仍保留。不要把代码仓库克隆后缺少模型误判为模型已打包交付。

先读：

1. `docs/superpowers/plans/2026-10-23-new-chat-handoff.md`。
2. `docs/superpowers/specs/2026-10-23-midterm-system-design.md`全文，含22节。
3. `docs/superpowers/plans/2026-10-23-midterm-implementation-plan.md`。
4. `docs/midterm/progress.md`、`acceptance.md`、`runbook.md`、`course-evidence.md`、`code-review.md`和`app/README.md`。

原设计/计划中“尚未实施”是编写当时状态；实际候选证据见执行账本，仍须独立核查而非据此跳过检查。原期中报告DOC未改写。

## 运行及凭据

正式网页 `http://127.0.0.1:8080`；开发页面5173是Vite代理，统一入口不管理Vite。主检测18081、OCR18082，业务MySQL3308、测试库 `campus_review_midterm_test`。系统MySQL80不是项目实例。

`app/scripts/status.ps1`分别读取网页和模型ready/busy/runId及进程归属。运行入口与进程日志见runbook，启动不安装依赖/不清库。停止仅使用经过创建时间、exe、完整参数、cwd及runId验证的登记进程，拒绝未知监听或复用PID。

账号为member1/member2/reviewer/admin；随机密码只在 `runtime/private-config/accounts.json`，可在授权的本机登录探针中读取，不要打印进聊天/日志/截图。数据库凭据与内部令牌也不得公开。Java重启后需要重新登录；期中业务数据和持久队列保留。

## 证据导航

| 核查对象 | 文件 / 实际样例 |
| --- | --- |
| 登录、CSRF、角色与组织ACL | M02-http.json，AuthAccessIT；M15四角色403/200矩阵 |
| 草稿、图片身份、Unicode位置、旧版保留 | M03/M09/M10证据，DocumentCodecTest及编辑器测试 |
| 正文、图片、OCR真实调用 | M04/M05/M08证据；不能用默认skip的模型测试证明已运行 |
| 发布及参考切换 | M08/M11证据与LibraryGenerationIT/ReferencePublicationIT |
| 六模型真实指标和看板 | M12-experiments.json，冻结CSV/逐条分数，ExperimentCatalog测试 |
| 超时与恢复 | M13-recovery.json、M13-runtime.json；实际batch8中断后13项完成，旧attempt38保留INTERRUPTED |
| 上限和容量 | M14-capacity.json、M14-cold-capacity.json；18边界，含热缓存/冷OCR区分、20MP近10MiB组合 |
| 最新新输入完整链路 | M15-final-flow.json：稿件15，版本13退回→版本14通过→参考200→新稿版本15在库代6命中 |
| 内部代码复核修复 | code-review.md；导航新建、替换上传重入、取消退出三项Important已用失败回归修复 |
| 最终源文件及版本 | delivery-files.json、依赖lock、迁移文件与frozen-assets.json |

全部Mxx JSON在 `docs/midterm/evidence/`。含业务原文/图片/完整报告的运行探针原件在本地 `runtime/probes/`，没有因为自测方便公开上传。

## 独立检查重点

建议首先核查四角色服务端越权、不可变版本/幂等、正式报告与证据图片ACL、跨组织草稿，以及编辑器路由/并发上传/取消退出后的保存。内部审查发现并修复问题说明自测可能漏边界，不能视为独立检查已完成。

真实业务复验请新建明确测试稿，独立观察新检测、人工退回重提、通过发布、参考实际就绪后新稿命中；已有M15结果只用于定位。自动化故障探针会有意中断项目服务，运行前先读说明，勿把它们当正常浏览入口。

`check.ps1 -Task ALL`使用独立测试库；清理逻辑必须先断言当前库名。不要在业务库做“清表再测试”。默认真实模型测试有明确skip，实际探针单列。模型busy时不并发加发任务；HTTP超时不代表GPU已空闲。原配置不可用时应明确失败，不替换当前模型。

## 已知受限范围

校园复用检索准确率、真实OCR转录CER、改写/同场景难例与标签冲突人工复核仍不完整。PAWS-X复述分类Macro-F1不能当校园审核准确率，噪声压力图不能当图像识别质量证据。容量是本机离散采样，不是长期并发或最低RAM保证。

恢复脚本已在全新目录/3318临时实例导入备份核验并关闭，未覆盖或自动激活业务目录；历史manifest绝对路径与SHA保持。跨机器路径迁移、原目录灾难切换、生产网络部署需单独验证。

协作/自动保存、预检、撤回/替换、发布稿修改、外部抓取、图文一致性等后续入口未开放。基础保留按设计22节映射，不应要求期中提前建成全部未来系统，也不能把预留字段当成已有产品功能。

教师评分模板/权重在本次实现中未另行确认。请将发现、复现条件、影响和证据分级记录，最终是否接受候选由用户决定。
