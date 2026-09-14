## Internal build timing

| Internal phase | Elapsed |
|---|---:|
| memory_build | 2.426489s |
| disk_insert | 70.307945s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (96.5% of internal elapsed time); spill=`True`.

- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
