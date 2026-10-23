# 校园图文审核系统

毕业设计：基于深度学习的图文审核系统的设计与实现——以南京传媒学院为例。

当前开发进度见 `docs/midterm/progress.md`。这是分阶段实现中的工程，尚未完成期中整体验收。

## M01：运行基础

需要已有 JDK21、Maven3.9、MySQL8、Python3.11。工具路径见 `app/config/local.example.json`；如需修改，复制为被忽略的 `local.json`。不使用系统 MySQL80，不注册系统服务，只运行独立3308实例。

在项目根目录执行：

```powershell
app/scripts/init.ps1
app/scripts/status.ps1
app/scripts/check.ps1 -Task M01
```

初始化会创建新的项目运行目录和随机凭据，已有数据与凭据不会重置。数据库业务迁移具有校验和，已应用SQL不得修改；升级添加新的有序迁移文件。测试只连接 `campus_review_midterm_test`，不清理业务库。

当前账户密码保存在本机 `runtime/private-config/accounts.json`，数据库凭据保存在 `runtime/private-config/database.json`，均禁止上传。预置账号为member1、member2、reviewer、admin，对应两组织成员、审核员及管理员，初始密码随机生成。

源码仓库不包含模型、数据集、运行库或依赖环境。冻结实验只读复用，本地文件哈希清单保存在 `docs/midterm/evidence/frozen-assets.json`，后续运行需按设计配置已有资产。不会自动下载或重新训练整套模型。

本机真实验证：MySQL8.0.46；迁移重复执行、数据保留、校验和变化拒绝与测试数据库保护2项集成测试通过；运行目录/3308保护1项Python测试通过。完整业务和六图容量尚未验证。

## M02：会话认证与前端外壳

已实现真实会话登录、退出、CSRF、密码哈希、当前成员关系授权、按角色导航和外观偏好。业务页面按M03—M12逐步接通，当前不能当作完整审核网站使用。

```powershell
app/scripts/check.ps1 -Task M02
app/scripts/build.ps1
```

前端依赖已锁定，已有环境中安装用`npm ci --registry=https://registry.npmjs.org`；本项目使用TypeScript5.9.3以兼容vue-tsc。新增环境或依赖必须经用户同意。

构建后前端由Java的8080同源提供。Java启动须设置CAMPUS_DB_PASSWORD、CAMPUS_MIGRATIONS和CAMPUS_ACCOUNTS_FILE指向本项目配置；不要把密码写入命令行参数或提交脚本。统一启动/停止和恢复入口将在M13完成。目前进程由本对话受控启动，端口可用不代表检测模型已就绪。
