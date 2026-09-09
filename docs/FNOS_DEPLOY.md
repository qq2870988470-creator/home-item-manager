# 飞牛 fnOS NAS 部署说明

本指南基于当前仓库，不需要在 NAS 重新生成代码。Mac 开发、调试、Git commit/push；NAS clone/pull、原生构建 Linux 镜像、运行服务、保存数据和备份。当前仅适合可信家庭局域网；尚无登录认证，不要直接发布公网。

## 1. 前置检查与架构

在 fnOS 启用 Docker，确认 SSH/终端账号具备 Docker、Git、Bash 权限，并有 `gzip`、`sha256sum`（或 shasum）。执行：

```bash
docker version
docker compose version
docker info --format '{{.Architecture}}'
```

Apple Silicon Mac 使用 Docker Desktop Linux arm64；常见 x86_64 NAS 使用 Linux amd64。本项目采用官方 `python:3.12-slim`、`node:22-alpine`、`nginx:1.28-alpine`、`postgres:17-alpine`、`redis:7-alpine`，没有写死 platform，依赖在目标架构的容器内安装。

NAS 应自行 `docker compose build`，不要把 Mac 的 ARM 单架构镜像 docker save 后直接在 AMD64 NAS 运行，也不要复制 node_modules、.venv。`.dockerignore` 排除了本地依赖、数据和秘密。

官方镜像支持架构依据：[Python](https://hub.docker.com/_/python)、[Node](https://hub.docker.com/_/node)、[PostgreSQL](https://hub.docker.com/_/postgres)、[Redis](https://hub.docker.com/_/redis)、[Nginx](https://hub.docker.com/_/nginx)。这里是架构设计审查，不能替代两类机器的实际构建运行验收。镜像标签可能更新，生产变更需重新测试，PostgreSQL 始终固定主版本 17。

## 2. 创建项目目录并 clone

以下 `/vol1/docker/` 只是示例。先在 fnOS 文件管理/共享目录确认真实路径，存储池不同可能名称不同；使用当前账号有权限的专用目录。数据目录和代码目录建议平级：

```text
/实际共享目录/home-item-manager/
├── app/       # Git 仓库
├── data/      # postgres、redis、backups
└── storage/   # images
```

```bash
mkdir -p /vol1/docker/home-item-manager
cd /vol1/docker/home-item-manager
git clone https://github.com/YOUR_ACCOUNT/home-item-manager.git app
cd app
cp .env.example .env
```

私有 GitHub 仓库使用 NAS 的只读 deploy key 或合适的凭据管理；不要在仓库 URL 中写 token，也不要提交生产 `.env`。

## 3. 配置 NAS 的 .env

编辑 `.env`：

```dotenv
APP_ENV=production
DATA_ROOT=/vol1/docker/home-item-manager/data
STORAGE_ROOT=/vol1/docker/home-item-manager/storage
POSTGRES_DB=home_items
POSTGRES_USER=homeapp
POSTGRES_PASSWORD=填入独立长随机密码
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=填入另一项独立长随机密码
CACHE_TTL=600
BIND_ADDRESS=192.168.1.20
FRONTEND_PORT=8080
```

把 NAS IP 和共享目录改成真实值。也可以 `BIND_ADDRESS=0.0.0.0`，但必须由防火墙限制可信内网；禁止公网映射。默认示例的 127.0.0.1 只允许 NAS 本机访问。

只需修改 `.env`，不改 Compose。NAS 使用绝对路径；Mac 使用 `./data`、`./storage`，两边不共享数据库文件。相对路径按项目目录解析。

## 4. 初始化目录与权限检查

```bash
bash scripts/init.sh
bash scripts/check-deployment.sh
```

初始化构建镜像，仅针对空目录设置 PostgreSQL/Redis 自身用户和图片 UID 10001 的权限。已有目录不递归改权限。检查脚本会实际尝试以服务 UID 写入临时文件并删除，同时检查 Docker、Compose、.env、必需变量、示例密码和配置合法性。

若失败，按输出的准确目录检查 fnOS 共享权限/ACL、文件系统只读状态和可用空间。部署账号需要写备份，容器用户需要写各自数据目录。不要使用 chmod 777。若目录中已有 PostgreSQL 数据，只能修正属主/ACL；不能删除内容重新初始化。远程 NFS/root-squash 可能阻止 chown，不建议把 PostgreSQL 运行目录放在这类共享盘。

## 5. 启动、查看状态、日志

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
# 可等待所有健康检查通过：
docker compose up -d --wait --wait-timeout 180
```

浏览器访问 `http://NAS局域网IP:8080`。后端第一次启动会执行 Alembic 创建数据库表。查看 `/api/health` 的 postgres、redis，应都为 true。故障定位：

```bash
docker compose logs --tail=100 backend postgres redis
docker compose exec backend alembic current
```

frontend 使用 React build + Nginx 长期运行，不使用 Vite 开发服务器；backend 不启用 reload。不要给生产命令加 docker-compose.dev.yml。

## 6. 数据安全与停止服务

| 数据 | NAS 目录 | 容器路径 |
| --- | --- | --- |
| PostgreSQL 17 | DATA_ROOT/postgres | /var/lib/postgresql/data |
| Redis AOF | DATA_ROOT/redis | /data |
| 照片 | STORAGE_ROOT/images | /app/storage/images |
| 备份 | DATA_ROOT/backups | /app/backups，只读挂载 |

`docker compose down` 仅删除容器和网络，本身不会删除这些宿主机 bind mount 目录。删除 backend/frontend、重新 build、重建 PostgreSQL 容器或 `git pull` 不会删除数据库/照片/备份。Git 仓库和 NAS 数据目录分开，更新源代码不触碰数据。

前提是 `.env` 一直指向原目录、磁盘已正确挂载且可写。数据盘未挂载时不要启动，避免在错误的空目录初始化数据库。

**危险命令：** `docker compose down -v`（会删 Docker 管理的 volumes；本项目 bind mount 不会因此删除，但仍避免使用）、`docker volume prune`、`rm -rf 数据目录`。不要随意删除 data、storage 或 NAS 共享目录。不要复制运行中的 PostgreSQL 原始目录来迁移，也不要直接切换 PostgreSQL 主版本。

当前固定 PostgreSQL 17，官方数据目录是 `/var/lib/postgresql/data`。18+ 的官方目录规则不同，不能只改 image 标签。请先备份，在新路径/新容器通过逻辑恢复演练主版本升级。[官方说明](https://hub.docker.com/_/postgres)

## 7. 更新代码与数据库

推荐：

```bash
bash scripts/update.sh
```

流程：确认干净 Git 工作区 → 检查目录 → 暂停后端 → pg_dump + 图片完整备份 → git pull --ff-only → build → Alembic migration → up -d → PostgreSQL/Redis 健康检查。不会自动删除旧备份，也不会删除数据库重建表。

基础更新命令确实是：

```bash
git pull
docker compose up -d --build
```

但生产不要跳过备份：新版启动可能自动迁移数据库，应使用安全脚本。手工操作需先 `bash scripts/backup.sh`，停止后端写入，再 pull/build/migration/up。仅当明确无结构变更且已有可恢复备份时，才直接用基础命令。

失败时脚本输出原 Git commit、备份路径和失败阶段。迁移失败不要启动旧版本猜测兼容性；先查看日志。需要回退时在隔离环境验证备份与旧 commit，然后按恢复步骤操作；不自动硬重置代码或回滚数据库。

## 8. 手动和自动备份

```bash
bash scripts/backup.sh
```

备份保存在 `.env` 中 DATA_ROOT 的 backups 子目录，包含同一维护时段的数据库压缩 dump、图片 tar.gz、SHA256 和清单。脚本短暂停止后端，完成后恢复。默认保留最近 30 天，只有普通 backup.sh 执行过期清理；update.sh 和 restore.sh 的安全备份不做清理。

在 fnOS 计划任务功能（名称随系统版本可能变化）或 cron 中设置每日执行本项目 backup.sh 的**绝对路径**。先手工运行成功，再配置调度并检查输出；任务账号需要 Docker 和数据目录权限。

```cron
0 3 * * * /bin/bash /vol1/docker/home-item-manager/app/scripts/backup.sh >> /vol1/docker/home-item-manager/backup.log 2>&1
```

定期把整个时间戳备份目录复制到不同设备/离线盘，别只保存在 NAS 同一块盘。

## 9. 恢复备份

先确认 `.env` 指向目标 NAS 数据目录，核对备份代码版本：

```bash
docker compose up -d --wait postgres redis
bash scripts/restore.sh /vol1/docker/home-item-manager/data/backups/实际时间戳目录
# 手工输入 RESTORE
docker compose up -d --wait
```

恢复脚本先验证校验和和归档安全性，确认后备份当前数据库/照片，再恢复照片和数据库，清理专用 Redis 缓存，执行迁移。数据库 restore 使用单事务；失败则回滚该事务。不会删除其他现存照片。缓存清理或迁移失败会保持后端停止。

恢复后确认物品、照片、历史都正常，并立即执行一次新备份。不要仅看到“数据库导入完成”就认定恢复成功。完整行为和失败处理参见 README 的恢复章节。

## 10. 迁移到另一台 NAS

1. 旧 NAS 安排维护，停止用户写入，运行备份，记下当前 `git rev-parse HEAD` 和数据库主版本 17；备份完成后保持旧实例停写，避免迁移期间新数据遗漏。
2. 安全传输完整备份目录（四个文件）、对应代码 commit 信息。`.env` 凭据通过独立安全渠道保存，不上传 GitHub。
3. 新 NAS clone GitHub，检出匹配 commit，创建新的 `.env`，设置新 NAS 实际路径与密码/IP。
4. 新 NAS 运行 init.sh/check-deployment.sh，启动 postgres/redis，按第 9 节恢复。新数据库用户名可不同，脚本使用 --no-owner/--no-privileges。
5. 新 NAS 原生构建镜像，启动所有服务，执行持久化自检并人工检查真实物品、图片、历史。
6. 验收后切换访问地址，配置新 NAS 自动备份。旧 NAS 和旧备份暂时保留，不要立刻清理。

跨 ARM/AMD64 迁移传递 Git 源代码、pg_dump 和图片归档，不传递 Mac 镜像或原始 PostgreSQL 数据文件。

## 11. 上线前验收

```bash
bash scripts/self-check.sh
```

脚本会实际重建服务，请安排维护时间。测试物品保留，备份恢复在临时隔离数据库中完成，不覆盖当前业务库。还需首次手工操作界面、确认 NAS 重启后路径仍正确，以及一次完整 restore.sh 的确认/恢复演练。详细未验证项目请查看 docs/REVIEW.md。
