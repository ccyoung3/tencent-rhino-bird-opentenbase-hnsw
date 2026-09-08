# CentOS Stream 9 ARM64 兼容性复现

本流程在 Apple Silicon Mac 的 OrbStack Linux Machine 中验证冻结的
OpenTenBase 18.6 + pgvector 0.8.6 HNSW 诊断候选。它只验证发行版、工具链、
编译、链接与功能回归，不运行或比较性能数据。

2026-09-03 的实际结果见
[[../../docs/2026-09-03-centos-stream9-arm64-compatibility|CentOS Stream 9 ARM64 兼容性报告]]。

## 固定输入

```text
OpenTenBase commit:
4c66f172a09296b08d53526f802ddd2b461bd7e8

pgvector base commit:
8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c

candidate patch SHA-256:
eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f
```

冻结补丁位于：

```text
experiments/hnsw_build/results/
20260902T163630Z-pre-centos-freeze/pgvector-candidate.patch
```

## 创建 Machine

以下 Mac 侧命令都从本项目根目录执行。OrbStack 2.0.5 使用：

```bash
machine_user="$(id -un)"

orb create \
  --arch arm64 \
  --user "$machine_user" \
  centos:9-Stream \
  opentenbase-centos
```

本次实测的 `machine_user` 是 `ccyoung`；其他复现者会使用自己的 macOS 用户名。

该版本不支持 `orb create` 的 `--memory`、`--cpus`、`--disk` 参数。进入后应
记录实际环境：

```bash
orb info opentenbase-centos --format json
orb -m opentenbase-centos

cat /etc/os-release
uname -m
nproc
free -h
df -h / /dev/shm
```

所有源码、构建目录、安装目录和数据库目录都放在 Machine 的 home 中，不在
`/mnt/mac` 共享目录中编译。

## 安装依赖

以下命令在 Machine 内由默认普通用户执行；只有包管理使用 `sudo`：

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --set-enabled crb

sudo dnf install -y \
  gcc make bison flex git diffutils tar gzip file findutils \
  pkgconf-pkg-config readline-devel zlib-devel openssl-devel libxml2-devel \
  perl perl-IPC-Run perl-Test-Harness perl-Test-Simple perl-Time-HiRes
```

`perl-IPC-Run` 来自 CentOS Stream 9 CRB。OpenTenBase 配置阶段会再次检查
`prove`、`IPC::Run`、`Test::More` 和 `Time::HiRes`。

## 取回精确源码并应用补丁

先从 Mac 推送冻结补丁和 smoke SQL：

```bash
orb -m opentenbase-centos mkdir -p \
  opentenbase-centos-validation/incoming

orb push -m opentenbase-centos \
  experiments/hnsw_build/results/20260902T163630Z-pre-centos-freeze/pgvector-candidate.patch \
  dev/sql/smoke.sql \
  opentenbase-centos-validation/incoming/
```

然后在 Machine 内执行：

```bash
validation_root="$HOME/opentenbase-centos-validation"
mkdir -p "$validation_root"
cd "$validation_root"

git init OpenTenBase
git -C OpenTenBase remote add origin \
  https://github.com/OpenTenBase/OpenTenBase.git
git -C OpenTenBase fetch --depth=1 origin \
  4c66f172a09296b08d53526f802ddd2b461bd7e8
git -C OpenTenBase checkout --detach FETCH_HEAD

git init pgvector
git -C pgvector remote add origin https://github.com/pgvector/pgvector.git
git -C pgvector fetch --depth=1 origin \
  8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c
git -C pgvector checkout --detach FETCH_HEAD

git -C pgvector apply --check ../incoming/pgvector-candidate.patch
git -C pgvector apply ../incoming/pgvector-candidate.patch
git -C pgvector diff --check
git -C pgvector diff --binary HEAD | sha256sum
```

最后一条命令必须得到固定的候选补丁 SHA-256。

## 构建 OpenTenBase

使用独立构建目录，配置时启用 TAP：

```bash
install_prefix="$validation_root/install"
otb_build="$validation_root/OpenTenBase-build"

mkdir -p "$install_prefix" "$otb_build"
cd "$otb_build"

"$validation_root/OpenTenBase/configure" \
  --prefix="$install_prefix" \
  --without-icu \
  --with-openssl \
  --with-libxml \
  --enable-tap-tests

make -j6
make install
```

验证版本与 PGXS TAP 模块：

```bash
"$install_prefix/bin/postgres" --version
"$install_prefix/bin/pg_config" --version

pgxs_file="$("$install_prefix/bin/pg_config" --pgxs)"
test -f "$(dirname "$pgxs_file")/../test/perl/PostgreSQL/Test/Cluster.pm"
test -f "$(dirname "$pgxs_file")/../test/perl/PostgreSQL/Test/Utils.pm"
```

## 构建 pgvector

```bash
export PATH="$install_prefix/bin:$PATH"
export PG_CONFIG="$install_prefix/bin/pg_config"
export LC_ALL=C

cd "$validation_root/pgvector"
make PG_CONFIG="$PG_CONFIG" clean
PG_CFLAGS="-Werror" make -j6 PG_CONFIG="$PG_CONFIG"
PG_CFLAGS="-Werror" make PG_CONFIG="$PG_CONFIG" install

ldd "$install_prefix/bin/postgres"
ldd "$install_prefix/lib/postgresql/vector.so"
```

两份 `ldd` 输出均不得包含 `not found`。把 `PG_CFLAGS` 作为环境变量传入，可在
增加 `-Werror` 的同时保留 pgvector Makefile 追加的 ARM64 优化参数。

## TAP

TAP 自行创建临时实例，应先清除外部连接变量：

```bash
unset PGHOST PGPORT PGUSER PGDATABASE PGDATA
cd "$validation_root/pgvector"

make PG_CONFIG="$PG_CONFIG" prove_installcheck \
  PROVE_TESTS=test/t/045_hnsw_low_memory_build.pl

make PG_CONFIG="$PG_CONFIG" prove_installcheck \
  'PROVE_TESTS=test/t/*hnsw*.pl'
```

预期分别为：

```text
Files=1, Tests=5, Result: PASS
Files=27, Tests=411, Result: PASS
```

## SQL regression 与 smoke

`make installcheck` 不会自行启动数据库，因此使用本次源码安装出的 OpenTenBase
建立独立实例：

```bash
cluster_dir="$validation_root/sql-cluster"
socket_dir="$validation_root/sql-socket"
if [ -e "$cluster_dir" ]; then
  echo "refusing to reuse existing cluster: $cluster_dir" >&2
  exit 1
fi
mkdir -p "$socket_dir"

initdb -D "$cluster_dir" \
  --auth-local=trust \
  --auth-host=reject \
  --locale=C \
  --encoding=UTF8

cleanup_server() {
  if pg_ctl -D "$cluster_dir" status >/dev/null 2>&1; then
    pg_ctl -D "$cluster_dir" -m fast -w stop
  fi
}

trap cleanup_server EXIT

pg_ctl -D "$cluster_dir" \
  -l "$validation_root/sql-server.log" \
  -o "-c listen_addresses= -c unix_socket_directories=$socket_dir -c port=55439" \
  -w start

export PGHOST="$socket_dir"
export PGPORT=55439
export PGUSER="$(id -un)"
export PGDATABASE=postgres

psql -X -v ON_ERROR_STOP=1 \
  -f "$validation_root/incoming/smoke.sql"

cd "$validation_root/pgvector"
make PG_CONFIG="$PG_CONFIG" installcheck \
  'REGRESS=hnsw_vector hnsw_halfvec hnsw_bit hnsw_sparsevec'

cleanup_server
trap - EXIT
```

smoke 必须显示 HNSW `Index Scan`；SQL regression 必须显示
`All 4 tests passed`。

## 最终完整性

```bash
git -C "$validation_root/OpenTenBase" status --short
git -C "$validation_root/pgvector" diff --check
git -C "$validation_root/pgvector" diff --binary HEAD | sha256sum
git -C "$validation_root/pgvector" status --short
```

OpenTenBase 应保持 clean；pgvector 只能包含固定的 4 个修改文件，且补丁 SHA
必须保持不变。

回到 Mac 项目根目录后，可校验本次 CentOS 原始证据本身：

```bash
shasum -a 256 -c \
  experiments/hnsw_build/results/20260903T010012Z-centos-stream9-arm64/SHA256SUMS
```

`SHA256SUMS` 中的路径相对于项目根目录，不能在证据子目录内直接执行该命令。
