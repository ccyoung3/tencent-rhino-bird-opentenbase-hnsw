#!/bin/sh
set -eu
mkdir -p /work/out
gcc -O2 -march=native -ftree-vectorize -fassociative-math -fno-signed-zeros -fno-trapping-math -std=c11 -Wall -Wextra -Werror -fopt-info-vec-optimized=/work/out/vectorization.txt /work/calibrate.c -o /work/out/calibrate
{
    echo 'gcc -O2 -march=native -ftree-vectorize -fassociative-math -fno-signed-zeros -fno-trapping-math -std=c11 -Wall -Wextra -Werror -fopt-info-vec-optimized=/work/out/vectorization.txt /work/calibrate.c -o /work/out/calibrate'
    gcc --version
    uname -a
    sha256sum /work/calibrate.c /work/out/calibrate
} > /work/out/compiler-identity.txt
objdump -d /work/out/calibrate > /work/out/disassembly.txt
ldd /work/out/calibrate > /work/out/ldd.txt
cp /work/calibrate.c /work/out/calibrate.c
