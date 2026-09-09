# 家中有数 · 家庭物品位置管理系统

React + FastAPI 的单家庭物品管理应用，记录物品所在位置、照片和位置变更历史。Mac 用于开发和提交代码；飞牛 fnOS NAS 用于从 GitHub 构建部署、保存数据和备份。

**核心原则：容器可以删除和重建，数据库、图片、备份必须保存在宿主机。**

当前是可信家庭网络第一版：无登录认证、无多家庭权限隔离，`users` / `homes` 已预留，固定使用 home_id=1。默认只监听本机 `127.0.0.1:8080`。NAS 访问请绑定可信局域网地址并配置防火墙；未加入认证前不要开放公网、端口转发或公开反向代理。

部署教程：[飞牛 NAS 部署](docs/FNOS_DEPLOY.md)。验证范围：[实际审查报告](docs/REVIEW.md)。

## 功能与技术架构

- 物品新增、编辑、分页列表、详情、删除；数量和位置校验。
- 自引用 `locations.parent_id` 位置树；阻止循环和删除仍被引用的位置。
- 搜索名称、描述及当前直接位置名称；PostgreSQL 普通不区分大小写查询，转义 `%` / `_`，未引入 Elasticsearch。
- 移动物品和编辑位置都在数据库事务内写入历史；首次登记也产生历史。重复移动到同一位置不新增历史。
- JPG / PNG / WebP 上传，最大 10 MB、限制像素；验证并重新编码为 JPEG，移除元数据，UUID 文件名。首张为封面。
- React 页面：主页、物品列表、添加、编辑、详情、搜索、位置管理、位置树、移动、历史。
- PostgreSQL 17 是唯一正式数据源；SQLAlchemy + Alembic 管理表结构。应用不调用 `create_all`。
- Redis 7 使用 AOF、`appendfsync everysec`；位置树和搜索缓存最长 600 秒。用户配置缓存仅预留命名空间用途，尚无配置 API。
- 缓存键包含数据库中事务性递增的家庭版本号。写入即切换版本，旧缓存不可再命中并在 TTL 后释放。Redis 故障时查询回退数据库。
- 前端由 Nginx 提供 React 编译产物，并代理 `/api/` 和 `/images/`。后端 Uvicorn 正式启动，不启用 reload。

四个服务：frontend、backend、postgres、redis。只有 frontend 对宿主机开放端口；数据库和 Redis 不公开端口。Nginx 使用 Docker DNS 动态解析后端，后端重建 IP 改变后代理可重新解析。

## 项目目录

```text
home-item-manager/
├── backend/                 # FastAPI、模型、Alembic 固定迁移、Dockerfile
├── frontend/                # React、Nginx、pnpm 锁文件、Dockerfile
├── storage/images/          # Mac 默认照片目录（不入 Git）
├── data/
│   ├── postgres/            # PostgreSQL 17 数据（不入 Git）
│   ├── redis/               # Redis AOF（不入 Git）
│   └── backups/             # 压缩备份集（不入 Git）
├── scripts/                 # 初始化、检查、备份、恢复、更新、自检
├── tests/                   # API 合约与归档安全测试
├── docs/FNOS_DEPLOY.md
├── docs/REVIEW.md
├── docker-compose.yml
├── docker-compose.dev.yml   # 可选 Mac 开发覆盖
├── .env.example
├── .gitignore
└── README.md
```

Git 不保存空数据目录，新部署使用初始化脚本创建。NAS 数据通常放在仓库之外，路径只需修改 `.env`。

## 环境变量配置

复制 `.env.example` 为 `.env`。生产 `.env` 绝不上传 GitHub，也不要提交含展开密码的 `docker compose config` 输出。

| 变量 | 默认示例 / 作用 |
| --- | --- |
| APP_ENV | production，部署标识 |
| DATA_ROOT | ./data；NAS 改为实际绝对目录 |
| STORAGE_ROOT | ./storage；NAS 改为实际绝对目录 |
| POSTGRES_DB | home_items |
| POSTGRES_USER | homeapp |
| POSTGRES_PASSWORD | 必须把 change_me 改为长随机密码 |
| REDIS_HOST / REDIS_PORT | redis / 6379，默认 Compose 内部服务 |
| REDIS_PASSWORD | 独立长随机密码，必须替换示例 |
| CACHE_TTL | 600 秒，上限 600 |
| BIND_ADDRESS | 127.0.0.1；NAS 可用固定局域网 IP |
| FRONTEND_PORT | 8080 |

容器内 `POSTGRES_HOST=postgres`、`POSTGRES_PORT=5432`、`IMAGE_DIR=/app/storage/images`、`BACKUP_DIR=/app/backups` 由 Compose 配置。后端通过 SQLAlchemy URL 对密码编码，不拼接未经编码的 URL。建议使用 `openssl rand -hex 32` 分别生成两项密码；复杂含 `$` 的 dotenv 值需遵循 Compose 引号规则。脚本使用 Compose 解析 `.env`，不会 `source .env` 执行内容。

**已有数据库中，修改 `.env` 的用户名/密码/数据库名不会重新初始化数据库或自动改密。** 必须先备份，通过 PostgreSQL 正规改密操作同步修改凭据，不能删除数据目录来“解决连接问题”。

## Docker 启动方法

需要 Docker Engine/Desktop、Docker Compose v2（支持 `--wait`、`config --environment`，建议 v2.24+）、Bash、Git，以及 `gzip` 和 `sha256sum` 或 `shasum`。fnOS 的共享目录需允许当前账号写备份，允许容器服务用户写各自数据目录。

```bash
cp .env.example .env
# 编辑 .env：设置两项强密码和实际数据路径
bash scripts/init.sh
bash scripts/check-deployment.sh
docker compose up -d --build --wait
docker compose ps
```

`init.sh` 构建镜像，仅为空目录设置对应容器用户属主；不递归修改已有数据权限。`check-deployment.sh` 用 PostgreSQL、Redis 和 backend 实际容器 UID 测试写权限，失败会指出目录。**不会执行 chmod 777。** 备份目录由宿主机部署账号管理；后端对 `/app/backups` 只读挂载，降低误删风险。

打开 [本机应用](http://localhost:8080)。API 健康检查 [health](http://localhost:8080/api/health)。默认健康输出包含 postgres、redis；Redis 故障显示 degraded，但后端继续工作。Postgres 故障返回 503。首次启动依赖两个服务健康，后续 Redis 故障不影响基本 CRUD。

初始迁移创建一个管理员、一户“我家”、一个顶层位置和三种分类。通过 `http://localhost:8080/api/docs` 查看交互 API 文档；开发模式也可使用 `http://localhost:8000/docs`。

### Mac 开发

Mac `.env` 使用 `APP_ENV=development`、`DATA_ROOT=./data`、`STORAGE_ROOT=./storage`；不要指向 NAS 生产数据。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
cd frontend
# 安装 Node.js 22.13+ 和 pnpm 11.19.0 后
pnpm install --frozen-lockfile
pnpm dev
```

开发覆盖仅在 Mac 本地开放 8000 并启用后端 reload；生产不加载此文件。浏览器使用 Vite 输出的地址，`/api` 自动代理到本机 8000。源代码在镜像内安装依赖，不 COPY Mac 的 node_modules 或 .venv。请勿同时在相同数据目录运行两个 Compose 项目。

## 数据库与 API

表：users、homes、locations、items、categories、tags、item_tags、item_photos、item_location_history。所有要求字段均已包含，时间使用带时区数据库字段。照片表只有路径和元数据，不保存图片二进制。分类与标签结构已建好，标签管理暂未提供页面/API。

| 方法 | 路径（前端访问加 /api） | 说明 |
| --- | --- | --- |
| GET / POST | /items | 分页列表 / 创建 |
| GET / PUT / DELETE | /items/{id} | 详情 / 完整更新 / 删除 |
| GET / POST | /locations | 列表 / 创建 |
| GET | /locations/tree | 树形位置 |
| PUT / DELETE | /locations/{id} | 更新 / 删除未被引用位置 |
| POST | /items/{id}/move | `to_location_id`、`note` |
| GET | /items/{id}/history | 最新历史在前 |
| GET | /search?q=关键词 | 支持 offset、limit |
| POST | /items/{id}/photos | multipart 字段 file |
| GET | /categories | 初始分类列表 |
| GET | /health | PostgreSQL、Redis 状态 |

`PUT /items/{id}` 需要完整名称和位置等字段；`POST /items` 示例：

```json
{"name":"剪刀","description":"红色手柄","location_id":1,"quantity":1}
```

删除物品会删除其数据库照片记录和位置历史（界面确认），但保留图片原文件以避免不可逆丢失；暂不自动清理孤立照片。历史引用过的位置不可删除，可重命名。历史保存位置 ID，位置重命名后显示当前名称，未提供历史名称快照。

## 数据库迁移

后端首次启动执行 `alembic upgrade head`，失败则拒绝启动。后续升级应使用 `scripts/update.sh`，严格先备份、停止写入、迁移、启动服务。不要直接编辑生产表，也不要删除数据库重建。

开发新增模型后生成迁移（在有开发数据库的环境）：

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD/backend/alembic:/app/alembic" backend alembic revision --autogenerate -m "describe change"
# 检查新迁移的 upgrade / downgrade，尤其 DROP 操作，然后提交到 Git
docker compose run --rm --no-deps backend alembic upgrade head
```

初始迁移是固定文件，不依赖当前模型动态建表。仅运行一个后端副本，避免并发迁移。PostgreSQL 主版本升级不属于普通应用迁移；禁止直接把镜像 17 改成 18。

## 停止、更新、重建与日志

```bash
docker compose stop                       # 停止，保留容器和宿主机数据
docker compose start                      # 恢复已存在容器
docker compose down                       # 删除容器和网络，保留绑定目录
bash scripts/update.sh                    # 推荐生产安全更新
# 已备份并安排维护后，也可手工：
git pull --ff-only
docker compose build
docker compose stop backend
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d --build --wait
# 只重建后端：
docker compose up -d --build --force-recreate backend
# 查看运行状态和日志：
docker compose ps
docker compose logs -f --tail=100
docker compose logs -f backend postgres redis
```

安全更新脚本要求干净 Git 工作区，先暂停后端并生成数据库和照片完整备份，然后 `git pull --ff-only`、构建、迁移、启动和依赖健康检查；**不清理旧备份**。迁移开始后遇错保持维护状态或报告失败，不会自动用旧应用连接已升级数据库。启动失败请查看日志和脚本输出的更新前备份路径，再决定修复或恢复。

## Docker 数据安全说明

### 数据实际在哪里

| 内容 | 宿主机 | 容器挂载 |
| --- | --- | --- |
| PostgreSQL 17 | `${DATA_ROOT}/postgres` | `/var/lib/postgresql/data` |
| Redis AOF | `${DATA_ROOT}/redis` | `/data` |
| 图片 | `${STORAGE_ROOT}/images` | `/app/storage/images` |
| 备份集 | `${DATA_ROOT}/backups` | backend 的 `/app/backups`（只读） |

本项目使用 **bind mount 宿主机目录**，没有依赖匿名 volume。`docker compose down` 本身不会删除宿主机的 PostgreSQL、Redis、图片或备份目录。删除 backend/frontend、删除并重建 PostgreSQL 容器、重新 build、更新 GitHub 代码均保留这些目录，前提是 `.env` 仍指向原路径，磁盘正常且未被其他操作删除。

**危险操作：**

- `docker compose down -v` 会删除 Compose 管理的 Docker volume。本项目 bind mount 不会因此被删除，但将来改为 volume 或在其他项目执行可能丢数据，因此不要习惯性使用 `-v`。
- 不要随意删除 `data/` 或 `storage/`，NAS 上同样不要删除 DATA_ROOT / STORAGE_ROOT 指向目录。
- 不要随意执行 `docker volume prune`。
- 不要随意执行 `rm -rf`，尤其是数据目录和磁盘挂载点。
- 不要将 PostgreSQL 17 数据目录直接交给 18+ 镜像。官方 18+ 调整了 PGDATA 和 volume 目标，必须制定主版本迁移与恢复方案。
- 不要改变 `.env` 路径后误把新初始化的空数据库当作“数据丢了”；先核对真实旧目录，勿覆盖。
- 不要在 PostgreSQL 运行时直接复制其原始文件当作有效备份。使用 pg_dump。

容器持久化不能防止硬盘故障、误删、NAS 损坏或勒索软件。备份与原数据同盘只防部分事故；定期将完整备份集加密复制到另一台设备/离线盘，并实测恢复。Redis AOF everysec 在断电时可能损失最近约一秒缓存，业务真实数据在 PostgreSQL。

官方依据：[Docker down](https://docs.docker.com/reference/cli/docker/compose/down/)、[bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)、[PostgreSQL 镜像目录规则](https://hub.docker.com/_/postgres)。

## 备份

```bash
bash scripts/backup.sh
# 可选调整保留天数，仅本次备份生效
RETENTION_DAYS=60 bash scripts/backup.sh
```

脚本使用维护锁排除同时备份/恢复/更新，暂停后端写入，使用 `pg_dump -Fc` 输出压缩 PostgreSQL 备份，并压缩完整照片目录。生成后验证 pg_restore 清单、gzip 完整性和 SHA256，成功后将 `.partial` 原子改名为正式目录；失败的 `.partial` 不当成完整备份。正常结束恢复原来运行的后端。不要绕过后端从其他程序并发写数据库/图片。

```text
${DATA_ROOT}/backups/20260909T030000Z-12345/
├── database.dump            # pg_dump custom 压缩格式，不能当 SQL 文本导入
├── images.tar.gz
├── SHA256SUMS
└── manifest.txt
```

默认只清理超过 30 天、名称匹配且含成功标识的完整备份目录；失败时不清理。恢复前自动备份、更新前备份不会主动清理任何旧备份。普通 backup.sh 的保留规则会覆盖这些旧的完整备份集，因此需长期保留的备份请复制到独立归档目录。

### 自动备份

由 NAS 计划任务或主机 cron 调度；仓库提供脚本，不会擅自修改当前机器的计划任务。示例每天凌晨 03:00（替换实际项目绝对路径）：

```cron
0 3 * * * /bin/bash /vol1/docker/home-item-manager/app/scripts/backup.sh >> /vol1/docker/home-item-manager/backup.log 2>&1
```

计划任务账号需要 Docker 权限和备份目录写权限，PATH 应包含 docker、gzip、sha256sum；日志目录需提前存在。备份会短暂停止后端，前端可能短暂显示服务不可用。每次核对计划任务日志和新备份，不要仅凭任务已创建就认定成功。

## 恢复

恢复会覆盖数据库。只使用可信来源、与代码版本兼容的完整备份集，先在隔离环境演练。

```bash
# 确认 .env 指向要恢复的环境，确保镜像已构建、目录已初始化
docker compose up -d --wait postgres redis
bash scripts/restore.sh /实际数据根目录/backups/20260909T030000Z-12345
# 必须手工输入 RESTORE，其余输入或 EOF 都取消
docker compose up -d --wait
docker compose ps
```

脚本先校验 SHA256、数据库目录清单及图片归档成员（拒绝目录穿越/链接），确认后暂停写入、自动备份当前数据。先恢复照片，再以 `pg_restore --clean --if-exists --single-transaction` 恢复数据库；失败的数据库恢复整体回滚。既有同名 UUID 文件必须内容一致，否则停止；不删除其他原照片。随后清空本应用专用 Redis DB，执行 Alembic，再恢复服务。Redis 清理或迁移失败保持后端停止，按提示修复。

恢复前自动备份可用于撤销误恢复。恢复到较旧代码/备份时先在隔离副本测试，跨版本新增依赖表可能导致 pg_restore 清理失败；不要自动 DROP 数据库。数据库成功不等于完整验收：必须查物品、打开照片、查看历史、重新执行备份。备份不包含 `.env`、Git 历史和 Redis 缓存，凭据需单独安全保存。

## PostgreSQL 与 Redis 运维

```bash
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
# psql 内可执行：\dt、SELECT count(*) FROM items;、\q
docker compose exec redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'
docker compose exec redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli INFO persistence'
docker compose exec redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli CONFIG GET appendonly'
docker compose exec backend alembic current
```

不要把真实密码直接写进命令历史或日志，不要对共享 Redis 实例运行本项目的 FLUSHDB 恢复逻辑；默认 Redis 为本应用专用。

## GitHub 管理与新服务器部署

Mac 首次上传前：

```bash
git init
git add .
git status --short
# 必须确认 .env、data、storage/images、.venv、node_modules 不在暂存区
git commit -m "Initial home item manager with persistent Docker deployment"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/home-item-manager.git
git push -u origin main
```

`.gitignore` 排除 `.env`、data、storage/images、__pycache__、node_modules、dist、*.db 等；只提供 `.env.example`。`.dockerignore` 同样排除本地依赖和数据，避免 Mac 架构文件进入 Linux 镜像。

新服务器安装 Docker / Compose / Git → clone → 复制并配置新的 `.env` → `bash scripts/init.sh` → `docker compose up -d --build --wait`。如需原家庭数据，安全传输完整备份集并运行恢复脚本；**clone GitHub 只得到代码，无法恢复数据库或照片**。具体 fnOS 和跨 NAS 迁移见专门部署说明。

## 自检

```bash
# 本地快速 API 测试（临时 SQLite，仅测合约，不代表 PostgreSQL 实测）
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/pytest -q tests
# 有 Docker 后，真实持久化验收（会重建服务，安排维护时间）
bash scripts/self-check.sh
```

自检脚本创建测试物品、照片和移动历史，重建 backend/frontend，重启并重建 PostgreSQL、检查 Redis AOF 重建保留、执行真实备份及隔离 PostgreSQL/图片恢复。测试数据保留供查看，脚本不会覆盖当前业务数据库进行恢复。详细已执行和未执行结果见 [REVIEW](docs/REVIEW.md)。
