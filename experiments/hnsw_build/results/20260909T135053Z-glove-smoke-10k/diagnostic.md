# HNSW build diagnostic report

- Status: `failed`
- Rows / dimensions: `10000` / `100`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`

## Failure

OperationalError: connection failed: connection to server at "127.0.0.1", port 55432 failed: FATAL:  no pg_hba.conf entry for host "192.168.107.1", user "postgres", database "postgres", no encryption


## Internal build timing

- Timing status: `incomplete`.
- expected exactly one main-fork summary for this logged-index workload
- CREATE INDEX did not return success; internal completion is not command success
- No stage bottleneck is attributed without a complete, successful run.