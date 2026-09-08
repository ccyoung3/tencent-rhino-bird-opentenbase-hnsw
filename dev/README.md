# Mac 上的 Linux/ARM64 开发环境

本环境用于在 Apple Silicon Mac 上，以 OrbStack 的 Docker-compatible 接口
运行原生 `linux/arm64` 容器并编译：

- OpenTenBase `REL_18_STABLE`；
- pgvector `v0.8.6`；
- 单机 HNSW 构建、诊断与回归实验。

它不代表裸机 Linux、x86 或生产服务器性能。性能报告必须记录 Mac
宿主、Docker 资源、ARM64 架构、数据集、参数和冷暖缓存条件，并只比较
同一环境中的相对结果。

## 固定源码

```bash
git -C OpenTenBase rev-parse HEAD
git -C pgvector rev-parse HEAD
```

两个仓库的开发分支均为 `codex/hnsw-build-diagnostics`。

2026-09-02 的实际编译、版本与 HNSW 验证结果见
[[../docs/2026-09-02-mac-arm64-baseline|Mac ARM64 环境基线]]。

## 构建与启动

在项目根目录执行：

```bash
docker compose -f dev/compose.yml build
docker compose -f dev/compose.yml up -d
docker compose -f dev/compose.yml ps
```

容器只把数据库端口绑定到宿主的 `127.0.0.1:55432`。本环境中的
`trust` 认证仅用于本机隔离开发，不能用于共享或生产环境。

## 最小验证

```bash
docker compose -f dev/compose.yml exec -T db \
  psql -U postgres -d postgres < dev/sql/smoke.sql

docker compose -f dev/compose.yml exec -T db \
  psql -U postgres -d postgres \
  -c "SELECT version(), extversion FROM pg_extension WHERE extname = 'vector';"
```

## 停止

```bash
docker compose -f dev/compose.yml down
```

该命令保留数据库命名卷。除非明确决定丢弃实验数据，否则不要添加
`--volumes`。

## 运行 pgvector TAP 测试

测试镜像包含 OpenTenBase 的 Perl 测试库和 `IPC::Run`，并使用非 root
用户执行 `initdb`：

```bash
docker build \
  -f dev/Dockerfile \
  --target test \
  -t opentenbase-pg18-pgvector:test-arm64 \
  .

docker run --rm --shm-size=2g \
  opentenbase-pg18-pgvector:test-arm64 \
  make prove_installcheck \
  PROVE_TESTS=test/t/045_hnsw_low_memory_build.pl
```

## CentOS Stream 9 补充验证

Docker 环境之外，冻结候选已在 OrbStack CentOS Stream 9 原生 ARM64 Machine
中完成 clean build、动态链接、专项 TAP、4 项 SQL regression、最小 HNSW
smoke 和全部 27 个 HNSW TAP 验证。

- 复现步骤：[[centos/README|CentOS Stream 9 ARM64 兼容性复现]]；
- 实测报告：
  [[../docs/2026-09-03-centos-stream9-arm64-compatibility|CentOS Stream 9 ARM64 兼容性报告]]。

该验证只增加发行版与工具链兼容性证据，不与本页 Docker 性能数字横向比较。
