#!/usr/bin/env bash
# This round has its own Linux-native source, build, install and evidence paths.
set -euo pipefail
timing_root=/home/ccyoung/opentenbase-timing-20260906
previous_root=/home/ccyoung/opentenbase-centos-validation
test ! -e "$timing_root/pgvector"
mkdir -p "$timing_root/evidence" "$timing_root/OpenTenBase-build"
exec > >(tee "$timing_root/evidence/session.log") 2>&1
cat /etc/os-release
uname -m
gcc --version
git -C "$previous_root/OpenTenBase" rev-parse HEAD
test -z "$(git -C "$previous_root/OpenTenBase" status --porcelain)"
git clone --no-hardlinks --no-checkout "$previous_root/pgvector" "$timing_root/pgvector"
git -C "$timing_root/pgvector" checkout --detach 8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c
git -C "$timing_root/pgvector" apply --check "$timing_root/incoming/pgvector.patch"
git -C "$timing_root/pgvector" apply "$timing_root/incoming/pgvector.patch"
cp "$timing_root/incoming/049_hnsw_build_timing.pl" "$timing_root/pgvector/test/t/"
cd "$timing_root/OpenTenBase-build"
"$previous_root/OpenTenBase/configure" --prefix="$timing_root/install" \
    --without-icu --with-openssl --with-libxml --enable-tap-tests \
    2>&1 | tee "$timing_root/evidence/opentenbase-configure.log"
make -j6 2>&1 | tee "$timing_root/evidence/opentenbase-build.log"
make install 2>&1 | tee "$timing_root/evidence/opentenbase-install.log"
export PATH="$timing_root/install/bin:$PATH"
export PG_CONFIG="$timing_root/install/bin/pg_config"
export LC_ALL=C
unset PGHOST PGPORT PGUSER PGDATABASE PGDATA
cd "$timing_root/pgvector"
PG_CFLAGS=-Werror make -j6 2>&1 | tee "$timing_root/evidence/pgvector-build-werror.log"
make install 2>&1 | tee "$timing_root/evidence/pgvector-install.log"
ldd "$timing_root/install/lib/postgresql/vector.so" | tee "$timing_root/evidence/ldd.log"
make prove_installcheck 'PROVE_TESTS=test/t/045_hnsw_low_memory_build.pl test/t/049_hnsw_build_timing.pl' \
    2>&1 | tee "$timing_root/evidence/tap-targeted.log"
make prove_installcheck 'PROVE_TESTS=test/t/*hnsw*.pl' \
    2>&1 | tee "$timing_root/evidence/tap-full.log"
initdb -D "$timing_root/sql-cluster" --auth-local=trust --auth-host=reject
mkdir -p "$timing_root/socket"
cleanup_server() {
    pg_ctl -D "$timing_root/sql-cluster" -m fast -w stop || true
}
trap cleanup_server EXIT
pg_ctl -D "$timing_root/sql-cluster" -l "$timing_root/evidence/sql-server.log" \
    -o "-c listen_addresses= -k $timing_root/socket -p 55440" -w start
export PGHOST="$timing_root/socket" PGPORT=55440
make installcheck 'REGRESS=hnsw_vector hnsw_halfvec hnsw_bit hnsw_sparsevec' \
    2>&1 | tee "$timing_root/evidence/sql-regression.log"
psql -X -v ON_ERROR_STOP=1 -d postgres -f "$timing_root/incoming/smoke.sql" \
    2>&1 | tee "$timing_root/evidence/smoke.log"
cleanup_server
trap - EXIT
git diff --check
git diff --binary HEAD | sha256sum | tee "$timing_root/evidence/patch-sha256.txt"
sha256sum src/hnsw.c src/hnsw.h src/hnswbuild.c test/t/049_hnsw_build_timing.pl \
    | tee "$timing_root/evidence/source-sha256.txt"
printf 'CentOS timing candidate validation passed\n'
