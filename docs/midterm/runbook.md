# 本机期中版操作手册

工作目录为 `D:\Data\GraduationProjectVersionC`，PowerShell中先切到该目录。软件路径、端口、输入限额和超时读取 `app/config/local.json`；不存在时读取 `local.example.json`。首次初始化与后续启动分开。当前已初始化，不要重新安装模型环境、重置凭据或改系统MySQL80。

## 启动与状态

```powershell
& app/scripts/start.ps1
& app/scripts/status.ps1
```

启动只调用现有JDK、主Python、独立OCR Python和项目3308 MySQL，不安装依赖、不构建工程、不清库。需要更新网页/Java时，先停止项目Java，再运行 `app/scripts/build.ps1`，最后 `app/scripts/start.ps1 -Component java`。

正式演示地址为 `http://127.0.0.1:8080`，前端静态构建由Java同源提供。开发用5173页面需要另外运行现有npm dev；统一入口不启动或终止开发Vite进程。当前8080、18081、18082、3308均仅绑定本机。

`status`分别给出网页ready、主检测ready/busy/runId、OCR ready/busy/runId；网页可登录不代表模型已经加载完成。模型启动等待上限每个180秒，未就绪会非零返回，保留进程日志，不再并发启动另一个进程。`owned=false`的监听服务不会被自动接管或终止。

进程登记位于 `runtime/processes/`，日志为 `runtime/logs/java.log`、`detector.log`、`ocr.log`。登记包括PID、创建时间、程序路径、完整参数、工作目录及模型runId；Windows OCR虚拟环境父进程与实际监听子进程分别核验。不要修改登记来强行匹配未知PID。启动/停止/备份入口使用同一Windows文件锁，避免并发管理。

## 停止与中断恢复

```powershell
& app/scripts/stop.ps1
# 明确中断本项目正在执行的计算（常规演示应先等待队列结束）
& app/scripts/stop.ps1 -Interrupt
# 仅停止项目OCR，或只关闭项目3308实例
& app/scripts/stop.ps1 -Component ocr
& app/scripts/stop.ps1 -StopMysql
```

停止按Java、主检测、OCR顺序执行；默认保留3308，可通过 `-StopMysql` 关闭经过datadir认证的项目实例。对繁忙或无法证明空闲的模型，默认拒绝停止；`-Interrupt`才表示有意中断已登记的项目进程。未知监听、PID复用或runId不一致会报错并保留未知进程。脚本不使用按进程名批量终止，也不操作系统MySQL80。

Java重启后会话失效，需要重新登录，稿件及报告仍在数据库。单worker持MySQL advisory lock串行调度；旧RUNNING任务只有在两个模型均证明ready且idle后才回收。成功项和历史结果不清空，旧执行标为INTERRUPTED，未完成项创建新attempt。取消/撤回/被替换的版本不会自动重试。历史pipeline与库代保持固定，旧配置缺失返回CONFIG_UNAVAILABLE，索引不兼容明确失败；不偷偷换当前模型或自动启用孤立新库。

HTTP超时的旧attempt记TIMED_OUT，业务项显示失败并允许人工重试；超时并不证明远端计算已停止。worker等待服务空闲后再继续可执行项目。OCR识别与其文字比对共享每图180秒预算，成功识别中间结果保留。单项失败可在审核页重试，其他成功项不重做。

## 备份与隔离恢复验证

先等待业务队列完成，停止Java，模型保持已停止或可证明空闲：

```powershell
& app/scripts/stop.ps1 -Component java
& app/scripts/backup.ps1
```

备份新建 `runtime/backups/<时间-随机编号>/`，包括业务SQL、uploads、derived、历代indexes、experiments、私有配置、应用配置及冻结模型文件清单。模型原文件仍在冻结目录，备份清单用于校验，不重复复制大型权重。校验全部文件与manifest后才写READY。备份含密码、内部令牌及业务数据，仅保存在本机，不能上传GitHub或放入公开报告。

使用备份命令输出的实际目录，并显式指定不存在的恢复目标：

```powershell
& app/scripts/restore.ps1 -Backup '<实际备份绝对路径>' -Target 'D:\Data\GraduationProjectVersionC\runtime\restores\演示恢复1' -Port 3318
```

恢复入口只接受全新的 `runtime/restores/` 子目录与3310—3399空闲端口，绝不覆盖现有业务目录或现有数据库。它校验备份后复制snapshot，初始化临时MySQL，将SQL导入 `campus_review_restore`，核对文件哈希、稿件/版本/执行/参考/发布计数，写入 `verification/result.json`，最后认证datadir并关闭临时实例。失败目录保留供诊断，不在原目录重复覆盖重试。

这是可独立检查的还原副本，**不会自动激活为业务运行目录**。历史manifest中的绝对路径及其哈希保持原样。灾难恢复到原项目运行位置需要先停服务、保存当前目录，并明确选择备份后人工执行目录切换；不得把隔离核验当成已完成跨机器路径迁移。原运行目录启动仍读取原有3308，恢复验证后可重新运行 `start.ps1`。

M13实测：备份 `20261023T134406Z-f02aedea`，恢复 `runtime/restores/M13-20261023T2146`；220文件校验，稿件7、送审7、检测执行36、参考199、发布2一致。恢复前后的系统MySQL80保持Running。后续验收新增稿件时计数自然增加，不能用此历史快照计数代替当前状态。

## 实验包与验证

```powershell
& validation/text/env/python.exe -B app/scripts/export_experiments.py
& app/scripts/check.ps1 -Task M12
& app/scripts/check.ps1 -Task M13
& app/scripts/check.ps1 -Task ALL
```

导出只读取冻结CSV/JSON/逐条分数，不加载或训练模型。目录指针只在完整版本包校验通过后原子切换。管理员网页手动或每10秒检查更新，不触发训练；新包坏损时保留上次已验证图表。

默认测试使用独立 `campus_review_midterm_test`，真实模型测试默认明确跳过；单元/故障测试与真实业务探针分开记录。正式恢复探针 `probe_recovery.py interrupt/verify` 只用于明确标记的验收稿件，会有意中断已登记的项目服务，不用于日常演示。真实批次8已完成13项，原成功attempt保留，未完成项换新attempt，旧发布快照仍可读。详见 `evidence/M13-recovery.json`。
