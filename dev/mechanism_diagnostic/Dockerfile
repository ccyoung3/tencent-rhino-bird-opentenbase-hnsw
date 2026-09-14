FROM opentenbase-pg18-pgvector:timing-v1-test-arm64 AS compiler
USER root
WORKDIR /work
COPY baseline/ /work/baseline/
COPY candidate/ /work/candidate/
COPY compile.sh /work/compile.sh
RUN /bin/sh /work/compile.sh

FROM opentenbase-pg18-pgvector:timing-v1-arm64 AS runtime
ARG VARIANT
COPY --from=compiler /work/out/${VARIANT}/vector.so /opt/opentenbase/lib/postgresql/vector.so
COPY --from=compiler /work/out/${VARIANT}/identity.txt /opt/hnsw-acceptance-identity.txt
LABEL hnsw.mechanism.test_only=true hnsw.mechanism.variant=$VARIANT
