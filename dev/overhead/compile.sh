#!/bin/sh
set -eu
mkdir -p /work/out
for variant in baseline candidate; do
    for mode in seed42 normal; do
        source_dir="/work/${variant}-${mode}"
        output_dir="/work/out/${variant}/${mode}"
        cp -a "/work/${variant}" "${source_dir}"
        mkdir -p "${output_dir}"
        cd "${source_dir}"
        flags=""
        if [ "${mode}" = seed42 ]; then flags="-DHNSW_MEMORY"; fi
        make -j4 PG_CONFIG=/opt/opentenbase/bin/pg_config PG_CPPFLAGS="${flags}"
        cp vector.so "${output_dir}/vector.so"
        {
            echo "variant=${variant}"
            echo "mode=${mode}"
            echo "PG_CPPFLAGS=${flags}"
            gcc --version
            /opt/opentenbase/bin/pg_config --version
            /opt/opentenbase/bin/pg_config --configure
            /opt/opentenbase/bin/pg_config --cflags
            sha256sum /opt/opentenbase/bin/postgres vector.so Makefile vector.control
            find src -type f \( -name '*.c' -o -name '*.h' \) -print0 | sort -z | xargs -0 sha256sum
        } > "${output_dir}/identity.txt"
    done
done
