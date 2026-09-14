#!/bin/sh
set -eu
for variant in baseline candidate; do
    cd "/work/${variant}"
    mkdir -p "/work/out/${variant}"
    make -j4 PG_CONFIG=/opt/opentenbase/bin/pg_config PG_CPPFLAGS=-DHNSW_MEMORY
    cp vector.so "/work/out/${variant}/vector.so"
    {
        echo 'test_only=true'
        echo "variant=${variant}"
        echo 'mode=seed42-leader-native-workers-with-local-counters'
        echo 'PG_CPPFLAGS=-DHNSW_MEMORY'
        gcc --version
        /opt/opentenbase/bin/pg_config --version
        /opt/opentenbase/bin/pg_config --configure
        /opt/opentenbase/bin/pg_config --cflags
        sha256sum /opt/opentenbase/bin/postgres vector.so Makefile vector.control
        find src -type f \( -name '*.c' -o -name '*.h' \) -print0 | sort -z | xargs -0 sha256sum
    } > "/work/out/${variant}/identity.txt"
done
