# 当前项目审查报告

本报告针对现有项目持续修改后的版本。未重新初始化项目，保留已完成的 API、数据模型和 React 功能。

## A. 已完成

- React 所需页面，以及物品编辑、分页和失败提示；生产使用静态构建 + Nginx。
- FastAPI 基础 CRUD、树结构位置、照片上传、普通搜索、移动和历史 API。
- 九张要求的表和固定 Alembic 初始迁移；有事务、外键引用保护、树循环校验。
- PostgreSQL 17、Redis AOF、图片、备份均配置宿主机 bind mount。
- DATA_ROOT / STORAGE_ROOT 参数化，Mac 与 NAS 路径独立，无 Mac 绝对路径写入部署配置。
- init/check-deployment/backup/restore/update/self-check 脚本；SHA256、维护锁、恢复确认、恢复前备份。
- TTL 最多 600 秒的树/搜索缓存，数据库版本使失效在 Redis 故障恢复后仍正确。
- 完整 README、fnOS 部署说明、Docker 数据安全、GitHub 工作流和跨 NAS 迁移说明。

## B. 未完成或未验证

- 当前机器未安装 Docker，无法启动 Compose 或连接真实 PostgreSQL/Redis；没有访问实际 fnOS NAS。
- 无登录认证、多用户/多家庭权限控制。仅限可信家庭内网，不适合公网服务。
- 分类只有初始分类和读取 API；标签表已预留，未实现分类/标签编辑界面。
- 用户配置缓存仅预留用途；没有用户配置 API。
- 暂无照片删除、更换封面、孤立文件自动清理；删除物品后原文件保留。
- 已提供定时备份配置示例，尚未在用户 NAS 安装/执行计划任务。
- 未完成浏览器交互验收、真实 NAS 权限/ACL/重启验收。
- 未连接用户 GitHub 仓库，未提交或推送；CI 文件已就绪，但未执行远端流水线。

## C. Docker 数据是否真正持久化

**配置层面已经持久化；运行层面仍需验收。** 四类路径使用外部目录，PostgreSQL 17 的挂载目标正确。没有仅把数据库/图片放在容器内部。备份由宿主机脚本写入 DATA_ROOT/backups，容器只读挂载，备份写入不依赖后端容器寿命。

但在没有 Docker daemon/NAS 的情况下，不能声称已实测删除容器后数据仍在。部署时必须核对 `.env`、目录写权限、数据盘挂载和 self-check 结果。

## D. 删除容器后哪些数据保留

在 bind mount 路径不变且未删除宿主机文件的前提下：

| 操作 | 保留的数据 |
| --- | --- |
| 删除 backend | PostgreSQL 所有记录、照片、历史、Redis 数据、备份 |
| 删除 frontend | 所有业务数据；前端静态资源可由镜像重建 |
| 重建 PostgreSQL 容器 | DATA_ROOT/postgres 内的数据库 |
| 重建 Redis 容器 | DATA_ROOT/redis 内的 AOF |
| build / git pull | 所有独立数据目录 |
| docker compose down | 以上所有 bind mount 数据 |

`down -v` 可能删 Docker 管理的 volumes；本项目 bind mount 不会被它删除，但仍明确警告不要惯用。手工删数据目录、错误覆盖、磁盘故障不受容器持久化保护。

## E. 当前是否适合飞牛 NAS

适合进入**家庭内网试部署/验收阶段**，尚不能标记为已生产验收。配置允许实际 NAS 路径，脚本支持 Linux/macOS 校验工具，检查真实服务 UID 写权限，不使用 chmod 777。

还需要在 NAS 执行初始化、部署检查、Compose 启动、self-check、一次人工确认的恢复演练，再确认计划备份执行成功。未加入认证前禁止公网开放。

## F. Mac ARM 与 NAS AMD64

没有发现代码或 Dockerfile 绑定 Mac 架构的问题：官方多架构 Python、Node、PostgreSQL、Redis、Nginx；无 platform 硬编码；依赖在目标机器容器中安装；不复制本地 node_modules/.venv。

官方支持架构：[Python](https://hub.docker.com/_/python)、[Node](https://hub.docker.com/_/node)、[Redis](https://hub.docker.com/_/redis)、[PostgreSQL](https://hub.docker.com/_/postgres)、[Nginx](https://hub.docker.com/_/nginx)。这是设计与官方文档核对结果，两种架构的 Docker 实际构建尚未执行。CI 已配置 AMD64 / ARM64 原生 runner，待推送验证。

PostgreSQL 保持 17；不直接切换 18+。[官方目录变更规则](https://hub.docker.com/_/postgres)

## G. 备份和恢复是否真的可以使用

代码已实现完整流程，shell 语法与归档安全测试已验证；**真实 pg_dump/pg_restore、NAS 文件权限和 restore.sh 完整运行目前未验证，不能承诺已实测可用。**

备份暂停后端写入，确保数据库和照片一致，输出压缩 dump、图片归档、SHA256 和清单；恢复要求输入 RESTORE，先备份当前数据，单事务恢复数据库并清理 Redis 缓存。旧照片不会被自动删除。update.sh 不执行备份过期清理。

self-check.sh 在有 Docker 的环境中会进行真实数据/图片持久化测试、Redis AOF 重建、真实备份和隔离恢复。CI 另在一次性测试库上运行 restore.sh 的取消与确认分支；这些流水线尚未运行。

## H. 下一步优先事项

1. 在 Mac Docker Desktop 或 NAS 启动四个服务，运行 self-check；核实物品、图片、历史和备份恢复。
2. 在隔离 NAS 测试环境完整执行 restore.sh，确认恢复后界面与图片正常；再进行正式数据登记。
3. 配置每日计划备份，保留异机副本，定期恢复演练。
4. 推送 GitHub，运行双架构 CI；再进行一次升级脚本与失败处理演练。
5. 若需要家庭多账号或远程访问，再优先增加认证与权限控制。

## 已执行验证

- 15 项本地测试通过：API 合约、移动历史、错误移动原子性、循环检测、位置删除保护、缓存失效及 Redis 故障回退、照片格式与封面、数量/搜索校验、删除关联记录、归档路径穿越和链接拒绝。
- 这些 API 测试使用临时 SQLite 和缓存替身，**不等于 PostgreSQL/Redis 集成测试**。
- pnpm 锁文件安装成功；React/Vite 生产构建成功。
- Alembic 使用 PostgreSQL 方言成功输出初始迁移 SQL（离线），未在 PostgreSQL 执行。
- 所有 shell 脚本 bash -n 语法通过。
- Compose / 开发覆盖 / CI / pnpm YAML 语法与四类挂载结构断言通过；没有运行 Docker Compose 自身的 config 验证。
- check-deployment.sh 在当前机器正确报告“未安装 Docker”，退出码 1。

## 用户要求的 11 项容器验收

| 场景 | 当前结果 |
| --- | --- |
| 1. compose up -d 全服务正常 | 未执行：无 Docker |
| 2. 创建测试物品 | 本地 API 测试通过；容器未执行 |
| 3. 上传测试图片 | 本地 API 测试通过；容器未执行 |
| 4–6. 删除重建 backend 后物品和图片保留 | 已提供自检脚本，未执行 |
| 7–8. 重启 PostgreSQL 数据保留 | 已提供自检脚本，未执行 |
| 9–10. 执行备份并生成数据库和图片备份 | 已提供脚本，真实备份未执行 |
| 11. README 完整写明恢复方法 | 已完成，包括确认、失败处理、新机恢复 |

运行环境限制已明确保留，未将未执行的 Docker/NAS 测试写成“通过”。
