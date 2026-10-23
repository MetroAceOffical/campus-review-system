# 图文审核系统期中技术设计草案

更新日期：2026年10月23日（Asia/Shanghai）。

当前状态：用户已确认主要设计及未来预留修订；本文件作为实施设计基线，实际容量、兼容性及交付状态仍须运行验证。关联任务清单：`../plans/2026-10-23-midterm-implementation-plan.md`；新对话交接说明：`../plans/2026-10-23-new-chat-handoff.md`。

性质：期中技术设计可审阅稿，汇总已确认范围和实现原则，并将其具体化为字段、接口与运行规则。字段命名、类型及契约是面向实施的设计细化，供整体审阅；不是开发完成报告，也不是最终任务级实施计划。本对话负责设计，编码与运行验证交由另一个对话完成。

## 1. 目标与阶段

选题：基于深度学习的图文审核系统的设计与实现——以南京传媒学院为例。

系统定位：面向校园组织投稿，在有限参考库内提供文字、图片复用证据及OCR辅助，由人工决定是否发布。相似结果不等于抄袭或侵权结论，未匹配不证明原创。

| 阶段 | 截止或安排 | 重点 |
| --- | --- | --- |
| 课程期中 | 2026年10月25日20:00前 | 实验与课程材料、真实检测与投稿审核发布闭环、丰富模型可视化 |
| 课程期末 | 2026年11月1日20:00前 | 在期中基础上优先提升检测能力；等待教师评分标准后调整 |
| 最终毕业设计 | 按学校节点 | 完善原需求、独立效果评价、部署与论文证据 |

期末尚未确定具体新增功能承诺。多成员协作不作为期末默认重点。原需求没有因阶段安排自动取消。

2026年10月23日补充后续扩展复核：第22节逐项映射原需求，区分期中必须落实的数据/调用边界与后续增量实现。允许后续新增表、字段、接口与评价数据，不承诺零迁移；不能把尚未开发的功能标成已实现，也不提前建设完整后续系统。

## 2. 依据与成果复用

依据工作区《图文审核系统需求方案初稿.md》《图文审核系统可行性讨论报告.md》《剩余可行性验证结果.md》，以及本对话后续逐项确认。

- 六模型冻结实验、BERT微调、预测结果、指标和训练记录复用，不默认重跑整套训练。
- 文字分块、字面匹配、BERT推理、DINOv2特征及OCR运行逻辑提取为服务模块。
- 原Java原型只作为状态与事务设计参考：X-User身份夹具、聚合JSON业务行、进程内异步等不直接作为正式系统方案。
- 已有Python HTTP接口主要覆盖固定库文字检测，图片/OCR及动态参考库需要正式接入。
- 原实验目录与冻结文件保留；网站业务数据、文件和动态索引独立存放。

## 3. 期中范围

### 3.1 账号与角色

- 预置两个组织，每组织一名投稿成员；另预置一名审核员、一名管理员，共四个账号。
- 真实登录、退出，密码使用专门密码哈希算法保存。
- 采用服务端会话；后端根据会话检查角色和组织权限。
- 页面刷新保持有效会话，退出使会话失效。
- 登录过期时保留当前编辑内容，重新登录后重试保存；不能承诺浏览器崩溃或断电后的恢复。
- 暂不提供注册、申请审批、账号组织管理、密码找回及多成员协作。
- 稿件归组织，操作归具体账号；成员关系独立建模，支持后续多组织成员关系。

### 3.2 投稿与编辑

- 标题单独填写；基础富文本支持段落、二三级标题、加粗、斜体、有序/无序列表、引用块、链接、撤销和重做。
- 图片支持上传、插入、移动、替换、删除、图注与来源；每稿最多6张。
- JPG、PNG、WebP静态图片；期中不开放GIF、SVG、视频、文档附件。
- 图文结构按正文顺序保存。图片显示编号从当版顺序派生，不能充当永久文件标识。
- 图片原文件独立保存，节点引用文件编号；图片节点另有文档内身份，防止同一文件多次出现时混淆位置。
- 移动时保留该节点的图注与来源；替换图片形成新文件引用，并要求确认来源。
- 支持手动保存；显示未保存修改与最近保存时间；保存失败保留编辑内容。
- 离开编辑页、退出或关闭页面时提示未保存修改。浏览器提示能力不等于断电恢复保证。
- 提交直接使用编辑器当前内容，包含尚未手动保存的修改。
- 图片上传未完成或校验失败时不能成功送审。
- 粘贴保留支持的格式，清理外部复杂样式；外站图片提示另行上传，不仅保存远程地址。
- 期中不提供裁剪、旋转、滤镜、文字环绕、自由布局、字体/字号等精细样式。

单图文件大小、分辨率及正文长度上限由实施阶段的针对性运行检查确定，检查后写入配置与页面说明；不将现有两图资源结果当作六图容量证据。

### 3.3 来源填写

- 正文可填多个来源链接，没有引用可不填；期中不做选中片段添加来源。
- 每图选择原创或引用；引用必须填来源链接。
- 来源随送审版本保存，修改新版不改变旧记录。
- 填来源仍正常检测。
- 完整授权转载、授权截图、校内转发与转载许可流程后续实现，期中不显示声称已支持这些流程的选项。

### 3.4 状态与操作

| 状态 | 投稿成员操作 |
| --- | --- |
| 草稿 | 编辑、保存、送审、确认后删除草稿 |
| 待审 | 查看内容和处理状态 |
| 退回 | 查看原因、修改、重新提交 |
| 通过 | 查看发布内容 |
| 拒绝 | 查看原因，本稿结束，不允许修改重提 |

- 退回与拒绝原因必填，通过无需原因。
- 期中不开放撤回、替换待审版本、修改发布稿、撤下和下架。
- 非草稿不开放删除入口。
- 每次重提新建独立版本和检测批次。
- 投稿成员可以查看本组织历次送审内容、决定和原因，不能查看正式检测报告。
- 审核员可以查看历次内容、报告和人工原因；默认展示最新版本。
- 期中不做逐字版本差异高亮。

## 4. 架构与技术

| 部分 | 技术/职责 |
| --- | --- |
| 前端 | Vue 3；Element Plus界面组件；Tiptap编辑器；Apache ECharts图表 |
| Java | Spring Boot、MyBatis、Maven；鉴权、版本、任务、审核、发布、参考库与看板权限 |
| 主检测进程 | 复用PyTorch环境；文字检索、BERT、DINOv2与OCR文字来源检索 |
| OCR进程 | 保留隔离PaddleOCR环境；图片识别、框及置信度 |
| 数据库 | MySQL；业务数据、任务、执行历史、报告及追溯记录 |
| 文件 | 原图、检测副本、模型、实验成果及动态检索索引分别管理 |

期中本机运行，浏览器访问。依赖具体版本在实施首次集成时核验、锁定。两个Python进程是内部部署划分，浏览器统一访问Java。

模型正常运行时保持加载。逻辑队列一次处理一篇稿件，该篇逐项处理；参考入库任务使用同一后台调度顺序，不并发争抢GPU。实验看板刷新不进入检测队列。

## 5. 稿件与内容数据

核心记录：稿件、草稿、送审版本、人工决定、操作记录。

- 稿件保存组织/创建人、当前送审版本、当前发布版本和业务状态；发布状态独立保存，不能用业务状态APPROVED作为发布页唯一判断。
- 每稿一份当前草稿，多份不可覆盖的送审快照。
- 快照固定标题、图文结构、来源、检测纯文字及位置映射、提交人和时间。
- 富文本JSON是图文结构依据；组织、状态、编号等查询约束字段独立保存。
- 发布页从通过版本读取，不读取可变草稿；发布指针为后续发布稿修改预留。
- 送审快照内容不可变；执行状态、报告和决定独立记录。
- 单个送审版本期中只接受一次有效人工决定，重复或过期操作被后端拒绝。
- 保存携带草稿修订号，旧窗口不能覆盖新保存内容；拒绝时保留本地内容供用户处理。
- 提交防重复，网络重试不能生成多个版本。
- 送审快照及任务记录需一致保存，避免有送审版本却丢失检测安排。

纯文字提取规则固定并版本化，保留段落边界；记录纯文字区间与富文本节点/节点内偏移的映射。检测位置回到该送审版本展示，不以当前草稿推算。

文件以独立编号管理。替换上传新文件，历史版本引用文件不覆盖、不删除。未引用临时文件延迟清理。OCR如使用缩放副本，记录转换关系，框统一换算到原图坐标；页面按显示比例缩放框。

### 5.1 核心表与事务边界

| 表 | 关键字段 |
| --- | --- |
| manuscript | id、organization_id、created_by、status、current_submission_id、published_version_id、created_at、updated_at |
| manuscript_draft | manuscript_id、title、content_json、sources_json、revision、updated_by、updated_at |
| submission_version | id、manuscript_id、version_no、title、content_json、sources_json、plain_text、position_map_json、submitted_by、submitted_at |
| review_decision | id、submission_version_id、reviewer_id、decision、reason、decided_at、detection_snapshot_json |
| operation_log | id、actor_id、object_type、object_id、version_id、operation、details_json、created_at |

同稿version_no唯一，review_decision的submission_version_id唯一。草稿保存按revision条件更新，成功递增，不匹配返回冲突并保留前端未保存内容。

送审事务一起完成权限/状态/修订号检查、当前草稿保存、快照生成、检测批次及项创建、稿件状态更新。事务提交后再调用Python。

通过事务一起完成有效人工决定、发布指针更新和持久入库任务创建。模型运行和索引构建不放在数据库事务内等待。退回/拒绝同样通过条件更新保证一次有效决定。

## 6. 检测路线及证据

| 项目 | 期中方法 |
| --- | --- |
| 正文 | 全文分块、字符TF-IDF、字面片段证据、微调BERT语义辅助 |
| 图片 | 预训练DINOv2特征与参考特征比较 |
| OCR | PP-OCRv5输出文字/框/分数，再调用文字来源检索 |
| 图文一致性 | 期中不运行，后续接入 |

六模型用于课程实验及可视化，不要求线上逐一运行。冻结方法的模型和阈值配置沿用；接入改变输入处理或参考库时需做回归检查。

- 文字：并排片段、相同文字高亮、正文定位、来源信息；附对应BERT语义窗口和分数。
- 图片：按当版顺序逐图展示，对照来源图片，支持放大。
- OCR：逐图展示识别文字、区域、置信度及文字匹配来源。
- 三项分数不合成抄袭百分比。
- 无匹配只表述为当前参考范围未发现符合条件内容。
- OCR空输出、低置信等作为限制说明，不能表示无复用。
- BERT目前只覆盖筛选后的部分窗口，不能宣称全稿语义覆盖。
- 当前字面检索改进不归因于BERT；DINO和OCR不包装为自行训练。

## 7. 任务、报告、人工决定

建议记录检测批次、检测项、每次执行历史。报告结果可以作为执行记录的结构化内容保存，具体字段与索引在详细数据库设计中展开。

一篇正文加6图最多13个逻辑项：正文1、图片相似6、OCR及识别文字比对6。OCR逻辑项内部仍记录识别与检索各自完成情况，不能掩盖子步骤失败。

- 批次保存版本、排队时间、进度及参考库版本；库版本在开始执行时绑定。
- 项记录适用类型、图片节点身份、当前状态和有效执行。
- 执行记录保存尝试编号、模型配置、时间、结果及错误。
- 区分排队、运行、完成、失败、中断和不适用；质量限制另行记录。
- 成功运行与检出匹配分开。
- 按提交先后处理整篇；进度可显示正文完成、正在处理配图3/6等。
- 单项失败继续保存其他结果，审核员重试失败项；重试新增执行历史。
- 有效执行编号检查阻止旧请求覆盖新尝试。
- 人工可以先于检测完成处理；决定记录当时检测情况。
- 人工处理后检测继续，报告绑定原送审版本，不改变决定、不发通知、不显示发布后疑点提醒。
- 所有适用检索排除同稿自身，同组织他稿照常参与。
- 报告保存来源标识和当时证据，不能只依赖可能改变的来源链接。
- 预留批次scene、取消标记和固定pipeline_manifest；期中只建立FORMAL批次，不开放预检、撤回或替换入口。内容算法接收不可变输入和调用场景，不依赖“只有送审版本才能检测”。

### 7.1 检测表与执行约束

| 表 | 关键字段 |
| --- | --- |
| detection_batch | id、submission_version_id、library_generation_id、status、created_at、started_at、finished_at |
| detection_item | id、batch_id、type、image_node_id、status、active_attempt_id |
| detection_attempt | id、item_id、attempt_no、model_config_json、started_at、finished_at、status、result_json、error_code、error_message |

正文项image_node_id为空，图片相关项必须绑定该版本图片节点。每项attempt_no唯一。执行前持久化attempt，再调用模型；回写同时校验item_id、active_attempt_id及预期状态，旧执行不更新当前结果。

OCR结果内部区分识别阶段与文字检索阶段，结果JSON按类型定义契约。空识别、低置信与执行失败分开。

服务重启导致的中断创建新尝试后重新排队；可重复的模型/解析错误先保留失败状态，人工重试，不无限自动重跑。超时按类型配置，不能沿用原型统一15秒。请求超时不等于Python计算停止，确认旧任务结束或检测进程恢复可用后才继续派发。

## 8. Java与Python约定

请求提供：任务/执行编号、稿件/版本编号、scene、inputSnapshotKey、inputSha256、检测类型、固定输入、参考库版本、配置标识。期中inputSnapshotKey为submission:{版本编号}；纯检测算法不查询送审表，也不把“存在正式送审编号”作为运算前提。

返回提供：相同身份字段、执行状态、耗时、实际模型配置、失败原因或检测证据。输入身份与有效执行不匹配时拒绝写回。

网页通过Java查询持久化状态；刷新不启动新检测。模型服务不可用时允许保存及送审，排队任务明确显示等待服务。

## 9. 参考库

- 管理员单篇添加；复用基础编辑器。
- 标题必填；正文与配图至少一种，最多6图。
- 有网页来源填原始链接；人工提供材料填来源类型和说明。
- 来源组织、原始发布时间已知则填，不猜测。
- 自动记录添加人和时间；手动导入不出现在发布页。
- 期中不提供原地修改，错误条目停用后重新添加。
- 停用只影响切换后开始的新检测，历史报告继续可追溯。
- 审核通过先发布，同时安排入库；入库失败不影响已发布展示。
- 分项成功部分可用；失败部分单独重试。

| 总体状态 | 说明 |
| --- | --- |
| 处理中 | 存在等待/运行项 |
| 可用于比对 | 所有适用部分均成功进入有效索引 |
| 部分可用 | 有成功入索引部分，也有失败或受限部分 |
| 处理失败 | 未生成任何可用检索内容 |

纯照片OCR无文字不使已成功图片特征失效；界面同时保留OCR限制。

### 索引版本

- 新内容处理完后生成新检索版本，准备完成再切换，构建时旧版继续可用。
- 文字小库全量重建分块、TF-IDF和公共片段统计；已计算图片特征/OCR复用，仅新增或改变图片重算。
- 一个批次固定同一库版本，默认重试沿用该版本。
- 如需按新库复查，另建批次，不覆盖历史。
- 仍被执行、重试或历史证据引用的索引/来源不得提前清理；详细保留与清理策略在实施方案中规定。
- 每篇站内稿件有效参考条目最多一份，后续发布修改通过版本化替换实现。

### 9.1 文件与参考库实体

| 表 | 关键字段与用途 |
| --- | --- |
| stored_file | id、storage_key、sha256、mime_type、size_bytes、width、height、uploaded_by、created_at；只记录文件身份 |
| reference_work | id、origin_type、manuscript_id、enabled、created_by、created_at；站内稿件引用唯一，管理员导入无站内稿件 |
| reference_revision | id、reference_work_id、title、content_json、source_metadata_json、original_published_at、processing_status；固定参考内容 |
| library_generation | id、status、index_location、manifest、created_at、activated_at；记录构建与切换 |

manifest标明实际可用的reference_revision及文字/图片/OCR处理产物。enabled与processing_status分开。站内入库从通过快照读取，不从工作草稿读取。

图注、原创/引用声明、来源位于文档图片节点，不存为文件的唯一属性。同文件不同使用位置可有不同声明。图片特征/OCR处理缓存按文件哈希和完整模型/预处理配置标识复用，新的使用位置重新绑定报告证据。

## 10. 模型实验看板

仅管理员可见，后端鉴权。前端Vue＋ECharts。

四页签建议：模型总览、详细评价、训练调参、实验对照。

- 指标柱状图、Macro-F1排名、雷达图、类别指标热力图。
- 六模型混淆矩阵、ROC/PR曲线、预测分数分布。
- 实际保存的逐轮Loss、验证指标、配置比较、耗时与效果关系。
- 官方测试与排除验证精确文本重合子集分别展示；子集是嵌套口径，不称第二个独立数据集。
- 预处理对照标明仅对应实际开展的逻辑回归实验。
- 以约15—20张图为设计目标，最终依据真实记录，每图有含义说明。
- 神经模型2—3轮按真实点数显示，不制造长曲线。
- SVM判断分数不称概率，按各模型自身分数尺度展示。
- 20组调参用验证结果比较，最终测试不用于重新选参。
- 固定结果由独立结构化文件提供，保留实验编号、配置、来源和更新时间。
- 手动刷新＋可开关的10秒自动检查；有变化更新图表，不刷新整页、不启动训练。
- 显示结果更新时间和最近检查时间；失败保留上次成功数据并提示。
- 发布完整结果文件再切换，避免读取半写文件。
- 正在训练的逐轮实时数据后续接统一格式；期中已完成实验刷新不伪装为正在训练。

## 11. 页面与接口分组

投稿成员：组织稿件列表、编辑页、详情/送审历史。审核员：工作台、审核详情与证据。管理员：参考库、实验看板。所有登录账号：已发布列表与正文、标题搜索。发布页不展示内部报告和审核原因。

登录后成员进入稿件列表，审核员进入工作台，管理员进入实验看板。页面详细布局留到后续讨论。

### 11.1 已确认的界面样式要求（2026年10月23日补充）

- 页面采用紧凑间距：模块间距约10—12px，常规模块内边距12—16px，页面外边距16—20px；避免用大量空白隔开相关内容。
- 全部界面边框采用直角，包括容器、按钮、输入框、标签、弹窗和头像；统计图的圆形散点属于数据标记，不属于圆角容器。
- 提供浅色、深色及跟随系统模式；支持预设主题色和自定义主题色，并保留偏好。主题作用于导航、按钮、选中状态与图表，状态色保持稳定。
- 默认优先明亮清晰的浅色布局；任意主题色不能降低按钮、文字和背景的可读性，生成主题时调整明度及前景色。
- 正式页面不展示原型提示、技术实现说明、开发阶段说明、重复描述操作逻辑的长段文字；仅保留完成操作、理解数据、辨认失败与证据限制所必要的文字。
- 预览阶段的“预览身份”和“界面预览”仅用于演示导航，正式登录后按实际身份显示，不保留身份切换模拟入口。
- 先按内容分类定义文字层级，再应用到各页面：

| 类别 | 建议样式 | 用途 |
| --- | --- | --- |
| 页面主标题 | 24—26px、700左右字重、主文字色 | 当前页面名称，每页一处 |
| 稿件标题 | 22—24px、700左右字重 | 正文阅读与审核的内容重点 |
| 模块/图表标题 | 15—18px、600左右字重 | 检测证据、来源、处理意见、图表标题 |
| 新闻正文/编辑正文 | 15px、常规字重、约1.8行高 | 长文阅读，可用系统宋体/衬线字体，编辑与阅读保持一致 |
| 表格正文与操作 | 13—14px，标题或主要动作适当加重 | 列表、表单、按钮 |
| 元信息/辅助标签 | 11—12px、次级文字色 | 时间、组织、版本、图注、坐标标签，不承载主要结论 |
| 关键数值 | 26—30px、700左右字重、等宽数字 | 实验指标和必要业务数量 |

字体优先使用系统可用字体。主要层级通过字号、字重、留白和对比形成，避免用不同颜色装饰所有文字。

接口分组：认证、文件、草稿、送审/版本、审核/报告/重试、发布、参考库、实验。具体路径、字段、分页和错误码在接口设计中补齐。

共同要求：会话身份、服务端角色/组织检查、草稿修订号防覆盖、提交及人工决定防重复、进度查询无副作用、错误可操作、历史报告权限一致。

### 11.2 已确认的主要HTTP接口

| 操作 | 接口 | 权限 |
| --- | --- | --- |
| 登录/退出/当前身份 | POST /api/auth/login；POST /api/auth/logout；GET /api/auth/me | 按登录状态 |
| 上传 | POST /api/files | 投稿成员、管理员 |
| 文件读取 | GET /api/files/{id} | 检查引用该文件的业务对象权限 |
| 稿件查询/创建 | GET /api/manuscripts；POST /api/manuscripts | 查询：成员本组织/审核员全平台；创建：成员 |
| 草稿读取/保存 | GET/PUT /api/manuscripts/{id}/draft | 本组织且状态允许 |
| 送审/历史 | POST/GET /api/manuscripts/{id}/submissions | POST本组织成员；GET本组织成员/审核员 |
| 送审内容 | GET /api/submissions/{id} | 本组织成员/审核员，不返回正式报告 |
| 人工决定 | POST /api/submissions/{id}/decision | 审核员 |
| 检测报告 | GET /api/detection-batches/{id}/report | 仅审核员 |
| 单项重试 | POST /api/detection-items/{id}/retries | 仅审核员 |
| 发布列表/正文 | GET /api/publications；GET /api/publications/{id} | 登录用户 |
| 参考库 | /api/references | 仅管理员 |
| 实验看板 | /api/experiments | 仅管理员 |

送审请求包含当前标题、图文结构、来源、草稿revision及唯一请求标识。身份/权限校验后，先查同一身份同一操作的幂等记录；已成功的同一请求返回原结果，新请求再检查revision/状态。标识重复但请求内容不同返回冲突，不能复用旧结果。

数据库编号传前端时序列化为字符串，时间提供明确时区。成员的状态查询只返回进度和必要状态，不携带相似来源、片段、模型分数等正式证据。

## 12. 初始化、启动与恢复

- 预置四账号和两组织。
- 从现有194篇文字参考材料及图片中核对整理，保留来源；合成夹具/变体不混为校园正式参考作品。
- 演示草稿明确标注用途，已发布页可以初始为空。
- 实验结果导入看板读取目录，保留原始冻结文件。
- 初始化可重复执行，不覆盖已产生业务、不重复建账号与来源。
- 提供统一启动/停止入口及初始化、恢复、演示说明。
- 检查MySQL、模型、目录、索引、两个Python进程、Java和前端。
- 模型加载状态单独检查，不能以网页可打开判断模型就绪。
- 重启保留已完成结果；中断尝试标明中断并创建新尝试，未执行项继续排队。
- 索引丢失/损坏暂停相应检索并提示重建，不把空库结果当无匹配。

## 13. 实施次序与验收

实施次序：真实登录和图文保存→送审/人工处理/发布→真实检测与证据→参考库更新→看板整合→异常恢复与提交材料。看板数据整理及课程报告可以提前推进。

期中验收：

1. 四账号可用，跨组织、角色及实验接口越权被拒绝。
2. 图文移动替换、保存重开，位置/图注/来源一致。
3. 退回重提旧版本不变、报告不串版。
4. 新输入实际检测、展示真实来源证据及定位。
5. 六图流程完成；单图失败不丢其他结果。
6. 人工先处理，检测后补不改决定、不提醒。
7. 通过后发布，入库完成后可被新稿检索，自身排除。
8. 添加/部分可用/停用/重试真正影响参考范围，历史证据可查看。
9. 离开页面任务继续，服务重启恢复，已完成结果保留。
10. 管理员看板图表与原始记录一致，两类刷新行为正确。
11. 六模型、预处理、调参、测试、图表、环境与复现入口和课程报告相符。

至少完成一次现场新输入→真实检测→人工处理→发布→入库→再次检索，不以预置报告替代。

## 14. 后续细化与证据边界

本稿第15—21节补充字段类型、请求响应契约、队列与索引时序、已确认初始参数及部署边界。界面以已认可的紧凑直角演示版为基准。整体审阅通过后，另行编制可交给编码对话的任务级实施计划。首次集成依赖锁定及容量验证属于实施任务，尚未通过设计文件代替运行验收。

目前未重新运行实验或编写业务代码。六图容量、正式登录、持久任务恢复、真实索引切换与完整浏览器流程仍须实施验收。

质量限制沿用可行性报告：文字真实改写和同事件难例不足；BERT未改善当前字面判断/排序；图片有同场景误接；真实OCR转录评价未完成；图文一致性原五类划分失败，不能包装为质量通过。

期末评分标准发布后，优先从文字语义、图片误报、真实OCR评价、图文一致性及实验展示中选择增量。补证与方法改进保留旧实验，不以添加模型数量代替贡献证明。

## 15. 字段类型与约束细化

### 15.1 共通规则

- MySQL 8、InnoDB、utf8mb4。主键采用正数BIGINT自增；传浏览器和Python时统一为十进制字符串。
- 时间使用DATETIME(3)，由应用按UTC写入；接口输出ISO 8601带时区，前端按Asia/Shanghai显示。连接配置使用UTC，不修改系统MySQL全局时区。
- 状态用VARCHAR(32)与应用枚举校验，不让前端传任意状态值直接落库。
- 结构化正文、证据及快照使用JSON；必需检索、关联和幂等字段独立成列。
- 所有已被版本、决定、报告引用的用户、文件、来源保留身份，不级联物理删除历史。
- 字段未特别说明时必填；引用编号、未发生的结束时间、可选来源信息可为空。长字符串入库前按业务上限校验。

### 15.2 账号与稿件

| 表 | 字段及类型 | 约束与索引 |
| --- | --- | --- |
| app_user | id BIGINT；username VARCHAR(64)；display_name VARCHAR(64)；password_hash VARCHAR(255)；role VARCHAR(16)；enabled BOOLEAN；created_at/updated_at DATETIME(3) | username唯一；role仅MEMBER/REVIEWER/ADMIN；初始化仅1个有效审核员 |
| organization | id BIGINT；name VARCHAR(100)；enabled BOOLEAN；created_at/updated_at DATETIME(3) | 初始两组织；组织编号稳定 |
| organization_member | organization_id/user_id BIGINT；enabled BOOLEAN；joined_at DATETIME(3) | 联合主键；外键关联组织和账号；应用保证只有MEMBER可关联 |
| manuscript | id/organization_id/created_by BIGINT；status/publication_state VARCHAR(32)；current_submission_id/published_version_id BIGINT可空；next_version_no INT；first_published_at/reprint_locked_at/deleted_at DATETIME(3)可空；reprint_allowed BOOLEAN默认true；created_at/updated_at DATETIME(3) | 索引(organization_id,status,updated_at)、(status,updated_at)、(publication_state,updated_at)；当前版本必须属于本稿 |
| manuscript_draft | manuscript_id BIGINT主键；title VARCHAR(200)；schema_version VARCHAR(16)；content_json/sources_json JSON；content_sha256 CHAR(64)；revision BIGINT；updated_by BIGINT；updated_at DATETIME(3) | 一稿一草稿；保存条件包含revision |
| submission_version | id/manuscript_id BIGINT；version_no INT；schema_version/extractor_version VARCHAR(16)；title VARCHAR(200)；content_json/sources_json JSON；plain_text LONGTEXT；position_map_json JSON；content_sha256 CHAR(64)；lifecycle_status VARCHAR(32)；superseded_by_version_id BIGINT可空；withdrawn_at DATETIME(3)可空；submitted_by BIGINT；submitted_at DATETIME(3) | UNIQUE(manuscript_id,version_no)；内容快照不可变，生命周期元信息可随业务变化 |
| review_decision | id/submission_version_id/reviewer_id BIGINT；decision VARCHAR(16)；reason TEXT可空；detection_snapshot_json JSON；decided_at DATETIME(3) | submission_version_id唯一；APPROVE/RETURN/REJECT；后两项原因非空 |
| operation_log | id/actor_id BIGINT；organization_id BIGINT可空；object_type VARCHAR(32)；object_id/version_id BIGINT可空；operation VARCHAR(48)；details_json JSON；created_at DATETIME(3) | 按对象及时间、操作者及时间索引；details含事件schemaVersion及当时显示名/组织名，不记录密码、会话或凭据 |

期中业务状态仅DRAFT/PENDING/RETURNED/APPROVED/REJECTED；publication_state仅NOT_PUBLISHED/PUBLISHED，首次通过设为PUBLISHED。发布列表根据publication_state及published_version_id查询。后续修改待审时可同时为status=PENDING和publication_state=PUBLISHED，保留旧发布版；下架扩展publication_state，不清除最后通过版本指针。

草稿删除使用deleted_at并记录操作。列表排除删除项；期中不开放其他状态的删除。当前版本关联可采用组合外键或在持有稿件行锁的事务中强校验，不能只依靠前端。

submission_version.lifecycle_status期中写PENDING/DECIDED；后续才使用SUPERSEDED/WITHDRAWN及相应关联字段。首次通过事务同时记录first_published_at、锁定reprint_allowed（沿用原需求默认true）及reprint_locked_at，后续不覆盖。管理员导入条目不据此获得转载许可，期中不开放转载入口。未来发布后管理新增publication_action记录，不删除“一次送审一次初始决定”的唯一约束，也不覆盖原审核决定。

版本序号在锁定稿件行后分配，唯一约束兜底。处理决定与版本、人工状态共同条件更新，不能用“先查后无条件写”防重复。

### 15.3 文件、检测与参考

| 表 | 字段及类型 | 约束与索引 |
| --- | --- | --- |
| stored_file | id/uploaded_by BIGINT；storage_key VARCHAR(255)；original_name VARCHAR(255)；sha256 CHAR(64)；mime_type VARCHAR(64)；size_bytes BIGINT；width/height INT；created_at DATETIME(3) | storage_key唯一；哈希索引用于处理缓存，不以文件名定位文件 |
| file_binding | id/file_id BIGINT；draft_manuscript_id/submission_version_id/reference_revision_id BIGINT可空；node_id VARCHAR(64)；purpose VARCHAR(32) | 三个归属仅一项非空；同对象node_id唯一；期中用途为BODY_IMAGE或EVIDENCE_IMAGE；后续授权附件单独绑定，不作为正文节点 |
| detection_batch | id BIGINT；submission_version_id BIGINT可空；scene VARCHAR(16)默认FORMAL；input_snapshot_key VARCHAR(100)；input_sha256 CHAR(64)；batch_no INT；library_generation_id BIGINT可空；pipeline_manifest_json JSON可空；status VARCHAR(32)；cancelled_at DATETIME(3)可空；cancel_reason VARCHAR(32)可空；created_at/started_at/finished_at DATETIME(3) | UNIQUE(submission_version_id,batch_no)；期中仅FORMAL，应用必验submission_version_id非空；开始时固定库及流水线；后续预检新增快照外键/唯一约束 |
| detection_item | id/batch_id BIGINT；type VARCHAR(32)；target_key VARCHAR(64)；image_node_id VARCHAR(64)可空；status VARCHAR(32)；active_attempt_id BIGINT可空；updated_at DATETIME(3) | UNIQUE(batch_id,type,target_key)，正文target_key为BODY；当前图片项target_key为节点编号 |
| detection_attempt | id/item_id BIGINT；attempt_no INT；status VARCHAR(32)；model_config_json/result_json JSON；started_at/finished_at DATETIME(3)；error_code VARCHAR(64)可空；error_message TEXT可空 | UNIQUE(item_id,attempt_no)；日志/结果不含凭据；执行结果一旦结束不覆盖 |
| reference_work | id/manuscript_id BIGINT可空；origin_type VARCHAR(16)；enabled BOOLEAN；created_by BIGINT；created_at DATETIME(3) | origin_type为MANUAL/PUBLISHED；manuscript_id唯一，MANUAL为空；不删除历史身份 |
| reference_revision | id/reference_work_id BIGINT；revision_no INT；submission_version_id BIGINT可空；title VARCHAR(200)；content_json/source_metadata_json JSON；original_published_at DATETIME(3)可空；processing_status VARCHAR(32)；artifacts_json JSON；created_at DATETIME(3) | UNIQUE(reference_work_id,revision_no)；PUBLISHED绑定通过版本；artifacts_json逐项保存成功产物及失败 |
| library_generation | id BIGINT；status VARCHAR(32)；index_location/manifest_location VARCHAR(255)；manifest_sha256 CHAR(64)；created_at/activated_at DATETIME(3) | BUILDING/READY/ACTIVE/ARCHIVED/FAILED；未完成构建不得激活 |
| runtime_state | name VARCHAR(64)主键；library_generation_id BIGINT可空；updated_at DATETIME(3) | CURRENT_LIBRARY单行指针；库切换使用事务更新 |

file_binding跟随草稿保存更新，送审时生成独立绑定；替换节点不能修改旧绑定。预置参考图片也登记stored_file与reference_revision绑定。读取文件同时检查绑定对象及purpose：能看本组织送审正文不等于能看EVIDENCE_IMAGE，正式检测证据绑定仍只允许审核员。不能把存储目录直接作为无鉴权静态资源目录。

### 15.4 队列与幂等

| 表 | 字段及类型 | 说明 |
| --- | --- | --- |
| background_job | id BIGINT；kind VARCHAR(32)；batch_id/item_id/reference_revision_id/reference_work_id BIGINT可空；status VARCHAR(32)；owner_run_id VARCHAR(36)可空；payload_json JSON；created_at/started_at/finished_at DATETIME(3)；error_code/message可空 | 全局排队记录；索引(status,id)；DETECT_BATCH/RETRY_ITEM/PREPARE_REFERENCE/REFRESH_LIBRARY依类型仅关联相应对象 |
| idempotency_record | id/actor_id BIGINT；operation VARCHAR(48)；request_key VARCHAR(64)；request_sha256 CHAR(64)；result_json JSON；created_at DATETIME(3) | UNIQUE(actor_id,operation,request_key)；送审、决定、重试、导入等重复提交返回同一结果 |

background_job直接复用队列表，不新增Redis或消息中间件。队列记录、业务对象及幂等成功结果在同一事务落库；事务回滚时不留下“成功幂等记录”。并发同键通过唯一约束等待/复查已提交结果；数据库异常不伪造成功响应。

这是数据结构设计，不要求期中开放账号组织管理、参考修改或模型管理页面。DDL迁移按依赖分步创建，循环指针外键在关联表建立后添加。

新增schema_migration(version VARCHAR(64)主键、checksum CHAR(64)、applied_at DATETIME(3))记录已应用的有序SQL迁移。后续以增量迁移升级，不靠删除数据目录、重新建库或重跑种子覆盖现有数据。是否使用迁移框架留给实施者按现有依赖决定，不为预留强制添加框架。

## 16. 正文结构与偏移契约

### 16.1 编辑结构

content_json采用Tiptap文档JSON，外层另记录schema_version。期中允许的节点为doc、paragraph、heading（level 2/3）、text、bulletList、orderedList、listItem、blockquote、hardBreak及自定义campusImage；允许bold、italic、link标记。

campusImage属性：nodeId、fileId、caption、origin（ORIGINAL/CITED）、sourceUrl。nodeId是一次文档使用位置的稳定编号，fileId是文件身份，二者不可混用。复制一个图片节点需生成新nodeId。图片顺序遍历正文时派生，不作为永久身份。

sources_json保存正文来源列表，每项包含sourceId和url。后端校验允许的节点、属性、链接协议、文件归属、图片数及引用必填项；不直接信任任意HTML或任意本地路径。引用链接仅允许http/https；期中不自动抓取。

保存草稿允许未完成的来源字段，送审及参考入库时执行完整校验。空草稿可保存；正式送审要求非空标题，且正文或配图至少一项存在。

### 16.2 文字提取和映射

- plain_text只取正文文字叶节点，块之间按统一规则插入换行。标题、图注、图片alt、来源链接不混入这段正文检索文本。
- 仅图片稿件的正文检测标为NOT_APPLICABLE；仍做图片与OCR。
- 空白和换行在生成映射前统一处理，生成后不能再无记录地规范化；保存extractor_version。
- position_map每项包含nodeId、plainStart、plainEnd、nodeTextStart、nodeTextEnd；纯格式段落也要能定位到稳定节点。无原生ID的文本块在保存前统一分配并在后端校验唯一。
- 跨语言偏移采用Unicode码点、从0开始、左闭右开。Python按该规则输出，Java使用码点计数；Vue通过码点到UTF-16偏移表转换到编辑器/DOM位置。
- 中文、换行、列表、表情符号、空文本节点、跨格式片段均有定位用例；不能只用纯中文无格式样本验收。
- 原文区间与证据片段校验不一致时，保留片段并提示无法定位，不在错误位置强行高亮。

OCR坐标统一为原图像素，记录originalWidth/Height及processingTransform；多边形与识别行逐项对应。若预处理包括方向变换，必须记录变换并逆映射，否则该能力关闭。

## 17. HTTP请求与响应契约

### 17.1 共通格式

成功响应：code=OK、data=业务对象、requestId=追踪编号。失败响应：code=明确错误码、message=可操作提示、details=字段错误或冲突摘要、requestId。HTTP状态同时正确设置，不全部返回200。

| HTTP状态 | 典型错误码 |
| --- | --- |
| 400 | VALIDATION_ERROR、UNSUPPORTED_DOCUMENT_NODE、INVALID_SOURCE |
| 401 | LOGIN_REQUIRED、SESSION_EXPIRED、BAD_CREDENTIALS |
| 403 | ACCESS_DENIED、CSRF_INVALID |
| 404 | RESOURCE_NOT_FOUND；无权查看的组织对象也可统一此响应 |
| 409 | DRAFT_REVISION_CONFLICT、INVALID_STATE、ALREADY_DECIDED、IDEMPOTENCY_CONFLICT |
| 413 | UPLOAD_TOO_LARGE、CONTENT_TOO_LARGE |
| 415 | UNSUPPORTED_IMAGE_TYPE |
| 500/503 | INTERNAL_ERROR、DATABASE_UNAVAILABLE；检测服务暂不可用通常记录任务状态，不回滚已成功送审 |

列表参数page从1开始，pageSize默认20、最大100；q和status可选。返回items、page、pageSize、total。排序字段由后端白名单控制。

有幂等要求的写操作使用Idempotency-Key请求头（UUID）。重试同次操作保留同key；用户修改内容重新发起时用新key。CSRF令牌及登录会话与幂等键职责分开。

### 17.2 主要请求体

| 接口 | 请求内容 | 成功返回重点 |
| --- | --- | --- |
| POST /api/auth/login | username、password | userId、displayName、role、organizations；不返回密码哈希或会话令牌 |
| GET /api/auth/me | 无 | 实际身份及可访问组织；前端据此建导航 |
| POST /api/files | multipart单文件 | fileId、mimeType、width、height、sizeBytes；不暴露绝对路径 |
| POST /api/manuscripts | organizationId（校验实际成员资格）、title可选 | manuscriptId、draftRevision |
| PUT /api/manuscripts/{id}/draft | expectedRevision、title、schemaVersion、content、sources | 新revision、savedAt |
| POST /api/manuscripts/{id}/submissions | expectedDraftRevision、title、schemaVersion、content、sources | submissionId、versionNo、batchId、status=PENDING |
| POST /api/submissions/{id}/decision | decision、reason（按决定必填） | decisionId、status、publishedVersionId（适用时）、referenceProcessingStatus |
| POST /api/detection-items/{id}/retries | expectedAttemptId（失败的那次） | jobId、itemId、status=QUEUED |
| POST /api/references | title、schemaVersion、content、sourceMetadata | referenceId、revisionId、jobId、processingStatus=QUEUED |
| PATCH /api/references/{id}/enabled | enabled | jobId、requestedEnabled、effectiveEnabled、status（切换尚未完成时202） |
| POST /api/references/{id}/retries | failedPartKeys；未指定则全部失败部分 | jobId及重试项目 |

GET /api/submissions/{id}只返回内容、版本与人工决定，不返回正式模型证据。GET /api/detection-batches/{id}/progress允许本组织成员及审核员，只包含项目类型、进度和完成状态；GET /report严格只允许审核员。

审核员的列表以送审及已处理稿件为范围，期中不列出尚未提交的组织草稿。管理员参考管理权限不自动开放组织草稿或正式报告。

### 17.3 报告结构

报告头包含reportSchemaVersion、batchId、scene、inputSnapshotKey、inputSha256、submissionId（正式批次）、versionNo、libraryGenerationId、pipelineManifest、status、items、generatedAt。每item包含itemId、type、target（正文或imageNodeId及当版图片序号）、status、qualityFlags、activeAttempt、evidence。每条evidence有evidenceId和evidenceType；ID在同次执行中稳定，由执行编号及证据身份派生，不因重新打开报告变化。

- TEXT_SIMILARITY证据：sourceWorkId、sourceRevisionId、sourceTitle、sourceUrl/说明、sourceKind、matches、semanticWindows。matches包含queryStart/End、sourceStart/End、queryText、sourceText及字面证据判定；semanticWindows独立列示片段和分数。
- IMAGE_SIMILARITY证据：queryFileId、sourceFileId、sourceWorkId/revisionId、similarity、threshold、acceptedCandidate及对应模型配置；余弦相似分数不标为概率。
- OCR_AND_TEXT证据：imageNodeId、ocrStatus、recognitionLines（lineId/text/confidence/polygon）、lowConfidenceLineIds、combinedText、textSearchStatus及文字检索证据。空识别时textSearchStatus=NOT_RUN，noReuseClaim=false。
- qualityFlags可含EMPTY_OCR、LOW_CONFIDENCE、COVERAGE_UNVERIFIED、INSUFFICIENT_TEXT；不能据此伪造准确性。
- sourceKind区分BODY与IMAGE_OCR；sourceScope期中为LIBRARY，未来可扩展EXTERNAL_MANUAL/EXTERNAL_FETCH/PUBLIC_ASSET。LIBRARY证据要求sourceWorkId/revisionId；临时来源后续改用其独立快照ID，不伪造正式来源编号。匹配来自OCR时展示来源图片与识别区域，不能冒充原文正文。

成功报告保存来源当时标题、引用片段、文件绑定和必要配置。文件证据通过受保护接口读取，不直接从外站重新获取。

### 17.4 实验接口

仅管理员：GET /api/experiments、GET /api/experiments/{id}、GET /api/experiments/{id}/metrics、/history、/search、/curves。

实验索引包含id、taskType、dataset、datasetRevision、splitProtocol、frozenAt、updatedAt、contentVersion、metricDefinitions和可用图表类型。当前六模型实验的testSet白名单为official_test或test_no_val_overlap；白名单与指标定义属于该实验manifest，不能全平台写死成只有这两种集合和分类指标。后续检索、图片、OCR和图文一致性各用本任务指标。曲线在离线转换时从保存预测分数计算，写入处理后的实验包，页面刷新不重复全量计算。

每次完整结果写好后发布manifest及其contentVersion；前端用版本检查，有更新再拉所需数据，无更新只更新检查时间。结果文件损坏时显示失败并保留最近成功快照。接口不接受任意本地文件路径。

## 18. 模型服务、队列与索引时序

### 18.1 服务内部接口

两个Python进程只绑定127.0.0.1，主进程18081，OCR进程18082。Java调用时带项目内部令牌；令牌来自本地私有配置，不发给浏览器。具体HTTP框架以现有环境可用依赖为准，期中适配保持小规模，不为框架重装模型环境。

| 服务接口 | 输入/输出 |
| --- | --- |
| 两进程 GET /health | ready、model/config标识、进程runId；模型未加载完返回ready=false |
| 主进程 POST /detect/text | taskId、attemptId、scene、inputSnapshotKey、inputSha256、versionId（正式场景）、libraryGenerationId、text、excludeManuscriptId、configId；返回片段与语义证据 |
| 主进程 POST /detect/image | 同样身份字段、登记文件标识及受控路径、库版本、自身排除；返回候选图片 |
| OCR进程 POST /recognize | taskId、attemptId、fileId、受控路径；返回原图坐标文字行与质量标记 |
| 主进程 POST /library/build | 待构建库编号、受控manifest位置；返回校验哈希与实际产物摘要 |

OCR_AND_TEXT逻辑项由Java先调用OCR，持久保存识别中间结果，再调用主进程文字检索。重试时配置及输入哈希未变化可复用成功的识别结果，但报告标明子步骤实际运行/复用情况。

不让浏览器指定本地路径。Python确认所有文件/manifest路径在项目允许根目录内，校验输入文件哈希和配置标识。Java与Python返回的任务身份必须一致才可落为当前结果。

模型计算与HTTP适配分开为可直接调用的普通Python模块，离线评价和线上服务调用同一份检测实现；当前确定性本地计算按配置和数值容差复核一致证据，耗时等运行元信息除外。未来生成式API保存实际请求配置/响应，不承诺重复调用逐字相同。期末不另外复制一套算法只用于展示好指标。

期中仍只提供正式检测接口。预检或库外比对后续以新业务入口适配相同计算模块，不创建假的送审版本，不强行把临时外部来源写入正式参考库。

### 18.2 冻结方法适配

文字配置来自validation/remaining/text/selection.json：48 token分块、12重叠；literal_minimum=32、min_chars=64、min_coverage=0.25；语义排序alpha=0。候选规则、公共片段抑制等从冻结实现提取并记录方法配置版本。

线上路径去除实验专用的T0整段截断对照、已知anchor强插候选、测试真值、合成桥接夹具。保留它们在原实验中，不作为在线结果来源。

自身稿件过滤在候选截取前执行，不能先取Top10后删除自身导致少召回候选。正文候选聚合与BERT窗口选取遵循冻结方法；语义分数不能默默改变字面接受规则。新增库导致TF-IDF/公共片段统计变化时做来源排序回归，不宣称冻结分数仍必然复现。

DINO沿用实际验证权重和处理器，默认阈值从开发选择产物读取（记录中约0.8157106638），不从测试重新选。OCR沿用独立环境的PP-OCRv5 mobile配置、CPU线程/辅助模型设置，框转换完整记录。任何缩放上限调整需检查实际图片与OCR质量变化。

开始批次时pipeline_manifest_json固定各模块的权重/修订/文件哈希、处理器/分块配置、阈值和候选策略、方法schema版本、参考库版本。未来API调用还需记录供应方、模型、提示词/输出schema及相关推理参数版本；不把密钥写入manifest。

generation manifest的每类特征产物记录feature_space_id（编码器权重、处理器、向量维度/归一化等配置哈希）及producer_config_hash。查询侧兼容校验失败时重建对应索引或明确失败，不将新模型向量与旧模型索引直接比较。BERT窗口推理、字面索引、DINO特征、OCR产物分别判定是否需重算，不因一项升级无条件重跑全部模块。

重试默认使用原批次流水线和库版本；旧权重/配置缺失时显示CONFIG_UNAVAILABLE，不偷偷改用当前模型。按新方法重新评价新建批次，旧报告与实验不覆盖。期中不建设在线模型切换页面。

### 18.3 排队与重试

期中单Java实例、单队列worker。进程启动时生成owner_run_id，通过本地实例锁/监听端口防止重复启动。队列按id先后选取，事务内条件认领QUEUED→RUNNING；模型调用在认领事务外。

正常顺序：正文→按文档顺序逐图图片相似→逐图OCR及文字检索。可不适用的项直接记录NOT_APPLICABLE。每完成一步持久化，失败继续处理其余项。batch为COMPLETED/PARTIAL_FAILED/FAILED与job已调度结束分别表达，不能用job完成冒充所有检测成功。

主检测服务尚未就绪时，未开始的检测job保持WAITING_SERVICE，恢复后按原排队序列执行。批次执行期间OCR服务不可用，OCR项明确失败并继续其他可执行项，不把它伪装成空识别。

人工重试：锁定失败item，验证expectedAttemptId和可重试状态，清除旧active_attempt_id，将item设QUEUED并建立RETRY_ITEM任务。worker执行时创建新attempt。服务重启：确认旧检测进程已停止或可证明空闲，回收旧owner任务，中断attempt保留INTERRUPTED，新尝试仅针对未完成部分。

请求超时记录TIMED_OUT并停止向该进程派发；等待空闲确认或恢复项目拥有的该进程。只按经过验证的进程句柄/runId及启动参数管理本系统进程，不能凭旧PID盲目终止。已有业务与成功结果不清空。

后续撤回/待审替换的失效规则现在写入回写条件：除active_attempt_id外，还检查batch.cancelled_at为空和正式版本未被WITHDRAWN/SUPERSEDED。取消后迟到响应只留技术记录，不成为有效报告；已完成证据可按旧版历史查看。取消终止原因与普通失败分开，不自动重试。单纯人工通过/退回/拒绝设置DECIDED，不能触发这条取消规则，仍继续本版检测。期中没有取消入口，相关取消字段保持空。

### 18.4 索引切换与保留

PREPARE_REFERENCE任务分别准备正文、图片特征、OCR和OCR文字索引材料，artifacts_json记录成功与失败；成功子项组成新generation。停用/启用通过REFRESH_LIBRARY任务构建新generation。

构建在新目录进行：写数据→校验文件及manifest哈希→写READY标记→Java确认→数据库事务切换CURRENT_LIBRARY并更新有效状态。文件准备与数据库切换分两步，异常时旧库继续工作。

API停用成功受理不等于停用已生效，处理中显示“待切换”；只有新索引激活后显示已停用。失败显示失败及仍在使用的有效状态。排队中的新检测在实际开始时读取CURRENT_LIBRARY并固定。

旧generation、参考内容、模型配置及必要文件期中全部保留，以支持失败项按原库重试。历史报告查看不要求重新推理。重建到READY但未激活的孤立产物可复核后恢复；不可因启动时扫描到较新目录就自行启用。

空参考库合法但要显式显示“当前参考库为空，未进行有效来源比对”，不能展示普通无匹配。新站初始化参考内容完成后再进行正式演示验收。

## 19. 已确认初始配置

下列是实施起点及边界测试对象，不是实测容量或耗时保证；实施调整须记录依据，功能范围变化另行反馈。

| 配置 | 初始值 |
| --- | --- |
| 标题 | 最多200 Unicode码点 |
| 正文 | 最多10,000 Unicode码点，不含富文本标签 |
| 配图 | 最多6张 |
| 单图文件 | 最多10MB；程序统一定义为10×1024×1024字节，页面注明 |
| 单图像素 | 不超过20,000,000，且任一边≤8,000px |
| 来源URL | 最多2,000字符 |
| 普通业务请求超时 | 15秒，不等待模型 |
| 单图上传超时 | 60秒 |
| 正文检测超时 | 每项120秒 |
| 图片相似超时 | 每图60秒 |
| OCR及文字比对超时 | 每图180秒，覆盖两个子阶段并记录实际耗时 |
| 索引构建超时 | 300秒 |
| 模型进程启动等待 | 每进程180秒 |
| 进度轮询 | 未结束时每3秒；离开页面停止，返回重新读取 |
| 看板自动检查 | 每10秒，可关闭 |

服务端和前端同源配置校验。上传单文件单请求，编辑器等待全部成功再送审；限额不意味着把6个原图同时解码常驻内存。超限不静默截断/缩小原文件、不丢编辑内容；检测副本规则及其质量影响单独记录。

自动轮询不弹出发布后疑点提醒。人工决定后的报告继续绑定原版，重新打开详情可查看。

会话初始空闲超时2小时，仅作为本机演示默认值；前端主题偏好持久保存在浏览器，退出不清主题。后端重启会话失效需要重新登录，业务任务仍从数据库恢复。此类实现默认值作为本稿细化内容，等待整体审阅。

## 20. 正式认证与本机部署细化

### 20.1 认证

正式Java工程采用与Spring Boot依赖管理兼容的Spring Security会话认证、PasswordEncoder及CSRF防护；不复用X-User，不自写密码加密算法。不因官方文档当前展示7.x而直接给Boot3.5强行升级依赖。

浏览器同源调用。开发时Vue开发服务器代理/api到Java；演示构建将前端静态产物交Java提供，同一浏览器地址访问。会话Cookie为HttpOnly、SameSite=Lax；本机HTTP配置与后续HTTPS配置分别管理。登录更新会话身份与会话标识，退出失效。

GET /api/auth/csrf提供CSRF令牌，前端写请求按返回headerName携带；登录/退出后重新取得令牌。登录过期弹出重新登录界面并保留当前编辑DOM；取得新会话/CSRF后才由用户重试原操作，不盲重放审核决定。

依据：[Spring PasswordEncoder](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/password-encoder.html)、[Spring CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)。具体配置API以所锁定兼容版本为准。

### 20.2 目录和端口

正式代码建议独立放入app/（frontend、backend、detector、ocr-worker、scripts），运行数据放runtime/（mysql、uploads、derived、indexes、experiments、logs、private-config）。不在冻结validation目录内直接开发业务服务。

Java默认8080，主检测18081，OCR18082；MySQL使用项目独立3308实例及专用数据库campus_review_midterm，沿用已有隔离启动验证思路。端口被占用就提示，不停止未知服务。不改动系统MySQL80服务。

MySQL二进制、JDK、Python环境、Node路径通过项目本地配置定位，启动时检查。初次初始化新建项目datadir和凭据，不寻找或恢复已清理的V5密码。凭据不写进截图/日志/前端，也不复用系统root用于日常业务。

已验证Java基础为JDK21、Spring Boot3.5.16、MyBatis starter3.0.5。新增依赖由Boot兼容管理；前端安装时固定版本和lockfile。模型环境先做导入/哈希/推理检查，缺少轻量适配依赖才定向补齐；不重新安装整套训练环境。

### 20.3 管理入口

交付初始化、启动、状态、停止、数据库备份/恢复的脚本入口及README。初始化与启动分开；启动不自动清库、不重置密码。停止仅管理本项目启动的进程。

备份包含SQL、uploads、参考内容及manifest、必要索引/配置；模型和冻结实验已有目录保留可核对的版本清单。恢复在明确指定的项目运行目录执行，先验证路径、端口和当前数据库状态；演示不需要一键破坏性重置功能。

## 21. 交接、测试与完成口径

### 21.1 实施交接内容

后续实施计划须给出每个任务的输入、目标文件/模块、依赖、完成证据、失败处理及所需人工工作。以真实登录、快照保存、真检测、发布入库形成第一条完整链路，再补齐6图、参考管理与全部图表；这只是开发顺序，不取消已确认期中范围。

编码对话遇到冻结程序与网站输入不一致时，先报告具体差异，提取通用函数、补回归；不为了接入直接改写历史指标或用已有报告代替新推理。复杂度或工期出现阻碍时反馈待完成项，不能静默删减需求。

### 21.2 必要验证分层

| 层次 | 必验内容 |
| --- | --- |
| 事务与权限 | 双窗口修订冲突；并发送审幂等；人工决定一次有效；跨组织/角色/文件读取拒绝；CSRF写请求保护 |
| 内容 | 图文移动替换重开；节点来源随版本；跨加粗/列表/表情的片段定位；OCR缩放框对应 |
| 模型适配 | 冻结样例对比；去除T0/真值夹具；当前库实际参与；阈值/配置记录；自身过滤先于TopK |
| 队列与恢复 | 停Java、停任一Python、超时但计算未停、旧结果迟到、单项重试、重启未完成项恢复 |
| 参考库 | 管理员导入不发布；通过后入库；部分可用；停用待切换及失败；构建中断旧库可用；按原库重试 |
| 资源边界 | 10,000字、6图、接近文件及像素上限、模糊/空OCR、多个稿件排队；记录耗时/内存/显存/失败，不推导未经测量吞吐 |
| 界面 | 认可视觉基准；多页面主题一致；自定义颜色可读；正式无开发说明；保存失败不丢编辑内容 |
| 实验展示 | 六模型及20配置数值与冻结CSV/JSON一致；ROC/PR由实际分数算；曲线轮数真实；刷新不训练；非管理员拒绝 |

性能测试先用代表性输入运行，再运行上限用例。对超时、丢进程、写库失败等采用可控故障，真实模型正常路径必须另有真实证据；故障桩不得进入演示正常结果。

### 21.3 提交物

- 可启动的前端、Java、两个检测进程及数据库初始化材料。
- 实验代码/模型/数据版本清单、六模型结果、可视化与复现入口。
- 操作说明、账号交付说明、演示脚本、测试结果与未完成项清单。
- 与课程模板一致的报告及环境可用证据；安装配置证据与实际业务使用证据分开。
- 明确自行训练BERT等实验、预训练DINO/OCR应用及后续视觉API的贡献边界。

用户尚未提供期末评分标准。Redis实际使用、外置Tomcat等如涉及教师特定评分项，单独对照课程要求；不为制造使用证据引入无业务用途组件，也不将内嵌Tomcat描述成已验证外置部署。

### 21.4 当前交接状态

用户确认设计及未来预留修订后，已另行编写任务级实施计划供审阅，并保留由新对话编码的安排。本对话不开始正式产品编码。所有运行上限、超时与兼容性以实施结果核验，任何未完成项保持显式，不以文档定稿宣称网站已交付。

## 22. 未来阶段预留复核（对照原需求V0.1）

### 22.1 复核结论与预留层次

原设计的组织关系、草稿修订、不可变送审内容、发布指针、报告执行历史和参考库版本可以继续使用。复核也发现预检目标、取消有效性、发布状态、流水线兼容及证据反馈身份原来不够具体，已补入本稿正文。

预留分三层：

1. **期中必须落实**：正确归属、独立状态、不可变内容、版本化模型/证据、可扩展检测类型、统一计算模块及数据库迁移机制。
2. **后续增量迁移**：预检快照、编辑租约、通知、授权附件、公共素材、临时来源、疑点反馈等新增表和入口；期中不提前建空系统。
3. **待评分/实验决定**：期末选择哪项检测提升、是否微调图片、图文一致性评价规模及最终性能目标；不能把“有接入位置”当作效果已达标。

本次补充是设计修订，不表示编码已经实现。既定期中功能与截止时间不变；期末仍优先检测能力，评分标准未出前不把全部后续业务安排进一周。

### 22.2 逐模块衔接表

| 原需求/未来工作 | 期中必须保留的基础 | 后续新增与迁移，期中不实现 |
| --- | --- | --- |
| 账号申请、审批和成员管理（3.2） | 账号稳定ID、互斥角色、enabled、实际操作者；授权检查读取当前有效关系 | account_application、审批原因、成员资料及管理页；联系方式/凭据交付按原开放项另定 |
| 多组织、离开组织、角色切换（3.1/3.3） | 成员关系独立，稿件归组织，不把创建人写成唯一权限依据；不限制一组织仅能一成员 | 组织切换、关系停用、身份转换事务、会话失效；不迁移稿件归属 |
| 共享编辑、自动保存（5） | 草稿revision、稳定节点、操作者和saveKind=MANUAL记录；保存服务不依赖“点了哪个按钮” | edit_lease的令牌/过期时间/心跳；AUTO保存模式及用户设置；同时检查租约和revision，撤回与租约边界另做并发验收 |
| 更丰富字体、字号和排版（4.2） | 编辑/阅读共用版本化文档schema，纯文本提取独立于外观 | 新marks/属性及schema迁移；旧稿按原schema读取，不因新样式强制改写历史 |
| 正文片段来源（4.3） | 来源有sourceId，文本块有稳定节点，快照保留来源和位置 | citation mark关联sourceId；版本差异包含引用变化；旧稿仅显示当时全文来源，不推造旧片段标注 |
| 授权转载与截图（4.4） | 文件按用途/业务对象授权，检测与发布只枚举正文BODY_IMAGE，不扫描全部上传文件 | 稿件整体声明、authorization_attachment随版本绑定，拒绝材料进入正文模型/发布/正式库；授权仍由人工判断 |
| 校内转载与首发许可（4.5） | 首次发布时间、默认允许字段和锁定时间随首次发布固定；导入材料不继承平台许可 | 转载入口、新稿来源关联及权限显示；不添加原稿变更自动同步 |
| 提交前自查（6） | scene与不可变输入DTO；算法不查询正式送审表；正式报告ACL不全局套到所有场景 | precheck_snapshot表、draftRevision/contentHash、批次目标外键及唯一约束；新预检入口只允许本组织读报告，草稿变化标旧报告失效；不得入库/自动训练 |
| 替换待审、撤回（7.3/7.4） | 当前版本指针、版本生命周期、取消标记、有效执行回写条件；决定接口检查当前版本 | 开放操作入口和新状态事务；保存superseded关系/撤回操作者；终止任务、拒绝旧页面决定；历史成功结果保留并标旧版 |
| 修改发布稿（7.2） | publication_state独立于送审状态，发布指针与草稿分离，参考作品身份关联稿件 | 开放APPROVED稿件编辑/重提；新版通过前保持旧版；新通过版替换参考revision，不重复保留多份有效条目 |
| 撤下、下架及后续人工处理（10.2） | 发布可见性独立，最后通过版本不删除；初始决定不可变 | publication_action追加事件及原因，publication_state扩展；下架前最后发布版仍留参考库并标记，不重写旧决定 |
| 文字语义及图片能力提升（8.1/8.2） | 统一离线/线上计算模块，pipeline manifest、特征兼容ID、缓存配置、原输入及报告schema | 新数据/训练/检索或重排策略与独立评价；必要索引重建；旧批次旧结果不覆盖，图片微调由证据决定 |
| OCR提升与中英文混排（8.3） | 原图、变换、多边形、置信度、识别与检索分阶段、低质量标记 | 新识别模型/处理器和真实转录数据；按配置失效相应缓存，重评CER/字段及定位，不能用更换工具名表示提升 |
| 图文相关与冲突（8.4） | 快照完整保留标题、正文结构、逐图图注和来源，不能只剩plain_text；检测type可扩展 | IMAGE_TEXT_CONSISTENCY处理器/请求、五类结果及双方证据；资料图/象征语境和不足输出；按实际图像内容隔离重新评价，API贡献单列 |
| 自身排除与同组织比较（8.5） | source→manuscript身份映射及候选前过滤；org不是免检条件 | 沿用同一规则；新检索策略回归自身排除和同组织他稿 |
| 库外按需提取与手动补充（9） | 匹配算法允许显式来源集合，证据sourceScope设计可扩展；不强制所有来源有reference_work_id | external_comparison/source_snapshot/material表及审核员入口；先展示实取材料，失败手动兜底；临时作用域不激活正式库；严格抓取按已验证支持范围接入 |
| 公共素材（11.4） | 独立文件身份和节点来源元信息，图片候选不直接等于整稿裁决 | public_asset及适用范围、插入选择、报告公共素材标识；只降低对应素材风险，不使整张海报/整篇稿件免检，仍参与一致性 |
| 常用原因（10.3） | review_decision.reason保存当时完整文字，不仅存模板ID | reviewer_reason_template表和维护页；模板修改不改变历史 |
| 疑点反馈（10.3） | evidenceId稳定且绑定attempt、批次、版本，报告不原地覆盖 | evidence_feedback表，确认问题/合理使用/判断有误；不自动套用新版、不当免检、不直接训练 |
| 版本差异（12） | 不可变图文/来源快照、节点ID、文件ID和码点映射 | 富文本结构差异、图片和声明差异；对照上一送审版或当前发布版；不展示原始HTML diff，不自动认定问题已解决 |
| 组织通知/发布后提醒（10.1/13.1） | 关键业务事件与事务一致记录、稳定事件ID/类型、组织/操作者/版本/时间；期中关闭通知 | notification及recipient/read状态、普通变化合并与重大事件独立、发布后疑点去重；按启用水位只消费新事件，不给历史批次补发提醒 |
| 时间线/管理员日志（13.2/13.3） | 结构化操作事件及当时姓名/组织/原因快照；报告/版本权限独立 | 面向角色的时间线投影及查询页；AUTO保存只更新保存时间，不逐次生成业务通知；技术日志不混进成员时间线 |
| 统计（15.1） | 稿件、版本、批次、项、attempt、决定分别有ID和时间 | 按口径聚合，不把重试当新稿；反馈统计待反馈表加入；审核决定不替代独立模型准确率 |
| 管理员参考管理（11.2/11.3） | 作品/内容revision/索引独立，启用请求与实际切换区分 | 内容编辑、移除、支持站点提取；批量导入继续为扩展；移除只影响新检索，证据保留 |
| 训练数据与评价（14/15.3） | 模型/数据/配置/划分协议版本与manifest、原始冻结文件，训练库与参考库分离 | 新原作簇、图像SHA、人工标签/转录及独立测试；已看测试作诊断，先冻结方案再评价；反馈仅候选材料 |
| 实验看板扩充（新增确认要求） | 按实验manifest定义taskType、数据集/划分、metricDefinitions、图表能力；只读已输出数据 | 展示检索Recall@K/MRR、图片评价、OCR CER、图文混淆/证据正确性等，不强塞进六模型分类模板；在线训练管理仍非核心 |
| 部署与规模 | 路径/端口/配置外置、API与计算分离、持久job、迁移与备份 | 服务器/HTTPS及更大库按实测调整；不提前引入分布式队列、多审核员分配或生产级吞吐承诺 |

### 22.3 必须落实的跨阶段调用约束

1. **输入快照与报告场景**：当前FORMAL由送审快照提供输入；未来PRECHECK使用草稿快照，EXTERNAL比较使用当前审核版本和临时来源快照。计算模块统一接收输入与配置，业务层各自决定权限、入库及结果有效性。scene参数不能由普通请求任意指定以绕过权限。
2. **发布与审核两条状态线**：新稿待审不发布，发布稿修改待审仍发布旧版，撤回待审只影响该次送审，下架才影响可见性。不得把“不是APPROVED”统一解释为不可展示。
3. **取消与人工决定分开**：撤回/替换使旧计算失效；人工决定不使计算失效。期中实现回写有效性条件但不开放取消功能，未来新增取消入口即可沿用。
4. **模型/索引/报告可复核**：每批固定manifest；同一权重不同预处理也是不同配置；特征空间不兼容必须重建或拒绝；旧配置丢失明确失败；新方法另建批次。
5. **证据与许可分开**：相似证据属于技术输出，合理使用反馈、授权截图、平台转载许可分别留存，不由一个布尔字段代替，也不使其余内容免检。
6. **授权材料隔离**：模型输入、发布输出和参考入库采用用途白名单；以后新增附件不会因“也是图片文件”被自动扫描或展示。
7. **事件与通知解耦**：期中记录业务事件，后续才产生用户通知。保存细节含saveKind=MANUAL；未来AUTO不能触发普通变化通知。状态更新和事件同事务，不能只在页面点击时记日志。
8. **新数据不覆盖旧证据**：新增库、新实验、新模型、来源修改和账号资料变化都不重写历史含义。使用增量SQL迁移与数据版本，不把期中成果当一次性演示库重建。

### 22.4 原需求12项功能验收的后续归位

| 原需求15.2项 | 期中覆盖与后续衔接 |
| --- | --- |
| 1 多组织/协作/越权 | 期中验越权；多组织切换和协作基于现有成员关系增量 |
| 2 编辑占用/旧页 | 期中验revision旧页保护；租约/过期令牌后续加 |
| 3 草稿/送审/预检失效 | 期中验快照分离；预检独立快照及哈希后续加 |
| 4 来源/授权/公共素材 | 期中验基本来源；授权/素材独立用途后续加 |
| 5 替换/撤回/旧审核 | 期中不开放；已有版本指针和失效边界，后续验状态与取消 |
| 6 人工先决定/后补提醒 | 期中继续检测但不提醒；后续显式启用提醒，不自动改决定 |
| 7 发布修改/下架保库 | 期中验首次发布和入库；双状态线/参考revision支撑后续 |
| 8 自身排除/同组织 | 期中实际验收，未来换模型继续回归 |
| 9 库外提取/兜底 | 后续临时来源作用域接入，不伪装为正式库 |
| 10 预检可见/正式不可见 | 期中验正式ACL；后续预检专用ACL，不开放全部report接口 |
| 11 通知/时间线/追溯 | 期中记录事件及身份；通知合并/角色时间线后续加 |
| 12 首发转载许可 | 期中保存默认许可及首发锁定；后续开放入口和可选许可操作 |

完整预留意味着这些原目标都有明确衔接位置，不意味着原目标已通过质量或工期验收。以上补充作为当前设计修订供用户审阅，涉及后续界面和评价规模的开放问题继续保留，不以设计默认值代替用户决策。

### 22.5 原目标及非目标保持

同义替换、句式改写、常见图像变形和适用的图文关联/冲突提示仍保留为原核心目标，当前未证实效果不自动降为扩展。后续围绕代表性样本补证和改进，不默认重跑已冻结的全部实验。

深度重写、极小局部/拼图识别、批量导入及在线训练管理继续按原扩展边界处理。全网查重、英文长文/跨语言检测、多审核员分配、社区功能和转载版本联动不因“预留完整”自动加入范围。

本次独立只读复核重点检查了取消与人工决定、预检与正式权限、发布后动作与初始决定约束三处，未发现剩余明显跨阶段阻塞。结论限于设计可衔接性，不代表功能或性能已运行验证。
