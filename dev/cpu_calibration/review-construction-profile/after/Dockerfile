FROM opentenbase-pg18-pgvector:timing-v1-test-arm64 AS compiler
USER root
WORKDIR /work
COPY calibrate.c compile.sh /work/
RUN /bin/sh /work/compile.sh

FROM opentenbase-pg18-pgvector:timing-v1-arm64 AS runtime
COPY --from=compiler /work/out/ /opt/cpu-calibration/
LABEL cpu.calibration.test_only=true
USER postgres
ENTRYPOINT ["/bin/sleep"]
CMD ["180"]
