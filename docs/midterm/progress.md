# SDD ledger — plan: docs/superpowers/plans/2026-10-23-midterm-implementation-plan.md

## 实施基线

当前完成状态：M01—M11完成；M12实验看板、M13恢复、M14容量与M15交付待完成。下文各阶段中的“进行中”是当时记录，以对应最终验收为准。

2026-10-23（Asia/Shanghai）开始。已完整读取交接、设计（含第22节）、实施计划、可行性报告第16节及剩余验证B/C和最终结论。无适用AGENTS.md，无Git仓库，无正式app工程。

Ruling: 按计划Global Constraints在当前目录实施，以文件SHA256清单保存检查点；不初始化Git、不创建依赖Git的工作树和skill辅助账本。计划专用账本统一为本文件。没有提交记录的成本由检查点清单与测试日志弥补。

## 接口预检

| 生产→消费 | 核对结果 |
| --- | --- |
| M01→M02/M03/M06/M07/M08 | 迁移按设计15节与22节；后续外键用增量迁移，测试库隔离 |
| M02→M03/M08/M10/M12 | 会话当前成员关系；正式证据仅审核员，实验仅管理员 |
| M03→M04/M08/M09/M10 | 不可变输入、码点偏移、图片nodeId与fileId分离 |
| M04/M05→M06/M07 | 普通计算函数、完整身份及配置校验，OCR子阶段独立 |
| M06→M07/M08/M11/M13 | 开始时固定库，READY后原子切换，历史保留 |
| M07→M08/M10/M13 | 决定不取消计算；取消/旧attempt拒绝回写 |
| M08→M09/M10/M11 | 幂等先于状态检查，发布与审核状态分开 |
| M12→M15 | CSV/JSON真实包，只读刷新，按taskType定义指标 |
| M13→M14/M15 | 超时后不继续派发忙进程，保留成功结果，单独模型就绪 |

目前未发现设计与任务之间需要调整的接口冲突。

## 任务状态

- M01：完成，GitHub已上传，见后文提交记录。
- M02：后端认证测试及前端单元测试通过，进行浏览器和统一检查入口核验。
- M03—M15：未开始，未声称完成。

## 已核验环境

- JDK 21.0.11：D:/Dev/Runtime/JDK/jdk-21.0.11。
- Maven 3.9.6：D:/Dev/Runtime/Maven/apache-maven-3.9.6。
- Node v26.7.0；主Python 3.11.17；PyTorch 2.8.0+cu128，成功导入。
- 3308/8080/18081/18082初始无监听。冻结目录只读复用。
- 当前日期尚未超过期中截止；所有容量与端到端验收仍未执行。

## M01运行记录

- `runtime/logs/M01-red.log`：首次确认MigrationRunner/DatabaseTarget缺失导致测试编译失败。首次依赖解析失败另由日志保留，不能冒称行为测试失败。
- Maven沿用全局镜像ID在项目settings覆盖为官方Central；全局settings与旧cache未改。新增Security/JUnit依赖进入runtime/m2-repository。
- 沙箱内启动的MySQL未能完成可连接就绪；改用获准的沙箱外项目进程启动后，3308 MySQL8.0.46真实可连。
- `app/scripts/check.ps1 -Task M01`：MigrationIT 2 tests / 0 failures / 0 errors（14:50 Asia/Shanghai）；运行安全测试1项通过。测试仅使用campus_review_midterm_test。
- 冻结清单580项已写evidence/frozen-assets.json，后续重新盘点仅校验不覆盖。
- 系统MySQL80实查Running；未停止或修改。
- M01仍待最终重复初始化和工程检查点，未提前标完成。

## 新增用户约束（2026-10-23）

- 每阶段验证后上传GitHub；用户授权私有仓库campus-review-system，目前用户自行创建后提供链接。不得上传凭据、runtime、依赖环境、模型权重或数据集。
- 新环境、新依赖、环境冲突须事先说明并获准。此前Java依赖已下载，现已告知用户。
- 用户已批准项目内安装Vue3/VueRouter/ElementPlus/Tiptap/ECharts及Vite/TypeScript/Vitest/VueTestUtils/jsdom等构建测试依赖；禁止全局安装或改其他环境。

## M02后端检查点

- RED：SpringBoot配置尚不存在，见runtime/logs/M02-red.log。
- GREEN：真实3308测试库，AuthAccessIT 4项 + MigrationIT 2项全部通过（2026-10-23 14:58 Asia/Shanghai）。四账号实际密码校验、会话ID轮换、CSRF、退出、伪造X-User、角色拒绝已验。
- 初始密码只在runtime/private-config/accounts.json；再次启动不重置既有密码。测试默认不打印HTTP请求以避免失败日志泄密。
- M02仍在进行；前端外壳及浏览器核验尚未完成。M03—M15未开始。

Task M01: complete — MigrationIT 2/2（runtime/logs/M01-final.log），运行目录保护1/1；重复init应用0项新迁移；未知Task真实非零退出。未初始化Git，待用户仓库链接后上传此阶段检查点。M02后端测试通过不代表M02页面完成。

M01 GitHub插件上传已完成：main提交14e2c0661d8d1f3a044a617c491112813ea2dd14。仓库为私有，未上传runtime、凭据、模型或数据集。后续阶段继续用插件提交，无需本机Git登录。

### M02前端记录

- 经用户批准，在app/frontend安装并锁定依赖，未全局安装。Vue3.5.44、Router4.6.4、ElementPlus2.14.7、Tiptap3.32.0、ECharts6.1.0、Vite8.3.5、Vitest5.0.5等详见package-lock.json。
- TypeScript7.0.2与vue-tsc3.3.13发生package exports不兼容；已报告并获准仅在本项目降为TypeScript5.9.3，重跑构建成功。不修改其他项目。
- 前端RED：模块尚未实现；GREEN：会话/CSRF请求2项、主题可读性1项通过。构建成功，有ElementPlus初始包体积提示；不影响本机运行，后续页面按需加载时处理。
- M02仅认证与外壳；暂空业务路由是开发接入点，不能作为列表/实验/发布功能完成证据；后续M09/M11/M12必须替换为真实页面后才整体交付。

- 实际Java同源服务8080已运行：四账号真实HTTP登录、会话轮换、HttpOnly/SameSite=Lax、缺CSRF拒绝、退出失效均通过，非敏感证据M02-http.json。
- 浏览器实开127.0.0.1:8080/#/login并核对截图：正式Vue登录页、直角边框、文字层级正常；尚未完成编辑/审核等后续业务浏览器流程。

Task M02: complete — 统一check -Task M02：AuthAccessIT4/4、前端3/3及生产构建通过；全后端6/6通过；四账号真实HTTP会话探针通过。M02范围仅认证、权限基础与外壳，业务页面及六图等仍待后续任务。

M02 GitHub插件上传完成：main提交0c0f3e38638ed0b42cc30cb58b4b78de591385aa。M03开始，先验证文档提取/码点、草稿revision与文件权限。

## M03进行中

- 实现版本化Tiptap结构校验、码点位置映射、来源与图片身份、canonical内容哈希、受控上传与按用途鉴权、草稿revision事务保护和MANUAL操作事件。
- 复用既有Pillow13.0.0以独立轻量子进程解码JPG/PNG/WebP；不安装Java图像插件、不加载模型；动画/伪装/尺寸超限拒绝，原图独立存储。
- 文档与HTTP接口先RED：DocumentCodec缺失，文件与草稿接口404；修复后M03后端7/7、全后端13/13通过。
- MySQL驱动DATETIME返回LocalDateTime；修正错误的Timestamp转换后，保存响应与revision冲突测试通过。
- 前端Tiptap已实现格式、图片上传/拖动/前后移动/替换/删除、图注与来源、手动保存及未保存保护。来源声明在替换后清空并要求确认。
- 实际编辑器回归发现“把复制图插在原图前方会改掉原图nodeId”；已先复现失败，再用事务位置映射保留原节点，复制使用新ID。该用例RED→GREEN。
- 当前前端6/6、Python图片与运行目录测试2/2、前端生产构建通过；M03浏览器插图/移动/替换/保存重开和真实HTTP新稿仍待核验，因此尚未标完成。
- 已能读取演示HTML的最终紧凑直角样式，视觉实现沿用设计11.1；不把其虚构业务或模拟身份接入正式系统。

### M03最终验收（2026-10-23 16:08 Asia/Shanghai）

- 浏览器实测补出了三个单元接口测试未覆盖的问题：嵌套登录form触发原生GET、Vue响应式对象不能structuredClone、选中图片后上传会覆盖原图。均补RED用例、修复并转GREEN。登录请求改为唯一表单拦截且显式POST；受影响的本机初始测试凭据已更新，未写入验证文件。
- Tiptap实际有序列表包含attrs.type=null，原后端白名单拒绝；新增真实结构回归后白名单接受标准列表标记，并验证start范围。
- 浏览器完成真实成员登录、新建稿件、含表情正文、两图上传、图注/原创引用声明、图片移动与替换、来源重确认、手动保存及刷新重开。图注/文件/节点/来源顺序正确；截图screenshots/M03-editor-reopened.png。
- 真实HTTP读取浏览器所建稿件并验证旧revision写入409，证据M03-http.json。稿件和三张输入图均明确为编辑器测试夹具，不发布、不加入正式参考库。
- 最终check -Task ALL：Java14/14、前端9/9、Python图片与路径安全2/2通过；生产构建成功。有包体积提示，后续页面拆分处理；不称性能验收完成。
- Task M03: complete。M04仅已写失败契约/真实探针测试，检测实现尚未开始；不计为检测成功。

M03 GitHub插件上传已完成：main提交eb7fea7fd3d14d36c3a0385902f22dbe8dcb82fa；已从main回读M03-http.json核对。下一任务M04复用冻结权重接入真实文字/DINO模块。

## M04最终验收

- 普通计算函数与HTTP共用实现；冻结helper只读导入，服务没有T0、已知anchor强插、测试真值或合成桥接分支。48/12分块、32/64/0.25规则、alpha=0、DINO开发阈值保持。
- 真实194篇库回归：35个查询窗，候选排序与冻结一致，BERT窗口最大差0.0；候选前自身排除后仍补足10候选。
- 真实DINO重新编码对冻结参考向量余弦0.9999999403953552；权重/处理器/配置哈希已记录。
- 真实HTTP和离线调用得到完全相同证据；身份/配置、内部认证、未就绪、忙进程、空库和损坏索引边界均验证。正式外部PRECHECK入口仍未开放，纯计算测试允许独立场景输入。
- check -Task M04 -RealModels：8/8通过、无跳过；runtime/logs/M04-final.log。冻结580文件哈希复核通过。
- 主检测服务127.0.0.1:18081已ready，runId=16fd6d6f-b3f0-4d4f-9241-1ea21bd5166f，busy=false。内部令牌仅私有配置，未上传。
- 独立探针用正式形状的输入身份但不查询送审数据库；完整来源输入和报告只存runtime/probes，不作为网站实际投稿或新增准确率评价。动态参考入库/持久队列尚待M06—M08。
- Task M04: complete。M05开始，复用原独立OCR环境，不安装新环境。

M04 GitHub插件上传完成：main提交3070a04ecc4ee35c2fd24ad1bc510aa3bed04296。

## M05最终验收

- 复用原env-ocr/Scripts/python.exe；原示例误写env-ocr/python.exe，已按实存路径纠正，没有新建/重装环境。
- PP-OCRv5 mobile CPU原配置不变，六个模型文件SHA256核对。缓存/USERPROFILE仅该子进程定位runtime/ocr-cache，原环境与系统设置不变。
- 契约覆盖空识别NOT_RUN/noReuseClaim=false、低置信、行/框一致、缩放逆映射与越界拒绝。
- 实际清晰图5行；实际强模糊图0行，保留EMPTY_OCR与COVERAGE_UNVERIFIED。未把渲染真值传入识别器，不声称真实校园CER或漏字评价完成。
- check -Task M05 -RealModels：6/6通过、无跳过；实际HTTP与直接调用识别行完全相同。摘要M05-ocr.json、M05-http.json，完整本地输出runtime/probes/M05。
- OCR服务18082 ready，runId=11508017-b211-4638-be0f-bc07694acf79，busy=false。Paddle的ccache/OMP非致命提示保持记录，不为消除提示安装环境或改冻结参数。
- 冻结580文件哈希复核通过。Task M05: complete。下一任务M06为动态参考库与兼容索引，尚未实现；投稿链仍未完成。

M05 GitHub插件上传完成：main提交f5f1709bb3a450f972bf410c60e9904cdbffe32e。

## M06最终验收

- 新增管理员参考创建/列表/启停接口、事务幂等记录、持久PREPARE_REFERENCE/REFRESH_LIBRARY任务；导入不生成发布稿。已知带时区原发布时间保存为UTC，无时区页面日期仅保留来源元数据，不猜测时间。
- 新目录构建、manifest/READY哈希核验、指针CAS原子切换；失败保持旧库、旧文件保留。按完整模型/处理器配置缓存图片，损坏或不兼容向量拒绝复用；TF-IDF逐代重建并保存哈希。
- RED→GREEN：新库函数与服务缺失、不同配置缓存键、错误特征空间；后补的损坏向量检查缺失和原发布时间为NULL亦先失败后修复。测试目录runtime/test与业务runtime隔离，避免独立数据库数字ID碰撞索引目录。
- 首批来源逐文件校验：194篇正文+59张官方原图按URL整理为196作品。正文源文件包含末尾换行，核验原文件SHA后再与JSON正文比较，不修改冻结文件。
- Ruling: 导入采用设计20MP/8000px/10MiB上限，6张超像素、1张超大小原图明确拒绝并保留来源和本地原件，不放宽限额或静默缩图。因此实际业务导入196作品、194正文、52图片，7项拒绝详情见M06-import.json；其成本为这7图不参与当前站内检索。通过现有单条管理员接口进行一次性本地初始化，不新增批量导入产品功能。
- 实际HTTP初始导入及重复执行通过；参考revision与job为QUEUED，M07处理前不称已入活动检索库。所有来源许可/人工复核状态保留；不上传源文本或原图。
- 独立真实模型探针构建194正文/59图索引，59图零失败；实际新增条目可检索、停用后新代排除、旧代保留、同输入READY重复返回相同哈希。该探针目录与业务库分开，业务指针切换由Java集成测试验证，队列串联留待M07。摘要M06-library.json。
- 最终check -Task ALL：Java16/16、前端9/9及生产构建通过，Python脚本3/3、主环境11项（3项真实模型探针按默认跳过）、OCR6项（2项真实探针按默认跳过）通过。真实M06建库另运行成功，runtime/logs/M06-real-library.log；冻结580文件再核验通过。
- Task M06: complete。M07开始，投稿和审核全链路尚未完成。

M06 GitHub插件上传完成：main提交1b5b7131454a62332a248aa846a38efdd1f0d053；已回读真实建库摘要核对。

## M07进行中

- 先编写13项、并发认领、DECIDED继续接受结果、取消/旧attempt拒绝迟到结果的数据库集成测试；尚未实现worker。

### M07最终验收

- MySQL条件认领，同一任务并发只成功一次；worker跨模型调用持有独立连接的数据库advisory lock，不持有业务事务。默认调度不开启，显式CAMPUS_WORKER_ENABLED=true才消费业务队列；不擅自回收旧RUNNING任务，M13实现恢复入口。
- 批次开始固定库代、manifest哈希和三模块完整配置；人工DECIDED仍接受报告，取消/撤回/替换及旧attempt结果被拒绝。失败项重试校验expectedAttemptId，清除active并新建持久任务；旧attempt不覆盖。
- 正文/逐图DINO/OCR文字检索逐项保存，OCR成功结果按文件和完整配置缓存。空识别不启动文字检索；OCR服务故障保留失败，其他项目成功。参考准备与索引刷新复用同一worker调度，失败部分可重试。
- 真实Java→独立18083检测进程(runtime/test/indexes)→现有18082 OCR→测试DB验证：正文+6图共13项全部COMPLETED，DINO原图匹配>0.99、OCR5行及文字检索完成，见M07-real-pipeline.json。该明确测试夹具未进入业务参考库。
- 受控故障验证：未就绪WAITING_SERVICE且不建attempt；OCR不可用时仅OCR项失败；原批次配置不被新配置覆盖；超时但busy仍为true时剩余2项保持QUEUED，不新建attempt，空闲后继续。mock仅用于故障控制，真实链另留证据。
- TDD记录：类缺失编译失败(M07-red.log)、重试服务缺失失败(M07-retry-red.log)后实现；最终check M07 -RealModels 7/7无跳过(runtime/logs/M07-final.log)。check ALL后端23项(默认跳过1项真实链)、前端9/9与构建、Python脚本3/3、主环境11项默认跳过3、OCR6项默认跳过2均通过。
- Task M07: complete。M08开始，尚未声称真实站内送审发布业务闭环完成。

M07 GitHub插件上传完成：main提交01ca7c8145487cd39fcd777d8b9c7c05da9443e7，已回读真实流水线摘要。业务worker开启后，初始197个准备/刷新任务全部COMPLETED，196参考revision全部READY，库代1 ACTIVE；52图片均进入业务库。

## M08最终验收

- 同一事务完成组织授权、状态/revision校验、当前草稿保存、不可变版本/文件绑定、检测批次/任务、状态指针和事件日志；同key同内容返回同一版本，改变内容409。
- 人工决定锁稿件/版本，唯一决定约束与条件状态双重保护，并发只成功一次。决定保存当时检测进度/有效attempt快照；DECIDED后的检测完成不改决定、不产生通知或发布后提醒。
- APPROVE事务从通过版本创建发布指针、首发/默认许可锁定时间、参考revision及持久任务；RETURN/REJECT不发布不入库。退回后再次送审为v2，v1原快照保留。发布读取只用published_version_id。
- 正式报告只允许审核员；成员可看本组织内容/进度，进度不带模型证据；他组织404。管理员的参考管理权限不扩展为正式报告权限。
- 集成检查补M07边界：OCR成功后先checkpoint落库再做文字检索，后段失败保留识别文字和textSearchStatus=FAILED。该测试先因方法缺失失败，再实现并通过，日志M08-ocr-checkpoint-red.log；成功OCR缓存可供重试复用。
- 实际HTTP业务闭环：明确标注“测试用途”的首稿正文+图三项全部COMPLETED，审核通过发布快照正确、参考准备/新代切换完成；另一个组织新稿匹配到该已发布来源，成员取正式报告403。摘要M08-business-loop.json，完整本地证据runtime/probes/M08。保留标注清楚的验收记录，不作为校园真实稿件或独立准确率数据。
- 最终check ALL：Java27项(默认跳过1项独立真实链)、前端9/9及构建、Python脚本3/3、主环境11项默认跳过3、OCR6项默认跳过2通过；实际业务链另通过，无mock。冻结580文件核验通过。runtime/logs/M08-final.log。
- Task M08: complete。M09开始，投稿列表/版本历史与审核等页面仍待实现，不能称网站整体完成。

M08 GitHub插件上传完成：main提交94548ab7ba2fc6b9b8185293ef97c6a2bfb297bb。

## M09最终验收

- 接入真实组织稿件列表、标题/状态过滤、分页、当前状态操作限制、确认后软删除草稿；其他组织无权删除/读取，非草稿不允许删除。补齐列表/历史后端接口，因为前序阶段只提供草稿/单版本读取。
- 送审直接使用当前编辑内容，服务失败保留输入；相同内容重试保留幂等key，不自动重放。上传进行中或未处理失败时送审禁用；上传失败可重试或明确忽略本次未插入的文件。送审期间正文/标题/来源均冻结。
- 历史页面独立快照渲染，无编辑控件；切换同步URL，3秒刷新未结束进度，离开停止。只请求内容/决定/进度，不请求正式报告。只读渲染使用Vue文本节点和白名单标签，不注入原始HTML。
- RED：M09列表GET缺失，Vue送审按钮缺失；GREEN：组织列表/删除IT、上传阻止/失败保留/幂等key组件测试。ElementPlus confirm的类型声明为不正确的交叉类型，在测试中按实际动作字符串做局部类型适配，无依赖/环境变更。
- 浏览器真实六图验收稿4：第一版3，图注顺序1/2/3/4/6/5，引用图及正文来源保存；受控停Java导致保存失败，重启导致401，原六图/标题/正文/来源均保留，弹窗重登后手动保存成功。
- 后端HTTP退回第一版（M10审核UI尚未实现），成员浏览器按原因直接提交未手动保存的修改生成第二版4；两版各13/13项完成。浏览器切回第一版确认正文/图注/来源未改。真实HTTP再次核验节点顺序/来源和成员取报告403。摘要M09-browser-flow.json，截图M09-v1-returned.png/M09-v2-submitted.png。
- check ALL Java28项(默认跳过1真实链)、前端10/10及生产构建、Python脚本3/3/主环境11/OCR6默认探针跳过通过；最后一次前端改动后10/10与构建再通过。runtime/logs/M09-final.log。未将此六张小图作为M14容量验收。
- Task M09: complete。M10开始，审核/参考/发布/实验等页面尚待完成。

M09 GitHub插件上传完成：main提交bf5dff4f393c3d2346727f4a127a6438e2478c26，代码、验证摘要及两版合成验收稿截图均已上传。

## M10最终验收

- 审核列表仅列已送审的当前版本，按待审/已处理/全部过滤；新审核页支持历史版本、送审正文与三类证据并排、独立BERT窗口、真实图片及开发阈值、OCR行/置信度/原图坐标框和来源图片OCR。
- 正文定位使用后端码点映射转换到UTF-16/Tiptap位置，格式分段拼接不切开表情代理对；只读正文高亮并滚动。图片选择以当版nodeId对齐，不用图片顺序充当身份。
- 未结束报告3秒刷新，离开清理计时；失败项重试保留原库/配置并只新建该项attempt；决定理由按规则校验，确认后保存。质量标记显示中文解释，空OCR明确“不证明无复用”；来源OCR区域按需展开。
- Ruling: 正式报告继续复用M08 DetectionController/DetectionQueryService提供的既有路由，不另建重复ReportController；接口与鉴权不变，成本为文件布局与计划示例不同。
- RED→GREEN：审核列表接口缺失、码点定位模块缺失；新故障断言发现等待只在job上而页面batch仍QUEUED，修复为批次WAITING_SERVICE，日志M10-waiting-red.log。追加验证重试成功前后其他item的active_attempt_id不变。
- 浏览器实际定位M08稿已保存字面证据并高亮到对应正文；DINO图片对照显示真实受保护文件与0.8157开发阈值，不当作概率。源码/缓存/模型不从网页刷新时重新计算。
- 实际停原OCR服务（核对18082父子进程且队列空闲），提交明确M10测试稿5：TEXT/IMAGE完成，OCR_SERVICE_UNAVAILABLE。恢复原环境后，浏览器点“重试失败项”：OCR第2次执行成功，识别1行，文字检索完成；HTTP验证其他两项执行编号不变、证据ID刷新稳定。
- 浏览器验证退回空理由被阻止；随后对该明确测试稿作人工通过决定，实际发布读取通过快照，参考准备任务自动执行。M10-review-flow.json记录业务核验；screenshots有定位/故障/恢复/图片对照本地证据，GitHub只存合成输入的对照及故障截图。
- 最终check ALL：Java29项(默认跳过1真实链)、前端12/12及类型/生产构建、Python脚本3/3、主环境11默认跳3、OCR6默认跳2通过。质量说明模板的类型错误在编译失败后改为有类型的格式化函数，无依赖变更。runtime/logs/M10-final.log；冻结580项核验通过。
- Task M10: complete。M11开始，参考/发布/实验页面与恢复/容量/交付验收仍待完成。

M10 GitHub插件上传完成：main提交0f3abaafd7a0079fadeae6bf808f00d683579ba9。

## M11进行中

- 参考搜索/详情、四角色发布列表、启停202接口已通过集成检查；参考管理/单篇导入/发布两页已接入，前端状态切换测试13/13通过，正在处理构建和真实管理员导入验收。尚未标完成。

### M11最终验收

- 管理员单篇参考导入复用编辑器，保存来源链接/人工说明、已知组织和带明确时区的原始时间；不抓取URL、不原地改旧材料、不提供批量导入。只读详情、标题搜索、分项结果、单部分/全部失败重试、启停待切换及构建失败保留原库均接入。
- 分项按当版文档nodeId派生图片编号，不按JSON键顺序误配；录入账号/时间及被初始限额拒绝的原图说明可查。启用申请与当前可检索状态分别显示，失败不再误写待切换。
- 发布列表按publication_state/published_version_id查询，四账号均可阅读；详情只含通过快照的正文/图/来源/组织/时间，不含决定理由或模型报告。
- RED→GREEN：标题过滤/发布列表缺失、参考页面缺失；补出的图片失败+空OCR边界先出现expected FAILED but PARTIAL，改为依据实际索引可用作品集合分类。集成测试同时验证正文可用而图片失败时仍PARTIAL且effectiveEnabled=true，无任何可用部分则FAILED。
- 浏览器新增明确M11测试参考199，观察QUEUED→READY/当前可检索；真实送审查询在库代4命中该来源，且发布列表查不到手动参考。浏览器停用先显示“停用待切换”，切代5后当前不参与检索；新查询不含199，旧报告证据ID及代4文件/hash保持。
- 实际四角色读取发布快照及对应图片均200；返回不带内部决定/报告。站内自动参考也已在M08/M10实测生成、切换及真实命中。摘要M11-reference-flow.json，截图M11-reference-disabled.png及M11-published-content.png。
- 最终check ALL：Java31项默认跳过1真实链、前端13/13及类型/构建、Python脚本3/3、主11默认跳3/OCR6默认跳2通过；补充“部分可用”断言后M11 4/4再通过。原生日期输入主题文字继承修正后最终构建通过。冻结580项核验通过；runtime/logs/M11-final.log、M11-final-parts.log、M11-final-build.log。
- Task M11: complete。M12开始，不声称实验看板和最终容量/恢复/交付验收已完成。
