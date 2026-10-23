# SDD ledger — plan: docs/superpowers/plans/2026-10-23-midterm-implementation-plan.md

## 实施基线

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
