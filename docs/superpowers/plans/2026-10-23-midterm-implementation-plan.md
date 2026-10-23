# 图文审核系统期中版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已指定在另一个对话实施；本对话只交付设计与计划，不在这里开始产品编码。是否采用子代理由执行对话的适用指令决定，本计划不要求并行代理。

**Goal:** 在2026年10月25日20:00（Asia/Shanghai）前争取完成已确认的期中投稿、真实图文检测、人工审核、发布入库和管理员实验看板，并如实提交课程实验与报告材料。

**Architecture:** Vue网页统一访问Java；Java管理会话、MySQL事务、不可变版本和持久队列；两个隔离Python进程分别承担文字/DINO与OCR。参考库按版本构建切换，报告固定输入、流水线和证据。原冻结实验只读复用。

**Tech Stack:** Vue 3、Element Plus、Tiptap、Apache ECharts；JDK21、Spring Boot3.5.16、MyBatis starter3.0.5、兼容的Spring Security；MySQL8；现有PyTorch/BERT/DINOv2环境与独立PaddleOCR环境。前端新增依赖首次安装时锁定版本，不预设未经核验的版本号。

**Spec:** `docs/superpowers/specs/2026-10-23-midterm-system-design.md`（包括第22节未来预留修订；发生冲突以用户最新指令及设计为准）。

## Global Constraints

- 期中2026年10月25日20:00前、期末2026年11月1日20:00前，Asia/Shanghai；不是全部任务必然按期完成的保证。
- 两组织各一名投稿成员、一名审核员、一名管理员；真实登录、服务端权限；正式报告仅审核员，实验看板仅管理员。
- 最多6张；标题200 Unicode码点、正文10,000码点；单图10×1024×1024字节、20,000,000像素、任边≤8,000；URL≤2,000字符。上限需实际检查。
- 普通请求15秒、上传60秒、正文120秒、图片每图60秒、OCR及比对每图180秒、索引300秒、进程启动每个180秒；可配置，不能视为正常耗时目标。
- 未结束进度3秒轮询，看板10秒可选自动检查；刷新不触发训练或重复检测。
- 人工先决定后模型继续；不改决定、不发送或展示发布后疑点提醒。
- 草稿、快照、发布指针、报告、参考内容独立；数据库持久队列；单worker整篇顺序处理；失败项独立重试。
- 编辑位置与图片身份分开，偏移为Unicode码点，OCR框回到原图；历史内容、文件、配置及证据不覆盖。
- 紧凑间距、全部界面边框直角、文字分级、浅色/深色/自定义主题色；正式版无原型和实现说明文字。
- 不开放期中以外的协作、预检、撤回/替换、发布稿修改、图文一致性、外部抓取、授权流程等入口；落实设计第22节必要基础，不提前建完整后续系统。
- 不改写冻结数据/模型/指标；不重训六模型；不以旧报告或故障桩作为真实网站结果。实验核验失败先定位差异。
- 路径/端口/凭据外置；仅管理项目独立3308 MySQL和项目进程，不改变系统MySQL80或旧环境全局配置。
- 当前工作区未据此假定存在Git。先检查；已有仓库按现有规则分任务提交。没有仓库则保留文件清单和哈希，不为提交文档擅自初始化或改写仓库。

## Review Focus

1. 表情、换行、跨加粗文字仍能准确定位，改动图片不串证据（M03/M10）。
2. 同一用户两个窗口、双击和超时重发不会覆盖草稿或重复送审/决定（M08）。
3. 成员直接请求证据图片/报告不能因“有权看稿件”而越权（M02/M03/M10）。
4. 模型或索引版本升级后不能混用向量，旧配置缺失不能悄悄换当前模型（M04/M06/M13）。
5. 请求超时不等于GPU已空闲，重启与迟到结果不能并发堆积或覆盖新执行（M07/M13）。

## 1. 执行入口与既有资产

先读设计全文、可行性报告第16节及《剩余可行性验证结果.md》的B/C结论。确认工作区是`D:\Data\GraduationProjectVersionC`，读取适用AGENTS.md，盘点已有变动后再写。

| 只读资产 | 用途 |
| --- | --- |
| validation/text/round2/selected/、search/、evaluation/ | 模型选择、训练历史、逐条预测及测试结果 |
| validation/text/round2/test-summary.csv、search-summary.csv、preprocessing.json | 六模型看板 |
| validation/remaining/text/run_text.py、text_core.py、selection.json、data/ | 提取文字方法与参考内容，去除实验专用分支 |
| validation/remaining/image/evaluation/evaluate.py、selection.json及相关模型目录 | DINO编码、阈值、变形样例与模型清单 |
| validation/remaining/vision/、vision/env-ocr/ | OCR运行方式、配置、模型和框结果；不重建整个环境 |
| validation/remaining/engineering/ | 事务/竞态及3308实例管理参考，不直接当正式产品 |
| validation/remaining/final_verify_bc.py | 已保存证据复算；不等同于产品验收 |

冻结证据先做只读清单/哈希。已有核验入口仅在确认它不会重训或覆盖选择文件后执行，发现差异记录原因，不为了“通过”改历史输出。

视觉参考为本对话认可的交互演示：
`C:/Users/MetroAce/.codex/visualizations/2026/10/22/01a16351-6cfa-7ce3-acfd-41062e5feeec/campus-review-demo.html`。
若新对话环境不能读该目录，先按设计11.1重现风格并回报；不要声称已读取。演示中的虚构业务数值、模拟身份切换和execCommand编辑不是正式实现。仅提取布局风格，不复制为已接后端的成果。

## 2. 计划文件结构

以下为计划创建的路径，不表示文件已存在。相邻职责可在实际实现中合理合并，但不得产生两套检测实现或一个巨大的接口分发器。

| 路径 | 职责 |
| --- | --- |
| app/backend/pom.xml；src/main/resources/application.yml | 正式Java工程和配置 |
| app/backend/src/main/java/local/campus/review/ | auth、content、manuscript、review、detection、reference、experiment各业务包 |
| app/backend/src/main/resources/db/migrations/ | 有序SQL迁移、校验与种子 |
| app/frontend/src/ | Vue路由、API、基础布局和业务页面；主题与样式独立 |
| app/python/campus_shared/contracts.py | 无重型依赖的请求/结果schema与验证 |
| app/python/campus_detection/{text,image,library,http_service}.py | 主检测计算与HTTP适配 |
| app/python/campus_ocr/{recognizer,http_service}.py | OCR计算与HTTP适配；由独立环境启动 |
| app/python/tests/ | stdlib unittest，模型真实探针与纯单元测试分开 |
| app/scripts/{init,start,status,stop,check,backup,restore}.ps1 | Windows管理、检查、备份/恢复入口 |
| app/config/local.example.json | 不含凭据的配置示例 |
| docs/midterm/{progress,acceptance,runbook,course-evidence}.md | 执行记录、验收、操作与课程材料 |
| runtime/ | SQL数据、文件、派生物、索引、实验包、日志和私有配置；不提交凭据 |

后端验证采用starter-test/JUnit；事务集成用项目3308中的独立`campus_review_midterm_test`库，不用H2伪装MySQL行为，不强制Docker。测试清理前必须确认当前库名精确等于测试库，禁止清理业务库。Python优先unittest，前端单元测试与浏览器检查采用首次集成时实际可用的工具，不重复安装浏览器。

`check.ps1 -Task Mxx`由M01建立统一入口，映射到下述确切测试类/模块；未配置的Task必须非零退出，不能空跑成功。模型测试明确加`-RealModels`，无模型不得按成功统计。未接通页面可以在进度中记未完成，正式交付不保留假成功按钮。

## 3. 任务清单

每个任务先写列出的关键行为测试并确认失败，最小实现后转绿；简单样式/文案不写镜像测试。运行结果与实际命令记入progress。每任务结束保存可恢复检查点；Git可用则提交该任务，未用Git则更新变动和哈希清单。

### M01：运行基础、迁移和可核对的检查入口

**Files:** 创建`app/config/local.example.json`、`app/scripts/{init,status,check}.ps1`、`app/backend/pom.xml`、`app/backend/src/main/resources/db/migrations/001_core.sql`、`docs/midterm/progress.md`；测试`app/backend/src/test/java/local/campus/review/bootstrap/MigrationIT.java`。

**Interfaces:** 配置提供Java/模型Python/OCR Python/MySQL路径、端口和runtime根目录。`MigrationRunner.apply(Connection, Path) -> List<AppliedMigration>`校验checksum；`check.ps1 -Task <id> [-RealModels]`返回真实退出码。

- [ ] 写`MigrationIT.reapplyPreservesExistingData`：连续初始化后用户行不重复、既有稿件不清空、迁移checksum变化拒绝静默重用；测试DB必须为`campus_review_midterm_test`。
- [ ] 运行`app/scripts/check.ps1 -Task M01`确认新测试未实现而失败。
- [ ] 建最小工程及设计15节表/约束，引用循环在后续迁移补齐；创建新项目3308实例与专用凭据，盘点并锁定首次使用依赖；已有服务不动。记录冻结资产哈希。
- [ ] 重跑M01通过，证明数据库可连接、迁移可重复、测试库保护生效。记录工具实际路径及版本，不写安装截图代替可用结果。

### M02：真实登录、组织权限与应用外壳

**Files:** 创建后端`auth/{SecurityConfig,AuthController,CurrentUser,AccessPolicy}.java`；前端`src/{main.ts,router.ts,api/http.ts,layouts/AppLayout.vue,views/LoginView.vue}`；测试`auth/AuthAccessIT.java`。

**Interfaces:** `CurrentUser(userId:String,role:Role,organizationIds:Set<String>)`；`AccessPolicy.requireOrganization(user, organizationId)`；`requireReviewer(user)`；`requireAdmin(user)`。前端`request<T>(path, options) -> Promise<T>`携带会话/CSRF，401保留页面内容并要求重新登录。

- [ ] 写`AuthAccessIT`：四账号角色正确；缺会话401；成员请求实验接口403；伪造X-User无效；缺CSRF的写请求被拒；退出后的旧会话无效。
- [ ] M02运行失败后，实现设计20.1的Spring Security会话和密码哈希、CSRF、当前关系授权；初始化四账号两组织，登录后按角色显示真实导航，不提供演示切换。
- [ ] Vue外壳落实直角、间距、文字层级与主题按钮，主题偏好保存到浏览器；不引入在线训练、注册审批等页面。
- [ ] M02转绿；用实际会话验证后端权限，不能只截图前端隐藏菜单。新增需要后续任务完成的接口先在测试中模拟服务，不作为业务已完成证据。

### M03：图文结构、受控文件与草稿保存

**Files:** 创建后端`content/{DocumentModels,DocumentCodec,FileController,FileService}.java`、`manuscript/{DraftController,DraftService}.java`；前端`src/components/CampusEditor.vue`、`src/editor/CampusImage.ts`、`src/views/EditorView.vue`；测试`content/DocumentCodecTest.java`、`content/FileAccessIT.java`、`manuscript/DraftIT.java`。

**Interfaces:** `DocumentCodec.validateAndExtract(DocumentInput) -> ExtractedDocument(plainText,positionMap,contentHash,schemaVersion,extractorVersion)`；`DraftService.save(user, manuscriptId, expectedRevision, input) -> SavedDraft`；编辑器`modelValue:DocumentInput`与`update:modelValue`，图片节点按设计16.1。

- [ ] 测试`unicodeAndFormattingOffsets`：`A😀中\n文`（其中\n为一个换行）的码点长度为5，表情之后区间不偏移；跨bold/list匹配能还原原文字；图片移动不改fileId；复制节点产生新nodeId。
- [ ] 测试`oldRevisionCannotOverwrite`、`evidenceFileIsNotMemberBodyFile`、`uploadLimitAndDecodedFormat`：旧revision409，成员读正式证据文件被拒，改后缀不能绕格式，超过10MiB被拒。M03先确认失败。
- [ ] 实现受控上传/绑定、Tiptap结构、图注/来源、保存及未保存保护；新建空稿允许保存，完整来源校验留给送审；原图不覆盖，未绑定文件延迟处理。
- [ ] M03转绿；浏览器实际插入、移动、替换、保存重开，检查图文位置与来源。没有后端保存响应不得显示“已保存”。

### M04：主检测模块与真实文字/DINO探针

**Files:** 创建`app/python/campus_shared/contracts.py`、`campus_detection/{text,image,http_service}.py`；测试`app/python/tests/test_detection_contract.py`、`test_text_real.py`、`test_image_real.py`。

**Interfaces:** 普通函数`detect_text(request:dict, library:dict, models:dict)->dict`、`detect_image(request:dict, library:dict, models:dict)->dict`。request/result字段按设计17.3/18.1；`scene/inputSnapshotKey/inputSha256`与业务状态无关，库通过明确manifest输入。HTTP只做验证、调用、序列化，不复制算法。

- [ ] 契约测试拒绝不匹配的任务身份/配置；空库返回受限状态；不要求真实数据库送审行。写真实样例对照测试，确保不运行T0、不插入已知anchor或夹具、不把alpha=0改为语义排序。
- [ ] 运行`check.ps1 -Task M04`确认缺实现失败；再以`-RealModels`加载冻结权重，保留库快照和配置标识。
- [ ] 提取冻结函数，保留48/12分块及开发阈值；计算前排除同稿来源，再截取候选；DINO使用实际已验处理器。模型保持加载，服务绑定127.0.0.1:18081。
- [ ] 契约及真实探针通过；记录实际模型哈希、输入、来源和输出，不使用已有测试报告当本次输出。离线脚本直接调用同一函数进行对照。

### M05：隔离OCR服务与识别坐标契约

**Files:** 创建`app/python/campus_ocr/{recognizer,http_service}.py`；测试`app/python/tests/test_ocr_contract.py`、`test_ocr_real.py`。

**Interfaces:** `recognize(image:dict, config:dict)->dict`返回原图宽高、变换、行ID/文字/置信度/多边形和qualityFlags；HTTP `POST /recognize`仅独立OCR环境启动，端口18082；后续Java调度串接M04文字检索。

- [ ] 测试`empty_ocr_is_not_no_reuse`：空识别必须`textSearchStatus=NOT_RUN`且`noReuseClaim=false`；框和行数量一致，坐标不越界，缩放框可逆回原图。
- [ ] M05先失败，再复用已验证PP-OCRv5 CPU配置实现；不得把主PyTorch环境改成OCR环境。
- [ ] 真实清晰/模糊图片实际识别，保留真实错误及质量标记；不注入转录真值作为模型输出。
- [ ] M05转绿；记录进程配置、输入哈希和识别行，证明接口结果来自本次运行。

### M06：参考作品、特征缓存与索引版本

**Files:** 创建后端`reference/{ReferenceService,LibraryGenerationService,ReferenceController}.java`；Python`campus_detection/library.py`；测试`reference/LibraryGenerationIT.java`、`app/python/tests/test_library.py`。

**Interfaces:** `build_library(manifest:dict, config:dict)->dict`，返回READY产物路径、哈希、逐项结果；`LibraryGenerationService.activate(generationId, expectedCurrentId)`原子切换；`ReferenceService.create(user,input)`持久保存revision和job。先建立服务能力，后台消费由M07接通。

- [ ] 测试`failedBuildKeepsCurrentGeneration`、`incompatibleFeatureSpaceIsRejected`、`publishedImportDoesNotBecomePublication`；同文件不同模型配置不能命中同一处理缓存。
- [ ] 运行M06确认失败；实现新目录构建/READY校验/事务切换、部分可用与停用待切换；导入内容不能绕过处理状态直接可用。
- [ ] 从194篇及已收图片整理首批来源，区分正式校园参考与合成夹具，记录实际导入数。新TF-IDF按该版本重建，图片/OCR缓存按配置复用。
- [ ] M06转绿；实际新增参考后构建，验证可检索；停用切换后新批次不含该条目，旧报告所需文件仍保留。

### M07：MySQL队列、分项执行及结果有效性

**Files:** 创建后端`detection/{JobWorker,DetectionService,AttemptRepository,DetectorClient}.java`；测试`detection/{QueueIT,LateResultIT}.java`。

**Interfaces:** `DetectionService.createFormalBatch(versionId,inputHash)->batchId`；`JobWorker.runOne()->JobOutcome`；`DetectorClient`调用M04/M05；`AttemptRepository.completeIfCurrent(attemptId,result)->boolean`同时检查有效执行、取消标记和正式版本生命周期。

- [ ] 测试仅一个worker认领、每批固定库/pipeline、13项逐项保存、一项失败不丢其他项；`decidedVersionStillAcceptsResult`为true，`cancelledBatchRejectsLateResult`为false；后者为基础条件测试，不开放撤回入口。
- [ ] M07失败后，实现事务认领、事务外模型调用、正文→逐图相似→逐图OCR文字比对、参考准备/重试job；OCR中间成功结果可按同配置复用。
- [ ] 真实正文加图片任务通过Java→两Python→数据库；未就绪显示等待，OCR故障明确失败；固定阈值与权重写manifest。
- [ ] M07转绿；模拟旧响应晚到不覆盖当前attempt，测试仅用于故障控制，正常真实模型链另留证据。

### M08：幂等送审、人工决定、发布和入库事务

**Files:** 创建后端`manuscript/{SubmissionController,SubmissionService}.java`、`review/{ReviewController,ReviewService}.java`、`reference/PublicationService.java`；测试`manuscript/SubmissionIT.java`、`review/DecisionIT.java`。

**Interfaces:** `SubmissionService.submit(user,manuscriptId,key,expectedRevision,input)->SubmissionReceipt`；`ReviewService.decide(user,submissionId,key,decision,reason)->DecisionReceipt`；`PublicationService.publishApprovedVersion(versionId)`在决定事务内更新发布与持久入库安排，不等待模型。

- [ ] 测试同key同内容返回同version，不同内容409；双窗口修改冲突；并发决定只成功一次；decision时记录检测快照；人工先通过后报告完成，不改决定、不产生提醒。
- [ ] M08先失败，再实现设计5.1/17.2事务；同稿版本序号唯一、稿件行锁、publication_state分离、首发默认许可锁定、操作事件同事务。
- [ ] GET发布内容只从已通过快照取，GET正式report只给审核员；参考入库从该通过快照取，不读草稿。单一决定约束不用于阻塞未来publication_action。
- [ ] M08转绿，真实HTTP走送审→实际检测→人工决定→发布→参考处理→新查询命中；这是第一条真实业务闭环里程碑。

### M09：投稿列表、编辑送审与版本历史

**Files:** 创建前端`src/{views/ManuscriptListView.vue,views/SubmissionHistoryView.vue,api/manuscripts.ts}`，修改`EditorView.vue`；浏览器检查`app/frontend/tests/submission-flow.spec.ts`。

**Interfaces:** `saveDraft(id,expectedRevision,input)`、`submitDraft(id,key,expectedRevision,input)`、`getSubmissions(id)`使用M03/M08契约；共享输入类型`src/types/document.ts`与后端schema一致。

- [ ] 浏览器测试上传未结束不能送审、网络保存失败内容仍在、401重新登录不清编辑、重复提交不建两版。
- [ ] M09检查先失败，再接真实列表、状态操作限制、来源字段、保存/送审、历史切换；成员不请求或接收正式报告证据。
- [ ] 完成退回→修改→重提；待审不开放编辑/撤回，拒绝不能重提；不显示未实现按钮或开发说明。
- [ ] M09通过；检查六图位置及来源、第一版与第二版快照；无自动保存不能显示自动保存文案。

### M10：审核工作台、正文/图片/OCR证据

**Files:** 创建前端`src/views/{ReviewQueueView,ReviewDetailView}.vue`、`src/components/{TextEvidence,ImageEvidence,OcrEvidence}.vue`、`src/api/review.ts`；后端`detection/ReportController.java`；测试`detection/ReportAccessIT.java`、前端`tests/review-flow.spec.ts`。

**Interfaces:** `getFormalReport(batchId)`、`getProgress(batchId)`、`retryItem(itemId,key,expectedAttemptId)`；`codePointRangeToEditorRange(document,map,start,end)`在`src/editor/positions.ts`实现，与M03映射契约一致。

- [ ] 测试成员直接访问report及EVIDENCE_IMAGE拒绝；表情和跨格式片段定位；图片移动不混OCR框；空OCR不显示无复用；重试只改变失败项。
- [ ] M10失败后接通左右对照、三类证据、历史版本、决定原因校验及失败重试；证据ID不因刷新变化。
- [ ] 未结束任务3秒刷新，离开停轮询；人工决定后继续处理但无疑点提醒。字面、语义、图片分数分别显示，不造抄袭百分比。
- [ ] M10通过；按认可界面完成现场新稿审核，证明可追溯到对应输入及真实来源。

### M11：参考管理与发布展示页面

**Files:** 创建前端`src/views/{ReferenceListView,ReferenceEditorView,PublicationListView,PublicationDetailView}.vue`、`src/api/references.ts`；测试`tests/reference-publication.spec.ts`。

**Interfaces:** 复用M03编辑器与M06/M08服务；发布查询按publication_state，来源导入不影响发布列表。

- [ ] 测试手动参考不发布、部分失败仍可用、停用先显示待切换、切换后生效、失败保留旧库、标题搜索可用。
- [ ] M11失败后实现管理员手动导入及来源说明、状态/重试/启停；不加参考原地编辑、批量导入或URL抓取。
- [ ] 全登录身份可阅读发布稿，内部报告/原因不出现在发布页；查看发布图不因此获得全部未发布文件权限。
- [ ] M11通过；管理员导入及站内入库各实际验证一次，新查询真实命中。

### M12：真实实验包与丰富模型看板

**Files:** 创建`app/scripts/export_experiments.py`、后端`experiment/{ExperimentCatalog,ExperimentController}.java`、前端`src/views/ExperimentView.vue`、`src/components/experiments/{OverviewCharts,EvaluationCharts,TrainingCharts,ComparisonCharts}.vue`；测试`app/python/tests/test_experiment_export.py`、`experiment/ExperimentAccessIT.java`。

**Interfaces:** `export_experiment(frozenRoot:Path,output:Path)->Manifest`；manifest及metrics/history/search/curves按设计17.4；`GET /api/experiments/{id}`提供contentVersion及图表能力。

- [ ] 从实际CSV断言BERT官方Macro-F1约0.7369837959240795、子集约0.7239446804664196；6模型、20配置、6混淆矩阵一致；曲线逐轮点数等于history记录。
- [ ] M12先失败，再只读转换：ROC/PR从真实score算，SVM不称概率；不同任务/测试口径不混；可用约15—20图，不能补造数据凑数。
- [ ] 实现四页签、指标/模型/口径切换、悬停值、手动与10秒可选刷新；原子发布实验包，无变化只更新检查时间，坏包保留上次图表。
- [ ] M12转绿；管理员API允许、其他角色拒绝；新固定实验包可被刷新读取，不触发训练。此数据整理可在M03之后作为独立工作进行，但不要求并行代理。

### M13：超时、进程恢复、索引兼容与运行入口

**Files:** 创建/完善`app/scripts/{start,status,stop,backup,restore}.ps1`、后端`detection/{RecoveryService,ProcessSupervisor}.java`；测试`detection/RecoveryIT.java`、`app/python/tests/test_pipeline_compatibility.py`；更新`docs/midterm/runbook.md`。

**Interfaces:** `RecoveryService.recoverPreviousRun(runId)`仅重排未完成项；`ProcessSupervisor.ensureReady(component)`只管理本项目验证过的进程句柄/runId；备份/恢复读取明确runtime与数据库配置。

- [ ] 写`timeoutDoesNotDispatchIntoBusyProcess`、`lateAttemptDoesNotOverwriteRetry`、`restartKeepsCompletedResults`、`oldPipelineMissingFailsExplicitly`、`unknownProcessIsNotStopped`测试。
- [ ] M13先失败，再实现设计18/19超时恢复、版本兼容拒绝、旧库保留；旧配置缺失返回CONFIG_UNAVAILABLE，不换当前模型重试。
- [ ] 实际停Java、停任一Python、模型调用超时受控故障、重启后读取数据库；确认发布和旧证据还在。备份在独立恢复目标验证，不覆盖业务目录。
- [ ] M13转绿；统一启动后网页和模型ready分别可查，停止只影响项目进程，原MySQL80保持原状。

### M14：六图和输入上限专项验证

**Files:** 创建`app/scripts/check_capacity.py`、`app/frontend/tests/boundary-flow.spec.ts`、`docs/midterm/acceptance.md`；仅必要时调整配置，记录差异。

**Interfaces:** `check_capacity(config,fixtureManifest)->EvidenceSummary`使用正式HTTP接口，保存输入哈希、任务ID、实际耗时/资源和结果，不直接改数据库冒充完成。

- [ ] 验证200/201标题码点、10,000/10,001正文码点、6/7图；10MiB附近文件、20MP及8,000边界；有效/伪装格式；超限保留编辑内容。
- [ ] 用真实长稿、6张代表性图跑完整文字/图片/OCR；再测接近上限组合。记录当前模型配置和最低可用主存，区分排队等待与计算时间。
- [ ] 多稿排队及模糊/空OCR可解释，部分失败不丢其他结果。若上限无法稳定运行，报告实际阻碍与建议，不暗中截断或删掉6图要求。
- [ ] 输出实际PASS/FAIL/受限/未执行清单，与正常模型样例及故障桩分开；不把一次成功推成生产吞吐结论。

### M15：课程材料、提交候选和交接

**Files:** 完成`docs/midterm/{runbook,acceptance,course-evidence,progress}.md`、`app/README.md`，按用户/课程要求另行生成报告产物；不擅自改写现有期中报告原件。

**Interfaces:** README给出实际配置、初始化、启动、四账号交付方式、演示步骤、停止/恢复入口；acceptance逐项引用任务ID与运行证据，course-evidence对应课程评分要求。

- [ ] 对照设计第13/21节及原需求第22节映射：期中实现、基础预留、后续功能、质量缺口逐项区分。
- [ ] 现场新输入→真检测→退回重提→通过发布→入库→新稿检索，四账号验证越权；看板按原数据核对。截图不包含密码/内部令牌。
- [ ] 整理六模型、EDA、预处理、调参、测试、图表、环境可用和复现说明；若教师模板/评分要求不在现有资料中，列为需用户提供，不编造。
- [ ] 按实际通过检查形成可提交候选；10月24日形成候选、25日留验收和报告是目标安排，不是已经完成或教师新增期限。执行若已晚于该节点，按实际剩余时间反馈，不倒填。
- [ ] 保存依赖lock、模型/数据/配置/迁移版本、备份与未完成项；期末等待评分标准，优先检测提升，不默认把所有协作功能塞进一周。

## 4. 任务依赖与执行优先级

主线：M01→M02→M03→M04/M05→M06→M07→M08→M09→M10→M11→M13→M14→M15；M12在基础配置和实际数据可读后独立推进，最终并入M15。斜杠表示同一阶段可顺序完成，不是授权并行代理。

M08后应看到后端真实闭环，M10后应看到浏览器真实闭环。达到中间里程碑不能宣布期中全部完成。任务预计成本由执行实测更新，不用模型推理秒数推算开发工时，也不用固定人工周数推算agent日历速度。

若时间不足：优先保护实验与课程材料，并及时列出网站剩余项和影响；用户批准的范围仍有效，不能把“优先级”变成自行删减。截图和演示不得隐藏未接通功能或用假结果代替。

## 5. 自审与交接记录

- 设计3—5/15—17：M01—M03、M08—M11覆盖。
- 设计6—9/18：M04—M08、M10—M13覆盖。
- 设计10及模型数据真实性：M12、M15覆盖。
- 设计11.1认可视觉规范：M02、M03、M09—M12及浏览器验收覆盖。
- 设计12/19—21：M01、M13—M15覆盖。
- 设计22必须基础：M01的迁移、M02组织权限、M03快照/节点/用途、M04统一计算、M06兼容索引、M07场景/取消边界、M08双状态/许可/事件、M10证据ID、M12任务型指标与M13恢复共同覆盖；后续表/页面不在本次施工。

计划中的命令和文件是执行目标，目前未创建正式app工程、未运行这些产品测试。执行者需先确认环境再创建文件，测试输出必须来自实际运行。

用户已选择新对话执行。本计划交用户审阅后，与设计和交接说明一起提交到该对话；本对话不创建新任务、不代替用户向其他对话发送消息。
